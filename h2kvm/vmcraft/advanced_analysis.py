# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/advanced_analysis.py
"""
Advanced filesystem analysis and search capabilities.

Provides comprehensive filesystem analysis beyond basic operations:
- Advanced file search (by name, content, size, date)
- Large file detection
- Duplicate file detection (by checksum)
- Disk space analysis
- Security audit (permissions, ownership)
- Certificate detection
- Log file analysis

Features:
- Fast file search with glob patterns
- Content search (grep-like)
- Size-based filtering
- Time-based filtering
- Checksum-based duplicate detection
- Comprehensive security auditing
"""

from __future__ import annotations

import fnmatch
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class AdvancedAnalyzer:
    """
    Advanced filesystem analyzer.

    Provides advanced search, analysis, and security auditing capabilities.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations):
        """
        Initialize advanced analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance for filesystem access
        """
        self.logger = logger
        self.file_ops = file_ops

    def search_files(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches
        self,
        path: str = "/",
        name_pattern: str | None = None,
        content_pattern: str | None = None,
        min_size_mb: float | None = None,
        max_size_mb: float | None = None,
        file_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        # reason: single search entry point combining name/type/size/content filters,
        # each independently optional, over a streamed file listing.
        """
        Advanced file search with multiple criteria.

        Args:
            path: Starting path for search
            name_pattern: Filename pattern (glob-style: *.txt, *.log, etc.)
            content_pattern: Content search pattern (regex)
            min_size_mb: Minimum file size in MB
            max_size_mb: Maximum file size in MB
            file_type: File type filter (file, dir, link)
            limit: Maximum number of results

        Returns:
            List of matching file dictionaries
        """
        results: list[dict[str, Any]] = []

        try:  # pylint: disable=too-many-nested-blocks
            # reason: applying the independent name/type/size/content filters in
            # sequence, each with an early-continue, naturally nests a few levels deep.
            # Get all files
            all_files = self.file_ops.find(path)

            for file_path in all_files[: limit * 10]:  # Search more, return limit
                if len(results) >= limit:
                    break

                try:
                    # Name pattern filter
                    if name_pattern:
                        if not fnmatch.fnmatch(Path(file_path).name, name_pattern):
                            continue

                    # Type filter
                    if file_type:
                        if (file_type == "file" and not self.file_ops.is_file(file_path)) or (
                            file_type == "dir" and not self.file_ops.is_dir(file_path)
                        ):
                            continue

                    # Size filter
                    if min_size_mb or max_size_mb:
                        if not self.file_ops.is_file(file_path):
                            continue

                        size_bytes = self._get_file_size(file_path)
                        if size_bytes is None:
                            continue

                        size_mb = size_bytes / (1024 * 1024)
                        if min_size_mb and size_mb < min_size_mb:
                            continue
                        if max_size_mb and size_mb > max_size_mb:
                            continue

                    # Content filter (expensive - do last)
                    if content_pattern and self.file_ops.is_file(file_path):
                        try:
                            content = self.file_ops.read_file(file_path)
                            if not re.search(content_pattern, content.decode("utf-8", errors="ignore")):
                                continue
                        except Exception:  # pylint: disable=broad-exception-caught
                            # reason: per-file content read/decode probe -- one
                            # unreadable file must not abort the whole search.
                            continue

                    # Add to results
                    file_info = self._get_file_info(file_path)
                    if file_info:
                        results.append(file_info)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # reason: per-file best-effort filtering -- one file's failure
                    # must not abort the whole search.
                    self.logger.debug(f"Error processing {file_path}: {e}")
                    continue

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort analysis step -- must not abort the whole run;
            # returns whatever partial results were collected.
            self.logger.warning(f"Search failed: {e}")

        return results[:limit]

    def find_large_files(
        self, path: str = "/", min_size_mb: float = 100, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Find large files exceeding a size threshold.

        Args:
            path: Starting path
            min_size_mb: Minimum file size in MB
            limit: Maximum number of results

        Returns:
            List of large files sorted by size (descending)
        """
        large_files: list[dict[str, Any]] = []

        try:
            all_files = self.file_ops.find(path)

            for file_path in all_files:
                try:
                    if not self.file_ops.is_file(file_path):
                        continue

                    size_bytes = self._get_file_size(file_path)
                    if size_bytes is None:
                        continue

                    size_mb = size_bytes / (1024 * 1024)
                    if size_mb >= min_size_mb:
                        large_files.append(
                            {
                                "path": file_path,
                                "size_bytes": size_bytes,
                                "size_mb": round(size_mb, 2),
                            }
                        )

                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: per-file best-effort stat -- one file's failure must
                    # not abort the whole search.
                    continue

            # Sort by size descending
            large_files.sort(key=lambda x: x["size_bytes"], reverse=True)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort analysis step -- must not abort the whole run;
            # returns whatever partial results were collected.
            self.logger.warning(f"Large file search failed: {e}")

        return large_files[:limit]

    def find_duplicates(
        self, path: str = "/", min_size_mb: float = 1, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Find duplicate files using SHA256 checksums.

        Args:
            path: Starting path
            min_size_mb: Minimum file size to check
            limit: Maximum number of duplicate sets

        Returns:
            List of duplicate file groups
        """
        duplicates: list[dict[str, Any]] = []

        try:
            # Build checksum map
            checksum_map: dict[str, list[str]] = defaultdict(list)

            all_files = self.file_ops.find(path)

            for file_path in all_files:
                try:
                    if not self.file_ops.is_file(file_path):
                        continue

                    size_bytes = self._get_file_size(file_path)
                    if size_bytes is None:
                        continue

                    size_mb = size_bytes / (1024 * 1024)
                    if size_mb < min_size_mb:
                        continue

                    # Calculate checksum
                    checksum = self.file_ops.checksum("sha256", file_path)
                    if checksum:
                        checksum_map[checksum].append(file_path)

                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: per-file best-effort checksum -- one file's failure
                    # must not abort the whole search.
                    continue

            # Find duplicates (checksums with multiple files)
            for checksum, files in checksum_map.items():
                if len(files) > 1 and len(duplicates) < limit:
                    size_bytes = self._get_file_size(files[0])
                    duplicates.append(
                        {
                            "checksum": checksum,
                            "count": len(files),
                            "files": files,
                            "size_bytes": size_bytes,
                            "total_wasted_bytes": size_bytes * (len(files) - 1) if size_bytes else 0,
                        }
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort analysis step -- must not abort the whole run;
            # returns whatever partial results were collected.
            self.logger.warning(f"Duplicate detection failed: {e}")

        return duplicates

    def analyze_disk_space(self, path: str = "/", top_n: int = 20) -> dict[str, Any]:
        """
        Analyze disk space usage by directory.

        Args:
            path: Starting path
            top_n: Number of top directories to return

        Returns:
            Dict with space analysis
        """
        analysis = {
            "total_bytes": 0,
            "file_count": 0,
            "dir_count": 0,
            "top_directories": [],
        }

        try:
            # Calculate sizes for each directory
            dir_sizes: dict[str, int] = {}

            all_files = self.file_ops.find(path)

            for file_path in all_files:
                try:
                    if self.file_ops.is_file(file_path):
                        analysis["file_count"] += 1
                        size = self._get_file_size(file_path)
                        if size:
                            analysis["total_bytes"] += size

                            # Add to parent directory size
                            parent = str(Path(file_path).parent)
                            dir_sizes[parent] = dir_sizes.get(parent, 0) + size

                    elif self.file_ops.is_dir(file_path):
                        analysis["dir_count"] += 1

                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: per-file best-effort stat -- one file's failure must
                    # not abort the whole analysis.
                    continue

            # Get top directories
            sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)
            analysis["top_directories"] = [
                {"path": path, "size_bytes": size, "size_mb": round(size / (1024 * 1024), 2)}
                for path, size in sorted_dirs[:top_n]
            ]

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort analysis step -- must not abort the whole run;
            # returns whatever partial results were collected.
            self.logger.warning(f"Disk space analysis failed: {e}")

        return analysis

    def find_certificates(self, path: str = "/") -> list[dict[str, Any]]:
        """
        Find SSL/TLS certificates on the filesystem.

        Searches common certificate locations:
        - /etc/pki/
        - /etc/ssl/
        - /usr/share/ca-certificates/
        - C:\\ProgramData\\Microsoft\\Crypto\\

        Args:
            path: Starting path (default: root)

        Returns:
            List of certificate files found
        """
        certificates: list[dict[str, Any]] = []

        cert_patterns = ["*.crt", "*.cer", "*.pem", "*.key", "*.p12", "*.pfx"]

        cert_paths = [
            "/etc/pki",
            "/etc/ssl",
            "/etc/ca-certificates",
            "/usr/share/ca-certificates",
            "/usr/local/share/ca-certificates",
            "/Windows/System32/config/systemprofile/AppData/Local",
            "/ProgramData/Microsoft/Crypto",
        ]

        try:
            all_files = self.file_ops.find(path)

            for file_path in all_files:
                try:
                    # Check if in certificate path
                    in_cert_path = any(cert_path in file_path for cert_path in cert_paths)

                    # Check if matches cert pattern
                    matches_pattern = any(
                        fnmatch.fnmatch(Path(file_path).name, pattern) for pattern in cert_patterns
                    )

                    if in_cert_path or matches_pattern:
                        if self.file_ops.is_file(file_path):
                            size = self._get_file_size(file_path)
                            certificates.append(
                                {
                                    "path": file_path,
                                    "size_bytes": size,
                                    "type": self._guess_cert_type(file_path),
                                }
                            )

                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: per-file best-effort probe -- one file's failure must
                    # not abort the whole search.
                    continue

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort analysis step -- must not abort the whole run;
            # returns whatever partial results were collected.
            self.logger.warning(f"Certificate search failed: {e}")

        return certificates

    def _get_file_info(self, file_path: str) -> dict[str, Any] | None:
        """Get detailed file information."""
        try:
            info = {
                "path": file_path,
                "type": "file" if self.file_ops.is_file(file_path) else "dir",
            }

            if self.file_ops.is_file(file_path):
                size = self._get_file_size(file_path)
                if size is not None:
                    info["size_bytes"] = size
                    info["size_mb"] = round(size / (1024 * 1024), 2)

            return info

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort info lookup -- caller treats None as "unavailable".
            return None

    def _get_file_size(self, file_path: str) -> int | None:
        """Get file size in bytes."""
        try:
            # Use stat to get file size
            # pylint: disable=protected-access
            # reason: tight internal coupling within this package -- FileOperations
            # doesn't expose a public accessor for the mount root path.
            full_path = self.file_ops._mount_root / file_path.lstrip("/")
            return full_path.stat().st_size
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort size lookup -- caller treats None as "unavailable".
            return None

    def _guess_cert_type(self, file_path: str) -> str:
        """Guess certificate type from extension."""
        ext = Path(file_path).suffix.lower()
        cert_types = {
            ".crt": "certificate",
            ".cer": "certificate",
            ".pem": "pem_encoded",
            ".key": "private_key",
            ".p12": "pkcs12",
            ".pfx": "pkcs12",
        }
        return cert_types.get(ext, "unknown")
