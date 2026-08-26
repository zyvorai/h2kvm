# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""AWS EC2 API client with retry logic."""

from __future__ import annotations

import logging
from typing import Any

from .exceptions import (
    AWSAuthError,
    InstanceNotFound,
    VolumeNotFound,
)
from .models import InstanceInfo, VolumeInfo
from .utils import instance_name_from_tags, retry

try:
    import boto3
    import botocore.exceptions

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


class AWSClient:
    """
    AWS EC2 API client.

    Wraps boto3 EC2 client with retry logic, structured logging,
    and clean error handling.
    """

    def __init__(
        self,
        region: str = "us-east-1",
        profile: str | None = None,
        log: logging.Logger | None = None,
    ):
        if not BOTO3_AVAILABLE:
            raise AWSAuthError("boto3 is required for AWS EC2 provider. Install with: pip install boto3")

        self.log = log or logger
        self.region = region

        session_kwargs: dict[str, Any] = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile

        try:
            session = boto3.Session(**session_kwargs)
            self.ec2 = session.client("ec2")
            self.s3 = session.client("s3")
            # Verify credentials early
            self.ec2.describe_regions(RegionNames=[region])
        except botocore.exceptions.NoCredentialsError as cred_err:
            raise AWSAuthError(
                "No AWS credentials found. Configure with:\n"
                "  aws configure\n"
                "  or set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY"
            ) from cred_err
        except botocore.exceptions.ClientError as e:
            raise AWSAuthError(f"AWS authentication failed: {e}") from e

        self.log.info("AWS client initialized: region=%s", region)

    def _retry(self, fn, *, label: str = "AWS API call", retries: int = 5):
        def _is_retryable(e: Exception) -> bool:
            if isinstance(e, botocore.exceptions.ClientError):
                code = e.response.get("Error", {}).get("Code", "")
                return code in (
                    "RequestLimitExceeded",
                    "Throttling",
                    "InternalError",
                    "ServiceUnavailable",
                )
            return isinstance(e, botocore.exceptions.ConnectionError)

        return retry(fn, retries=retries, retryable=_is_retryable, label=label, log=self.log)

    def describe_instance(self, instance_id: str) -> InstanceInfo:
        """Get instance metadata including attached volumes."""
        self.log.info("Describing instance %s", instance_id)

        try:
            resp = self._retry(
                lambda: self.ec2.describe_instances(InstanceIds=[instance_id]),
                label=f"describe_instances({instance_id})",
            )
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                raise InstanceNotFound(f"Instance {instance_id} not found") from e
            raise

        reservations = resp.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            raise InstanceNotFound(f"Instance {instance_id} not found")

        inst = reservations[0]["Instances"][0]
        root_dev = inst.get("RootDeviceName", "")

        volumes = []
        for bdm in inst.get("BlockDeviceMappings", []):
            ebs = bdm.get("Ebs")
            if not ebs:
                continue
            vol_id = ebs["VolumeId"]

            # Get volume details for size
            vol_resp = self._retry(
                lambda vid=vol_id: self.ec2.describe_volumes(VolumeIds=[vid]),
                label=f"describe_volumes({vol_id})",
            )
            vol_data = vol_resp["Volumes"][0]

            volumes.append(
                VolumeInfo(
                    volume_id=vol_id,
                    device=bdm["DeviceName"],
                    size_gb=vol_data["Size"],
                    volume_type=vol_data.get("VolumeType", ""),
                    is_root=(bdm["DeviceName"] == root_dev),
                    encrypted=vol_data.get("Encrypted", False),
                )
            )

        platform = inst.get("Platform", "")
        platform = "windows" if platform.lower() == "windows" else "linux"

        return InstanceInfo(
            instance_id=instance_id,
            name=instance_name_from_tags(inst.get("Tags")),
            state=inst["State"]["Name"],
            instance_type=inst.get("InstanceType", ""),
            platform=platform,
            architecture=inst.get("Architecture", "x86_64"),
            root_device_name=root_dev,
            root_device_type=inst.get("RootDeviceType", "ebs"),
            volumes=volumes,
            tags={t["Key"]: t["Value"] for t in (inst.get("Tags") or [])},
        )

    def stop_instance(self, instance_id: str) -> None:
        """Stop an instance and wait for it to reach 'stopped' state."""
        info = self.describe_instance(instance_id)
        if info.state == "stopped":
            self.log.info("Instance %s already stopped", instance_id)
            return

        self.log.info("Stopping instance %s (current state: %s)", instance_id, info.state)
        self._retry(
            lambda: self.ec2.stop_instances(InstanceIds=[instance_id]),
            label=f"stop_instances({instance_id})",
        )

        waiter = self.ec2.get_waiter("instance_stopped")
        self.log.info("Waiting for instance %s to stop...", instance_id)
        waiter.wait(InstanceIds=[instance_id], WaiterConfig={"Delay": 10, "MaxAttempts": 60})
        self.log.info("Instance %s stopped", instance_id)

    def get_root_volume(self, instance_id: str) -> VolumeInfo:
        """Get the root EBS volume for an instance."""
        info = self.describe_instance(instance_id)
        for vol in info.volumes:
            if vol.is_root:
                return vol
        raise VolumeNotFound(f"Root volume not found on {instance_id}")

    def create_snapshot(self, volume_id: str, description: str = "h2kvm export") -> str:
        """Create an EBS snapshot and wait for completion."""
        self.log.info("Creating snapshot for volume %s", volume_id)

        resp = self._retry(
            lambda: self.ec2.create_snapshot(
                VolumeId=volume_id,
                Description=description,
                TagSpecifications=[
                    {
                        "ResourceType": "snapshot",
                        "Tags": [
                            {"Key": "Name", "Value": f"h2kvm-{volume_id}"},
                            {"Key": "h2kvm", "Value": "true"},
                        ],
                    }
                ],
            ),
            label=f"create_snapshot({volume_id})",
        )
        snapshot_id = resp["SnapshotId"]
        self.log.info("Snapshot created: %s", snapshot_id)

        self.log.info("Waiting for snapshot %s to complete...", snapshot_id)
        waiter = self.ec2.get_waiter("snapshot_completed")
        waiter.wait(
            SnapshotIds=[snapshot_id],
            WaiterConfig={"Delay": 15, "MaxAttempts": 120},
        )
        self.log.info("Snapshot %s completed", snapshot_id)
        return snapshot_id

    def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete an EBS snapshot."""
        self.log.info("Deleting snapshot %s", snapshot_id)
        try:
            self._retry(
                lambda: self.ec2.delete_snapshot(SnapshotId=snapshot_id),
                label=f"delete_snapshot({snapshot_id})",
            )
        # best-effort cleanup; retry() itself catches any exception type,
        # must not abort the run over a failed snapshot delete
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.log.warning("Failed to delete snapshot %s: %s", snapshot_id, e)
