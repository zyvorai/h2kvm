# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures for converters tests."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest


@pytest.fixture()
def mock_logger():
    """Return a stdlib-style mock logger with all standard levels."""
    logger = Mock(spec=logging.Logger)
    logger.name = "test"
    logger.isEnabledFor = Mock(return_value=False)
    return logger
