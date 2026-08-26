# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/ai/diagnostic.py
"""
Diagnostic engine for migration error analysis.

Matches error text against built-in regex patterns and learned patterns
from the knowledge base.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from .models import Diagnosis

if TYPE_CHECKING:
    from .knowledge_base import KnowledgeBase

# ---------------------------------------------------------------------------
# Built-in error patterns
# ---------------------------------------------------------------------------

_BuiltinPattern = dict[str, Any]

BUILTIN_PATTERNS: list[_BuiltinPattern] = [
    {
        "id": "fstab_uuid_mismatch",
        "regex": r"(?i)(fstab|uuid).*(mismatch|not found|missing|invalid)",
        "root_cause": "Filesystem UUID in fstab does not match actual partition UUID after conversion",
        "suggestions": [
            "Run blkid to find current UUIDs",
            "Update /etc/fstab with correct UUIDs",
            "Use --fstab-mode=stabilize-all to auto-fix",
        ],
    },
    {
        "id": "grub_not_found",
        "regex": r"(?i)(grub|bootloader).*(not found|missing|error|failed)",
        "root_cause": "GRUB bootloader is missing or misconfigured for the target disk",
        "suggestions": [
            "Reinstall GRUB: grub2-install /dev/sdX",
            "Regenerate grub config: grub2-mkconfig -o /boot/grub2/grub.cfg",
            "Check boot partition mount point in fstab",
        ],
    },
    {
        "id": "initramfs_missing_drivers",
        "regex": r"(?i)(initramfs|initrd|dracut).*(missing|no.*driver|virtio|failed)",
        "root_cause": "initramfs/initrd lacks virtio drivers needed for KVM boot",
        "suggestions": [
            "Regenerate initramfs with virtio modules",
            "Use --regen-initramfs flag",
            "Manually add virtio_blk, virtio_scsi, virtio_net to dracut config",
        ],
    },
    {
        "id": "buslogic_no_driver",
        "regex": r"(?i)buslogic.*(no.*driver|unsupported|cannot)",
        "root_cause": "BusLogic SCSI controller has no KVM/virtio driver",
        "suggestions": [
            "Change VM controller to LSI Logic in VMware before export",
            "Use --vmdk-auto-fix-controller to rewrite descriptor",
            "Enable automatic BusLogic-to-LSILogic fix",
        ],
    },
    {
        "id": "vmware_tools_conflict",
        "regex": r"(?i)(vmware.tools|open-vm-tools).*(conflict|error|fail|block)",
        "root_cause": "VMware Tools or open-vm-tools conflict with KVM guest agent",
        "suggestions": [
            "Use --remove-vmware-tools to auto-remove",
            "Manually uninstall vmware-tools: vmware-uninstall-tools.pl",
            "Install qemu-guest-agent as replacement",
        ],
    },
    {
        "id": "disk_space_exhausted",
        "regex": r"(?i)(no space|disk full|ENOSPC|not enough space)",
        "root_cause": "Insufficient disk space on the conversion host",
        "suggestions": [
            "Free disk space in the conversion directory",
            "Use --conversion-dir to specify a larger partition",
            "Use --compress to reduce output image size",
        ],
    },
    {
        "id": "permission_denied",
        "regex": r"(?i)(permission denied|EACCES|operation not permitted)",
        "root_cause": "Insufficient permissions for disk or mount operations",
        "suggestions": [
            "Run as root or with sudo",
            "Check file ownership and permissions",
            "Verify SELinux/AppArmor policies",
        ],
    },
    {
        "id": "qemu_img_error",
        "regex": r"(?i)qemu-img.*(error|fail|corrupt|invalid)",
        "root_cause": "qemu-img encountered an error during image conversion",
        "suggestions": [
            "Verify source image integrity",
            "Check qemu-img version compatibility",
            "Try converting with --out-format=raw first",
        ],
    },
    {
        "id": "lvm_activation_failed",
        "regex": r"(?i)(lvm|vg|lv).*(activation|failed|cannot|error)",
        "root_cause": "LVM volume group or logical volume activation failed",
        "suggestions": [
            "Use --container-isolation to isolate LVM operations",
            "Run vgscan/vgchange -ay manually",
            "Check for conflicting VG names with host LVM",
        ],
    },
    {
        "id": "mount_failed",
        "regex": r"(?i)mount.*(failed|error|cannot|wrong fs)",
        "root_cause": "Failed to mount guest filesystem for offline fixes",
        "suggestions": [
            "Check filesystem type and integrity",
            "Run fsck on the guest partition",
            "Verify the correct backend is selected",
        ],
    },
    {
        "id": "network_unreachable",
        "regex": r"(?i)(network|connection).*(unreachable|refused|timeout|timed out)",
        "root_cause": "Network connectivity issue during remote disk download",
        "suggestions": [
            "Check network connectivity to source host",
            "Verify firewall rules and proxy settings",
            "Retry the operation",
        ],
    },
    {
        "id": "selinux_context",
        "regex": r"(?i)selinux.*(context|label|denied|error)",
        "root_cause": "SELinux label mismatch after filesystem modifications",
        "suggestions": [
            "Add autorelabel trigger: touch /.autorelabel",
            "Set permissive mode temporarily for first boot",
            "Restore contexts: restorecon -Rv /",
        ],
    },
]


class DiagnosticEngine:
    """Diagnose migration errors via pattern matching."""

    def __init__(self, kb: KnowledgeBase | None = None) -> None:
        self._kb = kb
        self._compiled: list[tuple[_BuiltinPattern, re.Pattern[str]]] = []
        for pat in BUILTIN_PATTERNS:
            try:
                self._compiled.append((pat, re.compile(pat["regex"])))
            except re.error:
                pass

    def diagnose(self, error_text: str) -> list[Diagnosis]:
        """Match *error_text* against known patterns.

        Returns a list of :class:`Diagnosis` objects, best match first.
        """
        if not error_text:
            return []

        results: list[Diagnosis] = []

        # Built-in patterns
        for pat, rx in self._compiled:
            m = rx.search(error_text)
            if m:
                results.append(
                    Diagnosis(
                        pattern_id=pat["id"],
                        error_text=error_text,
                        root_cause=pat["root_cause"],
                        confidence=0.8,
                        suggestions=list(pat["suggestions"]),
                        learned=False,
                    )
                )

        # Learned patterns from knowledge base
        if self._kb is not None:
            for ep in self._kb.get_error_patterns():
                try:
                    if re.search(ep["regex"], error_text, re.IGNORECASE):
                        self._kb.increment_error_pattern_hit(ep["pattern_id"])
                        results.append(
                            Diagnosis(
                                pattern_id=ep["pattern_id"],
                                error_text=error_text,
                                root_cause=ep.get("root_cause", ""),
                                confidence=0.6,
                                suggestions=_safe_json_list(ep.get("suggestions", "[]")),
                                similar_errors=ep.get("hit_count", 0),
                                learned=True,
                            )
                        )
                except re.error:
                    pass

        # Sort by confidence descending
        results.sort(key=lambda d: d.confidence, reverse=True)
        return results

    def learn_pattern(
        self,
        pattern_id: str,
        regex: str,
        root_cause: str,
        suggestions: list[str],
    ) -> bool:
        """Register a new learned error pattern in the knowledge base.

        Returns True on success, False if no KB or error.
        """
        if self._kb is None:
            return False
        try:
            re.compile(regex)  # validate
        except re.error:
            return False
        self._kb.register_error_pattern(pattern_id, regex, root_cause, suggestions)
        # Also add to in-memory compiled list
        try:
            self._compiled.append(
                (
                    {"id": pattern_id, "regex": regex, "root_cause": root_cause, "suggestions": suggestions},
                    re.compile(regex),
                ),
            )
        except re.error:
            pass
        return True


def _safe_json_list(value: Any) -> list[str]:
    """Parse a JSON string to list, or return as-is if already a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return []
