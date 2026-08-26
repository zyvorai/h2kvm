# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures for core tests."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest


@pytest.fixture()
def basic_logger():
    """Return a stdlib logger that writes to a NullHandler (no I/O)."""
    logger = logging.getLogger("h2kvm.test")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.fixture()
def mock_logger():
    """Return a Mock suitable for any component expecting a logger interface."""
    m = Mock(spec=logging.Logger)
    m.name = "mock-logger"
    return m


@pytest.fixture()
def make_context():
    """Factory: make_context(key=value, ...) -> dict."""

    def _make(**kw):
        return dict(**kw)

    return _make
