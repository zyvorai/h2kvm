# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/transports/hyperctl_common.py
"""
hyperctl / hypersdk common helpers for hyper2kvm.

Design goals:
  - Integrate with hypervisord daemon for high-performance VM exports
  - Fallback to pyvmomi if hyperctl/daemon not available
  - Provide both CLI (hyperctl) and API (direct REST) interfaces
  - Match the govc_common.py pattern for consistency
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ....core.exceptions import VMwareError

logger = logging.getLogger(__name__)


@dataclass
class HyperCtlConfig:
    """Configuration for hyperctl CLI tool."""

    daemon_url: str = "http://localhost:8080"
    hyperctl_path: str = "hyperctl"
    timeout: int = 3600


class HyperCtlRunner:
    """
    Wrapper for hyperctl CLI tool (hypersdk).

    Similar to GovcRunner but for the Go-based provider daemon.
    """

    def __init__(
        self,
        daemon_url: str = "http://localhost:8080",
        hyperctl_path: str = "hyperctl",
        timeout: int = 3600,
    ):
        self.daemon_url = daemon_url
        self.hyperctl_path = hyperctl_path
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

    def _run_command(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run hyperctl command."""
        # Build command - only add -daemon if not using default
        # Note: The installed hyperctl binary may not support -daemon flag,
        # so we rely on default http://localhost:8080
        cmd = [self.hyperctl_path, *args]

        self.logger.debug("Running hyperctl: %s", " ".join(cmd))

        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=check,
            )
        except subprocess.TimeoutExpired:
            raise VMwareError(msg=f"hyperctl command timed out after {self.timeout}s") from None
        except subprocess.CalledProcessError as e:
            raise VMwareError(msg=f"hyperctl failed: {e.stderr}") from e
        except FileNotFoundError:
            raise VMwareError(
                msg=f"hyperctl not found at {self.hyperctl_path}. "
                "Install hypersdk or set HYPERCTL_PATH environment variable."
            ) from None

    def check_daemon_status(self) -> dict[str, Any]:
        """Check if hypervisord daemon is running and get status."""
        result = self._run_command(["status"])

        # hyperctl status outputs a table, but we want JSON for parsing
        # For now, just check if it succeeded
        if result.returncode == 0:
            self.logger.info("hypervisord daemon is running")
            return {"status": "running", "output": result.stdout}
        raise VMwareError(msg="hypervisord daemon not responding")

    def submit_export_job(
        self,
        vm_path: str,
        output_path: str,
        # pylint: disable=unused-argument
        # Kept in the public signature (matching export_vm()/export_vm_hyperctl()) for API
        # consistency even though the installed hyperctl binary doesn't yet accept these flags.
        parallel_downloads: int = 4,
        remove_cdrom: bool = True,
    ) -> str:
        """
        Submit VM export job to hypervisord daemon.

        Note: The installed hyperctl binary only supports basic submit flags.
        Options like parallel_downloads and remove_cdrom are configured on the daemon side.

        Returns:
            job_id: The job ID for tracking progress
        """
        args = [
            "submit",
            "-vm",
            vm_path,
            "-output",
            output_path,
        ]

        # Note: -parallel and -remove-cdrom flags are not supported by the installed binary
        # These options are configured in the daemon's config file

        result = self._run_command(args)

        # Parse job ID from output
        # Output format: "  - Job ID: <job-id>" or JSON with "job_id" field
        stdout = result.stdout.strip()

        # Try JSON first
        try:
            data = json.loads(stdout)
            if "job_id" in data:
                self.logger.info("Export job submitted: %s", data["job_id"])
                return data["job_id"]
        except (json.JSONDecodeError, TypeError):
            pass

        # Fall back to line-by-line parsing
        for line in stdout.split("\n"):
            lower = line.lower()
            if "job id:" in lower or "job_id:" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    job_id = parts[1].strip()
                    if job_id:
                        self.logger.info("Export job submitted: %s", job_id)
                        return job_id

        raise VMwareError(msg=f"Failed to parse job ID from hyperctl output: {stdout[:200]}")

    def query_job(self, job_id: str) -> dict[str, Any]:
        """Query job status."""
        result = self._run_command(["query", "-id", job_id])

        stdout = result.stdout.strip()
        job_data: dict[str, Any] = {"job_id": job_id, "output": stdout}

        # Try JSON first (newer hyperctl versions)
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                job_data.update(data)
                # Normalize status field
                if "status" in data:
                    job_data["status"] = data["status"].lower()
                if "progress" in data:
                    with contextlib.suppress(ValueError, TypeError):
                        job_data["progress_percent"] = float(str(data["progress"]).rstrip("%"))
                return job_data
        except (json.JSONDecodeError, TypeError):
            pass

        # Fall back to table parsing
        try:
            lines = stdout.split("\n")
            if len(lines) >= 2:
                header = lines[0].split()
                data_line = lines[1].split(None, len(header) - 1)

                for i, field in enumerate(header):
                    if i < len(data_line):
                        job_data[field.lower()] = data_line[i]

                # Normalize common fields
                if "status" in job_data:
                    job_data["status"] = job_data["status"].lower()
                if "progress" in job_data:
                    progress_str = str(job_data["progress"]).rstrip("%")
                    with contextlib.suppress(ValueError):
                        job_data["progress_percent"] = float(progress_str)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Table-format parsing is a best-effort fallback for older hyperctl output;
            # any failure should just leave job_data as-is rather than crash the query.
            logger.debug("Failed to parse hyperctl query output: %s", e)

        return job_data

    def wait_for_job_completion(
        self,
        job_id: str,
        poll_interval: int = 5,
        timeout: int | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Wait for export job to complete.

        Args:
            job_id: Job ID to wait for
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait (None = unlimited)
            progress_callback: Optional callback(progress_dict) for progress updates

        Returns:
            Final job status dict
        """
        start_time = time.time()

        while True:
            if timeout and (time.time() - start_time) > timeout:
                raise VMwareError(msg=f"Job {job_id} timed out after {timeout}s")

            status = self.query_job(job_id)

            # Check terminal states via parsed status field first, then raw output
            job_status = status.get("status", "").lower()

            if job_status == "completed":
                self.logger.info("Job %s completed successfully", job_id)
                return status
            if job_status == "failed":
                msg = status.get("error", status.get("message", "unknown error"))
                raise VMwareError(msg=f"Job {job_id} failed: {msg}")
            if job_status == "cancelled":
                raise VMwareError(msg=f"Job {job_id} was cancelled")

            # Call progress callback if provided
            if progress_callback:
                try:
                    progress_callback(status)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # A caller-supplied callback must never break the polling loop.
                    self.logger.warning("Progress callback error: %s", e)

            time.sleep(poll_interval)

    # High-level wrapper surfacing submit + wait options together, matching the
    # export_vm_govc()/export_vm_hyperctl() convenience-function signatures.
    def export_vm(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        vm_path: str,
        output_path: str,
        parallel_downloads: int = 4,
        remove_cdrom: bool = True,
        wait: bool = True,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Export VM using hypervisord daemon (high-level wrapper).

        Args:
            vm_path: vSphere VM path (e.g., "/datacenter/vm/my-vm")
            output_path: Local output directory
            parallel_downloads: Number of parallel file downloads
            remove_cdrom: Remove CD/DVD devices before export
            wait: Wait for job completion
            progress_callback: Optional progress callback

        Returns:
            Job result dict
        """
        # Ensure output directory exists
        Path(output_path).mkdir(parents=True, exist_ok=True)

        # Submit job
        job_id = self.submit_export_job(
            vm_path=vm_path,
            output_path=output_path,
            parallel_downloads=parallel_downloads,
            remove_cdrom=remove_cdrom,
        )

        if not wait:
            return {"job_id": job_id, "status": "submitted"}

        # Wait for completion
        return self.wait_for_job_completion(
            job_id=job_id,
            progress_callback=progress_callback,
        )


# Factory function for easy instantiation


def create_hyperctl_runner(
    daemon_url: str | None = None,
    hyperctl_path: str | None = None,
) -> HyperCtlRunner:
    """
    Create HyperCtlRunner with environment variable defaults.

    Environment variables:
        HYPERVISORD_URL: Daemon URL (default: http://localhost:8080)
        HYPERCTL_PATH: Path to hyperctl binary (default: hyperctl)
    """
    daemon_url = daemon_url or os.getenv("HYPERVISORD_URL", "http://localhost:8080")
    hyperctl_path = hyperctl_path or os.getenv("HYPERCTL_PATH", "hyperctl")

    return HyperCtlRunner(
        daemon_url=daemon_url,
        hyperctl_path=hyperctl_path,
    )


# Convenience function for export


# Mirrors HyperCtlRunner.export_vm()'s options plus daemon_url for one-shot use.
def export_vm_hyperctl(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    vm_path: str,
    output_path: str,
    parallel_downloads: int = 4,
    remove_cdrom: bool = True,
    daemon_url: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Export VM using hyperctl (convenience function).

    This is the equivalent of export_vm_govc() but using hypersdk.

    Example:
        >>> from hyper2kvm.vmware.transports.hyperctl_common import export_vm_hyperctl
        >>> result = export_vm_hyperctl(
        ...     vm_path="/datacenter/vm/my-vm",
        ...     output_path="/tmp/export",
        ...     parallel_downloads=4,
        ... )
        >>> print(result["job_id"])
    """
    runner = create_hyperctl_runner(daemon_url=daemon_url)

    return runner.export_vm(
        vm_path=vm_path,
        output_path=output_path,
        parallel_downloads=parallel_downloads,
        remove_cdrom=remove_cdrom,
        progress_callback=progress_callback,
    )
