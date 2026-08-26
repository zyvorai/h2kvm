#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Worker Capability Detection for H2KVM

Detects environment capabilities and enables graceful degradation:
- USERSPACE_ONLY: Basic VMDK→QCOW2 conversion (kind, restrictive environments)
- NBD_INSPECTION: NBD device + partition reading (partial NBD support)
- FULL_OFFLINE_FIXES: Complete migration with guest fixes (production)
"""

import logging
import os
import subprocess
import tempfile
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from h2kvm.core.structured_log import log_event


class CapabilityLevel(Enum):
    """Environment capability levels for worker operations"""

    USERSPACE_ONLY = 1
    NBD_INSPECTION = 2
    FULL_OFFLINE_FIXES = 3

    def __str__(self):
        return self.name.lower().replace("_", "-")

    def can_mount_partitions(self) -> bool:
        """Check if this level supports mounting partitions"""
        return self == CapabilityLevel.FULL_OFFLINE_FIXES

    def can_inspect_disk(self) -> bool:
        """Check if this level supports disk inspection via NBD"""
        return self in (CapabilityLevel.NBD_INSPECTION, CapabilityLevel.FULL_OFFLINE_FIXES)

    def can_convert(self) -> bool:
        """Check if this level supports VMDK conversion"""
        return True  # All levels support conversion


class CapabilityDetector:
    """
    Detect worker environment capabilities at startup

    Performs progressive checks to determine what operations are available:
    1. NBD module availability
    2. NBD device creation
    3. NBD partition device support

    Example:
        detector = CapabilityDetector()
        level = detector.detect()

        if level == CapabilityLevel.FULL_OFFLINE_FIXES:
            # Full migration with offline fixes
        elif level == CapabilityLevel.NBD_INSPECTION:
            # Conversion + inspection only
        else:
            # Basic conversion only
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.detected_level: Optional[CapabilityLevel] = None
        self.detection_details: dict[str, any] = {}

    def detect(self) -> CapabilityLevel:
        """
        Detect capabilities using progressive checks

        Returns:
            CapabilityLevel: Detected capability level
        """
        self.logger.info("🔍 Detecting environment capabilities...")

        # Check 1: Can we access NBD module?
        if not self._check_nbd_module():
            self.logger.info("❌ NBD module unavailable")
            self.detected_level = CapabilityLevel.USERSPACE_ONLY
            self.detection_details["nbd_module"] = False
            self.detection_details["reason"] = "NBD kernel module not available"
            return self.detected_level

        # Check 2: Can we create NBD device?
        if not self._check_nbd_device():
            self.logger.warning(
                "⚠️  NBD module loaded but device creation failed.\n"
                "    Try: modprobe nbd max_part=16\n"
                "    Verify device exists: ls /dev/nbd0\n"
                "    Check permissions: ensure running as root or in 'disk' group."
            )
            self.detected_level = CapabilityLevel.USERSPACE_ONLY
            self.detection_details["nbd_device"] = False
            self.detection_details["reason"] = "NBD device /dev/nbd0 not accessible"
            return self.detected_level

        # Check 3: Do we get partition devices?
        if not self._check_nbd_partitions():
            self.logger.info("⚠️  NBD device available but partition devices missing")
            self.detected_level = CapabilityLevel.NBD_INSPECTION
            self.detection_details["nbd_partitions"] = False
            self.detection_details["reason"] = "NBD partition devices not created (likely Docker/kind)"
            return self.detected_level

        # Full capabilities available
        self.logger.info("✅ Full offline fix capabilities available")
        self.detected_level = CapabilityLevel.FULL_OFFLINE_FIXES
        self.detection_details["nbd_partitions"] = True
        self.detection_details["reason"] = "All capabilities available"
        log_event(
            "capability_detected",
            level=self.detected_level.name,
            nbd_module=True,
            nbd_device=True,
            nbd_partitions=True,
        )
        return self.detected_level

    def _check_nbd_module(self) -> bool:  # pylint: disable=too-many-return-statements
        # reason: each detection branch (already loaded, modprobe success, timeout,
        # missing binary, permission denied, other error) needs its own distinct
        # logged outcome for accurate capability reporting.
        """Check if NBD kernel module is available and loadable"""
        try:
            # First check if module is already loaded
            result = subprocess.run(["lsmod"], capture_output=True, timeout=5, text=True, check=False)

            if "nbd" in result.stdout:
                self.logger.debug("NBD module already loaded")
                self.detection_details["nbd_module_preloaded"] = True
                return True

            # Try to load NBD module with partition support
            result = subprocess.run(
                ["modprobe", "nbd", "max_part=16"], capture_output=True, timeout=5, check=False
            )

            if result.returncode == 0:
                self.logger.info("✅ NBD module loaded successfully")
                self.detection_details["nbd_module"] = True
                self.detection_details["nbd_module_preloaded"] = False
                return True
            self.logger.debug("modprobe failed: %s", result.stderr.decode())
            self.detection_details["nbd_module_error"] = result.stderr.decode()
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("NBD module load timed out")
            self.detection_details["nbd_module_error"] = "Timeout"
            return False
        except FileNotFoundError:
            self.logger.debug("modprobe command not found")
            self.detection_details["nbd_module_error"] = "modprobe not found"
            return False
        except PermissionError:
            self.logger.debug("Permission denied loading NBD module")
            self.detection_details["nbd_module_error"] = "Permission denied"
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort capability probe -- any unexpected failure should degrade
            # to USERSPACE_ONLY rather than crash startup detection.
            self.logger.debug("NBD module check failed: %s", e)
            self.detection_details["nbd_module_error"] = str(e)
            return False

    def _check_nbd_device(self) -> bool:
        """Check if NBD devices exist and are accessible"""
        try:
            # Check for /dev/nbd0
            nbd_path = Path("/dev/nbd0")

            if nbd_path.exists():
                # Verify it's a block device
                if nbd_path.stat().st_mode & 0o060000:  # S_IFBLK
                    self.logger.info("✅ NBD device /dev/nbd0 available")
                    self.detection_details["nbd_device"] = True
                    self.detection_details["nbd_device_path"] = "/dev/nbd0"
                    return True
                self.logger.debug("/dev/nbd0 exists but is not a block device")
                self.detection_details["nbd_device_error"] = "Not a block device"
                return False
            self.logger.debug("/dev/nbd0 not found")
            self.detection_details["nbd_device_error"] = "Device node missing"
            return False

        except PermissionError:
            self.logger.debug("Permission denied accessing /dev/nbd0")
            self.detection_details["nbd_device_error"] = "Permission denied"
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort capability probe -- any unexpected failure should degrade
            # to USERSPACE_ONLY rather than crash startup detection.
            self.logger.debug("NBD device check failed: %s", e)
            self.detection_details["nbd_device_error"] = str(e)
            return False

    def _check_nbd_partitions(self) -> bool:  # pylint: disable=too-many-return-statements
        # reason: each detection branch (image-creation failure, attach failure, partition
        # found/missing, timeout, missing binary, other error) needs its own distinct
        # logged outcome for accurate capability reporting.
        """
        Check if NBD partition devices are supported

        This is the critical check that differentiates Level 2 from Level 3.
        We create a small test image with partitions and see if /dev/nbd0p1 appears.

        Returns:
            bool: True if partition devices are created, False otherwise
        """
        test_image = None
        nbd_device = "/dev/nbd0"

        try:
            # Create a small test QCOW2 with a partition table
            test_image = self._create_test_image()

            if not test_image:
                self.logger.debug("Failed to create test image")
                return False

            # Try to attach it to NBD
            self.logger.debug("Attaching test image to NBD...")
            result = subprocess.run(
                ["qemu-nbd", "--connect", nbd_device, test_image],
                capture_output=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                self.logger.debug("Failed to attach test image: %s", result.stderr.decode())
                self.detection_details["nbd_attach_error"] = result.stderr.decode()
                return False

            # Give udev time to create partition devices
            time.sleep(2)

            # Check if partition device was created
            partition_device = Path(f"{nbd_device}p1")
            partition_exists = partition_device.exists()

            # Disconnect NBD
            subprocess.run(
                ["qemu-nbd", "--disconnect", nbd_device], capture_output=True, timeout=5, check=False
            )

            if partition_exists:
                self.logger.info("✅ NBD partition devices supported (%sp1 found)", nbd_device)
                self.detection_details["nbd_partitions"] = True
                self.detection_details["test_partition_created"] = True
                return True
            self.logger.info("❌ NBD partition devices NOT created (%sp1 missing)", nbd_device)
            self.detection_details["nbd_partitions"] = False
            self.detection_details["test_partition_created"] = False
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("NBD partition check timed out")
            self.detection_details["nbd_partition_error"] = "Timeout"
            return False
        except FileNotFoundError:
            self.logger.debug("qemu-nbd command not found")
            self.detection_details["nbd_partition_error"] = "qemu-nbd not found"
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort capability probe -- any unexpected failure should degrade
            # gracefully rather than crash startup detection.
            self.logger.debug("NBD partition check failed: %s", e)
            self.detection_details["nbd_partition_error"] = str(e)
            return False
        finally:
            # Ensure NBD is disconnected
            try:
                subprocess.run(
                    ["qemu-nbd", "--disconnect", nbd_device],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except Exception:  # pylint: disable=broad-exception-caught
                # reason: cleanup in a finally block must not raise and mask the real error.
                pass

            # Clean up test image
            if test_image and os.path.exists(test_image):
                try:
                    os.unlink(test_image)
                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: best-effort temp file cleanup must not raise.
                    pass

    def _create_test_image(self) -> Optional[str]:
        """
        Create a small test QCOW2 image with a partition table

        Returns:
            str: Path to test image, or None on failure
        """
        path = None
        try:
            # Create temporary file
            fd, path = tempfile.mkstemp(suffix=".qcow2", prefix="nbd-test-")
            os.close(fd)

            # Create 10MB QCOW2 image
            result = subprocess.run(
                ["qemu-img", "create", "-f", "qcow2", path, "10M"],
                capture_output=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                self.logger.debug(f"Failed to create test image: {result.stderr.decode()}")
                os.unlink(path)
                return None

            # Use parted to create partition table
            # First create GPT label
            subprocess.run(
                ["parted", "-s", path, "mklabel", "gpt"], capture_output=True, timeout=10, check=False
            )

            # Create one partition
            subprocess.run(
                ["parted", "-s", path, "mkpart", "primary", "1MiB", "9MiB"],
                capture_output=True,
                timeout=10,
                check=False,
            )

            return path

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort test-image creation used only for capability probing --
            # any failure should just report "no partition support" rather than crash.
            self.logger.debug("Test image creation failed: %s", e)
            if path and os.path.exists(path):
                os.unlink(path)
            return None

    def get_capability_report(self) -> dict[str, any]:
        """
        Get detailed capability report

        Returns:
            dict: Capability report with level, operations, and limitations
        """
        return {
            "level": self.detected_level.value if self.detected_level else 0,
            "level_name": self.detected_level.name if self.detected_level else "UNKNOWN",
            "level_description": str(self.detected_level) if self.detected_level else "unknown",
            "details": self.detection_details,
            "operations": self._get_available_operations(),
            "limitations": self._get_limitations(),
            "recommendations": self._get_recommendations(),
        }

    def _get_available_operations(self) -> list[str]:
        """List operations available at detected level"""
        ops = {
            CapabilityLevel.USERSPACE_ONLY: [
                "vmdk_parsing",
                "qcow2_conversion",
                "compression",
                "format_detection",
                "descriptor_analysis",
            ],
            CapabilityLevel.NBD_INSPECTION: [
                "vmdk_parsing",
                "qcow2_conversion",
                "compression",
                "format_detection",
                "descriptor_analysis",
                "nbd_device_attach",
                "partition_table_reading",
                "filesystem_detection",
                "lvm_metadata_inspection",
                "disk_geometry_analysis",
            ],
            CapabilityLevel.FULL_OFFLINE_FIXES: [
                "vmdk_parsing",
                "qcow2_conversion",
                "compression",
                "format_detection",
                "descriptor_analysis",
                "nbd_device_attach",
                "partition_table_reading",
                "filesystem_detection",
                "lvm_metadata_inspection",
                "disk_geometry_analysis",
                "partition_mounting",
                "fstab_stabilization",
                "initramfs_rebuild",
                "grub_regeneration",
                "network_configuration",
                "vmware_tools_removal",
                "virtio_driver_injection",
            ],
        }
        return ops.get(self.detected_level, [])

    def _get_limitations(self) -> list[str]:
        """List limitations at detected level"""
        limitations = {
            CapabilityLevel.USERSPACE_ONLY: [
                "Cannot inspect disk partition table",
                "Cannot detect guest filesystems",
                "Cannot mount guest filesystems",
                "Cannot apply offline fixes",
                "Guest may not boot without manual intervention",
                "Virtio drivers not injected",
            ],
            CapabilityLevel.NBD_INSPECTION: [
                "Cannot mount partitions (partition devices unavailable)",
                "Cannot apply offline fixes to guest filesystems",
                "Guest may not boot without manual intervention",
                "Virtio drivers not injected",
            ],
            CapabilityLevel.FULL_OFFLINE_FIXES: [],
        }
        return limitations.get(self.detected_level, [])

    def _get_recommendations(self) -> list[str]:
        """Get recommendations based on detected level"""
        recommendations = {
            CapabilityLevel.USERSPACE_ONLY: [
                "Deploy to production cluster with NBD support for full offline fixes",
                "Test VM boot in development environment before production use",
                "Consider manual virtio driver installation in guest",
                "Use VM+k3s lab environment for realistic testing",
            ],
            CapabilityLevel.NBD_INSPECTION: [
                "Deploy to production cluster for full offline fix capabilities",
                "Current environment supports inspection but not guest modifications",
                "Test VM boot before production deployment",
            ],
            CapabilityLevel.FULL_OFFLINE_FIXES: [],
        }
        return recommendations.get(self.detected_level, [])


def main():
    """Test capability detection"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    detector = CapabilityDetector()
    level = detector.detect()
    report = detector.get_capability_report()

    print("\n" + "=" * 60)
    print("CAPABILITY DETECTION REPORT")
    print("=" * 60)
    print(f"\n📊 Detected Level: {report['level_name']}")
    print(f"   Description: {report['level_description']}")
    print(f"   Reason: {report['details'].get('reason', 'N/A')}")

    print(f"\n✅ Available Operations ({len(report['operations'])}):")
    for op in report["operations"]:
        print(f"   - {op}")

    if report["limitations"]:
        print(f"\n⚠️  Limitations ({len(report['limitations'])}):")
        for limit in report["limitations"]:
            print(f"   - {limit}")

    if report["recommendations"]:
        print(f"\n💡 Recommendations ({len(report['recommendations'])}):")
        for rec in report["recommendations"]:
            print(f"   - {rec}")

    print("\n" + "=" * 60)
    print()

    return level


if __name__ == "__main__":
    main()
