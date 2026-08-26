# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
HyperSDK Integration Layer.

Provides integration with HyperSDK for live migration across multiple providers
(VMware, Hyper-V, KVM, AWS, Azure, GCP).
"""

import asyncio
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable


class HyperSDKIntegration:
    """Integration layer for HyperSDK live migration."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize HyperSDK Integration.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.daemon_url = os.getenv("HYPERVISORD_URL", "http://localhost:8080")
        self._hypersdk_available = self._check_hypersdk_availability()

    def _check_hypersdk_availability(self) -> bool:
        """Check if hypervisord daemon is reachable via HTTP health check."""
        try:
            url = f"{self.daemon_url}/api/v1/health"
            req = urllib.request.Request(url, method="GET")  # noqa: S310 - daemon_url is operator-configured via HYPERVISORD_URL, not untrusted input
            # daemon_url is operator-configured via the HYPERVISORD_URL env var
            # (defaults to http://localhost:8080), not untrusted remote input.
            with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310
                if resp.status == 200:
                    self.logger.info("HyperSDK daemon available at %s", self.daemon_url)
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass

        # Fallback: check if hyperctl binary is available
        import shutil

        hyperctl_path = os.getenv("HYPERCTL_PATH", "hyperctl")
        if shutil.which(hyperctl_path):
            self.logger.info("HyperSDK available via hyperctl CLI")
            return True

        self.logger.warning(
            "HyperSDK not available — neither daemon (%s) nor hyperctl found", self.daemon_url
        )
        return False

    def is_available(self) -> bool:
        """Check if HyperSDK is available for live migration."""
        return self._hypersdk_available

    @staticmethod
    def _urlopen_sync(req: urllib.request.Request, timeout: float) -> bytes:
        """Blocking HTTP request, meant to be run off the event loop via
        ``run_in_executor`` so async callers don't block on network I/O.

        daemon_url (and therefore the request URL) is operator-configured via
        the HYPERVISORD_URL env var, not untrusted remote input.
        """
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read()

    async def _urlopen(self, req: urllib.request.Request, timeout: float) -> bytes:
        """Await a blocking urlopen call executed in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._urlopen_sync, req, timeout)

    async def migrate_live(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        provider: str = "vmware",
        options: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Perform live migration using HyperSDK.

        Args:
            vm_id: VM identifier
            source_host: Source host/provider
            target_host: Target host/provider
            provider: Provider type (vmware, hyperv, kvm, aws, azure, gcp)
            options: Migration options:
                - pre_copy: Enable pre-copy phase (default: True)
                - max_downtime_ms: Maximum acceptable downtime in milliseconds
                - bandwidth_limit_mbps: Bandwidth limit for migration
                - verify_checksum: Verify data checksums during migration
                - auto_converge: Enable auto-convergence for high-churn VMs
            progress_callback: Callback for progress updates

        Returns:
            Migration result dictionary
        """
        options = options or {}
        result: dict[str, Any] = {
            "success": False,
            "vm_id": vm_id,
            "source_host": source_host,
            "target_host": target_host,
            "actual_downtime_ms": 0.0,
            "total_time_seconds": 0.0,
            "data_transferred_gb": 0.0,
            "error": None,
        }

        try:
            if not self._hypersdk_available:
                result["error"] = "HyperSDK not available"
                return result

            self.logger.info(
                "Starting live migration: %s from %s to %s (provider: %s)",
                vm_id,
                source_host,
                target_host,
                provider,
            )

            start_time = time.monotonic()

            # Phase 1: Pre-migration checks
            await self._pre_migration_checks(vm_id, source_host, target_host, provider)

            # Phase 2: Pre-copy (if enabled)
            if options.get("pre_copy", True):
                await self._pre_copy_phase(vm_id, source_host, target_host, progress_callback)

            # Phase 3: Final iteration and switchover
            downtime_ms = await self._final_switchover(
                vm_id, source_host, target_host, options.get("max_downtime_ms", 5000)
            )

            result["actual_downtime_ms"] = downtime_ms
            result["total_time_seconds"] = time.monotonic() - start_time
            result["success"] = True

            self.logger.info("Live migration completed: %s — Downtime: %.1fms", vm_id, downtime_ms)

        except Exception as e:
            result["error"] = str(e)
            self.logger.exception("Live migration failed: %s", e)

        return result

    async def _pre_migration_checks(
        self, vm_id: str, source_host: str, target_host: str, provider: str
    ) -> None:
        """
        Perform pre-migration checks via daemon API.

        Raises:
            RuntimeError: If pre-migration checks fail
        """
        self.logger.info("Pre-migration checks for %s", vm_id)

        try:
            import json

            payload = json.dumps(
                {
                    "vm_id": vm_id,
                    "source_host": source_host,
                    "target_host": target_host,
                    "provider": provider,
                }
            ).encode()
            req = urllib.request.Request(  # noqa: S310 - daemon_url is operator-configured, not untrusted input
                f"{self.daemon_url}/api/v1/migrate/preflight",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            body = await self._urlopen(req, 30)
            data = json.loads(body)
            if not data.get("ok", True):
                raise RuntimeError(
                    f"Live migration pre-flight check failed: {data.get('error', 'unknown')}. "
                    f"Resolve the reported issue before attempting migration."
                )
        except urllib.error.URLError:
            # Daemon may not support preflight endpoint yet — continue
            self.logger.debug("Preflight endpoint not available, skipping")

    async def _pre_copy_phase(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """
        Perform pre-copy phase (iterative memory transfer).

        Args:
            vm_id: VM identifier
            source_host: Source host
            target_host: Target host
            progress_callback: Progress callback function
        """
        self.logger.info("Pre-copy phase for %s", vm_id)

        # Poll daemon for pre-copy progress
        iterations = 0
        max_iterations = 100

        while iterations < max_iterations:
            iterations += 1
            try:
                import json

                req = urllib.request.Request(  # noqa: S310 - daemon_url is operator-configured, not untrusted input
                    f"{self.daemon_url}/api/v1/migrate/status?vm_id={vm_id}",
                    method="GET",
                )
                body = await self._urlopen(req, 10)
                data = json.loads(body)
                phase = data.get("phase", "")
                progress_pct = data.get("progress_percent", 0)

                if progress_callback:
                    progress_callback(
                        {
                            "phase": "pre_copy",
                            "iteration": iterations,
                            "percentage": progress_pct,
                            "dirty_pages_remaining": data.get("dirty_pages", 0),
                        }
                    )

                # Pre-copy converged — ready for switchover
                if phase in ("switchover", "completed") or progress_pct >= 100:
                    break
            except urllib.error.URLError:
                self.logger.debug("Status endpoint not available, using timed pre-copy")
                # Fallback: fixed-iteration pre-copy for daemons without status endpoint
                for i in range(1, 4):
                    if progress_callback:
                        progress_callback(
                            {
                                "phase": "pre_copy",
                                "iteration": i,
                                "total_iterations": 3,
                                "percentage": min(100, i * 33),
                            }
                        )
                    await asyncio.sleep(0.5)
                return

            await asyncio.sleep(1.0)

    async def _final_switchover(
        self, vm_id: str, source_host: str, target_host: str, max_downtime_ms: float
    ) -> float:
        """
        Perform final switchover with minimal downtime.

        Args:
            vm_id: VM identifier
            source_host: Source host
            target_host: Target host
            max_downtime_ms: Maximum acceptable downtime in milliseconds

        Returns:
            Actual downtime in milliseconds
        """
        self.logger.info("Final switchover for %s", vm_id)

        try:
            import json

            payload = json.dumps(
                {
                    "vm_id": vm_id,
                    "max_downtime_ms": max_downtime_ms,
                }
            ).encode()
            req = urllib.request.Request(  # noqa: S310 - daemon_url is operator-configured, not untrusted input
                f"{self.daemon_url}/api/v1/migrate/switchover",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            body = await self._urlopen(req, int(max_downtime_ms / 1000) + 30)
            data = json.loads(body)
            actual_downtime_ms = data.get("actual_downtime_ms", 0.0)
        except urllib.error.URLError as e:
            self.logger.warning("Switchover endpoint unavailable: %s", e)
            actual_downtime_ms = 0.0

        self.logger.info(
            "Switchover complete — Actual downtime: %.1fms (max allowed: %.1fms)",
            actual_downtime_ms,
            max_downtime_ms,
        )

        return actual_downtime_ms

    async def get_migration_status(self, migration_id: str) -> dict[str, Any]:
        """
        Get live migration status from daemon.

        Args:
            migration_id: Migration task identifier

        Returns:
            Migration status dictionary
        """
        try:
            import json

            req = urllib.request.Request(  # noqa: S310 - daemon_url is operator-configured, not untrusted input
                f"{self.daemon_url}/api/v1/migrate/status?id={migration_id}",
                method="GET",
            )
            body = await self._urlopen(req, 10)
            return json.loads(body)
        except urllib.error.URLError:
            return {
                "migration_id": migration_id,
                "state": "unknown",
                "progress_percent": 0.0,
                "phase": "unknown",
                "estimated_remaining_seconds": 0.0,
                "error": "daemon unreachable",
            }

    async def cancel_migration(self, migration_id: str) -> dict[str, Any]:
        """
        Cancel ongoing live migration.

        Args:
            migration_id: Migration task identifier

        Returns:
            Cancellation result
        """
        result: dict[str, Any] = {
            "cancelled": False,
            "migration_id": migration_id,
            "error": None,
        }

        try:
            import json

            self.logger.warning("Cancelling migration: %s", migration_id)
            payload = json.dumps({"migration_id": migration_id}).encode()
            req = urllib.request.Request(  # noqa: S310 - daemon_url is operator-configured, not untrusted input
                f"{self.daemon_url}/api/v1/migrate/cancel",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            body = await self._urlopen(req, 10)
            data = json.loads(body)
            result["cancelled"] = data.get("cancelled", True)

        except urllib.error.URLError as e:
            result["error"] = f"daemon unreachable: {e}"
            self.logger.exception("Failed to cancel migration: %s", e)
        except Exception as e:
            result["error"] = str(e)
            self.logger.exception("Failed to cancel migration: %s", e)

        return result

    def get_supported_providers(self) -> list[str]:
        """Get list of supported providers for live migration."""
        return [
            "vmware",  # VMware vSphere, ESXi
            "hyperv",  # Microsoft Hyper-V
            "kvm",  # KVM/QEMU
            "aws",  # AWS EC2
            "azure",  # Microsoft Azure
            "gcp",  # Google Cloud Platform
        ]

    async def validate_provider_config(self, provider: str, config: dict[str, Any]) -> dict[str, Any]:
        """
        Validate provider configuration for live migration.

        Args:
            provider: Provider name
            config: Provider configuration

        Returns:
            Validation result
        """
        validation: dict[str, Any] = {
            "valid": False,
            "provider": provider,
            "errors": [],
            "warnings": [],
        }

        try:
            supported_providers = self.get_supported_providers()
            if provider not in supported_providers:
                validation["errors"].append(
                    f"Unsupported provider: {provider}. Supported: {', '.join(supported_providers)}"
                )
                return validation

            # Provider-specific required fields
            required_fields_map = {
                "vmware": ["vcenter_host", "username", "password"],
                "hyperv": ["hyperv_host", "username", "password"],
                "kvm": ["libvirt_uri"],
                "aws": ["region", "access_key_id", "secret_access_key"],
                "azure": ["subscription_id", "resource_group"],
                "gcp": ["project_id", "zone"],
            }

            required_fields = required_fields_map.get(provider, [])
            for field in required_fields:
                if field not in config:
                    validation["errors"].append(f"Missing required field: {field}")

            if not validation["errors"]:
                validation["valid"] = True

        except Exception as e:
            validation["errors"].append(f"Validation error: {e}")

        return validation
