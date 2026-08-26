# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/logging_utils.py
"""
Shared logging utilities for h2kvm.

Provides common logging helpers to avoid duplication across modules.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator


def safe_logger(instance: Any, default_name: str = "h2kvm") -> logging.Logger:
    """
    Get logger from instance or return default logger.

    Checks if instance has a 'logger' attribute that is a logging.Logger.
    If so, returns it. Otherwise, returns a logger with the specified name.

    Args:
        instance: Object that may have a 'logger' attribute
        default_name: Name for default logger if instance has no logger

    Returns:
        logging.Logger instance
    """
    lg = getattr(instance, "logger", None)
    if isinstance(lg, logging.Logger):
        return lg
    return logging.getLogger(default_name)


def emoji_for_level(level: int) -> str:
    """
    Return emoji symbol for log level.

    Args:
        level: logging level (ERROR, WARNING, INFO, DEBUG)

    Returns:
        Emoji string for the level
    """
    if level >= logging.ERROR:
        return "❌"
    if level >= logging.WARNING:
        return "⚠️"
    if level >= logging.INFO:
        return "✅"
    return "🔍"


def log_with_emoji(logger: logging.Logger, level: int, msg: str, *args: Any) -> None:
    """
    Log a message with an emoji prefix based on log level.

    Args:
        logger: Logger instance to use
        level: logging level (ERROR, WARNING, INFO, DEBUG)
        msg: Message format string
        *args: Arguments for message formatting
    """
    logger.log(level, f"{emoji_for_level(level)} {msg}", *args)


@contextmanager
def log_step(logger: logging.Logger, description: str) -> Generator[None, None, None]:
    """
    Context manager for logging and timing operation steps.

    Logs the start of an operation, executes the block, then logs
    completion with elapsed time. Logs error and re-raises on exception.

    Args:
        logger: Logger instance to use
        description: Description of the operation

    Yields:
        None

    Example:
        with log_step(logger, "Processing data"):
            process_data()
    """
    t0 = time.time()
    log_with_emoji(logger, logging.INFO, "%s ...", description)
    try:
        yield
        log_with_emoji(logger, logging.INFO, "%s done (%.2fs)", description, time.time() - t0)
    except Exception as e:
        log_with_emoji(logger, logging.ERROR, "%s failed (%.2fs): %s", description, time.time() - t0, e)
        raise
