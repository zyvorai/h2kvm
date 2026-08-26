# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.ai.config module.

Loading AI configuration from the ``ai:`` section of a merged config dict.
"""

from __future__ import annotations

from h2kvm.ai.config import load_ai_config
from h2kvm.ai.models import AIConfig


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_none_config_returns_defaults():
    cfg = load_ai_config(None)
    assert cfg.enabled is True
    assert cfg.auto_remediate is False
    assert cfg.min_history_for_prediction == 3


def test_empty_dict_returns_defaults():
    cfg = load_ai_config({})
    assert cfg.enabled is True
    assert cfg.knowledge_base_path == "~/.cache/h2kvm/ai/knowledge.db"
    assert cfg.anomaly_z_threshold == 2.5


def test_defaults_match_ai_config_dataclass():
    cfg = load_ai_config(None)
    default = AIConfig()
    assert cfg.enabled == default.enabled
    assert cfg.knowledge_base_path == default.knowledge_base_path
    assert cfg.min_history_for_prediction == default.min_history_for_prediction
    assert cfg.anomaly_z_threshold == default.anomaly_z_threshold
    assert cfg.max_similar_lookback == default.max_similar_lookback
    assert cfg.auto_remediate == default.auto_remediate
    assert cfg.auto_remediate_risk_max == default.auto_remediate_risk_max
    assert cfg.telemetry_sampling_rate == default.telemetry_sampling_rate


# ---------------------------------------------------------------------------
# Partial override
# ---------------------------------------------------------------------------


def test_partial_config_merges_with_defaults():
    cfg = load_ai_config({"ai": {"enabled": False, "anomaly_z_threshold": 3.0}})
    assert cfg.enabled is False
    assert cfg.anomaly_z_threshold == 3.0
    # Non-overridden fields keep defaults.
    assert cfg.max_similar_lookback == 100
    assert cfg.auto_remediate is False
    assert cfg.knowledge_base_path == "~/.cache/h2kvm/ai/knowledge.db"


# ---------------------------------------------------------------------------
# Full override
# ---------------------------------------------------------------------------


def test_full_config_overrides_all():
    cfg = load_ai_config(
        {
            "ai": {
                "enabled": False,
                "knowledge_base_path": "/custom/kb.db",
                "min_history_for_prediction": 10,
                "anomaly_z_threshold": 4.0,
                "max_similar_lookback": 50,
                "auto_remediate": True,
                "auto_remediate_risk_max": "medium",
                "telemetry_sampling_rate": 0.5,
            }
        }
    )
    assert cfg.enabled is False
    assert cfg.knowledge_base_path == "/custom/kb.db"
    assert cfg.min_history_for_prediction == 10
    assert cfg.anomaly_z_threshold == 4.0
    assert cfg.max_similar_lookback == 50
    assert cfg.auto_remediate is True
    assert cfg.auto_remediate_risk_max == "medium"
    assert cfg.telemetry_sampling_rate == 0.5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_non_dict_ai_section_treated_as_empty():
    cfg = load_ai_config({"ai": "not-a-dict"})
    default = AIConfig()
    assert cfg.enabled == default.enabled
    assert cfg.anomaly_z_threshold == default.anomaly_z_threshold


def test_non_dict_ai_section_list():
    cfg = load_ai_config({"ai": [1, 2, 3]})
    assert cfg.enabled is True
    assert cfg.auto_remediate is False


def test_type_coercion_string_false():
    # bool("false") is True in Python -- verifies that load_ai_config
    # applies bool() coercion as documented.
    cfg = load_ai_config({"ai": {"enabled": "false"}})
    # "false" is a non-empty string, so bool("false") == True
    assert cfg.enabled is True


def test_type_coercion_zero_disables():
    cfg = load_ai_config({"ai": {"enabled": 0}})
    assert cfg.enabled is False
