# Helm Repository Guide

Official Helm chart repository for hyper2kvm - VM migration toolkit for Kubernetes.

**Repository URL**: `https://ssahani.github.io/hyper2kvm`

---

## Quick Start

### Add Repository

```bash
# Add hyper2kvm Helm repository
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm

# Update repository index
helm repo update

# Verify repository
helm search repo hyper2kvm
```

Expected output:
```
NAME                            CHART VERSION   APP VERSION     DESCRIPTION
hyper2kvm/hyper2kvm-operator    1.6.0           1.6.0           Kubernetes Operator for automated VM migration...
hyper2kvm/hyper2kvm-worker      1.2.0           1.2.0           Worker pods for VM migration execution
```

### Install Charts

**Operator Chart:**
```bash
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --create-namespace
```

**Worker Chart:**
```bash
helm install hyper2kvm-worker hyper2kvm/hyper2kvm-worker \
  --namespace hyper2kvm-workers \
  --create-namespace
```

---

## Available Charts

### hyper2kvm-operator

**Description**: Kubernetes Operator for automated VM migration job orchestration

**Features:**
- Automated job assignment with intelligent worker selection
- Admission webhooks with validation and mutation
- Resource quotas (10 active jobs per namespace, configurable)
- 20+ Prometheus metrics
- HA webhook deployment
- Automated TLS certificate management

**Installation:**
```bash
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --create-namespace \
  --set webhook.enabled=true \
  --set webhook.replicaCount=2
```

**Chart README**: [hyper2kvm-operator/README.md](../helm/hyper2kvm-operator/README.md)

**Documentation**: [Operator Deployment Guide](deployment/v1.6.0-helm-chart.md)

### hyper2kvm-worker

**Description**: Worker pods for VM migration execution

**Features:**
- DaemonSet or Deployment modes
- Persistent storage for input/output/temp
- Prometheus metrics with Grafana dashboard
- Job queue with JSONL event streaming
- 10-state job lifecycle

**Installation:**
```bash
helm install hyper2kvm-worker hyper2kvm/hyper2kvm-worker \
  --namespace hyper2kvm-workers \
  --create-namespace \
  --set worker.replicas=3
```

**Chart README**: [hyper2kvm-worker/README.md](../helm/hyper2kvm-worker/README.md)

**Documentation**: [Worker Protocol Summary](deployment/WORKER_PROTOCOL_SUMMARY.md)

---

## Common Operations

### Search Charts

```bash
# Search all charts
helm search repo hyper2kvm

# Search with versions
helm search repo hyper2kvm --versions

# Search specific chart
helm search repo hyper2kvm/hyper2kvm-operator
```

### Show Chart Information

```bash
# Show chart metadata
helm show chart hyper2kvm/hyper2kvm-operator

# Show default values
helm show values hyper2kvm/hyper2kvm-operator

# Show README
helm show readme hyper2kvm/hyper2kvm-operator

# Show all information
helm show all hyper2kvm/hyper2kvm-operator
```

### Customize Installation

**Create custom values file:**

```yaml
# custom-values.yaml
operator:
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 1Gi

webhook:
  enabled: true
  replicaCount: 3
  config:
    maxJobsPerNamespace: 50

  tls:
    certManager:
      enabled: true
      issuerRef:
        name: letsencrypt-prod
        kind: ClusterIssuer

monitoring:
  prometheus:
    enabled: true
  alerts:
    enabled: true
```

**Install with custom values:**

```bash
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --create-namespace \
  --values custom-values.yaml
```

### Upgrade Charts

```bash
# Update repository index
helm repo update

# Upgrade to latest version
helm upgrade hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --values custom-values.yaml

# Upgrade to specific version
helm upgrade hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --version 1.7.0
```

### List Installed Charts

```bash
# List all releases
helm list --all-namespaces

# List in specific namespace
helm list -n hyper2kvm-system
```

### Uninstall Charts

```bash
# Uninstall operator
helm uninstall hyper2kvm-operator -n hyper2kvm-system

# Uninstall worker
helm uninstall hyper2kvm-worker -n hyper2kvm-workers

# CRDs are kept by default (helm.sh/resource-policy: keep)
# To remove CRDs manually:
kubectl delete crd migrationjobs.hyper2kvm.io
```

---

## Version Management

### Semantic Versioning

Charts follow [semantic versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., 1.6.0)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes

### Version Compatibility

| Chart Version | Kubernetes | Helm |
|---------------|-----------|------|
| 1.6.x         | 1.24+     | 3.8+ |
| 1.7.x         | 1.24+     | 3.8+ |

### Viewing Available Versions

```bash
# Show all available versions
helm search repo hyper2kvm/hyper2kvm-operator --versions

# Output:
# NAME                            CHART VERSION   APP VERSION     DESCRIPTION
# hyper2kvm/hyper2kvm-operator    1.7.0           1.7.0           Kubernetes Operator...
# hyper2kvm/hyper2kvm-operator    1.6.0           1.6.0           Kubernetes Operator...
# hyper2kvm/hyper2kvm-operator    1.5.0           1.5.0           Kubernetes Operator...
```

### Installing Specific Version

```bash
# Install specific chart version
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --version 1.6.0 \
  --namespace hyper2kvm-system \
  --create-namespace
```

---

## Production Deployment

### Complete Production Setup

```bash
# 1. Add repository
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm
helm repo update

# 2. Create namespaces
kubectl create namespace hyper2kvm-system
kubectl create namespace hyper2kvm-workers

# 3. Install cert-manager (for TLS)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# 4. Create cluster issuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
EOF

# 5. Create production values
cat > production-values.yaml <<EOF
operator:
  resources:
    requests: {cpu: 200m, memory: 256Mi}
    limits: {cpu: 1000m, memory: 1Gi}

webhook:
  enabled: true
  replicaCount: 3
  config:
    maxJobsPerNamespace: 100
  tls:
    certManager:
      enabled: true
      issuerRef:
        name: selfsigned-issuer
        kind: ClusterIssuer

monitoring:
  prometheus:
    enabled: true
  alerts:
    enabled: true

networkPolicy:
  enabled: true
EOF

# 6. Install operator
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --values production-values.yaml \
  --wait

# 7. Verify installation
kubectl get pods -n hyper2kvm-system
helm test hyper2kvm-operator -n hyper2kvm-system

# 8. Install workers (if needed)
helm install hyper2kvm-worker hyper2kvm/hyper2kvm-worker \
  --namespace hyper2kvm-workers \
  --set worker.replicas=5 \
  --wait
```

---

## Troubleshooting

### Repository Not Found

```bash
# Remove and re-add repository
helm repo remove hyper2kvm
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm
helm repo update
```

### Chart Not Found

```bash
# Update repository index
helm repo update

# Verify repository URL
helm repo list

# Check GitHub Pages is deployed
curl -I https://ssahani.github.io/hyper2kvm/index.yaml
```

### Installation Fails

```bash
# Check Kubernetes version
kubectl version

# Verify Helm version
helm version

# Lint chart locally
helm lint hyper2kvm/hyper2kvm-operator

# Dry run installation
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --dry-run --debug
```

### Upgrade Fails

```bash
# View current values
helm get values hyper2kvm-operator -n hyper2kvm-system

# View release history
helm history hyper2kvm-operator -n hyper2kvm-system

# Rollback if needed
helm rollback hyper2kvm-operator -n hyper2kvm-system
```

---

## Development

### Using Local Charts

If you're developing charts locally, you can install from the filesystem:

```bash
# Install from local directory
helm install hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --create-namespace

# Upgrade from local directory
helm upgrade hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system
```

### Testing Charts

```bash
# Lint chart
helm lint ./helm/hyper2kvm-operator

# Template chart (no installation)
helm template hyper2kvm-operator ./helm/hyper2kvm-operator

# Dry run installation
helm install hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --dry-run --debug

# Run Helm tests
helm test hyper2kvm-operator -n hyper2kvm-system
```

---

## CI/CD Integration

### GitOps with ArgoCD

```yaml
# argocd-application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: hyper2kvm-operator
  namespace: argocd
spec:
  project: default
  source:
    chart: hyper2kvm-operator
    repoURL: https://ssahani.github.io/hyper2kvm
    targetRevision: 1.6.0
    helm:
      valueFiles:
        - values-production.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: hyper2kvm-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### GitOps with Flux

```yaml
# helmrelease.yaml
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: hyper2kvm-operator
  namespace: hyper2kvm-system
spec:
  interval: 10m
  chart:
    spec:
      chart: hyper2kvm-operator
      version: 1.6.0
      sourceRef:
        kind: HelmRepository
        name: hyper2kvm
        namespace: flux-system
  values:
    webhook:
      enabled: true
      replicaCount: 3
```

---

## Support

### Documentation

- **Chart READMEs**:
  - [Operator Chart](../helm/hyper2kvm-operator/README.md)
  - [Worker Chart](../helm/hyper2kvm-worker/README.md)

- **Deployment Guides**:
  - [Operator Deployment (v1.6.0)](deployment/v1.6.0-helm-chart.md)
  - [Worker Protocol Summary](deployment/WORKER_PROTOCOL_SUMMARY.md)

### Community

- **GitHub Issues**: [Report bugs](https://github.com/ssahani/hyper2kvm/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ssahani/hyper2kvm/discussions)
- **Repository**: [https://github.com/ssahani/hyper2kvm](https://github.com/ssahani/hyper2kvm)

---

## Release Process

For maintainers publishing new chart versions:

1. **Bump Chart Version**:
   ```bash
   ./scripts/bump-chart-version.sh --chart hyper2kvm-operator --type minor
   ```

2. **Package Charts**:
   ```bash
   ./scripts/package-charts.sh --update-index
   ```

3. **Create Git Tag**:
   ```bash
   git tag v1.7.0
   git push origin v1.7.0
   ```

4. **GitHub Actions** automatically:
   - Lints charts
   - Packages charts
   - Publishes to GitHub Pages
   - Creates GitHub Release

See [Release Documentation](../scripts/README.md) for details.

---

**Repository**: https://ssahani.github.io/hyper2kvm
**Source Code**: https://github.com/ssahani/hyper2kvm
**License**: Apache-2.0
