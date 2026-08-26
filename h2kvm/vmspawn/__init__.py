# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Production-grade systemd-vmspawn SDK for H2KVM.

This module provides a complete SDK for VM validation using systemd-vmspawn,
including lifecycle management, boot validation, Kubernetes node validation,
async operations for massive scale (1000+ VMs), TPM support, vsock communication,
and cloud-init injection.

Features:
- Synchronous and asynchronous VM operations
- Batch validation (1000+ VMs in parallel)
- TPM emulation support
- vsock host-guest communication
- cloud-init injection
- Kubernetes node validation
- Automatic cleanup engine
"""

from .async_machine import AsyncMachine
from .async_manager import AsyncVMManager
from .async_validator import AsyncKubernetesValidator, AsyncValidator
from .cleanup import CleanupEngine
from .cloudinit import create_cloud_init_config, create_network_config
from .exceptions import (
    VMSpawnError,
    VMStartError,
    VMStopError,
    VMTimeoutError,
    VMValidationError,
)
from .machine import Machine
from .manager import VMSpawnManager
from .models import VMConfig, VMStatus
from .validator import KubernetesNodeValidator, VMValidator
from .vsock import VsockClient, VsockServer

__all__ = [
    "AsyncKubernetesValidator",
    # Async API
    "AsyncMachine",
    "AsyncVMManager",
    "AsyncValidator",
    # Utilities
    "CleanupEngine",
    "KubernetesNodeValidator",
    # Sync API
    "Machine",
    # Models
    "VMConfig",
    # Exceptions
    "VMSpawnError",
    "VMSpawnManager",
    "VMStartError",
    "VMStatus",
    "VMStopError",
    "VMTimeoutError",
    "VMValidationError",
    "VMValidator",
    "VsockClient",
    "VsockServer",
    "create_cloud_init_config",
    "create_network_config",
]
