# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for OpenStack deployer (dry-run and missing SDK)."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from h2kvm.infrastructure.deployers.openstack import OpenStackDeployer, deploy_to_openstack


def test_dry_run_skips_connection(tmp_path):
    img = tmp_path / "vm.qcow2"
    img.write_bytes(b"fake")
    logger = MagicMock()
    args = argparse.Namespace(
        glance_name="test-image",
        dry_run=True,
        vm_name=None,
    )
    result = deploy_to_openstack(logger, args, str(img))
    assert result["dry_run"] is True
    assert result["glance_name"] == "test-image"


def test_missing_image_raises(tmp_path):
    logger = MagicMock()
    args = argparse.Namespace(glance_name="x", dry_run=False, vm_name=None)
    deployer = OpenStackDeployer(logger, args)
    from h2kvm.core.exceptions import InfrastructureError

    with pytest.raises(InfrastructureError, match="not found"):
        deployer.deploy(str(tmp_path / "missing.qcow2"))


def test_boot_instance_requires_flavor_network_key(tmp_path):
    img = tmp_path / "vm.qcow2"
    img.write_bytes(b"fake")
    logger = MagicMock()
    args = argparse.Namespace(
        glance_name="img",
        dry_run=False,
        vm_name=None,
        openstack_boot_instance=True,
        openstack_flavor=None,
        openstack_network="net-1",
        openstack_key_name="kp",
    )
    deployer = OpenStackDeployer(logger, args)
    from h2kvm.core.exceptions import InfrastructureError

    with pytest.raises(InfrastructureError, match="flavor"):
        deployer.deploy(str(img))
