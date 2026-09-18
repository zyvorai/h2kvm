# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""Windows license management module.

Provides functionality for extracting and preserving Windows license information
during VM migration, including product keys, activation state, and license type.
"""

from .extractor import (
    LicenseInfo,
    LicenseType,
    decode_product_key,
    detect_license_type,
    extract_license_info,
)

__all__ = [
    "LicenseInfo",
    "LicenseType",
    "decode_product_key",
    "detect_license_type",
    "extract_license_info",
]
