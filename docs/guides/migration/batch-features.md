# Batch Migration Features Guide

**Complete Guide to h2kvm's Batch Migration Features**

## Table of Contents

1. [Overview](#overview)
2. [Feature 1: Batch Orchestration](#feature-1-batch-orchestration)
3. [Feature 2: Network & Storage Mapping](#feature-2-network--storage-mapping)
4. [Feature 3: Migration Profiles](#feature-3-migration-profiles)
5. [Feature 4: Pre/Post Conversion Hooks](#feature-4-prepost-conversion-hooks)
6. [Feature 5: Libvirt XML Input](#feature-5-libvirt-xml-input)
7. [Complete Migration Workflows](#complete-migration-workflows)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Overview

h2kvm now includes comprehensive batch migration features for enterprise VM migration workflows. These features enable batch processing, configuration reuse, automation hooks, and libvirt integration.

### Implemented Features

| Feature | Status | Description |
|---------|--------|-------------|
| **Batch Orchestration** | ✅ Complete | Multi-VM parallel conversion with error isolation |
| **Network/Storage Mapping** | ✅ Complete | Source-to-target network and storage transformations |
| **Migration Profiles** | ✅ Complete | Reusable configuration templates with inheritance |
| **Pre/Post Hooks** | ✅ Complete | Automation via shell/Python/HTTP hooks at pipeline stages |
| **Libvirt XML Input** | ✅ Complete | Import existing libvirt VMs via domain XML parsing |
| **Direct Libvirt Integration** | 🚧 Planned | Domain creation and pool management |

### Architecture Principles

All features follow h2kvm's core design:
- **Security-First**: Path validation, timeout enforcement, process isolation
- **Configuration-Driven**: YAML/JSON for all features
- **Composition**: Reuse existing components (ManifestOrchestrator, Config.merge_dicts)
- **Atomic Operations**: Temp file + replace pattern for safety
- **Error Recovery**: Per-VM isolation, continue-on-error support

---

## Feature 1: Batch Orchestration

Convert multiple VMs in parallel with centralized reporting and error handling.

### Overview

Batch orchestration enables migrating many VMs simultaneously:
- Process VMs in parallel (configurable worker limit)
- Per-VM error isolation with continue-on-error
- Priority-based VM ordering
- Aggregate progress reporting
- Batch summary reports (JSON + text)

### Batch Manifest Structure

```json
{
  "batch_version": "1.0",
  "batch_metadata": {
    "batch_id": "migration-2026-01-22",
    "parallel_limit": 4,
    "continue_on_error": true
  },
  "vms": [
    {
      "id": "web-server",
      "manifest": "/work/web-server/manifest.json",
      "priority": 0,
      "enabled": true
    },
    {
      "id": "db-server",
      "manifest": "/work/db-server/manifest.json",
      "priority": 1,
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
# Create batch manifest
cat > batch.json <<EOF
{
  "batch_version": "1.0",
  "batch_metadata": {
    "batch_id": "datacenter-migration",
    "parallel_limit": 8,
    "continue_on_error": true
  },
  "vms": [
    {"manifest": "/work/vm1/manifest.json"},
    {"manifest": "/work/vm2/manifest.json"},
    {"manifest": "/work/vm3/manifest.json"}
  ]
}
EOF

# Run batch conversion
sudo h2kvmctl --batch-manifest batch.json --batch-parallel 4
```

### Output

- **Batch Report**: `/converted/batch_report.json` (aggregate stats, timing)
- **Batch Summary**: `/converted/batch_summary.txt` (human-readable)
- **Individual Reports**: Per-VM conversion reports in each output directory

### CLI Arguments

- `--batch-manifest <path>`: Path to batch manifest JSON/YAML
- `--batch-parallel <n>`: Number of parallel conversions (default: 4)
- `--batch-continue-on-error`: Continue batch even if some VMs fail

### Key Features

- **ThreadPoolExecutor**: Parallel processing using Python ThreadPoolExecutor
- **Priority Ordering**: VMs sorted by priority field (0=highest)
- **Error Isolation**: One VM failure doesn't stop others
- **Progress Tracking**: Rich library progress bars for all conversions
- **Aggregate Stats**: Success rates, timing, fastest/slowest conversions

### Example: Large Datacenter Migration

```bash
# Generate manifests for 100 VMs
for i in {1..100}; do
  cat > /work/vm$i/manifest.json <<EOF
{
  "manifest_version": "1.0",
  "source": {"provider": "vmware", "vm_name": "vm$i"},
  "disks": [{"id": "boot", "local_path": "/vmware/vm$i.vmdk", ...}],
  "output": {"directory": "/converted/vm$i"}
}
EOF
done

# Create batch manifest
cat > datacenter-batch.json <<EOF
{
  "batch_version": "1.0",
  "batch_metadata": {
    "batch_id": "datacenter-full-migration",
    "parallel_limit": 20,
    "continue_on_error": true
  },
  "vms": [
    $(for i in {1..100}; do echo "{\"manifest\": \"/work/vm$i/manifest.json\"},"; done | sed '$ s/,$//')
  ],
  "shared_config": {
    "profile": "production"
  }
}
EOF

# Run with 20 parallel conversions
sudo h2kvmctl --batch-manifest datacenter-batch.json --batch-parallel 20
```

**See**: `examples/batch/` for more examples.

---

## Feature 2: Network & Storage Mapping

Transform source network and storage configurations to target infrastructure.

### Overview

Network and storage mapping enables:
- **Network Mapping**: Translate source networks/port groups to target bridges
- **MAC Address Control**: Preserve, regenerate, or override MAC addresses
- **Storage Mapping**: Map disks to specific pools or directories
- **Format Override**: Force specific output formats (qcow2/raw)

### Network Mapping Configuration

```json
{
  "manifest_version": "1.0",
  "network_mapping": {
    "source_networks": {
      "VM Network": "br0",
      "DMZ Network": "br-dmz",
      "Internal": "br-internal"
    },
    "mac_address_policy": "preserve",
    "mac_address_overrides": {
      "00:50:56:ab:cd:ef": "52:54:00:12:34:56"
    }
  }
}
```

### Storage Mapping Configuration

```json
{
  "manifest_version": "1.0",
  "storage_mapping": {
    "default_pool": "vms",
    "disk_mappings": {
      "boot": "/var/lib/libvirt/images/boot",
      "data": "/mnt/storage/data",
      "logs": "/mnt/fast-ssd/logs"
    },
    "format_override": "qcow2"
  }
}
```

### MAC Address Policies

| Policy | Behavior |
|--------|----------|
| `preserve` | Keep original MAC addresses from source |
| `regenerate` | Generate new random MAC addresses |
| `custom` | Use mac_address_overrides for specific MACs |

### Usage Example

```yaml
manifest_version: "1.0"

source:
  provider: vmware-esxi
  vm_name: web-server

# Map VMware networks to KVM bridges
network_mapping:
  source_networks:
    "VM Network": "br0"
    "DMZ": "br-dmz"
  mac_address_policy: preserve

# Map disks to specific locations
storage_mapping:
  default_pool: "vms"
  disk_mappings:
    boot: "/var/lib/libvirt/images/production"
    data: "/mnt/ssd/vm-data"
  format_override: qcow2

disks:
  - id: boot
    source_format: vmdk
    local_path: /vmware/web-server-boot.vmdk
  - id: data
    source_format: vmdk
    local_path: /vmware/web-server-data.vmdk

output:
  format: qcow2
```

### Integration with Domain Emitter

The MappingApplier is integrated into `domain_emitter.py:263` to automatically apply network mappings when generating libvirt domain XML.

**See**: `examples/batch/network-mapping.yaml` and `examples/batch/storage-mapping.yaml`.

---

## Feature 3: Migration Profiles

Reusable configuration templates with inheritance for consistent VM conversions.

### Overview

Migration profiles provide:
- **7 Built-in Profiles**: production, testing, minimal, fast, windows, archive, debug
- **Profile Inheritance**: Extend existing profiles with `extends` field
- **Custom Profiles**: Create organization-specific profiles
- **Deep Merging**: Override specific settings while inheriting others

### Built-in Profiles

#### production
```yaml
pipeline:
  fix:
    enabled: true
    backup: true
    # grub is auto-handled
    regen_initramfs: true
  convert:
    enabled: true
    compress: true
    compress_level: 6
  validate:
    enabled: true
output:
  format: qcow2
```

#### testing
```yaml
extends: "production"
pipeline:
  convert:
    compress: false
  validate:
    enabled: false
output:
  format: raw
```

#### minimal
```yaml
pipeline:
  fix:
    enabled: true
    regen_initramfs: false
  convert:
    enabled: false
  validate:
    enabled: false
```

#### fast
```yaml
pipeline:
  fix:
    enabled: true
    backup: false
    # grub is auto-handled
    regen_initramfs: false
  convert:
    enabled: true
    compress: false
  validate:
    enabled: false
```

#### windows
```yaml
pipeline:
  fix:
    enabled: false
  convert:
    enabled: true
    compress: true
    compress_level: 6
  validate:
    enabled: true
output:
  format: qcow2
```

#### archive
```yaml
pipeline:
  fix:
    enabled: false
  convert:
    enabled: true
    compress: true
    compress_level: 9
  validate:
    enabled: true
output:
  format: qcow2
```

#### debug
```yaml
pipeline:
  inspect:
    enabled: true
    collect_guest_info: true
  fix:
    enabled: true
    backup: true
    print_fstab: true
  convert:
    enabled: false
  validate:
    enabled: true
```

### Using Profiles in Manifests

```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "profile_overrides": {
    "pipeline": {
      "convert": {
        "compress_level": 9
      }
    }
  },
  "source": {...},
  "disks": [...]
}
```

### Creating Custom Profiles

```yaml
# /etc/h2kvm/profiles/organization.yaml
extends: "production"

pipeline:
  fix:
    fstab_mode: "stabilize-all"
    remove_vmware_tools: true
  convert:
    compress_level: 8

hooks:
  post_convert:
    - type: http
      url: "https://monitoring.example.com/api/conversions"
      method: POST
```

Use custom profile:

```json
{
  "manifest_version": "1.0",
  "profile": "organization",
  "custom_profile_path": "/etc/h2kvm/profiles",
  "source": {...}
}
```

### Profile Inheritance Chain

```
organization
  ↓ extends
production
  ↓ (merged with profile_overrides)
Final Configuration
```

**See**: `h2kvm/profiles/README.md` and `examples/batch/batch-with-profiles.yaml`.

---

## Feature 4: Pre/Post Conversion Hooks

Execute custom scripts, Python functions, or HTTP webhooks at pipeline stages.

### Overview

Hooks enable automation:
- **7 Hook Stages**: Execute at pre/post extraction, fix, convert, validate
- **3 Hook Types**: Script (shell), Python (function calls), HTTP (webhooks)
- **Template Variables**: {{ variable }} substitution with 15+ context vars
- **Error Handling**: continue_on_error, timeout enforcement
- **Security**: Path validation, process isolation

### Hook Stages

| Stage | When | Use Case |
|-------|------|----------|
| `pre_extraction` | Before manifest load | Send start notification |
| `post_extraction` | After manifest load | Validate source disks |
| `pre_fix` | Before offline fixes | Create backup |
| `post_fix` | After fixes | Verify boot configuration |
| `pre_convert` | Before conversion | Check disk space |
| `post_convert` | After conversion | Verify output integrity |
| `post_validate` | After validation | Update inventory, cleanup |

### Hook Types

#### Script Hook

```json
{
  "type": "script",
  "path": "/scripts/backup-vm.sh",
  "args": ["{{ source_path }}", "/backups/{{ vm_name }}"],
  "env": {
    "VM_NAME": "{{ vm_name }}",
    "OUTPUT_PATH": "{{ output_path }}"
  },
  "timeout": 600,
  "continue_on_error": false,
  "working_directory": "/tmp"
}
```

#### Python Hook

```json
{
  "type": "python",
  "module": "migration_validators",
  "function": "verify_disk_integrity",
  "args": {
    "disk_path": "{{ output_path }}",
    "expected_format": "qcow2"
  },
  "timeout": 300,
  "continue_on_error": false
}
```

#### HTTP Hook

```json
{
  "type": "http",
  "url": "https://api.example.com/migrations",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer TOKEN",
    "Content-Type": "application/json"
  },
  "body": {
    "vm_name": "{{ vm_name }}",
    "stage": "{{ stage }}",
    "status": "completed",
    "output": "{{ output_path }}"
  },
  "timeout": 30,
  "continue_on_error": true
}
```

### Template Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `vm_name` | "web-server" | VM name from manifest |
| `source_path` | "/data/vm.vmdk" | Boot disk source path |
| `output_path` | "/converted/boot.qcow2" | Converted disk path |
| `stage` | "post_convert" | Current pipeline stage |
| `timestamp` | 1737547200 | Unix timestamp |
| `timestamp_iso` | "2026-01-22T10:00:00Z" | ISO 8601 timestamp |
| `user` | "root" | Current user |
| `hostname` | "migration-host" | System hostname |
| `manifest_path` | "/work/manifest.json" | Manifest file path |

### Complete Example

```json
{
  "manifest_version": "1.0",
  "hooks": {
    "pre_extraction": [
      {
        "type": "script",
        "path": "/scripts/notify-start.sh",
        "env": {"VM": "{{ vm_name }}"},
        "timeout": 60
      }
    ],
    "pre_fix": [
      {
        "type": "script",
        "path": "/scripts/backup-disk.sh",
        "args": ["{{ source_path }}", "/backups"],
        "timeout": 1800
      }
    ],
    "post_convert": [
      {
        "type": "python",
        "module": "validators",
        "function": "verify_qcow2",
        "args": {"disk": "{{ output_path }}"}
      },
      {
        "type": "http",
        "url": "https://tracker.example.com/api/status",
        "method": "POST",
        "body": {
          "vm": "{{ vm_name }}",
          "completed": "{{ timestamp_iso }}"
        }
      }
    ]
  },
  "source": {...},
  "disks": [...]
}
```

**See**: `examples/hooks/` for comprehensive examples and sample scripts.

---

## Feature 5: Libvirt XML Input

Import existing libvirt/KVM VMs by parsing domain XML files.

### Overview

The libvirt-xml extractor:
- Parses libvirt domain XML files
- Extracts disk paths, formats, sizes
- Detects firmware type (BIOS/UEFI)
- Extracts network configuration
- Captures memory/CPU settings
- Generates Artifact Manifest v1

### Usage

```bash
# Create config for libvirt-xml mode
cat > config.yaml <<EOF
cmd: libvirt-xml
output_dir: /work/converted
EOF

# Parse domain XML
sudo h2kvmctl \\
  --config config.yaml \\
  --libvirt-xml /etc/libvirt/qemu/my-vm.xml

# Generated: /work/converted/manifest.json
```

### Extract from Running VM

```bash
# Dump XML from running VM
virsh dumpxml my-vm > /tmp/my-vm.xml

# Parse it
sudo h2kvmctl \\
  --config <(echo "cmd: libvirt-xml\noutput_dir: /work") \\
  --libvirt-xml /tmp/my-vm.xml

# Convert using generated manifest
sudo h2kvmctl --config /work/manifest.json
```

### Firmware Detection

UEFI detected when:
- `<loader type="pflash">` present
- `<os firmware="efi">` set
- Loader path contains "OVMF"

Otherwise defaults to BIOS.

### OS Distro Detection

Attempts to extract from libosinfo metadata:
- `<metadata><libosinfo:os id="http://redhat.com/rhel/9.0">`
- Parses for: rhel, ubuntu, debian, centos, fedora

### Network Configuration Extraction

Captures per interface:
- Type (bridge, network)
- Source (bridge name or network name)
- MAC address
- Model (virtio, e1000, etc.)

### Generated Manifest

```json
{
  "manifest_version": "1.0",
  "source": {
    "provider": "libvirt",
    "vm_id": "domain-uuid",
    "vm_name": "web-server",
    "libvirt_xml_path": "/etc/libvirt/qemu/web-server.xml"
  },
  "disks": [
    {
      "id": "vda",
      "source_format": "qcow2",
      "local_path": "/var/lib/libvirt/images/boot.qcow2",
      "bytes": 107374182400,
      "checksum": "sha256:abc123...",
      "boot_order_hint": 0,
      "disk_type": "boot"
    }
  ],
  "firmware": {"type": "uefi"},
  "os_hint": "rhel9",
  "metadata": {
    "networks": [
      {"type": "bridge", "source": "br0", "mac": "52:54:00:6b:3c:58"}
    ],
    "memory_bytes": 8589934592,
    "vcpus": 4
  },
  "pipeline": {...},
  "output": {...}
}
```

**See**: `examples/libvirt-xml/` for sample domain XMLs and workflows.

---

## Complete Migration Workflows

### Workflow 1: Simple Batch Migration

```bash
# 1. Create manifests for each VM
for vm in vm1 vm2 vm3; do
  cat > /work/$vm/manifest.json <<EOF
{
  "manifest_version": "1.0",
  "profile": "production",
  "source": {"provider": "vmware", "vm_name": "$vm"},
  "disks": [{"id": "boot", "local_path": "/vmware/$vm.vmdk", ...}],
  "output": {"directory": "/converted/$vm"}
}
EOF
done

# 2. Create batch manifest
cat > batch.json <<EOF
{
  "batch_version": "1.0",
  "batch_metadata": {"parallel_limit": 3},
  "vms": [
    {"manifest": "/work/vm1/manifest.json"},
    {"manifest": "/work/vm2/manifest.json"},
    {"manifest": "/work/vm3/manifest.json"}
  ]
}
EOF

# 3. Run batch
sudo h2kvmctl --batch-manifest batch.json
```

### Workflow 2: Profile-Based with Hooks

```bash
# 1. Create manifest with profile and hooks
cat > manifest.json <<EOF
{
  "manifest_version": "1.0",
  "profile": "production",
  "hooks": {
    "pre_fix": [{
      "type": "script",
      "path": "/scripts/backup.sh",
      "args": ["{{ source_path }}", "/backups"]
    }],
    "post_convert": [{
      "type": "http",
      "url": "https://api.example.com/notify",
      "method": "POST",
      "body": {"vm": "{{ vm_name }}", "status": "done"}
    }]
  },
  "source": {...},
  "disks": [...]
}
EOF

# 2. Run conversion
sudo h2kvmctl --config manifest.json
```

### Workflow 3: Libvirt Import + Batch

```bash
# 1. Extract manifests from libvirt VMs
for vm in $(virsh list --name --all); do
  virsh dumpxml $vm > /tmp/${vm}.xml
  sudo h2kvmctl \\
    --config <(echo "cmd: libvirt-xml\noutput_dir: /work/$vm") \\
    --libvirt-xml /tmp/${vm}.xml
done

# 2. Create batch from generated manifests
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
sudo h2kvmctl --batch-manifest batch.json
```

### Workflow 4: Network Mapping Migration

```bash
# 1. Create manifest with network mapping
cat > manifest.yaml <<EOF
manifest_version: "1.0"
profile: production

network_mapping:
  source_networks:
    "VM Network": "br0"
    "DMZ": "br-dmz"
  mac_address_policy: preserve

source:
  provider: vmware
  vm_name: web-server

disks:
  - id: boot
    local_path: /vmware/web-server.vmdk

output:
  directory: /converted
EOF

# 2. Convert
sudo h2kvmctl --config manifest.yaml
```

---

## Best Practices

### Batch Conversion

1. **Start Small**: Test with 2-3 VMs before large batches
2. **Use Priorities**: Set priority for critical VMs
3. **Monitor Resources**: Limit parallel_limit based on available CPU/RAM/disk I/O
4. **Enable continue_on_error**: For non-critical batches to maximize throughput
5. **Check Reports**: Review batch_report.json for failures before cleanup

### Profiles

1. **Use Built-in Profiles**: Start with production/testing profiles
2. **Create Organization Profile**: Extend built-in profiles for consistency
3. **Test Profile Changes**: Use minimal/debug profiles for testing
4. **Version Control**: Store custom profiles in git
5. **Document Overrides**: Comment why profile_overrides are needed

### Hooks

1. **Test Hooks Independently**: Run scripts/functions manually before adding to manifest
2. **Use continue_on_error**: For non-critical hooks (notifications, metrics)
3. **Set Appropriate Timeouts**: Allow extra time for backup/validation hooks
4. **Log Hook Output**: Capture stdout/stderr for debugging
5. **Secure Credentials**: Use environment variables or secret management for HTTP hooks

### Network Mapping

1. **Document Mappings**: Maintain mapping documentation for teams
2. **Validate Bridge Names**: Ensure target bridges exist before conversion
3. **MAC Address Policy**: Use "preserve" for production, "regenerate" for test environments
4. **Test Mappings**: Verify network connectivity after conversion

### Libvirt Import

1. **Skip Checksums for Speed**: Use `--no-compute-checksums` for large disks
2. **Verify Disk Paths**: Ensure all referenced disks exist
3. **Review Generated Manifest**: Check and customize before conversion
4. **Update Metadata**: Add organization-specific metadata to generated manifests

---

## Troubleshooting

### Batch Issues

**Problem**: Batch fails immediately

**Solution**:
- Check batch manifest syntax (valid JSON/YAML)
- Verify all VM manifest paths exist
- Check batch_version is "1.0"

**Problem**: Some VMs fail in batch

**Solution**:
- Check `/converted/batch_summary.txt` for error details
- Review individual VM reports in output directories
- Use `--batch-continue-on-error` to complete batch despite failures

### Hook Issues

**Problem**: Hook not executing

**Solution**:
- Verify hook is in correct stage (e.g., "pre_fix" not "prefix")
- Check script path exists and is executable
- For Python hooks, verify module is importable
- Check h2kvm logs for hook execution messages

**Problem**: Hook timing out

**Solution**:
- Increase timeout value in hook config
- Test hook independently to identify performance issues
- Use `continue_on_error: true` for non-critical hooks

### Profile Issues

**Problem**: Profile not found

**Solution**:
- Check profile name matches built-in profiles exactly
- For custom profiles, verify `custom_profile_path` is correct
- Ensure custom profile file has `.yaml` extension

**Problem**: Profile overrides not applying

**Solution**:
- Verify `profile_overrides` structure matches manifest schema
- Check for typos in override paths
- Review merged config with `--dump-config` flag

### Libvirt XML Issues

**Problem**: "No disks found in domain XML"

**Solution**:
- Verify XML contains `<disk device="disk">` elements (not cdrom/floppy)
- Check disk source paths are specified
- Ensure disks actually exist at specified paths

**Problem**: Parse errors

**Solution**:
- Validate XML: `xmllint --noout domain.xml`
- Check XML is complete (not truncated)
- Ensure XML encoding is UTF-8

---

## Summary

h2kvm now provides enterprise-grade batch migration capabilities:

✅ **83% Implementation Complete** (5 of 6 phases)
✅ **Production Ready**: Batch orchestration, profiles, hooks, libvirt import
✅ **Fully Documented**: Comprehensive examples and guides
✅ **Security Hardened**: Path validation, timeouts, process isolation

**Next**: Phase 6 (Direct Libvirt Integration) for automatic domain creation and pool management.

**Questions?** See individual feature READMEs in `examples/` directories.
