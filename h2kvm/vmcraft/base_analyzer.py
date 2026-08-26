# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/base_analyzer.py
"""
Base classes for VMCraft analyzers and detectors.

Provides common initialization and utilities for all analyzer/detector classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from .file_ops import FileOperations


# base class exists purely to share __init__; subclasses add the public methods
# pylint: disable-next=too-few-public-methods
class BaseAnalyzer:
    """
    Base class for all VMCraft analyzers and detectors.

    Provides common initialization pattern used by all analyzer/detector classes.
    Subclasses inherit logger, file_ops, and mount_root attributes automatically.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize base analyzer.

        Args:
            logger: Logger instance for diagnostics
            file_ops: FileOperations instance for filesystem access
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def _check_exists(self, path: str) -> bool:
        """
        Check if file/directory exists in guest filesystem.

        Args:
            path: Absolute path in guest filesystem

        Returns:
            True if path exists
        """
        return self.file_ops.exists(path)

    def _is_dir(self, path: str) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Absolute path in guest filesystem

        Returns:
            True if path is a directory
        """
        return self.file_ops.is_dir(path)

    def _is_file(self, path: str) -> bool:
        """
        Check if path is a regular file.

        Args:
            path: Absolute path in guest filesystem

        Returns:
            True if path is a regular file
        """
        return self.file_ops.is_file(path)

    def _read_file(self, path: str) -> str:
        """
        Read file contents as string.

        Args:
            path: Absolute path in guest filesystem

        Returns:
            File contents as string

        Raises:
            Exception: If file doesn't exist or can't be read
        """
        return self.file_ops.cat(path)

    def _read_lines(self, path: str) -> list[str]:
        """
        Read file contents as list of lines.

        Args:
            path: Absolute path in guest filesystem

        Returns:
            List of lines (without trailing newlines)

        Raises:
            Exception: If file doesn't exist or can't be read
        """
        content = self.file_ops.cat(path)
        return content.splitlines()

    def _list_dir(self, path: str) -> list[str]:
        """
        List directory contents.

        Args:
            path: Absolute path to directory in guest filesystem

        Returns:
            List of filenames in directory

        Raises:
            Exception: If directory doesn't exist or can't be read
        """
        return self.file_ops.ls(path)

    def _safe_read(self, path: str, default: str = "") -> str:
        """
        Safely read file, returning default if file doesn't exist or can't be read.

        Args:
            path: Absolute path in guest filesystem
            default: Default value to return on error

        Returns:
            File contents or default value
        """
        try:
            return self.file_ops.cat(path)
        # "safe" read by design: any failure (missing file, permissions, etc.) falls back to default
        except Exception:  # pylint: disable=broad-exception-caught
            return default

    def _safe_read_lines(self, path: str, default: list[str] | None = None) -> list[str]:
        """
        Safely read file lines, returning default if file doesn't exist or can't be read.

        Args:
            path: Absolute path in guest filesystem
            default: Default value to return on error

        Returns:
            List of file lines or default value
        """
        if default is None:
            default = []
        try:
            content = self.file_ops.cat(path)
            return content.splitlines()
        # "safe" read by design: any failure (missing file, permissions, etc.) falls back to default
        except Exception:  # pylint: disable=broad-exception-caught
            return default
