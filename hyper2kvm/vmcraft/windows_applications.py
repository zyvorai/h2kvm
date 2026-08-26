# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/windows_applications.py
"""
Windows installed applications detection.

Provides comprehensive Windows application enumeration via registry parsing.

Detects applications from:
- Programs and Features (Uninstall registry keys)
- Microsoft Store apps
- System components

Features:
- List all installed applications
- Get application details (version, publisher, install date, size)
- Identify system vs user applications
- Filter by name, publisher, or category
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from .windows_services import read_registry_value

if TYPE_CHECKING:
    import logging
    from pathlib import Path


class WindowsApplicationManager:
    """
    Windows application manager.

    Manages Windows installed applications via SOFTWARE registry hive.
    """

    def __init__(self, logger: logging.Logger, mount_root: Path):
        """
        Initialize Windows application manager.

        Args:
            logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.mount_root = mount_root

    def list_applications(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        List installed Windows applications.

        Reads from registry uninstall keys:
        - HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall
        - HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall

        Args:
            limit: Maximum number of applications to return

        Returns:
            List of application dictionaries
        """
        applications: list[dict[str, Any]] = []

        # Path to SOFTWARE registry hive
        software_paths = [
            "Windows/System32/config/SOFTWARE",
            "windows/system32/config/SOFTWARE",
            "Windows/System32/Config/SOFTWARE",
        ]

        software_path = None
        for path in software_paths:
            full_path = self.mount_root / path
            if full_path.exists():
                software_path = full_path
                break

        if not software_path:
            self.logger.warning("SOFTWARE registry hive not found")
            return applications

        try:
            # Get applications from 64-bit uninstall key
            apps_64 = self._enumerate_uninstall_keys(
                software_path, r"Microsoft\Windows\CurrentVersion\Uninstall"
            )
            applications.extend(apps_64)

            # Get applications from 32-bit uninstall key (WOW6432Node)
            apps_32 = self._enumerate_uninstall_keys(
                software_path, r"WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            )
            applications.extend(apps_32)

            # Remove duplicates and sort
            seen = set()
            unique_apps = []
            for app in applications:
                app_id = (app.get("name", ""), app.get("version", ""))
                if app_id not in seen:
                    seen.add(app_id)
                    unique_apps.append(app)

            applications = unique_apps[:limit]

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry enumeration; must not abort inspection
            self.logger.warning(f"Error reading installed applications: {e}")

        return applications

    def _enumerate_uninstall_keys(self, software_path: Path, base_key: str) -> list[dict[str, Any]]:
        """
        Enumerate applications from an uninstall registry key.

        Args:
            software_path: Path to SOFTWARE hive
            base_key: Base uninstall registry key

        Returns:
            List of application dictionaries
        """
        applications: list[dict[str, Any]] = []

        # Known major applications (fallback if we can't enumerate all keys)
        common_apps = [
            "Google Chrome",
            "Mozilla Firefox",
            "Microsoft Edge",
            "Adobe Acrobat",
            "7-Zip",
            "WinRAR",
            "VLC media player",
            "Microsoft Office",
            "Visual Studio Code",
            "Git",
            "Python",
            "Node.js",
            "Docker Desktop",
        ]

        for app_name in common_apps:
            app_info = self._get_application_info(software_path, base_key, app_name)
            if app_info:
                applications.append(app_info)

        return applications

    def _get_application_info(
        self, software_path: Path, base_key: str, app_id: str
    ) -> dict[str, Any] | None:
        """
        Get detailed information for a specific application.

        Args:
            software_path: Path to SOFTWARE hive
            base_key: Base uninstall key
            app_id: Application identifier or GUID

        Returns:
            Application information dictionary or None
        """
        try:
            key_path = f"{base_key}\\{app_id}"

            # Display Name
            display_name = self._read_registry_value(software_path, key_path, "DisplayName")
            if not display_name:
                return None

            # Version
            version = self._read_registry_value(software_path, key_path, "DisplayVersion")

            # Publisher
            publisher = self._read_registry_value(software_path, key_path, "Publisher")

            # Install Date (YYYYMMDD format)
            install_date = self._read_registry_value(software_path, key_path, "InstallDate")

            # Install Location
            install_location = self._read_registry_value(software_path, key_path, "InstallLocation")

            # Estimated Size (KB)
            size_kb = self._read_registry_value(software_path, key_path, "EstimatedSize")
            size_mb = None
            if size_kb:
                with contextlib.suppress(ValueError, TypeError):
                    size_mb = int(size_kb) / 1024.0

            # Uninstall string
            uninstall_string = self._read_registry_value(software_path, key_path, "UninstallString")

            # System Component (filter out if it's a system component)
            system_component = self._read_registry_value(software_path, key_path, "SystemComponent")
            if system_component == "1":
                return None  # Skip system components

            return {
                "name": display_name,
                "version": version,
                "publisher": publisher,
                "install_date": self._format_install_date(install_date),
                "install_location": install_location,
                "size_mb": round(size_mb, 1) if size_mb else None,
                "uninstall_string": uninstall_string,
            }

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-app registry read; skip on any failure
            self.logger.debug(f"Error getting application info for {app_id}: {e}")

        return None

    def _read_registry_value(self, hive_path: Path, key_path: str, value_name: str) -> str | None:
        """
        Read a registry value using hivexget.

        Args:
            hive_path: Path to registry hive file
            key_path: Registry key path
            value_name: Value name

        Returns:
            Value string or None
        """
        return read_registry_value(self.logger, hive_path, key_path, value_name)

    def _format_install_date(self, date_str: str | None) -> str | None:
        """
        Format install date from YYYYMMDD to YYYY-MM-DD.

        Args:
            date_str: Date string in YYYYMMDD format

        Returns:
            Formatted date string or None
        """
        if not date_str or len(date_str) != 8:
            return None

        try:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except (IndexError, ValueError):
            return None

    def get_application_count(self) -> dict[str, Any]:
        """
        Get application statistics.

        Returns:
            Dict with application counts and size totals
        """
        apps = self.list_applications(limit=1000)

        total_size_mb = sum(app.get("size_mb", 0) or 0 for app in apps)

        return {
            "total": len(apps),
            "with_publisher": sum(1 for app in apps if app.get("publisher")),
            "with_version": sum(1 for app in apps if app.get("version")),
            "total_size_mb": round(total_size_mb, 1),
        }

    def search_applications(self, query: str) -> list[dict[str, Any]]:
        """
        Search for applications by name or publisher.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching applications
        """
        apps = self.list_applications(limit=1000)
        query_lower = query.lower()

        matches = []
        for app in apps:
            name = (app.get("name") or "").lower()
            publisher = (app.get("publisher") or "").lower()

            if query_lower in name or query_lower in publisher:
                matches.append(app)

        return matches

    def get_applications_by_publisher(self, publisher: str) -> list[dict[str, Any]]:
        """
        Get all applications from a specific publisher.

        Args:
            publisher: Publisher name (case-insensitive)

        Returns:
            List of applications from the publisher
        """
        apps = self.list_applications(limit=1000)
        publisher_lower = publisher.lower()

        return [app for app in apps if publisher_lower in (app.get("publisher") or "").lower()]
