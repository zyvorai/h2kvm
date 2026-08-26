# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/structured_log.py
# pylint: disable=too-many-lines
# Cohesive structured-logging module (event schema, async writer, rate
# limiting/sampling, span hierarchy, audit channel); splitting it would
# scatter closely-coupled pipeline state across files.
"""
Structured logging for VMCraft lifecycle operations.

Provides a canonical event schema with contextvars-based trace propagation,
timed phase tracking, and VMCraft-specific Prometheus metrics integration.

Every log record automatically gets:
    ts, level, service, component, host, pid, trace_id, vm_id,
    workflow, event, phase, duration_ms, status

Production hardening (v2):
    - Async (non-blocking) log writes with bounded queue + backpressure
    - Safe JSON serialization for datetime, UUID, Path, bytes, etc.
    - Field size enforcement (truncation) to prevent log-line bloat
    - Per-event token-bucket rate limiting with suppression counts
    - Probabilistic sampling by event-name prefix
    - Custom processor registry for extensibility
    - Dynamic runtime log-level control
    - Span hierarchy (span_id / parent_span_id) for distributed tracing
    - Dedicated audit channel (bypasses rate-limit + sampling)
    - Graceful shutdown with queue drain
"""

from __future__ import annotations

import atexit
import contextvars
import dataclasses
import datetime as _dt
import json
import logging
import os
import queue
import random
import socket
import sys
import threading
import time
import traceback as _traceback
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Context variables — propagate automatically through the call stack
# ---------------------------------------------------------------------------

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id",
    default=None,
)
_vm_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "vm_id",
    default=None,
)
_workflow_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "workflow",
    default=None,
)
_component_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "component",
    default=None,
)

# Span hierarchy context vars
_span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "span_id",
    default=None,
)
_parent_span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "parent_span_id",
    default=None,
)

SERVICE_NAME = "hyper2kvm"

# ---------------------------------------------------------------------------
# A. SafeJSONEncoder — handles exotic Python types
# ---------------------------------------------------------------------------


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that safely serializes common Python types.

    Handles: datetime, date, time, UUID, Path, bytes, set, frozenset,
    dataclasses, Exceptions.  Falls back to ``str(obj)`` for anything else.
    """

    def default(self, o: Any) -> Any:  # pylint: disable=too-many-return-statements
        # One early-return branch per exotic type this encoder knows how
        # to serialize; that's the point of this fallback dispatcher.
        if isinstance(o, (_dt.datetime, _dt.date, _dt.time)):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, Path):
            return str(o)
        if isinstance(o, bytes):
            try:
                return o.decode("utf-8", errors="replace")
            except Exception:  # pylint: disable=broad-exception-caught
                # Fallback JSON serialization must never raise regardless
                # of what odd encoding error a bytes value triggers.
                return f"<bytes len={len(o)}>"
        if isinstance(o, (set, frozenset)):
            return list(o)
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if isinstance(o, BaseException):
            return f"{type(o).__name__}: {o}"
        try:
            return str(o)
        except Exception:  # pylint: disable=broad-exception-caught
            # Fallback JSON serialization must never raise regardless of
            # what str(obj) does for an arbitrary/unknown type.
            return f"<unserializable {type(o).__name__}>"


def _safe_json_serializer(obj: Any, **kw: Any) -> str:
    """JSON serializer using SafeJSONEncoder."""
    return json.dumps(obj, cls=SafeJSONEncoder, **kw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_trace_id() -> str:
    """Generate a short random trace id (12 hex chars)."""
    return uuid.uuid4().hex[:12]


def _generate_span_id() -> str:
    """Generate a short random span id (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:  # pylint: disable=broad-exception-caught
        # Hostname lookup is decorative log metadata; any failure must
        # fall back rather than block logging setup.
        return "unknown"


# Cache hostname at import time (it won't change during a process lifetime).
_HOST = _hostname()

# ---------------------------------------------------------------------------
# Custom structured logging pipeline (zero-dependency structlog replacement)
# ---------------------------------------------------------------------------


class DropEvent(Exception):
    """Raised by processors to silently discard an event."""


Processor = Callable[[Any, str, dict[str, Any]], dict[str, Any]]


class PrintLogger:  # pylint: disable=too-few-public-methods
    # Minimal print-based logger backend (msg + level-name aliases);
    # intentionally has just one real method.
    """Simple logger that writes to a file object (default: stdout)."""

    def __init__(self, file: Any = None) -> None:
        self._file = file or sys.stdout

    def msg(self, message: str) -> None:
        """Write message followed by a newline and flush the file."""
        self._file.write(str(message) + "\n")
        self._file.flush()

    debug = info = warning = warn = error = critical = fatal = msg


class PrintLoggerFactory:  # pylint: disable=too-few-public-methods
    # Factory object whose sole job is __call__(); no natural second
    # public method to add.
    """Factory that creates PrintLogger instances."""

    def __init__(self, file: Any = None) -> None:
        self._file = file

    def __call__(self, *args: Any, **kwargs: Any) -> PrintLogger:
        return PrintLogger(self._file)


def _add_log_level(
    _logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: set ``level`` from the bound method name."""
    event_dict["level"] = method_name
    return event_dict


def _format_exc_info(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: format ``exc_info`` into a traceback string."""
    exc_info = event_dict.pop("exc_info", None)
    if exc_info:
        if isinstance(exc_info, BaseException):
            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
        elif exc_info is True:
            exc_info = sys.exc_info()
        if exc_info and exc_info[0] is not None:
            event_dict["exception"] = "".join(
                _traceback.format_exception(*exc_info),
            )
    return event_dict


class _UnicodeDecoder:  # pylint: disable=too-few-public-methods
    # Processor object whose sole job is __call__(); matches the
    # Processor callable protocol used throughout this pipeline.
    """Processor: decode bytes values to str."""

    def __init__(self, encoding: str = "utf-8", errors: str = "replace") -> None:
        self._encoding = encoding
        self._errors = errors

    def __call__(
        self,
        _logger: Any,
        _method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        for key in list(event_dict.keys()):
            if isinstance(event_dict[key], bytes):
                event_dict[key] = event_dict[key].decode(
                    self._encoding,
                    self._errors,
                )
        return event_dict


class _JSONRenderer:  # pylint: disable=too-few-public-methods
    # Processor object whose sole job is __call__(); matches the
    # Processor callable protocol used throughout this pipeline.
    """Processor: render event dict as a JSON string."""

    def __init__(
        self,
        serializer: Callable[..., str] | None = None,
        sort_keys: bool = True,
        **kw: Any,
    ) -> None:
        self._serializer = serializer or json.dumps
        self._kw = {"sort_keys": sort_keys, **kw}

    def __call__(
        self,
        _logger: Any,
        _method: str,
        event_dict: dict[str, Any],
    ) -> str:
        return self._serializer(event_dict, **self._kw)


class _ConsoleRenderer:  # pylint: disable=too-few-public-methods
    # Processor object whose sole job is __call__(); matches the
    # Processor callable protocol used throughout this pipeline.
    """Processor: render event dict as human-readable key=value output."""

    def __call__(
        self,
        _logger: Any,
        _method: str,
        event_dict: dict[str, Any],
    ) -> str:
        event = event_dict.pop("event", "")
        level = event_dict.pop("level", "")
        ts = event_dict.pop("ts", "")

        parts: list[str] = []
        if ts:
            parts.append(f"[{ts}]")
        if level:
            parts.append(level.upper())
        parts.append(str(event))

        for k, v in sorted(event_dict.items()):
            if not str(k).startswith("_"):
                parts.append(f"{k}={v}")

        return " ".join(parts)


def _add_logger_name(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: add logger name from LogRecord."""
    record = event_dict.get("_record")
    if record is not None:
        event_dict["logger"] = record.name
    return event_dict


class _TimeStamper:  # pylint: disable=too-few-public-methods
    # Processor object whose sole job is __call__(); matches the
    # Processor callable protocol used throughout this pipeline.
    """Processor: add ISO timestamp."""

    def __init__(self, fmt: str = "iso", utc: bool = True) -> None:
        self._fmt = fmt
        self._utc = utc

    def __call__(
        self,
        _logger: Any,
        _method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        now = _dt.datetime.now(_dt.timezone.utc) if self._utc else _dt.datetime.now()

        if self._fmt == "iso":
            event_dict["timestamp"] = now.isoformat()
        else:
            event_dict["timestamp"] = now.strftime(self._fmt)
        return event_dict


class ProcessorFormatter(logging.Formatter):
    """logging.Formatter that runs stdlib LogRecords through a processor chain.

    Replaces ``structlog.stdlib.ProcessorFormatter``.  Exported for use
    by ``logger.py``.
    """

    def __init__(
        self,
        processors: list[Any] | None = None,
        foreign_pre_chain: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._processors = list(processors or [])
        self._foreign_pre_chain = list(foreign_pre_chain or [])

    def format(self, record: logging.LogRecord) -> str:
        # Build initial event dict from LogRecord
        event_dict: dict[str, Any] = {
            "event": record.getMessage(),
            "_record": record,
        }

        # Run foreign pre-chain (for stdlib log records)
        for proc in self._foreign_pre_chain:
            event_dict = proc(record.name, record.levelname.lower(), event_dict)

        # Run main processors
        for proc in self._processors:
            result = proc(record.name, record.levelname.lower(), event_dict)
            if isinstance(result, str):
                return result
            event_dict = result

        return str(event_dict)


class BoundLogger:
    """Bound logger that runs events through a processor chain."""

    def __init__(self, logger: Any, processors: list[Any]) -> None:
        self._logger = logger
        self._processors = processors

    def _proxy(self, method_name: str, event: str, **kw: Any) -> None:
        event_dict: dict[str, Any] = {"event": event, **kw}
        try:
            for proc in self._processors:
                result = proc(self._logger, method_name, event_dict)
                if isinstance(result, str):
                    # Renderer returned a string — write it directly
                    self._logger.msg(result)
                    return
                event_dict = result
        except DropEvent:
            return

        # Final processor returned a dict (unexpected but handle gracefully)
        self._logger.msg(str(event_dict))

    def msg(self, event: str, **kw: Any) -> None:
        """Log event at info level (alias for info())."""
        self._proxy("info", event, **kw)

    def info(self, event: str, **kw: Any) -> None:
        """Log event at info level."""
        self._proxy("info", event, **kw)

    def debug(self, event: str, **kw: Any) -> None:
        """Log event at debug level."""
        self._proxy("debug", event, **kw)

    def warning(self, event: str, **kw: Any) -> None:
        """Log event at warning level."""
        self._proxy("warning", event, **kw)

    def error(self, event: str, **kw: Any) -> None:
        """Log event at error level."""
        self._proxy("error", event, **kw)

    def critical(self, event: str, **kw: Any) -> None:
        """Log event at critical level."""
        self._proxy("critical", event, **kw)


# Global configuration state
_global_processors: list[Any] = []
_global_logger_factory: Any = None  # pylint: disable=invalid-name
# Mutable module-level singleton state (reassigned by _configure()), not a
# true constant, so UPPER_CASE would misleadingly imply immutability.


def _configure(
    processors: list[Any],
    logger_factory: Any,
) -> None:
    """Configure the global processor chain and logger factory."""
    global _global_processors, _global_logger_factory  # pylint: disable=global-statement
    # Deliberate module-level singleton configuration entry point.
    _global_processors = list(processors)
    _global_logger_factory = logger_factory


def _get_bound_logger() -> BoundLogger:
    """Create a new BoundLogger using the global configuration."""
    factory = _global_logger_factory or PrintLoggerFactory()
    logger = factory()
    return BoundLogger(logger, _global_processors)


# ---------------------------------------------------------------------------
# B. AsyncLogWriter + factory — non-blocking bounded-queue log writes
# ---------------------------------------------------------------------------

_LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class AsyncLogWriter:
    """Thread-based async log writer with bounded queue and backpressure.

    When the queue is full, the oldest message is dropped and an overflow
    warning is emitted every *overflow_warn_interval* drops.

    Implements the same write interface as ``PrintLogger``
    (msg/info/debug/warning/error/critical all delegate to write).
    """

    def __init__(
        self,
        destination: Any = None,
        maxsize: int = 10_000,
        overflow_warn_interval: int = 1000,
    ) -> None:
        self._dest = destination or sys.stdout
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=maxsize)
        self._overflow_count = 0
        self._overflow_warn_interval = overflow_warn_interval
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._writer_loop,
            daemon=True,
            name="async-log-writer",
        )
        self._thread.start()

    def write(self, message: str) -> None:
        """Enqueue message for the writer thread, dropping oldest on overflow."""
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            # Drop oldest, enqueue new
            with self._lock:
                self._overflow_count += 1
                warn = (self._overflow_count % self._overflow_warn_interval) == 0
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                pass
            if warn:
                # Write overflow warning directly, bypassing queue
                try:
                    self._dest.write(
                        json.dumps(
                            {
                                "event": "log_queue_overflow",
                                "level": "warning",
                                "dropped": self._overflow_count,
                                "service": SERVICE_NAME,
                                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(
                                    timespec="milliseconds",
                                ),
                            }
                        )
                        + "\n",
                    )
                    self._dest.flush()
                except Exception:  # pylint: disable=broad-exception-caught
                    # Best-effort overflow warning; must not crash the
                    # producer thread over a logging-destination hiccup.
                    pass

    def flush(self) -> None:
        """No-op: flushing is handled by the background writer thread."""

    # PrintLogger-compatible interface — all methods delegate to write()
    def msg(self, message: str) -> None:
        """Enqueue message for the writer thread (PrintLogger-compatible)."""
        self.write(message)

    debug = info = warning = warn = error = critical = fatal = msg

    def _writer_loop(self) -> None:
        while True:
            msg = self._queue.get()
            if msg is None:
                break
            try:
                self._dest.write(msg)
                if not msg.endswith("\n"):
                    self._dest.write("\n")
                self._dest.flush()
            except Exception:  # pylint: disable=broad-exception-caught
                # Background writer thread: any destination failure must
                # not kill the thread or propagate to producers.
                pass

    def drain(self, timeout: float = 5.0) -> None:
        """Signal shutdown and drain remaining messages."""
        self._queue.put(None)
        self._thread.join(timeout=timeout)


class _AsyncLoggerFactory:  # pylint: disable=too-few-public-methods
    # Factory object whose sole job is __call__(); no natural second
    # public method to add.
    """LoggerFactory that writes through an AsyncLogWriter."""

    def __init__(self, writer: AsyncLogWriter) -> None:
        self._writer = writer

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncLogWriter:
        return self._writer


# ---------------------------------------------------------------------------
# C. Field size enforcement processor
# ---------------------------------------------------------------------------

_FIELD_MAX_STR_LEN = 4096  # 4 KB
_FIELD_MAX_DEPTH = 4


def _truncate_value(value: Any, depth: int = 0) -> Any:  # pylint: disable=too-many-return-statements
    # One early-return branch per value kind (str/bytes/depth-cap/dict/
    # list-tuple/passthrough); that's the point of this dispatcher.
    """Recursively truncate strings and cap collection nesting."""
    if isinstance(value, str) and len(value) > _FIELD_MAX_STR_LEN:
        return value[:_FIELD_MAX_STR_LEN] + "...<truncated>"
    if isinstance(value, bytes) and len(value) > _FIELD_MAX_STR_LEN:
        return value[:_FIELD_MAX_STR_LEN] + b"...<truncated>"
    if depth >= _FIELD_MAX_DEPTH:
        if isinstance(value, (dict, list, tuple, set, frozenset)):
            return "...<truncated>"
        return value
    if isinstance(value, dict):
        return {k: _truncate_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        truncated = [_truncate_value(item, depth + 1) for item in value]
        return type(value)(truncated) if isinstance(value, tuple) else truncated
    return value


def _enforce_field_limits(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: truncate oversized string fields and cap nesting."""
    for key in list(event_dict.keys()):
        event_dict[key] = _truncate_value(event_dict[key])
    return event_dict


# ---------------------------------------------------------------------------
# D. Rate limiter processor — per-event token bucket
# ---------------------------------------------------------------------------


class _TokenBucketRateLimiter:  # pylint: disable=too-few-public-methods
    # Processor object whose sole job is __call__(); matches the
    # Processor callable protocol used throughout this pipeline.
    """Per-event-name token-bucket rate limiter.

    Each unique event name gets its own bucket with *rate* tokens per second
    and a burst capacity of *burst*.  Events with ``_audit=True`` bypass
    rate limiting entirely.
    """

    def __init__(self, rate: float = 50.0, burst: int = 50) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: dict[str, tuple[float, float]] = {}  # event -> (tokens, last_ts)
        self._suppressed: dict[str, int] = {}
        self._lock = threading.Lock()

    def __call__(
        self,
        _logger: Any,
        _method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        # Audit events bypass rate limiting
        if event_dict.get("_audit"):
            return event_dict

        event_name = event_dict.get("event", "")
        now = time.monotonic()

        with self._lock:
            if event_name in self._buckets:
                tokens, last_ts = self._buckets[event_name]
                elapsed = now - last_ts
                tokens = min(self._burst, tokens + elapsed * self._rate)
            else:
                tokens = float(self._burst)
                last_ts = now

            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[event_name] = (tokens, now)
                # Attach suppression count if any were suppressed
                suppressed = self._suppressed.pop(event_name, 0)
                if suppressed > 0:
                    event_dict["_suppressed_count"] = suppressed
                return event_dict
            self._buckets[event_name] = (tokens, now)
            self._suppressed[event_name] = self._suppressed.get(event_name, 0) + 1
            raise DropEvent


_rate_limiter = _TokenBucketRateLimiter()


def _rate_limit_processor(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: apply token-bucket rate limiting."""
    return _rate_limiter(_logger, _method, event_dict)


# ---------------------------------------------------------------------------
# E. Sampling processor — probabilistic drop by event prefix
# ---------------------------------------------------------------------------

_sampling_rules: dict[str, float] = {}


def configure_sampling(rules: dict[str, float]) -> None:
    """Configure probabilistic sampling rules.

    Args:
        rules: Mapping of event-name prefix to keep-probability (0.0-1.0).
               E.g. ``{"debug_": 0.1}`` keeps 10% of events starting with
               ``"debug_"``.  Events with ``_audit=True`` always pass.
    """
    global _sampling_rules  # pylint: disable=global-statement
    # Deliberate module-level singleton configuration entry point.
    _sampling_rules = dict(rules)


def _sampling_processor(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: probabilistic event sampling."""
    if event_dict.get("_audit"):
        return event_dict

    event_name = str(event_dict.get("event", ""))
    for prefix, keep_prob in _sampling_rules.items():
        if event_name.startswith(prefix):
            if random.random() >= keep_prob:
                raise DropEvent
            event_dict["_sampled"] = True
            break
    return event_dict


# ---------------------------------------------------------------------------
# F. Processor registry — extensibility
# ---------------------------------------------------------------------------

_custom_processors: list[Any] = []


def add_processor(fn: Any) -> None:
    """Register a custom log processor.

    The processor will be appended after the built-in processors and before
    the final renderer.  Adding a processor forces a pipeline rebuild on the
    next log call.
    """
    global _configured  # pylint: disable=global-statement
    # Deliberate module-level singleton configuration entry point.
    _custom_processors.append(fn)
    _configured = False


# ---------------------------------------------------------------------------
# G. Dynamic level control
# ---------------------------------------------------------------------------

_current_level: str = "debug"  # pylint: disable=invalid-name
# Mutable module-level singleton state (reassigned by set_log_level()),
# not a true constant, so UPPER_CASE would misleadingly imply immutability.


def set_log_level(level: str) -> None:
    """Change the runtime log level.

    Args:
        level: One of ``"debug"``, ``"info"``, ``"warning"``, ``"error"``,
               ``"critical"``.  Events below this level are dropped.
    """
    global _current_level, _configured  # pylint: disable=global-statement
    # Deliberate module-level singleton configuration entry point.
    _current_level = level.lower()
    _configured = False


def _level_filter(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: drop events below the current log level."""
    event_level = event_dict.get("level", "info")
    if isinstance(event_level, str):
        event_level_num = _LOG_LEVEL_MAP.get(event_level.lower(), logging.INFO)
    else:
        event_level_num = logging.INFO
    threshold_num = _LOG_LEVEL_MAP.get(_current_level, logging.DEBUG)
    if event_level_num < threshold_num:
        raise DropEvent
    return event_dict


# ---------------------------------------------------------------------------
# H. Span hierarchy — processor + add_envelope update
# ---------------------------------------------------------------------------


def add_envelope(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Processor: inject canonical fields from context vars.

    Fields already present in *event_dict* (e.g. set explicitly by the
    caller) take precedence over context-var defaults.
    """
    defaults: dict[str, Any] = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
        "service": SERVICE_NAME,
        "host": _HOST,
        "pid": os.getpid(),
    }

    # Context-var fields (may be None -> omitted)
    trace_id = _trace_id_var.get()
    if trace_id is not None:
        defaults["trace_id"] = trace_id

    vm_id = _vm_id_var.get()
    if vm_id is not None:
        defaults["vm_id"] = vm_id

    workflow = _workflow_var.get()
    if workflow is not None:
        defaults["workflow"] = workflow

    component = _component_var.get()
    if component is not None:
        defaults["component"] = component

    # Span hierarchy
    span_id = _span_id_var.get()
    if span_id is not None:
        defaults["span_id"] = span_id

    parent_span_id = _parent_span_id_var.get()
    if parent_span_id is not None:
        defaults["parent_span_id"] = parent_span_id

    # Merge: explicit caller fields win over defaults
    return {**defaults, **event_dict}


# ---------------------------------------------------------------------------
# configure_structured_logging
# ---------------------------------------------------------------------------

_configured = False  # pylint: disable=invalid-name
_main_writer: AsyncLogWriter | None = None  # pylint: disable=invalid-name
_audit_writer: AsyncLogWriter | None = None  # pylint: disable=invalid-name
# Mutable module-level singleton state (reassigned by
# configure_structured_logging()), not true constants, so UPPER_CASE would
# misleadingly imply immutability.


def configure_structured_logging(
    json_output: bool = True,
    *,
    async_writes: bool = True,
    max_queue_size: int = 10_000,
) -> None:
    """
    Set up the structured logging pipeline with the canonical envelope
    processor chain.

    Args:
        json_output: If *True* render as JSON (machine-queryable).
                     If *False* use the console dev renderer.
        async_writes: If *True* (default) use a background thread for
                      non-blocking log writes.
        max_queue_size: Maximum queue depth for async writes.
    """
    global _configured, _main_writer, _audit_writer  # pylint: disable=global-statement
    # Deliberate module-level singleton configuration entry point.

    renderer: Processor
    if json_output:
        renderer = _JSONRenderer(
            sort_keys=False,
            serializer=_safe_json_serializer,
        )
    else:
        renderer = _ConsoleRenderer()

    # Build the processor pipeline
    processors: list[Processor] = [
        _add_log_level,
        _level_filter,
        add_envelope,
        _enforce_field_limits,
        _rate_limit_processor,
        _sampling_processor,
        *_custom_processors,
        _format_exc_info,
        _UnicodeDecoder(),
        renderer,
    ]

    # Logger factory: async or sync
    if async_writes:
        _main_writer = AsyncLogWriter(
            destination=sys.stdout,
            maxsize=max_queue_size,
        )
        logger_factory: Any = _AsyncLoggerFactory(_main_writer)
        # Audit writer goes to stderr
        _audit_writer = AsyncLogWriter(
            destination=sys.stderr,
            maxsize=max_queue_size,
        )
    else:
        _main_writer = None
        _audit_writer = None
        logger_factory = PrintLoggerFactory()

    _configure(processors=processors, logger_factory=logger_factory)
    _configured = True


def _ensure_configured() -> None:
    if not _configured:
        configure_structured_logging(json_output=True)


def _get_logger() -> BoundLogger:
    _ensure_configured()
    return _get_bound_logger()


# ---------------------------------------------------------------------------
# TraceContext — set/clear context vars for a lifecycle scope
# ---------------------------------------------------------------------------


class TraceContext:
    """
    Context manager that sets canonical context vars for a lifecycle scope.

    Usage::

        with TraceContext(vm_id="rhel88", workflow="vm_activation", component="lifecycle"):
            ...  # all log_event() / PhaseTimer calls inherit these fields
    """

    def __init__(
        self,
        vm_id: str,
        workflow: str,
        component: str = "lifecycle",
        trace_id: str | None = None,
    ) -> None:
        self.vm_id = vm_id
        self.workflow = workflow
        self.component = component
        self.trace_id = trace_id or generate_trace_id()
        self._tokens: list[contextvars.Token[str | None]] = []

    def __enter__(self) -> TraceContext:
        root_span_id = _generate_span_id()
        self._tokens = [
            _trace_id_var.set(self.trace_id),
            _vm_id_var.set(self.vm_id),
            _workflow_var.set(self.workflow),
            _component_var.set(self.component),
            _span_id_var.set(root_span_id),
            _parent_span_id_var.set(None),
        ]
        return self

    def __exit__(self, *exc_info: Any) -> None:
        for tok in reversed(self._tokens):
            tok.var.reset(tok)
        self._tokens.clear()


# ---------------------------------------------------------------------------
# PhaseTimer — timed phase tracking with start/complete events + span child
# ---------------------------------------------------------------------------


class PhaseTimer:
    """
    Context manager that logs a *start* event on enter and a *complete*
    event (with ``duration_ms`` and ``status``) on exit.

    Creates a child span: captures the current span_id as parent_span_id,
    sets a new span_id, and restores the previous span on exit.

    Usage::

        with PhaseTimer("nbd_connect_start", "nbd_connect_complete", phase="nbd"):
            nbd.connect(...)
    """

    def __init__(
        self,
        event_start: str,
        event_complete: str,
        phase: str,
        **extra: Any,
    ) -> None:
        self.event_start = event_start
        self.event_complete = event_complete
        self.phase = phase
        self.extra = extra
        self._t0: float = 0.0
        self._span_tokens: list[contextvars.Token[str | None]] = []

    def __enter__(self) -> PhaseTimer:
        # Create child span
        parent_span = _span_id_var.get()
        child_span = _generate_span_id()
        self._span_tokens = [
            _parent_span_id_var.set(parent_span),
            _span_id_var.set(child_span),
        ]

        self._t0 = time.monotonic()
        log_event(self.event_start, phase=self.phase, **self.extra)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration_ms = round((time.monotonic() - self._t0) * 1000, 1)
        status = "failure" if exc_type is not None else "success"
        log_event(
            self.event_complete,
            phase=self.phase,
            duration_ms=duration_ms,
            status=status,
            **self.extra,
        )

        # Restore parent span
        for tok in reversed(self._span_tokens):
            tok.var.reset(tok)
        self._span_tokens.clear()

        # Record Prometheus metrics (best-effort)
        try:
            # pylint: disable=import-outside-toplevel
            # Deliberately lazy: keeps this logging module decoupled from
            # the metrics subsystem at import time; any failure here
            # (import or recording) is swallowed below as best-effort.
            from hyper2kvm.core.metrics import (
                vmcraft_lvm_activation_seconds,
                vmcraft_nbd_connect_seconds,
                vmcraft_storage_failures_total,
            )

            duration_s = duration_ms / 1000.0
            if self.phase == "nbd":
                vmcraft_nbd_connect_seconds.observe(duration_s)
            elif self.phase == "lvm":
                vmcraft_lvm_activation_seconds.observe(duration_s)

            if status == "failure":
                vmcraft_storage_failures_total.labels(phase=self.phase).inc()
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # metrics are best-effort


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    """One-liner for ad-hoc structured events."""
    logger = _get_logger()
    log_fn = getattr(logger, level, logger.info)
    log_fn(event, **fields)


def log_slow_phase(
    event: str,
    duration_ms: float,
    threshold_ms: float = 5000.0,
    **fields: Any,
) -> None:
    """Warn when a phase exceeds a duration threshold (degraded performance)."""
    if duration_ms > threshold_ms:
        log_event(
            event,
            level="warning",
            duration_ms=duration_ms,
            threshold_ms=threshold_ms,
            degraded=True,
            **fields,
        )


# ---------------------------------------------------------------------------
# I. Audit logger — dedicated channel, bypasses rate-limit + sampling
# ---------------------------------------------------------------------------


def log_audit(event: str, **fields: Any) -> None:
    """Log an audit event.

    Audit events are:
    - Written to stderr via a dedicated AsyncLogWriter
    - Emitted through the main pipeline with ``_audit=True`` so they
      bypass rate limiting and sampling
    """
    # Write to audit (stderr) channel
    if _audit_writer is not None:
        audit_record = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            "level": "warning",
            "channel": "audit",
            "service": SERVICE_NAME,
            "host": _HOST,
            "pid": os.getpid(),
        }
        trace_id = _trace_id_var.get()
        if trace_id is not None:
            audit_record["trace_id"] = trace_id
        vm_id = _vm_id_var.get()
        if vm_id is not None:
            audit_record["vm_id"] = vm_id
        audit_record.update(fields)
        try:
            _audit_writer.write(_safe_json_serializer(audit_record))
        except Exception:  # pylint: disable=broad-exception-caught
            # Audit write to stderr channel is best-effort; must not block
            # the main pipeline emission below.
            pass

    # Also emit through main pipeline (bypasses rate-limit + sampling)
    log_event(event, level="warning", _audit=True, channel="audit", **fields)


def log_isolation_status(
    mode: str,
    host_conflicts: list[str] | None = None,
) -> None:
    """Emit a safety-audit event about storage isolation."""
    conflicts = host_conflicts or []
    if conflicts:
        log_audit(
            "isolation_check",
            isolation_mode=mode,
            host_conflicts=conflicts,
            conflict_count=len(conflicts),
        )
    else:
        log_event(
            "isolation_check",
            level="info",
            isolation_mode=mode,
            host_conflicts=conflicts,
            conflict_count=len(conflicts),
        )
    if conflicts:
        try:
            # pylint: disable=import-outside-toplevel
            # Deliberately lazy: keeps this logging module decoupled from
            # the metrics subsystem at import time; any failure here
            # (import or recording) is swallowed below as best-effort.
            from hyper2kvm.core.metrics import vmcraft_isolation_violations_total

            vmcraft_isolation_violations_total.inc()
        except Exception:  # pylint: disable=broad-exception-caught
            pass


def log_execution_summary(  # pylint: disable=too-many-arguments
    # All keyword-only fields of the canonical execution-summary event;
    # each is independently required for the final lifecycle record.
    *,
    vm_id: str,
    workflow: str,
    phases: dict[str, float] | None = None,
    total_duration_ms: float,
    status: str,
    error: str | None = None,
) -> None:
    """Final lifecycle summary event."""
    fields: dict[str, Any] = {
        "vm_id": vm_id,
        "workflow": workflow,
        "total_duration_ms": total_duration_ms,
        "status": status,
    }
    if phases:
        fields["phases"] = phases
    if error:
        fields["error"] = error

    level = "info" if status == "success" else "error"
    log_event("execution_summary", level=level, **fields)

    # Prometheus counter
    try:
        # pylint: disable=import-outside-toplevel
        # Deliberately lazy: keeps this logging module decoupled from the
        # metrics subsystem at import time; any failure here (import or
        # recording) is swallowed below as best-effort.
        from hyper2kvm.core.metrics import vmcraft_vm_activation_total

        vmcraft_vm_activation_total.labels(status=status).inc()
    except Exception:  # pylint: disable=broad-exception-caught
        pass


# ---------------------------------------------------------------------------
# K. Shutdown hook — drain async writers
# ---------------------------------------------------------------------------


def _shutdown_logging() -> None:
    """Drain both async log writers on process exit."""
    if _main_writer is not None:
        try:
            _main_writer.drain(timeout=5.0)
        except Exception:  # pylint: disable=broad-exception-caught
            # Shutdown-time drain is best-effort; must not block process
            # exit on a writer-thread hiccup.
            pass
    if _audit_writer is not None:
        try:
            _audit_writer.drain(timeout=2.0)
        except Exception:  # pylint: disable=broad-exception-caught
            # Shutdown-time drain is best-effort; must not block process
            # exit on a writer-thread hiccup.
            pass


atexit.register(_shutdown_logging)
