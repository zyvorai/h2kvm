# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd tools integration for hyper2kvm.

This module provides wrappers around systemd command-line tools to leverage
their functionality for VM migration tasks.

Available integrations:
- systemd-analyze: Performance analysis and boot time inspection
- systemd-cat: Logging to systemd journal
- systemd-cgtop: Real-time cgroup resource monitoring
- systemd-creds: Credential encryption and management
- systemd-cryptenroll: LUKS encryption and TPM2 enrollment
- systemd-delta: Configuration file override detection
- systemd-detect-virt: Virtualization environment detection
- systemd-dissect: Disk image inspection and mounting
- systemd-escape: String escaping for unit names
- systemd-id128: 128-bit ID generation
- systemd-inhibit: Prevent system sleep/shutdown during migrations
- systemd-machine-id-setup: Machine ID initialization
- systemd-mount: Filesystem mounting with unit file generation
- systemd-notify: Service status notifications
- systemd-nspawn: Container spawning for VM testing
- systemd-path: System path locations and monitoring
- systemd-repart: Automatic disk repartitioning
- systemd-run: Transient service execution with resource limits
- systemd-tmpfiles: Temporary file management
- systemd-vmspawn: VM spawning with QEMU/KVM
"""

from .analyze import BootTime, SystemdAnalyze, UnitTime
from .cat import SystemdCat
from .cgtop import CgroupStats, SystemdCgtop
from .creds import SystemdCreds
from .cryptenroll import SystemdCryptenroll
from .delta import ConfigOverride, SystemdDelta
from .detect_virt import SystemdDetectVirt, VirtType
from .dissect import ImageInfo, PartitionInfo, SystemdDissect
from .escape import systemd_escape, systemd_unescape
from .id128 import SystemdId128
from .inhibit import SystemdInhibit
from .machine_id import SystemdMachineId
from .mount import SystemdMount
from .notify import SystemdNotify
from .nspawn import SystemdNspawn
from .path import SystemdPath
from .repart import SystemdRepart
from .run import SystemdRun
from .tmpfiles import SystemdTmpfiles
from .vmspawn import SystemdVmspawn

__all__ = [
    "BootTime",
    "CgroupStats",
    "ConfigOverride",
    "ImageInfo",
    "PartitionInfo",
    "SystemdAnalyze",
    "SystemdCat",
    "SystemdCgtop",
    "SystemdCreds",
    "SystemdCryptenroll",
    "SystemdDelta",
    "SystemdDetectVirt",
    "SystemdDissect",
    "SystemdId128",
    "SystemdInhibit",
    "SystemdMachineId",
    "SystemdMount",
    "SystemdNotify",
    "SystemdNspawn",
    "SystemdPath",
    "SystemdRepart",
    "SystemdRun",
    "SystemdTmpfiles",
    "SystemdVmspawn",
    "UnitTime",
    "VirtType",
    "systemd_escape",
    "systemd_unescape",
]
