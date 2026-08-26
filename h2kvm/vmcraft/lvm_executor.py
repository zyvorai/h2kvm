# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# pylint: disable=too-many-lines  # cohesive parallel/isolated LVM executor; splitting would fragment safety logic
"""
Enterprise LVM Executor for parallel, host-isolated LVM operations.

Runs multiple LVM operations (UUID regeneration, VG manipulation, filesystem
fixes) across many disk images concurrently without ever touching host LVM.

Two execution modes:

    Direct mode (default):
        Python callback receives an isolated ``LVM`` instance with per-job
        LVM_SYSTEM_DIR and device filter.  All LVM commands run on the host
        but are restricted to the assigned NBD device.

    Podman mode (``podman_image`` set):
        A shell script runs inside a Podman container that gets the NBD
        device and its partitions, private ``/etc/lvm`` (with device filter
        baked into ``lvm.conf``), and private ``/var/lib/lvm`` + ``/run/lvm``
        tmpfs mounts.  No ``--privileged`` — only targeted capabilities.

Safety guarantees:
    * Strict device filter regex — anchored to exact device + pN partitions
    * ``global_filter`` + ``udev_sync=0`` — no udev auto-activation
    * LVM_SYSTEM_DIR per job (PID + thread ID) — no host cache pollution
    * File lock per NBD device — no cross-process allocation collision
    * Stale NBD recovery on startup — dead qemu-nbd processes cleaned up
    * Per-job hard timeout — hung callbacks forcibly reported
    * Podman mode — no --privileged, targeted caps, --network=none
    * Image path validated before NBD slot allocation

Example (direct mode):
    from h2kvm.vmcraft.lvm_executor import LVMExecutor, LVMJob

    def regen_uuids(lvm, nbd_device, job):
        for vg in lvm.vgs():
            lvm.vgchange_uuid(vg)

    executor = LVMExecutor(max_workers=4)
    results = executor.run([
        LVMJob(image_path="/images/vm1.qcow2", operation=regen_uuids),
        LVMJob(image_path="/images/vm2.qcow2", operation=regen_uuids),
    ])

Example (Podman mode):
    executor = LVMExecutor(max_workers=4, podman_image="fedora:latest")
    results = executor.run([
        LVMJob(
            image_path="/images/vm1.qcow2",
            script="vgscan && vgs",
        ),
    ])
"""

from __future__ import annotations

import fcntl
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .lvm import LVM

logger = logging.getLogger(__name__)

# Default hard timeout for a single job (seconds).
DEFAULT_JOB_TIMEOUT = 900


def _install_container_runtime(log: logging.Logger) -> str:
    """Auto-install podman (preferred) or docker via system package manager.

    Tries each known package manager in order until one succeeds.
    Requires root — the tool already runs as root for NBD/LVM operations.

    Returns:
        Name of the installed runtime command (``"podman"`` or ``"docker"``).

    Raises:
        RuntimeError: If installation fails with every package manager.
    """
    pkg_managers: list[tuple[str, list[list[str]]]] = [
        ("dnf", [["dnf", "install", "-y", "podman"]]),
        ("yum", [["yum", "install", "-y", "podman"]]),
        ("apt-get", [["apt-get", "update", "-y"], ["apt-get", "install", "-y", "podman"]]),
        ("zypper", [["zypper", "install", "-y", "podman"]]),
        ("pacman", [["pacman", "-S", "--noconfirm", "podman"]]),
    ]
    docker_pkg_managers: list[tuple[str, list[list[str]]]] = [
        ("dnf", [["dnf", "install", "-y", "docker"]]),
        ("yum", [["yum", "install", "-y", "docker"]]),
        ("apt-get", [["apt-get", "update", "-y"], ["apt-get", "install", "-y", "docker.io"]]),
        ("zypper", [["zypper", "install", "-y", "docker"]]),
        ("pacman", [["pacman", "-S", "--noconfirm", "docker"]]),
    ]

    errors: list[str] = []

    # Try podman first (preferred — daemonless)
    for mgr_name, cmds in pkg_managers:
        if not shutil.which(mgr_name):
            continue
        log.info(
            "No container runtime found; installing podman via %s ...",
            mgr_name,
            extra={
                "ctx": {"event": "container_runtime_install", "runtime": "podman", "pkg_manager": mgr_name}
            },
        )
        try:
            for cmd in cmds:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            if shutil.which("podman"):
                log.info(
                    "Successfully installed podman via %s",
                    mgr_name,
                    extra={"ctx": {"event": "container_runtime_installed", "runtime": "podman"}},
                )
                return "podman"
            errors.append(f"{mgr_name}: podman installed but binary not found in PATH")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{mgr_name}/podman: {exc}")
            log.debug("podman install via %s failed: %s", mgr_name, exc)
        break  # only try the first available package manager

    # Fallback to docker
    for mgr_name, cmds in docker_pkg_managers:
        if not shutil.which(mgr_name):
            continue
        log.info(
            "Podman install failed; trying docker via %s ...",
            mgr_name,
            extra={
                "ctx": {"event": "container_runtime_install", "runtime": "docker", "pkg_manager": mgr_name}
            },
        )
        try:
            for cmd in cmds:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            if shutil.which("docker"):
                log.info(
                    "Successfully installed docker via %s",
                    mgr_name,
                    extra={"ctx": {"event": "container_runtime_installed", "runtime": "docker"}},
                )
                return "docker"
            errors.append(f"{mgr_name}: docker installed but binary not found in PATH")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{mgr_name}/docker: {exc}")
            log.debug("docker install via %s failed: %s", mgr_name, exc)
        break

    raise RuntimeError(
        "Failed to auto-install a container runtime (tried podman, then docker). "
        f"Errors: {'; '.join(errors) or 'no supported package manager found (need dnf/yum/apt-get/zypper/pacman)'}"
    )


def _detect_container_runtime(log: logging.Logger | None = None) -> str:
    """
    Detect available container runtime (podman or docker).

    If neither is found and a *log* is provided, attempts automatic
    installation via :func:`_install_container_runtime` before raising.

    Returns the name of the first available runtime command.

    Raises:
        RuntimeError: If neither podman nor docker is found or installed.
    """
    for rt in ("podman", "docker"):
        if shutil.which(rt):
            return rt

    if log is not None:
        return _install_container_runtime(log)

    raise RuntimeError("No container runtime found. Install podman or docker to use container isolation.")


# ============================================================
# Data Classes
# ============================================================


class LVMJobStatus(Enum):
    """LVM job status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class LVMJob:
    """
    LVM job specification.

    Exactly one of ``operation`` or ``script`` must be provided.

    Args:
        image_path: Path to the disk image (qcow2, vmdk, raw, etc.)
        operation: Python callback ``(lvm, nbd_device, job) -> None`` for
            direct mode.  Receives an isolated ``LVM`` instance.
        script: Shell script string for Podman mode.  Runs inside a
            container where ``lvm.conf`` already restricts scanning to
            the assigned NBD device.
        job_id: Unique job identifier (auto-generated if omitted)
        image_format: qemu-nbd format hint (None = auto-detect)
        read_only: Mount image read-only
        metadata: Arbitrary user metadata carried through to results
    """

    image_path: str | Path
    operation: Callable[[LVM, str, LVMJob], None] | None = None
    script: str | None = None
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    image_format: str | None = None
    read_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.image_path = Path(self.image_path)
        if self.operation is None and self.script is None:
            raise ValueError("LVMJob requires either 'operation' (callable) or 'script' (str)")
        if self.operation is not None and self.script is not None:
            raise ValueError("LVMJob: 'operation' and 'script' are mutually exclusive")


@dataclass
class LVMJobResult:  # pylint: disable=too-many-instance-attributes  # dataclass models independent job-result fields
    """
    LVM job result.

    Populated by the executor after a job completes or fails.
    """

    job_id: str
    status: LVMJobStatus
    nbd_device: str | None = None
    error: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# NBD helpers (shared between direct and Podman paths)
# ============================================================


def _nbd_connect(
    nbd_device: str,
    image_path: Path,
    image_format: str | None,
    read_only: bool,
    log: logging.Logger,
) -> None:
    """Connect a disk image to an NBD device, partprobe, and settle."""
    cmd = ["qemu-nbd", "--connect", nbd_device]
    if image_format:
        cmd.extend(["--format", image_format])
    if read_only:
        cmd.append("--read-only")
    cmd.append(str(image_path))

    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    subprocess.run(
        ["partprobe", nbd_device],
        check=False,
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["udevadm", "settle"],
        check=False,
        capture_output=True,
        timeout=10,
    )
    log.debug("Connected %s to %s", image_path, nbd_device)


def _nbd_disconnect(nbd_device: str, log: logging.Logger) -> None:
    """Flush buffers, disconnect NBD, and settle udev."""
    try:
        subprocess.run(["sync"], check=False, timeout=10)
        subprocess.run(
            ["blockdev", "--flushbufs", nbd_device],
            check=False,
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["qemu-nbd", "--disconnect", nbd_device],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        subprocess.run(
            ["udevadm", "settle"],
            check=False,
            capture_output=True,
            timeout=10,
        )
        log.debug("Disconnected %s", nbd_device)
    except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not abort the caller
        log.warning("NBD disconnect warning for %s: %s", nbd_device, exc)


def _lvm_device_filter(nbd_device: str) -> str:
    """
    Strict LVM device filter for *nbd_device*.

    The regex anchors to the exact device name and its ``pN`` partitions,
    preventing overmatch on devices that share a prefix (e.g. ``/dev/nbd1``
    must not match ``/dev/nbd10``).  ``global_filter`` is set identically
    so it applies even if a VG's metadata references other devices.
    udev auto-activation is disabled to prevent the host udev from
    racing with our operations.
    """
    # pylint: disable=duplicate-code
    # reason: mirrors the equivalent LVM device-filter builder in
    # h2kvm/vmcraft/storage.py (_get_lvm_device_filter) -- structurally
    # similar by coincidence (both build the same lvm.conf filter string
    # shape for an NBD device), not shared logic; keeping independent
    # avoids coupling two unrelated LVM activation code paths.
    escaped = nbd_device.replace("/", r"\/")
    return (
        f"devices {{ "
        f'filter=["a|^{escaped}($|p[0-9]+$)|","r|.*|"] '
        f'global_filter=["a|^{escaped}($|p[0-9]+$)|","r|.*|"] '
        f"}} "
        f"activation {{ "
        f"udev_sync=0 udev_rules=0 "
        f"auto_activation_volume_list=[] "
        f"thin_pool_autoextend_threshold=0 "
        f"}} "
        f"global {{ locking_type=0 }}"
    )


def list_nbd_partitions(nbd_device: str, log: logging.Logger | None = None) -> list[str]:
    """
    List partition device paths for an NBD device.

    Uses ``lsblk`` to discover partitions rather than assuming a naming
    convention, so it works regardless of partition table type.

    Args:
        nbd_device: e.g. ``/dev/nbd0``

    Returns:
        List of partition paths, e.g. ``["/dev/nbd0p1", "/dev/nbd0p2"]``
    """
    _log = log or logger
    try:
        result = subprocess.run(
            ["lsblk", "-ln", "-o", "NAME,TYPE", nbd_device],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        parts: list[str] = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] == "part":
                parts.append(f"/dev/{fields[0]}")
        return parts
    except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort listing, must not abort the caller
        _log.debug("Partition listing failed for %s: %s", nbd_device, exc)
        return []


# ============================================================
# Startup recovery
# ============================================================


def _recover_stale_nbd(log: logging.Logger) -> int:
    """
    Disconnect NBD devices whose ``qemu-nbd`` process has died.

    Only disconnects devices where the owning PID no longer exists,
    so it never interferes with healthy connections from other processes.

    Returns:
        Number of devices recovered.
    """
    recovered = 0
    for i in range(64):
        pid_file = Path(f"/sys/block/nbd{i}/pid")
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)  # Check if process is alive
        except (ValueError, ProcessLookupError):
            # PID is invalid or process is dead — stale device
            try:
                subprocess.run(
                    ["qemu-nbd", "--disconnect", f"/dev/nbd{i}"],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
                log.warning("Recovered stale NBD /dev/nbd%d", i)
                recovered += 1
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort recovery, must not abort the scan
                pass
        except OSError:
            # PermissionError etc — process exists, leave it alone
            pass
    if recovered:
        log.info(
            "Recovered %d stale NBD device(s)",
            recovered,
            extra={"ctx": {"event": "nbd_stale_recovery", "devices_recovered": recovered}},
        )
    return recovered


# ============================================================
# NBD module helper
# ============================================================


def _ensure_nbd_module(log: logging.Logger | None = None) -> None:
    """
    Ensure the ``nbd`` kernel module is loaded with ``max_part=16``.

    The ``max_part=16`` parameter is supplied by
    ``/etc/modprobe.d/h2kvm-nbd.conf`` which is installed by the
    RPM package.  If the module is already loaded with a lower
    max_part it is NOT reloaded (that would disconnect active
    devices) — a warning is emitted instead.
    """
    _log = log or logger
    nbd_params = Path("/sys/module/nbd/parameters/max_part")

    if nbd_params.exists():
        try:
            current = int(nbd_params.read_text(encoding="utf-8").strip())
            if current < 16:
                _log.warning(
                    "nbd module loaded with max_part=%d (want 16); "
                    "reload manually when no NBD devices are active: "
                    "rmmod nbd && modprobe nbd",
                    current,
                )
        except (ValueError, OSError):
            pass
        return

    # Module not loaded — load it (modprobe.d config supplies max_part)
    try:
        subprocess.run(
            ["modprobe", "nbd"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        _log.debug("Loaded nbd module (max_part=16 via modprobe.d)")
    except FileNotFoundError:
        _log.warning(
            "modprobe not found. Cannot load nbd kernel module.\n"
            "Install kmod: dnf install kmod (or apt install kmod)"
        )
    except subprocess.CalledProcessError as exc:
        _log.warning(
            "Failed to load nbd kernel module: %s\n"
            "Ensure the nbd module is available:\n"
            "  RHEL/Fedora: dnf install kernel-modules-extra\n"
            "  Ubuntu/Debian: apt install linux-modules-extra-$(uname -r)\n"
            "  Or load manually: sudo modprobe nbd max_part=16",
            exc,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort module load, must not abort the caller
        _log.warning("Failed to load nbd module: %s", exc)


# ============================================================
# NBD Device Pool
# ============================================================


class _NBDPool:
    """
    Thread-safe NBD device pool with file locking.

    Thread-safe NBD device pool with per-device file locks for cross-process safety.

    Only devices that exist *and* have no active ``qemu-nbd`` process
    (per ``/sys/block/nbdX/pid``) are added to the pool on init.
    """

    def __init__(self, max_devices: int = 32, lock_dir: Path | None = None):
        self._max_devices = min(max_devices, 64)
        self._available: queue.Queue[str] = queue.Queue()
        self._in_use: set[str] = set()
        self._lock = threading.Lock()
        self._lock_dir = lock_dir or Path("/run/lock/h2kvm-nbd")
        self._device_fds: dict[str, int] = {}

        self._lock_dir.mkdir(parents=True, exist_ok=True)

        for i in range(self._max_devices):
            device = f"/dev/nbd{i}"
            pid_path = Path(f"/sys/block/nbd{i}/pid")
            if Path(device).exists() and not pid_path.exists():
                self._available.put(device)

        logger.debug("NBD pool initialised: %d devices available", self._available.qsize())

    # ---- public ----

    def acquire(self, timeout: float | None = 300) -> str:
        """
        Acquire an available NBD device with file lock.

        Raises:
            queue.Empty: No devices available within timeout.
        """
        deadline = time.monotonic() + (timeout if timeout is not None else 1e9)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise queue.Empty("No NBD devices available within timeout")

            try:
                device = self._available.get(timeout=min(remaining, 5))
            except queue.Empty:
                continue

            if self._try_lock(device):
                with self._lock:
                    self._in_use.add(device)
                logger.debug("Acquired NBD device: %s", device)
                return device

            # Device is locked by another process — put it back and
            # sleep briefly to avoid busy-spinning when all devices
            # are externally locked.
            self._available.put(device)
            time.sleep(0.5)

    def release(self, device: str) -> None:
        """Release an NBD device back to the pool."""
        self._release_lock(device)
        with self._lock:
            self._in_use.discard(device)
        self._available.put(device)
        logger.debug("Released NBD device: %s", device)

    # ---- file locking (mirrors nbd.py:308-393) ----

    def _try_lock(self, device: str) -> bool:
        nbd_name = Path(device).name
        lock_file = self._lock_dir / f"{nbd_name}.lock"
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                return False
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.fsync(fd)
            self._device_fds[device] = fd
            return True
        except OSError:
            return False

    def _release_lock(self, device: str) -> None:
        fd = self._device_fds.pop(device, None)
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            nbd_name = Path(device).name
            lock_file = self._lock_dir / f"{nbd_name}.lock"
            lock_file.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("Lock release warning for %s: %s", device, exc)


# ============================================================
# Isolated LVM Context (direct mode)
# ============================================================


class _IsolatedLVMContext:  # pylint: disable=too-many-instance-attributes  # tracks its full connect/isolate/cleanup state
    """
    Context manager: NBD connect + isolated LVM env + device filter + cleanup.

    On enter:
        1. Connect image to NBD via qemu-nbd
        2. partprobe + udev settle
        3. Create per-job LVM_SYSTEM_DIR (PID + thread-id)
        4. Build strict device filter restricting LVM to this NBD only

    On exit:
        1. Deactivate all VGs visible through the filter
        2. Disconnect NBD
        3. Remove temporary LVM_SYSTEM_DIR
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # full connect/isolation config
        self,
        nbd_device: str,
        image_path: Path,
        image_format: str | None = None,
        read_only: bool = False,
        scan_lock: threading.Lock | None = None,
        log: logging.Logger | None = None,
    ):
        self._nbd_device = nbd_device
        self._image_path = image_path
        self._image_format = image_format
        self._read_only = read_only
        self._scan_lock = scan_lock
        self._log = log or logger
        self._lvm_system_dir: Path | None = None
        self._lvm: LVM | None = None
        self._connected = False

    # ---- context manager ----

    def __enter__(self) -> LVM:
        _nbd_connect(
            self._nbd_device,
            self._image_path,
            self._image_format,
            self._read_only,
            self._log,
        )
        self._connected = True

        try:
            lvm_env, self._lvm_system_dir = self._create_isolated_env()
            device_filter = _lvm_device_filter(self._nbd_device)
            self._lvm = LVM(
                logger=self._log,
                env=lvm_env,
                device_filter=device_filter,
            )
            # Serialise the initial pvscan across workers to avoid
            # device-mapper contention during concurrent cache priming.
            if self._scan_lock is not None:
                with self._scan_lock:
                    self._lvm.scan(activate=False)
            else:
                self._lvm.scan(activate=False)
        except Exception:
            _nbd_disconnect(self._nbd_device, self._log)
            self._connected = False
            self._cleanup_lvm_dir()
            raise

        return self._lvm

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            self._deactivate_vgs()
        finally:
            try:
                if self._connected:
                    _nbd_disconnect(self._nbd_device, self._log)
                    self._connected = False
            finally:
                self._cleanup_lvm_dir()

    # ---- LVM isolation (mirrors storage.py) ----

    def _create_isolated_env(self) -> tuple[dict[str, str], Path]:
        """Create per-job LVM_SYSTEM_DIR keyed by PID + thread-id."""
        tid = threading.get_ident()
        lvm_dir = Path(tempfile.gettempdir()) / f"h2kvm-lvm-{os.getpid()}-{tid}"
        lvm_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["LVM_SYSTEM_DIR"] = str(lvm_dir)
        env["LVM_SUPPRESS_FD_WARNINGS"] = "1"
        self._log.debug("Isolated LVM env: %s", lvm_dir)
        return env, lvm_dir

    def _deactivate_vgs(self) -> None:
        """Deactivate all VGs visible through our device filter."""
        if self._lvm is None:
            return
        try:
            # Invalidate cache so we see the current state after the
            # user callback may have activated/created/removed VGs.
            self._lvm.invalidate_cache()
            vgs = self._lvm.vgs()
            if vgs:
                self._lvm.vg_activate(False, vgs)
                self._log.debug("Deactivated VGs: %s", vgs)
        except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not abort __exit__
            self._log.debug("VG deactivation warning: %s", exc)

    def _cleanup_lvm_dir(self) -> None:
        if self._lvm_system_dir and self._lvm_system_dir.exists():
            try:
                shutil.rmtree(self._lvm_system_dir)
            except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not abort __exit__
                self._log.debug("LVM dir cleanup warning: %s", exc)


# ============================================================
# Podman Worker (container isolation mode)
# ============================================================


_H2KVM_LVM_IMAGE = "localhost/h2kvm-lvm:latest"


def _ensure_lvm_image(log: logging.Logger, runtime: str | None = None) -> str:
    """
    Ensure a local container image with LVM tools exists.

    If ``localhost/h2kvm-lvm:latest`` is not present, it is built
    automatically from ``fedora-minimal`` with ``lvm2`` and
    ``device-mapper`` installed.  The image is cached locally and
    reused for all subsequent runs.

    Args:
        log: Logger instance
        runtime: Container runtime command (``podman`` or ``docker``).
                 Auto-detected if *None*.

    Returns:
        Image name suitable for ``<runtime> run``.
    """
    rt = runtime or _detect_container_runtime(log)

    # Check if our image already exists
    if rt == "docker":
        check_cmd = [rt, "image", "inspect", _H2KVM_LVM_IMAGE]
    else:
        check_cmd = [rt, "image", "exists", _H2KVM_LVM_IMAGE]

    result = subprocess.run(
        check_cmd,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        log.debug("Container image %s already exists (%s)", _H2KVM_LVM_IMAGE, rt)
        return _H2KVM_LVM_IMAGE

    # Build it
    log.info(
        "Building container image %s via %s (one-time operation)...",
        _H2KVM_LVM_IMAGE,
        rt,
        extra={
            "ctx": {"event": "container_image_build_start", "image": _H2KVM_LVM_IMAGE, "runtime": rt}
        },
    )
    containerfile = (
        "FROM registry.fedoraproject.org/fedora-minimal:latest\n"
        "RUN microdnf install -y --nodocs --setopt=install_weak_deps=0 "
        "lvm2 device-mapper && microdnf clean all\n"
    )
    build = subprocess.run(
        [rt, "build", "--network=host", "-t", _H2KVM_LVM_IMAGE, "-f", "-"],
        input=containerfile,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError(f"Failed to build {_H2KVM_LVM_IMAGE} via {rt}: {build.stderr.strip()}")
    log.info(
        "Built container image %s via %s",
        _H2KVM_LVM_IMAGE,
        rt,
        extra={
            "ctx": {"event": "container_image_build_complete", "image": _H2KVM_LVM_IMAGE, "runtime": rt}
        },
    )
    return _H2KVM_LVM_IMAGE


class _PodmanWorker:  # pylint: disable=too-few-public-methods  # single-purpose worker, run() is its only operation
    """
    Run an LVM shell script inside a container (podman or docker).

    On first use, builds ``localhost/h2kvm-lvm:latest`` from
    ``fedora-minimal`` with ``lvm2`` installed.  The image is cached
    locally and reused for all subsequent runs.

    The container is launched **without** ``--privileged``.  Instead it
    receives only the capabilities needed for device-mapper and block I/O:

        --cap-add=SYS_ADMIN         — device-mapper ioctls
        --cap-add=SYS_RAWIO         — raw block I/O
        --cap-add=MKNOD             — device node creation
        --security-opt=no-new-privileges
        --network=none              — no network access
        --device /dev/nbdX          — the NBD device
        --device /dev/nbdXp*        — all partition devices
        --device /dev/mapper/control — device-mapper control node
        --tmpfs /etc/lvm            — private LVM config
        --tmpfs /var/lib/lvm        — private LVM state
        --tmpfs /run/lvm            — private LVM runtime

    Before the user script runs, a wrapper writes ``/etc/lvm/lvm.conf``
    inside the container with the strict device filter.

    The container runtime (podman or docker) is auto-detected unless
    explicitly overridden.
    """

    def __init__(
        self,
        image: str | None = None,
        log: logging.Logger | None = None,
        runtime: str | None = None,
    ):
        self._log = log or logger
        # Detect container runtime (podman or docker)
        self._runtime = runtime or _detect_container_runtime(self._log)
        self._log.debug("Container runtime: %s", self._runtime)
        # If caller provides an explicit image, use it as-is.
        # Otherwise build/reuse the h2kvm-lvm image with LVM tools.
        if image and image != "auto":
            self._image = image
        else:
            self._image = _ensure_lvm_image(self._log, runtime=self._runtime)

    def run(
        self,
        nbd_device: str,
        script: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        Execute *script* inside a container with the NBD device.

        A strict device-filter ``lvm.conf`` is written into the container's
        ``/etc/lvm`` tmpfs before the user script runs, restricting all
        LVM commands to the assigned NBD device and its partitions.

        Args:
            nbd_device: Connected /dev/nbdX device
            script: Shell script to execute inside the container

        Returns:
            CompletedProcess from container run

        Raises:
            RuntimeError: If the container exits non-zero
        """
        escaped = nbd_device.replace("/", r"\/")

        # Wrapper: write strict lvm.conf, prime the cache, run user script.
        wrapper = (
            "set -e\n"
            "mkdir -p /etc/lvm\n"
            "cat > /etc/lvm/lvm.conf << 'LVMCONF'\n"
            "devices {\n"
            f'    filter = ["a|^{escaped}($|p[0-9]+$)|", "r|.*|"]\n'
            f'    global_filter = ["a|^{escaped}($|p[0-9]+$)|", "r|.*|"]\n'
            "}\n"
            "activation {\n"
            "    udev_sync = 0\n"
            "    udev_rules = 0\n"
            "    auto_activation_volume_list = []\n"
            "    thin_pool_autoextend_threshold = 0\n"
            "}\n"
            "global {\n"
            "    locking_type = 0\n"
            "}\n"
            "LVMCONF\n"
            "pvscan --cache >/dev/null 2>&1 || true\n"
            f"{script}\n"
        )

        rt = self._runtime

        # Build command with targeted capabilities instead of --privileged
        cmd = [
            rt,
            "run",
            "--rm",
            "--cap-add=SYS_ADMIN",
            "--cap-add=SYS_RAWIO",
            "--cap-add=MKNOD",
            "--security-opt=no-new-privileges",
            "--network=none",
            f"--device={nbd_device}",
        ]

        # Pass partition devices so they're visible inside the container
        nbd_path = Path(nbd_device)
        for part in sorted(nbd_path.parent.glob(f"{nbd_path.name}p*")):
            cmd.append(f"--device={part}")

        # device-mapper control node is required for LVM operations
        if Path("/dev/mapper/control").exists():
            cmd.append("--device=/dev/mapper/control")

        cmd.extend(
            [
                "--tmpfs",
                "/etc/lvm",
                "--tmpfs",
                "/var/lib/lvm",
                "--tmpfs",
                "/run/lvm",
                "--env",
                "LVM_SUPPRESS_FD_WARNINGS=1",
                self._image,
                "sh",
                "-c",
                wrapper,
            ]
        )

        self._log.debug("%s exec on %s: %s", rt, nbd_device, script)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Container script failed ({rt}, rc={result.returncode}): {result.stderr.strip()}"
            )

        return result


# ============================================================
# LVM Executor
# ============================================================


class LVMExecutor:  # pylint: disable=too-many-instance-attributes  # holds full pool/job/lock/timeout runtime state
    """
    Enterprise parallel LVM executor.

    Safely runs user-defined LVM operations across multiple disk images
    concurrently.  Each job gets its own NBD device and LVM isolation
    that makes host LVM completely invisible.

    On construction the executor:
        1. Ensures the ``nbd`` kernel module is loaded with ``max_part=16``
        2. Recovers stale NBD devices left by crashed ``qemu-nbd`` processes
        3. Builds a pool of free NBD devices (skipping those already in use)

    Args:
        max_workers: Maximum concurrent jobs (capped by available NBD devices)
        max_nbd_devices: Size of the NBD device pool
        podman_image: Container image for Podman mode.  Pass ``"auto"``
            to auto-build and cache ``localhost/h2kvm-lvm:latest``
            (fedora-minimal + lvm2), or an explicit image name.  When
            set, jobs that provide a ``script`` run inside a hardened
            container.  Jobs that provide an ``operation`` callback
            still run in direct mode regardless of this setting.
        job_timeout: Hard timeout in seconds per job (default 900).
            If a job's callback or script exceeds this, it is reported as
            failed and the NBD device is disconnected (which causes any
            in-flight LVM subprocesses to receive I/O errors).

    Example (direct mode):
        def fix_uuids(lvm, nbd_device, job):
            for vg in lvm.vgs():
                lvm.vgchange_uuid(vg)

        executor = LVMExecutor(max_workers=4)
        results = executor.run([
            LVMJob(image_path="/images/vm1.qcow2", operation=fix_uuids),
            LVMJob(image_path="/images/vm2.qcow2", operation=fix_uuids),
        ])

    Example (Podman mode):
        executor = LVMExecutor(max_workers=4, podman_image="fedora:latest")
        results = executor.run([
            LVMJob(image_path="/images/vm1.qcow2", script="vgscan && vgs"),
        ])
    """

    def __init__(
        self,
        max_workers: int = 8,
        max_nbd_devices: int = 32,
        podman_image: str | None = None,
        job_timeout: int = DEFAULT_JOB_TIMEOUT,
        logger_instance: logging.Logger | None = None,
    ):
        self._log = logger_instance or logger
        _ensure_nbd_module(self._log)
        _recover_stale_nbd(self._log)

        self._pool = _NBDPool(max_devices=max_nbd_devices)
        self._max_workers = min(max_workers, max_nbd_devices)
        self._job_timeout = job_timeout
        self._podman_worker = _PodmanWorker(image=podman_image, log=self._log) if podman_image else None

        # Serialises the pvscan phase across workers to prevent
        # device-mapper contention during concurrent cache priming.
        # Does NOT wrap the user callback — actual LVM work proceeds
        # in parallel because each job has its own device filter.
        self._scan_lock = threading.Lock()

        self._jobs: dict[str, LVMJob] = {}
        self._results: dict[str, LVMJobResult] = {}
        self._lock = threading.Lock()

        self._log.info(
            "LVMExecutor ready (workers=%d, nbd_pool=%d, podman=%s, job_timeout=%ds)",
            self._max_workers,
            max_nbd_devices,
            podman_image or "disabled",
            self._job_timeout,
            extra={
                "ctx": {
                    "event": "lvm_executor_ready",
                    "max_workers": self._max_workers,
                    "nbd_pool_size": max_nbd_devices,
                    "isolation_mode": "podman" if podman_image else "direct",
                    "job_timeout_s": self._job_timeout,
                }
            },
        )

    # ---- public API ----

    def run(
        self,
        jobs: list[LVMJob],
        progress_callback: Callable[[str, LVMJobStatus], None] | None = None,
    ) -> dict[str, LVMJobResult]:
        """
        Execute LVM jobs in parallel.

        Args:
            jobs: List of LVMJob specifications
            progress_callback: Optional callback(job_id, status) called on
                each status transition

        Returns:
            Dict mapping job_id to LVMJobResult
        """
        self._log.info(
            "Starting %d LVM jobs across %d workers",
            len(jobs),
            self._max_workers,
            extra={
                "ctx": {
                    "event": "lvm_executor_run_start",
                    "job_count": len(jobs),
                    "max_workers": self._max_workers,
                }
            },
        )

        # Validate before starting any work
        for job in jobs:
            if job.script is not None and self._podman_worker is None:
                raise ValueError(
                    f"Job {job.job_id} has 'script' but no podman_image was configured on the LVMExecutor"
                )

        # Reset state for this run
        with self._lock:
            self._jobs.clear()
            self._results.clear()

        for job in jobs:
            with self._lock:
                self._jobs[job.job_id] = job

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._worker, job, progress_callback): job for job in jobs}

            for future in as_completed(futures):
                job = futures[future]
                try:
                    future.result()
                except Exception as exc:  # pylint: disable=broad-exception-caught  # one job's crash must not abort the batch
                    self._log.error("Unhandled future exception for %s: %s", job.job_id, exc)

        succeeded = sum(1 for r in self._results.values() if r.status == LVMJobStatus.SUCCESS)
        failed = sum(1 for r in self._results.values() if r.status == LVMJobStatus.FAILED)
        self._log.info(
            "LVM executor complete: %d succeeded, %d failed",
            succeeded,
            failed,
            extra={
                "ctx": {
                    "event": "lvm_executor_run_complete",
                    "succeeded": succeeded,
                    "failed": failed,
                    "total": len(self._results),
                }
            },
        )

        return dict(self._results)

    def status(self) -> dict[str, Any]:
        """Return snapshot of executor state."""
        with self._lock:
            return {
                "max_workers": self._max_workers,
                "podman": self._podman_worker is not None,
                "job_timeout": self._job_timeout,
                "jobs_total": len(self._jobs),
                "succeeded": sum(1 for r in self._results.values() if r.status == LVMJobStatus.SUCCESS),
                "failed": sum(1 for r in self._results.values() if r.status == LVMJobStatus.FAILED),
            }

    # ---- internal worker ----

    def _worker(
        self,
        job: LVMJob,
        progress_callback: Callable[[str, LVMJobStatus], None] | None,
    ) -> LVMJobResult:
        """Per-job worker function executed inside the thread pool."""
        result = LVMJobResult(
            job_id=job.job_id,
            status=LVMJobStatus.PENDING,
            metadata=dict(job.metadata),
        )
        nbd_device: str | None = None

        try:
            # Validate image exists before wasting an NBD slot
            if not job.image_path.exists():
                raise FileNotFoundError(f"Image not found: {job.image_path}")

            # 1. Acquire NBD device
            nbd_device = self._pool.acquire(timeout=300)
            result.nbd_device = nbd_device
            result.status = LVMJobStatus.RUNNING

            if progress_callback:
                progress_callback(job.job_id, LVMJobStatus.RUNNING)

            # 2. Dispatch to the appropriate execution mode
            if job.script is not None:
                self._run_podman(job, nbd_device)
            else:
                self._run_direct(job, nbd_device)

            result.status = LVMJobStatus.SUCCESS
            self._log.info(
                "Job %s succeeded on %s",
                job.job_id,
                nbd_device,
                extra={
                    "ctx": {
                        "event": "lvm_job_success",
                        "job_id": job.job_id,
                        "nbd_device": nbd_device,
                        "image": str(job.image_path),
                    }
                },
            )

        except Exception as exc:  # pylint: disable=broad-exception-caught  # one job's failure must not abort the executor
            result.status = LVMJobStatus.FAILED
            result.error = str(exc)
            self._log.error(
                "Job %s failed: %s",
                job.job_id,
                exc,
                extra={
                    "ctx": {
                        "event": "lvm_job_failed",
                        "job_id": job.job_id,
                        "nbd_device": nbd_device,
                        "error": str(exc),
                        "image": str(job.image_path),
                    }
                },
            )

        finally:
            result.end_time = time.time()
            result.duration = result.end_time - result.start_time

            if nbd_device:
                self._pool.release(nbd_device)

            with self._lock:
                self._results[job.job_id] = result

            if progress_callback:
                progress_callback(job.job_id, result.status)

        return result

    def _run_direct(self, job: LVMJob, nbd_device: str) -> None:
        """Execute a Python callback with an isolated LVM instance."""
        ctx = _IsolatedLVMContext(
            nbd_device=nbd_device,
            image_path=job.image_path,
            image_format=job.image_format,
            read_only=job.read_only,
            scan_lock=self._scan_lock,
            log=self._log,
        )

        with ctx as lvm:
            # Run the callback inside a single-thread executor so we
            # can enforce the hard timeout.  On timeout we disconnect
            # the NBD device *first* (which causes any in-flight LVM
            # subprocesses to fail with I/O errors), then allow the
            # context manager to proceed with cleanup.
            #
            # We avoid the ``with`` statement for the inner executor
            # because its __exit__ calls shutdown(wait=True), which
            # would block until the callback thread finishes —
            # defeating the timeout.
            single = ThreadPoolExecutor(max_workers=1)
            future = single.submit(job.operation, lvm, nbd_device, job)
            try:
                future.result(timeout=self._job_timeout)
            except TimeoutError:
                # Disconnect NBD to break any hung LVM subprocesses
                # inside the callback thread, then abandon the thread.
                _nbd_disconnect(nbd_device, self._log)
                single.shutdown(wait=False, cancel_futures=True)
                raise RuntimeError(f"Job {job.job_id} exceeded timeout of {self._job_timeout}s") from None
            finally:
                single.shutdown(wait=False)

    def _run_podman(self, job: LVMJob, nbd_device: str) -> None:
        """Connect NBD on the host, run script in a Podman container."""
        _nbd_connect(
            nbd_device,
            job.image_path,
            job.image_format,
            job.read_only,
            self._log,
        )
        try:
            self._podman_worker.run(nbd_device, job.script)
        finally:
            _nbd_disconnect(nbd_device, self._log)
