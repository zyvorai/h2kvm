# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Linux-specific guest extraction logic.

Extracts network interfaces, packages, services, users, SSH keys,
disk usage, kernel modules, cron jobs, firewall rules, SELinux status,
and environment variables from Linux guest images.
"""

from __future__ import annotations

import configparser
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from hyper2kvm.core.guest_inspector import (
    DiskUsage,
    FirewallRule,
    InstalledPackage,
    NetworkInterface,
    ScheduledTask,
    SystemdService,
    UserAccount,
)

if TYPE_CHECKING:
    from hyper2kvm.core.guestfs_typing import guestfs

logger = logging.getLogger(__name__)


class LinuxGuestExtractor:
    """Extracts detailed information from Linux guest filesystems."""

    def __init__(self, log: logging.Logger | None = None):
        self.logger = log or logger

    # ── Network ─────────────────────────────────────────────────────

    def extract_network_interfaces(self, g: guestfs.GuestFS) -> list[NetworkInterface]:
        """Extract network interface information from Linux guest."""
        interfaces: list[NetworkInterface] = []

        try:
            if g.exists("/sys/class/net"):
                try:
                    for iface in g.ls("/sys/class/net"):
                        if iface in ("lo", "bonding_masters"):
                            continue
                        interface = NetworkInterface(name=iface)
                        self._read_sysfs_attrs(g, iface, interface)
                        interfaces.append(interface)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    self.logger.debug("Failed to parse /sys/class/net: %s", e)

            self._enrich_interfaces_from_config(g, interfaces)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.warning("Failed to extract network interfaces: %s", e)

        return interfaces

    def _read_sysfs_attrs(self, g: guestfs.GuestFS, iface: str, interface: NetworkInterface) -> None:
        """Read interface attributes from sysfs."""
        base = f"/sys/class/net/{iface}"

        mac_path = f"{base}/address"
        if g.exists(mac_path):
            try:
                mac = g.cat(mac_path).strip()
                if mac and mac != "00:00:00:00:00:00":
                    interface.mac_address = mac
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                pass

        type_path = f"{base}/type"
        if g.exists(type_path):
            try:
                iface_type = g.cat(type_path).strip()
                type_map = {"1": "ethernet", "772": "loopback", "801": "wireless"}
                interface.type = type_map.get(iface_type, f"type-{iface_type}")
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                pass

        mtu_path = f"{base}/mtu"
        if g.exists(mtu_path):
            try:
                interface.mtu = int(g.cat(mtu_path).strip())
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                pass

        driver_path = f"{base}/device/driver"
        if g.exists(driver_path):
            try:
                driver_link = g.readlink(driver_path)
                interface.driver = Path(driver_link).name
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                pass

    def _enrich_interfaces_from_config(self, g: guestfs.GuestFS, interfaces: list[NetworkInterface]) -> None:
        """Enrich interface information from all configuration systems."""
        self._enrich_from_systemd_networkd(g, interfaces)
        self._enrich_from_networkmanager(g, interfaces)
        self._enrich_from_netplan(g, interfaces)
        self._enrich_from_ifcfg_rh(g, interfaces)

    # ── systemd-networkd ────────────────────────────────────────────

    def _enrich_from_systemd_networkd(self, g: guestfs.GuestFS, interfaces: list[NetworkInterface]) -> None:
        if not g.exists("/etc/systemd/network"):
            return
        try:
            for network_file in g.glob_expand("/etc/systemd/network/*.network"):
                content = g.cat(network_file)
                interface = self._parse_systemd_network_file(content)
                if interface:
                    interfaces.append(interface)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to parse systemd-networkd config: %s", e)

    @staticmethod
    def _parse_systemd_network_file(content: str) -> NetworkInterface | None:
        current_section = None
        iface_pattern = None
        iface_mac = None
        dhcp_mode = None

        # pylint: disable=duplicate-code
        # reason: this INI-style section/key=value parsing loop mirrors a
        # similar loop in vmcraft/linux_services.py (unit-file parsing) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated config-parsing code paths.
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith((";", "#")):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()

            if current_section == "Match":
                if key == "Name":
                    iface_pattern = value
                elif key == "MACAddress":
                    iface_mac = value
            elif current_section == "Network" and key == "DHCP":
                dhcp_mode = value

        if not iface_pattern:
            return None

        iface_name = iface_pattern.replace("*", "0")
        return NetworkInterface(
            name=f"{iface_name} ({iface_pattern})",
            mac_address=iface_mac,
            type="dhcp" if dhcp_mode else "static",
        )

    # ── NetworkManager ──────────────────────────────────────────────

    def _enrich_from_networkmanager(self, g: guestfs.GuestFS, interfaces: list[NetworkInterface]) -> None:
        if not g.exists("/etc/NetworkManager/system-connections"):
            return
        try:
            for conn_file in g.glob_expand("/etc/NetworkManager/system-connections/*"):
                content = g.cat(conn_file)
                self._parse_networkmanager_connection(content, interfaces)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass

    @staticmethod
    def _parse_networkmanager_connection(content: str, interfaces: list[NetworkInterface]) -> None:
        """Parse a NetworkManager keyfile connection and match it to an interface by MAC."""
        try:
            parser = configparser.ConfigParser()
            parser.read_string(content)

            mac = None
            if parser.has_option("ethernet", "mac-address"):
                mac = parser.get("ethernet", "mac-address")
            elif parser.has_option("wifi", "mac-address"):
                mac = parser.get("wifi", "mac-address")

            iface_name = None
            if parser.has_option("connection", "interface-name"):
                iface_name = parser.get("connection", "interface-name")

            if mac:
                for iface in interfaces:
                    if iface.mac_address and iface.mac_address.lower() == mac.lower():
                        if iface_name:
                            iface.name = iface_name
                        break
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass

    # ── Netplan ─────────────────────────────────────────────────────

    def _enrich_from_netplan(self, g: guestfs.GuestFS, interfaces: list[NetworkInterface]) -> None:
        if not g.exists("/etc/netplan"):
            return
        try:
            for netplan_file in g.glob_expand("/etc/netplan/*.yaml"):
                content = g.cat(netplan_file)
                self._parse_netplan_file(content, interfaces)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass

    @staticmethod
    def _parse_netplan_file(content: str, interfaces: list[NetworkInterface]) -> None:
        """Parse a netplan YAML config and match ethernet/wifi entries to interfaces by MAC."""
        try:  # pylint: disable=too-many-nested-blocks  # walks ethernets/wifis sections matching interfaces by MAC
            import yaml  # pylint: disable=import-outside-toplevel  # keep PyYAML an optional/lazy dependency

            config = yaml.safe_load(content)
            if not config or "network" not in config:
                return
            network = config["network"]
            for section_key in ("ethernets", "wifis"):
                section = network.get(section_key, {})
                if not section:
                    continue
                for iface_name, iface_config in section.items():
                    mac = (iface_config.get("match") or {}).get("macaddress")
                    if not mac:
                        continue
                    for iface in interfaces:
                        if iface.mac_address and iface.mac_address.lower() == mac.lower():
                            iface.name = iface_name
                            addresses = iface_config.get("addresses", [])
                            if addresses:
                                iface.ip_addresses.append(addresses[0].split("/")[0])
                            break
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass

    # ── ifcfg-rh ────────────────────────────────────────────────────

    def _enrich_from_ifcfg_rh(self, g: guestfs.GuestFS, interfaces: list[NetworkInterface]) -> None:
        if not g.exists("/etc/sysconfig/network-scripts"):
            return
        try:  # pylint: disable=too-many-nested-blocks  # scans ifcfg files matching HWADDR to interfaces
            for ifcfg_file in g.glob_expand("/etc/sysconfig/network-scripts/ifcfg-*"):
                content = g.cat(ifcfg_file)
                for line in content.splitlines():
                    if line.startswith("HWADDR="):
                        mac = line.split("=", 1)[1].strip().strip('"')
                        for iface in interfaces:
                            if iface.mac_address == mac:
                                break
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass

    # ── Hostname / DNS ──────────────────────────────────────────────

    def extract_hostname(self, g: guestfs.GuestFS) -> str | None:
        """Extract the guest hostname from /etc/hostname or /etc/sysconfig/network."""
        try:
            if g.exists("/etc/hostname"):
                hostname = g.cat("/etc/hostname").strip()
                if hostname:
                    return hostname
            if g.exists("/etc/sysconfig/network"):
                content = g.cat("/etc/sysconfig/network")
                match = re.search(r"^HOSTNAME=(.+)$", content, re.MULTILINE)
                if match:
                    return match.group(1).strip().strip('"')
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract hostname: %s", e)
        return None

    def extract_dns_servers(self, g: guestfs.GuestFS) -> list[str]:
        """Extract nameserver entries from /etc/resolv.conf."""
        dns_servers: list[str] = []
        try:
            if g.exists("/etc/resolv.conf"):
                content = g.cat("/etc/resolv.conf")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("nameserver "):
                        dns_servers.append(line.split()[1])
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract DNS servers: %s", e)
        return dns_servers

    # ── Packages ────────────────────────────────────────────────────

    def detect_package_format(self, g: guestfs.GuestFS) -> str | None:
        """Detect the guest's package manager format from known package database paths."""
        if g.exists("/var/lib/rpm"):
            return "rpm"
        if g.exists("/var/lib/dpkg"):
            return "deb"
        if g.exists("/lib/apk/db"):
            return "apk"
        if g.exists("/var/lib/pacman"):
            return "pacman"
        return None

    def extract_packages(
        self, g: guestfs.GuestFS, package_format: str | None, max_packages: int = 100
    ) -> list[InstalledPackage]:
        """Extract installed packages, dispatching to the format-specific extractor."""
        try:
            if package_format == "rpm":
                return self._extract_rpm_packages(g, max_packages)
            if package_format == "deb":
                return self._extract_deb_packages(g, max_packages)
            if package_format == "apk":
                return self._extract_apk_packages(g, max_packages)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.warning("Failed to extract packages: %s", e)
        return []

    def _extract_rpm_packages(self, g: guestfs.GuestFS, max_packages: int) -> list[InstalledPackage]:
        packages: list[InstalledPackage] = []
        for log_file in ["/var/log/dnf.log", "/var/log/yum.log"]:
            if not g.exists(log_file) or len(packages) >= max_packages:
                continue
            try:
                content = g.cat(log_file)
                for line in content.splitlines()[-1000:]:
                    if "Installed:" not in line and "Installing:" not in line:
                        continue
                    match = re.search(r"([\w\-]+)-[\d\.]+-[\w\.]+\.", line)
                    if match and len(packages) < max_packages:
                        pkg_name = match.group(1)
                        if not any(p.name == pkg_name for p in packages):
                            packages.append(InstalledPackage(name=pkg_name, package_format="rpm"))
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                pass
        return packages

    def _extract_deb_packages(self, g: guestfs.GuestFS, max_packages: int) -> list[InstalledPackage]:
        packages: list[InstalledPackage] = []
        if not g.exists("/var/lib/dpkg/status"):
            return packages
        try:
            content = g.cat("/var/lib/dpkg/status")
            current_pkg = None
            for line in content.splitlines():
                if line.startswith("Package: "):
                    if current_pkg and len(packages) < max_packages:
                        packages.append(current_pkg)
                    current_pkg = InstalledPackage(name=line.split(": ", 1)[1].strip(), package_format="deb")
                elif current_pkg:
                    if line.startswith("Version: "):
                        current_pkg.version = line.split(": ", 1)[1].strip()
                    elif line.startswith("Architecture: "):
                        current_pkg.architecture = line.split(": ", 1)[1].strip()
                if len(packages) >= max_packages:
                    break
            if current_pkg and len(packages) < max_packages:
                packages.append(current_pkg)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass
        return packages

    def _extract_apk_packages(self, g: guestfs.GuestFS, max_packages: int) -> list[InstalledPackage]:
        packages: list[InstalledPackage] = []
        if not g.exists("/lib/apk/db/installed"):
            return packages
        try:
            content = g.cat("/lib/apk/db/installed")
            current_pkg = None
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("P:"):
                    if current_pkg and len(packages) < max_packages:
                        packages.append(current_pkg)
                    current_pkg = InstalledPackage(name=line[2:].strip(), package_format="apk")
                elif current_pkg:
                    if line.startswith("V:"):
                        current_pkg.version = line[2:].strip()
                    elif line.startswith("A:"):
                        current_pkg.architecture = line[2:].strip()
                if len(packages) >= max_packages:
                    break
            if current_pkg and len(packages) < max_packages:
                packages.append(current_pkg)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass
        return packages

    # ── Services ────────────────────────────────────────────────────

    def extract_systemd_services(self, g: guestfs.GuestFS) -> list[SystemdService]:
        """Extract systemd services enabled via *.target.wants symlinks."""
        services: list[SystemdService] = []
        try:  # pylint: disable=too-many-nested-blocks  # walks target.wants dirs collecting enabled services
            if not g.exists("/etc/systemd/system") and not g.exists("/usr/lib/systemd/system"):
                return services
            if g.exists("/etc/systemd/system"):
                for target_dir in g.glob_expand("/etc/systemd/system/*.target.wants"):
                    try:
                        for service_link in g.ls(target_dir):
                            if service_link.endswith(".service"):
                                services.append(SystemdService(name=service_link, enabled=True))
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                        pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract systemd services: %s", e)
        return services

    # ── Users ───────────────────────────────────────────────────────

    def extract_users(self, g: guestfs.GuestFS) -> list[UserAccount]:
        """Extract root and regular (uid >= 1000) user accounts from /etc/passwd."""
        users: list[UserAccount] = []
        try:
            if g.exists("/etc/passwd"):
                content = g.cat("/etc/passwd")
                for line in content.splitlines():
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(":")
                    if len(parts) >= 7:
                        user = UserAccount(
                            username=parts[0],
                            uid=int(parts[2]) if parts[2].isdigit() else None,
                            gid=int(parts[3]) if parts[3].isdigit() else None,
                            comment=parts[4],
                            home=parts[5],
                            shell=parts[6],
                        )
                        if user.uid == 0 or (user.uid and user.uid >= 1000):
                            users.append(user)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract users: %s", e)
        return users

    # ── SSH ──────────────────────────────────────────────────────────

    def extract_ssh_keys(self, g: guestfs.GuestFS) -> dict[str, list[str]]:
        """Extract authorized_keys entries per user (including root) from home directories."""
        ssh_keys: dict[str, list[str]] = {}
        try:
            for home_dir in g.glob_expand("/home/*"):
                username = Path(home_dir).name
                auth_path = f"{home_dir}/.ssh/authorized_keys"
                if g.exists(auth_path):
                    try:
                        keys = [
                            l.strip()
                            for l in g.cat(auth_path).splitlines()
                            if l.strip() and not l.startswith("#")
                        ]
                        if keys:
                            ssh_keys[username] = keys
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                        pass
            if g.exists("/root/.ssh/authorized_keys"):
                try:
                    keys = [
                        l.strip()
                        for l in g.cat("/root/.ssh/authorized_keys").splitlines()
                        if l.strip() and not l.startswith("#")
                    ]
                    if keys:
                        ssh_keys["root"] = keys
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract SSH keys: %s", e)
        return ssh_keys

    def extract_ssh_host_keys(self, g: guestfs.GuestFS) -> list[str]:
        """Extract SSH host public key fingerprints (truncated) from /etc/ssh."""
        host_keys: list[str] = []
        try:
            if g.exists("/etc/ssh"):
                for key_file in g.glob_expand("/etc/ssh/ssh_host_*_key.pub"):
                    try:
                        content = g.cat(key_file).strip()
                        if content:
                            host_keys.append(f"{Path(key_file).name}: {content[:80]}...")
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                        pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract SSH host keys: %s", e)
        return host_keys

    # ── Disk Usage ──────────────────────────────────────────────────

    def extract_disk_usage(self, g: guestfs.GuestFS) -> list[DiskUsage]:
        """Extract per-filesystem disk usage stats via statvfs, skipping unknown/swap filesystems."""
        usage_info: list[DiskUsage] = []
        try:
            for dev, fs_type in g.list_filesystems().items():
                if fs_type in ("unknown", "swap"):
                    continue
                try:
                    statvfs = g.statvfs(dev)
                    size_bytes = statvfs["blocks"] * statvfs["bsize"]
                    available_bytes = statvfs["bavail"] * statvfs["bsize"]
                    used_bytes = size_bytes - (statvfs["bfree"] * statvfs["bsize"])
                    use_percent = (used_bytes / size_bytes * 100) if size_bytes > 0 else 0
                    usage_info.append(
                        DiskUsage(
                            filesystem=dev,
                            mountpoint="/",
                            size_bytes=size_bytes,
                            used_bytes=used_bytes,
                            available_bytes=available_bytes,
                            use_percent=use_percent,
                        )
                    )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract disk usage: %s", e)
        return usage_info

    # ── Extended info ───────────────────────────────────────────────

    def extract_kernel_modules(self, g: guestfs.GuestFS) -> list[str]:
        """Extract loaded kernel module names from /proc/modules (capped at 50)."""
        modules: list[str] = []
        try:
            if g.exists("/proc/modules"):
                content = g.cat("/proc/modules")
                for line in content.splitlines():
                    if line:
                        modules.append(line.split()[0])
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract kernel modules: %s", e)
        return modules[:50]

    def extract_boot_parameters(self, g: guestfs.GuestFS) -> str | None:
        """Extract the kernel boot command line from /proc/cmdline."""
        try:
            if g.exists("/proc/cmdline"):
                return g.cat("/proc/cmdline").strip()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass
        return None

    def extract_timezone(self, g: guestfs.GuestFS) -> str | None:
        """Extract the guest timezone from /etc/timezone or the /etc/localtime symlink target."""
        try:
            if g.exists("/etc/timezone"):
                return g.cat("/etc/timezone").strip()
            if g.exists("/etc/localtime"):
                try:
                    link = g.readlink("/etc/localtime")
                    if "/zoneinfo/" in link:
                        return link.split("/zoneinfo/", 1)[1]
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass
        return None

    def extract_locale(self, g: guestfs.GuestFS) -> str | None:
        """Extract the guest LANG setting from locale.conf or the default/locale file."""
        try:
            for conf_path in ["/etc/locale.conf", "/etc/default/locale"]:
                if g.exists(conf_path):
                    content = g.cat(conf_path)
                    match = re.search(r"^LANG=(.+)$", content, re.MULTILINE)
                    if match:
                        return match.group(1).strip().strip('"')
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass
        return None

    def extract_cron_jobs(  # pylint: disable=too-many-nested-blocks,too-many-branches
        self, g: guestfs.GuestFS
    ) -> list[ScheduledTask]:
        """Extract scheduled tasks from /etc/crontab and per-user crontabs in /var/spool/cron."""
        tasks: list[ScheduledTask] = []
        # pylint: disable=duplicate-code
        # reason: this "cat + split cron line" parsing loop mirrors a
        # similar loop in vmcraft/scheduled_tasks.py (_parse_crontab) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated cron-parsing code paths.
        try:
            if g.exists("/etc/crontab"):
                try:
                    content = g.cat("/etc/crontab")
                    for line in content.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split(None, 6)
                        if len(parts) >= 7:
                            tasks.append(
                                ScheduledTask(
                                    name=f"cron: {parts[6][:50]}...",
                                    command=parts[6],
                                    schedule=f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]}",
                                    user=parts[5],
                                )
                            )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass

            # pylint: disable=duplicate-code
            # reason: this "cat + split cron line" parsing loop mirrors a
            # similar loop in vmcraft/services/systemd_offline.py
            # (sysusers.d parsing) -- structurally similar by coincidence,
            # not shared logic; keeping independent avoids coupling
            # unrelated per-user cron/sysusers parsing code paths.
            if g.exists("/var/spool/cron"):
                try:
                    for username in g.ls("/var/spool/cron"):
                        cron_path = f"/var/spool/cron/{username}"
                        if g.is_file(cron_path):
                            content = g.cat(cron_path)
                            for line in content.splitlines():
                                line = line.strip()
                                if not line or line.startswith("#"):
                                    continue
                                parts = line.split(None, 5)
                                if len(parts) >= 6:
                                    tasks.append(
                                        ScheduledTask(
                                            name=f"cron ({username}): {parts[5][:50]}...",
                                            command=parts[5],
                                            schedule=f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]}",
                                            user=username,
                                        )
                                    )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract cron jobs: %s", e)
        return tasks

    def extract_firewall_rules(  # pylint: disable=too-many-nested-blocks
        self, g: guestfs.GuestFS
    ) -> list[FirewallRule]:
        """Extract firewall rules from iptables rules.v4 and firewalld zone definitions."""
        rules: list[FirewallRule] = []
        try:
            if g.exists("/etc/iptables/rules.v4"):
                try:
                    content = g.cat("/etc/iptables/rules.v4")
                    for line in content.splitlines():
                        line = line.strip()
                        if line.startswith("-A"):
                            rules.append(
                                FirewallRule(
                                    name=line[:60],
                                    enabled=True,
                                    direction="inbound"
                                    if "INPUT" in line
                                    else "outbound"
                                    if "OUTPUT" in line
                                    else "forward",
                                    action="allow"
                                    if "ACCEPT" in line
                                    else "deny"
                                    if "DROP" in line or "REJECT" in line
                                    else None,
                                )
                            )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass

            if g.exists("/etc/firewalld/zones"):
                try:
                    for zone in g.ls("/etc/firewalld/zones"):
                        if zone.endswith(".xml"):
                            content = g.cat(f"/etc/firewalld/zones/{zone}")
                            services = re.findall(r'<service name="([^"]+)"', content)
                            for service in services:
                                rules.append(
                                    FirewallRule(
                                        name=f"{zone}: {service}",
                                        enabled=True,
                                        action="allow",
                                    )
                                )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract firewall rules: %s", e)
        return rules

    def extract_selinux_status(self, g: guestfs.GuestFS) -> str | None:
        """Extract the configured SELinux mode from /etc/selinux/config."""
        try:
            if g.exists("/etc/selinux/config"):
                content = g.cat("/etc/selinux/config")
                match = re.search(r"^SELINUX=(.+)$", content, re.MULTILINE)
                if match:
                    return match.group(1).strip().lower()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            pass
        return None

    def extract_environment(self, g: guestfs.GuestFS) -> dict[str, str]:
        """Extract environment variables from /etc/environment and export statements in /etc/profile.d."""
        env_vars: dict[str, str] = {}
        try:
            if g.exists("/etc/environment"):
                content = g.cat("/etc/environment")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"')

            if g.exists("/etc/profile.d"):
                try:
                    for pfile in g.glob_expand("/etc/profile.d/*.sh")[:5]:
                        content = g.cat(pfile)
                        for match in re.finditer(r"export\s+([A-Z_][A-Z0-9_]*)=(.+)", content):
                            env_vars[match.group(1)] = match.group(2).strip().strip('"').strip("'")
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest scan
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest scan
            self.logger.debug("Failed to extract environment variables: %s", e)
        return env_vars
