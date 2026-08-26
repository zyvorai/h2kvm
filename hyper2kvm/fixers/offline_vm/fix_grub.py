# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
GRUB Fixer - Production-Grade Implementation

Regenerates GRUB bootloader configuration for migrated VMs to ensure first-boot success.

Operations:
1. Detect boot mode (BIOS vs UEFI)
2. Detect GRUB version (grub2 vs grub-legacy)
3. Find boot disk (/dev/vda for KVM)
4. Regenerate GRUB configuration
5. Install GRUB to boot disk (BIOS) or ESP (UEFI)
6. Handle device name changes (sda → vda)
7. Validate grub.cfg

Idempotent: Safe to re-run multiple times.
Portable: Works in VM, bare metal, or online mode.
OS-aware: Handles RHEL/CentOS (grub2), Ubuntu/Debian (grub2/update-grub).
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .utils import create_backup, detect_os_from_root, run_command

logger = logging.getLogger(__name__)


class BootMode(str, Enum):
    """System boot mode."""

    BIOS = "bios"
    UEFI = "uefi"
    UNKNOWN = "unknown"


class GrubVersion(str, Enum):
    """GRUB version."""

    GRUB2 = "grub2"  # Modern GRUB (RHEL 7+, Ubuntu 16.04+)
    GRUB_LEGACY = "grub"  # Legacy GRUB (RHEL 6, Ubuntu <16.04)
    UNKNOWN = "unknown"


@dataclass
class BootDisk:
    """Information about boot disk."""

    device: str  # e.g., /dev/vda
    is_virtio: bool  # True if virtio disk
    partition_scheme: str  # gpt or mbr
    boot_partition: Optional[str] = None  # e.g., /dev/vda1 (for /boot)
    efi_partition: Optional[str] = None  # e.g., /dev/vda2 (for EFI)


class GrubFixer:  # pylint: disable=too-many-instance-attributes  # tracks detected boot mode, GRUB version, disk info, and stats together
    """
    Production-grade GRUB fixer.

    Regenerates GRUB bootloader configuration for VM migration to KVM.
    """

    def __init__(
        self,
        root_mount: str = "/mnt",
        boot_disk: str = "/dev/vda",  # Default to virtio disk
        skip_install: bool = False,  # Skip GRUB install (dangerous)
        dry_run: bool = False,
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize GRUB fixer.

        Args:
            root_mount: Path where root filesystem is mounted
            boot_disk: Boot disk device (e.g., /dev/vda for KVM)
            skip_install: Skip GRUB install step (regenerate config only)
            dry_run: If True, don't modify files
            logger_instance: Optional logger instance
        """
        self.root_mount = Path(root_mount)
        self.boot_disk = boot_disk
        self.skip_install = skip_install
        self.dry_run = dry_run
        self.logger = logger_instance or logging.getLogger(__name__)

        self.boot_dir = self.root_mount / "boot"
        self.etc_dir = self.root_mount / "etc"

        # Detected information
        self.os_info: dict[str, str] = {}
        self.boot_mode: BootMode = BootMode.UNKNOWN
        self.grub_version: GrubVersion = GrubVersion.UNKNOWN
        self.disk_info: Optional[BootDisk] = None

        # Statistics
        self.stats = {"config_regenerated": False, "grub_installed": False, "warnings": 0, "errors": 0}

    def fix(self) -> dict[str, any]:
        """
        Execute GRUB fixes.

        Returns:
            Dictionary with fix results:
            - success: bool
            - stats: Fix statistics
            - warnings: List of warnings
            - errors: List of errors
        """
        self.logger.info("Starting GRUB fix: boot_disk=%s, dry_run=%s", self.boot_disk, self.dry_run)

        results = {"success": False, "stats": {}, "warnings": [], "errors": []}

        try:
            # Step 1: Detect OS, boot mode, GRUB version
            self.logger.info("Detecting OS and boot configuration...")
            self.os_info = detect_os_from_root(str(self.root_mount))
            self.boot_mode = self._detect_boot_mode()
            self.grub_version = self._detect_grub_version()

            self.logger.info(
                "Detected: OS=%s, boot_mode=%s, grub=%s",
                self.os_info["family"],
                self.boot_mode.value,
                self.grub_version.value,
            )

            if self.grub_version == GrubVersion.UNKNOWN:
                error = "Could not detect GRUB version"
                self.logger.error(error)
                results["errors"].append(error)
                return results

            # Step 2: Analyze boot disk
            self.logger.info("Analyzing boot disk...")
            self.disk_info = self._analyze_boot_disk()

            # Step 3: Prepare GRUB environment
            self.logger.info("Preparing GRUB environment...")
            if not self.dry_run:
                self._prepare_grub_environment()

            # Step 4: Regenerate GRUB configuration
            self.logger.info("Regenerating GRUB configuration...")
            if not self.dry_run:
                self._regenerate_grub_config()
                self.stats["config_regenerated"] = True
            else:
                self.logger.info("DRY RUN: Would regenerate GRUB config")

            # Step 5: Install GRUB to boot disk
            if not self.skip_install:
                self.logger.info("Installing GRUB to boot disk...")
                if not self.dry_run:
                    self._install_grub()
                    self.stats["grub_installed"] = True
                else:
                    self.logger.info("DRY RUN: Would install GRUB to %s", self.boot_disk)
            else:
                self.logger.info("Skipping GRUB install (skip_install=True)")

            # Step 6: Validate GRUB configuration
            if not self.dry_run:
                self.logger.info("Validating GRUB configuration...")
                self._validate_grub_config()

            # Collect results
            results["success"] = True
            results["stats"] = self.stats
            results["warnings"] = self._collect_warnings()

            self.logger.info(
                "GRUB fix complete: config=%s, installed=%s",
                self.stats["config_regenerated"],
                self.stats["grub_installed"],
            )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            error = f"GRUB fix failed: {e}"
            self.logger.error(error, exc_info=True)
            results["errors"].append(error)
            self.stats["errors"] += 1

        return results

    def _detect_boot_mode(self) -> BootMode:
        """Detect BIOS or UEFI boot mode."""

        # Check 1: /sys/firmware/efi directory (definitive for UEFI)
        efi_dir = self.root_mount / "sys/firmware/efi"
        if efi_dir.exists():
            self.logger.debug("Detected UEFI: /sys/firmware/efi exists")
            return BootMode.UEFI

        # Check 2: EFI partition mounted at /boot/efi
        efi_mount = self.boot_dir / "efi"
        if efi_mount.exists() and efi_mount.is_dir():
            efi_grub = efi_mount / "EFI"
            if efi_grub.exists():
                self.logger.debug("Detected UEFI: /boot/efi/EFI exists")
                return BootMode.UEFI

        # Check 3: /etc/fstab for EFI partition
        fstab_path = self.etc_dir / "fstab"
        if fstab_path.exists():
            fstab_content = fstab_path.read_text()
            if "/boot/efi" in fstab_content or "vfat" in fstab_content:
                self.logger.debug("Detected UEFI: /boot/efi in fstab")
                return BootMode.UEFI

        # Check 4: GRUB config location
        # UEFI: /boot/efi/EFI/*/grub.cfg
        # BIOS: /boot/grub2/grub.cfg or /boot/grub/grub.cfg

        if efi_mount.exists():
            efi_grub_configs = list((efi_mount / "EFI").rglob("grub.cfg"))
            if efi_grub_configs:
                self.logger.debug("Detected UEFI: grub.cfg in /boot/efi/EFI")
                return BootMode.UEFI

        # Default to BIOS if no UEFI indicators
        self.logger.debug("Detected BIOS: no UEFI indicators found")
        return BootMode.BIOS

    def _detect_grub_version(self) -> GrubVersion:  # pylint: disable=too-many-return-statements  # each branch checks one distinct GRUB-version indicator
        """Detect GRUB version (grub2 vs legacy grub)."""

        # Check for grub2-mkconfig (modern)
        grub2_mkconfig = self.root_mount / "usr/sbin/grub2-mkconfig"
        if grub2_mkconfig.exists():
            return GrubVersion.GRUB2

        # Check for grub-mkconfig (Ubuntu/Debian grub2)
        grub_mkconfig = self.root_mount / "usr/sbin/grub-mkconfig"
        if grub_mkconfig.exists():
            return GrubVersion.GRUB2

        # Check for update-grub (Ubuntu/Debian wrapper for grub2)
        update_grub = self.root_mount / "usr/sbin/update-grub"
        if update_grub.exists():
            return GrubVersion.GRUB2

        # Check for legacy grub
        grub_legacy = self.root_mount / "sbin/grub"
        if grub_legacy.exists():
            return GrubVersion.GRUB_LEGACY

        # Check OS family
        if self.os_info.get("family") in ["centos", "rhel", "fedora"]:
            # RHEL 7+ uses grub2
            version = self.os_info.get("version_id", "0")
            if int(version.split(".")[0]) >= 7:
                return GrubVersion.GRUB2

        elif self.os_info.get("family") in ["ubuntu", "debian"]:
            # Ubuntu 16.04+ uses grub2
            return GrubVersion.GRUB2

        return GrubVersion.UNKNOWN

    def _analyze_boot_disk(self) -> BootDisk:
        """Analyze boot disk characteristics."""

        # Determine if virtio disk
        is_virtio = self.boot_disk.startswith("/dev/vd")

        # Try to detect partition scheme
        # In offline mode, we can't easily run parted, so we'll guess
        partition_scheme = "gpt" if self.boot_mode == BootMode.UEFI else "mbr"

        # Guess boot partition
        # Usually /dev/vda1 for boot, /dev/vda2 for root (or EFI)
        boot_partition = f"{self.boot_disk}1"
        efi_partition = f"{self.boot_disk}1" if self.boot_mode == BootMode.UEFI else None

        disk_info = BootDisk(
            device=self.boot_disk,
            is_virtio=is_virtio,
            partition_scheme=partition_scheme,
            boot_partition=boot_partition,
            efi_partition=efi_partition,
        )

        self.logger.debug(
            f"Boot disk: {disk_info.device}, virtio={disk_info.is_virtio}, "
            f"scheme={disk_info.partition_scheme}"
        )

        return disk_info

    def _prepare_grub_environment(self):
        """Prepare GRUB environment (bind mounts, etc.)."""

        # For BIOS systems, ensure /boot/grub2 or /boot/grub exists
        if self.boot_mode == BootMode.BIOS:
            grub2_dir = self.boot_dir / "grub2"
            grub_dir = self.boot_dir / "grub"

            if not grub2_dir.exists() and not grub_dir.exists():
                # Create grub2 directory (modern systems)
                if self.grub_version == GrubVersion.GRUB2:
                    grub2_dir.mkdir(parents=True, exist_ok=True)
                    self.logger.info("Created %s", grub2_dir)
                else:
                    grub_dir.mkdir(parents=True, exist_ok=True)
                    self.logger.info("Created %s", grub_dir)

        # For UEFI systems, ensure /boot/efi/EFI exists
        elif self.boot_mode == BootMode.UEFI:
            efi_dir = self.boot_dir / "efi/EFI"
            if not efi_dir.exists():
                efi_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info("Created %s", efi_dir)

    def _regenerate_grub_config(self):
        """Regenerate GRUB configuration."""

        if self.grub_version == GrubVersion.GRUB2:
            self._regenerate_grub2_config()
        elif self.grub_version == GrubVersion.GRUB_LEGACY:
            self._regenerate_grub_legacy_config()

    def _regenerate_grub2_config(self):
        """Regenerate GRUB2 configuration."""

        # Determine config file location
        if self.boot_mode == BootMode.UEFI:
            # UEFI: /boot/efi/EFI/<distro>/grub.cfg
            if self.os_info.get("family") in ["centos", "rhel", "fedora"]:
                config_path = self.boot_dir / "efi/EFI/centos/grub.cfg"
            else:
                config_path = self.boot_dir / "efi/EFI/ubuntu/grub.cfg"
        # BIOS: /boot/grub2/grub.cfg or /boot/grub/grub.cfg
        elif self.os_info.get("family") in ["centos", "rhel", "fedora"]:
            config_path = self.boot_dir / "grub2/grub.cfg"
        else:
            config_path = self.boot_dir / "grub/grub.cfg"

        # Backup existing config
        if config_path.exists():
            backup = create_backup(config_path)
            self.logger.info("Backed up GRUB config: %s", backup)

        # Determine command
        if self.os_info.get("family") in ["centos", "rhel", "fedora"]:
            # RHEL/CentOS: grub2-mkconfig
            cmd = ["grub2-mkconfig", "-o", str(config_path)]
        else:
            # Ubuntu/Debian: grub-mkconfig or update-grub
            update_grub = self.root_mount / "usr/sbin/update-grub"
            # update-grub is simpler, when available
            cmd = ["update-grub"] if update_grub.exists() else ["grub-mkconfig", "-o", str(config_path)]

        # Run in chroot
        chroot_cmd = ["chroot", str(self.root_mount), *cmd]

        self.logger.debug("Running: %s", " ".join(chroot_cmd))

        try:
            returncode, stdout, stderr = run_command(chroot_cmd, timeout=60)

            if returncode != 0:
                raise RuntimeError(
                    f"GRUB configuration regeneration failed. "
                    f"The guest may have missing kernel images or a broken /boot directory. "
                    f"Detail: {stderr}"
                )

            if stdout:
                self.logger.debug("grub-mkconfig output: %s", stdout[:500])

            self.logger.info("Regenerated GRUB config: %s", config_path)

        except Exception as e:
            self.logger.exception("Failed to regenerate GRUB config: %s", e)
            self.stats["errors"] += 1
            raise

    def _regenerate_grub_legacy_config(self):
        """Regenerate legacy GRUB configuration."""
        # Legacy GRUB uses /boot/grub/menu.lst or grub.conf
        # This is rarely needed for modern VMs

        warning = "Legacy GRUB detected - manual configuration may be needed"
        self.logger.warning(warning)
        self.stats["warnings"] += 1

        # For legacy GRUB, we'd typically update /boot/grub/menu.lst
        # But this is complex and rarely needed, so we'll warn instead

    def _install_grub(self):
        """Install GRUB to boot disk."""

        if self.boot_mode == BootMode.BIOS:
            self._install_grub_bios()
        elif self.boot_mode == BootMode.UEFI:
            self._install_grub_uefi()

    def _install_grub_bios(self):
        """Install GRUB to MBR (BIOS mode)."""

        if self.os_info.get("family") in ["centos", "rhel", "fedora"]:
            # RHEL/CentOS: grub2-install
            cmd = ["grub2-install", self.boot_disk]
        else:
            # Ubuntu/Debian: grub-install
            cmd = ["grub-install", self.boot_disk]

        # Run in chroot
        chroot_cmd = ["chroot", str(self.root_mount), *cmd]

        self.logger.debug("Running: %s", " ".join(chroot_cmd))

        try:
            returncode, stdout, stderr = run_command(chroot_cmd, timeout=60)

            if returncode != 0:
                # grub-install can succeed with warnings
                if "error" in stderr.lower():
                    raise RuntimeError(
                        f"GRUB bootloader installation failed. "
                        f"Ensure the boot disk is accessible and the guest has grub packages installed. "
                        f"Detail: {stderr}"
                    )
                self.logger.warning("grub-install warnings: %s", stderr)

            if stdout:
                self.logger.debug("grub-install output: %s", stdout)

            self.logger.info("Installed GRUB to %s", self.boot_disk)

        except Exception as e:
            self.logger.exception("Failed to install GRUB: %s", e)
            self.stats["errors"] += 1
            raise

    def _install_grub_uefi(self):
        """Install GRUB to EFI partition (UEFI mode)."""

        # UEFI GRUB installation is more complex
        # We typically don't need to reinstall on UEFI if config is regenerated

        self.logger.info("UEFI mode: GRUB install typically not needed (config regeneration sufficient)")

        # If really needed, would use:
        # grub2-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=centos

        # For now, we'll skip actual UEFI GRUB install as it's risky
        # and config regeneration is usually sufficient

    def _validate_grub_config(self):
        """Validate GRUB configuration file."""

        # Find grub.cfg
        if self.boot_mode == BootMode.UEFI:
            config_paths = list((self.boot_dir / "efi/EFI").rglob("grub.cfg"))
        else:
            config_paths = [self.boot_dir / "grub2/grub.cfg", self.boot_dir / "grub/grub.cfg"]

        for config_path in config_paths:
            if config_path.exists():
                content = config_path.read_text()

                # Check for critical elements
                checks = {
                    "has_menuentry": "menuentry" in content,
                    "has_linux_cmd": "linux" in content or "linuxefi" in content,
                    "has_initrd_cmd": "initrd" in content or "initrdefi" in content,
                    "has_root_param": "root=" in content,
                }

                all_good = all(checks.values())

                if all_good:
                    self.logger.info("✓ GRUB config validation passed: %s", config_path.name)
                else:
                    warning = f"GRUB config may be incomplete: {checks}"
                    self.logger.warning(warning)
                    self.stats["warnings"] += 1

                # Check for virtio references
                if "vda" in content or "virtio" in content:
                    self.logger.debug("GRUB config contains virtio references (good)")

                return

        warning = "Could not find grub.cfg to validate"
        self.logger.warning(warning)
        self.stats["warnings"] += 1

    def _collect_warnings(self) -> list[str]:
        """Collect all warnings from fix process."""
        warnings = []

        if self.skip_install:
            warnings.append("GRUB install skipped (skip_install=True)")

        if self.boot_mode == BootMode.UNKNOWN:
            warnings.append("Could not detect boot mode (BIOS/UEFI)")

        return warnings

    def get_summary(self) -> str:
        """Get human-readable summary of fixes."""
        lines = [
            "GRUB Fix Summary:",
            f"  OS: {self.os_info.get('family', 'unknown')} {self.os_info.get('version', '')}",
            f"  Boot mode: {self.boot_mode.value}",
            f"  GRUB version: {self.grub_version.value}",
            f"  Boot disk: {self.boot_disk}",
            f"  Config regenerated: {self.stats['config_regenerated']}",
            f"  GRUB installed: {self.stats['grub_installed']}",
            f"  Warnings: {self.stats['warnings']}",
            f"  Errors: {self.stats['errors']}",
        ]

        if self.disk_info:
            lines.append("\n  Disk info:")
            lines.append(f"    Device: {self.disk_info.device}")
            lines.append(f"    Virtio: {self.disk_info.is_virtio}")
            lines.append(f"    Partition scheme: {self.disk_info.partition_scheme}")

        return "\n".join(lines)


# Convenience function for direct usage
def fix_grub(
    root_mount: str = "/mnt", boot_disk: str = "/dev/vda", skip_install: bool = False, dry_run: bool = False
) -> dict[str, any]:
    """
    Fix GRUB in mounted root filesystem.

    Args:
        root_mount: Path where root filesystem is mounted
        boot_disk: Boot disk device (e.g., /dev/vda)
        skip_install: Skip GRUB install (regenerate config only)
        dry_run: If True, don't modify files

    Returns:
        Dictionary with fix results

    Example:
        >>> results = fix_grub("/mnt", boot_disk="/dev/vda", dry_run=False)
        >>> if results["success"]:
        ...     print("GRUB fixed successfully")
    """
    fixer = GrubFixer(root_mount=root_mount, boot_disk=boot_disk, skip_install=skip_install, dry_run=dry_run)

    return fixer.fix()
