# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Windows firstboot RDP and QEMU-GA script content."""

from h2kvm.fixers.windows.registry.firstboot import (
    _enhanced_virtio_driver_installation_cmd_block,
    _qemu_guest_agent_installation_cmd_block,
    _rdp_enablement_cmd_block,
)


def test_rdp_block_always_sets_registry_and_firewall():
    block = _rdp_enablement_cmd_block()
    assert "fDenyTSConnections" in block
    assert "Enable-NetFirewallRule" in block
    assert "remote desktop" in block.lower()


def test_rdp_block_starts_termservice():
    block = _rdp_enablement_cmd_block()
    assert "TermService" in block
    assert "UmRdpService" in block
    assert "Start-Service" in block
    assert "StartupType Automatic" in block


def test_rdp_block_cmd_fallback_without_powershell():
    block = _rdp_enablement_cmd_block()
    assert "sc config TermService start= auto" in block
    assert "net start TermService" in block


def test_qemu_guest_agent_block_installs_and_enables_service():
    block = _qemu_guest_agent_installation_cmd_block()
    assert r"%STAGE%\guest-agent\qemu-ga-x86_64.msi" in block
    assert "msiexec.exe" in block
    assert "Set-Service QEMU-GA -StartupType Automatic" in block
    assert "Start-Service QEMU-GA" in block


def test_enhanced_virtio_block_runs_staged_guest_tools_first():
    block = _enhanced_virtio_driver_installation_cmd_block()
    assert "virtio-win-guest-tools.exe" in block
    assert "/S','/norestart" in block
    assert "virtio-win-gt-x64.msi" in block
    assert "virtio-win-gt-x86.msi" in block
    assert "msiexec.exe" in block
    assert "Set-Service QEMU-GA -StartupType Automatic" in block
    assert "Start-Service QEMU-GA" in block


def test_rdp_block_omitted_when_include_rdp_false():
    from h2kvm.fixers.windows.registry.firstboot import (
        _firstboot_build_cmd_script,
        _firstboot_windows_paths,
    )

    script = _firstboot_build_cmd_script(
        service_name="h2kvm-firstboot",
        win=_firstboot_windows_paths("h2kvm-firstboot"),
        include_vmware_removal=False,
        include_rdp=False,
        extra_cmd=None,
    )
    assert "fDenyTSConnections" not in script
    assert "TermService" not in script
