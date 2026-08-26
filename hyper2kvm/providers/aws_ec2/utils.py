# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""AWS EC2 provider utilities."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry(  # pylint: disable=too-many-arguments  # generic retry helper: each knob configures one policy aspect
    fn: Callable[[], T],
    *,
    retries: int = 5,
    backoff_base: float = 1.0,
    backoff_cap: float = 30.0,
    retryable: Callable[[Exception], bool] | None = None,
    label: str = "operation",
    log: logging.Logger | None = None,
) -> T:
    """
    Retry a callable with exponential backoff.

    Args:
        fn: Zero-arg callable to retry
        retries: Maximum number of attempts
        backoff_base: Base delay in seconds (doubles each retry)
        backoff_cap: Maximum delay between retries
        retryable: Predicate to check if exception is retryable (default: all)
        label: Human-readable label for log messages
        log: Logger instance

    Returns:
        Result of fn()

    Raises:
        The last exception if all retries exhausted
    """
    _log = log or logger
    last_err: Exception | None = None

    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:  # pylint: disable=broad-exception-caught  # generic retry wrapper; retryable() filters
            last_err = e
            if retryable and not retryable(e):
                raise
            if attempt == retries - 1:
                raise
            delay = min(backoff_base * (2**attempt), backoff_cap)
            _log.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                label,
                attempt + 1,
                retries,
                e,
                delay,
            )
            time.sleep(delay)

    raise last_err  # unreachable, but keeps type checker happy


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Save pipeline state to JSON for resumability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.rename(path)


def load_state(path: Path) -> dict[str, Any] | None:
    """Load pipeline state from JSON. Returns None if not found."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def instance_name_from_tags(tags: list[dict[str, str]] | None) -> str:
    """Extract Name tag from EC2 instance tags."""
    if not tags:
        return ""
    for tag in tags:
        if tag.get("Key") == "Name":
            return tag.get("Value", "")
    return ""
