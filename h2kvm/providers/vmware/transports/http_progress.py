# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/transports/http_progress.py
"""
Progress reporter implementations for HTTP downloads.

Provides multiple progress reporting strategies using the Strategy pattern:
- SimpleProgressReporter: Basic percentage display (requires TTY)
- LoggingProgressReporter: Log-based progress (works everywhere)
- NoopProgressReporter: Silent (no output)
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from h2kvm.providers.vmware.utils.utils import is_tty as _is_tty

# Import from sibling module
from ....core.utils import U

if TYPE_CHECKING:
    import logging


# Progress Reporter Interface (Strategy Pattern)
class ProgressReporter(ABC):
    """Abstract base class for progress reporters."""

    @abstractmethod
    def start(self, description: str, total: int | None = None) -> None:
        """Start progress tracking."""

    @abstractmethod
    def update(self, delta: int) -> None:
        """Update progress by delta bytes."""

    @abstractmethod
    def finish(self) -> None:
        """Finish progress tracking."""


class SimpleProgressReporter(ProgressReporter):
    """Simple single-line progress reporter for TTY."""

    def __init__(self, file_name: str):
        self.file_name = file_name
        self.downloaded = 0
        self.total: int | None = None

    def start(self, description: str, total: int | None = None) -> None:
        self.total = total
        self._update_display()

    def update(self, delta: int) -> None:
        self.downloaded += delta
        self._update_display()

    def _update_display(self) -> None:
        if self.total and self.total > 0:
            pct = (self.downloaded / self.total) * 100.0
            s = f"{pct:.1f}% ({U.human_bytes(self.downloaded)}/{U.human_bytes(self.total)})"
        else:
            s = f"{U.human_bytes(self.downloaded)} (size unknown)"
        sys.stdout.write(f"Downloading {self.file_name}: {s} \r")
        sys.stdout.flush()

    def finish(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


class LoggingProgressReporter(ProgressReporter):
    """Logging-based progress reporter (works in all environments)."""

    def __init__(self, logger: logging.Logger, log_every_bytes: int = 128 * 1024 * 1024):
        self.logger = logger
        self.log_every_bytes = log_every_bytes
        self.downloaded = 0
        self.total: int | None = None
        self.last_log_mark = 0
        self.description = ""

    def start(self, description: str, total: int | None = None) -> None:
        self.description = description
        self.total = total
        self.logger.info("Starting download: %s", description)

    def update(self, delta: int) -> None:
        self.downloaded += delta
        if self.downloaded - self.last_log_mark >= self.log_every_bytes:
            self.last_log_mark = self.downloaded
            if self.total and self.total > 0:
                pct = (self.downloaded / self.total) * 100.0
                self.logger.info(
                    "Download progress: %s / %s (%.1f%%)",
                    U.human_bytes(self.downloaded),
                    U.human_bytes(self.total),
                    pct,
                )
            else:
                self.logger.info("Download progress: %s", U.human_bytes(self.downloaded))

    def finish(self) -> None:
        if self.total and self.total > 0:
            pct = (self.downloaded / self.total) * 100.0
            self.logger.info(
                "Download completed: %s (%s / %s, %.1f%%)",
                self.description,
                U.human_bytes(self.downloaded),
                U.human_bytes(self.total),
                pct,
            )
        else:
            self.logger.info("Download completed: %s (%s)", self.description, U.human_bytes(self.downloaded))


class NoopProgressReporter(ProgressReporter):
    """No-op progress reporter (silent)."""

    def start(self, description: str, total: int | None = None) -> None:
        pass

    def update(self, delta: int) -> None:
        pass

    def finish(self) -> None:
        pass


# Progress Reporter Factory
def create_progress_reporter(
    options: Any,  # HTTPDownloadOptions from main module
    file_name: str,
    logger: logging.Logger,
) -> ProgressReporter:
    """
    Create appropriate progress reporter based on options and environment.

    Strategy:
    1. If show_progress=False → NoopProgressReporter
    2. If TTY → SimpleProgressReporter
    3. Fallback → LoggingProgressReporter
    """
    if not getattr(options, "show_progress", True):
        return NoopProgressReporter()

    if _is_tty():
        return SimpleProgressReporter(file_name)

    return LoggingProgressReporter(logger, getattr(options, "log_every_bytes", 128 * 1024 * 1024))
