# Hyper2KVM Frequently Asked Questions (FAQ)

Common questions and answers about using Hyper2KVM for VM migration.

## Table of Contents

### General Questions
- [What is Hyper2KVM?](#what-is-hyper2kvm)
- [What makes it different from other tools?](#what-makes-it-different)
- [Is it production-ready?](#is-it-production-ready)
- [What platforms does it support?](#supported-platforms)
- [Do I need to stop the source VM?](#vm-downtime)

### Installation & Setup
- [How do I install Hyper2KVM?](#installation)
- [What are the system requirements?](#system-requirements)
- [Do I need root access?](#root-access)
- [Can I run it in a container?](#container-deployment)

### Migration Questions
- [How long does a migration take?](#migration-time)
- [Can I migrate Windows VMs?](#windows-support)
- [What about multi-disk VMs?](#multi-disk-vms)
- [Can I migrate running VMs?](#live-migration)
- [How do I migrate multiple VMs?](#batch-migration)

### Technical Questions
- [What formats are supported?](#supported-formats)
- [Does it work with encrypted disks?](#encrypted-disks)
- [Can it handle snapshots?](#snapshots)
- [What about thin-provisioned disks?](#thin-provisioning)
- [Why does my OVA conversion use BIOS when the VM is UEFI?](#why-does-my-ova-conversion-use-bios-when-the-vm-is-uefi)
- [Why is hyper2kvm using all host CPUs inside my container?](#why-is-hyper2kvm-using-all-host-cpus-inside-my-container)
- [Why can't I export VMs with independent disks via VDDK?](#why-cant-i-export-vms-with-independent-disks-via-vddk)
- [How do I enable offline fixes in the Kubernetes operator?](#how-do-i-enable-offline-fixes-in-the-kubernetes-operator)
- [Does hyper2kvm support VDS (vSphere Distributed Switch)?](#does-hyper2kvm-support-vds-vsphere-distributed-switch)

### Troubleshooting
- [VM won't boot after migration](#boot-failure)
- [Network doesn't work](#network-failure)
- [Migration fails with error](#migration-errors)
- [How do I rollback?](#rollback)

---

## General Questions

### What is Hyper2KVM?

Hyper2KVM is an enterprise-grade VM migration toolkit that converts virtual machines from VMware, Hyper-V, AWS, Azure, and other hypervisors into production-ready KVM systems.

**Key Features:**
- **Automated Fixes**: Bootloader, fstab, initramfs regeneration
- **VMCraft Engine**: 480+ native Python APIs for VM manipulation
- **Multi-Format Support**: VMDK, OVA, OVF, VHD, AMI, raw
- **Windows Support**: VirtIO driver injection, registry modification
- **Batch Processing**: Parallel multi-VM migrations
- **Enterprise Ready**: Kubernetes operator, monitoring, HA

**See**: [Main Documentation](index.md)

---

### What makes it different from other tools?

Unlike traditional migration tools that "boot and hope," Hyper2KVM applies **deterministic offline fixes** to ensure **first-boot success**:

| Feature | virt-v2v | Other Tools | Hyper2KVM |
|---------|----------|-------------|-----------|
| **Offline Fixes** | Limited | None | Comprehensive |
| **Windows VirtIO** | Manual | Manual | Automatic |
| **fstab Repair** | Basic | None | Advanced |
| **Initramfs Rebuild** | No | No | Yes |
| **XFS UUID Fix** | No | No | Yes |
| **Batch Migration** | Limited | Limited | Full |
| **Native Python** | No (C) | Varies | Yes |
| **Kubernetes** | No | No | Yes |

**Key Differentiator**: **VMCraft** - Native Python VM manipulation engine with 480+ APIs.

---

### Is it production-ready?

**Yes!** Hyper2KVM v0.3.0 is production-ready:

✅ **Tested**:
- 1387 automated tests (1271 Python + 116 Go)
- 90%+ code coverage
- 500+ successful migrations

✅ **Platforms**:
- OpenShift Container Platform 4.10-4.16
- Kubernetes 1.24-1.33
- RHEL/CentOS, Ubuntu, SUSE, Photon OS
- Windows Server 2012-2025, Windows 10/11

✅ **Enterprise Features**:
- High availability
- Monitoring (Prometheus/Grafana)
- Security (SCCs, RBAC)
- Audit logging

**See**: [Test Results](test-results/TEST_RESULTS.md)

---

### Supported Platforms

**Source Hypervisors:**
- ✅ VMware ESXi 6.5-8.0
- ✅ VMware Workstation/Fusion
- ✅ Hyper-V (2012-2022)
- ✅ AWS EC2
- ✅ Azure VMs
- ✅ Google Cloud
- ✅ KVM (P2V-like scenarios)

**Guest Operating Systems:**
- ✅ Windows 7-11, Server 2008-2025
- ✅ RHEL/CentOS 7-10
- ✅ Ubuntu 18.04-24.04
- ✅ Debian 10-12
- ✅ SUSE/openSUSE 15+
- ✅ Oracle Linux
- ✅ Photon OS 3.0-5.0
- ✅ Rocky Linux, AlmaLinux

**Output Formats:**
- ✅ qcow2 (recommended)
- ✅ raw
- ✅ VDI (VirtualBox)

**See**: [OS Support](os-support/README.md)

---

### VM Downtime

**Short Answer**: Depends on method

**Methods:**

1. **Standard Migration** (Recommended)
   - **Downtime**: Full downtime during migration
   - **Duration**: 10-30 minutes depending on size
   - **Best for**: Most migrations

2. **Live Fix** (Advanced)
   - **Downtime**: <5 seconds for final switchover
   - **Duration**: Preparation + quick switchover
   - **Best for**: Production systems
   - **See**: [Live Fix Guide](guides/migration/playbooks.md#live-fix)

3. **Batch Migration**
   - **Downtime**: Per VM (can stagger)
   - **Duration**: Parallel processing
   - **Best for**: Multiple VMs

**See**: [Migration Playbooks](guides/migration/playbooks.md)

---

## Installation & Setup

### Installation

**Quick Install:**

```bash
# Full installation (recommended)
pip install "hyper2kvm[full]"

# Minimal installation
pip install hyper2kvm

# From source
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
pip install -e ".[full]"
```

**Verification:**

```bash
h2kvmctl --version
hyper2kvm --version
```

**See**: [Installation Guide](getting-started/01-Installation.md)

---

### System Requirements

**Minimum:**
- Python 3.10+
- 4 GB RAM
- 2 CPU cores
- 2x VM size disk space
- Linux OS

**Recommended:**
- Python 3.11+
- 8+ GB RAM
- 4+ CPU cores
- 3x VM size disk space
- RHEL 9 / Ubuntu 22.04+
- libguestfs + Python bindings (auto-used for LVM/LUKS disks)
  - `sudo dnf install libguestfs-tools python3-libguestfs`

**See**: [System Requirements](getting-started/README.md#prerequisites)

---

### Can I migrate LUKS-encrypted disks?

**Yes.** Pass `--luks-enable --luks-passphrase "password"` and hyper2kvm will:

1. Auto-switch to libguestfs backend (supermin appliance)
2. Unlock LUKS with `cryptsetup_open()` inside the appliance
3. Fix fstab/grub on the decrypted filesystem
4. Preserve the existing initramfs (same as virt-v2v)
5. The migrated VM prompts for the LUKS passphrase at boot

For TPM-sealed LUKS, add a passphrase keyslot before migration (the KVM vTPM has different seeds).

**See**: [LUKS Migration Guide](../guides/migration/luks-encrypted-disks.md)

---

### Root Access

**Yes, most operations require root/sudo.**

**Why:**
- Mount filesystems
- Modify disk images
- Access guest filesystems
- Install bootloaders
- Modify system files

**Usage:**

```bash
# Run with sudo
sudo h2kvmctl --config migration.yaml

# Or use sudo -i
sudo -i
h2kvmctl --config migration.yaml
```

**Security**: See [Security Best Practices](guides/security-best-practices.md)

---

### Container Deployment

**Yes! Multiple options:**

1. **Docker/Podman**
   ```bash
   podman run -d -v /data:/data \
     ghcr.io/ssahani/hyper2kvm:2.1.0-worker
   ```

2. **Kubernetes**
   ```bash
   helm install hyper2kvm-operator ./helm/hyper2kvm-operator
   ```

3. **OpenShift**
   ```bash
   # Via OperatorHub or Helm
   ```

**See**: [Container Deployment Guide](deployment/container-deployment-guide.md)

---

## Migration Questions

### Migration Time

**Typical Times:**

| VM Size | OS Type | Time |
|---------|---------|------|
| <20 GB | Linux | 3-5 min |
| <20 GB | Windows | 5-8 min |
| 20-50 GB | Linux | 8-15 min |
| 20-50 GB | Windows | 12-20 min |
| >50 GB | Linux | 20-40 min |
| >50 GB | Windows | 30-60 min |

**Factors:**
- Disk size
- Compression level
- Network speed (remote fetch)
- Fixes enabled
- System performance

**See**: [Performance Metrics](test-results/README.md#migration-time-benchmarks)

---

### Windows Support

**Yes! Full Windows support including:**

✅ **VirtIO Driver Injection**
- Automatic driver installation (auto-discovered at `/var/lib/hyper2kvm/virtio-win.iso`)
- Install drivers with `sudo ./scripts/install-deps.sh --virtio-win` — no `--virtio-drivers-dir` flag needed
- Registry modification
- Network adapter configuration

✅ **Supported Versions:**
- Windows 7-11
- Windows Server 2008 R2 - 2025

✅ **Features:**
- Boot sector fixes
- Driver injection
- Registry updates
- Network configuration

**Example:**

```yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/vms
to_output: windows-server.qcow2

# Windows-specific — VirtIO ISO auto-discovered at /var/lib/hyper2kvm/virtio-win.iso
windows_drivers: true
# virtio_drivers_dir: /custom/path  # optional — only needed to override the standard path
```

**See**: [Windows Migration Guide](os-support/windows/guide.md)

---

### Multi-Disk VMs

**Yes, but requires multiple migrations:**

```bash
# Disk 1 (boot disk with fixes)
sudo h2kvmctl --config << EOF
command: local
vmdk: /vmware/vm-disk1.vmdk
output_dir: /kvm/vms
to_output: vm-disk1.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
EOF

# Disk 2 (data disk, no fixes needed)
sudo h2kvmctl --config << EOF
command: local
vmdk: /vmware/vm-disk2.vmdk
output_dir: /kvm/vms
to_output: vm-disk2.qcow2
compress: true
EOF
```

**Then update libvirt XML to include both disks.**

**See**: [Recipe #10](recipes/README.md#recipe-10-multi-disk-vm)

---

### Live Migration

**Yes, using live-fix method:**

```yaml
command: live-fix
host: esxi-host.example.com
user: root
identity: ~/.ssh/id_rsa

# Fixes
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

**Process:**
1. Connect to running VM via SSH
2. Apply fixes while running
3. Quick switchover (<5s downtime)

**See**: [Migration Playbooks](guides/migration/playbooks.md#live-fix)

---

### Batch Migration

**Yes! Multiple methods:**

**Method 1: JSON Manifest**

```yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
output_dir: /kvm/batch
```

```json
{
  "migrations": [
    {"vmdk": "/vmware/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vmware/vm2.vmdk", "to_output": "vm2.qcow2"},
    {"vmdk": "/vmware/vm3.vmdk", "to_output": "vm3.qcow2"}
  ]
}
```

**Method 2: Kubernetes Operator**

Submit multiple MigrationJob CRDs.

**See**: [Batch Migration Guide](guides/migration/batch-features.md)

---

## Technical Questions

### Supported Formats

**Input Formats:**
- ✅ VMDK (all types: monolithic, split, sparse, streamOptimized)
- ✅ OVA (VMware export archive)
- ✅ OVF (VMware export descriptor)
- ✅ VHD/VHDX (Hyper-V)
- ✅ AMI (AWS EC2 tarball)
- ✅ raw disk images
- ✅ Azure VHD

**Output Formats:**
- ✅ qcow2 (recommended)
- ✅ raw
- ✅ VDI (VirtualBox)

**See**: [CLI Reference](guides/cli/reference.md)

---

### Encrypted Disks

**Partial Support:**

**BitLocker (Windows):**
- ❌ Cannot migrate while encrypted
- ✅ Decrypt before migration
- ✅ Re-encrypt after migration

**LUKS (Linux):**
- ❌ Cannot modify while encrypted
- ✅ Decrypt before migration
- ✅ Re-encrypt after migration

**Workaround:**

```bash
# 1. Decrypt on source
# Windows: Disable BitLocker
# Linux: cryptsetup luksClose

# 2. Migrate
sudo h2kvmctl --config migration.yaml

# 3. Re-encrypt on target
# Windows: Enable BitLocker
# Linux: cryptsetup luksFormat
```

**See**: [Security Best Practices](guides/security-best-practices.md)

---

### Snapshots

**VMware Snapshots:**
- ❌ Not supported (linked clones)
- ✅ Consolidate snapshots first
- ✅ Export as standalone VM

**Process:**

```bash
# In VMware
1. Right-click VM → Snapshots → Consolidate
2. Wait for consolidation
3. Export VM or migrate VMDK
```

**See**: [VMDK Inspector](features/vmdk-inspector.md)

---

### Thin Provisioning

**Yes, supported:**

**Source:**
- ✅ Thin-provisioned VMDKs
- ✅ Thick-provisioned VMDKs

**Output:**
- ✅ Sparse qcow2 (default, space-efficient)
- ✅ Preallocated qcow2 (for performance)
- ✅ raw (full size)

**Example:**

```yaml
# Sparse output (saves space)
compress: true
keep_sparse: true

# Preallocated output (better performance)
preallocate: true
compress: false
```

---

### Why does my OVA conversion use BIOS when the VM is UEFI?

**Problem**: OVA export from VMware may not preserve firmware metadata correctly.

**Root Cause:**
- OVF descriptor sometimes omits firmware type
- Depends on how the OVA was exported (govc vs. vSphere UI)

**Solution**: Hyper2KVM auto-detects UEFI from multiple sources:

1. **OVF Metadata**: Checks `<vssd:VirtualSystemType>` for "uefi" or "efi"
2. **Guest Disk Analysis**: Mounts the guest disk and inspects:
   - EFI System Partition (ESP) presence
   - `/boot/efi/` mount point in fstab
   - GRUB configuration path (`/boot/efi/EFI/` vs `/boot/grub2/`)

**Manual Override:**

```yaml
command: ova
ova: /vmware/exported.ova
output_dir: /kvm/vms
to_output: vm.qcow2
firmware: uefi        # Force UEFI mode
emit_domain_xml: true
```

**Verification:**

```bash
# Check generated libvirt XML
grep -A2 '<os>' output/vm.xml
# Should show: <loader type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
```

**See**: [OVF Extractor Source](../../hyper2kvm/converters/extractors/ovf.py)

---

### Why is hyper2kvm using all host CPUs inside my container?

**Problem**: Python's `os.cpu_count()` returns physical CPU count, ignoring cgroup limits.

**Root Cause:**
- Docker/Kubernetes set CPU limits via cgroups (e.g., `--cpus=2`)
- `os.cpu_count()` reads `/proc/cpuinfo`, which shows host CPUs

**Solution**: Hyper2KVM uses `effective_cpu_count()` to respect cgroups:

```python
def effective_cpu_count() -> int:
    """Return CPU count respecting cgroup limits."""
    try:
        # Read cgroup v2 quota
        quota = int(Path("/sys/fs/cgroup/cpu.max").read_text().split()[0])
        period = int(Path("/sys/fs/cgroup/cpu.max").read_text().split()[1])
        if quota > 0:
            return max(1, quota // period)
    except (FileNotFoundError, ValueError):
        pass

    # Fallback to physical count
    return os.cpu_count() or 1
```

**Behavior:**
- **Host**: Uses all available CPUs
- **Container with `--cpus=2`**: Uses 2 CPUs
- **Kubernetes with `resources.limits.cpu: "4"`**: Uses 4 CPUs

**Verification:**

```bash
# Inside container
docker run --cpus=2 ghcr.io/ssahani/hyper2kvm:latest python3 -c \
  "from hyper2kvm.utils import effective_cpu_count; print(effective_cpu_count())"
# Output: 2 (not 16+)
```

**See**: [CPU Detector](../../hyper2kvm/utils/cpu.py)

---

### Why can't I export VMs with independent disks via VDDK?

**Problem**: VMware's VDDK library fails when VMs have disks in "independent" mode.

**Root Cause:**
- Independent disks (persistent/nonpersistent) are excluded from snapshots
- VDDK export relies on Change Block Tracking (CBT), which requires snapshot support
- govc and VDDK both fail with: `Cannot open the disk ... or one of the snapshot disks it depends on`

**Detection:**

```bash
# Check disk mode via govc
govc vm.info -json my-vm | jq '.VirtualMachines[].Config.Hardware.Device[] | select(.Backing.DiskMode)'
# Look for: "independent_persistent" or "independent_nonpersistent"
```

**Workarounds:**

1. **Change Disk Mode** (Requires VM downtime):
   ```bash
   # In vSphere UI:
   # Edit VM Settings → Hard Disk → Mode → Change to "Dependent"
   # Then export normally
   ```

2. **Use OVA Export** (No VDDK required):
   ```yaml
   command: vsphere
   vcenter_host: vcenter.example.com
   vm_name: my-vm
   vs_action: export_ova      # Uses OVF export, not VDDK
   output_dir: /kvm/vms
   ```

3. **Direct Datastore Access** (ESXi only):
   ```bash
   # SSH to ESXi host
   scp /vmfs/volumes/datastore1/my-vm/*.vmdk user@migration-host:/vmware/

   # Then migrate locally
   h2kvmctl --cmd local --vmdk /vmware/my-vm.vmdk -o /kvm/vms
   ```

**See**: [govc Export Implementation](../../hyper2kvm/converters/importers/govc_export.py)

---

### How do I enable offline fixes in the Kubernetes operator?

**Short Answer**: Set `conversion.offlineFixes: true` in your `HyperConversion` CR spec.

**Example HyperConversion CR:**

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: migrate-web-server
  namespace: default
spec:
  source:
    type: vmdk
    path: /mnt/vmware/web-server.vmdk

  conversion:
    outputFormat: qcow2
    compress: true
    offlineFixes: true         # Enable all offline fixes

  fixes:
    fstabMode: stabilize-all   # Fix /etc/fstab
    regenInitramfs: true       # Rebuild initramfs with virtio drivers
    xfsRegenerateUuid: true    # Fix cloned VMware VMs with XFS

  deployment:
    libvirt:
      enabled: true
      autoDefine: true
      autoStart: false
```

**What Gets Fixed:**
- `/etc/fstab`: UUIDs stabilized, VMware-specific entries removed
- Initramfs: Rebuilt with `virtio_blk`, `virtio_scsi`, `virtio_net`
- GRUB: Auto-detected and updated for KVM
- XFS UUIDs: Regenerated if cloned

**Verification:**

```bash
# Watch migration progress
kubectl logs -f deployment/hyperconversion-operator-controller-manager -n hyperconversion-system

# Check job status
kubectl get hyperconversion migrate-web-server -o yaml | grep -A5 status
```

**See**: [Operator CRD](../../operator/api/v1alpha1/hyperconversion_types.go)

---

### Does hyper2kvm support VDS (vSphere Distributed Switch)?

**Yes!** VDS networks are auto-detected and preserved during migration.

**How It Works:**

1. **Discovery via govc**:
   ```bash
   govc vm.info -json my-vm | jq '.VirtualMachines[].Config.Hardware.Device[] | select(._type == "VirtualEthernetCard")'
   ```

2. **VDS Detection**:
   - Standard vSwitch: `"network": "VM Network"`
   - VDS Port Group: `"portgroupid": "dvportgroup-123"`

3. **Mapping to KVM**:
   ```yaml
   # Generated libvirt XML preserves network name
   <interface type='network'>
     <source network='VM Network'/>   # or VDS port group name
     <model type='virtio'/>
   </interface>
   ```

**Example Migration:**

```yaml
command: vsphere
vcenter_host: vcenter.example.com
vm_name: prod-vm-with-vds
vs_action: export_vm
output_dir: /kvm/vms
emit_domain_xml: true    # Generates XML with VDS network mapping
```

**Post-Migration:**

You'll need to create a matching libvirt network:

```bash
# If source used VDS port group "Production-VLAN100"
virsh net-define << EOF
<network>
  <name>Production-VLAN100</name>
  <forward mode='bridge'/>
  <bridge name='br0'/>
</network>
EOF

virsh net-start Production-VLAN100
virsh net-autostart Production-VLAN100
```

**See**: [Libvirt XML Extractor](../../hyper2kvm/converters/extractors/libvirt_xml.py)

---

## Troubleshooting

### Boot Failure

**Problem**: VM doesn't boot after migration

**Common Causes:**
1. Missing virtio drivers in initramfs
2. Wrong fstab entries
3. GRUB configuration issues
4. Wrong disk controller

**Solution:**

```yaml
command: offline-fix
qcow2: /kvm/vms/failed-boot.qcow2

# Comprehensive fixes
fstab_mode: stabilize-all
regen_initramfs: true
initramfs_add_drivers:
  - virtio
  - virtio_blk
  - virtio_scsi
  - virtio_net
# grub is auto-handled
```

**See**: [Troubleshooting Guide](guides/troubleshooting.md#boot-failures)

---

### Network Failure

**Problem**: No network connectivity after migration

**Common Causes:**
1. Missing virtio_net driver
2. MAC address change
3. Network interface name change
4. NetworkManager issues

**Solution:**

```yaml
command: offline-fix
qcow2: /kvm/vms/no-network.qcow2

# Network fixes
regen_initramfs: true
initramfs_add_drivers:
  - virtio_net
  - e1000
fstab_mode: stabilize-all
```

**Manual Fix:**

```bash
# Inside VM after boot
ip link  # Check interface name
nmcli device  # Check NetworkManager
```

**See**: [Troubleshooting Guide](guides/troubleshooting.md#network-issues)

---

### Migration Errors

**Problem**: Migration fails with error

**Common Errors:**

1. **Permission Denied**
   ```bash
   # Solution: Run with sudo
   sudo h2kvmctl --config migration.yaml
   ```

2. **Disk Space**
   ```bash
   # Check available space (need 3x VM size)
   df -h /output/directory
   ```

3. **Missing Dependencies**
   ```bash
   # Install required tools
   sudo dnf install -y qemu-img qemu-system-x86  # RHEL/Fedora
   sudo apt-get install -y qemu-utils  # Ubuntu
   ```

4. **Corrupt VMDK**
   ```bash
   # Validate VMDK first
   ./scripts/vmdk_inspect.py /path/to/vm.vmdk
   ```

**See**: [Troubleshooting Guide](guides/troubleshooting.md)

---

### Rollback

**If migration fails or VM doesn't work:**

**Option 1: Keep Original**
- Original VM is never modified
- Simply don't delete source
- Start original VM if needed

**Option 2: Use Snapshots**
```bash
# Before migration
qemu-img snapshot -c before_migration vm.qcow2

# Rollback if needed
qemu-img snapshot -a before_migration vm.qcow2
```

**Option 3: Backup**
```bash
# Before migration
cp /vmware/original.vmdk /backup/original.vmdk.backup
```

**See**: [Migration Playbooks](guides/migration/playbooks.md#rollback-procedures)

---

## Additional Resources

### Documentation
- **[Main Documentation Hub](index.md)** - Complete documentation
- **[Getting Started](getting-started/)** - Installation and setup
- **[Tutorials](tutorials/)** - Step-by-step learning
- **[Recipes](recipes/)** - Quick solutions
- **[Troubleshooting](guides/troubleshooting.md)** - Fix common issues

### Support
- **GitHub Issues**: [Report bugs](https://github.com/ssahani/hyper2kvm/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/ssahani/hyper2kvm/discussions)

### Examples
- **[Migration Recipes](recipes/)** - Real-world examples
- **[Config Examples](../examples/)** - Sample configurations

---

**Can't find your question?** [Ask on GitHub Discussions](https://github.com/ssahani/hyper2kvm/discussions)

---

**Last Updated**: March 2026
**Total Questions**: 30+
**Coverage**: Installation, Migration, Troubleshooting, Technical, vSphere, Kubernetes
