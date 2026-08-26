# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Filesystem and partition probing helpers for VMCraft."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._runner import RunCommandFn, probe_stdout

if TYPE_CHECKING:
    import logging


def get_vfs_type(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> str:
    """Get filesystem type with blkid probe and lsblk fallback."""
    fstype = probe_stdout(
        logger,
        run_sudo,
        ["blkid", "-p", "-s", "TYPE", "-o", "value", device],
        debug_failure=True,
    )
    if fstype:
        return fstype

    fstype = probe_stdout(
        logger,
        run_sudo,
        ["lsblk", "-no", "FSTYPE", device],
        debug_failure=True,
    )
    if fstype:
        return fstype

    return ""


def get_vfs_uuid(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> str:
    """Get filesystem UUID for a block device."""
    return probe_stdout(logger, run_sudo, ["blkid", "-s", "UUID", "-o", "value", device])


def get_vfs_label(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> str:
    """Get filesystem label for a block device."""
    return probe_stdout(logger, run_sudo, ["blkid", "-s", "LABEL", "-o", "value", device])


def partition_to_number(partition: str) -> int:
    """Extract the partition number from a partition path."""
    m = re.match(r"^/dev/(?:nvme\d+n\d+|mmcblk\d+|nbd\d+|loop\d+)p(\d+)$", partition)
    if m:
        return int(m.group(1))

    m = re.match(r"^/dev/[a-zA-Z]+(\d+)$", partition)
    if m:
        return int(m.group(1))

    m = re.search(r"-part(\d+)$", partition)
    if m:
        return int(m.group(1))

    raise RuntimeError(
        f"Cannot extract partition number from '{partition}'. "
        f"Expected a device path like /dev/sda1 or /dev/nbd0p1."
    )


def partition_to_device(partition: str) -> str:
    """Resolve the parent block device from a partition path."""
    m = re.match(r"^(/dev/(?:nvme\d+n\d+|mmcblk\d+|nbd\d+|loop\d+))p\d+$", partition)
    if m:
        return m.group(1)

    m = re.match(r"^(/dev/[a-zA-Z]+)\d+$", partition)
    if m:
        return m.group(1)

    raise RuntimeError(
        f"Cannot determine parent block device from partition '{partition}'. "
        f"Expected a device path like /dev/sda1, /dev/nvme0n1p1, or /dev/nbd0p1."
    )
