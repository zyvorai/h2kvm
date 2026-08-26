# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/orchestration/ssh_opts.py
"""
Shared SSH-option normalization helper.

disk_discovery.DiskDiscovery and modes.inventory_mode's inventory handler
both accept a user-supplied `ssh_opt`/`esxi_ssh_opt` CLI value that may
arrive as None, a single string, or a list/tuple of strings, and both
normalized it identically. Centralizing that normalization here avoids
duplicating the same small helper in each orchestration module.
"""

from __future__ import annotations


def normalize_ssh_opts(v: object) -> list[str] | None:
    """Normalize SSH options from various input formats (None, str, list/tuple)."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        out = [str(x) for x in v if x is not None]
        return out or None
    return [str(v)]
