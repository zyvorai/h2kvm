# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/transports/vddk_loader.py
"""
VDDK disk download orchestration for VMware
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Import VMwareError
try:
    from .http_client import VMwareError
except ImportError:  # pragma: no cover
    try:
        from ....core.exceptions import VMwareError  # type: ignore
    except ImportError:  # pragma: no cover

        class VMwareError(Exception):  # type: ignore
            """Fallback VMware error type when neither http_client nor core.exceptions is importable."""


# Import ExportOptions
try:
    from h2kvm.providers.vmware.clients.client import ExportOptions, _safe_vm_name
except ImportError:  # pragma: no cover
    ExportOptions = None  # type: ignore
    _safe_vm_name = None  # type: ignore

# Import pyvmomi (vim)
# (shared availability probe, centralized in utils/compat.py to avoid
# duplicating this try/except stub across vmware provider modules)
from h2kvm.providers.vmware.utils.compat import vim

# ✅ VDDK client (ALL heavy logic in vddk_client.py)
try:
    from .vddk_client import VDDKConnectionSpec, VDDKESXClient  # type: ignore

    VDDK_CLIENT_AVAILABLE = True
except ImportError:  # pragma: no cover
    VDDKConnectionSpec = None  # type: ignore
    VDDKESXClient = None  # type: ignore
    VDDK_CLIENT_AVAILABLE = False


def _require_vddk_client() -> None:
    if not VDDK_CLIENT_AVAILABLE:
        raise VMwareError(
            "VDDK raw download requested but vddk_client is not importable. "
            "Ensure h2kvm/vsphere/vddk_client.py exists and imports cleanly."
        )


def vm_disks(_client: Any, vm_obj: Any) -> list[Any]:
    """Return the list of VirtualDisk devices attached to ``vm_obj``."""
    disks: list[Any] = []
    devices = getattr(getattr(getattr(vm_obj, "config", None), "hardware", None), "device", []) or []
    for dev in devices:
        if isinstance(dev, vim.vm.device.VirtualDisk):  # type: ignore[attr-defined]
            disks.append(dev)
    return disks


def check_independent_disks(client: Any, vm_obj: Any) -> list[dict[str, str]]:
    """Detect disks with 'independent' mode that VDDK >= 7.0 cannot export.

    Returns list of dicts with label, fileName, diskMode for each independent disk.
    """
    independent: list[dict[str, str]] = []
    for disk in vm_disks(client, vm_obj):
        backing = getattr(disk, "backing", None)
        if backing is None:
            continue
        disk_mode = getattr(backing, "diskMode", "") or ""
        if "independent" in disk_mode.lower():
            label = getattr(getattr(disk, "deviceInfo", None), "label", "unknown") or "unknown"
            fn = getattr(backing, "fileName", "unknown") or "unknown"
            independent.append({"label": label, "fileName": fn, "diskMode": disk_mode})
    return independent


def select_disk(client: Any, vm_obj: Any, label_or_index: str | None) -> Any:
    """Select a VM disk by index or by (case-insensitive substring) label."""
    disks = vm_disks(client, vm_obj)
    if not disks:
        raise VMwareError(
            "No virtual disks found on VM. The VM may have no hard disks attached, "
            "or the disk configuration is not accessible. Check the VM's hardware "
            "settings in vSphere to verify it has virtual disks."
        )
    if label_or_index is None:
        return disks[0]
    s = str(label_or_index).strip()
    if s.isdigit():
        idx = int(s)
        if idx < 0 or idx >= len(disks):
            raise VMwareError(f"Disk index out of range: {idx} (found {len(disks)})")
        return disks[idx]
    sl = s.lower()
    for d in disks:
        label = getattr(getattr(d, "deviceInfo", None), "label", "") or ""
        if sl in str(label).lower():
            return d
    available = []
    for d in disks:
        label = getattr(getattr(d, "deviceInfo", None), "label", "") or ""
        if label:
            available.append(label)
    available_str = ", ".join(available) if available else "none detected"
    raise VMwareError(
        f"No disk matching label '{s}'. Available disks: {available_str}\n"
        "Specify a disk by label (e.g., 'Hard disk 1') or index (e.g., 0, 1)."
    )


def _vm_disk_backing_filename(_client: Any, disk_obj: Any) -> str:
    backing = getattr(disk_obj, "backing", None)
    fn = getattr(backing, "fileName", None) if backing else None
    if not fn:
        raise VMwareError(
            "Selected disk has no backing file path (backing.fileName is empty). "
            "This can happen with RDM (Raw Device Mapping) disks or disks that are not "
            "stored on a datastore. VDDK cannot download RDM disks directly."
        )
    return str(fn)


def _resolve_esx_host_for_vm(client: Any, vm_obj: Any) -> str:
    host_obj = client._vm_runtime_host(vm_obj)  # pylint: disable=protected-access  # tight internal coupling within the vmware provider package
    if host_obj is None:
        raise VMwareError(
            "VM has no runtime.host — cannot determine which ESXi host runs this VM. "
            "The VM may be unregistered or in an error state. "
            "Check the VM status in vSphere and ensure it is registered on a host."
        )
    name = str(getattr(host_obj, "name", "") or "").strip()
    if not name:
        raise VMwareError(
            "Could not resolve ESXi host name for the VM's runtime host. "
            "The ESXi host may have been disconnected from vCenter. "
            "Check vCenter for disconnected hosts and re-add if needed."
        )
    return name


def _default_vddk_download_path(client: Any, opt: ExportOptions, *, disk_index: int) -> Path:
    out_dir = client._ensure_output_dir(opt.output_dir)  # pylint: disable=protected-access  # tight internal coupling within the vmware provider package
    return out_dir / f"{_safe_vm_name(opt.vm_name)}-disk{disk_index}.vmdk"


def vddk_download_disk(client: Any, opt: ExportOptions) -> Path:
    """
    export_mode="vddk_download" (EXPERIMENTAL)
      - control-plane: pyvmomi finds ESXi host + disk backing path
      - data-plane: vddk_client.VDDKESXClient reads and writes local file
    """
    _require_vddk_client()
    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

    vm_obj = client.get_vm_by_name(opt.vm_name)
    if vm_obj is None:
        raise VMwareError(f"VM not found: {opt.vm_name!r}")

    # Pre-flight: detect independent disks that VDDK >= 7.0 cannot open
    indep = check_independent_disks(client, vm_obj)
    if indep:
        labels = ", ".join(f"{d['label']} ({d['diskMode']})" for d in indep)
        raise VMwareError(
            f"VM {opt.vm_name!r} has {len(indep)} disk(s) with 'independent' mode: {labels}. "
            "VDDK >= 7.0 cannot export independent disks. "
            "Change disk mode to 'dependent' in vSphere before migration, "
            "or use govc/OVF export instead of VDDK."
        )

    disk_obj = select_disk(client, vm_obj, opt.vddk_download_disk)
    try:
        disks = vm_disks(client, vm_obj)
        disk_index = disks.index(disk_obj)
    except ValueError:
        disk_index = 0

    remote_vmdk = _vm_disk_backing_filename(client, disk_obj)  # "[ds] folder/disk.vmdk"
    esx_host = _resolve_esx_host_for_vm(client, vm_obj)

    local_path = (
        Path(opt.vddk_download_output)
        if opt.vddk_download_output
        else _default_vddk_download_path(client, opt, disk_index=disk_index)
    )

    spec = VDDKConnectionSpec(  # type: ignore[misc]
        host=esx_host,
        user=client.user,
        password=client.password,
        port=443,
        vddk_libdir=Path(opt.vddk_libdir) if opt.vddk_libdir else None,
        transport_modes=opt.vddk_transports or "nbdssl:nbd",
        thumbprint=opt.vddk_thumbprint,
        insecure=bool(opt.no_verify),
    )

    c = VDDKESXClient(client.logger, spec)  # type: ignore[misc]

    def _progress(done: int, total: int, pct: float) -> None:
        le = int(opt.vddk_download_log_every_bytes or 0)
        if total and done and le > 0:
            if done % le < int(opt.vddk_download_sectors_per_read or 2048) * 512:
                client.logger.info(
                    "VDDK download progress: %.1f GiB / %.1f GiB (%.1f%%)",
                    done / (1024**3),
                    total / (1024**3),
                    pct,
                )

    client.logger.warning("VDDK raw download is EXPERIMENTAL (explicit mode requested).")
    client.logger.info(
        "VDDK download: vm=%s disk=%s esx=%s remote=%s -> %s",
        opt.vm_name,
        opt.vddk_download_disk or str(disk_index),
        esx_host,
        remote_vmdk,
        local_path,
    )

    c.connect()
    try:
        out = c.download_vmdk(
            remote_vmdk,
            Path(local_path),
            sectors_per_read=int(opt.vddk_download_sectors_per_read or 2048),
            progress=_progress,
            log_every_bytes=int(opt.vddk_download_log_every_bytes or 0),
        )
        return Path(out)
    finally:
        c.disconnect()
