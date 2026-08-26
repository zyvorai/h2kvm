# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/compliance/report_generator.py
"""
Compliance report generator.

Generates compliance reports in multiple formats.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .base import ComplianceLevel, ComplianceResult

logger = logging.getLogger(__name__)


class ComplianceReportGenerator:
    """
    Compliance report generator.

    Generates reports in markdown, JSON, HTML, and CSV formats.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize report generator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def generate_markdown_report(self, result: ComplianceResult) -> str:
        """
        Generate markdown compliance report.

        Args:
            result: ComplianceResult to report on

        Returns:
            Markdown-formatted report
        """
        lines = [
            f"# Compliance Report: {result.framework.value.upper()}",
            "",
            f"**VM**: {result.vm_name}",
            f"**Framework**: {result.framework.value}",
            f"**OS**: {result.os_type} {result.os_version or ''}",
            f"**Scan Date**: {result.scan_start.isoformat()}",
            f"**Duration**: {result.duration_seconds:.1f}s",
            "",
            "---",
            "",
            "## Summary",
            "",
            f"**Compliance Score**: {result.compliance_score:.1f}%",
            f"**Overall Status**: {'✅ COMPLIANT' if result.overall_compliant else '❌ NON-COMPLIANT'}",
            "",
            f"**Total Checks**: {result.total_checks}",
            f"- ✅ Passed: {result.passed_checks}",
            f"- ❌ Failed: {result.failed_checks}",
            f"- ⏭️ Skipped: {result.skipped_checks}",
            "",
            "### Failures by Severity",
            "",
            f"- 🔴 Critical: {result.critical_failures}",
            f"- 🟠 High: {result.high_failures}",
            f"- 🟡 Medium: {result.medium_failures}",
            f"- 🟢 Low: {result.low_failures}",
            "",
            "---",
            "",
        ]

        # Group checks by status and level
        failed_critical = [c for c in result.checks if not c.passed and c.level == ComplianceLevel.CRITICAL]
        failed_high = [c for c in result.checks if not c.passed and c.level == ComplianceLevel.HIGH]
        failed_medium = [c for c in result.checks if not c.passed and c.level == ComplianceLevel.MEDIUM]
        [c for c in result.checks if not c.passed and c.level == ComplianceLevel.LOW]

        # Critical failures
        if failed_critical:
            lines.extend(["## 🔴 Critical Failures", ""])
            for check in failed_critical:
                lines.extend(
                    [
                        f"### {check.check_id}: {check.title}",
                        "",
                        f"**Description**: {check.description}",
                        f"**Finding**: {check.finding}",
                        "",
                    ]
                )
                if check.remediation:
                    lines.extend([f"**Remediation**: {check.remediation}", ""])
                if check.references:
                    lines.extend([f"**References**: {', '.join(check.references)}", ""])
                lines.append("---")
                lines.append("")

        # High failures
        if failed_high:
            lines.extend(["## 🟠 High Failures", ""])
            for check in failed_high:
                lines.extend(
                    [f"### {check.check_id}: {check.title}", "", f"**Finding**: {check.finding}", ""]
                )
                if check.remediation:
                    lines.extend([f"**Remediation**: {check.remediation}", ""])

        # Medium failures
        if failed_medium:
            lines.extend(["## 🟡 Medium Failures", ""])
            for check in failed_medium:
                lines.extend(
                    [f"### {check.check_id}: {check.title}", "", f"**Finding**: {check.finding}", ""]
                )
                if check.remediation:
                    lines.extend([f"**Remediation**: {check.remediation}", ""])

        # Passed checks (summary only)
        passed_checks = [c for c in result.checks if c.passed]
        if passed_checks:
            lines.extend(
                ["## ✅ Passed Checks", "", f"{len(passed_checks)} checks passed successfully:", ""]
            )
            for check in passed_checks:
                lines.append(f"- {check.check_id}: {check.title}")
            lines.append("")

        return "\n".join(lines)

    def generate_json_report(self, result: ComplianceResult) -> str:
        """
        Generate JSON compliance report.

        Args:
            result: ComplianceResult to report on

        Returns:
            JSON-formatted report
        """
        report = {
            "vm_name": result.vm_name,
            "framework": result.framework.value,
            "os_type": result.os_type,
            "os_version": result.os_version,
            "scan_start": result.scan_start.isoformat(),
            "scan_end": result.scan_end.isoformat() if result.scan_end else None,
            "duration_seconds": result.duration_seconds,
            "summary": {
                "overall_compliant": result.overall_compliant,
                "compliance_score": result.compliance_score,
                "total_checks": result.total_checks,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "skipped_checks": result.skipped_checks,
                "critical_failures": result.critical_failures,
                "high_failures": result.high_failures,
                "medium_failures": result.medium_failures,
                "low_failures": result.low_failures,
            },
            "checks": [
                {
                    "check_id": check.check_id,
                    "title": check.title,
                    "description": check.description,
                    "level": check.level.value,
                    "passed": check.passed,
                    "finding": check.finding,
                    "remediation": check.remediation,
                    "references": check.references,
                    "timestamp": check.timestamp.isoformat(),
                }
                for check in result.checks
            ],
        }

        return json.dumps(report, indent=2)

    def generate_csv_report(self, result: ComplianceResult) -> str:
        """
        Generate CSV compliance report.

        Args:
            result: ComplianceResult to report on

        Returns:
            CSV-formatted report
        """
        lines = ["Check ID,Title,Level,Status,Finding,Remediation"]

        for check in result.checks:
            lines.append(
                f'"{check.check_id}",'
                f'"{check.title}",'
                f'"{check.level.value}",'
                f'"{("PASS" if check.passed else "FAIL")}",'
                f'"{check.finding or ""}",'
                f'"{check.remediation or ""}"'
            )

        return "\n".join(lines)

    def save_reports(
        self, result: ComplianceResult, output_dir: Path, formats: list[str] | None = None
    ) -> dict[str, Path]:
        """
        Save compliance reports in multiple formats.

        Args:
            result: ComplianceResult to report on
            output_dir: Directory to save reports
            formats: List of formats (markdown, json, csv, html)

        Returns:
            Dict mapping format to output file path
        """
        if formats is None:
            formats = ["markdown", "json"]

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = {}

        # Generate and save markdown
        if "markdown" in formats:
            md_report = self.generate_markdown_report(result)
            md_file = output_dir / f"compliance_{result.vm_name}_{result.framework.value}.md"
            md_file.write_text(md_report)
            output_files["markdown"] = md_file
            self.logger.info(f"Markdown report saved: {md_file}")

        # Generate and save JSON
        if "json" in formats:
            json_report = self.generate_json_report(result)
            json_file = output_dir / f"compliance_{result.vm_name}_{result.framework.value}.json"
            json_file.write_text(json_report)
            output_files["json"] = json_file
            self.logger.info(f"JSON report saved: {json_file}")

        # Generate and save CSV
        if "csv" in formats:
            csv_report = self.generate_csv_report(result)
            csv_file = output_dir / f"compliance_{result.vm_name}_{result.framework.value}.csv"
            csv_file.write_text(csv_report)
            output_files["csv"] = csv_file
            self.logger.info(f"CSV report saved: {csv_file}")

        return output_files
