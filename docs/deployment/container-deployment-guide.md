# h2kvm Container Deployment Guide

Complete guide for deploying h2kvm in Docker, Podman, and Kubernetes environments with the Worker Job Protocol v1.

---

## Table of Contents

1. [Overview](#overview)
2. [Container Images](#container-images)
3. [Docker Deployment](#docker-deployment)
4. [Podman Deployment](#podman-deployment)
5. [Kubernetes Deployment](#kubernetes-deployment)
6. [Worker Job Protocol Integration](#worker-job-protocol-integration)
7. [Security Considerations](#security-considerations)
8. [Troubleshooting](#troubleshooting)

---

## Overview

h2kvm provides specialized container images for different deployment scenarios:

| Image Stage | Purpose | Use Case | Privileged Required |
|-------------|---------|----------|---------------------|
| `cli` | One-shot migrations | Convert single VMDK → qcow2 | No (for conversion only) |
| `daemon` | File watching | Auto-process dropped VMDKs | Yes (if using NBD/LVM) |
| `batch` | Parallel processing | Bulk migrations from manifest | Depends on operations |
| `tui` | Interactive UI | Terminal-based workflow | Depends on operations |
| `worker` | Job orchestration | Worker Job Protocol daemon | Yes (for privileged ops) |
| `production` | Full-featured | Backwards compatible | Yes (full capabilities) |

### Architecture Models

**Model 1: Safe Container (Conversion Only)**
```
┌─────────────────┐
│  Safe Container │  No privileged mode
│  (cli/batch)    │  qemu-img only
│                 │  
│  Input: VMDK    │
│  Output: qcow2  │
└─────────────────┘
```

**Model 2: Privileged Worker (Full Operations)**
```
┌─────────────────────┐
│ Privileged Worker   │  --privileged or extensive capabilities
│ (worker/daemon)     │  NBD, LVM, mount, chroot
│                     │  
│  - Format conversion│
│  - Disk inspection  │
│  - Offline repairs  │
│  - Initramfs regen  │
└─────────────────────┘
```

---

## Container Images

### Building Images

Build all specialized images:

```bash
# Build CLI image (minimal, conversion-only)
docker build --target cli -t h2kvm:cli .

# Build daemon image (long-running file watcher)
docker build --target daemon -t h2kvm:daemon .

# Build worker image (Worker Job Protocol)
docker build --target worker -t h2kvm:worker .

# Build production image (full-featured)
docker build --target production -t h2kvm:prod .
```

### Image Sizes

Approximate sizes after build:

- `cli`: ~750 MB (minimal runtime)
- `daemon`: ~850 MB (adds watchdog)
- `worker`: ~900 MB (adds protocol dependencies)
- `production`: ~1.2 GB (full dependencies)

---

## Docker Deployment

### Using Docker Compose

The repository includes `docker-compose.yml` with pre-configured services.

#### 1. Convert a Single VMDK (CLI Mode)

```bash
# Edit docker-compose.yml to set your paths
docker-compose run --rm cli \
  h2kvmctl --cmd local \
  --vmdk /data/vmware/test.vmdk \
  --output-dir /data/output \
  --to-output converted.qcow2 \
  --out-format qcow2 \
  --compress
```

#### 2. Run Daemon (File Watcher)

```bash
# Start daemon watching /mnt/incoming
docker-compose up -d daemon

# View logs
docker-compose logs -f daemon

# Drop VMDK into /mnt/incoming and watch it process
cp test.vmdk /mnt/incoming/

# Check output
ls -lh /mnt/output/
```

#### 3. Run Worker (Job Protocol)

```bash
# Start worker daemon
docker-compose up -d worker

# Submit a job
docker-compose exec worker \
  h2kvmctl.worker.cli run /data/job-spec.json --follow

# Check worker capabilities
docker-compose exec worker \
  h2kvmctl.worker.cli capabilities
```

### Manual Docker Commands

#### Safe Container (No Privileges)

```bash
docker run --rm \
  -v /path/to/vmdk:/data/input:ro \
  -v /path/to/output:/data/output:rw \
  h2kvm:cli \
  h2kvmctl --cmd local \
  --vmdk /data/input/test.vmdk \
  --output-dir /data/output \
  --to-output converted.qcow2 \
  --out-format qcow2 \
  --compress
```

#### Privileged Worker (Full Operations)

```bash
docker run --rm --privileged \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules:ro \
  -v /data/input:/data/input:ro \
  -v /data/output:/data/output:rw \
  -e H2KVM_MODE=worker \
  h2kvm:worker \
  h2kvmctl.worker.cli run /data/job-spec.json
```

---

## Podman Deployment

Podman offers better security with rootless containers and native systemd integration.

### Rootless Container (Conversion Only)

```bash
podman run --rm \
  -v /path/to/vmdk:/data/input:ro,z \
  -v /path/to/output:/data/output:rw,z \
  h2kvm:cli \
  h2kvmctl --cmd local \
  --vmdk /data/input/test.vmdk \
  --output-dir /data/output \
  --to-output converted.qcow2
```

Note the `:z` suffix for SELinux relabeling.

### Rootful Container (Privileged Operations)

```bash
sudo podman run --rm --privileged \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules:ro \
  -v /data/input:/data/input:ro,z \
  -v /data/output:/data/output:rw,z \
  -e H2KVM_MODE=worker \
  h2kvm:worker
```

### Podman with systemd

Generate systemd unit:

```bash
podman create \
  --name h2kvm-daemon \
  --privileged \
  -v /dev:/dev \
  -v /data/incoming:/data/incoming:rw,z \
  -v /data/output:/data/output:rw,z \
  -e H2KVM_MODE=daemon \
  h2kvm:daemon

podman generate systemd --name h2kvm-daemon > /etc/systemd/system/h2kvm-daemon.service

systemctl daemon-reload
systemctl enable --now h2kvm-daemon
```

---

## Kubernetes Deployment

Complete Kubernetes deployment using the Worker Job Protocol.

### Prerequisites

1. **Node Preparation**

Label worker nodes:
```bash
kubectl label nodes worker-01 h2kvm.io/worker-enabled=true
```

Verify NBD module available:
```bash
ssh worker-01 'ls /lib/modules/$(uname -r)/kernel/drivers/block/nbd.ko'
```

2. **Storage Provisioning**

Create PVCs for input/output:
```bash
# See k8s/base/storageclasses.yaml for examples
kubectl apply -f k8s/base/storageclasses.yaml
```

### Deployment Steps

#### 1. Deploy Base Resources

```bash
# Create namespace and RBAC
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/worker/rbac.yaml
```

#### 2. Deploy Worker Configuration

```bash
kubectl apply -f k8s/worker/configmap.yaml
```

#### 3. Deploy Worker DaemonSet

```bash
kubectl apply -f k8s/worker/daemonset.yaml

# Verify workers running
kubectl get pods -n h2kvm-workers -l app=h2kvm-worker
```

#### 4. Submit Migration Job

```bash
# Create job spec ConfigMap
kubectl create configmap h2kvm-job-001 \
  --from-file=job-spec.json=k8s/worker/examples/convert-job.json \
  -n h2kvm-workers

# Deploy job
sed 's/JOBID/001/g' k8s/worker/job-template.yaml | kubectl apply -f -

# Follow progress
kubectl logs -n h2kvm-workers -f job/h2kvm-migration-001
```

### Detailed Kubernetes Guide

See **[k8s/worker/README.md](../../k8s/worker/README.md)** for complete Kubernetes deployment documentation.

---

## Worker Job Protocol Integration

The Worker Job Protocol provides production-grade job orchestration.

### Job Submission Workflow

```
1. Create JobSpec JSON
   ↓
2. Submit via CLI/API/Kubernetes
   ↓
3. Job validated and queued
   ↓
4. Worker matched by capabilities
   ↓
5. Job executed with progress events
   ↓
6. Results stored, events streamed
```

### Example: Submit Conversion Job

**Create job spec:**

```json
{
  "version": "1.0",
  "job_id": "convert-vm-001",
  "operation": "convert",
  "image": {
    "path": "/data/input/production-vm.vmdk",
    "format": "vmdk"
  },
  "parameters": {
    "output_format": "qcow2",
    "compress": true
  },
  "artifacts": {
    "output_path": "/data/output"
  },
  "audit": {
    "requested_by": "ops-team",
    "ticket": "MIGR-1234"
  }
}
```

**Submit to worker:**

```bash
# Docker
docker exec h2kvm-worker \
  h2kvmctl.worker.cli run /data/convert-job.json --follow

# Kubernetes
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- \
  h2kvmctl.worker.cli run /data/convert-job.json --follow
```

### Monitoring Job Progress

```bash
# View job status
h2kvmctl.worker.cli status convert-vm-001

# Stream events
h2kvmctl.worker.cli events convert-vm-001 --follow

# List all jobs
h2kvmctl.worker.cli list
```

---

## Security Considerations

### Privileged Operations

Operations requiring privileged mode:

| Operation | Required Capabilities |
|-----------|----------------------|
| Format conversion | None (qemu-img is safe) |
| Disk inspection | None (read-only qemu-img info) |
| NBD attachment | `CAP_SYS_ADMIN`, `/dev/nbd*` access |
| LVM activation | `CAP_SYS_ADMIN`, device-mapper access |
| Mount operations | `CAP_SYS_ADMIN`, `CAP_MKNOD` |
| Chroot | `CAP_SYS_CHROOT` |

### Security Hardening

**Docker/Podman:**

```bash
# Drop unnecessary capabilities
docker run --cap-drop=ALL \
  --cap-add=SYS_ADMIN \
  --cap-add=MKNOD \
  --cap-add=SYS_CHROOT \
  --device=/dev/nbd0 \
  --device=/dev/nbd1 \
  h2kvm:worker
```

**Kubernetes:**

```yaml
securityContext:
  privileged: false
  capabilities:
    drop:
    - ALL
    add:
    - SYS_ADMIN
    - MKNOD
    - SYS_CHROOT
```

### Network Isolation

Restrict container egress:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: h2kvm-worker-policy
spec:
  podSelector:
    matchLabels:
      app: h2kvm-worker
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: UDP
      port: 53  # DNS only
```

### Audit Logging

Enable audit logging for privileged operations:

```yaml
env:
- name: H2KVM_AUDIT_LOG
  value: "/var/log/h2kvm/audit.log"
```

---

## Troubleshooting

### NBD Device Not Found

**Symptom:** `error: /dev/nbd0: No such file or directory`

**Solution:**

```bash
# Load NBD module on host
modprobe nbd max_part=16 nbds_max=16

# Verify
lsmod | grep nbd

# In Kubernetes, init container loads it automatically
```

### Permission Denied on NBD Operations

**Symptom:** `permission denied while trying to connect to NBD`

**Cause:** Container not running with sufficient privileges.

**Solution:**

```bash
# Docker: Add --privileged
docker run --privileged ...

# Kubernetes: Verify privileged in securityContext
kubectl get pod -o yaml | grep privileged
```

### Container Image Too Large

**Symptom:** Image size > 2 GB

**Solution:** Use specialized stages:

```bash
# Use cli stage for conversion-only (750 MB)
docker build --target cli -t h2kvm:cli .

# Avoid production stage unless needed (1.2 GB)
```

### Worker Can't Access Storage

**Symptom:** `FileNotFoundError: /data/input/test.vmdk`

**Solution:** Check volume mounts:

```bash
# Docker
docker run -v /host/path:/container/path:ro ...

# Kubernetes
kubectl describe pod | grep -A 5 Mounts
```

### Slow Conversion Performance

**Cause:** Using network storage for temp files.

**Solution:**

1. Mount fast local storage for `/data/output`
2. Use local-nvme StorageClass in Kubernetes
3. Avoid NFS for conversion temp directory

```bash
# Docker: Mount local SSD
docker run -v /mnt/nvme/temp:/data/output ...
```

### Out of Memory During Conversion

**Symptom:** Container killed by OOM

**Solution:** Increase memory limits:

```yaml
resources:
  limits:
    memory: "32Gi"  # For large VMDKs
```

### Job Interrupted by Pod Restart

**Symptom:** Migration incomplete after pod restart.

**Current State:** Jobs in progress are lost.

**Workaround:**

1. Increase `terminationGracePeriodSeconds` to allow job completion
2. Use hostPath for worker state to persist across restarts
3. Monitor job status and retry failed jobs

**Future Enhancement:** Checkpoint/resume support (planned)

---

## Performance Tuning

### CPU Allocation

```yaml
resources:
  requests:
    cpu: "4"    # Minimum for good performance
  limits:
    cpu: "16"   # Allow bursting for compression
```

### Memory Sizing

| VMDK Size | Recommended Memory |
|-----------|-------------------|
| < 100 GB  | 4 GB              |
| 100-500 GB | 8 GB             |
| 500 GB - 1 TB | 16 GB        |
| > 1 TB    | 32 GB             |

### Disk I/O

- Use local NVMe for conversion temp directory
- Separate volumes for input (slow, large) and output (fast, temp)
- Enable direct I/O where possible

---

## Next Steps

1. **Production Deployment:** Follow [k8s/worker/README.md](../../k8s/worker/README.md)
2. **Worker Protocol:** Read [docs/worker/PROTOCOL_SPEC.md](../worker/PROTOCOL_SPEC.md)
3. **Quick Start:** Try [docs/worker/QUICKSTART.md](../worker/QUICKSTART.md)
4. **Monitoring:** Set up Prometheus metrics (coming soon)

---

**Questions?** Open an issue at https://github.com/ssahani/h2kvm/issues
