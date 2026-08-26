# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures for container tests."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest


@pytest.fixture()
def mock_logger():
    """Return a mock logger with standard logging methods."""
    logger = MagicMock()
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.exception = Mock()
    return logger


@pytest.fixture()
def mock_vmcraft():
    """Return a mock VMCraft instance with exists/is_dir/ls/read_file methods.

    All methods return safe defaults (False, False, [], "") and can be
    overridden per-test via ``mock_vmcraft.exists.side_effect = ...``.
    """
    g = MagicMock()
    g.exists = Mock(return_value=False)
    g.is_dir = Mock(return_value=False)
    g.ls = Mock(return_value=[])
    g.read_file = Mock(return_value="")
    return g
