# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Inventory mode for discovering and cataloging VMs across providers."""

# hyper2kvm/modes/inventory_mode.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Optional: reuse your existing building blocks (present in your tree)
from hyper2kvm.converters.fetch import Fetch
from hyper2kvm.core.exceptions import Fatal
from hyper2kvm.core.utils import U
from hyper2kvm.infrastructure.ssh.ssh_client import SSHClient
from hyper2kvm.infrastructure.ssh.ssh_config import SSHConfig
from hyper2kvm.providers.vmware.clients.client import PYVMOMI_AVAILABLE, REQUESTS_AVAILABLE
from hyper2kvm.providers.vmware.utils.vmdk_parser import VMDK

from ..ssh_opts import normalize_ssh_opts as _normalize_ssh_opt_impl

if TYPE_CHECKING:
    import logging


# pylint: disable-next=too-few-public-methods  # plain data holder for one inventory risk finding
@dataclass
class Risk:
    """A single risk finding surfaced during inventory scanning."""

    severity: str  # "low"|"medium"|"high"
    code: str
    message: str
    details: dict[str, Any] | None = None


# run() is the sole public entrypoint by design; the rest are private helpers.
# pylint: disable-next=too-few-public-methods
class InventoryMode:
    """
    inventory mode:
      - scan a local file/dir OR ESXi remote descriptor pull OR vSphere selection (optional scaffold)
      - emit inventory.json + inventory.md (optional) + artifacts.json (optional)
      - exit code policy via --fail-on {none, low, medium, high}
    """

    def __init__(self, logger: logging.Logger, args):
        """Store the logger and parsed CLI args used to drive run()."""
        self.logger = logger
        self.args = args

    def run(self) -> None:
        """Scan the configured source and write inventory.json/inventory.md/artifacts.json."""
        out_root = Path(getattr(self.args, "output_dir", "./out")).expanduser().resolve()
        U.ensure_dir(out_root)

        inventory_dir = (
            Path(self.args.inventory_dir).expanduser().resolve()
            if getattr(self.args, "inventory_dir", None)
            else (out_root / "inventory")
        )
        U.ensure_dir(inventory_dir)

        json_out = (
            Path(self.args.json_out).expanduser().resolve()
            if getattr(self.args, "json_out", None)
            else (inventory_dir / "inventory.json")
        )
        md_out = (
            Path(self.args.md_out).expanduser().resolve()
            if getattr(self.args, "md_out", None)
            else (inventory_dir / "inventory.md")
        )
        artifacts_out = (
            Path(self.args.artifacts_out).expanduser().resolve()
            if getattr(self.args, "artifacts_out", None)
            else (inventory_dir / "artifacts.json")
        )

        source = getattr(self.args, "source", "auto")
        selector = getattr(self.args, "input", None)

        # Allow ESXi-only via flags (even if --input not provided)
        if (
            source in ("auto", "esxi")
            and getattr(self.args, "esxi_host", None)
            and getattr(self.args, "esxi_remote", None)
        ):
            source = "esxi"
        elif source == "auto":
            if selector is None:
                raise Fatal(2, "inventory: need --input or ESXi flags (--esxi-host/--esxi-remote)")
            p = Path(str(selector)).expanduser()
            source = "dir" if p.is_dir() else "local"

        inv: dict[str, Any] = {
            "mode": "inventory",
            "source": source,
            "output_dir": str(out_root),
            "inventory_dir": str(inventory_dir),
            "items": [],
            "risks": [],
            "summary": {},
        }
        artifacts: dict[str, Any] = {"downloaded": [], "notes": []}

        risks: list[Risk] = []

        if source in ("local", "dir"):
            items = self._scan_local(source=source, selector=selector)
            inv["items"] = items
            risks.extend(self._risk_checks(items))

        elif source == "esxi":
            items, downloaded = self._scan_esxi(out_root=out_root)
            inv["items"] = items
            artifacts["downloaded"] = downloaded
            risks.extend(self._risk_checks(items))

        elif source == "vsphere":
            # Keep it additive: this mode can just validate dependencies and suggest using vsphere subcommand
            # Your full vSphere flow already exists in VsphereMode under cmd=vsphere.
            if not PYVMOMI_AVAILABLE:
                raise Fatal(2, "pyvmomi not installed. Install: pip install pyvmomi")
            if not REQUESTS_AVAILABLE:
                self.logger.warning(
                    "requests not installed; some vSphere download actions may be unavailable"
                )
            inv["items"] = []
            inv["summary"] = {
                "note": "vSphere inventory can be obtained via the `vsphere` command; this is a scaffold."
            }
            artifacts["notes"].append("Use: hyper2kvm vsphere list_vm_names / get_vm_by_name / vm_disks")

        else:
            raise Fatal(2, f"inventory: unknown --source {source}")

        # finalize
        inv["risks"] = [r.__dict__ for r in risks]
        inv["summary"] = self._summarize(inv["items"], risks)

        json_out.write_text(U.json_dump(inv), encoding="utf-8")
        artifacts_out.write_text(U.json_dump(artifacts), encoding="utf-8")
        md_out.write_text(self._to_markdown(inv), encoding="utf-8")

        if getattr(self.args, "json", False):
            print(U.json_dump(inv))

        self._maybe_fail(risks, getattr(self.args, "fail_on", "high"))

        self.logger.info(f"Inventory written: {json_out}")
        self.logger.info(f"Artifacts written: {artifacts_out}")
        self.logger.info(f"Markdown written: {md_out}")

    def _scan_local(self, source: str, selector: str | None) -> list[dict[str, Any]]:
        p = Path(str(selector)).expanduser().resolve()
        if source == "local":
            if not p.exists():
                raise Fatal(2, f"inventory: not found: {p}")
            return [self._describe_path(p)]
        # dir
        if not p.is_dir():
            raise Fatal(2, f"inventory: --input is not a directory: {p}")

        include = getattr(self.args, "include_glob", None) or [
            "*.vmdk",
            "*.ova",
            "*.ovf",
            "*.vhd*",
            "*.tar*",
            "*.tgz",
        ]
        exclude = getattr(self.args, "exclude_glob", None) or ["*-flat.vmdk", "*.part", "*.tmp"]
        recursive = bool(getattr(self.args, "recursive", False))
        follow = bool(getattr(self.args, "follow_symlinks", False))
        max_items = int(getattr(self.args, "max_items", 0) or 0)

        paths: list[Path] = []
        it = p.rglob("*") if recursive else p.glob("*")
        for x in it:
            try:
                if x.is_dir():
                    continue
                if not follow and x.is_symlink():
                    continue
                if not any(x.match(g) for g in include):
                    continue
                if any(x.match(g) for g in exclude):
                    continue
                paths.append(x)
                if 0 < max_items <= len(paths):
                    break
            # a single unreadable/racy directory entry must not abort the whole scan
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        return [self._describe_path(x) for x in sorted(paths)]

    def _scan_esxi(self, out_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        host = getattr(self.args, "esxi_host", None)
        remote = getattr(self.args, "esxi_remote", None)
        if not host or not remote:
            raise Fatal(2, "inventory(esxi): require --esxi-host and --esxi-remote")

        fetch_dir = (
            Path(self.args.download_dir).expanduser().resolve()
            if getattr(self.args, "download_dir", None)
            else (out_root / "downloaded")
        )
        U.ensure_dir(fetch_dir)

        sshc = SSHClient(
            self.logger,
            SSHConfig(
                host=host,
                user=getattr(self.args, "esxi_user", "root"),
                port=int(getattr(self.args, "esxi_port", 22)),
                identity=getattr(self.args, "esxi_identity", None),
                ssh_opts=self._normalize_ssh_opt(getattr(self.args, "esxi_ssh_opt", None)) or [],
                sudo=False,
            ),
        )

        desc = Fetch.fetch_descriptor_and_extent(
            self.logger,
            sshc,
            remote,
            fetch_dir,
            bool(getattr(self.args, "esxi_fetch_all", False)),
        )

        item = self._describe_path(Path(desc).resolve())
        downloaded = [{"type": "vmdk_descriptor", "path": str(desc)}]
        return [item], downloaded

    def _describe_path(self, p: Path) -> dict[str, Any]:
        d: dict[str, Any] = {"path": str(p), "name": p.name, "type": self._classify(p)}
        try:
            st = p.stat()
            d["size_bytes"] = st.st_size
            d["size_human"] = U.human_bytes(st.st_size)
        except OSError:
            pass

        # VMDK extras (best-effort)
        if d["type"] == "vmdk":
            try:
                layout, extent = VMDK.guess_layout(self.logger, p)
                d["vmdk_layout"] = layout
                d["vmdk_extent"] = str(extent) if extent else None
            # best-effort VMDK introspection; inventory entry is still useful without it
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        return d

    def _classify(self, p: Path) -> str:
        s = p.name.lower()
        if s.endswith(".vmdk"):
            return "vmdk"
        if s.endswith(".ova"):
            return "ova"
        if s.endswith(".ovf"):
            return "ovf"
        if s.endswith(".vhd") or ".vhd." in s:
            return "vhd"
        if s.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz")):
            return "tarball"
        return "file"

    def _risk_checks(self, items: list[dict[str, Any]]) -> list[Risk]:
        risks: list[Risk] = []
        for it in items:
            t = it.get("type")
            if t == "vmdk":
                if it.get("vmdk_layout") == "descriptor" and not it.get("vmdk_extent"):
                    risks.append(
                        Risk(
                            "high", "VMDK_EXTENT_MISSING", f"VMDK descriptor has no extent: {it.get('path')}"
                        )
                    )
            if t in ("ova", "ovf", "tarball"):
                risks.append(
                    Risk("medium", "ARCHIVE_INPUT", f"Archive input requires extraction: {it.get('path')}")
                )
        return risks

    def _summarize(self, items: list[dict[str, Any]], risks: list[Risk]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        total_size = 0
        for it in items:
            counts[it.get("type", "unknown")] = counts.get(it.get("type", "unknown"), 0) + 1
            total_size += int(it.get("size_bytes", 0) or 0)

        sev_counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
        for r in risks:
            sev_counts[r.severity] = sev_counts.get(r.severity, 0) + 1

        return {
            "count": len(items),
            "by_type": counts,
            "total_size_bytes": total_size,
            "total_size_human": U.human_bytes(total_size),
            "risks": sev_counts,
        }

    def _to_markdown(self, inv: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append("# hyper2kvm inventory\n")
        lines.append(f"- Source: `{inv.get('source')}`")
        lines.append(f"- Output dir: `{inv.get('output_dir')}`")
        lines.append(f"- Inventory dir: `{inv.get('inventory_dir')}`\n")

        lines.append("## Summary\n")
        s = inv.get("summary", {})
        lines.append(f"- Items: **{s.get('count', 0)}**")
        lines.append(f"- Total size: **{s.get('total_size_human', 'n/a')}**")
        lines.append(f"- By type: `{s.get('by_type', {})}`")
        lines.append(f"- Risks: `{s.get('risks', {})}`\n")

        lines.append("## Items\n")
        for it in inv.get("items", []):
            lines.append(
                f"- `{it.get('type')}` **{it.get('name')}** — `{it.get('path')}` ({it.get('size_human', 'n/a')})"
            )

        lines.append("\n## Risks\n")
        rs = inv.get("risks", [])
        if not rs:
            lines.append("- None detected ✅")
        else:
            for r in rs:
                lines.append(f"- **{r.get('severity')}** `{r.get('code')}` — {r.get('message')}")

        lines.append("")
        return "\n".join(lines)

    def _maybe_fail(self, risks: list[Risk], fail_on: str) -> None:
        order = {"none": 999, "low": 0, "medium": 1, "high": 2}
        threshold = order.get(fail_on, 2)
        worst = -1
        for r in risks:
            worst = max(worst, order.get(r.severity, 0))
        if worst >= threshold and threshold != 999:
            raise Fatal(3, f"inventory: failing due to risk severity >= {fail_on}")

    @staticmethod
    def _normalize_ssh_opt(v) -> list[str] | None:
        return _normalize_ssh_opt_impl(v)
