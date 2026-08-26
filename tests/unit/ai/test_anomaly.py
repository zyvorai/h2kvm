# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.ai.anomaly.AnomalyDetector.

Covers duration, error-rate, and phase-sequence anomaly detection, the
detect_all() aggregation method, and custom threshold configuration.
"""

from __future__ import annotations

import pytest

from hyper2kvm.ai.anomaly import AnomalyDetector
from hyper2kvm.ai.models import AIConfig, MigrationFeatures, MigrationRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_records(
    n: int,
    duration: float = 100.0,
    errors: list[str] | None = None,
    phases: list[str] | None = None,
    success: bool = True,
    vary: bool = False,
) -> list[MigrationRecord]:
    """Build *n* history records.

    When *vary* is True, durations are spread around *duration* so that
    the standard deviation is non-zero (needed for z-score computation).
    """
    records: list[MigrationRecord] = []
    for i in range(n):
        d = duration + (i - n / 2) * 0.5 if vary else duration
        records.append(
            MigrationRecord(
                duration_seconds=d,
                errors=errors or [],
                phases=phases or ["inspect", "fix", "convert"],
                success=success,
            )
        )
    return records


# ---------------------------------------------------------------------------
# detect_duration_anomaly
# ---------------------------------------------------------------------------


class TestDetectDurationAnomaly:
    def test_insufficient_history_returns_non_anomaly(self):
        det = AnomalyDetector()
        history = _make_records(2, duration=100.0)
        result = det.detect_duration_anomaly(100.0, history)
        assert result.is_anomaly is False
        assert result.anomaly_type == ""

    def test_normal_duration_not_flagged(self):
        det = AnomalyDetector()
        history = _make_records(20, duration=100.0)
        result = det.detect_duration_anomaly(105.0, history)
        assert result.is_anomaly is False

    def test_anomalously_long_duration_flagged(self):
        det = AnomalyDetector()
        # vary=True gives non-zero std so z-score can be computed
        history = _make_records(20, duration=100.0, vary=True)
        result = det.detect_duration_anomaly(10000.0, history)
        assert result.is_anomaly is True
        assert result.anomaly_type == "duration"
        assert "longer" in result.message
        assert result.z_score > 0

    def test_anomalously_short_duration_flagged(self):
        det = AnomalyDetector()
        history = _make_records(20, duration=1000.0, vary=True)
        result = det.detect_duration_anomaly(0.001, history)
        assert result.is_anomaly is True
        assert "shorter" in result.message
        assert result.z_score < 0

    def test_expected_and_actual_values_populated(self):
        det = AnomalyDetector()
        history = _make_records(10, duration=100.0)
        result = det.detect_duration_anomaly(100.0, history)
        assert result.expected_value == pytest.approx(100.0)
        assert result.actual_value == pytest.approx(100.0)

    def test_failed_records_excluded_from_duration_history(self):
        det = AnomalyDetector()
        # Only 2 successful records (insufficient), the rest are failed
        history = _make_records(2, duration=100.0, success=True)
        history += _make_records(10, duration=100.0, success=False)
        result = det.detect_duration_anomaly(100.0, history)
        # Should treat as insufficient history since only 2 successful
        assert result.is_anomaly is False


# ---------------------------------------------------------------------------
# detect_error_rate_anomaly
# ---------------------------------------------------------------------------


class TestDetectErrorRateAnomaly:
    def test_insufficient_history(self):
        det = AnomalyDetector()
        history = _make_records(2)
        result = det.detect_error_rate_anomaly(5, history)
        assert result.is_anomaly is False

    def test_normal_error_count_not_flagged(self):
        det = AnomalyDetector()
        history = _make_records(20, errors=["err1"])
        result = det.detect_error_rate_anomaly(1, history)
        assert result.is_anomaly is False

    def test_anomalously_high_error_count_flagged(self):
        det = AnomalyDetector()
        # Build history with some having 0 errors, some having 1, to get
        # a non-zero std so z-score can be calculated
        history = []
        for i in range(20):
            errs = ["minor"] if i % 3 == 0 else []
            history.append(MigrationRecord(errors=errs))
        result = det.detect_error_rate_anomaly(50, history)
        assert result.is_anomaly is True
        assert result.anomaly_type == "error_rate"
        assert "50" in result.message
        assert result.z_score > 0

    def test_low_error_count_not_flagged_even_if_unusual(self):
        det = AnomalyDetector()
        # History has many errors; current has 0 (low side)
        history = _make_records(20, errors=["e1", "e2", "e3"])
        result = det.detect_error_rate_anomaly(0, history)
        # z_score will be negative, and error_rate only flags z > threshold
        assert result.is_anomaly is False


# ---------------------------------------------------------------------------
# detect_phase_anomaly
# ---------------------------------------------------------------------------


class TestDetectPhaseAnomaly:
    def test_empty_phases_returns_non_anomaly(self):
        det = AnomalyDetector()
        history = _make_records(10)
        result = det.detect_phase_anomaly([], history)
        assert result.is_anomaly is False

    def test_empty_history_returns_non_anomaly(self):
        det = AnomalyDetector()
        result = det.detect_phase_anomaly(["inspect", "convert"], [])
        assert result.is_anomaly is False

    def test_normal_phases_not_flagged(self):
        det = AnomalyDetector()
        history = _make_records(10, phases=["inspect", "fix", "convert"])
        result = det.detect_phase_anomaly(["inspect", "fix", "convert"], history)
        assert result.is_anomaly is False

    def test_unusual_phase_present(self):
        det = AnomalyDetector()
        # History only has ["inspect", "fix", "convert"]
        history = _make_records(10, phases=["inspect", "fix", "convert"])
        # Current migration has an extra unusual phase
        result = det.detect_phase_anomaly(
            ["inspect", "fix", "convert", "rollback_recovery"],
            history,
        )
        assert result.is_anomaly is True
        assert result.anomaly_type == "phase_sequence"
        assert "unexpected" in result.message.lower() or "unusual" in result.message.lower()

    def test_missing_common_phase(self):
        det = AnomalyDetector()
        # History always has ["inspect", "fix", "convert"]
        history = _make_records(10, phases=["inspect", "fix", "convert"])
        # Current migration is missing "convert"
        result = det.detect_phase_anomaly(["inspect", "fix"], history)
        assert result.is_anomaly is True
        assert "missing" in result.message.lower()

    def test_only_failed_history_returns_non_anomaly(self):
        det = AnomalyDetector()
        # All history records are failed -- no successful baseline
        history = _make_records(10, phases=["inspect", "fix"], success=False)
        result = det.detect_phase_anomaly(["inspect", "fix", "convert"], history)
        # No successful records means total==0, should return non-anomaly
        assert result.is_anomaly is False


# ---------------------------------------------------------------------------
# detect_all
# ---------------------------------------------------------------------------


class TestDetectAll:
    def test_returns_only_anomalies(self):
        det = AnomalyDetector()
        history = _make_records(20, duration=100.0, phases=["inspect", "fix", "convert"])
        results = det.detect_all(
            duration=100.0,
            error_count=0,
            phases=["inspect", "fix", "convert"],
            history=history,
        )
        # Nothing anomalous
        assert results == []

    def test_returns_multiple_anomalies(self):
        det = AnomalyDetector()
        # Build history with small variance in both duration and error count
        history = []
        for i in range(20):
            errs = ["minor"] if i % 3 == 0 else []
            history.append(
                MigrationRecord(
                    duration_seconds=100.0 + (i - 10) * 0.5,
                    errors=errs,
                    phases=["inspect", "fix", "convert"],
                    success=True,
                )
            )
        results = det.detect_all(
            duration=10000.0,  # anomalous duration
            error_count=50,  # anomalous error count
            phases=["inspect", "fix", "convert", "emergency_rollback"],  # anomalous phase
            history=history,
        )
        types = {r.anomaly_type for r in results}
        assert "duration" in types
        assert "error_rate" in types
        assert "phase_sequence" in types

    def test_returns_list_type(self):
        det = AnomalyDetector()
        history = _make_records(5)
        results = det.detect_all(100.0, 0, ["inspect"], history)
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Custom threshold via AIConfig
# ---------------------------------------------------------------------------


class TestCustomThreshold:
    def test_low_threshold_flags_more(self):
        config = AIConfig(anomaly_z_threshold=0.1)
        det = AnomalyDetector(config=config)
        history = _make_records(20, duration=100.0, vary=True)
        # Slightly different duration should be flagged with very low threshold
        result = det.detect_duration_anomaly(110.0, history)
        assert result.is_anomaly is True

    def test_high_threshold_flags_less(self):
        config = AIConfig(anomaly_z_threshold=100.0)
        det = AnomalyDetector(config=config)
        history = _make_records(20, duration=100.0, vary=True)
        # With a threshold of 100, a moderately different duration should pass
        # The std is small (~3), so 110 gives z~3.4 which is under 100
        result = det.detect_duration_anomaly(110.0, history)
        assert result.is_anomaly is False

    def test_default_threshold_is_2_5(self):
        det = AnomalyDetector()
        assert det._threshold == pytest.approx(2.5)

    def test_config_threshold_applied(self):
        config = AIConfig(anomaly_z_threshold=3.0)
        det = AnomalyDetector(config=config)
        assert det._threshold == pytest.approx(3.0)
