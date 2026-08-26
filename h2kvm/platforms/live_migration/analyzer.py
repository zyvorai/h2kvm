# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Live Migration Analyzer.

Analyzes VMs to determine if they can be migrated live with minimal downtime,
or if offline migration is required.
"""

import logging
from typing import Any


class LiveMigrationAnalyzer:
    """Analyzes VMs for live migration feasibility."""

    # Downtime thresholds (seconds)
    DOWNTIME_EXCELLENT = 5.0  # <5s: Excellent for live migration
    DOWNTIME_GOOD = 30.0  # <30s: Good for live migration
    DOWNTIME_ACCEPTABLE = 120.0  # <2min: Acceptable for live migration
    # >2min: Should use offline migration

    # Memory thresholds (MB)
    MEMORY_SMALL = 4096  # 4GB
    MEMORY_MEDIUM = 16384  # 16GB
    MEMORY_LARGE = 65536  # 64GB

    # Disk I/O thresholds (MB/s)
    DISK_IO_LOW = 10  # <10 MB/s
    DISK_IO_MEDIUM = 50  # <50 MB/s
    DISK_IO_HIGH = 100  # <100 MB/s

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize Live Migration Analyzer.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def can_migrate_live(self, vm_info: dict[str, Any]) -> dict[str, Any]:
        """
        Determine if VM can be migrated live.

        Args:
            vm_info: VM information dictionary with:
                - name: VM name
                - power_state: VM power state (on/off/suspended)
                - memory_mb: VM memory in MB
                - cpu_count: Number of vCPUs
                - disk_count: Number of disks
                - disk_size_gb: Total disk size in GB
                - disk_provisioning: Disk provisioning type (thin/thick)
                - os_type: Operating system type (linux/windows)
                - guest_tools_running: Whether guest tools are running
                - snapshot_count: Number of snapshots
                - connected_devices: List of connected devices (USB, CD, etc.)

        Returns:
            Dictionary with analysis results:
            {
                "feasible": bool,  # Can migrate live
                "recommended": bool,  # Recommended to migrate live
                "confidence": float,  # Confidence score (0.0-1.0)
                "estimated_downtime_seconds": float,
                "downtime_category": str,  # "excellent", "good", "acceptable", "poor"
                "reasons": list[str],  # Reasons for decision
                "warnings": list[str],  # Warnings about migration
                "requirements": list[str],  # Requirements for live migration
                "fallback_to_offline": bool,  # Fallback to offline if live fails
            }
        """
        analysis: dict[str, Any] = {
            "feasible": False,
            "recommended": False,
            "confidence": 0.0,
            "estimated_downtime_seconds": 0.0,
            "downtime_category": "unknown",
            "reasons": [],
            "warnings": [],
            "requirements": [],
            "fallback_to_offline": True,
        }

        try:
            # Check power state
            power_state = vm_info.get("power_state", "").lower()
            if power_state != "on":
                analysis["reasons"].append(f"VM is {power_state}, not running")
                analysis["feasible"] = False
                analysis["recommended"] = False
                return analysis

            # Check for blockers
            blockers = self._check_blockers(vm_info)
            if blockers:
                analysis["reasons"].extend(blockers)
                analysis["feasible"] = False
                analysis["recommended"] = False
                return analysis

            # VM is potentially migratable live
            analysis["feasible"] = True

            # Estimate downtime
            downtime = self._estimate_downtime(vm_info)
            analysis["estimated_downtime_seconds"] = downtime

            # Categorize downtime
            if downtime <= self.DOWNTIME_EXCELLENT:
                analysis["downtime_category"] = "excellent"
                analysis["confidence"] = 0.95
                analysis["recommended"] = True
            elif downtime <= self.DOWNTIME_GOOD:
                analysis["downtime_category"] = "good"
                analysis["confidence"] = 0.85
                analysis["recommended"] = True
            elif downtime <= self.DOWNTIME_ACCEPTABLE:
                analysis["downtime_category"] = "acceptable"
                analysis["confidence"] = 0.70
                analysis["recommended"] = True
            else:
                analysis["downtime_category"] = "poor"
                analysis["confidence"] = 0.50
                analysis["recommended"] = False
                analysis["reasons"].append(
                    f"Estimated downtime ({downtime:.1f}s) exceeds acceptable threshold"
                )

            # Add recommendations
            analysis["requirements"].extend(self._get_requirements(vm_info))
            analysis["warnings"].extend(self._get_warnings(vm_info))

            # Build reason list
            if analysis["recommended"]:
                analysis["reasons"].append(
                    f"Live migration feasible with {downtime:.1f}s estimated downtime"
                )
            else:
                analysis["reasons"].append("Offline migration recommended for this VM configuration")

            self.logger.info(
                f"Live migration analysis for {vm_info.get('name')}: "
                f"Feasible={analysis['feasible']}, "
                f"Recommended={analysis['recommended']}, "
                f"Downtime={downtime:.1f}s"
            )

        except Exception as e:
            analysis["reasons"].append(f"Analysis error: {e}")
            self.logger.exception(f"Live migration analysis failed: {e}")

        return analysis

    def _check_blockers(self, vm_info: dict[str, Any]) -> list[str]:
        """Check for conditions that block live migration."""
        blockers = []

        # Check for snapshots
        snapshot_count = vm_info.get("snapshot_count", 0)
        if snapshot_count > 0:
            blockers.append(f"VM has {snapshot_count} snapshot(s) - must consolidate before live migration")

        # Check for connected devices (USB, CD-ROM, etc.)
        connected_devices = vm_info.get("connected_devices", [])
        blocking_devices = [d for d in connected_devices if d.get("type") in ("usb", "cdrom", "floppy")]
        if blocking_devices:
            device_types = ", ".join([d.get("type", "unknown") for d in blocking_devices])
            blockers.append(f"Connected devices blocking live migration: {device_types}")

        # Check guest tools
        if not vm_info.get("guest_tools_running", False):
            blockers.append("Guest tools not running - required for reliable live migration")

        return blockers

    def _estimate_downtime(self, vm_info: dict[str, Any]) -> float:
        """
        Estimate live migration downtime in seconds.

        Downtime estimation formula:
        - Base downtime: 1-2 seconds (switchover time)
        - Memory transfer: memory_mb / transfer_rate_mbps
        - Disk sync: depends on dirty rate and pre-copy
        - Network latency: 0.1-0.5 seconds

        Returns:
            Estimated downtime in seconds
        """
        base_downtime = 2.0  # Base switchover time

        # Memory impact
        memory_mb = vm_info.get("memory_mb", 0)
        if memory_mb <= self.MEMORY_SMALL:
            memory_factor = 0.5
        elif memory_mb <= self.MEMORY_MEDIUM:
            memory_factor = 1.0
        elif memory_mb <= self.MEMORY_LARGE:
            memory_factor = 2.0
        else:
            memory_factor = 3.0

        # Disk I/O impact (estimated)
        vm_info.get("disk_size_gb", 0)
        disk_provisioning = vm_info.get("disk_provisioning", "thin")

        disk_factor = 0.5 if disk_provisioning == "thin" else 1.0

        # OS type impact
        os_type = vm_info.get("os_type", "").lower()
        os_factor = 1.5 if "windows" in os_type else 1.0  # Windows tends to have higher memory churn

        # Calculate estimated downtime
        estimated_downtime = base_downtime + (memory_factor * disk_factor * os_factor)

        return round(estimated_downtime, 2)

    def _get_requirements(self, vm_info: dict[str, Any]) -> list[str]:
        """Get requirements for live migration."""
        requirements = []

        # Guest tools
        if not vm_info.get("guest_tools_running"):
            requirements.append("Install and start guest tools (VMware Tools, QEMU Guest Agent)")

        # Network connectivity
        requirements.append("Ensure network connectivity between source and target hosts")

        # Storage requirements
        disk_size_gb = vm_info.get("disk_size_gb", 0)
        requirements.append(f"Ensure target has at least {disk_size_gb:.1f}GB available storage")

        # Memory requirements
        memory_mb = vm_info.get("memory_mb", 0)
        requirements.append(f"Ensure target has at least {memory_mb}MB available memory")

        return requirements

    def _get_warnings(self, vm_info: dict[str, Any]) -> list[str]:
        """Get warnings about live migration."""
        warnings = []

        # High memory warning
        memory_mb = vm_info.get("memory_mb", 0)
        if memory_mb > self.MEMORY_LARGE:
            warnings.append(f"Large memory allocation ({memory_mb}MB) may increase migration time")

        # Multiple disks warning
        disk_count = vm_info.get("disk_count", 0)
        if disk_count > 3:
            warnings.append(f"Multiple disks ({disk_count}) may increase migration complexity")

        # Thick provisioning warning
        if vm_info.get("disk_provisioning") == "thick":
            warnings.append("Thick-provisioned disks will require full disk transfer")

        return warnings

    def analyze_batch(self, vms: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Analyze multiple VMs for live migration.

        Args:
            vms: List of VM information dictionaries

        Returns:
            Batch analysis results with summary statistics
        """
        results = {
            "total_vms": len(vms),
            "live_feasible": 0,
            "live_recommended": 0,
            "offline_required": 0,
            "vms": [],
        }

        for vm in vms:
            analysis = self.can_migrate_live(vm)
            results["vms"].append(
                {
                    "name": vm.get("name"),
                    "analysis": analysis,
                }
            )

            if analysis["feasible"]:
                results["live_feasible"] += 1
            if analysis["recommended"]:
                results["live_recommended"] += 1
            else:
                results["offline_required"] += 1

        # Calculate percentages
        if results["total_vms"] > 0:
            results["live_feasible_pct"] = results["live_feasible"] / results["total_vms"] * 100
            results["live_recommended_pct"] = results["live_recommended"] / results["total_vms"] * 100

        self.logger.info(
            f"Batch analysis: {results['total_vms']} VMs - "
            f"{results['live_recommended']} recommended for live migration, "
            f"{results['offline_required']} require offline migration"
        )

        return results
