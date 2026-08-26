# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/providers/vmware/__init__.py
"""VMware vSphere provider for h2kvm."""


# Lazy imports to avoid initialization errors
def __getattr__(name):
    """Lazy import for VMware components."""
    if name == "VMwareClient":
        # pylint: disable-next=import-outside-toplevel  # lazy: avoid pulling in heavy VMware client deps at package import time
        from .clients.client import VMwareClient

        return VMwareClient
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["VMwareClient"]  # pylint: disable=undefined-all-variable  # resolved lazily via module __getattr__ (PEP 562), not a static name
