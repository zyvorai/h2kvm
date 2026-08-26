# Phase 4: OfflineFixJob - Kubernetes-Native Offline VM Repair

**Status:** ✅ Complete
**Version:** v1.0.0
**Date:** 2026-01-31

---

## Overview

Phase 4 implements a production-ready Kubernetes-native system for offline VM repairs. It orchestrates the execution of Phase 3 fixers (fstab, initramfs, grub, selinux) using KubeVirt VMs and host-level NBD management.

### Architecture Principle

> **Block devices stay on the host. Filesystems live in VMs. Containers orchestrate, never repair.**

This design is:
- ✅ **KubeVirt-safe** - Uses HostDisk pattern, not raw block devices
- ✅ **Production-ready** - Proper security, error handling, cleanup
- ✅ **SELinux-compatible** - Works with enforcing mode
- ✅ **Restart-safe** - Phase-driven reconciliation

---

## Components

### 1. OfflineFixJob CRD

Custom Resource Definition for declarative offline VM repair.

**Location:** `k8s/operator/crds/offlinefixjob.yaml`

**Example:**
```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: OfflineFixJob
metadata:
  name: centos9-fix
spec:
  source:
    disk:
      type: qcow2
      path: /var/lib/imports/centos9.qcow2
  fixes:
  - fstab
  - initramfs
  - grub
  - selinux
  nodeSelector:
    hyper2kvm.io/nbd-capable: "true"
```

**Status Phases:**
- `Pending` - Job created, selecting node
- `NBDPrepared` - NBD attached and mounted
- `VMRunning` - KubeVirt VM created
- `Fixing` - VM executing fixers
- `Completed` - Fixes applied successfully
- `Failed` - Error occurred

### 2. OfflineFixJob Controller

Python controller using kopf framework.

**Location:** `hyper2kvm/operator/offlinefixjob_controller.py` (400 lines)

**Responsibilities:**
- Watch OfflineFixJob resources
- Select NBD-capable nodes
- Coordinate with NBD prep DaemonSet via node annotations
- Create KubeVirt VMs with HostDisk
- Collect results from VMs
- Update job status
- Trigger cleanup

**Key Functions:**
```python
@kopf.on.create('hyper2kvm.io', 'v1alpha1', 'offlinefixjobs')
async def create_offline_fix_job(...)

@kopf.on.field(..., field='status.phase', new='Pending')
async def handle_pending(...)

@kopf.on.delete('hyper2kvm.io', 'v1alpha1', 'offlinefixjobs')
async def delete_offline_fix_job(...)
```

### 3. NBD Prep Daemon

DaemonSet that manages NBD on host nodes.

**Location:** `hyper2kvm/daemon/nbd_prep.py` (450 lines)

**Responsibilities:**
- Watch node annotations for job assignments
- Load NBD kernel module
- Attach disk images to NBD devices using qemu-nbd
- Probe partitions and activate LVM
- Mount guest filesystems to `/var/lib/kubevirt-offline/<job>/`
- Update node annotations when ready
- Cleanup: unmount and disconnect NBD

**Workflow:**
```python
1. Controller annotates node: offlinefix.hyper2kvm.io/job=namespace/name
2. Daemon sees annotation → Executes NBD setup
3. Daemon updates annotation: nbd-ready=true
4. Controller creates VM
5. VM completes → Controller signals cleanup
6. Daemon unmounts and disconnects NBD
```

### 4. Offline-Fix VM Image

Container image that runs as KubeVirt VM to execute fixers.

**Location:** `images/offline-fix-vm/`

**Files:**
- `Dockerfile` - Ubuntu 22.04 base with system tools
- `worker.py` (230 lines) - Fixer execution worker
- `entrypoint.sh` - VM startup script

**Integration with Phase 3:**
```
VM receives job spec → worker.py → Loads fixers:
  ├─ FstabFixer (fix_fstab.py)
  ├─ InitramfsFixer (fix_initramfs.py)
  ├─ GrubFixer (fix_grub.py)
  └─ SELinuxFixer (fix_selinux.py)

Results written to /output/result.json
```

**Input Contract:**
```json
{
  "job_id": "centos9-fix",
  "fixes": ["fstab", "initramfs", "grub", "selinux"],
  "parameters": {"bootDisk": "/dev/vda"},
  "safety": {"readOnly": false}
}
```

**Output Contract:**
```json
{
  "success": true,
  "operations": [
    {"operation": "fstab", "success": true, "durationSeconds": 2.5},
    {"operation": "initramfs", "success": true, "durationSeconds": 45.2},
    {"operation": "grub", "success": true, "durationSeconds": 12.1},
    {"operation": "selinux", "success": true, "durationSeconds": 0.3}
  ],
  "bootConfidence": 95
}
```

### 5. DaemonSet Manifest

Kubernetes manifest for NBD prep daemon.

**Location:** `k8s/daemon/nbd-prep-daemonset.yaml`

**Key Features:**
- Runs on nodes with label `hyper2kvm.io/nbd-capable=true`
- ServiceAccount + RBAC for node access
- **Scoped capabilities** (SYS_ADMIN, SYS_MODULE) - NOT privileged
- Volume mounts: `/dev`, `/var/lib/kubevirt-offline`, `/var/lib/imports`
- Resource limits: 512Mi RAM, 500m CPU

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. kubectl apply -f offlinefixjob.yaml                      │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Controller (kopf)                                        │
│    • Phase: Pending                                         │
│    • Selects node with hyper2kvm.io/nbd-capable=true        │
│    • Annotates node: offlinefix.hyper2kvm.io/job=ns/name   │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. NBD Prep DaemonSet (Python)                              │
│    • Watches node.metadata.annotations                      │
│    • qemu-nbd --connect /dev/nbd0 disk.qcow2               │
│    • partprobe /dev/nbd0                                    │
│    • vgchange -ay (activate LVM)                            │
│    • mount /dev/nbd0p2 /var/lib/kubevirt-offline/job-id     │
│    • Annotates node: nbd-ready=true                         │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Controller detects NBD ready                             │
│    • Phase: NBDPrepared                                     │
│    • Creates ConfigMap with job spec                        │
│    • Creates KubeVirt VirtualMachineInstance:               │
│      - Volume: HostDisk (path: /var/lib/kubevirt-offline/)  │
│      - Volume: ConfigMap (job spec)                         │
│      - Image: quay.io/hyper2kvm/offline-fix-vm:v1.0.0      │
│    • Phase: VMRunning                                       │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. KubeVirt VM starts                                       │
│    • Phase: Fixing                                          │
│    • Runs entrypoint.sh                                     │
│    • Calls worker.py with spec from ConfigMap               │
│    • Guest root visible at /vmroot                          │
│    • Executes Phase 3 fixers:                               │
│      ├─ FstabFixer (UUID conversion)                        │
│      ├─ InitramfsFixer (virtio injection)                   │
│      ├─ GrubFixer (bootloader regen)                        │
│      └─ SELinuxFixer (autorelabel)                          │
│    • Writes result.json to output                           │
│    • VM exits                                               │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Controller collects results                              │
│    • Reads result ConfigMap                                 │
│    • Updates OfflineFixJob.status.result                    │
│    • Calculates boot confidence score                       │
│    • Deletes VM                                             │
│    • Annotates node: cleanup=true                           │
│    • Phase: Completed                                       │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. NBD Prep DaemonSet cleanup                               │
│    • Sees cleanup annotation                                │
│    • umount /var/lib/kubevirt-offline/job-id/boot           │
│    • umount /var/lib/kubevirt-offline/job-id                │
│    • vgchange -an (deactivate LVM)                          │
│    • qemu-nbd --disconnect /dev/nbd0                        │
│    • Clears all node annotations                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Code Statistics

| Component | Lines | Language | Purpose |
|-----------|-------|----------|---------|
| OfflineFixJob CRD | 150 | YAML | Resource definition |
| Controller | 400 | Python | Orchestration logic |
| NBD Daemon | 450 | Python | Host NBD management |
| VM Worker | 230 | Python | Fixer execution |
| VM Entrypoint | 100 | Bash | VM startup |
| DaemonSet Manifest | 130 | YAML | K8s deployment |
| Build Script | 80 | Bash | Image building |
| **Total Phase 4** | **~1,540** | | **New code** |

**Combined with Phase 3:**
- Phase 3: 1,960 lines (fixers)
- Phase 4: 1,540 lines (orchestration)
- **Total: ~3,500 lines**

---

## Security

### Scoped Capabilities (Not Privileged)

NBD Prep DaemonSet uses minimal capabilities:

```yaml
securityContext:
  capabilities:
    add:
    - SYS_ADMIN    # For mount operations
    - SYS_MODULE   # For modprobe
  allowPrivilegeEscalation: false
```

**Why this is safe:**
- ❌ **NOT** using `privileged: true`
- ✅ Only specific capabilities granted
- ✅ Runs on trusted nodes only (labeled)
- ✅ ServiceAccount with RBAC
- ✅ SELinux-compatible

### Isolation Boundaries

```
Host
├─ NBD device (/dev/nbd0) - Host kernel, DaemonSet only
├─ Mount point (/var/lib/kubevirt-offline/) - Host filesystem, DaemonSet only
└─ KubeVirt VM
   └─ HostDisk mount - VM sees filesystem, not device
      └─ Fixers - Python code, no privileged operations
```

**Trust boundaries:**
1. **Host → DaemonSet:** Scoped capabilities
2. **Host → VM:** KubeVirt isolation
3. **VM → Guest FS:** Read/write via mount, no raw block access

---

## Integration with Migration CRD

OfflineFixJob can be created automatically by Migration controller:

```python
# In Migration controller
@kopf.on.field('hyper2kvm.io', 'v1alpha1', 'migrations',
               field='status.phase', new='ConversionComplete')
async def trigger_offline_fixes(spec, status, namespace, name, **kwargs):
    """Create OfflineFixJob after disk conversion."""

    ofj = {
        'apiVersion': 'hyper2kvm.io/v1alpha1',
        'kind': 'OfflineFixJob',
        'metadata': {
            'name': f'fix-{name}',
            'namespace': namespace,
            'ownerReferences': [...]
        },
        'spec': {
            'source': {
                'disk': {
                    'type': 'qcow2',
                    'pvc': status['convertedDiskPVC']
                }
            },
            'fixes': ['fstab', 'initramfs', 'grub', 'selinux']
        }
    }

    await api.create_namespaced_custom_object(..., body=ofj)
```

---

## Testing

### Unit Tests

```bash
# Test controller logic
cd hyper2kvm/operator
python -m pytest test_offlinefixjob_controller.py

# Test NBD daemon
cd hyper2kvm/daemon
python -m pytest test_nbd_prep.py
```

### Integration Tests

See: `docs/deployment/phase4-deployment.md`

1. Deploy CRD, DaemonSet, Controller
2. Label test node
3. Create OfflineFixJob with real VMDK
4. Monitor phases
5. Verify results

### End-to-End Tests

```bash
# Run complete workflow test
./tests/e2e_offlinefixjob_test.sh
```

---

## Deployment

**Quick Start:**

```bash
# 1. Build images
./scripts/build-phase4-images.sh

# 2. Push to registry
docker push quay.io/hyper2kvm/nbd-prep:v1.0.0
docker push quay.io/hyper2kvm/offline-fix-vm:v1.0.0

# 3. Deploy
kubectl apply -f k8s/operator/crds/offlinefixjob.yaml
kubectl apply -f k8s/daemon/nbd-prep-daemonset.yaml
kubectl label node worker-1 hyper2kvm.io/nbd-capable=true

# 4. Test
kubectl apply -f k8s/operator/examples/offlinefixjob-example.yaml
kubectl get offlinefixjob -w
```

**Full Guide:** See `docs/deployment/phase4-deployment.md`

---

## Troubleshooting

### Common Issues

**NBD not attaching:**
```bash
# Check DaemonSet logs
kubectl logs -n hyper2kvm-system -l app=nbd-prep

# Check NBD module
kubectl exec -n hyper2kvm-system <pod> -- lsmod | grep nbd
```

**VM not starting:**
```bash
# Check KubeVirt
kubectl get kubevirt -n kubevirt

# Check VMI
kubectl get vmi -n hyper2kvm-system
kubectl describe vmi <vm-name>
```

**Fixers failing:**
```bash
# Check VM logs
kubectl logs -n hyper2kvm-system <vm-pod>

# Check guest filesystem mount
kubectl exec -n hyper2kvm-system <vm-pod> -- ls /vmroot/etc
```

---

## Roadmap

### Future Enhancements

**Phase 5: Advanced Features**
- Multi-disk support
- LUKS encryption handling
- Custom fixer plugins
- Parallel fixer execution
- Incremental fixes (run only needed fixers)

**Monitoring:**
- Prometheus metrics
- Grafana dashboards
- Alerting rules

**Performance:**
- Fixer parallelization
- Caching of common operations
- NBD device pooling

---

## Related Documentation

- **Phase 3 Fixers:** `docs/phase3-fixers-README.md`
- **Deployment Guide:** `docs/deployment/phase4-deployment.md`
- **Architecture Design:** `/tmp/OFFLINE_FIX_CRD_DESIGN.md`
- **Implementation Guide:** `/tmp/PHASE4_IMPLEMENTATION_GUIDE.md`

---

## Summary

Phase 4 provides:
✅ **Kubernetes-native** offline VM repair
✅ **Production-ready** security and error handling
✅ **KubeVirt-safe** architecture (HostDisk pattern)
✅ **Integrates Phase 3** fixers seamlessly
✅ **Clean lifecycle** management
✅ **~1,540 lines** of orchestration code

**Combined with Phase 3: ~3,500 lines of complete VM migration system**

🎯 **Status: Ready for production deployment**
