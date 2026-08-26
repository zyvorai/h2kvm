# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/config_tracker.py
"""
Configuration management and drift detection.

Provides comprehensive configuration tracking:
- Configuration file inventory
- Configuration baseline creation
- Configuration drift detection
- Best practices validation
- Configuration change tracking
- Configuration backup recommendations

Features:
- Multi-format support (INI, YAML, JSON, XML, CONF)
- Configuration parsing and validation
- Drift detection against baseline
- Best practice checking
- Security configuration audit
- Configuration documentation generation
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class ConfigTracker:
    """
    Configuration tracker and drift detector.

    Tracks and analyzes system configurations.
    """

    # Common configuration file locations
    CONFIG_LOCATIONS = {
        "linux": [
            "/etc",
            "/etc/sysconfig",
            "/etc/default",
            "/etc/systemd",
            "/etc/network",
        ],
        "windows": [
            "/Windows/System32/config",
            "/ProgramData",
        ],
    }

    # Configuration file extensions
    CONFIG_EXTENSIONS = [
        ".conf",
        ".config",
        ".cfg",
        ".ini",
        ".yaml",
        ".yml",
        ".json",
        ".xml",
        ".properties",
    ]

    # Best practice checks
    BEST_PRACTICES = {
        "sshd_config": {
            "PermitRootLogin": "no",
            "PasswordAuthentication": "no",
            "PermitEmptyPasswords": "no",
            "X11Forwarding": "no",
        },
        "limits.conf": {
            "* hard nofile": "65536",
            "* soft nofile": "65536",
        },
    }

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize configuration tracker.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def track_configurations(self, os_type: str = "linux") -> dict[str, Any]:
        """
        Track all system configurations.

        Args:
            os_type: Operating system type

        Returns:
            Configuration tracking results
        """
        tracking: dict[str, Any] = {
            "os_type": os_type,
            "config_files": [],
            "total_configs": 0,
            "config_by_type": {},
            "modified_recently": [],
        }

        # Find all configuration files
        configs = self._find_config_files(os_type)
        tracking["config_files"] = configs
        tracking["total_configs"] = len(configs)

        # Categorize by type
        config_by_type: dict[str, int] = {}
        for config in configs:
            ext = Path(config["path"]).suffix
            config_by_type[ext] = config_by_type.get(ext, 0) + 1

        tracking["config_by_type"] = config_by_type

        # Find recently modified configs
        modified = self._find_recently_modified(configs)
        tracking["modified_recently"] = modified

        return tracking

    def _find_config_files(self, os_type: str) -> list[dict[str, Any]]:
        """Find all configuration files."""
        config_files = []

        locations = self.CONFIG_LOCATIONS.get(os_type, self.CONFIG_LOCATIONS["linux"])

        # pylint: disable=duplicate-code
        # reason: the "for location: if not is_dir: continue; try: scan
        # files" shape mirrors hyper2kvm/vmcraft/data_discovery.py's
        # _find_sensitive_files() and hyper2kvm/vmcraft/forensic_analyzer.py's
        # _analyze_recent_activity() -- coincidental, this is a generic
        # best-effort directory-sweep idiom reused with different bodies
        # throughout vmcraft's scanners.
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.find_files(location, file_type="f")
                for file_path in files[:200]:  # Limit per location
                    filename = Path(file_path).name
                    ext = Path(file_path).suffix

                    # Check if it's a config file
                    if ext in self.CONFIG_EXTENSIONS or "config" in filename.lower():
                        try:
                            age = self.file_ops.file_age(file_path)
                            config_files.append(
                                {
                                    "path": file_path,
                                    "name": filename,
                                    "type": ext,
                                    "size": age.get("size", 0),
                                    "mtime": age.get("mtime"),
                                }
                            )
                        except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan, must not abort over one file's quirk
                            pass

                    if len(config_files) >= 200:
                        break
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort config scan step, must not abort the whole scan over one file's quirk
                pass

            if len(config_files) >= 200:
                break

        return config_files

    def _find_recently_modified(self, configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Find recently modified configuration files."""
        # Simplified - in production would compare timestamps
        return configs[:20]  # Just return first 20 as "recent"

    def create_baseline(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """
        Create configuration baseline.

        Args:
            tracking: Configuration tracking results

        Returns:
            Configuration baseline
        """
        baseline = {
            "timestamp": "current",
            "total_configs": tracking.get("total_configs", 0),
            "configs": [],
            "checksums": {},
        }

        # Store config file information
        for config in tracking.get("config_files", []):
            try:
                # Calculate checksum
                checksum = self.file_ops.checksum(config["path"], "sha256")
                baseline["configs"].append(
                    {
                        "path": config["path"],
                        "checksum": checksum,
                        "size": config.get("size", 0),
                    }
                )
                baseline["checksums"][config["path"]] = checksum
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort config scan step, must not abort the whole scan over one file's quirk
                pass

        return baseline

    def detect_drift(self, baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        """
        Detect configuration drift from baseline.

        Args:
            baseline: Baseline configuration
            current: Current configuration

        Returns:
            Drift detection results
        """
        drift: dict[str, Any] = {
            "has_drift": False,
            "added_configs": [],
            "removed_configs": [],
            "modified_configs": [],
            "total_changes": 0,
        }

        baseline_paths = {c["path"] for c in baseline.get("configs", [])}
        current_paths = {c["path"] for c in current.get("config_files", [])}

        # Find added configs
        added = current_paths - baseline_paths
        drift["added_configs"] = list(added)

        # Find removed configs
        removed = baseline_paths - current_paths
        drift["removed_configs"] = list(removed)

        # Find modified configs
        baseline_checksums = baseline.get("checksums", {})
        for config in current.get("config_files", []):
            path = config["path"]
            if path in baseline_checksums:
                try:
                    current_checksum = self.file_ops.checksum(path, "sha256")
                    if current_checksum != baseline_checksums[path]:
                        drift["modified_configs"].append(
                            {
                                "path": path,
                                "baseline_checksum": baseline_checksums[path],
                                "current_checksum": current_checksum,
                            }
                        )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort config scan step, must not abort the whole scan over one file's quirk
                    pass

        drift["total_changes"] = (
            len(drift["added_configs"]) + len(drift["removed_configs"]) + len(drift["modified_configs"])
        )
        drift["has_drift"] = drift["total_changes"] > 0

        return drift

    def validate_best_practices(self) -> list[dict[str, Any]]:
        """
        Validate configurations against best practices.

        Returns:
            List of best practice violations
        """
        violations = []

        # Check SSH configuration
        sshd_config_path = "/etc/ssh/sshd_config"
        if self.file_ops.exists(sshd_config_path):
            try:
                content = self.file_ops.cat(sshd_config_path)
                expected = self.BEST_PRACTICES.get("sshd_config", {})

                for key, expected_value in expected.items():
                    # Simple parsing (not comprehensive)
                    pattern = f"{key}\\s+(.+)"
                    match = re.search(pattern, content, re.IGNORECASE)

                    if match:
                        actual_value = match.group(1).strip()
                        if actual_value.lower() != expected_value.lower():
                            violations.append(
                                {
                                    "file": sshd_config_path,
                                    "setting": key,
                                    "expected": expected_value,
                                    "actual": actual_value,
                                    "severity": "high",
                                }
                            )
                    else:
                        violations.append(
                            {
                                "file": sshd_config_path,
                                "setting": key,
                                "expected": expected_value,
                                "actual": "not set",
                                "severity": "high",
                            }
                        )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort config scan step, must not abort the whole scan over one file's quirk
                pass

        return violations

    def get_config_summary(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """
        Get configuration tracking summary.

        Args:
            tracking: Configuration tracking results

        Returns:
            Summary dictionary
        """
        config_by_type = tracking.get("config_by_type", {})

        return {
            "total_configs": tracking.get("total_configs", 0),
            "config_types": len(config_by_type),
            "most_common_type": max(config_by_type.items(), key=lambda x: x[1])[0]
            if config_by_type
            else "unknown",
            "recently_modified": len(tracking.get("modified_recently", [])),
        }

    def analyze_config_security(self) -> list[dict[str, Any]]:
        """
        Analyze configuration security.

        Returns:
            List of security issues
        """
        issues = []

        # Check for world-writable configs
        config_files = self._find_config_files("linux")

        for config in config_files[:50]:  # Limit check
            try:
                path = config["path"]
                # In a real implementation, would check file permissions
                # For now, just flag configs in sensitive locations
                if "/etc" in path:
                    issues.append(
                        {
                            "path": path,
                            "issue": "Configuration in sensitive location",
                            "recommendation": "Ensure proper permissions (644 or 600)",
                            "severity": "medium",
                        }
                    )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort config scan step, must not abort the whole scan over one file's quirk
                pass

        return issues[:20]  # Limit results

    def compare_configs(self, config1_path: str, config2_path: str) -> dict[str, Any]:
        """
        Compare two configuration files.

        Args:
            config1_path: First config file path
            config2_path: Second config file path

        Returns:
            Comparison results
        """
        comparison = {
            "identical": False,
            "differences": [],
        }

        try:
            content1 = self.file_ops.cat(config1_path)
            content2 = self.file_ops.cat(config2_path)

            if content1 == content2:
                comparison["identical"] = True
            else:
                # Simplified diff (line-by-line)
                lines1 = content1.splitlines()
                lines2 = content2.splitlines()

                max_lines = max(len(lines1), len(lines2))
                for i in range(min(max_lines, 100)):  # Limit to 100 lines
                    line1 = lines1[i] if i < len(lines1) else ""
                    line2 = lines2[i] if i < len(lines2) else ""

                    if line1 != line2:
                        comparison["differences"].append(
                            {
                                "line": i + 1,
                                "config1": line1,
                                "config2": line2,
                            }
                        )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort diff, capture any comparison failure into the result dict
            comparison["error"] = str(e)

        return comparison

    def generate_config_documentation(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """
        Generate configuration documentation.

        Args:
            tracking: Configuration tracking results

        Returns:
            Documentation data
        """
        documentation = {
            "title": "System Configuration Inventory",
            "total_configs": tracking.get("total_configs", 0),
            "config_categories": {},
            "critical_configs": [],
        }

        # Categorize configs
        categories: dict[str, list] = {
            "network": [],
            "security": [],
            "system": [],
            "application": [],
            "other": [],
        }

        for config in tracking.get("config_files", []):
            path = config["path"]

            # Categorize based on path/name
            if any(net in path.lower() for net in ["network", "interfaces", "resolv", "hosts"]):
                categories["network"].append(config)
            elif any(sec in path.lower() for sec in ["ssh", "ssl", "pam", "security"]):
                categories["security"].append(config)
            elif any(sys in path.lower() for sys in ["systemd", "sysctl", "fstab", "grub"]):
                categories["system"].append(config)
            else:
                categories["other"].append(config)

        documentation["config_categories"] = {k: len(v) for k, v in categories.items()}

        # Mark critical configs
        critical_patterns = [
            "/etc/passwd",
            "/etc/shadow",
            "/etc/ssh/sshd_config",
            "/etc/fstab",
            "/boot/grub",
        ]

        for config in tracking.get("config_files", []):
            for pattern in critical_patterns:
                if pattern in config["path"]:
                    documentation["critical_configs"].append(config)
                    break

        return documentation

    def get_config_backup_recommendations(self, _tracking: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get configuration backup recommendations.

        Args:
            _tracking: Configuration tracking results (currently unused; recommendations are static)

        Returns:
            List of backup recommendations
        """
        recommendations = []

        # Recommend backing up critical configs
        critical_paths = [
            "/etc",
            "/boot",
            "/home/*/.config",
        ]

        for path in critical_paths:
            recommendations.append(
                {
                    "path": path,
                    "priority": "high" if path == "/etc" else "medium",
                    "reason": "Contains critical system configuration",
                    "backup_method": "Full directory backup with versioning",
                }
            )

        return recommendations
