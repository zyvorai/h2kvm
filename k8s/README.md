# h2kvm - Kubernetes Deployment

Production-ready Kubernetes deployment for h2kvm Worker Job Protocol v1.

## Performance Highlights (v2.2.0+)

**Enterprise LVM Features in Worker Pods:**
- ✅ **7x Faster LVM Activation** - 0.71s vs 5-10s for traditional methods
- ✅ **100% Host Protection** - Device-filtered VG activation prevents node corruption
- ✅ **Production Validated** - RHEL 8.8 and openSUSE Leap 15.4 tested
- ✅ **Safe Multi-Tenant** - Workers safely activate only job-specific VGs

See [LVM Enterprise Improvements](../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md) for technical details.

---

## Quick Start

```bash
# Clone repository
cd /path/to/h2kvm

# Build and deploy (production)
cd k8s
make deploy-all NODE_NAMES="node1 node2 node3"

# Or for k3d/kind testing
make deploy-all-k3d
make label-nodes NODE_NAMES="k3d-cluster-agent-0 k3d-cluster-agent-1"
```

---

## Directory Structure

```
k8s/
├── Makefile                    # Deployment automation
├── README.md                   # This file
├── base/
│   ├── namespace.yaml          # Namespace definition
│   ├── storageclasses.yaml     # Storage class examples
│   ├── networkpolicy.yaml      # Network isolation
│   ├── rbac.yaml               # Global RBAC
│   └── psp.yaml                # Pod Security Policy
├── worker/
│   ├── configmap.yaml          # Worker configuration
│   ├── rbac.yaml               # Worker RBAC
│   ├── daemonset.yaml          # Worker DaemonSet (k3d/kind)
│   ├── daemonset-production.yaml  # Worker DaemonSet (production)
│   ├── pvc-templates.yaml      # PersistentVolumeClaim templates
│   ├── job-template.yaml       # Job template for one-shot migrations
│   ├── submit-job.sh           # Job submission helper script
│   ├── README.md               # Worker deployment guide
│   └── examples/
│       ├── inspect-job.json    # Example: Disk inspection
│       ├── convert-job.json    # Example: Format conversion
│       └── offline-fix-job.json # Example: Offline repair
└── monitoring/
    ├── servicemonitor.yaml     # Prometheus ServiceMonitor
    └── prometheusrules.yaml    # Prometheus alert rules (included in servicemonitor.yaml)
```

---

## Prerequisites

### Required

- **Kubernetes cluster** (v1.24+)
  - Production: Bare metal, cloud (EKS, GKE, AKS), or on-prem
  - Testing: k3d, kind, minikube
- **kubectl** configured
- **Docker** or Podman for image building
- **Storage provisioner** for PersistentVolumes
  - NFS for VMDK input (ReadOnlyMany)
  - Ceph/Rook for qcow2 output (ReadWriteMany)
  - Local NVMe for conversion temp (ReadWriteOnce, fastest)

### Optional

- **Prometheus Operator** for metrics
- **Grafana** for dashboards
- **k3d** for local testing

---

## Deployment Methods

### Method 1: Automated Deployment (Recommended)

Using the provided Makefile:

```bash
cd k8s

# Build worker image
make build-image

# Deploy all resources
make deploy-all

# Label worker nodes
make label-nodes NODE_NAMES="worker-01 worker-02 worker-03"

# Check status
make status
```

### Method 2: Manual Deployment

```bash
# 1. Create namespace
kubectl create namespace h2kvm-workers

# 2. Deploy RBAC
kubectl apply -f worker/rbac.yaml

# 3. Deploy ConfigMap
kubectl apply -f worker/configmap.yaml

# 4. Deploy storage (customize storage classes first!)
kubectl apply -f worker/pvc-templates.yaml

# 5. Label nodes
kubectl label nodes worker-01 h2kvm.io/worker-enabled=true

# 6. Deploy workers
kubectl apply -f worker/daemonset-production.yaml

# 7. Deploy monitoring (optional, requires Prometheus Operator)
kubectl apply -f monitoring/servicemonitor.yaml
```

### Method 3: k3d Testing

```bash
# Create k3d cluster
k3d cluster create h2kvm-test --servers 1 --agents 2

# Build and load image
make build-image
make load-image-k3d CLUSTER_NAME=h2kvm-test

# Deploy (k3d version without NBD init container)
make deploy-all-k3d

# Label nodes
make label-nodes NODE_NAMES="k3d-h2kvm-test-agent-0 k3d-h2kvm-test-agent-1"

# Check status
make status
```

---

## Storage Configuration

### Storage Classes

The deployment requires three types of storage:

1. **Input Storage** (VMDKs) - NFS, ReadOnlyMany
2. **Output Storage** (qcow2) - Ceph/Rook, ReadWriteMany
3. **Temp Storage** (conversion) - Local NVMe, ReadWriteOnce

Edit `base/storageclasses.yaml` to match your storage provisioner.

### PersistentVolumeClaims

Edit `worker/pvc-templates.yaml` to adjust:
- `storageClassName` - Match your storage classes
- `resources.requests.storage` - Adjust sizes for your workload

```bash
# Deploy PVCs
kubectl apply -f worker/pvc-templates.yaml

# Check status
kubectl get pvc -n h2kvm-workers
```

---

## Job Submission

### Using the Helper Script

```bash
cd k8s/worker

# Submit job and follow progress
./submit-job.sh --follow examples/convert-job.json

# Submit to specific worker
./submit-job.sh --worker h2kvm-worker-abc123 examples/inspect-job.json
```

### Using Makefile

```bash
# Submit job
make submit-job JOB_FILE=worker/examples/convert-job.json

# Check job status
make job-status JOB_ID=convert-example-001

# View job events
make job-events JOB_ID=convert-example-001
```

### Manual Submission

```bash
# 1. Find a worker pod
POD=$(kubectl get pods -n h2kvm-workers -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')

# 2. Copy job spec to pod
kubectl cp worker/examples/convert-job.json h2kvm-workers/$POD:/var/lib/h2kvm/job.json

# 3. Execute job
kubectl exec -n h2kvm-workers $POD -- \
  python3 -m h2kvm.worker.cli run /var/lib/h2kvm/job.json --follow
```

---

## Monitoring

### Prometheus Metrics

If Prometheus Operator is installed:

```bash
# Deploy ServiceMonitor
kubectl apply -f monitoring/servicemonitor.yaml

# Check metrics endpoint
POD=$(kubectl get pods -n h2kvm-workers -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward -n h2kvm-workers $POD 9090:9090

# Open browser: http://localhost:9090/metrics
```

**Metrics exposed:**
- `h2kvm_migration_total` - Total migrations by status
- `h2kvm_migration_duration_seconds` - Migration duration histogram
- `h2kvm_migration_failures_total` - Migration failures
- `h2kvm_worker_info` - Worker information
- `h2kvm_worker_jobs_active` - Active jobs count
- `h2kvm_vmdk_size_bytes` - VMDK size distribution
- `h2kvm_conversion_temp_usage_bytes` - Temp storage usage

### Alerts

Prometheus alerts are defined in `monitoring/servicemonitor.yaml`:
- `H2KVMWorkerDown` - Worker pod is down
- `H2KVMJobFailed` - Job failures detected
- `H2KVMMigrationSlow` - Migration taking too long
- `H2KVMTempStorageFull` - Temp storage nearly full

---

## Operational Commands

### Status and Logs

```bash
# Show deployment status
make status

# View worker logs (all pods)
make logs

# View specific pod logs
make logs POD_NAME=h2kvm-worker-abc123

# Follow logs
kubectl logs -n h2kvm-workers -l app=h2kvm-worker -f
```

### Worker Management

```bash
# Check worker capabilities
make capabilities

# List all jobs
make list-jobs

# Restart workers
make restart-workers

# Exec into worker
make exec POD_NAME=h2kvm-worker-abc123

# Describe worker
make describe-worker POD_NAME=h2kvm-worker-abc123
```

### Troubleshooting

```bash
# Check pod events
kubectl describe pod -n h2kvm-workers h2kvm-worker-abc123

# Check PVC status
kubectl get pvc -n h2kvm-workers

# Check storage class
kubectl get sc

# View worker capabilities
POD=$(kubectl get pods -n h2kvm-workers -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n h2kvm-workers $POD -- \
  python3 -m h2kvm.worker.cli capabilities
```

---

## Security

### RBAC

Workers run with minimal permissions:
- Read ConfigMaps (job specs)
- Update Pods (status)
- Create Events (logging)
- Read Secrets (credentials)

### Network Policy

Enable network isolation:

```bash
kubectl apply -f base/networkpolicy.yaml
```

Restricts worker egress to:
- DNS (UDP:53)
- Storage backends (as configured)

### Pod Security

Workers require privileged mode for:
- NBD device operations (`/dev/nbd*`)
- LVM activation (device-mapper)
- Filesystem mount (guest disk access)
- Chroot (initramfs regeneration)

Mitigations:
- Node isolation with taints
- Network policies
- Audit logging
- RBAC restrictions

---

## Performance Tuning

### Resource Limits

Edit `worker/daemonset-production.yaml`:

```yaml
resources:
  requests:
    cpu: "4"      # Adjust based on workload
    memory: "8Gi"
  limits:
    cpu: "16"     # Allow bursting
    memory: "32Gi"
```

### Storage Performance

1. **Use local NVMe** for conversion temp
2. **Separate volumes** for input (slow, large) and output (fast, temp)
3. **Enable direct I/O** where possible

### Parallelism

Scale worker count by labeling more nodes:

```bash
kubectl label nodes worker-04 worker-05 h2kvm.io/worker-enabled=true
```

---

## Cleanup

```bash
# Delete all resources
make cleanup

# Or manually
kubectl delete namespace h2kvm-workers

# Delete k3d cluster
k3d cluster delete h2kvm-test
```

---

## Advanced Topics

### Multi-Cluster Deployment

Deploy workers across multiple clusters with centralized job submission.

### Horizontal Pod Autoscaling

Scale workers based on queue depth:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: h2kvm-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: DaemonSet
    name: h2kvm-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Pods
    pods:
      metric:
        name: h2kvm_worker_jobs_active
      target:
        type: AverageValue
        averageValue: "2"
```

### Custom Scheduling

Use node affinity to schedule workers on specific hardware:

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: node.kubernetes.io/instance-type
          operator: In
          values:
          - c5.metal  # AWS bare metal for NBD performance
```

---

## What's Next?

### 🎯 I want to deploy quickly
→ Follow [Quick Start](#quick-start) above

### 📚 I want detailed deployment guides
→ See [Deployment Documentation](../docs/deployment/README.md)

### 🚀 I want performance details
→ Read [LVM Enterprise Improvements](../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)

### 🔍 I want to monitor workers
→ Check [Monitoring](#monitoring) section

### 🔴 I want OpenShift deployment
→ See [OpenShift Guides](../docs/deployment/openshift/)

## Support

- **Documentation:** [docs/worker/PROTOCOL_SPEC.md](../docs/worker/PROTOCOL_SPEC.md)
- **Quick Start:** [docs/worker/QUICKSTART.md](../docs/worker/QUICKSTART.md)
- **LVM Performance:** [docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md](../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)
- **Test Results:** [docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md](../docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)
- **Issues:** https://github.com/ssahani/h2kvm/issues

---

**Version:** 0.2.2
**Status:** Production Ready ✅
**LVM Performance:** 7x faster with 100% host protection
