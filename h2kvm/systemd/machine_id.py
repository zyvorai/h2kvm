# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-machine-id-setup integration for machine ID management.

This module wraps systemd-machine-id-setup to initialize machine IDs
for migrated VMs to ensure uniqueness.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from h2kvm.systemd._common import check_systemd_binary_available


class SystemdMachineId:
    """
    Wrapper for systemd-machine-id-setup command-line tool.

    Provides machine ID initialization for migrated VMs to ensure
    each VM has a unique identifier.
    """

    def __init__(self, systemd_machine_id_setup: str = "systemd-machine-id-setup"):
        """
        Initialize systemd-machine-id-setup wrapper.

        Parameters
        ----------
        systemd_machine_id_setup : str, default="systemd-machine-id-setup"
            Path to systemd-machine-id-setup binary
        """
        self.binary = systemd_machine_id_setup
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-machine-id-setup is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-machine-id-setup",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def setup(
        self,
        *,
        root: Path | None = None,
        print_only: bool = False,
    ) -> str:
        """
        Initialize or update machine ID.

        Parameters
        ----------
        root : Path | None
            Root directory (default: system root)
        print_only : bool, default=False
            Only print ID without writing to disk

        Returns
        -------
        str
            Machine ID (128-bit hex string)

        Examples
        --------
        >>> machine_id = SystemdMachineId()
        >>> # Generate new ID for migrated VM
        >>> new_id = machine_id.setup(
        ...     root=Path("/mnt/migrated-vm"),
        ... )
        >>> print(f"New machine ID: {new_id}")
        """
        cmd = [self.binary]

        if root:
            cmd.extend(["--root", str(root)])
        if print_only:
            cmd.append("--print")

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # h2kvm/systemd/repart.py's size() -- coincidental, both just
        # capture their own binary's text output.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Extract machine ID from output
        output = result.stdout.strip()
        if output:
            # Return the ID (should be 32 hex chars)
            return output

        # If no output, read from file
        machine_id_file = root / "etc/machine-id" if root else Path("/etc/machine-id")

        if machine_id_file.exists():
            return machine_id_file.read_text(encoding="utf-8").strip()

        return ""

    def commit(self, *, root: Path | None = None) -> None:
        """
        Commit transient machine ID to disk.

        Parameters
        ----------
        root : Path | None
            Root directory (default: system root)

        Examples
        --------
        >>> machine_id = SystemdMachineId()
        >>> machine_id.commit(root=Path("/mnt/migrated-vm"))
        """
        cmd = [self.binary, "--commit"]

        if root:
            cmd.extend(["--root", str(root)])

        subprocess.run(cmd, check=True)

    def read(self, *, root: Path | None = None) -> str:
        """
        Read current machine ID.

        Parameters
        ----------
        root : Path | None
            Root directory (default: system root)

        Returns
        -------
        str
            Machine ID

        Examples
        --------
        >>> machine_id = SystemdMachineId()
        >>> current_id = machine_id.read(root=Path("/mnt/vm"))
        >>> print(f"Current ID: {current_id}")
        """
        machine_id_file = root / "etc/machine-id" if root else Path("/etc/machine-id")

        if not machine_id_file.exists():
            return ""

        return machine_id_file.read_text(encoding="utf-8").strip()

    def clear(self, *, root: Path | None = None) -> None:
        """
        Clear machine ID (prepare for cloning).

        Parameters
        ----------
        root : Path | None
            Root directory (default: system root)

        Examples
        --------
        >>> machine_id = SystemdMachineId()
        >>> # Clear ID before migration
        >>> machine_id.clear(root=Path("/mnt/source-vm"))
        """
        machine_id_file = root / "etc/machine-id" if root else Path("/etc/machine-id")

        if machine_id_file.exists():
            # Write empty file (will be regenerated on boot)
            machine_id_file.write_text("\n", encoding="utf-8")
