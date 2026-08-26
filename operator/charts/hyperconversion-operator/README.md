# HyperConversion Operator Helm Chart

Kubernetes operator for automated VM migration to KubeVirt using CDI DataVolumes.

## Prerequisites

- Kubernetes 1.24+
- Helm 3+
- CDI (Containerized Data Importer) installed
- KubeVirt installed
- (Optional) cert-manager for webhook TLS certificates
- (Optional) Prometheus Operator for metrics

## Installing the Chart

```bash
# Add the repository (if published)
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm

# Install with default configuration
helm install hyperconversion hyper2kvm/hyperconversion-operator

# Install with custom values
helm install hyperconversion hyper2kvm/hyperconversion-operator \
  --set image.tag=v1.0.0 \
  --set webhooks.enabled=true \
  --set metrics.serviceMonitor.enabled=true
```

## Configuration

See `values.yaml` for all configuration options.

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Operator image repository | `hyper2kvm-operator` |
| `image.tag` | Operator image tag | `latest` |
| `replicaCount` | Number of operator replicas | `1` |
| `webhooks.enabled` | Enable admission webhooks | `true` |
| `metrics.enabled` | Enable Prometheus metrics | `true` |
| `metrics.serviceMonitor.enabled` | Create ServiceMonitor | `true` |
| `podDisruptionBudget.enabled` | Create PDB | `true` |
| `networkPolicy.enabled` | Create NetworkPolicy | `true` |

## Upgrading

```bash
helm upgrade hyperconversion hyper2kvm/hyperconversion-operator
```

## Uninstalling

```bash
helm uninstall hyperconversion
```

Note: CRDs are kept by default. To remove them:
```bash
kubectl delete crd hyperconversions.hyper2kvm.io
```
