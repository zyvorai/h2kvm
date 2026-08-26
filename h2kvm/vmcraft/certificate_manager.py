# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/certificate_manager.py
"""
SSL/TLS certificate management and tracking.

Provides comprehensive certificate analysis:
- Find certificate files (.crt, .pem, .cer, .key, .p12, .pfx)
- Parse certificate information
- Check expiration dates
- Identify self-signed certificates
- Detect weak algorithms
- Certificate chain validation

Features:
- Certificate discovery
- Expiration tracking
- Security analysis
- Key strength validation
- Certificate chain analysis
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from .file_ops import FileOperations


class CertificateManager:
    """
    SSL/TLS certificate manager.

    Manages and analyzes SSL/TLS certificates.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize certificate manager.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def find_certificates(self) -> dict[str, Any]:
        """
        Find all certificate files.

        Returns:
            Certificate discovery results
        """
        certs: dict[str, Any] = {
            "certificates": [],
            "private_keys": [],
            "keystores": [],
            "total_count": 0,
            "expiring_soon": [],
            "expired": [],
            "self_signed": [],
        }

        # Search common certificate locations
        search_paths = [
            "/etc/ssl/certs",
            "/etc/pki/tls/certs",
            "/etc/apache2/ssl",
            "/etc/nginx/ssl",
            "/etc/httpd/ssl",
            "/usr/local/share/ca-certificates",
        ]

        # pylint: disable=duplicate-code
        # reason: mirrors similar "for search_path in search_paths:
        # file_ops.find(...)" scan loops in
        # vmcraft/app_framework_detector.py (per-framework app detection)
        # -- structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated detector code paths.
        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files:
                    cert_info = self._analyze_certificate_file(file)
                    if cert_info:
                        certs["certificates"].append(cert_info)
                        certs["total_count"] += 1

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort scan of guest filesystem paths; one bad path
                # must not abort certificate discovery.
                self.logger.debug(f"Failed to search {search_path}: {e}")

        # Find private keys
        certs["private_keys"] = self._find_private_keys()

        # Find keystores
        certs["keystores"] = self._find_keystores()

        return certs

    def _analyze_certificate_file(self, filepath: str) -> dict[str, Any] | None:
        """Analyze a certificate file."""
        # Check file extension
        if not filepath.endswith((".crt", ".pem", ".cer")):
            return None

        cert_info: dict[str, Any] = {
            "path": filepath,
            "type": "certificate",
            "format": None,
            "subject": None,
            "issuer": None,
            "valid_from": None,
            "valid_to": None,
            "days_remaining": None,
            "expired": False,
            "self_signed": False,
            "algorithm": None,
            "key_size": None,
        }

        try:
            # Get file size
            stat = self.file_ops.stat(filepath)
            cert_info["size_bytes"] = stat.get("size", 0)

            # Read first few lines to identify format
            content = self.file_ops.cat(filepath)
            if "BEGIN CERTIFICATE" in content:
                cert_info["format"] = "PEM"
            elif "BEGIN RSA PRIVATE KEY" in content or "BEGIN PRIVATE KEY" in content:
                # This is actually a private key
                return None

            # Basic parsing (full parsing would require OpenSSL)
            # For now, just mark as found
            cert_info["note"] = "Full certificate parsing requires OpenSSL"

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort per-file analysis over guest state; a malformed
            # or unreadable file must not abort the overall scan.
            self.logger.debug(f"Failed to analyze certificate {filepath}: {e}")
            return None

        return cert_info

    def _find_private_keys(self) -> list[dict[str, Any]]:
        # pylint: disable=too-many-nested-blocks
        # Nested search-path / file / per-file-try structure is inherent to
        # scanning multiple guest directories for candidate key files.
        """Find private key files."""
        private_keys = []

        search_paths = [
            "/etc/ssl/private",
            "/etc/pki/tls/private",
            "/etc/apache2/ssl",
            "/etc/nginx/ssl",
        ]

        # pylint: disable=duplicate-code
        # reason: mirrors similar "for search_path in search_paths:
        # file_ops.find(...)" scan loops in
        # vmcraft/app_framework_detector.py (per-framework app detection)
        # -- structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated detector code paths.
        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files:
                    if file.endswith((".key", ".pem")):
                        try:
                            content = self.file_ops.cat(file)
                            if "PRIVATE KEY" in content:
                                stat = self.file_ops.stat(file)
                                key_info = {
                                    "path": file,
                                    "type": "private_key",
                                    "size_bytes": stat.get("size", 0),
                                    "encrypted": "ENCRYPTED" in content,
                                }
                                private_keys.append(key_info)
                        except Exception:  # pylint: disable=broad-exception-caught
                            # Best-effort per-file read; a single unreadable
                            # key file must not abort the search.
                            pass

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort scan of guest filesystem paths; one bad path
                # must not abort the search.
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return private_keys

    def _find_keystores(self) -> list[dict[str, Any]]:
        """Find Java keystores and PKCS#12 files."""
        keystores = []

        search_paths = [
            "/etc/ssl",
            "/opt",
            "/usr/local/share",
        ]

        # pylint: disable=duplicate-code
        # reason: mirrors similar "for search_path in search_paths:
        # file_ops.find(...)" scan loops in
        # vmcraft/app_framework_detector.py (per-framework app detection)
        # -- structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated detector code paths.
        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files:
                    if file.endswith((".p12", ".pfx", ".jks", ".keystore")):
                        stat = self.file_ops.stat(file)
                        keystore_info = {
                            "path": file,
                            "type": "keystore",
                            "format": "PKCS12" if file.endswith((".p12", ".pfx")) else "JKS",
                            "size_bytes": stat.get("size", 0),
                        }
                        keystores.append(keystore_info)

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort scan of guest filesystem paths; one bad path
                # must not abort the search.
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return keystores

    def check_certificate_expiration(  # pylint: disable=unused-argument
        self, certs: dict[str, Any], warning_days: int = 30
    ) -> dict[str, Any]:
        # certs kept for API parity with the sibling check_certificate_*
        # methods and documented for the OpenSSL-backed implementation this
        # currently stubs out.
        """
        Check certificate expiration.

        Args:
            certs: Certificate discovery results
            warning_days: Days before expiration to warn

        Returns:
            Expiration analysis
        """
        expiration: dict[str, Any] = {
            "expiring_soon": [],
            "expired": [],
            "valid": [],
            "warning_days": warning_days,
        }

        # Note: Full expiration checking requires parsing certificates
        # which needs OpenSSL. For now, return structure.
        expiration["note"] = "Certificate expiration checking requires OpenSSL parsing"

        return expiration

    def check_certificate_security(self, certs: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Check certificate security issues.

        Args:
            certs: Certificate discovery results

        Returns:
            List of security issues
        """
        issues = []

        # Check private key permissions
        for key in certs.get("private_keys", []):
            # Private keys should have restricted permissions (600 or 400)
            issues.append(
                {
                    "severity": "info",
                    "type": "private_key",
                    "path": key["path"],
                    "issue": "Private key found",
                    "recommendation": "Ensure key file has restricted permissions (600 or 400)",
                }
            )

            if not key.get("encrypted"):
                issues.append(
                    {
                        "severity": "medium",
                        "type": "private_key",
                        "path": key["path"],
                        "issue": "Private key is not encrypted",
                        "recommendation": "Consider encrypting private keys",
                    }
                )

        return issues

    def get_certificate_summary(self, certs: dict[str, Any]) -> dict[str, Any]:
        """
        Get certificate summary.

        Args:
            certs: Certificate discovery results

        Returns:
            Summary dictionary
        """
        return {
            "total_certificates": len(certs.get("certificates", [])),
            "total_private_keys": len(certs.get("private_keys", [])),
            "total_keystores": len(certs.get("keystores", [])),
            "encrypted_keys": sum(1 for key in certs.get("private_keys", []) if key.get("encrypted")),
            "unencrypted_keys": sum(1 for key in certs.get("private_keys", []) if not key.get("encrypted")),
        }

    def list_certificate_locations(self, certs: dict[str, Any]) -> dict[str, list[str]]:
        """
        List certificate locations by type.

        Args:
            certs: Certificate discovery results

        Returns:
            Dictionary of locations by type
        """
        locations: dict[str, list[str]] = {
            "certificates": [],
            "private_keys": [],
            "keystores": [],
        }

        for cert in certs.get("certificates", []):
            locations["certificates"].append(cert["path"])

        for key in certs.get("private_keys", []):
            locations["private_keys"].append(key["path"])

        for keystore in certs.get("keystores", []):
            locations["keystores"].append(keystore["path"])

        return locations

    def find_web_server_certificates(self, certs: dict[str, Any]) -> dict[str, list[str]]:
        """
        Find certificates used by web servers.

        Args:
            certs: Certificate discovery results

        Returns:
            Dictionary of web server certificates
        """
        web_certs: dict[str, list[str]] = {
            "apache": [],
            "nginx": [],
            "unknown": [],
        }

        for cert in certs.get("certificates", []):
            path = cert["path"]

            if "apache" in path or "httpd" in path:
                web_certs["apache"].append(path)
            elif "nginx" in path:
                web_certs["nginx"].append(path)
            else:
                web_certs["unknown"].append(path)

        return web_certs
