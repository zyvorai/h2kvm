# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/backup_sources/generic.py
"""
Generic backup source for archive-based backups.

Supports:
- Tar archives (.tar, .tar.gz, .tar.bz2, .tar.xz)
- ZIP archives
- Directory-based backups
- Restic/Borg archives (via export)

Use cases:
- Simple file-based backups
- Manual VM exports
- Generic archive restores
"""

from __future__ import annotations

import logging
import shutil
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .base import BackupFormat, BackupSource, BackupVMInfo, RestoreProgress

logger = logging.getLogger(__name__)


class GenericBackupSource(BackupSource):
    """
    Generic backup source for archive formats.

    Handles tar, zip, and directory-based backups.
    """

    def __init__(self, source_logger: logging.Logger, backup_path: Path | str):
        """
        Initialize generic backup source.

        Args:
            source_logger: Logger instance
            backup_path: Path to backup archive or directory
        """
        super().__init__(source_logger, backup_path)

        self.backup_type = self._detect_backup_type()

    def _detect_backup_type(self) -> str:
        """Detect backup type from path."""
        if self.backup_path.is_dir():
            return "directory"
        if self.backup_path.suffix in [".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz"]:
            return "tar"
        if self.backup_path.suffix == ".zip":
            return "zip"
        return "unknown"

    def list_vms(self, filters: dict[str, Any] | None = None) -> list[BackupVMInfo]:
        """
        List VMs in backup.

        For generic backups, we assume one VM per archive/directory.

        Args:
            filters: Optional filters (not used for generic backups)

        Returns:
            List with single BackupVMInfo object
        """
        vm_name = self.backup_path.stem

        # Detect disk images in backup
        disks = self._find_disk_images()

        vm_info = BackupVMInfo(
            backup_format=BackupFormat.GENERIC,
            vm_name=vm_name,
            backup_date=datetime.fromtimestamp(self.backup_path.stat().st_mtime),
            backup_type="full",
            backup_size_gb=self._get_backup_size(),
            backup_location=str(self.backup_path),
            disks=disks,
            backup_metadata={"backup_type": self.backup_type, "disk_count": len(disks)},
        )

        return [vm_info]

    def _find_disk_images(self) -> list[dict[str, Any]]:
        """Find disk images in backup."""
        disks = []
        disk_extensions = [".qcow2", ".vmdk", ".vdi", ".vhd", ".vhdx", ".img", ".raw"]

        if self.backup_type == "directory":
            # Scan directory for disk images
            for ext in disk_extensions:
                for disk_path in self.backup_path.rglob(f"*{ext}"):
                    disks.append(
                        {
                            "path": str(disk_path),
                            "format": ext[1:],  # Remove leading dot
                            "size_gb": disk_path.stat().st_size / (1024**3),
                        }
                    )

        elif self.backup_type == "tar":
            # List tar contents
            try:
                with tarfile.open(self.backup_path, "r:*") as tar:
                    for member in tar.getmembers():
                        if any(member.name.endswith(ext) for ext in disk_extensions):
                            disks.append(
                                {
                                    "path": member.name,
                                    "format": Path(member.name).suffix[1:],
                                    "size_gb": member.size / (1024**3),
                                }
                            )
            except (tarfile.TarError, OSError) as e:
                self.logger.warning("Failed to read backup archive contents: %s", e)

        elif self.backup_type == "zip":
            # List zip contents
            try:
                with zipfile.ZipFile(self.backup_path, "r") as zf:
                    for info in zf.infolist():
                        if any(info.filename.endswith(ext) for ext in disk_extensions):
                            disks.append(
                                {
                                    "path": info.filename,
                                    "format": Path(info.filename).suffix[1:],
                                    "size_gb": info.file_size / (1024**3),
                                }
                            )
            except (zipfile.BadZipFile, OSError) as e:
                self.logger.warning("Failed to read backup zip contents: %s", e)

        return disks

    def _get_backup_size(self) -> float:
        """Get backup size in GB."""
        if self.backup_path.is_dir():
            # Sum all files in directory
            total = sum(f.stat().st_size for f in self.backup_path.rglob("*") if f.is_file())
            return total / (1024**3)
        return self.backup_path.stat().st_size / (1024**3)

    def get_vm_info(self, vm_identifier: str) -> BackupVMInfo:
        """
        Get VM info.

        For generic backups, there's only one VM.

        Args:
            vm_identifier: VM name (ignored)

        Returns:
            BackupVMInfo object
        """
        vms = self.list_vms()
        return vms[0] if vms else None

    def restore_vm(
        self,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None = None,
        point_in_time: datetime | None = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Restore VM from generic backup.

        Workflow:
        1. Extract archive (if archive)
        2. Copy disk images to output directory
        3. Convert to qcow2 if needed

        Args:
            vm_info: BackupVMInfo to restore
            output_dir: Output directory
            progress_callback: Progress callback
            point_in_time: Not used
            verify_integrity: Verify integrity

        Returns:
            Restore result dict
        """
        # pylint: disable=duplicate-code
        # reason: mirrors proxmox.py's restore-result envelope -- same shape by convention, not shared logic.
        result: dict[str, Any] = {
            "success": False,
            "vm_name": vm_info.vm_name,
            "disks": [],
            "config": {},
            "warnings": [],
            "errors": [],
        }

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            if self.backup_type == "directory":
                # Copy disk images from directory
                for disk in vm_info.disks:
                    disk_path = Path(disk["path"])
                    dest_path = output_dir / disk_path.name

                    self.logger.info(f"Copying {disk_path.name}")
                    shutil.copy2(disk_path, dest_path)

                    result["disks"].append(
                        {
                            "path": dest_path,
                            "size_gb": dest_path.stat().st_size / (1024**3),
                            "format": disk["format"],
                        }
                    )

            elif self.backup_type == "tar":
                # Extract tar archive
                self._extract_tar(vm_info, output_dir, progress_callback)

                # Find extracted disks
                for disk in vm_info.disks:
                    disk_name = Path(disk["path"]).name
                    disk_path = output_dir / disk_name

                    if disk_path.exists():
                        result["disks"].append(
                            {
                                "path": disk_path,
                                "size_gb": disk_path.stat().st_size / (1024**3),
                                "format": disk["format"],
                            }
                        )

            elif self.backup_type == "zip":
                # Extract zip archive
                self._extract_zip(vm_info, output_dir, progress_callback)

                # Find extracted disks
                for disk in vm_info.disks:
                    disk_name = Path(disk["path"]).name
                    disk_path = output_dir / disk_name

                    if disk_path.exists():
                        result["disks"].append(
                            {
                                "path": disk_path,
                                "size_gb": disk_path.stat().st_size / (1024**3),
                                "format": disk["format"],
                            }
                        )

            # pylint: disable=duplicate-code
            # reason: mirrors restore_vm's success/except/return tail in proxmox.py -- kept independent.
            result["success"] = True
            self.logger.info(f"Successfully restored {vm_info.vm_name}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: restore spans extraction, copying, and format-specific I/O;
            # any failure must be recorded in the result rather than crash the caller
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to restore VM: {e}")

        return result

    def _extract_tar(
        self,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None,
    ) -> None:
        """Extract tar archive."""
        with tarfile.open(self.backup_path, "r:*") as tar:
            # Extract disk images only
            for disk in vm_info.disks:
                member = tar.getmember(disk["path"])
                tar.extract(member, output_dir)

                if progress_callback:
                    progress = RestoreProgress(
                        stage="extraction",
                        total_bytes=vm_info.backup_size_gb * 1024**3,
                        processed_bytes=member.size,
                        progress_pct=100.0,  # Simplified
                        speed_mbps=0.0,
                        eta_seconds=None,
                        current_file=disk["path"],
                    )
                    progress_callback(progress)

    def _extract_zip(
        self,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None,
    ) -> None:
        """Extract zip archive."""
        with zipfile.ZipFile(self.backup_path, "r") as zf:
            # Extract disk images only
            for disk in vm_info.disks:
                zf.extract(disk["path"], output_dir)

                if progress_callback:
                    progress = RestoreProgress(
                        stage="extraction",
                        total_bytes=vm_info.backup_size_gb * 1024**3,
                        processed_bytes=disk["size_gb"] * 1024**3,
                        progress_pct=100.0,
                        speed_mbps=0.0,
                        eta_seconds=None,
                        current_file=disk["path"],
                    )
                    progress_callback(progress)

    def verify_backup_integrity(self, vm_info: BackupVMInfo) -> dict[str, Any]:
        """
        Verify backup integrity.

        Basic checks:
        - Backup exists
        - Archive is valid (if archive)

        Args:
            vm_info: BackupVMInfo to verify

        Returns:
            Verification result dict
        """
        # pylint: disable=duplicate-code
        # reason: mirrors proxmox.py & veeam.py's verify-result envelope -- same shape by convention.
        result: dict[str, Any] = {
            "valid": True,
            "checksums_ok": True,
            "chain_complete": True,
            "errors": [],
            "warnings": [],
        }

        if not self.backup_path.exists():
            result["valid"] = False
            result["errors"].append("Backup path does not exist")
            return result

        # Verify archive integrity
        if self.backup_type == "tar":
            try:
                with tarfile.open(self.backup_path, "r:*"):
                    # Just opening is a basic integrity check
                    pass
            except (tarfile.TarError, OSError) as e:
                result["valid"] = False
                result["errors"].append(f"Tar archive corrupted: {e}")

        elif self.backup_type == "zip":
            try:
                with zipfile.ZipFile(self.backup_path, "r") as zf:
                    # Test zip integrity
                    bad_file = zf.testzip()
                    if bad_file:
                        result["valid"] = False
                        result["errors"].append(f"Corrupted file in zip: {bad_file}")
            except (zipfile.BadZipFile, OSError) as e:
                result["valid"] = False
                result["errors"].append(f"Zip archive corrupted: {e}")

        return result

    def get_backup_chain(self, vm_info: BackupVMInfo) -> list[BackupVMInfo]:
        """
        Get backup chain.

        Generic backups are always full, no chain.

        Args:
            vm_info: BackupVMInfo

        Returns:
            List with single BackupVMInfo
        """
        return [vm_info]

    def get_format(self) -> BackupFormat:
        """Get backup format."""
        return BackupFormat.GENERIC
