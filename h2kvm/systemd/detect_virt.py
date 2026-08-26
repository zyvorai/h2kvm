# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-detect-virt integration for virtualization detection.

This module wraps systemd-detect-virt to detect the virtualization
environment and hypervisor type.
"""

from __future__ import annotations

import subprocess
from enum import Enum

from h2kvm.systemd._common import check_systemd_binary_available


class VirtType(str, Enum):
    """Virtualization types detected by systemd-detect-virt."""

    # Full VMs
    QEMU = "qemu"
    KVM = "kvm"
    AMAZON = "amazon"
    ZXEN = "zxen"
    XEN = "xen"
    BOCHS = "bochs"
    UML = "uml"
    VMWARE = "vmware"
    ORACLE = "oracle"  # VirtualBox
    MICROSOFT = "microsoft"  # Hyper-V
    PARALLELS = "parallels"
    BHYVE = "bhyve"
    QNX = "qnx"
    ACRN = "acrn"
    APPLE = "apple"  # Apple Virtualization.Framework

    # Containers
    OPENVZ = "openvz"
    LXC = "lxc"
    LXC_LIBVIRT = "lxc-libvirt"
    SYSTEMD_NSPAWN = "systemd-nspawn"
    DOCKER = "docker"
    PODMAN = "podman"
    RKT = "rkt"
    WSL = "wsl"
    PROOT = "proot"
    POUCH = "pouch"

    # Special
    NONE = "none"
    UNKNOWN = "unknown"


class SystemdDetectVirt:
    """
    Wrapper for systemd-detect-virt command-line tool.

    Detects execution in a virtualized environment and identifies
    the virtualization technology.
    """

    def __init__(self, systemd_detect_virt: str = "systemd-detect-virt"):
        """
        Initialize systemd-detect-virt wrapper.

        Parameters
        ----------
        systemd_detect_virt : str, default="systemd-detect-virt"
            Path to systemd-detect-virt binary
        """
        self.binary = systemd_detect_virt
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-detect-virt is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-detect-virt",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def detect(self, *, quiet: bool = False) -> VirtType:
        """
        Detect virtualization environment.

        Parameters
        ----------
        quiet : bool, default=False
            Run in quiet mode (no output, just exit code)

        Returns
        -------
        VirtType
            Detected virtualization type

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> virt_type = detector.detect()
        >>> if virt_type == VirtType.KVM:
        ...     print("Running in KVM")
        """
        cmd = [self.binary]
        if quiet:
            cmd.append("--quiet")

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # h2kvm/systemd/repart.py's verify() -- coincidental, both
        # just capture their own binary's text output without raising on
        # non-zero exit.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        # Exit code indicates virtualization detected
        if result.returncode != 0:
            return VirtType.NONE

        # Parse output to get specific type
        virt_name = result.stdout.strip()

        try:
            return VirtType(virt_name)
        except ValueError:
            return VirtType.UNKNOWN

    def is_virtualized(self) -> bool:
        """
        Check if running in any virtualized environment.

        Returns
        -------
        bool
            True if virtualized, False otherwise

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> if detector.is_virtualized():
        ...     print("Running in VM or container")
        """
        result = subprocess.run(
            [self.binary, "--quiet"],
            capture_output=True,
            check=False,
        )

        return result.returncode == 0

    def is_vm(self) -> bool:
        """
        Check if running in a full VM (not container).

        Returns
        -------
        bool
            True if running in VM, False otherwise

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> if detector.is_vm():
        ...     print("Running in full VM")
        """
        result = subprocess.run(
            [self.binary, "--vm", "--quiet"],
            capture_output=True,
            check=False,
        )

        return result.returncode == 0

    def is_container(self) -> bool:
        """
        Check if running in a container.

        Returns
        -------
        bool
            True if running in container, False otherwise

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> if detector.is_container():
        ...     print("Running in container")
        """
        result = subprocess.run(
            [self.binary, "--container", "--quiet"],
            capture_output=True,
            check=False,
        )

        return result.returncode == 0

    def is_chroot(self) -> bool:
        """
        Check if running in a chroot environment.

        Returns
        -------
        bool
            True if running in chroot, False otherwise

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> if detector.is_chroot():
        ...     print("Running in chroot")
        """
        result = subprocess.run(
            [self.binary, "--chroot", "--quiet"],
            capture_output=True,
            check=False,
        )

        return result.returncode == 0

    def list_types(self) -> list[str]:
        """
        List all detectable virtualization types.

        Returns
        -------
        list[str]
            List of virtualization type names

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> types = detector.list_types()
        >>> print(types)
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) + return shape in
        # h2kvm/systemd/inhibit.py's list() -- coincidental, both just
        # capture and return their own binary's text output.
        result = subprocess.run(
            [self.binary, "--list"],
            capture_output=True,
            text=True,
            check=True,
        )

        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def get_hypervisor_name(self) -> str:
        """
        Get human-readable hypervisor name.

        Returns
        -------
        str
            Hypervisor name (e.g., "VMware", "KVM", "Hyper-V")

        Examples
        --------
        >>> detector = SystemdDetectVirt()
        >>> print(f"Running on: {detector.get_hypervisor_name()}")
        """
        virt_type = self.detect()

        name_map = {
            VirtType.VMWARE: "VMware",
            VirtType.KVM: "KVM",
            VirtType.QEMU: "QEMU",
            VirtType.MICROSOFT: "Hyper-V",
            VirtType.ORACLE: "VirtualBox",
            VirtType.XEN: "Xen",
            VirtType.AMAZON: "Amazon EC2",
            VirtType.PARALLELS: "Parallels",
            VirtType.BHYVE: "bhyve",
            VirtType.APPLE: "Apple Virtualization",
            VirtType.DOCKER: "Docker",
            VirtType.PODMAN: "Podman",
            VirtType.LXC: "LXC",
            VirtType.SYSTEMD_NSPAWN: "systemd-nspawn",
            VirtType.NONE: "None (Bare Metal)",
        }

        return name_map.get(virt_type, virt_type.value.title())
