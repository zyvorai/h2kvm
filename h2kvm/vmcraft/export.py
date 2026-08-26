# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/export.py
"""
Export and reporting capabilities for VMCraft.

Provides multiple export formats for VM inspection data:
- JSON export for automation and integration
- YAML export for human-readable configuration
- CSV export for spreadsheet analysis
- HTML report generation for documentation
- Markdown report for README files

Features:
- Comprehensive VM profile export
- Security audit reports
- Comparison reports (diff between VMs)
- Custom templates
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging


class ExportManager:
    """
    Export manager for VMCraft inspection data.

    Handles exporting VM inspection results to various formats.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize export manager.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def export_json(self, data: dict[str, Any], output_path: str | Path) -> bool:
        """
        Export data to JSON format.

        Args:
            data: Data dictionary to export
            output_path: Output file path

        Returns:
            True if successful
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

            self.logger.info(f"Exported JSON to {output_path}")
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort export step, must not crash caller
            self.logger.exception(f"JSON export failed: {e}")
            return False

    def export_yaml(self, data: dict[str, Any], output_path: str | Path) -> bool:
        """
        Export data to YAML format.

        Args:
            data: Data dictionary to export
            output_path: Output file path

        Returns:
            True if successful
        """
        try:
            import yaml  # pylint: disable=import-outside-toplevel  # keep PyYAML an optional/lazy dependency

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            self.logger.info(f"Exported YAML to {output_path}")
            return True

        except ImportError:
            self.logger.exception("PyYAML not installed. Install with: pip install pyyaml")
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort export step, must not crash caller
            self.logger.exception(f"YAML export failed: {e}")
            return False

    def export_markdown_report(
        self, data: dict[str, Any], output_path: str | Path, title: str = "VM Inspection Report"
    ) -> bool:
        """
        Generate Markdown report.

        Args:
            data: Inspection data
            output_path: Output file path
            title: Report title

        Returns:
            True if successful
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            lines = []
            lines.append(f"# {title}\n")
            lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            lines.append("---\n")

            # OS Information
            if "os" in data:
                lines.append("## Operating System\n")
                os_info = data["os"]
                lines.append(f"- **Type**: {os_info.get('type', 'unknown')}")
                lines.append(f"- **Product**: {os_info.get('product', 'unknown')}")
                lines.append(f"- **Version**: {os_info.get('version', 'unknown')}")
                lines.append(f"- **Architecture**: {os_info.get('arch', 'unknown')}")
                lines.append("")

            # Containers
            if "containers" in data:
                lines.append("## Container Detection\n")
                containers = data["containers"]
                lines.append(f"- **Is Container**: {containers.get('is_container', False)}")
                if containers.get("container_type"):
                    lines.append(f"- **Type**: {containers['container_type']}")
                lines.append("")

            # Security
            if "security" in data:
                lines.append("## Security\n")
                sec = data["security"]
                if "selinux" in sec:
                    lines.append(f"- **SELinux**: {sec['selinux'].get('mode', 'disabled')}")
                if "apparmor" in sec:
                    lines.append(
                        f"- **AppArmor**: {'enabled' if sec['apparmor'].get('enabled') else 'disabled'}"
                    )
                lines.append("")

            # Write report
            with output_path.open("w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            self.logger.info(f"Exported Markdown report to {output_path}")
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort export step, must not crash caller
            self.logger.exception(f"Markdown export failed: {e}")
            return False

    def create_vm_profile(
        self,
        os_info: dict[str, Any],
        containers: dict[str, Any] | None = None,
        security: dict[str, Any] | None = None,
        packages: dict[str, Any] | None = None,
        performance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create comprehensive VM profile for export.

        Args:
            os_info: Operating system information
            containers: Container detection results
            security: Security analysis results
            packages: Package information
            performance: Performance metrics

        Returns:
            Complete VM profile dictionary
        """
        profile = {
            "generated_at": datetime.now().isoformat(),
            "vmcraft_version": "2.0.0",
            "os": os_info,
        }

        if containers:
            profile["containers"] = containers

        if security:
            profile["security"] = security

        if packages:
            profile["packages"] = packages

        if performance:
            profile["performance"] = performance

        return profile

    def compare_vms(self, vm1_profile: dict[str, Any], vm2_profile: dict[str, Any]) -> dict[str, Any]:
        """
        Compare two VM profiles and generate diff report.

        Args:
            vm1_profile: First VM profile
            vm2_profile: Second VM profile

        Returns:
            Comparison results dictionary
        """
        comparison = {
            "vm1": vm1_profile.get("os", {}).get("product", "VM1"),
            "vm2": vm2_profile.get("os", {}).get("product", "VM2"),
            "differences": [],
            "similarities": [],
        }

        # Compare OS
        os1 = vm1_profile.get("os", {})
        os2 = vm2_profile.get("os", {})

        if os1.get("type") != os2.get("type"):
            comparison["differences"].append(
                {
                    "category": "os_type",
                    "vm1": os1.get("type"),
                    "vm2": os2.get("type"),
                }
            )
        else:
            comparison["similarities"].append("Same OS type")

        # Compare package counts
        pkg1 = vm1_profile.get("packages", {}).get("total_count", 0)
        pkg2 = vm2_profile.get("packages", {}).get("total_count", 0)

        if abs(pkg1 - pkg2) > 10:
            comparison["differences"].append(
                {
                    "category": "package_count",
                    "vm1": pkg1,
                    "vm2": pkg2,
                    "delta": pkg2 - pkg1,
                }
            )

        return comparison
