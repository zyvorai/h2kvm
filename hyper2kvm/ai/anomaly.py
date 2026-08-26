# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/anomaly.py
"""
Anomaly detection for migrations.

Uses z-score analysis on duration, error rate, and phase sequences to
flag migrations that deviate significantly from historical norms.
"""

from __future__ import annotations

from ._stats import (
    mean,
    z_score as calc_z,
)
from .models import AIConfig, AnomalyResult, MigrationRecord


class AnomalyDetector:
    """Detect anomalies in migration metrics."""

    def __init__(self, config: AIConfig | None = None) -> None:
        self._threshold = config.anomaly_z_threshold if config else 2.5

    def detect_duration_anomaly(
        self,
        duration: float,
        history: list[MigrationRecord],
    ) -> AnomalyResult:
        """Flag if *duration* is unusually long or short."""
        durations = [r.duration_seconds for r in history if r.success]
        if len(durations) < 3:
            return AnomalyResult()
        z = calc_z(duration, durations)
        if abs(z) > self._threshold:
            direction = "longer" if z > 0 else "shorter"
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type="duration",
                z_score=z,
                expected_value=mean(durations),
                actual_value=duration,
                message=f"Migration duration is significantly {direction} than historical average "
                f"(z={z:.2f}, threshold={self._threshold})",
            )
        return AnomalyResult(
            z_score=z,
            expected_value=mean(durations),
            actual_value=duration,
        )

    def detect_error_rate_anomaly(
        self,
        error_count: int,
        history: list[MigrationRecord],
    ) -> AnomalyResult:
        """Flag if the error count is unusually high."""
        error_counts = [float(len(r.errors)) for r in history]
        if len(error_counts) < 3:
            return AnomalyResult()
        z = calc_z(float(error_count), error_counts)
        if z > self._threshold:
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type="error_rate",
                z_score=z,
                expected_value=mean(error_counts),
                actual_value=float(error_count),
                message=f"Error count ({error_count}) is anomalously high "
                f"(z={z:.2f}, threshold={self._threshold})",
            )
        return AnomalyResult(
            z_score=z,
            expected_value=mean(error_counts),
            actual_value=float(error_count),
        )

    def detect_phase_anomaly(
        self,
        phases: list[str],
        history: list[MigrationRecord],
    ) -> AnomalyResult:
        """Flag if the set of phases differs markedly from the norm."""
        if not history or not phases:
            return AnomalyResult()
        # Build a "typical" phase set from successful migrations
        phase_counts: dict[str, int] = {}
        total = 0
        for rec in history:
            if rec.success:
                for p in rec.phases:
                    phase_counts[p] = phase_counts.get(p, 0) + 1
                total += 1
        if total == 0:
            return AnomalyResult()

        # Any phase present in <20% of history but appearing now is unusual
        unusual: list[str] = []
        for p in phases:
            freq = phase_counts.get(p, 0) / total
            if freq < 0.2:
                unusual.append(p)

        # Any phase present in >80% of history but missing now is unusual
        missing: list[str] = []
        for p, cnt in phase_counts.items():
            if cnt / total > 0.8 and p not in phases:
                missing.append(p)

        if unusual or missing:
            parts: list[str] = []
            if unusual:
                parts.append(f"unexpected phases: {unusual}")
            if missing:
                parts.append(f"missing phases: {missing}")
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type="phase_sequence",
                message=f"Phase sequence anomaly: {'; '.join(parts)}",
            )

        return AnomalyResult()

    def detect_all(
        self,
        duration: float,
        error_count: int,
        phases: list[str],
        history: list[MigrationRecord],
    ) -> list[AnomalyResult]:
        """Run all detectors and return any anomalies found."""
        results: list[AnomalyResult] = []
        for result in (
            self.detect_duration_anomaly(duration, history),
            self.detect_error_rate_anomaly(error_count, history),
            self.detect_phase_anomaly(phases, history),
        ):
            if result.is_anomaly:
                results.append(result)
        return results
