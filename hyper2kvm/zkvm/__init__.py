# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/zkvm/__init__.py
"""
Terminal User Interface (TUI) components for hyper2kvm.

The TUI is now implemented as a standalone Go binary (zkvm) using
Bubble Tea. It communicates with the Python backend via a Unix domain
socket using a newline-delimited JSON protocol.

This package retains the shared backend components:
- migration_tracker: Migration state and history tracking
- migration_controller: Process control (pause/resume/cancel)
- zkvm_config: zkvm configuration management
- types: Shared type definitions
- socket_server: Asyncio Unix socket server for TUI communication
"""

from .types import MigrationStatus

__all__ = [
    "MigrationStatus",
]
