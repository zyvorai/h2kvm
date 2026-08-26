# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
RHEL Boot Repair Components
============================

Critical boot component detection and repair for RHEL/CentOS systems.
Focuses on LVM, udev, dracut, and systemd boot issues.

Based on production experience with RHEL 7/8/9 boot failures.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Severity(Enum):
    """Issue severity levels"""

    CRITICAL = "critical"  # Will prevent boot
    HIGH = "high"  # May prevent boot
    MEDIUM = "medium"  # May cause delays/hangs
    LOW = "low"  # Informational
    INFO = "info"  # No action needed


class FixStatus(Enum):
    """Fix application status"""

    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_NEEDED = "not_needed"


@dataclass
class BootIssue:
    """Detected boot issue"""

    component: str
    severity: Severity
    description: str
    impact: str
    fix_available: bool
    fix_description: str = ""
    detection_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class BootFix:
    """Applied boot fix"""

    component: str
    status: FixStatus
    description: str
    changes_made: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class RHELBootRepair:
    """
    RHEL/CentOS boot repair detection and fixing.

    Detects and fixes critical boot issues including:
    - LVM filter restrictions
    - LVM device file corruption (RHEL 9)
    - udev configuration issues
    - nsswitch.conf ordering problems
    - GRUB configuration issues
    - SELinux context problems
    """

    def __init__(self, chroot_path: str = "/"):
        """
        Initialize RHEL boot repair.

        Args:
            chroot_path: Path to chroot (default: / for live system)
        """
        self.chroot = Path(chroot_path)
        self.logger = logging.getLogger(__name__)
        self.detected_issues: list[BootIssue] = []
        self.applied_fixes: list[BootFix] = []

    def detect_rhel_version(self) -> Optional[int]:
        """
        Detect RHEL/CentOS major version.

        Returns:
            Major version number or None if not RHEL/CentOS
        """
        os_release = self.chroot / "etc/os-release"
        redhat_release = self.chroot / "etc/redhat-release"

        try:
            # Try os-release first (RHEL 7+)
            if os_release.exists():
                content = os_release.read_text()
                for line in content.split("\n"):
                    if line.startswith("VERSION_ID="):
                        version = line.split("=")[1].strip('"').split(".")[0]
                        return int(version)

            # Fallback to redhat-release
            if redhat_release.exists():
                content = redhat_release.read_text()
                # Extract version like "release 8.5" or "release 7.9"
                match = re.search(r"release (\d+)", content)
                if match:
                    return int(match.group(1))

        except Exception as e:
            self.logger.debug(f"Failed to detect RHEL version: {e}")

        return None

    def check_lvm_filter(self) -> Optional[BootIssue]:
        """
        Check LVM filter configuration.

        Returns:
            BootIssue if restrictive filter detected, None otherwise
        """
        lvm_conf = self.chroot / "etc/lvm/lvm.conf"

        if not lvm_conf.exists():
            return None

        try:
            content = lvm_conf.read_text()

            # Look for filter configuration
            filter_match = re.search(r"filter\s*=\s*\[(.*?)\]", content, re.DOTALL)

            if filter_match:
                filter_value = filter_match.group(1).strip()

                # Check if filter accepts all devices (a/.*/  or  a|.*|)
                if re.search(r'"a[/|]\.\*[/|]"', filter_value):
                    # Filter accepts all - this is safe
                    return None

                # Restrictive filter detected
                return BootIssue(
                    component="lvm_filter",
                    severity=Severity.CRITICAL,
                    description="Restrictive LVM filter may block root device",
                    impact="Boot failure: 'LVM root not found' error",
                    fix_available=True,
                    fix_description='Change filter to accept all devices: filter = [ "a/.*/" ]',
                    detection_details={"current_filter": filter_value, "file": str(lvm_conf)},
                )

        except Exception as e:
            self.logger.debug(f"Failed to check LVM filter: {e}")

        return None

    def check_lvm_devices_file(self) -> Optional[BootIssue]:
        """
        Check LVM devices file (RHEL 9+ issue).

        Returns:
            BootIssue if problematic device file detected, None otherwise
        """
        rhel_version = self.detect_rhel_version()

        if rhel_version is None or rhel_version < 9:
            return None

        devices_file = self.chroot / "etc/lvm/devices/system.devices"

        if not devices_file.exists():
            return None

        # Device file exists in RHEL 9+ - this can cause clone issues
        return BootIssue(
            component="lvm_devices_file",
            severity=Severity.HIGH,
            description="LVM device file present (RHEL 9+) - may cause VM clone/snapshot issues",
            impact="Boot failure after VM cloning or snapshot restore",
            fix_available=True,
            fix_description="Remove device file and regenerate: rm system.devices && vgimportdevices -a",
            detection_details={"file": str(devices_file), "rhel_version": rhel_version},
        )

    def check_nsswitch_ordering(self) -> Optional[BootIssue]:
        """
        Check nsswitch.conf group ordering for udev.

        Returns:
            BootIssue if 'files' is not first in group lookup, None otherwise
        """
        nsswitch = self.chroot / "etc/nsswitch.conf"

        if not nsswitch.exists():
            return None

        try:
            content = nsswitch.read_text()

            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("group:"):
                    # Extract lookup order
                    parts = line.split(":")[1].strip().split()

                    if parts and parts[0] != "files":
                        return BootIssue(
                            component="nsswitch_group",
                            severity=Severity.MEDIUM,
                            description="'files' is not first in group lookup order",
                            impact="udev service may hang during boot, causing delays or timeouts",
                            fix_available=True,
                            fix_description="Ensure 'files' comes first: group: files sss ...",
                            detection_details={"current_order": " ".join(parts), "file": str(nsswitch)},
                        )

        except Exception as e:
            self.logger.debug(f"Failed to check nsswitch.conf: {e}")

        return None

    def check_udev_children_max(self) -> Optional[BootIssue]:
        """
        Check udev.children-max for large systems.

        Returns:
            BootIssue if setting is missing on potentially large system, None otherwise
        """
        grub_default = self.chroot / "etc/default/grub"

        if not grub_default.exists():
            return None

        try:
            content = grub_default.read_text()

            # Check if udev.children-max is already set
            if "udev.children-max" in content:
                return None

            # Check if system might benefit from this setting
            # Heuristic: Check for many devices or enterprise hardware indicators
            proc_partitions = self.chroot / "proc/partitions"
            if proc_partitions.exists():
                num_devices = len(
                    [
                        l
                        for l in proc_partitions.read_text().split("\n")
                        if l.strip() and not l.startswith("major")
                    ]
                )

                if num_devices > 20:  # Many devices
                    return BootIssue(
                        component="udev_children_max",
                        severity=Severity.MEDIUM,
                        description="Large number of devices detected, udev.children-max may be needed",
                        impact="Boot delays or timeouts on systems with many devices",
                        fix_available=True,
                        fix_description="Add to kernel cmdline: udev.children-max=1000",
                        detection_details={"device_count": num_devices, "file": str(grub_default)},
                    )

        except Exception as e:
            self.logger.debug(f"Failed to check udev children-max: {e}")

        return None

    def check_grub_lvm_root(self) -> Optional[BootIssue]:
        """
        Check GRUB root configuration for LVM.

        Returns:
            BootIssue if GRUB config has potential LVM root issues, None otherwise
        """
        # Check both BIOS and UEFI locations
        grub_configs = [
            self.chroot / "boot/grub2/grub.cfg",
            self.chroot / "boot/efi/EFI/redhat/grub.cfg",
            self.chroot / "boot/efi/EFI/centos/grub.cfg",
        ]

        for grub_cfg in grub_configs:
            if not grub_cfg.exists():
                continue

            try:
                content = grub_cfg.read_text()

                # Look for LVM root references
                if "root=/dev/mapper/" in content or "root=/dev/" in content:
                    # Check if LVM root is used but initramfs may not have LVM
                    if "root=/dev/mapper/" in content:
                        # This is likely LVM - verify initramfs exists
                        boot_dir = self.chroot / "boot"
                        initramfs_files = list(boot_dir.glob("initramfs-*.img"))

                        if not initramfs_files:
                            return BootIssue(
                                component="grub_lvm_initramfs",
                                severity=Severity.CRITICAL,
                                description="GRUB configured for LVM root but initramfs not found",
                                impact="Boot failure: Cannot find root filesystem",
                                fix_available=True,
                                fix_description="Regenerate initramfs with dracut",
                                detection_details={"grub_config": str(grub_cfg), "boot_dir": str(boot_dir)},
                            )

            except Exception as e:
                self.logger.debug(f"Failed to check GRUB config {grub_cfg}: {e}")

        return None

    def check_selinux_autorelabel(self) -> Optional[BootIssue]:
        """
        Check if SELinux autorelabel is needed.

        Returns:
            BootIssue if autorelabel marker exists (informational), None otherwise
        """
        autorelabel = self.chroot / ".autorelabel"

        if autorelabel.exists():
            return BootIssue(
                component="selinux_autorelabel",
                severity=Severity.INFO,
                description="SELinux autorelabel scheduled on next boot",
                impact="First boot will be slower due to full filesystem relabeling",
                fix_available=False,
                fix_description="This is expected after certain repair operations",
                detection_details={"marker_file": str(autorelabel)},
            )

        return None

    def check_systemd_default_target(self) -> Optional[BootIssue]:
        """
        Check systemd default target configuration.

        Returns:
            BootIssue if default.target is misconfigured, None otherwise
        """
        default_target = self.chroot / "etc/systemd/system/default.target"

        if not default_target.exists():
            return BootIssue(
                component="systemd_default_target",
                severity=Severity.LOW,
                description="systemd default.target symlink not found",
                impact="System may boot to unexpected runlevel",
                fix_available=True,
                fix_description="Create symlink to multi-user.target or graphical.target",
                detection_details={"expected_location": str(default_target)},
            )

        try:
            if default_target.is_symlink():
                target = default_target.resolve()
                if not target.exists():
                    return BootIssue(
                        component="systemd_default_target",
                        severity=Severity.MEDIUM,
                        description="default.target points to non-existent target",
                        impact="Boot may fail or hang at unexpected target",
                        fix_available=True,
                        fix_description="Fix symlink to valid target",
                        detection_details={"symlink": str(default_target), "points_to": str(target)},
                    )

        except Exception as e:
            self.logger.debug(f"Failed to check default.target: {e}")

        return None

    def detect_all_issues(self) -> list[BootIssue]:
        """
        Run all detection checks.

        Returns:
            List of detected boot issues
        """
        self.detected_issues.clear()

        checks = [
            self.check_lvm_filter,
            self.check_lvm_devices_file,
            self.check_nsswitch_ordering,
            self.check_udev_children_max,
            self.check_grub_lvm_root,
            self.check_selinux_autorelabel,
            self.check_systemd_default_target,
        ]

        for check in checks:
            try:
                issue = check()
                if issue:
                    self.detected_issues.append(issue)
                    self.logger.info(f"Detected {issue.severity.value} issue: {issue.component}")
            except Exception as e:
                self.logger.warning(f"Check failed for {check.__name__}: {e}")

        return self.detected_issues

    def fix_lvm_filter(self) -> BootFix:
        """
        Fix restrictive LVM filter.

        Returns:
            BootFix with results
        """
        lvm_conf = self.chroot / "etc/lvm/lvm.conf"

        if not lvm_conf.exists():
            return BootFix(
                component="lvm_filter", status=FixStatus.SKIPPED, description="lvm.conf not found"
            )

        try:
            content = lvm_conf.read_text()
            original_content = content

            # Replace restrictive filter with accept-all filter
            # Match: filter = [ ... ]
            new_content = re.sub(r"(filter\s*=\s*\[)[^]]*(\])", r'\1 "a/.*/", "r|.*|" \2', content)

            if new_content != original_content:
                # Backup original
                backup_path = lvm_conf.parent / f"{lvm_conf.name}.backup"
                lvm_conf.rename(backup_path)

                # Write new config
                lvm_conf.write_text(new_content)

                return BootFix(
                    component="lvm_filter",
                    status=FixStatus.APPLIED,
                    description="Changed LVM filter to accept all devices",
                    changes_made=[f"Backed up to {backup_path}", 'Set filter = [ "a/.*/", "r|.*|" ]'],
                )
            return BootFix(
                component="lvm_filter",
                status=FixStatus.NOT_NEEDED,
                description="LVM filter already accepts all devices",
            )

        except Exception as e:
            return BootFix(
                component="lvm_filter",
                status=FixStatus.FAILED,
                description="Failed to fix LVM filter",
                errors=[str(e)],
            )

    def fix_lvm_devices_file(self) -> BootFix:
        """
        Fix LVM devices file (RHEL 9).

        Returns:
            BootFix with results
        """
        devices_file = self.chroot / "etc/lvm/devices/system.devices"

        if not devices_file.exists():
            return BootFix(
                component="lvm_devices_file",
                status=FixStatus.NOT_NEEDED,
                description="LVM devices file does not exist",
            )

        try:
            # Backup the file
            backup_path = devices_file.parent / f"{devices_file.name}.backup"
            devices_file.rename(backup_path)

            return BootFix(
                component="lvm_devices_file",
                status=FixStatus.APPLIED,
                description="Removed LVM devices file (will be regenerated on boot)",
                changes_made=[
                    f"Backed up to {backup_path}",
                    "File will be regenerated via vgimportdevices on boot",
                ],
            )

        except Exception as e:
            return BootFix(
                component="lvm_devices_file",
                status=FixStatus.FAILED,
                description="Failed to remove LVM devices file",
                errors=[str(e)],
            )

    def fix_nsswitch_ordering(self) -> BootFix:
        """
        Fix nsswitch.conf group ordering.

        Returns:
            BootFix with results
        """
        nsswitch = self.chroot / "etc/nsswitch.conf"

        if not nsswitch.exists():
            return BootFix(
                component="nsswitch_group", status=FixStatus.SKIPPED, description="nsswitch.conf not found"
            )

        try:
            content = nsswitch.read_text()
            lines = content.split("\n")
            modified = False

            for i, line in enumerate(lines):
                if line.strip().startswith("group:"):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        sources = parts[1].strip().split()

                        # Move 'files' to first position if not already
                        if sources and sources[0] != "files" and "files" in sources:
                            sources.remove("files")
                            sources.insert(0, "files")
                            lines[i] = f"group: {' '.join(sources)}"
                            modified = True
                            break

            if modified:
                # Backup original
                backup_path = nsswitch.parent / f"{nsswitch.name}.backup"
                nsswitch.rename(backup_path)

                # Write new config
                nsswitch.write_text("\n".join(lines))

                return BootFix(
                    component="nsswitch_group",
                    status=FixStatus.APPLIED,
                    description="Fixed nsswitch.conf group ordering (files first)",
                    changes_made=[
                        f"Backed up to {backup_path}",
                        "Moved 'files' to first position in group lookup",
                    ],
                )
            return BootFix(
                component="nsswitch_group",
                status=FixStatus.NOT_NEEDED,
                description="nsswitch.conf group ordering already correct",
            )

        except Exception as e:
            return BootFix(
                component="nsswitch_group",
                status=FixStatus.FAILED,
                description="Failed to fix nsswitch.conf",
                errors=[str(e)],
            )

    def fix_systemd_default_target(self) -> BootFix:
        """
        Fix systemd default.target symlink.

        Returns:
            BootFix with results
        """
        default_target = self.chroot / "etc/systemd/system/default.target"
        multi_user_target = self.chroot / "usr/lib/systemd/system/multi-user.target"

        # Alternative location for multi-user.target
        if not multi_user_target.exists():
            multi_user_target = self.chroot / "lib/systemd/system/multi-user.target"

        if not multi_user_target.exists():
            return BootFix(
                component="systemd_default_target",
                status=FixStatus.FAILED,
                description="Cannot find multi-user.target to create symlink",
                errors=["multi-user.target not found in expected locations"],
            )

        try:
            # Remove existing symlink if broken
            if default_target.exists() or default_target.is_symlink():
                default_target.unlink()

            # Create symlink to multi-user.target
            default_target.symlink_to(multi_user_target)

            return BootFix(
                component="systemd_default_target",
                status=FixStatus.APPLIED,
                description="Created default.target symlink to multi-user.target",
                changes_made=[f"Created symlink: {default_target} → {multi_user_target}"],
            )

        except Exception as e:
            return BootFix(
                component="systemd_default_target",
                status=FixStatus.FAILED,
                description="Failed to fix default.target",
                errors=[str(e)],
            )

    def apply_all_fixes(self, auto_fix: bool = True) -> list[BootFix]:
        """
        Apply all available fixes for detected issues.

        Args:
            auto_fix: If True, apply critical and high severity fixes automatically

        Returns:
            List of applied fixes
        """
        self.applied_fixes.clear()

        # First detect all issues
        if not self.detected_issues:
            self.detect_all_issues()

        # Map components to fix functions
        fix_functions = {
            "lvm_filter": self.fix_lvm_filter,
            "lvm_devices_file": self.fix_lvm_devices_file,
            "nsswitch_group": self.fix_nsswitch_ordering,
            "systemd_default_target": self.fix_systemd_default_target,
        }

        for issue in self.detected_issues:
            if not issue.fix_available:
                continue

            # Skip low severity issues unless explicitly requested
            if not auto_fix and issue.severity in [Severity.LOW, Severity.INFO]:
                continue

            # Apply fix if function exists
            if issue.component in fix_functions:
                try:
                    fix = fix_functions[issue.component]()
                    self.applied_fixes.append(fix)

                    if fix.status == FixStatus.APPLIED:
                        self.logger.info(f"Applied fix for {issue.component}: {fix.description}")
                    elif fix.status == FixStatus.FAILED:
                        self.logger.warning(f"Fix failed for {issue.component}: {fix.description}")

                except Exception as e:
                    error_fix = BootFix(
                        component=issue.component,
                        status=FixStatus.FAILED,
                        description="Exception during fix application",
                        errors=[str(e)],
                    )
                    self.applied_fixes.append(error_fix)
                    self.logger.exception(f"Failed to apply fix for {issue.component}: {e}")

        return self.applied_fixes

    def generate_report(self) -> dict[str, Any]:
        """
        Generate comprehensive boot repair report.

        Returns:
            Report dictionary with issues and fixes
        """
        rhel_version = self.detect_rhel_version()

        report = {
            "rhel_version": rhel_version,
            "chroot_path": str(self.chroot),
            "issues_detected": len(self.detected_issues),
            "fixes_applied": len([f for f in self.applied_fixes if f.status == FixStatus.APPLIED]),
            "issues": [],
            "fixes": [],
        }

        # Add issues
        for issue in self.detected_issues:
            report["issues"].append(
                {
                    "component": issue.component,
                    "severity": issue.severity.value,
                    "description": issue.description,
                    "impact": issue.impact,
                    "fix_available": issue.fix_available,
                    "fix_description": issue.fix_description,
                    "details": issue.detection_details,
                }
            )

        # Add fixes
        for fix in self.applied_fixes:
            report["fixes"].append(
                {
                    "component": fix.component,
                    "status": fix.status.value,
                    "description": fix.description,
                    "changes": fix.changes_made,
                    "errors": fix.errors,
                }
            )

        # Summary by severity
        report["summary"] = {
            "critical": len([i for i in self.detected_issues if i.severity == Severity.CRITICAL]),
            "high": len([i for i in self.detected_issues if i.severity == Severity.HIGH]),
            "medium": len([i for i in self.detected_issues if i.severity == Severity.MEDIUM]),
            "low": len([i for i in self.detected_issues if i.severity == Severity.LOW]),
            "info": len([i for i in self.detected_issues if i.severity == Severity.INFO]),
        }

        return report


def detect_and_fix_rhel_boot_issues(chroot_path: str, auto_fix: bool = True) -> dict[str, Any]:
    """
    Convenience function to detect and fix RHEL boot issues.

    Args:
        chroot_path: Path to chroot
        auto_fix: Whether to automatically apply fixes

    Returns:
        Report dictionary with results
    """
    repair = RHELBootRepair(chroot_path)

    # Detect issues
    issues = repair.detect_all_issues()

    # Apply fixes if requested
    if auto_fix and issues:
        repair.apply_all_fixes(auto_fix=True)

    # Generate report
    return repair.generate_report()
