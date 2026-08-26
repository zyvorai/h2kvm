# H2KVM Worker Helm Chart

Helm chart for deploying h2kvm Worker Job Protocol v1 on Kubernetes.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.8+
- Storage provisioner for PersistentVolumes
- (Optional) Prometheus Operator for metrics

## Installation

### Quick Start

```bash
# Add custom values
cat > custom-values.yaml << EOFVALUES
worker:
  nodeSelector:
    h2kvm.io/worker-enabled: "true"

storage:
  input:
    storageClass: "nfs-storage"
  output:
    storageClass: "ceph-rbd"
  temp:
    storageClass: "local-nvme"
EOFVALUES

# Install chart
helm install h2kvm-worker ./h2kvm-worker \
  --namespace h2kvm-workers \
  --create-namespace \
  --values custom-values.yaml
```

### Verify Installation

```bash
# Check pods
kubectl get pods -n h2kvm-workers -l app=h2kvm-worker

# Check PVCs
kubectl get pvc -n h2kvm-workers

# Check worker capabilities
POD=$(kubectl get pods -n h2kvm-workers -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n h2kvm-workers $POD -- \
  python3 -m h2kvm.worker.cli capabilities
```

## Configuration

### Key Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `worker.image.repository` | Worker image repository | `h2kvm` |
| `worker.image.tag` | Worker image tag | `worker` |
| `worker.resources.requests.cpu` | CPU request | `2` |
| `worker.resources.requests.memory` | Memory request | `4Gi` |
| `worker.resources.limits.cpu` | CPU limit | `8` |
| `worker.resources.limits.memory` | Memory limit | `16Gi` |
| `worker.nodeSelector` | Node selector | `h2kvm.io/worker-enabled: "true"` |
| `storage.state.enabled` | Enable state PVC | `true` |
| `storage.state.size` | State PVC size | `10Gi` |
| `storage.events.enabled` | Enable events PVC | `true` |
| `storage.events.size` | Events PVC size | `5Gi` |
| `storage.input.enabled` | Enable input PVC | `true` |
| `storage.input.size` | Input PVC size | `1Ti` |
| `storage.output.enabled` | Enable output PVC | `true` |
| `storage.output.size` | Output PVC size | `500Gi` |
| `storage.temp.enabled` | Enable temp PVC | `true` |
| `storage.temp.size` | Temp PVC size | `200Gi` |
| `monitoring.metrics.enabled` | Enable Prometheus metrics | `true` |
| `monitoring.serviceMonitor.enabled` | Enable ServiceMonitor | `true` |

See `values.yaml` for complete configuration options.

## Storage Configuration

### Storage Classes

Configure storage classes for optimal performance:

```yaml
storage:
  # Worker state - needs persistence, moderate IOPS
  state:
    storageClass: "default"
    
  # Events - needs persistence, low IOPS
  events:
    storageClass: "default"
    
  # Input VMDKs - large files, read-only
  input:
    storageClass: "nfs-storage"  # NFS recommended
    
  # Output qcow2 - shared access
  output:
    storageClass: "ceph-rbd-fast"  # Ceph/Rook recommended
    
  # Conversion temp - maximum IOPS required
  temp:
    storageClass: "local-nvme"  # Local NVMe required!
```

### Disable Storage

To use emptyDir or hostPath instead of PVCs:

```yaml
storage:
  state:
    enabled: false
  events:
    enabled: false
```

Then manually mount volumes in DaemonSet.

## Monitoring

### Prometheus Metrics

Metrics are exposed on port 9090 by default:

```bash
# Port forward to access metrics
POD=$(kubectl get pods -n h2kvm-workers -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward -n h2kvm-workers $POD 9090:9090

# Access metrics: http://localhost:9090/metrics
```

### ServiceMonitor

If Prometheus Operator is installed:

```yaml
monitoring:
  serviceMonitor:
    enabled: true
    interval: 30s
    labels:
      prometheus: kube-prometheus
```

### Grafana Dashboard

Dashboard is automatically created as ConfigMap:

```bash
# Import into Grafana
kubectl get configmap h2kvm-worker-grafana-dashboard \
  -n h2kvm-workers \
  -o jsonpath='{.data.worker-overview\.json}' > dashboard.json

# Import dashboard.json into Grafana UI
```

## Job Submission

### Submit a Job

```bash
# Create job spec
cat > convert-job.json << EOFJOB
{
  "version": "1.0",
  "job_id": "convert-001",
  "operation": "convert",
  "image": {
    "path": "/data/input/vm.vmdk",
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
    "requested_by": "helm-user"
  }
}
EOFJOB

# Submit job
POD=$(kubectl get pods -n h2kvm-workers -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')
kubectl cp convert-job.json h2kvm-workers/$POD:/var/lib/h2kvm/job.json
kubectl exec -n h2kvm-workers $POD -- \
  python3 -m h2kvm.worker.cli run /var/lib/h2kvm/job.json --follow
```

## Upgrading

```bash
# Update values
helm upgrade h2kvm-worker ./h2kvm-worker \
  --namespace h2kvm-workers \
  --values custom-values.yaml
```

## Uninstallation

```bash
# Delete Helm release
helm uninstall h2kvm-worker --namespace h2kvm-workers

# Delete namespace (optional, will delete PVCs!)
kubectl delete namespace h2kvm-workers
```

## Troubleshooting

### Pods Not Starting

```bash
# Check events
kubectl describe daemonset -n h2kvm-workers h2kvm-worker

# Check pod events
kubectl describe pod -n h2kvm-workers <pod-name>
```

### PVCs Not Binding

```bash
# Check PVCs
kubectl get pvc -n h2kvm-workers

# Check storage classes
kubectl get sc

# Describe PVC
kubectl describe pvc -n h2kvm-workers <pvc-name>
```

### Metrics Not Appearing

```bash
# Check ServiceMonitor
kubectl get servicemonitor -n h2kvm-workers

# Check Prometheus targets
# (Access Prometheus UI and check targets)
```

## Examples

### Minimal Installation (k3d/kind)

```yaml
# minimal-values.yaml
storage:
  state:
    enabled: false
  events:
    enabled: false
  input:
    enabled: false
  output:
    enabled: false
  temp:
    enabled: false

initContainer:
  enabled: false  # k3d/kind may not support NBD

monitoring:
  serviceMonitor:
    enabled: false  # Prometheus Operator may not be installed
```

```bash
helm install h2kvm-worker ./h2kvm-worker \
  --namespace h2kvm-workers \
  --create-namespace \
  --values minimal-values.yaml
```

### Production Installation

```yaml
# production-values.yaml
worker:
  resources:
    requests:
      cpu: "4"
      memory: "8Gi"
    limits:
      cpu: "16"
      memory: "32Gi"
  expectedCount: 10

storage:
  state:
    size: 50Gi
    storageClass: "ceph-rbd"
  events:
    size: 20Gi
    storageClass: "ceph-rbd"
  input:
    size: 5Ti
    storageClass: "nfs-storage"
  output:
    size: 2Ti
    storageClass: "ceph-rbd-fast"
  temp:
    size: 500Gi
    storageClass: "local-nvme"

monitoring:
  serviceMonitor:
    enabled: true
    labels:
      prometheus: kube-prometheus
  grafanaDashboard:
    enabled: true

alerting:
  enabled: true
```

```bash
helm install h2kvm-worker ./h2kvm-worker \
  --namespace h2kvm-workers \
  --create-namespace \
  --values production-values.yaml
```

## Support

- Documentation: See `k8s/README.md` and `docs/worker/`
- Issues: https://github.com/ssahani/h2kvm/issues
