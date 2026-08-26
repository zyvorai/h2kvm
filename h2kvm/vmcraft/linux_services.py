# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/linux_services.py
"""
Linux systemd service management.

Provides systemd service operations:
- List systemd services
- Get service status
- Check enabled/disabled state
- Query service dependencies
- Analyze service startup
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class LinuxServiceManager:
    """
    Linux systemd service manager.

    Manages systemd services by reading unit files and systemd state.
    """

    def __init__(self, log: logging.Logger, mount_root: Path):
        """
        Initialize Linux service manager.

        Args:
            log: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = log
        self.mount_root = mount_root

    def list_services(self) -> list[dict[str, Any]]:
        """
        List all systemd service units.

        Searches for service unit files in standard systemd directories.

        Returns:
            List of service dictionaries with name, path, enabled status
        """
        services: list[dict[str, Any]] = []

        # Systemd unit file locations
        unit_paths = [
            "usr/lib/systemd/system",
            "lib/systemd/system",
            "etc/systemd/system",
        ]

        for unit_path in unit_paths:
            unit_dir = self.mount_root / unit_path
            if not unit_dir.exists():
                continue

            try:
                for service_file in unit_dir.glob("*.service"):
                    service_name = service_file.name

                    # Skip templates and symlinks (for now)
                    if "@" in service_name:
                        continue

                    service_info = {
                        "name": service_name.replace(".service", ""),
                        "unit_name": service_name,
                        "path": f"/{unit_path}/{service_name}",
                        "enabled": self._is_service_enabled(service_name),
                    }

                    # Parse unit file for additional info
                    unit_info = self._parse_unit_file(service_file)
                    service_info.update(unit_info)

                    services.append(service_info)

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort listing over a mounted guest filesystem; one
                # unreadable/odd unit dir must not abort service discovery.
                self.logger.debug(f"Error listing services in {unit_path}: {e}")

        # Remove duplicates (prefer /etc over /usr/lib)
        seen_names = set()
        unique_services = []
        for svc in sorted(services, key=lambda x: x["path"].startswith("/etc"), reverse=True):
            if svc["name"] not in seen_names:
                unique_services.append(svc)
                seen_names.add(svc["name"])

        return unique_services

    def get_service_info(self, service_name: str) -> dict[str, Any] | None:
        """
        Get detailed information about a service.

        Args:
            service_name: Name of service (with or without .service)

        Returns:
            Dict with service information or None if not found
        """
        if not service_name.endswith(".service"):
            service_name += ".service"

        # Search for service file
        unit_paths = [
            "etc/systemd/system",
            "usr/lib/systemd/system",
            "lib/systemd/system",
        ]

        for unit_path in unit_paths:
            service_file = self.mount_root / unit_path / service_name
            if service_file.exists():
                info = self._parse_unit_file(service_file)
                info["name"] = service_name.replace(".service", "")
                info["unit_name"] = service_name
                info["path"] = f"/{unit_path}/{service_name}"
                info["enabled"] = self._is_service_enabled(service_name)
                return info

        return None

    def _parse_unit_file(self, unit_file: Path) -> dict[str, Any]:  # pylint: disable=too-many-branches
        # One key/section pair per branch when parsing a systemd unit file;
        # complexity is inherent to the INI-like format being parsed.
        """
        Parse systemd unit file.

        Extracts key information from [Unit], [Service], and [Install] sections.

        Args:
            unit_file: Path to .service unit file

        Returns:
            Dict with parsed unit information
        """
        info: dict[str, Any] = {
            "description": None,
            "after": [],
            "before": [],
            "requires": [],
            "wants": [],
            "wanted_by": [],
            "type": None,
            "exec_start": None,
        }

        # pylint: disable=duplicate-code
        # reason: this INI-style unit-file section/key=value parsing loop
        # mirrors similar loops in core/inspectors/linux_extractor.py
        # (.network parsing) and vmcraft/systemd/systemctl.py
        # (cat_unit_file section parsing) -- structurally similar by
        # coincidence, not shared logic; keeping independent avoids
        # coupling unrelated unit-file parsing code paths.
        try:
            content = unit_file.read_text()
            current_section = None

            for line in content.splitlines():
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith(("#", ";")):
                    continue

                # Detect section headers
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                    continue

                # Parse key=value pairs
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # [Unit] section
                if current_section == "Unit":
                    if key == "Description":
                        info["description"] = value
                    elif key == "After":
                        info["after"].extend(value.split())
                    elif key == "Before":
                        info["before"].extend(value.split())
                    elif key == "Requires":
                        info["requires"].extend(value.split())
                    elif key == "Wants":
                        info["wants"].extend(value.split())

                # [Service] section
                elif current_section == "Service":
                    if key == "Type":
                        info["type"] = value
                    elif key == "ExecStart":
                        info["exec_start"] = value

                # [Install] section
                elif current_section == "Install" and key == "WantedBy":
                    info["wanted_by"].extend(value.split())

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort parse of a guest-provided unit file (may be
            # malformed/odd encoding); must not abort the caller.
            self.logger.debug(f"Error parsing unit file {unit_file}: {e}")

        return info

    def _is_service_enabled(self, service_name: str) -> bool:
        """
        Check if service is enabled.

        A service is enabled if there are symlinks in /etc/systemd/system
        target directories pointing to the service unit file.

        Args:
            service_name: Service unit name (e.g., sshd.service)

        Returns:
            True if service is enabled
        """
        # Check for symlinks in /etc/systemd/system/*.wants/ and *.requires/
        system_dir = self.mount_root / "etc/systemd/system"

        if not system_dir.exists():
            return False

        try:
            # Look for symlinks in .wants and .requires directories
            for target_dir in system_dir.glob("*.wants"):
                link = target_dir / service_name
                if link.exists() or link.is_symlink():
                    return True

            for target_dir in system_dir.glob("*.requires"):
                link = target_dir / service_name
                if link.exists() or link.is_symlink():
                    return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort symlink probe over guest state; must not abort
            # the caller on unexpected filesystem quirks.
            self.logger.debug(f"Error checking enabled status: {e}")

        return False

    def list_enabled_services(self) -> list[str]:
        """
        List all enabled services.

        Returns:
            List of enabled service names
        """
        services = self.list_services()
        return [svc["name"] for svc in services if svc.get("enabled", False)]

    def list_disabled_services(self) -> list[str]:
        """
        List all disabled services.

        Returns:
            List of disabled service names
        """
        services = self.list_services()
        return [svc["name"] for svc in services if not svc.get("enabled", False)]

    def get_service_dependencies(self, service_name: str) -> dict[str, Any]:
        """
        Get service dependencies.

        Args:
            service_name: Name of service to query

        Returns:
            Dict with dependency information
        """
        info = self.get_service_info(service_name)

        if not info:
            return {
                "service": service_name,
                "found": False,
            }

        return {
            "service": service_name,
            "found": True,
            "after": info.get("after", []),
            "before": info.get("before", []),
            "requires": info.get("requires", []),
            "wants": info.get("wants", []),
            "wanted_by": info.get("wanted_by", []),
        }

    def find_services_by_target(self, target: str = "multi-user.target") -> list[str]:
        """
        Find services enabled for a specific target.

        Args:
            target: Systemd target name (default: multi-user.target)

        Returns:
            List of service names
        """
        services = []
        target_dir = self.mount_root / "etc/systemd/system" / f"{target}.wants"

        if not target_dir.exists():
            return services

        try:
            for link in target_dir.iterdir():
                if link.name.endswith(".service"):
                    services.append(link.name.replace(".service", ""))

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort directory listing over guest state; must not
            # abort the caller on unexpected filesystem quirks.
            self.logger.debug(f"Error listing target services: {e}")

        return services

    def get_boot_services(self) -> list[str]:
        """
        Get services that start at boot.

        Combines services from default.target, multi-user.target, and graphical.target.

        Returns:
            List of service names
        """
        boot_services = set()

        # Common boot targets
        targets = [
            "default.target",
            "multi-user.target",
            "graphical.target",
            "sysinit.target",
        ]

        for target in targets:
            services = self.find_services_by_target(target)
            boot_services.update(services)

        return sorted(boot_services)

    def get_service_stats(self) -> dict[str, int]:
        """
        Get service statistics.

        Returns:
            Dict with counts of total, enabled, disabled services
        """
        services = self.list_services()

        return {
            "total": len(services),
            "enabled": sum(1 for svc in services if svc.get("enabled", False)),
            "disabled": sum(1 for svc in services if not svc.get("enabled", False)),
        }

    def find_failed_services(self) -> list[str]:
        """
        Find services that might have failed.

        This is a heuristic based on common failure indicators in unit files.

        Returns:
            List of potentially failed service names
        """
        # Since we're inspecting an offline system, we can't check actual status
        # This would need to be implemented differently for live systems
        self.logger.debug("Failed service detection not available for offline inspection")
        return []
