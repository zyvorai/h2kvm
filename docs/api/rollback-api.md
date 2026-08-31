# Rollback API Reference

**Module**: `h2kvm.rollback`
**Version**: 1.0.0
**Status**: Production-Ready

Complete API reference for the Rollback Framework, providing comprehensive migration rollback capabilities with snapshot management, state tracking, execution, and validation.

---

## Overview

The Rollback API provides enterprise-grade rollback capabilities for recovering from failed migrations. Features include:

- **Snapshot Management**: Create, restore, and manage VM snapshots
- **State Tracking**: Track migration progress with reversible checkpoints
- **Rollback Execution**: Execute full, partial, or incremental rollbacks
- **Rollback Validation**: Verify rollback success
- **Report Generation**: JSON and Markdown rollback reports

---

## Quick Start

```python
from h2kvm.rollback import RollbackOrchestrator
from pathlib import Path
import logging

# Setup
logger = logging.getLogger(__name__)
orchestrator = RollbackOrchestrator(logger, snapshot_dir=Path("/snapshots"))

# Create pre-migration snapshot
snapshot = orchestrator.snapshot_manager.create_snapshot(
    "/vms/production/app-server.qcow2",
    compute_checksum=True
)

print(f"Snapshot created: {snapshot.snapshot_id}")

# ... perform migration ...

# If migration fails, execute full rollback
report = orchestrator.execute_full_rollback(
    snapshot.snapshot_id,
    verify_checksum=True,
    validate=True
)

if report.status == "SUCCESS":
    print("✓ Rollback completed successfully")
else:
    print(f"✗ Rollback failed: {report.error}")

# Save rollback report
orchestrator.save_report(report, Path("/reports"), json_report=True, markdown_report=True)
```

---

## Core Classes

### RollbackOrchestrator

**Purpose**: Orchestrate complete rollback workflows with snapshot management, execution, and validation

**Import**:
```python
from h2kvm.rollback import RollbackOrchestrator
```

**Constructor**:
```python
RollbackOrchestrator(
    logger: logging.Logger,
    snapshot_dir: Path | None = None,
    state_dir: Path | None = None
)
```

**Parameters**:
- `logger`: Logger instance for operation logging
- `snapshot_dir`: Directory for snapshot storage (default: /var/lib/h2kvm/snapshots)
- `state_dir`: Directory for state tracking (default: /var/lib/h2kvm/state)

**Attributes**:
- `snapshot_manager`: SnapshotManager instance
- `state_tracker`: StateTracker instance
- `rollback_executor`: RollbackExecutor instance
- `rollback_validator`: RollbackValidator instance

---

#### execute_full_rollback()

Execute full rollback by restoring snapshot.

**Signature**:
```python
def execute_full_rollback(
    self,
    snapshot_id: str,
    *,
    verify_checksum: bool = False,
    validate: bool = True,
) -> RollbackReport
```

**Parameters**:
- `snapshot_id`: Snapshot ID to restore
- `verify_checksum`: Verify snapshot integrity (default: False)
- `validate`: Run validation after rollback (default: True)

**Returns**: `RollbackReport` with rollback results

**Example**:
```python
# Execute full rollback
report = orchestrator.execute_full_rollback(
    "snapshot_20260127_103045_123456",
    verify_checksum=True,
    validate=True
)

# Check results
if report.status == "SUCCESS":
    print(f"✓ Rollback succeeded")
    print(f"  Duration: {report.duration_ms}ms")
    print(f"  Actions: {report.execution_summary['total_actions']}")
else:
    print(f"✗ Rollback failed: {report.error}")
```

---

#### execute_partial_rollback()

Execute partial rollback of specific changes.

**Signature**:
```python
def execute_partial_rollback(
    self,
    *,
    revert_files: list[tuple[str, str]] | None = None,
    remove_files: list[str] | None = None,
    validate: bool = True,
) -> RollbackReport
```

**Parameters**:
- `revert_files`: List of (file_path, backup_path) tuples to revert
- `remove_files`: List of files to remove
- `validate`: Run validation after rollback (default: True)

**Returns**: `RollbackReport` with rollback results

**Example**:
```python
# Revert specific changes
report = orchestrator.execute_partial_rollback(
    revert_files=[
        ("/etc/fstab", "/etc/fstab.backup"),
        ("/boot/grub/grub.cfg", "/boot/grub/grub.cfg.backup"),
    ],
    remove_files=[
        "/etc/systemd/network/50-virtio.network",
        "/etc/udev/rules.d/70-persistent-net.rules",
    ],
    validate=True
)

print(f"Partial rollback: {report.status}")
print(f"Files reverted: {len(report.revert_files or [])}")
print(f"Files removed: {len(report.remove_files or [])}")
```

---

#### save_report()

Save rollback report to files.

**Signature**:
```python
def save_report(
    self,
    report: RollbackReport,
    output_dir: Path,
    *,
    json_report: bool = True,
    markdown_report: bool = True
) -> dict[str, str]
```

**Parameters**:
- `report`: RollbackReport object
- `output_dir`: Directory to save reports
- `json_report`: Generate JSON report (default: True)
- `markdown_report`: Generate Markdown report (default: True)

**Returns**: Dict mapping report type to file path

**Example**:
```python
reports = orchestrator.save_report(
    report,
    Path("/reports/rollback-001"),
    json_report=True,
    markdown_report=True
)

print(f"JSON: {reports['json']}")
print(f"Markdown: {reports['markdown']}")
```

---

### SnapshotManager

**Purpose**: Manage VM snapshots for rollback

**Import**:
```python
from h2kvm.rollback import SnapshotManager
```

**Constructor**:
```python
SnapshotManager(
    logger: logging.Logger,
    snapshot_dir: Path | None = None
)
```

**Parameters**:
- `logger`: Logger instance
- `snapshot_dir`: Snapshot storage directory

---

#### create_snapshot()

Create pre-migration snapshot.

**Signature**:
```python
def create_snapshot(
    self,
    source_path: str | Path,
    snapshot_type: SnapshotType = SnapshotType.QCOW2,
    *,
    compute_checksum: bool = False,
) -> Snapshot
```

**Parameters**:
- `source_path`: Path to VM disk image
- `snapshot_type`: Snapshot type (FULL, QCOW2, LVM, FILESYSTEM)
- `compute_checksum`: Compute SHA256 checksum (default: False)

**Returns**: `Snapshot` object

**Example**:
```python
from h2kvm.rollback import SnapshotManager, SnapshotType

manager = SnapshotManager(logger, Path("/snapshots"))

# Create QCOW2 snapshot (space-efficient)
snapshot = manager.create_snapshot(
    "/vms/production/app-server.qcow2",
    snapshot_type=SnapshotType.QCOW2,
    compute_checksum=True
)

print(f"Snapshot ID: {snapshot.snapshot_id}")
print(f"Snapshot path: {snapshot.snapshot_path}")
print(f"Size: {snapshot.size_bytes} bytes")
print(f"Checksum: {snapshot.checksum}")
```

---

#### restore_snapshot()

Restore VM from snapshot.

**Signature**:
```python
def restore_snapshot(
    self,
    snapshot_id: str,
    *,
    verify_checksum: bool = False
) -> None
```

**Parameters**:
- `snapshot_id`: Snapshot ID to restore
- `verify_checksum`: Verify snapshot integrity before restore (default: False)

**Raises**:
- `RuntimeError`: If snapshot not found or checksum mismatch

**Example**:
```python
# Restore with checksum verification
manager.restore_snapshot(
    "snapshot_20260127_103045_123456",
    verify_checksum=True
)

print("✓ Snapshot restored successfully")
```

---

#### list_snapshots()

List all available snapshots.

**Signature**:
```python
def list_snapshots(
    self,
    source_path: str | Path | None = None
) -> list[Snapshot]
```

**Parameters**:
- `source_path`: Filter by source path (optional)

**Returns**: List of Snapshot objects, sorted by timestamp (newest first)

**Example**:
```python
# List all snapshots
snapshots = manager.list_snapshots()

for snapshot in snapshots:
    print(f"{snapshot.snapshot_id}:")
    print(f"  Source: {snapshot.source_path}")
    print(f"  Created: {snapshot.created_at}")
    print(f"  Size: {snapshot.size_bytes} bytes")

# List snapshots for specific VM
vm_snapshots = manager.list_snapshots("/vms/production/web-server.qcow2")
print(f"Found {len(vm_snapshots)} snapshots for web-server")
```

---

#### delete_snapshot()

Delete snapshot.

**Signature**:
```python
def delete_snapshot(self, snapshot_id: str) -> None
```

**Parameters**:
- `snapshot_id`: Snapshot ID to delete

**Example**:
```python
# Delete old snapshot
manager.delete_snapshot("snapshot_20260120_083045_123456")
print("✓ Snapshot deleted")
```

---

### StateTracker

**Purpose**: Track migration progress with checkpoints

**Import**:
```python
from h2kvm.rollback import StateTracker, MigrationState
```

**Constructor**:
```python
StateTracker(
    logger: logging.Logger,
    migration_id: str | None = None,
    state_file: Path | None = None
)
```

**Parameters**:
- `logger`: Logger instance
- `migration_id`: Unique migration ID (auto-generated if None)
- `state_file`: Path to state file (optional)

---

#### checkpoint()

Create migration state checkpoint.

**Signature**:
```python
def checkpoint(
    self,
    state: MigrationState,
    description: str,
    *,
    reversible: bool = True,
    **data: Any
) -> None
```

**Parameters**:
- `state`: Migration state (enum value)
- `description`: Human-readable description
- `reversible`: Can this checkpoint be rolled back? (default: True)
- `**data`: Additional metadata

**Example**:
```python
from h2kvm.rollback import StateTracker, MigrationState

tracker = StateTracker(logger)

# Track migration progress
tracker.checkpoint(
    MigrationState.SNAPSHOT_CREATED,
    "Created pre-migration snapshot",
    reversible=True,
    snapshot_id="snapshot_20260127_103045"
)

tracker.checkpoint(
    MigrationState.BOOTLOADER_FIXED,
    "Fixed GRUB bootloader for KVM",
    reversible=True,
    bootloader="grub2",
    config="/boot/grub/grub.cfg"
)

tracker.checkpoint(
    MigrationState.COMPLETED,
    "Migration completed successfully",
    reversible=False  # Cannot rollback past completion
)
```

---

#### get_rollback_plan()

Get ordered list of checkpoints to rollback.

**Signature**:
```python
def get_rollback_plan(self) -> list[StateCheckpoint]
```

**Returns**: List of StateCheckpoint objects in reverse order (newest first)

**Note**: Only includes reversible checkpoints after the last irreversible checkpoint

**Example**:
```python
# Get rollback plan
plan = tracker.get_rollback_plan()

print(f"Rollback plan ({len(plan)} steps):")
for i, checkpoint in enumerate(plan, 1):
    print(f"{i}. {checkpoint.state.value}: {checkpoint.description}")
    print(f"   Timestamp: {checkpoint.timestamp}")
```

---

### RollbackExecutor

**Purpose**: Execute rollback actions

**Import**:
```python
from h2kvm.rollback import RollbackExecutor, RollbackAction, RollbackActionType
```

**Constructor**:
```python
RollbackExecutor(logger: logging.Logger)
```

---

#### execute_action()

Execute single rollback action.

**Signature**:
```python
def execute_action(self, action: RollbackAction) -> None
```

**Parameters**:
- `action`: RollbackAction to execute

**Raises**:
- `RuntimeError`: If action execution fails

**Example**:
```python
from h2kvm.rollback import RollbackExecutor, RollbackAction, RollbackActionType

executor = RollbackExecutor(logger)

# Revert file from backup
action = RollbackAction(
    action_type=RollbackActionType.REVERT_FILE,
    description="Revert fstab to original",
    file_path="/etc/fstab",
    backup_path="/etc/fstab.backup"
)

executor.execute_action(action)
print("✓ File reverted")
```

---

#### get_execution_summary()

Get summary of executed actions.

**Signature**:
```python
def get_execution_summary(self) -> dict[str, Any]
```

**Returns**: Dict with execution statistics

**Example**:
```python
summary = executor.get_execution_summary()

print(f"Total actions: {summary['total_actions']}")
print(f"Successful: {summary['successful_actions']}")
print(f"Failed: {summary['failed_actions']}")
print(f"Success rate: {summary['success_rate']:.1%}")
```

---

### RollbackValidator

**Purpose**: Validate rollback success

**Import**:
```python
from h2kvm.rollback import RollbackValidator
```

**Constructor**:
```python
RollbackValidator(logger: logging.Logger)
```

---

#### validate_snapshot_restored()

Validate snapshot was restored successfully.

**Signature**:
```python
def validate_snapshot_restored(
    self,
    original_path: str | Path,
    snapshot_path: str | Path
) -> ValidationResult
```

**Parameters**:
- `original_path`: Path where snapshot was restored
- `snapshot_path`: Original snapshot path

**Returns**: `ValidationResult` with status

**Example**:
```python
from h2kvm.rollback import RollbackValidator

validator = RollbackValidator(logger)

result = validator.validate_snapshot_restored(
    "/vms/production/app-server.qcow2",
    "/snapshots/snapshot_20260127_103045/app-server.qcow2"
)

if result.status == ValidationStatus.PASS:
    print("✓ Snapshot restored successfully")
else:
    print(f"✗ Validation failed: {result.message}")
```

---

## Data Structures

### SnapshotType

**Enum**: Type of snapshot

```python
class SnapshotType(Enum):
    FULL = "full"              # Complete copy of disk
    QCOW2 = "qcow2"            # QCOW2 snapshot with backing file
    LVM = "lvm"                # LVM snapshot
    FILESYSTEM = "filesystem"  # Filesystem-level backup
```

### MigrationState

**Enum**: Migration state (13 states)

```python
class MigrationState(Enum):
    NOT_STARTED = "not_started"
    SNAPSHOT_CREATED = "snapshot_created"
    PRE_MIGRATION_CHECKS = "pre_migration_checks"
    STORAGE_ACTIVATED = "storage_activated"
    FILESYSTEM_MOUNTED = "filesystem_mounted"
    BOOTLOADER_FIXED = "bootloader_fixed"
    DRIVERS_INSTALLED = "drivers_installed"
    NETWORK_CONFIGURED = "network_configured"
    FSTAB_STABILIZED = "fstab_stabilized"
    VALIDATION_PASSED = "validation_passed"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
```

### Snapshot

**Dataclass**: Snapshot metadata

```python
@dataclass
class Snapshot:
    snapshot_id: str
    source_path: str
    snapshot_path: str
    snapshot_type: SnapshotType
    size_bytes: int
    created_at: str
    checksum: str | None = None
```

### RollbackReport

**Dataclass**: Rollback report

```python
@dataclass
class RollbackReport:
    rollback_id: str
    strategy: RollbackStrategy
    status: str  # "SUCCESS", "FAILED", "PARTIAL"
    started_at: str
    completed_at: str
    duration_ms: float
    snapshot_id: str | None
    execution_summary: dict[str, Any]
    validation_summary: dict[str, Any]
    error: str | None = None
```

---

## Complete Example

```python
import logging
from pathlib import Path
from h2kvm.rollback import (
    RollbackOrchestrator,
    SnapshotType,
    MigrationState
)

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_migration_with_rollback(vm_path: str, target_path: str):
    """Execute migration with rollback capability."""

    # Create orchestrator
    orchestrator = RollbackOrchestrator(
        logger,
        snapshot_dir=Path("/snapshots"),
        state_dir=Path("/var/lib/h2kvm/state")
    )

    # Create pre-migration snapshot
    logger.info("Creating pre-migration snapshot...")
    snapshot = orchestrator.snapshot_manager.create_snapshot(
        vm_path,
        snapshot_type=SnapshotType.QCOW2,
        compute_checksum=True
    )

    logger.info(f"Snapshot created: {snapshot.snapshot_id}")

    # Track migration state
    tracker = orchestrator.state_tracker
    tracker.checkpoint(
        MigrationState.SNAPSHOT_CREATED,
        f"Created snapshot {snapshot.snapshot_id}",
        snapshot_id=snapshot.snapshot_id
    )

    try:
        # Perform migration steps...
        logger.info("Performing migration...")

        # Example: fix bootloader
        tracker.checkpoint(
            MigrationState.BOOTLOADER_FIXED,
            "Fixed bootloader for KVM",
            reversible=True
        )

        # Example: configure network
        tracker.checkpoint(
            MigrationState.NETWORK_CONFIGURED,
            "Configured network for VirtIO",
            reversible=True
        )

        # Mark as completed
        tracker.checkpoint(
            MigrationState.COMPLETED,
            "Migration completed successfully",
            reversible=False
        )

        logger.info("✓ Migration successful!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")

        # Execute rollback
        logger.info("Initiating rollback...")
        report = orchestrator.execute_full_rollback(
            snapshot.snapshot_id,
            verify_checksum=True,
            validate=True
        )

        if report.status == "SUCCESS":
            logger.info("✓ Rollback completed successfully")

            # Save rollback report
            reports = orchestrator.save_report(
                report,
                Path("/reports/rollback"),
                json_report=True,
                markdown_report=True
            )

            logger.info(f"Rollback report: {reports['markdown']}")
        else:
            logger.error(f"✗ Rollback failed: {report.error}")

        return False

# Example usage
if __name__ == "__main__":
    success = safe_migration_with_rollback(
        "/vms/production/app-server.qcow2",
        "/vms/migrated/app-server.qcow2"
    )

    if success:
        print("Migration completed successfully")
    else:
        print("Migration failed, VM rolled back to original state")
```

---

## See Also

- **[Rollback Framework Guide](../features/rollback-framework.md)**: Feature documentation
- **[Validation API](validation-api.md)**: Post-migration validation
- **[GuestKit API](guestkit-api.md)**: Guest filesystem manipulation
- **[Troubleshooting Guide](../guides/troubleshooting.md)**: Rollback troubleshooting

---

**Last Updated**: March 2026
**API Version**: 1.0.0
