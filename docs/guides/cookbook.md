## Usage cookbook (CLI ↔ YAML side by side)

This section shows **the same operation expressed two ways**:

1. **CLI invocation** — good for exploration and one-offs  
2. **YAML config** — recommended for repeatability, audits, and automation  

If something matters, put it in YAML.

---

## Prerequisites

Before following this guide, you should have:

- ✓ Completed the [Installation](02-Installation.md)
- ✓ Familiarity with basic h2kvm concepts
- ✓ Root/sudo access to your system
- ✓ Source VM files ready for migration



## Table of Contents

- [1. Local mode — Linux VMDK → qcow2](#1-local-mode-linux-vmdk-qcow2)
  - [CLI](#cli)
  - [YAML](#yaml)
- [2. Local mode — Windows VMDK with VirtIO pre-staging](#2-local-mode-windows-vmdk-with-virtio-pre-staging)
  - [CLI](#cli)
  - [YAML](#yaml)
- [3. Dry-run inspection (no writes)](#3-dry-run-inspection-no-writes)
  - [CLI](#cli)
  - [YAML](#yaml)
- [4. Fetch-and-fix — ESXi over SSH](#4-fetch-and-fix-esxi-over-ssh)
  - [CLI](#cli)
  - [YAML](#yaml)
- [5. Live-fix — running Linux VM over SSH](#5-live-fix-running-linux-vm-over-ssh)
  - [CLI](#cli)
  - [YAML](#yaml)
- [6. OVA appliance conversion](#6-ova-appliance-conversion)
  - [CLI](#cli)
  - [YAML](#yaml)
- [7. OVF descriptor conversion](#7-ovf-descriptor-conversion)
  - [CLI](#cli)
  - [YAML](#yaml)
- [8. vSphere — list VMs (pyvmomi control-plane)](#8-vsphere-list-vms-pyvmomi-control-plane)
  - [CLI](#cli)
  - [YAML](#yaml)
- [9. vSphere — download a VM disk](#9-vsphere-download-a-vm-disk)
  - [CLI](#cli)
  - [YAML](#yaml)
- [10. vSphere — download entire VM folder (HTTP data-plane)](#10-vsphere-download-entire-vm-folder-http-data-plane)
  - [CLI](#cli)
  - [YAML](#yaml)
- [11. vSphere — CBT delta sync](#11-vsphere-cbt-delta-sync)
  - [CLI](#cli)
  - [YAML](#yaml)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
    - [Issue: Command fails with permission denied](#issue-command-fails-with-permission-denied)
    - [Issue: Guest disk mount fails](#issue-guest-disk-mount-fails)
- [Next Steps](#next-steps)
- [Getting Help](#getting-help)

---
## 1. Local mode — Linux VMDK → qcow2

### CLI

```bash
sudo h2kvmctl \
  --output-dir ./out \
  local \
  --vmdk /path/to/linux.vmdk \
  --to-output linux-fixed.qcow2 \
  --flatten \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --remove-vmware-tools \
  --checksum \
  -v
````

### YAML

```yaml
command: local
output_dir: ./out

vmdk: /path/to/linux.vmdk
to_output: linux-fixed.qcow2

flatten: true
fstab_mode: stabilize-all
regen_initramfs: true
remove_vmware_tools: true

checksum: true
verbose: 1
```bash

---

## 2. Local mode — Windows VMDK with VirtIO pre-staging

> **Standard path**: `quickstart.sh` installs `virtio-win.iso` to `/var/lib/h2kvm/virtio-win.iso`.
> When the ISO is at the standard path, h2kvm auto-discovers it — no `--virtio-drivers-dir` flag needed.
> Use `--virtio-drivers-dir` only to override with a custom location.

### CLI

```bash
# If virtio-win.iso is at /var/lib/h2kvm/virtio-win.iso, omit --virtio-drivers-dir:
sudo h2kvmctl \
  --output-dir ./out \
  local \
  --vmdk /path/to/windows.vmdk \
  --to-output windows-fixed.qcow2 \
  --flatten \
  --checksum \
  -v

# Or override with a custom path:
sudo h2kvmctl \
  --output-dir ./out \
  local \
  --vmdk /path/to/windows.vmdk \
  --to-output windows-fixed.qcow2 \
  --flatten \
  --virtio-drivers-dir /path/to/virtio-win \
  --checksum \
  -v
```bash

### YAML

```yaml
command: local
output_dir: ./out

vmdk: /path/to/windows.vmdk
to_output: windows-fixed.qcow2

flatten: true
# optional — auto-discovered at /var/lib/h2kvm/virtio-win.iso
virtio_drivers_dir: /path/to/virtio-win

checksum: true
verbose: 1
```bash

This injects BOOT_START VirtIO drivers and registry entries **before first KVM boot**.

---

## 3. Dry-run inspection (no writes)

### CLI

```bash
sudo h2kvmctl \
  --dry-run \
  --print-fstab \
  local \
  --vmdk /path/to/vm.vmdk \
  -vv
```bash

### YAML

```yaml
command: local
vmdk: /path/to/vm.vmdk

dry_run: true
print_fstab: true
verbose: 2
```bash

Use this to understand **exactly what would change**.

---

## 4. Fetch-and-fix — ESXi over SSH

### CLI

```bash
sudo h2kvmctl \
  --output-dir ./out \
  fetch-and-fix \
  --host esxi.example.com \
  --user root \
  --remote /vmfs/volumes/datastore1/vm/vm.vmdk \
  --fetch-all \
  --flatten \
  --to-output esxi-fixed.qcow2 \
  -v
```bash

### YAML

```yaml
command: fetch-and-fix
output_dir: ./out

host: esxi.example.com
user: root
remote: /vmfs/volumes/datastore1/vm/vm.vmdk

fetch_all: true
flatten: true
to_output: esxi-fixed.qcow2

verbose: 1
```bash

This fetches the **entire snapshot chain**, flattens it, and converts offline.

---

## 5. Live-fix — running Linux VM over SSH

### CLI

```bash
sudo h2kvmctl \
  live-fix \
  --host vm.example.com \
  --user root \
  --sudo \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --remove-vmware-tools \
  -v
```bash

### YAML

```yaml
command: live-fix

host: vm.example.com
user: root
sudo: true

fstab_mode: stabilize-all
regen_initramfs: true
remove_vmware_tools: true

verbose: 1
```bash

Live-fix is **post-migration hygiene**, not a replacement for offline repair.

---

## 6. OVA appliance conversion

### CLI

```bash
sudo h2kvmctl \
  --output-dir ./out \
  ova \
  --ova appliance.ova \
  --flatten \
  --to-output appliance.qcow2 \
  -v
```bash

### YAML

```yaml
command: ova
output_dir: ./out

ova: appliance.ova
flatten: true
to_output: appliance.qcow2

verbose: 1
```bash

---

## 7. OVF descriptor conversion

### CLI

```bash
sudo h2kvmctl \
  --output-dir ./out \
  ovf \
  --ovf appliance.ovf \
  --flatten \
  --to-output appliance.qcow2 \
  -v
```bash

### YAML

```yaml
command: ovf
output_dir: ./out

ovf: appliance.ovf
flatten: true
to_output: appliance.qcow2

verbose: 1
```bash

---

## 8. vSphere — list VMs (pyvmomi control-plane)

### CLI

```bash
h2kvmctl vsphere \
  --vcenter vcenter.example.com \
  --vc-user administrator@vsphere.local \
  --vc-password-env VC_PASSWORD \
  --vc-insecure \
  list_vm_names \
  --json
```bash

### YAML

```yaml
command: vsphere

vcenter: vcenter.example.com
vc_user: administrator@vsphere.local
vc_password_env: VC_PASSWORD
vc_insecure: true

vs_action: list_vm_names
json: true
```bash

---

## 9. vSphere — download a VM disk

### CLI

```bash
h2kvmctl vsphere \
  --vcenter vcenter.example.com \
  --vc-user administrator@vsphere.local \
  --vc-password-env VC_PASSWORD \
  --vc-insecure \
  download_vm_disk \
  --vm-name myVM \
  --disk 0 \
  --local-path ./downloads/myVM-disk0.vmdk
```bash

### YAML

```yaml
command: vsphere

vcenter: vcenter.example.com
vc_user: administrator@vsphere.local
vc_password_env: VC_PASSWORD
vc_insecure: true

vs_action: download_vm_disk
vm_name: myVM
disk: 0
local_path: ./downloads/myVM-disk0.vmdk
```bash

---

## 10. vSphere — download entire VM folder (HTTP data-plane)

### CLI

```bash
h2kvmctl vsphere \
  --vcenter vcenter.example.com \
  --vc-user administrator@vsphere.local \
  --vc-password-env VC_PASSWORD \
  --vc-insecure \
  download_only_vm \
  --vm-name myVM \
  --output-dir ./downloads/myVM
```bash

### YAML

```yaml
command: vsphere

vcenter: vcenter.example.com
vc_user: administrator@vsphere.local
vc_password_env: VC_PASSWORD
vc_insecure: true

vs_action: download_only_vm
vm_name: myVM
output_dir: ./downloads/myVM

vs_include_glob: ["*"]
vs_exclude_glob: ["*.log"]
vs_concurrency: 6
```bash

This uses:

* pyvmomi for inventory
* HTTPS `/folder` for data transfer
* optional parallel downloads

---

## 11. vSphere — CBT delta sync

### CLI

```bash
h2kvmctl vsphere \
  --vcenter vcenter.example.com \
  --vc-user administrator@vsphere.local \
  --vc-password-env VC_PASSWORD \
  --vc-insecure \
  cbt_sync \
  --vm-name myVM \
  --disk 0 \
  --local-path ./downloads/myVM-disk0.vmdk \
  --enable-cbt \
  --snapshot-name h2kvm-cbt \
  --change-id "*"
```bash

### YAML

```yaml
command: vsphere

vcenter: vcenter.example.com
vc_user: administrator@vsphere.local
vc_password_env: VC_PASSWORD
vc_insecure: true

vs_action: cbt_sync
vm_name: myVM
disk: 0
local_path: ./downloads/myVM-disk0.vmdk

enable_cbt: true
snapshot_name: h2kvm-cbt
change_id: "*"
```bash

## Troubleshooting

### Common Issues

#### Issue: Command fails with permission denied

**Symptoms:**
- Error: "Permission denied" when accessing disk images
- Cannot write to output directory

**Solution:**
```bash
# Run with sudo
sudo h2kvmctl --config your-config.yaml

# Or fix permissions
sudo chown $(whoami) /path/to/output/directory
```

#### Issue: Guest disk mount fails

**Symptoms:**
- Error: "guestfs_mount: failed" or GuestKit mount error
- Cannot inspect guest OS

**Solution:**
```bash
# GuestKit is the default backend; check NBD availability
sudo modprobe nbd
ls /dev/nbd0

# Verify GuestKit backend dependencies
qemu-nbd --version
qemu-img --version

# Check KVM permissions
sudo usermod -aG kvm $(whoami)
# Log out and back in

# Verify disk image
qemu-img info /path/to/disk.vmdk
```

For more issues, see [Failure Modes](troubleshooting.md).

## Next Steps

Continue your migration journey:

- **[CLI Reference](04-CLI-Reference.md)** - Complete command options
- **[YAML Examples](05-YAML-Examples.md)** - Configuration templates
- **[Cookbook](06-Cookbook.md)** - Common scenarios
- **[Troubleshooting](troubleshooting.md)** - When things go wrong

## Getting Help

Found an issue? [Report it on GitHub](https://github.com/ssahani/h2kvm/issues)

