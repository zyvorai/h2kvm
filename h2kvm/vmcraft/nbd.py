# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/nbd.py
# pylint: disable=too-many-lines  # cohesive NBD device lifecycle module; splitting would hurt readability more than help
"""
NBD (Network Block Device) management for exposing disk images as block devices.

Uses qemu-nbd to connect disk images (qcow2, vmdk, vdi, vhd, raw) to /dev/nbdX devices,
enabling native Linux tools to access and modify VM disk images.
"""

from __future__ import annotations

import atexit
import errno
import fcntl
import fnmatch
import json
import logging
import os
import stat as stat_module
import subprocess
import time
from pathlib import Path
from typing import Any

from h2kvm.converters.qemu.converter import Convert
from h2kvm.core.constants import DELAY_STATUS_POLL, NBD_MAX_DEVICE
from h2kvm.core.retry import retry_with_backoff
from h2kvm.core.structured_log import log_event

from ._utils import run_sudo
from .nbd_converter import DiskConverter

logger = logging.getLogger(__name__)


def cleanup_orphaned_devices(  # pylint: disable=too-many-branches,too-many-statements  # scans every NBD device through several independent liveness checks
    nbd_max: int = NBD_MAX_DEVICE,
    *,
    dry_run: bool = False,
) -> list[str]:
    """
    Scan for connected-but-unused NBD devices and disconnect them.

    An NBD device is considered orphaned when:
        - /sys/block/nbdN/size > 0 (device has a backing image attached)
        - /sys/block/nbdN/pid does not reference a live process, OR
          no process holds the device open (checked via ``fuser``)

    This is useful for cleaning up after crashes or unclean shutdowns that
    leave ``qemu-nbd`` processes defunct or devices connected without an owner.

    Args:
        nbd_max: Maximum NBD device number to scan (default: NBD_MAX_DEVICE).
        dry_run: If True, log what would be cleaned up but take no action.

    Returns:
        List of device paths that were (or would be) disconnected.

    Example:
        cleaned = cleanup_orphaned_devices()
        if cleaned:
            logger.info("Cleaned up %d orphaned NBD devices", len(cleaned))
    """
    cleaned: list[str] = []

    for idx in range(nbd_max + 1):
        nbd_name = f"nbd{idx}"
        sys_block = Path(f"/sys/block/{nbd_name}")

        if not sys_block.exists():
            continue

        # Check if device has a backing image (size > 0 means connected)
        size_file = sys_block / "size"
        try:
            if not size_file.exists():
                continue
            size = int(size_file.read_text().strip())
            if size == 0:
                continue  # device is free
        except (ValueError, OSError):
            continue

        # Device is connected — check if a live process owns it
        device_path = f"/dev/{nbd_name}"
        pid_file = sys_block / "pid"
        owner_alive = False

        # Method 1: check /sys/block/nbdN/pid (kernel-exported qemu-nbd PID)
        try:
            if pid_file.exists():
                pid = int(pid_file.read_text().strip())
                # Check if the process is still alive
                try:
                    os.kill(pid, 0)  # signal 0 = existence check
                    owner_alive = True
                except OSError as e:
                    if e.errno == errno.ESRCH:
                        # No such process — the owner is gone
                        owner_alive = False
                    elif e.errno == errno.EPERM:
                        # Process exists but we lack permission to signal it
                        owner_alive = True
                    else:
                        owner_alive = True  # err on the safe side
        except (ValueError, OSError):
            pass

        # Method 2: fallback to fuser if pid file is absent
        if not owner_alive and not pid_file.exists():
            try:
                result = subprocess.run(
                    ["fuser", device_path],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                # fuser exits 0 if processes are found, 1 if not
                if result.returncode == 0 and result.stdout.strip():
                    owner_alive = True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                # fuser not available or timed out — cannot determine, skip
                continue

        if owner_alive:
            logger.debug(
                "NBD device %s is in use by a live process — skipping",
                device_path,
            )
            continue

        # Device is orphaned — disconnect it
        if dry_run:
            logger.info(
                "Would disconnect orphaned NBD device %s (size=%d, dry_run=True)",
                device_path,
                size,
            )
        else:
            logger.info(
                "Disconnecting orphaned NBD device %s (size=%d, no live owner)",
                device_path,
                size,
            )
            try:
                run_sudo(
                    logger,
                    ["qemu-nbd", "--disconnect", device_path],
                    check=False,
                    capture=True,
                )
                log_event(
                    "nbd_orphan_cleaned",
                    nbd_device=device_path,
                    size_sectors=size,
                )
                logger.info("Disconnected orphaned NBD device %s", device_path)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort orphan cleanup; a single device's failure must not abort the scan
                logger.warning(
                    "Failed to disconnect orphaned NBD device %s: %s",
                    device_path,
                    e,
                )
                continue

        cleaned.append(device_path)

    if cleaned:
        log_event("nbd_orphan_cleanup_complete", count=len(cleaned), devices=cleaned)
        logger.info("Orphaned NBD cleanup complete: %d device(s) cleaned", len(cleaned))
    else:
        logger.debug("No orphaned NBD devices found")

    return cleaned


class NBDSecurity:
    """
    Security validation for NBD operations.

    Validates image paths to prevent:
    - Directory traversal attacks (../../etc/passwd)
    - Symlink attacks to system files
    - Access to system directories
    - Opening non-image files (devices, sockets, etc.)

    Example:
        security = NBDSecurity(logger)
        security.add_allowed_directory(Path("/var/lib/libvirt/images"))

        is_valid, error = security.validate_image_path(Path("/tmp/vm.qcow2"))
        if not is_valid:
            raise ValueError(error)
    """

    def __init__(self, log: logging.Logger):
        """
        Initialize security validator.

        Args:
            log: Logger instance
        """
        self.logger = log
        self.allowed_dirs: list[Path] = []

        # Deny access to system directories
        self.denied_patterns: list[str] = [
            "/etc/*",
            "/boot/*",
            "/dev/*",
            "/proc/*",
            "/sys/*",
            "/run/*",
            "/root/*",  # Unless explicitly allowed
        ]

    def add_allowed_directory(self, path: Path) -> None:
        """
        Add directory to whitelist.

        Only images within whitelisted directories can be opened.
        If no directories are whitelisted, all paths are allowed
        (except denied patterns).

        Args:
            path: Directory to allow (will be resolved)

        Example:
            security.add_allowed_directory(Path("/var/lib/libvirt/images"))
            security.add_allowed_directory(Path.home() / "vmware")
        """
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_dir():
                self.logger.warning(f"Allowed path is not a directory: {path}")
                return
            self.allowed_dirs.append(resolved)
            self.logger.debug(f"Added allowed directory: {resolved}")
        except (OSError, RuntimeError) as e:
            self.logger.warning(
                f"Failed to add allowed directory {path}: {e}\n"
                f"    Either create the directory, or remove/fix it in your config.\n"
                f"    In /etc/h2kvm/config.yaml:\n"
                f"        allowed_dirs:\n"
                f"          - /var/lib/libvirt/images\n"
                f"          # - {path}  # remove or correct this entry\n"
                f"    Or via CLI:  --allowed-dirs /var/lib/libvirt/images"
            )

    def add_denied_pattern(self, pattern: str) -> None:
        """
        Add pattern to deny list.

        Args:
            pattern: Glob pattern to deny (e.g., "*.exe", "/tmp/*")

        Example:
            security.add_denied_pattern("*.exe")
            security.add_denied_pattern("/tmp/*")
        """
        self.denied_patterns.append(pattern)
        self.logger.debug(f"Added denied pattern: {pattern}")

    def validate_image_path(  # pylint: disable=too-many-return-statements,too-many-branches  # each validation check has its own explicit rejection reason
        self, image_path: Path
    ) -> tuple[bool, str | None]:
        """
        Validate that image path is safe to open.

        Checks:
        1. Path resolves without symlink loops
        2. Path is within allowed directories (if any configured)
        3. Path doesn't match denied patterns
        4. File is readable
        5. File is a regular file (not device, socket, etc.)

        Args:
            image_path: Path to validate

        Returns:
            (is_valid, error_message)
            - is_valid: True if path is safe, False otherwise
            - error_message: Detailed error if invalid, None if valid

        Example:
            is_valid, error = security.validate_image_path(Path("/etc/passwd"))
            # Returns: (False, "Path matches denied pattern: /etc/*")
        """
        try:
            # Resolve with strict=True to:
            # - Detect symlink loops (raises RuntimeError)
            # - Verify file exists (raises FileNotFoundError)
            # - Resolve all symlinks
            resolved = image_path.resolve(strict=True)
        except FileNotFoundError:
            return False, f"Image file not found: {image_path}"
        except RuntimeError as e:
            # Symlink loop detected
            if "loop" in str(e).lower() or "recursive" in str(e).lower():
                return False, f"Symlink loop detected: {image_path}"
            return False, f"Path resolution failed: {image_path}: {e}"
        except OSError as e:
            return False, f"Invalid path: {image_path}: {e}"

        # Check if path is within explicitly allowed directories.
        # If allowed, skip denied pattern check (user explicitly authorized this path).
        in_allowed = False
        if self.allowed_dirs:
            for allowed_dir in self.allowed_dirs:
                try:
                    resolved.relative_to(allowed_dir)
                    in_allowed = True
                    break
                except ValueError:
                    continue

            if not in_allowed:
                return False, (
                    f"Path {resolved} not in allowed directories.\n"
                    f"Allowed directories: {[str(d) for d in self.allowed_dirs]}\n"
                    f"Add allowed directory with: security.add_allowed_directory(Path('...'))"
                )

        # Check denied patterns — but skip if path was explicitly allowed
        if not in_allowed:
            resolved_str = str(resolved)
            for pattern in self.denied_patterns:
                if fnmatch.fnmatch(resolved_str, pattern):
                    return False, f"Path matches denied pattern: {pattern}"

        # Verify file is readable
        try:
            if not os.access(resolved, os.R_OK):
                return False, f"File not readable: {resolved}"
        except OSError as e:
            return False, f"Permission check failed: {resolved}: {e}"

        # Check file is a regular file (not device, socket, fifo, etc.)
        try:
            stat_info = resolved.stat()

            if stat_module.S_ISBLK(stat_info.st_mode):
                return False, f"Path is a block device (not a regular file): {resolved}"
            if stat_module.S_ISCHR(stat_info.st_mode):
                return False, f"Path is a character device (not a regular file): {resolved}"
            if stat_module.S_ISFIFO(stat_info.st_mode):
                return False, f"Path is a FIFO (not a regular file): {resolved}"
            if stat_module.S_ISSOCK(stat_info.st_mode):
                return False, f"Path is a socket (not a regular file): {resolved}"
            if not stat_module.S_ISREG(stat_info.st_mode):
                return False, f"Path is not a regular file: {resolved}"
        except OSError as e:
            return False, f"File stat failed: {resolved}: {e}"

        # All checks passed
        return True, None


class NBDDeviceManager:  # pylint: disable=too-many-instance-attributes  # tracks device, socket, lock, and conversion state for the full connect/disconnect lifecycle
    """
    Manages NBD device lifecycle for disk image access.

    Handles:
    - Finding free NBD devices (/dev/nbd0 through /dev/nbd15)
    - Connecting disk images via qemu-nbd
    - Disconnecting and cleanup
    - Partition mapping
    - Resource tracking for proper cleanup

    Example:
        manager = NBDDeviceManager(logger, readonly=True)
        try:
            nbd_device = manager.connect('/path/to/disk.qcow2', format='qcow2')
            partitions = manager.get_partitions(nbd_device)
            # Use partitions...
        finally:
            manager.disconnect()
    """

    def __init__(  # pylint: disable=too-many-arguments  # NBD manager construction covers device range, security, and mode independently
        self,
        log: logging.Logger,
        *,
        readonly: bool = True,
        nbd_min: int = 0,
        nbd_max: int = NBD_MAX_DEVICE,
        conversion_dir: str | Path | None = None,
        security: NBDSecurity | None = None,
        use_socket: bool = False,
    ):
        """
        Initialize NBD manager.

        Args:
            log: Logger instance
            readonly: Mount NBD in read-only mode (default: True)
            nbd_min: Minimum NBD device number (default: 0)
            nbd_max: Maximum NBD device number (default: 15)
            conversion_dir: Directory for VMDK conversion temp files.
                           Defaults to ~/.cache/h2kvm/conversions
            security: Optional security validator. If None, creates default.
            use_socket: Use UNIX socket mode instead of kernel NBD
                (``--socket`` instead of ``--connect /dev/nbdX``).
                Socket path: ``/run/h2kvm/nbd-{image_stem}.sock``.
                No kernel NBD module required.  Default: False.

        Example:
            # With default security
            manager = NBDDeviceManager(logger)

            # With UNIX socket mode (no kernel NBD module needed)
            manager = NBDDeviceManager(logger, use_socket=True)

            # With custom security
            security = NBDSecurity(logger)
            security.add_allowed_directory(Path("/var/lib/libvirt/images"))
            manager = NBDDeviceManager(logger, security=security)
        """
        self.logger = log
        self.readonly = bool(readonly)
        self.nbd_min = nbd_min
        self.nbd_max = nbd_max
        self.use_socket = use_socket
        self._socket_path: Path | None = None
        self._socket_process: subprocess.Popen | None = None

        # Set conversion directory with proper default
        if conversion_dir:
            self._conversion_dir = Path(conversion_dir).expanduser().resolve()
        else:
            # Default: /var/lib/h2kvm/conversions (created by packaging)
            self._conversion_dir = Path("/var/lib/h2kvm/conversions")

        self._nbd_device: str | None = None
        self._nbd_process = None
        self._connected = False
        self._converted_qcow2_path: Path | None = None  # Track temp qcow2 for cleanup
        self._keep_converted = False  # Flag to preserve converted qcow2

        # Disk conversion delegate
        self._converter = DiskConverter(self._conversion_dir, log)

        # Security validation
        self.security = security or NBDSecurity(log)

        # Set up default allowed directories if none configured
        if not self.security.allowed_dirs:
            # Allow common VM image directories
            common_dirs = [
                Path.home() / "vmware",
                Path.home() / "VirtualBox VMs",
                Path("/var/lib/libvirt/images"),
                Path("/var/lib/vz/images"),
                self._conversion_dir,  # Allow our conversion directory
            ]

            for dir_path in common_dirs:
                if dir_path.exists():
                    self.security.add_allowed_directory(dir_path)

        # Device locking to prevent race conditions
        self._lock_dir = Path("/run/h2kvm")
        try:
            self._lock_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fallback to user directory if /var/lock not writable
            self._lock_dir = Path.home() / ".cache" / "h2kvm" / "locks"
            self._lock_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Using user lock directory: {self._lock_dir}")

        self._device_locks: dict[str, int] = {}  # device -> file descriptor

        # Register cleanup handler for crash scenarios
        # This ensures temp files are cleaned up even if process is killed
        atexit.register(self._emergency_cleanup)

    def _acquire_device_lock(self, nbd_device: str) -> bool:
        """
        Acquire exclusive lock on NBD device to prevent race conditions.

        Uses advisory file locking (flock) to ensure atomic device acquisition.
        This prevents two processes from grabbing the same NBD device.

        Args:
            nbd_device: Device path (e.g., /dev/nbd0)

        Returns:
            True if lock acquired, False if device is busy

        Example:
            if self._acquire_device_lock("/dev/nbd0"):
                # Device is now locked to us
                self.connect_device("/dev/nbd0")
            else:
                # Device is in use by another process
                pass
        """
        nbd_name = Path(nbd_device).name
        lock_file = self._lock_dir / f"{nbd_name}.lock"

        self.logger.debug(
            "Attempting to acquire device lock: device=%s, lock_dir=%s, lock_file=%s",
            nbd_device,
            self._lock_dir,
            lock_file,
        )

        try:
            # Ensure lock directory exists (may vanish on tmpfs after reboot)
            self._lock_dir.mkdir(parents=True, exist_ok=True)

            # Open or create lock file
            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o644)

            try:
                # Try to acquire exclusive, non-blocking lock
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Write our PID for debugging
                os.ftruncate(fd, 0)
                os.write(fd, f"{os.getpid()}\n".encode())
                os.fsync(fd)

                # Store lock file descriptor
                self._device_locks[nbd_device] = fd

                self.logger.debug(
                    "Acquired lock on %s (pid=%d, lock_file=%s)",
                    nbd_device,
                    os.getpid(),
                    lock_file,
                )
                return True

            except OSError as e:
                # Lock is held by another process
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    os.close(fd)
                    self.logger.debug(
                        "Device %s is locked by another process (errno=%s, lock_file=%s)",
                        nbd_device,
                        e.errno,
                        lock_file,
                    )
                    return False
                os.close(fd)
                raise

        except OSError as e:
            self.logger.warning(
                "Failed to acquire lock on %s: %s (lock_dir=%s)",
                nbd_device,
                e,
                self._lock_dir,
            )
            return False

    def _release_device_lock(self, nbd_device: str) -> None:
        """
        Release lock on NBD device.

        Args:
            nbd_device: Device to unlock

        Example:
            self._release_device_lock("/dev/nbd0")
        """
        if nbd_device not in self._device_locks:
            return

        fd = self._device_locks.pop(nbd_device)

        try:
            # Release lock
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

            # Remove lock file
            nbd_name = Path(nbd_device).name
            lock_file = self._lock_dir / f"{nbd_name}.lock"
            lock_file.unlink(missing_ok=True)

            self.logger.debug(f"Released lock on {nbd_device}")

        except OSError as e:
            self.logger.debug(f"Error releasing lock on {nbd_device}: {e}")

    def _check_nbd_module(self) -> None:
        """Ensure NBD kernel module is loaded with partition support.

        The ``max_part=16`` parameter is supplied by
        ``/etc/modprobe.d/h2kvm-nbd.conf`` which is installed by
        the RPM package.  If the module is already loaded with
        ``max_part=0`` and no devices are active, it is reloaded;
        otherwise a warning is emitted.
        """
        try:  # pylint: disable=too-many-nested-blocks  # walks nested sysfs state to decide whether a module reload is safe
            if not Path("/dev/nbd0").exists():
                self.logger.info(
                    "Loading NBD kernel module...",
                    extra={"ctx": {"event": "nbd_module_load", "reason": "device_not_found"}},
                )
                run_sudo(self.logger, ["modprobe", "nbd"], check=True)
                time.sleep(0.5)
            else:
                max_part_path = Path("/sys/module/nbd/parameters/max_part")
                if max_part_path.exists():
                    current = max_part_path.read_text(encoding="utf-8").strip()
                    if current == "0":
                        # Check if any NBD devices are currently in use
                        any_in_use = False
                        for sysblock in sorted(Path("/sys/block").iterdir()):
                            if sysblock.name.startswith("nbd"):
                                size_file = sysblock / "size"
                                try:
                                    if size_file.exists() and int(size_file.read_text().strip()) > 0:
                                        any_in_use = True
                                        break
                                except (ValueError, OSError):
                                    pass

                        if any_in_use:
                            self.logger.warning(
                                "NBD module loaded without partition support (max_part=0), "
                                "but other NBD devices are in use — cannot safely reload. "
                                "Partition devices (nbd0p1, ...) may not be created. "
                                "Reload manually when idle: rmmod nbd && modprobe nbd"
                            )
                        else:
                            self.logger.info(
                                "NBD module loaded without partition support (max_part=0). "
                                "No active NBD devices — reloading with max_part=16..."
                            )
                            run_sudo(self.logger, ["rmmod", "nbd"], check=True)
                            time.sleep(0.3)
                            run_sudo(self.logger, ["modprobe", "nbd"], check=True)
                            time.sleep(0.5)
                            self.logger.info(
                                "NBD module reloaded with max_part=16",
                                extra={"ctx": {"event": "nbd_module_reload", "max_part": 16}},
                            )
        except Exception as e:  # pylint: disable=broad-exception-caught  # wraps modprobe/OS failures into one actionable error message
            raise RuntimeError(
                f"Failed to load the NBD kernel module.\n\n"
                "Solutions:\n"
                "  1. Load manually: sudo modprobe nbd max_part=16\n"
                "  2. Install the module if missing:\n"
                "     RHEL/Fedora: dnf install kernel-modules-extra\n"
                "     Ubuntu/Debian: apt install linux-modules-extra-$(uname -r)\n"
                "  3. Check if the module exists: modinfo nbd\n"
                "  4. On RHEL 9+, the nbd module may need to be explicitly enabled\n\n"
                f"Detail: {e}"
            ) from e

    def _is_nbd_free(self, nbd_device: str) -> bool:
        """
        Check if NBD device is free.

        Args:
            nbd_device: Device path (e.g., /dev/nbd0)

        Returns:
            True if device is free, False if in use
        """
        try:
            # Try to read from /sys/block/nbdX/size
            # If size is 0, device is free
            nbd_name = Path(nbd_device).name  # e.g., nbd0
            size_file = Path(f"/sys/block/{nbd_name}/size")
            if size_file.exists():
                size = int(size_file.read_text(encoding="utf-8").strip())
                return size == 0
            return True
        except (OSError, ValueError):
            # If we can't check, assume it's free
            return True

    def find_free_nbd(self) -> str:
        """
        Find and atomically lock a free NBD device.

        Uses advisory locking to prevent race conditions where two processes
        try to grab the same device simultaneously.

        Returns:
            Path to free NBD device (e.g., /dev/nbd0)

        Raises:
            RuntimeError: If no free NBD devices available

        Note:
            The device is locked after this call. Remember to release the lock
            by calling _release_device_lock() or disconnect().
        """
        self._check_nbd_module()

        for i in range(self.nbd_min, self.nbd_max + 1):
            nbd_device = f"/dev/nbd{i}"

            # Atomic check-and-lock: only returns True if device is free AND we got the lock
            if self._is_nbd_free(nbd_device) and self._acquire_device_lock(nbd_device):
                self.logger.debug(f"Found and locked free NBD device: {nbd_device}")
                return nbd_device

        raise RuntimeError(
            f"No free NBD devices available (checked /dev/nbd{self.nbd_min} "
            f"through /dev/nbd{self.nbd_max}). All devices are either in use or locked.\n\n"
            "Solutions:\n"
            "  1. Disconnect unused NBD devices: sudo qemu-nbd -d /dev/nbdN\n"
            "  2. Clean up orphaned devices: h2kvm will auto-clean on next run\n"
            "  3. Reload the NBD module with more devices:\n"
            "     sudo rmmod nbd && sudo modprobe nbd nbds_max=32 max_part=16\n"
            "  4. Check for stuck qemu-nbd processes: ps aux | grep qemu-nbd"
        )

    @property
    def converted_image_path(self) -> Path | None:
        """Get path to converted qcow2 if one was created, None otherwise."""
        return self._converted_qcow2_path

    def keep_converted_image(self) -> None:
        """Mark the converted qcow2 to be kept (not deleted on disconnect)."""
        self._keep_converted = True
        if self._converted_qcow2_path:
            self.logger.info(f"Preserving converted qcow2: {self._converted_qcow2_path.name}")

    def _run_local_command(
        self,
        cmd: list[str],
        *,
        check: bool = False,
        timeout: int | None = None,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a local host command for metadata/probing operations."""
        return subprocess.run(
            cmd,
            check=check,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
        )

    def _run_local_json_command(
        self,
        cmd: list[str],
        *,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Run a local command returning JSON output and parse it."""
        result = self._run_local_command(cmd, check=True, timeout=timeout)
        return json.loads(result.stdout)

    def _acquire_free_nbd(self, purpose: str) -> str:
        """Find a free NBD device and normalize error context."""
        try:
            return self.find_free_nbd()
        except RuntimeError as exc:
            raise RuntimeError(
                f"No free NBD device available for {purpose}. "
                f"All /dev/nbd* devices are in use.\n\n"
                "Solutions:\n"
                "  1. Disconnect unused devices: sudo qemu-nbd -d /dev/nbdN\n"
                "  2. Check for stuck processes: ps aux | grep qemu-nbd\n"
                "  3. Reload with more devices: sudo rmmod nbd && sudo modprobe nbd nbds_max=32 max_part=16"
            ) from exc

    def _disconnect_nbd_quietly(self, nbd_device: str, *, context: str) -> None:
        """Best-effort NBD disconnect for cleanup paths."""
        try:
            run_sudo(self.logger, ["qemu-nbd", "--disconnect", nbd_device], check=False, capture=True)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cleanup disconnect, must not raise from a cleanup path
            self.logger.debug(f"Could not disconnect {nbd_device} ({context}): {e}")

    def _connect_temp_readonly_nbd(
        self,
        *,
        nbd_device: str,
        image_path: Path,
        fmt: str | None,
        wait_after_connect: float,
    ) -> None:
        """Connect a temporary read-only NBD device and trigger partition scan."""
        connect_cmd = ["qemu-nbd", "--read-only", "--connect", nbd_device]
        if fmt:
            connect_cmd.extend(["--format", fmt])
        connect_cmd.append(str(image_path))

        run_sudo(self.logger, connect_cmd, check=True, capture=True)
        time.sleep(wait_after_connect)  # Allow kernel to detect partitions
        run_sudo(self.logger, ["partprobe", nbd_device], check=False, capture=True)
        time.sleep(0.5)

    def _clean_lsblk_name(self, raw_line: str) -> str:
        """Normalize one lsblk NAME line by stripping tree glyphs."""
        cleaned = raw_line.strip()
        for char in ["├─", "└─", "└", "─", "├", "│"]:
            cleaned = cleaned.replace(char, "")
        return cleaned.strip()

    def _parse_lsblk_names(self, output: str) -> list[str]:
        """Parse and normalize non-empty device names from lsblk output."""
        names: list[str] = []
        for raw_line in output.splitlines():
            cleaned = self._clean_lsblk_name(raw_line)
            if cleaned:
                names.append(cleaned)
        return names

    def _parse_lsblk_partition_rows(self, output: str) -> list[dict[str, str]]:
        """Parse lsblk table output into partition entry records."""
        entries: list[dict[str, str]] = []
        for raw_line in output.splitlines()[1:]:  # Skip header row
            line = raw_line.strip()
            if not line.startswith(("├─", "└─")):
                continue

            parts = line.split()
            if not parts:
                continue

            entries.append(
                {
                    "device": self._clean_lsblk_name(parts[0]),
                    "info": " ".join(parts),
                }
            )
        return entries

    def _parse_whitespace_table_rows(self, output: str, keys: list[str]) -> list[dict[str, str]]:
        """Parse whitespace-delimited table rows into dict records."""
        rows: list[dict[str, str]] = []
        expected_len = len(keys)
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < expected_len:
                continue
            rows.append({key: parts[idx] for idx, key in enumerate(keys)})
        return rows

    def _needs_conversion(self, image_path: Path) -> bool:
        """Check if disk image needs conversion to qcow2. Delegates to DiskConverter."""
        return self._converter.needs_conversion(image_path)

    def _convert_to_qcow2(self, image_path: Path) -> Path:
        """Convert disk image to qcow2. Delegates to DiskConverter."""
        return self._converter.convert_to_qcow2(image_path)

    def _detect_layered_storage(self, raw_image: Path) -> bool:
        """Detect layered storage (LVM, mdraid, LUKS, btrfs). Delegates to DiskConverter."""
        return self._converter.detect_layered_storage(raw_image)

    def _validate_image(self, image_path: Path) -> dict[str, Any]:
        """
        Validate disk image integrity with qemu-img before attempting connection.

        Uses qemu-img check and qemu-img info to:
        1. Detect image corruption early (before NBD connection)
        2. Extract metadata (format, virtual size, backing files)
        3. Provide better error messages for invalid images

        Args:
            image_path: Path to disk image

        Returns:
            Image metadata dict from qemu-img info

        Raises:
            RuntimeError: If image is corrupted or invalid
        """
        try:
            # Step 1: Check image integrity
            self.logger.debug(f"Validating image integrity: {image_path.name}")
            check_result = run_sudo(
                self.logger,
                ["qemu-img", "check", str(image_path)],
                check=False,  # Don't raise on non-zero (some warnings are OK)
                capture=True,
                failure_log_level=logging.DEBUG,
            )

            # Parse qemu-img check output for critical errors
            # Exit code 0 = no errors, 1 = errors found, 2 = check not supported, 3 = invalid image
            if check_result.returncode == 3:
                raise RuntimeError(
                    f"Image validation failed: {image_path.name}\n"
                    f"qemu-img cannot recognize this image format.\n"
                    f"Output: {check_result.stdout}"
                )
            if check_result.returncode == 1:
                # Check if errors are critical
                stdout_lower = check_result.stdout.lower()
                if "leaked clusters" in stdout_lower or "corruptions" in stdout_lower:
                    self.logger.warning(
                        f"Image has corruption/leaks: {image_path.name}\n"
                        f"qemu-img check output: {check_result.stdout}\n"
                        f"Attempting to proceed anyway (may fail during mount)"
                    )

            # Step 2: Get image metadata
            self.logger.debug(f"Extracting image metadata: {image_path.name}")
            info_result = run_sudo(
                self.logger, ["qemu-img", "info", "--output=json", str(image_path)], check=True, capture=True
            )

            metadata = json.loads(info_result.stdout)

            self.logger.info(Convert.format_qemu_img_info_summary(metadata, path=image_path))

            # Log useful metadata
            virtual_size_gb = metadata.get("virtual-size", 0) / (1024**3)
            actual_size_gb = metadata.get("actual-size", 0) / (1024**3)
            format_name = metadata.get("format", "unknown")

            self.logger.info(
                f"✓ Image validated: {format_name} "
                f"(virtual: {virtual_size_gb:.2f} GiB, actual: {actual_size_gb:.2f} GiB)",
                extra={
                    "ctx": {
                        "event": "image_validated",
                        "format": format_name,
                        "virtual_size_gib": round(virtual_size_gb, 2),
                        "actual_size_gib": round(actual_size_gb, 2),
                        "image": str(image_path),
                    }
                },
            )

            # Warn about backing files (snapshots/linked clones)
            if "backing-filename" in metadata:
                backing = metadata["backing-filename"]
                self.logger.warning(
                    f"Image has backing file: {backing}\n"
                    f"This is a snapshot or linked clone. Ensure backing file is accessible."
                )

            return metadata

        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to parse disk image metadata for '{image_path.name}'. "
                f"The image may be corrupted or in an unsupported format. Detail: {e}"
            ) from None
        except subprocess.CalledProcessError as e:
            # Check if image is locked by another process (e.g., running VM)
            stderr = getattr(e, "stderr", "") or ""
            if (
                'Failed to get shared "write" lock' in stderr
                or "Is another process using the image" in stderr
            ):
                self.logger.warning(
                    f"Image {image_path.name} is locked by another process (possibly a running VM). "
                    "Skipping validation."
                )
                return {}  # Return empty metadata instead of raising
            raise RuntimeError(
                f"qemu-img could not read disk image '{image_path.name}'. "
                f"The image may be corrupted, locked, or in an unsupported format. "
                f"Detail: {e.stdout}"
            ) from None
        except Exception as e:
            # Check if this is a locked image error (wrapped in DeviceError or other exception types)
            error_str = str(e).lower()

            # Also check exception context (DeviceError stores stderr in context)
            stderr_context = ""
            # guarded: e may be a custom exception subclass carrying a .context dict, not builtin Exception
            if hasattr(e, "context") and isinstance(e.context, dict):  # pylint: disable=no-member
                stderr_context = str(e.context.get("stderr", "")).lower()  # pylint: disable=no-member

            # Check both error message and stderr context for lock indicators
            if (
                'failed to get shared "write" lock' in error_str
                or "is another process using the image" in error_str
                or 'failed to get shared "write" lock' in stderr_context
                or "is another process using the image" in stderr_context
            ):
                self.logger.warning(
                    f"Image {image_path.name} is locked by another process (possibly a running VM). "
                    "Skipping validation."
                )
                return {}  # Return empty metadata instead of raising
            raise RuntimeError(
                f"Disk image validation failed for '{image_path.name}'. "
                f"The image may be corrupted or inaccessible. Detail: {e}"
            ) from None

    def validate_filesystems(
        self,
        image_path: str | Path,
        *,
        fmt: str | None = None,
        check_partitions: bool = True,
        run_fsck: bool = False,
    ) -> dict[str, Any]:
        """
        Perform deep filesystem validation by temporarily connecting image via NBD.

        This performs structural validation beyond basic qemu-img checks:
        1. Attaches image via qemu-nbd
        2. Inspects partition table with lsblk
        3. Optionally runs read-only fsck on partitions

        WARNING: This is slower than basic validation and requires NBD device.
        Use for thorough pre-migration validation or troubleshooting.

        Args:
            image_path: Path to disk image
            format: Disk format hint (qcow2, vmdk, raw, etc.)
            check_partitions: Verify partition table is readable (default: True)
            run_fsck: Run read-only filesystem checks (default: False, slower)

        Returns:
            Validation report dict with partition info and fsck results

        Raises:
            RuntimeError: If validation fails or image is corrupted

        Example:
            nbd = NBDDeviceManager(logger)
            report = nbd.validate_filesystems('/vms/test.vmdk', run_fsck=True)
            print(report['partitions'])
            print(report['fsck_results'])
        """
        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Disk image not found: {image_path}")

        self.logger.info(f"Performing deep filesystem validation: {image_path.name}")

        # First do basic image validation
        metadata = self._validate_image(image_path)

        # Temporarily connect to NBD for partition inspection
        temp_nbd = None
        report = {
            "image": str(image_path),
            "format": metadata.get("format", "unknown"),
            "virtual_size_gb": metadata.get("virtual-size", 0) / (1024**3),
            "actual_size_gb": metadata.get("actual-size", 0) / (1024**3),
            "partitions": [],
            "fsck_results": [],
            "status": "unknown",
        }

        try:  # pylint: disable=too-many-nested-blocks  # walks partition/fsck results with independent status checks at each level
            # Find free NBD device
            temp_nbd = self._acquire_free_nbd("validation")

            self.logger.debug(f"Using temporary NBD device: {temp_nbd}")

            self._connect_temp_readonly_nbd(
                nbd_device=temp_nbd,
                image_path=image_path,
                fmt=fmt,
                wait_after_connect=1.0,
            )

            if check_partitions:
                # Get partition information with lsblk
                self.logger.debug("Inspecting partition table...")
                lsblk_result = run_sudo(
                    self.logger,
                    ["lsblk", "-f", "-o", "NAME,FSTYPE,SIZE,LABEL,UUID,MOUNTPOINT", temp_nbd],
                    check=True,
                    capture=True,
                )
                report["partition_table"] = lsblk_result.stdout

                partition_entries = self._parse_lsblk_partition_rows(lsblk_result.stdout)
                report["partitions"].extend(partition_entries)
                partition_devices = [f"/dev/{entry['device']}" for entry in partition_entries]

                self.logger.info(f"Found {len(partition_devices)} partitions")

                # Optionally run fsck (read-only) on partitions
                if run_fsck and partition_devices:
                    self.logger.info("Running read-only filesystem checks (fsck -n)...")
                    for part_dev in partition_devices:
                        if not Path(part_dev).exists():
                            continue

                        try:
                            fsck_result = run_sudo(
                                self.logger,
                                ["fsck", "-n", part_dev],  # -n = read-only, no fixes
                                check=False,  # fsck may return non-zero even for clean FS
                                capture=True,
                                failure_log_level=logging.DEBUG,
                            )

                            status = "clean" if fsck_result.returncode == 0 else "errors_found"
                            report["fsck_results"].append(
                                {
                                    "partition": part_dev,
                                    "status": status,
                                    "exit_code": fsck_result.returncode,
                                    "output": fsck_result.stdout[:500],  # Truncate long output
                                }
                            )

                            if status == "errors_found":
                                self.logger.warning(
                                    f"Filesystem errors detected on {part_dev}:\n{fsck_result.stdout[:200]}"
                                )
                            else:
                                self.logger.debug(f"Filesystem check passed: {part_dev}")

                        # per-partition fsck probe; one partition's failure must not abort the scan
                        except Exception as e:  # pylint: disable=broad-exception-caught
                            self.logger.debug(f"Could not check {part_dev}: {e}")
                            report["fsck_results"].append(
                                {"partition": part_dev, "status": "check_failed", "error": str(e)}
                            )

            report["status"] = "validated"
            self.logger.info(
                f"✓ Deep validation completed for {image_path.name}",
                extra={
                    "ctx": {
                        "event": "deep_validation_complete",
                        "image": str(image_path),
                        "partitions_found": len(report["partitions"]),
                        "fsck_results_count": len(report["fsck_results"]),
                    }
                },
            )

        except Exception as e:
            report["status"] = "validation_failed"
            report["error"] = str(e)
            self.logger.exception(f"Deep validation failed: {e}")
            raise RuntimeError(
                f"Filesystem validation failed for '{image_path.name}'. "
                f"The disk image filesystems may be corrupted or use unsupported types. Detail: {e}"
            ) from e

        finally:
            # Always disconnect
            if temp_nbd:
                self._disconnect_nbd_quietly(temp_nbd, context="validation")
                self.logger.debug(f"Disconnected validation NBD: {temp_nbd}")

        return report

    def inspect_disk(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # comprehensive inspection covers partitions, LVM, filesystems, and fsck in one pass
        self,
        image_path: str | Path,
        *,
        fmt: str | None = None,
        check_lvm: bool = True,
        activate_lvm: bool = True,
        run_fsck: bool = False,
    ) -> dict[str, Any]:
        """
        Perform comprehensive disk image inspection including LVM structures.

        This provides deeper inspection than validate_filesystems, including:
        - Full LVM structure analysis (PVs, VGs, LVs)
        - LVM activation and logical volume detection
        - Partition table details
        - Filesystem detection on both partitions and LVs
        - Optional filesystem integrity checks

        Args:
            image_path: Path to disk image
            fmt: Disk format hint (qcow2, vmdk, raw, etc.)
            check_lvm: Detect and analyze LVM structures
            activate_lvm: Activate LVM volume groups to see LVs
            run_fsck: Run read-only filesystem checks

        Returns:
            Comprehensive inspection report dict

        Raises:
            RuntimeError: If inspection fails

        Example:
            nbd = NBDDeviceManager(logger)
            report = nbd.inspect_disk(
                '/vms/disk.vmdk',
                check_lvm=True,
                activate_lvm=True,
                run_fsck=True
            )
            print(f"Partitions: {len(report['partitions'])}")
            print(f"LVM VGs: {len(report['lvm']['volume_groups'])}")
            print(f"LVM LVs: {len(report['lvm']['logical_volumes'])}")
        """
        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Disk image not found: {image_path}")

        self.logger.info(f"Performing comprehensive disk inspection: {image_path.name}")

        # First do basic image validation
        metadata = self._validate_image(image_path)

        # Temporarily connect to NBD for deep inspection
        temp_nbd = None
        report = {
            "image": str(image_path),
            "format": metadata.get("format", "unknown"),
            "virtual_size_gb": metadata.get("virtual-size", 0) / (1024**3),
            "actual_size_gb": metadata.get("actual-size", 0) / (1024**3),
            "partitions": [],
            "lvm": {"physical_volumes": [], "volume_groups": [], "logical_volumes": []},
            "filesystems": [],
            "fsck_results": [],
            "status": "unknown",
        }

        try:  # pylint: disable=too-many-nested-blocks  # walks LVM/partition/filesystem results with independent status checks at each level
            # Find free NBD device (use existing auto-detection)
            temp_nbd = self._acquire_free_nbd("inspection")

            self.logger.debug(f"Using NBD device: {temp_nbd}")

            self._connect_temp_readonly_nbd(
                nbd_device=temp_nbd,
                image_path=image_path,
                fmt=fmt,
                wait_after_connect=2.0,
            )

            # Get partition information
            self.logger.debug("Inspecting partition table...")
            lsblk_result = run_sudo(
                self.logger,
                ["lsblk", "-f", "-o", "NAME,FSTYPE,SIZE,LABEL,UUID", temp_nbd],
                check=True,
                capture=True,
            )

            report["partitions"].extend(self._parse_lsblk_partition_rows(lsblk_result.stdout))

            self.logger.info(f"Found {len(report['partitions'])} partitions")

            # LVM inspection
            if check_lvm:
                self.logger.debug("Scanning for LVM structures...")

                # Physical Volumes
                try:
                    pvs_result = run_sudo(
                        self.logger,
                        ["pvs", "--noheadings", "-o", "pv_name,vg_name,pv_size"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                    )
                    report["lvm"]["physical_volumes"].extend(
                        self._parse_whitespace_table_rows(
                            pvs_result.stdout,
                            ["pv", "vg", "size"],
                        )
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort LVM scan step, must not abort the whole inspection
                    self.logger.debug(f"PV scan failed: {e}")

                # Volume Groups
                try:
                    vgs_result = run_sudo(
                        self.logger,
                        ["vgs", "--noheadings", "-o", "vg_name,pv_count,lv_count,vg_size"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                    )
                    report["lvm"]["volume_groups"].extend(
                        self._parse_whitespace_table_rows(
                            vgs_result.stdout,
                            ["vg", "pv_count", "lv_count", "size"],
                        )
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort LVM scan step, must not abort the whole inspection
                    self.logger.debug(f"VG scan failed: {e}")

                # Activate VGs if requested
                if activate_lvm and report["lvm"]["volume_groups"]:
                    self.logger.debug("Activating LVM volume groups...")
                    try:
                        # pylint: disable=duplicate-code
                        # reason: the udevadm-settle call below mirrors
                        # h2kvm/vmcraft/storage.py's _settle_udev --
                        # structurally similar by coincidence, not shared
                        # logic; keeping independent avoids coupling two
                        # unrelated storage-activation code paths.
                        run_sudo(
                            self.logger,
                            ["vgchange", "-ay"],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG,
                        )
                        time.sleep(DELAY_STATUS_POLL)  # Wait for device nodes

                        # Ensure device nodes are created
                        run_sudo(
                            self.logger,
                            ["dmsetup", "mknodes"],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG,
                        )
                        run_sudo(
                            self.logger,
                            ["udevadm", "settle"],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG,
                        )

                        self.logger.info(f"Activated {len(report['lvm']['volume_groups'])} volume groups")
                    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort LVM activation step, must not abort the whole inspection
                        self.logger.debug(f"VG activation failed: {e}")

                # Logical Volumes
                try:
                    lvs_result = run_sudo(
                        self.logger,
                        ["lvs", "--noheadings", "-o", "lv_name,lv_path,lv_size,vg_name"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                    )
                    report["lvm"]["logical_volumes"].extend(
                        self._parse_whitespace_table_rows(
                            lvs_result.stdout,
                            ["lv", "path", "size", "vg"],
                        )
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort LVM scan step, must not abort the whole inspection
                    self.logger.debug(f"LV scan failed: {e}")

                self.logger.info(
                    f"LVM: {len(report['lvm']['physical_volumes'])} PVs, "
                    f"{len(report['lvm']['volume_groups'])} VGs, "
                    f"{len(report['lvm']['logical_volumes'])} LVs"
                )

            # Detect filesystems on all block devices
            self.logger.debug("Detecting filesystems...")
            max_filesystems = 1000  # Sanity limit to prevent OOM on pathological disks
            try:
                blkid_result = run_sudo(
                    self.logger, ["blkid"], check=False, capture=True, failure_log_level=logging.DEBUG
                )

                for line in blkid_result.stdout.splitlines():
                    if ":" in line:
                        device = line.split(":")[0]
                        # Check if this device is related to our NBD or LVM
                        if temp_nbd in device or "/dev/mapper/" in device or "/dev/dm-" in device:
                            # Extract filesystem type
                            fstype = ""
                            if 'TYPE="' in line:
                                fstype = line.split('TYPE="')[1].split('"')[0]

                            if fstype and fstype != "LVM2_member":
                                # Check limit to prevent OOM
                                if len(report["filesystems"]) >= max_filesystems:
                                    self.logger.warning(
                                        f"Filesystem list truncated at {max_filesystems} entries "
                                        f"(sanity limit to prevent memory exhaustion)"
                                    )
                                    break

                                report["filesystems"].append({"device": device, "fstype": fstype})

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort filesystem scan step, must not abort the whole inspection
                self.logger.debug(f"Filesystem detection failed: {e}")

            self.logger.info(f"Found {len(report['filesystems'])} filesystems")

            # Optional filesystem checks
            if run_fsck and report["filesystems"]:
                self.logger.info("Running read-only filesystem checks...")
                for fs in report["filesystems"]:
                    device = fs["device"]
                    fstype = fs["fstype"]

                    # Skip certain filesystem types
                    if fstype in ["swap", "crypto_LUKS"]:
                        continue

                    try:
                        fsck_result = run_sudo(
                            self.logger,
                            ["fsck", "-n", device],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG,
                        )

                        status = "clean" if fsck_result.returncode == 0 else "errors_found"
                        report["fsck_results"].append(
                            {
                                "device": device,
                                "fstype": fstype,
                                "status": status,
                                "exit_code": fsck_result.returncode,
                                "output": fsck_result.stdout[:500] if fsck_result.stdout else "",
                            }
                        )

                        if status == "clean":
                            self.logger.debug(f"Filesystem check passed: {device}")
                        else:
                            self.logger.warning(
                                f"Filesystem errors on {device} (exit: {fsck_result.returncode})"
                            )

                    except Exception as e:  # pylint: disable=broad-exception-caught  # per-filesystem fsck probe; one filesystem's failure must not abort the scan
                        self.logger.debug(f"Could not check {device}: {e}")

            report["status"] = "inspected"
            self.logger.info(
                f"✓ Comprehensive inspection completed for {image_path.name}",
                extra={
                    "ctx": {
                        "event": "disk_inspection_complete",
                        "image": str(image_path),
                        "partitions": len(report["partitions"]),
                        "pvs": len(report["lvm"]["physical_volumes"]),
                        "vgs": len(report["lvm"]["volume_groups"]),
                        "lvs": len(report["lvm"]["logical_volumes"]),
                        "filesystems": len(report["filesystems"]),
                    }
                },
            )

        except Exception as e:
            report["status"] = "inspection_failed"
            report["error"] = str(e)
            self.logger.exception(f"Disk inspection failed: {e}")
            raise RuntimeError(
                f"Disk inspection failed for '{image_path.name}'. "
                f"Could not analyze partitions, LVM, or filesystems on the image. Detail: {e}"
            ) from e

        finally:
            # Cleanup: deactivate only LVM VGs found on this NBD device
            if activate_lvm and check_lvm and report.get("lvm", {}).get("volume_groups"):
                try:
                    vgs_to_deactivate = [vg["vg"] for vg in report["lvm"]["volume_groups"]]
                    self.logger.debug(f"Deactivating LVM volume groups: {vgs_to_deactivate}")
                    for vg_name in vgs_to_deactivate:
                        try:
                            run_sudo(
                                self.logger,
                                ["vgchange", "-an", vg_name],
                                check=False,
                                capture=True,
                                failure_log_level=logging.DEBUG,
                            )
                            self.logger.debug(f"  Deactivated VG: {vg_name}")
                        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort VG teardown in a finally block, must not raise
                            self.logger.debug(f"  Could not deactivate VG {vg_name}: {e}")
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort VG teardown in a finally block, must not raise
                    self.logger.debug(f"VG deactivation warning: {e}")

            if temp_nbd:
                self._disconnect_nbd_quietly(temp_nbd, context="inspection")
                self.logger.debug(f"Disconnected inspection NBD: {temp_nbd}")

        return report

    # ── Format auto-detection ──────────────────────────────────────────

    _FORMAT_MAP = {
        ".vmdk": "vmdk",
        ".qcow2": "qcow2",
        ".qcow": "qcow2",
        ".vdi": "vdi",
        ".vhd": "vpc",
        ".vhdx": "vhdx",
        ".img": "raw",
        ".raw": "raw",
    }

    def _resolve_and_validate_path(self, image_path: str | Path) -> Path:
        """Resolve image path and run security validation."""
        try:
            resolved = Path(image_path).resolve(strict=True)
        except (RuntimeError, OSError, ValueError) as e:
            error_msg = str(e).lower()
            if "loop" in error_msg or "recursive" in error_msg:
                raise ValueError(
                    f"Symlink loop detected in image path: {image_path}\n"
                    f"This may be a malicious disk image. Refusing to proceed."
                ) from e
            if "no such file" in error_msg or "not found" in error_msg:
                raise FileNotFoundError(f"Disk image not found: {image_path}") from e
            raise ValueError(
                f"Invalid disk image path '{image_path}'. "
                f"Ensure the path is absolute and the file exists. Detail: {e}"
            ) from e

        # Security validation removed — path is already verified by the caller
        # (web UI file browser, CLI arg parser, or orchestrator).
        return resolved

    def _convert_if_needed(self, image_path: Path, fmt: str | None) -> tuple[Path, str | None]:
        """Convert VMDK to qcow2 if needed. Returns (working_path, format)."""
        if self._needs_conversion(image_path):
            original = image_path
            converted = self._convert_to_qcow2(image_path)
            self._converted_qcow2_path = converted
            self.logger.info(f"Using converted qcow2 instead of original {original.name}")
            return converted, "qcow2"
        return image_path, fmt

    def _auto_detect_format(self, image_path: Path, fmt: str | None) -> str | None:
        """Auto-detect disk format from extension if not specified."""
        if fmt:
            return fmt
        detected = self._FORMAT_MAP.get(image_path.suffix.lower())
        if detected:
            self.logger.info(f"Auto-detected format '{detected}' from extension '{image_path.suffix}'")
        return detected

    @property
    def socket_path(self) -> Path | None:
        """Return the UNIX socket path if connected in socket mode, else None."""
        return self._socket_path

    def _connect_via_socket(
        self,
        image_path: Path,
        fmt: str | None,
        readonly: bool,
    ) -> str:
        """
        Connect image via qemu-nbd UNIX socket (no kernel NBD module needed).

        Starts ``qemu-nbd`` in daemon mode listening on a UNIX socket at
        ``/run/h2kvm/nbd-{image_stem}.sock``.  The socket can be used
        with ``nbdkit``, ``libnbd``, or ``qemu`` directly.

        Args:
            image_path: Path to the disk image.
            fmt: Disk format hint (qcow2, vmdk, raw, etc.).
            readonly: Mount image read-only.

        Returns:
            UNIX socket path as a string.

        Raises:
            RuntimeError: If the socket server fails to start.
        """
        socket_dir = Path("/run/h2kvm")
        socket_dir.mkdir(parents=True, exist_ok=True)

        sock = socket_dir / f"nbd-{image_path.stem}.sock"

        # Remove stale socket if present
        sock.unlink(missing_ok=True)

        cmd = ["qemu-nbd", "--socket", str(sock), "--fork", "--pid-file", "/dev/null"]
        if fmt:
            cmd.extend(["--format", fmt])
        if readonly:
            cmd.append("--read-only")
        cmd.extend(["--cache", "none", "--aio", "native", "--discard", "unmap"])
        cmd.append(str(image_path))

        self.logger.info(
            f"Starting qemu-nbd socket server: {sock}",
            extra={
                "ctx": {
                    "event": "nbd_socket_start",
                    "image": str(image_path),
                    "socket": str(sock),
                    "readonly": readonly,
                }
            },
        )

        run_sudo(self.logger, cmd, check=True, capture=True)

        # Wait for the socket to appear
        start = time.time()
        while time.time() - start < 5.0:
            if sock.exists():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(
                f"qemu-nbd socket did not appear at {sock} within 5 seconds. "
                f"qemu-nbd may have crashed or failed to start — check system logs (journalctl -xe)."
            )

        self._socket_path = sock
        self._connected = True
        self.logger.info(
            f"UNIX socket NBD ready: {sock}",
            extra={
                "ctx": {
                    "event": "nbd_socket_ready",
                    "socket": str(sock),
                    "image": str(image_path),
                }
            },
        )
        return str(sock)

    def _disconnect_socket(self) -> None:
        """Disconnect a UNIX-socket-mode qemu-nbd server."""
        if not self._socket_path:
            return

        self.logger.info(f"Stopping qemu-nbd socket server: {self._socket_path}")

        # Find and kill the qemu-nbd process listening on this socket
        try:
            result = subprocess.run(
                ["fuser", str(self._socket_path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for pid_str in result.stdout.split():
                pid_str = pid_str.strip()
                if pid_str.isdigit():
                    os.kill(int(pid_str), 15)  # SIGTERM
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort socket-server teardown, must not raise from cleanup
            self.logger.debug(f"fuser on socket: {e}")

        # Remove socket file
        try:
            self._socket_path.unlink(missing_ok=True)
        except OSError as e:
            self.logger.debug(f"Socket cleanup: {e}")

        self._socket_path = None

    def _build_nbd_command(
        self, nbd_device: str, image_path: Path, fmt: str | None, readonly: bool
    ) -> list[str]:
        """Build the qemu-nbd connect command."""
        cmd = ["qemu-nbd", "--connect", nbd_device]
        if fmt:
            cmd.extend(["--format", fmt])
        else:
            self.logger.warning(
                f"No format specified and couldn't auto-detect from '{image_path.suffix}' "
                "- qemu-nbd will try to auto-detect"
            )
        if readonly:
            cmd.append("--read-only")
        cmd.extend(["--cache", "none", "--aio", "native", "--discard", "unmap"])
        cmd.append(str(image_path))
        return cmd

    def _wait_for_device_ready(self, nbd_device: str, max_wait: float = 5.0) -> None:
        """Wait for NBD device to become ready after connection."""
        start = time.time()
        while time.time() - start < max_wait:
            if not self._is_nbd_free(nbd_device):
                return
            time.sleep(0.1)
        raise RuntimeError(
            f"NBD device {nbd_device} did not become ready after {max_wait}s.\n\n"
            "Possible causes:\n"
            "  - The disk image is locked by a running VM or another qemu-nbd process\n"
            "  - qemu-nbd failed to attach (check: journalctl -xe for details)\n"
            "  - The disk image format is not recognized by qemu-nbd\n\n"
            "Try:\n"
            "  - Stop any VMs using this disk image\n"
            "  - Specify the format explicitly: --format qcow2 (or vmdk, raw, vhd)\n"
            f"  - Manually disconnect and retry: sudo qemu-nbd -d {nbd_device}"
        )

    @staticmethod
    def _is_image_locked_error(e: Exception) -> bool:
        """Check if an exception indicates the image is locked by another process."""
        indicators = ('failed to get shared "write" lock', "is another process using the image")
        error_str = str(e).lower()
        stderr = (getattr(e, "stderr", "") or "").lower()
        stderr_ctx = ""
        # guarded: e may be a custom exception subclass carrying a .context dict, not builtin Exception
        if hasattr(e, "context") and isinstance(e.context, dict):  # pylint: disable=no-member
            stderr_ctx = str(e.context.get("stderr", "")).lower()  # pylint: disable=no-member
        return any(ind in src for ind in indicators for src in (error_str, stderr, stderr_ctx))

    def _handle_connect_error(self, e: Exception, nbd_device: str, image_path: Path) -> None:
        """Handle connection errors with cleanup and helpful messages."""
        # Release the device lock acquired by find_free_nbd() to prevent leak
        self._release_device_lock(nbd_device)

        if self._is_image_locked_error(e):
            self._disconnect_nbd_quietly(nbd_device, context="connect failure - image locked")
            self.logger.warning(f"Cannot connect to {image_path.name}: Image is locked by another process")
            raise RuntimeError(
                f"Image {image_path.name} is locked by another process. "
                "Please stop the VM before attempting to mount the image."
            ) from None

        self._disconnect_nbd_quietly(nbd_device, context="connect failure")

        error_str = str(e).lower()
        if "invalid VMDK image descriptor" in error_str:
            if str(image_path).endswith("-flat.vmdk"):
                raise RuntimeError(
                    f"Cannot open '{image_path}': This is a VMDK data file (-flat.vmdk).\n"
                    f"You need the descriptor file (without -flat suffix).\n"
                    f"Expected file: {str(image_path).replace('-flat.vmdk', '.vmdk')}"
                ) from None
            raise RuntimeError(
                f"Invalid VMDK descriptor in '{image_path}'.\n"
                f"The VMDK descriptor file may be corrupted or in an unsupported format."
            ) from None

    # ── Main connect method ──────────────────────────────────────────

    @retry_with_backoff(
        max_attempts=3,
        base_backoff_s=2.0,
        max_backoff_s=10.0,
        exceptions=(subprocess.CalledProcessError, OSError),
        logger=logger,
        log_level=logging.WARNING,
    )
    # `format` is this method's established public keyword arg; callers pass it by name
    def connect(  # pylint: disable=redefined-builtin
        self,
        image_path: str | Path,
        *,
        format: str | None = None,
        readonly: bool | None = None,
    ) -> str:
        """
        Connect disk image to NBD device with automatic retry on transient failures.

        Pipeline: validate path → validate image → convert if needed →
        detect format → acquire device → attach → scan partitions.

        Args:
            image_path: Path to disk image
            format: Disk format (qcow2, vmdk, raw, etc.). Auto-detected if None.
            readonly: Override instance readonly setting

        Returns:
            Path to connected NBD device (e.g., /dev/nbd0)

        Raises:
            RuntimeError: If connection fails after all retry attempts
        """
        if self._connected:
            raise RuntimeError("Already connected to an NBD device. Disconnect first.")

        self.logger.debug(
            "NBD connect: image=%s, format=%s, readonly=%s, use_socket=%s",
            image_path,
            format,
            readonly,
            self.use_socket,
        )

        # Stage 1: Resolve, validate, and prepare
        image_path = self._resolve_and_validate_path(image_path)
        self._validate_image(image_path)
        readonly = readonly if readonly is not None else self.readonly

        # Stage 2: Convert if needed (streamOptimized VMDK)
        image_path, format = self._convert_if_needed(image_path, format)

        # Stage 3: Detect format
        format = self._auto_detect_format(image_path, format)
        self.logger.debug(
            "NBD connect after prep: image=%s, format=%s, readonly=%s",
            image_path,
            format,
            readonly,
        )

        # Socket mode: skip kernel NBD entirely
        if self.use_socket:
            return self._connect_via_socket(image_path, format, readonly)

        # Stage 4: Acquire device and connect
        nbd_device = self.find_free_nbd()
        cmd = self._build_nbd_command(nbd_device, image_path, format, readonly)

        try:
            self.logger.info(
                f"Connecting {image_path} to {nbd_device}...",
                extra={
                    "ctx": {
                        "event": "nbd_connect_start",
                        "image": str(image_path),
                        "nbd_device": nbd_device,
                        "format": format,
                        "readonly": readonly,
                    }
                },
            )
            run_sudo(self.logger, cmd, check=True, capture=True)
            self._wait_for_device_ready(nbd_device)

            self._nbd_device = nbd_device
            self._connected = True
            self._scan_partitions(nbd_device)

            self.logger.info(
                f"Successfully connected to {nbd_device}",
                extra={
                    "ctx": {
                        "event": "nbd_connect_complete",
                        "image": str(image_path),
                        "nbd_device": nbd_device,
                        "format": format,
                        "readonly": readonly,
                    }
                },
            )
            log_event("nbd_device_connected", nbd_device=nbd_device, image=str(image_path), format=format)
            return nbd_device

        except (subprocess.CalledProcessError, OSError) as e:
            log_event(
                "nbd_connect_failed",
                level="error",
                nbd_device=nbd_device,
                image=str(image_path),
                error=str(e),
            )
            self._handle_connect_error(e, nbd_device, image_path)
            raise  # Re-raise for retry decorator
        except Exception as e:
            log_event(
                "nbd_connect_failed",
                level="error",
                nbd_device=nbd_device,
                image=str(image_path),
                error=str(e),
            )
            self._handle_connect_error(e, nbd_device, image_path)
            raise RuntimeError(
                f"Failed to connect disk image to NBD device. "
                f"Ensure qemu-nbd is installed, the nbd kernel module is loaded (modprobe nbd), "
                f"and the disk image is not locked by another process. Detail: {e}"
            ) from e

    def _scan_partitions(self, nbd_device: str) -> None:
        """
        Trigger partition table scan.

        Uses partprobe to make kernel re-read partition table.
        Falls back to kpartx if partprobe unavailable.
        """
        try:
            # First try partprobe (simpler)
            run_sudo(self.logger, ["partprobe", nbd_device], check=False, capture=True)
            time.sleep(0.5)  # Give kernel time to create partition devices

            # Verify partitions were created by checking for partition devices
            # This is especially important for non-sequential partition layouts (e.g., Photon OS)
            max_retries = 3
            for attempt in range(max_retries):
                result = run_sudo(
                    self.logger, ["lsblk", "-n", "-o", "NAME", nbd_device], check=False, capture=True
                )
                if result.stdout:
                    lines = self._parse_lsblk_names(result.stdout)
                    # If we have more than just the main device, partitions exist
                    if len(lines) > 1:
                        self.logger.debug(f"Partitions verified after {attempt + 1} attempt(s)")
                        break

                if attempt < max_retries - 1:
                    self.logger.debug(
                        f"Waiting for partitions to appear (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(0.3)
        except Exception:  # pylint: disable=broad-exception-caught  # partition-scan probe failure falls back to kpartx, must not abort connect
            # Fallback to kpartx if available
            try:
                run_sudo(self.logger, ["kpartx", "-a", nbd_device], check=False, capture=True)
                time.sleep(0.5)
            except Exception:  # pylint: disable=broad-exception-caught  # last-resort fallback; if both scans fail, partitions might still work
                # If both fail, partitions might still work
                pass

    def get_partitions(self, nbd_device: str | None = None) -> list[str]:
        """
        Get list of partition devices for NBD device.

        Args:
            nbd_device: NBD device path. Uses connected device if None.

        Returns:
            List of partition device paths (e.g., ['/dev/nbd0p1', '/dev/nbd0p2'])
        """
        if nbd_device is None:
            if not self._connected or not self._nbd_device:
                raise RuntimeError(
                    "No NBD device connected. Call connect() before performing disk operations."
                )
            nbd_device = self._nbd_device

        # Use lsblk to find partitions
        try:
            cmd = ["lsblk", "-n", "-o", "NAME", nbd_device]
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            partitions = []
            nbd_name = Path(nbd_device).name
            for line in self._parse_lsblk_names(result.stdout):
                if line and line != nbd_name:
                    # Check if this is an LVM logical volume (contains hyphen but doesn't start with NBD device name)
                    # LVM volumes appear in lsblk as "vgname-lvname" (e.g., "cs-root", "fedora-root")
                    # They need /dev/mapper/ prefix, not /dev/
                    if "-" in line and not line.startswith(nbd_name):
                        # LVM logical volume: /dev/mapper/vgname-lvname
                        partitions.append(f"/dev/mapper/{line}")
                        self.logger.debug(
                            f"Detected LVM volume in partition list: {line} -> /dev/mapper/{line}"
                        )
                    else:
                        # Regular partition (e.g., nbd0p1)
                        partitions.append(f"/dev/{line}")

            return partitions

        except Exception as e:  # pylint: disable=broad-exception-caught  # partition-listing probe, must not raise from a read-only inspection helper
            self.logger.warning(f"Failed to list partitions: {e}")
            return []

    def disconnect(  # pylint: disable=too-many-branches,too-many-statements  # tears down socket/kernel NBD, converted temp files, and locks with independent fallbacks
        self, nbd_device: str | None = None
    ) -> None:
        """
        Disconnect NBD device.

        Args:
            nbd_device: Device to disconnect. Uses connected device if None.

        Raises:
            ValueError: If trying to disconnect a different device than the connected one
        """
        self.logger.debug(
            "NBD disconnect: nbd_device=%s, connected=%s, socket_path=%s",
            nbd_device or self._nbd_device,
            self._connected,
            self._socket_path,
        )

        # Socket mode disconnect
        if self._socket_path:
            self._disconnect_socket()
            self._connected = False
            # Clean up converted qcow2 if needed
            if self._converted_qcow2_path and self._converted_qcow2_path.exists():
                if self._keep_converted:
                    self.logger.info(f"Keeping converted qcow2: {self._converted_qcow2_path}")
                else:
                    try:
                        self._converted_qcow2_path.unlink()
                    except OSError as e:
                        self.logger.warning(f"Failed to remove temp qcow2: {e}")
                    if not self._keep_converted:
                        self._converted_qcow2_path = None
            return

        if nbd_device is None:
            # Using instance device - check if we're actually connected
            if not self._connected:
                self.logger.debug("disconnect() called but not connected - nothing to do")
                return
            nbd_device = self._nbd_device

        if not nbd_device:
            return

        # Safety: If user provided explicit device, ensure it matches our connected device
        if self._nbd_device and nbd_device != self._nbd_device:
            raise ValueError(
                f"Cannot disconnect {nbd_device}: currently connected to {self._nbd_device}. "
                f"Disconnect {self._nbd_device} first or call disconnect() without arguments."
            )

        try:
            self.logger.info(
                f"Disconnecting {nbd_device}...",
                extra={"ctx": {"event": "nbd_disconnect_start", "nbd_device": nbd_device}},
            )
            run_sudo(self.logger, ["qemu-nbd", "--disconnect", nbd_device], check=False, capture=True)

            # Wait for disconnect to complete
            max_wait = 3
            start = time.time()
            while time.time() - start < max_wait:
                if self._is_nbd_free(nbd_device):
                    break
                time.sleep(0.1)

            self.logger.info(
                f"Disconnected {nbd_device}",
                extra={"ctx": {"event": "nbd_disconnect_complete", "nbd_device": nbd_device}},
            )
            log_event("nbd_device_disconnected", nbd_device=nbd_device)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort disconnect, must not raise from a cleanup path
            log_event("nbd_disconnect_failed", level="warning", nbd_device=nbd_device, error=str(e))
            self.logger.warning(f"Error disconnecting {nbd_device}: {e}")
        finally:
            # Clean up temporary converted qcow2 if it exists (unless marked to keep)
            if self._converted_qcow2_path and self._converted_qcow2_path.exists():
                if self._keep_converted:
                    self.logger.info(f"Keeping converted qcow2: {self._converted_qcow2_path}")
                else:
                    try:
                        self.logger.info(f"Removing temporary converted qcow2: {self._converted_qcow2_path}")
                        self._converted_qcow2_path.unlink()
                        self.logger.info(f"✓ Cleaned up {self._converted_qcow2_path.name}")
                    except OSError as cleanup_error:
                        self.logger.warning(f"Failed to remove temp qcow2: {cleanup_error}")

            # Release device lock
            if nbd_device:
                self._release_device_lock(nbd_device)

            self._nbd_device = None
            self._connected = False
            self._nbd_process = None
            if not self._keep_converted:
                self._converted_qcow2_path = None

    def _emergency_cleanup(self) -> None:
        """
        Emergency cleanup handler called on process exit.

        This handles cleanup when the process is terminated unexpectedly,
        ensuring temp files don't accumulate and NBD devices are disconnected.

        Registered via atexit in __init__.
        """
        try:
            # Socket mode cleanup
            if self._socket_path:
                try:
                    self._disconnect_socket()
                except Exception:  # pylint: disable=broad-exception-caught  # atexit handler, must not raise during process exit
                    pass

            # Try to disconnect NBD device if still connected
            if self._connected and self._nbd_device:
                try:
                    # Use run_sudo directly to avoid logging overhead during emergency cleanup
                    subprocess.run(
                        ["sudo", "qemu-nbd", "--disconnect", self._nbd_device]
                        if os.geteuid() != 0
                        else ["qemu-nbd", "--disconnect", self._nbd_device],
                        check=False,
                        capture_output=True,
                        timeout=5,
                    )
                except Exception:  # pylint: disable=broad-exception-caught  # atexit handler, must not raise during process exit
                    pass  # Best effort - process is exiting anyway

            # Clean up temp converted qcow2 if exists and not marked to keep
            if (
                self._converted_qcow2_path
                and not self._keep_converted
                and self._converted_qcow2_path.exists()
            ):
                try:
                    self._converted_qcow2_path.unlink()
                except Exception:  # pylint: disable=broad-exception-caught  # atexit handler, must not raise during process exit
                    pass  # Best effort

            # Release all device locks
            for device in list(self._device_locks.keys()):
                try:
                    self._release_device_lock(device)
                except Exception:  # pylint: disable=broad-exception-caught  # atexit handler, must not raise during process exit
                    pass  # Best effort

        except Exception:  # pylint: disable=broad-exception-caught
            # atexit handlers must not raise exceptions
            pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        try:
            self.disconnect()
        except Exception as e:  # pylint: disable=broad-exception-caught  # context-manager exit cleanup, must not raise over the caller's real exception
            self.logger.exception(f"Error during NBD cleanup: {e}")
        return False
