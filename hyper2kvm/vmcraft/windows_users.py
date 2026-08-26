# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/windows_users.py
"""
Windows user and group management.

Provides Windows user account operations:
- List local users from SAM registry
- Check user groups and memberships
- Identify administrator accounts
- Detect disabled accounts
- Query user properties
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ._utils import run_sudo

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class WindowsUserManager:
    """
    Windows user and group management.

    Manages Windows user accounts via registry (SAM hive) access.
    """

    def __init__(self, users_logger: logging.Logger, mount_root: Path):
        """
        Initialize Windows user manager.

        Args:
            users_logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = users_logger
        self.mount_root = mount_root

    def list_users(self) -> list[dict[str, Any]]:
        """
        List all local Windows user accounts.

        Reads user information from SAM registry hive.

        Returns:
            List of user account dictionaries with name, SID, flags, etc.
        """
        users: list[dict[str, Any]] = []

        # Path to SAM registry hive
        sam_paths = [
            "Windows/System32/config/SAM",
            "WINDOWS/SYSTEM32/CONFIG/SAM",
            "windows/system32/config/SAM",
        ]

        sam_path = None
        for path in sam_paths:
            full_path = self.mount_root / path
            if full_path.exists():
                sam_path = full_path
                break

        if not sam_path:
            self.logger.warning("SAM registry hive not found")
            return users

        try:
            # Use chntpw or reged to read SAM
            # For now, we'll use a simpler approach via registry dump
            users = self._parse_sam_registry(sam_path)

        # pylint: disable-next=broad-exception-caught  # registry parsing has multiple fallback tools/formats; a failure must not abort the caller
        except Exception as e:
            self.logger.warning(f"Error reading SAM registry: {e}")

        return users

    def _parse_sam_registry(self, sam_path: Path) -> list[dict[str, Any]]:
        """
        Parse SAM registry to extract user accounts.

        Uses chntpw or hivexsh if available.

        Args:
            sam_path: Path to SAM registry hive

        Returns:
            List of user dictionaries
        """
        users: list[dict[str, Any]] = []

        try:
            # Try using chntpw -l to list users
            result = run_sudo(self.logger, ["chntpw", "-l", str(sam_path)], check=False, capture=True)

            if result.returncode == 0:
                users = self._parse_chntpw_output(result.stdout)
            else:
                # Fallback: try hivexsh
                users = self._parse_with_hivexsh(sam_path)

        except FileNotFoundError:
            self.logger.debug("chntpw not available, trying hivexsh")
            users = self._parse_with_hivexsh(sam_path)
        # pylint: disable-next=broad-exception-caught  # chntpw output format varies; a parse failure must not abort the caller
        except Exception as e:
            self.logger.warning(f"Error parsing SAM: {e}")

        return users

    def _parse_chntpw_output(self, output: str) -> list[dict[str, Any]]:
        """
        Parse chntpw -l output to extract users.

        Example output:
        | RID -|---------- Username ------------| Admin? |- Lock? --|
        | 01f4 | Administrator                  | ADMIN  | dis/lock |
        | 01f5 | Guest                          |        | dis/lock |
        | 03e8 | User1                          |        |          |
        """
        users = []

        for line in output.splitlines():
            line = line.strip()

            # Skip header and separator lines
            if not line or (line.startswith("|") and ("RID" in line or "---" in line)):
                continue

            # Parse user lines
            if line.startswith("|"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5:
                    rid = parts[1]
                    username = parts[2]
                    is_admin = "ADMIN" in parts[3]
                    is_disabled = "dis" in parts[4].lower()
                    is_locked = "lock" in parts[4].lower()

                    users.append(
                        {
                            "username": username,
                            "rid": rid,
                            "is_admin": is_admin,
                            "is_disabled": is_disabled,
                            "is_locked": is_locked,
                        }
                    )

        return users

    def _parse_with_hivexsh(self, sam_path: Path) -> list[dict[str, Any]]:
        """
        Parse SAM using hivexsh tool.

        Args:
            sam_path: Path to SAM hive

        Returns:
            List of user dictionaries
        """
        users = []

        try:
            # Use hivexsh to navigate SAM\Domains\Account\Users\Names

            result = run_sudo(self.logger, ["hivexsh", "-w", str(sam_path)], check=False, capture=True)

            # Parse hivexsh output
            # This is a simplified version - full implementation would
            # need to read user properties from the registry values

            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "hivexsh")):
                    users.append(
                        {
                            "username": line,
                            "rid": None,
                            "is_admin": False,
                            "is_disabled": False,
                            "is_locked": False,
                        }
                    )

        # pylint: disable-next=broad-exception-caught  # hivexsh output format varies; a parse failure must not abort the caller
        except Exception as e:
            self.logger.debug(f"hivexsh parsing failed: {e}")

        return users

    def get_user_groups(self, username: str) -> list[str]:
        """
        Get groups that a user is a member of.

        Args:
            username: Username to query

        Returns:
            List of group names
        """
        groups: list[str] = []

        # This would require parsing SAM and SECURITY hives
        # For now, we'll return common groups based on user properties

        users = self.list_users()
        user = next((u for u in users if u["username"].lower() == username.lower()), None)

        if user:
            # All users are in Users group
            groups.append("Users")

            # Administrators
            if user.get("is_admin"):
                groups.append("Administrators")

            # Guest account
            if username.lower() == "guest":
                groups.append("Guests")

        return groups

    def is_administrator(self, username: str) -> bool:
        """
        Check if user is in Administrators group.

        Args:
            username: Username to check

        Returns:
            True if user is an administrator
        """
        users = self.list_users()
        user = next((u for u in users if u["username"].lower() == username.lower()), None)

        if user:
            return user.get("is_admin", False)

        return False

    def is_disabled(self, username: str) -> bool:
        """
        Check if user account is disabled.

        Args:
            username: Username to check

        Returns:
            True if account is disabled
        """
        users = self.list_users()
        user = next((u for u in users if u["username"].lower() == username.lower()), None)

        if user:
            return user.get("is_disabled", False)

        return False

    def get_user_info(self, username: str) -> dict[str, Any] | None:
        """
        Get detailed information about a user.

        Args:
            username: Username to query

        Returns:
            Dict with user information or None if not found
        """
        users = self.list_users()
        user = next((u for u in users if u["username"].lower() == username.lower()), None)

        if user:
            # Enhance with group information
            user["groups"] = self.get_user_groups(username)
            return user

        return None

    def list_administrators(self) -> list[str]:
        """
        List all administrator accounts.

        Returns:
            List of administrator usernames
        """
        users = self.list_users()
        return [u["username"] for u in users if u.get("is_admin", False)]

    def list_enabled_users(self) -> list[str]:
        """
        List all enabled user accounts.

        Returns:
            List of enabled usernames
        """
        users = self.list_users()
        return [u["username"] for u in users if not u.get("is_disabled", False)]

    def list_disabled_users(self) -> list[str]:
        """
        List all disabled user accounts.

        Returns:
            List of disabled usernames
        """
        users = self.list_users()
        return [u["username"] for u in users if u.get("is_disabled", False)]

    def get_user_count(self) -> dict[str, int]:
        """
        Get user account statistics.

        Returns:
            Dict with counts of total, enabled, disabled, admin users
        """
        users = self.list_users()

        return {
            "total": len(users),
            "enabled": sum(1 for u in users if not u.get("is_disabled", False)),
            "disabled": sum(1 for u in users if u.get("is_disabled", False)),
            "administrators": sum(1 for u in users if u.get("is_admin", False)),
        }
