# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/progress.py
"""
Progress tracking for CLI.

Provides progress bars and spinners for long-running operations.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProgressBar:
    """
    Simple progress bar.

    Attributes:
        total: Total number of items
        current: Current progress
        width: Progress bar width in characters
        prefix: Text prefix before bar
        suffix: Text suffix after bar
    """

    total: int
    current: int = 0
    width: int = 40
    prefix: str = "Progress"
    suffix: str = ""

    def update(self, current: int | None = None, increment: int = 1) -> None:
        """
        Update progress.

        Args:
            current: Set current value (overrides increment)
            increment: Increment current by this amount
        """
        if current is not None:
            self.current = current
        else:
            self.current += increment

        self.render()

    def render(self) -> None:
        """Render progress bar."""
        percent = 100.0 if self.total == 0 else self.current / self.total * 100

        filled = int(self.width * self.current / self.total) if self.total > 0 else self.width
        bar_str = "█" * filled + "-" * (self.width - filled)

        # Clear line and write progress
        sys.stdout.write(f"\r{self.prefix}: |{bar_str}| {percent:.1f}% {self.suffix}")
        sys.stdout.flush()

        # Newline when complete
        if self.current >= self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()


class Spinner:
    """
    Simple spinner for indeterminate progress.

    Attributes:
        message: Spinner message
        frames: Animation frames
    """

    def __init__(self, message: str = "Processing"):
        """
        Initialize spinner.

        Args:
            message: Spinner message
        """
        self.message = message
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_frame = 0
        self.is_running = False

    def start(self) -> None:
        """Start spinner."""
        self.is_running = True
        self.render()

    def stop(self, final_message: str | None = None) -> None:
        """
        Stop spinner.

        Args:
            final_message: Optional final message to display
        """
        self.is_running = False

        # Clear spinner line
        sys.stdout.write(f"\r{' ' * (len(self.message) + 10)}\r")

        if final_message:
            sys.stdout.write(f"{final_message}\n")

        sys.stdout.flush()

    def update(self, message: str | None = None) -> None:
        """
        Update spinner.

        Args:
            message: Optional new message
        """
        if message:
            self.message = message

        self.current_frame = (self.current_frame + 1) % len(self.frames)
        self.render()

    def render(self) -> None:
        """Render spinner frame."""
        if not self.is_running:
            return

        frame = self.frames[self.current_frame]
        sys.stdout.write(f"\r{frame} {self.message}")
        sys.stdout.flush()


class ProgressTracker:
    """
    Progress tracker for multi-stage operations.

    Tracks progress across multiple stages with estimated time remaining.
    """

    def __init__(self, stages: list[str]):
        """
        Initialize progress tracker.

        Args:
            stages: List of stage names
        """
        self.stages = stages
        self.current_stage_idx = 0
        self.stage_progress: dict[str, float] = dict.fromkeys(stages, 0.0)
        self.start_time = time.time()

    def start_stage(self, stage: str) -> None:
        """
        Start a new stage.

        Args:
            stage: Stage name
        """
        if stage in self.stages:
            self.current_stage_idx = self.stages.index(stage)
            self.stage_progress[stage] = 0.0
            self._render()

    def update_stage(self, stage: str, progress: float) -> None:
        """
        Update stage progress.

        Args:
            stage: Stage name
            progress: Progress percentage (0.0 to 100.0)
        """
        if stage in self.stage_progress:
            self.stage_progress[stage] = min(progress, 100.0)
            self._render()

    def complete_stage(self, stage: str) -> None:
        """
        Mark stage as complete.

        Args:
            stage: Stage name
        """
        if stage in self.stage_progress:
            self.stage_progress[stage] = 100.0
            self._render()

    def get_overall_progress(self) -> float:
        """
        Get overall progress percentage.

        Returns:
            Progress percentage (0.0 to 100.0)
        """
        if not self.stages:
            return 100.0

        total_progress = sum(self.stage_progress.values())
        return total_progress / len(self.stages)

    def get_eta(self) -> str:
        """
        Get estimated time remaining.

        Returns:
            ETA string (e.g., "2m 30s")
        """
        elapsed = time.time() - self.start_time
        progress = self.get_overall_progress()

        if progress == 0:
            return "Unknown"

        total_time = (elapsed / progress) * 100
        remaining = total_time - elapsed

        if remaining < 0:
            return "0s"

        minutes = int(remaining // 60)
        seconds = int(remaining % 60)

        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def _render(self) -> None:
        """Render progress tracker."""
        overall_progress = self.get_overall_progress()
        current_stage = (
            self.stages[self.current_stage_idx] if self.current_stage_idx < len(self.stages) else "Done"
        )
        eta = self.get_eta()

        # Clear line and render
        sys.stdout.write(f"\r[{overall_progress:.1f}%] {current_stage} (ETA: {eta})        ")
        sys.stdout.flush()

        # Newline when complete
        if overall_progress >= 100.0:
            sys.stdout.write("\n")
            sys.stdout.flush()
