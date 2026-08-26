# H2KVM + KubeVirt Integration

**Version:** v0.3.1
**Date:** 2026-01-31
**Status:** Production Ready

---

## Overview

This integration enables seamless migration of VMware VMs to KubeVirt-managed virtual machines running on Kubernetes.

**Flow:**
```
VMware VMDK → H2KVM Conversion → KubeVirt VM → Running on K8s
```

**Benefits:**
- Automated VMDK → QCOW2 conversion with offline fixes
- Native Kubernetes VM management via KubeVirt
- Declarative VM definitions
- Kubernetes-native storage (PVCs)
- Full VM lifecycle management (start, stop, migrate)

---

## Architecture

### Component Stack

```
┌─────────────────────────────────────────────────────────┐
│ KubeVirt VirtualMachine (VM running in pod)             │
├─────────────────────────────────────────────────────────┤
│ DataVolume (QCOW2 image in PVC)                         │
├─────────────────────────────────────────────────────────┤
│ H2KVM Conversion (VMDK → QCOW2 + offline fixes)     │
├─────────────────────────────────────────────────────────┤
│ Source VMDK (VMware export)                             │
└─────────────────────────────────────────────────────────┘
```

### Integration Points

1. **H2KVM MigrationJob** → Converts VMDK to KVM-ready QCOW2
2. **Kubernetes PVC** → Stores converted image
3. **KubeVirt DataVolume** → Imports QCOW2 into VM disk
4. **KubeVirt VirtualMachine** → Runs the converted VM

---

## Prerequisites

### Cluster Requirements

**Hardware:**
- Bare metal nodes OR VMs with nested virtualization enabled
- KVM support (`/dev/kvm` available on nodes)
- CPU: 4+ cores per node
- RAM: 8+ GB per node
- Storage: 50+ GB available

**Software:**
- Kubernetes 1.25+ or OpenShift 4.12+
- KubeVirt v1.0+
- Containerized Data Importer (CDI) v1.55+
- StorageClass with RWX support (optional, for live migration)

### Install KubeVirt

```bash
# Install KubeVirt operator
export VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases/latest | grep tag_name | cut -d '"' -f 4)

kubectl create -f https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-operator.yaml
kubectl create -f https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-cr.yaml

# Wait for deployment
kubectl wait --for=condition=Available kubevirt kubevirt -n kubevirt --timeout=5m

# Install virtctl CLI
curl -L -o virtctl https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/virtctl-${VERSION}-linux-amd64
chmod +x virtctl
sudo mv virtctl /usr/local/bin/
```

### Install CDI (for DataVolumes)

```bash
export CDI_VERSION=$(curl -s https://github.com/kubevirt/containerized-data-importer/releases/latest | grep -o "v[0-9]\+\.[0-9]\+\.[0-9]\+")

kubectl create -f https://github.com/kubevirt/containerized-data-importer/releases/download/$CDI_VERSION/cdi-operator.yaml
kubectl create -f https://github.com/kubevirt/containerized-data-importer/releases/download/$CDI_VERSION/cdi-cr.yaml
```

### Install H2KVM

```bash
# Install CRDs
kubectl apply -f https://raw.githubusercontent.com/ssahani/h2kvm/main/k8s/operator/crds/

# Deploy operator (see DEPLOYMENT.md)
kubectl apply -f k8s/operator/manifests/
```

---

## Integration Workflow

### Step 1: Convert VMDK with H2KVM

Create a `MigrationJob` to convert the VMDK:

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: centos9-conversion
  namespace: vms
spec:
  operation: offline_fix  # Full conversion with KVM preparation

  image:
    path: /data/input/centos9.vmdk
    format: vmdk

  artifacts:
    output_path: /data/output
    output_format: qcow2
    compress: true

  priority: 80
  timeout: 90m

  # Offline fix parameters
  parameters:
    fstab_mode: stabilize-all
    regen_initramfs: true
    regenerate_grub: true
    network_fixes: moderate
    disable_vmware_services: true
```

**Apply:**
```bash
kubectl apply -f centos9-migration.yaml

# Watch progress
kubectl get migrationjob centos9-conversion -n vms -w

# Check output
kubectl exec <worker-pod> -n vms -- ls -lh /data/output/
```

### Step 2: Create DataVolume from Converted Image

Import the QCOW2 into a DataVolume:

```yaml
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: centos9-disk
  namespace: vms
spec:
  source:
    pvc:
      name: centos9-output-pvc  # PVC from MigrationJob
      namespace: vms
  storage:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 20Gi  # Adjust based on VM size
    storageClassName: standard
```

**Alternative: HTTP source** (if QCOW2 is hosted):

```yaml
spec:
  source:
    http:
      url: "https://storage.example.com/centos9-fixed.qcow2"
  storage:
    # ... same as above
```

### Step 3: Create VirtualMachine

Define the VM using the converted disk:

```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: centos9-vm
  namespace: vms
  labels:
    app: centos9
    migrated-by: h2kvm
spec:
  running: false  # Set to true to auto-start
  template:
    metadata:
      labels:
        kubevirt.io/vm: centos9-vm
    spec:
      domain:
        devices:
          disks:
            - name: rootdisk
              disk:
                bus: virtio  # H2KVM injected virtio drivers
          interfaces:
            - name: default
              masquerade: {}
              model: virtio
        resources:
          requests:
            memory: 2Gi
            cpu: 2
      networks:
        - name: default
          pod: {}
      volumes:
        - name: rootdisk
          dataVolume:
            name: centos9-disk
```

**Apply:**
```bash
kubectl apply -f centos9-vm.yaml

# Start the VM
virtctl start centos9-vm -n vms

# Check status
kubectl get vmi -n vms
virtctl console centos9-vm -n vms
```

---

## Complete End-to-End Example

### Automated Pipeline

```yaml
---
# Step 1: Namespace
apiVersion: v1
kind: Namespace
metadata:
  name: vm-migrations

---
# Step 2: PVC for VMDK input
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: centos9-vmdk-input
  namespace: vm-migrations
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 3Gi

---
# Step 3: PVC for QCOW2 output
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: centos9-qcow2-output
  namespace: vm-migrations
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi

---
# Step 4: MigrationJob (converts VMDK → QCOW2)
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: centos9-migration
  namespace: vm-migrations
spec:
  operation: offline_fix

  image:
    path: /data/input/centos9.vmdk
    format: vmdk

  artifacts:
    output_path: /data/output
    output_format: qcow2
    compress: true

  priority: 90
  timeout: 120m

  parameters:
    fstab_mode: stabilize-all
    regen_initramfs: true
    regenerate_grub: true
    network_fixes: moderate

---
# Step 5: DataVolume (imports QCOW2 for KubeVirt)
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: centos9-rootdisk
  namespace: vm-migrations
spec:
  source:
    pvc:
      name: centos9-qcow2-output
      namespace: vm-migrations
  storage:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 20Gi
    storageClassName: standard

---
# Step 6: VirtualMachine (runs converted image)
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: centos9
  namespace: vm-migrations
  labels:
    app: centos9
    os: centos-stream-9
    migrated-from: vmware
    migrated-by: h2kvm
    migration-date: "2026-01-31"
  annotations:
    description: "CentOS Stream 9 migrated from VMware"
    h2kvm/source-vmdk: "centos9.vmdk"
    h2kvm/conversion-job: "centos9-migration"
spec:
  running: true
  template:
    metadata:
      labels:
        kubevirt.io/vm: centos9
    spec:
      domain:
        cpu:
          cores: 2
        devices:
          disks:
            - name: rootdisk
              disk:
                bus: virtio
            - name: cloudinit
              disk:
                bus: virtio
          interfaces:
            - name: default
              masquerade: {}
              model: virtio
        machine:
          type: q35
        resources:
          requests:
            memory: 2Gi
      networks:
        - name: default
          pod: {}
      volumes:
        - name: rootdisk
          dataVolume:
            name: centos9-rootdisk
        - name: cloudinit
          cloudInitNoCloud:
            userData: |
              #cloud-config
              hostname: centos9
              users:
                - name: centos
                  sudo: ALL=(ALL) NOPASSWD:ALL
                  shell: /bin/bash
              ssh_authorized_keys:
                - ssh-rsa AAAA... # Add your SSH key
```

---

## Deployment Instructions

### 1. Upload VMDK to Kubernetes

```bash
# Create namespace
kubectl create namespace vm-migrations

# Upload VMDK to PVC
kubectl run vmdk-uploader -n vm-migrations \
  --image=busybox --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"uploader","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"centos9-vmdk-input"}}]}}'

kubectl cp /path/to/centos9.vmdk vm-migrations/vmdk-uploader:/data/centos9.vmdk

kubectl delete pod vmdk-uploader -n vm-migrations
```

### 2. Apply Complete Pipeline

```bash
kubectl apply -f complete-vm-migration.yaml

# Monitor conversion
kubectl get migrationjob -n vm-migrations -w

# Monitor DataVolume import
kubectl get datavolume -n vm-migrations -w

# Check VM status
kubectl get vm -n vm-migrations
kubectl get vmi -n vm-migrations
```

### 3. Access the VM

```bash
# Start VM (if not auto-started)
virtctl start centos9 -n vm-migrations

# Access console
virtctl console centos9 -n vm-migrations

# SSH access (if cloud-init configured)
virtctl ssh centos@centos9 -n vm-migrations

# VNC access
virtctl vnc centos9 -n vm-migrations
```

---

## Advanced Features

### Live Migration

Enable live migration between nodes:

```yaml
spec:
  template:
    spec:
      evictionStrategy: LiveMigrate
```

Trigger migration:
```bash
virtctl migrate centos9 -n vm-migrations
```

#### Live Migration Visibility (Web Dashboard)

The h2kweb dashboard provides live migration visibility for KubeVirt VMs. You can trigger and monitor migrations directly from the web UI or the API:

```bash
# Trigger live migration from the API
curl -X POST https://localhost:5070/api/v1/kubevirt/vms/vm-migrations/centos9/migrate

# Check VMI status (includes migration state)
curl https://localhost:5070/api/v1/kubevirt/vmis
```

The dashboard's KubeVirt page shows migration progress, source/target node, and completion status in real time. The activity feed (`GET /api/v1/activity`) also records migration events for audit purposes.

### VM Snapshots

```yaml
apiVersion: snapshot.kubevirt.io/v1alpha1
kind: VirtualMachineSnapshot
metadata:
  name: centos9-snapshot-1
  namespace: vm-migrations
spec:
  source:
    apiGroup: kubevirt.io
    kind: VirtualMachine
    name: centos9
```

### Multi-Disk VMs

```yaml
spec:
  template:
    spec:
      domain:
        devices:
          disks:
            - name: rootdisk
              disk:
                bus: virtio
            - name: datadisk
              disk:
                bus: virtio
      volumes:
        - name: rootdisk
          dataVolume:
            name: centos9-root
        - name: datadisk
          dataVolume:
            name: centos9-data
```

---

## Integration with H2KVM Operator

### Enhanced MigrationJob with KubeVirt Output

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: vm-migration-with-kubevirt
  namespace: vm-migrations
spec:
  operation: offline_fix

  image:
    path: /data/input/windows10.vmdk
    format: vmdk

  artifacts:
    output_path: /data/output
    output_format: qcow2

  # KubeVirt integration (custom extension)
  kubevirt:
    enabled: true
    vmName: windows10
    dataVolumeName: windows10-disk
    autoStart: false
    vmSpec:
      resources:
        requests:
          memory: 4Gi
          cpu: 4
      cloudInit:
        enabled: false  # Windows doesn't support cloud-init
```

---

## Monitoring & Observability

### Check Migration Status

```bash
# H2KVM conversion
kubectl get migrationjob -n vm-migrations
kubectl describe migrationjob centos9-migration -n vm-migrations

# DataVolume import
kubectl get dv -n vm-migrations
kubectl describe dv centos9-rootdisk -n vm-migrations

# VM status
kubectl get vm,vmi -n vm-migrations
virtctl info centos9 -n vm-migrations
```

### Logs

```bash
# H2KVM worker logs
kubectl logs -n vm-migrations <migration-worker-pod>

# KubeVirt virt-launcher logs
kubectl logs -n vm-migrations <virt-launcher-pod>

# CDI importer logs
kubectl logs -n vm-migrations <importer-pod>
```

---

## Troubleshooting

### Issue 1: VM Won't Boot

**Symptoms:**
- VM starts but doesn't boot
- Kernel panic or grub errors

**Fix:**
Ensure offline fixes were applied during conversion:

```yaml
spec:
  parameters:
    regen_initramfs: true      # Essential for virtio drivers
    regenerate_grub: true      # Essential for boot
    fstab_mode: stabilize-all  # Essential for filesystem mounts
```

### Issue 2: Network Not Working

**Check:**
```bash
virtctl console centos9 -n vm-migrations
# Inside VM
ip a
```

**Fix:**
Ensure network was fixed during conversion:

```yaml
spec:
  parameters:
    network_fixes: moderate  # Updates NetworkManager configs
```

### Issue 3: DataVolume Import Fails

**Check:**
```bash
kubectl get events -n vm-migrations --sort-by='.lastTimestamp'
kubectl describe dv centos9-rootdisk -n vm-migrations
```

**Common causes:**
- Insufficient storage
- PVC not accessible
- QCOW2 file corrupted

---

## Performance Optimization

### Storage Class Selection

**For best VM performance:**
- Use SSD-backed storage classes
- Enable thin provisioning
- Use RWX for live migration support

```yaml
spec:
  storage:
    storageClassName: fast-ssd  # High-performance SSD
```

### Resource Tuning

```yaml
spec:
  template:
    spec:
      domain:
        cpu:
          cores: 4
          dedicatedCpuPlacement: true  # CPU pinning
        memory:
          hugepages:
            pageSize: 2Mi  # Use hugepages
        resources:
          requests:
            memory: 8Gi
          limits:
            memory: 8Gi
```

---

## Security Considerations

### Image Validation

Always validate converted images:

```bash
# Check QCOW2 integrity
qemu-img check centos9-fixed.qcow2

# Scan for malware (if applicable)
clamscan centos9-fixed.qcow2
```

### Network Policies

Restrict VM network access:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vm-network-policy
  namespace: vm-migrations
spec:
  podSelector:
    matchLabels:
      kubevirt.io/vm: centos9
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              role: admin
  egress:
    - to:
        - podSelector:
            matchLabels:
              role: database
```

---

## Comparison: Traditional vs H2KVM + KubeVirt

| Aspect | Traditional Migration | H2KVM + KubeVirt |
|--------|----------------------|----------------------|
| **Conversion** | Manual qemu-img | Automated with offline fixes |
| **Driver injection** | Manual | Automatic (virtio drivers) |
| **Boot config** | Manual GRUB/fstab edits | Automatic |
| **Deployment** | VM install, manual config | Declarative YAML |
| **Scaling** | Manual, per-VM | Kubernetes-native |
| **Storage** | Separate management | Integrated PVCs |
| **Networking** | Separate SDN | Kubernetes CNI |
| **Monitoring** | Separate tools | Kubernetes-native |
| **HA** | Complex setup | Built-in (live migration) |

---

## Production Checklist

Before production deployment:

- [ ] Cluster has bare metal or nested virt support
- [ ] KubeVirt installed and all pods running
- [ ] CDI installed for DataVolume support
- [ ] H2KVM operator deployed
- [ ] Storage class configured (fast SSD recommended)
- [ ] Network policies defined
- [ ] Backup strategy in place (VM snapshots)
- [ ] Monitoring configured (Prometheus + Grafana)
- [ ] Test VM migrations on non-critical workloads
- [ ] Document VM inventory and dependencies

---

## Tested Configurations

**Successful migrations:**
- CentOS Stream 9 (2.2 GB) ✅
- Debian 12 (6.8 GB) ✅
- Fedora 42 (2.5 GB) ✅

**Guest OS Support:**
- Linux (RHEL, CentOS, Ubuntu, Debian, Fedora, SUSE) ✅
- Windows (7, 10, 11, Server 2012-2022) ✅ (requires virtio drivers)

**Cluster Platforms:**
- Kubernetes 1.25+ ✅
- OpenShift 4.12+ ✅
- Rancher ✅
- Bare metal ✅

---

## Multi-Kubeconfig Management (Web Dashboard)

When managing KubeVirt VMs across multiple clusters, the h2kweb dashboard provides a multi-kubeconfig API so you can register several clusters and switch between them without restarting the service.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/kubeconfigs` | List registered kubeconfigs with live connection status |
| `POST` | `/api/v1/kubeconfigs/add` | Add kubeconfig via multipart upload or JSON path |
| `PUT` | `/api/v1/kubeconfigs/{id}/activate` | Set the active cluster |
| `DELETE` | `/api/v1/kubeconfigs/{id}` | Remove a cluster |

### How It Works

1. Register one or more kubeconfig files through the `/kubeconfigs` dashboard page or the API.
2. Activate the cluster you want to target.
3. All KubeVirt operations (VM/VMI listing, start/stop, VNC proxy, deploy status, host info) automatically use the active kubeconfig.

This eliminates the need to set `KUBECONFIG` environment variables or restart the dashboard when switching clusters.

### Example: Register and Activate a Production Cluster

```bash
# Add the production kubeconfig
curl -X POST https://localhost:5070/api/v1/kubeconfigs/add \
  -F "kubeconfig=@/home/user/.kube/prod.yaml"

# List clusters and note the ID
curl https://localhost:5070/api/v1/kubeconfigs

# Activate the production cluster
curl -X PUT https://localhost:5070/api/v1/kubeconfigs/{id}/activate
```

After activation, all KubeVirt VM management in the dashboard targets the production cluster.

---

## References

- [KubeVirt Documentation](https://kubevirt.io/user-guide/)
- [CDI Documentation](https://github.com/kubevirt/containerized-data-importer/blob/main/doc/datavolumes.md)
- [H2KVM Repository](https://github.com/ssahani/h2kvm)
- [Virtctl CLI Guide](https://kubevirt.io/user-guide/operations/virtctl_client_tool/)

---

**Last Updated:** 2026-03-29
**Status:** Production Ready
**Integration Tested:** ✅ CentOS 9 local conversion validated
**KubeVirt Compatibility:** v1.0+
