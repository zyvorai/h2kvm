# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/network/udev_rules.py
"""
MAC-based persistent udev rules for network interface naming.

After VMware -> KVM migration, interface names change because the
NIC driver changes (vmxnet3 -> virtio-net). This can break static IP
configurations that reference specific interface names.

This module generates udev rules that map MAC addresses to predictable
interface names, ensuring network configuration survives the migration.

The generated rules go to /etc/udev/rules.d/70-persistent-net.rules
which takes priority over the default predictable naming scheme.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

# pylint: disable=duplicate-code  # typing-only guestfs fallback stub is deliberately repeated per-module
if TYPE_CHECKING:
    import logging

    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # Typing-only fallback so annotations referencing ``guestfs.GuestFS``
        # still resolve when the real ``guestfs`` library isn't installed.
        # Named to match the real module so type checkers accept the alias.
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,too-few-public-methods
            """Typing-only stand-in for the ``guestfs`` module."""

            class GuestFS(Protocol):  # pylint: disable=too-few-public-methods
                """Typing-only stand-in for ``guestfs.GuestFS``."""
# pylint: enable=duplicate-code


_MAC_RE = re.compile(r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$")

RULES_PATH = "/etc/udev/rules.d/70-persistent-net.rules"


# One best-effort scanning method per network backend format; a bad file must not abort the others.
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
# pylint: disable=too-many-nested-blocks,broad-exception-caught
def _extract_mac_iface_mapping(
    g: guestfs.GuestFS,
    logger: logging.Logger,
) -> list[dict[str, str]]:
    """
    Extract MAC->interface mappings from the guest's existing network config.

    Searches:
      - /sys/class/net/*/address (if accessible via guestfs)
      - ifcfg files (HWADDR=)
      - systemd-networkd [Match] MACAddress=
      - NetworkManager mac-address=
      - netplan macaddress:
    """
    mappings: list[dict[str, str]] = []
    seen_macs: set[str] = set()

    def _add(mac: str, iface: str, source: str) -> None:
        mac_norm = mac.strip().lower().replace("-", ":")
        if not _MAC_RE.match(mac_norm):
            return
        if mac_norm in seen_macs:
            return
        # Skip virtual/loopback MACs
        if mac_norm in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
            return
        seen_macs.add(mac_norm)
        mappings.append({"mac": mac_norm, "iface": iface.strip(), "source": source})

    # Method 1: ifcfg-* files (RHEL/CentOS/Fedora)
    for prefix in (
        "/etc/sysconfig/network-scripts",
        "/etc/sysconfig/network",
    ):
        try:
            if not g.is_dir(prefix):
                continue
            for entry in g.ls(prefix):
                if not entry.startswith("ifcfg-"):
                    continue
                iface_name = entry[6:]  # strip "ifcfg-" prefix
                if iface_name in ("lo", "lo0"):
                    continue
                path = f"{prefix}/{entry}"
                try:
                    content = g.read_file(path).decode("utf-8", errors="replace")
                    for line in content.splitlines():
                        line = line.strip()
                        if line.upper().startswith("HWADDR="):
                            mac_val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            _add(mac_val, iface_name, f"ifcfg:{path}")
                except Exception:
                    continue
        except Exception:
            continue

    # Method 2: systemd-networkd .network files
    for netd_dir in ("/etc/systemd/network", "/run/systemd/network"):
        try:
            if not g.is_dir(netd_dir):
                continue
            for entry in g.ls(netd_dir):
                if not entry.endswith(".network"):
                    continue
                path = f"{netd_dir}/{entry}"
                try:
                    content = g.read_file(path).decode("utf-8", errors="replace")
                    mac_val = None
                    name_val = None
                    in_match = False
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("["):
                            in_match = stripped.lower() == "[match]"
                            continue
                        if in_match:
                            if stripped.lower().startswith("macaddress="):
                                mac_val = stripped.split("=", 1)[1].strip()
                            elif stripped.lower().startswith("name="):
                                name_val = stripped.split("=", 1)[1].strip()
                    if mac_val and name_val and not name_val.startswith("*"):
                        _add(mac_val, name_val, f"systemd-networkd:{path}")
                except Exception:
                    continue
        except Exception:
            continue

    # Method 3: NetworkManager .nmconnection files
    nm_dir = "/etc/NetworkManager/system-connections"
    try:
        if g.is_dir(nm_dir):
            for entry in g.ls(nm_dir):
                if not entry.endswith((".nmconnection", ".conf")):
                    continue
                path = f"{nm_dir}/{entry}"
                try:
                    content = g.read_file(path).decode("utf-8", errors="replace")
                    mac_val = None
                    iface_val = None
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped.lower().startswith("mac-address="):
                            mac_val = stripped.split("=", 1)[1].strip()
                        elif stripped.lower().startswith("interface-name="):
                            iface_val = stripped.split("=", 1)[1].strip()
                    if mac_val and iface_val:
                        _add(mac_val, iface_val, f"nm:{path}")
                except Exception:
                    continue
    except Exception:
        pass

    # Method 4: netplan YAML
    netplan_dir = "/etc/netplan"
    try:
        if g.is_dir(netplan_dir):
            for entry in g.ls(netplan_dir):
                if not entry.endswith((".yaml", ".yml")):
                    continue
                path = f"{netplan_dir}/{entry}"
                try:
                    content = g.read_file(path).decode("utf-8", errors="replace")
                    # Simple regex extraction (avoids YAML dependency in guest context)
                    # Match patterns like: macaddress: "aa:bb:cc:dd:ee:ff"
                    current_iface = None
                    for line in content.splitlines():
                        # Detect interface name (indentation-based)
                        m_iface = re.match(r"^\s{4,8}(\w[\w\-]*)\s*:", line)
                        if m_iface:
                            candidate = m_iface.group(1)
                            if candidate not in (
                                "macaddress",
                                "addresses",
                                "gateway4",
                                "nameservers",
                                "routes",
                                "match",
                                "dhcp4",
                                "dhcp6",
                                "mtu",
                                "optional",
                            ):
                                current_iface = candidate
                        m_mac = re.match(r"\s+macaddress\s*:\s*[\"']?([0-9a-fA-F:.-]+)", line)
                        if m_mac and current_iface:
                            _add(m_mac.group(1), current_iface, f"netplan:{path}")
                except Exception:
                    continue
    except Exception:
        pass

    logger.debug("Extracted %d MAC->iface mappings: %s", len(mappings), mappings)
    return mappings
# pylint: enable=too-many-locals,too-many-branches,too-many-statements
# pylint: enable=too-many-nested-blocks,broad-exception-caught


def generate_udev_rules(mappings: list[dict[str, str]]) -> str:
    """
    Generate udev rules content from MAC->interface mappings.

    Format:
      SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="aa:bb:cc:dd:ee:ff", NAME="eth0"
    """
    lines = [
        "# Generated by h2kvm - persistent network interface naming",
        "# Maps MAC addresses to interface names to preserve network config after migration",
        "",
    ]
    for entry in mappings:
        mac = entry["mac"].lower()
        iface = entry["iface"]
        source = entry.get("source", "unknown")
        lines.append(f"# Source: {source}")
        lines.append(f'SUBSYSTEM=="net", ACTION=="add", ATTR{{address}}=="{mac}", NAME="{iface}"')
        lines.append("")
    return "\n".join(lines) + "\n"


def inject_persistent_net_rules(
    g: guestfs.GuestFS,
    logger: logging.Logger,
    *,
    dry_run: bool = False,
    mac_iface_map: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Generate and write persistent udev rules for MAC->interface mapping.

    If ``mac_iface_map`` is provided, uses those mappings directly.
    Otherwise, auto-discovers MAC->iface pairs from existing network config.

    Args:
        g: GuestFS handle with root filesystem mounted
        logger: Logger instance
        dry_run: If True, don't write to disk
        mac_iface_map: Optional pre-built MAC->iface mappings

    Returns:
        Result dict with details of what was done.
    """
    result: dict[str, Any] = {
        "injected": False,
        "dry_run": dry_run,
        "mappings": [],
        "rules_path": RULES_PATH,
        "warnings": [],
        "notes": [],
    }

    # Get or discover mappings
    mappings = mac_iface_map or _extract_mac_iface_mapping(g, logger)

    result["mappings"] = mappings

    if not mappings:
        result["notes"].append(
            "No MAC->interface mappings found in network config. "
            "Skipping udev rule generation (the OS will use predictable naming)."
        )
        logger.info("No MAC->iface mappings found; skipping udev rule injection")
        return result

    # Generate rules content
    rules_content = generate_udev_rules(mappings)

    # Ensure udev rules directory exists
    rules_dir = "/etc/udev/rules.d"
    try:
        if not g.is_dir(rules_dir):
            if not dry_run:
                g.mkdir_p(rules_dir)
    except Exception:  # pylint: disable=broad-exception-caught  # dir may already exist or be unwritable; write below reports failure
        pass

    # Write rules
    if not dry_run:
        try:
            g.write(RULES_PATH, rules_content.encode("utf-8"))
            g.chmod(0o644, RULES_PATH)
            result["injected"] = True
            logger.info(
                "Injected %d MAC->iface udev rules at %s",
                len(mappings),
                RULES_PATH,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort injection, must not abort the caller
            result["warnings"].append(f"Failed to write udev rules: {e}")
            logger.warning("Failed to write udev rules to %s: %s", RULES_PATH, e)
    else:
        result["injected"] = True  # Would have been injected
        logger.info(
            "Dry-run: would inject %d MAC->iface udev rules at %s",
            len(mappings),
            RULES_PATH,
        )

    result["notes"].append(
        f"Generated {len(mappings)} persistent udev rule(s) mapping MAC addresses "
        f"to interface names. This prevents network breakage when NIC drivers change."
    )

    return result


__all__ = [
    "generate_udev_rules",
    "inject_persistent_net_rules",
]
