# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.ai.models module.

Dataclass models and enumerations used by the AI migration-intelligence module.
"""

from __future__ import annotations

from h2kvm.ai.models import (
    AIConfig,
    AnomalyResult,
    Diagnosis,
    HealthCheck,
    HealthReport,
    HealthStatus,
    MigrationFeatures,
    MigrationRecord,
    Prediction,
    Remediation,
    RemediationPlan,
    RiskFinding,
    RiskLevel,
    WorkloadProfile,
    WorkloadType,
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


def test_risk_level_values():
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"
    assert RiskLevel.CRITICAL.value == "critical"


def test_risk_level_is_str():
    assert isinstance(RiskLevel.LOW, str)
    assert RiskLevel.LOW == "low"


def test_workload_type_values():
    expected = {
        "database",
        "webserver",
        "appserver",
        "mailserver",
        "container_host",
        "dns",
        "monitoring",
        "generic",
    }
    assert {wt.value for wt in WorkloadType} == expected


def test_health_status_values():
    assert HealthStatus.PASS.value == "pass"
    assert HealthStatus.WARN.value == "warn"
    assert HealthStatus.FAIL.value == "fail"
    assert HealthStatus.SKIP.value == "skip"


# ---------------------------------------------------------------------------
# MigrationFeatures
# ---------------------------------------------------------------------------


def test_migration_features_defaults():
    f = MigrationFeatures()
    assert f.source_format == "vmdk"
    assert f.disk_size_gb == 0.0
    assert f.disk_count == 1
    assert f.os_family == "linux"
    assert f.has_lvm is False
    assert f.packages == []


def test_migration_features_to_vector_length():
    f = MigrationFeatures()
    vec = f.to_vector()
    assert isinstance(vec, list)
    assert len(vec) == 11


def test_migration_features_to_vector_values():
    f = MigrationFeatures(
        source_format="vmdk",
        disk_size_gb=50.0,
        disk_count=2,
        os_family="linux",
        has_lvm=True,
        has_luks=False,
        has_uefi=True,
        controller_type="pvscsi",
        has_snapshots=True,
        snapshot_count=3,
        fstab_entries=5,
    )
    vec = f.to_vector()
    assert vec[0] == 0.0  # vmdk
    assert vec[1] == 50.0  # disk_size_gb
    assert vec[2] == 2.0  # disk_count
    assert vec[3] == 0.0  # linux
    assert vec[4] == 1.0  # has_lvm True
    assert vec[5] == 0.0  # has_luks False
    assert vec[6] == 1.0  # has_uefi True
    assert vec[7] == 2.0  # pvscsi
    assert vec[8] == 1.0  # has_snapshots True
    assert vec[9] == 3.0  # snapshot_count
    assert vec[10] == 5.0  # fstab_entries


def test_migration_features_to_dict_from_dict_roundtrip():
    original = MigrationFeatures(
        source_format="vhdx",
        disk_size_gb=120.5,
        disk_count=3,
        os_family="windows",
        os_name="Windows Server 2019",
        os_version="10.0",
        has_lvm=True,
        has_luks=True,
        has_uefi=True,
        controller_type="sata",
        has_snapshots=True,
        snapshot_count=2,
        packages=["httpd", "vim"],
        services=["sshd", "nginx"],
        boot_mode="uefi",
        fstab_entries=4,
        initramfs_drivers=["virtio_blk"],
    )
    d = original.to_dict()
    restored = MigrationFeatures.from_dict(d)
    assert restored.source_format == original.source_format
    assert restored.disk_size_gb == original.disk_size_gb
    assert restored.os_family == original.os_family
    assert restored.packages == original.packages
    assert restored.services == original.services
    assert restored.initramfs_drivers == original.initramfs_drivers


def test_migration_features_from_dict_defaults():
    restored = MigrationFeatures.from_dict({})
    assert restored.source_format == "vmdk"
    assert restored.disk_count == 1
    assert restored.os_family == "linux"


def test_migration_features_unknown_format_in_vector():
    f = MigrationFeatures(source_format="unknown")
    vec = f.to_vector()
    assert vec[0] == 6.0  # fallback for unknown format


# ---------------------------------------------------------------------------
# MigrationRecord
# ---------------------------------------------------------------------------


def test_migration_record_defaults():
    r = MigrationRecord()
    assert len(r.record_id) == 12
    assert r.success is True
    assert r.duration_seconds == 0.0
    assert r.errors == []
    assert r.phases == []
    assert r.fixer_actions == []
    assert r.notes == ""


def test_migration_record_custom_values():
    r = MigrationRecord(success=False, errors=["disk error"], notes="failed")
    assert r.success is False
    assert r.errors == ["disk error"]
    assert r.notes == "failed"


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def test_prediction_highest_risk_empty():
    p = Prediction()
    assert p.highest_risk == RiskLevel.LOW


def test_prediction_highest_risk_mixed():
    p = Prediction(
        risks=[
            RiskFinding(rule="r1", level=RiskLevel.LOW),
            RiskFinding(rule="r2", level=RiskLevel.CRITICAL),
            RiskFinding(rule="r3", level=RiskLevel.MEDIUM),
        ]
    )
    assert p.highest_risk == RiskLevel.CRITICAL


def test_prediction_highest_risk_single():
    p = Prediction(
        risks=[
            RiskFinding(rule="r1", level=RiskLevel.HIGH),
        ]
    )
    assert p.highest_risk == RiskLevel.HIGH


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


def test_diagnosis_defaults():
    d = Diagnosis()
    assert d.pattern_id == ""
    assert d.confidence == 0.0
    assert d.suggestions == []
    assert d.learned is False


def test_diagnosis_custom():
    d = Diagnosis(
        pattern_id="ERR001",
        error_text="disk not found",
        root_cause="missing virtio driver",
        confidence=0.85,
        suggestions=["install virtio-win"],
        learned=True,
    )
    assert d.pattern_id == "ERR001"
    assert d.confidence == 0.85
    assert d.learned is True


# ---------------------------------------------------------------------------
# Remediation / RemediationPlan
# ---------------------------------------------------------------------------


def test_remediation_defaults():
    r = Remediation()
    assert r.fix_id == ""
    assert r.risk == RiskLevel.LOW
    assert r.auto_applicable is False
    assert r.prerequisites == []


def test_remediation_plan_defaults():
    rp = RemediationPlan()
    assert isinstance(rp.diagnosis, Diagnosis)
    assert rp.fixes == []
    assert rp.estimated_success_rate == 0.0


# ---------------------------------------------------------------------------
# HealthCheck / HealthReport
# ---------------------------------------------------------------------------


def test_health_check_defaults():
    hc = HealthCheck()
    assert hc.name == ""
    assert hc.status == HealthStatus.SKIP
    assert hc.details == {}


def test_health_report_passed_pass():
    hr = HealthReport(overall_status=HealthStatus.PASS)
    assert hr.passed() is True


def test_health_report_passed_skip():
    hr = HealthReport(overall_status=HealthStatus.SKIP)
    assert hr.passed() is True


def test_health_report_not_passed_fail():
    hr = HealthReport(overall_status=HealthStatus.FAIL)
    assert hr.passed() is False


def test_health_report_not_passed_warn():
    hr = HealthReport(overall_status=HealthStatus.WARN)
    assert hr.passed() is False


def test_health_report_summary():
    hr = HealthReport(
        checks=[
            HealthCheck(name="boot", status=HealthStatus.PASS),
            HealthCheck(name="net", status=HealthStatus.PASS),
            HealthCheck(name="disk", status=HealthStatus.FAIL),
            HealthCheck(name="fstab", status=HealthStatus.WARN),
        ]
    )
    s = hr.summary()
    assert s == {"pass": 2, "fail": 1, "warn": 1}


def test_health_report_summary_empty():
    hr = HealthReport()
    assert hr.summary() == {}


# ---------------------------------------------------------------------------
# AnomalyResult
# ---------------------------------------------------------------------------


def test_anomaly_result_defaults():
    ar = AnomalyResult()
    assert ar.is_anomaly is False
    assert ar.anomaly_type == ""
    assert ar.z_score == 0.0


# ---------------------------------------------------------------------------
# WorkloadProfile
# ---------------------------------------------------------------------------


def test_workload_profile_defaults():
    wp = WorkloadProfile()
    assert wp.workload_type == WorkloadType.GENERIC
    assert wp.confidence == 0.0
    assert wp.matched_indicators == []
    assert wp.recommendations == []


# ---------------------------------------------------------------------------
# AIConfig
# ---------------------------------------------------------------------------


def test_ai_config_defaults():
    cfg = AIConfig()
    assert cfg.enabled is True
    assert cfg.knowledge_base_path == "~/.cache/h2kvm/ai/knowledge.db"
    assert cfg.min_history_for_prediction == 3
    assert cfg.anomaly_z_threshold == 2.5
    assert cfg.max_similar_lookback == 100
    assert cfg.auto_remediate is False
    assert cfg.auto_remediate_risk_max == "low"
    assert cfg.telemetry_sampling_rate == 1.0
