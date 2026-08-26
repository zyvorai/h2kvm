# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/filesystem/fstab_stabilizer.py
"""
Comprehensive fstab stabilization for all Linux filesystems.

Converts unstable device paths to stable identifiers:
- /dev/sdX -> UUID= or PARTUUID=
- /dev/disk/by-path/... -> UUID=
- /dev/mapper/... -> stable identifier where possible
- btrfsvol:/dev/sdX/@subvol -> UUID=...,subvol=@subvol

Ensures reliable cross-hypervisor migration and boot stability.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .stable_mount import (
    DeviceIdentifiers,
    FilesystemMountOptions,
    convert_btrfs_subvol_spec,
    get_device_identifiers,
    get_recommended_fs_check_freq,
    is_stable_device_spec,
    log_fstab_conversion,
    normalize_fs_type,
    should_use_partuuid,
)

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs

logger = logging.getLogger(__name__)


@dataclass
class FstabEntry:  # pylint: disable=too-many-instance-attributes  # models every field of an /etc/fstab line
    """Parsed fstab entry."""

    spec: str  # Device specification
    mountpoint: str
    fs_type: str
    options: str
    dump: int
    pass_num: int
    original_line: str
    line_number: int
    comment: str | None = None


@dataclass
class FstabConversion:  # pylint: disable=too-many-instance-attributes  # models the full before/after result of one conversion
    """Result of converting a single fstab entry."""

    original_entry: FstabEntry
    new_spec: str | None
    new_options: str | None
    new_dump: int | None
    new_pass: int | None
    converted: bool
    reason: str
    identifiers: DeviceIdentifiers | None = None


class FstabStabilizer:
    """
    Convert fstab entries to use stable device identifiers.

    Handles all common Linux filesystems with appropriate options.
    """

    def __init__(
        self,
        g: guestfs.GuestFS,
        *,
        prefer_partuuid: bool = False,
        preserve_options: bool = True,
        optimize_options: bool = False,
        context: str = "hypervisor_migration",
    ):
        """
        Initialize fstab stabilizer.

        Args:
            g: GuestFS instance
            prefer_partuuid: Prefer PARTUUID over UUID (for cross-hypervisor stability)
            preserve_options: Keep existing mount options where possible
            optimize_options: Add recommended mount options for each filesystem
            context: Migration context (affects PARTUUID vs UUID preference)
        """
        self.g = g
        self.prefer_partuuid = prefer_partuuid
        self.preserve_options = preserve_options
        self.optimize_options = optimize_options
        self.context = context

        self.stats = {
            "total_entries": 0,
            "converted": 0,
            "already_stable": 0,
            "skipped": 0,
            "errors": 0,
        }

    def parse_fstab_line(self, line: str, line_number: int) -> FstabEntry | None:
        """
        Parse a single fstab line.

        Args:
            line: Line from /etc/fstab
            line_number: Line number (1-indexed)

        Returns:
            FstabEntry or None if line should be skipped
        """
        # Strip and check for empty/comment lines
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None

        # Split fields (handle tabs and spaces)
        fields = re.split(r"\s+", line.strip())
        if len(fields) < 4:
            logger.warning("fstab:%s: Invalid entry (too few fields)", line_number)
            return None

        spec = fields[0]
        mountpoint = fields[1]
        fs_type = fields[2]
        options = fields[3]
        dump = int(fields[4]) if len(fields) > 4 else 0
        pass_num = int(fields[5]) if len(fields) > 5 else 0

        return FstabEntry(
            spec=spec,
            mountpoint=mountpoint,
            fs_type=normalize_fs_type(fs_type),
            options=options,
            dump=dump,
            pass_num=pass_num,
            original_line=line,
            line_number=line_number,
        )

    def resolve_device_path(  # pylint: disable=too-many-return-statements,too-many-branches  # one branch per supported fstab spec format
        self, spec: str
    ) -> str | None:
        """
        Resolve device specification to actual device path.

        Handles:
        - /dev/sdX -> actual path
        - /dev/disk/by-path/... -> resolved device
        - /dev/disk/by-uuid/... -> resolved device
        - UUID=xxx -> /dev/... path
        - PARTUUID=xxx -> /dev/... path
        - btrfsvol:/dev/sdX/@subvol -> /dev/sdX

        Args:
            spec: Device specification from fstab

        Returns:
            Resolved device path or None if resolution fails
        """
        # Already a direct device path
        if spec.startswith("/dev/") and not spec.startswith("/dev/disk/"):
            # Handle btrfs subvolume specs
            if spec.startswith("btrfsvol:"):
                # Extract device part from btrfsvol:/dev/sdX/@subvol
                match = re.match(r"btrfsvol:(/dev/[^/@]+)", spec)
                if match:
                    return match.group(1)
            return spec

        # Resolve by-* symlinks
        if spec.startswith("/dev/disk/"):
            try:
                # GuestFS doesn't always support readlink, try direct resolution
                return spec  # Let guestfs handle it
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort resolution must not abort
                pass

        # UUID= or PARTUUID= specification
        if spec.startswith("UUID="):
            uuid = spec[5:]
            try:
                devices = self.g.findfs_uuid(uuid)
                return devices if devices else None
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort resolution must not abort
                logger.warning("Failed to resolve UUID=%s", uuid)
                return None

        if spec.startswith("PARTUUID="):
            partuuid = spec[9:]
            # GuestFS may not have findfs_partuuid, try blkid scan
            try:
                all_devices = self.g.list_devices() + list(self.g.list_partitions() or [])
                for dev in all_devices:
                    try:
                        blkid = self.g.blkid(dev)
                        if blkid.get("PARTUUID") == partuuid:
                            return dev
                    except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort resolution must not abort
                        continue
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort resolution must not abort
                logger.warning("Failed to resolve PARTUUID=%s", partuuid)

            return None

        # LABEL= specification
        if spec.startswith("LABEL="):
            label = spec[6:]
            try:
                devices = self.g.findfs_label(label)
                return devices if devices else None
            except Exception:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort resolution must not abort
                logger.warning("Failed to resolve LABEL=%s", label)
                return None

        return None

    def convert_entry(  # pylint: disable=too-many-return-statements  # one early-return per skip/error case for clarity
        self, entry: FstabEntry
    ) -> FstabConversion:
        """
        Convert a single fstab entry to use stable identifiers.

        Args:
            entry: Parsed fstab entry

        Returns:
            FstabConversion result
        """
        conversion = FstabConversion(
            original_entry=entry,
            new_spec=None,
            new_options=None,
            new_dump=None,
            new_pass=None,
            converted=False,
            reason="not_attempted",
        )

        # Skip special filesystems (tmpfs, proc, sysfs, etc.)
        special_fs = {"tmpfs", "devtmpfs", "sysfs", "proc", "devpts", "cgroup", "cgroup2", "securityfs"}
        if entry.fs_type in special_fs:
            conversion.reason = f"special_filesystem:{entry.fs_type}"
            self.stats["skipped"] += 1
            return conversion

        # Skip bind mounts
        if "bind" in entry.options.split(","):
            conversion.reason = "bind_mount"
            self.stats["skipped"] += 1
            return conversion

        # Check if already stable
        if is_stable_device_spec(entry.spec):
            conversion.reason = "already_stable"
            self.stats["already_stable"] += 1
            return conversion

        # Resolve device path
        device_path = self.resolve_device_path(entry.spec)
        if not device_path:
            conversion.reason = "device_not_found"
            self.stats["errors"] += 1
            logger.warning("fstab:%s: Could not resolve %s", entry.line_number, entry.spec)
            return conversion

        # Get device identifiers
        try:
            identifiers = get_device_identifiers(self.g, device_path)
            conversion.identifiers = identifiers
        except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort conversion must not abort
            conversion.reason = f"identifier_lookup_failed:{e}"
            self.stats["errors"] += 1
            logger.warning("fstab:%s: Failed to get identifiers for %s: %s", entry.line_number, device_path, e)
            return conversion

        # Handle Btrfs subvolume specifications
        if entry.spec.startswith("btrfsvol:") or entry.fs_type == "btrfs":
            new_spec = convert_btrfs_subvol_spec(
                entry.spec, identifiers, prefer_partuuid=self.prefer_partuuid
            )
        else:
            # Determine whether to use PARTUUID or UUID
            use_partuuid = (
                should_use_partuuid(entry.mountpoint, entry.fs_type, self.context) or self.prefer_partuuid
            )

            new_spec = identifiers.get_stable_spec(prefer_partuuid=use_partuuid)

        if not new_spec:
            conversion.reason = "no_stable_identifier_available"
            self.stats["errors"] += 1
            logger.warning("fstab:%s: No stable identifier for %s", entry.line_number, device_path)
            return conversion

        # Build mount options
        if self.optimize_options:
            fs_opts = FilesystemMountOptions.for_filesystem(entry.fs_type)
            existing_opts = entry.options.split(",") if self.preserve_options else []
            new_options = fs_opts.build_options_string(
                readonly="ro" in existing_opts,
                preserve_existing=existing_opts if self.preserve_options else None,
            )
        else:
            new_options = entry.options  # Keep original options

        # Get recommended fsck settings
        dump, pass_num = get_recommended_fs_check_freq(entry.fs_type, entry.mountpoint)

        # Set conversion results
        conversion.new_spec = new_spec
        conversion.new_options = new_options
        conversion.new_dump = dump
        conversion.new_pass = pass_num
        conversion.converted = True
        conversion.reason = "success"

        # Log the conversion
        log_fstab_conversion(entry.spec, new_spec, entry.mountpoint, entry.fs_type)

        self.stats["converted"] += 1
        return conversion

    def format_fstab_line(self, entry: FstabEntry, conversion: FstabConversion) -> str:
        """
        Format a converted fstab entry as a line.

        Args:
            entry: Original entry
            conversion: Conversion result

        Returns:
            Formatted fstab line
        """
        if not conversion.converted:
            return entry.original_line

        spec = conversion.new_spec or entry.spec
        options = conversion.new_options or entry.options
        dump = conversion.new_dump if conversion.new_dump is not None else entry.dump
        pass_num = conversion.new_pass if conversion.new_pass is not None else entry.pass_num

        # Format with proper spacing (aligned columns)
        return f"{spec:<40} {entry.mountpoint:<20} {entry.fs_type:<10} {options:<30} {dump} {pass_num}"

    def stabilize_fstab(self, fstab_path: str = "/etc/fstab") -> dict[str, Any]:
        """
        Stabilize an entire fstab file.

        Args:
            fstab_path: Path to fstab file in guest filesystem

        Returns:
            Statistics dict with conversion results
        """
        result = {
            "success": False,
            "fstab_path": fstab_path,
            "stats": {},
            "conversions": [],
            "errors": [],
        }

        # Read fstab
        try:
            fstab_content = self.g.read_file(fstab_path)
            if isinstance(fstab_content, bytes):
                fstab_content = fstab_content.decode("utf-8", errors="replace")

            # Log original fstab
            logger.info("📄 Original %s:", fstab_path)
            for line_num, line in enumerate(fstab_content.splitlines(), 1):
                logger.info("  %3d: %s", line_num, line)
        except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort read must not abort the migration
            result["errors"].append(f"Failed to read {fstab_path}: {e}")
            return result

        # Parse and convert entries
        new_lines = []
        for line_num, line in enumerate(fstab_content.splitlines(), 1):
            self.stats["total_entries"] += 1

            # Handle comments and empty lines
            if not line.strip() or line.strip().startswith("#"):
                new_lines.append(line)
                continue

            # Parse entry
            entry = self.parse_fstab_line(line, line_num)
            if not entry:
                new_lines.append(line)
                continue

            # Convert entry
            conversion = self.convert_entry(entry)
            result["conversions"].append(
                {
                    "line": line_num,
                    "original": entry.spec,
                    "new": conversion.new_spec,
                    "mountpoint": entry.mountpoint,
                    "fs_type": entry.fs_type,
                    "converted": conversion.converted,
                    "reason": conversion.reason,
                }
            )

            # Format new line
            new_line = self.format_fstab_line(entry, conversion)
            new_lines.append(new_line)

        # Write updated fstab
        try:
            new_fstab_content = "\n".join(new_lines) + "\n"

            # Log changes made
            logger.info("\n📝 Fstab conversions summary:")
            for conv in result["conversions"]:
                if conv["converted"]:
                    logger.info(
                        "  Line %3d: %-50s -> %-50s (%s)",
                        conv["line"],
                        conv["original"],
                        conv["new"],
                        conv["mountpoint"],
                    )

            # Log new fstab
            logger.info("\n📄 Updated %s:", fstab_path)
            for line_num, line in enumerate(new_lines, 1):
                logger.info("  %3d: %s", line_num, line)

            self.g.write(fstab_path, new_fstab_content)
            result["success"] = True
            logger.info(
                "\n✅ Stabilized %s: %s of %s entries converted",
                fstab_path,
                self.stats["converted"],
                self.stats["total_entries"],
            )
        except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs API errors are dynamic/untyped; best-effort write must not abort the migration
            result["errors"].append(f"Failed to write {fstab_path}: {e}")
            return result

        result["stats"] = self.stats.copy()
        return result
