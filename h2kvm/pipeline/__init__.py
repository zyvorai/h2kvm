# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
# https://zyvor.dev · info@zyvor.dev

"""
H2KVM conversion pipelines.

This module provides end-to-end VM conversion pipelines that automate:
- Disk format conversion
- Encryption setup
- TPM enrollment
- Boot configuration
"""

from .vmware_to_luks_tpm import (
    CrypttabUpdater,
    DiskConverter,
    FilesystemMigrator,
    GrubUpdater,
    H2KVMVMwareToLUKSPipeline,
    InitramfsBuilder,
    LUKSEncryptor,
    NBDAttach,
    RootDetector,
    TPMEnroll,
)

__all__ = [
    "CrypttabUpdater",
    "DiskConverter",
    "FilesystemMigrator",
    "GrubUpdater",
    "H2KVMVMwareToLUKSPipeline",
    "InitramfsBuilder",
    "LUKSEncryptor",
    "NBDAttach",
    "RootDetector",
    "TPMEnroll",
]
