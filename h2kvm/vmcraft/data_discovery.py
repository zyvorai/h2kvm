# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/data_discovery.py
"""
Data discovery and sensitive information detection.

Provides comprehensive data discovery:
- PII (Personally Identifiable Information) detection
- Credit card number detection
- API key and secret detection
- Database connection string detection
- Password file detection
- SSH key detection
- Data classification (public, internal, confidential, restricted)

Features:
- Pattern-based detection (regex)
- File content scanning
- Configuration file analysis
- Credential detection
- Sensitive data inventory
- Privacy compliance support (GDPR, CCPA)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class DataDiscovery:
    """
    Data discovery and sensitive information detector.

    Scans filesystem for sensitive data and credentials.
    """

    # Credit card patterns (Luhn algorithm not implemented here)
    CREDIT_CARD_PATTERNS = [
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?)\b",  # Visa
        r"\b(?:5[1-5][0-9]{14})\b",  # MasterCard
        r"\b(?:3[47][0-9]{13})\b",  # American Express
        r"\b(?:6(?:011|5[0-9]{2})[0-9]{12})\b",  # Discover
    ]

    # Social Security Number patterns
    SSN_PATTERNS = [
        r"\b\d{3}-\d{2}-\d{4}\b",  # XXX-XX-XXXX
        r"\b\d{9}\b",  # XXXXXXXXX (less precise)
    ]

    # Email patterns
    EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

    # API key patterns
    API_KEY_PATTERNS = [
        r"api[_-]?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?",
        r"apikey['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?",
        r"api[_-]?secret['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?",
        r"client[_-]?secret['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?",
    ]

    # AWS credentials
    AWS_KEY_PATTERNS = [
        r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID
        r"aws[_-]?secret[_-]?access[_-]?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
    ]

    # Database connection strings
    DB_CONNECTION_PATTERNS = [
        r"postgres://[^:]+:[^@]+@[^/]+/\w+",
        r"mysql://[^:]+:[^@]+@[^/]+/\w+",
        r"mongodb://[^:]+:[^@]+@[^/]+/\w+",
        r"jdbc:[^:]+://[^:]+:[^@]+@[^/]+:\d+/\w+",
    ]

    # Password patterns in config files
    PASSWORD_PATTERNS = [
        r"password['\"]?\s*[:=]\s*['\"]?([^'\"\\s]{6,})['\"]?",
        r"passwd['\"]?\s*[:=]\s*['\"]?([^'\"\\s]{6,})['\"]?",
        r"pwd['\"]?\s*[:=]\s*['\"]?([^'\"\\s]{6,})['\"]?",
    ]

    # Private key indicators
    PRIVATE_KEY_INDICATORS = [
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN DSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
    ]

    # Sensitive file patterns
    SENSITIVE_FILES = [
        r".*\.pem$",
        r".*\.key$",
        r".*\.p12$",
        r".*\.pfx$",
        r".*\.jks$",
        r".*id_rsa$",
        r".*id_dsa$",
        r".*\.ppk$",
        r".*password.*\.txt$",
        r".*credentials.*",
        r".*\.env$",
        r".*\.ini$",
        r".*\.conf$",
    ]

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize data discovery.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def discover_sensitive_data(self) -> dict[str, Any]:
        """
        Discover sensitive data comprehensively.

        Returns:
            Sensitive data discovery results
        """
        discovery: dict[str, Any] = {
            "pii_findings": [],
            "credentials": [],
            "api_keys": [],
            "private_keys": [],
            "database_connections": [],
            "sensitive_files": [],
            "total_findings": 0,
            "risk_level": "unknown",
        }

        # Scan for PII
        pii = self._scan_pii()
        discovery["pii_findings"] = pii

        # Scan for credentials
        creds = self._scan_credentials()
        discovery["credentials"] = creds

        # Scan for API keys
        api_keys = self._scan_api_keys()
        discovery["api_keys"] = api_keys

        # Scan for private keys
        private_keys = self._scan_private_keys()
        discovery["private_keys"] = private_keys

        # Scan for database connections
        db_connections = self._scan_database_connections()
        discovery["database_connections"] = db_connections

        # Find sensitive files
        sensitive_files = self._find_sensitive_files()
        discovery["sensitive_files"] = sensitive_files

        # Calculate total and risk
        discovery["total_findings"] = (
            len(pii)
            + len(creds)
            + len(api_keys)
            + len(private_keys)
            + len(db_connections)
            + len(sensitive_files)
        )

        discovery["risk_level"] = self._calculate_risk_level(discovery)

        return discovery

    # pylint: disable-next=too-many-branches
    def _scan_pii(self) -> list[dict[str, Any]]:
        """Scan for PII (Personally Identifiable Information)."""
        pii = []

        # Common locations for PII
        locations = [
            "/home",
            "/Users",
            "/var/www",
            "/opt",
        ]

        # Nested location/file/pattern loops with per-level best-effort try/except are inherent
        # to a best-effort filesystem content scan across several PII categories.
        # pylint: disable=too-many-nested-blocks
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.find_files(location, pattern="*.txt")
                for file_path in files[:50]:  # Limit per location
                    try:
                        # Read small files only
                        content = self.file_ops.cat(file_path)
                        if len(content) > 100000:  # Skip large files
                            continue

                        # Check for credit cards
                        for pattern in self.CREDIT_CARD_PATTERNS:
                            matches = re.findall(pattern, content)
                            if matches:
                                pii.append(
                                    {
                                        "type": "credit_card",
                                        "path": file_path,
                                        "count": len(matches),
                                        "severity": "critical",
                                    }
                                )

                        # Check for SSN
                        for pattern in self.SSN_PATTERNS:
                            matches = re.findall(pattern, content)
                            if matches and len(matches[0]) == 11:  # XXX-XX-XXXX format
                                pii.append(
                                    {
                                        "type": "ssn",
                                        "path": file_path,
                                        "count": len(matches),
                                        "severity": "critical",
                                    }
                                )

                        # Check for emails (less sensitive but still PII)
                        emails = re.findall(self.EMAIL_PATTERN, content)
                        if len(emails) > 10:  # Only if many emails found
                            pii.append(
                                {
                                    "type": "email_addresses",
                                    "path": file_path,
                                    "count": len(emails),
                                    "severity": "medium",
                                }
                            )

                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file read/scan is best-effort; a bad file must not abort the scan.
                        pass

                    if len(pii) >= 100:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Per-location scan is best-effort; a bad location must not abort discovery.
                pass

            if len(pii) >= 100:
                break
        # pylint: enable=too-many-nested-blocks

        return pii

    def _scan_credentials(self) -> list[dict[str, Any]]:
        """Scan for credentials in configuration files."""
        credentials = []

        # Common configuration file locations
        config_locations = [
            "/etc",
            "/opt",
            "/home/*/.config",
            "/root/.config",
        ]

        # Nested location/file loops with per-level best-effort try/except are inherent to a
        # best-effort filesystem content scan across several config-file locations.
        # pylint: disable=too-many-nested-blocks
        for location in config_locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                # Find config files
                config_files = self.file_ops.find_files(location, pattern="*.conf")
                config_files.extend(self.file_ops.find_files(location, pattern="*.ini"))
                config_files.extend(self.file_ops.find_files(location, pattern="*.env"))

                for file_path in config_files[:50]:
                    try:
                        content = self.file_ops.cat(file_path)
                        if len(content) > 50000:  # Skip large files
                            continue

                        # Check for passwords
                        for pattern in self.PASSWORD_PATTERNS:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                credentials.append(
                                    {
                                        "type": "password",
                                        "path": file_path,
                                        "count": len(matches),
                                        "severity": "high",
                                    }
                                )
                                break

                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file read/scan is best-effort; a bad file must not abort the scan.
                        pass

                    if len(credentials) >= 50:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Per-location scan is best-effort; a bad location must not abort discovery.
                pass

            if len(credentials) >= 50:
                break
        # pylint: enable=too-many-nested-blocks

        return credentials

    def _scan_api_keys(self) -> list[dict[str, Any]]:
        """Scan for API keys and secrets."""
        api_keys = []

        # Common locations for API keys
        locations = [
            "/home",
            "/root",
            "/opt",
            "/var/www",
        ]

        # Nested location/file loops with per-level best-effort try/except are inherent to a
        # best-effort filesystem content scan across several key/secret patterns.
        # pylint: disable=too-many-nested-blocks
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                # Find potential config files
                files = self.file_ops.find_files(location, pattern="*.env")
                files.extend(self.file_ops.find_files(location, pattern="*.conf"))
                files.extend(self.file_ops.find_files(location, pattern="*.ini"))

                for file_path in files[:50]:
                    try:
                        content = self.file_ops.cat(file_path)
                        if len(content) > 50000:
                            continue

                        # Check for API keys
                        for pattern in self.API_KEY_PATTERNS:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                api_keys.append(
                                    {
                                        "type": "api_key",
                                        "path": file_path,
                                        "count": len(matches),
                                        "severity": "high",
                                    }
                                )
                                break

                        # Check for AWS keys
                        for pattern in self.AWS_KEY_PATTERNS:
                            matches = re.findall(pattern, content)
                            if matches:
                                api_keys.append(
                                    {
                                        "type": "aws_key",
                                        "path": file_path,
                                        "count": len(matches),
                                        "severity": "critical",
                                    }
                                )
                                break

                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file read/scan is best-effort; a bad file must not abort the scan.
                        pass

                    if len(api_keys) >= 50:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Per-location scan is best-effort; a bad location must not abort discovery.
                pass

            if len(api_keys) >= 50:
                break
        # pylint: enable=too-many-nested-blocks

        return api_keys

    def _scan_private_keys(self) -> list[dict[str, Any]]:
        """Scan for private keys."""
        private_keys = []

        # SSH key locations
        ssh_locations = [
            "/root/.ssh",
            "/home/*/.ssh",
            "/Users/*/.ssh",
        ]

        # Nested location/file loops with per-level best-effort try/except are inherent to a
        # best-effort filesystem scan for SSH private key files and content markers.
        # pylint: disable=too-many-nested-blocks
        # pylint: disable=duplicate-code
        # reason: the "for location: if not is_dir: continue; try: scan files"
        # shape mirrors h2kvm/vmcraft/forensic_analyzer.py's
        # _detect_hidden_files() -- coincidental, this is a generic
        # best-effort directory-sweep idiom reused with different bodies
        # throughout vmcraft's scanners.
        for location in ssh_locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.ls(location)
                for filename in files:
                    file_path = f"{location}/{filename}"

                    # Check for key files
                    if any(filename.endswith(ext) for ext in ["id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"]):
                        private_keys.append(
                            {
                                "type": "ssh_private_key",
                                "path": file_path,
                                "severity": "high",
                            }
                        )

                    # Check content for private key markers
                    try:
                        content = self.file_ops.cat(file_path)
                        for indicator in self.PRIVATE_KEY_INDICATORS:
                            if indicator in content:
                                private_keys.append(
                                    {
                                        "type": "private_key",
                                        "path": file_path,
                                        "key_type": indicator.split()[1].lower(),
                                        "severity": "high",
                                    }
                                )
                                break
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file read/scan is best-effort; a bad file must not abort the scan.
                        pass

                    if len(private_keys) >= 50:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Per-location scan is best-effort; a bad location must not abort discovery.
                pass

            if len(private_keys) >= 50:
                break
        # pylint: enable=too-many-nested-blocks

        return private_keys

    def _scan_database_connections(self) -> list[dict[str, Any]]:
        """Scan for database connection strings."""
        db_connections = []

        # Common application config locations
        locations = [
            "/opt",
            "/var/www",
            "/home",
            "/etc",
        ]

        # Nested location/file loops with per-level best-effort try/except are inherent to a
        # best-effort filesystem content scan across several application config locations.
        # pylint: disable=too-many-nested-blocks
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                config_files = self.file_ops.find_files(location, pattern="*.conf")
                config_files.extend(self.file_ops.find_files(location, pattern="*.ini"))
                config_files.extend(self.file_ops.find_files(location, pattern="*.env"))

                for file_path in config_files[:50]:
                    try:
                        content = self.file_ops.cat(file_path)
                        if len(content) > 50000:
                            continue

                        # Check for database connection strings
                        for pattern in self.DB_CONNECTION_PATTERNS:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                db_connections.append(
                                    {
                                        "type": "database_connection",
                                        "path": file_path,
                                        "count": len(matches),
                                        "severity": "high",
                                    }
                                )
                                break

                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file read/scan is best-effort; a bad file must not abort the scan.
                        pass

                    if len(db_connections) >= 50:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Per-location scan is best-effort; a bad location must not abort discovery.
                pass

            if len(db_connections) >= 50:
                break
        # pylint: enable=too-many-nested-blocks

        return db_connections

    def _find_sensitive_files(self) -> list[dict[str, Any]]:
        """Find sensitive files by pattern."""
        sensitive = []

        # Scan common locations
        locations = ["/", "/home", "/root", "/opt", "/etc"]

        # pylint: disable=duplicate-code
        # reason: the "for location: if not is_dir: continue; try: scan files"
        # shape mirrors h2kvm/vmcraft/forensic_analyzer.py's
        # _analyze_recent_activity() and h2kvm/vmcraft/config_tracker.py's
        # _find_config_files() -- coincidental, this is a generic best-effort
        # directory-sweep idiom reused with different bodies throughout
        # vmcraft's scanners.
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.find_files(location, file_type="f")
                for file_path in files[:100]:
                    filename = Path(file_path).name

                    # Check against sensitive patterns
                    for pattern in self.SENSITIVE_FILES:
                        if re.match(pattern, filename, re.IGNORECASE):
                            sensitive.append(
                                {
                                    "path": file_path,
                                    "pattern": pattern,
                                    "severity": "medium",
                                }
                            )
                            break

                    if len(sensitive) >= 100:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Per-location scan is best-effort; a bad location must not abort discovery.
                pass

            if len(sensitive) >= 100:
                break

        return sensitive

    def _calculate_risk_level(self, discovery: dict[str, Any]) -> str:
        """Calculate overall risk level."""
        pii_count = len(discovery.get("pii_findings", []))
        creds_count = len(discovery.get("credentials", []))
        api_keys_count = len(discovery.get("api_keys", []))
        private_keys_count = len(discovery.get("private_keys", []))

        # Critical if PII or AWS keys found
        if pii_count > 0:
            return "critical"

        # High if credentials or API keys found
        if creds_count > 5 or api_keys_count > 0:
            return "high"

        # Medium if private keys or some credentials found
        if private_keys_count > 0 or creds_count > 0:
            return "medium"

        # Low if only sensitive files found
        if len(discovery.get("sensitive_files", [])) > 0:
            return "low"

        return "minimal"

    def get_discovery_summary(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """
        Get data discovery summary.

        Args:
            discovery: Discovery results

        Returns:
            Summary dictionary
        """
        return {
            "total_findings": discovery.get("total_findings", 0),
            "pii_count": len(discovery.get("pii_findings", [])),
            "credentials_count": len(discovery.get("credentials", [])),
            "api_keys_count": len(discovery.get("api_keys", [])),
            "private_keys_count": len(discovery.get("private_keys", [])),
            "db_connections_count": len(discovery.get("database_connections", [])),
            "sensitive_files_count": len(discovery.get("sensitive_files", [])),
            "risk_level": discovery.get("risk_level", "unknown"),
        }

    def classify_data_sensitivity(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """
        Classify discovered data by sensitivity level.

        Args:
            discovery: Discovery results

        Returns:
            Data classification
        """
        classification = {
            "restricted": [],  # PII, credit cards
            "confidential": [],  # Passwords, API keys
            "internal": [],  # DB connections
            "public": [],  # Everything else
        }

        # Classify PII as restricted
        for finding in discovery.get("pii_findings", []):
            classification["restricted"].append(finding)

        # Classify credentials and API keys as confidential
        for finding in discovery.get("credentials", []):
            classification["confidential"].append(finding)
        for finding in discovery.get("api_keys", []):
            classification["confidential"].append(finding)

        # Classify DB connections and private keys as internal
        for finding in discovery.get("database_connections", []):
            classification["internal"].append(finding)
        for finding in discovery.get("private_keys", []):
            classification["internal"].append(finding)

        return classification

    def get_compliance_report(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """
        Generate compliance report (GDPR, CCPA).

        Args:
            discovery: Discovery results

        Returns:
            Compliance report
        """
        report = {
            "gdpr_concerns": [],
            "ccpa_concerns": [],
            "compliance_score": 0,
        }

        # GDPR concerns (PII found)
        pii_findings = discovery.get("pii_findings", [])
        if pii_findings:
            report["gdpr_concerns"].append(
                {
                    "issue": f"{len(pii_findings)} PII findings detected",
                    "recommendation": "Ensure data is encrypted and access-controlled",
                }
            )

        # CCPA concerns (California consumer data)
        if pii_findings:
            report["ccpa_concerns"].append(
                {
                    "issue": f"{len(pii_findings)} personal information findings",
                    "recommendation": "Implement data protection measures",
                }
            )

        # Calculate compliance score (0-100)
        total_findings = discovery.get("total_findings", 0)
        if total_findings == 0:
            report["compliance_score"] = 100
        elif total_findings < 5:
            report["compliance_score"] = 80
        elif total_findings < 20:
            report["compliance_score"] = 60
        else:
            report["compliance_score"] = 40

        return report
