# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/network/topology.py
"""
Network topology graph building and interface rename planning.

This module builds a graph representation of network device relationships
(bonds, bridges, VLANs, etc.) from configuration files and plans interface
renames when migrating from VMware to KVM.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from hyper2kvm.config.config_loader import YAML_AVAILABLE, yaml

from .model import (
    DeviceKind,
    FixLevel,
    IfcfgKV,
    NetworkConfig,
    NetworkConfigType,
    TopoEdge,
    TopologyGraph,
    ifcfg_kind_and_links,
)

if TYPE_CHECKING:
    import logging

# Interface name patterns that indicate VMware-specific naming
INTERFACE_NAME_PATTERNS = [
    (r"(?i)^ens(33|160|161|192|224|256|193|225)$", "vmware-ens-pattern"),
    (r"(?i)^vmnic\d+$", "vmware-vmnic"),
]


class NetworkTopology:
    """
    Network topology graph builder and interface rename planner.

    Analyzes network configuration files to build a graph of device relationships
    and plans interface renames for VMware -> KVM migration.
    """

    def __init__(self, logger: logging.Logger, fix_level: FixLevel):
        """
        Initialize topology builder.

        Args:
            logger: Logger instance
            fix_level: Fix level (CONSERVATIVE, MODERATE, AGGRESSIVE)
        """
        self.logger = logger
        self.fix_level = fix_level

    # Edge helpers (topology safety)

    def _edge_touches(self, e: TopoEdge, name: str) -> bool:
        """Check if edge involves a specific interface."""
        return name in (e.src, e.dst)

    def _is_lower_layer_member_edge(self, e: TopoEdge, name: str) -> bool:
        """
        Check if edge indicates interface is a lower-layer member.

        Lower-layer members (bond slaves, bridge ports, VLAN parents)
        should not have L3 config auto-added.
        """
        return e.kind in ("slave", "port", "vlan") and self._edge_touches(e, name)

    def _is_lower_layer_member(self, name: str, edges: list[TopoEdge]) -> bool:
        """Check if interface is member of bond/bridge/VLAN."""
        return any(self._is_lower_layer_member_edge(e, name) for e in edges)

    # Interface rename detection

    def needs_interface_rename(self, interface_name: str) -> bool:
        """
        Check if interface name needs renaming (VMware-specific).

        Args:
            interface_name: Interface name to check

        Returns:
            True if interface should be renamed
        """
        name = (interface_name or "").strip()

        # Check VMware-specific patterns
        for pattern, _tag in INTERFACE_NAME_PATTERNS:
            if re.match(pattern, name, re.IGNORECASE):
                return True

        # Standard Linux interface names should NOT be renamed
        standard_patterns = [
            r"^eth\d+$",
            r"^en[opsx]\w+$",
            r"^ens\d+$",
            r"^eno\d+$",
            r"^enp\d+s\d+$",
        ]
        for pattern in standard_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return False

        return False

    def get_safe_interface_name(self, current_name: str) -> str:
        """
        Generate safe replacement interface name.

        Args:
            current_name: Current interface name

        Returns:
            New eth-based name
        """
        match = re.search(r"\d+", current_name or "")
        if match:
            return f"eth{match.group()}"
        return "eth0"

    # Topology building - backend-specific parsers

    def _netplan_add_to_topology(  # pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks  # one parsing section per netplan device kind
        self,
        graph: TopologyGraph,
        cfg: NetworkConfig,
        data: dict[str, Any],
    ) -> None:
        """
        Parse netplan YAML and add devices to topology graph.

        Args:
            graph: Topology graph to populate
            cfg: Network configuration object
            data: Parsed YAML data
        """
        if not isinstance(data, dict):
            return
        nw = data.get("network")
        if not isinstance(nw, dict):
            return

        # Parse ethernets
        eths = nw.get("ethernets")
        if isinstance(eths, dict):
            for ifname, icfg in eths.items():
                graph.add_node(str(ifname), DeviceKind.ETHERNET, source=cfg.path)
                if isinstance(icfg, dict):
                    set_name = icfg.get("set-name")
                    if isinstance(set_name, str) and set_name.strip():
                        graph.add_node(set_name.strip(), DeviceKind.ETHERNET, source=cfg.path)

        # Parse bonds
        bonds = nw.get("bonds")
        if isinstance(bonds, dict):
            for bname, bcfg in bonds.items():
                graph.add_node(str(bname), DeviceKind.BOND, source=cfg.path)
                if isinstance(bcfg, dict):
                    ifaces = bcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for m in ifaces:
                            if isinstance(m, str):
                                graph.add_node(m, DeviceKind.ETHERNET, source=cfg.path)
                                graph.add_edge(m, str(bname), "slave")

        # Parse bridges
        bridges = nw.get("bridges")
        if isinstance(bridges, dict):
            for brname, brcfg in bridges.items():
                graph.add_node(str(brname), DeviceKind.BRIDGE, source=cfg.path)
                if isinstance(brcfg, dict):
                    ifaces = brcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for m in ifaces:
                            if isinstance(m, str):
                                graph.add_node(m, graph.infer_kind(m), source=cfg.path)
                                graph.add_edge(m, str(brname), "port")

        # Parse VLANs
        vlans = nw.get("vlans")
        if isinstance(vlans, dict):
            for vname, vcfg in vlans.items():
                graph.add_node(str(vname), DeviceKind.VLAN, source=cfg.path)
                if isinstance(vcfg, dict):
                    link = vcfg.get("link")
                    if isinstance(link, str) and link.strip():
                        graph.add_node(link.strip(), graph.infer_kind(link.strip()), source=cfg.path)
                        graph.add_edge(link.strip(), str(vname), "vlan")

    def _systemd_add_to_topology(  # pylint: disable=too-many-locals,too-many-branches  # line-oriented ini-style parser, one branch per keyword
        self, graph: TopologyGraph, cfg: NetworkConfig
    ) -> None:
        """
        Parse systemd-networkd .network file and add to topology.

        Args:
            graph: Topology graph to populate
            cfg: Network configuration object
        """
        text = cfg.content
        sec = None
        match_names: list[str] = []
        bond_ref: str | None = None
        bridge_ref: str | None = None
        vlan_refs: list[str] = []

        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith(("#", ";")):
                continue
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                continue

            if sec == "match":
                m = re.match(r"^\s*Name\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    parts = re.split(r"\s+", m.group(1).strip())
                    for p in parts:
                        if p and not any(ch in p for ch in "*?[]"):
                            match_names.append(p)

            if sec == "network":
                m = re.match(r"^\s*Bond\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    bond_ref = m.group(1).strip()
                m = re.match(r"^\s*Bridge\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    bridge_ref = m.group(1).strip()
                m = re.match(r"^\s*VLAN\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    for p in re.split(r"\s+", m.group(1).strip()):
                        if p:
                            vlan_refs.append(p)

        for n in match_names:
            graph.add_node(n, DeviceKind.ETHERNET, source=cfg.path)
            if bond_ref:
                graph.add_node(bond_ref, DeviceKind.BOND, source=cfg.path)
                graph.add_edge(n, bond_ref, "slave")
            if bridge_ref:
                graph.add_node(bridge_ref, DeviceKind.BRIDGE, source=cfg.path)
                graph.add_edge(n, bridge_ref, "port")
            for vr in vlan_refs:
                graph.add_node(vr, DeviceKind.VLAN, source=cfg.path)
                graph.add_edge(n, vr, "vlan")

    def _nm_add_to_topology(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # line-oriented ini-style parser, one branch per keyword
        self, graph: TopologyGraph, cfg: NetworkConfig
    ) -> None:
        """
        Parse NetworkManager connection file and add to topology.

        Args:
            graph: Topology graph to populate
            cfg: Network configuration object
        """
        text = cfg.content
        sec = None
        conn_type = None
        iface_name = None
        vlan_parent = None
        slave_type = None
        master = None

        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith(("#", ";")):
                continue
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                continue

            if sec == "connection":
                m = re.match(r"^\s*type\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    conn_type = m.group(1).strip().lower()
                m = re.match(r"^\s*interface-name\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    iface_name = m.group(1).strip()
                m = re.match(r"^\s*slave-type\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    slave_type = m.group(1).strip().lower()
                m = re.match(r"^\s*master\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    master = m.group(1).strip()

            if sec == "vlan":
                m = re.match(r"^\s*parent\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    vlan_parent = m.group(1).strip()

        kind = DeviceKind.UNKNOWN
        if conn_type in ("ethernet", "802-3-ethernet"):
            kind = DeviceKind.ETHERNET
        elif conn_type == "bond":
            kind = DeviceKind.BOND
        elif conn_type == "bridge":
            kind = DeviceKind.BRIDGE
        elif conn_type == "vlan":
            kind = DeviceKind.VLAN

        if iface_name:
            graph.add_node(
                iface_name,
                kind if kind != DeviceKind.UNKNOWN else graph.infer_kind(iface_name),
                source=cfg.path,
            )

        if kind == DeviceKind.VLAN and iface_name and vlan_parent:
            graph.add_node(vlan_parent, graph.infer_kind(vlan_parent), source=cfg.path)
            graph.add_edge(vlan_parent, iface_name, "vlan")

        # NM bond slave / bridge port — create slave/port edge so DHCP
        # injection is suppressed for member interfaces.
        if iface_name and master and slave_type:
            master_kind = (
                DeviceKind.BOND
                if slave_type == "bond"
                else (DeviceKind.BRIDGE if slave_type == "bridge" else DeviceKind.UNKNOWN)
            )
            edge_kind = "slave" if slave_type == "bond" else "port"
            graph.add_node(master, master_kind, source=cfg.path)
            graph.add_edge(iface_name, master, edge_kind)

    # Main topology builder

    def build_topology(self, configs: list[NetworkConfig]) -> TopologyGraph:
        """
        Build topology graph from network configuration files.

        Args:
            configs: List of network configuration objects

        Returns:
            TopologyGraph with nodes and edges
        """
        graph = TopologyGraph()
        backend_touch: dict[str, set[str]] = {}

        for cfg in configs:
            try:
                if cfg.type in (NetworkConfigType.IFCFG_RH, NetworkConfigType.WICKED_IFCFG):
                    ifcfg = IfcfgKV.parse(cfg.content)
                    dev = (ifcfg.get("DEVICE") or "").strip()
                    if dev:
                        kind, edges = ifcfg_kind_and_links(ifcfg)
                        graph.add_node(dev, kind, source=cfg.path)
                        for e in edges:
                            graph.add_node(e.src, graph.infer_kind(e.src), source=cfg.path)
                            graph.add_node(e.dst, graph.infer_kind(e.dst), source=cfg.path)
                            graph.add_edge(e.src, e.dst, e.kind)
                        backend_touch.setdefault(dev, set()).add(cfg.type.value)

                elif cfg.type == NetworkConfigType.NETPLAN and YAML_AVAILABLE:
                    try:
                        data = yaml.safe_load(cfg.content) or {}
                        if isinstance(data, dict):
                            self._netplan_add_to_topology(graph, cfg, data)
                    except Exception:  # pylint: disable=broad-exception-caught  # malformed YAML must not abort topology building
                        pass

                elif cfg.type == NetworkConfigType.SYSTEMD_NETWORK:
                    self._systemd_add_to_topology(graph, cfg)

                elif cfg.type == NetworkConfigType.NETWORK_MANAGER:
                    self._nm_add_to_topology(graph, cfg)

            except Exception as e:  # pylint: disable=broad-exception-caught  # one config's parse failure must not abort topology building
                graph.warnings.append(f"Topology parse error for {cfg.path}: {e}")

        # Warn about conflicting backends managing same interface
        for dev, backends in backend_touch.items():
            if len(backends) > 1:
                graph.warnings.append(
                    f"Multiple backends appear to manage '{dev}': {sorted(backends)}. "
                    "This can cause race/conflicts after boot."
                )

        return graph

    # Interface rename planning

    def compute_rename_map(self, topo: TopologyGraph) -> dict[str, str]:
        """
        Compute interface rename map (AGGRESSIVE mode only).

        Args:
            topo: Topology graph

        Returns:
            Dict mapping old interface names to new names
        """
        if self.fix_level != FixLevel.AGGRESSIVE:
            return {}

        rename: dict[str, str] = {}
        used: set[str] = set(topo.nodes.keys())

        for node in topo.nodes.values():
            if node.kind not in (DeviceKind.ETHERNET, DeviceKind.UNKNOWN):
                continue
            old = node.name
            if not self.needs_interface_rename(old):
                continue
            new = self.get_safe_interface_name(old)

            # Avoid conflicts
            if new in used and new != old:
                base = "eth"
                num = 0
                m = re.match(r"^eth(\d+)$", new)
                if m:
                    num = int(m.group(1))
                for k in range(num, num + 32):
                    cand = f"{base}{k}"
                    if cand not in used:
                        new = cand
                        break

            if old != new:
                rename[old] = new
                used.add(new)

        # Propagate renames through topology (bonds, bridges, etc.)
        return topo.rename_map_propagate(rename)


__all__ = ["INTERFACE_NAME_PATTERNS", "NetworkTopology"]
