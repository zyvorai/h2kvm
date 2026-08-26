# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/recovery_manager.py
# pylint: disable=too-many-lines
# Cohesive checkpoint/recovery subsystem (models, locking, retention, querying);
# splitting would hurt readability more than help.
"""Recovery checkpoint management for migration workflows."""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import socket
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .constants import MAX_ERROR_MESSAGE_LENGTH, MAX_SAFE_STAGE_NAME_LENGTH
from .utils import U

if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore


# Helpers

_STAGE_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_stage(stage: str) -> str:
    stage = (stage or "").strip() or "unknown"
    stage = _STAGE_SAFE_RE.sub("-", stage)
    return stage[:MAX_SAFE_STAGE_NAME_LENGTH]


def _json_dumps(obj: Any, *, indent: int = 2) -> str:
    return json.dumps(obj, indent=indent, sort_keys=True)


def _sha256_text(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """
    Crash-safer atomic write:
      - write to unique temp file in same directory
      - fsync file
      - atomic replace
      - best-effort fsync directory entry
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd: int | None = None
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        with os.fdopen(fd, "w", encoding=encoding) as f:
            fd = None
            f.write(text)
            f.flush()
            with contextlib.suppress(Exception):
                os.fsync(f.fileno())

        Path(tmp_name).replace(path)

        try:
            dirfd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except Exception:  # pylint: disable=broad-exception-caught
            # Directory fsync is best-effort durability; must not fail the write.
            pass
    finally:
        if fd is not None:
            with contextlib.suppress(Exception):
                os.close(fd)
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort temp-file cleanup; must not mask the real write outcome.
                pass


def _read_text_best_effort(p: Path, *, encoding: str = "utf-8") -> str | None:
    try:
        return p.read_text(encoding=encoding)
    except Exception:  # pylint: disable=broad-exception-caught
        # Best-effort read used throughout recovery scanning; any failure means "unavailable".
        return None


# Exit codes + errors (automation-friendly)


@dataclass(frozen=True)
class ExitCode:  # pylint: disable=invalid-name
    """Enum-like namespace of exit codes used by recovery/checkpoint errors (UPPER_CASE by design)."""

    OK: int = 0
    CHECKPOINT_WRITE_FAILED: int = 20
    CHECKPOINT_READ_FAILED: int = 21
    CHECKPOINT_CORRUPT: int = 22
    NO_RECOVERY_POINT: int = 30
    LOCK_FAILED: int = 40
    STAGE_ORDER_VIOLATION: int = 50


class RecoveryError(RuntimeError):
    """Error raised for checkpoint/recovery failures, carrying a structured exit code and context."""

    def __init__(
        self,
        message: str,
        *,
        code: int,
        stage: str | None = None,
        checkpoint_id: str | None = None,
        path: Path | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.checkpoint_id = checkpoint_id
        self.path = path


# Stage definitions + deterministic recovery constraints


@dataclass(frozen=True)
class StageDef:
    """Static safety/behavior declaration for a named migration stage."""

    name: str
    resumable: bool = True
    safe_to_resume: bool = True
    requires_network: bool = False
    requires_guestfs: bool = False
    description: str | None = None


# Run manifest (audit trail)


@dataclass
class RunManifest:  # pylint: disable=too-many-instance-attributes
    """Audit-trail record of a migration run's identity, timing, and outcome (run.json)."""

    run_id: str
    created_ts: str
    host: str
    pid: int
    tool_version: str | None = None
    args_hash: str | None = None
    input_id: str | None = None  # e.g. VM name, image path hash, etc.
    status: str = "running"  # running|success|failed
    ended_ts: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation of this manifest."""
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> RunManifest:
        """Build a RunManifest from a dict (e.g. loaded from run.json), tolerating missing fields."""
        return RunManifest(
            run_id=str(d.get("run_id", "")),
            created_ts=str(d.get("created_ts", "")),
            host=str(d.get("host", "")),
            pid=int(d.get("pid", 0)),
            tool_version=(None if d.get("tool_version") in (None, "") else str(d.get("tool_version"))),
            args_hash=(None if d.get("args_hash") in (None, "") else str(d.get("args_hash"))),
            input_id=(None if d.get("input_id") in (None, "") else str(d.get("input_id"))),
            status=str(d.get("status", "running")),
            ended_ts=(None if d.get("ended_ts") in (None, "") else str(d.get("ended_ts"))),
            error=(None if d.get("error") in (None, "") else str(d.get("error"))),
        )


# Checkpoint model (with integrity + scopes)


@dataclass
class Checkpoint:  # pylint: disable=too-many-instance-attributes
    """A single recovery checkpoint: stage state, integrity hash, and resumability flags."""

    id: str
    stage: str
    timestamp: str
    data: dict[str, Any]

    # Optional “sub-stage” / scope support
    step: str | None = None  # e.g. "inject_storage"
    scope: str | None = None  # e.g. "windows_fix"
    parent_id: str | None = None  # links step checkpoints to a parent checkpoint id

    # State + compatibility
    completed: bool = False
    version: int = 3
    run_id: str | None = None

    # Safety flags (can be overridden by StageDef)
    resumable: bool = True
    safe_to_resume: bool = True

    # Integrity checks
    sha256: str | None = None
    bytes_len: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation of this checkpoint."""
        return asdict(self)

    def _canonical_json(self) -> str:
        # Important: canonical JSON for integrity hash (exclude sha256/bytes_len to avoid recursion)
        d = self.to_dict()
        d.pop("sha256", None)
        d.pop("bytes_len", None)
        return _json_dumps(d, indent=2)

    def finalize_integrity(self) -> None:
        """Compute and set this checkpoint's sha256/bytes_len integrity fields from its canonical JSON."""
        canon = self._canonical_json()
        self.bytes_len = len(canon.encode("utf-8", errors="replace"))
        self.sha256 = _sha256_text(canon)

    def to_json(self, *, indent: int = 2) -> str:
        """Finalize integrity fields and serialize this checkpoint to a JSON string."""
        # finalize before write
        self.finalize_integrity()
        return _json_dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Checkpoint:
        """Build a Checkpoint from a dict (e.g. loaded from a checkpoint file), tolerating missing fields."""
        stage = str(d.get("stage", ""))
        ts = str(d.get("timestamp", ""))
        cid = str(d.get("id") or f"{_safe_stage(stage)}_{ts}")

        return Checkpoint(
            id=cid,
            stage=stage,
            timestamp=ts,
            data=dict(d.get("data", {}) or {}),
            step=(None if d.get("step") in (None, "") else str(d.get("step"))),
            scope=(None if d.get("scope") in (None, "") else str(d.get("scope"))),
            parent_id=(None if d.get("parent_id") in (None, "") else str(d.get("parent_id"))),
            completed=bool(d.get("completed", False)),
            version=int(d.get("version", 1)),
            run_id=(None if d.get("run_id") in (None, "") else str(d.get("run_id"))),
            resumable=bool(d.get("resumable", True)),
            safe_to_resume=bool(d.get("safe_to_resume", True)),
            sha256=(None if d.get("sha256") in (None, "") else str(d.get("sha256"))),
            bytes_len=(None if d.get("bytes_len") in (None, "") else int(d.get("bytes_len"))),
        )

    @staticmethod
    def from_json(text: str) -> Checkpoint:
        """Build a Checkpoint from its JSON string representation."""
        return Checkpoint.from_dict(json.loads(text))

    def validate_integrity(self) -> bool:
        """Verify this checkpoint's sha256/bytes_len against its current canonical JSON."""
        # If old checkpoint has no hash, treat as “unknown but acceptable”.
        if not self.sha256 or not self.bytes_len:
            return True
        canon = self._canonical_json()
        if len(canon.encode("utf-8", errors="replace")) != int(self.bytes_len):
            return False
        return _sha256_text(canon) == self.sha256


# Recovery decision object (CLI can print this nicely)


@dataclass(frozen=True)
class RecoveryDecision:
    """Describes which checkpoint would be used to resume, and why (CLI-printable)."""

    checkpoint_id: str
    checkpoint_path: Path
    resume_stage: str
    resume_step: str | None
    resume_scope: str | None
    reason: str


# RecoveryManager


class RecoveryManager:  # pylint: disable=too-many-instance-attributes
    """
    Checkpoint manager with:
      ✅ crash-safer atomic writes (+ fsync)
      ✅ optional workdir locking (prevents concurrent stomping)
      ✅ run manifest (run.json)
      ✅ per-checkpoint JSON files (debuggable)
      ✅ optional JSONL event log index (append-only)
      ✅ integrity hashing to detect truncation/corruption
      ✅ latest-completed pointer for O(1) recovery
      ✅ deterministic recovery via stage_order + StageDef safety
      ✅ retention policies (newest N, last completed per stage, TTL)
      ✅ query helpers (list/latest/describe)

    Default behavior is library-friendly:
      - show_progress=False (no surprise UI spam)
    """

    def __init__(  # pylint: disable=too-many-arguments
        # Constructor configures many independent, orthogonal knobs (locking, indexing,
        # run identity, stage policy) for the whole recovery subsystem.
        self,
        logger: logging.Logger,
        workdir: Path,
        *,
        show_progress: bool = False,
        enable_index: bool = True,
        enable_lock: bool = True,
        run_id: str | None = None,
        tool_version: str | None = None,
        args_hash: str | None = None,
        input_id: str | None = None,
        stage_order: Sequence[str] | None = None,
        stage_defs: Sequence[StageDef] | None = None,
    ):
        self.logger = logger
        self.workdir = workdir
        self.show_progress = show_progress
        self.enable_index = enable_index
        self.enable_lock = enable_lock and (fcntl is not None)

        U.ensure_dir(workdir)

        self.run_id = (run_id or "").strip() or U.now_ts()
        self.tool_version = tool_version
        self.args_hash = args_hash
        self.input_id = input_id

        self.checkpoints: list[Checkpoint] = []

        self.stage_order = list(stage_order) if stage_order else None
        self._stage_rank: dict[str, int] | None = None
        if self.stage_order:
            self._stage_rank = {_safe_stage(s): i for i, s in enumerate(self.stage_order)}

        self.stage_defs: dict[str, StageDef] = {}
        if stage_defs:
            for sd in stage_defs:
                self.stage_defs[_safe_stage(sd.name)] = sd

        self._lock_fp = None  # file handle for flock

        # Write run manifest early (so you can find run metadata even if you crash).
        self._manifest = RunManifest(
            run_id=self.run_id,
            created_ts=U.now_ts(),
            host=socket.gethostname(),
            pid=os.getpid(),
            tool_version=self.tool_version,
            args_hash=self.args_hash,
            input_id=self.input_id,
        )
        self._write_manifest()

        if self.enable_lock:
            self._acquire_lock()

    # Paths

    def _manifest_path(self) -> Path:
        return self.workdir / "run.json"

    def _lock_path(self) -> Path:
        return self.workdir / ".lock"

    def _index_path(self) -> Path:
        return self.workdir / "checkpoints.jsonl"

    def _latest_completed_path(self) -> Path:
        return self.workdir / "latest_completed.json"

    def _checkpoint_id(self, stage: str, timestamp: str, *, scope: str | None, step: str | None) -> str:
        parts = [_safe_stage(stage), timestamp]
        if scope:
            parts.insert(0, _safe_stage(scope))
        if step:
            parts.append(_safe_stage(step))
        return "_".join(parts)

    def _checkpoint_path(self, cp: Checkpoint) -> Path:
        # Filename: checkpoint_<runid>_<scope?>_<stage>_<timestamp>_<step?>.json
        rid = _safe_stage(cp.run_id or self.run_id)
        st = _safe_stage(cp.stage)
        pieces = ["checkpoint", rid]
        if cp.scope:
            pieces.append(_safe_stage(cp.scope))
        pieces.append(st)
        pieces.append(cp.timestamp)
        if cp.step:
            pieces.append(_safe_stage(cp.step))
        name = "_".join(pieces) + ".json"
        return self.workdir / name

    # Locking

    def _acquire_lock(self) -> None:
        if fcntl is None:
            return
        p = self._lock_path()
        try:
            fp = p.open("a+", encoding="utf-8")
            fp.seek(0)
            fp.truncate(0)
            fp.write(_json_dumps({"pid": os.getpid(), "run_id": self.run_id, "ts": U.now_ts()}, indent=2))
            fp.flush()
            with contextlib.suppress(Exception):
                os.fsync(fp.fileno())

            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except Exception:  # pylint: disable=broad-exception-caught
                # Any flock failure must close fp before propagating; re-raised immediately below.
                fp.close()
                raise
            self._lock_fp = fp
            self.logger.debug("Acquired workdir lock: %s", p)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Lock acquisition can fail in many OS-specific ways; wrap uniformly as RecoveryError.
            raise RecoveryError(
                f"Failed to acquire workdir lock: {p} ({e})\n"
                f"    Another h2kvm process may be running in this directory.\n"
                f"    If no other process is active, remove the stale lock: rm -f {p}",
                code=ExitCode.LOCK_FAILED,
                path=p,
            ) from e

    def close(self) -> None:
        """Release the workdir lock. Call this when done with the manager."""
        self._release_lock()

    def _release_lock(self) -> None:
        try:
            if self._lock_fp is not None and fcntl is not None:
                with contextlib.suppress(Exception):
                    fcntl.flock(self._lock_fp.fileno(), fcntl.LOCK_UN)
                with contextlib.suppress(Exception):
                    self._lock_fp.close()
                self._lock_fp = None
        finally:
            # Do not delete lock file; its contents help debugging stale runs.
            pass

    # Manifest

    def _write_manifest(self) -> None:
        _atomic_write_text(self._manifest_path(), _json_dumps(self._manifest.to_dict(), indent=2))

    def mark_run_success(self) -> None:
        """Mark the run manifest as successfully completed and persist it."""
        self._manifest.status = "success"
        self._manifest.ended_ts = U.now_ts()
        self._manifest.error = None
        self._write_manifest()

    def mark_run_failed(self, error: str) -> None:
        """Mark the run manifest as failed with an error message and persist it."""
        self._manifest.status = "failed"
        self._manifest.ended_ts = U.now_ts()
        self._manifest.error = (error or "")[:MAX_ERROR_MESSAGE_LENGTH]
        self._write_manifest()

    # Index (JSONL event log)

    def _append_index_event(self, event: dict[str, Any]) -> None:
        if not self.enable_index:
            return
        p = self._index_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event, sort_keys=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                with contextlib.suppress(Exception):
                    os.fsync(f.fileno())
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Index is a debugging aid; a write failure here must not break the run.
            self.logger.debug("Failed to append checkpoint index event (%s): %s", p, e)

    # Progress

    def _maybe_progress(self):
        # No longer returns a Rich Progress; callers use logger directly.
        return None

    # Stage safety helpers

    def _stage_def(self, stage: str) -> StageDef | None:
        return self.stage_defs.get(_safe_stage(stage))

    def _rank(self, stage: str) -> int | None:
        if not self._stage_rank:
            return None
        return self._stage_rank.get(_safe_stage(stage))

    def assert_stage_order(self, prev_stage: str | None, next_stage: str) -> None:
        """
        Optional invariant: if stage_order provided, disallow “going backwards” unless caller opts out.
        """
        if not self.stage_order or not prev_stage:
            return
        pr = self._rank(prev_stage)
        nr = self._rank(next_stage)
        if pr is None or nr is None:
            return
        if nr < pr:
            raise RecoveryError(
                f"Stage order violation: cannot go from '{prev_stage}' to '{next_stage}' "
                f"(stages must proceed in order).\n"
                f"    This usually means a recovery checkpoint is out of sequence.\n"
                f"    To restart from scratch, remove the workdir and re-run.",
                code=ExitCode.STAGE_ORDER_VIOLATION,
                stage=next_stage,
            )

    # Save / complete

    def save_checkpoint(  # pylint: disable=too-many-arguments,too-many-locals
        # Checkpoint creation legitimately needs stage/scope/step/safety-flag inputs plus
        # several locals for id/path construction and atomic write bookkeeping.
        self,
        stage: str,
        data: dict[str, Any],
        *,
        scope: str | None = None,
        step: str | None = None,
        parent_id: str | None = None,
        resumable: bool | None = None,
        safe_to_resume: bool | None = None,
    ) -> Checkpoint:
        """Create, write, and record a new checkpoint for the given stage; returns it."""
        stage = (stage or "").strip() or "unknown"
        ts = U.now_ts()

        sd = self._stage_def(stage)
        r = sd.resumable if sd else True
        s = sd.safe_to_resume if sd else True
        if resumable is not None:
            r = bool(resumable)
        if safe_to_resume is not None:
            s = bool(safe_to_resume)

        cid = self._checkpoint_id(stage, ts, scope=scope, step=step)
        cp = Checkpoint(
            id=cid,
            stage=stage,
            timestamp=ts,
            data=data,
            scope=(None if not scope else str(scope)),
            step=(None if not step else str(step)),
            parent_id=(None if not parent_id else str(parent_id)),
            completed=False,
            run_id=self.run_id,
            resumable=r,
            safe_to_resume=s,
        )

        self.checkpoints.append(cp)

        cp_file = self._checkpoint_path(cp)
        try:
            _atomic_write_text(cp_file, cp.to_json(indent=2))
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Disk/OS write failures vary widely; wrap uniformly as RecoveryError.
            raise RecoveryError(
                f"Failed to write checkpoint: {cp_file} ({e})",
                code=ExitCode.CHECKPOINT_WRITE_FAILED,
                stage=stage,
                checkpoint_id=cp.id,
                path=cp_file,
            ) from e

        self._append_index_event({"type": "checkpoint", "run_id": self.run_id, "checkpoint": cp.to_dict()})
        self.logger.debug("Checkpoint saved: stage=%s id=%s file=%s", stage, cp.id, cp_file.name)
        return cp

    def mark_checkpoint_complete(  # pylint: disable=too-many-branches
        self, stage: str, *, scope: str | None = None, step: str | None = None
    ) -> Checkpoint | None:
        """
        Marks newest matching checkpoint as completed.
        Filters by run_id, and optionally scope/step.
        """
        stage = (stage or "").strip()
        scope = (scope or "").strip() or None
        step = (step or "").strip() or None

        # 1) In-memory newest first
        for cp in reversed(self.checkpoints):
            if cp.run_id != self.run_id:
                continue
            if cp.stage != stage:
                continue
            if scope is not None and (cp.scope or None) != scope:
                continue
            if step is not None and (cp.step or None) != step:
                continue
            if cp.completed:
                continue

            cp.completed = True
            cp_file = self._checkpoint_path(cp)
            try:
                if cp_file.exists():
                    _atomic_write_text(cp_file, cp.to_json(indent=2))
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Disk/OS write failures vary widely; wrap uniformly as RecoveryError.
                raise RecoveryError(
                    f"Failed to mark checkpoint complete (write): {cp_file} ({e})",
                    code=ExitCode.CHECKPOINT_WRITE_FAILED,
                    stage=stage,
                    checkpoint_id=cp.id,
                    path=cp_file,
                ) from e

            self._append_index_event(
                {"type": "complete", "run_id": self.run_id, "id": cp.id, "ts": U.now_ts()}
            )
            self._write_latest_completed(cp, cp_file)
            self.logger.debug("Checkpoint completed: stage=%s id=%s", stage, cp.id)
            return cp

        # 2) Fallback: scan files
        matches = self._find_checkpoint_files(stage=stage, scope=scope, step=step)
        if not matches:
            self.logger.debug(
                "No checkpoint files found to complete for stage=%s scope=%s step=%s", stage, scope, step
            )
            return None

        cp_file = matches[-1]
        text = _read_text_best_effort(cp_file)
        if text is None:
            return None
        try:
            cp = Checkpoint.from_json(text)
            if cp.run_id != self.run_id:
                return None
            if not cp.completed:
                cp.completed = True
                _atomic_write_text(cp_file, cp.to_json(indent=2))
            self._append_index_event(
                {"type": "complete", "run_id": self.run_id, "id": cp.id, "ts": U.now_ts()}
            )
            self._write_latest_completed(cp, cp_file)
            self.logger.debug(
                "Checkpoint completed (file): stage=%s id=%s file=%s", stage, cp.id, cp_file.name
            )
            return cp
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort fallback completion from a scanned file; corrupt/unexpected data must not crash.
            self.logger.debug("Failed to mark checkpoint complete for %s (%s): %s", stage, cp_file, e)
            return None

    def _write_latest_completed(self, cp: Checkpoint, cp_path: Path) -> None:
        payload = {
            "run_id": self.run_id,
            "id": cp.id,
            "stage": cp.stage,
            "scope": cp.scope,
            "step": cp.step,
            "timestamp": cp.timestamp,
            "path": cp_path.name,
        }
        try:
            _atomic_write_text(self._latest_completed_path(), _json_dumps(payload, indent=2))
        except Exception:  # pylint: disable=broad-exception-caught
            # pointer failure should never break the run
            pass

    # Query helpers

    def list_checkpoints(self, *, completed_only: bool = False) -> list[Checkpoint]:
        """Return all known checkpoints for this run, optionally filtered to completed ones."""
        cps = [cp for _, cp in self._load_all_checkpoint_files()]
        if completed_only:
            cps = [cp for cp in cps if cp.completed]
        return cps

    def latest_checkpoint(
        self,
        *,
        stage: str | None = None,
        scope: str | None = None,
        step: str | None = None,
        completed_only: bool = True,
    ) -> Checkpoint | None:
        """Return the newest checkpoint matching the given stage/scope/step filters, if any."""
        cps = self._load_all_checkpoint_files()
        for _p, cp in reversed(cps):  # newest first by filename sort inside loader
            if completed_only and not cp.completed:
                continue
            if stage is not None and cp.stage != stage:
                continue
            if scope is not None and (cp.scope or None) != scope:
                continue
            if step is not None and (cp.step or None) != step:
                continue
            return cp
        return None

    # Loading / scanning

    def _find_checkpoint_files(
        self,
        *,
        stage: str | None = None,
        scope: str | None = None,
        step: str | None = None,
    ) -> list[Path]:
        # Files are named: checkpoint_<runid>_<scope?>_<stage>_<timestamp>_<step?>.json
        rid = _safe_stage(self.run_id)
        files = sorted(self.workdir.glob(f"checkpoint_{rid}_*.json"))

        def ok_name(p: Path) -> bool:
            name = p.name
            if stage and f"_{_safe_stage(stage)}_" not in name:
                return False
            if scope and f"_{_safe_stage(scope)}_" not in name:
                return False
            if step:
                # step is at end as _<step>.json, but keep it loose
                if f"_{_safe_stage(step)}.json" not in name and f"_{_safe_stage(step)}_" not in name:
                    return False
            return True

        return [p for p in files if ok_name(p)]

    def _load_all_checkpoint_files(self) -> list[tuple[Path, Checkpoint]]:
        files = self._find_checkpoint_files()
        out: list[tuple[Path, Checkpoint]] = []
        if not files:
            return out

        self.logger.info("Scanning %d checkpoint files", len(files))
        for p in files:
            try:
                text = p.read_text(encoding="utf-8")
                cp = Checkpoint.from_json(text)
                if cp.run_id != self.run_id:
                    continue
                if not cp.validate_integrity():
                    self.logger.debug("Checkpoint integrity failed: %s", p)
                    continue
                out.append((p, cp))
            except Exception:  # pylint: disable=broad-exception-caught
                # Malformed/unreadable checkpoint file; skip it rather than abort scanning.
                self.logger.debug("Skipping unreadable checkpoint: %s", p)
        self.logger.info("Scanned %d checkpoints, found %d matching", len(files), len(out))

        out.sort(key=lambda x: x[0].name)
        return out

    # pylint: disable-next=too-many-return-statements
    def _read_latest_completed_pointer(self) -> tuple[Path, Checkpoint] | None:
        # Many early-out guards validating the pointer file and referenced checkpoint; each
        # is a distinct "pointer is unusable" case that reads more clearly as an early return.
        p = self._latest_completed_path()
        txt = _read_text_best_effort(p)
        if not txt:
            return None
        try:
            d = json.loads(txt)
            if str(d.get("run_id", "")) != self.run_id:
                return None
            fname = str(d.get("path", "")).strip()
            if not fname:
                return None
            cp_path = self.workdir / fname
            cp_txt = _read_text_best_effort(cp_path)
            if not cp_txt:
                return None
            cp = Checkpoint.from_json(cp_txt)
            if cp.run_id != self.run_id:
                return None
            if not cp.completed:
                return None
            if not cp.validate_integrity():
                return None
            return (cp_path, cp)
        except Exception:  # pylint: disable=broad-exception-caught
            # Malformed pointer/checkpoint file; treat as "no usable pointer".
            return None

    # Recovery (describe + perform)

    # Recovery policy has several independent, orthogonal knobs (scope/step filters, stage-order
    # overrides, pointer preference), and evaluating them requires the branching to match.
    # pylint: disable-next=too-many-arguments,too-many-branches
    def describe_recovery(
        self,
        stage: str,
        *,
        scope: str | None = None,
        step: str | None = None,
        allow_same_stage: bool = False,
        allow_later_stage: bool = False,
        prefer_pointer: bool = True,
    ) -> RecoveryDecision | None:
        """
        Returns a RecoveryDecision without mutating anything.
        """
        stage = (stage or "").strip()
        scope = (scope or "").strip() or None
        step = (step or "").strip() or None

        # Fast path: latest pointer (if caller isn't asking for stage/scoped filtering)
        if prefer_pointer and scope is None and step is None:
            ptr = self._read_latest_completed_pointer()
            if ptr is not None:
                p, cp = ptr
                # pointer might still violate requested policy; check it
                if not allow_same_stage and _safe_stage(cp.stage) == _safe_stage(stage):
                    pass
                elif self._eligible_for_recovery(
                    cp, requested_stage=stage, allow_later_stage=allow_later_stage
                ):
                    return RecoveryDecision(
                        checkpoint_id=cp.id,
                        checkpoint_path=p,
                        resume_stage=cp.stage,
                        resume_step=cp.step,
                        resume_scope=cp.scope,
                        reason="latest_completed pointer",
                    )

        cps = self._load_all_checkpoint_files()
        if not cps:
            return None

        requested_safe = _safe_stage(stage)
        req_rank = self._rank(stage)

        # Newest -> oldest
        for p, cp in reversed(cps):
            if not cp.completed:
                continue
            if scope is not None and (cp.scope or None) != scope:
                continue
            if step is not None and (cp.step or None) != step:
                continue

            if not allow_same_stage and (_safe_stage(cp.stage) == requested_safe):
                continue

            if req_rank is not None:
                cp_rank = self._rank(cp.stage)
                if cp_rank is None:
                    if not allow_later_stage:
                        continue
                elif (cp_rank > req_rank) and not allow_later_stage:
                    continue

            if not self._eligible_for_recovery(
                cp, requested_stage=stage, allow_later_stage=allow_later_stage
            ):
                continue

            return RecoveryDecision(
                checkpoint_id=cp.id,
                checkpoint_path=p,
                resume_stage=cp.stage,
                resume_step=cp.step,
                resume_scope=cp.scope,
                reason="newest eligible completed checkpoint",
            )

        return None

    def _eligible_for_recovery(
        self, cp: Checkpoint, *, requested_stage: str, allow_later_stage: bool
    ) -> bool:
        # 1) Check checkpoint flags
        if not cp.resumable or not cp.safe_to_resume:
            return False

        # 2) StageDef can override safety (most strict wins)
        sd = self._stage_def(cp.stage)
        if sd is not None and (not sd.resumable or not sd.safe_to_resume):
            return False

        # 3) If stage ordering exists, optionally reject “later-than-requested”
        if self.stage_order and not allow_later_stage:
            req_rank = self._rank(requested_stage)
            cp_rank = self._rank(cp.stage)
            if req_rank is not None and cp_rank is not None and cp_rank > req_rank:
                return False

        return True

    # Mirrors describe_recovery()'s policy knobs so behavior stays in sync.
    # pylint: disable-next=too-many-arguments
    def recover_from_checkpoint(
        self,
        stage: str,
        *,
        scope: str | None = None,
        step: str | None = None,
        allow_same_stage: bool = False,
        allow_later_stage: bool = False,
        prefer_pointer: bool = True,
    ) -> dict[str, Any] | None:
        """
        Perform recovery (returns cp.data) using the same policy as describe_recovery().
        """
        decision = self.describe_recovery(
            stage,
            scope=scope,
            step=step,
            allow_same_stage=allow_same_stage,
            allow_later_stage=allow_later_stage,
            prefer_pointer=prefer_pointer,
        )
        if decision is None:
            return None

        txt = _read_text_best_effort(decision.checkpoint_path)
        if txt is None:
            raise RecoveryError(
                f"Failed to read recovery checkpoint: {decision.checkpoint_path}",
                code=ExitCode.CHECKPOINT_READ_FAILED,
                stage=stage,
                checkpoint_id=decision.checkpoint_id,
                path=decision.checkpoint_path,
            )
        try:
            cp = Checkpoint.from_json(txt)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # JSON/dataclass parsing can fail in many ways for a corrupt file; wrap uniformly.
            raise RecoveryError(
                f"Failed to parse recovery checkpoint: {decision.checkpoint_path} ({e})",
                code=ExitCode.CHECKPOINT_CORRUPT,
                stage=stage,
                checkpoint_id=decision.checkpoint_id,
                path=decision.checkpoint_path,
            ) from e
        if not cp.validate_integrity():
            raise RecoveryError(
                f"Checkpoint integrity verification failed: {decision.checkpoint_path}\n"
                f"    The checkpoint file may be corrupted (truncated write or disk error).\n"
                f"    Delete this checkpoint and retry the migration from scratch.",
                code=ExitCode.CHECKPOINT_CORRUPT,
                stage=stage,
                checkpoint_id=decision.checkpoint_id,
                path=decision.checkpoint_path,
            )

        self.logger.info(
            "Recovering: stage=%s scope=%s step=%s id=%s file=%s reason=%s",
            cp.stage,
            cp.scope,
            cp.step,
            cp.id,
            decision.checkpoint_path.name,
            decision.reason,
        )
        return cp.data

    # Retention / cleanup

    # Retention policy layers three independent rules (newest-N, per-stage, TTL) over the same
    # checkpoint list; each rule needs its own tracking locals and branch to stay understandable.
    # pylint: disable-next=too-many-locals,too-many-branches
    def cleanup_old_checkpoints(
        self,
        *,
        keep_newest_total: int = 50,
        keep_last_completed_per_stage: int = 1,
        keep_last_failed_run: bool = True,
        ttl_days: int | None = None,
        also_prune_index: bool = False,
    ) -> None:
        """
        Retention policy (practical + debuggable):
          - Always keep newest `keep_newest_total` checkpoints (any completion state)
          - Keep last N completed per stage (`keep_last_completed_per_stage`)
          - If keep_last_failed_run=True and manifest says failed, keep *all* checkpoints (no-op)
          - If ttl_days set, delete checkpoints older than TTL (best-effort based on timestamp lexicographic)
          - Optionally compact JSONL index (lossy, debugging tradeoff)

        NOTE: TTL requires U.now_ts() timestamps to be lexicographically sortable and parseable by your own conventions.
              We do a *best-effort* TTL here; if parsing is unclear, TTL is skipped.
        """
        # If last run failed and we want to keep everything, do nothing.
        if keep_last_failed_run:
            mf = self._read_manifest()
            if mf is not None and mf.status == "failed":
                self.logger.debug(
                    "Retention: run failed; preserving all checkpoints (keep_last_failed_run=True)."
                )
                return

        cps = self._load_all_checkpoint_files()
        if not cps:
            return

        cps_sorted = sorted(cps, key=lambda x: x[0].name, reverse=True)  # newest first
        keep: set[Path] = set()

        # 1) keep newest N
        for p, _ in cps_sorted[: max(0, int(keep_newest_total))]:
            keep.add(p)

        # 2) keep last completed per stage
        if keep_last_completed_per_stage > 0:
            per_stage: dict[str, int] = {}
            for p, cp in cps_sorted:
                if not cp.completed:
                    continue
                k = _safe_stage(cp.stage)
                per_stage.setdefault(k, 0)
                if per_stage[k] >= keep_last_completed_per_stage:
                    continue
                keep.add(p)
                per_stage[k] += 1

        # 3) TTL -- keep non-expired files that aren't already kept by other policies
        cutoff = self._compute_cutoff_ts_days(ttl_days) if (ttl_days is not None and ttl_days > 0) else None
        if cutoff is not None:
            for p, cp in cps_sorted:
                if p in keep:
                    continue
                # Keep files that are newer than the cutoff (not yet expired)
                if cp.timestamp and cp.timestamp >= cutoff:
                    keep.add(p)

        # Delete those not kept
        to_delete: list[Path] = []
        for p, _cp in cps_sorted:
            if p in keep:
                continue
            to_delete.append(p)

        if not to_delete:
            return

        self.logger.info("Cleaning %d old checkpoints", len(to_delete))
        for p in to_delete:
            try:
                p.unlink(missing_ok=True)  # type: ignore[arg-type]
                self.logger.debug("Cleaned old checkpoint: %s", p.name)
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort retention cleanup; a single stuck/missing file must not abort the loop.
                pass

        if also_prune_index and self.enable_index:
            self._compact_index_best_effort(keep_lines=max(500, 50 * keep_newest_total))

    def _compact_index_best_effort(self, *, keep_lines: int = 2000) -> None:
        idx = self._index_path()
        try:
            lines = idx.read_text(encoding="utf-8").splitlines()
            if len(lines) <= keep_lines:
                return
            _atomic_write_text(idx, "\n".join(lines[-keep_lines:]) + "\n")
        except Exception:  # pylint: disable=broad-exception-caught
            # Index compaction is a lossy debugging optimization; failure must not break the run.
            pass

    def _read_manifest(self) -> RunManifest | None:
        """Load and parse the run manifest (run.json), returning None if missing or invalid."""
        txt = _read_text_best_effort(self._manifest_path())
        if not txt:
            return None
        try:
            return RunManifest.from_dict(json.loads(txt))
        except Exception:  # pylint: disable=broad-exception-caught
            # Malformed manifest; treat as unavailable rather than failing retention/queries.
            return None

    def _compute_cutoff_ts_days(self, days: int | None) -> str | None:
        """Compute cutoff timestamp for TTL-based cleanup.

        Args:
            days: Number of days for TTL. Checkpoints older than this are eligible for deletion.

        Returns:
            Cutoff timestamp string (YYYYMMDD-HHMMSS format, matching U.now_ts()),
            or None if days is invalid.
        """
        if days is None or days <= 0:
            return None
        cutoff_dt = datetime.datetime.now() - datetime.timedelta(days=days)
        return cutoff_dt.strftime("%Y%m%d-%H%M%S")
