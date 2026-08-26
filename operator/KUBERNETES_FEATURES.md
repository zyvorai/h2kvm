# Kubernetes-Native Features

This document describes the Kubernetes-native features implemented in the HyperConversion operator for production readiness.

## Table of Contents

1. [Validation and Mutation Webhooks](#webhooks)
2. [Prometheus Metrics](#prometheus-metrics)
3. [Pod Disruption Budget](#pod-disruption-budget)
4. [Network Policy](#network-policy)
5. [Health Checks](#health-checks)
6. [Certificate Management](#certificate-management)
7. [Deployment Options](#deployment-options)

---

## Webhooks

### Validation Webhook

The operator includes a ValidatingWebhookConfiguration that validates HyperConversion resources before they are created or updated.

**Validations Performed**:
- ✅ **Source URL**: Must be valid HTTP/HTTPS/S3 URL
- ✅ **Format**: Must be vmdk, vdi, vhd, vhdx, qcow2, or raw
- ✅ **Storage Size**: Minimum 1GB (warning if less)
- ✅ **CPU Cores**: Between 1-128
- ✅ **CPU Sockets**: At least 1
- ✅ **CPU Threads**: At least 1
- ✅ **Memory**: Required when VM specified, minimum 512MB (warning)
- ✅ **Firmware**: Must be bios, uefi, or uefi-secure
- ✅ **Network Type**: Must be pod, bridge, sriov, or multus
- ✅ **Network Name**: Required for bridge/multus types
- ✅ **Eviction Strategy**: Warns if LiveMigrate with ReadWriteOnce storage
- ✅ **Conversion Timeout**: Between 5-1440 minutes
- ✅ **Compression**: Must be zstd, zlib, or none

**Example Validation Error**:
```bash
$ kubectl apply -f invalid.yaml
Error from server (Forbidden): error when creating "invalid.yaml":
admission webhook "vhyperconversion.kb.io" denied the request:
source.url must use http, https, or s3 scheme, got: ftp
```

**Example Validation Warning**:
```bash
$ kubectl apply -f small-disk.yaml
Warning: storage.size is less than 1GB, this may be too small for most VM images
Warning: LiveMigrate eviction strategy requires ReadWriteMany access mode for shared storage
hyperconversion.h2kvm.io/test created
```

### Mutation Webhook

The operator includes a MutatingWebhookConfiguration that automatically sets sensible defaults for HyperConversion resources.

**Defaults Set**:
- **Storage Class**: `local-path` (if not specified)
- **Access Mode**: `ReadWriteOnce` (if not specified)
- **Volume Mode**: `Filesystem` (if not specified)
- **Firmware**: `bios` (if VM specified but firmware not set)
- **CPU Cores**: `2` (if VM specified but cores is 0)
- **CPU Sockets**: `1` (if VM specified but sockets is 0)
- **CPU Threads**: `1` (if VM specified but threads is 0)
- **Run Strategy**: `Always` (if VM specified but not set)
- **Eviction Strategy**: `LiveMigrateIfPossible` (if VM specified but not set)
- **Network Type**: `pod` (if network specified but type not set)
- **Network Model**: `virtio` (if network specified but model not set)
- **Compression**: `zstd` (if conversion specified but compression not set)
- **Timeout**: `60` minutes (if conversion specified but timeout is 0)

**Example**:
```yaml
# Input
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: minimal-example
spec:
  source:
    url: "http://example.com/disk.vmdk"
    format: vmdk
  storage:
    size: 20Gi
  vm:
    cpu:
      cores: 4
    memory: 8Gi

# After Mutation (defaults added automatically)
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: minimal-example
spec:
  source:
    url: "http://example.com/disk.vmdk"
    format: vmdk
  storage:
    size: 20Gi
    storageClass: local-path        # Added
    accessMode: ReadWriteOnce       # Added
    volumeMode: Filesystem          # Added
  vm:
    cpu:
      cores: 4
      sockets: 1                    # Added
      threads: 1                    # Added
    memory: 8Gi
    firmware: bios                  # Added
    runStrategy: Always             # Added
    evictionStrategy: LiveMigrateIfPossible  # Added
```

### Enabling Webhooks

**Prerequisites**:
- cert-manager installed in cluster
- Webhook service and certificates configured

**Deploy with Webhooks**:
```bash
# Install cert-manager (if not already installed)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Deploy operator with webhooks enabled
cd operator
kustomize build config/default_with_webhooks | kubectl apply -f -

# Or use custom kustomization
kubectl apply -k config/default
```

**Verify Webhooks**:
```bash
# Check webhook configurations
kubectl get validatingwebhookconfigurations | grep hyperconversion
kubectl get mutatingwebhookconfigurations | grep hyperconversion

# Check webhook service
kubectl get svc -n h2kvm-system webhook-service

# Check certificates
kubectl get certificate -n h2kvm-system
kubectl get secret -n h2kvm-system webhook-server-cert

# Test validation
kubectl apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: test-validation
spec:
  source:
    url: "ftp://invalid.com/disk.vmdk"  # Should fail
    format: vmdk
  storage:
    size: 10Gi
EOF
# Should get: source.url must use http, https, or s3 scheme, got: ftp
```

---

## Prometheus Metrics

### ServiceMonitor

The operator exposes Prometheus metrics via a ServiceMonitor resource (requires Prometheus Operator).

**Metrics Endpoint**: `https://<operator-pod>:8443/metrics`

**Available Metrics** (controller-runtime default metrics):
- `controller_runtime_reconcile_total` - Total reconciliations per controller
- `controller_runtime_reconcile_errors_total` - Reconciliation errors per controller
- `controller_runtime_reconcile_time_seconds` - Reconciliation duration
- `controller_runtime_max_concurrent_reconciles` - Max concurrent reconciles
- `workqueue_depth` - Current depth of workqueue
- `workqueue_adds_total` - Total adds to workqueue
- `workqueue_retries_total` - Total retries from workqueue

**Accessing Metrics**:
```bash
# Port-forward to operator pod
kubectl port-forward -n h2kvm-system deployment/hyperconversion-operator 8443:8443

# Query metrics (if auth disabled)
curl -k https://localhost:8443/metrics

# Or via Prometheus
# Metrics will be automatically scraped if Prometheus Operator is installed
```

**ServiceMonitor Configuration**:
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hyperconversion-operator
  namespace: h2kvm-system
spec:
  selector:
    matchLabels:
      control-plane: controller-manager
  endpoints:
  - port: https
    scheme: https
    path: /metrics
```

**Custom Metrics** (future enhancement):
- Migration duration histogram
- Success/failure counters
- Active migrations gauge
- DataVolume size distribution
- Format conversion counters

---

## Pod Disruption Budget

### Purpose

Ensures high availability by limiting the number of pods that can be down simultaneously during voluntary disruptions (node drains, upgrades, etc.).

**Configuration**:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: hyperconversion-operator-pdb
  namespace: h2kvm-system
spec:
  minAvailable: 1
  selector:
    matchLabels:
      control-plane: controller-manager
```

**Effect**:
- Kubernetes will ensure at least 1 operator pod is running at all times
- Node drains will respect this constraint
- Critical for zero-downtime upgrades

**Verify PDB**:
```bash
kubectl get pdb -n h2kvm-system
kubectl describe pdb hyperconversion-operator-pdb -n h2kvm-system
```

---

## Network Policy

### Purpose

Restricts network traffic to/from the operator pod for enhanced security.

**Ingress Rules**:
- ✅ Allow webhook traffic from API server (port 9443)
- ✅ Allow metrics scraping from Prometheus (port 8443)

**Egress Rules**:
- ✅ Allow DNS queries to kube-dns
- ✅ Allow Kubernetes API server access (ports 443, 6443)
- ✅ Allow CDI and KubeVirt communication (port 443)

**Configuration**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: hyperconversion-operator-netpol
  namespace: h2kvm-system
spec:
  podSelector:
    matchLabels:
      control-plane: controller-manager
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 9443  # Webhook
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 443  # API server, CDI, KubeVirt
```

**Testing Network Policy**:
```bash
# Apply network policy
kubectl apply -f config/network/network-policy.yaml

# Verify policy
kubectl get netpol -n h2kvm-system
kubectl describe netpol hyperconversion-operator-netpol -n h2kvm-system

# Test operator still works
kubectl apply -f config/samples/simple-vmdk-to-vm.yaml
kubectl get hc -w
```

---

## Health Checks

### Liveness Probe

Checks if the operator is alive and should be restarted if unhealthy.

**Endpoint**: `http://<operator-pod>:8081/healthz`

**Configuration**:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8081
  initialDelaySeconds: 15
  periodSeconds: 20
```

### Readiness Probe

Checks if the operator is ready to handle requests.

**Endpoint**: `http://<operator-pod>:8081/readyz`

**Configuration**:
```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8081
  initialDelaySeconds: 5
  periodSeconds: 10
```

**Testing Health Checks**:
```bash
# Port-forward to operator pod
kubectl port-forward -n h2kvm-system deployment/hyperconversion-operator 8081:8081

# Check liveness
curl http://localhost:8081/healthz
# Expected: ok

# Check readiness
curl http://localhost:8081/readyz
# Expected: ok
```

---

## Certificate Management

### cert-manager Integration

The operator uses cert-manager for automatic certificate generation and rotation for webhooks.

**Prerequisites**:
```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --for=condition=Available --timeout=300s deployment/cert-manager -n cert-manager
```

**Certificate Configuration**:
```yaml
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: selfsigned-issuer
  namespace: h2kvm-system
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: serving-cert
  namespace: h2kvm-system
spec:
  dnsNames:
  - webhook-service.h2kvm-system.svc
  - webhook-service.h2kvm-system.svc.cluster.local
  issuerRef:
    kind: Issuer
    name: selfsigned-issuer
  secretName: webhook-server-cert
```

**Verify Certificates**:
```bash
# Check certificate status
kubectl get certificate -n h2kvm-system serving-cert
kubectl describe certificate -n h2kvm-system serving-cert

# Check secret created
kubectl get secret -n h2kvm-system webhook-server-cert

# View certificate details
kubectl get secret -n h2kvm-system webhook-server-cert -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -text -noout
```

---

## Deployment Options

### Standard Deployment (No Webhooks)

```bash
cd operator
make deploy IMG=h2kvm-operator:latest
```

### Deployment with Webhooks

```bash
# Prerequisites
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Deploy operator with webhooks
cd operator
kustomize build config/default_with_webhooks | kubectl apply -f -

# Or modify default kustomization to include webhooks
kubectl apply -k config/default
```

### Deployment with Prometheus

```bash
# Prerequisites: Prometheus Operator installed

# Deploy with ServiceMonitor
cd operator
kubectl apply -f config/prometheus/monitor.yaml

# Verify metrics are being scraped
kubectl get servicemonitor -n h2kvm-system
```

### Deployment with Network Policy

```bash
# Deploy network policy
cd operator
kubectl apply -f config/network/network-policy.yaml

# Verify policy
kubectl get netpol -n h2kvm-system
```

### Complete Production Deployment

```bash
# 1. Install prerequisites
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# 2. Deploy operator with all features
cd operator
kustomize build config/default_with_webhooks | kubectl apply -f -

# 3. Verify deployment
kubectl get pods -n h2kvm-system
kubectl get svc -n h2kvm-system
kubectl get certificate -n h2kvm-system
kubectl get pdb -n h2kvm-system
kubectl get netpol -n h2kvm-system
kubectl get servicemonitor -n h2kvm-system

# 4. Test webhooks
kubectl apply -f config/samples/simple-vmdk-to-vm.yaml
kubectl get hc -w
```

---

## Summary

| Feature | Status | Purpose | Requirements |
|---------|--------|---------|--------------|
| **Validation Webhook** | ✅ Implemented | Validate HyperConversion before creation | cert-manager |
| **Mutation Webhook** | ✅ Implemented | Set sensible defaults | cert-manager |
| **Prometheus Metrics** | ✅ Implemented | Monitoring and alerting | Prometheus Operator (optional) |
| **ServiceMonitor** | ✅ Implemented | Automatic metrics scraping | Prometheus Operator |
| **PodDisruptionBudget** | ✅ Implemented | High availability | None |
| **NetworkPolicy** | ✅ Implemented | Network security | CNI with NetworkPolicy support |
| **Health Checks** | ✅ Implemented | Liveness and readiness | None (built-in) |
| **Certificate Management** | ✅ Implemented | Automatic cert rotation | cert-manager |

All features are production-ready and optional (can be deployed incrementally).
