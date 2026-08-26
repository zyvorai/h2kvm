# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Inspection Operations.

Provides OS inspection and detection methods for VMCraft via composition.
Merges InspectionMixin + EnhancedInspectionExtMixin.
"""

from __future__ import annotations

from typing import Any

from hyper2kvm.vmcraft._utils import run_sudo
from hyper2kvm.vmcraft.services import (
    get_cached_inspection_value,
    inspect_get_mountpoints as svc_inspect_get_mountpoints,
    inspect_os as svc_inspect_os,
    parse_fstab as svc_parse_fstab,
)


class InspectionOps:  # pylint: disable=too-many-public-methods,protected-access
    """
    Inspection operations via composition.

    This is a thin delegation facade: methods forward to attributes/managers
    on ``_host`` (the composed VMCraft instance), including via
    ``_host._enhanced_inspector_call``. `_host` is part of the same object
    graph as this component, so the protected-access is intentional tight
    internal coupling rather than reaching into an unrelated class. The
    large method count mirrors the many independent inspection getters
    VMCraft exposes (OS type/distro/version/arch, network, etc.).
    """

    def __init__(self, host) -> None:
        self._host = host

    # === Core Inspection (from InspectionMixin) ===

    def inspect_os(self) -> list[str]:
        """Detect operating systems on disk."""
        os_inspector = self._host._require_os_inspector()
        partitions = self._host.list_partitions()
        return svc_inspect_os(os_inspector, partitions)

    def inspect_get_type(self, root: str) -> str:
        """Get OS type (linux, windows, etc.)."""
        return get_cached_inspection_value(self._host._os_inspector, root, "type", "unknown")

    def inspect_get_distro(self, root: str) -> str:
        """Get distribution name."""
        return get_cached_inspection_value(self._host._os_inspector, root, "distro", "unknown")

    def inspect_get_product_name(self, root: str) -> str:
        """Get product name."""
        return get_cached_inspection_value(self._host._os_inspector, root, "product", "Unknown")

    def inspect_get_major_version(self, root: str) -> int:
        """Get major version number."""
        return get_cached_inspection_value(self._host._os_inspector, root, "major", 0)

    def inspect_get_minor_version(self, root: str) -> int:
        """Get minor version number."""
        return get_cached_inspection_value(self._host._os_inspector, root, "minor", 0)

    def inspect_get_arch(self, root: str) -> str:
        """Get architecture."""
        return get_cached_inspection_value(self._host._os_inspector, root, "arch", "unknown")

    def inspect_get_mountpoints(self, root: str) -> dict[str, str] | list[tuple[str, str]]:
        """Get mountpoints for root."""
        return svc_inspect_get_mountpoints(
            root=root,
            os_type=self._host.inspect_get_type(root),
            return_dict=self._host._return_dict,
            parse_fstab_fn=self._parse_fstab,
        )

    def _parse_fstab(self, root: str) -> list[tuple[str, str]]:
        """Parse /etc/fstab from root device."""
        return svc_parse_fstab(
            logger=self._host.logger,
            mount_root=self._host._mount_root,
            file_ops=self._host._file_ops,
            root=root,
            run_sudo=run_sudo,
            umount_all_fn=self._host.umount_all,
        )

    # === Enhanced Inspection (from EnhancedInspectionExtMixin) ===

    def inspect_network_config(self) -> list[dict[str, Any]]:
        """
        Inspect network configuration from multiple formats.

        Supports Debian, RHEL, netplan, NetworkManager, systemd-networkd.

        Returns:
            List of network interface configurations

        Example:
            interfaces = g.inspect_network_config()
            for iface in interfaces:
                print(f"{iface['name']}: {iface['ip_address']} (DHCP: {iface['dhcp']})")
                if iface['dns_servers']:
                    print(f"  DNS: {iface['dns_servers']}")
        """
        interfaces = self._host._enhanced_inspector_call("inspect_network")
        # Convert NetworkInterface objects to dicts
        return [
            {
                "name": iface.name,
                "ip_address": iface.ip_address,
                "mac_address": iface.mac_address,
                "dhcp": iface.dhcp,
                "dns_servers": iface.dns_servers,
            }
            for iface in interfaces
        ]

    def inspect_dns_config(self) -> list[str]:
        """
        Get DNS server configuration.

        Returns:
            List of DNS server IP addresses

        Example:
            dns_servers = g.inspect_dns_config()
            print(f"DNS servers: {dns_servers}")
        """
        return self._host._enhanced_inspector_call("inspect_dns")

    def inspect_user_accounts(self) -> list[dict[str, str]]:
        """
        List all user accounts from /etc/passwd.

        Returns:
            List of user account information

        Example:
            users = g.inspect_user_accounts()
            for user in users:
                print(f"{user['username']} (UID: {user['uid']}, Home: {user['home']})")
        """
        users = self._host._enhanced_inspector_call("inspect_users")
        return [
            {
                "username": user.username,
                "uid": user.uid,
                "gid": user.gid,
                "home": user.home,
                "shell": user.shell,
            }
            for user in users
        ]

    def inspect_ssh_configuration(self) -> dict[str, str]:
        """
        Parse SSH server configuration.

        Returns:
            Dict of SSH configuration settings

        Example:
            ssh_config = g.inspect_ssh_configuration()
            print(f"Port: {ssh_config.get('Port', '22')}")
            print(f"PermitRootLogin: {ssh_config.get('PermitRootLogin', 'no')}")
        """
        return self._host._enhanced_inspector_call("inspect_ssh_config")

    def inspect_selinux_status(self) -> str:
        """
        Check SELinux status.

        Returns:
            SELinux mode: enforcing, permissive, disabled, or unknown

        Example:
            selinux = g.inspect_selinux_status()
            print(f"SELinux: {selinux}")
        """
        return self._host._enhanced_inspector_call("inspect_selinux")

    def inspect_apparmor_status(self) -> bool:
        """
        Check if AppArmor is enabled.

        Returns:
            True if AppArmor is present/enabled

        Example:
            apparmor = g.inspect_apparmor_status()
            print(f"AppArmor enabled: {apparmor}")
        """
        return self._host._enhanced_inspector_call("inspect_apparmor")

    def inspect_installed_runtimes(self) -> dict[str, str]:
        """
        Detect installed language runtimes.

        Checks for: Python, Node.js, Ruby, Java, Go, Perl, PHP, Rust

        Returns:
            Dict mapping runtime name to installation status

        Example:
            runtimes = g.inspect_installed_runtimes()
            for name, status in runtimes.items():
                print(f"{name}: {status}")
        """
        return self._host._enhanced_inspector_call("inspect_runtimes")

    def inspect_installed_container_runtimes(self) -> list[str]:
        """
        Detect installed container runtimes.

        Checks for: Docker, Podman, containerd, CRI-O, LXC, LXD

        Returns:
            List of detected container runtime names

        Example:
            runtimes = g.inspect_installed_container_runtimes()
            print(f"Container runtimes: {runtimes}")
        """
        return self._host._enhanced_inspector_call("inspect_container_runtimes")

    def inspect_cron_jobs(self) -> list[str]:
        """
        List cron jobs from system crontab and cron directories.

        Returns:
            List of cron job descriptions

        Example:
            cron_jobs = g.inspect_cron_jobs()
            for job in cron_jobs:
                print(f"Cron: {job}")
        """
        return self._host._enhanced_inspector_call("inspect_cron")

    def inspect_systemd_timer_units(self) -> list[str]:
        """
        List systemd timer units.

        Returns:
            List of enabled systemd timer unit names

        Example:
            timers = g.inspect_systemd_timer_units()
            for timer in timers:
                print(f"Timer: {timer}")
        """
        return self._host._enhanced_inspector_call("inspect_systemd_timers")

    def inspect_guest_tools(self) -> list[str]:
        """
        Detect installed virtualization guest tools.

        Checks for: VMware Tools, QEMU Guest Agent, VirtualBox Guest Additions,
                    Hyper-V integration services, Xen tools

        Returns:
            List of detected guest tool names

        Example:
            tools = g.inspect_guest_tools()
            print(f"Guest tools installed: {tools}")
        """
        return self._host._enhanced_inspector_call("inspect_vm_tools")

    def inspect_system_timezone(self) -> str:
        """
        Get system timezone.

        Returns:
            Timezone string (e.g., "America/New_York") or "unknown"

        Example:
            timezone = g.inspect_system_timezone()
            print(f"Timezone: {timezone}")
        """
        return self._host._enhanced_inspector_call("inspect_timezone")

    def inspect_system_locale(self) -> str:
        """
        Get system locale.

        Returns:
            Locale string (e.g., "en_US.UTF-8") or "unknown"

        Example:
            locale = g.inspect_system_locale()
            print(f"Locale: {locale}")
        """
        return self._host._enhanced_inspector_call("inspect_locale")

    def inspect_kernel_parameters(self) -> dict[str, str]:
        """
        Get kernel sysctl parameters from /etc/sysctl.conf.

        Returns:
            Dict of kernel parameter key-value pairs

        Example:
            params = g.inspect_kernel_parameters()
            for key, value in params.items():
                print(f"{key} = {value}")
        """
        return self._host._enhanced_inspector_call("inspect_kernel_params")

    def inspect_swap_devices(self) -> list[str]:
        """
        Get swap devices from /etc/fstab.

        Returns:
            List of swap device paths

        Example:
            swap_devices = g.inspect_swap_devices()
            print(f"Swap devices: {swap_devices}")
        """
        return self._host._enhanced_inspector_call("inspect_swap")

    def inspect_fstab_entries(self) -> list[dict[str, Any]]:
        """
        Parse /etc/fstab into structured format.

        Returns:
            List of fstab entries with device, mountpoint, fstype, options, dump, pass

        Example:
            fstab = g.inspect_fstab_entries()
            for entry in fstab:
                print(f"{entry['device']} on {entry['mountpoint']} type {entry['fstype']}")
        """
        entries = self._host._enhanced_inspector_call("inspect_fstab")
        return [
            {
                "device": entry.device,
                "mountpoint": entry.mountpoint,
                "fstype": entry.fstype,
                "options": entry.options,
                "dump": entry.dump,
                "pass": entry.pass_num,
            }
            for entry in entries
        ]

    def inspect_cloud_init_installed(self) -> bool:
        """
        Detect if cloud-init is installed.

        Returns:
            True if cloud-init is present

        Example:
            has_cloud_init = g.inspect_cloud_init_installed()
            print(f"Cloud-init installed: {has_cloud_init}")
        """
        return self._host._enhanced_inspector_call("inspect_cloud_init")

    def inspect_ssl_certificates(self) -> list[dict[str, str]]:
        """
        List SSL certificates in common locations.

        Returns:
            List of dicts with certificate paths and types

        Example:
            certs = g.inspect_ssl_certificates()
            for cert in certs:
                print(f"{cert['type']}: {cert['path']}")
        """
        return self._host._enhanced_inspector_call("inspect_certificates")
