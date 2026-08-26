# Windows Migration Best Practices

**Version**: v0.5.0+
**Last Updated**: 2026-03-29
**Audience**: System Administrators, DevOps Engineers, IT Architects

This guide documents recommended approaches and best practices for Windows VM migrations using hyper2kvm in various enterprise scenarios.

---

## Table of Contents

1. [General Best Practices](#general-best-practices)
2. [Pre-Migration Planning](#pre-migration-planning)
3. [Migration Strategies](#migration-strategies)
4. [Domain-Joined Systems](#domain-joined-systems)
5. [Application Servers](#application-servers)
6. [Database Servers](#database-servers)
7. [High-Availability Environments](#high-availability-environments)
8. [Security Considerations](#security-considerations)
9. [Performance Optimization](#performance-optimization)
10. [Testing and Validation](#testing-and-validation)
11. [Rollback Planning](#rollback-planning)
12. [Documentation and Handoff](#documentation-and-handoff)

---

## General Best Practices

### 1. Always Test First

**Never migrate production systems without testing**:

```yaml
# Test migration workflow
1. Create test VM clone
2. Migrate test VM to KVM
3. Validate all functionality
4. Document issues and solutions
5. Only then migrate production
```

**Test environments should match production**:
- Same Windows version and patch level
- Same applications and services
- Same network configuration
- Same Active Directory integration

### 2. Maintain Source VM Backups

**Keep original VMs until migration fully validated**:

```bash
# Create backup before migration
cp source.vmdk source-backup-$(date +%Y%m%d).vmdk

# Or use snapshots (if on VMware)
vim-cmd vmsvc/snapshot.create <vmid> "pre-migration" "Before KVM migration"
```

**Retention recommendation**:
- Test migrations: 7 days
- Production migrations: 30-90 days
- Mission-critical systems: Until next successful backup cycle

### 3. Schedule Maintenance Windows

**Plan migrations during approved maintenance windows**:

| System Type | Recommended Window | Duration |
|-------------|-------------------|----------|
| Workstations | Evening/weekend | 2-4 hours |
| Application Servers | Weekend | 4-8 hours |
| Database Servers | Planned outage | 8-12 hours |
| Domain Controllers | Staged/phased | Multiple windows |

### 4. Communicate with Stakeholders

**Notification timeline**:
- **2 weeks before**: Initial notification, impact assessment
- **1 week before**: Detailed plan, rollback procedures
- **24 hours before**: Final confirmation, contact information
- **During migration**: Status updates every 2 hours
- **After completion**: Validation results, known issues

### 5. Use Version Control for Configurations

```bash
# Store migration configurations in git
git init windows-migrations
cd windows-migrations

# Create configuration per VM
cat > web-server-01.yaml <<EOF
command: local
vmdk: /data/vms/web-server-01.vmdk
...
EOF

# Commit and tag
git add web-server-01.yaml
git commit -m "Add web-server-01 migration config"
git tag -a web-server-01-v1 -m "Initial migration"
```

---

## Pre-Migration Planning

### Inventory and Assessment

**Create comprehensive inventory**:

```yaml
# vm-inventory.yaml
vms:
  - name: web-server-01
    os: Windows Server 2019 Standard
    role: IIS Web Server
    domain: company.com
    applications:
      - IIS 10.0
      - .NET Framework 4.8
    license_type: Volume/KMS
    network:
      ip: 192.168.1.100
      gateway: 192.168.1.1
      dns: [10.0.0.10, 10.0.0.11]
    storage:
      size: 100GB
      type: SSD
    dependencies:
      - sql-server-01 (database)
      - ad-dc-01 (authentication)
    migration_priority: high
    maintenance_window: Saturday 22:00-06:00
```

**Use hyper2kvm inspect**:

```bash
# Automated inspection
hyper2kvm inspect web-server-01.vmdk > web-server-01-inspection.json

# Extract key information
jq '.os_info, .installed_apps, .network_config' web-server-01-inspection.json
```

### Risk Assessment

**Classify VMs by risk level**:

| Risk Level | Criteria | Approach |
|-----------|----------|----------|
| **Low** | Non-domain, standard apps, DHCP | Batch migration, minimal planning |
| **Medium** | Domain-joined, business apps | Individual migration, testing required |
| **High** | SQL Server, critical services | Extensive planning, staged migration |
| **Critical** | Domain controllers, SAP, Oracle | Pilot program, vendor involvement |

### Dependency Mapping

```bash
# Create dependency graph
# Example: Visio, draw.io, or text format

Web Tier:
  - web-server-01 ──> sql-server-01
  - web-server-02 ──> sql-server-01

App Tier:
  - app-server-01 ──> sql-server-01
                  ──> license-server-01

Data Tier:
  - sql-server-01 ──> backup-server-01

Infrastructure:
  - All ──> ad-dc-01, ad-dc-02
  - All ──> dns-server-01
```

**Migration order**: Migrate from bottom up (infrastructure → data → app → web)

---

## Migration Strategies

### Strategy 1: Phased Migration (Recommended)

**Approach**: Migrate VMs in phases, validating each phase before proceeding

```yaml
Phase 1 (Week 1): Non-production test systems
  - dev-web-01
  - dev-app-01
  - test-db-01

Phase 2 (Week 2): Non-critical production
  - intranet-server
  - file-server-01

Phase 3 (Week 3): Business applications
  - app-server-01
  - app-server-02

Phase 4 (Week 4): Databases and critical systems
  - sql-server-01 (with failover)
  - web-server-01
```

**Benefits**:
- Learn from early migrations
- Minimize risk
- Allow for process refinement

### Strategy 2: Parallel Operation (Cutover)

**Approach**: Run old and new systems in parallel, then cutover

```yaml
Steps:
1. Migrate VM to KVM
2. Keep source VM powered off (but intact)
3. Run migrated VM in KVM for validation period (1-2 weeks)
4. If successful, decommission source VM
5. If issues, fall back to source VM
```

**Best for**:
- High-risk systems
- Long validation periods required
- Regulatory compliance needs

### Strategy 3: Big Bang Migration (Not Recommended)

**Approach**: Migrate all systems simultaneously

**Only consider if**:
- Very small environment (<10 VMs)
- Extended maintenance window available (weekend)
- All systems low-risk
- Rollback plan tested

---

## Domain-Joined Systems

### Best Practice: Use Unattended Domain Rejoin

**Preparation**:

```powershell
# On domain controller or admin workstation
# Pre-provision computer accounts

# For each VM
djoin.exe /provision `
  /domain company.com `
  /machine WEB-SERVER-01 `
  /savefile C:\djoin\web-server-01.txt `
  /printblob

# Repeat for all VMs
djoin.exe /provision /domain company.com /machine WEB-SERVER-02 /savefile C:\djoin\web-server-02.txt
djoin.exe /provision /domain company.com /machine APP-SERVER-01 /savefile C:\djoin\app-server-01.txt
```

**Migration configuration**:

```yaml
# web-server-01-config.yaml
windows:
  activedirectory:
    extract_domain_info: true
    rejoin_method: unattended
    domain: company.com
    ou_path: "OU=Web Servers,OU=Production,DC=company,DC=com"
    unattended_join_file: /data/djoin/web-server-01.txt
```

**Benefits**:
- No credentials in VM
- Atomic domain join
- Suitable for automation
- Reduced manual intervention

### Best Practice: Clean Up Stale Computer Objects

**Automate cleanup**:

```yaml
windows:
  activedirectory:
    cleanup_old_computer: true
    old_computer_name: "{{ source_vm_hostname }}"
```

**Manual cleanup for safety**:

```powershell
# On domain controller
Get-ADComputer -Filter {Name -eq "OLD-SERVER-NAME"} | Remove-ADComputer -Confirm:$true
```

### Best Practice: Stagger Domain Controller Migrations

**Never migrate all DCs simultaneously**:

```yaml
Week 1: Migrate DC-03 (PDC emulator NOT on this DC)
  - Validate replication
  - Monitor for 48 hours

Week 2: Migrate DC-02
  - Validate replication
  - Monitor for 48 hours

Week 3: Migrate DC-01 (if PDC emulator, transfer roles first)
  - Transfer FSMO roles to DC-02
  - Migrate DC-01
  - Transfer roles back if needed
```

---

## Application Servers

### Best Practice: Application Compatibility Assessment

**Before migration**:

```yaml
windows:
  appcompat:
    detect_hardware_apps: true
    detect_license_services: true
    detect_dongle_drivers: true
    generate_report: true
```

**Review report and plan mitigation**:

```bash
# Review compatibility findings
cat app-server-01-compatibility.md

# Plan mitigation for each finding
# Example:
# - AutoCAD → Contact Autodesk for license transfer
# - FlexLM → Verify license server connectivity post-migration
# - HASP dongle → Configure USB passthrough
```

### Best Practice: License Manager Servers

**For FlexLM, Sentinel, etc.**:

1. **Document license configuration**:
   ```bash
   # Backup license files
   cp /opt/flexlm/licenses/*.lic /backup/flexlm-licenses/

   # Document server name and ports
   echo "License server: license.company.com:27000" > license-config.txt
   ```

2. **Coordinate with vendor**:
   - Notify vendor of migration
   - Request license transfer if needed
   - Verify hostname requirements

3. **Test client connectivity**:
   ```bash
   # After migration, test from client
   telnet license-server.company.com 27000
   ```

### Best Practice: Multi-Tier Applications

**Migrate in reverse dependency order**:

```yaml
1. Migrate license servers first
2. Migrate database tier
3. Migrate application tier
4. Migrate web/presentation tier
5. Update load balancers last
```

**Staged cutover example**:

```yaml
Week 1: Migrate app-server-01 (but keep offline)
Week 2: Migrate app-server-02 (but keep offline)
Week 3: Cutover both simultaneously during maintenance window
Week 4: Decommission source VMs
```

---

## Database Servers

### Best Practice: SQL Server Migration Planning

**Pre-migration checklist**:

```yaml
- [ ] Document instance names and versions
- [ ] Backup all databases (full + transaction logs)
- [ ] Document linked servers
- [ ] Document replication topology (if any)
- [ ] Document SQL Agent jobs
- [ ] Document SSIS/SSRS configurations
- [ ] Test backup restoration
- [ ] Plan hostname strategy
```

**Hostname consideration**:

```yaml
Option 1: Keep same hostname (RECOMMENDED)
  - Minimal application impact
  - No connection string changes
  - Requires: cleanup_old_computer: true

Option 2: New hostname
  - SQL Server requires reconfiguration
  - sp_dropserver / sp_addserver
  - Update all connection strings
  - Update linked servers
  - Update replication
```

**Migration configuration**:

```yaml
windows:
  appcompat:
    detect_sql_server: true
    generate_sql_script: true

  performance:
    # Critical for database performance
    trim:
      enable: true
      schedule_optimization: true
    msi:
      enable: true
      devices:
        - viostor  # Important for I/O performance
```

**Post-migration SQL Server tasks**:

```sql
-- Run generated reconfiguration script
-- C:\hyper2kvm\appcompat\sql-reconfigure.sql

-- Verify server name
SELECT @@SERVERNAME, SERVERPROPERTY('ServerName');

-- If names don't match:
EXEC sp_dropserver '<old-name>';
GO
EXEC sp_addserver '<new-name>', 'local';
GO
-- Restart SQL Server

-- Update statistics
EXEC sp_updatestats;

-- Rebuild indexes if needed
EXEC sp_MSforeachtable 'DBCC DBREINDEX(''?'')';

-- Verify databases
SELECT name, state_desc, recovery_model_desc FROM sys.databases;
```

### Best Practice: High-Performance Database Configuration

**KVM host configuration**:

```bash
# CPU pinning for dedicated cores
virsh vcpupin sql-server-01 0 4
virsh vcpupin sql-server-01 1 5
virsh vcpupin sql-server-01 2 6
virsh vcpupin sql-server-01 3 7

# Huge pages for memory
echo 2048 > /proc/sys/vm/nr_hugepages

# VM huge pages configuration
virsh edit sql-server-01
# Add:
<memoryBacking>
  <hugepages/>
</memoryBacking>

# Direct I/O for storage
virsh edit sql-server-01
# Ensure:
<driver name='qemu' type='qcow2' cache='none' io='native'/>
```

### Best Practice: Oracle Database Migration

**Special considerations for Oracle**:

1. **Oracle licensing** - CPU/core count matters
2. **RAC environments** - May not be suitable for virtualization
3. **Vendor support** - Verify Oracle supports KVM

**If proceeding**:

```yaml
1. Contact Oracle support FIRST
2. Verify licensing implications
3. Test extensively before production
4. Consider Oracle VM as alternative
```

---

## High-Availability Environments

### Best Practice: Cluster-Aware Migration

**Windows Failover Clustering**:

```yaml
1. Migrate passive node first
2. Test failover to migrated node
3. Migrate active node
4. Test failback
5. Verify cluster functionality
```

**Example: SQL Server Always On AG**:

```yaml
Week 1: Migrate secondary replica (SQL-02)
  - Monitor replication
  - Validate synchronization
  - Test application connectivity

Week 2: Planned failover to SQL-02
  - Failover AG to SQL-02 (now on KVM)
  - Monitor for 48 hours

Week 3: Migrate primary replica (SQL-01)
  - SQL-02 (on KVM) is primary
  - Migrate SQL-01
  - Test synchronization

Week 4: Failback if desired
  - Or leave SQL-02 as primary
```

### Best Practice: Load-Balanced Web Servers

**Rolling migration approach**:

```yaml
1. Remove web-server-01 from load balancer pool
2. Migrate web-server-01 to KVM
3. Test web-server-01 functionality
4. Add web-server-01 back to load balancer
5. Verify traffic distribution
6. Repeat for web-server-02
7. Continue for remaining servers
```

**Load balancer configuration**:

```bash
# Before migration
haproxy stats:
  web-server-01: UP (VMware)
  web-server-02: UP (VMware)

# During migration
haproxy stats:
  web-server-01: UP (KVM) ← migrated
  web-server-02: UP (VMware)

# After migration
haproxy stats:
  web-server-01: UP (KVM)
  web-server-02: UP (KVM)
```

---

## Security Considerations

### Best Practice: Credential Management

**Never store credentials in configurations**:

```yaml
# BAD - Don't do this
activedirectory:
  rejoin_method: credential
  vc_user: "domain\\admin"  # NEVER HARDCODE
  password: "P@ssw0rd123!"   # NEVER HARDCODE

# GOOD - Use unattended or prompt
activedirectory:
  rejoin_method: unattended
  unattended_join_file: /secure/djoin-blob.txt  # Provisioned separately
```

**Secure djoin blob storage**:

```bash
# Store djoin blobs securely
mkdir -p /secure/djoin
chmod 700 /secure/djoin

# Copy djoin blobs
cp *.txt /secure/djoin/
chmod 600 /secure/djoin/*.txt
```

### Best Practice: License Key Protection

**Extracted license keys are sensitive**:

```bash
# Encrypt license reports
openssl enc -aes-256-cbc -salt -in license-report.json -out license-report.json.enc

# Decrypt when needed
openssl enc -d -aes-256-cbc -in license-report.json.enc -out license-report.json
```

### Best Practice: Network Segmentation

**Maintain network security boundaries**:

```yaml
# Ensure VMs maintain same network segment
Production VMs:
  - Before: VLAN 100 (192.168.100.0/24)
  - After:  VLAN 100 (192.168.100.0/24)

# KVM host network configuration
virsh net-define production-network.xml

# production-network.xml
<network>
  <name>production-vlan100</name>
  <forward mode='bridge'/>
  <bridge name='br-vlan100'/>
</network>
```

### Best Practice: Antivirus Compatibility

**Test antivirus on KVM**:

```yaml
Common enterprise antivirus:
  - Symantec Endpoint Protection ✓ Compatible
  - McAfee VirusScan Enterprise ✓ Compatible
  - Trend Micro OfficeScan ✓ Compatible
  - Sophos Endpoint ✓ Compatible
  - Windows Defender ✓ Compatible

May require:
  - Agent update after migration
  - Policy refresh
  - Reactivation with management server
```

---

## Performance Optimization

### Best Practice: Enable All Performance Features

**Recommended baseline configuration**:

```yaml
windows:
  performance:
    balloon:
      enable: true
      memory_stats_interval: 10
      free_page_reporting: true  # Windows Server 2019+, Win10 1809+

    trim:
      enable: true
      schedule_optimization: true

    msi:
      enable: true
      devices:
        - viostor
        - netkvm

    hyperv:
      cleanup: true  # If migrating from Hyper-V
```

### Best Practice: Storage Performance Tuning

**KVM host storage configuration**:

```yaml
# Use direct I/O for best performance
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native' discard='unmap'/>
  <source file='/data/kvm/server.qcow2'/>
  <target dev='vda' bus='virtio'/>
</disk>

# For best performance: use virtio-scsi
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native' discard='unmap'/>
  <source file='/data/kvm/server.qcow2'/>
  <target dev='sda' bus='scsi'/>
  <address type='drive' controller='0' bus='0' target='0' unit='0'/>
</disk>

<controller type='scsi' index='0' model='virtio-scsi'/>
```

**Windows guest storage optimization**:

```powershell
# Disable write-cache buffer flushing (if on UPS)
fsutil behavior set DisableDeleteNotification 0

# Optimize page file settings
# Recommendation: Fixed size = 1.5x RAM
$RAM = (Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory / 1MB
$PageFileSize = [math]::Round($RAM * 1.5)
$pagefile = Get-WmiObject Win32_PageFileSetting
$pagefile.InitialSize = $PageFileSize
$pagefile.MaximumSize = $PageFileSize
$pagefile.Put()
```

### Best Practice: Network Performance Tuning

**Enable multiqueue**:

```xml
<!-- KVM host network configuration -->
<interface type='network'>
  <source network='default'/>
  <model type='virtio'/>
  <driver name='vhost' queues='4'/>
</interface>
```

**Windows guest network tuning**:

```powershell
# Enable Receive-Side Scaling (RSS)
Set-NetAdapterRss -Name "Ethernet" -Enabled $true

# Configure RSS queues
Set-NetAdapterRss -Name "Ethernet" -NumberOfReceiveQueues 4

# Increase buffer sizes
Set-NetAdapterAdvancedProperty -Name "Ethernet" -DisplayName "Receive Buffers" -DisplayValue 2048
Set-NetAdapterAdvancedProperty -Name "Ethernet" -DisplayName "Transmit Buffers" -DisplayValue 2048
```

---

## Testing and Validation

### Best Practice: Comprehensive Testing Checklist

**Boot and initialization**:
- [ ] Windows boots successfully
- [ ] No BSOD or boot errors
- [ ] Boot time acceptable (<3 minutes for Server, <2 minutes for workstation)
- [ ] All services start correctly

**Drivers and hardware**:
- [ ] All VirtIO drivers loaded (balloon, netkvm, viostor)
- [ ] No unknown devices in Device Manager
- [ ] No driver warnings in Event Viewer

**Licensing**:
- [ ] Windows activation successful
- [ ] License type correct (OEM, Retail, MAK, KMS)
- [ ] slmgr /dli shows "Licensed"

**Active Directory**:
- [ ] Domain membership verified
- [ ] User can login with domain credentials
- [ ] Group Policy applied correctly
- [ ] Computer object in correct OU

**Networking**:
- [ ] IP configuration correct (static or DHCP)
- [ ] Gateway reachable
- [ ] DNS resolution working
- [ ] Domain controller reachable
- [ ] External connectivity working

**Storage**:
- [ ] All drives accessible
- [ ] Disk I/O performance acceptable
- [ ] TRIM enabled (for SSD)
- [ ] Free space matches expectations

**Applications**:
- [ ] All services running
- [ ] Application functionality tested
- [ ] Database connectivity working
- [ ] Web services responding
- [ ] License servers accessible (if applicable)

**Performance**:
- [ ] CPU utilization normal
- [ ] Memory utilization normal
- [ ] Disk I/O performance acceptable
- [ ] Network throughput acceptable
- [ ] No performance warnings in Event Viewer

### Best Practice: Automated Validation Scripts

**Create validation script**:

```powershell
# validate-migration.ps1

function Test-Migration {
    $Results = @()

    # Test Windows activation
    $Activation = (slmgr.vbs /dli | Select-String "Licensed").Count -gt 0
    $Results += [PSCustomObject]@{
        Test = "Windows Activation"
        Result = if ($Activation) { "PASS" } else { "FAIL" }
    }

    # Test domain membership
    $Domain = (Get-WmiObject Win32_ComputerSystem).PartOfDomain
    $Results += [PSCustomObject]@{
        Test = "Domain Membership"
        Result = if ($Domain) { "PASS" } else { "FAIL" }
    }

    # Test VirtIO drivers
    $VirtIODrivers = Get-WmiObject Win32_PnPSignedDriver | Where-Object {
        $_.DeviceName -like "*VirtIO*" -or $_.DeviceName -like "*Red Hat*"
    }
    $Results += [PSCustomObject]@{
        Test = "VirtIO Drivers"
        Result = if ($VirtIODrivers.Count -gt 0) { "PASS ($($VirtIODrivers.Count) drivers)" } else { "FAIL" }
    }

    # Test network connectivity
    $Gateway = Test-NetConnection -ComputerName (Get-NetRoute -DestinationPrefix "0.0.0.0/0").NextHop -InformationLevel Quiet
    $Results += [PSCustomObject]@{
        Test = "Gateway Connectivity"
        Result = if ($Gateway) { "PASS" } else { "FAIL" }
    }

    # Test DNS
    $DNS = (Resolve-DnsName google.com -ErrorAction SilentlyContinue) -ne $null
    $Results += [PSCustomObject]@{
        Test = "DNS Resolution"
        Result = if ($DNS) { "PASS" } else { "FAIL" }
    }

    # Test TRIM
    $TRIM = (fsutil behavior query DisableDeleteNotification | Select-String "DisableDeleteNotification = 0").Count -gt 0
    $Results += [PSCustomObject]@{
        Test = "TRIM Enabled"
        Result = if ($TRIM) { "PASS" } else { "WARN" }
    }

    # Display results
    $Results | Format-Table -AutoSize

    # Return overall result
    $FailCount = ($Results | Where-Object { $_.Result -eq "FAIL" }).Count
    if ($FailCount -eq 0) {
        Write-Host "`nMigration validation: SUCCESSFUL" -ForegroundColor Green
        return 0
    } else {
        Write-Host "`nMigration validation: FAILED ($FailCount failures)" -ForegroundColor Red
        return 1
    }
}

Test-Migration
```

---

## Rollback Planning

### Best Practice: Maintain Rollback Capability

**Rollback readiness checklist**:

```yaml
- [ ] Source VM backup exists and verified
- [ ] Source VM hypervisor (VMware/Hyper-V) still available
- [ ] Rollback procedure documented
- [ ] Rollback can complete within maintenance window
- [ ] Key stakeholders aware of rollback triggers
- [ ] Communication plan for rollback scenario
```

**Rollback triggers**:

```yaml
Immediate rollback required if:
  - VM fails to boot
  - Critical application non-functional
  - Data corruption detected
  - Performance degradation >50%

Planned rollback within 24 hours if:
  - Multiple non-critical issues
  - Unexpected application behavior
  - User acceptance testing fails
  - Performance degradation 25-50%
```

**Rollback procedure**:

```bash
# 1. Shutdown KVM VM
virsh shutdown windows-server

# 2. Power on source VM (VMware/Hyper-V)
vim-cmd vmsvc/power.on <vmid>

# 3. Verify source VM functionality
# 4. Update DNS/load balancers if needed
# 5. Document rollback reason
# 6. Schedule re-migration attempt
```

---

## Documentation and Handoff

### Best Practice: Comprehensive Documentation

**Create migration runbook per VM**:

```markdown
# web-server-01 Migration Runbook

## VM Information
- Hostname: web-server-01
- OS: Windows Server 2019 Standard
- IP: 192.168.1.100
- Domain: company.com
- Applications: IIS 10.0, .NET 4.8

## Migration Date
- Planned: 2026-02-15 22:00
- Actual: 2026-02-15 22:15
- Completed: 2026-02-16 02:30

## Issues Encountered
1. Network adapter not detected initially
   - Solution: Installed VirtIO network driver manually
   - Time: 30 minutes

2. License activation failed
   - Solution: Manually ran reactivation script
   - Time: 15 minutes

## Post-Migration Changes
- IP address: unchanged
- Hostname: unchanged
- Domain membership: re-joined successfully
- Applications: all functional

## Validation Results
- Boot time: 1m 45s (acceptable)
- Application response time: normal
- Network throughput: 1 Gbps (expected)
- Disk I/O: normal

## Handoff Notes
- VM running on kvm-host-02
- Monitored for 48 hours, no issues
- Source VM powered off, retained for 30 days
- Scheduled for decommissioning: 2026-03-17
```

### Best Practice: Knowledge Transfer

**Operational handoff checklist**:

```yaml
- [ ] VM location documented (which KVM host)
- [ ] Performance baselines established
- [ ] Monitoring configured
- [ ] Backup schedule verified
- [ ] Support team trained on KVM management
- [ ] Known issues documented
- [ ] Emergency contacts updated
```

---

## Summary: Migration Checklist Template

```yaml
Pre-Migration:
  - [ ] VM inventory complete
  - [ ] Risk assessment done
  - [ ] Dependencies mapped
  - [ ] Test migration successful
  - [ ] Stakeholders notified
  - [ ] Maintenance window approved
  - [ ] Rollback plan documented
  - [ ] Backup verified

Migration:
  - [ ] Source VM shutdown gracefully
  - [ ] Migration config reviewed
  - [ ] hyper2kvm conversion started
  - [ ] Progress monitored
  - [ ] Conversion completed successfully
  - [ ] KVM VM created
  - [ ] First boot successful

Post-Migration:
  - [ ] Validation script run
  - [ ] License activated
  - [ ] Domain rejoined
  - [ ] Applications tested
  - [ ] Performance verified
  - [ ] Monitoring enabled
  - [ ] Backup scheduled
  - [ ] Documentation updated
  - [ ] Stakeholders notified

Decommissioning (after retention period):
  - [ ] Source VM verified unused
  - [ ] Backups available elsewhere
  - [ ] Approval obtained
  - [ ] Source VM deleted
  - [ ] License reclaimed (if applicable)
  - [ ] Documentation archived
```

---

## Additional Resources

- [Windows Migration Guide](./windows-migration-guide.md)
- [Windows Troubleshooting Runbook](./windows-troubleshooting-runbook.md)
- [Windows Configuration Schema](../reference/windows-configuration-schema.md)

---

**Version**: v0.5.0
**Last Updated**: 2026-03-29
**Status**: Production-Ready
