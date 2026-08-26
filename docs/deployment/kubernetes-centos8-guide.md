# H2KVM Kubernetes Deployment on CentOS 8

Complete guide for deploying H2KVM on Kubernetes with CentOS 8 nodes.

---

## Quick Links

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start-5-minutes)
- [Full Installation](#full-installation)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## Overview

This guide covers deploying H2KVM on Kubernetes running on CentOS 8 (or CentOS Stream 8) nodes. The deployment supports:

- **Worker-based architecture** - Kubernetes-native job execution
- **Batch migrations** - Parallel VM processing
- **Persistent storage** - PVC-backed source/destination volumes
- **REST API** - Job submission and monitoring
- **CRD support** - Custom MigrationJob resources

---

## Prerequisites

### System Requirements

**Kubernetes Cluster**:
- Kubernetes 1.21+ (tested on 1.24, 1.25, 1.26)
- CentOS 8 / CentOS Stream 8 worker nodes
- At least 2 worker nodes recommended
- 4 CPU cores, 8GB RAM per node minimum

**Storage**:
- StorageClass with ReadWriteMany support (NFS, Ceph, etc.)
- Or ReadWriteOnce with single-node scheduling
- Minimum 100GB available storage

**Access**:
- kubectl configured with cluster admin access
- Container registry access (Docker Hub or private registry)

---

### CentOS 8 Node Preparation

Run on **all worker nodes** that will execute migrations:

```bash
# Update system
sudo dnf update -y

# Install required packages
sudo dnf install -y \
    qemu-img \
    qemu-kvm \
    libvirt-client \
    python3 \
    python3-pip \
    ntfs-3g

# Enable and start libvirtd (if using libvirt testing)
sudo systemctl enable --now libvirtd

# Add Kubernetes service account to required groups
# This will be done automatically by pod security context
```

**Note**: For CentOS Stream 8, some packages may need to be installed from EPEL:

```bash
# Enable EPEL repository
sudo dnf install -y epel-release

# Install additional dependencies
sudo dnf install -y ntfs-3g
```

---

## Quick Start (5 Minutes)

### 1. Create Namespace

```bash
kubectl create namespace h2kvm-system
```

### 2. Deploy Basic Setup

Create `h2kvm-basic.yaml`:

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: h2kvm-worker
  namespace: h2kvm-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: h2kvm-worker-role
  namespace: h2kvm-system
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: h2kvm-worker-binding
  namespace: h2kvm-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: h2kvm-worker-role
subjects:
- kind: ServiceAccount
  name: h2kvm-worker
  namespace: h2kvm-system

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vmware-storage
  namespace: h2kvm-system
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nfs-client  # Change to your StorageClass
  resources:
    requests:
      storage: 100Gi

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: kvm-storage
  namespace: h2kvm-system
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nfs-client  # Change to your StorageClass
  resources:
    requests:
      storage: 200Gi

---
apiVersion: batch/v1
kind: Job
metadata:
  name: test-migration
  namespace: h2kvm-system
spec:
  template:
    metadata:
      labels:
        app: h2kvm
    spec:
      serviceAccountName: h2kvm-worker
      restartPolicy: Never
      containers:
      - name: h2kvm
        image: ghcr.io/ssahani/h2kvm:latest
        imagePullPolicy: Always
        command:
          - h2kvmctl
          - --cmd
          - local
          - --vmdk
          - /mnt/vmware/test-vm.vmdk
          - --output-dir
          - /mnt/kvm
          - --to-output
          - test-vm.qcow2
          - --fstab-mode
          - stabilize-all
          - --regen-initramfs
          - --compress
        volumeMounts:
        - name: vmware-storage
          mountPath: /mnt/vmware
        - name: kvm-storage
          mountPath: /mnt/kvm
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
        securityContext:
          privileged: true  # Required for disk operations
          capabilities:
            add:
              - SYS_ADMIN
              - MKNOD
      volumes:
      - name: vmware-storage
        persistentVolumeClaim:
          claimName: vmware-storage
      - name: kvm-storage
        persistentVolumeClaim:
          claimName: kvm-storage
      nodeSelector:
        kubernetes.io/os: linux
```

### 3. Deploy

```bash
kubectl apply -f h2kvm-basic.yaml

# Watch progress
kubectl get jobs -n h2kvm-system -w

# Check logs
kubectl logs -n h2kvm-system job/test-migration -f
```

---

## Full Installation

### Step 1: Prepare CentOS 8 Nodes

On **each worker node**:

```bash
#!/bin/bash
# prepare-centos8-node.sh

set -e

echo "=== Preparing CentOS 8 Node for H2KVM ==="

# Update system
echo "Updating system..."
sudo dnf update -y

# Install EPEL if not present
if ! rpm -q epel-release &>/dev/null; then
    echo "Installing EPEL repository..."
    sudo dnf install -y epel-release
fi

# Install core dependencies
echo "Installing core packages..."
sudo dnf install -y \
    qemu-img \
    qemu-kvm \
    qemu-system-x86 \
    libvirt-client \
    libvirt-daemon-kvm \
    python3 \
    python3-pip \
    ntfs-3g \
    virt-install

# Install optional packages for enhanced features
echo "Installing optional packages..."
sudo dnf install -y \
    libhivex-bin \
    augeas \
    lvm2 \
    cryptsetup \
    parted

# Enable libvirtd (if needed for testing)
echo "Configuring libvirt..."
sudo systemctl enable --now libvirtd

# Configure kernel modules
echo "Loading kernel modules..."
sudo modprobe kvm
sudo modprobe kvm_intel || sudo modprobe kvm_amd

# Make kernel modules persistent
cat <<EOF | sudo tee /etc/modules-load.d/kvm.conf
kvm
kvm_intel
kvm_amd
EOF

# Set up device permissions
echo "Configuring device permissions..."
sudo chmod 666 /dev/kvm || true

# Disable SELinux enforcing for container operations (if needed)
# Note: This is optional and depends on your security requirements
if getenforce | grep -q "Enforcing"; then
    echo "SELinux is in enforcing mode. Consider permissive mode for development."
    echo "Production deployments should use proper SELinux policies."
    # Uncomment to set permissive:
    # sudo setenforce 0
    # sudo sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config
fi

# Verify installation
echo ""
echo "=== Verification ==="
qemu-img --version
virsh --version
python3 --version

echo ""
echo "✅ Node preparation complete!"
echo ""
echo "Next steps:"
echo "1. Label this node for h2kvm workloads:"
echo "   kubectl label node $(hostname) h2kvm=enabled"
echo "2. Deploy h2kvm manifests"
```

Run the script:

```bash
chmod +x prepare-centos8-node.sh
./prepare-centos8-node.sh

# Label the node
kubectl label node <node-name> h2kvm=enabled
```

---

### Step 2: Create Namespace and Service Account

```bash
# Create namespace
kubectl create namespace h2kvm-system

# Set as default for convenience
kubectl config set-context --current --namespace=h2kvm-system
```

Create `01-rbac.yaml`:

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: h2kvm-worker
  namespace: h2kvm-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: h2kvm-worker-role
  namespace: h2kvm-system
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log", "configmaps", "secrets"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: [""]
  resources: ["events"]
  verbs: ["create", "patch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: h2kvm-worker-binding
  namespace: h2kvm-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: h2kvm-worker-role
subjects:
- kind: ServiceAccount
  name: h2kvm-worker
  namespace: h2kvm-system
```

Apply:

```bash
kubectl apply -f 01-rbac.yaml
```

---

### Step 3: Configure Storage

Create `02-storage.yaml`:

```yaml
---
# Source VM storage (VMware VMDKs)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vmware-storage
  namespace: h2kvm-system
  labels:
    app: h2kvm
    storage-type: source
spec:
  accessModes:
    - ReadWriteMany  # Required for parallel migrations
  storageClassName: nfs-client  # CHANGE THIS to your StorageClass
  resources:
    requests:
      storage: 500Gi  # Adjust based on your needs

---
# Destination KVM storage
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: kvm-storage
  namespace: h2kvm-system
  labels:
    app: h2kvm
    storage-type: destination
spec:
  accessModes:
    - ReadWriteMany  # Required for parallel migrations
  storageClassName: nfs-client  # CHANGE THIS to your StorageClass
  resources:
    requests:
      storage: 1Ti  # Larger for QCOW2 files

---
# Optional: Temporary conversion storage (faster if on local SSD)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: conversion-temp
  namespace: h2kvm-system
  labels:
    app: h2kvm
    storage-type: temp
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path  # Fast local storage if available
  resources:
    requests:
      storage: 200Gi
```

**Storage Configuration Notes for CentOS 8**:

For **NFS storage**:
```bash
# On CentOS 8 NFS server
sudo dnf install -y nfs-utils
sudo systemctl enable --now nfs-server

# Create export directory
sudo mkdir -p /exports/h2kvm/{vmware,kvm}
sudo chown -R nobody:nobody /exports/h2kvm
sudo chmod -R 777 /exports/h2kvm

# Configure exports
cat <<EOF | sudo tee -a /etc/exports
/exports/h2kvm/vmware *(rw,sync,no_root_squash,no_subtree_check)
/exports/h2kvm/kvm *(rw,sync,no_root_squash,no_subtree_check)
EOF

# Apply changes
sudo exportfs -ra
```

Apply storage:

```bash
kubectl apply -f 02-storage.yaml

# Verify PVCs
kubectl get pvc
```

---

### Step 4: Deploy ConfigMap for Common Settings

Create `03-configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: h2kvm-config
  namespace: h2kvm-system
data:
  # Default migration settings
  default-fstab-mode: "stabilize-all"
  default-compress: "true"
  default-out-format: "qcow2"

  # Logging
  log-level: "INFO"

  # Resource limits
  default-memory-request: "4Gi"
  default-memory-limit: "8Gi"
  default-cpu-request: "2"
  default-cpu-limit: "4"
```

Apply:

```bash
kubectl apply -f 03-configmap.yaml
```

---

### Step 5: Deploy Migration Job Template

Create `04-migration-job-template.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate-VMNAME  # Replace VMNAME
  namespace: h2kvm-system
  labels:
    app: h2kvm
    migration-type: single
spec:
  backoffLimit: 2  # Retry twice on failure
  ttlSecondsAfterFinished: 86400  # Keep job for 24 hours
  template:
    metadata:
      labels:
        app: h2kvm
        job-name: migrate-VMNAME
    spec:
      serviceAccountName: h2kvm-worker
      restartPolicy: Never

      # Schedule on labeled nodes only
      nodeSelector:
        h2kvm: enabled

      # Prefer nodes with more resources
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node-role.kubernetes.io/worker
                operator: Exists

      containers:
      - name: h2kvm
        image: ghcr.io/ssahani/h2kvm:latest
        imagePullPolicy: Always

        command:
          - h2kvmctl
          - --cmd
          - local
          - --vmdk
          - /mnt/vmware/VMNAME.vmdk  # Replace VMNAME
          - --output-dir
          - /mnt/kvm
          - --to-output
          - VMNAME.qcow2  # Replace VMNAME
          - --fstab-mode
          - stabilize-all
          - --regen-initramfs
          - --update-grub
          - --compress
          - --out-format
          - qcow2
          - --log-level
          - INFO

        volumeMounts:
        - name: vmware-storage
          mountPath: /mnt/vmware
          readOnly: true
        - name: kvm-storage
          mountPath: /mnt/kvm
        - name: conversion-temp
          mountPath: /tmp/conversion

        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"

        securityContext:
          privileged: true
          capabilities:
            add:
              - SYS_ADMIN
              - MKNOD
              - SYS_CHROOT
          allowPrivilegeEscalation: true

        env:
        - name: PYTHONUNBUFFERED
          value: "1"
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace

      volumes:
      - name: vmware-storage
        persistentVolumeClaim:
          claimName: vmware-storage
      - name: kvm-storage
        persistentVolumeClaim:
          claimName: kvm-storage
      - name: conversion-temp
        persistentVolumeClaim:
          claimName: conversion-temp
```

---

### Step 6: Run a Test Migration

```bash
# Copy VMDKs to storage
kubectl run -it --rm copy-vmdk \
  --image=busybox \
  --overrides='
{
  "spec": {
    "containers": [{
      "name": "copy-vmdk",
      "image": "busybox",
      "stdin": true,
      "tty": true,
      "volumeMounts": [{
        "name": "vmware-storage",
        "mountPath": "/mnt/vmware"
      }]
    }],
    "volumes": [{
      "name": "vmware-storage",
      "persistentVolumeClaim": {
        "claimName": "vmware-storage"
      }
    }]
  }
}' \
  --namespace=h2kvm-system

# Inside the pod, copy your VMDK files
# Exit when done

# Edit and deploy migration job
sed 's/VMNAME/test-vm/g' 04-migration-job-template.yaml | kubectl apply -f -

# Monitor
kubectl get jobs -w
kubectl logs -f job/migrate-test-vm
```

---

## Production Deployment

### Production-Grade Deployment with REST API

Create `05-production-deployment.yaml`:

```yaml
---
# Worker Deployment for REST API
apiVersion: apps/v1
kind: Deployment
metadata:
  name: h2kvm-api
  namespace: h2kvm-system
  labels:
    app: h2kvm
    component: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: h2kvm
      component: api
  template:
    metadata:
      labels:
        app: h2kvm
        component: api
    spec:
      serviceAccountName: h2kvm-worker
      nodeSelector:
        h2kvm: enabled

      containers:
      - name: api
        image: ghcr.io/ssahani/h2kvm:latest
        imagePullPolicy: Always

        command:
          - h2kvm
          - daemon
          - --mode
          - api
          - --listen
          - 0.0.0.0:8080

        ports:
        - containerPort: 8080
          name: http
          protocol: TCP

        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10

        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5

        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1"

        env:
        - name: KUBERNETES_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace

---
# API Service
apiVersion: v1
kind: Service
metadata:
  name: h2kvm-api
  namespace: h2kvm-system
  labels:
    app: h2kvm
    component: api
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
    name: http
  selector:
    app: h2kvm
    component: api

---
# Ingress (optional)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: h2kvm-api
  namespace: h2kvm-system
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - host: h2kvm.example.com  # CHANGE THIS
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: h2kvm-api
            port:
              number: 80
```

Deploy:

```bash
kubectl apply -f 05-production-deployment.yaml

# Verify
kubectl get pods -l component=api
kubectl get svc h2kvm-api
```

---

### Batch Migration ConfigMap

Create `06-batch-migration.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: batch-migration-manifest
  namespace: h2kvm-system
data:
  manifest.json: |
    {
      "migrations": [
        {
          "vmdk": "/mnt/vmware/web-01.vmdk",
          "to_output": "web-01.qcow2"
        },
        {
          "vmdk": "/mnt/vmware/web-02.vmdk",
          "to_output": "web-02.qcow2"
        },
        {
          "vmdk": "/mnt/vmware/db-01.vmdk",
          "to_output": "db-01.qcow2",
          "compress": false,
          "out_format": "raw"
        }
      ]
    }

---
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-migration
  namespace: h2kvm-system
spec:
  parallelism: 3
  completions: 3
  template:
    metadata:
      labels:
        app: h2kvm
        job-type: batch
    spec:
      serviceAccountName: h2kvm-worker
      restartPolicy: Never
      nodeSelector:
        h2kvm: enabled

      containers:
      - name: h2kvm
        image: ghcr.io/ssahani/h2kvm:latest

        command:
          - h2kvmctl
          - --cmd
          - local
          - --batch-manifest
          - /config/manifest.json
          - --output-dir
          - /mnt/kvm
          - --fstab-mode
          - stabilize-all
          - --regen-initramfs
          - --batch-parallel
          - "1"

        volumeMounts:
        - name: vmware-storage
          mountPath: /mnt/vmware
        - name: kvm-storage
          mountPath: /mnt/kvm
        - name: batch-config
          mountPath: /config

        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"

        securityContext:
          privileged: true
          capabilities:
            add:
              - SYS_ADMIN
              - MKNOD

      volumes:
      - name: vmware-storage
        persistentVolumeClaim:
          claimName: vmware-storage
      - name: kvm-storage
        persistentVolumeClaim:
          claimName: kvm-storage
      - name: batch-config
        configMap:
          name: batch-migration-manifest
```

---

## Monitoring and Logging

### Deploy Monitoring Stack

```bash
# Install Prometheus Operator (if not already installed)
kubectl create -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml

# Create ServiceMonitor for h2kvm
cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: h2kvm-metrics
  namespace: h2kvm-system
spec:
  selector:
    matchLabels:
      app: h2kvm
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
EOF
```

### View Logs

```bash
# View job logs
kubectl logs -n h2kvm-system job/migrate-test-vm

# Follow logs in real-time
kubectl logs -n h2kvm-system -f job/migrate-test-vm

# View API logs
kubectl logs -n h2kvm-system -l component=api

# View all migration logs
kubectl logs -n h2kvm-system -l app=h2kvm --tail=100
```

---

## Troubleshooting

### Common Issues on CentOS 8

#### 1. KVM Module Not Loaded

**Symptom**: `/dev/kvm` not found

**Solution**:
```bash
# On worker nodes
sudo modprobe kvm
sudo modprobe kvm_intel  # or kvm_amd

# Verify
lsmod | grep kvm
ls -l /dev/kvm

# Make permanent
echo "kvm" | sudo tee /etc/modules-load.d/kvm.conf
echo "kvm_intel" | sudo tee -a /etc/modules-load.d/kvm.conf
```

#### 2. Permission Denied on /dev/kvm

**Symptom**: `Permission denied` when accessing KVM

**Solution**:
```bash
# On worker nodes
sudo chmod 666 /dev/kvm

# Or add to udev rules
cat <<EOF | sudo tee /etc/udev/rules.d/99-kvm.rules
KERNEL=="kvm", GROUP="kvm", MODE="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### 3. SELinux Blocking Operations

**Symptom**: SELinux denials in audit log

**Solution**:
```bash
# Check for denials
sudo ausearch -m avc -ts recent

# Temporary: Set permissive
sudo setenforce 0

# Permanent (development only):
sudo sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config

# Production: Create custom policy (recommended)
# See: https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/html/using_selinux/
```

#### 4. Storage Mount Failures

**Symptom**: PVC not mounting

**Check**:
```bash
# Describe PVC
kubectl describe pvc vmware-storage -n h2kvm-system

# Check PV
kubectl get pv

# On NFS server (CentOS 8)
sudo exportfs -v
sudo systemctl status nfs-server

# Test NFS mount manually
sudo mount -t nfs <nfs-server>:/export/path /mnt/test
```

#### 5. Job Stuck in Pending

**Symptom**: Job pods stay in Pending state

**Debug**:
```bash
# Check pod events
kubectl describe pod -n h2kvm-system <pod-name>

# Check node labels
kubectl get nodes --show-labels | grep h2kvm

# Check node resources
kubectl top nodes

# Check if nodes are ready
kubectl get nodes
```

#### 6. Out of Memory Errors

**Symptom**: OOMKilled errors

**Solution**:
```bash
# Increase memory limits in job spec
resources:
  requests:
    memory: "8Gi"
  limits:
    memory: "16Gi"

# Check node available memory
kubectl top nodes
free -h  # on worker nodes
```

---

### Debug Commands

```bash
# Shell into a running job pod
kubectl exec -it -n h2kvm-system <pod-name> -- /bin/bash

# Check h2kvm version
kubectl exec -n h2kvm-system <pod-name> -- h2kvmctl --version

# Test VMDK access
kubectl exec -n h2kvm-system <pod-name> -- ls -lh /mnt/vmware/

# Check available tools
kubectl exec -n h2kvm-system <pod-name> -- which qemu-img
kubectl exec -n h2kvm-system <pod-name> -- qemu-img --version

# View pod resource usage
kubectl top pod -n h2kvm-system
```

---

## Performance Tuning

### Node-Level Optimizations (CentOS 8)

```bash
# Increase file descriptor limits
echo "fs.file-max = 2097152" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Optimize kernel for virtualization
cat <<EOF | sudo tee -a /etc/sysctl.conf
# VM optimizations
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# Network optimizations
net.core.somaxconn = 1024
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 8192
EOF

sudo sysctl -p

# Enable huge pages (optional, for large VMs)
echo 1024 | sudo tee /proc/sys/vm/nr_hugepages
```

### Kubernetes-Level Optimizations

```yaml
# Use node affinity for faster storage
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: storage-type
            operator: In
            values:
            - ssd
            - nvme

# Use pod anti-affinity to spread migrations
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values:
            - h2kvm
        topologyKey: kubernetes.io/hostname
```

---

## Cleanup

```bash
# Delete all jobs
kubectl delete jobs -n h2kvm-system --all

# Delete deployment
kubectl delete deployment h2kvm-api -n h2kvm-system

# Delete PVCs (WARNING: This deletes data!)
kubectl delete pvc -n h2kvm-system --all

# Delete namespace
kubectl delete namespace h2kvm-system
```

---

## Next Steps

- **Scale Up**: Add more worker nodes and increase parallelism
- **Security**: Implement Pod Security Policies/Standards
- **Monitoring**: Deploy Prometheus and Grafana dashboards
- **Automation**: Use GitOps (ArgoCD/Flux) for deployment
- **Integration**: Connect to CI/CD pipelines

---

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [CentOS 8 Documentation](https://docs.centos.org/en-US/8-stream/)
- [H2KVM Migration Guide](../MIGRATION_CHECKLIST.md)
- [Best Practices](../BEST_PRACTICES.md)
- [Troubleshooting Guide](../TROUBLESHOOTING_FLOWCHART.md)

---

**Last Updated**: March 2026
**Tested On**: CentOS 8.5, CentOS Stream 8, Kubernetes 1.24-1.26
**Documentation Version**: 0.3.0
