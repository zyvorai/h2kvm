# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/config.py
"""
Load AI configuration from the ``ai:`` section of the merged config dict.
"""

from __future__ import annotations

from typing import Any

from .models import AIConfig

_DEFAULTS = {
    "enabled": True,
    "knowledge_base_path": "~/.cache/hyper2kvm/ai/knowledge.db",
    "min_history_for_prediction": 3,
    "anomaly_z_threshold": 2.5,
    "max_similar_lookback": 100,
    "auto_remediate": False,
    "auto_remediate_risk_max": "low",
    "telemetry_sampling_rate": 1.0,
}


def load_ai_config(merged_config: dict[str, Any] | None = None) -> AIConfig:
    """Build an :class:`AIConfig` from the ``ai:`` section of *merged_config*.

    Missing keys fall back to built-in defaults.
    """
    if merged_config is None:
        merged_config = {}
    ai_section = merged_config.get("ai") or {}
    if not isinstance(ai_section, dict):
        ai_section = {}

    def _get(key: str) -> Any:
        return ai_section.get(key, _DEFAULTS[key])

    return AIConfig(
        enabled=bool(_get("enabled")),
        knowledge_base_path=str(_get("knowledge_base_path")),
        min_history_for_prediction=int(_get("min_history_for_prediction")),
        anomaly_z_threshold=float(_get("anomaly_z_threshold")),
        max_similar_lookback=int(_get("max_similar_lookback")),
        auto_remediate=bool(_get("auto_remediate")),
        auto_remediate_risk_max=str(_get("auto_remediate_risk_max")),
        telemetry_sampling_rate=float(_get("telemetry_sampling_rate")),
    )
