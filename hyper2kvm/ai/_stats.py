# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/_stats.py
"""
Pure-Python statistics primitives for the AI module.

No external dependencies -- uses only stdlib math.
"""

from __future__ import annotations

import math


def mean(values: list[float]) -> float:
    """Arithmetic mean of *values*. Returns 0.0 for empty lists."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values: list[float], ddof: int = 1) -> float:
    """Sample variance (ddof=1) or population variance (ddof=0)."""
    n = len(values)
    if n < ddof + 1:
        return 0.0
    m = mean(values)
    return sum((x - m) ** 2 for x in values) / (n - ddof)


def std(values: list[float], ddof: int = 1) -> float:
    """Standard deviation."""
    return math.sqrt(variance(values, ddof))


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (0-100 scale).

    Returns 0.0 for empty lists.
    """
    if not values:
        return 0.0
    s = sorted(values)
    k = (pct / 100.0) * (len(s) - 1)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[lo]
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def z_score(value: float, values: list[float]) -> float:
    """Z-score of *value* relative to *values*.

    Returns 0.0 when the standard deviation is zero.
    """
    s = std(values)
    if s == 0.0:
        return 0.0
    return (value - mean(values)) / s


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors.

    Returns 0.0 when either vector has zero magnitude.
    """
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def linear_regression(x: list[float], y: list[float]) -> tuple[float, float]:
    """Simple linear regression.  Returns (slope, intercept).

    If *x* and *y* have different lengths or fewer than 2 points,
    returns (0.0, mean(y)).
    """
    n = min(len(x), len(y))
    if n < 2:
        return 0.0, mean(y)
    mx = mean(x[:n])
    my = mean(y[:n])
    ss_xy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    ss_xx = sum((x[i] - mx) ** 2 for i in range(n))
    if ss_xx == 0.0:
        return 0.0, my
    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    return slope, intercept


def weighted_mean(values: list[float], weights: list[float]) -> float:
    """Weighted average. Falls back to ``mean(values)`` on length mismatch."""
    if not values:
        return 0.0
    if len(values) != len(weights):
        return mean(values)
    total_w = sum(weights)
    if total_w == 0.0:
        return mean(values)
    return sum(v * w for v, w in zip(values, weights)) / total_w


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))
