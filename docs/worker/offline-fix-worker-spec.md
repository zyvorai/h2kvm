# Offline-Fix Worker Specification v1.0

**Status:** Draft
**Version:** 1.0
**Date:** 2026-01-31
**Author:** h2kvm Team

---

## Executive Summary

This specification defines the **contract** between Kubernetes workers (orchestrators) and offline-fix workers (VM/bare-metal environments) that perform dangerous operations requiring full NBD partition device access.

**Key Principle:**
> **Containers orchestrate. VMs operate.**

Kubernetes workers detect capabilities, prepare images, and orchestrate workflows. Offline-fix workers (VM/bare-metal) perform risky operations like mounting guest filesystems, modifying bootloaders, and injecting drivers.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [API Contract](#api-contract)
3. [Request Specification](#request-specification)
4. [Response Specification](#response-specification)
5. [Fix Operations](#fix-operations)
6. [Boot Confidence Scoring](#boot-confidence-scoring)
7. [Error Handling](#error-handling)
8. [Implementation Backends](#implementation-backends)
9. [Security Considerations](#security-considerations)
10. [Testing Strategy](#testing-strategy)

---

## Architecture Overview

### High-Level Flow

```
┌────────────────────────────────────────────────────────────────┐
│                    Kubernetes Worker Pod                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Capability Detection: NBD_INSPECTION detected             │  │
│  │ ↓                                                          │  │
│  │ Decision: Delegate to offline-fix VM                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────┬───────────────────────────────────────────────────┘
             │ OfflineFixRequest (JSON)
             ↓
┌────────────────────────────────────────────────────────────────┐
│                 Offline-Fix Launcher                            │
│  • Launches VM via libvirt/KubeVirt                            │
│  • Injects job spec via cloud-init/config-drive                │
│  • Monitors execution                                           │
└────────────┬───────────────────────────────────────────────────┘
             │
             ↓
┌────────────────────────────────────────────────────────────────┐
│               Offline-Fix VM Worker                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Read OfflineFixRequest from /config/job.json          │  │
│  │ 2. Attach input image via qemu-nbd                        │  │
│  │ 3. Detect OS and filesystems                              │  │
│  │ 4. Execute fix operations                                 │  │
│  │    • Mount root filesystem                                │  │
│  │    • Regenerate initramfs                                 │  │
│  │    • Update GRUB                                          │  │
│  │    • Fix fstab                                            │  │
│  │    • SELinux relabel                                      │  │
│  │ 5. Write OfflineFixResponse to /output/result.json       │  │
│  │ 6. Shutdown                                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────┬───────────────────────────────────────────────────┘
             │ OfflineFixResponse (JSON)
             ↓
┌────────────────────────────────────────────────────────────────┐
│                 Offline-Fix Launcher                            │
│  • Collects result.json                                         │
│  • Retrieves output image                                       │
│  • Cleans up VM                                                 │
└────────────┬───────────────────────────────────────────────────┘
             │ Fixed QCOW2 + metadata
             ↓
┌────────────────────────────────────────────────────────────────┐
│                    Kubernetes Worker Pod                        │
│  • Validates output                                             │
│  • Stores artifact                                              │
│  • Updates job status                                           │
└────────────────────────────────────────────────────────────────┘
```

---

## API Contract

### Contract Version

**Current:** `1.0`

The `version` field in both request and response MUST be set to `"1.0"`.

Future versions will maintain backward compatibility or provide migration paths.

### Communication Mechanism

The offline-fix worker communicates via **JSON files**:

**Input:**
- Path: `/config/job.json` (injected via cloud-init or virtio-serial)
- Format: `OfflineFixRequest` JSON

**Output:**
- Path: `/output/result.json`
- Format: `OfflineFixResponse` JSON

**Alternative Mechanisms** (future):
- HTTP API endpoint
- Message queue (RabbitMQ, NATS)
- Shared memory

---

## Request Specification

### OfflineFixRequest

Full schema: `h2kvm/worker/offline_fix_contract.py::OfflineFixRequest`

**Required Fields:**
```json
{
  "version": "1.0",
  "job_id": "unique-job-id",
  "image": {
    "path": "/work/input.qcow2",
    "format": "qcow2"
  }
}
```

**Complete Example:**
```json
{
  "version": "1.0",
  "job_id": "migrate-centos9-001",
  "image": {
    "path": "/work/input.qcow2",
    "format": "qcow2",
    "size_bytes": 2200000000,
    "virtual_size_bytes": 536870912000
  },
  "os_hint": {
    "family": "centos",
    "version": "9",
    "architecture": "x86_64",
    "boot_mode": "bios"
  },
  "parameters": {
    "update_grub": true,
    "regen_initramfs": true,
    "fstab_mode": "uuid",
    "inject_virtio": true,
    "remove_vmware_tools": true,
    "selinux_relabel": true,
    "dry_run": false,
    "create_backup": true
  },
  "operations": [
    "grub_regenerate",
    "initramfs_regenerate",
    "fstab_uuid",
    "virtio_inject",
    "selinux_relabel"
  ],
  "output_path": "/work/output.qcow2",
  "timeout_seconds": 3600,
  "requested_by": "k8s-worker-001",
  "tags": {
    "migration_id": "mig-12345",
    "source_hypervisor": "vmware"
  }
}
```

### OS Hints

Provide OS hints to **optimize** fix operations (skip unnecessary detection):

```json
{
  "os_hint": {
    "family": "centos",      // centos, rhel, ubuntu, windows
    "version": "9",
    "architecture": "x86_64",
    "boot_mode": "bios"      // bios, uefi
  }
}
```

**Behavior:**
- If `os_hint` provided: Skip detection, use hint
- If `os_hint` is `null`: Perform OS detection
- If hint is **wrong**: Detection may fail or produce incorrect fixes

---

## Response Specification

### OfflineFixResponse

Full schema: `h2kvm/worker/offline_fix_contract.py::OfflineFixResponse`

**Required Fields:**
```json
{
  "version": "1.0",
  "job_id": "migrate-centos9-001",
  "status": "success",
  "started_at": "2026-01-31T10:00:00Z",
  "completed_at": "2026-01-31T10:05:30Z",
  "duration_seconds": 330.5
}
```

**Complete Example:**
```json
{
  "version": "1.0",
  "job_id": "migrate-centos9-001",
  "status": "success",
  "started_at": "2026-01-31T10:00:00Z",
  "completed_at": "2026-01-31T10:05:30Z",
  "duration_seconds": 330.5,

  "detected_os": {
    "family": "centos",
    "name": "CentOS Stream",
    "version": "9",
    "architecture": "x86_64",
    "boot_mode": "bios",
    "root_filesystem": "xfs",
    "has_lvm": true,
    "has_selinux": true
  },

  "operations_performed": [
    {
      "operation": "grub_regenerate",
      "result": "success",
      "message": "GRUB configuration regenerated successfully",
      "duration_seconds": 5.2,
      "details": {
        "grub_version": "2.06",
        "kernel_count": 3
      }
    },
    {
      "operation": "initramfs_regenerate",
      "result": "success",
      "message": "Initramfs rebuilt with virtio drivers",
      "duration_seconds": 45.8,
      "details": {
        "modules_added": ["virtio_blk", "virtio_scsi", "virtio_net"]
      }
    },
    {
      "operation": "fstab_uuid",
      "result": "success",
      "message": "fstab converted to UUID",
      "duration_seconds": 1.3
    },
    {
      "operation": "selinux_relabel",
      "result": "success",
      "message": "SELinux contexts relabeled",
      "duration_seconds": 120.5
    }
  ],

  "fixes_applied": [
    "GRUB regenerated with virtio support",
    "initramfs rebuilt with virtio drivers",
    "fstab converted to UUID",
    "SELinux contexts relabeled"
  ],

  "fixes_skipped": [],

  "output_image": "/work/output.qcow2",
  "output_size_bytes": 2150000000,
  "backup_image": "/work/input.qcow2.backup",

  "boot_confidence": {
    "score": 0.95,
    "factors": {
      "bootloader_valid": 1.0,
      "initramfs_valid": 1.0,
      "fstab_valid": 1.0,
      "virtio_drivers": 0.9,
      "selinux_context": 0.85
    },
    "warnings": [
      "SELinux relabel may trigger on first boot"
    ]
  },

  "warnings": [
    "Old VMware tools packages still present (not removed)"
  ],

  "errors": [],

  "recommended_actions": [
    "boot-test",
    "validate-network-configuration",
    "verify-selinux-mode"
  ],

  "worker_id": "offline-fix-vm-001",
  "environment": {
    "kernel": "6.6.8-200.fc39.x86_64",
    "qemu_version": "8.1.0",
    "tools": {
      "dracut": "059",
      "grub2": "2.06"
    }
  }
}
```

---

## Fix Operations

### Operation Types

See `FixOperation` enum in contract for complete list.

#### Bootloader Operations

| Operation | Description | Requirements |
|-----------|-------------|--------------|
| `grub_regenerate` | Regenerate GRUB config | GRUB installed, root mounted |
| `grub_install` | Install GRUB to MBR/ESP | BIOS/UEFI detection |
| `bootloader_detect` | Detect bootloader type | Root mounted |

#### Filesystem Operations

| Operation | Description | Requirements |
|-----------|-------------|--------------|
| `fstab_uuid` | Convert fstab to UUID | Root mounted, blkid |
| `fstab_label` | Convert fstab to LABEL | Root mounted, e2label |
| `fstab_validate` | Validate fstab entries | Root mounted |

#### Initramfs Operations

| Operation | Description | Requirements |
|-----------|-------------|--------------|
| `initramfs_regenerate` | Rebuild initramfs | dracut/mkinitrd |
| `initramfs_virtio` | Add virtio to initramfs | dracut modules |

#### Driver Operations

| Operation | Description | Requirements |
|-----------|-------------|--------------|
| `virtio_inject` | Inject virtio drivers | Kernel modules |
| `vmware_tools_remove` | Remove VMware tools | Package manager |

#### SELinux Operations

| Operation | Description | Requirements |
|-----------|-------------|--------------|
| `selinux_relabel` | Relabel SELinux contexts | SELinux tools |
| `selinux_disable` | Disable SELinux | Root mounted |

#### Network Operations

| Operation | Description | Requirements |
|-----------|-------------|--------------|
| `network_stabilize` | Stabilize network config | NetworkManager/systemd-networkd |
| `network_predictable_names` | Enable predictable names | udev rules |

---

## Boot Confidence Scoring

### Score Calculation

Boot confidence is a **float from 0.0 to 1.0** representing likelihood of successful first boot.

**Formula:**
```
score = weighted_average(factors)

factors = {
  "bootloader_valid": 0.25,   // GRUB config valid
  "initramfs_valid": 0.25,    // initramfs has virtio
  "fstab_valid": 0.20,        // fstab uses UUID/LABEL
  "virtio_drivers": 0.15,     // Drivers present
  "selinux_context": 0.10,    // SELinux properly configured
  "filesystem_clean": 0.05    // No filesystem errors
}
```

### Score Interpretation

| Score | Interpretation | Recommendation |
|-------|----------------|----------------|
| 0.95 - 1.0 | Excellent | Boot directly in production |
| 0.85 - 0.94 | Good | Boot test recommended |
| 0.70 - 0.84 | Fair | Boot test required, may need tweaks |
| 0.50 - 0.69 | Poor | Manual intervention likely needed |
| 0.0 - 0.49 | Failed | Do not boot, investigate failures |

### Example Scoring

**Perfect Score (1.0):**
```json
{
  "score": 1.0,
  "factors": {
    "bootloader_valid": 1.0,
    "initramfs_valid": 1.0,
    "fstab_valid": 1.0,
    "virtio_drivers": 1.0,
    "selinux_context": 1.0,
    "filesystem_clean": 1.0
  },
  "warnings": []
}
```

**Typical Score (0.92):**
```json
{
  "score": 0.92,
  "factors": {
    "bootloader_valid": 1.0,
    "initramfs_valid": 1.0,
    "fstab_valid": 1.0,
    "virtio_drivers": 0.85,  // Some drivers missing
    "selinux_context": 0.80, // Relabel needed
    "filesystem_clean": 1.0
  },
  "warnings": [
    "virtio_rng driver not found (optional)",
    "SELinux relabel will occur on first boot"
  ]
}
```

---

## Error Handling

### Status Codes

| Status | Meaning | Next Steps |
|--------|---------|------------|
| `success` | All operations completed | Proceed to boot test |
| `partial` | Some operations failed | Review failures, may still boot |
| `failed` | Critical failure | Do not boot, investigate |
| `timeout` | Exceeded timeout | Retry with longer timeout |

### Error Reporting

Errors are reported in the `errors` array:

```json
{
  "status": "partial",
  "errors": [
    "Failed to regenerate initramfs: dracut command not found",
    "SELinux relabel skipped: SELinux not installed"
  ],
  "warnings": [
    "VMware tools packages still present"
  ]
}
```

### Retry Logic

**Retryable Errors:**
- Timeout
- Temporary filesystem errors
- LVM activation failures

**Non-Retryable Errors:**
- Invalid image format
- Corrupted filesystem
- Missing critical files

---

## Implementation Backends

### 1. Direct Libvirt (Bare Metal)

**Use Case:** Bare-metal Kubernetes nodes

```python
launcher = LibvirtOfflineFixLauncher(
    connection_uri="qemu:///system",
    base_image="/images/offline-fix-vm.qcow2"
)

result = launcher.run(offline_fix_request)
```

**Advantages:**
- Full control
- Fast execution
- No nested virtualization

**Disadvantages:**
- Requires libvirt on nodes
- Node security implications

---

### 2. KubeVirt (Kubernetes-Native)

**Use Case:** KubeVirt-enabled clusters

```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: offline-fix-vm
spec:
  template:
    spec:
      domain:
        devices:
          disks:
          - name: config
            disk:
              bus: virtio
          - name: work
            disk:
              bus: virtio
      volumes:
      - name: config
        configMap:
          name: offline-fix-job
      - name: work
        persistentVolumeClaim:
          claimName: work-volume
```

**Advantages:**
- Kubernetes-native
- Declarative
- Resource management

**Disadvantages:**
- Requires KubeVirt
- Slower than direct libvirt

---

### 3. External VM Service

**Use Case:** Centralized offline-fix service

```http
POST /v1/offline-fix HTTP/1.1
Content-Type: application/json

{
  "version": "1.0",
  "job_id": "...",
  "image": { ... }
}
```

**Advantages:**
- Centralized management
- Scalable
- Multi-cluster support

**Disadvantages:**
- Network overhead
- Additional infrastructure

---

## Security Considerations

### Isolation

Offline-fix VMs must be **isolated**:
- No network access (airgapped)
- No persistent storage
- Destroyed after job completion
- Cannot access other VMs/containers

### Input Validation

**CRITICAL:** Validate all inputs:
```python
# Prevent path traversal
if ".." in request.image.path:
    raise ValidationError("Invalid image path")

# Prevent command injection
if ";" in request.parameters.kernel_args:
    raise ValidationError("Invalid kernel arguments")
```

### Image Verification

Before processing:
1. Verify image format matches declaration
2. Check image size limits
3. Scan for malware (optional)

---

## Testing Strategy

### Unit Tests

Test contract validation:
```python
def test_offline_fix_request_validation():
    request = OfflineFixRequest(
        job_id="test-001",
        image=ImageSpec(path="/test.qcow2", format="qcow2")
    )
    assert request.version == "1.0"
```

### Integration Tests

Test with mock VM:
```python
def test_mock_offline_fix():
    request = create_test_request()
    runner = MockOfflineFixRunner()
    result = runner.run(request)
    assert result.status == OfflineFixStatus.SUCCESS
```

### End-to-End Tests

Test full pipeline:
1. K8s worker prepares image
2. Launches offline-fix VM
3. VM performs fixes
4. Collects result
5. Validates boot confidence

---

## Appendix: Contract Versioning

### Version 1.0 (Current)

Initial release with basic offline-fix operations.

### Version 1.1 (Planned)

- Add Windows support
- Add multi-disk support
- Add snapshot-based rollback

### Version 2.0 (Future)

- Breaking change: Split request/response into separate files
- Add streaming progress updates
- Add parallel operation support

---

## References

- Contract Implementation: `h2kvm/worker/offline_fix_contract.py`
- Mock Runner: `h2kvm/worker/offline_fix_mock.py`
- VM Image Build: `vm-image/Dockerfile.offline-fix`

---

**Document Version:** 1.0
**Last Updated:** 2026-03-29
**Status:** Draft - Ready for Review
