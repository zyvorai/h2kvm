# Tutorial: Exporting VMs from vSphere with govc and OVF Tool

This tutorial covers installing and using **govc** and **VMware OVF Tool** to export
VMs from vSphere/ESXi, and how h2kvm uses them internally via the NFC protocol.

## Prerequisites

- Access to a vCenter Server or standalone ESXi host
- Network connectivity to the ESXi host (NFC transfers go host → client directly)
- Sufficient disk space for exported VM images

---

## 1. Installing govc

govc is an open-source CLI built on the VMware vSphere API (govmomi).

### Linux (x86_64)

```bash
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | tar xzf - -C /usr/local/bin govc
chmod +x /usr/local/bin/govc
govc version
```

### Linux (ARM64)

```bash
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_arm64.tar.gz \
  | tar xzf - -C /usr/local/bin govc
chmod +x /usr/local/bin/govc
```

### macOS

```bash
brew install govc
```

### Verify

```bash
govc version
# govc 0.x.x
```

---

## 2. Installing VMware OVF Tool

OVF Tool is VMware's official CLI for importing/exporting OVF/OVA packages.

### Download

Download from Broadcom:
https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest

### Install (Linux — all distros)

```bash
# OVF Tool 5.0+ ships as a zip
sudo mkdir -p /opt/ovftool
sudo unzip VMware-ovftool-*.zip -d /opt/ovftool
sudo ln -sf /opt/ovftool/ovftool /usr/local/bin/ovftool

# Legacy bundle installer (OVF Tool 4.x)
# chmod +x VMware-ovftool-*.bundle
# sudo ./VMware-ovftool-*.bundle
# export PATH=/opt/ovftool:$PATH
```

### Verify

```bash
ovftool --version
# VMware ovftool 5.0.0 (build-XXXXXXXX)
```

---

## 3. Setting Up Environment Variables

Both tools use environment variables for authentication:

```bash
# For govc
export GOVC_URL='https://vcenter.example.com/sdk'
export GOVC_USERNAME='administrator@vsphere.local'
export GOVC_PASSWORD='your-password'
export GOVC_INSECURE=1              # Skip TLS verification (self-signed certs)
export GOVC_DATACENTER='Datacenter' # Your datacenter name

# For h2kvm (vc_password_env)
export VC_PASSWORD='your-password'
```

---

## 4. Discovering VMs with govc

### List VMs

```bash
# List all VMs in a datacenter
govc ls /Datacenter/vm/

# Get VM details
govc vm.info MyVM

# Get VM details as JSON (used by h2kvm for hardware extraction)
govc vm.info -json MyVM
# h2kvm extracts: memory (MiB), vCPUs, NIC count, total disk size
# These are propagated to the domain emitter for accurate libvirt XML generation
```

### List Disks

```bash
govc vm.disk.info MyVM
```

---

## 5. Exporting VMs with govc

govc uses VMware's **HttpNfcLease** (NFC protocol) under the hood.

### Export as OVF (directory)

```bash
govc export.ovf -vm MyVM /tmp/
# Output: /tmp/MyVM/MyVM.ovf + MyVM-disk1.vmdk + MyVM.mf
```

### Export as OVA (single file)

```bash
govc export.ova -vm MyVM /tmp/MyVM.ova
```

### Download a disk directly from datastore

```bash
govc datastore.download \
  "vm/MyVM/MyVM.vmdk" \
  ./MyVM.vmdk
```

---

## 6. Exporting VMs with OVF Tool

### Export to OVA

```bash
ovftool \
  --noSSLVerify \
  "vi://administrator@vsphere.local:password@vcenter/Datacenter/vm/MyVM" \
  /tmp/MyVM.ova
```

### Export to OVF directory

```bash
ovftool \
  --noSSLVerify \
  "vi://administrator@vsphere.local:password@vcenter/Datacenter/vm/MyVM" \
  /tmp/MyVM.ovf
```

### Export directly from ESXi (no vCenter)

```bash
ovftool \
  --noSSLVerify \
  "vi://root:password@esxi-host/MyVM" \
  /tmp/MyVM.ova
```

---

## 7. govc vs OVF Tool Comparison

| Feature                  | govc          | OVF Tool      |
|--------------------------|---------------|---------------|
| Open source              | Yes (Apache)  | No (VMware)   |
| Uses vSphere API         | Yes           | No            |
| NFC streaming            | Yes (internal)| Yes (internal)|
| Automation friendly      | Excellent     | Moderate      |
| OVA export               | Yes           | Yes           |
| OVF export               | Yes           | Yes           |
| Deploy to vSphere        | No            | Yes           |
| Snapshot management       | Yes           | No            |
| CBT (Changed Block Track)| Yes           | No            |
| Install size             | ~15 MB        | ~200 MB       |

### When to Use Which

**Use govc when:**
- Automating CI/CD pipelines
- You need snapshot/CBT management alongside export
- You want a lightweight, scriptable tool

**Use OVF Tool when:**
- You need VMware-supported export/import
- Deploying OVAs back to vSphere
- Working with complex OVF configurations

---

## 8. How NFC Works Under the Hood

Both govc and OVF Tool use VMware's **Network File Copy (NFC)** protocol:

```
Client (govc / ovftool / h2kvm)
  │
  │ vSphere API: VirtualMachine.ExportVm()
  ▼
vCenter
  │
  │ creates HttpNfcLease
  ▼
ESXi host (NFC transfer server)
  │
  │ provides signed HTTP URLs for each disk
  ▼
Client streams VMDK via HTTP GET
```

Key points:
- **HttpNfcLease** is a temporary disk streaming session opened by ESXi
- Client must send periodic **HttpNfcLeaseProgress()** keepalives or the lease expires
- Disk data flows **ESXi → client** directly (not via vCenter)
- Supports thick VMDK, thin VMDK, and snapshot chains

h2kvm has a dedicated NFC module (`h2kvm/providers/vmware/clients/nfc_lease.py`)
that handles lease management, retries, and progress reporting.

---

## 9. Using h2kvm for the Full Pipeline

h2kvm combines export + conversion + guest fixes in a single command:

### Using YAML config

```bash
# Set credentials
export VCENTER_HOST=vcenter.example.com
export VCENTER_USERNAME=administrator@vsphere.local
export VCENTER_PASSWORD=your-password
export VCENTER_DATACENTER=Production-DC
export VCENTER_VM_NAME=my-rhel-vm

# Run full pipeline
sudo -E h2kvmctl --config examples/yaml/70-complete-workflows/vsphere-to-libvirt-demo-export.yaml
```

### Using CLI directly

```bash
sudo -E h2kvmctl \
  --cmd vsphere \
  --vcenter vcenter.example.com \
  --vc-user administrator@vsphere.local \
  --vc-password-env VC_PASSWORD \
  --vc-insecure \
  --vs-action export_vm \
  --export-mode ovf_export \
  --vm-name my-rhel-vm \
  --govc-datacenter Datacenter \
  --flatten \
  --to-output my-rhel-vm.qcow2 \
  --out-format qcow2 \
  --compress \
  --regen-initramfs \
  --fstab-mode stabilize-all \
  --emit-domain-xml \
  --uefi
```

### The pipeline (runs automatically in one command)

```
vCenter VM
  ↓  govc export.ovf or ovftool (NFC streaming)
OVF + VMDK
  ↓  qemu-img convert (flatten + compress)
qcow2
  ↓  libguestfs offline fixes (fstab, initramfs + virtio, vmware-tools)
Fixed qcow2
  ↓  emit libvirt domain XML + virsh define
libvirt VM
  ↓  boot test (optional)
Running VM on KVM
```

All steps chain automatically — no need to run separate commands for export,
conversion, and import. Just run one `h2kvmctl --config` command.

---

## 10. Importing into libvirt/KVM

After exporting and converting a VM, you need to define and start it in libvirt.

### Generate libvirt domain XML with h2kvm

h2kvm can generate the domain XML automatically during conversion:

```bash
sudo -E h2kvmctl \
  --cmd vsphere \
  --vs-action export_vm \
  --vm-name my-rhel-vm \
  --vcenter vcenter.example.com \
  --vc-password-env VC_PASSWORD \
  --vc-insecure \
  --govc-datacenter Datacenter \
  --flatten --to-output my-rhel-vm.qcow2 --out-format qcow2 --compress \
  --emit-domain-xml --uefi
```

This produces both the qcow2 disk and a libvirt XML in the output directory.

### Define and start the VM

```bash
# Define the VM in libvirt
virsh define output/libvirt/my-rhel-vm.xml

# Start the VM
virsh start my-rhel-vm

# Connect via console
virsh console my-rhel-vm

# Or connect via VNC/SPICE
virsh domdisplay my-rhel-vm
```

### Manual libvirt import (without h2kvm XML generation)

If you exported and converted the disk manually, use `virt-install`:

```bash
# BIOS boot
virt-install \
  --name my-rhel-vm \
  --memory 4096 \
  --vcpus 4 \
  --cpu host-passthrough \
  --disk path=/data/exports/my-rhel-vm.qcow2,bus=virtio,cache=writeback \
  --network bridge=br0,model=virtio \
  --os-variant rhel9-unknown \
  --graphics vnc \
  --import \
  --noautoconsole

# UEFI boot
virt-install \
  --name my-rhel-vm \
  --memory 4096 \
  --vcpus 4 \
  --cpu host-passthrough \
  --disk path=/data/exports/my-rhel-vm.qcow2,bus=virtio,cache=writeback \
  --network bridge=br0,model=virtio \
  --os-variant rhel9-unknown \
  --boot uefi \
  --graphics vnc \
  --import \
  --noautoconsole
```

### Using virsh with hand-written XML

```bash
# Create a minimal domain XML
cat > /tmp/my-rhel-vm.xml << 'XMLEOF'
<domain type='kvm'>
  <name>my-rhel-vm</name>
  <memory unit='MiB'>4096</memory>
  <vcpu>4</vcpu>
  <cpu mode='host-passthrough'/>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
    <nvram template='/usr/share/OVMF/OVMF_VARS.fd'/>
    <boot dev='hd'/>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='writeback'/>
      <source file='/data/exports/my-rhel-vm.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='bridge'>
      <source bridge='br0'/>
      <model type='virtio'/>
    </interface>
    <serial type='pty'><target port='0'/></serial>
    <console type='pty'><target type='serial' port='0'/></console>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <graphics type='vnc' port='-1' autoport='yes'/>
    <video><model type='virtio'/></video>
  </devices>
</domain>
XMLEOF

virsh define /tmp/my-rhel-vm.xml
virsh start my-rhel-vm
```

### Managing the imported VM

```bash
# List running VMs
virsh list

# Shutdown gracefully
virsh shutdown my-rhel-vm

# Force power off
virsh destroy my-rhel-vm

# Remove VM definition (keeps disk)
virsh undefine my-rhel-vm

# Remove VM definition + UEFI NVRAM
virsh undefine my-rhel-vm --nvram

# Snapshot
virsh snapshot-create-as my-rhel-vm --name "post-migration"
```

### Verify the imported VM

```bash
# Check VM is running
virsh dominfo my-rhel-vm

# Check disk
virsh domblklist my-rhel-vm

# Check network
virsh domiflist my-rhel-vm

# Get IP address (requires qemu-guest-agent)
virsh domifaddr my-rhel-vm --source agent
```

---

## 11. Troubleshooting

### govc: "operation not allowed in current state"
The VM may need to be powered off first:
```bash
govc vm.power -off MyVM
govc export.ovf -vm MyVM /tmp/
```

### OVF Tool: SSL certificate errors
```bash
ovftool --noSSLVerify "vi://..." /tmp/output.ova
```

### NFC lease timeout
Exports of large disks can time out if progress isn't reported. h2kvm handles
keepalives automatically. For manual govc use, this is handled internally.

### "pyvmomi not installed"
```bash
pip install pyvmomi
# Or
pip install h2kvm[vsphere]
```

### libvirt: "cannot access storage file"
Ensure the qcow2 file path is accessible by the `qemu` user:
```bash
chmod 644 /data/exports/my-rhel-vm.qcow2
# Or set SELinux context (RHEL/Fedora)
chcon -t virt_image_t /data/exports/my-rhel-vm.qcow2
```

### libvirt: UEFI firmware not found
Install OVMF:
```bash
# Fedora/RHEL
dnf install edk2-ovmf
# Debian/Ubuntu
apt install ovmf
```

---

## See Also

- [YAML Examples](../../examples/yaml/70-complete-workflows/) — Distro-specific vSphere to libvirt configs
- [vSphere YAML Examples](../../examples/yaml/60-vsphere/) — Individual vSphere operations
- [Installation Guide](../02-Installation.md) — Full installation instructions
