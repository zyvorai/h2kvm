# Intermediate Tutorial: Batch Migration and Automation

**Duration**: 1-2 hours
**Difficulty**: Intermediate
**Prerequisites**: Completed [Beginner Tutorial](01-beginner-migration.md)

---

## What You'll Learn

By the end of this tutorial, you will:
- ✅ Execute batch migrations of multiple VMs
- ✅ Create reusable migration configurations
- ✅ Automate migration workflows
- ✅ Monitor migration progress
- ✅ Generate compliance reports
- ✅ Handle failed migrations gracefully

---

## Batch Migration Basics

### Scenario

You need to migrate 10 web servers from VMware to KVM over a weekend maintenance window.

**VMs**:
- web-01 through web-10 (Ubuntu 22.04, Apache, MySQL)
- Priority: High (customer-facing)
- Downtime window: 8 hours

---

## Step 1: Create Batch Configuration

Create a YAML configuration file for repeatable migrations.

**Create `batch-web-servers.yaml`**:
```yaml
# Batch migration manifest
# Run: h2kvmctl --batch-manifest batch-web-servers.yaml --batch-parallel 3

# Common settings for all VMs
defaults:
  cmd: local
  out_format: qcow2
  fstab_mode: stabilize-all
  regen_initramfs: true
  compress: true

# Individual VM configurations
migrations:
  - name: "web-01"
    vmdk: "/vmware/vms/web-01.vmdk"
    to_output: "/kvm/vms/web-01.qcow2"
    memory: 4096
    vcpus: 2

  - name: "web-02"
    vmdk: "/vmware/vms/web-02.vmdk"
    to_output: "/kvm/vms/web-02.qcow2"
    memory: 4096
    vcpus: 2

  - name: "web-03"
    vmdk: "/vmware/vms/web-03.vmdk"
    to_output: "/kvm/vms/web-03.qcow2"
    memory: 4096
    vcpus: 2

  # ... web-04 through web-10
  - name: "web-10"
    vmdk: "/vmware/vms/web-10.vmdk"
    to_output: "/kvm/vms/web-10.qcow2"
    memory: 4096
    vcpus: 2
```

---

## Step 2: Validate Configuration

Before executing, validate your batch configuration.

```bash
# Validate configuration syntax
hyper2kvm batch validate batch-web-servers.yaml

# Expected output:
# ✓ Configuration valid
# ✓ All source paths exist
# ✓ All target directories writable
# ✓ Sufficient disk space available
#
# Summary:
#   Total VMs: 10
#   Estimated duration: 2h 30m (with 3 parallel workers)
#   Estimated storage: 450 GB
```

---

## Step 3: Dry Run

Execute a dry run to see what would happen without actually migrating.

```bash
hyper2kvm batch execute batch-web-servers.yaml \
    --dry-run \
    --verbose

# Output:
# [DRY RUN] Batch Migration: Web Server Migration - January 2026
#
# Would execute:
#   [Worker 1] web-01: /vmware/vms/web-01.vmdk → /kvm/vms/web-01.qcow2
#   [Worker 2] web-02: /vmware/vms/web-02.vmdk → /kvm/vms/web-02.qcow2
#   [Worker 3] web-03: /vmware/vms/web-03.vmdk → /kvm/vms/web-03.qcow2
#
# Queue:
#   web-04, web-05, web-06, web-07, web-08, web-09, web-10
#
# Snapshots would be created in: /var/lib/hyper2kvm/snapshots
# Reports would be generated in: /var/lib/hyper2kvm/reports
```

---

## Step 4: Execute Batch Migration

Start the batch migration.

```bash
# Execute batch migration
hyper2kvm batch execute batch-web-servers.yaml \
    --parallel 3 \
    --validate-all \
    --compliance-report \
    --output-dir /reports/web-migration \
    --verbose

# Migration starts...
```

### Real-Time Progress

```bash
# In another terminal, monitor progress
watch -n 10 'hyper2kvm batch status batch-web-servers.yaml'

# Output:
# Batch Migration Status
# ======================
# Name: Web Server Migration - January 2026
# Started: 2026-01-27 08:00:00
# Elapsed: 45m 23s
#
# Overall Progress: 60% (6/10 complete)
#
# Active Migrations (3):
#   [Worker 1] web-07: Converting disk (45%)
#   [Worker 2] web-08: Applying fixes (bootloader)
#   [Worker 3] web-09: Validating migration
#
# Completed (6):
#   ✓ web-01: SUCCESS (12m 34s)
#   ✓ web-02: SUCCESS (13m 01s)
#   ✓ web-03: SUCCESS (11m 45s)
#   ✓ web-04: SUCCESS (14m 12s)
#   ✓ web-05: SUCCESS (12m 58s)
#   ✓ web-06: SUCCESS (13m 22s)
#
# Queued (1):
#   web-10
#
# Failed (0):
#   None
#
# Estimated completion: 09:15:00
```

---

## Step 5: Handle Failures

Suppose web-08 fails during migration.

### Investigate Failure

```bash
# Check detailed error for web-08
hyper2kvm batch logs --vm web-08 --tail 100

# Output:
# [ERROR] Migration failed for web-08
# [ERROR] Cause: Insufficient disk space on /kvm/vms
# [ERROR] Required: 45 GB, Available: 12 GB
# [ERROR] Rollback initiated: restoring snapshot_web08_080523
# [INFO] Rollback completed successfully
```

### Resolve Issue

```bash
# Free up disk space
df -h /kvm/vms

# Delete old snapshots or move files
rm -rf /kvm/vms/old-snapshots/*

# Verify space
df -h /kvm/vms
# /kvm/vms  500G  400G  100G  80% /kvm/vms
```

### Retry Failed Migration

```bash
# Retry only failed VMs
hyper2kvm batch retry batch-web-servers.yaml \
    --failed-only \
    --verbose

# Or retry specific VM
hyper2kvm batch retry batch-web-servers.yaml \
    --vm web-08
```

---

## Step 6: Review Results

After batch completion, review the summary report.

### Generate Summary

```bash
hyper2kvm batch report \
    --config batch-web-servers.yaml \
    --format markdown \
    --output /reports/web-migration/summary.md
```

### Summary Report

```markdown
# Batch Migration Summary

**Name**: Web Server Migration - January 2026
**Started**: 2026-01-27 08:00:00
**Completed**: 2026-01-27 10:45:32
**Duration**: 2h 45m 32s

## Overall Statistics

- **Total VMs**: 10
- **Successful**: 10
- **Failed**: 0 (1 retry)
- **Success Rate**: 100%

## Performance Metrics

- **Average Migration Time**: 14m 23s
- **Total Data Migrated**: 485 GB
- **Average Throughput**: 178 MB/s
- **Parallel Workers**: 3

## Individual VM Results

| VM Name | Status | Duration | Source Size | Target Size | Validation |
|---------|--------|----------|-------------|-------------|------------|
| web-01  | ✓ SUCCESS | 12m 34s | 45 GB | 38 GB | PASS |
| web-02  | ✓ SUCCESS | 13m 01s | 47 GB | 39 GB | PASS |
| web-03  | ✓ SUCCESS | 11m 45s | 42 GB | 35 GB | PASS |
| web-04  | ✓ SUCCESS | 14m 12s | 50 GB | 42 GB | PASS |
| web-05  | ✓ SUCCESS | 12m 58s | 46 GB | 38 GB | PASS |
| web-06  | ✓ SUCCESS | 13m 22s | 48 GB | 40 GB | PASS |
| web-07  | ✓ SUCCESS | 15m 05s | 52 GB | 44 GB | PASS |
| web-08  | ✓ SUCCESS | 16m 42s | 51 GB | 43 GB | PASS (retry) |
| web-09  | ✓ SUCCESS | 14m 38s | 49 GB | 41 GB | PASS |
| web-10  | ✓ SUCCESS | 13m 15s | 45 GB | 37 GB | PASS |

## Compliance Report

All migrations completed with:
- ✓ Pre-migration snapshots created
- ✓ Post-migration validation passed
- ✓ Audit trail generated
- ✓ Rollback capability available
```

---

## Automation Workflows

### Cron-Based Scheduled Migration

Migrate VMs during off-peak hours automatically.

**Create migration script**:
```bash
#!/bin/bash
# /scripts/automated-migration.sh

LOG_DIR=/var/log/hyper2kvm
REPORT_DIR=/reports/automated-migrations
DATE=$(date +%Y%m%d_%H%M%S)

# Create log file
exec 1>>"$LOG_DIR/migration-$DATE.log" 2>&1

echo "Starting automated migration: $DATE"

# Execute batch migration
hyper2kvm batch execute /etc/hyper2kvm/nightly-migrations.yaml \
    --parallel 2 \
    --validate-all \
    --output-dir "$REPORT_DIR/$DATE"

# Check exit status
if [ $? -eq 0 ]; then
    echo "Migration completed successfully"

    # Send success notification
    mail -s "Migration Success: $DATE" admin@company.com < "$REPORT_DIR/$DATE/summary.md"
else
    echo "Migration failed"

    # Send failure notification with logs
    mail -s "Migration FAILED: $DATE" admin@company.com < "$LOG_DIR/migration-$DATE.log"
fi
```

**Schedule with cron**:
```bash
# Edit crontab
crontab -e

# Add entry: Run every Saturday at 2 AM
0 2 * * 6 /scripts/automated-migration.sh
```

---

### CI/CD Integration

Integrate migration into CI/CD pipeline.

**GitLab CI Example** (`.gitlab-ci.yml`):
```yaml
stages:
  - validate
  - migrate
  - verify

validate_config:
  stage: validate
  script:
    - hyper2kvm batch validate migrations/batch-config.yaml
  only:
    - main

execute_migration:
  stage: migrate
  script:
    - hyper2kvm batch execute migrations/batch-config.yaml --parallel 5
  artifacts:
    paths:
      - reports/
    expire_in: 30 days
  only:
    - main
  when: manual

verify_migration:
  stage: verify
  script:
    - hyper2kvm batch report --format json > report.json
    - python3 scripts/check-success-rate.py report.json
  dependencies:
    - execute_migration
  only:
    - main
```

---

### Ansible Playbook Integration

Use Ansible for orchestrated migrations.

**Create `migrate-vms.yml`**:
```yaml
---
- name: Migrate VMs to KVM
  hosts: kvm-host
  become: yes
  tasks:
    - name: Install Hyper2KVM
      pip:
        name: hyper2kvm
        state: latest

    - name: Copy batch configuration
      copy:
        src: batch-config.yaml
        dest: /tmp/batch-config.yaml

    - name: Execute batch migration
      command: >
        hyper2kvm batch execute /tmp/batch-config.yaml
        --parallel 3
        --validate-all
        --output-dir /reports/ansible-migration
      register: migration_result

    - name: Display migration summary
      debug:
        msg: "{{ migration_result.stdout }}"

    - name: Generate compliance report
      command: hyper2kvm batch report --format pdf --output /reports/compliance.pdf
      when: migration_result.rc == 0

    - name: Send notification
      mail:
        subject: "Migration Complete"
        to: admin@company.com
        body: "Batch migration completed successfully. See attached report."
        attach: /reports/compliance.pdf
      when: migration_result.rc == 0
```

**Execute playbook**:
```bash
ansible-playbook migrate-vms.yml -i inventory.ini
```

---

## Configuration Templates

### Template for Web Servers

**`templates/web-server-template.yaml`**:
```yaml
batch:
# Batch migration template
defaults:
  cmd: local
  out_format: qcow2
  memory: 4096
  vcpus: 2
  fstab_mode: stabilize-all
  regen_initramfs: true
  compress: true

migrations:
  # Will be populated dynamically
  []
```

### Generate Configurations Dynamically

**Script**: `generate-batch-config.sh`
```bash
#!/bin/bash
# Generate batch config from VM inventory

TEMPLATE=templates/web-server-template.yaml
OUTPUT=batch-config.yaml
VM_LIST=vm-inventory.txt

# Start with template
cp $TEMPLATE $OUTPUT

# Add VMs from inventory
while IFS=, read -r name source target; do
    cat >> $OUTPUT <<EOF
  - name: "$name"
    vmdk: "$source"
    to_output: "$target"

EOF
done < $VM_LIST

echo "Generated $OUTPUT with $(wc -l < $VM_LIST) VMs"
```

**VM Inventory** (`vm-inventory.txt`):
```
web-01,/vmware/web-01.vmdk,/kvm/web-01.qcow2
web-02,/vmware/web-02.vmdk,/kvm/web-02.qcow2
web-03,/vmware/web-03.vmdk,/kvm/web-03.qcow2
```

---

## Monitoring and Alerting

### Prometheus Metrics Export

```bash
# Export metrics for Prometheus
hyper2kvm batch metrics \
    --config batch-config.yaml \
    --format prometheus \
    --output /metrics/hyper2kvm.prom

# Example metrics:
# hyper2kvm_migrations_total 10
# hyper2kvm_migrations_successful 10
# hyper2kvm_migrations_failed 0
# hyper2kvm_migration_duration_seconds{vm="web-01"} 754
# hyper2kvm_migration_data_gb{vm="web-01"} 45
```

### Grafana Dashboard

Import the Hyper2KVM Grafana dashboard for visualization:
- Migration success rate over time
- Average migration duration
- Data throughput
- Active migrations
- Failed migrations

---

## Best Practices

### 1. Test Configuration First

```bash
# Always validate before executing
hyper2kvm batch validate batch-config.yaml

# Run dry-run to preview
hyper2kvm batch execute batch-config.yaml --dry-run
```

### 2. Use Appropriate Parallelism

```yaml
# For fast storage (NVMe, local SSD): 4-8 workers
parallel_workers: 6

# For network storage (NFS, iSCSI): 2-3 workers
parallel_workers: 2

# For slow storage (HDD RAID): 1-2 workers
parallel_workers: 1
```

### 3. Prioritize Critical VMs

```yaml
migrations:
  - name: "production-db"
    priority: critical  # Migrate first

  - name: "dev-server"
    priority: low  # Migrate last
```

### 4. Enable Snapshots for Safety

```yaml
batch:
  snapshot_before_migration: true  # Always recommended
```

### 5. Generate Compliance Reports

```yaml
batch:
  generate_compliance_report: true
  compliance_requirements:
    - snapshot_created
    - validation_passed
    - audit_trail_generated
```

---

## Troubleshooting

### Issue: Batch hangs during execution

**Solution**:
```bash
# Check active workers
hyper2kvm batch status batch-config.yaml

# Cancel stuck migration
hyper2kvm batch cancel --vm web-05

# Resume batch
hyper2kvm batch resume batch-config.yaml
```

### Issue: Out of disk space

**Solution**:
```bash
# Check disk usage
df -h /kvm/vms

# Clean old snapshots
hyper2kvm snapshot cleanup --older-than 7d

# Adjust target compression
# In config: format: qcow2 with compression
```

### Issue: Network timeouts for remote sources

**Solution**:
```yaml
# In batch config, increase timeout
defaults:
  timeout: 3600  # 1 hour timeout
```

---

## Next Steps

Congratulations! You've mastered batch migration and automation workflows.

**Continue Learning**:
- **[Advanced Tutorial](03-advanced-features.md)**: Live migration, DR testing
- **[Enterprise Tutorial](04-enterprise-deployment.md)**: Production deployment
- **[API Reference](../api/cli-api.md)**: Programmatic batch migrations

**Explore Features**:
- **[Compliance & Audit](../features/compliance-audit.md)**: Compliance reporting
- **[Rollback Framework](../features/rollback-framework.md)**: Recover from failures
- **[Migration Validation](../features/migration-validation.md)**: Deep validation

---

## Summary Checklist

- ✅ Created batch migration configuration
- ✅ Validated configuration before execution
- ✅ Executed batch migration with parallelism
- ✅ Monitored migration progress in real-time
- ✅ Handled failed migrations gracefully
- ✅ Generated summary and compliance reports
- ✅ Automated migrations with cron/CI/CD
- ✅ Used configuration templates for repeatability

**Time to completion**: 1-2 hours ✅

**Next Tutorial**: [Advanced Features](03-advanced-features.md)
