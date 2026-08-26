# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Shared ``/proc/net/dev`` interface-name parsing.

network_topology.py and performance_analyzer.py both parse the guest's
``/proc/net/dev`` to enumerate network interface names (skipping loopback),
then build their own differently-shaped result from that list. Each used to
duplicate the parsing loop, which pylint's duplicate-code (R0801) checker
flagged as cross-file duplication. This module provides the single
canonical parser; callers build their own richer records around it.
"""

from __future__ import annotations


def parse_proc_net_dev_interface_names(content: str) -> list[str]:
    """
    Parse ``/proc/net/dev`` content into non-loopback interface names.

    Args:
        content: Raw text of the guest's /proc/net/dev

    Returns:
        Interface names in file order, excluding "lo"
    """
    names = []
    for line in content.splitlines():
        if ":" not in line:
            continue

        parts = line.split(":")
        if len(parts) >= 2:
            iface_name = parts[0].strip()

            # Skip loopback
            if iface_name == "lo":
                continue

            names.append(iface_name)

    return names
