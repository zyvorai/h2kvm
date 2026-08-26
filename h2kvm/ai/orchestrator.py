# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/ai/orchestrator.py
"""
AI Orchestrator -- lifecycle manager for all AI sub-engines.

Every public method is fail-safe: if AI raises an exception the error is
logged and migration continues unaffected.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from h2kvm.core.structured_log import log_event

from .anomaly import AnomalyDetector
from .config import load_ai_config
from .diagnostic import DiagnosticEngine
from .health import HealthEngine
from .knowledge_base import KnowledgeBase
from .models import (
    AIConfig,
    MigrationFeatures,
    MigrationRecord,
)
from .predictive import PredictiveEngine
from .privacy import DataAnonymizer
from .remediation import RemediationEngine
from .workload import WorkloadClassifier

logger = logging.getLogger(__name__)


def _fail_safe(method):
    """Decorator that catches exceptions so AI never blocks migration."""

    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as exc:  # pylint: disable=broad-exception-caught  # AI must never block or fail the migration pipeline
            _log("ai_error", error=str(exc), method=method.__name__)
            return None

    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper


def _log(event: str, **fields: Any) -> None:
    """Best-effort structured log event."""
    try:
        log_event(event, **fields)
    except Exception:  # pylint: disable=broad-exception-caught  # logging must never block or fail the migration pipeline
        pass


class AIOrchestrator:  # pylint: disable=too-many-instance-attributes  # owns handles to every AI sub-engine plus lifecycle state
    """
    Central AI orchestrator for migration intelligence.

    Manages the lifecycle of all AI engines and provides a simple
    interface for the migration pipeline to call:

    - :meth:`initialize` -- set up all engines
    - :meth:`pre_migration_analysis` -- predict + classify + risk-assess
    - :meth:`post_migration_analysis` -- health check + record + anomaly detect
    - :meth:`diagnose_error` -- diagnose + remediate errors
    - :meth:`get_info` -- return summary for ``--ai-info``
    - :meth:`shutdown` -- close resources
    """

    def __init__(self) -> None:
        self._config: AIConfig | None = None
        self._kb: KnowledgeBase | None = None
        self._predictive: PredictiveEngine | None = None
        self._diagnostic: DiagnosticEngine | None = None
        self._remediation: RemediationEngine | None = None
        self._health: HealthEngine | None = None
        self._anomaly: AnomalyDetector | None = None
        self._workload: WorkloadClassifier | None = None
        self._anonymizer: DataAnonymizer | None = None
        self._initialized = False
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @_fail_safe
    def initialize(self, merged_config: dict[str, Any] | None = None) -> bool:
        """Initialise all AI engines.  Returns True on success."""
        self._config = load_ai_config(merged_config)
        if not self._config.enabled:
            _log("ai_disabled")
            return False

        db_path = str(Path(self._config.knowledge_base_path).expanduser())
        self._kb = KnowledgeBase(db_path)
        self._predictive = PredictiveEngine(self._kb, self._config)
        self._diagnostic = DiagnosticEngine(self._kb)
        self._remediation = RemediationEngine(self._config)
        self._health = HealthEngine()
        self._anomaly = AnomalyDetector(self._config)
        self._workload = WorkloadClassifier()
        self._anonymizer = DataAnonymizer()
        self._initialized = True
        _log("ai_initialized", kb_path=db_path)
        return True

    @property
    def is_initialized(self) -> bool:
        """Return True if initialize() has completed successfully."""
        return self._initialized

    @_fail_safe
    def shutdown(self) -> None:
        """Release resources."""
        if self._kb is not None:
            self._kb.close()
            self._kb = None
        self._initialized = False
        _log("ai_shutdown")

    # ------------------------------------------------------------------
    # Pre-migration
    # ------------------------------------------------------------------

    @_fail_safe
    def pre_migration_analysis(
        self,
        features: MigrationFeatures,
    ) -> dict[str, Any] | None:
        """Run pre-migration analysis and return a summary dict.

        The dict contains keys: ``prediction``, ``workload``, ``risks``.
        """
        if not self._initialized:
            return None

        self._start_time = time.time()

        result: dict[str, Any] = {}

        # Prediction
        if self._predictive:
            pred = self._predictive.predict(features)
            result["prediction"] = pred
            _log(
                "ai_prediction",
                success_prob=pred.success_probability,
                risk_count=len(pred.risks),
                confidence=pred.confidence,
                similar_count=pred.similar_count,
            )

        # Workload classification
        if self._workload:
            wp = self._workload.classify(features)
            result["workload"] = wp
            _log("ai_workload", workload_type=wp.workload_type.value, confidence=wp.confidence)

        return result

    # ------------------------------------------------------------------
    # Post-migration
    # ------------------------------------------------------------------

    # Mirrors the full post-migration record shape (features/success/errors/phases/report/actions).
    @_fail_safe
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def post_migration_analysis(
        self,
        features: MigrationFeatures,
        success: bool,
        errors: list[str] | None = None,
        phases: list[str] | None = None,
        fixer_report: dict[str, Any] | None = None,
        fixer_actions: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Run post-migration analysis: health check, record, anomaly detection."""
        if not self._initialized:
            return None

        duration = time.time() - self._start_time if self._start_time else 0.0
        errors = errors or []
        phases = phases or []
        fixer_actions = fixer_actions or []
        result: dict[str, Any] = {}

        # Health check
        if self._health:
            health = self._health.check(fixer_report)
            result["health"] = health
            _log("ai_health", overall=health.overall_status.value, checks=health.summary())

        # Record migration
        record = MigrationRecord(
            features=features,
            success=success,
            duration_seconds=duration,
            errors=errors,
            phases=phases,
            fixer_actions=fixer_actions,
        )

        # Anonymize error texts before storing
        if self._anonymizer:
            record.errors = [self._anonymizer.anonymize_text(e) for e in record.errors]

        if self._kb:
            self._kb.record_migration(record)
            _log("ai_record_saved", record_id=record.record_id, success=success)

        # Anomaly detection
        if self._anomaly and self._kb:
            history = self._kb.get_all_records(limit=100)
            anomalies = self._anomaly.detect_all(duration, len(errors), phases, history)
            if anomalies:
                result["anomalies"] = anomalies
                for a in anomalies:
                    _log("ai_anomaly", type=a.anomaly_type, message=a.message, z_score=a.z_score)

        return result

    # ------------------------------------------------------------------
    # Error diagnosis
    # ------------------------------------------------------------------

    @_fail_safe
    def diagnose_error(self, error_text: str) -> dict[str, Any] | None:
        """Diagnose an error and generate remediation plans."""
        if not self._initialized:
            return None

        result: dict[str, Any] = {}

        if self._diagnostic:
            diagnoses = self._diagnostic.diagnose(error_text)
            result["diagnoses"] = diagnoses

            if diagnoses and self._remediation:
                plans = self._remediation.plan_all(diagnoses)
                result["remediation_plans"] = plans
                auto_fixes = self._remediation.get_auto_fixes(plans)
                result["auto_fixes"] = auto_fixes

                _log(
                    "ai_diagnosis",
                    pattern_count=len(diagnoses),
                    plan_count=len(plans),
                    auto_fix_count=len(auto_fixes),
                )

        return result

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    @_fail_safe
    def get_info(self) -> dict[str, Any] | None:
        """Return a summary dict for ``--ai-info``."""
        info: dict[str, Any] = {
            "initialized": self._initialized,
            "enabled": self._config.enabled if self._config else False,
        }

        if self._config:
            info["config"] = {
                "knowledge_base_path": self._config.knowledge_base_path,
                "min_history_for_prediction": self._config.min_history_for_prediction,
                "anomaly_z_threshold": self._config.anomaly_z_threshold,
                "auto_remediate": self._config.auto_remediate,
            }

        if self._kb:
            info["knowledge_base"] = self._kb.get_migration_stats()
            info["error_patterns"] = len(self._kb.get_error_patterns())

        return info
