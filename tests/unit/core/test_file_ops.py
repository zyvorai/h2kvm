# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for atomic file operations in h2kvm.core.file_ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from h2kvm.core.file_ops import atomic_write, ensure_parent_dir, safe_unlink


# ---------------------------------------------------------------------------
# atomic_write – success path
# ---------------------------------------------------------------------------


def test_atomic_write_creates_file_at_target(tmp_path):
    target = tmp_path / "output.bin"
    with atomic_write(target) as temp:
        temp.write_bytes(b"data")
    assert target.exists()


def test_atomic_write_content_arrives_at_target(tmp_path):
    target = tmp_path / "output.bin"
    payload = b"hello atomic world"
    with atomic_write(target) as temp:
        temp.write_bytes(payload)
    assert target.read_bytes() == payload


def test_atomic_write_temp_file_gone_after_success(tmp_path):
    target = tmp_path / "output.bin"
    temp_ref: Path | None = None
    with atomic_write(target) as temp:
        temp_ref = temp
        temp.write_bytes(b"x")
    assert temp_ref is not None
    assert not temp_ref.exists()


def test_atomic_write_yields_path_object(tmp_path):
    target = tmp_path / "output.bin"
    with atomic_write(target) as temp:
        assert isinstance(temp, Path)
        temp.write_bytes(b"")


def test_atomic_write_overwrites_existing_file(tmp_path):
    target = tmp_path / "output.bin"
    target.write_bytes(b"old content")
    with atomic_write(target) as temp:
        temp.write_bytes(b"new content")
    assert target.read_bytes() == b"new content"


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "c" / "output.bin"
    with atomic_write(target) as temp:
        temp.write_bytes(b"deep")
    assert target.exists()
    assert target.read_bytes() == b"deep"


def test_atomic_write_custom_suffix(tmp_path):
    target = tmp_path / "output.bin"
    with atomic_write(target, suffix=".tmp") as temp:
        assert temp.name.endswith(".tmp")
        temp.write_bytes(b"x")
    assert target.exists()


def test_atomic_write_custom_dir(tmp_path):
    target = tmp_path / "final" / "output.bin"
    (tmp_path / "final").mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    with atomic_write(target, dir=staging) as temp:
        # Temp file should be placed inside the staging directory
        assert temp.parent == staging
        temp.write_bytes(b"staged")
    assert target.read_bytes() == b"staged"


# ---------------------------------------------------------------------------
# atomic_write – error path
# ---------------------------------------------------------------------------


def test_atomic_write_cleans_up_on_error(tmp_path):
    target = tmp_path / "output.bin"
    temp_ref: Path | None = None
    with pytest.raises(RuntimeError, match="boom"):
        with atomic_write(target) as temp:
            temp_ref = temp
            temp.write_bytes(b"partial")
            raise RuntimeError("boom")
    assert temp_ref is not None
    assert not temp_ref.exists()
    assert not target.exists()


def test_atomic_write_reraises_exception(tmp_path):
    target = tmp_path / "output.bin"
    with pytest.raises(ValueError, match="expected"):
        with atomic_write(target) as temp:
            temp.write_bytes(b"x")
            raise ValueError("expected")


def test_atomic_write_delete_on_error_false_keeps_temp(tmp_path):
    target = tmp_path / "output.bin"
    temp_ref: Path | None = None
    with pytest.raises(RuntimeError):
        with atomic_write(target, delete_on_error=False) as temp:
            temp_ref = temp
            temp.write_bytes(b"keep me")
            raise RuntimeError("fail")
    assert temp_ref is not None
    assert temp_ref.exists()
    assert temp_ref.read_bytes() == b"keep me"
    assert not target.exists()


def test_atomic_write_text_mode(tmp_path):
    target = tmp_path / "output.txt"
    with atomic_write(target, mode="w") as temp:
        temp.write_text("hello text")
    assert target.read_text() == "hello text"


def test_atomic_write_target_not_created_on_error(tmp_path):
    target = tmp_path / "never_created.bin"
    with pytest.raises(OSError):
        with atomic_write(target) as temp:
            temp.write_bytes(b"will fail")
            raise OSError("disk full")
    assert not target.exists()


# ---------------------------------------------------------------------------
# safe_unlink
# ---------------------------------------------------------------------------


def test_safe_unlink_deletes_existing_file(tmp_path):
    f = tmp_path / "doomed.txt"
    f.write_text("bye")
    safe_unlink(f)
    assert not f.exists()


def test_safe_unlink_missing_ok_true_no_error(tmp_path):
    missing = tmp_path / "nonexistent.txt"
    # Should not raise
    safe_unlink(missing, missing_ok=True)


def test_safe_unlink_missing_ok_default_is_true(tmp_path):
    missing = tmp_path / "nonexistent.txt"
    # Default missing_ok=True, should not raise
    safe_unlink(missing)


def test_safe_unlink_missing_ok_false_raises(tmp_path):
    missing = tmp_path / "nonexistent.txt"
    with pytest.raises(FileNotFoundError):
        safe_unlink(missing, missing_ok=False)


# ---------------------------------------------------------------------------
# ensure_parent_dir
# ---------------------------------------------------------------------------


def test_ensure_parent_dir_creates_parent(tmp_path):
    target = tmp_path / "subdir" / "file.txt"
    ensure_parent_dir(target)
    assert target.parent.is_dir()


def test_ensure_parent_dir_creates_nested_parents(tmp_path):
    target = tmp_path / "a" / "b" / "c" / "file.txt"
    ensure_parent_dir(target)
    assert target.parent.is_dir()


def test_ensure_parent_dir_no_error_if_exists(tmp_path):
    target = tmp_path / "existing" / "file.txt"
    target.parent.mkdir(parents=True)
    # Should not raise when parent already exists
    ensure_parent_dir(target)
    assert target.parent.is_dir()
