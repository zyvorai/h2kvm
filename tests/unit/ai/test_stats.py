# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.ai._stats module.

Pure-Python statistics primitives used by the AI migration-intelligence module.
"""

from __future__ import annotations

import math

import pytest

from h2kvm.ai._stats import (
    clamp,
    cosine_similarity,
    linear_regression,
    mean,
    percentile,
    std,
    variance,
    weighted_mean,
    z_score,
)


# ---------------------------------------------------------------------------
# mean
# ---------------------------------------------------------------------------


def test_mean_empty():
    assert mean([]) == 0.0


def test_mean_single():
    assert mean([7.0]) == 7.0


def test_mean_known():
    assert mean([1.0, 2.0, 3.0, 4.0, 5.0]) == 3.0


def test_mean_negative_values():
    assert mean([-2.0, 0.0, 2.0]) == 0.0


# ---------------------------------------------------------------------------
# variance
# ---------------------------------------------------------------------------


def test_variance_empty():
    assert variance([]) == 0.0


def test_variance_single_ddof1():
    # With ddof=1 a single value yields 0.0 (n < ddof + 1).
    assert variance([5.0]) == 0.0


def test_variance_known_ddof1():
    # values: [2, 4, 4, 4, 5, 5, 7, 9]  mean=5
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    expected = sum((x - 5.0) ** 2 for x in vals) / (len(vals) - 1)
    assert variance(vals) == pytest.approx(expected)


def test_variance_population():
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    expected = sum((x - 5.0) ** 2 for x in vals) / len(vals)
    assert variance(vals, ddof=0) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# std
# ---------------------------------------------------------------------------


def test_std_empty():
    assert std([]) == 0.0


def test_std_known():
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    expected = math.sqrt(variance(vals))
    assert std(vals) == pytest.approx(expected)


def test_std_constant_values():
    # All values the same -> std should be 0.
    assert std([3.0, 3.0, 3.0, 3.0], ddof=0) == 0.0


# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------


def test_percentile_empty():
    assert percentile([], 50) == 0.0


def test_percentile_single():
    assert percentile([42.0], 50) == 42.0


def test_percentile_median_odd():
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0


def test_percentile_0_and_100():
    vals = [10.0, 20.0, 30.0]
    assert percentile(vals, 0) == 10.0
    assert percentile(vals, 100) == 30.0


def test_percentile_interpolation():
    # 25th percentile of [1,2,3,4]: k = 0.25*3 = 0.75
    # lerp(1, 2, 0.75) = 1*0.25 + 2*0.75 = 1.75
    assert percentile([1.0, 2.0, 3.0, 4.0], 25) == pytest.approx(1.75)


# ---------------------------------------------------------------------------
# z_score
# ---------------------------------------------------------------------------


def test_z_score_known():
    vals = [10.0, 20.0, 30.0]
    m = mean(vals)  # 20
    s = std(vals)
    assert z_score(30.0, vals) == pytest.approx((30.0 - m) / s)


def test_z_score_zero_std():
    assert z_score(5.0, [5.0, 5.0, 5.0]) == 0.0


def test_z_score_empty():
    assert z_score(1.0, []) == 0.0


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------


def test_cosine_identical_vectors():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite_vectors():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_length_mismatch():
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_cosine_empty():
    assert cosine_similarity([], []) == 0.0


def test_cosine_zero_magnitude():
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


# ---------------------------------------------------------------------------
# linear_regression
# ---------------------------------------------------------------------------


def test_linear_regression_perfect_line():
    # y = 2x + 1
    x = [1.0, 2.0, 3.0, 4.0]
    y = [3.0, 5.0, 7.0, 9.0]
    slope, intercept = linear_regression(x, y)
    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(1.0)


def test_linear_regression_single_point():
    slope, intercept = linear_regression([1.0], [5.0])
    assert slope == 0.0
    assert intercept == 5.0


def test_linear_regression_empty():
    slope, intercept = linear_regression([], [])
    assert slope == 0.0
    assert intercept == 0.0


def test_linear_regression_constant_x():
    # All x values the same -> ss_xx = 0 -> slope = 0, intercept = mean(y)
    slope, intercept = linear_regression([3.0, 3.0, 3.0], [1.0, 2.0, 3.0])
    assert slope == 0.0
    assert intercept == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# weighted_mean
# ---------------------------------------------------------------------------


def test_weighted_mean_basic():
    assert weighted_mean([1.0, 2.0, 3.0], [1.0, 1.0, 1.0]) == pytest.approx(2.0)


def test_weighted_mean_unequal_weights():
    # (10*3 + 20*1) / (3+1) = 50/4 = 12.5
    assert weighted_mean([10.0, 20.0], [3.0, 1.0]) == pytest.approx(12.5)


def test_weighted_mean_length_mismatch():
    # Falls back to unweighted mean.
    assert weighted_mean([2.0, 4.0, 6.0], [1.0]) == pytest.approx(4.0)


def test_weighted_mean_empty():
    assert weighted_mean([], []) == 0.0


def test_weighted_mean_zero_weights():
    # All weights are zero -> falls back to unweighted mean.
    assert weighted_mean([10.0, 20.0], [0.0, 0.0]) == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# clamp
# ---------------------------------------------------------------------------


def test_clamp_within_range():
    assert clamp(0.5) == 0.5


def test_clamp_below():
    assert clamp(-0.5) == 0.0


def test_clamp_above():
    assert clamp(1.5) == 1.0


def test_clamp_custom_bounds():
    assert clamp(15.0, lo=10.0, hi=20.0) == 15.0
    assert clamp(5.0, lo=10.0, hi=20.0) == 10.0
    assert clamp(25.0, lo=10.0, hi=20.0) == 20.0
