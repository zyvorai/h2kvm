# Windows Configuration Schema Reference

**Version**: v0.3.0+
**Module**: Advanced Windows Support (Phase 1)
**Last Updated**: 2026-03-29

This document describes the YAML/JSON configuration schema for advanced Windows migration features, including license management and Active Directory integration.

---

## Table of Contents

- [Overview](#overview)
- [Configuration Structure](#configuration-structure)
- [License Management](#license-management)
- [Active Directory Integration](#active-directory-integration)
- [Complete Examples](#complete-examples)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

---

## Overview

The `windows` configuration section controls enterprise Windows migration features:

- **License Management**: Extract, preserve, and reactivate Windows licenses (OEM, Retail, MAK, KMS)
- **Active Directory**: Automate domain rejoin after VM migration

These features are **optional** - if not configured, default behavior is used (no license reactivation, no domain rejoin).

---

## Configuration Structure

### Top-Level Schema

```yaml
windows:
  license:
    # License management settings
  active_directory:
    # AD domain rejoin settings
```

### Supported Formats

- **YAML**: `.yaml`, `.yml` (recommended)
- **JSON**: `.json`

### Key Normalization

All keys support both dash and underscore variants:
- `active-directory` → `active_directory` (normalized internally)
- `kms-server` → `kms_server` (normalized internally)

---

## License Management

Controls extraction and reactivation of Windows product licenses.

### Schema

```yaml
windows:
  license:
    preserve: bool              # Extract license info (default: false)
    reactivate: bool            # Auto-reactivate on first boot (default: false)
    force_type: string | null   # Override license type (default: null)
    kms_server: string | null   # KMS server override (default: null)
    kms_port: int | null        # KMS port override (default: 1688)
```

### Parameters

#### `preserve` (boolean)
**Default**: `false`

Extract Windows license information from offline registry during migration.

**Extracts**:
- Product key (DigitalProductId, DigitalProductId4)
- License type (OEM, Retail, MAK, KMS, Volume)
- Product ID
- Edition (Professional, Enterprise, Datacenter, etc.)
- KMS server configuration (if applicable)
- Activation status (offline approximation)

**Example**:
```yaml
windows:
  license:
    preserve: true
```

---

#### `reactivate` (boolean)
**Default**: `false`

Automatically reactivate Windows license on first boot after migration.

**Requires**: `preserve: true`

**Behavior**:
- Generates PowerShell script for first-boot execution
- Uses `slmgr.vbs` for activation
- Different strategies for each license type:
  - **MAK**: Install key + activate
  - **KMS**: Configure server + activate
  - **Retail**: Install key + activate
  - **OEM**: Warning + manual activation guidance
  - **Volume**: Activate with existing configuration

**Example**:
```yaml
windows:
  license:
    preserve: true
    reactivate: true
```

**First-Boot Process**:
1. PowerShell script executes as LocalSystem
2. Loads license info from `C:\h2kvm\license\license-info.json`
3. Executes appropriate `slmgr.vbs` commands
4. Logs results to `C:\h2kvm\license\reactivation.log`

---

#### `force_type` (string | null)
**Default**: `null` (auto-detect)

Override detected license type.

**Valid Values**:
- `KMS` - Key Management Service (volume licensing)
- `MAK` - Multiple Activation Key (volume licensing)
- `Retail` - Retail license
- `OEM` - Original Equipment Manufacturer license
- `Volume` - Generic volume license
- `null` - Auto-detect from registry

**Use Cases**:
- License type misdetected
- Converting OEM to Retail/MAK
- Testing specific activation workflows

**Example**:
```yaml
windows:
  license:
    preserve: true
    reactivate: true
    force_type: KMS
```

**Warning**: Forcing incorrect license type may cause activation failures.

---

#### `kms_server` (string | null)
**Default**: `null` (use detected server or DNS-based discovery)

Override KMS server hostname/IP for KMS license activation.

**Format**: `hostname` or `hostname:port`

**Example**:
```yaml
windows:
  license:
    preserve: true
    reactivate: true
    kms_server: kms.corp.example.com
```

**With Custom Port**:
```yaml
windows:
  license:
    kms_server: kms.corp.example.com:1689
```

**Behavior**:
- Overrides detected KMS server from registry
- Configures Windows to use specified KMS server
- Falls back to DNS-based KMS discovery if not specified

---

#### `kms_port` (integer | null)
**Default**: `1688` (standard KMS port)

Override KMS server port.

**Valid Range**: `1-65535`

**Example**:
```yaml
windows:
  license:
    kms_server: kms.corp.example.com
    kms_port: 1689
```

**Note**: Only relevant for KMS licenses.

---

### License Management Examples

#### Example 1: Basic License Preservation
```yaml
windows:
  license:
    preserve: true
    reactivate: false  # Extract only, no reactivation
```

**Use Case**: Extract license info for reporting, manual reactivation

---

#### Example 2: Full Automatic Reactivation
```yaml
windows:
  license:
    preserve: true
    reactivate: true
```

**Use Case**: Automatic license reactivation for Retail, MAK, or KMS licenses

---

#### Example 3: KMS License with Server Override
```yaml
windows:
  license:
    preserve: true
    reactivate: true
    kms_server: kms.newdatacenter.example.com
    kms_port: 1688
```

**Use Case**: Migrating to new datacenter with different KMS server

---

#### Example 4: Force MAK License Type
```yaml
windows:
  license:
    preserve: true
    reactivate: true
    force_type: MAK
```

**Use Case**: Converting OEM to MAK after purchasing volume license

---

## Active Directory Integration

Controls automated domain rejoin after VM migration.

### Schema

```yaml
windows:
  active_directory:
    enabled: bool                    # Enable AD integration (default: false)
    rejoin:
      method: string                 # Rejoin method (required)
      domain: string | null          # Domain override (default: null)
      ou_path: string | null         # OU path (default: null)
      credential_source: string      # Credential source (for 'credential' method)
      vault_path: string             # Vault path (for 'vault' credential source)
    unattended_join:
      enabled: bool                  # Enable offline join (default: false)
      file: string                   # djoin.exe output file path
    manual:
      create_reminder: bool          # Create desktop instructions (default: true)
```

### Parameters

#### `enabled` (boolean)
**Default**: `false`

Enable Active Directory domain rejoin automation.

**Example**:
```yaml
windows:
  active_directory:
    enabled: true
```

---

#### `rejoin.method` (string)
**Required** if `enabled: true`

Domain rejoin method.

**Valid Values**:
- `credential` - Automated rejoin with stored credentials
- `unattended` - Offline domain join (djoin.exe)
- `manual` - Manual rejoin with desktop instructions

**Comparison**:

| Method | Automation | Security | Prerequisites |
|--------|-----------|----------|---------------|
| `credential` | Full | Medium | Service account credentials |
| `unattended` | Full | High | Pre-provisioned join file from DC |
| `manual` | None | N/A | Administrator intervention |

**Example**:
```yaml
windows:
  active_directory:
    enabled: true
    rejoin:
      method: credential
```

---

#### `rejoin.domain` (string | null)
**Default**: `null` (use detected domain from registry)

Override detected domain name.

**Format**: Fully qualified domain name (FQDN)

**Example**:
```yaml
windows:
  active_directory:
    rejoin:
      method: credential
      domain: corp.example.com
```

**Use Cases**:
- Domain name changed
- Migrating to different domain
- Domain detection failed

---

#### `rejoin.ou_path` (string | null)
**Default**: `null` (default Computers container)

Specify Organizational Unit (OU) path for computer object in Active Directory.

**Format**: LDAP distinguished name (DN)

**Example**:
```yaml
windows:
  active_directory:
    rejoin:
      method: credential
      ou_path: "OU=Migrated VMs,OU=Servers,DC=corp,DC=example,DC=com"
```

**Benefits**:
- Organize migrated VMs in dedicated OU
- Apply specific Group Policies to migrated computers
- Delegate permissions for migration service account

**Note**: Service account must have permissions to create computer objects in specified OU.

---

#### `rejoin.credential_source` (string)
**Default**: `vault` (for `credential` method)

Source for domain join credentials.

**Valid Values**:
- `vault` - External vault (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault)
- `config` - Stored in configuration file (NOT RECOMMENDED for production)
- `prompt` - Interactive prompt during migration (NOT RECOMMENDED for automation)

**Example (Vault)**:
```yaml
windows:
  active_directory:
    rejoin:
      method: credential
      credential_source: vault
      vault_path: "secret/windows/domain-join"
```

**Example (Config - NOT RECOMMENDED)**:
```yaml
windows:
  active_directory:
    rejoin:
      method: credential
      credential_source: config
      username: "CORP\\svc_migration"
      password: "SecurePassword123!"  # WARNING: Plaintext password
```

**Security Warning**: `config` source stores credentials in plaintext. Use `vault` for production.

---

#### `unattended_join.enabled` (boolean)
**Default**: `false`

Enable offline domain join using djoin.exe.

**Requires**: `rejoin.method: unattended`

**Example**:
```yaml
windows:
  active_directory:
    rejoin:
      method: unattended
    unattended_join:
      enabled: true
      file: /path/to/server01-join.txt
```

---

#### `unattended_join.file` (string)
**Required** if `unattended_join.enabled: true`

Path to djoin.exe output file (provisioned on domain controller).

**Format**: Absolute path to `.txt` file

**Pre-Migration Step** (run on domain controller as domain admin):
```powershell
djoin.exe /provision /domain corp.example.com /machine SERVER01 /savefile server01-join.txt
```

**Example**:
```yaml
windows:
  active_directory:
    unattended_join:
      enabled: true
      file: /path/to/server01-join.txt
```

**Security Benefits**:
- No credentials stored during migration
- Pre-authorized by domain admin
- Time-limited and one-time use
- Auditable (AD tracks provisioning)

---

#### `manual.create_reminder` (boolean)
**Default**: `true` (for `manual` method)

Create desktop reminder file with manual domain rejoin instructions.

**Example**:
```yaml
windows:
  active_directory:
    rejoin:
      method: manual
    manual:
      create_reminder: true
```

**Output**: `C:\Users\Public\Desktop\DOMAIN-REJOIN-REQUIRED.txt`

**Contents**:
- Extracted domain information
- Step-by-step rejoin instructions
- Troubleshooting guidance

---

### Active Directory Examples

#### Example 1: Credential-Based Rejoin
```yaml
windows:
  active_directory:
    enabled: true
    rejoin:
      method: credential
      domain: corp.example.com
      ou_path: "OU=Migrated,OU=Servers,DC=corp,DC=example,DC=com"
      credential_source: vault
      vault_path: "secret/windows/domain-join"
```

**Use Case**: Automated domain rejoin with credentials from HashiCorp Vault

---

#### Example 2: Offline Domain Join
```yaml
windows:
  active_directory:
    enabled: true
    rejoin:
      method: unattended
    unattended_join:
      enabled: true
      file: /path/to/server01-join.txt
```

**Use Case**: High-security environment with pre-provisioned join files

---

#### Example 3: Manual Rejoin
```yaml
windows:
  active_directory:
    enabled: true
    rejoin:
      method: manual
    manual:
      create_reminder: true
```

**Use Case**: Administrator manually rejoins domain (safest default)

---

## Complete Examples

### Enterprise Windows Server Migration

Complete configuration with license and AD support:

```yaml
# Enterprise Windows Server 2022 Migration
command: local
vmdk: /data/vms/fileserver01.vmdk
to_output: fileserver01-kvm.qcow2
compress: true
verbose: 2

# VirtIO drivers
virtio_drivers_dir: /opt/virtio-win
enable_virtio_rng: true

# Windows enterprise features
windows:
  # License management
  license:
    preserve: true
    reactivate: true
    kms_server: kms.corp.example.com
    kms_port: 1688

  # Active Directory
  active_directory:
    enabled: true
    rejoin:
      method: unattended
    unattended_join:
      enabled: true
      file: /data/domain-join/fileserver01-join.txt

# Standard migration options
remove_vmware_tools: true
regen_initramfs: false  # Windows doesn't use initramfs
fstab_mode: stabilize-all
report: fileserver01-migration-report.md
```

---

### Windows Workstation Migration (Manual Rejoin)

Simple configuration with manual domain rejoin:

```yaml
command: local
vmdk: /data/vms/win11-workstation.vmdk
to_output: win11-workstation-kvm.qcow2

windows:
  license:
    preserve: true
    reactivate: true

  active_directory:
    enabled: true
    rejoin:
      method: manual
```

---

## Security Considerations

### License Management

1. **Product Keys**: Never logged in plaintext
   - Stored in `C:\h2kvm\license\license-info.json` (guest filesystem)
   - Accessible only during first boot as LocalSystem
   - Not persisted in host logs

2. **Reactivation Logs**: Sensitive information
   - Location: `C:\Windows\Temp\h2kvm-firstboot.log`
   - Contains slmgr.vbs output
   - May include partial product key info
   - Recommend deletion after successful activation

3. **OEM Licenses**: Hardware-locked
   - May require phone activation
   - Cannot be automated
   - Desktop reminder created with guidance

### Active Directory

1. **Credential Storage** (credential method)
   - **RECOMMENDED**: Use external vault (HashiCorp Vault, Azure Key Vault)
   - **NOT RECOMMENDED**: Store in config file (plaintext)
   - Credentials encrypted with DPAPI for LocalSystem
   - Credentials deleted after successful domain join

2. **Credential Lifecycle**:
   - Use least-privilege service account
   - Grant only "Join computers to domain" permission
   - Time-limit credentials (expire after migration window)
   - Rotate credentials regularly
   - Audit all domain join operations

3. **Offline Domain Join** (unattended method)
   - Most secure: no credentials during migration
   - Pre-authorized by domain admin
   - Join file is one-time use
   - Join file should be deleted after migration
   - Audit provisioning on domain controller

4. **Computer Object Cleanup**:
   - Old computer object should be disabled/deleted pre-migration
   - Prevents conflicts during domain rejoin
   - Use AD administrative tools or PowerShell

---

## Troubleshooting

### License Reactivation Failures

**Symptom**: Windows shows "Activate Windows" watermark after migration

**Check**:
```powershell
# View reactivation log
Get-Content C:\h2kvm\license\reactivation.log

# Check activation status
slmgr.vbs /dli

# Check license info
Get-Content C:\h2kvm\license\license-info.json
```

**Common Issues**:
1. **OEM License**: Hardware-locked, requires phone activation
   - Solution: Use phone activation or purchase Retail/MAK license

2. **KMS Server Unreachable**: Network connectivity issue
   - Solution: Verify DNS resolution and firewall rules
   - Test: `nslookup _vlmcs._tcp.corp.example.com`

3. **MAK Activation Limit**: No activations remaining
   - Solution: Request additional activations from Microsoft or use KMS

4. **Product Key Decoding Failed**: Registry data corrupted
   - Solution: Manual activation with known product key

### Domain Rejoin Failures

**Symptom**: Desktop reminder appears, automated rejoin failed

**Check**:
```powershell
# View rejoin log (credential method)
Get-Content C:\h2kvm\ad\rejoin.log

# View offline join log (unattended method)
Get-Content C:\h2kvm\ad\offline-join.log

# Check domain info
Get-Content C:\h2kvm\ad\domain-info.json

# Test domain connectivity
Test-ComputerSecureChannel -Verbose
nltest /dsgetdc:corp.example.com
```

**Common Issues**:
1. **Credentials Invalid**: Wrong username/password or expired
   - Solution: Verify credentials, check vault integration

2. **Computer Object Exists**: Old object not cleaned up
   - Solution: Delete old computer object in AD Users and Computers
   - PowerShell: `Get-ADComputer -Identity SERVER01 | Remove-ADComputer`

3. **DNS Resolution Failed**: Cannot locate domain controller
   - Solution: Configure DNS servers to point to domain DNS
   - Verify: `nslookup corp.example.com`

4. **Insufficient Permissions**: Service account lacks domain join rights
   - Solution: Grant "Join computers to domain" permission
   - Or: Add to "Domain Admins" group (less secure)

5. **OU Path Invalid**: Specified OU doesn't exist
   - Solution: Verify OU exists in AD
   - PowerShell: `Get-ADOrganizationalUnit -Filter 'Name -eq "Migrated"'`

---

## See Also

- [Advanced Windows Support Roadmap](../roadmap/Advanced-Windows-Support.md)
- [Windows Migration Guide](../os-support/windows/guide.md)
- [Configuration Loader](../reference/config-loader.md)
- [Security Best Practices](../guides/security-best-practices.md)

---

**Version**: v0.3.0
**Last Updated**: 2026-03-29
**Status**: Production-Ready (Phase 1 Complete)
