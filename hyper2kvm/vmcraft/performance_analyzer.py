# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/performance_analyzer.py
"""
Performance analysis and optimization recommendations.

Provides comprehensive performance analysis:
- Resource usage analysis (CPU, memory, disk, network)
- Bottleneck detection
- Performance metrics extraction
- Optimization recommendations
- Sizing recommendations for migration

Features:
- CPU usage patterns
- Memory consumption analysis
- Disk I/O patterns
- Network throughput estimation
- Process resource usage
- Performance bottleneck identification
- Right-sizing recommendations
"""

from __future__ import annotations

from typing import Any

from ._proc_net_dev import parse_proc_net_dev_interface_names
from .base_analyzer import BaseAnalyzer


class PerformanceAnalyzer(BaseAnalyzer):
    """
    Performance analyzer and optimization recommender.

    Analyzes resource usage and provides optimization recommendations.
    """

    def analyze_performance(self) -> dict[str, Any]:
        """
        Analyze performance comprehensively.

        Returns:
            Performance analysis results
        """
        analysis: dict[str, Any] = {
            "cpu": {},
            "memory": {},
            "disk": {},
            "network": {},
            "bottlenecks": [],
            "recommendations": [],
        }

        # Analyze CPU configuration
        analysis["cpu"] = self._analyze_cpu()

        # Analyze memory configuration
        analysis["memory"] = self._analyze_memory()

        # Analyze disk usage
        analysis["disk"] = self._analyze_disk()

        # Analyze network configuration
        analysis["network"] = self._analyze_network()

        # Detect bottlenecks
        bottlenecks = self._detect_bottlenecks(analysis)
        analysis["bottlenecks"] = bottlenecks

        # Generate recommendations
        recommendations = self._generate_recommendations(analysis)
        analysis["recommendations"] = recommendations

        return analysis

    def _analyze_cpu(self) -> dict[str, Any]:
        """Analyze CPU configuration."""
        cpu: dict[str, Any] = {
            "count": 0,
            "model": None,
            "architecture": None,
            "flags": [],
        }

        # Read /proc/cpuinfo
        if self.file_ops.exists("/proc/cpuinfo"):
            try:
                content = self.file_ops.cat("/proc/cpuinfo")
                cpu_count = 0
                model_name = None
                flags = None

                for line in content.splitlines():
                    if line.startswith("processor"):
                        cpu_count += 1
                    elif line.startswith("model name") and not model_name:
                        model_name = line.split(":", 1)[1].strip()
                    elif line.startswith("flags") and not flags:
                        flags = line.split(":", 1)[1].strip().split()

                cpu["count"] = cpu_count
                cpu["model"] = model_name
                cpu["flags"] = flags[:20] if flags else []  # Limit to 20 flags

                # Detect architecture
                if flags:
                    if "lm" in flags:
                        cpu["architecture"] = "x86_64"
                    else:
                        cpu["architecture"] = "x86"

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort /proc/cpuinfo parse; malformed/unusual guest data must not
                # abort the wider performance analysis.
                self.logger.debug(f"Failed to parse cpuinfo: {e}")

        return cpu

    def _analyze_memory(self) -> dict[str, Any]:
        """Analyze memory configuration."""
        memory: dict[str, Any] = {
            "total_mb": 0,
            "available_mb": 0,
            "swap_total_mb": 0,
            "usage_percent": 0,
        }

        # Read /proc/meminfo
        if self.file_ops.exists("/proc/meminfo"):
            try:
                content = self.file_ops.cat("/proc/meminfo")
                mem_total = 0
                mem_available = 0
                swap_total = 0

                for line in content.splitlines():
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) // 1024  # Convert KB to MB
                    elif line.startswith("MemAvailable:"):
                        mem_available = int(line.split()[1]) // 1024
                    elif line.startswith("SwapTotal:"):
                        swap_total = int(line.split()[1]) // 1024

                memory["total_mb"] = mem_total
                memory["available_mb"] = mem_available
                memory["swap_total_mb"] = swap_total

                if mem_total > 0:
                    memory["usage_percent"] = int(((mem_total - mem_available) / mem_total) * 100)

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort /proc/meminfo parse; malformed/unusual guest data must not
                # abort the wider performance analysis.
                self.logger.debug(f"Failed to parse meminfo: {e}")

        return memory

    def _analyze_disk(self) -> dict[str, Any]:
        """Analyze disk usage."""
        disk: dict[str, Any] = {
            "total_gb": 0,
            "used_gb": 0,
            "available_gb": 0,
            "usage_percent": 0,
            "mount_points": [],
        }

        # Read /proc/mounts to get mount points
        mount_points = []
        if self.file_ops.exists("/proc/mounts"):
            try:
                content = self.file_ops.cat("/proc/mounts")
                for line in content.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        device = parts[0]
                        mount_point = parts[1]
                        fstype = parts[2] if len(parts) >= 3 else "unknown"

                        # Filter out pseudo filesystems
                        if fstype not in [
                            "proc",
                            "sysfs",
                            "devtmpfs",
                            "tmpfs",
                            "devpts",
                            "cgroup",
                            "cgroup2",
                        ]:
                            mount_points.append(
                                {
                                    "device": device,
                                    "mount_point": mount_point,
                                    "fstype": fstype,
                                }
                            )
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort /proc/mounts parse; malformed/unusual guest data must not
                # abort the wider performance analysis.
                pass

        disk["mount_points"] = mount_points[:10]  # Limit to 10

        return disk

    def _analyze_network(self) -> dict[str, Any]:
        """Analyze network configuration."""
        network: dict[str, Any] = {
            "interfaces": [],
            "total_interfaces": 0,
        }

        # Read /proc/net/dev
        if self.file_ops.exists("/proc/net/dev"):
            try:
                content = self.file_ops.cat("/proc/net/dev")
                interfaces = [
                    {"name": iface_name} for iface_name in parse_proc_net_dev_interface_names(content)
                ]

                network["interfaces"] = interfaces
                network["total_interfaces"] = len(interfaces)

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort /proc/net/dev parse; malformed/unusual guest data must not
                # abort the wider performance analysis.
                self.logger.debug(f"Failed to parse network interfaces: {e}")

        return network

    def _detect_bottlenecks(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect performance bottlenecks."""
        bottlenecks = []

        # Check memory
        memory = analysis.get("memory", {})
        if memory.get("total_mb", 0) < 2048:
            bottlenecks.append(
                {
                    "resource": "memory",
                    "severity": "high",
                    "issue": f"Low memory: {memory.get('total_mb')} MB",
                    "recommendation": "Increase memory to at least 2 GB for optimal performance",
                }
            )

        # Check CPU count
        cpu = analysis.get("cpu", {})
        if cpu.get("count", 0) == 1:
            bottlenecks.append(
                {
                    "resource": "cpu",
                    "severity": "medium",
                    "issue": "Single CPU core",
                    "recommendation": "Consider adding more CPU cores for better performance",
                }
            )

        # Check swap usage
        if memory.get("swap_total_mb", 0) == 0:
            bottlenecks.append(
                {
                    "resource": "swap",
                    "severity": "low",
                    "issue": "No swap space configured",
                    "recommendation": "Configure swap space for memory overflow protection",
                }
            )

        return bottlenecks

    def _generate_recommendations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate performance optimization recommendations."""
        recommendations = []

        # Memory recommendations
        memory = analysis.get("memory", {})
        total_mb = memory.get("total_mb", 0)

        if total_mb > 0:
            if total_mb < 1024:
                recommendations.append(
                    {
                        "category": "memory",
                        "priority": "high",
                        "recommendation": f"Increase memory from {total_mb} MB to at least 2 GB",
                        "benefit": "Improved application performance and stability",
                    }
                )
            elif total_mb < 2048:
                recommendations.append(
                    {
                        "category": "memory",
                        "priority": "medium",
                        "recommendation": f"Consider increasing memory from {total_mb} MB to 4 GB",
                        "benefit": "Better multitasking and caching",
                    }
                )

        # CPU recommendations
        cpu = analysis.get("cpu", {})
        cpu_count = cpu.get("count", 0)

        if 0 < cpu_count < 2:
            recommendations.append(
                {
                    "category": "cpu",
                    "priority": "medium",
                    "recommendation": "Add more CPU cores (recommend 2-4 cores)",
                    "benefit": "Improved parallel processing and application responsiveness",
                }
            )

        # Disk recommendations
        disk = analysis.get("disk", {})
        mount_points = disk.get("mount_points", [])

        if len(mount_points) > 5:
            recommendations.append(
                {
                    "category": "disk",
                    "priority": "low",
                    "recommendation": "Consider consolidating mount points",
                    "benefit": "Simplified storage management",
                }
            )

        return recommendations

    def get_performance_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get performance summary.

        Args:
            analysis: Performance analysis results

        Returns:
            Summary dictionary
        """
        cpu = analysis.get("cpu", {})
        memory = analysis.get("memory", {})
        disk = analysis.get("disk", {})
        network = analysis.get("network", {})

        return {
            "cpu_count": cpu.get("count", 0),
            "memory_mb": memory.get("total_mb", 0),
            "memory_usage_percent": memory.get("usage_percent", 0),
            "swap_mb": memory.get("swap_total_mb", 0),
            "mount_points": len(disk.get("mount_points", [])),
            "network_interfaces": network.get("total_interfaces", 0),
            "bottleneck_count": len(analysis.get("bottlenecks", [])),
            "recommendation_count": len(analysis.get("recommendations", [])),
        }

    def get_sizing_recommendation(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get VM sizing recommendation for migration.

        Args:
            analysis: Performance analysis results

        Returns:
            Sizing recommendation
        """
        cpu = analysis.get("cpu", {})
        memory = analysis.get("memory", {})

        # Current configuration
        current_cpu = cpu.get("count", 1)
        current_memory_mb = memory.get("total_mb", 1024)

        # Recommended configuration (with 20% headroom)
        recommended_cpu = max(2, current_cpu)
        recommended_memory_mb = max(2048, int(current_memory_mb * 1.2))

        # Round memory to nearest GB
        recommended_memory_gb = (recommended_memory_mb + 512) // 1024

        return {
            "current": {
                "cpu": current_cpu,
                "memory_mb": current_memory_mb,
                "memory_gb": current_memory_mb // 1024,
            },
            "recommended": {
                "cpu": recommended_cpu,
                "memory_mb": recommended_memory_mb,
                "memory_gb": recommended_memory_gb,
            },
            "headroom": "20%",
            "rationale": "Recommended configuration includes 20% headroom for peak loads",
        }

    def estimate_resource_cost(
        self, analysis: dict[str, Any], cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """
        Estimate cloud resource cost.

        Args:
            analysis: Performance analysis results
            cloud_provider: Cloud provider (aws, azure, gcp)

        Returns:
            Cost estimation
        """
        sizing = self.get_sizing_recommendation(analysis)
        recommended = sizing["recommended"]

        cpu = recommended["cpu"]
        memory_gb = recommended["memory_gb"]

        # Simplified cost estimation (actual prices vary by region and instance type)
        cost_per_month = 0

        if cloud_provider == "aws":
            # Rough estimate: t3.medium (2 vCPU, 4 GB) = ~$30/month
            # Scale based on CPU and memory
            base_cost = 30
            cpu_factor = cpu / 2
            memory_factor = memory_gb / 4
            cost_per_month = base_cost * max(cpu_factor, memory_factor)

        elif cloud_provider == "azure":
            # Similar pricing model
            base_cost = 35
            cpu_factor = cpu / 2
            memory_factor = memory_gb / 4
            cost_per_month = base_cost * max(cpu_factor, memory_factor)

        elif cloud_provider == "gcp":
            # Similar pricing model
            base_cost = 28
            cpu_factor = cpu / 2
            memory_factor = memory_gb / 4
            cost_per_month = base_cost * max(cpu_factor, memory_factor)

        return {
            "provider": cloud_provider,
            "estimated_monthly_cost_usd": round(cost_per_month, 2),
            "cpu": cpu,
            "memory_gb": memory_gb,
            "note": "Estimate based on general-purpose instance types. Actual costs may vary.",
        }
