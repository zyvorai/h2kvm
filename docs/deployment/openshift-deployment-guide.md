# Hyper2KVM Operator - OpenShift Deployment Guide

**Version:** 0.3.0
**Date:** 2026-01-30
**Platform:** OpenShift 4.10 - 4.16

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
  - [Method 1: OperatorHub (Recommended)](#method-1-operatorhub-recommended)
  - [Method 2: Helm Chart](#method-2-helm-chart)
  - [Method 3: Manual Deployment](#method-3-manual-deployment)
- [Configuration](#configuration)
- [OpenShift-Specific Features](#openshift-specific-features)
- [Security](#security)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Upgrade Guide](#upgrade-guide)
- [Uninstallation](#uninstallation)

---

## Overview

Hyper2KVM Operator automates VM migration from VMware vSphere to OpenShift Virtualization/KVM. This guide covers deployment on OpenShift Container Platform with platform-specific optimizations.

### Key OpenShift Features

- **OperatorHub Integration**: One-click installation from OperatorHub catalog
- **OpenShift Routes**: Automatic external access to metrics and webhooks
- **SecurityContextConstraints**: Pre-configured SCCs for privileged worker operations
- **OAuth Proxy**: Integrated authentication for metrics endpoints
- **Monitoring Stack**: Native integration with OpenShift monitoring
- **Disconnected Support**: Full air-gapped deployment capability

---

## Prerequisites

### Cluster Requirements

- **OpenShift Version**: 4.10 - 4.16
- **Cluster Role**: `cluster-admin` (for installation)
- **Persistent Storage**: StorageClass with RWO support
- **Worker Nodes**: Nodes with kernel NBD module support

### Resource Requirements

**Operator**:
- CPU: 100m (request), 500m (limit)
- Memory: 128Mi (request), 512Mi (limit)

**Webhook**:
- CPU: 100m (request), 500m (limit)
- Memory: 128Mi (request), 512Mi (limit)

**Worker Pods** (per worker):
- CPU: 2 cores (request), 4 cores (limit)
- Memory: 4Gi (request), 8Gi (limit)
- Storage: 20Gi PVC for state

### Network Requirements

- **Internal**: Pod-to-pod communication (default OpenShift SDN)
- **External**: Optional Routes for metrics/API access
- **Air-Gapped**: Image mirroring to internal registry required

---

## Installation Methods

### Method 1: OperatorHub (Recommended)

Install directly from OpenShift OperatorHub with automatic updates and lifecycle management.

#### Step 1: Access OperatorHub

1. Log in to OpenShift Console
2. Navigate to **Operators** → **OperatorHub**
3. Search for "Hyper2KVM"

#### Step 2: Install Operator

1. Click **Hyper2KVM Operator**
2. Click **Install**
3. Configure installation:

   - **Update Channel**: `stable` (recommended) or `preview`
   - **Installation Mode**:
     - `A specific namespace on the cluster` (recommended)
     - `All namespaces on the cluster`
   - **Installed Namespace**: `hyper2kvm-system` (or custom)
   - **Update Approval**: `Automatic` or `Manual`

4. Click **Install**

#### Step 3: Verify Installation

```bash
# Check operator subscription
oc get subscription -n hyper2kvm-system

# Check CSV (ClusterServiceVersion)
oc get csv -n hyper2kvm-system

# Check operator pod
oc get pods -n hyper2kvm-system -l app.kubernetes.io/name=hyper2kvm-operator

# Check CRDs
oc get crd | grep hyper2kvm
```

Expected output:
```
migrationjobs.hyper2kvm.io
jobtemplates.hyper2kvm.io
```

#### Step 4: Create First Migration Job

```bash
oc apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: example-migration
  namespace: default
spec:
  operation: inspect
  image:
    path: /data/input/example.vmdk
    format: vmdk
  priority: 50
EOF
```

### Method 2: Helm Chart

Install using Helm with full customization capabilities.

#### Step 1: Add Helm Repository

```bash
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm
helm repo update
```

#### Step 2: Create OpenShift Values File

```yaml
# values-openshift.yaml
global:
  namespace: hyper2kvm-system

# Enable OpenShift-specific features
openshift:
  enabled: true
  autoDetect: true

  # Routes for external access
  route:
    enabled: true
    tls:
      termination: edge
      insecureEdgeTerminationPolicy: Redirect

  # SecurityContextConstraints
  scc:
    create: true
    name: hyper2kvm-worker-scc

  # OAuth proxy for authenticated metrics
  oauth:
    enabled: true

# Operator configuration
operator:
  replicaCount: 2  # HA deployment
  leaderElection:
    enabled: true
  resources:
    limits:
      cpu: 500m
      memory: 512Mi
    requests:
      cpu: 100m
      memory: 128Mi

# Webhook configuration
webhook:
  enabled: true
  replicaCount: 2  # HA deployment

# Monitoring
monitoring:
  prometheus:
    enabled: true
  grafana:
    enabled: true
```

#### Step 3: Install with Helm

```bash
# Create namespace
oc new-project hyper2kvm-system

# Install operator
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --values values-openshift.yaml

# Check installation
oc get all -n hyper2kvm-system
```

#### Step 4: Access Metrics Route

```bash
# Get metrics route URL
METRICS_URL=$(oc get route hyper2kvm-operator-metrics -n hyper2kvm-system -o jsonpath='{.spec.host}')
echo "Metrics: https://$METRICS_URL/metrics"

# Access via browser (requires authentication via OpenShift OAuth)
curl -k https://$METRICS_URL/metrics
```

### Method 3: Manual Deployment

Deploy using raw Kubernetes manifests.

#### Step 1: Install CRDs

```bash
oc apply -f k8s/operator/crds/
```

#### Step 2: Create SecurityContextConstraints

```bash
oc apply -f - <<EOF
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: hyper2kvm-worker-scc
allowPrivilegedContainer: true
allowHostNetwork: false
allowHostPorts: false
allowHostPID: false
allowHostIPC: false
requiredDropCapabilities:
  - KILL
  - MKNOD
  - SETUID
  - SETGID
allowedCapabilities:
  - SYS_ADMIN
  - SYS_MODULE
  - SYS_RAWIO
seLinuxContext:
  type: MustRunAs
runAsUser:
  type: RunAsAny
fsGroup:
  type: RunAsAny
supplementalGroups:
  type: RunAsAny
volumes:
  - configMap
  - downwardAPI
  - emptyDir
  - persistentVolumeClaim
  - projected
  - secret
  - hostPath
priority: 10
EOF
```

#### Step 3: Deploy Operator

```bash
# Create namespace
oc new-project hyper2kvm-system

# Apply operator manifests
oc apply -f k8s/operator/
```

---

## Configuration

### OpenShift-Specific Configuration

#### Routes

Routes provide external access to operator services.

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: hyper2kvm-metrics
  namespace: hyper2kvm-system
spec:
  to:
    kind: Service
    name: hyper2kvm-operator-metrics
  port:
    targetPort: metrics
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

#### SecurityContextConstraints

Workers require privileged access for NBD, mount, and LVM operations.

**Grant SCC to ServiceAccount**:

```bash
oc adm policy add-scc-to-user hyper2kvm-worker-scc \
  -z hyper2kvm-worker \
  -n hyper2kvm-workers
```

**Verify SCC Assignment**:

```bash
oc describe scc hyper2kvm-worker-scc
oc get pod <worker-pod> -n hyper2kvm-workers -o yaml | grep scc
```

#### OAuth Proxy

Enable OAuth proxy for authenticated metrics access.

**Configuration**:

```yaml
openshift:
  oauth:
    enabled: true
    image:
      repository: quay.io/openshift/origin-oauth-proxy
      tag: "4.14"
    resources:
      limits:
        cpu: 100m
        memory: 64Mi
```

**Access Metrics**:

```bash
# Get route
ROUTE=$(oc get route hyper2kvm-operator-metrics -o jsonpath='{.spec.host}')

# Access with OpenShift token
TOKEN=$(oc whoami -t)
curl -k -H "Authorization: Bearer $TOKEN" https://$ROUTE/metrics
```

---

## OpenShift-Specific Features

### 1. OpenShift Monitoring Integration

Operator metrics integrate with OpenShift's built-in monitoring stack.

**Enable ServiceMonitor**:

```yaml
monitoring:
  prometheus:
    enabled: true
```

**Access Metrics in Console**:

1. Navigate to **Observe** → **Metrics**
2. Query: `hyper2kvm_operator_reconciliation_duration_seconds`

**Create Alerts**:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hyper2kvm-alerts
  namespace: hyper2kvm-system
spec:
  groups:
    - name: hyper2kvm
      interval: 30s
      rules:
        - alert: MigrationJobFailed
          expr: hyper2kvm_operator_job_failures_total > 5
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "High migration job failure rate"
            description: "More than 5 jobs have failed in the last 5 minutes"
```

### 2. OpenShift Web Console Integration

Operator appears in OpenShift Console with custom UI.

**Features**:
- View MigrationJobs in **Workloads** → **MigrationJobs**
- Create jobs via YAML editor
- Monitor job status in real-time
- Access logs directly from console

### 3. Image Registry Integration

Use internal OpenShift registry for operator images.

```bash
# Tag and push to internal registry
oc tag ghcr.io/ssahani/hyper2kvm:2.0.0-operator \
  hyper2kvm-operator:2.0.0 \
  --reference-policy=local

# Update deployment to use internal image
oc set image deployment/hyper2kvm-operator \
  operator=image-registry.openshift-image-registry.svc:5000/hyper2kvm-system/hyper2kvm-operator:2.0.0
```

### 4. Disconnected/Air-Gapped Deployment

Full support for disconnected OpenShift clusters.

**Step 1: Mirror Images**

```bash
# Mirror operator images
oc image mirror \
  ghcr.io/ssahani/hyper2kvm:2.0.0-operator=internal-registry.example.com/hyper2kvm/operator:2.0.0 \
  ghcr.io/ssahani/hyper2kvm:2.0.0-worker=internal-registry.example.com/hyper2kvm/worker:2.0.0
```

**Step 2: Create ImageContentSourcePolicy**

```yaml
apiVersion: operator.openshift.io/v1alpha1
kind: ImageContentSourcePolicy
metadata:
  name: hyper2kvm-mirror
spec:
  repositoryDigestMirrors:
    - mirrors:
        - internal-registry.example.com/hyper2kvm
      source: ghcr.io/ssahani
```

**Step 3: Deploy Bundle**

```bash
operator-sdk run bundle internal-registry.example.com/hyper2kvm/bundle:v2.0.0
```

---

## Security

### Pod Security

Operator pods run with restricted security context:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

**Worker pods** require elevated privileges (via SCC):

```yaml
securityContext:
  privileged: true
  capabilities:
    add:
      - SYS_ADMIN
      - SYS_MODULE
      - SYS_RAWIO
```

### RBAC

Operator requires cluster-wide permissions:

- **MigrationJobs**: Full CRUD
- **Pods**: Read-only (worker discovery)
- **ConfigMaps**: Read/Write (leader election)
- **Events**: Create/Patch
- **SecurityContextConstraints**: Use
- **Routes**: Full CRUD

### Network Policies

Restrict network traffic to operator pods:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: hyper2kvm-operator
  namespace: hyper2kvm-system
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: hyper2kvm-operator
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - namespaceSelector: {}
```

---

## Monitoring

### Prometheus Metrics

**Operator Metrics**:
- `hyper2kvm_operator_reconciliation_duration_seconds` - Reconciliation duration
- `hyper2kvm_operator_job_total` - Total jobs
- `hyper2kvm_operator_job_failures_total` - Failed jobs
- `hyper2kvm_operator_worker_count` - Active workers
- `hyper2kvm_operator_is_leader` - Leader election status

**Access Metrics**:

```bash
# Port-forward to metrics endpoint
oc port-forward -n hyper2kvm-system svc/hyper2kvm-operator-metrics 8080:8080

# Query metrics
curl http://localhost:8080/metrics
```

### Grafana Dashboards

Import pre-built Grafana dashboard:

```bash
oc apply -f k8s/monitoring/dashboards/
```

**Dashboard Panels**:
- Active jobs
- Success rate
- Duration percentiles
- Worker utilization
- Storage usage

### Alerting

Configure alerts in OpenShift Alertmanager:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hyper2kvm-alerts
  namespace: hyper2kvm-system
spec:
  groups:
    - name: hyper2kvm
      rules:
        - alert: OperatorDown
          expr: up{job="hyper2kvm-operator"} == 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Hyper2KVM Operator is down"
```

---

## Troubleshooting

### Common Issues

#### 1. Operator Pod Not Starting

**Symptoms**: Operator pod in `CrashLoopBackOff`

**Debug**:

```bash
# Check pod logs
oc logs -n hyper2kvm-system -l app.kubernetes.io/name=hyper2kvm-operator

# Check events
oc get events -n hyper2kvm-system --sort-by='.lastTimestamp'

# Check pod describe
oc describe pod -n hyper2kvm-system -l app.kubernetes.io/name=hyper2kvm-operator
```

**Common Causes**:
- Missing RBAC permissions
- Image pull errors
- ConfigMap mount failures

#### 2. Worker Pods Failing SCC Checks

**Symptoms**: Worker pods stuck in `CreateContainerConfigError`

**Debug**:

```bash
# Check SCC assignment
oc get pod <worker-pod> -o yaml | grep openshift.io/scc

# List SCCs for ServiceAccount
oc describe scc hyper2kvm-worker-scc
```

**Fix**:

```bash
# Grant SCC to worker ServiceAccount
oc adm policy add-scc-to-user hyper2kvm-worker-scc \
  -z hyper2kvm-worker \
  -n hyper2kvm-workers
```

#### 3. Route Not Accessible

**Symptoms**: Cannot access metrics route

**Debug**:

```bash
# Check route
oc get route -n hyper2kvm-system

# Check route status
oc describe route hyper2kvm-operator-metrics -n hyper2kvm-system

# Check router logs
oc logs -n openshift-ingress -l app=router
```

**Fix**:

```bash
# Recreate route
oc delete route hyper2kvm-operator-metrics -n hyper2kvm-system
oc apply -f helm/hyper2kvm-operator/templates/openshift-route.yaml
```

#### 4. Webhook Certificate Errors

**Symptoms**: Admission webhook failing with TLS errors

**Debug**:

```bash
# Check webhook configuration
oc get validatingwebhookconfiguration,mutatingwebhookconfiguration | grep hyper2kvm

# Check certificate secret
oc get secret -n hyper2kvm-system | grep webhook-certs
```

**Fix**:

```bash
# Regenerate certificates
./scripts/generate-webhook-certs.sh hyper2kvm-system hyper2kvm-webhook
```

### Debug Commands

```bash
# Get all hyper2kvm resources
oc get all -n hyper2kvm-system -l app.kubernetes.io/part-of=hyper2kvm

# Check MigrationJobs
oc get migrationjobs --all-namespaces

# Describe specific job
oc describe migrationjob <job-name> -n <namespace>

# Check worker registry
oc logs -n hyper2kvm-system -l app.kubernetes.io/component=operator | grep "Worker registered"

# Check leader election
oc get lease -n hyper2kvm-system
```

---

## Upgrade Guide

### Upgrading via OperatorHub

**Automatic Upgrades** (if enabled):

```bash
# Check current version
oc get csv -n hyper2kvm-system

# Check available updates
oc get subscription hyper2kvm-operator -n hyper2kvm-system -o yaml
```

**Manual Upgrades**:

1. Navigate to **Operators** → **Installed Operators**
2. Click **Hyper2KVM Operator**
3. Click **Upgrade available**
4. Review changes
5. Click **Approve**

### Upgrading via Helm

```bash
# Update Helm repo
helm repo update

# Check available versions
helm search repo hyper2kvm/hyper2kvm-operator --versions

# Upgrade to latest
helm upgrade hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --values values-openshift.yaml

# Rollback if needed
helm rollback hyper2kvm-operator -n hyper2kvm-system
```

### Migration from v1.x to v2.0

**Breaking Changes**:
- CRD schema updated (v1alpha1)
- New metrics names
- Updated RBAC permissions

**Migration Steps**:

1. Backup existing jobs:

```bash
oc get migrationjobs --all-namespaces -o yaml > migrationjobs-backup.yaml
```

2. Upgrade operator
3. Verify CRD updates:

```bash
oc get crd migrationjobs.hyper2kvm.io -o yaml
```

4. Update existing jobs if needed

---

## Uninstallation

### Via OperatorHub

1. Navigate to **Operators** → **Installed Operators**
2. Find **Hyper2KVM Operator**
3. Click **Actions** → **Uninstall Operator**
4. Confirm uninstallation

**Cleanup CRDs** (optional - deletes all jobs!):

```bash
oc delete crd migrationjobs.hyper2kvm.io
oc delete crd jobtemplates.hyper2kvm.io
```

### Via Helm

```bash
# Uninstall operator
helm uninstall hyper2kvm-operator -n hyper2kvm-system

# Delete namespace
oc delete project hyper2kvm-system

# Delete CRDs (optional)
oc delete crd migrationjobs.hyper2kvm.io jobtemplates.hyper2kvm.io
```

### Via Manual

```bash
# Delete operator deployment
oc delete -f k8s/operator/

# Delete CRDs
oc delete -f k8s/operator/crds/

# Delete SCC
oc delete scc hyper2kvm-worker-scc

# Delete namespace
oc delete project hyper2kvm-system
```

---

## Additional Resources

- [Helm Chart README](../../helm/hyper2kvm-operator/README.md)
- [OLM Bundle Guide](../../olm/README.md)
- [Worker Protocol Spec](../worker/PROTOCOL_SPEC.md)
- [Comprehensive v2.0 Features](v2.0.0-comprehensive-features.md)
- [GitHub Repository](https://github.com/ssahani/hyper2kvm)

---

**Support**: https://github.com/ssahani/hyper2kvm/issues
**License**: MIT
