# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/retry_decorator.py
"""
High-level retry decorator for cloud provider API calls.

Wraps operations with exponential backoff + jitter, designed for transient
failures common in vSphere, Azure, and other remote APIs.

Complements :mod:`h2kvm.core.retry` (low-level retry_with_backoff) by
providing a simpler, opinionated interface targeted at provider methods.

Usage:
    from h2kvm.core.retry_decorator import api_retry

    class MyProvider:
        @api_retry(max_retries=5)
        def list_vms(self):
            ...

        @api_retry(retryable_exceptions=(ConnectionError, TimeoutError))
        def download_disk(self, url, dest):
            ...
"""

from __future__ import annotations

import logging
import random
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")

logger = logging.getLogger(__name__)

# Default exceptions considered safe to retry across cloud providers
_DEFAULT_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def api_retry(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    backoff_cap: float = 60.0,
    retryable_exceptions: type[Exception] | tuple[type[Exception], ...] = _DEFAULT_RETRYABLE,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for cloud/provider API calls with exponential backoff and jitter.

    Retries the decorated function on transient errors, logging each attempt.

    Args:
        max_retries: Maximum number of retry attempts after the initial call.
            Total attempts = 1 + max_retries. Default: 3.
        backoff_base: Base multiplier for exponential backoff (seconds). Default: 2.0.
        backoff_cap: Maximum backoff duration (seconds). Default: 60.0.
        retryable_exceptions: Exception type(s) that trigger a retry.
            Default: (ConnectionError, TimeoutError, OSError).

    Returns:
        Decorated function with retry logic.

    Example:
        @api_retry(max_retries=5, backoff_base=1.5)
        def connect_to_vsphere(host, user, password):
            ...

        @api_retry(retryable_exceptions=(ConnectionError, TimeoutError, requests.HTTPError))
        def download_vhd(url, dest):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            total_attempts = 1 + max_retries

            for attempt in range(1, total_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc

                    if attempt >= total_attempts:
                        logger.exception(
                            "%s failed after %d attempt(s): %s",
                            func.__qualname__,
                            total_attempts,
                            exc,
                        )
                        raise

                    # Exponential backoff with full jitter
                    sleep_time = min(backoff_base * (2 ** (attempt - 1)), backoff_cap)
                    sleep_time = random.uniform(0, sleep_time)

                    logger.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.2fs",
                        func.__qualname__,
                        attempt,
                        total_attempts,
                        exc,
                        sleep_time,
                    )
                    time.sleep(sleep_time)

            # Unreachable, but satisfies the type checker
            if last_exc is not None:
                raise last_exc
            raise RuntimeError(
                f"Operation '{func.__qualname__}' failed after all retry attempts "
                f"but no specific error was captured. This is an internal error."
            )

        return wrapper

    return decorator
