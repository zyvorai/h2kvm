# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/vsphere/command.py
"""
vSphere command orchestration for hyper2kvm.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyper2kvm.providers.vmware.clients.client import ExportOptions, VMwareClient

from ....core.exceptions import VMwareError

# Import from split modules
from .errors import (
    VsphereExitCode,
    _classify_exit_code,
)
from .govc import (
    GovmomiCLI,
    _arg_any,
    _Emitter,
    _merged_cfg,
    _p,
    _prefer_govc,
    _require,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# Snapshot helpers (normalize snapshot object type)


def _find_snapshot_tree_by_name(vm_obj: Any, name: str) -> Any | None:
    target = (name or "").strip()
    if not target:
        return None

    snap = getattr(vm_obj, "snapshot", None)
    roots = getattr(snap, "rootSnapshotList", None) if snap else None
    if not roots:
        return None

    stack = list(roots)
    while stack:
        node = stack.pop()
        if str(getattr(node, "name", "") or "") == target:
            return node
        kids = getattr(node, "childSnapshotList", None) or []
        stack.extend(list(kids))
    return None


def _snapshot_ref_from_tree(node: Any) -> Any:
    snap = getattr(node, "snapshot", None)
    return snap if snap is not None else node


class VsphereCommands:
    """Implements the `vsphere` CLI subcommands against a connected VMwareClient."""

    def __init__(self, client: VMwareClient, args: Any):
        self.client = client
        self.args = args
        self.logger = client.logger
        self.emit = _Emitter(args, self.logger)

    # ---- shared helpers ----

    def _vm_or_raise(self, vm_name: str) -> Any:
        vm = self.client.get_vm_by_name(vm_name)
        if vm is None:
            raise VMwareError(f"VM not found: {vm_name!r}")
        return vm

    def _govc(self) -> GovmomiCLI | None:
        return _prefer_govc(self.args, self.logger)

    def _govc_try(self, op: Callable[[GovmomiCLI], Any], *, warn: str) -> tuple[bool, Any]:
        g = self._govc()
        if not g:
            return (False, None)
        try:
            return (True, op(g))
        # govc call failed for any reason; fall back to the pyvmomi path
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.warning("%s: %s", warn, e)
            return (False, None)

    def _vm_summary_payload(self, vm: Any) -> dict[str, Any]:
        s = getattr(vm, "summary", None)
        cfg = getattr(s, "config", None) if s else None
        runtime = getattr(s, "runtime", None) if s else None
        guest = getattr(s, "guest", None) if s else None

        return {
            "name": getattr(vm, "name", None),
            "moId": getattr(vm, "_moId", None),
            "uuid": getattr(cfg, "uuid", None),
            "instanceUuid": getattr(cfg, "instanceUuid", None),
            "powerState": str(getattr(runtime, "powerState", None)),
            "guestFullName": getattr(guest, "guestFullName", None),
            "vmPathName": getattr(cfg, "vmPathName", None),
            "datacenter": self.client.vm_datacenter_name(vm),
            "esx_host": getattr(getattr(getattr(vm, "runtime", None), "host", None), "name", None),
        }

    def _disk_payload(self, device: Any, index: int) -> dict[str, Any]:
        label = getattr(getattr(device, "deviceInfo", None), "label", None)
        key = getattr(device, "key", None)
        cap = getattr(device, "capacityInKB", None)
        backing = getattr(device, "backing", None)
        fname = getattr(backing, "fileName", None) if backing else None
        return {
            "index": index,
            "label": str(label) if label else None,
            "device_key": int(key) if key is not None else None,
            "capacity_kb": int(cap) if cap is not None else None,
            "backing_file": str(fname) if fname else None,
        }

    def _selected_disk_payload(self, vm_name: str, selector: Any, device: Any) -> dict[str, Any]:
        label = getattr(getattr(device, "deviceInfo", None), "label", None)
        key = getattr(device, "key", None)
        backing = getattr(device, "backing", None)
        fname = getattr(backing, "fileName", None) if backing else None
        return {
            "vm": vm_name,
            "selector": selector,
            "label": str(label) if label else None,
            "device_key": int(key) if key is not None else None,
            "backing_file": str(fname) if fname else None,
        }

    def _resolve_snapshot_ref(self, vm: Any, snapshot_name: str) -> Any:
        node = _find_snapshot_tree_by_name(vm, snapshot_name)
        if node is None:
            raise VMwareError(f"Snapshot not found by name: {snapshot_name!r}")
        return _snapshot_ref_from_tree(node)

    # ---- actions ----

    def list_vm_names(self) -> Any:
        """List VM names visible to this vCenter/ESXi connection (govc, falling back to pyvmomi)."""
        used, names = self._govc_try(
            lambda g: g.list_vm_names(),
            warn="govc list_vm_names failed; falling back to pyvmomi",
        )
        provider = "govc" if used else "pyvmomi"
        if not used:
            names = self.client.list_vm_names()

        payload = {"vms": names, "provider": provider}
        self.emit.emit(payload, human=names)
        return names

    def get_vm_by_name(self) -> Any:
        """Look up a VM by name and emit its summary payload."""
        name = _require(self.args, "name")
        vm = self._vm_or_raise(name)
        out = self._vm_summary_payload(vm)
        self.emit.emit(out)
        return out

    def vm_disks(self) -> Any:
        """List the virtual disks attached to a VM."""
        vm_name = _require(self.args, "vm_name")
        vm = self._vm_or_raise(vm_name)
        disks = self.client.vm_disks(vm)
        out = [self._disk_payload(d, i) for i, d in enumerate(disks)]
        payload = {"vm": vm_name, "disks": out}
        self.emit.emit(payload)
        return out

    def select_disk(self) -> Any:
        """Resolve a single disk on a VM by label or index and emit its details."""
        vm_name = _require(self.args, "vm_name")
        selector = getattr(self.args, "label_or_index", None)
        vm = self._vm_or_raise(vm_name)
        d = self.client.select_disk(vm, selector)
        out = self._selected_disk_payload(vm_name, selector, d)
        self.emit.emit(out)
        return out

    def download_datastore_file(self) -> Any:
        """Download a single file from a datastore path (govc, falling back to pyvmomi HTTP)."""
        datastore = _require(self.args, "datastore")
        ds_path = _require(self.args, "ds_path")
        local_path = Path(_require(self.args, "local_path")).expanduser()
        chunk_size = int(getattr(self.args, "chunk_size", 1024 * 1024) or 1024 * 1024)
        dc_name = getattr(self.args, "dc_name", None)

        used, _ = self._govc_try(
            lambda g: g.download_datastore_file(datastore=datastore, ds_path=ds_path, local_path=local_path),
            warn="govc download_datastore_file failed; falling back to pyvmomi",
        )
        if used:
            out = {"ok": True, "local_path": str(local_path), "provider": "govc"}
            self.emit.emit(out, human_msg=str(local_path))
            return out

        self.client.download_datastore_file(
            datastore=datastore,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            chunk_size=chunk_size,
        )
        out = {"ok": True, "local_path": str(local_path), "provider": "pyvmomi"}
        self.emit.emit(out, human_msg=str(local_path))
        return out

    def datastore_ls(self) -> Any:
        """List files in a datastore directory (requires govc)."""
        datastore = _require(self.args, "datastore")
        ds_dir = _require(self.args, "ds_dir")

        govc = self._govc()
        if not govc:
            raise VMwareError("datastore_ls requires govc (install govc or disable this action)")

        files = govc.datastore_ls_json(datastore=datastore, ds_dir=ds_dir)
        names = govc._extract_names_from_ls_json(files)  # pylint: disable=protected-access  # same-package internal helper on GovmomiCLI

        out = {"ok": True, "provider": "govc", "datastore": datastore, "ds_dir": ds_dir, "files": files}
        self.emit.emit(out, human=names)
        return out

    def download_datastore_dir(self) -> Any:
        """Download a filtered set of files from a datastore directory (requires govc)."""
        datastore = _require(self.args, "datastore")
        ds_dir = _require(self.args, "ds_dir")
        local_dir = Path(_require(self.args, "local_dir")).expanduser()

        include_globs = tuple(getattr(self.args, "include_glob", None) or []) or ("*",)
        exclude_globs = tuple(getattr(self.args, "exclude_glob", None) or []) or ()
        max_files = int(getattr(self.args, "max_files", 5000) or 5000)

        govc = self._govc()
        if not govc:
            raise VMwareError("download_datastore_dir requires govc (install govc or disable this action)")

        res = govc.download_datastore_dir(
            datastore=datastore,
            ds_dir=ds_dir,
            local_dir=local_dir,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            max_files=max_files,
        )
        self.emit.emit(res, human=res.get("files") or [])
        return res

    def create_snapshot(self) -> Any:
        """Create a VM snapshot."""
        vm_name = _require(self.args, "vm_name")
        snap_name = _require(self.args, "name")
        quiesce = bool(getattr(self.args, "quiesce", True))
        memory = bool(getattr(self.args, "memory", False))
        description = getattr(self.args, "description", "Created by hyper2kvm") or "Created by hyper2kvm"

        vm = self._vm_or_raise(vm_name)
        snap = self.client.create_snapshot(
            vm, snap_name, quiesce=quiesce, memory=memory, description=description
        )

        out = {
            "ok": True,
            "vm": vm_name,
            "snapshot_name": snap_name,
            "snapshot_moref": self.client.snapshot_moref(snap),
        }
        self.emit.emit(out)
        return out

    def enable_cbt(self) -> Any:
        """Enable Changed Block Tracking (CBT) on a VM."""
        vm_name = _require(self.args, "vm_name")
        vm = self._vm_or_raise(vm_name)

        self.client.enable_cbt(vm)
        out = {"ok": True, "vm": vm_name, "cbt_enabled": True}
        self.emit.emit(out)
        return out

    def query_changed_disk_areas(self) -> Any:
        """Query CBT changed disk areas for a disk since a given change ID."""
        vm_name = _require(self.args, "vm_name")
        snapshot_name = _require(self.args, "snapshot_name")
        start_offset = int(getattr(self.args, "start_offset", 0) or 0)
        change_id = str(getattr(self.args, "change_id", "*") or "*")

        device_key = getattr(self.args, "device_key", None)
        disk_sel = getattr(self.args, "disk", None)

        vm = self._vm_or_raise(vm_name)
        snapshot_ref = self._resolve_snapshot_ref(vm, snapshot_name)

        if device_key is None:
            d = self.client.select_disk(vm, disk_sel)
            device_key = int(getattr(d, "key", 0) or 0)
            if not device_key:
                raise VMwareError("Could not resolve device_key from selected disk")

        r = self.client.query_changed_disk_areas(
            vm,
            snapshot=snapshot_ref,
            device_key=int(device_key),
            start_offset=start_offset,
            change_id=change_id,
        )

        out = {
            "vm": vm_name,
            "snapshot": snapshot_name,
            "device_key": int(device_key),
            "start_offset": start_offset,
            "change_id": change_id,
            "changedArea_count": len(getattr(r, "changedArea", []) or []),
            "length": int(getattr(r, "length", 0) or 0),
        }
        self.emit.emit(out)
        return out

    def download_vm_disk(self) -> Any:
        """Download a VM's disk file directly from its datastore (govc, falling back to pyvmomi)."""
        vm_name = _require(self.args, "vm_name")
        disk_sel = getattr(self.args, "disk", None)
        local_path = Path(_require(self.args, "local_path")).expanduser()
        chunk_size = int(getattr(self.args, "chunk_size", 1024 * 1024) or 1024 * 1024)

        vm = self._vm_or_raise(vm_name)
        d = self.client.select_disk(vm, disk_sel)

        # usually "[datastore] folder/file.vmdk"
        backing = self.client._vm_disk_backing_filename(d)  # pylint: disable=protected-access  # same-package internal helper on VMwareClient
        ds_name, rel_path = self.client.parse_backing_filename(backing)

        used, _ = self._govc_try(
            lambda g: g.download_datastore_file(datastore=ds_name, ds_path=rel_path, local_path=local_path),
            warn="govc download_vm_disk failed; falling back to pyvmomi",
        )
        if used:
            out = {
                "ok": True,
                "vm": vm_name,
                "disk": disk_sel,
                "remote": backing,
                "local_path": str(local_path),
                "provider": "govc",
            }
            self.emit.emit(out, human_msg=str(local_path))
            return out

        dc = self.client.resolve_datacenter_for_vm(vm_name, getattr(self.args, "dc_name", None))
        self.client.download_datastore_file(
            datastore=ds_name,
            ds_path=rel_path,
            local_path=local_path,
            dc_name=dc,
            chunk_size=chunk_size,
        )

        out = {
            "ok": True,
            "vm": vm_name,
            "disk": disk_sel,
            "remote": backing,
            "local_path": str(local_path),
            "provider": "pyvmomi",
        }
        self.emit.emit(out, human_msg=str(local_path))
        return out

    def cbt_sync(self) -> Any:
        """
        Scaffold: enable CBT + snapshot + one-shot QueryChangedDiskAreas summary.
        (Real delta patching requires VDDK/NBD reads + applying extents into the base image.)
        """
        vm_name = _require(self.args, "vm_name")
        disk_sel = getattr(self.args, "disk", None)
        local_path = Path(_require(self.args, "local_path")).expanduser()
        enable = bool(getattr(self.args, "enable_cbt", False))
        snapshot_name = getattr(self.args, "snapshot_name", "hyper2kvm-cbt") or "hyper2kvm-cbt"
        change_id = str(getattr(self.args, "change_id", "*") or "*")

        vm = self._vm_or_raise(vm_name)

        if enable:
            self.client.enable_cbt(vm)

        snap = self.client.create_snapshot(vm, snapshot_name, quiesce=True, memory=False)

        d = self.client.select_disk(vm, disk_sel)
        device_key = int(getattr(d, "key", 0) or 0)
        if not device_key:
            raise VMwareError("Could not resolve device_key for selected disk")

        # base pull so you at least have a consistent local artifact
        self.download_vm_disk_with(vm_name=vm_name, disk_sel=disk_sel, local_path=local_path)

        r = self.client.query_changed_disk_areas(
            vm,
            snapshot=snap,
            device_key=device_key,
            start_offset=0,
            change_id=change_id,
        )

        out = {
            "ok": True,
            "vm": vm_name,
            "disk": disk_sel,
            "snapshot_moref": self.client.snapshot_moref(snap),
            "device_key": device_key,
            "change_id": change_id,
            "changedArea_count": len(getattr(r, "changedArea", []) or []),
        }
        self.emit.emit(out)
        return out

    def download_vm_disk_with(self, *, vm_name: str, disk_sel: Any, local_path: Path) -> Any:
        """
        Internal reuse helper: call download_vm_disk logic without mutating self.args.
        """
        shim = _ArgsShim(
            vm_name=vm_name,
            disk=disk_sel,
            local_path=str(local_path),
            chunk_size=1024 * 1024,
            dc_name=getattr(self.args, "dc_name", None),
            json=getattr(self.args, "json", False),
            vcenter=getattr(self.args, "vcenter", None),
            vc_user=getattr(self.args, "vc_user", None),
            vc_password=getattr(self.args, "vc_password", None),
            vc_password_env=getattr(self.args, "vc_password_env", None),
            vc_insecure=getattr(self.args, "vc_insecure", None),
            govc_bin=getattr(self.args, "govc_bin", None),
            no_govmomi=getattr(self.args, "no_govmomi", False),
        )
        tmp = VsphereCommands(self.client, shim)
        return tmp.download_vm_disk()

    def download_only_vm(self) -> Any:
        """Download a filtered set of files from a VM's datastore folder, without exporting/converting it."""
        vm_name = _require(self.args, "vm_name")
        out_dir = getattr(self.args, "output_dir", None) or getattr(self.args, "output_dir", "./out")
        out_dir_path = Path(out_dir).expanduser()

        include_globs = tuple(getattr(self.args, "vs_include_glob", None) or []) or ("*",)
        exclude_globs = tuple(getattr(self.args, "vs_exclude_glob", None) or []) or ()

        # NOTE: --concurrency/--use-async-http (vs_concurrency/vs_use_async_http) are accepted
        # as CLI flags but ExportOptions has no download_only_concurrency/download_only_use_async_http
        # fields and the download-only implementation is sequential-only; passing them here would
        # raise TypeError. Not forwarded until ExportOptions/download_only_vm grow real support.
        opt = ExportOptions(
            vm_name=vm_name,
            export_mode="download_only",
            output_dir=out_dir_path,
            datacenter=getattr(self.args, "dc_name", "auto") or "auto",
            download_only_include_globs=include_globs,
            download_only_exclude_globs=exclude_globs,
            download_only_max_files=int(getattr(self.args, "vs_max_files", 5000) or 5000),
            download_only_fail_on_missing=bool(getattr(self.args, "vs_fail_on_missing", False)),
        )

        res = self.client.export_vm(opt)
        out = {"ok": True, "vm": vm_name, "output_dir": str(res)}
        self.emit.emit(out, human_msg=str(res))
        return out

    def vddk_download_disk(self) -> Any:
        """Download a VM disk via the VDDK transport."""
        vm_name = _require(self.args, "vm_name")
        disk_sel = getattr(self.args, "disk", None)
        local_path = Path(_require(self.args, "local_path")).expanduser()

        # accept both new and legacy flag names
        vddk_libdir = _p(_arg_any(self.args, "vddk_libdir", "vs_vddk_libdir2"))
        vddk_thumbprint = _arg_any(self.args, "vddk_thumbprint", "vs_vddk_thumbprint2")
        vddk_transports = _arg_any(self.args, "vddk_transports", "vs_vddk_transports2")
        no_verify = bool(_arg_any(self.args, "no_verify", "vs_no_verify2", default=False))

        opt = ExportOptions(
            vm_name=vm_name,
            export_mode="vddk_download",
            output_dir=local_path.parent,
            vddk_download_disk=disk_sel,
            vddk_download_output=local_path,
            vddk_libdir=vddk_libdir,
            vddk_thumbprint=vddk_thumbprint,
            vddk_transports=vddk_transports,
            no_verify=no_verify,
        )

        res = self.client.export_vm(opt)
        out = {"ok": True, "vm": vm_name, "disk": disk_sel, "local_path": str(res)}
        self.emit.emit(out, human_msg=str(res))
        return out


class _ArgsShim:  # pylint: disable=too-few-public-methods  # dynamic attribute bag standing in for an argparse.Namespace
    """Tiny shim so we can reuse action funcs without argparse objects."""

    def __init__(self, **kw: Any):
        for k, v in kw.items():
            setattr(self, k, v)


# Router


_ACTIONS: dict[str, str] = {
    "list_vm_names": "list_vm_names",
    "get_vm_by_name": "get_vm_by_name",
    "vm_disks": "vm_disks",
    "select_disk": "select_disk",
    "download_datastore_file": "download_datastore_file",
    "datastore_ls": "datastore_ls",
    "download_datastore_dir": "download_datastore_dir",
    "create_snapshot": "create_snapshot",
    "enable_cbt": "enable_cbt",
    "query_changed_disk_areas": "query_changed_disk_areas",
    "download_vm_disk": "download_vm_disk",
    "cbt_sync": "cbt_sync",
    "download_only_vm": "download_only_vm",
    "vddk_download_disk": "vddk_download_disk",
}


def _get_action_or_raise(args: Any) -> str:
    action = getattr(args, "vs_action", None)
    if not action:
        raise VMwareError("Missing vs_action (argparse should have required=True)")
    action = str(action)
    if action not in _ACTIONS:
        raise VMwareError(f"vsphere: unknown action: {action}")
    return action


def _build_client(args: Any, conf: dict[str, Any] | None, logger: Any) -> VMwareClient:
    cfg = _merged_cfg(args, conf)
    return VMwareClient.from_config(
        logger=logger,
        cfg=cfg,
        port=getattr(args, "vc_port", None),
        insecure=getattr(args, "vc_insecure", None),
        timeout=None,
    )


def run_vsphere_command(args: Any, conf: dict[str, Any] | None, logger: Any) -> int:
    """
    Entry point for: hyper2kvm.py vsphere <action> ...
    Returns structured exit codes suitable for shell/CI.
    """
    try:
        action = _get_action_or_raise(args)
        client = _build_client(args, conf, logger)

        with client:
            cmd = VsphereCommands(client, args)
            meth_name = _ACTIONS[action]
            meth = getattr(cmd, meth_name, None)
            if not callable(meth):
                raise VMwareError(f"vsphere: action not callable: {action} -> {meth_name}")
            meth()

        return int(VsphereExitCode.OK)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C).")
        return int(VsphereExitCode.INTERRUPTED)

    except VMwareError as e:
        code = _classify_exit_code(e)
        logger.exception("vsphere command failed (%s): %s", code.name, e)
        return int(code)

    # top-level CLI command guard: must translate any crash into a structured exit code, not propagate
    except Exception as e:  # pylint: disable=broad-exception-caught
        code = _classify_exit_code(e)
        logger.exception("vsphere command crashed (%s): %s", code.name, e)
        return int(code)
