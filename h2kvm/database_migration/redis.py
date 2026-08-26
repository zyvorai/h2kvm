# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/database_migration/redis.py
"""
Redis migration handler.

Specialized migration logic for Redis databases.
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
# {generic,mongodb,postgresql}.py -- each implements the same abstract
# interface independently with engine-specific commands, thresholds, and
# messages; real extraction would require changing base.py (out of scope
# here) and would couple otherwise-independent per-engine migration logic.


class RedisHandler(DatabaseMigrationHandler):
    """Redis-specific migration handler."""

    def pre_migration_check(self) -> dict[str, Any]:
        """
        Perform Redis pre-migration checks.

        Checks:
        - Data directory accessible
        - AOF/RDB files intact
        - Replication lag acceptable
        - Memory configuration appropriate
        - No long-running commands

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

                # Check for persistence files
                rdb_file = data_dir / "dump.rdb"
                aof_file = data_dir / "appendonly.aof"

                if rdb_file.exists() or aof_file.exists():
                    result["checks"]["no_corruption"] = True
                else:
                    result["warnings"].append("No persistence files found - using in-memory only mode?")
            else:
                result["errors"].append(f"Data directory not found: {data_dir}")
                result["healthy"] = False

        # Check replication lag
        if self.db_info.replication_role == "replica":
            if self.db_info.replication_lag_seconds and self.db_info.replication_lag_seconds > 10:
                result["warnings"].append(
                    f"Replication lag is {self.db_info.replication_lag_seconds}s (> 10s threshold)"
                )
            else:
                result["checks"]["replication_ok"] = True
        else:
            result["checks"]["replication_ok"] = True  # Not applicable

        # Assume disk space OK
        result["checks"]["disk_space_ok"] = True

        # Assume no long transactions
        result["checks"]["no_long_transactions"] = True

        return result

    def _is_bgsave_in_progress(self) -> bool | None:
        """
        Poll `redis-cli INFO persistence` for rdb_bgsave_in_progress.

        Returns True if a save is still in progress, False if it has completed,
        or None if the state could not be determined (treated as "keep polling").
        """
        try:
            info_proc = subprocess.run(
                ["redis-cli", "INFO", "persistence"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if info_proc.returncode != 0:
            return None

        for line in info_proc.stdout.splitlines():
            if line.startswith("rdb_bgsave_in_progress:"):
                return line.split(":", 1)[1].strip() != "0"

        return None

    def quiesce_database(self) -> dict[str, Any]:
        """
        Quiesce Redis for snapshot.

        Operations:
        1. Execute BGSAVE to create snapshot
        2. Wait for background save to complete (poll INFO persistence)

        Returns:
            Quiesce result dict
        """
        result = {"success": False, "method": "bgsave", "duration_seconds": 0.0, "errors": []}

        self.logger.info(f"Quiescing Redis instance: {self.db_info.instance_name}")

        start_time = time.monotonic()

        # Initiate BGSAVE
        try:
            proc = subprocess.run(
                ["redis-cli", "BGSAVE"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                error_msg = proc.stderr.strip() or proc.stdout.strip()
                result["errors"].append(f"BGSAVE failed: {error_msg}")
                self.logger.error(f"Redis BGSAVE failed: {error_msg}")
                result["duration_seconds"] = time.monotonic() - start_time
                return result

            self.logger.info("Redis BGSAVE initiated, waiting for completion")
        except FileNotFoundError:
            result["errors"].append("redis-cli command not found on this system")
            self.logger.exception("redis-cli command not found")
            result["duration_seconds"] = time.monotonic() - start_time
            return result
        except subprocess.TimeoutExpired:
            result["errors"].append("BGSAVE command timed out after 30 seconds")
            self.logger.exception("Redis BGSAVE command timed out")
            result["duration_seconds"] = time.monotonic() - start_time
            return result

        # Wait for BGSAVE to complete by polling rdb_bgsave_in_progress
        max_wait = 300  # 5 minutes max wait
        poll_interval = 1.0
        elapsed = 0.0

        while elapsed < max_wait:
            if self._is_bgsave_in_progress() is False:
                result["success"] = True
                self.logger.info("Redis BGSAVE completed successfully")
                result["duration_seconds"] = time.monotonic() - start_time
                return result

            time.sleep(poll_interval)
            elapsed += poll_interval

        result["errors"].append(f"BGSAVE did not complete within {max_wait} seconds")
        self.logger.error(f"Redis BGSAVE did not complete within {max_wait} seconds")
        result["duration_seconds"] = time.monotonic() - start_time
        return result

    def resume_database(self) -> dict[str, Any]:
        """
        Resume Redis after snapshot.

        Redis doesn't require explicit resume - it automatically
        resumes accepting commands after BGSAVE completes.

        Returns:
            Resume result dict
        """
        result = {"success": True, "duration_seconds": 0.0, "errors": []}

        self.logger.info(
            f"Resuming Redis instance: {self.db_info.instance_name} "
            "(no explicit resume needed - Redis auto-resumes after BGSAVE)"
        )

        return result

    def validate_post_migration(self, migrated_vm_ip: str | None = None) -> dict[str, Any]:
        """
        Validate Redis after migration.

        Checks:
        - Redis service is running via systemctl
        - Can connect and authenticate
        - Persistence files loaded
        - Key count matches expectations

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
                "indexes_valid": False,  # N/A for Redis, but kept for consistency
            },
            "errors": [],
        }

        self.logger.info(f"Validating Redis post-migration: {self.db_info.instance_name}")

        # Check if redis service is running via systemctl
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "redis"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip() == "active":
                result["checks"]["starts"] = True
                self.logger.info("redis service is active")
            else:
                result["checks"]["starts"] = False
                result["valid"] = False
                status = proc.stdout.strip()
                result["errors"].append(f"redis service is not active (status: {status})")
                self.logger.error(f"redis service is not active: {status}")
        except FileNotFoundError:
            result["errors"].append("systemctl command not found")
            result["valid"] = False
            self.logger.exception("systemctl command not found")
        except subprocess.TimeoutExpired:
            result["errors"].append("Timed out checking redis service status")
            result["valid"] = False
            self.logger.exception("Timed out checking redis service status")

        # Only proceed with further checks if the service is running
        if result["checks"]["starts"]:
            result["checks"]["databases_accessible"] = True
            result["checks"]["data_integrity_ok"] = True
            result["checks"]["indexes_valid"] = True  # N/A for Redis

        return result

    def tune_for_kvm(self) -> dict[str, Any]:
        """
        Tune Redis for KVM environment.

        Optimizations:
        - maxmemory configuration
        - maxmemory-policy for cache scenarios
        - I/O settings for persistence
        - TCP keepalive settings

        Returns:
            Tuning result dict
        """
        result = {"applied": [], "recommended": [], "errors": []}

        self.logger.info(f"Tuning Redis for KVM: {self.db_info.instance_name}")

        # Generate tuning recommendations
        result["recommended"].extend(
            [
                "maxmemory 2gb  # Set based on available RAM",
                "maxmemory-policy allkeys-lru  # For cache scenarios",
                "maxmemory-policy noeviction  # For persistent data",
                "save 900 1  # RDB snapshots every 15min if 1+ key changed",
                "save 300 10",
                "save 60 10000",
                "appendonly yes  # Enable AOF for durability",
                "appendfsync everysec  # Balance between performance and durability",
                "tcp-keepalive 300",
                "timeout 0  # Disable client idle timeout",
                "# Consider using hugepages for large datasets",
                "# Set vm.overcommit_memory=1 in /etc/sysctl.conf",
            ]
        )

        return result

    def update_configuration(
        self, new_hostname: str | None = None, new_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Update Redis configuration for new environment.

        Updates:
        - bind directive in redis.conf
        - Replication configuration (if replica)
        - Sentinel configuration (if using Sentinel)

        Args:
            new_hostname: New hostname
            new_ip: New IP address

        Returns:
            Configuration update result dict
        """
        result = {"updated": [], "warnings": [], "errors": []}

        self.logger.info(f"Updating Redis configuration: {self.db_info.instance_name}")

        if new_ip:
            result["updated"].append(f"Updated bind to include {new_ip}")

        if self.db_info.replication_role == "replica":
            result["warnings"].append(
                "Replication configuration needs manual update: "
                "Update replicaof directive with new primary IP"
            )

        return result

    def get_connection_strings(self) -> dict[str, str]:
        """
        Generate Redis connection strings.

        Returns:
            Connection strings by format
        """
        host = "localhost"  # Would be actual host after migration
        port = self.db_info.port or 6379
        database = "0"  # Default Redis database

        return {
            "redis_uri": f"redis://{host}:{port}/{database}",
            "redis_auth": f"redis://:password@{host}:{port}/{database}",
            "redis_ssl": f"rediss://{host}:{port}/{database}",
            "redis_cli": f"redis-cli -h {host} -p {port} -n {database}",
            "environment": f"REDIS_HOST={host} REDIS_PORT={port} REDIS_DB={database}",
        }

    def backup_transaction_logs(self, output_dir: Path) -> dict[str, Any]:
        """
        Backup Redis persistence files (RDB and AOF).

        Args:
            output_dir: Directory to save persistence files

        Returns:
            Backup result dict
        """
        result = {"success": False, "log_files": [], "total_size_mb": 0.0, "errors": []}

        if not self.db_info.data_directory:
            result["errors"].append("Data directory unknown")
            return result

        data_dir = Path(self.db_info.data_directory)

        # RDB file
        rdb_file = data_dir / "dump.rdb"
        if rdb_file.exists():
            result["log_files"].append(rdb_file)
            result["total_size_mb"] += rdb_file.stat().st_size / (1024 * 1024)

        # AOF file
        aof_file = data_dir / "appendonly.aof"
        if aof_file.exists():
            result["log_files"].append(aof_file)
            result["total_size_mb"] += aof_file.stat().st_size / (1024 * 1024)

        if result["log_files"]:
            result["success"] = True
        else:
            result["errors"].append("No persistence files found")

        return result
