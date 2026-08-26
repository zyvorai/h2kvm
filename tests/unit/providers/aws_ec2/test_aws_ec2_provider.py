# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for AWS EC2 provider using moto mock."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from hyper2kvm.providers.aws_ec2.client import AWSClient
from hyper2kvm.providers.aws_ec2.downloader import Downloader
from hyper2kvm.providers.aws_ec2.exceptions import (
    AWSProviderError,
    DownloadFailed,
    InstanceNotFound,
    VolumeNotFound,
)
from hyper2kvm.providers.aws_ec2.models import (
    AWSConfig,
    AWSDownloadConfig,
    AWSExportConfig,
    AWSShutdownConfig,
    DiskExport,
    ExportReport,
    ExportTask,
    InstanceInfo,
    VolumeInfo,
)
from hyper2kvm.providers.aws_ec2.utils import (
    instance_name_from_tags,
    load_state,
    retry,
    save_state,
)

logger = logging.getLogger(__name__)

# Set dummy AWS credentials for moto
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


# ============================================================================
# Models
# ============================================================================


class TestModels:
    def test_volume_info(self):
        vol = VolumeInfo(
            volume_id="vol-abc123",
            device="/dev/sda1",
            size_gb=100,
            is_root=True,
            encrypted=False,
        )
        assert vol.volume_id == "vol-abc123"
        assert vol.is_root is True
        assert vol.size_gb == 100

    def test_instance_info(self):
        vol = VolumeInfo(volume_id="vol-1", device="/dev/sda1", size_gb=50, is_root=True)
        info = InstanceInfo(
            instance_id="i-abc123",
            name="test-vm",
            state="running",
            instance_type="m5.xlarge",
            platform="linux",
            architecture="x86_64",
            root_device_name="/dev/sda1",
            root_device_type="ebs",
            volumes=[vol],
            tags={"Name": "test-vm", "env": "prod"},
        )
        assert info.instance_id == "i-abc123"
        assert info.platform == "linux"
        assert len(info.volumes) == 1
        assert info.volumes[0].is_root is True

    def test_export_task(self):
        task = ExportTask(
            task_id="export-123",
            status="completed",
            s3_bucket="my-bucket",
            s3_key="hyper2kvm/snap-123/disk.vmdk",
        )
        assert task.status == "completed"
        assert task.s3_key.endswith(".vmdk")

    def test_disk_export(self):
        disk = DiskExport(
            volume_id="vol-abc",
            device="/dev/sda1",
            is_root=True,
            size_gb=100,
        )
        assert disk.ok is False
        assert disk.errors == []
        disk.ok = True
        disk.snapshot_id = "snap-123"
        assert disk.snapshot_id == "snap-123"

    def test_export_report_jsonable(self):
        report = ExportReport(
            instance_id="i-abc123",
            instance_name="test-vm",
            region="us-east-1",
            platform="linux",
        )
        report.disks.append(
            DiskExport(
                volume_id="vol-1",
                device="/dev/sda1",
                is_root=True,
                size_gb=50,
            )
        )
        data = report.to_jsonable()
        assert data["instance_id"] == "i-abc123"
        assert len(data["disks"]) == 1
        assert data["disks"][0]["volume_id"] == "vol-1"

    def test_aws_config_defaults(self):
        cfg = AWSConfig(bucket="test-bucket")
        assert cfg.region == "us-east-1"
        assert cfg.profile is None
        assert cfg.export.disk_format == "vmdk"
        assert cfg.download.retries == 5
        assert cfg.shutdown.stop_instance is True

    def test_aws_config_custom(self):
        cfg = AWSConfig(
            region="eu-west-1",
            bucket="my-exports",
            instance_ids=["i-111", "i-222"],
            export=AWSExportConfig(disk_format="raw", disks="all"),
            download=AWSDownloadConfig(retries=3, parallel=4),
            shutdown=AWSShutdownConfig(stop_instance=False),
        )
        assert cfg.region == "eu-west-1"
        assert cfg.export.disk_format == "raw"
        assert cfg.download.retries == 3
        assert cfg.shutdown.stop_instance is False
        assert len(cfg.instance_ids) == 2


# ============================================================================
# Utils
# ============================================================================


class TestUtils:
    def test_retry_success(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert retry(fn, retries=3) == "ok"
        assert len(calls) == 1

    def test_retry_eventual_success(self):
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("not yet")
            return "done"

        result = retry(fn, retries=5, backoff_base=0.01, backoff_cap=0.02)
        assert result == "done"
        assert len(attempts) == 3

    def test_retry_exhausted(self):
        def fn():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            retry(fn, retries=3, backoff_base=0.01)

    def test_retry_non_retryable(self):
        calls = []

        def fn():
            calls.append(1)
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            retry(fn, retries=5, retryable=lambda e: isinstance(e, ValueError), backoff_base=0.01)
        assert len(calls) == 1  # Only one attempt

    def test_save_load_state(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = {"snapshot_id": "snap-123", "downloaded": True}
        save_state(state_file, state)

        loaded = load_state(state_file)
        assert loaded == state

    def test_load_state_missing(self, tmp_path):
        assert load_state(tmp_path / "nonexistent.json") is None

    def test_load_state_corrupt(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json{{{")
        assert load_state(bad_file) is None

    def test_instance_name_from_tags(self):
        assert (
            instance_name_from_tags(
                [
                    {"Key": "env", "Value": "prod"},
                    {"Key": "Name", "Value": "my-server"},
                ]
            )
            == "my-server"
        )

    def test_instance_name_from_tags_missing(self):
        assert instance_name_from_tags([{"Key": "env", "Value": "prod"}]) == ""

    def test_instance_name_from_tags_none(self):
        assert instance_name_from_tags(None) == ""


# ============================================================================
# Client (with moto)
# ============================================================================


class TestAWSClient:
    @mock_aws
    def test_describe_instance(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")

        # Create a VPC and subnet first
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        subnet = ec2.create_subnet(
            VpcId=vpc["Vpc"]["VpcId"],
            CidrBlock="10.0.1.0/24",
        )

        # Launch instance
        resp = ec2.run_instances(
            ImageId="ami-12345678",
            InstanceType="m5.xlarge",
            MinCount=1,
            MaxCount=1,
            SubnetId=subnet["Subnet"]["SubnetId"],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": "Name", "Value": "test-vm"}],
                }
            ],
        )
        instance_id = resp["Instances"][0]["InstanceId"]

        client = AWSClient(region="us-east-1")
        info = client.describe_instance(instance_id)

        assert info.instance_id == instance_id
        assert info.name == "test-vm"
        assert info.instance_type == "m5.xlarge"
        assert info.state == "running"
        assert len(info.volumes) >= 1

    @mock_aws
    def test_describe_instance_not_found(self):
        client = AWSClient(region="us-east-1")
        with pytest.raises(InstanceNotFound):
            client.describe_instance("i-nonexistent12345678")

    @mock_aws
    def test_stop_instance(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")
        resp = ec2.run_instances(ImageId="ami-12345678", InstanceType="t2.micro", MinCount=1, MaxCount=1)
        instance_id = resp["Instances"][0]["InstanceId"]

        client = AWSClient(region="us-east-1")
        client.stop_instance(instance_id)

        info = client.describe_instance(instance_id)
        assert info.state == "stopped"

    @mock_aws
    def test_stop_already_stopped(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")
        resp = ec2.run_instances(ImageId="ami-12345678", InstanceType="t2.micro", MinCount=1, MaxCount=1)
        instance_id = resp["Instances"][0]["InstanceId"]
        ec2.stop_instances(InstanceIds=[instance_id])
        ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

        client = AWSClient(region="us-east-1")
        # Should not raise
        client.stop_instance(instance_id)

    @mock_aws
    def test_get_root_volume(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")
        resp = ec2.run_instances(ImageId="ami-12345678", InstanceType="t2.micro", MinCount=1, MaxCount=1)
        instance_id = resp["Instances"][0]["InstanceId"]

        client = AWSClient(region="us-east-1")
        vol = client.get_root_volume(instance_id)
        assert vol.is_root is True
        assert vol.volume_id.startswith("vol-")

    @mock_aws
    def test_create_snapshot(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")

        # Create a volume
        vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)
        volume_id = vol["VolumeId"]

        client = AWSClient(region="us-east-1")
        snap_id = client.create_snapshot(volume_id)
        assert snap_id.startswith("snap-")

    @mock_aws
    def test_delete_snapshot(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")
        vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)
        snap = ec2.create_snapshot(VolumeId=vol["VolumeId"])

        client = AWSClient(region="us-east-1")
        # Should not raise
        client.delete_snapshot(snap["SnapshotId"])

    @mock_aws
    def test_windows_platform_detection(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")
        resp = ec2.run_instances(
            ImageId="ami-12345678",
            InstanceType="t2.micro",
            MinCount=1,
            MaxCount=1,
        )
        instance_id = resp["Instances"][0]["InstanceId"]

        client = AWSClient(region="us-east-1")
        info = client.describe_instance(instance_id)
        # moto doesn't set Platform for non-Windows, so it defaults to "linux"
        assert info.platform == "linux"


# ============================================================================
# Downloader
# ============================================================================


class TestDownloader:
    @mock_aws
    def test_download_file(self, tmp_path):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(Bucket="test-bucket", Key="disk.vmdk", Body=b"x" * 1024)

        downloader = Downloader(s3)
        dest = tmp_path / "disk.vmdk"
        result = downloader.download("test-bucket", "disk.vmdk", dest)

        assert result == dest
        assert dest.exists()
        assert dest.stat().st_size == 1024

    @mock_aws
    def test_download_with_progress(self, tmp_path):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(Bucket="test-bucket", Key="disk.vmdk", Body=b"y" * 2048)

        progress_calls = []
        downloader = Downloader(s3)
        downloader.download(
            "test-bucket",
            "disk.vmdk",
            tmp_path / "disk.vmdk",
            progress_cb=lambda dl, total: progress_calls.append((dl, total)),
        )

        assert len(progress_calls) > 0
        # Last call should have dl == total
        assert progress_calls[-1][0] == progress_calls[-1][1]

    @mock_aws
    def test_download_empty_object(self, tmp_path):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(Bucket="test-bucket", Key="empty.raw", Body=b"")

        downloader = Downloader(s3)
        dest = tmp_path / "empty.raw"
        result = downloader.download("test-bucket", "empty.raw", dest)
        assert result == dest
        assert dest.stat().st_size == 0

    @mock_aws
    def test_download_resume_complete(self, tmp_path):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        data = b"a" * 512
        s3.put_object(Bucket="test-bucket", Key="disk.raw", Body=data)

        # Create part file that's already complete
        dest = tmp_path / "disk.raw"
        part = dest.with_suffix(".raw.part")
        part.write_bytes(data)

        downloader = Downloader(s3)
        result = downloader.download("test-bucket", "disk.raw", dest, resume=True)
        assert result == dest
        assert dest.exists()
        assert dest.stat().st_size == 512

    @mock_aws
    def test_download_nonexistent_key(self, tmp_path):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        downloader = Downloader(s3, retries=1)
        with pytest.raises(DownloadFailed):
            downloader.download("test-bucket", "no-such-key", tmp_path / "out.vmdk")

    @mock_aws
    def test_delete_s3_object(self):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(Bucket="test-bucket", Key="to-delete.vmdk", Body=b"data")

        downloader = Downloader(s3)
        downloader.delete_s3_object("test-bucket", "to-delete.vmdk")

        # Verify deleted
        with pytest.raises(Exception):
            s3.head_object(Bucket="test-bucket", Key="to-delete.vmdk")


# ============================================================================
# Converter
# ============================================================================


class TestConverter:
    def test_run_h2kvmctl_builds_correct_command(self):
        from hyper2kvm.providers.aws_ec2.converter import Converter

        converter = Converter()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rc = converter.run_h2kvmctl(
                "/tmp/disk.vmdk",
                "/tmp/out",
                vm_name="test-vm",
                compress=True,
                regen_initramfs=True,
                emit_domain_xml=True,
            )

        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "h2kvmctl" in cmd
        assert "--cmd" in cmd
        assert "--vmdk" in cmd
        assert "/tmp/disk.vmdk" in cmd
        assert "--compress" in cmd
        assert "--regen-initramfs" in cmd
        assert "--emit-domain-xml" in cmd
        assert "--vm-name" in cmd
        assert "test-vm" in cmd

    def test_run_h2kvmctl_no_optional_flags(self):
        from hyper2kvm.providers.aws_ec2.converter import Converter

        converter = Converter()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            converter.run_h2kvmctl(
                "/tmp/disk.raw",
                "/tmp/out",
                vm_name="vm",
                compress=False,
                regen_initramfs=False,
                emit_domain_xml=False,
            )

        cmd = mock_run.call_args[0][0]
        assert "--compress" not in cmd
        assert "--regen-initramfs" not in cmd
        assert "--emit-domain-xml" not in cmd


# ============================================================================
# Exporter
# ============================================================================


class TestExporter:
    def test_wait_timeout(self):
        from hyper2kvm.providers.aws_ec2.exceptions import ExportFailed
        from hyper2kvm.providers.aws_ec2.exporter import Exporter

        mock_ec2 = MagicMock()
        mock_ec2.describe_export_image_tasks.return_value = {
            "ExportImageTasks": [
                {
                    "ExportImageTaskId": "export-123",
                    "Status": "active",
                    "Progress": "50%",
                }
            ]
        }

        exporter = Exporter(mock_ec2)
        with pytest.raises(ExportFailed, match="timeout"):
            exporter.wait("export-123", poll_interval=0.01, timeout=0.05)

    def test_wait_completed(self):
        from hyper2kvm.providers.aws_ec2.exporter import Exporter

        mock_ec2 = MagicMock()
        mock_ec2.describe_export_image_tasks.return_value = {
            "ExportImageTasks": [
                {
                    "ExportImageTaskId": "export-123",
                    "Status": "completed",
                    "S3ExportLocation": {
                        "S3Bucket": "my-bucket",
                        "S3Key": "hyper2kvm/snap-123/disk.vmdk",
                    },
                }
            ]
        }

        exporter = Exporter(mock_ec2)
        task = exporter.wait("export-123", poll_interval=0.01)
        assert task.status == "completed"
        assert task.s3_bucket == "my-bucket"
        assert task.s3_key.endswith(".vmdk")

    def test_wait_failed(self):
        from hyper2kvm.providers.aws_ec2.exceptions import ExportFailed
        from hyper2kvm.providers.aws_ec2.exporter import Exporter

        mock_ec2 = MagicMock()
        mock_ec2.describe_export_image_tasks.return_value = {
            "ExportImageTasks": [
                {
                    "ExportImageTaskId": "export-123",
                    "Status": "deleted",
                    "StatusMessage": "Cancelled by user",
                }
            ]
        }

        exporter = Exporter(mock_ec2)
        with pytest.raises(ExportFailed, match="deleted"):
            exporter.wait("export-123", poll_interval=0.01)

    def test_wait_task_disappeared(self):
        from hyper2kvm.providers.aws_ec2.exceptions import ExportFailed
        from hyper2kvm.providers.aws_ec2.exporter import Exporter

        mock_ec2 = MagicMock()
        mock_ec2.describe_export_image_tasks.return_value = {"ExportImageTasks": []}

        exporter = Exporter(mock_ec2)
        with pytest.raises(ExportFailed, match="not_found"):
            exporter.wait("export-gone", poll_interval=0.01)

    def test_cleanup_temp_amis(self):
        from hyper2kvm.providers.aws_ec2.exporter import Exporter

        mock_ec2 = MagicMock()
        exporter = Exporter(mock_ec2)
        exporter._temp_ami_ids = ["ami-111", "ami-222"]

        exporter.cleanup_temp_amis()
        assert mock_ec2.deregister_image.call_count == 2
        assert exporter._temp_ami_ids == []

    def test_cleanup_temp_amis_error_continues(self):
        from hyper2kvm.providers.aws_ec2.exporter import Exporter

        mock_ec2 = MagicMock()
        mock_ec2.deregister_image.side_effect = [Exception("fail"), None]
        exporter = Exporter(mock_ec2)
        exporter._temp_ami_ids = ["ami-bad", "ami-good"]

        # Should not raise
        exporter.cleanup_temp_amis()
        assert mock_ec2.deregister_image.call_count == 2


# ============================================================================
# Provider (integration-level with mocks)
# ============================================================================


class TestProviderConfig:
    def test_missing_bucket_raises(self):
        with pytest.raises(AWSProviderError, match="bucket"):
            from hyper2kvm.providers.aws_ec2.provider import AWSProvider

            AWSProvider(AWSConfig(bucket=""), log=logger)

    def test_vm_name_sanitization(self):
        import re

        # Simulate the sanitization logic from provider.py
        name = "../../etc/passwd"
        vm_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")[:50] or "fallback"
        assert "/" not in vm_name
        assert ".." not in vm_name
        assert vm_name == "etc-passwd"

    def test_vm_name_sanitization_empty(self):
        import re

        name = "////"
        vm_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")[:50] or "fallback"
        assert vm_name == "fallback"

    def test_vm_name_sanitization_normal(self):
        import re

        name = "My Web Server 01"
        vm_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")[:50] or "fallback"
        assert vm_name == "My-Web-Server-01"
