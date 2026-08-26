# h2kvm Operator Helm Chart

Kubernetes Operator for automated VM migration job orchestration. Converts VMware VMDKs to KVM-compatible qcow2 images with intelligent worker assignment, admission control, and comprehensive monitoring.

## TL;DR

```bash
# Add Helm repository (if published)
helm repo add h2kvm https://ssahani.github.io/h2kvm
helm repo update

# Install with default configuration
helm install h2kvm-operator h2kvm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace

# Install from local directory
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace
```

## Introduction

This chart deploys the h2kvm operator on a Kubernetes cluster using Helm. The operator provides:

- **Automated Job Assignment** - Intelligent worker selection with 100-point scoring algorithm
- **Admission Control** - Validation and mutation webhooks with resource quotas
- **Observability** - 20+ Prometheus metrics and Kubernetes events
- **Production Ready** - HA webhook deployment, TLS certificates, comprehensive testing

## Prerequisites

- Kubernetes 1.24+
- Helm 3.8+
- PV provisioner support (for worker storage)
- (Optional) Prometheus Operator for ServiceMonitor
- (Optional) cert-manager for automated TLS certificate management

## Installing the Chart

### Quick Start

```bash
# Install with default values
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace
```

### Custom Installation

```bash
# Install with custom values
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace \
  --values custom-values.yaml
```

### Example: Production Configuration

```yaml
# production-values.yaml
operator:
  replicaCount: 2  # HA (requires leader election in future)
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 1Gi

  metrics:
    serviceMonitor:
      enabled: true
      labels:
        prometheus: kube-prometheus

webhook:
  enabled: true
  replicaCount: 3  # HA for high availability

  tls:
    certManager:
      enabled: true
      issuerRef:
        name: letsencrypt-prod
        kind: ClusterIssuer

  config:
    maxJobsPerNamespace: 50  # Increase quota for large deployments

monitoring:
  prometheus:
    enabled: true
  alerts:
    enabled: true

networkPolicy:
  enabled: true
```

```bash
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace \
  --values production-values.yaml
```

## Uninstalling the Chart

```bash
# Uninstall release
helm uninstall h2kvm-operator -n h2kvm-system

# CRDs are kept by default (helm.sh/resource-policy: keep)
# To remove CRDs manually:
kubectl delete crd migrationjobs.h2kvm.io
```

## Configuration

See [values.yaml](values.yaml) for full configuration options.

### Key Configuration Parameters

#### Operator Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `operator.image.repository` | Operator image repository | `ghcr.io/ssahani/h2kvm` |
| `operator.image.tag` | Operator image tag | `1.6.0` |
| `operator.replicaCount` | Number of operator replicas | `1` |
| `operator.config.reconcileInterval` | Reconciliation interval (seconds) | `30` |
| `operator.config.logLevel` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `operator.resources.requests.cpu` | Operator CPU request | `100m` |
| `operator.resources.requests.memory` | Operator memory request | `128Mi` |
| `operator.metrics.enabled` | Enable Prometheus metrics | `true` |
| `operator.metrics.serviceMonitor.enabled` | Create ServiceMonitor | `true` |

#### Webhook Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `webhook.enabled` | Enable admission webhooks | `true` |
| `webhook.replicaCount` | Number of webhook replicas (HA) | `2` |
| `webhook.config.maxJobsPerNamespace` | Max active jobs per namespace | `10` |
| `webhook.config.validatingFailurePolicy` | Validating webhook failure policy | `Fail` |
| `webhook.config.mutatingFailurePolicy` | Mutating webhook failure policy | `Ignore` |
| `webhook.tls.certManager.enabled` | Use cert-manager for TLS | `false` |
| `webhook.tls.existingSecret` | Existing TLS secret name | `""` |

#### CRD Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `crd.install` | Install MigrationJob CRD | `true` |
| `crd.keep` | Keep CRD on uninstall | `true` |

#### Certificate Job Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `certJob.enabled` | Enable certificate generation job | `true` |
| `webhook.tls.certValidity` | Certificate validity (days) | `3650` |

## Usage Examples

### Create a Simple Conversion Job

```bash
cat <<EOF | kubectl apply -f -
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: convert-vm-disk
  namespace: default
spec:
  operation: convert
  image:
    path: /data/input/windows-server.vmdk
    format: vmdk
  artifacts:
    output_dir: /data/output
    output_name: windows-server.qcow2
    output_format: qcow2
    compress: true
EOF
```

### Create a High-Priority Job with Custom Settings

```bash
cat <<EOF | kubectl apply -f -
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: priority-conversion
  namespace: default
spec:
  operation: convert
  priority: 90  # High priority
  timeout: 4h
  retryPolicy:
    maxRetries: 3
    backoff: exponential
  image:
    path: /data/input/critical-vm.vmdk
    format: vmdk
    checksum: sha256:abc123...
  artifacts:
    output_dir: /data/output
    output_name: critical-vm.qcow2
    output_format: qcow2
  conversions:
    fstab_mode: stabilize-all
    regen_initramfs: true
EOF
```

### Monitor Job Status

```bash
# Watch job progress
kubectl get migrationjob convert-vm-disk -w

# Detailed status
kubectl describe migrationjob convert-vm-disk

# View events
kubectl get events --field-selector involvedObject.name=convert-vm-disk

# Check assigned worker
kubectl get migrationjob convert-vm-disk -o jsonpath='{.status.assignedWorker}'
```

## Monitoring and Observability

### Prometheus Metrics

The operator exposes 20+ Prometheus metrics on port 8080:

**Operator Metrics:**
- `h2kvm_operator_reconciliation_total`
- `h2kvm_operator_reconciliation_duration_seconds`
- `h2kvm_operator_queue_depth`
- `h2kvm_operator_workers_discovered`
- `h2kvm_operator_jobs_completed_total`

**Webhook Metrics:**
- `h2kvm_operator_webhook_validations_total`
- `h2kvm_operator_webhook_mutations_total`
- `h2kvm_operator_webhook_duration_seconds`

### Access Metrics

```bash
# Port-forward operator
kubectl port-forward -n h2kvm-system svc/h2kvm-operator 8080:8080

# Fetch metrics
curl http://localhost:8080/metrics

# Port-forward webhook
kubectl port-forward -n h2kvm-system svc/h2kvm-operator-webhook 8080:8080
curl http://localhost:8080/metrics
```

### Prometheus Queries

```promql
# Queue depth over time
h2kvm_operator_queue_depth{namespace="default"}

# Job success rate
rate(h2kvm_operator_jobs_completed_total{result="success"}[5m])
/
rate(h2kvm_operator_jobs_completed_total[5m])

# Worker utilization
sum(h2kvm_operator_worker_jobs) by (worker)

# Webhook rejection rate
rate(h2kvm_operator_webhook_validations_total{result="denied"}[5m])
```

## Admission Webhooks

### Validating Webhook

Rejects invalid jobs before creation:

- **Required fields**: operation, image.path, image.format
- **Valid operations**: inspect, convert, offline_fix
- **Valid formats**: vmdk, vdi, vhd, vhdx, qcow2, raw
- **Priority range**: 0-100
- **Timeout format**: \d+(s|m|h), max 24h
- **Resource quotas**: 10 active jobs per namespace (configurable)

### Mutating Webhook

Applies sensible defaults automatically:

- `priority`: 50
- `timeout`: 2h
- `retryPolicy.maxRetries`: 2
- `retryPolicy.backoff`: exponential
- `artifacts.output_format`: qcow2
- Adds creation timestamp annotation
- Adds webhook version annotation

### Testing Admission Control

```bash
# Valid job (should pass)
kubectl apply -f k8s/operator/examples/convert-job.yaml

# Invalid operation (should fail)
cat <<EOF | kubectl apply -f -
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: invalid-job
spec:
  operation: invalid_operation  # Invalid!
  image:
    path: /data/test.vmdk
    format: vmdk
EOF
# Expected: Error from server: admission webhook denied the request
```

## TLS Certificate Management

### Option 1: Self-Signed Certificates (Default)

Automatic certificate generation using cert-job:

```bash
# Certificates are automatically generated during helm install
# Valid for 10 years (configurable)
```

### Option 2: cert-manager (Recommended for Production)

```yaml
# values.yaml
webhook:
  tls:
    certManager:
      enabled: true
      issuerRef:
        name: selfsigned-issuer
        kind: ClusterIssuer

certJob:
  enabled: false  # Disable self-signed cert job
```

### Option 3: Existing Certificate Secret

```bash
# Create certificate secret manually
kubectl create secret tls h2kvm-webhook-certs \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  --namespace h2kvm-system
```

```yaml
# values.yaml
webhook:
  tls:
    existingSecret: h2kvm-webhook-certs

certJob:
  enabled: false  # Disable cert generation job
```

## Upgrading

### Upgrade to Latest Chart Version

```bash
# Update repository
helm repo update

# Upgrade release
helm upgrade h2kvm-operator h2kvm/h2kvm-operator \
  --namespace h2kvm-system \
  --values custom-values.yaml
```

### Upgrade from Local Chart

```bash
helm upgrade h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --values custom-values.yaml
```

### Rollback

```bash
# View release history
helm history h2kvm-operator -n h2kvm-system

# Rollback to previous version
helm rollback h2kvm-operator -n h2kvm-system
```

## Testing

### Run Helm Tests

```bash
# Run built-in tests
helm test h2kvm-operator -n h2kvm-system

# View test pod logs
kubectl logs -n h2kvm-system h2kvm-operator-test-connection
```

Tests verify:
- ✓ Operator health endpoint responds
- ✓ Webhook health endpoint responds
- ✓ MigrationJob CRD is installed

## Troubleshooting

### Operator Not Starting

```bash
# Check operator pods
kubectl get pods -n h2kvm-system -l app.kubernetes.io/component=operator

# View operator logs
kubectl logs -n h2kvm-system -l app.kubernetes.io/component=operator

# Check events
kubectl get events -n h2kvm-system --sort-by='.lastTimestamp'
```

### Webhook Not Working

```bash
# Check webhook pods
kubectl get pods -n h2kvm-system -l app.kubernetes.io/component=webhook

# View webhook logs
kubectl logs -n h2kvm-system -l app.kubernetes.io/component=webhook

# Verify webhook configurations
kubectl get validatingwebhookconfiguration h2kvm-operator-validating -o yaml
kubectl get mutatingwebhookconfiguration h2kvm-operator-mutating -o yaml

# Check webhook service endpoints
kubectl get endpoints -n h2kvm-system h2kvm-operator-webhook

# Verify certificates
kubectl get secret -n h2kvm-system h2kvm-operator-webhook-certs
```

### Jobs Not Being Assigned

```bash
# Check worker pods availability
kubectl get pods -n h2kvm-workers -l app=h2kvm-worker

# View operator reconciliation logs
kubectl logs -n h2kvm-system -l app.kubernetes.io/component=operator | grep reconcile

# Check job status
kubectl describe migrationjob <job-name>

# View metrics
kubectl port-forward -n h2kvm-system svc/h2kvm-operator 8080:8080
curl http://localhost:8080/metrics | grep queue_depth
```

## Security Considerations

### RBAC

The operator requires:
- ClusterRole for CRD and pod access (cluster-wide)
- Role for leader election (namespace-scoped)

### Pod Security

- Runs as non-root user (UID 1000)
- Read-only root filesystem
- Drops all capabilities
- No privilege escalation

### Network Policies

Enable network policies for enhanced security:

```yaml
# values.yaml
networkPolicy:
  enabled: true
```

## Documentation

For comprehensive documentation, see:

- **Architecture**: [docs/architecture/worker-job-protocol.md](../../docs/architecture/worker-job-protocol.md)
- **Operator Guide**: [docs/deployment/v1.4.0-operator.md](../../docs/deployment/v1.4.0-operator.md)
- **Webhook Guide**: [docs/deployment/v1.5.0-webhooks-metrics.md](../../docs/deployment/v1.5.0-webhooks-metrics.md)
- **Main Repository**: https://github.com/ssahani/h2kvm

## Support

- **GitHub Issues**: https://github.com/ssahani/h2kvm/issues
- **Discussions**: https://github.com/ssahani/h2kvm/discussions

## License

See [LICENSE](../../LICENSE)

## Maintainers

- ZyvorAI Labs Private Limited (ssahani@zyvor.dev)

---

**Version**: 1.6.0
**App Version**: 1.6.0
**Chart Type**: application
