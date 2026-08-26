# Advanced Tutorial: Live Migration & Disaster Recovery

**Duration**: 2-4 hours
**Difficulty**: Advanced
**Prerequisites**: Completed intermediate tutorial, SSH access to source VMs, understanding of networking

---

## What You'll Learn

By the end of this tutorial, you will:
- ✅ Perform live migrations without VM downtime (live-fix)
- ✅ Set up disaster recovery testing workflows
- ✅ Implement rollback strategies for failed migrations
- ✅ Configure automated post-migration validation
- ✅ Handle complex multi-tier application migrations
- ✅ Optimize migration performance for large VMs

---

## Prerequisites

### System Requirements
- **OS**: Linux with KVM support
- **Network**: SSH access to source VMs
- **Resources**: 16GB+ RAM, fast SSD storage
- **Privileges**: sudo access on both source and target systems

### Knowledge Requirements
- SSH key-based authentication
- libvirt/KVM management
- Basic Linux system administration
- Understanding of fstab, bootloaders, and initramfs

---

## Tutorial Overview

1. **Live Fix (SSH-Based)** - Fix running VMs without downtime
2. **Disaster Recovery Testing** - Validate migration safety
3. **Rollback Framework** - Recover from failed migrations
4. **Performance Optimization** - Speed up large VM migrations
5. **Multi-Tier Application Migration** - Migrate complex stacks

---

## Part 1: Live Fix - Zero-Downtime Migration Prep

### Scenario

You have a production database server that cannot afford downtime. You need to prepare it for migration to KVM without stopping the VM.

### 1.1: Setup SSH Access

First, set up passwordless SSH access:

```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "h2kvm-migration"

# Copy key to production VM
ssh-copy-id root@prod-db-01.example.com

# Test connection
ssh root@prod-db-01.example.com "uname -a"
```

### 1.2: Create Live Fix Configuration

Create `live-fix-db.yaml`:

```yaml
# Live fix configuration for production database server
cmd: live-fix
host: prod-db-01.example.com
user: root
port: 22
identity: ~/.ssh/id_ed25519

# Output directory for reports and backups
output_dir: ./migrations/prod-db-01
workdir: ./migrations/prod-db-01/work

# Fixes to apply
fstab_mode: stabilize-all      # Convert to UUID/LABEL
regen_initramfs: true           # Add virtio drivers
remove_vmware_tools: true       # Clean up VMware tools

# Safety features
no_backup: false                # Keep backups of modified files
dry_run: false                  # Set true for preview

# Logging
verbose: 2
log_file: ./migrations/prod-db-01/live-fix.log
```

### 1.3: Preview Changes (Dry Run)

**Always run dry-run first** to see what will be changed:

```bash
# Preview changes without modifying anything
h2kvmctl --config live-fix-db.yaml --dry-run
```

Example output:
```
🔍 DRY RUN MODE - No changes will be made

Inspection Results:
  OS: CentOS Stream 9
  Kernel: 5.14.0-162.el9
  Filesystems: 3 (ext4, xfs, swap)

Planned Changes:
  ✓ /etc/fstab: 3 entries will be converted to UUID
  ✓ initramfs: Will add virtio_blk, virtio_scsi, virtio_net
  ✓ VMware Tools: Will remove vmware-tools package

Backups will be created at: /root/.h2kvm-backup/
```

### 1.4: Execute Live Fix

If dry-run looks good, execute the actual fix:

```bash
# Apply fixes to running VM
h2kvmctl --config live-fix-db.yaml

# Monitor progress
tail -f ./migrations/prod-db-01/live-fix.log
```

### 1.5: Verify Results

After live-fix completes:

```bash
# Check the migration report
cat ./migrations/prod-db-01/migration-report.md

# SSH to VM and verify changes
ssh root@prod-db-01.example.com

# Verify fstab was updated
cat /etc/fstab
# Should now use UUID= instead of /dev/sdX

# Verify initramfs has virtio drivers
lsinitrd /boot/initramfs-$(uname -r).img | grep virtio

# Verify VMware tools removed
rpm -qa | grep vmware-tools  # Should be empty
```

### 1.6: Schedule VM Migration Window

Now that the VM is prepared, schedule a brief maintenance window to:
1. Shut down the VM on VMware
2. Export the VMDK
3. Convert to qcow2 using h2kvmctl
4. Import to KVM
5. Boot and validate

The live-fix preparation means the downtime will be minimal (just the export/import time).

---

## Part 2: Disaster Recovery Testing

### Scenario

Before migrating production systems, test the entire workflow in a DR environment.

### 2.1: Create DR Test Environment

```bash
# Create isolated network for DR testing
virsh net-define - <<EOF
<network>
  <name>dr-test-net</name>
  <bridge name='virbr-dr'/>
  <forward mode='nat'/>
  <ip address='192.168.99.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.99.100' end='192.168.99.254'/>
    </dhcp>
  </ip>
</network>
EOF

virsh net-start dr-test-net
virsh net-autostart dr-test-net
```

### 2.2: Create DR Migration Configuration

Create `dr-test-migration.yaml`:

```yaml
cmd: local
vmdk: /backups/prod-db-01-snapshot.vmdk
output_dir: ./dr-test/output
to_output: prod-db-01-dr.qcow2
out_format: qcow2

# Apply all production fixes
fstab_mode: stabilize-all
regen_initramfs: true
remove_vmware_tools: true
compress: true

# Enable automatic testing
libvirt_test: true
vm_name: dr-test-prod-db-01
memory: 8192
vcpus: 4
libvirt_network: dr-test-net
timeout: 600

# Keep VM running for validation
keep_domain: true

# Generate detailed reports
report: ./dr-test/dr-migration-report.md
checksum: true
verbose: 2
```

### 2.3: Execute DR Test Migration

```bash
# Run migration with automatic validation
h2kvmctl --config dr-test-migration.yaml

# Migration will:
# 1. Convert VMDK to qcow2
# 2. Apply fstab/initramfs fixes
# 3. Create libvirt domain
# 4. Boot VM automatically
# 5. Run validation tests
# 6. Keep VM running for manual testing
```

### 2.4: Validate DR Environment

```bash
# Check VM status
virsh list --all | grep dr-test

# Get VM IP address
virsh domifaddr dr-test-prod-db-01

# SSH to DR VM and run application tests
ssh root@<dr-vm-ip>

# Run database integrity checks
mysqladmin -u root -p ping
mysql -u root -p -e "SHOW DATABASES;"

# Check application logs
journalctl -u mysql -n 50

# Validate network connectivity
ping -c 3 192.168.99.1
```

### 2.5: DR Test Checklist

Create validation checklist:

```bash
cat > dr-validation-checklist.md <<'EOF'
# DR Migration Validation Checklist

## Boot Validation
- [ ] VM boots successfully
- [ ] No kernel panics or errors
- [ ] All filesystems mount correctly
- [ ] Network interfaces come up

## Application Validation
- [ ] Database service starts
- [ ] Database accepts connections
- [ ] Sample queries return correct data
- [ ] Application logs show no errors

## Performance Validation
- [ ] Disk I/O performance acceptable (fio tests)
- [ ] Network throughput meets requirements
- [ ] CPU performance normal

## Data Integrity
- [ ] Checksums match pre-migration
- [ ] Database consistency checks pass
- [ ] File counts match source

## Sign-off
- [ ] Reviewed by: ___________
- [ ] Date: ___________
- [ ] Approved for production migration: Yes/No
EOF
```

---

## Part 3: Rollback Framework

### Scenario

Implement automated rollback capability for production migrations.

### 3.1: Create Pre-Migration Snapshot Script

Create `create-migration-snapshot.sh`:

```bash
#!/bin/bash
# Create snapshot before migration

VM_NAME="$1"
SNAPSHOT_DIR="./snapshots"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$SNAPSHOT_DIR"

echo "Creating pre-migration snapshot for $VM_NAME..."

# Using h2kvm's rollback API
python3 <<EOF
import logging
from h2kvm.rollback import RollbackOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("snapshot")

orchestrator = RollbackOrchestrator(logger)

# Create snapshot with checksum
snapshot = orchestrator.snapshot_manager.create_snapshot(
    "/vms/${VM_NAME}.vmdk",
    compute_checksum=True,
    snapshot_dir="$SNAPSHOT_DIR"
)

print(f"✅ Snapshot created: {snapshot.snapshot_id}")
print(f"   Path: {snapshot.snapshot_path}")
print(f"   Checksum: {snapshot.checksum}")

# Save snapshot ID for rollback
with open("$SNAPSHOT_DIR/${VM_NAME}-latest-snapshot.txt", "w") as f:
    f.write(snapshot.snapshot_id)
EOF
```

### 3.2: Create Migration with Rollback Script

Create `migrate-with-rollback.sh`:

```bash
#!/bin/bash
# Migration with automatic rollback on failure

set -e

VM_NAME="$1"
CONFIG_FILE="$2"

# Create snapshot first
./create-migration-snapshot.sh "$VM_NAME"

echo "Starting migration for $VM_NAME..."

# Run migration and capture exit code
if h2kvmctl --config "$CONFIG_FILE"; then
    echo "✅ Migration succeeded!"

    # Optionally cleanup old snapshots after successful migration
    read -p "Delete pre-migration snapshot? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "./snapshots/${VM_NAME}"*
        echo "Snapshot deleted."
    fi
else
    echo "💥 Migration failed! Initiating rollback..."

    # Read snapshot ID
    SNAPSHOT_ID=$(cat "./snapshots/${VM_NAME}-latest-snapshot.txt")

    # Execute rollback
    python3 <<EOF
import logging
from h2kvm.rollback import RollbackOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rollback")

orchestrator = RollbackOrchestrator(logger)

# Execute full rollback with validation
report = orchestrator.execute_full_rollback(
    "$SNAPSHOT_ID",
    verify_checksum=True,
    validate=True
)

if report.success:
    print("✅ Rollback completed successfully")
else:
    print(f"💥 Rollback failed: {report.error_message}")
    exit(1)
EOF
fi
```

### 3.3: Test Rollback Procedure

```bash
# Make script executable
chmod +x migrate-with-rollback.sh

# Test with a non-critical VM first
./migrate-with-rollback.sh test-vm test-vm-config.yaml

# Intentionally cause failure to test rollback
# (e.g., wrong path in config)
./migrate-with-rollback.sh test-vm broken-config.yaml
# Should automatically rollback
```

---

## Part 4: Performance Optimization

### Scenario

Optimize migration of large VMs (500GB+) for minimal downtime.

### 4.1: Pre-Migration Optimization

```bash
# On source VM (before migration):
# 1. Clean up unnecessary data
ssh root@source-vm <<'EOF'
# Clear package cache
yum clean all  # RHEL/CentOS
apt clean      # Ubuntu/Debian

# Clear old logs
journalctl --vacuum-time=7d

# Clear temp files
find /tmp /var/tmp -type f -atime +7 -delete

# Zero out free space for better compression
dd if=/dev/zero of=/EMPTY bs=1M || rm -f /EMPTY
EOF

# 2. Shut down VM cleanly
ssh root@source-vm "shutdown -h now"
```

### 4.2: Optimized Migration Configuration

Create `large-vm-migration.yaml`:

```yaml
cmd: fetch-and-fix
host: esxi-host.example.com
user: root
remote: /vmfs/volumes/datastore1/large-vm/large-vm.vmdk

# Output configuration
output_dir: /fast-nvme/migrations
to_output: large-vm.qcow2
out_format: qcow2

# Performance optimizations
compress: true              # Enable qcow2 compression
flatten: true               # Flatten VMDK snapshots

# Parallel processing (if supported)
parallel_processing: true

# Fixes
fstab_mode: stabilize-all
regen_initramfs: true

# Monitoring
verbose: 2
log_file: /fast-nvme/migrations/large-vm.log
checksum: true

# Post-migration testing (optional, adds time)
libvirt_test: false  # Test separately after migration
```

### 4.3: Monitor Migration Performance

```bash
# Start migration in background
h2kvmctl --config large-vm-migration.yaml > migration.log 2>&1 &
MIGRATION_PID=$!

# Monitor progress in real-time
watch -n 5 '
echo "=== Migration Progress ==="
ps aux | grep $MIGRATION_PID
echo ""
echo "=== Disk Usage ==="
df -h /fast-nvme/migrations
echo ""
echo "=== Network Transfer ==="
ifstat 1 1
echo ""
echo "=== Recent Log Entries ==="
tail -5 /fast-nvme/migrations/large-vm.log
'

# Wait for completion
wait $MIGRATION_PID
echo "Migration completed with exit code: $?"
```

### 4.4: Performance Metrics

After migration, analyze performance:

```bash
# Extract timing information from log
cat migration.log | grep -E "(Duration|Speed|Time)"

# Calculate metrics
python3 <<'EOF'
import json

# Load migration report
with open('/fast-nvme/migrations/migration-report.json') as f:
    report = json.load(f)

# Calculate metrics
size_gb = report.get('source_size_bytes', 0) / (1024**3)
duration_sec = report.get('migration_duration_seconds', 1)
speed_mbps = (size_gb * 1024) / duration_sec

print(f"VM Size: {size_gb:.2f} GB")
print(f"Duration: {duration_sec:.2f} seconds ({duration_sec/60:.2f} minutes)")
print(f"Average Speed: {speed_mbps:.2f} MB/s")
print(f"Compression Ratio: {report.get('compression_ratio', 'N/A')}")
EOF
```

---

## Part 5: Multi-Tier Application Migration

### Scenario

Migrate a complete 3-tier application stack (web, app, database) with minimal downtime.

### 5.1: Plan Migration Order

```
Migration Order (reverse dependency):
1. Database tier (migrate first, test thoroughly)
2. Application tier (migrate second, update DB connection)
3. Web tier (migrate last, update app connection)
4. Load balancer reconfiguration
```

### 5.2: Create Master Migration Plan

Create `multi-tier-migration-plan.yaml`:

```yaml
# Multi-tier migration manifest
migrations:
  # Phase 1: Database tier
  - name: db-primary
    cmd: local
    vmdk: /backups/db-primary.vmdk
    to_output: db-primary.qcow2
    fstab_mode: stabilize-all
    regen_initramfs: true
    priority: 1

  - name: db-replica
    cmd: local
    vmdk: /backups/db-replica.vmdk
    to_output: db-replica.qcow2
    fstab_mode: stabilize-all
    regen_initramfs: true
    priority: 1

  # Phase 2: Application tier
  - name: app-server-01
    cmd: local
    vmdk: /backups/app-01.vmdk
    to_output: app-01.qcow2
    fstab_mode: stabilize-all
    regen_initramfs: true
    priority: 2

  - name: app-server-02
    cmd: local
    vmdk: /backups/app-02.vmdk
    to_output: app-02.qcow2
    fstab_mode: stabilize-all
    regen_initramfs: true
    priority: 2

  # Phase 3: Web tier
  - name: web-server-01
    cmd: local
    vmdk: /backups/web-01.vmdk
    to_output: web-01.qcow2
    fstab_mode: stabilize-all
    regen_initramfs: true
    priority: 3

  - name: web-server-02
    cmd: local
    vmdk: /backups/web-02.vmdk
    to_output: web-02.qcow2
    fstab_mode: stabilize-all
    regen_initramfs: true
    priority: 3
```

### 5.3: Create Phased Migration Script

Create `execute-phased-migration.sh`:

```bash
#!/bin/bash
# Execute multi-tier migration in phases

set -e

PLAN_FILE="multi-tier-migration-plan.yaml"
LOG_DIR="./migration-logs"
mkdir -p "$LOG_DIR"

# Function to migrate VMs of a specific priority
migrate_phase() {
    local phase=$1
    echo "==================================="
    echo "Migrating Phase $phase VMs..."
    echo "==================================="

    # Extract VMs for this phase and migrate
    python3 <<EOF
import yaml

with open('$PLAN_FILE') as f:
    plan = yaml.safe_load(f)

phase_vms = [vm for vm in plan['migrations'] if vm.get('priority') == $phase]

print(f"Phase $phase: {len(phase_vms)} VMs to migrate")

for vm in phase_vms:
    vm_name = vm['name']
    print(f"\\nMigrating {vm_name}...")

    # Create individual config for this VM
    config = f"/tmp/{vm_name}-config.yaml"
    with open(config, 'w') as f:
        yaml.dump(vm, f)

    # Run migration
    import subprocess
    result = subprocess.run(['h2kvmctl', '--config', config],
                          capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✅ {vm_name} migrated successfully")
    else:
        print(f"💥 {vm_name} migration failed!")
        print(result.stderr)
        raise Exception(f"Migration failed for {vm_name}")
EOF

    echo "Phase $phase completed!"
    echo ""
}

# Execute migrations phase by phase
migrate_phase 1  # Database tier
read -p "Phase 1 complete. Validate DBs, then press Enter to continue to Phase 2..."

migrate_phase 2  # Application tier
read -p "Phase 2 complete. Validate apps, then press Enter to continue to Phase 3..."

migrate_phase 3  # Web tier
echo "All phases completed!"
```

### 5.4: Validation Between Phases

Create `validate-tier.sh`:

```bash
#!/bin/bash
# Validate tier after migration

TIER=$1  # db, app, or web

case $TIER in
  db)
    echo "Validating database tier..."
    virsh list | grep -E "db-primary|db-replica"

    # Test DB connectivity
    mysql -h <db-primary-ip> -u monitor -p -e "SELECT 1;"

    # Check replication status
    mysql -h <db-replica-ip> -u monitor -p -e "SHOW SLAVE STATUS\G"
    ;;

  app)
    echo "Validating application tier..."
    virsh list | grep "app-server"

    # Test app endpoints
    curl -f http://<app-01-ip>:8080/health
    curl -f http://<app-02-ip>:8080/health
    ;;

  web)
    echo "Validating web tier..."
    virsh list | grep "web-server"

    # Test web servers
    curl -f http://<web-01-ip>/
    curl -f http://<web-02-ip>/
    ;;

  *)
    echo "Unknown tier: $TIER"
    exit 1
    ;;
esac

echo "✅ $TIER tier validation passed"
```

---

## Part 6: Production Migration Checklist

### Pre-Migration Checklist

```markdown
# Production Migration Checklist

## Planning Phase
- [ ] DR test migration completed successfully
- [ ] Performance requirements validated
- [ ] Rollback procedure tested
- [ ] Maintenance window scheduled and approved
- [ ] Stakeholders notified

## Pre-Migration Steps
- [ ] Create snapshots of all source VMs
- [ ] Backup all configuration files
- [ ] Document current IP addresses and network config
- [ ] Test SSH access to all VMs
- [ ] Verify sufficient disk space on target

## Migration Execution
- [ ] Enable maintenance mode on applications
- [ ] Shut down VMs in correct order
- [ ] Execute migrations using h2kvmctl
- [ ] Validate each VM before proceeding
- [ ] Update DNS/load balancer configuration

## Post-Migration Validation
- [ ] All VMs boot successfully
- [ ] Network connectivity verified
- [ ] Application services running
- [ ] Performance within acceptable range
- [ ] Data integrity checks pass
- [ ] Monitoring systems updated

## Rollback Decision Point
- [ ] Migration success confirmed by all teams
- [ ] Rollback not required
- [ ] Snapshots can be archived (not deleted yet)

## Cleanup (After 30 Days)
- [ ] Archive old VMware VMs
- [ ] Remove temporary migration files
- [ ] Delete old snapshots
- [ ] Update documentation
```

---

## Summary

You've learned:
- ✅ Live-fix for zero-downtime preparation
- ✅ DR testing workflows
- ✅ Automated rollback procedures
- ✅ Performance optimization for large VMs
- ✅ Multi-tier application migration strategies

## Next Steps

1. Practice these workflows in your lab environment
2. Document your organization's specific requirements
3. Create runbooks for your migration scenarios
4. Review the [Enterprise Deployment Tutorial](04-enterprise-deployment.md)

## Additional Resources

- [Live Migration API Documentation](../api/live-migration-api.md)
- [Rollback API Documentation](../api/rollback-api.md)
- [Performance Tuning Guide](../guides/performance-tuning.md)
- [Troubleshooting Guide](../guides/troubleshooting.md)

---

**Need Help?**
- GitHub Issues: [Report problems](https://github.com/ssahani/h2kvm/issues)
- Documentation: [Full documentation](../index.md)
