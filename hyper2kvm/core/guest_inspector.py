# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/guest_inspector.py
"""
Comprehensive guest OS inspection with mounting.

Extracts detailed information from disk images by mounting them:
- OS details (distribution, version, kernel)
- Network interfaces and MAC addresses
- IP configuration
- Installed packages
- Running services
- User accounts
- SSH configuration
- Disk usage
- Installed software
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .guest_identity import GuestDetector, GuestIdentity, GuestType
from .guestfs_factory import create_guestfs
from .structured_log import PhaseTimer, TraceContext, log_event

if TYPE_CHECKING:  # pylint: disable=duplicate-code
    # This typing-only guestfs-availability shim is intentionally identical to the
    # same block in other fixer/inspector modules; it's boilerplate for a fallback
    # typing stub, not shared logic worth extracting.
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
        # Typing-only fallback stub: name must match the real `guestfs` module/class
        # so annotations below resolve the same way whether or not guestfs is installed.
        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

GUESTFS_AVAILABLE = True  # Native implementation always available

logger = logging.getLogger(__name__)


@dataclass
class NetworkInterface:  # pylint: disable=too-many-instance-attributes
    """Network interface information.

    Models the many independent attributes libguestfs/inspectors report per NIC.
    """

    name: str
    mac_address: str | None = None
    ip_addresses: list[str] = field(default_factory=list)
    type: str | None = None  # ethernet, wireless, bridge, etc.
    state: str | None = None  # up, down
    mtu: int | None = None
    driver: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None


@dataclass
class InstalledPackage:
    """Installed package information."""

    name: str
    version: str | None = None
    architecture: str | None = None
    package_format: str | None = None  # rpm, deb, apk, etc.


@dataclass
class SystemdService:
    """Systemd service information."""

    name: str
    enabled: bool = False
    state: str | None = None  # active, inactive, failed
    preset: str | None = None


@dataclass
class UserAccount:
    """User account information."""

    username: str
    uid: int | None = None
    gid: int | None = None
    home: str | None = None
    shell: str | None = None
    comment: str | None = None


@dataclass
class DiskUsage:
    """Disk usage information."""

    filesystem: str
    mountpoint: str
    size_bytes: int
    used_bytes: int
    available_bytes: int
    use_percent: float


@dataclass
class Partition:
    """Partition information."""

    device: str
    number: int | None = None
    size_bytes: int | None = None
    filesystem_type: str | None = None
    label: str | None = None
    uuid: str | None = None
    bootable: bool = False


@dataclass
class Application:
    """Installed application (Windows) or package (Linux)."""

    name: str
    version: str | None = None
    vendor: str | None = None
    install_date: str | None = None
    install_location: str | None = None
    size_bytes: int | None = None


@dataclass
class FirewallRule:
    """Firewall rule information."""

    name: str
    enabled: bool = False
    direction: str | None = None  # inbound, outbound
    action: str | None = None  # allow, deny
    protocol: str | None = None
    port: str | None = None


@dataclass
class ScheduledTask:
    """Scheduled task or cron job."""

    name: str
    command: str | None = None
    schedule: str | None = None
    user: str | None = None
    enabled: bool = True


@dataclass
class GuestInspectionResult:  # pylint: disable=too-many-instance-attributes
    """Complete guest inspection result.

    Aggregates every category of inspection data (network, packages, services,
    users, disk, applications, firewall, etc.) into a single result object.
    """

    # Basic identity (from existing GuestIdentity)
    identity: GuestIdentity | None = None

    # Network information
    network_interfaces: list[NetworkInterface] = field(default_factory=list)
    hostname: str | None = None
    dns_servers: list[str] = field(default_factory=list)

    # Packages
    installed_packages: list[InstalledPackage] = field(default_factory=list)
    package_count: int = 0
    package_format: str | None = None  # rpm, deb, apk, pacman

    # Services
    systemd_services: list[SystemdService] = field(default_factory=list)
    service_count: int = 0

    # Users
    user_accounts: list[UserAccount] = field(default_factory=list)
    user_count: int = 0

    # SSH
    ssh_authorized_keys: dict[str, list[str]] = field(default_factory=dict)
    ssh_host_keys: list[str] = field(default_factory=list)

    # Disk usage
    disk_usage: list[DiskUsage] = field(default_factory=list)

    # Partitions and filesystems
    partitions: list[Partition] = field(default_factory=list)
    filesystems: list[str] = field(default_factory=list)
    mount_points: dict[str, str] = field(default_factory=dict)  # device -> mount point

    # Applications (Windows) or detailed packages (Linux)
    applications: list[Application] = field(default_factory=list)
    application_count: int = 0

    # Firewall
    firewall_rules: list[FirewallRule] = field(default_factory=list)
    firewall_enabled: bool | None = None

    # Scheduled tasks
    scheduled_tasks: list[ScheduledTask] = field(default_factory=list)

    # Environment and configuration
    environment_variables: dict[str, str] = field(default_factory=dict)
    selinux_status: str | None = None  # enforcing, permissive, disabled

    # Additional metadata
    kernel_modules: list[str] = field(default_factory=list)
    boot_parameters: str | None = None
    timezone: str | None = None
    locale: str | None = None

    # Windows-specific
    windows_product_name: str | None = None
    windows_build_number: str | None = None
    windows_install_date: str | None = None

    # Raw metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class ComprehensiveGuestInspector:  # pylint: disable=too-few-public-methods
    """
    Comprehensive guest OS inspector that mounts images and extracts detailed information.

    Delegates OS-specific extraction to LinuxGuestExtractor and WindowsGuestExtractor
    for maintainability. Shared infrastructure (partitions, filesystems, mounting) remains here.

    Deliberately has a single public entry point (`inspect`); the rest of the
    surface is private helper methods.
    """

    def __init__(self, logger_instance: logging.Logger | None = None):
        """
        Initialize inspector.

        Args:
            logger_instance: Logger to use (creates new one if None)
        """
        self.logger = logger_instance or logger

        # OS-specific extractors (composition over inheritance). Imported lazily
        # here to break a circular import: inspectors.linux_extractor/windows_extractor
        # import types from this module at their own top level.
        from .inspectors import (  # pylint: disable=import-outside-toplevel,cyclic-import
            LinuxGuestExtractor,
            WindowsGuestExtractor,
        )

        self._linux = LinuxGuestExtractor(self.logger)
        self._windows = WindowsGuestExtractor(self.logger)

    def inspect(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
        # Each flag independently toggles one category of extraction the caller
        # may want to skip; collapsing them would remove that fine-grained control.
        # The method also drives the full mount/inspect/extract/cleanup lifecycle,
        # which is inherently a lot of sequential steps and error paths.
        self,
        img_path: str | Path,
        *,
        readonly: bool = True,
        network_info: bool = True,
        package_info: bool = True,
        service_info: bool = True,
        user_info: bool = True,
        ssh_info: bool = True,
        disk_info: bool = True,
    ) -> GuestInspectionResult:
        """
        Perform comprehensive guest inspection.

        Args:
            img_path: Path to disk image
            readonly: Mount read-only (recommended)
            network_info: Extract network interface information
            package_info: Extract installed package information
            service_info: Extract systemd service information
            user_info: Extract user account information
            ssh_info: Extract SSH configuration
            disk_info: Extract disk usage information

        Returns:
            Complete inspection result

        Raises:
            RuntimeError: If guestfs not available or inspection fails
        """
        if not GUESTFS_AVAILABLE:
            raise RuntimeError(
                "Guest inspection backend is not available.\n"
                "    Try: pip install python3-guestfs\n"
                "    Or set backend to VMCraft in your config: backend: vmcraft\n"
                "    VMCraft is the default and does not require libguestfs."
            )

        img_path = Path(img_path)
        if not img_path.exists():
            raise FileNotFoundError(
                f"Disk image not found: {img_path}\n"
                f"    Verify the path is correct and the file exists.\n"
                f"    If using a relative path, try an absolute path instead."
            )

        result = GuestInspectionResult()

        # First, use existing GuestDetector for basic identity
        self.logger.info(f"Inspecting guest image: {img_path}")

        with TraceContext(vm_id=img_path.name, workflow="guest_inspection", component="guest_inspector"):
            with PhaseTimer("identity_detect_start", "identity_detect_complete", phase="identity"):
                result.identity = GuestDetector.detect(img_path, self.logger, readonly=readonly)

            if not result.identity:
                self.logger.warning(
                    "Could not detect guest identity.\n"
                    "    The disk image may be encrypted, use an unsupported filesystem, or be empty.\n"
                    "    For LUKS volumes, provide: --luks-passphrase or --luks-keyfile\n"
                    "    Migration will continue but offline fixes may be incomplete."
                )
                return result

            log_event(
                "guest_identity_detected",
                os_type=result.identity.type.value,
                method=result.identity.detection_method,
                confidence=result.identity.confidence,
            )

            # Now mount and extract detailed information
            g = create_guestfs(python_return_dict=True, backend="vmcraft")

            try:
                g.add_drive_opts(str(img_path), readonly=1 if readonly else 0)
                g.launch()

                # Extract partition and filesystem information (before mounting)
                result.partitions = self._extract_partitions(g)
                result.filesystems = self._extract_filesystems(g)

                # Get root filesystem
                roots = g.inspect_os()
                if not roots:
                    self.logger.warning(
                        "No operating systems found.\n"
                        "    The disk may be a data-only volume, encrypted, or use an unsupported filesystem.\n"
                        "    For LUKS volumes, provide: --luks-passphrase or --luks-keyfile"
                    )
                    return result

                root = roots[0]
                self.logger.debug("Inspecting root: %s", root)

                # Mount the filesystem
                mounts = self._get_mount_points(g, root)
                result.mount_points = mounts
                for mp, dev in mounts.items():
                    try:
                        if readonly:
                            g.mount_ro(dev, mp)
                        else:
                            g.mount(dev, mp)
                        self.logger.debug("Mounted %s at %s", dev, mp)
                    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-mount-point step, must not abort the whole inspection
                        self.logger.warning("Failed to mount %s at %s: %s", dev, mp, e)

                # Extract information based on OS type
                with PhaseTimer("detail_extract_start", "detail_extract_complete", phase="extraction"):
                    if result.identity.type == GuestType.LINUX:
                        self._inspect_linux(
                            g,
                            result,
                            network_info=network_info,
                            package_info=package_info,
                            service_info=service_info,
                            user_info=user_info,
                            ssh_info=ssh_info,
                            disk_info=disk_info,
                        )
                    elif result.identity.type == GuestType.WINDOWS:
                        self._inspect_windows(g, result, network_info=network_info, user_info=user_info)

                log_event(
                    "guest_inspection_complete",
                    os_type=result.identity.type.value,
                    partition_count=len(result.partitions),
                    package_count=result.package_count,
                    service_count=result.service_count,
                )

            except Exception as e:  # pylint: disable=broad-exception-caught  # catch-all: log a diagnostic before re-raising
                self.logger.error(
                    "Guest inspection failed for '%s': %s\n"
                    "    Common causes:\n"
                    "    - Disk image is corrupted or incomplete (re-download or re-export)\n"
                    "    - Image uses an unsupported filesystem (ZFS, Btrfs subvolumes)\n"
                    "    - Insufficient disk space for temporary conversion files\n"
                    "    - LUKS-encrypted volume (provide --luks-passphrase)\n"
                    "    Try: qemu-img check '%s' to verify image integrity.",
                    img_path,
                    e,
                    img_path,
                    exc_info=True,
                )
                raise
            finally:
                try:
                    g.umount_all()
                    g.shutdown()
                    g.close()
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not mask the original error/result
                    pass

        return result

    def _inspect_linux(  # pylint: disable=too-many-arguments
        # Mirrors the independent extraction toggles accepted by inspect().
        self,
        g: Any,
        result: GuestInspectionResult,
        *,
        network_info: bool,
        package_info: bool,
        service_info: bool,
        user_info: bool,
        ssh_info: bool,
        disk_info: bool,
    ) -> None:
        """Delegate Linux extraction to LinuxGuestExtractor."""
        lx = self._linux

        if network_info:
            result.network_interfaces = lx.extract_network_interfaces(g)
            result.hostname = lx.extract_hostname(g)
            result.dns_servers = lx.extract_dns_servers(g)

        if package_info:
            result.package_format = lx.detect_package_format(g)
            result.installed_packages = lx.extract_packages(g, result.package_format)
            result.package_count = len(result.installed_packages)

        if service_info:
            result.systemd_services = lx.extract_systemd_services(g)
            result.service_count = len(result.systemd_services)

        if user_info:
            result.user_accounts = lx.extract_users(g)
            result.user_count = len(result.user_accounts)

        if ssh_info:
            result.ssh_authorized_keys = lx.extract_ssh_keys(g)
            result.ssh_host_keys = lx.extract_ssh_host_keys(g)

        if disk_info:
            result.disk_usage = lx.extract_disk_usage(g)

        result.kernel_modules = lx.extract_kernel_modules(g)
        result.boot_parameters = lx.extract_boot_parameters(g)
        result.timezone = lx.extract_timezone(g)
        result.locale = lx.extract_locale(g)
        result.scheduled_tasks = lx.extract_cron_jobs(g)
        result.firewall_rules = lx.extract_firewall_rules(g)
        result.selinux_status = lx.extract_selinux_status(g)
        result.environment_variables = lx.extract_environment(g)

    def _inspect_windows(
        self,
        g: Any,
        result: GuestInspectionResult,
        *,
        network_info: bool,
        user_info: bool,
    ) -> None:
        """Delegate Windows extraction to WindowsGuestExtractor."""
        win = self._windows

        if network_info:
            result.network_interfaces = win.extract_network_interfaces(g)
            result.hostname = win.extract_hostname(g)

        result.applications = win.extract_applications(g)
        result.application_count = len(result.applications)
        result.windows_product_name = win.extract_product_name(g)
        result.windows_build_number = win.extract_build_number(g)
        result.windows_install_date = win.extract_install_date(g)

        if user_info:
            result.user_accounts = win.extract_users(g)
            result.user_count = len(result.user_accounts)

        result.scheduled_tasks = win.extract_scheduled_tasks(g)
        result.firewall_rules = win.extract_firewall_rules(g)
        result.environment_variables = win.extract_environment(g)

    def _get_mount_points(self, g: guestfs.GuestFS, root: str) -> dict[str, str]:
        """Get mount points for root filesystem."""
        mounts = {}

        try:
            # Get mount points from inspection
            mp_dict = g.inspect_get_mountpoints(root)

            # Sort by mount point length (mount / before /boot, etc.)
            sorted_mps = sorted(mp_dict.items(), key=lambda x: len(x[0]))

            mounts = dict(sorted_mps)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort mountpoint discovery, falls back to mounting root
            self.logger.warning("Failed to get mount points: %s", e)
            # Fallback: try to mount root
            mounts["/"] = root

        return mounts

    # General extraction methods (both Linux and Windows)

    def _extract_partitions(self, g: guestfs.GuestFS) -> list[Partition]:
        """Extract partition information from disk."""
        partitions = []

        try:
            devices = g.list_devices()
            for device in devices:
                try:
                    # Get partitions for this device
                    parts = g.list_partitions()
                    for part in parts:
                        if not part.startswith(device):
                            continue

                        partition = Partition(device=part)

                        # Try to get partition number
                        with contextlib.suppress(Exception):
                            partition.number = g.part_to_partnum(part)

                        # Try to get size
                        with contextlib.suppress(Exception):
                            partition.size_bytes = g.blockdev_getsize64(part)

                        # Try to get filesystem type
                        with contextlib.suppress(Exception):
                            partition.filesystem_type = g.vfs_type(part)

                        # Try to get label
                        with contextlib.suppress(Exception):
                            partition.label = g.vfs_label(part)

                        # Try to get UUID
                        with contextlib.suppress(Exception):
                            partition.uuid = g.vfs_uuid(part)

                        partitions.append(partition)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-device partition scan, must not abort the whole extraction
                    self.logger.debug("Failed to get partitions for %s: %s", device, e)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort partition extraction, must not abort the whole inspection
            self.logger.warning("Failed to extract partition information: %s", e)

        return partitions

    def _extract_filesystems(self, g: guestfs.GuestFS) -> list[str]:
        """Extract list of filesystems."""
        filesystems = []

        try:
            parts = g.list_partitions()
            for part in parts:
                try:
                    fs_type = g.vfs_type(part)
                    if fs_type and fs_type not in filesystems:
                        filesystems.append(fs_type)
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort per-partition fs-type probe, one failure must not abort the scan
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort filesystem extraction, must not abort the whole inspection
            self.logger.debug("Failed to extract filesystems: %s", e)

        return filesystems
