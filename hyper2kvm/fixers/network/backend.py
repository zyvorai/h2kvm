# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/network/backend.py
# pylint: disable=too-many-lines  # cohesive backend-specific network fixer implementations for several distro formats
"""
Backend-specific network configuration fixers for VMware -> KVM migration.

This module contains NetworkFixersBackend class with all backend-specific
fix methods for different network configuration formats:
- ifcfg (RHEL/CentOS/SUSE)
- netplan (Ubuntu/modern systems)
- /etc/network/interfaces (Debian)
- systemd-networkd
- NetworkManager
- Wicked (SUSE)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from hyper2kvm.config.config_loader import YAML_AVAILABLE, yaml

from .model import (
    DeviceKind,
    FixLevel,
    FixResult,
    IfcfgKV,
    NetworkConfig,
    TopoEdge,
    TopologyGraph,
    ifcfg_kind_and_links,
)
from .topology import INTERFACE_NAME_PATTERNS

if TYPE_CHECKING:
    import logging


class NetworkFixersBackend:
    """
    Backend-specific network configuration fixers.

    This class contains all the per-backend fix methods for different
    network configuration formats found in Linux distributions.
    """

    def __init__(
        self,
        logger: logging.Logger,
        fix_level: FixLevel,
        vmware_drivers: dict[str, str],
        mac_pinning_patterns: list[tuple[str, str]],
    ):
        """
        Initialize the backend fixers.

        Args:
            logger: Logger instance for output
            fix_level: Fix aggressiveness level (CONSERVATIVE, MODERATE, AGGRESSIVE)
            vmware_drivers: Dictionary mapping VMware driver names to regex patterns
            mac_pinning_patterns: List of (regex, tag) tuples for MAC pinning detection
        """
        self.logger = logger
        self.fix_level = fix_level
        self.vmware_drivers = vmware_drivers
        self.mac_pinning_patterns = mac_pinning_patterns

    # Edge helpers (topology safety)

    def _edge_touches(self, e: TopoEdge, name: str) -> bool:
        """Check if an edge touches a given interface name."""
        return name in (e.src, e.dst)

    def _is_lower_layer_member_edge(self, e: TopoEdge, name: str) -> bool:
        """
        Check if edge indicates interface is a lower-layer member.

        Orientation-agnostic: if either side is the interface and kind indicates
        membership, treat it as "lower layer" (do not auto-add L3/DHCP).
        """
        return e.kind in ("slave", "port", "vlan") and self._edge_touches(e, name)

    def _is_lower_layer_member(self, name: str, edges: list[TopoEdge]) -> bool:
        """Check if interface is a lower-layer member (slave/port/vlan)."""
        return any(self._is_lower_layer_member_edge(e, name) for e in edges)

    # Compatibility helpers

    def _ifcfg_kind_and_links(self, ifcfg: IfcfgKV) -> Any:
        """
        Wrapper for ifcfg_kind_and_links() from network_model.

        Older code called self._ifcfg_kind_and_links(); real implementation is
        network_model.ifcfg_kind_and_links(). Keep wrapper for compatibility.
        """
        try:
            return ifcfg_kind_and_links(ifcfg)
        except Exception as e:  # pylint: disable=broad-exception-caught  # external parser; malformed ifcfg files must not abort the whole fixer run
            self.logger.debug("Topology: ifcfg_kind_and_links parse failed: %s", e)
            return (DeviceKind.UNKNOWN, [])

    # Intent helpers

    def _ifcfg_has_static_intent(self, ifcfg: IfcfgKV) -> bool:
        """
        Check if ifcfg file has static IP configuration or IPv6 auto-config intent.

        Returns True if any static IP keys are present, BOOTPROTO=static,
        or IPv6 auto-configuration is enabled (prevents unwanted IPv4 DHCP
        injection on IPv6-only interfaces).
        """
        static_keys = [
            "IPADDR",
            "IPADDR0",
            "PREFIX",
            "NETMASK",
            "GATEWAY",
            "DNS1",
            "DNS2",
            "IPV6ADDR",
            "IPV6_DEFAULTGW",
        ]
        if any(ifcfg.has(k) for k in static_keys):
            return True
        bp = (ifcfg.get("BOOTPROTO") or "").strip().lower()
        if bp in ("static",):
            return True
        # IPv6-only interfaces: IPV6INIT=yes with autoconf or DHCPv6
        ipv6init = (ifcfg.get("IPV6INIT") or "").strip().lower()
        return ipv6init == "yes"

    def _netplan_iface_has_static_intent(self, iface_cfg: dict[str, Any]) -> bool:
        """
        Check if netplan interface config has static IP configuration intent.

        Returns True if any static networking keys are present.
        """
        return any(
            k in iface_cfg
            for k in ("addresses", "gateway4", "gateway6", "routes", "routing-policy", "nameservers")
        )

    # Netplan helpers

    def _netplan_collect_member_refs(  # pylint: disable=too-many-nested-blocks,too-many-branches
        self, nw: dict[str, Any]
    ) -> set[str]:
        """
        Collect all interface names that are members of bonds/bridges/vlans.

        Returns a set of interface names that should not have L3 config.

        Scans three independent netplan sections (bonds/bridges/vlans), each with nested type checks.
        """
        members: set[str] = set()

        bonds = nw.get("bonds")
        if isinstance(bonds, dict):
            for bcfg in bonds.values():
                if isinstance(bcfg, dict):
                    ifaces = bcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for x in ifaces:
                            if isinstance(x, str):
                                members.add(x)

        bridges = nw.get("bridges")
        if isinstance(bridges, dict):
            for brcfg in bridges.values():
                if isinstance(brcfg, dict):
                    ifaces = brcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for x in ifaces:
                            if isinstance(x, str):
                                members.add(x)

        vlans = nw.get("vlans")
        if isinstance(vlans, dict):
            for vcfg in vlans.values():
                if isinstance(vcfg, dict):
                    link = vcfg.get("link")
                    if isinstance(link, str) and link.strip():
                        members.add(link.strip())

        return members

    def _netplan_collect_setname_aliases(self, nw: dict[str, Any]) -> dict[str, str]:
        """
        Collect set-name aliases from netplan ethernet configs.

        Returns a dict mapping match-name -> set-name for renamed interfaces.
        """
        aliases: dict[str, str] = {}
        eths = nw.get("ethernets")
        if isinstance(eths, dict):
            for ifname, icfg in eths.items():
                if isinstance(icfg, dict):
                    sn = icfg.get("set-name")
                    if isinstance(sn, str) and sn.strip():
                        aliases[str(ifname)] = sn.strip()
        return aliases

    # Interfaces helper

    def _interfaces_block_has_address(self, block_lines: list[str]) -> bool:
        """
        Check if an interfaces(5) block has an address directive.

        Used to determine if 'inet static' is legitimate or should be DHCP.
        """
        return any(re.match(r"^\s*address\s+\S+", ln) for ln in block_lines)

    # Backend-specific fixers

    def fix_ifcfg_rh(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # ifcfg fixer covers many independent key/format cases
        self,
        config: NetworkConfig,
        *,
        topo: TopologyGraph | None = None,
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix ifcfg files (RHEL-ish and SUSE-ish).

        Fixes applied:
        - Remove MAC pinning (MODERATE+)
        - Comment out VMware-ish driver tokens on DEVICE/TYPE lines (conservative too)
        - Remove VMware-ish params (comment out)
        - In AGGRESSIVE mode: rename DEVICE/NAME + propagate to PHYSDEV/MASTER/BRIDGE where applicable
        - DHCP normalization ONLY when safe:
            - no static intent
            - not a slave/port/vlan-member of bond/bridge/vlan
            - and BOOTPROTO is invalid/weird

        Args:
            config: NetworkConfig object to fix
            topo: Optional topology graph for context
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        fixes_applied: list[str] = []
        warnings: list[str] = []
        ifcfg = IfcfgKV.parse(config.content)

        dev = (ifcfg.get("DEVICE") or "").strip()
        if not dev:
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=["Missing DEVICE="],
            )

        kind, edges = self._ifcfg_kind_and_links(ifcfg)
        topo_kind = topo.infer_kind(dev) if topo else kind

        topo_edges: list[TopoEdge] = topo.edges if topo else []
        local_edges: list[TopoEdge] = list(edges) if edges else []

        # --- fix VMware-specific DEVICE names (MODERATE+)
        is_vmware_nic = False
        if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            for pattern, tag in INTERFACE_NAME_PATTERNS:
                if re.match(pattern, dev, re.IGNORECASE):
                    is_vmware_nic = True
                    # VMware NIC names (ens192, ens33, etc.) won't exist on KVM.
                    # Comment out DEVICE= so NetworkManager matches by TYPE=Ethernet.
                    ifcfg.comment_out("DEVICE", f"VMware NIC name ({tag}) removed by hyper2kvm")
                    # Ensure TYPE=Ethernet for generic NM matching
                    if not ifcfg.has("TYPE"):
                        ifcfg.set("TYPE", "Ethernet")
                        fixes_applied.append("added-type-ethernet")
                    # Set descriptive NAME for NM display
                    old_name = ifcfg.get("NAME") or ""
                    if not old_name.strip() or old_name.strip().strip("\"'") == dev:
                        ifcfg.set("NAME", f"Migrated ({dev})")
                    fixes_applied.append(f"removed-vmware-nic-device-{dev}")
                    break

        # --- remove MAC pinning keys
        if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            for k in ("HWADDR", "MACADDR", "MACADDRESS", "CLONED_MAC"):
                if ifcfg.has(k):
                    ifcfg.delete(k, "MAC pinning removed by hyper2kvm")
                    fixes_applied.append(f"removed-mac-pinning-{k.lower()}")

        # --- ensure network activates on first boot (MODERATE+)
        if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            onboot = (ifcfg.get("ONBOOT") or "").strip().lower()
            # Force ONBOOT=yes when explicitly "no", or when missing on
            # VMware-named interfaces (DEVICE was removed, must auto-start).
            if onboot == "no" or (not onboot and is_vmware_nic):
                ifcfg.set("ONBOOT", "yes")
                fixes_applied.append("enabled-onboot")

            nm_ctrl = (ifcfg.get("NM_CONTROLLED") or "").strip().lower()
            if nm_ctrl == "no":
                ifcfg.set("NM_CONTROLLED", "yes")
                fixes_applied.append("enabled-nm-controlled")

            # Remove stale UUID — after migration the connection is effectively
            # new and a stale UUID can cause NM conflicts or silent failures.
            if ifcfg.has("UUID"):
                ifcfg.delete("UUID", "stale UUID removed by hyper2kvm")
                fixes_applied.append("removed-uuid")

        # --- VMware driver token cleanup
        new_lines: list[str] = []
        for ln in ifcfg.lines:
            changed = False
            for driver_name, pattern in self.vmware_drivers.items():
                if re.search(pattern, ln, re.IGNORECASE):
                    if re.match(r"^\s*(DEVICE|TYPE|ETHTOOL_OPTS|OPTIONS|DRIVER)\s*=", ln, re.IGNORECASE):
                        if not ln.lstrip().startswith("#"):
                            new_lines.append(f"# {ln}  # VMware token removed by hyper2kvm")
                            fixes_applied.append(f"removed-vmware-driver-token-{driver_name}")
                            changed = True
                    break
            if changed:
                continue
            new_lines.append(ln)
        ifcfg.lines = new_lines

        # --- VMware-ish params
        vmware_params = ["VMWARE_", "VMXNET_", "SCSIDEVICE", "SUBCHANNELS"]
        new_lines2: list[str] = []
        for ln in ifcfg.lines:
            u = ln.upper()
            if any(p in u for p in vmware_params) and not ln.lstrip().startswith("#"):
                new_lines2.append(f"# {ln}  # VMware-specific parameter removed by hyper2kvm")
                for p in vmware_params:
                    if p in u:
                        fixes_applied.append(f"removed-vmware-param-{p.lower()}")
                continue
            new_lines2.append(ln)
        ifcfg.lines = new_lines2

        # --- Aggressive renaming (DEVICE/NAME + references)
        rm = rename_map or {}
        renamed = False
        if self.fix_level == FixLevel.AGGRESSIVE and rm:
            # Skip DEVICE rename if we already commented it out (VMware NIC fix)
            if dev in rm and not is_vmware_nic:
                new_dev = rm[dev]
                ifcfg.set("DEVICE", new_dev)
                fixes_applied.append("renamed-device")
                dev = new_dev
                renamed = True

            namev = (ifcfg.get("NAME") or "").strip().strip("\"'")
            if namev and namev in rm:
                ifcfg.set("NAME", rm[namev])
                fixes_applied.append("renamed-name")
                renamed = True

            phys = (ifcfg.get("PHYSDEV") or "").strip()
            if phys and phys in rm:
                ifcfg.set("PHYSDEV", rm[phys])
                fixes_applied.append("renamed-physdev")
                renamed = True

            master = (ifcfg.get("MASTER") or "").strip()
            if master and master in rm:
                ifcfg.set("MASTER", rm[master])
                fixes_applied.append("renamed-master-ref")
                renamed = True

            br = (ifcfg.get("BRIDGE") or "").strip()
            if br and br in rm:
                ifcfg.set("BRIDGE", rm[br])
                fixes_applied.append("renamed-bridge-ref")
                renamed = True

        # IMPORTANT: if we renamed identifiers, recompute edges/kind from the updated content
        if renamed:
            kind, edges = self._ifcfg_kind_and_links(ifcfg)
            topo_kind = topo.infer_kind(dev) if topo else kind
            local_edges = list(edges) if edges else []

        all_edges: list[TopoEdge] = topo_edges + local_edges

        # --- DHCP normalization (careful!)
        is_lower_member = self._is_lower_layer_member(dev, all_edges)
        has_static = self._ifcfg_has_static_intent(ifcfg)
        bootproto = (ifcfg.get("BOOTPROTO") or "").strip().strip("\"'").lower()

        if bootproto and bootproto not in ("dhcp", "static", "none", "bootp"):
            # Invalid/unrecognized BOOTPROTO — normalize to DHCP if safe
            if not has_static and not is_lower_member:
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("normalized-bootproto->dhcp")
        elif not bootproto and not has_static and not is_lower_member:
            # Missing BOOTPROTO with no static config — the interface will
            # have no address.  Set DHCP so it gets an IP after migration.
            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("added-bootproto-dhcp")
        elif (
            bootproto == "none"
            and not has_static
            and not is_lower_member
            and topo_kind == DeviceKind.ETHERNET
        ):
            # BOOTPROTO=none with no static config on a plain ethernet —
            # at MODERATE+ change to DHCP so the interface gets an address.
            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("normalized-bootproto-none->dhcp")

        # --- warn on risky layout: IP on a bridge port
        if (
            kind == DeviceKind.ETHERNET
            and (ifcfg.has("BRIDGE") or any(e.kind == "port" for e in local_edges))
            and self._ifcfg_has_static_intent(ifcfg)
        ):
            warnings.append(
                f"{config.path}: IP/static config appears on a bridge port ({dev}). "
                "Often the IP should live on the bridge device, not the port. Not auto-moving."
            )

        new_content = ifcfg.render()
        return FixResult(
            config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings
        )

    def fix_netplan(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # netplan fixer covers many independent section/key cases
        self,
        config: NetworkConfig,
        *,
        topo: TopologyGraph | None = None,
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix netplan YAML configuration files.

        Fixes applied:
        - Remove MAC pinning (match.macaddress, macaddress, cloned-mac-address)
        - Remove VMware driver hints
        - Rename interface references (AGGRESSIVE mode)
        - Enable DHCP on interfaces without static config (AGGRESSIVE mode only, not for NetworkManager renderer)
        - Propagate renames through bonds/bridges/vlans

        Args:
            config: NetworkConfig object to fix
            topo: Optional topology graph for context
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        if not YAML_AVAILABLE:
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=["YAML support not available"],
            )

        fixes_applied: list[str] = []
        warnings: list[str] = []
        rm = rename_map or {}

        try:
            data = yaml.safe_load(config.content) or {}
            if not isinstance(data, dict):
                return FixResult(
                    config=config,
                    new_content=config.content,
                    applied_fixes=[],
                    validation_errors=["Netplan YAML is not a dict"],
                )

            nw = data.get("network")
            if not isinstance(nw, dict):
                return FixResult(
                    config=config,
                    new_content=config.content,
                    applied_fixes=[],
                    validation_errors=["Missing 'network:' section"],
                )

            renderer = str(nw.get("renderer") or "").lower()

            # AGGRESSIVE: enable DHCP on all interfaces without static config.
            # MODERATE: only enable DHCP on interfaces where we removed MAC/NIC
            # identity (otherwise we might inject DHCP on intentionally unconfigured
            # interfaces).  Never auto-DHCP when renderer=NetworkManager.
            allow_auto_dhcp_always = self.fix_level == FixLevel.AGGRESSIVE and renderer != "networkmanager"
            is_moderate = self.fix_level == FixLevel.MODERATE and renderer != "networkmanager"

            netplan_members = self._netplan_collect_member_refs(nw)
            setname_alias = self._netplan_collect_setname_aliases(nw)
            topo_edges: list[TopoEdge] = topo.edges if topo else []

            def is_member(name: str) -> bool:
                if name in netplan_members:
                    return True
                alias = setname_alias.get(name)
                if alias and alias in netplan_members:
                    return True
                for k, v in setname_alias.items():
                    if v == name and k in netplan_members:
                        return True
                return self._is_lower_layer_member(name, topo_edges)

            def scrub_mac(d: dict[str, Any], *, prefix: str) -> None:
                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    match_cfg = d.get("match")
                    if isinstance(match_cfg, dict) and "macaddress" in match_cfg:
                        del match_cfg["macaddress"]
                        fixes_applied.append(f"{prefix}-removed-match-mac")
                        if not match_cfg:
                            del d["match"]
                            fixes_applied.append(f"{prefix}-removed-empty-match")

                    for k in ("macaddress", "cloned-mac-address"):
                        if k in d:
                            del d[k]
                            fixes_applied.append(f"{prefix}-removed-{k}")

            def rename_list(lst: Any) -> Any:
                if not isinstance(lst, list):
                    return lst
                out: list[Any] = []
                changed = False
                for x in lst:
                    if isinstance(x, str) and x in rm:
                        out.append(rm[x])
                        changed = True
                    else:
                        out.append(x)
                if changed:
                    fixes_applied.append("netplan-renamed-interfaces-ref")
                return out

            def rename_ref(x: Any, tag: str) -> Any:
                if isinstance(x, str) and x in rm:
                    fixes_applied.append(tag)
                    return rm[x]
                return x

            eths = nw.get("ethernets")
            if isinstance(eths, dict):
                # --- Replace hardcoded VMware NIC names with wildcard match ---
                # VMware uses predictable names like ens33, ens160, ens192, etc.
                # On KVM these become ens3, enp1s0, etc. — a hardcoded name won't match.
                # Use INTERFACE_NAME_PATTERNS (shared with ifcfg/NM/networkd fixers)
                # for consistent VMware NIC detection across all backends.
                def _is_vmware_netplan_name(name: str) -> bool:
                    return any(re.match(pat, name, re.IGNORECASE) for pat, _tag in INTERFACE_NAME_PATTERNS)

                # Collect VMware NICs first, then pick the best one to keep.
                # Prefer NIC with static config over DHCP (static IP = identity).
                vmware_nics: list[tuple[str, dict[str, Any]]] = []
                rekeyed: dict[str, dict[str, Any]] = {}
                for ifname, icfg in list(eths.items()):
                    if not isinstance(icfg, dict):
                        rekeyed[ifname] = icfg
                        continue
                    match_block = icfg.get("match")
                    has_match = isinstance(match_block, dict) and match_block
                    if _is_vmware_netplan_name(str(ifname)) and not has_match:
                        vmware_nics.append((str(ifname), icfg))
                    else:
                        rekeyed[ifname] = icfg

                if vmware_nics:
                    # Pick the best NIC: prefer static config, then first in order
                    best_idx = 0
                    for i, (_, icfg) in enumerate(vmware_nics):
                        if self._netplan_iface_has_static_intent(icfg):
                            best_idx = i
                            break
                    best_name, best_cfg = vmware_nics[best_idx]
                    best_cfg["match"] = {"name": "en*"}
                    rekeyed["all-en"] = best_cfg
                    fixes_applied.append(f"eth-{best_name}-replaced-vmware-nic-name-with-match")
                    # Log dropped NICs; warn if any had static config
                    for i, (name, icfg) in enumerate(vmware_nics):
                        if i != best_idx:
                            fixes_applied.append(f"eth-{name}-merged-into-all-en")
                            if self._netplan_iface_has_static_intent(icfg):
                                warnings.append(
                                    f"{config.path}: Dropped static config from {name} "
                                    f"(merged into all-en from {best_name}). "
                                    "Review network config after boot — static addresses may be lost."
                                )

                nw["ethernets"] = rekeyed
                eths = rekeyed

                for ifname, icfg in list(eths.items()):
                    if not isinstance(icfg, dict):
                        continue
                    scrub_mac(icfg, prefix=f"eth-{ifname}")

                    if "driver" in icfg:
                        drv = str(icfg.get("driver") or "")
                        for vmware_driver in self.vmware_drivers:
                            if vmware_driver in drv.lower():
                                del icfg["driver"]
                                fixes_applied.append(f"eth-{ifname}-removed-vmware-driver-{vmware_driver}")
                                break

                    has_static = self._netplan_iface_has_static_intent(icfg)

                    set_name = icfg.get("set-name")
                    names_to_check = [str(ifname)]
                    if isinstance(set_name, str) and set_name.strip():
                        names_to_check.append(set_name.strip())

                    member = any(is_member(n) for n in names_to_check)

                    # Enable DHCP if interface has no static config and no dhcp4 set.
                    # At MODERATE, only do this if we modified the interface identity
                    # (MAC scrubbed or VMware NIC renamed).
                    iface_was_modified = any(f"eth-{ifname}-" in f for f in fixes_applied)
                    should_dhcp = allow_auto_dhcp_always or (is_moderate and iface_was_modified)
                    if should_dhcp and (not has_static) and ("dhcp4" not in icfg) and (not member):
                        icfg["dhcp4"] = True
                        fixes_applied.append(f"eth-{ifname}-enabled-dhcp4")

            bonds = nw.get("bonds")
            if isinstance(bonds, dict):
                for bname, bcfg in bonds.items():
                    if not isinstance(bcfg, dict):
                        continue
                    scrub_mac(bcfg, prefix=f"bond-{bname}")
                    if "interfaces" in bcfg:
                        bcfg["interfaces"] = rename_list(bcfg.get("interfaces"))

                    has_static = self._netplan_iface_has_static_intent(bcfg)
                    is_port = False
                    if topo is not None:
                        is_port = any(e.kind == "port" and (bname in (e.src, e.dst)) for e in topo.edges)

                    if (
                        allow_auto_dhcp_always
                        and (not has_static)
                        and ("dhcp4" not in bcfg)
                        and (not is_port)
                    ):
                        bcfg["dhcp4"] = True
                        fixes_applied.append(f"bond-{bname}-enabled-dhcp4")

            bridges = nw.get("bridges")
            if isinstance(bridges, dict):
                for brname, brcfg in bridges.items():
                    if not isinstance(brcfg, dict):
                        continue
                    scrub_mac(brcfg, prefix=f"bridge-{brname}")
                    if "interfaces" in brcfg:
                        brcfg["interfaces"] = rename_list(brcfg.get("interfaces"))

                    has_static = self._netplan_iface_has_static_intent(brcfg)
                    if allow_auto_dhcp_always and (not has_static) and ("dhcp4" not in brcfg):
                        brcfg["dhcp4"] = True
                        fixes_applied.append(f"bridge-{brname}-enabled-dhcp4")

            vlans = nw.get("vlans")
            if isinstance(vlans, dict):
                for vname, vcfg in vlans.items():
                    if not isinstance(vcfg, dict):
                        continue
                    scrub_mac(vcfg, prefix=f"vlan-{vname}")
                    if "link" in vcfg:
                        vcfg["link"] = rename_ref(vcfg.get("link"), "netplan-renamed-vlan-link")

                    has_static = self._netplan_iface_has_static_intent(vcfg)
                    if allow_auto_dhcp_always and (not has_static) and ("dhcp4" not in vcfg):
                        vcfg["dhcp4"] = True
                        fixes_applied.append(f"vlan-{vname}-enabled-dhcp4")

            new_content = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

            if renderer == "networkmanager" and any("enabled-dhcp4" in f for f in fixes_applied):
                warnings.append(
                    f"{config.path}: renderer=NetworkManager detected; DHCP changes may be overridden by NM profiles."
                )

            return FixResult(
                config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings
            )

        except Exception as e:  # pylint: disable=broad-exception-caught  # covers YAML parsing + extensive transforms; must report as FixResult, not crash
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=[f"YAML parse error: {e}"],
            )

    def fix_interfaces(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # Debian interfaces fixer covers many independent line/format cases
        self, config: NetworkConfig
    ) -> FixResult:
        """
        Fix /etc/network/interfaces (Debian-style) configuration.

        Fixes applied:
        - Remove VMware driver tokens
        - Remove hwaddress ether MAC pinning (MODERATE+)
        - Change 'inet static' to 'inet dhcp' when no address directive present (MODERATE+)

        Args:
            config: NetworkConfig object to fix

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []
        warnings: list[str] = []

        lines = content.split("\n")
        new_lines: list[str] = []

        current_iface: str | None = None
        iface_block_lines: list[str] = []
        in_iface_block = False

        def flush_block() -> None:
            nonlocal iface_block_lines, current_iface, in_iface_block
            if not in_iface_block or not current_iface:
                iface_block_lines = []
                current_iface = None
                in_iface_block = False
                return

            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                has_address = self._interfaces_block_has_address(iface_block_lines)
                for idx, ln in enumerate(iface_block_lines):
                    if re.match(r"^\s*iface\s+\S+\s+inet\s+static\b", ln) and not has_address:
                        iface_block_lines[idx] = re.sub(r"\bstatic\b", "dhcp", ln)
                        fixes_applied.append(f"iface-{current_iface}-static-without-address->dhcp")
                        break

            new_lines.extend(iface_block_lines)
            iface_block_lines = []
            current_iface = None
            in_iface_block = False

        for line in lines:
            if line.strip().startswith("iface "):
                flush_block()
                parts = line.split()
                if len(parts) >= 4:
                    current_iface = parts[1]
                    in_iface_block = True
                else:
                    current_iface = None
                    in_iface_block = False
                iface_block_lines = [line]
                continue

            if line.strip() and not line.startswith((" ", "\t")) and in_iface_block:
                flush_block()

            if in_iface_block:
                for driver_name, pattern in self.vmware_drivers.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        line = f"# {line}  # VMware token removed by hyper2kvm"
                        fixes_applied.append(f"removed-vmware-token-{driver_name}")
                        break

                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    if re.match(r"(?im)^\s*hwaddress\s+ether\s+.*$", line):
                        line = f"# {line}  # MAC pinning removed by hyper2kvm"
                        fixes_applied.append("removed-hwaddress")

                iface_block_lines.append(line)
            else:
                for driver_name, pattern in self.vmware_drivers.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        line = f"# {line}  # VMware token removed by hyper2kvm"
                        fixes_applied.append(f"removed-vmware-token-{driver_name}")
                        break
                new_lines.append(line)

        flush_block()

        new_content = "\n".join(new_lines)
        return FixResult(
            config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings
        )

    def fix_systemd_network(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks  # .network file fixer covers many independent section/key cases
        self,
        config: NetworkConfig,
        *,
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix systemd-networkd .network files.

        Fixes applied:
        - Remove MACAddress matching (MODERATE+)
        - Rename interface names in [Match] Name= (AGGRESSIVE mode)
        - Remove VMware driver tokens
        - Normalize DHCP= values
        - Add DHCP=yes when no static config present (AGGRESSIVE mode)

        Args:
            config: NetworkConfig object to fix
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []
        warnings: list[str] = []
        rm = rename_map or {}

        lines = content.split("\n")
        new_lines: list[str] = []

        sec = None
        saw_network_section = False
        in_network_section = False
        in_match_section = False
        saw_dhcp = False
        saw_static = False

        def is_static_key(ln: str) -> bool:
            return bool(
                re.match(
                    r"^\s*(Address|Gateway|DNS|Domains|Routes?|RoutingPolicyRule)\s*=", ln, re.IGNORECASE
                )
            )

        for line in lines:
            stripped = line.strip()

            msec = re.match(r"^\s*\[(.+)\]\s*$", stripped)
            if msec:
                sec = msec.group(1).strip().lower()
                in_match_section = sec == "match"
                in_network_section = sec == "network"
                if in_network_section:
                    saw_network_section = True
                new_lines.append(line)
                continue

            if in_match_section:
                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    if re.match(r"^\s*MACAddress\s*=", line, re.IGNORECASE):
                        new_lines.append(f"# {line}  # MAC pinning removed by hyper2kvm")
                        fixes_applied.append("removed-mac-match")
                        continue

                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    m = re.match(r"^\s*Name\s*=\s*(.+)\s*$", line, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        parts = re.split(r"\s+", val)
                        changed = False
                        out_parts: list[str] = []
                        for p in parts:
                            # AGGRESSIVE with rename map: use the mapped name
                            if (
                                self.fix_level == FixLevel.AGGRESSIVE
                                and rm
                                and p in rm
                                and not any(ch in p for ch in "*?[]")
                            ):
                                out_parts.append(rm[p])
                                changed = True
                            # MODERATE+: replace VMware-specific names with wildcard
                            elif not any(ch in p for ch in "*?[]"):
                                for pattern, _tag in INTERFACE_NAME_PATTERNS:
                                    if re.match(pattern, p, re.IGNORECASE):
                                        out_parts.append("en*")
                                        changed = True
                                        break
                                else:
                                    out_parts.append(p)
                            else:
                                out_parts.append(p)
                        if changed:
                            line = re.sub(
                                r"(?:^(\s*Name\s*=\s*)).*$",
                                r"\1" + " ".join(out_parts),
                                line,
                                flags=re.IGNORECASE,
                            )
                            fixes_applied.append("replaced-networkd-vmware-match-name")

            for driver_name, pattern in self.vmware_drivers.items():
                if re.search(pattern, line, re.IGNORECASE) and not line.lstrip().startswith("#"):
                    new_lines.append(f"# {line}  # VMware token removed by hyper2kvm")
                    fixes_applied.append(f"removed-vmware-token-{driver_name}")
                    break
            else:
                if in_network_section:
                    if re.match(r"^\s*DHCP\s*=", line, re.IGNORECASE):
                        saw_dhcp = True
                        if not re.search(r"(?i)=\s*(yes|true|ipv4|ipv6|both)\b", line):
                            line = "DHCP=yes"
                            fixes_applied.append("normalized-dhcp")
                    if is_static_key(line):
                        saw_static = True

                new_lines.append(line)

        # If MAC matching was removed and there's no DHCP or static config,
        # the interface has no way to get an address. Add DHCP=yes.
        mac_was_removed = any("removed-mac-match" in f for f in fixes_applied)
        needs_dhcp = (
            saw_network_section
            and not saw_dhcp
            and not saw_static
            and (self.fix_level == FixLevel.AGGRESSIVE or mac_was_removed)
        )
        if needs_dhcp:
            out: list[str] = []
            inserted = False
            for ln in new_lines:
                out.append(ln)
                if ln.strip().lower() == "[network]" and not inserted:
                    out.append("DHCP=yes")
                    fixes_applied.append("added-dhcp")
                    inserted = True
            new_lines = out

        new_content = "\n".join(new_lines)
        return FixResult(
            config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings
        )

    def fix_network_manager(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # .nmconnection fixer covers many independent section/key cases
        self,
        config: NetworkConfig,
        *,
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix NetworkManager connection profiles (.nmconnection).

        Fixes applied:
        - Remove MAC pinning (mac-address, cloned-mac-address, mac-address-blacklist)
        - Rename interface-name (AGGRESSIVE mode)
        - Rename VLAN parent (AGGRESSIVE mode)
        - Remove VMware driver hints

        Args:
            config: NetworkConfig object to fix
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []
        warnings: list[str] = []
        rm = rename_map or {}

        lines = content.split("\n")
        new_lines: list[str] = []
        sec = None

        def has_vmware_token(val: str) -> bool:
            for pat in self.vmware_drivers.values():
                if re.search(pat, val, re.IGNORECASE):
                    return True
            return bool(re.search(r"(?i)\bvmware\b", val))

        def _is_vmware_interface(name: str) -> bool:
            """Check if interface name is VMware-specific."""
            return any(re.match(pattern, name, re.IGNORECASE) for pattern, _tag in INTERFACE_NAME_PATTERNS)

        # First pass: determine connection type to scope UUID removal
        conn_type = ""
        for line in lines:
            m = re.match(r"^\s*type\s*=\s*(\S+)", line, re.IGNORECASE)
            if m:
                conn_type = m.group(1).strip().lower()
                break
        is_ethernet_conn = conn_type in ("ethernet", "802-3-ethernet", "")

        for line in lines:
            s = line.strip()
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                new_lines.append(line)
                continue

            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE) and re.match(
                r"^\s*(mac-address|cloned-mac-address|mac-address-blacklist)\s*=", line, re.IGNORECASE
            ):
                new_lines.append(f"# {line}  # MAC pinning removed by hyper2kvm")
                fixes_applied.append("removed-nm-mac")
                continue

            # Remove stale UUID from ethernet connections only — VPN, wifi,
            # and other profile types may be referenced by UUID in scripts.
            if (
                self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE)
                and sec == "connection"
                and is_ethernet_conn
            ):
                if re.match(r"^\s*uuid\s*=", line, re.IGNORECASE):
                    new_lines.append(f"# {line}  # stale UUID removed by hyper2kvm")
                    fixes_applied.append("removed-nm-uuid")
                    continue

            # Fix autoconnect=false — migrated VMs should auto-start networking
            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE) and re.match(
                r"^\s*autoconnect\s*=\s*false\s*$", line, re.IGNORECASE
            ):
                new_lines.append("autoconnect=true")
                fixes_applied.append("enabled-nm-autoconnect")
                continue

            # Remove VMware-specific interface-name at MODERATE+ level
            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                if re.match(r"^\s*interface-name\s*=", line, re.IGNORECASE):
                    m = re.match(r"^\s*interface-name\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
                    if m:
                        cur = m.group(1).strip()
                        # AGGRESSIVE with rename map: rename the interface
                        if self.fix_level == FixLevel.AGGRESSIVE and cur in rm:
                            line = f"interface-name={rm[cur]}"
                            fixes_applied.append("renamed-nm-interface-name")
                        # MODERATE+: remove VMware-specific interface names
                        elif _is_vmware_interface(cur):
                            new_lines.append(f"# {line}  # VMware interface-name removed by hyper2kvm")
                            fixes_applied.append("removed-nm-vmware-interface-name")
                            continue

            if self.fix_level == FixLevel.AGGRESSIVE and rm:
                if sec == "vlan" and re.match(r"^\s*parent\s*=", line, re.IGNORECASE):
                    m = re.match(r"^\s*parent\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
                    if m:
                        cur = m.group(1).strip()
                        if cur in rm:
                            line = f"parent={rm[cur]}"
                            fixes_applied.append("renamed-nm-vlan-parent")

            if re.match(r"^\s*driver\s*=", line, re.IGNORECASE) and not line.lstrip().startswith("#"):
                m = re.match(r"^\s*driver\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
                if m and has_vmware_token(m.group(1)):
                    new_lines.append(f"# {line}  # VMware driver hint removed by hyper2kvm")
                    fixes_applied.append("removed-nm-driver-hint")
                    continue

            new_lines.append(line)

        new_content = "\n".join(new_lines)
        return FixResult(
            config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings
        )

    def fix_wicked_xml(self, config: NetworkConfig) -> FixResult:
        """
        Fix Wicked XML configuration files (SUSE).

        Fixes applied:
        - Remove <mac-address> tags (MODERATE+)
        - Remove <match><mac-address> tags (MODERATE+)

        Args:
            config: NetworkConfig object to fix

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []

        if self.fix_level not in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            return FixResult(config=config, new_content=content, applied_fixes=[])

        new_content = content
        patterns = [
            (r"(?is)<\s*mac-address\s*>[^<]+<\s*/\s*mac-address\s*>", "wicked-mac-address"),
            (
                r"(?is)<\s*match\s*>.*?<\s*mac-address\s*>.*?</\s*mac-address\s*>.*?</\s*match\s*>",
                "wicked-match-mac",
            ),
        ]
        for pat, tag in patterns:
            if re.search(pat, new_content):
                new_content = re.sub(pat, "<!-- removed by hyper2kvm -->", new_content)
                fixes_applied.append(f"removed-mac-pinning-{tag}")

        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied)


__all__ = ["NetworkFixersBackend"]
