# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
# https://zyvor.dev · info@zyvor.dev

"""Detect a Windows root without pulling in the VirtIO installer."""

from __future__ import annotations

import logging
from typing import Any


def is_windows(self: Any, g: Any) -> bool:
    """True when the inspected root looks like Windows."""
    logger = getattr(self, "logger", None)
    root = getattr(self, "inspect_root", None)
    if not root:
        if logger:
            logger.debug("Windows detect: inspect_root missing")
        return False
    try:
        os_type = g.inspect_get_type(root)
        if os_type and str(os_type).lower() == "windows":
            return True
    except Exception:  # pylint: disable=broad-exception-caught
        if logger:
            logger.debug("Windows detect: inspect_get_type failed", exc_info=True)
    for dir_path in ("/Windows", "/WINDOWS", "/winnt", "/WINNT", "/Program Files"):
        try:
            if g.is_dir(dir_path):
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    for hive in (
        "/Windows/System32/config/SOFTWARE",
        "/WINDOWS/System32/config/SOFTWARE",
        "/winnt/system32/config/SOFTWARE",
    ):
        try:
            if g.is_file(hive):
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    if logger:
        logger.log(logging.DEBUG, "Windows detect: no signals")
    return False
