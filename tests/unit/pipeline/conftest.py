# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures for pipeline unit tests."""

from __future__ import annotations

import logging
import types
from unittest.mock import Mock

import pytest


@pytest.fixture()
def mock_logger():
    """Return a stdlib-style mock logger with all standard methods."""
    logger = Mock(spec=logging.Logger)
    logger.name = "test"
    return logger


@pytest.fixture()
def empty_args():
    """Return a bare SimpleNamespace with no attributes (triggers all defaults)."""
    return types.SimpleNamespace()


@pytest.fixture()
def full_disk_args():
    """Return a SimpleNamespace with every DiskProcessingConfig attribute set."""
    return types.SimpleNamespace(
        workdir="/tmp/work",
        skip_vmdk_inspection=True,
        vmdk_auto_fix_controller=True,
        flatten=True,
        flatten_format="raw",
        report="/tmp/report.json",
        dry_run=True,
        no_backup=True,
        print_fstab=True,
        no_grub=True,
        regen_initramfs=False,
        fstab_mode="passthrough",
        remove_vmware_tools=True,
        resize="20G",
        serial_console=False,
        initramfs_add_drivers=["virtio", "virtio_blk"],
        virtio_drivers_dir="/opt/virtio",
        luks_enable=True,
        luks_passphrase="secret",
        luks_passphrase_env="LUKS_PASS",
        luks_keyfile="/tmp/key",
        luks_mapper_prefix="test-crypt",
        backend="guestfish",
        container_isolation=True,
        conversion_dir="/tmp/conv",
        allowed_dirs=["/mnt", "/data"],
        cloud_init_config="/tmp/cloud.yaml",
        firstboot_scripts="/tmp/fb.sh",
        network_config_inject="/tmp/net.yaml",
        user_config_inject="/tmp/user.yaml",
        service_config_inject="/tmp/svc.yaml",
        hostname_config_inject="/tmp/host.yaml",
        root_password="rootpw",
        ssh_authorized_key="ssh-rsa AAAA",
        to_output="/tmp/out.qcow2",
        out_format="raw",
        compress=True,
        compress_level=9,
        checksum=True,
        cleanup_cache=False,
    )


@pytest.fixture()
def full_migration_args():
    """Return a SimpleNamespace with every MigrationConfig attribute set."""
    return types.SimpleNamespace(
        cmd="local",
        output_dir="/output",
        batch_manifest="/tmp/batch.yaml",
        enable_recovery=True,
        vs_action="export",
        parallel_processing=True,
        libvirt_test=True,
        qemu_test=True,
        vm_name="my-vm",
        memory=4096,
        vcpus=4,
        uefi=True,
        timeout=120,
        keep_domain=True,
        headless=True,
        health_check=True,
        health_check_timeout=300,
        deploy_k8s=True,
        k8s_continue_on_error=False,
        manifest_workflow_mode=True,
        manifest_workflow_dir="/tmp/mwf",
        workflow_mode=True,
        workflow_dir="/tmp/wf",
        watch_dir="/tmp/watch",
        dry_run=True,
        to_output="/tmp/out.qcow2",
        flatten=True,
    )


@pytest.fixture()
def minimal_migration_args():
    """Return a SimpleNamespace with only the mandatory MigrationConfig fields."""
    return types.SimpleNamespace()
