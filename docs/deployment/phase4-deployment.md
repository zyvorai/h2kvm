# Phase 4 Deployment Guide - OfflineFixJob System

**Component:** OfflineFixJob CRD + NBD Prep + Offline-Fix VM
**Version:** v1.0.0
**Prerequisites:** Kubernetes cluster, KubeVirt installed

---

## Overview

This guide deploys the complete Phase 4 offline-fix system:
- OfflineFixJob Custom Resource Definition
- NBD Prep DaemonSet (host-level NBD management)
- Offline-Fix VM image (executes Phase 3 fixers)
- OfflineFixJob Controller (orchestration)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ OfflineFixJob CR                                            │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ Controller (Python/kopf)                                    │
│  • Selects NBD-capable node                                 │
│  • Annotates node for DaemonSet                             │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ NBD Prep DaemonSet                                          │
│  • Attaches disk to NBD device                              │
│  • Mounts filesystem to /var/lib/kubevirt-offline/          │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ KubeVirt VM (offline-fix-vm)                                │
│  • Mounts HostDisk from NBD mount                           │
│  • Runs Phase 3 fixers (fstab, initramfs, grub, selinux)   │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│ Cleanup                                                     │
│  • DaemonSet unmounts and disconnects NBD                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### 1. Kubernetes Cluster

- Kubernetes 1.24+
- KubeVirt 0.59+ installed
- NBD kernel module available on nodes
- Privileged DaemonSets allowed (for NBD operations)

### 2. Node Requirements

Nodes that will run offline-fix operations need:

```bash
# NBD kernel module
sudo modprobe nbd max_part=16
lsmod | grep nbd

# Required tools
sudo apt-get install -y qemu-utils lvm2

# Directory for NBD mounts
sudo mkdir -p /var/lib/kubevirt-offline
sudo mkdir -p /var/lib/imports
```

### 3. KubeVirt

Verify KubeVirt is installed:

```bash
kubectl get kubevirt -n kubevirt
kubectl get vmi -A
```

---

## Step 1: Build Docker Images

### Option A: Build Locally

```bash
cd /path/to/hyper2kvm

# Set registry (change to your registry)
export REGISTRY=quay.io/yourusername
export VERSION=v1.0.0

# Build images
./scripts/build-phase4-images.sh

# Push to registry
docker push $REGISTRY/nbd-prep:$VERSION
docker push $REGISTRY/offline-fix-vm:$VERSION
```

### Option B: Use Pre-built Images

If using pre-built images from quay.io/hyper2kvm, skip to Step 2.

---

## Step 2: Deploy CRD

Deploy the OfflineFixJob Custom Resource Definition:

```bash
kubectl apply -f k8s/operator/crds/offlinefixjob.yaml
```

Verify:

```bash
kubectl get crd offlinefixjobs.hyper2kvm.io
kubectl api-resources | grep offlinefixjob
```

---

## Step 3: Label NBD-Capable Nodes

Label nodes that can perform NBD operations:

```bash
# Check nodes
kubectl get nodes

# Label nodes (adjust node names)
kubectl label node worker-1 hyper2kvm.io/nbd-capable=true
kubectl label node worker-2 hyper2kvm.io/nbd-capable=true

# Verify
kubectl get nodes -L hyper2kvm.io/nbd-capable
```

---

## Step 4: Deploy NBD Prep DaemonSet

### Update Image References (if needed)

Edit `k8s/daemon/nbd-prep-daemonset.yaml` if using custom registry:

```yaml
containers:
- name: nbd-prep
  image: quay.io/yourusername/nbd-prep:v1.0.0  # Change this
```

### Deploy DaemonSet

```bash
kubectl apply -f k8s/daemon/nbd-prep-daemonset.yaml
```

### Verify

```bash
# Check DaemonSet
kubectl get ds -n hyper2kvm-system nbd-prep

# Check pods on labeled nodes
kubectl get pods -n hyper2kvm-system -l app=nbd-prep -o wide

# Check logs
kubectl logs -n hyper2kvm-system -l app=nbd-prep --tail=50
```

Expected output:
```
NBD Prep Daemon starting on node: worker-1
Loading NBD kernel module
NBD module loaded successfully
```

---

## Step 5: Update Operator Deployment

The OfflineFixJob controller runs as part of the main operator.

### Update Operator Image (if rebuilding)

If you're rebuilding the operator to include Phase 4:

```bash
cd /path/to/hyper2kvm

# Build operator image
docker build -t quay.io/yourusername/operator:v1.5.0 .
docker push quay.io/yourusername/operator:v1.5.0
```

### Deploy/Update Operator

```bash
# If operator not deployed yet
kubectl apply -f k8s/operator/deployment.yaml

# If updating existing operator
kubectl set image deployment/hyper2kvm-operator \
  operator=quay.io/yourusername/operator:v1.5.0 \
  -n hyper2kvm-system

# Restart operator to load new controller
kubectl rollout restart deployment/hyper2kvm-operator -n hyper2kvm-system
```

### Verify

```bash
# Check operator logs for OfflineFixJob controller registration
kubectl logs -n hyper2kvm-system -l app=hyper2kvm-operator --tail=100 | grep -i offline
```

---

## Step 6: Prepare Test Disk Image

Place a test VMDK/qcow2 on NBD-capable nodes:

```bash
# On each NBD-capable node
sudo mkdir -p /var/lib/imports

# Copy or download test image
sudo cp /path/to/centos9.qcow2 /var/lib/imports/
# Or download
sudo curl -o /var/lib/imports/centos9.qcow2 https://example.com/centos9.qcow2

# Verify
ls -lh /var/lib/imports/
```

---

## Step 7: Create Test OfflineFixJob

### Create Job Manifest

```yaml
# test-offlinefixjob.yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: OfflineFixJob
metadata:
  name: test-centos9-fix
  namespace: hyper2kvm-system
spec:
  source:
    disk:
      type: qcow2
      path: /var/lib/imports/centos9.qcow2

  fixes:
  - fstab
  - initramfs
  - grub
  - selinux

  execution:
    mode: kubevirt-vm
    vmImage: quay.io/hyper2kvm/offline-fix-vm:v1.0.0
    resources:
      memory: "2Gi"
      cpu: "2"

  safety:
    readOnly: false
    allowXfsRepair: true

  nodeSelector:
    hyper2kvm.io/nbd-capable: "true"

  timeout: "30m"
```

### Apply Job

```bash
kubectl apply -f test-offlinefixjob.yaml
```

---

## Step 8: Monitor Job Execution

### Watch Status

```bash
# Watch job status
kubectl get offlinefixjob -w

# Expected phases:
# Pending → NBDPrepared → VMRunning → Fixing → Completed
```

### Check Details

```bash
# Get job details
kubectl describe offlinefixjob test-centos9-fix

# Check conditions
kubectl get offlinefixjob test-centos9-fix -o jsonpath='{.status.conditions}' | jq
```

### Monitor Components

```bash
# NBD prep daemon logs
kubectl logs -n hyper2kvm-system -l app=nbd-prep --tail=50 -f

# Operator logs
kubectl logs -n hyper2kvm-system -l app=hyper2kvm-operator --tail=50 -f

# VM logs (when running)
VM_NAME=$(kubectl get offlinefixjob test-centos9-fix -o jsonpath='{.status.vmName}')
kubectl logs -n hyper2kvm-system $VM_NAME
```

### Check Node Annotations

```bash
# See NBD status on node
NODE=$(kubectl get offlinefixjob test-centos9-fix -o jsonpath='{.status.node}')
kubectl get node $NODE -o jsonpath='{.metadata.annotations}' | jq | grep offlinefix
```

---

## Step 9: Verify Results

### Check Job Status

```bash
# Final status
kubectl get offlinefixjob test-centos9-fix -o yaml

# Check result
kubectl get offlinefixjob test-centos9-fix \
  -o jsonpath='{.status.result}' | jq
```

Expected output:
```json
{
  "success": true,
  "operations": [
    {
      "operation": "fstab",
      "success": true,
      "message": "...",
      "durationSeconds": 2.5
    },
    {
      "operation": "initramfs",
      "success": true,
      "message": "...",
      "durationSeconds": 45.2
    },
    {
      "operation": "grub",
      "success": true,
      "message": "...",
      "durationSeconds": 12.1
    },
    {
      "operation": "selinux",
      "success": true,
      "message": "...",
      "durationSeconds": 0.3
    }
  ],
  "bootConfidence": 95
}
```

### Check Boot Confidence

```bash
kubectl get offlinefixjob test-centos9-fix \
  -o jsonpath='{.status.result.bootConfidence}'
```

---

## Step 10: Cleanup

### Delete Test Job

```bash
kubectl delete offlinefixjob test-centos9-fix
```

This triggers automatic cleanup:
1. Controller deletes VM
2. Controller signals DaemonSet via node annotation
3. DaemonSet unmounts filesystem
4. DaemonSet disconnects NBD
5. Controller clears node annotations

### Verify Cleanup

```bash
# Check VM deleted
kubectl get vmi -n hyper2kvm-system

# Check node annotations cleared
kubectl get node $NODE -o jsonpath='{.metadata.annotations}' | jq | grep offlinefix

# Check NBD disconnected (on node)
ssh $NODE "lsblk | grep nbd"
```

---

## Troubleshooting

### NBD Not Attaching

```bash
# Check DaemonSet logs
kubectl logs -n hyper2kvm-system -l app=nbd-prep

# Check NBD module on node
kubectl exec -n hyper2kvm-system <nbd-prep-pod> -- lsmod | grep nbd

# Check NBD devices
kubectl exec -n hyper2kvm-system <nbd-prep-pod> -- ls -la /dev/nbd*
```

### VM Not Starting

```bash
# Check KubeVirt
kubectl get kubevirt -n kubevirt

# Check VMI status
kubectl get vmi -n hyper2kvm-system

# Check VMI events
kubectl describe vmi <vm-name> -n hyper2kvm-system

# Check virt-handler logs
kubectl logs -n kubevirt -l kubevirt.io=virt-handler --tail=100
```

### Fixers Failing

```bash
# Check VM logs
kubectl logs -n hyper2kvm-system <vm-name>

# Check if /vmroot is mounted correctly
kubectl exec -n hyper2kvm-system <vm-name> -- ls -la /vmroot/etc/

# Check job spec ConfigMap
kubectl get cm offline-fix-spec-test-centos9-fix -o yaml
```

### Cleanup Not Happening

```bash
# Check node annotations
kubectl get node $NODE -o jsonpath='{.metadata.annotations}' | jq

# Manually trigger cleanup (if needed)
kubectl annotate node $NODE offlinefix.hyper2kvm.io/cleanup=true

# Check DaemonSet logs
kubectl logs -n hyper2kvm-system -l app=nbd-prep --tail=50
```

---

## Production Checklist

Before deploying to production:

- [ ] Build and push Docker images to private registry
- [ ] Update image references in manifests
- [ ] Label NBD-capable nodes appropriately
- [ ] Test with real VMDK images
- [ ] Verify cleanup works correctly
- [ ] Set up monitoring/alerts
- [ ] Configure resource limits
- [ ] Test failure scenarios
- [ ] Document runbook for operators
- [ ] Set up RBAC policies

---

## Next Steps

### Integration with Migration CRD

To integrate OfflineFixJob with the Migration CRD:

1. Update Migration controller to create OfflineFixJob
2. Link Migration status to OfflineFixJob results
3. Use boot confidence score for migration validation

### Monitoring

Add Prometheus metrics:
- Job success/failure rates
- Fix operation durations
- Boot confidence scores
- NBD attachment times

### Advanced Features

- Multi-disk support
- LUKS encryption handling
- Custom fixer plugins
- Parallel fixer execution

---

## Summary

Phase 4 deployment provides:
✅ Kubernetes-native offline VM repair
✅ KubeVirt-safe architecture
✅ Production-ready error handling
✅ Clean lifecycle management
✅ Integration with Phase 3 fixers

**The system is now ready for production use!**
