# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-vmspawn integration for VM spawning and testing.

This module wraps systemd-vmspawn to spawn QEMU/KVM VMs for testing
migrated disk images in full virtualization mode.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from h2kvm.systemd._common import check_systemd_binary_available

if TYPE_CHECKING:
    from pathlib import Path


class SystemdVmspawn:
    """
    Wrapper for systemd-vmspawn command-line tool.

    Provides VM spawning with QEMU/KVM for testing migrated disk images
    in full virtualization mode before production deployment.
    """

    def __init__(self, systemd_vmspawn: str = "systemd-vmspawn"):
        """
        Initialize systemd-vmspawn wrapper.

        Parameters
        ----------
        systemd_vmspawn : str, default="systemd-vmspawn"
            Path to systemd-vmspawn binary
        """
        self.binary = systemd_vmspawn
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-vmspawn is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-vmspawn",
            solutions=[
                "Install systemd-container (Debian/Ubuntu: apt install systemd-container)"
            ],
        )

    def spawn(  # pylint: disable=too-many-arguments  # each argument maps 1:1 to a distinct systemd-vmspawn CLI flag
        self,
        image: Path,
        *,
        cpus: int | None = None,
        memory: str | None = None,
        console: str = "interactive",
        network_user: bool = False,
        network_tap: str | None = None,
        kernel: Path | None = None,
        initrd: Path | None = None,
        kernel_cmdline: str | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Spawn VM from disk image.

        Parameters
        ----------
        image : Path
            Disk image file to boot
        cpus : int | None
            Number of CPUs (default: 1)
        memory : str | None
            Memory size (e.g., "2G", "512M")
        console : str, default="interactive"
            Console mode (interactive, read-only, passive, gui)
        network_user : bool, default=False
            Enable user-mode networking
        network_tap : str | None
            TAP interface name for networking
        kernel : Path | None
            Kernel image to boot
        initrd : Path | None
            Initrd image to use
        kernel_cmdline : str | None
            Kernel command line arguments

        Returns
        -------
        subprocess.CompletedProcess
            VM execution result

        Examples
        --------
        >>> vmspawn = SystemdVmspawn()
        >>> # Test migrated disk image
        >>> vmspawn.spawn(
        ...     Path("/var/lib/h2kvm/migrated-vm.qcow2"),
        ...     cpus=2,
        ...     memory="4G",
        ...     network_user=True,
        ... )
        """
        cmd = [self.binary]

        if cpus:
            cmd.extend(["--cpus", str(cpus)])
        if memory:
            cmd.extend(["--ram", memory])
        if console:
            cmd.extend(["--console", console])
        if network_user:
            cmd.append("--network-user-mode")
        if network_tap:
            cmd.extend(["--network-tap", network_tap])
        if kernel:
            cmd.extend(["--linux", str(kernel)])
        if initrd:
            cmd.extend(["--initrd", str(initrd)])
        if kernel_cmdline:
            cmd.extend(["--kernel-command-line", kernel_cmdline])

        cmd.append(str(image))

        return subprocess.run(cmd, check=True)

    def spawn_with_vsock(
        self,
        image: Path,
        cid: int,
        *,
        cpus: int | None = None,
        memory: str | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Spawn VM with vsock for host-guest communication.

        Parameters
        ----------
        image : Path
            Disk image file
        cid : int
            VSOCK context ID
        cpus : int | None
            Number of CPUs
        memory : str | None
            Memory size

        Returns
        -------
        subprocess.CompletedProcess
            VM execution result

        Examples
        --------
        >>> vmspawn = SystemdVmspawn()
        >>> vmspawn.spawn_with_vsock(
        ...     Path("/var/lib/h2kvm/vm.qcow2"),
        ...     cid=3,
        ...     memory="2G",
        ... )
        """
        cmd = [self.binary, "--vsock", str(cid)]

        if cpus:
            cmd.extend(["--cpus", str(cpus)])
        if memory:
            cmd.extend(["--ram", memory])

        cmd.append(str(image))

        return subprocess.run(cmd, check=True)

    def spawn_with_tpm(
        self,
        image: Path,
        *,
        cpus: int | None = None,
        memory: str | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Spawn VM with TPM emulation.

        Parameters
        ----------
        image : Path
            Disk image file
        cpus : int | None
            Number of CPUs
        memory : str | None
            Memory size

        Returns
        -------
        subprocess.CompletedProcess
            VM execution result

        Examples
        --------
        >>> vmspawn = SystemdVmspawn()
        >>> # Test LUKS TPM auto-unlock
        >>> vmspawn.spawn_with_tpm(
        ...     Path("/var/lib/h2kvm/encrypted-vm.qcow2"),
        ...     memory="4G",
        ... )
        """
        cmd = [self.binary, "--tpm"]

        if cpus:
            cmd.extend(["--cpus", str(cpus)])
        if memory:
            cmd.extend(["--ram", memory])

        cmd.append(str(image))

        return subprocess.run(cmd, check=True)

    def spawn_secure_boot(
        self,
        image: Path,
        *,
        firmware: Path | None = None,
        cpus: int | None = None,
        memory: str | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Spawn VM with UEFI Secure Boot.

        Parameters
        ----------
        image : Path
            Disk image file
        firmware : Path | None
            UEFI firmware path (default: auto-detect)
        cpus : int | None
            Number of CPUs
        memory : str | None
            Memory size

        Returns
        -------
        subprocess.CompletedProcess
            VM execution result

        Examples
        --------
        >>> vmspawn = SystemdVmspawn()
        >>> # Test secure boot
        >>> vmspawn.spawn_secure_boot(
        ...     Path("/var/lib/h2kvm/vm.qcow2"),
        ...     memory="2G",
        ... )
        """
        cmd = [self.binary, "--secure-boot"]

        if firmware:
            cmd.extend(["--firmware", str(firmware)])
        if cpus:
            cmd.extend(["--cpus", str(cpus)])
        if memory:
            cmd.extend(["--ram", memory])

        cmd.append(str(image))

        return subprocess.run(cmd, check=True)
