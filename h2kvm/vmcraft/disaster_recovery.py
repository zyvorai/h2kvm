# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/disaster_recovery.py
"""
Disaster Recovery Planner Module for VMCraft.

Provides disaster recovery planning, backup strategies, RTO/RPO analysis,
and failover procedures.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path


class DisasterRecovery:
    """Disaster recovery planning and management."""

    # Recovery tier definitions
    RECOVERY_TIERS = {
        "tier_0": {
            "name": "Mission Critical",
            "rto_hours": 1,
            "rpo_minutes": 15,
            "availability": "99.99%",
        },
        "tier_1": {
            "name": "Business Critical",
            "rto_hours": 4,
            "rpo_minutes": 60,
            "availability": "99.9%",
        },
        "tier_2": {
            "name": "Important",
            "rto_hours": 24,
            "rpo_hours": 4,
            "availability": "99.5%",
        },
        "tier_3": {
            "name": "Standard",
            "rto_hours": 72,
            "rpo_hours": 24,
            "availability": "99%",
        },
    }

    def __init__(
        self,
        logger: logging.Logger,
        file_ops: Any,
        mount_root: Path,
    ) -> None:
        """Initialize disaster recovery planner."""
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def assess_recovery_requirements(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """
        Assess disaster recovery requirements.

        Args:
            system_info: System information and criticality

        Returns:
            Recovery requirements assessment
        """
        self.logger.info("Assessing disaster recovery requirements")

        criticality = system_info.get("criticality", "medium")
        data_sensitivity = system_info.get("data_sensitivity", "medium")
        business_impact = system_info.get("business_impact", "medium")

        # Determine recovery tier
        if criticality == "critical" or business_impact == "critical":
            tier = "tier_0"
        elif criticality == "high" or business_impact == "high":
            tier = "tier_1"
        elif criticality == "medium":
            tier = "tier_2"
        else:
            tier = "tier_3"

        tier_info = self.RECOVERY_TIERS[tier]

        return {
            "recovery_tier": tier,
            "tier_name": tier_info["name"],
            "rto_target_hours": tier_info["rto_hours"],
            "rpo_target": tier_info.get("rpo_minutes", tier_info.get("rpo_hours", 0) * 60),
            "target_availability": tier_info["availability"],
            "criticality_factors": {
                "system_criticality": criticality,
                "data_sensitivity": data_sensitivity,
                "business_impact": business_impact,
            },
            "recommended_strategies": self._get_tier_strategies(tier),
        }

    def _get_tier_strategies(self, tier: str) -> list[str]:
        """Get recommended DR strategies for tier."""
        strategies = {
            "tier_0": [
                "Real-time replication to secondary site",
                "Automated failover with load balancing",
                "Continuous data protection (CDP)",
                "24/7 monitoring and incident response",
            ],
            "tier_1": [
                "Synchronous replication",
                "Automated backup every hour",
                "Hot standby systems",
                "Regular DR testing (monthly)",
            ],
            "tier_2": [
                "Asynchronous replication",
                "Daily backups with weekly full backups",
                "Warm standby systems",
                "Quarterly DR testing",
            ],
            "tier_3": [
                "Scheduled backups",
                "Weekly full backups",
                "Cold standby or restore from backup",
                "Annual DR testing",
            ],
        }
        return strategies.get(tier, [])

    def create_backup_strategy(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """
        Create comprehensive backup strategy.

        Args:
            requirements: Recovery requirements

        Returns:
            Backup strategy plan
        """
        self.logger.info("Creating backup strategy")

        rpo_minutes = requirements.get("rpo_target", 60)
        data_size_gb = requirements.get("data_size_gb", 100)
        retention_days = requirements.get("retention_days", 30)

        # Determine backup frequency
        if rpo_minutes <= 15:
            frequency = "continuous"
            method = "Continuous Data Protection (CDP)"
        elif rpo_minutes <= 60:
            frequency = "hourly"
            method = "Incremental backup every hour"
        elif rpo_minutes <= 240:
            frequency = "every_4_hours"
            method = "Incremental backup every 4 hours"
        elif rpo_minutes <= 1440:  # 24 hours
            frequency = "daily"
            method = "Daily incremental + weekly full backup"
        else:
            frequency = "weekly"
            method = "Weekly full backup"

        # Calculate storage requirements
        storage_required = self._calculate_backup_storage(data_size_gb, frequency, retention_days)

        return {
            "backup_frequency": frequency,
            "backup_method": method,
            "rpo_minutes": rpo_minutes,
            "retention_policy": {
                "daily_backups": min(retention_days, 30),
                "weekly_backups": 12,
                "monthly_backups": 12,
            },
            "storage_requirements_gb": storage_required,
            "estimated_monthly_cost": round(storage_required * 0.10, 2),
            "backup_windows": self._recommend_backup_windows(frequency),
            "verification": "Weekly backup verification and restore testing",
        }

    def _calculate_backup_storage(self, data_size_gb: float, frequency: str, _retention_days: int) -> float:
        """Calculate required backup storage."""
        # Simplified calculation
        if frequency == "continuous":
            # CDP requires 2-3x data size
            return data_size_gb * 2.5
        if frequency == "hourly":
            # Hourly incrementals + weekly fulls
            return data_size_gb * 1.5
        if frequency == "daily":
            # Daily incrementals
            return data_size_gb * 1.2
        # Weekly backups
        return data_size_gb * 1.1

    def _recommend_backup_windows(self, frequency: str) -> list[dict[str, str]]:
        """Recommend backup time windows."""
        if frequency == "continuous":
            return [{"window": "24/7", "description": "Continuous protection"}]
        if frequency == "hourly":
            return [{"window": "Every hour", "description": "Automated hourly snapshots"}]
        return [
            {"window": "02:00-04:00", "description": "Low-traffic window"},
            {"window": "Sunday 01:00", "description": "Weekly full backup"},
        ]

    def calculate_rto_rpo(self, backup_config: dict[str, Any]) -> dict[str, Any]:
        """
        Calculate achievable RTO and RPO.

        Args:
            backup_config: Backup configuration

        Returns:
            RTO/RPO analysis
        """
        self.logger.info("Calculating RTO and RPO")

        backup_frequency = backup_config.get("backup_frequency", "daily")
        data_size_gb = backup_config.get("data_size_gb", 100)
        restore_speed_gbps = backup_config.get("restore_speed_gbps", 1.0)

        # Calculate RPO
        rpo_mapping = {
            "continuous": 0,
            "hourly": 60,
            "every_4_hours": 240,
            "daily": 1440,
            "weekly": 10080,
        }
        achievable_rpo_minutes = rpo_mapping.get(backup_frequency, 1440)

        # Calculate RTO (restore time + failover time)
        restore_time_minutes = (data_size_gb * 8) / (restore_speed_gbps * 1024 * 60)
        failover_time_minutes = 15  # Average failover overhead
        achievable_rto_minutes = restore_time_minutes + failover_time_minutes

        return {
            "achievable_rpo": {
                "minutes": achievable_rpo_minutes,
                "hours": round(achievable_rpo_minutes / 60, 2),
                "description": self._get_rpo_description(achievable_rpo_minutes),
            },
            "achievable_rto": {
                "minutes": round(achievable_rto_minutes, 0),
                "hours": round(achievable_rto_minutes / 60, 2),
                "breakdown": {
                    "data_restore_minutes": round(restore_time_minutes, 0),
                    "failover_minutes": failover_time_minutes,
                },
            },
            "data_loss_risk": self._assess_data_loss_risk(achievable_rpo_minutes),
            "downtime_risk": self._assess_downtime_risk(achievable_rto_minutes),
        }

    def _get_rpo_description(self, rpo_minutes: int) -> str:
        """Get RPO description."""
        if rpo_minutes == 0:
            return "Zero data loss (continuous protection)"
        if rpo_minutes <= 60:
            return "Minimal data loss (up to 1 hour)"
        if rpo_minutes <= 1440:
            return "Limited data loss (up to 1 day)"
        return "Significant potential data loss (over 1 day)"

    def _assess_data_loss_risk(self, rpo_minutes: int) -> str:
        """Assess data loss risk level."""
        if rpo_minutes <= 15:
            return "minimal"
        if rpo_minutes <= 240:
            return "low"
        if rpo_minutes <= 1440:
            return "medium"
        return "high"

    def _assess_downtime_risk(self, rto_minutes: float) -> str:
        """Assess downtime risk level."""
        if rto_minutes <= 60:
            return "minimal"
        if rto_minutes <= 240:
            return "low"
        if rto_minutes <= 1440:
            return "medium"
        return "high"

    def create_failover_procedure(self, system_config: dict[str, Any]) -> dict[str, Any]:
        """
        Create failover procedure documentation.

        Args:
            system_config: System configuration

        Returns:
            Failover procedure
        """
        self.logger.info("Creating failover procedure")

        has_database = system_config.get("has_database", False)
        has_load_balancer = system_config.get("has_load_balancer", False)

        steps = [
            {
                "step": 1,
                "action": "Detect Failure",
                "details": [
                    "Monitoring system detects primary site failure",
                    "Automatic alert sent to on-call team",
                    "Initiate DR procedure",
                ],
                "estimated_time_minutes": 5,
                "automation": "Automated",
            },
            {
                "step": 2,
                "action": "Validate Failure",
                "details": [
                    "Confirm primary site is truly down",
                    "Check network connectivity",
                    "Verify it's not a false alarm",
                ],
                "estimated_time_minutes": 10,
                "automation": "Manual",
            },
            {
                "step": 3,
                "action": "Activate Secondary Site",
                "details": [
                    "Power on secondary site systems",
                    "Start application services",
                    "Verify system health",
                ],
                "estimated_time_minutes": 15,
                "automation": "Semi-automated",
            },
        ]

        if has_database:
            steps.append(
                {
                    "step": 4,
                    "action": "Database Failover",
                    "details": [
                        "Promote standby database to primary",
                        "Verify data integrity",
                        "Update connection strings",
                    ],
                    "estimated_time_minutes": 20,
                    "automation": "Semi-automated",
                }
            )

        if has_load_balancer:
            steps.append(
                {
                    "step": 5,
                    "action": "Update Load Balancer",
                    "details": [
                        "Update DNS or load balancer config",
                        "Point traffic to secondary site",
                        "Monitor traffic switchover",
                    ],
                    "estimated_time_minutes": 10,
                    "automation": "Automated",
                }
            )

        steps.append(
            {
                "step": len(steps) + 1,
                "action": "Verify Operation",
                "details": [
                    "Run smoke tests",
                    "Verify application functionality",
                    "Monitor for errors",
                ],
                "estimated_time_minutes": 15,
                "automation": "Manual",
            }
        )

        steps.append(
            {
                "step": len(steps) + 1,
                "action": "Notify Stakeholders",
                "details": [
                    "Notify management of failover",
                    "Update status page",
                    "Document incident",
                ],
                "estimated_time_minutes": 5,
                "automation": "Manual",
            }
        )

        total_time = sum(s["estimated_time_minutes"] for s in steps)

        return {
            "total_steps": len(steps),
            "steps": steps,
            "estimated_total_time_minutes": total_time,
            "estimated_total_time_hours": round(total_time / 60, 2),
            "automation_level": self._calculate_automation_level(steps),
            "success_rate": "95%" if has_load_balancer and has_database else "85%",
        }

    def _calculate_automation_level(self, steps: list[dict[str, Any]]) -> str:
        """Calculate overall automation level."""
        automated = sum(1 for s in steps if s["automation"] == "Automated")
        semi_auto = sum(1 for s in steps if s["automation"] == "Semi-automated")
        total = len(steps)

        auto_percent = ((automated + semi_auto * 0.5) / total) * 100

        if auto_percent >= 75:
            return "Highly Automated"
        if auto_percent >= 50:
            return "Moderately Automated"
        return "Mostly Manual"

    # pylint: disable-next=unused-argument  # dr_config reserved for scenario selection; currently simulates a fixed scenario
    def test_dr_plan(self, dr_config: dict[str, Any]) -> dict[str, Any]:
        """
        Simulate DR plan testing.

        Args:
            dr_config: DR configuration (unused; test currently simulates a fixed scenario)

        Returns:
            Test results
        """
        self.logger.info("Testing DR plan")

        # Simulate test execution
        test_results = {
            "test_date": datetime.now().isoformat(),
            "test_type": "Full DR Failover Test",
            "test_duration_minutes": 120,
            "test_phases": [
                {
                    "phase": "Failover Initiation",
                    "status": "passed",
                    "actual_time_minutes": 15,
                    "expected_time_minutes": 20,
                },
                {
                    "phase": "Service Restoration",
                    "status": "passed",
                    "actual_time_minutes": 45,
                    "expected_time_minutes": 60,
                },
                {
                    "phase": "Data Validation",
                    "status": "passed",
                    "actual_time_minutes": 30,
                    "expected_time_minutes": 30,
                },
                {
                    "phase": "Failback",
                    "status": "passed",
                    "actual_time_minutes": 30,
                    "expected_time_minutes": 40,
                },
            ],
            "issues_found": 2,
            "issues": [
                {
                    "severity": "low",
                    "description": "DNS propagation slower than expected",
                    "resolution": "Update DNS TTL to 60 seconds",
                },
                {
                    "severity": "medium",
                    "description": "Manual step required for database promotion",
                    "resolution": "Automate database failover script",
                },
            ],
            "overall_result": "passed",
            "next_test_date": (datetime.now() + timedelta(days=90)).isoformat(),
        }

        # Calculate success metrics
        passed_phases = sum(1 for p in test_results["test_phases"] if p["status"] == "passed")
        success_rate = (passed_phases / len(test_results["test_phases"])) * 100

        test_results["success_rate"] = f"{success_rate}%"
        test_results["improvements_needed"] = len(
            [i for i in test_results["issues"] if i["severity"] in ["medium", "high"]]
        )

        return test_results

    def generate_dr_report(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive DR report."""
        requirements = self.assess_recovery_requirements(system_info)
        backup_strategy = self.create_backup_strategy(
            {
                "rpo_target": requirements["rpo_target"],
                "data_size_gb": system_info.get("data_size_gb", 100),
                "retention_days": 30,
            }
        )
        rto_rpo = self.calculate_rto_rpo(
            {
                "backup_frequency": backup_strategy["backup_frequency"],
                "data_size_gb": system_info.get("data_size_gb", 100),
            }
        )
        failover = self.create_failover_procedure(system_info)

        return {
            "generated_at": datetime.now().isoformat(),
            "system_name": system_info.get("name", "Unknown"),
            "recovery_requirements": requirements,
            "backup_strategy": backup_strategy,
            "rto_rpo_analysis": rto_rpo,
            "failover_procedure": failover,
            "compliance_status": {
                "rto_met": rto_rpo["achievable_rto"]["hours"] <= requirements["rto_target_hours"],
                "rpo_met": rto_rpo["achievable_rpo"]["minutes"] <= requirements["rpo_target"],
            },
            "recommendations": [
                "Schedule quarterly DR testing",
                "Document all DR procedures",
                "Train staff on failover process",
                "Review and update DR plan annually",
            ],
        }
