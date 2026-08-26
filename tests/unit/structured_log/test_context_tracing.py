# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for TraceContext, PhaseTimer, generate_trace_id, _generate_span_id."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from h2kvm.core.structured_log import (
    PhaseTimer,
    TraceContext,
    _generate_span_id,
    _parent_span_id_var,
    _span_id_var,
    _trace_id_var,
    _vm_id_var,
    _workflow_var,
    _component_var,
    generate_trace_id,
)


# --- generate_trace_id ---


def test_generate_trace_id_length():
    tid = generate_trace_id()
    assert len(tid) == 12
    # All hex chars
    int(tid, 16)


def test_generate_trace_id_uniqueness():
    t1 = generate_trace_id()
    t2 = generate_trace_id()
    assert t1 != t2


# --- _generate_span_id ---


def test_generate_span_id_length():
    sid = _generate_span_id()
    assert len(sid) == 8
    int(sid, 16)


# --- TraceContext ---


def test_trace_context_sets_vars():
    with TraceContext(vm_id="vm1", workflow="migrate", component="core"):
        assert _trace_id_var.get() is not None
        assert _vm_id_var.get() == "vm1"
        assert _workflow_var.get() == "migrate"
        assert _component_var.get() == "core"


def test_trace_context_clears_on_exit():
    before_trace = _trace_id_var.get()
    before_vm = _vm_id_var.get()

    with TraceContext(vm_id="vm1", workflow="w"):
        pass

    assert _trace_id_var.get() == before_trace
    assert _vm_id_var.get() == before_vm


def test_trace_context_auto_trace_id():
    """Omit trace_id -> generated."""
    with TraceContext(vm_id="v", workflow="w") as ctx:
        assert ctx.trace_id is not None
        assert len(ctx.trace_id) == 12


def test_trace_context_custom_trace_id():
    """Explicit trace_id used."""
    with TraceContext(vm_id="v", workflow="w", trace_id="custom123456") as ctx:
        assert ctx.trace_id == "custom123456"
        assert _trace_id_var.get() == "custom123456"


def test_trace_context_sets_root_span():
    """span_id set, parent_span_id = None."""
    with TraceContext(vm_id="v", workflow="w"):
        assert _span_id_var.get() is not None
        assert _parent_span_id_var.get() is None


def test_trace_context_nested_restore():
    """Inner exits -> outer vars restored."""
    with TraceContext(vm_id="outer", workflow="w1") as outer:
        outer_trace = _trace_id_var.get()
        outer_span = _span_id_var.get()

        with TraceContext(vm_id="inner", workflow="w2") as inner:
            assert _vm_id_var.get() == "inner"
            assert _trace_id_var.get() != outer_trace

        assert _vm_id_var.get() == "outer"
        assert _trace_id_var.get() == outer_trace
        assert _span_id_var.get() == outer_span


# --- PhaseTimer ---


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_logs_start(mock_log_event):
    with PhaseTimer("start_ev", "complete_ev", phase="test"):
        # On enter, log_event called with event_start
        mock_log_event.assert_called()
        args = mock_log_event.call_args_list[0]
        assert args[0][0] == "start_ev"


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_logs_complete_success(mock_log_event):
    with PhaseTimer("start_ev", "complete_ev", phase="test"):
        pass
    # Second call should be the complete event
    assert mock_log_event.call_count == 2
    complete_call = mock_log_event.call_args_list[1]
    assert complete_call[0][0] == "complete_ev"
    assert complete_call[1]["status"] == "success"
    assert "duration_ms" in complete_call[1]


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_logs_complete_failure(mock_log_event):
    with pytest.raises(ValueError):
        with PhaseTimer("start_ev", "complete_ev", phase="test"):
            raise ValueError("boom")
    complete_call = mock_log_event.call_args_list[1]
    assert complete_call[1]["status"] == "failure"


@patch("h2kvm.core.structured_log.log_event")
@patch("time.monotonic")
def test_phase_timer_duration_positive(mock_monotonic, mock_log_event):
    mock_monotonic.side_effect = [100.0, 100.05]
    with PhaseTimer("s", "c", phase="p"):
        pass
    complete_call = mock_log_event.call_args_list[1]
    assert complete_call[1]["duration_ms"] == 50.0


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_child_span(mock_log_event):
    """Inside timer, span_id differs, parent_span_id = outer."""
    outer_span_tok = _span_id_var.set("outer-span")
    try:
        with PhaseTimer("s", "c", phase="p"):
            inner_span = _span_id_var.get()
            parent = _parent_span_id_var.get()
            assert inner_span != "outer-span"
            assert parent == "outer-span"
    finally:
        _span_id_var.reset(outer_span_tok)


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_restores_span(mock_log_event):
    """After exit, span vars restored."""
    outer_span_tok = _span_id_var.set("outer-span")
    outer_parent_tok = _parent_span_id_var.set(None)
    try:
        with PhaseTimer("s", "c", phase="p"):
            pass
        assert _span_id_var.get() == "outer-span"
        assert _parent_span_id_var.get() is None
    finally:
        _span_id_var.reset(outer_span_tok)
        _parent_span_id_var.reset(outer_parent_tok)


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_extra_kwargs(mock_log_event):
    """Extra kwargs forwarded to both log calls."""
    with PhaseTimer("s", "c", phase="p", custom_field="val"):
        pass
    for call in mock_log_event.call_args_list:
        assert call[1]["custom_field"] == "val"


@patch("h2kvm.core.structured_log.log_event")
def test_phase_timer_metrics_import_silent(mock_log_event):
    """Missing metrics module -> no exception."""
    # PhaseTimer tries to import metrics at exit — should not raise
    with PhaseTimer("s", "c", phase="nbd"):
        pass
    # If we get here, no exception was raised
