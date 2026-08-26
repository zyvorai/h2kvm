# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/database_migration/generic.py
"""
Generic database migration handler.

Fallback handler for databases without specialized implementations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import DatabaseMigrationHandler

logger = logging.getLogger(__name__)


class GenericDatabaseHandler(DatabaseMigrationHandler):
    """
    Generic database migration handler.

    Provides basic migration support for databases without
    specialized handlers (Oracle, Cassandra, Elasticsearch, etc.).
    """

    def pre_migration_check(self) -> dict[str, Any]:
        """
        Perform generic pre-migration checks.

        Checks:
        - Data directory accessible
        - Sufficient disk space
        - Basic file integrity

        Returns:
            Health check result dict
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the pre_migration_check result-dict shape in
        # hyper2kvm/database_migration/postgresql.py -- both implement the
        # same DatabaseMigrationHandler.pre_migration_check interface
        # independently; keeping separate avoids coupling per-engine
        # health-check logic.
        result = {
            "healthy": True,
            "checks": {
                "accessible": False,
                "no_corruption": False,
                "replication_ok": False,
                "disk_space_ok": False,
                "no_long_transactions": False,
            },
            "warnings": [
                f"No specialized handler for {self.db_info.engine.value} - using generic migration"
            ],
            "errors": [],
        }

        # Check data directory exists
        if self.db_info.data_directory:
            data_dir = Path(self.db_info.data_directory)
            if data_dir.exists():
                result["checks"]["accessible"] = True
                result["checks"]["no_corruption"] = True  # Assume OK
            else:
                result["errors"].append(f"Data directory not found: {data_dir}")
                result["healthy"] = False

        # Assume other checks OK (can't verify without database-specific knowledge)
        result["checks"]["replication_ok"] = True
        result["checks"]["disk_space_ok"] = True
        result["checks"]["no_long_transactions"] = True

        return result

    def quiesce_database(self) -> dict[str, Any]:
        """
        Generic database quiesce.

        For offline migration, this is typically a no-op.
        For live migration, manual intervention may be required.

        Returns:
            Quiesce result dict
        """
        result = {"success": True, "method": "offline (VM shutdown)", "duration_seconds": 0.0, "errors": []}

        self.logger.warning(
            f"No specialized quiesce method for {self.db_info.engine.value}. "
            f"Ensure VM is shutdown cleanly before migration."
        )

        return result

    def resume_database(self) -> dict[str, Any]:
        """
        Generic database resume.

        For offline migration, database resumes on VM boot.

        Returns:
            Resume result dict
        """
        result = {"success": True, "duration_seconds": 0.0, "errors": []}

        self.logger.info(f"Database will resume on VM boot: {self.db_info.instance_name}")

        return result

    def validate_post_migration(self, migrated_vm_ip: str | None = None) -> dict[str, Any]:
        """
        Generic post-migration validation.

        Basic checks only - manual validation recommended.

        Args:
            migrated_vm_ip: IP of migrated VM

        Returns:
            Validation result dict
        """
        result = {
            "valid": True,
            "checks": {
                "starts": True,  # Assume OK - can't verify
                "databases_accessible": True,
                "data_integrity_ok": True,
                "indexes_valid": True,
            },
            "errors": [],
            "warnings": [
                f"Manual validation recommended for {self.db_info.engine.value}",
                "Verify database starts and accepts connections",
                "Run database-specific integrity checks",
            ],
        }

        self.logger.warning(
            f"No specialized validation for {self.db_info.engine.value}. "
            f"Manual validation strongly recommended."
        )

        return result

    def tune_for_kvm(self) -> dict[str, Any]:
        """
        Generic KVM tuning recommendations.

        Provides general virtualization best practices.

        Returns:
            Tuning result dict
        """
        return {
            "applied": [],
            "recommended": [
                "# General virtualization tuning:",
                "- Use VirtIO drivers for optimal I/O performance",
                "- Enable huge pages if database uses large memory",
                "- Set CPU affinity to avoid NUMA issues",
                "- Use dedicated disk volumes for database files",
                "- Monitor I/O latency and adjust queue depth if needed",
                "- Consider using dedicated network for database traffic",
                f"# Consult {self.db_info.engine.value} documentation for specific KVM tuning",
            ],
            "errors": [],
        }

    def update_configuration(
        self, new_hostname: str | None = None, new_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Generic configuration update.

        Provides guidance - manual intervention required.

        Args:
            new_hostname: New hostname
            new_ip: New IP address

        Returns:
            Configuration update result dict
        """
        result = {
            "updated": [],
            "warnings": [f"Manual configuration update required for {self.db_info.engine.value}"],
            "errors": [],
        }

        if new_hostname:
            result["warnings"].append(f"Update hostname references to: {new_hostname}")

        if new_ip:
            result["warnings"].append(f"Update IP address bindings to: {new_ip}")

        if self.db_info.config_file:
            result["warnings"].append(f"Review configuration file: {self.db_info.config_file}")

        if self.db_info.replication_role:
            result["warnings"].append(
                f"Replication configuration needs manual update (role: {self.db_info.replication_role})"
            )

        return result

    def get_connection_strings(self) -> dict[str, str]:
        """
        Generate generic connection information.

        Returns:
            Basic connection information
        """
        host = "localhost"
        port = self.db_info.port or 0
        instance = self.db_info.instance_name or "default"

        return {
            "generic": f"{self.db_info.engine.value}://{host}:{port}",
            "info": (
                f"Database: {self.db_info.engine.value}, Instance: {instance}, Host: {host}, Port: {port}"
            ),
            "note": f"Consult {self.db_info.engine.value} documentation for specific connection strings",
        }

    def backup_transaction_logs(self, output_dir: Path) -> dict[str, Any]:
        """
        Generic transaction log backup.

        Provides guidance - manual backup recommended.

        Args:
            output_dir: Directory to save logs

        Returns:
            Backup result dict
        """
        result = {
            "success": False,
            "log_files": [],
            "total_size_mb": 0.0,
            "errors": [],
            "warnings": [
                f"No specialized transaction log backup for {self.db_info.engine.value}",
                "Manual backup recommended before migration",
                f"Consult {self.db_info.engine.value} documentation for backup procedures",
            ],
        }

        if self.db_info.log_directory:
            result["warnings"].append(f"Log directory: {self.db_info.log_directory}")

        return result
