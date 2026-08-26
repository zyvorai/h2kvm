# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for network fixer backends (ifcfg, netplan, systemd-networkd, NM)."""

from __future__ import annotations

import logging
import textwrap

import pytest

from h2kvm.fixers.network.backend import NetworkFixersBackend
from h2kvm.fixers.network.model import FixLevel, FixResult, NetworkConfig, NetworkConfigType


def _make_backend(fix_level: FixLevel = FixLevel.MODERATE) -> NetworkFixersBackend:
    return NetworkFixersBackend(
        logger=logging.getLogger("test"),
        fix_level=fix_level,
        vmware_drivers={"vmxnet3": r"vmxnet3", "e1000e": r"e1000e"},
        mac_pinning_patterns=[],
    )


def _cfg(
    content: str,
    path: str = "/etc/sysconfig/network-scripts/ifcfg-ens192",
    cfg_type: NetworkConfigType = NetworkConfigType.IFCFG_RH,
) -> NetworkConfig:
    return NetworkConfig(path=path, content=textwrap.dedent(content), type=cfg_type)


# ── ifcfg-rh tests ─────────────────────────────────────────────────


class TestIfcfgRhVmwareNic:
    """Tests for VMware-specific NIC name handling in ifcfg files."""

    def test_vmware_device_commented_out(self):
        """DEVICE=ens192 should be commented out at MODERATE level."""
        backend = _make_backend()
        config = _cfg("""\
            TYPE=Ethernet
            DEVICE=ens192
            BOOTPROTO=dhcp
            ONBOOT=yes
        """)
        result = backend.fix_ifcfg_rh(config)
        assert "removed-vmware-nic-device-ens192" in result.applied_fixes
        # DEVICE= should be commented out (line starts with #), not active
        lines = result.new_content.splitlines()
        active_device_lines = [l for l in lines if l.strip().startswith("DEVICE=")]
        assert len(active_device_lines) == 0, f"DEVICE= still active: {active_device_lines}"
        assert any("# DEVICE=ens192" in l for l in lines)

    def test_vmware_name_set_to_migrated(self):
        """NAME should be set to 'Migrated (ens192)' after DEVICE removal."""
        backend = _make_backend()
        config = _cfg("""\
            TYPE=Ethernet
            DEVICE=ens192
            NAME=ens192
            BOOTPROTO=dhcp
            ONBOOT=yes
        """)
        result = backend.fix_ifcfg_rh(config)
        assert "Migrated (ens192)" in result.new_content

    def test_vmware_type_ethernet_added_if_missing(self):
        """TYPE=Ethernet should be added when missing and DEVICE is VMware."""
        backend = _make_backend()
        config = _cfg("""\
            DEVICE=ens192
            BOOTPROTO=dhcp
            ONBOOT=yes
        """)
        result = backend.fix_ifcfg_rh(config)
        assert "added-type-ethernet" in result.applied_fixes

    def test_normal_device_not_commented(self):
        """Non-VMware DEVICE names should NOT be commented out."""
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert not any("removed-vmware-nic-device" in f for f in result.applied_fixes)
        assert "DEVICE=eth0" in result.new_content

    def test_ens33_is_vmware(self):
        """ens33 should be detected as VMware-specific."""
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=ens33
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-ens33",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "removed-vmware-nic-device-ens33" in result.applied_fixes

    def test_ens3_is_not_vmware(self):
        """ens3 is a standard KVM NIC name, NOT VMware-specific."""
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=ens3
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-ens3",
        )
        result = backend.fix_ifcfg_rh(config)
        assert not any("removed-vmware-nic-device" in f for f in result.applied_fixes)


class TestIfcfgRhMacPinning:
    """Tests for MAC address pinning removal."""

    def test_hwaddr_removed(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            HWADDR=00:50:56:aa:bb:cc
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "removed-mac-pinning-hwaddr" in result.applied_fixes
        # HWADDR should be commented out, not active
        lines = result.new_content.splitlines()
        active_hwaddr = [l for l in lines if l.strip().startswith("HWADDR=")]
        assert len(active_hwaddr) == 0

    def test_mac_not_removed_at_conservative(self):
        backend = _make_backend(FixLevel.CONSERVATIVE)
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            HWADDR=00:50:56:aa:bb:cc
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert not any("removed-mac-pinning" in f for f in result.applied_fixes)


class TestIfcfgRhBootActivation:
    """Tests for ONBOOT, NM_CONTROLLED, UUID handling."""

    def test_onboot_no_becomes_yes(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            ONBOOT=no
            BOOTPROTO=dhcp
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "enabled-onboot" in result.applied_fixes
        assert "ONBOOT=yes" in result.new_content

    def test_missing_onboot_forced_for_vmware_nic(self):
        """Missing ONBOOT should be forced to yes for VMware-named NICs."""
        backend = _make_backend()
        config = _cfg("""\
            TYPE=Ethernet
            DEVICE=ens192
            BOOTPROTO=dhcp
        """)
        result = backend.fix_ifcfg_rh(config)
        assert "enabled-onboot" in result.applied_fixes

    def test_missing_onboot_not_forced_for_normal_nic(self):
        """Missing ONBOOT should NOT be forced for normal NICs."""
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            BOOTPROTO=dhcp
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "enabled-onboot" not in result.applied_fixes

    def test_nm_controlled_no_becomes_yes(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            BOOTPROTO=dhcp
            ONBOOT=yes
            NM_CONTROLLED=no
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "enabled-nm-controlled" in result.applied_fixes

    def test_uuid_removed(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            UUID=12345678-1234-1234-1234-123456789abc
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "removed-uuid" in result.applied_fixes


class TestIfcfgRhDhcpNormalization:
    """Tests for BOOTPROTO/DHCP normalization."""

    def test_missing_bootproto_gets_dhcp(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "added-bootproto-dhcp" in result.applied_fixes

    def test_bootproto_none_becomes_dhcp_for_ethernet(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            BOOTPROTO=none
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "normalized-bootproto-none->dhcp" in result.applied_fixes

    def test_static_config_not_changed_to_dhcp(self):
        """Interface with static IP should NOT get DHCP."""
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            BOOTPROTO=none
            IPADDR=10.0.0.1
            NETMASK=255.255.255.0
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert not any("dhcp" in f.lower() for f in result.applied_fixes)

    def test_bond_slave_no_dhcp(self):
        """Bond slave should NOT get DHCP added."""
        from h2kvm.fixers.network.model import TopoEdge, TopologyGraph

        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth1
            SLAVE=yes
            MASTER=bond0
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth1",
        )
        # Create topology with slave edge
        topo = TopologyGraph()
        topo.edges.append(TopoEdge(src="eth1", dst="bond0", kind="slave"))
        result = backend.fix_ifcfg_rh(config, topo=topo)
        assert not any("dhcp" in f.lower() for f in result.applied_fixes)

    def test_invalid_bootproto_normalized(self):
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            BOOTPROTO=vmware-custom
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert "normalized-bootproto->dhcp" in result.applied_fixes


class TestIfcfgRhAggressive:
    """Tests for AGGRESSIVE mode specific behavior."""

    def test_vmware_nic_skips_device_rename(self):
        """At AGGRESSIVE, VMware NIC should NOT get DEVICE renamed (it's commented out)."""
        backend = _make_backend(FixLevel.AGGRESSIVE)
        config = _cfg("""\
            TYPE=Ethernet
            DEVICE=ens192
            BOOTPROTO=dhcp
            ONBOOT=yes
        """)
        rename_map = {"ens192": "eth0"}
        result = backend.fix_ifcfg_rh(config, rename_map=rename_map)
        assert "removed-vmware-nic-device-ens192" in result.applied_fixes
        assert "renamed-device" not in result.applied_fixes


# ── Netplan tests ───────────────────────────────────────────────────


class TestNetplanVmwareNic:
    """Tests for VMware NIC name replacement in netplan."""

    def test_vmware_nic_replaced_with_match(self):
        backend = _make_backend()
        config = _cfg(
            """\
            network:
              version: 2
              ethernets:
                ens192:
                  dhcp4: true
        """,
            path="/etc/netplan/01-netcfg.yaml",
            cfg_type=NetworkConfigType.NETPLAN,
        )
        result = backend.fix_netplan(config)
        assert "eth-ens192-replaced-vmware-nic-name-with-match" in result.applied_fixes
        assert "ens192" not in result.new_content
        assert "en*" in result.new_content

    def test_non_vmware_nic_kept(self):
        backend = _make_backend()
        config = _cfg(
            """\
            network:
              version: 2
              ethernets:
                enp1s0:
                  dhcp4: true
        """,
            path="/etc/netplan/01-netcfg.yaml",
            cfg_type=NetworkConfigType.NETPLAN,
        )
        result = backend.fix_netplan(config)
        assert not any("replaced-vmware-nic" in f for f in result.applied_fixes)
        assert "enp1s0" in result.new_content

    def test_multi_vmware_nics_prefer_static(self):
        """When multiple VMware NICs exist, prefer the one with static config."""
        backend = _make_backend()
        config = _cfg(
            """\
            network:
              version: 2
              ethernets:
                ens160:
                  dhcp4: true
                ens192:
                  addresses:
                    - 10.0.0.1/24
                  gateway4: 10.0.0.254
        """,
            path="/etc/netplan/01-netcfg.yaml",
            cfg_type=NetworkConfigType.NETPLAN,
        )
        result = backend.fix_netplan(config)
        # ens192 (static) should be kept, ens160 (DHCP) should be merged
        assert "eth-ens192-replaced-vmware-nic-name-with-match" in result.applied_fixes
        assert "eth-ens160-merged-into-all-en" in result.applied_fixes
        assert "10.0.0.1/24" in result.new_content

    def test_mac_scrubbed(self):
        backend = _make_backend()
        config = _cfg(
            """\
            network:
              version: 2
              ethernets:
                enp1s0:
                  match:
                    macaddress: "00:50:56:aa:bb:cc"
                  dhcp4: true
        """,
            path="/etc/netplan/01-netcfg.yaml",
            cfg_type=NetworkConfigType.NETPLAN,
        )
        result = backend.fix_netplan(config)
        assert any("removed-match-mac" in f for f in result.applied_fixes)
        assert "00:50:56:aa:bb:cc" not in result.new_content


# ── systemd-networkd tests ──────────────────────────────────────────


class TestSystemdNetwork:
    """Tests for systemd-networkd .network file fixes."""

    def test_mac_match_removed(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [Match]
            MACAddress=00:50:56:aa:bb:cc

            [Network]
            DHCP=yes
        """,
            path="/etc/systemd/network/10-eth0.network",
            cfg_type=NetworkConfigType.SYSTEMD_NETWORK,
        )
        result = backend.fix_systemd_network(config)
        assert "removed-mac-match" in result.applied_fixes

    def test_vmware_name_replaced_with_wildcard(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [Match]
            Name=ens192

            [Network]
            DHCP=yes
        """,
            path="/etc/systemd/network/10-ens192.network",
            cfg_type=NetworkConfigType.SYSTEMD_NETWORK,
        )
        result = backend.fix_systemd_network(config)
        assert "replaced-networkd-vmware-match-name" in result.applied_fixes
        assert "en*" in result.new_content

    def test_non_vmware_name_kept(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [Match]
            Name=enp1s0

            [Network]
            DHCP=yes
        """,
            path="/etc/systemd/network/10-enp1s0.network",
            cfg_type=NetworkConfigType.SYSTEMD_NETWORK,
        )
        result = backend.fix_systemd_network(config)
        assert not any("replaced-networkd-vmware" in f for f in result.applied_fixes)
        assert "enp1s0" in result.new_content

    def test_dhcp_added_when_mac_removed_no_config(self):
        """DHCP=yes should be added when MAC was removed and no existing config."""
        backend = _make_backend()
        config = _cfg(
            """\
            [Match]
            MACAddress=00:50:56:aa:bb:cc

            [Network]
        """,
            path="/etc/systemd/network/10-eth0.network",
            cfg_type=NetworkConfigType.SYSTEMD_NETWORK,
        )
        result = backend.fix_systemd_network(config)
        assert "added-dhcp" in result.applied_fixes


# ── NetworkManager tests ────────────────────────────────────────────


class TestNetworkManager:
    """Tests for NetworkManager .nmconnection file fixes."""

    def test_mac_removed(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [connection]
            type=ethernet
            uuid=12345678-1234-1234-1234-123456789abc

            [ethernet]
            mac-address=00:50:56:AA:BB:CC
        """,
            path="/etc/NetworkManager/system-connections/ens192.nmconnection",
            cfg_type=NetworkConfigType.NETWORK_MANAGER,
        )
        result = backend.fix_network_manager(config)
        assert "removed-nm-mac" in result.applied_fixes

    def test_uuid_removed_for_ethernet(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [connection]
            type=ethernet
            uuid=12345678-1234-1234-1234-123456789abc

            [ethernet]
        """,
            path="/etc/NetworkManager/system-connections/eth0.nmconnection",
            cfg_type=NetworkConfigType.NETWORK_MANAGER,
        )
        result = backend.fix_network_manager(config)
        assert "removed-nm-uuid" in result.applied_fixes

    def test_uuid_not_removed_for_vpn(self):
        """UUID should NOT be removed from VPN profiles."""
        backend = _make_backend()
        config = _cfg(
            """\
            [connection]
            type=vpn
            uuid=12345678-1234-1234-1234-123456789abc

            [vpn]
            service-type=org.freedesktop.NetworkManager.openvpn
        """,
            path="/etc/NetworkManager/system-connections/vpn.nmconnection",
            cfg_type=NetworkConfigType.NETWORK_MANAGER,
        )
        result = backend.fix_network_manager(config)
        assert "removed-nm-uuid" not in result.applied_fixes

    def test_autoconnect_false_becomes_true(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [connection]
            type=ethernet
            autoconnect=false

            [ethernet]
        """,
            path="/etc/NetworkManager/system-connections/eth0.nmconnection",
            cfg_type=NetworkConfigType.NETWORK_MANAGER,
        )
        result = backend.fix_network_manager(config)
        assert "enabled-nm-autoconnect" in result.applied_fixes
        assert "autoconnect=true" in result.new_content

    def test_vmware_interface_name_removed(self):
        backend = _make_backend()
        config = _cfg(
            """\
            [connection]
            type=ethernet
            interface-name=ens192

            [ethernet]
        """,
            path="/etc/NetworkManager/system-connections/ens192.nmconnection",
            cfg_type=NetworkConfigType.NETWORK_MANAGER,
        )
        result = backend.fix_network_manager(config)
        assert "removed-nm-vmware-interface-name" in result.applied_fixes


# ── Validation tests ────────────────────────────────────────────────


class TestValidation:
    """Tests for network fix validation."""

    def test_missing_device_rejected(self):
        from h2kvm.fixers.network.validation import NetworkValidation

        validator = NetworkValidation(logging.getLogger("test"))
        errors = validator.validate_fix(
            original="DEVICE=eth0\nBOOTPROTO=dhcp\n",
            fixed="BOOTPROTO=dhcp\n",
            config_type=NetworkConfigType.IFCFG_RH,
        )
        assert any("ifcfg missing DEVICE" in e for e in errors)

    def test_device_commented_by_h2kvm_allowed(self):
        from h2kvm.fixers.network.validation import NetworkValidation

        validator = NetworkValidation(logging.getLogger("test"))
        fixed = (
            "# DEVICE=ens192  # VMware NIC name (vmware-ens-pattern) removed by h2kvm\nTYPE=Ethernet\n"
        )
        errors = validator.validate_fix(
            original="DEVICE=ens192\nTYPE=Ethernet\n",
            fixed=fixed,
            config_type=NetworkConfigType.IFCFG_RH,
        )
        assert not any("ifcfg missing DEVICE" in e for e in errors)


# ── Multi-NIC edge cases ───────────────────────────────────────────


class TestNetplanMultiNicEdgeCases:
    """Edge cases for multi-VMware-NIC merge in netplan."""

    def test_both_static_warns_on_dropped_config(self):
        """When both VMware NICs have static config, a warning should be emitted."""
        backend = _make_backend()
        config = _cfg(
            """\
            network:
              version: 2
              ethernets:
                ens160:
                  addresses:
                    - 10.0.0.1/24
                ens192:
                  addresses:
                    - 192.168.1.1/24
        """,
            path="/etc/netplan/01-netcfg.yaml",
            cfg_type=NetworkConfigType.NETPLAN,
        )
        result = backend.fix_netplan(config)
        # First static NIC (ens160) is kept, second (ens192) is dropped with warning
        assert "eth-ens160-replaced-vmware-nic-name-with-match" in result.applied_fixes
        assert "eth-ens192-merged-into-all-en" in result.applied_fixes
        assert any("Dropped static config" in w for w in result.warnings)
        assert "10.0.0.1/24" in result.new_content

    def test_neither_static_keeps_first(self):
        """When no VMware NIC has static config, first one is kept (safe for DHCP)."""
        backend = _make_backend()
        config = _cfg(
            """\
            network:
              version: 2
              ethernets:
                ens160:
                  dhcp4: true
                ens192:
                  dhcp4: true
        """,
            path="/etc/netplan/01-netcfg.yaml",
            cfg_type=NetworkConfigType.NETPLAN,
        )
        result = backend.fix_netplan(config)
        assert "eth-ens160-replaced-vmware-nic-name-with-match" in result.applied_fixes
        assert "eth-ens192-merged-into-all-en" in result.applied_fixes
        # No warning needed for DHCP-only drops
        assert not any("Dropped static config" in w for w in result.warnings)


# ── CONSERVATIVE level tests ────────────────────────────────────────


class TestConservativeLevel:
    """Confirm CONSERVATIVE level leaves most things untouched."""

    def test_vmware_device_not_commented(self):
        """CONSERVATIVE should NOT comment out VMware DEVICE names."""
        backend = _make_backend(FixLevel.CONSERVATIVE)
        config = _cfg("""\
            TYPE=Ethernet
            DEVICE=ens192
            HWADDR=00:50:56:aa:bb:cc
            BOOTPROTO=dhcp
            ONBOOT=no
            NM_CONTROLLED=no
            UUID=12345678-1234-1234-1234-123456789abc
        """)
        result = backend.fix_ifcfg_rh(config)
        # At CONSERVATIVE: no VMware NIC fix, no MAC removal, no ONBOOT/NM/UUID fix
        assert not any("removed-vmware-nic" in f for f in result.applied_fixes)
        assert not any("removed-mac-pinning" in f for f in result.applied_fixes)
        assert "enabled-onboot" not in result.applied_fixes
        assert "enabled-nm-controlled" not in result.applied_fixes
        assert "removed-uuid" not in result.applied_fixes
        # DEVICE should remain active
        lines = result.new_content.splitlines()
        assert any(l.strip().startswith("DEVICE=ens192") for l in lines)

    def test_ipv6_only_no_dhcp_injected(self):
        """IPv6-only ifcfg should NOT get IPv4 BOOTPROTO=dhcp."""
        backend = _make_backend()
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            IPV6INIT=yes
            IPV6_AUTOCONF=yes
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert not any("dhcp" in f.lower() for f in result.applied_fixes)

    def test_conservative_vmware_driver_tokens_still_cleaned(self):
        """CONSERVATIVE still removes VMware driver tokens (always-on fix)."""
        backend = _make_backend(FixLevel.CONSERVATIVE)
        config = _cfg(
            """\
            TYPE=Ethernet
            DEVICE=eth0
            DRIVER=vmxnet3
            BOOTPROTO=dhcp
            ONBOOT=yes
        """,
            path="/etc/sysconfig/network-scripts/ifcfg-eth0",
        )
        result = backend.fix_ifcfg_rh(config)
        assert any("removed-vmware-driver-token" in f for f in result.applied_fixes)
