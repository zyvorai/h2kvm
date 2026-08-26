# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/async_client/operations.py
"""
High-level async VMware operations.

Provides convenient async operations for common tasks.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from .client import AsyncVMwareClient

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MigrationProgress:
    """Progress information for a migration."""

    vm_name: str
    progress: float  # 0.0 to 1.0
    stage: str
    throughput_mbps: float
    elapsed_seconds: float
    eta_seconds: float | None = None


class AsyncVMwareOperations:
    """
    High-level async VMware operations.

    Provides convenient methods for common async tasks with
    progress tracking and error handling.

    Example:
        >>> ops = AsyncVMwareOperations(client)
        >>> await ops.batch_export(
        ...     ["vm1", "vm2", "vm3"],
        ...     Path("/output"),
        ...     on_progress=lambda p: print(p.vm_name, p.progress),
        ... )
    """

    def __init__(self, client: AsyncVMwareClient):
        """
        Initialize operations.

        Args:
            client: Async VMware client
        """
        self.client = client

    @staticmethod
    def _make_progress_callback(
        vm_name: str, on_progress: Callable[[MigrationProgress], None] | None
    ) -> Callable[[float, str, float], None]:
        """Wrap a raw (progress, stage, throughput) callback into a MigrationProgress callback."""
        start_time = time.time()

        def callback(progress: float, stage: str, throughput: float) -> None:
            if not on_progress:
                return

            elapsed = time.time() - start_time

            eta = None
            if 0.0 < progress < 1.0:
                eta = (elapsed / progress) * (1.0 - progress)

            on_progress(
                MigrationProgress(
                    vm_name=vm_name,
                    progress=progress,
                    stage=stage,
                    throughput_mbps=throughput,
                    elapsed_seconds=elapsed,
                    eta_seconds=eta,
                )
            )

        return callback

    async def batch_export(
        self,
        vm_names: list[str],
        output_dir: Path,
        on_progress: Callable[[MigrationProgress], None] | None = None,
        on_complete: Callable[[str, bool, str | None], None] | None = None,
    ) -> dict[str, Any]:
        """
        Export multiple VMs in parallel with progress tracking.

        Args:
            vm_names: List of VM names to export
            output_dir: Output directory
            on_progress: Optional progress callback
            on_complete: Optional completion callback(vm_name, success, error)

        Returns:
            Summary of batch export

        Example:
            >>> def progress_cb(p: MigrationProgress):
            ...     print(f"{p.vm_name}: {p.progress * 100:.1f}% - {p.stage}")
            >>>
            >>> results = await ops.batch_export(
            ...     ["vm1", "vm2", "vm3"],
            ...     Path("/output"),
            ...     on_progress=progress_cb,
            ... )
        """
        # Run the blocking pathlib call off the event loop (this codebase uses
        # asyncio, not trio/anyio, so asyncio.to_thread is the async-safe
        # equivalent here).
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

        logger.info("Starting batch export of %d VMs", len(vm_names))

        # Export VMs in parallel, each wired to its own per-VM progress callback.
        # (client.export_vms_parallel() only accepts a single shared callback with
        # no VM identity, so we call export_vm_async() directly per VM instead --
        # it still honors the client's concurrency limits internally.)
        tasks = [
            self.client.export_vm_async(
                vm_name, output_dir, self._make_progress_callback(vm_name, on_progress)
            )
            for vm_name in vm_names
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successes = []
        failures = []

        for idx, result in enumerate(results):
            vm_name = vm_names[idx]

            if isinstance(result, dict) and result.get("status") == "success":
                successes.append(vm_name)
                if on_complete:
                    on_complete(vm_name, True, None)
            else:
                error = str(result) if isinstance(result, Exception) else "Unknown error"
                failures.append((vm_name, error))
                if on_complete:
                    on_complete(vm_name, False, error)

        summary = {
            "total": len(vm_names),
            "succeeded": len(successes),
            "failed": len(failures),
            "success_rate": len(successes) / len(vm_names) if vm_names else 0,
            "successes": successes,
            "failures": failures,
        }

        logger.info("Batch export complete: %d/%d succeeded", summary["succeeded"], summary["total"])

        return summary

    async def export_with_retry(
        self,
        vm_name: str,
        output_dir: Path,
        max_retries: int = 3,
        on_progress: Callable[[MigrationProgress], None] | None = None,
    ) -> dict[str, Any]:
        """
        Export VM with automatic retry on failure.

        Args:
            vm_name: VM name
            output_dir: Output directory
            max_retries: Maximum retry attempts (default: 3)
            on_progress: Optional progress callback

        Returns:
            Export result

        Example:
            >>> result = await ops.export_with_retry(
            ...     "web-server-01",
            ...     Path("/output"),
            ...     max_retries=3,
            ... )
        """
        for attempt in range(max_retries):
            try:
                logger.info("Export attempt %d/%d for %s", attempt + 1, max_retries, vm_name)

                result = await self.client.export_vm_async(
                    vm_name, output_dir, self._make_progress_callback(vm_name, on_progress)
                )

                logger.info("Successfully exported %s on attempt %d", vm_name, attempt + 1)
                return result

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: must catch any export failure to drive the retry loop --
                # the final attempt re-raises via `raise` below.
                logger.warning("Export attempt %d failed for %s: %s", attempt + 1, vm_name, e)

                if attempt + 1 < max_retries:
                    # Exponential backoff
                    wait_time = 2**attempt
                    logger.info("Retrying in %d seconds...", wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    logger.exception("All %d attempts failed for %s", max_retries, vm_name)
                    raise
        return None

    async def get_vms_by_pattern(
        self,
        pattern: str,
        use_regex: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get VMs matching a name pattern.

        Args:
            pattern: Pattern to match (glob or regex)
            use_regex: Use regex instead of glob (default: False)

        Returns:
            List of matching VMs

        Example:
            >>> vms = await ops.get_vms_by_pattern("web-server-*")
            >>> vms = await ops.get_vms_by_pattern(r"^db-\\d+$", use_regex=True)
        """
        all_vms = await self.client.list_vms()

        if use_regex:
            regex = re.compile(pattern)
            matching = [vm for vm in all_vms if regex.match(vm["name"])]
        else:
            matching = [vm for vm in all_vms if fnmatch.fnmatch(vm["name"], pattern)]

        logger.info("Found %d VMs matching pattern: %s", len(matching), pattern)
        return matching


# Convenience function
async def migrate_vms_async(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    host: str,
    username: str,
    password: str,
    vm_names: list[str],
    output_dir: Path,
    datacenter: str | None = None,
    max_concurrent: int = 5,
    on_progress: Callable[[MigrationProgress], None] | None = None,
    on_complete: Callable[[str, bool, str | None], None] | None = None,
) -> dict[str, Any]:
    # reason: one-shot convenience wrapper bundling connection credentials, VM
    # selection, and callback options for a full async migration run.
    """
    Convenience function to migrate multiple VMs asynchronously.

    Args:
        host: vCenter host
        username: vCenter username
        password: vCenter password
        vm_names: List of VM names
        output_dir: Output directory
        datacenter: Datacenter name
        max_concurrent: Max parallel migrations (default: 5)
        on_progress: Progress callback
        on_complete: Completion callback

    Returns:
        Migration summary

    Example:
        >>> results = await migrate_vms_async(
        ...     "vcenter.example.com",
        ...     "admin",
        ...     "password",
        ...     ["vm1", "vm2", "vm3"],
        ...     Path("/output"),
        ...     max_concurrent=3,
        ... )
    """
    async with AsyncVMwareClient(
        host=host,
        username=username,
        password=password,
        datacenter=datacenter,
        max_concurrent_vms=max_concurrent,
    ) as client:
        ops = AsyncVMwareOperations(client)
        return await ops.batch_export(
            vm_names,
            output_dir,
            on_progress=on_progress,
            on_complete=on_complete,
        )
