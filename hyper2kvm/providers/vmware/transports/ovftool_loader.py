# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/transports/ovftool_loader.py

"""
OVF Tool and govc export operations for VMware
"""

import time
from pathlib import Path
from typing import Any

# OVF Tool client
try:
    from .ovftool_client import (
        OvfDeployOptions,
        OvfExportOptions,
        OvfToolError,
        deploy_ovf_or_ova,
        export_to_ova,
    )
except ImportError:  # pragma: no cover
    export_to_ova = None  # type: ignore
    deploy_ovf_or_ova = None  # type: ignore
    OvfExportOptions = None  # type: ignore
    OvfDeployOptions = None  # type: ignore
    OvfToolError = None  # type: ignore

# HTTP/HTTPS download client
# (shared VMwareError fallback resolution, centralized in utils/compat.py to
# avoid duplicating this try/except stub across vmware provider modules)
from hyper2kvm.providers.vmware.utils.compat import VMwareError
from hyper2kvm.providers.vmware.utils.utils import (
    ensure_output_dir as _ensure_output_dir,
    quote_inventory_path as _quote_inventory_path,
    safe_vm_name as _safe_vm_name,
)


def govc_export_ovf(client: Any, opt: Any) -> Path:
    """Export a VM to an OVF directory via govc."""
    g = client._govc()  # pylint: disable=protected-access  # tight internal coupling: split-module client helper
    if g is None:
        raise VMwareError("govc not available (or disabled); cannot run OVF export")

    out_base = _ensure_output_dir(opt.output_dir)
    out_dir = out_base / f"{_safe_vm_name(opt.vm_name)}.ovfdir"
    out_dir.mkdir(parents=True, exist_ok=True)

    g.export_ovf(
        vm=opt.vm_name,
        out_dir=str(out_dir),
        snapshot=opt.govc_export_snapshot,
        power_off=bool(opt.govc_export_power_off),
        disk_mode=opt.govc_export_disk_mode,
    )
    return out_dir


def govc_export_ova(client: Any, opt: Any) -> Path:
    """Export a VM to an OVA file via govc."""
    g = client._govc()  # pylint: disable=protected-access  # tight internal coupling: split-module client helper
    if g is None:
        raise VMwareError("govc not available (or disabled); cannot run OVA export")

    out_base = _ensure_output_dir(opt.output_dir)
    out_file = out_base / f"{_safe_vm_name(opt.vm_name)}.ova"

    g.export_ova(
        vm=opt.vm_name,
        out_file=str(out_file),
        snapshot=opt.govc_export_snapshot,
        power_off=bool(opt.govc_export_power_off),
        disk_mode=opt.govc_export_disk_mode,
    )
    return out_file


def _vm_inventory_path_under_vmfolder(client: Any, vm_obj: Any, dc_obj: Any) -> str:
    """
    Compute inventory path relative to Datacenter/vm folder, e.g.
      "<folder1>/<folder2>/<vmname>"

    This is what ovftool expects after ".../<dc_name>/vm/".
    """
    client._require_pyvmomi()  # pylint: disable=protected-access  # tight internal coupling: split-module client helper

    vm_folder = getattr(dc_obj, "vmFolder", None)
    if vm_folder is None:
        raise VMwareError("Datacenter has no vmFolder (unexpected)")

    parts: list[str] = []
    obj = vm_obj
    for _ in range(96):
        if obj is None:
            break
        name = getattr(obj, "name", None)
        if name:
            parts.append(str(name))
        parent = getattr(obj, "parent", None)
        if parent is None:
            break
        if parent == vm_folder:
            break
        obj = parent

    if not parts:
        # fallback: at least the VM name
        return str(getattr(vm_obj, "name", "") or "").strip() or "vm"

    parts = list(reversed(parts))
    return "/".join([p.strip("/") for p in parts if p.strip("/")])


def _build_ovftool_source_url(client: Any, vm_name: str) -> str:
    """
    Build a vi:// source URL for OVF Tool from VM object + inventory path.

    Format:
      vi://user:pass@host/<Datacenter>/vm/<folder...>/<vm>
    """
    vm_obj = client.get_vm_by_name(vm_name)
    if not vm_obj:
        raise VMwareError(f"VM not found: {vm_name}")

    dc_name = client.resolve_datacenter_for_vm(vm_name, "auto")
    dc_obj = client.get_datacenter_by_name(dc_name, refresh=False)
    if dc_obj is None:
        dc_obj = client.get_datacenter_by_name(dc_name, refresh=True)
    if dc_obj is None:
        raise VMwareError(f"Could not resolve datacenter object for dc={dc_name!r}")

    inv_rel = _vm_inventory_path_under_vmfolder(client, vm_obj, dc_obj)
    inv_rel_q = _quote_inventory_path(inv_rel)

    # NOTE: credential embedding is required by ovftool; do not log this URL verbatim.
    dc_q = _quote_inventory_path(dc_name)
    return f"vi://{client.user}:{client.password}@{client.host}/{dc_q}/vm/{inv_rel_q}"


def _ovftool_export_options(_client: Any, opt: Any) -> Any:
    if OvfExportOptions is None:
        raise VMwareError("OvfExportOptions not available (ovftool_client import failed)")
    return OvfExportOptions(
        no_ssl_verify=opt.ovftool_no_ssl_verify,
        thumbprint=opt.ovftool_thumbprint,
        accept_all_eulas=opt.ovftool_accept_all_eulas,
        quiet=opt.ovftool_quiet,
        verbose=opt.ovftool_verbose,
        overwrite=opt.ovftool_overwrite,
        disk_mode=opt.ovftool_disk_mode,
        retries=opt.ovftool_retries,
        retry_backoff_s=opt.ovftool_retry_backoff_s,
        extra_args=opt.ovftool_extra_args,
    )


def _ovftool_deploy_options(_client: Any, opt: Any, *, name: str) -> Any:
    if OvfDeployOptions is None:
        raise VMwareError("OvfDeployOptions not available (ovftool_client import failed)")
    return OvfDeployOptions(
        no_ssl_verify=opt.ovftool_no_ssl_verify,
        thumbprint=opt.ovftool_thumbprint,
        accept_all_eulas=opt.ovftool_accept_all_eulas,
        overwrite=opt.ovftool_overwrite,
        name=name,
        disk_mode=opt.ovftool_disk_mode,
        quiet=opt.ovftool_quiet,
        verbose=opt.ovftool_verbose,
        retries=opt.ovftool_retries,
        retry_backoff_s=opt.ovftool_retry_backoff_s,
        extra_args=opt.ovftool_extra_args,
    )


def ovftool_export_vm(client: Any, opt: Any) -> Path:
    """
    Export VM using OVF Tool (to OVA).
    """
    if export_to_ova is None:
        raise VMwareError("OVF Tool client not available. Ensure ovftool_client.py is importable.")

    out_dir = _ensure_output_dir(opt.output_dir)
    ova_path = out_dir / f"{_safe_vm_name(opt.vm_name)}.ova"
    source_url = _build_ovftool_source_url(client, opt.vm_name)
    options = _ovftool_export_options(client, opt)

    client.logger.info("Exporting VM %s to %s using OVF Tool...", opt.vm_name, ova_path)
    t0 = time.time()
    try:
        export_to_ova(
            paths=client._ovftool(),  # pylint: disable=protected-access  # tight internal coupling: client helper
            source=source_url,
            ova_path=ova_path,
            options=options,
            log_prefix="ovftool",
        )
    except OvfToolError as e:
        raise VMwareError(f"OVF Tool export failed: {e}") from e

    client.logger.info("OVF Tool export completed in %.1fs", time.time() - t0)
    return ova_path


def ovftool_deploy_ova(client: Any, source_ova: Path, opt: Any) -> None:
    """
    Deploy OVA/OVF using OVF Tool.
    """
    if deploy_ovf_or_ova is None:
        raise VMwareError("OVF Tool client not available. Ensure ovftool_client.py is importable.")
    if not source_ova.exists():
        raise VMwareError(f"Source OVA/OVF not found: {source_ova}")

    dc_name = client.resolve_datacenter_for_vm(opt.vm_name, opt.datacenter)
    dc_q = _quote_inventory_path(dc_name)

    # Target can be a datacenter/folder/resource pool; keep conservative for now.
    target_url = f"vi://{client.user}:{client.password}@{client.host}/{dc_q}"

    options = _ovftool_deploy_options(client, opt, name=opt.vm_name)

    client.logger.info("Deploying %s to vSphere using OVF Tool...", source_ova)
    t0 = time.time()
    try:
        deploy_ovf_or_ova(
            paths=client._ovftool(),  # pylint: disable=protected-access  # tight internal coupling: client helper
            source_ovf_or_ova=source_ova,
            target_vi=target_url,
            options=options,
            log_prefix="ovftool",
        )
    except OvfToolError as e:
        raise VMwareError(f"OVF Tool deployment failed: {e}") from e

    client.logger.info("OVF Tool deployment completed in %.1fs", time.time() - t0)
