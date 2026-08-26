# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for hyper2kvm.ai.remediation.RemediationEngine."""

from __future__ import annotations

import pytest

from hyper2kvm.ai.models import AIConfig, Diagnosis, Remediation, RiskLevel
from hyper2kvm.ai.remediation import RemediationEngine, FIX_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_diagnosis(pattern_id: str, confidence: float = 0.8) -> Diagnosis:
    return Diagnosis(
        pattern_id=pattern_id,
        error_text="test error",
        root_cause="test root cause",
        confidence=confidence,
        suggestions=["suggestion"],
    )


# ---------------------------------------------------------------------------
# FIX_REGISTRY sanity
# ---------------------------------------------------------------------------


class TestFixRegistry:
    def test_fix_registry_has_entries(self):
        assert len(FIX_REGISTRY) > 0

    def test_fstab_uuid_mismatch_in_registry(self):
        assert "fstab_uuid_mismatch" in FIX_REGISTRY

    def test_grub_not_found_in_registry(self):
        assert "grub_not_found" in FIX_REGISTRY

    def test_initramfs_missing_drivers_in_registry(self):
        assert "initramfs_missing_drivers" in FIX_REGISTRY

    def test_buslogic_no_driver_in_registry(self):
        assert "buslogic_no_driver" in FIX_REGISTRY

    def test_vmware_tools_conflict_in_registry(self):
        assert "vmware_tools_conflict" in FIX_REGISTRY

    def test_registry_entries_have_required_keys(self):
        for pattern_id, fixes in FIX_REGISTRY.items():
            assert isinstance(fixes, list)
            for fix in fixes:
                assert "fix_id" in fix
                assert "description" in fix
                assert "command" in fix
                assert "risk" in fix


# ---------------------------------------------------------------------------
# plan() for known and unknown patterns
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_known_pattern_returns_fixes(self):
        engine = RemediationEngine()
        diag = _make_diagnosis("fstab_uuid_mismatch")
        plan = engine.plan(diag)
        assert len(plan.fixes) > 0
        assert plan.diagnosis.pattern_id == "fstab_uuid_mismatch"
        assert plan.estimated_success_rate > 0.0

    def test_plan_unknown_pattern_returns_empty_fixes(self):
        engine = RemediationEngine()
        diag = _make_diagnosis("totally_unknown_pattern")
        plan = engine.plan(diag)
        assert len(plan.fixes) == 0
        assert plan.estimated_success_rate == 0.0

    def test_plan_deduplicates_fixes_within_plan(self):
        engine = RemediationEngine()
        diag = _make_diagnosis("fstab_uuid_mismatch")
        plan = engine.plan(diag)
        fix_ids = [f.fix_id for f in plan.fixes]
        assert len(fix_ids) == len(set(fix_ids))

    def test_remediation_fields_populated(self):
        engine = RemediationEngine()
        diag = _make_diagnosis("fstab_uuid_mismatch")
        plan = engine.plan(diag)
        for fix in plan.fixes:
            assert fix.fix_id != ""
            assert fix.description != ""
            assert fix.command != ""
            assert isinstance(fix.risk, RiskLevel)
            assert isinstance(fix.auto_applicable, bool)
            assert isinstance(fix.prerequisites, list)

    def test_estimated_success_rate_from_confidence(self):
        engine = RemediationEngine()
        diag = _make_diagnosis("fstab_uuid_mismatch", confidence=0.9)
        plan = engine.plan(diag)
        # est_success = confidence * 0.9 = 0.9 * 0.9 = 0.81
        assert plan.estimated_success_rate == pytest.approx(0.81, abs=0.01)


# ---------------------------------------------------------------------------
# plan_all() deduplication across multiple diagnoses
# ---------------------------------------------------------------------------


class TestPlanAll:
    def test_plan_all_deduplicates_across_diagnoses(self):
        engine = RemediationEngine()
        diag1 = _make_diagnosis("fstab_uuid_mismatch")
        diag2 = _make_diagnosis("fstab_uuid_mismatch")
        plans = engine.plan_all([diag1, diag2])
        # Second plan should have no fixes since they are deduplicated
        # First plan has the fixes, second is dropped (empty)
        all_fix_ids = []
        for p in plans:
            all_fix_ids.extend(f.fix_id for f in p.fixes)
        assert len(all_fix_ids) == len(set(all_fix_ids))

    def test_plan_all_different_patterns(self):
        engine = RemediationEngine()
        diag1 = _make_diagnosis("fstab_uuid_mismatch")
        diag2 = _make_diagnosis("grub_not_found")
        plans = engine.plan_all([diag1, diag2])
        assert len(plans) >= 2
        all_fix_ids = []
        for p in plans:
            all_fix_ids.extend(f.fix_id for f in p.fixes)
        assert len(all_fix_ids) == len(set(all_fix_ids))

    def test_plan_all_drops_empty_plans(self):
        engine = RemediationEngine()
        diag1 = _make_diagnosis("fstab_uuid_mismatch")
        diag2 = _make_diagnosis("unknown_xyz")
        plans = engine.plan_all([diag1, diag2])
        # unknown_xyz produces no fixes, so its plan should be dropped
        for p in plans:
            assert len(p.fixes) > 0


# ---------------------------------------------------------------------------
# get_auto_fixes() and auto-remediation
# ---------------------------------------------------------------------------


class TestAutoRemediation:
    def test_get_auto_fixes_returns_nothing_when_disabled(self):
        config = AIConfig(auto_remediate=False)
        engine = RemediationEngine(config=config)
        diag = _make_diagnosis("fstab_uuid_mismatch")
        plan = engine.plan(diag)
        auto = engine.get_auto_fixes([plan])
        assert auto == []

    def test_get_auto_fixes_filters_by_risk_ceiling_low(self):
        config = AIConfig(auto_remediate=True, auto_remediate_risk_max="low")
        engine = RemediationEngine(config=config)
        diag = _make_diagnosis("fstab_uuid_mismatch")
        plan = engine.plan(diag)
        auto = engine.get_auto_fixes([plan])
        # All auto fixes should have risk <= LOW
        for fix in auto:
            assert fix.risk == RiskLevel.LOW

    def test_auto_remediation_with_medium_risk_max(self):
        config = AIConfig(auto_remediate=True, auto_remediate_risk_max="medium")
        engine = RemediationEngine(config=config)
        diag = _make_diagnosis("buslogic_no_driver")
        plan = engine.plan(diag)
        auto = engine.get_auto_fixes([plan])
        # buslogic_autofix is MEDIUM risk and auto_applicable
        for fix in auto:
            assert fix.risk in (RiskLevel.LOW, RiskLevel.MEDIUM)

    def test_auto_remediation_with_low_risk_excludes_medium(self):
        config = AIConfig(auto_remediate=True, auto_remediate_risk_max="low")
        engine = RemediationEngine(config=config)
        diag = _make_diagnosis("buslogic_no_driver")
        plan = engine.plan(diag)
        auto = engine.get_auto_fixes([plan])
        # buslogic_autofix is MEDIUM risk, should be excluded at LOW ceiling
        fix_ids = [f.fix_id for f in auto]
        assert "buslogic_autofix" not in fix_ids

    def test_get_auto_fixes_deduplicates(self):
        config = AIConfig(auto_remediate=True, auto_remediate_risk_max="low")
        engine = RemediationEngine(config=config)
        diag1 = _make_diagnosis("fstab_uuid_mismatch")
        diag2 = _make_diagnosis("fstab_uuid_mismatch")
        plan1 = engine.plan(diag1)
        plan2 = engine.plan(diag2)
        auto = engine.get_auto_fixes([plan1, plan2])
        fix_ids = [f.fix_id for f in auto]
        assert len(fix_ids) == len(set(fix_ids))
