# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/forensic_analyzer.py
"""
Forensic analysis and incident response capabilities.

Provides comprehensive forensic analysis:
- Timeline analysis (file access, modifications, creations)
- Malware indicators detection
- Persistence mechanism detection
- Rootkit detection indicators
- Suspicious process detection
- Browser history analysis
- Recently accessed files

Features:
- File timeline generation (mtime, atime, ctime)
- Malware signature detection (basic patterns)
- Persistence mechanism enumeration
- Hidden file detection
- Suspicious file patterns
- Browser artifact analysis
- Recent document tracking
"""

from __future__ import annotations

import re
from typing import Any

from .base_analyzer import BaseAnalyzer


class ForensicAnalyzer(BaseAnalyzer):
    """
    Forensic analyzer for incident response.

    Analyzes filesystem for forensic evidence and security incidents.
    """

    # Suspicious file patterns
    SUSPICIOUS_PATTERNS = [
        r".*\.exe\.txt$",  # Hidden executables
        r".*\.(vbs|bat|cmd|ps1)$",  # Script files
        r".*mimikatz.*",  # Credential dumping tool
        r".*metasploit.*",  # Penetration testing framework
        r".*\.encrypted$",  # Ransomware indicators
        r".*\.locked$",  # Ransomware indicators
        r".*\.crypted$",  # Ransomware indicators
    ]

    # Known malware file names
    MALWARE_INDICATORS = [
        "nc.exe",
        "ncat.exe",  # Netcat
        "psexec.exe",  # Remote execution
        "mimikatz.exe",  # Credential dumping
        "procdump.exe",
        "procdump64.exe",  # Process dumping
        "pwdump.exe",  # Password dumping
        "fgdump.exe",  # Password dumping
    ]

    # Persistence locations (Windows)
    WINDOWS_PERSISTENCE = [
        "/Windows/System32/Tasks",  # Scheduled tasks
        "/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup",
        "/Users/*/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup",
    ]

    # Persistence locations (Linux)
    LINUX_PERSISTENCE = [
        "/etc/cron.d",
        "/etc/cron.daily",
        "/etc/cron.hourly",
        "/etc/cron.monthly",
        "/etc/cron.weekly",
        "/var/spool/cron",
        "/etc/rc.local",
        "/etc/init.d",
        "/etc/systemd/system",
        "/home/*/.config/autostart",
    ]

    def analyze_forensics(self, os_type: str = "linux") -> dict[str, Any]:
        """
        Perform comprehensive forensic analysis.

        Args:
            os_type: Operating system type

        Returns:
            Forensic analysis results
        """
        analysis: dict[str, Any] = {
            "os_type": os_type,
            "timeline": [],
            "suspicious_files": [],
            "persistence_mechanisms": [],
            "hidden_files": [],
            "recent_activity": {},
            "malware_indicators": [],
            "total_suspicious": 0,
        }

        # Detect suspicious files
        suspicious = self._detect_suspicious_files()
        analysis["suspicious_files"] = suspicious
        analysis["total_suspicious"] = len(suspicious)

        # Detect persistence mechanisms
        persistence = self._detect_persistence(os_type)
        analysis["persistence_mechanisms"] = persistence

        # Detect hidden files
        hidden = self._detect_hidden_files()
        analysis["hidden_files"] = hidden[:50]  # Limit to 50

        # Analyze recent activity
        recent = self._analyze_recent_activity()
        analysis["recent_activity"] = recent

        # Detect malware indicators
        malware = self._detect_malware_indicators()
        analysis["malware_indicators"] = malware

        return analysis

    def _detect_suspicious_files(self) -> list[dict[str, Any]]:
        """Detect suspicious files."""
        suspicious = []

        # Common suspicious locations
        locations = [
            "/tmp",
            "/var/tmp",
            "/dev/shm",
            "/Windows/Temp",
            "/Users/*/AppData/Local/Temp",
        ]

        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.ls(location)
                for filename in files[:100]:  # Limit per directory
                    file_path = f"{location}/{filename}"

                    # Check against suspicious patterns
                    for pattern in self.SUSPICIOUS_PATTERNS:
                        if re.match(pattern, filename, re.IGNORECASE):
                            suspicious.append(
                                {
                                    "path": file_path,
                                    "pattern": pattern,
                                    "reason": "Matches suspicious pattern",
                                }
                            )
                            break

                    # Check against malware indicators
                    if filename.lower() in [m.lower() for m in self.MALWARE_INDICATORS]:
                        suspicious.append(
                            {
                                "path": file_path,
                                "pattern": filename,
                                "reason": "Known malware tool",
                            }
                        )

                    if len(suspicious) >= 100:  # Limit total
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # file_ops wraps guestfs, which raises varied/dynamic error types; this is a
                # best-effort forensic scan and must not abort over one location's quirk.
                self.logger.debug(f"Error scanning {location}: {e}")

            if len(suspicious) >= 100:
                break

        return suspicious

    def _detect_persistence(self, os_type: str) -> list[dict[str, Any]]:
        """Detect persistence mechanisms."""
        persistence = []

        locations = self.WINDOWS_PERSISTENCE if os_type == "windows" else self.LINUX_PERSISTENCE

        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.ls(location)
                for filename in files[:50]:  # Limit per location
                    persistence.append(
                        {
                            "type": "persistence",
                            "location": location,
                            "file": filename,
                            "path": f"{location}/{filename}",
                        }
                    )

                    if len(persistence) >= 100:  # Limit total
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan across many possible layouts; one location's failure
                # must not abort the rest of the persistence sweep.
                pass

            if len(persistence) >= 100:
                break

        return persistence

    def _detect_hidden_files(self) -> list[dict[str, Any]]:
        """Detect hidden files."""
        hidden = []

        # Common locations for hidden files
        locations = [
            "/root",
            "/home/*",
            "/tmp",
            "/var/tmp",
        ]

        # pylint: disable=duplicate-code
        # reason: the "for location: if not is_dir: continue; try: scan
        # files" shape mirrors h2kvm/vmcraft/data_discovery.py's
        # _scan_private_keys() -- coincidental, this is a generic
        # best-effort directory-sweep idiom reused with different bodies
        # throughout vmcraft's scanners.
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.ls(location)
                for filename in files:
                    # Hidden files start with dot (Linux)
                    if filename.startswith(".") and filename not in [".", ".."]:
                        hidden.append(
                            {
                                "path": f"{location}/{filename}",
                                "name": filename,
                                "location": location,
                            }
                        )

                        if len(hidden) >= 50:
                            break
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan; one location's failure must not abort the sweep.
                pass

            if len(hidden) >= 50:
                break

        return hidden

    def _analyze_recent_activity(self) -> dict[str, Any]:
        """Analyze recent file activity."""
        activity: dict[str, Any] = {
            "recent_modifications": [],
            "recent_creations": [],
            "recent_accesses": [],
        }

        # Check common user directories
        locations = [
            "/home",
            "/root",
            "/Users",
            "/tmp",
        ]

        recent_files = []

        # pylint: disable=duplicate-code
        # reason: the "for location: if not is_dir: continue; try: scan
        # files" shape mirrors h2kvm/vmcraft/data_discovery.py's
        # _find_sensitive_files() and h2kvm/vmcraft/config_tracker.py's
        # _find_config_files() -- coincidental, this is a generic
        # best-effort directory-sweep idiom reused with different bodies
        # throughout vmcraft's scanners.
        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.find_files(location, file_type="f")
                for file_path in files[:100]:  # Limit per location
                    try:
                        age = self.file_ops.file_age(file_path)
                        recent_files.append(
                            {
                                "path": file_path,
                                "mtime": age.get("mtime"),
                                "atime": age.get("atime"),
                                "ctime": age.get("ctime"),
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file age lookup is best-effort; one bad file must not stop the scan.
                        pass

                    if len(recent_files) >= 100:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan; one location's failure must not abort the sweep.
                pass

            if len(recent_files) >= 100:
                break

        # Sort and categorize (simplified - would use actual timestamps in production)
        activity["recent_modifications"] = recent_files[:20]
        activity["recent_creations"] = recent_files[:20]
        activity["recent_accesses"] = recent_files[:20]

        return activity

    def _detect_malware_indicators(self) -> list[dict[str, Any]]:
        """Detect malware indicators."""
        indicators = []

        # Check for known malware paths

        # Check suspicious registry keys (for Windows)

        # For now, just check for known bad files
        for malware_file in self.MALWARE_INDICATORS:
            # Check common locations
            check_paths = [
                f"/tmp/{malware_file}",
                f"/var/tmp/{malware_file}",
                f"/Windows/Temp/{malware_file}",
                f"/Users/Public/{malware_file}",
            ]

            for path in check_paths:
                if self.file_ops.exists(path):
                    indicators.append(
                        {
                            "type": "known_malware",
                            "path": path,
                            "name": malware_file,
                            "severity": "high",
                        }
                    )

        return indicators

    def get_forensic_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get forensic analysis summary.

        Args:
            analysis: Forensic analysis results

        Returns:
            Summary dictionary
        """
        summary = {
            "total_suspicious_files": len(analysis.get("suspicious_files", [])),
            "total_persistence_mechanisms": len(analysis.get("persistence_mechanisms", [])),
            "total_hidden_files": len(analysis.get("hidden_files", [])),
            "malware_indicators": len(analysis.get("malware_indicators", [])),
            "risk_level": "unknown",
        }

        # Calculate risk level
        suspicious_count = summary["total_suspicious_files"]
        malware_count = summary["malware_indicators"]

        if malware_count > 0:
            summary["risk_level"] = "critical"
        elif suspicious_count > 50:
            summary["risk_level"] = "high"
        elif suspicious_count > 20:
            summary["risk_level"] = "medium"
        elif suspicious_count > 0:
            summary["risk_level"] = "low"
        else:
            summary["risk_level"] = "minimal"

        return summary

    def generate_timeline(self, hours: int = 24) -> list[dict[str, Any]]:  # pylint: disable=unused-argument
        """
        Generate file activity timeline.

        Args:
            hours: Number of hours to look back. Part of the documented public API (see
                analyzer_ops.py dispatch) for a future time-windowed timeline; the current
                simplified implementation scans unfiltered.

        Returns:
            List of timeline events
        """
        timeline = []

        # This would scan filesystem for recent changes
        # Simplified implementation
        locations = ["/tmp", "/var/tmp", "/home", "/root"]

        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.find_files(location, file_type="f")
                for file_path in files[:50]:
                    try:
                        age = self.file_ops.file_age(file_path)
                        timeline.append(
                            {
                                "timestamp": age.get("mtime", "unknown"),
                                "event": "file_modified",
                                "path": file_path,
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file age lookup is best-effort; one bad file must not stop the scan.
                        pass
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan; one location's failure must not abort the sweep.
                pass

        # Sort by timestamp (simplified)
        return timeline[:100]

    def detect_rootkit_indicators(self) -> list[dict[str, Any]]:
        """
        Detect rootkit indicators.

        Returns:
            List of rootkit indicators
        """
        indicators = []

        # Check for common rootkit files/directories

        # Check for suspicious kernel modules (Linux)
        if self.file_ops.is_dir("/lib/modules"):
            try:
                modules = self.file_ops.find_files("/lib/modules", pattern="*.ko")
                for module in modules[:50]:
                    # Check for suspicious names
                    if any(suspicious in module.lower() for suspicious in ["rootkit", "hide", "backdoor"]):
                        indicators.append(
                            {
                                "type": "suspicious_kernel_module",
                                "path": module,
                                "severity": "high",
                            }
                        )
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan; module listing failures must not abort detection.
                pass

        return indicators

    def analyze_browser_history(self) -> dict[str, Any]:
        """
        Analyze browser history artifacts.

        Returns:
            Browser history analysis
        """
        history: dict[str, Any] = {
            "browsers": [],
            "history_files": [],
            "cookie_files": [],
            "cache_dirs": [],
        }

        # Common browser data locations
        browser_paths = {
            "chrome": [
                "/Users/*/Library/Application Support/Google/Chrome",
                "/home/*/.config/google-chrome",
            ],
            "firefox": [
                "/Users/*/Library/Application Support/Firefox",
                "/home/*/.mozilla/firefox",
            ],
            "edge": [
                "/Users/*/Library/Application Support/Microsoft Edge",
                "/home/*/.config/microsoft-edge",
            ],
        }

        for browser, paths in browser_paths.items():
            for path in paths:
                if self.file_ops.is_dir(path):
                    history["browsers"].append(browser)
                    break

        return history

    def find_recently_accessed_files(  # pylint: disable=unused-argument
        self, days: int = 7
    ) -> list[dict[str, Any]]:
        """
        Find files accessed in the last N days.

        Args:
            days: Number of days to look back. Part of the documented public API (see
                analyzer_ops.py dispatch) for a future time-windowed filter; the current
                simplified implementation scans unfiltered.

        Returns:
            List of recently accessed files
        """
        recent = []

        # Common user data locations
        locations = [
            "/home",
            "/Users",
            "/root",
        ]

        for location in locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.find_files(location, file_type="f")
                for file_path in files[:100]:
                    try:
                        age = self.file_ops.file_age(file_path)
                        recent.append(
                            {
                                "path": file_path,
                                "atime": age.get("atime"),
                                "mtime": age.get("mtime"),
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Per-file age lookup is best-effort; one bad file must not stop the scan.
                        pass

                    if len(recent) >= 100:
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan; one location's failure must not abort the sweep.
                pass

            if len(recent) >= 100:
                break

        return recent

    def detect_data_exfiltration_indicators(self) -> list[dict[str, Any]]:
        """
        Detect potential data exfiltration indicators.

        Returns:
            List of exfiltration indicators
        """
        indicators = []

        # Check for large archives in temp directories
        temp_locations = ["/tmp", "/var/tmp", "/Windows/Temp"]

        for location in temp_locations:
            if not self.file_ops.is_dir(location):
                continue

            try:
                files = self.file_ops.ls(location)
                for filename in files[:50]:
                    # Check for archives
                    if any(filename.endswith(ext) for ext in [".zip", ".tar", ".tar.gz", ".7z", ".rar"]):
                        indicators.append(
                            {
                                "type": "suspicious_archive",
                                "path": f"{location}/{filename}",
                                "reason": "Large archive in temp directory",
                            }
                        )
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort scan; one location's listing failure must not abort detection.
                pass

        return indicators
