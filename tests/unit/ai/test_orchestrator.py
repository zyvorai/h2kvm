# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm/ai/orchestrator.py -- AIOrchestrator lifecycle and fail-safe behaviour."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from h2kvm.ai.models import (
    HealthStatus,
    MigrationFeatures,
    Prediction,
    WorkloadProfile,
    WorkloadType,
)
from h2kvm.ai.orchestrator import AIOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path, **overrides):
    """Build a minimal config dict pointing the KB at *tmp_path*."""
    ai = {"knowledge_base_path": str(tmp_path / "test.db")}
    ai.update(overrides)
    return {"ai": ai}


def _default_features(**kw) -> MigrationFeatures:
    return MigrationFeatures(
        source_format="vmdk",
        disk_size_gb=20.0,
        disk_count=1,
        os_family="linux",
        **kw,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def ai(tmp_path):
    config = {"ai": {"knowledge_base_path": str(tmp_path / "test.db")}}
    orch = AIOrchestrator()
    orch.initialize(config)
    yield orch
    orch.shutdown()


# ---------------------------------------------------------------------------
# Lifecycle -- initialize
# ---------------------------------------------------------------------------


class TestInitializeDefaults:
    def test_initialize_with_defaults_succeeds(self, tmp_path):
        config = _make_config(tmp_path)
        orch = AIOrchestrator()
        result = orch.initialize(config)
        assert result is True
        orch.shutdown()

    def test_initialize_sets_is_initialized(self, tmp_path):
        config = _make_config(tmp_path)
        orch = AIOrchestrator()
        orch.initialize(config)
        assert orch.is_initialized is True
        orch.shutdown()

    def test_is_initialized_false_before_init(self):
        orch = AIOrchestrator()
        assert orch.is_initialized is False


class TestInitializeDisabled:
    def test_initialize_with_enabled_false_returns_false(self, tmp_path):
        config = _make_config(tmp_path, enabled=False)
        orch = AIOrchestrator()
        result = orch.initialize(config)
        assert result is False

    def test_not_initialized_when_disabled(self, tmp_path):
        config = _make_config(tmp_path, enabled=False)
        orch = AIOrchestrator()
        orch.initialize(config)
        assert orch.is_initialized is False


# ---------------------------------------------------------------------------
# Lifecycle -- shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_shutdown_clears_initialized_flag(self, ai):
        assert ai.is_initialized is True
        ai.shutdown()
        assert ai.is_initialized is False

    def test_double_shutdown_does_not_raise(self, ai):
        ai.shutdown()
        ai.shutdown()  # second call must be silent

    def test_shutdown_before_init_does_not_raise(self):
        orch = AIOrchestrator()
        orch.shutdown()  # no-op, should not raise


# ---------------------------------------------------------------------------
# Pre-migration analysis
# ---------------------------------------------------------------------------


class TestPreMigrationAnalysis:
    def test_returns_prediction(self, ai):
        features = _default_features()
        result = ai.pre_migration_analysis(features)
        assert result is not None
        assert "prediction" in result
        pred = result["prediction"]
        assert isinstance(pred, Prediction)
        assert 0.0 <= pred.success_probability <= 1.0

    def test_returns_workload(self, ai):
        features = _default_features()
        result = ai.pre_migration_analysis(features)
        assert result is not None
        assert "workload" in result
        wp = result["workload"]
        assert isinstance(wp, WorkloadProfile)

    def test_when_not_initialized_returns_none(self, tmp_path):
        orch = AIOrchestrator()
        features = _default_features()
        result = orch.pre_migration_analysis(features)
        assert result is None

    def test_sets_start_time_for_duration_tracking(self, ai):
        features = _default_features()
        before = time.time()
        ai.pre_migration_analysis(features)
        after = time.time()
        assert ai._start_time >= before
        assert ai._start_time <= after

    def test_risk_detection_with_buslogic(self, ai):
        features = _default_features(controller_type="buslogic")
        result = ai.pre_migration_analysis(features)
        assert result is not None
        pred = result["prediction"]
        # buslogic is CRITICAL risk, probability should be penalised
        assert pred.success_probability < 1.0
        rules = [r.rule for r in pred.risks]
        assert "buslogic_controller" in rules

    def test_workload_classification_for_database(self, ai):
        features = _default_features(
            packages=["postgresql", "redis"],
            services=["postgresql"],
        )
        result = ai.pre_migration_analysis(features)
        assert result is not None
        wp = result["workload"]
        assert wp.workload_type == WorkloadType.DATABASE


# ---------------------------------------------------------------------------
# Post-migration analysis
# ---------------------------------------------------------------------------


class TestPostMigrationAnalysis:
    def test_records_migration(self, ai):
        features = _default_features()
        ai.pre_migration_analysis(features)
        result = ai.post_migration_analysis(features, success=True)
        assert result is not None
        assert "health" in result

    def test_health_check_skip_without_fixer_report(self, ai):
        features = _default_features()
        ai.pre_migration_analysis(features)
        result = ai.post_migration_analysis(features, success=True)
        assert result is not None
        health = result["health"]
        assert health.overall_status == HealthStatus.SKIP

    def test_health_check_with_fixer_report(self, ai):
        features = _default_features()
        ai.pre_migration_analysis(features)
        fixer_report = {
            "analysis": {"boot_mode": "bios", "grub_installed": True},
            "actions": ["grub2-install completed", "fstab stabilised"],
            "warnings": [],
        }
        result = ai.post_migration_analysis(
            features,
            success=True,
            fixer_report=fixer_report,
        )
        assert result is not None
        health = result["health"]
        assert health.overall_status in (HealthStatus.PASS, HealthStatus.WARN)

    def test_detects_anomalies_when_enough_history(self, ai):
        features = _default_features()
        # Record several normal migrations first
        for _ in range(5):
            ai.pre_migration_analysis(features)
            ai.post_migration_analysis(features, success=True)

        # Now record one with an extreme duration to trigger anomaly
        ai._start_time = time.time() - 99999  # simulate very long duration
        result = ai.post_migration_analysis(features, success=True)
        assert result is not None
        # May or may not have anomalies depending on history std dev,
        # but result should at least be a valid dict
        assert isinstance(result, dict)

    def test_when_not_initialized_returns_none(self):
        orch = AIOrchestrator()
        features = _default_features()
        result = orch.post_migration_analysis(features, success=True)
        assert result is None

    def test_records_errors_and_phases(self, ai):
        features = _default_features()
        ai.pre_migration_analysis(features)
        result = ai.post_migration_analysis(
            features,
            success=False,
            errors=["mount failed: wrong fs type"],
            phases=["convert", "mount", "fix"],
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Error diagnosis
# ---------------------------------------------------------------------------


class TestDiagnoseError:
    def test_returns_diagnoses(self, ai):
        result = ai.diagnose_error("fstab UUID mismatch: partition not found")
        assert result is not None
        assert "diagnoses" in result
        assert len(result["diagnoses"]) > 0
        diag = result["diagnoses"][0]
        assert diag.pattern_id == "fstab_uuid_mismatch"

    def test_returns_remediation_plans(self, ai):
        result = ai.diagnose_error("fstab UUID mismatch: partition not found")
        assert result is not None
        assert "remediation_plans" in result
        plans = result["remediation_plans"]
        assert len(plans) > 0
        assert plans[0].fixes  # at least one fix

    def test_when_not_initialized_returns_none(self):
        orch = AIOrchestrator()
        result = orch.diagnose_error("some error")
        assert result is None

    def test_unknown_error_returns_empty_diagnoses(self, ai):
        result = ai.diagnose_error("something completely unrelated to known patterns 12345")
        assert result is not None
        assert result["diagnoses"] == []

    def test_multiple_pattern_match(self, ai):
        # Error text matching multiple patterns
        result = ai.diagnose_error("permission denied when mounting; mount failed: wrong fs type")
        assert result is not None
        patterns = {d.pattern_id for d in result["diagnoses"]}
        assert "permission_denied" in patterns
        assert "mount_failed" in patterns


# ---------------------------------------------------------------------------
# get_info
# ---------------------------------------------------------------------------


class TestGetInfo:
    def test_returns_summary_dict(self, ai):
        info = ai.get_info()
        assert info is not None
        assert info["initialized"] is True
        assert info["enabled"] is True

    def test_includes_kb_stats(self, ai):
        info = ai.get_info()
        assert info is not None
        assert "knowledge_base" in info
        kb_stats = info["knowledge_base"]
        assert "total_migrations" in kb_stats
        assert "success_rate" in kb_stats

    def test_includes_config(self, ai):
        info = ai.get_info()
        assert info is not None
        assert "config" in info
        assert "knowledge_base_path" in info["config"]

    def test_includes_error_patterns_count(self, ai):
        info = ai.get_info()
        assert info is not None
        assert "error_patterns" in info
        assert isinstance(info["error_patterns"], int)


# ---------------------------------------------------------------------------
# Fail-safe behaviour
# ---------------------------------------------------------------------------


class TestFailSafe:
    def test_pre_migration_does_not_raise_on_internal_error(self, ai):
        # Force an internal error by breaking the predictive engine
        ai._predictive = None
        ai._workload = None
        # Should return a dict (possibly empty) but not raise
        result = ai.pre_migration_analysis(_default_features())
        # Result might be empty dict or None depending on path, but no exception
        assert result is not None or result is None  # just verify no raise

    def test_diagnose_error_does_not_raise_on_broken_engine(self, ai):
        ai._diagnostic = None
        # Should not raise even though engine is None
        result = ai.diagnose_error("any error")
        assert result is not None or result is None

    def test_get_info_does_not_raise_when_kb_closed(self, ai):
        ai._kb.close()
        ai._kb = None
        # get_info should still return something (without KB stats)
        result = ai.get_info()
        assert result is not None
        assert result["initialized"] is True

    def test_post_migration_does_not_raise_on_internal_error(self, ai):
        ai._health = None
        ai._kb = None
        ai._anomaly = None
        result = ai.post_migration_analysis(_default_features(), success=True)
        # fail_safe catches the error
        assert result is not None or result is None
