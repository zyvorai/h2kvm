# 📁 h2kvm Configuration Examples

This directory contains production-ready configuration examples for various migration scenarios, utilizing **h2kvm v0.3.0** with **VMCraft v9.0** capabilities.

## 📑 Table of Contents

- [Local VMDK Conversions (01-05)](#local-vmdk-conversions)
- [vSphere Download-Only (10-11)](#vsphere-download-only)
- [vSphere OVFTool Export (30-31)](#vsphere-ovftool-export)
- [vSphere VDDK Operations (40-41)](#vsphere-vddk-operations)
- [Photon OS Variations (50-53)](#photon-os-variations)
- [LibVirt XML Templates (60-66)](#libvirt-xml-templates)
- [Ubuntu Configurations (70)](#ubuntu-configurations)
- [Windows Drivers (80)](#windows-drivers)
- [Complete Examples (90-92)](#complete-examples)

---

## 🖥️ Local VMDK Conversions

Convert local VMDK files to QCOW2 format with offline fixes.

### 01-local-windows-11-vmdk.yaml
**Windows 11 VMDK → QCOW2 with VirtIO**
- ✅ Offline VirtIO driver injection
- ✅ Registry modification for VirtIO storage
- ✅ QCOW2 compression
- ✅ Checksum generation

```bash
h2kvm --config test-confs/01-local-windows-11-vmdk.yaml local
```

### 01-local-windows-10-vmdk.yaml
**Windows 10 VMDK → QCOW2 with VirtIO**
- ✅ Offline VirtIO driver injection
- ✅ SATA bootstrap mode support
- ✅ Registry fixes

```bash
h2kvm --config test-confs/01-local-windows-10-vmdk.yaml local
```

### 02-local-rhel-10-vmdk.yaml
**RHEL 10 VMDK → QCOW2**
- ✅ UUID-based fstab stabilization
- ✅ GRUB root= fixing
- ✅ Dracut initramfs regeneration
- ✅ SELinux compatibility

```bash
h2kvm --config test-confs/02-local-rhel-10-vmdk.yaml local
```

### 03-local-ubuntu-22-vmdk.yaml
**Ubuntu 22.04 LTS VMDK → QCOW2**
- ✅ UUID-based fstab stabilization
- ✅ update-initramfs regeneration
- ✅ Netplan/systemd compatibility

```bash
h2kvm --config test-confs/03-local-ubuntu-22-vmdk.yaml local
```

### 04-local-photon-os-vmdk.yaml
**VMware Photon OS VMDK → QCOW2**
- ✅ Dracut initramfs regeneration with virtio drivers
- ✅ systemd-networkd compatibility
- ✅ Virtio support verified (ships with drivers built-in)
- ⚠️  Note: "initramfs rebuild failed: mtime+size unchanged" is **normal** - means drivers already present

```bash
sudo ./h2kvmctl --config test-confs/04-local-photon-os-vmdk.yaml
```

**Libvirt Deployment:**
```bash
# Use virtio configuration (recommended)
sudo virsh define test-confs/photon-virtio.xml
sudo virsh start photon-converted

# Or SATA fallback (rarely needed)
sudo virsh define test-confs/photon-sata.xml
sudo virsh start photon-converted
```

**See also:**
- `test-confs/README-photon.md` - Detailed Photon OS guide
- `docs/os-support/photon-os.md` - Complete documentation

---

## ☁️ vSphere Download-Only

Download VM files from vCenter without conversion.

### 10-vsphere-download-only.yaml
**Basic vSphere Download**
- ✅ Concurrent downloads (4 parallel)
- ✅ Selective file patterns (exclude logs/locks)
- ✅ Async HTTP for large files

```bash
export VC_PASSWORD='your-vcenter-password'
h2kvm --config test-confs/10-vsphere-download-only.yaml vsphere
```

### 11-vsphere-govc-rhel-10-download.yaml
**Download using govc/govmomi**
- ✅ govc-based download (alternative to pyvmomi)
- ✅ RHEL 10.1 specific configuration

```bash
export VC_PASSWORD='your-vcenter-password'
h2kvm --config test-confs/11-vsphere-govc-rhel-10-download.yaml vsphere
```

---

## 📦 vSphere OVFTool Export

Export VMs using VMware OVF Tool.

### 30-vsphere-ovftool-rhel-10-ova.yaml
**OVA Export via OVFTool**

### 31-vsphere-ovftool-rhel-10-ovfdir.yaml
**OVF Directory Export via OVFTool**

---

## 💾 vSphere VDDK Operations

Direct disk operations using VMware VDDK.

### 40-vsphere-vddk-download-disk.yaml
**Download VM Disks using VDDK**
- ✅ Fast block-level transfers
- ✅ Incremental copy support

### 41-vsphere-pyvmomi-vddk.yaml
**Force pyvmomi with VDDK**
- ✅ Python-based vSphere access
- ✅ VDDK library integration

---

## 🌟 Photon OS Variations

VMware Photon OS specific configurations.

### 50-photon-os-libvirt.yaml
**Photon OS → LibVirt**

### 51-photon-os-ova.yaml
**Photon OS → OVA**

### 52-photon-os-ami.yaml
**Photon OS AMI → KVM**
- ✅ Download AMI tar.gz from packages.vmware.com
- ✅ Extract raw disk image, convert to qcow2
- ✅ fstab stabilization + initramfs rebuild with VirtIO drivers
- ✅ Libvirt smoke test (UEFI, headless)

```bash
sudo h2kvmctl --config test-confs/52-photon-os-ami.yaml
```

### 53-photon-os-azure-vhd.yaml
**Photon OS → Azure VHD**

---

## 📄 LibVirt XML Templates

Domain XML templates for converted VMs.

### Photon OS Templates

**photon-virtio.xml** - Recommended configuration
- ✅ Virtio disk for best performance
- ✅ SeaBIOS (BIOS mode)
- ✅ VNC graphics
- ✅ Tested and verified

```bash
sudo virsh define test-confs/photon-virtio.xml
sudo virsh start photon-converted
```

**photon-sata.xml** - Fallback configuration
- ⚠️  SATA disk (compatibility mode)
- ⚠️  Only use if virtio fails (rare)
- ✅ SeaBIOS (BIOS mode)
- ✅ VNC graphics

```bash
sudo virsh define test-confs/photon-sata.xml
sudo virsh start photon-converted
```

### Generic Templates

### 60-libvirt-guest-uefi.xml
**Generic UEFI Guest Template**

### 61-libvirt-rhel-10-fixed.xml
**RHEL 10 Post-Conversion Template**

### 62-libvirt-windows-10-fixed.xml
**Windows 10 Post-Conversion Template**

### 63-libvirt-windows-10-sata-uefi.xml
**Windows 10 SATA + UEFI Template**

### 64-libvirt-windows-10-fixed-sata.xml
**Windows 10 SATA (Bootstrap Phase)**

### 65-libvirt-windows-10-fixed-virtio.xml
**Windows 10 VirtIO (Final Phase)**

### 66-libvirt-windows-10-test.xml
**Windows 10 Testing Template**

---

## 🐧 Ubuntu Configurations

### 70-ubuntu-libvirt.yaml
**Ubuntu → LibVirt Conversion**

---

## 🪟 Windows Drivers

### 80-windows-drivers-network.yaml
**Windows Network Driver Configuration**
- ✅ VirtIO network drivers
- ✅ Registry configuration

---

## 📚 Complete Examples

### 90-h2kvm-full-config.yaml
**Comprehensive Configuration Example (YAML)**
- Shows all available options
- Detailed comments

### 91-h2kvm-full-config.json
**Comprehensive Configuration Example (JSON)**
- Same as YAML version in JSON format

### 92-override-nojson.yaml
**YAML Override Example**
- Demonstrates config file merging

---

## 🚀 Quick Start

### 1. Local VMDK Conversion
```bash
# Edit the config to point to your VMDK
vim test-confs/02-local-rhel-10-vmdk.yaml

# Run conversion
h2kvm --config test-confs/02-local-rhel-10-vmdk.yaml local
```

### 2. vSphere Download
```bash
# Set vCenter password
export VC_PASSWORD='your-password'

# Download VM files
h2kvm --config test-confs/10-vsphere-download-only.yaml vsphere
```

---

## 📝 Configuration File Structure

All configuration files follow this structure:

```yaml
# Header with emoji, title, description
# Usage examples
# Feature list
# Requirements

# Main command
cmd: local | vsphere

# Source configuration
vmdk: /path/to/disk.vmdk
# or
vcenter: vcenter.example.com
vm_name: vm-to-convert

# Output configuration
output_dir: /path/to/output
out_format: qcow2
compress: true

# Filesystem fixes
fstab_mode: stabilize-all
regen_initramfs: true
no_grub: false

# Testing (optional)
libvirt_test: false
qemu_test: false
```

---

## 🔧 Customization

To customize a configuration:

1. **Copy the template:**
   ```bash
   cp test-confs/02-local-rhel-10-vmdk.yaml my-config.yaml
   ```

2. **Edit paths and settings:**
   - Update `vmdk:` or `vm_name:`
   - Adjust `output_dir:`
   - Enable/disable features

3. **Run with your config:**
   ```bash
   h2kvm --config my-config.yaml local
   ```

---

## 📖 Documentation

For detailed documentation, see:
- **[docs/03-Quick-Start.md](../docs/03-Quick-Start.md)** - Getting started guide
- **[docs/04-CLI-Reference.md](../docs/04-CLI-Reference.md)** - All CLI options
- **[docs/05-YAML-Examples.md](../docs/05-YAML-Examples.md)** - Configuration examples
- **[docs/06-Cookbook.md](../docs/06-Cookbook.md)** - Common recipes
- **[docs/09-VMCraft.md](../docs/09-VMCraft.md)** - VMCraft Platform (307+ methods) ⭐ NEW

---

## 🆘 Support & Troubleshooting

### Common Issues

#### "initramfs rebuild failed: mtime+size unchanged"
**This is normal for cloud-native distributions like Photon OS.**
- ✅ It means virtio drivers are already present
- ✅ No action needed - the VM will boot successfully
- ✅ Verify by checking VM gets IP address and SSH responds

#### Domain doesn't persist after conversion
**The smoke test creates temporary domains for testing.**
- Use `keep_domain: true` in config for persistent domains
- Manually define domain: `sudo virsh define test-confs/photon-virtio.xml`
- Check domain status: `sudo virsh list --all`

#### VM boots but can't connect
**Verify the VM is fully operational:**
```bash
# Get IP address
sudo virsh domifaddr photon-converted

# Test SSH port
nc -zv <IP> 22

# Check domain is running
sudo virsh domstate photon-converted
```

#### Need root permissions
**h2kvmctl requires sudo for disk operations:**
```bash
# Correct usage
sudo ./h2kvmctl --config test-confs/04-local-photon-os-vmdk.yaml

# Will fail without sudo
./h2kvmctl --config test-confs/04-local-photon-os-vmdk.yaml
```

### Getting Help

If you encounter issues:
1. Check OS-specific docs: `docs/os-support/photon-os.md`
2. Review failure modes: `docs/reference/failure-modes.md`
3. Enable verbose logging: `verbose: 2` in config
4. Generate report: `report: /path/to/report.md`
5. Check logs in output directory

---

**Last Updated:** 2026-02-08
**h2kvm Version:** v0.3.0
**VMCraft Version:** v9.0
**Maintained by:** ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
