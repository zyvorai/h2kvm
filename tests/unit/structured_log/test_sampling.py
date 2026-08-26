# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for configure_sampling and _sampling_processor."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hyper2kvm.core.structured_log import (
    DropEvent,
    _sampling_processor,
    configure_sampling,
)


def test_no_rules_passes_all():
    """Empty rules -> pass."""
    configure_sampling({})
    ed = {"event": "anything"}
    result = _sampling_processor(None, "info", ed)
    assert result["event"] == "anything"
    assert "_sampled" not in result


def test_drop_at_zero_probability():
    """{"debug_": 0.0} -> DropEvent for matching."""
    configure_sampling({"debug_": 0.0})
    with patch("random.random", return_value=0.5):
        with pytest.raises(DropEvent):
            _sampling_processor(None, "info", {"event": "debug_foo"})


def test_keep_at_full_probability():
    """{"debug_": 1.0} -> pass + _sampled=True."""
    configure_sampling({"debug_": 1.0})
    with patch("random.random", return_value=0.99):
        result = _sampling_processor(None, "info", {"event": "debug_bar"})
    assert result["_sampled"] is True


def test_non_matching_passes():
    """Non-matching prefix -> pass without _sampled."""
    configure_sampling({"debug_": 0.0})
    result = _sampling_processor(None, "info", {"event": "info_event"})
    assert result["event"] == "info_event"
    assert "_sampled" not in result


def test_audit_bypass():
    """_audit=True always passes."""
    configure_sampling({"debug_": 0.0})
    result = _sampling_processor(None, "info", {"event": "debug_x", "_audit": True})
    assert result["event"] == "debug_x"


def test_first_rule_wins():
    """Multiple matching prefixes -> first applied."""
    configure_sampling({"d": 1.0, "de": 0.0})
    with patch("random.random", return_value=0.5):
        # "d" matches first with keep_prob=1.0, so random(0.5) < 1.0 -> keep
        result = _sampling_processor(None, "info", {"event": "debug_test"})
    assert result["_sampled"] is True


def test_configure_replaces_rules():
    """Second call replaces, not extends."""
    configure_sampling({"a": 0.5})
    configure_sampling({"b": 0.5})

    import hyper2kvm.core.structured_log as sl

    assert "a" not in sl._sampling_rules
    assert "b" in sl._sampling_rules


def test_statistical_distribution():
    """Mock random.random for deterministic checks."""
    configure_sampling({"slow_": 0.5})

    # random() returns 0.3 < 0.5 -> keep
    with patch("random.random", return_value=0.3):
        result = _sampling_processor(None, "info", {"event": "slow_query"})
    assert result["_sampled"] is True

    # random() returns 0.7 >= 0.5 -> drop
    with patch("random.random", return_value=0.7):
        with pytest.raises(DropEvent):
            _sampling_processor(None, "info", {"event": "slow_query"})
