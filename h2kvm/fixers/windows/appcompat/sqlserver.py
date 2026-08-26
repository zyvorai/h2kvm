# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""SQL Server instance detection and reconfiguration script generation.

Detects SQL Server installations, extracts configuration, and generates
T-SQL reconfiguration scripts for post-migration execution.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# pylint: disable=duplicate-code
# reason: shared optional-dependency import boilerplate, also present in
# registry/system.py (and appcompat/detector.py) -- kept per-module so each
# fixer stays independently importable.
try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

try:
    import hivex  # type: ignore
except ImportError:
    hivex = None  # type: ignore
# pylint: enable=duplicate-code

from h2kvm.fixers.windows.registry.encoding import _close_best_effort, _detect_current_controlset
from h2kvm.fixers.windows.registry.io import detect_windows_hive, download_and_open_hive

logger = logging.getLogger(__name__)


@dataclass
class SQLServerInstance:  # pylint: disable=too-many-instance-attributes  # instance metadata model, one field per detected registry attribute
    """SQL Server instance metadata."""

    name: str  # Instance name (MSSQLSERVER for default)
    instance_id: str  # Registry instance ID
    version: Optional[str] = None  # SQL Server version (e.g., "15.0.2000.5")
    edition: Optional[str] = None  # Edition (Standard, Enterprise, etc.)
    data_path: Optional[str] = None  # Default data directory
    log_path: Optional[str] = None  # Default log directory
    backup_path: Optional[str] = None  # Default backup directory
    tcp_port: Optional[int] = None  # TCP port (default 1433)
    service_account: Optional[str] = None  # Service account name
    is_clustered: bool = False  # Always On failover cluster instance
    is_availability_group: bool = False  # Always On Availability Group enabled

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "instance_id": self.instance_id,
            "version": self.version,
            "edition": self.edition,
            "data_path": self.data_path,
            "log_path": self.log_path,
            "backup_path": self.backup_path,
            "tcp_port": self.tcp_port,
            "service_account": self.service_account,
            "is_clustered": self.is_clustered,
            "is_availability_group": self.is_availability_group,
        }


def detect_sql_server_instances(g: "guestfs.GuestFS", root: str) -> list[SQLServerInstance]:
    """Detect SQL Server installations from registry.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        List of detected SQL Server instances
    """
    logger.info("Detecting SQL Server instances")

    instances = []

    try:
        software_path = detect_windows_hive(g, root, "SOFTWARE")
        if not software_path:
            logger.warning("SOFTWARE hive not found")
            return instances

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SOFTWARE"
            hive = download_and_open_hive(logger, g, software_path, local_hive, write=False)

            try:
                # Check both native and WOW64 paths
                sql_base_paths = [
                    "Microsoft\\Microsoft SQL Server",
                    "Wow6432Node\\Microsoft\\Microsoft SQL Server",
                ]

                for base_path in sql_base_paths:
                    instances.extend(_scan_sql_instances(hive, base_path, g, root))

            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection; must not abort migration over one hive's quirk
        logger.exception("Failed to detect SQL Server instances: %s", e)
        logger.debug("SQL Server detection error", exc_info=True)

    logger.info("Found %d SQL Server instance(s)", len(instances))
    return instances


def _scan_sql_instances(  # pylint: disable=too-many-locals  # enumerates instance name/id pairs and decodes several registry values inline
    hive: "hivex.Hivex", base_path: str, g: "guestfs.GuestFS", root: str
) -> list[SQLServerInstance]:
    """Scan SQL Server instances from a specific registry path.

    Args:
        hive: Opened SOFTWARE hive
        base_path: Base path to SQL Server registry key
        g: GuestFS instance (for service account extraction)
        root: Windows root path

    Returns:
        List of detected instances
    """
    instances = []

    try:
        root_node = hive.root()
        base_node = hive.node_get_child(root_node, base_path)

        if not base_node:
            return instances

        # Get instance names from "Instance Names\SQL" key
        instance_names_path = "Instance Names\\SQL"
        instance_names_node = hive.node_get_child(base_node, instance_names_path)

        if not instance_names_node:
            return instances

        # Enumerate instance name -> instance ID mappings
        values = hive.node_values(instance_names_node)

        for value in values:
            try:
                instance_name = hive.value_key(value)
                instance_id_bytes = hive.value_value(value)

                # Decode instance ID
                instance_id = instance_id_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")

                if instance_id:
                    instance = _extract_instance_config(hive, base_node, instance_name, instance_id, g, root)
                    if instance:
                        instances.append(instance)

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-instance scan, must not abort the whole enumeration
                logger.debug("Error processing SQL instance: %s", e)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection; must not abort migration over one registry path's quirk
        logger.debug("Error scanning SQL instances at %s: %s", base_path, e)

    return instances


def _extract_instance_config(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches  # decodes several independent registry values (version, edition, paths, port)
    hive: "hivex.Hivex",
    base_node: int,
    instance_name: str,
    instance_id: str,
    g: "guestfs.GuestFS",
    root: str,
) -> Optional[SQLServerInstance]:
    """Extract configuration for a specific SQL Server instance.

    Args:
        hive: Hivex instance
        base_node: Base SQL Server node
        instance_name: Instance name
        instance_id: Instance ID from registry
        g: GuestFS instance
        root: Windows root path

    Returns:
        SQLServerInstance object or None
    """
    try:
        instance_path = f"{instance_id}\\MSSQLServer"
        instance_node = hive.node_get_child(base_node, instance_path)

        if not instance_node:
            return None

        instance = SQLServerInstance(
            name=instance_name,
            instance_id=instance_id,
        )

        # Extract version
        try:
            version_value = hive.node_get_value(instance_node, "CurrentVersion")
            if version_value:
                version_bytes = hive.value_value(version_value)
                instance.version = version_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort optional field decode; missing/malformed value should not abort extraction
            pass

        # Extract edition
        try:
            setup_path = f"{instance_id}\\Setup"
            setup_node = hive.node_get_child(base_node, setup_path)
            if setup_node:
                edition_value = hive.node_get_value(setup_node, "Edition")
                if edition_value:
                    edition_bytes = hive.value_value(edition_value)
                    instance.edition = edition_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort optional field decode; missing/malformed value should not abort extraction
            pass

        # Extract default paths
        for path_name, attr_name in [
            ("DefaultData", "data_path"),
            ("DefaultLog", "log_path"),
            ("BackupDirectory", "backup_path"),
        ]:
            try:
                value = hive.node_get_value(instance_node, path_name)
                if value:
                    path_bytes = hive.value_value(value)
                    path_str = path_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")
                    setattr(instance, attr_name, path_str)
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort optional field decode; missing/malformed value should not abort extraction
                pass

        # Extract TCP port from SuperSocketNetLib\Tcp
        try:
            tcp_path = f"{instance_id}\\MSSQLServer\\SuperSocketNetLib\\Tcp"
            tcp_node = hive.node_get_child(base_node, tcp_path)
            if tcp_node:
                port_value = hive.node_get_value(tcp_node, "TcpPort")
                if port_value:
                    port_bytes = hive.value_value(port_value)
                    port_str = port_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")
                    try:
                        instance.tcp_port = int(port_str)
                    except ValueError:
                        instance.tcp_port = 1433  # Default
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort optional field decode; missing/malformed value should not abort extraction
            instance.tcp_port = 1433  # Default

        # Extract service account from SYSTEM hive
        instance.service_account = _extract_service_account(g, root, instance_name)

        # Check for clustering/availability groups
        # Note: Full detection would require reading from SYSTEM hive Services
        # For now, we'll mark these as unknown and let the DBA verify

        return instance

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort extraction; must not abort the whole scan over one instance's quirk
        logger.debug("Error extracting instance config for %s: %s", instance_name, e)
        return None


def _extract_service_account(g: "guestfs.GuestFS", root: str, instance_name: str) -> Optional[str]:
    """Extract SQL Server service account from SYSTEM hive.

    Args:
        g: GuestFS instance
        root: Windows root path
        instance_name: SQL Server instance name

    Returns:
        Service account name or None
    """
    # pylint: disable=duplicate-code
    # reason: SYSTEM-hive open + current-controlset resolution mirrors the
    # equivalent step in appcompat/detector.py's license-service scan --
    # coincidentally similar shape (both read the Services subtree), but each
    # walks a different path and returns different data, so kept independent.
    try:
        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            return None

        # Determine service name
        service_name = "MSSQLSERVER" if instance_name == "MSSQLSERVER" else f"MSSQL${instance_name}"

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive = download_and_open_hive(logger, g, system_path, local_hive, write=False)

            try:
                root_node = hive.root()
                controlset_name = _detect_current_controlset(hive, root_node)
                service_path = f"{controlset_name}\\Services\\{service_name}"
                # pylint: enable=duplicate-code

                service_node = hive.node_get_child(root_node, service_path)
                if not service_node:
                    return None

                # Read ObjectName value (service account)
                account_value = hive.node_get_value(service_node, "ObjectName")
                if account_value:
                    account_bytes = hive.value_value(account_value)
                    return account_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")

            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort extraction; must not abort the whole scan over one instance's quirk
        logger.debug("Error extracting service account for %s: %s", instance_name, e)

    return None


def generate_sql_reconfiguration_script(
    instances: list[SQLServerInstance],
    old_hostname: Optional[str] = None,
    new_hostname: Optional[str] = None,
) -> str:
    """Generate T-SQL reconfiguration script for post-migration.

    Args:
        instances: List of detected SQL Server instances
        old_hostname: Old server hostname (if known)
        new_hostname: New server hostname (if known)

    Returns:
        T-SQL script as string
    """
    if not instances:
        return "-- No SQL Server instances detected\n"

    lines = [
        "-- SQL Server Post-Migration Reconfiguration Script",
        "-- Generated by h2kvm",
        "--",
        "-- IMPORTANT: Review and customize this script before execution",
        "-- Run with appropriate permissions (sysadmin role required)",
        "",
    ]

    for instance in instances:
        lines.extend(
            [
                "-- ================================================================",
                f"-- Instance: {instance.name}",
                f"-- Version: {instance.version or 'Unknown'}",
                f"-- Edition: {instance.edition or 'Unknown'}",
                "-- ================================================================",
                "",
            ]
        )

        # Hostname-dependent reconfigurations
        if old_hostname and new_hostname:
            lines.extend(
                [
                    "-- Update linked servers (if any)",
                    f"-- Replace '{old_hostname}' with '{new_hostname}' in linked server definitions",
                    "",
                    "-- List existing linked servers:",
                    "-- EXEC sp_linkedservers;",
                    "",
                    "-- Update linked server (example):",
                    f"-- EXEC sp_dropserver @server = '{old_hostname}', @droplogins = 'droplogins';",
                    f"-- EXEC sp_addlinkedserver @server = '{new_hostname}';",
                    "",
                ]
            )

            # Replication
            lines.extend(
                [
                    "-- Update replication (if configured)",
                    "-- Check replication status:",
                    "-- SELECT * FROM sys.servers WHERE is_distributor = 1 OR is_publisher = 1 OR is_subscriber = 1;",
                    "",
                    "-- Update distributor (example):",
                    f"-- EXEC sp_changedistpublisher @publisher = '{old_hostname}', ",
                    f"--      @property = 'working_directory', @value = '\\\\{new_hostname}\\repldata';",
                    "",
                ]
            )

            # Always On Availability Groups
            if instance.is_availability_group:
                lines.extend(
                    [
                        "-- Always On Availability Group reconfiguration",
                        "-- WARNING: This requires careful planning and may cause downtime",
                        "",
                        "-- Check AG status:",
                        "-- SELECT * FROM sys.availability_groups;",
                        "-- SELECT * FROM sys.dm_hadr_availability_replica_states;",
                        "",
                        "-- Update listener (example):",
                        "-- ALTER AVAILABILITY GROUP [AG_Name] ",
                        "--     MODIFY LISTENER 'AGListener' (WITH IP ((N'10.0.0.100', N'255.255.255.0')));",
                        "",
                    ]
                )

        # Service Broker
        lines.extend(
            [
                "-- Service Broker endpoint reconfiguration (if applicable)",
                "-- SELECT * FROM sys.service_broker_endpoints;",
                "",
            ]
        )

        # Database mail
        lines.extend(
            [
                "-- Database Mail profile update (if applicable)",
                "-- EXEC msdb.dbo.sysmail_help_profile_sp;",
                "-- EXEC msdb.dbo.sysmail_update_profile_sp ",
                "--     @profile_name = 'DefaultProfile',",
                f"--     @description = 'Updated for {new_hostname or 'new server'}';",
                "",
            ]
        )

        # Backup/restore paths
        if instance.backup_path:
            lines.extend(
                [
                    "-- Verify backup directory is accessible:",
                    f"-- EXEC xp_fileexist '{instance.backup_path}';",
                    "",
                ]
            )

        # SQL Agent jobs
        lines.extend(
            [
                "-- Review SQL Agent jobs for hardcoded server names/paths",
                "-- SELECT job_id, name, enabled FROM msdb.dbo.sysjobs;",
                "",
            ]
        )

        lines.extend(["", ""])

    # General recommendations
    lines.extend(
        [
            "-- ================================================================",
            "-- General Post-Migration Tasks",
            "-- ================================================================",
            "",
            "-- 1. Update statistics on all databases",
            "-- EXEC sp_updatestats;",
            "",
            "-- 2. Rebuild indexes (if needed)",
            "-- EXEC sp_MSforeachdb 'USE [?]; EXEC sp_MSforeachtable @command1=\"DBCC DBREINDEX (''''?'''')\"';",
            "",
            "-- 3. Update compatibility level (if upgraded SQL Server version)",
            "-- ALTER DATABASE [DatabaseName] SET COMPATIBILITY_LEVEL = 150;  -- SQL Server 2019",
            "",
            "-- 4. Verify logins and permissions",
            "-- EXEC sp_helplogins;",
            "",
            "-- 5. Check for orphaned users",
            "-- EXEC sp_change_users_login 'Report';",
            "",
            "-- 6. Test database connectivity from applications",
            "",
            "-- END OF SCRIPT",
        ]
    )

    return "\n".join(lines)
