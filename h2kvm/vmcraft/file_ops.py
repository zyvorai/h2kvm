# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/file_ops.py
"""
File operations for guest filesystem manipulation.

Provides comprehensive file and directory operations including:
- Basic file I/O (read, write, upload, download)
- Directory operations (ls, find, mkdir)
- File manipulation (copy, move, chmod, chown)
- Advanced operations (checksum, timestamps, permissions)
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import logging
import os
import shutil
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LRUCache:
    """
    Simple LRU (Least Recently Used) cache implementation.

    Stores cache entries with automatic eviction when size limit is reached.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries to cache
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key in self.cache:
            # Move to end (most recently used)
            value, timestamp = self.cache.pop(key)
            self.cache[key] = (value, timestamp)
            self.hits += 1
            return value

        self.misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        """
        Put value into cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        # Remove if already exists
        if key in self.cache:
            self.cache.pop(key)

        # Add to end
        self.cache[key] = (value, time.time())

        # Evict oldest if over limit
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        """
        Invalidate cache entry.

        Args:
            key: Cache key to remove
        """
        if key in self.cache:
            self.cache.pop(key)

    def invalidate_prefix(self, prefix: str) -> None:
        """
        Invalidate all entries with given prefix.

        Args:
            prefix: Key prefix to invalidate
        """
        keys_to_remove = [k for k in self.cache if k.startswith(prefix)]
        for key in keys_to_remove:
            self.cache.pop(key)

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()

    def stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self.hits,
            "misses": self.misses,
            "size": len(self.cache),
            "max_size": self.max_size,
            "hit_rate": round(hit_rate, 2),
        }


class FileOperations:  # pylint: disable=too-many-public-methods  # guest filesystem operations wrapper covers many distinct file/dir primitives
    """
    File and directory operations on guest filesystem.

    All operations work relative to a mount root provided by the mount manager.
    """

    def __init__(
        self,
        instance_logger: logging.Logger,
        mount_root: Path,
        enable_cache: bool = True,
        cache_size: int = 1000,
    ):
        """
        Initialize file operations.

        Args:
            instance_logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
            enable_cache: Enable caching (default: True)
            cache_size: Maximum cache entries (default: 1000)
        """
        self.logger = instance_logger
        self.mount_root = mount_root
        self.enable_cache = enable_cache

        # Initialize caches
        self._metadata_cache = LRUCache(max_size=cache_size) if enable_cache else None
        self._dir_cache = LRUCache(max_size=cache_size // 2) if enable_cache else None

    def _guest_path(self, path: str) -> Path:
        """
        Convert guest path to host path in mount root.

        Args:
            path: Path in guest filesystem (e.g., /etc/fstab)

        Returns:
            Absolute path on host filesystem

        Raises:
            ValueError: If path escapes the mount root (path traversal)
        """
        candidate = self.mount_root / path[1:] if path.startswith("/") else self.mount_root / path

        # Resolve ".." components without following symlinks to prevent traversal
        # Use os.path.normpath to collapse ".." without hitting the filesystem
        normalized = Path(os.path.normpath(candidate))
        mount_root_resolved = Path(os.path.normpath(self.mount_root))

        if (
            not str(normalized).startswith(str(mount_root_resolved) + os.sep)
            and normalized != mount_root_resolved
        ):
            raise ValueError(
                f"Security: path '{path}' resolves outside the guest filesystem mount root. "
                f"Use an absolute guest path without '..' components."
            )

        # Resolve symlinks to prevent a malicious guest image from escaping
        # the mount root via symlinked paths.
        if normalized.exists():
            resolved = normalized.resolve()
        else:
            # For write operations the target may not exist yet — resolve the parent.
            resolved = normalized.parent.resolve() / normalized.name

        mount_root_real = mount_root_resolved.resolve()
        if not str(resolved).startswith(str(mount_root_real) + os.sep) and resolved != mount_root_real:
            raise ValueError(
                f"Security: path '{path}' resolves via symlinks outside the guest "
                f"filesystem mount root. Symlink traversal detected."
            )

        return normalized

    # Basic file operations

    def _get_cached_metadata(self, path: str) -> dict[str, Any] | None:
        """Get cached file metadata."""
        if not self.enable_cache or not self._metadata_cache:
            return None
        return self._metadata_cache.get(f"meta:{path}")

    def _cache_metadata(self, path: str, metadata: dict[str, Any]) -> None:
        """Cache file metadata."""
        if self.enable_cache and self._metadata_cache:
            self._metadata_cache.put(f"meta:{path}", metadata)

    def _invalidate_cache(self, path: str) -> None:
        """Invalidate cache for path and parent directory."""
        if not self.enable_cache:
            return

        if self._metadata_cache:
            self._metadata_cache.invalidate(f"meta:{path}")

        if self._dir_cache:
            # Invalidate parent directory listing
            parent = str(Path(path).parent)
            self._dir_cache.invalidate(f"dir:{parent}")

    def _get_metadata(self, path: str) -> dict[str, Any]:
        """
        Get file metadata with caching.

        Returns:
            Dict with exists, is_file, is_dir, size, mtime, permissions
        """
        # Check cache first
        cached = self._get_cached_metadata(path)
        if cached is not None:
            return cached

        # Gather metadata
        guest_path = self._guest_path(path)
        metadata: dict[str, Any] = {
            "exists": guest_path.exists(),
            "is_file": False,
            "is_dir": False,
            "is_symlink": False,
            "size": 0,
            "mtime": 0,
            "permissions": 0,
        }

        if metadata["exists"]:
            try:
                stat_info = guest_path.stat()
                metadata["is_file"] = guest_path.is_file()
                metadata["is_dir"] = guest_path.is_dir()
                metadata["is_symlink"] = guest_path.is_symlink()
                metadata["size"] = stat_info.st_size
                metadata["mtime"] = stat_info.st_mtime
                metadata["permissions"] = stat_info.st_mode
            except (OSError, PermissionError):
                pass

        # Cache the metadata
        self._cache_metadata(path, metadata)

        return metadata

    def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        return self._get_metadata(path)["is_file"]

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        return self._get_metadata(path)["is_dir"]

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return self._get_metadata(path)["exists"]

    def stat(self, path: str) -> dict[str, int]:
        """
        Get file stat information (guestfs-compatible format).

        Returns:
            Dict with size, mtime, and other stat fields
        """
        metadata = self._get_metadata(path)

        if not metadata["exists"]:
            raise FileNotFoundError(
                f"Path '{path}' does not exist in the guest filesystem. "
                f"Verify the path is correct and the guest disk is properly mounted."
            )

        # Return guestfs-compatible stat dict
        return {
            "dev": 0,
            "ino": 0,
            "mode": metadata["permissions"],
            "nlink": 1,
            "uid": 0,
            "gid": 0,
            "rdev": 0,
            "size": metadata["size"],
            "blksize": 4096,
            "blocks": (metadata["size"] + 4095) // 4096,
            "atime": int(metadata["mtime"]),
            "mtime": int(metadata["mtime"]),
            "ctime": int(metadata["mtime"]),
        }

    def read_file(self, path: str) -> bytes:
        """Read file contents as bytes."""
        return self._guest_path(path).read_bytes()

    def cat(self, path: str) -> str:
        """Read file contents as string."""
        return self._guest_path(path).read_text(encoding="utf-8")

    def write(self, path: str, content: bytes | str) -> None:
        """Write content to file."""
        if isinstance(content, str):
            self._guest_path(path).write_text(content, encoding="utf-8")
        else:
            self._guest_path(path).write_bytes(content)

        # Invalidate cache
        self._invalidate_cache(path)

    def upload(self, local_path: str, remote_path: str) -> None:
        """
        Upload a file from host to guest filesystem.

        Args:
            local_path: Path to file on host
            remote_path: Destination path in guest filesystem

        Example:
            file_ops.upload('/tmp/myfile.txt', '/etc/myconfig.conf')
        """
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(
                f"Local file not found at '{local_path}'. Verify the path exists and is readable."
            )

        if not local.is_file():
            raise ValueError(
                f"'{local_path}' is not a regular file (it may be a directory or special file). "
                f"Provide a path to a regular file."
            )

        # Read from host, write to guest
        content = local.read_bytes()
        guest_path = self._guest_path(remote_path)

        # Ensure parent directory exists
        guest_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to guest
        guest_path.write_bytes(content)

        # Invalidate cache
        self._invalidate_cache(remote_path)

        self.logger.info(f"Uploaded: {local_path} -> {remote_path} ({len(content)} bytes)")

    def download(self, remote_path: str, local_path: str) -> None:
        """
        Download a file from guest to host filesystem.

        Args:
            remote_path: Path to file in guest filesystem
            local_path: Destination path on host

        Example:
            file_ops.download('/etc/fstab', '/tmp/fstab.backup')
        """
        guest_path = self._guest_path(remote_path)

        if not guest_path.exists():
            raise FileNotFoundError(
                f"File '{remote_path}' not found in the guest filesystem. "
                f"Verify the path exists on the guest disk."
            )

        if not guest_path.is_file():
            raise ValueError(
                f"'{remote_path}' is not a regular file in the guest filesystem "
                f"(it may be a directory or special file)."
            )

        # Read from guest
        content = guest_path.read_bytes()

        # Write to host
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(content)

        self.logger.info(f"Downloaded: {remote_path} -> {local_path} ({len(content)} bytes)")

    # Directory operations

    def ls(self, path: str) -> list[str]:
        """List directory contents with caching."""
        # Check cache first
        if self.enable_cache and self._dir_cache:
            cached = self._dir_cache.get(f"dir:{path}")
            if cached is not None:
                return cached

        # Get directory listing
        result = [str(p.name) for p in self._guest_path(path).iterdir()]

        # Cache the result
        if self.enable_cache and self._dir_cache:
            self._dir_cache.put(f"dir:{path}", result)

        return result

    def find(self, path: str) -> list[str]:
        """Recursively find all files under path."""
        result = []
        base = self._guest_path(path)
        for root, _dirs, files in os.walk(base):
            root_path = Path(root)
            for f in files:
                rel = root_path / f
                with contextlib.suppress(ValueError):
                    result.append(str(rel.relative_to(base)))
        return result

    def mkdir_p(self, path: str) -> None:
        """Create directory (with parents)."""
        self._guest_path(path).mkdir(parents=True, exist_ok=True)
        # Invalidate cache
        self._invalidate_cache(path)

    # File manipulation

    def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        self._guest_path(path).chmod(mode)
        self._invalidate_cache(path)

    def ln_sf(self, target: str, link_name: str) -> None:
        """Create symbolic link."""
        link_path = self._guest_path(link_name)
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(target)
        self._invalidate_cache(link_name)

    def cp(self, src: str, dst: str) -> None:
        """Copy file."""
        shutil.copy2(self._guest_path(src), self._guest_path(dst))
        self._invalidate_cache(dst)

    def rm_f(self, path: str) -> None:
        """Remove file (force)."""
        try:
            self._guest_path(path).unlink()
            self._invalidate_cache(path)
        except FileNotFoundError:
            pass

    def touch(self, path: str) -> None:
        """Create empty file or update timestamp."""
        self._guest_path(path).touch()
        self._invalidate_cache(path)

    def readlink(self, path: str) -> str:
        """Read symbolic link target."""
        return str(self._guest_path(path).readlink())

    # Advanced operations

    def find_files(self, path: str, pattern: str | None = None, file_type: str | None = None) -> list[str]:
        """
        Find files in guest filesystem.

        Args:
            path: Starting directory path
            pattern: Optional glob pattern (e.g., "*.log", "config.*")
            file_type: Optional type filter ("f"=file, "d"=directory, "l"=symlink)

        Returns:
            List of matching file paths
        """
        search_path = self._guest_path(path)
        if not search_path.exists():
            return []

        results = []

        def scan_dir(directory: Path, base: str = ""):
            try:
                for entry in directory.iterdir():
                    rel_path = f"{base}/{entry.name}" if base else entry.name
                    full_guest_path = f"{path}/{rel_path}".replace("//", "/")

                    # Check if entry matches filters
                    matches = True

                    # Type filter
                    if file_type:
                        if (  # pylint: disable=too-many-boolean-expressions  # straightforward file/dir/symlink type match
                            (file_type == "f" and not entry.is_file())
                            or (file_type == "d" and not entry.is_dir())
                            or (file_type == "l" and not entry.is_symlink())
                        ):
                            matches = False

                    # Pattern filter
                    if matches and pattern:
                        if not fnmatch.fnmatch(entry.name, pattern):
                            matches = False

                    if matches:
                        results.append(full_guest_path)

                    # Always recurse into directories (regardless of type/pattern filters)
                    if entry.is_dir() and not entry.is_symlink():
                        scan_dir(entry, rel_path)

            except (PermissionError, OSError) as e:
                self.logger.debug(f"Cannot access {directory}: {e}")

        scan_dir(search_path)
        return sorted(results)

    def checksum(self, path: str, algorithm: str = "sha256") -> str:
        """
        Calculate checksum of file.

        Args:
            path: File path in guest
            algorithm: Hash algorithm (md5, sha1, sha256, sha512)

        Returns:
            Hexadecimal checksum string
        """
        file_path = self._guest_path(path)
        if not file_path.is_file():
            raise ValueError(
                f"'{path}' is not a regular file in the guest filesystem. Cannot compute checksum on directories."
            )

        hasher = hashlib.new(algorithm)
        with file_path.open("rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)

        checksum_value = hasher.hexdigest()
        self.logger.debug(f"{algorithm}({path}) = {checksum_value}")
        return checksum_value

    def file_age(self, path: str) -> dict[str, Any]:
        """
        Get file timestamps.

        Returns:
            Dict with atime, mtime, ctime (seconds since epoch)
        """
        file_path = self._guest_path(path)
        stat_info = file_path.stat()

        return {
            "atime": stat_info.st_atime,  # Access time
            "mtime": stat_info.st_mtime,  # Modification time
            "ctime": stat_info.st_ctime,  # Change time
            "size": stat_info.st_size,
        }

    def set_permissions(self, path: str, mode: int, recursive: bool = False) -> None:
        """
        Set file/directory permissions.

        Args:
            path: File or directory path
            mode: Permission mode (octal, e.g., 0o755)
            recursive: Apply to all files in directory
        """
        target = self._guest_path(path)

        if recursive and target.is_dir():
            for item in target.rglob("*"):
                try:
                    item.chmod(mode)
                except (PermissionError, OSError) as e:
                    self.logger.warning(f"Cannot chmod {item}: {e}")
        else:
            target.chmod(mode)

        self.logger.info(f"Set permissions {oct(mode)} on {path}")

    def set_owner(self, path: str, uid: int, gid: int, recursive: bool = False) -> None:
        """
        Set file/directory owner.

        Args:
            path: File or directory path
            uid: User ID
            gid: Group ID
            recursive: Apply to all files in directory
        """
        target = self._guest_path(path)

        if recursive and target.is_dir():
            for item in target.rglob("*"):
                try:
                    os.chown(item, uid, gid)
                except (PermissionError, OSError) as e:
                    self.logger.warning(f"Cannot chown {item}: {e}")
        else:
            os.chown(target, uid, gid)

        self.logger.info(f"Set owner {uid}:{gid} on {path}")

    def realpath(self, path: str) -> str:
        """
        Resolve path to absolute path (following symlinks).

        Args:
            path: Path to resolve

        Returns:
            Absolute path with symlinks resolved

        Raises:
            ValueError: If resolved path escapes the mount root
        """
        guest_path = self._guest_path(path)
        resolved = guest_path.resolve()

        # Convert back to guest path (remove mount_root prefix)
        mount_root_resolved = self.mount_root.resolve()
        try:
            rel = resolved.relative_to(mount_root_resolved)
            return f"/{rel}"
        except ValueError as err:
            raise ValueError(
                f"Security: resolved path for '{path}' escapes the guest filesystem mount root. "
                f"Use paths relative to the guest root without symlink escapes."
            ) from err

    # Cache management

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with metadata and directory cache statistics
        """
        if not self.enable_cache:
            return {
                "enabled": False,
                "metadata_cache": {},
                "dir_cache": {},
            }

        return {
            "enabled": True,
            "metadata_cache": self._metadata_cache.stats() if self._metadata_cache else {},
            "dir_cache": self._dir_cache.stats() if self._dir_cache else {},
        }

    def clear_cache(self) -> None:
        """Clear all caches."""
        if self.enable_cache:
            if self._metadata_cache:
                self._metadata_cache.clear()
            if self._dir_cache:
                self._dir_cache.clear()
            self.logger.debug("File operation caches cleared")
