# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""vSphere mode for VM discovery and export orchestration."""

# pylint: disable=too-many-lines
# cohesive vSphere action-handler class; splitting would scatter closely related
# connect/export/download logic across files

# hyper2kvm/vmware/vsphere/mode.py
from __future__ import annotations

import fnmatch
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from ....core.exceptions import Fatal, VMwareError, create_helpful_error
from ....core.utils import U

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

    import requests
    from pyVmomi import vim, vmodl
else:
    try:
        from pyVmomi import vim, vmodl
    except ImportError:
        # Set imported names to None
        vim = vmodl = None, None  # type: ignore

# Import from the correct modules
try:
    from hyper2kvm.providers.vmware.transports.http_client import (
        HTTPDownloadClient,
        HTTPDownloadOptions,
    )
except ImportError:  # pragma: no cover
    HTTPDownloadClient = None  # type: ignore
    HTTPDownloadOptions = None  # type: ignore

try:
    from hyper2kvm.providers.vmware.clients.client import VMwareClient
    from hyper2kvm.providers.vmware.transports.govc_common import GovcRunner
    from hyper2kvm.providers.vmware.transports.ovftool_client import (
        OvfDeployOptions,
        OvfExportOptions,
        OvfToolAuthError,
        OvfToolError,
        OvfToolNotFound,
        OvfToolSslError,
        deploy_ovf_or_ova,
        export_to_ova,
        find_ovftool,
        ovftool_version,
    )
except ImportError:  # pragma: no cover
    VMwareClient = None  # type: ignore
    GovcRunner = None  # type: ignore
    OvfDeployOptions = None  # type: ignore
    OvfExportOptions = None  # type: ignore
    OvfToolAuthError = None  # type: ignore
    OvfToolError = None  # type: ignore
    OvfToolNotFound = None  # type: ignore
    OvfToolSslError = None  # type: ignore
    deploy_ovf_or_ova = None  # type: ignore
    export_to_ova = None  # type: ignore
    find_ovftool = None  # type: ignore
    ovftool_version = None  # type: ignore


_DEFAULT_HTTP_TIMEOUT = (10, 300)  # (connect, read) seconds
_DEFAULT_CHUNK_SIZE = 1024 * 1024


# Utility Functions
def _boolish(v: Any) -> bool:
    """Convert various truthy values to boolean."""
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _short_exc(e: BaseException) -> str:
    """Get short exception description."""
    try:
        return f"{type(e).__name__}: {e}"
    except Exception:  # pylint: disable=broad-exception-caught  # exception-formatting helper must never itself raise, regardless of what str(e) does
        return type(e).__name__


def _fmt_duration(sec: float) -> str:
    """Format duration to human readable string."""
    if sec < 1.0:
        return f"{sec * 1000:.0f}ms"
    if sec < 60.0:
        return f"{sec:.2f}s"
    m = int(sec // 60)
    s = sec - (m * 60)
    return f"{m}m{s:.0f}s"


def _redact_cookie(cookie: str) -> str:
    """Redact cookie value for logging."""
    if not cookie:
        return ""
    try:
        parts = cookie.split("=", 1)
        if len(parts) != 2:
            return "Cookie=<redacted>"
        k, v = parts
        v = v.strip()
        tail = v[-6:] if len(v) >= 6 else v
        return f"{k}=…{tail}"
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort cookie redaction for logging; must not raise on malformed input
        return "Cookie=<redacted>"


def _is_transient_http(status: int) -> bool:
    """Check if HTTP status code indicates transient error."""
    return status in (408, 429, 500, 502, 503, 504)


def _norm_action(v: Any) -> str:
    """Normalize action name."""
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "export_vmin": "export_vm",
        "exportvm": "export_vm",
        "export": "export_vm",
        "ovftool_export": "ovftool_export",
        "ovftool_deploy": "ovftool_deploy",
    }
    return aliases.get(s, s)


def _norm_export_mode(v: Any) -> str:
    """Normalize export mode name."""
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "ovf": "ovf_export",
        "export_ovf": "ovf_export",
        "ovfdir": "ovf_export",
        "ova": "ova_export",
        "export_ova": "ova_export",
        "ovftool": "ovftool_export",
    }
    return aliases.get(s, s)


def _parse_vm_datastore_dir(vmx_path: str) -> tuple[str, str]:
    """Parse VM datastore directory from VMX path."""
    s = (vmx_path or "").strip()
    if not s.startswith("[") or "]" not in s:
        raise VMwareError(f"Unexpected vmPathName format: {vmx_path}")
    ds = s[1 : s.index("]")]
    rest = s[s.index("]") + 1 :].strip()
    folder = "" if "/" not in rest else rest.rsplit("/", 1)[0].lstrip("/")
    return ds, folder


def _parse_datastore_dir_override(s: str, *, default_ds: str | None = None) -> tuple[str, str]:
    """Parse datastore directory override."""
    t = (s or "").strip()
    if not t:
        raise VMwareError("Empty vs_datastore_dir override")

    if t.startswith("[") and "]" in t:
        ds = t[1 : t.index("]")]
        rest = t[t.index("]") + 1 :].strip()
        rest = rest.lstrip("/")
        folder = rest.rsplit("/", 1)[0] if "/" in rest else ""
        return ds, folder.strip("/")

    if not default_ds:
        raise VMwareError("vs_datastore_dir provided without datastore and default datastore is unknown")

    folder = t.strip().lstrip("/").rstrip("/")
    if "/" in folder and "." in folder.split("/")[-1]:
        folder = folder.rsplit("/", 1)[0]
    return str(default_ds), folder.strip("/")


def _safe_rel_ds_path(ds_path: str) -> str:
    """
    Sanitize datastore-relative paths before using them as local filesystem paths.

    - Must be relative (no absolute paths)
    - Must not contain '..' segments
    - Normalize backslashes to forward slashes (defensive)
    """
    raw = str(ds_path or "").replace("\\", "/").strip()
    raw = raw.lstrip("/")  # datastore-relative
    if not raw:
        raise VMwareError("empty ds_path")

    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise VMwareError(f"refusing ds_path with '..' segments: {ds_path!r}")

    # Reconstruct stable posix-ish relative path
    clean = "/".join(parts)
    if clean.startswith(("/", "..")):
        raise VMwareError(f"refusing unsafe ds_path: {ds_path!r}")
    return clean


# Transport Policy Functions
def _get_transport_preference(args: argparse.Namespace) -> str:
    """Get transport preference for datastore file downloads.

    New default: HTTPS (stable).
    VDDK: EXPERIMENTAL; only if explicitly requested.
    """
    v = getattr(args, "vs_transport", None) or getattr(args, "vs_download_transport", None)
    if not v:
        v = os.environ.get("VMDK2KVM_VSPHERE_TRANSPORT") or os.environ.get("VSPHERE_TRANSPORT")
    v = str(v).strip().lower() if v else "https"
    if v in ("https", "http", "folder", "pyvmomi"):
        return "https"
    if v == "vddk":
        return "vddk"
    if v == "auto":
        return "https"  # auto now means: stable first
    return "https"


def _get_http_timeout(args: argparse.Namespace) -> tuple[int, int]:
    """Get HTTP timeout configuration."""
    timeout = getattr(args, "vs_http_timeout", None)
    if timeout is None:
        timeout = os.environ.get("VMDK2KVM_VSPHERE_HTTP_TIMEOUT")
    if timeout:
        try:
            if isinstance(timeout, str) and "," in timeout:
                a, b = timeout.split(",", 1)
                timeout_tuple = (int(a.strip()), int(b.strip()))
            else:
                t = int(str(timeout).strip())
                timeout_tuple = (10, t)
        except (ValueError, TypeError):
            timeout_tuple = _DEFAULT_HTTP_TIMEOUT
    else:
        timeout_tuple = _DEFAULT_HTTP_TIMEOUT
    return timeout_tuple


def _get_http_retries(args: argparse.Namespace) -> int:
    """Get HTTP retry configuration."""
    retries = getattr(args, "vs_http_retries", None)
    if retries is None:
        retries = os.environ.get("VMDK2KVM_VSPHERE_HTTP_RETRIES")
    try:
        retries_i = int(retries) if retries is not None else 3
    except (ValueError, TypeError):
        retries_i = 3
    return max(0, retries_i)


# HTTPS Download Functions
# pylint: disable-next=too-many-arguments,too-many-positional-arguments,too-many-locals  # full HTTPS transport config surface (host/ds/paths/tls/timeouts/chunking) is inherent to a single-file download
def _download_one_folder_file(
    client: VMwareClient,
    vc_host: str,
    dc_name: str,
    ds_name: str,
    ds_path: str,
    local_path: Path,
    verify_tls: bool,
    args: argparse.Namespace,
    *,
    on_bytes: Callable[[int, int], None] | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> None:
    """Download a single file via HTTPS /folder endpoint using HTTPDownloadClient."""
    if HTTPDownloadClient is None:
        raise VMwareError("HTTPDownloadClient not available. Install: pip install requests")

    # Create download client
    timeout_tuple = _get_http_timeout(args)
    download_client = HTTPDownloadClient(
        logger=logging.getLogger(__name__),
        host=vc_host,
        port=443,
        insecure=not verify_tls,
        timeout=float(timeout_tuple[1]),  # Use read timeout
    )

    # Set session cookie from VMwareClient
    cookie = _get_session_cookie(client)
    download_client.set_session_cookie(cookie)

    # Configure download options to match previous behavior
    retries_i = _get_http_retries(args)
    options = HTTPDownloadOptions(
        show_progress=True,
        log_every_bytes=10 * 1024 * 1024,  # 10MB - progress bar fix applied!
        retries=retries_i,
        retry_backoff_s=2.0,
        chunk_size=chunk_size,
        resume_download=True,  # Bonus: resume support!
        atomic=True,
        show_panels=False,  # Don't show extra UI panels in vsphere mode
    )

    if _debug_enabled(args):
        logging.getLogger(__name__).debug(
            "vsphere: HTTPS /folder download (via HTTPDownloadClient): "
            "ds=[%s] path=%r verify_tls=%s timeout=%s chunk_size=%s retries=%d cookie=%r",
            ds_name,
            ds_path,
            verify_tls,
            timeout_tuple,
            chunk_size,
            retries_i,
            _redact_cookie(cookie),
        )

    # Download using HTTPDownloadClient
    t0 = time.monotonic()
    try:
        download_client.download_file(
            datastore=ds_name,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            on_bytes=on_bytes,
            options=options,
        )

        if _debug_enabled(args):
            try:
                sz = local_path.stat().st_size
            except OSError:
                sz = None
            logging.getLogger(__name__).debug(
                "vsphere: HTTPS download ok: ds=[%s] path=%r bytes=%s dur=%s",
                ds_name,
                ds_path,
                U.human_bytes(sz),
                _fmt_duration(time.monotonic() - t0),
            )

    except Exception as e:  # pylint: disable=broad-exception-caught  # only logs debug context before re-raising; must catch anything to log it
        # HTTPDownloadClient already wraps errors in VMwareError and handles retries
        if _debug_enabled(args):
            logging.getLogger(__name__).debug(
                "vsphere: HTTPS download failed: ds=[%s] path=%r dur=%s err=%s",
                ds_name,
                ds_path,
                _fmt_duration(time.monotonic() - t0),
                _short_exc(e),
            )
        raise  # Re-raise the VMwareError from HTTPDownloadClient


def _get_session_cookie(client: VMwareClient) -> str:
    """Get session cookie from VMwareClient."""
    # Prefer a public helper if your VMwareClient provides it.
    fn = getattr(client, "get_session_cookie", None)
    if callable(fn):
        cookie = fn()
        if cookie:
            return cookie

    # Fallback to pyVmomi internals (best-effort).
    try:
        si = getattr(client, "si", None)
        if si:
            cookie = getattr(getattr(si, "_stub", None), "cookie", None)
            if cookie:
                return cookie
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort pyVmomi stub access; shape unguaranteed
        pass

    raise VMwareError(
        "Cannot get session cookie: VMwareClient is not properly connected or returned empty cookie"
    )


def _get_response_status(e: requests.RequestException) -> int | None:
    """Extract status code from request exception."""
    try:
        resp = getattr(e, "response", None)
        if resp is not None:
            return int(getattr(resp, "status_code", 0) or 0)
    except (ValueError, TypeError):
        pass
    return None


# File Download Policy Functions
# pylint: disable-next=too-many-arguments  # transport-policy dispatch needs the full download address/config surface it forwards to the VDDK/HTTPS helpers
def _download_one_file_with_policy(
    client: VMwareClient,
    args: argparse.Namespace,
    *,
    vc_host: str,
    dc_name: str,
    ds_name: str,
    ds_path: str,
    local_path: Path,
    verify_tls: bool,
    on_bytes: Callable[[int, int], None] | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> None:
    """
    Download a file with transport policy.

    Policy order:
      - If user explicitly requested VDDK: try VDDK (EXPERIMENTAL), then fall back to HTTPS.
      - Default: HTTPS /folder.
    """
    pref = _get_transport_preference(args)

    if pref == "vddk":
        ok = _try_vddk_download(
            client=client,
            ds_name=ds_name,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            chunk_size=chunk_size,
            on_bytes=on_bytes,
            _args=args,
        )
        if ok:
            return

    _download_one_folder_file(
        client=client,
        vc_host=vc_host,
        dc_name=dc_name,
        ds_name=ds_name,
        ds_path=ds_path,
        local_path=local_path,
        verify_tls=verify_tls,
        args=args,
        on_bytes=on_bytes,
        chunk_size=chunk_size,
    )


# pylint: disable-next=too-many-arguments  # mirrors the sibling HTTPS download helper's full transfer-address/config surface
def _try_vddk_download(
    *,
    client: VMwareClient,
    ds_name: str,
    ds_path: str,
    local_path: Path,
    dc_name: str,
    chunk_size: int,
    on_bytes: Callable[[int, int], None] | None,
    _args: argparse.Namespace,
) -> bool:
    """
    Try VDDK download (experimental opt-in).

    Returns:
      True if VDDK download succeeded, False if unavailable/failed (caller should fall back).
    """
    logger = logging.getLogger(__name__)
    logger.warning("VDDK transport requested: EXPERIMENTAL (opt-in). Will fall back on failure.")

    fn = getattr(client, "download_datastore_file_vddk", None)
    if not callable(fn):
        logger.warning(
            "VDDK requested but VMwareClient has no download_datastore_file_vddk(); falling back to HTTPS."
        )
        return False

    try:
        # Prefer keyword form (more stable)
        fn(
            datastore=ds_name,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            chunk_size=chunk_size,
            on_bytes=on_bytes,
        )
        return True
    except TypeError:
        # Back-compat for older signatures
        fn(ds_name, ds_path, local_path)
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught  # VDDK is experimental/optional; any failure must fall back to HTTPS, not crash the export
        logger.warning("VDDK download failed; falling back to HTTPS folder: %s", _short_exc(e))
        return False


# Progress UI Functions (no-op stubs; Rich progress has been removed)
def _create_progress_ui(_args: argparse.Namespace, _total_files: int) -> tuple[None, None, None]:
    """Progress UI has been removed. Returns None placeholders for API compatibility."""
    return None, None, None


# pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument  # no-op stub kept for call-site compatibility after Rich progress removal
def _update_progress(
    progress: None,
    files_task: Any | None,
    bytes_task: Any | None,
    description: str | None = None,
    bytes_advance: int = 0,
    files_advance: int = 0,
) -> None:
    """No-op progress update (Rich progress has been removed)."""
    return
# pylint: enable=too-many-arguments,too-many-positional-arguments,unused-argument


# File Filtering Functions
def _filter_files_by_glob(
    files: list[str],
    include_glob: list[str],
    exclude_glob: list[str],
    max_files: int,
) -> list[str]:
    """Filter files based on glob patterns."""
    filtered: list[str] = []
    for rel in files:
        if not rel:
            continue
        bn = rel.split("/")[-1]

        if include_glob and not any(
            fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(bn, pat) for pat in include_glob
        ):
            continue

        if exclude_glob and any(
            fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(bn, pat) for pat in exclude_glob
        ):
            continue

        filtered.append(rel)

        if max_files and len(filtered) > max_files:
            raise Fatal(2, f"Refusing to process > max_files={max_files} (found so far: {len(filtered)})")

    return filtered


# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # govc listing + glob filtering both need their full parameter set
def _get_vm_files_from_govc(
    govc: GovcRunner,
    ds_name: str,
    folder: str,
    include_glob: list[str],
    exclude_glob: list[str],
    max_files: int,
) -> list[str]:
    """
    Get VM files using govc datastore.ls -json (via GovcRunner) with filtering.

    NOTE:
      GovcRunner.datastore_ls_json() returns paths relative to the directory you list.
      We convert them back to datastore-relative paths by prefixing folder when needed.
    """
    rels = govc.datastore_ls_json(ds_name, folder)
    base = (folder or "").strip().strip("/")

    files: list[str] = []
    for name in rels:
        nm = str(name or "").lstrip("/").strip()
        if not nm:
            continue
        rel = f"{base}/{nm}" if base else nm
        files.append(rel)

    return _filter_files_by_glob(files, include_glob, exclude_glob, max_files)


# VM Export Functions
# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # export fallback chain needs the full VM/target/connection context to hand off to each transport
def _export_vm_with_fallback(
    govc: GovcRunner,
    args: argparse.Namespace,
    vm_name: str,
    out_dir: Path,
    client: VMwareClient,
    vc_host: str,
    dc_name: str,
) -> int:
    """
    Export VM with fallback strategy: OVF -> OVA -> HTTPS folder.
    Control-plane prefers govc exports; data-plane fallback uses HTTPS /folder.
    """
    export_mode = _norm_export_mode(getattr(args, "export_mode", None) or "ovf_export")
    logger = logging.getLogger(__name__)

    logger.info(
        "export_vm: vm=%r out_dir=%s export_mode=%s (policy: ovf -> ova -> https)",
        vm_name,
        out_dir,
        export_mode,
    )

    # Try OVF export
    if export_mode in ("ovf_export", "auto"):
        try:
            govc.export_ovf(
                vm=vm_name,
                out_dir=str(out_dir),
                remove_cdroms=bool(getattr(args, "govc_remove_cdroms", True)),
                show_vm_info=bool(getattr(args, "govc_show_vm_info", True)),
                shutdown=bool(getattr(args, "govc_shutdown", False)),
                shutdown_timeout_s=float(getattr(args, "govc_shutdown_timeout_s", 300.0) or 300.0),
                shutdown_poll_s=float(getattr(args, "govc_shutdown_poll_s", 5.0) or 5.0),
                power_off=bool(getattr(args, "govc_power_off", False)),
                clean_outdir=bool(getattr(args, "govc_clean_outdir", False)),
                show_progress=bool(getattr(args, "govc_show_progress", True)),
                prefer_pty=bool(getattr(args, "govc_prefer_pty", True)),
            )
            return 0
        except Exception as e:  # pylint: disable=broad-exception-caught  # OVF export fallback step: must fall through to OVA
            logger.warning("export_vm: OVF export failed; trying OVA: %s", _short_exc(e))

    # Try OVA export
    if export_mode in ("ova_export", "ovf_export", "auto"):
        try:
            govc.export_ova(
                vm=vm_name,
                out_file=str(out_dir / f"{vm_name}.ova"),
                remove_cdroms=bool(getattr(args, "govc_remove_cdroms", True)),
                show_vm_info=bool(getattr(args, "govc_show_vm_info", True)),
                shutdown=bool(getattr(args, "govc_shutdown", False)),
                shutdown_timeout_s=float(getattr(args, "govc_shutdown_timeout_s", 300.0) or 300.0),
                shutdown_poll_s=float(getattr(args, "govc_shutdown_poll_s", 5.0) or 5.0),
                power_off=bool(getattr(args, "govc_power_off", False)),
                clean_outdir=bool(getattr(args, "govc_clean_outdir", False)),
                show_progress=bool(getattr(args, "govc_show_progress", True)),
                prefer_pty=bool(getattr(args, "govc_prefer_pty", True)),
            )
            return 0
        except Exception as e:  # pylint: disable=broad-exception-caught  # OVA export fallback step: must fall through to HTTPS
            logger.warning(
                "export_vm: OVA export failed; falling back to HTTPS folder download: %s", _short_exc(e)
            )

    # Fall back to HTTPS folder download
    return _export_vm_via_https(client, govc, args, vm_name, out_dir, vc_host, dc_name)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments,too-many-locals  # VM lookup, error reporting, and file-listing/download all need this connection/target context
def _export_vm_via_https(
    client: VMwareClient,
    govc: GovcRunner,
    args: argparse.Namespace,
    vm_name: str,
    out_dir: Path,
    vc_host: str,
    dc_name: str,
) -> int:
    """Export VM by downloading files via HTTPS."""
    logger = logging.getLogger(__name__)

    vm = client.get_vm_by_name(vm_name)
    if not vm:
        vcenter_host = getattr(client, "host", "unknown")
        raise create_helpful_error(
            Fatal,
            f"VM not found: {vm_name}",
            code=2,
            solutions=[
                f"Verify VM name (case-sensitive): govc ls -u '{vcenter_host}' /DC/vm/",
                "List all accessible VMs: hyper2kvm vsphere --vs-action list-vms",
                "Check datacenter configuration",
                "Verify permissions with vCenter administrator",
            ],
            causes=[
                "VM name is misspelled or case-sensitive",
                "VM is in a different datacenter",
                "Insufficient permissions to view VM",
                "VM has been renamed or deleted",
            ],
            doc_link="30-vSphere-Export.md#troubleshooting",
            vm_name=vm_name,
            vcenter=vcenter_host,
        )

    try:
        vmx_path = vm.summary.config.vmPathName if vm.summary and vm.summary.config else None
    except Exception:  # pylint: disable=broad-exception-caught  # vm.summary/.config are dynamic pyVmomi properties that can raise arbitrary server-side faults
        vmx_path = None

    if not vmx_path:
        raise Fatal(
            2, "vsphere export_vm: cannot determine VM folder (vm.summary.config.vmPathName missing)"
        )

    ds_name, folder = _parse_vm_datastore_dir(str(vmx_path))

    include_glob = list(getattr(args, "vs_include_glob", None) or ["*"])
    exclude_glob = list(
        getattr(args, "vs_exclude_glob", None) or ["*.lck", "*.log", "*.vswp", "*.vmem", "*.vmsn"]
    )
    max_files = int(getattr(args, "vs_max_files", 5000) or 5000)

    files = _get_vm_files_from_govc(govc, ds_name, folder, include_glob, exclude_glob, max_files)
    if not files:
        logger.info("export_vm: HTTPS fallback found no files to download.")
        return 0

    verify_tls = not bool(getattr(client, "insecure", False))

    logger.info(
        "export_vm: HTTPS fallback downloading %d files from [%s] %s", len(files), ds_name, folder or "."
    )

    _download_files_with_progress(
        client=client,
        args=args,
        files=files,
        ds_name=ds_name,
        vc_host=vc_host,
        dc_name=dc_name,
        verify_tls=verify_tls,
        out_dir=out_dir,
    )

    logger.info("export_vm: HTTPS fallback completed into %s", out_dir)
    return 0


# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # multi-file download needs the full connection/target context passed to each per-file download
def _download_files_with_progress(
    client: VMwareClient,
    args: argparse.Namespace,
    files: list[str],
    ds_name: str,
    vc_host: str,
    dc_name: str,
    verify_tls: bool,
    out_dir: Path,
) -> None:
    """Download multiple files with progress UI."""
    progress, files_task, bytes_task = _create_progress_ui(args, len(files))

    def download_job(ds_path: str) -> None:
        safe_ds_path = _safe_rel_ds_path(ds_path)
        local_path = out_dir / safe_ds_path

        def on_bytes(n: int, _total: int) -> None:
            _update_progress(
                progress,
                files_task,
                bytes_task,
                description=f"downloading: {safe_ds_path}",
                bytes_advance=n,
            )

        _download_one_file_with_policy(
            client=client,
            args=args,
            vc_host=vc_host,
            dc_name=dc_name,
            ds_name=ds_name,
            ds_path=safe_ds_path,
            local_path=local_path,
            verify_tls=verify_tls,
            on_bytes=on_bytes,
            chunk_size=int(getattr(args, "chunk_size", _DEFAULT_CHUNK_SIZE)),
        )
        _update_progress(progress, files_task, bytes_task, files_advance=1)

    for p in files:
        download_job(p)


# OVF Tool Helper Functions
def _build_ovftool_source_url(
    client: VMwareClient,
    vm_name: str,
    args: argparse.Namespace,
    dc_name: str,
) -> str:
    """Build a vi:// source URL for OVF Tool from VM name."""
    vc_host = str(args.vcenter)
    vc_user = str(args.vc_user)
    vc_pass = getattr(args, "vc_password", None)

    if not vc_pass:
        raise Fatal(2, "ovftool_export: vc_password is missing (set vc_password_env or vc_password)")

    vm = client.get_vm_by_name(vm_name)
    if not vm:
        raise Fatal(2, f"VM not found: {vm_name}")

    inv = _get_vim_inventory_path(vm, dc_name)

    u = quote(vc_user, safe="")
    p = quote(str(vc_pass), safe="")
    return f"vi://{u}:{p}@{vc_host}/{inv}"


def _get_vim_inventory_path(vm: vim.VirtualMachine, dc_name: str) -> str:
    """Build inventory path for ovftool: <dc>/vm/<folder1>/<folder2>/<vmname>"""
    parts: list[str] = []
    obj: Any = vm

    while obj is not None:
        try:
            if isinstance(obj, vim.Datacenter):
                break
            if isinstance(obj, vim.Folder) and obj.name and obj.name != "vm":
                parts.append(obj.name)
            obj = getattr(obj, "parent", None)
        except Exception:  # pylint: disable=broad-exception-caught  # dynamic pyVmomi walk; stop gracefully on anomaly
            break

    parts.reverse()
    folder_path = "/".join(parts) if parts else ""
    if folder_path:
        return f"{dc_name}/vm/{folder_path}/{vm.name}"
    return f"{dc_name}/vm/{vm.name}"


# Debug and Configuration Functions
def _debug_enabled(args: argparse.Namespace) -> bool:
    """Check if debug logging is enabled."""
    if _boolish(os.environ.get("VMDK2KVM_DEBUG") or os.environ.get("VMDK2KVM_VSPHERE_DEBUG")):
        return True
    if bool(getattr(args, "debug", False)):
        return True
    return logging.getLogger(__name__).isEnabledFor(logging.DEBUG)


def _get_dc_name(args: argparse.Namespace) -> str:
    """Get datacenter name from args or default."""
    v = getattr(args, "dc_name", None)
    return v if v else "ha-datacenter"


# Main VsphereMode Class
# pylint: disable-next=too-few-public-methods  # CLI entry-point class deliberately exposes a single run() method; the rest are internal action handlers
class VsphereMode:
    """
    CLI entry for vSphere actions.

    Policy:
      - VDDK is EXPERIMENTAL: never auto-run it. Only attempt if user explicitly sets vs_transport=vddk.
      - Export priority: OVF -> OVA -> HTTP/HTTPS folder
      - Control-plane: prefer govc (inventory/export). pyvmomi mainly for /folder cookie downloads.
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.govc = GovcRunner(logger=logger, args=args)

        self.ovftool_paths = None
        if getattr(args, "ovftool_path", None):
            try:
                self.ovftool_paths = find_ovftool(args.ovftool_path)
                version = ovftool_version(self.ovftool_paths)
                self.logger.info(
                    "OVF Tool found: %s (version: %s)", self.ovftool_paths.ovftool_bin, version or "unknown"
                )
            except Exception as e:  # pylint: disable=broad-exception-caught  # optional OVF Tool auto-detection at startup must not crash mode initialization
                self.logger.warning("OVF Tool not found at specified path: %s", e)

    def _require_govc(self) -> None:
        if not self.govc.available():
            raise Fatal(
                2,
                "vsphere: govc is required for this action (control-plane prefers govc). "
                "Install govc and ensure GOVC_* env / args are configured.",
            )

    def _require_ovftool(self) -> None:
        if not self.ovftool_paths:
            try:
                self.ovftool_paths = find_ovftool()
                version = ovftool_version(self.ovftool_paths)
                self.logger.info(
                    "OVF Tool auto-detected: %s (version: %s)",
                    self.ovftool_paths.ovftool_bin,
                    version or "unknown",
                )
            except Exception as e:
                raise Fatal(2, f"OVF Tool is required but not found: {e}") from e

    # govc helpers (public GovcRunner methods)
    # pylint: disable-next=too-many-locals  # each govc vm.info field is unpacked individually to build the flat inventory row
    def _govc_list_vm_names(self) -> list[dict[str, Any]]:
        """
        Inventory via govc.

        NOTE: we keep this method because callers want VM names quickly and this file
        already formats detailed shapes. It uses GovcRunner.run_json primitives.
        """
        self._require_govc()
        t0 = time.monotonic()

        found = self.govc.run_json(["find", "-type", "m", "-json", "."]) or {}
        vms = found.get("Elements") or []
        if not isinstance(vms, list):
            vms = []

        max_detail = int(getattr(self.args, "govc_max_detail", 500) or 500)
        if len(vms) > max_detail:
            out = [{"name": str(p).rsplit("/", maxsplit=1)[-1], "path": p} for p in vms]
            out = sorted(out, key=lambda x: x.get("name", ""))
            if _debug_enabled(self.args):
                self.logger.debug(
                    "govc: list_vm_names (names-only) took %s", _fmt_duration(time.monotonic() - t0)
                )
            return out

        detailed: list[dict[str, Any]] = []
        for pth in vms:
            try:
                info = self.govc.run_json(["vm.info", "-json", str(pth)]) or {}
                arr = info.get("VirtualMachines") or []
                if not arr:
                    continue
                vm = arr[0]
                cfg = vm.get("Config") or {}
                runtime = vm.get("Runtime") or {}
                guest = vm.get("Guest") or {}
                summary = vm.get("Summary") or {}
                detailed.append(
                    {
                        "name": cfg.get("Name") or str(pth).rsplit("/", maxsplit=1)[-1],
                        "runtime.powerState": runtime.get("PowerState"),
                        "summary.overallStatus": (summary.get("OverallStatus") or ""),
                        "summary.guest.guestFullName": (cfg.get("GuestFullName") or ""),
                        "summary.config.memorySizeMB": cfg.get("MemoryMB"),
                        "summary.config.numCpu": cfg.get("NumCPU"),
                        "summary.config.vmPathName": (cfg.get("VmPathName") or ""),
                        "summary.config.instanceUuid": cfg.get("InstanceUuid"),
                        "summary.config.uuid": cfg.get("Uuid"),
                        "guest.guestState": guest.get("GuestState"),
                        "path": pth,
                    }
                )
            except Exception as e:  # pylint: disable=broad-exception-caught  # per-VM inventory detail lookup; one VM's failure must not abort listing the others
                detailed.append(
                    {"name": str(pth).rsplit("/", maxsplit=1)[-1], "path": pth, "error": str(e)}
                )

        detailed = sorted(detailed, key=lambda x: x.get("name", ""))
        if _debug_enabled(self.args):
            self.logger.debug("govc: list_vm_names took %s", _fmt_duration(time.monotonic() - t0))
        return detailed

    # OVF Tool helpers
    def _ovftool_export_vm(self, client: VMwareClient, vm_name: str, out_dir: Path) -> None:
        self._require_ovftool()

        source_url = _build_ovftool_source_url(client, vm_name, self.args, _get_dc_name(self.args))
        ova_path = out_dir / f"{vm_name}.ova"

        options = OvfExportOptions(
            no_ssl_verify=bool(getattr(self.args, "ovftool_no_ssl_verify", True)),
            thumbprint=getattr(self.args, "ovftool_thumbprint", None),
            accept_all_eulas=bool(getattr(self.args, "ovftool_accept_all_eulas", True)),
            quiet=bool(getattr(self.args, "ovftool_quiet", False)),
            verbose=bool(getattr(self.args, "ovftool_verbose", False)),
            overwrite=bool(getattr(self.args, "ovftool_overwrite", False)),
            disk_mode=getattr(self.args, "ovftool_disk_mode", None),
            retries=int(getattr(self.args, "ovftool_retries", 0) or 0),
            retry_backoff_s=float(getattr(self.args, "ovftool_retry_backoff_s", 2.0) or 2.0),
            extra_args=tuple(getattr(self.args, "ovftool_extra_args", []) or []),
        )

        self.logger.info("Exporting VM %s to %s using OVF Tool...", vm_name, ova_path)
        t0 = time.monotonic()

        export_to_ova(
            paths=self.ovftool_paths,
            source=source_url,
            ova_path=ova_path,
            options=options,
            log_prefix="ovftool",
        )

        self.logger.info("OVF Tool export completed in %s", _fmt_duration(time.monotonic() - t0))

    # pylint: disable-next=too-many-locals  # builds the full OvfDeployOptions surface (target path, network map, ssl/retry/eula options) from args
    def _ovftool_deploy_ova(self, source_ova: Path, target_vm_name: str | None = None) -> None:
        self._require_ovftool()

        if not source_ova.exists():
            raise Fatal(2, f"Source OVA/OVF not found: {source_ova}")

        vc_host = str(self.args.vcenter)
        vc_user = str(self.args.vc_user)
        vc_pass = getattr(self.args, "vc_password", None)
        if not vc_pass:
            raise Fatal(2, "ovftool_deploy: vc_password is missing (set vc_password_env or vc_password)")

        dc_name = _get_dc_name(self.args)
        target_folder = getattr(self.args, "ovftool_target_folder", None)
        target_resource_pool = getattr(self.args, "ovftool_target_resource_pool", None)

        target_path = f"{dc_name}"
        if target_folder:
            target_path = f"{target_path}/vm/{target_folder}"
        elif target_resource_pool:
            target_path = f"{target_path}/host/{target_resource_pool}"

        u = quote(vc_user, safe="")
        p = quote(str(vc_pass), safe="")
        target_url = f"vi://{u}:{p}@{vc_host}/{target_path}"

        network_map: list[tuple[str, str]] = []
        net_mapping_str = getattr(self.args, "ovftool_network_map", None)
        if net_mapping_str:
            for mapping in str(net_mapping_str).split(","):
                if ":" in mapping:
                    src, dst = mapping.split(":", 1)
                    network_map.append((src.strip(), dst.strip()))

        options = OvfDeployOptions(
            no_ssl_verify=bool(getattr(self.args, "ovftool_no_ssl_verify", True)),
            thumbprint=getattr(self.args, "ovftool_thumbprint", None),
            accept_all_eulas=bool(getattr(self.args, "ovftool_accept_all_eulas", True)),
            overwrite=bool(getattr(self.args, "ovftool_overwrite", False)),
            power_on=bool(getattr(self.args, "ovftool_power_on", False)),
            name=target_vm_name or getattr(self.args, "ovftool_vm_name", None),
            datastore=getattr(self.args, "ovftool_datastore", None),
            network_map=tuple(network_map),
            disk_mode=getattr(self.args, "ovftool_disk_mode", None),
            quiet=bool(getattr(self.args, "ovftool_quiet", False)),
            verbose=bool(getattr(self.args, "ovftool_verbose", False)),
            retries=int(getattr(self.args, "ovftool_retries", 0) or 0),
            retry_backoff_s=float(getattr(self.args, "ovftool_retry_backoff_s", 2.0) or 2.0),
            extra_args=tuple(getattr(self.args, "ovftool_extra_args", []) or []),
        )

        self.logger.info("Deploying %s to vSphere using OVF Tool...", source_ova)
        t0 = time.monotonic()

        deploy_ovf_or_ova(
            paths=self.ovftool_paths,
            source_ovf_or_ova=source_ova,
            target_vi=target_url,
            options=options,
            log_prefix="ovftool",
        )

        self.logger.info("OVF Tool deployment completed in %s", _fmt_duration(time.monotonic() - t0))

    # Main runner
    # pylint: disable-next=too-many-branches  # connect/validate flow has one branch per distinct missing-parameter and connection-failure hint
    def run(self) -> int:
        """Resolve connection parameters, connect to vCenter, and dispatch the requested vSphere action."""
        vc_host = self.args.vcenter
        vc_user = self.args.vc_user
        vc_pass = getattr(self.args, "vc_password", None)

        if not vc_pass and getattr(self.args, "vc_password_env", None):
            vc_pass = os.environ.get(self.args.vc_password_env)

        if isinstance(vc_pass, str):
            vc_pass = vc_pass.strip() or None

        # ✅ persist resolved password back into args for ovftool helpers
        self.args.vc_password = vc_pass

        action = _norm_action(getattr(self.args, "vs_action", None))

        if not vc_host or not vc_user or not vc_pass:
            missing = []
            if not vc_host:
                missing.append("--vcenter (vCenter hostname, e.g., vcenter.example.com)")
            if not vc_user:
                missing.append("--vc-user (vCenter username, e.g., administrator@vsphere.local)")
            if not vc_pass:
                missing.append("--vc-password or --vc-password-env (vCenter password or env var name)")
            raise Fatal(
                2,
                f"vsphere: Missing required connection parameters:\n"
                f"  {chr(10).join('  - ' + m for m in missing)}\n\n"
                "You can also set environment variables: GOVC_URL, GOVC_USERNAME, GOVC_PASSWORD",
            )

        if _debug_enabled(self.args):
            self.logger.debug(
                "vsphere: connect params: host=%r user=%r port=%r insecure=%s "
                "dc_name=%r transport_pref=%r govc_available=%s",
                vc_host,
                vc_user,
                getattr(self.args, "vc_port", None),
                bool(getattr(self.args, "vc_insecure", False)),
                _get_dc_name(self.args),
                _get_transport_preference(self.args),
                self.govc.available(),
            )
            self.logger.debug("vsphere: normalized action=%r", action)

        # Actions that *require* govc
        if action in ("list_vm_names", "export_vm", "download_only_vm"):
            self._require_govc()

        if VMwareClient is None:
            raise Fatal(2, "vsphere: VMwareClient import failed (package/module issue)")

        client = VMwareClient(
            self.logger,
            vc_host,
            vc_user,
            vc_pass,
            port=getattr(self.args, "vc_port", None),
            insecure=bool(getattr(self.args, "vc_insecure", False)),
        )

        try:
            t0 = time.monotonic()
            client.connect()
            if _debug_enabled(self.args):
                self.logger.debug("vsphere: connected in %s", _fmt_duration(time.monotonic() - t0))
        except VMwareError as e:
            err_str = str(e).lower()
            hint = ""
            if "ssl" in err_str or "certificate" in err_str or "tls" in err_str:
                hint = "\n  Try: --vc-insecure to skip certificate verification"
            elif "refused" in err_str or "timed out" in err_str or "unreachable" in err_str:
                hint = (
                    "\n  Check: vCenter host is reachable and port 443 is open\n"
                    "  Try: curl -k https://<vcenter>/sdk to test connectivity"
                )
            elif "401" in err_str or "auth" in err_str or "login" in err_str:
                hint = "\n  Check: username and password are correct for vCenter (not ESXi)"
            raise Fatal(2, f"vsphere: Connection to {vc_host} failed: {e}{hint}") from e

        try:
            return self._handle_action(action, client, str(vc_host))
        finally:
            try:
                t0 = time.monotonic()
                client.disconnect()
                if _debug_enabled(self.args):
                    self.logger.debug("vsphere: disconnected in %s", _fmt_duration(time.monotonic() - t0))
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cleanup; must not mask the action's own result
                self.logger.warning("Failed to disconnect: %s", e)

    def _handle_action(self, action: str, client: VMwareClient, vc_host: str) -> int:
        dc_name = _get_dc_name(self.args)

        if action == "list_vm_names":
            return self._handle_list_vm_names()

        if action == "export_vm":
            return self._handle_export_vm(client, vc_host, dc_name)

        if action == "ovftool_export":
            return self._handle_ovftool_export(client)

        if action == "ovftool_deploy":
            return self._handle_ovftool_deploy()

        if action == "download_datastore_file":
            return self._handle_download_datastore_file(client, dc_name)

        if action == "download_only_vm":
            return self._handle_download_only_vm(client, vc_host, dc_name)

        valid_actions = [
            "list_vm_names",
            "export_vm",
            "ovftool_export",
            "ovftool_deploy",
            "download_datastore_file",
            "download_only_vm",
        ]
        raise Fatal(
            2,
            f"vsphere: unknown action '{action}'.\n"
            f"Valid actions: {', '.join(valid_actions)}\n"
            "Example: h2kvmctl vsphere --vs-action export_vm --vm-name MyVM",
        )

    def _handle_list_vm_names(self) -> int:
        vms = self._govc_list_vm_names()
        self.logger.info("VMs found (govc): %d", len(vms))
        if bool(getattr(self.args, "json", False)):
            print(json.dumps(vms, indent=2, default=str))
        else:
            for vm in vms:
                print(vm.get("name", "Unnamed VM"))
        return 0

    def _handle_export_vm(self, client: VMwareClient, vc_host: str, dc_name: str) -> int:
        vm_name = getattr(self.args, "vm_name", None) or getattr(self.args, "name", None)
        if not vm_name:
            raise Fatal(2, "vsphere export_vm: --vm_name is required")

        out_dir = Path(getattr(self.args, "output_dir", None) or ".").expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        return _export_vm_with_fallback(
            self.govc, self.args, str(vm_name), out_dir, client, vc_host, dc_name
        )

    def _handle_ovftool_export(self, client: VMwareClient) -> int:
        vm_name = getattr(self.args, "vm_name", None) or getattr(self.args, "name", None)
        if not vm_name:
            raise Fatal(2, "vsphere ovftool_export: --vm_name is required")

        out_dir = Path(getattr(self.args, "output_dir", None) or ".").expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._ovftool_export_vm(client, str(vm_name), out_dir)
            return 0
        except (OvfToolNotFound, OvfToolAuthError, OvfToolSslError, OvfToolError) as e:
            raise Fatal(2, f"OVF Tool export failed: {e}") from e
        except Exception as e:
            self.logger.exception("ovftool_export: unexpected error")
            raise Fatal(2, f"OVF Tool export failed with unexpected error: {e}") from e

    def _handle_ovftool_deploy(self) -> int:
        source_path = getattr(self.args, "source_path", None)
        if not source_path:
            raise Fatal(2, "vsphere ovftool_deploy: --source-path is required")

        source_path = Path(source_path).expanduser().resolve()
        target_vm_name = getattr(self.args, "vm_name", None) or getattr(self.args, "name", None)

        try:
            self._ovftool_deploy_ova(source_path, str(target_vm_name) if target_vm_name else None)
            return 0
        except (OvfToolNotFound, OvfToolAuthError, OvfToolSslError, OvfToolError) as e:
            raise Fatal(2, f"OVF Tool deployment failed: {e}") from e
        except Exception as e:
            self.logger.exception("ovftool_deploy: unexpected error")
            raise Fatal(2, f"OVF Tool deployment failed with unexpected error: {e}") from e

    def _handle_download_datastore_file(self, client: VMwareClient, dc_name: str) -> int:
        if not all(
            [
                getattr(self.args, "datastore", None),
                getattr(self.args, "ds_path", None),
                getattr(self.args, "local_path", None),
            ]
        ):
            raise Fatal(
                2, "vsphere download_datastore_file: --datastore, --ds-path, --local-path are required"
            )

        local_path = Path(self.args.local_path).expanduser().resolve()
        chunk_size = int(getattr(self.args, "chunk_size", _DEFAULT_CHUNK_SIZE))
        ds_path = _safe_rel_ds_path(str(self.args.ds_path))

        _download_one_file_with_policy(
            client=client,
            args=self.args,
            vc_host=str(self.args.vcenter),
            dc_name=dc_name,
            ds_name=str(self.args.datastore),
            ds_path=ds_path,
            local_path=local_path,
            verify_tls=not bool(getattr(client, "insecure", False)),
            on_bytes=None,
            chunk_size=chunk_size,
        )

        output = {
            "status": "success",
            "local_path": str(local_path),
            "datastore": str(self.args.datastore),
            "ds_path": ds_path,
            "dc_name": dc_name,
            "transport": _get_transport_preference(self.args),
        }

        if bool(getattr(self.args, "json", False)):
            print(json.dumps(output, indent=2))
        else:
            print(f"Downloaded [{self.args.datastore}] {ds_path} to {local_path}")
        return 0

    # pylint: disable-next=too-many-locals,too-many-branches  # single CLI action handler: resolves VM/paths, applies datastore-dir override, downloads, and formats output
    def _handle_download_only_vm(self, client: VMwareClient, vc_host: str, dc_name: str) -> int:
        vm_name = getattr(self.args, "vm_name", None)
        if not vm_name:
            raise Fatal(2, "vsphere download_only_vm: --vm_name is required")

        vm = client.get_vm_by_name(str(vm_name))
        if not vm:
            raise Fatal(2, f"vsphere: VM not found: {vm_name}")

        out_dir = Path(getattr(self.args, "output_dir", None) or ".").expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        include_glob = list(getattr(self.args, "vs_include_glob", None) or ["*"])
        exclude_glob = list(getattr(self.args, "vs_exclude_glob", None) or [])
        max_files = int(getattr(self.args, "vs_max_files", 5000) or 5000)
        fail_on_missing = bool(getattr(self.args, "vs_fail_on_missing", False))

        try:
            vmx_path = vm.summary.config.vmPathName if vm.summary and vm.summary.config else None
        except Exception:  # pylint: disable=broad-exception-caught  # vm.summary/.config are dynamic pyVmomi properties that can raise arbitrary server-side faults
            vmx_path = None

        if not vmx_path:
            raise Fatal(
                2,
                "vsphere download_only_vm: cannot determine VM folder (vm.summary.config.vmPathName missing)",
            )

        ds_name, folder = _parse_vm_datastore_dir(str(vmx_path))

        override = getattr(self.args, "vs_datastore_dir", None)
        if override:
            try:
                ds_name, folder = _parse_datastore_dir_override(str(override), default_ds=ds_name)
                self.logger.info(
                    "download_only_vm: using vs_datastore_dir override: [%s] %s", ds_name, folder or "."
                )
            except Exception as e:
                raise Fatal(
                    2, f"vsphere download_only_vm: invalid vs_datastore_dir={override!r}: {e}"
                ) from e

        if _debug_enabled(self.args):
            self.logger.debug(
                "download_only_vm: vm=%r vmx_path=%r resolved=[%s] %s out_dir=%r "
                "include=%s exclude=%s max_files=%s fail_on_missing=%s",
                str(vm_name),
                str(vmx_path),
                ds_name,
                folder or ".",
                str(out_dir),
                include_glob,
                exclude_glob,
                max_files,
                fail_on_missing,
            )

        files = _get_vm_files_from_govc(self.govc, ds_name, folder, include_glob, exclude_glob, max_files)

        if not files:
            output = {
                "status": "success",
                "vm_name": str(vm_name),
                "datastore": ds_name,
                "folder": folder,
                "matched": 0,
                "downloaded": 0,
                "output_dir": str(out_dir),
                "include_glob": include_glob,
                "exclude_glob": exclude_glob,
                "listing": "govc",
                "transport_pref": _get_transport_preference(self.args),
            }
            if bool(getattr(self.args, "json", False)):
                print(json.dumps(output, indent=2, default=str))
            else:
                print("No files matched; nothing downloaded.")
            return 0

        self.logger.info(
            "download_only_vm: matched %d files in [%s] %s (listing=govc)",
            len(files),
            ds_name,
            folder or ".",
        )

        verify_tls = not bool(getattr(client, "insecure", False))

        downloaded, errors = self._download_vm_files_with_progress(
            client=client,
            files=files,
            ds_name=ds_name,
            vc_host=vc_host,
            dc_name=dc_name,
            verify_tls=verify_tls,
            out_dir=out_dir,
            fail_on_missing=fail_on_missing,
        )

        output = self._prepare_download_output(
            vm_name=str(vm_name),
            ds_name=ds_name,
            folder=folder,
            out_dir=out_dir,
            files=files,
            downloaded=downloaded,
            errors=errors,
            override=str(override) if override else None,
        )

        if bool(getattr(self.args, "json", False)):
            print(json.dumps(output, indent=2, default=str))
        else:
            print(f"Downloaded {len(downloaded)}/{len(files)} files into {out_dir}")
            if errors:
                print("Some downloads failed:")
                for e in errors[:20]:
                    print(f" - {e}")
                if len(errors) > 20:
                    print(f" ... and {len(errors) - 20} more")
        return 0

    # pylint: disable-next=too-many-arguments,too-many-locals  # per-VM multi-file download needs the full connection/target/policy context
    def _download_vm_files_with_progress(
        self,
        *,
        client: VMwareClient,
        files: list[str],
        ds_name: str,
        vc_host: str,
        dc_name: str,
        verify_tls: bool,
        out_dir: Path,
        fail_on_missing: bool,
    ) -> tuple[list[str], list[str]]:
        downloaded: list[str] = []
        errors: list[str] = []

        progress, files_task, bytes_task = _create_progress_ui(self.args, len(files))

        def download_file(ds_path: str) -> None:
            safe_ds_path = _safe_rel_ds_path(ds_path)
            local_path = out_dir / safe_ds_path
            t0 = time.monotonic()

            def on_bytes(n: int, _total: int) -> None:
                _update_progress(
                    progress,
                    files_task,
                    bytes_task,
                    description=f"downloading: {safe_ds_path}",
                    bytes_advance=n,
                )

            try:
                _download_one_file_with_policy(
                    client=client,
                    args=self.args,
                    vc_host=vc_host,
                    dc_name=dc_name,
                    ds_name=ds_name,
                    ds_path=safe_ds_path,
                    local_path=local_path,
                    verify_tls=verify_tls,
                    on_bytes=on_bytes,
                    chunk_size=int(getattr(self.args, "chunk_size", _DEFAULT_CHUNK_SIZE)),
                )
                downloaded.append(safe_ds_path)
                _update_progress(progress, files_task, bytes_task, files_advance=1)

                if _debug_enabled(self.args):
                    try:
                        sz = local_path.stat().st_size
                    except OSError:
                        sz = None
                    self.logger.debug(
                        "download_only_vm: ok ds_path=%r local=%r size=%s dur=%s",
                        safe_ds_path,
                        str(local_path),
                        U.human_bytes(sz),
                        _fmt_duration(time.monotonic() - t0),
                    )
            except Exception as e:  # pylint: disable=broad-exception-caught  # per-file failure must not abort the rest; re-raised only if fail_on_missing
                msg = f"{safe_ds_path}: {e}"
                errors.append(msg)
                self.logger.info("Download error: %s", safe_ds_path)
                if _debug_enabled(self.args):
                    self.logger.debug(
                        "download_only_vm: fail ds_path=%r dur=%s err=%s",
                        safe_ds_path,
                        _fmt_duration(time.monotonic() - t0),
                        _short_exc(e),
                    )
                if fail_on_missing:
                    raise

        for p in files:
            download_file(p)

        return downloaded, errors

    # pylint: disable-next=too-many-arguments  # assembles the full download-result summary dict (matched/downloaded/errors/config) from its inputs
    def _prepare_download_output(
        self,
        *,
        vm_name: str,
        ds_name: str,
        folder: str,
        out_dir: Path,
        files: list[str],
        downloaded: list[str],
        errors: list[str],
        override: str | None,
    ) -> dict[str, Any]:
        dc_name = _get_dc_name(self.args)
        verify_tls = not bool(getattr(self.args, "vc_insecure", False))

        return {
            "status": "success" if not errors else "partial",
            "vm_name": vm_name,
            "datastore": ds_name,
            "folder": folder,
            "output_dir": str(out_dir),
            "matched": len(files),
            "downloaded": len(downloaded),
            "errors": errors,
            "include_glob": list(getattr(self.args, "vs_include_glob", None) or ["*"]),
            "exclude_glob": list(getattr(self.args, "vs_exclude_glob", None) or []),
            "dc_name": dc_name,
            "verify_tls": verify_tls,
            "listing": "govc",
            "govc_bin": getattr(self.govc, "govc_bin", None) if self.govc.available() else None,
            "vs_datastore_dir": str(override) if override else None,
            "transport_pref": _get_transport_preference(self.args),
            "vddk_experimental": True,
        }
