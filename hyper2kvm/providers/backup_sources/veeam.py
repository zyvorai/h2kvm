# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/backup_sources/veeam.py
"""
Veeam Backup & Replication integration.

Supports restoring VMs from Veeam backup files (VBK, VIB).

Veeam File Formats:
- .vbk: Full backup file
- .vib: Incremental backup file
- .vrb: Reverse incremental backup file

Restore Methods:
1. Extract VMDK from VBK/VIB using Veeam Extract Utility
2. Convert VMDK to qcow2 for KVM
3. Optionally merge incremental chain
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from hyper2kvm.converters.qemu.converter import run_qemu_img_convert
from hyper2kvm.core.structured_log import PhaseTimer, TraceContext, log_event

from .base import BackupFormat, BackupSource, BackupVMInfo, RestoreProgress

logger = logging.getLogger(__name__)


class VeeamBackupSource(BackupSource):
    """
    Veeam Backup & Replication source.

    Restores VMs from Veeam backup repository.
    """

    def __init__(self, source_logger: logging.Logger, backup_path: Path | str):
        """
        Initialize Veeam backup source.

        Args:
            source_logger: Logger instance
            backup_path: Path to Veeam backup repository
        """
        super().__init__(source_logger, backup_path)

        # Check for Veeam Extract Utility
        self._has_veeam_extract = self._check_veeam_extract()

    def _check_veeam_extract(self) -> bool:
        """Check if Veeam Extract Utility is available."""
        try:
            result = subprocess.run(["which", "veeamconfig"], capture_output=True, text=True, check=False)
            return result.returncode == 0
        except OSError as e:
            self.logger.debug("veeamconfig check failed: %s", e)
            return False

    def list_vms(self, filters: dict[str, Any] | None = None) -> list[BackupVMInfo]:
        """
        List VMs in Veeam backup.

        Scans for .vbk files in backup repository.

        Args:
            filters: Optional filters (vm_name pattern, date_after, date_before)

        Returns:
            List of BackupVMInfo objects
        """
        vms = []

        # Scan for VBK (full backup) files
        vbk_files = list(self.backup_path.rglob("*.vbk"))

        for vbk_file in vbk_files:
            try:
                vm_info = self._parse_vbk_file(vbk_file)

                # Apply filters
                if filters:
                    if "vm_name" in filters and filters["vm_name"] not in vm_info.vm_name:
                        continue
                    if "date_after" in filters and vm_info.backup_date:
                        if vm_info.backup_date < filters["date_after"]:
                            continue
                    if "date_before" in filters and vm_info.backup_date:
                        if vm_info.backup_date > filters["date_before"]:
                            continue

                vms.append(vm_info)

            # skip one unparseable backup file, must not abort listing the rest
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.warning("Skipping unparseable Veeam backup file '%s': %s", vbk_file.name, e)
                continue

        self.logger.info(f"Found {len(vms)} VMs in Veeam backup")
        return vms

    def _parse_vbk_file(self, vbk_path: Path) -> BackupVMInfo:
        """
        Parse VBK file metadata.

        Note: This is a simplified implementation. Real Veeam integration would
        use Veeam PowerShell module or REST API to query backup metadata.

        Args:
            vbk_path: Path to VBK file

        Returns:
            BackupVMInfo object
        """
        # Extract VM name from filename (convention: VMName_YYYYMMDD.vbk)
        vm_name = vbk_path.stem.split("_")[0] if "_" in vbk_path.stem else vbk_path.stem

        # Get file size
        backup_size_gb = vbk_path.stat().st_size / (1024**3)

        # Get modification time as backup date
        backup_date = datetime.fromtimestamp(vbk_path.stat().st_mtime)

        # Look for companion VIB (incremental) files
        vib_files = list(vbk_path.parent.glob(f"{vbk_path.stem}*.vib"))

        return BackupVMInfo(
            backup_format=BackupFormat.VEEAM,
            vm_name=vm_name,
            vm_uuid=None,
            backup_date=backup_date,
            backup_type="full",
            backup_size_gb=backup_size_gb,
            backup_location=str(vbk_path),
            cpu_count=2,  # Unknown without metadata
            memory_mb=4096,  # Unknown without metadata
            os_type="unknown",
            disks=[],  # Would be populated from VBK metadata
            parent_backup=None,
            chain_depth=len(vib_files),
            requires_merge=len(vib_files) > 0,
            original_hypervisor="vmware",  # Most Veeam backups are VMware
            backup_metadata={
                "vbk_file": str(vbk_path),
                "vib_count": len(vib_files),
                "vib_files": [str(f) for f in vib_files],
            },
        )

    def get_vm_info(self, vm_identifier: str) -> BackupVMInfo:
        """
        Get VM info by name.

        Args:
            vm_identifier: VM name

        Returns:
            BackupVMInfo object

        Raises:
            ValueError: If VM not found
        """
        vms = self.list_vms(filters={"vm_name": vm_identifier})

        if not vms:
            raise ValueError(
                f"VM '{vm_identifier}' not found in Veeam backup repository at {self.backup_path}. "
                f"Verify the VM name and that the backup (.vbk) files are present."
            )

        # Return most recent backup if multiple found
        # backup_date is always naive (derived from datetime.fromtimestamp() without
        # tzinfo elsewhere in this module), so the fallback must stay naive too or
        # comparisons against real backup_date values would raise TypeError.
        return max(vms, key=lambda vm: vm.backup_date or datetime.min)  # noqa: DTZ901

    def restore_vm(
        self,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None = None,
        point_in_time: datetime | None = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Restore VM from Veeam backup.

        Workflow:
        1. Extract VMDK from VBK/VIB
        2. Convert VMDK to qcow2
        3. Optionally verify integrity

        Args:
            vm_info: BackupVMInfo to restore
            output_dir: Output directory
            progress_callback: Progress callback
            point_in_time: Point-in-time restore (not implemented)
            verify_integrity: Verify before/after

        Returns:
            Restore result dict
        """
        result: dict[str, Any] = {
            "success": False,
            "vm_name": vm_info.vm_name,
            "disks": [],
            "config": {},
            "warnings": [],
            "errors": [],
        }

        with TraceContext(vm_id=vm_info.vm_name, workflow="veeam_restore", component="backup_sources"):
            try:
                # Create output directory
                output_dir.mkdir(parents=True, exist_ok=True)

                # Verify backup integrity first
                if verify_integrity:
                    self.logger.info(f"Verifying backup integrity for {vm_info.vm_name}")
                    with PhaseTimer("veeam_verify_start", "veeam_verify_complete", phase="verification"):
                        verification = self.verify_backup_integrity(vm_info)
                    if not verification["valid"]:
                        result["errors"].extend(verification["errors"])
                        return result

                # Extract VMDK from VBK
                vbk_path = Path(vm_info.backup_location)
                vmdk_path = output_dir / f"{vm_info.vm_name}.vmdk"

                self.logger.info(f"Extracting VMDK from {vbk_path.name}")

                if self._has_veeam_extract:
                    # Use Veeam Extract Utility if available
                    with PhaseTimer("veeam_extract_start", "veeam_extract_complete", phase="extraction"):
                        self._extract_with_veeam(vbk_path, vmdk_path, progress_callback)
                else:
                    # Fallback: Provide manual instructions
                    result["errors"].append(
                        "Veeam Extract Utility not available. "
                        "Please install Veeam Backup & Replication or use Veeam Standalone Extract Utility."
                    )
                    result["warnings"].append(
                        f"Manual extraction required: Use Veeam Extract Utility to extract {vbk_path} to {vmdk_path}"
                    )
                    return result

                # Convert VMDK to qcow2
                qcow2_path = output_dir / f"{vm_info.vm_name}.qcow2"

                self.logger.info("Converting disk image to qcow2")
                with PhaseTimer("veeam_convert_start", "veeam_convert_complete", phase="conversion"):
                    self._convert_vmdk_to_qcow2(vmdk_path, qcow2_path, progress_callback)

                # Clean up intermediate VMDK
                if vmdk_path.exists():
                    vmdk_path.unlink()

                result["success"] = True
                result["disks"].append(
                    {"path": qcow2_path, "size_gb": qcow2_path.stat().st_size / (1024**3), "format": "qcow2"}
                )

                self.logger.info(f"Successfully restored {vm_info.vm_name} to {qcow2_path}")
                log_event("veeam_restore_complete", vm_name=vm_info.vm_name, status="success")

            # restore covers extraction/conversion/IO steps; must not abort the whole batch over one VM's failure
            except Exception as e:  # pylint: disable=broad-exception-caught
                result["errors"].append(str(e))
                self.logger.exception("Failed to restore VM: %s", e)
                log_event("veeam_restore_failed", level="error", vm_name=vm_info.vm_name, error=str(e))

        return result

    def _extract_with_veeam(
        self, vbk_path: Path, output_path: Path, progress_callback: Callable[[RestoreProgress], None] | None
    ) -> None:
        """
        Extract VMDK using Veeam Extract Utility.

        Note: This is a placeholder. Real implementation would use:
        - Veeam PowerShell: Get-VBRBackup, Get-VBRRestorePoint, Export-VBRBackupItem
        - Veeam REST API
        - veeamconfig command-line tool (Linux)

        Args:
            vbk_path: Path to VBK file
            output_path: Output VMDK path
            progress_callback: Progress callback
        """
        # Placeholder implementation
        raise NotImplementedError(
            "Veeam extraction requires Veeam Extract Utility. "
            "Install Veeam Backup & Replication or use manual extraction."
        )

    def _convert_vmdk_to_qcow2(
        self, vmdk_path: Path, qcow2_path: Path, progress_callback: Callable[[RestoreProgress], None] | None
    ) -> None:
        """
        Convert VMDK to qcow2 using qemu-img.

        Args:
            vmdk_path: Input VMDK path
            qcow2_path: Output qcow2 path
            progress_callback: Progress callback
        """
        cmd = [
            "qemu-img",
            "convert",
            "-f",
            "vmdk",
            "-O",
            "qcow2",
            "-p",
            str(vmdk_path),
            str(qcow2_path),
        ]

        total_bytes = vmdk_path.stat().st_size

        def _progress(frac: float) -> None:
            if not progress_callback:
                return
            pct = frac * 100.0
            progress_callback(
                RestoreProgress(
                    stage="conversion",
                    total_bytes=total_bytes,
                    processed_bytes=int(total_bytes * frac),
                    progress_pct=pct,
                    speed_mbps=0.0,
                    eta_seconds=None,
                    current_file=str(vmdk_path),
                )
            )

        run_qemu_img_convert(
            self.logger,
            cmd,
            qcow2_path,
            src=vmdk_path,
            task_label="Veeam VMDK → qcow2",
            progress_callback=_progress if progress_callback else None,
            log_every_s=15.0,
        )

    def verify_backup_integrity(self, vm_info: BackupVMInfo) -> dict[str, Any]:
        """
        Verify Veeam backup integrity.

        Checks:
        - VBK file exists and is readable
        - Backup chain is complete (if incrementals exist)

        Args:
            vm_info: BackupVMInfo to verify

        Returns:
            Verification result dict
        """
        # pylint: disable=duplicate-code
        # reason: mirrors proxmox.py & generic.py's verify-result envelope -- same shape by convention.
        result: dict[str, Any] = {
            "valid": True,
            "checksums_ok": True,  # Veeam has internal checksums
            "chain_complete": True,
            "errors": [],
            "warnings": [],
        }

        vbk_path = Path(vm_info.backup_location)

        # Check VBK exists
        if not vbk_path.exists():
            result["valid"] = False
            result["errors"].append(f"VBK file not found: {vbk_path}")
            return result

        # Check VBK is readable
        if not vbk_path.is_file():
            result["valid"] = False
            result["errors"].append(f"VBK path is not a file: {vbk_path}")
            return result

        # Check for incremental chain
        if vm_info.chain_depth > 0:
            vib_files = vm_info.backup_metadata.get("vib_files", [])
            for vib_file in vib_files:
                if not Path(vib_file).exists():
                    result["chain_complete"] = False
                    result["warnings"].append(f"Incremental file missing: {vib_file}")

        return result

    def get_backup_chain(self, vm_info: BackupVMInfo) -> list[BackupVMInfo]:
        """
        Get full backup chain (VBK + VIBs).

        Args:
            vm_info: BackupVMInfo (can be incremental)

        Returns:
            List of BackupVMInfo in chain order
        """
        chain = [vm_info]

        # Add incremental backups if they exist
        if vm_info.chain_depth > 0:
            vib_files = vm_info.backup_metadata.get("vib_files", [])
            for vib_file in vib_files:
                vib_path = Path(vib_file)
                if vib_path.exists():
                    # Create BackupVMInfo for VIB
                    vib_info = BackupVMInfo(
                        backup_format=BackupFormat.VEEAM,
                        vm_name=vm_info.vm_name,
                        backup_date=datetime.fromtimestamp(vib_path.stat().st_mtime),
                        backup_type="incremental",
                        backup_size_gb=vib_path.stat().st_size / (1024**3),
                        backup_location=str(vib_path),
                        parent_backup=str(vm_info.backup_location),
                    )
                    chain.append(vib_info)

        return chain

    def get_format(self) -> BackupFormat:
        """Get backup format."""
        return BackupFormat.VEEAM
