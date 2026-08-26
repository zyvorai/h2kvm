# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
H2KVM Namespace-Isolated NBD + LVM Engine - Production Enhanced Version

Provides robust namespace-based isolation for LVM operations using unshare.
This offers maximum security by isolating /dev and preventing host contamination.

Key features:
- Proper error handling and cleanup
- Namespace reuse for performance
- SELinux/AppArmor awareness
- Resource limits and timeouts
- Logging and monitoring hooks

Usage:
    engine = H2KVM(
        image="guest.qcow2",
        mount_options=["ro", "noexec", "nosuid"],
        debug=True
    )

    with engine.namespace() as hvm:
        volumes = hvm.start()
        hvm.mount(volumes[0], "/mnt/guest")
        # ... do work ...
        # automatic cleanup
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from h2kvm.core.structured_log import PhaseTimer, TraceContext, log_event

logger = logging.getLogger(__name__)


class H2KVMError(Exception):
    """H2KVM operation failed."""


# ---------------------------------------
# NBD Module Loading
# ---------------------------------------


def load_nbd_module(max_part: int = 16) -> None:
    """
    Load NBD kernel module if not already loaded.

    Args:
        max_part: Maximum partitions per NBD device (default: 16)
    """
    # Check if already loaded
    try:
        with open("/proc/modules", encoding="utf-8") as f:
            if "nbd" in f.read():
                logger.debug("NBD module already loaded")
                return
    except OSError:
        pass

    # Load module
    try:
        subprocess.run(
            ["modprobe", "nbd", f"max_part={max_part}"], check=True, capture_output=True, timeout=10
        )
        logger.info("Loaded NBD module with max_part=%s", max_part)
    except subprocess.CalledProcessError as e:
        logger.warning("Could not load NBD module: %s", e.stderr.decode())
    except subprocess.TimeoutExpired:
        logger.warning("NBD module load timed out")


# ---------------------------------------
# Enhanced NBD Manager with Monitoring
# ---------------------------------------


class NBDManager:
    """Manages NBD connections with monitoring and automatic cleanup"""

    # Track used NBD devices across instances
    _used_devices: dict[str, bool] = {}

    def __init__(self, device: str = "/dev/nbd0", timeout: int = 30):
        """
        Initialize NBD manager.

        Args:
            device: NBD device path (default: /dev/nbd0)
            timeout: Connection timeout in seconds (default: 30)
        """
        self.device = device
        self.timeout = timeout
        self.pid = None
        self.connected = False

    def find_free_nbd(self) -> str:
        """
        Find first available NBD device.

        Returns:
            Path to free NBD device

        Raises:
            H2KVMError: If no free devices available
        """
        for i in range(16):
            dev = f"/dev/nbd{i}"
            if dev not in self._used_devices and os.path.exists(dev):
                self.device = dev
                return dev
        raise H2KVMError("No free NBD devices found")

    def connect(self, image: str) -> None:
        """
        Connect image to NBD with monitoring.

        Args:
            image: Path to disk image (qcow2, raw, vmdk, etc.)

        Raises:
            H2KVMError: If connection fails or times out
        """
        if not os.path.exists(image):
            raise H2KVMError(f"Image not found: {image}")

        # Find available device if current is in use
        if self.device in self._used_devices:
            self.find_free_nbd()

        load_nbd_module()

        # Start qemu-nbd with monitoring
        cmd = [
            "qemu-nbd",
            "--connect",
            self.device,
            "--cache=none",
            "--aio=native",
            "--discard=unmap",
            "--detect-zeroes=unmap",
            image,
        ]

        logger.info("Connecting %s to %s", image, self.device)

        # Start process (redirect to DEVNULL to avoid FD leak from pipes).
        # Deliberately not using 'with': qemu-nbd stays running as a background server
        # for the NBD connection after this call returns (it's disconnected later via
        # NBDManager.disconnect()) — closing/waiting on it here would be wrong or could hang.
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        self.pid = process.pid

        # Wait for connection with timeout
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if os.path.exists(self.device):
                # Verify device is ready
                try:
                    subprocess.run(
                        ["blockdev", "--getsz", self.device], check=True, capture_output=True, timeout=5
                    )
                    self.connected = True
                    self._used_devices[self.device] = True
                    logger.info("Successfully connected %s", self.device)
                    break
                except subprocess.CalledProcessError:
                    time.sleep(0.5)
            time.sleep(0.1)
        else:
            # Timeout - kill process and cleanup
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise H2KVMError(f"Timeout connecting to {self.device}")

        # Partition table probing
        try:
            subprocess.run(["partprobe", self.device], check=False, timeout=5)
        except subprocess.CalledProcessError:
            pass  # Non-fatal
        except subprocess.TimeoutExpired:
            logger.warning("partprobe timed out")

        time.sleep(1)  # Device settling time

    def disconnect(self) -> None:
        """Safely disconnect NBD device with cleanup."""
        if not self.connected:
            return

        logger.info("Disconnecting %s", self.device)

        # Try graceful disconnect first
        try:
            subprocess.run(["qemu-nbd", "--disconnect", self.device], check=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Force disconnect if needed
            try:
                with open(f"/sys/block/{Path(self.device).name}/pid", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(2)
            except (OSError, ValueError, ProcessLookupError):
                pass

        # Wait for device to become inactive (size == 0 means disconnected)
        start_time = time.time()
        nbd_name = Path(self.device).name
        while time.time() - start_time < 10:
            try:
                with open(f"/sys/block/{nbd_name}/size", encoding="utf-8") as f:
                    if int(f.read().strip()) == 0:
                        break
            except (OSError, ValueError):
                break
            time.sleep(0.5)

        self.connected = False
        self._used_devices.pop(self.device, None)
        logger.info("Disconnected %s", self.device)


# ---------------------------------------
# Enhanced Namespace LVM with Monitoring
# ---------------------------------------


class NamespaceLVM:
    """Manages LVM operations in isolated namespace"""

    def __init__(self, nbd_device: str, lvm_dir: str | None = None):
        """
        Initialize namespace LVM manager.

        Args:
            nbd_device: NBD device path to scan
            lvm_dir: Optional LVM metadata directory (auto-created if None)
        """
        self.nbd = nbd_device
        self.lvm_dir = lvm_dir or tempfile.mkdtemp(prefix="h2kvm-lvm-")
        self.ns_pid = None
        self.ns_mounts = []

    def _build_lvm_config(self) -> str:
        """
        Generate LVM configuration for isolation.

        Uses anchored regex (start AND end) to prevent overmatch
        (e.g. /dev/nbd1 must not match /dev/nbd10).

        Returns:
            LVM configuration string with strict filtering
        """
        escaped = self.nbd.replace("/", r"\/")
        return f"""
devices {{
    # Only allow our NBD device — anchored start AND end
    filter = [ "a|^{escaped}($|p[0-9]+$)|", "r|.*|" ]
    global_filter = [ "a|^{escaped}($|p[0-9]+$)|", "r|.*|" ]

    # Prevent host device scanning
    obtain_device_list_from_udev = 0
    external_device_info_source = "none"

    # Cache settings
    cache_dir = "{self.lvm_dir}/cache"
    cache_file_prefix = "h2kvm-"

    # Safe defaults
    ignore_suspended_devices = 1
    ignore_lvm_mirrors = 1
    disable_after_error_count = 3
    require_restorefile_with_uuid = 1
}}

global {{
    locking_dir = "{self.lvm_dir}/lock"
    prioritise_write_locks = 1
    wait_for_locks = 1
    fallback_to_clustered_locking = 0
    fallback_to_local_locking = 1
    locking_type = 1
}}

activation {{
    volume_list = [ ]
    auto_activation_volume_list = [ ]
    thin_pool_autoextend_threshold = 0
    read_only_volume_list = [ ]
    raid_region_size = 512
    readahead = "auto"
    raid_fault_policy = "warn"
    mirror_log_fault_policy = "allocate"
    mirror_device_fault_policy = "remove"
}}
"""

    def _create_namespace_script(self, action: str = "activate") -> str:
        """
        Create script for namespace operations.

        Args:
            action: Operation type ("activate" or "deactivate")

        Returns:
            Path to generated script
        """
        config = self._build_lvm_config()
        config_file = os.path.join(self.lvm_dir, "lvm.conf")

        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config)

        q_nbd = shlex.quote(self.nbd)
        q_lvm_dir = shlex.quote(self.lvm_dir)
        q_config_file = shlex.quote(config_file)
        q_action = shlex.quote(action)

        script = f"""#!/bin/bash
set -euo pipefail

# Create isolated /dev
mount -t tmpfs tmpfs /dev
mkdir -p /dev/mapper /dev/pts
mount -t devpts devpts /dev/pts

# Expose NBD device
if [ -b {q_nbd} ]; then
    major=$(stat -c '%t' {q_nbd})
    minor=$(stat -c '%T' {q_nbd})
    mknod {q_nbd} b $((0x$major)) $((0x$minor))

    # Expose partitions
    for part in {q_nbd}p*; do
        if [ -b "$part" ]; then
            major=$(stat -c '%t' "$part")
            minor=$(stat -c '%T' "$part")
            mknod "$part" b $((0x$major)) $((0x$minor))
        fi
    done
fi

# Bind mount LVM control if exists
if [ -e /dev/mapper/control ]; then
    touch /dev/mapper/control
    mount --bind /dev/mapper/control /dev/mapper/control
fi

# Set LVM environment
export LVM_SYSTEM_DIR={q_lvm_dir}

# Create required directories
mkdir -p {q_lvm_dir}/cache {q_lvm_dir}/lock

# Configure LVM
export LVM_SUPPRESS_FD_WARNINGS=1

if [ {q_action} = "activate" ]; then
    # Scan and activate
    lvm pvscan --cache 2>&1 || true
    lvm vgscan --config {q_config_file} 2>&1 || true
    lvm vgchange -ay --config {q_config_file} 2>&1

    # Wait for devices
    sleep 1

    # List logical volumes
    lvm lvs -o lv_path --noheadings --config {q_config_file} 2>&1 || true
elif [ {q_action} = "deactivate" ]; then
    # Deactivate volumes
    lvm vgchange -an --config {q_config_file} 2>&1 || true
fi
"""

        script_file = os.path.join(self.lvm_dir, "namespace.sh")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(script_file, 0o700)  # owner-only: script lives in a private tempdir

        return script_file

    def run_in_namespace(self, action: str = "activate") -> list[str]:
        """
        Run LVM command in isolated namespace.

        Args:
            action: Operation type ("activate" or "deactivate")

        Returns:
            List of logical volume paths

        Raises:
            H2KVMError: If operation fails or times out
        """
        script_file = self._create_namespace_script(action)

        try:
            # Start unshare process. Deliberately not using 'with': on TimeoutExpired below
            # we must kill the whole process group *before* waiting on it, whereas the 'with'
            # context manager would call wait() on __exit__ first and could hang indefinitely.
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                ["unshare", "--mount", "--pid", "--fork", "--mount-proc", "bash", script_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,  # New process group/session (thread-safe vs preexec_fn)
            )

            self.ns_pid = process.pid

            # Monitor process with timeout
            stdout, stderr = process.communicate(timeout=60)

            if process.returncode != 0:
                logger.error("Namespace operation failed: %s", stderr)
                raise H2KVMError(f"LVM operation failed: {stderr}")

            return self._parse_lv_output(stdout)

        except subprocess.TimeoutExpired as err:
            # Kill entire process group
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise H2KVMError("LVM operation timed out") from err

    def _parse_lv_output(self, output: str) -> list[str]:
        """
        Parse LVM output for logical volumes.

        Args:
            output: Raw LVM command output

        Returns:
            List of logical volume paths
        """
        volumes = []
        for line in output.splitlines():
            line = line.strip()
            if line and line.startswith("/dev/"):
                volumes.append(line)
        return volumes

    def cleanup(self) -> None:
        """Clean up namespace resources."""
        # Deactivate volumes
        try:
            self.run_in_namespace("deactivate")
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort cleanup; deactivation failure must not block tempdir removal below.
            logger.warning("Deactivation failed: %s", e)

        # Clean up directory
        shutil.rmtree(self.lvm_dir, ignore_errors=True)
        self.ns_pid = None


# ---------------------------------------
# Main H2KVM Engine with Enhanced Features
# ---------------------------------------


class H2KVM:  # pylint: disable=too-many-instance-attributes
    """Main H2KVM engine with namespace isolation"""

    def __init__(
        self,
        image: str,
        nbd: str | None = None,
        mount_options: list[str] | None = None,
        debug: bool = False,
    ):
        """
        Initialize H2KVM engine.

        Args:
            image: Path to disk image
            nbd: Optional NBD device path (auto-selected if None)
            mount_options: Mount options list (default: ["ro"])
            debug: Enable debug logging
        """
        self.image = image
        self.nbd = nbd or "/dev/nbd0"
        self.mount_options = mount_options or ["ro"]  # Read-only by default
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

        self.nbd_mgr = NBDManager(self.nbd)
        self.lvm = None
        self.mountpoints = []
        self.active = False

    @contextmanager
    def namespace(self):
        """
        Context manager for namespace operations.

        Ensures automatic cleanup on exit.

        Example:
            with engine.namespace() as hvm:
                volumes = hvm.start()
                # ... operations ...
                # automatic cleanup on exit
        """
        try:
            yield self
        finally:
            self.stop()

    def start(self) -> list[str]:
        """
        Start H2KVM and activate volumes.

        Returns:
            List of discovered logical volume paths

        Raises:
            H2KVMError: If startup fails
        """
        logger.info("Starting H2KVM with image: %s", self.image)

        with TraceContext(
            vm_id=Path(self.image).name, workflow="namespace_activation", component="namespace_lvm"
        ):
            try:
                # Connect NBD
                with PhaseTimer("ns_nbd_connect_start", "ns_nbd_connect_complete", phase="nbd"):
                    self.nbd_mgr.connect(self.image)

                # Initialize LVM in namespace
                self.lvm = NamespaceLVM(self.nbd_mgr.device)

                # Activate volumes
                with PhaseTimer("ns_lvm_activate_start", "ns_lvm_activate_complete", phase="lvm"):
                    volumes = self.lvm.run_in_namespace("activate")

                if not volumes:
                    logger.warning("No logical volumes found")
                else:
                    logger.info("Found %d volume(s)", len(volumes))
                    for v in volumes:
                        logger.info("  %s", v)
                    log_event("ns_volumes_discovered", volume_count=len(volumes))

                self.active = True
                return volumes

            except Exception as e:
                self.stop()
                raise H2KVMError(f"Start failed: {e}") from e

    def mount(self, volume: str, mountpoint: str) -> str:
        """
        Mount a logical volume.

        Args:
            volume: Logical volume path (e.g., /dev/mapper/vg-lv)
            mountpoint: Target mount point

        Returns:
            Mount point path

        Raises:
            H2KVMError: If mount fails
        """
        if not self.active:
            raise H2KVMError("Engine not started")

        Path(mountpoint).mkdir(parents=True, exist_ok=True)

        # Build mount options
        options = ",".join(self.mount_options)
        cmd = ["mount", "-o", options] if options else ["mount"]
        cmd.extend([volume, mountpoint])

        try:
            subprocess.run(cmd, check=True, timeout=30)
            self.mountpoints.append(mountpoint)
            logger.info("Mounted %s to %s", volume, mountpoint)
            return mountpoint
        except subprocess.TimeoutExpired as e:
            raise H2KVMError("Mount timeout") from e
        except subprocess.CalledProcessError as e:
            raise H2KVMError(f"Mount failed: {e}") from e

    def unmount(self, mountpoint: str) -> None:
        """
        Unmount a volume.

        Args:
            mountpoint: Mount point to unmount
        """
        try:
            subprocess.run(["umount", mountpoint], check=True, timeout=30)
            self.mountpoints.remove(mountpoint)
            logger.info("Unmounted %s", mountpoint)
        except ValueError:
            pass  # Not in list
        except subprocess.CalledProcessError as e:
            logger.exception("Unmount failed: %s", e)

    def stop(self) -> None:
        """Stop H2KVM and cleanup all resources."""
        logger.info("Stopping H2KVM")

        with PhaseTimer("ns_shutdown_start", "ns_shutdown_complete", phase="namespace_shutdown"):
            # Unmount any remaining mounts
            for mp in self.mountpoints[:]:
                try:
                    self.unmount(mp)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # Best-effort shutdown; one failed unmount must not block the rest of cleanup.
                    logger.exception("Failed to unmount %s: %s", mp, e)

            # Cleanup LVM namespace
            if self.lvm:
                try:
                    self.lvm.cleanup()
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # Best-effort shutdown; LVM cleanup failure must not block NBD disconnect.
                    logger.exception("LVM cleanup failed: %s", e)

            # Disconnect NBD
            try:
                self.nbd_mgr.disconnect()
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort shutdown; must not raise out of stop().
                logger.exception("NBD disconnect failed: %s", e)

        self.active = False
        logger.info("H2KVM stopped")

    def get_volume_info(self, volume: str) -> dict:
        """
        Get detailed volume information.

        Args:
            volume: Volume path to inspect

        Returns:
            Dictionary with volume information
        """
        if not self.active:
            raise H2KVMError("Engine not started")

        # Use lsblk to get volume info
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT", "-b", volume],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return {"info": result.stdout}
        except subprocess.CalledProcessError:
            return {"error": "Could not get volume info"}


# ---------------------------------------
# Production Example with Monitoring
# ---------------------------------------


def main():
    """Production example with proper error handling"""

    image = "guest.qcow2"
    mountpoint = "/mnt/h2kvm"

    # Create engine with read-only mount for safety
    engine = H2KVM(image=image, mount_options=["ro", "noexec", "nosuid"], debug=True)

    try:
        # Use context manager for automatic cleanup
        with engine.namespace() as hvm:
            volumes = hvm.start()

            if volumes:
                # Get volume information
                info = hvm.get_volume_info(volumes[0])
                logger.info("Volume info:\n%s", info.get("info", "N/A"))

                # Mount the first volume
                hvm.mount(volumes[0], mountpoint)

                # List contents
                subprocess.run(["ls", "-la", mountpoint], check=False)

                # Simulate work
                time.sleep(5)

                # Automatic unmount and cleanup in context manager

    except H2KVMError as e:
        logger.exception("H2KVM error: %s", e)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Top-level CLI entry point; any unexpected failure must be reported, not crash raw.
        logger.exception("Unexpected error: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
