# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for _TokenBucketRateLimiter and _rate_limit_processor."""

from __future__ import annotations

import threading
from unittest.mock import Mock, patch

import pytest

from hyper2kvm.core.structured_log import (
    DropEvent,
    _TokenBucketRateLimiter,
    _rate_limit_processor,
)


@pytest.fixture()
def limiter():
    return _TokenBucketRateLimiter(rate=10.0, burst=3)


def test_allows_initial_burst(limiter):
    """Fresh bucket allows `burst` events."""
    for i in range(3):
        ed = {"event": "test_event"}
        result = limiter(None, "info", ed)
        assert result["event"] == "test_event"


def test_drops_after_burst(limiter):
    """burst+1 raises DropEvent."""
    for _ in range(3):
        limiter(None, "info", {"event": "test_event"})
    with pytest.raises(DropEvent):
        limiter(None, "info", {"event": "test_event"})


def test_refills_over_time(limiter):
    """Tokens refill (mock time.monotonic)."""
    # Exhaust burst
    for _ in range(3):
        limiter(None, "info", {"event": "ev"})

    # Should drop now
    with pytest.raises(DropEvent):
        limiter(None, "info", {"event": "ev"})

    # Advance time by 0.5s at rate=10 -> 5 tokens refilled (capped at burst=3)
    with patch("time.monotonic") as mock_time:
        # The limiter uses time.monotonic() internally — we need to set a value
        # that's 0.5s after the last call
        mock_time.return_value = 1000.5
        # Need to also patch the stored timestamp
        limiter._buckets["ev"] = (0.0, 1000.0)
        result = limiter(None, "info", {"event": "ev"})
        assert result["event"] == "ev"


def test_per_event_isolation(limiter):
    """Different event names = separate buckets."""
    # Exhaust burst for "ev1"
    for _ in range(3):
        limiter(None, "info", {"event": "ev1"})
    with pytest.raises(DropEvent):
        limiter(None, "info", {"event": "ev1"})

    # "ev2" should still have full burst
    result = limiter(None, "info", {"event": "ev2"})
    assert result["event"] == "ev2"


def test_suppression_count(limiter):
    """Next allowed event after drops has _suppressed_count."""
    # Exhaust burst
    for _ in range(3):
        limiter(None, "info", {"event": "ev"})

    # Suppress 2 events
    for _ in range(2):
        with pytest.raises(DropEvent):
            limiter(None, "info", {"event": "ev"})

    # Refill tokens by manipulating bucket state
    limiter._buckets["ev"] = (3.0, 0.0)

    result = limiter(None, "info", {"event": "ev"})
    assert result["_suppressed_count"] == 2


def test_audit_bypass(limiter):
    """_audit=True always passes."""
    # Exhaust burst
    for _ in range(3):
        limiter(None, "info", {"event": "ev"})
    with pytest.raises(DropEvent):
        limiter(None, "info", {"event": "ev"})

    # Audit should pass
    result = limiter(None, "info", {"event": "ev", "_audit": True})
    assert result["event"] == "ev"


def test_thread_safety():
    """Concurrent calls don't corrupt state."""
    limiter = _TokenBucketRateLimiter(rate=100.0, burst=100)
    errors = []
    passed = {"count": 0}
    dropped = {"count": 0}
    lock = threading.Lock()

    def worker():
        for _ in range(50):
            try:
                limiter(None, "info", {"event": "threaded"})
                with lock:
                    passed["count"] += 1
            except DropEvent:
                with lock:
                    dropped["count"] += 1
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert passed["count"] + dropped["count"] == 200


def test_processor_delegates():
    """_rate_limit_processor calls global _rate_limiter."""
    import hyper2kvm.core.structured_log as sl

    original = sl._rate_limiter
    mock_limiter = Mock(return_value={"event": "ok"})
    sl._rate_limiter = mock_limiter
    try:
        result = _rate_limit_processor(None, "info", {"event": "test"})
        mock_limiter.assert_called_once()
        assert result["event"] == "ok"
    finally:
        sl._rate_limiter = original
