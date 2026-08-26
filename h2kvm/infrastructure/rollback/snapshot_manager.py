# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/rollback/snapshot_manager.py
"""
Snapshot management for rollback support.

Manages pre-migration snapshots and disk image backups for rollback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from h2kvm.core.exceptions import DiskConversionError, InfrastructureError

logger = logging.getLogger(__name__)


class SnapshotType(Enum):
    """Snapshot types."""

    FULL = "full"  # Full disk image copy
    QCOW2 = "qcow2"  # QCOW2 snapshot
    LVM = "lvm"  # LVM snapshot
    FILESYSTEM = "filesystem"  # Filesystem-level backup


@dataclass
class Snapshot:
    """
    Snapshot metadata.

    Attributes:
        snapshot_id: Unique snapshot identifier
        snapshot_type: Type of snapshot
        source_path: Original disk image path
        snapshot_path: Snapshot file path
        created_at: Snapshot creation timestamp
        size_bytes: Snapshot size in bytes
        checksum: SHA256 checksum of snapshot
        metadata: Additional snapshot metadata
    """

    snapshot_id: str
    snapshot_type: SnapshotType
    source_path: str
    snapshot_path: str
    created_at: datetime
    size_bytes: int
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.value,
            "source_path": self.source_path,
            "snapshot_path": self.snapshot_path,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        """Create from dictionary."""
        return cls(
            snapshot_id=data["snapshot_id"],
            snapshot_type=SnapshotType(data["snapshot_type"]),
            source_path=data["source_path"],
            snapshot_path=data["snapshot_path"],
            created_at=datetime.fromisoformat(data["created_at"]),
            size_bytes=data["size_bytes"],
            checksum=data.get("checksum"),
            metadata=data.get("metadata", {}),
        )


class SnapshotManager:
    """
    Snapshot manager.

    Manages creation, restoration, and cleanup of snapshots for rollback.
    """

    def __init__(self, logger: logging.Logger, snapshot_dir: Path | None = None):
        """
        Initialize snapshot manager.

        Args:
            logger: Logger instance
            snapshot_dir: Directory for storing snapshots (default: /var/lib/h2kvm/snapshots)
        """
        self.logger = logger
        self.snapshot_dir = snapshot_dir or Path("/var/lib/h2kvm/snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self._snapshots: dict[str, Snapshot] = {}
        self._load_snapshots()

    def _load_snapshots(self) -> None:
        """Load snapshots from metadata files."""
        metadata_dir = self.snapshot_dir / "metadata"
        if not metadata_dir.exists():
            return

        for metadata_file in metadata_dir.glob("*.json"):
            try:
                data = json.loads(metadata_file.read_text())
                snapshot = Snapshot.from_dict(data)
                self._snapshots[snapshot.snapshot_id] = snapshot
            except Exception as e:
                self.logger.warning(f"Failed to load snapshot metadata {metadata_file}: {e}")

    def _save_snapshot_metadata(self, snapshot: Snapshot) -> None:
        """Save snapshot metadata to file."""
        metadata_dir = self.snapshot_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = metadata_dir / f"{snapshot.snapshot_id}.json"
        metadata_file.write_text(json.dumps(snapshot.to_dict(), indent=2))

    def create_snapshot(
        self,
        source_path: str | Path,
        snapshot_type: SnapshotType = SnapshotType.QCOW2,
        *,
        compute_checksum: bool = False,
    ) -> Snapshot:
        """
        Create snapshot of disk image.

        Args:
            source_path: Path to source disk image
            snapshot_type: Type of snapshot to create
            compute_checksum: Compute SHA256 checksum (slower but verifiable)

        Returns:
            Snapshot metadata

        Raises:
            RuntimeError: If snapshot creation fails
        """
        source_path = Path(source_path)

        if not source_path.exists():
            raise DiskConversionError(
                code=66, msg=f"Cannot create snapshot: source image not found at {source_path}"
            ).with_context(
                solutions=[
                    "Verify the disk image path is correct",
                    "Ensure the file exists before creating snapshot",
                ],
                source_path=str(source_path),
            )

        # Generate snapshot ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        snapshot_id = f"snapshot_{source_path.stem}_{timestamp}"

        self.logger.info(f"Creating {snapshot_type.value} snapshot: {snapshot_id}")

        # Create snapshot based on type
        if snapshot_type == SnapshotType.QCOW2:
            snapshot = self._create_qcow2_snapshot(source_path, snapshot_id)
        elif snapshot_type == SnapshotType.FULL:
            snapshot = self._create_full_snapshot(source_path, snapshot_id)
        else:
            raise InfrastructureError(
                code=38, msg=f"Snapshot type '{snapshot_type.value}' is not yet supported"
            ).with_context(
                solutions=[
                    "Use snapshot_type=SnapshotType.QCOW2 for QCOW2 snapshots",
                    "Use snapshot_type=SnapshotType.FULL for full disk copies",
                ],
                requested_type=snapshot_type.value,
                supported_types=["qcow2", "full"],
            )

        # Compute checksum if requested
        if compute_checksum:
            self.logger.info("Computing snapshot checksum...")
            snapshot.checksum = self._compute_checksum(Path(snapshot.snapshot_path))

        # Save metadata
        self._save_snapshot_metadata(snapshot)
        self._snapshots[snapshot_id] = snapshot

        self.logger.info(f"Snapshot created: {snapshot_id} ({snapshot.size_bytes / (1024**3):.2f} GB)")

        return snapshot

    def _create_qcow2_snapshot(self, source_path: Path, snapshot_id: str) -> Snapshot:
        """Create QCOW2 snapshot using qemu-img."""
        # Create snapshot directory
        snapshot_dir = self.snapshot_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = snapshot_dir / f"{source_path.name}.snapshot"

        try:
            # Create QCOW2 snapshot with backing file
            cmd = [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                "-b",
                str(source_path.absolute()),
                "-F",
                "qcow2",
                str(snapshot_path),
            ]

            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Get snapshot size
            size_bytes = snapshot_path.stat().st_size

            return Snapshot(
                snapshot_id=snapshot_id,
                snapshot_type=SnapshotType.QCOW2,
                source_path=str(source_path),
                snapshot_path=str(snapshot_path),
                created_at=datetime.now(),
                size_bytes=size_bytes,
                metadata={"backing_file": str(source_path)},
            )

        except subprocess.CalledProcessError as e:
            raise DiskConversionError(
                code=73, msg=f"Failed to create QCOW2 snapshot for {source_path.name}"
            ).with_context(
                solutions=[
                    "Ensure qemu-img is installed: apt install qemu-utils",
                    "Verify sufficient disk space in snapshot directory",
                    "Check source image is a valid QCOW2 file",
                ],
                source_path=str(source_path),
                snapshot_id=snapshot_id,
                error=e.stderr,
            ) from e

    def _create_full_snapshot(self, source_path: Path, snapshot_id: str) -> Snapshot:
        """Create full disk image copy."""
        # Create snapshot directory
        snapshot_dir = self.snapshot_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = snapshot_dir / source_path.name

        try:
            self.logger.info(f"Copying {source_path} to {snapshot_path}...")
            shutil.copy2(source_path, snapshot_path)

            size_bytes = snapshot_path.stat().st_size

            return Snapshot(
                snapshot_id=snapshot_id,
                snapshot_type=SnapshotType.FULL,
                source_path=str(source_path),
                snapshot_path=str(snapshot_path),
                created_at=datetime.now(),
                size_bytes=size_bytes,
            )

        except Exception as e:
            raise DiskConversionError(
                code=73, msg=f"Failed to create full snapshot copy of {source_path.name}"
            ).with_context(
                solutions=[
                    "Verify sufficient disk space in snapshot directory",
                    "Check file permissions allow reading source and writing snapshot",
                    f"Ensure snapshot directory is writable: {snapshot_dir}",
                ],
                source_path=str(source_path),
                snapshot_dir=str(snapshot_dir),
                snapshot_id=snapshot_id,
            ) from e

    def _compute_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum of file."""
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest()

    def restore_snapshot(self, snapshot_id: str, *, verify_checksum: bool = False) -> None:
        """
        Restore snapshot to original location.

        Args:
            snapshot_id: Snapshot identifier
            verify_checksum: Verify snapshot checksum before restore

        Raises:
            RuntimeError: If restore fails
        """
        if snapshot_id not in self._snapshots:
            raise InfrastructureError(code=2, msg=f"Snapshot '{snapshot_id}' not found").with_context(
                solutions=[
                    "List available snapshots with list_snapshots()",
                    "Verify the snapshot ID is correct",
                    f"Check snapshot directory: {self.snapshot_dir}",
                ],
                snapshot_id=snapshot_id,
            )

        snapshot = self._snapshots[snapshot_id]

        self.logger.info(f"Restoring snapshot: {snapshot_id}")

        # Verify checksum if requested and available
        if verify_checksum and snapshot.checksum:
            self.logger.info("Verifying snapshot checksum...")
            current_checksum = self._compute_checksum(Path(snapshot.snapshot_path))
            if current_checksum != snapshot.checksum:
                raise RuntimeError(
                    f"Snapshot checksum mismatch: expected {snapshot.checksum}, got {current_checksum}"
                )

        # Restore based on snapshot type
        if snapshot.snapshot_type == SnapshotType.FULL:
            self._restore_full_snapshot(snapshot)
        elif snapshot.snapshot_type == SnapshotType.QCOW2:
            self._restore_qcow2_snapshot(snapshot)
        else:
            raise InfrastructureError(
                code=38,
                msg=f"Snapshot restore for type '{snapshot.snapshot_type.value}' is not yet implemented",
            ).with_context(
                solutions=[
                    "Use QCOW2 or FULL snapshot types which support restore",
                    "Manually restore the snapshot file if needed",
                ],
                snapshot_type=snapshot.snapshot_type.value,
                snapshot_id=snapshot.snapshot_id,
            )

        self.logger.info(f"Snapshot restored: {snapshot_id}")

    def _restore_full_snapshot(self, snapshot: Snapshot) -> None:
        """Restore full snapshot by copying back."""
        source_path = Path(snapshot.source_path)
        snapshot_path = Path(snapshot.snapshot_path)

        # Backup current state before restore
        if source_path.exists():
            backup_path = source_path.with_suffix(source_path.suffix + ".pre-restore")
            self.logger.info(f"Backing up current image to {backup_path}")
            shutil.move(source_path, backup_path)

        # Copy snapshot to original location
        self.logger.info(f"Restoring {snapshot_path} to {source_path}")
        shutil.copy2(snapshot_path, source_path)

    def _restore_qcow2_snapshot(self, snapshot: Snapshot) -> None:
        """Restore QCOW2 snapshot."""
        # For QCOW2 snapshots with backing files, we can commit changes back
        # or replace the original with the snapshot
        snapshot_path = Path(snapshot.snapshot_path)
        source_path = Path(snapshot.source_path)

        # Create backup of current state
        if source_path.exists():
            backup_path = source_path.with_suffix(source_path.suffix + ".pre-restore")
            self.logger.info(f"Backing up current image to {backup_path}")
            shutil.move(source_path, backup_path)

        # Copy snapshot to original location
        self.logger.info(f"Restoring {snapshot_path} to {source_path}")
        shutil.copy2(snapshot_path, source_path)

    def delete_snapshot(self, snapshot_id: str) -> None:
        """
        Delete snapshot.

        Args:
            snapshot_id: Snapshot identifier
        """
        if snapshot_id not in self._snapshots:
            raise InfrastructureError(code=2, msg=f"Snapshot '{snapshot_id}' not found").with_context(
                solutions=[
                    "List available snapshots with list_snapshots()",
                    "Verify the snapshot ID is correct",
                    f"Check snapshot directory: {self.snapshot_dir}",
                ],
                snapshot_id=snapshot_id,
            )

        snapshot = self._snapshots[snapshot_id]

        self.logger.info(f"Deleting snapshot: {snapshot_id}")

        # Delete snapshot files
        snapshot_path = Path(snapshot.snapshot_path)
        if snapshot_path.exists():
            if snapshot_path.is_file():
                snapshot_path.unlink()
            elif snapshot_path.is_dir():
                shutil.rmtree(snapshot_path)

        # Delete snapshot directory if empty
        snapshot_dir = snapshot_path.parent
        if snapshot_dir.exists() and not list(snapshot_dir.iterdir()):
            snapshot_dir.rmdir()

        # Delete metadata
        metadata_file = self.snapshot_dir / "metadata" / f"{snapshot_id}.json"
        if metadata_file.exists():
            metadata_file.unlink()

        # Remove from tracking
        del self._snapshots[snapshot_id]

        self.logger.info(f"Snapshot deleted: {snapshot_id}")

    def list_snapshots(self, source_path: str | None = None) -> list[Snapshot]:
        """
        List snapshots.

        Args:
            source_path: Optional filter by source path

        Returns:
            List of snapshots
        """
        snapshots = list(self._snapshots.values())

        if source_path:
            snapshots = [s for s in snapshots if s.source_path == str(source_path)]

        # Sort by creation time (newest first)
        snapshots.sort(key=lambda s: s.created_at, reverse=True)

        return snapshots

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        """Get snapshot by ID."""
        return self._snapshots.get(snapshot_id)
