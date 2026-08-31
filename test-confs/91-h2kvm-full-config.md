# JSON Configuration Guide for h2kvm

This document explains the JSON configuration format for `91-h2kvm-full-config.json`.

> **Note:** JSON does not support comments. For configurations with inline comments, use the YAML format (`90-h2kvm-full-config.yaml`) instead.

## Configuration File: 91-h2kvm-full-config.json

### Complete Example with Explanations

```json
{
  "command": "local",
  "vmdk": "/home/ssahani/by-path/openSUSE_Leap_15.4_VM_LinuxVMImages.COM.vmdk",
  "output_dir": "/home/ssahani/by-path/out",
  "flatten": true,
  "flatten_format": "qcow2",
  "to_output": "opensuse-leap-15.4-fixed.qcow2",
  "out_format": "qcow2",
  "compress": true,
  "checksum": true,
  "print_fstab": true,
  "fstab_mode": "stabilize-all",
  "no_grub": false,
  "regen_initramfs": true,
  "no_backup": false,
  "dry_run": false,
  "verbose": 2,
  "log_file": "/home/ssahani/by-path/out/h2kvm.log",
  "report": "/home/ssahani/by-path/out/h2kvm-report.md"
}
```

---

## Field Reference

### Command Selection

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | ✅ | Conversion mode. Options: `local`, `vsphere`, `hyperv` |

**Example:**
```json
{
  "command": "local"
}
```

---

### Input Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vmdk` | string | ✅ | Path to source VMDK file to convert |

**Example:**
```json
{
  "vmdk": "/path/to/virtual-machine.vmdk"
}
```

**Notes:**
- Must be an absolute path
- File must exist and be readable
- Supports both monolithic and split VMDK formats

---

### Output Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `output_dir` | string | ✅ | - | Directory for output files |
| `to_output` | string | ❌ | auto-generated | Final output filename (relative to `output_dir`) |
| `out_format` | string | ❌ | `qcow2` | Output format: `qcow2`, `raw`, `vmdk`, `vdi`, `vhdx` |
| `compress` | boolean | ❌ | `false` | Enable compression (qcow2 only) |
| `checksum` | boolean | ❌ | `false` | Generate SHA256 checksum file |

**Example:**
```json
{
  "output_dir": "/home/user/converted-vms",
  "to_output": "my-vm-converted.qcow2",
  "out_format": "qcow2",
  "compress": true,
  "checksum": true
}
```

**Notes:**
- `compress: true` significantly reduces output file size (qcow2 only)
- Compression may increase conversion time
- Checksum file is saved as `<filename>.sha256`

---

### Image Flattening

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `flatten` | boolean | ❌ | `false` | Flatten snapshot chain before conversion |
| `flatten_format` | string | ❌ | `qcow2` | Intermediate format for flattening |

**Example:**
```json
{
  "flatten": true,
  "flatten_format": "qcow2"
}
```

**When to use:**
- VMDKs with snapshot chains
- Complex multi-disk configurations
- When you need a single, consolidated disk image

**Notes:**
- Flattening merges all snapshots into a single image
- Recommended for VMs with multiple snapshots
- May increase processing time for large disks

---

### Filesystem Fixes

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `print_fstab` | boolean | ❌ | `false` | Display /etc/fstab before and after modifications |
| `fstab_mode` | string | ❌ | `none` | Fstab stabilization mode |
| `no_grub` | boolean | ❌ | `false` | Skip GRUB configuration updates |
| `regen_initramfs` | boolean | ❌ | `false` | Regenerate initramfs/initrd |
| `no_backup` | boolean | ❌ | `false` | Skip creating backups inside guest |

**fstab_mode options:**
- `none` - No changes to fstab
- `stabilize-all` - Convert all entries to stable identifiers (UUID/PARTUUID)
- `fix-root` - Fix only root filesystem entry
- `uuid` - Convert to UUID-based entries

**Example:**
```json
{
  "print_fstab": true,
  "fstab_mode": "stabilize-all",
  "no_grub": false,
  "regen_initramfs": true,
  "no_backup": false
}
```

**Notes:**
- `stabilize-all` uses priority: UUID → PARTUUID → LABEL
- `regen_initramfs` automatically detects dracut or update-initramfs
- Backups are stored inside guest at `/root/.h2kvm-backup/`
- GRUB updates fix `root=` kernel parameters

**Best practices:**
- Always use `fstab_mode: "stabilize-all"` for reliable boots
- Enable `regen_initramfs` when changing storage drivers
- Keep `no_backup: false` for safety during testing

---

### Safety & Debugging

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `dry_run` | boolean | ❌ | `false` | Preview changes without applying them |
| `verbose` | integer | ❌ | `0` | Logging verbosity level (0-2) |
| `log_file` | string | ❌ | none | Path to log file |
| `report` | string | ❌ | none | Path to Markdown report file |

**Verbosity levels:**
- `0` - INFO level (normal output)
- `1` - Verbose info (more details)
- `2` - DEBUG level (detailed troubleshooting output)

**Example:**
```json
{
  "dry_run": false,
  "verbose": 2,
  "log_file": "/var/log/h2kvm/conversion.log",
  "report": "/var/log/h2kvm/conversion-report.md"
}
```

**Notes:**
- Use `dry_run: true` to preview what would be changed
- `verbose: 2` recommended for troubleshooting
- Log files capture all debug output
- Reports include step-by-step conversion summary

---

### Working Directory

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `workdir` | string | ❌ | `/tmp/h2kvm-<random>` | Temporary working directory |

**Example:**
```json
{
  "workdir": "/mnt/fast-ssd/h2kvm-work"
}
```

**Notes:**
- Use fast storage (SSD) for better performance
- Requires space approximately equal to source VMDK size
- Automatically cleaned up after successful conversion
- Preserved on error for debugging

---

### Windows-Specific Options

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `virtio_drivers_dir` | string | ❌ | none | Path to extracted VirtIO drivers directory |

**Example:**
```json
{
  "virtio_drivers_dir": "/home/user/virtio-win-extracted"
}
```

**Notes:**
- Required for Windows VM conversions
- Must be an **extracted directory**, NOT an ISO
- Download from: https://fedorapeople.org/groups/virt/virtio-win/
- Drivers are injected offline before first boot

**Steps to prepare VirtIO drivers:**
```bash
# Mount the ISO
mkdir /tmp/virtio-mount
sudo mount -o loop virtio-win.iso /tmp/virtio-mount

# Copy to permanent location
cp -r /tmp/virtio-mount /home/user/virtio-win-extracted

# Unmount
sudo umount /tmp/virtio-mount
```

---

### Validation & Testing

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `libvirt_test` | boolean | ❌ | `false` | Test converted VM with libvirt |
| `qemu_test` | boolean | ❌ | `false` | Test converted VM with direct QEMU |
| `vm_name` | string | ❌ | auto | Name for test VM domain |
| `memory` | integer | ❌ | `2048` | RAM in MB for test VM |
| `vcpus` | integer | ❌ | `2` | Number of vCPUs for test VM |
| `uefi` | boolean | ❌ | `false` | Use UEFI firmware for test |
| `timeout` | integer | ❌ | `60` | Boot timeout in seconds |
| `keep_domain` | boolean | ❌ | `false` | Keep libvirt domain after test |
| `headless` | boolean | ❌ | `true` | Run test without GUI |

**Example:**
```json
{
  "libvirt_test": true,
  "vm_name": "test-converted-vm",
  "memory": 4096,
  "vcpus": 2,
  "uefi": false,
  "timeout": 120,
  "keep_domain": false,
  "headless": true
}
```

**Notes:**
- `libvirt_test` performs smoke test boot validation
- Timeout is how long to wait for successful boot
- `keep_domain: false` automatically cleans up test VM
- UEFI mode requires OVMF firmware package installed

---

## Complete Working Examples

### Example 1: Basic Linux VMDK Conversion

```json
{
  "command": "local",
  "vmdk": "/vms/ubuntu-22.04.vmdk",
  "output_dir": "/output",
  "to_output": "ubuntu-converted.qcow2",
  "out_format": "qcow2",
  "compress": true,
  "checksum": true,
  "fstab_mode": "stabilize-all",
  "regen_initramfs": true,
  "verbose": 1
}
```

### Example 2: Windows 10 with VirtIO Drivers

```json
{
  "command": "local",
  "vmdk": "/vms/windows10.vmdk",
  "output_dir": "/output",
  "out_format": "qcow2",
  "compress": true,
  "virtio_drivers_dir": "/home/user/virtio-win-extracted",
  "libvirt_test": true,
  "memory": 4096,
  "vcpus": 2,
  "timeout": 120,
  "verbose": 2,
  "log_file": "/output/windows10-conversion.log"
}
```

### Example 3: Production Conversion with Full Options

```json
{
  "command": "local",
  "vmdk": "/vms/rhel9-production.vmdk",
  "output_dir": "/output/production",
  "flatten": true,
  "flatten_format": "qcow2",
  "to_output": "rhel9-prod-converted.qcow2",
  "out_format": "qcow2",
  "compress": true,
  "checksum": true,
  "print_fstab": true,
  "fstab_mode": "stabilize-all",
  "no_grub": false,
  "regen_initramfs": true,
  "no_backup": false,
  "workdir": "/fast-storage/workdir",
  "libvirt_test": true,
  "vm_name": "rhel9-prod-test",
  "memory": 8192,
  "vcpus": 4,
  "uefi": true,
  "timeout": 180,
  "keep_domain": false,
  "headless": true,
  "verbose": 2,
  "log_file": "/output/production/conversion.log",
  "report": "/output/production/conversion-report.md"
}
```

### Example 4: Dry Run (Preview Changes)

```json
{
  "command": "local",
  "vmdk": "/vms/test-vm.vmdk",
  "output_dir": "/output/test",
  "fstab_mode": "stabilize-all",
  "regen_initramfs": true,
  "dry_run": true,
  "verbose": 2
}
```

---

## Usage

### Command Line

```bash
# Run with JSON config
h2kvm --config 91-h2kvm-full-config.json local

# Override specific field
h2kvm --config config.json --verbose 2 local

# With environment variables
export WORKDIR=/fast-storage
h2kvm --config config.json local
```

### Validation

Validate JSON syntax before running:

```bash
# Using jq
jq empty 91-h2kvm-full-config.json && echo "Valid JSON"

# Using Python
python -m json.tool 91-h2kvm-full-config.json
```

---

## Troubleshooting

### Common Issues

**"Invalid JSON" error:**
- Validate syntax with `jq` or JSON linter
- Check for trailing commas (not allowed in JSON)
- Ensure all strings are quoted with double quotes

**"File not found" error:**
- Use absolute paths for all file references
- Verify VMDK file exists: `ls -lh /path/to/file.vmdk`
- Check permissions: must be readable by h2kvm user

**"backend failed" error (GuestKit is the default backend):**
- Increase verbosity: `"verbose": 2`
- For GuestKit: ensure `qemu-nbd` and `nbd` kernel module are available
- Review log file for detailed error messages

### Getting Help

For more examples and troubleshooting:
- See `docs/05-YAML-Examples.md`
- See `docs/90-Failure-Modes.md`
- Use YAML format for inline documentation

---

## Converting to YAML

For better readability with comments, convert to YAML:

```bash
# Manual conversion (add comments as you go)
cp 91-h2kvm-full-config.json my-config.yaml

# Edit and add comments:
# This is a YAML comment - helps document your configuration!
command: local   # Conversion mode
vmdk: /path/to/vm.vmdk   # Source virtual disk
```

See `90-h2kvm-full-config.yaml` for the fully-commented YAML equivalent.

---

## Additional Resources

- **[CLI Reference](../docs/04-CLI-Reference.md)** - Complete command-line options
- **[YAML Examples](../docs/05-YAML-Examples.md)** - YAML configuration format
- **[Architecture](../docs/01-Architecture.md)** - Understanding how h2kvm works
- **[Troubleshooting](../docs/90-Failure-Modes.md)** - Common problems and solutions
