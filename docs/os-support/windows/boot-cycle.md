
# Windows Boot Cycle (hyper2kvm) ➡➡


## Table of Contents

- [Prerequisites](#prerequisites)
- [Why Windows fails after hypervisor migration](#why-windows-fails-after-hypervisor-migration)
- [The Windows Boot Cycle (2-Phase)](#the-windows-boot-cycle-2-phase)
- [Phase A: Offline Fix + Bootstrap Boot (SATA)](#phase-a-offline-fix-bootstrap-boot-sata)
  - [Goals](#goals)
  - [What we do offline](#what-we-do-offline)
    - [1) Discover Windows layout](#1-discover-windows-layout)
    - [2) Prepare VirtIO driver plan (data-driven)](#2-prepare-virtio-driver-plan-data-driven)
    - [3) Inject storage driver (the sacred step)](#3-inject-storage-driver-the-sacred-step)
    - [4) Populate CriticalDeviceDatabase](#4-populate-criticaldevicedatabase)
    - [5) Optional: Inject NetKVM (VirtIO network)](#5-optional-inject-netkvm-virtio-network)
    - [6) Optional: Network cleanup policies](#6-optional-network-cleanup-policies)
    - [7) BCD sanity checks + backups](#7-bcd-sanity-checks-backups)
  - [Why the bootstrap domain uses SATA / IDE](#why-the-bootstrap-domain-uses-sata-ide)
- [Phase B: Finalize Boot (VirtIO)](#phase-b-finalize-boot-virtio)
  - [Mermaid: Bootstrap → Final switch](#mermaid-bootstrap-final-switch)
- [Appendix: Minimal “Decision Rules”](#appendix-minimal-decision-rules)
- [Debugging Examples](#debugging-examples)
  - [Example 1: Check Boot Configuration](#example-1-check-boot-configuration)
  - [Example 2: Verify VirtIO Drivers](#example-2-verify-virtio-drivers)
  - [Example 3: Test Boot with QEMU](#example-3-test-boot-with-qemu)
  - [Example 4: Check Registry for VirtIO](#example-4-check-registry-for-virtio)
- [Next Steps](#next-steps)
- [Getting Help](#getting-help)

---

## Prerequisites

For Windows VM migration, you need:

- ✓ hyper2kvm installed ([Installation Guide](02-Installation.md))
- ✓ VirtIO drivers ISO downloaded
- ✓ Windows source VM disk (VMDK, VHD, etc.)
- ✓ Understanding of [Windows Boot Cycle](11-Windows-Boot-Cycle.md)

This document explains **how hyper2kvm makes Windows reliably boot on KVM/QEMU** after coming from *any* hypervisor (VMware, Hyper-V, cloud images, raw disks).

The core idea is simple:

> **Windows storage must be BOOT_START before the first KVM boot.**
> Network can wait. Storage cannot.

We implement a **two-phase boot cycle** to avoid the classic failure mode:

*  `INACCESSIBLE_BOOT_DEVICE` BSOD (VirtIO storage not ready at boot)

Instead we do:

*  Phase A: **Bootstrap** with SATA/IDE (safe, almost always boots)
*  Phase B: **Finalize** with VirtIO (fast, correct, production)

---

## Why Windows fails after hypervisor migration

Windows ties boot to:

* storage controller type (IDE / SATA / SCSI / VirtIO / NVMe)
* boot-critical driver startup type (**BOOT_START**)
* `CriticalDeviceDatabase` mappings (PNP IDs → service)
* BCD entries + firmware mode (BIOS vs UEFI)

When you change hypervisors, you change:

* controllers
* PNP IDs
* device paths
* sometimes firmware assumptions

So Windows boots fine on VMware… then faceplants on VirtIO.

---

## The Windows Boot Cycle (2-Phase)


```mermaid
flowchart TB
  A["Input Disks + Metadata<br/>(VMware / Hyper-V / Cloud / Raw)"]
    --> B["INSPECT Windows<br/>Detect firmware, boot disk, OS build"]

  B --> C["PLAN Fix<br/>Pick drivers + bootstrap strategy"]
  C --> D["OFFLINE FIX (GuestFS)<br/>Mount volumes, load hives"]

  D --> E["Inject VirtIO STORAGE<br/>Set BOOT_START"]
  E --> F["CriticalDeviceDatabase<br/>PNP ID → service"]

  F --> G["Optional: Inject NetKVM"]
  G --> H["Optional: Network cleanup"]

  H --> I["BCD sanity checks<br/>Backup before changes"]

  I --> J["Bootstrap Domain XML<br/>SATA/IDE + VirtIO ISO"]
  J --> K["First KVM Boot<br/>Hardware enumeration"]

  K --> L["Final Domain XML<br/>VirtIO disk + NIC"]
  L --> M["Second Boot<br/>Production profile"]

  M --> N["VALIDATE<br/>Smoke tests + logs"]
````

---

## Phase A: Offline Fix + Bootstrap Boot (SATA)

### Goals

* Guarantee Windows can boot once under KVM
* Ensure VirtIO **storage** driver is BOOT_START-capable
* Keep all changes reversible and logged

---

### What we do offline

#### 1) Discover Windows layout

We locate (best effort):

* `WindowsRoot` (usually `C:\Windows`)
* system directory (usually `C:\Windows\System32`)
* registry hives:

  * `SYSTEM`
  * `SOFTWARE`
  * optional `BCD` (UEFI: `\EFI\Microsoft\Boot\BCD`)

---

#### 2) Prepare VirtIO driver plan (data-driven)

Drivers are selected using **JSON/YAML**, based on:

* Windows build bucket
* architecture (x64)
* target devices (storage first, network second)

This lets you:

* add vendors with custom PNP IDs
* update OS mappings without code changes
* support future Windows releases safely

---

#### 3) Inject storage driver (the sacred step)

We stage VirtIO storage drivers and ensure:

* service exists (`viostor` or `vioscsi`)
* startup type = **BOOT_START**
* required registry keys exist
* optional `Group` / `Tag` set correctly

This single step prevents:

*  `INACCESSIBLE_BOOT_DEVICE`

---

#### 4) Populate CriticalDeviceDatabase

We map PNP IDs like:

```bash
PCI\VEN_1AF4&DEV_1001
```bash

to the correct storage service so Windows binds the driver **early in boot**.

---

#### 5) Optional: Inject NetKVM (VirtIO network)

Network drivers are:

* injected offline (recommended)
* usually SYSTEM_START (safe)

This ensures the **second boot** has working networking.

---

#### 6) Optional: Network cleanup policies

Windows often carries:

* ghost NICs
* stale MAC-bound profiles
* static IPs tied to removed adapters

hyper2kvm applies **safe, explicit policies only**:

* remove stale adapter references
* preserve static IP if safely discoverable
* provide DHCP fallback if binding is unsafe
* avoid “new network every boot” loops

---

#### 7) BCD sanity checks + backups

We **do not blindly rewrite BCD**.

We:

* detect firmware mode (BIOS vs UEFI)
* verify boot partition layout
* back up BCD before touching it
* repair only when clearly broken

---

### Why the bootstrap domain uses SATA / IDE

Even with perfect driver injection, Windows benefits from one boot where it:

* enumerates new chipset devices
* finalizes driver installs
* stabilizes services

So the bootstrap domain uses:

* disk via **SATA or IDE**
* VirtIO driver ISO attached
* conservative machine profile

---

## Phase B: Finalize Boot (VirtIO)

After first boot succeeds:

* disk bus → **VirtIO**
* NIC model → **VirtIO**
* remove bootstrap-only devices
* keep firmware mode unchanged

This is the **production domain**.

---

### Mermaid: Bootstrap → Final switch

```mermaid
sequenceDiagram
  participant H as hyper2kvm
  participant O as Offline Fix (GuestFS)
  participant B as Bootstrap Domain
  participant W as Windows (1st boot)
  participant F as Final Domain
  participant W2 as Windows (2nd boot)

  H->>O: Inspect + plan + decide firmware
  O->>O: Inject BOOT_START storage
  O->>O: Add CriticalDeviceDatabase mappings
  O->>O: Optional NetKVM + network cleanup
  O->>H: Emit bootstrap + final domain XML

  H->>B: Boot with SATA + VirtIO ISO
  B->>W: First boot, hardware settle
  W-->>B: Desktop reachable

  H->>F: Switch disk + NIC to VirtIO
  F->>W2: Second boot
  W2-->>F: Stable system + network
```bash

---

## Appendix: Minimal “Decision Rules”

```mermaid
flowchart TD
  S["Start"] --> D{"Windows detected?"}

  D -- "No" --> L["Use Linux pipeline"]
  D -- "Yes" --> F{"Firmware?"}

  F -- "UEFI" --> U["Preserve UEFI<br/>OVMF + NVRAM"]
  F -- "BIOS" --> B["Preserve BIOS<br/>SeaBIOS"]

  U --> P["Pick storage plan"]
  B --> P

  P --> V{"VirtIO boot-ready?"}
  V -- "Yes" --> Q["Bootstrap optional<br/>(still recommended)"]
  V -- "No" --> I["Inject BOOT_START storage + CDD"]

  I --> Z["Bootstrap SATA domain"]
  Q --> Z
  Z --> Y["Final VirtIO domain"]
```bash

## Debugging Examples

### Example 1: Check Boot Configuration

```bash
# Mount Windows disk and inspect boot config
sudo guestfish -a windows.qcow2 -i

# Inside guestfish
><fs> cat /Windows/System32/config/BCD-Template
><fs> ls /Windows/System32/drivers
><fs> cat /Windows/INF/setupapi.dev.log
```

### Example 2: Verify VirtIO Drivers

```bash
# Check if VirtIO drivers are present
sudo virt-ls -a windows.qcow2 /Windows/System32/drivers/ | grep virtio

# Expected output:
# viostor.sys
# netkvm.sys
# vioscsi.sys
```

### Example 3: Test Boot with QEMU

```bash
# Test Windows boot with serial console
qemu-system-x86_64 \
  -m 4096 \
  -smp 2 \
  -drive file=windows.qcow2,if=virtio \
  -net nic,model=virtio \
  -net user \
  -enable-kvm \
  -nographic \
  -serial mon:stdio
```

### Example 4: Check Registry for VirtIO

```bash
# Use virt-win-reg to inspect registry
virt-win-reg --unsafe-printable-strings windows.qcow2 \
  'HKLM\SYSTEM\CurrentControlSet\Control\CriticalDeviceDatabase' \
  | grep -i virtio
```


## Next Steps

For Windows migrations:

- **[Windows Boot Cycle](11-Windows-Boot-Cycle.md)** - Understanding Windows boot process
- **[Windows Troubleshooting](12-Windows-Troubleshooting.md)** - Common Windows issues
- **[Windows Networking](13-Windows-Networking.md)** - Network and driver configuration

## Getting Help

- [Troubleshooting Guide](90-Failure-Modes.md)
- [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)

