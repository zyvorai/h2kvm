# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""
H2KVM LUKS Auto-Unlock System

Production-grade LUKS auto-unlock with:
- TPM2 auto unlock
- HashiCorp Vault unlock
- Initramfs safe
- Kubernetes node integration
"""

from .unlocker import (
    Cryptsetup,
    LUKSDevice,
    LUKSUnlocker,
    TPM2KeySource,
    VaultKeySource,
    secure_wipe,
)

__all__ = [
    "Cryptsetup",
    "LUKSDevice",
    "LUKSUnlocker",
    "TPM2KeySource",
    "VaultKeySource",
    "secure_wipe",
]
