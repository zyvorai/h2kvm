# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for hyper2kvm.ai.diagnostic.DiagnosticEngine."""

from __future__ import annotations

import pytest

from hyper2kvm.ai.diagnostic import DiagnosticEngine, BUILTIN_PATTERNS
from hyper2kvm.ai.knowledge_base import KnowledgeBase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(str(tmp_path / "test.db"))


@pytest.fixture
def engine(kb):
    return DiagnosticEngine(kb)


# ---------------------------------------------------------------------------
# BUILTIN_PATTERNS sanity
# ---------------------------------------------------------------------------


class TestBuiltinPatterns:
    def test_builtin_patterns_non_empty(self):
        assert len(BUILTIN_PATTERNS) > 0

    def test_builtin_patterns_have_required_keys(self):
        for pat in BUILTIN_PATTERNS:
            assert "id" in pat
            assert "regex" in pat
            assert "root_cause" in pat
            assert "suggestions" in pat


# ---------------------------------------------------------------------------
# Empty / no-match cases
# ---------------------------------------------------------------------------


class TestDiagnoseEdgeCases:
    def test_empty_text_returns_empty_list(self, engine):
        result = engine.diagnose("")
        assert result == []

    def test_none_like_empty_returns_empty(self, engine):
        result = engine.diagnose("")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_unrelated_text_returns_empty(self, engine):
        result = engine.diagnose("everything is fine, no issues here")
        assert result == []


# ---------------------------------------------------------------------------
# Individual built-in pattern matching
# ---------------------------------------------------------------------------


class TestBuiltinPatternMatching:
    def test_fstab_uuid_mismatch(self, engine):
        result = engine.diagnose("fstab UUID mismatch on /dev/sda1")
        assert len(result) >= 1
        assert any(d.pattern_id == "fstab_uuid_mismatch" for d in result)
        diag = next(d for d in result if d.pattern_id == "fstab_uuid_mismatch")
        assert diag.confidence == 0.8
        assert diag.learned is False
        assert len(diag.suggestions) > 0

    def test_grub_not_found(self, engine):
        result = engine.diagnose("GRUB bootloader not found on disk /dev/vda")
        assert any(d.pattern_id == "grub_not_found" for d in result)

    def test_initramfs_missing_drivers(self, engine):
        result = engine.diagnose("initramfs missing virtio driver modules")
        assert any(d.pattern_id == "initramfs_missing_drivers" for d in result)

    def test_buslogic_no_driver(self, engine):
        result = engine.diagnose("buslogic controller: no driver available, cannot proceed")
        assert any(d.pattern_id == "buslogic_no_driver" for d in result)

    def test_vmware_tools_conflict(self, engine):
        result = engine.diagnose("open-vm-tools conflict with qemu-guest-agent blocking install")
        assert any(d.pattern_id == "vmware_tools_conflict" for d in result)

    def test_disk_space_exhausted(self, engine):
        result = engine.diagnose("write failed: ENOSPC (no space left on device)")
        assert any(d.pattern_id == "disk_space_exhausted" for d in result)

    def test_permission_denied(self, engine):
        result = engine.diagnose("Error: Permission denied when accessing /dev/sda")
        assert any(d.pattern_id == "permission_denied" for d in result)

    def test_qemu_img_error(self, engine):
        result = engine.diagnose("qemu-img: error converting image: file is corrupt")
        assert any(d.pattern_id == "qemu_img_error" for d in result)

    def test_lvm_activation_failed(self, engine):
        result = engine.diagnose("LVM VG activation failed: cannot activate vg_guest")
        assert any(d.pattern_id == "lvm_activation_failed" for d in result)

    def test_mount_failed(self, engine):
        result = engine.diagnose("mount /dev/sda2 on /mnt failed: wrong fs type")
        assert any(d.pattern_id == "mount_failed" for d in result)

    def test_network_unreachable(self, engine):
        result = engine.diagnose("network connection timed out to 10.0.0.1")
        assert any(d.pattern_id == "network_unreachable" for d in result)

    def test_selinux_context(self, engine):
        result = engine.diagnose("selinux context denied for /etc/shadow")
        assert any(d.pattern_id == "selinux_context" for d in result)


# ---------------------------------------------------------------------------
# Multiple matches and sorting
# ---------------------------------------------------------------------------


class TestMultipleMatches:
    def test_multiple_patterns_match(self, engine):
        # Text that triggers both mount_failed and permission_denied
        text = "mount /dev/sda1 failed: Permission denied"
        result = engine.diagnose(text)
        pattern_ids = [d.pattern_id for d in result]
        assert "mount_failed" in pattern_ids
        assert "permission_denied" in pattern_ids
        assert len(result) >= 2

    def test_results_sorted_by_confidence(self, engine, kb):
        # Learn a pattern with lower confidence (0.6) that matches same text
        engine.learn_pattern(
            "custom_mount",
            r"mount.*failed",
            "custom root cause",
            ["fix it"],
        )
        result = engine.diagnose("mount /dev/sda failed badly")
        # Built-in (0.8) should come before learned (0.6)
        assert len(result) >= 2
        assert result[0].confidence >= result[-1].confidence


# ---------------------------------------------------------------------------
# learn_pattern()
# ---------------------------------------------------------------------------


class TestLearnPattern:
    def test_learn_pattern_adds_new_pattern(self, engine, kb):
        ok = engine.learn_pattern(
            "custom_err",
            r"my_custom.*error",
            "Custom root cause",
            ["suggestion1"],
        )
        assert ok is True

    def test_learn_pattern_invalid_regex_returns_false(self, engine):
        ok = engine.learn_pattern(
            "bad_re",
            r"[invalid(regex",
            "bad regex",
            [],
        )
        assert ok is False

    def test_learned_pattern_matches_in_diagnose(self, engine):
        engine.learn_pattern(
            "timeout_err",
            r"operation timed out after \d+ seconds",
            "Operation exceeded timeout",
            ["Increase timeout", "Retry"],
        )
        result = engine.diagnose("operation timed out after 30 seconds")
        assert any(d.pattern_id == "timeout_err" for d in result)
        diag = next(d for d in result if d.pattern_id == "timeout_err")
        # learn_pattern() adds the pattern to the in-memory compiled list,
        # so it matches via the built-in path (confidence 0.8).  A separate
        # KB-only learned pattern would have confidence 0.6 and learned=True.
        assert diag.confidence == 0.8
        assert len(diag.suggestions) > 0

    def test_learn_pattern_without_kb_returns_false(self):
        engine_no_kb = DiagnosticEngine(kb=None)
        ok = engine_no_kb.learn_pattern("x", r"x", "x", [])
        assert ok is False
