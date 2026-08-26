# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/network_fixer.py
"""
Comprehensive network configuration fixer for VMware -> KVM migration.

This module provides backward-compatible imports and compatibility wrappers
for the network fixer functionality, which has been refactored into focused
single-responsibility modules:

- network/discovery.py: File discovery and I/O operations
- network/topology.py: Topology building and rename planning
- network/validation.py: Configuration validation
- network/backend.py: Backend-specific fix implementations
- network/core.py: Main orchestrator

The NetworkFixer class is now imported from network.core and re-exported
here for backward compatibility with existing code.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

# Import main orchestrator (re-export for backward compatibility)
from .network.core import NetworkFixer

# Import model types for compatibility
from .network.model import FixLevel

if TYPE_CHECKING:
    from hyper2kvm.core.guestfs_typing import guestfs

# Re-export for backward compatibility
__all__ = ["NetworkFixer", "fix_network_config", "fix_network_config_compat"]


# Optional compatibility wrapper (for project style)


def fix_network_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Compatibility entrypoint: call NetworkFixer directly.

    This function is designed to be called as a method on an object (like
    OfflineFixer) that has logger, network_fix_level, dry_run, and report
    attributes.

    Args:
        self: Object with logger, network_fix_level, dry_run, report attributes
        g: GuestFS handle with root filesystem mounted

    Returns:
        Dict with updated_files, count, and analysis
    """
    fix_level_str = getattr(self, "network_fix_level", "moderate")
    try:
        fix_level = FixLevel(fix_level_str)
    except ValueError:
        fix_level = FixLevel.MODERATE

    fixer = NetworkFixer(
        logger=getattr(self, "logger", logging.getLogger(__name__)),
        fix_level=fix_level,
        dry_run=bool(getattr(self, "dry_run", False)),
    )

    result = fixer.fix_network_config(g, progress_callback=None)

    if hasattr(self, "report"):
        self.report.setdefault("network", {})
        self.report["network"] = result

    updated_files = [d["path"] for d in result["stats"]["details"] if d.get("modified", False)]
    return {"updated_files": updated_files, "count": len(updated_files), "analysis": result}


# Alias that reads nicer in some call sites (keeps old name intact)
fix_network_config_compat = fix_network_config
