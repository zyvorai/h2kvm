# Windows Performance Optimization Schema Reference

**Version**: v0.5.0+
**Module**: Performance Optimization (Phase 3)
**Last Updated**: 2026-03-29

This document describes the configuration schema for Windows performance optimization features, including VirtIO balloon configuration, TRIM/discard enablement, MSI interrupt configuration, and Hyper-V enlightenments removal.

---

## Table of Contents

- [Overview](#overview)
- [Configuration Structure](#configuration-structure)
- [VirtIO Balloon Configuration](#virtio-balloon-configuration)
- [TRIM/Discard Enablement](#trimdiscard-enablement)
- [MSI Interrupt Configuration](#msi-interrupt-configuration)
- [Hyper-V Enlightenments Removal](#hyper-v-enlightenments-removal)
- [Complete Examples](#complete-examples)
- [Performance Benchmarking](#performance-benchmarking)
- [Troubleshooting](#troubleshooting)

---

## Overview

The `windows.performance` configuration section controls performance optimizations for Windows VMs on KVM:

- **VirtIO Balloon**: Dynamic memory management between guest and hypervisor
- **TRIM/Discard**: SSD optimization for improved performance and lifespan
- **MSI Interrupts**: ~20% network throughput improvement via Message Signaled Interrupts
- **Hyper-V Cleanup**: Remove Hyper-V enlightenments when migrating FROM Hyper-V TO KVM

All performance optimizations are **optional** and can be individually enabled/disabled.

---

## Configuration Structure

### Top-Level Schema

```yaml
windows:
  performance:
    # VirtIO balloon driver
    balloon:
      enable: bool                    # Enable balloon configuration (default: true)
      memory_stats_interval: int      # Memory stats interval in seconds (default: 10)
      free_page_reporting: bool       # Enable free page reporting (default: true)

    # TRIM/discard for SSDs
    trim:
      enable: bool                    # Enable TRIM/discard (default: true)
      schedule_optimization: bool     # Schedule automatic optimization (default: true)

    # MSI interrupts
    msi:
      enable: bool                    # Enable MSI interrupts (default: true)
      devices: list[str]              # Devices to configure (default: ["viostor", "netkvm"])

    # Hyper-V cleanup
    hyperv:
      cleanup: bool                   # Enable cleanup (default: false, auto-detect)
      force: bool                     # Force cleanup without detection (default: false)
```

---

## VirtIO Balloon Configuration

Controls VirtIO balloon driver settings for dynamic memory management.

### Schema

```yaml
windows:
  performance:
    balloon:
      enable: true                    # Enable balloon configuration
      memory_stats_interval: 10       # Report memory stats every 10 seconds
      free_page_reporting: true       # Enable free page reporting
```

### Parameters

#### `balloon.enable` (boolean)
**Default**: `true`

Enable VirtIO balloon driver configuration.

**Benefits**:
- Allows hypervisor to reclaim unused guest memory
- Improves memory utilization across VMs
- Enables memory overcommitment

**Example**:
```yaml
windows:
  performance:
    balloon:
      enable: true
```

---

#### `balloon.memory_stats_interval` (integer)
**Default**: `10` seconds

Interval for reporting memory statistics to the hypervisor.

**Valid Range**: `1-3600` seconds

**Recommendations**:
- **10s**: Default, good balance
- **5s**: More responsive, higher overhead
- **30s**: Less overhead, slower response

**Example**:
```yaml
windows:
  performance:
    balloon:
      memory_stats_interval: 10
```

**Registry**: `HKLM\SYSTEM\CurrentControlSet\Services\balloon\Parameters\MemoryStatsInterval`

---

#### `balloon.free_page_reporting` (boolean)
**Default**: `true`

Enable free page reporting for memory reclaim.

**Requirements**: Windows Server 2019+ or Windows 10 1809+

**Benefits**:
- Allows guest to report free pages to hypervisor
- Hypervisor can reclaim truly unused memory
- Improves memory overcommitment efficiency

**Example**:
```yaml
windows:
  performance:
    balloon:
      free_page_reporting: true
```

**Registry**: `HKLM\SYSTEM\CurrentControlSet\Services\balloon\Parameters\FreePageReporting = 1`

---

## TRIM/Discard Enablement

Controls TRIM/discard support for SSD-backed storage.

### Schema

```yaml
windows:
  performance:
    trim:
      enable: true                    # Enable TRIM/discard
      schedule_optimization: true     # Schedule weekly optimization
```

### Parameters

#### `trim.enable` (boolean)
**Default**: `true`

Enable TRIM/discard support for SSDs.

**Benefits**:
- Improves SSD performance
- Extends SSD lifespan
- Reduces write amplification

**Requirements**: Windows 7 and later

**Example**:
```yaml
windows:
  performance:
    trim:
      enable: true
```

**Registry**: `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\DisableDeleteNotification = 0`

**Note**: `DisableDeleteNotification = 0` means TRIM is **enabled**

---

#### `trim.schedule_optimization` (boolean)
**Default**: `true`

Schedule automatic TRIM optimization.

**Behavior**:
- Creates weekly scheduled task
- Runs on Sunday at 2:00 AM
- Uses `defrag.exe /C /L /O`
- Only on Windows 8/Server 2012+

**Example**:
```yaml
windows:
  performance:
    trim:
      schedule_optimization: true
```

**Scheduled Task**: `\Microsoft\Windows\Defrag\H2KVM TRIM Optimization`

---

## MSI Interrupt Configuration

Controls Message Signaled Interrupt (MSI) configuration for VirtIO devices.

### Schema

```yaml
windows:
  performance:
    msi:
      enable: true
      devices:
        - viostor    # VirtIO storage
        - netkvm     # VirtIO network
```

### Parameters

#### `msi.enable` (boolean)
**Default**: `true`

Enable MSI interrupts for VirtIO devices.

**Benefits**:
- ~20% network throughput improvement
- Reduced interrupt latency for storage
- Better CPU utilization

**Example**:
```yaml
windows:
  performance:
    msi:
      enable: true
```

---

#### `msi.devices` (list of strings)
**Default**: `["viostor", "netkvm"]`

List of VirtIO device drivers to configure for MSI.

**Valid Devices**:
- `viostor` - VirtIO block storage driver
- `netkvm` - VirtIO network driver
- `balloon` - VirtIO balloon driver (rarely needs MSI)

**Example**:
```yaml
windows:
  performance:
    msi:
      devices:
        - viostor
        - netkvm
```

**Registry Path**:
```
HKLM\SYSTEM\CurrentControlSet\Services\{device}\Parameters\
  InterruptManagement\MessageSignaledInterruptProperties\MSISupported = 1
```

---

## Hyper-V Enlightenments Removal

Controls removal of Hyper-V enlightenments for Hyper-V → KVM migrations.

### Schema

```yaml
windows:
  performance:
    hyperv:
      cleanup: true      # Enable cleanup (auto-detects Hyper-V)
      force: false       # Force cleanup without detection
```

### Parameters

#### `hyperv.cleanup` (boolean)
**Default**: `false` (auto-detect)

Enable Hyper-V enlightenments cleanup.

**When to Enable**:
- Migrating FROM Hyper-V TO KVM
- VM shows Hyper-V integration services

**Auto-Detection**: If not specified, automatically detects Hyper-V and cleans up if found.

**Example**:
```yaml
windows:
  performance:
    hyperv:
      cleanup: true
```

**Services Disabled** (12 total):
- `vmbus` - Hyper-V Virtual Machine Bus
- `hvservice` - Hyper-V Service
- `vmicheartbeat` - Heartbeat Service
- `vmickvpexchange` - Data Exchange Service
- `vmicshutdown` - Guest Shutdown Service
- `vmictimesync` - Time Synchronization Service
- `vmicvss` - Volume Shadow Copy Requestor
- And 5 more Hyper-V integration services

---

#### `hyperv.force` (boolean)
**Default**: `false`

Force Hyper-V cleanup without auto-detection.

**Use Case**: When auto-detection fails but you know the source was Hyper-V.

**Warning**: Only use if certain the VM came from Hyper-V.

**Example**:
```yaml
windows:
  performance:
    hyperv:
      cleanup: true
      force: true
```

---

## Complete Examples

### Example 1: Default Performance Optimization

```yaml
command: local
vmdk: /data/vms/windows-server.vmdk
to_output: windows-server-kvm.qcow2

windows:
  performance:
    # All defaults - enables balloon, TRIM, MSI
    balloon:
      enable: true
    trim:
      enable: true
    msi:
      enable: true
```

**Use Case**: Standard Windows VM migration with all optimizations

---

### Example 2: Custom Balloon Configuration

```yaml
command: local
vmdk: /data/vms/windows-workstation.vmdk
to_output: windows-workstation-kvm.qcow2

windows:
  performance:
    balloon:
      enable: true
      memory_stats_interval: 30      # Less frequent stats
      free_page_reporting: false     # Disable for older Windows
```

**Use Case**: Windows 7/8 VM where free page reporting not supported

---

### Example 3: SSD-Optimized Configuration

```yaml
command: local
vmdk: /data/vms/database-server.vmdk
to_output: database-server-kvm.qcow2

windows:
  performance:
    trim:
      enable: true
      schedule_optimization: true    # Weekly optimization
    msi:
      enable: true
      devices:
        - viostor                    # MSI for storage only
```

**Use Case**: Database server on SSD storage with storage-focused optimization

---

### Example 4: Hyper-V to KVM Migration

```yaml
command: local
vmdk: /data/vms/hyperv-vm.vmdk
to_output: hyperv-vm-kvm.qcow2

windows:
  performance:
    # Standard optimizations
    balloon:
      enable: true
    trim:
      enable: true
    msi:
      enable: true

    # Hyper-V cleanup
    hyperv:
      cleanup: true                  # Auto-detect and cleanup
```

**Use Case**: Migrating from Hyper-V to KVM

---

### Example 5: Maximum Performance Configuration

```yaml
command: local
vmdk: /data/vms/web-server.vmdk
to_output: web-server-kvm.qcow2

windows:
  performance:
    # Aggressive balloon configuration
    balloon:
      enable: true
      memory_stats_interval: 5       # More responsive
      free_page_reporting: true

    # Full SSD optimization
    trim:
      enable: true
      schedule_optimization: true

    # MSI for all VirtIO devices
    msi:
      enable: true
      devices:
        - viostor
        - netkvm
```

**Use Case**: High-performance web server requiring maximum optimization

---

### Example 6: Selective Optimization

```yaml
command: local
vmdk: /data/vms/legacy-app.vmdk
to_output: legacy-app-kvm.qcow2

windows:
  performance:
    # Enable only TRIM (conservative approach)
    balloon:
      enable: false
    trim:
      enable: true
      schedule_optimization: false   # Manual optimization only
    msi:
      enable: false                  # Avoid MSI for compatibility
```

**Use Case**: Legacy application where minimal changes preferred

---

## Performance Benchmarking

### Expected Improvements

| Optimization | Metric | Improvement |
|-------------|---------|-------------|
| MSI Interrupts | Network throughput | ~20% increase |
| MSI Interrupts | Network latency | ~15% reduction |
| TRIM/Discard | SSD write performance | ~10-30% (over time) |
| TRIM/Discard | SSD lifespan | Extended (varies) |
| VirtIO Balloon | Memory utilization | Varies by workload |

### Verification Scripts

All optimizations generate PowerShell verification scripts:

```
C:\h2kvm\performance\
├── balloon-verify.ps1      # Verify balloon configuration
├── trim-verify.ps1         # Verify TRIM enablement
├── trim-optimize.ps1       # Schedule TRIM optimization
└── msi-verify.ps1          # Verify MSI configuration
```

**Run After Migration**:
```powershell
# Verify all optimizations
cd C:\h2kvm\performance
.\balloon-verify.ps1
.\trim-verify.ps1
.\msi-verify.ps1
```

### Benchmarking Tools

**Network Performance**:
```powershell
# Before MSI
iperf3 -c server -t 60

# After MSI (expect ~20% improvement)
iperf3 -c server -t 60
```

**Storage Performance**:
```powershell
# TRIM verification
fsutil behavior query DisableDeleteNotify

# Expected output:
# DisableDeleteNotify = 0  (TRIM enabled)
```

**Balloon Status**:
```powershell
Get-Service balloon
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\balloon\Parameters"
```

---

## Troubleshooting

### Balloon Driver Not Working

**Symptom**: Balloon service not running or memory not being reclaimed

**Check**:
```powershell
# Verify service status
Get-Service balloon

# Check registry configuration
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\balloon\Parameters"

# View device status
Get-PnpDevice -FriendlyName "*Balloon*"
```

**Common Issues**:
1. **Balloon driver not installed**: Ensure VirtIO drivers injected during migration
2. **Service disabled**: Set Start type to AUTO
3. **Unsupported Windows version**: Free page reporting requires Windows 10 1809+

**Solution**:
```powershell
# Start service manually
Start-Service balloon

# Set to automatic start
Set-Service balloon -StartupType Automatic
```

---

### TRIM Not Enabled

**Symptom**: DisableDeleteNotification = 1 (TRIM disabled)

**Check**:
```powershell
# Query TRIM status
fsutil behavior query DisableDeleteNotify

# Check registry
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" | Select-Object DisableDeleteNotification
```

**Common Issues**:
1. **Not an SSD**: TRIM only works on SSD storage
2. **Windows version too old**: Requires Windows 7 SP1 or later
3. **Storage controller doesn't support discard**: Verify KVM storage backend

**Solution**:
```powershell
# Enable TRIM manually
fsutil behavior set DisableDeleteNotify 0

# Verify
fsutil behavior query DisableDeleteNotify
```

---

### MSI Not Applied

**Symptom**: Network performance not improved after migration

**Check**:
```powershell
# Verify MSI registry keys
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\netkvm\Parameters\InterruptManagement\MessageSignaledInterruptProperties"

Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\viostor\Parameters\InterruptManagement\MessageSignaledInterruptProperties"
```

**Common Issues**:
1. **MSISupported not set to 1**: Registry not updated correctly
2. **Driver doesn't support MSI**: Very old VirtIO drivers
3. **Hypervisor doesn't support MSI**: KVM configuration issue

**Solution**:
```powershell
# Set MSI manually
$Path = "HKLM:\SYSTEM\CurrentControlSet\Services\netkvm\Parameters\InterruptManagement\MessageSignaledInterruptProperties"
Set-ItemProperty -Path $Path -Name "MSISupported" -Value 1 -Type DWord

# Reboot required for changes to take effect
Restart-Computer
```

---

### Hyper-V Services Still Running

**Symptom**: Hyper-V integration services still active after migration

**Check**:
```powershell
# List Hyper-V services
Get-Service | Where-Object {$_.Name -like "vm*" -or $_.Name -like "hv*"}
```

**Common Issues**:
1. **Auto-detection failed**: Hyper-V not detected during migration
2. **Services not disabled**: Registry update failed
3. **Services re-enabled**: Windows Update may re-enable

**Solution**:
```powershell
# Disable Hyper-V services manually
$HyperVServices = @("vmbus", "hvservice", "vmicheartbeat", "vmickvpexchange",
                    "vmicshutdown", "vmictimesync", "vmicvss")

foreach ($Service in $HyperVServices) {
    Stop-Service $Service -Force -ErrorAction SilentlyContinue
    Set-Service $Service -StartupType Disabled -ErrorAction SilentlyContinue
}
```

---

## See Also

- [Advanced Windows Support Roadmap](../roadmap/Advanced-Windows-Support.md)
- [Windows Configuration Schema](../reference/windows-configuration-schema.md)
- [Windows Application Compatibility Schema](../reference/windows-appcompat-schema.md)
- [VirtIO Drivers Documentation](../os-support/windows/virtio-drivers.md)

---

**Version**: v0.5.0
**Last Updated**: 2026-03-29
**Status**: Production-Ready (Phase 3 Complete)
