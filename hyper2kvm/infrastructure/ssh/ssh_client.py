# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""SSH client for remote VM operations and live migration tasks."""

# hyper2kvm/ssh/ssh_client.py
from __future__ import annotations

import posixpath
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.utils import U

if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence
    from pathlib import Path

    from .ssh_config import SSHConfig


@dataclass(frozen=True)
class SSHResult:
    rc: int
    stdout: str
    stderr: str
    argv: list[str]
    seconds: float


class SSHClient:
    """
    Minimal, production-safe SSH helper.

    """

    def __init__(self, logger: logging.Logger, cfg: SSHConfig):
        self.logger = logger
        self.cfg = cfg
        self.use_rsync = U.which("rsync") is not None

        # Defaults (can be extended via cfg.*)
        self._connect_timeout = int(getattr(cfg, "connect_timeout", 10) or 10)
        self._server_alive_interval = int(getattr(cfg, "server_alive_interval", 10) or 10)
        self._server_alive_count = int(getattr(cfg, "server_alive_count", 3) or 3)
        self._strict_host_key = str(
            getattr(cfg, "strict_host_key_checking", "accept-new") or "accept-new"
        )  # accept-new | yes | no

        # Retry policy (optional)
        self._retries = int(getattr(cfg, "retries", 0) or 0)
        self._retry_sleep = float(getattr(cfg, "retry_sleep", 1.0) or 1.0)

        # rsync policy (optional)
        self._rsync_partial_dir = str(
            getattr(cfg, "rsync_partial_dir", ".rsync-partial") or ".rsync-partial"
        )
        self._rsync_append_verify = bool(getattr(cfg, "rsync_append_verify", False))
        self._ensure_remote_dir = bool(getattr(cfg, "ensure_remote_dir", True))

    # argv builders

    def _common(self) -> list[str]:
        opts: list[str] = []

        # When password auth is used, disable BatchMode so sshpass can work
        if not getattr(self.cfg, "password", None):
            opts += ["-o", "BatchMode=yes"]

        opts += [
            "-o",
            f"ConnectTimeout={self._connect_timeout}",
            "-o",
            f"ServerAliveInterval={self._server_alive_interval}",
            "-o",
            f"ServerAliveCountMax={self._server_alive_count}",
            "-o",
            f"StrictHostKeyChecking={self._strict_host_key}",
        ]

        # Optional: keep known_hosts separate per tool-run if user config provides it
        known_hosts = getattr(self.cfg, "known_hosts_file", None)
        if known_hosts:
            opts += ["-o", f"UserKnownHostsFile={known_hosts}"]

        if self.cfg.identity:
            opts += ["-i", self.cfg.identity]

        if self.cfg.ssh_opts:
            opts += list(self.cfg.ssh_opts)

        return opts

    def _sshpass_prefix(self) -> list[str]:
        """Prepend sshpass if password auth is configured."""
        pw = getattr(self.cfg, "password", None)
        if not pw:
            return []
        return ["sshpass", "-e"]

    def _ssh_args(self) -> list[str]:
        return ["-p", str(self.cfg.port), *self._common()]

    def _scp_args(self) -> list[str]:
        # -p preserves times
        return ["-P", str(self.cfg.port), "-p", *self._common()]

    def _rsync_args(self) -> list[str]:
        # rsync over ssh; prefer resume-friendly behavior for large images/artifacts
        shell_parts: list[str] = ["ssh", *self._common()]
        if self.cfg.port != 22:
            shell_parts += ["-p", str(self.cfg.port)]

        args: list[str] = [
            "-a",
            "-H",
            "--numeric-ids",
            "--info=progress2",
            "--partial",
            f"--partial-dir={self._rsync_partial_dir}",
            "--inplace",
            "-e",
            " ".join(shlex.quote(x) for x in shell_parts),
        ]

        # When resuming large files, --append-verify can be safer than plain --inplace for some workflows.
        if self._rsync_append_verify:
            # NOTE: --append-verify implies append semantics; only enable if your use-case fits.
            args += ["--append-verify"]

        return args

    # command helpers

    def _target(self) -> str:
        return f"{self.cfg.user}@{self.cfg.host}"

    def _maybe_sudo(self, cmd: str) -> str:
        if not getattr(self.cfg, "sudo", False):
            return cmd
        pw = getattr(self.cfg, "password", None)
        if pw:
            # Use sudo -S to read password from stdin (for sshpass-based auth)
            return f"echo {shlex.quote(pw)} | sudo -S -- sh -lc {shlex.quote(cmd)}"
        return f"sudo -n -- sh -lc {shlex.quote(cmd)}"

    def _remote_sh(self, cmd: str) -> str:
        """
        Wrap remote command so it runs under POSIX sh -lc with proper quoting.
        This prevents issues where ssh remote gets a command with spaces/quotes,
        and different shells interpret it oddly.
        """
        return f"sh -lc {shlex.quote(cmd)}"

    def _run_local(
        self,
        argv: Sequence[str],
        *,
        capture: bool,
        timeout: int | None,
    ) -> SSHResult:
        """
        Execute a local ssh/scp/rsync command. Never raises on rc!=0.
        (Timeout exceptions may still raise from U.run_cmd depending on its implementation.)
        """
        # Set SSHPASS env var if password auth is configured
        env = None
        pw = getattr(self.cfg, "password", None)
        if pw:
            import os

            env = os.environ.copy()
            env["SSHPASS"] = pw

        t0 = time.monotonic()
        cp = U.run_cmd(self.logger, list(argv), check=False, capture=capture, timeout=timeout, env=env)
        dt = time.monotonic() - t0
        return SSHResult(
            rc=int(getattr(cp, "returncode", 0) or 0),
            stdout=(cp.stdout or "") if capture else "",
            stderr=(cp.stderr or "") if capture else "",
            argv=list(argv),
            seconds=dt,
        )

    def _looks_transient_ssh(self, res: SSHResult | None, exc: BaseException | None) -> bool:
        """
        Decide whether to retry.

        We retry only on connection/transport-ish failures (ssh exit 255 or common SSH transport errors),
        not on normal remote command failures (rc 1/2/etc).
        """
        if isinstance(exc, subprocess.TimeoutExpired):
            return True

        if res is None:
            return False

        if res.rc == 255:
            return True

        s = (res.stderr or "").lower()
        transient_markers = [
            "connection timed out",
            "connection refused",
            "no route to host",
            "network is unreachable",
            "could not resolve hostname",
            "temporary failure in name resolution",
            "kex_exchange_identification",
            "connection reset by peer",
            "broken pipe",
            "connection closed",
        ]
        return any(m in s for m in transient_markers)

    def _raise_on_failure(self, res: SSHResult, desc: str) -> None:
        if res.rc == 0:
            return
        # Provide a compact error; keep stderr (often contains the real story).
        msg = (
            f"{desc} failed (rc={res.rc}, {res.seconds:.2f}s)\n"
            f"argv: {res.argv}\n"
            f"stderr: {(res.stderr or '').strip()}"
        ).strip()
        raise subprocess.CalledProcessError(res.rc, res.argv, output=res.stdout, stderr=msg)

    # public API

    def run(
        self,
        cmd: str,
        *,
        capture: bool = True,
        timeout: int | None = None,
        check: bool = True,
    ) -> SSHResult:
        """
        Run a command on the remote host.

        - Uses sh -lc quoting to avoid remote shell gotchas
        - Optional retries (cfg.retries) ONLY for transient/transport failures
        - Returns SSHResult with rc/stdout/stderr/duration
        - If check=True, raises CalledProcessError on rc!=0
        """
        raw = self._maybe_sudo(cmd)
        remote = self._remote_sh(raw)
        argv = [*self._sshpass_prefix(), "ssh", *self._ssh_args(), self._target(), remote]

        attempts = 1 + self._retries
        last_res: SSHResult | None = None
        last_exc: BaseException | None = None

        for attempt in range(1, attempts + 1):
            try:
                res = self._run_local(argv, capture=capture, timeout=timeout)
                last_res = res

                # Retry only on transport-ish failures
                if attempt < attempts and self._looks_transient_ssh(res, None):
                    self.logger.warning(
                        f"SSH transport issue (attempt {attempt}/{attempts}, rc={res.rc}); "
                        f"retrying in {self._retry_sleep:.1f}s"
                    )
                    time.sleep(self._retry_sleep)
                    continue

                if check:
                    self._raise_on_failure(res, "ssh")
                return res

            except BaseException as e:
                last_exc = e
                # If the exception itself looks transient (e.g. timeout), retry. Otherwise raise.
                if attempt < attempts and self._looks_transient_ssh(last_res, e):
                    self.logger.warning(
                        f"SSH exception (attempt {attempt}/{attempts}); retrying in {self._retry_sleep:.1f}s: {e}"
                    )
                    time.sleep(self._retry_sleep)
                    continue
                raise

        # If we fall through (shouldn't), raise the last exception or failure.
        if last_exc:
            raise last_exc
        if last_res:
            if check:
                self._raise_on_failure(last_res, "ssh")
            return last_res
        raise RuntimeError(
            "SSH command completed without producing a result or error. "
            "This is an unexpected internal condition — please report it with your logs."
        )

    def ssh(self, cmd: str, *, capture: bool = True, timeout: int | None = None) -> str:
        """Backwards-compatible: returns stdout string, raises on failure."""
        res = self.run(cmd, capture=capture, timeout=timeout, check=True)
        return res.stdout.strip()

    def check(self) -> None:
        out = self.ssh("echo OK", timeout=10).strip()
        if out != "OK":
            U.die(
                self.logger,
                f"SSH connectivity check failed (received: {out!r}).\n"
                f"Verify SSH access to {self.cfg.user}@{self.cfg.host}:{self.cfg.port}:\n"
                f"  1. Test manually: ssh -p {self.cfg.port} {self.cfg.user}@{self.cfg.host} echo OK\n"
                "  2. Check SSH key is authorized on the remote host\n"
                "  3. Ensure sshd is running on the target\n"
                "  4. Check firewall allows port " + str(self.cfg.port),
                1,
            )
        self.logger.debug("SSH connectivity OK")

    def scp_from(self, remote: str, local: Path) -> None:
        U.ensure_dir(local.parent)
        remote_spec = f"{self._target()}:{remote}"

        if self.use_rsync:
            argv = ["rsync", *self._rsync_args(), remote_spec, str(local)]
        else:
            argv = [*self._sshpass_prefix(), "scp", *self._scp_args(), remote_spec, str(local)]

        res = self._run_local(argv, capture=False, timeout=None)
        self._raise_on_failure(res, "copy (from)")
        self.logger.info(f"Copied {remote} -> {local}")

    def scp_to(self, local: Path, remote: str) -> None:
        remote_spec = f"{self._target()}:{remote}"

        # Best-effort: create remote parent dir (common failure mode in automation)
        if self._ensure_remote_dir:
            parent = posixpath.dirname(remote.rstrip("/"))
            if parent and parent not in (".", "/"):
                self.mkdir_p(parent)

        if self.use_rsync:
            argv = ["rsync", *self._rsync_args(), str(local), remote_spec]
        else:
            argv = [*self._sshpass_prefix(), "scp", *self._scp_args(), str(local), remote_spec]

        res = self._run_local(argv, capture=False, timeout=None)
        self._raise_on_failure(res, "copy (to)")
        self.logger.info(f"Copied {local} -> {remote}")

    # safer remote probes (argument-based)

    def _probe(self, script: str, arg1: str, *, timeout: int = 10) -> str:
        """
        Run a small POSIX sh script with a single positional argument ($1).
        Returns stdout (no-throw for rc!=0; scripts should print deterministically).
        """
        payload = f"sh -lc {shlex.quote(script)} -- {shlex.quote(arg1)}"
        res = self.run(payload, capture=True, timeout=timeout, check=False)
        return (res.stdout or "").strip()

    def exists(self, remote: str) -> bool:
        # Deterministic print; never throws for normal "false"
        out = self._probe('if [ -e "$1" ]; then printf 1; else printf 0; fi', remote)
        return out == "1"

    def is_file(self, remote: str) -> bool:
        out = self._probe('if [ -f "$1" ]; then printf 1; else printf 0; fi', remote)
        return out == "1"

    def is_dir(self, remote: str) -> bool:
        out = self._probe('if [ -d "$1" ]; then printf 1; else printf 0; fi', remote)
        return out == "1"

    def mkdir_p(self, remote_dir: str) -> None:
        # Use positional arg to avoid interpolation pitfalls
        payload = 'mkdir -p -- "$1"'
        cmd = f"sh -lc {shlex.quote(payload)} -- {shlex.quote(remote_dir)}"
        res = self.run(cmd, capture=False, timeout=30, check=False)
        self._raise_on_failure(res, "mkdir")

    def rm_rf(self, remote_path: str) -> None:
        payload = 'rm -rf -- "$1"'
        cmd = f"sh -lc {shlex.quote(payload)} -- {shlex.quote(remote_path)}"
        res = self.run(cmd, capture=False, timeout=60, check=False)
        self._raise_on_failure(res, "rm")

    def read_text(self, remote: str, *, max_bytes: int = 4 * 1024 * 1024) -> str:
        """
        Read remote file content safely (bounded).
        Uses head -c (if available); fallback to dd.
        Never raises on content-read failure (returns "" for missing/unreadable).
        """
        n = int(max_bytes)
        script = (
            'p="$1"; n="$2"; '
            '(head -c "$n" "$p" 2>/dev/null || dd if="$p" bs=1 count="$n" 2>/dev/null) || true'
        )

        # Two-arg call: we still keep it simple by embedding $2 as a quoted literal
        cmd = f"sh -lc {shlex.quote(script)} -- {shlex.quote(remote)} {shlex.quote(str(n))}"
        res = self.run(cmd, capture=True, timeout=30, check=False)
        return (res.stdout or "").rstrip("\n")
