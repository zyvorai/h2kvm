# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Integration tests for the h2kvm AI module -- end-to-end workflows."""

from __future__ import annotations

import time

import pytest

from h2kvm.ai.diagnostic import DiagnosticEngine
from h2kvm.ai.knowledge_base import KnowledgeBase
from h2kvm.ai.models import (
    HealthStatus,
    MigrationFeatures,
    MigrationRecord,
    Prediction,
    WorkloadProfile,
    WorkloadType,
)
from h2kvm.ai.orchestrator import AIOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(tmp_path, **overrides):
    """Build a config dict for tests."""
    ai = {"knowledge_base_path": str(tmp_path / "integ.db")}
    ai.update(overrides)
    return {"ai": ai}


def _features(**kw) -> MigrationFeatures:
    defaults = dict(
        source_format="vmdk",
        disk_size_gb=20.0,
        disk_count=1,
        os_family="linux",
        os_name="centos",
        os_version="7",
    )
    defaults.update(kw)
    return MigrationFeatures(**defaults)


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_init_pre_post_shutdown(self, tmp_path):
        """Complete happy-path: init -> pre-analysis -> post-analysis -> shutdown."""
        orch = AIOrchestrator()
        assert orch.initialize(_cfg(tmp_path)) is True
        assert orch.is_initialized is True

        features = _features()
        pre = orch.pre_migration_analysis(features)
        assert pre is not None
        assert "prediction" in pre
        assert "workload" in pre
        assert isinstance(pre["prediction"], Prediction)
        assert isinstance(pre["workload"], WorkloadProfile)

        post = orch.post_migration_analysis(features, success=True)
        assert post is not None
        assert "health" in post

        orch.shutdown()
        assert orch.is_initialized is False

    def test_lifecycle_with_errors(self, tmp_path):
        """Lifecycle with a failed migration recording."""
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features()
        orch.pre_migration_analysis(features)
        post = orch.post_migration_analysis(
            features,
            success=False,
            errors=["mount failed: wrong fs type", "permission denied"],
            phases=["convert", "mount"],
        )
        assert post is not None
        orch.shutdown()


# ---------------------------------------------------------------------------
# Diagnose and remediate
# ---------------------------------------------------------------------------


class TestDiagnoseAndRemediate:
    def test_known_error_yields_diagnosis_and_remediation(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        result = orch.diagnose_error("initramfs dracut failed: missing virtio driver")
        assert result is not None
        diags = result["diagnoses"]
        assert len(diags) >= 1
        assert diags[0].pattern_id == "initramfs_missing_drivers"
        assert diags[0].suggestions

        plans = result["remediation_plans"]
        assert len(plans) >= 1
        # Should include the initramfs regen fix
        fix_ids = [f.fix_id for p in plans for f in p.fixes]
        assert "initramfs_regen" in fix_ids

        orch.shutdown()

    def test_diagnosis_with_learned_pattern(self, tmp_path):
        """Error patterns registered in the KB are picked up by the diagnostic engine."""
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        # Teach a custom pattern via the KB directly
        orch._kb.register_error_pattern(
            pattern_id="custom_xfs_error",
            regex=r"(?i)xfs.*metadata.*corrupt",
            root_cause="XFS metadata corruption after snapshot flatten",
            suggestions=["Run xfs_repair", "Restore from backup"],
        )
        # Re-create the diagnostic engine to pick up the pattern
        diag_engine = DiagnosticEngine(orch._kb)
        diagnoses = diag_engine.diagnose("xfs metadata corrupt after conversion")
        assert any(d.pattern_id == "custom_xfs_error" for d in diagnoses)
        learned = [d for d in diagnoses if d.pattern_id == "custom_xfs_error"]
        assert learned[0].learned is True

        orch.shutdown()


# ---------------------------------------------------------------------------
# Knowledge base growth
# ---------------------------------------------------------------------------


class TestKnowledgeBaseGrowth:
    def test_kb_grows_with_recorded_migrations(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        info_before = orch.get_info()
        assert info_before["knowledge_base"]["total_migrations"] == 0

        for i in range(3):
            features = _features(disk_size_gb=10.0 + i)
            orch.pre_migration_analysis(features)
            orch.post_migration_analysis(features, success=True)

        info_after = orch.get_info()
        assert info_after["knowledge_base"]["total_migrations"] == 3
        assert info_after["knowledge_base"]["successful"] == 3
        assert info_after["knowledge_base"]["success_rate"] == 1.0

        orch.shutdown()

    def test_multiple_sequential_migrations_recorded_correctly(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        outcomes = [True, True, False, True, False]
        for success in outcomes:
            features = _features()
            orch.pre_migration_analysis(features)
            orch.post_migration_analysis(
                features,
                success=success,
                errors=["mount error"] if not success else [],
            )

        info = orch.get_info()
        stats = info["knowledge_base"]
        assert stats["total_migrations"] == 5
        assert stats["successful"] == 3
        assert stats["failed"] == 2

        orch.shutdown()


# ---------------------------------------------------------------------------
# Prediction confidence
# ---------------------------------------------------------------------------


class TestPredictionConfidence:
    def test_confidence_increases_with_more_history(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path, min_history_for_prediction=3))

        features = _features()

        # With no history, confidence should be "low"
        pre_no_history = orch.pre_migration_analysis(features)
        assert pre_no_history["prediction"].confidence == "low"

        # Record enough successful migrations to reach min_history
        for _ in range(5):
            orch.pre_migration_analysis(features)
            orch.post_migration_analysis(features, success=True)

        # Now predict again -- should have medium or high confidence
        pre_with_history = orch.pre_migration_analysis(features)
        assert pre_with_history["prediction"].confidence in ("medium", "high")
        assert pre_with_history["prediction"].similar_count >= 3

        orch.shutdown()


# ---------------------------------------------------------------------------
# Workload classification affects recommendations
# ---------------------------------------------------------------------------


class TestWorkloadClassification:
    def test_database_workload_recommendations(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features(
            packages=["postgresql", "redis-server"],
            services=["postgresql", "redis"],
        )
        result = orch.pre_migration_analysis(features)
        wp = result["workload"]
        assert wp.workload_type == WorkloadType.DATABASE
        assert wp.confidence > 0.0
        assert len(wp.recommendations) > 0
        assert any("database" in r.lower() or "I/O" in r for r in wp.recommendations)

        orch.shutdown()

    def test_webserver_workload_recommendations(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features(
            packages=["nginx", "certbot"],
            services=["nginx"],
        )
        result = orch.pre_migration_analysis(features)
        wp = result["workload"]
        assert wp.workload_type == WorkloadType.WEBSERVER
        assert len(wp.recommendations) > 0

        orch.shutdown()

    def test_generic_workload_when_no_indicators(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features(packages=[], services=[])
        result = orch.pre_migration_analysis(features)
        wp = result["workload"]
        assert wp.workload_type == WorkloadType.GENERIC

        orch.shutdown()


# ---------------------------------------------------------------------------
# Health check reflects fixer report contents
# ---------------------------------------------------------------------------


class TestHealthCheckIntegration:
    def test_health_pass_with_complete_fixer_report(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features()
        orch.pre_migration_analysis(features)
        fixer_report = {
            "analysis": {
                "boot_mode": "bios",
                "grub_installed": True,
                "initramfs_drivers": ["virtio_blk", "virtio_net"],
            },
            "actions": [
                "grub2-install completed",
                "fstab stabilised with UUID",
                "initramfs regenerated with virtio drivers",
                "vmware-tools removed",
            ],
            "warnings": [],
        }
        result = orch.post_migration_analysis(
            features,
            success=True,
            fixer_report=fixer_report,
        )
        health = result["health"]
        assert health.overall_status == HealthStatus.PASS
        assert health.passed() is True
        assert len(health.checks) > 0

        orch.shutdown()

    def test_health_warn_with_fstab_warnings(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features()
        orch.pre_migration_analysis(features)
        fixer_report = {
            "analysis": {"boot_mode": "bios"},
            "actions": [],
            "warnings": ["fstab: device /dev/sda3 not found"],
        }
        result = orch.post_migration_analysis(
            features,
            success=True,
            fixer_report=fixer_report,
        )
        health = result["health"]
        assert health.overall_status == HealthStatus.WARN

        orch.shutdown()

    def test_health_fail_when_grub_missing(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features()
        orch.pre_migration_analysis(features)
        fixer_report = {
            "analysis": {"boot_mode": "bios", "grub_installed": False},
            "actions": [],
            "warnings": [],
        }
        result = orch.post_migration_analysis(
            features,
            success=True,
            fixer_report=fixer_report,
        )
        health = result["health"]
        assert health.overall_status == HealthStatus.FAIL

        orch.shutdown()


# ---------------------------------------------------------------------------
# AI disabled -- migration still works
# ---------------------------------------------------------------------------


class TestAIDisabled:
    def test_disabled_ai_does_not_crash(self, tmp_path):
        orch = AIOrchestrator()
        result = orch.initialize(_cfg(tmp_path, enabled=False))
        assert result is False
        assert orch.is_initialized is False

        features = _features()

        # All methods should return None harmlessly
        assert orch.pre_migration_analysis(features) is None
        assert orch.post_migration_analysis(features, success=True) is None
        assert orch.diagnose_error("some error") is None

        info = orch.get_info()
        assert info is not None
        assert info["initialized"] is False
        assert info["enabled"] is False

        orch.shutdown()  # no crash


# ---------------------------------------------------------------------------
# Risk detection in integration context
# ---------------------------------------------------------------------------


class TestRiskDetectionIntegration:
    def test_uefi_risk_detected(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features(has_uefi=True, boot_mode="uefi")
        result = orch.pre_migration_analysis(features)
        pred = result["prediction"]
        rules = [r.rule for r in pred.risks]
        assert "uefi_boot" in rules

        orch.shutdown()

    def test_snapshot_risk_detected(self, tmp_path):
        orch = AIOrchestrator()
        orch.initialize(_cfg(tmp_path))

        features = _features(has_snapshots=True, snapshot_count=5)
        result = orch.pre_migration_analysis(features)
        pred = result["prediction"]
        rules = [r.rule for r in pred.risks]
        assert "active_snapshots" in rules
        assert "many_snapshots" in rules

        orch.shutdown()
