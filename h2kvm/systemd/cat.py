# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-cat integration for logging to systemd journal.

This module wraps systemd-cat to send migration logs to the systemd journal
for better integration with system logging.
"""

from __future__ import annotations

import subprocess

from h2kvm.systemd._common import check_systemd_binary_available


class SystemdCat:
    """
    Wrapper for systemd-cat command-line tool.

    Provides logging to systemd journal for better integration
    with system logging and monitoring.
    """

    def __init__(self, systemd_cat: str = "systemd-cat"):
        """
        Initialize systemd-cat wrapper.

        Parameters
        ----------
        systemd_cat : str, default="systemd-cat"
            Path to systemd-cat binary
        """
        self.binary = systemd_cat
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-cat is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-cat",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def log(
        self,
        message: str,
        *,
        identifier: str = "h2kvm",
        priority: int = 6,  # Info level
        level_prefix: bool = True,
    ) -> None:
        """
        Send message to systemd journal.

        Parameters
        ----------
        message : str
            Message to log
        identifier : str, default="h2kvm"
            Syslog identifier
        priority : int, default=6
            Syslog priority (0=emerg, 3=err, 6=info, 7=debug)
        level_prefix : bool, default=True
            Parse log level prefixes

        Examples
        --------
        >>> cat = SystemdCat()
        >>> cat.log("Migration started", priority=6)
        >>> cat.log("Migration failed", priority=3)
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the identifier/priority cmd-building shape in
        # h2kvm/systemd/inhibit.py's run() -- coincidental, each
        # method builds its own tool's CLI flags independently.
        cmd = [
            self.binary,
            "--identifier",
            identifier,
            "--priority",
            str(priority),
        ]

        if level_prefix:
            cmd.append("--level-prefix=true")
        else:
            cmd.append("--level-prefix=false")

        subprocess.run(
            cmd,
            input=message.encode(),
            check=True,
        )

    def run(
        self,
        command: list[str],
        *,
        identifier: str = "h2kvm",
        priority: int = 6,
    ) -> subprocess.CompletedProcess:
        """
        Run command and log output to journal.

        Parameters
        ----------
        command : list[str]
            Command to run
        identifier : str, default="h2kvm"
            Syslog identifier
        priority : int, default=6
            Syslog priority

        Returns
        -------
        subprocess.CompletedProcess
            Command result

        Examples
        --------
        >>> cat = SystemdCat()
        >>> result = cat.run(
        ...     ["qemu-img", "info", "disk.img"], identifier="vm-migration", priority=6
        ... )
        """
        cmd = [
            self.binary,
            "--identifier",
            identifier,
            "--priority",
            str(priority),
            "--",
            *command,
        ]

        return subprocess.run(cmd, check=True)
