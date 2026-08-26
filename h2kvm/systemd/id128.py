# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-id128 integration for 128-bit ID generation.

This module wraps systemd-id128 to generate unique 128-bit identifiers
for VMs, volumes, and other migration artifacts.
"""

from __future__ import annotations

import subprocess

from h2kvm.systemd._common import check_systemd_binary_available


class SystemdId128:
    """
    Wrapper for systemd-id128 command-line tool.

    Provides 128-bit UUID generation for VM identification
    and volume labeling during migration.
    """

    def __init__(self, systemd_id128: str = "systemd-id128"):
        """
        Initialize systemd-id128 wrapper.

        Parameters
        ----------
        systemd_id128 : str, default="systemd-id128"
            Path to systemd-id128 binary
        """
        self.binary = systemd_id128
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-id128 is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-id128",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def new(self) -> str:
        """
        Generate new random 128-bit ID.

        Returns
        -------
        str
            128-bit ID as hex string

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> vm_id = id128.new()
        >>> print(f"New VM ID: {vm_id}")
        """
        result = subprocess.run(
            [self.binary, "new"],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    def machine_id(self) -> str:
        """
        Get current machine ID.

        Returns
        -------
        str
            Machine ID

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> machine_id = id128.machine_id()
        >>> print(f"Machine ID: {machine_id}")
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) + return shape in
        # h2kvm/systemd/escape.py's systemd_unescape() -- coincidental,
        # both just capture and strip their own binary's text output.
        result = subprocess.run(
            [self.binary, "machine-id"],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    def boot_id(self) -> str:
        """
        Get current boot ID.

        Returns
        -------
        str
            Boot ID

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> boot_id = id128.boot_id()
        >>> print(f"Boot ID: {boot_id}")
        """
        result = subprocess.run(
            [self.binary, "boot-id"],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    def invocation_id(self) -> str:
        """
        Get current invocation ID (if running in systemd service).

        Returns
        -------
        str
            Invocation ID

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> try:
        ...     inv_id = id128.invocation_id()
        ...     print(f"Invocation ID: {inv_id}")
        ... except subprocess.CalledProcessError:
        ...     print("Not running in systemd service")
        """
        result = subprocess.run(
            [self.binary, "invocation-id"],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    def show(self, id128_str: str) -> dict[str, str]:
        """
        Show information about a 128-bit ID.

        Parameters
        ----------
        id128_str : str
            128-bit ID to show

        Returns
        -------
        dict[str, str]
            ID information

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> vm_id = id128.new()
        >>> info = id128.show(vm_id)
        >>> print(info)
        """
        result = subprocess.run(
            [self.binary, "show", id128_str],
            capture_output=True,
            text=True,
            check=True,
        )

        info = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key.strip()] = value.strip()

        return info

    def generate_vm_id(self) -> str:
        """
        Generate unique VM identifier.

        Returns
        -------
        str
            VM ID

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> vm_id = id128.generate_vm_id()
        >>> print(f"VM ID: {vm_id}")
        """
        return self.new()

    def generate_volume_id(self) -> str:
        """
        Generate unique volume identifier.

        Returns
        -------
        str
            Volume ID

        Examples
        --------
        >>> id128 = SystemdId128()
        >>> vol_id = id128.generate_volume_id()
        >>> print(f"Volume ID: {vol_id}")
        """
        return self.new()
