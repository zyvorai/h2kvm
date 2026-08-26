# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# pylint: disable=duplicate-code  # guestfs typing-stub fallback block is intentionally repeated per-module boilerplate
"""
Storage stack activation for offline VM fixing.

Handles activation of LVM, LUKS, RAID, and ZFS volumes before mounting.
This is critical for offline VM operations where the storage stack must be
manually activated before the root filesystem can be mounted.

Activation Order:
    1. LVM (Logical Volume Manager) - vgscan + vgchange
    2. LUKS (encryption) - unlock encrypted devices if key provided
    3. MD RAID - activate RAID arrays
    4. ZFS - import ZFS pools

Example:
    >>> from hyper2kvm.fixers.offline.operations import StorageActivator
    >>> activator = StorageActivator()
    >>> audit = activator.activate_all(g, luks_key_bytes=key)
    >>> if audit["lvm"]["activated"]:
    ...     print("LVM activated successfully")
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore  # pylint: disable=invalid-name,too-few-public-methods  # matches real guestfs module name for type-hint purposes; stub has no methods
            """Typing-only stand-in for the optional ``guestfs`` module."""

            class GuestFS(Protocol):  # pylint: disable=too-few-public-methods  # typing stub, no real methods needed
                """Typing-only stand-in for the ``guestfs.GuestFS`` handle type."""


class StorageActivator:
    """Activates storage stacks (LVM, LUKS, RAID, ZFS) for offline VMs."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize storage activator.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self._lvm_activated = False

    def activate_lvm(self, g: guestfs.GuestFS) -> None:
        """
        Activate LVM volume groups.

        Args:
            g: GuestFS instance
        """
        # Skip if already activated (prevent redundant scans)
        if self._lvm_activated:
            self.logger.debug("LVM already activated, skipping redundant activation")
            return

        if not hasattr(g, "vgscan") or not hasattr(g, "vgchange_activate_all"):
            return
        try:
            g.vgscan()
        except Exception:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; best-effort LVM activation must not abort mounting
            return
        try:
            g.vgchange_activate_all(True)
            self._lvm_activated = True  # Mark as activated on success
        except Exception:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; fall back to legacy int-flag form
            try:
                g.vgchange_activate_all(1)
                self._lvm_activated = True  # Mark as activated on success
            except Exception:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; best-effort LVM activation must not abort mounting
                pass

    def unlock_luks_devices(self, g: guestfs.GuestFS, luks_key_bytes: bytes | None) -> dict[str, Any]:
        """
        Unlock LUKS encrypted devices.

        Args:
            g: GuestFS instance
            luks_key_bytes: LUKS passphrase bytes

        Returns:
            Audit dict with unlock results
        """
        audit: dict[str, Any] = {
            "unlocked": [],
            "errors": [],
            "skipped_no_key": [],
        }

        if not luks_key_bytes:
            self.logger.debug("No LUKS key provided, skipping LUKS unlock")
            return audit

        try:
            # Get LUKS devices
            luks_devices = []
            with contextlib.suppress(Exception):
                luks_devices = g.list_dm_devices()

            if not luks_devices:
                self.logger.debug("No LUKS devices found")
                return audit

            for luks_dev in luks_devices:
                try:
                    # Try to unlock
                    g.luks_open(luks_dev, luks_dev.replace("/dev/", ""), luks_key_bytes)
                    audit["unlocked"].append(luks_dev)
                    self.logger.info("  ✓ Unlocked LUKS device: %s", luks_dev)
                except Exception as e:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; one bad LUKS device must not abort the others
                    audit["errors"].append(f"{luks_dev}: {e!s}")
                    self.logger.warning("  ⚠️  Failed to unlock %s: %s", luks_dev, e)

        except Exception as e:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; best-effort LUKS unlock must not abort mounting
            audit["errors"].append(f"Unexpected error: {e}")
            self.logger.exception("LUKS unlock failed: %s", e)

        return audit

    def can_run_command(self, g: guestfs.GuestFS, prog: str) -> bool:
        """
        Check if command is available in guest.

        Args:
            g: GuestFS instance
            prog: Program name

        Returns:
            True if program is available
        """
        try:
            paths = ["/sbin", "/usr/sbin", "/bin", "/usr/bin"]
            for base in paths:
                full = f"{base}/{prog}"
                if g.is_file(full):
                    return True
            return False
        except Exception:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; treat any failure as "command unavailable"
            return False

    def activate_mdraid(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Activate MD RAID arrays.

        Args:
            g: GuestFS instance

        Returns:
            Audit dict with activation results
        """
        audit: dict[str, Any] = {"activated": False, "errors": []}

        if not self.can_run_command(g, "mdadm"):
            self.logger.debug("mdadm not available, skipping RAID activation")
            return audit

        try:
            g.md_stat([])
            audit["activated"] = True
            self.logger.info("  ✓ Activated MD RAID arrays")
        except Exception as e:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; RAID may legitimately not be present
            audit["errors"].append(str(e))
            self.logger.debug("MD RAID activation failed (may not be present): %s", e)

        return audit

    def activate_zfs(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Activate ZFS pools.

        Args:
            g: GuestFS instance

        Returns:
            Audit dict with activation results
        """
        audit: dict[str, Any] = {"activated": False, "errors": []}

        if not self.can_run_command(g, "zpool"):
            self.logger.debug("zpool not available, skipping ZFS activation")
            return audit

        try:
            # Try to import all pools
            pools_out = g.command(["zpool", "import", "-a"])
            audit["activated"] = True
            self.logger.info("  ✓ Activated ZFS pools: %s", pools_out)
        except Exception as e:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; ZFS may legitimately not be present
            audit["errors"].append(str(e))
            self.logger.debug("ZFS activation failed (may not be present): %s", e)

        return audit

    def activate_all(self, g: guestfs.GuestFS, luks_key_bytes: bytes | None = None) -> dict[str, Any]:
        """
        Activate all storage stacks before mounting root.

        Args:
            g: GuestFS instance
            luks_key_bytes: Optional LUKS passphrase

        Returns:
            Audit dict with all activation results
        """
        audit: dict[str, Any] = {
            "lvm": {"activated": False},
            "luks": {},
            "mdraid": {},
            "zfs": {},
        }

        self.logger.debug("Activating storage stack (LVM, LUKS, RAID, ZFS)...")

        # Activate LVM
        try:
            self.activate_lvm(g)
            audit["lvm"]["activated"] = self._lvm_activated
        except Exception as e:  # pylint: disable=broad-exception-caught  # dynamic guestfs backend call; best-effort activation must not abort mounting
            self.logger.debug("LVM activation error: %s", e)

        # Unlock LUKS devices
        audit["luks"] = self.unlock_luks_devices(g, luks_key_bytes)

        # Activate RAID
        audit["mdraid"] = self.activate_mdraid(g)

        # Activate ZFS
        audit["zfs"] = self.activate_zfs(g)

        return audit
