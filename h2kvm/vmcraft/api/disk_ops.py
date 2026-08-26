# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Disk Operations.

Provides partition management, block device, and archive operations
for VMCraft via composition. Merges PartitionMixin + BlockdevMixin + ArchiveMixin.
"""

from __future__ import annotations

from h2kvm.vmcraft._utils import run_sudo
from h2kvm.vmcraft.services import (
    archive_dd_copy as svc_archive_dd_copy,
    archive_tar_in as svc_archive_tar_in,
    archive_tar_out as svc_archive_tar_out,
    blockdev_getsize64 as svc_blockdev_getsize64,
    blockdev_getsz as svc_blockdev_getsz,
    partition_add as svc_partition_add,
    partition_del as svc_partition_del,
    partition_disk as svc_partition_disk,
    partition_get_parttype as svc_partition_get_parttype,
    partition_init as svc_partition_init,
    partition_set_gpt_type as svc_partition_set_gpt_type,
    partition_set_name as svc_partition_set_name,
)


class DiskOps:
    """Disk operations (partitions, block devices, archives) via composition."""

    def __init__(self, host) -> None:
        self._host = host

    # === Partition Management (from PartitionMixin) ===

    def part_init(self, device: str, parttype: str) -> None:
        """
        Initialize empty partition table on device.

        Args:
            device: Device path (e.g., /dev/nbd0)
            parttype: Partition table type ("gpt", "msdos", or "mbr")

        Raises:
            RuntimeError: If initialization fails

        Example:
            g.part_init("/dev/nbd0", "gpt")
        """
        self._host._require_nbd_device()  # pylint: disable=protected-access  # DiskOps is a composed mixin of host; accessing host internals is by design

        svc_partition_init(
            self._host.logger,
            run_sudo,
            device,
            parttype,
            self._host.invalidate_partition_cache,
            self._host.blockdev_rereadpt,
        )

    def part_add(self, device: str, prlogex: str, startsect: int, endsect: int) -> None:
        """
        Add partition to device.

        Args:
            device: Device path (e.g., /dev/nbd0)
            prlogex: Partition type ("primary", "logical", "extended")
            startsect: Start sector
            endsect: End sector (-1 for end of disk)

        Raises:
            RuntimeError: If partition creation fails

        Example:
            # Create primary partition from 1MiB to 100%
            g.part_add("/dev/nbd0", "primary", 2048, -1)
        """
        self._host._require_nbd_device()  # pylint: disable=protected-access  # DiskOps is a composed mixin of host; accessing host internals is by design

        svc_partition_add(
            self._host.logger,
            run_sudo,
            device,
            prlogex,
            startsect,
            endsect,
            self._host.invalidate_partition_cache,
            self._host.blockdev_rereadpt,
        )

    def part_del(self, device: str, partnum: int) -> None:
        """
        Delete partition from device.

        Args:
            device: Device path (e.g., /dev/nbd0)
            partnum: Partition number to delete (1-based)

        Raises:
            RuntimeError: If deletion fails

        Example:
            g.part_del("/dev/nbd0", 1)
        """
        self._host._require_nbd_device()  # pylint: disable=protected-access  # DiskOps is a composed mixin of host; accessing host internals is by design

        svc_partition_del(
            self._host.logger,
            run_sudo,
            device,
            partnum,
            self._host.invalidate_partition_cache,
            self._host.blockdev_rereadpt,
        )

    def part_disk(self, device: str, parttype: str) -> None:
        """
        Initialize partition table and create single partition covering entire disk.

        Args:
            device: Device path
            parttype: Partition table type ("gpt", "msdos", or "mbr")

        Raises:
            RuntimeError: If operation fails

        Example:
            g.part_disk("/dev/nbd0", "gpt")
        """
        self._host._require_nbd_device()  # pylint: disable=protected-access  # DiskOps is a composed mixin of host; accessing host internals is by design

        svc_partition_disk(
            self._host.logger,
            run_sudo,
            device,
            parttype,
            self._host.invalidate_partition_cache,
            self._host.blockdev_rereadpt,
        )

    def part_set_name(self, device: str, partnum: int, name: str) -> None:
        """
        Set GPT partition name.

        Args:
            device: Device path
            partnum: Partition number
            name: Partition name

        Raises:
            RuntimeError: If operation fails (only works with GPT)

        Example:
            g.part_set_name("/dev/nbd0", 1, "EFI System")
        """
        self._host._require_nbd_device()  # pylint: disable=protected-access  # DiskOps is a composed mixin of host; accessing host internals is by design

        svc_partition_set_name(self._host.logger, run_sudo, device, partnum, name)

    def part_set_gpt_type(self, device: str, partnum: int, guid: str) -> None:
        """
        Set GPT partition type GUID.

        Args:
            device: Device path
            partnum: Partition number
            guid: Partition type GUID

        Raises:
            RuntimeError: If operation fails (requires sgdisk)

        Common GUIDs:
            - EFI System: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
            - Linux filesystem: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
            - Linux swap: 0657FD6D-A4AB-43C4-84E5-0933C84B4F4F
            - Linux LVM: E6D6D379-F507-44C2-A23C-238F2A3DF928

        Example:
            g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")
        """
        self._host._require_nbd_device()  # pylint: disable=protected-access  # DiskOps is a composed mixin of host; accessing host internals is by design

        svc_partition_set_gpt_type(self._host.logger, run_sudo, device, partnum, guid)

    def part_get_parttype(self, device: str) -> str:
        """
        Get partition table type.

        Args:
            device: Device path

        Returns:
            Partition table type ("gpt", "msdos", or "unknown")

        Example:
            parttype = g.part_get_parttype("/dev/nbd0")
            # Returns "gpt" or "msdos"
        """
        return svc_partition_get_parttype(self._host.logger, run_sudo, device)

    # === Block Device Operations (from BlockdevMixin) ===

    def blockdev_getsize64(self, device: str) -> int:
        """
        Get device size in bytes.

        Args:
            device: Device path (e.g., /dev/sda, /dev/nbd0p1)

        Returns:
            Size in bytes (0 if device doesn't exist or command fails)

        Example:
            size = g.blockdev_getsize64("/dev/nbd0")
            print(f"Disk size: {size} bytes ({size // (1024**3)} GB)")
        """
        # pylint: disable-next=protected-access  # DiskOps is a composed mixin; host internals by design
        return self._host._sudo_service_call(svc_blockdev_getsize64, device)

    def blockdev_getsz(self, device: str) -> int:
        """
        Get device size in 512-byte sectors.

        Args:
            device: Device path

        Returns:
            Size in 512-byte sectors (0 if device doesn't exist or command fails)

        Example:
            sectors = g.blockdev_getsz("/dev/nbd0")
            print(f"Disk size: {sectors} sectors")
        """
        # pylint: disable-next=protected-access  # DiskOps is a composed mixin; host internals by design
        return self._host._sudo_service_call(svc_blockdev_getsz, device)

    def dd_copy(self, src: str, dest: str, count: int | None = None, blocksize: int = 512) -> None:
        """
        Copy data using dd command.

        Args:
            src: Source file or device
            dest: Destination file or device
            count: Number of blocks to copy (None for all)
            blocksize: Block size in bytes (default: 512)

        Raises:
            RuntimeError: If dd command fails

        Example:
            # Copy first 1MB of disk
            g.dd_copy("/dev/nbd0", "/tmp/mbr-backup.bin", count=2048, blocksize=512)

            # Clone entire partition
            g.dd_copy("/dev/nbd0p1", "/dev/nbd1p1")
        """
        self._host._sudo_service_call(  # pylint: disable=protected-access  # composed mixin, host internals by design
            svc_archive_dd_copy,
            src=src,
            dest=dest,
            count=count,
            blocksize=blocksize,
        )

    # === Archive Operations (from ArchiveMixin) ===

    def tar_in(self, tarfile: str, directory: str, compress: str | None = None) -> None:
        """
        Unpack tarball into guest directory.

        Args:
            tarfile: Path to tar archive on host
            directory: Target directory in guest (absolute path)
            compress: Compression type ("gzip", "bzip2", "xz", or None)

        Raises:
            RuntimeError: If not launched or extraction fails

        Example:
            # Extract archive to /opt in guest
            g.tar_in("/tmp/myapp.tar.gz", "/opt", compress="gzip")
        """
        self._host._sudo_mount_service_call(  # pylint: disable=protected-access  # composed mixin, host internals by design
            svc_archive_tar_in,
            tarfile=tarfile,
            directory=directory,
            compress=compress,
        )

    def tar_out(self, directory: str, tarfile: str, compress: str | None = None) -> None:
        """
        Pack guest directory into tarball.

        Args:
            directory: Source directory in guest (absolute path)
            tarfile: Output tar file on host
            compress: Compression type ("gzip", "bzip2", "xz", or None)

        Raises:
            RuntimeError: If not launched, directory doesn't exist, or creation fails

        Example:
            # Pack /etc to tarball
            g.tar_out("/etc", "/tmp/etc-backup.tar.gz", compress="gzip")
        """
        self._host._sudo_mount_service_call(  # pylint: disable=protected-access  # composed mixin, host internals by design
            svc_archive_tar_out,
            directory=directory,
            tarfile=tarfile,
            compress=compress,
        )

    def tgz_in(self, tarball: str, directory: str) -> None:
        """
        Unpack gzipped tarball (convenience wrapper for tar_in).

        Args:
            tarball: Path to .tar.gz archive on host
            directory: Target directory in guest

        Example:
            g.tgz_in("/tmp/app.tar.gz", "/opt")
        """
        self.tar_in(tarball, directory, compress="gzip")

    def tgz_out(self, directory: str, tarball: str) -> None:
        """
        Pack directory to gzipped tarball (convenience wrapper for tar_out).

        Args:
            directory: Source directory in guest
            tarball: Output .tar.gz file on host

        Example:
            g.tgz_out("/var/log", "/tmp/logs.tar.gz")
        """
        self.tar_out(directory, tarball, compress="gzip")
