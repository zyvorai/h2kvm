# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/network/__init__.py
"""
Network configuration fixer for VMware -> KVM migration.

This package provides comprehensive network configuration fixing for Linux
guest systems being migrated from VMware to KVM. It handles multiple network
backend formats and performs topology-aware fixes.

Main entry point:
    NetworkFixer - Main orchestrator for network fixing operations

Supporting modules:
    - model: Data models and enums (NetworkConfig, FixLevel, etc.)
    - discovery: File discovery and I/O operations
    - topology: Topology graph building and rename planning
    - validation: Post-fix validation to prevent corruption
    - backend: Backend-specific fix implementations
    - core: Main orchestrator coordinating the pipeline
"""

from .core import NetworkFixer
from .model import (
    DeviceKind,
    FixLevel,
    FixResult,
    IfcfgKV,
    NetworkConfig,
    NetworkConfigType,
    TopoEdge,
    TopologyGraph,
    ifcfg_kind_and_links,
)

__all__ = [
    "DeviceKind",
    "FixLevel",
    "FixResult",
    "IfcfgKV",
    # Data models
    "NetworkConfig",
    "NetworkConfigType",
    # Main entry point
    "NetworkFixer",
    "TopoEdge",
    "TopologyGraph",
    # Utility functions
    "ifcfg_kind_and_links",
]
