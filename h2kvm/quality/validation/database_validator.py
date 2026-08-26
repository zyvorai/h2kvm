# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/validation/database_validator.py
"""
Database validation for post-migration checks.

Validates database configurations after migration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .health_checker import HealthCheckResult, HealthCheckStatus, HealthCheckType

logger = logging.getLogger(__name__)


@dataclass
class DatabaseCheckResult:
    """Result of database validation check."""

    database_type: str
    status: HealthCheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class DatabaseValidator:
    """
    Database validator.

    Validates database configurations and data integrity.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize database validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def check_postgresql_config(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check PostgreSQL configuration.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            # Check for PostgreSQL data directory
            pg_data_paths = [
                "/var/lib/postgresql/data",
                "/var/lib/pgsql/data",
                "/var/lib/postgresql/*/main",
            ]

            pg_found = False
            pg_path = None

            for path in pg_data_paths:
                if "*" not in path and vmcraft_instance.exists(path):
                    pg_found = True
                    pg_path = path
                    break

            duration = (time.time() - start) * 1000

            if pg_found:
                # Check for postgresql.conf
                config_file = f"{pg_path}/postgresql.conf"
                config_exists = vmcraft_instance.exists(config_file)

                return HealthCheckResult(
                    check_id="postgresql_config",
                    check_type=HealthCheckType.DATABASE,
                    name="PostgreSQL Configuration",
                    status=HealthCheckStatus.PASS if config_exists else HealthCheckStatus.WARN,
                    message=f"PostgreSQL data directory found at {pg_path}",
                    details={
                        "data_dir": pg_path,
                        "config_exists": config_exists,
                    },
                    duration_ms=duration,
                )
            return HealthCheckResult(
                check_id="postgresql_config",
                check_type=HealthCheckType.DATABASE,
                name="PostgreSQL Configuration",
                status=HealthCheckStatus.SKIP,
                message="PostgreSQL not detected",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="postgresql_config",
                check_type=HealthCheckType.DATABASE,
                name="PostgreSQL Configuration",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def check_mysql_config(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check MySQL/MariaDB configuration.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            # Check for MySQL data directory
            mysql_data_paths = [
                "/var/lib/mysql",
                "/var/lib/mariadb",
            ]

            mysql_found = False
            mysql_path = None

            for path in mysql_data_paths:
                if vmcraft_instance.exists(path):
                    mysql_found = True
                    mysql_path = path
                    break

            duration = (time.time() - start) * 1000

            if mysql_found:
                # Check for my.cnf
                config_files = [
                    "/etc/my.cnf",
                    "/etc/mysql/my.cnf",
                    "/etc/mysql/mysql.conf.d/mysqld.cnf",
                ]

                config_exists = False
                for config in config_files:
                    if vmcraft_instance.exists(config):
                        config_exists = True
                        break

                return HealthCheckResult(
                    check_id="mysql_config",
                    check_type=HealthCheckType.DATABASE,
                    name="MySQL/MariaDB Configuration",
                    status=HealthCheckStatus.PASS if config_exists else HealthCheckStatus.WARN,
                    message=f"MySQL data directory found at {mysql_path}",
                    details={
                        "data_dir": mysql_path,
                        "config_exists": config_exists,
                    },
                    duration_ms=duration,
                )
            return HealthCheckResult(
                check_id="mysql_config",
                check_type=HealthCheckType.DATABASE,
                name="MySQL/MariaDB Configuration",
                status=HealthCheckStatus.SKIP,
                message="MySQL/MariaDB not detected",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="mysql_config",
                check_type=HealthCheckType.DATABASE,
                name="MySQL/MariaDB Configuration",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def validate_databases(self, vmcraft_instance) -> list[HealthCheckResult]:
        """
        Run all database validation checks.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            List of health check results
        """
        return [
            self.check_postgresql_config(vmcraft_instance),
            self.check_mysql_config(vmcraft_instance),
        ]
