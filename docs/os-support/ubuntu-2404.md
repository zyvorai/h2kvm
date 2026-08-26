# Testing Converted Ubuntu 24.04.3 qcow2 on Fedora (GUI, BIOS)

This guide describes how to **validate a converted Ubuntu 24.04.3 qcow2 image**
using **KVM + libvirt** on Fedora, booting **with legacy BIOS (SeaBIOS)** and
attempting to land in **graphical mode** when available.

This is intended as a **post-conversion smoke test** after migrating
a VMware VMDK to qcow2 and applying offline fixes
(fstab, GRUB, initramfs, disk identifiers, etc.).

---

## Prerequisites

Before migrating this platform, ensure:

- ✓ h2kvm installed ([Installation Guide](02-Installation.md))
- ✓ Familiarity with [Quick Start Guide](03-Quick-Start.md)
- ✓ Root/sudo access
- ✓ Source VM accessible



## Table of Contents

- [Host Requirements (Fedora)](#host-requirements-fedora)
- [Image Under Test (Ubuntu 24.04.3)](#image-under-test-ubuntu-24043)
- [BIOS + GUI libvirt XML (Most Compatible)](#bios-gui-libvirt-xml-most-compatible)
- [Define and Start the VM](#define-and-start-the-vm)
- [Connect to the Console / GUI](#connect-to-the-console-gui)
  - [Option 1: virt-viewer (recommended)](#option-1-virt-viewer-recommended)
  - [Option 2: VNC](#option-2-vnc)
- [Expected Boot Sequence (Ubuntu 24.04.3)](#expected-boot-sequence-ubuntu-24043)
- [Troubleshooting](#troubleshooting)
  - [Drops to `grub>` prompt](#drops-to-grub-prompt)
  - [Drops to `(initramfs)` shell](#drops-to-initramfs-shell)
  - [Black screen after GRUB](#black-screen-after-grub)
  - [“No bootable device”](#no-bootable-device)
  - [Boots but no GUI](#boots-but-no-gui)
- [Notes (24.04.x specifics)](#notes-2404x-specifics)

---
## Host Requirements (Fedora)

Install required virtualization tools:

```bash
sudo dnf install -y \
  libvirt \
  qemu-kvm \
  qemu-img \
  virt-viewer
```

Enable libvirt and ensure the default network is active:

```bash
sudo systemctl enable --now libvirtd
sudo virsh net-start default 2>/dev/null || true
```

---

## Image Under Test (Ubuntu 24.04.3)

```
/home/ssahani/by-path/out/ubuntu-24.04.3.qcow2
```

**Assumptions:**

* Converted from VMware VMDK
* Legacy BIOS capable (non-UEFI build)
* Ubuntu **24.04.3** (Server or Desktop)
* GUI may or may not be installed (console-only is still a valid success)

---

## BIOS + GUI libvirt XML (Most Compatible)

This XML is conservative and generally works across Ubuntu images:

* SeaBIOS (`machine='pc'`)
* Virtio disk + network
* VNC graphics
* VGA video model

```bash
cat >/tmp/ubuntu-24043-test.xml <<'EOF'
<domain type='kvm'>
  <name>ubuntu-24043-gui</name>

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
      <source file='/home/ssahani/by-path/out/ubuntu-24.04.3.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>

    <!-- Network -->
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>

    <!-- Graphics -->
    <graphics type='vnc' autoport='yes' listen='127.0.0.1'/>

    <!-- Video -->
    <video>
      <model type='vga'/>
    </video>

    <input type='tablet' bus='usb'/>
  </devices>
</domain>
EOF
```

---

## Define and Start the VM

Remove any existing domain with the same name:

```bash
sudo virsh destroy ubuntu-24043-gui 2>/dev/null || true
sudo virsh undefine ubuntu-24043-gui 2>/dev/null || true
```

Define and start:

```bash
sudo virsh define /tmp/ubuntu-24043-test.xml
sudo virsh start ubuntu-24043-gui
```

---

## Connect to the Console / GUI

### Option 1: virt-viewer (recommended)

```bash
virt-viewer ubuntu-24043-gui
```

### Option 2: VNC

```bash
sudo virsh vncdisplay ubuntu-24043-gui
```

Connect to the displayed address, e.g.:

```
127.0.0.1:5901
```

---

## Expected Boot Sequence (Ubuntu 24.04.3)

A successful boot typically shows:

1. SeaBIOS splash
2. GRUB menu
3. Ubuntu kernel + initramfs
4. Either:

   * **GDM login** (Desktop / GUI installed), or
   * **Text login prompt** (Server image)

 **Pass condition:** any stable login prompt (GUI or console).

---

## Troubleshooting

### Drops to `grub>` prompt

Typical reasons:

* Broken GRUB config
* Wrong root device UUID
* Missing `/boot` or broken `/etc/fstab`

Quick check from GRUB:

```
ls
ls (hd0,msdos1)/
ls (hd0,gpt1)/
```

---

### Drops to `(initramfs)` shell

Likely causes:

* root device mismatch (`/dev/sda` → `vda`)
* missing virtio modules in initramfs (`virtio_blk`, `virtio_pci`, `virtio_scsi`)
* bad `/etc/fstab`

Inside initramfs:

```bash
ls /dev/vd*
ls /dev/disk/by-uuid
cat /proc/cmdline
```

Offline fix (inside guest, once booted) usually is:

```bash
sudo update-initramfs -u
sudo update-grub
```

---

### Black screen after GRUB

Try an alternate video model:

```xml
<model type='qxl' vram='65536'/>
```

or:

```xml
<model type='virtio'/>
```

---

### “No bootable device”

Some converted installs expect SATA first.

Switch the disk bus for the first boot:

```xml
<target dev='sda' bus='sata'/>
```

After it boots and initramfs is confirmed sane, revert to virtio.

---

### Boots but no GUI

Ubuntu Server defaults to:

```bash
systemctl get-default
```

Expected:

```
multi-user.target
```

This is **not a failure**.

If you want to verify GUI bits exist:

```bash
dpkg -l | egrep 'ubuntu-desktop|gdm3|gnome-shell'
```

---

## Notes (24.04.x specifics)

* Ubuntu 24.04.x typically uses GRUB for BIOS installs.
* Netplan is expected; network coming up via DHCP on `default` libvirt network is the normal smoke-test baseline.
* Console success is still a **pass** even if the original VM was “desktop-ish”.

---

**Status:**  Smoke test template for Ubuntu 24.04.3 (BIOS, KVM/libvirt)
