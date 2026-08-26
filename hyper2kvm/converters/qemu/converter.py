# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/converters/qemu/converter.py
# pylint: disable=too-many-lines  # cohesive qemu-img conversion/progress-parsing implementation, splitting would hurt readability more than help
"""QEMU disk format converter (qcow2, vmdk, raw)."""
# pylint: disable=duplicate-code
# reason: the qemu-img stderr progress-parsing loop here structurally mirrors
# hyper2kvm/converters/flatten.py's progress parser, but the two differ in real
# ways (this module adds a fraction-regex match and stricter bare-percent gating)
# -- kept independent rather than forcing a shared helper across them.

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hyper2kvm.core.exceptions import DiskConversionError
from hyper2kvm.core.structured_log import log_event
from hyper2kvm.core.utils import U

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable, Iterable


class Convert:
    """
    Notes:
      - We intentionally DO NOT expose/attempt --target-is-zero here.
        qemu-img requires -n (no-create) for --target-is-zero, which doesn't fit
        this fresh-file atomic workflow. If you later add a "precreate + -n"
        pathway (block/LV targets), implement that as a separate mode.
    """

    _RE_PAREN = re.compile(r"\((\d+(?:\.\d+)?)/100%\)")
    _RE_FRACTION = re.compile(r"(\d+(?:\.\d+)?)/100%")
    _RE_PROGRESS = re.compile(r"(?:progress|Progress)\s*[:=]\s*(\d+(?:\.\d+)?)")
    _RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")
    _RE_JSON = re.compile(r"^\s*\{.*\}\s*$")

    _RE_EXPECTED_FALLBACK = re.compile(
        r"("
        r"unknown option|unrecognized option|invalid option|"
        r"not supported|unsupported|"
        r"cannot be used with|mutually exclusive|"
        r"(?:compression_type|compression_level).*invalid"
        r")",
        re.IGNORECASE,
    )

    @dataclass(frozen=True)
    class ConvertOptions:
        """qemu-img convert tuning knobs (cache mode, threads, compression, preallocation)."""

        cache_mode: str = "none"  # none|writeback|unsafe|"" (disabled)
        threads: int | None = None  # -m N
        compression_type: str | None = "zstd"  # zstd|zlib|None (omit)
        compression_level: int | None = None  # compression_level=...
        preallocation: str | None = None  # preallocation=metadata, ...

        def short(self) -> str:
            """Return a compact one-line summary of these options for logging."""
            return (
                f"cache={self.cache_mode or 'off'} "
                f"threads={self.threads or 'off'} "
                f"ctype={self.compression_type or 'omit'} "
                f"clevel={self.compression_level if self.compression_level is not None else 'omit'} "
                f"prealloc={self.preallocation or 'omit'}"
            )

    # Public API

    @staticmethod
    def convert_image_with_progress(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
        logger: logging.Logger,
        src: Path,
        dst: Path,
        *,
        out_format: str,
        compress: bool,
        compress_level: int | None = None,
        compression_type: str | None = "zstd",
        progress_callback: Callable[[float], None] | None = None,
        in_format: str | None = None,
        preallocation: str | None = None,
        atomic: bool = True,
        cache_mode: str = "none",
        threads: int | None = None,
        ui_poll_s: float = 0.20,
        max_stderr_tail: int = 200,
    ) -> None:
        """Run qemu-img convert with live progress parsing, atomic replace, and format-specific tuning."""
        src = Path(src)
        dst = Path(dst)

        if U.which("qemu-img") is None:
            U.die(
                logger,
                "qemu-img not found. Install it:\n"
                "  RHEL/Fedora: sudo dnf install qemu-img\n"
                "  Ubuntu/Debian: sudo apt install qemu-utils\n"
                "  SUSE: sudo zypper install qemu-tools",
                1,
            )

        src = Convert._prefer_descriptor_for_flat(logger, src)
        if not src.is_file():
            raise FileNotFoundError(
                f"Source image file not found: {src}\n"
                "Verify the disk image path is correct and the file has not been moved or deleted.\n"
                "For split VMDKs, ensure both the descriptor (.vmdk) and extent (-flat.vmdk) files are present."
            )

        U.ensure_dir(dst.parent)

        final_dst = dst
        tmp_dst = dst.with_suffix(dst.suffix + ".part") if atomic else dst

        virt_size, detected_fmt = Convert._qemu_img_info(logger, src)
        if in_format is None:
            in_format = detected_fmt

        base = Convert.ConvertOptions(
            cache_mode=cache_mode,
            threads=threads,
            compression_type=compression_type,
            compression_level=compress_level,
            preallocation=preallocation,
        )

        plan = list(Convert._fallback_plan(base, out_format=out_format, compress=compress))

        U.banner(logger, f"Convert to {out_format.upper()}")
        log_event(
            "qemu_convert_start",
            source=str(src),
            destination=str(final_dst),
            in_format=in_format or "auto",
            out_format=out_format,
            compress=compress,
        )
        logger.info(
            f"Converting: {src} -> {final_dst} "
            f"(in_format={in_format or 'auto'}, out_format={out_format}, compress={compress}, atomic={atomic})"
        )

        last_error: subprocess.CalledProcessError | None = None

        for attempt_no, opt in enumerate(plan, start=1):
            if atomic and tmp_dst.exists():
                tmp_dst.unlink(missing_ok=True)

            cmd = Convert._build_convert_cmd(
                src=src,
                dst=tmp_dst,
                in_format=in_format,
                out_format=out_format,
                compress=compress,
                opt=opt,
            )

            logger.debug(f"[attempt {attempt_no}/{len(plan)}] opts: {opt.short()}")
            logger.debug(f"[attempt {attempt_no}/{len(plan)}] cmd: {' '.join(cmd)}")

            try:
                rc, stderr_lines = Convert._run_convert_process(
                    logger,
                    cmd,
                    tmp_dst=tmp_dst,
                    virt_size=virt_size,
                    ui_poll_s=ui_poll_s,
                    progress_callback=progress_callback,
                )
            except KeyboardInterrupt:
                logger.warning("Interrupted; aborting conversion.")
                raise

            if rc == 0:
                if atomic:
                    if not tmp_dst.exists():
                        raise FileNotFoundError(
                            f"Temporary conversion file missing: {tmp_dst}\n"
                            "It may have been removed by disk auto-cleanup during qemu-img convert. "
                            "Free space under /var/lib/hyper2kvm or disable auto-cleanup, then retry."
                        )
                    tmp_dst.replace(final_dst)
                Convert._safe_progress_callback(progress_callback, 1.0, logger=logger)
                if stderr_lines:
                    logger.debug("qemu-img stderr (tail):\n" + "\n".join(stderr_lines[-80:]))
                log_event(
                    "qemu_convert_complete",
                    source=str(src),
                    destination=str(final_dst),
                    out_format=out_format,
                    attempt=attempt_no,
                )
                return

            tail_lines = stderr_lines[-max_stderr_tail:] if stderr_lines else []
            tail = "\n".join(tail_lines) if tail_lines else ""

            match = Convert._RE_EXPECTED_FALLBACK.search(tail) if tail else None
            is_expected = match is not None

            if is_expected:
                snippet = Convert._extract_match_snippet(tail, match, radius=140)
                U.banner(logger, f"Fallback attempt {attempt_no}/{len(plan)} (options rejected)")
                logger.warning(f"Reason: {snippet}")
                logger.warning(f"Downgrading options. opts: {opt.short()}")
                if tail:
                    logger.debug("qemu-img stderr (tail):\n" + tail)
            else:
                logger.error(f"Conversion attempt {attempt_no} failed (rc={rc}). opts: {opt.short()}")
                if tail:
                    logger.error("qemu-img stderr (tail):\n" + tail)

            last_error = subprocess.CalledProcessError(rc, cmd)

        if atomic and tmp_dst.exists():
            with contextlib.suppress(Exception):
                tmp_dst.unlink()
        if last_error is None:
            raise DiskConversionError(
                code=73,
                msg=(
                    f"Disk conversion failed for '{src.name}' after {len(plan)} attempts, "
                    "but no specific error was captured."
                ),
            ).with_context(
                solutions=[
                    "Check available disk space: df -h " + str(dst.parent),
                    "Verify qemu-img is installed and up to date: qemu-img --version",
                    "Check system logs for OOM or I/O errors: journalctl -xe",
                    f"Try manual conversion: qemu-img convert -f auto -O {out_format} '{src}' '{dst}'",
                ],
                source_path=str(src),
                destination_path=str(dst),
                out_format=out_format,
                attempts=len(plan),
            )
        # Re-raise the last CalledProcessError with context
        raise DiskConversionError(
            code=last_error.returncode or 73,
            msg=(
                f"Disk conversion failed for '{src.name}': qemu-img exited with code {last_error.returncode}. "
                "Check available disk space and that the source image is not corrupted."
            ),
            cause=last_error,
        ).with_context(
            solutions=[
                f"Check disk space: df -h {dst.parent}",
                f"Verify source image: qemu-img check '{src}'",
                "Re-run with --verbose for detailed qemu-img output",
            ],
            source_path=str(src),
            destination_path=str(dst),
        ) from last_error

    @staticmethod
    def convert_image(  # pylint: disable=too-many-arguments  # thin wrapper mirrors convert_image_with_progress's public surface
        logger: logging.Logger,
        src: Path,
        dst: Path,
        *,
        out_format: str,
        compress: bool,
        compress_level: int | None = None,
        in_format: str | None = None,
    ) -> None:
        """Convert an image without progress reporting (see convert_image_with_progress)."""
        Convert.convert_image_with_progress(
            logger,
            src,
            dst,
            out_format=out_format,
            compress=compress,
            compress_level=compress_level,
            progress_callback=None,
            in_format=in_format,
        )

    @staticmethod
    def validate(logger: logging.Logger, path: Path, *, strict: bool = True) -> None:
        """Validate a converted image with qemu-img check (best-effort; warns instead of raising unless strict)."""
        path = Convert._prefer_descriptor_for_flat(logger, Path(path))
        if not path.is_file():
            logger.warning(
                f"Image file not found for validation: {path}\n"
                "The conversion may have failed silently. Check available disk space "
                "and that the source image was not removed during conversion."
            )
            return
        if U.which("qemu-img") is None:
            logger.warning(
                "qemu-img not found, skipping validation.\n"
                "    Install with: dnf install qemu-img  (or: apt install qemu-utils)"
            )
            return
        cmd = ["qemu-img", "check", str(path)]
        logger.debug(f"Executing validation command: {' '.join(cmd)}")
        cp = U.run_cmd(logger, cmd, check=False, capture=True)
        if cp.returncode == 0:
            logger.info("Image validation: OK (qemu-img check)")
            U.post_disk_tool_barrier(logger, Path(path), settle_s=1.0, unlock_timeout_s=20.0)
            return
        if not strict:
            logger.warning("Image validation: WARNING (qemu-img check reported issues)")
            logger.debug(f"return code: {cp.returncode}")
            logger.debug("stdout:\n" + (cp.stdout or ""))
            logger.debug("stderr:\n" + (cp.stderr or ""))
            return
        tail = ((cp.stderr or "") + (cp.stdout or "")).strip()
        raise DiskConversionError(
            code=cp.returncode or 73,
            msg=(
                f"qemu-img check failed for '{path.name}' (exit code {cp.returncode}). "
                "The image must be structurally sound before the pipeline continues."
            ),
        ).with_context(
            solutions=[
                f"Inspect manually: qemu-img check '{path}'",
                "Verify no other process has the image open (libguestfs, libvirt, backup tools)",
                "Re-export or re-convert the source disk if corruption is confirmed",
            ],
            source_path=str(path),
            check_stderr=tail[:4000] if tail else "",
        )

    # Fallback Policy (deduped)

    @staticmethod
    def _fallback_plan(
        base: ConvertOptions,
        *,
        out_format: str,
        compress: bool,
    ) -> Iterable[ConvertOptions]:
        def key(o: Convert.ConvertOptions) -> tuple:
            return (
                o.cache_mode,
                o.threads,
                o.compression_type,
                o.compression_level,
                o.preallocation,
            )

        seen: set[tuple] = set()
        ordered: list[Convert.ConvertOptions] = []

        def emit(opt: Convert.ConvertOptions) -> None:
            k = key(opt)
            if k in seen:
                return
            seen.add(k)
            ordered.append(opt)

        emit(base)

        if base.threads:
            emit(
                Convert.ConvertOptions(
                    cache_mode=base.cache_mode,
                    threads=None,
                    compression_type=base.compression_type,
                    compression_level=base.compression_level,
                    preallocation=base.preallocation,
                )
            )

        if out_format == "qcow2" and compress:
            if base.compression_type == "zstd":
                emit(
                    Convert.ConvertOptions(
                        cache_mode=base.cache_mode,
                        threads=None,
                        compression_type="zlib",
                        compression_level=base.compression_level,
                        preallocation=base.preallocation,
                    )
                )

            emit(
                Convert.ConvertOptions(
                    cache_mode=base.cache_mode,
                    threads=None,
                    compression_type=None,
                    compression_level=base.compression_level,
                    preallocation=base.preallocation,
                )
            )

            if base.compression_level is not None:
                emit(
                    Convert.ConvertOptions(
                        cache_mode=base.cache_mode,
                        threads=None,
                        compression_type=None,
                        compression_level=None,
                        preallocation=base.preallocation,
                    )
                )

        if base.cache_mode:
            emit(
                Convert.ConvertOptions(
                    cache_mode="",
                    threads=None,
                    compression_type=None if (out_format == "qcow2" and compress) else base.compression_type,
                    compression_level=None
                    if (out_format == "qcow2" and compress)
                    else base.compression_level,
                    preallocation=base.preallocation,
                )
            )

        emit(
            Convert.ConvertOptions(
                cache_mode="",
                threads=None,
                compression_type=None,
                compression_level=None,
                preallocation=None,
            )
        )

        yield from ordered

    # Core runner (progress + stderr capture)

    @staticmethod
    def _run_convert_process(  # pylint: disable=too-many-arguments,too-many-locals,too-many-statements  # single cohesive progress-poll/stderr-capture loop
        logger: logging.Logger,
        cmd: list[str],
        *,
        tmp_dst: Path,
        virt_size: int,
        ui_poll_s: float,
        progress_callback: Callable[[float], None] | None,
        callback_min_delta: float = 0.001,  # 0.1%
        size_poll_s: float = 0.50,
        log_every_s: float = 30.0,  # liveness logging even if % flat (non-interactive)
        task_label: str = "Conversion",
    ) -> tuple[int, list[str]]:
        start = time.time()
        stderr_lines: list[str] = []

        # Log-based progress for all modes (no Rich dependency).
        interactive = False

        # pylint: disable-next=consider-using-with  # process spans the whole function with custom poll/terminate/kill cleanup below
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=False,
            bufsize=0,
        )
        if proc.stderr is None:
            raise RuntimeError(
                "Failed to capture qemu-img output — the process started but stderr could not be read. "
                "This usually indicates exhausted system resources.\n"
                "Check: ulimit -n (open file limit), free -h (available memory), "
                "and /var/log/messages for OOM killer activity."
            )

        fd = proc.stderr.fileno()
        nonblocking_ok = False
        try:
            os.set_blocking(fd, False)
            nonblocking_ok = True
        except OSError:
            nonblocking_ok = False

        buf = b""

        def push_line(line_b: bytes) -> None:
            stderr_lines.append(line_b.decode("utf-8", errors="replace").rstrip("\n"))

        def read_available() -> int:
            nonlocal buf
            total = 0
            while True:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    return total
                except OSError:
                    return total
                if not chunk:
                    return total
                total += len(chunk)
                buf += chunk
                while True:
                    i = buf.find(b"\n")
                    if i < 0:
                        break
                    line = buf[: i + 1]
                    buf = buf[i + 1 :]
                    push_line(line)

        def drain_remaining() -> None:
            read_available()
            nonlocal buf
            if buf:
                push_line(buf)
                buf = b""

        last_seen_pct: float | None = None
        best_pct = 0.0
        processed_lines = 0
        last_io_tick = time.time()

        saw_real_pct = False
        just_snapped_to_truth = False  # one-shot event flag

        def clamp_pct(p: float) -> float:
            # NaN-safe clamp
            if math.isnan(p):
                return 0.0
            return max(0.0, min(100.0, p))

        def update_best(pct: float) -> None:
            nonlocal best_pct
            pct = clamp_pct(pct)
            best_pct = max(best_pct, pct)

        def parse_progress_pct(  # pylint: disable=too-many-return-statements,too-many-branches  # tries several qemu-img progress line formats in order
            line: str,
        ) -> float | None:
            s = (line or "").strip()
            if not s:
                return None

            if Convert._RE_JSON.match(s):
                try:
                    o = json.loads(s)
                    for k in ("progress", "percent", "pct"):
                        if k in o:
                            v = float(o[k])
                            return v if 0.0 <= v <= 100.0 else None
                except (ValueError, TypeError):
                    return None

            m = Convert._RE_PAREN.search(s)
            if m:
                try:
                    return float(m.group(1))
                except (ValueError, TypeError):
                    return None

            m = Convert._RE_FRACTION.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except (ValueError, TypeError):
                    return None

            m = Convert._RE_PROGRESS.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except (ValueError, TypeError):
                    return None

            # Tightened bare "NN%" parsing: require strong progress-ish context
            ss = s.lower()
            looks_like_progress = (
                "progress" in ss
                or "converting" in ss
                or "converted" in ss
                or "copying" in ss
                or "copied" in ss
            )
            if looks_like_progress:
                m = Convert._RE_PERCENT.search(s)
                if m:
                    try:
                        v = float(m.group(1))
                        return v if 0.0 <= v <= 100.0 else None
                    except (ValueError, TypeError):
                        return None

            return None

        def parse_new_lines() -> None:
            nonlocal processed_lines, last_seen_pct, saw_real_pct, best_pct, just_snapped_to_truth
            if processed_lines >= len(stderr_lines):
                return
            new_lines = stderr_lines[processed_lines:]
            processed_lines = len(stderr_lines)
            for line in new_lines:
                pct = parse_progress_pct(line)
                if pct is None:
                    continue
                pct = clamp_pct(pct)
                last_seen_pct = pct
                if not saw_real_pct:
                    best_pct = pct  # snap to truth once
                    saw_real_pct = True
                    just_snapped_to_truth = True
                else:
                    update_best(pct)

        def tmp_written_bytes() -> int | None:
            try:
                if not tmp_dst.exists():
                    return None
                return int(tmp_dst.stat().st_size)
            except OSError:
                return None

        def maybe_advance_pct_from_written(written_b: int | None) -> None:
            nonlocal best_pct
            if last_seen_pct is not None:
                return
            if virt_size <= 0 or written_b is None:
                return
            est = 100.0 * float(written_b) / float(virt_size)
            # never claim "done" from file size; qemu may still be finishing metadata
            est = min(est, 99.0)
            best_pct = max(best_pct, clamp_pct(est))

        last_cb_frac = -1.0

        def maybe_callback(frac: float) -> None:
            nonlocal last_cb_frac
            if progress_callback is None:
                return
            frac = max(0.0, min(1.0, frac))
            if last_cb_frac < 0:
                last_cb_frac = frac
                Convert._safe_progress_callback(progress_callback, frac, logger=logger)
                return
            if (frac - last_cb_frac) >= callback_min_delta:
                last_cb_frac = frac
                Convert._safe_progress_callback(progress_callback, frac, logger=logger)

        last_size_poll = 0.0
        cached_written: int | None = None

        # --- dynamic log throttling (prevents spam while Rich is live) ---
        last_emit_t = start
        last_emit_pct = 0.0

        def _clamp(v: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, v))

        def should_emit_progress(now: float) -> bool:
            nonlocal last_emit_t, last_emit_pct

            base_target_s = 20.0 if interactive else 45.0
            max_silence_s = 60.0 if interactive else 120.0

            dt = max(1e-6, now - last_emit_t)
            dp = max(0.0, best_pct - last_emit_pct)
            pct_rate = dp / dt  # % per second since last emit

            dyn_min_delta = _clamp(pct_rate * base_target_s, 0.5, 5.0)

            time_due = (now - last_emit_t) >= base_target_s
            progressed_enough = (best_pct - last_emit_pct) >= dyn_min_delta
            too_silent = (now - last_emit_t) >= max_silence_s

            if (time_due and progressed_enough) or too_silent:
                last_emit_t = now
                last_emit_pct = best_pct
                return True
            return False

        def poll_io(sel: selectors.BaseSelector) -> None:
            nonlocal last_io_tick
            if nonblocking_ok:
                n0 = read_available()
                if n0 > 0:
                    last_io_tick = time.time()
                parse_new_lines()
            events = sel.select(timeout=ui_poll_s)
            if events:
                n = read_available()
                if n > 0:
                    last_io_tick = time.time()
                parse_new_lines()

        def update_caches(now: float) -> None:
            nonlocal last_size_poll, cached_written
            if (now - last_size_poll) >= size_poll_s:
                cached_written = tmp_written_bytes()
                last_size_poll = now

        def compute_best(now: float) -> None:
            nonlocal best_pct, just_snapped_to_truth, last_emit_t, last_emit_pct
            maybe_advance_pct_from_written(cached_written)
            best_pct = clamp_pct(best_pct)

            if just_snapped_to_truth:
                logger.info(
                    "qemu-img progress detected; switching from estimation to true percent reporting."
                )
                # Reset emit gate so we don't immediately spam after snapping.
                last_emit_t = now
                last_emit_pct = best_pct
                just_snapped_to_truth = False

        def log_progress(now: float) -> None:
            nonlocal last_emit_t, last_emit_pct

            # Interactive: bar/spinner is the UI; keep logs rare.
            if interactive and not should_emit_progress(now):
                return

            # Non-interactive: gentle heartbeat regardless.
            if (not interactive) and (now - last_emit_t) < log_every_s:
                return

            if virt_size > 0 and last_seen_pct is not None:
                pct_for_rate = last_seen_pct  # truth-phase
                est_bytes = (pct_for_rate / 100.0) * float(virt_size)
                mb_s = (est_bytes / max(1e-6, (now - start))) / 1024 / 1024
                logger.info(f"⏳ {task_label} progress: {best_pct:.1f}% (~{mb_s:.1f} MB/s avg)")
            else:
                # In estimation/unknown phase: keep this line short (avoid noise)
                logger.info(f"⏳ {task_label} progress: {best_pct:.1f}%")

            # Keep emit state aligned for both modes.
            last_emit_t = now
            last_emit_pct = best_pct

        try:
            with selectors.DefaultSelector() as sel:
                sel.register(proc.stderr, selectors.EVENT_READ)

                while True:
                    poll_io(sel)
                    now = time.time()
                    update_caches(now)
                    compute_best(now)
                    log_progress(now)
                    maybe_callback(best_pct / 100.0)
                    if proc.poll() is not None:
                        break

                rc = proc.wait()
                drain_remaining()
                parse_new_lines()
                if rc == 0:
                    best_pct = 100.0
                    maybe_callback(1.0)
                return rc, stderr_lines

        except KeyboardInterrupt:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except Exception:  # pylint: disable=broad-exception-caught  # interrupt cleanup must not itself raise; fall back to kill()
                    proc.kill()
            finally:
                try:
                    drain_remaining()
                    parse_new_lines()
                except Exception:  # pylint: disable=broad-exception-caught  # interrupt cleanup must not itself raise
                    pass
                with contextlib.suppress(Exception):
                    proc.stderr.close()
            raise

        finally:
            try:
                if proc.poll() is not None:
                    drain_remaining()
            except Exception:  # pylint: disable=broad-exception-caught  # final cleanup must not itself raise
                pass
            with contextlib.suppress(Exception):
                proc.stderr.close()

    # Cmd builder / helpers

    @staticmethod
    def _build_convert_cmd(  # pylint: disable=too-many-arguments  # each qemu-img convert flag maps 1:1 to a distinct parameter
        *,
        src: Path,
        dst: Path,
        in_format: str | None,
        out_format: str,
        compress: bool,
        opt: ConvertOptions,
    ) -> list[str]:
        cmd: list[str] = ["qemu-img", "convert", "-p"]

        if opt.cache_mode:
            cmd += ["-t", opt.cache_mode, "-T", opt.cache_mode]

        if opt.threads and opt.threads > 0:
            cmd += ["-m", str(int(opt.threads))]

        if in_format:
            cmd += ["-f", in_format]

        cmd += ["-O", out_format]

        if out_format == "qcow2":
            opts: list[str] = []
            if opt.preallocation:
                opts.append(f"preallocation={opt.preallocation}")

            if compress:
                cmd.append("-c")
                if opt.compression_type:
                    opts.append(f"compression_type={opt.compression_type}")
                if opt.compression_level is not None:
                    opts.append(f"compression_level={int(opt.compression_level)}")

            if opts:
                cmd += ["-o", ",".join(opts)]

        cmd += [str(src), str(dst)]
        return cmd

    @staticmethod
    def _prefer_descriptor_for_flat(logger: logging.Logger, src: Path) -> Path:
        s = str(src)
        if s.endswith("-flat.vmdk"):
            descriptor = src.with_name(src.name.replace("-flat.vmdk", ".vmdk"))
            if descriptor.is_file():
                logger.info(f"Detected flat VMDK; using descriptor: {descriptor}")
                return descriptor
        return src

    @staticmethod
    def _compression_type_from_info(info: dict) -> str | None:
        fs = info.get("format-specific")
        if not isinstance(fs, dict):
            return None
        data = fs.get("data")
        if not isinstance(data, dict):
            return None
        raw = data.get("compression-type") or data.get("compression_type")
        if raw is None:
            return None
        return str(raw).strip().lower() or None

    @staticmethod
    def format_qemu_img_info_summary(info: dict, *, path: str | Path = "") -> str:
        """One-line human summary of ``qemu-img info --output=json``."""
        virt = int(info.get("virtual-size", 0) or 0)
        actual = int(info.get("actual-size", 0) or 0)
        fmt = info.get("format") or "unknown"
        label = Path(path).name if path else "image"
        parts = [f"format={fmt}"]
        if virt:
            parts.append(f"virtual={virt / (1024**3):.2f} GiB")
        if actual:
            parts.append(f"actual={actual / (1024**3):.2f} GiB")
        comp = Convert._compression_type_from_info(info)
        if comp:
            parts.append(f"compression={comp}")
        return f"qemu-img info {label}: " + ", ".join(parts)

    @staticmethod
    def qemu_img_info(logger: logging.Logger, src: Path) -> dict:
        """
        Run ``qemu-img info --output=json``, log a summary at INFO, return parsed JSON.
        """
        info_cmd = ["qemu-img", "info", "--output=json", str(src)]
        logger.debug("Executing: %s", " ".join(info_cmd))
        try:
            info_result = subprocess.run(info_cmd, capture_output=True, text=True, check=True)
        except FileNotFoundError as err:
            raise RuntimeError(
                "qemu-img not found. Install it:\n"
                "  RHEL/Fedora: sudo dnf install qemu-img\n"
                "  Ubuntu/Debian: sudo apt install qemu-utils"
            ) from err
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            stdout = (e.stdout or "").strip()
            detail = stderr or stdout
            msg = f"qemu-img info failed for {src}"
            if detail:
                msg += f": {detail}"
            sl = detail.lower()
            if "could not open" in sl or "no such file" in sl:
                msg += (
                    f"\n\nThe disk image '{src.name}' could not be opened. Check:\n"
                    "  - The file exists and is not corrupted\n"
                    "  - For split VMDKs, ensure both the descriptor and -flat.vmdk extent are present\n"
                    "  - The image is not locked by a running VM"
                )
            elif "unknown image format" in sl or "not supported" in sl:
                msg += (
                    f"\n\nThe image format of '{src.name}' is not recognized. "
                    "Supported formats: vmdk, qcow2, raw, vhd, vhdx, vdi. "
                    "If this is a split VMDK, point to the descriptor file (not the -flat.vmdk)."
                )
            raise RuntimeError(msg) from e

        try:
            info = json.loads(info_result.stdout or "{}")
        except Exception as e:
            raise RuntimeError(
                f"Could not read disk image metadata for '{src}' — qemu-img returned invalid output. "
                f"Ensure qemu-img is up to date and the disk image is not corrupted."
            ) from e

        logger.info(Convert.format_qemu_img_info_summary(info, path=src))
        return info

    @staticmethod
    def _qemu_img_info(logger: logging.Logger, src: Path) -> tuple[int, str | None]:
        info = Convert.qemu_img_info(logger, src)
        virt = int(info.get("virtual-size", 0) or 0)
        fmt = info.get("format")
        if fmt is not None and not isinstance(fmt, str):
            fmt = None
        return virt, fmt

    # Small helpers

    @staticmethod
    def _safe_progress_callback(
        cb: Callable[[float], None] | None,
        frac: float,
        *,
        logger: logging.Logger,
    ) -> None:
        if cb is None:
            return
        try:
            cb(max(0.0, min(1.0, frac)))
        except Exception as e:  # pylint: disable=broad-exception-caught  # caller-supplied callback can raise anything; must not abort the conversion
            logger.warning(f"Progress callback raised an error: {e}")

    @staticmethod
    def _extract_match_snippet(text: str, match: re.Match[str], *, radius: int = 140) -> str:
        if not text:
            return ""
        s = text.replace("\r", "\n")
        start = max(0, match.start() - radius)
        end = min(len(s), match.end() + radius)
        snippet = s[start:end]
        snippet = " ".join(snippet.split())
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(s) else ""
        return f"{prefix}{snippet}{suffix}"


def _infer_convert_src(cmd: list[str], dst: Path) -> Path | None:
    """Best-effort source path from a qemu-img convert argv (… SRC DST)."""
    dst_s = str(dst)
    for i in range(len(cmd) - 1, 0, -1):
        if cmd[i] == dst_s and i > 0:
            return Path(cmd[i - 1])
    return None


def run_qemu_img_convert(  # pylint: disable=too-many-arguments,too-many-locals  # thin wrapper mirrors _run_convert_process's full progress/label surface
    logger: logging.Logger,
    cmd: list[str],
    dst: Path,
    *,
    src: Path | None = None,
    task_label: str = "qemu-img convert",
    progress_callback: Callable[[float], None] | None = None,
    log_every_s: float = 15.0,
    check: bool = True,
) -> tuple[int, list[str]]:
    """
    Run ``qemu-img convert`` with ``-p`` progress streamed to the logger.

    Logs ``qemu-img info`` for the source image when available.
    """
    dst = Path(dst)
    src_path = Path(src) if src is not None else _infer_convert_src(cmd, dst)

    virt_size = 0
    if src_path is not None and src_path.is_file():
        try:
            info = Convert.qemu_img_info(logger, src_path)
            virt_size = int(info.get("virtual-size", 0) or 0)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort progress hint; a bad probe must not abort the conversion
            logger.warning("Could not read source image info before convert: %s", e)

    if "-p" not in cmd and "--progress" not in cmd:
        # Insert -p after "convert" subcommand when missing.
        try:
            idx = cmd.index("convert")
            cmd = [*cmd[: idx + 1], "-p", *cmd[idx + 1 :]]
        except ValueError:
            cmd = [*cmd, "-p"]

    rc, stderr_lines = Convert._run_convert_process(  # pylint: disable=protected-access  # module-level helper within the same module as Convert
        logger,
        cmd,
        tmp_dst=dst,
        virt_size=virt_size,
        ui_poll_s=0.25,
        progress_callback=progress_callback,
        log_every_s=log_every_s,
        task_label=task_label,
    )
    if check and rc != 0:
        tail = "\n".join(stderr_lines[-40:]).strip()
        raise subprocess.CalledProcessError(rc, cmd, stderr=tail or f"{task_label} failed (rc={rc})")
    return rc, stderr_lines
