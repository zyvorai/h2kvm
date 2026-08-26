# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/validation/__init__.py
"""
Migration validation framework.

Provides comprehensive pre- and post-migration validation to ensure successful VM migrations.
"""

from .database_validator import (
    DatabaseCheckResult,
    DatabaseValidator,
)
from .health_checker import (
    HealthChecker,
    HealthCheckResult,
    HealthCheckStatus,
    HealthCheckType,
)
from .network_validator import (
    NetworkCheckResult,
    NetworkValidator,
)
from .orchestrator import (
    ValidationOrchestrator,
    ValidationReport as OrchestratorValidationReport,
)
from .performance_validator import (
    PerformanceBenchmark,
    PerformanceMetric,
    PerformanceValidator,
)
from .service_validator import (
    ServiceCheckResult,
    ServiceValidator,
)
from .validation_framework import (
    BaseValidator,
    DiskValidator,
    ValidationReport,
    ValidationResult,
    ValidationRunner,
    ValidationSeverity,
    XMLValidator,
)
from .vmdk_inspector import (
    BootMode,
    Risk,
    RiskLevel,
    VMDKInspectionResult,
    VMDKInspector,
)

__all__ = [
    "BaseValidator",
    "BootMode",
    "DatabaseCheckResult",
    "DatabaseValidator",
    "DiskValidator",
    "HealthCheckResult",
    "HealthCheckStatus",
    "HealthCheckType",
    "HealthChecker",
    "NetworkCheckResult",
    "NetworkValidator",
    "OrchestratorValidationReport",
    "PerformanceBenchmark",
    "PerformanceMetric",
    "PerformanceValidator",
    "Risk",
    "RiskLevel",
    "ServiceCheckResult",
    "ServiceValidator",
    "VMDKInspectionResult",
    "VMDKInspector",
    "ValidationOrchestrator",
    "ValidationReport",
    "ValidationResult",
    "ValidationRunner",
    "ValidationSeverity",
    "XMLValidator",
]
