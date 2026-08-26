# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/database_migration/detector.py
"""
Database detection for VM disk images.

Scans VM filesystem for database installations and configurations.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base import DatabaseEngine, DatabaseInfo

logger = logging.getLogger(__name__)


class DatabaseDetector:
    """
    Detects database installations in VM disk images.

    Scans for:
    - Database binaries
    - Configuration files
    - Data directories
    - Running processes (if VM is live)
    """

    def __init__(self, logger_instance: logging.Logger):
        """
        Initialize database detector.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance

    def detect_databases(self, vmcraft_instance) -> list[DatabaseInfo]:
        """
        Detect all databases in VM.

        Args:
            vmcraft_instance: Launched VMCraft instance with mounted filesystem

        Returns:
            List of DatabaseInfo objects
        """
        databases = []

        # Detect each database type
        databases.extend(self._detect_postgresql(vmcraft_instance))
        databases.extend(self._detect_mysql(vmcraft_instance))
        databases.extend(self._detect_mongodb(vmcraft_instance))
        databases.extend(self._detect_redis(vmcraft_instance))
        databases.extend(self._detect_sqlserver(vmcraft_instance))

        self.logger.info(f"Detected {len(databases)} database instances")
        return databases

    def _detect_postgresql(self, g) -> list[DatabaseInfo]:
        """Detect PostgreSQL installations."""
        databases = []

        # Check for PostgreSQL binaries
        postgres_bin = "/usr/lib/postgresql"
        if g.exists(postgres_bin):
            # Find installed versions
            versions = []
            try:
                if g.is_dir(postgres_bin):
                    entries = g.ls(postgres_bin)
                    for entry in entries:
                        if re.match(r"\d+", entry):
                            versions.append(entry)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                self.logger.debug(f"Failed to list PostgreSQL versions: {e}")

            for version in versions:
                db_info = DatabaseInfo(
                    engine=DatabaseEngine.POSTGRESQL,
                    version=version,
                    instance_name=f"postgresql-{version}",
                    port=5432,
                    data_directory=f"/var/lib/postgresql/{version}/main",
                    config_file=f"/etc/postgresql/{version}/main/postgresql.conf",
                    log_directory="/var/log/postgresql",
                )

                # Try to read configuration
                if g.exists(db_info.config_file):
                    try:
                        config_content = g.read_file(db_info.config_file)
                        db_info.config = self._parse_postgresql_config(config_content)
                    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                        self.logger.debug(f"Failed to read PostgreSQL config: {e}")

                databases.append(db_info)

        return databases

    def _detect_mysql(self, g) -> list[DatabaseInfo]:
        """Detect MySQL/MariaDB installations."""
        databases = []

        # Check for MySQL/MariaDB
        mysql_paths = ["/usr/bin/mysqld", "/usr/sbin/mysqld"]

        for mysql_bin in mysql_paths:
            if g.exists(mysql_bin):
                # Determine if MySQL or MariaDB
                engine = DatabaseEngine.MYSQL

                # Try to detect version
                version = "unknown"

                db_info = DatabaseInfo(
                    engine=engine,
                    version=version,
                    instance_name="mysql",
                    port=3306,
                    data_directory="/var/lib/mysql",
                    config_file="/etc/mysql/my.cnf",
                    log_directory="/var/log/mysql",
                )

                # Read MySQL configuration
                config_paths = ["/etc/mysql/my.cnf", "/etc/my.cnf", "/etc/mysql/mysql.conf.d/mysqld.cnf"]

                for config_path in config_paths:
                    if g.exists(config_path):
                        try:
                            config_content = g.read_file(config_path)
                            db_info.config = self._parse_mysql_config(config_content)
                            db_info.config_file = config_path
                            break
                        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                            self.logger.debug(f"Failed to read MySQL config: {e}")

                databases.append(db_info)
                break  # Only add one MySQL instance

        return databases

    def _detect_mongodb(self, g) -> list[DatabaseInfo]:
        """Detect MongoDB installations."""
        databases = []

        # Check for MongoDB
        mongod_paths = ["/usr/bin/mongod", "/usr/local/bin/mongod"]

        for mongod_bin in mongod_paths:
            if g.exists(mongod_bin):
                db_info = DatabaseInfo(
                    engine=DatabaseEngine.MONGODB,
                    version="unknown",
                    instance_name="mongodb",
                    port=27017,
                    data_directory="/var/lib/mongodb",
                    config_file="/etc/mongod.conf",
                    log_directory="/var/log/mongodb",
                )

                # Read MongoDB configuration
                if g.exists("/etc/mongod.conf"):
                    try:
                        config_content = g.read_file("/etc/mongod.conf")
                        # MongoDB uses YAML config
                        # Simplified parsing
                        db_info.config = {"raw": config_content}
                    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                        self.logger.debug(f"Failed to read MongoDB config: {e}")

                databases.append(db_info)
                break

        return databases

    def _detect_redis(self, g) -> list[DatabaseInfo]:
        """Detect Redis installations."""
        databases = []

        # Check for Redis
        redis_paths = ["/usr/bin/redis-server", "/usr/local/bin/redis-server"]

        for redis_bin in redis_paths:
            if g.exists(redis_bin):
                db_info = DatabaseInfo(
                    engine=DatabaseEngine.REDIS,
                    version="unknown",
                    instance_name="redis",
                    port=6379,
                    data_directory="/var/lib/redis",
                    config_file="/etc/redis/redis.conf",
                    log_directory="/var/log/redis",
                )

                # Read Redis configuration
                config_paths = ["/etc/redis/redis.conf", "/etc/redis.conf"]

                for config_path in config_paths:
                    if g.exists(config_path):
                        try:
                            config_content = g.read_file(config_path)
                            db_info.config = self._parse_redis_config(config_content)
                            db_info.config_file = config_path
                            break
                        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                            self.logger.debug(f"Failed to read Redis config: {e}")

                databases.append(db_info)
                break

        return databases

    def _detect_sqlserver(self, g) -> list[DatabaseInfo]:
        """Detect SQL Server installations (Windows)."""
        databases = []

        # Check for SQL Server (Windows only)
        sqlserver_paths = [
            "/Program Files/Microsoft SQL Server",
            "/Program Files (x86)/Microsoft SQL Server",
        ]

        for sql_path in sqlserver_paths:
            if g.exists(sql_path):
                # SQL Server detected
                db_info = DatabaseInfo(
                    engine=DatabaseEngine.SQLSERVER,
                    version="unknown",
                    instance_name="MSSQLSERVER",
                    port=1433,
                    data_directory=f"{sql_path}/MSSQL*/MSSQL/DATA",
                    config_file=None,
                    metadata={"windows": True},
                )

                databases.append(db_info)
                break

        return databases

    def _parse_postgresql_config(self, config_content: str) -> dict[str, Any]:
        """Parse PostgreSQL configuration file."""
        config = {}

        # pylint: disable=duplicate-code
        # reason: mirrors similar "split key/value lines" PostgreSQL config
        # parsing loops in vmcraft/database_detector.py and
        # vmcraft/enhanced_inspection.py (sysctl.conf parsing) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated config-parsing code paths.
        for line in config_content.splitlines():
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse key = value
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'\"")

                config[key] = value

        return config

    def _parse_mysql_config(self, config_content: str) -> dict[str, Any]:
        """Parse MySQL/MariaDB configuration file."""
        config = {}
        current_section = None

        # pylint: disable=duplicate-code
        # reason: this INI-style section/key=value parsing loop mirrors a
        # similar loop in vmcraft/enhanced_inspection.py (NetworkManager
        # keyfile parsing) -- structurally similar by coincidence, not
        # shared logic; keeping independent avoids coupling unrelated
        # config-parsing code paths.
        for line in config_content.splitlines():
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith(("#", ";")):
                continue

            # Section header
            if line.startswith("["):
                current_section = line.strip("[]")
                config[current_section] = {}
                continue

            # Key-value pair
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if current_section:
                    config[current_section][key] = value
                else:
                    config[key] = value

        return config

    def _parse_redis_config(self, config_content: str) -> dict[str, Any]:
        """Parse Redis configuration file."""
        config = {}

        for line in config_content.splitlines():
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse key value (space-separated)
            parts = line.split(None, 1)
            if len(parts) == 2:
                key, value = parts
                config[key] = value

        return config

    def get_database_summary(self, databases: list[DatabaseInfo]) -> dict[str, Any]:
        """
        Generate summary of detected databases.

        Args:
            databases: List of DatabaseInfo objects

        Returns:
            Summary dict:
                {
                    "total_databases": int,
                    "by_engine": {engine: count},
                    "total_size_mb": float,
                    "requires_special_handling": list[str]
                }
        """
        summary = {
            "total_databases": len(databases),
            "by_engine": {},
            "total_size_mb": 0.0,
            "requires_special_handling": [],
        }

        for db in databases:
            engine_name = db.engine.value
            summary["by_engine"][engine_name] = summary["by_engine"].get(engine_name, 0) + 1
            summary["total_size_mb"] += db.total_size_mb

            # Flag databases that need special handling
            if db.replication_role in ["primary", "replica"]:
                summary["requires_special_handling"].append(
                    f"{db.instance_name} (replication: {db.replication_role})"
                )

            if db.total_size_mb > 100000:  # > 100GB
                summary["requires_special_handling"].append(
                    f"{db.instance_name} (large: {db.total_size_mb / 1024:.1f}GB)"
                )

        return summary
