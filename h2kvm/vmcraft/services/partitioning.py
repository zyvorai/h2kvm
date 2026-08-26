# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Partition management helpers for VMCraft."""

from __future__ import annotations

import logging
from typing import Any, Callable

from ._runner import RunCommandFn, run_captured

InvalidateFn = Callable[[str], None]
RereadFn = Callable[[str], None]


def _normalize_parttype(parttype: str, *, allow_alias: bool = True) -> str:
    if allow_alias and parttype == "mbr":
        parttype = "msdos"
    return parttype


def _run_partition_command(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    cmd: list[str],
    *,
    failure_log_level: int | None = None,
) -> Any:
    """Run a partition-related command with standard capture/check flags."""
    return run_captured(
        logger,
        run_sudo,
        cmd,
        check=True,
        debug_failure=failure_log_level == logging.DEBUG,
    )


def _wrap_partition_error(action: Callable[[], None], error_message: str) -> None:
    """Run partition action and normalize raised RuntimeError text."""
    try:
        action()
    except Exception as e:
        raise RuntimeError(
            f"{error_message}. Check that the device is not in use and you have sufficient permissions. "
            f"Detail: {e}"
        ) from e


def _refresh_partition_state(
    device: str,
    invalidate_partition_cache: InvalidateFn,
    blockdev_rereadpt: RereadFn,
) -> None:
    """Invalidate partition cache and force partition table re-read."""
    invalidate_partition_cache(device)
    blockdev_rereadpt(device)


def part_init(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # uniform DiskOps call signature
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    parttype: str,
    invalidate_partition_cache: InvalidateFn,
    blockdev_rereadpt: RereadFn,
) -> None:
    """Initialize a disk partition table."""
    parttype = _normalize_parttype(parttype, allow_alias=True)
    if parttype not in ("gpt", "msdos"):
        raise ValueError(f"Invalid partition type: {parttype}. Must be 'gpt' or 'msdos'/'mbr'")

    def _action() -> None:
        _run_partition_command(logger, run_sudo, ["parted", "-s", device, "mklabel", parttype])
        _refresh_partition_state(device, invalidate_partition_cache, blockdev_rereadpt)
        logger.info("Initialized %s partition table on %s", parttype, device)

    _wrap_partition_error(_action, f"Failed to initialize partition table on {device}")


def part_add(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # uniform DiskOps call signature
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    prlogex: str,
    startsect: int,
    endsect: int,
    invalidate_partition_cache: InvalidateFn,
    blockdev_rereadpt: RereadFn,
) -> None:
    """Add a partition to a disk."""
    if prlogex not in ("primary", "logical", "extended"):
        raise ValueError(f"Invalid partition type '{prlogex}'. Must be 'primary', 'logical', or 'extended'.")

    start_spec = f"{startsect}s"
    end_spec = "100%" if endsect == -1 else f"{endsect}s"

    def _action() -> None:
        _run_partition_command(
            logger,
            run_sudo,
            ["parted", "-s", device, "mkpart", prlogex, start_spec, end_spec],
        )
        _refresh_partition_state(device, invalidate_partition_cache, blockdev_rereadpt)
        logger.info("Added %s partition to %s: %s-%s", prlogex, device, start_spec, end_spec)

    _wrap_partition_error(_action, f"Failed to add partition to {device}")


def part_del(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # uniform DiskOps call signature
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    partnum: int,
    invalidate_partition_cache: InvalidateFn,
    blockdev_rereadpt: RereadFn,
) -> None:
    """Delete a partition from a disk."""
    if partnum < 1:
        raise ValueError(f"Invalid partition number: {partnum}. Must be >= 1")

    def _action() -> None:
        _run_partition_command(logger, run_sudo, ["parted", "-s", device, "rm", str(partnum)])
        _refresh_partition_state(device, invalidate_partition_cache, blockdev_rereadpt)
        logger.info("Deleted partition %s from %s", partnum, device)

    _wrap_partition_error(_action, f"Failed to delete partition {partnum} from {device}")


def part_disk(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # uniform DiskOps call signature
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    parttype: str,
    invalidate_partition_cache: InvalidateFn,
    blockdev_rereadpt: RereadFn,
) -> None:
    """Create a partition table and a single partition spanning the disk."""
    parttype = _normalize_parttype(parttype, allow_alias=True)
    if parttype not in ("gpt", "msdos"):
        raise ValueError(f"Invalid partition table type '{parttype}'. Must be 'gpt' or 'msdos' (MBR).")

    def _action() -> None:
        _run_partition_command(logger, run_sudo, ["parted", "-s", device, "mklabel", parttype])
        _run_partition_command(
            logger, run_sudo, ["parted", "-s", device, "mkpart", "primary", "1MiB", "100%"]
        )
        _refresh_partition_state(device, invalidate_partition_cache, blockdev_rereadpt)
        logger.info("Initialized %s partition table on %s with single partition", parttype, device)

    _wrap_partition_error(_action, f"Failed to initialize partition table on {device}")


def part_set_name(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    partnum: int,
    name: str,
) -> None:
    """Set GPT partition name."""
    if partnum < 1:
        raise ValueError(f"Invalid partition number {partnum}. Must be >= 1.")

    def _action() -> None:
        _run_partition_command(logger, run_sudo, ["parted", "-s", device, "name", str(partnum), name])
        logger.info("Set partition %s name to '%s' on %s", partnum, name, device)

    _wrap_partition_error(_action, "Failed to set partition name")


def part_set_gpt_type(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    partnum: int,
    guid: str,
) -> None:
    """Set GPT partition type GUID."""
    if partnum < 1:
        raise ValueError(f"Invalid partition number {partnum}. Must be >= 1.")

    def _action() -> None:
        _run_partition_command(logger, run_sudo, ["sgdisk", f"--typecode={partnum}:{guid}", device])
        logger.info("Set partition %s type to %s on %s", partnum, guid, device)

    _wrap_partition_error(_action, "Failed to set partition type")


def part_get_parttype(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> str:
    """Get partition table type from `parted print` output."""
    try:
        result = _run_partition_command(
            logger,
            run_sudo,
            ["parted", "-s", device, "print"],
            failure_log_level=logging.DEBUG,
        )
        output = result.stdout.lower()
        if "partition table: gpt" in output:
            return "gpt"
        if "partition table: msdos" in output or "partition table: mbr" in output:
            return "msdos"
        return "unknown"
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, "unknown" is a valid result
        logger.debug("Failed to get partition type for %s: %s", device, e)
        return "unknown"
