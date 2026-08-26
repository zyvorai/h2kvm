# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/filesystem/stable_mount.py
"""
Comprehensive Linux filesystem support with stable mount identifiers.

Ensures all filesystems use stable device identifiers (UUID, PARTUUID, LABEL)
instead of unstable paths like /dev/sdX or /dev/disk/by-path/...

Supports:
- ext2/ext3/ext4 (Linux standard)
- XFS (RHEL/CentOS/Fedora default)
- Btrfs (openSUSE/Fedora default, with subvolume support)
- F2FS (Flash-Friendly File System)
- JFS (IBM Journaled File System)
- ReiserFS (legacy)
- NILFS2 (continuous snapshots)
- ZFS (via stable pool identifiers)
- FAT16/FAT32/exFAT (cross-platform)
- NTFS (Windows compatibility)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pylint: disable=duplicate-code
    # reason: this TYPE_CHECKING-only guestfs stub block is intentionally duplicated
    # verbatim across fixer modules (see also fixers/bootloader/post_conversion.py) --
    # it's boilerplate, not shared logic worth extracting into a helper import.
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore  pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            # reason: TYPE_CHECKING-only stand-in module/class mirroring the `guestfs`
            # module's name so `guestfs.GuestFS` type hints resolve when the real
            # (dynamically-typed, C-extension) guestfs package isn't installed.
            class GuestFS(Protocol):  # pylint: disable=missing-class-docstring,too-few-public-methods
                ...


logger = logging.getLogger(__name__)


class FilesystemType(str, Enum):
    """Supported Linux filesystem types."""

    # Standard Linux filesystems
    EXT2 = "ext2"
    EXT3 = "ext3"
    EXT4 = "ext4"
    XFS = "xfs"
    BTRFS = "btrfs"

    # Advanced/specialized filesystems
    F2FS = "f2fs"
    JFS = "jfs"
    REISERFS = "reiserfs"
    REISER4 = "reiser4"
    NILFS2 = "nilfs2"
    ZFS = "zfs"
    BCACHEFS = "bcachefs"

    # Cross-platform filesystems
    VFAT = "vfat"
    FAT16 = "fat16"
    FAT32 = "fat32"
    EXFAT = "exfat"
    NTFS = "ntfs"

    # Special filesystems (not mountable as root)
    SWAP = "swap"
    TMPFS = "tmpfs"
    DEVTMPFS = "devtmpfs"
    SYSFS = "sysfs"
    PROC = "proc"
    CGROUP = "cgroup"
    CGROUP2 = "cgroup2"

    # Encrypted/layered
    LUKS = "crypto_LUKS"
    LVM = "lvm2_member"

    UNKNOWN = "unknown"


# Filesystem type aliases (normalization)
FS_TYPE_ALIASES = {
    "fat": "vfat",
    "msdos": "vfat",
    "fat12": "vfat",
    "ntfs-3g": "ntfs",
    "ntfs3": "ntfs",
    "fuse.ntfs": "ntfs",
    "exfatfs": "exfat",
    "fuse.exfat": "exfat",
    "ext2fs": "ext2",
    "ext3fs": "ext3",
    "ext4fs": "ext4",
    "xfsfs": "xfs",
    "btrfsfs": "btrfs",
    "crypto_luks": "crypto_LUKS",
    "luks": "crypto_LUKS",
}


@dataclass
class DeviceIdentifiers:
    """Stable device identifiers for fstab entries."""

    device_path: str
    uuid: str | None = None
    partuuid: str | None = None
    label: str | None = None
    partlabel: str | None = None
    fs_type: str | None = None

    def get_stable_spec(self, prefer_partuuid: bool = False) -> str | None:
        """
        Get the most stable device specification.

        Priority:
        1. PARTUUID (survives filesystem recreation) - if prefer_partuuid=True
        2. UUID (filesystem UUID) - default
        3. PARTUUID (fallback)
        4. LABEL (user-friendly but can be duplicated)
        5. PARTLABEL (partition label)
        6. None (no stable identifier available)

        Args:
            prefer_partuuid: Prefer PARTUUID over UUID (for cross-hypervisor stability)

        Returns:
            Stable device specification or None
        """
        if prefer_partuuid and self.partuuid:
            return f"PARTUUID={self.partuuid}"

        if self.uuid:
            return f"UUID={self.uuid}"

        if self.partuuid:
            return f"PARTUUID={self.partuuid}"

        if self.label:
            return f"LABEL={self.label}"

        if self.partlabel:
            return f"PARTLABEL={self.partlabel}"

        return None


@dataclass
class FilesystemMountOptions:
    """Filesystem-specific mount options."""

    fs_type: str
    default_opts: list[str]
    recommended_opts: list[str]
    ro_opts: list[str]  # Additional options for read-only mounts

    @classmethod
    def for_filesystem(cls, fs_type: str, _readonly: bool = False) -> FilesystemMountOptions:
        """Get recommended mount options for a filesystem type."""
        fs_type = normalize_fs_type(fs_type)

        # Map of filesystem types to mount options
        fs_opts = {
            "ext2": cls(
                fs_type="ext2",
                default_opts=["errors=remount-ro"],
                recommended_opts=["noatime"],
                ro_opts=["noload"],
            ),
            "ext3": cls(
                fs_type="ext3",
                default_opts=["errors=remount-ro"],
                recommended_opts=["noatime", "data=ordered"],
                ro_opts=["noload", "norecovery"],
            ),
            "ext4": cls(
                fs_type="ext4",
                default_opts=["errors=remount-ro"],
                recommended_opts=["noatime"],
                ro_opts=["noload", "norecovery"],
            ),
            "xfs": cls(
                fs_type="xfs",
                default_opts=["defaults"],
                recommended_opts=["noatime", "inode64"],
                ro_opts=["norecovery"],
            ),
            "btrfs": cls(
                fs_type="btrfs",
                default_opts=["defaults"],
                recommended_opts=["noatime", "compress=zstd", "space_cache=v2"],
                ro_opts=["norecovery"],
            ),
            "f2fs": cls(
                fs_type="f2fs",
                default_opts=["defaults"],
                recommended_opts=["noatime", "nodiscard"],
                ro_opts=["ro"],
            ),
            "jfs": cls(
                fs_type="jfs", default_opts=["defaults"], recommended_opts=["noatime"], ro_opts=["ro"]
            ),
            "reiserfs": cls(
                fs_type="reiserfs",
                default_opts=["defaults"],
                recommended_opts=["noatime", "notail"],
                ro_opts=["ro"],
            ),
            "nilfs2": cls(
                fs_type="nilfs2", default_opts=["defaults"], recommended_opts=["noatime"], ro_opts=["ro"]
            ),
            "vfat": cls(
                fs_type="vfat",
                default_opts=["defaults"],
                recommended_opts=["iocharset=utf8", "shortname=mixed", "errors=remount-ro"],
                ro_opts=["ro"],
            ),
            "exfat": cls(
                fs_type="exfat",
                default_opts=["defaults"],
                recommended_opts=["iocharset=utf8", "errors=remount-ro"],
                ro_opts=["ro"],
            ),
            "ntfs": cls(
                fs_type="ntfs",
                default_opts=["defaults"],
                recommended_opts=["permissions", "streams_interface=windows"],
                ro_opts=["ro"],
            ),
        }

        # Get options or use generic defaults
        return fs_opts.get(
            fs_type, cls(fs_type=fs_type, default_opts=["defaults"], recommended_opts=[], ro_opts=["ro"])
        )

    def build_options_string(
        self, readonly: bool = False, preserve_existing: list[str] | None = None
    ) -> str:
        """
        Build mount options string.

        Args:
            readonly: Include read-only options
            preserve_existing: Existing options to preserve (e.g., from current fstab)

        Returns:
            Comma-separated mount options string
        """
        opts = self.default_opts.copy()

        if preserve_existing:
            # Preserve user-specified options that don't conflict
            for opt in preserve_existing:
                opt_clean = opt.strip()
                if opt_clean and opt_clean not in opts:
                    # Skip "defaults" if we have specific options
                    if opt_clean == "defaults" and len(opts) > 1:
                        continue
                    opts.append(opt_clean)

        if readonly:
            # Add read-only options
            for ro_opt in self.ro_opts:
                if ro_opt not in opts:
                    opts.append(ro_opt)

        # Remove duplicates while preserving order
        seen = set()
        unique_opts = []
        for opt in opts:
            if opt not in seen:
                seen.add(opt)
                unique_opts.append(opt)

        return ",".join(unique_opts)


def normalize_fs_type(fs_type: str) -> str:
    """Normalize filesystem type string."""
    fs_clean = fs_type.strip().lower().replace("-", "_")
    return FS_TYPE_ALIASES.get(fs_clean, fs_clean)


def is_stable_device_spec(spec: str) -> bool:
    """Check if a device specification uses stable identifiers."""
    spec_upper = spec.upper()
    return any(spec_upper.startswith(prefix) for prefix in ("UUID=", "PARTUUID=", "LABEL=", "PARTLABEL="))


def get_device_identifiers(g: guestfs.GuestFS, device: str) -> DeviceIdentifiers:
    """
    Get all available stable identifiers for a device.

    Args:
        g: GuestFS instance
        device: Device path (e.g., /dev/nbd0p1, /dev/mapper/vg-lv)

    Returns:
        DeviceIdentifiers with all available identifiers
    """
    identifiers = DeviceIdentifiers(device_path=device)

    try:
        # Use blkid to get all identifiers
        blkid_map = g.blkid(device)

        identifiers.uuid = blkid_map.get("UUID")
        identifiers.partuuid = blkid_map.get("PARTUUID")
        identifiers.label = blkid_map.get("LABEL")
        identifiers.partlabel = blkid_map.get("PARTLABEL")
        identifiers.fs_type = normalize_fs_type(blkid_map.get("TYPE", "unknown"))

        logger.debug(
            "Device %s: UUID=%s, PARTUUID=%s, TYPE=%s",
            device,
            identifiers.uuid,
            identifiers.partuuid,
            identifiers.fs_type,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort identifier lookup -- returns identifiers with whatever
        # fields blkid managed to fill in rather than aborting the fixer run.
        logger.warning("Failed to get identifiers for %s: %s", device, e)

    return identifiers


def convert_btrfs_subvol_spec(
    spec: str, identifiers: DeviceIdentifiers, prefer_partuuid: bool = False
) -> str:
    """
    Convert btrfs subvolume specification to stable identifier.

    Examples:
        btrfsvol:/dev/sda2/@home -> UUID=xxx,subvol=@home
        /dev/sda2 (with subvol=@ in options) -> UUID=xxx

    Args:
        spec: Device specification (may include btrfsvol: prefix)
        identifiers: Device identifiers
        prefer_partuuid: Prefer PARTUUID over UUID

    Returns:
        Stable device specification
    """
    # Parse btrfsvol: prefix if present
    if spec.startswith("btrfsvol:"):
        spec = spec[9:]  # Remove "btrfsvol:" prefix

    # Get stable spec
    stable_spec = identifiers.get_stable_spec(prefer_partuuid=prefer_partuuid)

    return stable_spec or spec


def should_use_partuuid(mountpoint: str, fs_type: str, context: str = "hypervisor_migration") -> bool:
    """
    Determine whether to prefer PARTUUID over UUID.

    PARTUUID is preferred for:
    - Root filesystem in hypervisor migrations (survives filesystem tuning)
    - Btrfs filesystems (UUID is shared across subvolumes)
    - Cross-hypervisor migrations (more stable than filesystem UUID)

    UUID is preferred for:
    - Non-root filesystems (more commonly used)
    - Standard ext4/XFS filesystems (UUID is well-established)

    Args:
        mountpoint: Mount point (e.g., /, /home, /boot)
        fs_type: Filesystem type
        context: Migration context

    Returns:
        True if PARTUUID should be preferred
    """
    # Always prefer PARTUUID for Btrfs (UUID is shared across subvolumes)
    if fs_type == "btrfs":
        return True

    # Prefer PARTUUID for root in hypervisor migrations
    return mountpoint == "/" and context == "hypervisor_migration"


def get_recommended_fs_check_freq(  # pylint: disable=too-many-return-statements
    fs_type: str, mountpoint: str
) -> tuple[int, int]:
    # reason: distinct (dump, pass) fsck recommendations per filesystem family and
    # root-vs-non-root mountpoint are clearest expressed as early returns.
    """
    Get recommended fsck pass and check frequency for filesystem.

    Returns: (dump, pass) tuple for fstab
    - dump: 0 (no dump) or 1 (include in dump)
    - pass: 0 (no fsck), 1 (root fsck first), 2 (fsck after root)
    """
    fs_type = normalize_fs_type(fs_type)

    # Root filesystem
    if mountpoint == "/":
        if fs_type in ("xfs", "btrfs", "f2fs", "zfs"):
            # Modern filesystems don't need boot-time fsck
            return (0, 0)
        if fs_type in ("ext2", "ext3", "ext4"):
            # Ext filesystems benefit from fsck
            return (1, 1)
        return (0, 1)

    # Non-root filesystems
    if fs_type in ("xfs", "btrfs", "f2fs", "zfs", "reiserfs", "jfs"):
        # Modern journaling filesystems
        return (0, 0)
    if fs_type in ("ext2", "ext3", "ext4"):
        # Ext filesystems
        return (1, 2)
    if fs_type in ("vfat", "exfat", "ntfs"):
        # Windows-compatible filesystems (no fsck at boot)
        return (0, 0)
    # Default: no fsck
    return (0, 0)


# Logging helper
def log_fstab_conversion(original_spec: str, new_spec: str, mountpoint: str, fs_type: str) -> None:
    """Log fstab conversion for audit trail."""
    logger.info(
        "fstab stabilization: %s (%s): %s -> %s", mountpoint, fs_type, original_spec, new_spec
    )
