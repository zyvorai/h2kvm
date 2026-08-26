# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/offline/spec_converter.py
"""
Device identifier and fstab/crypttab spec conversion utilities.

This module provides device identifier stabilization logic for converting
potentially unstable device paths (like /dev/sda1 or by-path references)
to stable identifiers (UUID, PARTUUID, LABEL).

Extracted from offline_fixer.py to provide single-responsibility module
for spec conversion logic.
"""
# pylint: disable=duplicate-code
# The guestfs typing-only stand-in below is intentionally repeated verbatim in a few
# modules; it's a tiny fallback shim, not worth extracting into a shared import.

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from h2kvm.core.utils import U
from h2kvm.fixers.filesystem.fstab import _BYPATH_PREFIX, FstabMode, Ident, parse_btrfsvol_spec

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # typing-only stand-in matching the guestfs module's name/shape when unavailable
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            class GuestFS(Protocol): ...  # pylint: disable=missing-class-docstring,too-few-public-methods


logger = logging.getLogger("h2kvm.spec_converter")


class SpecConverter:  # pylint: disable=too-few-public-methods  # single public entrypoint (convert_spec) with private stabilization helpers
    """
    Device spec converter for stabilizing device identifiers.

    Converts unstable device references to stable identifiers based on:
    - FstabMode policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
    - Device type (btrfsvol, by-path, /dev/*)
    - Available blkid metadata
    """

    def __init__(
        self,
        fstab_mode: FstabMode,
        root_dev: str | None = None,
    ):
        """
        Initialize spec converter.

        Args:
            fstab_mode: Conversion policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
            root_dev: Optional root device for by-path inference
        """
        self.fstab_mode = fstab_mode
        self.root_dev = root_dev

    def convert_spec(self, g: guestfs.GuestFS, spec: str) -> tuple[str, str]:
        """
        Convert a device spec to stable identifier if needed.

        Args:
            g: GuestFS handle with system mounted
            spec: Original device spec (e.g., /dev/sda1, UUID=..., by-path/...)

        Returns:
            Tuple of (converted_spec, reason) where reason describes what happened:
            - "already-stable": spec is already stable (UUID, LABEL, etc.)
            - "by-path-unresolved": by-path couldn't be resolved
            - "mapped:<dev>": by-path was mapped to device
            - "mapped:<dev> no-id": mapped but no stable ID found
            - "blkid:<dev>": converted via blkid
            - "dev-no-id": /dev/* but no stable ID found
            - "unchanged": no conversion needed or possible
        """
        logger.info("🎯 convert_spec: spec=%r, fstab_mode=%r", spec, self.fstab_mode)

        original = spec

        # btrfsvol:/dev/XXX//@/path -> treat stable mapping for underlying dev
        if spec.startswith("btrfsvol:"):
            dev, _sv = parse_btrfsvol_spec(spec)
            spec = dev.strip()
            logger.info("  Parsed btrfsvol: %s -> dev=%s", original, dev)

        # Already stable (UUID=, LABEL=, PARTUUID=, etc.)
        if Ident.is_stable(spec):
            logger.info("  Already stable: %s", spec)
            return original, "already-stable"

        # by-path -> real dev -> stable
        if spec.startswith(_BYPATH_PREFIX):
            logger.info("  Detected by-path device, calling _stabilize_bypath")
            return self._stabilize_bypath(g, spec, original)

        # STABILIZE_ALL: rewrite any /dev/* to stable
        if self.fstab_mode == FstabMode.STABILIZE_ALL and spec.startswith("/dev/"):
            logger.info("  STABILIZE_ALL mode, calling _stabilize_dev for %s", spec)
            return self._stabilize_dev(g, spec, original)

        logger.info("  Unchanged: %s", spec)
        return original, "unchanged"

    # tries host symlink, guestfs realpath, then inference, each with its own logging/fallback branch
    def _stabilize_bypath(  # pylint: disable=too-many-branches
        self,
        g: guestfs.GuestFS,
        spec: str,
        original: str,
    ) -> tuple[str, str]:
        """
        Stabilize by-path reference to stable ID.

        Args:
            g: GuestFS handle
            spec: by-path spec (e.g., /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part1)
            original: Original spec before any processing

        Returns:
            Tuple of (converted_spec, reason)
        """
        logger.info("🔧 _stabilize_bypath: spec=%r, root_dev=%r", spec, self.root_dev)

        mapped: str | None = None

        # CRITICAL FIX: For VMCraft backend, by-path devices are on the HOST, not in guest filesystem
        # Use host-level symlink resolution first, fall back to guestfs realpath
        try:
            if os.path.exists(spec) and Path(spec).is_symlink():
                # Resolve symlink on host system
                real_dev = str(Path(spec).readlink())
                # Handle relative symlinks
                if not real_dev.startswith("/"):
                    real_dev = os.path.normpath(os.path.join(os.path.dirname(spec), real_dev))
                if real_dev.startswith("/dev/"):
                    mapped = real_dev
                    logger.info("  ✓ Resolved via host symlink: %s -> %s", spec, mapped)
        except OSError as e:
            logger.debug("  Host symlink resolution failed: %s", e)

        # Try guestfs realpath if host resolution didn't work
        if not mapped:
            try:
                rp = U.to_text(g.realpath(spec)).strip()
                # Only accept realpath result if it actually resolved to a DIFFERENT device
                if rp.startswith("/dev/") and rp != spec:
                    mapped = rp
                    logger.info("  ✓ Resolved via guestfs realpath: %s -> %s", spec, mapped)
                elif rp == spec:
                    logger.debug("  Guestfs realpath returned same path (no resolution): %s", spec)
            # backend-agnostic (native guestfs or VMCraft) call; various exception types possible, best-effort
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("  Guestfs realpath failed: %s", e)

        # If still not mapped, try inference helper (root_dev optional)
        if not mapped:
            mapped = Ident.infer_partition_from_bypath(spec, self.root_dev) if self.root_dev else None
            if mapped:
                logger.info("  ✓ Inferred from by-path: %s -> %s (root_dev=%s)", spec, mapped, self.root_dev)
            elif self.root_dev:
                logger.warning("  ✗ Inference failed despite root_dev=%s", self.root_dev)
            else:
                logger.warning("  ✗ Inference skipped: root_dev is None")

        if not mapped:
            logger.error("  ✗ FAILED to map by-path device: %s", spec)
            return original, "by-path-unresolved"

        # Get blkid info and choose stable ID
        logger.info("  🔍 Running blkid on mapped device: %s", mapped)
        blk = Ident.g_blkid_map(g, mapped)
        logger.info("  📋 Blkid result: %s", blk)
        stable = Ident.choose_stable(blk)
        if stable:
            logger.info("  ✅ Converted: %s -> %s", spec, stable)
            return stable, f"mapped:{mapped}"

        logger.warning("  ⚠️ No stable ID found for %s", mapped)
        return original, f"mapped:{mapped} no-id"

    def _stabilize_dev(
        self,
        g: guestfs.GuestFS,
        spec: str,
        original: str,
    ) -> tuple[str, str]:
        """
        Stabilize /dev/* reference to stable ID.

        Args:
            g: GuestFS handle
            spec: /dev/* spec (e.g., /dev/sda1)
            original: Original spec before any processing

        Returns:
            Tuple of (converted_spec, reason)
        """
        blk = Ident.g_blkid_map(g, spec)
        stable = Ident.choose_stable(blk)
        if stable:
            return stable, f"blkid:{spec}"

        return original, "dev-no-id"


__all__ = ["SpecConverter"]
