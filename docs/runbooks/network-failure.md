# Network Failure During Migration

## Scenario
Network connectivity lost between migration worker and source systems during active transfer.

**Common causes:**
- vSphere/ESXi host network partition
- HTTP/NFS server unreachable
- Firewall rule changes blocking HTTPS (443) or NFS (2049)
- DNS resolution failures
- Network switch/router failures
- Bandwidth throttling or QoS policy changes

## Symptoms / How to Detect

### Kubernetes Migrations
```bash
# Check pod events for network errors
kubectl describe pod -n h2kvm-migration -l job-name=migration | grep -A10 Events
# Look for: "connection refused", "timeout", "connection reset"

# Check CDI DataVolume import status
kubectl get dv -A
kubectl get dv -n h2kvm-migration -o yaml | grep -A5 "phase:"
# Look for: ImportInProgress (stuck), Failed

# Check operator logs for timeout errors
kubectl logs -n h2kvm-system -l control-plane=controller-manager --tail=50 | grep -iE "timeout|connection|network"

# Check CDI importer logs
kubectl logs -n h2kvm-migration -l app=containerized-data-importer | grep -E "ERROR|WARN"
```

### CLI Migrations (vSphere/govc)
```bash
# Check govc connectivity
export GOVC_URL=https://vcenter.example.com/sdk
export GOVC_USERNAME=administrator@vsphere.local
export GOVC_PASSWORD=<password>
export GOVC_INSECURE=1
govc ls  # test connection

# Check for timeout errors in logs
grep -i "timeout\|connection" /tmp/h2kvm-*/migration.log

# Test ESXi host network reachability
ping <esxi-host>
curl -k https://<esxi-host>  # should return HTML

# Check NFS mount (if using NFS datastore)
showmount -e <nfs-server>
mount | grep nfs
```

### General Network Tests
```bash
# DNS resolution
nslookup vcenter.example.com
dig vcenter.example.com

# Port connectivity
nc -zv vcenter.example.com 443
telnet vcenter.example.com 443

# Firewall/routing
traceroute vcenter.example.com
mtr -r vcenter.example.com  # detailed path analysis
```

## Root Cause Analysis Steps

### 1. Identify failure point
```bash
# Check when the failure occurred
kubectl get events -n h2kvm-migration --sort-by=.lastTimestamp | tail -20

# Check HyperConversion progress before failure
kubectl describe hc <name> -n h2kvm-migration | grep -A20 status

# For CLI migrations, check progress in logs
tail -100 /tmp/h2kvm-*/migration.log | grep PROGRESS
```

### 2. Determine network path
```bash
# Identify source system
kubectl get hc <name> -n h2kvm-migration -o yaml | grep -E "sourceVmdk|vsphereUrl"

# Test network path from worker pod
kubectl exec -n h2kvm-migration <pod> -- curl -k https://vcenter.example.com
kubectl exec -n h2kvm-migration <pod> -- nc -zv <esxi-host> 902  # HTTPS datastore access
```

### 3. Check for partial download
```bash
# Kubernetes: check PVC size
kubectl get pvc -n h2kvm-migration -o yaml | grep storage

# CLI: check downloaded size
ls -lh /tmp/h2kvm-*/
du -sh /tmp/h2kvm-*/*.vmdk

# Compare with expected size (from vSphere)
govc vm.info -json <vm-name> | jq '.VirtualMachines[].Config.Hardware.Device[] | select(.Backing.FileName) | .Backing.FileName, .CapacityInBytes'
```

### 4. Check network stability
```bash
# Monitor packet loss
ping -c 100 vcenter.example.com | grep loss

# Check bandwidth
iperf3 -c <target-host>  # if iperf3 server available

# Check firewall logs (if accessible)
sudo journalctl -u firewalld --since "1 hour ago"
```

## Resolution Steps

### Scenario A: vSphere Export Failure (govc)

#### 1. Verify vSphere connectivity
```bash
# Test govc connection
govc about
govc version

# List VMs to confirm access
govc ls /Datacenter/vm

# Check VM details
govc vm.info <vm-name>
```

#### 2. Retry with increased timeouts
```bash
# CLI migration with extended retries
h2kvmctl --cmd vsphere \
  --vs-url https://vcenter.example.com/sdk \
  --vs-username administrator@vsphere.local \
  --vs-password <password> \
  --vs-datacenter Datacenter \
  --vs-vm-name <vm-name> \
  --vs-action export_vm \
  --vs-export-retries 5 \
  --vs-export-timeout 3600 \
  --output-dir /tmp/h2kvm-retry

# Or edit Kubernetes HyperConversion CR
kubectl edit hc <name> -n h2kvm-migration
# Add: exportRetries: 5, exportTimeout: 3600
```

#### 3. Manual export if automation fails
```bash
# Export VM manually via govc
govc export.ovf -vm <vm-name> /tmp/manual-export/

# Then convert locally
h2kvmctl --cmd local \
  --vmdk /tmp/manual-export/<vm-name>-disk-0.vmdk \
  --output-dir /tmp/h2kvm-converted \
  --output-format qcow2
```

### Scenario B: CDI HTTP Import Failure

#### 1. Check DataVolume status
```bash
kubectl get dv -n h2kvm-migration
kubectl describe dv <name> -n h2kvm-migration
```

#### 2. If stuck in ImportInProgress
```bash
# CDI has built-in retry logic (default: 3 retries)
# Wait for automatic retry (check logs)
kubectl logs -n h2kvm-migration -l app=containerized-data-importer --follow

# Check retry count
kubectl get dv <name> -n h2kvm-migration -o yaml | grep -A5 restartCount
```

#### 3. If Failed permanently
```bash
# Delete and recreate DataVolume
kubectl delete dv <name> -n h2kvm-migration

# Delete and reapply HyperConversion CR
kubectl delete hc <name> -n h2kvm-migration
kubectl apply -f <hyperconversion.yaml>
```

### Scenario C: In-Cluster Copy Job (Two-Stage Migration)

#### 1. Check copy stage completion
```bash
# If copy-vmdk job succeeded, VMDK is local (no network needed)
kubectl get job copy-vmdk -n h2kvm-migration

# Check PVC with VMDK
kubectl get pvc vmdk-input -n h2kvm-migration
kubectl exec -n h2kvm-migration <pod> -- ls -lh /mnt/vmdk-input/
```

#### 2. Resume migration from local PVC
```bash
# If copy succeeded, migration job reads locally
kubectl delete job migration -n h2kvm-migration  # delete failed job
kubectl apply -f <migration-job.yaml>  # retry

# Migration will use local PVC, no network needed
```

### Scenario D: NFS Datastore Access

#### 1. Check NFS connectivity
```bash
# Test NFS mount from worker node
showmount -e <nfs-server>

# Mount manually to test
sudo mkdir -p /mnt/test-nfs
sudo mount -t nfs <nfs-server>:/export/path /mnt/test-nfs
ls -la /mnt/test-nfs
sudo umount /mnt/test-nfs
```

#### 2. Update NFS client settings
```bash
# If using autofs, reload
sudo systemctl reload autofs

# If using static mount, remount
sudo mount -a
```

## Prevention / Monitoring

### Pre-Migration Network Validation
```bash
# Add to pre-flight checks
./scripts/doctor.sh  # validates basic connectivity

# Test vSphere connectivity before migration
govc about
govc ls

# Test HTTP source availability
curl -I <http-source-url>

# Verify firewall rules allow traffic
sudo firewall-cmd --list-all
sudo iptables -L -n
```

### Retry Configuration
```yaml
# HyperConversion CR with retry settings
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: migration-with-retries
spec:
  sourceVmdk: https://source/vm.vmdk
  exportRetries: 5        # retry up to 5 times
  exportTimeout: 7200     # 2 hour timeout per attempt
  exportBackoffSeconds: 60  # 60s between retries
```

### CLI Retry Flags
```bash
# vSphere exports with retry
h2kvmctl --cmd vsphere \
  --vs-export-retries 5 \
  --vs-export-timeout 7200 \
  --vs-export-backoff 60 \
  ...
```

### Network Monitoring
```bash
# Monitor CDI importer progress
kubectl logs -n h2kvm-migration -l app=containerized-data-importer --follow | grep PROGRESS

# Monitor vSphere export progress (CLI)
tail -f /tmp/h2kvm-*/migration.log | grep -E "PROGRESS|download"

# Set up network alerts (Prometheus example)
# Alert if migration pod has network errors >3 in 5 minutes
```

### Pre-Copy Strategy
```bash
# For large VMs, pre-copy to local storage first
# 1. Export to HTTP server in same datacenter as cluster
govc export.ovf -vm <vm-name> /var/www/html/exports/

# 2. Copy to PVC via CDI
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: vmdk-local-copy
spec:
  source:
    http:
      url: "http://local-server/exports/vm-disk-0.vmdk"
  pvc:
    accessModes: [ReadWriteOnce]
    resources:
      requests:
        storage: 100Gi
EOF

# 3. Wait for copy to complete
kubectl wait --for=condition=Ready dv/vmdk-local-copy --timeout=3600s

# 4. Run migration from local PVC (no network needed)
h2kvmctl --cmd local --vmdk /mnt/vmdk-local-copy/disk.vmdk ...
```

## Escalation Path

**Escalate if:**
- Network failure persists >1 hour
- vSphere admin access needed (check firewall, NSX rules)
- NFS server issues (requires storage team)
- Repeated failures despite retries (possible source corruption)

**Escalation steps:**
1. Document network path: source → firewall → cluster
2. Collect network traces: `tcpdump -i any -w /tmp/network.pcap host vcenter.example.com`
3. Collect debug bundle: `./scripts/collect-debug-bundle.sh`
4. Contact network team with source/destination IPs and ports
5. If data transfer critical: consider offline migration (ship disk to datacenter)
