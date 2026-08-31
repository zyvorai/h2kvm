# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/sanity_checker.py
"""Pre-migration sanity checks and validation."""

from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

from h2kvm.libvirt.libvirt_utils import find_qemu_binary

from .structured_log import log_event
from .utils import U

if TYPE_CHECKING:
    import argparse
    import logging
    from collections.abc import Iterable, Sequence


class ExitCode(IntEnum):
    """Process exit codes returned by sanity checks."""

    OK = 0

    # generic failures
    BAD_ARGS = 2
    PERMISSION = 3
    DISK_SPACE = 4
    TOOLS_MISSING = 5
    GUESTFS = 6
    NETWORK = 7

    INTERNAL = 99


class ErrorKind:  # pylint: disable=too-few-public-methods
    """Namespace of SanityIssue.kind string constants (not a behavioral class)."""

    TOOLS = "tools"
    PERMISSION = "permission"
    DISK = "disk"
    GUESTFS = "guestfs"
    NETWORK = "network"
    BAD_ARGS = "bad_args"
    INTERNAL = "internal"


@dataclass
class SanityIssue:
    """A single sanity-check failure (kind + human-readable message)."""

    kind: str
    message: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.message}"


@dataclass
class SanityReport:
    """Aggregated results of all sanity checks: errors, warnings, and notes."""

    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)

    errors: list[SanityIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)

    checks_ran: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        """Return True if there are no missing required tools and no errors."""
        return not self.missing_required and not self.errors

    def add_error(self, kind: str, msg: str) -> None:
        """Record a sanity-check error of the given kind."""
        self.errors.append(SanityIssue(kind=kind, message=msg))

    def exit_code(self) -> int:  # pylint: disable=too-many-return-statements
        """
        Deterministic mapping of failures to exit codes.
        Preference: BAD_ARGS wins (fast feedback) then TOOLS then others.
        """
        if self.ok():
            return int(ExitCode.OK)

        kinds = {e.kind for e in self.errors}
        if ErrorKind.BAD_ARGS in kinds:
            return int(ExitCode.BAD_ARGS)

        if self.missing_required:
            return int(ExitCode.TOOLS_MISSING)

        if ErrorKind.PERMISSION in kinds:
            return int(ExitCode.PERMISSION)
        if ErrorKind.DISK in kinds:
            return int(ExitCode.DISK_SPACE)
        if ErrorKind.GUESTFS in kinds:
            return int(ExitCode.GUESTFS)
        if ErrorKind.NETWORK in kinds:
            return int(ExitCode.NETWORK)

        return int(ExitCode.INTERNAL)

    def to_dict(self) -> dict[str, object]:
        """
        Machine-friendly representation (JSON-serializable).
        """
        return {
            "ok": self.ok(),
            "exit_code": self.exit_code(),
            "missing_required": list(self.missing_required),
            "missing_optional": list(self.missing_optional),
            "errors": [{"kind": e.kind, "message": e.message} for e in self.errors],
            "warnings": list(self.warnings),
            "notes": dict(self.notes),
            "checks_ran": list(self.checks_ran),
        }


class SanityChecker:
    """
    Sanity checks for h2kvm:
      - tool availability (required vs optional, conditional)
      - guestfs backend import + minimal init (when needed)
      - disk space estimate
      - permissions on output dir
      - optional network connectivity (for download/fetch workflows)
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.out_root = Path(getattr(args, "output_dir", ".")).expanduser().resolve()
        self.report = SanityReport()

        # record useful context
        self.report.notes["mode"] = str(getattr(args, "mode", "") or "default")
        self.report.notes["output_dir"] = str(self.out_root)

    # tiny helpers

    def _need(self, flag: str) -> bool:
        """Return True if args has flag and it evaluates truthy."""
        return bool(getattr(self.args, flag, False))

    def _add_warn(self, msg: str) -> None:
        self.report.warnings.append(msg)

    def _add_err(self, kind: str, msg: str) -> None:
        self.report.add_error(kind, msg)

    def _tool_missing(self, tool: str) -> bool:
        return U.which(tool) is None

    def _has_any_qemu(self) -> bool:
        """Check if any QEMU binary is available (Fedora, RHEL, or Debian paths)."""
        return Path(find_qemu_binary()).is_file()

    def _bytes(self, n: int) -> str:
        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        x = float(max(0, int(n)))
        for u in units:
            if x < 1024 or u == units[-1]:
                return f"{x:.2f} {u}" if u != "B" else f"{int(x)} {u}"
            x /= 1024
        return f"{x:.2f} B"

    def _is_tty(self) -> bool:
        try:
            return sys.stderr.isatty()
        except (OSError, ValueError):
            return False

    def _args_mode(self) -> str:
        return str(getattr(self.args, "mode", "") or "")

    # network policy

    def _wants_network_check(self) -> bool:
        """
        Decide whether to *run* the network check.
        """
        if self._need("skip_sanity_net") or self._need("skip_network_check"):
            return False
        return self._args_mode() in ("fetch", "fetch-and-fix", "remote") or self._need("download")

    def _network_required(self) -> bool:
        """
        Decide whether a network failure should be ERROR or WARNING.
        Policy: fetch-like modes require network by default.
        Override knobs:
          - --net_optional forces WARNING
          - --net_required forces ERROR
        """
        if self._need("net_required"):
            self.report.notes["net_override"] = "required"
            return True
        if self._need("net_optional"):
            self.report.notes["net_override"] = "optional (user override)"
            return False
        return self._args_mode() in ("fetch", "fetch-and-fix", "remote") or self._need("download")

    # guestfs policy

    def _needs_guestfs(self) -> bool:
        """
        Require guestfs only when we intend to mount/modify guest filesystems.
        """
        if self._need("skip_guestfs_check") or self._need("no_guestfs_check"):
            return False

        if (
            self._need("fix")
            or self._need("offline_fix")
            or self._need("inject_drivers")
            or self._need("repair")
        ):
            return True

        mode = self._args_mode()
        if mode in ("fix", "offline-fix", "windows-fix", "linux-fix", "fetch-and-fix"):
            return True

        if getattr(self.args, "dry_run", False):
            return False

        return False

    def _same_filesystem(self, a: Path, b: Path) -> bool | None:
        """
        True if a and b are on the same filesystem (st_dev).
        Returns None if we cannot determine.
        """
        try:
            a_dev = Path(a).stat().st_dev
            b_dev = Path(b).stat().st_dev
            return a_dev == b_dev
        except OSError:
            return None

    # argument validation (lightweight)

    def check_args(self) -> None:
        """Validate lightweight argument invariants (output_dir, fetch-mode host)."""
        self.report.checks_ran.append("args")

        # output_dir basic sanity
        try:
            _ = str(self.out_root)
        except (OSError, ValueError) as e:
            self._add_err(ErrorKind.BAD_ARGS, f"Invalid output_dir: {e!s}")
            return

        # fetch-like modes need a host (best-effort: support common arg names)
        mode = self._args_mode()
        if mode in ("fetch", "fetch-and-fix", "remote"):
            host = (
                getattr(self.args, "host", None)
                or getattr(self.args, "esxi_host", None)
                or getattr(self.args, "remote_host", None)
            )
            if not host:
                self._add_err(
                    ErrorKind.BAD_ARGS, f"Mode '{mode}' requires a host (--host/--esxi-host/--remote-host)"
                )

    # checks

    def check_tools(self) -> None:  # pylint: disable=too-many-branches
        """Check required/optional tool availability and (conditionally) guestfs init."""
        # Branches are inherent: one per mode-conditional tool requirement.
        self.report.checks_ran.append("tools")

        mode = self._args_mode()

        # Always required
        required_tools: list[str] = ["qemu-img"]

        # Optional baseline
        optional_tools: list[str] = ["sgdisk"]

        fetch_like = mode in ("fetch", "fetch-and-fix", "remote")
        if fetch_like:
            required_tools.extend(["ssh", "scp"])
            if not self._need("fetch_no_rsync"):
                required_tools.append("rsync")
                self.report.notes["fetch_rsync"] = "required (default)"
            else:
                optional_tools.append("rsync")
                self.report.notes["fetch_rsync"] = "optional (--fetch_no_rsync set)"

        if self._need("libvirt_test") or self._need("keep_domain"):
            required_tools.append("virsh")

        # FIX: do NOT require qemu-system-x86_64 just because --uefi is set.
        # Only require it when we're actually going to run a qemu-based boot test.
        # Check both qemu-system-x86_64 (Fedora/Debian) and qemu-kvm (RHEL/AlmaLinux).
        if self._need("qemu_test"):
            if not self._has_any_qemu():
                required_tools.append("qemu-system-x86_64")
        elif self._need("uefi"):
            if not self._has_any_qemu():
                optional_tools.append("qemu-system-x86_64")

        # record for debugging
        self.report.notes["required_tools"] = ", ".join(sorted(set(required_tools)))
        self.report.notes["optional_tools"] = ", ".join(sorted(set(optional_tools)))

        missing_required = [t for t in sorted(set(required_tools)) if self._tool_missing(t)]
        missing_optional = [t for t in sorted(set(optional_tools)) if self._tool_missing(t)]

        self.report.missing_required.extend(missing_required)
        self.report.missing_optional.extend(missing_optional)

        if missing_required:
            install_hint = " ".join(missing_required)
            self._add_err(
                ErrorKind.TOOLS,
                f"Missing required tools: {', '.join(missing_required)}\n"
                f"    Install with: dnf install {install_hint}  (Fedora/RHEL)\n"
                f"                  apt install {install_hint}  (Debian/Ubuntu)",
            )

        if missing_optional:
            self._add_warn(f"Missing optional tools: {', '.join(missing_optional)}")

        # stop early if required tools are missing (avoid extra noise)
        if missing_required:
            self.report.notes["guestfs"] = "SKIPPED (required tools missing)"
            return

        # guestfs is conditional
        if not self._needs_guestfs():
            self.report.notes["guestfs"] = "SKIPPED (not needed for this run)"
            return

        try:
            # Deliberately lazy: guestfs_factory pulls in the heavy/optional guestfs backend,
            # which most sanity-check runs (guestfs not needed) should not have to import.
            from .guestfs_factory import create_guestfs  # pylint: disable=import-outside-toplevel

            g = create_guestfs(python_return_dict=True, backend="guestkit")
            g.set_trace(0)
            g.close()
            self.report.notes["guestfs"] = "OK (GuestKit backend)"
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Backend init can fail in many ways (import, subprocess, runtime); this is a
            # best-effort sanity check that must report a clean error, not crash the run.
            self._add_err(
                ErrorKind.GUESTFS,
                f"Disk inspection backend initialization failed: {e!s}\n"
                f"    The GuestKit backend requires qemu-img and qemu-nbd "
                f"(and pip install hypersdk-guestkit or pip install -e ~/tt/guestkit).\n"
                f"    Install host tools: dnf install qemu-img qemu-nbd  (Fedora/RHEL)\n"
                f"    If offline fixes are not needed, use: --skip-guestfs-check",
            )

    def _iter_input_paths(self) -> Iterable[Path]:
        disks = getattr(self.args, "disks", None)
        if disks:
            for d in disks:
                if d:
                    yield Path(d)

        for key in ("vmdk", "input", "image", "src", "source"):
            v = getattr(self.args, key, None)
            if v:
                yield Path(v)

    def _dir_size_bytes(self, root: Path, max_files: int = 20000) -> tuple[int | None, str | None]:
        """
        Best-effort directory sizing (bounded).
        Returns (size_bytes, note). If too large/unknown, returns (None, note).
        """
        try:
            total = 0
            count = 0
            for dp, _, files in os.walk(root):
                for fn in files:
                    count += 1
                    if count > max_files:
                        return None, f"directory size unknown (>{max_files} files)"
                    p = Path(dp) / fn
                    try:
                        total += p.stat().st_size
                    except OSError:
                        continue
            return total, None
        except OSError as e:
            return None, f"directory size failed: {e!s}"

    def _sum_existing_sizes(self, paths: Sequence[Path]) -> tuple[int, bool, list[str]]:
        total = 0
        missing: list[str] = []
        unknown = False

        for p in paths:
            try:
                pp = p.expanduser()
                if not pp.exists():
                    missing.append(str(pp))
                    unknown = True
                    continue

                if pp.is_file():
                    total += pp.stat().st_size
                    continue

                if pp.is_dir():
                    sz, note = self._dir_size_bytes(pp)
                    if sz is None:
                        unknown = True
                        self._add_warn(f"Input dir size unknown for {pp}: {note or 'unknown'}")
                    else:
                        total += sz
                    continue

                unknown = True
                self._add_warn(f"Input path not a regular file/dir (size unknown): {pp}")

            except OSError:
                unknown = True

        return total, unknown, missing

    def check_disk_space(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self,
    ) -> None:
        """Estimate required free space for the run and compare against actual free space.

        Combines several independent policy knobs (flatten/backup/stage/qcow2 conversion)
        into one model; splitting would scatter that model across helpers.
        """
        self.report.checks_ran.append("disk")

        if self._need("skip_sanity_disk") or self._need("skip_disk_check"):
            self.report.notes["disk_space"] = "SKIPPED (flagged)"
            return

        if getattr(self.args, "dry_run", False):
            self.report.notes["disk_space"] = "SKIPPED (dry-run)"
            self.report.notes["dry_run"] = "yes"
            return

        try:
            self.out_root.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(self.out_root)
            free_bytes = int(usage.free)

            inputs = list(dict.fromkeys([p.expanduser() for p in self._iter_input_paths()]))
            known_bytes, unknown, missing_inputs = self._sum_existing_sizes(inputs)

            # more paranoid disk model + dynamic slack for large inputs
            factor_out = 1.10
            factor_tmp = 1.10

            to_qcow2 = bool(getattr(self.args, "to_qcow2", False))
            if to_qcow2:
                factor_out = 1.20
                factor_tmp = 1.50

            if self._need("flatten"):
                factor_tmp += 1.00

            if self._need("backup") or self._need("keep_work") or self._need("keep_original"):
                factor_tmp += 0.75

            if self._need("stage") or self._need("copy_input") or self._need("make_work_copy"):
                factor_tmp += 1.00

            # cap temp factor to avoid ridiculous false-negatives
            factor_tmp = min(factor_tmp, 3.00)

            unknown_pad = 1.0
            if unknown:
                unknown_pad = 1.25
                self.report.notes["disk_unknown_pad"] = "1.25x"

            slack_min = 2 * 1024**3
            slack_scaled = int(min(32 * 1024**3, known_bytes * 0.02))
            slack = slack_min + slack_scaled

            estimated_needed = int(max(0, known_bytes) * (factor_out + factor_tmp) * unknown_pad + slack)

            self.report.notes["disk_free"] = self._bytes(free_bytes)
            self.report.notes["disk_input_known"] = self._bytes(known_bytes)
            self.report.notes["disk_need_est"] = self._bytes(estimated_needed)
            self.report.notes["disk_model"] = (
                f"out={factor_out:.2f}, tmp={factor_tmp:.2f}, slack={self._bytes(slack)}"
            )
            if unknown:
                self.report.notes["disk_input_unknown"] = "yes"

            if missing_inputs:
                self._add_warn(
                    f"{len(missing_inputs)} input path(s) not found; disk estimate may be inaccurate"
                )

            workdir = getattr(self.args, "workdir", None)
            if workdir:
                try:
                    wd = Path(workdir).expanduser().resolve()
                    same = self._same_filesystem(wd, self.out_root)
                    if same is True:
                        self.report.notes["workdir_fs"] = "same as output_dir"
                    elif same is False:
                        self.report.notes["workdir_fs"] = "different from output_dir"
                        self._add_warn(
                            f"workdir is on a different filesystem ({wd}); disk estimate only covers output_dir"
                        )
                    else:
                        self._add_warn(
                            f"Could not determine filesystem relation for workdir ({wd}) vs output_dir"
                        )
                except OSError:
                    pass

            if known_bytes <= 0:
                self._add_warn(
                    "Disk space check: could not size any inputs; not enforcing strict free-space gate"
                )
                return

            if free_bytes < estimated_needed:
                self._add_err(
                    ErrorKind.DISK,
                    f"Insufficient disk space: {self._bytes(free_bytes)} free, "
                    f"estimated needed {self._bytes(estimated_needed)} (known_input={self._bytes(known_bytes)})",
                )
                return

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort estimate spanning many operations; explicitly non-fatal by design.
            self._add_warn(f"Disk space check failed (non-fatal): {e!s}")

    def check_permissions(self) -> None:
        """Verify the output directory exists and is writable by the current user."""
        self.report.checks_ran.append("permissions")

        if self._need("skip_sanity_permissions") or self._need("skip_permissions_check"):
            self.report.notes["permissions"] = "SKIPPED (flagged)"
            return

        try:
            self.out_root.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".permtest_", dir=str(self.out_root))
            try:
                os.write(fd, b"ok\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            Path(tmp).unlink(missing_ok=True)
            self.report.notes["permissions"] = "OK"
        except OSError as e:
            self._add_err(
                ErrorKind.PERMISSION,
                f"Cannot write to output directory '{self.out_root}': {e!s}\n"
                f"    Ensure the directory exists and is writable by the current user.\n"
                f"    Try: sudo mkdir -p {self.out_root} && sudo chown $(whoami) {self.out_root}",
            )

    def check_network(self) -> None:
        """Optionally probe TCP connectivity to a host, for remote/fetch-like modes."""
        self.report.checks_ran.append("network")

        if not self._wants_network_check():
            self.report.notes["network"] = "SKIPPED"
            return

        host = getattr(self.args, "net_check_host", None) or "1.1.1.1"
        port = int(getattr(self.args, "net_check_port", None) or 53)
        timeout = float(getattr(self.args, "net_check_timeout", None) or 2.0)

        # tiny polish: record what we tried
        self.report.notes["network_target"] = f"{host}:{port}"
        self.report.notes["network_timeout_s"] = str(timeout)

        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
            self.report.notes["network"] = f"OK ({host}:{port})"
        except OSError as e:
            msg = (
                f"Network connectivity check failed (tcp {host}:{port}): {e!s}\n"
                f"    This is required for remote operations (fetch, vSphere, Azure).\n"
                f"    Verify network access, DNS resolution, and firewall rules.\n"
                f"    To skip this check: --skip-network-check"
            )
            if self._network_required():
                self._add_err(ErrorKind.NETWORK, msg)
            else:
                self._add_warn(msg)

    # orchestration

    def _run_checks(self, checks: Sequence[tuple[str, callable]]) -> None:
        for i, (name, fn) in enumerate(checks, 1):
            self.logger.info("Sanity check %d/%d: %s...", i, len(checks), name)
            fn()

    def _log_summary(self) -> None:
        # log once at end (avoid duplicates)
        log_event(
            "sanity_check_result",
            ok=self.report.ok(),
            checks_ran=self.report.checks_ran,
            error_count=len(self.report.errors),
            missing_required=self.report.missing_required,
            missing_optional=self.report.missing_optional,
        )
        if self.report.ok():
            self.logger.info("Sanity: OK")
            if self.report.missing_optional:
                self.logger.warning(
                    "Sanity: optional missing tools: %s\n"
                    "    Install with: dnf install %s  (or the equivalent for your distro)",
                    ", ".join(self.report.missing_optional),
                    " ".join(self.report.missing_optional),
                )
            if self.report.notes:
                self.logger.debug("Sanity notes: %s", self.report.notes)
            return

        self.logger.error("Sanity: FAILED (exit=%s)", self.report.exit_code())
        if self.report.missing_required:
            self.logger.error("Sanity: missing required tools: %s", ", ".join(self.report.missing_required))
        if self.report.missing_optional:
            self.logger.warning(
                "Sanity: missing optional tools: %s", ", ".join(self.report.missing_optional)
            )
        for e in self.report.errors:
            self.logger.error("Sanity error[%s]: %s", e.kind, e.message)
        for w in self.report.warnings:
            self.logger.warning("Sanity warn: %s", w)
        if self.report.notes:
            self.logger.debug("Sanity notes: %s", self.report.notes)

    def check_all(self) -> SanityReport:
        """Run all sanity checks in order, log a summary, and return the report."""
        checks: list[tuple[str, callable]] = [
            ("args", self.check_args),
            ("tools", self.check_tools),
            ("disk space", self.check_disk_space),
            ("permissions", self.check_permissions),
            ("network", self.check_network),
        ]

        self._run_checks(checks)
        self._log_summary()
        return self.report

    def die_if_failed(self) -> None:
        """
        Run checks if needed, and exit with structured exit codes.
        """
        if not self.report.checks_ran:
            self.check_all()

        if self.report.ok():
            return

        code = self.report.exit_code()

        # keep user-facing message short; details are already logged in summary
        if self.report.missing_required:
            U.die(
                self.logger,
                f"Sanity failed: missing required tools: {', '.join(self.report.missing_required)}",
                code,
            )

        headline = self.report.errors[0].message if self.report.errors else "Sanity failed"
        U.die(self.logger, f"Sanity failed: {headline}", code)
