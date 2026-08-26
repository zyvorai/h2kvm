# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/__init__.py
"""
hyper2kvm - Hypervisor to KVM Migration Library

A comprehensive tool for migrating virtual machines from various hypervisors
(VMware, Hyper-V, Azure) to KVM/libvirt.

Usage as a library:

    from hyper2kvm import Orchestrator, GuestDetector, VMwareClient

    # Detect guest OS
    detector = GuestDetector()
    guest = detector.detect('/mnt/disk')

    # Migrate from VMware
    client = VMwareClient(host='vcenter.example.com', ...)
    orchestrator = Orchestrator(vmware_client=client)
    result = orchestrator.run()

See docs/08-Library-API.md for detailed usage examples.
"""

__version__ = "2.2.6"


# Use lazy imports to avoid initialization errors
def __getattr__(name):
    # pylint: disable=too-many-return-statements,import-outside-toplevel
    # too-many-return-statements: one early-return dispatch branch per lazily
    # exported name is the whole point of this PEP 562 pattern.
    # import-outside-toplevel: these imports are deliberately lazy, to avoid
    # circular imports and keep heavy/optional submodules from loading eagerly.
    """Lazy import for better performance and to avoid circular dependencies."""
    if name == "Orchestrator":
        from .orchestration import Orchestrator

        return Orchestrator
    if name == "DiskProcessor":
        from .orchestration import DiskProcessor

        return DiskProcessor
    if name == "VMwareClient":
        # pylint: disable=no-name-in-module
        # VMwareClient is itself re-exported lazily via
        # providers.vmware.__getattr__ (PEP 562), so pylint can't see it
        # statically even though it resolves fine at runtime.
        from .providers.vmware import VMwareClient

        return VMwareClient
    if name == "AzureConfig":
        from .providers.azure import AzureConfig

        return AzureConfig
    if name == "AzureSourceProvider":
        from .providers.azure import AzureSourceProvider

        return AzureSourceProvider
    if name == "GuestDetector":
        from .core import GuestDetector

        return GuestDetector
    if name == "GuestIdentity":
        from .core import GuestIdentity

        return GuestIdentity
    if name == "GuestType":
        from .core import GuestType

        return GuestType
    if name == "VMCraft":
        from .vmcraft import VMCraft

        return VMCraft
    if name == "AIOrchestrator":
        # pylint: disable=no-name-in-module
        # AIOrchestrator is itself re-exported lazily via ai.__getattr__
        # (PEP 562), so pylint can't see it statically even though it
        # resolves fine at runtime.
        from .ai import AIOrchestrator

        return AIOrchestrator
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# pylint: disable=undefined-all-variable
# Every name below is supplied lazily by the module-level __getattr__ above
# (PEP 562), not by a module-level assignment/import, so pylint cannot
# verify them statically even though they resolve fine at runtime.
__all__ = [
    # AI
    "AIOrchestrator",
    "AzureConfig",
    # Platform providers
    "AzureSourceProvider",
    "DiskProcessor",
    "GuestDetector",
    # Guest detection
    "GuestIdentity",
    "GuestType",
    # Orchestration
    "Orchestrator",
    # VMCraft API
    "VMCraft",
    "VMwareClient",
    # Version
    "__version__",
]
