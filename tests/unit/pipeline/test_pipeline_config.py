# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.config.pipeline_config (DiskProcessingConfig, MigrationConfig)."""

from __future__ import annotations

import types

import pytest

from hyper2kvm.config.pipeline_config import DiskProcessingConfig, MigrationConfig, resolve_enable_rdp


# ---------------------------------------------------------------------------
# DiskProcessingConfig -- defaults
# ---------------------------------------------------------------------------


class TestDiskProcessingConfigDefaults:
    """Verify every default value on a bare DiskProcessingConfig()."""

    def test_workdir_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.workdir is None

    def test_skip_vmdk_inspection_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.skip_vmdk_inspection is False

    def test_flatten_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.flatten is False

    def test_flatten_format_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.flatten_format == "qcow2"

    def test_dry_run_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.dry_run is False

    def test_no_backup_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.no_backup is False

    def test_fstab_mode_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.fstab_mode == "stabilize-all"

    def test_regen_initramfs_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.regen_initramfs is True

    def test_serial_console_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.serial_console is True

    def test_backend_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.backend == "vmcraft"

    def test_out_format_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.out_format == "qcow2"

    def test_compress_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.compress is False

    def test_compress_level_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.compress_level is None

    def test_luks_enable_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.luks_enable is False

    def test_enable_rdp_default(self):
        cfg = DiskProcessingConfig()
        assert cfg.enable_rdp is None


# ---------------------------------------------------------------------------
# DiskProcessingConfig.from_args -- full args
# ---------------------------------------------------------------------------


class TestDiskProcessingConfigFromArgsFull:
    """from_args with every attribute supplied."""

    def test_from_args_full(self, full_disk_args):
        cfg = DiskProcessingConfig.from_args(full_disk_args)
        assert cfg.workdir == "/tmp/work"
        assert cfg.skip_vmdk_inspection is True
        assert cfg.flatten is True
        assert cfg.flatten_format == "raw"
        assert cfg.dry_run is True
        assert cfg.no_backup is True
        assert cfg.regen_initramfs is False
        assert cfg.fstab_mode == "passthrough"
        assert cfg.serial_console is False
        assert cfg.backend == "guestfish"
        assert cfg.out_format == "raw"
        assert cfg.compress is True
        assert cfg.compress_level == 9
        assert cfg.luks_enable is True
        assert cfg.luks_passphrase == "secret"
        assert cfg.luks_passphrase_env == "LUKS_PASS"
        assert cfg.luks_keyfile == "/tmp/key"
        assert cfg.luks_mapper_prefix == "test-crypt"
        assert cfg.to_output == "/tmp/out.qcow2"
        assert cfg.checksum is True
        assert cfg.cleanup_cache is False


# ---------------------------------------------------------------------------
# DiskProcessingConfig.from_args -- minimal (empty) args
# ---------------------------------------------------------------------------


class TestDiskProcessingConfigFromArgsMinimal:
    """from_args with no attributes -> all defaults."""

    def test_from_args_minimal(self, empty_args):
        cfg = DiskProcessingConfig.from_args(empty_args)
        assert cfg.workdir is None
        assert cfg.skip_vmdk_inspection is False
        assert cfg.flatten is False
        assert cfg.flatten_format == "qcow2"
        assert cfg.dry_run is False
        assert cfg.no_backup is False
        assert cfg.regen_initramfs is True
        assert cfg.fstab_mode == "stabilize-all"
        assert cfg.serial_console is True
        assert cfg.backend == "vmcraft"
        assert cfg.out_format == "qcow2"
        assert cfg.compress is False
        assert cfg.compress_level is None
        assert cfg.luks_enable is False


# ---------------------------------------------------------------------------
# DiskProcessingConfig.from_args -- partial args
# ---------------------------------------------------------------------------


class TestDiskProcessingConfigFromArgsPartial:
    """from_args with a subset of attributes -- rest should use defaults."""

    def test_partial_only_workdir(self):
        args = types.SimpleNamespace(workdir="/my/dir")
        cfg = DiskProcessingConfig.from_args(args)
        assert cfg.workdir == "/my/dir"
        assert cfg.flatten is False
        assert cfg.backend == "vmcraft"

    def test_partial_only_flatten(self):
        args = types.SimpleNamespace(flatten=True, flatten_format="raw")
        cfg = DiskProcessingConfig.from_args(args)
        assert cfg.flatten is True
        assert cfg.flatten_format == "raw"
        assert cfg.workdir is None

    def test_partial_only_luks(self):
        args = types.SimpleNamespace(luks_enable=True, luks_passphrase="pw")
        cfg = DiskProcessingConfig.from_args(args)
        assert cfg.luks_enable is True
        assert cfg.luks_passphrase == "pw"
        assert cfg.luks_keyfile is None

    def test_partial_only_appliance(self):
        args = types.SimpleNamespace(use_appliance=True, appliance_profile="luks", appliance_memory=2048)
        cfg = DiskProcessingConfig.from_args(args)
        assert cfg.workdir is None


# ---------------------------------------------------------------------------
# DiskProcessingConfig.is_luks_enabled
# ---------------------------------------------------------------------------


class TestDiskProcessingConfigIsLuksEnabled:
    """is_luks_enabled() logic."""

    def test_luks_enabled_when_flag_true(self):
        cfg = DiskProcessingConfig(luks_enable=True)
        assert cfg.is_luks_enabled() is True

    def test_luks_enabled_when_passphrase_set(self):
        cfg = DiskProcessingConfig(luks_passphrase="s3cret")
        assert cfg.is_luks_enabled() is True

    def test_luks_enabled_when_passphrase_env_set(self):
        cfg = DiskProcessingConfig(luks_passphrase_env="LUKS_PW")
        assert cfg.is_luks_enabled() is True

    def test_luks_enabled_when_keyfile_set(self):
        cfg = DiskProcessingConfig(luks_keyfile="/tmp/keyfile")
        assert cfg.is_luks_enabled() is True

    def test_luks_not_enabled_when_none_set(self):
        cfg = DiskProcessingConfig()
        assert cfg.is_luks_enabled() is False


# ---------------------------------------------------------------------------
# MigrationConfig -- defaults
# ---------------------------------------------------------------------------


class TestMigrationConfigDefaults:
    """Verify every default value on a bare MigrationConfig()."""

    def test_cmd_default(self):
        cfg = MigrationConfig()
        assert cfg.cmd is None

    def test_output_dir_default(self):
        cfg = MigrationConfig()
        assert cfg.output_dir == "."

    def test_vm_name_default(self):
        cfg = MigrationConfig()
        assert cfg.vm_name == "converted-vm"

    def test_memory_default(self):
        cfg = MigrationConfig()
        assert cfg.memory == 2048

    def test_vcpus_default(self):
        cfg = MigrationConfig()
        assert cfg.vcpus == 2

    def test_timeout_default(self):
        cfg = MigrationConfig()
        assert cfg.timeout == 60

    def test_health_check_timeout_default(self):
        cfg = MigrationConfig()
        assert cfg.health_check_timeout == 120

    def test_deploy_k8s_default(self):
        cfg = MigrationConfig()
        assert cfg.deploy_k8s is False

    def test_parallel_processing_default(self):
        cfg = MigrationConfig()
        assert cfg.parallel_processing is False


# ---------------------------------------------------------------------------
# MigrationConfig.from_args -- full args
# ---------------------------------------------------------------------------


class TestMigrationConfigFromArgsFull:
    """from_args with every attribute supplied."""

    def test_from_args_full(self, full_migration_args):
        cfg = MigrationConfig.from_args(full_migration_args)
        assert cfg.cmd == "local"
        assert cfg.output_dir == "/output"
        assert cfg.batch_manifest == "/tmp/batch.yaml"
        assert cfg.enable_recovery is True
        assert cfg.vs_action == "export"
        assert cfg.parallel_processing is True
        assert cfg.libvirt_test is True
        assert cfg.qemu_test is True
        assert cfg.vm_name == "my-vm"
        assert cfg.memory == 4096
        assert cfg.vcpus == 4
        assert cfg.uefi is True
        assert cfg.timeout == 120
        assert cfg.keep_domain is True
        assert cfg.headless is True
        assert cfg.health_check is True
        assert cfg.health_check_timeout == 300
        assert cfg.deploy_k8s is True
        assert cfg.k8s_continue_on_error is False
        assert cfg.manifest_workflow_mode is True
        assert cfg.manifest_workflow_dir == "/tmp/mwf"
        assert cfg.workflow_mode is True
        assert cfg.workflow_dir == "/tmp/wf"
        assert cfg.watch_dir == "/tmp/watch"
        assert cfg.dry_run is True
        assert cfg.to_output == "/tmp/out.qcow2"
        assert cfg.flatten is True


# ---------------------------------------------------------------------------
# MigrationConfig.from_args -- minimal (empty) args
# ---------------------------------------------------------------------------


class TestMigrationConfigFromArgsMinimal:
    """from_args with no attributes -> all defaults."""

    def test_from_args_minimal(self, minimal_migration_args):
        cfg = MigrationConfig.from_args(minimal_migration_args)
        assert cfg.cmd is None
        assert cfg.output_dir == "."
        assert cfg.vm_name == "converted-vm"
        assert cfg.memory == 2048
        assert cfg.vcpus == 2
        assert cfg.timeout == 60
        assert cfg.health_check_timeout == 120
        assert cfg.deploy_k8s is False
        assert cfg.parallel_processing is False
        assert cfg.dry_run is False
        assert cfg.flatten is False
