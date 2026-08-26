# Operating System Support

Comprehensive guides for migrating specific operating systems to KVM with H2KVM.

## Quick Navigation

### 🐧 Linux Distributions
- **[RHEL/CentOS](rhel-10.md)** - Red Hat Enterprise Linux 7-10, CentOS 7-9
- **[Ubuntu](ubuntu-2404.md)** - Ubuntu 18.04-24.04, Debian 10-12
- **[SUSE](suse.md)** - SUSE Linux Enterprise, openSUSE Leap/Tumbleweed
- **[Photon OS](photon-os.md)** - VMware Photon OS 3.0-5.0

### 🪟 Windows
- **[Windows Guide](windows/guide.md)** - Complete Windows migration guide (7-11, Server 2008-2025)
- **[Driver Injection](windows/driver-injection.md)** - VirtIO driver installation
- **[Boot Cycle](windows/boot-cycle.md)** - Windows boot process and fixes
- **[Networking](windows/networking.md)** - Network configuration
- **[Troubleshooting](windows/troubleshooting.md)** - Windows-specific issues

---

## Supported Operating Systems

### Linux Distributions

| OS Family | Versions | Status | Documentation |
|-----------|----------|--------|---------------|
| **RHEL/CentOS** | 7, 8, 9, 10 | ✅ Fully Tested | [Guide](rhel-10.md) |
| **Ubuntu** | 18.04, 20.04, 22.04, 24.04 | ✅ Fully Tested | [Guide](ubuntu-2404.md) |
| **Debian** | 10, 11, 12 | ✅ Tested | [Ubuntu Guide](ubuntu-2404.md) |
| **SUSE/SLES** | 15 SP1-SP6 | ✅ Tested | [Guide](suse.md) |
| **openSUSE** | Leap 15+, Tumbleweed | ✅ Tested | [Guide](suse.md) |
| **Photon OS** | 3.0, 4.0, 5.0 | ✅ Fully Tested | [Guide](photon-os.md) |
| **Oracle Linux** | 7, 8, 9 | ✅ Compatible | [RHEL Guide](rhel-10.md) |
| **Rocky Linux** | 8, 9 | ✅ Compatible | [RHEL Guide](rhel-10.md) |
| **AlmaLinux** | 8, 9 | ✅ Compatible | [RHEL Guide](rhel-10.md) |
| **Fedora** | 35+ | ✅ Compatible | [RHEL Guide](rhel-10.md) |
| **Amazon Linux** | 2, 2023 | ✅ Compatible | [RHEL Guide](rhel-10.md) |

### Windows

| OS Version | Status | VirtIO Support | Documentation |
|------------|--------|----------------|---------------|
| **Windows 11** | ✅ Fully Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Windows 10** | ✅ Fully Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Windows 8.1** | ✅ Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Windows 7** | ✅ Tested | ✅ Manual | [Guide](windows/guide.md) |
| **Server 2025** | ✅ Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Server 2022** | ✅ Fully Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Server 2019** | ✅ Fully Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Server 2016** | ✅ Fully Tested | ✅ Automatic | [Guide](windows/guide.md) |
| **Server 2012 R2** | ✅ Tested | ✅ Manual | [Guide](windows/guide.md) |
| **Server 2012** | ✅ Tested | ⚠️ Limited | [Guide](windows/guide.md) |

### BSD (Community Supported)

| OS | Versions | Status | Notes |
|----|----------|--------|-------|
| **FreeBSD** | 12+, 13+ | 🔶 Community | Basic support, manual fixes may be required |
| **OpenBSD** | 7+ | 🔶 Community | Limited testing |

---

## OS-Specific Features

### RHEL/CentOS
✅ Automatic SELinux context fixing
✅ Subscription Manager preservation
✅ XFS UUID regeneration
✅ LVM support
✅ Network scripts → NetworkManager migration

**See**: [RHEL Guide](rhel-10.md)

### Ubuntu/Debian
✅ Netplan configuration
✅ systemd-networkd support
✅ Cloud-init preservation
✅ snap package compatibility
✅ AppArmor profile handling

**See**: [Ubuntu Guide](ubuntu-2404.md)

### SUSE/openSUSE
✅ YaST configuration preservation
✅ Btrfs support
✅ AutoYaST compatibility
✅ Zypper repository migration

**See**: [SUSE Guide](suse.md)

### Photon OS
✅ tdnf package manager support
✅ systemd-networkd configuration
✅ Lightweight footprint preservation
✅ Container runtime compatibility

**See**: [Photon OS Guide](photon-os.md)

### Windows
✅ VirtIO driver automatic injection
✅ Registry modification
✅ Boot sector fixes
✅ Network adapter configuration
✅ Service dependency handling

**See**: [Windows Guide](windows/guide.md)

---

## Migration Compatibility Matrix

### Bootloader Support

| OS | BIOS/Legacy | UEFI | Secure Boot |
|----|-------------|------|-------------|
| **RHEL/CentOS** | ✅ Full | ✅ Full | ✅ Full |
| **Ubuntu** | ✅ Full | ✅ Full | ✅ Full |
| **SUSE** | ✅ Full | ✅ Full | ✅ Full |
| **Photon OS** | ✅ Full | ✅ Full | ⚠️ Manual |
| **Windows** | ✅ Full | ✅ Full | ⚠️ Manual |

### Filesystem Support

| Filesystem | Linux | Windows | Auto-Fix |
|------------|-------|---------|----------|
| **ext4** | ✅ Full | N/A | ✅ Yes |
| **xfs** | ✅ Full | N/A | ✅ Yes (UUID regen) |
| **btrfs** | ✅ Full | N/A | ✅ Yes |
| **LVM** | ✅ Full | N/A | ✅ Yes |
| **NTFS** | N/A | ✅ Full | ✅ Yes |
| **ReFS** | N/A | ✅ Basic | ⚠️ Limited |

### Network Configuration

| OS | NetworkManager | systemd-networkd | Other |
|----|----------------|------------------|-------|
| **RHEL 9+** | ✅ Default | ✅ Supported | - |
| **Ubuntu 22.04+** | ✅ Supported | ✅ Netplan | ✅ Netplan |
| **SUSE** | ✅ Wicked | ✅ Supported | ✅ Wicked |
| **Photon OS** | - | ✅ Default | - |
| **Windows** | - | - | ✅ Native |

---

## Testing Status by OS

### Comprehensive Testing (500+ Migrations)

```
Linux Distributions:   385 migrations (96.5% success rate)
├── RHEL/CentOS:      120 (98% success)
├── Ubuntu/Debian:     95 (97% success)
├── SUSE/openSUSE:     60 (95% success)
├── Photon OS:         45 (94% success)
└── Other Linux:       65 (96% success)

Windows Systems:      115 migrations (94% success rate)
├── Windows 10/11:     45 (96% success)
├── Server 2016-2022:  50 (95% success)
├── Server 2012:       15 (90% success)
└── Legacy (<2012):     5 (80% success)
```

**See**: [Test Results](../test-results/README.md)

---

## Common Scenarios by OS

### RHEL/CentOS

**Scenario**: Clone Fix (Duplicate XFS UUIDs)

```yaml
command: local
vmdk: /vmware/rhel9-clone.vmdk
output_dir: /kvm/vms
to_output: rhel9-fixed.qcow2

# XFS UUID regeneration
xfs_regenerate_uuid: true
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

**See**: [RHEL Guide](rhel-10.md#common-issues)

### Ubuntu

**Scenario**: Cloud-init VM

```yaml
command: local
vmdk: /vmware/ubuntu-cloud.vmdk
output_dir: /kvm/vms
to_output: ubuntu-cloud.qcow2

# Preserve cloud-init
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
# cloud-init automatically preserved
```

**See**: [Ubuntu Guide](ubuntu-2404.md#cloud-init)

### Windows Server

**Scenario**: Active Directory Domain Controller

```yaml
command: local
vmdk: /vmware/dc01.vmdk
output_dir: /kvm/vms
to_output: dc01.qcow2

# Windows with careful driver injection
windows_drivers: true
fstab_mode: stabilize-all
# grub is auto-handled

# Don't compress (faster first boot)
compress: false
```

**See**: [Windows Guide](windows/guide.md#domain-controllers)

---

## Known Issues & Workarounds

### Linux

**Issue**: NetworkManager network names change
**Workaround**: Pre-configure with MAC address matching
**See**: [Troubleshooting](../guides/troubleshooting.md#network-names)

**Issue**: SELinux relabeling required
**Workaround**: Automatic or manual `touch /.autorelabel`
**See**: [RHEL Guide](rhel-10.md#selinux)

### Windows

**Issue**: Windows activation may be required
**Workaround**: Use MAK or KMS reactivation
**See**: [Windows Guide](windows/guide.md#activation)

**Issue**: BitLocker encrypted disks not supported
**Workaround**: Disable BitLocker, migrate, re-enable
**See**: [Windows Troubleshooting](windows/troubleshooting.md#bitlocker)

---

## OS-Specific Recipes

Quick migration recipes for each OS:

### Quick Linux Recipe

```bash
sudo h2kvmctl --config << EOF
command: local
vmdk: /vmware/linux-vm.vmdk
output_dir: /kvm/vms
to_output: linux-vm.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
compress: true
EOF
```

### Quick Windows Recipe

```bash
sudo h2kvmctl --config << EOF
command: local
vmdk: /vmware/windows-vm.vmdk
output_dir: /kvm/vms
to_output: windows-vm.qcow2
windows_drivers: true
fstab_mode: stabilize-all
compress: true
EOF
```

**See**: [Migration Recipes](../recipes/README.md)

---

## Performance by OS

### Boot Time After Migration

| OS | First Boot | Subsequent Boots |
|----|------------|------------------|
| **RHEL 9** | 30-45s | 15-20s |
| **Ubuntu 24.04** | 25-35s | 12-18s |
| **SUSE 15** | 35-50s | 18-25s |
| **Photon OS** | 10-15s | 5-8s |
| **Windows 11** | 60-90s | 30-45s |
| **Server 2022** | 50-70s | 25-35s |

### Migration Time Estimates

| OS Type | Size | Time |
|---------|------|------|
| **Linux (minimal)** | 10 GB | 5-8 min |
| **Linux (desktop)** | 30 GB | 15-20 min |
| **Linux (server)** | 50 GB | 25-35 min |
| **Windows (minimal)** | 25 GB | 15-20 min |
| **Windows (desktop)** | 50 GB | 30-40 min |
| **Windows (server)** | 80 GB | 45-60 min |

---

## Getting Help

### Documentation
- **[Main Documentation](../index.md)** - Complete documentation hub
- **[Tutorials](../tutorials/)** - Step-by-step guides
- **[Migration Recipes](../recipes/)** - Quick solutions
- **[Troubleshooting](../guides/troubleshooting.md)** - Common issues
- **[FAQ](../FAQ.md)** - Frequently asked questions

### Support
- **GitHub Issues**: [Report OS-specific bugs](https://github.com/ssahani/h2kvm/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/ssahani/h2kvm/discussions)

### Testing
- **[Test Results](../test-results/)** - Detailed test results by OS
- **[Test Reports](../test-results/README.md)** - Success rates and statistics

---

## Contributing OS Documentation

Help us improve OS support documentation:

### Add a New OS

1. **Create guide**: `docs/os-support/your-os.md`
2. **Test migrations**: Document success rate
3. **Note issues**: Document known issues and workarounds
4. **Add examples**: Include working configurations
5. **Update this README**: Add to supported OS list

### Improve Existing Guides

1. **Test more versions**: Expand version coverage
2. **Document edge cases**: Add troubleshooting tips
3. **Add examples**: More real-world scenarios
4. **Update status**: Keep testing status current

**See**: [Contributing Guide](../development/contributing.md)

---

## What's Next?

Choose your OS to get started:

### 🐧 I'm migrating Linux
→ Check OS-specific guides above

### 🪟 I'm migrating Windows
→ Start with [Windows Guide](windows/guide.md)

### 🎓 I want to learn first
→ Try [Tutorials](../tutorials/01-beginner-migration.md)

### 🍳 I want quick recipes
→ See [Migration Recipes](../recipes/README.md)

---

## Quick Links

### Performance & Features
- **[LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - Technical details on 7x faster LVM activation
- **[LVM Test Results](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Production-ready test validation
- **[Migration Recipes](../recipes/README.md)** - Quick migration patterns

### Test Results
- **[openSUSE Leap 15.4](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md#opensuse-leap-154-test-btrfs-multi-subvolume)** - btrfs multi-subvolume test (100% success)
- **[RHEL 8.8](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md#rhel-88-test-full-pipeline)** - XFS on LVM test (100% success)
- **[All Test Results](../test-results/README.md)** - Comprehensive test reports

---

**Last Updated**: March 29, 2026
**Version**: 0.3.0
**Total OS Coverage**: 15+ operating systems
**Success Rate**: 96%+ across all Linux, 94%+ Windows
**LVM Performance**: 7x faster activation with 100% host protection
