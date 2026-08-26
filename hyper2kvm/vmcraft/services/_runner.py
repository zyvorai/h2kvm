# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared command-runner helpers for vmcraft service modules."""

from __future__ import annotations

import logging
from typing import Any, Callable

RunCommandFn = Callable[..., Any]


# Thin pass-through wrapper over an injected runner; each kwarg maps 1:1 to a
# distinct run_cmd() option, so consolidating them would just hide the same knobs.
# pylint: disable-next=too-many-arguments
def run_command(
    logger: logging.Logger,
    run_cmd: RunCommandFn,
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    failure_log_level: int | None = None,
) -> Any:
    """Execute command via injected runner with common kwargs handling."""
    kwargs: dict[str, Any] = {"check": check, "capture": capture}
    if failure_log_level is not None:
        kwargs["failure_log_level"] = failure_log_level
    return run_cmd(logger, cmd, **kwargs)


def run_captured(
    logger: logging.Logger,
    run_cmd: RunCommandFn,
    cmd: list[str],
    *,
    check: bool = True,
    debug_failure: bool = False,
) -> Any:
    """Execute a captured command with optional debug-level failure logging."""
    return run_command(
        logger,
        run_cmd,
        cmd,
        check=check,
        capture=True,
        failure_log_level=logging.DEBUG if debug_failure else None,
    )


def probe_stdout(
    logger: logging.Logger,
    run_cmd: RunCommandFn,
    cmd: list[str],
    *,
    check: bool = True,
    debug_failure: bool = False,
) -> str:
    """Return stripped stdout for a command, or empty string on any failure."""
    try:
        result = run_captured(
            logger,
            run_cmd,
            cmd,
            check=check,
            debug_failure=debug_failure,
        )
        return result.stdout.strip()
    except Exception:  # pylint: disable=broad-exception-caught
        # This is a "best-effort probe" helper by design: any failure (missing binary,
        # non-zero exit, timeout) degrades to an empty result rather than raising.
        return ""
