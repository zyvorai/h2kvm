#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
SELinux Relabel Fixer for VM Migration

Triggers boot-time SELinux relabeling for VMs migrated from Hyper-V to KVM.
After offline modifications (fstab, initramfs, GRUB), SELinux contexts may be
incorrect. This fixer uses the lightweight /.autorelabel approach instead of
the expensive fixfiles command.

Strategy:
- Touch /.autorelabel to trigger boot-time relabel
- Avoid fixfiles -F relabel (can take hours on large filesystems)
- Boot-time relabel is faster and runs in parallel
- Only applies to SELinux-enabled systems (RHEL, CentOS, Fedora)

Author: hyper2kvm team
License: Apache 2.0
"""

import logging
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .utils import detect_os_from_root

logger = logging.getLogger(__name__)


class SELinuxMode(Enum):
    """SELinux enforcement modes."""

    DISABLED = "disabled"
    PERMISSIVE = "permissive"
    ENFORCING = "enforcing"
    UNKNOWN = "unknown"


@dataclass
class SELinuxInfo:
    """SELinux configuration information."""

    mode: SELinuxMode
    policy: Optional[str]  # targeted, mls, etc.
    policy_exists: bool
    config_path: Optional[Path]
    autorelabel_path: Optional[Path]


class SELinuxFixer:
    """
    SELinux relabel fixer for migrated VMs.

    This fixer triggers boot-time SELinux relabeling by touching /.autorelabel.
    This is the recommended approach for offline modifications, as it:
    - Runs automatically on next boot
    - Much faster than fixfiles (parallel, optimized)
    - Handles all files correctly
    - No risk of timeout or incomplete relabel

    Usage:
        fixer = SELinuxFixer(root_mount="/mnt")
        result = fixer.fix()

        if result['success']:
            print(f"SELinux relabel scheduled: {result['autorelabel_created']}")
    """

    def __init__(self, root_mount: str = "/mnt", force_relabel: bool = False, dry_run: bool = False):
        """
        Initialize SELinux fixer.

        Args:
            root_mount: Guest filesystem root mount point
            force_relabel: Force relabel even if already scheduled
            dry_run: Don't make changes, only simulate
        """
        self.root_mount = Path(root_mount)
        self.force_relabel = force_relabel
        self.dry_run = dry_run

        # State
        self.os_info: Optional[dict[str, str]] = None
        self.selinux_info: Optional[SELinuxInfo] = None

        # Stats
        self.stats = {
            "selinux_enabled": False,
            "autorelabel_created": False,
            "autorelabel_existed": False,
            "warnings": 0,
            "errors": 0,
        }

        logger.info("SELinuxFixer initialized (root=%s, dry_run=%s)", root_mount, dry_run)

    def fix(self) -> dict[str, any]:
        """
        Run SELinux relabel fix.

        Returns:
            Dict with success status, stats, and details
        """
        logger.info("Starting SELinux relabel fix...")

        try:
            # Step 1: Detect OS
            logger.info("Step 1: Detecting OS...")
            self.os_info = detect_os_from_root(str(self.root_mount))
            logger.info("  OS: %s %s", self.os_info["family"], self.os_info["version"])

            # Step 2: Detect SELinux configuration
            logger.info("Step 2: Detecting SELinux configuration...")
            self.selinux_info = self._detect_selinux()
            logger.info("  SELinux mode: %s", self.selinux_info.mode.value)

            if self.selinux_info.policy:
                logger.info("  SELinux policy: %s", self.selinux_info.policy)

            # Step 3: Check if SELinux is enabled
            if self.selinux_info.mode == SELinuxMode.DISABLED:
                logger.info("SELinux is disabled, skipping relabel")
                return {
                    "success": True,
                    "skipped": True,
                    "reason": "SELinux disabled",
                    "stats": self.stats,
                    "selinux_info": {
                        "mode": self.selinux_info.mode.value,
                        "policy": self.selinux_info.policy,
                    },
                }

            self.stats["selinux_enabled"] = True

            # Step 4: Check if policy exists
            if not self.selinux_info.policy_exists:
                logger.warning("SELinux policy directory not found")
                self.stats["warnings"] += 1

            # Step 5: Touch /.autorelabel
            logger.info("Step 3: Creating /.autorelabel for boot-time relabel...")
            autorelabel_created = self._touch_autorelabel()

            if autorelabel_created:
                logger.info("  ✅ /.autorelabel created")
            else:
                logger.info("  ℹ️  /.autorelabel already exists")

            # Step 6: Validate
            logger.info("Step 4: Validating SELinux configuration...")
            self._validate_selinux()

            logger.info("SELinux relabel fix completed successfully")

            return {
                "success": True,
                "skipped": False,
                "stats": self.stats,
                "selinux_info": {
                    "mode": self.selinux_info.mode.value,
                    "policy": self.selinux_info.policy,
                    "policy_exists": self.selinux_info.policy_exists,
                },
                "autorelabel_path": str(self.selinux_info.autorelabel_path)
                if self.selinux_info.autorelabel_path
                else None,
            }

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            logger.error("SELinux fix failed: %s", e, exc_info=True)
            self.stats["errors"] += 1
            return {"success": False, "error": str(e), "stats": self.stats}

    def _detect_selinux(self) -> SELinuxInfo:
        """
        Detect SELinux configuration.

        Returns:
            SELinuxInfo with mode, policy, and paths
        """
        # Check /etc/selinux/config
        config_path = self.root_mount / "etc/selinux/config"

        mode = SELinuxMode.UNKNOWN
        policy = None

        if config_path.exists():
            logger.debug("Reading SELinux config: %s", config_path)
            content = config_path.read_text()

            # Parse SELINUX=enforcing|permissive|disabled
            for line in content.splitlines():
                line = line.strip()

                if line.startswith("SELINUX="):
                    value = line.split("=", 1)[1].strip()
                    if value == "enforcing":
                        mode = SELinuxMode.ENFORCING
                    elif value == "permissive":
                        mode = SELinuxMode.PERMISSIVE
                    elif value == "disabled":
                        mode = SELinuxMode.DISABLED

                elif line.startswith("SELINUXTYPE="):
                    policy = line.split("=", 1)[1].strip()
        else:
            # No config file = SELinux not installed
            logger.debug("No /etc/selinux/config found, SELinux not installed")
            mode = SELinuxMode.DISABLED

        # Check if policy directory exists
        policy_exists = False
        if policy:
            policy_dir = self.root_mount / f"etc/selinux/{policy}/policy"
            policy_exists = policy_dir.exists()
            logger.debug("Policy directory exists: %s (%s)", policy_exists, policy_dir)

        # /.autorelabel path
        autorelabel_path = self.root_mount / ".autorelabel"

        return SELinuxInfo(
            mode=mode,
            policy=policy,
            policy_exists=policy_exists,
            config_path=config_path if config_path.exists() else None,
            autorelabel_path=autorelabel_path,
        )

    def _touch_autorelabel(self) -> bool:
        """
        Touch /.autorelabel to trigger boot-time relabel.

        Returns:
            True if file was created, False if it already existed
        """
        autorelabel_path = self.selinux_info.autorelabel_path

        if not autorelabel_path:
            raise ValueError(
                "SELinux autorelabel path not configured. "
                "This is usually /.autorelabel — ensure SELinux info was detected from the guest."
            )

        # Check if already exists
        if autorelabel_path.exists():
            logger.debug("/.autorelabel already exists: %s", autorelabel_path)
            self.stats["autorelabel_existed"] = True

            if not self.force_relabel:
                return False

            logger.info("force_relabel=True, recreating /.autorelabel")

        # Touch the file
        if not self.dry_run:
            autorelabel_path.touch()
            logger.debug("Created /.autorelabel: %s", autorelabel_path)
        else:
            logger.info("[DRY-RUN] Would touch: %s", autorelabel_path)

        self.stats["autorelabel_created"] = True
        return True

    def _validate_selinux(self):
        """Validate SELinux configuration."""
        if not self.selinux_info.policy_exists:
            logger.warning("SELinux policy directory not found, relabel may fail")
            self.stats["warnings"] += 1
            return

        # Verify autorelabel was created (if not dry-run)
        if not self.dry_run and not self.selinux_info.autorelabel_path.exists():
            logger.error("/.autorelabel was not created")
            self.stats["errors"] += 1
            return

        logger.debug("SELinux configuration validated")

    def get_summary(self) -> str:
        """
        Get human-readable summary of SELinux fix.

        Returns:
            Formatted summary string
        """
        if not self.selinux_info:
            return "SELinux fix not run yet"

        lines = [
            "SELinux Fix Summary:",
            f"  Mode: {self.selinux_info.mode.value}",
        ]

        if self.selinux_info.policy:
            lines.append(f"  Policy: {self.selinux_info.policy}")

        if self.selinux_info.mode != SELinuxMode.DISABLED:
            lines.extend(
                [
                    f"  Policy exists: {self.selinux_info.policy_exists}",
                    f"  Autorelabel created: {self.stats['autorelabel_created']}",
                    f"  Autorelabel existed: {self.stats['autorelabel_existed']}",
                ]
            )

        lines.extend(
            [
                f"  Warnings: {self.stats['warnings']}",
                f"  Errors: {self.stats['errors']}",
            ]
        )

        if self.selinux_info.mode != SELinuxMode.DISABLED:
            lines.append("")
            lines.append("  On next boot:")
            lines.append("    - SELinux will relabel all files")
            lines.append("    - This may add 1-2 minutes to boot time")
            lines.append("    - /.autorelabel will be deleted after relabel")

        return "\n".join(lines)


def main():
    """Test SELinux fixer."""
    # Simple test
    logging.basicConfig(level=logging.INFO)

    root_mount = sys.argv[1] if len(sys.argv) > 1 else "/mnt"

    fixer = SELinuxFixer(root_mount=root_mount, dry_run=True)
    result = fixer.fix()

    print()
    print(fixer.get_summary())
    print()

    if result["success"]:
        print("✅ SELinux fix completed successfully")
    else:
        print(f"❌ SELinux fix failed: {result.get('error', 'Unknown error')}")

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
