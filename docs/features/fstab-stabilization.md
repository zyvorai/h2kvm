# Fstab Stabilization - UUID Conversion

## Overview

After migrating VMs from VMware/Hyper-V to KVM, some VMs may have fstab entries that reference devices using unstable identifiers like `/dev/disk/by-path/pci-*`. These identifiers are hardware-specific and will break when the VM is migrated to different hardware or when PCI addresses change in the virtualized environment.

This document describes the process of converting all fstab entries to use stable UUID identifiers.

## Problem Statement

### Unstable Device Identifiers

Some distributions (particularly openSUSE) use PCI-based device paths:
```
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2
```

These paths are problematic because:
- They are tied to specific PCI slot addresses
- They change when VM hardware configuration changes
- They break when migrating between hypervisors
- They fail in KVM when the virtual hardware layout differs from the source

### Stable Alternative: UUID

UUID (Universally Unique Identifier) provides a stable way to reference filesystems:
```
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85
```

Benefits:
- Unique to the filesystem, not the hardware
- Remains constant across migrations
- Works regardless of PCI addressing
- Standard practice for modern Linux systems

## Solution Approach

### Process

1. **Shutdown VMs**: Release disk locks
2. **Connect Disk via NBD**: Use qemu-nbd to access disk images offline
3. **Detect Partition Layout**: Handle GPT, MBR, LVM, and Btrfs subvolumes
4. **Extract UUIDs**: Use `blkid` to get filesystem UUIDs
5. **Update fstab**: Replace unstable identifiers with UUIDs
6. **Verify Boot**: Start VMs and confirm successful boot

### Tools Used

- `qemu-nbd`: Network Block Device for offline disk access
- `blkid`: UUID extraction
- `lvm2`: LVM volume group management
- `btrfs-progs`: Btrfs subvolume mounting

## VM-Specific Results

### 1. openSUSE Leap 15.4

**Status**: ✅ FIXED (11 entries converted)

**Original fstab** (by-path):
```
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /                       btrfs  defaults                      0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /var                    btrfs  subvol=/@/var                 0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /usr/local              btrfs  subvol=/@/usr/local           0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /tmp                    btrfs  subvol=/@/tmp                 0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /srv                    btrfs  subvol=/@/srv                 0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /root                   btrfs  subvol=/@/root                0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /opt                    btrfs  subvol=/@/opt                 0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /home                   btrfs  subvol=/@/home                0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /boot/grub2/x86_64-efi  btrfs  subvol=/@/boot/grub2/x86_64-efi  0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /boot/grub2/i386-pc     btrfs  subvol=/@/boot/grub2/i386-pc  0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /.snapshots             btrfs  subvol=/@/.snapshots          0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3  swap                    swap   defaults                      0  0
```

**Updated fstab** (UUID):
```
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /                       btrfs  defaults                      0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /var                    btrfs  subvol=/@/var                 0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /usr/local              btrfs  subvol=/@/usr/local           0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /tmp                    btrfs  subvol=/@/tmp                 0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /srv                    btrfs  subvol=/@/srv                 0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /root                   btrfs  subvol=/@/root                0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /opt                    btrfs  subvol=/@/opt                 0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /home                   btrfs  subvol=/@/home                0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /boot/grub2/x86_64-efi  btrfs  subvol=/@/boot/grub2/x86_64-efi  0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /boot/grub2/i386-pc     btrfs  subvol=/@/boot/grub2/i386-pc  0  0
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85  /.snapshots             btrfs  subvol=/@/.snapshots          0  0
UUID=03c038b5-fb29-470c-9f81-7100da936770  swap                    swap   defaults                      0  0
```

**Partition Layout**:
- `/dev/nbd14p1`: 8M BIOS boot partition
- `/dev/nbd14p2`: 510G Btrfs root (UUID: f293ef3c-255a-4582-8016-f72fb8dd3f85)
- `/dev/nbd14p3`: 2G swap (UUID: 03c038b5-fb29-470c-9f81-7100da936770)

**Boot Status**: ✅ Running successfully

---

### 2. Ubuntu 25 Server

**Status**: ✅ FIXED (1 entry converted)

**Original fstab** (dm-uuid):
```
# / was on /dev/ubuntu-vg/ubuntu-lv during curtin installation
/dev/disk/by-id/dm-uuid-LVM-TjdITyfq4bzjFZ72abuWRyAEBfhingPTcj6PMKRuLQ93CevoO4kJDDKVit8KAQbX / ext4 defaults 0 1
# /boot was on /dev/sda2 during curtin installation
/dev/disk/by-uuid/6f0d41a2-60a5-4400-bfb6-c384032694f9 /boot ext4 defaults 0 1
/swap.img	none	swap	sw	0	0
```

**Updated fstab** (UUID):
```
# / was on /dev/ubuntu-vg/ubuntu-lv during curtin installation
UUID=90bc13b5-9f1d-4865-92a9-cc87d93385ca / ext4 defaults 0 1
# /boot was on /dev/sda2 during curtin installation
UUID=6f0d41a2-60a5-4400-bfb6-c384032694f9 /boot ext4 defaults 0 1
/swap.img	none	swap	sw	0	0
```

**Partition Layout**:
- `/dev/nbd14p1`: 1M BIOS boot partition
- `/dev/nbd14p2`: 2G ext4 boot (UUID: 6f0d41a2-60a5-4400-bfb6-c384032694f9)
- `/dev/nbd14p3`: 498G LVM physical volume
  - VG: `ubuntu-vg`
  - LV: `ubuntu-lv` (100G ext4, UUID: 90bc13b5-9f1d-4865-92a9-cc87d93385ca)

**Boot Status**: ✅ Running successfully

---

### 3. Fedora Cloud 43

**Status**: ✅ ALREADY STABLE (no changes needed)

**Existing fstab** (already using UUID):
```
UUID=55773572-92c8-4d7e-bafd-3f4943a2f380 / btrfs compress=zstd:1,defaults,subvol=root 0 1
UUID=fc8240da-f3f1-47a3-87a1-4e80eb1371d0 /boot ext4 defaults 0 0
UUID=55773572-92c8-4d7e-bafd-3f4943a2f380 /home btrfs compress=zstd:1,subvol=home 0 0
UUID=55773572-92c8-4d7e-bafd-3f4943a2f380 /var btrfs compress=zstd:1,subvol=var 0 0
UUID=980C-1628 /boot/efi vfat defaults,umask=0077,shortname=winnt 0 0
```

**Partition Layout**:
- `/dev/nbd14p1`: 2M BIOS boot partition
- `/dev/nbd14p2`: 100M ext4 boot (UUID: fc8240da-f3f1-47a3-87a1-4e80eb1371d0)
- `/dev/nbd14p3`: 2G vfat EFI (UUID: 980C-1628)
- `/dev/nbd14p4`: 2.9G Btrfs root (UUID: 55773572-92c8-4d7e-bafd-3f4943a2f380)

**Boot Status**: ✅ Running successfully

---

### 4. CentOS 10 Server

**Status**: ✅ ALREADY STABLE (no changes needed)

**Existing fstab** (already using UUID):
```
UUID=3e0ad6b4-20e0-424d-999f-ce2e70cfb86e /                       xfs     defaults        0 0
UUID=15547891-2d55-4522-b27a-2183461fd641 /boot                   xfs     defaults        0 0
UUID=61907098-d80a-48ac-8b66-fffaa3d45bc5 /home                   xfs     defaults        0 0
UUID=54811d97-6965-4156-9527-f6cb43b70f2f none                    swap    defaults        0 0
```

**Partition Layout**:
- `/dev/nbd4p1`: 1M BIOS boot partition
- `/dev/nbd4p2`: 1G XFS boot (UUID: 15547891-2d55-4522-b27a-2183461fd641)
- `/dev/nbd4p3`: 499G LVM physical volume
  - VG: `cs`
  - LVs:
    - `root`: 70G XFS (UUID: 3e0ad6b4-20e0-424d-999f-ce2e70cfb86e)
    - `home`: 424.18G XFS (UUID: 61907098-d80a-48ac-8b66-fffaa3d45bc5)
    - `swap`: 4.81G (UUID: 54811d97-6965-4156-9527-f6cb43b70f2f)

**Boot Status**: ✅ Running successfully

---

### 5. Ubuntu VMware

**Status**: ✅ ALREADY STABLE (no changes needed)

**Existing fstab** (already using UUID):
```
# / was on /dev/sda2 during curtin installation
/dev/disk/by-uuid/d7da8f9b-5333-48d1-a96f-5c6ef03997ac / ext4 defaults 0 1
/swap.img	none	swap	sw	0	0
```

**Partition Layout**:
- `/dev/nbd14p1`: 1M BIOS boot partition
- `/dev/nbd14p2`: 20G ext4 root (UUID: d7da8f9b-5333-48d1-a96f-5c6ef03997ac)

**Boot Status**: ✅ Running successfully

---

## Technical Notes

### Handling Btrfs Subvolumes

For Btrfs filesystems with subvolumes (like openSUSE and Fedora):
1. Mount with specific subvolume: `mount -o subvol=root /dev/device /mnt`
2. All subvolumes share the same UUID
3. Subvolume names are specified in mount options: `subvol=/@/var`

### Handling LVM

For LVM-based systems (like CentOS and Ubuntu 25):
1. Scan for volume groups: `vgscan`
2. Activate volume groups: `vgchange -ay`
3. Mount logical volumes: `mount /dev/vgname/lvname /mnt`
4. Deactivate before disconnecting: `vgchange -an vgname`

**Important**: The NBD device number must match the one LVM expects. If LVM shows device mismatch warnings, reconnect to the correct NBD device.

### Device Mismatch Warning

When working with LVM, you may see:
```
WARNING: Device mismatch detected for cs/swap which is accessing /dev/nbd4p3 instead of /dev/nbd14p3.
```

**Solution**: Disconnect and reconnect to the NBD device LVM expects:
```bash
sudo vgchange -an vgname
sudo qemu-nbd -d /dev/nbd14
sudo qemu-nbd -c /dev/nbd4 /path/to/image.qcow2
sudo vgchange -ay
```

### UUID vs by-uuid Notation

Both notations are valid in fstab:
- `UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85`
- `/dev/disk/by-uuid/f293ef3c-255a-4582-8016-f72fb8dd3f85`

The `UUID=` notation is preferred as it's more concise.

## Verification

All 5 VMs are now running with stable UUID-based fstab entries:

```
$ sudo virsh list --all
 Id   Name                 State
------------------------------------
 1    opensuse-leap-15.4   running
 2    fedora43-cloud       running
 3    centos10-server      running
 4    ubuntu25-server      running
 5    ubuntu-vmware        running
```

## Recommendations

### For Future Migrations

1. **Always use fstab_mode: stabilize-all** in migration configs:
   ```yaml
   fstab_fixes_enable: true
   fstab_mode: stabilize-all
   ```

2. **Verify fstab after migration**:
   ```bash
   sudo qemu-nbd -c /dev/nbd0 image.qcow2
   sudo partprobe /dev/nbd0
   sudo mount /dev/nbd0pX /mnt
   sudo cat /mnt/etc/fstab
   ```

3. **Test boot before production**: Always test boot in a development environment before deploying to production.

### Best Practices

- Use UUID for all filesystem references
- Avoid device names like `/dev/sda1` (order can change)
- Avoid PCI paths (hardware-specific)
- For LVM, UUID is better than `/dev/vgname/lvname`
- For Btrfs, use UUID with subvolume options

## Summary

| VM                  | Original Identifier | Fixed | Boot Status |
|---------------------|---------------------|-------|-------------|
| openSUSE Leap 15.4  | by-path (PCI)       | ✅     | ✅ Running   |
| Ubuntu 25 Server    | dm-uuid (LVM)       | ✅     | ✅ Running   |
| Fedora Cloud 43     | UUID (stable)       | N/A   | ✅ Running   |
| CentOS 10 Server    | UUID (stable)       | N/A   | ✅ Running   |
| Ubuntu VMware       | UUID (stable)       | N/A   | ✅ Running   |

**Result**: 100% of VMs now use stable UUID identifiers and boot successfully in KVM.
