# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/validation/orchestrator.py
"""
Validation orchestrator.

Coordinates all validation checks and generates comprehensive reports.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .database_validator import DatabaseValidator
from .health_checker import HealthChecker, HealthCheckResult, HealthCheckStatus
from .network_validator import NetworkValidator
from .performance_validator import PerformanceValidator
from .service_validator import ServiceValidator

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """
    Comprehensive validation report.

    Attributes:
        success: Overall validation success (all critical checks passed)
        total_checks: Total number of checks performed
        passed: Number of checks that passed
        failed: Number of checks that failed
        warnings: Number of checks with warnings
        errors: Number of checks with errors
        checks: List of all check results
        summary_by_type: Summary grouped by check type
        duration_ms: Total validation duration in milliseconds
    """

    success: bool
    total_checks: int
    passed: int
    failed: int
    warnings: int
    errors: int
    checks: list[HealthCheckResult]
    summary_by_type: dict[str, dict[str, int]] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "errors": self.errors,
            "checks": [check.to_dict() for check in self.checks],
            "summary_by_type": self.summary_by_type,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class ValidationOrchestrator:
    """
    Validation orchestrator.

    Coordinates all validation checks and generates comprehensive reports.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize validation orchestrator.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.health_checker = HealthChecker(logger)
        self.service_validator = ServiceValidator(logger)
        self.network_validator = NetworkValidator(logger)
        self.database_validator = DatabaseValidator(logger)
        self.performance_validator = PerformanceValidator(logger)

    def validate_migration(
        self,
        vmcraft_instance,
        *,
        check_services: bool = True,
        check_network: bool = True,
        check_databases: bool = True,
        check_performance: bool = True,
    ) -> ValidationReport:
        """
        Run comprehensive migration validation.

        Args:
            vmcraft_instance: VMCraft instance with mounted filesystem
            check_services: Enable service validation
            check_network: Enable network validation
            check_databases: Enable database validation
            check_performance: Enable performance validation

        Returns:
            Validation report with all check results
        """
        import time

        start = time.time()

        self.logger.info("Starting migration validation...")

        all_checks: list[HealthCheckResult] = []

        # 1. System health checks (always run)
        self.logger.info("Running system health checks...")
        health_checks = self.health_checker.run_all_checks(vmcraft_instance)
        all_checks.extend(health_checks)

        # 2. Service validation
        if check_services:
            self.logger.info("Running service validation...")
            service_check = self.service_validator.validate_critical_services(vmcraft_instance)
            all_checks.append(service_check)

        # 3. Network validation
        if check_network:
            self.logger.info("Running network validation...")
            network_checks = self.network_validator.validate_network(vmcraft_instance)
            all_checks.extend(network_checks)

        # 4. Database validation
        if check_databases:
            self.logger.info("Running database validation...")
            database_checks = self.database_validator.validate_databases(vmcraft_instance)
            all_checks.extend(database_checks)

        # 5. Performance validation
        if check_performance:
            self.logger.info("Running performance validation...")
            performance_checks = self.performance_validator.validate_performance(vmcraft_instance)
            all_checks.extend(performance_checks)

        # Calculate summary
        total_checks = len(all_checks)
        passed = sum(1 for c in all_checks if c.status == HealthCheckStatus.PASS)
        failed = sum(1 for c in all_checks if c.status == HealthCheckStatus.FAIL)
        warnings = sum(1 for c in all_checks if c.status == HealthCheckStatus.WARN)
        errors = sum(1 for c in all_checks if c.status == HealthCheckStatus.ERROR)

        # Success if no failures/errors (warnings are acceptable)
        success = failed == 0 and errors == 0

        # Summary by type
        summary_by_type = {}
        for check in all_checks:
            check_type = check.check_type.value
            if check_type not in summary_by_type:
                summary_by_type[check_type] = {
                    "total": 0,
                    "pass": 0,
                    "fail": 0,
                    "warn": 0,
                    "error": 0,
                    "skip": 0,
                }

            summary_by_type[check_type]["total"] += 1
            status = check.status.value
            summary_by_type[check_type][status] += 1

        duration = (time.time() - start) * 1000

        report = ValidationReport(
            success=success,
            total_checks=total_checks,
            passed=passed,
            failed=failed,
            warnings=warnings,
            errors=errors,
            checks=all_checks,
            summary_by_type=summary_by_type,
            duration_ms=duration,
        )

        self.logger.info(
            f"Validation complete: {passed}/{total_checks} passed, "
            f"{failed} failed, {warnings} warnings, {errors} errors ({duration:.2f}ms)"
        )

        return report

    def generate_markdown_report(self, report: ValidationReport) -> str:
        """
        Generate Markdown validation report.

        Args:
            report: Validation report

        Returns:
            Markdown-formatted report
        """
        lines = [
            "# Migration Validation Report",
            "",
            "## Summary",
            "",
            f"**Overall Status**: {'✅ PASS' if report.success else '❌ FAIL'}",
            f"**Total Checks**: {report.total_checks}",
            f"**Passed**: {report.passed}",
            f"**Failed**: {report.failed}",
            f"**Warnings**: {report.warnings}",
            f"**Errors**: {report.errors}",
            f"**Duration**: {report.duration_ms:.2f}ms",
            "",
            "---",
            "",
        ]

        # Summary by type
        if report.summary_by_type:
            lines.extend(
                [
                    "## Summary by Check Type",
                    "",
                    "| Check Type | Total | Pass | Fail | Warn | Error | Skip |",
                    "|------------|-------|------|------|------|-------|------|",
                ]
            )

            for check_type, summary in sorted(report.summary_by_type.items()):
                lines.append(
                    f"| {check_type.title()} | {summary['total']} | "
                    f"{summary['pass']} | {summary['fail']} | {summary['warn']} | "
                    f"{summary['error']} | {summary['skip']} |"
                )

            lines.extend(["", "---", ""])

        # Detailed check results
        lines.extend(
            [
                "## Detailed Results",
                "",
            ]
        )

        # Group by type
        checks_by_type = {}
        for check in report.checks:
            check_type = check.check_type.value
            if check_type not in checks_by_type:
                checks_by_type[check_type] = []
            checks_by_type[check_type].append(check)

        for check_type, checks in sorted(checks_by_type.items()):
            lines.extend(
                [
                    f"### {check_type.title()} Checks",
                    "",
                ]
            )

            for check in checks:
                # Status emoji
                status_emoji = {
                    HealthCheckStatus.PASS: "✅",
                    HealthCheckStatus.FAIL: "❌",
                    HealthCheckStatus.WARN: "⚠️",
                    HealthCheckStatus.SKIP: "⏭️",
                    HealthCheckStatus.ERROR: "🔥",
                }[check.status]

                lines.extend(
                    [
                        f"#### {status_emoji} {check.name}",
                        "",
                        f"**Status**: {check.status.value.upper()}",
                        f"**Message**: {check.message}",
                        f"**Duration**: {check.duration_ms:.2f}ms",
                    ]
                )

                if check.details:
                    lines.append(f"**Details**: {json.dumps(check.details, indent=2)}")

                if check.remediation:
                    lines.extend(
                        [
                            "",
                            f"**Remediation**: {check.remediation}",
                        ]
                    )

                lines.append("")

        return "\n".join(lines)

    def save_report(
        self,
        report: ValidationReport,
        output_dir: Path,
        *,
        json_report: bool = True,
        markdown_report: bool = True,
    ) -> dict[str, str]:
        """
        Save validation report to files.

        Args:
            report: Validation report
            output_dir: Output directory
            json_report: Generate JSON report
            markdown_report: Generate Markdown report

        Returns:
            Dict mapping format to file path
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_files = {}

        # JSON report
        if json_report:
            json_file = output_dir / "validation-report.json"
            json_file.write_text(report.to_json())
            saved_files["json"] = str(json_file)
            self.logger.info(f"Saved JSON report: {json_file}")

        # Markdown report
        if markdown_report:
            md_file = output_dir / "validation-report.md"
            md_file.write_text(self.generate_markdown_report(report))
            saved_files["markdown"] = str(md_file)
            self.logger.info(f"Saved Markdown report: {md_file}")

        return saved_files
