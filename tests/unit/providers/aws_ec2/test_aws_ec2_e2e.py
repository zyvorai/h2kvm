# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""End-to-end AWS EC2 provider test simulating a real migration.

Uses moto to mock EC2/S3 APIs and patches the converter to skip
actual h2kvmctl execution. Tests the full pipeline:
  describe → stop → snapshot → export → download → convert → cleanup
"""

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

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

logger = logging.getLogger(__name__)


def _create_ec2_instance(ec2, *, name: str = "prod-web-01", instance_type: str = "m5.xlarge"):
    """Helper: create a running EC2 instance with a named tag."""
    resp = ec2.run_instances(
        ImageId="ami-12345678",
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": name}],
            }
        ],
    )
    return resp["Instances"][0]["InstanceId"]


def _create_s3_bucket(s3, bucket: str = "hyper2kvm-exports"):
    """Helper: create an S3 bucket."""
    s3.create_bucket(Bucket=bucket)


def _upload_fake_disk(s3, bucket: str, key: str, size_bytes: int = 1024 * 1024):
    """Helper: upload a fake disk image to S3."""
    s3.put_object(Bucket=bucket, Key=key, Body=b"\x00" * size_bytes)


class TestE2EFullPipeline:
    """Simulate a complete EC2 → KVM migration."""

    @mock_aws
    def test_full_migration_pipeline(self, tmp_path):
        """
        Simulate: running EC2 instance → stop → snapshot → export → download → convert.

        The export and convert steps are mocked since moto doesn't support
        export_image API. Everything else is real moto EC2/S3.
        """
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider
        from hyper2kvm.providers.aws_ec2.models import AWSShutdownConfig

        ec2 = boto3.client("ec2", region_name="us-east-1")
        s3 = boto3.client("s3", region_name="us-east-1")

        # Setup: create instance + S3 bucket
        instance_id = _create_ec2_instance(ec2, name="prod-web-01")
        _create_s3_bucket(s3, "hyper2kvm-exports")

        # Verify instance is running
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        assert resp["Reservations"][0]["Instances"][0]["State"]["Name"] == "running"

        output_dir = tmp_path / "output"
        workdir = tmp_path / "work"

        config = AWSConfig(
            region="us-east-1",
            bucket="hyper2kvm-exports",
            instance_ids=[instance_id],
            shutdown=AWSShutdownConfig(stop_instance=True),
            output_dir=output_dir,
            workdir=workdir,
        )

        # Patch exporter and converter since moto doesn't support export_image
        with patch.object(AWSProvider, "_process_volume", wraps=None) as mock_process:
            # Instead of patching _process_volume, let's test the components
            # individually and then test the orchestrator with full mocks
            pass

        # Test the real components individually:

        # 1. Client: describe + stop
        from hyper2kvm.providers.aws_ec2.client import AWSClient

        client = AWSClient(region="us-east-1")
        info = client.describe_instance(instance_id)
        assert info.name == "prod-web-01"
        assert info.state == "running"
        assert info.instance_type == "m5.xlarge"
        assert len(info.volumes) >= 1

        root_vol = client.get_root_volume(instance_id)
        assert root_vol.is_root is True
        assert root_vol.volume_id.startswith("vol-")

        # Stop the instance
        client.stop_instance(instance_id)
        info_after = client.describe_instance(instance_id)
        assert info_after.state == "stopped"

        # 2. Snapshot
        snap_id = client.create_snapshot(root_vol.volume_id)
        assert snap_id.startswith("snap-")

        # Verify snapshot exists
        snap_resp = ec2.describe_snapshots(SnapshotIds=[snap_id])
        assert snap_resp["Snapshots"][0]["State"] == "completed"

        # 3. S3 download (simulate export result)
        fake_disk_key = f"hyper2kvm/{snap_id}/disk.vmdk"
        fake_disk_size = 2 * 1024 * 1024  # 2MB
        _upload_fake_disk(s3, "hyper2kvm-exports", fake_disk_key, fake_disk_size)

        from hyper2kvm.providers.aws_ec2.downloader import Downloader

        downloader = Downloader(s3)
        progress_log = []
        local_path = workdir / "disk.vmdk"
        workdir.mkdir(parents=True, exist_ok=True)

        result = downloader.download(
            "hyper2kvm-exports",
            fake_disk_key,
            local_path,
            progress_cb=lambda dl, total: progress_log.append((dl, total)),
        )

        assert result == local_path
        assert local_path.exists()
        assert local_path.stat().st_size == fake_disk_size
        assert len(progress_log) > 0
        assert progress_log[-1][0] == progress_log[-1][1]  # final: dl == total

        # 4. Converter (mock h2kvmctl)
        from hyper2kvm.providers.aws_ec2.converter import Converter

        converter = Converter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            rc = converter.run_h2kvmctl(
                local_path,
                output_dir,
                vm_name="prod-web-01",
                compress=True,
                regen_initramfs=True,
                emit_domain_xml=True,
            )
        assert rc == 0

        cmd = mock_run.call_args[0][0]
        assert "h2kvmctl" in cmd
        assert str(local_path) in cmd
        assert "prod-web-01" in cmd

        # 5. Cleanup
        client.delete_snapshot(snap_id)
        downloader.delete_s3_object("hyper2kvm-exports", fake_disk_key)

        # Verify cleanup
        with pytest.raises(Exception):
            s3.head_object(Bucket="hyper2kvm-exports", Key=fake_disk_key)

    @mock_aws
    def test_full_provider_orchestrator(self, tmp_path):
        """
        Test the full AWSProvider.pull_instance() with mocked export/download.

        This tests the orchestrator logic: state management, phase ordering,
        cleanup, report generation.
        """
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider
        from hyper2kvm.providers.aws_ec2.models import ExportTask

        ec2_client = boto3.client("ec2", region_name="us-east-1")
        s3_client = boto3.client("s3", region_name="us-east-1")

        instance_id = _create_ec2_instance(ec2_client, name="db-server-01")
        _create_s3_bucket(s3_client, "export-bucket")

        output_dir = tmp_path / "output"
        workdir = tmp_path / "work"

        config = AWSConfig(
            region="us-east-1",
            bucket="export-bucket",
            instance_ids=[instance_id],
            output_dir=output_dir,
            workdir=workdir,
        )

        provider = AWSProvider(config)
        progress_events = []
        provider.progress_cb = lambda phase, msg, pct: progress_events.append((phase, msg, pct))

        # Mock the volume processing since export_image isn't in moto
        fake_disk = workdir / f"{instance_id}-vol-fake.vmdk"
        workdir.mkdir(parents=True, exist_ok=True)
        fake_disk.write_bytes(b"\x00" * 1024)

        def mock_process_volume(volume_id, inst_id, disk, state, state_path, **kwargs):
            disk.snapshot_id = "snap-mock123"
            disk.s3_bucket = "export-bucket"
            disk.s3_key = "hyper2kvm/snap-mock123/disk.vmdk"
            disk.local_path = str(fake_disk)
            disk.ok = True

        with patch.object(provider, "_process_volume", side_effect=mock_process_volume):
            with patch.object(provider.converter, "run_h2kvmctl", return_value=0):
                report = provider.pull_instance(instance_id)

        # Verify report
        assert report.instance_id == instance_id
        assert report.instance_name == "db-server-01"
        assert report.platform == "linux"
        assert report.region == "us-east-1"
        assert len(report.disks) == 1
        assert report.disks[0].ok is True
        assert report.disks[0].snapshot_id == "snap-mock123"
        assert report.errors == []

        # Verify report file written
        report_file = output_dir / f"{instance_id}-report.json"
        assert report_file.exists()
        report_data = json.loads(report_file.read_text())
        assert report_data["instance_id"] == instance_id
        assert report_data["instance_name"] == "db-server-01"

        # Verify progress events emitted
        phases = [e[0] for e in progress_events]
        assert "describe" in phases
        assert "stop" in phases
        assert "convert" in phases
        assert "done" in phases

        # Verify instance was stopped
        resp = ec2_client.describe_instances(InstanceIds=[instance_id])
        assert resp["Reservations"][0]["Instances"][0]["State"]["Name"] == "stopped"

        # Verify state file cleaned up on success
        state_file = workdir / f"{instance_id}.state.json"
        assert not state_file.exists()

    @mock_aws
    def test_provider_skip_stop_if_configured(self, tmp_path):
        """Test that stop_instance=False skips the stop phase."""
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider
        from hyper2kvm.providers.aws_ec2.models import AWSShutdownConfig

        ec2_client = boto3.client("ec2", region_name="us-east-1")
        s3_client = boto3.client("s3", region_name="us-east-1")

        instance_id = _create_ec2_instance(ec2_client, name="no-stop-vm")
        _create_s3_bucket(s3_client, "bucket")

        config = AWSConfig(
            region="us-east-1",
            bucket="bucket",
            shutdown=AWSShutdownConfig(stop_instance=False),
            output_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )

        provider = AWSProvider(config)

        fake_disk = tmp_path / "work" / "disk.vmdk"
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        fake_disk.write_bytes(b"\x00" * 512)

        def mock_process(volume_id, inst_id, disk, state, state_path, **kwargs):
            disk.local_path = str(fake_disk)
            disk.ok = True

        with patch.object(provider, "_process_volume", side_effect=mock_process):
            with patch.object(provider.converter, "run_h2kvmctl", return_value=0):
                report = provider.pull_instance(instance_id)

        # Instance should still be running
        resp = ec2_client.describe_instances(InstanceIds=[instance_id])
        assert resp["Reservations"][0]["Instances"][0]["State"]["Name"] == "running"
        assert report.errors == []

    @mock_aws
    def test_provider_handles_process_volume_failure(self, tmp_path):
        """Test that a failed volume doesn't crash the pipeline."""
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider

        ec2_client = boto3.client("ec2", region_name="us-east-1")
        s3_client = boto3.client("s3", region_name="us-east-1")

        instance_id = _create_ec2_instance(ec2_client, name="fail-vm")
        _create_s3_bucket(s3_client, "bucket")

        config = AWSConfig(
            region="us-east-1",
            bucket="bucket",
            output_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )

        provider = AWSProvider(config)

        with patch.object(
            provider,
            "_process_volume",
            side_effect=RuntimeError("Snapshot creation timed out"),
        ):
            with patch.object(provider.converter, "run_h2kvmctl", return_value=0):
                report = provider.pull_instance(instance_id)

        # Pipeline should complete with errors on the disk
        assert len(report.disks) == 1
        assert report.disks[0].ok is False
        assert "Snapshot creation timed out" in report.disks[0].errors[0]
        # No top-level error — individual disk failure is contained
        assert report.errors == []

    @mock_aws
    def test_provider_pull_all(self, tmp_path):
        """Test pull_all() processes multiple instances."""
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider

        ec2_client = boto3.client("ec2", region_name="us-east-1")
        s3_client = boto3.client("s3", region_name="us-east-1")

        id1 = _create_ec2_instance(ec2_client, name="vm-1")
        id2 = _create_ec2_instance(ec2_client, name="vm-2")
        _create_s3_bucket(s3_client, "bucket")

        config = AWSConfig(
            region="us-east-1",
            bucket="bucket",
            instance_ids=[id1, id2],
            output_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )

        provider = AWSProvider(config)

        fake_disk = tmp_path / "work" / "disk.vmdk"
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        fake_disk.write_bytes(b"\x00" * 512)

        def mock_process(volume_id, inst_id, disk, state, state_path, **kwargs):
            disk.local_path = str(fake_disk)
            disk.ok = True

        with patch.object(provider, "_process_volume", side_effect=mock_process):
            with patch.object(provider.converter, "run_h2kvmctl", return_value=0):
                reports = provider.pull_all()

        assert len(reports) == 2
        assert reports[0].instance_id == id1
        assert reports[1].instance_id == id2
        assert reports[0].instance_name == "vm-1"
        assert reports[1].instance_name == "vm-2"

    @mock_aws
    def test_state_file_resumability(self, tmp_path):
        """Test that state file enables resuming after interruption."""
        from hyper2kvm.providers.aws_ec2.utils import load_state, save_state

        state_path = tmp_path / "i-abc123.state.json"

        # Simulate phase 1: snapshot created, then interrupted
        state = {
            "vol-123": {
                "snapshot_id": "snap-resume456",
            }
        }
        save_state(state_path, state)

        # Simulate phase 2: resume picks up existing snapshot
        loaded = load_state(state_path)
        assert loaded is not None
        assert loaded["vol-123"]["snapshot_id"] == "snap-resume456"

        # Simulate phase 3: export completed
        loaded["vol-123"]["export_task_id"] = "export-789"
        loaded["vol-123"]["s3_bucket"] = "bucket"
        loaded["vol-123"]["s3_key"] = "hyper2kvm/snap-resume456/disk.vmdk"
        save_state(state_path, loaded)

        # Simulate phase 4: download completed
        loaded = load_state(state_path)
        loaded["vol-123"]["downloaded"] = True
        loaded["vol-123"]["local_path"] = "/tmp/disk.vmdk"
        save_state(state_path, loaded)

        # Final state has all phases
        final = load_state(state_path)
        assert final["vol-123"]["snapshot_id"] == "snap-resume456"
        assert final["vol-123"]["downloaded"] is True
        assert final["vol-123"]["local_path"] == "/tmp/disk.vmdk"

    @mock_aws
    def test_multi_disk_instance(self, tmp_path):
        """Test instance with multiple EBS volumes (root + data)."""
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider
        from hyper2kvm.providers.aws_ec2.models import AWSExportConfig

        ec2_client = boto3.client("ec2", region_name="us-east-1")
        s3_client = boto3.client("s3", region_name="us-east-1")

        # Create instance (gets root volume automatically)
        instance_id = _create_ec2_instance(ec2_client, name="multi-disk")

        # Attach a second data volume
        vol = ec2_client.create_volume(AvailabilityZone="us-east-1a", Size=100)
        ec2_client.attach_volume(
            VolumeId=vol["VolumeId"],
            InstanceId=instance_id,
            Device="/dev/sdf",
        )

        _create_s3_bucket(s3_client, "bucket")

        config = AWSConfig(
            region="us-east-1",
            bucket="bucket",
            export=AWSExportConfig(disks="all"),  # Export all disks
            output_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )

        provider = AWSProvider(config)

        # Verify provider sees both volumes
        info = provider.client.describe_instance(instance_id)
        assert len(info.volumes) == 2

        disk_count = 0

        def mock_process(volume_id, inst_id, disk, state, state_path, **kwargs):
            nonlocal disk_count
            disk_count += 1
            fake = tmp_path / "work" / f"disk-{disk_count}.vmdk"
            (tmp_path / "work").mkdir(parents=True, exist_ok=True)
            fake.write_bytes(b"\x00" * 256)
            disk.local_path = str(fake)
            disk.ok = True

        with patch.object(provider, "_process_volume", side_effect=mock_process):
            with patch.object(provider.converter, "run_h2kvmctl", return_value=0):
                report = provider.pull_instance(instance_id)

        assert len(report.disks) == 2
        assert disk_count == 2
        assert all(d.ok for d in report.disks)

    @mock_aws
    def test_root_only_export(self, tmp_path):
        """Test that disks='root' only exports the root volume."""
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider
        from hyper2kvm.providers.aws_ec2.models import AWSExportConfig

        ec2_client = boto3.client("ec2", region_name="us-east-1")
        s3_client = boto3.client("s3", region_name="us-east-1")

        instance_id = _create_ec2_instance(ec2_client)
        vol = ec2_client.create_volume(AvailabilityZone="us-east-1a", Size=50)
        ec2_client.attach_volume(VolumeId=vol["VolumeId"], InstanceId=instance_id, Device="/dev/sdg")
        _create_s3_bucket(s3_client, "bucket")

        config = AWSConfig(
            region="us-east-1",
            bucket="bucket",
            export=AWSExportConfig(disks="root"),  # Root only
            output_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )

        provider = AWSProvider(config)
        processed_volumes = []

        def mock_process(volume_id, inst_id, disk, state, state_path, **kwargs):
            processed_volumes.append(volume_id)
            fake = tmp_path / "work" / "disk.vmdk"
            (tmp_path / "work").mkdir(parents=True, exist_ok=True)
            fake.write_bytes(b"\x00" * 256)
            disk.local_path = str(fake)
            disk.ok = True

        with patch.object(provider, "_process_volume", side_effect=mock_process):
            with patch.object(provider.converter, "run_h2kvmctl", return_value=0):
                report = provider.pull_instance(instance_id)

        # Only root volume should be processed
        assert len(report.disks) == 1
        assert len(processed_volumes) == 1
        assert report.disks[0].is_root is True
