# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Root filesystem detection for offline VMs.

Provides heuristics for identifying and validating root filesystems.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hyper2kvm.core.utils import U

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore  # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            """Typing-only stand-in for the ``guestfs`` module when python-guestfs isn't installed."""

            class GuestFS(Protocol):  # pylint: disable=missing-class-docstring,too-few-public-methods
                """Typing-only stand-in for ``guestfs.GuestFS`` used solely for annotations."""


class RootDetector:
    """Detects and validates root filesystems in VMs."""

    # Root filesystem hint files
    _ROOT_HINT_FILES = ["/etc/fstab", "/etc/os-release", "/bin/sh", "/sbin/init"]

    # Strong root filesystem indicators
    _ROOT_STRONG_HINTS = ["/etc/passwd", "/usr/bin/env", "/var/lib", "/proc"]

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize root detector.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def looks_like_root(  # pylint: disable=too-many-branches  # weighs many independent OS-detection heuristics
        self, g: guestfs.GuestFS
    ) -> bool:
        """
        Check if currently mounted filesystem looks like a root filesystem.

        Uses multiple heuristics to detect Windows and Linux root filesystems
        while avoiding false positives from /boot partitions.

        Args:
            g: GuestFS instance (with potential root already mounted)

        Returns:
            True if filesystem appears to be a root filesystem
        """
        try:
            # Windows detection: check for system directories
            windows_hits = 0
            for path in ["/Windows/System32", "/WINDOWS/system32", "/windows/system32"]:
                try:
                    if g.is_dir(path):
                        windows_hits += 1
                except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort detection must not abort
                    pass

            if windows_hits >= 1:
                self.logger.info("🔍 Accepted: Windows root detected (%s indicators found)", windows_hits)
                return True

            # Best Linux root signal: /etc/os-release
            has_os_release = g.is_file("/etc/os-release")
            if has_os_release:
                self.logger.info("🔍 Accepted: has /etc/os-release (definitive Linux root indicator)")
                return True

            # Gather Linux diagnostic information
            has_etc = g.is_dir("/etc")

            # Check for systemd
            has_systemd = (
                g.is_file("/usr/bin/systemctl")
                or g.is_file("/usr/lib/systemd/systemd")
                or g.is_file("/lib/systemd/systemd")
            )

            # Check for shell
            has_shell = g.is_file("/bin/bash") or g.is_file("/usr/bin/bash") or g.is_file("/bin/sh")

            # Check top-level for boot signatures
            has_vmlinuz = False
            has_initramfs = False
            try:
                top_files = [U.to_text(x) for x in g.ls("/") if U.to_text(x)]
                has_vmlinuz = any(name.startswith("vmlinuz-") for name in top_files)
                has_initramfs = any(name.startswith("initramfs-") for name in top_files)
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort detection must not abort
                pass

            # Check for boot directories
            has_boot_dirs = (
                g.is_dir("/grub2") or g.is_dir("/grub") or g.is_dir("/efi") or g.is_dir("/loader")
            )

            # CRITICAL: Reject /boot partitions
            # /boot has kernel/initramfs at top-level + boot directories + no /etc/os-release
            if (has_vmlinuz or has_initramfs) and has_boot_dirs:
                self.logger.info(
                    "🔍 Rejected: looks like /boot (vmlinuz=%s, initramfs=%s, boot_dirs=%s)",
                    has_vmlinuz,
                    has_initramfs,
                    has_boot_dirs,
                )
                return False

            # Secondary Linux root signal: /etc + (systemd OR shell)
            if has_etc and (has_systemd or has_shell):
                self.logger.info(
                    "🔍 Accepted: Linux root with /etc + systemd/shell (etc=%s, systemd=%s, shell=%s)",
                    has_etc,
                    has_systemd,
                    has_shell,
                )
                return True

            # If we can't prove it's root, treat as not-root (safer)
            self.logger.info(
                "🔍 Rejected: insufficient root indicators "
                "(windows_hits=%s, os_release=%s, etc=%s, systemd=%s, shell=%s)",
                windows_hits,
                has_os_release,
                has_etc,
                has_systemd,
                has_shell,
            )
            return False

        except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort detection must not abort
            self.logger.debug("Error in root detection: %s", e)
            return False

    def score_root(  # pylint: disable=too-many-branches  # accumulates score across many independent guestfs heuristics
        self, g: guestfs.GuestFS
    ) -> int:
        """
        Score how likely the current mount is a root filesystem.

        Higher scores indicate stronger evidence of being a root filesystem.
        Helps disambiguate between multiple candidate partitions.

        Args:
            g: GuestFS instance

        Returns:
            Root score (higher = more likely to be root)
        """
        score = 0

        # Check hint files
        for p in self._ROOT_HINT_FILES:
            try:
                if g.is_file(p):
                    score += 5
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort scoring must not abort
                pass

        # Check strong hints
        for p in self._ROOT_STRONG_HINTS:
            try:
                if p.endswith("/"):
                    if g.is_dir(p[:-1]):
                        score += 2
                elif g.is_file(p) or g.is_dir(p):
                    score += 2
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort scoring must not abort
                pass

        # Bonus for /etc/os-release (definitive)
        try:
            if g.is_file("/etc/os-release"):
                score += 10
        except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort scoring must not abort
            pass

        # Bonus for init system
        try:
            if g.is_file("/usr/lib/systemd/systemd") or g.is_file("/sbin/init"):
                score += 5
        except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort scoring must not abort
            pass

        # Penalty for ISO/installer images
        try:
            if g.is_file("/.discinfo") or g.is_file("/isolinux/isolinux.cfg"):
                score -= 20
        except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort scoring must not abort
            pass

        return score

    def path_exists_case_insensitive(self, g: guestfs.GuestFS, path: str) -> bool:
        """
        Check if path exists (case-insensitive for Windows compatibility).

        Args:
            g: GuestFS instance
            path: Path to check

        Returns:
            True if path exists (case-insensitive)
        """
        try:
            # Try exact match first (fast path)
            if g.exists(path):
                return True

            # For Windows paths, try case-insensitive search
            parts = path.strip("/").split("/")
            if not parts or not parts[0]:
                return False

            current = "/"
            for part in parts:
                if not part:
                    continue

                try:
                    entries = g.ls(current)
                    entries_text = [U.to_text(e).lower() for e in entries]
                    part_lower = part.lower()

                    if part_lower in entries_text:
                        # Find the actual entry with matching case-insensitive name
                        idx = entries_text.index(part_lower)
                        actual_name = U.to_text(entries[idx])
                        current = f"{current.rstrip('/')}/{actual_name}"
                    else:
                        return False
                except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort lookup must not abort
                    return False

            return g.exists(current)

        except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort lookup must not abort
            return False
