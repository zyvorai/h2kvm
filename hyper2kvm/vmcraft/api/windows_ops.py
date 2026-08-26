# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows Operations.

Provides Windows-specific operations for VMCraft via composition.
Merges WindowsOpsMixin + win_* methods from StorageMixin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# pylint: disable=protected-access
# Every method below deliberately forwards to the host's internal manager
# dispatcher; WindowsOps is a same-package composition facade over the host,
# not an unrelated client reaching into its internals.


class WindowsOps:  # pylint: disable=too-many-public-methods
    # This is a thin composition facade: each win_* method is a one-line forward
    # to the host's internal manager dispatch, one per Windows subsystem it exposes.
    """Windows operations via composition."""

    def __init__(self, host) -> None:
        self._host = host

    # === Windows User Management (from WindowsOpsMixin) ===

    def win_list_users(self) -> list[dict[str, Any]]:
        """List all local Windows user accounts."""
        return self._host._dispatch_manager_attr_call("_win_users", "list_users")

    def win_get_user_info(self, username: str) -> dict[str, Any] | None:
        """Get detailed information about a Windows user."""
        return self._host._dispatch_manager_attr_call("_win_users", "get_user_info", username)

    def win_get_user_groups(self, username: str) -> list[str]:
        """Get groups that a Windows user is a member of."""
        return self._host._dispatch_manager_attr_call("_win_users", "get_user_groups", username)

    def win_is_administrator(self, username: str) -> bool:
        """Check if Windows user is in Administrators group."""
        return self._host._dispatch_manager_attr_call("_win_users", "is_administrator", username)

    def win_is_disabled(self, username: str) -> bool:
        """Check if Windows user account is disabled."""
        return self._host._dispatch_manager_attr_call("_win_users", "is_disabled", username)

    def win_list_administrators(self) -> list[str]:
        """List all Windows administrator accounts."""
        return self._host._dispatch_manager_attr_call("_win_users", "list_administrators")

    def win_list_enabled_users(self) -> list[str]:
        """List all enabled Windows user accounts."""
        return self._host._dispatch_manager_attr_call("_win_users", "list_enabled_users")

    def win_list_disabled_users(self) -> list[str]:
        """List all disabled Windows user accounts."""
        return self._host._dispatch_manager_attr_call("_win_users", "list_disabled_users")

    def win_get_user_count(self) -> dict[str, int]:
        """Get Windows user account statistics."""
        return self._host._dispatch_manager_attr_call("_win_users", "get_user_count")

    # === Windows Service Management (from WindowsOpsMixin) ===

    def win_list_services(self) -> list[dict[str, Any]]:
        """List all Windows services from SYSTEM registry."""
        return self._host._dispatch_manager_attr_call("_win_services", "list_services")

    def win_get_service_count(self) -> dict[str, Any]:
        """Get Windows service statistics by start type."""
        return self._host._dispatch_manager_attr_call("_win_services", "get_service_count")

    def win_list_automatic_services(self) -> list[str]:
        """List Windows services that start automatically."""
        return self._host._dispatch_manager_attr_call("_win_services", "list_automatic_services")

    def win_list_disabled_services(self) -> list[str]:
        """List disabled Windows services."""
        return self._host._dispatch_manager_attr_call("_win_services", "list_disabled_services")

    # === Windows Application Management (from WindowsOpsMixin) ===

    def win_list_applications(self, limit: int = 100) -> list[dict[str, Any]]:
        """List installed Windows applications from registry."""
        return self._host._dispatch_manager_attr_call("_win_apps", "list_applications", limit=limit)

    def win_get_application_count(self) -> dict[str, Any]:
        """Get Windows application statistics."""
        return self._host._dispatch_manager_attr_call("_win_apps", "get_application_count")

    def win_search_applications(self, query: str) -> list[dict[str, Any]]:
        """Search Windows applications by name or publisher."""
        return self._host._dispatch_manager_attr_call("_win_apps", "search_applications", query)

    def win_get_applications_by_publisher(self, publisher: str) -> list[dict[str, Any]]:
        """Get Windows applications from a specific publisher."""
        return self._host._dispatch_manager_attr_call(
            "_win_apps", "get_applications_by_publisher", publisher
        )

    # === Windows methods from StorageMixin ===

    def win_inject_driver(self, driver_path: str, inf_file: str | None = None) -> dict[str, Any]:
        """Inject Windows driver into guest filesystem."""
        return self._host._dispatch_manager_attr_call("_win_drivers", "inject_driver", driver_path, inf_file)

    def win_registry_read(self, hive_name: str, key_path: str, value_name: str) -> str | None:
        """Read value from Windows registry hive."""
        return self._host._dispatch_manager_attr_call(
            "_win_registry", "read_value", hive_name, key_path, value_name
        )

    def win_registry_write(
        self, hive_name: str, key_path: str, value_name: str, value: str, value_type: str = "sz"
    ) -> bool:
        """Write value to Windows registry hive."""
        return self._host._dispatch_manager_attr_call(
            "_win_registry", "write_value", hive_name, key_path, value_name, value, value_type
        )

    def win_registry_list_keys(self, hive_name: str, key_path: str = "") -> list[str]:
        """List subkeys under a registry key."""
        return self._host._dispatch_manager_attr_call("_win_registry", "list_keys", hive_name, key_path)

    def win_registry_list_values(self, hive_name: str, key_path: str) -> dict[str, Any]:
        """List values under a registry key."""
        return self._host._dispatch_manager_attr_call("_win_registry", "list_values", hive_name, key_path)

    def win_resolve_path(self, path: str) -> Path | None:
        """Resolve Windows path (case-insensitive)."""
        return self._host._dispatch_manager_attr_call("_win_registry", "resolve_path", path)
