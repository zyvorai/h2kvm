# Manifest-Driven Workflow

## Overview

The manifest-driven workflow provides a **declarative, reproducible, and auditable** approach to VM migrations. Instead of passing dozens of CLI arguments, you define your entire migration pipeline in a single JSON manifest file.

### Key Benefits

- **Declarative Configuration**: Define the entire pipeline in a single JSON file
- **Version Control**: Store manifests in git for audit trails and repeatability
- **Batch Processing**: Process multiple VMs with consistent configuration
- **Structured Reporting**: Generate machine-readable `report.json` with per-stage results
- **Stage Control**: Enable/disable specific pipeline stages as needed
- **CI/CD Integration**: Easy integration with automation systems

## Quick Start

### 1. Create a Manifest

Create `migration.json`:

```json
{
  "version": "1.0",
  "metadata": {
    "name": "production-webserver",
    "description": "Migrate production web server from VMware to KVM"
  },
  "source": {
    "type": "vmdk",
    "path": "/data/vms/webserver/disk.vmdk"
  },
  "output": {
    "directory": "/data/output/webserver",
    "format": "qcow2"
  },
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {"enabled": true},
    "convert": {"enabled": true},
    "validate": {"enabled": true}
  }
}
```

### 2. Run the Pipeline

```bash
hyper2kvm --manifest migration.json
```

### 3. Review Results

The pipeline generates `report.json` with detailed results:

```json
{
  "version": "1.0",
  "timestamp": "2026-01-21T18:23:32.808096",
  "pipeline": {
    "success": true,
    "duration_seconds": 245.67,
    "stages": {
      "load_manifest": {"success": true, "duration": 0.01},
      "inspect": {"success": true, "duration": 2.34},
      "fix": {"success": true, "duration": 120.45},
      "convert": {"success": true, "duration": 118.32},
      "validate": {"success": true, "duration": 4.55}
    }
  },
  "artifacts": [
    {
      "type": "converted_image",
      "path": "/data/output/webserver/webserver.qcow2",
      "format": "qcow2",
      "size_bytes": 10737418240,
      "size_human": "10.00 GiB"
    }
  ],
  "summary": {
    "total_stages": 5,
    "successful_stages": 5,
    "failed_stages": 0,
    "total_warnings": 0,
    "total_errors": 0,
    "total_artifacts": 1
  }
}
```

## Manifest Schema Reference

### Top-Level Structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Manifest schema version (currently "1.0") |
| `metadata` | object | No | Descriptive metadata about this migration |
| `source` | object | Yes | Source disk configuration |
| `output` | object | Yes | Output configuration |
| `pipeline` | object | Yes | Pipeline stages configuration |
| `configuration` | object | No | Guest OS configuration injection |
| `options` | object | No | Global options (dry-run, verbosity, etc.) |

### Metadata Section

```json
{
  "metadata": {
    "name": "production-webserver",
    "description": "Migrate production web server from VMware to KVM",
    "tags": ["production", "web", "linux"],
    "owner": "ops-team",
    "created": "2026-01-21"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable name for this migration |
| `description` | string | Detailed description |
| `tags` | array | Tags for organization and filtering |
| `owner` | string | Team or person responsible |
| `created` | string | Creation date |

### Source Section

```json
{
  "source": {
    "type": "vmdk",
    "path": "/data/vms/disk.vmdk"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Source disk type: `vmdk`, `ova`, `ovf`, `vhd`, `qcow2`, `raw` |
| `path` | string | Yes | Absolute or relative path to source disk |

**Supported Source Types:**
- `vmdk` - VMware virtual disk (descriptor or flat)
- `ova` - VMware OVA archive
- `ovf` - VMware OVF bundle
- `vhd` - Hyper-V virtual disk
- `qcow2` - QEMU/KVM disk image
- `raw` - Raw disk image

### Output Section

```json
{
  "output": {
    "directory": "/data/output/webserver",
    "format": "qcow2",
    "filename": "webserver-migrated.qcow2"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `directory` | string | Yes | Output directory (created if doesn't exist) |
| `format` | string | No | Output format: `qcow2` (default), `raw`, `vdi` |
| `filename` | string | No | Output filename (auto-generated if not specified) |

### Pipeline Section

The pipeline defines the execution flow with 5 stages:

```
LOAD_MANIFEST → INSPECT → FIX → CONVERT → VALIDATE
```

Each stage can be enabled/disabled independently:

```json
{
  "pipeline": {
    "inspect": {
      "enabled": true,
      "collect_guest_info": false
    },
    "fix": {
      "enabled": true,
      "backup": true,
      "print_fstab": false,
      "update_grub": true,
      "regen_initramfs": true,
      "fstab_mode": "stabilize-all",
      "remove_vmware_tools": false
    },
    "convert": {
      "enabled": true,
      "compress": false,
      "compress_level": null
    },
    "validate": {
      "enabled": true,
      "check_image_integrity": true
    }
  }
}
```

#### Stage: INSPECT

Gathers information about the source disk.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | - | Enable/disable this stage |
| `collect_guest_info` | boolean | false | Use guestfs backend to inspect guest OS details |

**Output:**
- Source path and existence check
- File size (bytes and human-readable)
- Guest OS information (if `collect_guest_info: true`)

#### Stage: FIX

Applies offline fixes to the guest filesystem to prepare for KVM.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | - | Enable/disable this stage |
| `backup` | boolean | true | Create backups before modifications |
| `print_fstab` | boolean | false | Print /etc/fstab before and after |
| `update_grub` | boolean | true | Update GRUB configuration |
| `regen_initramfs` | boolean | true | Regenerate initramfs with virtio drivers |
| `fstab_mode` | string | "stabilize-all" | fstab rewrite mode (see below) |
| `remove_vmware_tools` | boolean | false | Remove VMware tools packages |

**fstab_mode Options:**
- `stabilize-all` (recommended): Convert all mounts to /dev/disk/by-uuid
- `bypath-only`: Only convert /dev/sd* to /dev/disk/by-path
- `noop`: Don't modify /etc/fstab

**What Gets Fixed:**
- `/etc/fstab` - Stabilize mount points using UUIDs
- GRUB configuration - Update `root=` parameter and regenerate config
- Initramfs - Add virtio drivers for KVM compatibility
- Network configuration - Remove VMware-specific settings
- VMware tools - Optional removal

#### Stage: CONVERT

Converts the disk image to the target format.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | - | Enable/disable this stage |
| `compress` | boolean | false | Enable qcow2 compression (qcow2 only) |
| `compress_level` | integer | null | Compression level 1-9 (qcow2 only) |

**Supported Formats:**
- `qcow2` - QEMU Copy-On-Write (default, supports compression)
- `raw` - Raw disk image (no compression)
- `vdi` - VirtualBox disk image

#### Stage: VALIDATE

Validates the output image integrity.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | - | Enable/disable this stage |
| `check_image_integrity` | boolean | true | Verify image can be opened by qemu-img |

### Configuration Section

Inject runtime configuration into the guest OS filesystem (Linux only).

```json
{
  "configuration": {
    "users": {
      "create": [
        {
          "name": "sysadmin",
          "uid": 1001,
          "password": "secure-hash-here",
          "groups": ["wheel", "docker"],
          "shell": "/bin/bash",
          "ssh_authorized_keys": [
            "ssh-rsa AAAAB3... user@host"
          ]
        }
      ]
    },
    "services": {
      "enable": ["sshd", "docker"],
      "disable": ["vmware-tools"]
    },
    "hostname": {
      "hostname": "webserver01",
      "domain": "example.com",
      "hosts": [
        {"ip": "127.0.0.1", "hostname": "localhost"},
        {"ip": "10.0.0.10", "hostname": "webserver01.example.com webserver01"}
      ]
    },
    "network": {
      "systemd_networkd": [
        {
          "filename": "10-eth0.network",
          "content": "[Match]\nName=eth0\n\n[Network]\nAddress=10.0.0.10/24\nGateway=10.0.0.1\nDNS=8.8.8.8\n"
        }
      ]
    }
  }
}
```

**See Also:**
- [Priority-1-Features.md](Priority-1-Features.md) - Full documentation for configuration injection

### Options Section

Global runtime options.

```json
{
  "options": {
    "dry_run": false,
    "verbose": 2,
    "report": {
      "enabled": true,
      "path": "report.json"
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `dry_run` | boolean | false | Don't modify guest or write output |
| `verbose` | integer | 1 | Verbosity level (0=quiet, 1=normal, 2=verbose) |
| `report.enabled` | boolean | true | Generate report.json |
| `report.path` | string | "report.json" | Report filename (relative to output directory) |

## Report Format

The pipeline generates `report.json` with structured results.

### Report Structure

```json
{
  "version": "1.0",
  "timestamp": "2026-01-21T18:23:32.808096",
  "pipeline": {
    "success": true,
    "duration_seconds": 245.67,
    "stages": { /* stage results */ }
  },
  "artifacts": [ /* generated files */ ],
  "warnings": [ /* non-fatal issues */ ],
  "errors": [ /* fatal issues */ ],
  "summary": { /* aggregated stats */ }
}
```

### Stage Results

Each stage records:

```json
{
  "success": true,
  "duration": 120.45,
  "result": {
    /* stage-specific output */
  }
}
```

**On Failure:**

```json
{
  "success": false,
  "duration": 10.23,
  "error": "Error message here"
}
```

### Artifacts

Tracks generated files:

```json
{
  "artifacts": [
    {
      "type": "converted_image",
      "path": "/data/output/webserver/webserver.qcow2",
      "format": "qcow2",
      "size_bytes": 10737418240,
      "size_human": "10.00 GiB",
      "compressed": false
    }
  ]
}
```

### Warnings and Errors

```json
{
  "warnings": [
    {
      "stage": "fix",
      "message": "Could not remove VMware tools: package not found",
      "timestamp": "2026-01-21T18:25:15.123456"
    }
  ],
  "errors": [
    {
      "stage": "convert",
      "message": "Insufficient disk space",
      "timestamp": "2026-01-21T18:27:32.654321"
    }
  ]
}
```

## Complete Examples

### Example 1: Basic Migration

Minimal manifest for a simple VMDK → qcow2 conversion:

```json
{
  "version": "1.0",
  "metadata": {
    "name": "simple-migration"
  },
  "source": {
    "type": "vmdk",
    "path": "/data/source/disk.vmdk"
  },
  "output": {
    "directory": "/data/output",
    "format": "qcow2"
  },
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {"enabled": true},
    "convert": {"enabled": true},
    "validate": {"enabled": true}
  }
}
```

### Example 2: Production Server with User Injection

Complete production migration with user account creation:

```json
{
  "version": "1.0",
  "metadata": {
    "name": "production-webserver-migration",
    "description": "Migrate production web server from VMware to KVM",
    "owner": "ops-team",
    "tags": ["production", "web", "linux"]
  },
  "source": {
    "type": "vmdk",
    "path": "/data/vmware/webserver/disk.vmdk"
  },
  "output": {
    "directory": "/data/kvm/webserver",
    "format": "qcow2",
    "filename": "webserver-prod.qcow2"
  },
  "pipeline": {
    "inspect": {
      "enabled": true,
      "collect_guest_info": true
    },
    "fix": {
      "enabled": true,
      "backup": true,
      "update_grub": true,
      "regen_initramfs": true,
      "fstab_mode": "stabilize-all",
      "remove_vmware_tools": true
    },
    "convert": {
      "enabled": true,
      "compress": true,
      "compress_level": 6
    },
    "validate": {
      "enabled": true,
      "check_image_integrity": true
    }
  },
  "configuration": {
    "users": {
      "create": [
        {
          "name": "ansible",
          "uid": 1001,
          "password": "$6$rounds=656000$...",
          "groups": ["wheel"],
          "shell": "/bin/bash",
          "ssh_authorized_keys": [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ... ansible@controller"
          ]
        }
      ]
    },
    "services": {
      "enable": ["sshd", "nginx", "docker"],
      "disable": ["vmware-tools", "open-vm-tools"]
    },
    "hostname": {
      "hostname": "webserver01",
      "domain": "prod.example.com",
      "hosts": [
        {"ip": "127.0.0.1", "hostname": "localhost"},
        {"ip": "10.0.0.10", "hostname": "webserver01.prod.example.com webserver01"}
      ]
    },
    "network": {
      "systemd_networkd": [
        {
          "filename": "10-eth0.network",
          "content": "[Match]\nName=eth0\n\n[Network]\nAddress=10.0.0.10/24\nGateway=10.0.0.1\nDNS=8.8.8.8\nDNS=8.8.4.4\n"
        }
      ]
    }
  },
  "options": {
    "dry_run": false,
    "verbose": 2,
    "report": {
      "enabled": true,
      "path": "migration-report.json"
    }
  }
}
```

### Example 3: Inspection Only

Use the manifest to inspect source disks without modification:

```json
{
  "version": "1.0",
  "metadata": {
    "name": "inspection-only"
  },
  "source": {
    "type": "vmdk",
    "path": "/data/source/disk.vmdk"
  },
  "output": {
    "directory": "/tmp/inspection-output"
  },
  "pipeline": {
    "inspect": {
      "enabled": true,
      "collect_guest_info": true
    },
    "fix": {"enabled": false},
    "convert": {"enabled": false},
    "validate": {"enabled": false}
  },
  "options": {
    "report": {
      "enabled": true,
      "path": "inspection-report.json"
    }
  }
}
```

### Example 4: Batch Processing

Process multiple VMs by creating a manifest per VM:

**Directory Structure:**
```
migrations/
├── vm1.json
├── vm2.json
├── vm3.json
└── process-all.sh
```

**process-all.sh:**
```bash
#!/bin/bash
set -e

for manifest in migrations/*.json; do
  echo "Processing: $manifest"
  hyper2kvm --manifest "$manifest"

  # Check exit status
  if [ $? -eq 0 ]; then
    echo "✅ Success: $manifest"
  else
    echo "❌ Failed: $manifest"
    exit 1
  fi
done

echo "🎉 All migrations completed"
```

## Usage Patterns

### CI/CD Integration

```yaml
# .gitlab-ci.yml
vm-migration:
  stage: deploy
  script:
    - hyper2kvm --manifest manifests/production.json
  artifacts:
    paths:
      - output/
      - output/report.json
    expire_in: 30 days
  only:
    - main
```

### Version Control

Store manifests in git for audit trails:

```bash
# Track all migration manifests
git add migrations/*.json

# Commit with descriptive message
git commit -m "Add manifest for webserver01 production migration"

# Review history
git log --oneline -- migrations/webserver01.json
```

### Testing Before Production

Create a dry-run manifest to validate configuration:

```json
{
  "version": "1.0",
  "metadata": {
    "name": "dry-run-test"
  },
  "source": {
    "type": "vmdk",
    "path": "/data/source/disk.vmdk"
  },
  "output": {
    "directory": "/tmp/dry-run-output"
  },
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {"enabled": true},
    "convert": {"enabled": false},
    "validate": {"enabled": false}
  },
  "options": {
    "dry_run": true,
    "verbose": 2
  }
}
```

## Troubleshooting

### Common Issues

**Issue: "Manifest not found"**
```
FileNotFoundError: Manifest not found: /path/to/manifest.json
```
**Solution:** Verify the manifest path is correct and the file exists.

**Issue: "Source path not found"**
```
ManifestValidationError: Source path not found: /data/disk.vmdk
```
**Solution:** Ensure the `source.path` exists and is accessible.

**Issue: "Unsupported source type"**
```
ManifestValidationError: Unsupported source type: qcow3
```
**Solution:** Use a supported source type: `vmdk`, `ova`, `ovf`, `vhd`, `qcow2`, `raw`.

**Issue: Pipeline stage fails**

Check the `report.json` for detailed error information:

```bash
cat output/report.json | jq '.errors'
```

### Debugging

Enable verbose output:

```json
{
  "options": {
    "verbose": 2
  }
}
```

Or use CLI override:

```bash
hyper2kvm --manifest migration.json -vv
```

## Migration from CLI Workflow

### Old CLI Approach

```bash
hyper2kvm \
  --config config.yaml \
  --vmdk /data/source/disk.vmdk \
  --output-dir /data/output \
  --out-format qcow2 \
  --compress \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --remove-vmware-tools \
  --user-config-inject users.yaml \
  --service-config-inject services.yaml \
  --hostname-config-inject hostname.yaml
```

### New Manifest Approach

**manifest.json:**
```json
{
  "version": "1.0",
  "source": {"type": "vmdk", "path": "/data/source/disk.vmdk"},
  "output": {"directory": "/data/output", "format": "qcow2"},
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {
      "enabled": true,
      "fstab_mode": "stabilize-all",
      "regen_initramfs": true,
      "remove_vmware_tools": true
    },
    "convert": {"enabled": true, "compress": true},
    "validate": {"enabled": true}
  },
  "configuration": {
    "users": { /* inline from users.yaml */ },
    "services": { /* inline from services.yaml */ },
    "hostname": { /* inline from hostname.yaml */ }
  }
}
```

**Run:**
```bash
hyper2kvm --manifest manifest.json
```

## Best Practices

1. **Version Control**: Always store manifests in git
2. **Descriptive Names**: Use clear `metadata.name` and `metadata.description`
3. **Dry Run First**: Test with `"dry_run": true` before actual migration
4. **Enable Validation**: Always enable the `validate` stage
5. **Keep Reports**: Archive `report.json` for audit trails
6. **Use Compression**: Enable `compress: true` for qcow2 to save space
7. **Backup Strategy**: Keep `backup: true` in the `fix` stage
8. **Separate Configs**: For complex migrations, use separate manifest files per VM

## Reference

### Supported Source Types
- VMDK (VMware Virtual Disk)
- OVA (Open Virtual Appliance)
- OVF (Open Virtualization Format)
- VHD (Virtual Hard Disk)
- QCOW2 (QEMU Copy-On-Write)
- RAW (Raw disk image)

### Supported Output Formats
- qcow2 (recommended, supports compression)
- raw
- vdi

### Pipeline Stages
1. **LOAD_MANIFEST** - Always runs, validates manifest
2. **INSPECT** - Gathers source disk information
3. **FIX** - Applies offline filesystem fixes for KVM
4. **CONVERT** - Converts to target format
5. **VALIDATE** - Verifies output integrity

### Configuration Injection Features
- User account management (create, SSH keys, sudo)
- Systemd service control (enable/disable/mask)
- Hostname and /etc/hosts configuration
- Network configuration (systemd-networkd, NetworkManager)

See [Priority-1-Features.md](Priority-1-Features.md) for complete configuration injection documentation.
