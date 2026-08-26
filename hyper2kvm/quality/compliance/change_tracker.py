# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/compliance/change_tracker.py
"""
Change tracking for VM modifications.

Tracks all changes made during migration for audit and rollback.
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


class ChangeType(Enum):
    """Types of changes tracked."""

    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_PERMISSIONS = "file_permissions"
    FILE_OWNERSHIP = "file_ownership"

    PACKAGE_INSTALLED = "package_installed"
    PACKAGE_REMOVED = "package_removed"
    PACKAGE_UPGRADED = "package_upgraded"

    SERVICE_ENABLED = "service_enabled"
    SERVICE_DISABLED = "service_disabled"
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"

    KERNEL_PARAMETER = "kernel_parameter"
    SYSCTL_PARAMETER = "sysctl_parameter"
    ENVIRONMENT_VARIABLE = "environment_variable"

    NETWORK_CONFIG = "network_config"
    HOSTNAME = "hostname"
    FSTAB_ENTRY = "fstab_entry"
    BOOTLOADER = "bootloader"

    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"
    USER_MODIFIED = "user_modified"
    GROUP_MODIFIED = "group_modified"


@dataclass
class Change:
    """
    Individual change record.

    Represents a single modification made during migration.
    """

    # Change identification
    change_type: ChangeType
    timestamp: datetime = field(default_factory=datetime.now)
    change_id: str | None = None

    # Target
    resource: str | None = None  # File path, package name, etc.
    description: str | None = None

    # Change details
    old_value: Any | None = None
    new_value: Any | None = None

    # Rollback info
    reversible: bool = True
    rollback_command: str | None = None

    # Context
    reason: str | None = None  # Why was this change made?
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["change_type"] = self.change_type.value
        return data


class ChangeTracker:
    """
    Change tracker for VM modifications.

    Tracks all changes made during migration for audit and potential rollback.
    """

    def __init__(self, logger: logging.Logger, output_dir: Path, vm_name: str):
        """
        Initialize change tracker.

        Args:
            logger: Logger instance
            output_dir: Directory to store change logs
            vm_name: Name of VM being tracked
        """
        self.logger = logger
        self.output_dir = Path(output_dir)
        self.vm_name = vm_name

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Change log file
        self.change_file = self.output_dir / f"changes_{vm_name}.jsonl"

        # Change counter
        self._change_count = 0

        self.logger.info(f"Change tracker initialized for {vm_name}: {self.change_file}")

    def track_change(
        self,
        change_type: ChangeType,
        resource: str | None = None,
        description: str | None = None,
        old_value: Any | None = None,
        new_value: Any | None = None,
        reversible: bool = True,
        rollback_command: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Change:
        """
        Track a change.

        Args:
            change_type: Type of change
            resource: Resource being modified
            description: Human-readable description
            old_value: Original value
            new_value: New value
            reversible: Whether change can be rolled back
            rollback_command: Command to rollback change
            reason: Reason for change
            metadata: Additional context

        Returns:
            Created Change object
        """
        self._change_count += 1

        change = Change(
            change_type=change_type,
            change_id=f"{self.vm_name}_{self._change_count:06d}",
            resource=resource,
            description=description,
            old_value=old_value,
            new_value=new_value,
            reversible=reversible,
            rollback_command=rollback_command,
            reason=reason,
            metadata=metadata or {},
        )

        # Write to change log (append as JSON Lines)
        try:
            with open(self.change_file, "a") as f:
                f.write(json.dumps(change.to_dict()) + "\n")
        except Exception as e:
            self.logger.exception(f"Failed to write change record: {e}")

        self.logger.debug(f"CHANGE: {change_type.value} | Resource={resource} | {old_value} → {new_value}")

        return change

    def track_file_modified(
        self,
        file_path: str,
        old_content: str | None = None,
        new_content: str | None = None,
        reason: str | None = None,
    ) -> Change:
        """Track file modification."""
        return self.track_change(
            change_type=ChangeType.FILE_MODIFIED,
            resource=file_path,
            description=f"Modified {file_path}",
            old_value=old_content,
            new_value=new_content,
            reversible=True,
            rollback_command=f"Restore original content to {file_path}",
            reason=reason,
        )

    def track_file_created(
        self, file_path: str, content: str | None = None, reason: str | None = None
    ) -> Change:
        """Track file creation."""
        return self.track_change(
            change_type=ChangeType.FILE_CREATED,
            resource=file_path,
            description=f"Created {file_path}",
            new_value=content,
            reversible=True,
            rollback_command=f"rm -f {file_path}",
            reason=reason,
        )

    def track_file_deleted(
        self, file_path: str, old_content: str | None = None, reason: str | None = None
    ) -> Change:
        """Track file deletion."""
        return self.track_change(
            change_type=ChangeType.FILE_DELETED,
            resource=file_path,
            description=f"Deleted {file_path}",
            old_value=old_content,
            reversible=old_content is not None,
            rollback_command=f"Restore {file_path}" if old_content else None,
            reason=reason,
        )

    def track_package_installed(
        self, package_name: str, version: str | None = None, reason: str | None = None
    ) -> Change:
        """Track package installation."""
        return self.track_change(
            change_type=ChangeType.PACKAGE_INSTALLED,
            resource=package_name,
            description=f"Installed {package_name}" + (f" {version}" if version else ""),
            new_value=version,
            reversible=True,
            rollback_command=f"Remove {package_name}",
            reason=reason,
            metadata={"version": version} if version else {},
        )

    def track_service_enabled(self, service_name: str, reason: str | None = None) -> Change:
        """Track service enablement."""
        return self.track_change(
            change_type=ChangeType.SERVICE_ENABLED,
            resource=service_name,
            description=f"Enabled {service_name}",
            old_value="disabled",
            new_value="enabled",
            reversible=True,
            rollback_command=f"systemctl disable {service_name}",
            reason=reason,
        )

    def track_network_config(
        self,
        interface: str,
        old_config: dict[str, Any] | None = None,
        new_config: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Change:
        """Track network configuration change."""
        return self.track_change(
            change_type=ChangeType.NETWORK_CONFIG,
            resource=interface,
            description=f"Network config changed: {interface}",
            old_value=old_config,
            new_value=new_config,
            reversible=True,
            rollback_command=f"Restore network config for {interface}",
            reason=reason,
        )

    def track_fstab_entry(
        self,
        device: str,
        old_entry: str | None = None,
        new_entry: str | None = None,
        reason: str | None = None,
    ) -> Change:
        """Track fstab modification."""
        return self.track_change(
            change_type=ChangeType.FSTAB_ENTRY,
            resource=device,
            description=f"Fstab entry modified: {device}",
            old_value=old_entry,
            new_value=new_entry,
            reversible=True,
            rollback_command="Restore original fstab entry",
            reason=reason,
        )

    def get_changes(
        self, change_type: ChangeType | None = None, resource: str | None = None
    ) -> list[Change]:
        """
        Get filtered changes.

        Args:
            change_type: Filter by change type
            resource: Filter by resource

        Returns:
            List of matching Change objects
        """
        changes = []

        try:
            if not self.change_file.exists():
                return changes

            with open(self.change_file) as f:
                for line in f:
                    data = json.loads(line)

                    # Reconstruct change
                    change = Change(
                        change_type=ChangeType(data["change_type"]),
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        change_id=data.get("change_id"),
                        resource=data.get("resource"),
                        description=data.get("description"),
                        old_value=data.get("old_value"),
                        new_value=data.get("new_value"),
                        reversible=data.get("reversible", True),
                        rollback_command=data.get("rollback_command"),
                        reason=data.get("reason"),
                        metadata=data.get("metadata", {}),
                    )

                    # Apply filters
                    if change_type and change.change_type != change_type:
                        continue
                    if resource and change.resource != resource:
                        continue

                    changes.append(change)

        except Exception as e:
            self.logger.exception(f"Failed to read changes: {e}")

        return changes

    def get_summary(self) -> dict[str, Any]:
        """
        Get change summary.

        Returns:
            Summary statistics dict
        """
        changes = self.get_changes()

        summary = {
            "total_changes": len(changes),
            "by_type": {},
            "reversible_count": 0,
            "irreversible_count": 0,
            "resources_affected": set(),
            "start_time": None,
            "end_time": None,
        }

        for change in changes:
            # Count by type
            change_type_name = change.change_type.value
            summary["by_type"][change_type_name] = summary["by_type"].get(change_type_name, 0) + 1

            # Count reversibility
            if change.reversible:
                summary["reversible_count"] += 1
            else:
                summary["irreversible_count"] += 1

            # Track resources
            if change.resource:
                summary["resources_affected"].add(change.resource)

            # Track time range
            if summary["start_time"] is None or change.timestamp < summary["start_time"]:
                summary["start_time"] = change.timestamp
            if summary["end_time"] is None or change.timestamp > summary["end_time"]:
                summary["end_time"] = change.timestamp

        # Convert set to list
        summary["resources_affected"] = list(summary["resources_affected"])

        return summary

    def generate_rollback_script(self, output_file: Path | None = None) -> str:
        """
        Generate rollback script.

        Args:
            output_file: Optional path to write script

        Returns:
            Rollback script content
        """
        changes = self.get_changes()

        script_lines = [
            "#!/bin/bash",
            "# Rollback script for VM migration changes",
            f"# VM: {self.vm_name}",
            f"# Generated: {datetime.now().isoformat()}",
            "",
            "set -e  # Exit on error",
            "",
        ]

        # Reverse changes (newest first for rollback)
        reversible_changes = [c for c in reversed(changes) if c.reversible and c.rollback_command]

        if not reversible_changes:
            script_lines.append("# No reversible changes found")
        else:
            for change in reversible_changes:
                script_lines.extend(
                    [
                        f"# {change.change_type.value}: {change.description}",
                        f"echo 'Rolling back: {change.description}'",
                        change.rollback_command,
                        "",
                    ]
                )

        script_content = "\n".join(script_lines)

        # Write to file if requested
        if output_file:
            Path(output_file).write_text(script_content)
            self.logger.info(f"Rollback script written to: {output_file}")

        return script_content
