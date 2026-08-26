# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd unit file management for VMCraft.

This module provides APIs for creating, modifying, and analyzing systemd
unit files (services, timers, mounts, targets, paths) within guest VMs.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ._utils import run_sudo


class SystemdUnitsManager:
    """
    Systemd unit file creation, modification, and analysis.

    Provides APIs for generating unit files, parsing existing configurations,
    and analyzing boot performance.
    """

    def __init__(self, logger: logging.Logger, guest_root: str):
        """
        Initialize SystemdUnitsManager.

        Args:
            logger: Logger instance for output
            guest_root: Path to guest filesystem root
        """
        self.logger = logger
        self.guest_root = Path(guest_root)
        self.system_units_dir = self.guest_root / "etc/systemd/system"

    # ==================================================================================
    # Unit File Creation (5 methods)
    # ==================================================================================

    def create_service_unit(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # unit-file API surface
        self,
        name: str,
        description: str,
        exec_start: str,
        exec_stop: str | None = None,
        unit_type: str = "simple",
        restart: str = "on-failure",
        user: str | None = None,
        after: list[str] | None = None,
        requires: list[str] | None = None,
        wants: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create systemd service unit file.

        Args:
            name: Service name (e.g., "myapp")
            description: Service description
            exec_start: Command to start service
            exec_stop: Command to stop service (optional)
            unit_type: Service type (simple, forking, oneshot, dbus, notify, idle)
            restart: Restart policy (no, on-success, on-failure, on-abnormal, always)
            user: Run as specific user
            after: List of units this should start after
            requires: Hard dependencies
            wants: Soft dependencies

        Returns:
            Audit dict with operation result

        Example:
            >>> # Create custom service
            >>> g.units_create_service_unit(
            ...     name="myapp",
            ...     description="My Application",
            ...     exec_start="/usr/bin/myapp",
            ...     after=["network.target"],
            ...     restart="always",
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "unit": None, "path": None}

        try:
            # Ensure directory exists
            self.system_units_dir.mkdir(parents=True, exist_ok=True)

            # Construct unit file path
            if not name.endswith(".service"):
                name = f"{name}.service"

            unit_path = self.system_units_dir / name
            audit["attempted"] = True
            audit["unit"] = name
            audit["path"] = str(unit_path)

            # Build unit file content
            content = "[Unit]\n"
            content += f"Description={description}\n"

            if after:
                content += f"After={' '.join(after)}\n"

            if requires:
                content += f"Requires={' '.join(requires)}\n"

            if wants:
                content += f"Wants={' '.join(wants)}\n"

            content += "\n[Service]\n"
            content += f"Type={unit_type}\n"
            content += f"ExecStart={exec_start}\n"

            if exec_stop:
                content += f"ExecStop={exec_stop}\n"

            content += f"Restart={restart}\n"

            if user:
                content += f"User={user}\n"

            content += "\n[Install]\n"
            content += "WantedBy=multi-user.target\n"

            # Write file
            unit_path.write_text(content)
            unit_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info("Created service unit: %s", unit_path)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unit write, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to create service unit: %s", e)
            return audit

    def create_timer_unit(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # unit-file API surface
        self,
        name: str,
        description: str,
        on_calendar: str | None = None,
        on_boot_sec: str | None = None,
        on_unit_active_sec: str | None = None,
        service: str | None = None,
    ) -> dict[str, Any]:
        """
        Create systemd timer unit file.

        Args:
            name: Timer name (e.g., "backup")
            description: Timer description
            on_calendar: Calendar specification (e.g., "daily", "Mon *-*-* 00:00:00")
            on_boot_sec: Time after boot (e.g., "15min")
            on_unit_active_sec: Interval after last activation (e.g., "1h")
            service: Service to activate (defaults to same name)

        Returns:
            Audit dict with operation result

        Example:
            >>> # Create daily backup timer
            >>> g.units_create_timer_unit(
            ...     name="backup",
            ...     description="Daily Backup Timer",
            ...     on_calendar="daily",
            ...     service="backup.service",
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "unit": None, "path": None}

        if not on_calendar and not on_boot_sec and not on_unit_active_sec:
            audit["error"] = "at least one timer trigger required"
            return audit

        try:
            # Ensure directory exists
            self.system_units_dir.mkdir(parents=True, exist_ok=True)

            # Construct unit file path
            if not name.endswith(".timer"):
                name = f"{name}.timer"

            unit_path = self.system_units_dir / name
            audit["attempted"] = True
            audit["unit"] = name
            audit["path"] = str(unit_path)

            # Build unit file content
            content = "[Unit]\n"
            content += f"Description={description}\n"

            content += "\n[Timer]\n"

            if on_calendar:
                content += f"OnCalendar={on_calendar}\n"

            if on_boot_sec:
                content += f"OnBootSec={on_boot_sec}\n"

            if on_unit_active_sec:
                content += f"OnUnitActiveSec={on_unit_active_sec}\n"

            if service:
                content += f"Unit={service}\n"

            content += "\n[Install]\n"
            content += "WantedBy=timers.target\n"

            # Write file
            unit_path.write_text(content)
            unit_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info("Created timer unit: %s", unit_path)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unit write, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to create timer unit: %s", e)
            return audit

    def create_mount_unit(
        self, name: str, what: str, where: str, fs_type: str = "auto", options: str | None = None
    ) -> dict[str, Any]:
        """
        Create systemd mount unit file.

        Args:
            name: Mount unit name
            what: What to mount (device or path)
            where: Where to mount
            fs_type: Filesystem type
            options: Mount options

        Returns:
            Audit dict with operation result

        Example:
            >>> # Create mount unit
            >>> g.units_create_mount_unit(
            ...     name="data", what="/dev/sdb1", where="/mnt/data", fs_type="ext4", options="defaults"
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "unit": None, "path": None}

        try:
            # Ensure directory exists
            self.system_units_dir.mkdir(parents=True, exist_ok=True)

            # Mount units must match mount point path
            if not name.endswith(".mount"):
                name = f"{name}.mount"

            unit_path = self.system_units_dir / name
            audit["attempted"] = True
            audit["unit"] = name
            audit["path"] = str(unit_path)

            # Build unit file content
            content = "[Unit]\n"
            content += f"Description=Mount {where}\n"

            content += "\n[Mount]\n"
            content += f"What={what}\n"
            content += f"Where={where}\n"
            content += f"Type={fs_type}\n"

            if options:
                content += f"Options={options}\n"

            content += "\n[Install]\n"
            content += "WantedBy=multi-user.target\n"

            # Write file
            unit_path.write_text(content)
            unit_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info("Created mount unit: %s", unit_path)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unit write, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to create mount unit: %s", e)
            return audit

    def create_target_unit(
        self,
        name: str,
        description: str,
        requires: list[str] | None = None,
        wants: list[str] | None = None,
        after: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create systemd target unit file.

        Args:
            name: Target name
            description: Target description
            requires: Hard dependencies
            wants: Soft dependencies
            after: Ordering dependencies

        Returns:
            Audit dict with operation result

        Example:
            >>> # Create custom target
            >>> g.units_create_target_unit(
            ...     name="myapp",
            ...     description="My Application Target",
            ...     wants=["myapp-web.service", "myapp-db.service"],
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "unit": None, "path": None}

        try:
            # Ensure directory exists
            self.system_units_dir.mkdir(parents=True, exist_ok=True)

            # Construct unit file path
            if not name.endswith(".target"):
                name = f"{name}.target"

            unit_path = self.system_units_dir / name
            audit["attempted"] = True
            audit["unit"] = name
            audit["path"] = str(unit_path)

            # Build unit file content
            content = "[Unit]\n"
            content += f"Description={description}\n"

            if requires:
                content += f"Requires={' '.join(requires)}\n"

            if wants:
                content += f"Wants={' '.join(wants)}\n"

            if after:
                content += f"After={' '.join(after)}\n"

            # Write file
            unit_path.write_text(content)
            unit_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info("Created target unit: %s", unit_path)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unit write, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to create target unit: %s", e)
            return audit

    def create_path_unit(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # unit-file API surface
        self,
        name: str,
        description: str,
        path_exists: str | None = None,
        path_changed: str | None = None,
        path_modified: str | None = None,
        unit: str | None = None,
    ) -> dict[str, Any]:
        """
        Create systemd path unit (filesystem watcher).

        Args:
            name: Path unit name
            description: Path unit description
            path_exists: Trigger when path exists
            path_changed: Trigger when path changes
            path_modified: Trigger when path modified
            unit: Unit to activate

        Returns:
            Audit dict with operation result

        Example:
            >>> # Watch for file changes
            >>> g.units_create_path_unit(
            ...     name="watch-config",
            ...     description="Watch Config Directory",
            ...     path_changed="/etc/myapp/",
            ...     unit="myapp-reload.service",
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "unit": None, "path": None}

        if not path_exists and not path_changed and not path_modified:
            audit["error"] = "at least one path trigger required"
            return audit

        try:
            # Ensure directory exists
            self.system_units_dir.mkdir(parents=True, exist_ok=True)

            # Construct unit file path
            if not name.endswith(".path"):
                name = f"{name}.path"

            unit_path = self.system_units_dir / name
            audit["attempted"] = True
            audit["unit"] = name
            audit["path"] = str(unit_path)

            # Build unit file content
            content = "[Unit]\n"
            content += f"Description={description}\n"

            content += "\n[Path]\n"

            if path_exists:
                content += f"PathExists={path_exists}\n"

            if path_changed:
                content += f"PathChanged={path_changed}\n"

            if path_modified:
                content += f"PathModified={path_modified}\n"

            if unit:
                content += f"Unit={unit}\n"

            content += "\n[Install]\n"
            content += "WantedBy=multi-user.target\n"

            # Write file
            unit_path.write_text(content)
            unit_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info("Created path unit: %s", unit_path)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unit write, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to create path unit: %s", e)
            return audit

    # ==================================================================================
    # Unit File Management (4 methods)
    # ==================================================================================

    def read_unit_file(self, unit: str) -> dict[str, Any]:
        """
        Parse systemd unit file into structured dict.

        Args:
            unit: Unit name

        Returns:
            Dict with parsed sections

        Example:
            >>> config = g.units_read_unit_file("sshd.service")
            >>> print(config["sections"]["Service"]["ExecStart"])
        """
        result: dict[str, Any] = {"ok": False, "error": None, "sections": {}}

        # pylint: disable=duplicate-code
        # reason: this INI-style section/key=value parsing loop mirrors
        # similar loops in vmcraft/systemd_networkd.py (parse_network_file)
        # and vmcraft/enhanced_inspection.py -- structurally similar by
        # coincidence, not shared logic; keeping independent avoids
        # coupling unrelated config-parsing code paths.
        try:
            # Find unit file
            unit_path = self.system_units_dir / unit

            if not unit_path.exists():
                # Try system units
                system_path = self.guest_root / f"usr/lib/systemd/system/{unit}"
                if system_path.exists():
                    unit_path = system_path
                else:
                    result["error"] = "unit_file_not_found"
                    return result

            content = unit_path.read_text()
            sections: dict[str, dict[str, Any]] = {}
            current_section = None

            for line in content.split("\n"):
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith(("#", ";")):
                    continue

                # Section header
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                    sections[current_section] = {}
                # Key-value pair
                elif "=" in line and current_section:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Handle multiple values for same key
                    if key in sections[current_section]:
                        if not isinstance(sections[current_section][key], list):
                            sections[current_section][key] = [sections[current_section][key]]
                        sections[current_section][key].append(value)
                    else:
                        sections[current_section][key] = value

            result["ok"] = True
            result["sections"] = sections
            return result

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort read, must not abort
            result["error"] = str(e)
            self.logger.debug("Failed to read unit file: %s", e)
            return result

    def modify_unit_file(self, unit: str, section: str, key: str, value: str) -> dict[str, Any]:
        """
        Modify specific key in unit file.

        Args:
            unit: Unit name
            section: Section name (e.g., "Service", "Unit")
            key: Key to modify
            value: New value

        Returns:
            Audit dict with operation result

        Example:
            >>> # Change restart policy
            >>> g.units_modify_unit_file(
            ...     unit="myapp.service", section="Service", key="Restart", value="always"
            ... )
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        try:
            unit_path = self.system_units_dir / unit

            if not unit_path.exists():
                audit["error"] = "unit_file_not_found"
                return audit

            audit["attempted"] = True

            # Read current content
            lines = unit_path.read_text().split("\n")
            modified = False
            current_section = None

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Track current section
                if stripped.startswith("[") and stripped.endswith("]"):
                    current_section = stripped[1:-1]

                # Modify matching key
                if current_section == section and "=" in stripped:
                    line_key = stripped.split("=", 1)[0].strip()
                    if line_key == key:
                        lines[i] = f"{key}={value}"
                        modified = True
                        break

            if not modified:
                audit["error"] = "key_not_found"
                return audit

            # Write modified content
            unit_path.write_text("\n".join(lines))

            audit["ok"] = True
            self.logger.info("Modified unit file %s: [%s] %s=%s", unit, section, key, value)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort modify, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to modify unit file: %s", e)
            return audit

    def delete_unit_file(self, unit: str) -> dict[str, Any]:
        """
        Delete unit file.

        Args:
            unit: Unit name

        Returns:
            Audit dict with operation result

        Example:
            >>> g.units_delete_unit_file("myapp.service")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        try:
            unit_path = self.system_units_dir / unit

            if not unit_path.exists():
                audit["error"] = "unit_file_not_found"
                return audit

            audit["attempted"] = True

            unit_path.unlink()

            audit["ok"] = True
            self.logger.info("Deleted unit file: %s", unit)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort delete, must not abort
            audit["error"] = str(e)
            self.logger.warning("Failed to delete unit file: %s", e)
            return audit

    def validate_unit_file(self, unit: str) -> dict[str, Any]:
        """
        Validate unit file syntax.

        Args:
            unit: Unit name

        Returns:
            Audit dict with validation result

        Example:
            >>> result = g.units_validate_unit_file("myapp.service")
            >>> if not result["ok"]:
            ...     print(f"Invalid: {result['error']}")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "valid": False}

        try:
            # Check if file exists and is readable
            read_result = self.read_unit_file(unit)

            if not read_result["ok"]:
                audit["error"] = read_result["error"]
                return audit

            audit["attempted"] = True

            # Basic validation: must have at least Unit or Service/Timer/Mount section
            sections = read_result["sections"]

            if not sections:
                audit["error"] = "no_sections_found"
                return audit

            # Validate has appropriate sections
            valid_sections = ["Unit", "Service", "Timer", "Mount", "Target", "Path", "Install"]
            has_valid_section = any(s in sections for s in valid_sections)

            if not has_valid_section:
                audit["error"] = "no_valid_sections"
                return audit

            audit["ok"] = True
            audit["valid"] = True
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort validate, must not abort
            audit["error"] = str(e)
            self.logger.debug("Failed to validate unit file: %s", e)
            return audit

    # ==================================================================================
    # Analysis Methods (4 methods)
    # ==================================================================================

    def analyze_boot_performance(self) -> dict[str, Any]:
        """
        Analyze boot performance using systemd-analyze.

        Returns:
            Dict with boot timing information

        Example:
            >>> perf = g.units_analyze_boot_performance()
            >>> print(f"Boot time: {perf['boot_time']}")
        """
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "boot_time": None,
            "kernel_time": None,
            "userspace_time": None,
        }

        try:
            cmd = ["chroot", str(self.guest_root), "systemd-analyze"]
            result = run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)

            audit["attempted"] = True
            audit["ok"] = True

            # Parse output: "Startup finished in 1.234s (kernel) + 5.678s (userspace) = 6.912s"
            output = result.stdout.strip()
            audit["output"] = output

            # Extract timing information
            kernel_match = re.search(r"(\d+\.?\d*)(m?s) \(kernel\)", output)
            userspace_match = re.search(r"(\d+\.?\d*)(m?s) \(userspace\)", output)
            total_match = re.search(r"= (\d+\.?\d*)(m?s)", output)

            if kernel_match:
                audit["kernel_time"] = kernel_match.group(1) + kernel_match.group(2)

            if userspace_match:
                audit["userspace_time"] = userspace_match.group(1) + userspace_match.group(2)

            if total_match:
                audit["boot_time"] = total_match.group(1) + total_match.group(2)

            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort analysis, must not abort
            audit["error"] = str(e)
            self.logger.debug("Failed to analyze boot performance: %s", e)
            return audit

    def analyze_critical_chain(self, unit: str | None = None) -> dict[str, Any]:
        """
        Get critical boot path chain.

        Args:
            unit: Optional unit to analyze (default: boot target)

        Returns:
            Dict with critical chain analysis

        Example:
            >>> chain = g.units_analyze_critical_chain()
            >>> print(chain["output"])
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "output": None}

        try:
            cmd = ["chroot", str(self.guest_root), "systemd-analyze", "critical-chain"]

            if unit:
                cmd.append(unit)

            result = run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)

            audit["attempted"] = True
            audit["ok"] = True
            audit["output"] = result.stdout.strip()

            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort analysis, must not abort
            audit["error"] = str(e)
            self.logger.debug("Failed to analyze critical chain: %s", e)
            return audit

    def analyze_blame(self) -> dict[str, Any]:
        """
        Get services ordered by initialization time.

        Returns:
            Dict with blame analysis (services sorted by init time)

        Example:
            >>> blame = g.units_analyze_blame()
            >>> for service in blame["services"][:5]:
            ...     print(f"{service['time']}: {service['name']}")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "services": []}

        try:
            cmd = ["chroot", str(self.guest_root), "systemd-analyze", "blame"]
            result = run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)

            audit["attempted"] = True
            audit["ok"] = True

            # Parse output: "1.234s service-name.service"
            services = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        services.append({"time": parts[0], "name": parts[1]})

            audit["services"] = services
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort analysis, must not abort
            audit["error"] = str(e)
            self.logger.debug("Failed to analyze blame: %s", e)
            return audit

    def list_timers(self, show_all: bool = False) -> dict[str, Any]:
        """
        List active or all timers.

        Args:
            show_all: List all timers (default: active only)

        Returns:
            Dict with timer list

        Example:
            >>> timers = g.units_list_timers()
            >>> for timer in timers["timers"]:
            ...     print(f"{timer['timer']}: {timer['next']}")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "timers": []}

        try:
            cmd = ["chroot", str(self.guest_root), "systemctl", "list-timers", "--no-pager", "--no-legend"]

            if show_all:
                cmd.append("--all")

            result = run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)

            audit["attempted"] = True
            audit["ok"] = True

            # pylint: disable=duplicate-code
            # reason: this "for line in ...: parts = line.split(None, N)"
            # output-parsing loop mirrors similar loops in
            # vmcraft/systemd/systemctl.py (list_timers) -- structurally
            # similar by coincidence, not shared logic; keeping independent
            # avoids coupling unrelated systemctl-output parsing.
            # Parse output
            timers = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    # Format: NEXT LEFT LAST PASSED UNIT ACTIVATES
                    parts = line.split(None, 5)
                    if len(parts) >= 6:
                        timers.append(
                            {
                                "next": parts[0],
                                "left": parts[1],
                                "last": parts[2],
                                "passed": parts[3],
                                "timer": parts[4],
                                "activates": parts[5],
                            }
                        )

            audit["timers"] = timers
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort listing, must not abort
            audit["error"] = str(e)
            self.logger.debug("Failed to list timers: %s", e)
            return audit
