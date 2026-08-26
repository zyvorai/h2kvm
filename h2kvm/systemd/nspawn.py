# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-nspawn integration for container-based VM testing.

This module wraps systemd-nspawn to spawn containers for testing
migrated VM images before full deployment.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from h2kvm.core.exceptions import SystemdError

if TYPE_CHECKING:
    from pathlib import Path


class SystemdNspawn:
    """
    Wrapper for systemd-nspawn command-line tool.

    Provides lightweight container spawning for testing migrated
    VM images before deploying to production KVM.
    """

    def __init__(self, systemd_nspawn: str = "systemd-nspawn"):
        """
        Initialize systemd-nspawn wrapper.

        Parameters
        ----------
        systemd_nspawn : str, default="systemd-nspawn"
            Path to systemd-nspawn binary
        """
        self.binary = systemd_nspawn
        self._check_available()

    def _check_available(self) -> None:
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent binary-availability check in
        # h2kvm/systemd/path.py (and other systemd/*.py wrappers) -- shared shape
        # across the whole systemd/ package, kept independent per-tool since binary
        # name and remediation hints differ.
        """Check if systemd-nspawn is available."""
        try:
            subprocess.run(
                [self.binary, "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            msg = f"systemd-nspawn not available: {e}"
            raise SystemdError(code=127, msg=msg).with_context(
                solutions=["Install systemd-container (Debian/Ubuntu: apt install systemd-container)"]
            ) from e

    def spawn(  # pylint: disable=too-many-arguments  # many independent nspawn CLI flags map 1:1 to parameters
        self,
        directory: Path,
        *,
        boot: bool = False,
        ephemeral: bool = False,
        read_only: bool = False,
        network_veth: bool = False,
        bind: list[str] | None = None,
        command: list[str] | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Spawn container from directory.

        Parameters
        ----------
        directory : Path
            Root directory for container
        boot : bool, default=False
            Boot the container (run init system)
        ephemeral : bool, default=False
            Run in ephemeral mode (temporary copy)
        read_only : bool, default=False
            Mount root filesystem read-only
        network_veth : bool, default=False
            Create virtual Ethernet link
        bind : list[str] | None
            Bind mount paths (format: "source:dest")
        command : list[str] | None
            Command to run (default: shell)

        Returns
        -------
        subprocess.CompletedProcess
            Container execution result

        Examples
        --------
        >>> nspawn = SystemdNspawn()
        >>> # Test migrated VM in ephemeral container
        >>> nspawn.spawn(
        ...     Path("/var/lib/machines/test-vm"),
        ...     ephemeral=True,
        ...     boot=True,
        ...     network_veth=True,
        ... )
        """
        cmd = [self.binary]

        if boot:
            cmd.append("--boot")
        if ephemeral:
            cmd.append("--ephemeral")
        if read_only:
            cmd.append("--read-only")
        if network_veth:
            cmd.append("--network-veth")

        if bind:
            for bind_spec in bind:
                cmd.extend(["--bind", bind_spec])

        cmd.extend(["--directory", str(directory)])

        if command:
            cmd.extend(["--", *command])

        return subprocess.run(cmd, check=True)

    def spawn_image(
        self,
        image: Path,
        *,
        boot: bool = False,
        ephemeral: bool = False,
        read_only: bool = False,
        network_veth: bool = False,
    ) -> subprocess.CompletedProcess:
        """
        Spawn container from disk image.

        Parameters
        ----------
        image : Path
            Disk image file (.raw, .qcow2, etc.)
        boot : bool, default=False
            Boot the container
        ephemeral : bool, default=False
            Run in ephemeral mode
        read_only : bool, default=False
            Mount read-only
        network_veth : bool, default=False
            Create virtual network

        Returns
        -------
        subprocess.CompletedProcess
            Container execution result

        Examples
        --------
        >>> nspawn = SystemdNspawn()
        >>> # Test migrated disk image
        >>> nspawn.spawn_image(
        ...     Path("/var/lib/h2kvm/migrated-vm.raw"),
        ...     ephemeral=True,
        ...     boot=True,
        ... )
        """
        cmd = [self.binary]

        if boot:
            cmd.append("--boot")
        if ephemeral:
            cmd.append("--ephemeral")
        if read_only:
            cmd.append("--read-only")
        if network_veth:
            cmd.append("--network-veth")

        cmd.extend(["--image", str(image)])

        return subprocess.run(cmd, check=True)

    def shell(
        self,
        directory: Path,
        *,
        user: str | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Open shell in container.

        Parameters
        ----------
        directory : Path
            Container root directory
        user : str | None
            User to run shell as

        Returns
        -------
        subprocess.CompletedProcess
            Shell execution result

        Examples
        --------
        >>> nspawn = SystemdNspawn()
        >>> # Interactive shell in migrated VM
        >>> nspawn.shell(Path("/var/lib/machines/vm"), user="root")
        """
        cmd = [self.binary, "--directory", str(directory)]

        if user:
            cmd.extend(["--user", user])

        return subprocess.run(cmd, check=True)
