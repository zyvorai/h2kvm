# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/config_backup.py
"""
Configuration backup utilities.

Provides functions to back up, restore, and list configuration file backups
before modifications, ensuring safe rollback capability.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_config(config_path: str) -> str:
    """
    Create a timestamped backup of a configuration file.

    Copies the file at ``config_path`` to ``<config_path>.bak.<timestamp>``
    so that the original can be restored if a subsequent modification fails.

    Args:
        config_path: Absolute path to the configuration file to back up.

    Returns:
        The absolute path to the newly created backup file.

    Raises:
        FileNotFoundError: If *config_path* does not exist.
        OSError: If the copy operation fails (permissions, disk space, etc.).
    """
    src = Path(config_path)
    if not src.is_file():
        raise FileNotFoundError(
            f"Cannot back up configuration: file not found at '{config_path}'.\n"
            f"    Verify the path is correct. If the config was recently moved, update the path."
        )

    timestamp = int(time.time())
    backup_name = f"{src.name}.bak.{timestamp}"
    backup_path = src.parent / backup_name

    shutil.copy2(str(src), str(backup_path))
    logger.info("Backed up %s -> %s", config_path, backup_path)

    return str(backup_path)


def restore_config(backup_path: str, config_path: str) -> None:
    """
    Restore a configuration file from a backup.

    Overwrites *config_path* with the contents (and metadata) of
    *backup_path*.

    Args:
        backup_path: Path to the backup file to restore from.
        config_path: Path to the configuration file to overwrite.

    Raises:
        FileNotFoundError: If *backup_path* does not exist.
        OSError: If the copy operation fails.
    """
    src = Path(backup_path)
    if not src.is_file():
        raise FileNotFoundError(
            f"Cannot restore configuration: backup file not found at '{backup_path}'.\n"
            f"    List available backups with: list_backups('{config_path}')\n"
            f"    Backups are stored in the same directory as the original config file."
        )

    shutil.copy2(str(src), str(config_path))
    logger.info("Restored %s from backup %s", config_path, backup_path)


def list_backups(config_path: str) -> list[str]:
    """
    List available backup files for a given configuration file.

    Searches the same directory as *config_path* for files matching the
    pattern ``<filename>.bak.<timestamp>`` and returns them sorted by
    timestamp in descending order (most recent first).

    Args:
        config_path: Path to the original configuration file.

    Returns:
        A list of absolute paths to backup files, newest first.
        Returns an empty list if no backups exist or the parent
        directory is missing.
    """
    src = Path(config_path)
    parent = src.parent

    if not parent.is_dir():
        return []

    prefix = f"{src.name}.bak."
    backups = [str(p) for p in parent.iterdir() if p.name.startswith(prefix) and p.is_file()]

    # Sort by timestamp descending (newest first)
    backups.sort(reverse=True)

    return backups
