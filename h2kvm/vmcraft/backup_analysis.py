# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/backup_analysis.py
"""
Backup software and configuration analysis.

Provides comprehensive backup detection:
- Backup software: Bacula, Amanda, rsnapshot, Duplicity, Borg, Restic
- Cloud backup: AWS Backup, Azure Backup, Veeam
- Database backup: mysqldump, pg_dump, mongodump scripts
- Backup schedules from cron/systemd timers
- Backup locations and retention policies

Features:
- Detect installed backup software
- Parse backup configurations
- Identify backup schedules
- List backup destinations
- Check backup health
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class BackupAnalysis:
    """
    Backup software and configuration analyzer.

    Analyzes backup installations and configurations.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize backup analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def analyze_backup_software(self) -> dict[str, Any]:
        """
        Analyze backup software installations.

        Returns:
            Backup software analysis results
        """
        analysis: dict[str, Any] = {
            "backup_software": [],
            "schedules": [],
            "destinations": [],
            "total_software": 0,
            "total_schedules": 0,
        }

        # Detect backup software
        software = self._detect_backup_software()
        analysis["backup_software"] = software
        analysis["total_software"] = len(software)

        # Find backup schedules
        schedules = self._find_backup_schedules()
        analysis["schedules"] = schedules
        analysis["total_schedules"] = len(schedules)

        # Detect backup destinations
        destinations = self._detect_backup_destinations()
        analysis["destinations"] = destinations

        return analysis

    def _detect_backup_software(self) -> list[dict[str, Any]]:
        """Detect installed backup software."""
        software = []

        # Bacula
        if self.file_ops.exists("/usr/sbin/bacula-fd"):
            bacula = {
                "name": "Bacula",
                "type": "enterprise",
                "config": "/etc/bacula/bacula-fd.conf"
                if self.file_ops.exists("/etc/bacula/bacula-fd.conf")
                else None,
                "role": "client",
            }
            software.append(bacula)

        # Amanda
        if self.file_ops.exists("/usr/sbin/amrecover"):
            amanda = {
                "name": "Amanda",
                "type": "enterprise",
                "config": "/etc/amanda" if self.file_ops.is_dir("/etc/amanda") else None,
                "role": "client",
            }
            software.append(amanda)

        # rsnapshot
        if self.file_ops.exists("/usr/bin/rsnapshot"):
            rsnapshot = {
                "name": "rsnapshot",
                "type": "filesystem",
                "config": "/etc/rsnapshot.conf" if self.file_ops.exists("/etc/rsnapshot.conf") else None,
            }
            # Parse config if exists
            if rsnapshot["config"]:
                rsnapshot["details"] = self._parse_rsnapshot_config(rsnapshot["config"])
            software.append(rsnapshot)

        # Duplicity
        if self.file_ops.exists("/usr/bin/duplicity"):
            duplicity = {
                "name": "Duplicity",
                "type": "cloud-capable",
                "config": None,  # Usually scripted
            }
            software.append(duplicity)

        # Borg Backup
        if self.file_ops.exists("/usr/bin/borg"):
            borg = {
                "name": "BorgBackup",
                "type": "deduplication",
                "config": None,  # Repository-based
            }
            software.append(borg)

        # Restic
        if self.file_ops.exists("/usr/bin/restic"):
            restic = {
                "name": "Restic",
                "type": "cloud-capable",
                "config": None,  # Repository-based
            }
            software.append(restic)

        # Veeam Agent
        if self.file_ops.exists("/usr/bin/veeamconfig"):
            veeam = {
                "name": "Veeam Agent for Linux",
                "type": "enterprise",
                "config": "/etc/veeam" if self.file_ops.is_dir("/etc/veeam") else None,
            }
            software.append(veeam)

        # Custom backup scripts (common patterns)
        script_patterns = [
            "/usr/local/bin/backup",
            "/usr/local/bin/backup.sh",
            "/opt/backup/backup.sh",
            "/root/backup.sh",
        ]
        for script in script_patterns:
            if self.file_ops.exists(script):
                software.append(
                    {
                        "name": f"Custom Script ({Path(script).name})",
                        "type": "script",
                        "path": script,
                    }
                )

        return software

    def _parse_rsnapshot_config(self, config_path: str) -> dict[str, Any]:
        """Parse rsnapshot configuration."""
        details = {
            "snapshot_root": None,
            "intervals": [],
            "backup_points": [],
        }

        # pylint: disable=duplicate-code
        # reason: mirrors similar "cat + split key/value lines" config
        # parsing loops in vmcraft/database_detector.py (Redis/PostgreSQL
        # config) and vmcraft/enhanced_inspection.py (fstab parsing) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated config-parsing code paths.
        try:
            content = self.file_ops.cat(config_path)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                key = parts[0]
                value = parts[1]

                if key == "snapshot_root":
                    details["snapshot_root"] = value
                elif key.startswith(("retain", "interval")):
                    # retain hourly 6 or interval hourly 6
                    if len(parts) >= 3:
                        details["intervals"].append({"type": parts[1], "count": parts[2]})
                elif key == "backup":
                    # backup /home/ localhost/
                    details["backup_points"].append(
                        {"source": value, "destination": parts[2] if len(parts) >= 3 else None}
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort config parse, must not abort analysis
            self.logger.debug("Failed to parse rsnapshot config: %s", e)

        return details

    def _find_backup_schedules(self) -> list[dict[str, Any]]:
        """Find backup schedules in cron and systemd timers."""
        schedules = []

        # Check crontab files
        cron_paths = [
            "/etc/crontab",
            "/var/spool/cron/root",
        ]

        # Check /etc/cron.d/
        if self.file_ops.is_dir("/etc/cron.d"):
            try:
                cron_files = self.file_ops.ls("/etc/cron.d")
                cron_paths.extend([f"/etc/cron.d/{f}" for f in cron_files])
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort cron.d scan, must not abort analysis
                pass

        for cron_path in cron_paths:
            if not self.file_ops.exists(cron_path):
                continue

            try:
                content = self.file_ops.cat(cron_path)
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Look for backup-related keywords
                    if any(
                        keyword in line.lower()
                        for keyword in ["backup", "rsnapshot", "duplicity", "borg", "restic"]
                    ):
                        schedules.append(
                            {
                                "type": "cron",
                                "file": cron_path,
                                "command": line,
                            }
                        )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort crontab scan, must not abort analysis
                pass

        # Check systemd timers for backup
        if self.file_ops.is_dir("/etc/systemd/system"):
            try:
                timer_files = self.file_ops.find("/etc/systemd/system")
                for timer_file in timer_files:
                    if timer_file.endswith(".timer") and "backup" in timer_file.lower():
                        schedules.append(
                            {
                                "type": "systemd-timer",
                                "file": timer_file,
                            }
                        )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort timer scan, must not abort analysis
                pass

        return schedules

    def _detect_backup_destinations(self) -> list[dict[str, Any]]:
        """Detect backup destinations."""
        destinations = []

        # Check for common backup mount points
        mount_patterns = [
            "/mnt/backup",
            "/backup",
            "/mnt/backups",
            "/backups",
        ]

        for mount_point in mount_patterns:
            if self.file_ops.is_dir(mount_point):
                destinations.append(
                    {
                        "type": "local",
                        "path": mount_point,
                    }
                )

        # Check for S3/cloud backup indicators
        cloud_indicators = [
            ("/root/.aws/config", "AWS S3"),
            ("/root/.s3cfg", "S3-compatible"),
            ("/root/.config/rclone/rclone.conf", "Rclone (multi-cloud)"),
        ]

        for config_file, cloud_type in cloud_indicators:
            if self.file_ops.exists(config_file):
                destinations.append(
                    {
                        "type": "cloud",
                        "cloud_provider": cloud_type,
                        "config": config_file,
                    }
                )

        return destinations

    def get_backup_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get backup summary.

        Args:
            analysis: Backup analysis results

        Returns:
            Summary dictionary
        """
        return {
            "backup_software_count": analysis.get("total_software", 0),
            "scheduled_backups": analysis.get("total_schedules", 0),
            "backup_destinations": len(analysis.get("destinations", [])),
            "has_enterprise_backup": any(
                sw.get("type") == "enterprise" for sw in analysis.get("backup_software", [])
            ),
            "has_cloud_backup": any(
                dest.get("type") == "cloud" for dest in analysis.get("destinations", [])
            ),
        }

    def check_backup_health(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Check backup health and configuration.

        Args:
            analysis: Backup analysis results

        Returns:
            List of health issues
        """
        issues = []

        # Check if any backup software is installed
        if analysis.get("total_software", 0) == 0:
            issues.append(
                {
                    "severity": "high",
                    "issue": "No backup software detected",
                    "recommendation": "Install and configure backup solution (Borg, Restic, or rsnapshot recommended)",
                }
            )

        # Check if backups are scheduled
        if analysis.get("total_schedules", 0) == 0 and analysis.get("total_software", 0) > 0:
            issues.append(
                {
                    "severity": "medium",
                    "issue": "Backup software installed but no schedules found",
                    "recommendation": "Configure automated backup schedules via cron or systemd timers",
                }
            )

        # Check for backup destinations
        if len(analysis.get("destinations", [])) == 0 and analysis.get("total_software", 0) > 0:
            issues.append(
                {
                    "severity": "low",
                    "issue": "No backup destinations detected",
                    "recommendation": "Verify backup destination configuration",
                }
            )

        return issues

    def list_backup_software(self, analysis: dict[str, Any]) -> list[str]:
        """
        List names of detected backup software.

        Args:
            analysis: Backup analysis results

        Returns:
            List of backup software names
        """
        return [sw.get("name", "Unknown") for sw in analysis.get("backup_software", [])]

    def get_backup_schedules_by_type(self, analysis: dict[str, Any]) -> dict[str, int]:
        """
        Get backup schedule counts by type.

        Args:
            analysis: Backup analysis results

        Returns:
            Dictionary of schedule types and counts
        """
        schedules = analysis.get("schedules", [])
        by_type: dict[str, int] = {}

        for schedule in schedules:
            schedule_type = schedule.get("type", "unknown")
            by_type[schedule_type] = by_type.get(schedule_type, 0) + 1

        return by_type
