# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/transports/govc_export.py
"""
govc export workflow wrapper.

Single source of truth for:
  - CD/DVD removal before export
  - VM shutdown/power-off policy
  - Progress reporting (TTY / logger)
  - Output directory cleanup
  - OVA packaging (when mode='ova')

Design: callers pass a GovcExportSpec; this module runs the workflow.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from h2kvm.providers.vmware.utils.utils import is_tty as _is_tty

from ....core.exceptions import VMwareError


@dataclass
class GovcExportSpec:  # pylint: disable=too-many-instance-attributes  # models every independent govc-export tuning knob
    """All parameters needed for a govc export operation."""

    vm: str
    outdir: Path
    mode: str  # "ovf" or "ova"

    # govc configuration
    govc_bin: str = "govc"
    env: dict[str, str] | None = None

    # VM preparation
    remove_cdroms: bool = True
    show_vm_info: bool = True
    shutdown: bool = False
    shutdown_timeout_s: float = 300.0
    shutdown_poll_s: float = 5.0
    power_off: bool = False

    # Output handling
    clean_outdir: bool = False
    ova_filename: str | None = None  # only for mode="ova"

    # Progress/UI
    show_progress: bool = True
    prefer_pty: bool = True
    total_disk_bytes: int = 0  # pre-fetched disk capacity for progress %
    vm_hardware_info: dict[str, Any] | None = None  # populated by _fetch_vm_hardware_info


class GovcExportError(VMwareError):
    """Specialized error for govc export failures."""


# UI helpers (plain prints)
def _print_panel(_logger: Any, title: str, body: str = "") -> None:
    line = "─" * max(57, len(title) + 10)
    print(f"╭{line}╮")
    t = title[: max(0, len(line) - 2)]
    print(f"│ {t:<{len(line) - 2}} │")
    if body.strip():
        for bl in body.splitlines():
            print(f"│ {bl:<{len(line) - 2}} │")
    print(f"╰{line}╯")


def _info(logger: Any, msg: str) -> None:
    try:
        logger.info(msg)
    except Exception:  # pylint: disable=broad-exception-caught  # logger may be a stub/mock/broken implementation; must still surface the message
        print(msg)


def _debug(logger: Any, msg: str) -> None:
    with contextlib.suppress(Exception):
        logger.debug(msg)


def _warn(logger: Any, msg: str) -> None:
    try:
        logger.warning(msg)
    except Exception:  # pylint: disable=broad-exception-caught  # logger may be a stub/mock/broken implementation; must still surface the message
        print(f"WARNING: {msg}")


def _ok_line(logger: Any, msg: str) -> None:
    # Prefer printing a clean check line (matches your sample).
    _info(logger, f" ✓ {msg}")


# govc runners
def _run_govc_simple(
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Simple govc runner without PTY."""
    full_env = dict(os.environ)
    full_env.update(env)

    _debug(logger, f"Running govc: {' '.join(cmd)}")

    try:
        return subprocess.run(
            cmd,
            env=full_env,
            capture_output=capture_output,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr_text = (getattr(e, "stderr", None) or "").strip()[:800]
        error_msg = f"govc failed with exit code {e.returncode}"
        if stderr_text:
            error_msg += f": {stderr_text}"
        # Add actionable hints based on common error patterns
        sl = stderr_text.lower()
        if "login" in sl or "unauthorized" in sl or "not authenticated" in sl or "401" in sl:
            error_msg += (
                "\n\nAuthentication failed. Check your vSphere credentials:\n"
                "  - GOVC_URL, GOVC_USERNAME, GOVC_PASSWORD environment variables\n"
                "  - Verify the user has sufficient permissions in vCenter"
            )
        elif "no such host" in sl or "connection refused" in sl or "dial tcp" in sl:
            error_msg += (
                "\n\nConnection failed. Verify vSphere connectivity:\n"
                "  - Check GOVC_URL is correct (e.g., https://vcenter.example.com/sdk)\n"
                "  - Ensure the vCenter/ESXi host is reachable from this machine\n"
                "  - Check firewall rules allow HTTPS (port 443)"
            )
        elif "certificate" in sl or "tls" in sl or "x509" in sl:
            error_msg += (
                "\n\nTLS certificate error. Try one of:\n"
                "  - Set GOVC_INSECURE=1 to skip certificate verification\n"
                "  - Import the vCenter CA certificate into the system trust store"
            )
        raise GovcExportError(error_msg) from e
    except FileNotFoundError as e:
        raise GovcExportError(
            "govc binary not found. Install it from https://github.com/vmware/govmomi/releases "
            "and ensure it is in your PATH."
        ) from e
    except Exception as e:
        raise GovcExportError(
            f"Failed to run govc: {e}\n"
            "Ensure govc is installed and in PATH: https://github.com/vmware/govmomi/releases"
        ) from e


def _monitor_download_progress(  # pylint: disable=too-many-locals,too-many-nested-blocks  # single self-contained progress-formatting loop
    out_dir: str,
    _logger: Any,
    stop_event: threading.Event,
    interval: float = 3.0,
    total_bytes: int = 0,
) -> None:
    """Background thread: emit structured progress by watching file sizes."""
    start_time = time.time()
    last_size = 0
    last_time = start_time
    rate_window: deque[float] = deque(maxlen=5)

    while not stop_event.wait(interval):
        current = 0
        try:
            d = Path(out_dir)
            if d.exists():
                for f in d.rglob("*"):
                    try:
                        if f.is_file():
                            current += f.stat().st_size
                    except OSError:
                        pass
        except OSError:
            continue

        now = time.time()
        elapsed = now - last_time
        if current > 0 and elapsed > 0:
            instant_rate = (current - last_size) / elapsed if current > last_size else 0
            rate_window.append(instant_rate)
            smooth_rate = sum(rate_window) / len(rate_window)

            cur_mb = current / (1024 * 1024)
            rate_mbs = smooth_rate / (1024 * 1024)

            if total_bytes > 0:
                pct = min(current / total_bytes * 100, 100)
                total_mb = total_bytes / (1024 * 1024)
                remaining = total_bytes - current
                eta_s = remaining / smooth_rate if smooth_rate > 0 else 0
                eta_m, eta_sec = divmod(int(eta_s), 60)
                # Structured line parseable by TUI: [PROGRESS] pct|current|total|rate|eta
                print(
                    f"[PROGRESS] {pct:.1f}|{current}|{total_bytes}|{smooth_rate:.0f}|{int(eta_s)}",
                    file=sys.stderr,
                    flush=True,
                )
                # Human-readable line for log panel.
                print(
                    f"📥 {cur_mb:.0f}/{total_mb:.0f} MB ({pct:.0f}%) — {rate_mbs:.1f} MB/s — ETA {eta_m}m{eta_sec:02d}s",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"📥 {cur_mb:.0f} MB — {rate_mbs:.1f} MB/s",
                    file=sys.stderr,
                    flush=True,
                )

            last_size = current
            last_time = now


def _run_govc_with_logging(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
    *,
    title: str,
    monitor_dir: str | None = None,
    total_bytes: int = 0,
) -> subprocess.CompletedProcess:
    """
    Run govc while logging output lines.
    If monitor_dir is set, a background thread logs download progress by file size.
    """
    full_env = dict(os.environ)
    full_env.update(env)

    _info(logger, title)

    # pylint: disable=duplicate-code
    # reason: mirrors the Popen kwargs in nfc_lease.py's _run_govc --
    # both are standard subprocess-streaming setups, not shared logic; keeping
    # independent avoids coupling two unrelated govc invocation paths.
    # pylint: disable-next=consider-using-with  # process spans the function; consumed alongside a progress-monitor thread below
    proc = subprocess.Popen(
        cmd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    output_lines: list[str] = []

    # Start file-size progress monitor if output directory is known.
    stop_monitor = threading.Event()
    monitor_thread = None
    if monitor_dir:
        monitor_thread = threading.Thread(
            target=_monitor_download_progress,
            args=(monitor_dir, logger, stop_monitor),
            kwargs={"total_bytes": total_bytes},
            daemon=True,
        )
        monitor_thread.start()

    try:
        if proc.stdout is None:
            raise GovcExportError(
                "govc export process stdout is None - subprocess may have failed to start. "
                "Ensure govc is installed and in PATH: https://github.com/vmware/govmomi/releases"
            )
        # Read char-by-char to split on \n or \r so govc progress is streamed live.
        buf: list[str] = []
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            if ch in ("\n", "\r"):
                s = "".join(buf).strip()
                buf.clear()
                if s:
                    output_lines.append(s)
                    logger.info("%s", s)
            else:
                buf.append(ch)
        # Flush remaining buffer.
        if buf:
            s = "".join(buf).strip()
            if s:
                output_lines.append(s)
                logger.info("%s", s)

        rc = proc.wait()
        stdout = "\n".join(output_lines).strip()

        if rc != 0:
            tail = "\n".join(output_lines[-40:]).strip()
            msg = f"govc failed with exit code {rc}"
            if tail:
                msg += f":\n{tail}"
            tl = tail.lower()
            if "lease" in tl or "export" in tl:
                msg += (
                    "\n\nExport lease may have expired or been interrupted. "
                    "Ensure the VM is not being modified during export and retry."
                )
            elif "no such" in tl or "not found" in tl:
                msg += (
                    "\n\nVM or resource not found. Verify the VM name is correct "
                    "(names are case-sensitive) and the VM exists in the configured datacenter."
                )
            raise GovcExportError(msg)

        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")

    except GovcExportError:
        raise
    except Exception as e:
        with contextlib.suppress(Exception):
            proc.kill()
        tail = "\n".join(output_lines[-40:]).strip()
        msg = f"Failed to run govc: {e}"
        if tail:
            msg += f"\nLast output:\n{tail}"
        raise GovcExportError(msg) from e
    finally:
        stop_monitor.set()
        if monitor_thread:
            monitor_thread.join(timeout=2)


def _run_govc_with_tty_passthrough(
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
) -> None:
    """
    Let govc draw its own progress (best when attached to a real TTY).
    """
    full_env = dict(os.environ)
    full_env.update(env)

    _debug(logger, f"Running govc (TTY passthrough): {' '.join(cmd)}")

    try:
        subprocess.run(cmd, env=full_env, check=True)
    except subprocess.CalledProcessError as e:
        raise GovcExportError(
            f"govc failed with exit code {e.returncode}. "
            "Check vSphere connectivity and credentials (GOVC_URL, GOVC_USERNAME, GOVC_PASSWORD)."
        ) from e
    except FileNotFoundError as e:
        raise GovcExportError(
            "govc binary not found. Install it from https://github.com/vmware/govmomi/releases "
            "and ensure it is in your PATH."
        ) from e
    except Exception as e:
        raise GovcExportError(
            f"Failed to run govc: {e}\n"
            "Ensure govc is installed and in PATH: https://github.com/vmware/govmomi/releases"
        ) from e


def _run_govc_export(  # pylint: disable=too-many-arguments
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
    *,
    show_progress: bool,
    prefer_pty: bool,
    title: str,
    monitor_dir: str | None = None,
    total_bytes: int = 0,
) -> None:
    """
    Policy:
      - If not showing progress: capture output (best error context)
      - If showing progress and in TTY with prefer_pty: passthrough
      - Otherwise: stream via logging + optional file-size monitor
    """
    if not show_progress:
        _run_govc_simple(cmd, env, logger, capture_output=True)
        return

    if _is_tty() and prefer_pty:
        _run_govc_with_tty_passthrough(cmd, env, logger)
        return

    # Stream output via logging so TUI and non-TTY callers see progress.
    _run_govc_with_logging(cmd, env, logger, title=title, monitor_dir=monitor_dir, total_bytes=total_bytes)


# VM prep helpers
def _remove_cdrom_devices(spec: GovcExportSpec, logger: Any) -> list[str]:
    """Remove CD/DVD devices from VM before export. Returns removed device names."""
    removed: list[str] = []
    if not spec.remove_cdroms:
        return removed

    _info(logger, "Removing CD/DVD devices...")

    try:
        result = _run_govc_simple(
            [spec.govc_bin, "device.ls", "-vm", spec.vm],
            spec.env or {},
            logger,
        )

        cdroms: list[str] = []
        for line in (result.stdout or "").splitlines():
            s = line.strip()
            if s and "cdrom" in s.lower():
                parts = s.split()
                if parts:
                    cdroms.append(parts[0])

        if not cdroms:
            _debug(logger, "No CD/DVD devices found")
            return removed

        for dev in cdroms:
            try:
                _run_govc_simple(
                    [spec.govc_bin, "device.remove", "-vm", spec.vm, dev],
                    spec.env or {},
                    logger,
                    capture_output=False,
                )
                removed.append(dev)
                _ok_line(logger, f"Removed: {dev}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # govc raises dynamic errors; try the eject fallback before giving up on this device
                _warn(logger, f"Failed to remove device {dev}: {e} (trying eject)")
                with contextlib.suppress(Exception):
                    _run_govc_simple(
                        [spec.govc_bin, "device.cdrom.eject", "-vm", spec.vm],
                        spec.env or {},
                        logger,
                        capture_output=False,
                    )

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort CD/DVD removal must not abort the export
        _warn(logger, f"CD/DVD removal failed (continuing): {e}")

    return removed


def _get_vm_info_lines(spec: GovcExportSpec, logger: Any) -> list[str]:
    """
    Extract a few useful vm.info lines and return them for printing in a panel.
    """
    try:
        result = _run_govc_simple(
            [spec.govc_bin, "vm.info", spec.vm],
            spec.env or {},
            logger,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort informational panel; govc failure here must not abort the export
        _debug(logger, f"Could not get VM info: {e}")
        return []

    want = ("name:", "power state:", "storage:", "path:", "guest os:", "memory:", "cpu:")
    out: list[str] = []
    for line in (result.stdout or "").splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if any(k in low for k in want):
            out.append(s)
    return out


def _show_vm_info(spec: GovcExportSpec, logger: Any) -> None:
    if not spec.show_vm_info:
        return

    title = f"VM Information: {spec.vm}"
    lines = _get_vm_info_lines(spec, logger)

    if not lines:
        _print_panel(logger, title, "(No detailed info available)")
        return

    body = "\n".join([f" {ln}" for ln in lines])
    _print_panel(logger, title, body)


def _prepare_vm_power_state(spec: GovcExportSpec, logger: Any) -> None:
    """Handle VM power state (shutdown/power off) before export."""
    if spec.shutdown:
        _info(logger, "Shutting down VM (graceful)...")
        try:
            _run_govc_simple(
                [spec.govc_bin, "vm.power", "-s", spec.vm],
                spec.env or {},
                logger,
                capture_output=False,
            )

            start_time = time.time()
            while time.time() - start_time < spec.shutdown_timeout_s:
                try:
                    result = _run_govc_simple(
                        [spec.govc_bin, "vm.info", spec.vm],
                        spec.env or {},
                        logger,
                    )
                    if "poweredOff" in (result.stdout or ""):
                        _ok_line(logger, "VM is now powered off")
                        return
                except Exception:  # pylint: disable=broad-exception-caught  # govc raises dynamic errors; keep polling until the timeout elapses
                    pass
                time.sleep(spec.shutdown_poll_s)

            _warn(logger, "VM shutdown timeout exceeded")
        except Exception as e:  # pylint: disable=broad-exception-caught  # govc raises dynamic errors; a failed shutdown attempt must not abort the export
            _warn(logger, f"Shutdown failed: {e}")

    elif spec.power_off:
        _info(logger, "Powering off VM...")
        try:
            _run_govc_simple(
                [spec.govc_bin, "vm.power", "-off", spec.vm],
                spec.env or {},
                logger,
                capture_output=False,
            )
            _ok_line(logger, "VM powered off")
        except Exception as e:  # pylint: disable=broad-exception-caught  # govc raises dynamic errors; a failed power-off must not abort the export
            _warn(logger, f"Power off failed: {e}")


# Output helpers
def _clean_output_directory(outdir: Path, logger: Any) -> None:
    if outdir.exists():
        _info(logger, f"Cleaning output directory: {outdir}")
        try:
            for item in outdir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            _debug(logger, "Output directory cleaned")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cleanup must not abort the export
            _warn(logger, f"Failed to clean output directory: {e}")


def _create_ova_from_ovf(ovf_dir: Path, ova_file: Path, logger: Any) -> None:
    """
    Create OVA file from OVF directory.

    Note: OVA is a TAR archive containing the OVF descriptor + disks + manifest.
    """
    _info(logger, "Creating OVA archive from OVF files...")

    files = [p for p in ovf_dir.rglob("*") if p.is_file()]
    if not files:
        raise GovcExportError(f"No files found under OVF directory: {ovf_dir}")

    try:
        with tarfile.open(ova_file, "w") as tar:
            for i, fp in enumerate(files, 1):
                arcname = fp.relative_to(ovf_dir.parent)
                tar.add(fp, arcname=arcname)
                logger.info("Packaging OVA file %d/%d: %s", i, len(files), fp.name)

        if not ova_file.exists():
            raise GovcExportError("OVA file was not created after tar creation")

        size_bytes = ova_file.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        size_gb = size_bytes / (1024 * 1024 * 1024)
        if size_gb >= 1:
            _ok_line(logger, f"OVA created: {ova_file} ({size_gb:.2f} GB)")
        else:
            _ok_line(logger, f"OVA created: {ova_file} ({size_mb:.2f} MB)")

    except Exception as e:
        raise GovcExportError(f"Failed to create OVA: {e}") from e


def _find_exported_ovf_dir(parent: Path, vm_name: str) -> Path | None:
    """
    govc export.ovf typically creates a subdir named after the VM.
    We try best-effort discovery.
    """
    if not parent.exists():
        return None
    # Prefer directory containing vm_name
    for item in parent.iterdir():
        if item.is_dir() and vm_name in item.name:
            return item
    # Otherwise first directory
    for item in parent.iterdir():
        if item.is_dir():
            return item
    return None


def _fmt_elapsed(start_time: float) -> tuple[int, int]:
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return minutes, seconds


def _check_independent_disks(spec: GovcExportSpec, logger: Any) -> None:
    """Warn about disks with 'independent' mode that may fail with VDDK >= 7.0."""
    try:
        full_env = dict(os.environ)
        if spec.env:
            full_env.update(spec.env)
        result = subprocess.run(
            [spec.govc_bin, "device.info", "-vm", spec.vm, "-json", "disk-*"],
            env=full_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return
        data = json.loads(result.stdout)
        independent = []
        for dev in data.get("devices", []):
            backing = dev.get("backing", {})
            disk_mode = backing.get("diskMode", "")
            if "independent" in disk_mode.lower():
                label = dev.get("deviceInfo", {}).get("label", "unknown")
                fn = backing.get("fileName", "unknown")
                independent.append(f"{label} ({disk_mode}): {fn}")
        if independent:
            _warn(logger, f"WARNING: {len(independent)} disk(s) have 'independent' mode:")
            for d in independent:
                _warn(logger, f"  - {d}")
            _warn(
                logger,
                "Independent disks may fail with VDDK >= 7.0. "
                "Consider changing disk mode to 'dependent' in vSphere before migration.",
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort advisory check; govc/JSON errors must not abort the export
        _debug(logger, f"Independent disk check skipped: {exc}")


def _fetch_vm_hardware_info(  # pylint: disable=too-many-locals  # extracts several independent hardware fields from one govc JSON blob
    spec: GovcExportSpec, logger: Any
) -> dict:
    """Get VM hardware info (memory, CPU, disk size) via govc vm.info -json."""
    hw: dict = {}
    try:
        full_env = dict(os.environ)
        if spec.env:
            full_env.update(spec.env)
        result = subprocess.run(
            [spec.govc_bin, "vm.info", "-json", spec.vm],
            env=full_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return hw
        data = json.loads(result.stdout)
        total = 0
        for vm in data.get("virtualMachines", []):
            config = vm.get("config", {})
            hardware = config.get("hardware", {})

            # Memory (in MB)
            mem_mb = hardware.get("memoryMB") or config.get("memorySizeMB")
            if mem_mb:
                hw["memory_mib"] = int(mem_mb)

            # vCPUs
            num_cpu = hardware.get("numCPU") or config.get("numCpu")
            if num_cpu:
                hw["vcpus"] = int(num_cpu)

            # NIC count
            nic_count = 0
            for dev in hardware.get("device", []):
                cap = dev.get("capacityInBytes") or (dev.get("capacityInKB", 0) * 1024)
                if cap and cap > 0:
                    total += cap
                # Count NICs (backing has network reference)
                if dev.get("backing") and dev.get("macAddress"):
                    nic_count += 1
            if nic_count > 1:
                hw["nic_count"] = nic_count

        hw["total_disk_bytes"] = total
        if total > 0:
            _info(logger, f"Total disk size: {total / (1024**3):.1f} GB")
        if hw.get("memory_mib"):
            _info(logger, f"VM memory: {hw['memory_mib']} MiB, vCPUs: {hw.get('vcpus', '?')}")
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort hardware-info fetch; govc/JSON errors must not abort the export
        pass
    return hw


def _fetch_vm_disk_size(spec: GovcExportSpec, logger: Any) -> int:
    """Get total disk capacity in bytes via govc vm.info -json."""
    hw = _fetch_vm_hardware_info(spec, logger)
    return hw.get("total_disk_bytes", 0)


# Public entrypoint
# pylint: disable-next=too-many-branches,too-many-statements  # top-level orchestration of the full multi-step export workflow
def export_vm_govc(logger: Any, spec: GovcExportSpec) -> None:
    """
    Main export workflow.

    Steps:
    1. Banner
    2. Show VM info (optional)
    3. Remove CD/DVD devices (optional)
    4. Handle VM power state (optional)
    5. Clean output directory (optional)
    6. Run govc export.ovf
    7. Package OVA if mode='ova'
    8. Success panel
    """
    if spec.mode not in ("ovf", "ova"):
        raise GovcExportError(f"Invalid export mode: {spec.mode}. Must be 'ovf' or 'ova'")

    if spec.mode == "ova" and not spec.ova_filename:
        spec.ova_filename = f"{spec.vm}.ova"

    spec.outdir.mkdir(parents=True, exist_ok=True)
    if spec.clean_outdir:
        _clean_output_directory(spec.outdir, logger)

    # Banner (matches your sample vibe)
    banner_body = f"Mode: {spec.mode.upper()} | Output: {spec.outdir}"
    _print_panel(logger, f"Exporting VM: {spec.vm}", banner_body)

    # VM info panel
    _show_vm_info(spec, logger)

    # Pre-flight: warn about independent disks
    _check_independent_disks(spec, logger)

    # Remove CD/DVD devices
    _remove_cdrom_devices(spec, logger)

    # Handle power state
    _prepare_vm_power_state(spec, logger)

    # Fetch total disk size and hardware info for progress tracking and domain XML.
    hw = _fetch_vm_hardware_info(spec, logger)
    if spec.total_disk_bytes <= 0:
        spec.total_disk_bytes = hw.get("total_disk_bytes", 0)
    # Store hardware info for the orchestrator to propagate to domain emitter
    spec.vm_hardware_info = hw

    # Start export
    _info(logger, f"\nStarting {spec.mode.upper()} export...")
    _info(logger, "This may take several minutes depending on disk size...\n")

    start_time = time.time()

    if spec.mode == "ovf":
        export_cmd = [spec.govc_bin, "export.ovf", "-vm", spec.vm, str(spec.outdir)]
        try:
            _run_govc_export(
                export_cmd,
                spec.env or {},
                logger,
                show_progress=spec.show_progress,
                prefer_pty=spec.prefer_pty,
                title="Exporting OVF...",
                monitor_dir=str(spec.outdir),
                total_bytes=spec.total_disk_bytes,
            )
        except Exception as e:
            m, s = _fmt_elapsed(start_time)
            raise GovcExportError(f"OVF export failed after {m}m {s}s: {e}") from e

        ovf_dir = _find_exported_ovf_dir(spec.outdir, spec.vm)
        m, s = _fmt_elapsed(start_time)
        if ovf_dir:
            _ok_line(logger, f"OVF export completed in {m}m {s}s")
            _info(logger, f"Output: {ovf_dir}")
        else:
            _warn(logger, "Could not find OVF directory after export")
            try:
                _info(logger, "Contents of output directory:")
                for item in spec.outdir.iterdir():
                    _info(logger, f" {item.name}")
            except OSError:
                pass

        _print_panel(logger, "✓ Export completed successfully!", "")

    else:
        # OVA mode: export OVF to temp, then tar it as OVA into spec.outdir
        with tempfile.TemporaryDirectory(prefix=f"govc_export_{spec.vm}_") as tmpdir:
            tmp_path = Path(tmpdir)

            try:
                export_cmd = [spec.govc_bin, "export.ovf", "-vm", spec.vm, str(tmp_path)]
                _run_govc_export(
                    export_cmd,
                    spec.env or {},
                    logger,
                    show_progress=spec.show_progress,
                    prefer_pty=spec.prefer_pty,
                    title="Exporting OVF for OVA...",
                    monitor_dir=str(tmp_path),
                    total_bytes=spec.total_disk_bytes,
                )

                ovf_dir = _find_exported_ovf_dir(tmp_path, spec.vm)
                if not ovf_dir:
                    raise GovcExportError(f"Could not find OVF directory in temp location: {tmp_path}")

                ova_file = spec.outdir / (spec.ova_filename or f"{spec.vm}.ova")

                _info(logger, "▌ Creating OVA archive...")
                _create_ova_from_ovf(ovf_dir, ova_file, logger)

                m, s = _fmt_elapsed(start_time)
                _ok_line(logger, f"OVA export completed in {m}m {s}s")
                _info(logger, f"Output: {ova_file}\n")

                _print_panel(logger, "✓ Export completed successfully!", "")

            except Exception as e:
                m, s = _fmt_elapsed(start_time)
                raise GovcExportError(f"OVA export failed after {m}m {s}s: {e}") from e
