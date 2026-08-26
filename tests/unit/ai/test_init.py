# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm/ai/__init__.py -- lazy imports and convenience functions."""

from __future__ import annotations

import pytest

import h2kvm.ai
from h2kvm.ai.models import MigrationFeatures


# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------


class TestLazyImports:
    def test_lazy_import_ai_orchestrator(self):
        cls = h2kvm.ai.AIOrchestrator
        from h2kvm.ai.orchestrator import AIOrchestrator

        assert cls is AIOrchestrator

    def test_lazy_import_migration_features(self):
        cls = h2kvm.ai.MigrationFeatures
        from h2kvm.ai.models import MigrationFeatures as MF

        assert cls is MF

    def test_lazy_import_prediction(self):
        cls = h2kvm.ai.Prediction
        from h2kvm.ai.models import Prediction

        assert cls is Prediction

    def test_lazy_import_diagnosis(self):
        cls = h2kvm.ai.Diagnosis
        from h2kvm.ai.models import Diagnosis

        assert cls is Diagnosis

    def test_lazy_import_health_report(self):
        cls = h2kvm.ai.HealthReport
        from h2kvm.ai.models import HealthReport

        assert cls is HealthReport

    def test_lazy_import_workload_profile(self):
        cls = h2kvm.ai.WorkloadProfile
        from h2kvm.ai.models import WorkloadProfile

        assert cls is WorkloadProfile


# ---------------------------------------------------------------------------
# __getattr__ error case
# ---------------------------------------------------------------------------


class TestAttributeError:
    def test_unknown_attribute_raises(self):
        with pytest.raises(AttributeError, match="no_such_thing"):
            _ = h2kvm.ai.no_such_thing


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------


class TestAll:
    def test_all_contains_expected_names(self):
        expected = {
            "AIOrchestrator",
            "Diagnosis",
            "HealthReport",
            "MigrationFeatures",
            "Prediction",
            "WorkloadProfile",
            "diagnose_issue",
            "predict_migration",
        }
        assert expected == set(h2kvm.ai.__all__)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestPredictMigration:
    def test_predict_migration_returns_prediction(self, tmp_path):
        config = {"ai": {"knowledge_base_path": str(tmp_path / "pred.db")}}
        features = MigrationFeatures(disk_size_gb=10.0)
        result = h2kvm.ai.predict_migration(features, merged_config=config)
        assert result is not None
        from h2kvm.ai.models import Prediction

        assert isinstance(result, Prediction)
        assert 0.0 <= result.success_probability <= 1.0

    def test_predict_migration_disabled_returns_none(self, tmp_path):
        config = {
            "ai": {
                "enabled": False,
                "knowledge_base_path": str(tmp_path / "pred_off.db"),
            }
        }
        features = MigrationFeatures(disk_size_gb=10.0)
        result = h2kvm.ai.predict_migration(features, merged_config=config)
        assert result is None


class TestDiagnoseIssue:
    def test_diagnose_issue_returns_result(self, tmp_path):
        config = {"ai": {"knowledge_base_path": str(tmp_path / "diag.db")}}
        result = h2kvm.ai.diagnose_issue(
            "grub bootloader not found",
            merged_config=config,
        )
        assert result is not None
        assert "diagnoses" in result
        assert len(result["diagnoses"]) > 0

    def test_diagnose_issue_disabled_returns_none(self, tmp_path):
        config = {
            "ai": {
                "enabled": False,
                "knowledge_base_path": str(tmp_path / "diag_off.db"),
            }
        }
        result = h2kvm.ai.diagnose_issue("some error", merged_config=config)
        assert result is None
