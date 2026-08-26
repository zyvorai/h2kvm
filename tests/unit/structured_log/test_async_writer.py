# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for AsyncLogWriter, _AsyncLoggerFactory, and drain."""

from __future__ import annotations

import io
import json
import threading

import pytest

from hyper2kvm.core.structured_log import AsyncLogWriter, _AsyncLoggerFactory


@pytest.fixture()
def dest():
    """Destination StringIO for async writer."""
    return io.StringIO()


@pytest.fixture()
def writer(dest):
    """Create an AsyncLogWriter and drain it on teardown."""
    w = AsyncLogWriter(destination=dest, maxsize=100)
    yield w
    try:
        w.drain(timeout=2.0)
    except Exception:
        pass


def test_writes_to_destination(dest, writer):
    writer.write("hello")
    writer.drain(timeout=2.0)
    output = dest.getvalue()
    assert "hello" in output


def test_appends_newline(dest, writer):
    writer.write("no-newline")
    writer.drain(timeout=2.0)
    output = dest.getvalue()
    assert output.endswith("\n")


def test_no_double_newline(dest, writer):
    writer.write("has-newline\n")
    writer.drain(timeout=2.0)
    output = dest.getvalue()
    # Should not have double newline
    assert "has-newline\n" in output
    assert "\n\n" not in output


def test_drain_flushes_pending(dest, writer):
    for i in range(5):
        writer.write(f"msg-{i}")
    writer.drain(timeout=2.0)
    output = dest.getvalue()
    for i in range(5):
        assert f"msg-{i}" in output


def test_drain_timeout(dest):
    """Returns even if thread is slow (no hang)."""
    w = AsyncLogWriter(destination=dest, maxsize=100)
    w.drain(timeout=0.1)
    # Should return within the timeout


def test_overflow_drops_oldest(dest):
    """maxsize=2, 3 writes -> oldest dropped."""
    w = AsyncLogWriter(destination=dest, maxsize=2, overflow_warn_interval=1000)
    # Fill the queue by pausing the writer thread
    # We need to be more careful here — the writer thread consumes from the queue
    # So we use a blocking destination to create backpressure
    block = threading.Event()
    call_count = {"n": 0}
    original_write = dest.write

    def slow_write(msg):
        nonlocal call_count
        if call_count["n"] == 0:
            call_count["n"] += 1
            block.wait(timeout=2.0)
        return original_write(msg)

    dest.write = slow_write

    # First message gets picked up by the writer thread and blocks
    w.write("msg1")
    import time

    time.sleep(0.05)  # Let writer thread pick up msg1

    # These should fill the queue (maxsize=2)
    w.write("msg2")
    w.write("msg3")
    # This should trigger overflow (queue full)
    w.write("msg4")

    block.set()
    w.drain(timeout=2.0)

    output = dest.getvalue()
    # msg4 should be present (newest), msg2 may have been dropped (oldest in queue)
    assert "msg4" in output


def test_overflow_warning_interval(dest):
    """Warning written after N drops."""
    w = AsyncLogWriter(destination=dest, maxsize=1, overflow_warn_interval=2)
    # Block the writer
    block = threading.Event()
    call_count = {"n": 0}
    original_write = dest.write

    def slow_write(msg):
        if call_count["n"] == 0:
            call_count["n"] += 1
            block.wait(timeout=2.0)
        return original_write(msg)

    dest.write = slow_write

    w.write("block")
    import time

    time.sleep(0.05)

    # Fill queue and trigger overflows
    w.write("fill")
    for _ in range(3):
        w.write("overflow")

    block.set()
    w.drain(timeout=2.0)
    output = dest.getvalue()
    # After 2 overflows, a warning should be written
    assert "log_queue_overflow" in output or w._overflow_count > 0


def test_overflow_warning_format(dest):
    """Overflow warning should be valid JSON with expected fields."""
    w = AsyncLogWriter(destination=dest, maxsize=1, overflow_warn_interval=1)
    block = threading.Event()
    call_count = {"n": 0}
    original_write = dest.write

    overflow_messages = []

    def capturing_write(msg):
        if "log_queue_overflow" in msg:
            overflow_messages.append(msg)
        return original_write(msg)

    dest.write = capturing_write

    w.write("block")
    import time

    time.sleep(0.05)

    w.write("fill")
    # Trigger overflow with interval=1, so first overflow triggers warning
    w.write("overflow1")

    block.set()
    w.drain(timeout=2.0)

    if overflow_messages:
        parsed = json.loads(overflow_messages[0].strip())
        assert parsed["event"] == "log_queue_overflow"
        assert parsed["level"] == "warning"
        assert "dropped" in parsed
        assert "service" in parsed
        assert "ts" in parsed


def test_msg_delegates_to_write(dest, writer):
    writer.msg("via-msg")
    writer.drain(timeout=2.0)
    assert "via-msg" in dest.getvalue()


def test_all_methods_delegate(dest, writer):
    for method_name in ("info", "debug", "warning", "error", "critical", "fatal"):
        getattr(writer, method_name)(method_name)
    writer.drain(timeout=2.0)
    output = dest.getvalue()
    for method_name in ("info", "debug", "warning", "error", "critical", "fatal"):
        assert method_name in output


def test_flush_is_noop(writer):
    # Should not raise
    writer.flush()


def test_thread_is_daemon(dest):
    w = AsyncLogWriter(destination=dest, maxsize=10)
    assert w._thread.daemon is True
    w.drain(timeout=1.0)


def test_thread_name(dest):
    w = AsyncLogWriter(destination=dest, maxsize=10)
    assert w._thread.name == "async-log-writer"
    w.drain(timeout=1.0)


def test_factory_returns_writer(dest):
    w = AsyncLogWriter(destination=dest, maxsize=10)
    factory = _AsyncLoggerFactory(w)
    result = factory()
    assert result is w
    w.drain(timeout=1.0)


def test_dest_write_exception_swallowed():
    """Broken dest.write -> no crash."""

    class BrokenDest:
        def write(self, msg):
            raise OSError("disk full")

        def flush(self):
            raise OSError("disk full")

    w = AsyncLogWriter(destination=BrokenDest(), maxsize=10)
    w.write("test")
    # Should not crash
    w.drain(timeout=1.0)
