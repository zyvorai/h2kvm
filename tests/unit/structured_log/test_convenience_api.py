# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for log_event, log_slow_phase, log_audit, log_isolation_status, log_execution_summary, _shutdown_logging."""

from __future__ import annotations

import io
import json
from unittest.mock import Mock, patch

import pytest

import hyper2kvm.core.structured_log as sl
from hyper2kvm.core.structured_log import (
    PrintLoggerFactory,
    TraceContext,
    _configure,
    _safe_json_serializer,
    _JSONRenderer,
    _add_log_level,
    configure_structured_logging,
    log_audit,
    log_event,
    log_execution_summary,
    log_isolation_status,
    log_slow_phase,
)


@pytest.fixture()
def sync_json_capture():
    """Configure sync JSON logging to a captured StringIO and return it."""
    buf = io.StringIO()
    factory = PrintLoggerFactory(file=buf)
    renderer = _JSONRenderer(sort_keys=False, serializer=_safe_json_serializer)
    processors = [_add_log_level, renderer]
    _configure(processors, factory)
    sl._configured = True
    return buf


def _parse_output(buf):
    """Parse JSON lines from a StringIO buffer."""
    buf.seek(0)
    lines = [line.strip() for line in buf.readlines() if line.strip()]
    return [json.loads(line) for line in lines]


# --- log_event ---


def test_log_event_basic(sync_json_capture):
    log_event("test_event")
    records = _parse_output(sync_json_capture)
    assert len(records) == 1
    assert records[0]["event"] == "test_event"


def test_log_event_level(sync_json_capture):
    log_event("warn_event", level="warning")
    records = _parse_output(sync_json_capture)
    assert records[0]["level"] == "warning"


def test_log_event_extra_fields(sync_json_capture):
    log_event("ev", foo="bar", count=42)
    records = _parse_output(sync_json_capture)
    assert records[0]["foo"] == "bar"
    assert records[0]["count"] == 42


def test_log_event_invalid_level(sync_json_capture):
    """Unknown level falls back to info."""
    log_event("ev", level="nonexistent")
    records = _parse_output(sync_json_capture)
    # Should still emit (falls back to info via getattr fallback)
    assert len(records) == 1
    # The level in the record depends on which method was actually called
    assert records[0]["level"] == "info"


# --- log_slow_phase ---


def test_log_slow_phase_above_threshold(sync_json_capture):
    log_slow_phase("slow_op", duration_ms=6000.0, threshold_ms=5000.0)
    records = _parse_output(sync_json_capture)
    assert len(records) == 1
    assert records[0]["degraded"] is True


def test_log_slow_phase_below_threshold(sync_json_capture):
    log_slow_phase("fast_op", duration_ms=3000.0, threshold_ms=5000.0)
    records = _parse_output(sync_json_capture)
    assert len(records) == 0


def test_log_slow_phase_at_threshold(sync_json_capture):
    """At threshold (not strictly >) -> emits nothing."""
    log_slow_phase("edge_op", duration_ms=5000.0, threshold_ms=5000.0)
    records = _parse_output(sync_json_capture)
    assert len(records) == 0


def test_log_slow_phase_fields(sync_json_capture):
    log_slow_phase("slow", duration_ms=10000.0, threshold_ms=5000.0)
    records = _parse_output(sync_json_capture)
    assert records[0]["duration_ms"] == 10000.0
    assert records[0]["threshold_ms"] == 5000.0


# --- log_audit ---


def test_log_audit_main_pipeline(sync_json_capture):
    """Calls log_event with _audit=True."""
    log_audit("audit_event")
    records = _parse_output(sync_json_capture)
    assert len(records) == 1
    assert records[0]["_audit"] is True
    assert records[0]["channel"] == "audit"


def test_log_audit_no_writer(sync_json_capture):
    """sync mode -> no crash when _audit_writer is None."""
    sl._audit_writer = None
    log_audit("audit_event")
    records = _parse_output(sync_json_capture)
    assert len(records) == 1


def test_log_audit_context_vars(sync_json_capture):
    """Inside TraceContext -> trace_id + vm_id in audit writer record."""
    audit_buf = io.StringIO()
    from hyper2kvm.core.structured_log import AsyncLogWriter

    audit_w = AsyncLogWriter(destination=audit_buf, maxsize=100)
    sl._audit_writer = audit_w
    try:
        with TraceContext(vm_id="testvm", workflow="w", trace_id="trace123456"):
            log_audit("audit_ctx")
        audit_w.drain(timeout=2.0)
        audit_output = audit_buf.getvalue()
        # The audit writer record should contain trace_id and vm_id
        for line in audit_output.strip().split("\n"):
            if line.strip():
                parsed = json.loads(line)
                if parsed.get("event") == "audit_ctx":
                    assert parsed["trace_id"] == "trace123456"
                    assert parsed["vm_id"] == "testvm"
                    break
        else:
            # If we didn't find the record, that's a failure
            pytest.fail("audit_ctx record not found in audit writer output")
    finally:
        sl._audit_writer = None


def test_log_audit_extra_fields(sync_json_capture):
    log_audit("audit_ev", custom="value")
    records = _parse_output(sync_json_capture)
    assert records[0]["custom"] == "value"


def test_log_audit_writer_exception_swallowed(sync_json_capture):
    """Broken writer -> no propagation."""
    broken = Mock()
    broken.write.side_effect = OSError("boom")
    sl._audit_writer = broken
    try:
        # Should not raise
        log_audit("audit_broken")
    finally:
        sl._audit_writer = None


# --- log_isolation_status ---


def test_isolation_no_conflicts(sync_json_capture):
    """[] -> log_event (not audit), conflict_count=0."""
    log_isolation_status("exclusive", host_conflicts=[])
    records = _parse_output(sync_json_capture)
    assert len(records) == 1
    assert records[0]["conflict_count"] == 0
    # Should NOT have _audit flag (goes through log_event, not log_audit)
    assert "_audit" not in records[0]


def test_isolation_with_conflicts(sync_json_capture):
    """["host1"] -> log_audit, conflict_count=1."""
    log_isolation_status("shared", host_conflicts=["host1"])
    records = _parse_output(sync_json_capture)
    # log_audit calls log_event with _audit=True
    audit_records = [r for r in records if r.get("_audit")]
    assert len(audit_records) == 1
    assert audit_records[0]["conflict_count"] == 1


def test_isolation_metrics_silent(sync_json_capture):
    """Missing metrics -> no exception."""
    log_isolation_status("shared", host_conflicts=["h1"])
    # If we get here, no exception was raised


# --- log_execution_summary ---


def test_execution_summary_success(sync_json_capture):
    log_execution_summary(
        vm_id="vm1",
        workflow="migrate",
        total_duration_ms=1000.0,
        status="success",
    )
    records = _parse_output(sync_json_capture)
    assert len(records) == 1
    assert records[0]["level"] == "info"
    assert records[0]["status"] == "success"


def test_execution_summary_failure(sync_json_capture):
    log_execution_summary(
        vm_id="vm1",
        workflow="migrate",
        total_duration_ms=1000.0,
        status="failure",
        error="disk full",
    )
    records = _parse_output(sync_json_capture)
    assert len(records) == 1
    assert records[0]["level"] == "error"
    assert records[0]["error"] == "disk full"


def test_execution_summary_phases(sync_json_capture):
    log_execution_summary(
        vm_id="vm1",
        workflow="migrate",
        phases={"nbd": 100.0, "lvm": 200.0},
        total_duration_ms=300.0,
        status="success",
    )
    records = _parse_output(sync_json_capture)
    assert records[0]["phases"] == {"nbd": 100.0, "lvm": 200.0}


def test_execution_summary_metrics_silent(sync_json_capture):
    """Missing metrics -> no exception."""
    log_execution_summary(
        vm_id="vm1",
        workflow="migrate",
        total_duration_ms=100.0,
        status="success",
    )


# --- _shutdown_logging ---


def test_shutdown_drains_writers():
    """_shutdown_logging drains both writers."""
    main_w = Mock()
    audit_w = Mock()
    sl._main_writer = main_w
    sl._audit_writer = audit_w
    try:
        sl._shutdown_logging()
        main_w.drain.assert_called_once_with(timeout=5.0)
        audit_w.drain.assert_called_once_with(timeout=2.0)
    finally:
        sl._main_writer = None
        sl._audit_writer = None
