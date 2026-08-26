# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/cloud_optimizer.py
"""
Cloud Migration Optimizer Module for VMCraft.

Provides cloud-specific optimizations, cost analysis, migration planning,
and multi-cloud recommendations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path


class CloudOptimizer:
    """Cloud migration and optimization engine."""

    # Cloud provider instance types (simplified)
    CLOUD_INSTANCES = {
        "aws": {
            "t3.micro": {"vcpu": 2, "memory_gb": 1, "cost_hour": 0.0104},
            "t3.small": {"vcpu": 2, "memory_gb": 2, "cost_hour": 0.0208},
            "t3.medium": {"vcpu": 2, "memory_gb": 4, "cost_hour": 0.0416},
            "t3.large": {"vcpu": 2, "memory_gb": 8, "cost_hour": 0.0832},
            "m5.large": {"vcpu": 2, "memory_gb": 8, "cost_hour": 0.096},
            "m5.xlarge": {"vcpu": 4, "memory_gb": 16, "cost_hour": 0.192},
            "c5.large": {"vcpu": 2, "memory_gb": 4, "cost_hour": 0.085},
            "r5.large": {"vcpu": 2, "memory_gb": 16, "cost_hour": 0.126},
        },
        "azure": {
            "B1s": {"vcpu": 1, "memory_gb": 1, "cost_hour": 0.0104},
            "B2s": {"vcpu": 2, "memory_gb": 4, "cost_hour": 0.0416},
            "D2s_v3": {"vcpu": 2, "memory_gb": 8, "cost_hour": 0.096},
            "D4s_v3": {"vcpu": 4, "memory_gb": 16, "cost_hour": 0.192},
            "F2s_v2": {"vcpu": 2, "memory_gb": 4, "cost_hour": 0.085},
            "E2s_v3": {"vcpu": 2, "memory_gb": 16, "cost_hour": 0.126},
        },
        "gcp": {
            "e2-micro": {"vcpu": 2, "memory_gb": 1, "cost_hour": 0.0084},
            "e2-small": {"vcpu": 2, "memory_gb": 2, "cost_hour": 0.0168},
            "e2-medium": {"vcpu": 2, "memory_gb": 4, "cost_hour": 0.0336},
            "n1-standard-2": {"vcpu": 2, "memory_gb": 7.5, "cost_hour": 0.095},
            "n1-standard-4": {"vcpu": 4, "memory_gb": 15, "cost_hour": 0.19},
            "n1-highcpu-2": {"vcpu": 2, "memory_gb": 1.8, "cost_hour": 0.071},
            "n1-highmem-2": {"vcpu": 2, "memory_gb": 13, "cost_hour": 0.118},
        },
    }

    def __init__(
        self,
        logger: logging.Logger,
        file_ops: Any,
        mount_root: Path,
    ) -> None:
        """Initialize cloud optimizer."""
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def analyze_cloud_readiness(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze system readiness for cloud migration.

        Args:
            system_info: Current system information

        Returns:
            Cloud readiness assessment
        """
        self.logger.info("Analyzing cloud migration readiness")

        readiness_score = 100
        blockers = []
        warnings = []
        recommendations = []

        # Check OS compatibility
        os_type = system_info.get("os_type", "unknown")
        if os_type not in ["linux", "windows"]:
            blockers.append("Unsupported OS type for cloud migration")
            readiness_score -= 30

        # Check disk size
        disk_size_gb = system_info.get("disk_size_gb", 0)
        if disk_size_gb > 500:
            warnings.append(f"Large disk size ({disk_size_gb}GB) may increase migration time")
            readiness_score -= 10

        # Check for proprietary hardware dependencies
        if system_info.get("hardware_dependencies", []):
            blockers.append("Hardware dependencies detected - requires remediation")
            readiness_score -= 25

        # Check networking
        network_config = system_info.get("network_config", {})
        if network_config.get("static_ip"):
            warnings.append("Static IP configuration requires updating for cloud")
            readiness_score -= 5

        # Generate recommendations
        if readiness_score >= 80:
            recommendations.append("System is ready for cloud migration")
            recommendations.append("Proceed with migration planning")
        elif readiness_score >= 60:
            recommendations.append("Address warnings before migration")
            recommendations.append("Plan for configuration changes")
        else:
            recommendations.append("Resolve blockers before attempting migration")
            recommendations.append("Consider refactoring application architecture")

        return {
            "readiness_score": readiness_score,
            "readiness_level": self._get_readiness_level(readiness_score),
            "blockers": blockers,
            "warnings": warnings,
            "recommendations": recommendations,
            "estimated_migration_time_hours": self._estimate_migration_time(system_info),
        }

    def _get_readiness_level(self, score: int) -> str:
        """Get readiness level from score."""
        if score >= 90:
            return "excellent"
        if score >= 75:
            return "good"
        if score >= 60:
            return "fair"
        if score >= 40:
            return "poor"
        return "not_ready"

    def _estimate_migration_time(self, system_info: dict[str, Any]) -> float:
        """Estimate migration time in hours."""
        base_time = 2.0  # Base migration time
        disk_size_gb = system_info.get("disk_size_gb", 10)

        # Add time based on disk size (assuming 50 GB/hour transfer)
        transfer_time = disk_size_gb / 50

        return round(base_time + transfer_time, 1)

    def recommend_instance_type(
        self, requirements: dict[str, Any], cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """
        Recommend optimal cloud instance type.

        Args:
            requirements: Resource requirements (vcpu, memory_gb, workload_type)
            cloud_provider: Target cloud provider (aws, azure, gcp)

        Returns:
            Instance type recommendations
        """
        self.logger.info(f"Recommending instance type for {cloud_provider}")

        if cloud_provider not in self.CLOUD_INSTANCES:
            return {"error": f"Unsupported cloud provider: {cloud_provider}"}

        required_vcpu = requirements.get("vcpu", 2)
        required_memory_gb = requirements.get("memory_gb", 4)
        requirements.get("workload_type", "balanced")

        instances = self.CLOUD_INSTANCES[cloud_provider]
        recommendations = []

        # Find matching instances
        for instance_type, specs in instances.items():
            if specs["vcpu"] >= required_vcpu and specs["memory_gb"] >= required_memory_gb:
                # Calculate fit score
                vcpu_overhead = (specs["vcpu"] - required_vcpu) / required_vcpu
                memory_overhead = (specs["memory_gb"] - required_memory_gb) / required_memory_gb

                # Prefer minimal overhead (better fit)
                fit_score = 100 - (vcpu_overhead * 20 + memory_overhead * 20)

                recommendations.append(
                    {
                        "instance_type": instance_type,
                        "vcpu": specs["vcpu"],
                        "memory_gb": specs["memory_gb"],
                        "cost_per_hour": specs["cost_hour"],
                        "cost_per_month": round(specs["cost_hour"] * 730, 2),
                        "fit_score": round(max(0, fit_score), 2),
                    }
                )

        # Sort by fit score and cost
        recommendations.sort(key=lambda x: (-x["fit_score"], x["cost_per_hour"]))

        return {
            "cloud_provider": cloud_provider,
            "requirements": requirements,
            "recommendations": recommendations[:5],  # Top 5
            "optimal_choice": recommendations[0] if recommendations else None,
        }

    def calculate_cloud_costs(  # pylint: disable=too-many-locals  # itemizes many independent cost components in one projection
        self, usage_profile: dict[str, Any], cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """
        Calculate projected cloud costs.

        Args:
            usage_profile: Resource usage profile
            cloud_provider: Cloud provider

        Returns:
            Cost projections
        """
        self.logger.info(f"Calculating cloud costs for {cloud_provider}")

        instance_type = usage_profile.get("instance_type")
        if not instance_type:
            # Auto-recommend
            recommendation = self.recommend_instance_type(usage_profile, cloud_provider)
            instance_type = (
                recommendation["optimal_choice"]["instance_type"]
                if recommendation.get("optimal_choice")
                else None
            )

        if not instance_type or instance_type not in self.CLOUD_INSTANCES.get(cloud_provider, {}):
            return {"error": "Invalid instance type"}

        instance = self.CLOUD_INSTANCES[cloud_provider][instance_type]
        hourly_cost = instance["cost_hour"]

        # Calculate costs
        hours_per_month = 730
        uptime_percent = usage_profile.get("uptime_percent", 100)
        actual_hours = hours_per_month * (uptime_percent / 100)

        compute_cost = hourly_cost * actual_hours

        # Storage costs (simplified - $0.10/GB/month)
        storage_gb = usage_profile.get("storage_gb", 100)
        storage_cost = storage_gb * 0.10

        # Network egress (simplified - $0.09/GB)
        network_egress_gb = usage_profile.get("network_egress_gb_month", 50)
        network_cost = network_egress_gb * 0.09

        total_monthly_cost = compute_cost + storage_cost + network_cost

        return {
            "cloud_provider": cloud_provider,
            "instance_type": instance_type,
            "breakdown": {
                "compute": round(compute_cost, 2),
                "storage": round(storage_cost, 2),
                "network": round(network_cost, 2),
            },
            "total_monthly_cost": round(total_monthly_cost, 2),
            "total_annual_cost": round(total_monthly_cost * 12, 2),
            "uptime_hours_month": round(actual_hours, 0),
            "cost_optimization_tips": self._get_cost_optimization_tips(usage_profile),
        }

    def _get_cost_optimization_tips(self, usage_profile: dict[str, Any]) -> list[str]:
        """Get cost optimization tips."""
        tips = []

        uptime = usage_profile.get("uptime_percent", 100)
        if uptime < 80:
            tips.append("Consider using scheduled auto-stop for non-production hours")
            tips.append("Potential savings: 20-40%")

        if usage_profile.get("storage_gb", 0) > 200:
            tips.append("Implement storage tiering with S3 Glacier for archival data")
            tips.append("Potential savings: 30-50% on storage")

        if usage_profile.get("workload_type") == "compute_intensive":
            tips.append("Consider using spot instances for batch workloads")
            tips.append("Potential savings: 60-90% on compute")

        return tips

    def compare_cloud_providers(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """
        Compare costs across multiple cloud providers.

        Args:
            requirements: Resource requirements

        Returns:
            Multi-cloud comparison
        """
        self.logger.info("Comparing cloud providers")

        providers = ["aws", "azure", "gcp"]
        comparisons = []

        for provider in providers:
            recommendation = self.recommend_instance_type(requirements, provider)
            if recommendation.get("optimal_choice"):
                optimal = recommendation["optimal_choice"]
                comparisons.append(
                    {
                        "provider": provider,
                        "instance_type": optimal["instance_type"],
                        "monthly_cost": optimal["cost_per_month"],
                        "specs": {
                            "vcpu": optimal["vcpu"],
                            "memory_gb": optimal["memory_gb"],
                        },
                    }
                )

        # Sort by cost
        comparisons.sort(key=lambda x: x["monthly_cost"])

        # Calculate potential savings
        if len(comparisons) > 1:
            cheapest = comparisons[0]["monthly_cost"]
            most_expensive = comparisons[-1]["monthly_cost"]
            potential_savings = most_expensive - cheapest
            savings_percent = (potential_savings / most_expensive) * 100
        else:
            potential_savings = 0
            savings_percent = 0

        return {
            "providers_compared": len(comparisons),
            "comparisons": comparisons,
            "recommended_provider": comparisons[0]["provider"] if comparisons else None,
            "potential_annual_savings": round(potential_savings * 12, 2),
            "savings_percent": round(savings_percent, 2),
        }

    def generate_migration_plan(
        self, system_info: dict[str, Any], target_cloud: str = "aws"
    ) -> dict[str, Any]:
        """
        Generate comprehensive cloud migration plan.

        Args:
            system_info: Current system information
            target_cloud: Target cloud provider

        Returns:
            Migration plan with steps and timeline
        """
        self.logger.info(f"Generating migration plan for {target_cloud}")

        readiness = self.analyze_cloud_readiness(system_info)

        if readiness["readiness_score"] < 40:
            return {
                "error": "System not ready for migration",
                "blockers": readiness["blockers"],
                "readiness_score": readiness["readiness_score"],
            }

        # Generate migration phases
        phases = [
            {
                "phase": 1,
                "name": "Assessment & Planning",
                "duration_days": 3,
                "tasks": [
                    "Complete cloud readiness assessment",
                    "Document application dependencies",
                    "Create migration runbook",
                    "Set up cloud accounts and networking",
                ],
            },
            {
                "phase": 2,
                "name": "Preparation",
                "duration_days": 5,
                "tasks": [
                    "Provision target cloud resources",
                    "Configure security groups and IAM roles",
                    "Set up monitoring and logging",
                    "Create backup and rollback procedures",
                ],
            },
            {
                "phase": 3,
                "name": "Migration Execution",
                "duration_days": 2,
                "tasks": [
                    "Snapshot current system state",
                    "Transfer data to cloud storage",
                    "Launch cloud instances",
                    "Configure applications and services",
                ],
            },
            {
                "phase": 4,
                "name": "Testing & Validation",
                "duration_days": 3,
                "tasks": [
                    "Functional testing",
                    "Performance testing",
                    "Security validation",
                    "Disaster recovery testing",
                ],
            },
            {
                "phase": 5,
                "name": "Cutover & Optimization",
                "duration_days": 2,
                "tasks": [
                    "DNS cutover to cloud",
                    "Monitor application performance",
                    "Optimize cloud resources",
                    "Decommission on-premises infrastructure",
                ],
            },
        ]

        total_duration = sum(p["duration_days"] for p in phases)

        return {
            "target_cloud": target_cloud,
            "readiness_score": readiness["readiness_score"],
            "migration_phases": phases,
            "total_duration_days": total_duration,
            "total_duration_weeks": round(total_duration / 7, 1),
            "risk_level": "low" if readiness["readiness_score"] >= 80 else "medium",
            "success_probability": f"{readiness['readiness_score']}%",
        }

    def optimize_for_cloud(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """
        Optimize system configuration for cloud environment.

        Args:
            configuration: Current system configuration

        Returns:
            Cloud-optimized configuration recommendations
        """
        self.logger.info("Generating cloud optimization recommendations")

        optimizations = []

        # Networking optimizations
        optimizations.append(
            {
                "category": "Networking",
                "recommendation": "Use cloud-native load balancer instead of software LB",
                "benefit": "Better performance and high availability",
                "priority": "high",
            }
        )

        # Storage optimizations
        if configuration.get("storage_type") == "local":
            optimizations.append(
                {
                    "category": "Storage",
                    "recommendation": "Migrate to cloud block storage (EBS, Azure Disk, Persistent Disk)",
                    "benefit": "Durability, snapshots, and scalability",
                    "priority": "high",
                }
            )

        # Database optimizations
        if configuration.get("has_database"):
            optimizations.append(
                {
                    "category": "Database",
                    "recommendation": "Consider managed database service (RDS, Azure SQL, Cloud SQL)",
                    "benefit": "Automated backups, patching, and high availability",
                    "priority": "medium",
                }
            )

        # Security optimizations
        optimizations.append(
            {
                "category": "Security",
                "recommendation": "Implement cloud security groups and IAM roles",
                "benefit": "Fine-grained access control and audit logging",
                "priority": "high",
            }
        )

        # Monitoring optimizations
        optimizations.append(
            {
                "category": "Monitoring",
                "recommendation": "Use cloud-native monitoring (CloudWatch, Azure Monitor, Cloud Monitoring)",
                "benefit": "Integrated metrics, logs, and alerting",
                "priority": "medium",
            }
        )

        return {
            "total_optimizations": len(optimizations),
            "optimizations": optimizations,
            "high_priority": len([o for o in optimizations if o["priority"] == "high"]),
            "estimated_performance_gain": "20-40%",
            "estimated_cost_reduction": "15-30%",
        }
