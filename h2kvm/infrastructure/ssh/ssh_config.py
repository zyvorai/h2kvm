# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""SSH configuration management and connection parameters."""

# h2kvm/ssh/ssh_config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from h2kvm.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Sequence


def _is_probably_ipv6(host: str) -> bool:
    # cheap, good-enough heuristic (no ipaddress import needed)
    return ":" in (host or "")


def _scp_host(host: str) -> str:
    # scp/rsync need [v6] bracket form
    h = (host or "").strip()
    if _is_probably_ipv6(h) and not (h.startswith("[") and h.endswith("]")):
        return f"[{h}]"
    return h


def _clean_opt(opt: str) -> str:
    # Keep it one-line and strip; reject embedded newlines.
    o = (opt or "").strip()
    o = o.replace("\r", " ").replace("\n", " ")
    return " ".join(o.split())


@dataclass(frozen=True)
class SSHConfig:
    """
    Canonical SSH connection configuration.

    Designed for:
      - ESXi access
      - remote image fixes
      - smoke tests
      - automation / CI (non-interactive)
    """

    host: str
    user: str = "root"
    port: int = 22
    identity: Path | None = None
    password: str | None = None
    ssh_opts: list[str] = field(default_factory=list)

    # behavior
    sudo: bool = False
    connect_timeout: int = 10
    keepalive_interval: int = 30
    keepalive_count: int = 3

    # advanced
    jump_host: str | None = None  # ProxyJump
    strict_host_key_checking: bool = False  # automation-safe default

    # explicit non-interactive behavior (CI-safe)
    batch_mode: bool = True
    request_tty: bool = False

    # host key policy knobs
    known_hosts_file: Path | None = None
    accept_new_host_keys: bool = False  # semantic intent; may not be emitted on old ssh
    force_accept_new: bool = False  # if True, emit accept-new even if ssh might be old

    # performance / multiplexing knobs
    control_master: bool = False
    control_path: Path | None = None
    control_persist_s: int = 60

    def __post_init__(self) -> None:
        host = (self.host or "").strip()
        if not host:
            raise ConfigurationError(
                code=78, msg="SSH configuration error: host must not be empty"
            ).with_context(solutions=["Provide a valid hostname or IP address in the SSH configuration"])
        object.__setattr__(self, "host", host)

        user = (self.user or "").strip()
        if not user:
            raise ConfigurationError(
                code=78, msg="SSH configuration error: user must not be empty"
            ).with_context(solutions=["Provide a valid SSH username (e.g., 'root', 'admin')"])
        object.__setattr__(self, "user", user)

        if self.identity is not None:
            object.__setattr__(self, "identity", Path(self.identity).expanduser())

        if self.known_hosts_file is not None:
            object.__setattr__(self, "known_hosts_file", Path(self.known_hosts_file).expanduser())

        if self.jump_host is not None:
            j = (self.jump_host or "").strip()
            object.__setattr__(self, "jump_host", j or None)

        if self.ssh_opts:
            cleaned: list[str] = []
            seen = set()
            for opt in self.ssh_opts:
                o = _clean_opt(opt)
                if not o:
                    continue
                if o not in seen:
                    cleaned.append(o)
                    seen.add(o)
            object.__setattr__(self, "ssh_opts", cleaned)

        if self.port <= 0 or self.port > 65535:
            raise ConfigurationError(
                code=78, msg=f"SSH configuration error: invalid port {self.port}"
            ).with_context(
                solutions=["Use a valid TCP port number between 1 and 65535 (default: 22)"], port=self.port
            )

        for name, v in (
            ("connect_timeout", self.connect_timeout),
            ("keepalive_interval", self.keepalive_interval),
            ("keepalive_count", self.keepalive_count),
            ("control_persist_s", self.control_persist_s),
        ):
            if v < 0:
                raise ConfigurationError(
                    code=78, msg=f"SSH configuration error: {name} must be >= 0 (got {v})"
                ).with_context(solutions=[f"Set {name} to a non-negative value"])

    # Rendering helpers

    def target(self) -> str:
        # Using bracket form is harmless for ssh and consistent with scp.
        return f"{self.user}@{_scp_host(self.host)}"

    def scp_target(self) -> str:
        return f"{self.user}@{_scp_host(self.host)}"

    def _append_hostkey_policy(self, cmd: list[str]) -> None:
        if self.strict_host_key_checking:
            if self.accept_new_host_keys and self.force_accept_new:
                cmd += ["-o", "StrictHostKeyChecking=accept-new"]
            else:
                cmd += ["-o", "StrictHostKeyChecking=yes"]
        else:
            cmd += ["-o", "StrictHostKeyChecking=no"]

        if self.known_hosts_file is not None:
            cmd += ["-o", f"UserKnownHostsFile={self.known_hosts_file}"]
        elif not self.strict_host_key_checking:
            cmd += ["-o", "UserKnownHostsFile=/dev/null"]

    def _append_mux(self, cmd: list[str]) -> None:
        if not self.control_master:
            return
        cmd += ["-o", "ControlMaster=auto"]
        cmd += ["-o", f"ControlPersist={self.control_persist_s}s"]
        if self.control_path:
            cmd += ["-o", f"ControlPath={self.control_path}"]
        else:
            # Hash-based path avoids length limits.
            cmd += ["-o", "ControlPath=~/.ssh/cm-%C"]

    def base_cmd(self) -> list[str]:
        cmd: list[str] = [
            "ssh",
            "-p",
            str(self.port),
            "-o",
            f"ConnectTimeout={self.connect_timeout}",
            "-o",
            f"ServerAliveInterval={self.keepalive_interval}",
            "-o",
            f"ServerAliveCountMax={self.keepalive_count}",
        ]

        if self.batch_mode:
            cmd += ["-o", "BatchMode=yes"]
        if self.request_tty:
            cmd += ["-tt"]

        self._append_hostkey_policy(cmd)

        if self.identity:
            cmd += ["-i", str(self.identity)]
        if self.jump_host:
            cmd += ["-J", self.jump_host]

        self._append_mux(cmd)

        for opt in self.ssh_opts:
            cmd += ["-o", opt]

        cmd.append(self.target())
        return cmd

    def remote_cmd(self, argv: Sequence[str]) -> list[str]:
        args = list(argv)
        if self.sudo:
            args = ["sudo", "-n", "--", *args]
        return [*self.base_cmd(), "--", *args]

    def scp_src(self, remote_path: str) -> str:
        return f"{self.scp_target()}:{remote_path}"

    def scp_base_cmd(self) -> list[str]:
        cmd: list[str] = ["scp", "-P", str(self.port)]
        if self.identity:
            cmd += ["-i", str(self.identity)]
        if self.batch_mode:
            cmd += ["-o", "BatchMode=yes"]

        self._append_hostkey_policy(cmd)

        if self.jump_host:
            cmd += ["-o", f"ProxyJump={self.jump_host}"]

        # scp also benefits from multiplexing (it uses ssh under the hood).
        self._append_mux(cmd)

        for opt in self.ssh_opts:
            cmd += ["-o", opt]

        return cmd

    def describe(self) -> str:
        parts = [f"{self.user}@{self.host}:{self.port}"]
        if self.identity:
            parts.append(f"key={self.identity}")
        if self.jump_host:
            parts.append(f"via={self.jump_host}")
        if self.sudo:
            parts.append("sudo")
        if self.batch_mode:
            parts.append("batch")
        parts.append("hostkey=strict" if self.strict_host_key_checking else "hostkey=off")
        if self.accept_new_host_keys:
            parts.append("hostkey=accept-new(intent)")
        if self.control_master:
            parts.append("mux")
        return " ".join(parts)
