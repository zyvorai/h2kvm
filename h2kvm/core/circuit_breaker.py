# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/circuit_breaker.py
"""
Thread-safe circuit breaker for protecting remote/expensive calls.

The circuit breaker pattern prevents cascading failures by short-circuiting
calls to a failing dependency once a configurable failure threshold is reached.
After a recovery timeout the breaker enters a *half-open* state where a
limited number of probe calls are allowed through.  If those succeed the
circuit closes again; if they fail it re-opens.

Usage as a decorator::

    from h2kvm.core.circuit_breaker import circuit_breaker


    @circuit_breaker(name="vcenter_api")
    def call_vcenter(host, path): ...

Usage as a context manager::

    breaker = CircuitBreaker(name="storage_backend")
    with breaker:
        do_something_risky()

Manual usage::

    breaker = CircuitBreaker(name="nbd")
    breaker.before_call()  # raises CircuitOpenError when open
    try:
        result = risky_call()
        breaker.record_success()
    except Exception:
        breaker.record_failure()
        raise
"""

from __future__ import annotations

import enum
import functools
import logging
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(enum.Enum):
    """Possible states of a circuit breaker."""

    CLOSED = "closed"
    """Normal operation -- calls pass through."""

    OPEN = "open"
    """Too many failures -- calls are rejected immediately."""

    HALF_OPEN = "half_open"
    """Recovery probe -- a limited number of calls are allowed through."""


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit is open."""

    def __init__(self, name: str, remaining_seconds: float):
        self.name = name
        self.remaining_seconds = remaining_seconds
        super().__init__(f"Circuit breaker '{name}' is OPEN (retry in {remaining_seconds:.1f}s)")


class CircuitBreaker:  # pylint: disable=too-many-instance-attributes  # tracks full breaker state machine (counts, timestamps, config) cohesively
    """
    Thread-safe circuit breaker.

    Args:
        name: Human-readable identifier (used in log messages and errors).
        failure_threshold: Number of consecutive failures before the circuit
            opens (default ``5``).
        recovery_timeout: Seconds to wait in OPEN state before transitioning
            to HALF_OPEN (default ``60``).
        half_open_max_calls: Maximum probe calls allowed in HALF_OPEN state
            (default ``1``).
    """

    def __init__(
        self,
        name: str = "default",
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._half_open_calls: int = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0

    # -- public read-only properties -----------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current circuit state (may trigger OPEN -> HALF_OPEN transition)."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def failure_count(self) -> int:
        """Number of consecutive failures in the current window."""
        with self._lock:
            return self._failure_count

    # -- core operations -----------------------------------------------------

    def before_call(self) -> None:
        """
        Gate check -- call *before* executing the protected operation.

        Raises:
            CircuitOpenError: If the circuit is OPEN and the recovery
                timeout has not yet elapsed.
        """
        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                remaining = self.recovery_timeout - (time.monotonic() - self._opened_at)
                raise CircuitOpenError(self.name, max(0.0, remaining))

            # HALF_OPEN: allow limited probes
            if self._half_open_calls >= self.half_open_max_calls:
                remaining = self.recovery_timeout - (time.monotonic() - self._opened_at)
                raise CircuitOpenError(self.name, max(0.0, remaining))
            self._half_open_calls += 1

    def record_success(self) -> None:
        """Record a successful call -- resets failure count and may close."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._transition(CircuitState.CLOSED)
            else:
                # CLOSED: just reset consecutive failures
                self._failure_count = 0
                self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed call -- may open the circuit."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed -- re-open
                self._transition(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        """Force the circuit back to CLOSED (useful in tests or admin ops)."""
        with self._lock:
            self._transition(CircuitState.CLOSED)

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> CircuitBreaker:
        self.before_call()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        # Never suppress the exception

    # -- internals -----------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """Must be called while holding ``_lock``."""
        if self._state != CircuitState.OPEN:
            return
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self.recovery_timeout:
            self._transition(CircuitState.HALF_OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        """Must be called while holding ``_lock``."""
        old = self._state
        self._state = new_state

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0

        logger.info(
            "Circuit breaker '%s': %s -> %s (failures=%d)",
            self.name,
            old.value,
            new_state.value,
            self._failure_count,
        )

    def __repr__(self) -> str:
        return (
            f"<CircuitBreaker name={self.name!r} state={self.state.value} "
            f"failures={self._failure_count}/{self.failure_threshold}>"
        )


# ---------------------------------------------------------------------------
# Global registry (optional convenience)
# ---------------------------------------------------------------------------

_registry_lock = threading.Lock()
_registry: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    *,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
) -> CircuitBreaker:
    """
    Return a named circuit breaker, creating it on first access.

    Repeated calls with the same *name* return the **same** instance so
    that multiple call-sites sharing a logical dependency converge on a
    single breaker.
    """
    with _registry_lock:
        if name not in _registry:
            _registry[name] = CircuitBreaker(
                name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
            )
        return _registry[name]


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def circuit_breaker(
    name: str = "default",
    *,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
) -> Callable[[F], F]:
    """
    Decorator that wraps a function with a named circuit breaker.

    Args:
        name: Logical name of the breaker (shared across all decorated
            functions with the same name).
        failure_threshold: Failures before opening.
        recovery_timeout: Seconds in OPEN before probing.
        half_open_max_calls: Probe calls allowed in HALF_OPEN.

    Example::

        @circuit_breaker(name="vcenter_api", failure_threshold=3)
        def fetch_vm_list(host): ...
    """

    def decorator(func: F) -> F:
        breaker = get_breaker(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            breaker.before_call()
            try:
                result = func(*args, **kwargs)
            except Exception:
                breaker.record_failure()
                raise
            breaker.record_success()
            return result

        # Expose the breaker instance for inspection / manual reset
        wrapper.circuit_breaker = breaker  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
