# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Storage Stack Operations.

Provides LVM, crypto, and chroot command execution for VMCraft via composition.
Derived from StorageMixin (minus win_* and infrastructure methods).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from hyper2kvm.vmcraft._utils import run_sudo
from hyper2kvm.vmcraft.services import execute_chroot_command, execute_chroot_command_with_mounts
from hyper2kvm.vmcraft.storage import LVMActivator, LVMCreator


class StorageOps:
    """Storage stack operations via composition."""

    def __init__(self, host) -> None:
        self._host = host

    def vgscan(self) -> None:
        """Scan for LVM volume groups."""
        LVMActivator.activate(
            self._host.logger,
            # pylint: disable-next=protected-access  # StorageOps is a composed mixin; host internals by design
            nbd_device=self._host._nbd_device,
            container_isolation=getattr(self._host, "_container_isolation", True),
        )

    def vgchange_activate_all(self, enable: bool | int) -> None:
        """Activate all volume groups."""
        if enable:
            LVMActivator.activate(
                self._host.logger,
                # pylint: disable-next=protected-access  # StorageOps is a composed mixin; host internals by design
                nbd_device=self._host._nbd_device,
                container_isolation=getattr(self._host, "_container_isolation", True),
            )

    def lvs(self) -> list[str]:
        """List logical volumes (filtered to NBD device if available)."""
        return LVMActivator.list_logical_volumes(
            self._host.logger,
            # pylint: disable-next=protected-access  # StorageOps is a composed mixin; host internals by design
            nbd_device=self._host._nbd_device,
        )

    # LVM Creation APIs

    def pvcreate(self, devices: list[str]) -> dict[str, Any]:
        """
        Create physical volumes.

        Args:
            devices: List of device paths to initialize as PVs

        Returns:
            Audit dict with created PV list

        Example:
            result = g.pvcreate(["/dev/nbd0p1"])
        """
        return LVMCreator.pvcreate(self._host.logger, devices)

    def vgcreate(self, vgname: str, pvs: list[str]) -> dict[str, Any]:
        """
        Create volume group.

        Args:
            vgname: Volume group name
            pvs: List of physical volumes

        Returns:
            Audit dict with VG name

        Example:
            result = g.vgcreate("test_vg", ["/dev/nbd0p1"])
        """
        return LVMCreator.vgcreate(self._host.logger, vgname, pvs)

    def lvcreate(
        self, lvname: str, vgname: str, size_mb: int | None = None, extents: str | None = None
    ) -> dict[str, Any]:
        """
        Create logical volume.

        Args:
            lvname: Logical volume name
            vgname: Volume group name
            size_mb: Size in megabytes (mutually exclusive with extents)
            extents: Size in extents (e.g., "100%FREE")

        Returns:
            Audit dict with LV path

        Example:
            # Create LV with specific size
            result = g.lvcreate("data", "vg0", size_mb=1024)

            # Create LV using all free space
            result = g.lvcreate("data", "vg0", extents="100%FREE")
        """
        return LVMCreator.lvcreate(self._host.logger, lvname, vgname, size_mb, extents)

    def lvresize(self, lvpath: str, size_mb: int) -> dict[str, Any]:
        """
        Resize logical volume.

        Args:
            lvpath: LV device path (e.g., "/dev/vg0/data")
            size_mb: New size in megabytes

        Returns:
            Audit dict

        Example:
            result = g.lvresize("/dev/vg0/data", 2048)
        """
        return LVMCreator.lvresize(self._host.logger, lvpath, size_mb)

    def lvremove(self, lvpath: str, force: bool = False) -> dict[str, Any]:
        """
        Remove logical volume.

        Args:
            lvpath: LV device path
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = g.lvremove("/dev/vg0/data", force=True)
        """
        return LVMCreator.lvremove(self._host.logger, lvpath, force)

    def vgremove(self, vgname: str, force: bool = False) -> dict[str, Any]:
        """
        Remove volume group.

        Args:
            vgname: Volume group name
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = g.vgremove("vg0", force=True)
        """
        return LVMCreator.vgremove(self._host.logger, vgname, force)

    def cryptsetup_open(self, device: str, name: str, key: bytes) -> None:
        """Open LUKS encrypted device using host cryptsetup."""
        if not shutil.which("cryptsetup"):
            raise RuntimeError(
                "cryptsetup is not installed. Install it with: "
                "sudo dnf install cryptsetup (Fedora/RHEL) or sudo apt install cryptsetup (Debian/Ubuntu)"
            )

        # Close stale mapper if it exists from a previous failed run
        mapper = f"/dev/mapper/{name}"
        if os.path.exists(mapper):
            self._host.logger.info("LUKS: closing stale %s before re-open", name)
            # pylint: disable=duplicate-code
            # reason: this subprocess.run(...capture_output=True,
            # timeout=10) shape mirrors similar subprocess wrappers in
            # hyper2kvm/fixers/offline_fixer.py (lvs LVM scan) --
            # structurally similar by coincidence, not shared logic;
            # keeping independent avoids coupling unrelated
            # subprocess-invocation code paths.
            # Remove all dm devices (LVM LVs on top of LUKS, then LUKS itself)
            result = subprocess.run(
                ["dmsetup", "ls", "--target", "linear"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    dm_name = line.split()[0].strip() if line.split() else ""
                    if dm_name:
                        subprocess.run(
                            ["dmsetup", "remove", dm_name], capture_output=True, timeout=10, check=False
                        )
            subprocess.run(["cryptsetup", "close", name], capture_output=True, timeout=10, check=False)
            if os.path.exists(mapper):
                subprocess.run(
                    ["dmsetup", "remove", "-f", name], capture_output=True, timeout=10, check=False
                )

        self._host.logger.info("LUKS: opening %s as %s", device, name)
        proc = subprocess.run(
            ["cryptsetup", "open", "--type", "luks", device, name],
            input=key,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Failed to unlock LUKS encrypted device '{device}'. "
                f"The passphrase may be incorrect or the LUKS header may be damaged. "
                f"Detail: {err}"
            )
        self._host.logger.info("LUKS: opened %s -> /dev/mapper/%s", device, name)

    def command(self, cmd: list[str]) -> str:
        """Execute command in guest filesystem (via chroot)."""
        return self._run_chroot_command(cmd, quiet=False, with_mounts=False)

    def command_quiet(self, cmd: list[str]) -> str:
        """
        Execute command in guest filesystem (via chroot), but log failures as DEBUG only.
        Use this for commands that are expected to fail often (e.g., glob searches, bootloader commands).
        """
        return self._run_chroot_command(cmd, quiet=True, with_mounts=False)

    def command_with_mounts(self, cmd: list[str], quiet: bool = False) -> str:
        """
        Execute command in guest filesystem with /proc, /dev, /sys, /run bind-mounted.

        This provides a more complete chroot environment needed by bootloader tools
        like grub2-mkconfig and dracut, which require access to /proc/self/mountinfo,
        /dev, and /run.

        Args:
            cmd: Command to execute inside chroot
            quiet: If True, log failures at DEBUG level only

        Returns:
            Command stdout

        Raises:
            RuntimeError: If not launched or if command fails (when not quiet)
        """
        return self._run_chroot_command(cmd, quiet=quiet, with_mounts=True)

    def _run_chroot_command(self, cmd: list[str], quiet: bool, with_mounts: bool) -> str:
        """Run a command in chroot with optional bind mounts."""
        # pylint: disable-next=protected-access  # StorageOps is a composed mixin; host internals by design
        mount_root = self._host._require_mount_root()
        if with_mounts:
            return execute_chroot_command_with_mounts(
                self._host.logger,
                str(mount_root),
                cmd,
                run_sudo,
                quiet=quiet,
            )
        return execute_chroot_command(self._host.logger, str(mount_root), cmd, run_sudo, quiet=quiet)
