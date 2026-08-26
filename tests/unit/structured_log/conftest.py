# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures for structured_log tests."""

from __future__ import annotations

import io
from unittest.mock import Mock

import pytest

from h2kvm.core import structured_log as sl


@pytest.fixture(autouse=True)
def reset_global_state():
    """Save and restore all module-level globals and contextvars."""
    # Save module globals
    saved = {
        "_configured": sl._configured,
        "_global_processors": sl._global_processors[:],
        "_global_logger_factory": sl._global_logger_factory,
        "_custom_processors": sl._custom_processors[:],
        "_current_level": sl._current_level,
        "_sampling_rules": dict(sl._sampling_rules),
        "_main_writer": sl._main_writer,
        "_audit_writer": sl._audit_writer,
        "_rate_limiter": sl._rate_limiter,
    }

    # Save contextvar tokens
    ctx_vars = [
        sl._trace_id_var,
        sl._vm_id_var,
        sl._workflow_var,
        sl._component_var,
        sl._span_id_var,
        sl._parent_span_id_var,
    ]
    tokens = [var.set(var.get()) for var in ctx_vars]

    yield

    # Drain any async writers created during the test
    if sl._main_writer is not None and sl._main_writer is not saved["_main_writer"]:
        try:
            sl._main_writer.drain(timeout=1.0)
        except Exception:
            pass
    if sl._audit_writer is not None and sl._audit_writer is not saved["_audit_writer"]:
        try:
            sl._audit_writer.drain(timeout=1.0)
        except Exception:
            pass

    # Restore module globals
    sl._configured = saved["_configured"]
    sl._global_processors = saved["_global_processors"]
    sl._global_logger_factory = saved["_global_logger_factory"]
    sl._custom_processors[:] = saved["_custom_processors"]
    sl._current_level = saved["_current_level"]
    sl._sampling_rules.clear()
    sl._sampling_rules.update(saved["_sampling_rules"])
    sl._main_writer = saved["_main_writer"]
    sl._audit_writer = saved["_audit_writer"]
    sl._rate_limiter = saved["_rate_limiter"]

    # Restore contextvars
    for tok in tokens:
        tok.var.reset(tok)


@pytest.fixture()
def capture_output():
    """Return a StringIO for capturing logger output."""
    return io.StringIO()


@pytest.fixture()
def mock_logger():
    """Return a Mock with a .msg method, for processor tests."""
    return Mock()


@pytest.fixture()
def make_event_dict():
    """Factory: make(event="test", **kw) -> dict."""

    def _make(event: str = "test", **kw):
        return {"event": event, **kw}

    return _make
