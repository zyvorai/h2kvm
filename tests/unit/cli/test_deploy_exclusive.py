# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for deploy target mutual exclusion validation."""

from __future__ import annotations

import argparse

import pytest

from h2kvm.cli.args.validators import validate_deploy_exclusive


def test_k8s_and_openstack_rejected():
    args = argparse.Namespace(
        deploy_k8s=True,
        deploy_openstack=True,
        emit_domain_xml=False,
        virsh_define=False,
        libvirt_test=False,
    )
    with pytest.raises(SystemExit, match="mutually exclusive"):
        validate_deploy_exclusive(args, {})


def test_openstack_and_libvirt_rejected():
    args = argparse.Namespace(
        deploy_openstack=True,
        deploy_k8s=False,
        emit_domain_xml=True,
        virsh_define=False,
        libvirt_test=False,
    )
    with pytest.raises(SystemExit, match="deploy_openstack cannot be combined"):
        validate_deploy_exclusive(args, {})


def test_openstack_from_yaml_conf():
    args = argparse.Namespace(
        deploy_openstack=False,
        deploy_k8s=False,
        emit_domain_xml=False,
        virsh_define=False,
        libvirt_test=True,
    )
    with pytest.raises(SystemExit, match="deploy_openstack cannot be combined"):
        validate_deploy_exclusive(args, {"deploy_openstack": True})


def test_openstack_only_ok():
    args = argparse.Namespace(
        deploy_openstack=True,
        deploy_k8s=False,
        emit_domain_xml=False,
        virsh_define=False,
        libvirt_test=False,
    )
    validate_deploy_exclusive(args, {})
