# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/offline/validation.py
"""
Post-fix validation and health checks for offline guest modifications.

This module provides validation utilities for checking guest system health
after offline modifications have been applied. It includes disk space analysis
and validation suite creation for critical system components.

Extracted from offline_fixer.py to provide single-responsibility module
for validation logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import guest_has_cmd, guest_ls_glob
from h2kvm.core.validation_suite import CheckSpec, ValidationSuite

if TYPE_CHECKING:  # pylint: disable=duplicate-code
    # This typing-only guestfs-availability shim is intentionally identical to the
    # same block in other fixer modules (e.g. service_config_injector.py); it's
    # boilerplate for a fallback typing stub, not shared logic worth extracting.
    import logging

    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
        # Typing-only fallback stub: name must match the real `guestfs` module/class
        # so annotations below resolve the same way whether or not guestfs is installed.
        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...


class OfflineValidationManager:
    """
    Validation manager for offline guest modifications.

    Provides health checks and validation suites to ensure guest system
    is in good state after offline modifications.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize validation manager.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    @staticmethod
    def normalize_validation_results(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """
        Normalize validation results to consistent format.

        Args:
            raw: Raw validation results (various formats)

        Returns:
            Normalized dict with format: {check_name: {passed, critical, details}}
        """
        norm: dict[str, dict[str, Any]] = {}

        for name, v in (raw or {}).items():
            if isinstance(v, dict):
                passed = bool(v.get("passed", v.get("ok", False)))
                critical = bool(v.get("critical", False))
                details = v.get("details")

                if details is None:
                    details = {k: v[k] for k in v if k not in ("passed", "ok", "critical")}

                norm[name] = {"passed": passed, "critical": critical, "details": details}

            elif isinstance(v, bool):
                norm[name] = {"passed": v, "critical": False, "details": {}}

            else:
                norm[name] = {"passed": False, "critical": False, "details": {"raw": repr(v)}}

        return norm

    @staticmethod
    def summarize_validation(norm: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """
        Summarize normalized validation results.

        Args:
            norm: Normalized validation results

        Returns:
            Summary dict with: total, passed, failed, critical_failed, ok
        """
        total = len(norm)
        passed = sum(1 for r in norm.values() if r.get("passed"))
        failed = total - passed
        critical_failed = sum(1 for r in norm.values() if r.get("critical") and not r.get("passed"))

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "critical_failed": critical_failed,
            "ok": failed == 0,
        }

    def analyze_disk_space(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Analyze root filesystem disk space usage.

        Args:
            g: GuestFS handle with root mounted

        Returns:
            Dict with disk space analysis:
            - analysis: "success" or "failed"
            - total_gb, used_gb, free_gb: Space in GB
            - used_percent: Percentage used
            - recommend_resize: True if >80% used
            - recommend_cleanup: True if >90% used
        """
        try:
            stats = g.statvfs("/")
            total = stats["bsize"] * stats["blocks"]
            free = stats["bsize"] * stats["bfree"]
            used = total - free
            used_pct = (used / total) * 100 if total > 0 else 0.0

            out = {
                "analysis": "success",
                "total_gb": total / (1024**3),
                "used_gb": used / (1024**3),
                "free_gb": free / (1024**3),
                "used_percent": round(used_pct, 1),
                "recommend_resize": used_pct > 80,
                "recommend_cleanup": used_pct > 90,
            }

            if out["recommend_resize"]:
                self.logger.warning(f"Disk usage {used_pct:.1f}% - consider resizing disk")

            if out["recommend_cleanup"]:
                self.logger.warning(f"Disk usage {used_pct:.1f}% - critical, cleanup recommended")

            return out

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort disk-space probe over a guestfs handle, must not abort validation
            self.logger.debug("Disk analysis failed: %s", e)
            return {"analysis": "failed", "error": str(e)}

    def create_validation_suite(self, g: guestfs.GuestFS) -> ValidationSuite:
        """
        Create validation suite for checking guest system health.

        Creates a suite of validation checks for critical system components:
        - fstab exists
        - boot files present
        - kernel present
        - initramfs tools available

        Args:
            g: GuestFS handle with root mounted

        Returns:
            ValidationSuite with registered checks
        """
        suite = ValidationSuite(self.logger)

        def check_fstab_exists(_context):
            """Check if /etc/fstab exists."""
            try:
                return g.is_file("/etc/fstab")
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort guestfs probe, absence of fstab must not abort validation
                return False

        def check_boot_files(_context):
            """Check if boot directory structure exists."""
            for p in ("/boot", "/boot/grub", "/boot/grub2", "/boot/efi", "/efi"):
                try:
                    if g.is_dir(p):
                        return True
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort probe over candidate paths; one failing path must not abort the check
                    continue
            return False

        def check_kernel_presence(_context):
            """Check if kernel files are present."""
            kernels = guest_ls_glob(g, "/boot/vmlinuz-*")
            return len(kernels) > 0

        def check_initramfs_tools(_context):
            """Check if initramfs generation tools are available."""
            tools = ["dracut", "update-initramfs", "mkinitcpio"]
            return any(guest_has_cmd(g, t) for t in tools)

        # Register checks (critical checks will cause failure if they fail)
        suite.add_check(CheckSpec(name="fstab_exists", func=check_fstab_exists, critical=True))
        suite.add_check(CheckSpec(name="boot_files_present", func=check_boot_files, critical=True))
        suite.add_check(CheckSpec(name="kernel_present", func=check_kernel_presence, critical=True))
        suite.add_check(CheckSpec(name="initramfs_tools", func=check_initramfs_tools, critical=False))

        return suite


__all__ = ["OfflineValidationManager"]
