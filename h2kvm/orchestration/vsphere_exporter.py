# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/orchestrator/vsphere_exporter.py
"""
vSphere VM export handler.
Supports direct export and download-only modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from h2kvm.core.cred import resolve_vsphere_creds
from h2kvm.core.error_helpers import vm_not_found_error
from h2kvm.core.exceptions import Fatal, VMwareError
from h2kvm.core.logger import Log
from h2kvm.core.utils import U

if TYPE_CHECKING:
    import argparse
    import logging

# Conditional imports
try:
    from h2kvm.providers.vmware.clients.client import ExportOptions, VMwareClient

    VSPHERE_EXPORT_AVAILABLE = True
except ImportError:
    VMwareClient = None  # type: ignore
    ExportOptions = None  # type: ignore
    VSPHERE_EXPORT_AVAILABLE = False

try:
    from h2kvm.providers.vmware.clients.client import PYVMOMI_AVAILABLE
except ImportError:
    PYVMOMI_AVAILABLE = False


_DISK_SUFFIXES = (".vmdk", ".qcow2", ".raw", ".img", ".vdi", ".vhd", ".vhdx")
# Extents that a VMDK descriptor points at; the descriptor is the disk, not these.
_VMDK_EXTENT_SUFFIXES = ("-flat.vmdk", "-delta.vmdk", "-sesparse.vmdk", "-ctk.vmdk")


def find_exported_disks(logger: logging.Logger, root: Path) -> list[Path]:
    """Find the disk images an export left under ``root``.

    ``govc export.ovf`` writes ``<vm>.ovfdir/<vm>/*.vmdk``, so the search is
    recursive. When the export is only an OVA there is no plain disk to find,
    so the OVA is extracted and its disks are returned instead of the archive.
    """
    root = Path(root)
    disks = sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in _DISK_SUFFIXES
        and not p.name.lower().endswith(_VMDK_EXTENT_SUFFIXES)
        and p.stat().st_size > 0
    )
    if disks:
        return disks

    # pylint: disable-next=import-outside-toplevel  # lazy import: keeps the exporter import light
    from h2kvm.converters.extractors.ovf import OVF

    for ova in sorted(root.rglob("*.ova")):
        try:
            disks.extend(OVF.extract_ova(logger, ova, ova.with_suffix(".extracted")))
        # pylint: disable-next=broad-exception-caught  # one bad archive must not hide the other exports
        except Exception as e:
            logger.warning("Could not extract disks from %s: %s", ova, e)
    return disks


class VsphereExporter:
    """
    Handles vSphere VM export operations.

    Responsibilities:
    - vSphere VM identification and credential resolution
    - Direct export (govc export.ovf / export.ova, or HTTPS /folder)
    - download-only mode
    - Snapshot management
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args

    def is_export_enabled(self) -> bool:
        """Check if vSphere export is enabled."""
        enabled = bool(getattr(self.args, "vs_export", False))
        Log.trace(self.logger, "🌐 _vsphere_export_enabled: %s", enabled)
        return enabled

    def get_vm_names(self) -> list[str]:
        """Extract VM names from args (supports multiple sources)."""
        vms: list[str] = []
        if getattr(self.args, "vs_vm", None):
            vms = [str(self.args.vs_vm)]
        elif getattr(self.args, "vs_vms", None):
            v = self.args.vs_vms
            if isinstance(v, (list, tuple)):
                vms = [str(x) for x in v]
            else:
                vms = [s.strip() for s in str(v).split(",") if s.strip()]
        elif getattr(self.args, "vm_name", None):
            vms = [str(self.args.vm_name)]
        out = [x for x in (n.strip() for n in vms) if x]
        Log.trace(self.logger, "🧾 _vsphere_vm_names: %s", out)
        return out

    # resolves many independent CLI/config knobs (transport, snapshot options,
    # output format) before driving the per-VM export loop;
    # splitting it up would obscure how those knobs feed into ExportOptions
    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def export_many_sync(self, out_root: Path) -> list[Path]:
        """
        SYNC vSphere export path.

        Policy (download-first):
          - If vs_download_only:true => export_mode="download_only"
          - Else => export_mode="export" (direct export)

        Returns:
            List of exported disk image paths
        """
        Log.step(self.logger, "vSphere export (sync) initializing…")
        Log.trace(
            self.logger,
            "🌐 vSphere export: out_root=%s VSPHERE_EXPORT_AVAILABLE=%s",
            out_root,
            VSPHERE_EXPORT_AVAILABLE,
        )

        if not VSPHERE_EXPORT_AVAILABLE:
            raise Fatal(
                2,
                "vSphere export not available — the VMwareClient module failed to import.\n"
                "Install the required dependencies:\n"
                "  pip install pyvmomi requests\n",
            )

        if not PYVMOMI_AVAILABLE:
            raise Fatal(
                2,
                "pyvmomi is not installed. It is required for vSphere VM export.\n"
                "Install with: pip install pyvmomi\n"
                "Or if using govc-only mode: h2kvmctl --cmd vsphere --vs-action export_vm",
            )

        vms = self.get_vm_names()
        if not vms:
            raise Fatal(
                2,
                "No vSphere VM name(s) provided.\n"
                "Specify the VM to export with one of:\n"
                "  --vs-vm <vm-name>       Single VM\n"
                "  --vs-vms <vm1>,<vm2>    Multiple VMs\n"
                "  --vm-name <vm-name>     Alternative flag",
            )

        # Resolve creds using shared core/cred.py
        try:
            creds = resolve_vsphere_creds(vars(self.args))
        except Exception as e:
            raise Fatal(
                2,
                f"Missing or invalid vSphere credentials: {e}\n"
                "Provide credentials via:\n"
                "  --vs-host <vcenter-host> --vs-user <user> --vs-password <pass>\n"
                "  Or environment variables: GOVC_URL, GOVC_USERNAME, GOVC_PASSWORD\n"
                "  Or config file: vs_host, vs_user, vs_password",
            ) from e

        # Accept both vs_* and vc_* knobs
        port = int(getattr(self.args, "vs_port", None) or getattr(self.args, "vc_port", None) or 443)
        vs_insecure = getattr(self.args, "vs_insecure", None)
        insecure = bool(vs_insecure if vs_insecure is not None else getattr(self.args, "vc_insecure", False))

        timeout = getattr(self.args, "vs_timeout", None) or getattr(self.args, "vc_timeout", None)
        timeout_f = float(timeout) if timeout is not None else None

        datacenter = str(
            getattr(self.args, "vs_datacenter", None) or getattr(self.args, "vc_datacenter", None) or "auto"
        )
        compute = str(getattr(self.args, "vs_compute", None) or "auto")

        snapshot_moref = getattr(self.args, "vs_snapshot_moref", None)
        create_snapshot = bool(getattr(self.args, "vs_create_snapshot", False))

        extra_args = tuple(getattr(self.args, "vs_export_extra_args", []) or ())
        out_format = str(getattr(self.args, "out_format", "qcow2"))

        download_only = bool(getattr(self.args, "vs_download_only", False))

        Log.trace(
            self.logger,
            "🧷 vSphere export knobs: host=%s port=%s insecure=%s timeout=%s dc=%s compute=%s "
            "download_only=%s",
            getattr(creds, "host", None),
            port,
            insecure,
            timeout_f,
            datacenter,
            compute,
            download_only,
        )

        out_images: list[Path] = []
        failures: list[str] = []

        # SYNC context manager (no async-with)
        with VMwareClient(  # type: ignore[misc]
            self.logger,
            host=str(creds.host),
            user=str(creds.user),
            password=str(creds.password),
            port=port,
            insecure=insecure,
            timeout=timeout_f,
        ) as vc:
            Log.ok(self.logger, "vSphere connection established")
            for vm_name in vms:
                try:
                    Log.step(self.logger, f"Exporting VM: {vm_name}")
                    snap_moref = str(snapshot_moref) if snapshot_moref else None
                    if create_snapshot:
                        Log.trace(self.logger, "📸 create_snapshot enabled for %s", vm_name)
                        vm_obj = vc.get_vm_by_name(vm_name)
                        if not vm_obj:
                            raise VMwareError(
                                code=50,
                                msg=vm_not_found_error(vm_name, vcenter=str(creds.host)),
                            )
                        # NOTE: VMwareClient does not yet implement create_snapshot()/
                        # snapshot_moref() (same gap as VsphereCommands.create_snapshot()
                        # in providers/vmware/vsphere/command.py) -- a known missing
                        # feature, not guessed at here.
                        snap_obj = vc.create_snapshot(  # pylint: disable=no-member
                            vm_obj, name=f"h2kvm-{vm_name}", quiesce=True, memory=False
                        )
                        snap_moref = vc.snapshot_moref(snap_obj)  # pylint: disable=no-member
                        self.logger.info("📸 Snapshot created: %s (moref=%s)", vm_name, snap_moref)

                    job_dir = out_root / "vsphere-export" / vm_name
                    U.ensure_dir(job_dir)

                    export_mode = "download_only" if download_only else "ovf_export"

                    Log.trace(self.logger, "🧭 export_mode=%s job_dir=%s", export_mode, job_dir)

                    opt = ExportOptions(  # type: ignore[misc]
                        vm_name=vm_name,
                        export_mode=export_mode,
                        datacenter=datacenter,
                        compute=compute,
                        no_verify=bool(getattr(self.args, "vs_no_verify", False)),
                        output_dir=job_dir,
                        output_format=out_format,
                        extra_args=extra_args,
                        govc_export_snapshot=snap_moref,
                    )

                    # This must be SYNC in VMwareClient implementation
                    out_path = vc.export_vm(opt)  # type: ignore[attr-defined]
                    Log.trace(self.logger, "📤 export_vm returned: %r", out_path)

                    if export_mode == "download_only":
                        self.logger.info("⬇️ vSphere download-only OK: %s -> %s", vm_name, out_path)
                        continue

                    # export_mode == "ovf_export": discover artifacts
                    imgs = find_exported_disks(self.logger, job_dir)
                    Log.trace(self.logger, "🔎 vSphere discover: %s -> %d", job_dir, len(imgs))
                    if not imgs:
                        self.logger.warning(
                            "vSphere export produced no outputs for %s in %s", vm_name, job_dir
                        )
                    else:
                        self.logger.info("✅ vSphere export outputs for %s: %d file(s)", vm_name, len(imgs))
                    out_images.extend(imgs)

                # one VM's export failure must not abort exporting the rest of the batch
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self.logger.exception(
                        "vSphere export failed for VM '%s': %s\n"
                        "    Check vCenter connectivity, VM permissions, and available disk space.\n"
                        "    Re-run with --verbose for detailed error information.",
                        vm_name,
                        e,
                    )
                    self.logger.debug("vSphere export exception for %s", vm_name, exc_info=True)
                    failures.append(f"{vm_name}: {e}")

        # De-dup while preserving order
        seen: set[str] = set()
        uniq: list[Path] = []
        for p in out_images:
            sp = str(p)
            if sp not in seen:
                seen.add(sp)
                uniq.append(p)

        if failures:
            self.logger.warning("Some vSphere export jobs failed:")
            for f in failures:
                self.logger.warning(" - %s", f)

        Log.trace(self.logger, "📦 vSphere export: uniq_out_images=%d", len(uniq))
        return uniq
