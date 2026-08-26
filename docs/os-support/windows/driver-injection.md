# Windows VirtIO Driver Injection Guide

This document explains how h2kvm injects VirtIO drivers into Windows VMs during VMware to KVM migration.

## Overview

h2kvm uses a **multi-stage offline injection** approach:

1. **Offline pre-staging** — Copy driver files + register in DriverStore before first KVM boot
2. **Bootstrap boot** — Boot with SATA disk + VirtIO NIC/balloon/serial + VirtIO ISO
3. **Runtime install** — RunOnce batch file runs `pnputil` to properly bind drivers
4. **Verification** — Offline NBD check confirms all drivers present
5. **Final VM** — Production VM with all VirtIO devices working

## Supported Windows Versions

| Version | Status | Notes |
|---------|--------|-------|
| Windows 10 | Fully automatic | Guest agent responds, all drivers install |
| Windows 11 | One-click OOBE | "I don't have internet" → auto-install after login |
| Server 2019 | Supported | Uses w10 driver folder |
| Server 2022 | Supported | Uses w11 driver folder (build >= 22000) |
| Windows 7/8 | Supported | Uses w7/w8 driver folders |

## VirtIO ISO: Auto-Discovery

The VirtIO drivers ISO is **automatically discovered** at the standard path:

```
/var/lib/h2kvm/virtio-win.iso
```

To download it, run once:

```bash
sudo ./scripts/install-deps.sh --virtio-win
```

After that, no `--virtio-drivers-dir` flag or `virtio_drivers_dir` YAML key is needed -- h2kvm finds the ISO automatically. Use `--virtio-drivers-dir` only if you need to override with a custom path.

## Quick Start

### YAML Configuration

```yaml
cmd: local
vmdk: /path/to/windows.vmdk
output_dir: /path/to/output
to_output: /path/to/output/windows.qcow2
out_format: qcow2

# Windows settings
windows: true
guest_os: windows
vm_name: my-windows-vm

# VirtIO ISO -- optional if ISO is at /var/lib/h2kvm/virtio-win.iso (auto-discovered)
# virtio_drivers_dir: /custom/path/to/virtio-win.iso

# Enable multi-stage boot deployment
virtio_deploy_boot: true
virtio_deploy_timeout: 300

# UEFI boot
uefi: true
```

### CLI

```bash
# Ensure the VirtIO ISO is available (one-time setup):
sudo ./scripts/install-deps.sh --virtio-win

# Run migration (ISO auto-discovered at standard path):
sudo ./h2kvmctl --config my-config.yaml
```

## How It Works

### Stage 1 — Offline Injection (`VirtIOOfflineInjector`)

Before any boot, the injector mounts the QCOW2 via NBD and:

1. **Detects OS version** from offline registry (ProductName + CurrentBuild)
2. **Resolves driver folder** (w10, w11, 2k19, etc.) — build >= 22000 maps to w11
3. **Copies .sys files** to `Windows\System32\drivers\`
4. **Stages to DriverStore** with proper hash naming (`netkvm.inf_amd64_<md5hash>`)
5. **Registers OEM INF** in `Windows\INF\oem<N>.inf`
6. **Disables VMware services** (VMTools, vm3dservice, VGAuthService, etc.)
7. **Enables auto-logon** for RunOnce to fire without manual login
8. **Sets OOBE bypass** (Win11: BypassNRO, SkipMachineOOBE, ImageState)
9. **Stages RunOnce batch file** for pnputil driver installation
10. **Injects Unattend.xml** to handle OOBE region/network/account screens

### Stage 2 — Bootstrap Boot

The VM boots with:
- **SATA disk** (safe — no VirtIO storage driver needed)
- **VirtIO NIC** (triggers netkvm driver discovery)
- **VirtIO balloon** (triggers balloon driver)
- **VirtIO serial + guest agent channel**
- **VirtIO ISO attached as CD-ROM**

Windows auto-logs in → RunOnce fires → pnputil installs all matching drivers from the ISO.

### Stage 3 — Guest Agent Wait

The deployer polls `virsh qemu-agent-command` for up to 300s (configurable).
When the guest agent responds, all VirtIO drivers are confirmed installed.

### Stage 4 — Shutdown + Verification

After shutdown, the QCOW2 is mounted via NBD and checked for:
- `viostor.sys`
- `netkvm.sys`
- `vioser.sys`
- `balloon.sys`
- `viorng.sys`

### Stage 5 — Final VM

A production VM is created with all VirtIO devices. The VirtIO ISO remains
attached so Windows can find drivers if needed during OOBE.

## Drivers Injected

| Driver | File | Purpose | Start Type |
|--------|------|---------|------------|
| viostor | viostor.sys | VirtIO block storage | Demand (3) |
| netkvm | netkvm.sys | VirtIO network | Auto (2) |
| balloon | balloon.sys | Memory ballooning | Demand (3) |
| vioserial | vioser.sys | Serial/guest agent | Demand (3) |
| viorng | viorng.sys | Random number generator | Demand (3) |

## OS Detection

The injector reads the SOFTWARE registry hive offline:

```
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProductName
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\CurrentBuild
```

Build-based detection (handles Win11 reporting as "Windows 10"):
- Build >= 22000 → `w11` folder
- "Windows 10" in ProductName → `w10` folder
- "Server 2022" → `2k22` folder
- etc.

## Win11 OOBE Handling

Win11 enforces network during OOBE. h2kvm handles this with:

1. **BypassNRO** registry key — adds "I don't have internet" option
2. **SkipMachineOOBE + SkipUserOOBE** — prevents dynamic update loop
3. **ImageState = IMAGE_STATE_COMPLETE** — marks setup as complete
4. **Unattend.xml** — auto-configures region, hides network/account screens

After OOBE completes (one click on "I don't have internet"), the user logs in
and RunOnce installs all drivers automatically.

## CLI Arguments

| Argument | Description |
|----------|-------------|
| `--virtio-deploy-boot` | Enable multi-stage VirtIO boot deployment |
| `--virtio-deploy-timeout N` | Guest agent wait timeout in seconds (default: 180) |
| `--no-virtio-deploy-start-final` | Don't auto-start the final VM |
| `--virtio-drivers-dir PATH` | Path to VirtIO ISO file (override; auto-discovered at `/var/lib/h2kvm/virtio-win.iso`) |

## Verification

### Check Drivers After Migration

```bash
# Mount QCOW2 and verify
sudo qemu-nbd --connect /dev/nbd0 windows.qcow2
sudo ntfs-3g -o ro /dev/nbd0p3 /tmp/check
ls /tmp/check/Windows/System32/drivers/{viostor,netkvm,balloon,vioser,viorng}.sys
sudo umount /tmp/check
sudo qemu-nbd --disconnect /dev/nbd0
```

### Check VM State

```bash
virsh domstate my-windows-vm
virsh qemu-agent-command my-windows-vm '{"execute":"guest-ping"}'
```

## Troubleshooting

### BSOD: INACCESSIBLE_BOOT_DEVICE

**Cause**: viostor registered as Start=0 (boot-critical) while disk is on SATA.

**Fix**: Don't use `migration_mode=True` during bootstrap. The staged boot uses SATA disk.

### Win11 OOBE "Install driver" Screen

**Cause**: Win11 OOBE doesn't auto-scan CD for NIC drivers.

**Fix**: Click "I don't have internet" → complete OOBE → RunOnce installs drivers after login.

### Guest Agent Not Responding

**Cause**: Win11 OOBE blocks before user login, preventing RunOnce from firing.

**Fix**: Increase `--virtio-deploy-timeout` or accept that Win11 guest agent may not respond during bootstrap (drivers still install).

### VMware Services Causing Errors

**Cause**: VMware Tools services crash without VMware hardware.

**Fix**: The injector automatically disables VMware services in the SYSTEM hive.

## Architecture

```
VirtIOOfflineInjector          VirtioStagedDeployer
┌─────────────────────┐        ┌──────────────────────┐
│ Mount QCOW2 (NBD)   │        │ Stage 1: Bootstrap   │
│ Detect OS version    │        │   SATA + VirtIO NIC  │
│ Copy .sys files      │───────>│ Stage 2: Wait agent  │
│ Stage DriverStore    │        │ Stage 3: Verify      │
│ Disable VMware       │        │ Stage 4: Final VM    │
│ Set OOBE bypass      │        └──────────────────────┘
│ Inject Unattend.xml  │
│ Stage RunOnce batch  │
└─────────────────────┘
```

## References

- [VirtIO Drivers](https://fedorapeople.org/groups/virt/virtio-win/)
- [Windows PnP Documentation](https://docs.microsoft.com/en-us/windows-hardware/drivers/install/)
- [pnputil](https://docs.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil)
