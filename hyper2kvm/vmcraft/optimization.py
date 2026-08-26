# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/optimization.py
"""
Disk optimization and analysis operations.

Provides disk usage analysis and optimization:
- Large file detection
- Duplicate file detection
- Disk usage analysis
- Temporary file cleanup
- Empty directory detection
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DiskOptimizer:
    """
    Disk optimization and analysis.

    Provides tools for analyzing and optimizing disk usage.
    """

    def __init__(self, logger_instance: logging.Logger, mount_root: Path):
        """
        Initialize disk optimizer.

        Args:
            logger_instance: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger_instance
        self.mount_root = mount_root

    def find_large_files(self, min_size_mb: int = 100, path: str = "/") -> list[dict[str, Any]]:
        """
        Find large files in filesystem.

        Args:
            min_size_mb: Minimum file size in MB
            path: Starting path for search

        Returns:
            List of large files with size and path information
        """
        search_path = self.mount_root / path.lstrip("/")
        min_size_bytes = min_size_mb * 1024 * 1024
        large_files = []

        try:
            for root, _dirs, files in os.walk(search_path):
                for name in files:
                    filepath = Path(root) / name
                    try:
                        size = filepath.stat().st_size
                        if size >= min_size_bytes:
                            large_files.append(
                                {
                                    "path": str(filepath.relative_to(self.mount_root)),
                                    "size": size,
                                    "size_mb": size / (1024 * 1024),
                                }
                            )
                    except (PermissionError, OSError):
                        pass

            # Sort by size (largest first)
            large_files.sort(key=lambda x: x["size"], reverse=True)
            self.logger.info(f"Found {len(large_files)} files >= {min_size_mb}MB")

        # best-effort scan; large_files is still returned with whatever was found so far
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.exception(f"Find large files failed: {e}")

        return large_files

    # pylint: disable-next=too-many-locals
    def find_duplicates(self, path: str = "/", min_size_mb: int = 1) -> dict[str, list[str]]:
        """
        Find duplicate files by content hash.

        Args:
            path: Starting path for search
            min_size_mb: Minimum file size to check (skip small files)

        Returns:
            Dict mapping file hashes to lists of duplicate paths
        """
        search_path = self.mount_root / path.lstrip("/")
        min_size_bytes = min_size_mb * 1024 * 1024

        # First pass: group by size
        size_groups: dict[int, list[Path]] = defaultdict(list)

        try:
            for root, _dirs, files in os.walk(search_path):
                for name in files:
                    filepath = Path(root) / name
                    try:
                        size = filepath.stat().st_size
                        if size >= min_size_bytes:
                            size_groups[size].append(filepath)
                    except (PermissionError, OSError):
                        pass

            # Second pass: hash files with same size
            hash_groups: dict[str, list[str]] = defaultdict(list)

            for filepaths in size_groups.values():
                if len(filepaths) > 1:
                    for filepath in filepaths:
                        try:
                            file_hash = self._hash_file(filepath)
                            rel_path = str(filepath.relative_to(self.mount_root))
                            hash_groups[file_hash].append(rel_path)
                        except (PermissionError, OSError):
                            pass

            # Filter to only groups with duplicates
            duplicates = {h: paths for h, paths in hash_groups.items() if len(paths) > 1}

            total_dupes = sum(len(paths) - 1 for paths in duplicates.values())
            self.logger.info(f"Found {total_dupes} duplicate files")

        # best-effort scan; empty dict is a valid "no duplicates found" result on failure
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.exception(f"Find duplicates failed: {e}")
            return {}

        return duplicates

    def _hash_file(self, filepath: Path, chunk_size: int = 8192) -> str:
        """Calculate SHA256 hash of file."""
        hasher = hashlib.sha256()
        with filepath.open("rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()

    # pylint: disable-next=too-many-locals
    def analyze_disk_usage(self, path: str = "/", top_n: int = 20) -> dict[str, Any]:
        """
        Analyze disk usage by directory.

        Args:
            path: Starting path for analysis
            top_n: Number of top directories to return

        Returns:
            Dict with disk usage analysis
        """
        search_path = self.mount_root / path.lstrip("/")

        result: dict[str, Any] = {
            "total_size": 0,
            "total_files": 0,
            "total_dirs": 0,
            "top_directories": [],
        }

        try:
            dir_sizes: dict[str, int] = {}

            for root, dirs, files in os.walk(search_path):
                root_path = Path(root)
                dir_size = 0

                for name in files:
                    filepath = root_path / name
                    try:
                        size = filepath.stat().st_size
                        dir_size += size
                        result["total_size"] += size
                        result["total_files"] += 1
                    except (PermissionError, OSError):
                        pass

                result["total_dirs"] += len(dirs)
                rel_path = str(root_path.relative_to(self.mount_root))
                dir_sizes[rel_path] = dir_size

            # Sort by size and get top N
            sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)[:top_n]
            result["top_directories"] = [
                {"path": path, "size": size, "size_mb": size / (1024 * 1024)} for path, size in sorted_dirs
            ]

            self.logger.info(
                f"Disk usage: {result['total_size'] / (1024**3):.2f} GB, "
                f"{result['total_files']} files, {result['total_dirs']} dirs"
            )

        # best-effort walk; result is still returned with whatever was tallied so far
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.exception(f"Disk usage analysis failed: {e}")

        return result

    def cleanup_temp_files(self, dry_run: bool = True) -> dict[str, Any]:
        """
        Clean up temporary files.

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            Dict with cleanup results
        """
        result: dict[str, Any] = {
            "dry_run": dry_run,
            "files_found": 0,
            "files_deleted": 0,
            "space_freed": 0,
            "paths": [],
        }

        temp_dirs = ["tmp", "var/tmp", "var/cache"]

        # per-directory / per-file walk with a per-file try; clearer kept inline than split apart
        # pylint: disable-next=too-many-nested-blocks
        try:
            for temp_dir in temp_dirs:
                temp_path = self.mount_root / temp_dir
                if not temp_path.exists():
                    continue

                for item in temp_path.rglob("*"):
                    if item.is_file():
                        try:
                            size = item.stat().st_size
                            result["files_found"] += 1
                            result["space_freed"] += size
                            result["paths"].append(str(item.relative_to(self.mount_root)))

                            if not dry_run:
                                item.unlink()
                                result["files_deleted"] += 1
                        except (PermissionError, OSError):
                            pass

            action = "Would delete" if dry_run else "Deleted"
            self.logger.info(
                f"{action} {result['files_found']} temp files, {result['space_freed'] / (1024**2):.2f} MB"
            )

        # best-effort cleanup; result is still returned with whatever was processed so far
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.exception(f"Cleanup failed: {e}")

        return result
