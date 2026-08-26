# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-tmpfiles integration for temporary file management.

This module wraps systemd-tmpfiles to create, clean, and manage
temporary files and directories for VM migration tasks.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from h2kvm.systemd._common import check_systemd_binary_available

if TYPE_CHECKING:
    from pathlib import Path


class SystemdTmpfiles:
    """
    Wrapper for systemd-tmpfiles command-line tool.

    Provides temporary file/directory creation, cleanup, and management
    for VM migration artifacts.
    """

    def __init__(self, systemd_tmpfiles: str = "systemd-tmpfiles"):
        """
        Initialize systemd-tmpfiles wrapper.

        Parameters
        ----------
        systemd_tmpfiles : str, default="systemd-tmpfiles"
            Path to systemd-tmpfiles binary
        """
        self.binary = systemd_tmpfiles
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-tmpfiles is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-tmpfiles",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def create(
        self,
        *,
        prefix: str | None = None,
        config: Path | None = None,
        boot: bool = False,
    ) -> None:
        """
        Create files and directories from tmpfiles.d configuration.

        Parameters
        ----------
        prefix : str | None
            Only apply rules with specified prefix
        config : Path | None
            Specific configuration file to use
        boot : bool, default=False
            Apply boot-time rules only

        Examples
        --------
        >>> tmpfiles = SystemdTmpfiles()
        >>> tmpfiles.create(prefix="/run/h2kvm")
        """
        cmd = [self.binary, "--create"]

        if prefix:
            cmd.extend(["--prefix", prefix])
        if boot:
            cmd.append("--boot")
        if config:
            cmd.append(str(config))

        subprocess.run(cmd, check=True)

    def clean(
        self,
        *,
        prefix: str | None = None,
        config: Path | None = None,
    ) -> None:
        """
        Clean up temporary files and directories.

        Parameters
        ----------
        prefix : str | None
            Only clean paths with specified prefix
        config : Path | None
            Specific configuration file to use

        Examples
        --------
        >>> tmpfiles = SystemdTmpfiles()
        >>> tmpfiles.clean(prefix="/tmp/h2kvm")
        """
        cmd = [self.binary, "--clean"]

        if prefix:
            cmd.extend(["--prefix", prefix])
        if config:
            cmd.append(str(config))

        subprocess.run(cmd, check=True)

    def remove(
        self,
        *,
        prefix: str | None = None,
        config: Path | None = None,
    ) -> None:
        """
        Remove files and directories.

        Parameters
        ----------
        prefix : str | None
            Only remove paths with specified prefix
        config : Path | None
            Specific configuration file to use

        Examples
        --------
        >>> tmpfiles = SystemdTmpfiles()
        >>> tmpfiles.remove(prefix="/var/lib/h2kvm")
        """
        cmd = [self.binary, "--remove"]

        if prefix:
            cmd.extend(["--prefix", prefix])
        if config:
            cmd.append(str(config))

        subprocess.run(cmd, check=True)
