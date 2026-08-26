# Windows Application Compatibility Schema Reference

**Version**: v0.4.0+
**Module**: Application Compatibility Detection (Phase 2)
**Last Updated**: 2026-03-29

This document describes the configuration schema for Windows application compatibility detection features, including hardware-dependent application detection, license service scanning, and SQL Server instance detection.

---

## Table of Contents

- [Overview](#overview)
- [Configuration Structure](#configuration-structure)
- [Application Compatibility Detection](#application-compatibility-detection)
- [SQL Server Detection](#sql-server-detection)
- [Report Generation](#report-generation)
- [Complete Examples](#complete-examples)
- [Detected Application Types](#detected-application-types)
- [Troubleshooting](#troubleshooting)

---

## Overview

The `windows.appcompat` configuration section controls enterprise application compatibility detection features:

- **Hardware-Dependent Apps**: Detect CAD, graphics, and engineering software with hardware-locked licenses
- **License Services**: Identify FlexLM, RLM, HASP, and other license managers
- **Hardware Dongles**: Detect USB dongle drivers requiring passthrough
- **SQL Server**: Extract SQL Server instance configuration and generate reconfiguration scripts

These features are **optional** - if not configured, no compatibility detection is performed.

---

## Configuration Structure

### Top-Level Schema

```yaml
windows:
  appcompat:
    enabled: bool              # Enable compatibility detection (default: false)
    detect_apps: bool          # Detect hardware-dependent apps (default: true)
    detect_license_services: bool  # Detect license managers (default: true)
    detect_dongles: bool       # Detect hardware dongles (default: true)
    detect_sql_server: bool    # Detect SQL Server instances (default: true)

    sql_server:
      generate_script: bool    # Generate T-SQL reconfiguration script (default: true)
      old_hostname: string | null  # Old hostname for script substitution
      new_hostname: string | null  # New hostname for script substitution

    report:
      format: string           # Report format: json, markdown, both (default: both)
      output_path: string      # Report output path (default: auto-generated)
```

---

## Application Compatibility Detection

Controls detection of hardware-dependent applications and license services.

### Schema

```yaml
windows:
  appcompat:
    enabled: true              # Enable appcompat detection
    detect_apps: true          # Scan for hardware-dependent applications
    detect_license_services: true  # Scan for license manager services
    detect_dongles: true       # Scan for hardware dongle drivers
```

### Parameters

#### `enabled` (boolean)
**Default**: `false`

Enable application compatibility detection during migration analysis.

**Example**:
```yaml
windows:
  appcompat:
    enabled: true
```

---

#### `detect_apps` (boolean)
**Default**: `true` (when `enabled: true`)

Scan registry for installed applications from known hardware-dependent vendors.

**Detects**:
- Autodesk products (AutoCAD, Revit, 3ds Max, Maya)
- Adobe products (Creative Cloud, Photoshop, Premiere Pro)
- Bentley products (MicroStation, OpenBuildings)
- Dassault products (CATIA, SolidWorks)
- Siemens products (NX, Solid Edge)
- PTC products (Creo, Windchill)
- Ansys products (Workbench, Fluent)
- MathWorks MATLAB
- ESRI ArcGIS
- Altium Designer

**Example**:
```yaml
windows:
  appcompat:
    enabled: true
    detect_apps: true  # Scan for hardware-dependent apps
```

**Risk Assessment**:
- Applications are categorized as LOW, MEDIUM, HIGH, or CRITICAL risk
- Mitigation recommendations provided for each finding

---

#### `detect_license_services` (boolean)
**Default**: `true` (when `enabled: true`)

Scan SYSTEM registry hive for license manager services.

**Detects**:
- FlexLM (lmgrd)
- Reprise License Manager (rlm)
- Sentinel HASP License Manager (hasplms)
- Aladdin HASP Driver (aksusb)

**Example**:
```yaml
windows:
  appcompat:
    enabled: true
    detect_license_services: true
```

**Post-Migration Actions**:
License manager services require configuration updates (hostname, MAC address, license.dat files).

---

#### `detect_dongles` (boolean)
**Default**: `true` (when `enabled: true`)

Scan `System32/drivers` for hardware dongle drivers.

**Detects**:
- Aladdin HASP (akshasp.sys)
- SafeNet Sentinel (sentinel.sys)
- HASP Virtual Library (haspvlib.sys)
- CodeMeter Stick (cmstick.sys)
- WIBU-KEY Dongle (wibukey.sys)
- Rockey Dongle (rockey.sys)

**Example**:
```yaml
windows:
  appcompat:
    enabled: true
    detect_dongles: true
```

**Critical**: Hardware dongles require USB passthrough or network dongle server configuration.

---

## SQL Server Detection

Controls SQL Server instance detection and reconfiguration script generation.

### Schema

```yaml
windows:
  appcompat:
    detect_sql_server: true

    sql_server:
      generate_script: true
      old_hostname: "OLD-SERVER"
      new_hostname: "NEW-SERVER"
```

### Parameters

#### `detect_sql_server` (boolean)
**Default**: `true` (when `enabled: true`)

Detect SQL Server installations from SOFTWARE registry hive.

**Extracts**:
- Instance names (MSSQLSERVER, named instances)
- SQL Server version and edition
- Default data/log/backup paths
- TCP port configuration
- Service account names

**Example**:
```yaml
windows:
  appcompat:
    enabled: true
    detect_sql_server: true
```

---

#### `sql_server.generate_script` (boolean)
**Default**: `true` (when `detect_sql_server: true`)

Generate T-SQL reconfiguration script for post-migration execution.

**Script Includes**:
- Linked server updates (hostname substitution)
- Replication configuration guidance
- Always On Availability Group listener reconfiguration
- Service Broker endpoint updates
- Database Mail profile updates
- SQL Agent job review guidance

**Example**:
```yaml
windows:
  appcompat:
    sql_server:
      generate_script: true
```

**Output**: `C:\h2kvm\appcompat\sql-reconfiguration.sql` (in guest filesystem)

---

#### `sql_server.old_hostname` (string | null)
**Default**: `null` (auto-detect from registry if possible)

Old server hostname for use in SQL Server reconfiguration script substitutions.

**Example**:
```yaml
windows:
  appcompat:
    sql_server:
      old_hostname: "PROD-SQL-01"
      new_hostname: "PROD-SQL-01-KVM"
```

**Use Case**: Enables automated hostname replacement in linked servers, replication, and Always On AG configurations.

---

#### `sql_server.new_hostname` (string | null)
**Default**: `null`

New server hostname after migration.

**Example**:
```yaml
windows:
  appcompat:
    sql_server:
      new_hostname: "PROD-SQL-01-KVM"
```

---

## Report Generation

Controls compatibility report format and output location.

### Schema

```yaml
windows:
  appcompat:
    report:
      format: "both"  # json, markdown, both
      output_path: "/tmp/appcompat-report"
```

### Parameters

#### `report.format` (string)
**Default**: `"both"`

Report output format.

**Valid Values**:
- `json` - JSON format only
- `markdown` - Markdown format only
- `both` - Both JSON and Markdown

**Example**:
```yaml
windows:
  appcompat:
    report:
      format: "both"
```

**Outputs**:
- JSON: Structured data for programmatic processing
- Markdown: Human-readable report with risk assessment

---

#### `report.output_path` (string)
**Default**: Auto-generated based on VM name

Path prefix for compatibility report output files.

**Example**:
```yaml
windows:
  appcompat:
    report:
      output_path: "/migration/reports/vm01-appcompat"
```

**Generated Files**:
- `{output_path}.json` - JSON report
- `{output_path}.md` - Markdown report

---

## Complete Examples

### Example 1: Basic Compatibility Detection

```yaml
command: local
vmdk: /data/vms/workstation.vmdk
to_output: workstation-kvm.qcow2

windows:
  appcompat:
    enabled: true
    # All detection types enabled by default
```

**Use Case**: Quick compatibility scan during migration

---

### Example 2: SQL Server Migration with Reconfiguration

```yaml
command: local
vmdk: /data/vms/sql-server.vmdk
to_output: sql-server-kvm.qcow2

windows:
  appcompat:
    enabled: true
    detect_sql_server: true

    sql_server:
      generate_script: true
      old_hostname: "PROD-SQL-01"
      new_hostname: "PROD-SQL-01-KVM"

    report:
      format: "both"
      output_path: "/migration/reports/sql-server-appcompat"
```

**Use Case**: SQL Server migration with automated reconfiguration script generation

---

### Example 3: Selective Detection (Apps and Dongles Only)

```yaml
command: local
vmdk: /data/vms/cad-workstation.vmdk
to_output: cad-workstation-kvm.qcow2

windows:
  appcompat:
    enabled: true
    detect_apps: true           # Detect CAD software
    detect_license_services: false
    detect_dongles: true        # Detect HASP dongles
    detect_sql_server: false
```

**Use Case**: Focus on CAD software and hardware dongle detection

---

### Example 4: Enterprise Migration with Full Detection

```yaml
command: local
vmdk: /data/vms/enterprise-server.vmdk
to_output: enterprise-server-kvm.qcow2

windows:
  # License management
  license:
    preserve: true
    reactivate: true
    kms_server: kms.corp.example.com

  # Active Directory
  active_directory:
    enabled: true
    rejoin:
      method: unattended
    unattended_join:
      enabled: true
      file: /data/domain-join/enterprise-server-join.txt

  # Application compatibility
  appcompat:
    enabled: true
    detect_apps: true
    detect_license_services: true
    detect_dongles: true
    detect_sql_server: true

    sql_server:
      generate_script: true
      old_hostname: "ENT-SRV-01"
      new_hostname: "ENT-SRV-01-KVM"

    report:
      format: "both"
      output_path: "/migration/reports/enterprise-server"
```

**Use Case**: Complete enterprise migration with all Windows features enabled

---

## Detected Application Types

### Hardware-Dependent Application Vendors

| Vendor | Products | Risk Level | License Type |
|--------|----------|------------|--------------|
| Autodesk | AutoCAD, Revit, Maya, 3ds Max | HIGH | Hardware-locked |
| Adobe Systems | Creative Cloud, Photoshop | HIGH | Hardware fingerprint |
| Bentley | MicroStation, OpenBuildings | HIGH | Hardware ID |
| Dassault | CATIA, SolidWorks | HIGH | Hardware-locked |
| Siemens | NX, Solid Edge | HIGH | Hardware dongle |
| PTC | Creo, Windchill | HIGH | Hardware fingerprint |
| Ansys | Workbench, Fluent | MEDIUM | License server |
| MathWorks | MATLAB | MEDIUM | License reactivation |
| ESRI | ArcGIS | MEDIUM | Machine ID |
| Altium | Designer | HIGH | Hardware dongle |

### License Manager Services

| Service | Manager | Configuration File | Port |
|---------|---------|-------------------|------|
| lmgrd | FlexLM | license.dat | 27000+ |
| rlm | Reprise | rlm.opt | 5053 |
| hasplms | Sentinel HASP | hasp_vendor.ini | Various |
| aksusb | Aladdin HASP | - | - |

### Hardware Dongle Drivers

| Driver | Dongle Type | Vendor | Passthrough Required |
|--------|-------------|--------|----------------------|
| akshasp.sys | HASP | Aladdin | Yes (or network server) |
| sentinel.sys | Sentinel | SafeNet | Yes (or network server) |
| haspvlib.sys | HASP Virtual | Aladdin | No (virtual) |
| cmstick.sys | CodeMeter | WIBU-Systems | Yes (or network server) |
| wibukey.sys | WIBU-KEY | WIBU-Systems | Yes (or network server) |
| rockey.sys | Rockey | Rockey | Yes |

---

## Troubleshooting

### No Applications Detected

**Symptom**: Compatibility report shows zero findings despite known software

**Check**:
```bash
# Verify SOFTWARE hive is accessible
h2kvmctl --debug migrate ...
# Check logs for registry access errors
```

**Common Causes**:
1. SOFTWARE hive not found (wrong partition mounted)
2. Registry permissions issue
3. Application installed in non-standard location

**Solution**: Verify Windows system volume is correctly identified

---

### SQL Server Not Detected

**Symptom**: Known SQL Server installation not detected

**Check**:
```powershell
# On source VM, verify SQL Server registry keys
Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"
```

**Common Causes**:
1. SQL Server installed as WOW64 application (32-bit on 64-bit Windows)
2. Custom instance name not in standard registry location
3. SQL Server Express with non-standard configuration

**Solution**: Manually verify SQL Server paths in compatibility report

---

### Dongle Drivers Detected but Dongle Not Present

**Symptom**: Driver found but no physical dongle attached to source VM

**Explanation**: Driver detection is filesystem-based. Drivers may be installed without dongles attached.

**Action**:
- If dongle is required: Ensure USB passthrough configured or use network dongle server
- If dongle not used: Safe to ignore warning

---

### License Service Configuration Not Updated

**Symptom**: FlexLM or RLM service fails after migration

**Check**:
```bash
# On migrated VM, check license configuration
cat C:\Flexlm\license.dat
cat C:\RLM\license.rlm
```

**Solution**:
1. Update hostname in license.dat
2. Update MAC address (for MAC-locked licenses)
3. Restart license manager service
4. Reactivate vendor licenses if needed

---

### SQL Reconfiguration Script Fails

**Symptom**: T-SQL script generated but execution fails

**Common Issues**:
1. **Linked servers**: Update server names in script
2. **Always On AG**: Requires manual listener reconfiguration
3. **Replication**: May require replication removal and re-setup
4. **Permissions**: Script must run as sysadmin

**Solution**: Review and customize generated script before execution. The script is a template requiring DBA review.

---

## See Also

- [Advanced Windows Support Roadmap](../roadmap/Advanced-Windows-Support.md)
- [Windows Configuration Schema](../reference/windows-configuration-schema.md)
- [Windows Migration Guide](../os-support/windows/guide.md)
- [Configuration Loader](../reference/config-loader.md)

---

**Version**: v0.4.0
**Last Updated**: 2026-03-29
**Status**: Production-Ready (Phase 2 Complete)
