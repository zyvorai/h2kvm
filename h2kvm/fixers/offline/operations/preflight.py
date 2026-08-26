# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/offline/operations/preflight.py
"""
Preflight guest inspection for migration readiness.

Runs BEFORE the actual migration/conversion to detect issues early:
  - Encryption mode (LUKS version, cipher, KDF, clevis bindings)
  - Missing virtio drivers (Linux: initramfs modules, Windows: driver files)
  - Boot configuration issues (GRUB misconfiguration, missing initramfs)
  - Incompatible features (BitLocker, unsupported filesystems)
  - Guest OS identification and compatibility assessment

This catches problems before expensive disk transfer/conversion, saving
time and preventing failed migrations.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from h2kvm.core.guestfs_typing import guestfs


@dataclass
class PreflightFinding:
    """A single preflight inspection finding."""

    severity: str  # "critical", "warning", "info"
    category: str  # "encryption", "drivers", "boot", "compat", "os"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for reporting/serialization."""
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class PreflightReport:
    """Complete preflight inspection report."""

    guest_os: dict[str, Any] = field(default_factory=dict)
    findings: list[PreflightFinding] = field(default_factory=list)
    passed: bool = True  # False if any critical findings

    @property
    def critical_count(self) -> int:
        """Number of findings with severity 'critical'."""
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        """Number of findings with severity 'warning'."""
        return sum(1 for f in self.findings if f.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for reporting/serialization."""
        return {
            "passed": self.passed,
            "guest_os": self.guest_os,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": sum(1 for f in self.findings if f.severity == "info"),
            "findings": [f.to_dict() for f in self.findings],
        }


class PreflightInspector:  # pylint: disable=too-few-public-methods
    # Single public entrypoint (inspect()) dispatching to many private
    # _check_*/_detect_* helpers; that's the intended shape of this
    # inspection engine.
    """
    Pre-migration guest inspection engine.

    Examines a disk image to detect potential migration issues
    before expensive conversion/transfer operations begin.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def inspect(  # pylint: disable=too-many-arguments
        # One keyword-only flag per independent check category; each is
        # meant to be individually toggleable by callers.
        self,
        g: guestfs.GuestFS,
        *,
        image_path: Path | None = None,
        check_encryption: bool = True,
        check_drivers: bool = True,
        check_boot: bool = True,
        check_compat: bool = True,
    ) -> PreflightReport:
        """
        Run all preflight checks on a mounted guest filesystem.

        Args:
            g: GuestFS handle (guest should be mounted)
            image_path: Optional path to image for block-level checks
            check_encryption: Check for LUKS/BitLocker encryption
            check_drivers: Check for missing virtio drivers
            check_boot: Check boot configuration
            check_compat: Check compatibility issues

        Returns:
            PreflightReport with all findings
        """
        report = PreflightReport()

        # Detect guest OS first
        report.guest_os = self._detect_guest_os(g)
        is_windows = report.guest_os.get("type") == "windows"
        is_linux = report.guest_os.get("type") == "linux"

        self.logger.info(
            "Preflight inspection: OS=%s type=%s",
            report.guest_os.get("name", "unknown"),
            report.guest_os.get("type", "unknown"),
        )

        if check_encryption:
            self._check_encryption(g, report, image_path=image_path, is_windows=is_windows)

        if check_drivers:
            if is_linux:
                self._check_linux_drivers(g, report)
            elif is_windows:
                self._check_windows_drivers(g, report)

        if check_boot:
            if is_linux:
                self._check_linux_boot(g, report)

        if check_compat:
            self._check_compatibility(g, report, is_windows=is_windows, is_linux=is_linux)

        # Set pass/fail
        report.passed = report.critical_count == 0

        self.logger.info(
            "Preflight result: %s (%d critical, %d warnings)",
            "PASSED" if report.passed else "FAILED",
            report.critical_count,
            report.warning_count,
        )

        return report

    def _detect_guest_os(self, g: guestfs.GuestFS) -> dict[str, Any]:
        # pylint: disable=too-many-branches,too-many-nested-blocks,broad-exception-caught
        # Each guestfs probe (is_dir/is_file/read_file) is wrapped in its
        # own best-effort try/except: a single probe failing (e.g. odd
        # guest filesystem state) must not abort OS detection, which tries
        # several independent detection strategies in sequence.
        """Detect guest OS type and version."""
        info: dict[str, Any] = {"type": "unknown", "name": "unknown"}

        # Check for Windows
        for win_dir in ("/Windows", "/WINDOWS", "/winnt"):
            try:
                if g.is_dir(win_dir):
                    info["type"] = "windows"
                    info["name"] = "Windows"
                    # Try to get version from SOFTWARE hive
                    for sw_path in (
                        f"{win_dir}/System32/config/SOFTWARE",
                        f"{win_dir}/system32/config/SOFTWARE",
                    ):
                        try:
                            if g.is_file(sw_path):
                                info["software_hive"] = sw_path
                                break
                        except Exception:
                            continue
                    return info
            except Exception:
                continue

        # Check for Linux
        try:
            if g.is_file("/etc/os-release"):
                content = g.read_file("/etc/os-release").decode("utf-8", errors="replace")
                info["type"] = "linux"
                for line in content.splitlines():
                    if line.startswith("PRETTY_NAME="):
                        info["name"] = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("ID="):
                        info["distro"] = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("VERSION_ID="):
                        info["version"] = line.split("=", 1)[1].strip().strip('"')
                return info
        except Exception:
            pass

        # Fallback checks
        for hint in ("/bin/bash", "/usr/bin/env", "/etc/passwd"):
            try:
                if g.is_file(hint):
                    info["type"] = "linux"
                    info["name"] = "Linux (unknown distro)"
                    return info
            except Exception:
                continue

        return info

    def _check_encryption(
        self,
        g: guestfs.GuestFS,
        report: PreflightReport,
        *,
        image_path: Path | None = None,
        is_windows: bool = False,
    ) -> None:
        # pylint: disable=broad-exception-caught
        # Each detection probe (guestfs call, subprocess, cryptsetup) is
        # wrapped in its own best-effort try/except: a single probe
        # failing must not abort the other independent encryption checks.
        """Check for disk encryption (LUKS, BitLocker)."""
        # Check BitLocker on Windows
        if is_windows:
            for bde_path in (
                "/Windows/System32/config/SYSTEM",
                "/WINDOWS/System32/config/SYSTEM",
            ):
                try:
                    if g.is_file(bde_path):
                        # Check for BitLocker via FVE metadata markers
                        # BitLocker uses -FVE-FS- signature in the BDE partition
                        report.findings.append(
                            PreflightFinding(
                                severity="info",
                                category="encryption",
                                message="Windows SYSTEM hive found; BitLocker check delegated to migration phase",
                                details={"hive_path": bde_path},
                            )
                        )
                        break
                except Exception:
                    continue

        # Check LUKS on host level (requires image_path for block-level checks)
        if image_path and image_path.exists():
            try:
                result = subprocess.run(
                    ["file", "-b", str(image_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if "LUKS" in result.stdout:
                    # Parse LUKS version
                    luks_info = self._get_luks_info(image_path)
                    if luks_info.get("has_clevis"):
                        report.findings.append(
                            PreflightFinding(
                                severity="warning",
                                category="encryption",
                                message="LUKS volume with Clevis/NBDE binding detected. "
                                "Ensure --clevis-server is configured for auto-unlock.",
                                details=luks_info,
                            )
                        )
                    else:
                        report.findings.append(
                            PreflightFinding(
                                severity="warning",
                                category="encryption",
                                message=f"LUKS{luks_info.get('version', '')} encrypted volume detected. "
                                "Passphrase or keyfile required for migration.",
                                details=luks_info,
                            )
                        )
            except Exception as e:
                self.logger.debug("LUKS check failed: %s", e)

        # Check for /etc/crypttab (indicates LUKS in use)
        try:
            if g.is_file("/etc/crypttab"):
                content = g.read_file("/etc/crypttab").decode("utf-8", errors="replace")
                entries = [
                    l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")
                ]
                if entries:
                    report.findings.append(
                        PreflightFinding(
                            severity="warning",
                            category="encryption",
                            message=f"crypttab has {len(entries)} encrypted volume(s). "
                            "Ensure LUKS keys are available for migration.",
                            details={"entries": entries},
                        )
                    )
        except Exception:
            pass

    def _get_luks_info(self, image_path: Path) -> dict[str, Any]:
        """Get LUKS metadata from a disk image."""
        info: dict[str, Any] = {}
        try:
            result = subprocess.run(
                ["cryptsetup", "luksDump", str(image_path)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            output = result.stdout
            # Parse version
            m = re.search(r"Version:\s+(\d+)", output)
            if m:
                info["version"] = int(m.group(1))
            # Parse cipher
            m = re.search(r"Cipher name:\s+(\S+)", output)
            if m:
                info["cipher"] = m.group(1)
            # Parse KDF
            m = re.search(r"PBKDF:\s+(\S+)", output)
            if m:
                info["kdf"] = m.group(1)
            # Check for clevis token (LUKS2)
            info["has_clevis"] = "clevis" in output.lower()
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort metadata extraction; any cryptsetup/parsing
            # failure should just leave `info` partially filled.
            self.logger.debug("cryptsetup luksDump failed: %s", e)
        return info

    def _check_linux_drivers(  # pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks
        self, g: guestfs.GuestFS, report: PreflightReport
    ) -> None:
        # pylint: disable=broad-exception-caught
        # Scans every installed kernel's module tree for virtio drivers,
        # with a best-effort guestfs probe per module/pattern; a single
        # probe failing must not abort the scan of other kernels/modules.
        """Check if virtio drivers are available in initramfs."""
        virtio_modules = {"virtio_pci", "virtio_blk", "virtio_scsi", "virtio_net"}

        # Check /lib/modules for virtio driver availability
        kernels_checked = 0
        kernels_with_virtio = 0
        try:
            modules_dir = "/lib/modules"
            if g.is_dir(modules_dir):
                for kver in g.ls(modules_dir):
                    kmod_dir = f"{modules_dir}/{kver}"
                    if not g.is_dir(kmod_dir):
                        continue
                    kernels_checked += 1
                    # Check for virtio modules
                    found_modules: set[str] = set()
                    for mod_name in virtio_modules:
                        # Search common paths
                        for pattern in (
                            f"{kmod_dir}/kernel/drivers/virtio/{mod_name}.ko*",
                            f"{kmod_dir}/kernel/drivers/block/{mod_name}.ko*",
                            f"{kmod_dir}/kernel/drivers/net/{mod_name}.ko*",
                            f"{kmod_dir}/kernel/drivers/scsi/{mod_name}.ko*",
                        ):
                            try:
                                matches = g.glob_expand(pattern)
                                if matches:
                                    found_modules.add(mod_name)
                                    break
                            except Exception:
                                continue
                    if found_modules:
                        kernels_with_virtio += 1
                    else:
                        report.findings.append(
                            PreflightFinding(
                                severity="warning",
                                category="drivers",
                                message=f"Kernel {kver} has no virtio modules in standard paths. "
                                "initramfs rebuild will add them if available.",
                                details={"kernel": kver, "searched": list(virtio_modules)},
                            )
                        )
        except Exception as e:
            self.logger.debug("Kernel module check failed: %s", e)

        if kernels_checked == 0:
            report.findings.append(
                PreflightFinding(
                    severity="warning",
                    category="drivers",
                    message="No kernel modules directory found (/lib/modules). initramfs rebuild may fail.",
                )
            )
        elif kernels_with_virtio > 0:
            report.findings.append(
                PreflightFinding(
                    severity="info",
                    category="drivers",
                    message=f"virtio drivers found in {kernels_with_virtio}/{kernels_checked} kernel(s)",
                )
            )

        # Check if initramfs tools are available
        initramfs_tools = {
            "dracut": ["/usr/bin/dracut", "/bin/dracut", "/sbin/dracut"],
            "mkinitramfs": ["/usr/sbin/mkinitramfs", "/sbin/mkinitramfs"],
            "mkinitrd": ["/sbin/mkinitrd", "/usr/sbin/mkinitrd"],
        }
        found_tools = []
        for tool_name, tool_paths in initramfs_tools.items():
            try:
                if any(g.is_file(p) for p in tool_paths):
                    found_tools.append(tool_name)
            except Exception:
                continue

        if not found_tools:
            report.findings.append(
                PreflightFinding(
                    severity="warning",
                    category="boot",
                    message="No initramfs rebuild tool found (dracut/mkinitramfs/mkinitrd). "
                    "Boot may fail without virtio modules in initramfs.",
                    details={"checked": list(initramfs_tools.keys())},
                )
            )
        else:
            report.findings.append(
                PreflightFinding(
                    severity="info",
                    category="boot",
                    message=f"initramfs tool(s) available: {', '.join(found_tools)}",
                )
            )

    def _check_windows_drivers(self, g: guestfs.GuestFS, report: PreflightReport) -> None:
        # pylint: disable=broad-exception-caught
        # Best-effort guestfs probe per driver/path; a single probe
        # failing must not abort the scan of other drivers/paths.
        """Check for existing virtio drivers on Windows."""
        # Check if virtio drivers are already installed (e.g., from a previous migration)
        virtio_drivers = ["viostor.sys", "vioscsi.sys", "netkvm.sys", "balloon.sys"]
        found = []
        for drv in virtio_drivers:
            for sys32 in ("/Windows/System32/drivers", "/WINDOWS/System32/drivers"):
                try:
                    if g.is_file(f"{sys32}/{drv}"):
                        found.append(drv)
                        break
                except Exception:
                    continue

        if found:
            report.findings.append(
                PreflightFinding(
                    severity="info",
                    category="drivers",
                    message=f"VirtIO drivers already present: {', '.join(found)}",
                    details={"found": found},
                )
            )
        else:
            report.findings.append(
                PreflightFinding(
                    severity="info",
                    category="drivers",
                    message="No VirtIO drivers found. They will be injected during migration.",
                )
            )

    def _check_linux_boot(self, g: guestfs.GuestFS, report: PreflightReport) -> None:
        # pylint: disable=broad-exception-caught
        # Each boot-config probe (GRUB, /boot contents, firmware type) is
        # independently best-effort; one probe failing must not abort the
        # others.
        """Check Linux boot configuration for potential issues."""
        # Check GRUB config exists
        grub_paths = [
            "/boot/grub2/grub.cfg",
            "/boot/grub/grub.cfg",
            "/boot/grub/menu.lst",
            "/boot/efi/EFI/fedora/grub.cfg",
            "/boot/efi/EFI/centos/grub.cfg",
            "/boot/efi/EFI/redhat/grub.cfg",
            "/boot/efi/EFI/ubuntu/grub.cfg",
        ]
        grub_found = False
        for gp in grub_paths:
            try:
                if g.is_file(gp):
                    grub_found = True
                    # Check for VMware-specific references that need fixing
                    content = g.read_file(gp).decode("utf-8", errors="replace")
                    if "vmw_pvscsi" in content or "vmxnet3" in content:
                        report.findings.append(
                            PreflightFinding(
                                severity="info",
                                category="boot",
                                message=f"GRUB config {gp} references VMware drivers. "
                                "These will be updated during migration.",
                                details={"path": gp},
                            )
                        )
                    break
            except Exception:
                continue

        if not grub_found:
            report.findings.append(
                PreflightFinding(
                    severity="warning",
                    category="boot",
                    message="No GRUB configuration found. Boot repair may be needed.",
                    details={"checked": grub_paths},
                )
            )

        # Check for initramfs/initrd in /boot
        try:
            if g.is_dir("/boot"):
                boot_files = g.ls("/boot")
                has_vmlinuz = any(f.startswith("vmlinuz") for f in boot_files)
                has_initramfs = any(f.startswith(("initramfs", "initrd")) for f in boot_files)
                if not has_vmlinuz:
                    report.findings.append(
                        PreflightFinding(
                            severity="critical",
                            category="boot",
                            message="No vmlinuz kernel image found in /boot. VM cannot boot.",
                        )
                    )
                if not has_initramfs:
                    report.findings.append(
                        PreflightFinding(
                            severity="critical",
                            category="boot",
                            message="No initramfs/initrd found in /boot. VM cannot boot.",
                        )
                    )
        except Exception:
            pass

        # Check firmware type (BIOS vs UEFI)
        try:
            if g.is_dir("/boot/efi") or g.is_dir("/sys/firmware/efi"):
                report.findings.append(
                    PreflightFinding(
                        severity="info",
                        category="boot",
                        message="UEFI boot detected. Ensure OVMF firmware is configured.",
                    )
                )
            else:
                report.findings.append(
                    PreflightFinding(
                        severity="info",
                        category="boot",
                        message="BIOS boot detected.",
                    )
                )
        except Exception:
            pass

    def _check_compatibility(  # pylint: disable=too-many-branches,too-many-nested-blocks
        self,
        g: guestfs.GuestFS,
        report: PreflightReport,
        *,
        is_windows: bool = False,
        is_linux: bool = False,
    ) -> None:
        # pylint: disable=broad-exception-caught
        # Each compatibility probe is independently best-effort; one probe
        # failing (odd fstab entry, guestfs quirk) must not abort the
        # others.
        """Check for general compatibility issues."""
        # pylint: disable=duplicate-code
        # reason: this fstab-line parsing loop mirrors the equivalent
        # fstab-entry parser in vmcraft/enhanced_inspection.py -- structurally
        # similar by coincidence, not shared logic; keeping independent
        # avoids coupling unrelated fstab-parsing code paths.
        # Check for unsupported filesystems
        if is_linux:
            try:
                if g.is_file("/etc/fstab"):
                    content = g.read_file("/etc/fstab").decode("utf-8", errors="replace")
                    for line in content.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if len(parts) >= 3:
                            fstype = parts[2]
                            if fstype in ("zfs", "btrfs"):
                                report.findings.append(
                                    PreflightFinding(
                                        severity="info",
                                        category="compat",
                                        message=f"Filesystem {fstype} detected in fstab. "
                                        "Ensure target supports this filesystem.",
                                        details={"line": line},
                                    )
                                )
            except Exception:
                pass

        # Check for VMware Tools (should be removed)
        if is_linux:
            vmtools_indicators = [
                "/usr/bin/vmware-toolbox-cmd",
                "/etc/vmware-tools",
                "/usr/lib/vmware-tools",
            ]
            for indicator in vmtools_indicators:
                try:
                    if g.exists(indicator):
                        report.findings.append(
                            PreflightFinding(
                                severity="info",
                                category="compat",
                                message="VMware Tools detected. Will be cleaned up during migration.",
                                details={"path": indicator},
                            )
                        )
                        break
                except Exception:
                    continue

        if is_windows:
            # Check for VMware Tools on Windows
            for vmtool in (
                "/Program Files/VMware/VMware Tools",
                "/Program Files (x86)/VMware/VMware Tools",
            ):
                try:
                    if g.is_dir(vmtool):
                        report.findings.append(
                            PreflightFinding(
                                severity="info",
                                category="compat",
                                message="VMware Tools detected on Windows. "
                                "Will be handled during firstboot.",
                                details={"path": vmtool},
                            )
                        )
                        break
                except Exception:
                    continue


__all__ = ["PreflightFinding", "PreflightInspector", "PreflightReport"]
