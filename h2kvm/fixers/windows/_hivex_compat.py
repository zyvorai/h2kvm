# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Shared optional-dependency probe for the ``hivex`` package.

Several Windows fixer modules read raw registry hives via ``hivex`` when
it's installed and gracefully skip that check when it isn't. Each used to
duplicate this try/except import guard, which pylint's duplicate-code
(R0801) checker flagged as cross-file duplication. This module provides
the single canonical probe; callers do::

    from h2kvm.fixers.windows._hivex_compat import HIVEX_AVAILABLE, hivex
"""

from __future__ import annotations

try:
    import hivex  # type: ignore

    HIVEX_AVAILABLE = True
except ImportError:
    hivex = None  # type: ignore
    HIVEX_AVAILABLE = False

__all__ = ["HIVEX_AVAILABLE", "hivex"]
