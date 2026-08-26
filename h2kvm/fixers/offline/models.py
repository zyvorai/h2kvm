# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Data models for offline fixing operations.

This module provides dataclasses for tracking the results of various
offline VM fixing operations, particularly VMware tools removal.

Example:
    >>> result = VmwareRemovalResult()
    >>> result.removed_paths.append("/usr/lib/vmware-tools")
    >>> result.removed_services.append("vmware-tools.service")
    >>> audit_dict = result.as_dict()
    >>> print(audit_dict["counts"]["removed_paths"])
    1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VmwareRemovalResult:  # pylint: disable=too-many-instance-attributes
    # Each field tracks a distinct category of removal action for the
    # audit trail; that's the point of this reporting model.
    """
    Result of VMware tools removal operation.

    Tracks all actions taken during VMware tools cleanup, including files
    removed, services disabled, and any errors encountered. Used for
    audit trail and reporting.

    Attributes:
        enabled: Whether VMware removal was enabled/attempted
        removed_paths: List of file/directory paths that were removed
        removed_services: List of systemd services that were disabled/removed
        removed_symlinks: List of symbolic links that were removed
        package_hints: List of package manager hints found (e.g., RPM, DEB packages)
        touched_files: List of files that were modified (not removed)
        warnings: List of warning messages generated during removal
        notes: List of informational notes about the removal process
        errors: List of error messages if removal failed
    """

    enabled: bool = True
    removed_paths: list[str] = field(default_factory=list)
    removed_services: list[str] = field(default_factory=list)
    removed_symlinks: list[str] = field(default_factory=list)
    package_hints: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "enabled": self.enabled,
            "removed_paths": self.removed_paths,
            "removed_services": self.removed_services,
            "removed_symlinks": self.removed_symlinks,
            "package_hints": self.package_hints,
            "touched_files": self.touched_files,
            "warnings": self.warnings,
            "notes": self.notes,
            "errors": self.errors,
            "counts": {
                "removed_paths": len(self.removed_paths),
                "removed_services": len(self.removed_services),
                "removed_symlinks": len(self.removed_symlinks),
                "package_hints": len(self.package_hints),
                "touched_files": len(self.touched_files),
                "warnings": len(self.warnings),
                "notes": len(self.notes),
                "errors": len(self.errors),
            },
        }
