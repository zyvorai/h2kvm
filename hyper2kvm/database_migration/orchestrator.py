# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/database_migration/orchestrator.py
"""
Database migration orchestrator.

Coordinates database-aware migration workflow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import (
    DatabaseEngine,
    DatabaseInfo,
    DatabaseMigrationHandler,
)
from .detector import DatabaseDetector
from .generic import GenericDatabaseHandler
from .mongodb import MongoDBHandler
from .mysql import MySQLHandler
from .postgresql import PostgreSQLHandler
from .redis import RedisHandler

logger = logging.getLogger(__name__)


class DatabaseMigrationOrchestrator:
    """
    Orchestrates database-aware VM migration.

    Workflow:
    1. Detect databases in VM
    2. Pre-migration health checks
    3. Quiesce databases for consistent snapshot
    4. Resume databases after snapshot
    5. Post-migration validation
    6. KVM performance tuning
    7. Configuration updates
    """

    def __init__(self, logger_instance: logging.Logger):
        """
        Initialize database migration orchestrator.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance
        self.detector = DatabaseDetector(logger_instance)

    def detect_databases(self, vmcraft_instance) -> list[DatabaseInfo]:
        """
        Detect all databases in VM.

        Args:
            vmcraft_instance: Launched VMCraft instance

        Returns:
            List of detected DatabaseInfo objects
        """
        self.logger.info("Scanning VM for database installations...")
        databases = self.detector.detect_databases(vmcraft_instance)

        if databases:
            self.logger.info(f"Detected {len(databases)} database instance(s):")
            for db in databases:
                self.logger.info(f"  - {db.engine.value} {db.version} ({db.instance_name or 'default'})")
        else:
            self.logger.info("No databases detected in VM")

        return databases

    def get_handler(self, db_info: DatabaseInfo) -> DatabaseMigrationHandler:
        """
        Get appropriate handler for database engine.

        Args:
            db_info: Database information

        Returns:
            DatabaseMigrationHandler instance
        """
        handler_map = {
            DatabaseEngine.POSTGRESQL: PostgreSQLHandler,
            DatabaseEngine.MYSQL: MySQLHandler,
            DatabaseEngine.MARIADB: MySQLHandler,  # Use MySQL handler
            DatabaseEngine.MONGODB: MongoDBHandler,
            DatabaseEngine.REDIS: RedisHandler,
        }

        handler_class = handler_map.get(db_info.engine, GenericDatabaseHandler)
        return handler_class(self.logger, db_info)

    def pre_migration_checks(self, databases: list[DatabaseInfo]) -> dict[str, Any]:
        """
        Run pre-migration health checks on all databases.

        Args:
            databases: List of detected databases

        Returns:
            Summary of health check results:
                {
                    "all_healthy": bool,
                    "checks": list[dict],  # Per-database results
                    "critical_errors": list[str],
                    "warnings": list[str]
                }
        """
        self.logger.info("Running pre-migration health checks...")

        results = {"all_healthy": True, "checks": [], "critical_errors": [], "warnings": []}

        for db_info in databases:
            handler = self.get_handler(db_info)
            check_result = handler.pre_migration_check()

            check_summary = {
                "engine": db_info.engine.value,
                "instance": db_info.instance_name,
                "healthy": check_result["healthy"],
                "checks": check_result["checks"],
                "errors": check_result["errors"],
                "warnings": check_result["warnings"],
            }

            results["checks"].append(check_summary)

            if not check_result["healthy"]:
                results["all_healthy"] = False
                results["critical_errors"].extend(
                    [f"{db_info.instance_name}: {err}" for err in check_result["errors"]]
                )

            results["warnings"].extend(
                [f"{db_info.instance_name}: {warn}" for warn in check_result["warnings"]]
            )

        if results["all_healthy"]:
            self.logger.info("✓ All database health checks passed")
        else:
            self.logger.warning(f"⚠ {len(results['critical_errors'])} critical error(s) found")

        return results

    def quiesce_databases(self, databases: list[DatabaseInfo]) -> dict[str, Any]:
        """
        Quiesce all databases for consistent snapshot.

        Args:
            databases: List of databases to quiesce

        Returns:
            Quiesce results summary
        """
        self.logger.info("Quiescing databases for snapshot...")

        results = {"success": True, "databases": [], "total_duration_seconds": 0.0, "errors": []}

        for db_info in databases:
            handler = self.get_handler(db_info)
            quiesce_result = handler.quiesce_database()

            db_result = {
                "engine": db_info.engine.value,
                "instance": db_info.instance_name,
                "success": quiesce_result["success"],
                "method": quiesce_result["method"],
                "duration_seconds": quiesce_result["duration_seconds"],
                "errors": quiesce_result["errors"],
            }

            results["databases"].append(db_result)
            results["total_duration_seconds"] += quiesce_result["duration_seconds"]

            if not quiesce_result["success"]:
                results["success"] = False
                results["errors"].extend(
                    [f"{db_info.instance_name}: {err}" for err in quiesce_result["errors"]]
                )

        if results["success"]:
            self.logger.info(f"✓ All databases quiesced (total: {results['total_duration_seconds']:.1f}s)")
        else:
            self.logger.error("✗ Database quiesce failed")

        return results

    def resume_databases(self, databases: list[DatabaseInfo]) -> dict[str, Any]:
        """
        Resume all databases after snapshot.

        Args:
            databases: List of databases to resume

        Returns:
            Resume results summary
        """
        self.logger.info("Resuming databases after snapshot...")

        results = {"success": True, "databases": [], "total_duration_seconds": 0.0, "errors": []}

        for db_info in databases:
            handler = self.get_handler(db_info)
            resume_result = handler.resume_database()

            db_result = {
                "engine": db_info.engine.value,
                "instance": db_info.instance_name,
                "success": resume_result["success"],
                "duration_seconds": resume_result["duration_seconds"],
                "errors": resume_result["errors"],
            }

            results["databases"].append(db_result)
            results["total_duration_seconds"] += resume_result["duration_seconds"]

            if not resume_result["success"]:
                results["success"] = False
                results["errors"].extend(
                    [f"{db_info.instance_name}: {err}" for err in resume_result["errors"]]
                )

        if results["success"]:
            self.logger.info(f"✓ All databases resumed (total: {results['total_duration_seconds']:.1f}s)")
        else:
            self.logger.error("✗ Database resume failed")

        return results

    def validate_post_migration(
        self, databases: list[DatabaseInfo], migrated_vm_ip: str | None = None
    ) -> dict[str, Any]:
        """
        Validate databases after migration.

        Args:
            databases: List of databases to validate
            migrated_vm_ip: IP of migrated VM (for remote validation)

        Returns:
            Validation results summary
        """
        self.logger.info("Validating databases after migration...")

        results = {"all_valid": True, "validations": [], "errors": [], "warnings": []}

        for db_info in databases:
            handler = self.get_handler(db_info)
            validation_result = handler.validate_post_migration(migrated_vm_ip)

            validation_summary = {
                "engine": db_info.engine.value,
                "instance": db_info.instance_name,
                "valid": validation_result["valid"],
                "checks": validation_result["checks"],
                "errors": validation_result.get("errors", []),
                "warnings": validation_result.get("warnings", []),
            }

            results["validations"].append(validation_summary)

            if not validation_result["valid"]:
                results["all_valid"] = False
                results["errors"].extend(
                    [f"{db_info.instance_name}: {err}" for err in validation_result.get("errors", [])]
                )

            results["warnings"].extend(
                [f"{db_info.instance_name}: {warn}" for warn in validation_result.get("warnings", [])]
            )

        if results["all_valid"]:
            self.logger.info("✓ All database validations passed")
        else:
            self.logger.warning(f"⚠ {len(results['errors'])} validation error(s) found")

        return results

    def tune_for_kvm(self, databases: list[DatabaseInfo]) -> dict[str, Any]:
        """
        Apply KVM performance tuning for databases.

        Args:
            databases: List of databases to tune

        Returns:
            Tuning results summary
        """
        self.logger.info("Generating KVM performance tuning recommendations...")

        results = {"databases": [], "all_applied": [], "all_recommended": []}

        for db_info in databases:
            handler = self.get_handler(db_info)
            tuning_result = handler.tune_for_kvm()

            db_tuning = {
                "engine": db_info.engine.value,
                "instance": db_info.instance_name,
                "applied": tuning_result["applied"],
                "recommended": tuning_result["recommended"],
                "errors": tuning_result["errors"],
            }

            results["databases"].append(db_tuning)
            results["all_applied"].extend(tuning_result["applied"])
            results["all_recommended"].extend(tuning_result["recommended"])

        self.logger.info(f"Generated {len(results['all_recommended'])} tuning recommendation(s)")

        return results

    def generate_migration_guide(
        self, databases: list[DatabaseInfo], new_hostname: str | None = None, new_ip: str | None = None
    ) -> str:
        """
        Generate post-migration guide for database administrators.

        Args:
            databases: List of migrated databases
            new_hostname: New hostname after migration
            new_ip: New IP address after migration

        Returns:
            Markdown-formatted migration guide
        """
        guide_lines = [
            "# Database Migration Post-Migration Guide",
            "",
            f"**Generated**: {__import__('datetime').datetime.now().isoformat()}",
            f"**Databases Migrated**: {len(databases)}",
            "",
        ]

        if new_hostname:
            guide_lines.append(f"**New Hostname**: {new_hostname}")
        if new_ip:
            guide_lines.append(f"**New IP Address**: {new_ip}")

        guide_lines.extend(["", "---", ""])

        for db_info in databases:
            handler = self.get_handler(db_info)

            guide_lines.extend(
                [
                    f"## {db_info.engine.value.upper()} - {db_info.instance_name or 'default'}",
                    "",
                    f"**Version**: {db_info.version}",
                    f"**Data Directory**: {db_info.data_directory or 'N/A'}",
                    f"**Config File**: {db_info.config_file or 'N/A'}",
                    "",
                ]
            )

            # Configuration updates
            config_result = handler.update_configuration(new_hostname, new_ip)
            if config_result["updated"]:
                guide_lines.extend(["### Configuration Updates Applied", ""])
                for update in config_result["updated"]:
                    guide_lines.append(f"- {update}")
                guide_lines.append("")

            if config_result["warnings"]:
                guide_lines.extend(["### ⚠ Manual Actions Required", ""])
                for warning in config_result["warnings"]:
                    guide_lines.append(f"- {warning}")
                guide_lines.append("")

            # Connection strings
            conn_strings = handler.get_connection_strings()
            guide_lines.extend(["### Connection Strings", "", "```"])
            for format_name, conn_str in conn_strings.items():
                guide_lines.append(f"{format_name}: {conn_str}")
            guide_lines.extend(["```", ""])

            # Tuning recommendations
            tuning = handler.tune_for_kvm()
            if tuning["recommended"]:
                guide_lines.extend(["### Performance Tuning Recommendations", "", "```"])
                guide_lines.extend(tuning["recommended"])
                guide_lines.extend(["```", ""])

            guide_lines.append("---")
            guide_lines.append("")

        return "\n".join(guide_lines)

    def orchestrate_migration(
        self,
        vmcraft_instance,
        new_hostname: str | None = None,
        new_ip: str | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate complete database-aware migration workflow.

        Args:
            vmcraft_instance: Launched VMCraft instance
            new_hostname: New hostname for VM
            new_ip: New IP address for VM
            output_dir: Directory to save migration artifacts

        Returns:
            Complete migration result summary
        """
        self.logger.info("Starting database-aware migration workflow...")

        result = {
            "success": False,
            "databases_detected": 0,
            "health_checks_passed": False,
            "quiesce_successful": False,
            "resume_successful": False,
            "validation_passed": False,
            "guide_generated": False,
            "errors": [],
            "warnings": [],
        }

        try:
            # Step 1: Detect databases
            databases = self.detect_databases(vmcraft_instance)
            result["databases_detected"] = len(databases)

            if not databases:
                self.logger.info("No databases detected - skipping database-specific migration")
                result["success"] = True
                return result

            # Step 2: Pre-migration health checks
            health_checks = self.pre_migration_checks(databases)
            result["health_checks_passed"] = health_checks["all_healthy"]

            if not health_checks["all_healthy"]:
                result["errors"].extend(health_checks["critical_errors"])
                self.logger.error("Pre-migration health checks failed - aborting")
                return result

            # Step 3: Quiesce databases
            quiesce_result = self.quiesce_databases(databases)
            result["quiesce_successful"] = quiesce_result["success"]

            if not quiesce_result["success"]:
                result["errors"].extend(quiesce_result["errors"])
                self.logger.error("Database quiesce failed")
                return result

            # Note: At this point, external migration tool would snapshot the VM

            # Step 4: Resume databases
            resume_result = self.resume_databases(databases)
            result["resume_successful"] = resume_result["success"]

            if not resume_result["success"]:
                result["errors"].extend(resume_result["errors"])
                result["warnings"].append("Databases may still be in quiesced state")

            # Step 5: Post-migration validation (would run after VM starts on KVM)
            # Skipped in this phase - would be run post-boot

            # Step 6: Generate migration guide
            guide = self.generate_migration_guide(databases, new_hostname, new_ip)

            if output_dir:
                guide_path = Path(output_dir) / "database-migration-guide.md"
                guide_path.write_text(guide)
                self.logger.info(f"Migration guide saved to: {guide_path}")
                result["guide_generated"] = True

            result["success"] = True
            self.logger.info("✓ Database-aware migration workflow completed")

        except Exception as e:  # pylint: disable=broad-exception-caught  # top-level workflow guard: must not crash the whole migration over one step's failure
            self.logger.exception(f"Migration workflow failed: {e}")
            result["errors"].append(str(e))
            result["success"] = False

        return result
