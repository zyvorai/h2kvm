# Integration Contract: hypersdk ↔ hyper2kvm

## Overview

This document defines the **integration contract** between **hypersdk** (daemon/API/control-plane) and **hyper2kvm** (fix/convert/validate engine).

**Architecture:**
- **hypersdk** produces artifacts + manifest (handles the messy outside world)
- **hyper2kvm** consumes manifest and performs deterministic offline operations
- **Communication:** File-based via versioned JSON manifest

---

## Artifact Manifest v1 Specification

### Design Principles

1. **Provider-agnostic**: hyper2kvm never talks to providers directly
2. **Minimal requirements**: Only `disks[]` + optional firmware hint required
3. **Backward compatible**: Version changes within major version must be compatible
4. **Deterministic**: Same manifest → same outcome
5. **Resumable**: Checksums enable idempotent operations

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "title": "Artifact Manifest",
  "description": "Contract between hypersdk and hyper2kvm for VM migration artifacts",
  "type": "object",
  "required": ["manifest_version", "disks"],
  "properties": {
    "manifest_version": {
      "type": "string",
      "description": "Manifest schema version (semantic versioning)",
      "enum": ["1.0"]
    },
    "source": {
      "type": "object",
      "description": "Source system metadata (informational, not required by hyper2kvm)",
      "properties": {
        "provider": {
          "type": "string",
          "description": "Source provider",
          "examples": ["vsphere", "azure", "aws", "hyperv", "local"]
        },
        "vm_id": {
          "type": "string",
          "description": "Provider-specific VM identifier"
        },
        "vm_name": {
          "type": "string",
          "description": "Human-readable VM name"
        },
        "datacenter": {
          "type": "string",
          "description": "Datacenter or region"
        },
        "export_timestamp": {
          "type": "string",
          "format": "date-time",
          "description": "When export/fetch occurred (ISO 8601)"
        },
        "export_method": {
          "type": "string",
          "description": "How artifacts were obtained",
          "examples": ["govc-export", "ovftool", "snapshot", "direct-download"]
        }
      }
    },
    "vm": {
      "type": "object",
      "description": "VM hardware and firmware metadata",
      "properties": {
        "cpu": {
          "type": "integer",
          "description": "Number of vCPUs",
          "minimum": 1
        },
        "mem_gb": {
          "type": "integer",
          "description": "Memory in GB",
          "minimum": 1
        },
        "firmware": {
          "type": "string",
          "description": "Firmware type (helps hyper2kvm make boot decisions)",
          "enum": ["bios", "uefi", "unknown"],
          "default": "bios"
        },
        "secureboot": {
          "type": "boolean",
          "description": "Secure boot enabled",
          "default": false
        },
        "os_hint": {
          "type": "string",
          "description": "OS hint (optional, helps decision-making)",
          "examples": ["linux", "windows", "unknown"]
        },
        "os_version": {
          "type": "string",
          "description": "OS version string",
          "examples": ["Ubuntu 22.04", "Windows Server 2019"]
        }
      }
    },
    "disks": {
      "type": "array",
      "description": "Disk artifacts (REQUIRED)",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "source_format", "bytes", "local_path"],
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique disk identifier within this manifest",
            "pattern": "^[a-zA-Z0-9_-]+$",
            "examples": ["disk-0", "boot-disk", "data-disk-1"]
          },
          "source_format": {
            "type": "string",
            "description": "Disk image format",
            "enum": ["vmdk", "qcow2", "raw", "vhd", "vhdx", "vdi"]
          },
          "bytes": {
            "type": "integer",
            "description": "Disk size in bytes",
            "minimum": 0
          },
          "local_path": {
            "type": "string",
            "description": "Absolute path to disk file on local filesystem"
          },
          "checksum": {
            "type": "string",
            "description": "SHA-256 checksum (format: 'sha256:hexdigest')",
            "pattern": "^sha256:[a-f0-9]{64}$"
          },
          "boot_order_hint": {
            "type": "integer",
            "description": "Boot priority (0=primary boot disk, 1=secondary, etc.)",
            "minimum": 0
          },
          "label": {
            "type": "string",
            "description": "Human-readable disk label"
          },
          "disk_type": {
            "type": "string",
            "description": "Disk type hint",
            "enum": ["boot", "data", "unknown"],
            "default": "unknown"
          }
        }
      }
    },
    "nics": {
      "type": "array",
      "description": "Network interfaces (informational)",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "NIC identifier"
          },
          "mac": {
            "type": "string",
            "description": "MAC address",
            "pattern": "^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
          },
          "network": {
            "type": "string",
            "description": "Network name from source"
          }
        }
      }
    },
    "notes": {
      "type": "array",
      "description": "Informational notes from export process",
      "items": {
        "type": "string"
      }
    },
    "warnings": {
      "type": "array",
      "description": "Non-fatal warnings from export process",
      "items": {
        "type": "object",
        "properties": {
          "stage": {
            "type": "string",
            "description": "Export stage where warning occurred"
          },
          "message": {
            "type": "string",
            "description": "Warning message"
          },
          "timestamp": {
            "type": "string",
            "format": "date-time"
          }
        }
      }
    },
    "metadata": {
      "type": "object",
      "description": "Additional metadata (extensible)",
      "properties": {
        "hypersdk_version": {
          "type": "string",
          "description": "hypersdk version that created this manifest"
        },
        "job_id": {
          "type": "string",
          "description": "hypersdk job identifier"
        },
        "created_at": {
          "type": "string",
          "format": "date-time",
          "description": "When manifest was created"
        },
        "tags": {
          "type": "object",
          "description": "User-defined tags",
          "additionalProperties": {
            "type": "string"
          }
        }
      }
    }
  }
}
```

### Minimal Valid Manifest

The **absolute minimum** hyper2kvm requires:

```json
{
  "manifest_version": "1.0",
  "disks": [
    {
      "id": "disk-0",
      "source_format": "vmdk",
      "bytes": 10737418240,
      "local_path": "/work/job123/disk-0.vmdk"
    }
  ]
}
```

### Recommended Manifest

What hypersdk **should** provide for optimal results:

```json
{
  "manifest_version": "1.0",
  "source": {
    "provider": "vsphere",
    "vm_id": "vm-1234",
    "vm_name": "webserver01",
    "datacenter": "DC1",
    "export_timestamp": "2026-01-21T18:30:00Z",
    "export_method": "govc-export"
  },
  "vm": {
    "cpu": 4,
    "mem_gb": 16,
    "firmware": "uefi",
    "secureboot": false,
    "os_hint": "linux",
    "os_version": "Ubuntu 22.04"
  },
  "disks": [
    {
      "id": "boot-disk",
      "source_format": "vmdk",
      "bytes": 107374182400,
      "local_path": "/work/job123/boot-disk.vmdk",
      "checksum": "sha256:a1b2c3d4e5f6...",
      "boot_order_hint": 0,
      "label": "OS Boot Disk",
      "disk_type": "boot"
    },
    {
      "id": "data-disk",
      "source_format": "vmdk",
      "bytes": 536870912000,
      "local_path": "/work/job123/data-disk.vmdk",
      "checksum": "sha256:f6e5d4c3b2a1...",
      "boot_order_hint": 1,
      "label": "Application Data",
      "disk_type": "data"
    }
  ],
  "nics": [
    {
      "id": "eth0",
      "mac": "00:50:56:ab:cd:ef",
      "network": "VM Network"
    }
  ],
  "metadata": {
    "hypersdk_version": "0.1.0",
    "job_id": "job-123",
    "created_at": "2026-01-21T18:30:00Z",
    "tags": {
      "environment": "production",
      "team": "ops"
    }
  }
}
```

---

## hyper2kvm Manifest Processing

### What hyper2kvm Uses

| Field | Usage | Impact if Missing |
|-------|-------|-------------------|
| `manifest_version` | Version validation | **FATAL** - Cannot proceed |
| `disks[].id` | Artifact tracking | **FATAL** - Cannot identify outputs |
| `disks[].source_format` | Format detection | **FATAL** - Cannot process |
| `disks[].bytes` | Size validation | **FATAL** - Cannot verify integrity |
| `disks[].local_path` | Input file location | **FATAL** - Cannot read disk |
| `disks[].checksum` | Integrity verification | **WARNING** - Skips checksum validation |
| `disks[].boot_order_hint` | Primary disk selection | Uses first disk as boot disk |
| `vm.firmware` | Boot config decisions | Assumes BIOS |
| `vm.os_hint` | Fix strategy selection | Uses auto-detection |

### What hyper2kvm Ignores (but preserves in report)

- `source.*` - All fields (informational only)
- `vm.cpu`, `vm.mem_gb` - Not needed for offline fixes
- `nics[]` - Informational
- `notes`, `warnings` - Passed through to output report
- `metadata.*` - Preserved for traceability

### Processing Logic

```python
# Pseudo-code for hyper2kvm manifest processing

def load_manifest(path):
    manifest = json.load(path)

    # Version check
    if manifest["manifest_version"] != "1.0":
        raise UnsupportedVersion(f"Expected 1.0, got {manifest['manifest_version']}")

    # Required fields
    if not manifest.get("disks"):
        raise ValidationError("Missing required field: disks")

    # Validate disks
    for disk in manifest["disks"]:
        validate_disk(disk)  # Check id, source_format, bytes, local_path

        if not os.path.exists(disk["local_path"]):
            raise FileNotFoundError(f"Disk not found: {disk['local_path']}")

        if "checksum" in disk:
            verify_checksum(disk["local_path"], disk["checksum"])

    # Extract hints
    firmware = manifest.get("vm", {}).get("firmware", "bios")
    os_hint = manifest.get("vm", {}).get("os_hint", "unknown")

    # Identify boot disk
    boot_disk = find_boot_disk(manifest["disks"])

    return ProcessingContext(
        disks=manifest["disks"],
        boot_disk=boot_disk,
        firmware=firmware,
        os_hint=os_hint,
        source_metadata=manifest.get("source", {}),
        input_warnings=manifest.get("warnings", [])
    )
```

---

## hyper2kvm Output Report

### Report Format

hyper2kvm generates `report.json` that hypersdk can consume:

```json
{
  "version": "1.0",
  "hyper2kvm_version": "1.0.0",
  "timestamp": "2026-01-21T18:45:00Z",
  "input_manifest": {
    "path": "/work/job123/manifest.json",
    "manifest_version": "1.0",
    "source_provider": "vsphere",
    "source_vm_id": "vm-1234",
    "source_vm_name": "webserver01"
  },
  "pipeline": {
    "success": true,
    "duration_seconds": 245.67,
    "stages": {
      "load_manifest": {
        "success": true,
        "duration": 0.12,
        "result": {
          "disks_found": 2,
          "checksums_verified": 2,
          "firmware": "uefi",
          "os_hint": "linux"
        }
      },
      "inspect": {
        "success": true,
        "duration": 3.45,
        "result": {
          "disks": [
            {
              "id": "boot-disk",
              "detected_format": "vmdk",
              "actual_bytes": 107374182400,
              "partitions": 3,
              "filesystems": ["ext4", "swap"]
            },
            {
              "id": "data-disk",
              "detected_format": "vmdk",
              "actual_bytes": 536870912000,
              "partitions": 1,
              "filesystems": ["xfs"]
            }
          ]
        }
      },
      "fix": {
        "success": true,
        "duration": 120.34,
        "result": {
          "disks_processed": ["boot-disk"],
          "fstab_updated": true,
          "grub_updated": true,
          "initramfs_regenerated": true,
          "vmware_tools_removed": true
        }
      },
      "convert": {
        "success": true,
        "duration": 118.56,
        "result": {
          "disks_converted": 2,
          "output_format": "qcow2",
          "compression": true
        }
      },
      "validate": {
        "success": true,
        "duration": 3.20,
        "result": {
          "integrity_checks_passed": 2,
          "boot_config_valid": true
        }
      }
    }
  },
  "artifacts": [
    {
      "type": "converted_disk",
      "disk_id": "boot-disk",
      "path": "/work/job123/output/boot-disk.qcow2",
      "format": "qcow2",
      "size_bytes": 95367431680,
      "size_human": "88.82 GiB",
      "compressed": true,
      "checksum": "sha256:1a2b3c4d...",
      "boot_order_hint": 0
    },
    {
      "type": "converted_disk",
      "disk_id": "data-disk",
      "path": "/work/job123/output/data-disk.qcow2",
      "format": "qcow2",
      "size_bytes": 503316480000,
      "size_human": "468.75 GiB",
      "compressed": true,
      "checksum": "sha256:4d3c2b1a...",
      "boot_order_hint": 1
    }
  ],
  "warnings": [
    {
      "stage": "fix",
      "message": "Data disk skipped (not bootable)",
      "timestamp": "2026-01-21T18:35:15.123456"
    }
  ],
  "errors": [],
  "summary": {
    "total_stages": 5,
    "successful_stages": 5,
    "failed_stages": 0,
    "total_warnings": 1,
    "total_errors": 0,
    "total_artifacts": 2,
    "input_disks": 2,
    "output_disks": 2
  }
}
```

---

## Versioning Policy

### manifest_version

**Format:** Semantic versioning (`MAJOR.MINOR`)

**Compatibility rules:**
- **MAJOR version** change: Breaking changes, may reject old manifests
- **MINOR version** change: Backward compatible additions (new optional fields)

**Examples:**
- `1.0` → `1.1`: Added optional `vm.tpm` field ✅ Compatible
- `1.x` → `2.0`: Changed `disks[]` structure ❌ Breaking

### Version Support

| hyper2kvm Version | Supported Manifest Versions |
|-------------------|----------------------------|
| 1.0.x | 1.0 |
| 1.1.x | 1.0, 1.1 |
| 2.0.x | 2.0 (1.x deprecated) |

### Error Handling

**Unsupported version:**
```json
{
  "error": "UnsupportedManifestVersion",
  "message": "Manifest version '2.0' not supported. This hyper2kvm version supports: ['1.0']",
  "manifest_version": "2.0",
  "supported_versions": ["1.0"]
}
```

---

## Integration Workflow

### Phase 1: hypersdk Export

```
[hypersdk] POST /v1/exports
    ↓
[hypersdk] Download/stage disks → /work/{job_id}/artifacts/
    ↓
[hypersdk] Compute checksums
    ↓
[hypersdk] Generate manifest.json
    ↓
[hypersdk] Job status: "export_complete"
```

### Phase 2: hyper2kvm Convert

```
[hypersdk] POST /v1/conversions (input: job_id)
    ↓
[hypersdk] Spawn: hyper2kvm --manifest /work/{job_id}/manifest.json
    ↓
[hyper2kvm] LOAD_MANIFEST → INSPECT → FIX → CONVERT → VALIDATE
    ↓
[hyper2kvm] Write: report.json
    ↓
[hypersdk] Parse report.json
    ↓
[hypersdk] Update job status: "conversion_complete"
```

### Phase 3: hypersdk Publish (optional)

```
[hypersdk] POST /v1/publish (input: job_id)
    ↓
[hypersdk] Upload artifacts → S3/Azure Blob/etc.
    ↓
[hypersdk] Register image in target (libvirt/OpenStack/etc.)
    ↓
[hypersdk] Trigger webhook: "conversion.published"
```

---

## Resumability Contract

### hypersdk Guarantees

1. **Idempotent exports**: If `manifest.json` exists and checksums match, reuse artifacts
2. **Stable paths**: Artifacts at `/work/{job_id}/` don't move during job lifetime
3. **Checksum verification**: Always verify checksums before reuse

### hyper2kvm Guarantees

1. **Read-only input**: Never modifies input disks
2. **Idempotent operations**: Same manifest → same output (deterministic)
3. **Checksum on output**: Always compute checksums for output artifacts
4. **Partial resume**: Can detect and skip completed stages (future enhancement)

---

## Testing Contract

### Conformance Tests

Both repos must maintain:

1. **Golden manifests**: `tests/fixtures/manifests/*.json`
2. **Round-trip tests**: hypersdk export → hyper2kvm convert → validate report
3. **Schema validation**: Automated schema validation in CI

### Test Matrix

| Source Provider | Disk Count | Firmware | OS | Status |
|----------------|------------|----------|-----|--------|
| vSphere | 1 | BIOS | Linux | ✅ Required |
| vSphere | 2 | UEFI | Linux | ✅ Required |
| vSphere | 1 | UEFI | Windows | ✅ Required |
| Local (vmdk) | 1 | BIOS | Linux | ✅ Required |
| Azure | 1 | UEFI | Linux | 🔄 Future |
| AWS | 1 | UEFI | Linux | 🔄 Future |

---

## Definition of Done (Phase 0)

✅ JSON schema documented and validated
✅ hyper2kvm accepts Artifact Manifest v1
✅ Backward compatibility with legacy format
✅ Multi-disk pipeline support
✅ Reference examples committed
✅ Integration contract documented
✅ Checksums validated (when present)
✅ Report format includes multi-disk artifacts

---

## Future Enhancements (Post-Phase 0)

### Delta/Incremental Support (Phase 5)

```json
{
  "manifest_version": "1.0",
  "mode": "delta",
  "base_manifest_id": "job-100",
  "disks": [
    {
      "id": "boot-disk",
      "source_format": "vmdk",
      "bytes": 5368709120,
      "local_path": "/work/job123/boot-disk-delta.vmdk",
      "delta_metadata": {
        "base_checksum": "sha256:...",
        "changed_blocks": [...],
        "provider_specific": {...}
      }
    }
  ]
}
```

### OpenStack deploy (manifest pipeline)

After conversion, upload the boot disk to Glance via hyper2kvm `deploy_openstack` (requires `openstacksdk` on the worker).

```json
{
  "pipeline": {
    "openstack": {
      "enabled": true,
      "glance_name": "migrated-web-01",
      "os_cloud": "production",
      "visibility": "private",
      "boot_instance": false,
      "flavor": "m1.medium",
      "network": "<neutron-network-uuid>",
      "key_name": "admin-key",
      "wait": true
    }
  }
}
```

Mutually exclusive with `pipeline.kubevirt.enabled` and local libvirt define/start in the same hyper2kvm run.

### Validation Tiers (Phase 4)

```json
{
  "pipeline": {
    "validate": {
      "enabled": true,
      "tiers": {
        "tier0": true,   // File integrity, checksums
        "tier1": true,   // Boot config sanity
        "tier2": false   // Smoke boot test (requires libvirt)
      }
    }
  }
}
```

---

## Contact / Escalation

**Schema changes:** Must be coordinated between both repos
**Breaking changes:** Require major version bump and migration guide
**Bugs in contract:** File issue in both repos with `integration` label

---

**Version:** 1.0
**Last Updated:** 2026-03-29
**Status:** Active
