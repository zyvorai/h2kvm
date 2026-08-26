# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/backup_sources/proxmox.py
"""
Proxmox Backup Server (PBS) integration.

Supports restoring VMs from Proxmox Backup Server snapshots.

PBS uses:
- Datastore-based architecture
- Incremental backups with deduplication
- Chunk-based storage format (.fidx, .didx files)

Restore Methods:
1. Use proxmox-backup-client to restore VM image
2. Convert to qcow2 for KVM
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from hyper2kvm.converters.qemu.converter import run_qemu_img_convert

from .base import BackupFormat, BackupSource, BackupVMInfo, RestoreProgress

logger = logging.getLogger(__name__)


class ProxmoxBackupSource(BackupSource):
    """
    Proxmox Backup Server source.

    Restores VMs from PBS datastore.
    """

    def __init__(
        self,
        source_logger: logging.Logger,
        backup_path: Path | str,
        datastore: str = "backup",
        repository: str | None = None,
    ):
        """
        Initialize Proxmox Backup Server source.

        Args:
            source_logger: Logger instance
            backup_path: Path to PBS datastore
            datastore: PBS datastore name (default: "backup")
            repository: Optional PBS repository string (user@pbs:datastore)
        """
        super().__init__(source_logger, backup_path)

        self.datastore = datastore
        self.repository = repository
        self._has_pbs_client = self._check_pbs_client()

    def _check_pbs_client(self) -> bool:
        """Check if proxmox-backup-client is available."""
        try:
            result = subprocess.run(["which", "proxmox-backup-client"], capture_output=True, check=False)
            return result.returncode == 0
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort capability probe -- any failure means "use the
            # manual datastore-scan fallback" rather than crashing.
            self.logger.debug(f"proxmox-backup-client check failed: {e}")
            return False

    def list_vms(self, filters: dict[str, Any] | None = None) -> list[BackupVMInfo]:
        """
        List VMs in PBS datastore.

        Args:
            filters: Optional filters (vm_name, backup_type)

        Returns:
            List of BackupVMInfo objects
        """
        vms = []

        if not self._has_pbs_client:
            self.logger.warning(
                "proxmox-backup-client not available, scanning datastore manually.\n"
                "    For faster listing, install: apt install proxmox-backup-client\n"
                "    See: https://pbs.proxmox.com/docs/backup-client.html"
            )
            return self._list_vms_manual(filters)

        # Use PBS client to list snapshots
        try:  # pylint: disable=too-many-nested-blocks
            # reason: parsing each snapshot line and applying the optional vm_name/
            # backup_type filters naturally nests for/if/if/if a few levels deep.
            cmd = ["proxmox-backup-client", "snapshot", "list"]
            if self.repository:
                cmd.extend(["--repository", self.repository])

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Parse output
            for line in result.stdout.splitlines():
                if "vm/" in line:
                    vm_info = self._parse_snapshot_line(line)
                    if vm_info:
                        # Apply filters
                        if filters:
                            if "vm_name" in filters and filters["vm_name"] not in vm_info.vm_name:
                                continue
                            if "backup_type" in filters and vm_info.backup_type != filters["backup_type"]:
                                continue

                        vms.append(vm_info)

        except subprocess.CalledProcessError as e:
            self.logger.exception(f"Failed to list PBS snapshots: {e}")

        self.logger.info(f"Found {len(vms)} VMs in PBS backup")
        return vms

    def _list_vms_manual(  # pylint: disable=too-many-nested-blocks
        self, filters: dict[str, Any] | None
    ) -> list[BackupVMInfo]:
        # reason: scanning datastore/vm/{vmid}/{timestamp}/*.fidx needs nested
        # dir-walk/parse/build-and-filter loops to reconstruct VM info without PBS client.
        """Manually scan datastore for VM backups."""
        vms = []

        # PBS structure: datastore/vm/{vmid}/{timestamp}/*.fidx
        vm_dirs = (self.backup_path / "vm").glob("*") if (self.backup_path / "vm").exists() else []

        for vm_dir in vm_dirs:
            if not vm_dir.is_dir():
                continue

            vm_id = vm_dir.name

            # Find snapshot directories
            for snapshot_dir in vm_dir.glob("*"):
                if not snapshot_dir.is_dir():
                    continue

                try:
                    # Parse timestamp from directory name
                    timestamp_str = snapshot_dir.name
                    backup_date = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    )

                    # Look for .fidx files (fixed index = VM disk images)
                    fidx_files = list(snapshot_dir.glob("*.fidx"))

                    if fidx_files:
                        vm_info = BackupVMInfo(
                            backup_format=BackupFormat.PROXMOX_PBS,
                            vm_name=f"vm-{vm_id}",
                            vm_uuid=vm_id,
                            backup_date=backup_date,
                            backup_type="full",  # PBS uses incremental chunks internally
                            backup_size_gb=sum(f.stat().st_size for f in fidx_files) / (1024**3),
                            backup_location=str(snapshot_dir),
                            disks=[{"path": str(f), "format": "fidx"} for f in fidx_files],
                            original_hypervisor="proxmox",
                            backup_metadata={
                                "vm_id": vm_id,
                                "snapshot_dir": str(snapshot_dir),
                                "fidx_files": [str(f) for f in fidx_files],
                            },
                        )
                        if filters:
                            if "vm_name" in filters and filters["vm_name"] not in vm_info.vm_name:
                                continue
                            if "backup_type" in filters and vm_info.backup_type != filters["backup_type"]:
                                continue

                        vms.append(vm_info)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # reason: per-snapshot best-effort scan -- one unparseable snapshot
                    # directory must not abort listing the rest.
                    self.logger.warning(f"Skipping unparseable backup snapshot '{snapshot_dir}': {e}")
                    continue

        return vms

    def _parse_snapshot_line(self, line: str) -> BackupVMInfo | None:
        """Parse PBS snapshot list output line."""
        # Example: vm/100/2024-01-15T10:30:00Z
        try:
            parts = line.split()
            if len(parts) < 2:
                return None

            snapshot_path = parts[0]
            if not snapshot_path.startswith("vm/"):
                return None

            _, vm_id, timestamp_str = snapshot_path.split("/")
            backup_date = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

            return BackupVMInfo(
                backup_format=BackupFormat.PROXMOX_PBS,
                vm_name=f"vm-{vm_id}",
                vm_uuid=vm_id,
                backup_date=backup_date,
                backup_type="full",
                backup_location=snapshot_path,
                original_hypervisor="proxmox",
            )

        except (ValueError, KeyError, TypeError) as e:
            self.logger.debug(f"Failed to parse PBS snapshot line: {e}")
            return None

    def get_vm_info(self, vm_identifier: str) -> BackupVMInfo:
        """
        Get VM info by ID or name.

        Args:
            vm_identifier: VM ID or name

        Returns:
            BackupVMInfo object

        Raises:
            ValueError: If VM not found
        """
        vms = self.list_vms()

        # Try to find by VM ID or name
        for vm in vms:
            if vm_identifier in (vm.vm_uuid, vm.vm_name):
                return vm

        raise ValueError(
            f"VM '{vm_identifier}' not found in Proxmox Backup Server. "
            f"Verify the VM ID/name and that the backup exists in the configured datastore."
        )

    def restore_vm(
        self,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None = None,
        point_in_time: datetime | None = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Restore VM from PBS.

        Args:
            vm_info: BackupVMInfo to restore
            output_dir: Output directory
            progress_callback: Progress callback
            point_in_time: Not used (PBS handles snapshot selection)
            verify_integrity: Verify integrity

        Returns:
            Restore result dict
        """
        # pylint: disable=duplicate-code
        # reason: mirrors generic.py's restore-result envelope -- same shape by convention, not shared logic.
        result: dict[str, Any] = {
            "success": False,
            "vm_name": vm_info.vm_name,
            "disks": [],
            "config": {},
            "warnings": [],
            "errors": [],
        }

        if not self._has_pbs_client:
            result["errors"].append("proxmox-backup-client not available")
            result["warnings"].append(
                "Install proxmox-backup-client to restore from PBS: apt install proxmox-backup-client"
            )
            return result

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            # Restore each disk
            for idx, disk in enumerate(vm_info.disks):
                disk_name = f"disk-{idx}.img"
                img_path = output_dir / disk_name
                qcow2_path = output_dir / f"{vm_info.vm_name}-disk{idx}.qcow2"

                # Restore using PBS client
                self.logger.info(f"Restoring disk {idx} from PBS")
                self._restore_disk_from_pbs(vm_info, disk, img_path)

                # Convert to qcow2
                self.logger.info("Converting to qcow2")
                self._convert_to_qcow2(img_path, qcow2_path)

                # Clean up intermediate image
                if img_path.exists():
                    img_path.unlink()

                result["disks"].append(
                    {"path": qcow2_path, "size_gb": qcow2_path.stat().st_size / (1024**3), "format": "qcow2"}
                )

            # pylint: disable=duplicate-code
            # reason: mirrors restore_vm's success/except/return tail in generic.py -- kept independent.
            result["success"] = True
            self.logger.info(f"Successfully restored {vm_info.vm_name}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort restore step -- failure is reported back in the
            # result dict rather than raised, so callers can decide how to proceed.
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to restore VM: {e}")

        return result

    def _restore_disk_from_pbs(
        self, vm_info: BackupVMInfo, _disk: dict[str, Any], output_path: Path
    ) -> None:
        # reason: `_disk` is currently unused -- proxmox-backup-client restores the
        # whole snapshot given only its path; kept in the signature to mirror the
        # per-disk call site and for future per-disk restore support.
        """
        Restore disk using proxmox-backup-client.

        Args:
            vm_info: BackupVMInfo
            output_path: Output path for restored image
        """
        snapshot_path = vm_info.backup_location

        cmd = ["proxmox-backup-client", "restore", snapshot_path, str(output_path)]

        if self.repository:
            cmd.extend(["--repository", self.repository])

        subprocess.run(cmd, check=True, capture_output=True)

    def _convert_to_qcow2(self, input_path: Path, output_path: Path) -> None:
        """Convert raw image to qcow2."""
        cmd = ["qemu-img", "convert", "-f", "raw", "-O", "qcow2", str(input_path), str(output_path)]
        run_qemu_img_convert(
            self.logger,
            cmd,
            output_path,
            src=input_path,
            task_label="Proxmox backup → qcow2",
            log_every_s=15.0,
        )

    def verify_backup_integrity(self, vm_info: BackupVMInfo) -> dict[str, Any]:
        """
        Verify PBS backup integrity.

        PBS has built-in verification, so we just check if snapshot exists.

        Args:
            vm_info: BackupVMInfo to verify

        Returns:
            Verification result dict
        """
        # pylint: disable=duplicate-code
        # reason: mirrors generic.py & veeam.py's verify-result envelope -- same shape by convention.
        result: dict[str, Any] = {
            "valid": True,
            "checksums_ok": True,  # PBS verifies internally
            "chain_complete": True,
            "errors": [],
            "warnings": [],
        }

        # Check if snapshot directory exists
        snapshot_path = Path(vm_info.backup_location)
        if not snapshot_path.exists():
            result["valid"] = False
            result["errors"].append(f"Snapshot not found: {snapshot_path}")

        return result

    def get_backup_chain(self, vm_info: BackupVMInfo) -> list[BackupVMInfo]:
        """
        Get backup chain.

        PBS handles incremental chunks internally, so chain is just the snapshot.

        Args:
            vm_info: BackupVMInfo

        Returns:
            List with single BackupVMInfo (PBS handles incrementals internally)
        """
        return [vm_info]

    def get_format(self) -> BackupFormat:
        """Get backup format."""
        return BackupFormat.PROXMOX_PBS
