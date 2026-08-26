## Step-by-step: first boot validation with SATA + UEFI (libvirt)

This is the safest “first boot” profile for Windows images that were converted from VMware, because it avoids the classic trap:

> Windows boots once with a conservative storage controller (SATA/AHCI), then you install VirtIO inside the guest, then you switch the disk bus to VirtIO.

That sequence prevents **INACCESSIBLE_BOOT_DEVICE** when the VirtIO storage driver isn’t boot-ready yet.


## Table of Contents

- [Prerequisites](#prerequisites)
  - [0) Host prerequisites (Fedora/RHEL family)](#0-host-prerequisites-fedorarhel-family)
  - [1) Put the qcow2 where libvirt/qemu can read it](#1-put-the-qcow2-where-libvirtqemu-can-read-it)
  - [2) Create a per-VM OVMF VARS file](#2-create-a-per-vm-ovmf-vars-file)
  - [3) Save the domain XML](#3-save-the-domain-xml)
  - [4) Define and boot the VM](#4-define-and-boot-the-vm)
  - [5) Connect a viewer](#5-connect-a-viewer)
- [After Windows boots: install VirtIO drivers (so you can switch to VirtIO safely)](#after-windows-boots-install-virtio-drivers-so-you-can-switch-to-virtio-safely)
- [Troubleshooting quick hits](#troubleshooting-quick-hits)
  - [VM won’t start / “Permission denied”](#vm-wont-start-permission-denied)
  - [Black screen](#black-screen)
  - [INACCESSIBLE_BOOT_DEVICE on VirtIO boot](#inaccessible_boot_device-on-virtio-boot)
- [Problem statement](#problem-statement)
- [Driver injection model](#driver-injection-model)
  - [Supported driver classes](#supported-driver-classes)
- [Registry editing (offline)](#registry-editing-offline)
  - [SYSTEM hive operations](#system-hive-operations)
  - [Required service values](#required-service-values)
- [CriticalDeviceDatabase (CDD)](#criticaldevicedatabase-cdd)
- [BCD handling](#bcd-handling)
  - [What we do](#what-we-do)
  - [What we do NOT do](#what-we-do-not-do)
- [Common failure prevented](#common-failure-prevented)
- [Next Steps](#next-steps)
- [Getting Help](#getting-help)

---

## Prerequisites

For Windows VM migration, you need:

- ✓ h2kvm installed ([Installation Guide](02-Installation.md))
- ✓ VirtIO drivers ISO available (see below)
- ✓ Windows source VM disk (VMDK, VHD, etc.)
- ✓ Understanding of [Windows Boot Cycle](11-Windows-Boot-Cycle.md)

### VirtIO Drivers ISO

The VirtIO drivers ISO is **automatically discovered** at `/var/lib/h2kvm/virtio-win.iso`. Download it with:

```bash
sudo ./scripts/install-deps.sh --virtio-win
```

Once downloaded, h2kvm finds the ISO automatically -- no extra flags needed. Use `--virtio-drivers-dir` only to override with a custom path.

### 0) Host prerequisites (Fedora/RHEL family)

```bash
sudo dnf install -y \
  libvirt \
  qemu-kvm \
  virt-viewer \
  edk2-ovmf

sudo systemctl enable --now libvirtd
sudo virsh net-start default 2>/dev/null || true
```bash

### 1) Put the qcow2 where libvirt/qemu can read it

Libvirt often runs QEMU under a confined user/service context. Even if the qcow2 file is `644`, the *parent directories* can still block traversal.

**Recommended**: move/copy to a libvirt-friendly location:

```bash
sudo mkdir -p /var/lib/libvirt/images
sudo cp -a /home/ssahani/tt/h2kvm/out/windows10-fixed.qcow2 /var/lib/libvirt/images/
sudo chmod 644 /var/lib/libvirt/images/windows10-fixed.qcow2
```bash

(If you *must* keep it under `/home/...`, ensure directory execute bits allow traversal; on SELinux systems you may also need proper labeling.)

### 2) Create a per-VM OVMF VARS file

UEFI NVRAM state must be unique per VM.

```bash
sudo cp -a /usr/share/edk2/ovmf/OVMF_VARS.fd /var/tmp/win10-fixed-sata_VARS.fd
sudo chmod 644 /var/tmp/win10-fixed-sata_VARS.fd
```bash

### 3) Save the domain XML

Create `win10-sata-uefi.xml` with the contents below.

**Important**: I changed the `<source file=...>` to point at `/var/lib/libvirt/images/windows10-fixed.qcow2` to match step (1). If you keep your original path, update it consistently.

```xml
<!-- win10-sata-uefi.xml -->
<domain type='kvm'>
  <name>win10-fixed-sata</name>
  <memory unit='MiB'>4096</memory>
  <currentMemory unit='MiB'>4096</currentMemory>
  <vcpu placement='static'>4</vcpu>

  <os>
    <type arch='x86_64' machine='pc-q35-8.2'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>
    <nvram>/var/tmp/win10-fixed-sata_VARS.fd</nvram>
    <boot dev='hd'/>
  </os>

  <features>
    <acpi/>
    <apic/>
    <hyperv mode='custom'>
      <relaxed state='on'/>
      <vapic state='on'/>
      <spinlocks state='on' retries='8191'/>
    </hyperv>
    <vmport state='off'/>
  </features>

  <cpu mode='host-passthrough' check='none'/>
  <clock offset='localtime'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>

  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>

  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <!-- SATA/AHCI controller -->
    <controller type='sata' index='0'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x1f' function='0x2'/>
    </controller>

    <!-- Disk on SATA (safe first boot) -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none' io='native'/>
      <source file='/var/lib/libvirt/images/windows10-fixed.qcow2'/>
      <target dev='sda' bus='sata'/>
    </disk>

    <!-- Network: e1000e for max compatibility; switch to virtio later -->
    <interface type='network'>
      <source network='default'/>
      <model type='e1000e'/>
    </interface>

    <!-- USB + input -->
    <controller type='usb' model='qemu-xhci'/>
    <input type='tablet' bus='usb'/>
    <input type='mouse' bus='ps2'/>
    <input type='keyboard' bus='ps2'/>

    <!-- Graphics -->
    <graphics type='spice' autoport='yes' listen='127.0.0.1'/>
    <video>
      <model type='qxl' ram='65536' vram='65536' heads='1'/>
    </video>

    <!-- Sound -->
    <sound model='ich9'/>

    <!-- Serial console -->
    <serial type='pty'>
      <target port='0'/>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
  </devices>
</domain>
```bash

### 4) Define and boot the VM

```bash
sudo virsh define win10-sata-uefi.xml
sudo virsh start win10-fixed-sata
```bash

### 5) Connect a viewer

```bash
virt-viewer win10-fixed-sata
```bash

You should now see the Windows boot sequence. On the first boot, expect Windows to do some hardware detection and driver setup.

---

## After Windows boots: install VirtIO drivers (so you can switch to VirtIO safely)

Once you can log in successfully, install VirtIO inside Windows. Attach the VirtIO driver ISO (at `/var/lib/h2kvm/virtio-win.iso` if installed via `install-deps.sh --virtio-win`) as a CDROM and run the installer, or use Device Manager to point to the mounted ISO.

After VirtIO storage drivers are installed, you can switch:

* disk bus: `sata` → `virtio`
* network model: `e1000e` → `virtio`

(Do this in a *copy* of the XML or via `virsh edit win10-fixed-sata`.)

---

## Troubleshooting quick hits

### VM won’t start / “Permission denied”

Typical causes:

* qcow2 is in a path QEMU can’t traverse (`/home/...` with restrictive directory perms)
* SELinux labeling mismatch on the file/dir
* wrong permissions on NVRAM vars file

Fastest fix is what we already do above: keep disks under `/var/lib/libvirt/images/` and ensure:

* `chmod 644` on qcow2 and vars file
* parent directories are traversable (execute bit)

### Black screen

* Make sure OVMF paths exist (`/usr/share/edk2/ovmf/OVMF_CODE.fd` and `OVMF_VARS.fd` may differ by distro)
* Try removing any leftover conflicting NVRAM file and recreating it

### INACCESSIBLE_BOOT_DEVICE on VirtIO boot

That’s exactly why we start with SATA.
Boot with SATA, install VirtIO drivers in Windows, then switch.

---

If you want, I can also add the **follow-up section** that shows the *VirtIO version* of the same XML (disk bus virtio + virtio-net) and a minimal snippet for attaching a `virtio-win.iso` CDROM in libvirt.
# WINDOWS.md — Windows Migration Deep Dive

This document explains how `h2kvm` handles Windows guests and **why each step exists**.

---

## Problem statement

Windows does not boot based on:
- filesystem correctness
- disk visibility
- registry sanity alone

It boots based on **boot-critical drivers registered correctly**.

---

## Driver injection model

### Supported driver classes
- Storage: viostor / vioscsi
- Network: netkvm
- Balloon: balloon
- Optional: virtiofs, input, GPU

Drivers are copied to:
```bash
Windows/System32/drivers/
```bash

---

## Registry editing (offline)

### SYSTEM hive operations
- Opened via `hivex`
- Correct ControlSet detected
- Services created under:
  ```
  HKLM\SYSTEM\ControlSetXXX\Services
  ```

### Required service values
- `Type = 1` (kernel driver)
- `Start = BOOT or SYSTEM`
- `Group = Boot Bus Extender` (storage)

---

## CriticalDeviceDatabase (CDD)

Without CDD entries, Windows may:
- ignore a valid driver
- bind it too late
- blue-screen at boot

Entries are created under:
```bash
HKLM\SYSTEM\ControlSetXXX\Control\CriticalDeviceDatabase
```bash

Mapped by PCI vendor/device IDs.

---

## BCD handling

### What we do
- Detect BIOS and UEFI BCD stores
- Create timestamped backups
- Report presence and size

### What we do NOT do
- Binary patch BCD
- Run `bcdedit` offline

This avoids corrupting boot metadata.

---

## Common failure prevented

**INACCESSIBLE_BOOT_DEVICE**

Caused by:
- wrong StartType
- missing CDD
- wrong storage driver selected

`h2kvm` fixes all three before first boot.

## Next Steps

For Windows migrations:

- **[Windows Boot Cycle](11-Windows-Boot-Cycle.md)** - Understanding Windows boot process
- **[Windows Troubleshooting](12-Windows-Troubleshooting.md)** - Common Windows issues
- **[Windows Networking](13-Windows-Networking.md)** - Network and driver configuration

## Getting Help

- [Troubleshooting Guide](90-Failure-Modes.md)
- [GitHub Issues](https://github.com/ssahani/h2kvm/issues)

