# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/main.py
"""
VMCraft main class - delegates to modular components.

This file provides the main VMCraft API that maintains backward compatibility
with the original monolithic implementation while delegating to specialized modules.
Uses composition (ops classes) instead of mixin inheritance.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from .advanced_analysis import AdvancedAnalyzer
from .api import (
    AnalyzerOps,
    AugeasOps,
    DiskOps,
    FileOps,
    FilesystemOps,
    InspectionOps,
    LinuxOps,
    MountOps,
    SecurityOps,
    StorageOps,
    SystemdOps,
    WindowsOps,
)
from .app_framework_detector import AppFrameworkDetector
from .augeas_mgr import AugeasManager
from .backup import BackupManager
from .backup_analysis import BackupAnalysis
from .certificate_manager import CertificateManager
from .cloud_detector import CloudDetector
from .cloud_optimizer import CloudOptimizer
from .compliance_checker import ComplianceChecker
from .config_tracker import ConfigTracker
from .container_analyzer import ContainerAnalyzer
from .data_discovery import DataDiscovery
from .database_detector import DatabaseDetector
from .dependency_mapper import DependencyMapper
from .disaster_recovery import DisasterRecovery
from .enhanced_inspection import EnhancedInspector
from .export import ExportManager
from .file_ops import FileOperations
from .firewall_analyzer import FirewallAnalyzer
from .forensic_analyzer import ForensicAnalyzer
from .hardware_detector import HardwareDetector
from .inspection import OSInspector
from .license_detector import LicenseDetector
from .linux_detection import LinuxDetector
from .linux_services import LinuxServiceManager
from .log_analyzer import LogAnalyzer
from .migration_planner import MigrationPlanner
from .monitoring_detector import MonitoringDetector
from .mount import MountManager
from .network_config import NetworkConfigAnalyzer
from .network_topology import NetworkTopology
from .optimization import DiskOptimizer
from .performance_analyzer import PerformanceAnalyzer
from .scheduled_tasks import ScheduledTaskAnalyzer
from .security import SecurityAuditor
from .services import (
    blockdev_flushbufs as svc_blockdev_flushbufs,
    blockdev_getbsz as svc_blockdev_getbsz,
    blockdev_getro as svc_blockdev_getro,
    blockdev_getss as svc_blockdev_getss,
    blockdev_rereadpt as svc_blockdev_rereadpt,
    blockdev_setro as svc_blockdev_setro,
    blockdev_setrw as svc_blockdev_setrw,
    close_backend,
    inspect_filesystems_grouped as svc_inspect_filesystems_grouped,
    inspect_get_filesystems_for_root as svc_inspect_get_filesystems_for_root,
    launch_backend,
    partition_to_device,
    partition_to_number,
    shutdown_backend,
)
from .ssh_analyzer import SSHAnalyzer
from .storage_analyzer import StorageAnalyzer
from .systemd import JournalctlManager, SystemConfigManager, SystemctlManager, SystemdAnalyzer
from .systemd_journal import SystemdJournalManager
from .systemd_mgr import SystemdManager
from .systemd_networkd import SystemdNetworkdManager
from .systemd_units import SystemdUnitsManager
from .user_activity import UserActivityAnalyzer
from .vulnerability_scanner import VulnerabilityScanner
from .webserver_analyzer import WebServerAnalyzer
from .windows_applications import WindowsApplicationManager
from .windows_detection import WindowsDetector
from .windows_drivers import WindowsDriverInjector
from .windows_registry import WindowsRegistryManager
from .windows_services import WindowsServiceManager
from .windows_users import WindowsUserManager

if TYPE_CHECKING:
    from pathlib import Path

    from .nbd import NBDDeviceManager
    from .storage import StorageStackActivator

logger = logging.getLogger(__name__)
TManager = TypeVar("TManager")  # pylint: disable=invalid-name  # standard TypeVar naming convention (T-prefixed)


class VMCraft:  # pylint: disable=too-many-instance-attributes,too-many-public-methods  # main API coordinating ~30 specialized subsystem modules
    """
    Native VM disk manipulation API.

    Uses qemu-nbd + Linux tools for comprehensive guest filesystem access.
    Provides 480+ methods for VM manipulation and configuration.

    This is the main entry point that coordinates all specialized modules.
    Methods are provided by composition via ops classes and exposed through
    ``__getattr__`` for full backward compatibility.
    """

    def __init__(  # pylint: disable=too-many-statements  # initializes ~30 independent lazily-created subsystem manager slots
        self,
        python_return_dict: bool = True,
        conversion_dir: str | Path | None = None,
        allowed_dirs: list[str] | None = None,
        container_isolation: bool = True,
    ):
        """
        Initialize VMCraft.

        Args:
            python_return_dict: Return dicts instead of tuples (default: True)
            conversion_dir: Directory for VMDK conversion temp files.
                           Defaults to ~/.cache/hyper2kvm/conversions
            allowed_dirs: Additional directories allowed for VM image access (security).
                         If None, uses default allowed directories.
            container_isolation: Run LVM activation inside a Podman container.
        """
        self._return_dict = python_return_dict
        self._conversion_dir = conversion_dir  # Store for NBD manager creation
        self._allowed_dirs = allowed_dirs  # Store for NBD security configuration
        self._container_isolation = container_isolation
        self._drives: list[dict[str, Any]] = []
        self._nbd_manager: NBDDeviceManager | None = None
        self._nbd_device: str | None = None
        self._storage_activator: StorageStackActivator | None = None
        self._storage_audit: dict[str, Any] | None = None
        # Multi-drive per-drive state (populated by launch_backend)
        self._nbd_managers: list[NBDDeviceManager] = []
        self._nbd_devices: list[str] = []
        self._storage_activators: list[StorageStackActivator] = []
        self._mount_root: Path | None = None
        self._launched = False
        self._trace = False
        self._perf_metrics: dict[str, float] = {}
        self.logger = logging.getLogger(__name__)

        # Performance caches
        self._partition_cache: dict[str, tuple[list[str], float]] = {}
        self._blkid_cache: dict[str, tuple[dict[str, str], float]] = {}
        self._blkid_cache_ttl: int = 120  # 2 minutes TTL for blkid cache

        # Specialized managers (initialized after launch)
        self._mount_manager: MountManager | None = None
        self._file_ops: FileOperations | None = None
        self._linux_detector: LinuxDetector | None = None
        self._windows_detector: WindowsDetector | None = None
        self._os_inspector: OSInspector | None = None
        self._win_registry: WindowsRegistryManager | None = None
        self._win_drivers: WindowsDriverInjector | None = None
        self._win_users: WindowsUserManager | None = None
        self._win_services: WindowsServiceManager | None = None
        self._win_apps: WindowsApplicationManager | None = None
        self._linux_services: LinuxServiceManager | None = None
        self._network_config: NetworkConfigAnalyzer | None = None
        self._firewall_analyzer: FirewallAnalyzer | None = None
        self._advanced_analyzer: AdvancedAnalyzer | None = None
        self._export_mgr: ExportManager | None = None
        self._scheduled_tasks: ScheduledTaskAnalyzer | None = None
        self._ssh_analyzer: SSHAnalyzer | None = None
        self._log_analyzer: LogAnalyzer | None = None
        self._hardware_detector: HardwareDetector | None = None
        self._backup_mgr: BackupManager | None = None
        self._security_auditor: SecurityAuditor | None = None
        self._disk_optimizer: DiskOptimizer | None = None
        self._database_detector: DatabaseDetector | None = None
        self._webserver_analyzer: WebServerAnalyzer | None = None
        self._certificate_manager: CertificateManager | None = None
        self._container_analyzer: ContainerAnalyzer | None = None
        self._compliance_checker: ComplianceChecker | None = None
        self._backup_analysis: BackupAnalysis | None = None
        self._user_activity: UserActivityAnalyzer | None = None
        self._app_framework_detector: AppFrameworkDetector | None = None
        self._cloud_detector: CloudDetector | None = None
        self._monitoring_detector: MonitoringDetector | None = None
        self._vulnerability_scanner: VulnerabilityScanner | None = None
        self._license_detector: LicenseDetector | None = None
        self._performance_analyzer: PerformanceAnalyzer | None = None
        self._migration_planner: MigrationPlanner | None = None
        self._dependency_mapper: DependencyMapper | None = None
        self._forensic_analyzer: ForensicAnalyzer | None = None
        self._data_discovery: DataDiscovery | None = None
        self._config_tracker: ConfigTracker | None = None
        self._network_topology: NetworkTopology | None = None
        self._storage_analyzer: StorageAnalyzer | None = None
        self._cloud_optimizer: CloudOptimizer | None = None
        self._disaster_recovery: DisasterRecovery | None = None

        # Systemd managers (initialized after launch)
        self._systemctl: SystemctlManager | None = None
        self._journalctl: JournalctlManager | None = None
        self._systemd_analyze: SystemdAnalyzer | None = None
        self._sysconfig: SystemConfigManager | None = None
        self._systemd_mgr: SystemdManager | None = None
        self._systemd_networkd: SystemdNetworkdManager | None = None
        self._systemd_journal: SystemdJournalManager | None = None
        self._systemd_units: SystemdUnitsManager | None = None

        # Enhanced inspection (initialized after launch)
        self._enhanced_inspector: EnhancedInspector | None = None

        # Augeas configuration management (initialized after launch)
        self._augeas: Any | None = None

        # Hivex compatibility shim state (populated by hivex_open())
        self._hivex_handles: dict[int, tuple] = {}
        self._hivex_last_handle: int | None = None

        # Initialize ops instances (created immediately; guards handle pre-launch errors)
        self._ops_instances: list[object] = []
        self._initialize_ops()

        # Log backend selection
        self.logger.debug("Using VMCraft backend (qemu-nbd + Linux tools)")

    # ==================================================================================
    # Ops composition — created in __init__, methods exposed via __getattr__
    # ==================================================================================

    def _initialize_ops(self) -> None:
        """Create all ops instances that provide the flat API surface."""
        self.mounting = MountOps(self)
        self.files = FileOps(self)
        self.inspection = InspectionOps(self)
        self.filesystem = FilesystemOps(self)
        self.disk = DiskOps(self)
        self.storage = StorageOps(self)
        self.systemd = SystemdOps(self)
        self.windows = WindowsOps(self)
        self.linux = LinuxOps(self)
        self.security = SecurityOps(self)
        self.analyzer = AnalyzerOps(self)
        self.augeas_ops = AugeasOps(self)
        self._ops_instances = [
            self.mounting,
            self.files,
            self.inspection,
            self.filesystem,
            self.disk,
            self.storage,
            self.systemd,
            self.windows,
            self.linux,
            self.security,
            self.analyzer,
            self.augeas_ops,
        ]

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute lookups to ops instances for backward compatibility."""
        # Avoid infinite recursion: _ops_instances must be found via __dict__
        ops = self.__dict__.get("_ops_instances")
        if ops:
            for instance in ops:
                try:
                    return getattr(instance, name)
                except AttributeError:
                    continue
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    # ==================================================================================
    # Hivex compatibility shim (guestfs API emulation for Windows registry access)
    # ==================================================================================

    def hivex_open(self, hive_path: str, *_args: Any) -> int:
        """
        Open a Windows registry hive file for reading.

        Emulates guestfs hivex_open() by downloading the hive from the guest
        filesystem and opening it with python-hivex. Returns a handle ID.
        """
        import tempfile  # pylint: disable=import-outside-toplevel  # only needed for the (rarely used) hivex compatibility shim

        try:
            import hivex as _hivex  # pylint: disable=import-outside-toplevel  # optional dependency, only needed for Windows registry access
        except ImportError as err:
            raise AttributeError(
                "Windows registry access requires python-hivex. Install it with: dnf install python3-hivex"
            ) from err

        data = self.read_file(hive_path)
        if not data or len(data) < 4096:
            raise RuntimeError(f"Failed to read hive: {hive_path}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".hiv") as tmp:
            tmp.write(data)

        try:
            h = _hivex.Hivex(tmp.name, write=False)
        except Exception:
            os.unlink(tmp.name)
            raise

        handle_id = id(h)
        self._hivex_handles[handle_id] = (h, tmp.name)
        # Track last-opened handle for handle-less guestfs API calls
        self._hivex_last_handle = handle_id
        return handle_id

    def _get_hivex(self, handle_id: int):
        """Get the python-hivex object for a handle ID."""
        handles = getattr(self, "_hivex_handles", {})
        entry = handles.get(handle_id)
        if not entry:
            raise RuntimeError("Invalid hivex handle")
        return entry[0]

    def _get_last_hivex(self):
        """Get the most recently opened hivex object (for handle-less API calls)."""
        hid = getattr(self, "_hivex_last_handle", None)
        if hid is not None:
            return self._get_hivex(hid)
        raise RuntimeError("No hivex handle open")

    def hivex_close(self, handle_id: int) -> None:
        """Close a hivex handle and clean up temp file."""
        handles = getattr(self, "_hivex_handles", None)
        if handles is None:
            return
        entry = handles.pop(handle_id, None)
        if entry:
            h, tmp_path = entry
            try:
                h.close()
            except Exception:  # pylint: disable=broad-exception-caught  # hivex is a dynamic library; best-effort close must not abort cleanup
                pass
            try:
                os.unlink(tmp_path)
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort temp file cleanup, must not raise
                pass
        # Clear last handle if it was this one
        if getattr(self, "_hivex_last_handle", None) == handle_id:
            self._hivex_last_handle = None

    def hivex_root(self, handle_id: int) -> int:
        """Get the root node ID of an open hive (uses the given handle)."""
        return self._get_hivex(handle_id).root()

    def hivex_node_get_child(self, handle_id: int, node: int, name: str):
        """Get a named child node of ``node`` in the hive for ``handle_id``."""
        return self._get_hivex(handle_id).node_get_child(node, name)

    def hivex_node_children(self, node: int) -> list:
        """List children of a node (uses last-opened hive)."""
        return self._get_last_hivex().node_children(node)

    def hivex_node_name(self, node: int) -> str:
        """Get name of a node (uses last-opened hive)."""
        return self._get_last_hivex().node_name(node)

    def hivex_node_values(self, node: int) -> list:
        """List values of a node (uses last-opened hive)."""
        return self._get_last_hivex().node_values(node)

    def hivex_node_get_value(self, handle_id: int, node: int, name: str):
        """Get a named value from ``node`` in the hive for ``handle_id``."""
        return self._get_hivex(handle_id).node_get_value(node, name)

    def hivex_value_key(self, val: int) -> str:
        """Get value key name (uses last-opened hive)."""
        return self._get_last_hivex().value_key(val)

    def hivex_value_type(self, val: int) -> int:
        """Get value type (uses last-opened hive)."""
        t, _ = self._get_last_hivex().value_value(val)
        return t

    def hivex_value_value(self, val: int) -> bytes:
        """Get value data (uses last-opened hive)."""
        _, data = self._get_last_hivex().value_value(val)
        return data

    def hivex_value_string(self, handle_id: int, val: int) -> str:
        """Decode a REG_SZ/REG_EXPAND_SZ/REG_MULTI_SZ value to a string (uses the given handle)."""
        h = self._get_hivex(handle_id)
        t, data = h.value_value(val)
        if t in (1, 2):  # REG_SZ, REG_EXPAND_SZ
            return data.decode("utf-16-le", errors="ignore").rstrip("\x00")
        if t == 7:  # REG_MULTI_SZ
            return data.decode("utf-16-le", errors="ignore").rstrip("\x00")
        return data.decode("utf-8", errors="ignore")

    def hivex_commit(self, handle_id: int) -> None:
        """Commit changes (no-op for read-only handles)."""

    # ==================================================================================
    # Infrastructure methods (moved from StorageMixin / SystemdMixin)
    # ==================================================================================

    def _dispatch_manager_attr_call(
        self,
        manager_attr: str,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke a manager method through a launched component attribute guard."""
        manager = self._require_component_attr(manager_attr)
        return getattr(manager, method)(*args, **kwargs)

    def _require_launched_component(self, component: TManager | None) -> TManager:
        """Ensure component/manager is initialized before use."""
        if not component:
            raise RuntimeError("VMCraft not initialized. Call launch() before performing disk operations.")
        return component

    def _require_component_attr(self, attr_name: str) -> Any:
        """Resolve a component attribute and enforce launched guard semantics."""
        return self._require_launched_component(getattr(self, attr_name))

    def _enhanced_inspector_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to enhanced inspector manager."""
        return self._dispatch_manager_attr_call("_enhanced_inspector", method, *args, **kwargs)

    def _run_sudo_stdout(self, cmd: list[str]) -> str:
        """Run command with sudo helper and return captured stdout."""
        run_cmd = self._get_run_command()
        return run_cmd(
            self.logger,
            cmd,
            check=True,
            capture=True,
            failure_log_level=logging.DEBUG,
        ).stdout

    def _get_run_command(self) -> Callable[..., Any]:
        """Resolve command runner dynamically so tests/patching can override it."""
        # pylint: disable-next=import-outside-toplevel  # re-resolved per call so test patching of run_sudo takes effect
        from hyper2kvm.vmcraft import _utils

        return _utils.run_sudo

    def _sudo_service_call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call helper that takes (logger, run_sudo, ...)."""
        return fn(self.logger, self._get_run_command(), *args, **kwargs)

    def _sudo_mount_service_call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call helper that takes (logger, run_sudo, mount_root=..., ...)."""
        mount_root = self._require_mount_root()
        return fn(self.logger, self._get_run_command(), *args, mount_root=mount_root, **kwargs)

    def _offline_systemd_mount_call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call offline systemd helper that takes (logger, mount_root, ...)."""
        return self._offline_systemd_call(
            fn,
            *args,
            requires_mount_root=True,
            pass_mount_root=True,
            **kwargs,
        )

    def _offline_systemd_command_call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call offline systemd helper that takes (logger, command_quiet, ...)."""
        return self._offline_systemd_call(
            fn,
            *args,
            requires_mount_root=True,
            pass_command_quiet=True,
            **kwargs,
        )

    def _offline_systemd_run_command_call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call offline systemd helper that takes (logger, mount_root, run_command=...)."""
        return self._offline_systemd_call(
            fn,
            *args,
            requires_mount_root=True,
            pass_mount_root=True,
            run_command=self._run_sudo_stdout,
            **kwargs,
        )

    def _offline_systemd_call(
        self,
        fn: Callable[..., Any],
        *args: Any,
        requires_mount_root: bool = False,
        pass_mount_root: bool = False,
        pass_command_quiet: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Generic dispatcher for offline-systemd helper signatures."""
        mount_root: Path | None = None
        if requires_mount_root:
            mount_root = self._require_mount_root()

        call_args: list[Any] = [self.logger]
        if pass_mount_root:
            call_args.append(mount_root)
        if pass_command_quiet:
            call_args.append(self.command_quiet)
        call_args.extend(args)
        return fn(*call_args, **kwargs)

    # ==================================================================================
    # Lifecycle and setup
    # ==================================================================================

    def set_trace(self, enable: int | bool) -> None:
        """Enable debug tracing."""
        self._trace = bool(enable)
        if self._trace:
            self.logger.setLevel(logging.DEBUG)

    def add_drive_opts(  # pylint: disable=redefined-builtin  # mirrors the guestfs.GuestFS.add_drive_opts() API signature for compatibility
        self, path: str, *, readonly: int | bool = 1, format: str | None = None, **_kwargs
    ) -> None:
        """
        Add a disk image.

        Args:
            path: Path to disk image
            readonly: Mount read-only (default: True)
            format: Disk format (qcow2, vmdk, raw, etc.)
            **kwargs: Other options (ignored for compatibility)
        """
        if self._launched:
            raise RuntimeError(
                "Cannot add drives after VMCraft has been launched. Add all drives before calling launch()."
            )

        self._drives.append(
            {
                "path": str(path),
                "readonly": bool(readonly),
                "format": format,
            }
        )

    def launch(self) -> None:
        """
        Launch the backend.

        Connects NBD devices, activates storage stack, creates mount root,
        and initializes all specialized managers.
        """
        launch_backend(self)

    def _initialize_runtime_managers(self) -> None:  # pylint: disable=too-many-statements  # one straight-line assignment per specialized manager
        """Initialize all specialized managers after mount root is ready."""
        self._mount_manager = MountManager(self.logger, self._mount_root)
        self._file_ops = FileOperations(self.logger, self._mount_root, enable_cache=True, cache_size=1000)
        self._linux_detector = LinuxDetector(self.logger, self._mount_root)
        self._windows_detector = WindowsDetector(self.logger, self._mount_root)
        self._os_inspector = OSInspector(
            self.logger, self._mount_root, self._linux_detector, self._windows_detector
        )
        self._win_registry = WindowsRegistryManager(self.logger, self._mount_root)
        self._win_drivers = WindowsDriverInjector(self.logger, self._mount_root)
        self._win_users = WindowsUserManager(self.logger, self._mount_root)
        self._win_services = WindowsServiceManager(self.logger, self._mount_root)
        self._win_apps = WindowsApplicationManager(self.logger, self._mount_root)
        self._linux_services = LinuxServiceManager(self.logger, self._mount_root)
        self._network_config = NetworkConfigAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._firewall_analyzer = FirewallAnalyzer(self.logger, self._file_ops)
        self._advanced_analyzer = AdvancedAnalyzer(self.logger, self._file_ops)
        self._export_mgr = ExportManager(self.logger)
        self._scheduled_tasks = ScheduledTaskAnalyzer(self.logger, self._file_ops)
        self._ssh_analyzer = SSHAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._log_analyzer = LogAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._hardware_detector = HardwareDetector(self.logger, self._file_ops, self._mount_root)
        self._backup_mgr = BackupManager(self.logger, self._mount_root)
        self._security_auditor = SecurityAuditor(self.logger, self._mount_root)
        self._disk_optimizer = DiskOptimizer(self.logger, self._mount_root)
        self._database_detector = DatabaseDetector(self.logger, self._file_ops, self._mount_root)
        self._webserver_analyzer = WebServerAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._certificate_manager = CertificateManager(self.logger, self._file_ops, self._mount_root)
        self._container_analyzer = ContainerAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._compliance_checker = ComplianceChecker(self.logger, self._file_ops, self._mount_root)
        self._backup_analysis = BackupAnalysis(self.logger, self._file_ops, self._mount_root)
        self._user_activity = UserActivityAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._app_framework_detector = AppFrameworkDetector(self.logger, self._file_ops, self._mount_root)
        self._cloud_detector = CloudDetector(self.logger, self._file_ops, self._mount_root)
        self._monitoring_detector = MonitoringDetector(self.logger, self._file_ops, self._mount_root)
        self._vulnerability_scanner = VulnerabilityScanner(self.logger, self._file_ops, self._mount_root)
        self._license_detector = LicenseDetector(self.logger, self._file_ops, self._mount_root)
        self._performance_analyzer = PerformanceAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._migration_planner = MigrationPlanner(self.logger, self._file_ops, self._mount_root)
        self._dependency_mapper = DependencyMapper(self.logger, self._file_ops, self._mount_root)
        self._forensic_analyzer = ForensicAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._data_discovery = DataDiscovery(self.logger, self._file_ops, self._mount_root)
        self._config_tracker = ConfigTracker(self.logger, self._file_ops, self._mount_root)
        self._network_topology = NetworkTopology(self.logger, self._file_ops, self._mount_root)
        self._storage_analyzer = StorageAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._cloud_optimizer = CloudOptimizer(self.logger, self._file_ops, self._mount_root)
        self._disaster_recovery = DisasterRecovery(self.logger, self._file_ops, self._mount_root)

        # Initialize systemd managers
        self._systemctl = SystemctlManager(self.command_quiet, self.logger)
        self._journalctl = JournalctlManager(self.command_quiet, self.logger)
        self._systemd_analyze = SystemdAnalyzer(self.command_quiet, self.logger)
        self._sysconfig = SystemConfigManager(self.command_quiet, self.logger)
        self._systemd_mgr = SystemdManager(self.logger, str(self._mount_root))
        self._systemd_networkd = SystemdNetworkdManager(self.logger, str(self._mount_root))
        self._systemd_journal = SystemdJournalManager(self.logger, str(self._mount_root))
        self._systemd_units = SystemdUnitsManager(self.logger, str(self._mount_root))

        # Initialize enhanced inspector
        self._enhanced_inspector = EnhancedInspector(
            mount_root=self._mount_root,
            logger=self.logger,
            cat_func=self.cat,
            exists_func=self.exists,
            is_dir_func=self.is_dir,
            ls_func=self.ls,
        )

        # Initialize Augeas manager (lazy - call aug_init() to activate)
        self._augeas = AugeasManager(self.logger, str(self._mount_root))

    # ==================================================================================
    # _require_* guards (only those actually referenced by ops classes)
    # ==================================================================================

    def _require_mount_root(self) -> Path:
        return self._require_component_attr("_mount_root")

    def _require_nbd_device(self) -> str:
        return self._require_component_attr("_nbd_device")

    def _require_os_inspector(self) -> OSInspector:
        return self._require_component_attr("_os_inspector")

    def _require_file_ops(self) -> FileOperations:
        return self._require_component_attr("_file_ops")

    def _require_mount_manager(self) -> MountManager:
        return self._require_component_attr("_mount_manager")

    # ==================================================================================
    # Lifecycle
    # ==================================================================================

    def sync(self) -> None:
        """Flush filesystem buffers to disk."""
        if not self._launched:
            return

        os.sync()
        self.logger.debug("VMCraft sync: flushed filesystem buffers")

    def shutdown(self) -> None:
        """Shutdown the backend."""
        shutdown_backend(self)

    @property
    def converted_image_path(self) -> Path | None:
        """
        Get path to converted qcow2 if a conversion was performed.

        Returns None if no conversion was needed, or the path to the temporary
        qcow2 file if the original VMDK required conversion.
        """
        if self._nbd_manager:
            return self._nbd_manager.converted_image_path
        return None

    def keep_converted_image(self) -> None:
        """
        Preserve the converted qcow2 image (don't delete on shutdown).

        Call this after launch() if you want to keep the temporary converted
        qcow2 for further processing (e.g., as input to final conversion).
        """
        if self._nbd_manager:
            self._nbd_manager.keep_converted_image()

    def close(self) -> None:
        """Close and cleanup."""
        close_backend(self)

    # ==================================================================================
    # Utility / Info APIs (direct methods that stay on VMCraft)
    # ==================================================================================

    def get_backend_info(self) -> dict[str, Any]:
        """Get information about the VMCraft backend."""
        return {
            "backend": "vmcraft",
            "implementation": "VMCraft - Python disk manipulation library",
            "version": "1.0.0",
            "features": {
                "nbd_based": True,
                "requires_root": True,
                "guestfs_api_compatible": True,
                "performance": "5x faster startup, 10x less memory",
                "windows_support": True,
                "driver_injection": True,
                "registry_operations": True,
            },
            "launched": self._launched,
            "nbd_device": self._nbd_device if self._launched else None,
            "nbd_devices": list(self._nbd_devices) if self._launched else [],
            "drive_count": len(self._drives),
            "mount_root": str(self._mount_root) if self._mount_root else None,
        }

    def part_to_partnum(self, partition: str) -> int:
        """
        Extract partition number from partition device path.

        Examples:
            /dev/sda1 -> 1
            /dev/nvme0n1p2 -> 2
            /dev/nbd0p3 -> 3

        Raises:
            RuntimeError: If partition number cannot be extracted
        """
        return partition_to_number(partition)

    def part_to_dev(self, partition: str) -> str:
        """
        Get parent device from partition path.

        Examples:
            /dev/sda1 -> /dev/sda
            /dev/nvme0n1p2 -> /dev/nvme0n1
            /dev/nbd0p3 -> /dev/nbd0

        Raises:
            RuntimeError: If parent device cannot be determined
        """
        return partition_to_device(partition)

    def blockdev_getss(self, device: str) -> int:
        """
        Get logical sector size in bytes.

        Uses /sys/block/*/queue/logical_block_size for NBD devices.
        Falls back to blockdev --getss command.

        Returns:
            Sector size in bytes (typically 512 or 4096)
        """
        return self._sudo_service_call(svc_blockdev_getss, device)

    def blockdev_getbsz(self, device: str) -> int:
        """
        Get block size in bytes.

        Returns:
            Block size in bytes (typically 4096)
        """
        return self._sudo_service_call(svc_blockdev_getbsz, device)

    def blockdev_setrw(self, device: str) -> None:
        """
        Set block device to read-write mode.

        Args:
            device: Device path
        """
        self._sudo_service_call(svc_blockdev_setrw, device)

    def blockdev_setro(self, device: str) -> None:
        """
        Set block device to read-only mode.

        Args:
            device: Device path
        """
        self._sudo_service_call(svc_blockdev_setro, device)

    def blockdev_getro(self, device: str) -> bool:
        """
        Check if block device is read-only.

        Args:
            device: Device path

        Returns:
            True if read-only, False if read-write
        """
        return self._sudo_service_call(svc_blockdev_getro, device)

    def blockdev_flushbufs(self, device: str) -> None:
        """
        Flush buffers for block device.

        Args:
            device: Device path
        """
        self._sudo_service_call(svc_blockdev_flushbufs, device)

    def blockdev_rereadpt(self, device: str) -> None:
        """
        Re-read partition table (equivalent to partprobe).

        Args:
            device: Device path
        """
        self._sudo_service_call(svc_blockdev_rereadpt, device)

    def inspect_filesystems(self) -> dict[str, list[str]]:
        """
        Inspect and return filesystems for each detected OS root.

        This is a convenience wrapper over list_filesystems() that groups
        filesystems by detected operating system roots.

        Returns:
            Dict mapping root device to list of filesystem devices
            Example: {"/dev/nbd0p2": ["/dev/nbd0p1", "/dev/nbd0p2"]}
        """
        return svc_inspect_filesystems_grouped(
            os_inspector=self._os_inspector,
            list_filesystems_fn=self.list_filesystems,
            inspect_os_fn=self.inspect_os,
            part_to_dev_fn=self.part_to_dev,
        )

    def inspect_get_filesystems(self, root: str) -> list[str]:
        """
        Get list of filesystems for specified OS root.

        Args:
            root: Root device path (e.g., /dev/nbd0p2)

        Returns:
            List of filesystem device paths on same disk
        """
        return svc_inspect_get_filesystems_for_root(root, self.inspect_filesystems)

    # ==================================================================================

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        try:
            self.close()
        except Exception as e:  # pylint: disable=broad-exception-caught  # context-manager cleanup must not raise and mask the original exception
            self.logger.exception("Error during cleanup: %s", e)
        return False
