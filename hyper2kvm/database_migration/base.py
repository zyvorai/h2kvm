# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/database_migration/base.py
"""
Base database migration interface.

Defines abstract base class for database-specific migration handlers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseEngine(Enum):
    """Supported database engines."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    MONGODB = "mongodb"
    REDIS = "redis"
    ORACLE = "oracle"
    SQLSERVER = "sqlserver"
    CASSANDRA = "cassandra"
    ELASTICSEARCH = "elasticsearch"
    UNKNOWN = "unknown"


@dataclass
class DatabaseInfo:  # pylint: disable=too-many-instance-attributes
    # reason: models the full set of independent facts collected about a discovered
    # database instance (identity, location, status, replication, performance, config).
    """
    Database instance information.

    Metadata about discovered database instance.
    """

    # Identity
    engine: DatabaseEngine
    version: str
    instance_name: str | None = None
    port: int | None = None

    # Location
    data_directory: str | None = None
    config_file: str | None = None
    log_directory: str | None = None

    # Status
    running: bool = False
    pid: int | None = None

    # Databases
    databases: list[str] = field(default_factory=list)
    total_size_mb: float = 0.0

    # Replication
    replication_role: str | None = None  # primary, replica, standalone
    replication_lag_seconds: float | None = None

    # Performance
    connections: int = 0
    max_connections: int = 0
    cache_size_mb: float = 0.0

    # Configuration
    config: dict[str, Any] = field(default_factory=dict)

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatabaseMigrationResult:  # pylint: disable=too-many-instance-attributes
    # reason: models the full set of independent pre/post-migration outcome fields
    # (health checks, snapshot consistency, validation, timing) as a flat result record.
    """Database migration operation result."""

    success: bool
    engine: DatabaseEngine
    instance_name: str

    # Pre-migration
    health_check_passed: bool = False
    quiesce_successful: bool = False

    # Migration
    snapshot_consistent: bool = False
    transaction_logs_preserved: bool = False

    # Post-migration
    validation_passed: bool = False
    performance_tuned: bool = False
    replication_restored: bool = False

    # Details
    databases_migrated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # Timing
    pre_migration_duration_seconds: float = 0.0
    migration_duration_seconds: float = 0.0
    post_migration_duration_seconds: float = 0.0


class DatabaseMigrationHandler(ABC):
    """
    Abstract base class for database-specific migration handlers.

    Each database engine implements this interface.
    """

    def __init__(self, handler_logger: logging.Logger, db_info: DatabaseInfo):
        """
        Initialize database migration handler.

        Args:
            handler_logger: Logger instance
            db_info: DatabaseInfo object
        """
        self.logger = handler_logger
        self.db_info = db_info

    @abstractmethod
    def pre_migration_check(self) -> dict[str, Any]:
        """
        Perform pre-migration health checks.

        Checks:
        - Database is accessible
        - No corruption detected
        - Replication lag acceptable
        - Sufficient disk space
        - No long-running transactions
        - Backup recent and valid

        Returns:
            Health check result dict:
                {
                    "healthy": bool,
                    "checks": {
                        "accessible": bool,
                        "no_corruption": bool,
                        "replication_ok": bool,
                        "disk_space_ok": bool,
                        "no_long_transactions": bool
                    },
                    "warnings": list[str],
                    "errors": list[str]
                }
        """

    @abstractmethod
    def quiesce_database(self) -> dict[str, Any]:
        """
        Quiesce database for consistent snapshot.

        Operations:
        - Flush dirty buffers to disk
        - Checkpoint WAL/redo logs
        - Pause replication (if replica)
        - Set read-only mode (optional)
        - Wait for pending transactions

        Returns:
            Quiesce result dict:
                {
                    "success": bool,
                    "method": str,  # checkpoint, flush, read-only, etc.
                    "duration_seconds": float,
                    "errors": list[str]
                }
        """

    @abstractmethod
    def resume_database(self) -> dict[str, Any]:
        """
        Resume database after snapshot.

        Operations:
        - Exit read-only mode
        - Resume replication
        - Resume normal operations

        Returns:
            Resume result dict
        """

    @abstractmethod
    def validate_post_migration(self, migrated_vm_ip: str | None = None) -> dict[str, Any]:
        """
        Validate database after migration.

        Checks:
        - Database starts successfully
        - All databases accessible
        - Data integrity checks pass
        - Indexes valid
        - Statistics up to date

        Args:
            migrated_vm_ip: IP of migrated VM (for remote validation)

        Returns:
            Validation result dict:
                {
                    "valid": bool,
                    "checks": {
                        "starts": bool,
                        "databases_accessible": bool,
                        "data_integrity_ok": bool,
                        "indexes_valid": bool
                    },
                    "errors": list[str]
                }
        """

    @abstractmethod
    def tune_for_kvm(self) -> dict[str, Any]:
        """
        Tune database configuration for KVM environment.

        Optimizations:
        - Adjust shared memory settings
        - Tune I/O scheduler settings
        - Optimize cache sizes for VirtIO
        - Network buffer tuning
        - CPU affinity recommendations

        Returns:
            Tuning result dict:
                {
                    "applied": list[str],  # Applied tuning changes
                    "recommended": list[str],  # Manual recommendations
                    "errors": list[str]
                }
        """

    @abstractmethod
    def update_configuration(
        self, new_hostname: str | None = None, new_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Update database configuration for new environment.

        Updates:
        - Hostname in configuration
        - IP addresses in firewall rules
        - SSL certificates (if hostname changed)
        - Replication configuration

        Args:
            new_hostname: New hostname (if changed)
            new_ip: New IP address (if changed)

        Returns:
            Configuration update result dict
        """

    @abstractmethod
    def get_connection_strings(self) -> dict[str, str]:
        """
        Generate connection strings for applications.

        Returns:
            Dict of connection strings by format:
                {
                    "jdbc": "jdbc:postgresql://...",
                    "odbc": "Driver={PostgreSQL};...",
                    "native": "postgresql://user@host/db",
                    "environment": "PGHOST=... PGPORT=..."
                }
        """

    @abstractmethod
    def backup_transaction_logs(self, output_dir: Path) -> dict[str, Any]:
        """
        Backup transaction logs for point-in-time recovery.

        Args:
            output_dir: Directory to save transaction logs

        Returns:
            Backup result dict:
                {
                    "success": bool,
                    "log_files": list[Path],
                    "total_size_mb": float,
                    "errors": list[str]
                }
        """

    def get_engine(self) -> DatabaseEngine:
        """Get database engine type."""
        return self.db_info.engine

    def estimate_downtime(self) -> dict[str, Any]:
        """
        Estimate migration downtime for database.

        Factors:
        - Database size
        - Quiesce time
        - Snapshot time
        - Resume time

        Returns:
            Downtime estimation dict:
                {
                    "quiesce_seconds": float,
                    "snapshot_seconds": float,
                    "resume_seconds": float,
                    "total_seconds": float,
                    "notes": str
                }
        """
        # Default estimation
        db_size_gb = self.db_info.total_size_mb / 1024

        # Quiesce time: depends on active transactions and cache size
        quiesce_time = 5.0 + (self.db_info.cache_size_mb / 1000)  # ~1s per GB cache

        # Snapshot time: depends on storage backend (assume fast snapshots)
        snapshot_time = 2.0

        # Resume time
        resume_time = 3.0

        total = quiesce_time + snapshot_time + resume_time

        return {
            "quiesce_seconds": quiesce_time,
            "snapshot_seconds": snapshot_time,
            "resume_seconds": resume_time,
            "total_seconds": total,
            "notes": f"Estimated for {db_size_gb:.1f}GB database",
        }
