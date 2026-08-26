# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Mount operation helpers for VMCraft."""

from __future__ import annotations

import logging


class MountManagerProtocol:  # pylint: disable=unused-argument
    # Structural protocol describing the mount-manager interface VMCraft's
    # host object implements; parameter names/signatures here must match
    # the real implementation. Method bodies are intentionally empty
    # (stub declarations, not implementations).
    """Structural interface for the mount-manager object VMCraft composes with."""

    def mount(
        self,
        device: str,
        mountpoint: str,
        *,
        readonly: bool = False,
        options: str | None = None,
        failure_log_level: int | None = None,
    ) -> None:
        """Mount device at mountpoint with the given options."""

    def umount_all(self) -> None:
        """Unmount all filesystems managed by this mount manager."""

    def mountpoints(self) -> list[str]:
        """Return the list of currently active mountpoints."""

    def mounts(self) -> list[str]:
        """Return the list of currently mounted devices."""

    def mount_all_parallel(
        self, devices: list[tuple[str, str]], max_workers: int = 4, readonly: bool = True
    ) -> dict[str, bool]:
        """Mount multiple (device, mountpoint) pairs concurrently."""

    def mount_with_fallback(self, device: str, mountpoint: str, fstype: str | None = None) -> bool:
        """Mount device, retrying with progressively more permissive options on failure."""


class FileOpsProtocol:  # pylint: disable=unused-argument,too-few-public-methods
    # Structural protocol describing the file-ops interface VMCraft's host
    # object implements; the method body is intentionally empty (stub
    # declaration, not an implementation). Only one method is needed by
    # this protocol's consumers.
    """Structural interface for the file-ops object VMCraft composes with."""

    def clear_cache(self) -> None:
        """Clear any cached filesystem state."""


def _mount_with_debug(
    mount_manager: MountManagerProtocol,
    device: str,
    mountpoint: str,
    *,
    readonly: bool,
) -> None:
    """Mount helper with standardized debug failure logging."""
    mount_manager.mount(device, mountpoint, readonly=readonly, failure_log_level=logging.DEBUG)


def _manager_list(mount_manager: MountManagerProtocol | None, method_name: str) -> list[str]:
    """Safely call a list-returning mount manager method."""
    if not mount_manager:
        return []
    return getattr(mount_manager, method_name)()


def mount_rw(
    _logger: logging.Logger, mount_manager: MountManagerProtocol, device: str, mountpoint: str
) -> None:
    """Mount device at mountpoint in read-write mode."""
    _mount_with_debug(mount_manager, device, mountpoint, readonly=False)


def mount_ro(
    _logger: logging.Logger, mount_manager: MountManagerProtocol, device: str, mountpoint: str
) -> None:
    """Mount device at mountpoint in read-only mode."""
    _mount_with_debug(mount_manager, device, mountpoint, readonly=True)


def mount_with_options(
    mount_manager: MountManagerProtocol, options: str, device: str, mountpoint: str
) -> None:
    """Mount device with custom options."""
    mount_manager.mount(device, mountpoint, options=options)


def umount_all_and_clear_cache(
    mount_manager: MountManagerProtocol | None, file_ops: FileOpsProtocol | None
) -> None:
    """Unmount all filesystems and clear file-ops cache when available."""
    if mount_manager:
        mount_manager.umount_all()
    if file_ops:
        file_ops.clear_cache()


def get_mountpoints(mount_manager: MountManagerProtocol | None) -> list[str]:
    """Return active mountpoints."""
    return _manager_list(mount_manager, "mountpoints")


def get_mounts(mount_manager: MountManagerProtocol | None) -> list[str]:
    """Return mounted devices."""
    return _manager_list(mount_manager, "mounts")


def mount_all_parallel(
    mount_manager: MountManagerProtocol,
    devices: list[tuple[str, str]],
    max_workers: int = 4,
    readonly: bool = True,
) -> dict[str, bool]:
    """Mount multiple filesystems in parallel."""
    return mount_manager.mount_all_parallel(devices, max_workers, readonly)


def mount_with_fallback(
    mount_manager: MountManagerProtocol,
    device: str,
    mountpoint: str,
    fstype: str | None = None,
) -> bool:
    """Mount with fallback strategy."""
    return mount_manager.mount_with_fallback(device, mountpoint, fstype)
