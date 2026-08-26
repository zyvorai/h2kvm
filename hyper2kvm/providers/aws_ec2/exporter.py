# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""EC2 image export to S3."""

from __future__ import annotations

import logging
import time
from typing import Callable

from .exceptions import ExportFailed
from .models import ExportTask

logger = logging.getLogger(__name__)


class Exporter:
    """
    Export EBS snapshots to S3 as disk images.

    Uses the EC2 ExportImage API (snapshot → S3 VMDK/VHD/RAW).
    Polls until completion with progress callbacks.
    """

    def __init__(self, ec2_client, log: logging.Logger | None = None):
        self.ec2 = ec2_client
        self.log = log or logger
        self._temp_ami_ids: list[str] = []

    def start_export(
        self,
        snapshot_id: str,
        bucket: str,
        *,
        prefix: str = "hyper2kvm",
        disk_format: str = "vmdk",
        role_name: str = "vmimport",
    ) -> str:
        """
        Start an export-image task from an EBS snapshot.

        EC2 ExportImage requires an AMI, not a snapshot directly.
        This method registers a temporary AMI from the snapshot,
        exports the AMI, and tracks the temp AMI for cleanup.

        Args:
            snapshot_id: EBS snapshot to export
            bucket: S3 bucket for output
            prefix: S3 key prefix
            disk_format: Output format (vmdk, vhd, raw)
            role_name: IAM role for vmimport

        Returns:
            Export task ID
        """
        self.log.info(
            "Starting export: snapshot=%s bucket=%s format=%s",
            snapshot_id,
            bucket,
            disk_format,
        )

        # Register a temporary AMI from the snapshot
        ami_name = f"hyper2kvm-temp-{snapshot_id}"
        self.log.info("Registering temp AMI from snapshot %s", snapshot_id)
        ami_resp = self.ec2.register_image(
            Name=ami_name,
            RootDeviceName="/dev/sda1",
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {"SnapshotId": snapshot_id},
                }
            ],
            VirtualizationType="hvm",
            Architecture="x86_64",
        )
        ami_id = ami_resp["ImageId"]
        self._temp_ami_ids.append(ami_id)
        self.log.info("Registered temp AMI: %s", ami_id)

        # Wait for AMI to be available
        waiter = self.ec2.get_waiter("image_available")
        waiter.wait(ImageIds=[ami_id])

        # Export the AMI to S3
        resp = self.ec2.export_image(
            ImageId=ami_id,
            DiskImageFormat=disk_format.upper(),
            S3ExportLocation={
                "S3Bucket": bucket,
                "S3Prefix": f"{prefix}/{snapshot_id}/",
            },
            RoleName=role_name,
        )
        task_id = resp["ExportImageTaskId"]

        self.log.info("Export task started: %s", task_id)
        return task_id

    def wait(
        self,
        task_id: str,
        *,
        poll_interval: int = 15,
        timeout: int = 7200,
        progress_cb: Callable[[str, str], None] | None = None,
    ) -> ExportTask:
        """
        Poll export task until completion.

        Args:
            task_id: Export image task ID
            poll_interval: Seconds between polls
            timeout: Maximum wait time in seconds
            progress_cb: Callback(status, progress_pct)

        Returns:
            Completed ExportTask

        Raises:
            ExportFailed: If task fails or is cancelled
        """
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise ExportFailed(task_id, "timeout", f"Exceeded {timeout}s")

            resp = self.ec2.describe_export_image_tasks(
                ExportImageTaskIds=[task_id],
            )
            tasks = resp.get("ExportImageTasks", [])
            if not tasks:
                raise ExportFailed(task_id, "not_found", "Task disappeared")

            task = tasks[0]
            status = task.get("Status", "unknown")
            progress = task.get("Progress", "")
            status_msg = task.get("StatusMessage", "")

            self.log.info(
                "Export %s: status=%s progress=%s elapsed=%.0fs",
                task_id,
                status,
                progress or "—",
                elapsed,
            )

            if progress_cb:
                progress_cb(status, progress)

            if status == "completed":
                s3_loc = task.get("S3ExportLocation", {})
                return ExportTask(
                    task_id=task_id,
                    status="completed",
                    s3_bucket=s3_loc.get("S3Bucket", ""),
                    s3_key=s3_loc.get("S3Key", ""),
                )

            if status in ("deleted", "deleting", "cancelled"):
                raise ExportFailed(task_id, status, status_msg)

            time.sleep(poll_interval)

    def cleanup_temp_amis(self) -> None:
        """Deregister all temporary AMIs created during exports."""
        for ami_id in list(self._temp_ami_ids):
            self.log.info("Deregistering temp AMI: %s", ami_id)
            try:
                self.ec2.deregister_image(ImageId=ami_id)
            # best-effort cleanup of a temp AMI must not abort cleanup of the rest
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.log.warning("Failed to deregister temp AMI %s: %s", ami_id, e)
        self._temp_ami_ids.clear()
