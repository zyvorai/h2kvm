# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/azure/__init__.py
"""Azure VM migration module for h2kvm."""

from __future__ import annotations

from .models import AzureConfig
from .source import AzureSourceProvider

__all__ = ["AzureConfig", "AzureSourceProvider"]
