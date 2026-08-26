# Photon OS Test Configurations

This directory contains configuration files for testing Photon OS conversions from VMware VMDK to KVM/QCOW2.

## Files

### Conversion Configuration

**`04-local-photon-os-vmdk.yaml`** - Main conversion configuration
- Converts local Photon OS VMDK to QCOW2
- Applies fstab stabilization, GRUB fixes, initramfs rebuild
- Runs libvirt smoke test to verify bootability
- Generates reports and checksums

Usage:
```bash
sudo ./h2kvmctl --config test-confs/04-local-photon-os-vmdk.yaml
```

### Libvirt Domain XML Files

**`photon-virtio.xml`** - Recommended configuration (virtio)
- Uses virtio disk interface for best performance
- **Use this by default** - Photon OS ships with virtio drivers
- Tested and verified to boot successfully

Usage:
```bash
sudo virsh define test-confs/photon-virtio.xml
sudo virsh start photon-converted
```

**`photon-sata.xml`** - Fallback configuration (SATA)
- Uses SATA disk interface for compatibility
- **Only use if virtio fails** (very rare with modern Photon OS)
- Provided as troubleshooting fallback

Usage:
```bash
sudo virsh define test-confs/photon-sata.xml
sudo virsh start photon-converted
```

## Expected Behavior

### During Conversion

You will see this warning - **this is normal**:
```
⚠️  initramfs rebuild failed: mtime+size unchanged
```

**This means:**
- Photon OS already has virtio drivers in the initramfs
- No rebuild was needed (image is already KVM-ready)
- The VM will boot successfully with virtio

### After Conversion

Successful boot indicators:
- ✅ VM reaches RUNNING state
- ✅ Acquires IP address via DHCP
- ✅ SSH daemon accessible on port 22
- ✅ Console shows login prompt

## Verification

Check VM status:
```bash
sudo virsh dominfo photon-converted
sudo virsh domifaddr photon-converted  # Get IP address
```

Test network connectivity:
```bash
# Get IP from virsh
IP=$(sudo virsh domifaddr photon-converted | awk '/ipv4/{print $4}' | cut -d/ -f1)

# Test SSH port
nc -zv $IP 22
```

## Troubleshooting

### VM not booting
1. Check it's using virtio: `sudo virsh dumpxml photon-converted | grep "bus="`
2. Try SATA fallback if virtio fails (rare)
3. Check console output: `sudo virsh console photon-converted`

### No IP address
- Wait 30-60 seconds for DHCP
- Check network is started: `sudo virsh net-list --all`
- Start network: `sudo virsh net-start default`

### Can't connect via SSH
- Verify port is open: `nc -zv <IP> 22`
- Check VM is fully booted: `sudo virsh domstate photon-converted`
- You may need credentials from original VM

## Related Documentation

- **Full guide**: `docs/os-support/photon-os.md`
- **Conversion workflow**: `docs/03-Quick-Start.md`
- **CLI reference**: `docs/04-CLI-Reference.md`

## Test Results

- ✅ Photon OS 5.0 - Boots with virtio
- ✅ Photon OS 4.0 - Boots with virtio
- ✅ Photon OS 3.0 - Boots with virtio
- ⚠️  Older versions - May need SATA fallback

**Last tested:** 2026-02-08
**Status:** All tests passing with virtio configuration
