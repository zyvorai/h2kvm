# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-notify integration for service notifications.

This module wraps systemd-notify to send status updates and readiness
notifications when h2kvm runs as a systemd service.
"""

from __future__ import annotations

import subprocess

from h2kvm.systemd._common import check_systemd_binary_available


class SystemdNotify:
    """
    Wrapper for systemd-notify command-line tool.

    Sends status updates and readiness notifications to systemd
    when running as a service.
    """

    def __init__(self, systemd_notify: str = "systemd-notify"):
        """
        Initialize systemd-notify wrapper.

        Parameters
        ----------
        systemd_notify : str, default="systemd-notify"
            Path to systemd-notify binary
        """
        self.binary = systemd_notify
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-notify is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-notify",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def ready(self) -> None:
        """
        Notify systemd that service is ready.

        Examples
        --------
        >>> notify = SystemdNotify()
        >>> # After initialization complete
        >>> notify.ready()
        """
        subprocess.run(
            [self.binary, "--ready"],
            check=True,
        )

    def status(self, message: str) -> None:
        """
        Send status update to systemd.

        Parameters
        ----------
        message : str
            Status message

        Examples
        --------
        >>> notify = SystemdNotify()
        >>> notify.status("Migrating VM: web-server-01 (25%)")
        """
        subprocess.run(
            [self.binary, f"STATUS={message}"],
            check=True,
        )

    def stopping(self) -> None:
        """
        Notify systemd that service is stopping.

        Examples
        --------
        >>> notify = SystemdNotify()
        >>> notify.stopping()
        """
        subprocess.run(
            [self.binary, "STOPPING=1"],
            check=True,
        )

    def reloading(self) -> None:
        """
        Notify systemd that service is reloading.

        Examples
        --------
        >>> notify = SystemdNotify()
        >>> notify.reloading()
        """
        subprocess.run(
            [self.binary, "RELOADING=1"],
            check=True,
        )

    def watchdog(self) -> None:
        """
        Send watchdog keepalive ping.

        Examples
        --------
        >>> notify = SystemdNotify()
        >>> # In watchdog loop
        >>> notify.watchdog()
        """
        subprocess.run(
            [self.binary, "WATCHDOG=1"],
            check=True,
        )

    def mainpid(self, pid: int) -> None:
        """
        Send main PID to systemd.

        Parameters
        ----------
        pid : int
            Main process ID

        Examples
        --------
        >>> import os
        >>> notify = SystemdNotify()
        >>> notify.mainpid(os.getpid())
        """
        subprocess.run(
            [self.binary, f"MAINPID={pid}"],
            check=True,
        )

    def extend_timeout(self, microseconds: int) -> None:
        """
        Extend the service timeout.

        Parameters
        ----------
        microseconds : int
            Timeout extension in microseconds

        Examples
        --------
        >>> notify = SystemdNotify()
        >>> # Extend timeout by 30 seconds
        >>> notify.extend_timeout(30_000_000)
        """
        subprocess.run(
            [self.binary, f"EXTEND_TIMEOUT_USEC={microseconds}"],
            check=True,
        )
