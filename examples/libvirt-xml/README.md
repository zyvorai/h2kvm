# Libvirt XML Templates

Tested and working libvirt domain XML templates for migrated VMs.

## Templates

### Linux (RHEL/CentOS/Fedora/Rocky/AlmaLinux)

1. **`linux-bios.xml`** - BIOS/Legacy boot
   - ✅ Tested with CentOS 8/9, RHEL 8/9, Fedora
   - Q35 chipset, VirtIO disk/network
   - SPICE graphics, serial console
   - QEMU guest agent ready

2. **`linux-uefi.xml`** - UEFI boot
   - ✅ Tested with CentOS 9, RHEL 9.4, Fedora
   - OVMF UEFI firmware
   - Secure Boot ready (disabled by default)
   - Q35 chipset, VirtIO disk/network

### Windows

3. **`windows-server-uefi.xml`** - Windows Server/10/11
   - UEFI boot with OVMF
   - Hyper-V enlightenments for performance
   - VirtIO disk/network (requires drivers)
   - Local time clock (Windows requirement)

## Usage

### Method 1: Direct Import

```bash
# Edit the XML file first:
# 1. Change VM name
# 2. Update disk path
# 3. Adjust memory/CPU if needed

# Import to libvirt
virsh define linux-bios.xml

# Start the VM
virsh start linux-vm-bios
```

### Method 2: Use as Template for h2kvm

The `h2kvm` tool can automatically generate similar XML during migration.

## Customization Guide

### Common Edits

- **VM Name**: `<name>your-vm-name</name>`
- **Memory**: `<memory unit='KiB'>8388608</memory>  <!-- 8 GB -->`
- **CPUs**: `<vcpu placement='static'>4</vcpu>`
- **Disk**: `<source file='/path/to/your/disk.qcow2'/>`

## License

Apache-2.0 (same as h2kvm)
