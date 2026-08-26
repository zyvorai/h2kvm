# Storage Backend Failure

## Scenario
Storage subsystem failures during migration: PVC unavailable, provisioner down, disk full, I/O errors, or snapshot failures.

**Common causes:**
- Disk space exhausted on worker nodes
- Storage provisioner (local-path, Rook, NFS) crashed
- Network storage (NFS, iSCSI, Ceph) unreachable
- PVC stuck in Pending (WaitForFirstConsumer binding issues)
- Underlying disk hardware failures
- Filesystem corruption or read-only remount

## Symptoms / How to Detect

### Kubernetes Migrations
```bash
# Check PVC status (look for Pending, Lost, Failed)
kubectl get pvc -n h2kvm-migration
kubectl get pvc -A | grep -vE "Bound|Available"

# Check for Pending PVCs with details
kubectl describe pvc -n h2kvm-migration | grep -A10 "Events:"

# Check storage provisioner health
kubectl get pods -n kube-system | grep -E "local-path|rook|nfs"

# Check storage class availability
kubectl get sc
kubectl describe sc <storage-class-name>

# Check for I/O errors in pod logs
kubectl logs -n h2kvm-migration <pod> | grep -iE "i/o error|read-only|no space left"

# Check DataVolume status (CDI)
kubectl get dv -A
kubectl describe dv <name> -n h2kvm-migration | grep -A5 status
```

### Node-Level Checks
```bash
# Check disk space on nodes
kubectl top nodes
kubectl get nodes -o custom-columns=NAME:.metadata.name,DISK:.status.allocatable.ephemeral-storage

# SSH to node or use kubectl debug
kubectl debug node/<node-name> -it --image=ubuntu
# Inside debug container:
chroot /host
df -h
df -i  # check inode usage
du -sh /var/lib/kubelet/pods/* | sort -h | tail -10

# Check for disk errors in kernel log
dmesg | grep -iE "error|fail|i/o"
journalctl -k | grep -iE "disk|storage|i/o"

# Check filesystem health
sudo fsck -n /dev/sda1  # dry-run check

# Check for read-only filesystems
mount | grep "ro,"
```

### CLI Migrations
```bash
# Check disk space in output directory
df -h <output-dir>
df -i <output-dir>

# Check for I/O errors
dmesg | grep -iE "i/o error|ext4|xfs"
journalctl --since "1 hour ago" | grep -i "i/o"

# Check write permissions
touch <output-dir>/test-write
rm <output-dir>/test-write
```

## Root Cause Analysis Steps

### 1. Identify storage backend
```bash
# Determine storage class used by PVC
kubectl get pvc <name> -n h2kvm-migration -o yaml | grep storageClassName

# Check storage class provisioner
kubectl get sc <storage-class> -o yaml | grep provisioner

# For local-path (k3d, k3s)
kubectl get pods -n kube-system -l app=local-path-provisioner

# For Rook/Ceph
kubectl get cephcluster -n rook-ceph
kubectl get pods -n rook-ceph

# For NFS
kubectl get pods -n nfs-provisioner
showmount -e <nfs-server>
```

### 2. Check provisioner logs
```bash
# local-path-provisioner
kubectl logs -n kube-system -l app=local-path-provisioner --tail=100

# Rook/Ceph
kubectl logs -n rook-ceph -l app=rook-ceph-operator --tail=100

# NFS provisioner
kubectl logs -n nfs-provisioner <pod> --tail=100
```

### 3. Analyze disk space
```bash
# Check which node the PVC is bound to
kubectl get pv | grep <pvc-name>
kubectl describe pv <pv-name> | grep "Node Affinity"

# Check node disk usage
kubectl debug node/<node-name> -it --image=ubuntu
chroot /host
df -h
du -sh /var/lib/rancher/k3s/storage/*  # k3s local-path
du -sh /var/lib/kubelet/pods/*  # general kubelet storage

# Check if migration output is consuming space
ls -lh /tmp/h2kvm-*
du -sh /tmp/h2kvm-*
```

### 4. Check for I/O bottlenecks
```bash
# Monitor I/O wait
iostat -x 5
iotop -o  # show processes with I/O

# Check disk health (SMART)
sudo smartctl -a /dev/sda
sudo smartctl -H /dev/sda  # health summary
```

## Resolution Steps

### Scenario A: PVC Stuck in Pending

**Root cause:** WaitForFirstConsumer binding mode, no storage provisioner, or insufficient disk space

#### 1. Diagnose binding issue
```bash
kubectl describe pvc <pvc-name> -n h2kvm-migration
# Look for: "waiting for first consumer", "no nodes available", "storage quota exceeded"
```

#### 2. For WaitForFirstConsumer storage class
```bash
# Create a consumer pod to trigger binding
kubectl run pvc-binder --rm -i --restart=Never --image=busybox \
  --overrides='{"spec":{"containers":[{"name":"bind","image":"busybox",
  "command":["sleep","10"],"volumeMounts":[{"name":"vol","mountPath":"/data"}]}],
  "volumes":[{"name":"vol","persistentVolumeClaim":{"claimName":"<pvc-name>"}}]}}' \
  -n h2kvm-migration

# Or annotate with target node (local-path specific)
kubectl annotate pvc <pvc-name> -n h2kvm-migration \
  volume.kubernetes.io/selected-node=<node-name>
```

#### 3. For missing provisioner
```bash
# Check if provisioner is running
kubectl get pods -n kube-system | grep provisioner

# Restart provisioner
kubectl rollout restart deployment local-path-provisioner -n kube-system

# Wait for provisioner to be ready
kubectl wait --for=condition=Available deployment/local-path-provisioner \
  -n kube-system --timeout=60s
```

#### 4. If quota exceeded
```bash
# Check resource quota
kubectl get resourcequota -n h2kvm-migration
kubectl describe resourcequota -n h2kvm-migration

# Increase quota or clean up old PVCs
kubectl delete pvc <old-pvc> -n h2kvm-migration
```

### Scenario B: Disk Full on Node

**Root cause:** Migration output consuming all available space, or excessive logging

#### 1. Identify space hogs
```bash
# Find large directories on node
kubectl debug node/<node-name> -it --image=ubuntu
chroot /host
du -sh /* | sort -h | tail -10
du -sh /var/lib/rancher/k3s/storage/* | sort -h | tail -10
du -sh /tmp/h2kvm-* | sort -h | tail -10
```

#### 2. Clean up migration artifacts
```bash
# Delete completed migration PVCs
kubectl get pvc -n h2kvm-migration
kubectl delete pvc <completed-pvc> -n h2kvm-migration

# Delete completed jobs (keeps logs for 1 hour by default)
kubectl delete jobs --field-selector=status.successful=1 -n h2kvm-migration

# Clean up failed migrations
kubectl delete hc --all -n h2kvm-migration  # if no active migrations
```

#### 3. Clean up Docker/containerd cache
```bash
# On the node
kubectl debug node/<node-name> -it --image=ubuntu
chroot /host

# Clean Docker
docker system prune -a -f --volumes

# Or clean containerd (k3s)
k3s crictl rmi --prune
rm -rf /var/lib/rancher/k3s/agent/containerd/io.containerd.snapshotter.*/snapshots/*

# Clean old logs
journalctl --vacuum-time=7d
find /var/log -name "*.log" -mtime +7 -delete
```

#### 4. Clean up temporary files
```bash
# On the node
rm -rf /tmp/h2kvm-*
rm -rf /var/tmp/h2kvm-*

# Or from kubectl
kubectl debug node/<node-name> -it --image=ubuntu -- \
  chroot /host sh -c "rm -rf /tmp/h2kvm-*"
```

#### 5. Expand disk (if applicable)
```bash
# For cloud VMs, resize disk
# AWS: modify EBS volume, then extend filesystem
# GCP: resize persistent disk, then extend filesystem

# Extend filesystem (after disk resize)
sudo growpart /dev/sda 1
sudo resize2fs /dev/sda1  # ext4
# Or for XFS:
sudo xfs_growfs /
```

### Scenario C: Storage Provisioner Crashed

**Root cause:** Provisioner OOM, configuration error, or storage backend unreachable

#### 1. Check provisioner status
```bash
kubectl get pods -n kube-system -l app=local-path-provisioner
kubectl describe pod -n kube-system -l app=local-path-provisioner
kubectl logs -n kube-system -l app=local-path-provisioner --tail=100
```

#### 2. Restart provisioner
```bash
# local-path-provisioner
kubectl rollout restart deployment local-path-provisioner -n kube-system

# Rook/Ceph
kubectl rollout restart deployment rook-ceph-operator -n rook-ceph

# Wait for ready
kubectl wait --for=condition=Available deployment/local-path-provisioner \
  -n kube-system --timeout=120s
```

#### 3. If restart fails, check configuration
```bash
# Check ConfigMap
kubectl get configmap local-path-config -n kube-system -o yaml

# Verify storage path exists on nodes
kubectl debug node/<node-name> -it --image=ubuntu
chroot /host
ls -ld /var/lib/rancher/k3s/storage  # should exist and be writable
```

### Scenario D: Network Storage (NFS/iSCSI) Unreachable

**Root cause:** Network partition, storage server down, firewall blocking access

#### 1. Test connectivity from worker node
```bash
kubectl debug node/<node-name> -it --image=ubuntu
chroot /host

# NFS
showmount -e <nfs-server>
mount -t nfs <nfs-server>:/export /mnt/test
ls /mnt/test
umount /mnt/test

# iSCSI
iscsiadm -m discovery -t st -p <iscsi-server>
```

#### 2. Check network path
```bash
ping <storage-server>
traceroute <storage-server>
nc -zv <storage-server> 2049  # NFS
nc -zv <storage-server> 3260  # iSCSI
```

#### 3. Check firewall/security groups
```bash
# On storage server
sudo firewall-cmd --list-all
sudo iptables -L -n

# Verify NFS exports
sudo exportfs -v
```

#### 4. Remount storage (if stale)
```bash
# Force remount NFS volumes
kubectl delete pod <pod-with-nfs-mount> -n h2kvm-migration  # recreates pod
```

### Scenario E: I/O Errors or Filesystem Corruption

**Root cause:** Disk hardware failure, filesystem corruption, read-only remount

#### 1. Check kernel logs for I/O errors
```bash
dmesg | grep -iE "i/o error|ext4|xfs|ata|scsi"
journalctl -k --since "1 hour ago" | grep -iE "error|fail"
```

#### 2. Check filesystem status
```bash
mount | grep "ro,"  # check for read-only mounts

# Run filesystem check (requires unmount)
sudo umount /dev/sda1
sudo fsck -y /dev/sda1
sudo mount /dev/sda1 /mnt
```

#### 3. Check SMART health
```bash
sudo smartctl -H /dev/sda
sudo smartctl -a /dev/sda | grep -E "Reallocated|Pending|Uncorrectable"
```

#### 4. If disk failing, migrate data
```bash
# Cordon node (prevent new pods)
kubectl cordon <node-name>

# Drain node (move pods to other nodes)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# Replace disk (hardware intervention)
# After replacement, uncordon
kubectl uncordon <node-name>
```

### Scenario F: CLI Migration with Disk Full

**Root cause:** Output directory on full filesystem

#### 1. Check available space
```bash
df -h <output-dir>
du -sh <output-dir>
```

#### 2. Clean up or change output location
```bash
# Clean up old migrations
rm -rf /tmp/h2kvm-old-*
rm -rf <output-dir>/checkpoints/*  # if resuming not needed

# Or use different output directory with more space
h2kvmctl --cmd local \
  --vmdk /path/to/source.vmdk \
  --output-dir /mnt/large-disk/h2kvm-output \
  --output-format qcow2
```

## Prevention / Monitoring

### Disk Space Monitoring
```bash
# Set up Prometheus alerts for disk usage
# Alert when >80% full
# Example PromQL: node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.2

# Monitor PVC usage
kubectl get pvc -A -o custom-columns=\
NAME:.metadata.name,\
NAMESPACE:.metadata.namespace,\
CAPACITY:.status.capacity.storage,\
USED:.status.phase
```

### Resource Quotas
```yaml
# Set quotas per namespace
apiVersion: v1
kind: ResourceQuota
metadata:
  name: h2kvm-quota
  namespace: h2kvm-migration
spec:
  hard:
    requests.storage: "500Gi"
    persistentvolumeclaims: "10"
```

### Automated Cleanup
```bash
# Deploy PVC cleanup CronJob (example)
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: pvc-cleanup
  namespace: h2kvm-migration
spec:
  schedule: "0 2 * * *"  # daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: pvc-cleaner
          containers:
          - name: cleanup
            image: bitnami/kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              # Delete PVCs older than 7 days from completed migrations
              kubectl get pvc -n h2kvm-migration -o json | \
              jq -r '.items[] | select(.metadata.creationTimestamp | fromdateiso8601 < now - 604800) | .metadata.name' | \
              xargs -I {} kubectl delete pvc {} -n h2kvm-migration
          restartPolicy: OnFailure
EOF
```

### Pre-Flight Checks
```bash
# Check disk space before migration
./scripts/doctor.sh

# Add to HyperConversion CR validation webhook
# Reject if insufficient storage available
```

### Storage Class Best Practices
```yaml
# Use WaitForFirstConsumer for better node placement
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path-wait
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
```

### Health Checks
```bash
# Run regular health checks
./scripts/health-check.sh

# Check storage provisioner health
kubectl get pods -n kube-system -l app=local-path-provisioner
kubectl logs -n kube-system -l app=local-path-provisioner --tail=20
```

## Escalation Path

**Escalate immediately if:**
- Disk hardware failure (SMART errors, I/O errors)
- Filesystem corruption with data loss
- Network storage backend completely unavailable
- Multiple nodes experiencing storage issues (cluster-wide problem)

**Escalation steps:**
1. Collect debug bundle: `./scripts/collect-debug-bundle.sh`
2. Document storage backend type and failure symptoms
3. Save relevant logs:
   ```bash
   kubectl logs -n kube-system -l app=local-path-provisioner > provisioner.log
   dmesg > kernel.log
   df -h > disk-space.txt
   ```
4. Contact storage team (for network storage) or infrastructure team (for local disks)
5. If critical migration in progress: consider pausing and migrating to new node
6. For vendor-supported storage (Rook, NetApp, etc.): open support ticket with logs
