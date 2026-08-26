# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Chroot execution helpers for VMCraft."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._runner import RunCommandFn, run_captured

if TYPE_CHECKING:
    import logging


def _ensure_bind_mount(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    source: str,
    target: Path,
) -> bool:
    """Ensure source is bind-mounted to target. Returns True if mounted by this call."""
    check_result = run_captured(logger, run_sudo, ["mountpoint", "-q", str(target)], check=False)
    if check_result.returncode == 0:
        return False
    run_captured(logger, run_sudo, ["mount", "--bind", source, str(target)])
    logger.debug("Bind-mounted %s to %s", source, target)
    return True


def _cleanup_mounts(logger: logging.Logger, run_sudo: RunCommandFn, mounts_to_cleanup: list[str]) -> None:
    """Best-effort unmount of bind mounts in reverse order."""
    for mount_path in reversed(mounts_to_cleanup):
        try:
            run_captured(
                logger,
                run_sudo,
                ["umount", mount_path],
                check=False,
                debug_failure=True,
            )
            logger.debug("Unmounted %s", mount_path)
        # defensive cleanup path; must not abort cleanup of the remaining mounts
        except Exception as e:  # pragma: no cover  # pylint: disable=broad-exception-caught
            logger.debug("Failed to unmount %s: %s", mount_path, e)


def execute_chroot_command(
    logger: logging.Logger,
    mount_root: str,
    cmd: list[str],
    run_sudo: RunCommandFn,
    *,
    quiet: bool = False,
) -> str:
    """Execute a command in the guest chroot and return stdout."""
    chroot_cmd = ["chroot", str(mount_root), *cmd]
    result = run_captured(logger, run_sudo, chroot_cmd, check=True, debug_failure=quiet)
    return result.stdout


def execute_chroot_command_with_mounts(
    logger: logging.Logger,
    mount_root: str,
    cmd: list[str],
    run_sudo: RunCommandFn,
    *,
    quiet: bool = False,
) -> str:
    """Execute a chroot command with /proc,/dev,/sys,/run bind-mounted."""
    root_path = Path(mount_root)
    mounts_to_cleanup: list[str] = []

    try:
        for mount_point in ["proc", "dev", "sys", "run"]:
            target = root_path / mount_point
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)

            if _ensure_bind_mount(logger, run_sudo, f"/{mount_point}", target):
                mounts_to_cleanup.append(str(target))

        return execute_chroot_command(
            logger,
            mount_root,
            cmd,
            run_sudo,
            quiet=quiet,
        )

    finally:
        _cleanup_mounts(logger, run_sudo, mounts_to_cleanup)
