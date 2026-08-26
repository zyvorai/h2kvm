# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures for vmcraft unit tests."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture()
def mock_logger():
    """Return a Mock that satisfies the logging.Logger interface (no real I/O)."""
    m = Mock(spec=logging.Logger)
    m.name = "mock-logger"
    return m


@pytest.fixture()
def mock_file_ops():
    """Return a configurable Mock that acts as a FileOperations instance.

    Every method returns a sane default.  Tests can override individual
    return values via ``mock_file_ops.<method>.return_value = ...``.
    """
    ops = Mock()
    ops.exists.return_value = False
    ops.is_dir.return_value = False
    ops.is_file.return_value = False
    ops.cat.return_value = ""
    ops.ls.return_value = []
    return ops


@pytest.fixture()
def make_file_ops():
    """Factory fixture: ``make_file_ops(exists=True, cat="hello")`` etc."""

    def _make(
        *,
        exists: bool = False,
        is_dir: bool = False,
        is_file: bool = False,
        cat: str = "",
        ls: list[str] | None = None,
    ) -> Mock:
        ops = Mock()
        ops.exists.return_value = exists
        ops.is_dir.return_value = is_dir
        ops.is_file.return_value = is_file
        ops.cat.return_value = cat
        ops.ls.return_value = ls if ls is not None else []
        return ops

    return _make


@pytest.fixture()
def mock_mount_root(tmp_path: Path) -> Path:
    """Return a temporary directory usable as a mount root."""
    root = tmp_path / "guest_root"
    root.mkdir()
    return root
