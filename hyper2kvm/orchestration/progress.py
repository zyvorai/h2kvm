# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Structured progress output for batch migrations.

Emits machine-readable JSON progress events to stdout or a file,
enabling external tools (CI, monitoring, TUI) to track migration state.

Usage:
    tracker = ProgressTracker(output="json", file="/tmp/progress.jsonl")
    tracker.start_batch(total=5)
    tracker.start_item("vm1.vmdk")
    tracker.update_progress("vm1.vmdk", phase="converting", percent=45.0)
    tracker.complete_item("vm1.vmdk")
    tracker.finish_batch()
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

logger = logging.getLogger(__name__)


@dataclass
class ItemProgress:
    """Progress state for a single migration item."""

    name: str
    phase: str = "pending"  # pending, copying, converting, fixing, compressing, done, failed
    percent: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""
    output_path: str = ""

    @property
    def duration_s(self) -> float:
        """Elapsed seconds since this item started, or 0 if not yet started."""
        end = self.completed_at or time.time()
        return end - self.started_at if self.started_at else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary of this item's progress."""
        return {
            "name": self.name,
            "phase": self.phase,
            "percent": round(self.percent, 1),
            "duration_s": round(self.duration_s, 1),
            "error": self.error,
            "output_path": self.output_path,
        }


class ProgressTracker:
    """Emits structured progress events for batch migrations."""

    def __init__(
        self,
        output: str = "json",  # "json", "text", "silent"
        file: str | None = None,  # Write progress to file (JSONL)
    ):
        self.output = output
        self.items: dict[str, ItemProgress] = {}
        self.total = 0
        self.completed = 0
        self.failed = 0
        self.started_at = 0.0
        self._file: TextIO | None = None

        if file:
            Path(file).parent.mkdir(parents=True, exist_ok=True)
            self._file = open(  # noqa: SIM115 - handle outlives __init__, closed explicitly in close()  # pylint: disable=consider-using-with  # file stays open across many method calls; closed explicitly in close()/finish_batch()
                file, "a", encoding="utf-8"
            )

    def close(self) -> None:
        """Flush and close the progress-log file handle, if one is open."""
        if self._file:
            self._file.close()
            self._file = None

    def start_batch(self, total: int, names: list[str] | None = None) -> None:
        """Record the start of a batch of `total` items and emit a batch_start event."""
        self.total = total
        self.started_at = time.time()
        self.completed = 0
        self.failed = 0
        if names:
            for name in names:
                self.items[name] = ItemProgress(name=name)
        self._emit("batch_start", {"total": total})

    def start_item(self, name: str) -> None:
        """Mark item `name` as starting and emit an item_start event."""
        item = self.items.setdefault(name, ItemProgress(name=name))
        item.phase = "starting"
        item.started_at = time.time()
        item.percent = 0.0
        self._emit("item_start", {"name": name})

    def update_progress(
        self,
        name: str,
        phase: str | None = None,
        percent: float | None = None,
        message: str | None = None,
    ) -> None:
        """Update phase/percent for item `name` and emit a progress event."""
        item = self.items.get(name)
        if not item:
            return
        if phase:
            item.phase = phase
        if percent is not None:
            item.percent = min(100.0, max(0.0, percent))
        self._emit(
            "progress",
            {
                "name": name,
                "phase": item.phase,
                "percent": round(item.percent, 1),
                "message": message or "",
                "batch_percent": round(self._batch_percent(), 1),
            },
        )

    def complete_item(self, name: str, output_path: str = "") -> None:
        """Mark item `name` as done and emit an item_complete event."""
        item = self.items.get(name)
        if not item:
            return
        item.phase = "done"
        item.percent = 100.0
        item.completed_at = time.time()
        item.output_path = output_path
        self.completed += 1
        self._emit(
            "item_complete",
            {
                "name": name,
                "duration_s": round(item.duration_s, 1),
                "output_path": output_path,
                "batch_progress": f"{self.completed}/{self.total}",
            },
        )

    def fail_item(self, name: str, error: str) -> None:
        """Mark item `name` as failed and emit an item_failed event."""
        item = self.items.get(name)
        if not item:
            return
        item.phase = "failed"
        item.completed_at = time.time()
        item.error = error
        self.failed += 1
        self._emit(
            "item_failed",
            {
                "name": name,
                "error": error,
                "duration_s": round(item.duration_s, 1),
            },
        )

    def finish_batch(self) -> dict[str, Any]:
        """Emit a batch_complete event, close the file handle, and return the summary."""
        elapsed = time.time() - self.started_at if self.started_at else 0.0
        summary = {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "duration_s": round(elapsed, 1),
            "success": self.failed == 0,
        }
        self._emit("batch_complete", summary)
        self.close()
        return summary

    def get_summary(self) -> dict[str, Any]:
        """Return the current batch-level progress summary, including all items."""
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "in_progress": sum(
                1 for i in self.items.values() if i.phase not in ("done", "failed", "pending")
            ),
            "batch_percent": round(self._batch_percent(), 1),
            "items": {name: item.to_dict() for name, item in self.items.items()},
        }

    def _batch_percent(self) -> float:
        if self.total == 0:
            return 0.0
        item_percents = sum(i.percent for i in self.items.values())
        return item_percents / self.total

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        record = {
            "event": event,
            "timestamp": time.time(),
            **data,
        }

        if self.output == "json":
            line = json.dumps(record, default=str)
            print(line, file=sys.stderr, flush=True)

        elif self.output == "text":
            if event == "progress":
                name = data.get("name", "")
                pct = data.get("percent", 0)
                phase = data.get("phase", "")
                batch_pct = data.get("batch_percent", 0)
                print(f"  [{batch_pct:5.1f}%] {name}: {phase} ({pct:.0f}%)", file=sys.stderr, flush=True)
            elif event in ("item_complete", "item_failed"):
                name = data.get("name", "")
                dur = data.get("duration_s", 0)
                status = "DONE" if event == "item_complete" else f"FAILED: {data.get('error', '')}"
                print(f"  {name}: {status} ({dur}s)", file=sys.stderr, flush=True)
            elif event == "batch_complete":
                c = data.get("completed", 0)
                t = data.get("total", 0)
                f = data.get("failed", 0)
                d = data.get("duration_s", 0)
                print(f"  Batch complete: {c}/{t} succeeded, {f} failed ({d}s)", file=sys.stderr, flush=True)

        # Always write to file if configured
        if self._file:
            self._file.write(json.dumps(record, default=str) + "\n")
            self._file.flush()
