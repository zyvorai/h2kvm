# VMDK Conversion Directory Configuration

## Overview

h2kvm converts sparse VMDK files to QCOW2 format during migration for reliability and performance. This guide explains how to configure the temporary conversion directory for optimal disk space management.

## Default Behavior

**Before (hardcoded)**:
- Conversion directory: `/var/tmp/guestkit-conversions/`
- Issues: System-wide location, permission conflicts, disk space constraints

**After (configurable)**:
- Default: `~/.cache/h2kvm/conversions`
- Per-user isolation
- Respects XDG Base Directory specification
- Better disk space management

## Configuration Methods

### 1. CLI Argument (Highest Priority)

```bash
# Specify conversion directory via CLI
h2kvmctl --conversion-dir /path/to/conversions --config migration.yaml

# Example: Use large disk for conversions
h2kvmctl --conversion-dir /mnt/large-disk/guestkit-temp --config centos.yaml
```

### 2. YAML Configuration File

```yaml
# migration.yaml
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: /path/to/output

# Conversion directory configuration
conversion_dir: ~/large-disk/guestkit-conversions

# Other settings...
fstab_mode: stabilize-all
libvirt_import: true
```

### 3. Environment Variable

```bash
# Set via environment (future enhancement)
export H2KVM_CONVERSION_DIR=/mnt/large-disk/conversions
h2kvmctl --config migration.yaml
```

## Use Cases

### Single-User Workstation

**Scenario**: Developer migrating VMs on local workstation

```bash
# Use default per-user cache directory
h2kvmctl --config migration.yaml

# Conversion files stored in: ~/.cache/h2kvm/conversions
```

**Benefits**:
- No configuration needed
- Automatic cleanup
- No permission issues

### Multi-User Server

**Scenario**: Shared server with multiple users running migrations

```bash
# User 1
h2kvmctl --conversion-dir ~/conversions --config user1-vm.yaml

# User 2
h2kvmctl --conversion-dir ~/conversions --config user2-vm.yaml
```

**Benefits**:
- User isolation (no conflicts)
- Each user manages their own space
- No shared directory permission issues

### Dedicated Service User

**Scenario**: Automated migration service running as dedicated user

```bash
# Create dedicated user
sudo useradd -r -m -d /var/lib/h2kvm -s /bin/bash h2kvm
sudo mkdir -p /var/lib/h2kvm/conversions
sudo chown h2kvm:h2kvm /var/lib/h2kvm/conversions

# Add to required groups
sudo usermod -a -G kvm,qemu,disk,libvirt h2kvm

# Configure sudoers for NBD operations
sudo tee /etc/sudoers.d/h2kvm << 'EOF'
h2kvm ALL=(ALL) NOPASSWD: /usr/bin/qemu-nbd
h2kvm ALL=(ALL) NOPASSWD: /usr/sbin/modprobe
h2kvm ALL=(ALL) NOPASSWD: /usr/bin/qemu-img
h2kvm ALL=(ALL) NOPASSWD: /usr/bin/mount
h2kvm ALL=(ALL) NOPASSWD: /usr/bin/umount
h2kvm ALL=(ALL) NOPASSWD: /usr/sbin/vgchange
h2kvm ALL=(ALL) NOPASSWD: /usr/sbin/lvscan
h2kvm ALL=(ALL) NOPASSWD: /usr/sbin/blkid
EOF

# Run migration as service user
sudo -u h2kvm h2kvmctl --conversion-dir /var/lib/h2kvm/conversions --config migration.yaml
```

**Benefits**:
- Proper service isolation
- Predictable location for monitoring
- Systemd integration ready
- Enterprise-ready

### Large Disk for Conversions

**Scenario**: Home directory has limited space, need to use different disk

```bash
# Mount large disk
sudo mkdir -p /mnt/large-disk
sudo mount /dev/sdb1 /mnt/large-disk

# Create conversion directory
mkdir -p /mnt/large-disk/h2kvm-conversions

# Run migration
h2kvmctl --conversion-dir /mnt/large-disk/h2kvm-conversions --config migration.yaml
```

**Benefits**:
- Use disk with most available space
- Avoid filling up system partitions
- Better I/O performance (separate disk)

### Container/Kubernetes Deployment

**Scenario**: Running h2kvm in container with volume mounts

```yaml
# Kubernetes Pod
apiVersion: v1
kind: Pod
metadata:
  name: h2kvm-migration
spec:
  containers:
  - name: h2kvm
    image: h2kvm:latest
    volumeMounts:
    - name: conversions
      mountPath: /var/conversions
    - name: vmdk-source
      mountPath: /vmdk
    - name: output
      mountPath: /output
    command:
    - h2kvmctl
    - --conversion-dir
    - /var/conversions
    - --config
    - /config/migration.yaml
  volumes:
  - name: conversions
    emptyDir:
      sizeLimit: 100Gi
  - name: vmdk-source
    persistentVolumeClaim:
      claimName: vmdk-pvc
  - name: output
    persistentVolumeClaim:
      claimName: output-pvc
```

**Benefits**:
- Explicit volume control
- Size limits
- Cleanup on pod deletion

## Disk Space Considerations

### Sparse VMDK Conversion

**Scenario**: VM with 500GB virtual size, 2GB actual usage

```bash
# Sparse conversion (LVM not detected)
# Disk space needed: ~2GB (actual usage)
h2kvmctl --conversion-dir ~/conversions --config vm.yaml
```

**Process**:
1. VMDK → RAW: ~2GB (sparse)
2. RAW → QCOW2: ~2GB (sparse-aware)
3. Total: ~4GB during conversion, ~2GB final

### Non-Sparse Conversion (LVM/RAID/LUKS)

**Scenario**: VM with 500GB virtual size, contains LVM

```bash
# LVM detected → sparse disabled (prevent corruption)
# Disk space needed: ~500GB (full virtual size)
h2kvmctl --conversion-dir /mnt/large-disk/conversions --config vm.yaml
```

**Warning**: h2kvm automatically disables sparse conversion for:
- LVM volumes
- mdraid arrays
- LUKS encrypted volumes

**Best Practice**: Always use a conversion directory with enough space for the full virtual size.

### Checking Available Space

```bash
# Check home directory space
df -h ~

# Check conversion directory space
df -h ~/.cache/h2kvm/conversions

# Check large disk space
df -h /mnt/large-disk
```

## Cleanup and Maintenance

### Manual Cleanup

```bash
# Remove all conversion temporary files
rm -rf ~/.cache/h2kvm/conversions/*

# Remove specific conversion
rm -rf ~/.cache/h2kvm/conversions/vm-name.*
```

### Automatic Cleanup

Conversion files are automatically cleaned up:
- ✅ On successful migration (by default)
- ✅ On graceful shutdown
- ⚠️ **Not cleaned** on crashes or `kill -9`

### Systemd Timer for Cleanup

```ini
# /etc/systemd/system/h2kvm-cleanup.timer
[Unit]
Description=Cleanup h2kvm conversion directory daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/h2kvm-cleanup.service
[Unit]
Description=Cleanup old h2kvm conversions

[Service]
Type=oneshot
ExecStart=/usr/bin/find /var/lib/h2kvm/conversions -type f -mtime +1 -delete
User=h2kvm
Group=h2kvm
```

Enable:
```bash
sudo systemctl enable --now h2kvm-cleanup.timer
```

## Troubleshooting

### Permission Denied

**Error**: `Permission denied: /var/tmp/guestkit-conversions`

**Solution**:
```bash
# Use user-specific directory
h2kvmctl --conversion-dir ~/conversions --config migration.yaml
```

### No Space Left on Device

**Error**: `qemu-img: error while writing at byte X: No space left on device`

**Solution**:
```bash
# Check available space
df -h ~/.cache/h2kvm/conversions

# Use larger disk
h2kvmctl --conversion-dir /mnt/large-disk/conversions --config migration.yaml

# Or clean up old conversions
rm -rf ~/.cache/h2kvm/conversions/*
```

### Conversion Directory Not Created

**Error**: Conversion fails with "directory does not exist"

**Solution**: Directory is created automatically, but ensure parent directory is writable:
```bash
# Ensure parent exists and is writable
mkdir -p ~/custom-conversions
h2kvmctl --conversion-dir ~/custom-conversions --config migration.yaml
```

## Security Considerations

### Directory Permissions

**Default behavior**:
```bash
# Created with mode 0700 (owner read/write/execute only)
ls -ld ~/.cache/h2kvm/conversions
# drwx------ user user ~/.cache/h2kvm/conversions
```

**Custom directory**:
```bash
# Ensure proper permissions
mkdir -p /var/lib/h2kvm/conversions
chmod 700 /var/lib/h2kvm/conversions
chown h2kvm:h2kvm /var/lib/h2kvm/conversions
```

### Sensitive Data

**Warning**: Conversion files are **unencrypted temporary copies** of VM disks.

**Best practices**:
- Use encrypted filesystem for conversion directory
- Clean up immediately after migration
- Avoid shared/public directories
- Use dedicated user for service deployments

### SELinux/AppArmor

**SELinux context** (RHEL/CentOS/Fedora):
```bash
# Set proper context for conversion directory
sudo semanage fcontext -a -t virt_image_t "/var/lib/h2kvm/conversions(/.*)?"
sudo restorecon -Rv /var/lib/h2kvm/conversions
```

**AppArmor profile** (Ubuntu/Debian):
```bash
# Add to /etc/apparmor.d/local/usr.bin.qemu-system-x86_64
/var/lib/h2kvm/conversions/** rw,
```

## Performance Tips

### I/O Performance

**Best practices**:
- Use local disk (avoid NFS/network mounts)
- Use SSD for faster conversions
- Use separate disk from output directory (parallel I/O)

### Example: Optimal Setup

```bash
# Fast SSD for conversions (temporary)
h2kvmctl --conversion-dir /mnt/ssd/conversions \
         --config migration.yaml

# Large HDD for final output (permanent)
# (configured in migration.yaml as output_dir)
```

## Migration Path

### From Hardcoded `/var/tmp`

**No action required** - defaults changed automatically to `~/.cache/h2kvm/conversions`

### Existing Scripts

**Option 1: Use default**
```bash
# Old (still works)
h2kvm --config migration.yaml

# New (same behavior)
h2kvmctl --config migration.yaml
# Uses ~/.cache/h2kvm/conversions
```

**Option 2: Explicit configuration**
```bash
# Preserve old behavior
h2kvmctl --conversion-dir /var/tmp/guestkit-conversions --config migration.yaml
```

## Summary

| Scenario | Recommended Configuration |
|----------|--------------------------|
| Developer workstation | Default (`~/.cache/h2kvm/conversions`) |
| Multi-user server | Per-user (`~/conversions`) |
| Dedicated service | `/var/lib/h2kvm/conversions` |
| Limited disk space | External disk (`/mnt/large-disk/conversions`) |
| Container deployment | Volume mount (`/var/conversions`) |
| CI/CD pipeline | Workspace directory (`$WORKSPACE/conversions`) |

**Key Points**:
- Default is per-user and automatic
- Configure for large VMs or limited space
- Clean up periodically
- Use dedicated user for services
- Ensure enough space for full virtual size (LVM VMs)
