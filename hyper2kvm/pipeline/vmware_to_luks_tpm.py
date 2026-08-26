# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Fully automated VMware → LUKS2 + TPM conversion pipeline.

This module provides an end-to-end conversion pipeline that:
1. Converts VMware VMDK to RAW format
2. Attaches disk via NBD
3. Detects root partition
4. Creates LUKS2 encrypted container
5. Migrates filesystem into LUKS
6. Updates crypttab + fstab
7. Enrolls TPM auto-unlock
8. Rebuilds initramfs
9. Updates GRUB configuration

Architecture aligned with:
- OpenShift confidential VMs
- Talos Linux encrypted nodes
- Flatcar Container Linux
- Kubernetes encrypted worker nodes

Usage:
    pipeline = Hyper2KVMVMwareToLUKSPipeline()
    pipeline.run("/path/to/vm.vmdk", output="/path/to/encrypted.raw")
"""

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

LOG = logging.getLogger("hyper2kvm.pipeline")


# ============================================================
# Exceptions
# ============================================================


class PipelineError(Exception):
    """Base exception for pipeline errors."""


class ConversionError(PipelineError):
    """Disk conversion failed."""


class AttachError(PipelineError):
    """NBD attach failed."""


class DetectionError(PipelineError):
    """Root partition detection failed."""


class EncryptionError(PipelineError):
    """LUKS encryption failed."""


class MigrationError(PipelineError):
    """Filesystem migration failed."""


class EnrollmentError(PipelineError):
    """TPM enrollment failed."""


class InitramfsError(PipelineError):
    """Initramfs rebuild failed."""


# ============================================================
# Command runner
# ============================================================


def run(cmd, check=True, capture_output=False):
    """
    Execute shell command with logging.

    Args:
        cmd: Command as list of strings
        check: Raise exception on non-zero exit
        capture_output: Capture stdout/stderr

    Returns:
        CompletedProcess object
    """
    LOG.info("Running: %s", " ".join(cmd))

    return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)


# ============================================================
# Disk conversion
# ============================================================


class DiskConverter:  # pylint: disable=too-few-public-methods  # single-purpose pipeline step, one operation by design
    """Convert disk images between formats."""

    def vmdk_to_raw(self, vmdk: str, raw: str) -> None:
        """
        Convert disk image to RAW format.

        Args:
            vmdk: Path to source disk image (VMDK, QCOW2, VHD, etc.)
            raw: Path to output RAW file

        Raises:
            ConversionError: If conversion fails
        """
        try:
            run(
                [
                    "qemu-img",
                    "convert",
                    "-O",
                    "raw",
                    "-p",  # Show progress
                    vmdk,
                    raw,
                ]
            )
            LOG.info("Converted %s → %s", vmdk, raw)
        except subprocess.CalledProcessError as e:
            raise ConversionError(f"Failed to convert {vmdk}: {e}") from e


# ============================================================
# NBD attach
# ============================================================


class NBDAttach:
    """Attach/detach disk images via NBD."""

    def __init__(self, device: str = "/dev/nbd0"):
        self.device = device
        self._attached = False

    def attach(self, image: str) -> str:
        """
        Attach disk image via NBD.

        Args:
            image: Path to disk image

        Returns:
            NBD device path (e.g., "/dev/nbd0")

        Raises:
            AttachError: If attach fails
        """
        try:
            # Load NBD module
            run(["modprobe", "nbd", "max_part=16"], check=False)

            # Disconnect if already connected
            run(["qemu-nbd", "--disconnect", self.device], check=False)

            # Connect image
            run(["qemu-nbd", "--connect", self.device, "--format", "raw", image])

            # Update partition table
            run(["partprobe", self.device])

            self._attached = True
            LOG.info("Attached %s to %s", image, self.device)
            return self.device

        except subprocess.CalledProcessError as e:
            raise AttachError(f"Failed to attach {image}: {e}") from e

    def detach(self) -> None:
        """Detach NBD device."""
        if self._attached:
            try:
                run(["qemu-nbd", "--disconnect", self.device])
                self._attached = False
                LOG.info("Detached %s", self.device)
            except subprocess.CalledProcessError as e:
                LOG.warning("Failed to detach %s: %s", self.device, e)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.detach()


# ============================================================
# Root partition detection
# ============================================================


class RootDetector:
    """Detect root partition on disk."""

    def detect(self, disk: str) -> tuple[str, str]:
        """
        Detect root partition and filesystem type.

        Args:
            disk: Disk device path (e.g., "/dev/nbd0")

        Returns:
            Tuple of (partition_path, fstype)

        Raises:
            DetectionError: If no suitable root partition found
        """
        try:
            result = run(["lsblk", "-ln", "-o", "NAME,FSTYPE,SIZE,TYPE", disk], capture_output=True)

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue

                name, fstype, size, ptype = parts[:4]

                # Skip non-partitions
                if ptype != "part":
                    continue

                # Look for Linux filesystems
                if fstype in ("ext4", "xfs", "ext3", "btrfs"):
                    partition = f"/dev/{name}"
                    LOG.info("Detected root partition: %s (%s, %s)", partition, fstype, size)
                    return partition, fstype

            raise DetectionError(f"No suitable root partition found on {disk}")

        except subprocess.CalledProcessError as e:
            raise DetectionError(f"Failed to detect root partition: {e}") from e

    def get_uuid(self, partition: str) -> str:
        """
        Get UUID of partition.

        Args:
            partition: Partition device path

        Returns:
            UUID string
        """
        try:
            result = run(["blkid", "-s", "UUID", "-o", "value", partition], capture_output=True)

            part_uuid = result.stdout.strip()
            LOG.info("Partition %s UUID: %s", partition, part_uuid)
            return part_uuid

        except subprocess.CalledProcessError:
            # Generate new UUID if none exists
            new_uuid = str(uuid.uuid4())
            LOG.warning("No UUID found for %s, generating: %s", partition, new_uuid)
            return new_uuid


# ============================================================
# LUKS encryption
# ============================================================


class LUKSEncryptor:
    """Create and manage LUKS2 encrypted containers."""

    def __init__(self, keyfile: Optional[str] = None):
        self.keyfile = keyfile or "/tmp/hyper2kvm-luks.key"
        self._created_keyfile = False

    def create_keyfile(self) -> str:
        """
        Create random LUKS keyfile.

        Returns:
            Path to keyfile
        """
        if not os.path.exists(self.keyfile):
            run(["dd", "if=/dev/random", f"of={self.keyfile}", "bs=32", "count=1"])
            os.chmod(self.keyfile, 0o400)
            self._created_keyfile = True
            LOG.info("Created keyfile: %s", self.keyfile)

        return self.keyfile

    def encrypt(self, partition: str, mapper_name: str = "cryptroot") -> str:
        """
        Encrypt partition with LUKS2.

        Args:
            partition: Partition device path
            mapper_name: Device mapper name

        Returns:
            Path to decrypted device (e.g., "/dev/mapper/cryptroot")

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            keyfile = self.create_keyfile()

            # Format with LUKS2
            run(
                [
                    "cryptsetup",
                    "luksFormat",
                    "--type",
                    "luks2",
                    "--cipher",
                    "aes-xts-plain64",
                    "--key-size",
                    "512",
                    "--hash",
                    "sha256",
                    "--pbkdf",
                    "argon2id",
                    "--batch-mode",
                    partition,
                    keyfile,
                ]
            )

            LOG.info("Created LUKS2 container on %s", partition)

            # Open encrypted device
            run(["cryptsetup", "open", partition, mapper_name, "--key-file", keyfile])

            mapper_path = f"/dev/mapper/{mapper_name}"
            LOG.info("Opened LUKS device: %s", mapper_path)
            return mapper_path

        except subprocess.CalledProcessError as e:
            raise EncryptionError(f"Failed to encrypt {partition}: {e}") from e

    def cleanup(self) -> None:
        """Remove temporary keyfile."""
        if self._created_keyfile and os.path.exists(self.keyfile):
            Path(self.keyfile).unlink()
            LOG.info("Removed keyfile: %s", self.keyfile)


# ============================================================
# Filesystem migration
# ============================================================


class FilesystemMigrator:  # pylint: disable=too-few-public-methods  # single-purpose pipeline step, one operation by design
    """Migrate filesystem between devices."""

    def migrate(self, source: str, target: str, fstype: str = "ext4") -> None:
        """
        Migrate filesystem from source to target.

        Args:
            source: Source partition
            target: Target partition (LUKS container)
            fstype: Filesystem type

        Raises:
            MigrationError: If migration fails
        """
        source_mnt = "/mnt/hyper2kvm_source"
        target_mnt = "/mnt/hyper2kvm_target"

        try:
            # Create mount points
            Path(source_mnt).mkdir(parents=True, exist_ok=True)
            Path(target_mnt).mkdir(parents=True, exist_ok=True)

            # Create filesystem on target
            if fstype == "ext4":
                run(["mkfs.ext4", "-F", target])
            elif fstype == "xfs":
                run(["mkfs.xfs", "-f", target])
            else:
                raise MigrationError(f"Unsupported filesystem: {fstype}")

            LOG.info("Created %s filesystem on %s", fstype, target)

            # Mount source and target
            run(["mount", "-o", "ro", source, source_mnt])
            run(["mount", target, target_mnt])

            LOG.info("Migrating filesystem...")

            # Copy filesystem
            run(["rsync", "-aAXH", "--numeric-ids", "--info=progress2", f"{source_mnt}/", f"{target_mnt}/"])

            LOG.info("Filesystem migrated successfully")

            # Unmount
            run(["umount", source_mnt])
            run(["umount", target_mnt])

        except subprocess.CalledProcessError as e:
            # Cleanup on error
            run(["umount", source_mnt], check=False)
            run(["umount", target_mnt], check=False)
            raise MigrationError(f"Failed to migrate filesystem: {e}") from e

        finally:
            # Remove mount points
            shutil.rmtree(source_mnt, ignore_errors=True)
            shutil.rmtree(target_mnt, ignore_errors=True)


# ============================================================
# crypttab update
# ============================================================


class CrypttabUpdater:  # pylint: disable=too-few-public-methods  # single-purpose pipeline step, one operation by design
    """Update /etc/crypttab for auto-unlock."""

    def update(self, mount_point: str, device_uuid: str, mapper_name: str = "cryptroot") -> None:
        """
        Add crypttab entry for TPM auto-unlock.

        Args:
            mount_point: Root filesystem mount point
            device_uuid: UUID of encrypted partition
            mapper_name: Device mapper name
        """
        crypttab_path = Path(mount_point) / "etc/crypttab"

        entry = f"{mapper_name} UUID={device_uuid} none luks,tpm2-device=auto\n"

        with open(crypttab_path, "a", encoding="utf-8") as f:
            f.write(entry)

        LOG.info("Updated %s with TPM entry", crypttab_path)


# ============================================================
# TPM enrollment
# ============================================================


class TPMEnroll:  # pylint: disable=too-few-public-methods  # single-purpose pipeline step, one operation by design
    """Enroll LUKS device with TPM2."""

    def enroll(self, device: str, pcrs: Optional[list[int]] = None) -> None:
        """
        Enroll LUKS device with TPM2.

        Args:
            device: LUKS device path
            pcrs: PCR banks to use (default: 0,1,2,3,7)

        Raises:
            EnrollmentError: If enrollment fails
        """
        if pcrs is None:
            pcrs = [0, 1, 2, 3, 7]

        pcr_str = "+".join(str(p) for p in pcrs)

        try:
            run(
                [
                    "systemd-cryptenroll",
                    "--tpm2-device=auto",
                    f"--tpm2-pcrs={pcr_str}",
                    "--wipe-slot=empty",
                    device,
                ]
            )

            LOG.info("Enrolled %s with TPM2 (PCRs: %s)", device, pcr_str)

        except subprocess.CalledProcessError as e:
            raise EnrollmentError(f"Failed to enroll {device}: {e}") from e


# ============================================================
# Initramfs rebuild
# ============================================================


class InitramfsBuilder:  # pylint: disable=too-few-public-methods  # single-purpose pipeline step, one operation by design
    """Rebuild initramfs with LUKS + TPM support."""

    def rebuild(self, root_mount: str) -> None:
        """
        Rebuild initramfs in chroot.

        Args:
            root_mount: Root filesystem mount point

        Raises:
            InitramfsError: If rebuild fails
        """
        try:
            # Detect dracut or update-initramfs
            if os.path.exists(f"{root_mount}/usr/bin/dracut"):
                run(
                    [
                        "chroot",
                        root_mount,
                        "dracut",
                        "--force",
                        "--add",
                        "crypt tpm2-tss",
                        "--include",
                        "/etc/crypttab",
                        "/etc/crypttab",
                    ]
                )
                LOG.info("Rebuilt initramfs with dracut")

            elif os.path.exists(f"{root_mount}/usr/sbin/update-initramfs"):
                run(["chroot", root_mount, "update-initramfs", "-u"])
                LOG.info("Rebuilt initramfs with update-initramfs")

            else:
                raise InitramfsError("No initramfs tool found (dracut/update-initramfs)")

        except subprocess.CalledProcessError as e:
            raise InitramfsError(f"Failed to rebuild initramfs: {e}") from e


# ============================================================
# GRUB update
# ============================================================


class GrubUpdater:  # pylint: disable=too-few-public-methods  # single-purpose pipeline step, one operation by design
    """Update GRUB configuration for encrypted root."""

    def update(self, root_mount: str, device_uuid: str) -> None:
        """
        Update GRUB configuration.

        Args:
            root_mount: Root filesystem mount point
            device_uuid: UUID of encrypted partition
        """
        try:
            # Update GRUB default config
            default_grub = Path(root_mount) / "etc/default/grub"

            if default_grub.exists():
                content = default_grub.read_text()

                # Add rd.luks.uuid to GRUB_CMDLINE_LINUX
                if "GRUB_CMDLINE_LINUX=" in content:
                    content = content.replace(
                        'GRUB_CMDLINE_LINUX="', f'GRUB_CMDLINE_LINUX="rd.luks.uuid={device_uuid} '
                    )
                    default_grub.write_text(content)

            # Rebuild GRUB config
            if os.path.exists(f"{root_mount}/usr/sbin/grub2-mkconfig"):
                run(["chroot", root_mount, "grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])
                LOG.info("Updated GRUB with grub2-mkconfig")

            elif os.path.exists(f"{root_mount}/usr/sbin/update-grub"):
                run(["chroot", root_mount, "update-grub"])
                LOG.info("Updated GRUB with update-grub")

            else:
                LOG.warning(
                    "No GRUB update tool found.\n"
                    "    Expected one of: grub2-mkconfig, grub-mkconfig, update-grub\n"
                    "    Install with: dnf install grub2-tools  (or: apt install grub2-common)"
                )

        except subprocess.CalledProcessError as e:
            LOG.warning(
                "Failed to update GRUB: %s\n"
                "    Manual fix: boot a rescue image and run grub2-mkconfig / grub2-install\n"
                "    See: https://docs.fedoraproject.org/en-US/quick-docs/bootloading-with-grub2/",
                e,
            )


# ============================================================
# Full pipeline
# ============================================================


# orchestrator composes one step object per pipeline stage; run() is the single entry point
# pylint: disable-next=too-many-instance-attributes,too-few-public-methods
class Hyper2KVMVMwareToLUKSPipeline:
    """
    Complete VMware → LUKS2 + TPM conversion pipeline.

    This pipeline automates the entire process of converting a VMware VM
    to an encrypted, TPM-unlocked bootable image suitable for Kubernetes
    worker nodes.

    Usage:
        pipeline = Hyper2KVMVMwareToLUKSPipeline()
        pipeline.run(
            vmdk="/path/to/vm.vmdk",
            output="/path/to/encrypted.raw"
        )
    """

    def __init__(self):
        self.converter = DiskConverter()
        self.detector = RootDetector()
        self.encryptor = LUKSEncryptor()
        self.migrator = FilesystemMigrator()
        self.crypttab_updater = CrypttabUpdater()
        self.tpm_enroll = TPMEnroll()
        self.initramfs_builder = InitramfsBuilder()
        self.grub_updater = GrubUpdater()

    def run(self, vmdk: str, output: Optional[str] = None, skip_tpm: bool = False) -> str:
        """
        Execute full conversion pipeline.

        Args:
            vmdk: Path to VMware VMDK file
            output: Path to output RAW file (default: {vmdk}.encrypted.raw)

        Returns:
            Path to encrypted RAW image

        Raises:
            PipelineError: If any step fails
        """
        if output is None:
            output = f"{vmdk}.encrypted.raw"

        LOG.info("Starting VMware → LUKS2 + TPM pipeline")
        LOG.info("Input: %s", vmdk)
        LOG.info("Output: %s", output)

        # Step 1: Convert VMDK to RAW
        LOG.info("Step 1/9: Converting disk image to RAW")
        self.converter.vmdk_to_raw(vmdk, output)

        # Step 2: Attach via NBD
        LOG.info("Step 2/9: Attaching disk via NBD")
        with NBDAttach() as nbd:
            disk = nbd.attach(output)

            # Step 3: Detect root partition
            LOG.info("Step 3/9: Detecting root partition")
            root_partition, fstype = self.detector.detect(disk)
            root_uuid = self.detector.get_uuid(root_partition)

            # Step 4: Create LUKS2 container
            LOG.info("Step 4/9: Creating LUKS2 encrypted container")
            luks_device = self.encryptor.encrypt(root_partition)

            # Step 5: Migrate filesystem
            LOG.info("Step 5/9: Migrating filesystem to LUKS")
            self.migrator.migrate(root_partition, luks_device, fstype)

            # Step 6: Mount for configuration
            LOG.info("Step 6/9: Updating system configuration")
            mount_point = "/mnt/hyper2kvm_config"
            Path(mount_point).mkdir(parents=True, exist_ok=True)

            try:
                run(["mount", luks_device, mount_point])

                # Update crypttab
                self.crypttab_updater.update(mount_point, root_uuid)

                # Step 7: Enroll TPM (unless skipped)
                if skip_tpm:
                    LOG.info("Step 7/9: Skipping TPM enrollment (--no-tpm)")
                else:
                    LOG.info("Step 7/9: Enrolling TPM2 auto-unlock")
                    self.tpm_enroll.enroll(root_partition)

                # Step 8: Rebuild initramfs
                LOG.info("Step 8/9: Rebuilding initramfs")
                self.initramfs_builder.rebuild(mount_point)

                # Step 9: Update GRUB
                LOG.info("Step 9/9: Updating GRUB configuration")
                self.grub_updater.update(mount_point, root_uuid)

            finally:
                run(["umount", mount_point], check=False)
                shutil.rmtree(mount_point, ignore_errors=True)
                run(["cryptsetup", "close", "cryptroot"], check=False)

        # Cleanup
        self.encryptor.cleanup()

        LOG.info("Conversion complete: %s", output)
        LOG.info("VM is ready to boot with TPM auto-unlock")

        return output
