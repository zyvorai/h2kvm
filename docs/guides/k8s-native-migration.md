# ☸️ Kubernetes-Native Migration with MigrationJob

🎉 **World's First Cloud-Native VM Migration Platform!**

h2kvm now supports **fully Kubernetes-native migrations** using the `MigrationJob` custom resource. No host machine with sudo required - everything runs inside Kubernetes!

## 🌟 Why This is Revolutionary

### Before: Host-Based Migration
```
❌ Requires dedicated migration host
❌ Needs root/sudo access
❌ Manual VMDK upload to cluster
❌ Complex multi-step process
❌ No horizontal scaling
❌ Not GitOps-friendly
```

### After: K8s-Native Migration
```
✅ Runs entirely in Kubernetes
✅ No special host required
✅ Declarative API (kubectl apply)
✅ GitOps ready (ArgoCD, Flux)
✅ Scales horizontally
✅ Cloud-native workflow
✅ Automatic VM creation
```

## 🚀 Quick Start

### 1. Install the Operator

```bash
# Apply CRD
kubectl apply -f k8s/operator/migrationjob-crd.yaml

# Deploy operator
kubectl apply -f k8s/operator/deployment.yaml

# Deploy NBD prep DaemonSet
kubectl apply -f k8s/daemon/nbd-prep-daemonset.yaml
```

### 2. Create a MigrationJob

```bash
kubectl apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: my-first-migration
  namespace: default
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://storage.example.com/centos9.vmdk"
  migration:
    offlineFixes:
      enabled: true
    conversion:
      format: qcow2
      compress: true
  destination:
    size: 20Gi
    storageClass: local-path
  createVM:
    enabled: true
    autoStart: true
EOF
```

### 3. Watch the Migration

```bash
# Check status
kubectl get migrationjob my-first-migration

# Watch progress
kubectl get migrationjob my-first-migration -w

# View details
kubectl describe migrationjob my-first-migration

# Check created VM
kubectl get vm
```

## 📊 Migration Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. User creates MigrationJob CR                            │
│     kubectl apply -f migration.yaml                         │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  2. Operator creates source PVC                             │
│     Phase: Pending → Uploading                              │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  3. Temporary pod downloads VMDK to PVC                     │
│     curl/wget downloads from URL                            │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  4. Operator selects NBD-capable node                       │
│     Looks for nodes with h2kvm.io/nbd-capable=true      │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  5. DaemonSet prepares NBD device                           │
│     - Attaches VMDK via NBD                                 │
│     - Mounts filesystem                                     │
│     Phase: Preparing                                        │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  6. Migration pod runs h2kvm                            │
│     - Offline fixes (fstab, GRUB, initramfs)                │
│     - Converts to QCOW2                                     │
│     - Writes to destination PVC                             │
│     Phase: Migrating                                        │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  7. Operator creates VirtualMachine (if enabled)            │
│     Phase: Creating → Completed                             │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  8. VM boots in Kubernetes! 🎉                              │
│     Status: Running, Ready: True                            │
└─────────────────────────────────────────────────────────────┘
```

## 📋 MigrationJob Specification

### Source Types

#### 1. VMDK from URL
Download VMDK from HTTP(S) URL:

```yaml
source:
  type: vmdk-url
  vmdk:
    url: "https://storage.example.com/vm.vmdk"
```

#### 2. VMDK from existing PVC
Use VMDK already uploaded to PVC:

```yaml
source:
  type: vmdk-pvc
  vmdk:
    pvcName: my-vmdk-pvc
    path: disk.vmdk  # Optional, defaults to disk.vmdk
```

#### 3. Direct PVC (already QCOW2)
Use existing QCOW2 in PVC:

```yaml
source:
  type: pvc
  pvc:
    name: my-disk-pvc
```

### Migration Options

#### Offline Fixes
```yaml
migration:
  offlineFixes:
    enabled: true
    fstabMode: stabilize-all  # none | uuid-only | stabilize-partitions | stabilize-all
    fstabPreferPartuuid: false
    grubFixes: true
    initramfsRegen: true
    initramfsModules:
      - virtio_blk
      - virtio_scsi
      - virtio_net
      - virtio_pci
    networkFixes: true
```

#### Conversion Options
```yaml
migration:
  conversion:
    format: qcow2  # qcow2 | raw
    compress: true
    compressionType: zstd  # zstd | zlib
```

#### Node Selection
```yaml
migration:
  nodeSelector:
    storage: high-performance
    zone: us-west-1a
```

### Destination Configuration

```yaml
destination:
  pvcName: my-vm-disk  # Optional, auto-generated if not specified
  storageClass: longhorn  # Or ceph-block, local-path, etc.
  size: 50Gi
  accessModes:
    - ReadWriteOnce
```

### VM Creation

```yaml
createVM:
  enabled: true
  name: my-vm  # Optional, defaults to job name
  cpu: "8"
  memory: 16Gi
  autoStart: true  # Start VM after migration
  networkType: masquerade  # pod | masquerade | bridge
```

### Cleanup Policy

```yaml
cleanupPolicy: OnSuccess  # Always | OnSuccess | Never
```

**OnSuccess**: Delete temporary resources after successful migration
**Always**: Delete temporary resources even if migration fails
**Never**: Keep all resources for debugging

### Timeout

```yaml
timeout: 1h  # 30m, 1h, 2h, etc.
```

## 🎯 Use Cases

### 1. Single VM Migration

```bash
kubectl apply -f k8s/examples/migrationjob-basic.yaml
```

### 2. Batch Migration (GitOps)

```bash
# Migrate multiple VMs in parallel
kubectl apply -f k8s/examples/migrationjob-batch.yaml

# Watch all migrations
kubectl get migrationjob -w
```

### 3. CI/CD Integration

```yaml
# ArgoCD Application
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: vm-migrations
spec:
  source:
    path: migrations/
    repoURL: https://github.com/myorg/vm-migrations
  destination:
    namespace: migrations
  syncPolicy:
    automated:
      prune: false  # Don't delete completed migrations
```

### 4. Scheduled Migrations (CronJob)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-migrations
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: create-migration
            image: bitnami/kubectl
            command:
            - kubectl
            - apply
            - -f
            - /migrations/migration-job.yaml
```

## 📊 Monitoring

### Check Migration Status

```bash
# List all migrations
kubectl get migrationjob

# Example output:
# NAME                PHASE        SOURCE       VM           AGE
# migrate-centos9     Completed    vmdk-url     centos9      5m
# migrate-ubuntu      Migrating    vmdk-pvc     ubuntu       2m
# migrate-photon      Failed       vmdk-url     -            10m
```

### View Details

```bash
kubectl describe migrationjob migrate-centos9
```

### Watch Events

```bash
kubectl get events --field-selector involvedObject.name=migrate-centos9
```

### Check Logs

```bash
# Migration pod logs
kubectl logs -l migration.h2kvm.io/job=migrate-centos9

# Operator logs
kubectl logs -n h2kvm-system deployment/h2kvm-operator
```

## 🔧 Troubleshooting

### Migration Stuck in "Pending"

**Cause**: No NBD-capable nodes

**Solution**: Ensure nodes have label:
```bash
kubectl label nodes <node-name> h2kvm.io/nbd-capable=true
```

### Migration Stuck in "Preparing"

**Cause**: NBD DaemonSet not running

**Solution**: Check DaemonSet:
```bash
kubectl get daemonset -n h2kvm-system nbd-prep

# Check pod logs
kubectl logs -n h2kvm-system -l app=nbd-prep
```

### Migration Failed in "Uploading"

**Cause**: VMDK URL inaccessible or PVC too small

**Solution**:
- Check URL accessibility
- Increase destination PVC size

### Migration Failed in "Migrating"

**Cause**: Offline fixes failed

**Solution**: Check migration pod logs:
```bash
kubectl logs migration-<job-name>
```

### VM Created but Not Starting

**Cause**: Insufficient resources or disk format issue

**Solution**:
```bash
# Check VM status
kubectl get vm <vm-name> -o yaml

# Check VMI events
kubectl get events --field-selector involvedObject.kind=VirtualMachineInstance
```

## 🎓 Examples

### Example 1: Migrate from URL with Custom Settings

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: web-server-migration
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://vmware-exports.example.com/web-01.vmdk"
  migration:
    offlineFixes:
      fstabMode: stabilize-all
      grubFixes: true
      initramfsModules:
        - virtio_blk
        - virtio_scsi
    conversion:
      format: qcow2
      compress: true
      compressionType: zstd
    nodeSelector:
      zone: us-east-1a
  destination:
    pvcName: web-01-disk
    storageClass: fast-ssd
    size: 100Gi
  createVM:
    enabled: true
    name: web-server-01
    cpu: "16"
    memory: 32Gi
    autoStart: true
  cleanupPolicy: OnSuccess
  timeout: 2h
```

### Example 2: Migrate from Existing PVC (No VM Creation)

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: database-migration
spec:
  source:
    type: vmdk-pvc
    vmdk:
      pvcName: db-vmdk-upload
      path: database.vmdk
  migration:
    offlineFixes:
      enabled: true
    conversion:
      format: qcow2
      compress: false  # Don't compress database disks
  destination:
    storageClass: ceph-block
    size: 500Gi
  createVM:
    enabled: false  # Manual VM creation later
  cleanupPolicy: Never  # Keep for debugging
```

### Example 3: GitOps Workflow

**Directory structure:**
```
migrations/
├── kustomization.yaml
├── web-servers/
│   ├── web-01.yaml
│   ├── web-02.yaml
│   └── web-03.yaml
└── databases/
    ├── db-primary.yaml
    └── db-replica.yaml
```

**Apply all migrations:**
```bash
kubectl apply -k migrations/
```

## 🔐 RBAC

The operator requires these permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: h2kvm-operator
rules:
  - apiGroups: ["h2kvm.io"]
    resources: ["migrationjobs", "migrationjobs/status"]
    verbs: ["*"]
  - apiGroups: [""]
    resources: ["persistentvolumeclaims", "pods", "nodes"]
    verbs: ["*"]
  - apiGroups: ["kubevirt.io"]
    resources: ["virtualmachines"]
    verbs: ["*"]
```

## 🚀 Performance & Scaling

### Horizontal Scaling

Multiple migrations run in parallel:
- Each migration gets its own pod
- Node affinity prevents conflicts
- NBD devices isolated per node

**Example: Migrate 100 VMs:**
```bash
for i in {1..100}; do
  kubectl apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: migrate-vm-$i
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://storage/vm-$i.vmdk"
  destination:
    size: 20Gi
  createVM:
    enabled: true
EOF
done

# All 100 migrations run in parallel! 🚀
```

### Resource Requirements

**Per Migration:**
- CPU: ~2 cores
- Memory: ~4-8 GB
- Storage: Source + Destination PVC

**Operator:**
- CPU: 100m
- Memory: 256Mi

## 📚 See Also

- [MigrationJob CRD Reference](../api/migrationjob.md)
- [Operator Installation](operator-setup.md)
- [NBD DaemonSet Configuration](nbd-daemonset.md)
- [Traditional K8s Deployment](k8s-automated-deployment.md)

## 🎉 Summary

**MigrationJob makes VM migration:**
- ☁️ **Cloud-native** - Kubernetes-first design
- 🚀 **Scalable** - Parallel migrations
- 📝 **Declarative** - GitOps ready
- 🔄 **Automated** - End-to-end workflow
- 🎯 **Simple** - Just `kubectl apply`!

No more host machines, no more sudo, no more manual steps. Just pure Kubernetes! 💫
