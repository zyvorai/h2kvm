# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/azure/__init__.py
"""Azure VM migration module for h2kvm."""

from __future__ import annotations

from .models import AzureConfig
from .source import AzureSourceProvider

__all__ = ["AzureConfig", "AzureSourceProvider"]
