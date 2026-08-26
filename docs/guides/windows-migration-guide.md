# Comprehensive Windows VM Migration Guide

**Version**: v0.5.0+
**Last Updated**: 2026-03-29
**Audience**: System Administrators, DevOps Engineers, IT Professionals

This guide provides step-by-step instructions for migrating Windows VMs from VMware, Hyper-V, or other hypervisors to KVM using h2kvm with full enterprise feature support.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Pre-Migration Planning](#pre-migration-planning)
4. [Basic Migration Workflow](#basic-migration-workflow)
5. [Enterprise Features](#enterprise-features)
   - [License Management](#license-management)
   - [Active Directory Integration](#active-directory-integration)
   - [Application Compatibility](#application-compatibility)
   - [Performance Optimization](#performance-optimization)
6. [Post-Migration Tasks](#post-migration-tasks)
7. [Common Scenarios](#common-scenarios)
8. [Troubleshooting](#troubleshooting)

---

## Overview

h2kvm supports comprehensive Windows VM migration with enterprise features:

- **Automated driver injection**: VirtIO drivers for storage, network, and peripherals
- **License preservation**: Extract and reactivate Windows licenses (OEM, Retail, MAK, KMS)
- **Active Directory support**: Domain membership detection and rejoin automation
- **Application compatibility**: Detect hardware-dependent apps, license services, SQL Server
- **Performance optimization**: VirtIO balloon, TRIM/discard, MSI interrupts, Hyper-V cleanup

**Supported Windows Versions**:
- Windows Server 2008 R2 through 2025
- Windows 7 through 11
- Both x64 and x86 (32-bit)

---

## Prerequisites

### Software Requirements

1. **h2kvm** v0.5.0 or later
2. **VirtIO drivers ISO** — auto-downloaded to `/var/lib/h2kvm/virtio-win.iso` by `quickstart.sh` or `sudo ./scripts/install-deps.sh --virtio-win`. If the ISO is at the standard path, h2kvm auto-discovers it and no `--virtio-drivers-dir` flag is needed. You can also download manually from [Fedora VirtIO](https://fedorapeople.org/groups/virt/virtio-win/).
3. **Source VM files** (VMDK, VHDX, VHD, or OVA)
4. **KVM hypervisor** (QEMU/KVM, libvirt)

### Access Requirements

- **Read access** to source VM files
- **Write access** to target storage location
- **Network connectivity** (for KMS activation if applicable)
- **Domain admin credentials** (for AD operations, if applicable)

### Resource Requirements

- **Disk space**: 2x source VM size (for conversion)
- **RAM**: 2GB minimum, 4GB recommended
- **CPU**: Multi-core recommended for faster conversion

---

## Pre-Migration Planning

### 1. Inventory Source VM

Document the source VM configuration:

```bash
# For VMware VMs
vmware-vdiskmanager -R source.vmdk

# For Hyper-V VMs
Get-VHD -Path C:\VMs\source.vhdx | Select-Object *

# Using h2kvm inspect
h2kvm inspect source.vmdk
```

**Document**:
- Operating system version
- Domain membership status
- Installed applications (especially hardware-dependent ones)
- License type (OEM, Retail, MAK, KMS)
- Network configuration
- Storage configuration (basic, LVM, encrypted)

### 2. Prepare VirtIO Drivers

The easiest way to install VirtIO drivers is to use the built-in script, which downloads the ISO to the standard path (`/var/lib/h2kvm/virtio-win.iso`). When the ISO is at this location, h2kvm auto-discovers it — no `--virtio-drivers-dir` flag is needed.

```bash
# Recommended: auto-download to standard path (auto-discovered by h2kvm)
sudo ./scripts/install-deps.sh --virtio-win

# Or download manually from Fedora
wget https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso
sudo mkdir -p /var/lib/h2kvm
sudo mv virtio-win.iso /var/lib/h2kvm/virtio-win.iso

# Optional: extract drivers to a custom path (only if you need a non-standard location)
mkdir -p /opt/virtio-drivers
h2kvm extract-drivers virtio-win.iso /opt/virtio-drivers
```

### 3. Create Configuration File

Create a YAML configuration file for your migration:

```yaml
# windows-migration.yaml
command: local
vmdk: /data/vms/windows-server.vmdk
to_output: /data/kvm/windows-server.qcow2

windows:
  # VirtIO driver injection
  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
  # virtio_drivers_path: /opt/virtio-drivers  # only needed to override the standard path

  # License management
  license:
    extract: true
    reactivate: true
    kms_server: kms.example.com  # Optional: Override KMS server

  # Active Directory
  activedirectory:
    extract_domain_info: true
    rejoin_method: unattended  # manual, credential, or unattended
    ou_path: "OU=Servers,DC=example,DC=com"  # Optional

  # Application compatibility scanning
  appcompat:
    detect_hardware_apps: true
    detect_license_services: true
    detect_sql_server: true
    generate_report: true

  # Performance optimization
  performance:
    balloon:
      enable: true
      memory_stats_interval: 10
      free_page_reporting: true
    trim:
      enable: true
      schedule_optimization: true
    msi:
      enable: true
      devices:
        - viostor
        - netkvm
    hyperv:
      cleanup: true  # Auto-detect Hyper-V and cleanup
```

---

## Basic Migration Workflow

### Step 1: Run Migration

```bash
# Using configuration file
h2kvm migrate --config windows-migration.yaml

# Or inline for simple migrations
h2kvm convert \
  --input /data/vms/windows-server.vmdk \
  --output /data/kvm/windows-server.qcow2 \
  --windows-optimize
  # --virtio-drivers-dir /opt/virtio-drivers  # optional override; auto-discovered at /var/lib/h2kvm/virtio-win.iso
```

### Step 2: Monitor Progress

```bash
# Check conversion progress
tail -f /var/log/h2kvm/migration.log

# Monitor resource usage
watch -n 1 'df -h /data/kvm && free -h'
```

### Step 3: Create KVM VM

After successful conversion, create the KVM VM:

```bash
# Using virt-install
virt-install \
  --name windows-server \
  --memory 4096 \
  --vcpus 2 \
  --disk path=/data/kvm/windows-server.qcow2,bus=virtio \
  --network network=default,model=virtio \
  --graphics vnc \
  --os-variant win2k19 \
  --import

# Or using virsh with XML
virsh define windows-server.xml
virsh start windows-server
```

### Step 4: First Boot Verification

Connect to the VM console and verify:

1. **Windows boots successfully**
2. **VirtIO drivers loaded** (check Device Manager)
3. **Network connectivity** established
4. **Disk performance** acceptable

---

## Enterprise Features

### License Management

#### Automatic License Detection

h2kvm automatically extracts Windows license information during migration:

```yaml
windows:
  license:
    extract: true  # Extract license info from registry
```

**Extracted information**:
- Product key (Windows 7-11, Server 2008 R2-2025)
- License type (OEM, Retail, MAK, KMS, Volume)
- Product name and edition
- Installation ID

#### License Reactivation

Configure automatic reactivation:

```yaml
windows:
  license:
    extract: true
    reactivate: true
    kms_server: kms.company.com  # Optional: Override detected KMS
    kms_port: 1688  # Optional: Custom KMS port
```

**Reactivation methods by license type**:

| License Type | Method | Notes |
|--------------|--------|-------|
| OEM | Requires phone activation | Original key may not work on KVM |
| Retail | Automatic online activation | Usually works without intervention |
| MAK | Automatic online activation | Decrements activation count |
| KMS | Automatic KMS activation | Requires network connectivity to KMS |
| Volume | Manual intervention may be required | Contact your volume license administrator |

#### Post-Migration License Activation

After first boot, check activation status:

```powershell
# Check activation status
slmgr.vbs /dli
slmgr.vbs /dlv

# If reactivation failed, run manually
C:\h2kvm\license\reactivate.ps1

# For KMS clients
slmgr.vbs /ato
```

#### License Report

Review the extracted license information:

```bash
# View license report (created during migration)
cat /data/kvm/windows-server-license-report.json
```

Example report:
```json
{
  "product_name": "Windows Server 2019 Standard",
  "license_type": "Volume",
  "partial_product_key": "XXXXX-XXXXX-XXXXX-XXXXX-AB123",
  "kms_server": "kms.company.com:1688",
  "activation_required": true
}
```

---

### Active Directory Integration

#### Domain Membership Detection

Automatically detect domain membership:

```yaml
windows:
  activedirectory:
    extract_domain_info: true
```

**Extracted information**:
- Domain name (NetBIOS and DNS)
- Computer account name
- Last used domain controller
- Workgroup vs. domain status

#### Domain Rejoin Methods

Choose the appropriate rejoin method:

##### 1. Manual Rejoin (Recommended for Testing)

```yaml
windows:
  activedirectory:
    rejoin_method: manual
```

**Steps after first boot**:
1. Review instructions: `C:\h2kvm\activedirectory\domain-rejoin.ps1`
2. Manually unjoin/rejoin using GUI or PowerShell
3. Reboot to complete

**Best for**: Test environments, single VM migrations

##### 2. Credential-Based Rejoin

```yaml
windows:
  activedirectory:
    rejoin_method: credential
    domain: example.com
    ou_path: "OU=Servers,DC=example,DC=com"
```

**Steps after first boot**:
1. Run: `C:\h2kvm\activedirectory\domain-rejoin.ps1`
2. Enter domain admin credentials when prompted
3. System will automatically rejoin and reboot

**Best for**: Interactive migrations with admin supervision

##### 3. Unattended Rejoin (Recommended for Production)

```yaml
windows:
  activedirectory:
    rejoin_method: unattended
    domain: example.com
    ou_path: "OU=Servers,DC=example,DC=com"
    unattended_join_file: /path/to/djoin-blob.txt
```

**Preparation steps**:
```powershell
# On domain controller or admin workstation
# Pre-create computer account and generate join blob

djoin.exe /provision `
  /domain example.com `
  /machine NEW-SERVER-NAME `
  /savefile C:\djoin-blob.txt `
  /printblob

# Copy djoin-blob.txt to h2kvm host
```

**Benefits**:
- No credentials stored in VM
- Atomic domain join operation
- Suitable for automation and templates

**Best for**: Production environments, mass migrations

#### AD Computer Object Cleanup

Remove stale computer objects from Active Directory:

```yaml
windows:
  activedirectory:
    cleanup_old_computer: true
    old_computer_name: "OLD-SERVER-NAME"
```

**Manual cleanup script** is also generated:
```powershell
# On domain controller or admin workstation
C:\h2kvm\activedirectory\ad-cleanup.ps1
```

This prevents conflicts when the migrated VM has a different computer name.

---

### Application Compatibility

#### Compatibility Scanning

Enable comprehensive compatibility scanning:

```yaml
windows:
  appcompat:
    detect_hardware_apps: true
    detect_license_services: true
    detect_dongle_drivers: true
    detect_sql_server: true
    generate_report: true
```

#### Hardware-Dependent Applications

Detects applications with known hardware dependencies:

- **Autodesk products** (AutoCAD, Maya, 3ds Max)
- **Adobe Creative Cloud** (Photoshop, Illustrator, Premiere Pro)
- **CAD/CAM software** (SolidWorks, CATIA, Mastercam)
- **Engineering tools** (MATLAB, LabVIEW)
- **Security software** (antivirus, encryption tools)

**Report output**:
```json
{
  "hardware_apps": [
    {
      "name": "AutoCAD 2023",
      "vendor": "Autodesk",
      "risk_level": "HIGH",
      "reason": "Hardware-locked licensing (FlexLM)",
      "recommendation": "Contact vendor for license transfer"
    }
  ]
}
```

#### License Manager Services

Detects license services that may need reconfiguration:

- FlexLM (FlexNet Publisher)
- Sentinel HASP/LDK
- CodeMeter
- WIBU-Systems
- SafeNet Sentinel

#### Hardware Dongle Drivers

Detects USB dongle drivers:

- Sentinel HASP
- WIBU CodeMeter
- SafeNet eToken
- Gemalto

**Mitigation**: Ensure dongle is attached to KVM host and USB passthrough configured.

#### SQL Server Detection

Automatically detects SQL Server instances:

```yaml
windows:
  appcompat:
    detect_sql_server: true
    generate_sql_script: true
```

**Detected information**:
- Instance name and version
- Edition (Express, Standard, Enterprise)
- Installation path
- Service accounts
- Network configuration

**Generated reconfiguration script**:
```powershell
# C:\h2kvm\appcompat\sql-reconfigure.sql
```

SQL Server may require:
1. Server name update (if hostname changed)
2. Linked server reconfiguration
3. Replication reinitialization
4. Reporting Services reconfiguration
5. License reactivation

#### Compatibility Report

Review the generated compatibility report:

```bash
# JSON format
cat /data/kvm/windows-server-compatibility.json

# Markdown format (human-readable)
cat /data/kvm/windows-server-compatibility.md
```

**Report sections**:
- Executive summary (risk levels, findings count)
- Hardware-dependent applications
- License manager services
- Hardware dongle drivers
- SQL Server instances
- Recommended actions

---

### Performance Optimization

#### VirtIO Balloon Driver

Configure memory ballooning:

```yaml
windows:
  performance:
    balloon:
      enable: true
      memory_stats_interval: 10  # seconds
      free_page_reporting: true  # Windows 10 1809+, Server 2019+
```

**Benefits**:
- Dynamic memory management
- Memory overcommitment support
- Improved host memory utilization

**Verification**:
```powershell
# Check balloon service status
Get-Service balloon

# Verify registry settings
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\balloon\Parameters"
```

#### TRIM/Discard for SSDs

Enable TRIM support:

```yaml
windows:
  performance:
    trim:
      enable: true
      schedule_optimization: true  # Weekly scheduled task
```

**Benefits**:
- Improved SSD performance
- Extended SSD lifespan
- Reduced write amplification

**Verification**:
```powershell
# Check TRIM status
fsutil behavior query DisableDeleteNotification

# Expected output: DisableDeleteNotification = 0 (enabled)

# Manually run optimization
defrag C: /L /O
```

#### MSI Interrupts

Enable Message Signaled Interrupts:

```yaml
windows:
  performance:
    msi:
      enable: true
      devices:
        - viostor  # VirtIO storage
        - netkvm   # VirtIO network
```

**Benefits**:
- ~20% network throughput improvement
- Reduced interrupt latency
- Better CPU utilization

**Verification**:
```powershell
# Run verification script
C:\h2kvm\performance\msi-verify.ps1

# Check registry manually
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\netkvm\Parameters\InterruptManagement\MessageSignaledInterruptProperties"
```

#### Hyper-V Enlightenments Cleanup

Remove Hyper-V components when migrating from Hyper-V:

```yaml
windows:
  performance:
    hyperv:
      cleanup: true  # Auto-detect and cleanup
      force: false   # Force cleanup without detection
```

**Removed services** (12 total):
- Hyper-V Virtual Machine Bus (vmbus)
- Hyper-V Guest Service Interface
- Hyper-V Heartbeat Service
- Hyper-V Data Exchange Service
- Hyper-V Time Synchronization Service
- And 7 more integration services

**Verification**:
```powershell
# Check for remaining Hyper-V services
Get-Service | Where-Object {$_.Name -like "vm*" -or $_.Name -like "hv*"}

# Should return no running services
```

---

## Post-Migration Tasks

### 1. Initial Boot Validation

**Checklist**:
- [ ] Windows boots successfully
- [ ] No driver missing warnings
- [ ] Network adapters visible in Device Manager
- [ ] Disk I/O performance acceptable
- [ ] Event Viewer shows no critical errors

### 2. License Activation

```powershell
# Check activation status
slmgr.vbs /dli

# If not activated, run reactivation script
C:\h2kvm\license\reactivate.ps1

# Verify activation
slmgr.vbs /xpr
```

### 3. Domain Rejoin

```powershell
# For manual/credential rejoin
C:\h2kvm\activedirectory\domain-rejoin.ps1

# For unattended rejoin (automatic on first boot)
# Verify domain membership
Get-CimInstance -ClassName Win32_ComputerSystem | Select-Object Domain, PartOfDomain
```

### 4. Active Directory Cleanup

On domain controller or admin workstation:

```powershell
# Remove old computer object
C:\h2kvm\activedirectory\ad-cleanup.ps1

# Or manually via GUI
dsa.msc  # Active Directory Users and Computers
```

### 5. Application Validation

Review compatibility report and take action:

```bash
# Review compatibility report
cat windows-server-compatibility.md
```

**Action items**:
1. **Hardware-dependent apps**: Contact vendors for license transfer
2. **License services**: Verify license server connectivity
3. **Hardware dongles**: Attach dongle via USB passthrough
4. **SQL Server**: Run reconfiguration script

```powershell
# Run SQL Server reconfiguration
sqlcmd -S localhost -i C:\h2kvm\appcompat\sql-reconfigure.sql
```

### 6. Performance Verification

Run verification scripts:

```powershell
# Verify all performance optimizations
C:\h2kvm\performance\balloon-verify.ps1
C:\h2kvm\performance\trim-verify.ps1
C:\h2kvm\performance\msi-verify.ps1
```

### 7. Network Configuration

Verify network settings:

```powershell
# Check IP configuration
Get-NetIPAddress
Get-NetIPConfiguration

# Verify DNS and gateway
Test-NetConnection -ComputerName 8.8.8.8
nslookup example.com
```

### 8. Backup VM

Create a backup of the working VM:

```bash
# Create snapshot
virsh snapshot-create-as windows-server \
  post-migration-working \
  "Working state after migration and validation"

# Or clone VM
virt-clone \
  --original windows-server \
  --name windows-server-backup \
  --file /data/kvm/windows-server-backup.qcow2
```

---

## Common Scenarios

### Scenario 1: Domain-Joined Database Server

**Requirements**:
- Windows Server 2019 with SQL Server 2019
- Domain member (example.com)
- MAK license
- SSD storage

**Configuration**:
```yaml
command: local
vmdk: /data/vms/db-server.vmdk
to_output: /data/kvm/db-server.qcow2

windows:
  # virtio_drivers_path: /opt/virtio-drivers  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso

  license:
    extract: true
    reactivate: true

  activedirectory:
    extract_domain_info: true
    rejoin_method: unattended
    domain: example.com
    ou_path: "OU=Database Servers,OU=Servers,DC=example,DC=com"
    unattended_join_file: /data/djoin-db-server.txt

  appcompat:
    detect_sql_server: true
    generate_sql_script: true

  performance:
    balloon:
      enable: true
    trim:
      enable: true
      schedule_optimization: true
    msi:
      enable: true
```

**Post-migration**:
1. Verify domain rejoin successful
2. Run SQL Server reconfiguration script
3. Update SQL Server service account if needed
4. Repoint application connection strings
5. Verify database connectivity and performance

---

### Scenario 2: Standalone Hyper-V Workstation

**Requirements**:
- Windows 10 Professional
- Migrating from Hyper-V
- Retail license
- Desktop applications (Office, Adobe Creative Cloud)

**Configuration**:
```yaml
command: local
vhdx: /data/vms/workstation.vhdx
to_output: /data/kvm/workstation.qcow2

windows:
  # virtio_drivers_path: /opt/virtio-drivers  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso

  license:
    extract: true
    reactivate: true

  appcompat:
    detect_hardware_apps: true
    detect_license_services: true

  performance:
    balloon:
      enable: true
      free_page_reporting: true
    trim:
      enable: true
    msi:
      enable: true
    hyperv:
      cleanup: true  # Remove Hyper-V components
```

**Post-migration**:
1. Verify Hyper-V services disabled
2. Check license activation (may require phone activation for Retail)
3. Verify Adobe Creative Cloud license (may need reactivation)
4. Test application functionality

---

### Scenario 3: KMS-Activated Application Server

**Requirements**:
- Windows Server 2022
- KMS activation
- Enterprise applications with FlexLM licensing
- Domain member

**Configuration**:
```yaml
command: local
vmdk: /data/vms/app-server.vmdk
to_output: /data/kvm/app-server.qcow2

windows:
  # virtio_drivers_path: /opt/virtio-drivers  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso

  license:
    extract: true
    reactivate: true
    kms_server: kms.company.com
    kms_port: 1688

  activedirectory:
    extract_domain_info: true
    rejoin_method: credential
    domain: company.com

  appcompat:
    detect_hardware_apps: true
    detect_license_services: true
    generate_report: true

  performance:
    balloon:
      enable: true
    trim:
      enable: true
    msi:
      enable: true
```

**Post-migration**:
1. Verify KMS activation (should be automatic)
2. Contact software vendors for license transfer (FlexLM)
3. Reconfigure license server settings in applications
4. Verify network connectivity to license servers

---

### Scenario 4: Multi-VM Batch Migration

For migrating multiple Windows VMs:

```bash
#!/bin/bash
# batch-migrate.sh

VMs=(
    "web-server-01:example.com:Web Servers"
    "web-server-02:example.com:Web Servers"
    "app-server-01:example.com:App Servers"
)

for vm in "${VMs[@]}"; do
    IFS=':' read -r name domain ou <<< "$vm"

    echo "Migrating $name..."

    cat > "${name}-config.yaml" <<EOF
command: local
vmdk: /data/vms/${name}.vmdk
to_output: /data/kvm/${name}.qcow2

windows:
  # virtio_drivers_path: /opt/virtio-drivers  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
  license:
    extract: true
    reactivate: true
  activedirectory:
    extract_domain_info: true
    rejoin_method: unattended
    domain: ${domain}
    ou_path: "OU=${ou},DC=example,DC=com"
    unattended_join_file: /data/djoin-${name}.txt
  performance:
    balloon:
      enable: true
    trim:
      enable: true
    msi:
      enable: true
EOF

    h2kvm migrate --config "${name}-config.yaml"
done
```

---

## Troubleshooting

### Boot Failures

**Symptom**: VM fails to boot, BSOD 0x0000007B

**Cause**: VirtIO storage driver not properly injected

**Solution**:
```bash
# Re-run migration with forced driver injection
# VirtIO ISO is auto-discovered at /var/lib/h2kvm/virtio-win.iso
h2kvm convert \
  --input source.vmdk \
  --output target.qcow2 \
  --force-virtio-injection
  # --virtio-drivers-dir /custom/path  # only if ISO is not at standard path
```

### License Activation Failures

**Symptom**: License reactivation script fails

**Causes & Solutions**:

| License Type | Error | Solution |
|--------------|-------|----------|
| KMS | Cannot contact KMS server | Verify network connectivity, check KMS server address |
| MAK | Activation limit reached | Contact Microsoft support for reset |
| Retail | Hardware changed too much | Use phone activation |
| OEM | OEM key not valid | Contact Microsoft or use new license |

### Domain Rejoin Failures

**Symptom**: Domain rejoin fails with error

**Common errors**:

1. **"The specified domain either does not exist or could not be contacted"**
   - Check DNS configuration
   - Verify network connectivity to domain controllers
   - Test: `nslookup example.com`

2. **"The account already exists"**
   - Computer object still exists in AD
   - Run AD cleanup script: `C:\h2kvm\activedirectory\ad-cleanup.ps1`

3. **"Access denied"**
   - Incorrect domain admin credentials
   - Verify credentials and retry

### Performance Issues

**Symptom**: Poor disk or network performance

**Verification**:
```powershell
# Check VirtIO drivers loaded
Get-WmiObject Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*VirtIO*"}

# Verify MSI interrupts
C:\h2kvm\performance\msi-verify.ps1

# Check TRIM enabled
fsutil behavior query DisableDeleteNotification
```

**Solutions**:
1. Verify VirtIO drivers installed correctly
2. Enable MSI interrupts if not already enabled
3. For SSD storage, verify TRIM enabled
4. Check KVM host configuration (CPU pinning, huge pages)

### Application Compatibility Issues

**Symptom**: Application fails to start or function incorrectly

**Steps**:
1. Review compatibility report: `cat compatibility-report.md`
2. For hardware-dependent apps: Contact vendor for license transfer
3. For license services: Verify license server connectivity
4. For SQL Server: Run reconfiguration script
5. For dongles: Configure USB passthrough in KVM

### Event Viewer Errors

**Common errors after migration**:

| Event ID | Source | Meaning | Solution |
|----------|--------|---------|----------|
| 10016 | DistributedCOM | DCOM permissions | Usually harmless, can be ignored |
| 7031 | Service Control Manager | Service crashed | Check specific service logs |
| 1014 | DNS Client | DNS resolution failed | Verify DNS settings |
| 6005 | EventLog | System started | Normal, indicates successful boot |

---

## Additional Resources

- [Windows Configuration Schema Reference](../reference/windows-configuration-schema.md)
- [Application Compatibility Schema](../reference/windows-appcompat-schema.md)
- [Performance Optimization Schema](../reference/windows-performance-schema.md)
- [VirtIO Drivers Documentation](../os-support/windows/virtio-drivers.md)
- [Advanced Windows Support Roadmap](../roadmap/Advanced-Windows-Support.md)

---

## Support

For issues or questions:

1. **Check logs**: `/var/log/h2kvm/migration.log`
2. **Review documentation**: [https://github.com/h2kvm/docs](https://github.com/h2kvm/docs)
3. **Report bugs**: [https://github.com/h2kvm/issues](https://github.com/h2kvm/issues)

---

**Version**: v0.5.0
**Last Updated**: 2026-03-29
**Status**: Production-Ready
