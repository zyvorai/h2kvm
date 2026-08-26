# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/compliance/orchestrator.py
"""
Compliance orchestrator.

Coordinates compliance validation, audit logging, change tracking, and reporting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .audit_logger import AuditLogger
from .base import ComplianceFramework, ComplianceResult
from .change_tracker import ChangeTracker
from .cis_benchmarks import CISBenchmarkValidator
from .report_generator import ComplianceReportGenerator
from .stig_validator import STIGValidator

logger = logging.getLogger(__name__)


class ComplianceOrchestrator:
    """
    Compliance orchestrator.

    Unified interface for compliance validation, audit logging, and reporting.
    """

    def __init__(self, logger: logging.Logger, audit_dir: Path | None = None, session_id: str | None = None):
        """
        Initialize compliance orchestrator.

        Args:
            logger: Logger instance
            audit_dir: Directory for audit logs
            session_id: Optional session identifier
        """
        self.logger = logger

        # Initialize components
        self.audit_logger = (
            AuditLogger(logger, audit_dir or Path("./audit"), session_id) if audit_dir else None
        )

        self.report_generator = ComplianceReportGenerator(logger)

        # Available validators
        self.validators = {
            ComplianceFramework.CIS_BENCHMARK: CISBenchmarkValidator(logger),
            ComplianceFramework.STIG: STIGValidator(logger),
        }

        # Change tracker (per-VM)
        self.change_trackers: dict[str, ChangeTracker] = {}

    def get_change_tracker(self, vm_name: str, output_dir: Path) -> ChangeTracker:
        """
        Get or create change tracker for VM.

        Args:
            vm_name: VM name
            output_dir: Directory for change logs

        Returns:
            ChangeTracker instance
        """
        if vm_name not in self.change_trackers:
            self.change_trackers[vm_name] = ChangeTracker(self.logger, output_dir, vm_name)
        return self.change_trackers[vm_name]

    def validate_compliance(
        self, vmcraft_instance, os_info: dict[str, Any], frameworks: list[ComplianceFramework] | None = None
    ) -> dict[ComplianceFramework, ComplianceResult]:
        """
        Validate VM against compliance frameworks.

        Args:
            vmcraft_instance: Launched VMCraft instance
            os_info: OS information dict
            frameworks: List of frameworks to check (None = all)

        Returns:
            Dict mapping framework to ComplianceResult
        """
        vm_name = vmcraft_instance.disk_path.stem if hasattr(vmcraft_instance, "disk_path") else "unknown"

        if frameworks is None:
            frameworks = list(self.validators.keys())

        results = {}

        for framework in frameworks:
            validator = self.validators.get(framework)
            if not validator:
                self.logger.warning(f"No validator available for {framework.value}")
                continue

            self.logger.info(f"Running {framework.value} compliance scan...")

            # Log audit event
            if self.audit_logger:
                self.audit_logger.log_event(
                    event_type=__import__(
                        "h2kvm.quality.compliance.audit_logger", fromlist=["AuditEventType"]
                    ).AuditEventType.COMPLIANCE_SCAN_STARTED,
                    vm_name=vm_name,
                    action="compliance_scan",
                    description=f"Starting {framework.value} compliance scan",
                    metadata={"framework": framework.value},
                )

            # Run validation
            result = validator.validate(vmcraft_instance, os_info)
            results[framework] = result

            # Log completion
            if self.audit_logger:
                self.audit_logger.log_compliance_scan(
                    vm_name=vm_name,
                    framework=framework.value,
                    result="compliant" if result.overall_compliant else "non_compliant",
                    score=result.compliance_score,
                    metadata={
                        "passed_checks": result.passed_checks,
                        "failed_checks": result.failed_checks,
                        "critical_failures": result.critical_failures,
                    },
                )

                # Log individual violations
                failed_checks = validator.get_failed_checks(result)
                for check in failed_checks:
                    self.audit_logger.log_compliance_violation(
                        vm_name=vm_name,
                        framework=framework.value,
                        check_id=check.check_id,
                        severity=check.level.value,
                        finding=check.finding or "",
                    )

        return results

    def generate_reports(
        self,
        results: dict[ComplianceFramework, ComplianceResult],
        output_dir: Path,
        formats: list[str] | None = None,
    ) -> dict[str, list[Path]]:
        """
        Generate compliance reports for all results.

        Args:
            results: Dict of compliance results by framework
            output_dir: Directory to save reports
            formats: List of formats (markdown, json, csv)

        Returns:
            Dict mapping format to list of output file paths
        """
        output_files: dict[str, list[Path]] = {}

        for framework, result in results.items():
            self.logger.info(f"Generating reports for {framework.value}...")

            files = self.report_generator.save_reports(result, output_dir, formats)

            for format_name, file_path in files.items():
                if format_name not in output_files:
                    output_files[format_name] = []
                output_files[format_name].append(file_path)

        return output_files

    def get_compliance_summary(self, results: dict[ComplianceFramework, ComplianceResult]) -> dict[str, Any]:
        """
        Get summary of all compliance results.

        Args:
            results: Dict of compliance results by framework

        Returns:
            Summary dict
        """
        summary = {
            "total_frameworks": len(results),
            "overall_compliant": all(r.overall_compliant for r in results.values()),
            "by_framework": {},
            "aggregate": {
                "total_checks": 0,
                "passed_checks": 0,
                "failed_checks": 0,
                "critical_failures": 0,
                "high_failures": 0,
                "medium_failures": 0,
                "low_failures": 0,
            },
        }

        for framework, result in results.items():
            summary["by_framework"][framework.value] = {
                "compliant": result.overall_compliant,
                "score": result.compliance_score,
                "passed": result.passed_checks,
                "failed": result.failed_checks,
                "critical_failures": result.critical_failures,
            }

            # Aggregate totals
            summary["aggregate"]["total_checks"] += result.total_checks
            summary["aggregate"]["passed_checks"] += result.passed_checks
            summary["aggregate"]["failed_checks"] += result.failed_checks
            summary["aggregate"]["critical_failures"] += result.critical_failures
            summary["aggregate"]["high_failures"] += result.high_failures
            summary["aggregate"]["medium_failures"] += result.medium_failures
            summary["aggregate"]["low_failures"] += result.low_failures

        # Calculate aggregate score
        if summary["aggregate"]["total_checks"] > 0:
            summary["aggregate"]["compliance_score"] = (
                summary["aggregate"]["passed_checks"] / summary["aggregate"]["total_checks"]
            ) * 100.0
        else:
            summary["aggregate"]["compliance_score"] = 0.0

        return summary

    def full_compliance_workflow(
        self,
        vmcraft_instance,
        os_info: dict[str, Any],
        output_dir: Path,
        frameworks: list[ComplianceFramework] | None = None,
        report_formats: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run full compliance workflow.

        Args:
            vmcraft_instance: Launched VMCraft instance
            os_info: OS information dict
            output_dir: Directory for reports and logs
            frameworks: List of frameworks to check
            report_formats: List of report formats

        Returns:
            Workflow result dict
        """
        self.logger.info("Starting full compliance workflow...")

        result = {
            "success": False,
            "compliance_results": {},
            "reports_generated": {},
            "summary": {},
            "errors": [],
        }

        try:
            # Step 1: Validate compliance
            compliance_results = self.validate_compliance(vmcraft_instance, os_info, frameworks)
            result["compliance_results"] = compliance_results

            # Step 2: Generate reports
            report_files = self.generate_reports(compliance_results, output_dir, report_formats)
            result["reports_generated"] = {
                fmt: [str(f) for f in files] for fmt, files in report_files.items()
            }

            # Step 3: Generate summary
            summary = self.get_compliance_summary(compliance_results)
            result["summary"] = summary

            result["success"] = True
            self.logger.info(
                f"Compliance workflow complete: "
                f"{'COMPLIANT' if summary['overall_compliant'] else 'NON-COMPLIANT'}"
            )

        except Exception as e:
            self.logger.exception(f"Compliance workflow failed: {e}")
            result["errors"].append(str(e))
            result["success"] = False

        return result
