# Hyper2KVM API Reference

Comprehensive API documentation for all Hyper2KVM modules and features.

---

## Core APIs

### VMCraft API
**[Complete Documentation](vmcraft-api.md)**

Guest filesystem manipulation API with 480+ comprehensive methods for VM manipulation.

**Key Features**:
- Filesystem operations (mount, read, write, edit)
- Partition management (create, delete, resize)
- LVM operations (create, manage volumes)
- Package management (install, update, query)
- Configuration editing (Augeas integration)
- Archive operations (tar, compression)

**Quick Example**:
```python
from hyper2kvm.vmcraft import VMCraft

vmcraft = VMCraft(logger)
vmcraft.add_disk("/vms/server.qcow2")
vmcraft.launch()

# Read file
content = vmcraft.read_file("/etc/fstab")

# Edit configuration
vmcraft.write_file("/etc/hostname", "new-hostname")

vmcraft.shutdown()
```

---

### Validation API
**[Complete Documentation](validation-api.md)** ✨ NEW

Post-migration validation framework with automated health checks.

**Features**:
- System health checks (boot, fstab, kernel modules)
- Service validation (systemd services)
- Network validation (interfaces, DNS)
- Database validation (PostgreSQL, MySQL/MariaDB)
- Performance benchmarking (disk I/O)
- JSON and Markdown reports

**Quick Example**:
```python
from hyper2kvm.validation import ValidationOrchestrator

orchestrator = ValidationOrchestrator(logger)
report = orchestrator.validate_migration(
    vmcraft,
    check_services=True,
    check_network=True,
    check_databases=True
)

if report.overall_status == "PASS":
    print("✓ Validation passed!")
```

---

### Rollback API
**[Complete Documentation](rollback-api.md)** ✨ NEW

Migration rollback and recovery framework with snapshot management.

**Features**:
- Snapshot management (create, restore, delete)
- State tracking with reversible checkpoints
- Full and partial rollback strategies
- Rollback validation
- SHA256 checksum verification
- JSON and Markdown reports

**Quick Example**:
```python
from hyper2kvm.rollback import RollbackOrchestrator

orchestrator = RollbackOrchestrator(logger)

# Create snapshot
snapshot = orchestrator.snapshot_manager.create_snapshot(
    "/vms/app-server.qcow2",
    compute_checksum=True
)

# ... perform migration ...

# If migration fails, rollback
report = orchestrator.execute_full_rollback(
    snapshot.snapshot_id,
    verify_checksum=True,
    validate=True
)
```

---

### CLI API
**[Complete Documentation](cli-api.md)** ✨ NEW

Rich terminal interface with interactive wizard and configuration management.

**Features**:
- Interactive 5-step migration wizard
- Progress tracking (bars, spinners, multi-stage)
- Rich output formatting (ANSI colors, tables)
- Configuration management (JSON/YAML)
- Validation and error handling

**Quick Example**:
```python
from hyper2kvm.cli import MigrationWizard, ProgressBar

# Interactive wizard
wizard = MigrationWizard(logger)
result = wizard.run(interactive=True)

# Progress bar
bar = ProgressBar(total=100, prefix="Copying")
for i in range(100):
    # ... do work ...
    bar.update(increment=1)
```

---

## Feature APIs

### Live Migration API
**[Complete Documentation](live-migration-api.md)**

Live migration with minimal downtime using HyperSDK integration.

**Features**:
- Feasibility analysis (downtime estimation)
- Pre-copy memory transfer
- Final switchover (<5s downtime)
- Multi-provider support (VMware, Hyper-V, AWS, Azure, GCP)
- Progress monitoring and cancellation

**Quick Example**:
```python
from hyper2kvm.live import LiveMigrationAnalyzer, HybridMigrationManager

# Analyze feasibility
analyzer = LiveMigrationAnalyzer(logger)
analysis = analyzer.analyze_vm("/vms/prod-app.vmdk")

if analysis.recommendation == "EXCELLENT":
    # Execute live migration
    manager = HybridMigrationManager(logger)
    result = manager.migrate_live(
        "/vms/prod-app.vmdk",
        provider="vmware",
        max_downtime_seconds=5
    )
```

---

### Backup Integration API
**[Complete Documentation](backup-api.md)**

Backup restore and DR testing integration.

**Features**:
- Veeam Backup & Replication support
- Proxmox Backup Server support
- Generic backup restore
- DR testing workflows
- Backup validation

**Quick Example**:
```python
from hyper2kvm.backup import VeeamBackupSource

# Restore from Veeam
source = VeeamBackupSource("/backups/veeam-repo", logger)
vms = source.list_vms()

source.restore_vm(
    "prod-app-01",
    "/vms/dr-test/prod-app-01.qcow2"
)
```

---

## API Comparison

| API | Methods | Status | Use Cases |
|-----|---------|--------|-----------|
| **VMCraft** | 480+ | ✅ Production | Guest filesystem manipulation |
| **Validation** | 15+ | ✅ Production | Post-migration validation |
| **Rollback** | 20+ | ✅ Production | Rollback and recovery |
| **CLI** | 10+ | ✅ Production | Interactive workflows |
| **Live Migration** | 8+ | ✅ Production | Minimal-downtime migration |
| **Backup** | 12+ | ✅ Production | DR testing, backup restore |
| **Database** | 10+ | ✅ Production | Database-aware migration |
| **Container** | 6+ | ✅ Production | VM → Kubernetes |

---

## API Patterns

### Common Initialization

```python
import logging
from hyper2kvm.vmcraft import VMCraft

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize VMCraft (required for most operations)
vmcraft = VMCraft(logger)
vmcraft.add_disk("/vms/server.qcow2")
vmcraft.launch()

try:
    # Perform operations...
    pass
finally:
    # Always cleanup
    vmcraft.shutdown()
```

### Error Handling

```python
from hyper2kvm.vmcraft import VMCraft

try:
    vmcraft = VMCraft(logger)
    vmcraft.add_disk("/vms/server.qcow2")
    vmcraft.launch()

    # Operations that might fail
    content = vmcraft.read_file("/etc/config")

except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
except RuntimeError as e:
    logger.error(f"Runtime error: {e}")
finally:
    if vmcraft:
        vmcraft.shutdown()
```

### Context Manager (Recommended)

```python
from hyper2kvm.vmcraft import VMCraft

# Using context manager for automatic cleanup
with VMCraft(logger) as vmcraft:
    vmcraft.add_disk("/vms/server.qcow2")
    vmcraft.launch()

    # Operations...
    content = vmcraft.read_file("/etc/fstab")

# Automatic shutdown when exiting context
```

---

## API Versioning

All APIs follow semantic versioning (SemVer):

- **Major version** (X.0.0): Breaking changes
- **Minor version** (0.X.0): New features, backward compatible
- **Patch version** (0.0.X): Bug fixes

**Current Version**: 1.0.0 (All APIs)

---

## Deprecation Policy

- Deprecated APIs are marked in documentation
- Deprecated features remain for 2 minor versions
- Migration guides provided for breaking changes

---

## Examples Repository

See the [examples directory](../../examples/) for complete, runnable examples:

- `examples/vmcraft/` - VMCraft API examples
- `examples/validation/` - Validation API examples
- `examples/rollback/` - Rollback API examples
- `examples/batch/` - Batch migration examples
- `examples/live/` - Live migration examples

---

## API Support

- **Documentation**: This directory
- **Tutorials**: [docs/tutorials/](../tutorials/)
- **Recipes**: [docs/recipes/](../recipes/)
- **Issues**: [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)

---

## Contributing

Help improve Hyper2KVM APIs:

- **Report Issues**: [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)
- **Suggest Features**: [Feature Requests](https://github.com/ssahani/hyper2kvm/issues/new?labels=enhancement)
- **Submit PRs**: [Contributing Guide](../development/contributing.md)

---

**Last Updated**: March 2026
**API Version**: 1.0.0
