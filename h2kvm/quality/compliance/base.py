# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/compliance/base.py
"""
Base compliance framework interface.

Defines abstract base classes for compliance validation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ComplianceFramework(Enum):
    """Supported compliance frameworks."""

    CIS_BENCHMARK = "cis_benchmark"
    STIG = "stig"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    GDPR = "gdpr"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    NIST = "nist"


class ComplianceLevel(Enum):
    """Compliance check severity levels."""

    CRITICAL = "critical"  # Must pass for compliance
    HIGH = "high"  # Should pass for compliance
    MEDIUM = "medium"  # Recommended for compliance
    LOW = "low"  # Best practice
    INFO = "info"  # Informational only


@dataclass
class ComplianceCheck:
    """
    Individual compliance check result.

    Represents a single compliance validation check.
    """

    # Identification
    check_id: str
    framework: ComplianceFramework
    title: str
    description: str

    # Result
    passed: bool
    level: ComplianceLevel

    # Details
    finding: str | None = None
    remediation: str | None = None
    references: list[str] = field(default_factory=list)

    # Context
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceResult:
    """
    Compliance validation result for a VM.

    Summary of all compliance checks for a specific framework.
    """

    # Identity
    vm_name: str
    framework: ComplianceFramework

    # Results
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    skipped_checks: int = 0

    # By level
    critical_failures: int = 0
    high_failures: int = 0
    medium_failures: int = 0
    low_failures: int = 0

    # Details
    checks: list[ComplianceCheck] = field(default_factory=list)
    overall_compliant: bool = False
    compliance_score: float = 0.0  # 0.0 - 100.0

    # Timing
    scan_start: datetime = field(default_factory=datetime.now)
    scan_end: datetime | None = None
    duration_seconds: float = 0.0

    # Context
    os_type: str | None = None
    os_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ComplianceValidator(ABC):
    """
    Abstract base class for compliance validators.

    Each compliance framework implements this interface.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize compliance validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    @abstractmethod
    def get_framework(self) -> ComplianceFramework:
        """
        Get compliance framework type.

        Returns:
            ComplianceFramework enum value
        """

    @abstractmethod
    def validate(self, vmcraft_instance, os_info: dict[str, Any]) -> ComplianceResult:
        """
        Validate VM against compliance framework.

        Args:
            vmcraft_instance: Launched VMCraft instance
            os_info: OS information dict

        Returns:
            ComplianceResult with all check results
        """

    @abstractmethod
    def get_checks(self) -> list[dict[str, Any]]:
        """
        Get list of available compliance checks.

        Returns:
            List of check metadata dicts:
                {
                    "check_id": str,
                    "title": str,
                    "description": str,
                    "level": ComplianceLevel,
                    "references": list[str]
                }
        """

    def calculate_compliance_score(self, result: ComplianceResult) -> float:
        """
        Calculate compliance score (0.0 - 100.0).

        Weighted by severity:
        - Critical: 4x weight
        - High: 3x weight
        - Medium: 2x weight
        - Low: 1x weight
        - Info: 0x weight (not counted)

        Args:
            result: ComplianceResult to score

        Returns:
            Compliance score (0.0 - 100.0)
        """
        if result.total_checks == 0:
            return 0.0

        total_weight = 0.0
        passed_weight = 0.0

        for check in result.checks:
            if check.level == ComplianceLevel.INFO:
                continue  # Don't count informational checks

            # Assign weights by level
            weight_map = {
                ComplianceLevel.CRITICAL: 4.0,
                ComplianceLevel.HIGH: 3.0,
                ComplianceLevel.MEDIUM: 2.0,
                ComplianceLevel.LOW: 1.0,
            }

            weight = weight_map.get(check.level, 1.0)
            total_weight += weight

            if check.passed:
                passed_weight += weight

        if total_weight == 0:
            return 100.0  # All checks are informational

        return (passed_weight / total_weight) * 100.0

    def is_compliant(self, result: ComplianceResult) -> bool:
        """
        Determine if VM is compliant.

        VM is compliant if:
        - No critical failures
        - No high failures
        - Compliance score >= 80%

        Args:
            result: ComplianceResult to evaluate

        Returns:
            True if compliant, False otherwise
        """
        return (
            result.critical_failures == 0 and result.high_failures == 0 and result.compliance_score >= 80.0
        )

    def get_failed_checks(
        self, result: ComplianceResult, min_level: ComplianceLevel | None = None
    ) -> list[ComplianceCheck]:
        """
        Get list of failed checks.

        Args:
            result: ComplianceResult to filter
            min_level: Minimum severity level to include

        Returns:
            List of failed ComplianceCheck objects
        """
        failed = [check for check in result.checks if not check.passed]

        if min_level:
            level_order = [
                ComplianceLevel.CRITICAL,
                ComplianceLevel.HIGH,
                ComplianceLevel.MEDIUM,
                ComplianceLevel.LOW,
                ComplianceLevel.INFO,
            ]

            min_index = level_order.index(min_level)
            failed = [check for check in failed if level_order.index(check.level) <= min_index]

        return failed
