# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/database_detector.py
"""
Database detection and configuration analysis.

Provides comprehensive database detection:
- MySQL/MariaDB (configuration, users, databases)
- PostgreSQL (configuration, roles, databases)
- MongoDB (configuration, users, databases)
- Redis (configuration, persistence settings)
- SQLite (database file detection)
- Oracle Database (basic detection)
- Microsoft SQL Server (basic detection)

Features:
- Detect installed databases
- Parse configuration files
- List databases and users
- Identify data directories
- Check security settings
- Version detection
"""

# pylint: disable=duplicate-code
# reason: this module has 4+ small config-parsing blocks (MySQL/Redis/
# PostgreSQL key=value loops, SQLite search-path scans) that are
# structurally similar to blocks in several sibling vmcraft detector
# modules (e.g. enhanced_inspection.py, app_framework_detector.py,
# database_migration/detector.py, backup_analysis.py) by coincidence, not
# shared logic; keeping each independently editable avoids coupling
# unrelated detector code paths. See git history for the pylint pass that
# reviewed each instance.

from __future__ import annotations

from typing import Any

from .base_analyzer import BaseAnalyzer


class DatabaseDetector(BaseAnalyzer):
    """
    Database detection and analysis.

    Detects and analyzes database installations on VMs.
    """

    def detect_databases(self) -> dict[str, Any]:
        """
        Detect all database installations.

        Returns:
            Database detection results
        """
        databases: dict[str, Any] = {
            "mysql": None,
            "postgresql": None,
            "mongodb": None,
            "redis": None,
            "sqlite_files": [],
            "oracle": None,
            "mssql": None,
            "detected_count": 0,
        }

        # Detect MySQL/MariaDB
        mysql = self._detect_mysql()
        if mysql.get("installed"):
            databases["mysql"] = mysql
            databases["detected_count"] += 1

        # Detect PostgreSQL
        postgresql = self._detect_postgresql()
        if postgresql.get("installed"):
            databases["postgresql"] = postgresql
            databases["detected_count"] += 1

        # Detect MongoDB
        mongodb = self._detect_mongodb()
        if mongodb.get("installed"):
            databases["mongodb"] = mongodb
            databases["detected_count"] += 1

        # Detect Redis
        redis = self._detect_redis()
        if redis.get("installed"):
            databases["redis"] = redis
            databases["detected_count"] += 1

        # Find SQLite files
        sqlite_files = self._find_sqlite_files()
        if sqlite_files:
            databases["sqlite_files"] = sqlite_files

        # Detect Oracle (basic)
        oracle = self._detect_oracle()
        if oracle.get("installed"):
            databases["oracle"] = oracle
            databases["detected_count"] += 1

        # Detect MS SQL Server (basic)
        mssql = self._detect_mssql()
        if mssql.get("installed"):
            databases["mssql"] = mssql
            databases["detected_count"] += 1

        return databases

    def _detect_mysql(self) -> dict[str, Any]:
        """Detect MySQL/MariaDB installation."""
        mysql: dict[str, Any] = {
            "installed": False,
            "type": None,  # mysql or mariadb
            "version": None,
            "config_file": None,
            "data_dir": None,
            "port": 3306,
            "bind_address": None,
            "users": [],
            "databases": [],
        }

        # Check for MySQL/MariaDB binaries
        mysql_paths = [
            "/usr/bin/mysqld",
            "/usr/sbin/mysqld",
            "/usr/local/mysql/bin/mysqld",
        ]

        for path in mysql_paths:
            if self.file_ops.exists(path):
                mysql["installed"] = True
                break

        if not mysql["installed"]:
            return mysql

        # Determine if MySQL or MariaDB
        if self.file_ops.exists("/usr/bin/mariadb") or self.file_ops.exists("/etc/mysql/mariadb.cnf"):
            mysql["type"] = "mariadb"
        else:
            mysql["type"] = "mysql"

        # Parse configuration
        config_paths = [
            "/etc/my.cnf",
            "/etc/mysql/my.cnf",
            "/etc/mysql/mysql.conf.d/mysqld.cnf",
        ]

        for config_path in config_paths:
            if self.file_ops.exists(config_path):
                mysql["config_file"] = config_path
                config = self._parse_mysql_config(config_path)
                mysql.update(config)
                break

        # Check data directory
        if mysql.get("data_dir") and self.file_ops.is_dir(mysql["data_dir"]):
            # List databases (directories in data_dir)
            try:
                db_dirs = self.file_ops.ls(mysql["data_dir"])
                # Filter out system files
                mysql["databases"] = [
                    d
                    for d in db_dirs
                    if not d.startswith(".")
                    and d not in ["mysql", "performance_schema", "information_schema", "sys"]
                ]
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
                pass

        return mysql

    def _parse_mysql_config(self, config_path: str) -> dict[str, Any]:
        """Parse MySQL configuration file."""
        config = {}

        try:
            content = self.file_ops.cat(config_path)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "[")):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"')

                    if key == "datadir":
                        config["data_dir"] = value
                    elif key == "port":
                        config["port"] = int(value)
                    elif key == "bind-address":
                        config["bind_address"] = value

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
            self.logger.debug(f"Failed to parse MySQL config: {e}")

        return config

    def _detect_postgresql(  # pylint: disable=too-many-branches  # covers multiple binary/config path patterns and version fallbacks
        self,
    ) -> dict[str, Any]:
        """Detect PostgreSQL installation."""
        postgresql: dict[str, Any] = {
            "installed": False,
            "version": None,
            "config_file": None,
            "data_dir": None,
            "port": 5432,
            "listen_addresses": None,
            "databases": [],
        }

        # Check for PostgreSQL binary
        pg_paths = [
            "/usr/bin/postgres",
            "/usr/lib/postgresql/*/bin/postgres",
        ]

        for path_pattern in pg_paths:
            # Simple check without glob
            if "*" not in path_pattern:
                if self.file_ops.exists(path_pattern):
                    postgresql["installed"] = True
                    break
            else:
                # Check common version paths
                for ver in ["16", "15", "14", "13", "12", "11", "10"]:
                    path = path_pattern.replace("*", ver)
                    if self.file_ops.exists(path):
                        postgresql["installed"] = True
                        postgresql["version"] = ver
                        break
                if postgresql["installed"]:
                    break

        if not postgresql["installed"]:
            return postgresql

        # Parse configuration
        config_paths = [
            "/etc/postgresql/*/main/postgresql.conf",
            "/var/lib/pgsql/data/postgresql.conf",
        ]

        for config_pattern in config_paths:
            if "*" not in config_pattern:
                if self.file_ops.exists(config_pattern):
                    postgresql["config_file"] = config_pattern
                    config = self._parse_postgresql_config(config_pattern)
                    postgresql.update(config)
                    break
            else:
                # Check common version paths
                for ver in ["16", "15", "14", "13", "12", "11", "10"]:
                    config_path = config_pattern.replace("*", ver)
                    if self.file_ops.exists(config_path):
                        postgresql["config_file"] = config_path
                        config = self._parse_postgresql_config(config_path)
                        postgresql.update(config)
                        break
                if postgresql["config_file"]:
                    break

        return postgresql

    def _parse_postgresql_config(self, config_path: str) -> dict[str, Any]:
        """Parse PostgreSQL configuration file."""
        config = {}

        try:
            content = self.file_ops.cat(config_path)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")

                    if key == "data_directory":
                        config["data_dir"] = value
                    elif key == "port":
                        config["port"] = int(value)
                    elif key == "listen_addresses":
                        config["listen_addresses"] = value

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
            self.logger.debug(f"Failed to parse PostgreSQL config: {e}")

        return config

    def _detect_mongodb(self) -> dict[str, Any]:
        """Detect MongoDB installation."""
        mongodb: dict[str, Any] = {
            "installed": False,
            "version": None,
            "config_file": None,
            "data_dir": None,
            "port": 27017,
            "bind_ip": None,
        }

        # Check for MongoDB binary
        if self.file_ops.exists("/usr/bin/mongod"):
            mongodb["installed"] = True

        if not mongodb["installed"]:
            return mongodb

        # Parse configuration
        config_path = "/etc/mongod.conf"
        if self.file_ops.exists(config_path):
            mongodb["config_file"] = config_path
            config = self._parse_mongodb_config(config_path)
            mongodb.update(config)

        return mongodb

    def _parse_mongodb_config(self, config_path: str) -> dict[str, Any]:
        """Parse MongoDB configuration file (YAML format)."""
        config = {}

        try:
            content = self.file_ops.cat(config_path)

            # Simple YAML parsing for common keys
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "dbPath":
                        config["data_dir"] = value
                    elif key == "port":
                        config["port"] = int(value)
                    elif key == "bindIp":
                        config["bind_ip"] = value

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
            self.logger.debug(f"Failed to parse MongoDB config: {e}")

        return config

    def _detect_redis(self) -> dict[str, Any]:
        """Detect Redis installation."""
        redis: dict[str, Any] = {
            "installed": False,
            "version": None,
            "config_file": None,
            "data_dir": None,
            "port": 6379,
            "bind": None,
            "persistence": None,
        }

        # Check for Redis binary
        if self.file_ops.exists("/usr/bin/redis-server"):
            redis["installed"] = True

        if not redis["installed"]:
            return redis

        # Parse configuration
        config_path = "/etc/redis/redis.conf"
        if self.file_ops.exists(config_path):
            redis["config_file"] = config_path
            config = self._parse_redis_config(config_path)
            redis.update(config)

        return redis

    def _parse_redis_config(self, config_path: str) -> dict[str, Any]:
        """Parse Redis configuration file."""
        config = {}

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
                value = " ".join(parts[1:])

                if key == "dir":
                    config["data_dir"] = value
                elif key == "port":
                    config["port"] = int(value)
                elif key == "bind":
                    config["bind"] = value
                elif key in ["save", "appendonly"]:
                    config["persistence"] = key

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
            self.logger.debug(f"Failed to parse Redis config: {e}")

        return config

    def _find_sqlite_files(  # pylint: disable=too-many-nested-blocks  # nested best-effort scan/stat/limit-check loop over candidate DB files
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find SQLite database files."""
        sqlite_files = []

        # Common locations for SQLite databases
        search_paths = [
            "/var/lib",
            "/usr/local/share",
            "/opt",
        ]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                # Use find with depth limit
                # Look for .db, .sqlite, .sqlite3 files
                files = self.file_ops.find(search_path)
                for file in files[:100]:  # Limit search
                    if file.endswith((".db", ".sqlite", ".sqlite3")):
                        try:
                            stat = self.file_ops.stat(file)
                            sqlite_files.append(
                                {
                                    "path": file,
                                    "size_bytes": stat.get("size", 0),
                                    "size_mb": round(stat.get("size", 0) / (1024 * 1024), 2),
                                }
                            )

                            if len(sqlite_files) >= limit:
                                break
                        except Exception:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
                            pass

                if len(sqlite_files) >= limit:
                    break

            except Exception:  # pylint: disable=broad-exception-caught  # best-effort DB detection/parsing, must not abort the whole scan
                pass

        return sqlite_files

    def _detect_oracle(self) -> dict[str, Any]:
        """Detect Oracle Database (basic)."""
        oracle: dict[str, Any] = {
            "installed": False,
            "oracle_home": None,
            "version": None,
        }

        # Check for Oracle directories
        oracle_paths = [
            "/u01/app/oracle",
            "/opt/oracle",
        ]

        for path in oracle_paths:
            if self.file_ops.is_dir(path):
                oracle["installed"] = True
                oracle["oracle_home"] = path
                break

        return oracle

    def _detect_mssql(self) -> dict[str, Any]:
        """Detect Microsoft SQL Server (basic)."""
        mssql: dict[str, Any] = {
            "installed": False,
            "version": None,
        }

        # Check for SQL Server on Linux
        if self.file_ops.exists("/opt/mssql/bin/sqlservr"):
            mssql["installed"] = True

        return mssql

    def get_database_summary(self, databases: dict[str, Any]) -> dict[str, Any]:
        """
        Get database summary.

        Args:
            databases: Database detection results

        Returns:
            Summary dictionary
        """
        return {
            "total_databases": databases.get("detected_count", 0),
            "mysql_installed": databases.get("mysql", {}).get("installed", False),
            "postgresql_installed": databases.get("postgresql", {}).get("installed", False),
            "mongodb_installed": databases.get("mongodb", {}).get("installed", False),
            "redis_installed": databases.get("redis", {}).get("installed", False),
            "sqlite_file_count": len(databases.get("sqlite_files", [])),
        }

    def check_database_security(self, databases: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Check database security settings.

        Args:
            databases: Database detection results

        Returns:
            List of security issues
        """
        issues = []

        # Check MySQL
        mysql = databases.get("mysql")
        if mysql and mysql.get("installed") and mysql.get("bind_address") == "0.0.0.0":
            issues.append(
                {
                    "database": "mysql",
                    "severity": "medium",
                    "issue": "MySQL listening on all interfaces (0.0.0.0)",
                    "recommendation": "Bind to specific interface or localhost",
                }
            )

        # Check PostgreSQL
        postgresql = databases.get("postgresql")
        if postgresql and postgresql.get("installed") and postgresql.get("listen_addresses") == "*":
            issues.append(
                {
                    "database": "postgresql",
                    "severity": "medium",
                    "issue": "PostgreSQL listening on all interfaces (*)",
                    "recommendation": "Bind to specific interface or localhost",
                }
            )

        # Check MongoDB
        mongodb = databases.get("mongodb")
        if mongodb and mongodb.get("installed") and mongodb.get("bind_ip") == "0.0.0.0":
            issues.append(
                {
                    "database": "mongodb",
                    "severity": "medium",
                    "issue": "MongoDB listening on all interfaces (0.0.0.0)",
                    "recommendation": "Bind to specific interface or localhost",
                }
            )

        # Check Redis
        redis = databases.get("redis")
        if redis and redis.get("installed") and redis.get("bind") == "0.0.0.0":
            issues.append(
                {
                    "database": "redis",
                    "severity": "high",
                    "issue": "Redis listening on all interfaces (0.0.0.0)",
                    "recommendation": "Bind to localhost and enable authentication",
                }
            )

        return issues
