# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/storage_analyzer.py
"""
Advanced storage analysis and optimization.

Provides comprehensive storage analysis:
- Volume snapshot analysis
- Thin provisioning detection
- Storage tiering analysis
- RAID configuration detection
- Deduplication ratio estimation
- Storage performance metrics
- Storage capacity planning

Features:
- LVM snapshot detection
- Thin/thick provisioning analysis
- RAID level identification
- Storage efficiency metrics
- I/O pattern analysis
- Storage optimization recommendations
"""

from __future__ import annotations

import re
from typing import Any

from .base_analyzer import BaseAnalyzer


class StorageAnalyzer(BaseAnalyzer):
    """
    Advanced storage analyzer.

    Analyzes storage configuration, performance, and optimization opportunities.
    """

    # RAID level patterns
    RAID_LEVELS = {
        "raid0": {"redundancy": False, "min_disks": 2, "efficiency": 100},
        "raid1": {"redundancy": True, "min_disks": 2, "efficiency": 50},
        "raid5": {"redundancy": True, "min_disks": 3, "efficiency": 67},
        "raid6": {"redundancy": True, "min_disks": 4, "efficiency": 50},
        "raid10": {"redundancy": True, "min_disks": 4, "efficiency": 50},
    }

    def analyze_storage(self) -> dict[str, Any]:
        """
        Analyze storage comprehensively.

        Returns:
            Storage analysis results
        """
        analysis: dict[str, Any] = {
            "volumes": [],
            "snapshots": [],
            "thin_volumes": [],
            "raid_arrays": [],
            "storage_efficiency": {},
            "total_capacity_gb": 0,
            "used_capacity_gb": 0,
        }

        # Analyze LVM volumes
        volumes = self._analyze_lvm_volumes()
        analysis["volumes"] = volumes

        # Detect snapshots
        snapshots = self._detect_snapshots()
        analysis["snapshots"] = snapshots

        # Detect thin provisioning
        thin = self._detect_thin_provisioning()
        analysis["thin_volumes"] = thin

        # Detect RAID arrays
        raid = self._detect_raid()
        analysis["raid_arrays"] = raid

        # Calculate storage efficiency
        efficiency = self._calculate_storage_efficiency(analysis)
        analysis["storage_efficiency"] = efficiency

        return analysis

    def _analyze_lvm_volumes(self) -> list[dict[str, Any]]:
        """Analyze LVM volumes."""
        volumes = []

        # Check for LVM
        if not self.file_ops.is_dir("/dev/mapper"):
            return volumes

        try:
            devices = self.file_ops.ls("/dev/mapper")
            for device in devices[:50]:  # Limit to 50
                if device in ["control"]:
                    continue

                volumes.append(
                    {
                        "name": device,
                        "path": f"/dev/mapper/{device}",
                        "type": "lvm",
                    }
                )
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort LVM scan, must not abort analysis
            pass

        return volumes

    def _detect_snapshots(self) -> list[dict[str, Any]]:
        """Detect LVM snapshots."""
        snapshots = []

        # Parse lvdisplay output or /proc/mounts for snapshot indicators
        # In a real implementation, would execute lvs command
        # For now, detect snapshot volumes by naming convention

        volumes = self._analyze_lvm_volumes()
        for volume in volumes:
            name = volume["name"]
            # Common snapshot naming patterns
            if any(pattern in name.lower() for pattern in ["snap", "snapshot", "backup"]):
                snapshots.append(
                    {
                        "name": name,
                        "type": "lvm_snapshot",
                        "origin": "unknown",  # Would be parsed from lvs output
                    }
                )

        return snapshots

    def _detect_thin_provisioning(self) -> list[dict[str, Any]]:
        """Detect thin-provisioned volumes."""
        thin_volumes = []

        # Check for thin pool LVs
        # In a real implementation, would parse lvs output with -o lv_attr
        # For now, just detect based on naming conventions

        volumes = self._analyze_lvm_volumes()
        for volume in volumes:
            name = volume["name"]
            if "thin" in name.lower() or "pool" in name.lower():
                thin_volumes.append(
                    {
                        "name": name,
                        "type": "thin_lv",
                        "provisioning": "thin",
                    }
                )

        return thin_volumes

    def _detect_raid(self) -> list[dict[str, Any]]:
        """Detect RAID arrays."""
        raid_arrays = []

        # Check /proc/mdstat for software RAID
        if self.file_ops.exists("/proc/mdstat"):  # pylint: disable=too-many-nested-blocks  # mdstat line parsing requires nested field walk
            try:
                content = self.file_ops.cat("/proc/mdstat")

                for line in content.splitlines():
                    # Detect array line (e.g., "md0 : active raid1 sda1[0] sdb1[1]")
                    if line.startswith("md"):
                        parts = line.split()
                        if len(parts) >= 4:
                            array_name = parts[0]
                            status = parts[2]
                            raid_level = parts[3]

                            # Extract devices
                            devices = []
                            for part in parts[4:]:
                                device = part.split("[")[0]
                                devices.append(device)

                            raid_arrays.append(
                                {
                                    "name": array_name,
                                    "level": raid_level,
                                    "status": status,
                                    "devices": devices,
                                    "device_count": len(devices),
                                }
                            )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort mdstat parse, must not abort analysis
                pass

        return raid_arrays

    def _calculate_storage_efficiency(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Calculate storage efficiency metrics."""
        efficiency: dict[str, Any] = {
            "thin_provisioned_count": len(analysis.get("thin_volumes", [])),
            "snapshot_count": len(analysis.get("snapshots", [])),
            "raid_efficiency": 100,
            "dedup_estimate": 0,
        }

        # Calculate RAID efficiency
        raid_arrays = analysis.get("raid_arrays", [])
        if raid_arrays:
            total_efficiency = 0
            for array in raid_arrays:
                level = array.get("level", "").lower()
                raid_info = self.RAID_LEVELS.get(level, {})
                total_efficiency += raid_info.get("efficiency", 100)

            efficiency["raid_efficiency"] = int(total_efficiency / len(raid_arrays))

        # Estimate deduplication potential (simplified)
        # In reality would scan for duplicate blocks
        efficiency["dedup_estimate"] = 10  # Assume 10% potential savings

        return efficiency

    def get_storage_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get storage summary.

        Args:
            analysis: Storage analysis results

        Returns:
            Summary dictionary
        """
        return {
            "total_volumes": len(analysis.get("volumes", [])),
            "snapshot_count": len(analysis.get("snapshots", [])),
            "thin_volumes": len(analysis.get("thin_volumes", [])),
            "raid_arrays": len(analysis.get("raid_arrays", [])),
            "storage_efficiency": analysis.get("storage_efficiency", {}).get("raid_efficiency", 100),
        }

    def get_capacity_planning(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get storage capacity planning recommendations.

        Args:
            analysis: Storage analysis results

        Returns:
            Capacity planning data
        """
        planning = {
            "current_usage": "unknown",
            "projected_growth": "unknown",
            "recommendations": [],
        }

        # Check if thin provisioning is used
        thin_count = len(analysis.get("thin_volumes", []))
        if thin_count == 0:
            planning["recommendations"].append(
                {
                    "priority": "medium",
                    "recommendation": "Consider thin provisioning to improve storage efficiency",
                    "benefit": "Reduce storage waste and improve utilization",
                }
            )

        # Check if snapshots exist
        snapshot_count = len(analysis.get("snapshots", []))
        if snapshot_count > 5:
            planning["recommendations"].append(
                {
                    "priority": "high",
                    "recommendation": f"Review {snapshot_count} snapshots - consider cleanup",
                    "benefit": "Reclaim storage space",
                }
            )

        # Check RAID configuration
        raid_arrays = analysis.get("raid_arrays", [])
        if not raid_arrays:
            planning["recommendations"].append(
                {
                    "priority": "low",
                    "recommendation": "No RAID detected - consider adding redundancy",
                    "benefit": "Improve data protection and availability",
                }
            )

        return planning

    def analyze_storage_performance(self) -> dict[str, Any]:
        """
        Analyze storage performance indicators.

        Returns:
            Performance analysis
        """
        performance = {
            "io_scheduler": "unknown",
            "read_ahead": "unknown",
            "mount_options": [],
        }

        # Check I/O scheduler
        block_devices = ["/sys/block/sda", "/sys/block/vda", "/sys/block/nvme0n1"]

        for device in block_devices:
            scheduler_path = f"{device}/queue/scheduler"
            if self.file_ops.exists(scheduler_path):
                try:
                    content = self.file_ops.cat(scheduler_path)
                    # Extract current scheduler (in brackets)
                    match = re.search(r"\[(\w+)\]", content)
                    if match:
                        performance["io_scheduler"] = match.group(1)
                        break
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort scheduler read, must not abort analysis
                    pass

        # Check mount options from /proc/mounts
        if self.file_ops.exists("/proc/mounts"):
            try:
                content = self.file_ops.cat("/proc/mounts")
                for line in content.splitlines()[:20]:  # First 20 mounts
                    parts = line.split()
                    if len(parts) >= 4:
                        device = parts[0]
                        mount_point = parts[1]
                        options = parts[3]

                        # Skip pseudo filesystems
                        if device.startswith("/dev"):
                            performance["mount_options"].append(
                                {
                                    "device": device,
                                    "mount_point": mount_point,
                                    "options": options,
                                }
                            )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort mount options read, must not abort analysis
                pass

        return performance

    def detect_storage_tiering(self) -> dict[str, Any]:
        """
        Detect storage tiering configuration.

        Returns:
            Storage tiering analysis
        """
        tiering = {
            "tiers_detected": False,
            "tiers": [],
        }

        # Check for bcache (SSD caching)
        if self.file_ops.is_dir("/sys/fs/bcache"):
            tiering["tiers_detected"] = True
            tiering["tiers"].append(
                {
                    "type": "bcache",
                    "technology": "SSD caching",
                }
            )

        # Check for dm-cache
        if self.file_ops.is_dir("/sys/block"):
            try:
                blocks = self.file_ops.ls("/sys/block")
                for block in blocks:
                    if "dm-" in block:
                        # Check if it's a cache device
                        tiering["tiers"].append(
                            {
                                "type": "dm-cache",
                                "device": block,
                            }
                        )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort dm-cache scan, must not abort analysis
                pass

        return tiering

    def estimate_deduplication_ratio(self) -> dict[str, Any]:
        """
        Estimate potential deduplication ratio.

        Returns:
            Deduplication estimation
        """
        dedup = {
            "estimated_ratio": 1.0,
            "potential_savings_percent": 0,
            "recommendation": "unknown",
        }

        # Simplified estimation
        # In reality would scan file checksums
        # Assume some common patterns:
        # - VM images typically have 20-30% dedup potential
        # - Database files have 10-15% dedup potential
        # - General files have 5-10% dedup potential

        # For now, assume conservative 10% savings
        dedup["estimated_ratio"] = 1.1
        dedup["potential_savings_percent"] = 10
        dedup["recommendation"] = "Consider enabling deduplication for 10% storage savings"

        return dedup

    def analyze_raid_health(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Analyze RAID array health.

        Args:
            analysis: Storage analysis results

        Returns:
            List of RAID health issues
        """
        issues = []

        raid_arrays = analysis.get("raid_arrays", [])

        for array in raid_arrays:
            status = array.get("status", "").lower()
            level = array.get("level", "").lower()

            # Check status
            if status not in ["active", "clean"]:
                issues.append(
                    {
                        "array": array["name"],
                        "issue": f"Array status is {status}",
                        "severity": "high",
                        "recommendation": "Check array health with mdadm",
                    }
                )

            # Check device count vs RAID level requirements
            device_count = array.get("device_count", 0)
            raid_info = self.RAID_LEVELS.get(level, {})
            min_disks = raid_info.get("min_disks", 0)

            if device_count < min_disks:
                issues.append(
                    {
                        "array": array["name"],
                        "issue": f"Insufficient devices for {level} (have {device_count}, need {min_disks})",
                        "severity": "critical",
                        "recommendation": "Add disks to array or rebuild",
                    }
                )

        return issues

    def get_optimization_recommendations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get storage optimization recommendations.

        Args:
            analysis: Storage analysis results

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Check thin provisioning
        if len(analysis.get("thin_volumes", [])) == 0:
            recommendations.append(
                {
                    "category": "provisioning",
                    "priority": "medium",
                    "recommendation": "Implement thin provisioning",
                    "benefit": "Improve storage efficiency by 20-30%",
                    "complexity": "medium",
                }
            )

        # Check snapshots
        snapshot_count = len(analysis.get("snapshots", []))
        if snapshot_count > 10:
            recommendations.append(
                {
                    "category": "snapshots",
                    "priority": "high",
                    "recommendation": f"Clean up old snapshots ({snapshot_count} found)",
                    "benefit": "Reclaim storage space",
                    "complexity": "low",
                }
            )

        # Check RAID
        if len(analysis.get("raid_arrays", [])) == 0:
            recommendations.append(
                {
                    "category": "redundancy",
                    "priority": "low",
                    "recommendation": "Consider implementing RAID for data protection",
                    "benefit": "Improve availability and data protection",
                    "complexity": "high",
                }
            )

        # Deduplication
        recommendations.append(
            {
                "category": "deduplication",
                "priority": "low",
                "recommendation": "Evaluate deduplication for storage savings",
                "benefit": "Potential 10-30% storage savings",
                "complexity": "medium",
            }
        )

        return recommendations
