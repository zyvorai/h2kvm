# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/validation_suite.py
# pylint: disable=too-many-lines  # cohesive validation-runner: spec/result types + sequential/subprocess/parallel execution
"""Comprehensive validation suite for pre/post migration checks."""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import pickle
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from hyper2kvm.core.utils import effective_cpu_count

if TYPE_CHECKING:
    import logging

# Types

CheckFunc = Callable[[dict[str, Any]], Any]
SkipIfFunc = Callable[[dict[str, Any]], bool]
ContextSanitizer = Callable[[dict[str, Any]], dict[str, Any]]


class SupportsRichConsole(Protocol):  # pylint: disable=too-few-public-methods  # minimal structural protocol, intentionally single-method
    """Structural protocol for a rich-like Console, so we don't hard-depend on rich's Console type."""

    def print(self, *args: Any, **kwargs: Any) -> Any:
        """Print to the console (mirrors rich.console.Console.print's signature)."""


# Exit codes (CLI-friendly)


class ExitCodes:  # pylint: disable=too-few-public-methods  # constants namespace + one classifier method, not meant to grow
    """
    Structured exit codes for shell/CI/systemd.

      0 = all ok
      1 = failures present (non-critical only)
      2 = critical failures present
      3 = suite internal error (runner crashed)
      4 = invalid config / misuse (e.g., no checks)
    """

    OK = 0
    FAIL = 1
    CRITICAL = 2
    INTERNAL = 3
    INVALID = 4

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> int:
        """Classify a run_all() result payload into one of the structured exit codes above."""
        if not isinstance(payload, dict):
            return ExitCodes.INTERNAL
        stats = payload.get("stats") or {}
        total = int(stats.get("total", 0) or 0)
        if total <= 0:
            return ExitCodes.INVALID
        if payload.get("failed_critical", False):
            return ExitCodes.CRITICAL
        ok = bool(payload.get("ok", False))
        return ExitCodes.OK if ok else ExitCodes.FAIL


# Spec + result


@dataclass
class CheckSpec:  # pylint: disable=too-many-instance-attributes  # dataclass models many independent execution/retry/safety knobs
    """
    A single validation check.

    Timeouts:
      - If timeout_s is set and the check is run in a subprocess, timeout is HARD:
        the child process is terminated by the parent.
      - If timeout_s is set but the check runs in-process, timeout is SOFT:
        we mark it failed if it exceeded the budget.

    Subprocess mode requirements:
      - spec.func must be pickleable (top-level functions are safest).
      - context must be pickleable after sanitization/narrowing.

    Dependencies:
      - depends_on lists check names that must have PASSED (not skipped) for this check to run.
        If a dependency failed => skip_reason=dependency_failed:<name>
        If a dependency was skipped => skip_reason=dependency_skipped:<name>

    Retries:
      - retries > 0 repeats the check if it fails. Attempts count is recorded.
        (By default retries apply to non-critical checks; can be overridden by retry_critical.)

    Parallelism:
      - If tagged "parallel_safe" and suite parallelism is enabled, this check may run
        concurrently in its own process (never threads). Hard timeouts are enforced by the parent
        killing that process when timeout expires (no nested multiprocessing).
    """

    name: str
    func: CheckFunc

    # semantics
    critical: bool = False
    description: str | None = None
    tags: list[str] = field(default_factory=list)

    # execution controls
    timeout_s: float | None = None  # hard in subprocess, soft in-process
    run_in_process: bool = False  # prefer subprocess
    skip_if: SkipIfFunc | None = None  # extra skip predicate
    depends_on: list[str] = field(default_factory=list)

    # reliability controls
    retries: int = 0
    retry_delay_s: float = 0.0
    retry_backoff: float = 1.0
    retry_critical: bool = False

    # safety controls
    # structured shrinking knobs (keeps shape)
    max_depth: int = 5
    max_list_items: int = 50
    max_dict_items: int = 50
    max_string_len: int = 4000
    # final safeguard cap (repr)
    max_result_repr_len: int = 20000

    # redaction
    redact_keys: list[str] = field(default_factory=list)  # extra per-check redact keys


@dataclass
class CheckResult:  # pylint: disable=too-many-instance-attributes  # dataclass models many independent result/meta/retry fields
    """Outcome of running a single CheckSpec: payload, timing, and skip/retry/mode metadata."""

    name: str
    passed: bool
    critical: bool
    duration_s: float

    # payload
    result: Any = None
    error: str | None = None
    traceback: str | None = None

    # meta
    skipped: bool = False
    skip_reason: str | None = None
    tags: list[str] = field(default_factory=list)
    description: str | None = None
    timed_out: bool = False
    terminated: bool = False
    mode: str = "inprocess"  # "inprocess" | "subprocess" | "parallel" | "skipped"

    # retry/meta
    attempts: int = 1
    result_truncated: bool = False


# Small helpers: redaction + structured shrinking + caps


def _is_mapping(x: Any) -> bool:
    return isinstance(x, dict)


def _is_sequence(x: Any) -> bool:
    return isinstance(x, (list, tuple))


def _redact_in_obj(obj: Any, redact_tokens: set[str]) -> Any:
    """
    Best-effort recursive redaction.
    Redacts if any token appears as a substring in the key (case-insensitive).
    """
    try:
        if _is_mapping(obj):
            out: dict[Any, Any] = {}
            for k, v in obj.items():
                key_s = str(k).lower()
                if any(tok in key_s for tok in redact_tokens):
                    out[k] = "***REDACTED***"
                else:
                    out[k] = _redact_in_obj(v, redact_tokens)
            return out
        if _is_sequence(obj):
            return obj.__class__(_redact_in_obj(v, redact_tokens) for v in obj)  # type: ignore[misc]
        return obj
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort redaction over arbitrary check-result objects, must not crash the suite
        return obj


def _shrink_obj(  # pylint: disable=too-many-arguments,too-many-return-statements,too-many-branches  # structured shrink must handle str/mapping/sequence/scalar cases with independent caps
    obj: Any,
    *,
    depth: int,
    max_depth: int,
    max_list_items: int,
    max_dict_items: int,
    max_string_len: int,
) -> tuple[Any, bool]:
    """
    Structured shrink: preserves shape where possible.
    Returns (shrunk_obj, truncated_flag).
    """
    truncated = False

    if depth >= max_depth:
        # stop descending; keep a hint but don't explode
        try:
            return {"_truncated": True, "_repr": repr(obj)[:200]}, True
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort repr of an arbitrary object, must not crash the suite
            return {"_truncated": True, "_repr": "<unreprable>"}, True

    try:
        if isinstance(obj, str):
            if len(obj) > max_string_len:
                return obj[: max_string_len - 3] + "...", True
            return obj, False

        if _is_mapping(obj):
            out: dict[Any, Any] = {}
            items = list(obj.items())
            if len(items) > max_dict_items:
                truncated = True
                items = items[:max_dict_items]
            for k, v in items:
                vv, tt = _shrink_obj(
                    v,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_list_items=max_list_items,
                    max_dict_items=max_dict_items,
                    max_string_len=max_string_len,
                )
                if tt:
                    truncated = True
                out[k] = vv
            if truncated:
                out["_truncated_dict_items"] = True
            return out, truncated

        if _is_sequence(obj):
            seq = list(obj)
            if len(seq) > max_list_items:
                truncated = True
                seq = seq[:max_list_items]
            out_list: list[Any] = []
            for v in seq:
                vv, tt = _shrink_obj(
                    v,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_list_items=max_list_items,
                    max_dict_items=max_dict_items,
                    max_string_len=max_string_len,
                )
                if tt:
                    truncated = True
                out_list.append(vv)
            if truncated:
                out_list.append({"_truncated_list_items": True})
            # preserve tuple/list type roughly
            return (obj.__class__(out_list) if isinstance(obj, tuple) else out_list), truncated

        # scalars / unknown objects
        return obj, False

    except Exception:  # pylint: disable=broad-exception-caught  # structured shrink must never raise on arbitrary check-result content
        # last resort
        try:
            return {"_truncated": True, "_repr": repr(obj)[:200]}, True
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort repr of an arbitrary object, must not crash the suite
            return {"_truncated": True, "_repr": "<unreprable>"}, True


def _cap_repr(obj: Any, max_repr_len: int) -> tuple[Any, bool]:
    """
    Final safeguard: cap repr if needed.
    """
    if max_repr_len <= 0:
        return obj, False
    try:
        s = repr(obj)
        if len(s) <= max_repr_len:
            return obj, False
        preview = s[: max_repr_len - 3] + "..."
        return {"_truncated_repr": preview}, True
    except Exception:  # pylint: disable=broad-exception-caught  # final safeguard cap, must never raise on arbitrary result content
        return {"_truncated_repr": "<unreprable-result>"}, True


def _sleep_with_backoff(base_delay: float, backoff: float, attempt_idx: int) -> None:
    if base_delay <= 0:
        return
    mult = 1.0
    if attempt_idx > 0 and backoff and backoff > 1.0:
        mult = backoff**attempt_idx
    time.sleep(base_delay * mult)


# Multiprocessing child plumbing (top-level for spawn)


def _child_run_check(func: CheckFunc, context: dict[str, Any], conn: Any) -> None:
    """
    Child process entry: run func(context), send ("ok", result) or ("err", (err, tb)).
    One-shot Pipe.
    """
    try:
        res = func(context)
        conn.send(("ok", res))
    except Exception as e:  # pylint: disable=broad-exception-caught  # must catch any error from an arbitrary check function and report it, not crash the child
        tb = traceback.format_exc()
        conn.send(("err", (str(e), tb)))
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def _exitcode_hint(exitcode: int | None) -> str:
    if exitcode is None:
        return "exitcode=None"
    if exitcode < 0:
        return f"exitcode={exitcode} (signal={-exitcode})"
    return f"exitcode={exitcode}"


def _can_pickle(obj: Any) -> tuple[bool, str | None]:
    try:
        pickle.dumps(obj)
        return True, None
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort pickleability probe over arbitrary objects
        return False, str(e)


# Main suite


class ValidationSuite:
    """
    Process-first validation runner (no threads):

      - typed CheckSpec/CheckResult
      - per-check duration timing
      - skip support via context flags + per-check skip predicate
      - dependency-aware skipping (distinguishes skipped vs failed deps)
      - retries with backoff
      - per-check and global redaction + structured shrinking + result caps
      - subprocess execution for hard timeouts
      - process-based parallel execution for checks tagged "parallel_safe"
        (spawn-safe, no nested multiprocessing)
      - JSON-friendly output + stats (by tag + slowest, excluding skipped)
      - structured exit codes helper (ExitCodes.from_payload)

    Payload semantics:
      - ok == True only if *no checks failed* (critical or non-critical)
      - failed_critical reports whether any critical checks actually failed
      - stop_on_critical only affects how far we run, not what ok means
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        console: SupportsRichConsole | None = None,
        default_use_processes: bool = False,
        mp_start_method: str = "spawn",
        context_sanitizer: ContextSanitizer | None = None,
    ):
        self.logger = logger
        self.console = console
        self.checks: list[CheckSpec] = []
        self.default_use_processes = bool(default_use_processes)
        self.mp_start_method = mp_start_method
        self.context_sanitizer = context_sanitizer
        self._logged_mp_start_method = False

    def add_check(self, spec: CheckSpec) -> None:
        """
        Add a validation check using a CheckSpec object.

        Args:
            spec: Pre-configured CheckSpec object

        Example:
            suite = ValidationSuite()
            check = CheckSpec(
                name="cpu_count",
                func=check_cpu_count,
                critical=True,
                description="Verify CPU count matches expected value",
                tags=["hardware", "cpu"],
                timeout_s=10.0,
                retries=2,
            )
            suite.add_check(check)
        """
        self.checks.append(spec)

    # Skip + dependency logic

    def _should_skip(self, spec: CheckSpec, context: dict[str, Any]) -> tuple[bool, str | None]:
        # Supported skip mechanisms:
        #   context["skip_checks"] = {"name1", "name2"}
        #   context["skip_tags"]   = {"network", "slow"}
        skip_checks = set(context.get("skip_checks", []) or [])
        skip_tags = set(context.get("skip_tags", []) or [])

        if spec.name in skip_checks:
            return True, "user:skip_checks"
        if spec.tags and (set(spec.tags) & skip_tags):
            hit = next(iter(set(spec.tags) & skip_tags))
            return True, f"user:skip_tags:{hit}"
        if spec.skip_if is not None:
            try:
                if bool(spec.skip_if(context)):
                    return True, "skip_if:true"
            except Exception as e:  # pylint: disable=broad-exception-caught  # caller-supplied predicate, must not abort the suite
                self.logger.debug("skip_if predicate errored for %s: %s", spec.name, e)
        return False, None

    def _dependency_ok(
        self, spec: CheckSpec, results_json: dict[str, dict[str, Any]]
    ) -> tuple[bool, str | None]:
        if not spec.depends_on:
            return True, None
        for dep in spec.depends_on:
            dep_r = results_json.get(dep)
            if not dep_r:
                return False, f"dependency_missing:{dep}"
            if bool(dep_r.get("skipped", False)):
                return False, f"dependency_skipped:{dep}"
            if not bool(dep_r.get("passed", False)):
                return False, f"dependency_failed:{dep}"
        return True, None

    # Context narrowing/sanitization + redaction keys

    def _sanitize_context_for_child(
        self, context: dict[str, Any], *, allow_keys: Sequence[str] | None
    ) -> dict[str, Any]:
        ctx = context
        if allow_keys:
            out: dict[str, Any] = {}
            for k in allow_keys:
                if k in ctx:
                    out[k] = ctx[k]
            ctx = out

        if self.context_sanitizer is not None:
            try:
                ctx = self.context_sanitizer(ctx)
            except Exception as e:  # pylint: disable=broad-exception-caught  # caller-supplied sanitizer, must not abort the suite
                self.logger.debug("context_sanitizer errored: %s", e)

        return ctx

    def _effective_redact_tokens(self, spec: CheckSpec, context: dict[str, Any]) -> set[str]:
        base = {str(k).lower() for k in (context.get("redact_keys", []) or [])}
        extra = {str(k).lower() for k in (spec.redact_keys or [])}
        # sensible defaults
        base |= {
            "password",
            "passwd",
            "token",
            "secret",
            "apikey",
            "api_key",
            "authorization",
            "bearer",
            "cookie",
            "session",
        }
        return base | extra

    # Result post-processing

    def _postprocess_result(self, spec: CheckSpec, context: dict[str, Any], r: CheckResult) -> CheckResult:
        if r.skipped or (not r.passed):
            return r

        tokens = self._effective_redact_tokens(spec, context)
        redacted = _redact_in_obj(r.result, tokens)

        shrunk, trunc1 = _shrink_obj(
            redacted,
            depth=0,
            max_depth=spec.max_depth,
            max_list_items=spec.max_list_items,
            max_dict_items=spec.max_dict_items,
            max_string_len=spec.max_string_len,
        )
        capped, trunc2 = _cap_repr(shrunk, spec.max_result_repr_len)

        r.result = capped
        r.result_truncated = bool(trunc1 or trunc2)
        return r

    # Execution: in-process (soft timeout) + subprocess (hard timeout)

    def _run_check_inprocess_once(
        self, spec: CheckSpec, context: dict[str, Any], *, show_tracebacks: bool
    ) -> CheckResult:
        t0 = time.monotonic()
        try:
            out = spec.func(context)
            dur = time.monotonic() - t0

            if spec.timeout_s is not None and dur > spec.timeout_s:
                return CheckResult(
                    name=spec.name,
                    passed=False,
                    critical=spec.critical,
                    duration_s=dur,
                    error=f"Check exceeded soft timeout ({dur:.2f}s > {spec.timeout_s:.2f}s)",
                    timed_out=True,
                    mode="inprocess",
                    tags=list(spec.tags),
                    description=spec.description,
                )

            return CheckResult(
                name=spec.name,
                passed=True,
                critical=spec.critical,
                duration_s=dur,
                result=out,
                mode="inprocess",
                tags=list(spec.tags),
                description=spec.description,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught  # must catch any error from an arbitrary check func, report as failed, not crash the suite
            dur = time.monotonic() - t0
            tb = traceback.format_exc()
            return CheckResult(
                name=spec.name,
                passed=False,
                critical=spec.critical,
                duration_s=dur,
                error=str(e),
                traceback=(tb if show_tracebacks else None),
                mode="inprocess",
                tags=list(spec.tags),
                description=spec.description,
            )

    def _run_check_subprocess_once(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements  # hard-timeout subprocess execution: pickle checks, spawn, poll, collect result
        self,
        spec: CheckSpec,
        context: dict[str, Any],
        *,
        show_tracebacks: bool,
        strict_process_checks: bool,
        allow_context_keys: Sequence[str] | None,
        mode_override: str = "subprocess",
    ) -> CheckResult:
        t0 = time.monotonic()

        child_ctx = self._sanitize_context_for_child(context, allow_keys=allow_context_keys)

        ok_f, why_f = _can_pickle(spec.func)
        ok_c, why_c = _can_pickle(child_ctx)
        if not ok_f or not ok_c:
            bits = []
            if not ok_f:
                bits.append(f"func not pickleable: {why_f}")
            if not ok_c:
                bits.append(f"context not pickleable: {why_c}")
            msg = "; ".join(bits) or "cannot pickle for subprocess"

            if strict_process_checks:
                dur = time.monotonic() - t0
                return CheckResult(
                    name=spec.name,
                    passed=False,
                    critical=spec.critical,
                    duration_s=dur,
                    error=f"Cannot run in subprocess (strict mode): {msg}",
                    mode=mode_override,
                    tags=list(spec.tags),
                    description=spec.description,
                )
            raise RuntimeError(msg)

        try:
            ctx = mp.get_context(self.mp_start_method)
        except Exception:  # pylint: disable=broad-exception-caught  # unsupported start method on this platform, fall back to spawn
            ctx = mp.get_context("spawn")

        parent_conn, child_conn = ctx.Pipe(duplex=False)
        p = ctx.Process(target=_child_run_check, args=(spec.func, child_ctx, child_conn), daemon=True)
        p.start()

        timed_out = False
        terminated = False

        timeout = spec.timeout_s
        if timeout is None:
            p.join()
        else:
            p.join(timeout)

        if p.is_alive():
            timed_out = True
            terminated = True
            try:
                p.terminate()
            finally:
                p.join(2.0)

        dur = time.monotonic() - t0

        with contextlib.suppress(Exception):
            child_conn.close()

        if timed_out:
            with contextlib.suppress(Exception):
                parent_conn.close()
            return CheckResult(
                name=spec.name,
                passed=False,
                critical=spec.critical,
                duration_s=dur,
                error=f"Check timed out after {timeout:.2f}s",
                timed_out=True,
                terminated=terminated,
                mode=mode_override,
                tags=list(spec.tags),
                description=spec.description,
            )

        # not timed out => read result
        err_s: str | None = None
        tb_s: str | None = None
        result: Any = None
        passed = False

        try:
            if parent_conn.poll(0.0):
                kind, payload = parent_conn.recv()
            else:
                kind, payload = None, None
        except Exception as e:  # pylint: disable=broad-exception-caught  # child pipe may be closed/corrupted, must not crash the parent
            kind, payload = None, None
            err_s = f"Failed to read subprocess result: {e}"

        if kind == "ok":
            passed = True
            result = payload
        elif kind == "err":
            passed = False
            try:
                err_s, tb_s = payload
            except Exception:  # pylint: disable=broad-exception-caught  # defensive unpack of an untrusted child payload
                err_s = "Subprocess reported error, but payload malformed"
                tb_s = None
        else:
            passed = False
            if err_s is None:
                err_s = f"Check subprocess exited without result ({_exitcode_hint(p.exitcode)})"

        with contextlib.suppress(Exception):
            parent_conn.close()

        return CheckResult(
            name=spec.name,
            passed=passed,
            critical=spec.critical,
            duration_s=dur,
            result=result,
            error=err_s,
            traceback=(tb_s if show_tracebacks else None),
            mode=mode_override,
            tags=list(spec.tags),
            description=spec.description,
        )

    def _run_with_retries(self, spec: CheckSpec, exec_once: Callable[[], CheckResult]) -> CheckResult:
        max_attempts = 1 + max(0, int(spec.retries or 0))
        allow_retry = (not spec.critical) or bool(spec.retry_critical)

        last: CheckResult | None = None
        for attempts, i in enumerate(range(max_attempts), start=1):
            r = exec_once()
            r.attempts = attempts
            last = r

            if r.passed:
                return r
            if not allow_retry:
                return r
            if i >= max_attempts - 1:
                return r

            _sleep_with_backoff(spec.retry_delay_s, spec.retry_backoff, i)

        return last or CheckResult(
            name=spec.name, passed=False, critical=spec.critical, duration_s=0.0, error="unknown"
        )

    # Parallel scheduler (process-based, spawn-safe, no nested multiprocessing)

    @staticmethod
    def _is_parallel_candidate(spec: CheckSpec) -> bool:
        return "parallel_safe" in set(spec.tags or [])

    def _run_parallel_checks(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements  # spawn-safe process pool scheduler: dispatch, poll, timeout/retry, collect
        self,
        specs: list[CheckSpec],
        context: dict[str, Any],
        *,
        show_tracebacks: bool,
        strict_process_checks: bool,
        allow_context_keys: Sequence[str] | None,
        max_workers: int,
        use_hard_timeout: bool,
    ) -> dict[str, CheckResult]:
        """
        Run parallel-safe checks with bounded concurrency using processes directly.
        Hard timeouts enforced by killing the worker process.
        Retries handled by re-queuing.
        """
        if not specs:
            return {}

        # Pre-sanitize and pickle-check the worker context once.
        worker_ctx = self._sanitize_context_for_child(context, allow_keys=allow_context_keys)
        ok_ctx, why_ctx = _can_pickle(worker_ctx)
        if not ok_ctx:
            # Can't parallelize safely; caller should fallback sequentially.
            raise RuntimeError(
                f"Cannot run validation checks in parallel — the worker context contains "
                f"non-serializable objects ({why_ctx}). Falling back to sequential execution."
            )

        try:
            ctx = mp.get_context(self.mp_start_method)
        except Exception:  # pylint: disable=broad-exception-caught  # unsupported start method on this platform, fall back to spawn
            ctx = mp.get_context("spawn")

        # Task state
        pending: list[tuple[float, CheckSpec, int]] = []  # (ready_time, spec, attempt_index starting at 1)
        now = time.monotonic()
        for s in specs:
            pending.append((now, s, 1))

        running: dict[str, dict[str, Any]] = {}
        finished: dict[str, CheckResult] = {}

        def start_one(spec: CheckSpec, attempt: int) -> None:
            # One process per check attempt; parent enforces timeout by termination.
            # Note: if use_hard_timeout is False, we still run as a process here (parallel),
            # but no timeout enforcement beyond whatever the parent chooses to do.
            ok_f, why_f = _can_pickle(spec.func)
            if not ok_f:
                if strict_process_checks:
                    finished[spec.name] = CheckResult(
                        name=spec.name,
                        passed=False,
                        critical=spec.critical,
                        duration_s=0.0,
                        error=f"Cannot run parallel process (strict): func not pickleable: {why_f}",
                        mode="parallel",
                        tags=list(spec.tags),
                        description=spec.description,
                        attempts=attempt,
                    )
                    return
                # non-strict: fail with message (parallel mode can't fall back to in-process safely here)
                finished[spec.name] = CheckResult(
                    name=spec.name,
                    passed=False,
                    critical=spec.critical,
                    duration_s=0.0,
                    error=f"Cannot run parallel process: func not pickleable: {why_f}",
                    mode="parallel",
                    tags=list(spec.tags),
                    description=spec.description,
                    attempts=attempt,
                )
                return

            parent_conn, child_conn = ctx.Pipe(duplex=False)
            p = ctx.Process(target=_child_run_check, args=(spec.func, worker_ctx, child_conn), daemon=True)
            p.start()

            running[spec.name] = {
                "spec": spec,
                "proc": p,
                "conn": parent_conn,
                "child_conn": child_conn,
                "t0": time.monotonic(),
                "attempt": attempt,
            }

        def complete(name: str, r: CheckResult) -> None:
            finished[name] = r

        def can_retry(spec: CheckSpec, r: CheckResult, attempt: int) -> bool:
            if r.passed:
                return False
            if spec.critical and not spec.retry_critical:
                return False
            return attempt < (1 + max(0, int(spec.retries or 0)))

        # Main loop
        while pending or running:
            now = time.monotonic()

            # start as many as possible
            pending.sort(key=lambda x: x[0])
            while pending and len(running) < max_workers and pending[0][0] <= now:
                _, spec, attempt = pending.pop(0)
                if spec.name in finished:
                    continue
                start_one(spec, attempt)

            # poll running procs
            done_names: list[str] = []
            for name, st in list(running.items()):
                spec: CheckSpec = st["spec"]
                p: mp.Process = st["proc"]
                conn = st["conn"]
                child_conn = st["child_conn"]
                t0: float = st["t0"]
                attempt: int = st["attempt"]

                timeout = spec.timeout_s if use_hard_timeout else None
                elapsed = time.monotonic() - t0

                # timeout enforcement
                if timeout is not None and elapsed > timeout and p.is_alive():
                    try:
                        p.terminate()
                    finally:
                        p.join(2.0)
                    # close conns
                    with contextlib.suppress(Exception):
                        child_conn.close()
                    with contextlib.suppress(Exception):
                        conn.close()

                    r = CheckResult(
                        name=spec.name,
                        passed=False,
                        critical=spec.critical,
                        duration_s=elapsed,
                        error=f"Check timed out after {timeout:.2f}s",
                        timed_out=True,
                        terminated=True,
                        mode="parallel",
                        tags=list(spec.tags),
                        description=spec.description,
                        attempts=attempt,
                    )

                    if can_retry(spec, r, attempt):
                        # schedule retry
                        delay = spec.retry_delay_s * ((spec.retry_backoff or 1.0) ** max(0, attempt - 1))
                        pending.append((time.monotonic() + max(0.0, delay), spec, attempt + 1))
                    else:
                        complete(name, r)

                    done_names.append(name)
                    continue

                # finished?
                if not p.is_alive():
                    p.join(0.0)
                    # close child end
                    with contextlib.suppress(Exception):
                        child_conn.close()

                    result: Any = None
                    err_s: str | None = None
                    tb_s: str | None = None
                    passed = False

                    try:
                        if conn.poll(0.0):
                            kind, payload = conn.recv()
                        else:
                            kind, payload = None, None
                    except Exception as e:  # pylint: disable=broad-exception-caught  # child pipe may be closed/corrupted, must not crash the scheduler
                        kind, payload = None, None
                        err_s = f"Failed to read parallel result: {e}"

                    if kind == "ok":
                        passed = True
                        result = payload
                    elif kind == "err":
                        passed = False
                        try:
                            err_s, tb_s = payload
                        except Exception:  # pylint: disable=broad-exception-caught  # defensive unpack of an untrusted child payload
                            err_s = "Parallel worker reported error, payload malformed"
                    else:
                        passed = False
                        if err_s is None:
                            err_s = f"Parallel worker exited without result ({_exitcode_hint(p.exitcode)})"

                    with contextlib.suppress(Exception):
                        conn.close()

                    r = CheckResult(
                        name=spec.name,
                        passed=passed,
                        critical=spec.critical,
                        duration_s=elapsed,
                        result=result,
                        error=err_s,
                        traceback=(tb_s if show_tracebacks else None),
                        mode="parallel",
                        tags=list(spec.tags),
                        description=spec.description,
                        attempts=attempt,
                    )

                    if can_retry(spec, r, attempt):
                        delay = spec.retry_delay_s * ((spec.retry_backoff or 1.0) ** max(0, attempt - 1))
                        pending.append((time.monotonic() + max(0.0, delay), spec, attempt + 1))
                    else:
                        complete(name, r)

                    done_names.append(name)

            for name in done_names:
                running.pop(name, None)

            # avoid busy loop
            if not done_names:
                time.sleep(0.05)

        return finished

    # JSON serialization + stats

    @staticmethod
    def _result_to_json(r: CheckResult, *, show_tracebacks: bool) -> dict[str, Any]:
        d: dict[str, Any] = {
            "passed": bool(r.passed) and (not r.skipped),
            "critical": r.critical,
            "duration_s": round(r.duration_s, 3),
            "skipped": r.skipped,
            "skip_reason": r.skip_reason,
            "tags": list(r.tags),
            "timed_out": r.timed_out,
            "terminated": r.terminated,
            "mode": r.mode,
            "attempts": int(r.attempts or 1),
            "result_truncated": bool(r.result_truncated),
        }
        if r.description:
            d["description"] = r.description
        if not r.skipped and d["passed"]:
            d["result"] = r.result
        elif not r.skipped:
            d["error"] = r.error or "unknown error"
            if show_tracebacks and r.traceback:
                d["traceback"] = r.traceback
        return d

    def _compute_tag_stats(self, results_json: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for r in results_json.values():
            tags = r.get("tags") or []
            if not tags:
                tags = ["_untagged"]
            for t in tags:
                d = out.setdefault(
                    str(t), {"executed": 0, "passed": 0, "failed": 0, "skipped": 0, "total": 0}
                )
                d["total"] += 1
                if bool(r.get("skipped", False)):
                    d["skipped"] += 1
                else:
                    d["executed"] += 1
                    if bool(r.get("passed", False)):
                        d["passed"] += 1
                    else:
                        d["failed"] += 1
        return out

    def _compute_slowest(
        self, results_json: dict[str, dict[str, Any]], top_n: int = 10
    ) -> list[dict[str, Any]]:
        items: list[tuple[str, float, str]] = []
        for name, r in results_json.items():
            if bool(r.get("skipped", False)):
                continue
            try:
                dur = float(r.get("duration_s", 0.0) or 0.0)
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort cast of untrusted result data, must not crash the stats
                dur = 0.0
            mode = str(r.get("mode", "") or "")
            items.append((name, dur, mode))
        items.sort(key=lambda x: x[1], reverse=True)
        top_n = max(1, int(top_n or 10))
        return [{"name": n, "duration_s": round(d, 3), "mode": m} for (n, d, m) in items[:top_n]]

    # run_all() helper methods (complexity reduction)

    def _parse_run_config(
        self, context: dict[str, Any], use_processes: bool | None
    ) -> tuple[bool, bool, list[str] | None, list[str], bool, set[str]]:
        """Parse and validate run_all configuration from context."""
        use_procs = self.default_use_processes if use_processes is None else bool(use_processes)
        strict_process_checks = bool(context.get("strict_process_checks", False))

        allow_context_keys = context.get("process_context_keys")
        if allow_context_keys is not None and not isinstance(allow_context_keys, (list, tuple)):
            allow_context_keys = None

        missing_required = list(context.get("missing_required_tools", []) or [])
        fail_fast_missing = bool(context.get("fail_fast_on_missing_required_tools", True))
        expensive_tags = set(
            context.get("expensive_tags", ["expensive", "guestfs"]) or ["expensive", "guestfs"]
        )

        return (
            use_procs,
            strict_process_checks,
            allow_context_keys,
            missing_required,
            fail_fast_missing,
            expensive_tags,
        )

    def _log_mp_start_method(self) -> None:
        """Log multiprocessing start method once."""
        if self._logged_mp_start_method:
            return
        try:
            _ = mp.get_context(self.mp_start_method)
            method = self.mp_start_method
        except Exception:  # pylint: disable=broad-exception-caught  # unsupported start method on this platform, fall back to spawn
            method = "spawn"
        self.logger.debug("ValidationSuite multiprocessing start method: %s", method)
        self._logged_mp_start_method = True

    def _create_check_executor(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # each param is an independent execution-mode knob
        self,
        spec: CheckSpec,
        context: dict[str, Any],
        use_procs: bool,
        show_tracebacks: bool,
        strict_process_checks: bool,
        allow_context_keys: list[str] | None,
    ) -> Callable[[], CheckResult]:
        """Create executor function for a check (subprocess or in-process)."""
        run_sub = bool(spec.run_in_process) or (use_procs and spec.timeout_s is not None)

        def exec_once() -> CheckResult:
            if run_sub:
                return self._run_check_subprocess_once(
                    spec,
                    context,
                    show_tracebacks=show_tracebacks,
                    strict_process_checks=strict_process_checks,
                    allow_context_keys=allow_context_keys,
                    mode_override="subprocess",
                )
            return self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

        return exec_once

    def _should_run_check(
        self,
        spec: CheckSpec,
        context: dict[str, Any],
        results_json: dict[str, dict[str, Any]],
        missing_required: list[str],
        expensive_tags: set[str],
    ) -> tuple[bool, str]:
        """
        Determine if a check should run.

        Returns:
            (should_run, skip_reason)
        """
        if spec.name in results_json:
            return (False, "already_done")

        if missing_required and (set(spec.tags or []) & expensive_tags):
            return (False, "missing_required_tools:skip_expensive")

        sk, sk_reason = self._should_skip(spec, context)
        if sk:
            return (False, sk_reason or "skipped")

        dep_ok, dep_reason = self._dependency_ok(spec, results_json)
        if not dep_ok:
            return (False, dep_reason or "dependency_blocked")

        return (True, "")

    def _build_result_payload(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # each param is an independent summary-stat field
        self,
        total: int,
        passed_count: int,
        failed_count: int,
        skipped_count: int,
        failed_critical: bool,
        results_json: dict[str, dict[str, Any]],
        duration_s: float,
        top_slowest: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build final result payload with stats."""
        ok = failed_count == 0
        payload = {
            "ok": ok,
            "failed_critical": failed_critical,
            "results": results_json,
            "stats": {
                "total": total,
                "passed": passed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "duration_s": round(duration_s, 3),
                "by_tag": self._compute_tag_stats(results_json),
                "slowest": self._compute_slowest(results_json, top_n=top_slowest),
            },
        }
        if error:
            payload["error"] = error
        payload["exit_code"] = ExitCodes.from_payload(payload)
        return payload

    # Public API

    def run_all(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements  # main orchestration entry point: sequential + parallel phases, retries, stats
        self,
        context: dict[str, Any],
        *,
        stop_on_critical: bool = True,
        show_tracebacks: bool = False,
        log_summary: bool = True,
        use_processes: bool | None = None,
        parallel: bool = False,
        max_workers: int | None = None,
        top_slowest: int = 10,
    ) -> dict[str, Any]:
        """
        Returns JSON-friendly payload:
          {
            "ok": bool,
            "failed_critical": bool,
            "results": {name: {...}},
            "stats": {...},
            "exit_code": int
          }

        Context policy knobs:
          - strict_process_checks: bool
              If True, subprocess-required checks FAIL (not fallback) when pickle/subprocess fails.
          - process_context_keys: [str, ...]
              If provided, only these keys are passed into child processes.
          - missing_required_tools: [str, ...]
              If non-empty:
                - if fail_fast_on_missing_required_tools True: suite stops early; marks all checks skipped
                - else: skips checks whose tags intersect expensive_tags
          - fail_fast_on_missing_required_tools: bool (default True)
          - expensive_tags: [str, ...] default ["expensive","guestfs"]
          - redact_keys: [str, ...] global redaction tokens
          - max_workers: int default min(4, cpu_count)
        """
        started = time.monotonic()

        total = len(self.checks)
        if total <= 0:
            payload = self._build_result_payload(
                0, 0, 0, 0, False, {}, 0.0, top_slowest, error="No checks registered"
            )
            if log_summary:
                self._log_summary(payload)
            return payload

        # Parse configuration
        (
            use_procs,
            strict_process_checks,
            allow_context_keys,
            missing_required,
            fail_fast_missing,
            expensive_tags,
        ) = self._parse_run_config(context, use_processes)
        self._log_mp_start_method()

        results_json: dict[str, dict[str, Any]] = {}
        failed_critical = False
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        def mark_skipped(spec: CheckSpec, reason: str) -> None:
            nonlocal skipped_count
            r = CheckResult(
                name=spec.name,
                passed=False,
                critical=spec.critical,
                duration_s=0.0,
                skipped=True,
                skip_reason=reason,
                tags=list(spec.tags),
                description=spec.description,
                mode="skipped",
                attempts=0,
            )
            results_json[spec.name] = self._result_to_json(r, show_tracebacks=False)
            skipped_count += 1

        def already_done(name: str) -> bool:
            return name in results_json

        # Fail-fast on missing required tools (truthful semantics: skipped, not "critical failed")
        if missing_required and fail_fast_missing:
            msg = f"Missing required tools: {', '.join(missing_required)}"
            self.logger.error(msg)
            for spec in self.checks:
                mark_skipped(spec, "missing_required_tools:fail_fast")
            total_dur = time.monotonic() - started
            payload = self._build_result_payload(
                total, 0, 0, skipped_count, False, results_json, total_dur, top_slowest, error=msg
            )
            if log_summary:
                self._log_summary(payload)
            return payload

        # Phase A: sequential checks (and any non-parallel-safe or dependency/critical ones)
        for spec in self.checks:
            # Check if we should run this check
            should_run, skip_reason = self._should_run_check(
                spec, context, results_json, missing_required, expensive_tags
            )
            if not should_run:
                if skip_reason and skip_reason not in ["already_done"]:
                    mark_skipped(spec, skip_reason)
                continue

            is_parallel = (
                parallel
                and self._is_parallel_candidate(spec)
                and (not spec.critical)
                and (not spec.depends_on)
            )
            if is_parallel:
                continue  # defer to Phase B

            # Create executor
            exec_once = self._create_check_executor(
                spec, context, use_procs, show_tracebacks, strict_process_checks, allow_context_keys
            )

            try:
                r = self._run_with_retries(spec, exec_once)
            except Exception as e:  # pylint: disable=broad-exception-caught  # execution machinery failure, must not abort the whole suite run
                if strict_process_checks:
                    r = CheckResult(
                        name=spec.name,
                        passed=False,
                        critical=spec.critical,
                        duration_s=0.0,
                        error=f"Execution failed (strict mode): {e}",
                        traceback=(traceback.format_exc() if show_tracebacks else None),
                        tags=list(spec.tags),
                        description=spec.description,
                        mode=(
                            "subprocess"
                            if bool(spec.run_in_process) or (use_procs and spec.timeout_s is not None)
                            else "inprocess"
                        ),
                        attempts=1,
                    )
                else:
                    self.logger.debug("Execution error for %s (%s); fallback to in-process", spec.name, e)
                    r = self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

            r = self._postprocess_result(spec, context, r)
            results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)

            if r.skipped:
                skipped_count += 1
            elif r.passed:
                passed_count += 1
                self.logger.debug("Validation passed: %s (%.2fs) [%s]", spec.name, r.duration_s, r.mode)
            else:
                failed_count += 1
                msg = (
                    f"Validation failed: {spec.name} ({r.duration_s:.2f}s) [{r.mode}] - {r.error or 'error'}"
                )
                if r.critical:
                    failed_critical = True
                    self.logger.error(msg)
                    if show_tracebacks and r.traceback:
                        self.logger.error((r.traceback or "").rstrip())
                    if stop_on_critical:
                        break
                else:
                    self.logger.warning(msg)
                    if show_tracebacks and r.traceback:
                        self.logger.warning((r.traceback or "").rstrip())

        # If critical fail stops early, mark remaining as skipped (truthfully)
        if failed_critical and stop_on_critical:
            for spec in self.checks:
                if not already_done(spec.name):
                    mark_skipped(spec, "stopped_on_critical")
            total_dur = time.monotonic() - started
            payload = self._build_result_payload(
                total,
                passed_count,
                failed_count,
                skipped_count,
                failed_critical,
                results_json,
                total_dur,
                top_slowest,
            )
            if log_summary:
                self._log_summary(payload)
            return payload

        # Phase B: parallel-safe checks (spawn-safe scheduler)
        if parallel:
            # gather candidates still not done
            candidates: list[CheckSpec] = []
            for spec in self.checks:
                # Check if we should run this check
                should_run, skip_reason = self._should_run_check(
                    spec, context, results_json, missing_required, expensive_tags
                )
                if not should_run:
                    if skip_reason and skip_reason not in ["already_done"]:
                        mark_skipped(spec, skip_reason)
                    continue

                if self._is_parallel_candidate(spec) and (not spec.critical) and (not spec.depends_on):
                    candidates.append(spec)
                else:
                    # run sequentially (non-parallel-safe) now
                    exec_once2 = self._create_check_executor(
                        spec, context, use_procs, show_tracebacks, strict_process_checks, allow_context_keys
                    )
                    r = self._run_with_retries(spec, exec_once2)
                    r = self._postprocess_result(spec, context, r)
                    results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)

                    if r.passed:
                        passed_count += 1
                    else:
                        failed_count += 1

            if candidates:
                cpu = effective_cpu_count()
                mw = int(max_workers or 0) or int(context.get("max_workers", 0) or 0) or min(4, cpu)
                mw = max(1, min(mw, cpu))

                # In parallel mode, we already run each check in its own process; "use_hard_timeout"
                # just decides whether we enforce spec.timeout_s as a hard kill in that scheduler.
                use_hard_timeout = bool(
                    use_procs
                )  # hard timeout enforcement enabled when processes are allowed

                try:
                    par_results = self._run_parallel_checks(
                        candidates,
                        context,
                        show_tracebacks=show_tracebacks,
                        strict_process_checks=strict_process_checks,
                        allow_context_keys=allow_context_keys,
                        max_workers=mw,
                        use_hard_timeout=use_hard_timeout,
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught  # parallel scheduler failure, fall back to sequential rather than abort
                    # If parallel machinery fails, fall back sequentially (best-effort)
                    self.logger.warning("Parallel execution failed (%s); falling back to sequential", e)
                    par_results = {}
                    for spec in candidates:
                        exec_once3 = self._create_check_executor(
                            spec,
                            context,
                            use_procs,
                            show_tracebacks,
                            strict_process_checks,
                            allow_context_keys,
                        )
                        rr = self._run_with_retries(spec, exec_once3)
                        par_results[spec.name] = rr

                for name, r in par_results.items():
                    spec = next((s for s in candidates if s.name == name), None)
                    if spec is None:
                        continue
                    r = self._postprocess_result(spec, context, r)
                    results_json[name] = self._result_to_json(r, show_tracebacks=show_tracebacks)
                    if r.passed:
                        passed_count += 1
                    else:
                        failed_count += 1

        # Any remaining not executed => skipped (truthfully)
        for spec in self.checks:
            if not already_done(spec.name):
                mark_skipped(spec, "not_executed")

        total_dur = time.monotonic() - started
        payload = self._build_result_payload(
            total,
            passed_count,
            failed_count,
            skipped_count,
            failed_critical,
            results_json,
            total_dur,
            top_slowest,
        )

        if log_summary:
            self._log_summary(payload)

        return payload

    # Logging

    def _log_summary(self, payload: dict[str, Any]) -> None:
        stats = payload.get("stats", {}) or {}
        self.logger.info(
            "Validation summary: total=%s passed=%s failed=%s skipped=%s duration=%.2fs ok=%s exit_code=%s",
            stats.get("total", "?"),
            stats.get("passed", "?"),
            stats.get("failed", "?"),
            stats.get("skipped", "?"),
            float(stats.get("duration_s", 0.0)),
            bool(payload.get("ok", False)),
            payload.get("exit_code", "?"),
        )

        if payload.get("failed_critical"):
            self.logger.error("One or more CRITICAL validations failed.")

        results = payload.get("results", {}) or {}
        failed = [
            name
            for name, r in results.items()
            if (not r.get("skipped", False)) and (not r.get("passed", True))
        ]
        if failed:
            self.logger.warning("Failed validations: %s", ", ".join(failed))
