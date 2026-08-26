# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/network_config.py
"""
Network configuration analysis for both Windows and Linux.

Provides comprehensive network configuration detection:
- Network interfaces (IP, MAC, gateway, DNS)
- Routing tables
- Hostname and domain configuration
- Network manager settings
- Windows network configuration
- Linux network configuration (NetworkManager, systemd-networkd, ifcfg)

Features:
- Parse network interface configurations
- Detect static vs DHCP
- Extract DNS and gateway settings
- Identify network bonds and bridges
- VPN configuration detection
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class NetworkConfigAnalyzer:
    """
    Network configuration analyzer for VMs.

    Analyzes network configuration for both Windows and Linux systems.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize network config analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def analyze_network_config(self, os_type: str) -> dict[str, Any]:
        """
        Analyze network configuration based on OS type.

        Args:
            os_type: Operating system type ("windows" or "linux")

        Returns:
            Network configuration dictionary
        """
        if os_type == "windows":
            return self._analyze_windows_network()
        if os_type == "linux":
            return self._analyze_linux_network()
        return {"error": f"Unsupported OS type: {os_type}"}

    def _analyze_linux_network(self) -> dict[str, Any]:
        """
        Analyze Linux network configuration.

        Supports:
        - NetworkManager (/etc/NetworkManager/system-connections/)
        - systemd-networkd (/etc/systemd/network/)
        - ifcfg files (/etc/sysconfig/network-scripts/)
        - Netplan (/etc/netplan/)
        - interfaces file (/etc/network/interfaces)

        Returns:
            Network configuration dictionary
        """
        config: dict[str, Any] = {
            "interfaces": [],
            "hostname": None,
            "dns_servers": [],
            "default_gateway": None,
            "network_manager": None,
        }

        # Hostname
        config["hostname"] = self._get_linux_hostname()

        # DNS servers
        config["dns_servers"] = self._get_linux_dns()

        # Detect network manager
        if self.file_ops.is_dir("/etc/NetworkManager"):
            config["network_manager"] = "NetworkManager"
            config["interfaces"].extend(self._parse_networkmanager_config())
        elif self.file_ops.is_dir("/etc/systemd/network"):
            config["network_manager"] = "systemd-networkd"
            config["interfaces"].extend(self._parse_systemd_networkd_config())
        elif self.file_ops.is_dir("/etc/sysconfig/network-scripts"):
            config["network_manager"] = "ifcfg"
            config["interfaces"].extend(self._parse_ifcfg_config())
        elif self.file_ops.is_dir("/etc/netplan"):
            config["network_manager"] = "netplan"
            config["interfaces"].extend(self._parse_netplan_config())
        elif self.file_ops.exists("/etc/network/interfaces"):
            config["network_manager"] = "interfaces"
            config["interfaces"].extend(self._parse_interfaces_file())

        return config

    def _get_linux_hostname(self) -> str | None:
        """Get Linux hostname from /etc/hostname."""
        try:
            if self.file_ops.exists("/etc/hostname"):
                hostname = self.file_ops.cat("/etc/hostname").strip()
                return hostname if hostname else None
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config read -- caller treats None as "unavailable".
            self.logger.debug(f"Failed to read hostname: {e}")
        return None

    def _get_linux_dns(self) -> list[str]:
        """Get DNS servers from /etc/resolv.conf."""
        dns_servers = []
        try:
            if self.file_ops.exists("/etc/resolv.conf"):
                content = self.file_ops.cat("/etc/resolv.conf")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            dns_servers.append(parts[1])
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config read -- returns whatever was parsed so far.
            self.logger.debug(f"Failed to read resolv.conf: {e}")
        return dns_servers

    def _parse_networkmanager_config(self) -> list[dict[str, Any]]:
        """Parse NetworkManager connection files."""
        interfaces = []
        try:
            conn_dir = "/etc/NetworkManager/system-connections"
            if self.file_ops.is_dir(conn_dir):
                files = self.file_ops.ls(conn_dir)
                for file in files:
                    if file.endswith(".nmconnection"):
                        iface = self._parse_nmconnection_file(f"{conn_dir}/{file}")
                        if iface:
                            interfaces.append(iface)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config discovery -- returns whatever was parsed so far.
            self.logger.debug(f"Failed to parse NetworkManager config: {e}")
        return interfaces

    def _parse_nmconnection_file(self, filepath: str) -> dict[str, Any] | None:
        """Parse a NetworkManager connection file."""
        try:
            content = self.file_ops.cat(filepath)
            iface = {
                "name": Path(filepath).stem,
                "type": None,
                "method": None,
                "addresses": [],
                "gateway": None,
            }

            # Parse INI-style file
            for line in content.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "type":
                        iface["type"] = value
                    elif key == "method":
                        iface["method"] = value
                    elif key.startswith("address"):
                        iface["addresses"].append(value)
                    elif key == "gateway":
                        iface["gateway"] = value

            return iface if iface["name"] else None

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort per-file parse -- caller treats None as "skip it".
            return None

    def _parse_systemd_networkd_config(self) -> list[dict[str, Any]]:
        """Parse systemd-networkd configuration."""
        interfaces = []
        try:
            net_dir = "/etc/systemd/network"
            if self.file_ops.is_dir(net_dir):
                files = self.file_ops.ls(net_dir)
                for file in files:
                    if file.endswith(".network"):
                        iface = self._parse_systemd_network_file(f"{net_dir}/{file}")
                        if iface:
                            interfaces.append(iface)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config discovery -- returns whatever was parsed so far.
            self.logger.debug(f"Failed to parse systemd-networkd config: {e}")
        return interfaces

    def _parse_systemd_network_file(self, filepath: str) -> dict[str, Any] | None:
        """Parse a systemd .network file."""
        try:
            content = self.file_ops.cat(filepath)
            iface = {
                "name": Path(filepath).stem,
                "dhcp": False,
                "addresses": [],
                "gateway": None,
            }

            for line in content.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "DHCP":
                        iface["dhcp"] = value.lower() in ["yes", "true", "ipv4", "ipv6"]
                    elif key == "Address":
                        iface["addresses"].append(value)
                    elif key == "Gateway":
                        iface["gateway"] = value

            return iface

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort per-file parse -- caller treats None as "skip it".
            return None

    def _parse_ifcfg_config(self) -> list[dict[str, Any]]:
        """Parse ifcfg-* configuration files (Red Hat/CentOS/Fedora)."""
        interfaces = []
        try:
            ifcfg_dir = "/etc/sysconfig/network-scripts"
            if self.file_ops.is_dir(ifcfg_dir):
                files = self.file_ops.ls(ifcfg_dir)
                for file in files:
                    if file.startswith("ifcfg-") and not file.endswith(".bak"):
                        iface = self._parse_ifcfg_file(f"{ifcfg_dir}/{file}")
                        if iface:
                            interfaces.append(iface)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config discovery -- returns whatever was parsed so far.
            self.logger.debug(f"Failed to parse ifcfg config: {e}")
        return interfaces

    def _parse_ifcfg_file(self, filepath: str) -> dict[str, Any] | None:
        """Parse an ifcfg-* file."""
        try:
            content = self.file_ops.cat(filepath)
            iface = {
                "name": Path(filepath).name.replace("ifcfg-", ""),
                "bootproto": None,
                "ipaddr": None,
                "netmask": None,
                "gateway": None,
                "dns": [],
            }

            for line in content.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip().upper()
                    value = value.strip().strip('"')

                    if key == "BOOTPROTO":
                        iface["bootproto"] = value
                    elif key == "IPADDR":
                        iface["ipaddr"] = value
                    elif key == "NETMASK":
                        iface["netmask"] = value
                    elif key == "GATEWAY":
                        iface["gateway"] = value
                    elif key.startswith("DNS"):
                        iface["dns"].append(value)

            return iface

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort per-file parse -- caller treats None as "skip it".
            return None

    def _parse_netplan_config(self) -> list[dict[str, Any]]:
        """Parse Netplan configuration (Ubuntu)."""
        interfaces = []
        try:
            # Netplan uses YAML - basic parsing
            netplan_dir = "/etc/netplan"
            if self.file_ops.is_dir(netplan_dir):
                files = self.file_ops.ls(netplan_dir)
                for file in files:
                    if file.endswith((".yaml", ".yml")):
                        # Basic YAML parsing for network interfaces
                        content = self.file_ops.cat(f"{netplan_dir}/{file}")
                        # Simple extraction - full YAML parser would be better
                        iface = {
                            "name": "netplan",
                            "config_file": file,
                            "content_preview": content[:200] if len(content) > 200 else content,
                        }
                        interfaces.append(iface)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config discovery -- returns whatever was parsed so far.
            self.logger.debug(f"Failed to parse netplan config: {e}")
        return interfaces

    def _parse_interfaces_file(self) -> list[dict[str, Any]]:
        """Parse /etc/network/interfaces file (Debian)."""
        interfaces = []
        # pylint: disable=duplicate-code
        # reason: mirrors similar "cat + split key/value lines" config
        # parsing loops in vmcraft/database_detector.py (Redis config),
        # vmcraft/enhanced_inspection.py (_parse_debian_interfaces), and
        # vmcraft/ssh_analyzer.py (authorized_keys) -- structurally similar
        # by coincidence, not shared logic; keeping independent avoids
        # coupling unrelated config-parsing code paths.
        try:
            if self.file_ops.exists("/etc/network/interfaces"):
                content = self.file_ops.cat("/etc/network/interfaces")
                current_iface = None

                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split()
                    if len(parts) < 2:
                        continue

                    if parts[0] == "iface":
                        if current_iface:
                            interfaces.append(current_iface)
                        current_iface = {
                            "name": parts[1],
                            "family": parts[2] if len(parts) > 2 else None,
                            "method": parts[3] if len(parts) > 3 else None,
                            "options": {},
                        }
                    elif current_iface and len(parts) >= 2:
                        # reason: false positive -- `current_iface and` above already
                        # guarantees this is the dict assigned a few lines up, not None.
                        current_iface["options"][parts[0]] = " ".join(  # pylint: disable=unsubscriptable-object
                            parts[1:]
                        )

                if current_iface:
                    interfaces.append(current_iface)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort config discovery -- returns whatever was parsed so far.
            self.logger.debug(f"Failed to parse interfaces file: {e}")
        return interfaces

    def _analyze_windows_network(self) -> dict[str, Any]:
        """
        Analyze Windows network configuration.

        Reads network settings from registry:
        - HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters
        - Network adapters configuration

        Returns:
            Network configuration dictionary
        """
        config: dict[str, Any] = {
            "hostname": None,
            "dns_servers": [],
            "interfaces": [],
            "domain": None,
        }

        # Windows network config is in registry - would need registry parsing
        # For now, return basic structure
        config["note"] = "Windows network config requires registry parsing"

        return config

    def get_interface_count(self) -> int:
        """
        Get number of network interfaces.

        Returns:
            Number of interfaces detected
        """
        # This would need OS type detection first
        return 0

    def find_static_ips(self, config: dict[str, Any]) -> list[str]:
        """
        Find statically configured IP addresses.

        Args:
            config: Network configuration dictionary

        Returns:
            List of static IP addresses
        """
        static_ips = []

        for iface in config.get("interfaces", []):
            # Check for static configuration
            if iface.get("bootproto") == "static" or iface.get("method") == "static":
                if iface.get("ipaddr"):
                    static_ips.append(iface["ipaddr"])
            if iface.get("addresses"):
                static_ips.extend(iface["addresses"])

        return static_ips

    def detect_network_bonds(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Detect network bonding/teaming configurations.

        Args:
            config: Network configuration dictionary

        Returns:
            List of bonded interfaces
        """
        bonds = []

        for iface in config.get("interfaces", []):
            if "bond" in iface.get("name", "").lower() or iface.get("type") == "bond":
                bonds.append(iface)

        return bonds
