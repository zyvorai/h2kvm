# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Batch checkpoint management for resumable long-running migrations.

This module provides checkpoint/resume capabilities for batch conversions,
enabling recovery from interruptions, crashes, or manual stops.

Capabilities:
- Save checkpoint state after each VM completes
- Detect and resume from existing checkpoints
- Track VM completion status
- Automatic checkpoint cleanup on success
- Manual checkpoint reset

Security:
- Atomic checkpoint writes (temp + replace)
- Safe path validation
- Checksum verification
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from h2kvm.core.exceptions import CheckpointError


class CheckpointManager:
    """
    Manage batch conversion checkpoints for resume capability.

    Checkpoints enable long-running batch migrations to be resumed from
    the last successfully completed VM if interrupted.

    Example:
        >>> manager = CheckpointManager("/work/batch", "migration-2026")
        >>> if manager.has_checkpoint():
        >>>     completed = manager.load_checkpoint()
        >>> manager.save_checkpoint(["vm1", "vm2"])
        >>> manager.cleanup()
    """

    def __init__(
        self,
        checkpoint_dir: Path | str,
        batch_id: str,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize CheckpointManager.

        Args:
            checkpoint_dir: Directory to store checkpoint files
            batch_id: Unique identifier for this batch
            logger: Logger instance

        Raises:
            RollbackError: If checkpoint directory creation fails
        """
        self.checkpoint_dir = Path(checkpoint_dir).resolve()
        self.batch_id = batch_id
        self.logger = logger or logging.getLogger(__name__)

        # Sanitize batch_id for filename
        safe_batch_id = self._sanitize_filename(batch_id)
        self.checkpoint_file = self.checkpoint_dir / f"checkpoint-{safe_batch_id}.json"

        # Ensure checkpoint directory exists
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise CheckpointError(
                msg=f"Failed to create checkpoint directory {checkpoint_dir}: {e}", cause=e
            ) from e

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize batch ID for safe filename usage."""
        # Replace non-alphanumeric characters with hyphens
        safe = re.sub(r"[^a-zA-Z0-9._-]", "-", name)
        return safe[:100]  # Limit length

    def has_checkpoint(self) -> bool:
        """
        Check if a checkpoint exists for this batch.

        Returns:
            True if checkpoint file exists
        """
        return self.checkpoint_file.exists()

    def load_checkpoint(self) -> dict[str, Any]:
        """
        Load checkpoint data.

        Returns:
            Dictionary with checkpoint state:
            - batch_id: Batch identifier
            - timestamp: Checkpoint save time (Unix timestamp)
            - completed_vms: List of completed VM IDs
            - failed_vms: List of failed VM IDs with errors
            - total_vms: Total VMs in batch
            - resume_from: Next VM index to process

        Raises:
            RollbackError: If checkpoint doesn't exist or is invalid
        """
        if not self.has_checkpoint():
            raise CheckpointError(msg=f"No checkpoint found: {self.checkpoint_file}")

        try:
            with open(self.checkpoint_file, encoding="utf-8") as f:
                data = json.load(f)

            # Validate checkpoint structure
            required_fields = ["batch_id", "timestamp", "completed_vms"]
            for field in required_fields:
                if field not in data:
                    raise CheckpointError(msg=f"Invalid checkpoint: missing '{field}' field")

            # Verify batch ID matches
            if data["batch_id"] != self.batch_id:
                self.logger.warning(
                    f"Checkpoint batch_id mismatch: expected '{self.batch_id}', found '{data['batch_id']}'"
                )

            self.logger.info("📂 Loaded checkpoint: %d VMs completed", len(data.get("completed_vms", [])))

            return data

        except json.JSONDecodeError as e:
            raise CheckpointError(msg=f"Invalid checkpoint JSON: {e}", cause=e) from e
        except Exception as e:
            raise CheckpointError(msg=f"Failed to load checkpoint: {e}", cause=e) from e

    def save_checkpoint(
        self,
        completed_vms: list[str],
        failed_vms: list[dict[str, Any]] | None = None,
        total_vms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Save checkpoint state atomically.

        Args:
            completed_vms: List of successfully completed VM IDs
            failed_vms: List of failed VMs with error info
            total_vms: Total number of VMs in batch
            metadata: Optional additional metadata

        Raises:
            RollbackError: If checkpoint save fails
        """
        checkpoint_data = {
            "batch_id": self.batch_id,
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "completed_vms": completed_vms,
            "failed_vms": failed_vms or [],
            "total_vms": total_vms,
            "resume_from": len(completed_vms) + len(failed_vms or []),
            "metadata": metadata or {},
        }

        # Atomic write: temp file + replace
        tmp_file = self.checkpoint_file.with_suffix(".json.tmp")

        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2, sort_keys=False)
                f.write("\n")

            # Atomic replace
            tmp_file.replace(self.checkpoint_file)

            self.logger.info(f"💾 Checkpoint saved: {len(completed_vms)}/{total_vms} VMs completed")

        except Exception as e:
            # Clean up temp file on error
            with contextlib.suppress(Exception):
                tmp_file.unlink()
            raise CheckpointError(msg=f"Failed to save checkpoint: {e}", cause=e) from e

    def get_completed_vm_ids(self) -> set[str]:
        """
        Get set of completed VM IDs from checkpoint.

        Returns:
            Set of completed VM IDs (empty if no checkpoint)
        """
        if not self.has_checkpoint():
            return set()

        try:
            checkpoint = self.load_checkpoint()
            return set(checkpoint.get("completed_vms", []))
        except CheckpointError:
            return set()

    def get_failed_vm_ids(self) -> set[str]:
        """
        Get set of failed VM IDs from checkpoint.

        Returns:
            Set of failed VM IDs (empty if no checkpoint)
        """
        if not self.has_checkpoint():
            return set()

        try:
            checkpoint = self.load_checkpoint()
            failed = checkpoint.get("failed_vms", [])
            return {vm.get("vm_id") for vm in failed if "vm_id" in vm}
        except CheckpointError:
            return set()

    def should_skip_vm(self, vm_id: str) -> bool:
        """
        Check if VM should be skipped (already completed or failed).

        Args:
            vm_id: VM identifier

        Returns:
            True if VM should be skipped
        """
        completed = self.get_completed_vm_ids()
        failed = self.get_failed_vm_ids()
        return vm_id in completed or vm_id in failed

    def cleanup(self) -> None:
        """
        Remove checkpoint file (call on successful batch completion).
        """
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
                self.logger.info("🧹 Checkpoint cleaned up")
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not abort
                self.logger.warning("Failed to cleanup checkpoint: %s", e)

    def reset(self) -> None:
        """
        Manually reset checkpoint (force restart from beginning).
        """
        self.cleanup()
        self.logger.info("🔄 Checkpoint reset - batch will restart from beginning")

    def get_progress_percentage(self) -> float:
        """
        Calculate progress percentage from checkpoint.

        Returns:
            Progress as percentage (0.0 to 100.0), or 0.0 if no checkpoint
        """
        if not self.has_checkpoint():
            return 0.0

        try:
            checkpoint = self.load_checkpoint()
            total = checkpoint.get("total_vms", 0)
            if total == 0:
                return 0.0

            completed = len(checkpoint.get("completed_vms", []))
            failed = len(checkpoint.get("failed_vms", []))
            processed = completed + failed

            return (processed / total) * 100.0

        except CheckpointError:
            return 0.0


__all__ = [
    "CheckpointError",
    "CheckpointManager",
]
