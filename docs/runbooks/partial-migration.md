# Partial Migration Recovery

## Scenario
Migration completed partially with one or more stages failing while others succeeded.

**Common partial states:**
- Disk converted to QCOW2 but offline fixes failed (fstab, grub, initramfs)
- Offline fixes completed but VM creation/deployment failed
- Multi-disk VM with some disks converted, others failed
- Libvirt domain XML generated but virsh define failed
- Kubernetes DataVolume created but VirtualMachine startup failed

## Symptoms / How to Detect

### Kubernetes Migrations
```bash
# Check HyperConversion phase (stuck in intermediate state)
kubectl get hc -A
# Look for: Converting, FixingBoot, CreatingVM (not progressing to Ready)

# Check job completion status
kubectl get jobs -n h2kvm-migration
# Look for: 0/1 completions (stuck), or multiple jobs with only some completed

# Check migration logs for errors
kubectl logs -n h2kvm-migration -l job-name=migration --tail=100 | grep -E "ERROR|WARN|Failed"

# Check DataVolume status
kubectl get dv -n h2kvm-migration
# Look for: Succeeded (DV ready) but VM not created

# Check VM status
kubectl get vm,vmi -n h2kvm-migration
# VM may be Created but VMI not Running
```

### CLI Migrations
```bash
# Check output directory for artifacts
ls -lh <output-dir>/
# Look for: *.qcow2 (conversion done), *.xml (domain XML), *.log (errors)

# Check migration log for stage completion
cat <output-dir>/migration.log | grep -E "Stage.*complete|Stage.*failed"

# Verify QCOW2 integrity
qemu-img check <output-dir>/converted.qcow2
qemu-img info <output-dir>/converted.qcow2

# Check for checkpoint files (multi-disk scenarios)
ls <output-dir>/checkpoints/
cat <output-dir>/checkpoints/disk0.json
```

### Specific Failure Detection
```bash
# Conversion succeeded, offline fixes failed
grep "Offline fixes failed" <output-dir>/migration.log
grep "guestfs error" <output-dir>/migration.log

# Offline fixes succeeded, deployment failed
grep "virsh define failed" <output-dir>/migration.log
grep "Failed to create VM" <output-dir>/migration.log

# Multi-disk: identify which disks completed
grep "Converting disk" <output-dir>/migration.log
ls <output-dir>/*.qcow2
```

## Root Cause Analysis Steps

### 1. Identify completed stages
```bash
# Kubernetes: check HyperConversion status
kubectl describe hc <name> -n h2kvm-migration | grep -A30 status
# Look for: lastCompletedStage, failedStage, errorMessage

# CLI: parse migration log
grep "Stage:" <output-dir>/migration.log
# Stages: Download, Convert, OfflineFixes, EmitDomainXML, Deploy
```

### 2. Determine failure point
```bash
# Check last successful operation
tail -200 <output-dir>/migration.log | grep -E "✓|SUCCESS|complete"

# Check first error
grep -A10 "ERROR" <output-dir>/migration.log | head -20

# For offline fixes failures
grep -A20 "guestfs" <output-dir>/migration.log
```

### 3. Assess usability of partial output
```bash
# Verify QCOW2 is bootable (even without fixes)
qemu-img info <output-dir>/converted.qcow2
file <output-dir>/converted.qcow2

# Check if libvirt XML exists
cat <output-dir>/domain.xml

# Test boot (dry-run, don't persist)
virsh create --transient <output-dir>/domain.xml
# Or with QEMU directly
qemu-system-x86_64 -hda <output-dir>/converted.qcow2 -m 2G -nographic
```

## Resolution Steps

### Scenario A: QCOW2 Exists, Offline Fixes Failed

**Root cause:** libguestfs errors (missing tools, LVM detection, fstab parsing)

#### Option 1: Boot VM and fix manually
```bash
# Kubernetes: Create VM with existing PVC
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: manual-fix-vm
  namespace: h2kvm-migration
spec:
  runStrategy: Always
  template:
    spec:
      domain:
        cpu: {cores: 2}
        resources: {requests: {memory: 4Gi}}
        devices:
          disks:
          - name: disk0
            disk: {bus: virtio}
          - name: cloudinit
            disk: {bus: virtio}
      volumes:
      - name: disk0
        persistentVolumeClaim:
          claimName: <output-pvc-name>
      - name: cloudinit
        cloudInitNoCloud:
          userData: |
            #cloud-config
            password: temp123
            chpasswd: {expire: False}
            ssh_pwauth: True
EOF

# Wait for VM to start
kubectl wait --for=condition=Ready vmi/manual-fix-vm -n h2kvm-migration --timeout=300s

# Access console
virtctl console manual-fix-vm -n h2kvm-migration

# Inside VM, fix issues manually:
# 1. Fix fstab (remove VMware-specific mounts, use UUID)
sudo vi /etc/fstab
# Replace /dev/sda1 with UUID=... (get from blkid)

# 2. Regenerate initramfs
sudo dracut --force --regenerate-all

# 3. Fix GRUB
sudo grub2-mkconfig -o /boot/grub2/grub.cfg

# 4. Enable serial console
sudo grubby --update-kernel=ALL --args="console=ttyS0,115200n8"

# 5. Reboot to test
sudo reboot
```

#### Option 2: Re-run offline fixes only
```bash
# CLI: run h2kvmctl with only fix flags on existing QCOW2
h2kvmctl --cmd local \
  --vmdk <output-dir>/converted.qcow2 \
  --output-dir <output-dir>/fixes-retry \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --serial-console \
  --verbose 2

# This will:
# - Mount QCOW2 with guestfs
# - Fix fstab (UUID-based, remove invalid mounts)
# - Regenerate initramfs with virtio drivers
# - Enable serial console
# - Update GRUB config
```

#### Option 3: Skip offline fixes, deploy as-is
```bash
# If VM is known to be compatible (recent Ubuntu/RHEL)
# Deploy without offline fixes, rely on cloud-init for adaptation

# Kubernetes: use original QCOW2 in PVC
kubectl apply -f <vm-manifest.yaml>

# CLI: import to libvirt
virsh define <output-dir>/domain.xml
virsh start <vm-name>
```

### Scenario B: Offline Fixes Succeeded, VM Creation Failed

**Root cause:** virsh connection issues, libvirt permissions, resource constraints

#### 1. Verify QCOW2 is ready
```bash
qemu-img check <output-dir>/fixed.qcow2
qemu-img info <output-dir>/fixed.qcow2

# Check if domain XML exists
cat <output-dir>/domain.xml
```

#### 2. Manually create VM
```bash
# Kubernetes: Create VirtualMachine resource
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: recovered-vm
  namespace: h2kvm-migration
spec:
  runStrategy: Always
  template:
    metadata:
      labels:
        kubevirt.io/vm: recovered-vm
    spec:
      domain:
        cpu: {cores: 4}
        resources:
          requests:
            memory: 8Gi
        devices:
          disks:
          - name: disk0
            disk: {bus: virtio}
          interfaces:
          - name: default
            masquerade: {}
      networks:
      - name: default
        pod: {}
      volumes:
      - name: disk0
        persistentVolumeClaim:
          claimName: <output-pvc-name>
EOF

# Wait for VMI to start
kubectl wait --for=condition=Ready vmi/recovered-vm -n h2kvm-migration --timeout=600s

# Get IP and test
kubectl get vmi recovered-vm -n h2kvm-migration -o yaml | grep -A5 interfaces
```

```bash
# CLI: import to libvirt manually
virsh define <output-dir>/domain.xml
virsh start <vm-name>

# If virsh define fails, check permissions
sudo chown root:root <output-dir>/domain.xml
sudo chmod 644 <output-dir>/domain.xml

# Check libvirt connection
virsh uri
virsh list --all

# If resource issues, edit XML to reduce CPU/RAM
virt-xml <vm-name> --edit --vcpus 2
virt-xml <vm-name> --edit --memory 4096
```

### Scenario C: Multi-Disk Migration with Some Disks Failed

**Root cause:** Network timeout, disk corruption, space constraints

#### 1. Identify completed disks
```bash
# Check checkpoint state
cat <output-dir>/checkpoints/migration-state.json
# Or individual disk checkpoints
ls <output-dir>/checkpoints/disk*.json

# List converted disks
ls -lh <output-dir>/*.qcow2
```

#### 2. Resume migration (auto-skips completed disks)
```bash
# Kubernetes: Delete and reapply HyperConversion
# (operator detects existing PVCs, skips completed disks)
kubectl delete hc <name> -n h2kvm-migration
kubectl apply -f <hyperconversion.yaml>

# CLI: Re-run same command (checkpoint/resume)
h2kvmctl --cmd local \
  --vmdk /path/to/multi-disk.vmdk \
  --output-dir <same-output-dir> \
  --enable-recovery

# h2kvmctl will:
# - Read checkpoint/migration-state.json
# - Skip disks with status: "completed"
# - Resume failed disks from last checkpoint
```

#### 3. Manual conversion of failed disks
```bash
# If auto-resume fails, convert failed disks manually
qemu-img convert -f vmdk -O qcow2 \
  /path/to/failed-disk.vmdk \
  <output-dir>/failed-disk.qcow2

# Then attach to existing VM
virsh attach-disk <vm-name> \
  <output-dir>/failed-disk.qcow2 \
  vdb --targetbus virtio --persistent
```

### Scenario D: Libvirt XML Generated, virsh Define Failed

**Root cause:** Libvirt service down, XML validation errors, resource conflicts

#### 1. Diagnose virsh issue
```bash
# Check libvirt service
sudo systemctl status libvirtd
sudo journalctl -u libvirtd --since "1 hour ago"

# Validate XML
virt-xml-validate <output-dir>/domain.xml domain

# Check for name conflicts
virsh list --all | grep <vm-name>
```

#### 2. Fix and retry
```bash
# Fix XML validation errors
# Common issues: invalid CPU model, missing network, incorrect disk path
vi <output-dir>/domain.xml

# Fix disk path (use absolute path)
sed -i "s|<source file='converted.qcow2'|<source file='$(pwd)/<output-dir>/converted.qcow2'|" <output-dir>/domain.xml

# Fix CPU model (use host-passthrough if unsure)
sed -i "s|<cpu mode='custom'.*|<cpu mode='host-passthrough'/>|" <output-dir>/domain.xml

# Retry define
virsh define <output-dir>/domain.xml

# If name conflict
virsh undefine <vm-name>
virsh define <output-dir>/domain.xml
```

### Scenario E: Kubernetes DataVolume Ready, VirtualMachine Failed to Start

**Root cause:** Insufficient resources, image pull issues, KubeVirt component down

#### 1. Check VMI status
```bash
kubectl get vmi -n h2kvm-migration
kubectl describe vmi <name> -n h2kvm-migration | grep -A20 Events
# Look for: Scheduling failures, resource constraints
```

#### 2. Check node resources
```bash
kubectl top nodes
kubectl describe nodes | grep -A10 "Allocated resources"
```

#### 3. Fix and restart VM
```bash
# Delete failed VMI
kubectl delete vmi <name> -n h2kvm-migration

# Edit VM resource requests
kubectl edit vm <name> -n h2kvm-migration
# Reduce: cpu: 2, memory: 4Gi

# Restart VM
virtctl start <name> -n h2kvm-migration
```

## Prevention / Monitoring

### Enable Checkpointing
```bash
# CLI migrations with auto-checkpoint
h2kvmctl --enable-recovery --checkpoint-interval 300  # every 5 min
```

### Staged Validation
```bash
# Add validation after each stage
h2kvmctl --validate-after-convert --validate-after-fixes

# Or use health check
h2kvmctl --health-check
```

### Pre-Flight Checks
```bash
# Run doctor.sh before migration
./scripts/doctor.sh
# Validates: KVM, qemu-img, libvirt, disk space, permissions

# Check libvirt connectivity
virsh list --all

# Check Kubernetes resources
kubectl top nodes
kubectl get sc  # ensure storage class exists
```

### Monitoring Phase Transitions
```bash
# Watch HyperConversion progress
kubectl get hc -A --watch

# Alert on stuck phases (>30 min in same phase)
# Prometheus alert example:
# - alert: MigrationStuck
#   expr: time() - h2kvm_phase_timestamp > 1800
```

### Logging
```bash
# Enable verbose logging
h2kvmctl --verbose 2  # CLI

# Kubernetes: increase operator log level
kubectl set env deployment/hyperconversion-operator -n h2kvm-system LOG_LEVEL=debug
```

## Escalation Path

**Escalate if:**
- Offline fixes fail repeatedly (possible guestfs bug or OS incompatibility)
- VM boots but critical services don't start (data corruption)
- Multi-disk migration consistently fails on same disk
- libvirt/KubeVirt errors not in documentation

**Escalation steps:**
1. Collect debug bundle: `./scripts/collect-debug-bundle.sh`
2. Save migration artifacts:
   ```bash
   tar czf migration-debug.tar.gz <output-dir>/ /tmp/h2kvm-*/
   ```
3. Document completed vs failed stages
4. Check for known issues: https://github.com/ssahani/h2kvm/issues
5. Contact platform team with debug bundle and migration log
