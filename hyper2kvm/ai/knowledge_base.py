# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/knowledge_base.py
"""
SQLite-backed knowledge base for migration history.

Thread-safe via a reentrant write lock.  Schema auto-created on first use
and versioned for future upgrades.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ._stats import cosine_similarity
from .models import MigrationFeatures, MigrationRecord

_SCHEMA_VERSION = 1

_CREATE_SQL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS migrations (
    record_id   TEXT PRIMARY KEY,
    timestamp   REAL NOT NULL,
    features    TEXT NOT NULL,
    success     INTEGER NOT NULL,
    duration_s  REAL NOT NULL,
    errors      TEXT NOT NULL DEFAULT '[]',
    phases      TEXT NOT NULL DEFAULT '[]',
    fixer_actions TEXT NOT NULL DEFAULT '[]',
    notes       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS error_patterns (
    pattern_id  TEXT PRIMARY KEY,
    regex       TEXT NOT NULL,
    root_cause  TEXT NOT NULL DEFAULT '',
    suggestions TEXT NOT NULL DEFAULT '[]',
    hit_count   INTEGER NOT NULL DEFAULT 0,
    last_seen   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_migrations_ts ON migrations(timestamp);
CREATE INDEX IF NOT EXISTS idx_migrations_success ON migrations(success);
"""


class KnowledgeBase:
    """SQLite-backed storage for migration records and error patterns."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = "~/.cache/hyper2kvm/ai/knowledge.db"
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    # -- connection --------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.executescript(_CREATE_SQL)
            # Insert version if missing
            cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (_SCHEMA_VERSION,),
                )
            conn.commit()

    # -- public API --------------------------------------------------------

    def record_migration(self, record: MigrationRecord) -> None:
        """Store a completed migration record."""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO migrations "
                "(record_id, timestamp, features, success, duration_s, errors, phases, fixer_actions, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.record_id,
                    record.timestamp,
                    json.dumps(record.features.to_dict()),
                    int(record.success),
                    record.duration_seconds,
                    json.dumps(record.errors),
                    json.dumps(record.phases),
                    json.dumps(record.fixer_actions),
                    record.notes,
                ),
            )
            conn.commit()

    def get_all_records(self, limit: int = 500) -> list[MigrationRecord]:
        """Retrieve recent migration records, newest first."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT * FROM migrations ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_record(r) for r in cur.fetchall()]

    def get_similar_migrations(
        self,
        features: MigrationFeatures,
        top_k: int = 10,
        max_lookback: int = 100,
    ) -> list[tuple[MigrationRecord, float]]:
        """Return the *top_k* most similar migration records with similarity scores."""
        records = self.get_all_records(limit=max_lookback)
        if not records:
            return []
        target_vec = features.to_vector()
        scored: list[tuple[MigrationRecord, float]] = []
        for rec in records:
            rec_vec = rec.features.to_vector()
            sim = cosine_similarity(target_vec, rec_vec)
            scored.append((rec, sim))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    def get_migration_stats(self) -> dict[str, Any]:
        """Aggregate statistics across all stored migrations."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("SELECT COUNT(*) as total FROM migrations")
            total = cur.fetchone()["total"]
            cur = conn.execute("SELECT COUNT(*) as ok FROM migrations WHERE success=1")
            successes = cur.fetchone()["ok"]
            cur = conn.execute("SELECT AVG(duration_s) as avg_dur FROM migrations")
            avg_dur = cur.fetchone()["avg_dur"] or 0.0
            cur = conn.execute("SELECT AVG(duration_s) as avg_dur FROM migrations WHERE success=1")
            avg_dur_success = cur.fetchone()["avg_dur"] or 0.0
            return {
                "total_migrations": total,
                "successful": successes,
                "failed": total - successes,
                "success_rate": (successes / total) if total else 0.0,
                "avg_duration_seconds": avg_dur,
                "avg_duration_success": avg_dur_success,
            }

    # -- error patterns ----------------------------------------------------

    def register_error_pattern(
        self,
        pattern_id: str,
        regex: str,
        root_cause: str = "",
        suggestions: list[str] | None = None,
    ) -> None:
        """Add or update a learned error pattern."""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO error_patterns "
                "(pattern_id, regex, root_cause, suggestions, hit_count, last_seen) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (
                    pattern_id,
                    regex,
                    root_cause,
                    json.dumps(suggestions or []),
                    time.time(),
                ),
            )
            conn.commit()

    def get_error_patterns(self) -> list[dict[str, Any]]:
        """Return all stored error patterns."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("SELECT * FROM error_patterns ORDER BY hit_count DESC")
            return [dict(r) for r in cur.fetchall()]

    def increment_error_pattern_hit(self, pattern_id: str) -> None:
        """Bump the hit counter + last_seen for a pattern."""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE error_patterns SET hit_count=hit_count+1, last_seen=? WHERE pattern_id=?",
                (time.time(), pattern_id),
            )
            conn.commit()

    # -- maintenance -------------------------------------------------------

    def prune_old_records(self, max_age_days: int = 180) -> int:
        """Delete migration records older than *max_age_days*.  Returns rows deleted."""
        cutoff = time.time() - (max_age_days * 86400)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("DELETE FROM migrations WHERE timestamp < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def close(self) -> None:
        """Close the underlying sqlite connection, if open."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MigrationRecord:
        features_dict = json.loads(row["features"])
        return MigrationRecord(
            record_id=row["record_id"],
            timestamp=row["timestamp"],
            features=MigrationFeatures.from_dict(features_dict),
            success=bool(row["success"]),
            duration_seconds=row["duration_s"],
            errors=json.loads(row["errors"]),
            phases=json.loads(row["phases"]),
            fixer_actions=json.loads(row["fixer_actions"]),
            notes=row["notes"],
        )
