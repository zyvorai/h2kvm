# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Resource Control Integration
=====================================

CPU, memory, and IO resource control using systemd cgroups v2.
Real-time monitoring and constraint management for VM operations.
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import dbus

    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


@dataclass
class ResourceLimits:
    """Resource limit configuration"""

    cpu_quota: Optional[str] = None  # e.g., "50%"
    cpu_weight: Optional[int] = None  # 1-10000, default 100
    memory_max: Optional[str] = None  # e.g., "2G"
    memory_high: Optional[str] = None  # Soft limit
    io_weight: Optional[int] = None  # 1-10000, default 100
    io_read_bps_max: Optional[str] = None  # e.g., "100M"
    io_write_bps_max: Optional[str] = None
    tasks_max: Optional[int] = None  # Max number of tasks


@dataclass
class ResourceUsage:
    """Current resource usage snapshot"""

    cpu_percent: float
    memory_bytes: int
    memory_percent: float
    io_read_bytes: int
    io_write_bytes: int
    num_threads: int
    num_fds: int
    timestamp: float


class SystemdResourceControl:
    """Manage systemd resource controls for processes"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.bus = None
        self.systemd_manager = None

        if DBUS_AVAILABLE:
            self._setup_dbus()
        else:
            self.logger.warning(
                "DBus not available, resource control will be limited.\n"
                "    Ensure dbus-daemon is running: systemctl status dbus\n"
                "    Install with: pip install dbus-python  (or: dnf install python3-dbus)"
            )

    def _setup_dbus(self):
        """Initialize DBus connection for systemd"""
        try:
            self.bus = dbus.SystemBus()
            self.systemd_manager = self.bus.get_object(
                "org.freedesktop.systemd1", "/org/freedesktop/systemd1"
            )
            self.logger.info("DBus connection established for resource control")
        except Exception as e:
            self.logger.warning(f"Failed to setup DBus: {e}")

    def apply_limits(self, pid: int, limits: ResourceLimits, scope_name: Optional[str] = None) -> bool:
        """Apply resource limits to a process via transient scope

        Args:
            pid: Process ID to control
            limits: Resource limits to apply
            scope_name: Optional custom scope name

        Returns:
            True if limits were successfully applied
        """
        if not DBUS_AVAILABLE or not self.systemd_manager:
            self.logger.warning(
                "Cannot apply limits: DBus not available.\n"
                "    Ensure dbus-daemon is running: systemctl status dbus\n"
                "    Install with: pip install dbus-python  (or: dnf install python3-dbus)"
            )
            return self._apply_limits_via_systemd_run(pid, limits, scope_name)

        try:
            if scope_name is None:
                scope_name = f"hyper2kvm-{pid}"

            full_scope_name = f"{scope_name}.scope"

            # Build property list
            properties = [("Description", f"Hyper2KVM Process {pid}")]

            if limits.cpu_quota:
                # Convert percentage to systemd format (e.g., "50%" -> 50%)
                quota = limits.cpu_quota.rstrip("%")
                properties.append(("CPUQuota", f"{quota}%"))

            if limits.cpu_weight:
                properties.append(("CPUWeight", dbus.UInt64(limits.cpu_weight)))

            if limits.memory_max:
                mem_bytes = self._parse_size(limits.memory_max)
                properties.append(("MemoryMax", dbus.UInt64(mem_bytes)))

            if limits.memory_high:
                mem_bytes = self._parse_size(limits.memory_high)
                properties.append(("MemoryHigh", dbus.UInt64(mem_bytes)))

            if limits.io_weight:
                properties.append(("IOWeight", dbus.UInt64(limits.io_weight)))

            if limits.tasks_max:
                properties.append(("TasksMax", dbus.UInt64(limits.tasks_max)))

            # Create transient scope
            interface = dbus.Interface(self.systemd_manager, "org.freedesktop.systemd1.Manager")

            interface.StartTransientUnit(
                full_scope_name,
                "fail",
                properties,
                [("PIDs", dbus.Array([dbus.UInt32(pid)], signature="u"))],
            )

            self.logger.info(f"Applied resource limits to PID {pid} via scope {full_scope_name}")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to apply resource limits via DBus: {e}")
            return self._apply_limits_via_systemd_run(pid, limits, scope_name)

    def _apply_limits_via_systemd_run(
        self, pid: int, limits: ResourceLimits, scope_name: Optional[str] = None
    ) -> bool:
        """Fallback: Apply limits using systemd-run command"""
        try:
            if scope_name is None:
                scope_name = f"hyper2kvm-{pid}"

            cmd = ["systemd-run", "--scope", "--unit", scope_name, f"--property=PIDs={pid}"]

            if limits.cpu_quota:
                cmd.append(f"--property=CPUQuota={limits.cpu_quota}")

            if limits.cpu_weight:
                cmd.append(f"--property=CPUWeight={limits.cpu_weight}")

            if limits.memory_max:
                cmd.append(f"--property=MemoryMax={limits.memory_max}")

            if limits.memory_high:
                cmd.append(f"--property=MemoryHigh={limits.memory_high}")

            if limits.io_weight:
                cmd.append(f"--property=IOWeight={limits.io_weight}")

            if limits.tasks_max:
                cmd.append(f"--property=TasksMax={limits.tasks_max}")

            # Need a dummy command
            cmd.append("true")

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                self.logger.info(f"Applied resource limits to PID {pid} via systemd-run")
                return True
            self.logger.error(f"systemd-run failed: {result.stderr}")
            return False

        except Exception as e:
            self.logger.exception(f"Failed to apply limits via systemd-run: {e}")
            return False

    def get_cgroup_path(self, pid: int) -> Optional[Path]:
        """Get cgroup v2 path for a process

        Args:
            pid: Process ID

        Returns:
            Path to cgroup directory or None
        """
        try:
            cgroup_file = Path(f"/proc/{pid}/cgroup")
            if not cgroup_file.exists():
                return None

            content = cgroup_file.read_text()
            # cgroup v2 format: 0::/path
            for line in content.split("\n"):
                if line.startswith("0::"):
                    cgroup_rel_path = line.split("::", 1)[1]
                    return Path("/sys/fs/cgroup") / cgroup_rel_path.lstrip("/")

            return None

        except Exception as e:
            self.logger.exception(f"Failed to get cgroup path for PID {pid}: {e}")
            return None

    def read_cgroup_stat(self, pid: int, stat_file: str) -> Optional[str]:
        """Read a cgroup stat file for a process

        Args:
            pid: Process ID
            stat_file: Stat file name (e.g., 'cpu.stat', 'memory.current')

        Returns:
            File contents or None
        """
        cgroup_path = self.get_cgroup_path(pid)
        if not cgroup_path:
            return None

        stat_path = cgroup_path / stat_file
        try:
            if stat_path.exists():
                return stat_path.read_text()
        except Exception as e:
            self.logger.debug(f"Failed to read {stat_file}: {e}")

        return None

    def get_current_limits(self, pid: int) -> dict[str, str]:
        """Get current resource limits for a process

        Args:
            pid: Process ID

        Returns:
            Dictionary of current limits
        """
        limits = {}
        cgroup_path = self.get_cgroup_path(pid)

        if not cgroup_path:
            return limits

        # Read various limit files
        limit_files = {
            "cpu.max": "cpu_quota",
            "cpu.weight": "cpu_weight",
            "memory.max": "memory_max",
            "memory.high": "memory_high",
            "io.weight": "io_weight",
            "pids.max": "tasks_max",
        }

        for file, key in limit_files.items():
            try:
                file_path = cgroup_path / file
                if file_path.exists():
                    limits[key] = file_path.read_text().strip()
            except Exception as e:
                self.logger.debug(f"Failed to read {file}: {e}")

        return limits

    @staticmethod
    def _parse_size(size_str: str) -> int:
        """Parse size string to bytes

        Args:
            size_str: Size string like '2G', '500M', etc.

        Returns:
            Size in bytes
        """
        size_str = size_str.upper().strip()
        multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

        if size_str[-1] in multipliers:
            return int(float(size_str[:-1]) * multipliers[size_str[-1]])

        return int(size_str)


class ResourceMonitor:
    """Monitor resource usage for processes"""

    def __init__(self, pid: int, interval: float = 1.0):
        """
        Args:
            pid: Process ID to monitor
            interval: Monitoring interval in seconds
        """
        self.pid = pid
        self.interval = interval
        self.logger = logging.getLogger(__name__)
        self.monitoring = False
        self.monitor_thread = None
        self.history: list[ResourceUsage] = []
        self.max_history = 300  # Keep 5 minutes at 1s interval

        if not PSUTIL_AVAILABLE:
            self.logger.warning(
                "psutil not available, monitoring will be limited.\n"
                "    Install with: pip install psutil  (or: dnf install python3-psutil)"
            )
            self.process = None
        else:
            try:
                self.process = psutil.Process(pid)
            except psutil.NoSuchProcess:
                self.logger.exception(f"Process {pid} does not exist")
                self.process = None

    def start_monitoring(self):
        """Start background monitoring thread"""
        if self.monitoring:
            self.logger.warning("Monitoring already active")
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info(f"Started monitoring PID {self.pid}")

    def stop_monitoring(self):
        """Stop monitoring thread"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info(f"Stopped monitoring PID {self.pid}")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                usage = self.get_current_usage()
                if usage:
                    self.history.append(usage)

                    # Trim history
                    if len(self.history) > self.max_history:
                        self.history = self.history[-self.max_history :]

                    # Log warnings for high usage
                    self._check_thresholds(usage)

                time.sleep(self.interval)

            except Exception as e:
                self.logger.exception(f"Error in monitoring loop: {e}")
                time.sleep(self.interval)

    def get_current_usage(self) -> Optional[ResourceUsage]:
        """Get current resource usage snapshot

        Returns:
            ResourceUsage object or None
        """
        if not PSUTIL_AVAILABLE or not self.process:
            return None

        try:
            # Refresh process info
            self.process.cpu_percent()  # First call returns 0, need to call twice
            time.sleep(0.1)

            cpu_percent = self.process.cpu_percent()
            mem_info = self.process.memory_info()
            mem_percent = self.process.memory_percent()
            num_threads = self.process.num_threads()

            # Get IO stats if available
            io_counters = self.process.io_counters() if hasattr(self.process, "io_counters") else None
            io_read = io_counters.read_bytes if io_counters else 0
            io_write = io_counters.write_bytes if io_counters else 0

            # Get FD count
            try:
                num_fds = self.process.num_fds() if hasattr(self.process, "num_fds") else 0
            except (AttributeError, psutil.AccessDenied):
                num_fds = 0

            return ResourceUsage(
                cpu_percent=cpu_percent,
                memory_bytes=mem_info.rss,
                memory_percent=mem_percent,
                io_read_bytes=io_read,
                io_write_bytes=io_write,
                num_threads=num_threads,
                num_fds=num_fds,
                timestamp=time.time(),
            )

        except psutil.NoSuchProcess:
            self.logger.warning(f"Process {self.pid} no longer exists")
            self.monitoring = False
            return None
        except Exception as e:
            self.logger.exception(f"Failed to get resource usage: {e}")
            return None

    def _check_thresholds(self, usage: ResourceUsage):
        """Check usage against warning thresholds"""
        # CPU warning at 90%
        if usage.cpu_percent > 90:
            self.logger.warning(f"High CPU usage: {usage.cpu_percent:.1f}% for PID {self.pid}")

        # Memory warning at 80%
        if usage.memory_percent > 80:
            self.logger.warning(
                f"High memory usage: {usage.memory_percent:.1f}% "
                f"({usage.memory_bytes / 1024**3:.2f} GB) for PID {self.pid}"
            )

        # Thread count warning at 1000
        if usage.num_threads > 1000:
            self.logger.warning(f"High thread count: {usage.num_threads} for PID {self.pid}")

    def get_statistics(self) -> dict:
        """Get statistical summary of resource usage

        Returns:
            Dictionary with min/max/avg statistics
        """
        if not self.history:
            return {}

        stats = {
            "samples": len(self.history),
            "duration": self.history[-1].timestamp - self.history[0].timestamp,
            "cpu": self._calculate_stats([u.cpu_percent for u in self.history]),
            "memory": self._calculate_stats([u.memory_bytes for u in self.history]),
            "memory_percent": self._calculate_stats([u.memory_percent for u in self.history]),
            "threads": self._calculate_stats([u.num_threads for u in self.history]),
        }

        # IO stats if available
        io_read = [u.io_read_bytes for u in self.history if u.io_read_bytes > 0]
        io_write = [u.io_write_bytes for u in self.history if u.io_write_bytes > 0]

        if io_read:
            stats["io_read"] = self._calculate_stats(io_read)
        if io_write:
            stats["io_write"] = self._calculate_stats(io_write)

        return stats

    @staticmethod
    def _calculate_stats(values: list[float]) -> dict[str, float]:
        """Calculate min/max/avg for a list of values"""
        if not values:
            return {}

        return {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "current": values[-1] if values else 0,
        }

    def get_recent_usage(self, seconds: int = 60) -> list[ResourceUsage]:
        """Get usage history for recent period

        Args:
            seconds: Number of seconds to look back

        Returns:
            List of ResourceUsage objects
        """
        if not self.history:
            return []

        cutoff = time.time() - seconds
        return [u for u in self.history if u.timestamp >= cutoff]

    def format_current_usage(self) -> str:
        """Format current usage as human-readable string

        Returns:
            Formatted usage string
        """
        usage = self.get_current_usage()
        if not usage:
            return "No usage data available"

        return (
            f"CPU: {usage.cpu_percent:.1f}% | "
            f"Memory: {usage.memory_bytes / 1024**3:.2f} GB ({usage.memory_percent:.1f}%) | "
            f"Threads: {usage.num_threads} | "
            f"I/O: R={usage.io_read_bytes / 1024**2:.1f}MB W={usage.io_write_bytes / 1024**2:.1f}MB"
        )


def create_resource_profile(profile_name: str) -> ResourceLimits:
    """Create pre-defined resource limit profiles

    Args:
        profile_name: Name of the profile ('low', 'medium', 'high', 'unlimited')

    Returns:
        ResourceLimits object
    """
    profiles = {
        "low": ResourceLimits(
            cpu_quota="25%", cpu_weight=50, memory_max="1G", memory_high="768M", io_weight=50, tasks_max=256
        ),
        "medium": ResourceLimits(
            cpu_quota="50%",
            cpu_weight=100,
            memory_max="2G",
            memory_high="1536M",
            io_weight=100,
            tasks_max=512,
        ),
        "high": ResourceLimits(
            cpu_quota="75%", cpu_weight=500, memory_max="4G", memory_high="3G", io_weight=500, tasks_max=1024
        ),
        "unlimited": ResourceLimits(cpu_weight=1000, io_weight=1000),
    }

    return profiles.get(profile_name.lower(), profiles["medium"])
