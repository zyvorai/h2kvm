# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/registry/encoding.py
"""
Low-level registry encoding and hivex operations.

Provides:
- Guest file I/O helpers
- Hivex node normalization
- Registry value encoding/decoding (REG_SZ, REG_DWORD, etc.)
- Hivex lifecycle management (open/close/commit)
- Driver value normalization
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from .io import _is_probably_regf

# pylint: disable=duplicate-code
# reason: shared optional-dependency import boilerplate (guestfs/hivex),
# mirrored in registry/system.py -- kept per-module so each registry fixer
# stays independently importable.
if TYPE_CHECKING:
    import logging

    import guestfs  # type: ignore
else:
    try:
        import guestfs  # type: ignore
    except ImportError:
        guestfs = None  # type: ignore

try:
    import hivex  # type: ignore
except ImportError:
    hivex = None  # type: ignore
# pylint: enable=duplicate-code

# Guest file helpers


def _mkdir_p_guest(logger: logging.Logger, g: guestfs.GuestFS, path: str) -> None:
    """Create directory in guest filesystem (mkdir -p)."""
    # best-effort guest dir probing; guestfs raises backend-specific exceptions
    try:
        if g.is_dir(path):
            return
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # best-effort mkdir -p; falls through to per-component creation on any failure
    try:
        g.mkdir_p(path)
        logger.debug("Created guest dir: %s", path)
        return
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    cur = ""
    for comp in path.strip("/").split("/"):
        cur = "/" + comp if not cur else cur.rstrip("/") + "/" + comp
        # best-effort per-component mkdir; guestfs raises backend-specific exceptions
        try:
            if not g.is_dir(cur):
                g.mkdir(cur)
        except Exception:  # pylint: disable=broad-exception-caught
            pass


def _upload_bytes(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    guest_path: str,
    data: bytes,
    *,
    results: dict[str, Any] | None = None,
) -> None:
    """
    Write bytes to a guest file using a local temp file + upload.
    Adds sha256 + size into results["uploaded_files"] if provided.
    """
    parent = str(Path(guest_path).parent).replace("\\", "/")
    _mkdir_p_guest(logger, g, parent)

    sha = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory() as td:
        lp = Path(td) / Path(guest_path).name
        lp.write_bytes(data)
        g.upload(str(lp), guest_path)

    # best-effort size lookup; guestfs raises backend-specific exceptions, fall back to len(data)
    try:
        st = g.statns(guest_path)
        sz = int(getattr(st, "st_size", 0) or 0)
    except Exception:  # pylint: disable=broad-exception-caught
        sz = len(data)

    if results is not None:
        results.setdefault("uploaded_files", []).append(
            {"guest_path": guest_path, "sha256": sha, "bytes": sz}
        )
    logger.info("Uploaded guest file: %s (sha256=%s, bytes=%s)", guest_path, sha, sz)


def _encode_windows_cmd_script(text: str) -> bytes:
    """
    Encode .cmd in a Windows-friendly way (UTF-16LE + BOM).
    Also normalizes to CRLF.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return b"\xff\xfe" + t.encode("utf-16le", errors="replace")


# Hivex node normalization (IMPORTANT)

NodeLike = Union[int, None]


def _node_id(n: NodeLike) -> int:
    """Convert node to int, treating None as 0."""
    if n is None:
        return 0
    try:
        return int(n)
    except (TypeError, ValueError):
        return 0


def _node_ok(n: NodeLike) -> bool:
    """Check if node is valid (non-zero)."""
    return _node_id(n) != 0


# Registry encoding helpers (CRITICAL)


def _reg_sz(s: str) -> bytes:
    """Encode string as REG_SZ (UTF-16LE with null terminator)."""
    return (s + "\0").encode("utf-16le", errors="ignore")


def _decode_reg_sz(raw: bytes) -> str:
    """Decode REG_SZ with fallback to UTF-8."""
    # raw comes from a possibly-corrupt registry hive and may not even be bytes-like; best-effort decode
    try:
        return raw.decode("utf-16le", errors="ignore").rstrip("\x00")
    except Exception:  # pylint: disable=broad-exception-caught
        try:
            return raw.decode("utf-8", errors="ignore").rstrip("\x00")
        except Exception:  # pylint: disable=broad-exception-caught
            return ""


def _mk_reg_value(name: str, t: int, value: bytes) -> dict[str, Any]:
    """Create registry value dictionary."""
    return {"key": name, "t": int(t), "value": value}


def _set_sz(h: hivex.Hivex, node: NodeLike, key: str, s: str) -> None:
    """Set REG_SZ value."""
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(
            f"Cannot set Windows registry value '{key}' (REG_SZ) — the target registry key does not exist. "
            f"The Windows registry hive may be corrupted."
        )
    h.node_set_value(nid, _mk_reg_value(key, 1, _reg_sz(s)))


def _set_expand_sz(h: hivex.Hivex, node: NodeLike, key: str, s: str) -> None:
    """Set REG_EXPAND_SZ value."""
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(
            f"Cannot set Windows registry value '{key}' (REG_EXPAND_SZ) — the target registry key does not exist. "
            f"The Windows registry hive may be corrupted."
        )
    h.node_set_value(nid, _mk_reg_value(key, 2, _reg_sz(s)))


def _set_dword(h: hivex.Hivex, node: NodeLike, key: str, v: int) -> None:
    """Set REG_DWORD value."""
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(
            f"Cannot set Windows registry value '{key}' (REG_DWORD) — the target registry key does not exist. "
            f"The Windows registry hive may be corrupted."
        )
    h.node_set_value(nid, _mk_reg_value(key, 4, int(v).to_bytes(4, "little", signed=False)))


def _ensure_child(h: hivex.Hivex, parent: NodeLike, name: str) -> int:
    """Get or create child node."""
    pid = _node_id(parent)
    if pid == 0:
        raise RuntimeError(
            f"Cannot create registry key '{name}' — the parent key does not exist. "
            f"The Windows registry hive structure may be corrupted."
        )

    ch = _node_id(h.node_get_child(pid, name))
    if ch == 0:
        ch = _node_id(h.node_add_child(pid, name))
    if ch == 0:
        raise RuntimeError(
            f"Failed to create registry key '{name}'. The registry hive may be read-only or corrupted."
        )
    return ch


def _delete_child_if_exists(
    h: hivex.Hivex, parent: NodeLike, name: str, *, logger: logging.Logger | None = None
) -> bool:
    """Delete child node if it exists (tries multiple hivex API signatures)."""
    pid = _node_id(parent)
    if pid == 0:
        return False

    child = _node_id(h.node_get_child(pid, name))
    if child == 0:
        return False

    tried: list[str] = []
    for args in ((pid, child), (pid, name), (child,)):
        tried.append(repr(args))
        # hivex's node_delete_child signature varies across versions; probe each call shape
        try:
            h.node_delete_child(*args)  # type: ignore[misc]
            if logger:
                logger.debug("Deleted child key %r using node_delete_child%s", name, args)
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            if logger:
                logger.debug("node_delete_child%s failed for %r: %s", args, name, e)
            continue

    if logger:
        logger.warning("All node_delete_child signatures failed for %r (tried: %s)", name, ", ".join(tried))
    return False


def _hivex_read_value_dict(h: hivex.Hivex, node: NodeLike, key: str) -> dict[str, Any] | None:
    """Read raw value dictionary from registry node."""
    nid = _node_id(node)
    if nid == 0:
        return None
    # hivex raises various undocumented exception types; treat any failure as "value not present"
    try:
        v = h.node_get_value(nid, key)
        if not v or "value" not in v:
            return None
        return v
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _hivex_read_sz(h: hivex.Hivex, node: NodeLike, key: str) -> str | None:
    """Read REG_SZ value."""
    v = _hivex_read_value_dict(h, node, key)
    if not v:
        return None
    raw = v.get("value")
    if isinstance(raw, (bytes, bytearray)):
        s = _decode_reg_sz(bytes(raw)).strip()
        return s or None
    if raw is None:
        return None
    s2 = str(raw).strip()
    return s2 or None


def _hivex_read_dword(h: hivex.Hivex, node: NodeLike, key: str) -> int | None:
    """Read REG_DWORD value."""
    v = _hivex_read_value_dict(h, node, key)
    if not v:
        return None
    raw = v.get("value")
    if isinstance(raw, (bytes, bytearray)) and len(raw) >= 4:
        return int.from_bytes(bytes(raw)[:4], "little", signed=False)
    if isinstance(raw, int):
        return raw
    return None


def _detect_current_controlset(h: hivex.Hivex, root: NodeLike) -> str:
    """Detect active ControlSet (ControlSet001 vs ControlSet002)."""
    r = _node_id(root)
    if r == 0:
        return "ControlSet001"

    select = _node_id(h.node_get_child(r, "Select"))
    if select == 0:
        return "ControlSet001"

    v = _hivex_read_value_dict(h, select, "Current")
    if not v:
        return "ControlSet001"

    cur_raw = v.get("value")
    if isinstance(cur_raw, (bytes, bytearray)) and len(cur_raw) >= 4:
        current_set = int.from_bytes(bytes(cur_raw)[:4], "little", signed=False)
    elif isinstance(cur_raw, int):
        current_set = int(cur_raw)
    else:
        current_set = 1

    return f"ControlSet{current_set:03d}"


# Hivex open helpers (LOCAL FILES ONLY)


def _open_hive_local(path: Path, *, write: bool) -> hivex.Hivex:
    """Open local hive file with validation."""
    if not path.exists():
        raise FileNotFoundError(
            f"Windows registry hive file not found at {path}. "
            f"The hive may not have been downloaded from the guest disk."
        )
    st = path.stat()
    if st.st_size < 4096:
        raise RuntimeError(
            f"Windows registry hive file at {path} is too small ({st.st_size} bytes) — "
            f"it may be corrupted or incomplete. Re-export the hive from the guest disk."
        )
    if not _is_probably_regf(path):
        raise RuntimeError(
            f"File at {path} is not a valid Windows registry hive — "
            f"missing 'regf' signature. It may be corrupted or not a registry hive."
        )
    if hivex is None:
        raise RuntimeError(
            "python-hivex is not available for this interpreter "
            f"({sys.executable}, Python {sys.version_info.major}.{sys.version_info.minor}). "
            "On RHEL-family systems, `dnf install python3-hivex` only installs bindings for "
            "the distro default `python3`. Pip-installed `h2kvmctl` often runs under "
            "Python 3.11/3.12 — install the matching RPM (e.g. `sudo dnf install "
            "python3.12-hivex` on EL9 when that package exists), or install h2kvm "
            "into the same Python that already has `python3-hivex`. "
            "Also install `hivex` for the `hivexget` CLI."
        )
    return hivex.Hivex(str(path), write=(1 if write else 0))


def _close_best_effort(h: hivex.Hivex | None) -> None:
    """Close hive (handles version differences)."""
    if h is None:
        return
    # hivex API varies by version; try each close method name, falling through on any failure
    try:
        if hasattr(h, "close") and callable(h.close):
            h.close()
            return
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        if hasattr(h, "hivex_close") and callable(h.hivex_close):
            h.hivex_close()
            return
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _commit_best_effort(h: hivex.Hivex) -> None:
    """Commit hive changes (handles version differences)."""
    if hasattr(h, "commit") and callable(h.commit):
        try:
            h.commit(None)  # type: ignore[arg-type]
            return
        except TypeError:
            h.commit()  # type: ignore[call-arg]
            return
        # hivex API varies by version; fall through to the hivex_commit method name on any failure
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    if hasattr(h, "hivex_commit") and callable(h.hivex_commit):
        try:
            h.hivex_commit(None)  # type: ignore[arg-type]
            return
        except TypeError:
            h.hivex_commit()  # type: ignore[call-arg]
            return

    raise RuntimeError(
        "python-hivex: unable to commit registry changes — no compatible commit method found. "
        "This may indicate an incompatible python-hivex version. "
        "Try upgrading: sudo dnf update python3-hivex (Fedora/RHEL)"
    )


# Internal: normalize Driver values (fixes NoneType -> int errors)


def _driver_start_default(drv: Any, *, fallback: int = 3) -> int:
    """Extract start_type from driver object with fallback."""
    st = getattr(drv, "start_type", None)

    if st is not None and hasattr(st, "value"):
        v = getattr(st, "value", None)
        if v is None:
            return int(fallback)
        try:
            return int(v)
        except (TypeError, ValueError):
            return int(fallback)

    if st is None:
        return int(fallback)

    try:
        return int(st)
    except (TypeError, ValueError):
        return int(fallback)


def _driver_type_norm(drv: Any) -> str:
    """Normalize driver type string."""
    t = getattr(drv, "type", None)
    if t is None:
        return ""
    if hasattr(t, "value"):
        v = getattr(t, "value", None)
        if v is not None:
            return str(v)
    return str(t)


def _pci_id_normalize(pci_id: str) -> str:
    """Normalize PCI ID string."""
    return str(pci_id).strip()
