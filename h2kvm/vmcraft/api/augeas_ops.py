# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Augeas Configuration Management Operations.

Provides Augeas-based configuration management for VMCraft via composition.
"""

from __future__ import annotations


class AugeasOps:
    """Augeas configuration management via composition."""

    # pylint: disable=protected-access
    # Deliberate composition-pattern coupling: this Ops class reaches into the
    # host client's internal dispatch/cache attributes, same pattern used
    # throughout h2kvm/vmcraft/api/*.py within the same package.

    def __init__(self, host) -> None:
        self._host = host

    def aug_init(self, flags: int = 0) -> None:
        """
        Initialize Augeas configuration API.

        Must be called before using other aug_* methods. Augeas provides structured
        editing of configuration files using lenses for common formats (fstab,
        network configs, systemd units, etc.).

        Args:
            flags: Augeas initialization flags (default: 0)
                   Common flags: augeas.Augeas.SAVE_BACKUP, augeas.Augeas.NO_LOAD

        Raises:
            RuntimeError: If not launched or Augeas library not available

        Example:
            g.aug_init()
            # Now ready to use aug_get, aug_set, etc.
        """
        self._host._dispatch_manager_attr_call("_augeas", "init", flags)

    def aug_close(self) -> None:
        """
        Close Augeas and release resources.

        Should be called when finished with Augeas operations to free memory.

        Example:
            g.aug_init()
            # ... use Augeas
            g.aug_close()
        """
        self._host._dispatch_manager_attr_call("_augeas", "close")

    def aug_get(self, path: str) -> str | None:
        """
        Get configuration value at Augeas path.

        Args:
            path: Augeas path (e.g., "/files/etc/fstab/1/spec")

        Returns:
            Configuration value or None if path doesn't exist

        Raises:
            RuntimeError: If Augeas not initialized

        Example:
            g.aug_init()
            # Get first fstab entry's device
            device = g.aug_get("/files/etc/fstab/1/spec")
            print(f"Device: {device}")
        """
        return self._host._dispatch_manager_attr_call("_augeas", "get", path)

    def aug_set(self, path: str, value: str) -> None:
        """
        Set configuration value at Augeas path.

        Changes are made in memory. Call aug_save() to write to disk.

        Args:
            path: Augeas path
            value: Value to set

        Raises:
            RuntimeError: If Augeas not initialized or set fails

        Example:
            g.aug_init()
            # Change first fstab entry's dump value
            g.aug_set("/files/etc/fstab/1/dump", "0")
            g.aug_save()
        """
        self._host._dispatch_manager_attr_call("_augeas", "set", path, value)

    def aug_save(self) -> None:
        """
        Save Augeas changes to disk.

        Writes all pending changes to their respective configuration files.

        Raises:
            RuntimeError: If Augeas not initialized or save fails

        Example:
            g.aug_init()
            g.aug_set("/files/etc/fstab/1/dump", "0")
            g.aug_save()  # Writes changes to /etc/fstab
        """
        self._host._dispatch_manager_attr_call("_augeas", "save")

    def aug_match(self, pattern: str) -> list[str]:
        """
        Match Augeas paths by pattern.

        Args:
            pattern: Augeas path pattern (e.g., "/files/etc/fstab/*")

        Returns:
            List of matching paths

        Raises:
            RuntimeError: If Augeas not initialized

        Example:
            g.aug_init()
            # Get all fstab entries
            entries = g.aug_match("/files/etc/fstab/*[label() != '#comment']")
            print(f"Found {len(entries)} fstab entries")
        """
        return self._host._dispatch_manager_attr_call("_augeas", "match", pattern)

    def aug_insert(self, path: str, label: str, before: bool = True) -> None:
        """
        Insert new node at Augeas path.

        Args:
            path: Path where to insert (must exist)
            label: Label for new node
            before: Insert before (True) or after (False) the path

        Raises:
            RuntimeError: If Augeas not initialized or insert fails

        Example:
            g.aug_init()
            # Insert new fstab entry before entry 1
            g.aug_insert("/files/etc/fstab/1", "01", before=True)
            g.aug_set("/files/etc/fstab/01/spec", "/dev/sda1")
            g.aug_set("/files/etc/fstab/01/file", "/boot")
            g.aug_save()
        """
        self._host._dispatch_manager_attr_call("_augeas", "insert", path, label, before)

    def aug_rm(self, path: str) -> int:
        """
        Remove nodes matching Augeas path.

        Args:
            path: Augeas path (can be pattern with wildcards)

        Returns:
            Number of nodes removed

        Raises:
            RuntimeError: If Augeas not initialized

        Example:
            g.aug_init()
            # Remove all commented lines from fstab
            count = g.aug_rm("/files/etc/fstab/#comment")
            print(f"Removed {count} comments")
            g.aug_save()
        """
        return self._host._dispatch_manager_attr_call("_augeas", "remove", path)

    def aug_defvar(self, name: str, expr: str) -> None:
        """
        Define Augeas variable for use in path expressions.

        Variables can be used in subsequent paths as $name.

        Args:
            name: Variable name
            expr: Expression to evaluate

        Raises:
            RuntimeError: If Augeas not initialized or defvar fails

        Example:
            g.aug_init()
            # Define variable for fstab root entry
            g.aug_defvar("root", "/files/etc/fstab/*[file='/']")
            device = g.aug_get("$root/spec")
            print(f"Root device: {device}")
        """
        self._host._dispatch_manager_attr_call("_augeas", "defvar", name, expr)

    def aug_defnode(self, name: str, expr: str, value: str | None = None) -> tuple[int, bool]:
        """
        Define Augeas node variable.

        Creates the node if it doesn't exist.

        Args:
            name: Variable name
            expr: Node expression
            value: Optional value to set if node is created

        Returns:
            Tuple of (number of nodes matching expr, created flag)

        Raises:
            RuntimeError: If Augeas not initialized or defnode fails

        Example:
            g.aug_init()
            # Ensure fstab has a /tmp entry
            count, created = g.aug_defnode("tmp", "/files/etc/fstab/*[file='/tmp']", None)
            if created:
                g.aug_set("$tmp/spec", "tmpfs")
                g.aug_set("$tmp/vfstype", "tmpfs")
                g.aug_save()
        """
        return self._host._dispatch_manager_attr_call("_augeas", "defnode", name, expr, value)
