# h2kvm Migration Playbooks

Comprehensive step-by-step playbooks for common VM migration scenarios.

## Table of Contents

1. [Playbook 1: vSphere to KVM Single VM](#playbook-1-vsphere-to-kvm-single-vm)
2. [Playbook 2: vSphere to KVM Bulk Migration](#playbook-2-vsphere-to-kvm-bulk-migration)
3. [Playbook 3: AWS EC2 to KVM Migration](#playbook-3-aws-ec2-to-kvm-migration)
4. [Playbook 4: Azure VM to KVM Migration](#playbook-4-azure-vm-to-kvm-migration)
5. [Playbook 5: Disaster Recovery Migration](#playbook-5-disaster-recovery-migration)
6. [Playbook 6: Development Environment Migration](#playbook-6-development-environment-migration)
7. [Playbook 7: Production Database Migration](#playbook-7-production-database-migration)
8. [Playbook 8: Web Application Stack Migration](#playbook-8-web-application-stack-migration)
9. [Playbook 9: Zero-Downtime Migration](#playbook-9-zero-downtime-migration)
10. [Playbook 10: Hybrid Cloud Migration](#playbook-10-hybrid-cloud-migration)

---

## Playbook 1: vSphere to KVM Single VM

**Scenario**: Migrate a single VM from VMware vSphere to KVM/libvirt

**Prerequisites**:
- vSphere credentials with VM export permissions
- Target KVM host with sufficient storage
- Network connectivity between systems
- h2kvm installed and configured

### Step 1: Pre-Migration Assessment

```bash
# Check vSphere connectivity
export VSPHERE_HOST=vcenter.example.com
export VSPHERE_USERNAME=administrator@vsphere.local
export VSPHERE_PASSWORD='YourPassword'

# List available VMs
h2kvm --vsphere-list --vsphere-host $VSPHERE_HOST \
  --vsphere-user $VSPHERE_USERNAME \
  --vsphere-password $VSPHERE_PASSWORD

# Get VM details
h2kvm --vsphere-inspect --vm-name web-server-01 \
  --vsphere-host $VSPHERE_HOST \
  --vsphere-user $VSPHERE_USERNAME \
  --vsphere-password $VSPHERE_PASSWORD
```

### Step 2: Check Target Resources

```bash
# Check available storage on KVM host
df -h /var/lib/libvirt/images

# Check memory availability
free -h

# Verify QEMU/KVM installation
virsh version
qemu-img --version
```

### Step 3: Export and Convert VM

```bash
# Export VM from vSphere and convert to QCOW2
h2kvm \
  --vsphere-host $VSPHERE_HOST \
  --vsphere-user $VSPHERE_USERNAME \
  --vsphere-password $VSPHERE_PASSWORD \
  --vm-name web-server-01 \
  --output /var/lib/libvirt/images/web-server-01.qcow2 \
  --inject-drivers \
  --compress \
  --verbose

# Monitor progress
tail -f /var/log/h2kvm/migration.log
```

### Step 4: Create Libvirt Domain

```bash
# Generate libvirt XML
cat > web-server-01.xml <<'EOF'
<domain type='kvm'>
  <name>web-server-01</name>
  <memory unit='GiB'>4</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch='x86_64'>hvm</type>
    <boot dev='hd'/>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/web-server-01.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='bridge'>
      <source bridge='br0'/>
      <model type='virtio'/>
    </interface>
    <graphics type='vnc' port='-1'/>
    <console type='pty'/>
  </devices>
</domain>
EOF

# Define and start VM
virsh define web-server-01.xml
virsh start web-server-01
```

### Step 5: Post-Migration Validation

```bash
# Check VM status
virsh dominfo web-server-01

# Connect to console
virsh console web-server-01

# Inside VM, verify:
# - Network connectivity
# - All disks mounted
# - Services running

# Check network
ip addr show
ping -c 4 8.8.8.8

# Check disks
df -h
lsblk

# Check services
systemctl status
```

### Step 6: Cleanup

```bash
# Power off old vSphere VM (after validation)
# DO NOT delete until fully validated

# Document migration
cat > migration-report-web-server-01.txt <<EOF
Migration Report
================
VM Name: web-server-01
Source: vSphere vcenter.example.com
Destination: KVM kvm-host-01.local
Date: $(date)
Status: SUCCESS
Validation: PASSED
Notes: All services verified working
EOF
```

**Estimated Time**: 1-2 hours
**Risk Level**: Low (single VM, non-critical)
**Rollback**: Start original vSphere VM

---

## Playbook 2: vSphere to KVM Bulk Migration

**Scenario**: Migrate multiple VMs from vSphere to KVM in parallel

**Prerequisites**:
- VM inventory list
- Scheduled maintenance window
- Sufficient target storage and compute
- Batch migration plan approved

### Step 1: Create Migration Inventory

```bash
# Create VM list file
cat > vms-to-migrate.txt <<'EOF'
web-server-01
web-server-02
app-server-01
app-server-02
cache-server-01
EOF

# Verify all VMs exist
while read vm; do
  h2kvm --vsphere-inspect --vm-name "$vm" \
    --vsphere-host $VSPHERE_HOST \
    --vsphere-user $VSPHERE_USERNAME \
    --vsphere-password $VSPHERE_PASSWORD
done < vms-to-migrate.txt
```

### Step 2: Pre-Migration Validation

```bash
# Generate migration plan
h2kvm --batch vms-to-migrate.txt \
  --vsphere-host $VSPHERE_HOST \
  --vsphere-user $VSPHERE_USERNAME \
  --vsphere-password $VSPHERE_PASSWORD \
  --dry-run \
  --output-dir /var/lib/libvirt/images

# Check total storage required
du -sh /exports/vsphere/*

# Verify target capacity
df -h /var/lib/libvirt/images
```

### Step 3: Execute Batch Migration

```bash
# Run batch migration with 4 parallel workers
h2kvm --batch vms-to-migrate.txt \
  --vsphere-host $VSPHERE_HOST \
  --vsphere-user $VSPHERE_USERNAME \
  --vsphere-password $VSPHERE_PASSWORD \
  --output-dir /var/lib/libvirt/images \
  --parallel 4 \
  --inject-drivers \
  --compress \
  --log-file /var/log/h2kvm/batch-migration.log \
  --webhook-url https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  --webhook-type slack

# Monitor progress
watch -n 5 'tail -20 /var/log/h2kvm/batch-migration.log'
```

### Step 4: Automated Post-Migration

```bash
#!/bin/bash
# post-migration-validation.sh

VM_LIST="vms-to-migrate.txt"

while read vm; do
  echo "Validating $vm..."

  # Define VM
  virsh define /var/lib/libvirt/images/${vm}.xml

  # Start VM
  virsh start $vm

  # Wait for boot
  sleep 30

  # Check status
  STATUS=$(virsh domstate $vm)

  if [ "$STATUS" = "running" ]; then
    echo "✓ $vm is running"
  else
    echo "✗ $vm failed to start"
  fi
done < $VM_LIST
```

### Step 5: Generate Migration Report

```bash
# Create comprehensive report
h2kvm --report \
  --log-file /var/log/h2kvm/batch-migration.log \
  --output migration-report.html

# Email report
mail -s "Migration Report: vSphere to KVM" admin@example.com < migration-report.html
```

**Estimated Time**: 4-8 hours (depends on VM count and size)
**Risk Level**: Medium (multiple VMs, requires coordination)
**Rollback**: Start original vSphere VMs (staged rollback)

---

## Playbook 3: AWS EC2 to KVM Migration

**Scenario**: Migrate EC2 instance to on-premises KVM

**Prerequisites**:
- AWS credentials with EC2 and S3 permissions
- Instance stopped (for consistency)
- S3 bucket for export
- Sufficient bandwidth for download

### Step 1: Prepare AWS Environment

```bash
# Set AWS credentials
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_DEFAULT_REGION=us-east-1

# Stop instance
INSTANCE_ID=i-1234567890abcdef0
aws ec2 stop-instances --instance-ids $INSTANCE_ID

# Wait for stopped state
aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID
```

### Step 2: Create and Export EBS Snapshot

```bash
# Get volume ID
VOLUME_ID=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId' \
  --output text)

# Create snapshot
SNAPSHOT_ID=$(aws ec2 create-snapshot \
  --volume-id $VOLUME_ID \
  --description "Export for KVM migration" \
  --query 'SnapshotId' \
  --output text)

# Wait for snapshot completion
aws ec2 wait snapshot-completed --snapshot-ids $SNAPSHOT_ID

# Create export task
aws ec2 create-instance-export-task \
  --instance-id $INSTANCE_ID \
  --target-environment vmware \
  --export-to-s3-task "S3Bucket=my-export-bucket,S3Prefix=exports/"
```

### Step 3: Download from S3

```bash
# Download exported disk
aws s3 sync s3://my-export-bucket/exports/ /tmp/aws-export/

# Find VMDK file
VMDK_FILE=$(find /tmp/aws-export -name "*.vmdk" | head -1)
```

### Step 4: Convert to QCOW2 for KVM

```bash
# Convert VMDK to QCOW2
h2kvm \
  --input $VMDK_FILE \
  --output /var/lib/libvirt/images/aws-instance.qcow2 \
  --os-type linux \
  --inject-drivers \
  --compress \
  --verbose
```

### Step 5: Fix AWS-specific Configuration

```bash
# Remove cloud-init AWS datasource
virt-customize -a /var/lib/libvirt/images/aws-instance.qcow2 \
  --run-command 'rm -f /etc/cloud/cloud.cfg.d/*_aws.cfg'

# Update network configuration
virt-customize -a /var/lib/libvirt/images/aws-instance.qcow2 \
  --run-command 'rm -f /etc/sysconfig/network-scripts/ifcfg-eth*'

# Regenerate SSH host keys
virt-customize -a /var/lib/libvirt/images/aws-instance.qcow2 \
  --run-command 'rm -f /etc/ssh/ssh_host_*' \
  --run-command 'dpkg-reconfigure openssh-server'
```

### Step 6: Create KVM Domain

```bash
# Import to libvirt
virt-install \
  --name aws-instance \
  --memory 4096 \
  --vcpus 2 \
  --disk /var/lib/libvirt/images/aws-instance.qcow2,bus=virtio \
  --network bridge=br0,model=virtio \
  --graphics vnc \
  --import \
  --noautoconsole

# Start VM
virsh start aws-instance
```

**Estimated Time**: 3-6 hours (depends on disk size and bandwidth)
**Risk Level**: Medium (cloud egress costs, download time)
**Rollback**: Start AWS instance

---

## Playbook 4: Azure VM to KVM Migration

**Scenario**: Migrate Azure VM to on-premises KVM

**Prerequisites**:
- Azure credentials
- VM deallocated
- Azure Storage account
- ExpressRoute or VPN for fast transfer

### Step 1: Prepare Azure Environment

```bash
# Set Azure credentials
az login

# Deallocate VM
RESOURCE_GROUP=production-rg
VM_NAME=web-server-01

az vm deallocate --resource-group $RESOURCE_GROUP --name $VM_NAME
```

### Step 2: Export Managed Disk

```bash
# Get disk ID
DISK_ID=$(az vm show \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --query "storageProfile.osDisk.managedDisk.id" \
  --output tsv)

# Create disk export SAS URL
DISK_SAS=$(az disk grant-access \
  --ids $DISK_ID \
  --duration-in-seconds 86400 \
  --query "accessSas" \
  --output tsv)
```

### Step 3: Download VHD

```bash
# Download VHD using azcopy
azcopy copy "$DISK_SAS" "/tmp/azure-export/disk.vhd"

# Or use wget
wget -O /tmp/azure-export/disk.vhd "$DISK_SAS"
```

### Step 4: Convert VHD to QCOW2

```bash
# Convert using h2kvm
h2kvm \
  --input /tmp/azure-export/disk.vhd \
  --output /var/lib/libvirt/images/azure-vm.qcow2 \
  --os-type linux \
  --inject-drivers \
  --compress
```

### Step 5: Remove Azure Agent

```bash
# Remove Azure agent (waagent)
virt-customize -a /var/lib/libvirt/images/azure-vm.qcow2 \
  --run-command 'systemctl disable waagent' \
  --run-command 'apt-get remove -y walinuxagent || yum remove -y WALinuxAgent'

# Update network config
virt-customize -a /var/lib/libvirt/images/azure-vm.qcow2 \
  --run-command 'rm -f /etc/netplan/90-azure.yaml'
```

### Step 6: Import to KVM

```bash
# Define VM
virt-install \
  --name azure-vm \
  --memory 8192 \
  --vcpus 4 \
  --disk /var/lib/libvirt/images/azure-vm.qcow2,bus=virtio \
  --network bridge=br0,model=virtio \
  --import

# Start VM
virsh start azure-vm
```

**Estimated Time**: 4-8 hours (large VHD download)
**Risk Level**: Medium (Azure egress costs, long download)
**Rollback**: Restart Azure VM

---

## Playbook 5: Disaster Recovery Migration

**Scenario**: Emergency migration for DR failover

**Prerequisites**:
- DR plan documented
- VM replicas synced
- Network configured
- Tested runbook

### Step 1: Declare Disaster

```bash
# Document incident
cat > /var/log/dr-incident-$(date +%Y%m%d).log <<EOF
DR Event Declared
=================
Date: $(date)
Severity: P1
Reason: Primary datacenter outage
Duration: Unknown
Initiated by: On-call engineer
EOF

# Alert team
mail -s "DR ACTIVATED" team@example.com < /var/log/dr-incident-$(date +%Y%m%d).log
```

### Step 2: Activate DR VMs

```bash
#!/bin/bash
# dr-activate.sh

DR_VMS=(
  "web-server-01-dr"
  "app-server-01-dr"
  "db-server-01-dr"
)

for vm in "${DR_VMS[@]}"; do
  echo "Activating $vm..."

  # Start VM
  virsh start $vm

  # Wait for SSH
  until ssh -o ConnectTimeout=5 $vm 'exit' 2>/dev/null; do
    sleep 5
  done

  echo "✓ $vm is online"
done

# Update DNS
nsupdate <<EOF
server ns1.example.com
update delete web.example.com A
update add web.example.com 300 A 10.0.2.10
send
EOF
```

### Step 3: Verify Services

```bash
# Check web tier
curl -f http://web.example.com/health || echo "WEB FAILED"

# Check app tier
curl -f http://app.example.com:8080/health || echo "APP FAILED"

# Check database
mysql -h db.example.com -u monitor -p -e "SELECT 1" || echo "DB FAILED"
```

### Step 4: Monitor and Document

```bash
# Continuous monitoring
while true; do
  date
  virsh list --all
  curl -s http://web.example.com/health
  sleep 60
done | tee /var/log/dr-monitoring.log

# Document all actions
script /var/log/dr-actions-$(date +%Y%m%d).log
```

**Estimated Time**: 30 minutes - 2 hours (depends on automation)
**Risk Level**: High (production outage)
**Rollback**: Failback to primary datacenter

---

## Playbook 6: Development Environment Migration

**Scenario**: Migrate development VMs for cost savings

**Prerequisites**:
- Developer approval
- Code repositories backed up
- Non-production environment
- Low priority

### Step 1: Inventory Dev VMs

```bash
# List all dev VMs
h2kvm --vsphere-list --vsphere-host vcenter.dev.local | grep -i dev > dev-vms.txt

# Get VM owners
for vm in $(cat dev-vms.txt); do
  owner=$(ldapsearch -x -b "dc=example,dc=com" "(vm=$vm)" owner | grep owner)
  echo "$vm,$owner"
done > dev-vm-owners.csv
```

### Step 2: Notify Developers

```bash
# Send notification
cat > dev-migration-notice.txt <<'EOF'
Subject: Development VM Migration

Your development VM will be migrated from vSphere to KVM on Friday after 5 PM.

What you need to do:
1. Shut down your VM before 5 PM Friday
2. Commit all code changes
3. Update your connection settings on Monday

Questions? Contact devops@example.com
EOF

mail -s "Dev VM Migration" $(cat dev-vm-owners.csv | cut -d, -f2) < dev-migration-notice.txt
```

### Step 3: Migrate During Maintenance Window

```bash
# Friday 5 PM - start migration
h2kvm --batch dev-vms.txt \
  --vsphere-host vcenter.dev.local \
  --output-dir /var/lib/libvirt/images/dev \
  --parallel 8 \
  --low-priority \
  --compress

# Let it run over weekend
```

### Step 4: Update VM Inventory

```bash
# Update CMDB
for vm in $(cat dev-vms.txt); do
  curl -X PATCH https://cmdb.example.com/api/vms/$vm \
    -H "Content-Type: application/json" \
    -d '{"platform": "kvm", "host": "kvm-dev-01.local"}'
done
```

**Estimated Time**: Weekend (automated)
**Risk Level**: Low (dev environment, non-critical)
**Rollback**: Developers can restore from snapshots

---

## Playbook 7: Production Database Migration

**Scenario**: Migrate production database server with minimal downtime

**Prerequisites**:
- Database replication configured
- Maintenance window approved
- Rollback plan tested
- Stakeholder signoff

### Step 1: Enable Replication

```bash
# On source DB (vSphere VM)
mysql -u root -p <<'EOF'
CHANGE MASTER TO
  MASTER_HOST='db-replica.local',
  MASTER_USER='repl',
  MASTER_PASSWORD='password',
  MASTER_LOG_FILE='mysql-bin.000001',
  MASTER_LOG_POS=0;
START SLAVE;
SHOW SLAVE STATUS\G
EOF
```

### Step 2: Sync and Verify

```bash
# Monitor replication lag
while true; do
  LAG=$(mysql -u root -p -e "SHOW SLAVE STATUS\G" | grep Seconds_Behind_Master | awk '{print $2}')
  echo "Replication lag: $LAG seconds"
  if [ "$LAG" -eq 0 ]; then
    break
  fi
  sleep 10
done
```

### Step 3: Cutover

```bash
# Set application to read-only
curl -X POST https://app.example.com/admin/readonly

# Stop writes on source
mysql -u root -p -e "SET GLOBAL read_only = 1;"

# Wait for final sync
sleep 30

# Promote replica
mysql -u root -p -e "STOP SLAVE; RESET SLAVE ALL;"

# Update application config
sed -i 's/db.old.local/db.new.local/' /etc/app/database.conf
systemctl restart app

# Enable writes
curl -X POST https://app.example.com/admin/readwrite
```

### Step 4: Verify Data Integrity

```bash
# Checksum comparison
mysqldump --all-databases --single-transaction | md5sum
# Compare with source

# Run application tests
./run-integration-tests.sh

# Monitor for errors
tail -f /var/log/app/errors.log
```

**Estimated Time**: 2-4 hours (planned downtime: 15 minutes)
**Risk Level**: High (production data)
**Rollback**: Revert DNS to old server

---

## Playbook 8: Web Application Stack Migration

**Scenario**: Migrate multi-tier web application

**Prerequisites**:
- Load balancer configured
- Application architecture documented
- Dependencies mapped
- Rolling migration plan

### Step 1: Migration Order

```
1. Database tier (using Playbook 7)
2. Application tier (rolling)
3. Web tier (rolling)
4. Cache tier (can drain)
```

### Step 2: Migrate Database (Day 1)

```bash
# Use Playbook 7 for database migration
./playbook-7-database-migration.sh
```

### Step 3: Migrate Application Tier (Day 2)

```bash
# Remove app-01 from load balancer
curl -X DELETE https://lb.example.com/api/backends/app-01

# Migrate app-01
h2kvm --vm-name app-01 \
  --vsphere-host vcenter.local \
  --output /var/lib/libvirt/images/app-01.qcow2 \
  --inject-drivers

# Start on KVM
virsh define app-01.xml
virsh start app-01

# Add to load balancer
curl -X POST https://lb.example.com/api/backends \
  -d '{"name": "app-01", "ip": "10.0.3.00", "port": 8080}'

# Verify health
curl http://lb.example.com/health | grep app-01

# Repeat for app-02, app-03
```

### Step 4: Migrate Web Tier (Day 3)

```bash
# Similar rolling migration for web-01, web-02, web-03
for web in web-01 web-02 web-03; do
  # Remove from LB
  curl -X DELETE https://lb.example.com/api/backends/$web

  # Migrate
  h2kvm --vm-name $web --output /var/lib/libvirt/images/${web}.qcow2

  # Start on KVM
  virsh start $web

  # Add back to LB
  curl -X POST https://lb.example.com/api/backends \
    -d "{\"name\": \"$web\", \"ip\": \"10.0.3.${i}\", \"port\": 80}"

  # Verify
  curl -I http://lb.example.com/
done
```

### Step 5: Migrate Cache (Day 4)

```bash
# Drain Redis cache
redis-cli BGSAVE

# Stop accepting connections
redis-cli CONFIG SET protected-mode yes

# Migrate
h2kvm --vm-name cache-01 --output /var/lib/libvirt/images/cache-01.qcow2

# Start and restore
virsh start cache-01
redis-cli --rdb /var/lib/redis/dump.rdb
```

**Estimated Time**: 4 days (rolling with no downtime)
**Risk Level**: Medium (complex dependencies)
**Rollback**: Per-tier rollback capability

---

## Playbook 9: Zero-Downtime Migration

**Scenario**: Migrate with absolutely no downtime

**Prerequisites**:
- Active-active configuration
- Real-time replication
- Load balancer with health checks
- Automated failover

### Step 1: Configure Replication

```bash
# Set up real-time data replication
# (Database replication, file sync, etc.)

# Enable bidirectional sync
lsyncd /etc/lsyncd/lsyncd.conf.lua
```

### Step 2: Build Shadow Environment

```bash
# Migrate all VMs to KVM (kept offline)
h2kvm --batch all-vms.txt \
  --output-dir /var/lib/libvirt/images/shadow \
  --no-start

# Configure replication to shadow VMs
./setup-replication.sh
```

### Step 3: Verify Sync

```bash
# Check data consistency
diff -r /mnt/production /mnt/shadow

# Verify database replication
mysql -e "SHOW SLAVE STATUS\G" | grep Seconds_Behind_Master
```

### Step 4: Controlled Cutover

```bash
# Traffic distribution: 90% old, 10% new
curl -X PATCH https://lb.example.com/api/pools/main \
  -d '{"backends": [
    {"name": "old-stack", "weight": 90},
    {"name": "new-stack", "weight": 10}
  ]}'

# Monitor for errors
tail -f /var/log/app/*.log | grep ERROR

# Gradually shift traffic
# 80/20, then 70/30, then 50/50, then 20/80, then 0/100
```

### Step 5: Complete Migration

```bash
# Final cutover: 100% to new
curl -X PATCH https://lb.example.com/api/pools/main \
  -d '{"backends": [{"name": "new-stack", "weight": 100}]}'

# Monitor
watch -n 5 'curl -s http://lb.example.com/metrics | grep requests_per_second'
```

**Estimated Time**: 1 week (gradual rollout)
**Risk Level**: Low (can roll back any time)
**Rollback**: Adjust load balancer weights

---

## Playbook 10: Hybrid Cloud Migration

**Scenario**: Migrate to hybrid cloud (some VMs stay in cloud)

**Prerequisites**:
- Cloud connectivity (VPN/DirectConnect)
- Hybrid network design
- Cloud cost analysis
- Application profiling

### Step 1: Categorize Workloads

```bash
# Classify VMs
cat > workload-classification.csv <<'EOF'
VM,Type,Location,Reason
db-primary,database,on-prem,latency-sensitive
db-replica,database,cloud,DR
web-01,web,cloud,elastic scaling
app-01,application,on-prem,compliance
cache-01,cache,on-prem,performance
EOF
```

### Step 2: Migrate On-Prem Candidates

```bash
# Migrate latency-sensitive workloads to on-prem KVM
grep ",on-prem," workload-classification.csv | cut -d, -f1 > migrate-to-kvm.txt

h2kvm --batch migrate-to-kvm.txt \
  --output-dir /var/lib/libvirt/images \
  --inject-drivers
```

### Step 3: Configure Hybrid Networking

```bash
# Set up VPN between on-prem and cloud
ipsec up aws-tunnel

# Verify connectivity
ping -c 4 10.1.0.10  # Cloud subnet

# Configure routing
ip route add 10.1.0.0/16 via 10.0.0.1 dev eth1
```

### Step 4: Update Application Config

```bash
# Update database connection strings
# On-prem app → on-prem DB
sed -i 's/db.cloud.example.com/db.local/' /etc/app/config.ini

# Cloud app → on-prem DB (via VPN)
ssh cloud-app-01 "echo 'DB_HOST=10.0.1.10' >> /etc/app/env"
```

### Step 5: Optimize Traffic Flow

```bash
# Measure latency
for host in web-01 app-01 db-primary; do
  echo "$host: $(ping -c 10 $host | tail -1 | awk '{print $4}' | cut -d/ -f2) ms"
done

# Adjust placement if needed
# Move high-traffic services closer together
```

**Estimated Time**: 2-3 weeks (phased approach)
**Risk Level**: Medium (complex networking)
**Rollback**: Revert network changes, restart cloud VMs

---

## General Best Practices

### Before Migration

1. **Document Everything**
   - Current architecture
   - Dependencies
   - Configuration files
   - Credentials (in vault)

2. **Test the Process**
   - Dry run on non-critical VM
   - Validate conversion
   - Test rollback procedure

3. **Communicate**
   - Notify stakeholders
   - Schedule maintenance window
   - Prepare status updates

### During Migration

1. **Monitor Continuously**
   ```bash
   watch -n 5 'virsh list --all; df -h'
   ```

2. **Log Everything**
   ```bash
   script /var/log/migration-$(date +%Y%m%d-%H%M%S).log
   ```

3. **Stay Ready to Rollback**
   - Keep old VMs powered off (not deleted)
   - Have rollback commands ready
   - Monitor for issues

### After Migration

1. **Validate Thoroughly**
   - Application functionality
   - Performance metrics
   - Security posture

2. **Update Documentation**
   - New IP addresses
   - New hostnames
   - New procedures

3. **Decommission Old Infrastructure**
   - Only after 30+ days
   - After full validation
   - With proper approval

---

## Troubleshooting Common Issues

### Issue: Boot Failure After Migration

```bash
# Fix MBR
virt-rescue -a vm.qcow2
><rescue> grub2-install /dev/sda
><rescue> grub2-mkconfig -o /boot/grub2/grub.cfg
```

### Issue: Network Not Working

```bash
# Fix network interface names
virt-customize -a vm.qcow2 \
  --run-command 'rm -f /etc/udev/rules.d/70-persistent-net.rules'
```

### Issue: High CPU Usage

```bash
# Switch to host CPU model
virsh edit vm-name
# Change <cpu mode='custom'> to <cpu mode='host-passthrough'>
```

---

## Useful Scripts

### Pre-Migration Checklist

```bash
#!/bin/bash
# pre-migration-check.sh

echo "Pre-Migration Checklist"
echo "======================="

# Check connectivity
ping -c 1 $VSPHERE_HOST &>/dev/null && echo "✓ vSphere reachable" || echo "✗ vSphere unreachable"

# Check storage
FREE_GB=$(df /var/lib/libvirt/images | tail -1 | awk '{print $4/1024/1024}')
echo "✓ Free storage: ${FREE_GB} GB"

# Check tools
command -v qemu-img &>/dev/null && echo "✓ qemu-img installed" || echo "✗ qemu-img missing"
command -v virsh &>/dev/null && echo "✓ virsh installed" || echo "✗ virsh missing"
```

### Post-Migration Validation

```bash
#!/bin/bash
# post-migration-validate.sh

VM=$1

echo "Validating $VM..."

# Check running
if virsh domstate $VM | grep -q running; then
  echo "✓ VM is running"
else
  echo "✗ VM not running"
  exit 1
fi

# Check network
VM_IP=$(virsh domifaddr $VM | grep ipv4 | awk '{print $4}' | cut -d/ -f1)
if ping -c 1 $VM_IP &>/dev/null; then
  echo "✓ Network accessible"
else
  echo "✗ Network not accessible"
  exit 1
fi

echo "✓ $VM validation passed"
```

---

## See Also

- [Quick Start Guide](./03-Quick-Start.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)
- [Security Best Practices](./SECURITY-BEST-PRACTICES.md)
- [API Reference](./API-Reference.md)
