# Tutorial: Migrating Windows VMs from VMware to KVM

This tutorial covers migrating Windows 10/11 and Windows Server VMs from
VMware vSphere to libvirt/KVM with VirtIO driver injection and two-phase boot.

## Why Windows Migration Is Different

Windows VMs require extra steps compared to Linux:

1. **VirtIO drivers** must be injected offline before the first KVM boot
2. **Registry edits** register the VirtIO storage driver as a boot-start driver
3. **Two-phase boot** ensures Windows loads VirtIO drivers safely (SATA first, then VirtIO)
4. **VMware Tools** must be removed to avoid conflicts

h2kvm handles all of this automatically.

---

## Prerequisites

```bash
# Install dependencies
sudo ./scripts/install-deps.sh --qemu --guestfs --libvirt --ovmf

# Install VirtIO drivers ISO (recommended — downloads to standard path)
sudo ./scripts/install-deps.sh --virtio-win
# Downloads to /var/lib/h2kvm/virtio-win.iso
# quickstart.sh also auto-downloads it there
# h2kvmctl auto-discovers this path — no --virtio-win-iso flag needed

# Alternative: install from distro packages
# Fedora/RHEL:
# sudo dnf install virtio-win
# The ISO will be at: /usr/share/virtio-win/virtio-win.iso

# Or download manually:
# https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso
```

Verify:

```bash
ls /var/lib/h2kvm/virtio-win.iso
# or if installed via dnf:
# ls /usr/share/virtio-win/virtio-win.iso
```

---

## 1. Local Windows VMDK Migration

The simplest case: you have a Windows VMDK file locally.

### Create the YAML config

```yaml
# windows-local.yaml
cmd: local
vmdk: /path/to/windows-10.vmdk
output_dir: ./output-win10
to_output: win10.qcow2
out_format: qcow2
flatten: true
compress: true

# Windows mode
windows: true
guest_os: windows
virtio_win_iso: /usr/share/virtio-win/virtio-win.iso  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
remove_vmware_tools: true

# Two-phase boot: bootstrap first (SATA), then switch to VirtIO
win_stage: bootstrap

# libvirt domain XML
emit_domain_xml: true
virsh_define: true
vm_name: win10-migrated
memory: 4096
vcpus: 4
uefi: true
machine: q35
disk_bus: virtio
disk_cache: writeback
net_model: virtio
libvirt_network: default
graphics: spice
video: qxl
usb_tablet: true
clock: localtime

# Boot test
libvirt_test: true
keep_domain: true
timeout: 600

verbose: 1
```

### Run the migration

```bash
sudo ./h2kvmctl --config windows-local.yaml
```

### What happens under the hood

1. **Flatten** — collapses VMDK snapshot chain into a single disk
2. **Convert** — VMDK to qcow2 with compression
3. **VirtIO injection** — mounts the disk offline, injects VirtIO drivers:
   - `viostor` (storage) — registered as BOOT_START in the registry
   - `NetKVM` (network) — registered for PnP detection
   - `vioscsi` (SCSI) — alternative storage driver
   - `Balloon`, `vioserial`, `viorng` — optional drivers
4. **Registry edits** — adds VirtIO to `CriticalDeviceDatabase` and `Services` hive
5. **VMware Tools removal** — removes VMware driver files and registry entries
6. **Domain XML** — generates libvirt XML with two-phase boot config
7. **Boot test** — starts the VM and verifies it reaches running state

---

## 2. Two-Phase Boot Strategy

Windows cannot boot directly on VirtIO if it was installed on a VMware (LSI Logic/PVSCSI) disk controller. The two-phase boot solves this:

### Phase 1: Bootstrap (SATA)

```bash
# This is what win_stage: bootstrap does
sudo ./h2kvmctl --config windows-local.yaml
```

The bootstrap XML uses a **SATA disk controller** so Windows can boot on familiar hardware. During boot, Windows detects the injected VirtIO drivers via Plug and Play and installs them.

After Phase 1:
- VM boots with SATA disk
- VirtIO drivers are loaded and available in Device Manager
- VM is running — verify with `virsh list`

### Phase 2: Switch to VirtIO

Once VirtIO drivers are confirmed working, switch to VirtIO for production performance:

```bash
# Option A: Re-run with final stage
# Change win_stage: bootstrap to win_stage: final in the YAML, then:
sudo ./h2kvmctl --config windows-local.yaml

# Option B: Manual switch
virsh shutdown win10-migrated
virsh edit win10-migrated
# Change: <target dev='sda' bus='sata'/> → <target dev='vda' bus='virtio'/>
virsh start win10-migrated
```

Or use the h2kvmctl `--virtio-deploy-boot` flag:

```bash
sudo ./h2kvmctl --cmd local \
    --vmdk ./output-win10/win10.qcow2 \
    --windows \
    --win-stage final \
    --emit-domain-xml \
    --vm-name win10-migrated \
    --uefi --machine q35
```

### Verify VirtIO drivers in Windows

After Phase 2, check inside the Windows VM:
1. Open **Device Manager**
2. Look for:
   - `Red Hat VirtIO SCSI controller` under Storage controllers
   - `Red Hat VirtIO Ethernet Adapter` under Network adapters
   - `VirtIO Balloon Driver` under System devices

---

## 3. Export from vCenter and Migrate

End-to-end: export a Windows VM from vCenter and convert to libvirt.

### Using ovftool

```yaml
# windows-vcenter.yaml
cmd: vsphere
vs_action: ovftool_export

# vCenter connection
vcenter: 10.73.213.134
vc_user: administrator@vsphere.local
vc_password: your-password
vc_insecure: true
dc_name: Datacenter

# ovftool
ovftool_no_ssl_verify: true
ovftool_accept_all_eulas: true

# VM to export
vm_name: windows-10-pro

# Disk processing
output_dir: ./output-win10-vcenter
flatten: true
to_output: win10-vcenter.qcow2
out_format: qcow2
compress: true

# Windows mode
windows: true
guest_os: windows
virtio_win_iso: /usr/share/virtio-win/virtio-win.iso  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
remove_vmware_tools: true
win_stage: bootstrap

# libvirt
emit_domain_xml: true
virsh_define: true
vm_name: win10-vcenter
memory: 8192
vcpus: 4
uefi: true
machine: q35
disk_bus: virtio
disk_cache: writeback
net_model: virtio
libvirt_network: default
graphics: spice
video: qxl
usb_tablet: true
clock: localtime

# Boot test
libvirt_test: true
keep_domain: true
timeout: 600

verbose: 1
```

### Using govc

```yaml
# windows-govc.yaml
cmd: vsphere
vs_action: export_vm
export_mode: ovf_export
vs_control_plane: govc

# vCenter connection
vcenter: 10.73.213.134
vc_user: administrator@vsphere.local
vc_password: your-password
vc_insecure: true
dc_name: Datacenter

# govc settings
govc_url: "https://10.73.213.134/sdk"
govc_insecure: true
govc_datacenter: Datacenter
govc_export_remove_cdroms: true

# VM to export
vm_name: windows-10-pro

# Same disk/Windows/libvirt settings as above...
output_dir: ./output-win10-govc
flatten: true
to_output: win10-govc.qcow2
out_format: qcow2
compress: true
windows: true
guest_os: windows
virtio_win_iso: /usr/share/virtio-win/virtio-win.iso  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
remove_vmware_tools: true
win_stage: bootstrap
emit_domain_xml: true
uefi: true
machine: q35
disk_bus: virtio
disk_cache: writeback
net_model: virtio
libvirt_network: default
graphics: spice
video: qxl
usb_tablet: true
clock: localtime
libvirt_test: true
timeout: 600
verbose: 1
```

Run:

```bash
sudo ./h2kvmctl --config windows-vcenter.yaml
# or
sudo ./h2kvmctl --config windows-govc.yaml
```

---

## 4. Windows Network Configuration

By default, Windows will use DHCP after migration. To set a static IP:

### YAML method

```yaml
# Add to your migration YAML:
win_net_json: |
  {
    "mode": "static",
    "address": "192.168.1.50",
    "prefix": 24,
    "gateway": "192.168.1.1",
    "dns": ["8.8.8.8", "8.8.4.4"]
  }
```

### JSON file method

```bash
# Create network config
cat > win-network.json << 'EOF'
{
  "mode": "dhcp",
  "dns": ["10.0.0.53"]
}
EOF

# Use in YAML:
# win_net_override: ./win-network.json
```

---

## 5. Windows Version-Specific Notes

### Windows 10

```yaml
windows: true
guest_os: windows
win_stage: bootstrap
uefi: true       # Most Win10 installs are UEFI
machine: q35
```

### Windows 11

Windows 11 requires TPM 2.0 and Secure Boot. After migration, add TPM to the domain XML:

```yaml
windows: true
guest_os: windows
win_stage: bootstrap
uefi: true
machine: q35     # Required for Windows 11

# After h2kvmctl generates the XML, add TPM manually:
# virsh edit win11-vm
# Add inside <devices>:
#   <tpm model='tpm-crb'>
#     <backend type='emulator' version='2.0'/>
#   </tpm>
```

Install swtpm for TPM emulation:

```bash
# Fedora/RHEL
sudo dnf install swtpm swtpm-tools

# Debian/Ubuntu
sudo apt install swtpm swtpm-tools
```

### Windows Server 2016/2019/2022

```yaml
windows: true
guest_os: windows
win_stage: bootstrap
uefi: true
machine: q35
memory: 4096     # Minimum for Server
vcpus: 2
```

---

## 6. CLI Quick Reference

### One-liner: local VMDK

```bash
sudo ./h2kvmctl --cmd local \
    --vmdk /path/to/windows.vmdk \
    --windows \
    --virtio-win-iso /usr/share/virtio-win/virtio-win.iso \  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
    --remove-vmware-tools \
    --flatten --to-output win.qcow2 --out-format qcow2 --compress \
    --win-stage bootstrap \
    --emit-domain-xml --uefi --machine q35 \
    --guest-os windows \
    --graphics spice --video qxl --usb-tablet \
    --clock localtime \
    --libvirt-test --timeout 600 \
    -v
```

### One-liner: vCenter export

```bash
sudo ./h2kvmctl --cmd vsphere \
    --vcenter vcenter.example.com \
    --vc-user administrator@vsphere.local \
    --vc-password-env VC_PASSWORD \
    --vc-insecure \
    --vs-action export_vm --export-mode ovf_export \
    --vm-name windows-10-pro \
    --govc-datacenter Datacenter \
    --windows \
    --virtio-win-iso /usr/share/virtio-win/virtio-win.iso \  # optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
    --flatten --to-output win10.qcow2 --out-format qcow2 --compress \
    --win-stage bootstrap \
    --emit-domain-xml --uefi --machine q35 \
    --guest-os windows \
    --libvirt-test --timeout 600 \
    -v
```

---

## 7. Troubleshooting

### Windows blue screens on first boot (INACCESSIBLE_BOOT_DEVICE)

The VirtIO storage driver wasn't injected correctly or `win_stage` wasn't set to `bootstrap`.

```bash
# Re-run with bootstrap stage (SATA boot)
# Ensure virtio_win_iso is available at the standard path
ls /var/lib/h2kvm/virtio-win.iso
# or install it:
sudo ./scripts/install-deps.sh --virtio-win
```

### Windows boots but no network

VirtIO network driver needs PnP detection. After booting:
1. Open Device Manager in Windows
2. Right-click the unknown network device
3. Update Driver → Browse → point to `E:\NetKVM\` (VirtIO ISO)

Or inject network config:

```yaml
win_net_json: '{"mode": "dhcp"}'
```

### Boot test times out

Windows takes longer to boot than Linux. Increase timeout:

```yaml
timeout: 600   # 10 minutes
```

### VirtIO ISO not found

```bash
# Recommended: use install-deps.sh (downloads to standard path)
sudo ./scripts/install-deps.sh --virtio-win
ls /var/lib/h2kvm/virtio-win.iso

# Alternative: Fedora/RHEL package
sudo dnf install virtio-win
ls /usr/share/virtio-win/virtio-win.iso

# Or download manually
curl -LO https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso
```

### UEFI firmware not found

```bash
# Fedora/RHEL
sudo dnf install edk2-ovmf

# Debian/Ubuntu
sudo apt install ovmf
```

---

## 8. Complete Migration Workflow Summary

```
VMware VM (Windows 10/11/Server)
  |
  |-- Export from vCenter (ovftool or govc)
  |   or copy local VMDK
  |
  v
h2kvmctl --windows --win-stage bootstrap
  (virtio-win.iso auto-discovered at /var/lib/h2kvm/virtio-win.iso)
  |
  |-- Flatten VMDK → qcow2
  |-- Inject VirtIO drivers (viostor, NetKVM, vioscsi)
  |-- Edit registry (BOOT_START, CriticalDeviceDatabase)
  |-- Remove VMware Tools
  |-- Generate libvirt XML (SATA bootstrap)
  |
  v
Phase 1: Boot with SATA
  |-- Windows detects VirtIO via PnP
  |-- Drivers install automatically
  |-- Verify in Device Manager
  |
  v
Phase 2: Switch to VirtIO
  |-- virsh edit → change bus='sata' to bus='virtio'
  |-- or re-run with --win-stage final
  |
  v
Production VM on KVM (VirtIO disk + network)
```

---

## See Also

- [vSphere Export Tutorial](05-vsphere-export-tools.md) — govc and OVF Tool setup
- [Installation Guide](../getting-started/01-Installation.md) — dependency installation
- [YAML Examples](../../examples/yaml/70-complete-workflows/) — distro-specific configs
- [VirtIO Driver Documentation](../../docs/windows-virtio-injection.md) — driver injection internals
