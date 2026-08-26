# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/network_model.py
"""
Network model + topology helpers for VMware -> KVM network config fixing.

This file intentionally contains:
- Enums/dataclasses (NetworkConfig, FixResult, etc.)
- TopologyGraph (best-effort)
- IfcfgKV parser (loss-minimizing key=value editor)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import builtins

# Enums / dataclasses


class NetworkConfigType(Enum):
    """Types of network configuration files."""

    IFCFG_RH = "ifcfg-rh"  # RHEL-ish ifcfg files (also SUSE ifcfg works similarly)
    NETPLAN = "netplan"  # Ubuntu netplan YAML
    INTERFACES = "interfaces"  # Debian interfaces
    SYSTEMD_NETWORK = "systemd-network"  # systemd-networkd .network
    SYSTEMD_NETDEV = "systemd-netdev"  # systemd-networkd .netdev
    NETWORK_MANAGER = "network-manager"  # NetworkManager profiles
    WICKED = "wicked"  # SUSE wicked XML
    WICKED_IFCFG = "wicked-ifcfg"  # SUSE ifcfg files
    UNKNOWN = "unknown"


class FixLevel(Enum):
    """Level of fix aggressiveness."""

    CONSERVATIVE = "conservative"  # Minimal changes (VMware specifics only)
    MODERATE = "moderate"  # VMware + MAC pinning removal (recommended)
    AGGRESSIVE = "aggressive"  # Normalize naming + apply more "sane defaults"


@dataclass
class NetworkConfig:  # pylint: disable=too-many-instance-attributes
    """Represents a network configuration file.

    Many independent fields track the file's content, parsed type, and the
    fix/backup bookkeeping applied to it; splitting them would obscure the model.
    """

    path: str
    content: str
    type: NetworkConfigType
    original_hash: str = ""
    modified: bool = False
    backup_path: str = ""
    error: str | None = None
    fixes_applied: list[str] = field(default_factory=list)


@dataclass
class FixResult:
    """Result of fixing a network configuration."""

    config: NetworkConfig
    new_content: str
    applied_fixes: list[str]
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backup_created: bool = False


# Topology model (best-effort)


class DeviceKind(Enum):
    """Kind of network device in the topology graph."""

    ETHERNET = "ethernet"
    BOND = "bond"
    BRIDGE = "bridge"
    VLAN = "vlan"
    UNKNOWN = "unknown"


@dataclass
class TopoNode:
    """A device node in the best-effort network topology graph."""

    name: str
    kind: DeviceKind
    sources: set[str] = field(default_factory=set)  # config paths
    props: dict[str, Any] = field(default_factory=dict)  # arbitrary parsed details


@dataclass
class TopoEdge:
    """A directed relationship (slave/port/vlan) between two topology nodes."""

    src: str
    dst: str
    kind: str  # "slave", "port", "vlan"


class TopologyGraph:
    """
    Minimal topology graph:
      - Nodes: devices (ethX / ens192 / bond0 / br0 / br-ex / vlan100 or eth0.100)
      - Edges:
          ethernet -> bond ("slave")
          ethernet -> bridge ("port")
          bond -> bridge ("port")
          parent -> vlan ("vlan")
    """

    def __init__(self) -> None:
        self.nodes: dict[str, TopoNode] = {}
        self.edges: list[TopoEdge] = []
        self.warnings: list[str] = []

    def add_node(self, name: str, kind: DeviceKind, *, source: str | None = None, **props: Any) -> None:
        """Add or update a device node, upgrading UNKNOWN kind and merging props."""
        if not name:
            return
        n = self.nodes.get(name)
        if n is None:
            n = TopoNode(name=name, kind=kind)
            self.nodes[name] = n
        # Upgrade UNKNOWN -> known kind if new info arrives
        elif n.kind == DeviceKind.UNKNOWN and kind != DeviceKind.UNKNOWN:
            n.kind = kind

        if source:
            n.sources.add(source)

        # Prefer latest facts (later parsers often know more)
        for k, v in props.items():
            n.props[k] = v

    def add_edge(self, src: str, dst: str, kind: str) -> None:
        """Record a directed edge between two device names, if both are set."""
        if not src or not dst:
            return
        self.edges.append(TopoEdge(src=src, dst=dst, kind=kind))

    def infer_kind(self, name: str) -> DeviceKind:
        """Return the known kind for `name`, or guess it from naming heuristics."""
        if name in self.nodes:
            return self.nodes[name].kind

        # Heuristics
        if re.match(r"^bond\d+$", name):
            return DeviceKind.BOND

        # Bridges: br0, br-ex, br-int, bridge0, bridge1...
        if re.match(r"^(br|bridge)\d+$", name) or name.startswith("br-"):
            return DeviceKind.BRIDGE

        # VLAN-ish: eth0.100 / ens3.20 etc.
        if re.match(r"^\w+\.\d+$", name):
            return DeviceKind.VLAN

        return DeviceKind.UNKNOWN

    def rename_map_propagate(self, rename_map: dict[str, str]) -> dict[str, str]:
        """
        Expand rename map across trivial VLAN names (eth0.100), if present.

        We propagate based on currently-known node/edge names, so callers can
        apply the expanded mapping back onto config files.
        """
        out = dict(rename_map)

        # Collect names we can see in the graph
        seen: set[str] = set(self.nodes.keys())
        for e in self.edges:
            seen.add(e.src)
            seen.add(e.dst)

        for old, new in list(rename_map.items()):
            # Only propagate "old.<vid>" -> "new.<vid>" for patterns we actually observed
            for n in seen:
                if n.startswith(old + "."):
                    out[n] = n.replace(old + ".", new + ".", 1)

        return out

    def apply_rename_map(self, rename_map: dict[str, str]) -> None:
        """
        Apply renames to graph state (nodes + edges).

        This is optional; use it if you want the topology summary to reflect
        post-fix interface names.

        NOTE: We do not enforce that every edge endpoint has a node.
        This graph is best-effort and may contain dangling edges.
        """
        if not rename_map:
            return

        # Rename nodes (re-key dict)
        new_nodes: dict[str, TopoNode] = {}
        for name, node in self.nodes.items():
            new_name = rename_map.get(name, name)
            node.name = new_name
            if new_name in new_nodes:
                # Merge if collision
                existing = new_nodes[new_name]
                if existing.kind == DeviceKind.UNKNOWN and node.kind != DeviceKind.UNKNOWN:
                    existing.kind = node.kind
                existing.sources |= node.sources
                existing.props.update(node.props)
            else:
                new_nodes[new_name] = node
        self.nodes = new_nodes

        # Rename edges
        for e in self.edges:
            e.src = rename_map.get(e.src, e.src)
            e.dst = rename_map.get(e.dst, e.dst)

    def summarize(self) -> dict[str, Any]:
        """Return a summary dict of devices grouped by kind, edges, and warnings."""
        by_kind: dict[str, list[str]] = {}
        for n in self.nodes.values():
            by_kind.setdefault(n.kind.value, []).append(n.name)
        for k in list(by_kind.keys()):
            by_kind[k] = sorted(set(by_kind[k]))
        edges = [{"src": e.src, "dst": e.dst, "kind": e.kind} for e in self.edges]
        return {"devices": by_kind, "edges": edges, "warnings": self.warnings}


# ifcfg parser (key=value preserving unknown lines/comments)


@dataclass
class IfcfgKV:
    """
    Simple ifcfg representation.
    - Preserves original lines order.
    - Parses KEY=VALUE (supports quoted values).
    - Allows rewriting keys while keeping comments/unknown lines intact.

    Notes:
      - Tracks duplicates (same key multiple times) to avoid silent weirdness.
      - Tracks keys commented out by this editor, so later set() doesn't overwrite comments.
    """

    lines: list[str]
    kv: dict[str, str] = field(default_factory=dict)
    key_line_idx: dict[str, int] = field(default_factory=dict)  # last *active* line index
    duplicates: dict[str, list[int]] = field(
        default_factory=dict
    )  # key -> line indices (active occurrences)
    commented_keys: builtins.set[str] = field(default_factory=set)  # keys we commented out via this editor
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def _strip_inline_comment_unquoted(val: str) -> str:
        """
        Strip inline comments from an unquoted value (conservative).

        Example:
          FOO=bar # comment  -> "bar"
          FOO="bar # ok"     -> unchanged (handled by quoted parsing)
          FOO=bar#baz        -> unchanged (intentionally conservative)
        """
        m = re.search(r"\s+#", val)
        if m:
            return val[: m.start()].rstrip()
        return val

    @staticmethod
    def parse(text: str) -> IfcfgKV:
        """Parse ifcfg text into an IfcfgKV, tracking duplicate active keys."""
        lines = text.splitlines()
        kv: dict[str, str] = {}
        idx: dict[str, int] = {}
        dups: dict[str, list[int]] = {}
        warnings: list[str] = []

        for i, ln in enumerate(lines):
            # Skip pure comments early (they're preserved in lines, just not "active" keys)
            if ln.lstrip().startswith("#"):
                continue

            m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$", ln)
            if not m:
                continue

            key = m.group(1).strip().upper()
            val = m.group(2).strip()

            # Handle quoted values
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val2 = val[1:-1]
            else:
                # Strip inline comments for unquoted values
                val2 = IfcfgKV._strip_inline_comment_unquoted(val)

            # Track duplicates (active assignments only)
            if key in dups:
                dups[key].append(i)
            elif key in idx:
                dups[key] = [idx[key], i]

            kv[key] = val2
            idx[key] = i

        for k, where in sorted(dups.items()):
            warnings.append(f"ifcfg duplicate active key {k} on lines {where} (last one wins)")

        return IfcfgKV(lines=lines, kv=kv, key_line_idx=idx, duplicates=dups, warnings=warnings)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the active value for `key` (case-insensitive), or `default`."""
        return self.kv.get(key.upper(), default)

    def has(self, key: str) -> bool:
        """Return True if `key` has an active (non-commented) value."""
        return key.upper() in self.kv

    def is_commented(self, key: str) -> bool:
        """Return True if `key` was commented out by this editor."""
        return key.upper() in self.commented_keys

    def set(self, key: str, value: str, *, quote: bool = False) -> None:
        """Set `key` to `value`, appending a new line if the prior one was commented."""
        k = key.upper()
        out_val = f'"{value}"' if quote else value
        line = f"{k}={out_val}"

        # If previously commented out (by us) OR the last known line is commented,
        # append a fresh active line instead of overwriting the comment.
        if k in self.key_line_idx:
            i = self.key_line_idx[k]
            existing = self.lines[i] if 0 <= i < len(self.lines) else ""
            if existing.lstrip().startswith("#") or k in self.commented_keys:
                self.key_line_idx[k] = len(self.lines)
                self.lines.append(line)
            else:
                self.lines[i] = line
        else:
            self.key_line_idx[k] = len(self.lines)
            self.lines.append(line)

        self.kv[k] = value
        self.commented_keys.discard(k)

    def comment_out(self, key: str, tag: str) -> bool:
        """Comment out `key`'s active line (tagging it) and drop it from the model."""
        k = key.upper()

        # Commenting out means "no active definition" afterwards.
        if k not in self.key_line_idx:
            # Might still exist in kv from external meddling; make model consistent.
            self.kv.pop(k, None)
            self.commented_keys.add(k)
            return False

        i = self.key_line_idx[k]
        if not 0 <= i < len(self.lines):
            self.kv.pop(k, None)
            self.commented_keys.add(k)
            self.key_line_idx.pop(k, None)
            return False

        ln = self.lines[i]
        if ln.lstrip().startswith("#"):
            # Already commented; ensure model doesn't pretend it's active.
            self.kv.pop(k, None)
            self.commented_keys.add(k)
            self.key_line_idx.pop(k, None)
            return False

        self.lines[i] = f"# {ln}  # {tag}"

        # Keep the editor model honest: no active key remains.
        self.kv.pop(k, None)
        self.commented_keys.add(k)
        self.key_line_idx.pop(k, None)

        return True

    def delete(self, key: str, tag: str) -> bool:
        """Delete `key` (implemented as comment_out, which is safer than removing)."""
        # safer than removing; comment out and update model
        return self.comment_out(key, tag)

    def render(self) -> str:
        """Render the current lines back into ifcfg file text."""
        # Keep a trailing newline for POSIX sanity
        out = "\n".join(self.lines)
        if not out.endswith("\n"):
            out += "\n"
        return out


def ifcfg_kind_and_links(ifcfg: IfcfgKV) -> tuple[DeviceKind, list[TopoEdge]]:
    """
    Infer device kind and edges from an ifcfg file.
    """
    dev = (ifcfg.get("DEVICE") or "").strip()
    typ = (ifcfg.get("TYPE") or "").strip().lower()
    edges: list[TopoEdge] = []

    kind = DeviceKind.ETHERNET

    # Bond
    if ifcfg.get("BONDING_MASTER", "").lower() == "yes" or typ == "bond":
        kind = DeviceKind.BOND

    # Bridge (prefer explicit type, otherwise conservative name patterns)
    elif typ == "bridge" or (dev and (re.match(r"^(br|bridge)\d+$", dev) or dev.startswith("br-"))):
        kind = DeviceKind.BRIDGE

    # VLAN (prefer explicit VLAN=yes or PHYSDEV, then fall back to pattern)
    else:
        vlan_yes = ifcfg.get("VLAN", "").lower() == "yes"
        phys = (ifcfg.get("PHYSDEV") or "").strip()
        dotted_vlan = bool(dev and re.match(r"^\w+\.\d+$", dev))
        if vlan_yes or bool(phys) or dotted_vlan:
            kind = DeviceKind.VLAN

    # Slave link (eth -> bond)
    if ifcfg.get("SLAVE", "").lower() == "yes" and ifcfg.has("MASTER"):
        master = (ifcfg.get("MASTER") or "").strip()
        if dev and master:
            edges.append(TopoEdge(src=dev, dst=master, kind="slave"))

    # Port link (eth/bond -> bridge)
    if ifcfg.has("BRIDGE"):
        br = (ifcfg.get("BRIDGE") or "").strip()
        if dev and br:
            edges.append(TopoEdge(src=dev, dst=br, kind="port"))

    # VLAN parent link
    phys = (ifcfg.get("PHYSDEV") or "").strip()
    if kind == DeviceKind.VLAN:
        if phys and dev:
            edges.append(TopoEdge(src=phys, dst=dev, kind="vlan"))
        elif dev and re.match(r"^\w+\.\d+$", dev):
            parent = dev.split(".", 1)[0]
            edges.append(TopoEdge(src=parent, dst=dev, kind="vlan"))

    return kind, edges
