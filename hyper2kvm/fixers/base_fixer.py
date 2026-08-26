# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Base class for all fixer modules."""

# hyper2kvm/fixers/base_fixer.py
from __future__ import annotations


class BaseFixer:  # pylint: disable=too-few-public-methods
    """Abstract base class for fixer modules; subclasses implement run()."""

    def run(self) -> int:
        """Execute the fixer and return a process-style exit code."""
        raise NotImplementedError
