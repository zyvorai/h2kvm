# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for h2kvm.ai.predictive.PredictiveEngine."""

from __future__ import annotations

import pytest

from h2kvm.ai.knowledge_base import KnowledgeBase
from h2kvm.ai.models import AIConfig, MigrationFeatures, MigrationRecord, RiskLevel
from h2kvm.ai.predictive import PredictiveEngine, RISK_RULES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(str(tmp_path / "test.db"))


@pytest.fixture
def engine(kb):
    return PredictiveEngine(kb)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_features(**overrides) -> MigrationFeatures:
    """Create a MigrationFeatures with sensible defaults, applying overrides."""
    kw = dict(
        source_format="vmdk",
        disk_size_gb=40.0,
        disk_count=1,
        os_family="linux",
        controller_type="lsilogic",
        has_snapshots=False,
        snapshot_count=0,
        has_luks=False,
        has_uefi=False,
        fstab_entries=3,
    )
    kw.update(overrides)
    return MigrationFeatures(**kw)


def _seed_history(kb, count=5, success=True, duration=120.0, features=None):
    """Insert *count* migration records into the knowledge base."""
    feat = features or _default_features()
    for i in range(count):
        rec = MigrationRecord(
            record_id=f"seed-{i}",
            features=feat,
            success=success,
            duration_seconds=duration,
        )
        kb.record_migration(rec)


# ---------------------------------------------------------------------------
# RISK_RULES sanity
# ---------------------------------------------------------------------------


class TestRiskRules:
    def test_risk_rules_non_empty(self):
        assert len(RISK_RULES) > 0

    def test_risk_rules_have_required_keys(self):
        for rule in RISK_RULES:
            assert "id" in rule
            assert "check" in rule
            assert "level" in rule
            assert "message" in rule
            assert "mitigation" in rule


# ---------------------------------------------------------------------------
# Prediction with empty knowledge base
# ---------------------------------------------------------------------------


class TestPredictEmptyKB:
    def test_predict_empty_kb_returns_low_confidence(self, engine):
        features = _default_features()
        pred = engine.predict(features)
        assert pred.confidence == "low"
        assert pred.similar_count == 0

    def test_predict_empty_kb_no_risk_returns_full_probability(self, engine):
        features = _default_features()
        pred = engine.predict(features)
        assert pred.success_probability == 1.0


# ---------------------------------------------------------------------------
# Individual risk detection
# ---------------------------------------------------------------------------


class TestRiskDetection:
    def test_buslogic_risk(self, engine):
        features = _default_features(controller_type="buslogic")
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "buslogic_controller" in risk_rules
        buslogic = next(r for r in pred.risks if r.rule == "buslogic_controller")
        assert buslogic.level == RiskLevel.CRITICAL

    def test_snapshot_risk(self, engine):
        features = _default_features(has_snapshots=True, snapshot_count=1)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "active_snapshots" in risk_rules
        snap = next(r for r in pred.risks if r.rule == "active_snapshots")
        assert snap.level == RiskLevel.HIGH

    def test_luks_risk(self, engine):
        features = _default_features(has_luks=True)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "luks_encrypted" in risk_rules
        luks = next(r for r in pred.risks if r.rule == "luks_encrypted")
        assert luks.level == RiskLevel.MEDIUM

    def test_uefi_risk(self, engine):
        features = _default_features(has_uefi=True)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "uefi_boot" in risk_rules
        uefi = next(r for r in pred.risks if r.rule == "uefi_boot")
        assert uefi.level == RiskLevel.MEDIUM

    def test_large_disk_risk(self, engine):
        features = _default_features(disk_size_gb=600.0)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "large_disk" in risk_rules
        large = next(r for r in pred.risks if r.rule == "large_disk")
        assert large.level == RiskLevel.MEDIUM

    def test_multi_disk_risk(self, engine):
        features = _default_features(disk_count=5)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "multi_disk" in risk_rules
        multi = next(r for r in pred.risks if r.rule == "multi_disk")
        assert multi.level == RiskLevel.LOW

    def test_windows_risk(self, engine):
        features = _default_features(os_family="windows")
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "windows_os" in risk_rules
        win = next(r for r in pred.risks if r.rule == "windows_os")
        assert win.level == RiskLevel.MEDIUM

    def test_no_fstab_risk(self, engine):
        features = _default_features(fstab_entries=0)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "no_fstab" in risk_rules

    def test_many_snapshots_risk(self, engine):
        features = _default_features(has_snapshots=True, snapshot_count=5)
        pred = engine.predict(features)
        risk_rules = [r.rule for r in pred.risks]
        assert "many_snapshots" in risk_rules


# ---------------------------------------------------------------------------
# Risk penalty stacking
# ---------------------------------------------------------------------------


class TestRiskPenalties:
    def test_multiple_risks_stack_penalties(self, engine):
        features = _default_features(
            controller_type="buslogic",
            has_snapshots=True,
            has_luks=True,
        )
        pred = engine.predict(features)
        # CRITICAL * 0.5, HIGH * 0.8, MEDIUM * 0.95 -> significantly < 1.0
        assert pred.success_probability < 0.5
        assert len(pred.risks) >= 3

    def test_no_risk_features_gives_high_probability(self, engine):
        features = _default_features()
        pred = engine.predict(features)
        # Only "no_fstab" risk (fstab_entries=3 so no risk) -- should be ~1.0
        assert pred.success_probability >= 0.95

    def test_critical_risk_halves_probability(self, engine):
        clean = _default_features()
        risky = _default_features(controller_type="buslogic")
        pred_clean = engine.predict(clean)
        pred_risky = engine.predict(risky)
        # buslogic CRITICAL applies a 0.5 multiplier
        assert pred_risky.success_probability <= pred_clean.success_probability * 0.55


# ---------------------------------------------------------------------------
# History-weighted predictions
# ---------------------------------------------------------------------------


class TestHistoryPredictions:
    def test_predict_with_history_gives_higher_confidence(self, kb, engine):
        _seed_history(kb, count=5, success=True, duration=90.0)
        features = _default_features()
        pred = engine.predict(features)
        assert pred.confidence == "medium"
        assert pred.similar_count >= 5

    def test_predict_with_large_history_gives_high_confidence(self, kb, engine):
        _seed_history(kb, count=12, success=True, duration=90.0)
        features = _default_features()
        pred = engine.predict(features)
        assert pred.confidence == "high"
        assert pred.similar_count >= 10

    def test_similarity_weighted_success_probability(self, kb, engine):
        # Mix of successes and failures -- should be between 0 and 1
        for i in range(4):
            rec = MigrationRecord(
                record_id=f"ok-{i}",
                features=_default_features(),
                success=True,
                duration_seconds=100.0,
            )
            kb.record_migration(rec)
        for i in range(4):
            rec = MigrationRecord(
                record_id=f"fail-{i}",
                features=_default_features(),
                success=False,
                duration_seconds=100.0,
            )
            kb.record_migration(rec)
        features = _default_features()
        pred = engine.predict(features)
        # With 8 records (>= min_history=3), it should use weighted history
        assert pred.confidence in ("medium", "high")
        assert 0.1 < pred.success_probability < 0.9


# ---------------------------------------------------------------------------
# Duration estimation
# ---------------------------------------------------------------------------


class TestDurationEstimation:
    def test_duration_from_history(self, kb, engine):
        _seed_history(kb, count=5, success=True, duration=200.0)
        features = _default_features()
        pred = engine.predict(features)
        # Should be close to the seeded duration of 200s
        assert 150.0 < pred.estimated_duration_seconds < 250.0

    def test_duration_fallback_disk_heuristic(self, engine):
        features = _default_features(disk_size_gb=10.0)
        pred = engine.predict(features)
        # Fallback: disk_size_gb * 60 + 30 = 10*60 + 30 = 630
        assert pred.estimated_duration_seconds == pytest.approx(630.0, abs=1.0)

    def test_duration_fallback_minimum(self, engine):
        features = _default_features(disk_size_gb=0.0)
        pred = engine.predict(features)
        # max(30.0, 0*60+30) = 30.0
        assert pred.estimated_duration_seconds >= 30.0

    def test_duration_ignores_failed_records(self, kb, engine):
        # Only failed records with long durations
        _seed_history(kb, count=5, success=False, duration=9999.0)
        features = _default_features(disk_size_gb=20.0)
        pred = engine.predict(features)
        # Failed records are excluded from duration estimation
        # Fallback: 20*60+30 = 1230
        assert pred.estimated_duration_seconds < 2000.0


# ---------------------------------------------------------------------------
# PredictiveEngine with AIConfig
# ---------------------------------------------------------------------------


class TestPredictiveEngineConfig:
    def test_engine_respects_min_history_config(self, kb):
        config = AIConfig(min_history_for_prediction=10)
        eng = PredictiveEngine(kb, config=config)
        _seed_history(kb, count=5, success=True)
        features = _default_features()
        pred = eng.predict(features)
        # Only 5 records, but min_history is 10, so confidence is "low"
        assert pred.confidence == "low"

    def test_engine_respects_max_lookback_config(self, kb):
        config = AIConfig(max_similar_lookback=2)
        eng = PredictiveEngine(kb, config=config)
        _seed_history(kb, count=10, success=True, duration=100.0)
        features = _default_features()
        pred = eng.predict(features)
        # Only looks back at 2 records
        assert pred.similar_count <= 2
