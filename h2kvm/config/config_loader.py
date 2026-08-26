# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/config/config_loader.py
"""Configuration file loader for YAML/JSON config files."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging

try:
    import yaml  # type: ignore

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class Config:
    """
    Config loader/merger with:
      - JSON/YAML support
      - safe glob/dir expansion (correct suffix filtering)
      - deep merge with configurable list strategy
      - dash-key -> underscore normalization (deep)
      - optional HMAC signature verification
      - VM fan-out via 'vms' list, with deep-merge per VM override
      - argparse defaults application with type coercion
      - ✅ alias canonicalization (command<->cmd, vs_action<->action)
      - ✅ vSphere control-plane canonicalization (govc knobs, env aliases)
    """

    # Public API

    @staticmethod
    def load_one(logger: logging.Logger, path: str) -> dict[str, Any]:
        """
        Load a single configuration file (YAML or JSON).

        Args:
            logger: Logger instance for error reporting
            path: Path to configuration file (.yaml, .yml, or .json)

        Returns:
            Dictionary containing normalized configuration with:
            - Keys converted from dash-case to underscore_case
            - Aliases canonicalized (cmd<->command, etc.)
            - Signature verified if enabled

        Raises:
            SystemExit: If file not found, invalid format, or verification fails

        Examples:
            >>> config = Config.load_one(logger, "migration.yaml")
            >>> print(config["cmd"])  # 'local', 'vsphere', etc.
        """
        p = Path(path).expanduser().resolve()
        if not p.exists():
            # Enhanced error message (no behavior change: still dies with code=1)
            Config._die_missing_config(logger, p, original_spec=path)

        # Verify signature if enabled
        Config.verify_signature(logger, p)

        try:
            raw = p.read_text(encoding="utf-8")
            if p.suffix.lower() == ".json":
                data = json.loads(raw)
            else:
                if not YAML_AVAILABLE:
                    U.die(logger, "PyYAML not installed. Install with: pip install PyYAML", 1)
                data = yaml.safe_load(raw) or {}
        except Exception as e:  # pylint: disable=broad-exception-caught  # parsing can raise many error types; all funnel to U.die
            # Keep YAML-specific errors nice if available
            if YAML_AVAILABLE and isinstance(e, getattr(yaml, "YAMLError", Exception)):
                U.die(
                    logger,
                    f"Invalid YAML syntax in config file '{p}': {e}\n"
                    f"    Check for indentation errors, missing colons, or unquoted special characters.",
                    1,
                )
            U.die(
                logger,
                f"Failed to read config file '{p}': {e}\n"
                f"    Verify the file is readable and contains valid JSON or YAML.",
                1,
            )

        if not isinstance(data, dict):
            U.die(
                logger,
                f"Config file '{p}' must contain a YAML/JSON mapping (key: value pairs), not a list or scalar.\n"
                f"    Example:\n      command: local\n      vmdk: /path/to/disk.vmdk",
                1,
            )

        # Normalize keys deeply: dash -> underscore
        out = Config._normalize_keys(logger, data, path=str(p))

        out = Config._canonicalize_aliases(out)

        logger.debug(f"Loaded config {p}:\n{U.json_dump(out)}")
        return out

    @staticmethod
    def verify_signature(  # pylint: disable=inconsistent-return-statements  # U.die() always raises; pylint can't see that
        logger: logging.Logger, config_path: Path
    ) -> bool:
        """
        Verify config file signature for production use.

        Behavior:
          - If VM2KVM_CONFIG_SECRET is unset -> verification disabled (returns True).
          - If .sig file missing -> warn + allow (returns True). (You can tighten this if desired.)
          - If present and mismatched -> die.
        """
        secret = os.environ.get("VM2KVM_CONFIG_SECRET", "")
        if not secret:
            logger.debug("No config verification secret set (VM2KVM_CONFIG_SECRET)")
            return True

        sig_path = config_path.with_suffix(config_path.suffix + ".sig")
        if not sig_path.exists():
            U.die(logger, f"Config signature verification enabled but .sig file missing: {sig_path}", 1)

        try:
            config_content = config_path.read_bytes()
            expected_sig = hmac.new(secret.encode(), config_content, hashlib.sha256).hexdigest()
            actual_sig = sig_path.read_text(encoding="utf-8").strip()
            if not hmac.compare_digest(expected_sig, actual_sig):
                U.die(
                    logger,
                    f"Config signature verification failed for '{config_path}'.\n"
                    f"    The .sig file does not match the config contents. "
                    f"Regenerate the signature or check for file tampering.",
                    1,
                )
            logger.debug("Config signature verified: %s", config_path)
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught  # verification can raise many error types; all funnel to U.die
            U.die(
                logger,
                f"Config signature verification error for '{config_path}': {e}\n"
                f"    Ensure VM2KVM_CONFIG_SECRET is correct and the .sig file is readable.",
                1,
            )

    @staticmethod
    def merge_dicts(
        base: dict[str, Any],
        override: dict[str, Any],
        *,
        list_mode: str = "replace",  # "replace" | "append" | "extend_unique"
    ) -> dict[str, Any]:
        """
        Deep merge:
          - dict + dict => recurse
          - list => strategy by list_mode
          - scalar => override replaces

        list_mode:
          - replace: override list replaces base list
          - append: base + override (concatenate)
          - extend_unique: concatenate but keep first occurrence (hashable only)
        """
        out: dict[str, Any] = dict(base)

        for k, v in override.items():  # pylint: disable=too-many-nested-blocks  # merge strategies are inherently branchy
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = Config.merge_dicts(out[k], v, list_mode=list_mode)
                continue

            if isinstance(out.get(k), list) and isinstance(v, list):
                if list_mode == "replace":
                    out[k] = v
                elif list_mode == "append":
                    out[k] = list(out[k]) + list(v)
                elif list_mode == "extend_unique":
                    merged: list[Any] = []
                    seen: set = set()
                    for item in list(out[k]) + list(v):
                        try:
                            if item in seen:
                                continue
                            seen.add(item)
                        except TypeError:
                            # unhashable type -> just append (best effort dedup)
                            pass
                        merged.append(item)
                    out[k] = merged
                else:
                    out[k] = v
                continue

            out[k] = v

        return out

    @staticmethod
    def load_many(
        logger: logging.Logger,
        paths: list[str],
        *,
        list_mode: str = "replace",
    ) -> dict[str, Any]:
        """Expand, load, and deep-merge multiple config files in order."""
        paths = Config.expand_configs(logger, paths)

        # Pre-check missing before the progress UI starts
        Config._precheck_missing_paths(logger, paths)

        conf: dict[str, Any] = {}

        if not paths:
            return conf

        for i, p in enumerate(paths, 1):
            logger.info("Loading config %d/%d: %s", i, len(paths), p)
            conf = Config.merge_dicts(conf, Config.load_one(logger, p), list_mode=list_mode)

        return Config._canonicalize_aliases(conf)

    @staticmethod
    def apply_as_defaults(
        logger: logging.Logger,
        parser: argparse.ArgumentParser,
        conf: dict[str, Any],
        *,
        strict: bool = False,
    ) -> None:
        """
        Apply config values as argparse defaults.

        Enhancements:
          - type coercion using argparse action.type when present
          - turns off required if provided by config
          - optionally strict: die if config contains keys not present in argparse dests
        """
        if not conf:
            return

        valid_dests = Config._collect_argparse_dests(parser)

        if strict:
            unknown = sorted(set(conf.keys()) - valid_dests)
            if unknown:
                U.die(logger, f"Unknown config keys (no argparse dest): {unknown}", 1)

        def apply_actions(actions: list[argparse.Action], scope: str) -> None:
            for act in actions:
                dest = getattr(act, "dest", None)
                if not dest or dest not in conf:
                    continue

                raw_val = conf[dest]
                val = Config._coerce_argparse_value(logger, act, raw_val, scope=scope, dest=dest)

                logger.debug(f"[Config:{scope}] default {dest}: {act.default!r} -> {val!r}")
                act.default = val

                if getattr(act, "required", False) and val is not None:
                    act.required = False

        # argparse has no public API for introspecting sub-actions/subparsers.
        # pylint: disable=protected-access
        apply_actions(parser._actions, "global")

        sp_action = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
        if sp_action:
            for name, sp in sp_action.choices.items():
                apply_actions(sp._actions, f"sub:{name}")
        # pylint: enable=protected-access

    @staticmethod
    def apply_config_to_namespace(
        logger: logging.Logger,
        parser: argparse.ArgumentParser,
        conf: dict[str, Any],
        namespace: argparse.Namespace,
    ) -> None:
        """
        Apply all keys from a config dict onto an existing argparse.Namespace.

        Uses the parser's action definitions for type coercion (via
        ``_coerce_argparse_value``), so YAML values like ``memory: 4096``
        or ``compress: true`` are coerced exactly as if they had been
        passed on the command line.

        Keys that have no matching argparse action are set directly on the
        namespace (forward-compatibility for new options).
        """
        if not conf:
            return

        normalized = Config._normalize_keys(logger, conf, path="<daemon-config>")
        normalized = Config._canonicalize_aliases(normalized)

        # Build dest -> action lookup across global parser + all subparsers.
        # argparse has no public API for introspecting sub-actions/subparsers.
        # pylint: disable=protected-access
        action_map: dict[str, argparse.Action] = {}
        for act in parser._actions:
            dest = getattr(act, "dest", None)
            if dest:
                action_map[dest] = act
        sp_action = next(
            (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)),
            None,
        )
        if sp_action:
            for sp in sp_action.choices.values():
                for act in sp._actions:
                    dest = getattr(act, "dest", None)
                    if dest and dest not in action_map:
                        action_map[dest] = act
        # pylint: enable=protected-access

        for key, raw_val in normalized.items():
            if key in action_map:
                val = Config._coerce_argparse_value(
                    logger,
                    action_map[key],
                    raw_val,
                    scope="daemon",
                    dest=key,
                )
            else:
                val = raw_val
            logger.debug(f"[Config:daemon] namespace {key} = {val!r}")
            setattr(namespace, key, val)

    @staticmethod
    def expand_configs(logger: logging.Logger, configs: list[str]) -> list[str]:
        """
        Expand list of config specs:
          - directories: include **/*.yml, **/*.yaml, **/*.json
          - glob patterns: expanded via glob.glob
          - files: passed through
        """
        expanded: list[str] = []

        for c in configs:
            p = Path(c).expanduser()

            if p.exists() and p.is_dir():
                # Correct suffix filtering (your original '*.[yaml|yml|json]' is a glob bug)
                for f in p.rglob("*"):
                    if f.is_file() and f.suffix.lower() in (".yaml", ".yml", ".json"):
                        expanded.append(str(f.resolve()))
                continue

            if "*" in c or "?" in c or ("[" in c and "]" in c):
                pattern_path = Path(c)
                if pattern_path.is_absolute():
                    glob_anchor = Path(pattern_path.anchor)
                    glob_pattern = str(pattern_path.relative_to(glob_anchor))
                    matches = glob_anchor.glob(glob_pattern)
                else:
                    matches = Path().glob(c)
                expanded.extend([str(Path(x).expanduser().resolve()) for x in matches])
                continue

            expanded.append(str(Path(c).expanduser().resolve()))

        # De-dup while preserving order
        seen = set()
        uniq: list[str] = []
        for x in expanded:
            if x not in seen:
                uniq.append(x)
                seen.add(x)

        logger.debug(f"Expanded configs: {uniq}")
        return uniq

    @staticmethod
    def load_vm_configs(
        logger: logging.Logger,
        paths: list[str],
        *,
        list_mode: str = "replace",
    ) -> list[dict[str, Any]]:
        """
        Load configs; if a config has 'vms' list, fan-out into per-VM configs.
        Each VM entry deep-merges over the base config (minus 'vms').
        """
        vm_confs: list[dict[str, Any]] = []
        paths = Config.expand_configs(logger, paths)

        # Pre-check missing before the progress UI starts
        Config._precheck_missing_paths(logger, paths)

        if not paths:
            return vm_confs

        for i, path in enumerate(paths, 1):
            logger.info("Loading VM config %d/%d: %s", i, len(paths), path)
            conf = Config.load_one(logger, path)

            vms = conf.get("vms")
            if isinstance(vms, list):
                base = dict(conf)
                base.pop("vms", None)

                for idx, vm in enumerate(vms):
                    if not isinstance(vm, dict):
                        U.die(logger, f"'vms' entries must be mappings/dicts in {path} (index {idx})", 1)
                    vm_conf = Config.merge_dicts(base, vm, list_mode=list_mode)
                    vm_confs.append(vm_conf)
            else:
                vm_confs.append(conf)

        return [Config._canonicalize_aliases(c) for c in vm_confs]

    @staticmethod
    def _canonicalize_aliases(d: dict[str, Any]) -> dict[str, Any]:
        """
        Canonicalize common alias keys so YAML can stay stable while code evolves.

        """
        # command <-> cmd
        if "command" in d and "cmd" not in d:
            d["cmd"] = d["command"]
        elif "cmd" in d and "command" not in d:
            d["command"] = d["cmd"]

        # vs_action <-> action
        if "vs_action" in d and "action" not in d:
            d["action"] = d["vs_action"]
        elif "action" in d and "vs_action" not in d:
            d["vs_action"] = d["action"]

        # vs_control_plane <-> control_plane
        if "vs_control_plane" in d and "control_plane" not in d:
            d["control_plane"] = d["vs_control_plane"]
        elif "control_plane" in d and "vs_control_plane" not in d:
            d["vs_control_plane"] = d["control_plane"]

        # GOVC_* style aliases (after key normalization, these are likely "govc_url" etc,
        # but users may still write "GOVC_URL" in YAML; safe-load keeps case, normalize_keys
        # does not change case, so we map a few common ones explicitly.)
        # Prefer explicit govc_* if present.
        govc_map = {
            "GOVC_URL": "govc_url",
            "GOVC_USERNAME": "govc_user",
            "GOVC_USER": "govc_user",
            "GOVC_PASSWORD": "govc_password",
            "GOVC_PASSWORD_ENV": "govc_password_env",
            "GOVC_INSECURE": "govc_insecure",
            "GOVC_DATACENTER": "govc_datacenter",
            "GOVC_DATASTORE": "govc_ds",
            "GOVC_DS": "govc_ds",
            "GOVC_FOLDER": "govc_folder",
            "GOVC_CLUSTER": "govc_cluster",
            "GOVC_RESOURCE_POOL": "govc_resource_pool",
        }
        for src, dst in govc_map.items():
            if src in d and dst not in d:
                d[dst] = d[src]

        # Light normalization of vs_control_plane values if user provided one
        if "vs_control_plane" in d and isinstance(d["vs_control_plane"], str):
            d["vs_control_plane"] = d["vs_control_plane"].strip().lower()

        return d

    @staticmethod
    def _normalize_keys(logger: logging.Logger, obj: Any, *, path: str, _prefix: str = "") -> Any:
        """
        Recursively normalize dict keys:
          - replace '-' with '_' in keys
        """
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                nk = str(k).replace("-", "_")
                if nk != k:
                    logger.debug(f"Normalized config key: {_prefix}{k} -> {_prefix}{nk} (file={path})")
                out[nk] = Config._normalize_keys(logger, v, path=path, _prefix=f"{_prefix}{nk}.")
            return out
        if isinstance(obj, list):
            return [Config._normalize_keys(logger, x, path=path, _prefix=_prefix) for x in obj]
        return obj

    @staticmethod
    def _collect_argparse_dests(parser: argparse.ArgumentParser) -> set:
        """Collect argparse dest names across the parser and all subparsers."""
        # argparse has no public API for introspecting sub-actions/subparsers.
        # pylint: disable=protected-access
        dests = set()
        for a in parser._actions:
            d = getattr(a, "dest", None)
            if d:
                dests.add(d)
        sp_action = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
        if sp_action:
            for sp in sp_action.choices.values():
                for a in sp._actions:
                    d = getattr(a, "dest", None)
                    if d:
                        dests.add(d)
        return dests
        # pylint: enable=protected-access

    @staticmethod
    def _coerce_argparse_value(  # pylint: disable=too-many-return-statements  # each branch coerces one distinct value shape
        logger: logging.Logger,
        act: argparse.Action,
        raw_val: Any,
        *,
        scope: str,
        dest: str,
    ) -> Any:
        """
        Best-effort type coercion consistent with argparse.
        """
        nargs = getattr(act, "nargs", None)
        act_type = getattr(act, "type", None)

        # argparse has no public API for introspecting these action types.
        # pylint: disable=protected-access
        if isinstance(act, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            # pylint: enable=protected-access
            if isinstance(raw_val, bool):
                return raw_val
            if isinstance(raw_val, str):
                s = raw_val.strip().lower()
                return s in ("1", "true", "yes", "y", "on")
            return bool(raw_val)

        if act_type is None:
            return raw_val

        def coerce_one(x: Any) -> Any:
            try:
                return act_type(x)
            except (ValueError, TypeError):
                logger.warning(
                    f"[Config:{scope}] could not convert '{dest}' value {x!r} to {act_type.__name__}, using as-is"
                )
                return x

        if nargs in ("+", "*") or isinstance(raw_val, (list, tuple)):
            if isinstance(raw_val, (list, tuple)):
                return [coerce_one(x) for x in raw_val]
            return [coerce_one(raw_val)]

        return coerce_one(raw_val)

    @staticmethod
    def _precheck_missing_paths(logger: logging.Logger, paths: list[str]) -> None:
        """
        Fail early (before progress UI) if any expanded configs don't exist.
        This avoids partial progress bars and gives one clean actionable error.
        """
        if not paths:
            return
        missing = [p for p in paths if not Path(p).exists()]
        if not missing:
            return

        msg_lines: list[str] = ["Config file(s) not found:"]
        for m in missing[:20]:
            msg_lines.append(f" - {m}")
        if len(missing) > 20:
            msg_lines.append(f" ... and {len(missing) - 20} more")

        msg_lines.append("")
        msg_lines.append(Config._missing_config_help(missing[0], original_spec=None))

        U.die(logger, "\n".join(msg_lines), 1)

    @staticmethod
    def _die_missing_config(
        logger: logging.Logger, resolved: Path, *, original_spec: str | None = None
    ) -> None:
        help_text = Config._missing_config_help(str(resolved), original_spec=original_spec)
        msg = f"Config not found: {resolved}\n\n{help_text}"
        U.die(logger, msg, 1)

    @staticmethod
    def _missing_config_help(resolved_path: str, *, original_spec: str | None) -> str:
        """
        Build actionable hints for missing config paths.
        - Shows whether user passed a glob
        - Shows nearby configs in same directory
        - Suggests correct usage
        """
        rp = Path(resolved_path).expanduser()
        parent = rp.parent

        lines: list[str] = []

        if original_spec and (
            ("*" in original_spec)
            or ("?" in original_spec)
            or ("[" in original_spec and "]" in original_spec)
        ):
            lines.append(f"Note: the config argument looked like a glob pattern: {original_spec!r}")
            lines.append(" It expanded to zero matching files (or matched paths that don't exist).")

        if parent.exists() and parent.is_dir():
            candidates: list[Path] = []
            for ext in (".yaml", ".yml", ".json"):
                candidates.extend(sorted(parent.glob(f"*{ext}")))

            if candidates:
                lines.append("Configs found in that directory:")
                for c in candidates[:10]:
                    lines.append(f" - {c.resolve()}")
                if len(candidates) > 10:
                    lines.append(f" ... and {len(candidates) - 10} more")
            else:
                lines.append("That directory exists, but no *.yaml/*.yml/*.json configs were found there.")
        else:
            lines.append("Parent directory does not exist (or is not accessible).")

        lines.append("Tip: pass an absolute path, e.g. --config /full/path/config.yaml")
        return "\n".join(lines)
