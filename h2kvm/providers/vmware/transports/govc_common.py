# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/transports/govc_common.py
"""
govc / govmomi common helpers for h2kvm.

Design goals:
  - Best-effort + additive: if govc isn't available, callers can fall back to pyvmomi
  - Be defensive about output shapes and path forms
  - Keep behavior stable: callers decide preference policy; this module provides primitives
  - Make debugging human-friendly: log what we normalize, what we run, and how we parse

NOTE:
  - Workflow-y operations (export ovf/ova, shutdown VM, cdrom removal) are implemented
    in govc_export.py and reused here via thin wrappers.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ....core.exceptions import VMwareError

if TYPE_CHECKING:
    from collections.abc import Sequence

# Optional: use project JSON helpers if present (keeps formatting consistent)
try:  # pragma: no cover
    from ....core.utils import U  # type: ignore
except ImportError:  # pragma: no cover
    U = None  # type: ignore

# Reuse the workflow wrapper (single source of truth)
try:  # pragma: no cover
    from .govc_export import GovcExportSpec, export_vm_govc
except Exception:  # pylint: disable=broad-exception-caught  # optional workflow module; export helpers degrade to raising VMwareError when unavailable
    # pylint: disable=invalid-name
    # These fall back to None (not UPPER_CASE constants) because they alias
    # optionally-imported classes/functions of the same name used below.
    GovcExportSpec = None  # type: ignore
    export_vm_govc = None  # type: ignore


# Datastore path normalization (accepts "[ds] path" or "path")

_DS_BACKING_RE = re.compile(r"^\[(?P<ds>[^\]]+)\]\s*(?P<path>.+)$")


def normalize_ds_path(datastore: str, ds_path: str) -> tuple[str, str]:
    """
    Normalize datastore paths for govc.

    Accepts:
      - "[datastore] folder/file"
      - "folder/file"
      - "/folder/file"

    Returns:
      (datastore, "folder/file")  # datastore-relative, no leading slash
    """
    s = (ds_path or "").strip()
    if not s:
        raise VMwareError(
            "Datastore path is empty. Provide the path in one of these formats:\n"
            '  - "[datastore1] vm-folder/disk.vmdk" (full datastore path)\n'
            '  - "vm-folder/disk.vmdk" (relative to datastore root)\n'
            "You can find datastore paths in vSphere: Datastore Browser or VM Settings."
        )

    m = _DS_BACKING_RE.match(s)
    if m:
        ds = (m.group("ds") or "").strip()
        path = (m.group("path") or "").strip()
        return (ds or datastore), path.lstrip("/")

    return datastore, s.lstrip("/")


# Resilient parsing for `govc datastore.ls -json`


def _flatten_any(obj: Any) -> list[Any]:
    """Flatten nested dict/list structures into a list of candidate file entries."""
    if obj is None:
        return []
    if isinstance(obj, list):
        out: list[Any] = []
        for v in obj:
            out.extend(_flatten_any(v))
        return out
    if isinstance(obj, dict):
        # Most common keys seen across govc versions
        for k in ("file", "File", "files", "Files", "items", "Items", "Elements", "elements"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
        out = []
        for v in obj.values():
            if isinstance(v, (dict, list)):
                out.extend(_flatten_any(v))
        return out
    return []


def _extract_path(ent: Any) -> str | None:
    if ent is None:
        return None
    if isinstance(ent, str):
        return ent
    if isinstance(ent, dict):
        # govc datastore.ls -json (newer) often uses: {"path": "..."}
        for k in ("path", "Path", "FilePath", "Name", "name"):
            v = ent.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def extract_paths_from_datastore_ls_json(data: Any) -> list[str]:
    """
    Extract file paths from govc datastore.ls -json output.

    Known shapes (examples):
      - [ { "folderPath": "[ds] folder/", "file": [ {"path": "a.vmdk"}, ... ] } ]
      - { "file": [ {"path": "a.vmdk"}, ... ] }
      - { "Files": [ {"Path": "a.vmdk"}, ... ] }
      - { "Elements": [ "a.vmdk", ... ] }

    Returns:
      List[str] of extracted paths (as provided by govc), with leading slashes stripped.
      Callers may further normalize relative-to-folder behavior.
    """
    raw = _flatten_any(data)
    out: list[str] = []
    for ent in raw:
        p = _extract_path(ent)
        if not p:
            continue
        out.append(str(p).lstrip("/"))

    # De-dup while preserving order
    seen = set()
    uniq: list[str] = []
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


@dataclass
class GovcConfig:  # pylint: disable=too-many-instance-attributes
    """govc CLI + vCenter connection configuration."""

    govc_bin: str = "govc"
    disable: bool = False  # user requested no govmomi/govc

    vcenter: str | None = None
    vc_user: str | None = None
    vc_password: str | None = None
    vc_password_env: str | None = None
    vc_insecure: bool = False
    dc_name: str | None = None


def _looks_like_govc_usage(text: str) -> bool:
    """
    Check if text looks like govc usage/help output using regex patterns.
    """
    t = (text or "").strip()
    if not t:
        return False

    usage_patterns = [
        r"^Usage:\s*govc\s*<COMMAND>",
        r"The available commands are listed below",
        r"govmomi is a Go library for interacting",
    ]

    return any(re.search(p, t, re.IGNORECASE) for p in usage_patterns)


def _extract_vm_info_with_regex(text: str) -> dict[str, str]:
    """Extract VM info using regex patterns."""
    patterns = {
        "name": r"^Name:\s*(.+)$",
        "power_state": r"Power\s+state:\s*(.+)$",
        "storage": r"Storage\s*(?:committed|used)?:\s*(.+)$",
        "path": r"Path:\s*(.+)$",
        "guest_os": r"Guest\s+OS:\s*(.+)$",
        "memory": r"Memory\s+size:\s*(.+)$",
        "cpus": r"CPU\s*(?:s)?:\s*(.+)$",
        "instance_uuid": r"Instance\s+UUID:\s*(.+)$",
        "bios_uuid": r"BIOS\s+UUID:\s*(.+)$",
    }

    info: dict[str, str] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            info[key] = match.group(1).strip()

    return info


def _mask_secret(v: str | None) -> str:
    if not v:
        return "<unset>"
    vv = str(v)
    if len(vv) <= 4:
        return "***"
    return f"{vv[:2]}***{vv[-2:]}"


def _log(logger: Any, level: str, msg: str, *args: Any) -> None:
    """Safe logger wrapper that never raises."""
    try:
        fn = getattr(logger, level, None)
        if callable(fn):
            fn(msg, *args)
            return
    except Exception:  # pylint: disable=broad-exception-caught  # logging helper must never raise, whatever the logger object does
        pass
    try:
        print((msg % args) if args else msg)
    except Exception:  # pylint: disable=broad-exception-caught  # logging helper must never raise, even on the final print fallback
        return


def _summarize_json_shape(  # pylint: disable=too-many-return-statements
    # Debug-only helper: each branch is a distinct data shape (None/list/dict/scalar).
    data: Any,
) -> str:
    """Return a short human-readable description of `data`'s shape, for debug logs."""
    try:
        if data is None:
            return "None"
        if isinstance(data, list):
            if not data:
                return "list(len=0)"
            head = data[0]
            if isinstance(head, dict):
                keys = sorted(head.keys())
                return f"list(len={len(data)}), head_keys={keys}"
            return f"list(len={len(data)}), head_type={type(head).__name__}"
        if isinstance(data, dict):
            keys = sorted(data.keys())
            return f"dict(keys={keys})"
        return type(data).__name__
    except Exception:  # pylint: disable=broad-exception-caught  # debug-shape helper, must never raise
        return "<shape-unavailable>"


def _json_loads_best_effort(text: str) -> Any:
    """
    Parse JSON, preferring project helper if it exists and is callable.
    Fixes the common failure mode: U is present but doesn't implement json_loads.
    """
    if U is not None:
        jl = getattr(U, "json_loads", None)
        if callable(jl):
            return jl(text)  # pylint: disable=not-callable  # guarded by callable(jl) above; pylint can't narrow the Optional[Any] from getattr()
    return json.loads(text)


def _normalize_runner_env(env: dict[str, str]) -> dict[str, str]:
    """
    IMPORTANT FIX:
      We must pass a *complete* environment to subprocess calls (inherit os.environ),
      not a tiny dict containing only GOVC_* vars.
    """
    merged = dict(os.environ)
    merged.update(env or {})
    return merged


def _fmt_head(s: Any, limit: int = 2000) -> str:
    """Return `s` stringified and truncated to `limit` chars, or "" on any failure."""
    try:
        t = "" if s is None else str(s)
        t = t.strip()
        if not t:
            return ""
        if len(t) <= limit:
            return t
        return t[:limit] + "…"
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort formatting for diagnostics, must never raise
        return ""


def _format_export_exception(e: BaseException) -> str:
    """
    Preserve details from GovcExportError (or anything that stashes rc/cmd/stdout/stderr).
    This is the main fix for the useless 'VMwareError: error' symptom.
    """
    # If govc_export.py defines a rich exception, harvest common fields.
    parts: list[str] = []

    etype = type(e).__name__
    msg = str(e).strip()
    if msg:
        parts.append(f"{etype}: {msg}")
    else:
        parts.append(f"{etype}")

    # Common attribute names we might have in GovcExportError or wrappers
    cmd = getattr(e, "cmd", None) or getattr(e, "command", None)
    rc = getattr(e, "rc", None) or getattr(e, "returncode", None)
    stdout = getattr(e, "stdout", None) or getattr(e, "out", None)
    stderr = getattr(e, "stderr", None) or getattr(e, "err", None)

    if cmd:
        if isinstance(cmd, (list, tuple)):
            parts.append(f"cmd={' '.join(str(x) for x in cmd)}")
        else:
            parts.append(f"cmd={cmd}")

    if rc is not None:
        parts.append(f"rc={rc}")

    sh = _fmt_head(stdout)
    eh = _fmt_head(stderr)
    if eh:
        parts.append(f"stderr={eh}")
    if sh and not eh:
        # if stderr is empty but stdout has useful content, include it
        parts.append(f"stdout={sh}")

    # If the message is literally "error" and we found no extra fields, add repr()
    if (msg.lower() == "error") and (len(parts) <= 1):
        parts.append(f"repr={e!r}")

    return " | ".join(parts)


class GovcRunner:
    """
    Minimal govc execution helper.

    - Seeds GOVC_* from args/config (additive: doesn't override user env unless missing).
    - Provides run_text/run_json + availability checks.
    - Detects the "usage blob" failure mode (arg parse failure) and throws clearly.
    - Emits debug logs describing normalization, env seeding, parsing, and results.

    Also provides thin wrappers to the workflow module govc_export.py for OVF/OVA exports.
    """

    def __init__(self, *, logger: Any, args: Any):
        self.logger = logger
        self.args = args
        self.govc_bin = getattr(args, "govc_bin", None) or os.environ.get("GOVC_BIN", "govc")

    # -------- policy / availability

    def available(self) -> bool:
        """Return True if the govc binary runs and reports version 0."""
        try:
            p = subprocess.run(
                [self.govc_bin, "version"],
                capture_output=True,
                check=False,
                text=True,
                env=_normalize_runner_env({}),
            )
            ok = p.returncode == 0
            _log(self.logger, "debug", "govc.available: bin=%s rc=%s", self.govc_bin, p.returncode)
            if not ok:
                _log(self.logger, "debug", "govc.available: stderr=%s", (p.stderr or "").strip()[:800])
            return ok
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort availability probe, must not raise
            _log(self.logger, "debug", "govc.available: exception=%r", e)
            return False

    def enabled(self) -> bool:
        """Return True if govc is not disabled by args and is available."""
        if bool(getattr(self.args, "no_govmomi", False)):
            _log(self.logger, "debug", "govc.enabled: disabled by --no-govmomi/args.no_govmomi")
            return False
        ok = self.available()
        _log(self.logger, "debug", "govc.enabled: %s", ok)
        return ok

    # -------- env + execution

    def env(self) -> dict[str, str]:
        """Build the subprocess environment, seeding GOVC_* vars from args if unset."""
        env = dict(os.environ)

        vc_host = getattr(self.args, "vcenter", None)
        vc_user = getattr(self.args, "vc_user", None)
        vc_pass = getattr(self.args, "vc_password", None)

        vc_pass_env = getattr(self.args, "vc_password_env", None)
        if not vc_pass and vc_pass_env:
            vc_pass = os.environ.get(str(vc_pass_env))

        if isinstance(vc_pass, str):
            vc_pass = vc_pass.strip() or None

        # Additive seeding (don't stomp user env)
        if vc_host and not env.get("GOVC_URL"):
            env["GOVC_URL"] = f"https://{vc_host}/sdk"
        if vc_user and not env.get("GOVC_USERNAME"):
            env["GOVC_USERNAME"] = str(vc_user)
        if vc_pass and not env.get("GOVC_PASSWORD"):
            env["GOVC_PASSWORD"] = str(vc_pass)

        insecure = bool(getattr(self.args, "vc_insecure", False))
        if insecure:
            env["GOVC_INSECURE"] = env.get("GOVC_INSECURE", "1")

        dc = getattr(self.args, "dc_name", None)
        if dc and not env.get("GOVC_DATACENTER"):
            env["GOVC_DATACENTER"] = str(dc)

        _log(
            self.logger,
            "debug",
            "govc.env: GOVC_URL=%s GOVC_USERNAME=%s GOVC_PASSWORD=%s GOVC_INSECURE=%s "
            "GOVC_DATACENTER=%s (vc_password_env=%s)",
            env.get("GOVC_URL", "<unset>"),
            env.get("GOVC_USERNAME", "<unset>"),
            env.get("GOVC_PASSWORD", "<unset>") and _mask_secret(env.get("GOVC_PASSWORD")),
            env.get("GOVC_INSECURE", "<unset>"),
            env.get("GOVC_DATACENTER", "<unset>"),
            vc_pass_env or "<unset>",
        )
        return env

    def run_text(self, cmd: Sequence[str]) -> str:
        """Run `govc <cmd>` and return its stdout, raising VMwareError on failure."""
        full = [self.govc_bin, *list(cmd)]
        _log(self.logger, "debug", "govc.exec: %s", " ".join(full))

        env = _normalize_runner_env(self.env())

        p = subprocess.run(
            full,
            capture_output=True,
            env=env,
            text=True,
            check=False,
        )

        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()

        _log(
            self.logger,
            "debug",
            "govc.exec: rc=%s stdout_len=%d stderr_len=%d",
            p.returncode,
            len(out),
            len(err),
        )
        if err:
            _log(self.logger, "debug", "govc.exec: stderr(head)=%s", err[:1200])
        if out:
            _log(self.logger, "debug", "govc.exec: stdout(head)=%s", out[:1200])

        if _looks_like_govc_usage(out) or _looks_like_govc_usage(err):
            raise VMwareError(
                "govc printed usage/help output instead of command output "
                "(likely argument parsing issue). "
                f"cmd={' '.join(full)}"
            )

        if p.returncode != 0:
            detail = err or out[:1200]
            raise VMwareError(f"govc failed ({p.returncode}): {detail}")

        return out

    def run_json(self, cmd: Sequence[str]) -> Any:
        """Run `govc <cmd>` and parse its stdout as JSON, raising VMwareError on failure."""
        out = self.run_text(cmd)
        if not out:
            _log(self.logger, "debug", "govc.json: empty output (cmd=%s)", " ".join(cmd))
            return None
        try:
            _log(self.logger, "debug", "govc.json: parsing len=%d head=%s", len(out), out[:200])
            data = _json_loads_best_effort(out)  # best-effort JSON loader
            _log(self.logger, "debug", "govc.json: parsed shape=%s", _summarize_json_shape(data))
            return data
        except Exception as e:  # pylint: disable=broad-exception-caught  # any parse failure must surface as a clear VMwareError, not a bare JSON exception
            raise VMwareError(f"govc returned non-JSON output: {e}: {out[:2000]}") from e

    def run(self, cmd: Sequence[str], *, json_output: bool = False) -> Any:
        """
        Backwards-compatible shim.

        Older callers expect GovcRunner.run([...]) -> str
        Some callers may want JSON.
        """
        if json_output:
            return self.run_json(cmd)
        return self.run_text(cmd)

    def datastore_ls_text(self, datastore: str, ds_dir: str) -> list[str]:
        """Return the plain-text lines from `govc datastore.ls -ds <datastore> <ds_dir>/`."""
        ds, rel = normalize_ds_path(datastore, ds_dir)
        rel = rel.rstrip("/") + "/"
        _log(self.logger, "debug", "datastore_ls_text: ds=%s ds_dir=%s -> rel=%s", ds, ds_dir, rel)

        out = self.run_text(["datastore.ls", "-ds", str(ds), rel])
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        _log(self.logger, "debug", "datastore_ls_text: lines=%d sample=%s", len(lines), lines[:8])
        return lines

    def datastore_ls_json(self, datastore: str, ds_dir: str) -> list[str]:
        """Returns paths from `govc datastore.ls -json` (relative to ds_dir when possible)."""
        ds, rel = normalize_ds_path(datastore, ds_dir)
        rel = rel.rstrip("/") + "/"

        _log(self.logger, "debug", "datastore_ls_json: ds=%s ds_dir=%s -> rel=%s", ds, ds_dir, rel)

        # NOTE: govc arg order matters; path must be last.
        data = self.run_json(["datastore.ls", "-json", "-ds", str(ds), rel])

        paths = extract_paths_from_datastore_ls_json(data)
        _log(self.logger, "debug", "datastore_ls_json: extracted=%d sample=%s", len(paths), paths[:12])

        # Attempt to strip folder prefix when govc returns it (varies by version)
        base = rel.lstrip("/")
        prefix = base.rstrip("/") + "/"

        cleaned: list[str] = []
        stripped = 0
        for p in paths:
            pp = p.lstrip("/")
            if base and pp.startswith(prefix):
                pp = pp[len(prefix) :]
                stripped += 1
            cleaned.append(pp)

        cleaned = [p for p in cleaned if p]
        _log(
            self.logger,
            "debug",
            "datastore_ls_json: cleaned=%d stripped_prefix=%d prefix=%s sample=%s",
            len(cleaned),
            stripped,
            prefix,
            cleaned[:12],
        )
        return cleaned

    # VM info extraction with regex

    def get_vm_info(self, vm: str) -> dict[str, str]:
        """Get VM information using regex parsing."""
        try:
            output = self.run_text(["vm.info", vm])
            return _extract_vm_info_with_regex(output)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort VM info lookup, must not abort the caller
            _log(self.logger, "debug", "Failed to get VM info: %s", e)
            return {}

    # VM export helpers (OVF/OVA) - thin wrappers, reuse govc_export.py

    def export_ovf(  # pylint: disable=too-many-arguments,too-many-locals
        # Each keyword-only parameter maps 1:1 onto a GovcExportSpec field;
        # collapsing them would just move the same surface area into a dict.
        self,
        *,
        vm: str,
        out_dir: str,
        snapshot: str | None = None,  # currently unused by govc_export.py
        power_off: bool = False,
        disk_mode: str | None = None,  # currently unused by govc_export.py
        extra_args: Sequence[str] | None = None,  # currently unused by govc_export.py
        remove_cdroms: bool = True,
        show_vm_info: bool = True,
        shutdown: bool = False,
        shutdown_timeout_s: float = 300.0,
        shutdown_poll_s: float = 5.0,
        clean_outdir: bool = False,
        show_progress: bool = True,
        prefer_pty: bool = True,
    ) -> str:
        """
        Export a VM as an OVF directory.

        Delegates the workflow to govc_export.py (single source of truth).
        """
        if export_vm_govc is None or GovcExportSpec is None:
            raise VMwareError("govc_export.py not available to perform export")

        if not vm or not str(vm).strip():
            raise VMwareError("govc export.ovf: empty vm")
        if not out_dir or not str(out_dir).strip():
            raise VMwareError("govc export.ovf: empty out_dir")

        if snapshot or disk_mode or extra_args:
            _log(
                self.logger,
                "debug",
                "govc.export.ovf: snapshot/disk_mode/extra_args currently ignored by govc_export.py "
                "(snapshot=%r disk_mode=%r extra_args=%r)",
                snapshot,
                disk_mode,
                list(extra_args) if extra_args else None,
            )

        try:
            export_vm_govc(
                self.logger if hasattr(self.logger, "info") else logging.getLogger(__name__),
                GovcExportSpec(
                    vm=str(vm),
                    outdir=Path(str(out_dir)),
                    mode="ovf",
                    govc_bin=str(self.govc_bin),
                    env=self.env(),  # NOTE: govc_export merges with os.environ internally
                    remove_cdroms=bool(remove_cdroms),
                    show_vm_info=bool(show_vm_info),
                    shutdown=bool(shutdown),
                    shutdown_timeout_s=float(shutdown_timeout_s),
                    shutdown_poll_s=float(shutdown_poll_s),
                    power_off=bool(power_off),
                    clean_outdir=bool(clean_outdir),
                    show_progress=bool(show_progress),
                    prefer_pty=bool(prefer_pty),
                ),
            )
        except Exception as e:
            # 🔥 Critical: preserve govc stderr/cmd/rc instead of collapsing to "error"
            raise VMwareError(_format_export_exception(e)) from e

        return f"exported ovf: vm={vm} out_dir={out_dir}"

    def export_ova(  # pylint: disable=too-many-arguments,too-many-locals
        # Each keyword-only parameter maps 1:1 onto a GovcExportSpec field;
        # collapsing them would just move the same surface area into a dict.
        self,
        *,
        vm: str,
        out_file: str,
        snapshot: str | None = None,  # currently unused by govc_export.py
        power_off: bool = False,
        disk_mode: str | None = None,  # currently unused by govc_export.py
        extra_args: Sequence[str] | None = None,  # currently unused by govc_export.py
        remove_cdroms: bool = True,
        show_vm_info: bool = True,
        shutdown: bool = False,
        shutdown_timeout_s: float = 300.0,
        shutdown_poll_s: float = 5.0,
        clean_outdir: bool = False,
        show_progress: bool = True,
        prefer_pty: bool = True,
    ) -> str:
        """
        Export a VM as OVA.

        Delegates the workflow to govc_export.py (single source of truth).
        """
        if export_vm_govc is None or GovcExportSpec is None:
            raise VMwareError("govc_export.py not available to perform export")

        if not vm or not str(vm).strip():
            raise VMwareError("govc export.ova: empty vm")
        if not out_file or not str(out_file).strip():
            raise VMwareError("govc export.ova: empty out_file")

        if snapshot or disk_mode or extra_args:
            _log(
                self.logger,
                "debug",
                "govc.export.ova: snapshot/disk_mode/extra_args currently ignored by govc_export.py "
                "(snapshot=%r disk_mode=%r extra_args=%r)",
                snapshot,
                disk_mode,
                list(extra_args) if extra_args else None,
            )

        out_path = Path(str(out_file)).expanduser().resolve()
        out_dir = out_path.parent
        ova_name = out_path.name

        try:
            export_vm_govc(
                self.logger if hasattr(self.logger, "info") else logging.getLogger(__name__),
                GovcExportSpec(
                    vm=str(vm),
                    outdir=Path(str(out_dir)),
                    mode="ova",
                    govc_bin=str(self.govc_bin),
                    env=self.env(),  # NOTE: govc_export merges with os.environ internally
                    remove_cdroms=bool(remove_cdroms),
                    show_vm_info=bool(show_vm_info),
                    ova_filename=str(ova_name),
                    shutdown=bool(shutdown),
                    shutdown_timeout_s=float(shutdown_timeout_s),
                    shutdown_poll_s=float(shutdown_poll_s),
                    power_off=bool(power_off),
                    clean_outdir=bool(clean_outdir),
                    show_progress=bool(show_progress),
                    prefer_pty=bool(prefer_pty),
                ),
            )
        except Exception as e:
            # 🔥 Critical: preserve govc stderr/cmd/rc instead of collapsing to "error"
            raise VMwareError(_format_export_exception(e)) from e

        return f"exported ova: vm={vm} out_file={out_file}"

    # CD/DVD device management

    def get_cdrom_devices(self, vm: str) -> list[str]:
        """Get list of CD/DVD devices for a VM."""
        try:
            output = self.run_text(["device.ls", "-vm", vm])
            lines = output.splitlines()

            cdrom_pattern = re.compile(r"^(cdrom-\w+)", re.IGNORECASE)
            devices: list[str] = []

            for line in lines:
                line = line.strip()
                match = cdrom_pattern.match(line)
                if match:
                    devices.append(match.group(1))
                elif re.search(r"cdrom", line, re.IGNORECASE):
                    parts = line.split()
                    if parts:
                        devices.append(parts[0])

            # De-dup keep order
            unique_devices: list[str] = []
            seen = set()
            for dev in devices:
                if dev not in seen:
                    seen.add(dev)
                    unique_devices.append(dev)

            return unique_devices

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort device listing, must not abort the caller
            _log(self.logger, "debug", "Failed to get CD/DVD devices: %s", e)
            return []

    def remove_cdrom_devices(self, vm: str) -> None:
        """Remove all CD/DVD devices from VM."""
        devices = self.get_cdrom_devices(vm)
        if not devices:
            _log(self.logger, "debug", "No CD/DVD devices found to remove")
            return

        for device in devices:
            try:
                _log(self.logger, "debug", "Removing CD/DVD device: %s", device)
                self.run_text(["device.remove", "-vm", vm, device])
            except Exception as e:  # pylint: disable=broad-exception-caught  # per-device removal, must not abort removing the rest; falls back to eject
                _log(self.logger, "debug", "Failed to remove device %s: %s", device, e)
                # Fallback: try ejecting (best-effort)
                with contextlib.suppress(Exception):
                    self.run_text(["device.cdrom.eject", "-vm", vm])
