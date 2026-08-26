# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/offline/config_rewriter.py
"""
In-guest configuration file rewriting (fstab, crypttab).

This module handles rewriting /etc/fstab and /etc/crypttab to use stable
device identifiers (UUID, PARTUUID, LABEL) instead of potentially unstable
names like /dev/sda1 or by-path references.

Extracted from offline_fixer.py to provide single-responsibility module
for configuration rewriting logic.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U
from h2kvm.fixers.filesystem.fstab import _BYPATH_PREFIX, IGNORE_MOUNTPOINTS, Change, FstabMode, Ident

if TYPE_CHECKING:
    import logging

    from h2kvm.core.guestfs_typing import guestfs

    from .spec_converter import SpecConverter


class FstabCrypttabRewriter:
    """
    Rewriter for /etc/fstab and /etc/crypttab files.

    Stabilizes device identifiers in configuration files to prevent boot failures
    when moving VMs between different hypervisors or hardware.
    """

    def __init__(  # pylint: disable=too-many-arguments  # config init, all keyword-only flags
        self,
        logger: logging.Logger,
        spec_converter: SpecConverter,
        *,
        dry_run: bool = False,
        no_backup: bool = False,
        print_fstab: bool = False,
        fstab_mode: FstabMode = FstabMode.BYPATH_ONLY,
    ):
        """
        Initialize config rewriter.

        Args:
            logger: Logger instance
            spec_converter: SpecConverter instance for device ID conversion
            dry_run: If True, don't make actual changes
            no_backup: If True, skip backup creation
            print_fstab: If True, print fstab before/after to stdout
            fstab_mode: Conversion policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
        """
        self.logger = logger
        self.spec_converter = spec_converter
        self.dry_run = dry_run
        self.no_backup = no_backup
        self.print_fstab = print_fstab
        self.fstab_mode = fstab_mode

    def backup_file(self, g: guestfs.GuestFS, path: str) -> None:
        """
        Create timestamped backup of a file in the guest.

        Args:
            g: GuestFS handle
            path: Path to file in guest
        """
        if self.no_backup or self.dry_run:
            return

        try:
            if not g.is_file(path):
                return
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guestfs check, must not abort the fixer
            return

        backup_path = f"{path}.backup.h2kvm.{U.now_ts()}"
        try:
            g.cp(path, backup_path)
            self.logger.debug(f"Backup: {path} -> {backup_path}")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort backup, must not abort the fixer
            self.logger.warning(f"Backup failed for {path}: {e}")

    # fstab parsing/rewriting is inherently a single linear pass; splitting it
    # up would obscure the line-by-line rewrite logic.
    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def rewrite_fstab(self, g: guestfs.GuestFS) -> tuple[int, list[Change], dict[str, Any]]:
        """
        Rewrite /etc/fstab with stable device identifiers.

        Args:
            g: GuestFS handle with root filesystem mounted

        Returns:
            Tuple of (num_changes, change_list, audit_info) where:
            - num_changes: Number of lines changed
            - change_list: List of Change objects describing each change
            - audit_info: Dict with statistics (total_lines, entries, etc.)
        """
        fstab = "/etc/fstab"

        if self.fstab_mode == FstabMode.NOOP:
            self.logger.info("fstab: mode=noop (skipping)")
            return 0, [], {"reason": "noop"}

        try:
            if not g.is_file(fstab):
                self.logger.warning("fstab: /etc/fstab not found; skipping")
                return 0, [], {"reason": "missing"}
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guestfs check, must not abort the fixer
            self.logger.warning("fstab: /etc/fstab check failed; skipping")
            return 0, [], {"reason": "missing"}

        before = U.to_text(g.read_file(fstab))

        # Always log original fstab
        self.logger.info("\n📄 Original /etc/fstab:")
        for line_num, line in enumerate(before.splitlines(), 1):
            self.logger.info(f"  {line_num:3d}: {line}")

        if self.print_fstab:
            print("\n--- /etc/fstab (before) ---\n" + before)

        lines = before.splitlines()
        out_lines: list[str] = []
        changes: list[Change] = []
        total = 0
        entries = 0
        bypath = 0

        for idx, line in enumerate(lines, 1):
            total += 1
            s = line.strip()

            if not s or s.startswith("#"):
                out_lines.append(line)
                continue

            cols = s.split()
            if len(cols) < 4:
                out_lines.append(line)
                continue

            spec, mp = cols[0], cols[1]

            if mp in IGNORE_MOUNTPOINTS:
                out_lines.append(line)
                continue

            entries += 1
            if spec.startswith(_BYPATH_PREFIX):
                bypath += 1

            if self.fstab_mode == FstabMode.BYPATH_ONLY and not (
                spec.startswith((_BYPATH_PREFIX, "btrfsvol:"))
            ):
                out_lines.append(line)
                continue

            new_spec, reason = self.spec_converter.convert_spec(g, spec)
            if new_spec != spec:
                cols[0] = new_spec
                out_lines.append("\t".join(cols))
                changes.append(Change(idx, mp, spec, new_spec, reason))
            else:
                out_lines.append(line)

        audit = {
            "total_lines": total,
            "entries": entries,
            "bypath_entries": bypath,
            "changed_entries": len(changes),
        }

        self.logger.info(
            f"fstab scan: total_lines={total} entries={entries} "
            f"bypath_entries={bypath} changed_entries={len(changes)}"
        )

        # /tmp sanity check (common for some minimal images)
        self._ensure_tmp_sanity(g)

        if not changes:
            if self.print_fstab:
                print("\n--- /etc/fstab (after - unchanged) ---\n" + before)
            return 0, [], audit

        # Log changes summary
        self.logger.info("\n📝 Fstab conversions summary:")
        for ch in changes:
            self.logger.info(
                f"  Line {ch.line_no:3d}: {ch.old:50s} -> {ch.new:50s} ({ch.mountpoint}) [{ch.reason}]"
            )

        after = "\n".join(out_lines) + "\n"

        # Always log updated fstab
        self.logger.info("\n📄 Updated /etc/fstab:")
        for line_num, line in enumerate(out_lines, 1):
            self.logger.info(f"  {line_num:3d}: {line}")

        if self.print_fstab:
            print("\n--- /etc/fstab (after) ---\n" + after)

        if self.dry_run:
            self.logger.info(f"fstab: DRY-RUN: would apply {len(changes)} change(s).")
            return len(changes), changes, audit

        # Apply changes
        self.backup_file(g, fstab)
        g.write(fstab, after.encode("utf-8"))
        self.logger.info(f"/etc/fstab updated ({len(changes)} changes).")

        return len(changes), changes, audit

    def _ensure_tmp_sanity(self, g: guestfs.GuestFS) -> None:
        """
        Ensure /tmp directory exists and has correct permissions.

        Args:
            g: GuestFS handle
        """
        try:
            if not g.is_dir("/tmp"):
                self.logger.info("Fixing /tmp: creating directory inside guest")
                if not self.dry_run:
                    g.mkdir_p("/tmp")
                    with contextlib.suppress(Exception):
                        g.chmod(0o1777, "/tmp")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guestfs fixup, must not abort the fixer
            self.logger.warning(f"/tmp sanity fix failed: {e}")

    def rewrite_crypttab(self, g: guestfs.GuestFS) -> int:
        """
        Rewrite /etc/crypttab with stable device identifiers.

        Args:
            g: GuestFS handle with root filesystem mounted

        Returns:
            Number of lines changed
        """
        path = "/etc/crypttab"

        try:
            if not g.is_file(path):
                return 0
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guestfs check, must not abort the fixer
            return 0

        before = U.to_text(g.read_file(path))
        out: list[str] = []
        changed = 0
        lines = before.splitlines()

        for line in lines:
            s = line.strip()

            if not s or s.startswith("#"):
                out.append(line)
                continue

            cols = s.split()
            if len(cols) < 2:
                out.append(line)
                continue

            name, spec = cols[0], cols[1]

            if Ident.is_stable(spec):
                out.append(line)
                continue

            if self.fstab_mode == FstabMode.BYPATH_ONLY and not (
                spec.startswith((_BYPATH_PREFIX, "btrfsvol:"))
            ):
                out.append(line)
                continue

            new_spec, reason = self.spec_converter.convert_spec(g, spec)
            if new_spec != spec:
                cols[1] = new_spec
                out.append(" ".join(cols))
                changed += 1
                self.logger.info(f"crypttab: {name}: {spec} -> {new_spec} [{reason}]")
            else:
                out.append(line)

        if changed == 0:
            return 0

        after = "\n".join(out) + "\n"

        if self.dry_run:
            self.logger.info(f"crypttab: DRY-RUN: would apply {changed} change(s).")
            return changed

        # Apply changes
        self.backup_file(g, path)
        g.write(path, after.encode("utf-8"))
        self.logger.info(f"/etc/crypttab updated ({changed} changes).")

        return changed


__all__ = ["FstabCrypttabRewriter"]
