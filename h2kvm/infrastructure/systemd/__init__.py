# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Integration Module for H2KVM
=========================================

Deep systemd integration providing:
- Service management and lifecycle control
- Journal structured logging
- Resource control (CPU, memory, IO)
- Socket activation for on-demand processing
- Timer-based scheduled repairs
- Path monitoring for automatic repairs
- D-Bus control interface
- Boot-time integration (repart, growfs, makefs, firstboot)
- Boot performance analysis
- Emergency recovery configuration

Version: 3.0.0
"""

__version__ = "3.0.0"
__author__ = "H2KVM Development Team"
__license__ = "Apache-2.0"

# Import main components
try:
    from .boot import (
        BootEnvironment,
        BootEnvironmentRecovery,
        BootPerformanceAnalyzer,
        BootType,
        FilesystemType,
        MountConfiguration,
        PartitionDefinition,
        PartitionType,
        SystemdBootIntegration,
        SystemdFirstBootManager,
        SystemdGrowfsManager,
        SystemdMakefsManager,
        SystemdMountManager,
        SystemdRemountFSManager,
        SystemdRepartManager,
        SystemdTmpfilesManager,
        SystemdUnitType,
        integrate_with_vm_repair,
    )
    from .firstboot import (
        SystemdFirstboot,
        setup_firstboot_for_converted_image,
    )
    from .firstboot_enterprise import (
        FirstbootConfig,
        generate_enterprise_firstboot_script,
    )
    from .journal import JournalLogger, JournalMonitor
    from .path_monitor import VMPathMonitor
    from .resource_control import ResourceMonitor, SystemdResourceControl
    from .rhel_boot_repair import (
        BootFix,
        BootIssue,
        FixStatus,
        RHELBootRepair,
        Severity,
        detect_and_fix_rhel_boot_issues,
    )
    from .socket_activation import RepairSocketServer
    from .systemd_core import SystemdIntegration

    __all__ = [
        "BootEnvironment",
        "BootEnvironmentRecovery",
        "BootFix",
        "BootIssue",
        "BootPerformanceAnalyzer",
        "BootType",
        "FilesystemType",
        "FirstbootConfig",
        "FixStatus",
        "JournalLogger",
        "JournalMonitor",
        "MountConfiguration",
        # Data classes
        "PartitionDefinition",
        # Enums
        "PartitionType",
        # RHEL boot repair
        "RHELBootRepair",
        "RepairSocketServer",
        "ResourceMonitor",
        "Severity",
        # Boot integration
        "SystemdBootIntegration",
        "SystemdFirstBootManager",
        # Firstboot integration
        "SystemdFirstboot",
        "SystemdGrowfsManager",
        # Core components
        "SystemdIntegration",
        "SystemdMakefsManager",
        "SystemdMountManager",
        "SystemdRemountFSManager",
        "SystemdRepartManager",
        "SystemdResourceControl",
        "SystemdTmpfilesManager",
        "SystemdUnitType",
        "VMPathMonitor",
        "detect_and_fix_rhel_boot_issues",
        "generate_enterprise_firstboot_script",
        # Helper functions
        "integrate_with_vm_repair",
        "setup_firstboot_for_converted_image",
    ]
except ImportError as e:
    # Systemd dependencies not available
    import warnings

    warnings.warn(
        f"Systemd integration dependencies not available: {e}. "
        "Install with: pip install 'h2kvm[systemd]'",
        ImportWarning,
        stacklevel=2,
    )
    __all__ = []


def check_systemd_available() -> bool:
    """Check if systemd integration is available on this system"""
    import importlib.util

    try:
        return (
            importlib.util.find_spec("systemd.daemon") is not None
            and importlib.util.find_spec("systemd.journal") is not None
        )
    except ImportError:
        return False


def get_systemd_version() -> str:
    """Get systemd version if available"""
    try:
        import subprocess

        result = subprocess.run(["systemctl", "--version"], capture_output=True, text=True, check=False)
        first_line = result.stdout.split("\n")[0]
        return first_line.split()[1] if len(first_line.split()) > 1 else "unknown"
    except Exception:
        return "unknown"
