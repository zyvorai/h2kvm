# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Enhanced validation framework for VM conversion validation.

This module provides a comprehensive validation framework for verifying
converted VMs meet quality and correctness standards.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ValidationSeverity(Enum):
    """Validation issue severity levels."""

    INFO = "info"  # Informational message
    WARNING = "warning"  # Non-critical issue
    ERROR = "error"  # Critical issue that may prevent VM boot
    CRITICAL = "critical"  # Severe issue that will prevent VM boot


@dataclass
class ValidationResult:
    """Result from a single validation check."""

    check_name: str
    severity: ValidationSeverity
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        status = "✓" if self.passed else "✗"
        return f"ValidationResult({status} {self.check_name}: {self.severity.value})"


@dataclass
class ValidationReport:
    """Aggregate report from all validation checks."""

    validator_name: str
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    results: list[ValidationResult] = field(default_factory=list)
    duration: float = 0.0

    def add_result(self, result: ValidationResult) -> None:
        """Add a validation result."""
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1

    def has_errors(self) -> bool:
        """Check if report contains any errors or critical issues."""
        return any(
            not r.passed and r.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
            for r in self.results
        )

    def has_warnings(self) -> bool:
        """Check if report contains any warnings."""
        return any(not r.passed and r.severity == ValidationSeverity.WARNING for r in self.results)

    def get_issues_by_severity(self, severity: ValidationSeverity) -> list[ValidationResult]:
        """Get all issues of a specific severity."""
        return [r for r in self.results if not r.passed and r.severity == severity]

    def get_summary(self) -> dict[str, Any]:
        """Get validation summary."""
        return {
            "validator": self.validator_name,
            "total_checks": self.total_checks,
            "passed": self.passed_checks,
            "failed": self.failed_checks,
            "has_errors": self.has_errors(),
            "has_warnings": self.has_warnings(),
            "duration": self.duration,
            "errors": len(self.get_issues_by_severity(ValidationSeverity.ERROR)),
            "warnings": len(self.get_issues_by_severity(ValidationSeverity.WARNING)),
            "critical": len(self.get_issues_by_severity(ValidationSeverity.CRITICAL)),
        }

    def __repr__(self) -> str:
        return (
            f"ValidationReport({self.validator_name}: "
            f"{self.passed_checks}/{self.total_checks} passed, "
            f"{self.failed_checks} failed)"
        )


class BaseValidator(ABC):
    """Base class for all validators."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.report = ValidationReport(validator_name=self.__class__.__name__)

    @abstractmethod
    def validate(self, context: dict[str, Any]) -> ValidationReport:
        """
        Run all validation checks.

        Args:
            context: Validation context (paths, metadata, etc.)

        Returns:
            ValidationReport with all results
        """

    def _add_result(
        self,
        check_name: str,
        passed: bool,
        severity: ValidationSeverity,
        message: str,
        details: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
    ) -> None:
        """Helper to add a validation result."""
        result = ValidationResult(
            check_name=check_name,
            severity=severity,
            passed=passed,
            message=message,
            details=details or {},
            suggestions=suggestions or [],
        )
        self.report.add_result(result)

        # Log the result
        if passed:
            self.logger.debug(f"✓ {check_name}: {message}")
        elif severity == ValidationSeverity.CRITICAL:
            self.logger.error(f"✗ CRITICAL: {check_name}: {message}")
        elif severity == ValidationSeverity.ERROR:
            self.logger.error(f"✗ ERROR: {check_name}: {message}")
        elif severity == ValidationSeverity.WARNING:
            self.logger.warning(f"⚠ WARNING: {check_name}: {message}")
        else:
            self.logger.info(f"ℹ INFO: {check_name}: {message}")


class DiskValidator(BaseValidator):
    """Validator for disk-related checks."""

    def validate(self, context: dict[str, Any]) -> ValidationReport:
        """
        Validate disk configuration and files.

        Args:
            context: Must contain:
                - output_path: Path to converted disk
                - format: Expected disk format (qcow2, raw, etc.)
                - minimum_size: Optional minimum disk size in bytes

        Returns:
            ValidationReport with disk validation results
        """
        import time

        start_time = time.time()

        output_path = Path(context.get("output_path", ""))
        context.get("format", "qcow2")
        minimum_size = context.get("minimum_size", 0)

        # Check 1: Disk file exists
        if output_path.exists():
            self._add_result(
                check_name="disk_exists",
                passed=True,
                severity=ValidationSeverity.INFO,
                message=f"Disk file exists: {output_path}",
            )
        else:
            self._add_result(
                check_name="disk_exists",
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Disk file not found: {output_path}",
                suggestions=["Check conversion process completed successfully"],
            )
            self.report.duration = time.time() - start_time
            return self.report

        # Check 2: Disk size
        disk_size = output_path.stat().st_size
        if minimum_size > 0 and disk_size < minimum_size:
            self._add_result(
                check_name="disk_size",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Disk too small: {disk_size} bytes < {minimum_size} bytes",
                details={"actual_size": disk_size, "minimum_size": minimum_size},
            )
        else:
            self._add_result(
                check_name="disk_size",
                passed=True,
                severity=ValidationSeverity.INFO,
                message=f"Disk size: {disk_size} bytes",
                details={"size_bytes": disk_size, "size_mb": disk_size // (1024 * 1024)},
            )

        # Check 3: Non-zero size
        if disk_size == 0:
            self._add_result(
                check_name="disk_non_zero",
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                message="Disk file is empty (0 bytes)",
                suggestions=["Check conversion process for errors"],
            )
        else:
            self._add_result(
                check_name="disk_non_zero",
                passed=True,
                severity=ValidationSeverity.INFO,
                message="Disk is non-empty",
            )

        # Check 4: Readable
        if output_path.is_file() and output_path.stat().st_mode & 0o400:
            self._add_result(
                check_name="disk_readable",
                passed=True,
                severity=ValidationSeverity.INFO,
                message="Disk file is readable",
            )
        else:
            self._add_result(
                check_name="disk_readable",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message="Disk file is not readable",
                suggestions=["Check file permissions"],
            )

        self.report.duration = time.time() - start_time
        return self.report


class XMLValidator(BaseValidator):
    """Validator for libvirt domain XML."""

    def validate(self, context: dict[str, Any]) -> ValidationReport:
        """
        Validate libvirt domain XML.

        Args:
            context: Must contain:
                - xml_path: Path to domain XML file

        Returns:
            ValidationReport with XML validation results
        """
        import time

        start_time = time.time()

        xml_path = Path(context.get("xml_path", ""))

        # Check 1: XML file exists
        if xml_path.exists():
            self._add_result(
                check_name="xml_exists",
                passed=True,
                severity=ValidationSeverity.INFO,
                message=f"XML file exists: {xml_path}",
            )
        else:
            self._add_result(
                check_name="xml_exists",
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"XML file not found: {xml_path}",
            )
            self.report.duration = time.time() - start_time
            return self.report

        # Check 2: Parse XML
        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(xml_path)
            root = tree.getroot()

            self._add_result(
                check_name="xml_well_formed",
                passed=True,
                severity=ValidationSeverity.INFO,
                message="XML is well-formed",
            )

            # Check 3: Root element is 'domain'
            if root.tag == "domain":
                self._add_result(
                    check_name="xml_root_element",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    message="Root element is 'domain'",
                )
            else:
                self._add_result(
                    check_name="xml_root_element",
                    passed=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Unexpected root element: {root.tag}",
                )

            # Check 4: Domain has name
            name_elem = root.find("name")
            if name_elem is not None and name_elem.text:
                self._add_result(
                    check_name="domain_has_name",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    message=f"Domain name: {name_elem.text}",
                )
            else:
                self._add_result(
                    check_name="domain_has_name",
                    passed=False,
                    severity=ValidationSeverity.WARNING,
                    message="Domain has no name",
                )

            # Check 5: Domain has disks
            devices = root.find("devices")
            disks = devices.findall("disk") if devices is not None else []
            if len(disks) > 0:
                self._add_result(
                    check_name="domain_has_disks",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    message=f"Domain has {len(disks)} disk(s)",
                    details={"disk_count": len(disks)},
                )
            else:
                self._add_result(
                    check_name="domain_has_disks",
                    passed=False,
                    severity=ValidationSeverity.ERROR,
                    message="Domain has no disks",
                    suggestions=["Ensure disk devices are properly configured"],
                )

        except Exception as e:
            self._add_result(
                check_name="xml_well_formed",
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"XML parsing failed: {e}",
                suggestions=["Check XML syntax and structure"],
            )

        self.report.duration = time.time() - start_time
        return self.report


class ValidationRunner:
    """Orchestrates running multiple validators."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize validation runner.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.validators: list[BaseValidator] = []

    def add_validator(self, validator: BaseValidator) -> None:
        """Add a validator to run."""
        self.validators.append(validator)

    def run_all(self, context: dict[str, Any]) -> list[ValidationReport]:
        """
        Run all validators.

        Args:
            context: Validation context

        Returns:
            List of ValidationReport objects
        """
        reports = []

        self.logger.info(f"Running {len(self.validators)} validator(s)")

        for validator in self.validators:
            self.logger.info(f"  Running {validator.__class__.__name__}...")
            report = validator.validate(context)
            reports.append(report)

            # Log summary
            summary = report.get_summary()
            self.logger.info(
                f"  {validator.__class__.__name__}: {summary['passed']}/{summary['total_checks']} passed"
            )

            if summary["has_errors"]:
                self.logger.error(f"  {summary['errors']} error(s), {summary['critical']} critical")

        return reports

    def get_aggregate_summary(self, reports: list[ValidationReport]) -> dict[str, Any]:
        """
        Get aggregate summary across all reports.

        Args:
            reports: List of validation reports

        Returns:
            Aggregate summary
        """
        total_checks = sum(r.total_checks for r in reports)
        total_passed = sum(r.passed_checks for r in reports)
        total_failed = sum(r.failed_checks for r in reports)
        has_errors = any(r.has_errors() for r in reports)
        has_warnings = any(r.has_warnings() for r in reports)

        return {
            "total_validators": len(reports),
            "total_checks": total_checks,
            "passed": total_passed,
            "failed": total_failed,
            "has_errors": has_errors,
            "has_warnings": has_warnings,
            "validator_summaries": [r.get_summary() for r in reports],
        }


__all__ = [
    "BaseValidator",
    "DiskValidator",
    "ValidationReport",
    "ValidationResult",
    "ValidationRunner",
    "ValidationSeverity",
    "XMLValidator",
]
