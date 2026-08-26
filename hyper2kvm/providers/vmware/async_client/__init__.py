# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/async_client/__init__.py
"""
Async VMware client for parallel operations.

Provides async/await API for concurrent VM migrations.
"""

from ....core.optional_imports import HTTPX_AVAILABLE

__all__ = ["HTTPX_AVAILABLE"]

if HTTPX_AVAILABLE:
    from .client import AsyncVMwareClient
    from .operations import AsyncVMwareOperations
    from .semaphore import ConcurrencyManager

    __all__ += ["AsyncVMwareClient", "AsyncVMwareOperations", "ConcurrencyManager"]
