# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Filesystem-specific command helpers for VMCraft."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._runner import RunCommandFn, run_captured

if TYPE_CHECKING:
    import logging


def _nonempty_stripped_lines(output: str) -> list[str]:
    """Return non-empty stripped lines from command output."""
    return [line.strip() for line in output.splitlines() if line.strip()]


def ntfs_3g_probe(logger: logging.Logger, run_sudo: RunCommandFn, device: str, *, rw: bool = False) -> int:
    """Probe NTFS mountability using ntfs-3g.probe."""
    try:
        cmd = ["ntfs-3g.probe"]
        if rw:
            cmd.append("--readwrite")
        cmd.append(device)

        result = run_captured(logger, run_sudo, cmd, check=False, debug_failure=True)
        return result.returncode
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, must not abort caller
        logger.debug("ntfs_3g_probe failed: %s", e)
        return 1


def btrfs_filesystem_show(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    *,
    device: str | None = None,
) -> list[dict[str, str]]:
    """Parse `btrfs filesystem show` output."""
    try:
        cmd = ["btrfs", "filesystem", "show"]
        if device:
            cmd.append(device)

        result = run_captured(logger, run_sudo, cmd, debug_failure=True)

        filesystems: list[dict[str, str]] = []
        current_fs: dict[str, str] | None = None

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()

            if line.startswith("Label:"):
                if current_fs:
                    filesystems.append(current_fs)
                current_fs = {}

                if "'" in line:
                    label_match = re.search(r"Label: '([^']*)'", line)
                    current_fs["label"] = label_match.group(1) if label_match else ""
                else:
                    current_fs["label"] = ""

                uuid_match = re.search(r"uuid: ([a-f0-9-]+)", line)
                current_fs["uuid"] = uuid_match.group(1) if uuid_match else ""
            elif "Total devices" in line and current_fs is not None:
                match = re.search(r"Total devices (\d+)", line)
                if match:
                    # current_fs is a dict here (guarded by "is not None" above); pylint's
                    # inference doesn't narrow the "dict[str, str] | None" union through
                    # the elif guard.
                    current_fs["total_devices"] = match.group(1)  # pylint: disable=unsupported-assignment-operation

        if current_fs:
            filesystems.append(current_fs)

        return filesystems
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, must not abort caller
        logger.debug("btrfs_filesystem_show failed: %s", e)
        return []


def btrfs_subvolume_list(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    *,
    mount_point: str,
) -> list[dict[str, str]]:
    """List Btrfs subvolumes for a mount point."""
    try:
        result = run_captured(
            logger,
            run_sudo,
            ["btrfs", "subvolume", "list", mount_point],
            debug_failure=True,
        )

        subvolumes: list[dict[str, str]] = []
        for raw_line in result.stdout.splitlines():
            match = re.match(r"ID (\d+).*path (.+)$", raw_line.strip())
            if match:
                subvolumes.append({"id": match.group(1), "path": match.group(2)})
        return subvolumes
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, must not abort caller
        logger.debug("btrfs_subvolume_list failed: %s", e)
        return []


def zfs_pool_list(logger: logging.Logger, run_sudo: RunCommandFn) -> list[str]:
    """List imported ZFS pool names."""
    try:
        result = run_captured(
            logger,
            run_sudo,
            ["zpool", "list", "-H", "-o", "name"],
            debug_failure=True,
        )
        return _nonempty_stripped_lines(result.stdout)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, must not abort caller
        logger.debug("zfs_pool_list failed: %s", e)
        return []


def zfs_dataset_list(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    *,
    pool: str | None = None,
) -> list[dict[str, str]]:
    """List ZFS datasets and parse tab-separated fields."""
    try:
        cmd = ["zfs", "list", "-H", "-o", "name,used,avail,refer,mountpoint"]
        if pool:
            cmd.append(pool)

        result = run_captured(logger, run_sudo, cmd, debug_failure=True)

        datasets: list[dict[str, str]] = []
        for line in _nonempty_stripped_lines(result.stdout):
            parts = line.split("\t")
            if len(parts) >= 5:
                datasets.append(
                    {
                        "name": parts[0],
                        "used": parts[1],
                        "avail": parts[2],
                        "refer": parts[3],
                        "mountpoint": parts[4],
                    }
                )
        return datasets
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, must not abort caller
        logger.debug("zfs_dataset_list failed: %s", e)
        return []
