# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Plan mode for generating migration execution plans from inventory data."""

# h2kvm/modes/plan_mode.py
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from h2kvm.core.exceptions import Fatal
from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


class PlanMode:  # pylint: disable=too-few-public-methods  # thin mode wrapper driven by run(), mirrors the other orchestration modes
    """
    plan mode:
      - read inventory.json (or call inventory mode externally) and emit plan YAML(s)
      - optionally emit batch YAML + libvirt XML templates (hook points)
    """

    def __init__(self, logger: logging.Logger, args):
        self.logger = logger
        self.args = args

    def run(self) -> None:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # builds a per-item migration plan from many optional inventory/CLI fields
        """Read inventory.json and write a plan YAML (and optional batch YAML) per VM."""
        out_root = Path(getattr(self.args, "output_dir", "./out")).expanduser().resolve()
        U.ensure_dir(out_root)

        plans_dir = (
            Path(self.args.plans_dir).expanduser().resolve()
            if getattr(self.args, "plans_dir", None)
            else (out_root / "plans")
        )
        U.ensure_dir(plans_dir)

        inventory_json = getattr(self.args, "inventory_json", None)
        if inventory_json:
            inv_path = Path(inventory_json).expanduser().resolve()
        else:
            # Default to <out>/inventory/inventory.json (matches InventoryMode default)
            inv_path = out_root / "inventory" / "inventory.json"

        if not inv_path.exists():
            raise Fatal(2, f"plan: inventory json not found: {inv_path}")

        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = list(inv.get("items", []))

        name_prefix = getattr(self.args, "name_prefix", None) or ""
        profile = getattr(self.args, "profile", "auto")
        enable_tests = bool(getattr(self.args, "enable_tests", False))
        default_uefi = bool(getattr(self.args, "default_uefi", False))
        default_bios = bool(getattr(self.args, "default_bios", False))
        emit_batch = bool(getattr(self.args, "emit_batch", False))

        if default_uefi and default_bios:
            raise Fatal(2, "plan: cannot set both --default-uefi and --default-bios")

        plan_index: list[dict[str, Any]] = []
        batch_vms: list[dict[str, Any]] = []

        for idx, it in enumerate(items):
            p = it.get("path")
            if not p:
                continue

            # Minimal default plan (additive + safe)
            vm_name = f"{name_prefix}{Path(p).stem}".strip("-") or f"{name_prefix}vm{idx}"
            to_output = f"{vm_name}.qcow2"

            plan: dict[str, Any] = {
                "command": "local",
                "vmdk": p,
                "output_dir": str(out_root),
                "workdir": str(out_root / "work"),
                "flatten": True,
                "flatten_format": "qcow2",
                "to_output": to_output,
                "out_format": "qcow2",
                "compress": True,
                "checksum": True,
                "fstab_mode": "stabilize-all",
                "print_fstab": True,
                "regen_initramfs": True,
                "remove_vmware_tools": True,
                "report": f"{vm_name}-report.md",
                "verbose": 1,
            }

            # Profile tweaks (keep conservative)
            # NOTE: You can expand this later (photon/windows heuristics) without changing orchestrator.
            if profile == "windows":
                plan["remove_vmware_tools"] = False
                plan["print_fstab"] = False
                plan["regen_initramfs"] = False
            elif profile in ("photon", "linux", "ubuntu", "debian", "suse"):
                plan["remove_vmware_tools"] = True

            if enable_tests:
                plan["libvirt_test"] = True
                plan["qemu_test"] = True
                plan["vm_name"] = vm_name
                if default_uefi:
                    plan["uefi"] = True
                if default_bios:
                    plan["uefi"] = False

            yml_path = plans_dir / f"{vm_name}.yaml"
            yml_path.write_text(self._to_yaml(plan), encoding="utf-8")

            plan_index.append({"vm_name": vm_name, "plan": str(yml_path), "to_output": to_output})
            batch_vms.append({"vmdk": plan["vmdk"], "to_output": plan["to_output"]})

        summary_md = (
            Path(self.args.summary_md).expanduser().resolve()
            if getattr(self.args, "summary_md", None)
            else (plans_dir / "plan-summary.md")
        )
        summary_md.write_text(self._summary_md(plan_index, inv_path), encoding="utf-8")

        if emit_batch and batch_vms:
            batch_path = plans_dir / "plan-batch.yaml"
            batch_plan = {
                "command": "local",
                "output_dir": str(out_root),
                "flatten": True,
                "out_format": "qcow2",
                "compress": True,
                "parallel_processing": True,
                "enable_recovery": True,
                "vms": batch_vms,
            }
            batch_path.write_text(self._to_yaml(batch_plan), encoding="utf-8")

        if getattr(self.args, "json", False):
            print(U.json_dump({"plans_dir": str(plans_dir), "plans": plan_index}))

        self.logger.info(f"Plans written: {plans_dir}")
        self.logger.info(f"Summary written: {summary_md}")

    def _summary_md(self, plan_index: list[dict[str, Any]], inv_path: Path) -> str:
        lines: list[str] = []
        lines.append("# h2kvm migration plan\n")
        lines.append(f"- Inventory: `{inv_path}`")
        lines.append(f"- Plans: **{len(plan_index)}**\n")
        lines.append("## Generated plan files\n")
        for x in plan_index:
            lines.append(f"- **{x['vm_name']}**: `{x['plan']}` → `{x['to_output']}`")
        lines.append("")
        return "\n".join(lines)

    def _to_yaml(self, data: dict[str, Any]) -> str:
        # Prefer PyYAML if you already ship it; else simple fallback.
        try:
            import yaml as _yaml  # type: ignore  # pylint: disable=import-outside-toplevel  # optional dependency; fall back to json below if unavailable

            return _yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
        except Exception:  # pylint: disable=broad-exception-caught  # covers both "yaml not installed" and any yaml.dump failure; falls back to json either way
            return json.dumps(data, indent=2)
