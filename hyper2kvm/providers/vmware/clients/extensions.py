# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""VMware client extensions for asynchronous operations and progress tracking."""

# hyper2kvm/vmware/clients/extensions.py
from __future__ import annotations

import asyncio
import logging
import re
import shlex
from typing import TYPE_CHECKING

from .client import VMwareClient

if TYPE_CHECKING:
    from collections.abc import Sequence

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class _TailBuffer:
    """Small ring buffer holding the last N log lines."""

    def __init__(self, max_lines: int = 80) -> None:
        self.max_lines = max(1, int(max_lines))
        self._lines: list[str] = []

    def add(self, line: str) -> None:
        """Append a line to the buffer, trimming the oldest lines beyond max_lines."""
        if not line:
            return
        self._lines.append(line)
        if len(self._lines) > self.max_lines:
            self._lines = self._lines[-self.max_lines :]

    def text(self) -> str:
        """Return the buffered lines joined by newlines, stripped of leading/trailing whitespace."""
        return "\n".join(self._lines).strip()


def _safe_decode(b: bytes) -> str:
    try:
        return b.decode("utf-8", errors="replace")
    except Exception:  # pylint: disable=broad-exception-caught
        # decode(errors="replace") is nearly infallible; this is a last-resort codec fallback.
        return b.decode(errors="replace")


def _strip_ansi(s: str) -> str:
    # Conservative ANSI remover (keeps logs readable).
    return _ANSI_RE.sub("", s or "")


async def _pump_with_tail(
    stream: asyncio.StreamReader | None,
    logger: logging.Logger,
    level: int,
    prefix: str,
    *,
    tail: _TailBuffer,
) -> None:
    """Line-based pump (uses readline). Kept for compatibility; chunked pump below is safer."""
    if stream is None:
        return

    while True:
        line = await stream.readline()
        if not line:
            break
        msg = _strip_ansi(_safe_decode(line).rstrip())
        if msg:
            tail.add(msg)
            logger.log(level, "%s%s", prefix, msg)


async def _run_logged_subprocess_with_tails(
    logger: logging.Logger,
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    stderr_tail_lines: int = 160,
    stdout_tail_lines: int = 60,
) -> tuple[int, str, str]:
    """
    Like VMwareClient._run_logged_subprocess(), but ALSO returns (rc, stdout_tail, stderr_tail).
    Add-only helper so you don't have to touch the existing method.
    """
    logger.info("Running: %s", " ".join(shlex.quote(a) for a in argv))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    out_tail = _TailBuffer(max_lines=stdout_tail_lines)
    err_tail = _TailBuffer(max_lines=stderr_tail_lines)

    await asyncio.gather(
        _pump_with_tail(proc.stdout, logger, logging.INFO, "", tail=out_tail),
        _pump_with_tail(proc.stderr, logger, logging.INFO, "", tail=err_tail),
    )

    rc = int(await proc.wait())
    return rc, out_tail.text(), err_tail.text()


def _is_transient_vpx_error(stderr_tail: str) -> bool:
    s = (stderr_tail or "").lower()
    needles = (
        "connection reset",
        "timed out",
        "timeout",
        "ssl",
        "certificate",
        "handshake",
        "authentication failed",
        "permission denied",
        "could not connect",
        "no route to host",
        "name or service not known",
        "unknown host",
        "path does not specify a host system",
        "cannot find datacenter",
        "cannot locate host",
        "vddk",
        "libvixdisklib",
        "thumbprint",
    )
    return any(n in s for n in needles)


# NOTE: export functionality uses pure hyper2kvm architecture
# Legacy helper removed
# def _pretty_export_failure(rc: int, stderr_tail: str, argv: Sequence[str]) -> str:
#     tail = (stderr_tail or "").strip()
#     cmd = " ".join(shlex.quote(a) for a in argv)
#
#     if not tail:
#         return f"export failed (rc={rc}) with no captured stderr. cmd={cmd}"
#
#     return (
#         f"export failed (rc={rc}).\n"
#         f"--- export stderr (tail) ---\n{tail}\n"
#         f"--- command ---\n{cmd}"
#     )
#
#
# async def async_export_vm_verbose(self: VMwareClient, opt: ExportOptions) -> Path:
#     """
#     Drop-in alternative that never hides the real reason.
#     Use: await client.async_export_vm_verbose(opt)
#     """
#     if shutil.which("export-vm") is None:
#         raise VMwareError("export-vm not found in PATH. Install export tooling.")

#     if not self.si:
#         raise VMwareError("Not connected to vSphere; cannot export. Call connect() first.")
#
#     # If using VDDK with verification enabled, compute thumbprint automatically.
#     if opt.transport.strip().lower() == "vddk" and (not opt.vddk_thumbprint) and (not opt.no_verify):
#         self.logger.info("Computing TLS thumbprint (SHA1) for %s:%s ...", self.host, self.port)
#         tp = await asyncio.to_thread(self.compute_server_thumbprint_sha1, self.host, self.port, 10.0)
#         opt = ExportOptions(**{**opt.__dict__, "vddk_thumbprint": tp})
#
#     pwfile = self._write_password_file(opt.output_dir)
#     try:
#         argv = await asyncio.to_thread(self._build_export_cmd, opt, password_file=pwfile)
#         env = os.environ.copy()
#
#         rc, _out_tail, err_tail = await _run_logged_subprocess_with_tails(
#             self.logger,
#             argv,
#             env=env,
#             stderr_tail_lines=160,
#             stdout_tail_lines=60,
#         )
#
#         if rc != 0:
#             # Helpful "what exists?" context on failure (best-effort).
#             try:
#                 self.logger.error("Available datacenters: %s", self.list_datacenters(refresh=True))
#             except Exception:
#                 pass
#             try:
#                 self.logger.error("Available ESXi hosts: %s", self.list_host_names(refresh=True))
#             except Exception:
#                 pass
#
#             msg = _pretty_export_failure(rc, err_tail, argv)
#             if _is_transient_vpx_error(err_tail):
#                 msg += "\n(looks like a vpx/vddk connectivity/auth/path issue; stderr tail above is the clue)"
#             raise VMwareError(msg)
#
#         self.logger.info("export finished OK -> %s", opt.output_dir)
#         return opt.output_dir
#
#     finally:
#         try:
#             pwfile.unlink()
#         except FileNotFoundError:
#             pass
#         except Exception as e:
#             self.logger.warning("Failed to remove password file %s: %s", pwfile, e)
#
#
# # Monkey-patch add-only (keeps your existing API intact)
# VMwareClient.async_export_vm_verbose = async_export_vm_verbose  # type: ignore[attr-defined]


async def _pump_stream_chunked(  # pylint: disable=too-many-arguments
    # Each parameter configures independent pump behavior (stream, logger target, tail capture, chunk size).
    stream: asyncio.StreamReader | None,
    logger: logging.Logger,
    level: int,
    prefix: str,
    *,
    tail: _TailBuffer | None = None,
    chunk_size: int = 8192,
) -> None:
    """
    Robust pump that DOES NOT use readline().

    Fixes: asyncio.exceptions.LimitOverrunError:
      "Separator is not found, and chunk exceed the limit"
    which can happen with long lines without '\\n'.
    """
    if stream is None:
        return

    buf = bytearray()

    while True:
        data = await stream.read(chunk_size)
        if not data:
            break

        buf.extend(data)

        # Emit complete lines.
        while True:
            nl = buf.find(b"\n")
            if nl < 0:
                break
            raw_line = bytes(buf[:nl])
            del buf[: nl + 1]

            msg = _strip_ansi(_safe_decode(raw_line).rstrip())
            if not msg:
                continue
            if tail is not None:
                tail.add(msg)
            logger.log(level, "%s%s", prefix, msg)

    # Flush remaining partial line.
    if buf:
        msg = _strip_ansi(_safe_decode(bytes(buf)).rstrip())
        if msg:
            if tail is not None:
                tail.add(msg)
            logger.log(level, "%s%s", prefix, msg)


async def _run_logged_subprocess_chunked(
    logger: logging.Logger,
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> int:
    """Drop-in replacement for VMwareClient._run_logged_subprocess(), but safe."""
    logger.info("Running: %s", " ".join(shlex.quote(a) for a in argv))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    await asyncio.gather(
        _pump_stream_chunked(proc.stdout, logger, logging.INFO, "", tail=None),
        _pump_stream_chunked(proc.stderr, logger, logging.INFO, "", tail=None),
    )

    return int(await proc.wait())


async def _run_logged_subprocess_with_tails_chunked(
    logger: logging.Logger,
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    stderr_tail_lines: int = 160,
    stdout_tail_lines: int = 60,
) -> tuple[int, str, str]:
    """
    Safe replacement for _run_logged_subprocess_with_tails().
    Keeps the same signature/return value: (rc, stdout_tail, stderr_tail).
    """
    logger.info("Running: %s", " ".join(shlex.quote(a) for a in argv))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    out_tail = _TailBuffer(max_lines=stdout_tail_lines)
    err_tail = _TailBuffer(max_lines=stderr_tail_lines)

    await asyncio.gather(
        _pump_stream_chunked(proc.stdout, logger, logging.INFO, "", tail=out_tail),
        _pump_stream_chunked(proc.stderr, logger, logging.INFO, "", tail=err_tail),
    )

    rc = int(await proc.wait())
    return rc, out_tail.text(), err_tail.text()


async def _vmwareclient__run_logged_subprocess_safe(
    self: VMwareClient,
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> int:
    # Preserve existing logging format; do not log secrets.
    return await _run_logged_subprocess_chunked(self.logger, argv, env=env)


# Deliberate add-only monkey-patch of the client's subprocess runner from its own extensions module.
VMwareClient._run_logged_subprocess = (  # type: ignore[attr-defined]  # pylint: disable=protected-access
    _vmwareclient__run_logged_subprocess_safe
)

# Module-level tails helper for subprocess execution
_run_logged_subprocess_with_tails = _run_logged_subprocess_with_tails_chunked  # type: ignore[assignment]
