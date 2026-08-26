#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
NBD Preparation Daemon for OfflineFixJob.

Runs as DaemonSet on NBD-capable nodes. Watches node annotations and:
1. Attaches disk images to NBD devices
2. Mounts guest filesystems
3. Updates node annotations when ready
4. Cleans up on job completion

Architecture:
  Controller annotates node → This daemon sees annotation →
  Attach NBD + mount FS → Update node annotation →
  Controller creates VM → VM runs fixers →
  Controller signals cleanup → Daemon unmounts + disconnects
"""

import fcntl
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from kubernetes import client, config, watch

# Configuration constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB max output

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import constants from centralized module
try:
    from ...core.constants import (
        ANNOTATION_CLEANUP,
        ANNOTATION_MOUNT_PATH,
        ANNOTATION_NBD_DEVICE,
        ANNOTATION_NBD_READY,
        ANNOTATION_OFFLINE_FIX_JOB,
        IMPORTS_PATH,
        MOUNT_BASE_PATH,
        NBD_BASE_PATH,
    )
except ImportError:
    # Fallback for standalone execution
    ANNOTATION_OFFLINE_FIX_JOB = "offlinefix.h2kvm.io/job"
    ANNOTATION_NBD_READY = "offlinefix.h2kvm.io/nbd-ready"
    ANNOTATION_NBD_DEVICE = "offlinefix.h2kvm.io/nbd-device"
    ANNOTATION_MOUNT_PATH = "offlinefix.h2kvm.io/mount-path"
    ANNOTATION_CLEANUP = "offlinefix.h2kvm.io/cleanup"
    NBD_BASE_PATH = "/dev/nbd"
    MOUNT_BASE_PATH = "/var/lib/kubevirt-offline"
    IMPORTS_PATH = "/var/lib/imports"


def retry_on_failure(func, max_retries=MAX_RETRIES, delay=RETRY_DELAY, logger=logger):
    """
    Retry wrapper for operations that may fail transiently.

    Args:
        func: Callable to retry
        max_retries: Maximum number of retry attempts
        delay: Delay in seconds between retries
        logger: Logger instance for logging retry attempts

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries fail
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.exception(f"All {max_retries} attempts failed: {e}")

    raise last_exception


class NBDPrepDaemon:
    """NBD preparation daemon."""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.api = None
        self.active_jobs = {}  # job_ref -> {device, mount_path}
        self.activated_vgs = []  # Track VGs we activated for safe cleanup
        self.nbd_lock_fds = {}  # File descriptors for NBD locks, keyed by device path

    def run(self):
        """Main daemon loop."""
        logger.info(f"NBD Prep Daemon starting on node: {self.node_name}")

        # Load Kubernetes config
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded kubeconfig from ~/.kube/config")

        self.api = client.CoreV1Api()

        # Load NBD module once
        self.load_nbd_module()

        # Watch node annotations
        self.watch_node()

    def load_nbd_module(self):
        """Load NBD kernel module."""
        logger.info("Loading NBD kernel module")
        try:
            subprocess.run(["modprobe", "nbd", "max_part=16"], check=True, capture_output=True)
            logger.info("NBD module loaded successfully")
        except subprocess.CalledProcessError as e:
            logger.exception(f"Failed to load NBD module: {e}")
            sys.exit(1)

    def watch_node(self):
        """Watch this node for annotation changes."""
        w = watch.Watch()

        while True:
            try:
                for event in w.stream(
                    self.api.list_node, field_selector=f"metadata.name={self.node_name}", timeout_seconds=30
                ):
                    if event["type"] in ["ADDED", "MODIFIED"]:
                        node = event["object"]
                        self.handle_node_update(node)

            except Exception as e:
                logger.exception(f"Watch error: {e}")
                time.sleep(5)

    def handle_node_update(self, node):
        """Handle node update event."""
        annotations = node.metadata.annotations or {}

        # Check for job annotation
        job_ref = annotations.get(ANNOTATION_OFFLINE_FIX_JOB)
        cleanup = annotations.get(ANNOTATION_CLEANUP) == "true"

        if cleanup and job_ref:
            # Cleanup requested
            self.cleanup_job(job_ref)

        elif job_ref:
            # Check if already processed
            nbd_ready = annotations.get(ANNOTATION_NBD_READY) == "true"

            if not nbd_ready and job_ref not in self.active_jobs:
                # New job, process it
                self.setup_nbd(job_ref)

    def setup_nbd(self, job_ref: str):
        """
        Set up NBD for a job.

        Args:
            job_ref: Namespace/name of the OfflineFixJob
        """
        logger.info(f"Setting up NBD for job: {job_ref}")

        nbd_device = None  # Track for cleanup on error
        mount_path = None

        try:
            # Parse job ref
            _namespace, job_name = job_ref.split("/")

            # Sanitize job_name to prevent path traversal
            if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", job_name):
                raise ValueError(
                    f"Invalid job name '{job_name}': must contain only alphanumeric characters, hyphens, and underscores"
                )

            # Get job to read disk spec
            # For now, use hardcoded path (production would query the CRD)
            disk_path = Path(IMPORTS_PATH) / f"{job_name}.qcow2"

            if not disk_path.exists():
                # Try common patterns
                for ext in [".qcow2", ".vmdk", ".img"]:
                    candidate = Path(IMPORTS_PATH) / f"{job_name}{ext}"
                    if candidate.exists():
                        disk_path = candidate
                        break

            if not disk_path.exists():
                raise FileNotFoundError(f"Disk image not found for job {job_name}")

            # Find free NBD device
            nbd_device = self.find_free_nbd_device()
            if not nbd_device:
                raise RuntimeError(
                    "No free NBD device available. All /dev/nbd* devices are in use. "
                    "Disconnect unused devices with 'qemu-nbd -d /dev/nbdN' or increase max_part in nbd module."
                )

            # Attach disk to NBD
            self.attach_disk_to_nbd(str(disk_path), nbd_device)

            # Wait for partitions
            time.sleep(2)
            self.probe_partitions(nbd_device)

            # Activate LVM if present (pass NBD device for filtering)
            self.activate_lvm(nbd_device)

            # Mount root partition
            mount_path = self.mount_root_partition(nbd_device, job_name)

            # Mount boot partition if separate
            self.mount_boot_partition(nbd_device, mount_path)

            # Update node annotations
            self.update_node_annotations(job_ref, nbd_device, mount_path)

            # Track active job
            self.active_jobs[job_ref] = {"device": nbd_device, "mount_path": mount_path}

            logger.info(f"NBD setup complete: device={nbd_device}, mount={mount_path}")

        except Exception as e:
            logger.exception(f"NBD setup failed for {job_ref}: {e}")
            logger.debug("NBD setup error details", exc_info=True)

            # Cleanup: Disconnect NBD if it was attached
            if nbd_device:
                try:
                    logger.info(f"Cleaning up failed setup: disconnecting {nbd_device}")
                    self.disconnect_nbd(nbd_device)
                except Exception as cleanup_error:
                    logger.exception(f"Cleanup failed: {cleanup_error}")

            # Cleanup: Unmount if mounted
            if mount_path and self.is_mount_point(mount_path):
                try:
                    self.unmount(mount_path)
                except (OSError, RuntimeError) as unmount_error:
                    logger.warning(f"Failed to unmount {mount_path}: {unmount_error}")

            # Update node annotation with error
            try:
                error_msg = str(e)[:200]  # Truncate if too long
                body = {
                    "metadata": {
                        "annotations": {
                            ANNOTATION_NBD_READY: "false",
                            "offlinefix.h2kvm.io/nbd-error": error_msg,
                        }
                    }
                }
                self.api.patch_node(self.node_name, body)
                logger.info(f"Updated node annotations with error for {job_ref}")
            except Exception as patch_error:
                logger.exception(f"Failed to update node with error: {patch_error}")

            # Don't crash the daemon - just log and continue watching
            # The controller will see the error annotation and can retry or fail the job

    def cleanup_job(self, job_ref: str):
        """
        Cleanup NBD for a job.

        Args:
            job_ref: Namespace/name of the OfflineFixJob
        """
        logger.info(f"Cleaning up NBD for job: {job_ref}")

        if job_ref not in self.active_jobs:
            logger.warning(f"Job {job_ref} not in active jobs")
            return

        job_info = self.active_jobs[job_ref]
        nbd_device = job_info["device"]
        mount_path = job_info["mount_path"]

        try:
            # Unmount boot
            boot_mount = Path(mount_path) / "boot"
            if self.is_mount_point(str(boot_mount)):
                self.unmount(str(boot_mount))

            # Unmount root
            if self.is_mount_point(mount_path):
                self.unmount(mount_path)

            # Deactivate LVM
            self.deactivate_lvm()

            # Disconnect NBD
            self.disconnect_nbd(nbd_device)

            # Remove mount directory
            if Path(mount_path).exists():
                Path(mount_path).rmdir()

            # Remove from active jobs
            del self.active_jobs[job_ref]

            # Clear node annotations
            self.clear_node_annotations(job_ref)

            logger.info(f"Cleanup complete for job: {job_ref}")

        except Exception as e:
            logger.exception(f"Cleanup failed for {job_ref}: {e}")

    def find_free_nbd_device(self) -> Optional[str]:
        """Find an unused NBD device."""
        for i in range(16):
            device = f"{NBD_BASE_PATH}{i}"

            # Method 1: Check if device exists
            if not Path(device).exists():
                logger.debug(f"{device} does not exist, skipping")
                continue

            # Method 2: Check /sys/block/nbdX/pid for active connection (if available)
            # Note: This may not exist on all kernel versions
            pid_file = Path(f"/sys/block/nbd{i}/pid")
            if pid_file.exists():
                try:
                    pid_str = pid_file.read_text().strip()
                    if pid_str:  # File has content
                        pid = int(pid_str)
                        if pid > 0:
                            logger.debug(f"{device} is in use (pid={pid})")
                            continue
                except (ValueError, OSError) as e:
                    logger.debug(f"{device} pid check failed: {e}")

            # Method 3: Check with lsblk (most reliable)
            # Use -b for bytes (more reliable than human-readable) and -o SIZE to get just size
            result = subprocess.run(
                ["lsblk", "-n", "-b", "-o", "SIZE", device],
                capture_output=True,
                text=True,
                check=False,
            )

            # If lsblk shows the device with size > 0, it's connected
            if result.returncode == 0 and result.stdout.strip():
                try:
                    size_bytes = int(result.stdout.strip())
                    if size_bytes == 0:
                        # Size is 0 bytes - device is free
                        logger.debug(f"{device} is free (size=0)")
                        return device
                    # Device has a size - it's connected
                    logger.debug(f"{device} is in use (size={size_bytes} bytes)")
                    continue
                except ValueError:
                    # Can't parse size - assume free
                    logger.debug(f"{device} has unparseable size, assuming free")
                    return device
            else:
                # lsblk failed - assume free
                logger.debug(f"{device} lsblk failed, assuming free")
                return device

        logger.error("No free NBD devices found")
        return None

    def acquire_nbd_lock(self, nbd_device: str):
        """
        Acquire exclusive lock on NBD device.

        Prevents concurrent NBD operations that could cause conflicts.
        """
        lock_file = f"/var/run/nbd_{nbd_device.replace('/', '_')}.lock"
        logger.debug(f"Acquiring NBD lock: {lock_file}")

        # Intentionally kept open past this function: the fd is stored in
        # self.nbd_lock_fds and closed later by release_nbd_lock().
        fd = open(lock_file, "w")  # noqa: SIM115
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.nbd_lock_fds[nbd_device] = fd
            logger.debug(f"NBD lock acquired: {lock_file}")
        except OSError as e:
            fd.close()
            raise RuntimeError(
                f"Failed to acquire NBD lock for {nbd_device} - another operation in progress"
            ) from e

    def release_nbd_lock(self, nbd_device: str):
        """Release NBD lock for a specific device."""
        fd = self.nbd_lock_fds.pop(nbd_device, None)
        if fd:
            logger.debug(f"Releasing NBD lock for {nbd_device}")
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
            except Exception as e:
                logger.warning(f"Failed to release NBD lock for {nbd_device}: {e}")

    def attach_disk_to_nbd(self, disk_path: str, nbd_device: str):
        """
        Attach disk image to NBD device with retry logic.

        Uses retry wrapper to handle transient failures.
        """
        logger.info(f"Attaching {disk_path} to {nbd_device}")

        # Acquire lock to prevent concurrent NBD operations
        self.acquire_nbd_lock(nbd_device)

        try:

            def _attach():
                # First, ensure device is disconnected (in case of previous failed attempt)
                logger.debug(f"Ensuring {nbd_device} is disconnected before attach")
                subprocess.run(
                    ["qemu-nbd", "--disconnect", nbd_device],
                    capture_output=True,
                    # Ok if disconnect fails (device not connected)
                    check=False,
                )

                # Small delay to let kernel release the device
                time.sleep(0.5)

                # Now attach the disk
                result = subprocess.run(
                    ["qemu-nbd", f"--connect={nbd_device}", disk_path],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    # Log stderr for debugging
                    stderr = result.stderr.strip()
                    # Truncate output if too large
                    if len(stderr) > MAX_OUTPUT_SIZE:
                        stderr = stderr[:MAX_OUTPUT_SIZE] + "... [truncated]"

                    logger.error(f"qemu-nbd connect failed (exit {result.returncode}): {stderr}")
                    raise subprocess.CalledProcessError(
                        result.returncode, result.args, output=result.stdout, stderr=result.stderr
                    )

                # Wait for device to be ready
                self._wait_for_nbd_device(nbd_device)

            # Retry attach operation
            retry_on_failure(_attach, max_retries=MAX_RETRIES, delay=RETRY_DELAY, logger=logger)
            logger.info(f"Successfully attached {disk_path} to {nbd_device}")

        finally:
            # Always release lock
            self.release_nbd_lock(nbd_device)

    def _wait_for_nbd_device(self, nbd_device: str):
        """Wait for NBD device to become available."""
        for i in range(MAX_RETRIES):
            if os.path.exists(nbd_device):
                logger.debug(f"NBD device {nbd_device} is ready")
                return
            logger.warning(f"Waiting for {nbd_device}... (attempt {i + 1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)

        raise RuntimeError(
            f"NBD device {nbd_device} did not become available after {MAX_RETRIES} attempts. "
            f"The disk image may be locked or the nbd kernel module may need reloading."
        )

    def probe_partitions(self, nbd_device: str):
        """Force kernel to detect partitions."""
        subprocess.run(["partprobe", nbd_device], capture_output=True, check=False)

    def activate_lvm(self, nbd_device: Optional[str] = None):
        """
        Activate LVM volume groups if present.

        Uses device filtering to only activate VGs on the NBD device,
        preventing accidental activation of host system VGs.

        Args:
            nbd_device: NBD device path (e.g., "/dev/nbd0") to filter VGs
        """
        logger.info(f"Scanning for LVM volumes (NBD device: {nbd_device})")

        # Get NBD partitions for explicit device specification
        nbd_partitions = []
        if nbd_device:
            nbd_dev_path = Path(nbd_device)
            nbd_partitions = [str(p) for p in nbd_dev_path.parent.glob(f"{nbd_dev_path.name}p*")]
            logger.info(f"NBD partitions for LVM scan: {nbd_partitions}")

            if not nbd_partitions:
                logger.debug(f"No partitions found on {nbd_device}")
                return

            # Scan each NBD partition with devicesfile disabled
            for part in nbd_partitions:
                result = subprocess.run(
                    ["pvscan", "--devicesfile", "", "--cache", part],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    logger.debug(f"  Scanned PV: {part}")
                else:
                    logger.debug(f"  No PV on {part}")

            # General scan with devicesfile disabled
            result = subprocess.run(
                ["vgscan", "--devicesfile", "", "--cache"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.debug(f"vgscan failed: {result.stderr}")
                return
        else:
            # No NBD device specified - use standard scan (less safe)
            logger.warning("No NBD device specified - using standard LVM scan")
            result = subprocess.run(["pvscan", "--cache"], capture_output=True, text=True, check=False)

            if result.returncode != 0:
                logger.debug(f"pvscan failed: {result.stderr}")
                return

            result = subprocess.run(["vgscan", "--cache"], capture_output=True, text=True, check=False)

            if result.returncode != 0:
                logger.debug(f"vgscan failed: {result.stderr}")
                return

        # Find VGs using explicit device list (only NBD partitions)
        vgs_to_activate = []
        if nbd_partitions:
            try:
                # Query each NBD partition with devicesfile disabled
                vg_set = set()
                for part in nbd_partitions:
                    try:
                        result = subprocess.run(
                            ["pvs", "--devicesfile", "", "--devices", part, "--noheadings", "-o", "vg_name"],
                            capture_output=True,
                            text=True,
                            check=False,
                        )

                        if result.returncode == 0:
                            for line in result.stdout.strip().split("\n"):
                                vg_name = line.strip()
                                if vg_name:
                                    vg_set.add(vg_name)
                                    logger.info(f"  Found VG '{vg_name}' on {part}")
                    except Exception as e:
                        logger.debug(f"  No LVM PV on {part}: {e}")
                        continue

                vgs_to_activate = list(vg_set)
                logger.info(f"Found VGs on {nbd_device}: {vgs_to_activate}")
            except Exception as e:
                logger.warning(f"Could not determine VGs from NBD partitions: {e}")
        else:
            # Fallback: list all VGs (only if no NBD device specified)
            result = subprocess.run(
                ["vgs", "--noheadings", "-o", "vg_name"], capture_output=True, text=True, check=False
            )

            if result.returncode == 0 and result.stdout.strip():
                vgs_to_activate = [vg.strip() for vg in result.stdout.strip().split("\n")]

        # Activate only NBD-related VGs with devicesfile disabled
        if vgs_to_activate:
            for vg in vgs_to_activate:
                try:
                    # Build device list for vgchange
                    cmd = ["vgchange"]
                    if nbd_partitions:
                        cmd.extend(["--devicesfile", ""])
                        for part in nbd_partitions:
                            cmd.extend(["--devices", part])
                    cmd.extend(["-ay", vg])

                    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

                    if result.returncode == 0:
                        logger.info(f"Activated VG: {vg} (from {nbd_device})")
                    else:
                        logger.warning(f"Failed to activate VG {vg}: {result.stderr}")
                        continue

                    # Ensure device nodes are created and udev catches up
                    subprocess.run(["dmsetup", "mknodes"], capture_output=True, text=True, check=False)
                    subprocess.run(
                        ["udevadm", "settle"], capture_output=True, text=True, timeout=5, check=False
                    )
                    logger.debug("Waited for udev to settle after VG activation")

                except Exception as e:
                    logger.warning(f"Failed to activate VG {vg}: {e}")

            # Track which VGs we activated for safe cleanup (append, don't overwrite)
            self.activated_vgs.extend(vgs_to_activate)
            logger.info(f"✓ LVM volume groups activated: {vgs_to_activate}")
        else:
            logger.debug("No LVM volume groups found")

    def deactivate_lvm(self):
        """
        Deactivate only LVM volume groups we activated.

        Uses devicesfile="" for consistency with activation,
        ensuring we only affect the VGs we explicitly activated.
        """
        if not self.activated_vgs:
            logger.debug("No LVM volume groups to deactivate")
            return

        logger.info(f"Deactivating LVM volume groups: {self.activated_vgs}")
        for vg in self.activated_vgs:
            try:
                result = subprocess.run(
                    ["vgchange", "--devicesfile", "", "-an", vg],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode == 0:
                    logger.debug(f"✓ Deactivated VG: {vg}")
                else:
                    logger.warning(f"Failed to deactivate VG {vg}: {result.stderr}")
            except Exception as e:
                logger.warning(f"Exception deactivating VG {vg}: {e}")

        # Settle udev after LVM deactivation
        try:
            subprocess.run(["udevadm", "settle"], capture_output=True, text=True, timeout=5, check=False)
            logger.debug("Waited for udev to settle after VG deactivation")
        except Exception as e:
            logger.debug(f"udevadm settle warning: {e}")

        # Clear the list after deactivation
        self.activated_vgs = []

    def mount_root_partition(self, nbd_device: str, job_name: str) -> str:
        """
        Find and mount root partition by trying all candidates.

        Prioritizes LVM logical volumes over raw partitions since
        enterprise Linux distributions commonly use LVM for root.
        """
        # Get all block devices (partitions + LVM logical volumes)
        result = subprocess.run(
            ["lsblk", "-n", "-l", "-p", "-o", "NAME,SIZE,TYPE"], capture_output=True, text=True, check=True
        )

        # Parse block device list - separate LVM and partitions
        lvm_candidates = []
        partition_candidates = []

        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                size = parts[1]
                dev_type = parts[2]

                # Include partitions from our NBD device
                if dev_type == "part" and name.startswith(nbd_device):
                    # Skip extended partition table entries (1K size)
                    if "1K" not in size and "512" not in size:
                        partition_candidates.append((name, "partition"))

                # Include LVM logical volumes (prioritize these)
                elif dev_type == "lvm":
                    # Only include LVs from the VGs we activated
                    # This prevents mounting host LVs
                    if self.activated_vgs:
                        # Extract VG name from device path
                        # LVM devices are typically /dev/mapper/vgname-lvname
                        for vg in self.activated_vgs:
                            vg_prefix = vg.replace("-", "--")  # LVM escapes hyphens
                            if vg_prefix in name or f"/dev/{vg}/" in name:
                                lvm_candidates.append((name, "lvm"))
                                break
                    else:
                        # No VG tracking - include all LVM (less safe)
                        lvm_candidates.append((name, "lvm"))

        # Prioritize LVM volumes first (root is usually on LVM in RHEL/CentOS)
        candidates = lvm_candidates + partition_candidates

        if not candidates:
            raise RuntimeError(
                "No partitions or LVM volumes found on the disk image. "
                "The disk may be empty, corrupted, or use an unsupported partition scheme. "
                "Verify the disk image with: qemu-img info <disk_path>"
            )

        logger.info(f"Found {len(candidates)} candidates to check:")
        logger.info(f"  LVM volumes: {len(lvm_candidates)}")
        logger.info(f"  Partitions: {len(partition_candidates)}")

        for name, dev_type in candidates:
            logger.info(f"  - {name} ({dev_type})")

        # Create mount point
        mount_path = Path(MOUNT_BASE_PATH) / job_name
        mount_path.mkdir(parents=True, exist_ok=True)

        # Try each candidate until we find one with /etc
        for name, dev_type in candidates:
            logger.info(f"Trying to mount {name} ({dev_type})")

            # Try mounting this device (readonly first to check)
            result = subprocess.run(
                ["mount", "-o", "ro", name, str(mount_path)],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.debug(f"Failed to mount {name}: {result.stderr}")
                continue

            # Check if this looks like a root filesystem
            etc_path = mount_path / "etc"
            if etc_path.is_dir():
                logger.info(f"✓ Found root filesystem on {name} ({dev_type})")
                # Remount read-write
                subprocess.run(["umount", str(mount_path)], check=True)
                subprocess.run(["mount", name, str(mount_path)], check=True)
                return str(mount_path)
            # Not root, unmount and try next
            logger.debug(f"{name} does not contain /etc")
            subprocess.run(["umount", str(mount_path)], check=False)

        raise RuntimeError(
            f"Could not find root filesystem — none of the {len(candidates)} "
            f"partitions/volumes contain /etc. The disk image may not contain a "
            f"Linux root filesystem, or the filesystem type may not be supported."
        )

    def mount_boot_partition(self, nbd_device: str, root_mount_path: str):
        """Mount /boot if it's a separate partition."""
        boot_part = f"{nbd_device}p1"

        if not Path(boot_part).exists():
            return

        # Check if it's a filesystem
        result = subprocess.run(
            ["blkid", "-s", "TYPE", "-o", "value", boot_part],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return

        # Create boot mount point
        boot_mount = Path(root_mount_path) / "boot"
        boot_mount.mkdir(parents=True, exist_ok=True)

        # Mount boot partition
        logger.info(f"Mounting boot partition {boot_part} to {boot_mount}")
        subprocess.run(["mount", boot_part, str(boot_mount)], capture_output=True, check=False)

    def is_mount_point(self, path: str) -> bool:
        """Check if path is a mount point."""
        result = subprocess.run(["mountpoint", "-q", path], capture_output=True, check=False)
        return result.returncode == 0

    def unmount(self, mount_path: str):
        """Unmount a filesystem."""
        logger.info(f"Unmounting {mount_path}")
        subprocess.run(["umount", mount_path], check=True, capture_output=True)

    def disconnect_nbd(self, nbd_device: str):
        """Disconnect NBD device."""
        logger.info(f"Disconnecting {nbd_device}")
        subprocess.run(["qemu-nbd", "--disconnect", nbd_device], capture_output=True, check=False)

    def update_node_annotations(self, job_ref: str, nbd_device: str, mount_path: str):
        """Update node annotations with NBD ready status."""
        body = {
            "metadata": {
                "annotations": {
                    ANNOTATION_NBD_READY: "true",
                    ANNOTATION_NBD_DEVICE: nbd_device,
                    ANNOTATION_MOUNT_PATH: mount_path,
                }
            }
        }

        self.api.patch_node(self.node_name, body)
        logger.info(f"Updated node annotations for {job_ref}")

    def clear_node_annotations(self, job_ref: str):
        """Clear NBD annotations from node."""
        body = {
            "metadata": {
                "annotations": {
                    ANNOTATION_OFFLINE_FIX_JOB: None,
                    ANNOTATION_NBD_READY: None,
                    ANNOTATION_NBD_DEVICE: None,
                    ANNOTATION_MOUNT_PATH: None,
                    ANNOTATION_CLEANUP: None,
                }
            }
        }

        self.api.patch_node(self.node_name, body)
        logger.info(f"Cleared node annotations for {job_ref}")


def main():
    """Main entry point."""
    node_name = os.environ.get("NODE_NAME")
    if not node_name:
        logger.error("NODE_NAME environment variable not set")
        sys.exit(1)

    daemon = NBDPrepDaemon(node_name)
    daemon.run()


if __name__ == "__main__":
    main()
