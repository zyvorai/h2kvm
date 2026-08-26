# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Hybrid Migration Manager.

Combines live migration with scheduled offline fixes to minimize downtime while
ensuring proper VM configuration.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

from .hypersdk_integration import HyperSDKIntegration


class HybridMigrationManager:
    """Manages hybrid migration workflow (live + offline fixes)."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize Hybrid Migration Manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.hypersdk = HyperSDKIntegration(logger)

    async def migrate_hybrid(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        provider: str = "vmware",
        maintenance_window: dict[str, Any] | None = None,
        offline_fixes: list[str] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Perform hybrid migration (live migration + offline fixes).

        Args:
            vm_id: VM identifier
            source_host: Source host
            target_host: Target host
            provider: Provider type
            maintenance_window: Optional maintenance window:
                - start_time: datetime when maintenance can start
                - duration_minutes: Maximum maintenance duration
            offline_fixes: List of offline fixes to apply:
                - "bootloader" - Regenerate bootloader
                - "initramfs" - Rebuild initramfs
                - "drivers" - Inject VirtIO drivers
                - "network" - Fix network configuration
                - "fstab" - Stabilize fstab
            progress_callback: Progress callback function

        Returns:
            Migration result dictionary
        """
        offline_fixes = offline_fixes or []
        result: dict[str, Any] = {
            "success": False,
            "phase_completed": None,  # "live", "offline_fixes", "complete"
            "live_migration": {},
            "offline_fixes": {},
            "total_downtime_seconds": 0.0,
            "error": None,
        }

        try:
            self.logger.info(
                f"Starting hybrid migration: {vm_id} "
                f"(live + offline fixes: {', '.join(offline_fixes) if offline_fixes else 'none'})"
            )

            # Phase 1: Live migration
            self.logger.info("Phase 1: Live migration")
            if progress_callback:
                progress_callback({"phase": "live_migration", "progress": 0})

            live_result = await self.hypersdk.migrate_live(
                vm_id=vm_id,
                source_host=source_host,
                target_host=target_host,
                provider=provider,
                progress_callback=progress_callback,
            )

            result["live_migration"] = live_result
            result["phase_completed"] = "live"

            if not live_result["success"]:
                result["error"] = f"Live migration failed: {live_result.get('error')}"
                self.logger.error(result["error"])
                return result

            self.logger.info(f"Live migration completed - Downtime: {live_result['actual_downtime_ms']}ms")

            # Phase 2: Offline fixes (if requested and maintenance window allows)
            if offline_fixes:
                if maintenance_window:
                    # Schedule fixes for maintenance window
                    await self._schedule_offline_fixes(
                        vm_id, offline_fixes, maintenance_window, progress_callback
                    )
                else:
                    # Apply fixes immediately
                    self.logger.info("Phase 2: Applying offline fixes")
                    fixes_result = await self._apply_offline_fixes(vm_id, offline_fixes, progress_callback)
                    result["offline_fixes"] = fixes_result
                    result["phase_completed"] = "offline_fixes"

                    # Calculate total downtime
                    offline_downtime = fixes_result.get("total_time_seconds", 0)
                    result["total_downtime_seconds"] = (
                        live_result["actual_downtime_ms"] / 1000.0 + offline_downtime
                    )
            else:
                # No offline fixes requested
                result["total_downtime_seconds"] = live_result["actual_downtime_ms"] / 1000.0

            result["success"] = True
            result["phase_completed"] = "complete"

            self.logger.info(
                f"Hybrid migration completed - Total downtime: {result['total_downtime_seconds']:.2f}s"
            )

        except Exception as e:
            result["error"] = str(e)
            self.logger.exception(f"Hybrid migration failed: {e}")

        return result

    async def _schedule_offline_fixes(
        self,
        vm_id: str,
        offline_fixes: list[str],
        maintenance_window: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """
        Schedule offline fixes for maintenance window.

        Args:
            vm_id: VM identifier
            offline_fixes: List of fixes to apply
            maintenance_window: Maintenance window definition
            progress_callback: Progress callback
        """
        start_time = maintenance_window.get("start_time")
        duration_minutes = maintenance_window.get("duration_minutes", 60)

        if not start_time:
            raise ValueError("Maintenance window start_time not specified")

        # Convert to datetime if needed
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)

        self.logger.info(
            f"Offline fixes scheduled for maintenance window: {start_time} "
            f"(duration: {duration_minutes} minutes)"
        )

        # Calculate time until maintenance window
        now = datetime.now(start_time.tzinfo)
        wait_seconds = (start_time - now).total_seconds()

        if wait_seconds > 0:
            self.logger.info(f"Waiting {wait_seconds:.0f}s until maintenance window")
            if progress_callback:
                progress_callback(
                    {
                        "phase": "waiting_for_maintenance",
                        "wait_seconds": wait_seconds,
                        "start_time": start_time.isoformat(),
                    }
                )
            await asyncio.sleep(wait_seconds)

        # Apply fixes during maintenance window
        self.logger.info("Maintenance window started - applying offline fixes")
        await self._apply_offline_fixes(vm_id, offline_fixes, progress_callback)

    async def _apply_offline_fixes(
        self,
        vm_id: str,
        offline_fixes: list[str],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Apply offline fixes to migrated VM.

        Args:
            vm_id: VM identifier
            offline_fixes: List of fixes to apply
            progress_callback: Progress callback

        Returns:
            Fixes result dictionary
        """
        result = {
            "success": False,
            "fixes_applied": [],
            "fixes_failed": [],
            "total_time_seconds": 0.0,
            "error": None,
        }

        try:
            import time

            start_time = time.time()

            # Power off VM for offline fixes
            self.logger.info(f"Powering off VM {vm_id} for offline fixes")
            await self._power_off_vm(vm_id)

            # Apply each fix
            for idx, fix in enumerate(offline_fixes):
                if progress_callback:
                    progress_callback(
                        {
                            "phase": "offline_fixes",
                            "current_fix": fix,
                            "progress": int((idx / len(offline_fixes)) * 100),
                        }
                    )

                self.logger.info(f"Applying fix: {fix}")

                try:
                    await self._apply_single_fix(vm_id, fix)
                    result["fixes_applied"].append(fix)
                    self.logger.info(f"Fix applied successfully: {fix}")
                except Exception as e:
                    result["fixes_failed"].append({"fix": fix, "error": str(e)})
                    self.logger.exception(f"Fix failed: {fix} - {e}")

            # Power on VM
            self.logger.info(f"Powering on VM {vm_id} after offline fixes")
            await self._power_on_vm(vm_id)

            result["total_time_seconds"] = time.time() - start_time
            result["success"] = len(result["fixes_failed"]) == 0

        except Exception as e:
            result["error"] = str(e)
            self.logger.exception(f"Offline fixes failed: {e}")

        return result

    async def _apply_single_fix(self, vm_id: str, fix: str) -> None:
        """
        Apply single offline fix.

        Args:
            vm_id: VM identifier
            fix: Fix type to apply

        Raises:
            RuntimeError: If fix fails
        """
        # Map fix types to actual fix functions
        fix_handlers = {
            "bootloader": self._fix_bootloader,
            "initramfs": self._fix_initramfs,
            "drivers": self._fix_drivers,
            "network": self._fix_network,
            "fstab": self._fix_fstab,
        }

        handler = fix_handlers.get(fix)
        if not handler:
            raise ValueError(f"Unknown fix type: {fix}")

        await handler(vm_id)

    async def _fix_bootloader(self, vm_id: str) -> None:
        """Fix bootloader configuration."""
        self.logger.debug(f"Regenerating bootloader for {vm_id}")
        # Placeholder for actual bootloader fix
        # This would use VMCraft to regenerate GRUB
        await asyncio.sleep(0.1)

    async def _fix_initramfs(self, vm_id: str) -> None:
        """Rebuild initramfs with VirtIO drivers."""
        self.logger.debug(f"Rebuilding initramfs for {vm_id}")
        # Placeholder for actual initramfs rebuild
        # This would use VMCraft to rebuild initramfs
        await asyncio.sleep(0.1)

    async def _fix_drivers(self, vm_id: str) -> None:
        """Inject VirtIO drivers."""
        self.logger.debug(f"Injecting VirtIO drivers for {vm_id}")
        # Placeholder for driver injection
        # This would use VMCraft for Windows or Linux driver injection
        await asyncio.sleep(0.1)

    async def _fix_network(self, vm_id: str) -> None:
        """Fix network configuration."""
        self.logger.debug(f"Fixing network configuration for {vm_id}")
        # Placeholder for network fix
        # This would use VMCraft to fix network config
        await asyncio.sleep(0.1)

    async def _fix_fstab(self, vm_id: str) -> None:
        """Stabilize fstab entries."""
        self.logger.debug(f"Stabilizing fstab for {vm_id}")
        # Placeholder for fstab fix
        # This would use VMCraft to convert to UUID/LABEL
        await asyncio.sleep(0.1)

    async def _power_off_vm(self, vm_id: str) -> None:
        """Power off VM gracefully."""
        self.logger.debug(f"Powering off VM {vm_id}")
        # Placeholder for actual power off via HyperSDK
        await asyncio.sleep(0.1)

    async def _power_on_vm(self, vm_id: str) -> None:
        """Power on VM."""
        self.logger.debug(f"Powering on VM {vm_id}")
        # Placeholder for actual power on via HyperSDK
        await asyncio.sleep(0.1)

    def estimate_hybrid_migration_time(
        self,
        vm_info: dict[str, Any],
        offline_fixes: list[str],
    ) -> dict[str, Any]:
        """
        Estimate total time for hybrid migration.

        Args:
            vm_info: VM information
            offline_fixes: List of offline fixes

        Returns:
            Time estimate dictionary
        """
        estimate = {
            "live_migration_seconds": 0.0,
            "offline_fixes_seconds": 0.0,
            "total_seconds": 0.0,
            "total_downtime_seconds": 0.0,
        }

        # Estimate live migration time (mostly pre-copy, minimal downtime)
        memory_mb = vm_info.get("memory_mb", 0)
        estimate["live_migration_seconds"] = max(10.0, memory_mb / 1000)  # ~1GB/s transfer

        # Estimate offline fixes time
        fix_times = {
            "bootloader": 30.0,
            "initramfs": 45.0,
            "drivers": 20.0,
            "network": 10.0,
            "fstab": 5.0,
        }

        for fix in offline_fixes:
            estimate["offline_fixes_seconds"] += fix_times.get(fix, 10.0)

        # Add overhead for power off/on
        if offline_fixes:
            estimate["offline_fixes_seconds"] += 20.0  # Power cycle overhead

        estimate["total_seconds"] = estimate["live_migration_seconds"] + estimate["offline_fixes_seconds"]

        # Total downtime = live migration downtime + offline fixes time
        estimate["total_downtime_seconds"] = 5.0 + estimate["offline_fixes_seconds"]

        return estimate
