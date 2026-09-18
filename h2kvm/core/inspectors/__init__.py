# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""OS-specific guest inspection extractors."""

from .linux_extractor import LinuxGuestExtractor
from .windows_extractor import WindowsGuestExtractor

__all__ = ["LinuxGuestExtractor", "WindowsGuestExtractor"]
