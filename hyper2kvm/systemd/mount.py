# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-mount integration for filesystem mounting.

This module wraps systemd-mount to mount/unmount filesystems
with automatic unit file generation.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from hyper2kvm.systemd._common import check_systemd_binary_available

if TYPE_CHECKING:
    from pathlib import Path


class SystemdMount:
    """
    Wrapper for systemd-mount command-line tool.

    Provides filesystem mounting with automatic systemd unit file
    generation for VM disk access.
    """

    def __init__(self, systemd_mount: str = "systemd-mount"):
        """
        Initialize systemd-mount wrapper.

        Parameters
        ----------
        systemd_mount : str, default="systemd-mount"
            Path to systemd-mount binary
        """
        self.binary = systemd_mount
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-mount is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-mount",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def mount(  # pylint: disable=too-many-arguments  # each option maps 1:1 to a systemd-mount CLI flag
        self,
        what: Path,
        where: Path | None = None,
        *,
        fs_type: str | None = None,
        options: str | None = None,
        owner: int | None = None,
        fsck: bool = True,
    ) -> str:
        """
        Mount filesystem.

        Parameters
        ----------
        what : Path
            What to mount (device or image file)
        where : Path | None
            Where to mount (auto-generated if None)
        fs_type : str | None
            Filesystem type (auto-detected if None)
        options : str | None
            Mount options (e.g., "ro,noexec")
        owner : int | None
            Owner UID for runtime directory
        fsck : bool, default=True
            Run fsck before mounting

        Returns
        -------
        str
            Mount point path

        Examples
        --------
        >>> mount = SystemdMount()
        >>> mountpoint = mount.mount(Path("/dev/sdb1"), options="ro")
        >>> print(f"Mounted at: {mountpoint}")
        """
        cmd = [self.binary]

        if fs_type:
            cmd.extend(["--type", fs_type])
        if options:
            cmd.extend(["--options", options])
        if owner is not None:
            cmd.extend(["--owner", str(owner)])
        if not fsck:
            cmd.append("--no-fsck")

        cmd.append(str(what))
        if where:
            cmd.append(str(where))

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # hyper2kvm/systemd/cryptenroll.py's enroll_recovery() and
        # hyper2kvm/systemd/delta.py's find_overrides() -- coincidental,
        # each just captures its own binary's text output.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse output to get mount point
        for line in result.stdout.splitlines():
            if "Mounted" in line or "mounted" in line:
                # Extract path from output
                parts = line.split()
                if len(parts) > 1:
                    return parts[-1].strip(".")

        return str(where) if where else ""

    def umount(self, what: Path) -> None:
        """
        Unmount filesystem.

        Parameters
        ----------
        what : Path
            What to unmount (device or mount point)

        Examples
        --------
        >>> mount = SystemdMount()
        >>> mount.umount(Path("/run/media/disk"))
        """
        subprocess.run(
            [self.binary, "--umount", str(what)],
            check=True,
        )

    def list(self) -> list[dict[str, str]]:
        """
        List active mounts managed by systemd.

        Returns
        -------
        list[dict[str, str]]
            List of mount information dicts

        Examples
        --------
        >>> mount = SystemdMount()
        >>> mounts = mount.list()
        >>> for m in mounts:
        ...     print(f"{m['what']} -> {m['where']}")
        """
        result = subprocess.run(
            [self.binary, "--list"],
            capture_output=True,
            text=True,
            check=True,
        )

        mounts = []
        lines = result.stdout.splitlines()

        # Skip header
        for line in lines[1:]:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 3:
                mounts.append(
                    {
                        "what": parts[0],
                        "where": parts[1],
                        "type": parts[2],
                    }
                )

        return mounts
