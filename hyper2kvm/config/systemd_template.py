# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/config/systemd_template.py
"""Systemd unit file templates for service generation."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hyper2kvm.core.utils import U

# Keep this template in one place so both CLI help and generator use the same text.
# We use Python .format_map() so we can inject safe, quoted values.
SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=hyper2kvm Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} {script} --daemon --watch-dir={watch_dir} --config={config} {extra_args}
Restart=always
RestartSec=3
User={user}
Group={group}
WorkingDirectory={workdir}
Environment=PYTHONUNBUFFERED=1
# (Optional) load environment overrides, secrets, proxies, etc.
EnvironmentFile=-{env_file}
# Hardening (safe defaults; relax if you need device access beyond libvirt/qemu)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectControlGroups=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
LockPersonality=true
RestrictRealtime=true
RestrictSUIDSGID=true
RemoveIPC=true
UMask=0022
# Write access only where needed
ReadWritePaths={rw_paths}

# If you rely on qemu/libvirt, you may need to loosen some of these.
# E.g. uncomment:
# DeviceAllow=/dev/kvm r
# DeviceAllow=/dev/nbd* rw
# SupplementaryGroups=libvirt, kvm

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def _q(s: str) -> str:
    """Shell-quote for systemd ExecStart arguments."""
    return shlex.quote(s)


def _q_opt(s: str | None) -> str:
    """Quote optional strings; empty becomes empty."""
    if not s:
        return ""
    return _q(str(s))


def _join_rw_paths(rw: Any) -> str:
    """
    Normalize ReadWritePaths value.
    - Accept string or list/tuple of strings.
    - Keep spacing tidy.
    """
    if isinstance(rw, (list, tuple)):
        parts = [str(x).strip() for x in rw if str(x).strip()]
        return " ".join(parts)
    if isinstance(rw, str) and rw.strip():
        return rw.strip()
    return "/var/lib/hyper2kvm /var/log/hyper2kvm /tmp"


def _normalize_extra_args(extra: Any) -> str:
    """
    Extra args are appended verbatim (user-controlled).
    We keep behavior same (no parsing), but trim and collapse whitespace a bit.
    """
    if extra is None:
        return ""
    s = str(extra).strip()
    return " ".join(s.split()) if s else ""


@dataclass(frozen=True)
class SystemdUnitParams:  # pylint: disable=too-many-instance-attributes  # dataclass models many independent unit-file fields
    """Resolved parameters used to render the systemd unit template."""

    python: str
    script: str
    watch_dir: str
    config: str
    user: str = "root"
    group: str = "root"
    workdir: str = "/"
    env_file: str = "/etc/default/hyper2kvm"
    rw_paths: str = "/var/lib/hyper2kvm /var/log/hyper2kvm /tmp"
    extra_args: str = ""


def _infer_defaults(args: Any) -> SystemdUnitParams:
    """
    Infer sensible defaults from args, with fallbacks.
    We quote values for ExecStart safety.
    """
    python = getattr(args, "python", None) or "/usr/bin/python3"
    script = getattr(args, "script", None) or getattr(args, "entrypoint", None) or "/path/to/hyper2kvm.py"
    watch_dir = getattr(args, "watch_dir", None) or "/path/to/watch"
    config = getattr(args, "config", None) or "/path/to/config.yaml"

    user = getattr(args, "user", None) or "root"
    group = getattr(args, "group", None) or user

    # Prefer explicit workdir, else infer from script directory, else "/"
    workdir = getattr(args, "workdir", None)
    if not workdir:
        try:
            p = Path(str(script)).expanduser()
            workdir = str(p.parent) if p.parent and str(p.parent) != "." else "/"
        except (OSError, ValueError, RuntimeError):
            workdir = "/"

    env_file = getattr(args, "env_file", None) or "/etc/default/hyper2kvm"

    rw_paths = _join_rw_paths(getattr(args, "rw_paths", None))
    extra_args = _normalize_extra_args(getattr(args, "extra_args", None))

    # Quote ExecStart pieces; keep User/Group/paths unquoted (systemd expects raw)
    return SystemdUnitParams(
        python=_q(str(python)),
        script=_q(str(script)),
        watch_dir=_q(str(watch_dir)),
        config=_q(str(config)),
        user=str(user),
        group=str(group),
        workdir=str(workdir),
        env_file=str(env_file),
        rw_paths=str(rw_paths),
        extra_args=extra_args,
    )


def _validate_params(p: SystemdUnitParams) -> None:
    """
    Conservative validation. We do NOT fail on missing files because this is a generator,
    but we guard against empty critical fields.
    """
    if not p.python or not p.script:
        raise ValueError(
            "Systemd unit requires 'python' and 'script' parameters. "
            "Set the Python interpreter path and script path."
        )
    if not p.watch_dir or not p.config:
        raise ValueError(
            "Systemd unit requires 'watch_dir' and 'config' parameters. "
            "Set the directory to watch and configuration file path."
        )
    if not p.user:
        raise ValueError("Systemd unit requires a 'user' to run as (e.g., 'root' or 'hyper2kvm').")
    if not p.group:
        raise ValueError("Systemd unit requires a 'group' to run as (e.g., 'root' or 'hyper2kvm').")
    if not p.workdir:
        raise ValueError("Systemd unit requires a 'workdir' (working directory for the service).")


def _render_unit(p: SystemdUnitParams) -> str:
    return SYSTEMD_UNIT_TEMPLATE.format_map(
        {
            "python": p.python,
            "script": p.script,
            "watch_dir": p.watch_dir,
            "config": p.config,
            "extra_args": p.extra_args,
            "user": p.user,
            "group": p.group,
            "workdir": p.workdir,
            "env_file": p.env_file,
            "rw_paths": p.rw_paths,
        }
    )


def generate_systemd_unit(args: Any, logger=None) -> None:
    """
    Print or write a sample systemd unit file.

    Enhancements (same functionality):
      - robust default inference (workdir inferred from script when unset)
      - small validation to avoid emitting broken units
      - atomic write + fsync for durability (best effort)
      - clearer next-step instructions and safer enable command
      - still avoids dangerous unquoted ExecStart args
    """
    params = _infer_defaults(args)
    _validate_params(params)
    unit = _render_unit(params)

    out = getattr(args, "output", None)
    if out:
        out_path = Path(str(out)).expanduser()
        U.ensure_dir(out_path.parent)

        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(unit, encoding="utf-8")

        # Best-effort durability: fsync file then fsync dir
        try:
            with open(tmp, "rb") as f:
                os.fsync(f.fileno())
        except OSError as e:
            if logger:
                logger.debug(f"fsync on {tmp} skipped: {e}")

        tmp.replace(out_path)

        try:
            dfd = os.open(str(out_path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError as e:
            if logger:
                logger.debug(f"fsync on directory skipped: {e}")

        if logger:
            logger.info("Systemd unit written to %s", out_path)

            name = out_path.name
            unit_name = name if name.endswith(".service") else f"{name}.service"

            logger.info("Next steps:")
            logger.info(" sudo install -m 0644 %s /etc/systemd/system/%s", out_path, unit_name)
            logger.info(" sudo systemctl daemon-reload")
            logger.info(" sudo systemctl enable --now %s", unit_name)

            # Extra tip, but harmless:
            logger.info(" sudo journalctl -u %s -f", unit_name)

        return

    # No output path: print to stdout
    print(unit)


# Simple class wrapper for tests
class SystemdTemplate:  # pylint: disable=too-few-public-methods  # thin test-oriented wrapper, single render() is its whole purpose
    """Simple wrapper class for systemd template generation."""

    def __init__(self, vm_name: str, description: str = "", exec_start: str = "", exec_stop: str = ""):
        self.vm_name = vm_name
        self.description = description
        self.exec_start = exec_start
        self.exec_stop = exec_stop

    def render(self) -> str:
        """Render a simple systemd unit file."""
        return f"""[Unit]
Description={self.description or self.vm_name}
After=network-online.target

[Service]
Type=simple
ExecStart={self.exec_start}
ExecStop={self.exec_stop}
Restart=always

[Install]
WantedBy=multi-user.target
"""
