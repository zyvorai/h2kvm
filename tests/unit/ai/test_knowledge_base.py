# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.ai.knowledge_base.KnowledgeBase.

Covers record storage/retrieval, error-pattern management, similarity
search, statistics aggregation, pruning, close/reconnect, and basic
thread safety.
"""

from __future__ import annotations

import threading
import time

import pytest

from hyper2kvm.ai.knowledge_base import KnowledgeBase
from hyper2kvm.ai.models import MigrationFeatures, MigrationRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(str(tmp_path / "test.db"))


def _make_record(
    *,
    record_id: str = "rec1",
    success: bool = True,
    duration: float = 120.0,
    errors: list[str] | None = None,
    phases: list[str] | None = None,
    fixer_actions: list[str] | None = None,
    notes: str = "",
    timestamp: float | None = None,
    features: MigrationFeatures | None = None,
) -> MigrationRecord:
    return MigrationRecord(
        record_id=record_id,
        timestamp=timestamp if timestamp is not None else time.time(),
        features=features or MigrationFeatures(),
        success=success,
        duration_seconds=duration,
        errors=errors or [],
        phases=phases or [],
        fixer_actions=fixer_actions or [],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Constructor / DB creation
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "subdir" / "kb.db"
        KnowledgeBase(str(db_path))
        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path):
        db_path = tmp_path / "a" / "b" / "c" / "kb.db"
        KnowledgeBase(str(db_path))
        assert db_path.parent.is_dir()

    def test_schema_version_stored(self, tmp_path):
        import sqlite3

        db_path = str(tmp_path / "test.db")
        KnowledgeBase(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        assert row is not None
        assert row["version"] == 1
        conn.close()

    def test_reopen_existing_db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        kb1 = KnowledgeBase(db_path)
        kb1.record_migration(_make_record(record_id="r1"))
        kb1.close()
        kb2 = KnowledgeBase(db_path)
        records = kb2.get_all_records()
        assert len(records) == 1
        assert records[0].record_id == "r1"
        kb2.close()


# ---------------------------------------------------------------------------
# record_migration
# ---------------------------------------------------------------------------


class TestRecordMigration:
    def test_store_single_record(self, kb):
        rec = _make_record(record_id="abc")
        kb.record_migration(rec)
        records = kb.get_all_records()
        assert len(records) == 1
        assert records[0].record_id == "abc"

    def test_store_preserves_fields(self, kb):
        features = MigrationFeatures(
            disk_size_gb=42.0,
            os_family="linux",
            has_lvm=True,
            packages=["nginx"],
            services=["httpd"],
        )
        rec = _make_record(
            record_id="f1",
            success=False,
            duration=99.5,
            errors=["err1", "err2"],
            phases=["inspect", "convert"],
            fixer_actions=["fix_grub"],
            notes="test note",
            features=features,
        )
        kb.record_migration(rec)
        got = kb.get_all_records()[0]
        assert got.record_id == "f1"
        assert got.success is False
        assert got.duration_seconds == pytest.approx(99.5)
        assert got.errors == ["err1", "err2"]
        assert got.phases == ["inspect", "convert"]
        assert got.fixer_actions == ["fix_grub"]
        assert got.notes == "test note"
        assert got.features.disk_size_gb == pytest.approx(42.0)
        assert got.features.has_lvm is True
        assert got.features.packages == ["nginx"]

    def test_upsert_replaces_existing_record(self, kb):
        kb.record_migration(_make_record(record_id="dup", duration=100.0))
        kb.record_migration(_make_record(record_id="dup", duration=200.0))
        records = kb.get_all_records()
        assert len(records) == 1
        assert records[0].duration_seconds == pytest.approx(200.0)

    def test_store_multiple_records(self, kb):
        for i in range(5):
            kb.record_migration(_make_record(record_id=f"r{i}"))
        assert len(kb.get_all_records()) == 5


# ---------------------------------------------------------------------------
# get_all_records
# ---------------------------------------------------------------------------


class TestGetAllRecords:
    def test_empty_db_returns_empty_list(self, kb):
        assert kb.get_all_records() == []

    def test_returns_newest_first(self, kb):
        now = time.time()
        kb.record_migration(_make_record(record_id="old", timestamp=now - 100))
        kb.record_migration(_make_record(record_id="mid", timestamp=now - 50))
        kb.record_migration(_make_record(record_id="new", timestamp=now))
        records = kb.get_all_records()
        assert [r.record_id for r in records] == ["new", "mid", "old"]

    def test_limit_parameter(self, kb):
        for i in range(10):
            kb.record_migration(_make_record(record_id=f"r{i}", timestamp=float(i)))
        records = kb.get_all_records(limit=3)
        assert len(records) == 3
        # newest first: r9, r8, r7
        assert records[0].record_id == "r9"


# ---------------------------------------------------------------------------
# get_similar_migrations
# ---------------------------------------------------------------------------


class TestGetSimilarMigrations:
    def test_empty_db_returns_empty(self, kb):
        features = MigrationFeatures()
        result = kb.get_similar_migrations(features)
        assert result == []

    def test_returns_scored_tuples(self, kb):
        feat = MigrationFeatures(disk_size_gb=10.0, os_family="linux")
        kb.record_migration(_make_record(record_id="a", features=feat))
        kb.record_migration(
            _make_record(
                record_id="b",
                features=MigrationFeatures(disk_size_gb=1000.0, os_family="windows"),
            )
        )
        result = kb.get_similar_migrations(feat, top_k=5)
        assert len(result) == 2
        # Each item is (MigrationRecord, float)
        rec, score = result[0]
        assert isinstance(rec, MigrationRecord)
        assert isinstance(score, float)
        # The exact match should score higher
        assert result[0][1] >= result[1][1]

    def test_top_k_limits_results(self, kb):
        feat = MigrationFeatures(disk_size_gb=10.0)
        for i in range(20):
            kb.record_migration(_make_record(record_id=f"r{i}", features=feat))
        result = kb.get_similar_migrations(feat, top_k=5)
        assert len(result) == 5

    def test_identical_features_score_1(self, kb):
        feat = MigrationFeatures(disk_size_gb=50.0, has_lvm=True, fstab_entries=4)
        kb.record_migration(_make_record(record_id="same", features=feat))
        result = kb.get_similar_migrations(feat)
        assert len(result) == 1
        _, score = result[0]
        assert score == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# get_migration_stats
# ---------------------------------------------------------------------------


class TestGetMigrationStats:
    def test_empty_db_stats(self, kb):
        stats = kb.get_migration_stats()
        assert stats["total_migrations"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_duration_seconds"] == 0.0
        assert stats["avg_duration_success"] == 0.0

    def test_all_successful(self, kb):
        for i in range(3):
            kb.record_migration(
                _make_record(
                    record_id=f"s{i}",
                    success=True,
                    duration=100.0,
                )
            )
        stats = kb.get_migration_stats()
        assert stats["total_migrations"] == 3
        assert stats["successful"] == 3
        assert stats["failed"] == 0
        assert stats["success_rate"] == pytest.approx(1.0)
        assert stats["avg_duration_seconds"] == pytest.approx(100.0)

    def test_mixed_success_failure(self, kb):
        kb.record_migration(_make_record(record_id="ok1", success=True, duration=100.0))
        kb.record_migration(_make_record(record_id="ok2", success=True, duration=200.0))
        kb.record_migration(_make_record(record_id="fail1", success=False, duration=50.0))
        stats = kb.get_migration_stats()
        assert stats["total_migrations"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == pytest.approx(2 / 3)
        assert stats["avg_duration_seconds"] == pytest.approx((100 + 200 + 50) / 3)
        assert stats["avg_duration_success"] == pytest.approx((100 + 200) / 2)


# ---------------------------------------------------------------------------
# Error patterns
# ---------------------------------------------------------------------------


class TestErrorPatterns:
    def test_register_and_retrieve(self, kb):
        kb.register_error_pattern(
            pattern_id="ep1",
            regex="qemu-img: error.*",
            root_cause="disk corruption",
            suggestions=["re-export VMDK", "run fsck"],
        )
        patterns = kb.get_error_patterns()
        assert len(patterns) == 1
        p = patterns[0]
        assert p["pattern_id"] == "ep1"
        assert p["regex"] == "qemu-img: error.*"
        assert p["root_cause"] == "disk corruption"
        assert p["hit_count"] == 0

    def test_register_multiple_patterns(self, kb):
        kb.register_error_pattern("ep1", "error1.*")
        kb.register_error_pattern("ep2", "error2.*")
        kb.register_error_pattern("ep3", "error3.*")
        assert len(kb.get_error_patterns()) == 3

    def test_register_replaces_existing(self, kb):
        kb.register_error_pattern("ep1", "old_regex")
        kb.register_error_pattern("ep1", "new_regex")
        patterns = kb.get_error_patterns()
        assert len(patterns) == 1
        assert patterns[0]["regex"] == "new_regex"

    def test_empty_suggestions_default(self, kb):
        kb.register_error_pattern("ep1", "err.*")
        patterns = kb.get_error_patterns()
        import json

        assert json.loads(patterns[0]["suggestions"]) == []

    def test_increment_hit_count(self, kb):
        kb.register_error_pattern("ep1", "err.*")
        kb.increment_error_pattern_hit("ep1")
        kb.increment_error_pattern_hit("ep1")
        kb.increment_error_pattern_hit("ep1")
        patterns = kb.get_error_patterns()
        assert patterns[0]["hit_count"] == 3

    def test_increment_nonexistent_pattern_is_noop(self, kb):
        # Should not raise; just no rows affected
        kb.increment_error_pattern_hit("nonexistent")
        assert kb.get_error_patterns() == []

    def test_patterns_ordered_by_hit_count(self, kb):
        kb.register_error_pattern("low", "a.*")
        kb.register_error_pattern("high", "b.*")
        for _ in range(5):
            kb.increment_error_pattern_hit("high")
        kb.increment_error_pattern_hit("low")
        patterns = kb.get_error_patterns()
        assert patterns[0]["pattern_id"] == "high"
        assert patterns[1]["pattern_id"] == "low"


# ---------------------------------------------------------------------------
# prune_old_records
# ---------------------------------------------------------------------------


class TestPruneOldRecords:
    def test_prune_removes_old_records(self, kb):
        old_ts = time.time() - (200 * 86400)  # 200 days ago
        new_ts = time.time()
        kb.record_migration(_make_record(record_id="old", timestamp=old_ts))
        kb.record_migration(_make_record(record_id="new", timestamp=new_ts))
        deleted = kb.prune_old_records(max_age_days=180)
        assert deleted == 1
        records = kb.get_all_records()
        assert len(records) == 1
        assert records[0].record_id == "new"

    def test_prune_nothing_to_delete(self, kb):
        kb.record_migration(_make_record(record_id="recent"))
        deleted = kb.prune_old_records(max_age_days=180)
        assert deleted == 0
        assert len(kb.get_all_records()) == 1

    def test_prune_empty_db(self, kb):
        deleted = kb.prune_old_records()
        assert deleted == 0

    def test_prune_custom_max_age(self, kb):
        ts = time.time() - (10 * 86400)  # 10 days ago
        kb.record_migration(_make_record(record_id="ten_days_old", timestamp=ts))
        # 30-day window should keep it
        assert kb.prune_old_records(max_age_days=30) == 0
        # 5-day window should prune it
        assert kb.prune_old_records(max_age_days=5) == 1


# ---------------------------------------------------------------------------
# close and reconnection
# ---------------------------------------------------------------------------


class TestCloseAndReconnect:
    def test_close_then_reopen(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        kb = KnowledgeBase(db_path)
        kb.record_migration(_make_record(record_id="before_close"))
        kb.close()
        # After close, re-creating should work
        kb2 = KnowledgeBase(db_path)
        records = kb2.get_all_records()
        assert len(records) == 1
        kb2.close()

    def test_close_is_idempotent(self, kb):
        kb.close()
        kb.close()  # Should not raise

    def test_operations_after_close_reconnect(self, tmp_path):
        """Calling _get_conn after close should reconnect."""
        db_path = str(tmp_path / "test.db")
        kb = KnowledgeBase(db_path)
        kb.record_migration(_make_record(record_id="r1"))
        kb.close()
        # Internally _conn is None, next operation should reconnect
        kb.record_migration(_make_record(record_id="r2"))
        records = kb.get_all_records()
        assert len(records) == 2


# ---------------------------------------------------------------------------
# Thread safety (basic)
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_writes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        kb = KnowledgeBase(db_path)
        errors: list[Exception] = []

        def writer(start_id: int):
            try:
                for i in range(20):
                    kb.record_migration(_make_record(record_id=f"t{start_id}_{i}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        records = kb.get_all_records(limit=200)
        assert len(records) == 80  # 4 threads * 20 records

    def test_concurrent_reads_and_writes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        kb = KnowledgeBase(db_path)
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(20):
                    kb.record_migration(_make_record(record_id=f"w{i}"))
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                for _ in range(20):
                    kb.get_all_records()
                    kb.get_migration_stats()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
