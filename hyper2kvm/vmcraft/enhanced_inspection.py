# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Enhanced guest inspection operations.

Provides deep inspection capabilities for comprehensive VM analysis:
- Network configuration (multiple formats)
- DNS configuration
- User accounts
- SSH configuration
- SELinux/AppArmor status
- Runtime detection (Python, Node, Java, etc.)
- Container runtime detection
- Cron jobs and systemd timers
- SSL certificates
- VM guest tools
- Timezone and locale
- Kernel parameters
- Swap devices
- fstab structured parsing
"""
# pylint: disable=too-many-lines
# Cohesive single-class inspector covering many independent guest-config formats;
# splitting would fragment closely-related parsing logic more than it would help.
# pylint: disable=duplicate-code
# reason: this module has 9+ small config-parsing blocks (ifcfg/BOOTPROTO,
# sshd_config, sysctl.conf, fstab, resolved.conf, Debian interfaces,
# NetworkManager keyfile, ...) that are structurally similar to blocks in
# several sibling vmcraft/database_migration modules by coincidence, not
# shared logic; keeping each independently editable avoids coupling
# unrelated inspection code paths. See git history for the pylint pass
# that reviewed each instance.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import logging
    from pathlib import Path


@dataclass
class NetworkInterface:
    """Network interface configuration."""

    name: str
    ip_address: list[str]
    mac_address: str
    dhcp: bool
    dns_servers: list[str]


@dataclass
class UserAccount:
    """User account information."""

    username: str
    uid: str
    gid: str
    home: str
    shell: str


@dataclass
class FstabEntry:
    """fstab mount entry."""

    device: str
    mountpoint: str
    fstype: str
    options: str
    dump: int
    pass_num: int


class EnhancedInspector:
    """
    Enhanced guest inspection operations.

    Provides comprehensive analysis beyond basic OS detection.
    """

    # injects one guest-file-access callable per primitive (cat/exists/is_dir/ls) to stay guestfs-backend-agnostic
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        mount_root: Path,
        logger: logging.Logger,
        cat_func: Callable[[str], str],
        exists_func: Callable[[str], bool],
        is_dir_func: Callable[[str], bool],
        ls_func: Callable[[str], list[str]],
    ):
        """
        Initialize enhanced inspector.

        Args:
            mount_root: Root directory for mounted guest filesystem
            logger: Logger instance
            cat_func: Function to read guest files
            exists_func: Function to check file existence
            is_dir_func: Function to check if path is directory
            ls_func: Function to list directory contents
        """
        self.mount_root = mount_root
        self.logger = logger
        self.cat = cat_func
        self.exists = exists_func
        self.is_dir = is_dir_func
        self.ls = ls_func

    # Network Configuration Inspection

    # tries each of 5 network-config formats in turn, each with its own detect/parse/log branch
    def inspect_network(self) -> list[NetworkInterface]:  # pylint: disable=too-many-branches
        """
        Inspect network configuration from multiple formats.

        Supports:
        - /etc/network/interfaces (Debian/Ubuntu)
        - /etc/sysconfig/network-scripts/ifcfg-* (RHEL/CentOS/Fedora)
        - /etc/netplan/*.yaml (Ubuntu 17.10+)
        - /etc/NetworkManager/system-connections/*.nmconnection
        - /etc/systemd/network/*.network

        Returns:
            List of NetworkInterface objects
        """
        interfaces = []

        # Try Debian/Ubuntu interfaces file
        if self.exists("/etc/network/interfaces"):
            try:
                content = self.cat("/etc/network/interfaces")
                interfaces.extend(self._parse_debian_interfaces(content))
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse Debian interfaces: {e}")

        # Try RHEL/CentOS/Fedora network scripts
        if self.is_dir("/etc/sysconfig/network-scripts"):
            try:
                files = self.ls("/etc/sysconfig/network-scripts")
                for file in [f for f in files if f.startswith("ifcfg-")]:
                    path = f"/etc/sysconfig/network-scripts/{file}"
                    content = self.cat(path)
                    iface = self._parse_rhel_interface(content, file)
                    if iface:
                        interfaces.append(iface)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse RHEL interfaces: {e}")

        # Try netplan (newer Ubuntu)
        if self.is_dir("/etc/netplan"):
            try:
                files = self.ls("/etc/netplan")
                for file in [f for f in files if f.endswith((".yaml", ".yml"))]:
                    path = f"/etc/netplan/{file}"
                    content = self.cat(path)
                    interfaces.extend(self._parse_netplan(content))
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse netplan: {e}")

        # Try NetworkManager
        if self.is_dir("/etc/NetworkManager/system-connections"):
            try:
                files = self.ls("/etc/NetworkManager/system-connections")
                for file in [f for f in files if f.endswith(".nmconnection")]:
                    path = f"/etc/NetworkManager/system-connections/{file}"
                    content = self.cat(path)
                    iface = self._parse_networkmanager(content, file)
                    if iface:
                        interfaces.append(iface)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse NetworkManager: {e}")

        # Try systemd-networkd
        if self.is_dir("/etc/systemd/network"):
            try:
                files = self.ls("/etc/systemd/network")
                for file in [f for f in files if f.endswith(".network")]:
                    path = f"/etc/systemd/network/{file}"
                    content = self.cat(path)
                    iface = self._parse_systemd_network(content, file)
                    if iface:
                        interfaces.append(iface)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse systemd-networkd: {e}")

        return interfaces

    def _parse_debian_interfaces(self, content: str) -> list[NetworkInterface]:
        """Parse Debian /etc/network/interfaces format."""
        interfaces = []
        current_iface = None

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("iface "):
                if current_iface:
                    interfaces.append(current_iface)
                parts = line.split()
                if len(parts) >= 4:
                    dhcp = parts[3] == "dhcp"
                    current_iface = NetworkInterface(
                        name=parts[1],
                        ip_address=[],
                        mac_address="",
                        dhcp=dhcp,
                        dns_servers=[],
                    )

            elif current_iface:
                if line.startswith("address "):
                    addr = line.split(None, 1)[1]
                    current_iface.ip_address.append(addr)
                elif line.startswith(("hwaddress ", "hwaddr ")):
                    current_iface.mac_address = line.split(None, 1)[1]
                elif line.startswith("dns-nameservers "):
                    # Extract DNS servers from "dns-nameservers 8.8.8.8 8.8.4.4"
                    dns_list = line.split()[1:]
                    current_iface.dns_servers.extend(dns_list)

        if current_iface:
            interfaces.append(current_iface)

        return interfaces

    def _parse_rhel_interface(self, content: str, filename: str) -> NetworkInterface | None:
        """Parse RHEL /etc/sysconfig/network-scripts/ifcfg-* format."""
        iface = NetworkInterface(
            name=filename.replace("ifcfg-", ""),
            ip_address=[],
            mac_address="",
            dhcp=False,
            dns_servers=[],
        )

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"')

                if key == "BOOTPROTO":
                    iface.dhcp = value.lower() in ("dhcp", "bootp")
                elif key == "IPADDR" or key.startswith("IPADDR"):
                    iface.ip_address.append(value)
                elif key in ("HWADDR", "MACADDR"):
                    iface.mac_address = value
                elif key.startswith("DNS"):
                    # Extract DNS servers from DNS1, DNS2, DNS3, etc.
                    try:
                        int(key[3:])  # Verify it's DNSx format
                        iface.dns_servers.append(value)
                    except (ValueError, IndexError):
                        pass

        return iface

    # each netplan interface has several independent optional sub-blocks (addresses/match/nameservers)
    def _parse_netplan(self, content: str) -> list[NetworkInterface]:  # pylint: disable=too-many-locals
        """Parse netplan YAML configuration."""
        interfaces = []

        # Simple YAML parsing for netplan
        # Format: ethernets: -> interface_name: -> dhcp4/addresses/match
        try:
            # PyYAML is optional; if unavailable, the ImportError is caught below and logged,
            # falling back to an empty result rather than a hard module-import dependency
            import yaml  # pylint: disable=import-outside-toplevel

            data = yaml.safe_load(content)

            if not data or "network" not in data:
                return interfaces

            ethernets = data.get("network", {}).get("ethernets", {})
            for name, config in ethernets.items():
                iface = NetworkInterface(
                    name=name,
                    ip_address=[],
                    mac_address="",
                    dhcp=config.get("dhcp4", False) or config.get("dhcp", False),
                    dns_servers=[],
                )

                # Get IP addresses
                addresses = config.get("addresses", [])
                for addr in addresses:
                    iface.ip_address.append(str(addr))

                # Get MAC address
                match = config.get("match", {})
                mac = match.get("macaddress") or config.get("macaddress")
                if mac:
                    iface.mac_address = str(mac)

                # Get DNS servers from nameservers.addresses
                nameservers = config.get("nameservers", {})
                dns_addresses = nameservers.get("addresses", [])
                for dns in dns_addresses:
                    iface.dns_servers.append(str(dns))

                interfaces.append(iface)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
            self.logger.debug(f"YAML parse error in netplan: {e}")
            # Fallback to manual parsing if PyYAML not available

        return interfaces

    # INI-style parser: one section/key-value branch per NetworkManager connection setting
    def _parse_networkmanager(  # pylint: disable=too-many-branches,too-many-nested-blocks
        self, content: str, filename: str
    ) -> NetworkInterface | None:
        """Parse NetworkManager connection file."""
        iface = NetworkInterface(
            name=filename.replace(".nmconnection", ""),
            ip_address=[],
            mac_address="",
            dhcp=False,
            dns_servers=[],
        )

        current_section = ""
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if current_section == "connection":
                    if key == "interface-name":
                        iface.name = value
                elif current_section in ("ethernet", "wifi"):
                    if key == "mac-address":
                        iface.mac_address = value
                elif current_section == "ipv4":
                    if key == "method":
                        iface.dhcp = value == "auto"
                    elif key.startswith("address"):
                        # Format: address1=192.168.1.10/24,192.168.1.1
                        ip = value.split(",")[0].split("/")[0]
                        iface.ip_address.append(ip)
                    elif key == "dns":
                        # DNS servers separated by semicolons
                        for dns in value.split(";"):
                            dns = dns.strip()
                            if dns:
                                iface.dns_servers.append(dns)

        return iface

    def _parse_systemd_network(self, content: str, filename: str) -> NetworkInterface | None:
        """Parse systemd-networkd .network file."""
        iface = NetworkInterface(
            name=filename.replace(".network", ""),
            ip_address=[],
            mac_address="",
            dhcp=False,
            dns_servers=[],
        )

        current_section = ""
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if current_section == "Match":
                    if key == "Name":
                        iface.name = value
                    elif key == "MACAddress":
                        iface.mac_address = value
                elif current_section == "Network":
                    if key == "DHCP":
                        iface.dhcp = value in ("yes", "ipv4", "true")
                    elif key == "Address":
                        ip = value.split("/")[0]
                        iface.ip_address.append(ip)
                    elif key == "DNS":
                        # DNS servers can be space-separated
                        for dns in value.split():
                            iface.dns_servers.append(dns)

        return iface

    # DNS Configuration

    # tries each of 4 DNS-config sources in preference order, each with its own parse/fallback branch
    def inspect_dns(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks
        self,
    ) -> list[str]:
        """
        Get DNS server configuration from multiple sources.

        Parses in order of preference:
        1. /etc/resolv.conf
        2. /etc/systemd/resolved.conf + drop-ins (if resolv.conf points to loopback)
        3. Network interface configurations (if no resolv.conf or empty)
        4. NetworkManager global DNS

        Returns:
            List of DNS server IP addresses (sorted and deduplicated)
        """
        dns_servers = []
        has_resolv_conf = False
        is_loopback_only = True

        # Parse /etc/resolv.conf
        if self.exists("/etc/resolv.conf"):
            try:
                content = self.cat("/etc/resolv.conf")
                has_resolv_conf = True

                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("nameserver "):
                        server = line.split(None, 1)[1]
                        dns_servers.append(server)
                        if not server.startswith("127.") and server != "::1":
                            is_loopback_only = False

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/resolv.conf: {e}")

        # If resolv.conf points to loopback (systemd-resolved), parse resolved.conf + drop-ins
        if has_resolv_conf and is_loopback_only and self.exists("/etc/systemd/resolved.conf"):
            try:
                # Parse main resolved.conf
                content = self.cat("/etc/systemd/resolved.conf")
                parsed = self._parse_systemd_resolved_content(content)
                dns_servers.extend(parsed["dns"])
                dns_servers.extend(parsed["fallback_dns"])

                # Parse drop-ins in /etc/systemd/resolved.conf.d/
                if self.is_dir("/etc/systemd/resolved.conf.d"):
                    try:
                        files = self.ls("/etc/systemd/resolved.conf.d")
                        conf_files = sorted([f for f in files if f.endswith(".conf")])

                        for conf_file in conf_files:
                            path = f"/etc/systemd/resolved.conf.d/{conf_file}"
                            content = self.cat(path)
                            parsed = self._parse_systemd_resolved_content(content)
                            dns_servers.extend(parsed["dns"])
                            dns_servers.extend(parsed["fallback_dns"])
                    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                        self.logger.debug(f"Failed to parse resolved.conf.d: {e}")

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse systemd-resolved configuration: {e}")

        # If no resolv.conf or empty, collect from network interface configs
        elif not has_resolv_conf or not dns_servers:
            try:
                interfaces = self.inspect_network()
                for iface in interfaces:
                    dns_servers.extend(iface.dns_servers)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to collect DNS from network interfaces: {e}")

            # Parse NetworkManager global DNS
            if self.exists("/etc/NetworkManager/NetworkManager.conf"):
                try:
                    content = self.cat("/etc/NetworkManager/NetworkManager.conf")
                    in_dns_section = False

                    for line in content.splitlines():
                        line = line.strip()

                        if line == "[dns]":
                            in_dns_section = True
                        elif in_dns_section and line.startswith("["):
                            in_dns_section = False
                        elif in_dns_section and line.startswith("dns="):
                            value = line.split("=", 1)[1].strip()
                            for server in value.split(";"):
                                server = server.strip()
                                if server:
                                    dns_servers.append(server)

                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                    self.logger.debug(f"Failed to parse NetworkManager global DNS: {e}")

        # Sort and deduplicate
        return sorted(set(dns_servers))

    def _parse_systemd_resolved_content(self, content: str) -> dict[str, list[str]]:
        """
        Parse systemd resolved.conf content for DNS servers.

        Returns:
            Dict with 'dns' and 'fallback_dns' lists
        """
        parsed = {
            "dns": [],
            "fallback_dns": [],
        }
        current_section = ""

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                continue

            if current_section == "Resolve" and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key == "DNS":
                    for server in value.split():
                        # Extract IP, ignoring port/interface/SNI
                        ip = server.split(":")[0].split("%")[0].split("#")[0]
                        if ip:
                            parsed["dns"].append(ip)

                elif key == "FallbackDNS":
                    for server in value.split():
                        # Extract IP, ignoring port/interface/SNI
                        ip = server.split(":")[0].split("%")[0].split("#")[0]
                        if ip:
                            parsed["fallback_dns"].append(ip)

        return parsed

    # User Accounts

    def inspect_users(self) -> list[UserAccount]:
        """
        List user accounts from /etc/passwd.

        Returns:
            List of UserAccount objects
        """
        users = []

        if self.exists("/etc/passwd"):
            try:
                content = self.cat("/etc/passwd")
                for line in content.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 7:
                        users.append(
                            UserAccount(
                                username=parts[0],
                                uid=parts[2],
                                gid=parts[3],
                                home=parts[5],
                                shell=parts[6],
                            )
                        )
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/passwd: {e}")

        return users

    # SSH Configuration

    def inspect_ssh_config(self) -> dict[str, str]:
        """
        Parse SSH server configuration.

        Returns:
            Dict of SSH configuration key-value pairs
        """
        config = {}

        if self.exists("/etc/ssh/sshd_config"):
            try:
                content = self.cat("/etc/ssh/sshd_config")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(None, 1)
                    if len(parts) >= 2:
                        config[parts[0]] = parts[1]

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse SSH config: {e}")

        return config

    # Security Status

    def inspect_selinux(self) -> str:
        """
        Check SELinux status.

        Returns:
            SELinux mode: enforcing, permissive, disabled, or unknown
        """
        if self.exists("/etc/selinux/config"):
            try:
                content = self.cat("/etc/selinux/config")
                for line in content.splitlines():
                    if line.strip().startswith("SELINUX="):
                        return line.split("=", 1)[1].strip()
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse SELinux config: {e}")
                return "unknown"

        return "disabled"

    def inspect_apparmor(self) -> bool:
        """
        Check if AppArmor is enabled.

        Returns:
            True if AppArmor is present/enabled
        """
        return self.exists("/etc/apparmor") or self.exists("/sys/kernel/security/apparmor")

    # Runtime Detection

    def inspect_runtimes(self) -> dict[str, str]:
        """
        Detect installed language runtimes.

        Checks for: Python, Node.js, Ruby, Java, Go, Perl, PHP, Rust

        Returns:
            Dict mapping runtime name to "installed" or version info
        """
        runtimes = {}

        runtime_binaries = {
            "python3": "/usr/bin/python3",
            "python": "/usr/bin/python",
            "python2": "/usr/bin/python2",
            "node": "/usr/bin/node",
            "nodejs": "/usr/bin/nodejs",
            "ruby": "/usr/bin/ruby",
            "java": "/usr/bin/java",
            "go": "/usr/bin/go",
            "perl": "/usr/bin/perl",
            "php": "/usr/bin/php",
            "rustc": "/usr/bin/rustc",
        }

        for name, path in runtime_binaries.items():
            if self.exists(path):
                runtimes[name] = "installed"

        return runtimes

    # Container Runtime Detection

    def inspect_container_runtimes(self) -> list[str]:
        """
        Detect installed container runtimes.

        Checks for: Docker, Podman, containerd, CRI-O, LXC, LXD

        Returns:
            List of detected container runtime names
        """
        runtimes = []

        runtime_indicators = {
            "docker": "/usr/bin/docker",
            "podman": "/usr/bin/podman",
            "containerd": "/usr/bin/containerd",
            "cri-o": ("/usr/bin/crio", "/usr/bin/cri-o"),
            "lxc": "/usr/bin/lxc-start",
            "lxd": "/usr/bin/lxd",
        }

        for name, paths in runtime_indicators.items():
            if isinstance(paths, tuple):
                if any(self.exists(p) for p in paths):
                    runtimes.append(name)
            elif self.exists(paths):
                runtimes.append(name)

        return runtimes

    # Cron Jobs

    def inspect_cron(self) -> list[str]:
        """
        List cron jobs from system crontab and cron directories.

        Returns:
            List of cron job descriptions (file paths or crontab lines)
        """
        cron_jobs = []

        # System crontab
        if self.exists("/etc/crontab"):
            try:
                content = self.cat("/etc/crontab")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        cron_jobs.append(f"crontab: {line}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/crontab: {e}")

        # Cron directories
        cron_dirs = [
            "/etc/cron.d",
            "/etc/cron.daily",
            "/etc/cron.hourly",
            "/etc/cron.weekly",
            "/etc/cron.monthly",
        ]

        for cron_dir in cron_dirs:
            if self.is_dir(cron_dir):
                try:
                    files = self.ls(cron_dir)
                    for file in files:
                        cron_jobs.append(f"{cron_dir}/{file}")
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                    self.logger.debug(f"Failed to list {cron_dir}: {e}")

        return cron_jobs

    # systemd Timers

    def inspect_systemd_timers(self) -> list[str]:
        """
        List systemd timer units.

        Returns:
            List of enabled systemd timer unit names
        """
        timers = []

        if self.is_dir("/etc/systemd/system/timers.target.wants"):
            try:
                files = self.ls("/etc/systemd/system/timers.target.wants")
                timers = [f for f in files if f.endswith(".timer")]
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to list systemd timers: {e}")

        return timers

    # VM Guest Tools

    def inspect_vm_tools(self) -> list[str]:
        """
        Detect installed virtualization guest tools.

        Checks for:
        - VMware Tools
        - QEMU Guest Agent
        - VirtualBox Guest Additions
        - Hyper-V integration services
        - Xen tools

        Returns:
            List of detected guest tool names
        """
        tools = []

        tool_indicators = {
            "vmware-tools": (
                "/usr/bin/vmware-toolbox-cmd",
                "/etc/vmware-tools",
                "/usr/bin/vmtoolsd",
            ),
            "qemu-guest-agent": (
                "/usr/bin/qemu-ga",
                "/usr/bin/qemu-guest-agent",
            ),
            "virtualbox-guest-additions": (
                "/usr/sbin/VBoxService",
                "/opt/VBoxGuestAdditions",
            ),
            "hyper-v-tools": (
                "/usr/sbin/hv_kvp_daemon",
                "/usr/sbin/hv_vss_daemon",
            ),
            "xen-tools": (
                "/usr/sbin/xenstore",
                "/usr/bin/xenstore-ls",
            ),
        }

        for name, paths in tool_indicators.items():
            if any(self.exists(p) for p in paths):
                tools.append(name)

        return tools

    # Timezone and Locale

    def inspect_timezone(self) -> str:
        """
        Get system timezone.

        Returns:
            Timezone string (e.g., "America/New_York") or "unknown"
        """
        # Check /etc/timezone (Debian/Ubuntu)
        if self.exists("/etc/timezone"):
            try:
                return self.cat("/etc/timezone").strip()
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to read /etc/timezone: {e}")

        # Check /etc/localtime symlink
        localtime_path = self.mount_root / "etc/localtime"
        if localtime_path.is_symlink():
            try:
                target = localtime_path.readlink()
                # Extract timezone from /usr/share/zoneinfo/...
                target_str = str(target)
                if "zoneinfo/" in target_str:
                    return target_str.split("zoneinfo/", 1)[1]
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to read /etc/localtime symlink: {e}")

        return "unknown"

    def inspect_locale(self) -> str:
        """
        Get system locale.

        Returns:
            Locale string (e.g., "en_US.UTF-8") or "unknown"
        """
        # Check /etc/locale.conf (systemd-based)
        if self.exists("/etc/locale.conf"):
            try:
                content = self.cat("/etc/locale.conf")
                for line in content.splitlines():
                    if line.strip().startswith("LANG="):
                        return line.split("=", 1)[1].strip()
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/locale.conf: {e}")

        # Check /etc/default/locale (Debian/Ubuntu)
        if self.exists("/etc/default/locale"):
            try:
                content = self.cat("/etc/default/locale")
                for line in content.splitlines():
                    if line.strip().startswith("LANG="):
                        return line.split("=", 1)[1].strip().strip('"')
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/default/locale: {e}")

        return "unknown"

    # Kernel Parameters

    def inspect_kernel_params(self) -> dict[str, str]:
        """
        Get kernel sysctl parameters from /etc/sysctl.conf.

        Returns:
            Dict of kernel parameter key-value pairs
        """
        params = {}

        if self.exists("/etc/sysctl.conf"):
            try:
                content = self.cat("/etc/sysctl.conf")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if "=" in line:
                        key, value = line.split("=", 1)
                        params[key.strip()] = value.strip()

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/sysctl.conf: {e}")

        return params

    # Swap Devices

    def inspect_swap(self) -> list[str]:
        """
        Get swap devices from /etc/fstab.

        Returns:
            List of swap device paths
        """
        swap_devices = []

        if self.exists("/etc/fstab"):
            try:
                content = self.cat("/etc/fstab")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == "swap":
                        swap_devices.append(parts[0])

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse swap from fstab: {e}")

        return swap_devices

    # fstab Parsing

    def inspect_fstab(self) -> list[FstabEntry]:
        """
        Parse /etc/fstab into structured format.

        Returns:
            List of FstabEntry objects
        """
        entries = []

        if self.exists("/etc/fstab"):
            try:
                content = self.cat("/etc/fstab")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split()
                    if len(parts) >= 3:
                        entries.append(
                            FstabEntry(
                                device=parts[0],
                                mountpoint=parts[1],
                                fstype=parts[2],
                                options=parts[3] if len(parts) > 3 else "defaults",
                                dump=int(parts[4]) if len(parts) > 4 else 0,
                                pass_num=int(parts[5]) if len(parts) > 5 else 0,
                            )
                        )

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                self.logger.debug(f"Failed to parse /etc/fstab: {e}")

        return entries

    # Cloud-init Detection

    def inspect_cloud_init(self) -> bool:
        """
        Detect if cloud-init is installed.

        Returns:
            True if cloud-init is present
        """
        return (
            self.exists("/etc/cloud/cloud.cfg")
            or self.exists("/usr/bin/cloud-init")
            or self.exists("/var/lib/cloud")
        )

    # SSL Certificates

    def inspect_certificates(self) -> list[dict[str, str]]:
        """
        List SSL certificates in common locations.

        Returns:
            List of dicts with certificate paths
        """
        certs = []

        cert_dirs = [
            "/etc/ssl/certs",
            "/etc/pki/tls/certs",
            "/etc/pki/ca-trust",
            "/etc/ssl/private",
        ]

        for cert_dir in cert_dirs:
            if self.is_dir(cert_dir):
                try:
                    files = self.ls(cert_dir)
                    for file in files:
                        if file.endswith((".crt", ".pem", ".cert", ".cer")):
                            certs.append({"path": f"{cert_dir}/{file}", "type": "certificate"})
                        elif file.endswith(".key"):
                            certs.append({"path": f"{cert_dir}/{file}", "type": "private_key"})
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest-config parsing; try this format, log and continue
                    self.logger.debug(f"Failed to list {cert_dir}: {e}")

        return certs
