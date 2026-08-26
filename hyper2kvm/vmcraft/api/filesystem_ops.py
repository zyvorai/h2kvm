# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Filesystem Operations.

Provides filesystem manipulation, query, and extended filesystem methods
for VMCraft via composition. Merges FilesystemMixin + FilesystemExtMixin.
"""

from __future__ import annotations

import os
from typing import Any

from hyper2kvm.vmcraft._utils import run_sudo
from hyper2kvm.vmcraft.services import (
    ext_get_e2attrs as svc_ext_get_e2attrs,
    ext_set_e2attrs as svc_ext_set_e2attrs,
    extract_filesystems_from_lsblk,
    find_by_label,
    find_by_uuid,
    fs_btrfs_filesystem_show as svc_fs_btrfs_filesystem_show,
    fs_btrfs_subvolume_list as svc_fs_btrfs_subvolume_list,
    fs_ntfs_3g_probe as svc_fs_ntfs_3g_probe,
    fs_xfs_admin as svc_fs_xfs_admin,
    fs_xfs_db as svc_fs_xfs_db,
    fs_xfs_growfs as svc_fs_xfs_growfs,
    fs_xfs_info as svc_fs_xfs_info,
    fs_xfs_repair as svc_fs_xfs_repair,
    fs_zfs_dataset_list as svc_fs_zfs_dataset_list,
    fs_zfs_pool_list as svc_fs_zfs_pool_list,
    get_vfs_label,
    get_vfs_type,
    get_vfs_uuid,
    invalidate_partition_cache as svc_invalidate_partition_cache,
    list_attached_devices,
    list_filesystems as svc_list_filesystems,
    list_partitions_cached as svc_list_partitions_cached,
)


class FilesystemOps:  # pylint: disable=too-many-public-methods,protected-access
    # reason: this class is composed *into* a host client (VMCraft) purely to split
    # its filesystem-related surface into its own module; reaching into the host's
    # `_`-prefixed helpers/caches is tight, intentional internal coupling within the
    # same package, not an unrelated class's internals. The large public method count
    # mirrors the equally large set of filesystem operations the host exposes.
    """Filesystem operations via composition."""

    def __init__(self, host) -> None:
        self._host = host

    # === Core filesystem operations (from FilesystemMixin) ===

    def list_filesystems(self) -> dict[str, str]:
        """List all filesystems."""
        return svc_list_filesystems(self._host.logger, run_sudo)

    def _extract_filesystems(self, dev: dict, result: dict) -> None:
        """Recursively extract filesystems from lsblk output."""
        extract_filesystems_from_lsblk(dev, result)

    def list_partitions(self, device: str | None = None, use_cache: bool = True) -> list[str]:
        """
        List all partitions with optional caching.

        Args:
            device: Optional device to list partitions for (defaults to NBD device)
            use_cache: Enable caching (default: True, 60-second TTL)

        Returns:
            List of partition device paths
        """
        return svc_list_partitions_cached(
            self._host.logger,
            self._host._nbd_manager,
            self._host._nbd_device,
            self._host._partition_cache,
            device=device,
            use_cache=use_cache,
        )

    def invalidate_partition_cache(self, device: str | None = None) -> None:
        """
        Invalidate partition cache.

        Call this after partition table modifications (part_add, part_del, etc.).

        Args:
            device: Optional device to invalidate (None = clear all)
        """
        svc_invalidate_partition_cache(self._host.logger, self._host._partition_cache, device)

    def findfs_uuid(self, uuid: str) -> str:
        """
        Find device by filesystem UUID.

        Args:
            uuid: Filesystem UUID to search for

        Returns:
            Device path (e.g., /dev/sda1)

        Raises:
            RuntimeError: If device not found
        """
        return find_by_uuid(self._host._nbd_device, uuid, self._host.list_partitions, self._host.vfs_uuid)

    def findfs_label(self, label: str) -> str:
        """
        Find device by filesystem label.

        Args:
            label: Filesystem label to search for

        Returns:
            Device path (e.g., /dev/sda1)

        Raises:
            RuntimeError: If device not found
        """
        return find_by_label(self._host._nbd_device, label, self._host.list_partitions, self._host.vfs_label)

    def list_devices(self) -> list[str]:
        """List all devices."""
        return list_attached_devices(self._host._nbd_device)

    def vfs_type(self, device: str) -> str:
        """
        Get filesystem type using multiple probing methods.

        Uses blkid -p (low-level probe) first, then falls back to lsblk.
        This is more reliable after LVM activation.
        """
        return get_vfs_type(self._host.logger, run_sudo, device)

    def vfs_uuid(self, device: str) -> str:
        """Get filesystem UUID."""
        return get_vfs_uuid(self._host.logger, run_sudo, device)

    def vfs_label(self, device: str) -> str:
        """Get filesystem label."""
        return get_vfs_label(self._host.logger, run_sudo, device)

    def statvfs(self, path: str) -> dict[str, int]:
        """Get filesystem statistics."""
        self._host._require_file_ops()
        mount_root = self._host._require_mount_root()
        guest_path = mount_root / path.lstrip("/")
        st = os.statvfs(guest_path)
        return {
            "bsize": st.f_bsize,
            "blocks": st.f_blocks,
            "bfree": st.f_bfree,
            "bavail": st.f_bavail,
            "files": st.f_files,
            "ffree": st.f_ffree,
            "flag": st.f_flag,
        }

    # === Extended filesystem operations (from FilesystemExtMixin) ===

    def get_e2attrs(self, file: str) -> str:
        """
        Get ext2/3/4 file attributes.

        Returns attribute string like "-------------e--"
        Common flags: i (immutable), a (append-only), e (extent format)

        Args:
            file: Guest filesystem path

        Returns:
            Attribute string (empty if not ext filesystem or error)
        """
        self._host._require_mount_root()
        return svc_ext_get_e2attrs(self._host.logger, file, self._host.command_quiet)

    def set_e2attrs(self, file: str, attrs: str, clear: bool = False) -> None:
        """
        Set ext2/3/4 file attributes.

        Args:
            file: Guest filesystem path
            attrs: Attribute string (e.g., "i" for immutable, "a" for append-only)
            clear: If True, remove attributes instead of adding them

        Common attributes:
            i - immutable (file cannot be modified)
            a - append-only (file can only be appended)
            d - no dump (file not backed up by dump)
            e - extent format (file uses extents)
        """
        self._host._require_mount_root()
        svc_ext_set_e2attrs(file, attrs, clear=clear, command_fn=self._host.command)

    def ntfs_3g_probe(self, device: str, rw: bool = False) -> int:
        """
        Probe NTFS filesystem with ntfs-3g.probe tool.

        Args:
            device: Device path
            rw: If True, test for read-write capability

        Returns:
            0 if mountable, non-zero otherwise
        """
        return self._host._sudo_service_call(svc_fs_ntfs_3g_probe, device, rw=rw)

    def btrfs_filesystem_show(self, device: str | None = None) -> list[dict[str, str]]:
        """
        Show Btrfs filesystem information.

        Args:
            device: Optional device path to query specific filesystem

        Returns:
            List of dicts with Btrfs filesystem info
            Keys: label, uuid, total_devices, used_devices
        """
        return self._host._sudo_service_call(svc_fs_btrfs_filesystem_show, device=device)

    def btrfs_subvolume_list(self, _device: str) -> list[dict[str, str]]:
        """
        List Btrfs subvolumes on a device.

        Note: Device must be mounted first.

        Args:
            _device: Unused -- `btrfs subvolume list` operates on the currently
                mounted root, not an arbitrary device; kept for API/call-site
                consistency with other per-device filesystem methods.

        Returns:
            List of dicts with subvolume info
            Keys: id, path, parent_id (if available)
        """
        mount_root = self._host._require_mount_root()
        return self._host._sudo_service_call(svc_fs_btrfs_subvolume_list, mount_point=str(mount_root))

    def zfs_pool_list(self) -> list[str]:
        """
        List imported ZFS pools.

        Returns:
            List of pool names
        """
        return self._host._sudo_service_call(svc_fs_zfs_pool_list)

    def zfs_dataset_list(self, pool: str | None = None) -> list[dict[str, str]]:
        """
        List ZFS datasets.

        Args:
            pool: Optional pool name to filter datasets

        Returns:
            List of dicts with dataset info
            Keys: name, used, avail, refer, mountpoint
        """
        return self._host._sudo_service_call(svc_fs_zfs_dataset_list, pool=pool)

    def xfs_info(self, device: str) -> dict[str, Any]:
        """
        Get XFS filesystem information and geometry.

        Args:
            device: XFS device path or mount point

        Returns:
            Dict with XFS filesystem information:
            - blocksize: Block size in bytes
            - agcount: Number of allocation groups
            - agsize: Allocation group size in blocks
            - sectsize: Sector size in bytes
            - inodesize: Inode size in bytes
            - naming: Naming version
            - log: Log information
            - realtime: Realtime section information (if present)
            - label: Filesystem label (if set)
        """
        return self._host._sudo_service_call(svc_fs_xfs_info, device)

    def xfs_admin(self, device: str, label: str | None = None, uuid: str | None = None) -> dict[str, str]:
        """
        Get or set XFS filesystem label and UUID.

        Args:
            device: XFS device path
            label: Optional new label to set (max 12 characters)
            uuid: Optional new UUID to set (or "generate" for random UUID)

        Returns:
            Dict with current label and UUID (after any changes)
            Keys: label, uuid

        Raises:
            RuntimeError: If setting label/UUID fails
        """
        return self._host._sudo_service_call(svc_fs_xfs_admin, device, label=label, uuid=uuid)

    def xfs_growfs(self, mountpoint: str, data_blocks: int | None = None) -> dict[str, Any]:
        """
        Grow (expand) an XFS filesystem.

        Note: The filesystem must be mounted.

        Args:
            mountpoint: Mount point of the XFS filesystem
            data_blocks: Optional target size in blocks (if None, grows to fill device)

        Returns:
            Dict with growth information:
            - success: True if growth succeeded
            - old_blocks: Original size in blocks
            - new_blocks: New size in blocks

        Raises:
            RuntimeError: If filesystem is not mounted or growth fails
        """
        return self._host._sudo_service_call(
            svc_fs_xfs_growfs,
            mountpoint,
            data_blocks=data_blocks,
            xfs_info_fn=self._host.xfs_info,
        )

    def xfs_repair(self, device: str, check_only: bool = False) -> dict[str, Any]:
        """
        Repair or check an XFS filesystem.

        IMPORTANT: Filesystem must NOT be mounted.

        Args:
            device: XFS device path
            check_only: If True, only check for errors (don't repair)

        Returns:
            Dict with repair information:
            - clean: True if filesystem is clean
            - errors_found: True if errors were found
            - errors_repaired: True if errors were repaired (check_only=False)
            - output: Command output

        Raises:
            RuntimeError: If filesystem is mounted or repair fails critically
        """
        return self._host._sudo_service_call(svc_fs_xfs_repair, device, check_only=check_only)

    def xfs_db(self, device: str, commands: list[str]) -> str:
        """
        Execute XFS debug/inspection commands using xfs_db.

        CAUTION: This is a low-level tool. Use with care.

        Args:
            device: XFS device path
            commands: List of xfs_db commands to execute

        Returns:
            Command output as string

        Example:
            # Get superblock info
            output = g.xfs_db("/dev/nbd0p1", ["sb 0", "p"])
        """
        return self._host._sudo_service_call(svc_fs_xfs_db, device, commands)

    def backup_files(self, paths: list[str], dest_archive: str, compression: str = "gzip") -> dict[str, Any]:
        """Backup files to archive."""
        return self._host._dispatch_manager_attr_call(
            "_backup_mgr", "backup_files", paths, dest_archive, compression
        )

    def restore_files(self, src_archive: str, dest_path: str = "/") -> dict[str, Any]:
        """Restore files from archive."""
        return self._host._dispatch_manager_attr_call("_backup_mgr", "restore_files", src_archive, dest_path)

    def audit_permissions(self, path: str = "/") -> dict[str, Any]:
        """Audit file permissions for security issues."""
        return self._host._dispatch_manager_attr_call("_security_auditor", "audit_permissions", path)

    def analyze_disk_usage(self, path: str = "/", top_n: int = 20) -> dict[str, Any]:
        """Analyze disk usage by directory."""
        return self._host._dispatch_manager_attr_call("_disk_optimizer", "analyze_disk_usage", path, top_n)

    def cleanup_temp_files(self, dry_run: bool = True) -> dict[str, Any]:
        """Clean up temporary files."""
        return self._host._dispatch_manager_attr_call("_disk_optimizer", "cleanup_temp_files", dry_run)
