# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/args/helpers.py
"""CLI argument helper functions and utilities."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse


def _require(v: Any) -> bool:
    """True if v is meaningfully present (treats empty/whitespace-only strings as missing)."""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    return True


def _merged_get(args: argparse.Namespace, conf: dict[str, Any], key: str) -> Any:
    """
    Prefer CLI override if present (non-empty), else config.
    Supports both snake_case keys in conf and argparse dest keys.
    """
    v = getattr(args, key, None)
    if _require(v):
        return v
    return conf.get(key)


def _merged_secret(
    args: argparse.Namespace, conf: dict[str, Any], value_key: str, env_key: str
) -> str | None:
    """
    Resolve a secret from (CLI value) or (CLI env var name) or (YAML value) or (YAML env var name).
    Example: (vc_password, vc_password_env)
    """
    direct = _merged_get(args, conf, value_key)
    if _require(direct):
        return str(direct)

    envname = _merged_get(args, conf, env_key)
    if _require(envname):
        return os.environ.get(str(envname), None)

    return None


def _merged_cmd(args: argparse.Namespace, conf: dict[str, Any]) -> str | None:
    """
    Resolve command from CLI args or config, with alias normalization.

    Supported aliases:
    - "migrate" → "local"
    """
    # Command aliases mapping
    command_aliases = {
        "migrate": "local",
    }

    v = getattr(args, "cmd", None)
    if _require(v):
        cmd = str(v).strip()
        return command_aliases.get(cmd, cmd)

    v = conf.get("cmd")
    if _require(v):
        cmd = str(v).strip()
        return command_aliases.get(cmd, cmd)

    v = conf.get("command")
    if _require(v):
        cmd = str(v).strip()
        return command_aliases.get(cmd, cmd)

    return None


def _merged_vs_action(args: argparse.Namespace, conf: dict[str, Any]) -> str | None:
    v = getattr(args, "vs_action", None)
    if _require(v):
        return str(v).strip()
    v = conf.get("vs_action")
    if _require(v):
        return str(v).strip()
    v = conf.get("action")
    if _require(v):
        return str(v).strip()
    return None


def _resolve_workdir(args: argparse.Namespace, conf: dict[str, Any]) -> str:
    out_dir = _merged_get(args, conf, "output_dir") or "./out"
    wd = getattr(args, "workdir", None) or os.path.join(str(out_dir), "work")
    Path(wd).mkdir(parents=True, exist_ok=True)
    return str(wd)


def _materialize_win_net_json_if_needed(args: argparse.Namespace, conf: dict[str, Any], logger: Any) -> None:
    """
    If user provided inline win_net_json and did NOT provide win_net_override,
    write the JSON to a stable file under workdir, and set args.win_net_override.
    """
    p = _merged_get(args, conf, "win_net_override")
    if _require(p):
        return

    js = _merged_get(args, conf, "win_net_json")
    if not _require(js):
        return

    parsed = json.loads(str(js))
    if not isinstance(parsed, dict):
        raise SystemExit("win_net_json must be a JSON object (top-level dict)")

    wd = _resolve_workdir(args, conf)
    out_path = os.path.join(wd, "win-net-override.json")

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(parsed, indent=2, sort_keys=True))
            f.write("\n")
    except Exception as e:
        raise SystemExit(f"Failed to write materialized win-net override JSON to {out_path}: {e}") from e

    args.win_net_override = out_path

    with contextlib.suppress(Exception):
        logger.info("Materialized win_net_json into %s", out_path)


def _materialize_virtio_config_json_if_needed(
    args: argparse.Namespace, conf: dict[str, Any], logger: Any
) -> None:
    """
    If user provided inline virtio_config_json and did NOT provide virtio_config_path,
    write it under workdir and set args.virtio_config_path.
    """
    pth = _merged_get(args, conf, "virtio_config_path")
    if _require(pth):
        return

    js = _merged_get(args, conf, "virtio_config_json")
    if not _require(js):
        return

    parsed = json.loads(str(js))
    if not isinstance(parsed, dict):
        raise SystemExit("virtio_config_json must be a JSON object (top-level dict)")

    wd = _resolve_workdir(args, conf)
    out_path = os.path.join(wd, "virtio-config.json")

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(parsed, indent=2, sort_keys=True))
            f.write("\n")
    except Exception as e:
        raise SystemExit(f"Failed to write materialized virtio-config JSON to {out_path}: {e}") from e

    args.virtio_config_path = out_path

    with contextlib.suppress(Exception):
        logger.info("Materialized virtio_config_json into %s", out_path)
