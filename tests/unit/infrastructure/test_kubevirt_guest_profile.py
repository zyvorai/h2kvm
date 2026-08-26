# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""kubevirt_guest_profile unit tests."""

from h2kvm.infrastructure.deployers.kubevirt_guest_profile import (
    kubevirt_os_variant,
    kubevirt_os_variant_from_name,
)


def test_rhel10_variant():
    assert kubevirt_os_variant(distro_id="rhel", version_id="10.0") == "rhel10.0"


def test_ubuntu24_variant():
    assert kubevirt_os_variant(distro_id="ubuntu", version_id="24.04") == "ubuntu24.04"


def test_name_heuristic_u2204():
    assert kubevirt_os_variant_from_name("my-u2204-vm") == "ubuntu22.04"
