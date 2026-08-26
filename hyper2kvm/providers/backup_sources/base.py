# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/backup_sources/base.py
"""
Base backup source interface for VM restore.

Defines abstract base class for backup format integrations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class BackupFormat(Enum):
    """Supported backup formats."""

    VEEAM = "veeam"
    COMMVAULT = "commvault"
    PROXMOX_PBS = "proxmox_pbs"
    ACRONIS = "acronis"
    RESTIC = "restic"
    BORG = "borg"
    GENERIC = "generic"


@dataclass
class BackupVMInfo:  # pylint: disable=too-many-instance-attributes
    """
    Backup VM metadata.

    Standardized VM information extracted from backup metadata (identity, backup
    metadata, VM config, disks, and chain info) — genuinely many independent fields.
    """

    # Identity
    backup_format: BackupFormat
    vm_name: str
    vm_uuid: str | None = None

    # Backup metadata
    backup_date: datetime | None = None
    backup_type: str = "full"  # full, incremental, differential
    backup_size_gb: float = 0.0
    backup_location: str = ""  # Path or URI

    # VM configuration
    cpu_count: int = 2
    memory_mb: int = 4096
    os_type: str = "unknown"  # windows, linux

    # Disk information
    disks: list[dict[str, Any]] = field(default_factory=list)

    # Backup chain info
    parent_backup: str | None = None  # For incremental/differential
    chain_depth: int = 0
    requires_merge: bool = False

    # Additional metadata
    original_hypervisor: str | None = None
    backup_metadata: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class RestoreProgress:
    """Restore progress tracking."""

    stage: str  # extraction, conversion, verification
    total_bytes: int
    processed_bytes: int
    progress_pct: float
    speed_mbps: float
    eta_seconds: float | None
    current_file: str | None = None


class BackupSource(ABC):
    """
    Abstract base class for backup source implementations.

    All backup sources must implement these methods.
    """

    def __init__(self, log: logging.Logger, backup_path: Path | str):
        """
        Initialize backup source.

        Args:
            log: Logger instance
            backup_path: Path to backup repository/file
        """
        self.logger = log
        self.backup_path = Path(backup_path)

        if not self.backup_path.exists():
            raise ValueError(
                f"Backup path does not exist: {backup_path}. "
                f"Verify the path is correct and the backup storage is mounted/accessible."
            )

    @abstractmethod
    def list_vms(self, filters: dict[str, Any] | None = None) -> list[BackupVMInfo]:
        """
        List VMs available in backup.

        Args:
            filters: Optional filters (date range, VM name pattern, etc.)

        Returns:
            List of BackupVMInfo objects
        """

    @abstractmethod
    def get_vm_info(self, vm_identifier: str) -> BackupVMInfo:
        """
        Get detailed information about backed-up VM.

        Args:
            vm_identifier: VM name or UUID in backup

        Returns:
            BackupVMInfo object

        Raises:
            ValueError: If VM not found in backup
        """

    @abstractmethod
    def restore_vm(
        self,
        vm_info: BackupVMInfo,
        output_dir: Path,
        progress_callback: Callable[[RestoreProgress], None] | None = None,
        point_in_time: datetime | None = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Restore VM from backup.

        Args:
            vm_info: BackupVMInfo for VM to restore
            output_dir: Directory to restore VM disks
            progress_callback: Optional progress callback
            point_in_time: Optional point-in-time to restore (for incremental backups)
            verify_integrity: Verify backup integrity before/after restore

        Returns:
            Restore result dict with:
                {
                    "success": bool,
                    "vm_name": str,
                    "disks": [{"path": Path, "size_gb": float, "format": str}],
                    "config": dict,  # VM configuration
                    "warnings": list[str],
                    "errors": list[str]
                }

        Raises:
            RuntimeError: If restore fails
        """

    @abstractmethod
    def verify_backup_integrity(self, vm_info: BackupVMInfo) -> dict[str, Any]:
        """
        Verify backup integrity.

        Args:
            vm_info: BackupVMInfo to verify

        Returns:
            Verification result dict:
                {
                    "valid": bool,
                    "checksums_ok": bool,
                    "chain_complete": bool,
                    "errors": list[str],
                    "warnings": list[str]
                }
        """

    @abstractmethod
    def get_backup_chain(self, vm_info: BackupVMInfo) -> list[BackupVMInfo]:
        """
        Get full backup chain for VM (for incremental/differential backups).

        Args:
            vm_info: BackupVMInfo (can be incremental)

        Returns:
            List of BackupVMInfo objects in chain order (full → incremental)
        """

    def get_format(self) -> BackupFormat:
        """Get backup format type."""
        raise NotImplementedError("Subclass must implement get_format()")

    def estimate_restore_time(self, vm_info: BackupVMInfo) -> dict[str, Any]:
        """
        Estimate restore time.

        Args:
            vm_info: BackupVMInfo to estimate

        Returns:
            Estimation dict:
                {
                    "extraction_seconds": float,
                    "conversion_seconds": float,
                    "total_seconds": float,
                    "notes": str
                }
        """
        # Default estimation: 50 MB/s extraction + conversion overhead
        extraction_time = (vm_info.backup_size_gb * 1024) / 50  # seconds
        conversion_time = extraction_time * 0.3  # 30% overhead for conversion

        return {
            "extraction_seconds": extraction_time,
            "conversion_seconds": conversion_time,
            "total_seconds": extraction_time + conversion_time,
            "notes": "Estimates based on 50 MB/s extraction speed",
        }
