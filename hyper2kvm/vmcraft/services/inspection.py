# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Inspection helpers for VMCraft."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, Callable

from ._runner import RunCommandFn, run_captured

if TYPE_CHECKING:
    import logging
    from pathlib import Path


def _best_effort_umount(logger: logging.Logger, run_sudo: RunCommandFn, mount_root: Path) -> None:
    """Attempt unmount and suppress any cleanup errors."""
    with contextlib.suppress(Exception):
        run_captured(logger, run_sudo, ["umount", str(mount_root)], check=False)


def _safe_base_device(device: str, part_to_dev_fn: Callable[[str], str]) -> str | None:
    """Return a normalized base device or None if normalization fails."""
    try:
        return part_to_dev_fn(device) if "/" in device else device
    except Exception:  # pylint: disable=broad-exception-caught  # normalization is best-effort, caller treats None as "unknown"
        return None


def _group_filesystems_by_base_device(
    filesystems: dict[str, str],
    part_to_dev_fn: Callable[[str], str],
) -> dict[str, list[str]]:
    """Group filesystem device paths by normalized base device."""
    grouped: dict[str, list[str]] = {}
    for fs_dev in filesystems:
        base = _safe_base_device(fs_dev, part_to_dev_fn)
        if base:
            grouped.setdefault(base, []).append(fs_dev)
    return grouped


def inspect_os(os_inspector: Any, partitions: list[str]) -> list[str]:
    """Detect operating systems on partitions."""
    return os_inspector.inspect_partitions(partitions)


def get_cached_inspection_value(os_inspector: Any | None, root: str, key: str, default: Any) -> Any:
    """Fetch cached inspection value for root if available."""
    if os_inspector and os_inspector.has_cached_info(root):
        return os_inspector.get_cached_info(root).get(key, default)
    return default


def parse_fstab(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals  # orchestrates mount-check/mount/parse/unmount flow
    logger: logging.Logger,
    mount_root: Path | None,
    file_ops: Any | None,
    root: str,
    run_sudo: RunCommandFn,
    umount_all_fn: Callable[[], None],
) -> list[tuple[str, str]]:
    """Parse /etc/fstab from a root device."""
    if not mount_root or not file_ops:
        return []

    mounts: list[tuple[str, str]] = []

    try:
        # Check if already mounted before attempting umount + mount
        already_mounted = False
        mp_result = run_captured(
            logger,
            run_sudo,
            ["mountpoint", "-q", str(mount_root)],
            check=False,
        )
        if mp_result.returncode == 0:
            already_mounted = True
            logger.debug("Device %s already mounted at %s, skipping mount", root, mount_root)

        if not already_mounted:
            umount_all_fn()
            try:
                run_captured(
                    logger,
                    run_sudo,
                    ["mount", "-o", "ro", root, str(mount_root)],
                    check=True,
                )
            except Exception as mount_err:  # pylint: disable=broad-exception-caught  # mount() can raise various error types; message must be inspected
                # Check error message and context for "already mounted"
                err_str = str(mount_err).lower()
                ctx = getattr(mount_err, "context", None) or {}
                ctx_stderr = str(ctx.get("stderr", "")).lower()
                ctx_stdout = str(ctx.get("stdout", "")).lower()
                if (
                    "already mounted" in err_str
                    or "already mounted" in ctx_stderr
                    or "already mounted" in ctx_stdout
                ):
                    logger.debug("Device %s already mounted at %s, continuing", root, mount_root)
                else:
                    raise

        fstab_path = mount_root / "etc/fstab"
        if not fstab_path.exists():
            return mounts

        # pylint: disable=duplicate-code
        # reason: mirrors similar "read + split whitespace-separated
        # fields" parsing loops in vmcraft/ssh_analyzer.py
        # (authorized_keys parsing) -- structurally similar by coincidence,
        # not shared logic; keeping independent avoids coupling unrelated
        # config-parsing code paths.
        for line in fstab_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                mounts.append((parts[0], parts[1]))

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort inspection, must not abort caller
        logger.warning("Failed to parse fstab: %s", e)
    finally:
        _best_effort_umount(logger, run_sudo, mount_root)

    return mounts


def inspect_get_mountpoints(
    root: str,
    os_type: str,
    return_dict: bool,
    parse_fstab_fn: Callable[[str], list[tuple[str, str]]],
) -> dict[str, str] | list[tuple[str, str]]:
    """Build mountpoint mapping for a given root."""
    if os_type == "windows":
        if return_dict:
            return {"/": root}
        return [(root, "/")]

    mounts = parse_fstab_fn(root)
    if return_dict:
        return {mp: dev for dev, mp in mounts}
    return list(mounts)


def extract_filesystems_from_lsblk(dev: dict[str, Any], result: dict[str, str]) -> None:
    """Recursively extract filesystems from lsblk JSON output."""
    name = dev.get("name")
    fstype = dev.get("fstype")

    if name and fstype:
        result[f"/dev/{name}"] = fstype

    for child in dev.get("children", []):
        extract_filesystems_from_lsblk(child, result)


def list_filesystems(logger: logging.Logger, run_sudo: RunCommandFn) -> dict[str, str]:
    """List all filesystems from lsblk output."""
    result: dict[str, str] = {}

    try:
        cmd = ["lsblk", "-f", "--json", "-o", "NAME,FSTYPE"]
        output = run_captured(logger, run_sudo, cmd, check=True)
        data = json.loads(output.stdout)
        for dev in data.get("blockdevices", []):
            extract_filesystems_from_lsblk(dev, result)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort inspection, must not abort caller
        logger.warning("Failed to list filesystems: %s", e)

    return result


def inspect_filesystems_grouped(
    *,
    os_inspector: Any | None,
    list_filesystems_fn: Callable[[], dict[str, str]],
    inspect_os_fn: Callable[[], list[str]],
    part_to_dev_fn: Callable[[str], str],
) -> dict[str, list[str]]:
    """Group filesystems by detected root device or by disk fallback."""
    result: dict[str, list[str]] = {}
    all_fs = list_filesystems_fn()
    grouped_by_base = _group_filesystems_by_base_device(all_fs, part_to_dev_fn)

    if os_inspector:
        try:
            roots = inspect_os_fn()
            for root_dev in roots:
                root_base = _safe_base_device(root_dev, part_to_dev_fn) or root_dev
                result[root_dev] = grouped_by_base.get(root_base, [])
        except Exception:  # pylint: disable=broad-exception-caught  # falls through to disk-based grouping below
            pass

    if not result:
        for devices in grouped_by_base.values():
            if devices:
                result[devices[0]] = devices

    return result


def inspect_get_filesystems_for_root(
    root: str,
    inspect_filesystems_fn: Callable[[], dict[str, list[str]]],
) -> list[str]:
    """Return grouped filesystems for one root device."""
    return inspect_filesystems_fn().get(root, [])
