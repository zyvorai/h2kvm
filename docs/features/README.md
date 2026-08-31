# Features Documentation

Comprehensive documentation for all H2KVM features and capabilities.

## Performance Highlights (v2.2.0+)

**Enterprise LVM Improvements:**
- ✅ **7x Faster LVM Activation** - 0.71s vs 5-10s for traditional methods
- ✅ **100% Host Protection** - Device-filtered VG activation prevents corruption
- ✅ **Production Validated** - RHEL 8.8 and openSUSE Leap 15.4 tested
- 📖 **[Technical Guide](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - Architecture details
- 📊 **[Test Results](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Validation reports

## Quick Navigation

### 🔧 Core Features
- **[GuestKit Integration](../architecture/GUESTKIT.md)** - Offline disk inspect and repair
- **[XFS UUID Regeneration](xfs-uuid-regeneration.md)** - Fix cloned VMware VMs
- **[fstab Stabilization](fstab-stabilization.md)** - Automatic fstab repair
- **[Enhanced Chroot](enhanced-chroot.md)** - Advanced filesystem access

### 🔍 Inspection & Validation
- **[VMDK Inspector](vmdk-inspector.md)** - Analyze VMDK files pre-migration
- **[VMDK Validation](vmdk-validation.md)** - Pre-migration validation checks
- **[BusLogic Auto-Fix](buslogic-auto-fix.md)** - Legacy SCSI controller handling

### 🔄 Daemon & Automation
- **[Daemon Mode](daemon-mode.md)** - Background daemon operation
- **[Daemon Architecture](daemon-architecture.md)** - Design and components
- **[Daemon Enhancements](daemon-enhancements.md)** - Advanced daemon features
- **[Daemon User Guide](daemon-user-guide.md)** - Complete daemon usage

### ⚙️ System Integration
- **[Systemd Integration](systemd-integration.md)** - Service management
- **[Configuration Injection](configuration-injection.md)** - Dynamic configuration

### ☁️ Cloud & Virtualization
- **[vSphere Export](vsphere-export.md)** - VMware vSphere integration
- **[vSphere Design](vsphere-design.md)** - vSphere architecture

### 📦 GuestKit

- **[GuestKit Integration Guide](../architecture/GUESTKIT.md)** — install, configure, pipeline integration
- **[LVM Backends](../architecture/LVM_BACKENDS.md)** — LVM activation during offline fixes
- **[Backends](../architecture/BACKENDS.md)** — `guestkit`, `guestfs`, `auto`

---

## Features by Category

### 🎯 Essential Features (Start Here)

| Feature | Description | Status | Difficulty |
|---------|-------------|--------|------------|
| **[GuestKit Integration](../architecture/GUESTKIT.md)** | Offline disk inspect and repair | ✅ Production | ⭐⭐ |
| **[fstab Stabilization](fstab-stabilization.md)** | Automatic fstab repair | ✅ Production | ⭐ |
| **[Enhanced Chroot](enhanced-chroot.md)** | Advanced filesystem access | ✅ Production | ⭐⭐ |
| **[VMDK Inspector](vmdk-inspector.md)** | Pre-migration analysis | ✅ Production | ⭐ |

### 🔧 Boot & Filesystem Features

| Feature | Use Case | Documentation |
|---------|----------|---------------|
| **XFS UUID Regeneration** | Fix cloned VMware VMs with duplicate UUIDs | [Guide](xfs-uuid-regeneration.md) |
| **fstab Stabilization** | Auto-repair fstab, convert to UUID/LABEL | [Guide](fstab-stabilization.md) |
| **Enhanced Chroot** | Safe filesystem access with full isolation | [Guide](enhanced-chroot.md) |
| **BusLogic Auto-Fix** | Handle legacy BusLogic SCSI controllers | [Guide](buslogic-auto-fix.md) |

### 🔍 Validation & Inspection

| Feature | Purpose | Documentation |
|---------|---------|---------------|
| **VMDK Inspector** | Analyze VMDK structure, detect issues | [Guide](vmdk-inspector.md) |
| **VMDK Validation** | Pre-migration compatibility checks | [Guide](vmdk-validation.md) |

### 🔄 Automation & Daemon

| Feature | Capability | Documentation |
|---------|-----------|---------------|
| **Daemon Mode** | Background processing, job queue | [Guide](daemon-mode.md) |
| **Daemon Architecture** | Design patterns, components | [Guide](daemon-architecture.md) |
| **Daemon Enhancements** | Advanced features, monitoring | [Guide](daemon-enhancements.md) |
| **Daemon User Guide** | Complete usage guide | [Guide](daemon-user-guide.md) |

### ⚙️ System & Configuration

| Feature | Function | Documentation |
|---------|----------|---------------|
| **Systemd Integration** | Service management, auto-start | [Guide](systemd-integration.md) |
| **Configuration Injection** | Dynamic config generation | [Guide](configuration-injection.md) |

### ☁️ Cloud & Virtualization Integration

| Platform | Features | Documentation |
|----------|----------|---------------|
| **vSphere** | Export, fetch, integration | [Export](vsphere-export.md), [Design](vsphere-design.md) |

---

## GuestKit engine

### Overview

GuestKit is H2KVM's native Python VM manipulation engine and the default guestfs backend, with **480+ APIs** for guest filesystem operations without requiring external C dependencies.

**Key Capabilities:**
- ✅ **Direct filesystem access** - Native Python, no C dependencies
- ✅ **480+ APIs** - Comprehensive guest manipulation
- ✅ **OS detection** - Automatic operating system identification
- ✅ **Package management** - yum, dnf, apt, zypper support
- ✅ **Configuration editing** - Augeas integration
- ✅ **Windows support** - Registry, driver injection
- ✅ **LVM support** - Logical volume management
- ✅ **Performance optimized** - Caching, lazy loading

**Documentation:**
- **[Complete Guide](architecture/GUESTKIT.md)** - Full GuestKit documentation
- **[Advanced Features](architecture/GUESTKIT.md)** - Expert-level usage
- **[OS Detection](architecture/GUESTKIT.md)** - OS identification system
- **[Windows Support](os-support/windows/README.md)** - Windows-specific features

**Specialized Guides:**
- **[Augeas Guide](architecture/GUESTKIT.md)** - Configuration file editing
- **[LVM Guide](architecture/LVM_BACKENDS.md)** - Logical volume management
- **[Partition Management](architecture/GUESTKIT.md)** - Disk partitioning
- **[Performance Guide](architecture/GUESTKIT.md)** - Optimization techniques

---

## Feature Highlights

### 1. XFS UUID Regeneration

**Problem**: Cloned VMware VMs often have duplicate XFS filesystem UUIDs, causing boot failures.

**Solution**: Automatic UUID regeneration with fstab updates.

```yaml
command: local
vmdk: /vmware/cloned-vm.vmdk
output_dir: /kvm/vms
to_output: fixed-vm.qcow2

# Enable XFS UUID fix
xfs_regenerate_uuid: true
fstab_mode: stabilize-all
```

**See**: [XFS UUID Regeneration Guide](xfs-uuid-regeneration.md)

---

### 2. fstab Stabilization

**Problem**: VMDKs use device names (/dev/sda1) which may change in KVM.

**Solution**: Automatic conversion to UUID or LABEL-based mounting.

**Modes:**
- `stabilize-all`: Convert all entries to UUID
- `uuid-only`: Only update UUID entries
- `label-fallback`: Prefer UUID, fallback to LABEL
- `preserve`: Keep original entries

```yaml
fstab_mode: stabilize-all
```

**See**: [fstab Stabilization Guide](fstab-stabilization.md)

---

### 3. Enhanced Chroot

**Problem**: Standard chroot is unsafe and can affect host system.

**Solution**: Isolated chroot environment with proper cleanup.

**Features:**
- Automatic mount/unmount of /proc, /sys, /dev
- Safe cleanup even on errors
- Nested chroot support
- Resource isolation

**See**: [Enhanced Chroot Guide](enhanced-chroot.md)

---

### 4. VMDK Inspector

**Problem**: Need to analyze VMDK before migration to detect issues.

**Solution**: Comprehensive VMDK analysis tool.

**Capabilities:**
- Disk geometry inspection
- Partition table analysis
- Filesystem detection
- OS detection
- Issue identification
- Migration recommendations

```bash
# Inspect VMDK
./scripts/vmdk_inspect.py /path/to/vm.vmdk

# With auto-fix recommendations
./scripts/vmdk_inspect.py /path/to/vm.vmdk --auto-fix
```

**See**: [VMDK Inspector Guide](vmdk-inspector.md)

---

### 5. Daemon Mode

**Problem**: Need background processing and job queue for large-scale migrations.

**Solution**: Full-featured daemon with REST API.

**Features:**
- Background job processing
- REST API for job submission
- Job queue with priorities
- Progress tracking
- Metrics and monitoring
- Systemd integration

```bash
# Start daemon
h2kvm daemon start

# Submit job
h2kvm daemon submit migration.yaml

# Check status
h2kvm daemon status
```

**See**: [Daemon Mode Guide](daemon-mode.md), [Daemon User Guide](daemon-user-guide.md)

---

## Feature Comparison

### GuestKit Highlights

| Feature | GuestKit |
|---------|---------|
| **Language** | Pure Python |
| **Dependencies** | Minimal (qemu-nbd, qemu-img) |
| **APIs** | 480+ |
| **Windows Support** | Native |
| **Performance** | Optimized (NBD-based) |
| **Installation** | pip install |
| **Portability** | High |

### Migration Modes

| Mode | Downtime | Use Case | Features |
|------|----------|----------|----------|
| **Standard** | Full | Most migrations | Complete feature set |
| **Live Fix** | <5 seconds | Production VMs | SSH-based, minimal downtime |
| **Daemon** | Scheduled | Batch migrations | Queue, scheduling, monitoring |

---

## Common Feature Combinations

### Combination 1: Safe Linux Migration

```yaml
command: local
vmdk: /vmware/linux-vm.vmdk
output_dir: /kvm/vms
to_output: linux-vm.qcow2

# Essential features
fstab_mode: stabilize-all
xfs_regenerate_uuid: true
regen_initramfs: true
# grub is auto-handled
```

**Features Used**: fstab stabilization, XFS UUID regen, enhanced chroot

---

### Combination 2: VMware Clone Fix

```yaml
command: local
vmdk: /vmware/cloned-vm.vmdk
output_dir: /kvm/vms
to_output: fixed-clone.qcow2

# Clone-specific fixes
xfs_regenerate_uuid: true
fstab_mode: stabilize-all
regen_initramfs: true
```

**Features Used**: XFS UUID regeneration, fstab stabilization

---

### Combination 3: Production Migration with Validation

```bash
# 1. Inspect VMDK
./scripts/vmdk_inspect.py /vmware/prod-vm.vmdk --auto-fix

# 2. Run migration with all features
h2kvm --config << EOF
command: local
vmdk: /vmware/prod-vm.vmdk
output_dir: /kvm/vms
to_output: prod-vm.qcow2
fstab_mode: stabilize-all
xfs_regenerate_uuid: true
regen_initramfs: true
# grub is auto-handled
compress: true
EOF
```

**Features Used**: VMDK inspector, fstab stabilization, XFS UUID, enhanced chroot

---

## Feature Status

### Production Ready ✅

| Feature | Version | Status |
|---------|---------|--------|
| GuestKit engine | 1.0+ | ✅ Stable |
| fstab Stabilization | 1.0+ | ✅ Stable |
| XFS UUID Regen | 1.0+ | ✅ Stable |
| Enhanced Chroot | 1.0+ | ✅ Stable |
| VMDK Inspector | 1.3+ | ✅ Stable |
| VMDK Validation | 1.3+ | ✅ Stable |
| Daemon Mode | 1.0+ | ✅ Stable |
| Systemd Integration | 1.0+ | ✅ Stable |
| vSphere Export | 1.0+ | ✅ Stable |
| BusLogic Auto-Fix | 1.3+ | ✅ Stable |

### Beta Features 🔶

| Feature | Version | Status |
|---------|---------|--------|
| Configuration Injection | 2.0+ | 🔶 Beta |

---

## Performance Characteristics

### GuestKit Performance

| Operation | Speed | Notes |
|-----------|-------|-------|
| **OS Detection** | <1 sec | Cached after first detection |
| **Package Query** | 1-2 sec | Database operations |
| **File Read** | Fast | Direct filesystem access |
| **File Write** | Fast | Optimized I/O |
| **Chroot Setup** | <1 sec | One-time per session |

### Feature Overhead

| Feature | Time Impact | When to Use |
|---------|-------------|-------------|
| **fstab Stabilization** | +2-5 sec | Always (essential) |
| **XFS UUID Regen** | +5-30 sec | VMware clones only |
| **VMDK Inspection** | +10-30 sec | Pre-migration analysis |
| **VMDK Validation** | +5-15 sec | Pre-migration checks |

---

## Best Practices

### Essential Features (Always Use)

✅ **fstab Stabilization**: Prevents boot failures from device name changes
✅ **Enhanced Chroot**: Safe filesystem access
✅ **VMDK Inspector**: Identify issues before migration

### Conditional Features (Use When Needed)

🔶 **XFS UUID Regeneration**: Use for VMware clones
🔶 **BusLogic Auto-Fix**: Use for VMs with BusLogic SCSI
🔶 **Daemon Mode**: Use for batch migrations
🔶 **vSphere Export**: Use for VMware vSphere integration

### Performance Features

⚡ **GuestKit Caching**: Enabled by default
⚡ **Lazy Loading**: Reduces memory usage
⚡ **Parallel Processing**: Use batch mode for multiple VMs

---

## Feature Development

### Contributing New Features

1. **Identify need**: Use case and user request
2. **Design**: Architecture and API design
3. **Implement**: Code with tests
4. **Document**: Feature guide and examples
5. **Test**: Integration and unit tests
6. **Release**: Version and changelog

**See**: [Contributing Guide](../development/contributing.md)

---

## Related Documentation

### Before Using Features
- **[Getting Started](../getting-started/)** - Installation and setup
- **[Tutorials](../tutorials/)** - Step-by-step learning

### While Using Features
- **[User Guides](../guides/)** - Task-oriented guides
- **[Recipes](../recipes/)** - Quick solutions
- **[Troubleshooting](../guides/troubleshooting.md)** - Fix issues

### After Using Features
- **[API Reference](../reference/api/)** - Complete API docs
- **[Testing Guide](../development/testing-guide.md)** - Testing features

---

## Feature Requests

Have an idea for a new feature?

1. **Check existing features**: Review this documentation
2. **Search issues**: [GitHub Issues](https://github.com/ssahani/h2kvm/issues)
3. **Create feature request**: [New Feature Request](https://github.com/ssahani/h2kvm/issues/new)
4. **Discuss**: [GitHub Discussions](https://github.com/ssahani/h2kvm/discussions)

---

## What's Next?

Choose your area of interest:

### 🔧 I want to use GuestKit
→ Read [GuestKit integration guide](architecture/GUESTKIT.md)

### 🔍 I want to inspect VMDKs
→ See [VMDK Inspector](vmdk-inspector.md)

### 🔄 I want automation
→ Try [Daemon Mode](daemon-mode.md)

### ⚙️ I want system integration
→ Check [Systemd Integration](systemd-integration.md)

### 📚 I want complete reference
→ See [API Reference](../reference/api/API-Reference.md)

### 🚀 I want performance optimization
→ Read [LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)

---

**Last Updated**: March 29, 2026
**Version**: 0.3.0
**Total Features**: 20+
**Production Ready**: 15+
**GuestKit APIs**: 480+
**LVM Performance**: 7x faster with 100% host protection
