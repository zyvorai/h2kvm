---
title: "hyper2kvm — Ubuntu 22.04 LVM vCenter Migration Report"
date: "March 19, 2026"
author: "hyper2kvm Migration Team"
---

# Ubuntu 22.04 LVM — vCenter to KVM Migration Report

**Date:** March 19, 2026
**Tool:** hyper2kvm v0.3.0
**Source:** VMware vCenter 10.73.213.134 (ESXi 8.0)
**Target:** Fedora 43 (KVM/libvirt)

---

## 1. Source VM Details

| Parameter | Value |
|-----------|-------|
| VM Name | esx8.0-ubuntu22.04.5-x64-with-lvm-partitions |
| vCenter | 10.73.213.134 |
| Datacenter | data |
| ESXi Host | 10.73.212.36 |
| Guest OS | Debian GNU/Linux 12 (64-bit) |
| Actual OS | Ubuntu 22.04.5 LTS |
| Memory | 2048 MB |
| vCPUs | 1 |
| Disk | LVM partitions |
| Power State | poweredOff |
| Firmware | UEFI |

---

## 2. Migration Config

**File:** `ubuntu-vcenter-to-libvirt.yaml`

```yaml
cmd: vsphere
vs_action: export_vm
export_mode: ovf_export
vs_control_plane: govc

vcenter: 10.73.213.134
vc_user: administrator@vsphere.local
vc_password: VCENTER@redhat2025
vc_insecure: true
dc_name: data
govc_url: "https://10.73.213.134/sdk"
govc_insecure: true
govc_datacenter: data
govc_export_remove_cdroms: true

vm_name: esx8.0-ubuntu22.04.5-x64-with-lvm-partitions

output_dir: ./output-ubuntu
flatten: true
to_output: ubuntu-2204.qcow2
out_format: qcow2
compress: true

fstab_mode: stabilize-all
regen_initramfs: true
remove_vmware_tools: true

emit_domain_xml: true
virsh_define: true
memory: 2048
vcpus: 2
uefi: true
machine: q35
disk_bus: virtio
disk_cache: none
net_model: virtio
libvirt_network: default
serial_console: true
graphics: vnc
guest_os: linux

libvirt_test: true
keep_domain: true
timeout: 120

verbose: 1
```

**Command:**
```bash
sudo ./h2kvmctl --config ubuntu-vcenter-to-libvirt.yaml
```

---

## 3. Migration Pipeline

```
vCenter (10.73.213.134 / datacenter: data)
  │
  │  govc export.ovf (NFC streaming, ~3 hours)
  ▼
OVF + VMDK (5.4 GB)
  │
  │  Auto-chained (no manual step)
  ▼
VMCraft offline fixes
  ├── fstab stabilized (UUID-based mounts)
  ├── initramfs rebuilt (virtio_blk, virtio_scsi, virtio_net, nvme)
  ├── LVM volumes activated and fixed
  └── VMware Tools removed
  │
  │  qemu-img convert (flatten + compress)
  ▼
ubuntu-2204.qcow2 (5.4 GB compressed)
  │
  │  emit libvirt domain XML
  ▼
libvirt domain defined + started
  │
  │  boot test
  ▼
VM RUNNING on KVM ✓
```

---

## 4. Results

### Export Phase

| Metric | Value |
|--------|-------|
| Export method | govc export.ovf (NFC) |
| Export time | ~3 hours |
| VMDK size | 5.4 GB |
| OVF size | 9.3 KB |
| CD-ROM removed | cdrom-3000 |

### Conversion Phase

| Metric | Value |
|--------|-------|
| Backend | VMCraft (pure Python + qemu-nbd) |
| Input | 5.4 GB VMDK |
| Output | ubuntu-2204.qcow2 (5.4 GB compressed) |
| Format | qcow2 |
| Pipeline chaining | Automatic (govc → convert → fixes → libvirt) |

### Guest Fixes Applied

| Fix | Status |
|-----|--------|
| fstab stabilization | Applied (UUID-based) |
| initramfs rebuild | Applied (virtio_blk, virtio_scsi, virtio_net, nvme) |
| LVM activation | Activated |
| VMware Tools removal | Removed |
| Boot configuration | UEFI (systemd-boot) |

### libvirt Deployment

| Metric | Value |
|--------|-------|
| Domain name | esx8.0-ubuntu22.04.5-x64-with-lvm-partitions |
| Domain XML | output-ubuntu/libvirt/esx8.0-ubuntu22.04.5-x64-with-lvm-partitions.xml |
| Machine type | q35 |
| Firmware | UEFI (OVMF) |
| Disk bus | virtio |
| Network | virtio (default network) |
| Graphics | VNC |
| virsh define | SUCCESS |
| virsh start | SUCCESS |
| Boot test | PASSED — domain reached RUNNING state |

---

## 5. Output Files

```
output-ubuntu/
├── ubuntu-2204.qcow2                                              (5.4 GB)
├── libvirt/
│   └── esx8.0-ubuntu22.04.5-x64-with-lvm-partitions.xml          (1.9 KB)
├── esx8.0-ubuntu22.04.5-x64-with-lvm-partitions.VARS.fd           (NVRAM)
└── work/                                                           (temp)
```

---

## 6. Verification

```
$ sudo virsh list | grep ubuntu
 20   esx8.0-ubuntu22.04.5-x64-with-lvm-partitions   running

$ ls -lh output-ubuntu/ubuntu-2204.qcow2
-rw-r--r-- 1 qemu qemu 5.4G output-ubuntu/ubuntu-2204.qcow2

$ ls -lh output-ubuntu/libvirt/*.xml
-rw-r--r-- 1 root root 1.9K output-ubuntu/libvirt/esx8.0-ubuntu22.04.5-x64-with-lvm-partitions.xml
```

---

## 7. Target Host Environment

| Component | Version |
|-----------|---------|
| OS | Fedora 43 (kernel 6.18.13) |
| hyper2kvm | 0.3.0 |
| govc | 0.44.0 |
| qemu-img | 10.1.4 |
| libvirt | 11.6.0 |
| OVMF | OVMF_CODE.fd |
| Backend | VMCraft (pure Python) |

---

## 8. Conclusion

**Result: SUCCESS**

Ubuntu 22.04.5 LTS with LVM partitions was successfully migrated from VMware vCenter (ESXi 8.0) to KVM/libvirt using a single `h2kvmctl --config` command. The entire pipeline — govc NFC export, disk conversion, offline guest fixes (fstab, initramfs, LVM, VMware Tools), libvirt domain creation, and boot test — ran automatically without manual intervention.
