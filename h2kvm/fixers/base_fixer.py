# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""Base class for all fixer modules."""

# h2kvm/fixers/base_fixer.py
from __future__ import annotations


class BaseFixer:  # pylint: disable=too-few-public-methods
    """Abstract base class for fixer modules; subclasses implement run()."""

    def run(self) -> int:
        """Execute the fixer and return a process-style exit code."""
        raise NotImplementedError
