# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/windows_registry.py
"""
Windows registry operations.

Provides read/write access to Windows registry hives using hivex tools:
- Read registry values (hivexget)
- Write registry values (hivexregedit)
- List registry keys and values
- Case-insensitive path resolution

Supports all standard hives:
- SOFTWARE (installed software, Windows version, etc.)
- SYSTEM (hardware, drivers, services)
- SAM (user accounts)
- SECURITY (security policy)
- DEFAULT (default user profile)
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ._utils import run_sudo

logger = logging.getLogger(__name__)


class WindowsRegistryManager:
    """
    Windows registry hive manager.

    Provides read/write access to Windows registry using hivex tools.
    """

    def __init__(self, manager_logger: logging.Logger, mount_root: Path):
        """
        Initialize registry manager.

        Args:
            manager_logger: Logger instance
            mount_root: Root directory where Windows filesystem is mounted
        """
        self.logger = manager_logger
        self.mount_root = mount_root

    def _find_hive_file(self, hive_name: str) -> Path | None:
        """
        Find registry hive file (case-insensitive).

        Args:
            hive_name: Hive name (SOFTWARE, SYSTEM, SAM, etc.)

        Returns:
            Path to hive file or None if not found
        """
        for try_path in [
            f"Windows/System32/config/{hive_name}",
            f"windows/system32/config/{hive_name.lower()}",
            f"Windows/System32/Config/{hive_name}",
        ]:
            test_path = self.mount_root / try_path
            if test_path.exists():
                return test_path

        return None

    def read_value(self, hive_name: str, key_path: str, value_name: str) -> str | None:
        """
        Read value from Windows registry hive.

        Args:
            hive_name: Registry hive (SOFTWARE, SYSTEM, SAM, etc.)
            key_path: Registry key path (e.g., "Microsoft\\Windows NT\\CurrentVersion")
            value_name: Value name to read

        Returns:
            Value string or None if not found

        Example:
            value = registry.read_value("SOFTWARE", "Microsoft\\Windows NT\\CurrentVersion", "ProductName")
        """
        hive_file = self._find_hive_file(hive_name)
        if not hive_file:
            self.logger.warning(f"Registry hive not found: {hive_name}")
            return None

        try:
            # Use hivexget to read registry value
            result = run_sudo(
                self.logger, ["hivexget", str(hive_file), key_path, value_name], check=True, capture=True
            )
            value = result.stdout.strip().strip('"')
            return value if value else None

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.logger.debug(f"Failed to read registry value {hive_name}\\{key_path}\\{value_name}: {e}")
            return None

    def write_value(  # pylint: disable=unused-argument  # value_type is public API, reserved for future dword/multi-sz support; only sz is implemented today
        self, hive_name: str, key_path: str, value_name: str, value: str, value_type: str = "sz"
    ) -> bool:
        """
        Write value to Windows registry hive.

        Args:
            hive_name: Registry hive (SOFTWARE, SYSTEM, etc.)
            key_path: Registry key path
            value_name: Value name to write
            value: Value to write
            value_type: Value type (sz=string, dword=32-bit int, etc.)

        Returns:
            True if successful

        Example:
            ok = registry.write_value("SOFTWARE", "Microsoft\\MyApp", "Version", "1.0")
        """
        hive_file = self._find_hive_file(hive_name)
        if not hive_file:
            self.logger.warning(f"Registry hive not found: {hive_name}")
            return False

        try:
            # Use hivexregedit to write registry value
            # Create a temporary reg file with the change
            reg_content = f"""Windows Registry Editor Version 5.00

[{key_path}]
"{value_name}"="{value}"
"""
            with tempfile.NamedTemporaryFile(mode="w", suffix=".reg", delete=False) as f:
                f.write(reg_content)
                reg_file = f.name

            try:
                # Apply registry changes using hivexregedit
                run_sudo(
                    self.logger,
                    ["hivexregedit", "--merge", str(hive_file), reg_file],
                    check=True,
                    capture=True,
                )
                self.logger.info(f"Updated registry: {hive_name}\\{key_path}\\{value_name}")
                return True

            finally:
                Path(reg_file).unlink(missing_ok=True)

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.logger.exception(f"Failed to write registry value: {e}")
            return False

    def list_keys(self, hive_name: str, key_path: str = "") -> list[str]:
        """
        List subkeys under a registry key.

        Args:
            hive_name: Registry hive name
            key_path: Registry key path (empty for root)

        Returns:
            List of subkey names

        Example:
            keys = registry.list_keys("SOFTWARE", "Microsoft")
        """
        hive_file = self._find_hive_file(hive_name)
        if not hive_file:
            return []

        try:
            # Use hivexsh to list keys
            script = f"cd {key_path}\nls\nquit\n" if key_path else "ls\nquit\n"

            with tempfile.NamedTemporaryFile(mode="w", suffix=".hivexsh", delete=False) as f:
                f.write(script)
                script_file = f.name

            try:
                result = run_sudo(
                    self.logger, ["hivexsh", "-f", script_file, str(hive_file)], check=True, capture=True
                )

                # Parse output (skip hivexsh> prompts)
                keys = []
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and not line.startswith("hivexsh>"):
                        keys.append(line)

                return keys

            finally:
                Path(script_file).unlink(missing_ok=True)

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.logger.debug(f"Failed to list registry keys: {e}")
            return []

    def list_values(self, hive_name: str, key_path: str) -> dict[str, Any]:
        """
        List values under a registry key.

        Args:
            hive_name: Registry hive name
            key_path: Registry key path

        Returns:
            Dict of value names to their data

        Example:
            values = registry.list_values("SOFTWARE", "Microsoft\\Windows NT\\CurrentVersion")
        """
        hive_file = self._find_hive_file(hive_name)
        if not hive_file:
            return {}

        try:
            # Use hivexsh to list values
            script = f"cd {key_path}\nlsval\nquit\n"

            with tempfile.NamedTemporaryFile(mode="w", suffix=".hivexsh", delete=False) as f:
                f.write(script)
                script_file = f.name

            try:
                result = run_sudo(
                    self.logger, ["hivexsh", "-f", script_file, str(hive_file)], check=True, capture=True
                )

                # Parse output
                values = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and not line.startswith("hivexsh>") and "=" in line:
                        # Format: "ValueName"=type:value
                        name, data = line.split("=", 1)
                        name = name.strip('"')
                        values[name] = data.strip()

                return values

            finally:
                Path(script_file).unlink(missing_ok=True)

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.logger.debug(f"Failed to list registry values: {e}")
            return {}

    def resolve_path(self, path: str) -> Path | None:
        """
        Resolve Windows path (case-insensitive).

        Args:
            path: Windows-style path (e.g., "C:\\Windows\\System32\\drivers")

        Returns:
            Resolved Path object or None if not found

        Example:
            driver_path = registry.resolve_path("C:\\Windows\\System32\\drivers\\mydriver.sys")
        """
        # Strip drive letter if present
        if len(path) >= 2 and path[1] == ":":
            path = path[3:]  # Remove "C:\"

        # Convert backslashes to forward slashes
        path = path.replace("\\", "/")

        # Try exact path first
        full_path = self.mount_root / path
        if full_path.exists():
            return full_path

        # Try case-insensitive search
        parts = Path(path).parts
        current = self.mount_root

        for part in parts:
            if not current.is_dir():
                return None

            # Look for matching entry (case-insensitive)
            found = False
            try:
                for entry in current.iterdir():
                    if entry.name.lower() == part.lower():
                        current = entry
                        found = True
                        break
            except (PermissionError, OSError):
                return None

            if not found:
                return None

        return current if current.exists() else None
