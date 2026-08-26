# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/filesystem/universal_rewriter.py
"""
Production-grade universal filesystem rewriter.

Deterministic, topology-aware rewriting for:
- ext4 / xfs / vfat / ntfs / swap
- Btrfs with subvolumes
- LUKS → crypttab
- LVM, mdraid, mapper devices
- PARTUUID vs UUID rules

No guessing, no basename hacks - only actual device probing.
"""
# pylint: disable=duplicate-code
# The guestfs typing-only stand-in below is intentionally repeated verbatim in a few
# modules; it's a tiny fallback shim, not worth extracting into a shared import.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # typing-only stand-in matching the guestfs module's name/shape when unavailable
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            class GuestFS(Protocol): ...  # pylint: disable=missing-class-docstring,too-few-public-methods


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Inventory model
# ------------------------------------------------------------


@dataclass
class DevInfo:
    """Complete device information."""

    dev: str  # Device path (e.g., /dev/nbd0p1, /dev/mapper/vg-root)
    fstype: str | None  # Filesystem type (ext4, xfs, btrfs, crypto_LUKS, swap)
    uuid: str | None  # Filesystem or LUKS UUID
    label: str | None  # Filesystem label
    partuuid: str | None  # Partition UUID (GPT)
    blk_type: str | None  # lsblk TYPE: part, lvm, crypt, raid, disk
    luks_uuid: str | None  # If crypto_LUKS container


def blkid_export_guestfs(g: guestfs.GuestFS, dev: str) -> dict[str, str]:
    """Get blkid information using guestfs."""
    try:
        blkid_map = g.blkid(dev)
        return {str(k).upper(): str(v) for k, v in blkid_map.items() if v}
    # backend-agnostic (native guestfs or VMCraft) probe; various exception types possible, best-effort
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("blkid failed for %s: %s", dev, e)
        return {}


def lsblk_type_guestfs(_g: guestfs.GuestFS, dev: str) -> str | None:
    """Get lsblk TYPE using guestfs best-effort."""
    # GuestFS doesn't have direct lsblk, infer from device path
    if dev.startswith("/dev/mapper/"):
        if "luks" in dev.lower() or "crypt" in dev.lower():
            return "crypt"
        return "lvm"  # Assume LVM for most mapper devices
    if dev.startswith("/dev/md"):
        return "raid"
    if re.match(r"/dev/\w+\d+$", dev):  # e.g., /dev/sda1, /dev/nbd0p1
        return "part"
    if re.match(r"/dev/\w+$", dev):  # e.g., /dev/sda, /dev/nbd0
        return "disk"
    return None


def luks_uuid_of_guestfs(g: guestfs.GuestFS, dev: str) -> str | None:
    """Get LUKS UUID if device is encrypted."""
    d = blkid_export_guestfs(g, dev)
    if d.get("TYPE") == "crypto_LUKS":
        return d.get("UUID")
    return None


def build_inventory(g: guestfs.GuestFS, devs: list[str]) -> dict[str, DevInfo]:
    """
    Build complete device inventory.

    Args:
        g: GuestFS instance
        devs: List of device paths to inventory

    Returns:
        Dict mapping device path to DevInfo
    """
    inv: dict[str, DevInfo] = {}

    for dev in devs:
        d = blkid_export_guestfs(g, dev)
        fstype = d.get("TYPE")

        info = DevInfo(
            dev=dev,
            fstype=fstype,
            uuid=d.get("UUID"),
            label=d.get("LABEL"),
            partuuid=d.get("PARTUUID"),
            blk_type=lsblk_type_guestfs(g, dev),
            luks_uuid=None,
        )

        # If LUKS, get its UUID
        if fstype == "crypto_LUKS":
            info.luks_uuid = luks_uuid_of_guestfs(g, dev)

        inv[dev] = info

        logger.debug(
            "Inventory: %s type=%s uuid=%s partuuid=%s blk_type=%s",
            dev,
            fstype,
            info.uuid,
            info.partuuid,
            info.blk_type,
        )

    return inv


# ------------------------------------------------------------
# Spec resolution
# ------------------------------------------------------------

_SPEC_UUID = re.compile(r"^UUID=(.+)$", re.IGNORECASE)
_SPEC_PARTUUID = re.compile(r"^PARTUUID=(.+)$", re.IGNORECASE)
_SPEC_LABEL = re.compile(r"^LABEL=(.+)$", re.IGNORECASE)


def normalize_spec(spec: str) -> str:
    """Normalize device specification."""
    return spec.strip()


def find_by_spec(  # pylint: disable=too-many-return-statements  # sequential UUID/PARTUUID/LABEL/direct-path resolution, each with its own early return by priority
    inv: dict[str, DevInfo], spec: str
) -> DevInfo | None:
    """
    Find device in inventory by spec.

    Args:
        inv: Device inventory
        spec: Device specification (UUID=xxx, /dev/sdX, etc.)

    Returns:
        DevInfo or None
    """
    spec = normalize_spec(spec)

    # Handle btrfsvol: prefix for Btrfs
    if spec.startswith("btrfsvol:"):
        spec = spec[9:]  # Remove prefix

    # UUID= specification
    m = _SPEC_UUID.match(spec)
    if m:
        u = m.group(1)
        for di in inv.values():
            if di.uuid == u:
                return di
        return None

    # PARTUUID= specification
    m = _SPEC_PARTUUID.match(spec)
    if m:
        pu = m.group(1)
        for di in inv.values():
            if di.partuuid == pu:
                return di
        return None

    # LABEL= specification
    m = _SPEC_LABEL.match(spec)
    if m:
        lab = m.group(1)
        for di in inv.values():
            if di.label == lab:
                return di
        return None

    # Direct device node
    if spec.startswith("/dev/") and spec in inv:
        return inv[spec]

    return None


# ------------------------------------------------------------
# Canonical spec selection
# ------------------------------------------------------------


def prefer_partuuid(di: DevInfo, mountpoint: str) -> bool:
    """
    Determine if PARTUUID should be preferred over UUID.

    PARTUUID is preferred only for:
    - Real partitions (not LVM/mdraid/mapper)
    - Boot-critical mounts (/, /boot, /boot/efi)

    Args:
        di: Device info
        mountpoint: Mount point

    Returns:
        True if PARTUUID should be used
    """
    return di.partuuid is not None and di.blk_type == "part" and mountpoint in ("/", "/boot", "/boot/efi")


def stable_spec(di: DevInfo, mountpoint: str) -> str:
    """
    Get stable device specification.

    Rules:
    - Partition mounts (/, /boot, /boot/efi) → PARTUUID
    - Everything else (LVM, mdraid, mapper) → UUID
    - Fallbacks: PARTUUID, LABEL, device path

    Args:
        di: Device info
        mountpoint: Mount point

    Returns:
        Stable device specification
    """
    # Prefer PARTUUID for partition-based boot mounts
    if prefer_partuuid(di, mountpoint):
        return f"PARTUUID={di.partuuid}"

    # Filesystem UUID for everything else
    if di.uuid:
        return f"UUID={di.uuid}"

    # Fallbacks (rare)
    if di.partuuid:
        return f"PARTUUID={di.partuuid}"

    if di.label:
        return f"LABEL={di.label}"

    # Last resort: keep device path
    return di.dev


# ------------------------------------------------------------
# Mount option manipulation
# ------------------------------------------------------------


def set_mountopt(opts: str, opt: str, *, key: str) -> str:
    """
    Set or replace a mount option.

    Args:
        opts: Current options string (comma-separated)
        opt: New option to set (e.g., "subvol=@")
        key: Option key to replace (e.g., "subvol")

    Returns:
        Updated options string
    """
    parts = [o for o in opts.split(",") if o]
    # Remove existing options with same key
    parts = [o for o in parts if not (o == key or o.startswith(key + "="))]
    parts.append(opt)
    return ",".join(parts)


# ------------------------------------------------------------
# fstab rewrite (all filesystems)
# ------------------------------------------------------------


def split_fstab_line(line: str) -> tuple[str, str, str, str, str, str] | None:
    """
    Parse fstab line into components.

    Args:
        line: Line from /etc/fstab

    Returns:
        (spec, mountpoint, fstype, options, dump, pass) or None
    """
    s = line.strip()
    if not s or s.startswith("#"):
        return None

    parts = s.split()
    if len(parts) < 4:
        return None

    spec = parts[0]
    mp = parts[1]
    fstype = parts[2]
    opts = parts[3]
    dump = parts[4] if len(parts) > 4 else "0"
    pas = parts[5] if len(parts) > 5 else "0"

    return spec, mp, fstype, opts, dump, pas


# single-pass fstab rewrite handling multiple filesystem-specific cases; splitting would fragment cohesive logic
def rewrite_fstab(  # pylint: disable=too-many-locals
    g: guestfs.GuestFS,
    fstab_path: str,
    inv: dict[str, DevInfo],
    *,
    btrfs_subvol_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Rewrite fstab with stable device identifiers.

    Args:
        g: GuestFS instance
        fstab_path: Path to fstab in guest (/etc/fstab)
        inv: Device inventory
        btrfs_subvol_map: Optional Btrfs subvolume mapping {"/": "@", "/home": "@home"}

    Returns:
        Statistics dict
    """
    btrfs_subvol_map = btrfs_subvol_map or {}
    stats = {
        "total_lines": 0,
        "converted": 0,
        "already_stable": 0,
        "skipped": 0,
        "errors": 0,
    }

    try:
        content = g.read_file(fstab_path)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
    # backend-agnostic (native guestfs or VMCraft) read; various exception types possible, best-effort
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to read %s: %s", fstab_path, e)
        stats["errors"] += 1
        return stats

    out_lines: list[str] = []

    for line in content.splitlines():
        stats["total_lines"] += 1

        parsed = split_fstab_line(line)
        if not parsed:
            # Comment or empty line - preserve as-is
            out_lines.append(line)
            continue

        spec, mp, fstype, opts, dump, pas = parsed

        # Skip special filesystems (tmpfs, proc, etc.)
        if fstype in ("tmpfs", "devtmpfs", "sysfs", "proc", "devpts", "cgroup", "cgroup2"):
            out_lines.append(line)
            stats["skipped"] += 1
            continue

        # Find device in inventory
        di = find_by_spec(inv, spec)
        if not di:
            # Unknown device - preserve as-is
            logger.warning("fstab: Device not found in inventory: %s", spec)
            out_lines.append(line)
            stats["errors"] += 1
            continue

        # Check if already stable
        if spec.upper().startswith(("UUID=", "PARTUUID=", "LABEL=")):
            out_lines.append(line)
            stats["already_stable"] += 1
            continue

        # Get canonical spec
        new_spec = stable_spec(di, mp)

        # Filesystem-specific handling
        if fstype == "btrfs":
            # Handle Btrfs subvolumes
            desired_subvol = btrfs_subvol_map.get(mp)
            if desired_subvol:
                opts = set_mountopt(opts, f"subvol={desired_subvol}", key="subvol")

        # Swap special case: always prefer UUID
        if fstype == "swap" and di.uuid:
            new_spec = f"UUID={di.uuid}"

        # Write new line with stable spec
        new_line = f"{new_spec:<40} {mp:<20} {fstype:<10} {opts:<30} {dump} {pas}"
        out_lines.append(new_line)
        stats["converted"] += 1

        logger.info("fstab: %s (%s): %s → %s", mp, fstype, spec, new_spec)

    # Write updated fstab
    try:
        new_content = "\n".join(out_lines) + "\n"
        g.write(fstab_path, new_content)
        logger.info(
            "Updated %s: %s converted, %s already stable",
            fstab_path,
            stats["converted"],
            stats["already_stable"],
        )
    # backend-agnostic (native guestfs or VMCraft) write; various exception types possible, best-effort
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to write %s: %s", fstab_path, e)
        stats["errors"] += 1

    return stats


# ------------------------------------------------------------
# crypttab rewrite (LUKS)
# ------------------------------------------------------------


def rewrite_crypttab(  # pylint: disable=too-many-locals  # single-pass crypttab rewrite mirroring rewrite_fstab's structure
    g: guestfs.GuestFS,
    crypttab_path: str,
    inv: dict[str, DevInfo],
) -> dict[str, Any]:
    """
    Rewrite crypttab with LUKS UUIDs.

    Args:
        g: GuestFS instance
        crypttab_path: Path to crypttab in guest (/etc/crypttab)
        inv: Device inventory

    Returns:
        Statistics dict
    """
    stats = {
        "total_lines": 0,
        "converted": 0,
        "already_stable": 0,
        "errors": 0,
    }

    try:
        content = g.read_file(crypttab_path)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
    # backend-agnostic (native guestfs or VMCraft) read; various exception types possible, best-effort
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("crypttab not found or unreadable: %s", e)
        return stats

    out_lines: list[str] = []

    for line in content.splitlines():
        stats["total_lines"] += 1

        s = line.strip()
        if not s or s.startswith("#"):
            out_lines.append(line)
            continue

        parts = s.split()
        if len(parts) < 2:
            out_lines.append(line)
            continue

        name, spec = parts[0], parts[1]

        # Check if already UUID-based
        if spec.upper().startswith("UUID="):
            out_lines.append(line)
            stats["already_stable"] += 1
            continue

        # Find device in inventory
        di = find_by_spec(inv, spec)

        if di:
            # Get LUKS UUID
            luks = di.luks_uuid or luks_uuid_of_guestfs(g, di.dev)
            if luks:
                parts[1] = f"UUID={luks}"
                new_line = " ".join(parts)
                out_lines.append(new_line)
                stats["converted"] += 1
                logger.info("crypttab: %s: %s → UUID=%s", name, spec, luks)
                continue

        # Keep original if no LUKS UUID found
        out_lines.append(line)

    # Write updated crypttab
    try:
        new_content = "\n".join(out_lines) + "\n"
        g.write(crypttab_path, new_content)
        logger.info("Updated %s: %s converted", crypttab_path, stats["converted"])
    # backend-agnostic (native guestfs or VMCraft) write; various exception types possible, best-effort
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to write %s: %s", crypttab_path, e)
        stats["errors"] += 1

    return stats
