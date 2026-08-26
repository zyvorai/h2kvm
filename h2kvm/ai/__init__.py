# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/ai/__init__.py
"""
AI-powered migration intelligence for h2kvm.

Public API:
    - AIOrchestrator: central lifecycle + fail-safe wrapper
    - predict_migration: one-shot prediction helper
    - diagnose_issue: one-shot diagnostic helper

All heavy imports are lazy so ``import h2kvm.ai`` is cheap.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    # pylint: disable=import-outside-toplevel  # deliberate PEP 562 lazy exports: keeps `import h2kvm.ai` cheap
    if name == "AIOrchestrator":
        from .orchestrator import AIOrchestrator

        return AIOrchestrator

    if name == "MigrationFeatures":
        from .models import MigrationFeatures

        return MigrationFeatures

    if name == "Prediction":
        from .models import Prediction

        return Prediction

    if name == "Diagnosis":
        from .models import Diagnosis

        return Diagnosis

    if name == "HealthReport":
        from .models import HealthReport

        return HealthReport

    if name == "WorkloadProfile":
        from .models import WorkloadProfile

        return WorkloadProfile

    raise AttributeError(f"module 'h2kvm.ai' has no attribute {name!r}")


def predict_migration(
    features: Any,
    merged_config: dict[str, Any] | None = None,
) -> Any | None:
    """One-shot convenience: initialise AI, predict, shut down."""
    from .orchestrator import AIOrchestrator  # pylint: disable=import-outside-toplevel  # lazy import

    ai = AIOrchestrator()
    ai.initialize(merged_config)
    if not ai.is_initialized:
        return None
    try:
        result = ai.pre_migration_analysis(features)
        return result.get("prediction") if result else None
    finally:
        ai.shutdown()


def diagnose_issue(
    error_text: str,
    merged_config: dict[str, Any] | None = None,
) -> Any | None:
    """One-shot convenience: initialise AI, diagnose, shut down."""
    from .orchestrator import AIOrchestrator  # pylint: disable=import-outside-toplevel  # lazy import

    ai = AIOrchestrator()
    ai.initialize(merged_config)
    if not ai.is_initialized:
        return None
    try:
        return ai.diagnose_error(error_text)
    finally:
        ai.shutdown()


__all__ = [
    # The six names below are resolved dynamically via module __getattr__ (PEP 562 lazy exports).
    "AIOrchestrator",  # pylint: disable=undefined-all-variable
    "Diagnosis",  # pylint: disable=undefined-all-variable
    "HealthReport",  # pylint: disable=undefined-all-variable
    "MigrationFeatures",  # pylint: disable=undefined-all-variable
    "Prediction",  # pylint: disable=undefined-all-variable
    "WorkloadProfile",  # pylint: disable=undefined-all-variable
    "diagnose_issue",
    "predict_migration",
]
