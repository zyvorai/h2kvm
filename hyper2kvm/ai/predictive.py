# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/predictive.py
"""
Predictive engine for migration success probability and duration estimation.

Combines rule-based risk detection with similarity-weighted history to
generate predictions before a migration begins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._stats import clamp, weighted_mean
from .models import (
    AIConfig,
    MigrationFeatures,
    Prediction,
    RiskFinding,
    RiskLevel,
)

if TYPE_CHECKING:
    from .knowledge_base import KnowledgeBase

# ---------------------------------------------------------------------------
# Risk rules -- each is a callable(features) -> RiskFinding | None
# ---------------------------------------------------------------------------

RiskRule = dict[str, Any]

RISK_RULES: list[RiskRule] = [
    {
        "id": "buslogic_controller",
        "check": lambda f: f.controller_type == "buslogic",
        "level": RiskLevel.CRITICAL,
        "message": "BusLogic controller has no KVM driver -- VM may not boot",
        "mitigation": "Change controller to LSI Logic or enable auto-fix",
    },
    {
        "id": "active_snapshots",
        "check": lambda f: f.has_snapshots,
        "level": RiskLevel.HIGH,
        "message": "Active snapshots detected -- flatten before migration",
        "mitigation": "Consolidate snapshots in VMware or use --flatten",
    },
    {
        "id": "many_snapshots",
        "check": lambda f: f.snapshot_count > 3,
        "level": RiskLevel.HIGH,
        "message": "Deep snapshot chain may cause issues",
        "mitigation": "Consolidate snapshots before migration",
    },
    {
        "id": "luks_encrypted",
        "check": lambda f: f.has_luks,
        "level": RiskLevel.MEDIUM,
        "message": "LUKS encrypted volumes require key material during migration",
        "mitigation": "Provide --luks-passphrase or --luks-keyfile",
    },
    {
        "id": "uefi_boot",
        "check": lambda f: f.has_uefi,
        "level": RiskLevel.MEDIUM,
        "message": "UEFI boot mode requires OVMF firmware on target host",
        "mitigation": "Ensure OVMF is installed and use --uefi flag",
    },
    {
        "id": "large_disk",
        "check": lambda f: f.disk_size_gb > 500,
        "level": RiskLevel.MEDIUM,
        "message": "Large disk (>500 GB) -- conversion may be slow",
        "mitigation": "Ensure sufficient free space and use fast storage",
    },
    {
        "id": "multi_disk",
        "check": lambda f: f.disk_count > 4,
        "level": RiskLevel.LOW,
        "message": "Multiple disks detected -- verify all are included",
        "mitigation": "Use --parallel-processing for faster conversion",
    },
    {
        "id": "no_fstab",
        "check": lambda f: f.fstab_entries == 0,
        "level": RiskLevel.LOW,
        "message": "No fstab entries detected -- guest analysis may be incomplete",
        "mitigation": "Verify guest OS was fully analysed",
    },
    {
        "id": "windows_os",
        "check": lambda f: f.os_family == "windows",
        "level": RiskLevel.MEDIUM,
        "message": "Windows guest requires virtio driver injection",
        "mitigation": "Provide --virtio-drivers-dir with signed drivers",
    },
]


class PredictiveEngine:  # pylint: disable=too-few-public-methods
    # Single-entrypoint "engine" object (predict()); no natural second
    # public method to add.
    """Generate pre-migration predictions."""

    def __init__(self, kb: KnowledgeBase, config: AIConfig | None = None) -> None:
        self._kb = kb
        self._min_history = config.min_history_for_prediction if config else 3
        self._max_lookback = config.max_similar_lookback if config else 100

    def predict(self, features: MigrationFeatures) -> Prediction:
        """Return a :class:`Prediction` for the given migration features."""
        # --- risk rules ---
        risks: list[RiskFinding] = []
        for rule in RISK_RULES:
            try:
                if rule["check"](features):
                    risks.append(
                        RiskFinding(
                            rule=rule["id"],
                            level=rule["level"],
                            message=rule["message"],
                            mitigation=rule["mitigation"],
                        )
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                # RISK_RULES "check" callables are arbitrary lambdas; one
                # bad rule must not abort prediction for the whole guest.
                pass

        # --- similarity-weighted success probability ---
        similar = self._kb.get_similar_migrations(
            features,
            top_k=self._max_lookback,
            max_lookback=self._max_lookback,
        )
        similar_count = len(similar)

        if similar_count >= self._min_history:
            success_values = [float(rec.success) for rec, _ in similar]
            sim_weights = [sim for _, sim in similar]
            success_prob = weighted_mean(success_values, sim_weights)
            confidence = "high" if similar_count >= 10 else "medium"
        else:
            # Not enough history -- use rule-based penalty
            success_prob = 1.0
            confidence = "low"

        # Apply risk penalties
        for risk in risks:
            if risk.level == RiskLevel.CRITICAL:
                success_prob *= 0.5
            elif risk.level == RiskLevel.HIGH:
                success_prob *= 0.8
            elif risk.level == RiskLevel.MEDIUM:
                success_prob *= 0.95

        success_prob = clamp(success_prob)

        # --- duration estimation ---
        duration = self._estimate_duration(features, similar)

        return Prediction(
            success_probability=round(success_prob, 3),
            estimated_duration_seconds=round(duration, 1),
            risks=risks,
            similar_count=similar_count,
            confidence=confidence,
        )

    # ------------------------------------------------------------------

    def _estimate_duration(
        self,
        features: MigrationFeatures,
        similar: list[tuple[Any, float]],
    ) -> float:
        """Estimate migration duration from history or disk size heuristic."""
        if similar:
            durations = [
                rec.duration_seconds for rec, _ in similar if rec.success and rec.duration_seconds > 0
            ]
            weights = [sim for rec, sim in similar if rec.success and rec.duration_seconds > 0]
            if durations:
                return weighted_mean(durations, weights)

        # Fallback: ~60 s/GB for conversion + 30 s fixed overhead
        return max(30.0, features.disk_size_gb * 60.0 + 30.0)
