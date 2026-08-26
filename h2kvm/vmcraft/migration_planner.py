# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/migration_planner.py
"""
Automated migration planning and compatibility checking.

Provides comprehensive migration planning:
- Source platform detection (VMware, Hyper-V, VirtualBox, etc.)
- Target platform compatibility checking
- Migration task generation
- Dependency ordering
- Risk assessment
- Rollback planning

Features:
- Platform compatibility matrix
- Driver requirement detection
- Network reconfiguration planning
- Boot configuration updates
- Migration task sequencing
- Pre-migration checklist
- Post-migration validation
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from .file_ops import FileOperations


class MigrationPlanner:
    """
    Automated migration planner.

    Plans VM migrations with compatibility checking and task sequencing.
    """

    # Platform compatibility matrix
    COMPATIBILITY = {
        "vmware_to_kvm": {
            "supported": True,
            "driver_changes": ["vmxnet3 -> virtio-net", "pvscsi -> virtio-scsi"],
            "bootloader_update": True,
            "complexity": "medium",
        },
        "hyperv_to_kvm": {
            "supported": True,
            "driver_changes": ["netvsc -> virtio-net", "storvsc -> virtio-scsi"],
            "bootloader_update": True,
            "complexity": "medium",
        },
        "virtualbox_to_kvm": {
            "supported": True,
            "driver_changes": ["vboxnet -> virtio-net", "vboxsf -> 9p/virtiofs"],
            "bootloader_update": True,
            "complexity": "low",
        },
        "aws_to_kvm": {
            "supported": True,
            "driver_changes": ["ena -> virtio-net", "nvme -> virtio-blk"],
            "bootloader_update": True,
            "complexity": "high",
        },
        "vmware_to_aws": {
            "supported": True,
            "driver_changes": ["vmxnet3 -> ena"],
            "bootloader_update": True,
            "complexity": "high",
        },
    }

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize migration planner.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def plan_migration(
        self, source_platform: str, target_platform: str, os_info: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Plan migration from source to target platform.

        Args:
            source_platform: Source platform (vmware, hyperv, virtualbox, aws, etc.)
            target_platform: Target platform (kvm, aws, azure, gcp)
            os_info: Optional OS information from inspection

        Returns:
            Migration plan
        """
        plan: dict[str, Any] = {
            "source_platform": source_platform,
            "target_platform": target_platform,
            "compatible": False,
            "complexity": "unknown",
            "tasks": [],
            "prerequisites": [],
            "risks": [],
            "estimated_downtime_minutes": 0,
        }

        # Check compatibility
        migration_key = f"{source_platform}_to_{target_platform}"
        compatibility = self.COMPATIBILITY.get(migration_key, {})

        if compatibility.get("supported"):
            plan["compatible"] = True
            plan["complexity"] = compatibility.get("complexity", "unknown")

            # Generate tasks
            tasks = self._generate_migration_tasks(source_platform, target_platform, compatibility, os_info)
            plan["tasks"] = tasks

            # Generate prerequisites
            prerequisites = self._generate_prerequisites(source_platform, target_platform)
            plan["prerequisites"] = prerequisites

            # Assess risks
            risks = self._assess_migration_risks(source_platform, target_platform, os_info)
            plan["risks"] = risks

            # Estimate downtime
            plan["estimated_downtime_minutes"] = self._estimate_downtime(plan["complexity"])

        else:
            plan["compatible"] = False
            plan["risks"] = [
                {
                    "severity": "critical",
                    "risk": f"Migration path {migration_key} not supported",
                    "mitigation": "Manual migration required",
                }
            ]

        return plan

    def _generate_migration_tasks(
        self, source: str, target: str, compatibility: dict[str, Any], _os_info: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Generate migration tasks in dependency order."""
        tasks = []

        # Task 1: Backup
        tasks.append(
            {
                "id": 1,
                "name": "Create backup",
                "description": "Create full backup of source VM",
                "category": "preparation",
                "priority": 1,
                "estimated_minutes": 30,
                "automated": False,
            }
        )

        # Task 2: Install target drivers
        if compatibility.get("driver_changes"):
            tasks.append(
                {
                    "id": 2,
                    "name": "Install target platform drivers",
                    "description": f"Install drivers for {target}",
                    "category": "driver_injection",
                    "priority": 2,
                    "estimated_minutes": 10,
                    "automated": True,
                    "driver_changes": compatibility.get("driver_changes"),
                }
            )

        # Task 3: Update network configuration
        tasks.append(
            {
                "id": 3,
                "name": "Update network configuration",
                "description": "Reconfigure network for target platform",
                "category": "network",
                "priority": 3,
                "estimated_minutes": 15,
                "automated": True,
            }
        )

        # Task 4: Update bootloader
        if compatibility.get("bootloader_update"):
            tasks.append(
                {
                    "id": 4,
                    "name": "Update bootloader configuration",
                    "description": "Update GRUB/bootloader for target platform",
                    "category": "bootloader",
                    "priority": 4,
                    "estimated_minutes": 10,
                    "automated": True,
                }
            )

        # Task 5: Remove source platform tools
        tasks.append(
            {
                "id": 5,
                "name": "Remove source platform tools",
                "description": f"Uninstall {source} guest tools/agents",
                "category": "cleanup",
                "priority": 5,
                "estimated_minutes": 5,
                "automated": True,
            }
        )

        # Task 6: Install target platform tools
        tasks.append(
            {
                "id": 6,
                "name": "Install target platform tools",
                "description": f"Install {target} guest tools/agents",
                "category": "tools",
                "priority": 6,
                "estimated_minutes": 10,
                "automated": False,
            }
        )

        # Task 7: Test boot
        tasks.append(
            {
                "id": 7,
                "name": "Test boot on target platform",
                "description": "Perform test boot and validation",
                "category": "validation",
                "priority": 7,
                "estimated_minutes": 20,
                "automated": False,
            }
        )

        return tasks

    def _generate_prerequisites(self, _source: str, target: str) -> list[dict[str, Any]]:
        """Generate migration prerequisites."""
        prerequisites = []

        # Common prerequisites
        prerequisites.append(
            {
                "requirement": "VM snapshot or backup",
                "description": "Create recovery point before migration",
                "critical": True,
            }
        )

        prerequisites.append(
            {
                "requirement": "Target platform access",
                "description": f"Ensure access to {target} environment",
                "critical": True,
            }
        )

        prerequisites.append(
            {
                "requirement": "Storage space",
                "description": "Verify sufficient storage on target",
                "critical": True,
            }
        )

        # Platform-specific prerequisites
        if target == "kvm":
            prerequisites.append(
                {
                    "requirement": "KVM host prepared",
                    "description": "KVM host with libvirt configured",
                    "critical": True,
                }
            )

        elif target in ["aws", "azure", "gcp"]:
            prerequisites.append(
                {
                    "requirement": "Cloud account configured",
                    "description": f"{target.upper()} account with appropriate permissions",
                    "critical": True,
                }
            )

            prerequisites.append(
                {
                    "requirement": "Network connectivity",
                    "description": "Network path to cloud provider",
                    "critical": True,
                }
            )

        return prerequisites

    def _assess_migration_risks(
        self, _source: str, _target: str, _os_info: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Assess migration risks."""
        risks = []

        # Driver compatibility risk
        risks.append(
            {
                "severity": "medium",
                "risk": "Driver compatibility issues",
                "impact": "Network or storage may not work after migration",
                "mitigation": "Install target drivers before migration",
                "probability": "low",
            }
        )

        # Boot failure risk
        risks.append(
            {
                "severity": "high",
                "risk": "Boot failure on target platform",
                "impact": "VM may not boot after migration",
                "mitigation": "Test boot in isolated environment first",
                "probability": "medium",
            }
        )

        # Network reconfiguration risk
        risks.append(
            {
                "severity": "medium",
                "risk": "Network connectivity loss",
                "impact": "VM may lose network connectivity",
                "mitigation": "Document current network config, prepare console access",
                "probability": "medium",
            }
        )

        # Data loss risk
        risks.append(
            {
                "severity": "critical",
                "risk": "Data loss during migration",
                "impact": "Loss of VM data",
                "mitigation": "Create verified backup before migration",
                "probability": "very_low",
            }
        )

        return risks

    def _estimate_downtime(self, complexity: str) -> int:
        """Estimate migration downtime in minutes."""
        downtime_map = {
            "low": 30,
            "medium": 60,
            "high": 120,
        }

        return downtime_map.get(complexity, 90)

    def get_migration_summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        """
        Get migration summary.

        Args:
            plan: Migration plan

        Returns:
            Summary dictionary
        """
        tasks = plan.get("tasks", [])
        risks = plan.get("risks", [])

        return {
            "compatible": plan.get("compatible", False),
            "complexity": plan.get("complexity", "unknown"),
            "total_tasks": len(tasks),
            "automated_tasks": sum(1 for t in tasks if t.get("automated")),
            "manual_tasks": sum(1 for t in tasks if not t.get("automated")),
            "estimated_downtime_minutes": plan.get("estimated_downtime_minutes", 0),
            "total_risks": len(risks),
            "critical_risks": sum(1 for r in risks if r.get("severity") == "critical"),
        }

    def get_checklist(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Generate pre-migration checklist.

        Args:
            plan: Migration plan

        Returns:
            Checklist items
        """
        checklist = []

        # Prerequisites
        for idx, prereq in enumerate(plan.get("prerequisites", []), 1):
            checklist.append(
                {
                    "id": f"PRE-{idx}",
                    "category": "prerequisite",
                    "item": prereq.get("requirement"),
                    "description": prereq.get("description"),
                    "critical": prereq.get("critical", False),
                    "completed": False,
                }
            )

        # Backup verification
        checklist.append(
            {
                "id": "BACKUP-1",
                "category": "backup",
                "item": "Verify backup integrity",
                "description": "Test backup restore before proceeding",
                "critical": True,
                "completed": False,
            }
        )

        # Documentation
        checklist.append(
            {
                "id": "DOC-1",
                "category": "documentation",
                "item": "Document current configuration",
                "description": "Document network, storage, and application config",
                "critical": False,
                "completed": False,
            }
        )

        return checklist

    def generate_rollback_plan(self, _plan: dict[str, Any]) -> dict[str, Any]:
        """
        Generate rollback plan.

        Args:
            plan: Migration plan

        Returns:
            Rollback plan
        """
        return {
            "trigger_conditions": [
                "Boot failure on target platform",
                "Critical application failure",
                "Data integrity issues",
                "Network connectivity issues",
            ],
            "steps": [
                {
                    "id": 1,
                    "action": "Stop target VM",
                    "description": "Power off migrated VM on target platform",
                },
                {
                    "id": 2,
                    "action": "Restore from backup",
                    "description": "Restore VM from pre-migration backup",
                },
                {
                    "id": 3,
                    "action": "Start source VM",
                    "description": "Boot original VM on source platform",
                },
                {
                    "id": 4,
                    "action": "Verify functionality",
                    "description": "Confirm all services operational",
                },
            ],
            "estimated_rollback_time_minutes": 30,
        }

    def validate_migration_readiness(self, plan: dict[str, Any]) -> dict[str, Any]:
        """
        Validate migration readiness.

        Args:
            plan: Migration plan

        Returns:
            Validation results
        """
        validation = {
            "ready": True,
            "blockers": [],
            "warnings": [],
        }

        # Check if migration is compatible
        if not plan.get("compatible"):
            validation["ready"] = False
            validation["blockers"].append(
                {
                    "issue": "Unsupported migration path",
                    "action": "Choose different target platform or perform manual migration",
                }
            )

        # Check for critical risks
        risks = plan.get("risks", [])
        critical_risks = [r for r in risks if r.get("severity") == "critical"]

        if critical_risks:
            validation["warnings"].append(
                {
                    "issue": f"{len(critical_risks)} critical risks identified",
                    "action": "Review and mitigate critical risks before proceeding",
                }
            )

        return validation
