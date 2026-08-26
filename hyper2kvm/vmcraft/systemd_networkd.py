# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-networkd configuration management for VMCraft.

This module provides APIs for creating, modifying, and migrating network
configurations using systemd-networkd. Supports migration from ifcfg and
NetworkManager configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging


class SystemdNetworkdManager:
    """
    Systemd-networkd configuration file management.

    Provides APIs for creating .network, .netdev, and .link files,
    as well as migration helpers for converting from legacy network
    configuration formats.
    """

    def __init__(self, logger: logging.Logger, guest_root: str):
        """
        Initialize SystemdNetworkdManager.

        Args:
            logger: Logger instance for output
            guest_root: Path to guest filesystem root
        """
        self.logger = logger
        self.guest_root = Path(guest_root)
        self.networkd_dir = self.guest_root / "etc/systemd/network"
        self.sysconfig_dir = self.guest_root / "etc/sysconfig/network-scripts"

    # ==================================================================================
    # Network File Management (6 methods)
    # ==================================================================================

    def create_network_file(
        self, name: str, match: dict[str, str], network: dict[str, Any], dhcp: str | None = None
    ) -> dict[str, Any]:
        """
        Create .network file in /etc/systemd/network/.

        Args:
            name: Network file name (e.g., "10-eth0")
            match: Match section (e.g., {"Name": "eth0", "MACAddress": "..."})
            network: Network section (e.g., {"Address": "192.168.1.10/24", "Gateway": "192.168.1.1"})
            dhcp: DHCP mode (yes, no, ipv4, ipv6)

        Returns:
            Audit dict with operation result

        Example:
            >>> # Create DHCP configuration
            >>> g.networkd_create_network_file(
            ...     name="10-eth0", match={"Name": "eth0"}, network={}, dhcp="yes"
            ... )
            >>>
            >>> # Create static IP configuration
            >>> g.networkd_create_network_file(
            ...     name="10-eth0",
            ...     match={"Name": "eth0"},
            ...     network={"Address": "192.168.1.100/24", "Gateway": "192.168.1.1", "DNS": "8.8.8.8"},
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "file": None, "path": None}

        try:
            # Ensure directory exists
            self.networkd_dir.mkdir(parents=True, exist_ok=True)

            # Construct file path
            if not name.endswith(".network"):
                name = f"{name}.network"

            file_path = self.networkd_dir / name
            audit["attempted"] = True
            audit["file"] = name
            audit["path"] = str(file_path)

            # Build INI-style content
            content = "[Match]\n"
            for key, value in match.items():
                content += f"{key}={value}\n"

            content += "\n[Network]\n"
            if dhcp:
                content += f"DHCP={dhcp}\n"

            for key, value in network.items():
                if key != "DHCP":  # Already handled
                    if isinstance(value, list):
                        # Multiple values (e.g., DNS servers)
                        for v in value:
                            content += f"{key}={v}\n"
                    else:
                        content += f"{key}={value}\n"

            # Write file
            file_path.write_text(content)
            file_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info(f"Created network file: {file_path}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to create network file: {e}")
            return audit

    def create_netdev_file(self, name: str, kind: str, netdev_config: dict[str, Any]) -> dict[str, Any]:
        """
        Create .netdev file for virtual devices (bridge, bond, vlan).

        Args:
            name: Device name (e.g., "br0", "bond0")
            kind: Device kind (bridge, bond, vlan, vxlan, etc.)
            netdev_config: Additional configuration for the netdev

        Returns:
            Audit dict with operation result

        Example:
            >>> # Create bridge device
            >>> g.networkd_create_netdev_file(name="br0", kind="bridge", netdev_config={"STP": "yes"})
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "file": name, "path": None}

        try:
            self.networkd_dir.mkdir(parents=True, exist_ok=True)

            # Construct file path
            filename = f"10-{name}.netdev" if not name.endswith(".netdev") else name

            file_path = self.networkd_dir / filename
            audit["attempted"] = True
            audit["path"] = str(file_path)

            # Build INI-style content
            content = "[NetDev]\n"
            content += f"Name={name.replace('.netdev', '')}\n"
            content += f"Kind={kind}\n"

            # Add kind-specific section
            if kind.lower() == "bridge":
                content += "\n[Bridge]\n"
            elif kind.lower() == "bond":
                content += "\n[Bond]\n"
            elif kind.lower() == "vlan":
                content += "\n[VLAN]\n"

            for key, value in netdev_config.items():
                content += f"{key}={value}\n"

            # Write file
            file_path.write_text(content)
            file_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info(f"Created netdev file: {file_path}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to create netdev file: {e}")
            return audit

    def create_link_file(self, name: str, match: dict[str, str], link: dict[str, str]) -> dict[str, Any]:
        """
        Create .link file for device naming.

        Args:
            name: Link file name
            match: Match section (e.g., {"MACAddress": "00:11:22:33:44:55"})
            link: Link section (e.g., {"Name": "eth0"})

        Returns:
            Audit dict with operation result

        Example:
            >>> # Set persistent interface name based on MAC
            >>> g.networkd_create_link_file(
            ...     name="10-persistent-net",
            ...     match={"MACAddress": "00:11:22:33:44:55"},
            ...     link={"Name": "eth0"},
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "file": name, "path": None}

        try:
            self.networkd_dir.mkdir(parents=True, exist_ok=True)

            if not name.endswith(".link"):
                name = f"{name}.link"

            file_path = self.networkd_dir / name
            audit["attempted"] = True
            audit["path"] = str(file_path)

            # Build content
            content = "[Match]\n"
            for key, value in match.items():
                content += f"{key}={value}\n"

            content += "\n[Link]\n"
            for key, value in link.items():
                content += f"{key}={value}\n"

            file_path.write_text(content)
            file_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info(f"Created link file: {file_path}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to create link file: {e}")
            return audit

    def remove_network_file(self, name: str) -> dict[str, Any]:
        """
        Remove .network file.

        Args:
            name: Network file name

        Returns:
            Audit dict with operation result
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "file": name}

        try:
            if not name.endswith(".network"):
                name = f"{name}.network"

            file_path = self.networkd_dir / name

            if not file_path.exists():
                audit["error"] = "file_not_found"
                return audit

            audit["attempted"] = True

            file_path.unlink()

            audit["ok"] = True
            self.logger.info(f"Removed network file: {file_path}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to remove network file: {e}")
            return audit

    def list_network_files(self) -> list[dict[str, Any]]:
        """
        List all systemd-networkd configuration files.

        Returns:
            List of dicts with file information

        Example:
            >>> files = g.networkd_list_network_files()
            >>> for f in files:
            ...     print(f"{f['name']}: {f['type']}")
        """
        files = []

        if not self.networkd_dir.exists():
            return files

        try:
            for file_path in self.networkd_dir.iterdir():
                if file_path.is_file():
                    file_type = None
                    if file_path.suffix == ".network":
                        file_type = "network"
                    elif file_path.suffix == ".netdev":
                        file_type = "netdev"
                    elif file_path.suffix == ".link":
                        file_type = "link"

                    if file_type:
                        files.append({"name": file_path.name, "type": file_type, "path": str(file_path)})

            return sorted(files, key=lambda x: x["name"])

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            self.logger.debug(f"Failed to list network files: {e}")
            return []

    def parse_network_file(self, name: str) -> dict[str, Any]:
        """
        Parse existing .network file.

        Args:
            name: Network file name

        Returns:
            Dict with parsed configuration sections

        Example:
            >>> config = g.networkd_parse_network_file("10-eth0.network")
            >>> print(config["Match"]["Name"])
            >>> print(config["Network"]["DHCP"])
        """
        result: dict[str, Any] = {"ok": False, "error": None, "sections": {}}

        # pylint: disable=duplicate-code
        # reason: this INI-style section/key=value parsing loop mirrors
        # similar loops in vmcraft/systemd_units.py (parse_unit_file) and
        # vmcraft/enhanced_inspection.py (resolved.conf parsing) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated config-parsing code paths.
        try:
            if not name.endswith(".network"):
                name = f"{name}.network"

            file_path = self.networkd_dir / name

            if not file_path.exists():
                result["error"] = "file_not_found"
                return result

            content = file_path.read_text()
            sections: dict[str, dict[str, Any]] = {}
            current_section = None

            for line in content.split("\n"):
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith(("#", ";")):
                    continue

                # Section header
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                    sections[current_section] = {}
                # Key-value pair
                elif "=" in line and current_section:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Handle multiple values for same key
                    if key in sections[current_section]:
                        # Convert to list if not already
                        if not isinstance(sections[current_section][key], list):
                            sections[current_section][key] = [sections[current_section][key]]
                        sections[current_section][key].append(value)
                    else:
                        sections[current_section][key] = value

            result["ok"] = True
            result["sections"] = sections
            return result

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            result["error"] = str(e)
            self.logger.debug(f"Failed to parse network file: {e}")
            return result

    # ==================================================================================
    # Migration Helpers (6 methods)
    # ==================================================================================

    def migrate_from_ifcfg(  # pylint: disable=too-many-locals,too-many-branches
        self, interface: str
    ) -> dict[str, Any]:
        # reason: translating the many independent ifcfg-* keys (BOOTPROTO, IPADDR,
        # NETMASK, GATEWAY, DNS*, BONDING_OPTS, ...) to systemd-networkd fields is
        # inherently a wide per-key mapping.
        """
        Migrate from /etc/sysconfig/network-scripts/ifcfg-* to systemd-networkd.

        Args:
            interface: Interface name (e.g., "eth0")

        Returns:
            Audit dict with migration result

        Example:
            >>> # Migrate RHEL/Fedora ifcfg to networkd
            >>> result = g.networkd_migrate_from_ifcfg("eth0")
            >>> if result["ok"]:
            ...     print(f"Created: {result['networkd_file']}")
        """
        # pylint: disable=duplicate-code
        # reason: this audit-dict-init + docstring shape mirrors similar
        # service-action methods in vmcraft/systemd_mgr.py (service_status)
        # -- structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated systemd/networkd migration
        # code paths.
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "interface": interface,
            "ifcfg_file": None,
            "networkd_file": None,
        }

        try:
            # Read ifcfg file
            ifcfg_path = self.sysconfig_dir / f"ifcfg-{interface}"

            if not ifcfg_path.exists():
                audit["error"] = "ifcfg_not_found"
                return audit

            audit["attempted"] = True
            audit["ifcfg_file"] = str(ifcfg_path)

            # Parse ifcfg file
            config = {}
            for line in ifcfg_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip().strip('"').strip("'")

            # Convert to networkd format
            match_section = {"Name": interface}
            network_section: dict[str, Any] = {}

            bootproto = config.get("BOOTPROTO", "none").lower()

            if bootproto == "dhcp":
                dhcp_mode = "yes"
            elif bootproto in ["none", "static"]:
                dhcp_mode = None
                if "IPADDR" in config:
                    prefix = config.get("PREFIX", config.get("NETMASK", "24"))
                    # Convert netmask to prefix if needed
                    if "." in str(prefix):
                        # It's a netmask, convert to CIDR
                        prefix = self._netmask_to_cidr(prefix)
                    network_section["Address"] = f"{config['IPADDR']}/{prefix}"

                if "GATEWAY" in config:
                    network_section["Gateway"] = config["GATEWAY"]

                dns_servers = []
                for i in range(1, 4):  # DNS1, DNS2, DNS3
                    dns_key = f"DNS{i}"
                    if dns_key in config:
                        dns_servers.append(config[dns_key])
                if dns_servers:
                    network_section["DNS"] = dns_servers
            else:
                dhcp_mode = None

            # Create networkd file
            result = self.create_network_file(
                name=f"10-{interface}", match=match_section, network=network_section, dhcp=dhcp_mode
            )

            audit["ok"] = result["ok"]
            audit["networkd_file"] = result.get("path")

            if result["ok"]:
                self.logger.info(f"Migrated {interface} from ifcfg to networkd")
            else:
                audit["error"] = result.get("error")

            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to migrate ifcfg: {e}")
            return audit

    def migrate_from_networkmanager(self) -> dict[str, Any]:
        """
        Migrate NetworkManager connections to systemd-networkd.

        Returns:
            Audit dict with migration results

        Example:
            >>> result = g.networkd_migrate_from_networkmanager()
            >>> print(f"Migrated {result['count']} connections")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "count": 0, "migrated": []}

        try:
            nm_connections_dir = self.guest_root / "etc/NetworkManager/system-connections"

            if not nm_connections_dir.exists():
                audit["error"] = "nm_connections_not_found"
                return audit

            audit["attempted"] = True

            # This is a simplified migration - real NetworkManager connections
            # use keyfile format which is more complex
            migrated_count = 0

            for conn_file in nm_connections_dir.glob("*.nmconnection"):
                try:
                    # Parse NetworkManager keyfile (simplified)
                    conn_name = conn_file.stem
                    self.logger.info(f"Found NetworkManager connection: {conn_name}")

                    # For now, create a simple DHCP configuration
                    # Real implementation would parse the full keyfile
                    result = self.create_network_file(
                        name=f"50-{conn_name}", match={"Name": conn_name}, network={}, dhcp="yes"
                    )

                    if result["ok"]:
                        migrated_count += 1
                        audit["migrated"].append(conn_name)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # reason: best-effort systemd-networkd config step; record/log the
                    # failure instead of aborting the wider network migration
                    self.logger.debug(f"Failed to migrate {conn_file}: {e}")
                    continue

            audit["ok"] = migrated_count > 0
            audit["count"] = migrated_count

            self.logger.info(f"Migrated {migrated_count} NetworkManager connections")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to migrate from NetworkManager: {e}")
            return audit

    def create_dhcp_network(self, interface: str) -> dict[str, Any]:
        """
        Create simple DHCP configuration for interface.

        Args:
            interface: Interface name

        Returns:
            Audit dict with operation result

        Example:
            >>> g.networkd_create_dhcp_network("eth0")
        """
        return self.create_network_file(
            name=f"10-{interface}", match={"Name": interface}, network={}, dhcp="yes"
        )

    def create_static_network(
        self, interface: str, address: str, gateway: str, dns: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Create static IP configuration.

        Args:
            interface: Interface name
            address: IP address with CIDR (e.g., "192.168.1.100/24")
            gateway: Gateway IP address
            dns: List of DNS server addresses

        Returns:
            Audit dict with operation result

        Example:
            >>> g.networkd_create_static_network(
            ...     interface="eth0",
            ...     address="192.168.1.100/24",
            ...     gateway="192.168.1.1",
            ...     dns=["8.8.8.8", "8.8.4.4"],
            ... )
        """
        network_config: dict[str, Any] = {"Address": address, "Gateway": gateway}

        if dns:
            network_config["DNS"] = dns

        return self.create_network_file(
            name=f"10-{interface}", match={"Name": interface}, network=network_config
        )

    def create_bridge_network(self, bridge_name: str, interfaces: list[str]) -> dict[str, Any]:
        """
        Create bridge configuration.

        Args:
            bridge_name: Bridge device name (e.g., "br0")
            interfaces: List of interfaces to add to bridge

        Returns:
            Audit dict with operation results

        Example:
            >>> # Create bridge for KVM networking
            >>> g.networkd_create_bridge_network("br0", ["eth0"])
        """
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "bridge": bridge_name,
            "interfaces": interfaces,
            "files_created": [],
        }

        try:
            audit["attempted"] = True

            # Create bridge netdev
            netdev_result = self.create_netdev_file(name=bridge_name, kind="bridge", netdev_config={})

            if not netdev_result["ok"]:
                audit["error"] = f"Failed to create netdev: {netdev_result.get('error')}"
                return audit

            audit["files_created"].append(netdev_result["path"])

            # Create bridge network file
            bridge_network = self.create_network_file(
                name=f"10-{bridge_name}", match={"Name": bridge_name}, network={}, dhcp="yes"
            )

            if not bridge_network["ok"]:
                audit["error"] = f"Failed to create bridge network: {bridge_network.get('error')}"
                return audit

            audit["files_created"].append(bridge_network["path"])

            # Create network files for slave interfaces
            for iface in interfaces:
                slave_result = self.create_network_file(
                    name=f"20-{iface}", match={"Name": iface}, network={"Bridge": bridge_name}
                )

                if slave_result["ok"]:
                    audit["files_created"].append(slave_result["path"])

            audit["ok"] = True
            self.logger.info(f"Created bridge {bridge_name} with interfaces: {interfaces}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to create bridge: {e}")
            return audit

    def enable_networkd(self) -> dict[str, Any]:
        """
        Enable and start systemd-networkd.

        Returns:
            Audit dict with operation result

        Example:
            >>> # After migrating configurations
            >>> g.networkd_enable_networkd()
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        try:
            audit["attempted"] = True

            # Create systemd service enable symlink
            systemd_system = self.guest_root / "etc/systemd/system/multi-user.target.wants"
            systemd_system.mkdir(parents=True, exist_ok=True)

            networkd_service = systemd_system / "systemd-networkd.service"
            networkd_target = Path("/usr/lib/systemd/system/systemd-networkd.service")

            # Create symlink if it doesn't exist
            if not networkd_service.exists():
                networkd_service.symlink_to(networkd_target)

            audit["ok"] = True
            self.logger.info("Enabled systemd-networkd")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            audit["error"] = str(e)
            self.logger.warning(f"Failed to enable networkd: {e}")
            return audit

    # ==================================================================================
    # Helper Methods
    # ==================================================================================

    def _netmask_to_cidr(self, netmask: str) -> int:
        """
        Convert netmask to CIDR prefix length.

        Args:
            netmask: Netmask in dotted decimal (e.g., "255.255.255.0")

        Returns:
            CIDR prefix length (e.g., 24)
        """
        try:
            octets = netmask.split(".")
            binary = "".join([bin(int(octet))[2:].zfill(8) for octet in octets])
            return binary.count("1")
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort systemd-networkd config step; record/log the
            # failure instead of aborting the wider network migration
            return 24  # Default to /24 if conversion fails
