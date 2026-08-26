# VMCraft Migration Tools - Quick Start Guide

Get started with VM migration in 5 minutes!

## Prerequisites

### Required

- **Python 3.8+**: `python3 --version`
- **VMCraft library**: `pip install -e .` (from repo root)
- **qemu-nbd**: `sudo apt-get install qemu-utils`
- **sudo privileges**: For mounting disk images

### Optional (Recommended)

- **jq**: For JSON parsing in shell scripts - `sudo apt-get install jq`
- **bc**: For calculations in shell scripts - `sudo apt-get install bc`
- **libguestfs**: For LVM/LUKS disk support - `sudo apt-get install libguestfs-tools python3-guestfs`

---

## Quick Start - Single VM Migration

Migrate a single VM with one command:

```bash
# Make scripts executable (first time only)
chmod +x *.sh

# Migrate a VM
./quick_migrate.sh /vmware/rhel9.vmdk /kvm/rhel9.qcow2 enterprise
```

That's it! The script will:
1. ✅ Assess migration readiness
2. ✅ Execute migration with enterprise strategy
3. ✅ Validate production readiness
4. ✅ Generate comprehensive reports
5. ✅ Add to analytics database

---

## Quick Start - Batch Migration

Migrate multiple VMs:

### Step 1: Create Config File

Create `my_migrations.json`:

```json
{
  "migrations": [
    {
      "source": "/vmware/web-01.vmdk",
      "target": "/kvm/web-01.qcow2",
      "strategy": "web_server",
      "description": "Web server migration"
    },
    {
      "source": "/vmware/db-01.vmdk",
      "target": "/kvm/db-01.qcow2",
      "strategy": "database",
      "description": "Database server migration"
    }
  ]
}
```

### Step 2: Run Batch Migration

```bash
./batch_migrate.sh my_migrations.json
```

The script will process all migrations sequentially with progress tracking.

---

## Quick Start - Analytics Dashboard

Track migration metrics:

```bash
# Generate HTML dashboard
python3 migration_analytics.py dashboard --output analytics.html

# Open in browser
xdg-open analytics.html  # Linux
open analytics.html      # macOS
```

---

## Migration Strategies

Choose the right strategy for your use case:

| Strategy | Use Case | Phases | Time |
|----------|----------|--------|------|
| `basic` | Simple VMs, testing | Inspection + Migration | ~5 min |
| `enterprise` | Production VMs (recommended) | All phases | ~15 min |
| `database` | Database servers | Service + Boot validation | ~10 min |
| `web_server` | Web/app servers | Service + Network | ~10 min |
| `security_hardened` | DMZ/security-critical | Service + Network + Security | ~12 min |
| `minimal_downtime` | Fast migrations | Service management only | ~7 min |

---

## Common Workflows

### Workflow 1: Safe Production Migration

```bash
# Step 1: Assess readiness
python3 pre_migration_readiness.py /vmware/prod-vm.vmdk --output readiness.json

# Step 2: Review risk score
jq '.risk_assessment' readiness.json

# Step 3: If safe, migrate
./quick_migrate.sh /vmware/prod-vm.vmdk /kvm/prod-vm.qcow2 enterprise

# Step 4: Review validation
jq '.production_readiness' migration_reports/validation_*.json
```

### Workflow 2: Batch Migration with Monitoring

```bash
# Step 1: Create batch config (my_migrations.json)
# Step 2: Run batch migration
./batch_migrate.sh my_migrations.json

# Step 3: Monitor progress
tail -f batch_migration_*/batch_migration.log

# Step 4: Generate analytics
python3 migration_analytics.py dashboard
```

### Workflow 3: Test Migration First

```bash
# Step 1: Dry run (assessment only)
python3 migration_orchestrator.py migrate test.vmdk test.qcow2 --dry-run

# Step 2: Review assessment results
# Step 3: Run actual migration
./quick_migrate.sh test.vmdk test.qcow2 basic
```

---

## Understanding Reports

### Readiness Report

```json
{
  "risk_assessment": {
    "overall_score": 25,      // 0-100 (lower is better)
    "risk_level": "LOW"       // LOW/MODERATE/HIGH/CRITICAL
  },
  "blockers": [],             // Issues that prevent migration
  "recommendations": [...]    // Suggested actions
}
```

**Risk Levels:**
- **0-30**: LOW - Safe to migrate ✅
- **31-60**: MODERATE - Review recommendations ⚠️
- **61-80**: HIGH - Address issues first ⚠️
- **81-100**: CRITICAL - Migration not recommended ❌

### Validation Report

```json
{
  "production_readiness": {
    "score": 92,              // 0-100 (higher is better)
    "readiness": "READY"      // READY/CONDITIONALLY_READY/NEEDS_WORK/NOT_READY
  },
  "issues": [...]             // Validation issues found
}
```

**Readiness Levels:**
- **90-100**: READY - Deploy to production ✅
- **70-89**: CONDITIONALLY_READY - Review issues ⚠️
- **50-69**: NEEDS_WORK - Fix issues first ⚠️
- **0-49**: NOT_READY - Critical issues ❌

---

## Command Reference

### Quick Migration Script

```bash
./quick_migrate.sh <source> <target> [strategy]

# Examples
./quick_migrate.sh vm.vmdk vm.qcow2 enterprise
./quick_migrate.sh db.vmdk db.qcow2 database
```

### Batch Migration Script

```bash
./batch_migrate.sh <config.json>

# Example
./batch_migrate.sh batch_migration_example.json
```

### Pre-Migration Assessment

```bash
python3 pre_migration_readiness.py <source> --output readiness.json

# Examples
python3 pre_migration_readiness.py vm.vmdk --output readiness.json
python3 pre_migration_readiness.py vm.vmdk --verbose
```

### Migration Orchestrator

```bash
python3 migration_orchestrator.py migrate <source> <target> --strategy <strategy>

# Examples
python3 migration_orchestrator.py migrate vm.vmdk vm.qcow2 --strategy enterprise
python3 migration_orchestrator.py migrate vm.vmdk vm.qcow2 --dry-run
python3 migration_orchestrator.py batch-migrate config.json
```

### Post-Migration Validation

```bash
python3 post_migration_validation.py <target> --output validation.json

# Examples
python3 post_migration_validation.py vm.qcow2 --output validation.json
python3 post_migration_validation.py vm.qcow2 --verbose
```

### Migration Analytics

```bash
# Add report
python3 migration_analytics.py add migration_report.json

# Add multiple reports
python3 migration_analytics.py add-batch reports/

# Generate dashboard
python3 migration_analytics.py dashboard --output analytics.html

# Show statistics
python3 migration_analytics.py stats

# Show trends
python3 migration_analytics.py trends --period 30

# Export metrics
python3 migration_analytics.py export --format json --output metrics.json
```

---

## Troubleshooting

### Issue: "Source VM not found"

**Solution**: Check path is correct and file exists
```bash
ls -lh /path/to/vm.vmdk
```

### Issue: "Readiness assessment failed"

**Solution**: Check if disk image is corrupted
```bash
qemu-img check /path/to/vm.vmdk
```

### Issue: "Migration failed during service management"

**Solution**: Check if systemd is available in guest OS
```bash
# Review migration log
cat migration_reports/migration_*.log
```

### Issue: "Validation shows low production score"

**Solution**: Review issues in validation report
```bash
jq '.issues' validation_report.json
```

### Issue: "Permission denied"

**Solution**: Ensure sudo access is configured
```bash
sudo -v  # Test sudo access
```

---

## Best Practices

### ✅ DO

1. **Always run readiness assessment first**
   ```bash
   python3 pre_migration_readiness.py vm.vmdk
   ```

2. **Use appropriate strategy**
   - Production VMs → `enterprise`
   - Database servers → `database`
   - Web servers → `web_server`

3. **Review reports before production deployment**
   ```bash
   jq . readiness.json validation.json
   ```

4. **Keep backups of source VMs**
   - Don't delete source until validated

5. **Track migrations with analytics**
   ```bash
   python3 migration_analytics.py dashboard
   ```

### ❌ DON'T

1. **Don't skip readiness assessment**
   - May miss critical issues

2. **Don't ignore CRITICAL risk levels**
   - Address issues before migrating

3. **Don't delete source VMs immediately**
   - Keep for 30+ days

4. **Don't migrate during peak hours**
   - Schedule during maintenance windows

5. **Don't skip validation**
   - Always validate before production

---

## Performance Tips

### Faster Migrations

1. **Use SSD storage** for target disk
2. **Use `minimal_downtime` strategy** for speed
3. **Run on dedicated migration server** with high I/O

### Batch Processing

1. **Process in parallel** (run multiple batch scripts)
2. **Group by strategy** for efficiency
3. **Schedule during off-hours**

---

## Getting Help

### Documentation

- **Migration Cookbook**: `MIGRATION-COOKBOOK.md`
- **Tool README**: `README.md`
- **VMCraft Features**: `../VMCRAFT-FEATURES-GUIDE.md`

### Examples

See `batch_migration_example.json` for batch config example.

### Support

- Report issues: https://github.com/ssahani/hyper2kvm/issues
- Email: (your support email)

---

## Success Checklist

Before migrating to production, ensure:

- [ ] Readiness assessment shows LOW or MODERATE risk
- [ ] No migration blockers present
- [ ] Migration completed successfully (check reports)
- [ ] Validation shows READY or CONDITIONALLY_READY
- [ ] Production score ≥ 70
- [ ] No CRITICAL issues in validation
- [ ] Source VM backed up
- [ ] Target VM tested (boot, services, network)
- [ ] Migration added to analytics for tracking

---

## Next Steps

1. **Read the Migration Cookbook** for detailed recipes
   ```bash
   cat MIGRATION-COOKBOOK.md
   ```

2. **Review the full README** for advanced features
   ```bash
   cat README.md
   ```

3. **Generate your first migration**
   ```bash
   ./quick_migrate.sh /path/to/source.vmdk /path/to/target.qcow2 enterprise
   ```

4. **Track your migrations**
   ```bash
   python3 migration_analytics.py dashboard
   ```

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────┐
│ VMCraft Migration Tools - Quick Reference              │
├─────────────────────────────────────────────────────────┤
│ Single VM:                                              │
│   ./quick_migrate.sh source.vmdk target.qcow2 enterprise│
│                                                         │
│ Batch VMs:                                              │
│   ./batch_migrate.sh config.json                        │
│                                                         │
│ Analytics:                                              │
│   python3 migration_analytics.py dashboard              │
│                                                         │
│ Risk Levels:                                            │
│   0-30:  LOW ✅      90-100: READY ✅                   │
│   31-60: MODERATE ⚠️  70-89:  CONDITIONALLY_READY ⚠️    │
│   61-80: HIGH ⚠️      50-69:  NEEDS_WORK ⚠️             │
│   81-100: CRITICAL ❌ 0-49:   NOT_READY ❌              │
│                                                         │
│ Strategies:                                             │
│   enterprise, database, web_server, security_hardened  │
└─────────────────────────────────────────────────────────┘
```

Happy migrating! 🚀
