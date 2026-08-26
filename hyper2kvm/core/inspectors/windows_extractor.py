# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows-specific guest extraction logic.

Extracts network interfaces, hostname, applications, product info,
users, scheduled tasks, firewall rules, and environment variables
from Windows guest images using registry hive parsing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hyper2kvm.core.guest_inspector import (
    Application,
    FirewallRule,
    NetworkInterface,
    ScheduledTask,
    UserAccount,
)
from hyper2kvm.core.registry_reader import (
    HIVE_SOFTWARE,
    HIVE_SYSTEM,
    RegistryReader,
)

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods,duplicate-code
        # Typing-only stand-in named to match the real 'guestfs' module so
        # 'guestfs.GuestFS' annotations resolve when the module is absent. This exact stub
        # is intentionally repeated verbatim in other modules (e.g. grub.py, registry_reader.py)
        # that need the same TYPE_CHECKING-only fallback; it's boilerplate, not logic to share.
        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

logger = logging.getLogger(__name__)


class WindowsGuestExtractor:
    """Extracts detailed information from Windows guest filesystems."""

    def __init__(self, log: logging.Logger | None = None):
        self.logger = log or logger

    # ── Network ─────────────────────────────────────────────────────

    def extract_network_interfaces(self, g: guestfs.GuestFS) -> list[NetworkInterface]:
        """Extract configured network interfaces (IP, subnet, gateway) from the SYSTEM hive."""
        interfaces: list[NetworkInterface] = []

        with RegistryReader(g, HIVE_SYSTEM, self.logger) as reg:
            if not reg.is_open:
                return interfaces

            ifaces_key = reg.navigate(
                [
                    "ControlSet001",
                    "Services",
                    "Tcpip",
                    "Parameters",
                    "Interfaces",
                ]
            )
            if not ifaces_key:
                return interfaces

            for child in reg.get_children(ifaces_key):
                interface = self._parse_interface_node(reg, child)
                if interface and (interface.ip_addresses or interface.name):
                    interfaces.append(interface)

        return interfaces

    @staticmethod
    def _parse_interface_node(reg: RegistryReader, node: Any) -> NetworkInterface:
        # Tight internal coupling with RegistryReader in the same package; no public accessor exists.
        name = reg._hivex.node_name(node)  # pylint: disable=protected-access
        interface = NetworkInterface(name=name)

        for value in reg.get_values(node):
            val_name = reg.value_name(value)
            val_data = reg.value_data(value)
            if not val_data:
                continue

            decoded = reg.decode_string(val_data)
            if not decoded:
                continue

            if val_name == "IPAddress":
                interface.ip_addresses.append(decoded)
            elif val_name == "SubnetMask":
                interface.subnet_mask = decoded
            elif val_name == "DefaultGateway":
                interface.gateway = decoded

        return interface

    # ── Hostname ────────────────────────────────────────────────────

    def extract_hostname(self, g: guestfs.GuestFS) -> str | None:
        """Extract the computer hostname from the SYSTEM hive."""
        with RegistryReader(g, HIVE_SYSTEM, self.logger) as reg:
            if not reg.is_open:
                return None
            return reg.read_string_value(
                ["ControlSet001", "Control", "ComputerName", "ComputerName"],
                "ComputerName",
            )

    # ── Applications ────────────────────────────────────────────────

    def extract_applications(self, g: guestfs.GuestFS) -> list[Application]:
        """Extract installed applications from the SOFTWARE hive's Uninstall key."""
        applications: list[Application] = []

        with RegistryReader(g, HIVE_SOFTWARE, self.logger) as reg:
            if not reg.is_open:
                return self._extract_applications_fallback(g)

            uninstall_key = reg.navigate(
                [
                    "Microsoft",
                    "Windows",
                    "CurrentVersion",
                    "Uninstall",
                ]
            )
            if not uninstall_key:
                return self._extract_applications_fallback(g)

            for app_key in reg.get_children(uninstall_key):
                if len(applications) >= 100:
                    break
                app = self._parse_application_key(reg, app_key)
                if app:
                    applications.append(app)

        return applications

    @staticmethod
    def _parse_application_key(reg: RegistryReader, app_key: Any) -> Application | None:
        try:
            app_data: dict[str, str] = {}
            for value in reg.get_values(app_key):
                val_name = reg.value_name(value)
                val_raw = reg.value_data(value)
                if val_raw:
                    decoded = reg.decode_string(val_raw)
                    if decoded:
                        app_data[val_name] = decoded

            if "DisplayName" in app_data:
                return Application(
                    name=app_data.get("DisplayName", ""),
                    version=app_data.get("DisplayVersion", ""),
                    vendor=app_data.get("Publisher", ""),
                    install_location=app_data.get("InstallLocation", ""),
                )
        except Exception:  # pylint: disable=broad-exception-caught
            # Best-effort per-app registry parse; a malformed entry must not abort the list.
            pass
        return None

    def _extract_applications_fallback(self, g: guestfs.GuestFS) -> list[Application]:
        applications: list[Application] = []
        try:
            for path, win_path in [
                ("/Program Files", "C:\\Program Files"),
                ("/Program Files (x86)", "C:\\Program Files (x86)"),
            ]:
                if g.exists(path):
                    try:
                        for prog in g.ls(path)[:50]:
                            applications.append(
                                Application(
                                    name=prog,
                                    install_location=f"{win_path}\\{prog}",
                                )
                            )
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort per-directory listing, must not abort fallback extraction
                        pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fallback extraction, must not abort guest inspection
            self.logger.debug(f"Failed to extract Windows applications: {e}")
        return applications

    # ── Windows Version Info ────────────────────────────────────────

    _CURRENT_VERSION_PATH = ["Microsoft", "Windows NT", "CurrentVersion"]

    def extract_product_name(self, g: guestfs.GuestFS) -> str | None:
        """Extract the Windows product name (e.g. 'Windows Server 2019') from the SOFTWARE hive."""
        with RegistryReader(g, HIVE_SOFTWARE, self.logger) as reg:
            if not reg.is_open:
                return None
            return reg.read_string_value(self._CURRENT_VERSION_PATH, "ProductName")

    def extract_build_number(self, g: guestfs.GuestFS) -> str | None:
        """Extract the Windows build number from the SOFTWARE hive."""
        with RegistryReader(g, HIVE_SOFTWARE, self.logger) as reg:
            if not reg.is_open:
                return None
            return reg.read_string_value(self._CURRENT_VERSION_PATH, "CurrentBuildNumber")

    def extract_install_date(self, g: guestfs.GuestFS) -> str | None:
        """Extract the Windows installation date (ISO format) from the SOFTWARE hive."""
        with RegistryReader(g, HIVE_SOFTWARE, self.logger) as reg:
            if not reg.is_open:
                return None
            timestamp = reg.read_dword_value(self._CURRENT_VERSION_PATH, "InstallDate")
            if timestamp is not None:
                try:
                    return datetime.fromtimestamp(timestamp).isoformat()
                except (ValueError, OSError, OverflowError):
                    pass
            return None

    # ── Users ───────────────────────────────────────────────────────

    def extract_users(self, g: guestfs.GuestFS) -> list[UserAccount]:
        """Extract local user accounts by listing profile directories under /Users."""
        users: list[UserAccount] = []
        try:
            if g.exists("/Users"):
                for username in g.ls("/Users"):
                    if username not in ("Public", "Default", "Default User", "All Users"):
                        users.append(
                            UserAccount(
                                username=username,
                                home=f"C:\\Users\\{username}",
                            )
                        )
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort user enumeration, must not abort guest inspection
            self.logger.debug(f"Failed to extract Windows users: {e}")
        return users

    # ── Scheduled Tasks ─────────────────────────────────────────────

    def extract_scheduled_tasks(self, g: guestfs.GuestFS) -> list[ScheduledTask]:
        """Extract scheduled task names by listing files under Windows\\System32\\Tasks."""
        tasks: list[ScheduledTask] = []
        try:
            if g.exists("/Windows/System32/Tasks"):
                task_files = g.find("/Windows/System32/Tasks")
                for task_path in task_files[:20]:
                    if g.is_file(task_path):
                        task_name = task_path.replace("/Windows/System32/Tasks/", "")
                        tasks.append(ScheduledTask(name=task_name))
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort task enumeration, must not abort guest inspection
            self.logger.debug(f"Failed to extract Windows scheduled tasks: {e}")
        return tasks

    # ── Firewall ────────────────────────────────────────────────────

    def extract_firewall_rules(self, g: guestfs.GuestFS) -> list[FirewallRule]:
        """Extract firewall enabled/disabled state per profile from the SYSTEM hive."""
        rules: list[FirewallRule] = []

        with RegistryReader(g, HIVE_SYSTEM, self.logger) as reg:
            if not reg.is_open:
                return rules

            fw_key = reg.navigate(
                [
                    "ControlSet001",
                    "Services",
                    "SharedAccess",
                    "Parameters",
                    "FirewallPolicy",
                ]
            )
            if not fw_key:
                return rules

            for profile_name in ["StandardProfile", "DomainProfile", "PublicProfile"]:
                profile = reg.find_key(fw_key, profile_name)
                if not profile:
                    continue
                for value in reg.get_values(profile):
                    if reg.value_name(value) == "EnableFirewall":
                        val_data = reg.value_data(value)
                        if val_data:
                            enabled_val = reg.decode_dword(val_data)
                            if enabled_val is not None:
                                rules.append(
                                    FirewallRule(
                                        name=f"{profile_name} Firewall",
                                        enabled=(enabled_val == 1),
                                        direction="both",
                                    )
                                )

        return rules

    # ── Environment ─────────────────────────────────────────────────

    def extract_environment(self, g: guestfs.GuestFS) -> dict[str, str]:
        """Extract system-wide environment variables from the SYSTEM hive."""
        with RegistryReader(g, HIVE_SYSTEM, self.logger) as reg:
            if not reg.is_open:
                return {}
            return reg.read_all_string_values(
                [
                    "ControlSet001",
                    "Control",
                    "Session Manager",
                    "Environment",
                ]
            )
