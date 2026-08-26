# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Core Systemd Integration
=========================

Deep integration with systemd for service management, logging, and control.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

try:
    import systemd.daemon
    import systemd.journal

    SYSTEMD_AVAILABLE = True
except ImportError:
    SYSTEMD_AVAILABLE = False

try:
    import dbus
    import dbus.mainloop.glib

    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


class SystemdIntegration:
    """Deep integration with systemd services"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.bus = None
        self.systemd_manager = None

        if not SYSTEMD_AVAILABLE:
            self.logger.warning(
                "Systemd Python bindings not available.\n"
                "    Install with: pip install systemd-python  (or: dnf install python3-systemd)"
            )
            return

        if DBUS_AVAILABLE:
            self._setup_dbus()

    def _setup_dbus(self):
        """Setup DBus connection for systemd control"""
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.bus = dbus.SystemBus()
            self.systemd_manager = self.bus.get_object(
                "org.freedesktop.systemd1", "/org/freedesktop/systemd1"
            )
        except Exception as e:
            self.logger.warning(f"Failed to setup DBus: {e}")

    def notify_ready(self):
        """Notify systemd that service is ready"""
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify("READY=1")
            self.logger.info("Notified systemd: service ready")

    def notify_status(self, status: str):
        """Send status update to systemd"""
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify(f"STATUS={status}")
            self.logger.debug(f"Systemd status: {status}")

    def notify_stopping(self):
        """Notify systemd that service is stopping"""
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify("STOPPING=1")
            self.logger.info("Notified systemd: service stopping")

    def watchdog_ping(self):
        """Send watchdog keepalive to systemd"""
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify("WATCHDOG=1")

    def create_service_unit(
        self, name: str, image_path: str, description: Optional[str] = None, schedule: Optional[str] = None
    ) -> Path:
        """Create systemd service unit for VM repair

        Args:
            name: Service name (e.g., 'vm-repair-web01')
            image_path: Path to VM disk image
            description: Service description
            schedule: Optional systemd calendar expression for timer

        Returns:
            Path to created service file
        """
        desc = description or f"VM Boot Repair for {name}"

        service_content = f"""[Unit]
Description={desc}
Documentation=man:h2kvm(1)
After=network.target libvirtd.service
Requires=libvirtd.service
Before=libvirt-guests.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/h2kvmctl --cmd local --vmdk {image_path} --output-dir /var/lib/libvirt/images --offline-fix
User=root
Group=root

# Performance
CPUSchedulingPolicy=batch
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=4

# Resource limits
MemoryMax=4G
TasksMax=512
CPUQuota=75%

# Security hardening
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictRealtime=yes
RestrictNamespaces=yes
LockPersonality=yes
NoNewPrivileges=yes

# Filesystem access
ReadWritePaths=/var/lib/libvirt/images /mnt/vmroot /var/log/h2kvm
ReadOnlyPaths=/usr /etc

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=h2kvm-{name}

[Install]
WantedBy=multi-user.target
"""

        service_path = Path(f"/etc/systemd/system/h2kvm-{name}.service")
        service_path.write_text(service_content)

        # Create timer if schedule provided
        if schedule:
            self._create_timer_unit(name, schedule)

        # Reload systemd
        subprocess.run(["systemctl", "daemon-reload"], check=False)

        self.logger.info(f"Created service unit: {service_path}")
        return service_path

    def _create_timer_unit(self, name: str, schedule: str):
        """Create systemd timer unit"""
        timer_content = f"""[Unit]
Description=Schedule VM repair for {name}
Requires=h2kvm-{name}.service

[Timer]
OnCalendar={schedule}
Persistent=true
RandomizedDelaySec=15min

[Install]
WantedBy=timers.target
"""

        timer_path = Path(f"/etc/systemd/system/h2kvm-{name}.timer")
        timer_path.write_text(timer_content)

        # Enable and start timer
        subprocess.run(["systemctl", "enable", f"h2kvm-{name}.timer"], check=False)
        subprocess.run(["systemctl", "start", f"h2kvm-{name}.timer"], check=False)

        self.logger.info(f"Created and started timer: {timer_path}")

    def create_transient_scope(self, pid: int, name: str, cpu_quota: str = "50%", memory_max: str = "2G"):
        """Create transient systemd scope for resource control

        Args:
            pid: Process ID to move to scope
            name: Scope name
            cpu_quota: CPU quota (e.g., "50%")
            memory_max: Memory limit (e.g., "2G")
        """
        if not DBUS_AVAILABLE or not self.systemd_manager:
            self.logger.warning(
                "DBus not available, cannot create scope.\n"
                "    Ensure dbus-daemon is running: systemctl status dbus\n"
                "    Install with: pip install dbus-python  (or: dnf install python3-dbus)"
            )
            return

        try:
            scope_name = f"h2kvm-{name}-{pid}.scope"

            properties = [
                ("Description", f"H2KVM Process {name}"),
                ("CPUQuota", cpu_quota),
                ("MemoryMax", self._parse_size(memory_max)),
                ("TasksMax", 512),
                ("IOWeight", 100),
            ]

            self.systemd_manager.StartTransientUnit(
                scope_name, "fail", properties, [("PIDs", [dbus.UInt32(pid)])]
            )

            self.logger.info(f"Created transient scope {scope_name} for PID {pid}")
        except Exception as e:
            self.logger.exception(f"Failed to create transient scope: {e}")

    @staticmethod
    def _parse_size(size_str: str) -> int:
        """Parse size string like '2G' to bytes"""
        size_str = size_str.upper().strip()
        multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

        if size_str[-1] in multipliers:
            return int(size_str[:-1]) * multipliers[size_str[-1]]
        return int(size_str)

    def get_service_status(self, service_name: str) -> dict:
        """Get status of a systemd service

        Args:
            service_name: Name of the service

        Returns:
            Dictionary with service status information
        """
        try:
            result = subprocess.run(
                ["systemctl", "show", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )

            status = {}
            for line in result.stdout.split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    status[key] = value

            return status
        except Exception as e:
            self.logger.exception(f"Failed to get service status: {e}")
            return {}

    def enable_service(self, service_name: str):
        """Enable systemd service"""
        try:
            subprocess.run(["systemctl", "enable", service_name], check=True)
            self.logger.info(f"Enabled service: {service_name}")
        except subprocess.CalledProcessError as e:
            self.logger.exception(f"Failed to enable service {service_name}: {e}")

    def start_service(self, service_name: str):
        """Start systemd service"""
        try:
            subprocess.run(["systemctl", "start", service_name], check=True)
            self.logger.info(f"Started service: {service_name}")
        except subprocess.CalledProcessError as e:
            self.logger.exception(f"Failed to start service {service_name}: {e}")

    def stop_service(self, service_name: str):
        """Stop systemd service"""
        try:
            subprocess.run(["systemctl", "stop", service_name], check=True)
            self.logger.info(f"Stopped service: {service_name}")
        except subprocess.CalledProcessError as e:
            self.logger.exception(f"Failed to stop service {service_name}: {e}")

    def reload_daemon(self):
        """Reload systemd daemon configuration"""
        try:
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            self.logger.info("Reloaded systemd daemon")
        except subprocess.CalledProcessError as e:
            self.logger.exception(f"Failed to reload systemd daemon: {e}")
