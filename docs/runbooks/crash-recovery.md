# Crash Recovery

## Scenario
Worker pod crashes, node reboots, or h2kvmctl process terminates unexpectedly during an active migration.

**Common causes:**
- OOM killer terminates pod/process
- Node hardware failure or kernel panic
- Power loss or network partition
- Manual termination (kill -9, pod deletion)

## Symptoms / How to Detect

### Kubernetes Deployments
```bash
# Check for failed or crashlooping pods
kubectl get pods -n hyper2kvm-migration --field-selector=status.phase=Failed
kubectl get pods -n hyper2kvm-migration | grep -E 'CrashLoopBackOff|Error|OOMKilled'

# Check for stuck jobs (running >4 hours)
kubectl get jobs -n hyper2kvm-migration | grep -v Complete

# Check HyperConversion status (stuck in Converting or CreatingVM)
kubectl get hc -A
kubectl describe hc <name> -n hyper2kvm-migration | grep -A10 Status

# Check pod events for crash details
kubectl describe pod -n hyper2kvm-migration -l job-name=migration | grep -A10 Events
```

### CLI Migrations
```bash
# Check for orphaned processes
ps aux | grep h2kvmctl
ps aux | grep qemu-nbd

# Check for orphaned NBD devices (indicates unclean shutdown)
ls -la /sys/block/nbd*/pid 2>/dev/null
lsof /dev/nbd*

# Check for stuck device-mapper devices
sudo dmsetup ls
sudo vgs  # orphaned LVM volume groups

# Look for crash logs
journalctl -u h2kvmctl --since "1 hour ago"
dmesg | grep -i "out of memory"
```

## Root Cause Analysis Steps

### 1. Determine crash type
```bash
# Check if OOM killed
kubectl describe pod <pod> -n hyper2kvm-migration | grep "OOMKilled"
dmesg | grep -i "killed process"

# Check node status (was it rebooted?)
kubectl get events --all-namespaces | grep -i "node.*not.*ready"
uptime  # check system uptime

# Check for kernel panics
journalctl -k | grep -i panic

# Check disk full errors
kubectl logs <pod> -n hyper2kvm-migration | grep -i "no space left"
df -h
```

### 2. Identify migration stage at crash
```bash
# Check migration logs for last operation
kubectl logs <pod> -n hyper2kvm-migration --tail=100 | grep -E "PROGRESS|Converting|Fixing"

# For CLI migrations, check output directory
ls -lh /tmp/hyper2kvm-*/
cat /tmp/hyper2kvm-*/migration.log | tail -50
```

### 3. Check for data corruption
```bash
# Verify partial QCOW2 integrity
qemu-img check <output-dir>/converted.qcow2
qemu-img info <output-dir>/converted.qcow2

# Check for incomplete writes
ls -lh <output-dir>/  # compare sizes with expected
```

## Resolution Steps

### Scenario A: Kubernetes Migration Crash

#### 1. Assess current state
```bash
# Check if PVC with partial output exists
kubectl get pvc -n hyper2kvm-migration

# Examine HyperConversion CR status
kubectl get hc <name> -n hyper2kvm-migration -o yaml | grep -A20 status
```

#### 2. Clean up orphaned resources
```bash
# Delete failed job (keeps PVC)
kubectl delete job migration -n hyper2kvm-migration

# If pod is stuck terminating
kubectl delete pod <pod> -n hyper2kvm-migration --force --grace-period=0
```

#### 3. Resume migration
```bash
# Option 1: Reapply HyperConversion CR (operator reconciles)
kubectl apply -f <hyperconversion.yaml>

# Option 2: Delete and recreate (if reconciliation fails)
kubectl delete hc <name> -n hyper2kvm-migration
kubectl apply -f <hyperconversion.yaml>
```

#### 4. If migration cannot resume (data corrupted)
```bash
# Clean up all resources
kubectl delete hc <name> -n hyper2kvm-migration
kubectl delete job --all -n hyper2kvm-migration
kubectl delete pvc qcow2-output -n hyper2kvm-migration

# Start fresh migration
kubectl apply -f <hyperconversion.yaml>
```

### Scenario B: CLI Migration Crash

#### 1. Clean up orphaned resources
```bash
# Disconnect NBD devices
sudo qemu-nbd --disconnect /dev/nbd0
sudo qemu-nbd --disconnect /dev/nbd1
# Or disconnect all
for dev in /dev/nbd*; do sudo qemu-nbd --disconnect "$dev" 2>/dev/null; done

# Deactivate orphaned LVM volume groups
sudo vgchange -an

# Remove orphaned device-mapper entries
sudo dmsetup remove_all

# Kill orphaned processes
sudo pkill -f qemu-nbd
sudo pkill -f h2kvmctl
```

#### 2. Verify partial output
```bash
# Check what was completed
ls -lh <output-dir>/
qemu-img info <output-dir>/converted.qcow2

# Check for checkpoint state (if enabled)
ls <output-dir>/checkpoints/
cat <output-dir>/checkpoints/disk0.json  # shows completed chunks
```

#### 3. Resume migration
```bash
# If checkpoints exist, re-run same command (auto-resumes)
h2kvmctl --cmd local \
  --vmdk /path/to/source.vmdk \
  --output-dir <same-output-dir> \
  --output-format qcow2 \
  --enable-recovery

# If no checkpoints, start fresh with different output dir
h2kvmctl --cmd local \
  --vmdk /path/to/source.vmdk \
  --output-dir /tmp/hyper2kvm-retry \
  --output-format qcow2
```

### Scenario C: Node Crash (Kubernetes)

#### 1. Check node status
```bash
kubectl get nodes
kubectl describe node <node-name> | grep -A10 Conditions

# Check if node came back online
kubectl get events --all-namespaces | grep <node-name>
```

#### 2. Verify NBD cleanup (on recovered node)
```bash
# SSH to node or use kubectl debug
kubectl debug node/<node-name> -it --image=busybox

# Inside debug pod
chroot /host
ls /sys/block/nbd*/pid  # should be empty
dmsetup ls  # should show no orphaned devices
```

#### 3. Resume migration
```bash
# Check if job rescheduled automatically
kubectl get pods -n hyper2kvm-migration -o wide

# If not, delete and reapply HyperConversion
kubectl delete hc <name> -n hyper2kvm-migration
kubectl apply -f <hyperconversion.yaml>
```

## Prevention / Monitoring

### Resource Limits
```yaml
# Set appropriate memory limits in operator/config/manager/deployment.yaml
resources:
  requests:
    memory: 4Gi
    cpu: 2000m
  limits:
    memory: 8Gi
    cpu: 4000m
```

### Graceful Shutdown
```yaml
# Enable preStop hook for cleanup
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "qemu-nbd --disconnect /dev/nbd0; dmsetup remove_all"]

# Set long termination grace period
terminationGracePeriodSeconds: 7200  # 2 hours
```

### Monitoring
```bash
# Set up alerts for pod restarts
kubectl get events -n hyper2kvm-migration --watch | grep -E 'Killing|OOMKilled'

# Monitor node health
kubectl top nodes
kubectl describe nodes | grep -E 'MemoryPressure|DiskPressure'

# Enable checkpoint/recovery
h2kvmctl --enable-recovery --checkpoint-interval 300  # every 5 min
```

### Backups
```bash
# Backup operator state before maintenance
./scripts/collect-debug-bundle.sh /var/backups/hyper2kvm-state-$(date +%Y%m%d)

# Snapshot PVCs with partial migrations
kubectl get pvc -n hyper2kvm-migration -o yaml > pvc-backup.yaml
```

## Escalation Path

**Escalate immediately if:**
- Node crash caused by hardware failure (disk, memory)
- Data corruption detected in converted QCOW2
- Migration crashed 3+ times with same error
- Critical production VM stuck in half-migrated state

**Escalation steps:**
1. Collect debug bundle: `./scripts/collect-debug-bundle.sh`
2. Document crash timeline and symptoms
3. Contact on-call platform engineer (see README.md)
4. If data loss risk: engage storage team immediately
