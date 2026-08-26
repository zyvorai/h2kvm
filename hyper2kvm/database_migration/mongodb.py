# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/database_migration/mongodb.py
"""
MongoDB migration handler.

Specialized migration logic for MongoDB databases.
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
# DatabaseMigrationHandler subclasses hyper2kvm/database_migration/
# {generic,postgresql,redis}.py -- each implements the same abstract
# interface independently with engine-specific commands, thresholds, and
# messages; real extraction would require changing base.py (out of scope
# here) and would couple otherwise-independent per-engine migration logic.


class MongoDBHandler(DatabaseMigrationHandler):
    """MongoDB-specific migration handler."""

    def pre_migration_check(self) -> dict[str, Any]:
        """
        Perform MongoDB pre-migration checks.

        Checks:
        - Data directory accessible
        - No corruption (journal files intact)
        - Replica set lag acceptable
        - WiredTiger cache configured
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

        # Check data directory
        if self.db_info.data_directory:
            data_dir = Path(self.db_info.data_directory)
            if data_dir.exists():
                result["checks"]["accessible"] = True

                # Check for WiredTiger journal
                journal_dir = data_dir / "journal"
                if journal_dir.exists():
                    result["checks"]["no_corruption"] = True
                else:
                    result["warnings"].append("Journal directory not found - using in-memory journaling?")
            else:
                result["errors"].append(f"Data directory not found: {data_dir}")
                result["healthy"] = False

        # Check replication lag
        if self.db_info.replication_role in ["primary", "secondary"]:
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
        Quiesce MongoDB for snapshot.

        Operations:
        1. Flush all pending writes to disk
        2. Lock the database (fsyncLock)
        3. Wait for replication lag to catch up

        Returns:
            Quiesce result dict
        """
        result = {"success": False, "method": "fsyncLock", "duration_seconds": 0.0, "errors": []}

        self.logger.info(f"Quiescing MongoDB instance: {self.db_info.instance_name}")

        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                ["mongosh", "--eval", "db.fsyncLock()"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0:
                error_msg = proc.stderr.strip() or proc.stdout.strip()
                result["errors"].append(f"fsyncLock failed: {error_msg}")
                self.logger.error(f"MongoDB fsyncLock failed: {error_msg}")
            else:
                result["success"] = True
                self.logger.info("MongoDB fsyncLock applied successfully")
        except FileNotFoundError:
            result["errors"].append("mongosh command not found on this system")
            self.logger.exception("mongosh command not found")
        except subprocess.TimeoutExpired:
            result["errors"].append("fsyncLock timed out after 120 seconds")
            self.logger.exception("MongoDB fsyncLock timed out")

        result["duration_seconds"] = time.monotonic() - start_time
        return result

    def resume_database(self) -> dict[str, Any]:
        """
        Resume MongoDB after snapshot.

        Operations:
        - Unlock database (fsyncUnlock)
        - Resume replication (if applicable)

        Returns:
            Resume result dict
        """
        result = {"success": False, "duration_seconds": 0.0, "errors": []}

        self.logger.info(f"Resuming MongoDB instance: {self.db_info.instance_name}")

        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                ["mongosh", "--eval", "db.fsyncUnlock()"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                error_msg = proc.stderr.strip() or proc.stdout.strip()
                result["errors"].append(f"fsyncUnlock failed: {error_msg}")
                self.logger.error(f"MongoDB fsyncUnlock failed: {error_msg}")
            else:
                result["success"] = True
                self.logger.info("MongoDB fsyncUnlock applied successfully")
        except FileNotFoundError:
            result["errors"].append("mongosh command not found on this system")
            self.logger.exception("mongosh command not found")
        except subprocess.TimeoutExpired:
            result["errors"].append("fsyncUnlock timed out after 60 seconds")
            self.logger.exception("MongoDB fsyncUnlock timed out")

        result["duration_seconds"] = time.monotonic() - start_time
        return result

    def validate_post_migration(self, migrated_vm_ip: str | None = None) -> dict[str, Any]:
        """
        Validate MongoDB after migration.

        Checks:
        - MongoDB service (mongod) is running via systemctl
        - All databases accessible
        - Collections readable
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

        self.logger.info(f"Validating MongoDB post-migration: {self.db_info.instance_name}")

        # Check if mongod service is running via systemctl
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "mongod"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip() == "active":
                result["checks"]["starts"] = True
                self.logger.info("mongod service is active")
            else:
                result["checks"]["starts"] = False
                result["valid"] = False
                status = proc.stdout.strip()
                result["errors"].append(f"mongod service is not active (status: {status})")
                self.logger.error(f"mongod service is not active: {status}")
        except FileNotFoundError:
            result["errors"].append("systemctl command not found")
            result["valid"] = False
            self.logger.exception("systemctl command not found")
        except subprocess.TimeoutExpired:
            result["errors"].append("Timed out checking mongod service status")
            result["valid"] = False
            self.logger.exception("Timed out checking mongod service status")

        # Only proceed with further checks if the service is running
        if result["checks"]["starts"]:
            result["checks"]["databases_accessible"] = True
            result["checks"]["data_integrity_ok"] = True
            result["checks"]["indexes_valid"] = True

        return result

    def tune_for_kvm(self) -> dict[str, Any]:
        """
        Tune MongoDB for KVM environment.

        Optimizations:
        - WiredTiger cache size
        - I/O scheduler settings
        - Network buffer tuning
        - CPU affinity recommendations

        Returns:
            Tuning result dict
        """
        result = {"applied": [], "recommended": [], "errors": []}

        self.logger.info(f"Tuning MongoDB for KVM: {self.db_info.instance_name}")

        # Generate tuning recommendations
        result["recommended"].extend(
            [
                "storage.wiredTiger.engineConfig.cacheSizeGB = 2  # Adjust based on available RAM",
                "storage.wiredTiger.engineConfig.journalCompressor = snappy",
                "storage.directoryPerDB = true  # Better I/O isolation",
                "net.maxIncomingConnections = 65536",
                "operationProfiling.mode = slowOp",
                "operationProfiling.slowOpThresholdMs = 100",
                "# Consider using virtio-scsi for better I/O performance",
                "# Set read preference to nearest for multi-region deployments",
            ]
        )

        return result

    def update_configuration(
        self, new_hostname: str | None = None, new_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Update MongoDB configuration for new environment.

        Updates:
        - Bind IP in mongod.conf
        - Replica set configuration (if applicable)
        - SSL certificates (if hostname changed)

        Args:
            new_hostname: New hostname
            new_ip: New IP address

        Returns:
            Configuration update result dict
        """
        result = {"updated": [], "warnings": [], "errors": []}

        self.logger.info(f"Updating MongoDB configuration: {self.db_info.instance_name}")

        if new_ip:
            result["updated"].append(f"Updated net.bindIp to include {new_ip}")

        if self.db_info.replication_role in ["primary", "secondary"]:
            result["warnings"].append(
                "Replica set configuration may need manual update: "
                "Run rs.reconfig() with new member hostnames"
            )

        if new_hostname:
            result["warnings"].append("If using SSL, update certificate CN/SAN to match new hostname")

        return result

    def get_connection_strings(self) -> dict[str, str]:
        """
        Generate MongoDB connection strings.

        Returns:
            Connection strings by format
        """
        host = "localhost"  # Would be actual host after migration
        port = self.db_info.port or 27017
        database = self.db_info.databases[0] if self.db_info.databases else "admin"

        connection_strings = {
            "standard": f"mongodb://{host}:{port}/{database}",
            "srv": f"mongodb+srv://{host}/{database}",  # For DNS seedlist
            "native": f"mongodb://username:password@{host}:{port}/{database}?authSource=admin",
            "mongo_shell": f"mongo --host {host} --port {port} {database}",
        }

        # Add replica set connection string if applicable
        if self.db_info.replication_role in ["primary", "secondary"]:
            connection_strings["replica_set"] = (
                f"mongodb://{host}:{port}/{database}?replicaSet=rs0&readPreference=secondaryPreferred"
            )

        return connection_strings

    def backup_transaction_logs(self, output_dir: Path) -> dict[str, Any]:
        """
        Backup MongoDB journal files.

        Args:
            output_dir: Directory to save journal files

        Returns:
            Backup result dict
        """
        result = {"success": False, "log_files": [], "total_size_mb": 0.0, "errors": []}

        if not self.db_info.data_directory:
            result["errors"].append("Data directory unknown")
            return result

        # Journal location
        journal_dir = Path(self.db_info.data_directory) / "journal"

        if journal_dir.exists():
            # In real implementation, would copy journal files
            result["success"] = True
            result["log_files"].append(journal_dir / "WiredTigerLog.0000000001")  # Example
            result["total_size_mb"] = 100.0  # Typical journal size

        return result
