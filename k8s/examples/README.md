# 🚀 MigrationJob Examples

This directory contains example `MigrationJob` manifests for Kubernetes-native VM migrations.

## 📋 Quick Reference

| Example | Description | Use Case |
|---------|-------------|----------|
| `migrationjob-basic.yaml` | Basic migration from URL | Getting started, single VM |
| `migrationjob-from-pvc.yaml` | Migration from existing PVC | Pre-uploaded VMDK |
| `migrationjob-batch.yaml` | Multiple parallel migrations | Bulk migrations, GitOps |

## 🎯 Examples

### 1. Basic Migration (VMDK from URL)

**File:** `migrationjob-basic.yaml`

Downloads VMDK from HTTP(S) URL, performs offline fixes, and creates a VM.

```bash
# Apply the example
kubectl apply -f migrationjob-basic.yaml

# Watch progress
kubectl get migrationjob migrate-centos9 -w

# Check created VM
kubectl get vm centos9
```

**Features:**
- ✅ Downloads VMDK from URL
- ✅ Full offline fixes (fstab, GRUB, initramfs)
- ✅ QCOW2 conversion with zstd compression
- ✅ Auto-creates and starts VM
- ✅ Cleans up temporary resources

### 2. Migration from Existing PVC

**File:** `migrationjob-from-pvc.yaml`

Use this when you've already uploaded a VMDK to a PVC manually.

```bash
# First, create PVC and upload VMDK
kubectl create -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: photon-source-vmdk
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
EOF

# Upload VMDK to PVC (using a temporary pod)
kubectl run uploader --image=alpine --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"uploader","image":"alpine","command":["sleep","3600"],"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"photon-source-vmdk"}}]}}'
kubectl wait --for=condition=Ready pod/uploader
kubectl cp photon.vmdk uploader:/data/disk.vmdk
kubectl delete pod uploader

# Now run migration
kubectl apply -f migrationjob-from-pvc.yaml
```

**Features:**
- ✅ Uses existing PVC with VMDK
- ✅ Minimal config (uses smart defaults)
- ✅ Production storage class (Longhorn)
- ✅ Auto VM creation

### 3. Batch Migrations

**File:** `migrationjob-batch.yaml`

Migrate multiple VMs in parallel - perfect for GitOps workflows!

```bash
# Apply all migrations at once
kubectl apply -f migrationjob-batch.yaml

# Watch all migrations
kubectl get migrationjob -w

# Check individual status
kubectl describe migrationjob migrate-web-01
kubectl describe migrationjob migrate-web-02
kubectl describe migrationjob migrate-db-01

# Check created VMs
kubectl get vm
```

**Features:**
- ✅ 3 VMs migrate in parallel
- ✅ Different resource allocations per VM
- ✅ Node selectors for database (high-performance storage)
- ✅ Database doesn't auto-start (manual verification)
- ✅ GitOps ready (commit to Git, ArgoCD applies)

## 🔧 Customizing Examples

### Change Source URL

```yaml
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://your-storage/your-vm.vmdk"  # <- Change this
```

### Change Storage Class

```yaml
spec:
  destination:
    storageClass: your-storage-class  # <- Change this (e.g., ceph-block, nfs)
    size: 50Gi
```

### Adjust VM Resources

```yaml
spec:
  createVM:
    enabled: true
    cpu: "8"       # <- Change CPU count
    memory: 16Gi   # <- Change memory
    autoStart: true
```

### Disable Auto VM Creation

If you want to create the VM manually later:

```yaml
spec:
  createVM:
    enabled: false  # <- Disable auto VM creation
```

Then manually create VM:
```bash
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: my-vm
spec:
  running: true
  template:
    spec:
      domain:
        devices:
          disks:
          - name: rootdisk
            disk:
              bus: virtio
        resources:
          requests:
            memory: 8Gi
            cpu: 4
      volumes:
      - name: rootdisk
        persistentVolumeClaim:
          claimName: migrate-centos9-disk  # <- Use migration output PVC
EOF
```

### Keep Resources for Debugging

```yaml
spec:
  cleanupPolicy: Never  # <- Keep temporary resources
```

Then manually cleanup:
```bash
# List resources
kubectl get pvc -l migration.hyper2kvm.io/job=migrate-centos9
kubectl get pod -l migration.hyper2kvm.io/job=migrate-centos9

# Delete when done
kubectl delete migrationjob migrate-centos9
```

## 📊 Monitoring

### Check Status

```bash
# List all migrations
kubectl get migrationjob

# Output:
# NAME                PHASE        SOURCE       VM           AGE
# migrate-centos9     Completed    vmdk-url     centos9      5m
# migrate-ubuntu      Migrating    vmdk-pvc     ubuntu       2m
# migrate-photon      Failed       vmdk-url     -            10m
```

### Detailed Status

```bash
kubectl describe migrationjob migrate-centos9
```

### Watch Events

```bash
kubectl get events --field-selector involvedObject.name=migrate-centos9 --watch
```

### Pod Logs

```bash
# Migration pod logs
kubectl logs -l migration.hyper2kvm.io/job=migrate-centos9

# Uploader pod logs (for vmdk-url source)
kubectl logs uploader-migrate-centos9-source
```

## 🎓 Advanced Patterns

### GitOps with Kustomize

Create a `kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - migrationjob-basic.yaml
  - migrationjob-from-pvc.yaml
  - migrationjob-batch.yaml

namespace: prod-migrations

commonLabels:
  environment: production
  team: infrastructure
```

Apply:
```bash
kubectl apply -k .
```

### GitOps with ArgoCD

Create an ArgoCD Application:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: vm-migrations
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/myorg/vm-migrations
    targetRevision: main
    path: migrations/
  destination:
    server: https://kubernetes.default.svc
    namespace: migrations
  syncPolicy:
    automated:
      prune: false  # Don't delete completed migrations
      selfHeal: true
```

### Multi-Environment Migrations

**Directory structure:**
```
migrations/
├── base/
│   └── migrationjob-template.yaml
├── dev/
│   └── kustomization.yaml
├── staging/
│   └── kustomization.yaml
└── prod/
    └── kustomization.yaml
```

**base/migrationjob-template.yaml:**
```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: app-migration
spec:
  source:
    type: vmdk-url
    vmdk:
      url: https://storage/app.vmdk
  destination:
    size: 20Gi
```

**dev/kustomization.yaml:**
```yaml
resources:
  - ../base

nameSuffix: -dev
namespace: dev-migrations

patches:
  - patch: |-
      - op: replace
        path: /spec/destination/storageClass
        value: local-path
    target:
      kind: MigrationJob
```

**prod/kustomization.yaml:**
```yaml
resources:
  - ../base

nameSuffix: -prod
namespace: prod-migrations

patches:
  - patch: |-
      - op: replace
        path: /spec/destination/storageClass
        value: ceph-block
      - op: replace
        path: /spec/createVM/cpu
        value: "16"
      - op: replace
        path: /spec/createVM/memory
        value: 32Gi
    target:
      kind: MigrationJob
```

Apply:
```bash
# Dev environment
kubectl apply -k dev/

# Production environment
kubectl apply -k prod/
```

## 🔍 Troubleshooting

### Migration Stuck in Pending

Check if nodes are NBD-capable:
```bash
kubectl get nodes -l hyper2kvm.io/nbd-capable=true

# If no nodes, label them:
kubectl label nodes worker-1 hyper2kvm.io/nbd-capable=true
```

### Migration Failed

Check the migration pod logs:
```bash
kubectl logs migration-migrate-centos9
```

### Download Failed (vmdk-url)

Check uploader pod:
```bash
kubectl logs uploader-migrate-centos9-source
```

Common issues:
- URL not accessible
- Certificate issues (try HTTP instead of HTTPS for testing)
- PVC too small

### VM Won't Start

Check VM status:
```bash
kubectl describe vm centos9

# Check VMI
kubectl get vmi

# Check virt-launcher pod
kubectl logs virt-launcher-centos9-xxxxx
```

## 📚 See Also

- [K8s-Native Migration Guide](../../docs/guides/k8s-native-migration.md)
- [MigrationJob CRD](../operator/migrationjob-crd.yaml)
- [Operator Setup](../operator/README.md)

## 💡 Tips

1. **Start Small**: Test with `migrationjob-basic.yaml` first
2. **Use from-pvc**: Upload VMDK separately for faster iterations
3. **Monitor**: Watch events and logs during migration
4. **Cleanup**: Set `cleanupPolicy: OnSuccess` to save space
5. **Scale**: Use batch migrations for parallel processing
6. **GitOps**: Commit MigrationJobs to Git for audit trail

Happy migrating! 🚀
