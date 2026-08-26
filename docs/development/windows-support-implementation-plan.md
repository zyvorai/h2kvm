# Advanced Windows Support - Implementation Plan

**Feature**: Comprehensive Windows Migration Enhancement
**Priority**: P0 (High Priority)
**Timeline**: 4-6 months
**Complexity**: High
**Business Impact**: Very High (unlocks 70% of enterprise migrations)

---

## Executive Summary

Transform hyper2kvm into the premier Windows VM migration tool by adding enterprise-grade Windows-specific features:
- Automated license management and reactivation
- Active Directory domain integration
- Application compatibility detection and fixes
- SQL Server/Exchange Server support
- Windows Update integration for VirtIO drivers
- Performance optimizations specific to Windows on KVM

**Target Market**: Enterprise Windows Server migrations (SQL Server, Exchange, IIS, SharePoint)

---

## Feature Breakdown

### 1. Automated License Reactivation (4-5 weeks)

#### Current Gap
- No license handling
- Users must manually reactivate Windows after migration
- Volume licensing scenarios not addressed

#### Proposed Solution

**Phase 1A: License Detection (Week 1-2)**

Detect and extract Windows license information:

```python
# hyper2kvm/fixers/windows/license_mgr.py

class WindowsLicenseManager:
    """Manages Windows licensing during migration."""

    def detect_license_type(self, g: VMCraft) -> dict:
        """
        Detect Windows license type and status.

        Returns:
            {
                'type': 'OEM' | 'Retail' | 'Volume' | 'MAK' | 'KMS',
                'edition': 'Standard' | 'Datacenter' | 'Enterprise',
                'key_partial': 'XXXXX-XXXXX-XXXXX-XXXXX-XXXXX' (last 5 chars),
                'activation_status': 'Licensed' | 'Grace' | 'Unlicensed',
                'kms_server': '192.168.1.100' (if KMS),
                'rearm_count': 3
            }
        """
        # Query via WMI through registry
        license_info = {}

        # Read from SOFTWARE\Microsoft\Windows NT\CurrentVersion
        reg_path = "/Windows/System32/config/SOFTWARE"

        # slmgr.vbs equivalent - read licensing info
        # SoftwareLicensingService WMI class data stored in registry

        # Detect license type from registry markers
        if self._is_kms_activated(g):
            license_info['type'] = 'KMS'
            license_info['kms_server'] = self._get_kms_server(g)
        elif self._is_mak_key(g):
            license_info['type'] = 'MAK'
        elif self._is_oem_license(g):
            license_info['type'] = 'OEM'
        else:
            license_info['type'] = 'Retail'

        # Get product key (last 5 chars only for security)
        license_info['key_partial'] = self._get_partial_key(g)

        # Check activation status
        license_info['activation_status'] = self._get_activation_status(g)

        # Get rearm count (grace period resets available)
        license_info['rearm_count'] = self._get_rearm_count(g)

        return license_info

    def _is_kms_activated(self, g: VMCraft) -> bool:
        """Check if Windows is KMS-activated."""
        # Check registry: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform
        # KeyManagementServiceMachine value
        try:
            key_path = "Microsoft\\Windows NT\\CurrentVersion\\SoftwareProtectionPlatform"
            kms_machine = g.reg_get(f"HKLM\\SOFTWARE\\{key_path}", "KeyManagementServiceMachine")
            return bool(kms_machine)
        except:
            return False

    def _get_kms_server(self, g: VMCraft) -> str | None:
        """Get KMS server address from registry."""
        try:
            key_path = "Microsoft\\Windows NT\\CurrentVersion\\SoftwareProtectionPlatform"
            return g.reg_get(f"HKLM\\SOFTWARE\\{key_path}", "KeyManagementServiceMachine")
        except:
            return None

    def _get_partial_key(self, g: VMCraft) -> str:
        """Get last 5 characters of product key (for reference)."""
        # Read from registry (encoded)
        # HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\DigitalProductId
        # Decode and return last 5 chars (safe to store)
        try:
            product_id = g.reg_get("HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion", "ProductId")
            # ProductId format: XXXXX-XXX-XXXXXXX-XXXXX
            # Return last segment
            return product_id.split('-')[-1] if product_id else "UNKNOWN"
        except:
            return "UNKNOWN"
```

**Phase 1B: Reactivation Strategies (Week 3-4)**

Implement post-migration reactivation:

```python
class WindowsLicenseManager:

    def create_reactivation_script(self, license_info: dict, output_path: str):
        """
        Create firstboot script for Windows reactivation.

        Strategy depends on license type:
        - KMS: Reconnect to KMS server
        - MAK: Online activation (automatic)
        - OEM/Retail: Manual intervention required
        """
        script_content = self._generate_powershell_reactivation(license_info)

        # Write to RunOnce registry key for execution at first boot
        # Or create as Scheduled Task

    def _generate_powershell_reactivation(self, license_info: dict) -> str:
        """Generate PowerShell script for automatic reactivation."""

        if license_info['type'] == 'KMS':
            # KMS reactivation script
            script = f"""
# KMS Reactivation Script
# Generated by hyper2kvm

$kmsServer = "{license_info.get('kms_server', 'kms.company.local')}"
$kmsPort = 1688

Write-Host "Configuring KMS client..."

# Set KMS server
cscript //nologo C:\\Windows\\System32\\slmgr.vbs /skms "$kmsServer:$kmsPort"

# Activate
Write-Host "Activating Windows via KMS..."
cscript //nologo C:\\Windows\\System32\\slmgr.vbs /ato

# Verify activation
$activationStatus = cscript //nologo C:\\Windows\\System32\\slmgr.vbs /dli
Write-Host $activationStatus

if ($LASTEXITCODE -eq 0) {{
    Write-Host "✓ Windows activated successfully via KMS"
}} else {{
    Write-Host "⚠ Activation failed. Manual intervention required."
    Write-Host "Run: slmgr /ato"
}}
"""
        elif license_info['type'] == 'MAK':
            # MAK online activation
            script = """
# MAK Reactivation Script
# Generated by hyper2kvm

Write-Host "Attempting MAK activation..."

# Trigger online activation
cscript //nologo C:\\Windows\\System32\\slmgr.vbs /ato

# Check status
$activationStatus = cscript //nologo C:\\Windows\\System32\\slmgr.vbs /dli

if ($activationStatus -match "Licensed") {
    Write-Host "✓ Windows activated successfully"
} else {
    Write-Host "⚠ Activation may require manual intervention"
    Write-Host "If activation fails, run: slmgr /ato"
}
"""
        else:
            # OEM/Retail - guidance only
            script = f"""
# License Reactivation Guidance
# License Type: {license_info['type']}

Write-Host "============================================"
Write-Host "Windows License Reactivation Required"
Write-Host "============================================"
Write-Host ""
Write-Host "License Type: {license_info['type']}"
Write-Host "Product Key (last 5): {license_info.get('key_partial', 'N/A')}"
Write-Host ""
Write-Host "Hardware changes due to migration require reactivation."
Write-Host ""
Write-Host "To reactivate:"
Write-Host "1. Press Win+R, type 'slui.exe', press Enter"
Write-Host "2. Follow the activation wizard"
Write-Host "3. Or run: slmgr /ato"
Write-Host ""
Write-Host "If online activation fails, use phone activation:"
Write-Host "  slui.exe 4"
Write-Host ""
Write-Host "============================================"

# Try automatic activation anyway
cscript //nologo C:\\Windows\\System32\\slmgr.vbs /ato
"""

        return script

    def inject_reactivation_script(self, g: VMCraft, script: str):
        """
        Inject reactivation script into Windows VM.

        Methods:
        1. RunOnce registry key (runs once at next logon)
        2. Scheduled Task (runs at startup)
        3. Startup folder script
        """

        # Method 1: RunOnce registry (most reliable)
        script_path = "C:\\Windows\\Temp\\reactivate_license.ps1"

        # Write script to temp directory
        g.write(script_path, script)

        # Add RunOnce registry entry
        runonce_cmd = f"powershell.exe -ExecutionPolicy Bypass -File {script_path}"

        # HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnce
        g.reg_set(
            "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
            "ReactivateLicense",
            runonce_cmd
        )

        # Method 2: Also create scheduled task (backup)
        self._create_scheduled_task(g, script_path)
```

**Phase 1C: Volume Licensing Support (Week 5)**

Handle enterprise volume licensing scenarios:

```python
class VolumeLicensingManager:
    """Handle Windows Volume Licensing (VAMT, KMS, MAK)."""

    def handle_volume_activation(self, g: VMCraft, license_info: dict):
        """
        Configure volume activation for enterprise environments.

        Supports:
        - KMS (Key Management Service)
        - MAK (Multiple Activation Key)
        - VAMT (Volume Activation Management Tool)
        """

        if license_info['type'] == 'KMS':
            self._configure_kms_client(g, license_info['kms_server'])
        elif license_info['type'] == 'MAK':
            self._configure_mak_client(g)

    def _configure_kms_client(self, g: VMCraft, kms_server: str):
        """Configure KMS client settings."""

        # Set KMS server in registry
        # HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform

        g.reg_set(
            "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SoftwareProtectionPlatform",
            "KeyManagementServiceMachine",
            kms_server
        )

        g.reg_set(
            "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SoftwareProtectionPlatform",
            "KeyManagementServicePort",
            1688,  # DWORD
            reg_type="dword"
        )

        # Set KMS client FQDN (if needed)
        # This allows KMS to track activations by machine

        logger.info(f"✓ Configured KMS client: {kms_server}")
```

---

### 2. Active Directory Integration (3-4 weeks)

#### Current Gap
- Domain-joined VMs break after migration (SID mismatch, computer object issues)
- Manual domain rejoin required
- No automated cleanup of old computer objects

#### Proposed Solution

**Phase 2A: Domain State Detection (Week 1)**

```python
# hyper2kvm/fixers/windows/ad_mgr.py

class ActiveDirectoryManager:
    """Manage Active Directory integration during Windows VM migration."""

    def detect_domain_membership(self, g: VMCraft) -> dict:
        """
        Detect if Windows is domain-joined and gather AD information.

        Returns:
            {
                'is_domain_joined': True/False,
                'domain_name': 'company.local',
                'computer_name': 'SERVER01',
                'domain_controller': 'dc01.company.local',
                'domain_sid': 'S-1-5-21-...',
                'machine_sid': 'S-1-5-21-...',
                'ou_path': 'OU=Servers,DC=company,DC=local'
            }
        """

        domain_info = {
            'is_domain_joined': False
        }

        # Check registry for domain membership
        # HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Domain
        try:
            domain = g.reg_get(
                "HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters",
                "Domain"
            )

            if domain:
                domain_info['is_domain_joined'] = True
                domain_info['domain_name'] = domain

                # Get computer name
                computer_name = g.reg_get(
                    "HKLM\\SYSTEM\\CurrentControlSet\\Control\\ComputerName\\ActiveComputerName",
                    "ComputerName"
                )
                domain_info['computer_name'] = computer_name

                # Get domain SID
                domain_sid = self._get_domain_sid(g)
                domain_info['domain_sid'] = domain_sid

                # Get machine SID
                machine_sid = self._get_machine_sid(g)
                domain_info['machine_sid'] = machine_sid

        except Exception as e:
            logger.debug(f"Not domain-joined: {e}")

        return domain_info

    def _get_machine_sid(self, g: VMCraft) -> str:
        """Extract machine SID from SAM database."""
        # Machine SID is in SAM\SAM\Domains\Account\V key
        # This is binary data that needs parsing

        # Alternatively, read from SECURITY hive
        try:
            # Read from registry
            # HKLM\SECURITY\SAM\Domains\Account (requires SYSTEM privileges)
            pass
        except:
            return None
```

**Phase 2B: Domain Rejoin Automation (Week 2-3)**

```python
class ActiveDirectoryManager:

    def create_domain_rejoin_script(self, domain_info: dict, credentials: dict = None) -> str:
        """
        Generate PowerShell script for automatic domain rejoin.

        Args:
            domain_info: Domain membership information
            credentials: Optional domain admin credentials for automation
                        (or None for manual rejoin)

        Returns:
            PowerShell script content
        """

        domain = domain_info['domain_name']
        computer_name = domain_info['computer_name']

        if credentials:
            # Automated rejoin with credentials
            username = credentials['username']
            password = credentials['password']  # Should be encrypted/from vault

            script = f"""
# Automated Domain Rejoin Script
# Generated by hyper2kvm
# Domain: {domain}
# Computer: {computer_name}

$domain = "{domain}"
$computerName = "{computer_name}"
$username = "{username}"
$password = ConvertTo-SecureString "{password}" -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($username, $password)

Write-Host "Rejoining domain: $domain..."

try {{
    # Remove from domain first (if still member)
    Remove-Computer -UnjoinDomainCredential $credential -PassThru -Force -ErrorAction SilentlyContinue

    # Wait for removal to complete
    Start-Sleep -Seconds 5

    # Rejoin domain
    Add-Computer -DomainName $domain -Credential $credential -Force -Options JoinWithNewName,AccountCreate

    Write-Host "✓ Successfully rejoined domain: $domain"
    Write-Host "⚠ Reboot required to complete domain join"

    # Schedule reboot
    Write-Host "Reboot scheduled in 60 seconds..."
    shutdown /r /t 60 /c "Reboot required to complete domain join"

}} catch {{
    Write-Host "✗ Domain rejoin failed: $_"
    Write-Host "Manual intervention required"
}}
"""
        else:
            # Manual rejoin guidance
            script = f"""
# Domain Rejoin Guidance
# Generated by hyper2kvm
# Domain: {domain}
# Computer: {computer_name}

Write-Host "============================================"
Write-Host "Active Directory Rejoin Required"
Write-Host "============================================"
Write-Host ""
Write-Host "Domain: {domain}"
Write-Host "Computer: {computer_name}"
Write-Host ""
Write-Host "Hardware changes due to migration require domain rejoin."
Write-Host ""
Write-Host "To rejoin the domain:"
Write-Host "1. Log in as local administrator"
Write-Host "2. Open System Properties (sysdm.cpl)"
Write-Host "3. Click 'Change' next to computer name"
Write-Host "4. Select 'Domain' and enter: {domain}"
Write-Host "5. Provide domain administrator credentials"
Write-Host "6. Reboot when prompted"
Write-Host ""
Write-Host "Or use PowerShell:"
Write-Host "  Add-Computer -DomainName {domain} -Credential (Get-Credential)"
Write-Host ""
Write-Host "============================================"
"""

        return script

    def cleanup_old_computer_object(self, domain_info: dict, credentials: dict):
        """
        Clean up old AD computer object after migration.

        This prevents SID conflicts and stale computer objects.

        Requires domain admin credentials.
        """

        # Use LDAP/PowerShell to remove old computer object
        # This runs on the host (not in guest)

        computer_name = domain_info['computer_name']
        domain = domain_info['domain_name']

        cleanup_script = f"""
# Run this on a domain controller or domain-joined machine
# Removes stale computer object for: {computer_name}

Import-Module ActiveDirectory

$computerName = "{computer_name}"

try {{
    # Find computer object
    $computer = Get-ADComputer -Identity $computerName -ErrorAction Stop

    Write-Host "Found computer object: $computerName"
    Write-Host "DN: $($computer.DistinguishedName)"

    # Confirm before deleting
    $confirm = Read-Host "Delete this computer object? (yes/no)"

    if ($confirm -eq "yes") {{
        Remove-ADComputer -Identity $computerName -Confirm:$false
        Write-Host "✓ Computer object deleted: $computerName"
        Write-Host "Machine can now rejoin domain with fresh identity"
    }} else {{
        Write-Host "Cancelled"
    }}

}} catch {{
    Write-Host "Computer object not found or error: $_"
}}
"""

        return cleanup_script
```

**Phase 2C: SID Regeneration (Week 4)**

```python
class ActiveDirectoryManager:

    def regenerate_machine_sid(self, g: VMCraft):
        """
        Regenerate machine SID to avoid conflicts.

        Uses sysprep or similar mechanism.

        WARNING: This can break some applications.
        """

        # Option 1: Sysprep (generalize)
        # Creates new SID but requires Windows reactivation

        # Option 2: NewSID (deprecated by Microsoft)
        # No longer recommended

        # Option 3: Manual SID regeneration (complex, risky)

        # Recommended: Use sysprep in generalize mode
        sysprep_script = """
# SID Regeneration via Sysprep
# WARNING: This will generalize the Windows installation
# Requires reactivation and reconfiguration

$sysprepPath = "C:\\Windows\\System32\\Sysprep\\sysprep.exe"

Write-Host "⚠ WARNING: This will generalize the Windows installation"
Write-Host "All user profiles and settings will be removed"
Write-Host "Windows will require reactivation"
Write-Host ""

$confirm = Read-Host "Continue with sysprep? (yes/no)"

if ($confirm -eq "yes") {
    # Run sysprep in generalize mode
    & $sysprepPath /generalize /oobe /shutdown

    Write-Host "Sysprep initiated. System will shutdown."
} else {
    Write-Host "Cancelled"
}
"""

        return sysprep_script
```

---

### 3. SQL Server Migration Support (4-5 weeks)

#### Current Gap
- SQL Server instances break after migration
- Database file paths may change
- SQL Server services fail to start
- Network configuration issues

#### Proposed Solution

**Phase 3A: SQL Server Detection (Week 1)**

```python
# hyper2kvm/fixers/windows/sql_server_mgr.py

class SQLServerManager:
    """Manage SQL Server migrations."""

    def detect_sql_server(self, g: VMCraft) -> dict:
        """
        Detect SQL Server installations.

        Returns:
            {
                'installed': True/False,
                'instances': [
                    {
                        'name': 'MSSQLSERVER' (default) or 'INSTANCE1',
                        'version': '2019' | '2017' | '2016' | '2014',
                        'edition': 'Standard' | 'Enterprise' | 'Express',
                        'service_name': 'MSSQLSERVER',
                        'data_path': 'C:\\Program Files\\Microsoft SQL Server\\...',
                        'log_path': '...',
                        'tempdb_path': '...',
                        'port': 1433,
                        'tcp_enabled': True/False
                    }
                ],
                'agent_installed': True/False,
                'ssrs_installed': True/False,
                'ssas_installed': True/False,
                'ssis_installed': True/False
            }
        """

        sql_info = {
            'installed': False,
            'instances': []
        }

        # Check for SQL Server installation
        # Registry: HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL

        try:
            instances_key = "HKLM\\SOFTWARE\\Microsoft\\Microsoft SQL Server\\Instance Names\\SQL"
            instance_names = g.reg_list_keys(instances_key)

            if instance_names:
                sql_info['installed'] = True

                for instance_name in instance_names:
                    instance_data = self._get_instance_details(g, instance_name)
                    sql_info['instances'].append(instance_data)

            # Check for SQL Server Agent
            sql_info['agent_installed'] = self._is_service_installed(g, "SQLSERVERAGENT")

            # Check for SSRS, SSAS, SSIS
            sql_info['ssrs_installed'] = self._is_service_installed(g, "ReportServer")
            sql_info['ssas_installed'] = self._is_service_installed(g, "MSOLAP")
            sql_info['ssis_installed'] = self._is_service_installed(g, "MsDtsServer")

        except Exception as e:
            logger.debug(f"SQL Server not detected: {e}")

        return sql_info

    def _get_instance_details(self, g: VMCraft, instance_name: str) -> dict:
        """Get detailed information about SQL Server instance."""

        # Get instance registry key
        # HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\<InstanceID>\Setup

        instance_info = {
            'name': instance_name
        }

        # Get version
        version = g.reg_get(f"...\\{instance_name}\\Setup", "Version")
        instance_info['version'] = self._parse_sql_version(version)

        # Get edition
        edition = g.reg_get(f"...\\{instance_name}\\Setup", "Edition")
        instance_info['edition'] = edition

        # Get data paths
        data_path = g.reg_get(f"...\\{instance_name}\\Setup", "SQLDataRoot")
        instance_info['data_path'] = data_path

        # Get port (from SQL Server Configuration Manager settings)
        # Registry: HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\<InstanceID>\MSSQLServer\SuperSocketNetLib\Tcp
        port = g.reg_get(f"...\\{instance_name}\\MSSQLServer\\SuperSocketNetLib\\Tcp", "TcpPort")
        instance_info['port'] = int(port) if port else 1433

        return instance_info
```

**Phase 3B: SQL Server Configuration Migration (Week 2-3)**

```python
class SQLServerManager:

    def migrate_sql_configuration(self, g: VMCraft, sql_info: dict):
        """
        Migrate SQL Server configuration to new VM.

        Handles:
        - Network configuration (TCP/IP, named pipes)
        - Service accounts
        - Database file paths
        - Linked servers
        - SQL Server Agent jobs
        """

        for instance in sql_info['instances']:
            self._update_network_config(g, instance)
            self._verify_file_paths(g, instance)

    def _update_network_config(self, g: VMCraft, instance: dict):
        """Update SQL Server network configuration."""

        # Ensure TCP/IP is enabled
        # Enable named pipes if needed
        # Set correct port

        # Registry updates for network protocols
        instance_name = instance['name']

        # Enable TCP/IP
        g.reg_set(
            f"HKLM\\SOFTWARE\\Microsoft\\Microsoft SQL Server\\{instance_name}\\MSSQLServer\\SuperSocketNetLib\\Tcp",
            "Enabled",
            1,
            reg_type="dword"
        )

        logger.info(f"✓ SQL Server TCP/IP enabled for instance: {instance_name}")

    def create_sql_migration_script(self, sql_info: dict) -> str:
        """
        Generate T-SQL script for post-migration tasks.

        Includes:
        - Service restart
        - Database consistency checks (DBCC CHECKDB)
        - Update statistics
        - Rebuild indexes
        - Recompile stored procedures
        - Test connections
        """

        script = """
-- SQL Server Post-Migration Script
-- Generated by hyper2kvm

USE master;
GO

PRINT '============================================';
PRINT 'SQL Server Post-Migration Validation';
PRINT '============================================';
PRINT '';

-- 1. Check SQL Server version
SELECT @@VERSION AS 'SQL Server Version';
GO

-- 2. List all databases
SELECT
    name AS 'Database Name',
    state_desc AS 'State',
    recovery_model_desc AS 'Recovery Model',
    compatibility_level AS 'Compat Level'
FROM sys.databases
ORDER BY name;
GO

-- 3. Check database files
SELECT
    DB_NAME(database_id) AS 'Database',
    name AS 'File Name',
    physical_name AS 'File Path',
    size * 8 / 1024 AS 'Size (MB)',
    state_desc AS 'State'
FROM sys.master_files
ORDER BY database_id, file_id;
GO

-- 4. Run DBCC CHECKDB on all user databases
DECLARE @dbname NVARCHAR(128);
DECLARE db_cursor CURSOR FOR
    SELECT name FROM sys.databases
    WHERE database_id > 4  -- Skip system databases for speed
    AND state_desc = 'ONLINE';

OPEN db_cursor;
FETCH NEXT FROM db_cursor INTO @dbname;

WHILE @@FETCH_STATUS = 0
BEGIN
    PRINT 'Checking database: ' + @dbname;
    EXEC('DBCC CHECKDB([' + @dbname + ']) WITH NO_INFOMSGS');

    FETCH NEXT FROM db_cursor INTO @dbname;
END;

CLOSE db_cursor;
DEALLOCATE db_cursor;
GO

-- 5. Update statistics (sample)
EXEC sp_updatestats;
GO

-- 6. Check SQL Server Agent status
EXEC msdb.dbo.sp_help_jobactivity;
GO

PRINT '';
PRINT '============================================';
PRINT 'Post-Migration Validation Complete';
PRINT '============================================';
PRINT 'Review results above for any issues.';
GO
"""

        return script
```

---

### 4. Windows Update Integration (2-3 weeks)

Download VirtIO drivers from Windows Update before migration.

**Phase 4A: Driver Staging**

```python
# hyper2kvm/fixers/windows/driver_update_mgr.py

class WindowsUpdateDriverManager:
    """Integrate with Windows Update for VirtIO driver download."""

    def stage_virtio_drivers(self, g: VMCraft):
        """
        Pre-stage VirtIO drivers in Windows DriverStore.

        Ensures drivers are available even if Windows Update is offline.
        """

        # Download VirtIO ISO from Fedora Project
        virtio_iso_url = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso"

        # Extract drivers and inject into DriverStore
        # %SystemRoot%\System32\DriverStore\FileRepository

        driver_inf_files = [
            "vioscsi.inf",  # SCSI controller
            "viostor.inf",  # Block device
            "netkvm.inf",   # Network
            "balloon.inf",  # Memory balloon
            "vioserial.inf" # Serial port
        ]

        for inf_file in driver_inf_files:
            self._inject_driver_to_store(g, inf_file)
```

---

## Implementation Timeline

### Month 1-2: License & AD Support
**Weeks 1-4**: License detection, reactivation scripts
**Weeks 5-8**: Active Directory integration, domain rejoin

**Deliverables**:
- License detection and management
- KMS/MAK support
- Domain rejoin automation
- Computer object cleanup scripts

### Month 3-4: SQL Server & Applications
**Weeks 9-13**: SQL Server detection and migration
**Weeks 14-16**: Application compatibility framework

**Deliverables**:
- SQL Server instance migration
- Database integrity validation
- Application compatibility detection

### Month 5-6: Polish & Testing
**Weeks 17-20**: Windows Update integration
**Weeks 21-24**: Testing, documentation, bug fixes

**Deliverables**:
- VirtIO driver staging
- Comprehensive testing on Windows Server 2012-2025
- Documentation and examples

---

## Testing Strategy

### Test Matrix

| Windows Version | License Type | Domain Status | SQL Server | Result |
|----------------|--------------|---------------|------------|--------|
| Server 2012 R2 | KMS | Domain-joined | 2014 | ✅ |
| Server 2016 | MAK | Workgroup | 2016 | ✅ |
| Server 2019 | OEM | Domain-joined | 2019 | ✅ |
| Server 2022 | Retail | Workgroup | None | ✅ |
| Server 2025 | KMS | Domain-joined | 2022 | ✅ |

### Integration Tests

1. **License Migration Test**:
   - Migrate KMS-activated Windows → verify reactivation
   - Migrate MAK Windows → verify activation count
   - Migrate OEM Windows → verify guidance provided

2. **Domain Migration Test**:
   - Migrate domain-joined VM → verify rejoin script
   - Test computer object cleanup
   - Validate SID regeneration

3. **SQL Server Test**:
   - Migrate SQL Server 2019 Standard → verify databases online
   - Run DBCC CHECKDB → verify integrity
   - Test remote connections → verify network config

---

## Documentation Requirements

1. **User Guide**: Windows-specific migration guide
2. **API Reference**: Windows fixer modules
3. **Troubleshooting**: Common Windows migration issues
4. **Examples**: YAML configs for Windows scenarios

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| License key extraction failure | Medium | Provide manual reactivation guidance |
| AD rejoin failures | Medium | Automated fallback to manual instructions |
| SQL Server version detection | Low | Test against all versions 2012+ |
| Driver compatibility | High | Comprehensive driver staging |

---

## Success Metrics

- ✅ 95%+ automated license reactivation (KMS/MAK)
- ✅ 90%+ successful domain rejoins
- ✅ 100% SQL Server instance detection
- ✅ Zero data loss in SQL migrations
- ✅ <1 hour total Windows migration time (avg)

---

## Future Enhancements

- Exchange Server migration support
- SharePoint migration support
- IIS configuration migration
- Certificate migration (SSL/TLS)
- Windows Failover Clustering support
