# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Extended filesystem attribute helpers for VMCraft."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import logging


def _parse_lsattr_flags(output: str) -> str:
    """Extract the leading attributes field from `lsattr -d` output."""
    text = output.strip()
    if not text:
        return ""
    parts = text.split(None, 1)
    return parts[0] if parts else ""


def _chattr_cmd(file: str, attrs: str, *, clear: bool) -> list[str]:
    """Build `chattr` command for setting or clearing attributes."""
    return ["chattr", f"-{attrs}" if clear else f"+{attrs}", file]


def get_e2attrs(
    logger: logging.Logger,
    file: str,
    command_quiet_fn: Callable[[list[str]], str],
) -> str:
    """Get ext attribute flags for a path via `lsattr -d`."""
    try:
        return _parse_lsattr_flags(command_quiet_fn(["lsattr", "-d", file]))
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort attr lookup, must not abort caller
        logger.debug("get_e2attrs failed for %s: %s", file, e)

    return ""


def set_e2attrs(
    file: str,
    attrs: str,
    *,
    clear: bool,
    command_fn: Callable[[list[str]], None],
) -> None:
    """Set or clear ext attribute flags using `chattr`."""
    cmd = _chattr_cmd(file, attrs, clear=clear)
    try:
        command_fn(cmd)
    except Exception as e:
        raise RuntimeError(
            f"Failed to set file attributes on '{file}'. "
            f"The filesystem may not support extended attributes. Detail: {e}"
        ) from e
