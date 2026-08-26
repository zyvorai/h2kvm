# 🚀 Advanced Migration Features

hyper2kvm provides enterprise-grade features for complex migration scenarios.

## 📊 Table of Contents

1. [Prometheus Metrics & Monitoring](#prometheus-metrics)
2. [Webhook Validation](#webhook-validation)
3. [Multi-Disk Migration](#multi-disk-migration)
4. [Dry-Run Mode](#dry-run-mode)

---

## 📊 Prometheus Metrics

### Overview

hyper2kvm exports comprehensive Prometheus metrics for observability and monitoring.

### Available Metrics

#### Migration Lifecycle
```promql
# Total migrations created
hyper2kvm_migrations_total{namespace="default", source_type="vmdk-url"}

# Successful migrations
hyper2kvm_migrations_succeeded_total{namespace="default", source_type="vmdk-url"}

# Failed migrations
hyper2kvm_migrations_failed_total{namespace="default", source_type="vmdk-url", reason="upload_failed"}

# Active migrations by phase
hyper2kvm_migrations_active{namespace="default", phase="Migrating"}

# Migration duration (histogram)
hyper2kvm_migration_duration_seconds{namespace="default", source_type="vmdk-url"}
```

#### Multi-Disk Metrics
```promql
# Multi-disk migrations
hyper2kvm_multi_disk_migrations_total{namespace="default", disk_count="3"}

# Per-disk migration duration
hyper2kvm_disk_migration_duration_seconds{namespace="default", disk_index="0"}
```

#### Dry-Run Metrics
```promql
# Dry-run validations
hyper2kvm_dry_run_validations_total{namespace="default", result="success"}

# Issues found during dry-run
hyper2kvm_dry_run_issues_found_total{namespace="default", issue_type="insufficient_storage"}
```

#### Compression Metrics
```promql
# Compression ratio achieved
hyper2kvm_conversion_compression_ratio{namespace="default", format="qcow2"}
```

#### VM Metrics
```promql
# VMs created
hyper2kvm_vms_created_total{namespace="default", auto_started="true"}

# VMs currently running
hyper2kvm_vms_running{namespace="default"}
```

#### Webhook Metrics
```promql
# Webhook validations
hyper2kvm_operator_webhook_validations_total{result="allowed"}
```

### Setup

#### 1. Install Prometheus

```bash
# Using Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack
```

#### 2. Configure ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hyper2kvm-operator
  namespace: hyper2kvm-system
spec:
  selector:
    matchLabels:
      app: hyper2kvm-operator
  endpoints:
    - port: metrics
      interval: 30s
```

#### 3. Deploy Grafana Dashboard

```bash
kubectl create configmap hyper2kvm-dashboard \\
  --from-file=k8s/monitoring/grafana-dashboard.json \\
  -n monitoring

kubectl label configmap hyper2kvm-dashboard \\
  grafana_dashboard=1 \\
  -n monitoring
```

### Grafana Dashboard

The included Grafana dashboard (`k8s/monitoring/grafana-dashboard.json`) provides:

- ✅ Migration success rate (%)
- ✅ Active migrations count
- ✅ Migration rate over time
- ✅ Success vs failure graphs
- ✅ Migrations by phase (stacked)
- ✅ Duration percentiles (p50, p90, p99)
- ✅ Compression ratios
- ✅ Multi-disk migration tracking
- ✅ Dry-run validation results
- ✅ Top failure reasons (table)

### Example Queries

**Success Rate (Last 5m)**:
```promql
sum(rate(hyper2kvm_migrations_succeeded_total[5m])) /
sum(rate(hyper2kvm_migrations_total[5m])) * 100
```

**Average Migration Duration**:
```promql
avg(rate(hyper2kvm_migration_duration_seconds_sum[5m]) /
    rate(hyper2kvm_migration_duration_seconds_count[5m]))
```

**P99 Migration Duration**:
```promql
histogram_quantile(0.99,
  sum(rate(hyper2kvm_migration_duration_seconds_bucket[5m])) by (le)
)
```

### Alerting Rules

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hyper2kvm-alerts
spec:
  groups:
    - name: hyper2kvm
      rules:
        - alert: HighMigrationFailureRate
          expr: |
            (sum(rate(hyper2kvm_migrations_failed_total[5m])) /
             sum(rate(hyper2kvm_migrations_total[5m]))) > 0.2
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "High migration failure rate"
            description: "{{ $value | humanizePercentage }} of migrations are failing"

        - alert: MigrationStuck
          expr: |
            hyper2kvm_migrations_active{phase!="Completed"} > 0
          for: 2h
          labels:
            severity: warning
          annotations:
            summary: "Migration stuck for > 2h"
            description: "Migration in phase {{ $labels.phase }} for > 2h"

        - alert: NoActiveWorkers
          expr: |
            hyper2kvm_operator_workers_available == 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "No migration workers available"
```

---

## ✅ Webhook Validation

### Overview

Admission webhooks validate MigrationJob resources before creation, preventing invalid configurations.

### What Gets Validated

1. **Required Fields**
   - source, destination are present
   - source.vmdk.url for vmdk-url type
   - destination.size is specified

2. **Field Format**
   - URLs are HTTP(S)
   - Sizes match pattern: `10Gi`, `20Gi`
   - CPU is numeric
   - Memory matches pattern: `2Gi`, `4Gi`

3. **Resource Existence**
   - Source PVCs exist (if type=vmdk-pvc)
   - StorageClass is valid

4. **Cross-Field Validation**
   - Destination size reasonable for VM
   - Multi-disk configurations are consistent

### Setup

#### 1. Create Webhook Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: hyper2kvm-webhook
  namespace: hyper2kvm-system
spec:
  selector:
    app: hyper2kvm-operator
  ports:
    - port: 443
      targetPort: 8443
```

#### 2. Create ValidatingWebhookConfiguration

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: hyper2kvm-validation
webhooks:
  - name: validate.migrationjobs.hyper2kvm.io
    admissionReviewVersions: ["v1"]
    sideEffects: None
    rules:
      - operations: ["CREATE", "UPDATE"]
        apiGroups: ["hyper2kvm.io"]
        apiVersions: ["v1alpha1"]
        resources: ["migrationjobs"]
    clientConfig:
      service:
        name: hyper2kvm-webhook
        namespace: hyper2kvm-system
        path: /validate
      caBundle: <base64-ca-cert>
    failurePolicy: Fail
```

### Example: Validation Failure

```bash
$ kubectl apply -f invalid-migration.yaml

Error from server (Invalid): error when creating "invalid-migration.yaml":
admission webhook "validate.migrationjobs.hyper2kvm.io" denied the request:
Validation failed:
  - source.vmdk.url is required for source.type=vmdk-url
  - destination.size is required
  - Invalid memory format: 2G. Expected format: 2Gi, 4Gi, etc.

Warnings:
  - Destination size 1Gi is very small for a VM. Consider at least 10Gi
```

---

## 💾 Multi-Disk Migration

### Overview

Migrate VMs with multiple disks (OS disk + data disks) in a single operation.

**Libvirt domain XML** now natively supports multi-disk VMs via the `additional_disks` configuration field. When an OVA/OVF contains multiple disk references, or when `govc vm.info -json` reports multiple disks, all disks are rendered as separate `<disk>` elements (vda, vdb, vdc, ...) in the generated domain XML.

### Multi-NIC Support

VMs with multiple network interfaces are automatically detected from OVF metadata (`ResourceType=10` Ethernet Adapter items) or `govc vm.info -json` (devices with `macAddress`). The detected `nic_count` generates multiple `<interface>` elements in the libvirt domain XML, each with `virtio` model on the default network. The first NIC preserves any configured MAC address.

### Secure Boot Detection

Secure Boot is auto-detected from two sources:
1. **OVF metadata** — `vmw:Config` with `bootOptions.efiSecureBootEnabled=TRUE`
2. **Guest EFI binaries** — offline fixer scans for shim binaries (`shimx64.efi`) in standard paths for Fedora, RHEL, CentOS, Ubuntu, Debian, and SUSE

When detected, the Linux domain XML uses `.secboot.fd` OVMF firmware and adds `secure='yes'` to the `<loader>` element.

### Use Cases

- **Database VMs**: OS disk + data disk + log disk
- **Application Servers**: OS disk + application data disk
- **Windows VMs**: C: drive + D: drive + E: drive

### Example

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: multi-disk-vm
spec:
  source:
    type: multi-disk
    disks:
      - name: os-disk
        type: vmdk-url
        vmdk:
          url: "https://storage/os.vmdk"
        bootOrder: 1
        bus: virtio

      - name: data-disk
        type: vmdk-url
        vmdk:
          url: "https://storage/data.vmdk"
        bus: virtio

  destination:
    pvcs:
      - name: vm-os
        diskName: os-disk
        storageClass: fast-ssd
        size: 50Gi

      - name: vm-data
        diskName: data-disk
        storageClass: standard
        size: 500Gi

  createVM:
    enabled: true
    cpu: "8"
    memory: 16Gi
```

### How It Works

1. **Upload Phase**: All VMDK files uploaded in parallel
2. **Migration Phase**: Disks migrated one by one (sequential)
3. **VM Creation**: All PVCs attached to single VM

### Monitoring

```bash
# Check multi-disk progress
kubectl get migrationjob multi-disk-vm -o yaml | grep -A 20 multiDiskProgress

# Output:
# multiDiskProgress:
#   totalDisks: 2
#   completedDisks: 1
#   currentDisk: data-disk
#   diskStatus:
#   - name: os-disk
#     phase: Completed
#     pvcName: vm-os
#     size: 50Gi
#   - name: data-disk
#     phase: Migrating
#     pvcName: vm-data
```

### Metrics

```promql
# Multi-disk migrations
hyper2kvm_multi_disk_migrations_total{disk_count="2"}

# Per-disk duration
hyper2kvm_disk_migration_duration_seconds{disk_index="0"}  # First disk
hyper2kvm_disk_migration_duration_seconds{disk_index="1"}  # Second disk
```

### Best Practices

1. **OS disk first**: Set `bootOrder: 1` on OS disk
2. **Storage classes**: Use fast storage for OS, standard for data
3. **Sizing**: Allocate appropriate sizes per disk
4. **Bus type**: Use `virtio` for best performance

---

## 🧪 Dry-Run Mode

### Overview

Validate migrations without executing them. Perfect for:
- Pre-migration checks
- CI/CD validation
- Capacity planning
- Troubleshooting

### Example

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: validate-migration
spec:
  dryRun: true  # Enable dry-run mode

  validationOptions:
    checkStorageAvailability: true
    checkNodeResources: true
    checkKubeVirt: true
    checkNBDCapability: true

  source:
    type: vmdk-url
    vmdk:
      url: "https://storage/vm.vmdk"

  destination:
    storageClass: longhorn
    size: 50Gi

  createVM:
    enabled: true
    cpu: "16"
    memory: 32Gi
```

### Validation Checks

#### 1. Storage Availability
- ✅ StorageClass exists
- ✅ Sufficient capacity available
- ✅ PVC can be created

#### 2. Node Resources
- ✅ Sufficient CPU for VM
- ✅ Sufficient memory for VM
- ✅ NBD-capable nodes exist

#### 3. KubeVirt Installation
- ✅ KubeVirt CRDs exist
- ✅ VirtualMachine can be created

#### 4. Source Accessibility
- ✅ VMDK URL is reachable
- ✅ Source PVC exists (if applicable)

### Results

```bash
$ kubectl get migrationjob validate-migration -o yaml

status:
  phase: DryRunCompleted
  dryRunValidation:
    valid: true
    errors: []
    warnings:
      - "StorageClass 'longhorn' has 80% capacity used"
      - "Requesting 16 CPU cores, nodes have 32 available"
    checks:
      storageAvailable: true
      nodeResources: true
      kubeVirtInstalled: true
      nbdCapable: true
  message: "Dry-run validation passed with 2 warnings"
```

### Failed Validation Example

```bash
status:
  phase: Failed
  dryRunValidation:
    valid: false
    errors:
      - "StorageClass 'longhorn' not found"
      - "Insufficient node resources: requested 32 CPU, available 16"
      - "KubeVirt CRDs not installed"
    warnings: []
    checks:
      storageAvailable: false
      nodeResources: false
      kubeVirtInstalled: false
      nbdCapable: true
```

### Workflow

```bash
# 1. Validate migration
kubectl apply -f migration-dry-run.yaml

# 2. Check results
kubectl get migrationjob validate-migration -o yaml | grep -A 20 dryRunValidation

# 3. If valid, run actual migration
kubectl apply -f migration-actual.yaml
```

### CI/CD Integration

```yaml
# GitLab CI example
validate-migration:
  stage: validate
  script:
    - kubectl apply -f migrations/vm-migration-dry-run.yaml
    - |
      if kubectl get migrationjob my-migration -o jsonpath='{.status.dryRunValidation.valid}' | grep -q false; then
        echo "Validation failed!"
        kubectl get migrationjob my-migration -o yaml
        exit 1
      fi
  only:
    - merge_requests

migrate-vm:
  stage: deploy
  script:
    - kubectl apply -f migrations/vm-migration.yaml
  only:
    - main
```

### Metrics

```promql
# Dry-run validations
hyper2kvm_dry_run_validations_total{result="success"}

# Issues found
hyper2kvm_dry_run_issues_found_total{issue_type="insufficient_storage"}
```

---

## 🎯 Combining Features

### Example: Multi-Disk + Dry-Run

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: validate-multi-disk
spec:
  # Validate multi-disk migration
  dryRun: true

  source:
    type: multi-disk
    disks:
      - name: os-disk
        type: vmdk-url
        vmdk:
          url: "https://storage/os.vmdk"
        bootOrder: 1
      - name: data-disk
        type: vmdk-url
        vmdk:
          url: "https://storage/data.vmdk"

  destination:
    pvcs:
      - name: vm-os
        diskName: os-disk
        size: 50Gi
      - name: vm-data
        diskName: data-disk
        size: 500Gi

  createVM:
    enabled: true
```

### Example: Multi-Disk with Metrics

```promql
# Monitor multi-disk migration
sum(hyper2kvm_migrations_active{phase="Migrating"}) by (namespace)

# Check disk-specific progress
hyper2kvm_disk_migration_duration_seconds

# Compression ratio per disk
hyper2kvm_conversion_compression_ratio{format="qcow2"}
```

---

## 📚 See Also

- [K8s-Native Migration](k8s-native-migration.md)
- [Automated K8s Deployment](k8s-automated-deployment.md)
- [Monitoring Setup](../operations/monitoring.md)
- [Troubleshooting](../operations/troubleshooting.md)
