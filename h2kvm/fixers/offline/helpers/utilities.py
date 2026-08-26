# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Utility functions for offline VM fixing.

Provides common helper functions used across offline fixing operations.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
from typing import TYPE_CHECKING, Any

from h2kvm.converters.qemu.converter import Convert
from h2kvm.core.utils import U, blinking_progress

if TYPE_CHECKING:
    from pathlib import Path

    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=duplicate-code
        # This typing-only guestfs fallback stub is intentionally
        # duplicated in h2kvm/fixers/offline/operations/preflight.py:
        # each module needs its own self-contained TYPE_CHECKING guard, and
        # extracting a shared helper just for a type stub isn't worth the
        # added import coupling between these two independent modules.
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            # Typing-only fallback stub mimicking the real `guestfs` module
            # name/shape so `guestfs.GuestFS` type hints resolve even when
            # the real (optional, C-extension-backed) guestfs package isn't
            # installed. Renaming would defeat the point of mirroring the
            # real module's naming.
            class GuestFS(Protocol):  # pylint: disable=missing-class-docstring,too-few-public-methods
                ...


class OfflineUtilities:
    """Utility functions for offline VM operations."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize utilities.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def safe_umount_all(g: guestfs.GuestFS) -> None:
        """
        Safely unmount all filesystems in guest.

        Args:
            g: GuestFS instance
        """
        with contextlib.suppress(Exception):
            g.umount_all()

    def read_luks_key_bytes(
        self, luks_passphrase: str | None, luks_passphrase_env: str | None, luks_keyfile: Path | None
    ) -> bytes | None:
        """
        Read LUKS encryption key from various sources.

        Args:
            luks_passphrase: Direct passphrase string
            luks_passphrase_env: Environment variable name containing passphrase
            luks_keyfile: Path to keyfile

        Returns:
            LUKS key as bytes, or None if not available
        """
        # Try direct passphrase first
        if luks_passphrase:
            return luks_passphrase.encode("utf-8")

        # Try environment variable
        if luks_passphrase_env:
            val = os.environ.get(luks_passphrase_env)
            if val:
                return val.encode("utf-8")

        # Try keyfile
        if luks_keyfile and luks_keyfile.exists():
            try:
                return luks_keyfile.read_bytes()
            except OSError as e:
                self.logger.warning(f"Could not read LUKS keyfile {luks_keyfile}: {e}")

        return None

    def stash_guestfs_info(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Extract diagnostic information from guestfs for reporting.

        Args:
            g: GuestFS instance

        Returns:
            Dict with guestfs diagnostic info
        """
        info: dict[str, Any] = {}

        with contextlib.suppress(Exception):
            info["guestfs_version"] = g.version()

        with contextlib.suppress(Exception):
            info["available_space"] = g.available_all_groups()

        return info

    def resize_image_container(
        self, image: Path, resize: str, dry_run: bool = False
    ) -> dict[str, Any] | None:
        """
        Resize QEMU image container.

        Args:
            image: Path to image file
            resize: Resize specification (e.g., "+10G", "50G")
            dry_run: If True, skip actual resize

        Returns:
            Resize result dict, or None if resize not requested
        """
        if not resize:
            return None

        if dry_run:
            self.logger.info("DRY-RUN: skipping image resize")
            return {"image_resize": "skipped", "dry_run": True}

        try:
            # Get current image size
            info = Convert.qemu_img_info(self.logger, image)
            current_size = int(info.get("virtual-size", 0))

            if current_size <= 0:
                raise RuntimeError(
                    "Could not determine disk image size — qemu-img info did not report a virtual size. "
                    "The image file may be corrupted or in an unsupported format."
                )

            # Calculate new size
            if str(resize).startswith("+"):
                add = U.human_to_bytes(str(resize)[1:])
                new_size = current_size + add
            else:
                new_size = U.human_to_bytes(str(resize))

            # Check for shrink attempt
            if new_size < current_size:
                self.logger.warning("Shrink not supported (requested size < current size)")
                return {"image_resize": "skipped", "reason": "shrink_not_supported"}

            # Resize image
            cmd = ["qemu-img", "resize", str(image), str(new_size)]
            with subprocess.Popen(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True
            ) as proc:
                blinking_progress("Resizing image", proc)
                proc.wait()

                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, cmd)

            self.logger.info("Resized image to %s", U.human_bytes(new_size))
            return {"image_resize": "ok", "new_size": new_size, "old_size": current_size}

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort resize step: RuntimeError (bad qemu-img output),
            # unit-conversion errors, and subprocess failures must all
            # degrade to a reported failure rather than crash the fixer.
            self.logger.exception("Image resize failed: %s", e)
            return {"image_resize": "failed", "error": str(e)}
