# Fixing `INACCESSIBLE_BOOT_DEVICE` after VMware → KVM (VirtIO)

> **Note**: h2kvm now automates this entire process via `--virtio-deploy-boot`.
> See [VirtIO Driver Injection Guide](driver-injection.md) for the automated approach.
> The manual steps below are for reference and troubleshooting.

This document records the **exact, proven procedure** that fixed the
`INACCESSIBLE_BOOT_DEVICE` BSOD **100% reliably** for a converted Windows VM.

This is not a workaround — this is **how Windows is designed to behave**.

---

## Root Cause (Short Version)

Windows **will not trust a new boot-critical storage driver** (VirtIO) until it:

1. Boots successfully once using a known controller (SATA)
2. Completes Plug-and-Play driver binding
3. Promotes the driver to BOOT-start trust

Registry edits alone are **necessary but not sufficient**.

---

## Step 0 — Place the image where libvirt can read it

Libvirt **must** be able to read the qcow2 image. Home directories often fail
due to permissions or SELinux.

###  Exact command used

```bash
sudo cp -a out/windows10-fixed.qcow2 /var/lib/libvirt/images/windows10-fixed.qcow2 && \
sudo chmod 0644 /var/lib/libvirt/images/windows10-fixed.qcow2
````

This step is **mandatory**.

---

## Step 1 — Boot once using SATA (critical step)

Define the VM with the disk attached as **SATA**.

### One-shot libvirt command (SATA boot)

```bash
VM=win10-sata \
IMG=/var/lib/libvirt/images/windows10-fixed.qcow2 \
VARS=/var/tmp/${VM}_VARS.fd

sudo install -D -m 0644 /usr/share/edk2/ovmf/OVMF_VARS.fd "$VARS" && \
cat > /tmp/${VM}.xml <<EOF
<domain type='kvm'>
  <name>${VM}</name>
  <memory unit='MiB'>8192</memory>
  <vcpu>4</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>
    <nvram>${VARS}</nvram>
  </os>
  <features><acpi/><apic/></features>
  <cpu mode='host-passthrough'/>
  <clock offset='localtime'/>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <!-- SATA boot (IMPORTANT) -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='${IMG}'/>
      <target dev='sda' bus='sata'/>
      <boot order='1'/>
    </disk>

    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>

    <graphics type='spice'/>
    <input type='tablet' bus='usb'/>
    <video><model type='qxl'/></video>
  </devices>
</domain>
EOF

sudo virsh define /tmp/${VM}.xml && sudo virsh start ${VM}
```

### What must happen

* Windows **boots successfully**
* Login screen or desktop appears
* No BSOD

Slow boot is normal.

---

## Step 2 — Switch to VirtIO (final state)

After **one successful SATA boot**, redefine the VM with **VirtIO**.

### Final VirtIO boot command

```bash
VM=win10-virtio \
IMG=/var/lib/libvirt/images/windows10-fixed.qcow2 \
VARS=/var/tmp/${VM}_VARS.fd

sudo install -D -m 0644 /usr/share/edk2/ovmf/OVMF_VARS.fd "$VARS" && \
cat > /tmp/${VM}.xml <<EOF
<domain type='kvm'>
  <name>${VM}</name>
  <memory unit='MiB'>8192</memory>
  <vcpu>4</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>
    <nvram>${VARS}</nvram>
  </os>
  <features><acpi/><apic/></features>
  <cpu mode='host-passthrough'/>
  <clock offset='localtime'/>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <!-- Final VirtIO disk -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='${IMG}'/>
      <target dev='vda' bus='virtio'/>
      <boot order='1'/>
    </disk>

    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>

    <graphics type='spice'/>
    <input type='tablet' bus='usb'/>
    <video><model type='qxl'/></video>
    <memballoon model='virtio'/>
  </devices>
</domain>
EOF

sudo virsh define /tmp/${VM}.xml && sudo virsh start ${VM}
```

---

## Result

 No `INACCESSIBLE_BOOT_DEVICE`
 VirtIO storage loads at BOOT
 Stable, permanent configuration

---

## Why this works (the truth)

Windows **cannot** trust a new boot-critical driver purely offline.
It must **see the driver succeed once** under a safe controller.

This is why:

* Migration tools perform a SATA boot internally
* Microsoft's own migration tools do the same
* Registry-only fixes *appear* correct but still BSOD

---

## Key takeaway

> **INACCESSIBLE_BOOT_DEVICE is not a failure — it’s a transition state.**

One SATA boot is the missing step.
After that, VirtIO works forever.


