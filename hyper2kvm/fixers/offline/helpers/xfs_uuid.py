# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Production-grade filesystem UUID regeneration for VM conversions.

Safely regenerates UUIDs on LVM logical volumes only, auto-updates
fstab and crypttab, and verifies /boot safety before proceeding.

Safety rules:
    - Regenerate UUID -> LVM logical volumes only
    - Never touch -> partitions (/dev/sda1, /dev/vda1)
    - Never touch -> /boot, /boot/efi partitions
    - Auto-update fstab with new UUIDs
    - Auto-update crypttab with new UUIDs
    - Verify /boot is mountable before dracut runs
    - Works through guestfs API (VMCraft backend)

Supported filesystems:
    - XFS (via xfs_admin -U generate or g.set_uuid)
    - ext4/ext3/ext2 (via g.set_uuid)

This matches the safety level of virt-v2v, osbuild, and image-builder.
"""

from __future__ import annotations

import contextlib
import logging
import re
import uuid as _uuid_mod
from typing import TYPE_CHECKING, Any

from hyper2kvm.core.utils import U

if TYPE_CHECKING:
    from hyper2kvm.core.guestfs_typing import guestfs


class FilesystemUUIDRegenerator:
    """
    Production-safe filesystem UUID regeneration for cloned VMs.

    Only targets LVM logical volumes. Never touches plain partitions
    like /boot (/dev/sda1) to avoid breaking bootloader references.
    Auto-updates fstab and crypttab after regeneration.
    """

    # Filesystem types we can regenerate UUIDs for
    SUPPORTED_FSTYPES = {"xfs", "ext4", "ext3", "ext2"}

    # Filesystem types that are swap (UUID regen via mkswap)
    SWAP_FSTYPES = {"swap"}

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    # ----------------------------------------------------------------
    # Main entry point
    # ----------------------------------------------------------------

    def regenerate_uuids(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Regenerate filesystem UUIDs on LVM volumes and update fstab/crypttab.

        Must run BEFORE mounting filesystems (devices must be unmounted
        for UUID changes to succeed).

        Args:
            g: GuestFS instance (launched, LVM activated, nothing mounted)

        Returns:
            Audit dict with regeneration results and UUID mapping
        """
        audit: dict[str, Any] = {
            "attempted": False,
            "lvm_volumes_found": 0,
            "regenerated": [],
            "skipped": [],
            "fstab_updated": False,
            "crypttab_updated": False,
            "errors": [],
        }

        try:
            # 1) Find LVM logical volumes only
            lvm_devices = self._find_lvm_volumes(g)
            audit["lvm_volumes_found"] = len(lvm_devices)

            if not lvm_devices:
                self.logger.debug("No LVM logical volumes found, skipping UUID regeneration")
                return audit

            # 2) Regenerate UUIDs on eligible volumes
            audit["attempted"] = True
            uuid_map: dict[str, str] = {}

            for device in lvm_devices:
                result = self._regenerate_device_uuid(g, device)
                if result["status"] == "regenerated":
                    uuid_map[result["old_uuid"]] = result["new_uuid"]
                    audit["regenerated"].append(result)
                elif result["status"] == "skipped":
                    audit["skipped"].append(result)
                else:
                    audit["errors"].append(f"{device}: {result.get('error', 'unknown')}")

            # 3) Update fstab with new UUIDs (if root is mounted later,
            #    the fstab stabilizer will use the correct UUIDs)
            if uuid_map:
                self.logger.info("Regenerated %d UUID(s), updating config files...", len(uuid_map))
                audit["uuid_map"] = uuid_map
            else:
                self.logger.info("No UUIDs were regenerated")

        except Exception as e:  # pylint: disable=broad-exception-caught  # top-level fault-tolerant wrapper
            audit["errors"].append(f"Unexpected error: {e}")
            self.logger.exception("UUID regeneration failed: %s", e)

        return audit

    def update_fstab(self, g: guestfs.GuestFS, uuid_map: dict[str, str]) -> bool:
        """
        Update /etc/fstab with regenerated UUIDs.

        Call this AFTER root is mounted (so /etc/fstab is accessible).

        Args:
            g: GuestFS instance with root mounted
            uuid_map: Mapping of old_uuid -> new_uuid

        Returns:
            True if fstab was modified
        """
        if not uuid_map:
            return False

        try:
            if not g.is_file("/etc/fstab"):
                self.logger.debug("No /etc/fstab found")
                return False

            content = U.to_text(g.read_file("/etc/fstab"))
            original = content

            for old_uuid, new_uuid in uuid_map.items():
                # Replace UUID= references (case-insensitive for safety)
                content = re.sub(
                    rf"UUID={re.escape(old_uuid)}",
                    f"UUID={new_uuid}",
                    content,
                    flags=re.IGNORECASE,
                )

            if content != original:
                g.write("/etc/fstab", content)
                changes = sum(1 for old in uuid_map if f"UUID={old}" in original)
                self.logger.info("Updated /etc/fstab: %d UUID reference(s) replaced", changes)
                return True

            self.logger.debug("No UUID references in fstab matched regenerated UUIDs")
            return False

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort config update, must not abort
            self.logger.warning("Failed to update fstab: %s", e)
            return False

    def update_crypttab(self, g: guestfs.GuestFS, uuid_map: dict[str, str]) -> bool:
        """
        Update /etc/crypttab with regenerated UUIDs.

        Call this AFTER root is mounted.

        Args:
            g: GuestFS instance with root mounted
            uuid_map: Mapping of old_uuid -> new_uuid

        Returns:
            True if crypttab was modified
        """
        if not uuid_map:
            return False

        try:
            if not g.is_file("/etc/crypttab"):
                self.logger.debug("No /etc/crypttab found")
                return False

            content = U.to_text(g.read_file("/etc/crypttab"))
            original = content

            for old_uuid, new_uuid in uuid_map.items():
                content = re.sub(
                    rf"UUID={re.escape(old_uuid)}",
                    f"UUID={new_uuid}",
                    content,
                    flags=re.IGNORECASE,
                )

            if content != original:
                g.write("/etc/crypttab", content)
                self.logger.info("Updated /etc/crypttab with regenerated UUIDs")
                return True

            return False

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort config update, must not abort
            self.logger.warning("Failed to update crypttab: %s", e)
            return False

    def verify_boot_safe(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Verify /boot is mounted and contains kernel + initramfs.

        Call this AFTER mounting root and /boot, BEFORE running dracut.
        Prevents dracut from writing initramfs to an empty /boot directory
        on the root LV instead of the actual boot partition.

        Args:
            g: GuestFS instance with root and /boot mounted

        Returns:
            Safety check results dict
        """
        result: dict[str, Any] = {
            "safe": False,
            "boot_mounted": False,
            "has_vmlinuz": False,
            "has_initramfs": False,
            "has_grub": False,
            "errors": [],
        }

        try:
            if not g.is_dir("/boot"):
                result["errors"].append("/boot directory missing")
                return result

            # Check /boot has content (not an empty mount point)
            try:
                boot_entries = [U.to_text(x) for x in g.ls("/boot")]
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort probe, treat as empty on failure
                boot_entries = []

            if not boot_entries:
                result["errors"].append("/boot is empty -- likely not mounted from boot partition")
                return result

            result["boot_mounted"] = True

            # Check for kernel
            result["has_vmlinuz"] = any(e.startswith("vmlinuz") for e in boot_entries)

            # Check for initramfs
            result["has_initramfs"] = any(e.startswith(("initramfs", "initrd")) for e in boot_entries)

            # Check for GRUB
            result["has_grub"] = any(e in ("grub2", "grub", "loader") for e in boot_entries)

            if not result["has_vmlinuz"]:
                result["errors"].append("No vmlinuz found in /boot")
            if not result["has_initramfs"]:
                result["errors"].append("No initramfs/initrd found in /boot")

            result["safe"] = result["has_vmlinuz"] and result["has_initramfs"]

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort safety check, must not abort
            result["errors"].append(f"Boot safety check failed: {e}")

        return result

    # ----------------------------------------------------------------
    # Internal methods
    # ----------------------------------------------------------------

    def _find_lvm_volumes(self, g: guestfs.GuestFS) -> list[str]:
        """
        Find LVM logical volumes with supported filesystem types.

        Only returns LVM LVs, never plain partitions.
        Skips swap volumes (handled separately).
        """
        devices = []
        try:
            lvs = g.lvs()
        except Exception:  # pylint: disable=broad-exception-caught  # no LVM support is a normal, expected outcome
            self.logger.debug("No LVM support or no LVs found")
            return devices

        for lv in lvs:
            try:
                fstype = U.to_text(g.vfs_type(lv))
                if fstype in self.SUPPORTED_FSTYPES:
                    devices.append(lv)
                elif fstype in self.SWAP_FSTYPES:
                    self.logger.debug("  Skipping swap volume: %s", lv)
                else:
                    self.logger.debug("  Skipping %s: unsupported fstype %s", lv, fstype)
            except Exception as e:  # pylint: disable=broad-exception-caught  # per-volume probe, must not abort scan
                self.logger.debug("Skipping device %s (filesystem type check failed): %s", lv, e)
                continue

        return devices

    def _regenerate_device_uuid(self, g: guestfs.GuestFS, device: str) -> dict[str, Any]:
        """
        Regenerate UUID for a single device.

        Uses VMCraft xfs_admin for XFS on VMCraft backend,
        g.set_uuid() for everything else.

        Args:
            g: GuestFS instance
            device: Device path (e.g., /dev/rhel/root)

        Returns:
            Result dict with status, old_uuid, new_uuid, or error
        """
        result: dict[str, Any] = {"device": device, "status": "unknown"}

        # Get filesystem type
        try:
            fstype = U.to_text(g.vfs_type(device))
            result["fstype"] = fstype
        except Exception as e:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend, best-effort probe
            result["status"] = "error"
            result["error"] = f"Cannot detect fstype: {e}"
            return result

        if fstype not in self.SUPPORTED_FSTYPES:
            result["status"] = "skipped"
            result["reason"] = f"Unsupported fstype: {fstype}"
            return result

        # Get old UUID
        old_uuid = None
        with contextlib.suppress(Exception):
            old_uuid = U.to_text(g.vfs_uuid(device))

        if not old_uuid:
            result["status"] = "skipped"
            result["reason"] = "Could not read current UUID"
            return result

        result["old_uuid"] = old_uuid

        # Regenerate UUID
        try:
            if fstype == "xfs":
                self._set_uuid_xfs(g, device)
            else:
                # ext4, ext3, ext2
                self._set_uuid_ext(g, device)
        except Exception as e:  # pylint: disable=broad-exception-caught  # inspects message across guestfs error kinds
            error_msg = str(e).lower()
            if "mounted" in error_msg:
                result["status"] = "skipped"
                result["reason"] = "Device is mounted"
                self.logger.debug("  Skipping %s: currently mounted", device)
                return result
            result["status"] = "error"
            result["error"] = str(e)
            self.logger.warning("  Failed to regenerate UUID for %s: %s", device, e)
            return result

        # Verify new UUID
        new_uuid = None
        with contextlib.suppress(Exception):
            new_uuid = U.to_text(g.vfs_uuid(device))

        if new_uuid and new_uuid != old_uuid:
            result["status"] = "regenerated"
            result["new_uuid"] = new_uuid
            self.logger.info("  Regenerated UUID for %s: %s... -> %s...", device, old_uuid[:8], new_uuid[:8])
        else:
            result["status"] = "error"
            result["error"] = "UUID unchanged after regeneration"

        return result

    def _set_uuid_xfs(self, g: guestfs.GuestFS, device: str) -> None:
        """Set new UUID on XFS filesystem."""
        if hasattr(g, "xfs_admin"):
            # VMCraft backend: use xfs_admin via run_sudo on host
            g.xfs_admin(device, uuid="generate")
        else:
            # Fallback: use native set_uuid API
            g.set_uuid(device, str(_uuid_mod.uuid4()))

    def _set_uuid_ext(self, g: guestfs.GuestFS, device: str) -> None:
        """Set new UUID on ext2/ext3/ext4 filesystem."""
        new_uuid = str(_uuid_mod.uuid4())
        if hasattr(g, "set_uuid"):
            g.set_uuid(device, new_uuid)
        elif hasattr(g, "is_file") and any(g.is_file(p) for p in ("/sbin/tune2fs", "/usr/sbin/tune2fs")):
            g.command(["tune2fs", "-U", new_uuid, device])
        else:
            self.logger.debug("tune2fs not available in guest — skipping UUID regen for %s", device)


# Backward-compatible alias
XfsUuidRegenerator = FilesystemUUIDRegenerator
