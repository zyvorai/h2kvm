# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/transports/__init__.py
"""
VMware transport/download mechanisms.

This package provides various transport methods for downloading VM data:
- vddk_client: VMware VDDK-based transport
- vddk_loader: VDDK library loader and wrapper
- http_client: HTTPS download client
- http_progress: Progress reporters for HTTP downloads
- ovftool_client: VMware ovftool-based transport
- ovftool_loader: ovftool binary loader
- govc_common: Common govc utility functions
- govc_export: govc-based export functionality
- hyperctl_common: hypersdk daemon integration (NEW)
"""

# Try to import hyperctl support
try:
    from .hyperctl_common import (
        HyperCtlRunner,
        create_hyperctl_runner,
        export_vm_hyperctl,
    )

    HYPERCTL_AVAILABLE = True
except ImportError:
    HYPERCTL_AVAILABLE = False
    HyperCtlRunner = None
    create_hyperctl_runner = None
    export_vm_hyperctl = None

__all__ = [
    "HYPERCTL_AVAILABLE",
    "HyperCtlRunner",
    "create_hyperctl_runner",
    "export_vm_hyperctl",
]
