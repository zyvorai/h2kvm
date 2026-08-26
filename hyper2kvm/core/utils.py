# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/utils.py
"""Core utility functions used across hyper2kvm."""

from __future__ import annotations

import contextlib
import datetime as _dt
import fnmatch
import gc
import hashlib
import itertools
import json
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from shutil import which as _which
from typing import TYPE_CHECKING, Any

from .constants import SIZE_1_MIB
from .exceptions import Fatal

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

    import guestfs  # type: ignore


def effective_cpu_count() -> int:
    """Return the effective CPU count respecting cgroup limits and CPU affinity.

    Check order: cgroup v2 cpu.max → cgroup v1 cfs_quota → sched_getaffinity → os.cpu_count.
    """
    # 1. cgroup v2: /sys/fs/cgroup/cpu.max  →  "quota period" or "max period"
    try:
        with open("/sys/fs/cgroup/cpu.max", encoding="utf-8") as f:
            parts = f.read().strip().split()
            if len(parts) == 2 and parts[0] != "max":
                quota, period = int(parts[0]), int(parts[1])
                if period > 0:
                    cpus = quota // period
                    if cpus >= 1:
                        return cpus
    except (OSError, ValueError):
        pass

    # 2. cgroup v1: cpu.cfs_quota_us / cpu.cfs_period_us
    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", encoding="utf-8") as f:
            quota = int(f.read().strip())
        if quota != -1:
            with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", encoding="utf-8") as f:
                period = int(f.read().strip())
            if period > 0:
                cpus = quota // period
                if cpus >= 1:
                    return cpus
    except (OSError, ValueError):
        pass

    # 3. sched_getaffinity (respects taskset / cpuset)
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        pass

    # 4. Fallback
    return os.cpu_count() or 1


class U:
    """Grab-bag of static utility helpers (process running, sizing, paths) used across hyper2kvm."""

    @staticmethod
    def die(logger: logging.Logger | None, msg: str, code: int = 1) -> None:
        """Log an error (if a logger is given) and raise a Fatal with the given exit code."""
        if logger:
            logger.error(msg)
        raise Fatal(code, msg)

    @staticmethod
    def ensure_dir(p: Path) -> None:
        """Create the directory (and parents) if it doesn't already exist."""
        p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def which(prog: str) -> str | None:
        """Locate an executable on PATH, or None if not found."""
        return _which(prog)

    @staticmethod
    def which_virt_filesystems() -> str | None:
        """``virt-filesystems`` from libguestfs-tools.

        Resolves when the binary lives under ``/usr/sbin`` (or similar) but the
        current ``PATH`` omits that directory — common for non-interactive jobs and
        some unit tests.
        """
        w = _which("virt-filesystems")
        if w:
            return w
        for cand in (
            "/usr/bin/virt-filesystems",
            "/usr/sbin/virt-filesystems",
            "/sbin/virt-filesystems",
        ):
            try:
                if Path(cand).is_file() and os.access(cand, os.X_OK):
                    return cand
            except OSError:
                continue
        return None

    # Handles fuser/lsof fallback and multiple platform-specific probing paths; the
    # branching/statement count is inherent to robustly detecting file-lock holders.
    @staticmethod
    def wait_disk_image_unlock(  # pylint: disable=too-many-branches,too-many-statements
        logger: logging.Logger | None,
        path: Path | str,
        *,
        timeout_s: float = 30.0,
        poll_s: float = 1.0,
    ) -> None:
        """Wait until no local process is using the image (best-effort, Linux-oriented).

        Mitigates races where ``virt-filesystems``, ``qemu-img check``, or ``qemu-img info``
        still hold the file while ``qemu-img convert`` starts (e.g. shared-write lock errors).

        Uses GNU ``fuser`` when available (exit code 1 means no accessors). Falls back to
        ``lsof -t``. If neither exists, sleeps briefly so prior ``qemu-img`` can settle.
        """
        p = Path(path)
        try:
            if not p.is_file():
                return
        except OSError:
            return

        ps = str(p)
        deadline = time.monotonic() + float(timeout_s)
        fuser_bin = U.which("fuser")
        if not fuser_bin:
            for cand in ("/usr/sbin/fuser", "/sbin/fuser", "/bin/fuser"):
                try:
                    if Path(cand).is_file() and os.access(cand, os.X_OK):
                        fuser_bin = cand
                        break
                except OSError:
                    continue
        lsof_bin = U.which("lsof")

        if not fuser_bin and not lsof_bin:
            if logger:
                logger.info(
                    "fuser/lsof not available; sleeping 3s as image unlock barrier before next qemu-img step"
                )
            time.sleep(3.0)
            with contextlib.suppress(Exception):
                subprocess.run(["sync"], capture_output=True, text=True, timeout=120, check=False)
            return

        while time.monotonic() < deadline:
            locked = False
            if fuser_bin:
                try:
                    r = subprocess.run(
                        [fuser_bin, ps],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                    # GNU fuser: 0 = at least one process is using the file, 1 = none
                    if r.returncode == 1:
                        locked = False
                    elif r.returncode == 0:
                        locked = True
                    else:
                        locked = True
                except (OSError, subprocess.SubprocessError) as e:
                    if logger:
                        logger.debug("fuser probe failed for %s: %s", ps, e)
                    locked = True
            elif lsof_bin:
                try:
                    r = subprocess.run(
                        [lsof_bin, "-t", ps],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                    pids = (r.stdout or "").strip().splitlines()
                    locked = bool(pids)
                except (OSError, subprocess.SubprocessError) as e:
                    if logger:
                        logger.debug("lsof probe failed for %s: %s", ps, e)
                    locked = True

            if not locked:
                with contextlib.suppress(Exception):
                    subprocess.run(["sync"], capture_output=True, text=True, timeout=120, check=False)
                return

            if logger and logger.isEnabledFor(logging.DEBUG):
                logger.debug("Disk image still in use, waiting: %s", ps)
            time.sleep(float(poll_s))

        raise RuntimeError(f"Timed out after {timeout_s:.0f}s waiting for disk image to be unlocked: {ps}")

    @staticmethod
    def post_disk_tool_barrier(
        logger: logging.Logger | None,
        image: Path,
        *,
        settle_s: float = 2.0,
        unlock_timeout_s: float = 25.0,
    ) -> None:
        """After ``virt-filesystems``, ``qemu-img check``, or similar, release FD pressure.

        Libguestfs and qemu-img often exit before helper processes drop the image lock.
        """
        try:
            if not Path(image).is_file():
                return
        except OSError:
            return
        gc.collect()
        if settle_s > 0:
            time.sleep(float(settle_s))
        try:
            U.wait_disk_image_unlock(logger, image, timeout_s=float(unlock_timeout_s))
        except RuntimeError as e:
            if logger:
                logger.warning("Image unlock barrier after disk tooling: %s", e)
        with contextlib.suppress(Exception):
            subprocess.run(["sync"], capture_output=True, text=True, timeout=120, check=False)

    @staticmethod
    def now_ts() -> str:
        """Return the current local timestamp formatted as YYYYMMDD-HHMMSS."""
        return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    @staticmethod
    def json_dump(obj: Any) -> str:
        """Serialize an object to pretty-printed, sorted JSON, falling back to repr() on failure."""
        try:
            return json.dumps(obj, indent=2, sort_keys=True, default=str)
        except Exception:  # pylint: disable=broad-exception-caught
            # This is a best-effort debug/log serializer; any failure falls back to repr().
            return repr(obj)

    @staticmethod
    def human_bytes(n: int | None) -> str:
        """Format a byte count as a human-readable string (e.g. '1.50 GiB')."""
        if n is None:
            return "unknown"
        x = float(n)
        for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
            if x < 1024 or unit == "PiB":
                return f"{x:.2f} {unit}" if unit != "B" else f"{int(x)} {unit}"
            x /= 1024
        return f"{n} B"

    @staticmethod
    def banner(logger: logging.Logger | None, title: str) -> None:
        """Log a title surrounded by horizontal rule lines, for visually separating output sections."""
        if not logger:
            return
        line = "─" * max(10, len(title) + 2)
        logger.info(line)
        logger.info(f" {title}")
        logger.info(line)

    @staticmethod
    def _pretty_cmd(cmd: list[str]) -> str:
        return " ".join(shlex.quote(x) for x in cmd)

    # Central command runner supporting streaming, capture, timeouts, and Fatal-wrapping;
    # the argument count and branching are inherent to covering all these call-site needs
    # in one place rather than duplicating subprocess boilerplate everywhere.
    @staticmethod
    def run_cmd(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
        logger: logging.Logger,
        cmd: list[str],
        *,
        check: bool = True,
        capture: bool = False,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        cwd: str | Path | None = None,
        input_text: str | None = None,
        stream: bool = False,
        fatal: bool = False,
        failure_log_level: int | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Run a command.

        - capture=True uses subprocess.run(capture_output=True, text=True)
        - stream=True streams stdout/stderr to logger in realtime (forces capture=False)
        - fatal=True wraps failures into Fatal (otherwise re-raises subprocess exceptions)
        - failure_log_level=level controls log level for failures (default: ERROR, can be WARNING or DEBUG)
        """
        pretty = U._pretty_cmd(cmd)
        logger.debug("Running: %s", pretty)

        try:
            if stream:
                # Realtime streaming (best for long qemu-img/qemu-nbd etc)
                with subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=str(cwd) if cwd is not None else None,
                ) as proc:
                    try:
                        if proc.stdout is None:
                            raise RuntimeError(
                                "Failed to capture command output. "
                                "Check system resources (open file limits, available memory)."
                            )
                        out_lines: list[str] = []
                        for line in proc.stdout:
                            line = line.rstrip("\n")
                            out_lines.append(line)
                            logger.info(line)
                        rc = proc.wait(timeout=timeout)
                        stdout = "\n".join(out_lines) if out_lines else ""
                        cp = subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")
                        if check and rc != 0:
                            raise subprocess.CalledProcessError(rc, cmd, output=stdout, stderr="")
                        return cp
                    finally:
                        with contextlib.suppress(Exception):
                            if proc.stdout is not None:
                                proc.stdout.close()
                        with contextlib.suppress(Exception):
                            if proc.stderr is not None:
                                proc.stderr.close()
                        with contextlib.suppress(Exception):
                            if proc.poll() is None:
                                proc.wait(timeout=5)

            # Non-streaming path
            return subprocess.run(
                cmd,
                check=check,
                capture_output=capture,
                text=True,
                env=env,
                timeout=timeout,
                cwd=str(cwd) if cwd is not None else None,
                input=input_text,
            )

        except subprocess.CalledProcessError as e:
            stdout = (e.stdout or e.output or "").strip()
            stderr = (e.stderr or "").strip()

            # Determine log level: use failure_log_level if specified, otherwise ERROR
            log_level = failure_log_level if failure_log_level is not None else logging.ERROR

            # Only log if not DEBUG level or if logger is at DEBUG level
            if log_level != logging.DEBUG or logger.isEnabledFor(logging.DEBUG):
                if stdout or stderr:
                    logger.log(
                        log_level,
                        "Command failed: %s%s%s",
                        pretty,
                        f"\nstdout:\n{stdout}" if stdout else "",
                        f"\nstderr:\n{stderr}" if stderr else "",
                    )
                else:
                    logger.log(log_level, "Command failed: %s (no output)", pretty)

            if fatal:
                raise Fatal(e.returncode or 1, f"Command failed: {pretty}") from e
            raise

        except subprocess.TimeoutExpired as e:
            logger.exception("Command timed out: %s (timeout=%ss)", pretty, timeout)
            if fatal:
                raise Fatal(124, f"Command timed out: {pretty}") from e
            raise

        except FileNotFoundError as e:
            # Avoid logger.exception noise when the binary is not installed (common on minimal hosts).
            logger.warning("Executable not found for %s: %s", pretty, e)
            if fatal:
                raise Fatal(127, f"Executable not found: {pretty}") from e
            raise

        except Exception as e:
            logger.exception("Command error: %s (%s)", pretty, e)
            if fatal:
                raise Fatal(1, f"Command error: {pretty}: {e}") from e
            raise

    @staticmethod
    def log_virt_filesystems_introspection(
        logger: logging.Logger,
        image: Path,
        *,
        timeout: int | None = 120,
    ) -> dict[str, Any]:
        """Optional disk introspection via ``virt-filesystems`` from libguestfs-tools."""
        vff = U.which_virt_filesystems()
        if not vff:
            logger.warning(
                "virt-filesystems not found — install libguestfs-tools "
                "(e.g. dnf install -y libguestfs-tools; apt install libguestfs-tools). "
                "If the package is installed, ensure PATH includes /usr/sbin "
                "(e.g. export PATH=/usr/local/bin:/usr/bin:/usr/sbin). "
                "skipping optional introspection for %s",
                image,
            )
            return {
                "ok": False,
                "missing_binary": True,
                "cmd": ["virt-filesystems", "-a", str(image), "--all", "--long", "-h"],
            }

        cmd = [vff, "-a", str(image), "--all", "--long", "-h"]
        ret: dict[str, Any]
        try:
            cp = U.run_cmd(logger, cmd, capture=True, check=False, timeout=timeout)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Introspection is optional/best-effort; any failure degrades to a warning + error record.
            logger.warning("virt-filesystems failed for %s: %s", image, e)
            ret = {"ok": False, "error": str(e), "cmd": cmd}
        else:
            out = (cp.stdout or "").strip()
            if out:
                logger.info("virt-filesystems -a %s --all --long -h\n%s", image, out)
            else:
                logger.info("virt-filesystems -a %s: (empty)", image)
            ret = {"ok": True, "stdout": out, "cmd": cmd, "rc": getattr(cp, "returncode", 0)}

        U.post_disk_tool_barrier(logger, Path(image))
        return ret

    @staticmethod
    def require_root_if_needed(logger: logging.Logger, write_actions: bool) -> None:
        """Die with a Fatal error if write_actions is requested but the process isn't root."""
        if not write_actions:
            return
        if os.geteuid() != 0:
            U.die(logger, "This operation requires root. Re-run with sudo.", 1)

    @staticmethod
    def checksum(path: Path, algo: str = "sha256") -> str:
        """Compute the hex digest of a file's contents using the given hash algorithm."""
        h = hashlib.new(algo)
        total_size = path.stat().st_size
        chunk = SIZE_1_MIB

        def _iter_blocks(f) -> Iterable[bytes]:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                yield b

        _log = logging.getLogger(__name__)
        processed = 0
        last_log_pct = -1

        with open(path, "rb") as f:
            for blk in _iter_blocks(f):
                h.update(blk)
                processed += len(blk)
                if total_size > 0:
                    pct = int(processed * 100 / total_size)
                    if pct >= last_log_pct + 10:
                        _log.info("Computing checksum: %d%%", pct)
                        last_log_pct = pct
        return h.hexdigest()

    @staticmethod
    def safe_unlink(p: Path, *, missing_ok: bool = True) -> None:
        """Delete a file, ignoring FileNotFoundError when missing_ok, and swallowing other errors."""
        try:
            p.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise
        except Exception:  # pylint: disable=broad-exception-caught
            # deliberately quiet (callers can log if they care)
            pass

    @staticmethod
    def to_text(x: Any) -> str:
        """Coerce a value (None, bytes, or anything else) to a plain str."""
        if x is None:
            return ""
        if isinstance(x, bytes):
            return x.decode("utf-8", "replace")
        return str(x)

    @staticmethod
    def human_to_bytes(s: str) -> int:
        """
        Parse human sizes:
          - "10G", "10GiB", "10GB"
          - "512M", "512MiB"
          - "1024" (bytes)
        """
        raw = s.strip()
        if not raw:
            raise ValueError(
                "Disk size value is empty. Provide a size like '10G', '512M', or '1024' (bytes)."
            )

        t = raw.upper().replace(" ", "")
        # normalize common suffixes
        t = (
            t.replace("KIB", "KI")
            .replace("MIB", "MI")
            .replace("GIB", "GI")
            .replace("TIB", "TI")
            .replace("PIB", "PI")
        )
        t = t.replace("KB", "K").replace("MB", "M").replace("GB", "G").replace("TB", "T").replace("PB", "P")
        t = t.rstrip("B")

        multipliers = {
            "": 1,
            "K": 1024,
            "KI": 1024,
            "M": 1024**2,
            "MI": 1024**2,
            "G": 1024**3,
            "GI": 1024**3,
            "T": 1024**4,
            "TI": 1024**4,
            "P": 1024**5,
            "PI": 1024**5,
        }

        # split numeric and suffix
        num = ""
        suf = ""
        for i, ch in enumerate(t):
            if ch.isdigit() or ch in {".", "-"}:
                num += ch
            else:
                suf = t[i:]
                break

        if suf not in multipliers:
            raise ValueError(
                f"Unrecognized size unit '{suf}' in '{raw}'. "
                f"Supported units: K, M, G, T, P (e.g., '10G', '512M', '1T')."
            )

        result = int(float(num) * multipliers[suf])
        if result < 0:
            raise ValueError(f"Negative size '{raw}' is not allowed. Size must be a positive value.")
        return result


def guest_has_cmd(g: guestfs.GuestFS, cmd: str) -> bool:
    """
    Replacement for g.available() checks.
    Uses a shell inside the appliance in a way that avoids injection.

    Note: Uses command_quiet() if available (VMCraft) to suppress error logging
    since these checks often fail (e.g., checking for mdadm/zpool in minimal guests).
    """
    try:
        # Pass cmd as $1 so it isn't interpolated into the shell string.
        # Use command_quiet if available (VMCraft) to suppress error logging for expected failures
        if hasattr(g, "command_quiet"):
            out = g.command_quiet(
                [
                    "sh",
                    "-lc",
                    'command -v "$1" >/dev/null 2>&1 && echo YES || echo NO',
                    "sh",
                    cmd,
                ]
            )
        else:
            out = g.command(
                [
                    "sh",
                    "-lc",
                    'command -v "$1" >/dev/null 2>&1 && echo YES || echo NO',
                    "sh",
                    cmd,
                ]
            )
        return U.to_text(out).strip() == "YES"
    except Exception:  # pylint: disable=broad-exception-caught
        # command-existence probes commonly fail for missing binaries in minimal guests;
        # any failure just means "not available".
        return False


def guest_ls_glob(g: guestfs.GuestFS, pattern: str) -> list[str]:
    """
    Replacement for g.glob().
    Uses g.glob_expand() which is safe from shell injection.
    Falls back to manual directory listing + fnmatch for VMCraft backend
    which doesn't implement glob_expand().

    NOTE: Returns matches that exist in the guest filesystem.
    """
    try:
        return [U.to_text(x) for x in g.glob_expand(pattern)]
    except (AttributeError, NotImplementedError):
        # VMCraft backend doesn't have glob_expand — fallback to manual glob
        pass
    except Exception:  # pylint: disable=broad-exception-caught
        # glob_expand() failures (bad pattern, guest FS quirks) degrade to "no matches".
        return []

    # Manual fallback: list directory + fnmatch
    dir_path = pattern.rsplit("/", 1)[0] if "/" in pattern else "/"
    file_pattern = pattern.rsplit("/", 1)[1] if "/" in pattern else pattern
    try:
        if not g.is_dir(dir_path):
            return []
        entries = g.ls(dir_path)
        matches = []
        for entry in entries:
            name = U.to_text(entry) if isinstance(entry, bytes) else entry
            if fnmatch.fnmatch(name, file_pattern):
                full_path = f"{dir_path}/{name}"
                matches.append(full_path)
        return matches
    except Exception:  # pylint: disable=broad-exception-caught
        # Manual directory-listing fallback; any guest FS access failure means "no matches".
        return []


def blinking_progress(logger: logging.Logger, label: str, interval: float = 0.12):
    """Tiny spinner context manager for long-running external commands.
    Avoids drawing if stderr isn't a TTY (so CI logs don't become hieroglyphs).
    """

    @contextlib.contextmanager
    def _cm():
        is_tty = getattr(sys.stderr, "isatty", lambda: False)()
        if not is_tty:
            logger.debug("%s ...", label)
            yield
            logger.debug("%s done", label)
            return

        stop = threading.Event()
        spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])

        def run():
            while not stop.is_set():
                ch = next(spinner)
                sys.stderr.write(f"\r{ch} {label}")
                sys.stderr.flush()
                time.sleep(interval)
            sys.stderr.write(f"\r✅ {label}\n")
            sys.stderr.flush()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=1.0)

    return _cm()
