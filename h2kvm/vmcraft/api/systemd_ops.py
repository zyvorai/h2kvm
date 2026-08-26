# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Operations.

Provides comprehensive systemd integration methods for VMCraft via composition.
Merges SystemdMixin + SystemdExtMixin into a single SystemdOps class.

Includes systemctl, journalctl, systemd-analyze, sysconfig, systemd management,
systemd-networkd, systemd journal, and unit file management.
"""

# pylint: disable=too-many-lines
# reason: cohesive SystemdOps composition class covering the full systemd surface
# (systemctl, journalctl, systemd-analyze, networkd, units, ...); splitting it would
# scatter a single conceptual API across many files.

from __future__ import annotations

from typing import Any

from h2kvm.vmcraft.services import (
    offline_journalctl_export_to_file as svc_offline_journalctl_export_to_file,
    offline_journalctl_list_boots_detailed as svc_offline_journalctl_list_boots_detailed,
    offline_systemd_analyze_failures as svc_offline_systemd_analyze_failures,
    offline_systemd_analyze_plot_offline as svc_offline_systemd_analyze_plot_offline,
    offline_systemd_analyze_security_offline as svc_offline_systemd_analyze_security_offline,
    offline_systemd_analyze_time_offline as svc_offline_systemd_analyze_time_offline,
    offline_systemd_boot_entries as svc_offline_systemd_boot_entries,
    offline_systemd_boot_loader_config as svc_offline_systemd_boot_loader_config,
    offline_systemd_coredump_config as svc_offline_systemd_coredump_config,
    offline_systemd_coredump_list as svc_offline_systemd_coredump_list,
    offline_systemd_detect_anomalies as svc_offline_systemd_detect_anomalies,
    offline_systemd_detect_virt as svc_offline_systemd_detect_virt,
    offline_systemd_logind_config as svc_offline_systemd_logind_config,
    offline_systemd_machine_id as svc_offline_systemd_machine_id,
    offline_systemd_migration_readiness_check as svc_offline_systemd_migration_readiness_check,
    offline_systemd_networkd_config as svc_offline_systemd_networkd_config,
    offline_systemd_oomd_config as svc_offline_systemd_oomd_config,
    offline_systemd_portable_list as svc_offline_systemd_portable_list,
    offline_systemd_post_migration_validation as svc_offline_systemd_post_migration_validation,
    offline_systemd_pstore_list as svc_offline_systemd_pstore_list,
    offline_systemd_resolved_config as svc_offline_systemd_resolved_config,
    offline_systemd_security_compliance_check as svc_offline_systemd_security_compliance_check,
    offline_systemd_sysext_list as svc_offline_systemd_sysext_list,
    offline_systemd_sysusers_config as svc_offline_systemd_sysusers_config,
    offline_systemd_timesyncd_config as svc_offline_systemd_timesyncd_config,
)


class SystemdOps:  # pylint: disable=too-many-public-methods
    # reason: thin 1:1 wrapper surface over the full systemd operation set
    # (systemctl, journalctl, analyze, networkd, units, journal, ...).
    """Systemd operations via composition."""

    # pylint: disable=protected-access
    # reason: SystemdOps is a composition helper that deliberately reaches into its
    # host client's dispatch helpers (_dispatch_manager_attr_call,
    # _offline_systemd_*_call, _require_mount_root) within the same vmcraft.api
    # package -- same pattern used throughout h2kvm/vmcraft/api/*.py.

    def __init__(self, host) -> None:
        self._host = host

    # ============================================================================
    # Dispatch helpers
    # ============================================================================

    def _systemctl_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to systemctl manager."""
        return self._host._dispatch_manager_attr_call("_systemctl", method, *args, **kwargs)

    def _journalctl_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to journalctl manager."""
        return self._host._dispatch_manager_attr_call("_journalctl", method, *args, **kwargs)

    def _systemd_analyze_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to systemd-analyze manager."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", method, *args, **kwargs)

    def _sysconfig_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to sysconfig manager (timedatectl, hostnamectl, etc)."""
        return self._host._dispatch_manager_attr_call("_sysconfig", method, *args, **kwargs)

    def _systemd_mgr_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to systemd manager."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", method, *args, **kwargs)

    def _systemd_networkd_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to systemd-networkd manager."""
        return self._host._dispatch_manager_attr_call("_systemd_networkd", method, *args, **kwargs)

    def _systemd_journal_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to systemd journal manager."""
        return self._host._dispatch_manager_attr_call("_systemd_journal", method, *args, **kwargs)

    def _systemd_units_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch call to systemd units manager."""
        return self._host._dispatch_manager_attr_call("_systemd_units", method, *args, **kwargs)

    # ============================================================================
    # systemctl APIs
    # ============================================================================

    def systemctl_list_units(
        self, unit_type: str = "service", state: str | None = None, all_units: bool = True
    ) -> list[dict[str, str]]:
        """
        List systemd units.

        Args:
            unit_type: Type of unit (service, timer, socket, target, mount, etc.)
            state: Filter by state (active, inactive, failed, running, etc.)
            all_units: Include inactive units

        Returns:
            List of dicts with keys: unit, load, active, sub, description
        """
        return self._host._dispatch_manager_attr_call(
            "_systemctl", "list_units", unit_type, state, all_units
        )

    def systemctl_list_unit_files(self, unit_type: str = "service") -> list[dict[str, str]]:
        """List installed unit files."""
        return self._host._dispatch_manager_attr_call("_systemctl", "list_unit_files", unit_type)

    def systemctl_is_active(self, unit: str) -> bool:
        """Check if a unit is active."""
        return self._host._dispatch_manager_attr_call("_systemctl", "is_active", unit)

    def systemctl_is_enabled(self, unit: str) -> str:
        """Check if a unit is enabled (returns: enabled, disabled, static, masked, etc.)."""
        return self._host._dispatch_manager_attr_call("_systemctl", "is_enabled", unit)

    def systemctl_is_failed(self, unit: str) -> bool:
        """Check if a unit is in failed state."""
        return self._host._dispatch_manager_attr_call("_systemctl", "is_failed", unit)

    def systemctl_show(self, unit: str) -> dict[str, str]:
        """Show properties of a unit."""
        return self._host._dispatch_manager_attr_call("_systemctl", "show", unit)

    def systemctl_status(self, unit: str) -> dict[str, Any]:
        """Get detailed status of a unit."""
        return self._host._dispatch_manager_attr_call("_systemctl", "status", unit)

    def systemctl_cat(self, unit: str) -> str:
        """Show unit file content."""
        return self._host._dispatch_manager_attr_call("_systemctl", "cat", unit)

    def systemctl_list_dependencies(
        self, unit: str, reverse: bool = False, recursive: bool = True
    ) -> list[str]:
        """List unit dependencies."""
        return self._host._dispatch_manager_attr_call(
            "_systemctl", "list_dependencies", unit, reverse, recursive
        )

    def systemctl_list_failed(self) -> list[dict[str, str]]:
        """List all failed units."""
        return self._systemctl_call("list_failed")

    def systemctl_get_default_target(self) -> str:
        """Get the default boot target."""
        return self._systemctl_call("get_default_target")

    def systemctl_list_targets(self) -> list[str]:
        """List all available targets."""
        return self._systemctl_call("list_targets")

    def systemctl_list_timers(self) -> list[dict[str, str]]:
        """List systemd timers."""
        return self._systemctl_call("list_timers")

    def systemctl_list_sockets(self) -> list[dict[str, str]]:
        """List systemd socket units."""
        return self._systemctl_call("list_sockets")

    def systemctl_list_mounts(self) -> list[dict[str, str]]:
        """List systemd mount units."""
        return self._systemctl_call("list_mounts")

    # Enhanced systemctl operations

    def systemctl_cat_unit_file(self, unit: str) -> str:
        """
        Get full unit file content including drop-ins.

        Args:
            unit: Unit name (e.g., "sshd.service")

        Returns:
            Full unit file content

        Example:
            content = g.systemctl_cat_unit_file("nginx.service")
            if "PrivateTmp" in content:
                print("Service uses PrivateTmp")
        """
        return self._host._dispatch_manager_attr_call("_systemctl", "cat_unit_file", unit)

    def systemctl_read_unit_file(self, unit: str) -> dict[str, dict[str, str]]:
        """
        Parse unit file into structured configuration.

        Args:
            unit: Unit name

        Returns:
            Dict of sections with key-value pairs

        Example:
            config = g.systemctl_read_unit_file("sshd.service")
            exec_start = config.get("Service", {}).get("ExecStart")
            print(f"ExecStart: {exec_start}")
        """
        return self._host._dispatch_manager_attr_call("_systemctl", "read_unit_file", unit)

    def systemctl_get_unit_overrides(self, unit: str) -> list[str]:
        """
        Get list of drop-in override files for a unit.

        Args:
            unit: Unit name

        Returns:
            List of override file paths

        Example:
            overrides = g.systemctl_get_unit_overrides("sshd.service")
            print(f"Unit has {len(overrides)} override(s)")
        """
        return self._host._dispatch_manager_attr_call("_systemctl", "get_unit_overrides", unit)

    def systemctl_get_unit_dependencies_full(self, unit: str) -> dict[str, list[str]]:
        """
        Get comprehensive dependency information for a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with dependency types (requires, wants, conflicts, etc.)

        Example:
            deps = g.systemctl_get_unit_dependencies_full("nginx.service")
            print(f"Requires: {deps['requires']}")
            print(f"After: {deps['after']}")
        """
        return self._host._dispatch_manager_attr_call("_systemctl", "get_unit_dependencies_full", unit)

    def systemctl_analyze_unit_conflicts(self) -> list[dict[str, Any]]:
        """
        Analyze all units for potential conflicts.

        Returns:
            List of dicts describing conflicts

        Example:
            conflicts = g.systemctl_analyze_unit_conflicts()
            for conflict in conflicts:
                print(f"Conflict: {conflict['unit1']} vs {conflict['unit2']}")
        """
        return self._systemctl_call("analyze_unit_conflicts")

    def systemctl_get_unit_security_settings(self, unit: str) -> dict[str, Any]:
        """
        Extract security-related settings from a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with security settings (PrivateTmp, ProtectSystem, etc.)

        Example:
            security = g.systemctl_get_unit_security_settings("nginx.service")
            if not security.get("private_tmp"):
                print("Service does not use PrivateTmp")
        """
        return self._host._dispatch_manager_attr_call("_systemctl", "get_unit_security_settings", unit)

    # ============================================================================
    # journalctl APIs
    # ============================================================================

    def journalctl_query(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        unit: str | None = None,
        priority: int | None = None,
        since: str | None = None,
        until: str | None = None,
        boot: int | str | None = None,
        lines: int | None = None,
        grep: str | None = None,
        output_format: str = "short",
    ) -> str:
        """Query systemd journal logs."""
        return self._host._dispatch_manager_attr_call(
            "_journalctl", "query", unit, priority, since, until, boot, lines, grep, output_format
        )

    def journalctl_list_boots(self) -> list[dict[str, str]]:
        """List available boot entries."""
        return self._journalctl_call("list_boots")

    def journalctl_get_boot_log(self, boot: int | str = 0, lines: int | None = None) -> str:
        """Get log for a specific boot."""
        return self._host._dispatch_manager_attr_call("_journalctl", "get_boot_log", boot, lines)

    def journalctl_get_errors(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """Get error messages from journal."""
        return self._host._dispatch_manager_attr_call("_journalctl", "get_errors", since, lines)

    def journalctl_get_warnings(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """Get warning messages from journal."""
        return self._host._dispatch_manager_attr_call("_journalctl", "get_warnings", since, lines)

    def journalctl_disk_usage(self) -> dict[str, Any]:
        """Get journal disk usage information."""
        return self._journalctl_call("disk_usage")

    def journalctl_verify(self) -> dict[str, Any]:
        """Verify journal file consistency."""
        return self._journalctl_call("verify")

    def journalctl_export(self, output_format: str = "json", since: str | None = None) -> str:
        """Export journal logs."""
        return self._host._dispatch_manager_attr_call("_journalctl", "export", output_format, since)

    # Enhanced journal operations

    def journalctl_search(
        self, pattern: str, since: str | None = None, lines: int = 100
    ) -> list[dict[str, str]]:
        """
        Search journal logs for a pattern.

        Args:
            pattern: Pattern to search for (grep-compatible regex)
            since: Search logs since this time
            lines: Maximum number of matching entries

        Returns:
            List of matching journal entries

        Example:
            # Search for authentication failures
            failures = g.journalctl_search("authentication failure", since="1 day ago")
            for entry in failures:
                print(f"{entry['unit']}: {entry['message']}")
        """
        return self._host._dispatch_manager_attr_call("_journalctl", "search", pattern, since, lines)

    def journalctl_statistics(self) -> dict[str, Any]:
        """
        Get journal statistics and message counts.

        Returns:
            Dict with journal statistics

        Example:
            stats = g.journalctl_statistics()
            print(f"Time range: {stats['time_range']}")
        """
        return self._journalctl_call("statistics")

    def journalctl_vacuum(
        self, size: str | None = None, time: str | None = None, files: int | None = None
    ) -> dict[str, str]:
        """
        Clean up old journal log files.

        Args:
            size: Keep only this much disk space (e.g., "500M")
            time: Keep only logs newer than this (e.g., "1month")
            files: Keep only this many journal files

        Returns:
            Dict with vacuum results

        Example:
            result = g.journalctl_vacuum(size="500M")
        """
        return self._host._dispatch_manager_attr_call("_journalctl", "vacuum", size, time, files)

    def journalctl_get_boot_time(self, boot: int | str = 0) -> dict[str, str]:
        """
        Get boot and shutdown time for a specific boot.

        Args:
            boot: Boot ID or offset (0=current, -1=previous)

        Returns:
            Dict with boot_time and shutdown_time

        Example:
            boot_info = g.journalctl_get_boot_time(0)
            print(f"Boot time: {boot_info['boot_time']}")
        """
        return self._host._dispatch_manager_attr_call("_journalctl", "get_boot_time", boot)

    # ============================================================================
    # systemd-analyze APIs
    # ============================================================================

    def systemd_analyze_time(self) -> dict[str, Any]:
        """Analyze system boot time."""
        return self._systemd_analyze_call("time")

    def systemd_analyze_blame(self, lines: int | None = None) -> list[dict[str, str]]:
        """Show which services took the longest to initialize."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "blame", lines)

    def systemd_analyze_critical_chain(self, unit: str | None = None) -> str:
        """Show critical chain for boot or specific unit."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "critical_chain", unit)

    def systemd_analyze_security(self, unit: str | None = None) -> list[dict[str, Any]]:
        """Analyze security settings of services."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "security", unit)

    def systemd_analyze_verify(self, unit: str) -> dict[str, Any]:
        """Verify unit file syntax and configuration."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "verify", unit)

    def systemd_analyze_dot(self, pattern: str | None = None, to_pattern: str | None = None) -> str:
        """Generate dependency graph in GraphViz dot format."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "dot", pattern, to_pattern)

    def systemd_analyze_calendar(self, expression: str) -> dict[str, str]:
        """Validate and show next elapse times for calendar expressions."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "calendar", expression)

    def systemd_analyze_dump(self) -> str:
        """Dump server state in human-readable form."""
        return self._systemd_analyze_call("dump")

    def systemd_analyze_plot(self) -> str:
        """Generate SVG boot time plot."""
        return self._systemd_analyze_call("plot")

    def systemd_analyze_syscall_filter(self, set_name: str | None = None) -> list[str]:
        """List system calls in seccomp filter sets."""
        return self._host._dispatch_manager_attr_call("_systemd_analyze", "syscall_filter", set_name)

    # ============================================================================
    # Configuration APIs (timedatectl, hostnamectl, localectl, loginctl)
    # ============================================================================

    def timedatectl_status(self) -> dict[str, str]:
        """Get time and date settings."""
        return self._sysconfig_call("timedatectl_status")

    def timedatectl_list_timezones(self) -> list[str]:
        """List available timezones."""
        return self._sysconfig_call("timedatectl_list_timezones")

    def timedatectl_show(self) -> dict[str, str]:
        """Show time/date properties in machine-readable format."""
        return self._sysconfig_call("timedatectl_show")

    def hostnamectl_status(self) -> dict[str, str]:
        """Get hostname and system information."""
        return self._sysconfig_call("hostnamectl_status")

    def hostnamectl_hostname(self) -> str:
        """Get current hostname."""
        return self._sysconfig_call("hostnamectl_hostname")

    def localectl_status(self) -> dict[str, str]:
        """Get locale and keyboard configuration."""
        return self._sysconfig_call("localectl_status")

    def localectl_list_locales(self) -> list[str]:
        """List available locales."""
        return self._sysconfig_call("localectl_list_locales")

    def localectl_list_keymaps(self) -> list[str]:
        """List available keyboard mappings."""
        return self._sysconfig_call("localectl_list_keymaps")

    def localectl_list_x11_keymap_models(self) -> list[str]:
        """List available X11 keymap models."""
        return self._sysconfig_call("localectl_list_x11_keymap_models")

    def localectl_list_x11_keymap_layouts(self) -> list[str]:
        """List available X11 keymap layouts."""
        return self._sysconfig_call("localectl_list_x11_keymap_layouts")

    def loginctl_list_sessions(self) -> list[dict[str, str]]:
        """List current login sessions."""
        return self._sysconfig_call("loginctl_list_sessions")

    def loginctl_list_users(self) -> list[dict[str, str]]:
        """List logged-in users."""
        return self._sysconfig_call("loginctl_list_users")

    def loginctl_show_session(self, session: str) -> dict[str, str]:
        """Show properties of a login session."""
        return self._host._dispatch_manager_attr_call("_sysconfig", "loginctl_show_session", session)

    # ============================================================================
    # Advanced systemd Methods - Enhanced Inspection & Forensics
    # ============================================================================

    # Category 1: Core Offline Analysis

    def systemd_analyze_plot_offline(self, output_path: str | None = None) -> str:
        """
        Generate SVG boot timeline from offline VM.

        Works by analyzing journald logs without booting VM.

        Args:
            output_path: Optional path for SVG output

        Returns:
            SVG content as string (or empty if no boot data)
        """
        return self._host._offline_systemd_run_command_call(
            svc_offline_systemd_analyze_plot_offline,
            output_path=output_path,
        )

    def systemd_analyze_security_offline(self, unit: str | None = None) -> list[dict[str, Any]]:
        """
        Security analysis of systemd units from offline VM.

        Analyzes service hardening features without running VM.

        Args:
            unit: Optional specific unit to analyze (default: all services)

        Returns:
            List of security analysis results with scores
        """
        return self._host._offline_systemd_run_command_call(
            svc_offline_systemd_analyze_security_offline,
            unit=unit,
        )

    def systemd_analyze_time_offline(self) -> dict[str, float]:
        """
        Analyze boot time from offline VM journal.

        Returns:
            Dict with boot timing information
            Keys: kernel_time, userspace_time, total_time (in seconds)
        """
        return self._host._offline_systemd_run_command_call(
            svc_offline_systemd_analyze_time_offline,
        )

    def systemd_detect_virt(self) -> dict[str, str]:
        """
        Detect virtualization type from guest VM perspective.

        Returns:
            Dict with virtualization info
        """
        return self._host._offline_systemd_command_call(svc_offline_systemd_detect_virt)

    def systemd_machine_id(self) -> str:
        """
        Get unique machine ID from systemd.

        Returns:
            128-bit machine ID as hex string
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_machine_id)

    # Category 2: Network & Journal (enhanced versions)

    def journalctl_list_boots_detailed(self) -> list[dict[str, Any]]:
        """
        List all boots with detailed information.

        Returns:
            List of boot records with timestamps and IDs
        """
        return self._host._offline_systemd_command_call(svc_offline_journalctl_list_boots_detailed)

    def journalctl_export_to_file(
        self, output_path: str, since: str | None = None, until: str | None = None
    ) -> bool:
        """
        Export journal logs to binary format for offline analysis.

        Args:
            output_path: Path to save exported journal
            since: Optional start timestamp
            until: Optional end timestamp

        Returns:
            True if export successful
        """
        return self._host._offline_systemd_command_call(
            svc_offline_journalctl_export_to_file,
            output_path,
            since,
            until,
        )

    def systemd_networkd_config(self) -> dict[str, Any]:
        """
        Inspect systemd-networkd configuration.

        Returns:
            Dict with network configuration
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_networkd_config)

    def systemd_resolved_config(self) -> dict[str, Any]:
        """
        Inspect systemd-resolved DNS configuration.

        Returns:
            Dict with DNS configuration
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_resolved_config)

    # Category 3: Forensic Analysis

    def systemd_coredump_list(self) -> list[dict[str, Any]]:
        """
        List all core dumps from VM crashes.

        Returns:
            List of core dump records
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_coredump_list)

    def systemd_coredump_config(self) -> dict[str, str]:
        """
        Get core dump configuration from VM.

        Returns:
            Dict with coredump settings
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_coredump_config)

    def systemd_pstore_list(self) -> list[dict[str, Any]]:
        """
        List persistent storage crash data (pstore).

        Returns:
            List of pstore entries
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_pstore_list)

    def systemd_sysusers_config(self) -> list[dict[str, Any]]:
        """
        Get systemd-sysusers configuration.

        Returns:
            List of sysusers entries
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_sysusers_config)

    def systemd_logind_config(self) -> dict[str, Any]:
        """
        Get systemd-logind configuration.

        Returns:
            Dict with logind configuration
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_logind_config)

    def systemd_boot_entries(self) -> list[dict[str, Any]]:
        """
        List systemd-boot (UEFI) boot entries.

        Returns:
            List of boot entries
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_boot_entries)

    def systemd_boot_loader_config(self) -> dict[str, str]:
        """
        Get systemd-boot loader configuration.

        Returns:
            Dict with boot loader settings
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_boot_loader_config)

    def systemd_sysext_list(self) -> list[dict[str, Any]]:
        """
        List systemd system extensions.

        Returns:
            List of system extensions
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_sysext_list)

    # Category 4: Compliance & Security

    def systemd_security_compliance_check(self) -> dict[str, Any]:
        """
        Comprehensive security compliance check.

        Returns:
            Dict with compliance results
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_security_compliance_check)

    def systemd_detect_anomalies(self) -> dict[str, list[dict[str, Any]]]:
        """
        Detect suspicious configurations and anomalies.

        Returns:
            Dict categorizing anomalies by type
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_detect_anomalies)

    def systemd_analyze_failures(self) -> dict[str, Any]:
        """
        Comprehensive analysis of failed services.

        Returns:
            Dict with failure analysis
        """
        self._host._require_mount_root()
        return svc_offline_systemd_analyze_failures(
            self._host.logger,
            systemctl_list_units=self._host.systemctl_list_units,
            systemctl_status=self._host.systemctl_status,
        )

    # Category 5: Migration Readiness

    def systemd_migration_readiness_check(self) -> dict[str, Any]:
        """
        Comprehensive migration readiness assessment.

        Returns:
            Dict with readiness assessment
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_migration_readiness_check)

    def systemd_post_migration_validation(self) -> dict[str, Any]:
        """
        Validate VM after migration.

        Returns:
            Dict with validation results
        """
        self._host._require_mount_root()
        return svc_offline_systemd_post_migration_validation(
            self._host.logger,
            systemd_detect_virt=self._host.systemd_detect_virt,
            systemd_machine_id=self._host.systemd_machine_id,
            systemd_boot_entries=self._host.systemd_boot_entries,
        )

    # Category 6: Advanced System Analysis

    def systemd_oomd_config(self) -> dict[str, Any]:
        """
        Get systemd-oomd (Out-Of-Memory daemon) configuration.

        Returns:
            Dict with OOM daemon configuration
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_oomd_config)

    def systemd_timesyncd_config(self) -> dict[str, Any]:
        """
        Get systemd-timesyncd (NTP client) configuration.

        Returns:
            Dict with NTP configuration
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_timesyncd_config)

    def systemd_portable_list(self) -> list[dict[str, Any]]:
        """
        List systemd portable service images.

        Returns:
            List of portable service images
        """
        return self._host._offline_systemd_mount_call(svc_offline_systemd_portable_list)

    # ============================================================================
    # Systemd Management APIs (from SystemdExtMixin - Core Service Management)
    # ============================================================================

    def systemd_is_available(self) -> bool:
        """
        Check if systemd is available in guest.

        Returns:
            True if systemd is present, False otherwise
        """
        return self._systemd_mgr_call("is_systemd_available")

    def systemd_service_start(self, service: str) -> dict[str, Any]:
        """Start systemd service."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "service_start", service)

    def systemd_service_stop(self, service: str) -> dict[str, Any]:
        """Stop systemd service."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "service_stop", service)

    def systemd_service_restart(self, service: str) -> dict[str, Any]:
        """Restart systemd service."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "service_restart", service)

    def systemd_service_enable(self, service: str) -> dict[str, Any]:
        """Enable service to start at boot."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "service_enable", service)

    def systemd_service_disable(self, service: str) -> dict[str, Any]:
        """Disable service from starting at boot."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "service_disable", service)

    def systemd_service_status(self, service: str) -> dict[str, Any]:
        """Get detailed service status."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "service_status", service)

    def systemd_services_enable_multiple(self, services: list[str]) -> dict[str, bool]:
        """Enable multiple services at once."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "services_enable_multiple", services)

    def systemd_services_disable_multiple(self, services: list[str]) -> dict[str, bool]:
        """Disable multiple services at once."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "services_disable_multiple", services)

    def systemd_services_mask(self, services: list[str]) -> dict[str, bool]:
        """Mask services to prevent activation."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "services_mask", services)

    def systemd_list_services(self, state: str | None = None) -> list[dict[str, Any]]:
        """List all systemd services with optional state filter."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "list_services", state)

    def systemd_list_failed_services(self) -> list[str]:
        """List services in failed state."""
        return self._systemd_mgr_call("list_failed_services")

    def systemd_get_service_dependencies(self, service: str) -> dict[str, list[str]]:
        """Get service dependencies."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "get_service_dependencies", service)

    def systemd_daemon_reload(self) -> dict[str, Any]:
        """Reload systemd manager configuration."""
        return self._systemd_mgr_call("daemon_reload")

    def systemd_systemctl_preset(self, service: str) -> dict[str, Any]:
        """Apply distribution preset for service."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "systemctl_preset", service)

    def systemd_is_service_active(self, service: str) -> bool:
        """Check if service is currently active."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "is_service_active", service)

    def systemd_is_service_enabled(self, service: str) -> bool:
        """Check if service is enabled to start at boot."""
        return self._host._dispatch_manager_attr_call("_systemd_mgr", "is_service_enabled", service)

    # ============================================================================
    # Systemd-networkd APIs (Network Configuration Management)
    # ============================================================================

    def networkd_create_network_file(
        self, name: str, match: dict[str, str], network: dict[str, Any], dhcp: str | None = None
    ) -> dict[str, Any]:
        """Create .network file in /etc/systemd/network/."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_networkd", "create_network_file", name, match, network, dhcp
        )

    def networkd_create_netdev_file(
        self, name: str, kind: str, netdev_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Create .netdev file for virtual devices."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_networkd", "create_netdev_file", name, kind, netdev_config
        )

    def networkd_create_link_file(
        self, name: str, match: dict[str, str], link: dict[str, str]
    ) -> dict[str, Any]:
        """Create .link file for device naming."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_networkd", "create_link_file", name, match, link
        )

    def networkd_remove_network_file(self, name: str) -> dict[str, Any]:
        """Remove .network file."""
        return self._host._dispatch_manager_attr_call("_systemd_networkd", "remove_network_file", name)

    def networkd_list_network_files(self) -> list[dict[str, Any]]:
        """List all systemd-networkd configuration files."""
        return self._systemd_networkd_call("list_network_files")

    def networkd_parse_network_file(self, name: str) -> dict[str, Any]:
        """Parse existing .network file."""
        return self._host._dispatch_manager_attr_call("_systemd_networkd", "parse_network_file", name)

    def networkd_migrate_from_ifcfg(self, interface: str) -> dict[str, Any]:
        """Migrate from ifcfg-* to systemd-networkd."""
        return self._host._dispatch_manager_attr_call("_systemd_networkd", "migrate_from_ifcfg", interface)

    def networkd_migrate_from_networkmanager(self) -> dict[str, Any]:
        """Migrate NetworkManager connections to systemd-networkd."""
        return self._systemd_networkd_call("migrate_from_networkmanager")

    def networkd_create_dhcp_network(self, interface: str) -> dict[str, Any]:
        """Create simple DHCP configuration for interface."""
        return self._host._dispatch_manager_attr_call("_systemd_networkd", "create_dhcp_network", interface)

    def networkd_create_static_network(
        self, interface: str, address: str, gateway: str, dns: list[str] | None = None
    ) -> dict[str, Any]:
        """Create static IP configuration."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_networkd", "create_static_network", interface, address, gateway, dns
        )

    def networkd_create_bridge_network(self, bridge_name: str, interfaces: list[str]) -> dict[str, Any]:
        """Create bridge configuration."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_networkd", "create_bridge_network", bridge_name, interfaces
        )

    def networkd_enable_networkd(self) -> dict[str, Any]:
        """Enable and start systemd-networkd."""
        return self._systemd_networkd_call("enable_networkd")

    # ============================================================================
    # Systemd Journal Integration
    # ============================================================================

    def journal_get(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        lines: int | None = None,
        unit: str | None = None,
        priority: str | None = None,
        since: str | None = None,
        until: str | None = None,
        grep: str | None = None,
    ) -> dict[str, Any]:
        """Get journal entries with filtering."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_journal", "get", lines, unit, priority, since, until, grep
        )

    def journal_get_service(self, service: str, lines: int = 100) -> dict[str, Any]:
        """Get journal entries for specific service."""
        return self._host._dispatch_manager_attr_call("_systemd_journal", "get_service", service, lines)

    def journal_get_since_boot(self, boot_offset: int = 0) -> dict[str, Any]:
        """Get journal entries since specified boot."""
        return self._host._dispatch_manager_attr_call("_systemd_journal", "get_since_boot", boot_offset)

    def journal_get_priority(self, priority: str, lines: int = 100) -> dict[str, Any]:
        """Get journal entries by priority level."""
        return self._host._dispatch_manager_attr_call("_systemd_journal", "get_priority", priority, lines)

    def journal_get_tail(self, lines: int = 100) -> dict[str, Any]:
        """Get last N journal entries."""
        return self._host._dispatch_manager_attr_call("_systemd_journal", "get_tail", lines)

    def journal_list_boots(self) -> dict[str, Any]:
        """List available boot sessions."""
        return self._systemd_journal_call("list_boots")

    def journal_get_boot_id(self) -> str | None:
        """Get current boot ID."""
        return self._systemd_journal_call("get_boot_id")

    def journal_get_disk_usage(self) -> dict[str, Any]:
        """Get journal disk usage statistics."""
        return self._systemd_journal_call("get_disk_usage")

    def journal_vacuum(
        self, size: str | None = None, time: str | None = None, files: int | None = None
    ) -> dict[str, Any]:
        """Clean up old journal entries."""
        return self._host._dispatch_manager_attr_call("_systemd_journal", "vacuum", size, time, files)

    def journal_verify(self) -> dict[str, Any]:
        """Verify journal file consistency."""
        return self._systemd_journal_call("verify")

    # ============================================================================
    # Systemd Unit File Management
    # ============================================================================

    def units_create_service_unit(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        description: str,
        exec_start: str,
        exec_stop: str | None = None,
        service_type: str = "simple",
        restart: str = "on-failure",
        user: str | None = None,
        after: list[str] | None = None,
        requires: list[str] | None = None,
        wants: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create systemd service unit file."""
        return self._systemd_units_call(
            "create_service_unit",
            name,
            description,
            exec_start,
            exec_stop,
            service_type,
            restart,
            user,
            after,
            requires,
            wants,
        )

    def units_create_timer_unit(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        description: str,
        on_calendar: str | None = None,
        on_boot_sec: str | None = None,
        on_unit_active_sec: str | None = None,
        service: str | None = None,
    ) -> dict[str, Any]:
        """Create systemd timer unit file."""
        return self._systemd_units_call(
            "create_timer_unit", name, description, on_calendar, on_boot_sec, on_unit_active_sec, service
        )

    def units_create_mount_unit(
        self, name: str, what: str, where: str, fs_type: str = "auto", options: str | None = None
    ) -> dict[str, Any]:
        """Create systemd mount unit file."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_units", "create_mount_unit", name, what, where, fs_type, options
        )

    def units_create_target_unit(
        self,
        name: str,
        description: str,
        requires: list[str] | None = None,
        wants: list[str] | None = None,
        after: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create systemd target unit file."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_units", "create_target_unit", name, description, requires, wants, after
        )

    def units_create_path_unit(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        description: str,
        path_exists: str | None = None,
        path_changed: str | None = None,
        path_modified: str | None = None,
        unit: str | None = None,
    ) -> dict[str, Any]:
        """Create systemd path unit."""
        return self._systemd_units_call(
            "create_path_unit", name, description, path_exists, path_changed, path_modified, unit
        )

    def units_read_unit_file(self, unit: str) -> dict[str, Any]:
        """Parse systemd unit file into structured dict."""
        return self._host._dispatch_manager_attr_call("_systemd_units", "read_unit_file", unit)

    def units_modify_unit_file(self, unit: str, section: str, key: str, value: str) -> dict[str, Any]:
        """Modify specific key in unit file."""
        return self._host._dispatch_manager_attr_call(
            "_systemd_units", "modify_unit_file", unit, section, key, value
        )

    def units_delete_unit_file(self, unit: str) -> dict[str, Any]:
        """Delete unit file."""
        return self._host._dispatch_manager_attr_call("_systemd_units", "delete_unit_file", unit)

    def units_validate_unit_file(self, unit: str) -> dict[str, Any]:
        """Validate unit file syntax."""
        return self._host._dispatch_manager_attr_call("_systemd_units", "validate_unit_file", unit)

    def units_analyze_boot_performance(self) -> dict[str, Any]:
        """Analyze boot performance using systemd-analyze."""
        return self._systemd_units_call("analyze_boot_performance")

    def units_analyze_critical_chain(self, unit: str | None = None) -> dict[str, Any]:
        """Get critical boot path chain."""
        return self._host._dispatch_manager_attr_call("_systemd_units", "analyze_critical_chain", unit)

    def units_analyze_blame(self) -> dict[str, Any]:
        """Get services ordered by initialization time."""
        return self._systemd_units_call("analyze_blame")

    def units_list_timers(self, all_timers: bool = False) -> dict[str, Any]:
        """List active or all timers."""
        return self._host._dispatch_manager_attr_call("_systemd_units", "list_timers", all_timers)
