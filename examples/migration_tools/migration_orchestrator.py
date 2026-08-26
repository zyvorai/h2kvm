#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMCraft Migration Orchestrator

Automated end-to-end VM migration workflow orchestration.

This tool orchestrates the complete migration process:
1. Pre-migration readiness assessment
2. Migration execution with selected strategy
3. Post-migration validation
4. Comprehensive reporting
5. Rollback capabilities

Usage:
    # Single VM migration with automatic assessment
    python migration_orchestrator.py migrate /path/to/source.vmdk /output/target.qcow2 --strategy enterprise

    # Batch migration from config file
    python migration_orchestrator.py batch-migrate migration-config.json

    # Dry-run mode (assessment only)
    python migration_orchestrator.py migrate source.vmdk target.qcow2 --dry-run

    # Custom strategy with specific phases
    python migration_orchestrator.py migrate source.vmdk target.qcow2 --phases inspection,services,network,validation

Author: VMCraft Team
Version: 1.0.0
"""

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Import VMCraft
try:
    from h2kvm.vmcraft.main import VMCraft
except ImportError:
    print("ERROR: h2kvm library not found. Install with: pip install -e .")
    sys.exit(1)

# Import migration tools
try:
    from pre_migration_readiness import ReadinessAssessment
    from post_migration_validation import PostMigrationValidation
except ImportError:
    print("WARNING: Migration assessment tools not found in current directory")
    ReadinessAssessment = None
    PostMigrationValidation = None


class MigrationStrategy(Enum):
    """Migration strategy types."""

    BASIC = "basic"
    ENTERPRISE = "enterprise"
    DATABASE = "database"
    WEB_SERVER = "web_server"
    SECURITY_HARDENED = "security_hardened"
    MINIMAL_DOWNTIME = "minimal_downtime"
    CUSTOM = "custom"


class MigrationPhase(Enum):
    """Migration phases."""

    READINESS_ASSESSMENT = "readiness_assessment"
    PRE_MIGRATION_BACKUP = "pre_migration_backup"
    INSPECTION = "inspection"
    MIGRATION = "migration"
    SERVICE_MANAGEMENT = "service_management"
    NETWORK_CONFIGURATION = "network_configuration"
    SECURITY_HARDENING = "security_hardening"
    BOOT_VALIDATION = "boot_validation"
    POST_MIGRATION_VALIDATION = "post_migration_validation"
    FINAL_REPORT = "final_report"


class MigrationOrchestrator:
    """
    Orchestrates end-to-end VM migration workflows.

    Supports multiple migration strategies and provides comprehensive
    assessment, execution, validation, and reporting.
    """

    def __init__(
        self,
        source_disk: str,
        target_disk: str,
        strategy: MigrationStrategy = MigrationStrategy.ENTERPRISE,
        dry_run: bool = False,
        custom_phases: list[str] | None = None,
    ):
        """
        Initialize migration orchestrator.

        Args:
            source_disk: Source VM disk image path
            target_disk: Target VM disk image path (output)
            strategy: Migration strategy to use
            dry_run: If True, only assess readiness without migrating
            custom_phases: Custom list of phases to execute
        """
        self.source_disk = Path(source_disk)
        self.target_disk = Path(target_disk)
        self.strategy = strategy
        self.dry_run = dry_run
        self.custom_phases = custom_phases

        # Initialize logging
        self.logger = logging.getLogger(__name__)

        # Migration state
        self.migration_id = f"migration_{int(time.time())}"
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

        # Results tracking
        self.readiness_report: dict[str, Any] = {}
        self.migration_results: dict[str, Any] = {}
        self.validation_report: dict[str, Any] = {}
        self.phase_results: dict[str, dict[str, Any]] = {}

        # Backup tracking for rollback
        self.backups: list[Path] = []

        # Validate inputs
        if not self.source_disk.exists():
            raise FileNotFoundError(f"Source disk not found: {self.source_disk}")

        if self.target_disk.exists():
            self.logger.warning(f"Target disk already exists: {self.target_disk}")

    def execute(self) -> dict[str, Any]:
        """
        Execute complete migration workflow.

        Returns:
            Comprehensive migration report
        """
        self.start_time = datetime.now()
        self.logger.info(f"=== Migration Orchestrator Started ===")
        self.logger.info(f"Migration ID: {self.migration_id}")
        self.logger.info(f"Source: {self.source_disk}")
        self.logger.info(f"Target: {self.target_disk}")
        self.logger.info(f"Strategy: {self.strategy.value}")
        self.logger.info(f"Dry Run: {self.dry_run}")

        try:
            # Phase 1: Readiness Assessment
            self._execute_phase(MigrationPhase.READINESS_ASSESSMENT, self._phase_readiness_assessment)

            # Check readiness before proceeding
            if not self._check_readiness_passed():
                self.logger.error("Readiness assessment failed - migration aborted")
                return self._generate_final_report(success=False, aborted=True)

            # Dry run stops here
            if self.dry_run:
                self.logger.info("Dry run complete - no migration performed")
                return self._generate_final_report(success=True, dry_run=True)

            # Phase 2: Pre-migration Backup
            self._execute_phase(MigrationPhase.PRE_MIGRATION_BACKUP, self._phase_pre_migration_backup)

            # Phase 3: Inspection
            self._execute_phase(MigrationPhase.INSPECTION, self._phase_inspection)

            # Phase 4: Migration
            self._execute_phase(MigrationPhase.MIGRATION, self._phase_migration)

            # Strategy-specific phases
            if self._should_execute_phase("service_management"):
                self._execute_phase(MigrationPhase.SERVICE_MANAGEMENT, self._phase_service_management)

            if self._should_execute_phase("network_configuration"):
                self._execute_phase(MigrationPhase.NETWORK_CONFIGURATION, self._phase_network_configuration)

            if self._should_execute_phase("security_hardening"):
                self._execute_phase(MigrationPhase.SECURITY_HARDENING, self._phase_security_hardening)

            if self._should_execute_phase("boot_validation"):
                self._execute_phase(MigrationPhase.BOOT_VALIDATION, self._phase_boot_validation)

            # Phase 5: Post-migration Validation
            self._execute_phase(
                MigrationPhase.POST_MIGRATION_VALIDATION, self._phase_post_migration_validation
            )

            # Check validation results
            validation_passed = self._check_validation_passed()

            # Phase 6: Final Report
            self._execute_phase(MigrationPhase.FINAL_REPORT, self._phase_final_report)

            return self._generate_final_report(success=validation_passed)

        except Exception as e:
            self.logger.error(f"Migration failed with exception: {e}", exc_info=True)
            return self._generate_final_report(success=False, error=str(e))

        finally:
            self.end_time = datetime.now()

    def _execute_phase(self, phase: MigrationPhase, phase_func: callable) -> None:
        """Execute a migration phase with error handling."""
        phase_name = phase.value
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"Phase: {phase_name.upper()}")
        self.logger.info(f"{'=' * 60}")

        phase_start = time.time()

        try:
            result = phase_func()
            phase_duration = time.time() - phase_start

            self.phase_results[phase_name] = {
                "success": True,
                "duration_seconds": phase_duration,
                "result": result,
                "error": None,
            }

            self.logger.info(f"✓ Phase '{phase_name}' completed in {phase_duration:.2f}s")

        except Exception as e:
            phase_duration = time.time() - phase_start

            self.phase_results[phase_name] = {
                "success": False,
                "duration_seconds": phase_duration,
                "result": None,
                "error": str(e),
            }

            self.logger.error(f"✗ Phase '{phase_name}' failed after {phase_duration:.2f}s: {e}")
            raise

    def _should_execute_phase(self, phase_name: str) -> bool:
        """Check if a phase should be executed based on strategy and custom phases."""
        if self.custom_phases:
            return phase_name in self.custom_phases

        # Strategy-based phase selection
        strategy_phases = {
            MigrationStrategy.BASIC: ["inspection", "migration"],
            MigrationStrategy.ENTERPRISE: [
                "inspection",
                "migration",
                "service_management",
                "network_configuration",
                "security_hardening",
                "boot_validation",
            ],
            MigrationStrategy.DATABASE: ["inspection", "migration", "service_management", "boot_validation"],
            MigrationStrategy.WEB_SERVER: [
                "inspection",
                "migration",
                "service_management",
                "network_configuration",
            ],
            MigrationStrategy.SECURITY_HARDENED: [
                "inspection",
                "migration",
                "service_management",
                "network_configuration",
                "security_hardening",
            ],
            MigrationStrategy.MINIMAL_DOWNTIME: ["inspection", "migration", "service_management"],
        }

        return phase_name in strategy_phases.get(self.strategy, [])

    # =========================================================================
    # Phase Implementations
    # =========================================================================

    def _phase_readiness_assessment(self) -> dict[str, Any]:
        """Phase 1: Pre-migration readiness assessment."""
        if not ReadinessAssessment:
            self.logger.warning("Readiness assessment tool not available - skipping")
            return {"skipped": True, "reason": "tool_not_available"}

        self.logger.info("Running pre-migration readiness assessment...")

        assessment = ReadinessAssessment(str(self.source_disk))
        report = assessment.run_full_assessment()

        self.readiness_report = report

        # Log key findings
        risk_score = report.get("risk_assessment", {}).get("overall_score", 0)
        risk_level = report.get("risk_assessment", {}).get("risk_level", "UNKNOWN")

        self.logger.info(f"Risk Score: {risk_score}/100 ({risk_level})")

        blockers = report.get("blockers", [])
        if blockers:
            self.logger.warning(f"Found {len(blockers)} migration blockers:")
            for blocker in blockers:
                self.logger.warning(f"  - {blocker}")

        recommendations = report.get("recommendations", [])
        if recommendations:
            self.logger.info(f"Recommendations ({len(recommendations)}):")
            for rec in recommendations[:3]:  # Show first 3
                self.logger.info(f"  - {rec}")

        return report

    def _check_readiness_passed(self) -> bool:
        """Check if readiness assessment passed."""
        if not self.readiness_report:
            return True  # Skip check if no assessment

        risk_level = self.readiness_report.get("risk_assessment", {}).get("risk_level", "UNKNOWN")
        blockers = self.readiness_report.get("blockers", [])

        # Fail if critical risk or blockers present
        if risk_level == "CRITICAL" or blockers:
            return False

        return True

    def _phase_pre_migration_backup(self) -> dict[str, Any]:
        """Phase 2: Create pre-migration backup."""
        self.logger.info("Creating pre-migration backup...")

        backup_dir = self.target_disk.parent / f"backups_{self.migration_id}"
        backup_dir.mkdir(exist_ok=True)

        source_backup = backup_dir / f"source_{self.source_disk.name}.backup"

        try:
            self.logger.info(f"Copying source to: {source_backup}")
            shutil.copy2(self.source_disk, source_backup)
            self.backups.append(source_backup)

            backup_size_mb = source_backup.stat().st_size / (1024 * 1024)

            return {"backup_path": str(source_backup), "backup_size_mb": backup_size_mb, "success": True}

        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return {"success": False, "error": str(e)}

    def _phase_inspection(self) -> dict[str, Any]:
        """Phase 3: Inspect source VM."""
        self.logger.info("Inspecting source VM...")

        with VMCraft(str(self.source_disk)) as g:
            # Detect OS
            roots = g.inspect_os()
            if not roots:
                raise RuntimeError("No operating systems detected in source disk")

            root = roots[0]

            # Gather OS metadata
            os_info = {
                "type": g.inspect_get_type(root),
                "distro": g.inspect_get_distro(root),
                "product_name": g.inspect_get_product_name(root),
                "major_version": g.inspect_get_major_version(root),
                "minor_version": g.inspect_get_minor_version(root),
                "hostname": g.inspect_get_hostname(root),
            }

            # Partition analysis
            partitions = g.list_partitions(use_cache=True)

            # LVM detection
            lvm_detected = False
            try:
                pvs = g.pvs()
                vgs = g.vgs()
                lvs = g.lvs()
                lvm_detected = len(pvs) > 0
            except Exception:
                pvs, vgs, lvs = [], [], []

            # Systemd check
            systemd_available = g.systemd_is_available()

            inspection_result = {
                "root": root,
                "os_info": os_info,
                "partitions": partitions,
                "partition_count": len(partitions),
                "lvm_detected": lvm_detected,
                "lvm_components": {"pvs": len(pvs), "vgs": len(vgs), "lvs": len(lvs)},
                "systemd_available": systemd_available,
            }

            self.logger.info(f"OS: {os_info.get('distro')} {os_info.get('product_name')}")
            self.logger.info(f"Partitions: {len(partitions)}")
            self.logger.info(f"LVM: {'Yes' if lvm_detected else 'No'}")
            self.logger.info(f"Systemd: {'Yes' if systemd_available else 'No'}")

            return inspection_result

    def _phase_migration(self) -> dict[str, Any]:
        """Phase 4: Execute migration."""
        self.logger.info("Executing migration...")

        # Create target disk if needed
        if not self.target_disk.exists():
            self.logger.info(f"Creating target disk: {self.target_disk}")
            # For now, copy source to target
            # In production, use qemu-img convert with optimization
            shutil.copy2(self.source_disk, self.target_disk)

        migration_result = {
            "source": str(self.source_disk),
            "target": str(self.target_disk),
            "target_size_mb": self.target_disk.stat().st_size / (1024 * 1024),
            "success": True,
        }

        self.logger.info(f"Migration complete: {self.target_disk}")

        return migration_result

    def _phase_service_management(self) -> dict[str, Any]:
        """Phase 5: Service management (VMware → KVM)."""
        self.logger.info("Managing services...")

        with VMCraft(str(self.target_disk)) as g:
            # Mount filesystem
            roots = g.inspect_os()
            if not roots:
                return {"skipped": True, "reason": "no_os_detected"}

            root = roots[0]
            mountpoints = g.inspect_get_mountpoints(root)
            for mp, device in sorted(mountpoints.items()):
                try:
                    g.mount(device, mp)
                except Exception as e:
                    self.logger.debug(f"Mount failed for {device}: {e}")

            # Check systemd availability
            if not g.systemd_is_available():
                return {"skipped": True, "reason": "systemd_not_available"}

            # Disable VMware services
            vmware_services = ["vmtoolsd.service", "vmware-tools.service", "open-vm-tools.service"]

            disabled_services = []
            for svc in vmware_services:
                try:
                    result = g.systemd_service_disable(svc)
                    if result.get("ok"):
                        disabled_services.append(svc)
                except Exception:
                    pass

            # Mask VMware services
            masked_services = []
            try:
                result = g.systemd_services_mask(vmware_services)
                if result.get("ok"):
                    masked_services = result.get("services", [])
            except Exception:
                pass

            # Enable KVM services
            kvm_services = ["qemu-guest-agent.service"]
            enabled_services = []

            for svc in kvm_services:
                try:
                    result = g.systemd_service_enable(svc)
                    if result.get("ok"):
                        enabled_services.append(svc)
                except Exception:
                    pass

            # Reload systemd
            try:
                g.systemd_daemon_reload()
            except Exception:
                pass

            service_result = {
                "disabled_services": disabled_services,
                "masked_services": masked_services,
                "enabled_services": enabled_services,
                "success": True,
            }

            self.logger.info(f"Disabled {len(disabled_services)} VMware services")
            self.logger.info(f"Enabled {len(enabled_services)} KVM services")

            return service_result

    def _phase_network_configuration(self) -> dict[str, Any]:
        """Phase 6: Network configuration migration."""
        self.logger.info("Configuring network...")

        with VMCraft(str(self.target_disk)) as g:
            # Mount filesystem
            roots = g.inspect_os()
            if not roots:
                return {"skipped": True, "reason": "no_os_detected"}

            root = roots[0]
            mountpoints = g.inspect_get_mountpoints(root)
            for mp, device in sorted(mountpoints.items()):
                try:
                    g.mount(device, mp)
                except Exception:
                    pass

            if not g.systemd_is_available():
                return {"skipped": True, "reason": "systemd_not_available"}

            # Migrate network configuration
            migrated_interfaces = []
            for interface in ["eth0", "ens3", "ens33"]:
                try:
                    result = g.networkd_migrate_from_ifcfg(interface)
                    if result.get("ok"):
                        migrated_interfaces.append(interface)
                except Exception:
                    pass

            # Enable systemd-networkd
            networkd_enabled = False
            try:
                result = g.networkd_enable_networkd()
                networkd_enabled = result.get("ok", False)
            except Exception:
                pass

            network_result = {
                "migrated_interfaces": migrated_interfaces,
                "networkd_enabled": networkd_enabled,
                "success": True,
            }

            self.logger.info(f"Migrated {len(migrated_interfaces)} network interfaces")

            return network_result

    def _phase_security_hardening(self) -> dict[str, Any]:
        """Phase 7: Security hardening."""
        self.logger.info("Applying security hardening...")

        with VMCraft(str(self.target_disk)) as g:
            # Mount filesystem
            roots = g.inspect_os()
            if not roots:
                return {"skipped": True, "reason": "no_os_detected"}

            root = roots[0]
            mountpoints = g.inspect_get_mountpoints(root)
            for mp, device in sorted(mountpoints.items()):
                try:
                    g.mount(device, mp)
                except Exception:
                    pass

            # SSH hardening with Augeas
            hardening_applied = []
            try:
                g.aug_init()

                # Disable root login
                g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
                hardening_applied.append("disabled_root_login")

                # Disable password authentication
                g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")
                hardening_applied.append("disabled_password_auth")

                # Enable public key authentication
                g.aug_set("/files/etc/ssh/sshd_config/PubkeyAuthentication", "yes")
                hardening_applied.append("enabled_pubkey_auth")

                g.aug_save()
                g.aug_close()

            except Exception as e:
                self.logger.warning(f"Augeas hardening failed: {e}")

            security_result = {"hardening_applied": hardening_applied, "success": len(hardening_applied) > 0}

            self.logger.info(f"Applied {len(hardening_applied)} security hardenings")

            return security_result

    def _phase_boot_validation(self) -> dict[str, Any]:
        """Phase 8: Boot validation."""
        self.logger.info("Validating boot configuration...")

        with VMCraft(str(self.target_disk)) as g:
            # Mount filesystem
            roots = g.inspect_os()
            if not roots:
                return {"skipped": True, "reason": "no_os_detected"}

            root = roots[0]
            mountpoints = g.inspect_get_mountpoints(root)
            for mp, device in sorted(mountpoints.items()):
                try:
                    g.mount(device, mp)
                except Exception:
                    pass

            if not g.systemd_is_available():
                return {"skipped": True, "reason": "systemd_not_available"}

            # Check for failed services
            failed_services = []
            try:
                failed_services = g.systemd_list_failed_services()
            except Exception:
                pass

            # Boot performance analysis
            boot_performance = None
            try:
                boot_performance = g.units_analyze_boot_performance()
            except Exception:
                pass

            boot_result = {
                "failed_services": failed_services,
                "failed_service_count": len(failed_services),
                "boot_performance": boot_performance,
                "success": len(failed_services) == 0,
            }

            self.logger.info(f"Failed services: {len(failed_services)}")
            if boot_performance:
                self.logger.info(f"Boot time: {boot_performance.get('boot_time', 'N/A')}")

            return boot_result

    def _phase_post_migration_validation(self) -> dict[str, Any]:
        """Phase 9: Post-migration validation."""
        if not PostMigrationValidation:
            self.logger.warning("Post-migration validation tool not available - skipping")
            return {"skipped": True, "reason": "tool_not_available"}

        self.logger.info("Running post-migration validation...")

        validator = PostMigrationValidation(str(self.target_disk))
        report = validator.run_full_validation()

        self.validation_report = report

        # Log key findings
        production_score = report.get("production_readiness", {}).get("score", 0)
        readiness = report.get("production_readiness", {}).get("readiness", "UNKNOWN")

        self.logger.info(f"Production Readiness: {production_score}/100 ({readiness})")

        issues = report.get("issues", [])
        if issues:
            self.logger.warning(f"Found {len(issues)} validation issues:")
            for issue in issues[:5]:  # Show first 5
                self.logger.warning(f"  - [{issue['severity']}] {issue['issue']}")

        return report

    def _check_validation_passed(self) -> bool:
        """Check if post-migration validation passed."""
        if not self.validation_report:
            return True  # Skip check if no validation

        readiness = self.validation_report.get("production_readiness", {}).get("readiness", "UNKNOWN")
        critical_issues = [
            issue
            for issue in self.validation_report.get("issues", [])
            if issue.get("severity") == "CRITICAL"
        ]

        # Fail if not production ready or critical issues present
        if readiness == "NOT_READY" or critical_issues:
            return False

        return True

    def _phase_final_report(self) -> dict[str, Any]:
        """Phase 10: Generate final report."""
        self.logger.info("Generating final report...")

        report = self._generate_final_report(success=True)

        # Write report to file
        report_path = self.target_disk.parent / f"migration_report_{self.migration_id}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        self.logger.info(f"Report saved to: {report_path}")

        return {"report_path": str(report_path)}

    def _generate_final_report(
        self, success: bool, dry_run: bool = False, aborted: bool = False, error: str | None = None
    ) -> dict[str, Any]:
        """Generate comprehensive final report."""
        duration = None
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()

        report = {
            "migration_id": self.migration_id,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "dry_run": dry_run,
            "aborted": aborted,
            "error": error,
            "duration_seconds": duration,
            "source_disk": str(self.source_disk),
            "target_disk": str(self.target_disk),
            "strategy": self.strategy.value,
            "phases": self.phase_results,
            "readiness_assessment": self.readiness_report,
            "validation_report": self.validation_report,
            "backups": [str(b) for b in self.backups],
        }

        return report

    def rollback(self) -> bool:
        """
        Rollback migration using backups.

        Returns:
            True if rollback successful
        """
        self.logger.warning("=== Starting Migration Rollback ===")

        if not self.backups:
            self.logger.error("No backups available for rollback")
            return False

        try:
            # Remove target disk
            if self.target_disk.exists():
                self.logger.info(f"Removing target disk: {self.target_disk}")
                self.target_disk.unlink()

            # Restore source from backup
            source_backup = self.backups[0]
            if source_backup.exists():
                self.logger.info(f"Restoring source from backup: {source_backup}")
                shutil.copy2(source_backup, self.source_disk)

            self.logger.info("✓ Rollback completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False


def batch_migrate(config_file: Path) -> list[dict[str, Any]]:
    """
    Execute batch migration from config file.

    Config format:
    {
        "migrations": [
            {
                "source": "/path/to/vm1.vmdk",
                "target": "/output/vm1.qcow2",
                "strategy": "enterprise"
            },
            ...
        ]
    }

    Returns:
        List of migration reports
    """
    logger = logging.getLogger(__name__)
    logger.info(f"=== Batch Migration Started ===")
    logger.info(f"Config: {config_file}")

    with open(config_file) as f:
        config = json.load(f)

    migrations = config.get("migrations", [])
    logger.info(f"Found {len(migrations)} migrations to process")

    results = []

    for i, migration_spec in enumerate(migrations, 1):
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Migration {i}/{len(migrations)}")
        logger.info(f"{'=' * 80}")

        source = migration_spec["source"]
        target = migration_spec["target"]
        strategy_name = migration_spec.get("strategy", "enterprise")

        try:
            strategy = MigrationStrategy(strategy_name)
        except ValueError:
            logger.error(f"Invalid strategy: {strategy_name}")
            continue

        orchestrator = MigrationOrchestrator(source_disk=source, target_disk=target, strategy=strategy)

        report = orchestrator.execute()
        results.append(report)

        if not report["success"]:
            logger.error(f"Migration {i} failed - check report for details")

    # Summary
    successful = sum(1 for r in results if r["success"])
    logger.info(f"\n=== Batch Migration Complete ===")
    logger.info(f"Total: {len(results)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {len(results) - successful}")

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="VMCraft Migration Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enterprise migration with full validation
  %(prog)s migrate /vmware/rhel9.vmdk /kvm/rhel9.qcow2 --strategy enterprise

  # Dry-run (assessment only)
  %(prog)s migrate source.vmdk target.qcow2 --dry-run

  # Database migration strategy
  %(prog)s migrate db.vmdk db-kvm.qcow2 --strategy database

  # Custom phases
  %(prog)s migrate vm.vmdk vm-kvm.qcow2 --phases inspection,services,validation

  # Batch migration
  %(prog)s batch-migrate migrations.json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Single migration command
    migrate_parser = subparsers.add_parser("migrate", help="Execute single VM migration")
    migrate_parser.add_argument("source", help="Source VM disk image")
    migrate_parser.add_argument("target", help="Target VM disk image (output)")
    migrate_parser.add_argument(
        "--strategy",
        choices=[s.value for s in MigrationStrategy],
        default="enterprise",
        help="Migration strategy (default: enterprise)",
    )
    migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Dry-run mode (assessment only, no migration)"
    )
    migrate_parser.add_argument("--phases", help="Comma-separated list of custom phases to execute")
    migrate_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Batch migration command
    batch_parser = subparsers.add_parser("batch-migrate", help="Execute batch migration")
    batch_parser.add_argument("config", help="Migration config JSON file")
    batch_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    if args.command == "migrate":
        # Parse custom phases
        custom_phases = None
        if args.phases:
            custom_phases = [p.strip() for p in args.phases.split(",")]

        # Create orchestrator
        orchestrator = MigrationOrchestrator(
            source_disk=args.source,
            target_disk=args.target,
            strategy=MigrationStrategy(args.strategy),
            dry_run=args.dry_run,
            custom_phases=custom_phases,
        )

        # Execute migration
        report = orchestrator.execute()

        # Print summary
        print("\n" + "=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Success: {report['success']}")
        print(f"Duration: {report['duration_seconds']:.2f}s")

        if report.get("readiness_assessment"):
            risk_score = report["readiness_assessment"].get("risk_assessment", {}).get("overall_score", 0)
            print(f"Pre-Migration Risk Score: {risk_score}/100")

        if report.get("validation_report"):
            prod_score = report["validation_report"].get("production_readiness", {}).get("score", 0)
            print(f"Post-Migration Production Score: {prod_score}/100")

        # Exit code
        sys.exit(0 if report["success"] else 1)

    elif args.command == "batch-migrate":
        results = batch_migrate(Path(args.config))
        successful = sum(1 for r in results if r["success"])

        print("\n" + "=" * 80)
        print("BATCH MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Total Migrations: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {len(results) - successful}")

        sys.exit(0 if successful == len(results) else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
