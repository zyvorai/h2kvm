# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/remediation.py
"""
Remediation engine for generating fix plans from diagnoses.

Maps diagnostic pattern IDs to concrete remediation steps, with
deduplication and risk filtering.
"""

from __future__ import annotations

from .models import AIConfig, Diagnosis, Remediation, RemediationPlan, RiskLevel

# ---------------------------------------------------------------------------
# Fix registry: pattern_id -> list of Remediation templates
# ---------------------------------------------------------------------------

FIX_REGISTRY: dict[str, list[dict[str, object]]] = {
    "fstab_uuid_mismatch": [
        {
            "fix_id": "fstab_stabilize",
            "description": "Re-stabilise fstab UUIDs using hyper2kvm offline fixer",
            "command": "--fstab-mode=stabilize-all",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
        {
            "fix_id": "fstab_manual_blkid",
            "description": "Manually update fstab with blkid output",
            "command": "blkid && vi /etc/fstab",
            "risk": RiskLevel.MEDIUM,
            "auto_applicable": False,
        },
    ],
    "grub_not_found": [
        {
            "fix_id": "grub_reinstall",
            "description": "Reinstall GRUB bootloader",
            "command": "grub2-install /dev/sdX && grub2-mkconfig -o /boot/grub2/grub.cfg",
            "risk": RiskLevel.MEDIUM,
            "auto_applicable": False,
        },
        {
            "fix_id": "grub_regen_config",
            "description": "Regenerate GRUB configuration via hyper2kvm",
            "command": "--no-grub is NOT set (default enables grub fix)",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
    ],
    "initramfs_missing_drivers": [
        {
            "fix_id": "initramfs_regen",
            "description": "Regenerate initramfs with virtio drivers",
            "command": "--regen-initramfs",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
        {
            "fix_id": "initramfs_add_drivers",
            "description": "Add specific virtio drivers to initramfs",
            "command": "--initramfs-add-drivers virtio,virtio_blk,virtio_scsi,virtio_net,virtio_pci",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
    ],
    "buslogic_no_driver": [
        {
            "fix_id": "buslogic_autofix",
            "description": "Auto-rewrite VMDK descriptor from BusLogic to LSI Logic",
            "command": "--vmdk-auto-fix-controller",
            "risk": RiskLevel.MEDIUM,
            "auto_applicable": True,
        },
    ],
    "vmware_tools_conflict": [
        {
            "fix_id": "remove_vmware_tools",
            "description": "Remove VMware Tools during offline fix phase",
            "command": "--remove-vmware-tools",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
    ],
    "disk_space_exhausted": [
        {
            "fix_id": "use_conversion_dir",
            "description": "Use a dedicated conversion directory with more space",
            "command": "--conversion-dir /path/to/larger/partition",
            "risk": RiskLevel.LOW,
            "auto_applicable": False,
        },
        {
            "fix_id": "enable_compression",
            "description": "Enable output compression to reduce disk usage",
            "command": "--compress",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
    ],
    "permission_denied": [
        {
            "fix_id": "run_as_root",
            "description": "Run with root privileges",
            "command": "sudo h2kvmctl ...",
            "risk": RiskLevel.LOW,
            "auto_applicable": False,
        },
    ],
    "lvm_activation_failed": [
        {
            "fix_id": "lvm_container_isolation",
            "description": "Enable container isolation for LVM operations",
            "command": "--container-isolation",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
    ],
    "selinux_context": [
        {
            "fix_id": "selinux_autorelabel",
            "description": "Trigger SELinux autorelabel on next boot",
            "command": "touch /.autorelabel (done automatically by fixer)",
            "risk": RiskLevel.LOW,
            "auto_applicable": True,
        },
    ],
}

# Risk ordering for filtering
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class RemediationEngine:
    """Generate remediation plans from diagnoses."""

    def __init__(self, config: AIConfig | None = None) -> None:
        self._auto_remediate = config.auto_remediate if config else False
        max_risk_str = (config.auto_remediate_risk_max if config else "low").lower()
        self._max_auto_risk = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL,
        }.get(max_risk_str, RiskLevel.LOW)

    def plan(self, diagnosis: Diagnosis) -> RemediationPlan:
        """Build a :class:`RemediationPlan` for a single diagnosis."""
        templates = FIX_REGISTRY.get(diagnosis.pattern_id, [])
        fixes: list[Remediation] = []
        seen_ids: set[str] = set()
        for tmpl in templates:
            fix_id = str(tmpl["fix_id"])
            if fix_id in seen_ids:
                continue
            seen_ids.add(fix_id)
            fixes.append(
                Remediation(
                    fix_id=fix_id,
                    description=str(tmpl.get("description", "")),
                    command=str(tmpl.get("command", "")),
                    risk=tmpl.get("risk", RiskLevel.LOW),  # type: ignore[arg-type]
                    auto_applicable=bool(tmpl.get("auto_applicable", False)),
                    prerequisites=list(tmpl.get("prerequisites", [])),
                )
            )

        # Filter by auto risk ceiling when auto_remediate is on
        if self._auto_remediate:
            max_order = _RISK_ORDER.get(self._max_auto_risk, 0)
            fixes = [f for f in fixes if not f.auto_applicable or _RISK_ORDER.get(f.risk, 0) <= max_order]

        est_success = diagnosis.confidence * 0.9 if fixes else 0.0

        return RemediationPlan(
            diagnosis=diagnosis,
            fixes=fixes,
            estimated_success_rate=round(est_success, 2),
        )

    def plan_all(self, diagnoses: list[Diagnosis]) -> list[RemediationPlan]:
        """Generate remediation plans for multiple diagnoses, deduplicating fixes."""
        plans: list[RemediationPlan] = []
        global_seen: set[str] = set()
        for diag in diagnoses:
            plan = self.plan(diag)
            # Deduplicate across plans
            deduped: list[Remediation] = []
            for fix in plan.fixes:
                if fix.fix_id not in global_seen:
                    global_seen.add(fix.fix_id)
                    deduped.append(fix)
            plan.fixes = deduped
            if plan.fixes:
                plans.append(plan)
        return plans

    def get_auto_fixes(self, plans: list[RemediationPlan]) -> list[Remediation]:
        """Extract auto-applicable fixes within the risk ceiling."""
        if not self._auto_remediate:
            return []
        max_order = _RISK_ORDER.get(self._max_auto_risk, 0)
        auto: list[Remediation] = []
        seen: set[str] = set()
        for plan in plans:
            for fix in plan.fixes:
                if fix.auto_applicable and fix.fix_id not in seen:
                    if _RISK_ORDER.get(fix.risk, 0) <= max_order:
                        seen.add(fix.fix_id)
                        auto.append(fix)
        return auto
