# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Cloud-init injection for VM configuration."""

import tempfile
from pathlib import Path

import yaml


def create_cloud_init_config(
    *,
    hostname: str | None = None,
    users: list[str] | None = None,
    ssh_authorized_keys: list[str] | None = None,
    packages: list[str] | None = None,
    runcmd: list[str] | None = None,
) -> Path:
    """
    Create cloud-init user-data configuration.

    Args:
        hostname: VM hostname
        users: List of usernames
        ssh_authorized_keys: List of SSH public keys
        packages: Packages to install
        runcmd: Commands to run

    Returns:
        Path to cloud-init config file

    Example:
        >>> config = create_cloud_init_config(
        ...     hostname="test-vm",
        ...     users=["admin"],
        ...     ssh_authorized_keys=["ssh-rsa AAAAB3..."],
        ...     packages=["vim", "curl"],
        ...     runcmd=["echo 'VM ready' > /tmp/ready"],
        ... )
    """
    config = {}

    if hostname:
        config["hostname"] = hostname

    if users:
        config["users"] = users

    if ssh_authorized_keys:
        config["ssh_authorized_keys"] = ssh_authorized_keys

    if packages:
        config["packages"] = packages

    if runcmd:
        config["runcmd"] = runcmd

    user_data = "#cloud-config\n" + yaml.dump(config, default_flow_style=False)

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, prefix="cloud-init-") as tmp:
        tmp.write(user_data)
        tmp.flush()
        tmp_name = tmp.name

    return Path(tmp_name)


def create_network_config(
    *,
    static_ip: str | None = None,
    gateway: str | None = None,
    dns: list[str] | None = None,
) -> Path:
    """
    Create cloud-init network configuration.

    Args:
        static_ip: Static IP address (e.g., "192.168.1.100/24")
        gateway: Gateway IP
        dns: List of DNS servers

    Returns:
        Path to network config file
    """
    config = {"version": 2, "ethernets": {"eth0": {}}}

    if static_ip:
        config["ethernets"]["eth0"]["addresses"] = [static_ip]

    if gateway:
        config["ethernets"]["eth0"]["gateway4"] = gateway

    if dns:
        config["ethernets"]["eth0"]["nameservers"] = {"addresses": dns}

    network_config = yaml.dump(config, default_flow_style=False)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, prefix="network-config-"
    ) as tmp:
        tmp.write(network_config)
        tmp.flush()
        tmp_name = tmp.name

    return Path(tmp_name)
