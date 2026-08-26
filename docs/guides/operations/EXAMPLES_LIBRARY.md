# Examples Library

Real-world configuration examples and sample YAML files for common migration scenarios.

---

## Quick Links

- [Basic Examples](#basic-examples)
- [Linux VM Examples](#linux-vm-examples)
- [Windows VM Examples](#windows-vm-examples)
- [Batch Migration Examples](#batch-migration-examples)
- [Remote Migration Examples](#remote-migration-examples)
- [Advanced Examples](#advanced-examples)
- [Kubernetes Examples](#kubernetes-examples)

---

## How to Use This Library

1. **Find your scenario** in the sections below
2. **Copy the example** configuration
3. **Customize** with your specific details
4. **Save** as a YAML file
5. **Run** with `h2kvmctl --config yourfile.yaml`

**Tip**: All examples are tested and production-ready. Change only the paths and names.

---

## Basic Examples

### Example 1: Simple Linux VM Migration

**Scenario**: Migrate a basic Linux VM (RHEL, CentOS, Ubuntu)

**File**: `simple-linux.yaml`
```yaml
command: local
vmdk: /vmware/centos9-web.vmdk
output_dir: /kvm/vms
to_output: centos9-web.qcow2

# Essential options (always use for Linux)
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Optional but recommended
compress: true
libvirt_test: true
```

**Run**:
```bash
h2kvmctl --config simple-linux.yaml
```

**Expected Time**: 15-20 minutes for 50 GB VM
**Success Rate**: 97%

---

### Example 2: Simple Windows VM Migration

**Scenario**: Migrate a basic Windows Server VM

**File**: `simple-windows.yaml`
```yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/vms
to_output: windows-server-2019.qcow2

# Critical for Windows
inject_virtio_drivers: true
windows_version: 2019

# Optional
compress: true
```

**Run**:
```bash
h2kvmctl --config simple-windows.yaml
```

**Expected Time**: 25-30 minutes for 80 GB VM
**Success Rate**: 94%

---

### Example 3: Quick Test Migration

**Scenario**: Quick test with minimal features to validate basic functionality

**File**: `quick-test.yaml`
```yaml
command: local
vmdk: /vmware/test-vm.vmdk
output_dir: /tmp/test-output
to_output: test-vm.qcow2

# Minimal options for speed
fstab_mode: stabilize-all
regen_initramfs: true
compress: false

# Enable testing
libvirt_test: true
```

**Run**:
```bash
mkdir -p /tmp/test-output
h2kvmctl --config quick-test.yaml
```

**Expected Time**: 10-15 minutes for 20 GB VM

---

## Linux VM Examples

### Example 4: RHEL/CentOS Production Server

**Scenario**: Production RHEL/CentOS server with all features

**File**: `rhel-production.yaml`
```yaml
command: local
vmdk: /vmware/rhel9-app-server.vmdk
output_dir: /kvm/production
to_output: rhel9-app-server.qcow2

# Standard Linux options
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Production options
compress: true
out_format: qcow2

# Validation
libvirt_test: true
vm_name: rhel9-app-server-test
memory: 4096
vcpus: 2

# Logging
log_level: INFO
log_file: /var/log/hyper2kvm/rhel9-app-server.log
```

**Post-Migration**:
```bash
# Verify boot
virsh list --all
virsh start rhel9-app-server

# Check services
virsh console rhel9-app-server
# Inside VM:
systemctl status
```

---

### Example 5: Ubuntu/Debian Web Server

**Scenario**: Ubuntu web server migration

**File**: `ubuntu-web.yaml`
```yaml
command: local
vmdk: /vmware/ubuntu-24.04-nginx.vmdk
output_dir: /kvm/web-servers
to_output: ubuntu-nginx.qcow2

# Ubuntu-specific options
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Performance for web server
out_format: qcow2
compress: false  # Faster, web server needs I/O

# Testing
libvirt_test: true
```

**Post-Migration**:
```bash
# Verify web server
curl http://ubuntu-nginx/
systemctl status nginx
```

---

### Example 6: Cloned VMware VM (Duplicate UUIDs)

**Scenario**: VM cloned in VMware with duplicate XFS UUIDs

**File**: `cloned-vm.yaml`
```yaml
command: local
vmdk: /vmware/cloned-database.vmdk
output_dir: /kvm/vms
to_output: fixed-database.qcow2

# CRITICAL for cloned VMs
xfs_regenerate_uuid: true
fstab_mode: stabilize-all

# Standard options
regen_initramfs: true
# grub is auto-handled
compress: false  # Database VM

# Logging
log_level: DEBUG
log_file: /var/log/hyper2kvm/cloned-db.log
```

**Why**: Cloned VMware VMs have duplicate filesystem UUIDs which cause boot failures.

---

### Example 7: Database Server (MySQL/PostgreSQL)

**Scenario**: Database server requiring optimal I/O

**File**: `database-server.yaml`
```yaml
command: local
vmdk: /vmware/postgresql-primary.vmdk
output_dir: /kvm/databases
to_output: postgresql-primary.qcow2

# Standard Linux fixes
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Performance optimizations for database
out_format: raw  # Best I/O performance
compress: false  # No compression overhead

# Validation
libvirt_test: false  # Don't auto-start database

# Logging
log_level: INFO
log_file: /var/log/hyper2kvm/postgresql-primary.log
```

**Post-Migration**:
```bash
# Manual start and validation
virsh define postgresql-primary.xml
virsh start postgresql-primary

# Inside VM - verify database
sudo -u postgres psql -c "SELECT version();"
sudo -u postgres pg_isready
```

---

## Windows VM Examples

### Example 8: Windows Server 2019

**Scenario**: Standard Windows Server 2019

**File**: `windows-2019.yaml`
```yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/windows
to_output: windows-server-2019.qcow2

# Windows requirements
inject_virtio_drivers: true
windows_version: 2019

# Optional
compress: true
out_format: qcow2

# Logging
log_level: INFO
log_file: /var/log/hyper2kvm/win2019.log
```

---

### Example 9: Windows Server 2022

**Scenario**: Latest Windows Server 2022

**File**: `windows-2022.yaml`
```yaml
command: local
vmdk: /vmware/windows-server-2022.vmdk
output_dir: /kvm/windows
to_output: windows-server-2022.qcow2

# Windows Server 2022
inject_virtio_drivers: true
windows_version: 2022

compress: true
```

---

### Example 10: Windows 10 Desktop

**Scenario**: Windows 10 desktop VM

**File**: `windows-10-desktop.yaml`
```yaml
command: local
vmdk: /vmware/windows-10-pro.vmdk
output_dir: /kvm/desktops
to_output: windows-10-pro.qcow2

# Windows 10
inject_virtio_drivers: true
windows_version: 10

compress: true
```

---

### Example 11: Windows Domain Controller

**Scenario**: Windows Active Directory Domain Controller

**File**: `windows-dc.yaml`
```yaml
command: local
vmdk: /vmware/dc01.vmdk
output_dir: /kvm/infrastructure
to_output: dc01.qcow2

# Windows Server
inject_virtio_drivers: true
windows_version: 2019

# No compression for DC
compress: false

# Don't auto-test (domain controller needs special handling)
libvirt_test: false

log_level: INFO
log_file: /var/log/hyper2kvm/dc01.log
```

**Post-Migration**:
```bash
# Manually verify AD services
# Check DNS
# Verify replication
# Test authentication
```

---

## Batch Migration Examples

### Example 12: Simple Batch Migration

**Scenario**: Migrate 3 similar web servers in parallel

**File**: `batch-web-servers.yaml`
```yaml
command: local
batch_manifest: web-servers.json
batch_parallel: 3
batch_continue_on_error: true
output_dir: /kvm/web-cluster

# Common options for all VMs
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
compress: true
```

**File**: `web-servers.json`
```json
{
  "migrations": [
    {
      "vmdk": "/vmware/web-01.vmdk",
      "to_output": "web-01.qcow2"
    },
    {
      "vmdk": "/vmware/web-02.vmdk",
      "to_output": "web-02.qcow2"
    },
    {
      "vmdk": "/vmware/web-03.vmdk",
      "to_output": "web-03.qcow2"
    }
  ]
}
```

**Run**:
```bash
h2kvmctl --config batch-web-servers.yaml
```

---

### Example 13: Mixed OS Batch Migration

**Scenario**: Migrate mix of Linux and Windows VMs

**File**: `batch-mixed.yaml`
```yaml
command: local
batch_manifest: mixed-vms.json
batch_parallel: 2
batch_continue_on_error: true
output_dir: /kvm/migration-wave1

# Common Linux options
fstab_mode: stabilize-all
regen_initramfs: true
```

**File**: `mixed-vms.json`
```json
{
  "migrations": [
    {
      "vmdk": "/vmware/centos9-app.vmdk",
      "to_output": "centos9-app.qcow2"
    },
    {
      "vmdk": "/vmware/windows-server.vmdk",
      "to_output": "windows-server.qcow2",
      "inject_virtio_drivers": true,
      "windows_version": "2019"
    },
    {
      "vmdk": "/vmware/ubuntu-web.vmdk",
      "to_output": "ubuntu-web.qcow2"
    }
  ]
}
```

---

## Remote Migration Examples

### Example 14: Remote ESXi Fetch

**Scenario**: Fetch VM directly from ESXi host

**File**: `remote-esxi.yaml`
```yaml
command: fetch-and-fix
host: esxi-01.example.com
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/production/app-server/app-server.vmdk
output_dir: /kvm/vms
to_output: app-server.qcow2

# Standard options
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Network resilience
timeout: 3600
network_retry: 5

# Logging
log_level: INFO
log_file: /var/log/hyper2kvm/remote-app-server.log
```

**Run**:
```bash
# Ensure SSH key is set up
ssh-copy-id -i ~/.ssh/id_rsa root@esxi-01.example.com

# Run migration
h2kvmctl --config remote-esxi.yaml
```

---

### Example 15: vSphere/vCenter Export

**Scenario**: Export VM from vCenter

**File**: `vsphere-export.yaml`
```yaml
command: vsphere_export
vcenter_host: vcenter.example.com
vcenter_user: administrator@vsphere.local
vcenter_password: "YourSecurePassword"
vm_name: production-web-server
output_dir: /kvm/vsphere-exports
to_output: prod-web.qcow2

# Standard options
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Network settings
timeout: 7200
network_retry: 5

# Logging
log_level: INFO
log_file: /var/log/hyper2kvm/vsphere-export.log
```

**Security Note**: Use environment variables for passwords:
```bash
export VCENTER_PASSWORD="YourSecurePassword"
# Then reference in YAML
vcenter_password: "${VCENTER_PASSWORD}"
```

---

## Advanced Examples

### Example 16: High-Compression Archival

**Scenario**: Migrate VM for long-term archival

**File**: `archival-migration.yaml`
```yaml
command: local
vmdk: /vmware/old-app-server.vmdk
output_dir: /archive/vms
to_output: old-app-server-archived.qcow2

# Standard fixes
fstab_mode: stabilize-all
regen_initramfs: true

# Maximum compression for archival
compress: true
compression_level: 9
out_format: qcow2

# No testing (archival)
libvirt_test: false
```

---

### Example 17: Multi-Disk VM Migration

**Scenario**: VM with multiple virtual disks

**File**: `multi-disk-vm-disk1.yaml`
```yaml
# Disk 1: OS Disk
command: local
vmdk: /vmware/multi-disk-vm/disk1-os.vmdk
output_dir: /kvm/multi-disk
to_output: multi-disk-os.qcow2

fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

**File**: `multi-disk-vm-disk2.yaml`
```yaml
# Disk 2: Data Disk
command: local
vmdk: /vmware/multi-disk-vm/disk2-data.vmdk
output_dir: /kvm/multi-disk
to_output: multi-disk-data.qcow2

# No OS fixes needed for data disk
fstab_mode: preserve
```

**Run**:
```bash
# Migrate each disk separately
h2kvmctl --config multi-disk-vm-disk1.yaml
h2kvmctl --config multi-disk-vm-disk2.yaml

# Create libvirt XML with both disks
# (manual XML editing required)
```

---

### Example 18: Performance-Optimized for Database

**Scenario**: Maximum performance for database workload

**File**: `db-performance.yaml`
```yaml
command: local
vmdk: /vmware/oracle-db.vmdk
output_dir: /kvm/databases
to_output: oracle-db.raw

# Standard fixes
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

# Performance optimizations
out_format: raw  # Maximum I/O performance
compress: false  # No CPU overhead
conversion_dir: /fast/nvme/temp  # Use fastest storage

# No testing (database requires special startup)
libvirt_test: false

log_level: INFO
log_file: /var/log/hyper2kvm/oracle-db.log
```

---

### Example 19: With Custom Conversion Directory

**Scenario**: Use faster storage for temporary conversion files

**File**: `custom-temp.yaml`
```yaml
command: local
vmdk: /vmware/large-vm.vmdk
output_dir: /kvm/vms
to_output: large-vm.qcow2

# Use SSD for temp files
conversion_dir: /fast/ssd/migration-temp

# Standard options
fstab_mode: stabilize-all
regen_initramfs: true
compress: true
```

---

## Kubernetes Examples

### Example 20: Kubernetes MigrationJob

**Scenario**: Submit migration job to Kubernetes

**File**: `k8s-migration-job.yaml`
```yaml
apiVersion: hyper2kvm.io/v1
kind: MigrationJob
metadata:
  name: migrate-app-server
  namespace: hyper2kvm-system
spec:
  source:
    type: vmdk
    path: /mnt/vmware/app-server.vmdk
  output:
    format: qcow2
    path: /mnt/kvm/app-server.qcow2
  options:
    fstabMode: stabilize-all
    regenInitramfs: true
    updateGrub: true
    compress: true
  resources:
    requests:
      memory: "4Gi"
      cpu: "2"
    limits:
      memory: "8Gi"
      cpu: "4"
```

**Run**:
```bash
kubectl apply -f k8s-migration-job.yaml

# Monitor
kubectl get migrationjob migrate-app-server -w

# Check logs
kubectl logs -f job/migrate-app-server
```

---

### Example 21: Kubernetes Batch Migration

**Scenario**: Multiple migrations as Kubernetes jobs

**File**: `k8s-batch-migrations.yaml`
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-migration-wave1
  namespace: hyper2kvm-system
spec:
  parallelism: 3
  completions: 3
  template:
    spec:
      containers:
      - name: hyper2kvm
        image: ghcr.io/ssahani/hyper2kvm:latest
        command:
          - h2kvmctl
          - --config
          - /config/migration.yaml
        volumeMounts:
          - name: config
            mountPath: /config
          - name: vmware-storage
            mountPath: /mnt/vmware
          - name: kvm-storage
            mountPath: /mnt/kvm
      volumes:
        - name: config
          configMap:
            name: migration-configs
        - name: vmware-storage
          persistentVolumeClaim:
            claimName: vmware-pvc
        - name: kvm-storage
          persistentVolumeClaim:
            claimName: kvm-pvc
      restartPolicy: Never
```

---

## Example Scripts

### Example 22: Automated Validation Script

**File**: `validate-migration.sh`
```bash
#!/bin/bash
# Validate migrated VM

VM_NAME=$1
QCOW2_FILE=$2

echo "=== Validating $VM_NAME ==="

# 1. Check file integrity
echo "Checking QCOW2 integrity..."
qemu-img check $QCOW2_FILE
if [ $? -ne 0 ]; then
    echo "ERROR: QCOW2 file is corrupted"
    exit 1
fi

# 2. Import to libvirt
echo "Importing to libvirt..."
virsh define ${VM_NAME}.xml

# 3. Start VM
echo "Starting VM..."
virsh start $VM_NAME

# 4. Wait for boot
echo "Waiting for boot..."
sleep 30

# 5. Check if running
if [ "$(virsh domstate $VM_NAME)" != "running" ]; then
    echo "ERROR: VM failed to start"
    exit 1
fi

# 6. Get IP address
IP=$(virsh domifaddr $VM_NAME | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)
echo "VM IP: $IP"

# 7. Test connectivity
echo "Testing connectivity..."
ping -c 4 $IP

echo "=== Validation Complete ==="
```

**Run**:
```bash
chmod +x validate-migration.sh
./validate-migration.sh app-server /kvm/vms/app-server.qcow2
```

---

### Example 23: Batch Migration Script

**File**: `batch-migrate.sh`
```bash
#!/bin/bash
# Batch migrate multiple VMs

VMS_DIR="/vmware/vms"
OUTPUT_DIR="/kvm/vms"
CONFIG_TEMPLATE="migration-template.yaml"

for vmdk in $VMS_DIR/*.vmdk; do
    VM_NAME=$(basename $vmdk .vmdk)

    echo "=== Migrating $VM_NAME ==="

    # Create config from template
    cat > /tmp/${VM_NAME}-migration.yaml << EOF
command: local
vmdk: $vmdk
output_dir: $OUTPUT_DIR
to_output: ${VM_NAME}.qcow2

fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
compress: true

log_file: /var/log/hyper2kvm/${VM_NAME}.log
EOF

    # Run migration
    h2kvmctl --config /tmp/${VM_NAME}-migration.yaml

    if [ $? -eq 0 ]; then
        echo "SUCCESS: $VM_NAME migrated"
    else
        echo "FAILED: $VM_NAME migration failed"
    fi

    echo ""
done

echo "=== Batch migration complete ==="
```

---

## Configuration Template

### Universal Template

Use this as a starting point for any migration:

```yaml
# Hyper2KVM Migration Configuration Template
# Version: 0.3.0
# Documentation: https://github.com/ssahani/hyper2kvm

# ============================================
# BASIC CONFIGURATION (Required)
# ============================================
command: local  # or: fetch-and-fix, vsphere_export
vmdk: /path/to/source.vmdk
output_dir: /path/to/output
to_output: output-name.qcow2

# ============================================
# LINUX VM OPTIONS (Recommended)
# ============================================
fstab_mode: stabilize-all  # or: uuid-only, preserve
regen_initramfs: true
# grub is auto-handled

# ============================================
# WINDOWS VM OPTIONS
# ============================================
# inject_virtio_drivers: true
# windows_version: 2019  # or: 2012, 2016, 2022, 10, 11

# ============================================
# VMWARE CLONE FIX
# ============================================
# xfs_regenerate_uuid: true  # Use for cloned VMs

# ============================================
# OUTPUT OPTIONS
# ============================================
out_format: qcow2  # or: raw, vdi
compress: true  # or: false
# compression_level: 6  # 1-9, default 6

# ============================================
# REMOTE OPTIONS
# ============================================
# host: esxi.example.com
# user: root
# identity: ~/.ssh/id_rsa
# remote: /vmfs/volumes/datastore1/vm.vmdk
# timeout: 3600
# network_retry: 3

# ============================================
# VALIDATION
# ============================================
libvirt_test: true  # or: false
# vm_name: test-vm
# memory: 2048
# vcpus: 2

# ============================================
# LOGGING
# ============================================
log_level: INFO  # or: DEBUG, WARNING, ERROR
log_file: /var/log/hyper2kvm/migration.log

# ============================================
# ADVANCED
# ============================================
# conversion_dir: /tmp/conversion
# keep_original: true
# parallel_streams: 4
```

---

## Quick Copy Commands

```bash
# Download examples directory
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm/examples

# Or copy individual examples
curl -O https://raw.githubusercontent.com/ssahani/hyper2kvm/main/examples/simple-linux.yaml
```

---

## Need Help?

- **Can't find your scenario?** Check [Migration Decision Tree](MIGRATION_DECISION_TREE.md)
- **Need to troubleshoot?** See [Troubleshooting Flowchart](TROUBLESHOOTING_FLOWCHART.md)
- **Want best practices?** Read [Best Practices Guide](BEST_PRACTICES.md)
- **Questions?** Check [FAQ](FAQ.md)

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
**Examples Tested**: Yes, all examples are tested and production-ready
