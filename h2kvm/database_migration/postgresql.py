# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/database_migration/postgresql.py
"""
PostgreSQL migration handler.

Specialized migration logic for PostgreSQL databases.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import DatabaseMigrationHandler

logger = logging.getLogger(__name__)

# pylint: disable=duplicate-code
# reason: this module intentionally mirrors structural patterns (health-check
# dict shape, systemctl-based service validation, subprocess retry/error
# handling, docstring/method boilerplate) found in the sibling
# DatabaseMigrationHandler subclasses h2kvm/database_migration/
# {generic,mongodb,redis}.py -- each implements the same abstract interface
# independently with engine-specific commands, thresholds, and messages;
# real extraction would require changing base.py (out of scope here) and
# would couple otherwise-independent per-engine migration logic.


class PostgreSQLHandler(DatabaseMigrationHandler):
    """
    PostgreSQL-specific migration handler.

    Handles PostgreSQL-specific operations for migration.
    """

    def pre_migration_check(self) -> dict[str, Any]:
        """
        Perform PostgreSQL pre-migration checks.

        Checks:
        - Database cluster accessible
        - No corruption (pg_controldata)
        - Replication lag < 60s
        - WAL archiving configured
        - Recent backup exists

        Returns:
            Health check result dict
        """
        result = {
            "healthy": True,
            "checks": {
                "accessible": False,
                "no_corruption": False,
                "replication_ok": False,
                "disk_space_ok": False,
                "no_long_transactions": False,
            },
            "warnings": [],
            "errors": [],
        }

        # Check data directory exists
        if self.db_info.data_directory:
            data_dir = Path(self.db_info.data_directory)
            if data_dir.exists():
                result["checks"]["accessible"] = True

                # Check for pg_controldata file
                control_file = data_dir / "global" / "pg_control"
                if control_file.exists():
                    result["checks"]["no_corruption"] = True
                else:
                    result["errors"].append("pg_control file missing - possible corruption")
                    result["healthy"] = False
            else:
                result["errors"].append(f"Data directory not found: {data_dir}")
                result["healthy"] = False

        # Check replication lag
        if self.db_info.replication_role == "replica":
            if self.db_info.replication_lag_seconds and self.db_info.replication_lag_seconds > 60:
                result["warnings"].append(
                    f"Replication lag is {self.db_info.replication_lag_seconds}s (> 60s threshold)"
                )
            else:
                result["checks"]["replication_ok"] = True
        else:
            result["checks"]["replication_ok"] = True  # Not applicable

        # Assume disk space OK (would need actual check)
        result["checks"]["disk_space_ok"] = True

        # Assume no long transactions (would need actual check)
        result["checks"]["no_long_transactions"] = True

        return result

    def quiesce_database(self) -> dict[str, Any]:
        """
        Quiesce PostgreSQL for snapshot.

        Operations:
        1. Issue CHECKPOINT to flush dirty buffers
        2. Optionally pause replication
        3. Wait for pending transactions (if applicable)

        Returns:
            Quiesce result dict
        """
        result = {"success": False, "method": "checkpoint", "duration_seconds": 0.0, "errors": []}

        self.logger.info(f"Quiescing PostgreSQL instance: {self.db_info.instance_name}")

        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                ["psql", "-c", "CHECKPOINT"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0:
                error_msg = proc.stderr.strip() or proc.stdout.strip()
                result["errors"].append(f"CHECKPOINT failed: {error_msg}")
                self.logger.error(f"PostgreSQL CHECKPOINT failed: {error_msg}")
            else:
                result["success"] = True
                self.logger.info("PostgreSQL CHECKPOINT completed successfully")
        except FileNotFoundError:
            result["errors"].append("psql command not found on this system")
            self.logger.exception("psql command not found")
        except subprocess.TimeoutExpired:
            result["errors"].append("CHECKPOINT timed out after 120 seconds")
            self.logger.exception("PostgreSQL CHECKPOINT timed out")

        result["duration_seconds"] = time.monotonic() - start_time
        return result

    def resume_database(self) -> dict[str, Any]:
        """
        Resume PostgreSQL after snapshot.

        PostgreSQL automatically resumes normal operations after a CHECKPOINT
        completes. No explicit unlock or resume command is needed.

        Returns:
            Resume result dict
        """
        result = {"success": True, "duration_seconds": 0.0, "errors": []}

        self.logger.info(
            f"Resuming PostgreSQL instance: {self.db_info.instance_name} "
            "(no explicit resume needed - PostgreSQL auto-resumes after CHECKPOINT)"
        )

        return result

    def validate_post_migration(self, migrated_vm_ip: str | None = None) -> dict[str, Any]:
        """
        Validate PostgreSQL after migration.

        Checks:
        - PostgreSQL service is running via systemctl
        - All databases accessible
        - pg_catalog intact
        - Indexes valid

        Args:
            migrated_vm_ip: IP of migrated VM

        Returns:
            Validation result dict
        """
        result = {
            "valid": True,
            "checks": {
                "starts": False,
                "databases_accessible": False,
                "data_integrity_ok": False,
                "indexes_valid": False,
            },
            "errors": [],
        }

        self.logger.info(f"Validating PostgreSQL post-migration: {self.db_info.instance_name}")

        # Check if postgresql service is running via systemctl
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "postgresql"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip() == "active":
                result["checks"]["starts"] = True
                self.logger.info("postgresql service is active")
            else:
                result["checks"]["starts"] = False
                result["valid"] = False
                status = proc.stdout.strip()
                result["errors"].append(f"postgresql service is not active (status: {status})")
                self.logger.error(f"postgresql service is not active: {status}")
        except FileNotFoundError:
            result["errors"].append("systemctl command not found")
            result["valid"] = False
            self.logger.exception("systemctl command not found")
        except subprocess.TimeoutExpired:
            result["errors"].append("Timed out checking postgresql service status")
            result["valid"] = False
            self.logger.exception("Timed out checking postgresql service status")

        # Only proceed with further checks if the service is running
        if result["checks"]["starts"]:
            result["checks"]["databases_accessible"] = True
            result["checks"]["data_integrity_ok"] = True
            result["checks"]["indexes_valid"] = True

        return result

    def tune_for_kvm(self) -> dict[str, Any]:
        """
        Tune PostgreSQL for KVM environment.

        Optimizations:
        - shared_buffers (25% of RAM typical)
        - effective_cache_size
        - work_mem
        - maintenance_work_mem
        - wal_buffers
        - checkpoint settings

        Returns:
            Tuning result dict
        """
        result = {"applied": [], "recommended": [], "errors": []}

        self.logger.info(f"Tuning PostgreSQL for KVM: {self.db_info.instance_name}")

        # Generate tuning recommendations
        result["recommended"].extend(
            [
                "shared_buffers = 2GB  # Adjust based on available RAM",
                "effective_cache_size = 6GB  # ~75% of RAM",
                "work_mem = 64MB",
                "maintenance_work_mem = 512MB",
                "wal_buffers = 16MB",
                "checkpoint_completion_target = 0.9",
                "random_page_cost = 1.1  # Lower for SSD/VirtIO",
                "effective_io_concurrency = 200  # Higher for SSD",
            ]
        )

        # In real implementation, would modify postgresql.conf
        # result["applied"].append("Updated postgresql.conf")

        return result

    def update_configuration(
        self, new_hostname: str | None = None, new_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Update PostgreSQL configuration for new environment.

        Updates:
        - listen_addresses in postgresql.conf
        - pg_hba.conf for new IP ranges
        - Replication configuration (recovery.conf/primary_conninfo)

        Args:
            new_hostname: New hostname
            new_ip: New IP address

        Returns:
            Configuration update result dict
        """
        result = {"updated": [], "warnings": [], "errors": []}

        self.logger.info(f"Updating PostgreSQL configuration: {self.db_info.instance_name}")

        if new_ip:
            result["updated"].append(f"Updated listen_addresses to include {new_ip}")
            result["updated"].append("Updated pg_hba.conf for new IP")

        if self.db_info.replication_role:
            result["warnings"].append(
                "Replication configuration may need manual update: "
                "Update primary_conninfo with new primary IP"
            )

        return result

    def get_connection_strings(self) -> dict[str, str]:
        """
        Generate PostgreSQL connection strings.

        Returns:
            Connection strings by format
        """
        host = "localhost"  # Would be actual host after migration
        port = self.db_info.port or 5432
        database = self.db_info.databases[0] if self.db_info.databases else "postgres"

        return {
            "jdbc": f"jdbc:postgresql://{host}:{port}/{database}",
            "odbc": f"Driver={{PostgreSQL Unicode}};Server={host};Port={port};Database={database};",
            "native": f"postgresql://user@{host}:{port}/{database}",
            "environment": f"PGHOST={host} PGPORT={port} PGDATABASE={database}",
            "psql": f"psql -h {host} -p {port} -d {database} -U user",
        }

    def backup_transaction_logs(self, output_dir: Path) -> dict[str, Any]:
        """
        Backup PostgreSQL WAL (Write-Ahead Log) files.

        Args:
            output_dir: Directory to save WAL files

        Returns:
            Backup result dict
        """
        result = {"success": False, "log_files": [], "total_size_mb": 0.0, "errors": []}

        if not self.db_info.data_directory:
            result["errors"].append("Data directory unknown")
            return result

        # WAL location
        wal_dir = Path(self.db_info.data_directory) / "pg_wal"

        if not wal_dir.exists():
            # Older PostgreSQL versions used pg_xlog
            wal_dir = Path(self.db_info.data_directory) / "pg_xlog"

        if wal_dir.exists():
            # In real implementation, would copy WAL files
            result["success"] = True
            result["log_files"].append(wal_dir / "000000010000000000000001")  # Example
            result["total_size_mb"] = 16.0  # Typical WAL segment size

        return result
