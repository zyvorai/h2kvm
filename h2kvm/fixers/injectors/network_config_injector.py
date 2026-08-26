# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/network_config_injector.py
# pylint: disable=duplicate-code  # guestfs typing-stub fallback block is intentionally repeated per-module boilerplate, not shared logic worth extracting
"""
Network configuration injection for Linux VMs.

Allows injecting custom network configuration files for post-migration network
setup without cloud-init. Supports:
  - systemd-networkd (.network, .netdev files)
  - NetworkManager (.nmconnection files)

Use cases:
- Static IP configuration
- Bond/bridge/VLAN setup
- Custom DNS/gateway/routes
- Network device renaming
- Virtual network devices (bonds, bridges, VLANs, VXLANs, tunnels)
- NetworkManager connection profiles
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore  # pylint: disable=invalid-name,too-few-public-methods  # matches real guestfs module name for type-hint purposes; stub has no methods
            """Typing-only stand-in for the optional ``guestfs`` module."""

            class GuestFS(Protocol):  # pylint: disable=too-few-public-methods  # typing stub, no real methods needed
                """Typing-only stand-in for the ``guestfs.GuestFS`` handle type."""


def inject_network_config(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    # covers systemd-networkd + NetworkManager injection with many independent validation/write steps
    self,
    g: guestfs.GuestFS,
) -> dict[str, Any]:
    """
    Inject network configuration files (systemd-networkd and/or NetworkManager).

    Expected payload (self.network_config_inject):
      {
        # Systemd-networkd files
        "network_files": [
          {
            "name": "eth0",  # Creates /etc/systemd/network/10-eth0.network
            "type": "network",  # "network" or "netdev"
            "priority": 10,  # Optional, default 50
            "content": '''
              [Match]
              Name=eth0

              [Network]
              Address=192.168.1.100/24
              Gateway=192.168.1.1
              DNS=8.8.8.8
            '''
          },
          {
            "name": "br0",
            "type": "netdev",
            "priority": 10,
            "content": '''
              [NetDev]
              Name=br0
              Kind=bridge
            '''
          }
        ],

        # NetworkManager connection profiles
        "nm_connections": [
          {
            "name": "eth0",  # Creates /etc/NetworkManager/system-connections/eth0.nmconnection
            "content": '''
              [connection]
              id=eth0
              type=ethernet
              interface-name=eth0

              [ipv4]
              method=manual
              address1=192.168.1.100/24,192.168.1.1
              dns=8.8.8.8;8.8.4.4;
            '''
          }
        ],

        # Optional: enable systemd-networkd service
        "enable_networkd": true,

        # Optional: enable NetworkManager service
        "enable_network_manager": true
      }
    """
    logger = getattr(self, "logger", None)

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    _log("debug", "🌐 network-config: inject_network_config(): enter")

    # Get configuration
    config = getattr(self, "network_config_inject", None)
    if config is None:
        _log("debug", "🌐 network-config: no network_config_inject set; skipping")
        return {"injected": False, "reason": "no_config"}

    if not isinstance(config, dict):
        _log("warning", f"🌐 network-config: network_config_inject is not a dict: {type(config).__name__}")
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    _log("debug", f"🌐 network-config: dry_run={dry}")

    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "files_created": [],
        "service_enabled": False,
    }

    # Handle network files
    network_files = config.get("network_files", [])
    nm_connections = config.get("nm_connections", [])

    # Check if there's anything to inject
    if not network_files and not nm_connections:
        _log("warning", "🌐 network-config: no network_files or nm_connections provided")
        return {"injected": False, "reason": "no_files"}

    # Process systemd-networkd files if any
    networkd_dir = "/etc/systemd/network"
    if network_files:
        # Create directory if needed
        if not dry:
            try:
                if not g.is_dir(networkd_dir):
                    g.mkdir_p(networkd_dir)
                    _log("debug", f"📁 Created directory: {networkd_dir}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs mkdir_p can raise various backend errors; abort cleanly
                _log("error", f"Failed to create networkd directory: {e}")
                return {"injected": False, "reason": "mkdir_failed", "error": str(e)}

        for idx, file_config in enumerate(network_files):
            name = file_config.get("name")
            file_type = file_config.get("type", "network")
            priority = file_config.get("priority", 50)
            content = file_config.get("content", "")

            if not name:
                _log("warning", f"🌐 network-config: file #{idx} has no name, skipping")
                continue

            if not content:
                _log("warning", f"🌐 network-config: file '{name}' has no content, skipping")
                continue

            if file_type not in ("network", "netdev"):
                _log("warning", f"🌐 network-config: file '{name}' has invalid type '{file_type}', skipping")
                continue

            # Build filename: priority-name.type
            filename = f"{priority:02d}-{name}.{file_type}"
            filepath = f"{networkd_dir}/{filename}"

            # Ensure content is properly formatted
            content = content.strip() + "\n"

            if dry:
                _log("info", f"DRY-RUN: would write {file_type} config: {filepath}")
                results["files_created"].append(
                    {"path": filepath, "bytes": len(content.encode("utf-8")), "type": file_type}
                )
            else:
                try:
                    g.write(filepath, content.encode("utf-8"))
                    _log("info", f"Wrote {file_type} config: {filepath}")
                    results["files_created"].append(
                        {"path": filepath, "bytes": len(content.encode("utf-8")), "type": file_type}
                    )
                except Exception as e:
                    _log("error", f"Failed to write {file_type} config {filepath}: {e}")
                    raise

    # Handle NetworkManager connection files (already retrieved above)
    if nm_connections:
        nm_dir = "/etc/NetworkManager/system-connections"

        # Create directory if needed
        if not dry:
            try:
                if not g.is_dir(nm_dir):
                    g.mkdir_p(nm_dir)
                    _log("debug", f"📁 Created directory: {nm_dir}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs mkdir_p can raise various backend errors; abort cleanly
                _log("error", f"Failed to create NetworkManager directory: {e}")
                return {"injected": False, "reason": "mkdir_nm_failed", "error": str(e)}

        for idx, conn_config in enumerate(nm_connections):
            name = conn_config.get("name")
            content = conn_config.get("content", "")

            if not name:
                _log("warning", f"🌐 network-config: NM connection #{idx} has no name, skipping")
                continue

            if not content:
                _log("warning", f"🌐 network-config: NM connection '{name}' has no content, skipping")
                continue

            # Build filename: name.nmconnection
            filename = f"{name}.nmconnection"
            filepath = f"{nm_dir}/{filename}"

            # Ensure content is properly formatted
            content = content.strip() + "\n"

            if dry:
                _log("info", f"DRY-RUN: would write NM connection: {filepath}")
                results["files_created"].append(
                    {"path": filepath, "bytes": len(content.encode("utf-8")), "type": "nmconnection"}
                )
            else:
                try:
                    g.write(filepath, content.encode("utf-8"))
                    # NetworkManager connections need 0600 permissions
                    try:
                        g.chmod(0o600, filepath)
                    except Exception:  # pylint: disable=broad-exception-caught  # not all guestfs versions support chmod; best-effort permission tightening
                        pass  # Not all guestfs versions support chmod
                    _log("info", f"Wrote NM connection: {filepath}")
                    results["files_created"].append(
                        {"path": filepath, "bytes": len(content.encode("utf-8")), "type": "nmconnection"}
                    )
                except Exception as e:
                    _log("error", f"Failed to write NM connection {filepath}: {e}")
                    raise

    if not results["files_created"]:
        _log("warning", "🌐 network-config: no valid files to write")
        return {"injected": False, "reason": "no_valid_files"}

    # Enable systemd-networkd if requested
    services_enabled = []
    if config.get("enable_networkd", False) and not dry:
        if _enable_service(g, logger, "systemd-networkd.service"):
            services_enabled.append("systemd-networkd")

    # Enable NetworkManager if requested
    if config.get("enable_network_manager", False) and not dry:
        if _enable_service(g, logger, "NetworkManager.service"):
            services_enabled.append("NetworkManager")

    results["services_enabled"] = services_enabled
    _log(
        "info",
        f"🌐 network-config: injection complete; files={len(results['files_created'])}, services={services_enabled}",
    )
    return results


def _enable_service(g: guestfs.GuestFS, logger: Any, service_name: str) -> bool:
    """Enable a systemd service by creating symlink in multi-user.target.wants"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        wants_dir = "/etc/systemd/system/multi-user.target.wants"

        # Try multiple possible service file locations
        service_paths = [
            f"/usr/lib/systemd/system/{service_name}",
            f"/lib/systemd/system/{service_name}",
            f"/etc/systemd/system/{service_name}",
        ]

        service_file = None
        for path in service_paths:
            if g.exists(path):
                service_file = path
                break

        if not service_file:
            _log("warning", f"{service_name} not found in guest")
            return False

        # Ensure wants directory exists
        if not g.is_dir(wants_dir):
            g.mkdir_p(wants_dir)

        # Create symlink if it doesn't exist
        symlink_path = f"{wants_dir}/{service_name}"
        if not g.exists(symlink_path):
            g.ln_sf(service_file, symlink_path)
            _log("info", f"Enabled {service_name}")
        else:
            _log("debug", f"{service_name} already enabled")

        return True
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort service enablement, must not abort the whole injection
        _log("warning", f"Failed to enable {service_name}: {e}")
        return False
