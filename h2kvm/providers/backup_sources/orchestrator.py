# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/backup_sources/orchestrator.py
"""
Backup Restore Orchestrator.

Unified interface for restoring VMs from multiple backup solutions.
Auto-detects backup format and coordinates restore operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from .base import BackupFormat, BackupSource, BackupVMInfo, RestoreProgress
from .generic import GenericBackupSource
from .proxmox import ProxmoxBackupSource
from .veeam import VeeamBackupSource

logger = logging.getLogger(__name__)


class BackupRestoreOrchestrator:
    """
    Orchestrates VM restore from multiple backup sources.

    Auto-detects backup format and provides unified restore interface.
    """

    def __init__(self, logger_instance: logging.Logger):
        """
        Initialize backup restore orchestrator.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance
        self._sources: dict[str, BackupSource] = {}

    def add_backup_source(
        self, name: str, backup_path: Path | str, format_hint: BackupFormat | None = None, **kwargs: Any
    ) -> bool:
        """
        Add backup source.

        Auto-detects format if not specified.

        Args:
            name: Friendly name for this backup source
            backup_path: Path to backup repository/file
            format_hint: Optional format hint (auto-detected if None)
            **kwargs: Format-specific arguments (e.g., datastore for Proxmox)

        Returns:
            True if source added successfully

        Example:
            # Add Veeam backup
            orchestrator.add_backup_source(
                "prod-veeam",
                "/mnt/backups/veeam",
                BackupFormat.VEEAM
            )

            # Add Proxmox Backup Server
            orchestrator.add_backup_source(
                "pbs-datastore",
                "/mnt/pbs/backup",
                BackupFormat.PROXMOX_PBS,
                datastore="backup"
            )

            # Add generic tar backup (auto-detect)
            orchestrator.add_backup_source(
                "manual-backup",
                "/backups/vm-archive.tar.gz"
            )
        """
        try:
            backup_path = Path(backup_path)

            # Auto-detect format if not provided
            if format_hint is None:
                format_hint = self._detect_format(backup_path)

            # Create appropriate backup source
            if format_hint == BackupFormat.VEEAM:
                source = VeeamBackupSource(self.logger, backup_path)
            elif format_hint == BackupFormat.PROXMOX_PBS:
                source = ProxmoxBackupSource(
                    self.logger,
                    backup_path,
                    datastore=kwargs.get("datastore", "backup"),
                    repository=kwargs.get("repository"),
                )
            elif format_hint == BackupFormat.GENERIC:
                source = GenericBackupSource(self.logger, backup_path)
            else:
                self.logger.error(f"Unsupported backup format: {format_hint}")
                return False

            self._sources[name] = source
            self.logger.info(f"Added {format_hint.value} backup source: {name}")
            return True

        # best-effort source setup; caller checks the returned bool instead of a raised exception
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.exception(f"Failed to add backup source {name}: {e}")
            return False

    def _detect_format(self, backup_path: Path) -> BackupFormat:
        """
        Auto-detect backup format from path.

        Args:
            backup_path: Path to backup

        Returns:
            Detected BackupFormat
        """
        # Check for Veeam files
        if backup_path.is_dir():
            if list(backup_path.rglob("*.vbk")):
                return BackupFormat.VEEAM

            # Check for PBS structure
            if (backup_path / "vm").exists():
                return BackupFormat.PROXMOX_PBS

        # Check file extensions for generic backups
        if backup_path.suffix in [".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz", ".zip"]:
            return BackupFormat.GENERIC

        # Default to generic
        return BackupFormat.GENERIC

    def list_all_vms(self, filters: dict[str, Any] | None = None) -> dict[str, list[BackupVMInfo]]:
        """
        List VMs across all backup sources.

        Args:
            filters: Optional filters

        Returns:
            Dict mapping source name to list of VMs

        Example:
            all_vms = orchestrator.list_all_vms()
            for source_name, vms in all_vms.items():
                print(f"{source_name}: {len(vms)} VMs")
                for vm in vms:
                    print(f"  - {vm.vm_name} ({vm.backup_date})")
        """
        results: dict[str, list[BackupVMInfo]] = {}

        for name, source in self._sources.items():
            try:
                vms = source.list_vms(filters)
                results[name] = vms
                self.logger.info(f"Found {len(vms)} VMs in {name}")
            # one source's listing failure must not abort listing the rest
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.exception(f"Failed to list VMs from {name}: {e}")
                results[name] = []

        return results

    def find_vm(self, vm_identifier: str) -> tuple[str, BackupVMInfo] | None:
        """
        Find VM across all backup sources.

        Args:
            vm_identifier: VM name or UUID

        Returns:
            Tuple of (source_name, BackupVMInfo) or None if not found

        Example:
            result = orchestrator.find_vm("prod-sql-01")
            if result:
                source_name, vm_info = result
                print(f"Found in {source_name}: {vm_info.backup_date}")
        """
        for name, source in self._sources.items():
            try:
                vm_info = source.get_vm_info(vm_identifier)
                return (name, vm_info)
            except ValueError:
                continue  # Not found in this source
            # one source's search error must not abort searching the rest
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.debug(f"Error searching {name} for {vm_identifier}: {e}")
                continue

        return None

    def restore_vm(
        self,
        source_name: str,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Restore VM from specified backup source.

        Args:
            source_name: Name of backup source
            vm_info: BackupVMInfo to restore
            output_dir: Output directory
            progress_callback: Progress callback
            verify_integrity: Verify backup integrity

        Returns:
            Restore result dict

        Example:
            result = orchestrator.restore_vm(
                "prod-veeam",
                vm_info,
                Path("/var/lib/libvirt/images"),
                progress_callback=lambda p: print(f"Progress: {p.progress_pct}%")
            )

            if result["success"]:
                print(f"Restored {result['vm_name']}")
                for disk in result["disks"]:
                    print(f"  Disk: {disk['path']}")
        """
        if source_name not in self._sources:
            raise ValueError(
                f"Backup source '{source_name}' not found. "
                f"Available sources: {', '.join(self._sources.keys()) or 'none registered'}. "
                f"Register a source first with add_source()."
            )

        source = self._sources[source_name]

        self.logger.info(f"Restoring {vm_info.vm_name} from {source_name}")

        return source.restore_vm(
            vm_info, output_dir, progress_callback=progress_callback, verify_integrity=verify_integrity
        )

    def verify_all_backups(self) -> dict[str, Any]:
        """
        Verify integrity of all backups.

        Returns:
            Verification summary dict:
                {
                    "total_sources": int,
                    "total_vms": int,
                    "valid_vms": int,
                    "invalid_vms": int,
                    "by_source": {source_name: {vm_name: verification_result}}
                }

        Example:
            summary = orchestrator.verify_all_backups()
            print(f"Verified {summary['total_vms']} VMs")
            print(f"Valid: {summary['valid_vms']}, Invalid: {summary['invalid_vms']}")
        """
        summary = {
            "total_sources": len(self._sources),
            "total_vms": 0,
            "valid_vms": 0,
            "invalid_vms": 0,
            "by_source": {},
        }

        for source_name, source in self._sources.items():
            source_results = {}

            try:
                vms = source.list_vms()
                summary["total_vms"] += len(vms)

                for vm in vms:
                    verification = source.verify_backup_integrity(vm)
                    source_results[vm.vm_name] = verification

                    if verification["valid"]:
                        summary["valid_vms"] += 1
                    else:
                        summary["invalid_vms"] += 1

            # one source's verification failure must not abort verifying the rest
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.exception(f"Failed to verify backups in {source_name}: {e}")

            summary["by_source"][source_name] = source_results

        return summary

    def generate_dr_test_plan(
        self, vms: list[tuple[str, BackupVMInfo]], test_env_capacity_gb: int = 1000
    ) -> dict[str, Any]:
        """
        Generate DR (Disaster Recovery) test plan.

        Analyzes which VMs can be restored within capacity constraints.

        Args:
            vms: List of (source_name, BackupVMInfo) tuples to test
            test_env_capacity_gb: Available storage capacity for testing

        Returns:
            DR test plan dict:
                {
                    "total_vms": int,
                    "vms_in_plan": int,
                    "total_size_gb": float,
                    "estimated_time_hours": float,
                    "restore_order": list[tuple[source, vm]],
                    "warnings": list[str]
                }

        Example:
            # Find critical VMs
            critical_vms = [
                orchestrator.find_vm("db-prod-01"),
                orchestrator.find_vm("web-prod-01"),
                orchestrator.find_vm("app-prod-01")
            ]

            # Generate test plan
            plan = orchestrator.generate_dr_test_plan(
                critical_vms,
                test_env_capacity_gb=500
            )

            print(f"Can test {plan['vms_in_plan']}/{plan['total_vms']} VMs")
            print(f"Total size: {plan['total_size_gb']} GB")
            print(f"Estimated time: {plan['estimated_time_hours']} hours")
        """
        # Sort VMs by size (smallest first)
        sorted_vms = sorted(vms, key=lambda x: x[1].backup_size_gb if x else 0)

        plan = {
            "total_vms": len(vms),
            "vms_in_plan": 0,
            "total_size_gb": 0.0,
            "estimated_time_hours": 0.0,
            "restore_order": [],
            "warnings": [],
        }

        used_capacity = 0.0

        for source_name, vm_info in sorted_vms:
            if vm_info is None:
                continue

            # Check if VM fits in remaining capacity
            if used_capacity + vm_info.backup_size_gb <= test_env_capacity_gb:
                plan["vms_in_plan"] += 1
                plan["total_size_gb"] += vm_info.backup_size_gb
                plan["restore_order"].append((source_name, vm_info))
                used_capacity += vm_info.backup_size_gb

                # Estimate restore time (assume 50 MB/s)
                restore_time_hours = (vm_info.backup_size_gb * 1024) / (50 * 3600)
                plan["estimated_time_hours"] += restore_time_hours
            else:
                plan["warnings"].append(
                    f"VM {vm_info.vm_name} ({vm_info.backup_size_gb} GB) exceeds remaining capacity"
                )

        return plan

    def get_source_list(self) -> list[tuple[str, BackupFormat]]:
        """
        Get list of configured backup sources.

        Returns:
            List of (source_name, format) tuples
        """
        return [(name, source.get_format()) for name, source in self._sources.items()]
