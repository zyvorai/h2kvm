# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Block device helper functions for VMCraft."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._runner import RunCommandFn, probe_stdout, run_captured

if TYPE_CHECKING:
    import logging


def _blockdev_cmd(option: str, device: str) -> list[str]:
    """Build a blockdev command for a device."""
    return ["blockdev", option, device]


def _run_int_cmd(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    cmd: list[str],
    *,
    default: int,
    debug_message: str | None = None,
) -> int:
    """Run command and parse integer stdout, returning default on failure."""
    try:
        return int(probe_stdout(logger, run_sudo, cmd, debug_failure=True))
    # best-effort probe; caller-supplied default is the intended fallback on any failure
    except Exception as e:  # pylint: disable=broad-exception-caught
        if debug_message:
            logger.debug(debug_message, cmd[-1], e)
        return default


def _run_mutating_cmd(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    cmd: list[str],
    error_message: str,
) -> None:
    """Run mutating blockdev command and wrap failures uniformly."""
    try:
        run_captured(logger, run_sudo, cmd)
    except Exception as e:
        raise RuntimeError(error_message.format(error=e)) from e


def _run_bool_cmd(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    cmd: list[str],
    *,
    true_value: str = "1",
) -> bool:
    """Run command and compare stdout to expected true value."""
    return probe_stdout(logger, run_sudo, cmd) == true_value


def _run_with_fallback(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    primary_cmd: list[str],
    fallback_cmd: list[str],
    error_message: str,
) -> None:
    """Run primary command then fallback command if primary fails."""
    try:
        run_captured(logger, run_sudo, primary_cmd)
    # primary command failed; fall through to the fallback command below
    except Exception:  # pylint: disable=broad-exception-caught
        try:
            run_captured(logger, run_sudo, fallback_cmd)
        except Exception as e2:
            raise RuntimeError(
                f"{error_message}. The device may be in use or inaccessible. Detail: {e2}"
            ) from e2


def getsize64(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> int:
    """Get block device size in bytes."""
    return _run_int_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--getsize64", device),
        default=0,
        debug_message="blockdev_getsize64 failed for %s: %s",
    )


def getsz(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> int:
    """Get block device size in 512-byte sectors."""
    return _run_int_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--getsz", device),
        default=0,
        debug_message="blockdev_getsz failed for %s: %s",
    )


def getss(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> int:
    """Get logical sector size in bytes."""
    try:
        device_name = Path(device).name
        sys_path = Path(f"/sys/block/{device_name}/queue/logical_block_size")
        if sys_path.exists():
            return int(sys_path.read_text(encoding="utf-8").strip())
    # best-effort sysfs read; falls through to the blockdev command below
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return _run_int_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--getss", device),
        default=512,
    )


def getbsz(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> int:
    """Get block size in bytes."""
    return _run_int_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--getbsz", device),
        default=4096,
    )


def getro(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> bool:
    """Check whether block device is read-only."""
    return _run_bool_cmd(logger, run_sudo, _blockdev_cmd("--getro", device), true_value="1")


def setrw(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> None:
    """Set block device to read-write mode."""
    _run_mutating_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--setrw", device),
        f"Failed to set {device} to read-write: {{error}}",
    )


def setro(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> None:
    """Set block device to read-only mode."""
    _run_mutating_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--setro", device),
        f"Failed to set {device} to read-only: {{error}}",
    )


def flushbufs(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> None:
    """Flush block device buffers."""
    _run_mutating_cmd(
        logger,
        run_sudo,
        _blockdev_cmd("--flushbufs", device),
        f"Failed to flush buffers for {device}: {{error}}",
    )


def rereadpt(logger: logging.Logger, run_sudo: RunCommandFn, device: str) -> None:
    """Re-read partition table, with partprobe fallback."""
    _run_with_fallback(
        logger,
        run_sudo,
        _blockdev_cmd("--rereadpt", device),
        ["partprobe", device],
        f"Failed to re-read partition table for {device}",
    )
