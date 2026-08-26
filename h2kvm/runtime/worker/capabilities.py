# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/worker/capabilities.py
"""
Runtime Capability Detection.

Detects execution environment (container vs host) and available capabilities
for privileged disk operations.
"""

from __future__ import annotations

import contextlib
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ExecutionMode:
    """Execution mode constants."""

    HOST = "host"
    SAFE_CONTAINER = "safe_container"
    PRIVILEGED_CONTAINER = "privileged_container"


class CapabilityLevel(Enum):
    """
    Three-tier capability levels for migration operations.

    Provides graceful degradation based on environment capabilities:
    - Level 1: Basic conversion without NBD (kind, restrictive containers)
    - Level 2: NBD inspection without partition mounting (partial NBD)
    - Level 3: Full offline fixes with partition mounting (production)
    """

    USERSPACE_ONLY = 1  # Basic VMDK→QCOW2 conversion
    NBD_INSPECTION = 2  # NBD device + partition reading
    FULL_OFFLINE_FIXES = 3  # Complete migration with guest fixes

    def __str__(self):
        return self.name.lower().replace("_", "-")

    def can_mount_partitions(self) -> bool:
        """Check if this level supports mounting partitions."""
        return self == CapabilityLevel.FULL_OFFLINE_FIXES

    def can_inspect_disk(self) -> bool:
        """Check if this level supports disk inspection via NBD."""
        return self in (CapabilityLevel.NBD_INSPECTION, CapabilityLevel.FULL_OFFLINE_FIXES)

    def can_convert(self) -> bool:
        """Check if this level supports VMDK conversion."""
        return True  # All levels support conversion


class CapabilityDetector:
    """
    Detects runtime capabilities for disk operations.

    Checks:
    - Container vs host execution
    - NBD device availability
    - LVM tools and permissions
    - Mount capabilities
    - SELinux tools
    - Available system resources
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._mode: str | None = None
        self._capabilities: dict[str, bool] | None = None

    def detect_execution_mode(self) -> str:
        """
        Detect execution mode.

        Returns:
            One of: "host", "safe_container", "privileged_container"
        """
        if self._mode:
            return self._mode

        # Check if running in container
        if not self._is_in_container():
            self._mode = ExecutionMode.HOST
            self.logger.info(f"Detected execution mode: {self._mode}")
            return self._mode

        # In container - check if privileged
        if self._has_nbd_access():
            self._mode = ExecutionMode.PRIVILEGED_CONTAINER
        else:
            self._mode = ExecutionMode.SAFE_CONTAINER

        self.logger.info(f"Detected execution mode: {self._mode}")
        return self._mode

    def _is_in_container(self) -> bool:
        """Check if running inside a container."""

        # Method 1: Check /.dockerenv
        if Path("/.dockerenv").exists():
            self.logger.debug("Container detected: /.dockerenv exists")
            return True

        # Method 2: Check /proc/1/cgroup for container runtime
        try:
            with open("/proc/1/cgroup") as f:
                content = f.read()
                if "docker" in content or "lxc" in content or "kubepods" in content:
                    self.logger.debug("Container detected: cgroup contains container runtime")
                    return True
        except Exception as e:
            self.logger.debug(f"Could not check /proc/1/cgroup: {e}")

        # Method 3: Check if running as PID 1 with minimal process tree
        # (containers typically have very few processes)
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5, check=False)
            if result.returncode == 0:
                process_count = len(result.stdout.strip().split("\n"))
                # Host typically has 100+ processes, containers have <20
                if process_count < 30:
                    self.logger.debug(f"Container likely detected: only {process_count} processes")
                    return True
        except Exception as e:
            self.logger.debug(f"Could not check process count: {e}")

        self.logger.debug("Not detected as container")
        return False

    def _has_nbd_access(self) -> bool:
        """
        Check if NBD devices are accessible with comprehensive validation.

        This implements battle-tested checks to avoid false positives in
        containerized environments (k3d, kind, Docker Desktop).

        Returns:
            bool: True if NBD is genuinely accessible, False otherwise
        """

        # Check 1: qemu-nbd binary must exist
        import shutil

        if not shutil.which("qemu-nbd"):
            self.logger.debug("NBD not available: qemu-nbd binary not found")
            return False

        # Check 2: /dev/nbd devices must exist
        nbd_devices = list(Path("/dev").glob("nbd*"))
        if not nbd_devices:
            self.logger.debug("NBD not available: no /dev/nbd* devices present")
            return False

        # Check 3: Kernel NBD module must be loaded (host-level check)
        if not Path("/sys/module/nbd").exists():
            self.logger.debug("NBD not available: kernel module not loaded")
            return False

        # Check 4: Test actual device access (CAP_SYS_ADMIN check)
        test_dev = Path("/dev/nbd0")
        if not test_dev.exists():
            self.logger.debug("NBD not available: /dev/nbd0 doesn't exist")
            return False

        try:
            # Try to open device - this requires CAP_SYS_ADMIN
            with open(test_dev, "rb"):
                # Just opening is enough to verify permission
                pass
            self.logger.debug("NBD device accessible: successfully opened /dev/nbd0")
        except PermissionError:
            self.logger.debug("NBD not accessible: permission denied (CAP_SYS_ADMIN missing)")
            return False
        except Exception as e:
            self.logger.debug(f"NBD access check failed: {e}")
            return False

        # Check 5: Container/nested runtime heuristics
        # If in container, must have host kernel modules mounted
        if Path("/.dockerenv").exists():
            # Container detected - check for host kernel modules
            if not Path("/lib/modules").exists():
                self.logger.debug("NBD not reliable: container without host kernel modules")
                return False
            self.logger.debug("Container detected but has host kernel modules - NBD may work")

        # Check 6: Verify we can read device metadata from sysfs
        try:
            size_file = Path("/sys/block/nbd0/size")
            if size_file.exists():
                size = size_file.read_text().strip()
                self.logger.debug(f"NBD fully accessible: /dev/nbd0 (size={size})")
            else:
                self.logger.debug("NBD accessible but no sysfs metadata")
        except PermissionError:
            self.logger.debug("NBD accessible but sysfs permission denied")
        except Exception as e:
            self.logger.debug(f"NBD accessible but sysfs check failed: {e}")

        # All checks passed
        self.logger.info("NBD access verified: all capability checks passed")
        return True

    def _check_lvm_available(self) -> bool:
        """Check if LVM tools are available and functional."""

        # Check if LVM commands exist
        for cmd in ["pvs", "vgs", "lvs", "vgchange"]:
            try:
                result = subprocess.run(["which", cmd], capture_output=True, timeout=5, check=False)
                if result.returncode != 0:
                    self.logger.debug(f"LVM tool not found: {cmd}")
                    return False
            except Exception as e:
                self.logger.debug(f"LVM tool check failed for {cmd}: {e}")
                return False

        # Check if we can list volume groups (requires device mapper access)
        try:
            result = subprocess.run(
                ["vgs", "--noheadings"], capture_output=True, text=True, timeout=10, check=False
            )
            self.logger.debug(f"LVM functional: vgs returned {result.returncode}")
            return result.returncode == 0
        except Exception as e:
            self.logger.debug(f"LVM functionality check failed: {e}")
            return False

    def _check_mount_available(self) -> bool:
        """Check if mount/umount operations are permitted."""

        # Check if running as root or has CAP_SYS_ADMIN
        if os.geteuid() != 0:
            self.logger.debug("Mount not available: not running as root")
            return False

        # Check if mount command exists
        try:
            result = subprocess.run(["which", "mount"], capture_output=True, timeout=5, check=False)
            if result.returncode != 0:
                self.logger.debug("Mount not available: mount command not found")
                return False
        except Exception as e:
            self.logger.debug(f"Mount check failed: {e}")
            return False

        # Perform actual test mount to verify capability works
        return self._test_mount_capability()

    def _test_mount_capability(self) -> bool:
        """
        Test actual mount capability with a tmpfs mount.

        Returns:
            True if mount/umount operations work, False otherwise
        """
        import shutil
        import tempfile

        test_dir = None
        try:
            # Create temporary directory for test mount
            test_dir = tempfile.mkdtemp(prefix="h2kvm-mount-test-")

            # Try to mount tmpfs
            mount_result = subprocess.run(
                ["mount", "-t", "tmpfs", "-o", "size=1M", "tmpfs", test_dir],
                capture_output=True,
                timeout=10,
                text=True,
                check=False,
            )

            if mount_result.returncode != 0:
                self.logger.debug(f"Mount test failed: {mount_result.stderr.strip()}")
                return False

            # Verify mount succeeded by checking mountpoint
            check_result = subprocess.run(["mountpoint", "-q", test_dir], timeout=5, check=False)

            if check_result.returncode != 0:
                self.logger.debug("Mount test failed: mountpoint verification failed")
                # Try to unmount anyway in case mount partially succeeded
                subprocess.run(["umount", test_dir], timeout=5, capture_output=True, check=False)
                return False

            # Unmount the test filesystem
            umount_result = subprocess.run(
                ["umount", test_dir], capture_output=True, timeout=10, text=True, check=False
            )

            if umount_result.returncode != 0:
                self.logger.warning(f"Mount test: umount failed: {umount_result.stderr.strip()}")
                # Try force unmount
                subprocess.run(["umount", "-f", test_dir], timeout=5, capture_output=True, check=False)
                return False

            self.logger.debug("Mount capability verified with tmpfs test")
            return True

        except subprocess.TimeoutExpired:
            self.logger.debug("Mount test timed out")
            return False
        except Exception as e:
            self.logger.debug(f"Mount capability test failed: {e}")
            return False
        finally:
            # Cleanup: ensure test directory is removed
            if test_dir and os.path.exists(test_dir):
                try:
                    # Final attempt to unmount if it's still mounted
                    subprocess.run(["umount", "-f", test_dir], capture_output=True, timeout=5, check=False)
                except Exception:
                    pass
                with contextlib.suppress(Exception):
                    shutil.rmtree(test_dir, ignore_errors=True)

    def _check_selinux_tools(self) -> bool:
        """Check if SELinux tools are available."""

        for cmd in ["restorecon", "semanage", "chcon"]:
            try:
                result = subprocess.run(["which", cmd], capture_output=True, timeout=5, check=False)
                if result.returncode != 0:
                    self.logger.debug(f"SELinux tool not found: {cmd}")
                    return False
            except Exception:
                return False

        return True

    def _check_qemu_img(self) -> bool:
        """Check if qemu-img is available."""

        try:
            result = subprocess.run(["qemu-img", "--version"], capture_output=True, timeout=5, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def detect_capabilities(self) -> dict[str, bool]:
        """
        Detect all available capabilities.

        Returns:
            Dictionary of capability name -> availability
        """
        if self._capabilities:
            return self._capabilities

        self._capabilities = {
            "nbd": self._has_nbd_access(),
            "lvm": self._check_lvm_available(),
            "mount": self._check_mount_available(),
            "selinux": self._check_selinux_tools(),
            "qemu_img": self._check_qemu_img(),
        }

        self.logger.info(f"Detected capabilities: {self._capabilities}")
        return self._capabilities

    def get_system_info(self) -> dict[str, any]:
        """Get system information for worker registration."""

        import psutil

        info = {
            "hostname": platform.node(),
            "os": platform.system(),
            "os_release": platform.release(),
            "kernel_version": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        }

        # Get memory info
        try:
            mem = psutil.virtual_memory()
            info["memory_gb"] = int(mem.total / (1024**3))
            info["memory_available_gb"] = int(mem.available / (1024**3))
        except Exception as e:
            self.logger.debug(f"Could not get memory info: {e}")
            info["memory_gb"] = 0

        # Get disk info
        try:
            disk = psutil.disk_usage("/")
            info["disk_space_gb"] = int(disk.total / (1024**3))
            info["disk_available_gb"] = int(disk.free / (1024**3))
        except Exception as e:
            self.logger.debug(f"Could not get disk info: {e}")
            info["disk_space_gb"] = 0

        return info

    def can_execute_job(self, job_requirements: dict[str, bool]) -> tuple[bool, str | None]:
        """
        Check if current environment can execute job with given requirements.

        Args:
            job_requirements: Dictionary of required capabilities

        Returns:
            Tuple of (can_execute, reason_if_cannot)
        """
        capabilities = self.detect_capabilities()

        for capability, required in job_requirements.items():
            if required and not capabilities.get(capability, False):
                return False, f"Missing required capability: {capability}"

        return True, None

    def suggest_execution_mode(self, job_requirements: dict[str, bool]) -> str:
        """
        Suggest execution mode for job requirements.

        Args:
            job_requirements: Dictionary of required capabilities

        Returns:
            Suggested mode: "host", "privileged_container", or "safe_container"
        """
        needs_privileged = any(
            [
                job_requirements.get("nbd", False),
                job_requirements.get("lvm", False),
                job_requirements.get("mount", False),
            ]
        )

        if needs_privileged:
            current_mode = self.detect_execution_mode()
            if current_mode in (ExecutionMode.SAFE_CONTAINER, ExecutionMode.PRIVILEGED_CONTAINER):
                return ExecutionMode.PRIVILEGED_CONTAINER
            return ExecutionMode.HOST
        return ExecutionMode.SAFE_CONTAINER

    def detect_capability_level(self) -> CapabilityLevel:
        """
        Detect three-tier capability level for migration operations.

        Progressive checks:
        1. NBD module availability → USERSPACE_ONLY if unavailable
        2. NBD device creation → USERSPACE_ONLY if fails
        3. NBD partition devices → NBD_INSPECTION if missing, else FULL_OFFLINE_FIXES

        Returns:
            CapabilityLevel: Detected capability level
        """
        self.logger.info("🔍 Detecting migration capability level...")

        # Check 1: NBD module available?
        if not self._check_nbd_module():
            self.logger.info("❌ NBD module unavailable")
            return CapabilityLevel.USERSPACE_ONLY

        # Check 2: NBD device accessible?
        if not self._has_nbd_access():
            self.logger.warning("⚠️  NBD module loaded but device inaccessible")
            return CapabilityLevel.USERSPACE_ONLY

        # Check 3: NBD partition devices supported?
        if not self._check_nbd_partition_devices():
            self.logger.info("⚠️  NBD device available but partition devices missing")
            return CapabilityLevel.NBD_INSPECTION

        # Full capabilities available
        self.logger.info("✅ Full offline fix capabilities available")
        return CapabilityLevel.FULL_OFFLINE_FIXES

    def _check_nbd_module(self) -> bool:
        """Check if NBD kernel module is available and loadable."""
        try:
            # First check if module is already loaded
            result = subprocess.run(["lsmod"], capture_output=True, timeout=5, text=True, check=False)

            if "nbd" in result.stdout:
                self.logger.debug("NBD module already loaded")
                return True

            # Try to load NBD module with partition support
            result = subprocess.run(
                ["modprobe", "nbd", "max_part=16"], capture_output=True, timeout=5, check=False
            )

            if result.returncode == 0:
                self.logger.info("✅ NBD module loaded successfully")
                return True
            self.logger.debug(f"modprobe failed: {result.stderr.decode()}")
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("NBD module load timed out")
            return False
        except FileNotFoundError:
            self.logger.debug("modprobe command not found")
            return False
        except PermissionError:
            self.logger.debug("Permission denied loading NBD module")
            return False
        except Exception as e:
            self.logger.debug(f"NBD module check failed: {e}")
            return False

    def _find_free_nbd_device(self) -> str | None:
        """Find a free NBD device by checking /sys/block/nbdN/size."""
        for i in range(16):
            dev = f"/dev/nbd{i}"
            if not Path(dev).exists():
                continue
            size_file = Path(f"/sys/block/nbd{i}/size")
            try:
                if size_file.exists():
                    size = int(size_file.read_text().strip())
                    if size == 0:
                        return dev
                else:
                    return dev
            except (ValueError, OSError):
                continue
        return None

    def _check_nbd_partition_devices(self) -> bool:
        """
        Check if NBD partition devices are supported.

        This is the critical check that differentiates Level 2 from Level 3.
        Creates a small test image with partitions and checks if /dev/nbdNp1 appears.

        Returns:
            bool: True if partition devices are created, False otherwise
        """
        test_image = None
        nbd_device = self._find_free_nbd_device()

        if not nbd_device:
            self.logger.debug("No free NBD device available for partition test")
            return False

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
                self.logger.debug(f"Failed to attach test image: {result.stderr.decode()}")
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
                self.logger.info(f"✅ NBD partition devices supported ({nbd_device}p1 found)")
                return True
            self.logger.info(f"❌ NBD partition devices NOT created ({nbd_device}p1 missing)")
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("NBD partition check timed out")
            return False
        except FileNotFoundError:
            self.logger.debug("qemu-nbd command not found")
            return False
        except Exception as e:
            self.logger.debug(f"NBD partition check failed: {e}")
            return False
        finally:
            # Ensure NBD is disconnected
            try:
                subprocess.run(
                    ["qemu-nbd", "--disconnect", nbd_device], capture_output=True, timeout=5, check=False
                )
            except Exception:  # Suppress all cleanup errors
                pass

            # Clean up test image
            if test_image and os.path.exists(test_image):
                try:
                    os.unlink(test_image)
                except Exception:  # Suppress file deletion errors
                    pass

    def _create_test_image(self) -> str | None:
        """
        Create a small test QCOW2 image with a partition table.

        Returns:
            str: Path to test image, or None on failure
        """
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

        except Exception as e:
            self.logger.debug(f"Test image creation failed: {e}")
            if path and os.path.exists(path):
                os.unlink(path)
            return None

    def get_capability_level_report(self, level: CapabilityLevel) -> dict[str, any]:
        """
        Get detailed capability report for a given level.

        Args:
            level: Capability level to report on

        Returns:
            dict: Capability report with operations, limitations, and recommendations
        """
        return {
            "level": level.value,
            "level_name": level.name,
            "level_description": str(level),
            "operations": self._get_available_operations(level),
            "limitations": self._get_limitations(level),
            "recommendations": self._get_recommendations(level),
        }

    def _get_available_operations(self, level: CapabilityLevel) -> list[str]:
        """List operations available at given level."""
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
        return ops.get(level, [])

    def _get_limitations(self, level: CapabilityLevel) -> list[str]:
        """List limitations at given level."""
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
        return limitations.get(level, [])

    def _get_recommendations(self, level: CapabilityLevel) -> list[str]:
        """Get recommendations based on detected level."""
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
        return recommendations.get(level, [])

    def get_detection_diagnostics(self) -> dict[str, any]:
        """
        Get detailed diagnostics about capability detection.

        Returns a comprehensive report of all detection checks for transparency
        and debugging. Useful for troubleshooting capability detection issues.

        Returns:
            dict: Detailed diagnostic information including:
                - detected_level: The final detected capability level
                - checks: Results of each detection check
                - environment: Environment information
                - skipped_steps: Operations that will be skipped
                - recommended_actions: Recommended next steps
        """
        level = self.detect_capability_level()
        report = self.get_capability_level_report(level)

        # Run all detection checks
        nbd_module = self._check_nbd_module()
        nbd_access = self._has_nbd_access()
        nbd_partitions = self._check_nbd_partition_devices() if nbd_access else False

        # Determine skip reasons
        skipped_steps = []
        if level < CapabilityLevel.NBD_INSPECTION:
            skipped_steps.append(
                {
                    "step": "nbd_inspection",
                    "reason": "NBD kernel module not loaded"
                    if not nbd_module
                    else "NBD device inaccessible",
                }
            )
        if level < CapabilityLevel.FULL_OFFLINE_FIXES:
            skipped_steps.append(
                {
                    "step": "offline_fixes",
                    "reason": "NBD partition devices not created (container limitation)"
                    if nbd_access
                    else "NBD unavailable",
                }
            )

        # Recommended actions based on level
        recommended_actions = []
        if level == CapabilityLevel.USERSPACE_ONLY:
            recommended_actions = ["run-online-fix", "boot-test", "deploy-to-production-cluster"]
        elif level == CapabilityLevel.NBD_INSPECTION:
            recommended_actions = ["run-online-fix", "boot-test", "deploy-to-vm-worker-for-offline-fixes"]
        else:
            recommended_actions = ["boot-test", "validate-guest-configuration"]

        return {
            "detected_level": level.name,
            "level_value": level.value,
            "checks": {
                "nbd_module_loaded": nbd_module,
                "nbd_device_accessible": nbd_access,
                "nbd_partition_devices": nbd_partitions,
                "qemu_nbd_available": shutil.which("qemu-nbd") is not None,
                "in_container": self._is_in_container(),
                "has_sys_admin": os.geteuid() == 0,
                "host_modules_mounted": Path("/lib/modules").exists(),
            },
            "capabilities": {
                "nbd": nbd_access,
                "offline_mount": level >= CapabilityLevel.FULL_OFFLINE_FIXES,
                "partition_inspection": level >= CapabilityLevel.NBD_INSPECTION,
            },
            "operations": report["operations"],
            "limitations": report["limitations"],
            "skipped_steps": skipped_steps,
            "recommended_actions": recommended_actions,
            "environment": {
                "execution_mode": self.detect_execution_mode().name
                if hasattr(self, "detect_execution_mode")
                else "unknown",
                "container_detected": Path("/.dockerenv").exists(),
                "has_kernel_modules": Path("/lib/modules").exists(),
                "has_dev_passthrough": Path("/dev/nbd0").exists() if nbd_module else False,
            },
        }


# Global detector instance
_detector: CapabilityDetector | None = None


def get_detector() -> CapabilityDetector:
    """Get global capability detector instance."""
    global _detector
    if _detector is None:
        _detector = CapabilityDetector()
    return _detector
