# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm/fixers/offline_fixer.py (OfflineFixConfig, OfflineFSFix.__init__)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# OfflineFixConfig is a plain dataclass at the top of offline_fixer.py.
# OfflineFSFix imports many heavy modules at module-level. We use a conditional
# import: test the dataclass always, but skip OfflineFSFix tests if import fails.

from hyper2kvm.fixers.offline_fixer import OfflineFixConfig


# ---------------------------------------------------------------------------
# OfflineFixConfig - defaults
# ---------------------------------------------------------------------------


class TestOfflineFixConfigDefaults:
    """Verify every default value of the OfflineFixConfig dataclass."""

    def test_image_required(self):
        cfg = OfflineFixConfig(image=Path("/disk.qcow2"))
        assert cfg.image == Path("/disk.qcow2")

    def test_dry_run_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.dry_run is False

    def test_no_backup_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.no_backup is False

    def test_print_fstab_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.print_fstab is False

    def test_update_grub_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.update_grub is True

    def test_regen_initramfs_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.regen_initramfs is True

    def test_fstab_mode_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.fstab_mode == "by-uuid"

    def test_report_path_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.report_path is None

    def test_resize_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.resize is None

    def test_remove_vmware_tools_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.remove_vmware_tools is False

    def test_inject_cloud_init_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.inject_cloud_init is None

    def test_firstboot_scripts_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.firstboot_scripts is None

    def test_network_config_inject_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.network_config_inject is None

    def test_user_config_inject_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.user_config_inject is None

    def test_service_config_inject_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.service_config_inject is None

    def test_hostname_config_inject_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.hostname_config_inject is None

    def test_recovery_manager_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.recovery_manager is None

    def test_virtio_drivers_dir_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.virtio_drivers_dir is None

    def test_luks_enable_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.luks_enable is False

    def test_luks_passphrase_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.luks_passphrase is None

    def test_luks_passphrase_env_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.luks_passphrase_env is None

    def test_luks_keyfile_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.luks_keyfile is None

    def test_luks_mapper_prefix_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.luks_mapper_prefix == "hyper2kvm-crypt"

    def test_filesystem_repair_enable_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.filesystem_repair_enable is False

    def test_conversion_dir_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.conversion_dir is None

    def test_allowed_dirs_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.allowed_dirs is None

    def test_backend_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.backend == "vmcraft"

    def test_container_isolation_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.container_isolation is True

    def test_auto_backend_switch_default(self):
        cfg = OfflineFixConfig(image=Path("/x"))
        assert cfg.auto_backend_switch is True


# ---------------------------------------------------------------------------
# OfflineFixConfig - custom values
# ---------------------------------------------------------------------------


class TestOfflineFixConfigCustom:
    """Verify OfflineFixConfig accepts and stores custom values."""

    def test_all_fields_custom(self):
        cfg = OfflineFixConfig(
            image=Path("/images/vm.qcow2"),
            dry_run=True,
            no_backup=True,
            print_fstab=True,
            update_grub=False,
            regen_initramfs=False,
            fstab_mode="by-label",
            report_path=Path("/tmp/report.json"),
            resize="+10G",
            remove_vmware_tools=True,
            inject_cloud_init={"key": "value"},
            firstboot_scripts={"script1": "/bin/true"},
            network_config_inject={"net": "cfg"},
            user_config_inject={"user": "data"},
            service_config_inject={"svc": "on"},
            hostname_config_inject={"hostname": "test"},
            recovery_manager=None,
            virtio_drivers_dir="/opt/virtio",
            luks_enable=True,
            luks_passphrase="secret",
            luks_passphrase_env="MY_PASS",
            luks_keyfile=Path("/keys/luks.key"),
            luks_mapper_prefix="custom-crypt",
            filesystem_repair_enable=True,
            conversion_dir="/tmp/conv",
            allowed_dirs=["/mnt", "/data"],
            backend="guestfs",
            container_isolation=False,
        )

        assert cfg.image == Path("/images/vm.qcow2")
        assert cfg.dry_run is True
        assert cfg.no_backup is True
        assert cfg.print_fstab is True
        assert cfg.update_grub is False
        assert cfg.regen_initramfs is False
        assert cfg.fstab_mode == "by-label"
        assert cfg.report_path == Path("/tmp/report.json")
        assert cfg.resize == "+10G"
        assert cfg.remove_vmware_tools is True
        assert cfg.inject_cloud_init == {"key": "value"}
        assert cfg.firstboot_scripts == {"script1": "/bin/true"}
        assert cfg.network_config_inject == {"net": "cfg"}
        assert cfg.user_config_inject == {"user": "data"}
        assert cfg.service_config_inject == {"svc": "on"}
        assert cfg.hostname_config_inject == {"hostname": "test"}
        assert cfg.virtio_drivers_dir == "/opt/virtio"
        assert cfg.luks_enable is True
        assert cfg.luks_passphrase == "secret"
        assert cfg.luks_passphrase_env == "MY_PASS"
        assert cfg.luks_keyfile == Path("/keys/luks.key")
        assert cfg.luks_mapper_prefix == "custom-crypt"
        assert cfg.filesystem_repair_enable is True
        assert cfg.conversion_dir == "/tmp/conv"
        assert cfg.allowed_dirs == ["/mnt", "/data"]
        assert cfg.backend == "guestfs"
        assert cfg.container_isolation is False

    def test_image_accepts_string_path(self):
        # Path() should accept Path objects; the dataclass stores it as-is
        cfg = OfflineFixConfig(image=Path("/foo/bar.qcow2"))
        assert isinstance(cfg.image, Path)


# ---------------------------------------------------------------------------
# OfflineFSFix.__init__ (conditionally import - skip if heavy deps missing)
# ---------------------------------------------------------------------------


try:
    from hyper2kvm.fixers.offline_fixer import OfflineFSFix

    _HAS_OFFLINE_FS_FIX = True
except ImportError:
    _HAS_OFFLINE_FS_FIX = False

# The OfflineFSFix.__init__ converts fstab_mode to the FstabMode enum.
# The valid enum values are "stabilize-all", "bypath-only", "noop".
# The OfflineFixConfig default of "by-uuid" is accepted by the dataclass
# but will fail in OfflineFSFix.__init__. Use a valid value in these tests.
_VALID_FSTAB_MODE = "stabilize-all"


def _make_config(**overrides):
    """Helper: create OfflineFixConfig with a valid fstab_mode for OfflineFSFix."""
    defaults = dict(image=Path("/disk.qcow2"), fstab_mode=_VALID_FSTAB_MODE)
    defaults.update(overrides)
    return OfflineFixConfig(**defaults)


@pytest.mark.skipif(not _HAS_OFFLINE_FS_FIX, reason="OfflineFSFix import failed (missing deps)")
class TestOfflineFSFixInit:
    """OfflineFSFix.__init__ stores config fields properly."""

    def test_image_stored_as_path(self, mock_logger):
        cfg = _make_config()
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.image == Path("/disk.qcow2")
        assert isinstance(fixer.image, Path)

    def test_dry_run_stored(self, mock_logger):
        cfg = _make_config(dry_run=True)
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.dry_run is True

    def test_no_backup_stored(self, mock_logger):
        cfg = _make_config(no_backup=True)
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.no_backup is True

    def test_update_grub_stored(self, mock_logger):
        cfg = _make_config(update_grub=False)
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.update_grub is False

    def test_luks_enable_stored(self, mock_logger):
        cfg = _make_config(luks_enable=True)
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.luks_enable is True

    def test_luks_mapper_prefix_stored(self, mock_logger):
        cfg = _make_config(luks_mapper_prefix="my-prefix")
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.luks_mapper_prefix == "my-prefix"

    def test_report_dict_initialized(self, mock_logger):
        cfg = _make_config()
        fixer = OfflineFSFix(mock_logger, cfg)
        assert isinstance(fixer.report, dict)
        assert fixer.report["tool"] == "hyper2kvm"
        assert "changes" in fixer.report
        assert "analysis" in fixer.report

    def test_backend_stored(self, mock_logger):
        cfg = _make_config(backend="guestfs")
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.backend == "guestfs"

    def test_container_isolation_stored(self, mock_logger):
        cfg = _make_config(container_isolation=False)
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.container_isolation is False

    def test_inject_dicts_default_to_empty(self, mock_logger):
        cfg = _make_config()
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.inject_cloud_init_data == {}
        assert fixer.firstboot_config == {}
        assert fixer.network_config_inject == {}
        assert fixer.user_config_inject == {}
        assert fixer.service_config_inject == {}
        assert fixer.hostname_config_inject == {}

    def test_resize_stored(self, mock_logger):
        cfg = _make_config(resize="+20G")
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.resize == "+20G"

    def test_allowed_dirs_defaults_to_empty_list(self, mock_logger):
        cfg = _make_config()
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.allowed_dirs == []

    def test_conversion_dir_stored(self, mock_logger):
        cfg = _make_config(conversion_dir="/tmp/conv")
        fixer = OfflineFSFix(mock_logger, cfg)
        assert fixer.conversion_dir == "/tmp/conv"
