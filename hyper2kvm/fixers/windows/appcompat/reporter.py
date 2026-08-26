# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Application compatibility report generation.

Aggregates findings from application detection, license service scanning,
and SQL Server detection to generate comprehensive migration compatibility reports.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from .detector import AppCompatFinding, RiskLevel
from .sqlserver import SQLServerInstance

logger = logging.getLogger(__name__)


@dataclass
class CompatibilityReport:  # pylint: disable=too-many-instance-attributes  # dataclass models independent report fields
    """Comprehensive application compatibility report."""

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    hostname: str = "Unknown"

    # Findings
    hardware_apps: list[AppCompatFinding] = field(default_factory=list)
    license_services: list[AppCompatFinding] = field(default_factory=list)
    dongle_drivers: list[AppCompatFinding] = field(default_factory=list)
    sql_instances: list[SQLServerInstance] = field(default_factory=list)

    # Summary statistics
    total_findings: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "hostname": self.hostname,
            "summary": {
                "total_findings": self.total_findings,
                "risk_breakdown": {
                    "critical": self.critical_findings,
                    "high": self.high_findings,
                    "medium": self.medium_findings,
                    "low": self.low_findings,
                },
            },
            "hardware_dependent_applications": [f.to_dict() for f in self.hardware_apps],
            "license_services": [f.to_dict() for f in self.license_services],
            "dongle_drivers": [f.to_dict() for f in self.dongle_drivers],
            "sql_server_instances": [i.to_dict() for i in self.sql_instances],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:  # pylint: disable=too-many-branches  # one independent report section per finding category
        """Generate Markdown report."""
        lines = [
            "# Application Compatibility Report",
            "",
            f"**Generated**: {self.timestamp}",
            f"**Hostname**: {self.hostname}",
            "",
            "## Executive Summary",
            "",
            f"- **Total Findings**: {self.total_findings}",
            f"- **Critical Risk**: {self.critical_findings}",
            f"- **High Risk**: {self.high_findings}",
            f"- **Medium Risk**: {self.medium_findings}",
            f"- **Low Risk**: {self.low_findings}",
            "",
        ]

        # Hardware-dependent applications
        if self.hardware_apps:
            lines.extend(
                [
                    "## Hardware-Dependent Applications",
                    "",
                    f"Found **{len(self.hardware_apps)}** applications that may require attention after migration:",
                    "",
                ]
            )

            for app in self.hardware_apps:
                lines.extend(
                    [
                        f"### {app.name}",
                        "",
                        f"- **Vendor**: {app.vendor or 'Unknown'}",
                        f"- **Version**: {app.version or 'Unknown'}",
                        f"- **Risk Level**: {app.risk_level.value}",
                        "",
                        "**Recommendations**:",
                    ]
                )

                for rec in app.recommendations:
                    lines.append(f"- {rec}")

                lines.extend(["", "---", ""])

        # License services
        if self.license_services:
            lines.extend(
                [
                    "## License Manager Services",
                    "",
                    f"Found **{len(self.license_services)}** license manager services:",
                    "",
                ]
            )

            for svc in self.license_services:
                lines.extend(
                    [
                        f"### {svc.name}",
                        "",
                        f"- **Risk Level**: {svc.risk_level.value}",
                        "",
                        "**Recommendations**:",
                    ]
                )

                for rec in svc.recommendations:
                    lines.append(f"- {rec}")

                lines.extend(["", "---", ""])

        # Dongle drivers
        if self.dongle_drivers:
            lines.extend(
                [
                    "## Hardware Dongle Drivers",
                    "",
                    f"Found **{len(self.dongle_drivers)}** hardware dongle drivers:",
                    "",
                    "⚠️ **CRITICAL**: Hardware dongles require USB passthrough or network dongle server.",
                    "",
                ]
            )

            for dongle in self.dongle_drivers:
                lines.extend(
                    [
                        f"### {dongle.name}",
                        "",
                        f"- **Risk Level**: {dongle.risk_level.value}",
                        f"- **Driver**: {dongle.details.get('driver_name', 'Unknown')}",
                        "",
                        "**Recommendations**:",
                    ]
                )

                for rec in dongle.recommendations:
                    lines.append(f"- {rec}")

                lines.extend(["", "---", ""])

        # SQL Server instances
        if self.sql_instances:
            lines.extend(
                [
                    "## SQL Server Instances",
                    "",
                    f"Found **{len(self.sql_instances)}** SQL Server instance(s):",
                    "",
                ]
            )

            for instance in self.sql_instances:
                lines.extend(
                    [
                        f"### Instance: {instance.name}",
                        "",
                        f"- **Version**: {instance.version or 'Unknown'}",
                        f"- **Edition**: {instance.edition or 'Unknown'}",
                        f"- **TCP Port**: {instance.tcp_port or 1433}",
                        f"- **Service Account**: {instance.service_account or 'Unknown'}",
                        "",
                    ]
                )

                if instance.data_path:
                    lines.append(f"- **Data Path**: `{instance.data_path}`")
                if instance.log_path:
                    lines.append(f"- **Log Path**: `{instance.log_path}`")
                if instance.backup_path:
                    lines.append(f"- **Backup Path**: `{instance.backup_path}`")

                lines.extend(
                    [
                        "",
                        "**Post-Migration Actions**:",
                        "- Execute generated SQL reconfiguration script",
                        "- Update linked servers with new hostname",
                        "- Verify database connectivity from applications",
                        "- Review SQL Agent jobs for hardcoded paths",
                        "",
                        "---",
                        "",
                    ]
                )

        # General recommendations
        lines.extend(
            [
                "## General Post-Migration Checklist",
                "",
                "1. ✅ Review all findings above and address critical/high-risk items",
                "2. ✅ Ensure hardware dongles are passed through or network dongles are configured",
                "3. ✅ Update license server configurations (FlexLM, RLM, etc.)",
                "4. ✅ Execute SQL Server reconfiguration script (if applicable)",
                "5. ✅ Reactivate hardware-locked application licenses",
                "6. ✅ Test all critical applications",
                "7. ✅ Verify network connectivity to license servers",
                "",
            ]
        )

        return "\n".join(lines)


def generate_compatibility_report(
    hardware_apps: list[AppCompatFinding],
    license_services: list[AppCompatFinding],
    dongle_drivers: list[AppCompatFinding],
    sql_instances: list[SQLServerInstance],
    hostname: str = "Unknown",
) -> CompatibilityReport:
    """Generate comprehensive compatibility report from findings.

    Args:
        hardware_apps: Hardware-dependent application findings
        license_services: License service findings
        dongle_drivers: Dongle driver findings
        sql_instances: SQL Server instances
        hostname: Server hostname

    Returns:
        CompatibilityReport object
    """
    logger.info("Generating application compatibility report")

    report = CompatibilityReport(
        hostname=hostname,
        hardware_apps=hardware_apps,
        license_services=license_services,
        dongle_drivers=dongle_drivers,
        sql_instances=sql_instances,
    )

    # Calculate summary statistics
    all_findings = hardware_apps + license_services + dongle_drivers

    report.total_findings = len(all_findings)

    for finding in all_findings:
        if finding.risk_level == RiskLevel.CRITICAL:
            report.critical_findings += 1
        elif finding.risk_level == RiskLevel.HIGH:
            report.high_findings += 1
        elif finding.risk_level == RiskLevel.MEDIUM:
            report.medium_findings += 1
        elif finding.risk_level == RiskLevel.LOW:
            report.low_findings += 1

    logger.info(
        "Compatibility report generated: %d findings (%d critical, %d high)",
        report.total_findings,
        report.critical_findings,
        report.high_findings,
    )

    return report
