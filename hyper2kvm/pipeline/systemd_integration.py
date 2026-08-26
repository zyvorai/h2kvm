# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd integration for migration pipeline.

This module integrates systemd tools into the hyper2kvm migration pipeline
for enhanced functionality and resource management.
"""

from __future__ import annotations

import logging
from pathlib import Path

from hyper2kvm.systemd import (
    SystemdCreds,
    SystemdCryptenroll,
    SystemdDetectVirt,
    SystemdDissect,
    SystemdRun,
)

logger = logging.getLogger(__name__)


class SystemdPipelineIntegration:
    """
    Systemd integration for migration pipeline.

    Provides systemd tool integration for:
    - Source platform detection
    - Disk image inspection
    - Secure credential management
    - LUKS encryption handling
    - Resource-limited task execution
    """

    def __init__(self):
        """Initialize systemd pipeline integration."""
        self.detect_virt = SystemdDetectVirt()
        self.dissect = SystemdDissect()
        self.creds = SystemdCreds()
        self.cryptenroll = SystemdCryptenroll()
        self.run = SystemdRun()

    def detect_source_platform(self) -> dict[str, str | bool]:
        """
        Detect source virtualization platform.

        Returns
        -------
        dict
            Platform detection results
        """
        logger.info("🔍 Detecting source platform using systemd-detect-virt")

        return {
            "is_virtualized": self.detect_virt.is_virtualized(),
            "is_vm": self.detect_virt.is_vm(),
            "is_container": self.detect_virt.is_container(),
            "virt_type": self.detect_virt.detect().value,
            "hypervisor": self.detect_virt.get_hypervisor_name(),
        }

    def inspect_disk_image(self, image_path: Path) -> dict:
        """
        Inspect disk image using systemd-dissect.

        Parameters
        ----------
        image_path : Path
            Path to disk image

        Returns
        -------
        dict
            Image inspection results
        """
        logger.info("🔍 Inspecting disk image: %s", image_path)

        # Validate image
        if not self.dissect.validate(image_path):
            logger.warning("⚠️  Image validation failed: %s", image_path)
            return {"valid": False}

        # Get detailed info
        info = self.dissect.inspect(image_path)

        return {
            "valid": True,
            "path": str(info.path),
            "format": info.format,
            "size": info.size,
            "partition_count": len(info.partitions),
            "os_release": info.os_release,
            "machine_id": info.machine_id,
            "hostname": info.hostname,
        }

    def encrypt_credential(self, name: str, value: str) -> Path:
        """
        Encrypt migration credential using systemd-creds.

        Parameters
        ----------
        name : str
            Credential name
        value : str
            Credential value to encrypt

        Returns
        -------
        Path
            Path to encrypted credential file
        """
        logger.info("🔐 Encrypting credential: %s", name)

        output_path = Path(f"/var/lib/hyper2kvm/credentials/{name}.cred")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.creds.encrypt(value, name, output=output_path)

        logger.info("✅ Credential encrypted: %s", output_path)
        return output_path

    def decrypt_credential(self, credential_path: Path) -> str:
        """
        Decrypt migration credential using systemd-creds.

        Parameters
        ----------
        credential_path : Path
            Path to encrypted credential

        Returns
        -------
        str
            Decrypted credential value
        """
        logger.info("🔓 Decrypting credential: %s", credential_path)

        return self.creds.decrypt(credential_path)

    def setup_luks_tpm2(self, device: Path, *, pcrs: str = "7+14") -> None:
        """
        Set up TPM2 auto-unlock for LUKS encrypted volumes.

        Parameters
        ----------
        device : Path
            LUKS device path
        pcrs : str, default="7+14"
            PCR banks to bind to
        """
        logger.info("🔐 Setting up TPM2 auto-unlock for: %s", device)

        self.cryptenroll.enroll_tpm2(device, tpm2_pcrs=pcrs)

        logger.info("✅ TPM2 enrolled for device: %s", device)

    def run_conversion_with_limits(
        self,
        input_path: Path,
        output_path: Path,
        *,
        memory_max: str = "4G",
        cpu_quota: str = "200%",
    ) -> None:
        """
        Run disk conversion with systemd resource limits.

        Parameters
        ----------
        input_path : Path
            Input disk image
        output_path : Path
            Output disk image
        memory_max : str, default="4G"
            Maximum memory usage
        cpu_quota : str, default="200%"
            CPU quota (200% = 2 cores)
        """
        logger.info("⚙️  Running conversion with systemd-run")
        logger.info("   Memory limit: %s", memory_max)
        logger.info("   CPU quota: %s", cpu_quota)

        result = self.run.run(
            ["qemu-img", "convert", "-p", "-O", "qcow2", str(input_path), str(output_path)],
            description=f"VM disk conversion: {input_path.name}",
            memory_max=memory_max,
            cpu_quota=cpu_quota,
            unit_name=f"hyper2kvm-convert-{input_path.stem}",
        )

        if result.returncode == 0:
            logger.info("✅ Conversion completed successfully")
        else:
            logger.error("❌ Conversion failed: %s", result.stderr)

    def extract_os_info(self, image_path: Path) -> dict | None:
        """
        Extract OS information from disk image.

        Parameters
        ----------
        image_path : Path
            Path to disk image

        Returns
        -------
        dict | None
            OS information or None if not found
        """
        logger.info("📄 Extracting OS info from: %s", image_path)

        try:
            # Use systemd-dissect --with to run cat /etc/os-release
            result = self.dissect.with_image(
                image_path,
                ["cat", "/etc/os-release"],
            )

            # Parse os-release
            os_info = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    os_info[key] = value.strip('"')

            logger.info("✅ OS detected: %s", os_info.get("NAME", "Unknown"))
            return os_info

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort OS detection, must not abort the pipeline
            logger.warning("⚠️  Could not extract OS info: %s", e)
            return None


# Example pipeline integration
def enhanced_migration_pipeline(
    source_image: Path,
    target_image: Path,
    *,
    vcenter_password: str | None = None,
):
    """
    Example migration pipeline with systemd integration.

    Parameters
    ----------
    source_image : Path
        Source disk image
    target_image : Path
        Target disk image path
    vcenter_password : str | None
        vCenter password (will be encrypted)
    """
    integration = SystemdPipelineIntegration()

    # Step 1: Detect source platform
    logger.info("Step 1: Detect source platform")
    platform_info = integration.detect_source_platform()
    logger.info("   Platform: %s", platform_info["hypervisor"])

    # Step 2: Inspect source disk
    logger.info("Step 2: Inspect source disk")
    disk_info = integration.inspect_disk_image(source_image)
    if not disk_info["valid"]:
        logger.error("❌ Invalid disk image")
        return

    logger.info("   Format: %s", disk_info["format"])
    logger.info("   Size: %s bytes", f"{disk_info['size']:,}")

    # Step 3: Encrypt credentials (if provided)
    if vcenter_password:
        logger.info("Step 3: Encrypt vCenter credentials")
        cred_path = integration.encrypt_credential(
            "vcenter-password",
            vcenter_password,
        )
        logger.info("   Credential stored: %s", cred_path)

    # Step 4: Extract OS information
    logger.info("Step 4: Extract OS information")
    os_info = integration.extract_os_info(source_image)
    if os_info:
        logger.info("   OS: %s", os_info.get("NAME", "Unknown"))
        logger.info("   Version: %s", os_info.get("VERSION", "Unknown"))

    # Step 5: Run conversion with resource limits
    logger.info("Step 5: Run disk conversion")
    integration.run_conversion_with_limits(
        source_image,
        target_image,
        memory_max="4G",
        cpu_quota="200%",
    )

    logger.info("✅ Migration pipeline complete!")
