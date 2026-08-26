# Advanced Windows Support - Implementation Roadmap

## Executive Summary

This document outlines the implementation roadmap for advanced Windows migration features in h2kvm. Based on comprehensive analysis of the current codebase, this plan extends existing production-ready Windows capabilities with enterprise-focused enhancements.

**Current State**: h2kvm v0.3.0 has excellent Windows migration fundamentals:
- ✅ VirtIO driver injection (8 driver types, full architecture support)
- ✅ Registry manipulation (SYSTEM/SOFTWARE hives)
- ✅ First-boot service provisioning
- ✅ Network configuration retention
- ✅ VMware Tools removal
- ✅ Boot configuration detection

**Proposed Enhancement**: Add enterprise Windows features for license management, Active Directory integration, application compatibility, and performance optimization.

---

## Current Windows Capabilities Assessment

### Production-Ready Features ✅

#### 1. VirtIO Driver Injection
**Files**: `h2kvm/fixers/windows/virtio/`
**Status**: Fully implemented (2,500+ lines)

**Capabilities**:
- 8 driver types: storage, network, balloon, GPU, input, filesystem, serial, RNG
- Windows release support: XP → Windows 12, Server 2008 → Server 2022
- PCI ID-based device matching with fallback buckets
- INF file discovery and staging
- SHA256 verification before/after upload
- Safe hive download/modify/upload/verify cycle

**Configuration**:
```yaml
windows:
  virtio:
    drivers:
      - name: viostor
        type: storage
        start: BOOT  # 0 = boot-critical
        pci_ids: ["1af4:1001", "1af4:1042"]
      - name: netkvm
        type: network
        start: AUTO  # 2 = auto-start
```

#### 2. Registry Operations
**Files**: `h2kvm/fixers/windows/registry/`
**Status**: Fully implemented (1,800+ lines)

**Capabilities**:
- SYSTEM hive: Service creation, CriticalDeviceDatabase population
- SOFTWARE hive: DevicePath modification, RunOnce entries
- Low-level hivex operations: REG_SZ, REG_EXPAND_SZ, REG_DWORD
- ControlSet detection and manipulation
- Safe modification pipeline with verification

#### 3. First-Boot Service Provisioning
**Files**: `h2kvm/fixers/windows/registry/firstboot.py`
**Status**: Fully implemented (200+ lines)

**Capabilities**:
- One-shot Windows service creation (runs as LocalSystem)
- VMware Tools uninstallation (7 removal methods)
- Custom command/script execution
- Idempotency markers (`C:\h2kvm\firstboot.done`)
- Comprehensive logging to `C:\Windows\Temp\h2kvm-firstboot.log`

#### 4. Network Configuration Retention
**Files**: `h2kvm/fixers/windows/network_fixer.py`
**Status**: Fully implemented (600+ lines)

**Capabilities**:
- Offline TCP/IP interface snapshot from SYSTEM hive
- Static IP, gateway, DNS server preservation
- DHCP-derived value capture
- First-boot PowerShell script for reapplication
- MAC address or adapter name-based selection

---

## Proposed Advanced Features

### Priority 1: License & Activation Management

#### Feature 1.1: License Key Extraction & Preservation
**Business Value**: High - Prevents activation issues post-migration
**Implementation Complexity**: Medium
**Estimated Effort**: 3-5 days

**Requirements**:
- Extract Windows product key from source VM registry
- Support multiple license types: OEM, Retail, MAK, KMS, Volume
- Preserve activation state metadata
- Handle Windows 8+ encrypted license keys

**Implementation Approach**:

1. **Offline License Key Extraction**:
```python
# File: h2kvm/fixers/windows/license/extractor.py

def extract_license_info(guestfs, root):
    """Extract Windows license/activation state from offline registry."""

    # Read from SOFTWARE hive
    software_path = detect_windows_hive(guestfs, root, "SOFTWARE")

    keys_to_read = [
        # Digital Product Key (Windows 8+)
        r"Microsoft\Windows NT\CurrentVersion\DigitalProductId",
        r"Microsoft\Windows NT\CurrentVersion\DigitalProductId4",

        # Product key location (older Windows)
        r"Microsoft\Windows NT\CurrentVersion\ProductId",

        # License type
        r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\Activation",

        # KMS information
        r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\KeyManagementServiceName",
        r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\KeyManagementServicePort",
    ]

    license_data = {}
    hive = download_and_open_hive(guestfs, software_path)

    for key_path in keys_to_read:
        try:
            value = read_registry_value(hive, key_path)
            license_data[key_path] = value
        except KeyError:
            continue

    return {
        "product_key": decode_product_key(license_data),
        "license_type": detect_license_type(license_data),
        "kms_server": license_data.get("KeyManagementServiceName"),
        "kms_port": license_data.get("KeyManagementServicePort"),
        "activation_state": determine_activation_state(license_data),
    }
```

2. **Product Key Decoding** (DigitalProductId decryption):
```python
def decode_product_key(license_data):
    """Decode encrypted Windows product key from registry binary."""

    # Extract DigitalProductId4 (Windows 8+) or DigitalProductId (Windows 7)
    dpid = license_data.get("DigitalProductId4") or license_data.get("DigitalProductId")

    if not dpid:
        return None

    # Windows 8+ uses 3-byte encoded key starting at offset 808
    # Algorithm: Microsoft's base-24 encoding with "BCDFGHJKMPQRTVWXY2346789"
    key_offset = 808 if "DigitalProductId4" in license_data else 52

    key_bytes = dpid[key_offset:key_offset + 15]
    key_chars = "BCDFGHJKMPQRTVWXY2346789"

    # Decode using Microsoft's algorithm (simplified)
    decoded = decode_base24(key_bytes, key_chars)

    # Format as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
    return format_product_key(decoded)
```

3. **First-Boot Reactivation Script**:
```powershell
# File: templates/windows/reactivate-license.ps1

$LogFile = "C:\h2kvm\license-reactivation.log"

function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
}

Write-Log "=== Windows License Reactivation Started ==="

# Read license metadata injected by h2kvm
$LicenseInfo = Get-Content "C:\h2kvm\license\license-info.json" | ConvertFrom-Json

switch ($LicenseInfo.Type) {
    "MAK" {
        Write-Log "Detected MAK license - installing key"
        slmgr.vbs /ipk $LicenseInfo.ProductKey
        slmgr.vbs /ato
    }
    "KMS" {
        Write-Log "Detected KMS license - configuring KMS server"
        slmgr.vbs /skms "$($LicenseInfo.KMSServer):$($LicenseInfo.KMSPort)"
        slmgr.vbs /ato
    }
    "OEM" {
        Write-Log "Detected OEM license - activation may require manual intervention"
        # OEM licenses are hardware-locked, may need phone activation
    }
    "Retail" {
        Write-Log "Detected Retail license - installing key"
        slmgr.vbs /ipk $LicenseInfo.ProductKey
        slmgr.vbs /ato
    }
}

# Verify activation
$ActivationStatus = slmgr.vbs /dli
Write-Log "Activation result: $ActivationStatus"

Write-Log "=== License Reactivation Complete ==="
```

**Integration Point**:
```python
# In h2kvm/fixers/windows/fixer.py

def fix_windows(self, guestfs, root):
    # ... existing driver injection ...

    # NEW: License preservation
    if self.config.windows.preserve_license:
        from .license import extractor, reactivator

        license_info = extractor.extract_license_info(guestfs, root)

        # Stage license metadata for first-boot
        reactivator.stage_reactivation_script(
            guestfs,
            root,
            license_info
        )

        # Add reactivation to first-boot service
        self.firstboot.add_command(
            r"powershell.exe -ExecutionPolicy Bypass -File C:\h2kvm\license\reactivate-license.ps1"
        )
```

**Configuration**:
```yaml
windows:
  license:
    preserve: true
    reactivate: true
    # Optional: Override detected license type
    force_type: KMS  # KMS, MAK, Retail, OEM
    kms_server: kms.example.com
    kms_port: 1688
```

**Testing Requirements**:
- Test with Windows 7, 8.1, 10, 11, Server 2012-2022
- Test MAK, KMS, OEM, Retail license types
- Verify product key decryption accuracy
- Test slmgr.vbs reactivation success rate

**Risks & Mitigations**:
- **Risk**: OEM licenses are hardware-locked (motherboard BIOS)
  - **Mitigation**: Document phone activation process, provide warning
- **Risk**: Product key decryption algorithm changes between Windows versions
  - **Mitigation**: Maintain version-specific decoders with fallbacks
- **Risk**: Enterprise KMS servers may not be reachable post-migration
  - **Mitigation**: Allow manual KMS server override in config

---

#### Feature 1.2: Volume License Server Update
**Business Value**: Medium - Critical for enterprise environments
**Implementation Complexity**: Low
**Estimated Effort**: 1-2 days

**Requirements**:
- Update KMS server hostname/IP in registry
- Update KMS port if non-default
- Support DNS-based KMS discovery override

**Implementation**:
```python
def update_kms_configuration(guestfs, root, kms_server, kms_port=1688):
    """Update KMS server configuration in SOFTWARE hive."""

    software_hive = detect_windows_hive(guestfs, root, "SOFTWARE")
    hive = download_and_open_hive(guestfs, software_hive)

    base_path = r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform"

    set_registry_value(
        hive,
        f"{base_path}\\KeyManagementServiceName",
        kms_server,
        "REG_SZ"
    )

    set_registry_value(
        hive,
        f"{base_path}\\KeyManagementServicePort",
        str(kms_port),
        "REG_SZ"
    )

    upload_and_verify_hive(guestfs, software_hive, hive)
```

---

### Priority 2: Active Directory Integration

#### Feature 2.1: Domain Membership Preservation
**Business Value**: Very High - Critical for enterprise Windows
**Implementation Complexity**: High
**Estimated Effort**: 5-8 days

**Current Limitation**: Domain-joined VMs lose membership after migration due to:
- Computer object SID mismatch
- Kerberos keys invalidated
- Secure channel broken
- Machine account password no longer valid

**Challenges**:
1. **Cannot preserve domain membership offline** - Active Directory secure channel requires live interaction
2. **SID regeneration breaks domain trust** - Sysprep changes machine SID
3. **Machine account password rotation** - Cannot be preserved offline

**Proposed Approach**: Automated domain rejoin post-migration

**Implementation**:

1. **Offline Domain Metadata Extraction**:
```python
# File: h2kvm/fixers/windows/activedirectory/extractor.py

def extract_domain_info(guestfs, root):
    """Extract Active Directory membership info from offline registry."""

    system_hive = detect_windows_hive(guestfs, root, "SYSTEM")
    software_hive = detect_windows_hive(guestfs, root, "SOFTWARE")

    hive_system = download_and_open_hive(guestfs, system_hive)
    hive_software = download_and_open_hive(guestfs, software_hive)

    # Read domain membership from SYSTEM hive
    controlset = detect_current_controlset(hive_system)

    domain_keys = {
        "domain_name": read_reg(hive_system, f"{controlset}\\Control\\ComputerName\\ComputerName\\Domain"),
        "computer_name": read_reg(hive_system, f"{controlset}\\Control\\ComputerName\\ActiveComputerName\\ComputerName"),
        "dns_domain": read_reg(hive_software, r"Microsoft\Windows\CurrentVersion\Group Policy\History\NetworkName"),
        "dc_name": read_reg(hive_software, r"Microsoft\Windows\CurrentVersion\Group Policy\History\DCName"),
    }

    return {
        "is_domain_joined": bool(domain_keys.get("domain_name")),
        "domain": domain_keys.get("domain_name"),
        "computer_name": domain_keys.get("computer_name"),
        "dns_domain": domain_keys.get("dns_domain"),
        "last_dc": domain_keys.get("dc_name"),
    }
```

2. **First-Boot Domain Rejoin Script**:
```powershell
# File: templates/windows/rejoin-domain.ps1

$LogFile = "C:\h2kvm\ad\rejoin-domain.log"
$ConfigFile = "C:\h2kvm\ad\domain-info.json"

function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
}

Write-Log "=== Domain Rejoin Started ==="

# Read domain metadata
if (-not (Test-Path $ConfigFile)) {
    Write-Log "ERROR: Domain config not found at $ConfigFile"
    exit 1
}

$DomainInfo = Get-Content $ConfigFile | ConvertFrom-Json

# Option 1: Use stored credentials (encrypted with DPAPI for LocalSystem)
if ($DomainInfo.CredentialFile) {
    $CredPath = "C:\h2kvm\ad\credentials.xml"
    $Credential = Import-Clixml -Path $CredPath

    Write-Log "Rejoining domain: $($DomainInfo.Domain)"

    try {
        # Remove from domain first (clean break)
        Remove-Computer -UnjoinDomainCredential $Credential -Force -Restart:$false

        # Rejoin domain
        Add-Computer `
            -DomainName $DomainInfo.Domain `
            -Credential $Credential `
            -OUPath $DomainInfo.OUPath `
            -Force `
            -Restart:$false

        Write-Log "SUCCESS: Rejoined domain $($DomainInfo.Domain)"

        # Schedule reboot
        shutdown.exe /r /t 60 /c "Restarting to complete domain rejoin"

    } catch {
        Write-Log "ERROR: Failed to rejoin domain: $_"
    }
}

# Option 2: Use unattended join file (requires domain admin pre-provisioning)
elseif ($DomainInfo.UnattendedJoinFile) {
    Write-Log "Using unattended join file (djoin.exe)"

    $JoinFile = "C:\h2kvm\ad\unattended-join.txt"

    # Execute offline domain join
    djoin.exe /RequestODJ /LoadFile $JoinFile /WindowsPath C:\Windows /LocalOS

    if ($LASTEXITCODE -eq 0) {
        Write-Log "SUCCESS: Applied offline domain join"
        shutdown.exe /r /t 60
    } else {
        Write-Log "ERROR: djoin.exe failed with exit code $LASTEXITCODE"
    }
}

# Option 3: Manual rejoin (output instructions)
else {
    Write-Log "MANUAL ACTION REQUIRED: Rejoin domain manually"
    Write-Log "Domain: $($DomainInfo.Domain)"
    Write-Log "Computer Name: $($DomainInfo.ComputerName)"
    Write-Log "OU Path: $($DomainInfo.OUPath)"

    # Create desktop reminder
    $ReminderPath = "C:\Users\Public\Desktop\REJOIN-DOMAIN.txt"
    @"
IMPORTANT: This VM was migrated and needs to rejoin the domain.

Domain: $($DomainInfo.Domain)
Computer Name: $($DomainInfo.ComputerName)
Organizational Unit: $($DomainInfo.OUPath)

Steps:
1. Open System Properties (sysdm.cpl)
2. Click "Change" under Computer Name
3. Select "Domain" and enter: $($DomainInfo.Domain)
4. Provide domain admin credentials
5. Restart when prompted

After rejoining, delete this file.
"@ | Out-File -FilePath $ReminderPath

    Write-Log "Created reminder file at $ReminderPath"
}

Write-Log "=== Domain Rejoin Complete ==="
```

3. **Offline Domain Join Support (djoin.exe)**:

**Pre-Migration Workflow** (on source domain controller):
```powershell
# Domain admin provisions computer object ahead of time
djoin.exe /provision /domain example.com /machine VM01 /savefile vm01-join.txt
```

**Migration Integration**:
```python
def stage_unattended_domain_join(guestfs, root, unattended_join_file):
    """Stage offline domain join file for djoin.exe."""

    # Upload pre-provisioned join file
    join_content = read_file(unattended_join_file)
    guestfs.write(f"{root}/h2kvm/ad/unattended-join.txt", join_content)

    domain_info = {
        "UnattendedJoinFile": True,
        "Method": "djoin.exe"
    }

    write_json(guestfs, f"{root}/h2kvm/ad/domain-info.json", domain_info)
```

**Configuration**:
```yaml
windows:
  active_directory:
    enabled: true

    # Option 1: Automated rejoin with credentials
    rejoin:
      method: credential  # credential, unattended, manual
      domain: example.com
      ou_path: "OU=Migrated,OU=Servers,DC=example,DC=com"
      credential_source: vault  # vault, config, prompt
      vault_path: "secret/windows/domain-join"

    # Option 2: Offline domain join (requires pre-provisioning)
    unattended_join:
      file: /path/to/vm01-join.txt  # From djoin.exe /provision

    # Option 3: Manual rejoin (just extract metadata)
    manual:
      create_reminder: true
```

**Security Considerations**:
- **Credentials stored encrypted**: Use DPAPI for LocalSystem or external vault
- **Least-privilege service account**: Domain join permissions only
- **Time-limited credentials**: Rotate vault secrets regularly
- **Audit trail**: Log all domain join attempts

**Limitations**:
- Cannot preserve existing domain relationship (secure channel breaks)
- Requires domain admin or delegated join permissions
- Computer object may conflict if not cleaned up pre-migration
- Kerberos tickets lost (users must re-authenticate)

---

#### Feature 2.2: Computer Object Cleanup
**Business Value**: Medium - Prevents AD bloat
**Implementation Complexity**: Low
**Estimated Effort**: 1 day

**Approach**: Provide pre-migration script to disable/delete old computer object

```powershell
# Pre-migration script (run on domain controller)
# File: scripts/windows/cleanup-ad-computer.ps1

param(
    [Parameter(Mandatory=$true)]
    [string]$ComputerName,

    [Parameter(Mandatory=$false)]
    [ValidateSet("Disable", "Delete")]
    [string]$Action = "Disable"
)

$Computer = Get-ADComputer -Identity $ComputerName -ErrorAction SilentlyContinue

if (-not $Computer) {
    Write-Host "Computer $ComputerName not found in AD"
    exit 1
}

switch ($Action) {
    "Disable" {
        Disable-ADAccount -Identity $Computer
        Write-Host "Disabled computer object: $ComputerName"

        # Add description
        Set-ADComputer -Identity $Computer -Description "Disabled - Migrated on $(Get-Date -Format 'yyyy-MM-dd')"
    }
    "Delete" {
        Remove-ADComputer -Identity $Computer -Confirm:$false
        Write-Host "Deleted computer object: $ComputerName"
    }
}
```

---

### Priority 3: Application Compatibility

#### Feature 3.1: Hardware-Dependent Application Detection
**Business Value**: High - Prevents post-migration failures
**Implementation Complexity**: Medium
**Estimated Effort**: 3-4 days

**Scope**: Detect applications that may break due to hardware changes

**Detection Targets**:
1. **License servers** (FlexLM, RLM, Sentinel)
2. **Hardware dongles** (HASP, SafeNet, CodeMeter)
3. **MAC address-locked licenses**
4. **Hardware-fingerprint activation** (Adobe, Autodesk)
5. **COM port dependencies**
6. **Parallel port devices**

**Implementation**:
```python
# File: h2kvm/fixers/windows/appcompat/detector.py

def detect_hardware_dependent_apps(guestfs, root):
    """Scan for applications with hardware dependencies."""

    findings = []

    # 1. Scan installed applications from registry
    software_hive = detect_windows_hive(guestfs, root, "SOFTWARE")
    hive = download_and_open_hive(guestfs, software_hive)

    uninstall_keys = [
        r"Microsoft\Windows\CurrentVersion\Uninstall",
        r"Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

    for uninstall_key in uninstall_keys:
        apps = enumerate_registry_keys(hive, uninstall_key)

        for app in apps:
            app_info = read_app_metadata(hive, f"{uninstall_key}\\{app}")

            # Check against known hardware-dependent vendors
            if is_hardware_dependent(app_info):
                findings.append({
                    "app": app_info["DisplayName"],
                    "vendor": app_info.get("Publisher"),
                    "version": app_info.get("DisplayVersion"),
                    "risk": assess_migration_risk(app_info),
                    "recommendation": get_mitigation_steps(app_info),
                })

    # 2. Scan for license manager services
    system_hive = detect_windows_hive(guestfs, root, "SYSTEM")
    hive_system = download_and_open_hive(guestfs, system_hive)

    license_services = [
        "lmgrd",  # FlexLM
        "rlm",    # Reprise License Manager
        "hasplms", # Sentinel HASP
    ]

    controlset = detect_current_controlset(hive_system)
    services_path = f"{controlset}\\Services"

    for service in license_services:
        if service_exists(hive_system, f"{services_path}\\{service}"):
            findings.append({
                "type": "license_service",
                "service": service,
                "risk": "HIGH",
                "recommendation": "Update license server configuration post-migration",
            })

    # 3. Scan for dongle drivers
    dongle_drivers = [
        "akshasp",  # Aladdin HASP
        "sentinel", # SafeNet Sentinel
        "haspvlib", # HASP virtual library
        "cmstick",  # CodeMeter stick
    ]

    for driver in dongle_drivers:
        driver_path = f"{root}/Windows/System32/drivers/{driver}.sys"
        if guestfs.exists(driver_path):
            findings.append({
                "type": "dongle_driver",
                "driver": driver,
                "risk": "CRITICAL",
                "recommendation": "Ensure dongle is attached to target hypervisor or use network dongle",
            })

    return findings


def is_hardware_dependent(app_info):
    """Check if application is known to have hardware dependencies."""

    hardware_dependent_vendors = [
        "Autodesk",
        "Adobe Systems",
        "Bentley",
        "Dassault",
        "Siemens",
        "PTC",
        "Ansys",
        "MathWorks",
    ]

    publisher = app_info.get("Publisher", "")

    for vendor in hardware_dependent_vendors:
        if vendor.lower() in publisher.lower():
            return True

    return False
```

**Output Report**:
```json
{
  "hardware_dependent_apps": [
    {
      "app": "AutoCAD 2022",
      "vendor": "Autodesk",
      "version": "24.1",
      "risk": "HIGH",
      "recommendation": "Reactivate license after migration - Autodesk licenses are hardware-locked"
    },
    {
      "type": "license_service",
      "service": "lmgrd",
      "risk": "HIGH",
      "recommendation": "Update license server configuration in C:\\Flexlm\\license.dat"
    },
    {
      "type": "dongle_driver",
      "driver": "akshasp",
      "risk": "CRITICAL",
      "recommendation": "Ensure HASP dongle is attached to target hypervisor"
    }
  ]
}
```

---

#### Feature 3.2: SQL Server Instance Reconfiguration
**Business Value**: Very High - SQL Server is extremely common
**Implementation Complexity**: High
**Estimated Effort**: 5-7 days

**Challenges**:
- Instance-specific registry keys
- Tempdb location changes
- Linked server updates
- Always On Availability Group reconfiguration
- Replication subscriber/publisher updates

**Implementation**:
```python
# File: h2kvm/fixers/windows/appcompat/sqlserver.py

def detect_sql_server_instances(guestfs, root):
    """Detect SQL Server installations and configurations."""

    software_hive = detect_windows_hive(guestfs, root, "SOFTWARE")
    hive = download_and_open_hive(guestfs, software_hive)

    instances = []

    # SQL Server registry path
    sql_base_keys = [
        r"Microsoft\Microsoft SQL Server",
        r"Wow6432Node\Microsoft\Microsoft SQL Server",
    ]

    for base_key in sql_base_keys:
        instance_names_key = f"{base_key}\\Instance Names\\SQL"

        if not key_exists(hive, instance_names_key):
            continue

        instance_map = read_registry_values(hive, instance_names_key)

        for instance_name, instance_id in instance_map.items():
            instance_config = extract_instance_config(
                hive,
                base_key,
                instance_id
            )

            instances.append({
                "name": instance_name,
                "id": instance_id,
                "version": instance_config.get("Version"),
                "edition": instance_config.get("Edition"),
                "data_path": instance_config.get("DefaultData"),
                "log_path": instance_config.get("DefaultLog"),
                "backup_path": instance_config.get("BackupDirectory"),
                "tcp_port": instance_config.get("TcpPort"),
                "service_account": extract_service_account(guestfs, root, instance_name),
            })

    return instances


def generate_sql_reconfiguration_script(instances):
    """Generate T-SQL script for post-migration reconfiguration."""

    script_lines = ["-- SQL Server Post-Migration Reconfiguration Script", ""]

    for instance in instances:
        script_lines.extend([
            f"-- Instance: {instance['name']}",
            "USE master;",
            "GO",
            "",
            "-- Update linked servers (replace old hostname)",
            "EXEC sp_droplinkedsrvlogin @rmtsrvname = 'OLD_SERVER', @locallogin = NULL;",
            "EXEC sp_dropserver 'OLD_SERVER';",
            "EXEC sp_addlinkedserver @server = 'NEW_SERVER';",
            "",
            "-- Reconfigure Always On Availability Groups (if applicable)",
            "-- ALTER AVAILABILITY GROUP [AG_Name] REMOVE LISTENER 'OldListener';",
            "-- ALTER AVAILABILITY GROUP [AG_Name] ADD LISTENER 'NewListener' (WITH IP((N'10.0.0.100', N'255.255.255.0')), PORT=1433);",
            "",
            "-- Update Replication (if applicable)",
            "-- exec sp_changedistpublisher @publisher = 'OldServer', @property = 'working_directory', @value = '\\\\NewServer\\repldata';",
            "",
        ])

    return "\n".join(script_lines)
```

**First-Boot Integration**:
```powershell
# File: templates/windows/reconfigure-sqlserver.ps1

$LogFile = "C:\h2kvm\sql\reconfiguration.log"
$ScriptFile = "C:\h2kvm\sql\reconfigure-instance.sql"

function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
}

Write-Log "=== SQL Server Reconfiguration Started ==="

# Read instance metadata
$InstanceInfo = Get-Content "C:\h2kvm\sql\instances.json" | ConvertFrom-Json

foreach ($Instance in $InstanceInfo.Instances) {
    Write-Log "Processing instance: $($Instance.Name)"

    # Connect to instance
    $ServerInstance = if ($Instance.Name -eq "MSSQLSERVER") {
        "(local)"
    } else {
        "(local)\$($Instance.Name)"
    }

    try {
        # Execute reconfiguration script
        Invoke-Sqlcmd `
            -ServerInstance $ServerInstance `
            -InputFile $ScriptFile `
            -ErrorAction Stop

        Write-Log "SUCCESS: Reconfigured instance $($Instance.Name)"

    } catch {
        Write-Log "ERROR: Failed to reconfigure $($Instance.Name): $_"
    }
}

Write-Log "=== SQL Server Reconfiguration Complete ==="
```

**Configuration**:
```yaml
windows:
  applications:
    sql_server:
      enabled: true
      detect: true
      reconfigure: true

      # Update linked servers
      linked_servers:
        replace_hostname: true
        old_hostname: oldserver.example.com
        new_hostname: newserver.example.com

      # Update Always On AG listeners
      availability_groups:
        - name: AG_Primary
          listener_old: oldlistener.example.com
          listener_new: newlistener.example.com
          ip: 10.0.0.100

      # Tempdb relocation (optional)
      tempdb:
        relocate: false
        data_path: "D:\\MSSQL\\TEMPDB"
        log_path: "D:\\MSSQL\\TEMPDB"
```

---

### Priority 4: Performance Optimization

#### Feature 4.1: VirtIO Balloon Driver Auto-Configuration
**Business Value**: Medium - Improves memory management
**Implementation Complexity**: Low
**Estimated Effort**: 1 day

**Status**: Driver injection already implemented, just needs auto-start configuration

**Enhancement**:
```yaml
windows:
  virtio:
    drivers:
      - name: balloon
        type: memory
        start: AUTO  # Already supported
        auto_configure: true  # NEW: Auto-configure balloon service

        # Balloon configuration
        config:
          memory_stats_interval: 10  # Report stats every 10 seconds
          free_page_reporting: true  # Enable free page reporting
```

**Registry Configuration**:
```python
def configure_balloon_driver(hive_system, controlset):
    """Configure VirtIO balloon driver parameters."""

    balloon_params_key = f"{controlset}\\Services\\balloon\\Parameters"

    # Create Parameters key if missing
    ensure_key_exists(hive_system, balloon_params_key)

    # Set memory stats interval (in seconds)
    set_registry_value(
        hive_system,
        f"{balloon_params_key}\\MemoryStatsInterval",
        10,
        "REG_DWORD"
    )

    # Enable free page reporting
    set_registry_value(
        hive_system,
        f"{balloon_params_key}\\FreePageReporting",
        1,
        "REG_DWORD"
    )
```

---

#### Feature 4.2: TRIM/Discard Enablement
**Business Value**: Medium - Improves storage performance on SSDs
**Implementation Complexity**: Low
**Estimated Effort**: 1 day

**Implementation**:
```powershell
# File: templates/windows/enable-trim.ps1

$LogFile = "C:\h2kvm\storage\trim-enablement.log"

function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
}

Write-Log "=== TRIM/Discard Enablement Started ==="

# Check if disks support TRIM
$Disks = Get-PhysicalDisk | Where-Object { $_.MediaType -eq "SSD" -or $_.MediaType -eq "UnSpecified" }

foreach ($Disk in $Disks) {
    Write-Log "Checking disk: $($Disk.FriendlyName)"

    # Enable TRIM on volume
    $Volumes = Get-Partition -DiskNumber $Disk.DeviceId | Get-Volume

    foreach ($Volume in $Volumes) {
        if ($Volume.FileSystemType -eq "NTFS" -or $Volume.FileSystemType -eq "ReFS") {
            Write-Log "Enabling TRIM on volume $($Volume.DriveLetter)"

            # Enable TRIM via fsutil
            fsutil behavior set DisableDeleteNotify 0

            # Verify TRIM is enabled
            $TrimStatus = fsutil behavior query DisableDeleteNotify
            Write-Log "TRIM status: $TrimStatus"
        }
    }
}

# Schedule regular TRIM optimization
Write-Log "Scheduling weekly TRIM optimization"
Optimize-Volume -DriveLetter C -ReTrim -Verbose

# Enable scheduled optimization task
$Task = Get-ScheduledTask -TaskName "ScheduledDefrag" -ErrorAction SilentlyContinue
if ($Task) {
    Enable-ScheduledTask -TaskName "ScheduledDefrag"
    Write-Log "Enabled scheduled disk optimization task"
}

Write-Log "=== TRIM Enablement Complete ==="
```

---

#### Feature 4.3: MSI Interrupt Configuration
**Business Value**: Medium - Reduces interrupt latency
**Implementation Complexity**: Medium
**Estimated Effort**: 2-3 days

**Background**: Message Signaled Interrupts (MSI/MSI-X) reduce latency vs legacy line-based interrupts

**Implementation**:
```python
def configure_msi_interrupts(hive_system, controlset):
    """Enable MSI/MSI-X for VirtIO devices."""

    # Enable MSI for VirtIO SCSI/storage
    viostor_params = f"{controlset}\\Services\\viostor\\Parameters"
    set_registry_value(hive_system, f"{viostor_params}\\MSISupported", 1, "REG_DWORD")

    # Enable MSI for VirtIO network
    netkvm_params = f"{controlset}\\Services\\netkvm\\Parameters"
    set_registry_value(hive_system, f"{netkvm_params}\\MSISupported", 1, "REG_DWORD")

    # Global MSI policy (prefer MSI over line-based)
    msi_policy = f"{controlset}\\Control\\PnP\\Pci"
    set_registry_value(hive_system, f"{msi_policy}\\MSIPolicy", 1, "REG_DWORD")
```

---

#### Feature 4.4: Hyper-V Enlightenments Removal
**Business Value**: Low - Only relevant for Hyper-V → KVM migrations
**Implementation Complexity**: Low
**Estimated Effort**: 1 day

**Purpose**: Remove Hyper-V synthetic devices and enlightenments that don't apply to KVM

**Implementation**:
```python
def remove_hyperv_enlightenments(hive_system, controlset):
    """Remove Hyper-V specific drivers and enlightenments."""

    hyperv_services = [
        "storflt",      # Hyper-V storage filter
        "vmbus",        # Hyper-V VMBus
        "storvsc",      # Hyper-V storage VSC
        "netvsc",       # Hyper-V network VSC
        "hyperkbd",     # Hyper-V keyboard
        "hypervideo",   # Hyper-V video
        "vmgid",        # Hyper-V generation ID
        "vmicheartbeat",# Hyper-V heartbeat IC
        "vmickvpexchange", # Hyper-V KVP IC
        "vmicshutdown", # Hyper-V shutdown IC
        "vmictimesync", # Hyper-V time sync IC
        "vmicvss",      # Hyper-V VSS IC
    ]

    for service in hyperv_services:
        service_key = f"{controlset}\\Services\\{service}"

        if key_exists(hive_system, service_key):
            # Set to disabled (do not delete - may cause boot issues)
            set_registry_value(hive_system, f"{service_key}\\Start", 4, "REG_DWORD")
```

---

## Implementation Prioritization Matrix

| Feature | Business Value | Complexity | Effort (days) | Priority | Phase |
|---------|---------------|-----------|---------------|----------|-------|
| License Key Extraction | High | Medium | 3-5 | P1 | 1 |
| Domain Rejoin Automation | Very High | High | 5-8 | P1 | 1 |
| App Compatibility Detection | High | Medium | 3-4 | P2 | 2 |
| SQL Server Reconfiguration | Very High | High | 5-7 | P2 | 2 |
| VirtIO Balloon Config | Medium | Low | 1 | P3 | 3 |
| TRIM Enablement | Medium | Low | 1 | P3 | 3 |
| MSI Interrupt Config | Medium | Medium | 2-3 | P3 | 3 |
| KMS Server Update | Medium | Low | 1-2 | P3 | 3 |
| Hyper-V Removal | Low | Low | 1 | P4 | 4 |
| Computer Object Cleanup | Medium | Low | 1 | P4 | 4 |

**Total Estimated Effort**: 23-32 days (engineering time)

---

## Development Phases

### Phase 1: Core Enterprise Features (2-3 weeks)
**Goal**: Enable enterprise Windows migrations with license and AD support

**Deliverables**:
1. ✅ License key extraction and preservation
2. ✅ Automated license reactivation (MAK, KMS, Retail)
3. ✅ Domain metadata extraction
4. ✅ Automated domain rejoin (credential-based)
5. ✅ Offline domain join support (djoin.exe)
6. ✅ Manual domain rejoin guidance
7. ✅ KMS server configuration updates
8. ✅ Comprehensive logging and reporting

**Testing Requirements**:
- Windows 7, 8.1, 10, 11 (all editions)
- Server 2012 R2, 2016, 2019, 2022
- OEM, Retail, MAK, KMS, Volume licenses
- Domain-joined and workgroup VMs
- Multiple SQL Server versions (2012-2022)

---

### Phase 2: Application Compatibility (2-3 weeks)
**Goal**: Detect and mitigate application-specific issues

**Deliverables**:
1. ✅ Hardware-dependent app detection
2. ✅ License server identification (FlexLM, RLM, HASP)
3. ✅ SQL Server instance detection
4. ✅ SQL Server reconfiguration scripts
5. ✅ Application compatibility report generation
6. ✅ Mitigation guidance for detected issues

**Testing Requirements**:
- SQL Server 2012-2022 (Standard, Enterprise)
- Autodesk, Adobe, Bentley, Siemens applications
- License servers: FlexLM, RLM, Sentinel
- Hardware dongles: HASP, SafeNet, CodeMeter

---

### Phase 3: Performance Optimization (1 week)
**Goal**: Optimize Windows performance on KVM

**Deliverables**:
1. ✅ VirtIO balloon auto-configuration
2. ✅ TRIM/discard enablement
3. ✅ MSI interrupt configuration
4. ✅ Performance validation scripts
5. ✅ Benchmarking tools integration

**Testing Requirements**:
- SSD-backed storage validation
- Network throughput testing (before/after MSI)
- Memory ballooning effectiveness
- TRIM/discard verification

---

### Phase 4: Cleanup & Polish (1 week)
**Goal**: Complete remaining features and documentation

**Deliverables**:
1. ✅ Hyper-V enlightenments removal
2. ✅ AD computer object cleanup scripts
3. ✅ Comprehensive user documentation
4. ✅ Migration best practices guide
5. ✅ Troubleshooting runbook

---

## Configuration Schema

```yaml
windows:
  # License & Activation
  license:
    preserve: true              # Extract and preserve license key
    reactivate: true            # Auto-reactivate on first boot
    force_type: null            # Override: KMS, MAK, Retail, OEM
    kms_server: kms.example.com # KMS server override
    kms_port: 1688              # KMS port override

  # Active Directory
  active_directory:
    enabled: true

    # Automated rejoin with credentials
    rejoin:
      method: credential        # credential, unattended, manual
      domain: example.com
      ou_path: "OU=Migrated,OU=Servers,DC=example,DC=com"
      credential_source: vault  # vault, config, prompt
      vault_path: "secret/windows/domain-join"

      # Service account for domain join
      service_account:
        username: "DOMAIN\\svc_migration"
        password_vault: "secret/windows/svc_migration"

    # Offline domain join (requires pre-provisioning)
    unattended_join:
      enabled: false
      file: /path/to/djoin-output.txt

    # Manual rejoin (metadata only)
    manual:
      create_reminder: true     # Desktop reminder file

  # Application Compatibility
  applications:
    # App detection
    detect_hardware_dependent: true
    generate_report: true
    report_path: /tmp/app-compat-report.json

    # SQL Server specific
    sql_server:
      enabled: true
      detect: true
      reconfigure: true

      linked_servers:
        replace_hostname: true
        old_hostname: oldserver.example.com
        new_hostname: newserver.example.com

      availability_groups:
        - name: AG_Primary
          listener_old: oldlistener.example.com
          listener_new: newlistener.example.com
          ip: 10.0.0.100

      tempdb:
        relocate: false
        data_path: "D:\\MSSQL\\TEMPDB"

  # Performance Optimization
  performance:
    # VirtIO balloon
    balloon:
      auto_configure: true
      memory_stats_interval: 10
      free_page_reporting: true

    # TRIM/discard
    trim:
      enable: true
      schedule_optimization: true

    # MSI interrupts
    msi:
      enable: true
      devices: [storage, network]

    # Hyper-V cleanup
    hyperv:
      remove_enlightenments: true  # Only for Hyper-V → KVM
```

---

## Testing Strategy

### Unit Tests
- License key decoding algorithms
- Registry manipulation functions
- Domain metadata extraction
- App detection logic
- SQL Server instance discovery

### Integration Tests
- End-to-end license preservation
- Domain rejoin workflows
- SQL Server reconfiguration
- Performance optimization validation

### System Tests
- Real Windows VM migrations (7, 8.1, 10, 11, Server 2012-2022)
- Domain-joined and workgroup scenarios
- SQL Server migrations
- Application compatibility scenarios

### Performance Tests
- MSI interrupt latency improvements
- TRIM/discard effectiveness
- Balloon driver memory management
- Network throughput with VirtIO

---

## Documentation Requirements

1. **User Guide**: "Advanced Windows Migration Features"
   - License preservation walkthrough
   - Domain rejoin configuration
   - Application compatibility reports
   - Performance tuning recommendations

2. **Administrator Guide**: "Enterprise Windows Migration"
   - Pre-migration checklist
   - AD computer object cleanup
   - SQL Server migration procedures
   - Troubleshooting common issues

3. **Developer Guide**: "Extending Windows Support"
   - Adding new application handlers
   - Custom first-boot scripts
   - Registry manipulation patterns
   - Testing new Windows features

4. **API Reference**: "Windows Fixer API"
   - License management API
   - AD integration API
   - App compatibility API
   - Performance tuning API

---

## Risk Assessment

### High Risk Items
| Risk | Impact | Mitigation |
|------|--------|-----------|
| License key decryption fails | Cannot reactivate Windows | Implement version-specific decoders with fallbacks |
| Domain rejoin fails | VM not accessible to domain users | Provide manual rejoin instructions, test extensively |
| SQL Server corruption | Database downtime | Read-only detection, generate scripts for manual execution |
| Credential exposure | Security breach | Use vault integration, encrypted storage, audit logging |

### Medium Risk Items
| Risk | Impact | Mitigation |
|------|--------|-----------|
| App compatibility false positives | Unnecessary warnings | Refine detection rules, allow user overrides |
| Performance degradation | Poor user experience | Extensive benchmarking, configurable optimizations |
| MSI interrupt conflicts | Device malfunction | Make MSI optional, test on diverse hardware |

### Low Risk Items
| Risk | Impact | Mitigation |
|------|--------|-----------|
| TRIM not supported | Reduced SSD lifespan | Detect SSD support before enabling |
| Balloon driver overhead | Minor performance impact | Make balloon optional, document trade-offs |

---

## Success Criteria

### Phase 1 Success Metrics
- ✅ 95%+ license key extraction accuracy across Windows 7-11
- ✅ 90%+ successful domain rejoin with credentials
- ✅ 100% successful offline domain join (with pre-provisioning)
- ✅ Zero credential leaks in logs or reports

### Phase 2 Success Metrics
- ✅ Detect 80%+ of hardware-dependent applications
- ✅ Generate actionable SQL Server reconfiguration scripts
- ✅ <5% false positive rate in app compatibility detection

### Phase 3 Success Metrics
- ✅ 20%+ network throughput improvement with MSI interrupts
- ✅ TRIM/discard verified on 100% of SSD-backed VMs
- ✅ Balloon driver successfully manages memory on 95%+ of VMs

---

## Future Enhancements (Post-Phase 4)

### Phase 5: Advanced Features
- **IIS Configuration Migration**: Site bindings, app pools, SSL certificates
- **Exchange Server Support**: Database relocation, network configuration
- **SharePoint Support**: Farm configuration, content database paths
- **Certificate Store Migration**: Machine certificates, SSL/TLS certs
- **Windows Firewall Rules**: Export and import firewall configuration
- **Scheduled Tasks**: Preserve scheduled jobs with updated paths

### Phase 6: Cloud Integration
- **Azure AD Join**: Migrate Azure AD-joined devices
- **Microsoft 365 Integration**: OneDrive, Teams desktop app reconfiguration
- **Intune Enrollment**: Re-enroll in device management
- **Conditional Access**: Update device compliance

---

## Appendix A: Registry Paths Reference

### License & Activation
```
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\DigitalProductId
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\DigitalProductId4
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\Activation
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\KeyManagementServiceName
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\KeyManagementServicePort
```

### Domain Membership
```
HKLM\SYSTEM\ControlSet001\Control\ComputerName\ComputerName\Domain
HKLM\SYSTEM\ControlSet001\Control\ComputerName\ActiveComputerName\ComputerName
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\History\NetworkName
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\History\DCName
```

### SQL Server
```
HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL
HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\{InstanceID}\Setup\SQLPath
HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\{InstanceID}\MSSQLServer\DefaultData
HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\{InstanceID}\MSSQLServer\DefaultLog
```

### VirtIO Drivers
```
HKLM\SYSTEM\ControlSet001\Services\viostor\Parameters\MSISupported
HKLM\SYSTEM\ControlSet001\Services\netkvm\Parameters\MSISupported
HKLM\SYSTEM\ControlSet001\Services\balloon\Parameters\MemoryStatsInterval
HKLM\SYSTEM\ControlSet001\Control\PnP\Pci\MSIPolicy
```

---

## Appendix B: Known Limitations

1. **OEM Licenses**: Hardware-locked to motherboard BIOS, may require phone activation
2. **Azure AD Join**: Cannot be preserved offline, requires cloud re-enrollment
3. **BitLocker**: Encryption keys may be lost, decrypt before migration
4. **Cluster Services**: Windows Failover Cluster requires manual reconfiguration
5. **BCD Editing**: Cannot edit Boot Configuration Data offline (requires Windows tools)
6. **User Profiles**: NTUSER.DAT modifications not implemented (user-specific settings lost)
7. **SAM Modifications**: Local user passwords cannot be preserved (security restriction)

---

## Appendix C: Vendor-Specific Handlers

### Autodesk Products
- License server: `C:\ProgramData\Autodesk\AdskLicensingService\LicPath.txt`
- Requires reactivation after hardware change

### Adobe Creative Cloud
- License tied to hardware fingerprint
- Requires deactivation before migration, reactivation after

### SQL Server
- Always On AG: Update listener endpoint
- Linked Servers: Update server names/IPs
- Replication: Update distributor/publisher names
- Tempdb: May need relocation to separate disk

### FlexLM License Servers
- License file: `C:\Flexlm\license.dat`
- Update `SERVER` line with new hostname/MAC
- Restart lmgrd service

---

**Document Version**: 1.0
**Last Updated**: 2026-03-29
**Status**: Draft - Pending Implementation
