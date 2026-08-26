# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows registry hive reader utility.

Provides a context-managed reader for Windows registry hives that eliminates
the duplicated download/open/navigate/extract/close pattern found across
multiple inspection methods.
"""
# pylint: disable=duplicate-code
# The guestfs typing-only stand-in below is intentionally repeated verbatim in a few
# modules; it's a tiny fallback shim, not worth extracting into a shared import.

from __future__ import annotations

import contextlib
import logging
import os
import struct
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # typing-only stand-in matching the guestfs module's name/shape when unavailable
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            class GuestFS(Protocol): ...  # pylint: disable=missing-class-docstring,too-few-public-methods


logger = logging.getLogger(__name__)

# Registry hive paths on Windows filesystem
HIVE_SYSTEM = "/Windows/System32/config/SYSTEM"
HIVE_SOFTWARE = "/Windows/System32/config/SOFTWARE"
HIVE_SAM = "/Windows/System32/config/SAM"


class RegistryReader:
    """
    Context-managed reader for Windows registry hives.

    Handles downloading the hive from a guest filesystem, opening it with
    hivex, and cleaning up temporary files. Provides navigation and value
    extraction helpers.

    Usage:
        with RegistryReader(g, HIVE_SYSTEM) as reg:
            if reg.is_open:
                value = reg.read_string_value(
                    ["ControlSet001", "Control", "ComputerName", "ComputerName"],
                    "ComputerName",
                )
    """

    def __init__(self, g: guestfs.GuestFS, hive_path: str, log: logging.Logger | None = None):
        self._g = g
        self._hive_path = hive_path
        self._logger = log or logger
        self._hivex = None  # type: Any
        self._tmp_path: str | None = None
        self.is_open = False

    def __enter__(self) -> RegistryReader:
        try:
            import hivex  # pylint: disable=import-outside-toplevel  # hivex is an optional dependency; probed here via ImportError
        except ImportError:
            self._logger.debug("hivex library not available for Windows registry parsing")
            return self

        if not self._g.exists(self._hive_path):
            return self

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".reg") as tmp:
                self._tmp_path = tmp.name

            self._g.download(self._hive_path, self._tmp_path)
            self._hivex = hivex.Hivex(self._tmp_path)
            self.is_open = True
        # hivex raises various undocumented exception types; any failure means "hive unreadable"
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._logger.debug("Failed to open registry hive %s: %s", self._hive_path, e)
            self._cleanup()

        return self

    def __exit__(self, *exc: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        if self._hivex is not None:
            with contextlib.suppress(Exception):
                self._hivex.close()
            self._hivex = None
        if self._tmp_path and os.path.exists(self._tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(self._tmp_path)
            self._tmp_path = None
        self.is_open = False

    def find_key(self, parent: Any, name: str) -> Any | None:
        """Find a child key by name under parent. Returns None if not found."""
        if not self.is_open or parent is None:
            return None
        try:
            for child in self._hivex.node_children(parent):
                if self._hivex.node_name(child) == name:
                    return child
        except Exception:  # pylint: disable=broad-exception-caught  # hivex raises various undocumented exception types; any failure means "key not found"
            pass
        return None

    def navigate(self, path: list[str]) -> Any | None:
        """Navigate a registry key path from root. Returns the final key or None."""
        if not self.is_open:
            return None
        node = self._hivex.root()
        for segment in path:
            node = self.find_key(node, segment)
            if node is None:
                return None
        return node

    def get_values(self, key: Any) -> list[Any]:
        """Get all values for a registry key."""
        if not self.is_open or key is None:
            return []
        try:
            return self._hivex.node_values(key)
        except Exception:  # pylint: disable=broad-exception-caught  # hivex raises various undocumented exception types; treat any failure as "no values"
            return []

    def get_children(self, key: Any) -> list[Any]:
        """Get all child keys for a registry key."""
        if not self.is_open or key is None:
            return []
        try:
            return self._hivex.node_children(key)
        except Exception:  # pylint: disable=broad-exception-caught  # hivex raises various undocumented exception types; treat any failure as "no children"
            return []

    def value_name(self, value: Any) -> str:
        """Get the name of a registry value."""
        return self._hivex.value_key(value)

    def value_data(self, value: Any) -> tuple[int, bytes] | None:
        """Get the raw data of a registry value as (type, bytes)."""
        try:
            return self._hivex.value_value(value)
        except Exception:  # pylint: disable=broad-exception-caught  # hivex raises various undocumented exception types; treat any failure as "no data"
            return None

    def decode_string(self, val_data: tuple[int, bytes]) -> str | None:
        """Decode a registry string value (REG_SZ) from raw data."""
        if not val_data or len(val_data) <= 1:
            return None
        try:
            return val_data[1].decode("utf-16-le", errors="ignore").split("\x00")[0] or None
        except (UnicodeDecodeError, IndexError):
            return None

    def decode_dword(self, val_data: tuple[int, bytes]) -> int | None:
        """Decode a DWORD value from raw data."""
        if not val_data or len(val_data) <= 1 or len(val_data[1]) < 4:
            return None
        try:
            return struct.unpack("<I", val_data[1][:4])[0]
        except struct.error:
            return None

    def read_string_value(self, path: list[str], value_name: str) -> str | None:
        """
        Navigate to a key and read a single string value.

        Args:
            path: Registry key path segments from root
            value_name: Name of the value to read

        Returns:
            Decoded string, or None if not found
        """
        key = self.navigate(path)
        if key is None:
            return None

        for val in self.get_values(key):
            if self.value_name(val) == value_name:
                data = self.value_data(val)
                return self.decode_string(data) if data else None
        return None

    def read_dword_value(self, path: list[str], value_name: str) -> int | None:
        """
        Navigate to a key and read a single DWORD value.

        Args:
            path: Registry key path segments from root
            value_name: Name of the value to read

        Returns:
            Integer value, or None if not found
        """
        key = self.navigate(path)
        if key is None:
            return None

        for val in self.get_values(key):
            if self.value_name(val) == value_name:
                data = self.value_data(val)
                return self.decode_dword(data) if data else None
        return None

    def read_all_string_values(self, path: list[str]) -> dict[str, str]:
        """
        Navigate to a key and read all string values as a dict.

        Args:
            path: Registry key path segments from root

        Returns:
            Dict of value_name -> decoded_string
        """
        key = self.navigate(path)
        if key is None:
            return {}

        result = {}
        for val in self.get_values(key):
            name = self.value_name(val)
            data = self.value_data(val)
            if data:
                decoded = self.decode_string(data)
                if decoded is not None:
                    result[name] = decoded
        return result
