# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/transports/ovftool_client.py
"""
ovftool wrapper client for h2kvm.

This module provides a **thin, defensive, no-threads** wrapper around Broadcom/VMware
OVF Tool ("ovftool") to export/import OVF/OVA from/to vSphere endpoints.

Notes:
  - ovftool is proprietary and must be installed by the user.
  - It can export from:
      - vCenter / ESXi: vi://user:pass@host/...
      - local: OVF/OVA to local, or deploy local OVF/OVA to vi://
  - ovftool accepts both OVF directory and OVA file outputs depending on destination.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# Optional: select for single-flow multiplexing stdout/stderr without threads
# (shared availability probe, centralized in utils/compat.py to avoid
# duplicating this try/except stub across vmware provider modules)
from h2kvm.providers.vmware.utils.compat import SELECT_AVAILABLE, select

if TYPE_CHECKING:
    from collections.abc import Sequence


# Errors
class OvfToolError(RuntimeError):
    """Generic ovftool failure."""


class OvfToolNotFound(OvfToolError):
    """Raised when ovftool binary cannot be found."""


class OvfToolAuthError(OvfToolError):
    """Likely authentication/permission failure (best-effort classification)."""


class OvfToolSslError(OvfToolError):
    """Likely SSL/certificate/handshake failure (best-effort classification)."""


# Regex helpers for parsing output
_PROGRESS_RE = re.compile(r"^\s*Progress:\s*(\d+)\s*%\s*$", re.IGNORECASE)
_VERSION_RE = re.compile(r"^\s*VMware\s+OVF\s+Tool\s+([\w\.\-\+]+)", re.IGNORECASE)
# Some ovftool builds print "Error:" lines; keep it loose.
_ERROR_HINT_RE = re.compile(r"\b(error|failed|exception)\b", re.IGNORECASE)

# Very common strings you might see; used only for *best-effort* error typing
_SSL_HINTS = (
    "SSL",
    "CERTIFICATE",
    "handshake",
    "thumbprint",
    "noSSLVerify",
    "PKIX",
    "x509",
)
_AUTH_HINTS = (
    "authentication",
    "permission",
    "not authorized",
    "unauthorized",
    "invalid login",
    "denied",
)


# Config dataclasses
@dataclass(frozen=True)
class OvfToolPaths:
    """Resolved ovftool binary path."""

    ovftool_bin: str


@dataclass(frozen=True)
class OvfExportOptions:  # pylint: disable=too-many-instance-attributes  # models every independent ovftool export flag
    """
    Export options for ovftool.

    Many flags are "pass-through"; if you need something not modeled here,
    use extra_args.
    """

    # TLS / endpoint
    no_ssl_verify: bool = True
    thumbprint: str | None = None  # e.g. "AA:BB:..."; used with vi:// endpoints

    # Legal / UX
    accept_all_eulas: bool = True
    quiet: bool = False
    verbose: bool = False

    # Output shape
    overwrite: bool = False

    # VM / disk behavior (commonly useful for deploy/import, harmless on export)
    disk_mode: str | None = None  # "thin" | "thick" | "eagerZeroedThick" (depends on target)

    # Optional retry wrapper (our wrapper, not ovftool internal)
    retries: int = 0
    retry_backoff_s: float = 2.0

    # Extra raw args appended last (advanced escape hatch)
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class OvfDeployOptions:  # pylint: disable=too-many-instance-attributes  # models every independent ovftool deploy flag
    """
    Deploy options for importing OVF/OVA to vSphere via ovftool.

    This is a minimal starter set; ovftool has a huge surface area.
    """

    no_ssl_verify: bool = True
    thumbprint: str | None = None
    accept_all_eulas: bool = True

    overwrite: bool = False
    power_on: bool = False

    # Placement knobs (some are expressed as --prop:, --net:, etc; keep generic)
    name: str | None = None  # --name=...
    datastore: str | None = None  # --datastore=...
    network_map: tuple[tuple[str, str], ...] = ()  # (src_net, dst_net) -> --net:"src"="dst"

    # Disk / provisioning
    disk_mode: str | None = None  # "thin" etc.

    quiet: bool = False
    verbose: bool = False

    retries: int = 0
    retry_backoff_s: float = 2.0
    extra_args: tuple[str, ...] = ()


# UI helpers (plain box-drawing)
def _print_panel(title: str, body: str = "") -> None:
    """
    Render a panel like:

    ╭─────────────────────────────────────────────────────────╮
    │ ✓ Export completed successfully! │
    ╰─────────────────────────────────────────────────────────╯
    """
    inner_w = max(57, len(title) + 6, *(len(x) + 4 for x in body.splitlines() if x.strip()))  # type: ignore[arg-type]
    line = "─" * inner_w
    print(f"╭{line}╮")

    t = title
    if len(t) > inner_w - 2:
        t = t[: inner_w - 3] + "…"
    print(f"│ {t:<{inner_w - 2}} │")

    if body.strip():
        for bl in body.splitlines():
            s = bl.rstrip("\n")
            if len(s) > inner_w - 2:
                s = s[: inner_w - 3] + "…"
            print(f"│ {s:<{inner_w - 2}} │")

    print(f"╰{line}╯")


def _info_line(msg: str) -> None:
    print(msg)


def _warn_line(msg: str) -> None:
    print(f"WARNING: {msg}")


def _ok_line(msg: str) -> None:
    # match your sample: "  ✓ Removed: cdrom-1000"
    print(f" ✓ {msg}")


def _fmt_elapsed(start_time: float) -> tuple[int, int]:
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return minutes, seconds


# Public API
def find_ovftool(explicit_path: str | None = None) -> OvfToolPaths:
    """
    Resolve ovftool binary.

    Search order:
      1) explicit_path if provided
      2) $OVFTOOL or $OVFTOOL_BIN
      3) PATH via shutil.which("ovftool")
      4) common install locations (best-effort)
    """
    candidates: list[str] = []

    if explicit_path:
        candidates.append(explicit_path)

    env_bin = os.environ.get("OVFTOOL") or os.environ.get("OVFTOOL_BIN")
    if env_bin:
        candidates.append(env_bin)

    which = shutil.which("ovftool")
    if which:
        candidates.append(which)

    # Common locations (Linux)
    candidates.extend(
        [
            "/usr/bin/ovftool",
            "/usr/local/bin/ovftool",
            "/opt/vmware/ovftool/ovftool",
            "/opt/vmware/ovf-tool/ovftool",
            "/opt/ovftool/ovftool",
        ]
    )

    for c in candidates:
        p = Path(c).expanduser()
        if p.is_file() and os.access(str(p), os.X_OK):
            return OvfToolPaths(ovftool_bin=str(p))

    raise OvfToolNotFound(
        "ovftool binary not found. Install OVF Tool and ensure 'ovftool' is in PATH, "
        "or set OVFTOOL=/path/to/ovftool."
    )


def ovftool_version(paths: OvfToolPaths) -> str | None:
    """Return ovftool version string if detected, else None."""
    rc, out, _err = _run_capture([paths.ovftool_bin, "--version"])
    if rc != 0:
        return None
    for line in out.splitlines():
        m = _VERSION_RE.search(line)
        if m:
            return m.group(1)
    # Some builds just output a version number; fallback to first non-empty line
    for line in out.splitlines():
        s = line.strip()
        if s:
            return s
    return None


def export_to_ovf_or_ova(  # pylint: disable=too-many-arguments
    *,
    paths: OvfToolPaths,
    source: str,
    destination: str | Path,
    options: OvfExportOptions | None = None,
    env: dict[str, str] | None = None,
    log_prefix: str = "ovftool",
) -> None:
    """
    Export from a vSphere endpoint (or other ovftool-supported source) to OVF directory or OVA file.

    Examples:
      source: "vi://administrator@vsphere.local:pass@vcenter.example/DC/vm/MyVM"
      destination: "/var/tmp/MyVM.ova" (OVA)
      destination: "/var/tmp/MyVM-ovf/" (OVF dir)

    Important:
      - Do NOT embed passwords in logs. This module masks vi:// credentials on logging.
    """
    opt = options or OvfExportOptions()
    dest_path = Path(destination).expanduser()
    dest = str(dest_path)

    mode = "OVA" if dest_path.suffix.lower() == ".ova" else "OVF"
    _print_panel(
        title="Exporting via ovftool",
        body=f"Mode: {mode} | Output: {dest}\nSource: {_mask_vi_credentials(source)}",
    )
    _info_line(f"Starting {mode} export...")
    _info_line("This may take several minutes depending on disk size...\n")

    cmd: list[str] = [paths.ovftool_bin]
    cmd.extend(_common_flags(no_ssl_verify=opt.no_ssl_verify, thumbprint=opt.thumbprint))
    if opt.accept_all_eulas:
        cmd.append("--acceptAllEulas")
    if opt.quiet:
        cmd.append("--quiet")
    if opt.verbose:
        cmd.append("--X:logLevel=verbose")  # best-effort; harmless if ignored

    if opt.overwrite:
        cmd.append("--overwrite")

    if opt.disk_mode:
        # Not always meaningful for export, but some environments expect it.
        cmd.append(f"--diskMode={opt.disk_mode}")

    cmd.extend(opt.extra_args)
    cmd.append(source)
    cmd.append(dest)

    start = time.time()
    _run_with_retries(
        cmd=cmd,
        retries=opt.retries,
        backoff_s=opt.retry_backoff_s,
        env=env,
        log_prefix=log_prefix,
    )
    m, s = _fmt_elapsed(start)
    _ok_line(f"{mode} export completed in {m}m {s}s")
    _info_line(f"Output: {dest}\n")
    _print_panel("✓ Export completed successfully!", "")


def export_to_ova(  # pylint: disable=too-many-arguments
    *,
    paths: OvfToolPaths,
    source: str,
    ova_path: str | Path,
    options: OvfExportOptions | None = None,
    env: dict[str, str] | None = None,
    log_prefix: str = "ovftool",
) -> None:
    """Convenience wrapper to export explicitly to an .ova file."""
    p = Path(ova_path).expanduser()
    if p.suffix.lower() != ".ova":
        raise ValueError(f"ova_path must end with .ova, got: {p}")
    export_to_ovf_or_ova(
        paths=paths,
        source=source,
        destination=p,
        options=options,
        env=env,
        log_prefix=log_prefix,
    )


def deploy_ovf_or_ova(  # pylint: disable=too-many-arguments
    *,
    paths: OvfToolPaths,
    source_ovf_or_ova: str | Path,
    target_vi: str,
    options: OvfDeployOptions | None = None,
    env: dict[str, str] | None = None,
    log_prefix: str = "ovftool",
) -> None:
    """
    Deploy/import an OVF directory or OVA file to a vSphere target.

    source_ovf_or_ova:
      - "/path/to/vm.ova"
      - "/path/to/vm.ovf"
      - "/path/to/ovf-dir/" (contains .ovf)

    target_vi example:
      - "vi://administrator@vsphere.local:pass@vcenter.example/DC/host/Cluster/Resources"
      - Sometimes you deploy to a specific host or folder; ovftool URL shapes vary.

    This wrapper models only a small set of common knobs; use extra_args for the rest.
    """
    opt = options or OvfDeployOptions()
    srcp = Path(source_ovf_or_ova).expanduser()
    src = str(srcp)

    _print_panel(
        title="Deploying via ovftool",
        body=f"Source: {src}\nTarget: {_mask_vi_credentials(target_vi)}",
    )
    _info_line("Starting deploy/import...")
    _info_line("This may take several minutes depending on disk size...\n")

    cmd: list[str] = [paths.ovftool_bin]
    cmd.extend(_common_flags(no_ssl_verify=opt.no_ssl_verify, thumbprint=opt.thumbprint))
    if opt.accept_all_eulas:
        cmd.append("--acceptAllEulas")
    if opt.quiet:
        cmd.append("--quiet")
    if opt.verbose:
        cmd.append("--X:logLevel=verbose")

    if opt.overwrite:
        cmd.append("--overwrite")
    if opt.power_on:
        cmd.append("--powerOn")

    if opt.name:
        cmd.append(f"--name={opt.name}")

    if opt.datastore:
        cmd.append(f"--datastore={opt.datastore}")

    if opt.disk_mode:
        cmd.append(f"--diskMode={opt.disk_mode}")

    for src_net, dst_net in opt.network_map:
        # ovftool expects quoting around names containing spaces; we pass raw and let subprocess handle.
        cmd.append(f"--net:{src_net}={dst_net}")

    cmd.extend(opt.extra_args)
    cmd.append(src)
    cmd.append(target_vi)

    start = time.time()
    _run_with_retries(
        cmd=cmd,
        retries=opt.retries,
        backoff_s=opt.retry_backoff_s,
        env=env,
        log_prefix=log_prefix,
    )
    m, s = _fmt_elapsed(start)
    _ok_line(f"Deploy completed in {m}m {s}s")
    _print_panel("✓ Deploy completed successfully!", "")


# Internals
def _common_flags(*, no_ssl_verify: bool, thumbprint: str | None) -> list[str]:
    flags: list[str] = []
    if no_ssl_verify:
        flags.append("--noSSLVerify")
    if thumbprint:
        flags.append(f"--thumbprint={thumbprint}")
    return flags


def _mask_vi_credentials(s: str) -> str:
    """
    Mask vi://user:pass@host style credentials.

    Best-effort: we mask anything between 'vi://' and '@' if it contains ':'.

    vi://user:pass@host/... -> vi://user:****@host/...
    """
    return re.sub(r"(vi://[^/@:]+:)([^@]+)(@)", r"\1****\3", s)


def _fmt_cmd_for_log(cmd: Sequence[str]) -> str:
    # Quote for shell-like readability, mask secrets on each token
    toks = [_mask_vi_credentials(t) for t in cmd]
    return " ".join(shlex.quote(t) for t in toks)


def _classify_error(stderr: str, stdout: str) -> type | None:
    blob = (stdout + "\n" + stderr).lower()
    if any(h.lower() in blob for h in _SSL_HINTS):
        return OvfToolSslError
    if any(h.lower() in blob for h in _AUTH_HINTS):
        return OvfToolAuthError
    return None


def _run_capture(cmd: Sequence[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    p = subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        env=_merged_env(env),
        check=False,
    )
    return p.returncode, p.stdout or "", p.stderr or ""


def _merged_env(env: dict[str, str] | None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return merged


def _run_with_retries(
    *,
    cmd: Sequence[str],
    retries: int,
    backoff_s: float,
    env: dict[str, str] | None,
    log_prefix: str,
) -> None:
    attempts = 0
    while True:
        attempts += 1
        try:
            _run_streaming(cmd=cmd, env=env, log_prefix=log_prefix)
            return
        except Exception as e:  # pylint: disable=broad-exception-caught  # ovftool subprocess raises dynamic errors; the retry loop must classify and continue
            if attempts > retries:
                raise
            sleep_s = backoff_s * (2 ** (attempts - 2)) if attempts >= 2 else backoff_s
            _warn_line(f"{log_prefix}: attempt {attempts} failed: {e}")
            _info_line(f"{log_prefix}: retrying in {sleep_s:.1f}s...")
            time.sleep(sleep_s)


def _run_streaming(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # single cohesive no-threads stdout/stderr multiplexing loop
    *,
    cmd: Sequence[str],
    env: dict[str, str] | None,
    log_prefix: str,
) -> None:
    """
    Run ovftool and stream output line-by-line (NO threads).

    Diagnostics:
      - Captures rolling tails from stdout/stderr for error classification + helpful exceptions.
      - Logs progress percentage when lines like "Progress: 12%" appear.
    """
    cmd_list = list(cmd)
    print(f"{log_prefix}: exec: {_fmt_cmd_for_log(cmd_list)}")

    tail_max = 300
    out_tail: list[str] = []
    err_tail: list[str] = []
    last_pct: int | None = None

    def _tail_push(buf: list[str], line: str) -> None:
        buf.append(line)
        if len(buf) > tail_max:
            del buf[0 : len(buf) - tail_max]

    try:
        # pylint: disable-next=consider-using-with  # process spans the rest of this function with custom stdout/stderr multiplexing
        p = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=_merged_env(env),
        )
    except FileNotFoundError as e:
        raise OvfToolNotFound(str(e)) from e

    if p.stdout is None or p.stderr is None:
        raise OvfToolError(
            "ovftool process stdout/stderr is None - subprocess may have failed to start. "
            "Ensure ovftool is installed and in PATH. Download from VMware website or check installation."
        )

    # Multiplex without threads to avoid deadlocks:
    # - Prefer select.select when available (POSIX).
    # - Fallback: alternating non-ideal readline (still single-flow).
    open_streams = {p.stdout: "stdout", p.stderr: "stderr"}

    def _handle_line(which: str, line: str) -> None:
        nonlocal last_pct
        s = line.rstrip("\n")
        if which == "stdout":
            _tail_push(out_tail, s)
        else:
            _tail_push(err_tail, s)

        # Log progress percentage lines
        m = _PROGRESS_RE.match(s)
        if m:
            try:
                pct = max(0, min(100, int(m.group(1))))
                if last_pct is None or pct != last_pct:
                    last_pct = pct
                    print(f"{log_prefix}: Progress: {pct}%")
            except (ValueError, TypeError):
                pass
            return

        print(f"{log_prefix}: {s}")

    try:
        if SELECT_AVAILABLE:
            while open_streams:
                rc = p.poll()

                rlist = list(open_streams.keys())
                ready, _, _ = select.select(rlist, [], [], 0.2)  # type: ignore[arg-type]
                if not ready:
                    if rc is not None:
                        break
                    continue

                for st in ready:
                    line = st.readline()
                    if not line:
                        open_streams.pop(st, None)
                        continue
                    _handle_line(open_streams[st], line)

                if rc is not None and not ready:
                    break
        else:
            while True:
                out_line = p.stdout.readline()
                if out_line:
                    _handle_line("stdout", out_line)

                err_line = p.stderr.readline()
                if err_line:
                    _handle_line("stderr", err_line)

                rc = p.poll()
                if rc is not None:
                    break

        rc = p.wait()

        # Drain any remaining output after process end
        for st, which in [(p.stdout, "stdout"), (p.stderr, "stderr")]:
            while True:
                line = st.readline()
                if not line:
                    break
                _handle_line(which, line)

        if rc != 0:
            stdout_txt = "\n".join(out_tail)
            stderr_txt = "\n".join(err_tail)
            klass = _classify_error(stderr_txt, stdout_txt) or OvfToolError
            raise klass(
                f"ovftool failed rc={rc}\n"
                f"cmd={_fmt_cmd_for_log(cmd_list)}\n"
                f"--- stdout (tail) ---\n{stdout_txt}\n"
                f"--- stderr (tail) ---\n{stderr_txt}\n"
            )

    finally:
        with contextlib.suppress(Exception):
            p.kill()
            p.wait()
