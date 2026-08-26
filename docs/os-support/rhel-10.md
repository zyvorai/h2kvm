  # Testing Converted RHEL 10 qcow2 on Fedora (GUI, UEFI)


## Table of Contents

- [Prerequisites](#prerequisites)
- [Host Requirements (Fedora)](#host-requirements-fedora)
- [Image Under Test](#image-under-test)
- [Why UEFI Needs a VARS Template (and Why Libvirt Yells)](#why-uefi-needs-a-vars-template-and-why-libvirt-yells)
- [Put the qcow2 Where Libvirt Can Read It (Avoid Permission/SELinux Traps)](#put-the-qcow2-where-libvirt-can-read-it-avoid-permissionselinux-traps)
- [UEFI + GUI libvirt XML (Known-Good)](#uefi-gui-libvirt-xml-known-good)
- [Define and Start the VM](#define-and-start-the-vm)
- [Connect to the GUI](#connect-to-the-gui)
  - [Option 1: virt-viewer (recommended)](#option-1-virt-viewer-recommended)
  - [Option 2: SPICE display address](#option-2-spice-display-address)
- [Expected Boot Sequence](#expected-boot-sequence)
- [Troubleshooting](#troubleshooting)
  - [“unable to find any master var store … OVMF_CODE.fd”](#unable-to-find-any-master-var-store-ovmf_codefd)
  - [Permission denied reading qcow2](#permission-denied-reading-qcow2)
  - [Black screen after GRUB](#black-screen-after-grub)
  - [“No bootable device” / drops to UEFI shell](#no-bootable-device-drops-to-uefi-shell)
  - [Boot logs needed (no GUI)](#boot-logs-needed-no-gui)
- [Notes](#notes)
- [Next Steps](#next-steps)
- [Related Documentation](#related-documentation)

---

## Prerequisites

Before migrating this platform, ensure:

- ✓ hyper2kvm installed ([Installation Guide](02-Installation.md))
- ✓ Familiarity with [Quick Start Guide](03-Quick-Start.md)
- ✓ Root/sudo access
- ✓ Source VM accessible

This guide describes how to **validate a converted RHEL 10 qcow2 image**
using **KVM + libvirt** on Fedora, booting **directly into graphical (GUI) mode**
with **UEFI (OVMF)**.

This is intended as a **post-conversion smoke test** after migrating
a VMware VMDK to qcow2 and applying offline fixes (fstab, GRUB/BLS, initramfs, etc.).

---

## Host Requirements (Fedora)

Install required virtualization tools:

```bash
sudo dnf install -y \
  libvirt \
  qemu-kvm \
  qemu-img \
  virt-viewer \
  edk2-ovmf
```

Enable libvirt and ensure the default network is active:

```bash
sudo systemctl enable --now libvirtd
sudo virsh net-start default 2>/dev/null || true
```

---

## Image Under Test

```
/home/ssahani/by-path/out/rhel10-fixed.qcow2
```

**Assumptions:**

* Converted from VMware VMDK
* UEFI guest (OVMF)
* RHEL 10 (or RHEL-like) with GRUB2 + BLS

---

## Why UEFI Needs a VARS Template (and Why Libvirt Yells)

UEFI guests use **two firmware blobs**:

* `OVMF_CODE.fd` (read-only firmware code)
* `OVMF_VARS.fd` (mutable per-VM NVRAM “vars store”)

Libvirt must know a **master VARS template** so it can create a per-VM NVRAM file.
On your host, the available firmware pairs are:

* `/usr/share/edk2/ovmf/OVMF_CODE.fd`
* `/usr/share/edk2/ovmf/OVMF_VARS.fd`
* (secureboot variants also exist, but we use non-secureboot by default)

---

## Put the qcow2 Where Libvirt Can Read It (Avoid Permission/SELinux Traps)

Copy the image into the standard libvirt images directory:

```bash
sudo install -o qemu -g qemu -m 0640 \
  /home/ssahani/by-path/out/rhel10-fixed.qcow2 \
  /var/lib/libvirt/images/rhel10-fixed.qcow2
```
or 
```bash
sudo cp /home/ssahani/by-path/out/rhel10-fixed.qcow2 \
  /var/lib/libvirt/images/

sudo chown qemu:qemu /var/lib/libvirt/images/rhel10-fixed.qcow2

```
Create the NVRAM directory (safe even if it already exists):

```bash
sudo mkdir -p /var/lib/libvirt/qemu/nvram
```

---

## UEFI + GUI libvirt XML (Known-Good)

This XML is a conservative, reliable UEFI configuration:

* q35 machine
* OVMF UEFI firmware
* Explicit VARS template (prevents “master var store” errors)
* Virtio disk + network
* SPICE graphics + virtio video
* Serial console
* Virtio RNG (helps entropy-starved boots)

```bash
cat >/tmp/rhel10-uefi-gui.xml <<'EOF'
<domain type='kvm'>
  <name>rhel10-fixed-uefi-gui</name>

  <memory unit='MiB'>4096</memory>
  <currentMemory unit='MiB'>4096</currentMemory>
  <vcpu placement='static'>2</vcpu>

  <os>
    <type arch='x86_64' machine='q35'>hvm</type>

    <!-- UEFI firmware (non-secureboot) -->
    <loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>

    <!-- Per-VM NVRAM file, copied from template on first boot -->
    <nvram template='/usr/share/edk2/ovmf/OVMF_VARS.fd'>/var/lib/libvirt/qemu/nvram/rhel10-fixed-uefi-gui_VARS.fd</nvram>

    <!-- Optional: enable temporarily for deep boot debugging -->
    <!-- <cmdline>rd.debug rd.shell loglevel=7 systemd.log_level=debug systemd.log_target=console</cmdline> -->
  </os>

  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>

  <cpu mode='host-passthrough' check='none'/>

  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>

  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>

  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <!-- USB controller (tablet input) -->
    <controller type='usb' index='0' model='qemu-xhci'/>

    <!-- Root disk -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none' io='native' discard='unmap'/>
      <source file='/var/lib/libvirt/images/rhel10-fixed.qcow2'/>
      <target dev='vda' bus='virtio'/>
      <boot order='1'/>
    </disk>

    <!-- Network -->
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>

    <!-- Serial console -->
    <serial type='pty'>
      <target port='0'/>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>

    <!-- Guest agent channel (install qemu-guest-agent inside guest) -->
    <channel type='unix'>
      <source mode='bind'/>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>

    <!-- Graphics: SPICE + virtio GPU -->
    <graphics type='spice' autoport='yes' listen='127.0.0.1'/>
    <video>
      <model type='virtio' heads='1'/>
    </video>

    <input type='tablet' bus='usb'/>

    <!-- RNG helps early boot -->
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>

    <memballoon model='virtio'/>
  </devices>
</domain>
EOF
```

---

## Define and Start the VM

If a domain with the same name already exists, remove it first:

```bash
sudo virsh destroy rhel10-fixed-uefi-gui 2>/dev/null || true
sudo virsh undefine rhel10-fixed-uefi-gui --nvram 2>/dev/null || sudo virsh undefine rhel10-fixed-uefi-gui 2>/dev/null || true
```

Define and start the VM:

```bash
sudo virsh define /tmp/rhel10-uefi-gui.xml
sudo virsh start rhel10-fixed-uefi-gui
```

---

## Connect to the GUI

### Option 1: virt-viewer (recommended)

```bash
virt-viewer rhel10-fixed-uefi-gui
```

### Option 2: SPICE display address

```bash
sudo virsh domdisplay rhel10-fixed-uefi-gui
```

---

## Expected Boot Sequence

A successful boot should show:

1. OVMF splash (or quick handoff)
2. GRUB menu
3. RHEL kernel + initramfs (dracut)
4. Graphical login screen (gdm)

If this sequence completes, the image is **boot-validated**.

---

## Troubleshooting

### “unable to find any master var store … OVMF_CODE.fd”

Your XML is missing the VARS template link. Confirm these lines exist:

```xml
<loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>
<nvram template='/usr/share/edk2/ovmf/OVMF_VARS.fd'>/var/lib/libvirt/qemu/nvram/NAME_VARS.fd</nvram>
```

### Permission denied reading qcow2

Keep the qcow2 under `/var/lib/libvirt/images/` with `qemu:qemu` ownership:

```bash
sudo chown qemu:qemu /var/lib/libvirt/images/rhel10-fixed.qcow2
sudo chmod 0640 /var/lib/libvirt/images/rhel10-fixed.qcow2
```

### Black screen after GRUB

Try a simpler video model:

```xml
<video><model type='qxl'/></video>
```

or even:

```xml
<video><model type='vga'/></video>
```

### “No bootable device” / drops to UEFI shell

Usually the EFI boot entry/NVRAM is missing or wrong. Two common fixes:

1) Ensure you’re using UEFI (OVMF) and the guest actually has an EFI System Partition.
2) From the guest’s GRUB, confirm BLS/root is correct and regenerate if needed.

### Boot logs needed (no GUI)

Attach the serial console:

```bash
sudo virsh console rhel10-fixed-uefi-gui
```

Optionally enable debug kernel args in the XML `<cmdline>` (commented in the XML).

---

## Notes

* This test uses **UEFI + OVMF** (not SeaBIOS)
* Explicit VARS template avoids the classic libvirt “master var store” failure
* Designed for VMware → KVM migrations where you want a quick, repeatable smoke test

---

**Status:**  Verified working for RHEL 10 qcow2 (UEFI, GUI)

## Next Steps

After migrating this platform:

- **[Test your VM](../examples/README.md)** - Validation examples
- **[Troubleshooting](90-Failure-Modes.md)** - Common issues
- **[Cookbook](06-Cookbook.md)** - More migration scenarios

## Related Documentation

- [Quick Start](03-Quick-Start.md)
- [CLI Reference](04-CLI-Reference.md)
- [Architecture](01-Architecture.md)

