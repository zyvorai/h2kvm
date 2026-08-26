# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""KubeVirt VirtualMachine manifest helpers (guest OS hints for v9s)."""

from types import SimpleNamespace

from hyper2kvm.infrastructure.deployers.kubevirt_guest_profile import (
    LINUX_SSH_PORT,
    WINDOWS_RDP_PORT,
    build_kubevirt_vm_manifest,
    is_windows_guest,
    kubevirt_os_variant,
    parse_os_release,
    propagate_linux_metadata_from_report,
    resolve_guest_profile,
)


def test_is_windows_guest_from_guest_os():
    args = SimpleNamespace(guest_os="windows", windows=False)
    assert is_windows_guest(args) is True


def test_linux_guest_from_guest_os():
    args = SimpleNamespace(guest_os="linux", windows=False)
    profile = resolve_guest_profile(args, vm_name="rhel88-migrated")
    assert profile.family == "linux"


def test_windows_manifest_has_v9s_labels_and_rdp_port():
    args = SimpleNamespace(guest_os="windows", windows=True, uefi=True)
    vm = build_kubevirt_vm_manifest(
        vm_name="2025legacy-67790c6f",
        namespace="default",
        run_strategy="Always",
        volume={"name": "rootdisk", "persistentVolumeClaim": {"claimName": "disk"}},
        root_disk_bus="sata",
        memory="8Gi",
        cpu_cores="4",
        args=args,
    )

    labels = vm["metadata"]["labels"]
    assert labels["v9s.io/guest-os"] == "windows"
    assert labels["v9s.io/rdp"] == "enabled"

    domain = vm["spec"]["template"]["spec"]["domain"]
    assert "os" not in domain
    assert domain["cpu"]["cores"] == 4
    assert "video" not in domain["devices"]
    assert domain["devices"]["autoattachGraphicsDevice"] is True
    ports = domain["devices"]["interfaces"][0]["ports"]
    assert ports[0]["port"] == WINDOWS_RDP_PORT
    assert domain["firmware"]["bootloader"]["efi"]["secureBoot"] is False


def test_windows_uefi_secure_boot_enables_smm():
    args = SimpleNamespace(guest_os="windows", windows=True, uefi=True, win_secure_boot=True)
    vm = build_kubevirt_vm_manifest(
        vm_name="win11-migrated",
        namespace="default",
        run_strategy="Halted",
        volume={"name": "rootdisk", "persistentVolumeClaim": {"claimName": "disk"}},
        root_disk_bus="sata",
        memory="8Gi",
        cpu_cores="2",
        args=args,
    )
    domain = vm["spec"]["template"]["spec"]["domain"]
    assert domain["firmware"]["bootloader"]["efi"]["secureBoot"] is True
    assert domain["features"]["smm"]["enabled"] is True


def test_rhel88_linux_manifest_from_os_release():
    os_release = """
ID=rhel
VERSION_ID="8.10"
PRETTY_NAME="Red Hat Enterprise Linux 8.10 (Ootpa)"
ID_LIKE="centos fedora"
"""
    args = SimpleNamespace(guest_os="linux", windows=False, uefi=False)
    propagate_linux_metadata_from_report(
        args,
        {"analysis": {"guest": {"os_release": os_release}}},
    )

    vm = build_kubevirt_vm_manifest(
        vm_name="rhel88-migrated",
        namespace="default",
        run_strategy="Halted",
        volume={"name": "rootdisk", "persistentVolumeClaim": {"claimName": "pvc"}},
        root_disk_bus="virtio",
        memory="4Gi",
        cpu_cores="2",
        args=args,
    )

    labels = vm["metadata"]["labels"]
    assert labels["v9s.io/guest-os"] == "linux"
    assert labels["os.template.kubevirt.io/variant"] == "rhel8.10"
    assert labels["hyper2kvm.io/os-distro"] == "rhel"
    assert labels["hyper2kvm.io/os-version"] == "8.10"

    domain = vm["spec"]["template"]["spec"]["domain"]
    assert "os" not in domain
    assert domain["cpu"]["cores"] == 2
    assert domain["devices"]["rng"] == {}
    ports = domain["devices"]["interfaces"][0]["ports"]
    assert ports[0]["port"] == LINUX_SSH_PORT


def test_ubuntu2204_variant_mapping():
    assert kubevirt_os_variant(distro_id="ubuntu", version_id="22.04") == "ubuntu22.04"


def test_rocky9_variant_mapping():
    assert kubevirt_os_variant(distro_id="rocky", version_id="9.4") == "rocky9.4"


def test_variant_from_vm_name_rhel88():
    args = SimpleNamespace(guest_os="linux", windows=False, uefi=False)
    profile = resolve_guest_profile(args, vm_name="esx8.0-rhel8.8-with-thin-provision")
    assert profile.os_variant == "rhel8.8"


def test_parse_os_release():
    parsed = parse_os_release('ID="ubuntu"\nVERSION_ID="24.04"\n')
    assert parsed["ID"] == "ubuntu"
    assert parsed["VERSION_ID"] == "24.04"
