# VMCraft Migration Tools Suite

Comprehensive toolkit for enterprise VM migration planning, execution, and validation.

## Overview

The Migration Tools Suite provides end-to-end support for VMware to KVM migrations:

1. **Pre-Migration Assessment** - Risk analysis and readiness checking
2. **Migration Orchestration** - Automated execution with multiple strategies
3. **Post-Migration Validation** - Production readiness verification
4. **Migration Analytics** - Metrics tracking and dashboard
5. **Quick Start Scripts** - One-command migration workflows
6. **Migration Cookbook** - Recipes for common migration scenarios

---

## Quick Start

**Migrate a VM with one command:**

```bash
./quick_migrate.sh /vmware/rhel9.vmdk /kvm/rhel9.qcow2 enterprise
```

**Migrate multiple VMs:**

```bash
./batch_migrate.sh batch_migration_example.json
```

See [QUICK-START.md](QUICK-START.md) for detailed getting started guide.

---

## Tools

### 1. Pre-Migration Readiness Assessment

**File**: `pre_migration_readiness.py`

**Purpose**: Assess VM migration readiness and identify potential issues before migration.

**Features**:
- OS compatibility validation
- Disk configuration analysis
- LVM detection and enumeration
- Systemd service dependency checking
- Network configuration review
- Boot configuration validation
- Risk scoring (0-100 scale)
- Migration blocker detection
- Automated recommendations

**Usage**:
```bash
# Full assessment with JSON report
python pre_migration_readiness.py /path/to/vm.vmdk --output assessment_report.json

# Quick assessment (console output only)
python pre_migration_readiness.py /path/to/vm.vmdk

# Verbose output
python pre_migration_readiness.py /path/to/vm.vmdk --verbose
```

**Risk Scoring**:
- **0-30**: LOW - Safe to migrate
- **31-60**: MODERATE - Review recommendations
- **61-80**: HIGH - Address issues before migration
- **81-100**: CRITICAL - Migration not recommended

**Example Output**:
```json
{
  "timestamp": "2025-01-26T10:30:00",
  "vm_image": "/vmware/rhel9.vmdk",
  "risk_assessment": {
    "overall_score": 25,
    "risk_level": "LOW"
  },
  "os_compatibility": {
    "check": "PASS",
    "os_type": "linux",
    "distro": "rhel",
    "version": "9.2"
  },
  "blockers": [],
  "recommendations": [
    "Enable systemd-networkd for network management",
    "Create LVM snapshots before migration"
  ]
}
```

---

### 2. Migration Orchestrator

**File**: `migration_orchestrator.py`

**Purpose**: Automated end-to-end migration workflow execution with multiple strategies.

**Features**:
- Pre-migration readiness check
- Automatic backup creation
- VM inspection and analysis
- Service management (VMware → KVM)
- Network configuration migration
- Security hardening
- Boot validation
- Post-migration validation
- Comprehensive reporting
- Rollback capabilities
- Batch migration support

**Migration Strategies**:

| Strategy | Phases | Use Case |
|----------|--------|----------|
| `basic` | Inspection, Migration | Simple VMs, minimal changes |
| `enterprise` | All phases | Production VMs, complete migration |
| `database` | Inspection, Migration, Services, Boot Validation | Database servers |
| `web_server` | Inspection, Migration, Services, Network | Web/application servers |
| `security_hardened` | Inspection, Migration, Services, Network, Security | DMZ/security-critical VMs |
| `minimal_downtime` | Inspection, Migration, Services | Fast migrations |
| `custom` | User-defined phases | Custom workflows |

**Usage**:

```bash
# Enterprise migration (full workflow)
python migration_orchestrator.py migrate /vmware/rhel9.vmdk /kvm/rhel9.qcow2 --strategy enterprise

# Dry-run (assessment only, no migration)
python migration_orchestrator.py migrate source.vmdk target.qcow2 --dry-run

# Database migration strategy
python migration_orchestrator.py migrate db.vmdk db-kvm.qcow2 --strategy database

# Custom phases
python migration_orchestrator.py migrate vm.vmdk vm-kvm.qcow2 --phases inspection,services,validation

# Batch migration from config file
python migration_orchestrator.py batch-migrate batch_migration_example.json

# Verbose output
python migration_orchestrator.py migrate vm.vmdk vm-kvm.qcow2 --strategy enterprise --verbose
```

**Migration Phases**:

1. **Readiness Assessment** - Pre-flight checks
2. **Pre-Migration Backup** - Automatic backup creation
3. **Inspection** - OS detection and analysis
4. **Migration** - Disk conversion and copy
5. **Service Management** - VMware → KVM service migration
6. **Network Configuration** - ifcfg → systemd-networkd
7. **Security Hardening** - SSH hardening, service lockdown
8. **Boot Validation** - Boot configuration and performance
9. **Post-Migration Validation** - Production readiness check
10. **Final Report** - Comprehensive JSON report

**Example Report**:
```json
{
  "migration_id": "migration_1737884400",
  "success": true,
  "duration_seconds": 245.67,
  "strategy": "enterprise",
  "phases": {
    "readiness_assessment": {"success": true, "duration_seconds": 45.2},
    "migration": {"success": true, "duration_seconds": 120.5},
    "service_management": {"success": true, "duration_seconds": 15.3}
  },
  "readiness_assessment": {
    "risk_level": "LOW",
    "overall_score": 25
  },
  "validation_report": {
    "production_readiness": {
      "readiness": "READY",
      "score": 92
    }
  }
}
```

**Batch Migration**:

Create a JSON config file (`batch_migration_example.json`):
```json
{
  "migrations": [
    {
      "source": "/vmware/web-01.vmdk",
      "target": "/kvm/web-01.qcow2",
      "strategy": "web_server"
    },
    {
      "source": "/vmware/db-01.vmdk",
      "target": "/kvm/db-01.qcow2",
      "strategy": "database"
    }
  ]
}
```

Execute batch migration:
```bash
python migration_orchestrator.py batch-migrate batch_migration_example.json
```

---

### 3. Post-Migration Validation

**File**: `post_migration_validation.py`

**Purpose**: Validate migrated VMs for production readiness.

**Features**:
- Boot configuration verification
- Service health checking
- Network configuration validation
- Filesystem integrity testing
- Boot performance analysis
- Security posture audit
- Production readiness scoring
- Issue tracking with remediation steps
- Comprehensive reporting

**Usage**:
```bash
# Full validation with JSON report
python post_migration_validation.py /kvm/vm.qcow2 --output validation_report.json

# Quick validation (console output only)
python post_migration_validation.py /kvm/vm.qcow2

# Verbose output
python post_migration_validation.py /kvm/vm.qcow2 --verbose
```

**Production Readiness Scoring**:
- **90-100**: READY - Production deployment approved
- **70-89**: CONDITIONALLY_READY - Minor issues, review recommended
- **50-69**: NEEDS_WORK - Address issues before production
- **0-49**: NOT_READY - Critical issues, migration failed

**Validation Checks**:

| Check | Description | Pass Criteria |
|-------|-------------|---------------|
| Boot Configuration | Boot mode, bootloader | EFI/BIOS detected, bootloader present |
| Service Health | Failed services, VMware cleanup | No failed services, VMware services removed |
| Network Configuration | systemd-networkd status | networkd enabled and configured |
| Filesystem Integrity | Mount test for all filesystems | All filesystems mountable |
| Boot Performance | Boot time analysis | Boot time < 60s |
| Security Posture | SSH configuration audit | Root login disabled, key auth enabled |

**Example Output**:
```json
{
  "timestamp": "2025-01-26T11:00:00",
  "vm_image": "/kvm/rhel9.qcow2",
  "production_readiness": {
    "score": 92,
    "readiness": "READY"
  },
  "validation_results": {
    "boot_configuration": {"status": "PASS"},
    "service_health": {"status": "PASS"},
    "network_configuration": {"status": "PASS"},
    "filesystem_integrity": {"status": "PASS"},
    "boot_performance": {"status": "PASS"},
    "security_posture": {"status": "PASS"}
  },
  "issues": [],
  "remediation_steps": []
}
```

---

### 4. Migration Analytics

**File**: `migration_analytics.py`

**Purpose**: Track migration metrics and generate analytics dashboards.

**Features**:
- Migration metrics aggregation
- Success rate tracking
- Performance trend analysis
- Risk score trending
- Production readiness tracking
- HTML dashboard generation
- JSON/CSV export

**Usage**:
```bash
# Add migration report to analytics database
python migration_analytics.py add migration_report_12345.json

# Add all reports from directory
python migration_analytics.py add-batch reports/

# Generate HTML dashboard
python migration_analytics.py dashboard --output analytics.html

# Show statistics
python migration_analytics.py stats

# Show 30-day trends
python migration_analytics.py trends --period 30

# Export metrics to JSON
python migration_analytics.py export --format json --output metrics.json
```

**Dashboard Features**:
- Total migrations count
- Success rate with progress bars
- Average duration
- Strategy breakdown
- Phase performance statistics
- Quality metrics (risk scores, production scores)
- Visual metrics cards with color coding

**Example Dashboard Output**:
- Success rate: 95.5%
- Average duration: 12.3 minutes
- Average production score: 89/100
- Most common strategy: enterprise (45%)

---

### 5. Quick Start Scripts

**Files**: `quick_migrate.sh`, `batch_migrate.sh`

**Purpose**: One-command migration workflows with automatic assessment and validation.

#### Single VM Migration (`quick_migrate.sh`)

**Features**:
- Automatic readiness assessment
- Migration execution
- Post-migration validation
- Report generation
- Analytics integration
- Color-coded progress output

**Usage**:
```bash
./quick_migrate.sh <source.vmdk> <target.qcow2> [strategy]

# Examples
./quick_migrate.sh /vmware/rhel9.vmdk /kvm/rhel9.qcow2 enterprise
./quick_migrate.sh /vmware/db.vmdk /kvm/db.qcow2 database
```

**Workflow**:
1. Pre-migration readiness assessment
2. Risk score evaluation (with confirmation prompts)
3. Migration execution with selected strategy
4. Post-migration validation
5. Production readiness evaluation
6. Comprehensive summary with all report paths
7. Automatic analytics database update

#### Batch Migration (`batch_migrate.sh`)

**Features**:
- Multiple VM processing from JSON config
- Sequential migration execution
- Per-migration output directories
- Progress tracking
- Success/failure summary
- Batch analytics

**Usage**:
```bash
./batch_migrate.sh <config.json>

# Example
./batch_migrate.sh batch_migration_example.json
```

**Config Format**:
```json
{
  "migrations": [
    {
      "source": "/vmware/web-01.vmdk",
      "target": "/kvm/web-01.qcow2",
      "strategy": "web_server",
      "description": "Web server migration"
    }
  ]
}
```

**Output**:
- Individual migration logs
- Batch summary (successful/failed counts)
- Success rate calculation
- All reports added to analytics

---

### 6. Migration Cookbook

**File**: `MIGRATION-COOKBOOK.md`

**Purpose**: Practical recipes for common migration scenarios.

**Recipes Included**:

1. **Basic VMware to KVM Migration** - Simple single-VM migration
2. **Large Enterprise VM Migration** - Multi-VM production migration
3. **Database Server Migration** - Database-specific optimizations
4. **Web Server Farm Migration** - Load-balanced web servers
5. **Security-Hardened Migration** - DMZ/security-critical VMs
6. **Minimal Downtime Migration** - Fast migrations with minimal interruption
7. **Disaster Recovery Setup** - DR site migration
8. **Batch Migration Workflow** - Automated multi-VM migrations
9. **Troubleshooting Failed Migrations** - Common issues and solutions
10. **Performance Optimization** - Speed up large migrations

**Each Recipe Includes**:
- Use case description
- Time estimate
- Complexity rating
- Risk level
- Prerequisites
- Detailed steps with code examples
- Post-migration checklist
- Common pitfalls

**Example Recipe** (Database Migration):
```python
# 1. Pre-migration database health check
with VMCraft("/vmware/db-server.vmdk") as g:
    # Check database service
    status = g.systemd_service_status("postgresql.service")

    # Create pre-migration backup
    g.tar_out("/var/lib/postgresql", "db_backup.tar.xz", compress="xz")

# 2. Execute migration with database strategy
python migration_orchestrator.py migrate \\
    /vmware/db-server.vmdk \\
    /kvm/db-server.qcow2 \\
    --strategy database

# 3. Post-migration validation
python post_migration_validation.py /kvm/db-server.qcow2
```

---

## Installation

### Requirements

**Core Requirements**:
- Python 3.8+
- VMCraft library (h2kvm)
- qemu-nbd
- sudo privileges

**Optional (for specific features)**:
- `lvm2` - For LVM management
- `python-augeas` + `augeas` - For configuration management
- `systemd` - For systemd integration

### Install

```bash
# Clone repository
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm

# Install dependencies
pip install -e .

# Navigate to migration tools
cd examples/migration_tools

# Make scripts executable
chmod +x *.py
```

---

## Quick Start

### 1. Assess VM Readiness

```bash
# Run readiness assessment
python pre_migration_readiness.py /vmware/vm.vmdk --output readiness.json

# Review risk score
jq '.risk_assessment' readiness.json
```

### 2. Execute Migration

```bash
# Enterprise migration (recommended)
python migration_orchestrator.py migrate \\
    /vmware/vm.vmdk \\
    /kvm/vm.qcow2 \\
    --strategy enterprise \\
    --verbose
```

### 3. Validate Migration

```bash
# Run post-migration validation
python post_migration_validation.py /kvm/vm.qcow2 --output validation.json

# Review production readiness
jq '.production_readiness' validation.json
```

### 4. Review Reports

```bash
# View migration report
ls -lh migration_report_*.json

# View readiness assessment
cat readiness.json | jq '.recommendations'

# View validation issues
cat validation.json | jq '.issues'
```

---

## Workflow Examples

### Complete Single VM Migration

```bash
#!/bin/bash
# complete_migration.sh - End-to-end migration workflow

VM_SOURCE="/vmware/production/web-01.vmdk"
VM_TARGET="/kvm/production/web-01.qcow2"

# Step 1: Pre-migration assessment
echo "=== Pre-Migration Assessment ==="
python pre_migration_readiness.py "$VM_SOURCE" --output readiness.json

# Check risk score
RISK_SCORE=$(jq -r '.risk_assessment.overall_score' readiness.json)
if [ "$RISK_SCORE" -gt 60 ]; then
    echo "ERROR: Risk score too high ($RISK_SCORE). Review assessment."
    exit 1
fi

# Step 2: Execute migration
echo "=== Migration Execution ==="
python migration_orchestrator.py migrate \\
    "$VM_SOURCE" \\
    "$VM_TARGET" \\
    --strategy enterprise \\
    --verbose

# Step 3: Post-migration validation
echo "=== Post-Migration Validation ==="
python post_migration_validation.py "$VM_TARGET" --output validation.json

# Check production readiness
PROD_SCORE=$(jq -r '.production_readiness.score' validation.json)
if [ "$PROD_SCORE" -lt 70 ]; then
    echo "WARNING: Production score low ($PROD_SCORE). Review validation."
fi

echo "=== Migration Complete ==="
echo "Risk Score: $RISK_SCORE/100"
echo "Production Score: $PROD_SCORE/100"
```

### Batch Migration Workflow

```bash
#!/bin/bash
# batch_migration.sh - Migrate multiple VMs

# Create batch config
cat > batch_config.json <<EOF
{
  "migrations": [
    {"source": "/vmware/web-01.vmdk", "target": "/kvm/web-01.qcow2", "strategy": "web_server"},
    {"source": "/vmware/web-02.vmdk", "target": "/kvm/web-02.qcow2", "strategy": "web_server"},
    {"source": "/vmware/db-01.vmdk", "target": "/kvm/db-01.qcow2", "strategy": "database"}
  ]
}
EOF

# Execute batch migration
python migration_orchestrator.py batch-migrate batch_config.json --verbose

# Validate all migrations
for vm in /kvm/*.qcow2; do
    echo "Validating $vm..."
    python post_migration_validation.py "$vm"
done
```

---

## Best Practices

### Pre-Migration

1. **Always run readiness assessment first**
   ```bash
   python pre_migration_readiness.py vm.vmdk --output readiness.json
   ```

2. **Review risk score and blockers**
   - Address CRITICAL issues before migration
   - Review HIGH risk recommendations

3. **Test with dry-run**
   ```bash
   python migration_orchestrator.py migrate vm.vmdk vm.qcow2 --dry-run
   ```

4. **Create manual backups**
   - Backup source VM
   - Backup critical data separately

### During Migration

1. **Use appropriate strategy**
   - `enterprise` for production VMs
   - `database` for database servers
   - `web_server` for web/app servers
   - `security_hardened` for DMZ VMs

2. **Monitor progress**
   - Use `--verbose` flag for detailed output
   - Review phase results in real-time

3. **Keep logs**
   - Redirect output to log file
   - Save migration reports

### Post-Migration

1. **Always run validation**
   ```bash
   python post_migration_validation.py vm.qcow2 --output validation.json
   ```

2. **Review production readiness score**
   - Score ≥ 90: Safe to deploy
   - Score 70-89: Review issues
   - Score < 70: Address critical issues

3. **Test migrated VM**
   - Boot test
   - Service health check
   - Network connectivity test
   - Application functionality test

4. **Keep backups**
   - Don't delete source VM immediately
   - Keep backups for 30+ days

---

## Troubleshooting

### Common Issues

**Issue**: Readiness assessment fails with "No OS detected"
- **Solution**: Verify disk image is not corrupted
- **Solution**: Check disk format is supported (qcow2, vmdk, raw)

**Issue**: Migration fails during service management
- **Solution**: Verify systemd is available in guest OS
- **Solution**: Check VMware tools are installed

**Issue**: Validation fails with low production score
- **Solution**: Review `issues` array in validation report
- **Solution**: Follow remediation steps
- **Solution**: Re-run validation after fixes

**Issue**: Network configuration migration fails
- **Solution**: Check if ifcfg files exist in guest
- **Solution**: Verify systemd-networkd is available

**Issue**: Batch migration partially fails
- **Solution**: Review individual migration reports
- **Solution**: Re-run failed migrations separately

### Debug Mode

Enable verbose output for detailed troubleshooting:

```bash
# Readiness assessment
python pre_migration_readiness.py vm.vmdk --verbose

# Migration orchestrator
python migration_orchestrator.py migrate vm.vmdk vm.qcow2 --verbose

# Post-migration validation
python post_migration_validation.py vm.qcow2 --verbose
```

### Log Files

Migration reports are automatically saved:
- Readiness: `<output>.json` or console output
- Migration: `migration_report_<id>.json`
- Validation: `<output>.json` or console output

---

## Advanced Usage

### Custom Migration Phases

Execute only specific phases:

```bash
python migration_orchestrator.py migrate vm.vmdk vm.qcow2 \\
    --phases inspection,services,validation \\
    --verbose
```

### Rollback Failed Migration

```python
from migration_orchestrator import MigrationOrchestrator

orchestrator = MigrationOrchestrator("source.vmdk", "target.qcow2")
report = orchestrator.execute()

if not report["success"]:
    print("Migration failed - rolling back...")
    orchestrator.rollback()
```

### Integration with CI/CD

```yaml
# .gitlab-ci.yml example
migrate_vms:
  stage: migrate
  script:
    - python migration_orchestrator.py batch-migrate migrations.json
  artifacts:
    paths:
      - migration_report_*.json
    expire_in: 30 days
```

---

## Migration Metrics

Track migration success with these metrics:

1. **Risk Score** (Pre-Migration)
   - Target: < 30 (LOW risk)
   - Threshold: < 60 (acceptable)

2. **Migration Duration**
   - Basic VM: 5-10 minutes
   - Enterprise VM: 10-20 minutes
   - Large VM (100GB+): 30-60 minutes

3. **Production Readiness Score** (Post-Migration)
   - Target: ≥ 90 (READY)
   - Threshold: ≥ 70 (acceptable)

4. **Success Rate**
   - Target: 95%+ for batch migrations
   - Threshold: 90%+ acceptable

---

## Support

### Getting Help

1. **Documentation**
   - Migration Cookbook: `MIGRATION-COOKBOOK.md`
   - VMCraft Features Guide: `../VMCRAFT-FEATURES-GUIDE.md`
   - API Documentation: `../../docs/09-VMCraft.md`

2. **Examples**
   - Systemd migration: `../systemd_migration/`
   - Advanced features: `../advanced_vmcraft/`
   - Enterprise example: `../enterprise_migration_master.py`

3. **Issues**
   - Report bugs: https://github.com/ssahani/h2kvm/issues
   - Feature requests: GitHub Issues

### Contributing

Contributions welcome! Please submit PRs for:
- New migration strategies
- Additional validation checks
- Migration recipes
- Bug fixes

---

## License

This project is licensed under the same license as the h2kvm project.

---

## Summary

The Migration Tools Suite provides:

✅ **Complete Workflow** - Pre-migration → Migration → Post-migration
✅ **Risk Assessment** - Identify issues before migration
✅ **Automated Execution** - Multiple strategies for different scenarios
✅ **Production Validation** - Ensure VMs are production-ready
✅ **Batch Support** - Migrate multiple VMs efficiently
✅ **Comprehensive Reports** - JSON reports for audit trails
✅ **Rollback Capabilities** - Safe migration with backups
✅ **Best Practices** - Recipes for common scenarios

**Next Steps**:
1. Review `MIGRATION-COOKBOOK.md` for migration recipes
2. Run `pre_migration_readiness.py` on your VMs
3. Execute migrations with `migration_orchestrator.py`
4. Validate with `post_migration_validation.py`
