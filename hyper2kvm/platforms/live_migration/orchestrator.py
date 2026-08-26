# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Live Migration Orchestrator.

Coordinates live migration workflow including feasibility analysis, HyperSDK
integration, and hybrid migration with offline fixes.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .analyzer import LiveMigrationAnalyzer
from .hybrid_manager import HybridMigrationManager
from .hypersdk_integration import HyperSDKIntegration


class LiveMigrationOrchestrator:
    """Orchestrates complete live migration workflow."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize Live Migration Orchestrator.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.analyzer = LiveMigrationAnalyzer(logger)
        self.hypersdk = HyperSDKIntegration(logger)
        self.hybrid_mgr = HybridMigrationManager(logger)

    async def migrate(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        vm_info: dict[str, Any] | None = None,
        provider: str = "vmware",
        mode: str = "auto",  # auto, live, offline, hybrid
        offline_fixes: list[str] | None = None,
        maintenance_window: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate VM migration with automatic mode selection.

        Args:
            vm_id: VM identifier
            source_host: Source host
            target_host: Target host
            vm_info: Optional VM information (will be queried if not provided)
            provider: Provider type (vmware, hyperv, kvm, aws, azure, gcp)
            mode: Migration mode:
                - auto: Automatically choose best mode based on analysis
                - live: Force live migration
                - offline: Force offline migration
                - hybrid: Live migration + scheduled offline fixes
            offline_fixes: List of offline fixes to apply (for hybrid mode)
            maintenance_window: Maintenance window for offline fixes
            options: Additional migration options
            progress_callback: Progress callback function

        Returns:
            Migration result dictionary
        """
        options = options or {}
        result: dict[str, Any] = {
            "success": False,
            "vm_id": vm_id,
            "mode_selected": None,
            "mode_recommended": None,
            "analysis": {},
            "migration": {},
            "error": None,
        }

        try:
            self.logger.info(
                f"Starting migration orchestration: {vm_id} ({source_host} → {target_host}, mode: {mode})"
            )

            # Step 1: Analyze VM for live migration feasibility
            if not vm_info:
                vm_info = await self._get_vm_info(vm_id, source_host, provider)

            analysis = self.analyzer.can_migrate_live(vm_info)
            result["analysis"] = analysis

            # Step 2: Select migration mode
            if mode == "auto":
                if analysis["recommended"]:
                    selected_mode = "live"
                    result["mode_recommended"] = "live"
                else:
                    selected_mode = "offline"
                    result["mode_recommended"] = "offline"

                if offline_fixes:
                    # If offline fixes requested, use hybrid mode
                    selected_mode = "hybrid"
                    result["mode_recommended"] = "hybrid"
            else:
                selected_mode = mode
                result["mode_recommended"] = analysis.get("recommended", "unknown")

            result["mode_selected"] = selected_mode

            self.logger.info(
                f"Migration mode selected: {selected_mode} (recommended: {result['mode_recommended']})"
            )

            # Step 3: Execute migration based on selected mode
            if selected_mode == "live":
                migration_result = await self._execute_live_migration(
                    vm_id,
                    source_host,
                    target_host,
                    provider,
                    options,
                    progress_callback,
                )
            elif selected_mode == "hybrid":
                migration_result = await self._execute_hybrid_migration(
                    vm_id,
                    source_host,
                    target_host,
                    provider,
                    offline_fixes,
                    maintenance_window,
                    progress_callback,
                )
            elif selected_mode == "offline":
                migration_result = await self._execute_offline_migration(
                    vm_id,
                    source_host,
                    target_host,
                    provider,
                    offline_fixes,
                    progress_callback,
                )
            else:
                raise ValueError(f"Invalid migration mode: {selected_mode}")

            result["migration"] = migration_result
            result["success"] = migration_result.get("success", False)

            if result["success"]:
                self.logger.info(f"Migration completed successfully: {vm_id} (mode: {selected_mode})")
            else:
                self.logger.error(f"Migration failed: {vm_id} - {migration_result.get('error')}")

        except Exception as e:
            result["error"] = str(e)
            self.logger.exception(f"Migration orchestration failed: {e}")

        return result

    async def _execute_live_migration(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        provider: str,
        options: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Execute live migration only."""
        self.logger.info(f"Executing live migration: {vm_id}")

        return await self.hypersdk.migrate_live(
            vm_id=vm_id,
            source_host=source_host,
            target_host=target_host,
            provider=provider,
            options=options,
            progress_callback=progress_callback,
        )

    async def _execute_hybrid_migration(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        provider: str,
        offline_fixes: list[str] | None,
        maintenance_window: dict[str, Any] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Execute hybrid migration (live + offline fixes)."""
        self.logger.info(f"Executing hybrid migration: {vm_id}")

        return await self.hybrid_mgr.migrate_hybrid(
            vm_id=vm_id,
            source_host=source_host,
            target_host=target_host,
            provider=provider,
            maintenance_window=maintenance_window,
            offline_fixes=offline_fixes,
            progress_callback=progress_callback,
        )

    async def _execute_offline_migration(
        self,
        vm_id: str,
        source_host: str,
        target_host: str,
        provider: str,
        offline_fixes: list[str] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Execute offline migration with fixes."""
        self.logger.info(f"Executing offline migration: {vm_id}")

        # Placeholder for offline migration
        # This would use existing hyper2kvm offline migration
        result = {
            "success": False,
            "mode": "offline",
            "error": "Offline migration integration pending",
        }

        self.logger.warning("Offline migration selected - using traditional hyper2kvm workflow")

        return result

    async def _get_vm_info(self, vm_id: str, host: str, provider: str) -> dict[str, Any]:
        """
        Query VM information from provider.

        Args:
            vm_id: VM identifier
            host: Host where VM is running
            provider: Provider type

        Returns:
            VM information dictionary
        """
        # Placeholder for actual VM info query via HyperSDK
        return {
            "name": vm_id,
            "power_state": "on",
            "memory_mb": 8192,
            "cpu_count": 4,
            "disk_count": 1,
            "disk_size_gb": 100,
            "disk_provisioning": "thin",
            "os_type": "linux",
            "guest_tools_running": True,
            "snapshot_count": 0,
            "connected_devices": [],
        }

    async def plan_batch_migration(
        self,
        vms: list[dict[str, Any]],
        provider: str = "vmware",
    ) -> dict[str, Any]:
        """
        Plan batch migration for multiple VMs.

        Args:
            vms: List of VM information dictionaries
            provider: Provider type

        Returns:
            Batch migration plan
        """
        self.logger.info(f"Planning batch migration for {len(vms)} VMs")

        # Analyze all VMs
        batch_analysis = self.analyzer.analyze_batch(vms)

        # Create migration plan
        plan = {
            "total_vms": batch_analysis["total_vms"],
            "live_migration_candidates": [],
            "offline_migration_required": [],
            "hybrid_migration_candidates": [],
            "estimated_total_time_hours": 0.0,
            "estimated_total_downtime_minutes": 0.0,
        }

        for vm_analysis in batch_analysis["vms"]:
            vm_name = vm_analysis["name"]
            analysis = vm_analysis["analysis"]

            if analysis["recommended"]:
                plan["live_migration_candidates"].append(
                    {
                        "name": vm_name,
                        "estimated_downtime_seconds": analysis["estimated_downtime_seconds"],
                    }
                )
            else:
                plan["offline_migration_required"].append(
                    {"name": vm_name, "reason": analysis.get("reasons", [])}
                )

        # Calculate totals
        plan["estimated_total_downtime_minutes"] = sum(
            vm["estimated_downtime_seconds"] / 60 for vm in plan["live_migration_candidates"]
        )

        self.logger.info(
            f"Batch migration plan: "
            f"{len(plan['live_migration_candidates'])} live, "
            f"{len(plan['offline_migration_required'])} offline"
        )

        return plan

    def generate_migration_report(
        self,
        migration_result: dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Generate migration report.

        Args:
            migration_result: Migration result from migrate()
            output_path: Path to save report
        """
        try:
            report = self._build_report_content(migration_result)
            output_path.write_text(report, encoding="utf-8")
            self.logger.info(f"Migration report saved: {output_path}")
        except Exception as e:
            self.logger.exception(f"Failed to generate migration report: {e}")

    def _build_report_content(self, migration_result: dict[str, Any]) -> str:
        """Build migration report content."""
        timestamp = datetime.now().isoformat()

        report = f"""# Live Migration Report
Generated: {timestamp}

## Summary
- **VM**: {migration_result.get("vm_id")}
- **Status**: {"✅ SUCCESS" if migration_result.get("success") else "❌ FAILED"}
- **Mode Selected**: {migration_result.get("mode_selected")}
- **Mode Recommended**: {migration_result.get("mode_recommended")}

## Feasibility Analysis
"""

        analysis = migration_result.get("analysis", {})
        if analysis:
            report += f"""
- **Feasible**: {analysis.get("feasible")}
- **Recommended**: {analysis.get("recommended")}
- **Confidence**: {analysis.get("confidence", 0) * 100:.1f}%
- **Estimated Downtime**: {analysis.get("estimated_downtime_seconds", 0):.1f}s
- **Category**: {analysis.get("downtime_category")}

### Reasons
{chr(10).join(["- " + r for r in analysis.get("reasons", [])])}

### Warnings
{chr(10).join(["- " + w for w in analysis.get("warnings", [])])}

### Requirements
{chr(10).join(["- " + r for r in analysis.get("requirements", [])])}
"""

        # Migration details
        migration = migration_result.get("migration", {})
        if migration:
            report += f"""

## Migration Details
- **Success**: {migration.get("success")}
"""
            if migration.get("actual_downtime_ms"):
                report += f"- **Actual Downtime**: {migration.get('actual_downtime_ms')}ms\n"
            if migration.get("total_time_seconds"):
                report += f"- **Total Time**: {migration.get('total_time_seconds'):.1f}s\n"
            if migration.get("error"):
                report += f"- **Error**: {migration.get('error')}\n"

        # Error details
        if migration_result.get("error"):
            report += f"""

## Error Details
```
{migration_result.get("error")}
```
"""

        report += """

---
Generated by hyper2kvm Live Migration Orchestrator
"""

        return report
