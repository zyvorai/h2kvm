# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Firstboot Integration
==============================

Production-grade systemd-firstboot integration for H2KVM converted images.

Architecture:
    kernel → initramfs → systemd (PID 1) → generators → detect conversion →
    activate firstboot service → log to journal → disable permanently

Components:
    - systemd generator (detection)
    - firstboot service (execution)
    - firstboot script (operations)
    - journal logging (visibility)
    - machine-id reset (trigger)
    - conversion flag (detection marker)
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .firstboot_enterprise import FirstbootConfig, generate_enterprise_firstboot_script


class SystemdFirstboot:
    """
    Systemd firstboot integration for H2KVM.

    Implements production-grade firstboot initialization flow:
    1. Conversion detection via generator
    2. Oneshot service execution
    3. Structured journal logging
    4. Automatic cleanup and disable
    """

    # System paths
    SYSTEM_DIR = Path("/usr/lib/systemd/system")
    GENERATOR_DIR = Path("/usr/lib/systemd/system-generators")
    LIBEXEC_DIR = Path("/usr/libexec")
    CONVERSION_FLAG = Path("/etc/h2kvm/converted")
    MACHINE_ID = Path("/etc/machine-id")
    DBUS_MACHINE_ID = Path("/var/lib/dbus/machine-id")

    def __init__(self, chroot_path: str = "/"):
        """
        Initialize systemd firstboot integration.

        Args:
            chroot_path: Path to chroot (default: / for live system)
        """
        self.chroot = Path(chroot_path)
        self.logger = logging.getLogger(__name__)

    def create_generator(self) -> Path:
        """
        Create systemd generator for firstboot detection.

        The generator runs early in boot and dynamically enables
        the firstboot service only if conversion flag is present.

        Returns:
            Path to created generator
        """
        generator_path = self.chroot / self.GENERATOR_DIR.relative_to("/") / "h2kvm-generator"
        generator_path.parent.mkdir(parents=True, exist_ok=True)

        generator_content = """#!/usr/bin/env python3
\"\"\"
H2KVM systemd generator
Dynamically enables firstboot service if conversion detected
\"\"\"

import os
import sys

RUN_SYSTEM = "/run/systemd/system"
SERVICE = "h2kvm-firstboot.service"
FLAG = "/etc/h2kvm/converted"

def main():
    \"\"\"Enable firstboot service if conversion flag exists\"\"\"

    # Check for conversion flag
    if not os.path.exists(FLAG):
        sys.exit(0)

    # Create wants directory
    wants_dir = os.path.join(RUN_SYSTEM, "multi-user.target.wants")
    os.makedirs(wants_dir, exist_ok=True)

    # Create symlink to enable service
    symlink = os.path.join(wants_dir, SERVICE)
    service_path = f"/usr/lib/systemd/system/{SERVICE}"

    if not os.path.exists(symlink):
        try:
            os.symlink(service_path, symlink)
        except FileExistsError:
            pass

if __name__ == "__main__":
    main()
"""

        generator_path.write_text(generator_content)
        generator_path.chmod(0o755)

        self.logger.info(f"Created systemd generator: {generator_path}")
        return generator_path

    def create_firstboot_service(self) -> Path:
        """
        Create systemd firstboot service unit.

        Returns:
            Path to created service unit
        """
        service_path = self.chroot / self.SYSTEM_DIR.relative_to("/") / "h2kvm-firstboot.service"
        service_path.parent.mkdir(parents=True, exist_ok=True)

        service_content = """[Unit]
Description=H2KVM First Boot Initialization
Documentation=man:h2kvm(1)
DefaultDependencies=no

# Run after filesystem is mounted but before multi-user
After=local-fs.target systemd-remount-fs.service
Before=multi-user.target network-pre.target
Wants=local-fs.target

# Only run if conversion flag exists
ConditionPathExists=/etc/h2kvm/converted

# First boot detection (empty machine-id)
ConditionFirstBoot=yes

[Service]
Type=oneshot
ExecStart=/usr/libexec/h2kvm-firstboot
RemainAfterExit=yes

# Resource limits
MemoryMax=2G
TasksMax=512
CPUQuota=75%

# Security hardening
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/etc /boot /var
ProtectHome=yes
NoNewPrivileges=yes

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=h2kvm-firstboot

[Install]
WantedBy=multi-user.target
"""

        service_path.write_text(service_content)
        service_path.chmod(0o644)

        self.logger.info(f"Created firstboot service: {service_path}")
        return service_path

    def create_firstboot_script(self, config: Optional[FirstbootConfig] = None) -> Path:
        """
        Create enterprise-grade firstboot execution script.

        Args:
            config: Firstboot configuration

        Returns:
            Path to created script
        """
        if config is None:
            config = FirstbootConfig()

        script_path = self.chroot / self.LIBEXEC_DIR.relative_to("/") / "h2kvm-firstboot"
        script_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate enterprise-grade firstboot script
        script_content = generate_enterprise_firstboot_script(config)

        script_path.write_text(script_content)
        script_path.chmod(0o755)

        self.logger.info(f"Created enterprise firstboot script: {script_path}")
        return script_path

    def mark_for_firstboot(self) -> dict[str, Any]:
        """
        Mark image for firstboot initialization.

        This should be called during VM conversion to trigger
        firstboot on next boot.

        Returns:
            Results dictionary
        """
        results = {
            "conversion_flag_created": False,
            "machine_id_reset": False,
            "dbus_machine_id_removed": False,
            "errors": [],
        }

        try:
            # Create conversion flag
            flag_path = self.chroot / self.CONVERSION_FLAG.relative_to("/")
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.write_text("Converted by H2KVM\n")
            results["conversion_flag_created"] = True
            self.logger.info(f"Created conversion flag: {flag_path}")

        except Exception as e:
            results["errors"].append(f"conversion_flag: {e}")
            self.logger.exception(f"Failed to create conversion flag: {e}")

        try:
            # Reset machine-id to trigger ConditionFirstBoot=yes
            machine_id_path = self.chroot / self.MACHINE_ID.relative_to("/")
            if machine_id_path.exists():
                machine_id_path.write_text("")  # Truncate to 0 bytes
                results["machine_id_reset"] = True
                self.logger.info(f"Reset machine-id: {machine_id_path}")

        except Exception as e:
            results["errors"].append(f"machine_id: {e}")
            self.logger.exception(f"Failed to reset machine-id: {e}")

        try:
            # Remove dbus machine-id
            dbus_machine_id_path = self.chroot / self.DBUS_MACHINE_ID.relative_to("/")
            if dbus_machine_id_path.exists():
                dbus_machine_id_path.unlink()
                results["dbus_machine_id_removed"] = True
                self.logger.info(f"Removed dbus machine-id: {dbus_machine_id_path}")

        except Exception as e:
            results["errors"].append(f"dbus_machine_id: {e}")
            self.logger.exception(f"Failed to remove dbus machine-id: {e}")

        return results

    def install_firstboot_components(self, config: Optional[FirstbootConfig] = None) -> dict[str, Any]:
        """
        Install all firstboot components into image.

        Args:
            config: Firstboot configuration

        Returns:
            Installation results
        """
        results = {
            "generator_created": False,
            "service_created": False,
            "script_created": False,
            "marked_for_firstboot": False,
            "errors": [],
        }

        try:
            # Create generator
            self.create_generator()
            results["generator_created"] = True

        except Exception as e:
            results["errors"].append(f"generator: {e}")
            self.logger.exception(f"Failed to create generator: {e}")

        try:
            # Create service unit
            self.create_firstboot_service()
            results["service_created"] = True

        except Exception as e:
            results["errors"].append(f"service: {e}")
            self.logger.exception(f"Failed to create service: {e}")

        try:
            # Create firstboot script
            self.create_firstboot_script(config)
            results["script_created"] = True

        except Exception as e:
            results["errors"].append(f"script: {e}")
            self.logger.exception(f"Failed to create script: {e}")

        try:
            # Mark for firstboot
            mark_results = self.mark_for_firstboot()
            results["marked_for_firstboot"] = mark_results["conversion_flag_created"]
            results["mark_details"] = mark_results

        except Exception as e:
            results["errors"].append(f"mark_firstboot: {e}")
            self.logger.exception(f"Failed to mark for firstboot: {e}")

        return results

    def generate_report(self) -> dict[str, Any]:
        """
        Generate firstboot integration report.

        Returns:
            Report dictionary
        """
        report = {"components_installed": {}, "firstboot_marked": False, "expected_journal_output": []}

        # Check installed components
        generator_path = self.chroot / self.GENERATOR_DIR.relative_to("/") / "h2kvm-generator"
        service_path = self.chroot / self.SYSTEM_DIR.relative_to("/") / "h2kvm-firstboot.service"
        script_path = self.chroot / self.LIBEXEC_DIR.relative_to("/") / "h2kvm-firstboot"
        flag_path = self.chroot / self.CONVERSION_FLAG.relative_to("/")

        report["components_installed"]["generator"] = generator_path.exists()
        report["components_installed"]["service"] = service_path.exists()
        report["components_installed"]["script"] = script_path.exists()
        report["firstboot_marked"] = flag_path.exists()

        # Expected journal output
        if all(report["components_installed"].values()) and report["firstboot_marked"]:
            report["expected_journal_output"] = [
                "systemd[1]: Starting H2KVM First Boot Initialization...",
                "h2kvm-firstboot[NNN]: H2KVM First Boot Initialization Started",
                "h2kvm-firstboot[NNN]: Step 1/6: Generating new machine-id",
                "h2kvm-firstboot[NNN]: Step 2/6: Regenerating initramfs",
                "h2kvm-firstboot[NNN]: Step 3/6: Regenerating GRUB configuration",
                "h2kvm-firstboot[NNN]: Step 4/6: Activating LVM volumes",
                "h2kvm-firstboot[NNN]: Step 5/6: Settling udev",
                "h2kvm-firstboot[NNN]: Step 6/6: Reloading systemd daemon",
                "h2kvm-firstboot[NNN]: H2KVM First Boot Initialization Completed",
                "systemd[1]: Finished H2KVM First Boot Initialization",
            ]

        return report


def setup_firstboot_for_converted_image(
    chroot_path: str, config: Optional[FirstbootConfig] = None
) -> dict[str, Any]:
    """
    Convenience function to setup firstboot for converted image.

    Args:
        chroot_path: Path to chroot
        config: Firstboot configuration

    Returns:
        Results dictionary
    """
    firstboot = SystemdFirstboot(chroot_path)
    return firstboot.install_firstboot_components(config)
