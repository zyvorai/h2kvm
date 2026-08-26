# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Live migration support module.

This module provides live VM migration capabilities with minimal downtime using
HyperSDK for multi-provider support (VMware, Hyper-V, KVM, AWS, Azure, GCP).

Components:
- Live Migration Analyzer: Determines VM migration feasibility
- HyperSDK Integration: Interfaces with HyperSDK for provider abstraction
- Hybrid Migration Manager: Combines live migration with offline fixes
- Live Migration Orchestrator: Coordinates the entire live migration workflow
"""

from .analyzer import LiveMigrationAnalyzer
from .hybrid_manager import HybridMigrationManager
from .hypersdk_integration import HyperSDKIntegration
from .orchestrator import LiveMigrationOrchestrator

__all__ = [
    "HybridMigrationManager",
    "HyperSDKIntegration",
    "LiveMigrationAnalyzer",
    "LiveMigrationOrchestrator",
]
