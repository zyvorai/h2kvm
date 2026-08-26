# h2kvm Worker Kubernetes Deployment

Production-ready Kubernetes manifests for deploying h2kvm workers using the Worker Job Protocol v1.

## Architecture

```
┌─────────────────────────────┐
│     Control Plane           │
│  (Job Submission Service)   │
│                             │
│  kubectl apply -f job.yaml  │
└──────────────┬──────────────┘
               │
               │ Worker Job Protocol (JSON)
               ▼
┌─────────────────────────────┐
│      Data Plane             │
│   (Worker DaemonSet)        │
│                             │
│  - NBD device operations    │
│  - LVM activation           │
│  - VM disk conversion       │
│  - Progress event streaming │
└─────────────────────────────┘
```

## Components

| File | Purpose |
|------|---------|
| `configmap.yaml` | Worker configuration |
| `rbac.yaml` | Service account and permissions |
| `daemonset.yaml` | Long-running worker pods on all nodes |
| `job-template.yaml` | One-shot CLI migration jobs |

## Prerequisites

### Node Preparation

Label nodes that should run workers:

```bash
kubectl label nodes worker-node1 h2kvm.io/worker-enabled=true
kubectl label nodes worker-node2 h2kvm.io/worker-enabled=true
```

### NBD Kernel Module

Workers require the NBD kernel module. The DaemonSet includes an init container that loads it automatically:

```bash
# Verify NBD module is available on nodes
ssh worker-node1 'ls /lib/modules/$(uname -r)/kernel/drivers/block/nbd.ko'
```

### Storage Provisioning

Create PersistentVolumeClaims for input/output storage:

```bash
# Example: Local storage for fast conversion
cat > pvc-local-fast.yaml << 'EOFPVC'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: conversion-temp
  namespace: h2kvm-workers
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: local-nvme
  resources:
    requests:
      storage: 500Gi
EOFPVC

kubectl apply -f pvc-local-fast.yaml
```

## Deployment

### Step 1: Create Namespace

```bash
kubectl apply -f ../base/namespace.yaml
```

### Step 2: Deploy RBAC

```bash
kubectl apply -f rbac.yaml
```

### Step 3: Deploy ConfigMap

```bash
kubectl apply -f configmap.yaml
```

### Step 4: Deploy Worker DaemonSet

```bash
kubectl apply -f daemonset.yaml
```

### Step 5: Verify Deployment

```bash
# Check pods are running
kubectl get pods -n h2kvm-workers -l app=h2kvm-worker

# Check worker capabilities
kubectl exec -n h2kvm-workers -it h2kvm-worker-xxxxx -- \
  python3 -m h2kvm.worker.cli capabilities

# Check NBD module loaded
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- lsmod | grep nbd
```

## Usage

### One-Shot Migration (Job)

Create a job specification ConfigMap:

```bash
cat > job-spec-configmap.yaml << 'EOFCM'
apiVersion: v1
kind: ConfigMap
metadata:
  name: h2kvm-job-migration-001
  namespace: h2kvm-workers
data:
  job-spec.json: |
    {
      "version": "1.0",
      "job_id": "migration-001",
      "operation": "convert",
      "image": {
        "path": "/input/vm.vmdk",
        "format": "vmdk"
      },
      "parameters": {
        "output_format": "qcow2",
        "compress": true
      },
      "artifacts": {
        "output_path": "/output"
      },
      "audit": {
        "requested_by": "kubernetes-operator"
      }
    }
EOFCM

kubectl apply -f job-spec-configmap.yaml
```

Submit the job:

```bash
# Copy template and replace JOBID
sed 's/JOBID/migration-001/g' job-template.yaml > migration-001-job.yaml

kubectl apply -f migration-001-job.yaml

# Follow job progress
kubectl logs -n h2kvm-workers -f job/h2kvm-migration-migration-001

# Check job status
kubectl get job -n h2kvm-workers
```

### Long-Running Worker (DaemonSet)

Workers watch for job files in the queue directory:

```bash
# Submit job via ConfigMap
cat > queue-job.yaml << 'EOFJOB'
apiVersion: v1
kind: ConfigMap
metadata:
  name: queued-job-002
  namespace: h2kvm-workers
  labels:
    h2kvm.io/job-type: queued
data:
  job-spec.json: |
    {
      "version": "1.0",
      "job_id": "queued-002",
      "operation": "inspect",
      "image": {
        "path": "/data/incoming/test.qcow2",
        "format": "qcow2"
      },
      "artifacts": {
        "output_path": "/data/output"
      },
      "audit": {
        "requested_by": "daemon-watcher"
      }
    }
EOFJOB

kubectl apply -f queue-job.yaml

# Worker will pick up the job automatically
```

## Monitoring

### Check Worker Events

```bash
# View worker logs
kubectl logs -n h2kvm-workers -l app=h2kvm-worker --tail=100 -f

# View job events (stored in worker pod)
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- \
  python3 -m h2kvm.worker.cli events migration-001

# Check job status
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- \
  python3 -m h2kvm.worker.cli status migration-001
```

### List All Jobs

```bash
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- \
  python3 -m h2kvm.worker.cli list
```

## Resource Limits

Default resource limits per worker pod:

- CPU: 2-8 cores (request-limit)
- Memory: 4-16 GB (request-limit)
- Grace period: 2 hours (for completing migrations)

Adjust in `daemonset.yaml` based on node capacity and VMDK sizes.

## Security

### Privileged Mode

Workers run with `privileged: true` because they require:
- NBD device access (`/dev/nbd*`)
- LVM operations (device-mapper)
- Mount operations (filesystem surgery)
- Chroot (initramfs regeneration)

### Mitigation

- Network policy: Restrict egress to storage and DNS only
- Node isolation: Taint worker nodes to prevent other workloads
- Audit logging: All privileged operations logged via Worker Protocol events
- RBAC: Minimal permissions for service account

### Pod Security

Apply Pod Security Standards:

```bash
kubectl label namespace h2kvm-workers \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted
```

## Troubleshooting

### Pod Won't Start

```bash
# Check events
kubectl describe pod -n h2kvm-workers h2kvm-worker-xxxxx

# Common issues:
# 1. NBD module not available on node
# 2. /dev not mounted (check volume mounts)
# 3. Image pull failure
```

### NBD Module Not Loading

```bash
# Check kernel module availability
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- \
  ls /lib/modules/$(uname -r)/kernel/drivers/block/nbd.ko

# Load manually on node
ssh worker-node1 'sudo modprobe nbd max_part=16 nbds_max=16'
```

### Job Fails with "Missing capability: nbd"

Worker doesn't have NBD access. Check:

```bash
# Verify privileged mode enabled
kubectl get pod -n h2kvm-workers h2kvm-worker-xxxxx -o yaml | grep privileged

# Verify /dev mounted
kubectl exec -n h2kvm-workers h2kvm-worker-xxxxx -- ls -la /dev/nbd0
```

### Migration Interrupted by Pod Restart

Jobs in progress are lost on pod restart. To prevent:

1. Increase `terminationGracePeriodSeconds` (default: 7200)
2. Use PVC for worker state (currently hostPath)
3. Implement checkpoint/resume (future enhancement)

## Scaling

### Horizontal Scaling

Add more worker nodes:

```bash
kubectl label nodes worker-node3 h2kvm.io/worker-enabled=true

# DaemonSet automatically schedules pod on new node
kubectl get pods -n h2kvm-workers -o wide
```

### Vertical Scaling

Increase resources per pod:

```yaml
# Edit daemonset.yaml
resources:
  limits:
    cpu: "16"
    memory: "32Gi"
```

## Example: Complete Workflow

```bash
# 1. Deploy infrastructure
kubectl apply -f ../base/namespace.yaml
kubectl apply -f rbac.yaml
kubectl apply -f configmap.yaml
kubectl apply -f daemonset.yaml

# 2. Wait for workers ready
kubectl wait --for=condition=Ready pods -n h2kvm-workers -l app=h2kvm-worker --timeout=300s

# 3. Submit migration job
cat > migration-job-spec.yaml << 'EOFJOB'
apiVersion: v1
kind: ConfigMap
metadata:
  name: h2kvm-job-prod-001
  namespace: h2kvm-workers
data:
  job-spec.json: |
    {
      "version": "1.0",
      "job_id": "prod-migration-001",
      "operation": "convert",
      "image": {
        "path": "/input/production-vm.vmdk",
        "format": "vmdk"
      },
      "parameters": {
        "output_format": "qcow2",
        "compress": true
      },
      "artifacts": {
        "output_path": "/output",
        "log_upload": true
      },
      "audit": {
        "requested_by": "ops-team",
        "ticket": "PROD-1234"
      }
    }
EOFJOB

kubectl apply -f migration-job-spec.yaml

# 4. Create and submit job
sed 's/JOBID/prod-migration-001/g' job-template.yaml | kubectl apply -f -

# 5. Monitor progress
kubectl logs -n h2kvm-workers -f job/h2kvm-migration-prod-migration-001

# 6. Retrieve results
kubectl exec -n h2kvm-workers job/h2kvm-migration-prod-migration-001 -- \
  ls -lh /output/
```

## Next Steps

- Set up Prometheus ServiceMonitor for metrics
- Configure alerting for job failures
- Implement REST API for job submission
- Deploy Kubernetes operator for automated worker management

---

**Questions?** See the complete protocol spec: `docs/worker/PROTOCOL_SPEC.md`
