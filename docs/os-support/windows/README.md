# Windows Migration Documentation

Complete documentation for migrating Windows VMs from VMware/Hyper-V to KVM.

---

## Quick Links

### 📖 Core Documentation
- **[Windows Migration Guide](guide.md)** - Complete step-by-step Windows migration guide
- **[Driver Injection](driver-injection.md)** - VirtIO driver injection process
- **[Boot Cycle](boot-cycle.md)** - Windows boot process on KVM
- **[Networking](networking.md)** - Windows network configuration
- **[Troubleshooting](troubleshooting.md)** - Common Windows migration issues

---

## VirtIO Drivers: Auto-Discovery

The VirtIO Windows drivers ISO is **automatically discovered** at the standard path:

```
/var/lib/h2kvm/virtio-win.iso
```

**Easiest setup** -- run once and forget:

```bash
sudo ./scripts/install-deps.sh --virtio-win
```

This downloads the ISO to the standard location. After that, h2kvm finds it automatically -- no `--virtio-drivers-dir` flag or `virtio_drivers_dir` YAML key needed.

To use a different ISO location, pass `--virtio-drivers-dir /your/path/to/virtio-win.iso` as an override.

---

## Documentation Overview

### Windows Migration Guide
**File**: [guide.md](guide.md)

**Complete Windows migration walkthrough**:
- Prerequisites and host setup
- First boot validation (SATA + UEFI)
- VirtIO driver installation
- Boot-to-VirtIO transition
- Driver injection model
- Registry editing (offline)
- CriticalDeviceDatabase (CDD) handling
- BCD (Boot Configuration Data) handling

**Supported Windows Versions**:
- **Client**: Windows 12, 11, 10, 8.1, 7
- **Server**: Server 2025, 2022, 2019, 2016, 2012 R2, 2012

**Use when**: Migrating any Windows VM to KVM

---

### Driver Injection Guide
**File**: [driver-injection.md](driver-injection.md)

**VirtIO driver injection process**:
- Supported driver classes (storage, network, SCSI, balloon, serial)
- Offline driver injection (before first boot)
- Online driver installation (after boot)
- Registry modification for boot drivers
- Service configuration
- CriticalDeviceDatabase updates

**Driver Types Supported**:
- **viostor** - VirtIO SCSI storage driver (boot-critical)
- **vioscsi** - VirtIO SCSI controller driver
- **NetKVM** - VirtIO network adapter driver
- **vioser** - VirtIO serial driver
- **Balloon** - Memory ballooning driver

**Use when**: Preparing Windows for VirtIO or troubleshooting driver issues

---

### Boot Cycle Documentation
**File**: [boot-cycle.md](boot-cycle.md)

**Windows boot process on KVM**:
- UEFI vs BIOS boot
- Boot manager (bootmgr) process
- BCD (Boot Configuration Data) structure
- Disk controller detection
- Driver loading sequence
- INACCESSIBLE_BOOT_DEVICE prevention

**Boot Strategies**:
1. **SATA First Boot** (Recommended) - Boot with SATA, install drivers, switch to VirtIO
2. **VirtIO Direct Boot** - Pre-inject drivers for direct VirtIO boot
3. **IDE Fallback** - Legacy compatibility for older Windows

**Use when**: Understanding Windows boot on KVM or troubleshooting boot failures

---

### Networking Configuration
**File**: [networking.md](networking.md)

**Windows network setup on KVM**:
- VirtIO network driver installation
- Network adapter configuration
- Static IP vs DHCP
- DNS configuration
- Network troubleshooting
- Performance optimization

**Network Modes**:
- **NAT** - Simple outbound connectivity
- **Bridge** - Full network access
- **Host-only** - Isolated network
- **Macvtap** - High-performance bridge alternative

**Use when**: Configuring Windows networking or troubleshooting connectivity

---

### Troubleshooting Guide
**File**: [troubleshooting.md](troubleshooting.md)

**Common Windows migration issues**:
- INACCESSIBLE_BOOT_DEVICE errors
- Black screen on boot
- Permission denied errors
- VirtIO driver issues
- Network connectivity problems
- Performance issues
- UEFI boot failures

**Troubleshooting Tools**:
- Event Viewer analysis
- Safe Mode boot
- Driver verification
- Registry inspection
- BCD troubleshooting

**Use when**: Diagnosing and fixing Windows migration issues

---

## Windows Migration Workflow

### Standard Migration Path

```
┌────────────────────────────────────────┐
│  Phase 1: CONVERSION                   │
│  ├─ Convert VMDK to qcow2              │
│  ├─ Extract VirtIO drivers (offline)   │
│  └─ Prepare UEFI boot environment      │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Phase 2: FIRST BOOT (SATA)            │
│  ├─ Boot with SATA/AHCI controller     │
│  ├─ Verify Windows boots successfully  │
│  └─ Validate system stability          │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Phase 3: DRIVER INSTALLATION          │
│  ├─ Install VirtIO drivers in guest    │
│  ├─ Verify driver installation         │
│  └─ Reboot to load drivers             │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Phase 4: SWITCH TO VIRTIO             │
│  ├─ Shutdown Windows VM                │
│  ├─ Change disk bus to VirtIO          │
│  ├─ Change NIC model to VirtIO         │
│  └─ Boot with VirtIO devices           │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Phase 5: VALIDATION                   │
│  ├─ Verify boot with VirtIO            │
│  ├─ Test network connectivity          │
│  ├─ Validate performance               │
│  └─ Production readiness check         │
└────────────────────────────────────────┘
```

---

## Quick Start Paths

### Path 1: First Windows Migration (1-2 hours)

**Goal**: Migrate a Windows VM and get it booting

```bash
# 1. Read Windows Migration Guide
docs/os-support/windows/guide.md

# 2. Convert VM with driver injection
h2kvm local \
  --vmdk /vms/windows.vmdk \
  --output-dir /vms/converted \
  --to-output windows.qcow2 \
  --windows-inject-virtio

# 3. Create SATA boot XML (from guide)
docs/os-support/windows/guide.md - Prerequisites section

# 4. First boot with SATA
virsh define windows-sata.xml
virsh start windows

# 5. Install VirtIO drivers
docs/os-support/windows/driver-injection.md

# 6. Switch to VirtIO
docs/os-support/windows/guide.md - After Windows boots section
```

**Recommended**: [Windows Migration Guide](guide.md)

---

### Path 2: Troubleshooting Boot Issues (30 minutes - 2 hours)

**Goal**: Fix Windows boot problems

```bash
# 1. Identify issue type
docs/os-support/windows/troubleshooting.md

# 2. Check boot cycle
docs/os-support/windows/boot-cycle.md

# 3. Verify drivers
docs/os-support/windows/driver-injection.md

# 4. Apply fix from troubleshooting guide
docs/os-support/windows/troubleshooting.md - Specific issue section
```

**Recommended**: [Troubleshooting](troubleshooting.md) + [Boot Cycle](boot-cycle.md)

---

### Path 3: Production Deployment (4-8 hours)

**Goal**: Deploy Windows migrations at scale

```bash
# 1. Understand complete process
docs/os-support/windows/guide.md

# 2. Set up automation
docs/guides/migration/batch-features.md

# 3. Configure driver injection
docs/os-support/windows/driver-injection.md

# 4. Test boot process
docs/os-support/windows/boot-cycle.md

# 5. Prepare networking
docs/os-support/windows/networking.md

# 6. Create runbook
docs/guides/operations/MIGRATION_RUNBOOK_TEMPLATE.md
```

**Recommended**: All Windows docs + [Batch Features](../../guides/migration/batch-features.md)

---

## Windows-Specific Challenges

### Challenge 1: INACCESSIBLE_BOOT_DEVICE

**Problem**: Windows blue screens with INACCESSIBLE_BOOT_DEVICE when booting with VirtIO

**Solution**:
1. Boot with SATA first (safe controller)
2. Install VirtIO drivers in guest
3. Switch to VirtIO after drivers loaded

**Documentation**: [Guide](guide.md) - Common failure prevented + [Troubleshooting](troubleshooting.md)

---

### Challenge 2: Driver Injection Timing

**Problem**: When to inject drivers - offline or online?

**Solutions**:
- **Offline Injection**: Before first boot (requires GuestKit access to Windows registry)
- **Online Installation**: After booting with SATA (safer, recommended)

**Documentation**: [Driver Injection](driver-injection.md)

---

### Challenge 3: UEFI vs BIOS Boot

**Problem**: Windows boot mode mismatch

**Solution**:
- Check source VM boot mode (UEFI or BIOS)
- Match boot mode on target KVM
- Use OVMF for UEFI, SeaBIOS for BIOS

**Documentation**: [Boot Cycle](boot-cycle.md) + [Guide](guide.md)

---

### Challenge 4: Network Driver Loading

**Problem**: Network doesn't work after migration

**Solution**:
1. Install NetKVM driver (VirtIO network)
2. Configure network adapter in Windows
3. Validate DNS and routing

**Documentation**: [Networking](networking.md)

---

## Windows Version Support Matrix

| Windows Version | Status | Notes |
|----------------|--------|-------|
| **Windows 12** | ✅ Full | Latest client OS |
| **Windows 11** | ✅ Full | Requires TPM 2.0 emulation |
| **Windows 10** | ✅ Full | All editions supported |
| **Windows 8.1** | ✅ Full | Legacy support |
| **Windows 7** | ⚠️ Limited | EOL, basic support |
| **Server 2025** | ✅ Full | Latest server OS |
| **Server 2022** | ✅ Full | Full support |
| **Server 2019** | ✅ Full | Full support |
| **Server 2016** | ✅ Full | Full support |
| **Server 2012 R2** | ✅ Full | Full support |
| **Server 2012** | ⚠️ Limited | EOL, basic support |

---

## Boot Strategy Comparison

| Strategy | Safety | Speed | Complexity | Use Case |
|----------|--------|-------|------------|----------|
| **SATA First** | ✅✅✅ High | ⚠️ Slower | ✅ Simple | Recommended for first migration |
| **VirtIO Direct** | ⚠️ Medium | ✅✅ Fast | ⚠️⚠️ Complex | Production with tested process |
| **IDE Fallback** | ✅✅ High | ❌ Slowest | ✅ Simple | Legacy Windows (7, Server 2008) |

---

## VirtIO Driver Types

### Boot-Critical Drivers

**Must be present for Windows to boot**:
- **viostor** - VirtIO SCSI storage driver (highest priority)
- **vioscsi** - VirtIO SCSI controller driver

**Installation**: Must be injected offline OR boot with SATA first

---

### Post-Boot Drivers

**Can be installed after Windows boots**:
- **NetKVM** - VirtIO network adapter
- **vioser** - VirtIO serial port
- **Balloon** - Memory ballooning
- **qxldod** - Display driver

**Installation**: Install in guest OS via Device Manager or installer

---

## Common Commands

### Convert with VirtIO Injection
```bash
# If virtio-win.iso is at /var/lib/h2kvm/virtio-win.iso (auto-discovered):
h2kvm local \
  --vmdk /vms/windows.vmdk \
  --output-dir /vms/output \
  --to-output windows.qcow2 \
  --windows-inject-virtio \
  --out-format qcow2

# To override with a custom ISO path:
h2kvm local \
  --vmdk /vms/windows.vmdk \
  --output-dir /vms/output \
  --to-output windows.qcow2 \
  --windows-inject-virtio \
  --virtio-drivers-dir /custom/path/virtio-win.iso \
  --out-format qcow2
```

---

### Create UEFI Boot XML
```xml
<domain type='kvm'>
  <name>windows-vm</name>
  <memory unit='GiB'>4</memory>
  <vcpu>2</vcpu>
  <os firmware='efi'>
    <type arch='x86_64' machine='q35'>hvm</type>
    <boot dev='hd'/>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/vms/windows.qcow2'/>
      <target dev='sda' bus='sata'/>  <!-- SATA for first boot -->
    </disk>
  </devices>
</domain>
```

---

### Switch to VirtIO After Driver Install
```xml
<!-- Change bus from 'sata' to 'virtio' -->
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2'/>
  <source file='/vms/windows.qcow2'/>
  <target dev='vda' bus='virtio'/>  <!-- Changed to virtio -->
</disk>
```

---

## Integration with Other Documentation

### Pre-Migration
- **[Migration Decision Tree](../../guides/decision-support/MIGRATION_DECISION_TREE.md)** - Choose approach
- **[Pre-Flight Validation](../../guides/operations/PRE_FLIGHT_VALIDATION.md)** - Verify readiness
- **[Best Practices](../../guides/operations/BEST_PRACTICES.md)** - Windows-specific practices

### During Migration
- **[Windows Migration Guide](guide.md)** - Step-by-step process
- **[CLI Reference](../../guides/cli/reference.md)** - Command syntax
- **[Migration Playbooks](../../guides/migration/playbooks.md)** - Workflow examples

### Post-Migration
- **[Monitoring Guide](../../guides/operations/MONITORING_GUIDE.md)** - Windows monitoring
- **[Troubleshooting](troubleshooting.md)** - Issue resolution
- **[Troubleshooting Flowchart](../../guides/decision-support/TROUBLESHOOTING_FLOWCHART.md)** - Diagnostic paths

---

## Related Features

### Windows-Specific Features
- **[VirtIO Driver Injection](../../features/virtio-driver-injection.md)** - Automated driver injection
- **[Windows Registry Editing](../../features/windows-registry.md)** - Offline registry modification
- **[BCD Management](../../features/bcd-management.md)** - Boot configuration editing

### General Features
- **[VMDK Inspector](../../features/vmdk-inspector.md)** - Analyze Windows VMDKs
- **[GuestKit](../../features/architecture/GUESTKIT.md)** - Low-level Windows manipulation

---

## Windows Migration Best Practices

### Before Migration
1. ✅ Install VirtIO drivers ISO: `sudo ./scripts/install-deps.sh --virtio-win` (auto-downloads to `/var/lib/h2kvm/virtio-win.iso`)
2. ✅ Document source VM configuration (boot mode, disk layout)
3. ✅ Verify Windows license (volume vs retail)
4. ✅ Check for third-party drivers that may need reinstallation
5. ✅ Create checkpoint/snapshot before migration

### During Migration
1. ✅ Use SATA for first boot (safer)
2. ✅ Inject VirtIO drivers during conversion OR plan for online install
3. ✅ Match UEFI/BIOS mode from source
4. ✅ Allocate sufficient memory (min 2GB for client, 4GB for server)

### After Migration
1. ✅ Verify all drivers loaded correctly
2. ✅ Test network connectivity
3. ✅ Check Windows activation status
4. ✅ Validate application functionality
5. ✅ Remove VMware Tools if present

---

## Summary

**5 comprehensive Windows documentation files** covering:
- ✅ Complete migration guide with SATA-first strategy
- ✅ VirtIO driver injection (offline and online)
- ✅ Windows boot process on KVM
- ✅ Network configuration and troubleshooting
- ✅ Common issues and solutions

**Supported**: Windows 7-12, Server 2012-2025 (20+ versions)

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
**Windows Support**: Production-ready for all modern Windows versions

**Quick Navigation**: [OS Support Hub](../README.md) | [Documentation Hub](../../index.md) | [Troubleshooting](troubleshooting.md)
