# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Typed configuration dataclasses for the migration pipeline.

Replaces scattered getattr(args, ...) calls with type-safe, documented
configuration objects that can be constructed from argparse.Namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hyper2kvm.core.constants import DEFAULT_CONTAINER_ISOLATION


def resolve_enable_rdp(
    enable_rdp: bool | None,
    *,
    guest_os: str | None = None,
    windows: bool = False,
) -> bool | None:
    """Default enable_rdp=True for Windows guests when unset; Linux leaves None."""
    if enable_rdp is not None:
        return enable_rdp
    g = (guest_os or "").lower()
    if windows or g == "windows" or ("win" in g and g not in ("darwin",)):
        return True
    return None


if TYPE_CHECKING:
    import argparse


@dataclass
class DiskProcessingConfig:  # pylint: disable=too-many-instance-attributes
    # reason: dataclass models the full set of independent disk-processing config
    # fields (inspection, flattening, offline fixes, conversion, output); splitting
    # would fragment a single argparse-derived config surface.
    """
    Configuration for disk processing pipeline operations.

    Covers VMDK inspection, flattening, offline fixes, format conversion,
    and output options. Constructed from argparse.Namespace via from_args().

    See Also:
        - OfflineFixConfig: Subset used by the offline fixer engine
        - Orchestrator: Uses MigrationConfig for orchestration-level settings
    """

    # Working directory
    workdir: str | None = None

    # VMDK inspection
    skip_vmdk_inspection: bool = False
    vmdk_auto_fix_controller: bool = False

    # Snapshot flattening
    flatten: bool = False
    flatten_format: str = "qcow2"

    # Report
    report: str | None = None

    # Offline fix flags
    dry_run: bool = False
    no_backup: bool = False
    print_fstab: bool = False
    no_grub: bool = False
    regen_initramfs: bool = True
    fstab_mode: str = "stabilize-all"
    remove_vmware_tools: bool = False
    enable_rdp: bool | None = None
    resize: str | None = None
    serial_console: bool = True
    initramfs_add_drivers: list[str] | None = None

    # Windows / drivers
    windows: bool = False
    guest_os: str | None = None
    virtio_drivers_dir: str | None = None
    custom_pnp_drivers: list[str] | None = None

    # LUKS
    luks_enable: bool = False
    luks_passphrase: str | None = None
    luks_passphrase_env: str | None = None
    luks_keyfile: str | None = None
    luks_mapper_prefix: str = "hyper2kvm-crypt"

    # Backend
    backend: str = "vmcraft"
    container_isolation: bool = DEFAULT_CONTAINER_ISOLATION
    conversion_dir: str | None = None
    allowed_dirs: list[str] | None = None

    # Injection config file paths
    cloud_init_config: str | None = None
    firstboot_scripts: str | None = None
    network_config_inject: str | None = None
    user_config_inject: str | None = None
    service_config_inject: str | None = None
    hostname_config_inject: str | None = None

    # Convenience user setup
    root_password: str | None = None
    ssh_authorized_key: str | None = None

    # Output conversion
    to_output: str | None = None
    out_format: str = "qcow2"
    compress: bool = False
    compress_level: int | None = None
    checksum: bool = False
    cleanup_cache: bool = True

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> DiskProcessingConfig:
        """Construct from argparse.Namespace with safe defaults."""
        return cls(
            workdir=getattr(args, "workdir", None),
            skip_vmdk_inspection=getattr(args, "skip_vmdk_inspection", False),
            vmdk_auto_fix_controller=getattr(args, "vmdk_auto_fix_controller", False),
            flatten=getattr(args, "flatten", False),
            flatten_format=getattr(args, "flatten_format", "qcow2"),
            report=getattr(args, "report", None),
            dry_run=getattr(args, "dry_run", False),
            no_backup=getattr(args, "no_backup", False),
            print_fstab=getattr(args, "print_fstab", False),
            no_grub=getattr(args, "no_grub", False),
            regen_initramfs=getattr(args, "regen_initramfs", True),
            fstab_mode=getattr(args, "fstab_mode", "stabilize-all"),
            remove_vmware_tools=getattr(args, "remove_vmware_tools", False),
            enable_rdp=getattr(args, "enable_rdp", None),
            resize=getattr(args, "resize", None),
            serial_console=getattr(args, "serial_console", True),
            initramfs_add_drivers=getattr(args, "initramfs_add_drivers", None),
            windows=getattr(args, "windows", False),
            guest_os=getattr(args, "guest_os", None),
            virtio_drivers_dir=getattr(args, "virtio_drivers_dir", None),
            custom_pnp_drivers=getattr(args, "custom_pnp_drivers", None),
            luks_enable=getattr(args, "luks_enable", False),
            luks_passphrase=getattr(args, "luks_passphrase", None),
            luks_passphrase_env=getattr(args, "luks_passphrase_env", None),
            luks_keyfile=getattr(args, "luks_keyfile", None),
            luks_mapper_prefix=getattr(args, "luks_mapper_prefix", "hyper2kvm-crypt"),
            backend=getattr(args, "backend", "vmcraft"),
            container_isolation=getattr(args, "container_isolation", DEFAULT_CONTAINER_ISOLATION),
            conversion_dir=getattr(args, "conversion_dir", None),
            allowed_dirs=getattr(args, "allowed_dirs", None),
            cloud_init_config=getattr(args, "cloud_init_config", None),
            firstboot_scripts=getattr(args, "firstboot_scripts", None),
            network_config_inject=getattr(args, "network_config_inject", None),
            user_config_inject=getattr(args, "user_config_inject", None),
            service_config_inject=getattr(args, "service_config_inject", None),
            hostname_config_inject=getattr(args, "hostname_config_inject", None),
            root_password=getattr(args, "root_password", None),
            ssh_authorized_key=getattr(args, "ssh_authorized_key", None),
            to_output=getattr(args, "to_output", None),
            out_format=getattr(args, "out_format", "qcow2"),
            compress=getattr(args, "compress", False),
            compress_level=getattr(args, "compress_level", None),
            checksum=getattr(args, "checksum", False),
            cleanup_cache=getattr(args, "cleanup_cache", True),
        )

    def is_luks_enabled(self) -> bool:
        """Check if LUKS unlocking is enabled (explicit flag or implicit via credentials)."""
        if self.luks_enable:
            return True
        return bool(self.luks_passphrase or self.luks_passphrase_env or self.luks_keyfile)


@dataclass
class MigrationConfig:  # pylint: disable=too-many-instance-attributes
    # reason: dataclass models the full set of independent top-level migration
    # config fields (mode, recovery, deployment, daemon settings); splitting would
    # fragment a single argparse-derived config surface.
    """
    Configuration for top-level migration orchestration.

    Covers mode selection, test settings, deployment options, and
    daemon mode configuration. Constructed from argparse.Namespace via from_args().
    """

    # Mode
    cmd: str | None = None
    output_dir: str = "."
    batch_manifest: str | None = None

    # Recovery
    enable_recovery: bool = False

    # vSphere
    vs_action: str = ""

    # Processing
    parallel_processing: bool = False

    # Testing
    libvirt_test: bool = False
    qemu_test: bool = False
    vm_name: str = "converted-vm"
    memory: int = 2048
    vcpus: int = 2
    uefi: bool = False
    timeout: int = 60
    keep_domain: bool = False
    headless: bool = False
    health_check: bool = False
    health_check_timeout: int = 120
    libvirt_network: str = "default"
    libvirt_network_config: dict | None = None

    # Windows VirtIO deployment
    windows: bool = False
    guest_os: str | None = None
    virtio_drivers_dir: str | None = None
    custom_pnp_drivers: list[str] | None = None

    # Windows VirtIO staged boot deployment
    virtio_deploy_boot: bool = False
    virtio_deploy_timeout: int = 180
    virtio_deploy_start_final: bool = True

    # Deployment
    deploy_k8s: bool = False
    k8s_continue_on_error: bool = True
    deploy_openstack: bool = False
    openstack_continue_on_error: bool = True

    # Daemon mode
    manifest_workflow_mode: bool = False
    manifest_workflow_dir: str | None = None
    workflow_mode: bool = False
    workflow_dir: str | None = None
    watch_dir: str | None = None

    # AI migration intelligence
    no_ai: bool = False
    ai_info: bool = False

    # Shared with DiskProcessingConfig
    dry_run: bool = False
    to_output: str | None = None
    flatten: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> MigrationConfig:
        """Construct from argparse.Namespace with safe defaults."""
        return cls(
            cmd=getattr(args, "cmd", None),
            output_dir=getattr(args, "output_dir", "."),
            batch_manifest=getattr(args, "batch_manifest", None),
            enable_recovery=getattr(args, "enable_recovery", False),
            vs_action=getattr(args, "vs_action", ""),
            parallel_processing=getattr(args, "parallel_processing", False),
            libvirt_test=getattr(args, "libvirt_test", False),
            qemu_test=getattr(args, "qemu_test", False),
            vm_name=getattr(args, "vm_name", "converted-vm"),
            memory=getattr(args, "memory", 2048),
            vcpus=getattr(args, "vcpus", 2),
            uefi=getattr(args, "uefi", False),
            timeout=getattr(args, "timeout", 60),
            keep_domain=getattr(args, "keep_domain", False),
            headless=getattr(args, "headless", False),
            health_check=getattr(args, "health_check", False),
            health_check_timeout=getattr(args, "health_check_timeout", 120),
            libvirt_network=getattr(args, "libvirt_network", "default"),
            libvirt_network_config=getattr(args, "libvirt_network_config", None),
            windows=getattr(args, "windows", False),
            guest_os=getattr(args, "guest_os", None),
            virtio_drivers_dir=getattr(args, "virtio_drivers_dir", None),
            custom_pnp_drivers=getattr(args, "custom_pnp_drivers", None),
            virtio_deploy_boot=getattr(args, "virtio_deploy_boot", False),
            virtio_deploy_timeout=getattr(args, "virtio_deploy_timeout", 180),
            virtio_deploy_start_final=getattr(args, "virtio_deploy_start_final", True),
            deploy_k8s=getattr(args, "deploy_k8s", False),
            k8s_continue_on_error=getattr(args, "k8s_continue_on_error", True),
            deploy_openstack=getattr(args, "deploy_openstack", False),
            openstack_continue_on_error=getattr(args, "openstack_continue_on_error", True),
            manifest_workflow_mode=getattr(args, "manifest_workflow_mode", False),
            manifest_workflow_dir=getattr(args, "manifest_workflow_dir", None),
            workflow_mode=getattr(args, "workflow_mode", False),
            workflow_dir=getattr(args, "workflow_dir", None),
            watch_dir=getattr(args, "watch_dir", None),
            no_ai=getattr(args, "no_ai", False),
            ai_info=getattr(args, "ai_info", False),
            dry_run=getattr(args, "dry_run", False),
            to_output=getattr(args, "to_output", None),
            flatten=getattr(args, "flatten", False),
        )
