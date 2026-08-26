# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/network_topology.py
"""
Network topology and advanced network analysis.

Provides comprehensive network topology mapping:
- Network interface topology
- Routing table analysis
- DNS configuration analysis
- VPN configuration detection
- Network bonding/teaming topology
- VLAN configuration
- Network policy analysis

Features:
- Interface relationship mapping
- Route path visualization data
- DNS hierarchy analysis
- VPN tunnel detection
- Network redundancy analysis
- Network segmentation detection
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._proc_net_dev import parse_proc_net_dev_interface_names

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class NetworkTopology:
    """
    Network topology analyzer.

    Maps and analyzes network topology and advanced network configurations.
    """

    # Common network configuration files
    NETWORK_CONFIGS = {
        "linux": [
            "/etc/network/interfaces",
            "/etc/sysconfig/network-scripts/ifcfg-*",
            "/etc/netplan/*.yaml",
            "/etc/NetworkManager/system-connections/*",
        ],
        "windows": [
            "/Windows/System32/drivers/etc/hosts",
            "/Windows/System32/config/SYSTEM",
        ],
    }

    # VPN configuration patterns
    VPN_INDICATORS = [
        "/etc/openvpn",
        "/etc/ipsec.conf",
        "/etc/strongswan",
        "/etc/wireguard",
        "/etc/xl2tpd",
    ]

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize network topology analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def map_network_topology(self) -> dict[str, Any]:
        """
        Map complete network topology.

        Returns:
            Network topology mapping
        """
        topology: dict[str, Any] = {
            "interfaces": [],
            "routes": [],
            "dns_servers": [],
            "vpn_configs": [],
            "bonds": [],
            "vlans": [],
            "total_interfaces": 0,
        }

        # Detect interfaces
        interfaces = self._detect_interfaces()
        topology["interfaces"] = interfaces
        topology["total_interfaces"] = len(interfaces)

        # Parse routing table
        routes = self._parse_routing_table()
        topology["routes"] = routes

        # Analyze DNS configuration
        dns = self._analyze_dns()
        topology["dns_servers"] = dns

        # Detect VPN configurations
        vpn = self._detect_vpn()
        topology["vpn_configs"] = vpn

        # Detect network bonds/teams
        bonds = self._detect_bonds()
        topology["bonds"] = bonds

        # Detect VLANs
        vlans = self._detect_vlans()
        topology["vlans"] = vlans

        return topology

    # reads two independent interface sources (/proc/net/dev and config-file directories), each
    # with its own existence/type/dedup branches
    def _detect_interfaces(self) -> list[dict[str, Any]]:  # pylint: disable=too-many-branches
        """Detect network interfaces."""
        interfaces = []

        # Read /proc/net/dev for interface list
        if self.file_ops.exists("/proc/net/dev"):
            try:
                content = self.file_ops.cat("/proc/net/dev")
                for iface_name in parse_proc_net_dev_interface_names(content):
                    interfaces.append(
                        {
                            "name": iface_name,
                            "type": self._guess_interface_type(iface_name),
                        }
                    )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; probe next source on any failure
                pass

        # Read network config files
        config_paths = [
            "/etc/network/interfaces",
            "/etc/sysconfig/network-scripts",
        ]

        for config_path in config_paths:  # pylint: disable=too-many-nested-blocks
            if self.file_ops.exists(config_path):
                try:
                    if self.file_ops.is_dir(config_path):
                        files = self.file_ops.ls(config_path)
                        for filename in files:
                            if filename.startswith("ifcfg-"):
                                iface_name = filename.replace("ifcfg-", "")
                                if iface_name not in [i["name"] for i in interfaces]:
                                    interfaces.append(
                                        {
                                            "name": iface_name,
                                            "type": self._guess_interface_type(iface_name),
                                            "config_file": f"{config_path}/{filename}",
                                        }
                                    )
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; probe next source on any failure
                    pass

        return interfaces[:50]  # Limit to 50 interfaces

    # simple prefix-based classification; one branch per known interface-naming convention
    def _guess_interface_type(self, name: str) -> str:  # pylint: disable=too-many-return-statements
        """Guess interface type from name."""
        if name.startswith("eth"):
            return "ethernet"
        if name.startswith(("wlan", "wlp")):
            return "wireless"
        if name.startswith("br"):
            return "bridge"
        if name.startswith("bond"):
            return "bond"
        if name.startswith(("tun", "tap")):
            return "vpn"
        if "." in name:
            return "vlan"
        return "unknown"

    def _parse_routing_table(self) -> list[dict[str, Any]]:
        """Parse routing table."""
        routes = []

        # Read /proc/net/route
        if self.file_ops.exists("/proc/net/route"):
            try:
                content = self.file_ops.cat("/proc/net/route")
                lines = content.splitlines()

                # Skip header
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 8:
                        routes.append(
                            {
                                "interface": parts[0],
                                "destination": parts[1],
                                "gateway": parts[2],
                                "flags": parts[3],
                                "metric": parts[6] if len(parts) > 6 else "0",
                            }
                        )

                        if len(routes) >= 100:
                            break
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; return whatever was parsed so far
                pass

        return routes

    def _analyze_dns(self) -> list[str]:
        """Analyze DNS configuration."""
        dns_servers = []

        # Read /etc/resolv.conf
        if self.file_ops.exists("/etc/resolv.conf"):
            try:
                content = self.file_ops.cat("/etc/resolv.conf")
                for line in content.splitlines():
                    if line.strip().startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            dns_servers.append(parts[1])
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; return whatever was parsed so far
                pass

        return dns_servers

    def _detect_vpn(self) -> list[dict[str, Any]]:
        """Detect VPN configurations."""
        vpn_configs = []

        for vpn_path in self.VPN_INDICATORS:
            if self.file_ops.exists(vpn_path):
                vpn_type = Path(vpn_path).name

                if self.file_ops.is_dir(vpn_path):
                    # Count config files
                    try:
                        files = self.file_ops.ls(vpn_path)
                        config_count = len([f for f in files if f.endswith((".conf", ".ovpn"))])

                        vpn_configs.append(
                            {
                                "type": vpn_type,
                                "path": vpn_path,
                                "config_count": config_count,
                                "status": "configured",
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; skip this VPN indicator on failure
                        pass
                else:
                    vpn_configs.append(
                        {
                            "type": vpn_type,
                            "path": vpn_path,
                            "status": "configured",
                        }
                    )

        return vpn_configs

    # per-bond parsing (mode + slave list) nested inside the bond-directory listing loop
    def _detect_bonds(self) -> list[dict[str, Any]]:
        """Detect network bonding/teaming."""
        bonds = []

        # Check for bonding interfaces in /proc/net/bonding
        if self.file_ops.is_dir("/proc/net/bonding"):  # pylint: disable=too-many-nested-blocks
            try:
                bond_files = self.file_ops.ls("/proc/net/bonding")
                for bond_name in bond_files:
                    bond_path = f"/proc/net/bonding/{bond_name}"
                    try:
                        content = self.file_ops.cat(bond_path)

                        # Parse bonding info
                        mode = "unknown"
                        slaves = []

                        for line in content.splitlines():
                            if "Bonding Mode:" in line:
                                mode = line.split(":")[-1].strip()
                            elif "Slave Interface:" in line:
                                slave = line.split(":")[-1].strip()
                                slaves.append(slave)

                        bonds.append(
                            {
                                "name": bond_name,
                                "mode": mode,
                                "slaves": slaves,
                                "slave_count": len(slaves),
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; skip this bond on failure
                        pass
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; return whatever was parsed so far
                pass

        return bonds

    def _detect_vlans(self) -> list[dict[str, Any]]:
        """Detect VLAN configurations."""
        vlans = []

        # Check /proc/net/vlan for VLAN info
        if self.file_ops.is_dir("/proc/net/vlan"):
            try:
                vlan_files = self.file_ops.ls("/proc/net/vlan")
                for vlan_file in vlan_files:
                    if vlan_file == "config":
                        continue

                    vlans.append(
                        {
                            "interface": vlan_file,
                            "vlan_id": self._extract_vlan_id(vlan_file),
                        }
                    )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guest-file read; return whatever was parsed so far
                pass

        # Also check for interface names with dots (e.g., eth0.100)
        interfaces = self._detect_interfaces()
        for iface in interfaces:
            if "." in iface["name"]:
                parts = iface["name"].split(".")
                if len(parts) == 2 and parts[1].isdigit():
                    vlans.append(
                        {
                            "interface": iface["name"],
                            "parent": parts[0],
                            "vlan_id": parts[1],
                        }
                    )

        return vlans

    def _extract_vlan_id(self, interface_name: str) -> str:
        """Extract VLAN ID from interface name."""
        if "." in interface_name:
            parts = interface_name.split(".")
            if len(parts) >= 2:
                return parts[-1]

        # Try regex
        match = re.search(r"vlan(\d+)", interface_name)
        if match:
            return match.group(1)

        return "unknown"

    def get_topology_summary(self, topology: dict[str, Any]) -> dict[str, Any]:
        """
        Get network topology summary.

        Args:
            topology: Network topology data

        Returns:
            Summary dictionary
        """
        return {
            "total_interfaces": topology.get("total_interfaces", 0),
            "total_routes": len(topology.get("routes", [])),
            "dns_server_count": len(topology.get("dns_servers", [])),
            "vpn_count": len(topology.get("vpn_configs", [])),
            "bond_count": len(topology.get("bonds", [])),
            "vlan_count": len(topology.get("vlans", [])),
            "has_redundancy": len(topology.get("bonds", [])) > 0,
            "has_vpn": len(topology.get("vpn_configs", [])) > 0,
        }

    def analyze_network_redundancy(self, topology: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze network redundancy.

        Args:
            topology: Network topology data

        Returns:
            Redundancy analysis
        """
        analysis = {
            "has_bonding": False,
            "bond_count": 0,
            "redundant_routes": 0,
            "redundancy_score": 0,
        }

        bonds = topology.get("bonds", [])
        analysis["has_bonding"] = len(bonds) > 0
        analysis["bond_count"] = len(bonds)

        # Count redundant routes (simplified - check for multiple default gateways)
        routes = topology.get("routes", [])
        default_gateways = [r for r in routes if r.get("destination") == "00000000"]
        analysis["redundant_routes"] = len(default_gateways) - 1 if len(default_gateways) > 1 else 0

        # Calculate redundancy score (0-100)
        score = 0
        if analysis["has_bonding"]:
            score += 50
        if analysis["redundant_routes"] > 0:
            score += 30
        if len(topology.get("dns_servers", [])) > 1:
            score += 20

        analysis["redundancy_score"] = min(score, 100)

        return analysis

    def detect_network_segmentation(self, topology: dict[str, Any]) -> dict[str, Any]:
        """
        Detect network segmentation.

        Args:
            topology: Network topology data

        Returns:
            Segmentation analysis
        """
        segmentation = {
            "vlans_detected": False,
            "vlan_count": 0,
            "segments": [],
        }

        vlans = topology.get("vlans", [])
        segmentation["vlans_detected"] = len(vlans) > 0
        segmentation["vlan_count"] = len(vlans)

        # Create segments from VLANs
        for vlan in vlans:
            segmentation["segments"].append(
                {
                    "type": "vlan",
                    "id": vlan.get("vlan_id"),
                    "interface": vlan.get("interface"),
                }
            )

        return segmentation

    def generate_topology_graph(self, topology: dict[str, Any]) -> dict[str, Any]:
        """
        Generate topology graph data for visualization.

        Args:
            topology: Network topology data

        Returns:
            Graph data structure
        """
        graph = {
            "nodes": [],
            "edges": [],
        }

        # Add interface nodes
        for iface in topology.get("interfaces", []):
            graph["nodes"].append(
                {
                    "id": iface["name"],
                    "label": iface["name"],
                    "type": iface.get("type", "unknown"),
                }
            )

        # Add bond relationships
        for bond in topology.get("bonds", []):
            # Add bond node
            graph["nodes"].append(
                {
                    "id": bond["name"],
                    "label": bond["name"],
                    "type": "bond",
                }
            )

            # Add edges from slaves to bond
            for slave in bond.get("slaves", []):
                graph["edges"].append(
                    {
                        "from": slave,
                        "to": bond["name"],
                        "type": "member_of",
                    }
                )

        # Add VLAN relationships
        for vlan in topology.get("vlans", []):
            parent = vlan.get("parent")
            if parent:
                graph["edges"].append(
                    {
                        "from": parent,
                        "to": vlan["interface"],
                        "type": "vlan",
                        "vlan_id": vlan.get("vlan_id"),
                    }
                )

        return graph

    def get_network_policy_summary(self) -> dict[str, Any]:
        """
        Get network policy summary.

        Returns:
            Network policy summary
        """
        policy = {
            "firewall_active": False,
            "selinux_network_policy": False,
            "network_namespaces": 0,
        }

        # Check for firewall
        if self.file_ops.exists("/etc/firewalld") or self.file_ops.exists("/etc/iptables"):
            policy["firewall_active"] = True

        # Check for SELinux network policy
        if self.file_ops.exists("/etc/selinux/config"):
            policy["selinux_network_policy"] = True

        return policy
