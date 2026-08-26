# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/retry.py
"""
Retry utilities with exponential backoff.

Provides decorators and utilities for retrying operations with configurable
backoff strategies.
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


def retry_with_backoff(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # each param is an independent backoff-policy knob
    max_attempts: int = 3,
    base_backoff_s: float = 2.0,
    max_backoff_s: float = 60.0,
    jitter_s: float = 1.0,
    exceptions: type[Exception] | tuple[type[Exception], ...] = Exception,
    logger: logging.Logger | None = None,
    log_level: int = logging.WARNING,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        base_backoff_s: Base backoff time in seconds (default: 2.0)
        max_backoff_s: Maximum backoff time in seconds (default: 60.0)
        jitter_s: Random jitter to add to backoff in seconds (default: 1.0)
        exceptions: Exception type(s) to catch and retry (default: Exception)
        logger: Logger to use for warnings (default: None, no logging)
        log_level: Log level for retry messages (default: logging.WARNING)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(max_attempts=5, base_backoff_s=1.0)
        def flaky_operation():
            # ... operation that might fail ...
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:  # pylint: disable=broad-exception-caught  # caller-configurable, defaults to Exception to retry unknown failures
                    last_exception = e

                    if attempt < max_attempts:
                        # Calculate backoff with exponential increase and jitter
                        sleep_time = min(base_backoff_s * (2 ** (attempt - 1)), max_backoff_s)
                        if jitter_s > 0:
                            sleep_time += random.uniform(0, jitter_s)

                        if logger:
                            logger.log(
                                log_level,
                                "%s failed (attempt %d/%d): %s. Retrying in %.2fs...",
                                func.__name__,
                                attempt,
                                max_attempts,
                                e,
                                sleep_time,
                            )

                        time.sleep(sleep_time)
                    # Final attempt failed
                    elif logger:
                        logger.log(
                            logging.ERROR,
                            "%s failed after %d attempts: %s",
                            func.__name__,
                            max_attempts,
                            e,
                        )

            # Re-raise the last exception
            if last_exception:
                raise last_exception

            # Should never reach here, but satisfy type checker
            raise RuntimeError(
                f"Operation '{func.__name__}' failed after all retry attempts "
                f"but no specific error was captured. This is an internal error."
            )

        return wrapper

    return decorator


def retry_operation(  # pylint: disable=too-many-arguments  # each param is an independent backoff-policy knob
    operation: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_backoff_s: float = 2.0,
    max_backoff_s: float = 60.0,
    jitter_s: float = 1.0,
    exceptions: type[Exception] | tuple[type[Exception], ...] = Exception,
    operation_name: str = "operation",
    logger: logging.Logger | None = None,
    log_level: int = logging.WARNING,
) -> T:
    """
    Retry an operation (function call) with exponential backoff.

    This is a non-decorator version for one-off retry operations.

    Args:
        operation: Callable that returns T
        max_attempts: Maximum number of attempts (default: 3)
        base_backoff_s: Base backoff time in seconds (default: 2.0)
        max_backoff_s: Maximum backoff time in seconds (default: 60.0)
        jitter_s: Random jitter to add to backoff in seconds (default: 1.0)
        exceptions: Exception type(s) to catch and retry (default: Exception)
        operation_name: Name for logging (default: "operation")
        logger: Logger to use for warnings (default: None, no logging)
        log_level: Log level for retry messages (default: logging.WARNING)

    Returns:
        Result of the operation

    Example:
        result = retry_operation(
            lambda: download_file(url),
            max_attempts=5,
            operation_name="download",
            logger=my_logger,
        )
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except exceptions as e:  # pylint: disable=broad-exception-caught  # caller-configurable, defaults to Exception to retry unknown failures
            last_exception = e

            if attempt < max_attempts:
                # Calculate backoff with exponential increase and jitter
                sleep_time = min(base_backoff_s * (2 ** (attempt - 1)), max_backoff_s)
                if jitter_s > 0:
                    sleep_time += random.uniform(0, jitter_s)

                if logger:
                    logger.log(
                        log_level,
                        "%s failed (attempt %d/%d): %s. Retrying in %.2fs...",
                        operation_name,
                        attempt,
                        max_attempts,
                        e,
                        sleep_time,
                    )

                time.sleep(sleep_time)
            # Final attempt failed
            elif logger:
                logger.log(
                    logging.ERROR,
                    "%s failed after %d attempts: %s",
                    operation_name,
                    max_attempts,
                    e,
                )

    # Re-raise the last exception
    if last_exception:
        raise last_exception

    # Should never reach here
    raise RuntimeError(
        f"Operation '{operation_name}' failed after all retry attempts "
        f"but no specific error was captured. This is an internal error."
    )
