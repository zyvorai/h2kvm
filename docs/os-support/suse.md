# Testing Converted openSUSE qcow2 on Fedora (GUI, BIOS)

This guide describes how to **validate a converted openSUSE qcow2 image**
using **KVM + libvirt** on Fedora, booting **directly into graphical (GUI) mode**
with **legacy BIOS (SeaBIOS)**.

This is intended as a **post-conversion smoke test** after migrating
a VMware VMDK to qcow2 and applying offline fixes (fstab, GRUB, initramfs, etc.).

---


## Table of Contents

- [Host Requirements (Fedora)](#host-requirements-fedora)
- [Image Under Test](#image-under-test)
- [BIOS + GUI libvirt XML (Most Compatible)](#bios-gui-libvirt-xml-most-compatible)
- [Define and Start the VM](#define-and-start-the-vm)
- [Connect to the GUI](#connect-to-the-gui)
  - [Option 1: virt-viewer (recommended)](#option-1-virt-viewer-recommended)
  - [Option 2: VNC](#option-2-vnc)
- [Expected Boot Sequence](#expected-boot-sequence)
- [Troubleshooting](#troubleshooting)
  - [Black screen after GRUB](#black-screen-after-grub)
  - [“No bootable device”](#no-bootable-device)
  - [Boots to text mode only](#boots-to-text-mode-only)
- [Notes](#notes)

---
## Host Requirements (Fedora)

Install required virtualization tools:

```bash
sudo dnf install -y \
  libvirt \
  qemu-kvm \
  qemu-img \
  virt-viewer
````

Enable libvirt and ensure the default network is active:

```bash
sudo systemctl enable --now libvirtd
sudo virsh net-start default 2>/dev/null || true
```

---

## Image Under Test

```
/home/ssahani/by-path/out/opensuse-leap-15.4-fixed.qcow2
```

**Assumptions:**

* Converted from VMware VMDK
* Legacy BIOS (non-UEFI)
* openSUSE Leap 15.4

---

## BIOS + GUI libvirt XML (Most Compatible)

This XML configuration is intentionally conservative and works reliably
for legacy openSUSE guests:

* SeaBIOS (`machine='pc'`)
* Virtio disk + network
* VNC graphics
* QXL video

```bash
cat >/tmp/opensuse-test.xml <<'EOF'
<domain type='kvm'>
  <name>opensuse-leap-15-4-gui</name>

  <memory unit='MiB'>4096</memory>
  <vcpu>2</vcpu>

  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>

  <features>
    <acpi/>
    <apic/>
  </features>

  <cpu mode='host-passthrough'/>

  <devices>
    <!-- Disk -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/home/ssahani/by-path/out/opensuse-leap-15.4-fixed.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>

    <!-- Network -->
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>

    <!-- Graphics -->
    <graphics type='vnc' autoport='yes' listen='127.0.0.1'/>

    <video>
      <model type='qxl' vram='65536'/>
    </video>

    <input type='tablet' bus='usb'/>
  </devices>
</domain>
EOF
```

---

## Define and Start the VM

If a domain with the same name already exists, remove it first:

```bash
sudo virsh destroy opensuse-leap-15-4-gui 2>/dev/null || true
sudo virsh undefine opensuse-leap-15-4-gui 2>/dev/null || true
```

Define and start the VM:

```bash
sudo virsh define /tmp/opensuse-test.xml
sudo virsh start opensuse-leap-15-4-gui
```

---

## Connect to the GUI

### Option 1: virt-viewer (recommended)

```bash
virt-viewer opensuse-leap-15-4-gui
```

### Option 2: VNC

```bash
sudo virsh vncdisplay opensuse-leap-15-4-gui
```

Connect to the displayed address, for example:

```
127.0.0.1:5901
```

---

## Expected Boot Sequence

A successful boot should show:

1. SeaBIOS splash
2. GRUB menu
3. openSUSE kernel + initramfs
4. Graphical login screen

If this sequence completes, the image is **boot-validated**.

---

## Troubleshooting

### Black screen after GRUB

Try a simpler video model:

```xml
<model type='vga'/>
```

### “No bootable device”

Some older installs expect SATA instead of virtio:

```xml
<target dev='sda' bus='sata'/>
```

### Boots to text mode only

This is a **guest OS configuration issue**, not a virtualization problem.

Inside the guest:

```bash
systemctl get-default
systemctl status display-manager
```

---

## Notes

* This test avoids UEFI entirely
* Designed for legacy VMware → KVM migrations
* Suitable as an automated or manual post-conversion smoke test

---

**Status:** ✅ Verified working for openSUSE Leap 15.4 (BIOS, GUI)

```
