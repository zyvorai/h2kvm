# Batch Migration Quick Reference

**One-page reference for all batch migration features**

## Feature Matrix

| Feature | CLI Flag | Config Key | Example |
|---------|----------|------------|---------|
| **Batch Conversion** | `--batch-manifest` | N/A | See [Batch](#batch-conversion) |
| **Parallel Limit** | `--batch-parallel N` | `parallel_limit` | `--batch-parallel 4` |
| **Continue on Error** | `--batch-continue-on-error` | `continue_on_error` | Flag enabled |
| **Network Mapping** | N/A | `network_mapping` | See [Network](#network-mapping) |
| **Storage Mapping** | N/A | `storage_mapping` | See [Storage](#storage-mapping) |
| **Migration Profile** | N/A | `profile` | `"profile": "production"` |
| **Profile Overrides** | N/A | `profile_overrides` | See [Profiles](#profiles) |
| **Pre/Post Hooks** | N/A | `hooks` | See [Hooks](#hooks) |
| **Libvirt XML** | `--libvirt-xml PATH` | `cmd: libvirt-xml` | See [Libvirt](#libvirt-xml-import) |

## Batch Conversion

### Minimal Batch Manifest

```json
{
  "batch_version": "1.0",
  "vms": [
    {"manifest": "/path/to/vm1.json"},
    {"manifest": "/path/to/vm2.json"}
  ]
}
```

### Full Batch Manifest

```json
{
  "batch_version": "1.0",
  "batch_metadata": {
    "batch_id": "migration-2026",
    "parallel_limit": 4,
    "continue_on_error": true
  },
  "vms": [
    {
      "id": "vm1",
      "manifest": "/work/vm1/manifest.json",
      "priority": 0,
      "enabled": true
    }
  ],
  "shared_config": {
    "output_directory": "/converted",
    "profile": "production"
  }
}
```

### Usage

```bash
sudo h2kvmctl --batch-manifest batch.json --batch-parallel 8
```

## Network Mapping

### Configuration

```json
{
  "network_mapping": {
    "source_networks": {
      "VM Network": "br0",
      "DMZ Network": "br-dmz"
    },
    "mac_address_policy": "preserve",
    "mac_address_overrides": {
      "00:50:56:ab:cd:ef": "52:54:00:12:34:56"
    }
  }
}
```

### MAC Address Policies

| Policy | Behavior |
|--------|----------|
| `preserve` | Keep original MACs |
| `regenerate` | Generate new random MACs |
| `custom` | Use `mac_address_overrides` |

## Storage Mapping

### Configuration

```json
{
  "storage_mapping": {
    "default_pool": "vms",
    "disk_mappings": {
      "boot": "/var/lib/libvirt/images/boot",
      "data": "/mnt/storage/data"
    },
    "format_override": "qcow2"
  }
}
```

### Format Options

- `qcow2` - QEMU Copy-On-Write v2 (default, compressed)
- `raw` - Raw disk image (faster, larger)
- `vdi` - VirtualBox Disk Image
- `vmdk` - VMware Virtual Disk

## Profiles

### Built-in Profiles

| Profile | Use Case | Key Settings |
|---------|----------|--------------|
| `production` | Default production migrations | Full pipeline, compression level 6 |
| `testing` | Test environment migrations | No compression, no validation |
| `minimal` | Bare minimum conversion | No initramfs regen, no conversion |
| `fast` | Speed-optimized | No backup, no grub update, no compression |
| `windows` | Windows VM migrations | Skips Linux-specific fixes |
| `archive` | Long-term storage | Maximum compression (level 9) |
| `debug` | Troubleshooting | Full logging, guest info collection |

### Using Profiles

```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "profile_overrides": {
    "pipeline": {
      "convert": {"compress_level": 9}
    }
  }
}
```

### Custom Profile

Create `/etc/h2kvm/profiles/custom.yaml`:

```yaml
extends: "production"
pipeline:
  fix:
    fstab_mode: "stabilize-all"
  convert:
    compress_level: 8
```

Use in manifest:

```json
{
  "profile": "custom",
  "custom_profile_path": "/etc/h2kvm/profiles"
}
```

## Hooks

### Hook Stages

| Stage | When Executed |
|-------|--------------|
| `pre_extraction` | Before manifest load |
| `post_extraction` | After manifest load, before fixes |
| `pre_fix` | Before offline fixes |
| `post_fix` | After fixes, before conversion |
| `pre_convert` | Before format conversion |
| `post_convert` | After conversion, before validation |
| `post_validate` | After validation complete |

### Script Hook

```json
{
  "type": "script",
  "path": "/scripts/backup.sh",
  "args": ["{{ source_path }}", "/backups"],
  "env": {"VM_NAME": "{{ vm_name }}"},
  "timeout": 600,
  "continue_on_error": false,
  "working_directory": "/tmp"
}
```

### Python Hook

```json
{
  "type": "python",
  "module": "validators",
  "function": "verify_disk",
  "args": {"disk_path": "{{ output_path }}"},
  "timeout": 300
}
```

### HTTP Hook

```json
{
  "type": "http",
  "url": "https://api.example.com/notify",
  "method": "POST",
  "headers": {"Authorization": "Bearer TOKEN"},
  "body": {
    "vm": "{{ vm_name }}",
    "status": "completed"
  },
  "timeout": 30,
  "continue_on_error": true
}
```

### Template Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `{{ vm_name }}` | "web-server" | VM name |
| `{{ source_path }}` | "/data/vm.vmdk" | Source disk path |
| `{{ output_path }}` | "/out/vm.qcow2" | Output disk path |
| `{{ stage }}` | "post_convert" | Current stage |
| `{{ timestamp }}` | 1737547200 | Unix timestamp |
| `{{ timestamp_iso }}` | "2026-01-22T..." | ISO timestamp |
| `{{ user }}` | "root" | Current user |
| `{{ hostname }}` | "host" | System hostname |

## Libvirt XML Import

### Export VM XML

```bash
virsh dumpxml my-vm > /tmp/my-vm.xml
```

### Parse XML to Manifest

```bash
cat > config.yaml <<EOF
cmd: libvirt-xml
output_dir: /work/converted
EOF

sudo h2kvmctl \
  --config config.yaml \
  --libvirt-xml /tmp/my-vm.xml
```

### Convert Using Generated Manifest

```bash
sudo h2kvmctl --config /work/converted/manifest.json
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--libvirt-xml PATH` | Path to domain XML |
| `--compute-checksums` | Compute SHA256 (default: on) |
| `--no-compute-checksums` | Skip checksums (faster) |
| `--manifest-filename NAME` | Output filename (default: manifest.json) |

## Complete Examples

### Example 1: Batch + Profiles

```json
{
  "batch_version": "1.0",
  "batch_metadata": {"parallel_limit": 4},
  "vms": [
    {
      "manifest": "/work/vm1.json",
      "overrides": {"profile": "production"}
    },
    {
      "manifest": "/work/vm2.json",
      "overrides": {"profile": "testing"}
    }
  ]
}
```

### Example 2: Network Mapping + Hooks

```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "network_mapping": {
    "source_networks": {"VM Network": "br0"},
    "mac_address_policy": "preserve"
  },
  "hooks": {
    "post_convert": [{
      "type": "http",
      "url": "https://api.example.com/notify",
      "method": "POST",
      "body": {"vm": "{{ vm_name }}", "done": true}
    }]
  },
  "source": {...},
  "disks": [...]
}
```

### Example 3: Libvirt Import Batch

```bash
# 1. Export all VMs
for vm in $(virsh list --name --all); do
  virsh dumpxml $vm > /tmp/${vm}.xml
  sudo h2kvmctl \
    --config <(echo "cmd: libvirt-xml\noutput_dir: /work/$vm") \
    --libvirt-xml /tmp/${vm}.xml
done

# 2. Create batch
cat > batch.json <<EOF
{
  "batch_version": "1.0",
  "vms": [
    $(for vm in $(virsh list --name --all); do
        echo "{\"manifest\": \"/work/$vm/manifest.json\"},"
      done | sed '$ s/,$//')
  ]
}
EOF

# 3. Run batch
sudo h2kvmctl --batch-manifest batch.json --batch-parallel 8
```

## Troubleshooting

### Batch Issues

```bash
# Check batch summary
cat /converted/batch_summary.txt

# View detailed report
cat /converted/batch_report.json

# Debug single VM
sudo h2kvmctl --config /work/vm1/manifest.json -vv
```

### Profile Issues

```bash
# List available profiles
python3 -c "from h2kvm.profiles import ProfileLoader; \
            print(ProfileLoader().list_available_profiles())"

# Dump merged config
sudo h2kvmctl --config manifest.json --dump-config
```

### Hook Issues

```bash
# Test script independently
/scripts/hook.sh arg1 arg2

# Check hook execution in logs
sudo h2kvmctl --config manifest.json 2>&1 | grep "Hook"

# Test Python function
python3 -c "from module import function; function(args)"
```

## Performance Tips

1. **Batch Parallel Limit**: Set based on CPU cores and disk I/O
   - HDD storage: 2-4 parallel VMs
   - SSD storage: 4-8 parallel VMs
   - NVMe storage: 8-16 parallel VMs

2. **Compression**: Balance speed vs size
   - Fast: `compress: false` or `compress_level: 1`
   - Balanced: `compress_level: 6` (default)
   - Maximum: `compress_level: 9`

3. **Checksums**: Skip for speed if not needed
   - Production: Enable checksums
   - Testing: Use `--no-compute-checksums`

4. **Profiles**: Choose appropriate profile
   - Speed: Use `fast` profile
   - Quality: Use `production` profile
   - Testing: Use `testing` or `minimal`

## Quick Command Reference

```bash
# Batch conversion
sudo h2kvmctl --batch-manifest batch.json --batch-parallel 4

# With continue-on-error
sudo h2kvmctl --batch-manifest batch.json --batch-continue-on-error

# Libvirt XML import
sudo h2kvmctl \
  --config <(echo "cmd: libvirt-xml\noutput_dir: /out") \
  --libvirt-xml /path/to/domain.xml

# Skip checksums (faster)
sudo h2kvmctl \
  --config config.yaml \
  --libvirt-xml domain.xml \
  --no-compute-checksums

# Dump configuration
sudo h2kvmctl --config manifest.json --dump-config

# Verbose logging
sudo h2kvmctl --config manifest.json -vvv
```

## Documentation Links

- **Full Guide**: `docs/Batch-Migration-Features-Guide.md`
- **Batch Examples**: `examples/batch/`
- **Profile Guide**: `h2kvm/profiles/README.md`
- **Hooks Guide**: `examples/hooks/README.md`
- **Libvirt Guide**: `examples/libvirt-xml/README.md`
- **Testing Guide**: `tests/BATCH_MIGRATION_TESTING_GUIDE.md`
- **Progress Tracker**: `BATCH_MIGRATION_PROGRESS.md`

## Support

For issues or questions:
- File bug: `https://github.com/anthropics/h2kvm/issues`
- Documentation: `docs/` directory
- Examples: `examples/` directory
