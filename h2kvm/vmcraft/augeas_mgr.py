# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/augeas_mgr.py
"""
Augeas configuration management for VMCraft.

Provides structured configuration file editing using the Augeas library.
Supports common configuration formats: fstab, network configs, systemd units, etc.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    import augeas

    HAS_AUGEAS = True
except ImportError:
    HAS_AUGEAS = False
    augeas = None  # type: ignore


logger = logging.getLogger(__name__)


class AugeasManager:
    """
    Augeas configuration management wrapper.

    Provides high-level API for editing configuration files using Augeas lenses.
    Augeas is an optional dependency - gracefully degrades if not available.
    """

    def __init__(self, manager_logger: logging.Logger, root: str):
        """
        Initialize Augeas manager.

        Args:
            manager_logger: Logger instance
            root: Filesystem root (e.g., /tmp/mount-root for guest filesystem)
        """
        self.logger = manager_logger
        self.root = root
        self._aug: Any | None = None
        self._initialized = False

        if not HAS_AUGEAS:
            self.logger.warning("Augeas library not available. Install with: pip install python-augeas")

    def init(self, flags: int = 0) -> None:
        """
        Initialize Augeas with guest filesystem root.

        Args:
            flags: Augeas initialization flags (default: 0)
                   Common flags: augeas.Augeas.SAVE_BACKUP, augeas.Augeas.NO_LOAD

        Raises:
            RuntimeError: If Augeas library is not available or initialization fails
        """
        if not HAS_AUGEAS:
            raise RuntimeError("Augeas library not available (pip install python-augeas)")

        if self._initialized:
            self.logger.debug("Augeas already initialized")
            return

        try:
            # Initialize Augeas with guest root
            self._aug = augeas.Augeas(root=self.root, flags=flags)
            self._initialized = True
            self.logger.debug(f"Augeas initialized with root={self.root}, flags={flags}")
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Augeas configuration editor for root={self.root}. "
                f"Ensure python-augeas is installed correctly and the guest filesystem is mounted. "
                f"Detail: {e}"
            ) from e

    def close(self) -> None:
        """Close Augeas instance and release resources."""
        if self._aug:
            try:
                self._aug.close()
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cleanup; the augeas C binding can raise various error types on close
                self.logger.warning(f"Error closing Augeas: {e}")
            finally:
                self._aug = None
                self._initialized = False
                self.logger.debug("Augeas closed")

    def get(self, path: str) -> str | None:
        """
        Get configuration value at path.

        Args:
            path: Augeas path (e.g., "/files/etc/fstab/1/spec")

        Returns:
            Configuration value or None if path doesn't exist

        Raises:
            RuntimeError: If Augeas is not initialized
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            return self._aug.get(path)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort lookup; the augeas C binding can raise various error types
            self.logger.debug(f"Augeas get failed for {path}: {e}")
            return None

    def set(self, path: str, value: str) -> None:
        """
        Set configuration value at path.

        Args:
            path: Augeas path
            value: Value to set

        Raises:
            RuntimeError: If Augeas is not initialized or set fails
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            self._aug.set(path, value)
        except Exception as e:
            raise RuntimeError(
                f"Failed to set config value '{path}' in guest filesystem. "
                f"The config file may be read-only or the Augeas lens may not support this format. "
                f"Detail: {e}"
            ) from e

    def save(self) -> None:
        """
        Save changes to disk.

        Writes all pending changes to their respective configuration files.

        Raises:
            RuntimeError: If Augeas is not initialized or save fails
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            self._aug.save()
            self.logger.debug("Augeas changes saved")
        except Exception as e:
            raise RuntimeError(
                f"Failed to save configuration changes to guest filesystem. "
                f"Check that the guest disk is mounted read-write and has available space. "
                f"Detail: {e}"
            ) from e

    def match(self, pattern: str) -> list[str]:
        """
        Match paths by pattern.

        Args:
            pattern: Augeas path pattern (e.g., "/files/etc/fstab/*")

        Returns:
            List of matching paths

        Raises:
            RuntimeError: If Augeas is not initialized
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            return self._aug.match(pattern) or []
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort lookup; the augeas C binding can raise various error types
            self.logger.debug(f"Augeas match failed for {pattern}: {e}")
            return []

    def insert(self, path: str, label: str, before: bool = True) -> None:
        """
        Insert new node at path.

        Args:
            path: Path where to insert (must exist)
            label: Label for new node
            before: Insert before (True) or after (False) the path

        Raises:
            RuntimeError: If Augeas is not initialized or insert fails
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            self._aug.insert(path, label, before)
        except Exception as e:
            raise RuntimeError(
                f"Failed to insert config entry at '{path}' in guest filesystem. "
                f"The target path may not exist or the config format may not support insertion. "
                f"Detail: {e}"
            ) from e

    def remove(self, path: str) -> int:
        """
        Remove nodes matching path.

        Args:
            path: Augeas path (can be pattern with wildcards)

        Returns:
            Number of nodes removed

        Raises:
            RuntimeError: If Augeas is not initialized
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            count = self._aug.remove(path)
            return count if count else 0
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort removal; the augeas C binding can raise various error types
            self.logger.debug(f"Augeas remove failed for {path}: {e}")
            return 0

    def defvar(self, name: str, expr: str) -> None:
        """
        Define variable for use in path expressions.

        Variables can be used in subsequent paths as $name.

        Args:
            name: Variable name
            expr: Expression to evaluate

        Raises:
            RuntimeError: If Augeas is not initialized or defvar fails
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            self._aug.defvar(name, expr)
        except Exception as e:
            raise RuntimeError(
                f"Failed to define Augeas variable '{name}'. "
                f"The expression may be invalid or reference non-existent paths. Detail: {e}"
            ) from e

    def defnode(self, name: str, expr: str, value: str | None = None) -> tuple[int, bool]:
        """
        Define node variable.

        Creates the node if it doesn't exist.

        Args:
            name: Variable name
            expr: Node expression
            value: Optional value to set if node is created

        Returns:
            Tuple of (number of nodes matching expr, created flag)

        Raises:
            RuntimeError: If Augeas is not initialized or defnode fails
        """
        if not self._initialized or not self._aug:
            raise RuntimeError(
                "Augeas configuration editor not initialized. "
                "Call init() on the AugeasManager before performing config operations."
            )

        try:
            result = self._aug.defnode(name, expr, value)
            # defnode returns None if expr doesn't match and node was created
            # or tuple (count, created) in other cases
            if result is None:
                return (1, True)
            return result
        except Exception as e:
            raise RuntimeError(
                f"Failed to define Augeas node '{name}'. "
                f"The expression may be invalid or the config structure unsupported. Detail: {e}"
            ) from e

    def is_initialized(self) -> bool:
        """Check if Augeas is initialized."""
        return self._initialized

    def __enter__(self):
        """Context manager entry."""
        if not self._initialized:
            self.init()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.close()
        return False
