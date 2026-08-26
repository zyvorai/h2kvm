# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/transports/vddk_client.py
# pylint: disable=too-many-lines  # self-contained ctypes VDDK binding; splitting would separate tightly-coupled C API surface
"""
VDDK client for ESXi "download-only" pulls.

This module is intentionally *self-contained* and does NOT depend on pyvmomi.
It focuses on the data-plane: connect to ESXi via VMware VDDK (VixDiskLib),
open a VMDK, read sectors, and stream to a local file.

You can use this from vmware_client.py (pyvmomi control-plane) by:
  - resolving ESXi host + backing.fileName ("[datastore] path/to/disk.vmdk")
  - calling VDDKESXClient.download_vmdk(...)

Runtime requirements:
  - VMware VDDK installed/extracted locally (libvixDiskLib.so present)
  - VDDK dependencies available to dynamic loader (often via LD_LIBRARY_PATH)
  - Network access to ESXi on 443 and VDDK transport ports (NBD/NBDSSL) as needed

Caveats:
  - VDDK API is C; symbol availability can vary by VDDK version.
  - This module binds only the minimal symbols it uses.
  - VDDK is NOT thread-safe. Do NOT call VDDK functions from multiple threads.
  - For best reliability, open the *descriptor* VMDK (not -flat.vmdk).

Notes on historical crash fix (free(): invalid size / memory corruption):
  1) Proper structure alignment with _pack_ = 1
  2) Better library loading with dependency resolution
  3) Safer ConnectEx parameter handling
"""

from __future__ import annotations

import contextlib
import ctypes
import faulthandler
import hashlib
import logging
import os
import random
import signal
import socket
import ssl
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class VDDKError(RuntimeError):
    """Generic VDDK client error."""


class VDDKCancelled(VDDKError):
    """Raised when a caller cancels an in-progress download."""


_VIXDISKLIB_API_VERSION_MAJOR = 9
_VIXDISKLIB_API_VERSION_MINOR = 0

# Open flags (stable)
_VIXDISKLIB_FLAG_OPEN_READ_ONLY = 0x00000001

# VDDK types
_VixDiskLibConnection = ctypes.c_void_p
_VixDiskLibHandle = ctypes.c_void_p

_SECTOR_SIZE = 512

# Global list to keep callback references alive
_VDDK_CALLBACK_REFS: list[object] = []

# Enable faulthandler early for better crash diagnostics
faulthandler.enable()


# ctypes structures


class _VixDiskLibConnectParams(ctypes.Structure):  # pylint: disable=too-few-public-methods  # ctypes struct mirrors the VDDK C API; fields only, no methods
    """
    Minimal connect params struct.

    Important: Use _pack_ = 1 to match VDDK's internal structure exactly.
    Some VDDK versions require tight packing without padding.
    """

    _pack_ = 1
    _fields_ = [
        ("vmxSpec", ctypes.c_char_p),
        ("serverName", ctypes.c_char_p),
        ("thumbPrint", ctypes.c_char_p),
        ("userName", ctypes.c_char_p),
        ("password", ctypes.c_char_p),
        ("port", ctypes.c_uint32),
    ]


class _VixDiskLibInfo(ctypes.Structure):  # pylint: disable=too-few-public-methods  # ctypes struct mirrors the VDDK C API; fields only, no methods
    """
    VixDiskLibInfo from VDDK headers.

    We only rely on 'capacity' (in sectors), but keep the early fields correct.
    """

    _fields_ = [
        ("magic", ctypes.c_uint32),
        ("version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("capacity", ctypes.c_uint64),  # sectors
        # More fields exist (geometry, adapterType, etc.) but we stop here.
    ]


def _as_cstr(s: str | None) -> bytes | None:
    if s is None:
        return None
    s2 = str(s).strip()
    return s2.encode("utf-8") if s2 else None


def normalize_thumbprint(tp: str) -> str:
    """
    Normalize a SHA1 thumbprint to colon-separated lower-case bytes:
      "AABBCC.." or "aa:bb:cc" -> "aa:bb:cc:..."
    """
    raw = (tp or "").strip().replace(" ", "").replace(":", "").lower()
    if len(raw) != 40 or any(c not in "0123456789abcdef" for c in raw):
        raise VDDKError(f"Invalid thumbprint (expected SHA1 40 hex chars): {tp!r}")
    return ":".join(raw[i : i + 2] for i in range(0, 40, 2))


def compute_server_thumbprint_sha1(host: str, port: int = 443, timeout: float = 10.0) -> str:
    """
    Fetch the server certificate (DER) and return SHA1 thumbprint (colon-separated).

    SECURITY NOTE: This function intentionally disables TLS certificate verification
    because it's used specifically to FETCH the certificate for thumbprint extraction.
    This is a chicken-and-egg scenario: you need the cert to verify, but you're trying
    to get the cert to compute its thumbprint for later verification.

    This function should ONLY be used for thumbprint extraction, NOT for data transfer.
    The computed thumbprint should then be used for proper certificate pinning in
    subsequent connections.
    """
    # SECURITY: Disabled verification is intentional for certificate extraction only
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # Required to fetch cert without prior verification
    ctx.verify_mode = ssl.CERT_NONE  # Required to fetch cert without prior verification
    with (
        socket.create_connection((host, port), timeout=timeout) as sock,
        ctx.wrap_socket(sock, server_hostname=host) as ssock,
    ):
        der = ssock.getpeercert(binary_form=True)
    # SHA-1 here is the vSphere/VDDK thumbprint format, not used for security.
    sha1 = hashlib.sha1(der, usedforsecurity=False).hexdigest()
    return ":".join(sha1[i : i + 2] for i in range(0, 40, 2))


def _peek_tls_cert_sha1(host: str, port: int, timeout: float) -> tuple[str | None, str | None]:
    """
    Best-effort: fetch peer cert and return (sha1_thumbprint, subject_str).
    Returns (None, None) on failure.

    SECURITY NOTE: This function intentionally disables TLS certificate verification
    for certificate inspection purposes only. Do not use for data transfer.
    """
    try:
        # SECURITY: Disabled verification is intentional for certificate inspection only
        ctx = ssl.create_default_context()
        ctx.check_hostname = False  # Required to fetch cert for inspection
        ctx.verify_mode = ssl.CERT_NONE  # Required to fetch cert for inspection
        with (
            socket.create_connection((host, port), timeout=timeout) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as ssock,
        ):
            der = ssock.getpeercert(binary_form=True)
            info = ssock.getpeercert() or {}

        # SHA-1 here is the vSphere/VDDK thumbprint format, not used for security.
        sha1 = hashlib.sha1(der, usedforsecurity=False).hexdigest()
        tp = ":".join(sha1[i : i + 2] for i in range(0, 40, 2))
        subj = str(info.get("subject", "")) if info else ""
        return tp, subj
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort TLS peer-cert probe, must not raise
        return None, None


def _tcp_probe(host: str, port: int, timeout: float) -> tuple[bool, str]:
    """Best-effort TCP connect probe. Returns (ok, detail)."""
    try:
        t0 = time.time()
        with socket.create_connection((host, port), timeout=timeout):
            dt = max(0.0, time.time() - t0)
            return True, f"ok ({dt:.3f}s)"
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort TCP probe, must not raise
        return False, f"{type(e).__name__}: {e}"


def _resolve_host(host: str) -> tuple[bool, str]:
    """Best-effort DNS resolution. Returns (ok, detail string)."""
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = sorted({i[4][0] for i in infos})
        return True, ", ".join(addrs[:8]) + (" ..." if len(addrs) > 8 else "")
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort DNS resolution probe, must not raise
        return False, f"{type(e).__name__}: {e}"


def _atomic_write_replace(tmp_path: Path, final_path: Path) -> None:
    """Atomic-ish replace on POSIX."""
    os.replace(str(tmp_path), str(final_path))


def _fsync_dir(path: Path) -> None:
    """
    Best-effort fsync of a directory to make rename durable on POSIX.
    No-op if not supported.
    """
    try:
        fd = os.open(str(path), os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort dir fsync, must not abort the write
        pass


def _looks_like_datastore_path(p: str) -> bool:
    # Common form: "[datastore1] folder/disk.vmdk"
    s = (p or "").strip()
    return s.startswith("[") and "]" in s and s.lower().endswith(".vmdk")


def _is_flat_or_delta_vmdk(p: str) -> bool:
    s = (p or "").lower()
    return s.endswith(("-flat.vmdk", "-delta.vmdk", "-sesparse.vmdk"))


def _fmt_eta(seconds: float) -> str:
    try:
        s = int(max(0.0, seconds))
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort ETA formatting, must not raise
        return "?"
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


# Crash handler (for debugging memory corruption)


def _setup_crash_handler(logger: logging.Logger) -> None:
    """Setup comprehensive crash handlers for memory corruption debugging."""

    def sigsegv_handler(_signum, frame):
        logger.critical("=" * 80)
        logger.critical("SIGSEGV DETECTED - Memory Corruption in VDDK")
        logger.critical("=" * 80)

        logger.critical("\nStack trace at crash:")
        for filename, lineno, name, line in traceback.extract_stack(frame):
            logger.critical(" %s:%s in %s", filename, lineno, name)
            if line:
                logger.critical(" %s", line.strip())

        try:
            logger.critical("\nVDDK Connection state: initialized")
            logger.critical("LD_LIBRARY_PATH: %s", os.environ.get("LD_LIBRARY_PATH"))
            logger.critical("VDDK_HOME: %s", os.environ.get("VDDK_HOME"))
        except Exception:  # pylint: disable=broad-exception-caught  # crash-handler diagnostics must not raise from a signal handler
            pass

        logger.critical("\n" + "=" * 80)
        logger.critical("Attempting safe termination...")

        signal.signal(signal.SIGSEGV, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGSEGV)

    signal.signal(signal.SIGSEGV, sigsegv_handler)


# Dynamic loading & symbol binding


def _candidate_lib_names() -> tuple[str, ...]:
    return (
        "libvixDiskLib.so",
        "libvixDiskLib.so.9",
        "libvixDiskLib.so.7",
        "libvixDiskLib.so.6",
        "libvixDiskLib.so.5",
    )


def _load_vddk_cdll(
    vddk_libdir: Path | None,
    *,
    mutate_env: bool = True,  # pylint: disable=unused-argument  # kept for API compatibility; called with mutate_env=... elsewhere
) -> ctypes.CDLL:
    """
    Load libvixDiskLib.so. If vddk_libdir is provided, try it first.

    VDDK often requires LD_LIBRARY_PATH setup for its dependencies.
    This function sets VDDK_HOME and builds an LD_LIBRARY_PATH when vddk_libdir is provided.
    """
    # NOTE: mutate_env is intentionally kept for API compatibility.
    # Current behavior always mutates env when vddk_libdir is provided.
    if vddk_libdir:
        vddk_path = Path(vddk_libdir).expanduser().resolve()
        os.environ["VDDK_HOME"] = str(vddk_path)

        lib_paths = [
            str(vddk_path),
            str(vddk_path / "lib64"),
            str(vddk_path / "lib"),
            str(vddk_path / "bin"),
            "/usr/lib64",
            "/usr/lib",
            "/lib64",
            "/lib",
            os.environ.get("LD_LIBRARY_PATH", ""),
        ]

        new_ld_path = ":".join([p for p in lib_paths if p and os.path.exists(p.split(":")[0])])
        os.environ["LD_LIBRARY_PATH"] = new_ld_path

        logger = logging.getLogger(__name__)
        logger.debug("VDDK: Set LD_LIBRARY_PATH=%s", new_ld_path)
        logger.debug("VDDK: Set VDDK_HOME=%s", vddk_path)

    last_error: Exception | None = None

    if vddk_libdir:
        vddk_path = Path(vddk_libdir).expanduser().resolve()
        for n in _candidate_lib_names():
            cand = vddk_path / n
            if cand.exists():
                try:
                    logger = logging.getLogger(__name__)
                    logger.debug("VDDK: Trying explicit path: %s", cand)
                    return ctypes.CDLL(str(cand), mode=ctypes.RTLD_GLOBAL)
                except Exception as e:  # pylint: disable=broad-exception-caught  # try each candidate lib path in turn, must not abort the search
                    last_error = e
                    logger.debug("VDDK: Failed to load %s: %s", cand, e)

    for n in _candidate_lib_names():
        try:
            logger = logging.getLogger(__name__)
            logger.debug("VDDK: Trying system load: %s", n)
            return ctypes.CDLL(n, mode=ctypes.RTLD_GLOBAL)
        except Exception as e:  # pylint: disable=broad-exception-caught  # try each candidate lib name in turn, must not abort the search
            last_error = e

    raise VDDKError(
        "Failed to load VDDK library (libvixDiskLib.so).\n"
        "Ensure:\n"
        " 1. VDDK is installed at the path specified by vddk_libdir\n"
        " 2. All VDDK dependencies are available in LD_LIBRARY_PATH\n"
        " 3. You have proper permissions to load the library\n"
        f"Last error: {last_error!r}\n"
        f"LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH')}"
    )


def _bind_symbols(lib: ctypes.CDLL) -> None:
    """Bind minimal VDDK symbols used by this module."""
    try:
        lib.VixDiskLib_InitEx.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,  # logFunc
            ctypes.c_void_p,  # warnFunc
            ctypes.c_void_p,  # panicFunc
            ctypes.c_char_p,  # libDir
            ctypes.c_char_p,  # configFile
        ]
        lib.VixDiskLib_InitEx.restype = ctypes.c_int
    except AttributeError:
        lib.VixDiskLib_Init.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,  # logFunc
            ctypes.c_void_p,  # warnFunc
            ctypes.c_void_p,  # panicFunc
        ]
        lib.VixDiskLib_Init.restype = ctypes.c_int

    lib.VixDiskLib_Exit.argtypes = []
    lib.VixDiskLib_Exit.restype = None

    try:
        lib.VixDiskLib_ConnectEx.argtypes = [
            ctypes.POINTER(_VixDiskLibConnectParams),
            ctypes.c_char_p,  # identity
            ctypes.c_char_p,  # snapshotRef
            ctypes.c_char_p,  # transportModes
            ctypes.POINTER(_VixDiskLibConnection),
        ]
        lib.VixDiskLib_ConnectEx.restype = ctypes.c_int
    except AttributeError:
        lib.VixDiskLib_Connect.argtypes = [
            ctypes.POINTER(_VixDiskLibConnectParams),
            ctypes.POINTER(_VixDiskLibConnection),
        ]
        lib.VixDiskLib_Connect.restype = ctypes.c_int

    lib.VixDiskLib_Disconnect.argtypes = [_VixDiskLibConnection]
    lib.VixDiskLib_Disconnect.restype = None

    lib.VixDiskLib_Open.argtypes = [
        _VixDiskLibConnection,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.POINTER(_VixDiskLibHandle),
    ]
    lib.VixDiskLib_Open.restype = ctypes.c_int

    lib.VixDiskLib_Close.argtypes = [_VixDiskLibHandle]
    lib.VixDiskLib_Close.restype = None

    lib.VixDiskLib_GetInfo.argtypes = [
        _VixDiskLibHandle,
        ctypes.POINTER(ctypes.POINTER(_VixDiskLibInfo)),
    ]
    lib.VixDiskLib_GetInfo.restype = ctypes.c_int

    lib.VixDiskLib_FreeInfo.argtypes = [ctypes.c_void_p]
    lib.VixDiskLib_FreeInfo.restype = None

    lib.VixDiskLib_Read.argtypes = [
        _VixDiskLibHandle,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_void_p,  # uint8*
    ]
    lib.VixDiskLib_Read.restype = ctypes.c_int

    lib.VixDiskLib_GetErrorText.argtypes = [ctypes.c_int, ctypes.c_char_p]
    lib.VixDiskLib_GetErrorText.restype = ctypes.c_char_p

    lib.VixDiskLib_FreeErrorText.argtypes = [ctypes.c_void_p]
    lib.VixDiskLib_FreeErrorText.restype = None


def _err_text(lib: ctypes.CDLL, rc: int) -> str:
    """Best-effort conversion of VDDK error codes to text."""
    try:
        # Try to get error text with buffer first (safer)
        buf = ctypes.create_string_buffer(256)
        p = lib.VixDiskLib_GetErrorText(int(rc), buf)

        if p:
            # Some versions return pointer
            raw = ctypes.cast(p, ctypes.c_char_p).value
            msg = raw.decode("utf-8", errors="replace") if raw else f"VDDK rc={rc}"
            with contextlib.suppress(Exception):
                lib.VixDiskLib_FreeErrorText(p)
            return msg
        if buf.value:
            # Buffer was filled directly
            return buf.value.decode("utf-8", errors="replace")
        return f"VDDK rc={rc}"
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort VDDK error-text decode, fall back to rc code
        return f"VDDK rc={rc}"


def _is_likely_transient_error(msg: str) -> bool:
    m = (msg or "").lower()

    hard = (
        "permission",
        "access denied",
        "no such file",
        "not found",
        "invalid",
        "bad parameter",
        "unsupported",
        "authentication",
        "auth failed",
        "thumbprint",
        "certificate",
    )
    if any(x in m for x in hard):
        return False

    transient = (
        "timeout",
        "timed out",
        "connection",
        "connect",
        "network",
        "transport",
        "reset",
        "broken pipe",
        "eof",
        "unavailable",
        "try again",
        "tempor",
    )
    if any(x in m for x in transient):
        return True

    return True


# VDDK logging callbacks

_VDDK_LOG_CB_SIMPLE = ctypes.CFUNCTYPE(None, ctypes.c_char_p)

# Mutable global state for ctypes callback lifetime, not true constants.
# pylint: disable=invalid-name
_g_vddk_log_cb: _VDDK_LOG_CB_SIMPLE | None = None
_g_vddk_warn_cb: _VDDK_LOG_CB_SIMPLE | None = None
_g_vddk_panic_cb: _VDDK_LOG_CB_SIMPLE | None = None
# pylint: enable=invalid-name


def _mk_vddk_log_cb_simple(logger: logging.Logger, level: str) -> _VDDK_LOG_CB_SIMPLE:
    """Simple callback that attempts to decode a char* message safely."""

    def _cb(msg_p: ctypes.c_char_p) -> None:
        try:
            if msg_p:
                msg_bytes = msg_p.value
                msg = msg_bytes.decode("utf-8", "replace").rstrip() if msg_bytes else "<empty message>"
            else:
                msg = "<NULL pointer>"

            if level == "debug":
                logger.debug("VDDK: %s", msg)
            elif level == "warning":
                logger.warning("VDDK: %s", msg)
            else:
                logger.error("VDDK: %s", msg)
        except Exception as e:  # pylint: disable=broad-exception-caught  # ctypes callback must never propagate into VDDK C code
            with contextlib.suppress(Exception):
                logger.exception("VDDK callback error: %s", e)

    cb = _VDDK_LOG_CB_SIMPLE(_cb)
    _VDDK_CALLBACK_REFS.append(cb)
    return cb


def _mk_dummy_callback() -> _VDDK_LOG_CB_SIMPLE:
    """Create a dummy callback that does nothing."""

    def _cb(_: ctypes.c_char_p) -> None:
        return

    cb = _VDDK_LOG_CB_SIMPLE(_cb)
    _VDDK_CALLBACK_REFS.append(cb)
    return cb


# Global init (InitEx once) - SINGLE THREAD ONLY

_vddk_inited = False  # pylint: disable=invalid-name  # mutable global init-guard flag, not a true constant


def vddk_init_once(logger: logging.Logger, lib: ctypes.CDLL, *, vddk_libdir: Path | None) -> None:
    """
    Initialize VDDK once per process.

    WARNING: VDDK is NOT thread-safe. Do NOT call this from multiple threads.
    """
    # Module-level so ctypes callbacks/init-guard stay alive and avoid re-init.
    global _vddk_inited, _g_vddk_log_cb, _g_vddk_warn_cb, _g_vddk_panic_cb  # pylint: disable=global-statement

    if _vddk_inited:
        return

    libdir_c = _as_cstr(str(Path(vddk_libdir).expanduser().resolve())) if vddk_libdir else None

    _setup_crash_handler(logger)

    api_versions = [
        (_VIXDISKLIB_API_VERSION_MAJOR, _VIXDISKLIB_API_VERSION_MINOR),
        (7, 0),
        (6, 7),
        (6, 5),
    ]

    for major, minor in api_versions:
        try:
            logger.debug("VDDK: Trying InitEx API %d.%d...", major, minor)
            rc = lib.VixDiskLib_InitEx(
                major,
                minor,
                None,
                None,
                None,
                libdir_c,
                None,
            )
            if rc == 0:
                logger.debug("VDDK: InitEx OK (API %d.%d, no callbacks)", major, minor)
                _vddk_inited = True
                return
        except AttributeError:
            try:
                logger.debug("VDDK: Trying Init API %d.%d...", major, minor)
                rc = lib.VixDiskLib_Init(
                    major,
                    minor,
                    None,
                    None,
                    None,
                )
                if rc == 0:
                    logger.debug("VDDK: Init OK (API %d.%d, no callbacks)", major, minor)
                    _vddk_inited = True
                    return
            except AttributeError:
                continue

    logger.debug("VDDK: Trying with dummy callbacks...")
    _g_vddk_log_cb = _mk_dummy_callback()
    _g_vddk_warn_cb = _mk_dummy_callback()
    _g_vddk_panic_cb = _mk_dummy_callback()

    rc = lib.VixDiskLib_InitEx(
        _VIXDISKLIB_API_VERSION_MAJOR,
        _VIXDISKLIB_API_VERSION_MINOR,
        _g_vddk_log_cb,
        _g_vddk_warn_cb,
        _g_vddk_panic_cb,
        libdir_c,
        None,
    )
    if rc != 0:
        raise VDDKError(
            "VixDiskLib_InitEx failed with all API versions.\n"
            "Possible causes:\n"
            "  - VDDK library version mismatch (try VDDK 7.0 or 8.0)\n"
            "  - Missing VDDK dependencies (check ldd on libvixDiskLib.so)\n"
            "  - Incorrect VDDK installation path\n"
            f"  VDDK_HOME={os.environ.get('VDDK_HOME', 'not set')}\n"
            f"  LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH', 'not set')}"
        )

    logger.debug("VDDK: InitEx OK (with dummy callbacks)")
    _vddk_inited = True


def vddk_cleanup() -> None:
    """Clean up VDDK resources."""
    global _vddk_inited  # pylint: disable=global-statement  # init-guard must be module-level so future calls see the reset state
    if _vddk_inited:
        try:
            # Try to load the library to call Exit
            lib = None
            for n in _candidate_lib_names():
                try:
                    lib = ctypes.CDLL(n, mode=ctypes.RTLD_GLOBAL)
                    break
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort library load during cleanup, must not abort Exit()
                    continue

            if lib and hasattr(lib, "VixDiskLib_Exit"):
                lib.VixDiskLib_Exit()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort VDDK cleanup, must not raise
            pass
        finally:
            _VDDK_CALLBACK_REFS.clear()
            _vddk_inited = False


# Public API

ProgressFn = Callable[[int, int, float], None]
CancelFn = Callable[[], bool]


@dataclass(frozen=True)
class VDDKConnectionSpec:  # pylint: disable=too-many-instance-attributes  # models the full VDDK ESXi connection parameter set
    """Connection parameters for a VDDK ESXi session (host/credentials, transport, and diagnostics)."""

    host: str
    user: str
    password: str
    port: int = 443
    thumbprint: str | None = None
    insecure: bool = False
    transport_modes: str | None = None  # e.g. "nbdssl:nbd"
    vddk_libdir: Path | None = None
    tls_thumbprint_timeout: float = 10.0
    mutate_ld_library_path: bool = True

    # Debug / diagnostics
    debug_preflight: bool = True
    preflight_timeout: float = 5.0


class VDDKESXClient:
    """
    Minimal ESXi VDDK reader.

    WARNING: This class is NOT thread-safe. VDDK API is single-threaded only.

    Lifecycle:
      - connect()
      - download_vmdk(...)
      - disconnect()
    """

    def __init__(self, logger: logging.Logger, spec: VDDKConnectionSpec):
        self.logger = logger
        self.spec = spec

        self._lib: ctypes.CDLL | None = None
        self._conn: _VixDiskLibConnection = _VixDiskLibConnection()
        self._connect_strings: dict[str, bytes | None] = {}

    def __enter__(self) -> VDDKESXClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    def _ensure_loaded(self) -> None:
        if self._lib is not None:
            return

        s = self.spec
        if not (s.host and s.user and s.password):
            missing = []
            if not s.host:
                missing.append("host (ESXi hostname or IP)")
            if not s.user:
                missing.append("user (ESXi username, typically 'root')")
            if not s.password:
                missing.append("password (ESXi password)")
            raise VDDKError(
                f"Missing VDDK connection details: {', '.join(missing)}.\n"
                "These are the ESXi host credentials (not vCenter). "
                "Set them via --vddk-host, --vddk-user, --vddk-password or "
                "corresponding environment variables."
            )

        self.logger.debug(
            "VDDK: loading lib (vddk_libdir=%r mutate_ld_library_path=%s LD_LIBRARY_PATH=%r)",
            str(s.vddk_libdir) if s.vddk_libdir else None,
            bool(s.mutate_ld_library_path),
            os.environ.get("LD_LIBRARY_PATH", ""),
        )

        lib = _load_vddk_cdll(s.vddk_libdir, mutate_env=bool(s.mutate_ld_library_path))
        self.logger.debug("VDDK: CDLL loaded: %r", getattr(lib, "_name", lib))
        _bind_symbols(lib)
        vddk_init_once(self.logger, lib, vddk_libdir=s.vddk_libdir)

        self._lib = lib

    def _preflight_debug(self) -> None:
        """Extra diagnostics before ConnectEx. Never raises; logs only."""
        s = self.spec
        if not s.debug_preflight:
            return

        self.logger.debug(
            "VDDK: preflight host=%r port=%d user=%r insecure=%s transports=%r",
            s.host,
            s.port,
            s.user,
            s.insecure,
            s.transport_modes,
        )

        ok_res, res = _resolve_host(s.host)
        if ok_res:
            self.logger.debug("VDDK: DNS resolve %s -> %s", s.host, res)
        else:
            self.logger.error("VDDK: DNS resolve failed for %s: %s", s.host, res)

        ok_tcp, tcp = _tcp_probe(s.host, int(s.port), float(s.preflight_timeout))
        if ok_tcp:
            self.logger.debug("VDDK: TCP connect %s:%d -> %s", s.host, s.port, tcp)
        else:
            self.logger.error("VDDK: TCP connect failed %s:%d -> %s", s.host, s.port, tcp)

        # Only check TLS if not insecure
        if not s.insecure:
            tp, subj = _peek_tls_cert_sha1(s.host, int(s.port), float(s.preflight_timeout))
            if tp:
                self.logger.debug("VDDK: TLS peer cert sha1=%s subject=%s", tp, subj)
            else:
                self.logger.debug("VDDK: TLS peer cert fetch failed")

        if s.thumbprint:
            try:
                self.logger.debug(
                    "VDDK: thumbprint raw=%r normalized=%r",
                    s.thumbprint,
                    normalize_thumbprint(s.thumbprint),
                )
            except Exception as e:  # pylint: disable=broad-exception-caught  # preflight diagnostics must never raise
                self.logger.exception("VDDK: thumbprint invalid: %r (%s)", s.thumbprint, e)

    def connect(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # single-pass ConnectEx setup covers preflight, params, and error-hinting
        self,
    ) -> None:
        """Connect to ESXi host using VDDK."""
        self._ensure_loaded()
        if self._lib is None:
            raise VDDKError(
                "VDDK library not loaded. Download and install VMware VDDK from "
                "https://developer.vmware.com/web/sdk/8.0/vddk - See docs for installation instructions."
            )

        s = self.spec
        self._preflight_debug()

        # FIX: Use correct transport mode based on insecure flag
        transport = "nbd" if s.insecure else "nbdssl"  # Plain NBD without SSL, or NBD with SSL

        # Allow override from spec
        if s.transport_modes:
            transport = s.transport_modes

        self.logger.debug("VDDK: Using transport: %s (insecure=%s)", transport, s.insecure)

        # Encode strings and keep references
        server_bytes = s.host.encode("utf-8")
        user_bytes = s.user.encode("utf-8")
        password_bytes = s.password.encode("utf-8")
        transport_bytes = transport.encode("utf-8")

        # Store thumbprint if provided and not insecure
        thumbprint_bytes = None
        if not s.insecure and s.thumbprint:
            try:
                thumbprint_bytes = normalize_thumbprint(s.thumbprint).encode("utf-8")
            except Exception as e:  # pylint: disable=broad-exception-caught  # thumbprint normalization failure just disables TLS verification, logged as a warning
                self.logger.warning("VDDK: Invalid thumbprint, will not verify TLS: %s", e)

        # Keep references to prevent garbage collection
        self._connect_strings = {
            "server": server_bytes,
            "user": user_bytes,
            "password": password_bytes,
            "transport": transport_bytes,
            "thumbprint": thumbprint_bytes,
        }

        # Initialize connection parameters
        params = _VixDiskLibConnectParams()
        # Zero out the structure
        ctypes.memset(ctypes.byref(params), 0, ctypes.sizeof(params))

        # Set fields. Names must match _VixDiskLibConnectParams._fields_ (the VDDK C API) exactly.
        # pylint: disable=invalid-name,attribute-defined-outside-init
        params.serverName = ctypes.c_char_p(server_bytes)
        params.userName = ctypes.c_char_p(user_bytes)
        params.password = ctypes.c_char_p(password_bytes)
        params.port = ctypes.c_uint32(int(s.port))

        # These should be NULL/NONE for ESXi connections
        params.vmxSpec = None

        # Set thumbprint if provided and not insecure
        if thumbprint_bytes and not s.insecure:
            params.thumbPrint = ctypes.c_char_p(thumbprint_bytes)
        else:
            params.thumbPrint = None
        # pylint: enable=invalid-name,attribute-defined-outside-init

        conn = _VixDiskLibConnection()
        t0 = time.time()

        self.logger.debug(
            "VDDK: ConnectEx params: serverName=%r port=%d user=%r transport=%r thumbPrint=%r",
            s.host,
            int(s.port),
            s.user,
            transport,
            "****" if thumbprint_bytes else None,
        )

        try:
            if hasattr(self._lib, "VixDiskLib_ConnectEx"):
                rc = self._lib.VixDiskLib_ConnectEx(
                    ctypes.byref(params),
                    None,  # identity
                    None,  # snapshotRef
                    ctypes.c_char_p(transport_bytes),
                    ctypes.byref(conn),
                )
            else:
                rc = self._lib.VixDiskLib_Connect(
                    ctypes.byref(params),
                    ctypes.byref(conn),
                )
        except Exception as e:  # pylint: disable=broad-exception-caught  # ctypes call into VDDK C library can fail in many ways
            dt = max(0.0, time.time() - t0)
            self.logger.exception("VDDK: Connect EXCEPTION dt=%.3fs: %s", dt, e)
            raise VDDKError(f"VixDiskLib_Connect raised exception: {e}") from e

        dt = max(0.0, time.time() - t0)

        if rc != 0:
            msg = _err_text(self._lib, rc)
            self.logger.error(
                "VDDK: Connect FAILED rc=%d dt=%.3fs msg=%s (host=%s port=%d transport=%s insecure=%s user=%s)",
                int(rc),
                dt,
                msg,
                s.host,
                int(s.port),
                transport,
                bool(s.insecure),
                s.user,
            )
            hint = ""
            ml = (msg or "").lower()
            if "authentication" in ml or "permission" in ml or "access denied" in ml:
                hint = (
                    "\n\nAuthentication failed. Verify ESXi credentials:\n"
                    "  - Username and password are for the ESXi host (not vCenter)\n"
                    "  - The user has sufficient permissions for disk access"
                )
            elif "thumbprint" in ml or "certificate" in ml:
                hint = (
                    "\n\nTLS certificate verification failed. Either:\n"
                    "  - Provide the correct thumbprint via --vddk-thumbprint\n"
                    "  - Use --insecure to skip certificate verification"
                )
            elif "connect" in ml or "network" in ml or "timeout" in ml:
                hint = (
                    "\n\nNetwork connection failed. Check:\n"
                    "  - ESXi host is reachable on port 443\n"
                    "  - Firewall rules allow NBD/NBDSSL traffic\n"
                    "  - DNS resolves the ESXi hostname correctly"
                )
            raise VDDKError(f"VixDiskLib_Connect failed: {msg}{hint}")

        self._conn = conn
        self.logger.info(
            "VDDK: connected to ESXi %s:%d (transport=%s, insecure=%s) (dt=%.3fs)",
            s.host,
            s.port,
            transport,
            s.insecure,
            dt,
        )

    def disconnect(self) -> None:
        """Disconnect from ESXi host."""
        if self._lib is None:
            return

        try:
            if self._conn:
                self.logger.debug("VDDK: disconnecting")
                self._lib.VixDiskLib_Disconnect(self._conn)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort disconnect, must not mask cleanup
            self.logger.debug("VDDK: disconnect error ignored: %s", e)
        finally:
            self._conn = _VixDiskLibConnection()
            self._connect_strings.clear()

    def _require_connected(self) -> None:
        if self._lib is None:
            raise VDDKError("VDDK library not loaded")
        if not self._conn:
            raise VDDKError("VDDK not connected (call connect())")

    def _open_ro(self, remote_vmdk: str) -> _VixDiskLibHandle:
        self._require_connected()
        if self._lib is None:
            raise VDDKError(
                "VDDK library not loaded. Download and install VMware VDDK from "
                "https://developer.vmware.com/web/sdk/8.0/vddk - See docs for installation instructions."
            )

        self.logger.debug("VDDK: Open RO %r", remote_vmdk)

        h = _VixDiskLibHandle()
        rc = self._lib.VixDiskLib_Open(
            self._conn,
            _as_cstr(remote_vmdk),
            ctypes.c_uint32(_VIXDISKLIB_FLAG_OPEN_READ_ONLY),
            ctypes.byref(h),
        )
        if rc != 0:
            msg = _err_text(self._lib, rc)
            self.logger.error("VDDK: Open FAILED rc=%d msg=%s path=%r", int(rc), msg, remote_vmdk)
            hint = ""
            ml = (msg or "").lower()
            if "unknown error" in ml or rc in (1, 2, 13):
                hint = (
                    " This may be caused by a disk in 'independent' mode which "
                    "VDDK >= 7.0 cannot open. Change the disk mode to 'dependent' "
                    "in vSphere, or use govc/OVF export instead."
                )
            raise VDDKError(f"VixDiskLib_Open failed for {remote_vmdk!r}: {msg}.{hint}")

        self.logger.debug("VDDK: Open OK handle=%r", h)
        return h

    def _close(self, h: _VixDiskLibHandle) -> None:
        if self._lib is None:
            raise VDDKError(
                "VDDK library not loaded. Download and install VMware VDDK from "
                "https://developer.vmware.com/web/sdk/8.0/vddk - See docs for installation instructions."
            )
        with contextlib.suppress(Exception):
            self._lib.VixDiskLib_Close(h)

    def _capacity_sectors(self, h: _VixDiskLibHandle) -> int:
        self._require_connected()
        if self._lib is None:
            raise VDDKError(
                "VDDK library not loaded. Download and install VMware VDDK from "
                "https://developer.vmware.com/web/sdk/8.0/vddk - See docs for installation instructions."
            )

        self.logger.debug("VDDK: GetInfo(handle=%r)", h)

        info_p = ctypes.POINTER(_VixDiskLibInfo)()
        rc = self._lib.VixDiskLib_GetInfo(h, ctypes.byref(info_p))
        if rc != 0:
            msg = _err_text(self._lib, rc)
            self.logger.error("VDDK: GetInfo FAILED rc=%d msg=%s", int(rc), msg)
            raise VDDKError(f"VixDiskLib_GetInfo failed: {msg}")

        try:
            cap = int(info_p.contents.capacity)
            self.logger.debug(
                "VDDK: GetInfo OK capacity_sectors=%d (%.2f GiB)",
                cap,
                (cap * _SECTOR_SIZE) / (1024**3),
            )
            return cap
        finally:
            with contextlib.suppress(Exception):
                self._lib.VixDiskLib_FreeInfo(info_p)

    def _read_with_retry(  # pylint: disable=too-many-arguments  # sector read + full retry/backoff/cancel policy in one call
        self,
        h: _VixDiskLibHandle,
        start_sector: int,
        num_sectors: int,
        buf_p: ctypes.c_void_p,
        *,
        max_retries: int,
        base_backoff_s: float,
        max_backoff_s: float,
        jitter_s: float,
        cancel: CancelFn | None,
    ) -> None:
        """Read sectors with retry/backoff on likely transient errors."""
        if self._lib is None:
            raise VDDKError(
                "VDDK library not loaded. Download and install VMware VDDK from "
                "https://developer.vmware.com/web/sdk/8.0/vddk - See docs for installation instructions."
            )

        attempt = 0
        while True:
            if cancel and cancel():
                raise VDDKCancelled("Download cancelled")

            rc = self._lib.VixDiskLib_Read(
                h,
                ctypes.c_uint64(int(start_sector)),
                ctypes.c_uint64(int(num_sectors)),
                buf_p,
            )
            if rc == 0:
                return

            msg = _err_text(self._lib, rc)
            transient = _is_likely_transient_error(msg)

            attempt += 1
            if (not transient) or attempt > max_retries:
                raise VDDKError(
                    f"VixDiskLib_Read failed at sector={start_sector} count={num_sectors} "
                    f"(attempt={attempt}/{max_retries}, transient={transient}): {msg}"
                )

            backoff = min(max_backoff_s, base_backoff_s * (2 ** (attempt - 1)))
            backoff += random.uniform(0.0, max(0.0, jitter_s))
            self.logger.warning(
                "VDDK: transient read error at sector=%d count=%d: %s (retry %d/%d in %.2fs)",
                start_sector,
                num_sectors,
                msg,
                attempt,
                max_retries,
                backoff,
            )
            time.sleep(backoff)

    def download_vmdk(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements  # top-level streaming download covers resume, retry, progress, and verification
        self,
        remote_vmdk: str,
        local_path: Path,
        *,
        sectors_per_read: int = 2048,  # 1 MiB (2048 * 512)
        progress: ProgressFn | None = None,
        progress_interval_s: float = 0.5,
        log_every_bytes: int = 256 * 1024 * 1024,
        resume: bool = True,
        durable: bool = False,
        allow_flat: bool = False,
        cancel: CancelFn | None = None,
        max_read_retries: int = 6,
        base_backoff_s: float = 0.25,
        max_backoff_s: float = 8.0,
        jitter_s: float = 0.25,
        verify_size: bool = True,
        compute_sha256: bool = False,
    ) -> Path:
        """
        Stream a remote VMDK into a local file by reading sectors.

        WARNING: VDDK is NOT thread-safe. Do NOT call this from multiple threads.

        remote_vmdk should typically be the descriptor:
          "[datastore] vm/vm.vmdk"

        local_path is written atomically: <name>.part then rename.
        """
        self._require_connected()
        if self._lib is None:
            raise VDDKError(
                "VDDK library not loaded. Download and install VMware VDDK from "
                "https://developer.vmware.com/web/sdk/8.0/vddk - See docs for installation instructions."
            )

        remote_vmdk = (remote_vmdk or "").strip()
        if not remote_vmdk:
            raise VDDKError(
                "remote_vmdk path is empty. Provide the datastore path in the format:\n"
                '  "[datastore1] vm-folder/vm-disk.vmdk"\n'
                "You can find this path in vSphere under VM Settings > Hard Disk > Disk File."
            )

        if not _looks_like_datastore_path(remote_vmdk):
            self.logger.warning("VDDK: remote path doesn't look like datastore form: %r", remote_vmdk)

        if _is_flat_or_delta_vmdk(remote_vmdk) and not allow_flat:
            raise VDDKError(
                f"Refusing to open non-descriptor VMDK {remote_vmdk!r}. "
                "Pass the descriptor .vmdk (not -flat/-delta) or set allow_flat=True."
            )

        local_path = Path(local_path).expanduser().resolve()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_suffix(local_path.suffix + ".part")

        h: _VixDiskLibHandle | None = None
        sha256 = hashlib.sha256() if compute_sha256 else None

        try:
            h = self._open_ro(remote_vmdk)

            cap_sectors = self._capacity_sectors(h)
            total_bytes = cap_sectors * _SECTOR_SIZE
            if cap_sectors <= 0:
                raise VDDKError(f"Invalid capacity from VDDK GetInfo: sectors={cap_sectors}")

            spr = max(1, int(sectors_per_read))
            buf = (ctypes.c_ubyte * (spr * _SECTOR_SIZE))()
            buf_p = ctypes.cast(buf, ctypes.c_void_p)

            done = 0
            sector = 0
            mode = "wb"

            if resume and tmp.exists():
                st = tmp.stat()
                if st.st_size > 0 and st.st_size % _SECTOR_SIZE == 0:
                    done = int(st.st_size)
                    sector = done // _SECTOR_SIZE
                    if sector > cap_sectors:
                        self.logger.warning("VDDK: existing .part > remote capacity; restarting: %s", tmp)
                        done = 0
                        sector = 0
                        mode = "wb"
                    else:
                        mode = "r+b"
                        self.logger.info(
                            "VDDK: resuming from %s (%.2f GiB, sector=%d/%d)",
                            tmp,
                            done / (1024**3),
                            sector,
                            cap_sectors,
                        )
                else:
                    self.logger.warning("VDDK: existing .part is not sector-aligned; restarting: %s", tmp)
                    with contextlib.suppress(Exception):
                        tmp.unlink()
                    done = 0
                    sector = 0
                    mode = "wb"

            self.logger.info(
                "VDDK: download start: %s -> %s (sectors=%d, %.2f GiB)%s",
                remote_vmdk,
                local_path,
                cap_sectors,
                total_bytes / (1024**3),
                " [resume]" if sector else "",
            )

            start = time.time()
            last_log = done
            last_progress_ts = 0.0

            win_bytes = done
            win_ts = time.time()

            with open(tmp, mode) as f:
                if mode == "r+b":
                    f.seek(done, os.SEEK_SET)

                while sector < cap_sectors:
                    if cancel and cancel():
                        raise VDDKCancelled("Download cancelled")

                    n = min(spr, cap_sectors - sector)
                    chunk_bytes = int(n) * _SECTOR_SIZE

                    self._read_with_retry(
                        h,
                        start_sector=int(sector),
                        num_sectors=int(n),
                        buf_p=buf_p,
                        max_retries=int(max_read_retries),
                        base_backoff_s=float(base_backoff_s),
                        max_backoff_s=float(max_backoff_s),
                        jitter_s=float(jitter_s),
                        cancel=cancel,
                    )

                    mv = memoryview(buf)[:chunk_bytes]
                    f.write(mv)
                    if sha256 is not None:
                        sha256.update(mv)

                    sector += int(n)
                    done += chunk_bytes

                    if progress:
                        now = time.time()
                        if (now - last_progress_ts) >= max(
                            0.05, float(progress_interval_s)
                        ) or done == total_bytes:
                            last_progress_ts = now
                            pct = (done / total_bytes * 100.0) if total_bytes else 0.0
                            progress(done, total_bytes, pct)

                    if log_every_bytes and (done - last_log) >= int(log_every_bytes):
                        last_log = done

                        now = time.time()
                        w_elapsed = max(0.001, now - win_ts)
                        w_bytes = max(0, done - win_bytes)
                        if w_elapsed >= 1.0:
                            win_ts = now
                            win_bytes = done
                        mib_s = (w_bytes / (1024**2)) / w_elapsed if w_elapsed else 0.0

                        remain = max(0, total_bytes - done)
                        eta_s = remain / (mib_s * (1024**2)) if mib_s > 0 else 0.0

                        self.logger.info(
                            "VDDK: progress %.1f%% (%.1f/%.1f MiB) speed=%.1f MiB/s eta=%s",
                            (done / total_bytes * 100.0) if total_bytes else 0.0,
                            done / (1024**2),
                            total_bytes / (1024**2),
                            mib_s,
                            _fmt_eta(eta_s),
                        )

                if durable:
                    try:
                        f.flush()
                        os.fsync(f.fileno())
                    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fsync, logged and ignored
                        self.logger.warning("VDDK: fsync failed (ignored): %s", e)

            if verify_size:
                try:
                    sz = tmp.stat().st_size
                    if sz != total_bytes:
                        raise VDDKError(
                            f"Downloaded size mismatch for {tmp}: got={sz} expected={total_bytes}"
                        )
                except FileNotFoundError as e:
                    raise VDDKError(f"Temporary file missing after write: {tmp}") from e

            _atomic_write_replace(tmp, local_path)

            if durable:
                _fsync_dir(local_path.parent)

            if verify_size:
                try:
                    sz2 = local_path.stat().st_size
                    if sz2 != total_bytes:
                        raise VDDKError(
                            f"Final size mismatch for {local_path}: got={sz2} expected={total_bytes}"
                        )
                except FileNotFoundError as e:
                    raise VDDKError(f"Final file missing after rename: {local_path}") from e

            elapsed = max(0.0, time.time() - start)
            mib_s_total = (done / (1024**2)) / elapsed if elapsed > 0 else 0.0

            if sha256 is not None:
                self.logger.info("VDDK: sha256 %s %s", sha256.hexdigest(), local_path)

            self.logger.info(
                "VDDK: download done: %s (%.2f GiB, %.1f MiB/s)",
                local_path,
                done / (1024**3),
                mib_s_total,
            )
            return local_path

        except VDDKCancelled:
            self.logger.warning("VDDK: download cancelled; partial kept at %s", tmp)
            raise
        finally:
            if h:
                self._close(h)
