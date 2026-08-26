# Failure Modes and Troubleshooting Guide

This document covers common failure scenarios in VM migration and how hyper2kvm addresses them.

## Table of Contents

1. [Boot Failures](#boot-failures)
2. [Storage Issues](#storage-issues)
3. [Network Problems](#network-problems)
4. [Windows-Specific Issues](#windows-specific-issues)
5. [Conversion Failures](#conversion-failures)
6. [Testing Failures](#testing-failures)
7. [Debugging Strategies](#debugging-strategies)

---

## Boot Failures

### Failure: VM boots once, fails after reboot

**Symptoms:**
- First boot succeeds
- Subsequent reboots fail with kernel panic or "no root device"
- Error: "VFS: Cannot open root device"

**Root Cause:**
- `/etc/fstab` uses `/dev/sd*` or `/dev/disk/by-path/`
- Device enumeration changes between boots
- Hypervisor disk controller differences

**Solution:**
```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --fix-fstab \
  --use-uuid
```

**Manual Fix:**
```bash
# Mount the disk
sudo guestfish -a vm.qcow2 -i

# Check fstab
cat /etc/fstab

# Convert to UUID
blkid
# Edit fstab to use UUID=xxx instead of /dev/sdX
```

---

### Failure: Kernel panic - no initramfs match

**Symptoms:**
- Boot stops at "Loading initial ramdisk"
- Kernel panic during init
- Missing drivers in initramfs

**Root Cause:**
- Initramfs built for VMware devices
- Missing virtio drivers
- Wrong kernel modules

**Solution:**
```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --regen-initramfs \
  --add-virtio-modules
```

**Manual Fix (Fedora/RHEL):**
```bash
sudo guestfish -a vm.qcow2 -i
dracut --force --add-drivers "virtio_blk virtio_net virtio_pci" /boot/initramfs-$(uname -r).img $(uname -r)
```

---

### Failure: GRUB cannot find root device

**Symptoms:**
- GRUB error: "no such device"
- Boot stops at GRUB rescue prompt
- Kernel parameter `root=` points to wrong device

**Root Cause:**
- GRUB config references old device paths
- UUID changed after conversion
- Missing GRUB modules

**Solution:**
```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --fix-bootloader \
  --regenerate-grub
```

---

## Storage Issues

### Failure: Corrupted data after conversion

**Symptoms:**
- Files missing or corrupted
- Filesystem errors after first boot
- `qemu-img check` reports errors

**Root Cause:**
- Snapshot chain not properly flattened
- Parent VMDK descriptors missing
- Conversion interrupted

**Solution:**
```bash
# Always flatten snapshots
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --flatten \
  --to-output vm.qcow2 \
  --verify
```

**Prevention:**
```bash
# Check source VMDK integrity first
qemu-img check vm.vmdk
qemu-img info vm.vmdk

# Validate after conversion
qemu-img check vm.qcow2
```

---

### Failure: Disk full / out of space during conversion

**Symptoms:**
- Conversion fails mid-process
- Error: "No space left on device"
- Partial output file created

**Root Cause:**
- Insufficient disk space for conversion
- Temporary files fill up disk
- Compression not enabled

**Solution:**
```bash
# Check space before conversion
df -h /output/directory

# Use compression to save space
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --compress \
  --temp-dir /large/partition
```

---

### Failure: Snapshot chain broken

**Symptoms:**
- Error: "Could not open backing file"
- Parent VMDK not found
- Conversion fails on snapshot VMDKs

**Root Cause:**
- Split VMDK extents missing
- Snapshot parent chain incomplete
- Descriptor file corrupted

**Solution:**
```bash
# Fetch all related files
sudo h2kvmctl fetch-and-fix \
  --host esxi.example.com \
  --remote /vmfs/volumes/ds1/vm/vm.vmdk \
  --fetch-all \
  --flatten
```

---

## Network Problems

### Failure: No network after migration

**Symptoms:**
- Network interfaces missing
- Wrong interface names (ens3 vs eth0)
- No IP address assigned

**Root Cause:**
- Network config uses old interface names
- NetworkManager/systemd-networkd confusion
- MAC address changed

**Solution:**
```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --fix-network \
  --regenerate-network-config
```

**Manual Fix:**
```bash
# Check interface names
ip link show

# Regenerate network config
sudo nmcli connection show
sudo nmcli connection delete old-connection
sudo nmcli connection add type ethernet ifname ens3
```

---

### Failure: Network works but loses config on reboot

**Symptoms:**
- Network works on first boot
- Loses IP/DNS after reboot
- Persistent naming issues

**Root Cause:**
- udev rules cache old MAC addresses
- Persistent network rules from old hypervisor
- Multiple network managers fighting

**Solution:**
```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --clean-udev-rules \
  --fix-network
```

---

## Windows-Specific Issues

### Failure: Windows blue screen (BSOD) on first boot

**Symptoms:**
- BSOD with INACCESSIBLE_BOOT_DEVICE
- Stop code: 0x0000007B
- Cannot boot to desktop

**Root Cause:**
- VirtIO storage driver not loaded
- Driver not set to BOOT_START in registry
- Missing CriticalDeviceDatabase entries

**Solution:**
```bash
# Download VirtIO drivers first
wget https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso

# Inject drivers offline
sudo h2kvmctl local \
  --vmdk windows.vmdk \
  --to-output windows.qcow2 \
  --windows \
  --inject-virtio \
  --virtio-win-iso ./virtio-win.iso
```

**See also:** [Windows Migration Guide](10-Windows-Guide.md)

---

### Failure: Windows boots but no network

**Symptoms:**
- Windows boots successfully
- Network adapter shows "No driver" in Device Manager
- Yellow exclamation mark on network device

**Root Cause:**
- VirtIO network driver not installed
- Driver installed but not activated
- Wrong driver version

**Solution:**
```bash
# Use two-phase Windows boot
sudo h2kvmctl local \
  --vmdk windows.vmdk \
  --to-output windows.qcow2 \
  --windows \
  --inject-virtio \
  --virtio-win-iso ./virtio-win.iso \
  --two-phase-boot
```

---

### Failure: Windows activation issues after migration

**Symptoms:**
- Windows reports "not activated"
- Activation key invalid
- Hardware change detected

**Root Cause:**
- Hardware ID changed significantly
- OEM activation tied to hardware
- Volume license not portable

**Solution:**
- Re-activate with valid key
- Use volume license if available
- Contact Microsoft if hardware-locked OEM license

**Not a hyper2kvm issue** - this is expected Windows behavior.

---

## Conversion Failures

### Failure: qemu-img convert fails

**Symptoms:**
- Error: "Could not open file"
- Conversion hangs indefinitely
- Segmentation fault

**Root Cause:**
- Corrupted source VMDK
- Unsupported VMDK features
- Memory issues with large disks

**Solution:**
```bash
# Try alternative converter
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --use-export

# Or increase resources
ulimit -v unlimited
sudo h2kvmctl local --vmdk vm.vmdk --to-output vm.qcow2
```

---

### Failure: guestfs backend cannot mount filesystem

**Symptoms:**
- Error: "guestfs_mount: failed"
- Cannot inspect guest OS
- Unknown filesystem type

**Root Cause:**
- Missing filesystem support packages
- LVM/LUKS encryption
- Filesystem corruption

**Solution:**
```bash
# Install filesystem support
sudo dnf install xfsprogs e2fsprogs

# Skip inspection if needed
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --no-guest-inspection
```

---

### Failure: Conversion extremely slow

**Symptoms:**
- Conversion takes hours
- Progress bar stuck
- CPU at 100% for extended time

**Root Cause:**
- Large disk size
- Compression overhead
- Sparse file handling

**Solution:**
```bash
# Use fast mode
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --no-compress \
  --fast

# Or use multiple threads
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --threads 4
```

---

## Testing Failures

### Failure: libvirt test fails on headless server

**Symptoms:**
- Error: "Failed to connect to display"
- SDL/GTK errors
- Missing XDG_RUNTIME_DIR

**Root Cause:**
- Graphics device requires X11
- Running on headless server
- Display environment not configured

**Solution:**
```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --qemu-test \
  --headless
```

---

### Failure: QEMU test times out

**Symptoms:**
- VM boots but test never completes
- Timeout after 5 minutes
- No console output

**Root Cause:**
- VM boot is slow
- Serial console not configured
- Test waiting for boot completion

**Solution:**
```bash
# Increase timeout
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --qemu-test \
  --boot-timeout 600

# Or disable boot test
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --no-test
```

---

## Debugging Strategies

### Enable Debug Logging

```bash
sudo h2kvmctl --log-level DEBUG local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --log-file debug.log
```

### Use Dry Run Mode

```bash
# Preview what will happen
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --dry-run
```

### Generate Detailed Report

```bash
sudo h2kvmctl local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --report migration-report.md
```

### Manual Inspection

```bash
# Inspect source VMDK
qemu-img info vm.vmdk
qemu-img check vm.vmdk

# Inspect output
qemu-img info vm.qcow2
qemu-img check vm.qcow2

# Mount and explore
sudo guestfish -a vm.qcow2 -i
><fs> ls /
><fs> cat /etc/fstab
><fs> cat /boot/grub2/grub.cfg
```

### Boot in Rescue Mode

```bash
# Boot with serial console
qemu-system-x86_64 \
  -m 2048 \
  -smp 2 \
  -drive file=vm.qcow2,if=virtio \
  -enable-kvm \
  -nographic \
  -serial mon:stdio \
  -append "console=ttyS0"
```

---

## Common Error Messages

### "VFS: Cannot open root device"
- Fix: Update `/etc/fstab` to use UUID
- See: [Boot Failures](#failure-vm-boots-once-fails-after-reboot)

### "INACCESSIBLE_BOOT_DEVICE (0x0000007B)"
- Fix: Inject VirtIO drivers
- See: [Windows BSOD](#failure-windows-blue-screen-bsod-on-first-boot)

### "Could not open backing file"
- Fix: Flatten snapshot chain
- See: [Snapshot chain broken](#failure-snapshot-chain-broken)

### "guestfs_launch failed"
- Fix: Check guestfs backend configuration and filesystem support packages

### "No space left on device"
- Fix: Free up space or use compression
- See: [Disk full](#failure-disk-full--out-of-space-during-conversion)

---

## Getting Help

If you encounter issues not covered here:

1. **Enable debug logging:** `--log-level DEBUG`
2. **Generate a report:** `--report issue-report.md`
3. **Check GitHub Issues:** https://github.com/ssahani/hyper2kvm/issues
4. **Create a bug report:** Use the issue template

### Information to Include

When reporting issues, provide:
- Source VM type (VMware, Hyper-V, etc.)
- Guest OS and version
- Command used (with sensitive data redacted)
- Full error output
- Debug logs
- Output of `qemu-img info` on source and destination

---

## Related Documentation

- [Windows Troubleshooting](12-Windows-Troubleshooting.md)
- [Windows Boot Cycle](11-Windows-Boot-Cycle.md)
- [Quick Start Guide](03-Quick-Start.md)
- [CLI Reference](04-CLI-Reference.md)
