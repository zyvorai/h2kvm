# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Azure resource cleanup and tagging utilities."""
# h2kvm/azure/cleanup.py

from __future__ import annotations


def make_tags(*, enable: bool, run_tag: str, vm_name: str) -> dict[str, str]:
    """
    Create resource tags for Azure resources created during migration.

    Args:
        enable: Whether to create tags
        run_tag: Unique identifier for this migration run
        vm_name: Name of the VM being migrated

    Returns:
        Dictionary of tags to apply to Azure resources
    """
    if not enable:
        return {}

    return {
        "h2kvm": "true",
        "h2kvm-run": run_tag,
        "h2kvm-vm": vm_name,
        "h2kvm-managed": "true",
    }
