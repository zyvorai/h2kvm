# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/backup.py
"""
Backup and restore operations for guest filesystems.

Provides file and directory backup/restore capabilities:
- Archive creation (tar with gzip/bzip2/xz compression)
- Archive extraction
- Selective file backup
- Progress tracking
"""

from __future__ import annotations

import logging
import tarfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages backup and restore operations.

    Provides archive-based backup and restore for guest files.
    """

    def __init__(self, backup_logger: logging.Logger, mount_root: Path):
        """
        Initialize backup manager.

        Args:
            backup_logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = backup_logger
        self.mount_root = mount_root

    def backup_files(self, paths: list[str], dest_archive: str, compression: str = "gzip") -> dict[str, Any]:
        """
        Backup files to archive.

        Args:
            paths: List of paths to backup (relative to guest root)
            dest_archive: Destination archive path on host
            compression: Compression type (gzip, bzip2, xz, none)

        Returns:
            Dict with backup results
        """
        result: dict[str, Any] = {
            "ok": False,
            "archive": dest_archive,
            "compression": compression,
            "files_backed_up": 0,
            "error": None,
        }

        try:
            # Determine compression mode
            mode_map = {
                "gzip": "w:gz",
                "bzip2": "w:bz2",
                "xz": "w:xz",
                "none": "w",
            }
            mode = mode_map.get(compression, "w:gz")

            with tarfile.open(dest_archive, mode) as tar:
                for path in paths:
                    full_path = self.mount_root / path.lstrip("/")
                    if full_path.exists():
                        tar.add(str(full_path), arcname=path)
                        result["files_backed_up"] += 1
                    else:
                        self.logger.warning(f"Path not found: {path}")

            result["ok"] = True
            self.logger.info(f"Backed up {result['files_backed_up']} files to {dest_archive}")

        except (OSError, tarfile.TarError) as e:
            result["error"] = str(e)
            self.logger.exception(f"Backup failed: {e}")

        return result

    def restore_files(self, src_archive: str, dest_path: str = "/") -> dict[str, Any]:
        """
        Restore files from archive.

        Args:
            src_archive: Source archive path on host
            dest_path: Destination path in guest (default: /)

        Returns:
            Dict with restore results
        """
        result: dict[str, Any] = {
            "ok": False,
            "archive": src_archive,
            "destination": dest_path,
            "files_restored": 0,
            "error": None,
        }

        try:
            dest = self.mount_root / dest_path.lstrip("/")

            with tarfile.open(src_archive, "r:*") as tar:
                # Use the "data" extraction filter (PEP 706) to reject unsafe
                # members (path traversal, device files, etc.) during extraction.
                tar.extractall(path=dest, filter="data")
                result["files_restored"] = len(tar.getmembers())

            result["ok"] = True
            self.logger.info(f"Restored {result['files_restored']} files from {src_archive}")

        except (OSError, tarfile.TarError) as e:
            result["error"] = str(e)
            self.logger.exception(f"Restore failed: {e}")

        return result
