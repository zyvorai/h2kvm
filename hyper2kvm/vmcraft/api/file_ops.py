# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
File Operations.

Provides file system manipulation methods for VMCraft via composition.
All methods delegate to the FileOperations manager.
"""

from __future__ import annotations

from typing import Any

from hyper2kvm.vmcraft._utils import run_sudo
from hyper2kvm.vmcraft.services import (
    blkid_lookup as svc_blkid_lookup,
    call_file_ops,
)


class FileOps:  # pylint: disable=too-many-public-methods
    """File operations via composition."""

    # too-many-public-methods: thin 1:1 wrapper surface over many file
    # operations, same pattern as systemd_ops.py.
    #
    # pylint: disable=protected-access
    # Deliberate composition-pattern coupling: this Ops class reaches into the
    # host client's internal dispatch/cache attributes, same pattern used
    # throughout hyper2kvm/vmcraft/api/*.py within the same package.

    def __init__(self, host) -> None:
        self._host = host

    def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        return call_file_ops(self._host._file_ops, "is_file", path)

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        return call_file_ops(self._host._file_ops, "is_dir", path)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return call_file_ops(self._host._file_ops, "exists", path)

    def stat(self, path: str) -> dict[str, int]:
        """Get file stat information (guestfs-compatible format)."""
        return call_file_ops(self._host._file_ops, "stat", path)

    def read_file(self, path: str) -> bytes:
        """Read file contents as bytes."""
        return call_file_ops(self._host._file_ops, "read_file", path)

    def cat(self, path: str) -> str:
        """Read file contents as string."""
        return call_file_ops(self._host._file_ops, "cat", path)

    def write(self, path: str, content: bytes | str) -> None:
        """Write content to file."""
        call_file_ops(self._host._file_ops, "write", path, content)

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file from host to guest filesystem."""
        call_file_ops(self._host._file_ops, "upload", local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file from guest to host filesystem."""
        call_file_ops(self._host._file_ops, "download", remote_path, local_path)

    def ls(self, path: str) -> list[str]:
        """List directory contents."""
        return call_file_ops(self._host._file_ops, "ls", path)

    def find(self, path: str) -> list[str]:
        """Recursively find all files under path."""
        return call_file_ops(self._host._file_ops, "find", path)

    def mkdir_p(self, path: str) -> None:
        """Create directory (with parents)."""
        call_file_ops(self._host._file_ops, "mkdir_p", path)

    def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        call_file_ops(self._host._file_ops, "chmod", path, mode)

    def ln_sf(self, target: str, link_name: str) -> None:
        """Create symbolic link."""
        call_file_ops(self._host._file_ops, "ln_sf", target, link_name)

    def cp(self, src: str, dst: str) -> None:
        """Copy file."""
        call_file_ops(self._host._file_ops, "cp", src, dst)

    def rm_f(self, path: str) -> None:
        """Remove file (force)."""
        call_file_ops(self._host._file_ops, "rm_f", path)

    def touch(self, path: str) -> None:
        """Create empty file or update timestamp."""
        call_file_ops(self._host._file_ops, "touch", path)

    def readlink(self, path: str) -> str:
        """Read symbolic link target."""
        return call_file_ops(self._host._file_ops, "readlink", path)

    def find_files(self, path: str, pattern: str | None = None, file_type: str | None = None) -> list[str]:
        """Find files in guest filesystem."""
        return call_file_ops(self._host._file_ops, "find_files", path, pattern, file_type)

    def checksum(self, path: str, algorithm: str = "sha256") -> str:
        """Calculate checksum of file."""
        return call_file_ops(self._host._file_ops, "checksum", path, algorithm)

    def file_age(self, path: str) -> dict[str, Any]:
        """Get file timestamps."""
        return call_file_ops(self._host._file_ops, "file_age", path)

    def set_permissions(self, path: str, mode: int, recursive: bool = False) -> None:
        """Set file/directory permissions."""
        call_file_ops(self._host._file_ops, "set_permissions", path, mode, recursive)

    def set_owner(self, path: str, uid: int, gid: int, recursive: bool = False) -> None:
        """Set file/directory owner."""
        call_file_ops(self._host._file_ops, "set_owner", path, uid, gid, recursive)

    def realpath(self, path: str) -> str:
        """Resolve path to absolute path (following symlinks)."""
        return call_file_ops(self._host._file_ops, "realpath", path)

    def blkid(self, device: str, use_cache: bool = True) -> dict[str, str]:
        """
        Get device metadata using blkid with optional caching.

        Args:
            device: Device path
            use_cache: Enable TTL-based caching (default: True, 2-minute TTL)

        Returns:
            Dict of device metadata (TYPE, UUID, LABEL, etc.)
        """
        return svc_blkid_lookup(
            self._host.logger,
            run_sudo,
            device,
            use_cache=use_cache,
            blkid_cache=self._host._blkid_cache,
            blkid_cache_ttl=self._host._blkid_cache_ttl,
        )
