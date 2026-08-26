# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/clients/nfc_lease.py
"""
NFC export/download via govc CLI (govmomi).

Key fact:
- `govc export.ovf` / `govc export.ova` use VMware's HttpNfcLease mechanism under the hood
  (aka "NFC export"): lease acquisition + keepalive + signed URL fetch + downloads.

Why this exists:
- You already have a *custom* NFC data-plane downloader (requests + Range + retries).
- Sometimes you want the "just export it" path: let govc manage HttpNfcLease + keepalive
  + URL signing + downloads, and you simply orchestrate it reliably.

Important differences vs nfc_lease_client.py:
- govc is NOT a pure data-plane client. It performs control-plane + data-plane together
  for export.ovf / export.ova.
- There is no lease heartbeat callback here: govc keeps the lease alive internally.
- Resume semantics are best-effort: govc does not guarantee HTTP Range resume.
  We implement "idempotent skip" (when enabled) + retries around the govc command,
  and best-effort publish of the result.

Notes on "atomic publish":
- For OVA (single file), publish is truly atomic via os.replace().
- For OVF (directory tree), publish is best-effort: we merge/overwrite files into the
  final directory. This is safe and idempotent for typical tool usage, but readers could
  observe partial updates if they inspect the directory mid-copy.

Docs/refs:
- govc is shipped from vmware/govmomi and provides export.ovf / export.ova commands.
"""

from __future__ import annotations

import os
import random
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging


class NFCLeaseError(RuntimeError):
    """Generic NFC (govc) export/download error."""


class NFCLeaseCancelled(NFCLeaseError):
    """Raised when a caller cancels an in-progress export."""


ProgressFn = Callable[[int, int, float], None]
CancelFn = Callable[[], bool]
LeaseHeartbeatFn = Callable[[int, int], None]  # accepted but not used (govc handles keepalive)


@dataclass(frozen=True)
class GovcSessionSpec:  # pylint: disable=too-many-instance-attributes  # dataclass models govc's full GOVC_* env surface
    """
    govc auth/session config.

    You can supply either explicit fields below, or rely on existing GOVC_* env
    already exported in the process environment.
    """

    url: str | None = None
    username: str | None = None
    password: str | None = None

    # govc -k / GOVC_INSECURE
    insecure: bool | None = None

    # Optional extras
    ca_certs: str | None = None  # GOVC_TLS_CA_CERTS
    thumbprint: str | None = None  # GOVC_THUMBPRINT
    token: str | None = None  # GOVC_TOKEN (if you use it)
    debug: bool | None = None  # GOVC_DEBUG (very noisy)
    persist_session: bool | None = None  # GOVC_PERSIST_SESSION

    # Optional inventory context
    datacenter: str | None = None  # GOVC_DATACENTER
    datastore: str | None = None  # GOVC_DATASTORE
    folder: str | None = None  # GOVC_FOLDER
    resource_pool: str | None = None  # GOVC_RESOURCE_POOL
    host: str | None = None  # GOVC_HOST
    cluster: str | None = None  # GOVC_CLUSTER


@dataclass(frozen=True)
class GovcExportSpec:  # pylint: disable=too-many-instance-attributes  # dataclass models govc export's full flag surface
    """
    What to export.

    vm: inventory path or name that govc can resolve (often "vm/MyVM" or "MyVM").
    out_dir: final output directory where exported files should land.
    """

    vm: str
    out_dir: Path

    # export options
    export_ova: bool = False  # if True, uses `govc export.ova`; else `govc export.ovf`
    name: str | None = None  # optional target base name under out_dir (see OVA note below)

    # Pass-through flags (used only if set)
    dc: str | None = None
    ds: str | None = None
    folder: str | None = None
    pool: str | None = None
    host: str | None = None
    cluster: str | None = None

    # govc binary path (default: resolve from PATH)
    govc_bin: str = "govc"

    # Preflight checks (recommended)
    preflight: bool = True
    preflight_vm_info: bool = True  # if True, verify VM is resolvable before export


# Helpers


def _env_apply(session: GovcSessionSpec, base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)

    def set_if(k: str, v: str | None) -> None:
        if v is not None:
            env[k] = v

    def set_bool(k: str, v: bool | None) -> None:
        if v is not None:
            env[k] = "1" if v else "0"

    set_if("GOVC_URL", session.url)
    set_if("GOVC_USERNAME", session.username)
    set_if("GOVC_PASSWORD", session.password)

    set_bool("GOVC_INSECURE", session.insecure)
    set_if("GOVC_TLS_CA_CERTS", session.ca_certs)
    set_if("GOVC_THUMBPRINT", session.thumbprint)
    set_if("GOVC_TOKEN", session.token)
    set_bool("GOVC_DEBUG", session.debug)
    set_bool("GOVC_PERSIST_SESSION", session.persist_session)

    set_if("GOVC_DATACENTER", session.datacenter)
    set_if("GOVC_DATASTORE", session.datastore)
    set_if("GOVC_FOLDER", session.folder)
    set_if("GOVC_RESOURCE_POOL", session.resource_pool)
    set_if("GOVC_HOST", session.host)
    set_if("GOVC_CLUSTER", session.cluster)

    return env


def _mkdirp(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _best_effort_publish_dir(tmp_dir: Path, final_dir: Path) -> None:
    """
    Best-effort publish of an exported directory tree:
    - ensure final exists
    - merge/overwrite files from tmp into final
    - then remove tmp

    This is safe and idempotent, but not strictly atomic for directory readers.
    """
    _mkdirp(final_dir)
    for root, _dirs, files in os.walk(tmp_dir):
        rel = Path(root).relative_to(tmp_dir)
        dst_root = final_dir / rel
        _mkdirp(dst_root)
        for fn in files:
            src = Path(root) / fn
            dst = dst_root / fn
            os.replace(str(src), str(dst))
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _parse_govc_progress(line: str) -> tuple[int, int, float] | None:
    """
    Best-effort parsing of govc progress output.
    govc output formats vary by command/version; we keep it permissive.

    Recognizes:
      - "xx%" patterns (no bytes)
      - "<done>/<total>" integers when present (rare; depends on govc output)

    Returns (done, total, pct).
    """
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
    if m:
        pct = float(m.group(1))
        return (-1, -1, pct)

    m2 = re.search(r"\b(\d+)\s*/\s*(\d+)\b", line)
    if m2:
        done = int(m2.group(1))
        total = int(m2.group(2))
        pct = (done * 100.0 / total) if total > 0 else 0.0
        return (done, total, pct)

    return None


def _should_append_ova_ext(name: str) -> bool:
    n = name.strip().lower()
    return not n.endswith((".ova", ".ovf"))


# Public API


class GovcNfcExporter:  # pylint: disable=too-few-public-methods  # export() is the only intended entry point
    """
    govc-backed exporter.

    Guarantees we provide:
    - retries/backoff around the govc invocation
    - publish into final out_dir
      * OVA: atomic os.replace()
      * OVF: best-effort merge/overwrite publish
    - optional "skip if already exported" heuristic

    Reminder:
    - This path uses HttpNfcLease implicitly via govc export.ovf/export.ova.
    """

    def __init__(self, logger: logging.Logger, session: GovcSessionSpec):
        self.logger = logger
        self.session = session

    # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    # Retry/publish orchestration around a single govc export invocation needs the full knob set.
    def export(
        self,
        spec: GovcExportSpec,
        *,
        resume: bool = True,
        progress: ProgressFn | None = None,
        progress_interval_s: float = 0.5,
        cancel: CancelFn | None = None,
        heartbeat: LeaseHeartbeatFn | None = None,  # accepted for signature compatibility; ignored
        max_retries: int = 5,
        base_backoff_s: float = 1.0,
        max_backoff_s: float = 20.0,
        jitter_s: float = 0.5,
        skip_if_present: bool = True,
        stage_gc_max_age_s: float = 7 * 24 * 3600,  # 7 days
    ) -> Path:
        """
        Export ``spec.vm`` via govc (HttpNfcLease under the hood) into ``spec.out_dir``.

        Stages the export into a per-attempt temp directory, retries transient
        govc failures with jittered exponential backoff, then publishes the
        result into the final path (atomically for OVA, best-effort merge for
        OVF). Returns the final published path.
        """
        _ = heartbeat  # explicitly ignored (govc handles lease keepalive internally)

        out_dir = Path(spec.out_dir).expanduser().resolve()
        _mkdirp(out_dir)

        target_name = spec.name or self._default_name_from_vm(spec.vm)

        # OVA naming: unless caller explicitly uses .ova, we append it for sanity.
        if spec.export_ova and _should_append_ova_ext(target_name):
            target_name = f"{target_name}.ova"

        final_path = out_dir / target_name

        # Stage root (per-export target)
        stage_parent = out_dir / f".{target_name}.govc.stage"
        _mkdirp(stage_parent)
        self._gc_stage_dirs(stage_parent, max_age_s=float(stage_gc_max_age_s))

        env = _env_apply(self.session)

        # Optional preflight: fail fast if auth/env is broken or VM isn't resolvable
        if spec.preflight:
            self._preflight(env=env, govc_bin=spec.govc_bin, vm=spec.vm, do_vm_info=spec.preflight_vm_info)

        # Resume knob: disable skip fast-path when resume is False
        effective_skip = bool(skip_if_present) and bool(resume)

        # Fast path: already exported
        if effective_skip and final_path.exists():
            if spec.export_ova:
                if final_path.is_file() and final_path.stat().st_size > 0:
                    self.logger.info("✅ govc: output already present, skipping: %s", final_path)
                    return final_path
            else:
                ovf_files = list(final_path.glob("*.ovf"))
                if final_path.is_dir() and ovf_files:
                    self.logger.info("✅ govc: output already present, skipping: %s", final_path)
                    return final_path

        # Build base command (NFC export path)
        cmd: list[str] = [spec.govc_bin]
        if spec.export_ova:
            cmd += ["export.ova", "-vm", spec.vm]
        else:
            cmd += ["export.ovf", "-vm", spec.vm]

        # Optional flags (only if set)
        if spec.dc:
            cmd += ["-dc", spec.dc]
        if spec.ds:
            cmd += ["-ds", spec.ds]
        if spec.folder:
            cmd += ["-folder", spec.folder]
        if spec.pool:
            cmd += ["-pool", spec.pool]
        if spec.host:
            cmd += ["-host", spec.host]
        if spec.cluster:
            cmd += ["-cluster", spec.cluster]

        attempt = 0
        last_cb = 0.0  # last progress callback timestamp (for throttling)

        while True:
            if cancel and cancel():
                raise NFCLeaseCancelled("Export cancelled")

            attempt += 1
            stage_dir = Path(tempfile.mkdtemp(prefix=f"{target_name}.", dir=str(stage_parent)))

            if spec.export_ova:
                stage_out = stage_dir / Path(target_name).name
                cmd_run = [*cmd, str(stage_out)]
            else:
                stage_out = stage_dir / Path(target_name).stem
                cmd_run = [*cmd, str(stage_out)]

            self.logger.info(
                "📦 govc (HttpNfcLease): export start (attempt %d/%d): %s",
                attempt,
                int(max_retries),
                " ".join(shlex.quote(x) for x in cmd_run),
            )

            last_cb_holder = [last_cb]

            try:
                self._run_govc(
                    cmd_run,
                    env=env,
                    cancel=cancel,
                    progress=progress,
                    progress_interval_s=progress_interval_s,
                    last_cb_holder=last_cb_holder,
                )
                last_cb = float(last_cb_holder[0])

                if spec.export_ova:
                    if not stage_out.exists() or stage_out.stat().st_size <= 0:
                        raise NFCLeaseError(f"govc export produced empty OVA: {stage_out}")
                    os.replace(str(stage_out), str(final_path))
                    shutil.rmtree(stage_dir, ignore_errors=True)
                else:
                    if not stage_out.exists() or not stage_out.is_dir():
                        raise NFCLeaseError(f"govc export did not create output dir: {stage_out}")
                    ovfs = list(stage_out.glob("*.ovf"))
                    if not ovfs:
                        raise NFCLeaseError(f"govc export output missing .ovf: {stage_out}")

                    if final_path.exists() and final_path.is_file():
                        raise NFCLeaseError(f"Final path exists as file, expected dir: {final_path}")

                    _mkdirp(final_path)
                    _best_effort_publish_dir(stage_out, final_path)
                    shutil.rmtree(stage_dir, ignore_errors=True)

                self.logger.info("✅ govc: export done: %s", final_path)
                return final_path

            except NFCLeaseCancelled:
                self.logger.warning("🛑 govc: export cancelled (kept stage dir): %s", stage_dir)
                raise
            except Exception as e:  # pylint: disable=broad-exception-caught  # govc/subprocess errors are all transient-retryable here
                shutil.rmtree(stage_dir, ignore_errors=True)

                if attempt >= int(max_retries):
                    raise NFCLeaseError(f"govc export failed after {attempt} attempts: {e}") from e

                backoff = min(float(max_backoff_s), float(base_backoff_s) * (2 ** (attempt - 1)))
                backoff += random.uniform(0.0, max(0.0, float(jitter_s)))

                self.logger.warning(
                    "🔁 govc: transient export error: %s (retry %d/%d in %.2fs)",
                    e,
                    attempt,
                    int(max_retries),
                    backoff,
                )
                time.sleep(backoff)
    # pylint: enable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements

    def _default_name_from_vm(self, vm: str) -> str:
        return vm.replace("/", "_").replace("\\", "_").strip() or "vm"

    def _gc_stage_dirs(self, stage_parent: Path, *, max_age_s: float) -> None:
        try:
            now = time.time()
            for p in stage_parent.iterdir():
                try:
                    st = p.stat()
                    age = now - float(st.st_mtime)
                    if age > float(max_age_s):
                        if p.is_dir():
                            shutil.rmtree(p, ignore_errors=True)
                        else:
                            p.unlink(missing_ok=True)  # type: ignore[arg-type]
                except Exception:  # pylint: disable=broad-exception-caught  # one stale entry must not abort the sweep
                    continue
        except Exception:  # pylint: disable=broad-exception-caught  # stage GC is best-effort, must not abort export
            pass

    def _preflight(self, *, env: dict[str, str], govc_bin: str, vm: str, do_vm_info: bool) -> None:
        """
        Fail fast if govc can't talk to vCenter or VM isn't resolvable.
        This avoids spending minutes exporting before discovering auth/env issues.
        """
        try:
            # Cheap connectivity/auth check
            self._run_quick([govc_bin, "about"], env=env)
        except Exception as e:  # pylint: disable=broad-exception-caught  # translate any failure into a domain-specific error
            raise NFCLeaseError(f"govc preflight failed (about): {e}") from e

        if do_vm_info:
            try:
                self._run_quick([govc_bin, "vm.info", "-vm", vm], env=env)
            except Exception as e:  # pylint: disable=broad-exception-caught  # translate any failure into a domain-specific error
                raise NFCLeaseError(f"govc preflight failed (vm.info -vm {vm!r}): {e}") from e

    def _run_quick(self, cmd: list[str], *, env: dict[str, str]) -> None:
        p = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if p.returncode != 0:
            out = (p.stdout or "").strip()
            msg = out[-2000:] if out else f"rc={p.returncode}"
            raise NFCLeaseError(f"command failed: {' '.join(shlex.quote(x) for x in cmd)} :: {msg}")

    def _terminate_process_group(
        self,
        logger: logging.Logger,
        p: subprocess.Popen,
        *,
        term_grace_s: float = 2.0,
        kill_grace_s: float = 2.0,
    ) -> None:
        try:
            pgid = os.getpgid(p.pid)
        except Exception:  # pylint: disable=broad-exception-caught  # process may already be gone; fall back to direct signal
            pgid = None

        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGTERM)
            else:
                p.terminate()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort terminate; wait/kill below still runs
            pass

        try:
            p.wait(timeout=float(term_grace_s))
            return
        except Exception:  # pylint: disable=broad-exception-caught  # didn't exit in time; escalate to SIGKILL below
            pass

        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGKILL)
            else:
                p.kill()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort kill; final wait below still runs
            pass

        try:
            p.wait(timeout=float(kill_grace_s))
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort final wait, only logged
            logger.debug("govc: process did not exit promptly after SIGKILL (pid=%s)", p.pid)

    def _run_govc(  # pylint: disable=too-many-arguments,too-many-locals  # streams+parses govc's live output while tracking progress/cancel state
        self,
        cmd: list[str],
        *,
        env: dict[str, str],
        cancel: CancelFn | None,
        progress: ProgressFn | None,
        progress_interval_s: float,
        last_cb_holder: list[float],
    ) -> None:
        # pylint: disable=duplicate-code
        # reason: mirrors the Popen kwargs in govc_export.py's _run_govc_with_logging --
        # both are standard subprocess-streaming setups, not shared logic; keeping
        # independent avoids coupling two unrelated govc invocation paths.
        with subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            start_new_session=True,
        ) as p:
            if p.stdout is None:
                raise RuntimeError(
                    "Failed to capture VMware export output stream. "
                    "Check system resources (open file limits, available memory)."
                )
            for raw in p.stdout:
                if cancel and cancel():
                    self._terminate_process_group(self.logger, p)
                    raise NFCLeaseCancelled("Export cancelled")

                line = raw.rstrip("\n")
                if line:
                    parsed = _parse_govc_progress(line)
                    if parsed is not None:
                        done, total, pct = parsed
                        now = time.time()
                        if (now - float(last_cb_holder[0])) >= max(0.05, float(progress_interval_s)):
                            last_cb_holder[0] = now
                            if progress is not None:
                                progress(done, total, pct)
                        # Log progress at INFO so TUI can display it.
                        self.logger.info("govc: %s", line)
                    else:
                        self.logger.debug("govc: %s", line)

            rc = p.wait()
            if rc != 0:
                raise NFCLeaseError(f"govc exited with rc={rc}")


def export_with_govc(  # pylint: disable=too-many-arguments  # convenience wrapper over GovcExportSpec + export()'s full knob set
    logger: logging.Logger,
    session: GovcSessionSpec,
    vm: str,
    out_dir: Path,
    *,
    export_ova: bool = False,
    name: str | None = None,
    preflight: bool = True,
    preflight_vm_info: bool = True,
    # Compat knobs
    resume: bool = True,
    progress: ProgressFn | None = None,
    progress_interval_s: float = 0.5,
    cancel: CancelFn | None = None,
    heartbeat: LeaseHeartbeatFn | None = None,  # ignored
    max_retries: int = 5,
) -> Path:
    """Convenience wrapper: build a GovcExportSpec and export the VM in one call."""
    spec = GovcExportSpec(
        vm=vm,
        out_dir=out_dir,
        export_ova=export_ova,
        name=name,
        preflight=preflight,
        preflight_vm_info=preflight_vm_info,
    )
    return GovcNfcExporter(logger, session).export(
        spec,
        resume=resume,
        progress=progress,
        progress_interval_s=progress_interval_s,
        cancel=cancel,
        heartbeat=heartbeat,
        max_retries=max_retries,
    )
