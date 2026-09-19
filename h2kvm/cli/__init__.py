# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/__init__.py
"""
Enhanced CLI framework.

Provides modern command-line interface with interactive wizards,
progress tracking, and rich output formatting.
"""

from .config import (
    ConfigManager,
    MigrationConfig,
)
from .formatter import (
    OutputFormatter,
    OutputStyle,
    Table,
)
from .progress import (
    ProgressBar,
    ProgressTracker,
    Spinner,
)
from .wizard import (
    MigrationWizard,
    WizardResult,
    WizardStep,
)

__all__ = [
    "ConfigManager",
    "MigrationConfig",
    "MigrationWizard",
    "OutputFormatter",
    "OutputStyle",
    "ProgressBar",
    "ProgressTracker",
    "Spinner",
    "Table",
    "WizardResult",
    "WizardStep",
]
