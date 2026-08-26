# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for log processors: _add_log_level, _format_exc_info, _UnicodeDecoder,
_add_logger_name, _level_filter, add_envelope, _enforce_field_limits."""

from __future__ import annotations

import logging
import os
from unittest.mock import Mock

import pytest

from hyper2kvm.core.structured_log import (
    DropEvent,
    _add_log_level,
    _add_logger_name,
    _enforce_field_limits,
    _format_exc_info,
    _level_filter,
    _UnicodeDecoder,
    _current_level,
    _trace_id_var,
    _vm_id_var,
    _workflow_var,
    _component_var,
    _span_id_var,
    _parent_span_id_var,
    add_envelope,
    SERVICE_NAME,
)


# --- _add_log_level ---


def test_add_log_level_sets_level(mock_logger, make_event_dict):
    ed = make_event_dict()
    result = _add_log_level(mock_logger, "warning", ed)
    assert result["level"] == "warning"


def test_add_log_level_preserves_fields(mock_logger, make_event_dict):
    ed = make_event_dict(foo="bar")
    result = _add_log_level(mock_logger, "info", ed)
    assert result["foo"] == "bar"
    assert result["event"] == "test"


# --- _format_exc_info ---


def test_format_exc_info_exception_instance(mock_logger, make_event_dict):
    exc = ValueError("oops")
    try:
        raise exc
    except ValueError:
        ed = make_event_dict(exc_info=exc)
        result = _format_exc_info(mock_logger, "error", ed)
    assert "exception" in result
    assert "ValueError" in result["exception"]
    assert "exc_info" not in result


def test_format_exc_info_true_in_except(mock_logger, make_event_dict):
    try:
        raise RuntimeError("fail")
    except RuntimeError:
        ed = make_event_dict(exc_info=True)
        result = _format_exc_info(mock_logger, "error", ed)
    assert "exception" in result
    assert "RuntimeError" in result["exception"]


def test_format_exc_info_true_outside_except(mock_logger, make_event_dict):
    ed = make_event_dict(exc_info=True)
    result = _format_exc_info(mock_logger, "error", ed)
    # Outside except block, sys.exc_info() returns (None, None, None)
    assert "exception" not in result


def test_format_exc_info_tuple(mock_logger, make_event_dict):
    try:
        raise TypeError("bad")
    except TypeError:
        import sys

        info = sys.exc_info()
        ed = make_event_dict(exc_info=info)
        result = _format_exc_info(mock_logger, "error", ed)
    assert "exception" in result
    assert "TypeError" in result["exception"]


def test_format_exc_info_removes_key(mock_logger, make_event_dict):
    ed = make_event_dict(exc_info=None)
    result = _format_exc_info(mock_logger, "info", ed)
    assert "exc_info" not in result


def test_format_exc_info_absent_key(mock_logger, make_event_dict):
    ed = make_event_dict()
    result = _format_exc_info(mock_logger, "info", ed)
    assert "exception" not in result
    assert result["event"] == "test"


# --- _UnicodeDecoder ---


def test_unicode_decoder_decodes_bytes(mock_logger, make_event_dict):
    dec = _UnicodeDecoder()
    ed = make_event_dict(data=b"hello")
    result = dec(mock_logger, "info", ed)
    assert result["data"] == "hello"


def test_unicode_decoder_leaves_strings(mock_logger, make_event_dict):
    dec = _UnicodeDecoder()
    ed = make_event_dict(data="already str")
    result = dec(mock_logger, "info", ed)
    assert result["data"] == "already str"


def test_unicode_decoder_custom_encoding(mock_logger, make_event_dict):
    dec = _UnicodeDecoder(encoding="latin-1")
    ed = make_event_dict(data="café".encode("latin-1"))
    result = dec(mock_logger, "info", ed)
    assert result["data"] == "café"


def test_unicode_decoder_replace_errors(mock_logger, make_event_dict):
    dec = _UnicodeDecoder(errors="replace")
    ed = make_event_dict(data=b"\xff\xfe")
    result = dec(mock_logger, "info", ed)
    assert isinstance(result["data"], str)


# --- _add_logger_name ---


def test_add_logger_name_with_record(mock_logger, make_event_dict):
    record = logging.LogRecord("mylogger", logging.INFO, "f", 1, "msg", (), None)
    ed = make_event_dict(_record=record)
    result = _add_logger_name(mock_logger, "info", ed)
    assert result["logger"] == "mylogger"


def test_add_logger_name_without_record(mock_logger, make_event_dict):
    ed = make_event_dict()
    result = _add_logger_name(mock_logger, "info", ed)
    assert "logger" not in result


# --- _level_filter ---


def test_level_filter_passes_at_threshold(mock_logger, make_event_dict):
    import hyper2kvm.core.structured_log as sl

    sl._current_level = "warning"
    ed = make_event_dict(level="warning")
    result = _level_filter(mock_logger, "warning", ed)
    assert result["event"] == "test"


def test_level_filter_passes_above_threshold(mock_logger, make_event_dict):
    import hyper2kvm.core.structured_log as sl

    sl._current_level = "warning"
    ed = make_event_dict(level="error")
    result = _level_filter(mock_logger, "error", ed)
    assert result["event"] == "test"


def test_level_filter_drops_below_threshold(mock_logger, make_event_dict):
    import hyper2kvm.core.structured_log as sl

    sl._current_level = "warning"
    ed = make_event_dict(level="debug")
    with pytest.raises(DropEvent):
        _level_filter(mock_logger, "debug", ed)


def test_level_filter_defaults_for_missing_level(mock_logger, make_event_dict):
    import hyper2kvm.core.structured_log as sl

    sl._current_level = "debug"
    ed = make_event_dict()  # no level key
    result = _level_filter(mock_logger, "info", ed)
    assert result["event"] == "test"


def test_level_filter_defaults_for_non_string_level(mock_logger, make_event_dict):
    import hyper2kvm.core.structured_log as sl

    sl._current_level = "debug"
    ed = make_event_dict(level=42)
    result = _level_filter(mock_logger, "info", ed)
    assert result["event"] == "test"


def test_level_filter_case_insensitive(mock_logger, make_event_dict):
    import hyper2kvm.core.structured_log as sl

    sl._current_level = "warning"
    ed = make_event_dict(level="WARNING")
    result = _level_filter(mock_logger, "warning", ed)
    assert result["event"] == "test"


# --- add_envelope ---


def test_add_envelope_injects_defaults(mock_logger, make_event_dict):
    ed = make_event_dict()
    result = add_envelope(mock_logger, "info", ed)
    assert "ts" in result
    assert result["service"] == SERVICE_NAME
    assert "host" in result
    assert result["pid"] == os.getpid()


def test_add_envelope_includes_context_vars(mock_logger, make_event_dict):
    tok_trace = _trace_id_var.set("t123")
    tok_vm = _vm_id_var.set("vm1")
    tok_wf = _workflow_var.set("migrate")
    tok_comp = _component_var.set("core")
    try:
        ed = make_event_dict()
        result = add_envelope(mock_logger, "info", ed)
        assert result["trace_id"] == "t123"
        assert result["vm_id"] == "vm1"
        assert result["workflow"] == "migrate"
        assert result["component"] == "core"
    finally:
        _trace_id_var.reset(tok_trace)
        _vm_id_var.reset(tok_vm)
        _workflow_var.reset(tok_wf)
        _component_var.reset(tok_comp)


def test_add_envelope_omits_none_vars(mock_logger, make_event_dict):
    # Default context vars are None
    ed = make_event_dict()
    result = add_envelope(mock_logger, "info", ed)
    assert "trace_id" not in result
    assert "vm_id" not in result


def test_add_envelope_explicit_fields_win(mock_logger, make_event_dict):
    ed = make_event_dict(service="custom-svc", host="custom-host")
    result = add_envelope(mock_logger, "info", ed)
    assert result["service"] == "custom-svc"
    assert result["host"] == "custom-host"


def test_add_envelope_span_hierarchy(mock_logger, make_event_dict):
    tok_span = _span_id_var.set("span1")
    tok_parent = _parent_span_id_var.set("parent1")
    try:
        ed = make_event_dict()
        result = add_envelope(mock_logger, "info", ed)
        assert result["span_id"] == "span1"
        assert result["parent_span_id"] == "parent1"
    finally:
        _span_id_var.reset(tok_span)
        _parent_span_id_var.reset(tok_parent)


# --- _enforce_field_limits ---


def test_enforce_field_limits_truncates_long_str(mock_logger, make_event_dict):
    long_str = "x" * 10000
    ed = make_event_dict(big=long_str)
    result = _enforce_field_limits(mock_logger, "info", ed)
    assert len(result["big"]) < len(long_str)
    assert result["big"].endswith("...<truncated>")


def test_enforce_field_limits_truncates_long_bytes(mock_logger, make_event_dict):
    long_bytes = b"y" * 10000
    ed = make_event_dict(big=long_bytes)
    result = _enforce_field_limits(mock_logger, "info", ed)
    assert len(result["big"]) < len(long_bytes)
    assert result["big"].endswith(b"...<truncated>")


def test_enforce_field_limits_caps_nesting(mock_logger, make_event_dict):
    # Build deep nesting: 6 levels
    deep = {"a": {"b": {"c": {"d": {"e": {"f": "leaf"}}}}}}
    ed = make_event_dict(nested=deep)
    result = _enforce_field_limits(mock_logger, "info", ed)
    # At depth 4, collections should be truncated to string
    nested = result["nested"]
    level = nested
    for key in ("a", "b", "c"):
        assert isinstance(level, dict)
        level = level[key]
    # At depth 4, the inner dict's values are replaced with truncation markers
    assert isinstance(level, dict)
    assert level["d"] == "...<truncated>"


def test_enforce_field_limits_preserves_short(mock_logger, make_event_dict):
    ed = make_event_dict(short="ok")
    result = _enforce_field_limits(mock_logger, "info", ed)
    assert result["short"] == "ok"


def test_enforce_field_limits_handles_lists(mock_logger, make_event_dict):
    ed = make_event_dict(items=["a", "b", "c"])
    result = _enforce_field_limits(mock_logger, "info", ed)
    assert result["items"] == ["a", "b", "c"]


def test_enforce_field_limits_handles_tuples(mock_logger, make_event_dict):
    ed = make_event_dict(items=("a", "b"))
    result = _enforce_field_limits(mock_logger, "info", ed)
    assert result["items"] == ("a", "b")
