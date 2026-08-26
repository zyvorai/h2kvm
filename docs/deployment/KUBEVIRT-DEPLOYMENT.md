# KubeVirt Deployment Guide - RHEL 8.8 VM

Complete guide for deploying the migrated RHEL 8.8 VM to KubeVirt on k3d.

## 📋 Overview

This deployment takes the RHEL 8.8 VM that was migrated from VMware ESXi using hyper2kvm and runs it on KubeVirt (Kubernetes-native virtualization).

**Architecture:**
```
VMware ESXi (VMDK)
    ↓ [hyper2kvm migration]
libvirt (QCOW2)
    ↓ [KubeVirt deployment]
Kubernetes/KubeVirt (VM as Pod)
```

## 🚀 Quick Start (One Command)

For a complete automated deployment on k3d:

```bash
chmod +x deploy-to-kubevirt-k3d.sh
./deploy-to-kubevirt-k3d.sh
```

This will:
1. ✅ Create k3d cluster
2. ✅ Install KubeVirt
3. ✅ Install CDI (Containerized Data Importer)
4. ✅ Upload QCOW2 image
5. ✅ Deploy RHEL 8.8 VM
6. ✅ Configure networking and services

## 📦 Prerequisites

### Required Tools

1. **k3d** (lightweight Kubernetes)
   ```bash
   curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
   ```

2. **kubectl** (Kubernetes CLI)
   ```bash
   # Linux
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   chmod +x kubectl
   sudo mv kubectl /usr/local/bin/
   ```

3. **virtctl** (KubeVirt CLI)
   ```bash
   VERSION=v1.2.0
   wget https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/virtctl-${VERSION}-linux-amd64
   chmod +x virtctl-${VERSION}-linux-amd64
   sudo mv virtctl-${VERSION}-linux-amd64 /usr/local/bin/virtctl
   ```

### Verify Prerequisites

```bash
k3d version
kubectl version --client
virtctl version --client
```

## 🎯 Manual Deployment Steps

### Step 1: Create k3d Cluster

```bash
k3d cluster create rhel-kubevirt \
    --agents 1 \
    --api-port 6550 \
    --port "30022:30022@server:0" \
    --port "30590:30590@server:0" \
    --k3s-arg "--disable=traefik@server:0"
```

**Port Mappings:**
- `30022` - SSH access to VM
- `30590` - VNC console access

### Step 2: Install KubeVirt

```bash
# Set KubeVirt version
export KUBEVIRT_VERSION=v1.2.0

# Install KubeVirt Operator
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml

# Install KubeVirt CR
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml

# Wait for KubeVirt to be ready
kubectl wait --for=condition=Available kubevirt kubevirt -n kubevirt --timeout=600s
```

### Step 3: Install CDI (Containerized Data Importer)

```bash
export CDI_VERSION=v1.59.0

kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml
kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml

# Wait for CDI to be ready
kubectl wait --for=condition=Available cdi cdi -n cdi --timeout=300s
```

### Step 4: Upload QCOW2 Image

```bash
# Create namespace
kubectl create namespace rhel-vms

# Upload image using virtctl
virtctl image-upload pvc rhel8-disk \
    --namespace=rhel-vms \
    --image-path=./output/rhel8.8-fixed.qcow2 \
    --size=20Gi \
    --insecure \
    --force-bind
```

**Alternative: Use the upload script**
```bash
chmod +x upload-to-kubevirt.sh
./upload-to-kubevirt.sh rhel-vms
```

### Step 5: Deploy the VM

```bash
kubectl apply -f kubevirt-rhel8.8-deployment.yaml
```

## 📊 VM Configuration

The deployed VM has the following specifications:

| Component | Configuration |
|-----------|---------------|
| **OS** | RHEL 8.8 Beta (Ootpa) |
| **Memory** | 4 GiB |
| **vCPUs** | 2 (1 socket, 2 cores) |
| **Disk** | 20 GiB (virtio) |
| **Network** | virtio (pod networking) |
| **Machine** | q35 (modern chipset) |
| **Firmware** | BIOS (SeaBIOS) |
| **Graphics** | VNC + Serial Console |

## 🔌 Accessing the VM

### Method 1: Console Access (virtctl)

```bash
# Serial console
virtctl console rhel8-migrated -n rhel-vms

# Exit: Ctrl+] or Ctrl+5
```

### Method 2: VNC Console

```bash
# Launch VNC viewer
virtctl vnc rhel8-migrated -n rhel-vms

# Or port-forward and use any VNC client
kubectl port-forward -n rhel-vms service/rhel8-vnc 5900:5900
# Then connect to: localhost:5900
```

### Method 3: SSH (via NodePort)

```bash
# SSH to the VM via k3d node
ssh -p 30022 cloud-user@localhost

# Default password: redhat
```

### Method 4: Direct Pod Access

```bash
# Get VMI (VirtualMachineInstance) name
kubectl get vmi -n rhel-vms

# SSH into the VMI pod
kubectl exec -it virt-launcher-rhel8-migrated-xxxxx -n rhel-vms -- /bin/sh
```

## 🛠️ VM Management

### Check VM Status

```bash
# List all VMs
kubectl get vm,vmi -n rhel-vms

# Get detailed VM info
kubectl describe vm rhel8-migrated -n rhel-vms

# Watch VM events
kubectl get events -n rhel-vms --watch
```

### Control VM Power State

```bash
# Stop VM
virtctl stop rhel8-migrated -n rhel-vms

# Start VM
virtctl start rhel8-migrated -n rhel-vms

# Restart VM
virtctl restart rhel8-migrated -n rhel-vms

# Pause VM
virtctl pause vm rhel8-migrated -n rhel-vms

# Unpause VM
virtctl unpause vm rhel8-migrated -n rhel-vms
```

### VM Migration (Live)

```bash
# Migrate VM to another node (if you have multiple nodes)
virtctl migrate rhel8-migrated -n rhel-vms

# Check migration status
kubectl get virtualmachineinstancemigration -n rhel-vms
```

### Access VM Logs

```bash
# Get VM serial console logs
kubectl logs -n rhel-vms virt-launcher-rhel8-migrated-xxxxx

# Follow logs
kubectl logs -f -n rhel-vms virt-launcher-rhel8-migrated-xxxxx
```

## 🔍 Troubleshooting

### VM Won't Start

```bash
# Check VMI status
kubectl describe vmi rhel8-migrated -n rhel-vms

# Check pod events
kubectl get events -n rhel-vms --sort-by='.lastTimestamp'

# Check virt-launcher pod
kubectl get pods -n rhel-vms
kubectl logs -n rhel-vms virt-launcher-rhel8-migrated-xxxxx
```

### PVC Issues

```bash
# Check PVC status
kubectl get pvc -n rhel-vms
kubectl describe pvc rhel8-disk -n rhel-vms

# Check PV
kubectl get pv
```

### Networking Issues

```bash
# Check if VM has IP
kubectl get vmi rhel8-migrated -n rhel-vms -o jsonpath='{.status.interfaces[0].ipAddress}'

# Test connectivity from another pod
kubectl run -it --rm debug --image=busybox --restart=Never -- sh
# Inside pod: ping <VM_IP>
```

### CDI Upload Issues

```bash
# Check CDI upload pod
kubectl get pods -n rhel-vms | grep upload

# Check upload logs
kubectl logs -n rhel-vms cdi-upload-rhel8-disk
```

## 📸 Snapshots and Backups

### Create VM Snapshot

```bash
cat <<EOF | kubectl apply -f -
apiVersion: snapshot.kubevirt.io/v1alpha1
kind: VirtualMachineSnapshot
metadata:
  name: rhel8-snapshot-$(date +%Y%m%d)
  namespace: rhel-vms
spec:
  source:
    apiGroup: kubevirt.io
    kind: VirtualMachine
    name: rhel8-migrated
EOF
```

### List Snapshots

```bash
kubectl get vmsnapshot -n rhel-vms
```

### Restore from Snapshot

```bash
cat <<EOF | kubectl apply -f -
apiVersion: snapshot.kubevirt.io/v1alpha1
kind: VirtualMachineRestore
metadata:
  name: rhel8-restore-$(date +%Y%m%d)
  namespace: rhel-vms
spec:
  target:
    apiGroup: kubevirt.io
    kind: VirtualMachine
    name: rhel8-migrated
  virtualMachineSnapshotName: rhel8-snapshot-20260219
EOF
```

## 🧹 Cleanup

### Delete VM (keep disk)

```bash
kubectl delete vm rhel8-migrated -n rhel-vms
```

### Delete VM and disk

```bash
kubectl delete vm rhel8-migrated -n rhel-vms
kubectl delete pvc rhel8-disk -n rhel-vms
```

### Delete namespace

```bash
kubectl delete namespace rhel-vms
```

### Delete entire k3d cluster

```bash
k3d cluster delete rhel-kubevirt
```

## 🎓 Additional Resources

- **KubeVirt Documentation**: https://kubevirt.io/user-guide/
- **CDI Documentation**: https://github.com/kubevirt/containerized-data-importer
- **k3d Documentation**: https://k3d.io/
- **virtctl Commands**: https://kubevirt.io/user-guide/operations/virtctl_client_tool/

## 📊 Resource Files

This deployment includes:

1. **kubevirt-rhel8.8-deployment.yaml** - Complete VM definition with all resources
2. **deploy-to-kubevirt-k3d.sh** - Automated deployment script
3. **upload-to-kubevirt.sh** - Quick image upload script
4. **KUBEVIRT-DEPLOYMENT.md** - This guide

## ✅ Migration Validation

After VM boots, validate the migration:

```bash
# Connect to VM console
virtctl console rhel8-migrated -n rhel-vms

# Check kernel
uname -r
# Expected: 4.18.0-432.el8.x86_64

# Check OS
cat /etc/redhat-release
# Expected: Red Hat Enterprise Linux release 8.8 Beta (Ootpa)

# Check disks
lsblk
# Expected: vda (virtio disk)

# Check fstab
cat /etc/fstab
# Expected: UUIDs for all filesystems

# Check network
ip addr
nmcli connection show

# Check services
systemctl status
```

## 🎉 Success Indicators

Your migration is successful if:

- ✅ VM boots without errors
- ✅ Serial console is accessible
- ✅ Network interface is up with IP
- ✅ fstab shows UUID-based mounts
- ✅ Disk is using virtio driver (vda)
- ✅ SSH service is running
- ✅ QEMU guest agent is active

---

**Migrated with hyper2kvm** 🚀
VMware ESXi → libvirt → KubeVirt
