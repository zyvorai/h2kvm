# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-dissect integration for disk image inspection.

This module wraps systemd-dissect to provide disk image inspection,
mounting, and file extraction capabilities.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from h2kvm.systemd._common import check_systemd_binary_available


@dataclass
class PartitionInfo:  # pylint: disable=too-many-instance-attributes
    # reason: models the full set of independent partition-table fields reported
    # by systemd-dissect for one partition.
    """Information about a partition in a disk image."""

    number: int
    start: int
    end: int
    size: int
    type: str
    name: str | None = None
    uuid: str | None = None
    mountpoint: str | None = None


@dataclass
class ImageInfo:
    """Information about a disk image."""

    path: Path
    format: str
    size: int
    partitions: list[PartitionInfo]
    os_release: dict[str, str] | None = None
    machine_id: str | None = None
    hostname: str | None = None


class SystemdDissect:
    """
    Wrapper for systemd-dissect command-line tool.

    Provides disk image inspection, mounting, and file extraction using
    systemd's Discoverable Disk Image (DDI) functionality.
    """

    def __init__(self, systemd_dissect: str = "systemd-dissect"):
        """
        Initialize systemd-dissect wrapper.

        Parameters
        ----------
        systemd_dissect : str, default="systemd-dissect"
            Path to systemd-dissect binary
        """
        self.binary = systemd_dissect
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-dissect is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-dissect",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def inspect(self, image: Path) -> ImageInfo:
        """
        Inspect disk image and return detailed information.

        Parameters
        ----------
        image : Path
            Path to disk image file

        Returns
        -------
        ImageInfo
            Detailed image information

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> info = dissect.inspect(Path("/path/to/disk.img"))
        >>> print(info.partitions)
        """
        result = subprocess.run(
            [self.binary, "--json=short", str(image)],
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)

        # Parse partition information
        partitions = []
        for idx, part in enumerate(data.get("partitions", [])):
            partitions.append(
                PartitionInfo(
                    number=idx + 1,
                    start=part.get("offset", 0),
                    end=part.get("offset", 0) + part.get("size", 0),
                    size=part.get("size", 0),
                    type=part.get("type", "unknown"),
                    name=part.get("label"),
                    uuid=part.get("uuid"),
                )
            )

        # Parse OS information if available
        os_release = data.get("osRelease")

        return ImageInfo(
            path=image,
            format=data.get("imageType", "unknown"),
            size=data.get("imageSize", 0),
            partitions=partitions,
            os_release=os_release,
            machine_id=data.get("machineId"),
            hostname=data.get("hostname"),
        )

    def mount(
        self,
        image: Path,
        mountpoint: Path,
        *,
        read_only: bool = True,
        mkdir: bool = True,
    ) -> None:
        """
        Mount disk image at specified mountpoint.

        Parameters
        ----------
        image : Path
            Path to disk image file
        mountpoint : Path
            Directory to mount image at
        read_only : bool, default=True
            Mount in read-only mode
        mkdir : bool, default=True
            Create mountpoint directory if it doesn't exist

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> dissect.mount(Path("disk.img"), Path("/mnt/disk"))
        """
        cmd = [self.binary, "--mount", str(image), str(mountpoint)]

        if read_only:
            cmd.append("--read-only")
        if mkdir:
            cmd.append("--mkdir")

        subprocess.run(cmd, check=True)

    def umount(self, mountpoint: Path, *, rmdir: bool = True) -> None:
        """
        Unmount disk image from mountpoint.

        Parameters
        ----------
        mountpoint : Path
            Directory where image is mounted
        rmdir : bool, default=True
            Remove mountpoint directory after unmounting

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> dissect.umount(Path("/mnt/disk"))
        """
        cmd = [self.binary, "--umount", str(mountpoint)]

        if rmdir:
            cmd.append("--rmdir")

        subprocess.run(cmd, check=True)

    def list_partitions(self, image: Path) -> list[PartitionInfo]:
        """
        List all partitions in disk image.

        Parameters
        ----------
        image : Path
            Path to disk image file

        Returns
        -------
        list[PartitionInfo]
            List of partition information

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> partitions = dissect.list_partitions(Path("disk.img"))
        >>> for part in partitions:
        ...     print(f"{part.number}: {part.type} ({part.size} bytes)")
        """
        # Parse output and return partition info
        # For now, delegate to inspect() which has JSON output
        info = self.inspect(image)
        return info.partitions

    def copy_from(
        self,
        image: Path,
        source_path: str,
        target_path: Path | None = None,
    ) -> Path:
        """
        Copy file from disk image to host.

        Parameters
        ----------
        image : Path
            Path to disk image file
        source_path : str
            Path to file inside image
        target_path : Path | None
            Destination path on host (default: current directory)

        Returns
        -------
        Path
            Path to extracted file

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> file = dissect.copy_from(Path("disk.img"), "/etc/hostname", Path("/tmp/hostname"))
        """
        cmd = [self.binary, "--copy-from", str(image), source_path]

        if target_path:
            cmd.append(str(target_path))

        subprocess.run(cmd, check=True)

        return target_path or Path(Path(source_path).name)

    def copy_to(
        self,
        image: Path,
        source_path: Path,
        target_path: str,
    ) -> None:
        """
        Copy file from host to disk image.

        Parameters
        ----------
        image : Path
            Path to disk image file
        source_path : Path
            Path to file on host
        target_path : str
            Destination path inside image

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> dissect.copy_to(Path("disk.img"), Path("/tmp/config"), "/etc/myconfig")
        """
        cmd = [
            self.binary,
            "--copy-to",
            str(image),
            str(source_path),
            target_path,
        ]

        subprocess.run(cmd, check=True)

    def validate(self, image: Path) -> bool:
        """
        Validate disk image structure.

        Parameters
        ----------
        image : Path
            Path to disk image file

        Returns
        -------
        bool
            True if valid, False otherwise

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> if dissect.validate(Path("disk.img")):
        ...     print("Image is valid")
        """
        try:
            subprocess.run(
                [self.binary, "--validate", str(image)],
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def with_image(
        self,
        image: Path,
        command: list[str],
    ) -> subprocess.CompletedProcess:
        """
        Execute command with image mounted.

        Mounts the image, runs command, then unmounts automatically.

        Parameters
        ----------
        image : Path
            Path to disk image file
        command : list[str]
            Command and arguments to run

        Returns
        -------
        subprocess.CompletedProcess
            Result of command execution

        Examples
        --------
        >>> dissect = SystemdDissect()
        >>> result = dissect.with_image(Path("disk.img"), ["cat", "/etc/os-release"])
        >>> print(result.stdout)
        """
        cmd = [self.binary, "--with", str(image), "--", *command]

        return subprocess.run(cmd, capture_output=True, text=True, check=True)
