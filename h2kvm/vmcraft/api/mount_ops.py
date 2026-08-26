# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Mount Operations.

Provides mount/unmount methods for VMCraft via composition.
All methods delegate to the MountManager.
"""

from __future__ import annotations

from h2kvm.vmcraft.services import (
    get_mountpoints,
    get_mounts,
    mount_all_parallel as svc_mount_all_parallel,
    mount_ro,
    mount_rw,
    mount_with_fallback as svc_mount_with_fallback,
    mount_with_options,
    umount_all_and_clear_cache,
)


class MountOps:
    # pylint: disable=protected-access
    # MountOps is a composition helper deliberately paired with its host
    # VMCraft object; reaching into the host's _mount_manager/_file_ops/
    # _require_mount_manager() is the intended internal coupling for this
    # mixin-style delegation pattern, not an external API violation.
    """Mount operations via composition."""

    def __init__(self, host) -> None:
        self._host = host

    def mount(self, device: str, mountpoint: str) -> None:
        """Mount device at mountpoint (read-write)."""
        mount_rw(self._host.logger, self._host._require_mount_manager(), device, mountpoint)

    def mount_ro(self, device: str, mountpoint: str) -> None:
        """Mount device at mountpoint (read-only)."""
        mount_ro(self._host.logger, self._host._require_mount_manager(), device, mountpoint)

    def mount_options(self, options: str, device: str, mountpoint: str) -> None:
        """Mount device with custom options."""
        mount_with_options(self._host._require_mount_manager(), options, device, mountpoint)

    def umount_all(self) -> None:
        """Unmount all mounted filesystems."""
        umount_all_and_clear_cache(self._host._mount_manager, self._host._file_ops)

    def mountpoints(self) -> list[str]:
        """Get list of current mountpoints."""
        return get_mountpoints(self._host._mount_manager)

    def mounts(self) -> list[str]:
        """Get list of mounted devices."""
        return get_mounts(self._host._mount_manager)

    def mount_all_parallel(
        self, devices: list[tuple[str, str]], max_workers: int = 4, readonly: bool = True
    ) -> dict[str, bool]:
        """
        Mount multiple filesystems in parallel.

        Provides 2-3x performance improvement over sequential mounting when
        working with multi-partition VMs.

        Args:
            devices: List of (device, mountpoint) tuples
            max_workers: Maximum concurrent mount operations (default: 4)
            readonly: Mount in read-only mode (default: True)

        Returns:
            Dict mapping mountpoint to success status

        Example:
            devices = [
                ("/dev/nbd0p1", "/boot"),
                ("/dev/nbd0p2", "/"),
                ("/dev/nbd0p3", "/home"),
            ]
            results = g.mount_all_parallel(devices, max_workers=3)
        """
        return svc_mount_all_parallel(self._host._require_mount_manager(), devices, max_workers, readonly)

    def mount_with_fallback(self, device: str, mountpoint: str, fstype: str | None = None) -> bool:
        """
        Mount with automatic fallback to recovery modes.

        Useful for mounting potentially damaged or inconsistent filesystems.
        Tries progressively more permissive mount options.

        Args:
            device: Device path
            mountpoint: Mount point path
            fstype: Optional filesystem type (auto-detected if None)

        Returns:
            True if mount succeeded with any strategy

        Example:
            # Try to mount potentially damaged filesystem
            if g.mount_with_fallback("/dev/nbd0p1", "/"):
                print("Mounted successfully")
        """
        return svc_mount_with_fallback(self._host._require_mount_manager(), device, mountpoint, fstype)
