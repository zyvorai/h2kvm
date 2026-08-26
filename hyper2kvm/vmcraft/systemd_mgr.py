# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd service and unit management for VMCraft.

This module provides comprehensive systemd integration for managing services,
analyzing dependencies, and controlling systemd units within guest VMs.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ._utils import run_sudo


class SystemdManager:
    """
    Systemd service and unit management.

    Provides APIs for controlling systemd services, querying service states,
    managing dependencies, and performing bulk operations on guest VM systemd.

    This class uses systemd-nspawn for isolated systemd operations when available,
    falling back to chroot-based operations for compatibility.
    """

    def __init__(self, logger: logging.Logger, guest_root: str):
        """
        Initialize SystemdManager.

        Args:
            logger: Logger instance for output
            guest_root: Path to guest filesystem root
        """
        self.logger = logger
        self.guest_root = Path(guest_root)
        self._systemd_available: bool | None = None
        self._use_nspawn: bool | None = None

    def is_systemd_available(self) -> bool:
        """
        Check if systemd is available in guest.

        Returns:
            True if systemd is present, False otherwise

        Example:
            >>> if g.systemd_is_available():
            ...     g.systemd_service_enable("sshd")
        """
        if self._systemd_available is not None:
            return self._systemd_available

        # Check for systemd binary
        systemd_paths = [
            self.guest_root / "usr/lib/systemd/systemd",
            self.guest_root / "lib/systemd/systemd",
            self.guest_root / "usr/bin/systemd",
        ]

        self._systemd_available = any(p.exists() for p in systemd_paths)

        if self._systemd_available:
            self.logger.debug("Systemd detected in guest")
        else:
            self.logger.debug("Systemd not found in guest")

        return self._systemd_available

    def _check_nspawn_available(self) -> bool:
        """Check if systemd-nspawn is available on host."""
        if self._use_nspawn is not None:
            return self._use_nspawn

        try:
            run_sudo(
                self.logger,
                ["which", "systemd-nspawn"],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
            self._use_nspawn = True
            self.logger.debug("systemd-nspawn available, will use for systemctl operations")
        except Exception:  # pylint: disable=broad-exception-caught  # availability probe, absence is expected
            self._use_nspawn = False
            self.logger.debug("systemd-nspawn not available, will use chroot")

        return self._use_nspawn

    def _run_systemctl(self, args: list[str]) -> dict[str, Any]:
        """
        Run systemctl command in guest context.

        Args:
            args: systemctl arguments

        Returns:
            Audit dict with command results
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "stdout": "", "stderr": ""}

        if not self.is_systemd_available():
            audit["error"] = "systemd_not_available"
            return audit

        audit["attempted"] = True

        # pylint: disable=duplicate-code
        # reason: this chroot/nspawn-exec + audit-dict try/except shape
        # mirrors the equivalent block in vmcraft/systemd_journal.py
        # (journalctl runner) -- structurally similar by coincidence, not
        # shared logic; keeping independent avoids coupling unrelated
        # journalctl/systemctl execution code paths.
        try:
            if self._check_nspawn_available():
                # Use systemd-nspawn for proper systemd isolation
                cmd = ["systemd-nspawn", "-D", str(self.guest_root), "--quiet", "--pipe", "systemctl", *args]
            else:
                # Fall back to chroot
                cmd = ["chroot", str(self.guest_root), "systemctl", *args]

            result = run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)

            audit["ok"] = True
            audit["stdout"] = result.stdout
            audit["stderr"] = result.stderr
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort systemd op, must not abort
            audit["error"] = str(e)
            if hasattr(e, "stderr"):
                audit["stderr"] = e.stderr
            return audit

    # Service Control Methods (6 methods)

    def service_start(self, service: str) -> dict[str, Any]:
        """
        Start systemd service.

        Args:
            service: Service name (e.g., "sshd.service" or "sshd")

        Returns:
            Audit dict with operation result

        Example:
            >>> result = g.systemd_service_start("qemu-guest-agent")
            >>> if result["ok"]:
            ...     print("Service started successfully")
        """
        self.logger.info(f"Starting systemd service: {service}")
        result = self._run_systemctl(["start", service])
        result["service"] = service
        result["action"] = "start"
        return result

    def service_stop(self, service: str) -> dict[str, Any]:
        """
        Stop systemd service.

        Args:
            service: Service name

        Returns:
            Audit dict with operation result

        Example:
            >>> g.systemd_service_stop("vmtoolsd")
        """
        self.logger.info(f"Stopping systemd service: {service}")
        result = self._run_systemctl(["stop", service])
        result["service"] = service
        result["action"] = "stop"
        return result

    def service_restart(self, service: str) -> dict[str, Any]:
        """
        Restart systemd service.

        Args:
            service: Service name

        Returns:
            Audit dict with operation result

        Example:
            >>> g.systemd_service_restart("sshd")
        """
        self.logger.info(f"Restarting systemd service: {service}")
        result = self._run_systemctl(["restart", service])
        result["service"] = service
        result["action"] = "restart"
        return result

    def service_enable(self, service: str) -> dict[str, Any]:
        """
        Enable service to start at boot.

        Args:
            service: Service name

        Returns:
            Audit dict with operation result

        Example:
            >>> # Enable qemu-guest-agent for KVM environment
            >>> g.systemd_service_enable("qemu-guest-agent")
        """
        self.logger.info(f"Enabling systemd service: {service}")
        result = self._run_systemctl(["enable", service])
        result["service"] = service
        result["action"] = "enable"
        return result

    # pylint: disable=duplicate-code
    # reason: this docstring/audit-dict shape mirrors similar service-action
    # methods in vmcraft/systemd_networkd.py (migrate_from_ifcfg) --
    # structurally similar by coincidence, not shared logic; keeping
    # independent avoids coupling unrelated systemd/networkd migration
    # code paths.
    def service_disable(self, service: str) -> dict[str, Any]:
        """
        Disable service from starting at boot.

        Args:
            service: Service name

        Returns:
            Audit dict with operation result

        Example:
            >>> # Disable VMware tools during migration
            >>> g.systemd_service_disable("vmtoolsd")
        """
        self.logger.info(f"Disabling systemd service: {service}")
        result = self._run_systemctl(["disable", service])
        result["service"] = service
        result["action"] = "disable"
        return result

    def service_status(self, service: str) -> dict[str, Any]:
        """
        Get detailed service status.

        Args:
            service: Service name

        Returns:
            Dict with status information including:
            - active: Active state (active, inactive, failed)
            - sub: Sub-state (running, dead, exited)
            - loaded: Load state
            - description: Service description

        Example:
            >>> status = g.systemd_service_status("sshd")
            >>> print(f"Active: {status.get('active')}")
        """
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "service": service,
            "active": None,
            "sub": None,
            "loaded": None,
            "description": None,
        }

        if not self.is_systemd_available():
            audit["error"] = "systemd_not_available"
            return audit

        audit["attempted"] = True

        try:
            result = self._run_systemctl(["status", service])

            # Parse status output
            if result.get("stdout"):
                lines = result["stdout"].split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("Loaded:"):
                        match = re.search(r"Loaded:\s+(\S+)", line)
                        if match:
                            audit["loaded"] = match.group(1)
                    elif line.startswith("Active:"):
                        match = re.search(r"Active:\s+(\S+)\s+\((\S+)\)", line)
                        if match:
                            audit["active"] = match.group(1)
                            audit["sub"] = match.group(2)

            audit["ok"] = True
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort systemd op, must not abort
            audit["error"] = str(e)
            return audit

    # Bulk Operations (3 methods)

    def services_enable_multiple(self, services: list[str]) -> dict[str, bool]:
        """
        Enable multiple services at once.

        Args:
            services: List of service names

        Returns:
            Dict mapping service name to success status

        Example:
            >>> services = ["sshd", "qemu-guest-agent", "chronyd"]
            >>> results = g.systemd_services_enable_multiple(services)
            >>> for svc, ok in results.items():
            ...     print(f"{svc}: {'OK' if ok else 'FAILED'}")
        """
        results = {}

        for service in services:
            result = self.service_enable(service)
            results[service] = result.get("ok", False)

        return results

    def services_disable_multiple(self, services: list[str]) -> dict[str, bool]:
        """
        Disable multiple services at once.

        Args:
            services: List of service names

        Returns:
            Dict mapping service name to success status

        Example:
            >>> # Disable VMware-specific services
            >>> vmware_services = ["vmtoolsd", "vmware-tools", "open-vm-tools"]
            >>> results = g.systemd_services_disable_multiple(vmware_services)
        """
        results = {}

        for service in services:
            result = self.service_disable(service)
            results[service] = result.get("ok", False)

        return results

    def services_mask(self, services: list[str]) -> dict[str, bool]:
        """
        Mask services to prevent activation.

        Masking creates a symlink to /dev/null, preventing the service
        from being started by any means.

        Args:
            services: List of service names

        Returns:
            Dict mapping service name to success status

        Example:
            >>> # Completely prevent VMware services from starting
            >>> g.systemd_services_mask(["vmtoolsd", "vmware-tools"])
        """
        results = {}

        for service in services:
            self.logger.info(f"Masking systemd service: {service}")
            result = self._run_systemctl(["mask", service])
            results[service] = result.get("ok", False)

        return results

    # Query/Analysis Methods (6 methods)

    def list_services(self, state: str | None = None) -> list[dict[str, Any]]:
        """
        List all systemd services with optional state filter.

        Args:
            state: Filter by state (active, inactive, failed, enabled, disabled)

        Returns:
            List of service info dicts with keys:
            - name: Service name
            - load: Load state (loaded, not-found)
            - active: Active state (active, inactive, failed)
            - sub: Sub-state (running, dead, exited)
            - description: Service description

        Example:
            >>> # List all active services
            >>> active = g.systemd_list_services(state="active")
            >>> for svc in active:
            ...     print(f"{svc['name']}: {svc['description']}")
        """
        if not self.is_systemd_available():
            return []

        try:
            cmd_args = ["list-units", "--type=service", "--all", "--no-pager", "--no-legend"]

            if state:
                cmd_args.append(f"--state={state}")

            result = self._run_systemctl(cmd_args)

            if not result.get("ok"):
                return []

            services = []
            for line in result.get("stdout", "").strip().split("\n"):
                if not line.strip():
                    continue

                # Parse systemctl list-units output
                # Format: UNIT LOAD ACTIVE SUB DESCRIPTION
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    services.append(
                        {
                            "name": parts[0],
                            "load": parts[1],
                            "active": parts[2],
                            "sub": parts[3],
                            "description": parts[4],
                        }
                    )

            return services

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort systemd op, must not abort
            self.logger.debug(f"Failed to list services: {e}")
            return []

    def list_failed_services(self) -> list[str]:
        """
        List services in failed state.

        Returns:
            List of failed service names

        Example:
            >>> failed = g.systemd_list_failed_services()
            >>> if failed:
            ...     print(f"Failed services: {', '.join(failed)}")
            ...     for svc in failed:
            ...         status = g.systemd_service_status(svc)
            ...         print(f"  {svc}: {status}")
        """
        failed_services = self.list_services(state="failed")
        return [svc["name"] for svc in failed_services]

    def get_service_dependencies(self, service: str) -> dict[str, list[str]]:
        """
        Get service dependencies.

        Args:
            service: Service name

        Returns:
            Dict with dependency lists:
            - requires: Hard dependencies
            - wants: Soft dependencies
            - after: Services that should start before this one
            - before: Services that should start after this one

        Example:
            >>> deps = g.systemd_get_service_dependencies("network.service")
            >>> print(f"Requires: {', '.join(deps['requires'])}")
            >>> print(f"After: {', '.join(deps['after'])}")
        """
        deps = {"requires": [], "wants": [], "after": [], "before": []}

        if not self.is_systemd_available():
            return deps

        try:
            result = self._run_systemctl(
                ["show", service, "--property=Requires,Wants,After,Before", "--no-pager"]
            )

            if not result.get("ok"):
                return deps

            for line in result.get("stdout", "").strip().split("\n"):
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.lower()

                if key in deps and value:
                    # Split space-separated values and filter empty
                    deps[key] = [v.strip() for v in value.split() if v.strip()]

            return deps

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort systemd op, must not abort
            self.logger.debug(f"Failed to get dependencies for {service}: {e}")
            return deps

    def daemon_reload(self) -> dict[str, Any]:
        """
        Reload systemd manager configuration.

        This should be called after modifying unit files to make
        systemd aware of the changes.

        Returns:
            Audit dict with operation result

        Example:
            >>> # After creating/modifying unit files
            >>> g.systemd_daemon_reload()
        """
        self.logger.info("Reloading systemd daemon configuration")
        result = self._run_systemctl(["daemon-reload"])
        result["action"] = "daemon-reload"
        return result

    def systemctl_preset(self, service: str) -> dict[str, Any]:
        """
        Apply distribution preset for service.

        This enables/disables the service based on distribution defaults.

        Args:
            service: Service name

        Returns:
            Audit dict with operation result

        Example:
            >>> # Apply distribution defaults for service
            >>> g.systemd_systemctl_preset("sshd")
        """
        self.logger.info(f"Applying systemd preset for: {service}")
        result = self._run_systemctl(["preset", service])
        result["service"] = service
        result["action"] = "preset"
        return result

    def is_service_active(self, service: str) -> bool:
        """
        Check if service is currently active.

        Args:
            service: Service name

        Returns:
            True if service is active, False otherwise

        Example:
            >>> if g.systemd_is_service_active("sshd"):
            ...     print("SSH server is running")
        """
        try:
            result = self._run_systemctl(["is-active", service])
            stdout = result.get("stdout", "").strip().lower()
            return result.get("ok", False) and stdout == "active"
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort systemd op, must not abort
            self.logger.debug(f"systemctl is-active check failed for '{service}': {e}")
            return False

    def is_service_enabled(self, service: str) -> bool:
        """
        Check if service is enabled to start at boot.

        Args:
            service: Service name

        Returns:
            True if service is enabled, False otherwise

        Example:
            >>> if not g.systemd_is_service_enabled("qemu-guest-agent"):
            ...     g.systemd_service_enable("qemu-guest-agent")
        """
        try:
            result = self._run_systemctl(["is-enabled", service])
            return result.get("ok", False) and "enabled" in result.get("stdout", "").lower()
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort systemd op, must not abort
            self.logger.debug(f"systemctl is-enabled check failed for '{service}': {e}")
            return False
