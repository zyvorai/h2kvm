# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemctl integration for VMCraft.

Provides service management and inspection capabilities.
"""

# pylint: disable=duplicate-code
# reason: this module has 6 near-identical "for line in result.splitlines():
# ... parts = line.split(...)" output-parsing loops (one per systemctl
# subcommand) that are structurally similar to output-parsing loops in
# sibling systemd/* and vmcraft modules (e.g. systemd/sysconfig.py,
# systemd/analyze.py, systemd_units.py) by coincidence, not shared logic;
# keeping each independently editable avoids coupling unrelated
# subcommand-output parsing. See git history for the pylint pass that
# reviewed each instance.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import logging


class SystemctlManager:  # pylint: disable=too-many-public-methods  # thin one-method-per-systemctl-subcommand wrapper
    """Manage systemd services via systemctl."""

    def __init__(self, command_runner: Callable[[list[str]], str], logger: logging.Logger):
        """
        Initialize SystemctlManager.

        Args:
            command_runner: Function to execute commands in guest (e.g., VMCraft.command_quiet)
            logger: Logger instance
        """
        self.command = command_runner
        self.logger = logger

    def list_units(
        self, unit_type: str = "service", state: str | None = None, all_units: bool = True
    ) -> list[dict[str, str]]:
        """
        List systemd units.

        Args:
            unit_type: Type of unit (service, timer, socket, target, mount, etc.)
            state: Filter by state (active, inactive, failed, running, etc.)
            all_units: Include inactive units (default: True)

        Returns:
            List of dicts with keys: unit, load, active, sub, description

        Example:
            services = manager.list_units("service", "active")
            for svc in services:
                print(f"{svc['unit']}: {svc['description']}")
        """
        try:
            cmd = ["systemctl", "list-units", f"--type={unit_type}", "--no-pager", "--plain", "--no-legend"]
            if all_units:
                cmd.append("--all")
            if state:
                cmd.append(f"--state={state}")

            result = self.command(cmd)

            units = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Parse systemctl output
                # Format: UNIT  LOAD  ACTIVE  SUB  DESCRIPTION
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    units.append(
                        {
                            "unit": parts[0],
                            "load": parts[1],
                            "active": parts[2],
                            "sub": parts[3],
                            "description": parts[4],
                        }
                    )
                elif len(parts) >= 4:
                    units.append(
                        {
                            "unit": parts[0],
                            "load": parts[1],
                            "active": parts[2],
                            "sub": parts[3],
                            "description": "",
                        }
                    )

            return units

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl list-units failed: {e}")
            return []

    def list_unit_files(self, unit_type: str = "service") -> list[dict[str, str]]:
        """
        List installed unit files.

        Args:
            unit_type: Type of unit file to list

        Returns:
            List of dicts with keys: unit_file, state

        Example:
            unit_files = manager.list_unit_files("service")
            enabled = [u for u in unit_files if u['state'] == 'enabled']
        """
        try:
            cmd = [
                "systemctl",
                "list-unit-files",
                f"--type={unit_type}",
                "--no-pager",
                "--plain",
                "--no-legend",
            ]
            result = self.command(cmd)

            unit_files = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                if len(parts) >= 2:
                    unit_files.append(
                        {
                            "unit_file": parts[0],
                            "state": parts[1],
                        }
                    )

            return unit_files

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl list-unit-files failed: {e}")
            return []

    def is_active(self, unit: str) -> bool:
        """
        Check if a unit is active.

        Args:
            unit: Unit name (e.g., "sshd.service")

        Returns:
            True if active, False otherwise
        """
        try:
            cmd = ["systemctl", "is-active", unit]
            result = self.command(cmd)
            return result.strip() == "active"
        except Exception:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            return False

    def is_enabled(self, unit: str) -> str:
        """
        Check if a unit is enabled.

        Args:
            unit: Unit name

        Returns:
            State string: "enabled", "disabled", "static", "masked", "generated", etc.
        """
        try:
            cmd = ["systemctl", "is-enabled", unit]
            result = self.command(cmd)
            return result.strip()
        except Exception:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            return "unknown"

    def is_failed(self, unit: str) -> bool:
        """
        Check if a unit is in failed state.

        Args:
            unit: Unit name

        Returns:
            True if failed, False otherwise
        """
        try:
            cmd = ["systemctl", "is-failed", unit]
            result = self.command(cmd)
            return result.strip() == "failed"
        except Exception:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            return False

    def show(self, unit: str) -> dict[str, str]:
        """
        Show properties of a unit.

        Args:
            unit: Unit name

        Returns:
            Dict of unit properties

        Example:
            props = manager.show("sshd.service")
            print(f"Main PID: {props.get('MainPID')}")
            print(f"Memory: {props.get('MemoryCurrent')}")
        """
        try:
            cmd = ["systemctl", "show", unit, "--no-pager"]
            result = self.command(cmd)

            properties = {}
            for line in result.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    properties[key] = value

            return properties

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl show failed for {unit}: {e}")
            return {}

    def status(self, unit: str) -> dict[str, Any]:
        """
        Get detailed status of a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with keys: active, sub, main_pid, status_text, recent_logs

        Example:
            status = manager.status("nginx.service")
            print(f"Active: {status['active']}")
            print(f"PID: {status['main_pid']}")
        """
        try:
            cmd = ["systemctl", "status", unit, "--no-pager", "--lines=10"]
            result = self.command(cmd)

            status_info = {
                "active": "unknown",
                "sub": "unknown",
                "main_pid": "",
                "status_text": result,
                "recent_logs": [],
            }

            # Parse status output
            for line in result.splitlines():
                line = line.strip()

                # Active line: "Active: active (running) since ..."
                if line.startswith("Active:"):
                    match = re.search(r"Active:\s+(\w+)\s+\((\w+)\)", line)
                    if match:
                        status_info["active"] = match.group(1)
                        status_info["sub"] = match.group(2)

                # Main PID line: "Main PID: 1234 (nginx)"
                elif line.startswith("Main PID:"):
                    match = re.search(r"Main PID:\s+(\d+)", line)
                    if match:
                        status_info["main_pid"] = match.group(1)

                # Log lines
                elif line.startswith(("├─", "└─", "│")):
                    status_info["recent_logs"].append(line)

            return status_info

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl status failed for {unit}: {e}")
            return {
                "active": "unknown",
                "sub": "unknown",
                "main_pid": "",
                "status_text": "",
                "recent_logs": [],
            }

    def cat(self, unit: str) -> str:
        """
        Show unit file content.

        Args:
            unit: Unit name

        Returns:
            Unit file content as string
        """
        try:
            cmd = ["systemctl", "cat", unit, "--no-pager"]
            return self.command(cmd)
        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl cat failed for {unit}: {e}")
            return ""

    def list_dependencies(self, unit: str, reverse: bool = False, recursive: bool = True) -> list[str]:
        """
        List unit dependencies.

        Args:
            unit: Unit name
            reverse: Show reverse dependencies (what depends on this unit)
            recursive: Show all recursive dependencies (default: True)

        Returns:
            List of dependency unit names

        Example:
            deps = manager.list_dependencies("nginx.service")
            print(f"nginx depends on: {deps}")

            rdeps = manager.list_dependencies("network.target", reverse=True)
            print(f"Services needing network: {rdeps}")
        """
        try:
            cmd = ["systemctl", "list-dependencies", unit, "--no-pager", "--plain"]
            if reverse:
                cmd.append("--reverse")
            if not recursive:
                cmd.append("--no-recursion")

            result = self.command(cmd)

            dependencies = []
            for line in result.splitlines():
                line = line.strip()
                if not line or line == unit:
                    continue

                # Remove tree characters
                line = re.sub(r"^[●├─└│\s]+", "", line)
                if line:
                    dependencies.append(line)

            return dependencies

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl list-dependencies failed for {unit}: {e}")
            return []

    def list_failed(self) -> list[dict[str, str]]:
        """
        List all failed units.

        Returns:
            List of dicts with failed unit information

        Example:
            failed = manager.list_failed()
            if failed:
                print(f"⚠️  {len(failed)} services failed!")
                for unit in failed:
                    print(f"  - {unit['unit']}: {unit['description']}")
        """
        try:
            cmd = ["systemctl", "list-units", "--state=failed", "--no-pager", "--plain", "--no-legend"]
            result = self.command(cmd)

            failed_units = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 4)
                if len(parts) >= 5:
                    failed_units.append(
                        {
                            "unit": parts[0],
                            "load": parts[1],
                            "active": parts[2],
                            "sub": parts[3],
                            "description": parts[4],
                        }
                    )

            return failed_units

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl list failed units: {e}")
            return []

    def get_default_target(self) -> str:
        """
        Get the default boot target.

        Returns:
            Default target name (e.g., "multi-user.target", "graphical.target")
        """
        try:
            cmd = ["systemctl", "get-default"]
            result = self.command(cmd)
            return result.strip()
        except Exception:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            return ""

    def list_targets(self) -> list[str]:
        """
        List all available targets.

        Returns:
            List of target names
        """
        try:
            cmd = [
                "systemctl",
                "list-units",
                "--type=target",
                "--all",
                "--no-pager",
                "--plain",
                "--no-legend",
            ]
            result = self.command(cmd)

            targets = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                if parts:
                    targets.append(parts[0])

            return targets

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl list targets failed: {e}")
            return []

    def list_timers(self) -> list[dict[str, str]]:
        """
        List systemd timers.

        Returns:
            List of dicts with timer information
            Keys: next, left, last, passed, unit, activates

        Example:
            timers = manager.list_timers()
            for timer in timers:
                print(f"{timer['unit']} next run: {timer['next']}")
        """
        try:
            cmd = ["systemctl", "list-timers", "--all", "--no-pager", "--plain", "--no-legend"]
            result = self.command(cmd)

            timers = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Format: NEXT  LEFT  LAST  PASSED  UNIT  ACTIVATES
                parts = line.split(None, 5)
                if len(parts) >= 6:
                    timers.append(
                        {
                            "next": parts[0],
                            "left": parts[1],
                            "last": parts[2],
                            "passed": parts[3],
                            "unit": parts[4],
                            "activates": parts[5],
                        }
                    )

            return timers

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl list-timers failed: {e}")
            return []

    def list_sockets(self) -> list[dict[str, str]]:
        """
        List systemd socket units.

        Returns:
            List of dicts with socket information
        """
        return self.list_units("socket", all_units=True)

    def list_mounts(self) -> list[dict[str, str]]:
        """
        List systemd mount units.

        Returns:
            List of dicts with mount information
        """
        return self.list_units("mount", all_units=True)

    # Enhanced unit file operations

    def cat_unit_file(self, unit: str) -> str:
        """
        Get the full content of a unit file including drop-ins.

        Args:
            unit: Unit name (e.g., "sshd.service")

        Returns:
            Full unit file content as string

        Example:
            content = manager.cat_unit_file("sshd.service")
            if "PermitRootLogin" in content:
                print("Root login configuration found")
        """
        try:
            cmd = ["systemctl", "cat", unit, "--no-pager"]
            return self.command(cmd)
        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"systemctl cat {unit} failed: {e}")
            return ""

    def read_unit_file(self, unit: str) -> dict[str, dict[str, str]]:
        """
        Parse unit file configuration into structured format.

        Args:
            unit: Unit name

        Returns:
            Dict of sections, each containing key-value pairs
            Example: {"Unit": {"Description": "...", ...}, "Service": {...}, ...}

        Example:
            config = manager.read_unit_file("nginx.service")
            print(f"Type: {config.get('Service', {}).get('Type')}")
            print(f"ExecStart: {config.get('Service', {}).get('ExecStart')}")
        """
        try:
            content = self.cat_unit_file(unit)
            if not content:
                return {}

            sections = {}
            current_section = None

            for line in content.splitlines():
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith(("#", ";")):
                    continue

                # Skip file markers from systemctl cat output
                if line.startswith("# /") or line == "# (empty)":
                    continue

                # Section header
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                    sections[current_section] = {}
                    continue

                # Key-value pair
                if "=" in line and current_section:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Handle multi-value keys (like ExecStartPre)
                    if key in sections[current_section]:
                        # Convert to list if not already
                        existing = sections[current_section][key]
                        if not isinstance(existing, list):
                            sections[current_section][key] = [existing]
                        sections[current_section][key].append(value)
                    else:
                        sections[current_section][key] = value

            return sections

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"read_unit_file {unit} failed: {e}")
            return {}

    def get_unit_overrides(self, unit: str) -> list[str]:
        """
        Get list of drop-in override files for a unit.

        Args:
            unit: Unit name

        Returns:
            List of override file paths

        Example:
            overrides = manager.get_unit_overrides("sshd.service")
            if overrides:
                print(f"Unit has {len(overrides)} overrides")
        """
        try:
            content = self.cat_unit_file(unit)
            if not content:
                return []

            overrides = []
            for line in content.splitlines():
                # systemctl cat shows file paths as comments
                if line.startswith("# /") and ".d/" in line:
                    path = line[2:].strip()
                    overrides.append(path)

            return overrides

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"get_unit_overrides {unit} failed: {e}")
            return []

    def get_unit_dependencies_full(self, unit: str) -> dict[str, list[str]]:
        """
        Get comprehensive dependency information for a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with different dependency types:
            - requires: Units this unit requires
            - wants: Units this unit wants
            - required_by: Units requiring this unit
            - wanted_by: Units wanting this unit
            - conflicts: Units conflicting with this unit
            - before: Units that must start before this unit
            - after: Units that must start after this unit

        Example:
            deps = manager.get_unit_dependencies_full("nginx.service")
            print(f"Requires: {deps['requires']}")
            print(f"Required by: {deps['required_by']}")
        """
        try:
            properties = self.show(unit)

            dependencies = {
                "requires": [],
                "wants": [],
                "required_by": [],
                "wanted_by": [],
                "conflicts": [],
                "before": [],
                "after": [],
            }

            # Parse dependency properties
            dep_mapping = {
                "Requires": "requires",
                "Wants": "wants",
                "RequiredBy": "required_by",
                "WantedBy": "wanted_by",
                "Conflicts": "conflicts",
                "Before": "before",
                "After": "after",
            }

            for prop_key, dep_key in dep_mapping.items():
                value = properties.get(prop_key, "")
                if value:
                    # Dependencies are space-separated
                    dependencies[dep_key] = [d for d in value.split() if d]

            return dependencies

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"get_unit_dependencies_full {unit} failed: {e}")
            return {
                "requires": [],
                "wants": [],
                "required_by": [],
                "wanted_by": [],
                "conflicts": [],
                "before": [],
                "after": [],
            }

    def analyze_unit_conflicts(self) -> list[dict[str, Any]]:
        """
        Analyze all units for potential conflicts.

        Returns:
            List of dicts describing conflicts:
            - unit1, unit2: Conflicting units
            - reason: Why they conflict
            - severity: conflict severity (high/medium/low)

        Example:
            conflicts = manager.analyze_unit_conflicts()
            for conflict in conflicts:
                print(f"⚠️  {conflict['unit1']} conflicts with {conflict['unit2']}")
                print(f"   Reason: {conflict['reason']}")
        """
        try:
            conflicts = []

            # Get all services
            services = self.list_units("service", all_units=True)

            # Check each service for explicit conflicts
            for service in services:
                unit_name = service["unit"]
                deps = self.get_unit_dependencies_full(unit_name)

                for conflicting_unit in deps.get("conflicts", []):
                    # Check if conflicting unit exists and is active
                    if self.is_active(conflicting_unit):
                        conflicts.append(
                            {
                                "unit1": unit_name,
                                "unit2": conflicting_unit,
                                "reason": f"{unit_name} explicitly conflicts with {conflicting_unit}",
                                "severity": "high",
                            }
                        )

            # Check for port conflicts (services listening on same port)
            # This would require parsing ExecStart commands, which is complex
            # For now, just return explicit conflicts

            return conflicts

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"analyze_unit_conflicts failed: {e}")
            return []

    def get_unit_security_settings(self, unit: str) -> dict[str, Any]:
        """
        Extract security-related settings from a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with security settings including:
            - private_tmp: Whether unit uses private /tmp
            - protect_system: System protection level
            - protect_home: Home directory protection
            - no_new_privileges: NoNewPrivileges setting
            - user: User the service runs as
            - capabilities: Linux capabilities

        Example:
            security = manager.get_unit_security_settings("nginx.service")
            if not security.get("private_tmp"):
                print("⚠️  Service does not use PrivateTmp")
        """
        try:
            properties = self.show(unit)
            config = self.read_unit_file(unit)

            service_section = config.get("Service", {})

            return {
                "private_tmp": properties.get("PrivateTmp", "no") == "yes",
                "protect_system": properties.get("ProtectSystem", ""),
                "protect_home": properties.get("ProtectHome", ""),
                "no_new_privileges": properties.get("NoNewPrivileges", "no") == "yes",
                "user": properties.get("User", "root"),
                "group": properties.get("Group", ""),
                "capabilities": properties.get("CapabilityBoundingSet", ""),
                "read_only_paths": service_section.get("ReadOnlyPaths", ""),
                "inaccessible_paths": service_section.get("InaccessiblePaths", ""),
                "private_devices": properties.get("PrivateDevices", "no") == "yes",
                "protect_kernel_tunables": properties.get("ProtectKernelTunables", "no") == "yes",
                "protect_control_groups": properties.get("ProtectControlGroups", "no") == "yes",
                "restrict_namespaces": properties.get("RestrictNamespaces", "no") == "yes",
                "lock_personality": properties.get("LockPersonality", "no") == "yes",
            }

        except Exception as e:  # pylint: disable=broad-exception-caught  # command_runner is an injected callable; must not crash on any error
            self.logger.debug(f"get_unit_security_settings {unit} failed: {e}")
            return {}
