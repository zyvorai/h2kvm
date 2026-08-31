# Migrating LUKS-Encrypted Disks

Guide for migrating VMs with LUKS-encrypted root filesystems from VMware to KVM.

## How It Works

When h2kvm detects a LUKS-encrypted partition on the guest disk, it automatically:

1. **Switches to libguestfs backend** — boots a supermin appliance VM with full device visibility
2. **Unlocks the LUKS partition** — `g.cryptsetup_open()` inside the appliance
3. **Activates LVM** — `g.lvm_scan(True)` discovers volumes inside LUKS
4. **Fixes fstab, network, grub** — same as non-encrypted disks
5. **Preserves the existing initramfs** — does NOT rebuild it (same as virt-v2v)
6. **Writes virtio driver configs** — `/etc/dracut.conf.d/` or `/etc/initramfs-tools/`

The VM boots and **prompts for the LUKS passphrase** at console — exactly like the original VM.

## Quick Start

```bash
# Passphrase-based LUKS disk
sudo h2kvmctl --cmd local \
  --vmdk /path/to/encrypted-vm.vmdk \
  --luks-enable --luks-passphrase "your-passphrase" \
  --flatten --regen-initramfs \
  --emit-domain-xml --virsh-define \
  --vm-name my-luks-vm \
  -o /output

# Passphrase from environment variable
export H2KVM_LUKS_PASSPHRASE="your-passphrase"
sudo h2kvmctl --cmd local --vmdk disk.vmdk --luks-enable ...

# Passphrase from keyfile
sudo h2kvmctl --cmd local --vmdk disk.vmdk \
  --luks-enable --luks-keyfile /path/to/keyfile ...
```

## YAML Configuration

```yaml
cmd: local
vmdk: /path/to/encrypted-vm.vmdk
output_dir: ./output
flatten: true
regen_initramfs: true

# LUKS configuration
luks_enable: true
luks_passphrase: "your-passphrase"
# Or: luks_keyfile: /path/to/keyfile
# Or: luks_passphrase_env: MY_LUKS_PASS

# Libvirt
emit_domain_xml: true
virsh_define: true
vm_name: my-luks-vm
```

## What Happens During Migration

```
VMDK → flatten → qcow2
  ↓
Quick probe: detected LUKS on disk
  ↓
Auto-switched to libguestfs backend (supermin appliance)
  ↓
g.cryptsetup_open(/dev/sda3, passphrase, "h2kvm-crypt1")
  ↓
g.lvm_scan(True) → discovers LVM inside LUKS
  ↓
Mount decrypted root → fix fstab, network, grub
  ↓
Skip initramfs rebuild (preserve existing LUKS boot config)
  ↓
Write virtio driver configs → /etc/dracut.conf.d/
  ↓
qcow2 compress → libvirt define+start
  ↓
VM boots → "Please unlock disk dm_crypt-0:" → enter passphrase → login
```

## Why initramfs Is NOT Rebuilt

This matches virt-v2v behavior. The guest's existing initramfs already contains:
- `cryptsetup` for LUKS unlock
- Correct LUKS UUID references from `/etc/crypttab`
- Correct `root=UUID=...` in kernel cmdline

Rebuilding inside libguestfs would break these references because the device
mapper paths (`/dev/mapper/h2kvm-crypt1`) differ from what the guest expects
(`dm-uuid-CRYPT-LUKS-<uuid>-<name>`).

Virtio driver configs are written to disk but only take effect after the user
rebuilds initramfs inside the booted VM:

```bash
# After first boot (inside the VM):
sudo update-initramfs -u    # Ubuntu/Debian
sudo dracut -f              # RHEL/Fedora
```

## TPM-Sealed LUKS (Pre-Migration Preparation)

If the LUKS volume is sealed to a VMware vTPM, the KVM vTPM will have different
seeds and auto-unlock will fail. You must prepare the disk **before** migration:

```bash
# On the source VM (before migration):

# 1. Find the TPM binding
sudo clevis luks list -d /dev/sda3

# 2. Recover the passphrase (if TPM-only)
sudo clevis luks pass -d /dev/sda3

# 3. Add a passphrase keyslot
sudo cryptsetup luksAddKey /dev/sda3

# 4. Remove the TPM binding
sudo clevis luks unbind -d /dev/sda3 -s 1
# Or: sudo systemd-cryptenroll --wipe-slot=tpm2 /dev/sda3
```

After migration, re-bind to the KVM vTPM:

```bash
# On the migrated VM (after boot with passphrase):
sudo clevis luks bind -d /dev/sda3 tpm2 '{}'
# Or: sudo systemd-cryptenroll --tpm2-device=auto /dev/sda3
```

## Prerequisites

```bash
# Required: libguestfs with Python bindings
sudo dnf install libguestfs-tools python3-libguestfs    # Fedora/RHEL
sudo apt install libguestfs-tools python3-guestfs       # Ubuntu/Debian
```

libguestfs is auto-detected. If not installed, h2kvm falls back to GuestKit
with host-based `cryptsetup` (works but less robust).

## Tested Configurations

| Guest OS | Encryption | LVM | Boot | Result |
|----------|-----------|-----|------|--------|
| Ubuntu 22.04.5 | LUKS2 + LVM | ubuntu-vg/ubuntu-lv | UEFI | Passphrase prompt → login |
| RHEL 8.8 | No LUKS, LVM only | rhel/root | BIOS | Direct boot → GDM |
| CentOS Stream 9 | No LUKS, LVM only | cs/root | BIOS | Direct boot → console |

## Troubleshooting

### "No valid partition devices found"
- Ensure `--luks-passphrase` is correct
- Check: `sudo cryptsetup luksDump /dev/sda3` on the source disk

### VM drops to initramfs shell
- The initramfs was rebuilt by mistake — it has wrong LUKS UUIDs
- Fix: boot from original initramfs, or rebuild inside the VM

### "libguestfs not available"
- Install: `sudo dnf install python3-libguestfs`
- Without it, LUKS unlock uses host `cryptsetup` (less reliable)

### TPM auto-unlock fails after migration
- Expected — KVM vTPM has different seeds than VMware vTPM
- Solution: add passphrase keyslot before migration (see TPM section above)
```
