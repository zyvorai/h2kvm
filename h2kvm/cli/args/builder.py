# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/args/builder.py
"""
Argument parser builder for h2kvm CLI.

This module constructs the main ArgumentParser with all command-line arguments,
help text formatting, and epilog examples (YAML, systemd).
"""

from __future__ import annotations

import argparse

from h2kvm.cli.help_texts import FEATURE_SUMMARY, SYSTEMD_EXAMPLE, YAML_EXAMPLE
from h2kvm.config.systemd_template import SYSTEMD_UNIT_TEMPLATE
from h2kvm.core.logger import c


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    """Combines raw description formatting with default value display in help."""


def _build_epilog() -> str:
    return (
        c("YAML examples:\n", "cyan", ["bold"])
        + c(YAML_EXAMPLE, "cyan")
        + "\n"
        + c("Feature summary:\n", "cyan", ["bold"])
        + c(FEATURE_SUMMARY, "cyan")
        + c("\nSystemd Service Example:\n", "cyan", ["bold"])
        + c(SYSTEMD_UNIT_TEMPLATE + SYSTEMD_EXAMPLE, "cyan")
    )
