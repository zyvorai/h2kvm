# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Linux Operations.

Provides Linux-specific operations for VMCraft via composition.
Includes service management and cache management.
"""

# Every method here delegates through the host's _dispatch_manager_attr_call() by design —
# this is the composition mixin pattern used throughout h2kvm.vmcraft.api (see
# augeas_ops.py, analyzer_ops.py, etc.): tight, intentional coupling to the host object.
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any


class LinuxOps:
    """Linux operations via composition."""

    def __init__(self, host) -> None:
        self._host = host

    # Linux Service Management

    def linux_list_services(self) -> list[dict[str, Any]]:
        """List all systemd service units."""
        return self._host._dispatch_manager_attr_call("_linux_services", "list_services")

    def linux_get_service_info(self, service_name: str) -> dict[str, Any] | None:
        """Get detailed information about a systemd service."""
        return self._host._dispatch_manager_attr_call("_linux_services", "get_service_info", service_name)

    def linux_list_enabled_services(self) -> list[str]:
        """List all enabled systemd services."""
        return self._host._dispatch_manager_attr_call("_linux_services", "list_enabled_services")

    def linux_list_disabled_services(self) -> list[str]:
        """List all disabled systemd services."""
        return self._host._dispatch_manager_attr_call("_linux_services", "list_disabled_services")

    def linux_get_service_dependencies(self, service_name: str) -> dict[str, Any]:
        """Get systemd service dependencies."""
        return self._host._dispatch_manager_attr_call(
            "_linux_services", "get_service_dependencies", service_name
        )

    def linux_find_services_by_target(self, target: str = "multi-user.target") -> list[str]:
        """Find services enabled for a specific systemd target."""
        return self._host._dispatch_manager_attr_call("_linux_services", "find_services_by_target", target)

    def linux_get_boot_services(self) -> list[str]:
        """Get services that start at boot."""
        return self._host._dispatch_manager_attr_call("_linux_services", "get_boot_services")

    def linux_get_service_stats(self) -> dict[str, int]:
        """Get systemd service statistics."""
        return self._host._dispatch_manager_attr_call("_linux_services", "get_service_stats")

    # Cache Management

    def get_cache_stats(self) -> dict[str, Any]:
        """Get file operation cache statistics."""
        return self._host._dispatch_manager_attr_call("_file_ops", "get_cache_stats")

    def clear_cache(self) -> None:
        """Clear file operation caches."""
        self._host._dispatch_manager_attr_call("_file_ops", "clear_cache")
