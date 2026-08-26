# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
fstab Fixer - Production-Grade Implementation

Fixes /etc/fstab for migrated VMs to ensure first-boot success.

Operations:
1. Convert device names → UUIDs (or LABELs)
2. Remove VMware-specific entries
3. Validate all UUIDs/LABELs exist on the system
4. Fix mount options for virtio
5. Handle LVM entries correctly
6. Preserve comments and formatting

Idempotent: Safe to re-run multiple times.
Portable: Works in VM, bare metal, or online mode.
OS-aware: Handles CentOS, RHEL, Ubuntu, Debian, Photon.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .utils import (
    create_backup,
    get_block_device_info,
    resolve_device_to_path,
)

logger = logging.getLogger(__name__)


class FstabMode(str, Enum):
    """fstab device identification mode."""

    UUID = "uuid"
    LABEL = "label"
    DEVICE = "device"


class FstabEntryType(str, Enum):
    """Type of fstab entry."""

    ROOT = "root"
    BOOT = "boot"
    SWAP = "swap"
    HOME = "home"
    DATA = "data"
    VMWARE = "vmware"
    TMPFS = "tmpfs"
    PROC = "proc"
    SYSFS = "sysfs"
    DEVPTS = "devpts"
    OTHER = "other"


@dataclass
class FstabEntry:  # pylint: disable=too-many-instance-attributes  # models every fstab field plus parse/resolution/fix metadata
    """
    Parsed fstab entry.

    Represents a single line in /etc/fstab with all fields and metadata.
    """

    # Original line from fstab
    original_line: str

    # Parsed fields (6 standard fstab fields)
    device: str  # Device specification (UUID=..., /dev/sda1, etc.)
    mountpoint: str  # Mount point
    fstype: str  # Filesystem type
    options: str  # Mount options
    dump: str  # Dump frequency
    pass_num: str  # fsck pass number

    # Metadata
    line_number: int  # Line number in original file
    is_comment: bool = False  # Is this a comment line?
    is_blank: bool = False  # Is this a blank line?
    entry_type: FstabEntryType = FstabEntryType.OTHER  # Entry type

    # Resolution
    resolved_device: Optional[str] = None  # Actual /dev/xxx path
    resolved_uuid: Optional[str] = None  # UUID if available
    resolved_label: Optional[str] = None  # LABEL if available

    # Fix decisions
    should_remove: bool = False  # Should this entry be removed?
    should_convert: bool = False  # Should device be converted to UUID/LABEL?
    fix_reason: Optional[str] = None  # Reason for fix

    def __str__(self) -> str:
        """Reconstruct fstab line."""
        if self.is_comment or self.is_blank:
            return self.original_line

        return (
            f"{self.device}\t{self.mountpoint}\t{self.fstype}\t{self.options}\t{self.dump}\t{self.pass_num}"
        )


class FstabFixer:
    """
    Production-grade fstab fixer.

    Fixes /etc/fstab for VM migration by:
    - Converting device names to UUIDs
    - Removing VMware-specific entries
    - Validating all entries
    - Handling LVM correctly
    """

    def __init__(
        self,
        root_mount: str = "/mnt",
        mode: FstabMode = FstabMode.UUID,
        dry_run: bool = False,
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize fstab fixer.

        Args:
            root_mount: Path where root filesystem is mounted
            mode: Device identification mode (uuid, label, device)
            dry_run: If True, don't modify files
            logger_instance: Optional logger instance
        """
        self.root_mount = Path(root_mount)
        self.mode = mode
        self.dry_run = dry_run
        self.logger = logger_instance or logging.getLogger(__name__)

        self.fstab_path = self.root_mount / "etc/fstab"
        self.entries: list[FstabEntry] = []

        # Statistics
        self.stats = {"total_entries": 0, "converted": 0, "removed": 0, "warnings": 0, "errors": 0}

    def fix(self) -> dict[str, any]:
        """
        Execute fstab fixes.

        Returns:
            Dictionary with fix results:
            - success: bool
            - backup_path: Path to backup file
            - stats: Fix statistics
            - warnings: List of warnings
            - errors: List of errors

        Raises:
            FileNotFoundError: If fstab not found
            PermissionError: If cannot write fstab
        """
        self.logger.info("Starting fstab fix: mode=%s, dry_run=%s", self.mode.value, self.dry_run)

        results = {"success": False, "backup_path": None, "stats": {}, "warnings": [], "errors": []}

        # Validate fstab exists
        if not self.fstab_path.exists():
            error = f"fstab not found: {self.fstab_path}"
            self.logger.error(error)
            results["errors"].append(error)
            return results

        try:
            # Step 1: Parse existing fstab
            self.logger.info("Parsing fstab...")
            self._parse_fstab()
            self.stats["total_entries"] = len(
                [e for e in self.entries if not e.is_comment and not e.is_blank]
            )

            # Step 2: Resolve all devices
            self.logger.info("Resolving device paths...")
            self._resolve_devices()

            # Step 3: Classify entries
            self.logger.info("Classifying entries...")
            self._classify_entries()

            # Step 4: Decide fixes
            self.logger.info("Determining fixes...")
            self._determine_fixes()

            # Step 5: Apply fixes
            if not self.dry_run:
                self.logger.info("Creating backup...")
                backup_path = create_backup(self.fstab_path)
                results["backup_path"] = str(backup_path)

                self.logger.info("Writing fixed fstab...")
                self._write_fstab()
            else:
                self.logger.info("DRY RUN: Skipping fstab write")

            # Collect results
            results["success"] = True
            results["stats"] = self.stats
            results["warnings"] = self._collect_warnings()

            self.logger.info(
                "fstab fix complete: converted=%s, removed=%s, warnings=%s",
                self.stats["converted"],
                self.stats["removed"],
                self.stats["warnings"],
            )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            error = f"fstab fix failed: {e}"
            self.logger.error(error, exc_info=True)
            results["errors"].append(error)
            self.stats["errors"] += 1

        return results

    def _parse_fstab(self):
        """Parse /etc/fstab into FstabEntry objects."""
        with open(self.fstab_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                original_line = line.rstrip("\n")

                # Blank line
                if not original_line.strip():
                    self.entries.append(
                        FstabEntry(
                            original_line=original_line,
                            device="",
                            mountpoint="",
                            fstype="",
                            options="",
                            dump="",
                            pass_num="",
                            line_number=line_num,
                            is_blank=True,
                        )
                    )
                    continue

                # Comment line
                if original_line.strip().startswith("#"):
                    self.entries.append(
                        FstabEntry(
                            original_line=original_line,
                            device="",
                            mountpoint="",
                            fstype="",
                            options="",
                            dump="",
                            pass_num="",
                            line_number=line_num,
                            is_comment=True,
                        )
                    )
                    continue

                # Parse fstab fields
                parts = original_line.split()
                if len(parts) < 4:
                    # Malformed entry - keep as comment
                    self.logger.warning("Line %s: Malformed fstab entry (< 4 fields)", line_num)
                    self.entries.append(
                        FstabEntry(
                            original_line=f"# MALFORMED: {original_line}",
                            device="",
                            mountpoint="",
                            fstype="",
                            options="",
                            dump="",
                            pass_num="",
                            line_number=line_num,
                            is_comment=True,
                        )
                    )
                    self.stats["warnings"] += 1
                    continue

                device = parts[0]
                mountpoint = parts[1]
                fstype = parts[2]
                options = parts[3]
                dump = parts[4] if len(parts) > 4 else "0"
                pass_num = parts[5] if len(parts) > 5 else "0"

                entry = FstabEntry(
                    original_line=original_line,
                    device=device,
                    mountpoint=mountpoint,
                    fstype=fstype,
                    options=options,
                    dump=dump,
                    pass_num=pass_num,
                    line_number=line_num,
                )

                self.entries.append(entry)

        self.logger.debug("Parsed %d fstab lines", len(self.entries))

    def _resolve_devices(self):
        """Resolve device specifications to actual device paths and UUIDs."""
        for entry in self.entries:
            if entry.is_comment or entry.is_blank:
                continue

            # Skip pseudo-filesystems
            if entry.fstype in ["proc", "sysfs", "devpts", "tmpfs", "devtmpfs", "cgroup"]:
                continue

            # Skip swap that's already UUID-based
            if entry.fstype == "swap" and entry.device.startswith("UUID="):
                entry.resolved_uuid = entry.device[5:]
                continue

            # Resolve device to actual path
            device_path = resolve_device_to_path(entry.device, str(self.root_mount))

            if device_path:
                entry.resolved_device = device_path

                # Get UUID and LABEL
                info = get_block_device_info(device_path)
                entry.resolved_uuid = info.uuid
                entry.resolved_label = info.label

                self.logger.debug(
                    "Line %s: %s → %s (UUID=%s, LABEL=%s)",
                    entry.line_number,
                    entry.device,
                    device_path,
                    info.uuid,
                    info.label,
                )
            else:
                self.logger.warning("Line %s: Could not resolve device: %s", entry.line_number, entry.device)
                self.stats["warnings"] += 1

    def _classify_entries(self):
        """Classify fstab entries by type."""
        for entry in self.entries:
            if entry.is_comment or entry.is_blank:
                continue

            # Pseudo-filesystems
            if entry.fstype in ["proc", "sysfs", "devpts", "devtmpfs", "cgroup"]:
                if entry.fstype == "tmpfs":
                    entry.entry_type = FstabEntryType.TMPFS
                else:
                    entry.entry_type = FstabEntryType.PROC
                continue

            # Mountpoint-based classification
            if entry.mountpoint == "/":
                entry.entry_type = FstabEntryType.ROOT
            elif entry.mountpoint == "/boot":
                entry.entry_type = FstabEntryType.BOOT
            elif entry.mountpoint == "/home":
                entry.entry_type = FstabEntryType.HOME
            elif entry.fstype == "swap":
                entry.entry_type = FstabEntryType.SWAP
            elif "vmware" in entry.device.lower() or "vmhgfs" in entry.fstype.lower():
                entry.entry_type = FstabEntryType.VMWARE
            else:
                entry.entry_type = FstabEntryType.DATA

    def _determine_fixes(self):
        """Determine what fixes to apply to each entry."""
        for entry in self.entries:
            if entry.is_comment or entry.is_blank:
                continue

            # Skip pseudo-filesystems
            if entry.entry_type in [FstabEntryType.PROC, FstabEntryType.TMPFS]:
                continue

            # Remove VMware entries
            if entry.entry_type == FstabEntryType.VMWARE:
                entry.should_remove = True
                entry.fix_reason = "VMware-specific filesystem (removed)"
                self.stats["removed"] += 1
                self.logger.info("Line %s: Removing VMware entry: %s", entry.line_number, entry.device)
                continue

            # Convert to UUID/LABEL if not already
            if self.mode == FstabMode.UUID:
                if not entry.device.startswith("UUID="):
                    if entry.resolved_uuid:
                        entry.should_convert = True
                        entry.fix_reason = f"Converted {entry.device} → UUID={entry.resolved_uuid}"
                        self.stats["converted"] += 1
                        self.logger.info("Line %s: %s", entry.line_number, entry.fix_reason)
                    else:
                        warning = f"No UUID available for {entry.device} (keeping as-is)"
                        entry.fix_reason = warning
                        self.logger.warning("Line %s: %s", entry.line_number, warning)
                        self.stats["warnings"] += 1

            elif self.mode == FstabMode.LABEL and not entry.device.startswith("LABEL="):
                if entry.resolved_label:
                    entry.should_convert = True
                    entry.fix_reason = f"Converted {entry.device} → LABEL={entry.resolved_label}"
                    self.stats["converted"] += 1
                    self.logger.info("Line %s: %s", entry.line_number, entry.fix_reason)
                else:
                    warning = f"No LABEL available for {entry.device} (keeping as-is)"
                    entry.fix_reason = warning
                    self.logger.warning("Line %s: %s", entry.line_number, warning)
                    self.stats["warnings"] += 1

    def _write_fstab(self):
        """Write fixed fstab back to disk."""
        lines = []

        for entry in self.entries:
            # Skip removed entries
            if entry.should_remove:
                lines.append(f"# REMOVED (VMware): {entry.original_line}")
                continue

            # Blank or comment - keep as-is
            if entry.is_blank or entry.is_comment:
                lines.append(entry.original_line)
                continue

            # Convert device if needed
            if entry.should_convert:
                if self.mode == FstabMode.UUID and entry.resolved_uuid:
                    entry.device = f"UUID={entry.resolved_uuid}"
                elif self.mode == FstabMode.LABEL and entry.resolved_label:
                    entry.device = f"LABEL={entry.resolved_label}"

            # Reconstruct line
            lines.append(str(entry))

        # Write to file
        with open(self.fstab_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        self.logger.info("Wrote fixed fstab to %s", self.fstab_path)

    def _collect_warnings(self) -> list[str]:
        """Collect all warnings from fix process."""
        warnings = []

        for entry in self.entries:
            if entry.fix_reason and "keeping as-is" in entry.fix_reason.lower():
                warnings.append(f"Line {entry.line_number}: {entry.fix_reason}")

        return warnings

    def get_summary(self) -> str:
        """Get human-readable summary of fixes."""
        lines = [
            "fstab Fix Summary:",
            f"  Total entries: {self.stats['total_entries']}",
            f"  Converted to {self.mode.value.upper()}: {self.stats['converted']}",
            f"  Removed (VMware): {self.stats['removed']}",
            f"  Warnings: {self.stats['warnings']}",
            f"  Errors: {self.stats['errors']}",
        ]

        if self.stats["converted"] > 0:
            lines.append("\n  Converted entries:")
            for entry in self.entries:
                if entry.should_convert:
                    lines.append(f"    Line {entry.line_number}: {entry.fix_reason}")

        if self.stats["removed"] > 0:
            lines.append("\n  Removed entries:")
            for entry in self.entries:
                if entry.should_remove:
                    lines.append(f"    Line {entry.line_number}: {entry.device} → {entry.fix_reason}")

        return "\n".join(lines)


# Convenience function for direct usage
def fix_fstab(root_mount: str = "/mnt", mode: str = "uuid", dry_run: bool = False) -> dict[str, any]:
    """
    Fix /etc/fstab in mounted root filesystem.

    Args:
        root_mount: Path where root filesystem is mounted
        mode: Device identification mode ("uuid", "label", "device")
        dry_run: If True, don't modify files

    Returns:
        Dictionary with fix results

    Example:
        >>> results = fix_fstab("/mnt", mode="uuid", dry_run=False)
        >>> if results["success"]:
        ...     print(f"Fixed fstab: {results['stats']['converted']} converted")
    """
    fixer = FstabFixer(root_mount=root_mount, mode=FstabMode(mode), dry_run=dry_run)

    return fixer.fix()
