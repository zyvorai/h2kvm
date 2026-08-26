# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Archive and block-copy command helpers for VMCraft."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._runner import RunCommandFn, run_captured

if TYPE_CHECKING:
    import logging
    from pathlib import Path


def _compression_flag(compress: str | None) -> str | None:
    """Map compression name to tar CLI flag."""
    return {
        "gzip": "-z",
        "bzip2": "-j",
        "xz": "-J",
    }.get(compress)


def _run_archive_cmd(logger: logging.Logger, run_sudo: RunCommandFn, cmd: list[str], error_msg: str) -> None:
    """Run archive/block copy command and normalize failures."""
    try:
        run_captured(logger, run_sudo, cmd)
    except Exception as e:
        raise RuntimeError(
            f"{error_msg}. Check disk space, file permissions, and that the archive is not corrupted. "
            f"Detail: {e}"
        ) from e


def _tar_cmd(
    mode_flag: str,
    *,
    tarfile: str,
    target_dir: str,
    target_name: str | None = None,
    compress: str | None = None,
) -> list[str]:
    """Build tar command for extract/create operations."""
    cmd = ["tar", mode_flag, tarfile, "-C", target_dir]
    if target_name is not None:
        cmd.append(target_name)
    flag = _compression_flag(compress)
    if flag:
        cmd.insert(1, flag)
    return cmd


# Each kwarg is an independent archive parameter (source root, file, guest path,
# compression); keyword-only args already make call sites self-documenting.
# pylint: disable-next=too-many-arguments
def tar_in(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    *,
    mount_root: Path,
    tarfile: str,
    directory: str,
    compress: str | None = None,
) -> None:
    """Extract tar archive into guest directory rooted at `mount_root`."""
    guest_dir = mount_root / directory.lstrip("/")
    guest_dir.mkdir(parents=True, exist_ok=True)

    cmd = _tar_cmd("-xf", tarfile=tarfile, target_dir=str(guest_dir), compress=compress)

    _run_archive_cmd(logger, run_sudo, cmd, "Failed to extract tar archive")
    logger.info("Extracted %s to %s", tarfile, directory)


# Each kwarg is an independent archive parameter (source root, file, guest path,
# compression); keyword-only args already make call sites self-documenting.
# pylint: disable-next=too-many-arguments
def tar_out(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    *,
    mount_root: Path,
    directory: str,
    tarfile: str,
    compress: str | None = None,
) -> None:
    """Create tar archive from guest directory rooted at `mount_root`."""
    guest_dir = mount_root / directory.lstrip("/")
    if not guest_dir.exists():
        raise RuntimeError(
            f"Directory '{directory}' does not exist in the guest filesystem. "
            f"Verify the path is correct and the guest disk is properly mounted."
        )

    cmd = _tar_cmd(
        "-cf",
        tarfile=tarfile,
        target_dir=str(guest_dir.parent),
        target_name=guest_dir.name,
        compress=compress,
    )

    _run_archive_cmd(logger, run_sudo, cmd, "Failed to create tar archive")
    logger.info("Created %s from %s", tarfile, directory)


# Each kwarg is an independent dd parameter (src, dest, count, blocksize);
# keyword-only args already make call sites self-documenting.
# pylint: disable-next=too-many-arguments
def dd_copy(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    *,
    src: str,
    dest: str,
    count: int | None = None,
    blocksize: int = 512,
) -> None:
    """Copy data with `dd` command."""
    cmd = ["dd", f"if={src}", f"of={dest}", f"bs={blocksize}"]
    if count:
        cmd.append(f"count={count}")
    _run_archive_cmd(logger, run_sudo, cmd, "dd copy failed")
    logger.info("Copied %s to %s (bs=%s, count=%s)", src, dest, blocksize, count or "all")
