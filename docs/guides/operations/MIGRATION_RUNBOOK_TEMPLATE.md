# Migration Runbook Template

Customizable template for creating migration runbooks for your specific VM migrations.

---

## How to Use This Template

1. **Copy this template** for each migration project
2. **Fill in all [PLACEHOLDER] values** with your specific information
3. **Customize** sections based on your requirements
4. **Review** with stakeholders before migration
5. **Follow** during execution
6. **Update** with actual times and results

---

## Migration Overview

### Project Information

| Field | Value |
|-------|-------|
| **Project Name** | [PROJECT_NAME] |
| **Migration ID** | [MIG-YYYY-MM-DD-##] |
| **Prepared By** | [YOUR_NAME] |
| **Date Prepared** | [YYYY-MM-DD] |
| **Last Updated** | [YYYY-MM-DD] |
| **Status** | [DRAFT/APPROVED/IN-PROGRESS/COMPLETE] |

### Migration Schedule

| Phase | Planned Date/Time | Actual Date/Time |
|-------|-------------------|------------------|
| **Pre-Migration Testing** | [YYYY-MM-DD HH:MM] | |
| **Migration Execution** | [YYYY-MM-DD HH:MM] | |
| **Validation** | [YYYY-MM-DD HH:MM] | |
| **Production Cutover** | [YYYY-MM-DD HH:MM] | |

### VM Inventory

| VM Name | OS | Size (GB) | Priority | Dependencies |
|---------|----|-----------| ---------|--------------|
| [VM-NAME-1] | [OS-VERSION] | [SIZE] | [HIGH/MEDIUM/LOW] | [LIST-DEPS] |
| [VM-NAME-2] | [OS-VERSION] | [SIZE] | [HIGH/MEDIUM/LOW] | [LIST-DEPS] |
| [VM-NAME-3] | [OS-VERSION] | [SIZE] | [HIGH/MEDIUM/LOW] | [LIST-DEPS] |

**Total VMs**: [NUMBER]
**Total Size**: [SIZE] GB

---

## Pre-Migration Preparation

### 1. Environment Setup

**Source Environment**:
- **Platform**: [VMware vSphere / ESXi / Hyper-V / Other]
- **Version**: [VERSION]
- **Location**: [DATACENTER/LOCATION]
- **Access Method**: [SSH / vCenter API / Web UI]

**Target Environment**:
- **Platform**: [KVM / QEMU / libvirt]
- **Version**: [VERSION]
- **Location**: [DATACENTER/LOCATION]
- **Migration Host**: [HOSTNAME/IP]

**Migration Server Details**:
```
Hostname: [MIGRATION-SERVER]
IP Address: [IP-ADDRESS]
OS: [OS-VERSION]
CPUs: [NUMBER]
Memory: [SIZE] GB
Disk Space: [SIZE] GB
Network: [BANDWIDTH] Mbps
```

### 2. Access Requirements

**Source Access**:
- [ ] ESXi/vCenter credentials: `[USERNAME]`
- [ ] SSH key configured: `[PATH-TO-KEY]`
- [ ] Network connectivity verified
- [ ] Firewall rules configured

**Target Access**:
- [ ] KVM host access: `[USERNAME]@[HOSTNAME]`
- [ ] libvirt permissions granted
- [ ] Storage paths created: `[OUTPUT-DIR]`
- [ ] Network configured

### 3. Software Installation

- [ ] Hyper2KVM installed: Version `[VERSION]`
- [ ] Dependencies verified: qemu-img `[VERSION]`
- [ ] Pre-flight validation passed
- [ ] Test migration successful

### 4. Backup Verification

| VM | Backup Date | Backup Location | Verified |
|----|-------------|-----------------|----------|
| [VM-NAME-1] | [YYYY-MM-DD] | [LOCATION] | [ ] |
| [VM-NAME-2] | [YYYY-MM-DD] | [LOCATION] | [ ] |
| [VM-NAME-3] | [YYYY-MM-DD] | [LOCATION] | [ ] |

### 5. Stakeholder Communication

| Role | Name | Email | Phone | Notified |
|------|------|-------|-------|----------|
| **Project Manager** | [NAME] | [EMAIL] | [PHONE] | [ ] |
| **Technical Lead** | [NAME] | [EMAIL] | [PHONE] | [ ] |
| **Application Owner** | [NAME] | [EMAIL] | [PHONE] | [ ] |
| **Operations Team** | [NAME] | [EMAIL] | [PHONE] | [ ] |

**Notification Template**:
```
Subject: VM Migration - [PROJECT_NAME] - [DATE]

Dear Team,

This is to inform you that we will be migrating the following VMs:
- [VM-LIST]

Schedule:
- Start: [START-TIME]
- Expected completion: [END-TIME]
- Expected downtime: [DURATION]

Impact:
- [DESCRIBE-IMPACT]

Rollback plan:
- [DESCRIBE-ROLLBACK]

Contact for issues:
- [CONTACT-INFO]
```

---

## Migration Execution Plan

### Phase 1: Pre-Migration Tasks (T-24 hours)

**Time**: [YYYY-MM-DD HH:MM]

- [ ] **Verify backups current**
  ```bash
  # Verify backup dates
  [BACKUP-VERIFICATION-COMMAND]
  ```

- [ ] **Final system checks**
  ```bash
  ./pre-flight-check.sh
  ```

- [ ] **Prepare configurations**
  - [ ] YAML files created: `[CONFIG-DIR]/*.yaml`
  - [ ] Configurations tested
  - [ ] Batch manifest ready (if applicable)

- [ ] **Team briefing**
  - [ ] Runbook reviewed
  - [ ] Roles assigned
  - [ ] Communication plan confirmed
  - [ ] Go/No-Go decision: [GO / NO-GO]

### Phase 2: Migration Execution

#### VM 1: [VM-NAME-1]

**Planned Start**: [HH:MM]
**Actual Start**: _______
**Actual End**: _______

**Pre-Migration**:
- [ ] Verify backup timestamp: _______
- [ ] Take final snapshot
- [ ] Record current state:
  ```
  IP Address: [IP]
  Services running: [SERVICE-LIST]
  ```

**Shutdown Source VM**:
```bash
# On VMware
ssh root@[ESXI-HOST] "vim-cmd vmsvc/power.off [VM-ID]"
# Verify powered off
ssh root@[ESXI-HOST] "vim-cmd vmsvc/power.getstate [VM-ID]"
```
- [ ] Shutdown time: _______
- [ ] Verified powered off

**Execute Migration**:
```bash
# Start migration
h2kvmctl --config /path/to/[VM-NAME-1].yaml 2>&1 | tee migration-[VM-NAME-1].log

# Monitor progress
tail -f migration-[VM-NAME-1].log
```
- [ ] Migration started: _______
- [ ] Progress: _____ %
- [ ] Migration completed: _______

**Configuration Used**:
```yaml
command: local
vmdk: [SOURCE-VMDK-PATH]
output_dir: [OUTPUT-DIR]
to_output: [VM-NAME-1].qcow2

# Options
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
compress: [true/false]

# [Add any special options]
```

**Validation**:
```bash
# Verify output
qemu-img info [OUTPUT-DIR]/[VM-NAME-1].qcow2
qemu-img check [OUTPUT-DIR]/[VM-NAME-1].qcow2
```
- [ ] File created successfully
- [ ] File size: _______ GB
- [ ] No corruption detected

**Boot Test**:
```bash
# Import to libvirt
virsh define [OUTPUT-DIR]/[VM-NAME-1].xml

# Start VM
virsh start [VM-NAME-1]

# Console access
virsh console [VM-NAME-1]
```
- [ ] VM boots successfully
- [ ] No kernel errors
- [ ] Filesystems mounted
- [ ] Network configured

**Application Validation**:
- [ ] [SERVICE-1] started
- [ ] [SERVICE-2] started
- [ ] [APPLICATION] accessible
- [ ] [DATABASE] responding

**Issues Encountered**:
```
[DESCRIBE ANY ISSUES]
```

**Resolution**:
```
[DESCRIBE RESOLUTION]
```

---

#### VM 2: [VM-NAME-2]

[Repeat same structure as VM 1]

---

#### VM 3: [VM-NAME-3]

[Repeat same structure as VM 1]

---

### Phase 3: Post-Migration Validation

**Time**: [HH:MM]

#### System Validation

For each VM:
- [ ] **[VM-NAME-1]**
  - [ ] Boot validated
  - [ ] Network tested
  - [ ] Services running
  - [ ] Applications functional
  - [ ] Performance acceptable

- [ ] **[VM-NAME-2]**
  - [ ] Boot validated
  - [ ] Network tested
  - [ ] Services running
  - [ ] Applications functional
  - [ ] Performance acceptable

- [ ] **[VM-NAME-3]**
  - [ ] Boot validated
  - [ ] Network tested
  - [ ] Services running
  - [ ] Applications functional
  - [ ] Performance acceptable

#### Integration Testing

- [ ] **Inter-VM connectivity**
  ```bash
  # Test VM-to-VM connectivity
  ping [VM-2] from [VM-1]
  ping [VM-3] from [VM-1]
  ```

- [ ] **External connectivity**
  ```bash
  # Test external access
  curl [EXTERNAL-SERVICE]
  ```

- [ ] **Database connectivity**
  ```bash
  # Test database connections
  [DB-TEST-COMMAND]
  ```

- [ ] **Application workflow**
  - [ ] [WORKFLOW-STEP-1]
  - [ ] [WORKFLOW-STEP-2]
  - [ ] [WORKFLOW-STEP-3]

#### Performance Validation

- [ ] **CPU usage**: _____ % (Expected: [EXPECTED]%)
- [ ] **Memory usage**: _____ GB (Expected: [EXPECTED] GB)
- [ ] **Disk I/O**: _____ MB/s (Expected: [EXPECTED] MB/s)
- [ ] **Network throughput**: _____ Mbps (Expected: [EXPECTED] Mbps)

**Performance Test Results**:
```bash
# Run performance tests
[PERFORMANCE-TEST-COMMAND]
```

Results:
```
[TEST-RESULTS]
```

### Phase 4: Production Cutover

**Planned Time**: [HH:MM]
**Actual Time**: _______

#### Network Cutover

- [ ] **Update DNS records**
  ```
  [VM-NAME-1]: [OLD-IP] → [NEW-IP]
  [VM-NAME-2]: [OLD-IP] → [NEW-IP]
  [VM-NAME-3]: [OLD-IP] → [NEW-IP]
  ```
  - [ ] DNS updated: _______
  - [ ] DNS propagation verified: _______

- [ ] **Update load balancer**
  ```bash
  [LOAD-BALANCER-UPDATE-COMMAND]
  ```
  - [ ] Load balancer updated: _______

- [ ] **Update firewall rules**
  ```bash
  [FIREWALL-UPDATE-COMMAND]
  ```
  - [ ] Firewall updated: _______

#### Application Cutover

- [ ] **Update connection strings**
  - [ ] Application servers updated
  - [ ] Database connection strings updated
  - [ ] API endpoints updated

- [ ] **Restart dependent services**
  ```bash
  [SERVICE-RESTART-COMMANDS]
  ```

#### Monitoring Cutover

- [ ] **Update monitoring**
  - [ ] [MONITORING-SYSTEM] updated
  - [ ] Alerts configured
  - [ ] Dashboards updated

- [ ] **Verify monitoring**
  - [ ] Metrics collecting
  - [ ] Alerts working
  - [ ] Dashboards showing data

#### Final Validation

- [ ] **End-to-end test**
  - [ ] User login successful
  - [ ] Application fully functional
  - [ ] No errors in logs

- [ ] **Stakeholder sign-off**
  - [ ] Application owner: _______ [NAME] [TIME]
  - [ ] Technical lead: _______ [NAME] [TIME]
  - [ ] Operations team: _______ [NAME] [TIME]

---

## Rollback Plan

### Decision Criteria

Rollback if:
- [ ] VM won't boot after 3 attempts
- [ ] Critical application functionality broken
- [ ] Performance degradation > 50%
- [ ] Data integrity issues detected
- [ ] Stakeholder requests rollback

**Decision Point**: [HH:MM]
**Decision Maker**: [NAME]

### Rollback Procedure

**Estimated Rollback Time**: [DURATION]

#### Step 1: Stop Migrated VMs

```bash
# Stop all migrated VMs
virsh shutdown [VM-NAME-1]
virsh shutdown [VM-NAME-2]
virsh shutdown [VM-NAME-3]

# Force if necessary
virsh destroy [VM-NAME-1]
virsh destroy [VM-NAME-2]
virsh destroy [VM-NAME-3]
```
- [ ] All migrated VMs stopped: _______

#### Step 2: Restore Source VMs

```bash
# On VMware
ssh root@[ESXI-HOST] "vim-cmd vmsvc/power.on [VM-ID-1]"
ssh root@[ESXI-HOST] "vim-cmd vmsvc/power.on [VM-ID-2]"
ssh root@[ESXI-HOST] "vim-cmd vmsvc/power.on [VM-ID-3]"
```
- [ ] Source VMs powered on: _______

#### Step 3: Verify Source VMs

- [ ] [VM-NAME-1] boots successfully
- [ ] [VM-NAME-2] boots successfully
- [ ] [VM-NAME-3] boots successfully
- [ ] All services running
- [ ] Applications functional

#### Step 4: Revert Network Changes

- [ ] DNS records reverted
- [ ] Load balancer reverted
- [ ] Firewall rules reverted
- [ ] Monitoring reverted

#### Step 5: Notify Stakeholders

**Rollback Notification**:
```
Subject: Migration Rollback - [PROJECT_NAME]

The migration has been rolled back due to:
[REASON]

All systems have been restored to source environment.

Current status: [STATUS]

Next steps: [NEXT-STEPS]
```

**Rollback Completed**: _______

---

## Post-Migration Tasks

### Immediate (Within 24 Hours)

- [ ] **Monitor migrated VMs**
  - [ ] Check logs: _______
  - [ ] Monitor performance: _______
  - [ ] Review alerts: _______

- [ ] **Document lessons learned**
  ```
  What went well:
  [NOTES]

  What could be improved:
  [NOTES]

  Issues encountered:
  [NOTES]
  ```

- [ ] **Update documentation**
  - [ ] Update inventory
  - [ ] Update network diagrams
  - [ ] Update runbooks

### Short-Term (Within 1 Week)

- [ ] **Extended validation**
  - [ ] Full application testing
  - [ ] Performance baseline
  - [ ] Backup testing

- [ ] **Cleanup**
  - [ ] Archive migration files
  - [ ] Remove temporary configs
  - [ ] Document final state

### Long-Term (Within 1 Month)

- [ ] **Source decommission**
  - [ ] Plan decommission date: _______
  - [ ] Final backup
  - [ ] Power off source VMs
  - [ ] Release resources

- [ ] **Final documentation**
  - [ ] Complete runbook
  - [ ] Update knowledge base
  - [ ] Share lessons learned

---

## Contact Information

### Emergency Contacts

| Role | Name | Phone | Email | Escalation Order |
|------|------|-------|-------|------------------|
| **Primary** | [NAME] | [PHONE] | [EMAIL] | 1 |
| **Secondary** | [NAME] | [PHONE] | [EMAIL] | 2 |
| **Manager** | [NAME] | [PHONE] | [EMAIL] | 3 |

### Vendor Support

| Vendor | Support Number | Support Email | Account Number |
|--------|----------------|---------------|----------------|
| **Hyper2KVM** | [SUPPORT-INFO] | support@hyper2kvm.io | [ACCOUNT] |
| **VMware** | [SUPPORT-INFO] | [EMAIL] | [ACCOUNT] |
| **[OTHER]** | [SUPPORT-INFO] | [EMAIL] | [ACCOUNT] |

---

## Appendix

### A. Configuration Files

**Location**: `[CONFIG-DIR]`

Files:
- `[VM-NAME-1].yaml`
- `[VM-NAME-2].yaml`
- `[VM-NAME-3].yaml`
- `batch.yaml` (if applicable)

### B. Scripts

**Location**: `[SCRIPTS-DIR]`

Scripts:
- `pre-flight-check.sh`
- `migration-monitor.sh`
- `validation-check.sh`
- `rollback.sh`

### C. Logs

**Location**: `[LOGS-DIR]`

Logs:
- `migration-[VM-NAME].log`
- `validation-[VM-NAME].log`
- `system.log`

### D. Sign-Off

| Phase | Approver | Date | Signature |
|-------|----------|------|-----------|
| **Pre-Migration** | [NAME] | [DATE] | _______ |
| **Migration** | [NAME] | [DATE] | _______ |
| **Validation** | [NAME] | [DATE] | _______ |
| **Cutover** | [NAME] | [DATE] | _______ |
| **Completion** | [NAME] | [DATE] | _______ |

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [YYYY-MM-DD] | [NAME] | Initial version |
| 1.1 | [YYYY-MM-DD] | [NAME] | [CHANGES] |

---

**Runbook Template Version**: 0.3.0
**Last Updated**: March 2026

---

## Usage Notes

1. **Save a copy** of this template for each migration project
2. **Fill in all placeholders** ([PLACEHOLDER]) with actual values
3. **Customize sections** based on your specific requirements
4. **Review and approve** before migration day
5. **Print or keep open** during migration execution
6. **Update in real-time** with actual times and results
7. **Archive** with project documentation after completion

**Template**: [Download blank template](MIGRATION_RUNBOOK_TEMPLATE.md)
**Example**: [See example runbook](examples/runbook-example.md)

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
