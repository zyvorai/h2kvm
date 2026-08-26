# Migration Guides

Comprehensive migration workflows, playbooks, and batch migration features for VM migrations.

---

## Quick Links

### 📖 Migration Workflows
- **[Migration Playbooks](playbooks.md)** - 10 step-by-step migration scenarios
- **[Quick Reference](quick-reference.md)** - Fast migration command reference

### 🔄 Batch Migration
- **[Batch Features Guide](batch-features.md)** - Complete batch migration features
- **[Batch Quick Reference](batch-quick-reference.md)** - Batch migration commands

---

## Guide Descriptions

### Migration Playbooks
**File**: [playbooks.md](playbooks.md)

**10 Complete Playbooks**:
1. **vSphere to KVM Single VM** - Basic single VM migration
2. **vSphere to KVM Bulk Migration** - Multiple VM batch migration
3. **AWS EC2 to KVM Migration** - Cloud to on-premise
4. **Azure VM to KVM Migration** - Azure migration workflow
5. **Disaster Recovery Migration** - DR scenario handling
6. **Development Environment Migration** - Dev/test environments
7. **Production Database Migration** - Database-specific workflow
8. **Web Application Stack Migration** - Multi-tier applications
9. **Zero-Downtime Migration** - Live migration strategies
10. **Hybrid Cloud Migration** - Multi-cloud scenarios

**Each playbook includes**:
- Prerequisites checklist
- Step-by-step instructions
- Verification procedures
- Rollback procedures
- Troubleshooting tips
- Complete command examples

**Use when**: Planning and executing specific migration scenarios

---

### Migration Quick Reference
**File**: [quick-reference.md](quick-reference.md)

**Quick command reference for**:
- Local VMDK conversion
- Remote ESXi fetch
- OVA/OVF extraction
- Live SSH-based fixes
- Common migration patterns
- Output format options
- Compression and optimization

**Use when**: Need quick syntax for common migration tasks

---

### Batch Features Guide
**File**: [batch-features.md](batch-features.md)

**Complete batch migration features**:
- **Batch Orchestration** - Multi-VM parallel conversion with error isolation
- **Network & Storage Mapping** - Source-to-target transformations
- **Migration Profiles** - Reusable configuration templates
- **Pre/Post Hooks** - Automation via shell/Python/HTTP hooks
- **Libvirt XML Input** - Import existing libvirt VMs

**Architecture**:
- Security-first design (path validation, timeouts, isolation)
- Configuration-driven (YAML/JSON)
- Atomic operations (temp file + replace pattern)
- Error handling and rollback

**Use when**: Migrating multiple VMs, need automation, require custom workflows

---

### Batch Quick Reference
**File**: [batch-quick-reference.md](batch-quick-reference.md)

**Quick reference for**:
- Batch manifest format
- Parallel execution options
- Profile management
- Hook configuration
- Network/storage mapping syntax
- Error handling options

**Use when**: Need quick syntax for batch migration features

---

## Migration Workflow Comparison

| Scenario | Recommended Guide | Features Used | Complexity |
|----------|-------------------|---------------|------------|
| **Single VM migration** | Quick Reference | Basic conversion | Low |
| **5-10 VMs** | Playbooks → Batch Quick Reference | Batch orchestration | Medium |
| **10+ VMs** | Batch Features Guide | Full batch features | Medium-High |
| **Production migration** | Playbooks (#7-9) → Batch Features | Hooks, profiles, mapping | High |
| **Cloud migration** | Playbooks (#3-4, #10) | Platform-specific | Medium-High |
| **Zero downtime** | Playbooks (#9) | Live migration | High |

---

## Quick Start Paths

### Path 1: First Single VM Migration (30 minutes)

**Goal**: Migrate your first VM from VMware to KVM

```bash
# 1. Use Quick Reference for basic syntax
docs/guides/migration/quick-reference.md

# 2. Run simple migration
h2kvm local \
  --vmdk /vms/source.vmdk \
  --output-dir /vms/migrated \
  --to-output vm.qcow2

# 3. Verify and boot
virsh define /vms/migrated/vm.xml
virsh start vm
```

**Recommended**: [Quick Reference](quick-reference.md)

---

### Path 2: vSphere Bulk Migration (2-4 hours)

**Goal**: Migrate 10+ VMs from vSphere to KVM

```bash
# 1. Follow Playbook 2 for planning
docs/guides/migration/playbooks.md - Playbook 2

# 2. Use Batch Features for automation
docs/guides/migration/batch-features.md

# 3. Create batch manifest
cat > migrations.json <<EOF
{
  "migrations": [
    {"vmdk": "/vms/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vms/vm2.vmdk", "to_output": "vm2.qcow2"}
  ]
}
EOF

# 4. Execute batch
h2kvm local \
  --batch-manifest migrations.json \
  --batch-parallel 4 \
  --batch-continue-on-error
```

**Recommended**: [Playbooks](playbooks.md) + [Batch Features Guide](batch-features.md)

---

### Path 3: Production Database Migration (4-8 hours)

**Goal**: Zero-downtime production database migration

```bash
# 1. Follow Playbook 7 for database-specific steps
docs/guides/migration/playbooks.md - Playbook 7

# 2. Configure hooks for backup/restore
docs/guides/migration/batch-features.md - Pre/Post Hooks

# 3. Use migration profile
cat > db-profile.yaml <<EOF
profile:
  name: "production-db"
  regen_initramfs: true
  fstab_mode: stabilize-all
  libvirt_test: true
  hooks:
    pre_conversion: "./scripts/backup-db.sh"
    post_conversion: "./scripts/verify-db.sh"
EOF

# 4. Execute with profile
h2kvm local \
  --vmdk /vms/db-server.vmdk \
  --profile db-profile.yaml
```

**Recommended**: [Playbooks](playbooks.md) + [Batch Features Guide](batch-features.md)

---

## Migration Type Guide

### Local VMDK Conversion

**Scenario**: VMDK files already accessible locally

**Recommended**:
- [Quick Reference](quick-reference.md) - Local conversion section
- [Playbook 1](playbooks.md) - If complex VM

**Command**:
```bash
h2kvm local --vmdk /path/to/vm.vmdk --output-dir /output
```

---

### Remote vSphere Migration

**Scenario**: Fetch VMs directly from ESXi/vCenter

**Recommended**:
- [Playbook 1](playbooks.md) - Single VM
- [Playbook 2](playbooks.md) - Bulk migration
- [Batch Features Guide](batch-features.md) - Automation

**Command**:
```bash
h2kvm fetch-and-fix \
  --host esxi.example.com \
  --user root \
  --identity ~/.ssh/id_rsa \
  --remote /vmfs/volumes/datastore1/vm/vm.vmdk
```

---

### OVA/OVF Import

**Scenario**: Import VMs from OVA/OVF packages

**Recommended**:
- [Quick Reference](quick-reference.md) - OVA extraction
- [Playbook 6](playbooks.md) - Development environments

**Command**:
```bash
h2kvm ova \
  --ova /path/to/vm.ova \
  --output-dir /output
```

---

### Cloud Migration (AWS/Azure)

**Scenario**: Migrate from cloud providers

**Recommended**:
- [Playbook 3](playbooks.md) - AWS EC2
- [Playbook 4](playbooks.md) - Azure VMs
- [Playbook 10](playbooks.md) - Hybrid cloud

**AWS Command**:
```bash
h2kvm ami \
  --ami ami-12345678 \
  --region us-east-1 \
  --output-dir /output
```

**Azure Command**:
```bash
h2kvm azure \
  --vhd https://storage.blob.core.windows.net/vhds/vm.vhd \
  --output-dir /output
```

---

### Live Migration (Zero Downtime)

**Scenario**: Migrate without stopping source VM

**Recommended**:
- [Playbook 9](playbooks.md) - Zero-downtime migration
- [Batch Features Guide](batch-features.md) - Hooks for orchestration

**Command**:
```bash
h2kvm live-fix \
  --host source-vm.example.com \
  --user root \
  --identity ~/.ssh/id_rsa
```

---

## Batch Migration Features

### Feature 1: Batch Orchestration

**Execute multiple migrations in parallel**:
```bash
h2kvm local \
  --batch-manifest migrations.json \
  --batch-parallel 4 \
  --batch-continue-on-error
```

**Documentation**: [Batch Features Guide](batch-features.md) - Feature 1

---

### Feature 2: Network & Storage Mapping

**Transform network/storage during migration**:
```yaml
mappings:
  network:
    "VM Network": "br0"
    "Storage Network": "br1"
  storage:
    "datastore1": "/vms/pool1"
    "datastore2": "/vms/pool2"
```

**Documentation**: [Batch Features Guide](batch-features.md) - Feature 2

---

### Feature 3: Migration Profiles

**Reusable configuration templates**:
```yaml
profile:
  name: "linux-server"
  regen_initramfs: true
  fstab_mode: stabilize-all
  compress: true
  libvirt_test: true
```

**Documentation**: [Batch Features Guide](batch-features.md) - Feature 3

---

### Feature 4: Pre/Post Hooks

**Automation at pipeline stages**:
```yaml
hooks:
  pre_conversion: "./backup.sh"
  post_conversion: "./verify.sh"
  pre_fix: "./prepare.sh"
  post_fix: "./cleanup.sh"
```

**Documentation**: [Batch Features Guide](batch-features.md) - Feature 4

---

### Feature 5: Libvirt XML Input

**Import from existing libvirt domains**:
```bash
h2kvm libvirt-import \
  --domain-xml /etc/libvirt/qemu/vm.xml \
  --output-dir /output
```

**Documentation**: [Batch Features Guide](batch-features.md) - Feature 5

---

## Common Migration Patterns

### Pattern 1: Simple Single VM
**Files**: Quick Reference
**Features**: Basic conversion
**Time**: 30 minutes

### Pattern 2: Bulk Migration
**Files**: Playbooks (#2) + Batch Features
**Features**: Batch orchestration, parallel execution
**Time**: 2-4 hours

### Pattern 3: Production Migration
**Files**: Playbooks (#7-9) + Batch Features
**Features**: Profiles, hooks, mapping, validation
**Time**: 4-8 hours

### Pattern 4: Cloud Migration
**Files**: Playbooks (#3, #4, #10)
**Features**: Platform-specific converters
**Time**: 2-4 hours

### Pattern 5: Zero Downtime
**Files**: Playbooks (#9) + Batch Features
**Features**: Live migration, hooks, verification
**Time**: 8+ hours

---

## Integration with Other Documentation

### Pre-Migration Planning
- **[Migration Decision Tree](../decision-support/MIGRATION_DECISION_TREE.md)** - Choose approach
- **[Pre-Flight Validation](../operations/PRE_FLIGHT_VALIDATION.md)** - Verify readiness
- **[Migration Checklist](../operations/MIGRATION_CHECKLIST.md)** - Track progress

### During Migration
- **[Quick Reference](quick-reference.md)** - Command syntax
- **[Playbooks](playbooks.md)** - Step-by-step procedures
- **[Batch Features](batch-features.md)** - Automation features

### Post-Migration
- **[Best Practices](../operations/BEST_PRACTICES.md)** - Proven practices
- **[Monitoring Guide](../operations/MONITORING_GUIDE.md)** - Production monitoring
- **[Troubleshooting Flowchart](../decision-support/TROUBLESHOOTING_FLOWCHART.md)** - Issue resolution

---

## Tool Selection Matrix

| Your Need | Recommended Guide |
|-----------|-------------------|
| **First migration** | Quick Reference |
| **Specific scenario** | Playbooks (choose scenario) |
| **Multiple VMs** | Batch Quick Reference |
| **Complex automation** | Batch Features Guide |
| **Production migration** | Playbooks (#7-9) + Batch Features |
| **Quick command lookup** | Quick Reference or Batch Quick Reference |

---

## Related Documentation

### Getting Started
- **[Installation Guide](../../getting-started/01-Installation.md)** - Install H2KVM
- **[Quick Start](../../getting-started/02-Quick-Start.md)** - First migration
- **[Beginner Tutorial](../../tutorials/01-beginner-migration.md)** - Step-by-step walkthrough

### Operational Guides
- **[Operations Hub](../operations/)** - Complete operational toolkit
- **[Examples Library](../operations/EXAMPLES_LIBRARY.md)** - 23+ configuration examples
- **[Automation Scripts](../operations/AUTOMATION_SCRIPTS.md)** - 10 automation scripts

### Reference
- **[CLI Reference](../cli/reference.md)** - Complete command documentation
- **[API Reference](../../reference/api/README.md)** - Programmatic usage

---

## Summary

**4 comprehensive migration guides** covering:
- ✅ 10 step-by-step migration playbooks
- ✅ Quick reference for common migrations
- ✅ Complete batch migration features
- ✅ Batch quick reference

**Total Documentation**: ~15,000+ lines covering all migration scenarios

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
**Guides**: 4 comprehensive migration guides

**Quick Navigation**: [Guides Hub](../README.md) | [Documentation Hub](../../index.md) | [Operational Guides](../operations/)
