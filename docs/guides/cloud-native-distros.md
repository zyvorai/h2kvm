# Cloud-Native Distribution Migration Guide

This guide covers migrating cloud-native Linux distributions (Photon OS, CoreOS, Flatcar, etc.) from VMware to KVM.

## Overview

Cloud-native distributions are **purpose-built for virtualization** and include:
- ✅ Virtio drivers pre-installed
- ✅ Minimal OS footprint
- ✅ Cloud-init support
- ✅ Container runtime focus

**Result:** These distributions migrate easily with minimal configuration!

---

## Supported Cloud-Native Distributions

| Distribution | Virtio Support | Initramfs Tool | Special Notes |
|-------------|----------------|----------------|---------------|
| **VMware Photon OS** | ✅ Built-in | dracut | systemd-networkd default |
| **Fedora CoreOS** | ✅ Built-in | dracut | Immutable OS |
| **Flatcar Container Linux** | ✅ Built-in | dracut | CoreOS successor |
| **RancherOS** | ✅ Built-in | N/A | Docker-based |
| **K3OS** | ✅ Built-in | N/A | K3s-optimized |
| **Talos Linux** | ✅ Built-in | N/A | Kubernetes-native |

---

## Quick Start: Photon OS Example

### 1. Conversion Configuration

```yaml
cmd: local
vmdk: /path/to/photon.vmdk
output_dir: /output
to_output: photon-converted.qcow2
out_format: qcow2

# Standard fixes
flatten: true
fstab_mode: stabilize-all
regen_initramfs: true
no_grub: false
checksum: true

# Optional: Test boot
libvirt_test: true
vm_name: photon-test
keep_domain: true
```

### 2. Run Conversion

```bash
sudo h2kvmctl --config photon-migration.yaml
```

### 3. Expected Warning (NORMAL!)

```
⚠️  initramfs rebuild failed: mtime+size unchanged
```

**This is expected and correct!** It means:
- Virtio drivers are already present
- No rebuild needed
- VM will boot successfully

### 4. Deploy to Libvirt

```bash
# Use virtio for best performance (recommended)
sudo virsh define test-confs/photon-virtio.xml
sudo virsh start photon-converted

# Verify boot
sudo virsh domifaddr photon-converted  # Get IP
nc -zv <IP> 22                          # Test SSH
```

---

## Understanding the Initramfs Warning

### What Does This Warning Mean?

```
⚠️  initramfs rebuild failed: mtime+size unchanged (mtime=1769251671, size=22324924)
```

**Explanation:**
1. h2kvm attempts to rebuild initramfs with virtio drivers
2. dracut detects the drivers are **already present**
3. No changes made (mtime and size unchanged)
4. Warning logged for transparency

**Action Required:** None! This is the expected behavior.

### Why Do Cloud-Native Distros Have Virtio Built-In?

Cloud-native distributions are designed for:
- ☁️  Public cloud environments (AWS, Azure, GCP)
- 🚀 Kubernetes/container platforms
- 📦 Minimal attack surface
- ⚡ Fast boot times

All major cloud providers use virtio, so these distros ship with virtio support by default.

---

## Verification Checklist

After conversion, verify successful migration:

### ✅ Boot Verification

```bash
# 1. Check VM is running
sudo virsh list --all
# Expected: "running" state

# 2. Get IP address
sudo virsh domifaddr photon-converted
# Expected: IP address assigned via DHCP

# 3. Test SSH connectivity
nc -zv <IP> 22
# Expected: Connection successful
```

### ✅ Virtio Drivers

```bash
# Inside the VM, check loaded drivers
lsmod | grep virtio

# Expected output:
# virtio_net
# virtio_blk
# virtio_pci
# virtio_ring
```

### ✅ Disk Performance

```bash
# Check disk is using virtio
sudo virsh dumpxml photon-converted | grep "target dev"

# Expected:
# <target dev='vda' bus='virtio'/>
```

---

## Configuration Tips

### Use Virtio by Default

```xml
<!-- Recommended for cloud-native distros -->
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2'/>
  <source file='/path/to/photon.qcow2'/>
  <target dev='vda' bus='virtio'/>
</disk>
```

### SATA Fallback (Rarely Needed)

Only use if virtio fails (very rare with modern versions):

```xml
<!-- Fallback configuration -->
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2'/>
  <source file='/path/to/photon.qcow2'/>
  <target dev='sda' bus='sata'/>
</disk>
```

### Network Configuration

Cloud-native distros typically use:
- **Photon OS**: systemd-networkd
- **CoreOS/Flatcar**: NetworkManager or systemd-networkd
- **RancherOS/K3OS**: Docker networking

Most will auto-configure with DHCP - no manual network fixes needed!

---

## Troubleshooting

### VM Doesn't Get IP Address

**Check DHCP on libvirt network:**
```bash
sudo virsh net-list --all
sudo virsh net-start default
sudo virsh net-info default
```

**Inside VM, check network service:**
```bash
# Photon OS
systemctl status systemd-networkd

# CoreOS/Flatcar
systemctl status NetworkManager
```

### Cannot Connect via SSH

**Verify SSH is running:**
```bash
# Get VM IP
IP=$(sudo virsh domifaddr photon-converted | awk '/ipv4/{print $4}' | cut -d/ -f1)

# Test SSH port
nc -zv $IP 22

# Check from VM console
sudo virsh console photon-converted
# Login and check: systemctl status sshd
```

### Boot Failures (Rare)

If virtio boot fails (unlikely with cloud-native distros):

1. **Try SATA disk as fallback**
   ```bash
   sudo virsh define test-confs/photon-sata.xml
   sudo virsh start photon-converted
   ```

2. **Check initramfs manually**
   ```bash
   sudo virt-ls -a photon.qcow2 /boot/
   sudo virt-cat -a photon.qcow2 /boot/initramfs-*
   ```

3. **Force rebuild**
   ```bash
   sudo virt-customize -a photon.qcow2 \
     --run-command 'dracut -f --add-drivers "virtio_blk virtio_scsi virtio_net"'
   ```

---

## Performance Optimization

### Enable Compression

Cloud-native distros are typically small, but compression helps:

```yaml
compress: true
compress_level: 6  # Balance speed/size
```

### Use Host CPU Passthrough

```xml
<cpu mode='host-passthrough'/>
```

### Optimize Network

```xml
<interface type='network'>
  <source network='default'/>
  <model type='virtio'/>
  <driver name='vhost' queues='4'/>  <!-- Multi-queue -->
</interface>
```

---

## Migration Patterns

### Pattern 1: Batch Migration

```yaml
# batch-photon-migration.yaml
batch_manifest: photon-vms.json
batch_parallel: 4
batch_continue_on_error: true
```

```json
// photon-vms.json
[
  {"vmdk": "/vms/photon-web-01.vmdk", "name": "web-01"},
  {"vmdk": "/vms/photon-web-02.vmdk", "name": "web-02"},
  {"vmdk": "/vms/photon-app-01.vmdk", "name": "app-01"}
]
```

### Pattern 2: Direct to Kubernetes

```bash
sudo h2kvmctl --config photon.yaml --deploy-k8s \
  --k8s-namespace production \
  --k8s-vm-name photon-app \
  --k8s-auto-start
```

### Pattern 3: Template-Based

```yaml
# Create template from first conversion
# Then clone for additional VMs
virt-clone -o photon-template -n photon-prod-01 --auto-clone
```

---

## Best Practices

### ✅ Do

- Use virtio disk and network by default
- Expect and ignore "mtime unchanged" warning
- Verify boot by checking IP and SSH connectivity
- Keep original VMDK as backup until verified
- Test one VM before batch migration

### ❌ Don't

- Don't use SATA unless virtio fails
- Don't worry about initramfs rebuild warning
- Don't modify network config manually (usually auto-configured)
- Don't skip boot verification
- Don't delete source VMs immediately

---

## Reference Configurations

### Photon OS
- Conversion: `test-confs/04-local-photon-os-vmdk.yaml`
- Virtio XML: `test-confs/photon-virtio.xml`
- SATA XML: `test-confs/photon-sata.xml`
- Guide: `test-confs/README-photon.md`

### Documentation
- OS Support: `docs/os-support/photon-os.md`
- Troubleshooting: `docs/guides/troubleshooting.md`
- Quick Start: `docs/getting-started/02-Quick-Start.md`

---

## Support

For cloud-native distribution migrations:
1. Check OS-specific docs in `docs/os-support/`
2. Review troubleshooting guide
3. Enable verbose logging: `verbose: 2`
4. Generate conversion report: `report: /path/to/report.md`

---

**Last Updated:** 2026-03-29
**Tested Distributions:** Photon OS 3.0, 4.0, 5.0 | CoreOS | Flatcar
**Status:** Production Ready ✅
