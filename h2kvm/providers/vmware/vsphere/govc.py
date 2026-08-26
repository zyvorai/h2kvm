# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/vsphere/govc.py
"""govc CLI wrapper and utility functions for vSphere operations"""

from __future__ import annotations

import contextlib
import fnmatch
import subprocess
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ....core.exceptions import VMwareError
from ....core.utils import U

if TYPE_CHECKING:
    from collections.abc import Iterable

try:
    from h2kvm.providers.vmware.transports.govc_common import GovcRunner, normalize_ds_path
except ImportError:
    # fallback for minimal environment
    GovcRunner = None
    normalize_ds_path = None


# Small generic helpers


def _p(s: str | None) -> Path | None:
    if not s:
        return None
    return Path(s).expanduser()


def _normalize_ds_path(datastore: str, ds_path: str) -> tuple[str, str]:
    """Backwards-compatible wrapper; real logic lives in govc_common.normalize_ds_path()."""
    return normalize_ds_path(datastore, ds_path)


def _arg_any(args: Any, *names: str, default: Any = None) -> Any:
    """
    Return the first present, non-empty attribute from args among names.
    Useful to support legacy flags without infecting code with suffixes like "2".
    """
    for n in names:
        if not n:
            continue
        v = getattr(args, n, None)
        if v not in (None, ""):
            return v
    return default


def _require(args: Any, name: str) -> Any:
    """
    Validate that argparse-like object has attribute AND it is non-None.
    Keep this for action-specific required args (not global argparse requirements).
    """
    if not hasattr(args, name):
        raise VMwareError(f"Missing required arg: {name}")
    v = getattr(args, name)
    if v is None:
        raise VMwareError(f"Missing required arg: {name}")
    return v


def _merged_cfg(args: Any, conf: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge CLI + YAML config into a single dict for VMwareClient.from_config().
    CLI overrides config. We also populate vs_* aliases for compat.
    """
    cfg: dict[str, Any] = dict(conf or {})

    vcenter = getattr(args, "vcenter", None)
    vc_user = getattr(args, "vc_user", None)
    vc_password = getattr(args, "vc_password", None)
    vc_password_env = getattr(args, "vc_password_env", None)
    vc_port = getattr(args, "vc_port", None)
    vc_insecure = getattr(args, "vc_insecure", None)
    dc_name = getattr(args, "dc_name", None)

    cfg.update(
        {
            # canonical
            "vcenter": vcenter,
            "vc_user": vc_user,
            "vc_password": vc_password,
            "vc_password_env": vc_password_env,
            "vc_port": vc_port,
            "vc_insecure": vc_insecure,
            "dc_name": dc_name,
            # aliases (historical)
            "vs_host": vcenter,
            "vs_user": vc_user,
            "vs_password": vc_password,
            "vs_password_env": vc_password_env,
            "vs_port": vc_port,
            "vs_insecure": vc_insecure,
        }
    )

    # Drop None so config can still supply defaults
    return {k: v for k, v in cfg.items() if v is not None}


def _as_payload(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


# Output policy (single source of truth)


class _Emitter:
    """
    Exactly one output style per action:
      - --json => print JSON payload only
      - non-json => log human lines (or a single human message)
    """

    def __init__(self, args: Any, logger: Any):
        self.args = args
        self.logger = logger

    def json_enabled(self) -> bool:
        """Return True if the CLI args request JSON output."""
        return bool(getattr(self.args, "json", False))

    def emit(
        self,
        payload: Any,
        *,
        human: Iterable[str] | None = None,
        human_msg: str | None = None,
    ) -> None:
        """Print `payload` as JSON, or as human-readable lines/message/fallback JSON."""
        payload = _as_payload(payload)
        if self.json_enabled():
            print(U.json_dump(payload))
            return

        if human is not None:
            for line in human:
                self.logger.info("%s", line)
            return

        if human_msg:
            self.logger.info("%s", human_msg)
            return

        # fallback (still non-json, but structured)
        self.logger.info("%s", U.json_dump(payload))


# govc adapter (centralized subprocess execution)


class GovmomiCLI(GovcRunner):
    """
    Best-effort integration with govmomi CLI (`govc`).

    Preference policy (unchanged):
      - If govc exists AND user didn't disable it: prefer it for
          * list_vm_names
          * download_datastore_file
          * datastore_ls / download_datastore_dir
      - Everything else stays in VMwareClient/pyvmomi.
    """

    def __init__(self, args: Any, logger: Any):
        super().__init__(logger=logger, args=args)

    def _run_text(self, argv: list[str]) -> str:
        """
        Centralized subprocess runner for text output.
        We intentionally do NOT scatter subprocess.run across the file.
        """
        full = [self.govc_bin, *list(argv)]
        with contextlib.suppress(Exception):
            self.logger.debug("govc: %s", " ".join(full))

        p = subprocess.run(
            full,
            capture_output=True,
            env=self.env(),
            text=True,
            check=False,
        )
        if p.returncode != 0:
            raise VMwareError(f"govc failed ({p.returncode}): {p.stderr.strip()}")
        return p.stdout or ""

    def list_vm_names(self) -> list[str]:
        """
        Prefer: govc find -type m -json .
        Returns VM *names* (basename of inventory paths).
        """
        data = self.run_json(["find", "-type", "m", "-json", "."]) or {}
        elems = data.get("Elements") or []
        if not isinstance(elems, list):
            elems = []
        names = [str(p).rsplit("/", maxsplit=1)[-1] for p in elems if p]
        return sorted({n for n in names if n})

    def download_datastore_file(self, datastore: str, ds_path: str, local_path: Path) -> None:
        """
        govc datastore.download -ds <datastore> <remote> <local>
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)

        ds, remote = normalize_ds_path(datastore, ds_path)
        if not remote:
            raise VMwareError("govc datastore.download: empty ds_path after normalization")

        self._run_text(["datastore.download", "-ds", str(ds), remote, str(local_path)])

    # govc's ls -json output shape has varied across versions; each branch
    # handles one known shape and is clearer kept inline than split apart
    # pylint: disable-next=too-many-branches
    def _extract_names_from_ls_json(self, files: Any) -> list[str]:
        """
        Robust extraction of leaf names from govc datastore.ls -json output.
        Shapes vary across govc versions and flags.
        """
        out: list[str] = []
        if files is None:
            return out

        if isinstance(files, list):
            items = files
        elif isinstance(files, dict):
            items = []
            for k in ("Files", "files", "File", "file", "Elements", "elements"):
                v = files.get(k)
                if isinstance(v, list):
                    items = v
                    break
        else:
            items = []

        for it in items:
            if it is None:
                continue
            if isinstance(it, str):
                out.append(Path(it).name)
                continue
            if isinstance(it, dict):
                for k in ("Name", "name", "Path", "path", "File", "file"):
                    v = it.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(Path(v).name)
                        break
                continue
            out.append(Path(str(it)).name)

        seen = set()
        uniq: list[str] = []
        for n in out:
            if n and n not in seen:
                uniq.append(n)
                seen.add(n)
        return uniq

    def datastore_ls_names(self, datastore: str, ds_dir: str) -> list[str]:
        """
        govc datastore.ls -json -ds <datastore> <dir/>
        Returns *leaf names* (non-recursive).
        """
        files = self.datastore_ls_json(datastore=datastore, ds_dir=ds_dir)
        return self._extract_names_from_ls_json(files)

    # pylint: disable-next=too-many-arguments  # mostly keyword-only filtering options with sane defaults
    def download_datastore_dir(
        self,
        datastore: str,
        ds_dir: str,
        local_dir: Path,
        *,
        include_globs: tuple[str, ...] = ("*",),
        exclude_globs: tuple[str, ...] = (),
        max_files: int = 5000,
    ) -> dict[str, Any]:
        """
        Non-recursive directory download using:
          - govc datastore.ls -json
          - govc datastore.download (per file)
        """
        ds, rel_dir = normalize_ds_path(datastore, ds_dir)
        rel_dir = rel_dir.rstrip("/") + "/"
        local_dir.mkdir(parents=True, exist_ok=True)

        names = self.datastore_ls_names(ds, rel_dir)

        picked: list[str] = []
        for n in names:
            ok = True
            if include_globs:
                ok = any(fnmatch.fnmatch(n, g) for g in include_globs)
            if ok and exclude_globs and any(fnmatch.fnmatch(n, g) for g in exclude_globs):
                ok = False
            if ok:
                picked.append(n)
            if len(picked) >= int(max_files or 5000):
                break

        for n in picked:
            remote = rel_dir + n
            dst = local_dir / n
            self.download_datastore_file(ds, remote, dst)

        return {
            "ok": True,
            "provider": "govc",
            "datastore": str(ds),
            "ds_dir": rel_dir,
            "local_dir": str(local_dir),
            "files_total": len(names),
            "files_downloaded": len(picked),
            "files": picked,
        }


def _prefer_govc(args: Any, logger: Any) -> GovmomiCLI | None:
    g = GovmomiCLI(args=args, logger=logger)
    return g if g.enabled() else None
