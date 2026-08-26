# H2KVM on Kubernetes + CentOS 8 - Quick Start

Deploy H2KVM on Kubernetes with CentOS 8 worker nodes in under 10 minutes.

---

## TL;DR - One-Command Deployment

```bash
# 1. Prepare nodes
./scripts/deploy-k8s-centos8.sh prepare

# 2. Deploy H2KVM
./scripts/deploy-k8s-centos8.sh deploy

# 3. Run test
./scripts/deploy-k8s-centos8.sh test
```

---

## Prerequisites

- **Kubernetes cluster** with CentOS 8 worker nodes
- **kubectl** configured with admin access
- **NFS server** or other ReadWriteMany storage (optional: can use ReadWriteOnce)
- At least **2 worker nodes** with 4 CPU cores, 8GB RAM each

---

## Step-by-Step Deployment

### Step 1: Prepare CentOS 8 Worker Nodes

Run the preparation script to generate node setup commands:

```bash
./scripts/deploy-k8s-centos8.sh prepare
```

This creates `/tmp/prepare-node.sh`. Copy and run it on each worker node:

```bash
# On your local machine
scp /tmp/prepare-node.sh root@worker-node-1:/tmp/
scp /tmp/prepare-node.sh root@worker-node-2:/tmp/

# On each worker node
ssh root@worker-node-1
bash /tmp/prepare-node.sh
exit

ssh root@worker-node-2
bash /tmp/prepare-node.sh
exit
```

**What this does**:
- Installs qemu-img, qemu-kvm, libvirt, Python3
- Loads KVM kernel modules
- Configures /dev/kvm permissions
- Sets up required system packages

**Label the nodes**:

```bash
kubectl label node worker-node-1 h2kvm=enabled
kubectl label node worker-node-2 h2kvm=enabled

# Verify
kubectl get nodes -L h2kvm
```

---

### Step 2: Deploy H2KVM

Deploy the core components:

```bash
# Basic deployment with defaults
./scripts/deploy-k8s-centos8.sh deploy

# Or with custom storage settings
STORAGE_CLASS=nfs-client \
VMWARE_STORAGE_SIZE=500Gi \
KVM_STORAGE_SIZE=1Ti \
./scripts/deploy-k8s-centos8.sh deploy
```

**What this creates**:
- Namespace: `h2kvm-system`
- ServiceAccount and RBAC
- PersistentVolumeClaims for source/destination storage
- ConfigMaps for configuration

**Verify deployment**:

```bash
./scripts/deploy-k8s-centos8.sh status

# Or manually:
kubectl get all -n h2kvm-system
kubectl get pvc -n h2kvm-system
```

---

### Step 3: Upload VMDKs to Storage

Copy your VMware VMDKs to the source storage PVC:

```bash
# Start a temporary pod with storage mounted
kubectl run -it --rm upload-vmdk \
  --image=alpine \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "upload-vmdk",
        "image": "alpine",
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

# Inside the pod, you can use wget, scp, or mount NFS
# For example:
wget -O /mnt/vmware/test-vm.vmdk http://your-server/test-vm.vmdk

# Or use kubectl cp from outside:
kubectl cp local-vm.vmdk h2kvm-system/upload-vmdk:/mnt/vmware/test-vm.vmdk

# Exit when done
exit
```

**Alternative: Direct NFS mount**:

If using NFS storage, you can copy directly:

```bash
# Mount NFS on your local machine
sudo mount -t nfs nfs-server:/export/h2kvm /mnt/nfs

# Copy VMDKs
sudo cp /vmware/vms/*.vmdk /mnt/nfs/vmware/

# Unmount
sudo umount /mnt/nfs
```

---

### Step 4: Run Your First Migration

Create a migration job:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate-test-vm
  namespace: h2kvm-system
spec:
  template:
    metadata:
      labels:
        app: h2kvm
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
EOF
```

**Monitor the migration**:

```bash
# Watch job status
kubectl get jobs -n h2kvm-system -w

# View logs
kubectl logs -n h2kvm-system -f job/migrate-test-vm

# Check completion
kubectl wait --for=condition=complete job/migrate-test-vm -n h2kvm-system --timeout=3600s
```

---

### Step 5: Retrieve Migrated VM

Download the migrated QCOW2 file:

```bash
# Start a pod to access storage
kubectl run -it --rm download-qcow2 \
  --image=alpine \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "download-qcow2",
        "image": "alpine",
        "stdin": true,
        "tty": true,
        "volumeMounts": [{
          "name": "kvm-storage",
          "mountPath": "/mnt/kvm"
        }]
      }],
      "volumes": [{
        "name": "kvm-storage",
        "persistentVolumeClaim": {
          "claimName": "kvm-storage"
        }
      }]
    }
  }' \
  --namespace=h2kvm-system

# List migrated files
ls -lh /mnt/kvm/

# Exit and copy from outside
exit

# Copy to local machine
kubectl cp h2kvm-system/download-qcow2:/mnt/kvm/test-vm.qcow2 ./test-vm.qcow2
```

---

## Batch Migration Example

Migrate multiple VMs in parallel:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: batch-manifest
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
          "to_output": "db-01.qcow2"
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
          name: batch-manifest
EOF

# Monitor
kubectl get jobs -n h2kvm-system -w
kubectl logs -n h2kvm-system -l app=h2kvm
```

---

## Common Operations

### View All Migrations

```bash
# List all jobs
kubectl get jobs -n h2kvm-system

# Check job status
kubectl get jobs -n h2kvm-system -o wide

# View job details
kubectl describe job migrate-test-vm -n h2kvm-system
```

### Debug Failed Migration

```bash
# Get pod name
POD=$(kubectl get pods -n h2kvm-system -l job-name=migrate-test-vm -o jsonpath='{.items[0].metadata.name}')

# View logs
kubectl logs -n h2kvm-system $POD

# Get events
kubectl get events -n h2kvm-system --field-selector involvedObject.name=$POD

# Shell into pod (if still running)
kubectl exec -it -n h2kvm-system $POD -- /bin/bash
```

### Clean Up Old Jobs

```bash
# Delete completed jobs older than 24 hours
kubectl delete jobs -n h2kvm-system --field-selector status.successful=1

# Delete failed jobs
kubectl delete jobs -n h2kvm-system --field-selector status.failed=1

# Delete all jobs
kubectl delete jobs -n h2kvm-system --all
```

---

## Troubleshooting

### Job Stays in Pending

**Check**:
```bash
kubectl describe pod -n h2kvm-system <pod-name>
```

**Common causes**:
- No nodes with label `h2kvm=enabled`
- Insufficient resources
- PVC not bound

**Fix**:
```bash
# Check node labels
kubectl get nodes -L h2kvm

# Check PVC status
kubectl get pvc -n h2kvm-system

# Check node resources
kubectl top nodes
```

### Permission Denied on /dev/kvm

**On worker nodes**:
```bash
sudo chmod 666 /dev/kvm
ls -l /dev/kvm
```

### SELinux Issues

**On worker nodes**:
```bash
# Check for denials
sudo ausearch -m avc -ts recent

# Temporary fix (development only)
sudo setenforce 0
```

---

## Cleanup

Remove all H2KVM resources:

```bash
# Using script
./scripts/deploy-k8s-centos8.sh cleanup

# Or manually
kubectl delete namespace h2kvm-system
```

---

## Next Steps

- **[Full Kubernetes Guide](kubernetes-centos8-guide.md)** - Complete documentation
- **[Production Deployment](../deployment/kubernetes.md)** - Production-grade setup
- **[Monitoring](../MONITORING_GUIDE.md)** - Set up monitoring
- **[Best Practices](../BEST_PRACTICES.md)** - Migration best practices

---

## Support

- **Documentation**: [https://github.com/ssahani/h2kvm/docs](https://github.com/ssahani/h2kvm/docs)
- **Issues**: [https://github.com/ssahani/h2kvm/issues](https://github.com/ssahani/h2kvm/issues)
- **Discussions**: [https://github.com/ssahani/h2kvm/discussions](https://github.com/ssahani/h2kvm/discussions)

---

**Last Updated**: March 2026
**Tested On**: CentOS 8.5, CentOS Stream 8, Kubernetes 1.24-1.26
