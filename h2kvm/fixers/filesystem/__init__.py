# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/filesystem/__init__.py
"""
Filesystem fixing modules for VMware -> KVM migration.

This package provides filesystem-related fixes:
- fixer: Filesystem detection and fixing
- fstab: fstab and crypttab rewriting (legacy)
- universal_rewriter: Production-grade rewriter (NEW)
"""

import logging
import re

from .universal_rewriter import (
    DevInfo,
    build_inventory,
    find_by_spec,
    rewrite_crypttab,
    rewrite_fstab,
    stable_spec,
)

__all__ = [
    "DevInfo",
    "build_inventory",
    "find_by_spec",
    "rewrite_crypttab",
    "rewrite_fstab",
    "stabilize_guest_fstab",
    "stable_spec",
]


# one-shot orchestration helper: builds inventory, detects btrfs subvols, rewrites fstab/crypttab -- inherently
# multi-step; splitting would obscure the linear fault-tolerant flow more than it would help.
def stabilize_guest_fstab(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    g, *, detect_btrfs: bool = True, fstab_path: str = "/etc/fstab"
):
    """
    One-shot helper: stabilize fstab using universal rewriter.

    Usage in offline_fixer.py:
    ```python
    from ..filesystem import stabilize_guest_fstab

    result = stabilize_guest_fstab(g)
    print(f"Converted: {result['fstab_stats']['converted']} entries")
    ```

    Args:
        g: GuestFS instance (must be launched and root mounted)
        detect_btrfs: Auto-detect Btrfs subvolume layout
        fstab_path: Path to fstab in guest

    Returns:
        Result dict with stats
    """
    logger = logging.getLogger(__name__)

    result = {
        "success": False,
        "inventory_size": 0,
        "fstab_stats": {},
        "crypttab_stats": {},
        "btrfs_subvols": {},
        "errors": [],
    }

    try:  # pylint: disable=too-many-nested-blocks  # linear best-effort orchestration, splitting would hurt clarity
        # 1. Build device inventory
        devices = []

        # Get partitions
        try:
            devices.extend(g.list_partitions() or [])
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort inventory step, must not abort
            logger.warning("Failed to list partitions: %s", e)

        # Get logical volumes
        try:
            if hasattr(g, "lvs"):
                devices.extend(g.lvs() or [])
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort inventory step, must not abort
            logger.warning("Failed to list LVs: %s", e)

        # Get filesystem map devices (includes /dev/mapper/*)
        try:
            fsmap = g.list_filesystems() or {}
            for dev in fsmap:
                if dev not in devices:
                    devices.append(dev)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort inventory step, must not abort
            logger.warning("Failed to list filesystems: %s", e)

        logger.info("Building inventory for %d devices...", len(devices))
        inv = build_inventory(g, devices)
        result["inventory_size"] = len(inv)

        # 2. Detect Btrfs subvolumes if requested
        btrfs_map = {}
        if detect_btrfs:
            try:
                # Simple heuristic: if root is btrfs, check for common subvolumes
                if g.is_dir("/") and g.exists("/etc/fstab"):
                    # Read current fstab to see if subvolumes are in use
                    fstab_content = g.read_file(fstab_path)
                    if isinstance(fstab_content, bytes):
                        fstab_content = fstab_content.decode("utf-8", errors="replace")

                    # Look for subvol= options in current fstab
                    for line in fstab_content.splitlines():
                        if "subvol=" in line and not line.strip().startswith("#"):
                            parts = line.split()
                            if len(parts) >= 4:
                                mp = parts[1]
                                opts = parts[3]
                                # Extract subvol value
                                match = re.search(r"subvol=([^,\s]+)", opts)
                                if match:
                                    subvol = match.group(1)
                                    btrfs_map[mp] = subvol
                                    logger.info("Detected Btrfs subvol: %s → %s", mp, subvol)

                result["btrfs_subvols"] = btrfs_map
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort heuristic, must not abort
                logger.warning("Btrfs subvolume detection failed: %s", e)

        # 3. Rewrite fstab
        fstab_stats = rewrite_fstab(g, fstab_path, inv, btrfs_subvol_map=btrfs_map)
        result["fstab_stats"] = fstab_stats

        # 4. Rewrite crypttab if it exists
        crypttab_path = "/etc/crypttab"
        if g.is_file(crypttab_path):
            crypttab_stats = rewrite_crypttab(g, crypttab_path, inv)
            result["crypttab_stats"] = crypttab_stats

        result["success"] = True
        return result

    except Exception as e:  # pylint: disable=broad-exception-caught  # top-level fault-tolerant wrapper, must not raise
        result["errors"].append(str(e))
        logger.exception("Filesystem stabilization failed: %s", e)
        return result
