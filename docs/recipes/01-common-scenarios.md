# Migration Recipes: Common Scenarios

**Last Updated**: March 2026

Practical recipes for common VM migration scenarios. Each recipe includes prerequisites, step-by-step instructions, validation, and troubleshooting tips.

---

## Table of Contents

1. [Single Windows Server Migration](#1-single-windows-server-migration)
2. [Linux Web Server Migration](#2-linux-web-server-migration)
3. [Database Server Migration](#3-database-server-migration)
4. [Batch Migration of 50+ VMs](#4-batch-migration-of-50-vms)
5. [Live Migration with Minimal Downtime](#5-live-migration-with-minimal-downtime)
6. [DR Testing from Veeam Backup](#6-dr-testing-from-veeam-backup)
7. [VM to Kubernetes Migration](#7-vm-to-kubernetes-migration)
8. [Domain Controller Migration](#8-domain-controller-migration)
9. [Legacy Application Server](#9-legacy-application-server)
10. [High-Availability Cluster Migration](#10-high-availability-cluster-migration)

---

## 1. Single Windows Server Migration

**Scenario**: Migrate Windows Server 2019 from Hyper-V to KVM
**Duration**: 15-30 minutes
**Difficulty**: Beginner

### Prerequisites
- Windows Server VM (2012 R2 or later)
- Source VM disk file (.vhdx, .vmdk)
- Disk space: 3x source VM size
- sudo/root access
- VirtIO drivers: `quickstart.sh` installs `virtio-win.iso` to `/var/lib/hyper2kvm/virtio-win.iso` (auto-discovered, no extra flags needed). Use `--virtio-drivers-dir` only to override with a custom path.

### Steps

```bash
# 1. Locate source VM
SOURCE=/path/to/windows-server.vhdx
TARGET=/vms/migrated/windows-server.qcow2

# 2. Create pre-migration snapshot (recommended)
hyper2kvm snapshot create $SOURCE \
    --type qcow2 \
    --checksum

# 3. Execute migration with all fixes
hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --format qcow2 \
    --fix-all \
    --verbose

# 4. Validate migration
hyper2kvm validate $TARGET \
    --check-boot \
    --check-services \
    --check-network \
    --report /reports/windows-server-validation.json

# 5. Import to libvirt
virt-install \
    --name windows-server \
    --memory 8192 \
    --vcpus 4 \
    --disk $TARGET,bus=virtio \
    --network bridge=br0,model=virtio \
    --graphics vnc \
    --os-variant win2k19 \
    --import
```

### Validation
```bash
# Connect to VM console
virsh console windows-server

# Or VNC
virt-viewer windows-server
```

**Expected Boot Time**: 1-2 minutes to login prompt

### Troubleshooting

**Issue**: VM boots to "Inaccessible Boot Device"
```bash
# Solution: Re-inject VirtIO drivers
hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --fix-drivers \
    --force
```

**Issue**: Network adapter not found
```bash
# Solution: Re-apply network fix
hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --fix-network \
    --force
```

---

## 2. Linux Web Server Migration

**Scenario**: Migrate Ubuntu 22.04 LAMP stack from VMware to KVM
**Duration**: 10-20 minutes
**Difficulty**: Beginner

### Prerequisites
- Ubuntu 18.04+ or similar Linux distro
- Apache/Nginx + MySQL/PostgreSQL
- Source VM disk (.vmdk, .qcow2)

### Steps

```bash
# 1. Define paths
SOURCE=/vmware/ubuntu-web-01.vmdk
TARGET=/vms/migrated/ubuntu-web-01.qcow2

# 2. Migrate with database-aware mode
hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --format qcow2 \
    --fix-all \
    --prepare-databases \
    --verbose

# 3. Validate including database checks
hyper2kvm validate $TARGET \
    --check-boot \
    --check-fstab \
    --check-services \
    --check-network \
    --check-databases \
    --report /reports/web-server-validation.json

# 4. Import to libvirt
virt-install \
    --name ubuntu-web-01 \
    --memory 4096 \
    --vcpus 2 \
    --disk $TARGET,bus=virtio \
    --network bridge=br0,model=virtio \
    --graphics none \
    --console pty,target_type=serial \
    --os-variant ubuntu22.04 \
    --import
```

### Post-Migration Verification

```bash
# Start VM
virsh start ubuntu-web-01

# Connect via console
virsh console ubuntu-web-01

# Inside VM: verify services
systemctl status apache2
systemctl status mysql

# Test web server
curl http://localhost
```

### Troubleshooting

**Issue**: fstab errors, VM drops to emergency mode
```bash
# Solution: Re-stabilize fstab
hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --stabilize-fstab \
    --force
```

**Issue**: Apache fails to start
```bash
# Inside VM: check Apache config
apachectl configtest

# Check for renamed network interfaces
ip addr show

# Update Apache VirtualHost configs if needed
```

---

## 3. Database Server Migration

**Scenario**: Migrate PostgreSQL database server with minimal downtime
**Duration**: 20-40 minutes (depending on DB size)
**Difficulty**: Intermediate

### Prerequisites
- PostgreSQL or MySQL/MariaDB
- Database backup (recommended)
- Maintenance window scheduled

### Steps

```bash
# 1. Pre-migration database backup (inside source VM)
# PostgreSQL
pg_dumpall > /backup/db-backup-$(date +%Y%m%d).sql

# MySQL
mysqldump --all-databases > /backup/db-backup-$(date +%Y%m%d).sql

# 2. Shutdown source VM gracefully
virsh shutdown source-db-server
# Wait for clean shutdown
sleep 30

# 3. Migrate with database preparation
SOURCE=/vms/source/db-server.qcow2
TARGET=/vms/migrated/db-server.qcow2

hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --format qcow2 \
    --fix-all \
    --prepare-databases \
    --database-type postgresql \
    --verbose

# 4. Validate including database checks
hyper2kvm validate $TARGET \
    --check-boot \
    --check-services \
    --check-databases \
    --full-check \
    --report /reports/db-server-validation.json

# 5. Import to libvirt
virt-install \
    --name db-server \
    --memory 16384 \
    --vcpus 8 \
    --disk $TARGET,bus=virtio,cache=writeback \
    --network bridge=br0,model=virtio \
    --os-variant rhel8.5 \
    --import

# 6. Start VM and verify database
virsh start db-server
```

### Post-Migration Verification

```bash
# Inside VM: verify PostgreSQL
sudo systemctl status postgresql
sudo -u postgres psql -c "SELECT version();"

# Verify database connectivity
sudo -u postgres psql -c "\l"

# Check database size (should match pre-migration)
sudo -u postgres psql -c "SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) AS size FROM pg_database;"
```

### Downtime Optimization

**For minimal downtime, use live migration**:
```bash
hyper2kvm live migrate $SOURCE \
    --target $TARGET \
    --provider vmware \
    --max-downtime 5 \
    --prepare-databases
```

Expected downtime: <5 seconds for memory switchover

---

## 4. Batch Migration of 50+ VMs

**Scenario**: Migrate entire datacenter (50 VMs) over weekend
**Duration**: 4-8 hours (depends on parallelism)
**Difficulty**: Intermediate

### Prerequisites
- List of VMs to migrate
- Sufficient storage for all VMs
- Network bandwidth for data transfer
- Maintenance window

### Steps

**1. Create batch configuration**:
```yaml
# batch-config.yaml
batch:
  name: "Datacenter Migration - Q1 2026"
  parallel_workers: 5
  snapshot_before_migration: true

migrations:
  - name: "web-server-01"
    source: "/vms/source/web-01.vmdk"
    target: "/vms/migrated/web-01.qcow2"
    priority: high
    options:
      fstab_mode: stabilize-all
      validate: true

  - name: "web-server-02"
    source: "/vms/source/web-02.vmdk"
    target: "/vms/migrated/web-02.qcow2"
    priority: high
    options:
      fstab_mode: stabilize-all
      validate: true

  - name: "app-server-01"
    source: "/vms/source/app-01.vhdx"
    target: "/vms/migrated/app-01.qcow2"
    priority: medium
    options:
      fstab_mode: stabilize-all
      prepare_databases: true
      database_type: "mysql"

  # ... 47 more VMs
```

**2. Execute batch migration**:
```bash
# Start batch migration
hyper2kvm batch execute batch-config.yaml \
    --parallel 5 \
    --validate-all \
    --compliance-report \
    --output-dir /reports/datacenter-migration

# Monitor progress
watch -n 10 'hyper2kvm batch status batch-config.yaml'
```

**3. Review summary report**:
```bash
# Generate summary
hyper2kvm batch report --format markdown > /reports/migration-summary.md

# Example output:
# Batch Migration Summary
# =======================
# Total VMs: 50
# Successful: 48
# Failed: 2
# Success Rate: 96%
# Total Duration: 6h 23m
```

### Handling Failures

```bash
# Retry failed migrations
hyper2kvm batch retry batch-config.yaml \
    --failed-only \
    --verbose

# Or rollback specific VMs
hyper2kvm rollback \
    --vm web-server-03 \
    --snapshot snapshot_20260127_080000
```

---

## 5. Live Migration with Minimal Downtime

**Scenario**: Migrate production app server with <5s downtime
**Duration**: 30-60 minutes
**Difficulty**: Advanced

### Prerequisites
- HyperSDK installed (`pip install hypersdk`)
- VMware vCenter or Hyper-V host access
- Running VM (will stay online during migration)
- Network connectivity to source hypervisor

### Steps

**1. Analyze feasibility**:
```bash
# Check if VM is suitable for live migration
hyper2kvm live analyze /vms/prod-app.vmdk

# Expected output:
# Live Migration Feasibility Analysis
# ====================================
# VM: prod-app
# Estimated Downtime: 3.2s
# Confidence: 95%
# Recommendation: EXCELLENT - Highly recommended for live migration
#
# Blockers: None
# Warnings: None
```

**2. Execute live migration**:
```bash
hyper2kvm live migrate /vms/prod-app.vmdk \
    --target /vms/migrated/prod-app.qcow2 \
    --provider vmware \
    --vcenter-host vcenter.company.com \
    --vcenter-user admin@vsphere.local \
    --max-downtime 5 \
    --verbose

# Migration phases:
# [1/3] Pre-copy phase: Copying memory while VM runs (3m 45s)
# [2/3] Final switchover: Pausing VM and copying final delta (2.8s)
# [3/3] Post-migration: Starting VM on target (1.2s)
#
# Total downtime: 2.8s ✓
```

**3. Validate migrated VM**:
```bash
hyper2kvm validate /vms/migrated/prod-app.qcow2 \
    --check-all \
    --full-check \
    --report /reports/live-migration-validation.json
```

**4. Cutover production traffic**:
```bash
# Start VM in KVM
virsh start prod-app

# Update DNS or load balancer to point to new IP
# Monitor application logs for errors
```

### Rollback Plan

```bash
# If issues arise, rollback is instant (VM still running on source)
hyper2kvm live rollback /vms/prod-app.vmdk

# Or manually:
# 1. Stop KVM VM
# 2. Resume source VM
# 3. Revert DNS/load balancer changes
```

---

## 6. DR Testing from Veeam Backup

**Scenario**: Test disaster recovery by restoring from Veeam backup
**Duration**: 20-40 minutes
**Difficulty**: Intermediate

### Prerequisites
- Veeam Backup & Replication repository access
- Veeam backup files (.vbk, .vib)
- Test network isolated from production

### Steps

**1. List available backups**:
```bash
hyper2kvm backup list \
    --source veeam:///backups/veeam-repo \
    --format table

# Output:
# VM Name       | Backup Date         | Type        | Size
# --------------|---------------------|-------------|-------
# prod-app-01   | 2026-01-26 02:00:00 | Full (VBK)  | 45 GB
# prod-app-01   | 2026-01-27 02:00:00 | Incr (VIB)  | 8 GB
# prod-web-01   | 2026-01-26 02:00:00 | Full (VBK)  | 32 GB
```

**2. Restore from backup**:
```bash
hyper2kvm backup restore \
    --source veeam:///backups/veeam-repo \
    --vm prod-app-01 \
    --target /vms/dr-test/prod-app-01.qcow2 \
    --date 2026-01-27 \
    --apply-fixes \
    --verbose

# Restore process:
# [1/4] Extracting VMDK from Veeam backup
# [2/4] Converting VMDK to QCOW2
# [3/4] Applying migration fixes
# [4/4] Creating DR test environment
```

**3. Run DR validation**:
```bash
hyper2kvm validate /vms/dr-test/prod-app-01.qcow2 \
    --check-all \
    --check-databases \
    --check-services \
    --full-check \
    --report /reports/dr-test-prod-app-01.json
```

**4. Start DR test VM**:
```bash
virt-install \
    --name dr-test-prod-app-01 \
    --memory 8192 \
    --vcpus 4 \
    --disk /vms/dr-test/prod-app-01.qcow2,bus=virtio \
    --network network=dr-test-network,model=virtio \
    --os-variant rhel8.5 \
    --import
```

**5. Verify application**:
```bash
# Inside VM: check application
systemctl status app-service
curl http://localhost:8080/health

# Test database connectivity
psql -U app_user -d app_db -c "SELECT count(*) FROM users;"
```

**6. Cleanup DR test**:
```bash
# Destroy test VM
virsh destroy dr-test-prod-app-01
virsh undefine dr-test-prod-app-01

# Remove test disk
rm /vms/dr-test/prod-app-01.qcow2
```

---

## 7. VM to Kubernetes Migration

**Scenario**: Extract Docker containers from VM and deploy to Kubernetes
**Duration**: 45-90 minutes
**Difficulty**: Advanced

### Prerequisites
- VM running Docker/Podman
- Kubernetes cluster access
- Container registry

### Steps

**1. Extract containers from VM**:
```bash
hyper2kvm container extract /vms/docker-host.qcow2 \
    --output-dir /k8s/manifests/app-stack \
    --generate-manifests \
    --registry docker.io/mycompany \
    --namespace production

# Extraction output:
# Found 3 containers:
#   - nginx:1.21 (web-frontend)
#   - app:v2.3 (api-backend)
#   - redis:7.0 (cache)
#
# Generated Kubernetes manifests:
#   - deployments/web-frontend.yaml
#   - deployments/api-backend.yaml
#   - deployments/cache.yaml
#   - services/web-frontend-svc.yaml
#   - services/api-backend-svc.yaml
#   - configmaps/app-config.yaml
#   - secrets/app-secrets.yaml (base64 encoded)
```

**2. Review generated manifests**:
```bash
ls -R /k8s/manifests/app-stack/

# /k8s/manifests/app-stack/:
# deployments/
# services/
# configmaps/
# secrets/
# ingress/
```

**3. Customize manifests (optional)**:
```bash
# Edit deployment replicas
vim /k8s/manifests/app-stack/deployments/api-backend.yaml

# Update service type (ClusterIP, NodePort, LoadBalancer)
vim /k8s/manifests/app-stack/services/web-frontend-svc.yaml
```

**4. Deploy to Kubernetes**:
```bash
# Create namespace
kubectl create namespace production

# Apply manifests
kubectl apply -f /k8s/manifests/app-stack/ -n production

# Verify deployment
kubectl get all -n production
```

**5. Verify application**:
```bash
# Check pod status
kubectl get pods -n production

# Check logs
kubectl logs -n production deployment/api-backend

# Test service
kubectl port-forward -n production svc/web-frontend 8080:80
curl http://localhost:8080
```

---

## 8. Domain Controller Migration

**Scenario**: Migrate Windows Server Active Directory Domain Controller
**Duration**: 30-60 minutes
**Difficulty**: Advanced

### Prerequisites
- Windows Server 2016+ Domain Controller
- Additional DC for redundancy (recommended)
- Maintenance window
- AD database backup

### Steps

**1. Pre-migration tasks (in source VM)**:
```powershell
# Check AD health
dcdiag /v

# Backup AD database
wbadmin start systemstatebackup -backupTarget:D:\ADBackup

# Verify replication (if multiple DCs)
repadmin /showrepl
```

**2. Migrate VM**:
```bash
SOURCE=/vms/source/dc01.vhdx
TARGET=/vms/migrated/dc01.qcow2

hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --format qcow2 \
    --fix-all \
    --preserve-sid \
    --verbose
```

**3. Validate migration**:
```bash
hyper2kvm validate $TARGET \
    --check-boot \
    --check-services \
    --check-network \
    --report /reports/dc01-validation.json
```

**4. Import and start VM**:
```bash
virt-install \
    --name dc01 \
    --memory 4096 \
    --vcpus 2 \
    --disk $TARGET,bus=virtio \
    --network bridge=br0,model=virtio \
    --os-variant win2k19 \
    --import
```

**5. Post-migration verification (in migrated VM)**:
```powershell
# Verify AD services
Get-Service NTDS, DNS, Kdc, Netlogon | Select Name, Status

# Check replication
repadmin /replsummary

# Verify FSMO roles (if primary DC)
netdom query fsmo

# Test AD functionality
Get-ADDomainController
Get-ADUser -Filter *
```

### Troubleshooting

**Issue**: AD replication fails
```powershell
# Solution: Force replication
repadmin /syncall /AdeP

# Check for errors
dcdiag /test:replications
```

**Issue**: Clients cannot authenticate
```powershell
# Solution: Verify DNS
nslookup dc01.domain.com

# Verify SRV records
nslookup -type=SRV _ldap._tcp.dc._msdcs.domain.com
```

---

## 9. Legacy Application Server

**Scenario**: Migrate old Linux server (CentOS 6) with legacy apps
**Duration**: 30-50 minutes
**Difficulty**: Intermediate

### Prerequisites
- Legacy OS (EOL or near-EOL)
- Custom/proprietary applications
- Documentation of dependencies

### Steps

**1. Inventory legacy system (before migration)**:
```bash
# Inside source VM: document installed packages
rpm -qa > /backup/installed-packages.txt

# Document running services
systemctl list-units --type=service --state=running > /backup/services.txt

# Document network configuration
ip addr show > /backup/network-config.txt
ifconfig > /backup/ifconfig.txt
```

**2. Migrate with compatibility mode**:
```bash
SOURCE=/vms/legacy/centos6-app.vmdk
TARGET=/vms/migrated/centos6-app.qcow2

hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --format qcow2 \
    --fix-bootloader \
    --fix-network \
    --legacy-mode \
    --preserve-network-config \
    --verbose
```

**3. Validate migration**:
```bash
hyper2kvm validate $TARGET \
    --check-boot \
    --check-fstab \
    --check-services \
    --report /reports/legacy-app-validation.json
```

**4. Import to libvirt**:
```bash
virt-install \
    --name centos6-app \
    --memory 2048 \
    --vcpus 2 \
    --disk $TARGET,bus=virtio \
    --network bridge=br0,model=virtio \
    --os-variant centos6.10 \
    --import
```

**5. Post-migration verification**:
```bash
# Start VM
virsh start centos6-app

# Inside VM: verify services
service legacy-app status

# Test application
curl http://localhost:8080/api/health
```

### Troubleshooting

**Issue**: Legacy application fails to start
```bash
# Solution: Check dependencies
ldd /opt/legacy-app/bin/app-server

# Check for missing libraries
cat /var/log/messages | grep -i error

# May need to install compat libraries
yum install compat-libstdc++-33
```

---

## 10. High-Availability Cluster Migration

**Scenario**: Migrate 2-node HA cluster (e.g., Pacemaker/Corosync)
**Duration**: 2-4 hours
**Difficulty**: Advanced

### Prerequisites
- HA cluster with 2+ nodes
- Shared storage or DRBD replication
- Maintenance window
- Cluster configuration backup

### Steps

**1. Backup cluster configuration**:
```bash
# On active node
pcs config backup cluster-backup
cibadmin --query > /backup/cluster-config.xml
```

**2. Put cluster in maintenance mode**:
```bash
pcs property set maintenance-mode=true
```

**3. Migrate node 1**:
```bash
# Shutdown node 1
ssh node1 "shutdown -h now"

# Migrate node 1
hyper2kvm migrate /vms/cluster-node1.vmdk \
    --target /vms/migrated/cluster-node1.qcow2 \
    --fix-all \
    --preserve-network-config
```

**4. Start node 1 in KVM**:
```bash
virsh start cluster-node1

# Wait for node to boot
sleep 60

# Verify node is online
ssh cluster-node1 "hostname"
```

**5. Migrate node 2**:
```bash
# Shutdown node 2
ssh node2 "shutdown -h now"

# Migrate node 2
hyper2kvm migrate /vms/cluster-node2.vmdk \
    --target /vms/migrated/cluster-node2.qcow2 \
    --fix-all \
    --preserve-network-config

# Start node 2
virsh start cluster-node2
```

**6. Restore cluster**:
```bash
# On node 1: verify cluster communication
pcs status

# Restore cluster from maintenance
pcs property set maintenance-mode=false

# Verify resources
pcs resource status

# Verify quorum
pcs quorum status
```

### Validation

```bash
# Verify cluster is healthy
pcs status

# Test failover
pcs node standby cluster-node1
# Verify resources migrate to node 2
pcs status

# Resume node 1
pcs node unstandby cluster-node1
```

---

## Common Patterns

### Pre-Migration Checklist

```bash
# 1. Document current state
virsh dumpxml <vm-name> > /backup/vm-definition.xml
qemu-img info /path/to/disk.qcow2 > /backup/disk-info.txt

# 2. Create snapshot
hyper2kvm snapshot create /path/to/disk.qcow2 --checksum

# 3. Backup critical data (inside VM)
# - Database dumps
# - Configuration files
# - Application data
```

### Post-Migration Validation

```bash
# Always run validation
hyper2kvm validate $TARGET \
    --check-boot \
    --check-fstab \
    --check-services \
    --check-network \
    --full-check

# Check validation report
cat /reports/validation-report.md
```

### Rollback Procedure

```bash
# If migration fails
hyper2kvm rollback \
    --snapshot snapshot_20260127_080000 \
    --verify-checksum \
    --validate

# Or manual rollback
cp /snapshots/original.qcow2 /vms/restored.qcow2
```

---

## See Also

- **[Beginner Tutorial](../tutorials/01-beginner-migration.md)**: Step-by-step first migration
- **[OS-Specific Recipes](02-os-specific.md)**: Operating system specific migrations
- **[Application Recipes](03-application-specific.md)**: Application-specific migrations
- **[Troubleshooting Guide](../guides/troubleshooting.md)**: Common issues and solutions

---

**Last Updated**: March 2026
