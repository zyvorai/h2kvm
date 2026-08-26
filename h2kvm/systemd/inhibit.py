# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-inhibit integration for preventing system sleep/shutdown.

This module wraps systemd-inhibit to prevent system sleep, shutdown, or idle
during long-running VM migration operations.
"""

from __future__ import annotations

import subprocess

from h2kvm.systemd._common import check_systemd_binary_available


class SystemdInhibit:
    """
    Wrapper for systemd-inhibit command-line tool.

    Prevents system sleep, shutdown, or idle during migration operations
    to ensure migrations complete successfully.
    """

    def __init__(self, systemd_inhibit: str = "systemd-inhibit"):
        """
        Initialize systemd-inhibit wrapper.

        Parameters
        ----------
        systemd_inhibit : str, default="systemd-inhibit"
            Path to systemd-inhibit binary
        """
        self.binary = systemd_inhibit
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-inhibit is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-inhibit",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def run(
        self,
        command: list[str],
        *,
        what: str = "idle:sleep:shutdown",
        who: str = "h2kvm",
        why: str = "VM migration in progress",
        mode: str = "block",
    ) -> subprocess.CompletedProcess:
        """
        Run command with inhibitor lock.

        Parameters
        ----------
        command : list[str]
            Command to run with inhibitor
        what : str, default="idle:sleep:shutdown"
            What to inhibit (idle, sleep, shutdown, handle-power-key, etc.)
        who : str, default="h2kvm"
            Name of program taking lock
        why : str, default="VM migration in progress"
            Reason for lock
        mode : str, default="block"
            Lock mode (block or delay)

        Returns
        -------
        subprocess.CompletedProcess
            Command result

        Examples
        --------
        >>> inhibit = SystemdInhibit()
        >>> result = inhibit.run(
        ...     ["qemu-img", "convert", "input.vmdk", "output.qcow2"],
        ...     why="Disk conversion in progress",
        ... )
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the identifier/priority cmd-building shape in
        # h2kvm/systemd/cat.py's log() -- coincidental, each method
        # builds its own tool's CLI flags independently.
        cmd = [
            self.binary,
            "--what",
            what,
            "--who",
            who,
            "--why",
            why,
            "--mode",
            mode,
            "--",
            *command,
        ]

        return subprocess.run(cmd, check=True)

    def list(self) -> str:
        """
        List active inhibitor locks.

        Returns
        -------
        str
            List of inhibitors

        Examples
        --------
        >>> inhibit = SystemdInhibit()
        >>> locks = inhibit.list()
        >>> print(locks)
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) + return shape in
        # h2kvm/systemd/detect_virt.py's list_types() -- coincidental,
        # both just capture and return their own binary's text output.
        result = subprocess.run(
            [self.binary, "--list"],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout
