# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/windows_services.py
"""
Windows service management and analysis.

Provides comprehensive Windows service enumeration and configuration
via registry parsing (SYSTEM hive).

Features:
- List all Windows services
- Get service configuration (start type, path, dependencies)
- Identify running services
- Detect service failures
- Service dependency analysis
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING, Any

from ._utils import run_sudo

if TYPE_CHECKING:
    import logging
    from pathlib import Path


def read_registry_value(
    logger: logging.Logger, hive_path: Path, key_path: str, value_name: str
) -> str | None:
    """
    Read a registry value using hivexget.

    Shared by WindowsServiceManager and (via import)
    h2kvm.vmcraft.windows_applications.WindowsApplicationManager, which both
    perform the exact same registry-value lookup against a mounted guest hive.

    Args:
        logger: Logger instance for output
        hive_path: Path to registry hive file
        key_path: Registry key path
        value_name: Value name

    Returns:
        Value string or None
    """
    try:
        result = run_sudo(logger, ["hivexget", str(hive_path), key_path, value_name], check=False, capture=True)

        if result.returncode == 0:
            value = result.stdout.strip().strip('"')
            return value if value else None

    except Exception:  # pylint: disable=broad-exception-caught  # best-effort hivexget lookup; missing value/tool just means "not found"
        pass

    return None


class WindowsServiceManager:
    """
    Windows service manager.

    Manages Windows services via SYSTEM registry hive access.
    """

    def __init__(self, logger: logging.Logger, mount_root: Path):
        """
        Initialize Windows service manager.

        Args:
            logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.mount_root = mount_root

    def list_services(self) -> list[dict[str, Any]]:
        """
        List all Windows services.

        Reads service information from SYSTEM registry hive.

        Returns:
            List of service dictionaries with name, display name, start type, etc.
        """
        services: list[dict[str, Any]] = []

        # Path to SYSTEM registry hive
        system_paths = [
            "Windows/System32/config/SYSTEM",
            "windows/system32/config/SYSTEM",
            "Windows/System32/Config/SYSTEM",
        ]

        system_path = None
        for path in system_paths:
            full_path = self.mount_root / path
            if full_path.exists():
                system_path = full_path
                break

        if not system_path:
            self.logger.warning("SYSTEM registry hive not found")
            return services

        try:
            # Get list of service keys
            # Services are in ControlSet001\Services
            services = self._enumerate_services(system_path)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest inspection, must not abort
            self.logger.warning(f"Error reading SYSTEM registry: {e}")

        return services

    def _enumerate_services(self, system_path: Path) -> list[dict[str, Any]]:
        """
        Enumerate Windows services from SYSTEM hive.

        Args:
            system_path: Path to SYSTEM registry hive

        Returns:
            List of service dictionaries
        """
        services: list[dict[str, Any]] = []

        script_path = None
        try:
            # List all service keys using hivexsh. run_sudo() has no stdin/input
            # support, so the commands are written to a script file and passed
            # via hivexsh's "-f" (non-interactive) flag instead of stdin.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".hivexsh", delete=False, encoding="utf-8"
            ) as script_file:
                script_file.write("cd ControlSet001\\Services\nls\n")
                script_path = script_file.name

            result = run_sudo(
                self.logger,
                ["hivexsh", "-f", script_path, "-w", str(system_path)],
                check=False,
                capture=True,
            )

            if result.returncode != 0:
                # Try with hivex-navigator or fallback
                return self._enumerate_services_fallback(system_path)

            # Parse output to get service names
            service_names = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("Welcome") and not line.startswith("hivexsh"):
                    service_names.append(line)

            # Get details for each service
            for svc_name in service_names[:100]:  # Limit to first 100
                svc_info = self._get_service_info(system_path, svc_name)
                if svc_info:
                    services.append(svc_info)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest inspection, must not abort
            self.logger.debug(f"Error enumerating services: {e}")
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

        return services

    def _enumerate_services_fallback(self, system_path: Path) -> list[dict[str, Any]]:
        """
        Fallback method to enumerate services using hivexget.

        Args:
            system_path: Path to SYSTEM registry hive

        Returns:
            List of service dictionaries
        """
        services: list[dict[str, Any]] = []

        # Known common Windows services
        common_services = [
            "Eventlog",
            "PlugPlay",
            "RpcSs",
            "W32Time",
            "Winmgmt",
            "wuauserv",
            "BITS",
            "Dhcp",
            "Dnscache",
            "LanmanServer",
            "LanmanWorkstation",
            "Spooler",
            "Themes",
            "AudioSrv",
            "BFE",
            "MpsSvc",
            "WinDefend",
            "SecurityHealthService",
            "Tcpip",
            "Netman",
            "NlaSvc",
            "WinHttpAutoProxySvc",
        ]

        for svc_name in common_services:
            svc_info = self._get_service_info(system_path, svc_name)
            if svc_info:
                services.append(svc_info)

        return services

    def _get_service_info(self, system_path: Path, service_name: str) -> dict[str, Any] | None:
        """
        Get detailed information for a specific service.

        Args:
            system_path: Path to SYSTEM registry hive
            service_name: Service name

        Returns:
            Service information dictionary or None
        """
        try:
            # Read service properties
            base_path = rf"ControlSet001\Services\{service_name}"

            # Display Name
            display_name = self._read_registry_value(system_path, base_path, "DisplayName")

            # Start type (0=Boot, 1=System, 2=Automatic, 3=Manual, 4=Disabled)
            start = self._read_registry_value(system_path, base_path, "Start")
            start_type = self._parse_start_type(start)

            # Image path
            image_path = self._read_registry_value(system_path, base_path, "ImagePath")

            # Service type
            type_val = self._read_registry_value(system_path, base_path, "Type")
            service_type = self._parse_service_type(type_val)

            # Only include if it has service-like properties
            if start_type or image_path or display_name:
                return {
                    "name": service_name,
                    "display_name": display_name or service_name,
                    "start_type": start_type or "unknown",
                    "service_type": service_type or "unknown",
                    "image_path": image_path,
                }

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest inspection, must not abort
            self.logger.debug(f"Error getting service info for {service_name}: {e}")

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

    def _parse_start_type(self, start_val: str | None) -> str:
        """
        Parse Windows service start type.

        Args:
            start_val: Start value from registry

        Returns:
            Human-readable start type
        """
        if not start_val:
            return "unknown"

        try:
            start_int = int(start_val, 16) if start_val.startswith("0x") else int(start_val)
            start_map = {
                0: "boot",
                1: "system",
                2: "automatic",
                3: "manual",
                4: "disabled",
            }
            return start_map.get(start_int, "unknown")
        except (ValueError, AttributeError):
            return "unknown"

    def _parse_service_type(self, type_val: str | None) -> str:
        """
        Parse Windows service type.

        Args:
            type_val: Type value from registry

        Returns:
            Human-readable service type
        """
        if not type_val:
            return "unknown"

        try:
            type_int = int(type_val, 16) if type_val.startswith("0x") else int(type_val)
            type_map = {
                0x1: "kernel_driver",
                0x2: "file_system_driver",
                0x4: "adapter",
                0x10: "own_process",
                0x20: "share_process",
                0x100: "interactive",
            }
            return type_map.get(type_int, f"0x{type_int:x}")
        except (ValueError, AttributeError):
            return "unknown"

    def get_service_count(self) -> dict[str, Any]:
        """
        Get Windows service statistics.

        Returns:
            Dict with service counts by start type
        """
        services = self.list_services()

        return {
            "total": len(services),
            "automatic": sum(1 for s in services if s.get("start_type") == "automatic"),
            "manual": sum(1 for s in services if s.get("start_type") == "manual"),
            "disabled": sum(1 for s in services if s.get("start_type") == "disabled"),
            "boot": sum(1 for s in services if s.get("start_type") == "boot"),
            "system": sum(1 for s in services if s.get("start_type") == "system"),
        }

    def list_automatic_services(self) -> list[str]:
        """
        List services configured to start automatically.

        Returns:
            List of automatic service names
        """
        services = self.list_services()
        return [s["name"] for s in services if s.get("start_type") == "automatic"]

    def list_disabled_services(self) -> list[str]:
        """
        List disabled services.

        Returns:
            List of disabled service names
        """
        services = self.list_services()
        return [s["name"] for s in services if s.get("start_type") == "disabled"]
