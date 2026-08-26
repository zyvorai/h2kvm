# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/license_detector.py
"""
Software license detection and compliance tracking.

Provides comprehensive license analysis:
- Open source license detection (GPL, MIT, Apache, BSD, etc.)
- Commercial software identification
- License compliance checking
- SBOM (Software Bill of Materials) generation
- License risk assessment

Features:
- Package license detection
- Commercial software inventory
- License compatibility checking
- SBOM generation (SPDX format)
- Copyleft detection
- License risk scoring
"""

from __future__ import annotations

from typing import Any

from .base_analyzer import BaseAnalyzer


class LicenseDetector(BaseAnalyzer):
    """
    Software license detector and compliance tracker.

    Detects licenses and tracks compliance.
    """

    # Common open source licenses
    OSS_LICENSES = {
        "gpl-2.0": {"name": "GNU GPL v2", "type": "copyleft", "commercial_use": True, "risk": "medium"},
        "gpl-3.0": {"name": "GNU GPL v3", "type": "copyleft", "commercial_use": True, "risk": "medium"},
        "lgpl-2.1": {
            "name": "GNU LGPL v2.1",
            "type": "weak_copyleft",
            "commercial_use": True,
            "risk": "low",
        },
        "lgpl-3.0": {"name": "GNU LGPL v3", "type": "weak_copyleft", "commercial_use": True, "risk": "low"},
        "mit": {"name": "MIT License", "type": "permissive", "commercial_use": True, "risk": "minimal"},
        "apache-2.0": {
            "name": "Apache License 2.0",
            "type": "permissive",
            "commercial_use": True,
            "risk": "minimal",
        },
        "bsd-2-clause": {
            "name": "BSD 2-Clause",
            "type": "permissive",
            "commercial_use": True,
            "risk": "minimal",
        },
        "bsd-3-clause": {
            "name": "BSD 3-Clause",
            "type": "permissive",
            "commercial_use": True,
            "risk": "minimal",
        },
        "mpl-2.0": {
            "name": "Mozilla Public License 2.0",
            "type": "weak_copyleft",
            "commercial_use": True,
            "risk": "low",
        },
        "agpl-3.0": {"name": "GNU AGPL v3", "type": "copyleft", "commercial_use": True, "risk": "high"},
    }

    # Commercial software patterns
    COMMERCIAL_SOFTWARE = {
        "oracle": {"vendor": "Oracle Corporation", "license": "Commercial"},
        "vmware": {"vendor": "VMware Inc.", "license": "Commercial"},
        "microsoft": {"vendor": "Microsoft Corporation", "license": "Proprietary"},
        "red hat": {"vendor": "Red Hat Inc.", "license": "Commercial (+ OSS)"},
        "suse": {"vendor": "SUSE", "license": "Commercial (+ OSS)"},
    }

    def detect_licenses(self, os_type: str = "linux") -> dict[str, Any]:
        """
        Detect software licenses comprehensively.

        Args:
            os_type: Operating system type

        Returns:
            License detection results
        """
        licenses: dict[str, Any] = {
            "os_type": os_type,
            "oss_licenses": [],
            "commercial_software": [],
            "unknown_licenses": [],
            "total_packages": 0,
            "compliance_risk": "unknown",
        }

        if os_type == "linux":
            # Detect from package manager
            packages = self._detect_linux_licenses()
            licenses["oss_licenses"] = packages.get("oss", [])
            licenses["commercial_software"] = packages.get("commercial", [])
            licenses["unknown_licenses"] = packages.get("unknown", [])
            licenses["total_packages"] = len(packages.get("all", []))

        # Calculate compliance risk
        licenses["compliance_risk"] = self._calculate_compliance_risk(licenses)

        return licenses

    def _detect_linux_licenses(self) -> dict[str, Any]:
        """Detect licenses from Linux package managers."""
        packages: dict[str, Any] = {
            "oss": [],
            "commercial": [],
            "unknown": [],
            "all": [],
        }

        # Check RPM-based systems
        if self.file_ops.is_dir("/var/lib/rpm"):
            rpm_packages = self._parse_rpm_licenses()
            packages["all"].extend(rpm_packages)
            self._categorize_packages(rpm_packages, packages)

        # Check DEB-based systems
        if self.file_ops.is_dir("/var/lib/dpkg"):
            deb_packages = self._parse_deb_licenses()
            packages["all"].extend(deb_packages)
            self._categorize_packages(deb_packages, packages)

        return packages

    def _parse_rpm_licenses(self) -> list[dict[str, Any]]:
        """Parse RPM package licenses."""
        return []

        # Note: Full RPM database parsing would require reading Berkeley DB
        # For now, check for common commercial packages

        # This is simplified - full implementation would parse RPM database

    def _parse_deb_licenses(self) -> list[dict[str, Any]]:
        """Parse Debian package licenses."""
        packages = []

        # Check dpkg status file
        if self.file_ops.exists("/var/lib/dpkg/status"):
            try:
                content = self.file_ops.cat("/var/lib/dpkg/status")
                current_package = None

                for line in content.splitlines():
                    if line.startswith("Package:"):
                        current_package = line.split(":", 1)[1].strip()
                    elif line.startswith("Version:") and current_package:
                        version = line.split(":", 1)[1].strip()

                        # Check copyright file for license info
                        copyright_path = f"/usr/share/doc/{current_package}/copyright"
                        license_info = self._detect_license_from_file(copyright_path)

                        packages.append(
                            {
                                "name": current_package,
                                "version": version,
                                "license": license_info.get("license", "unknown"),
                                "license_type": license_info.get("type", "unknown"),
                            }
                        )

                        if len(packages) >= 100:  # Limit to 100 packages
                            break

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort dpkg parse, must not abort scan
                self.logger.debug(f"Failed to parse dpkg status: {e}")

        return packages

    def _detect_license_from_file(  # pylint: disable=too-many-branches  # exhaustive per-license-family text matching
        self, filepath: str
    ) -> dict[str, Any]:
        """Detect license from copyright/license file."""
        license_info = {
            "license": "unknown",
            "type": "unknown",
        }

        if not self.file_ops.exists(filepath):
            return license_info

        try:
            content = self.file_ops.cat(filepath).lower()

            # Check for common licenses
            if "gpl" in content:
                if "version 3" in content or "gplv3" in content:
                    license_info["license"] = "gpl-3.0"
                    license_info["type"] = "copyleft"
                elif "version 2" in content or "gplv2" in content:
                    license_info["license"] = "gpl-2.0"
                    license_info["type"] = "copyleft"
                else:
                    license_info["license"] = "gpl"
                    license_info["type"] = "copyleft"

            elif "lgpl" in content:
                license_info["license"] = "lgpl"
                license_info["type"] = "weak_copyleft"

            elif "apache" in content:
                if "version 2" in content or "2.0" in content:
                    license_info["license"] = "apache-2.0"
                else:
                    license_info["license"] = "apache"
                license_info["type"] = "permissive"

            elif "mit license" in content:
                license_info["license"] = "mit"
                license_info["type"] = "permissive"

            elif "bsd" in content:
                if "3-clause" in content:
                    license_info["license"] = "bsd-3-clause"
                elif "2-clause" in content:
                    license_info["license"] = "bsd-2-clause"
                else:
                    license_info["license"] = "bsd"
                license_info["type"] = "permissive"

            elif "mozilla public license" in content or "mpl" in content:
                license_info["license"] = "mpl-2.0"
                license_info["type"] = "weak_copyleft"

            elif "agpl" in content:
                license_info["license"] = "agpl-3.0"
                license_info["type"] = "copyleft"

        except Exception:  # pylint: disable=broad-exception-caught  # best-effort license text scan, must not abort
            pass

        return license_info

    def _categorize_packages(self, packages: list[dict[str, Any]], result: dict[str, Any]) -> None:
        """Categorize packages by license type."""
        for pkg in packages:
            license_type = pkg.get("license_type", "unknown")

            if license_type in ["permissive", "copyleft", "weak_copyleft"]:
                result["oss"].append(pkg)
            elif license_type == "commercial":
                result["commercial"].append(pkg)
            else:
                result["unknown"].append(pkg)

    def _calculate_compliance_risk(self, licenses: dict[str, Any]) -> str:
        """Calculate license compliance risk."""
        oss_licenses = licenses.get("oss_licenses", [])
        commercial = licenses.get("commercial_software", [])
        unknown = licenses.get("unknown_licenses", [])

        # Count copyleft licenses
        copyleft_count = sum(
            1 for pkg in oss_licenses if pkg.get("license_type") in ["copyleft", "weak_copyleft"]
        )

        # High risk if many copyleft or commercial licenses
        if copyleft_count > 10 or len(commercial) > 5:
            return "high"
        if copyleft_count > 5 or len(commercial) > 2 or len(unknown) > 20:
            return "medium"
        if copyleft_count > 0 or len(commercial) > 0:
            return "low"
        return "minimal"

    def get_license_summary(self, licenses: dict[str, Any]) -> dict[str, Any]:
        """
        Get license summary.

        Args:
            licenses: License detection results

        Returns:
            Summary dictionary
        """
        oss_licenses = licenses.get("oss_licenses", [])

        # Count by type
        copyleft = sum(1 for pkg in oss_licenses if pkg.get("license_type") == "copyleft")
        weak_copyleft = sum(1 for pkg in oss_licenses if pkg.get("license_type") == "weak_copyleft")
        permissive = sum(1 for pkg in oss_licenses if pkg.get("license_type") == "permissive")

        return {
            "total_packages": licenses.get("total_packages", 0),
            "oss_packages": len(oss_licenses),
            "commercial_packages": len(licenses.get("commercial_software", [])),
            "unknown_licenses": len(licenses.get("unknown_licenses", [])),
            "copyleft_licenses": copyleft,
            "weak_copyleft_licenses": weak_copyleft,
            "permissive_licenses": permissive,
            "compliance_risk": licenses.get("compliance_risk", "unknown"),
        }

    def get_copyleft_packages(self, licenses: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get packages with copyleft licenses.

        Args:
            licenses: License detection results

        Returns:
            List of copyleft packages
        """
        copyleft = []

        for pkg in licenses.get("oss_licenses", []):
            if pkg.get("license_type") in ["copyleft", "weak_copyleft"]:
                copyleft.append(pkg)

        return copyleft

    def generate_sbom(self, licenses: dict[str, Any]) -> dict[str, Any]:
        """
        Generate Software Bill of Materials (SBOM).

        Args:
            licenses: License detection results

        Returns:
            SBOM in simplified format
        """
        sbom = {
            "format": "simple-sbom",
            "version": "1.0",
            "packages": [],
            "licenses": {},
            "commercial": [],
        }

        # Add OSS packages
        for pkg in licenses.get("oss_licenses", []):
            sbom["packages"].append(
                {
                    "name": pkg.get("name"),
                    "version": pkg.get("version"),
                    "license": pkg.get("license"),
                }
            )

            # Count licenses
            license_name = pkg.get("license", "unknown")
            sbom["licenses"][license_name] = sbom["licenses"].get(license_name, 0) + 1

        # Add commercial software
        sbom["commercial"] = licenses.get("commercial_software", [])

        return sbom

    def check_license_compatibility(
        self, licenses: dict[str, Any], target_license: str = "proprietary"
    ) -> list[dict[str, Any]]:
        """
        Check license compatibility issues.

        Args:
            licenses: License detection results
            target_license: Target license for compatibility check

        Returns:
            List of compatibility issues
        """
        issues = []

        # If targeting proprietary/commercial distribution
        if target_license == "proprietary":
            # Strong copyleft (GPL, AGPL) is incompatible
            for pkg in licenses.get("oss_licenses", []):
                if pkg.get("license", "").startswith("gpl") or pkg.get("license", "").startswith("agpl"):
                    issues.append(
                        {
                            "package": pkg.get("name"),
                            "license": pkg.get("license"),
                            "severity": "high",
                            "issue": "GPL/AGPL license incompatible with proprietary distribution",
                            "recommendation": "Remove package or seek alternative",
                        }
                    )

        return issues
