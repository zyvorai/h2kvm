# Migration Quick Reference

**Quick Reference Card for Common h2kvm Migration Scenarios**

One-page guide for the most frequent migration tasks with copy-paste commands.

---

## Basic Migration Patterns

### 1. Simple VMware to KVM

**Scenario**: Convert VMDK to QCOW2 for local KVM use

```bash
# Single command migration
h2kvm convert /path/to/vm.vmdk --output /var/lib/libvirt/images/vm.qcow2

# With offline fixes (recommended)
h2kvm convert /path/to/vm.vmdk \
  --output /var/lib/libvirt/images/vm.qcow2 \
  --offline-fixes

# With automatic libvirt domain creation
h2kvm convert /path/to/vm.vmdk \
  --output /var/lib/libvirt/images/vm.qcow2 \
  --offline-fixes \
  --libvirt-domain my-vm \
  --autostart
```

**Key Options**:
- `--offline-fixes`: Apply bootloader repairs, fstab fixes, network stabilization
- `--libvirt-domain`: Create libvirt XML definition
- `--autostart`: Configure VM to start on boot

---

### 2. Hyper-V to KVM

**Scenario**: Migrate Hyper-V VHDX to KVM QCOW2

```bash
# Direct conversion
h2kvm convert /path/to/vm.vhdx \
  --output /var/lib/libvirt/images/vm.qcow2 \
  --format qcow2

# With Windows-specific fixes
h2kvm convert /path/to/vm.vhdx \
  --output /var/lib/libvirt/images/vm.qcow2 \
  --offline-fixes \
  --inject-virtio \
  --windows
```

**Windows-Specific Options**:
- `--inject-virtio`: Inject VirtIO drivers for Windows
- `--windows`: Apply Windows-specific registry fixes
- `--driver-repo /path/to/virtio-win`: Custom VirtIO driver location

---

### 3. Cloud Image Customization

**Scenario**: Customize cloud images for local deployment

```bash
# Basic cloud-init configuration
h2kvm customize ubuntu-cloud.qcow2 \
  --cloud-init user-data.yaml \
  --hostname my-server \
  --output customized.qcow2

# With network and user setup
h2kvm customize fedora-cloud.qcow2 \
  --user admin \
  --ssh-key ~/.ssh/id_rsa.pub \
  --root-password "$PASSWORD" \
  --network-config network.yaml \
  --output custom-fedora.qcow2
```

**Cloud-Init Options**:
- `--cloud-init`: Path to cloud-init user-data YAML
- `--user`: Create user account
- `--ssh-key`: Inject SSH public key
- `--root-password`: Set root password
- `--network-config`: Custom network configuration

---

### 4. Batch Migration

**Scenario**: Migrate multiple VMs from manifest file

```bash
# Create batch manifest
cat > batch.yaml <<EOF
vms:
  - name: web-server-01
    source: /vmware/web-01.vmdk
    priority: high

  - name: db-server
    source: /vmware/database.vmdk
    priority: high

  - name: test-server
    source: /vmware/test.vmdk
    priority: low

shared_config:
  output_dir: /var/lib/libvirt/images
  format: qcow2
  offline_fixes: true
  parallel_limit: 2
EOF

# Run batch migration
h2kvm batch batch.yaml

# Resume interrupted batch
h2kvm batch batch.yaml --resume

# Continue on errors
h2kvm batch batch.yaml --continue-on-error
```

**Batch Options**:
- `--resume`: Resume from last checkpoint
- `--continue-on-error`: Don't stop on single VM failure
- `--parallel-limit`: Max concurrent migrations (default: 2)
- `--checkpoint-interval`: Save progress every N seconds

---

### 5. vSphere Live Migration

**Scenario**: Migrate running VMs from vSphere

```bash
# Configure vSphere credentials
export VSPHERE_HOST="vcenter.example.com"
export VSPHERE_USER="administrator@vsphere.local"
export VSPHERE_PASSWORD="password"

# List available VMs
h2kvm vsphere list --host $VSPHERE_HOST

# Export single VM
h2kvm vsphere export \
  --vm "Production Web Server" \
  --output /exports/web-server.qcow2 \
  --format qcow2

# Export with snapshot
h2kvm vsphere export \
  --vm "Database Server" \
  --snapshot "Pre-migration" \
  --output /exports/db-server.qcow2
```

**vSphere Options**:
- `--host`: vCenter server hostname
- `--user`: vSphere username
- `--password`: vSphere password (use env var for security)
- `--snapshot`: Use specific snapshot
- `--datacenter`: Target datacenter (if multiple)

---

## Advanced Patterns

### 6. Multi-Disk Migration

**Scenario**: VM with multiple disks

```bash
# Migrate all disks
h2kvm convert /vmware/vm-disk1.vmdk \
  --additional-disks /vmware/vm-disk2.vmdk,/vmware/vm-disk3.vmdk \
  --output-dir /var/lib/libvirt/images/multi-disk-vm \
  --offline-fixes

# Creates:
# - /var/lib/libvirt/images/multi-disk-vm/disk1.qcow2
# - /var/lib/libvirt/images/multi-disk-vm/disk2.qcow2
# - /var/lib/libvirt/images/multi-disk-vm/disk3.qcow2
```

---

### 7. Compression and Optimization

**Scenario**: Minimize storage footprint

```bash
# Enable compression
h2kvm convert /source/vm.vmdk \
  --output /dest/vm.qcow2 \
  --compression zstd \
  --compression-level 6

# Trim unused space
h2kvm optimize /dest/vm.qcow2 --trim

# Convert to thin provisioning
h2kvm convert /source/thick.vmdk \
  --output /dest/thin.qcow2 \
  --preallocation off
```

**Compression Options**:
- `--compression`: Algorithm (zstd, lz4, zlib, none)
- `--compression-level`: 1-9 (higher = better compression, slower)
- `--trim`: Remove unused blocks
- `--preallocation`: Storage allocation (off, metadata, falloc, full)

---

### 8. Network Stabilization

**Scenario**: Fix network interfaces post-migration

```bash
# Automatic network stabilization
h2kvm convert /source/vm.vmdk \
  --output /dest/vm.qcow2 \
  --offline-fixes \
  --network-stable

# Manual network mapping
h2kvm convert /source/vm.vmdk \
  --output /dest/vm.qcow2 \
  --network-mapping "VM Network=br0,Management=br1"

# Convert to NetworkManager
h2kvm fixnet /dest/vm.qcow2 \
  --to-networkmanager
```

**Network Options**:
- `--network-stable`: Use stable device naming (by-path, by-uuid)
- `--network-mapping`: Map source networks to target bridges
- `--to-networkmanager`: Convert from ifcfg to NetworkManager

---

### 9. Bootloader Repair

**Scenario**: Fix GRUB after migration

```bash
# Auto-detect and repair GRUB
h2kvm fixboot /path/to/vm.qcow2

# Force GRUB2 reinstall
h2kvm fixboot /path/to/vm.qcow2 --reinstall-grub

# Enhanced chroot repair (for complex boot issues)
h2kvm fixboot /path/to/vm.qcow2 --enhanced-chroot

# Specify boot device
h2kvm fixboot /path/to/vm.qcow2 --boot-device /dev/vda
```

**Bootloader Options**:
- `--reinstall-grub`: Force GRUB2 reinstallation
- `--enhanced-chroot`: Use bind mounts for /dev, /proc, /sys
- `--boot-device`: Target device for GRUB installation
- `--uefi`: Fix UEFI boot instead of legacy BIOS

---

### 10. Filesystem Stabilization

**Scenario**: Fix fstab for KVM device names

```bash
# Convert /etc/fstab to stable identifiers
h2kvm fixfstab /path/to/vm.qcow2

# Force UUID-based mounting
h2kvm fixfstab /path/to/vm.qcow2 --prefer uuid

# Force LABEL-based mounting
h2kvm fixfstab /path/to/vm.qcow2 --prefer label

# Validate without changes
h2kvm fixfstab /path/to/vm.qcow2 --dry-run
```

**Fstab Options**:
- `--prefer uuid`: Use UUID= mount identifiers
- `--prefer label`: Use LABEL= mount identifiers
- `--prefer path`: Use /dev/disk/by-path/ identifiers
- `--dry-run`: Show what would be changed

---

## TUI (Terminal User Interface)

### 11. Interactive Migration

**Scenario**: Use TUI for guided migration

```bash
# Launch TUI
h2kvm-tui

# Or with specific features
h2kvm-tui --theme dark
h2kvm-tui --config ~/.config/h2kvm/custom-tui.json
```

**TUI Keyboard Shortcuts**:
- `F1`: Help
- `F2`: Migration Wizard
- `F3`: VM Browser
- `F5`: Refresh
- `Ctrl+S`: Settings
- `Ctrl+Q`: Quit

**TUI Features**:
- Visual migration wizard (step-by-step)
- VM browser (vSphere, Local, Hyper-V)
- Real-time migration monitoring
- Batch migration management
- Settings persistence
- Migration history tracking

---

## Inspection and Analysis

### 12. Pre-Migration Analysis

**Scenario**: Analyze VM before migration

```bash
# Full inspection
h2kvm inspect /path/to/vm.vmdk

# Check migration readiness
h2kvm readiness-check /path/to/vm.vmdk

# Operating system detection
h2kvm os-info /path/to/vm.vmdk

# Filesystem analysis
h2kvm fs-info /path/to/vm.vmdk

# Boot configuration
h2kvm boot-info /path/to/vm.vmdk
```

**Inspection Output Includes**:
- OS type and version
- Installed kernels
- Boot loader configuration
- Filesystem layout
- Network configuration
- Systemd services
- Mounted filesystems
- LVM/LUKS detection

---

### 13. Post-Migration Validation

**Scenario**: Verify migration success

```bash
# Boot validation
h2kvm validate-boot /dest/vm.qcow2

# Network validation
h2kvm validate-network /dest/vm.qcow2

# Compare with source
h2kvm compare /source/vm.vmdk /dest/vm.qcow2

# Generate migration report
h2kvm report /dest/vm.qcow2 --output migration-report.json
```

---

## Troubleshooting

### 14. Common Issues

**Migration fails with GRUB error**:
```bash
# Apply enhanced chroot fix
h2kvm fixboot /vm.qcow2 --enhanced-chroot
```

**VM doesn't boot (black screen)**:
```bash
# Check boot configuration
h2kvm boot-info /vm.qcow2

# Reinstall GRUB
h2kvm fixboot /vm.qcow2 --reinstall-grub --boot-device /dev/vda
```

**Network interfaces not working**:
```bash
# Stabilize network configuration
h2kvm fixnet /vm.qcow2 --network-stable

# Or convert to NetworkManager
h2kvm fixnet /vm.qcow2 --to-networkmanager
```

**Filesystem mount failures**:
```bash
# Fix fstab with UUIDs
h2kvm fixfstab /vm.qcow2 --prefer uuid

# Check filesystem layout
h2kvm fs-info /vm.qcow2
```

**Windows VM stuck at boot**:
```bash
# Inject VirtIO drivers
h2kvm convert source.vhdx --output dest.qcow2 \
  --inject-virtio \
  --driver-repo /usr/share/virtio-win

# Apply Windows registry fixes
h2kvm fixwin dest.qcow2
```

---

## Configuration Examples

### 15. Profile-Based Migration

**Scenario**: Use pre-configured profiles for consistency

```bash
# Create profile
cat > ~/.config/h2kvm/profiles/production.yaml <<EOF
format: qcow2
offline_fixes: true
compression: zstd
compression_level: 6
network_stable: true
libvirt_domain_auto: true
autostart: true
cpu: 4
memory: 8192
EOF

# Use profile
h2kvm convert /source/vm.vmdk \
  --profile production \
  --output /dest/vm.qcow2

# Override profile settings
h2kvm convert /source/vm.vmdk \
  --profile production \
  --cpu 8 \
  --memory 16384 \
  --output /dest/vm.qcow2
```

---

### 16. Hooks and Automation

**Scenario**: Execute custom scripts during migration

```bash
# Define hooks in manifest
cat > migration.yaml <<EOF
vm:
  name: web-server
  source: /source/web.vmdk
  output: /dest/web.qcow2

hooks:
  pre_migration:
    - script: /scripts/backup-source.sh
  post_migration:
    - script: /scripts/configure-vm.sh
    - script: /scripts/start-vm.sh
  on_error:
    - script: /scripts/alert-admin.sh
EOF

# Run migration with hooks
h2kvm migrate migration.yaml
```

---

## Environment Variables

```bash
# vSphere configuration
export VSPHERE_HOST="vcenter.example.com"
export VSPHERE_USER="administrator@vsphere.local"
export VSPHERE_PASSWORD="secret"

# Storage locations
export H2KVM_OUTPUT_DIR="/var/lib/libvirt/images"
export H2KVM_TEMP_DIR="/tmp/h2kvm"

# Default settings
export H2KVM_FORMAT="qcow2"
export H2KVM_COMPRESSION="zstd"
export H2KVM_OFFLINE_FIXES="true"

# Logging
export H2KVM_LOG_LEVEL="info"
export H2KVM_LOG_FILE="/var/log/h2kvm.log"
```

---

## Performance Tips

### CPU and Memory

```bash
# Limit CPU usage (nice level)
nice -n 10 h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2

# Set I/O priority (ionice)
ionice -c 3 h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2

# Combine CPU and I/O limits
nice -n 10 ionice -c 3 h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2
```

### Parallel Operations

```bash
# Batch migration with parallelism
h2kvm batch manifest.yaml --parallel-limit 4

# Process multiple VMs concurrently
for vm in web1 web2 web3 web4; do
  h2kvm convert /source/$vm.vmdk --output /dest/$vm.qcow2 &
done
wait  # Wait for all to complete
```

### Compression Trade-offs

```bash
# Fast compression (lz4)
h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2 --compression lz4

# Balanced (zstd level 3)
h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2 --compression zstd --compression-level 3

# Maximum compression (zstd level 9)
h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2 --compression zstd --compression-level 9
```

---

## Getting Help

```bash
# General help
h2kvm --help

# Command-specific help
h2kvm convert --help
h2kvm batch --help
h2kvm vsphere --help

# Show version
h2kvm --version

# Enable verbose logging
h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2 --verbose

# Debug mode (very verbose)
h2kvm convert /source/vm.vmdk --output /dest/vm.qcow2 --debug
```

---

## Quick Syntax Reference

```bash
# Basic conversion
h2kvm convert <source> --output <dest> [OPTIONS]

# With offline fixes
h2kvm convert <source> --output <dest> --offline-fixes

# Batch migration
h2kvm batch <manifest.yaml> [OPTIONS]

# vSphere export
h2kvm vsphere export --vm "<name>" --output <dest> [OPTIONS]

# Bootloader repair
h2kvm fixboot <image> [OPTIONS]

# Network stabilization
h2kvm fixnet <image> [OPTIONS]

# Fstab stabilization
h2kvm fixfstab <image> [OPTIONS]

# Inspection
h2kvm inspect <image>
h2kvm os-info <image>
h2kvm fs-info <image>
h2kvm boot-info <image>

# TUI
h2kvm-tui
```

---

**Last Updated**: March 29, 2026
**Version**: 1.0
**For More Details**: See full documentation in `docs/` directory

**Common Use Case**: VMware to KVM with all fixes
```bash
h2kvm convert /vmware/production.vmdk \
  --output /var/lib/libvirt/images/production.qcow2 \
  --offline-fixes \
  --network-stable \
  --compression zstd \
  --libvirt-domain production \
  --cpu 4 \
  --memory 8192 \
  --autostart
```
