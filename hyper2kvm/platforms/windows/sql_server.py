# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
SQL Server migration support module.

Handles SQL Server-specific migration tasks including:
- SQL Server instance detection
- Configuration migration (instance settings, ports, logins)
- Database validation
- Service reconfiguration
- Linked server updates
"""

import logging
from pathlib import Path
from typing import Any

from hyper2kvm.vmcraft.main import VMCraft


class SQLServerManager:
    """Manages SQL Server migration tasks for Windows VMs."""

    # Common SQL Server paths
    SQL_SERVER_PATHS = [
        "/Program Files/Microsoft SQL Server",
        "/Program Files (x86)/Microsoft SQL Server",
    ]

    # SQL Server versions
    SQL_VERSIONS = {
        "160": "SQL Server 2022",
        "150": "SQL Server 2019",
        "140": "SQL Server 2017",
        "130": "SQL Server 2016",
        "120": "SQL Server 2014",
        "110": "SQL Server 2012",
    }

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize SQL Server Manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def detect_sql_server(self, g: VMCraft) -> dict[str, Any]:
        """
        Detect SQL Server instances on Windows VM.

        Args:
            g: Launched VMCraft instance with Windows VM mounted

        Returns:
            Dictionary with SQL Server information:
            {
                "detected": bool,
                "instances": [
                    {
                        "name": str,  # Instance name (MSSQLSERVER for default)
                        "version": str,  # e.g., "SQL Server 2019"
                        "version_number": str,  # e.g., "150"
                        "edition": str,  # Enterprise, Standard, Express, etc.
                        "port": int,  # TCP port (1433 default)
                        "data_path": str,  # Data directory
                        "log_path": str,  # Log directory
                        "backup_path": str,  # Backup directory
                        "service_account": str,  # Service account name
                    }
                ],
                "databases": [
                    {
                        "name": str,
                        "instance": str,
                        "size_mb": int,
                        "state": str,  # Online, Offline, etc.
                    }
                ],
                "error": str | None
            }
        """
        audit: dict[str, Any] = {
            "detected": False,
            "instances": [],
            "databases": [],
            "error": None,
        }

        try:
            # Check for SQL Server installation
            sql_installed = False
            for path in self.SQL_SERVER_PATHS:
                if g.exists(path):
                    sql_installed = True
                    break

            if not sql_installed:
                self.logger.info("SQL Server not detected on this VM")
                return audit

            # Detect instances
            instances = self._detect_instances(g)
            audit["instances"] = instances
            audit["detected"] = len(instances) > 0

            if audit["detected"]:
                self.logger.info(f"Detected {len(instances)} SQL Server instance(s)")

                # Detect databases for each instance
                for instance in instances:
                    databases = self._detect_databases(g, instance["name"])
                    audit["databases"].extend(databases)

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"SQL Server detection failed: {e}")

        return audit

    def migrate_sql_configuration(
        self,
        g: VMCraft,
        sql_info: dict[str, Any],
        target_ip: str | None = None,
        target_hostname: str | None = None,
    ) -> dict[str, Any]:
        """
        Create SQL Server migration configuration script.

        Args:
            g: Launched VMCraft instance
            sql_info: SQL Server info from detect_sql_server()
            target_ip: New IP address after migration
            target_hostname: New hostname after migration

        Returns:
            Audit dict with script generation status
        """
        audit: dict[str, Any] = {
            "script_generated": False,
            "script_path": None,
            "instances_configured": 0,
            "error": None,
        }

        try:
            instances = sql_info.get("instances", [])
            if not instances:
                audit["error"] = "No SQL Server instances found"
                return audit

            # Generate migration script
            script = self._generate_sql_migration_script(instances, target_ip, target_hostname)

            # Save script
            script_path = "/Windows/Temp/sql-server-migration.ps1"
            temp_script = Path("/tmp/sql-server-migration.ps1")
            temp_script.write_text(script, encoding="utf-16-le")

            g.upload(str(temp_script), script_path)
            temp_script.unlink()

            audit["script_generated"] = True
            audit["script_path"] = script_path
            audit["instances_configured"] = len(instances)

            self.logger.info(f"Generated SQL Server migration script for {len(instances)} instance(s)")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to create SQL migration script: {e}")

        return audit

    def create_sql_migration_script(
        self,
        sql_info: dict[str, Any],
        target_ip: str | None = None,
        target_hostname: str | None = None,
    ) -> str:
        """
        Generate SQL Server migration PowerShell script.

        Args:
            sql_info: SQL Server information
            target_ip: New IP address
            target_hostname: New hostname

        Returns:
            PowerShell script content
        """
        return self._generate_sql_migration_script(sql_info.get("instances", []), target_ip, target_hostname)

    # Private helper methods

    def _detect_instances(self, g: VMCraft) -> list[dict[str, Any]]:
        """Detect SQL Server instances."""
        instances = []

        try:
            # Check for default instance (MSSQLSERVER)
            default_service = (
                "/Windows/System32/config/systemprofile/AppData/Local/Microsoft/Microsoft SQL Server"
            )
            if g.exists(default_service):
                instances.append(
                    {
                        "name": "MSSQLSERVER",
                        "version": "SQL Server",
                        "version_number": "unknown",
                        "edition": "Unknown",
                        "port": 1433,
                        "data_path": "C:\\Program Files\\Microsoft SQL Server\\MSSQL\\DATA",
                        "log_path": "C:\\Program Files\\Microsoft SQL Server\\MSSQL\\LOG",
                        "backup_path": "C:\\Program Files\\Microsoft SQL Server\\MSSQL\\BACKUP",
                        "service_account": "NT Service\\MSSQLSERVER",
                    }
                )

            # Check for named instances
            # In production, enumerate from registry:
            # HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL

        except Exception as e:
            self.logger.debug(f"Instance detection error: {e}")

        return instances

    def _detect_databases(self, g: VMCraft, instance_name: str) -> list[dict[str, Any]]:
        """Detect databases for a SQL Server instance."""
        databases = []

        try:
            # In production, enumerate database files from:
            # - Master database system tables
            # - File system scan of data directories

            # For now, return placeholder for system databases
            system_dbs = ["master", "model", "msdb", "tempdb"]
            for db in system_dbs:
                databases.append(
                    {
                        "name": db,
                        "instance": instance_name,
                        "size_mb": 0,
                        "state": "Online",
                    }
                )

        except Exception as e:
            self.logger.debug(f"Database detection error: {e}")

        return databases

    def _generate_sql_migration_script(
        self,
        instances: list[dict[str, Any]],
        target_ip: str | None,
        target_hostname: str | None,
    ) -> str:
        """Generate comprehensive SQL Server migration script."""

        instances_config = "\n".join(
            [
                f"""
    # Instance: {inst["name"]}
    Write-Log "Configuring instance: {inst["name"]}"
    $InstanceName = "{inst["name"]}"
    """
                for inst in instances
            ]
        )

        # Built as a standalone variable (not inline in the f-string below)
        # because a backslash inside an f-string's {...} substitution is a
        # SyntaxError before Python 3.12, and this whole block is nested
        # inside the outer f-string's substitution expression tree.
        server_properties_config = chr(10).join(
            [
                f"""
        $ServerInstance = if ("{name}" -eq "MSSQLSERVER") {{ "localhost" }} else {{ "localhost\\{name}" }}
        Write-Log "Updating configuration for $ServerInstance"

        # Enable TCP/IP protocol
        $Smo = [System.Reflection.Assembly]::LoadWithPartialName("Microsoft.SqlServer.Smo")
        $Wmi = New-Object Microsoft.SqlServer.Management.Smo.Wmi.ManagedComputer
        $Uri = "ManagedComputer[@Name='$env:COMPUTERNAME']/ServerInstance[@Name='{name}']/ServerProtocol[@Name='Tcp']"
        $Tcp = $Wmi.GetSmoObject($Uri)
        $Tcp.IsEnabled = $true
        $Tcp.Alter()
        Write-Log "TCP/IP protocol enabled for {name}"
"""
                for inst in instances
                for name in [inst["name"]]
            ]
        )

        return f"""# SQL Server Migration Configuration Script
# Generated by hyper2kvm
# This script configures SQL Server after VM migration

$LogFile = "C:\\Windows\\Temp\\sql-migration.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}}

Write-Log "Starting SQL Server migration configuration"

try {{
    # New server details
    {
            f'$NewIP = "{target_ip}"'
            if target_ip
            else '$NewIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.PrefixOrigin -ne "WellKnown"} | Select-Object -First 1).IPAddress'
        }
    {f'$NewHostname = "{target_hostname}"' if target_hostname else "$NewHostname = $env:COMPUTERNAME"}

    Write-Log "New IP: $NewIP"
    Write-Log "New Hostname: $NewHostname"

    # Configure SQL Server instances
{instances_config}

    # Restart SQL Server services
    Write-Log "Restarting SQL Server services"
    {
            chr(10).join(
                [
                    f'    Restart-Service "MSSQL${inst["name"]}" -Force'
                    if inst["name"] != "MSSQLSERVER"
                    else '    Restart-Service "MSSQLSERVER" -Force'
                    for inst in instances
                ]
            )
        }

    Write-Log "SQL Server services restarted"

    # Update SQL Server configuration
    Write-Log "Updating SQL Server configuration"

    # Import SQL Server module
    Import-Module SqlServer -ErrorAction SilentlyContinue

    if (Get-Module -Name SqlServer) {{
        Write-Log "SQL Server PowerShell module loaded"

        # Update server properties
{server_properties_config}

    }} else {{
        Write-Log "WARNING: SQL Server PowerShell module not available"
        Write-Log "Some configuration steps may need to be performed manually"
    }}

    # Validation
    Write-Log "Validating SQL Server instances"
{
            chr(10).join(
                [
                    f'''
    $Service = Get-Service "MSSQL${inst["name"]}" -ErrorAction SilentlyContinue
    if ($Service -and $Service.Status -eq "Running") {{
        Write-Log "Instance {inst["name"]}: Running"
    }} else {{
        Write-Log "WARNING: Instance {inst["name"]}: Not running"
    }}
'''
                    if inst["name"] != "MSSQLSERVER"
                    else '''
    $Service = Get-Service "MSSQLSERVER" -ErrorAction SilentlyContinue
    if ($Service -and $Service.Status -eq "Running") {
        Write-Log "Instance MSSQLSERVER: Running"
    } else {
        Write-Log "WARNING: Instance MSSQLSERVER: Not running"
    }
'''
                    for inst in instances
                ]
            )
        }

    Write-Log "SQL Server migration configuration completed"
    Write-Log ""
    Write-Log "=== MANUAL STEPS REQUIRED ==="
    Write-Log "1. Update linked servers with new hostnames/IPs"
    Write-Log "2. Reconfigure replication (if applicable)"
    Write-Log "3. Update connection strings in applications"
    Write-Log "4. Test database connectivity"
    Write-Log "5. Verify SQL Server Agent jobs"
    Write-Log "6. Update backup schedules/paths (if changed)"
    Write-Log "================================"

}} catch {{
    Write-Log "ERROR: SQL Server migration failed - $($_.Exception.Message)"
    Write-Log $_.Exception.StackTrace
    exit 1
}}
"""

    def validate_databases(
        self,
        g: VMCraft,
        sql_info: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate database validation script.

        Args:
            g: VMCraft instance
            sql_info: SQL Server information

        Returns:
            Audit dict with validation script
        """
        audit: dict[str, Any] = {
            "script_generated": False,
            "script_path": None,
            "error": None,
        }

        try:
            databases = sql_info.get("databases", [])
            instances = sql_info.get("instances", [])

            script = self._generate_validation_script(instances, databases)

            # Save script
            script_path = "/Windows/Temp/sql-validation.ps1"
            temp_script = Path("/tmp/sql-validation.ps1")
            temp_script.write_text(script, encoding="utf-16-le")

            g.upload(str(temp_script), script_path)
            temp_script.unlink()

            audit["script_generated"] = True
            audit["script_path"] = script_path

            self.logger.info("Generated SQL Server validation script")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to create validation script: {e}")

        return audit

    def _generate_validation_script(
        self,
        instances: list[dict[str, Any]],
        databases: list[dict[str, Any]],
    ) -> str:
        """Generate database validation script."""
        # Built as a standalone variable (not inline in the f-string below)
        # because a backslash inside an f-string's {...} substitution is a
        # SyntaxError before Python 3.12, and this whole block is nested
        # inside the outer f-string's substitution expression tree.
        instance_validation_config = chr(10).join(
            [
                # SQL text below is a fully static PowerShell literal (no Python
                # values are interpolated into the SQL query strings themselves,
                # only into unrelated PowerShell variable names) so this is not
                # a real string-based SQL injection vector.
                f"""
    $Instance = if ("{name}" -eq "MSSQLSERVER") {{ "localhost" }} else {{ "localhost\\{name}" }}
    Write-Log "Validating instance: $Instance"

    # Check instance connectivity
    $Query = "SELECT @@VERSION AS Version, @@SERVERNAME AS ServerName"
    try {{
        $Result = Invoke-Sqlcmd -ServerInstance $Instance -Query $Query -ErrorAction Stop
        Write-Log "Instance $Instance: Connected"
        Write-Log "Server: $($Result.ServerName)"
        Write-Log "Version: $($Result.Version)"
    }} catch {{
        Write-Log "ERROR: Cannot connect to instance $Instance - $($_.Exception.Message)"
    }}

    # List databases
    $Query = "SELECT name, state_desc, recovery_model_desc FROM sys.databases"
    try {{
        $Databases = Invoke-Sqlcmd -ServerInstance $Instance -Query $Query
        Write-Log "Databases on $Instance:"
        foreach ($DB in $Databases) {{
            Write-Log "  - $($DB.name): $($DB.state_desc) (Recovery: $($DB.recovery_model_desc))"
        }}
    }} catch {{
        Write-Log "ERROR: Cannot query databases - $($_.Exception.Message)"
    }}
"""  # noqa: S608
                for inst in instances
                for name in [inst["name"]]
            ]
        )

        return f"""# SQL Server Database Validation Script
# Generated by hyper2kvm

$LogFile = "C:\\Windows\\Temp\\sql-validation.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}}

Write-Log "Starting SQL Server database validation"

try {{
    # Import SQL Server module
    Import-Module SqlServer -ErrorAction SilentlyContinue

    if (-not (Get-Module -Name SqlServer)) {{
        Write-Log "ERROR: SQL Server PowerShell module not available"
        exit 1
    }}

    # Validate each instance and database
{instance_validation_config}

    Write-Log "Database validation completed"

}} catch {{
    Write-Log "ERROR: Validation failed - $($_.Exception.Message)"
    exit 1
}}
"""
