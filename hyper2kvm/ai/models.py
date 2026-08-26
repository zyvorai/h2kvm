# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/models.py
"""
Dataclass models for the AI migration-intelligence module.

All models are plain dataclasses -- no external dependencies.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class RiskLevel(str, Enum):
    """Severity level for a detected migration risk or remediation action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkloadType(str, Enum):
    """Classified workload role for a migrated VM."""

    DATABASE = "database"
    WEBSERVER = "webserver"
    APPSERVER = "appserver"
    MAILSERVER = "mailserver"
    CONTAINER_HOST = "container_host"
    DNS = "dns"
    MONITORING = "monitoring"
    GENERIC = "generic"


class HealthStatus(str, Enum):
    """Outcome of a single post-migration health check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
@dataclass
class MigrationFeatures:  # pylint: disable=too-many-instance-attributes  # full feature vector covering disk, OS, boot, and package/service signals
    """Feature vector extracted from VMDK inspection + guest detection."""

    source_format: str = "vmdk"
    disk_size_gb: float = 0.0
    disk_count: int = 1
    os_family: str = "linux"
    os_name: str = ""
    os_version: str = ""
    has_lvm: bool = False
    has_luks: bool = False
    has_uefi: bool = False
    controller_type: str = "lsilogic"
    has_snapshots: bool = False
    snapshot_count: int = 0
    packages: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    boot_mode: str = "bios"
    fstab_entries: int = 0
    initramfs_drivers: list[str] = field(default_factory=list)

    def to_vector(self) -> list[float]:
        """Produce a numeric feature vector for similarity search."""
        fmt_map = {"vmdk": 0.0, "vhd": 1.0, "vhdx": 2.0, "ova": 3.0, "raw": 4.0, "qcow2": 5.0}
        os_map = {"linux": 0.0, "windows": 1.0, "freebsd": 2.0}
        ctrl_map = {"lsilogic": 0.0, "buslogic": 1.0, "pvscsi": 2.0, "ide": 3.0, "sata": 4.0}
        return [
            fmt_map.get(self.source_format, 6.0),
            self.disk_size_gb,
            float(self.disk_count),
            os_map.get(self.os_family, 3.0),
            float(self.has_lvm),
            float(self.has_luks),
            float(self.has_uefi),
            ctrl_map.get(self.controller_type, 5.0),
            float(self.has_snapshots),
            float(self.snapshot_count),
            float(self.fstab_entries),
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        return {
            "source_format": self.source_format,
            "disk_size_gb": self.disk_size_gb,
            "disk_count": self.disk_count,
            "os_family": self.os_family,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "has_lvm": self.has_lvm,
            "has_luks": self.has_luks,
            "has_uefi": self.has_uefi,
            "controller_type": self.controller_type,
            "has_snapshots": self.has_snapshots,
            "snapshot_count": self.snapshot_count,
            "packages": self.packages,
            "services": self.services,
            "boot_mode": self.boot_mode,
            "fstab_entries": self.fstab_entries,
            "initramfs_drivers": self.initramfs_drivers,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MigrationFeatures:
        """Reconstruct from a dict (e.g. JSON from the knowledge base)."""
        return cls(
            source_format=d.get("source_format", "vmdk"),
            disk_size_gb=d.get("disk_size_gb", 0.0),
            disk_count=d.get("disk_count", 1),
            os_family=d.get("os_family", "linux"),
            os_name=d.get("os_name", ""),
            os_version=d.get("os_version", ""),
            has_lvm=d.get("has_lvm", False),
            has_luks=d.get("has_luks", False),
            has_uefi=d.get("has_uefi", False),
            controller_type=d.get("controller_type", "lsilogic"),
            has_snapshots=d.get("has_snapshots", False),
            snapshot_count=d.get("snapshot_count", 0),
            packages=d.get("packages", []),
            services=d.get("services", []),
            boot_mode=d.get("boot_mode", "bios"),
            fstab_entries=d.get("fstab_entries", 0),
            initramfs_drivers=d.get("initramfs_drivers", []),
        )


# ---------------------------------------------------------------------------
# Migration record (stored in knowledge base)
# ---------------------------------------------------------------------------
@dataclass
class MigrationRecord:  # pylint: disable=too-many-instance-attributes  # full audit record of one migration run for the knowledge base
    """Immutable record of a completed migration stored in the knowledge base."""

    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    features: MigrationFeatures = field(default_factory=MigrationFeatures)
    success: bool = True
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    fixer_actions: list[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
@dataclass
class RiskFinding:
    """A single risk detected during pre-migration analysis."""

    rule: str = ""
    level: RiskLevel = RiskLevel.LOW
    message: str = ""
    mitigation: str = ""


@dataclass
class Prediction:
    """AI prediction for a planned migration."""

    success_probability: float = 1.0
    estimated_duration_seconds: float = 0.0
    risks: list[RiskFinding] = field(default_factory=list)
    similar_count: int = 0
    confidence: str = "low"  # low | medium | high

    @property
    def highest_risk(self) -> RiskLevel:
        """Return the highest RiskLevel among self.risks (LOW if none)."""
        if not self.risks:
            return RiskLevel.LOW
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return max(self.risks, key=lambda r: order.get(r.level, 0)).level


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------
@dataclass
class Diagnosis:
    """Root-cause analysis for a migration error."""

    pattern_id: str = ""
    error_text: str = ""
    root_cause: str = ""
    confidence: float = 0.0
    suggestions: list[str] = field(default_factory=list)
    similar_errors: int = 0
    learned: bool = False  # True if from knowledge base rather than built-in


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------
@dataclass
class Remediation:
    """A single remediation action."""

    fix_id: str = ""
    description: str = ""
    command: str = ""
    risk: RiskLevel = RiskLevel.LOW
    auto_applicable: bool = False
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class RemediationPlan:
    """An ordered list of remediation actions for a diagnosed issue."""

    diagnosis: Diagnosis = field(default_factory=Diagnosis)
    fixes: list[Remediation] = field(default_factory=list)
    estimated_success_rate: float = 0.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@dataclass
class HealthCheck:
    """Result of a single post-migration health check."""

    name: str = ""
    status: HealthStatus = HealthStatus.SKIP
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """Aggregated post-migration health report."""

    checks: list[HealthCheck] = field(default_factory=list)
    overall_status: HealthStatus = HealthStatus.SKIP
    timestamp: float = field(default_factory=time.time)

    def passed(self) -> bool:
        """Return True if the overall status is PASS or SKIP (i.e. not FAIL/WARN)."""
        return self.overall_status in (HealthStatus.PASS, HealthStatus.SKIP)

    def summary(self) -> dict[str, int]:
        """Return a count of checks per HealthStatus value."""
        counts: dict[str, int] = {}
        for c in self.checks:
            counts[c.status.value] = counts.get(c.status.value, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Anomaly
# ---------------------------------------------------------------------------
@dataclass
class AnomalyResult:
    """Result of anomaly detection on a migration."""

    is_anomaly: bool = False
    anomaly_type: str = ""
    z_score: float = 0.0
    expected_value: float = 0.0
    actual_value: float = 0.0
    message: str = ""


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------
@dataclass
class WorkloadProfile:
    """Classified workload profile for a migrated VM."""

    workload_type: WorkloadType = WorkloadType.GENERIC
    confidence: float = 0.0
    matched_indicators: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AI Config
# ---------------------------------------------------------------------------
@dataclass
class AIConfig:  # pylint: disable=too-many-instance-attributes  # one field per config.yaml `ai:` setting
    """Configuration for the AI module, loaded from config.yaml ``ai:`` section."""

    enabled: bool = True
    knowledge_base_path: str = "~/.cache/hyper2kvm/ai/knowledge.db"
    min_history_for_prediction: int = 3
    anomaly_z_threshold: float = 2.5
    max_similar_lookback: int = 100
    auto_remediate: bool = False
    auto_remediate_risk_max: str = "low"
    telemetry_sampling_rate: float = 1.0
