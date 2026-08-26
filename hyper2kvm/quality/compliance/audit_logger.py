# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/compliance/audit_logger.py
"""
Audit logging for migration operations.

Tracks all operations for compliance and forensic analysis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Audit event types."""

    # VM operations
    VM_DETECTED = "vm_detected"
    VM_MIGRATION_STARTED = "vm_migration_started"
    VM_MIGRATION_COMPLETED = "vm_migration_completed"
    VM_MIGRATION_FAILED = "vm_migration_failed"

    # Disk operations
    DISK_MOUNTED = "disk_mounted"
    DISK_UNMOUNTED = "disk_unmounted"
    DISK_MODIFIED = "disk_modified"
    DISK_CONVERTED = "disk_converted"

    # File operations
    FILE_READ = "file_read"
    FILE_WRITTEN = "file_written"
    FILE_DELETED = "file_deleted"
    FILE_MODIFIED = "file_modified"

    # Configuration changes
    CONFIG_MODIFIED = "config_modified"
    NETWORK_CONFIG_CHANGED = "network_config_changed"
    FSTAB_MODIFIED = "fstab_modified"
    BOOTLOADER_MODIFIED = "bootloader_modified"

    # Security operations
    PERMISSIONS_CHANGED = "permissions_changed"
    USER_ACCOUNT_MODIFIED = "user_account_modified"
    SSH_KEY_MODIFIED = "ssh_key_modified"

    # Compliance checks
    COMPLIANCE_SCAN_STARTED = "compliance_scan_started"
    COMPLIANCE_SCAN_COMPLETED = "compliance_scan_completed"
    COMPLIANCE_VIOLATION = "compliance_violation"

    # Database operations
    DATABASE_DETECTED = "database_detected"
    DATABASE_QUIESCED = "database_quiesced"
    DATABASE_RESUMED = "database_resumed"

    # Backup operations
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"

    # System events
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"


@dataclass
class AuditEvent:
    """
    Individual audit event.

    Immutable record of a single auditable operation.
    """

    # Event identification
    event_type: AuditEventType
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str | None = None

    # Actor information
    user: str | None = None
    source_ip: str | None = None
    session_id: str | None = None

    # Target information
    vm_name: str | None = None
    resource: str | None = None  # File path, config key, etc.

    # Event details
    action: str | None = None
    description: str | None = None
    result: str = "success"  # success, failure, error

    # Changes
    old_value: Any | None = None
    new_value: Any | None = None

    # Context
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["event_type"] = self.event_type.value
        return data


class AuditLogger:
    """
    Audit logger for migration operations.

    Writes audit events to structured log files for compliance.
    """

    def __init__(self, logger: logging.Logger, audit_dir: Path, session_id: str | None = None):
        """
        Initialize audit logger.

        Args:
            logger: Logger instance
            audit_dir: Directory to store audit logs
            session_id: Optional session identifier
        """
        self.logger = logger
        self.audit_dir = Path(audit_dir)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create audit directory
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        # Audit log file
        self.audit_file = self.audit_dir / f"audit_{self.session_id}.jsonl"

        # Event counter
        self._event_count = 0

        self.logger.info(f"Audit logger initialized: {self.audit_file}")

    def log_event(
        self,
        event_type: AuditEventType,
        vm_name: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        description: str | None = None,
        result: str = "success",
        old_value: Any | None = None,
        new_value: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """
        Log audit event.

        Args:
            event_type: Type of event
            vm_name: VM being operated on
            resource: Resource being accessed/modified
            action: Action being performed
            description: Human-readable description
            result: Operation result (success, failure, error)
            old_value: Original value before change
            new_value: New value after change
            metadata: Additional context

        Returns:
            Created AuditEvent
        """
        self._event_count += 1

        event = AuditEvent(
            event_type=event_type,
            event_id=f"{self.session_id}_{self._event_count:06d}",
            session_id=self.session_id,
            vm_name=vm_name,
            resource=resource,
            action=action,
            description=description,
            result=result,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata or {},
        )

        # Write to audit log (append as JSON Lines)
        try:
            with open(self.audit_file, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            self.logger.exception(f"Failed to write audit event: {e}")

        # Also log to standard logger for debugging
        self.logger.debug(
            f"AUDIT: {event_type.value} | VM={vm_name} | Resource={resource} | Result={result}"
        )

        return event

    def log_vm_migration_started(
        self, vm_name: str, source: str, destination: str, metadata: dict[str, Any] | None = None
    ) -> AuditEvent:
        """Log VM migration start."""
        return self.log_event(
            event_type=AuditEventType.VM_MIGRATION_STARTED,
            vm_name=vm_name,
            action="migrate",
            description=f"Migration started: {source} → {destination}",
            metadata={"source": source, "destination": destination, **(metadata or {})},
        )

    def log_vm_migration_completed(
        self, vm_name: str, duration_seconds: float, metadata: dict[str, Any] | None = None
    ) -> AuditEvent:
        """Log successful VM migration."""
        return self.log_event(
            event_type=AuditEventType.VM_MIGRATION_COMPLETED,
            vm_name=vm_name,
            action="migrate",
            description=f"Migration completed in {duration_seconds:.1f}s",
            result="success",
            metadata={"duration_seconds": duration_seconds, **(metadata or {})},
        )

    def log_vm_migration_failed(
        self, vm_name: str, error: str, metadata: dict[str, Any] | None = None
    ) -> AuditEvent:
        """Log failed VM migration."""
        return self.log_event(
            event_type=AuditEventType.VM_MIGRATION_FAILED,
            vm_name=vm_name,
            action="migrate",
            description=f"Migration failed: {error}",
            result="failure",
            metadata={"error": error, **(metadata or {})},
        )

    def log_file_modified(
        self,
        vm_name: str,
        file_path: str,
        old_content: str | None = None,
        new_content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log file modification."""
        return self.log_event(
            event_type=AuditEventType.FILE_MODIFIED,
            vm_name=vm_name,
            resource=file_path,
            action="modify",
            description=f"File modified: {file_path}",
            old_value=old_content,
            new_value=new_content,
            metadata=metadata,
        )

    def log_config_modified(
        self,
        vm_name: str,
        config_key: str,
        old_value: Any,
        new_value: Any,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log configuration change."""
        return self.log_event(
            event_type=AuditEventType.CONFIG_MODIFIED,
            vm_name=vm_name,
            resource=config_key,
            action="modify",
            description=f"Configuration changed: {config_key}",
            old_value=old_value,
            new_value=new_value,
            metadata=metadata,
        )

    def log_compliance_scan(
        self, vm_name: str, framework: str, result: str, score: float, metadata: dict[str, Any] | None = None
    ) -> AuditEvent:
        """Log compliance scan completion."""
        return self.log_event(
            event_type=AuditEventType.COMPLIANCE_SCAN_COMPLETED,
            vm_name=vm_name,
            action="compliance_scan",
            description=f"Compliance scan ({framework}): {result}",
            result=result,
            metadata={"framework": framework, "score": score, **(metadata or {})},
        )

    def log_compliance_violation(
        self,
        vm_name: str,
        framework: str,
        check_id: str,
        severity: str,
        finding: str,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log compliance violation."""
        return self.log_event(
            event_type=AuditEventType.COMPLIANCE_VIOLATION,
            vm_name=vm_name,
            resource=check_id,
            action="compliance_check",
            description=f"Compliance violation: {finding}",
            result="failure",
            metadata={
                "framework": framework,
                "check_id": check_id,
                "severity": severity,
                "finding": finding,
                **(metadata or {}),
            },
        )

    def get_events(
        self, event_type: AuditEventType | None = None, vm_name: str | None = None, result: str | None = None
    ) -> list[AuditEvent]:
        """
        Get filtered audit events.

        Args:
            event_type: Filter by event type
            vm_name: Filter by VM name
            result: Filter by result (success, failure, error)

        Returns:
            List of matching AuditEvent objects
        """
        events = []

        try:
            if not self.audit_file.exists():
                return events

            with open(self.audit_file) as f:
                for line in f:
                    data = json.loads(line)

                    # Reconstruct event
                    event = AuditEvent(
                        event_type=AuditEventType(data["event_type"]),
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        event_id=data.get("event_id"),
                        user=data.get("user"),
                        source_ip=data.get("source_ip"),
                        session_id=data.get("session_id"),
                        vm_name=data.get("vm_name"),
                        resource=data.get("resource"),
                        action=data.get("action"),
                        description=data.get("description"),
                        result=data.get("result", "success"),
                        old_value=data.get("old_value"),
                        new_value=data.get("new_value"),
                        metadata=data.get("metadata", {}),
                    )

                    # Apply filters
                    if event_type and event.event_type != event_type:
                        continue
                    if vm_name and event.vm_name != vm_name:
                        continue
                    if result and event.result != result:
                        continue

                    events.append(event)

        except Exception as e:
            self.logger.exception(f"Failed to read audit events: {e}")

        return events

    def get_summary(self) -> dict[str, Any]:
        """
        Get audit log summary.

        Returns:
            Summary statistics dict
        """
        events = self.get_events()

        summary = {
            "total_events": len(events),
            "by_type": {},
            "by_result": {"success": 0, "failure": 0, "error": 0},
            "vms_affected": set(),
            "start_time": None,
            "end_time": None,
        }

        for event in events:
            # Count by type
            event_type_name = event.event_type.value
            summary["by_type"][event_type_name] = summary["by_type"].get(event_type_name, 0) + 1

            # Count by result
            if event.result in summary["by_result"]:
                summary["by_result"][event.result] += 1

            # Track VMs
            if event.vm_name:
                summary["vms_affected"].add(event.vm_name)

            # Track time range
            if summary["start_time"] is None or event.timestamp < summary["start_time"]:
                summary["start_time"] = event.timestamp
            if summary["end_time"] is None or event.timestamp > summary["end_time"]:
                summary["end_time"] = event.timestamp

        # Convert set to list for JSON serialization
        summary["vms_affected"] = list(summary["vms_affected"])

        return summary
