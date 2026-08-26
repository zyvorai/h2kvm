# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for _JSONRenderer, _ConsoleRenderer, _TimeStamper, ProcessorFormatter."""

from __future__ import annotations

import json
import logging
from unittest.mock import Mock

from h2kvm.core.structured_log import (
    ProcessorFormatter,
    _ConsoleRenderer,
    _JSONRenderer,
    _TimeStamper,
    _safe_json_serializer,
)


# --- _JSONRenderer ---


def test_json_renderer_returns_str(mock_logger, make_event_dict):
    renderer = _JSONRenderer()
    ed = make_event_dict(level="info")
    result = renderer(mock_logger, "info", ed)
    assert isinstance(result, str)


def test_json_renderer_sorted_keys_default(mock_logger, make_event_dict):
    renderer = _JSONRenderer()
    ed = make_event_dict(z_field=1, a_field=2)
    result = renderer(mock_logger, "info", ed)
    parsed = json.loads(result)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_json_renderer_unsorted(mock_logger, make_event_dict):
    renderer = _JSONRenderer(sort_keys=False)
    ed = make_event_dict()
    result = renderer(mock_logger, "info", ed)
    # Should still be valid JSON
    parsed = json.loads(result)
    assert parsed["event"] == "test"


def test_json_renderer_custom_serializer(mock_logger, make_event_dict):
    renderer = _JSONRenderer(serializer=_safe_json_serializer)
    ed = make_event_dict()
    result = renderer(mock_logger, "info", ed)
    parsed = json.loads(result)
    assert parsed["event"] == "test"


def test_json_renderer_extra_kwargs(mock_logger, make_event_dict):
    renderer = _JSONRenderer(indent=2)
    ed = make_event_dict()
    result = renderer(mock_logger, "info", ed)
    assert "\n" in result  # indented output is multi-line


# --- _ConsoleRenderer ---


def test_console_renderer_returns_str(mock_logger, make_event_dict):
    renderer = _ConsoleRenderer()
    ed = make_event_dict()
    result = renderer(mock_logger, "info", ed)
    assert isinstance(result, str)


def test_console_renderer_format_with_all_fields(mock_logger, make_event_dict):
    renderer = _ConsoleRenderer()
    ed = make_event_dict(ts="2024-01-01T00:00:00Z", level="info")
    result = renderer(mock_logger, "info", ed)
    assert "[2024-01-01T00:00:00Z]" in result
    assert "INFO" in result
    assert "test" in result


def test_console_renderer_pops_consumed_keys(mock_logger, make_event_dict):
    renderer = _ConsoleRenderer()
    ed = make_event_dict(ts="ts", level="info", extra="val")
    result = renderer(mock_logger, "info", ed)
    assert "extra=val" in result


def test_console_renderer_hides_underscore_keys(mock_logger, make_event_dict):
    renderer = _ConsoleRenderer()
    ed = make_event_dict(_internal="hidden", visible="shown")
    result = renderer(mock_logger, "info", ed)
    assert "_internal" not in result
    assert "visible=shown" in result


def test_console_renderer_sorts_remaining(mock_logger, make_event_dict):
    renderer = _ConsoleRenderer()
    ed = make_event_dict(zz="last", aa="first")
    result = renderer(mock_logger, "info", ed)
    idx_aa = result.find("aa=")
    idx_zz = result.find("zz=")
    assert idx_aa < idx_zz


def test_console_renderer_handles_missing_fields(mock_logger):
    renderer = _ConsoleRenderer()
    ed = {"event": "bare"}
    result = renderer(mock_logger, "info", ed)
    assert "bare" in result


# --- _TimeStamper ---


def test_timestamper_iso_utc(mock_logger, make_event_dict):
    ts = _TimeStamper(fmt="iso", utc=True)
    ed = make_event_dict()
    result = ts(mock_logger, "info", ed)
    assert "timestamp" in result
    assert "+00:00" in result["timestamp"] or "Z" in result["timestamp"]


def test_timestamper_local(mock_logger, make_event_dict):
    ts = _TimeStamper(fmt="iso", utc=False)
    ed = make_event_dict()
    result = ts(mock_logger, "info", ed)
    assert "timestamp" in result


def test_timestamper_custom_strftime(mock_logger, make_event_dict):
    ts = _TimeStamper(fmt="%Y-%m-%d", utc=True)
    ed = make_event_dict()
    result = ts(mock_logger, "info", ed)
    assert "timestamp" in result
    # Should be date-only format
    parts = result["timestamp"].split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # year


# --- ProcessorFormatter ---


def test_processor_formatter_formats_log_record():
    def renderer(_logger, _method, ed):
        return json.dumps({"event": ed["event"]})

    fmt = ProcessorFormatter(processors=[renderer])
    record = logging.LogRecord("test", logging.INFO, "f", 1, "hello", (), None)
    result = fmt.format(record)
    parsed = json.loads(result)
    assert parsed["event"] == "hello"


def test_processor_formatter_runs_foreign_pre_chain():
    captured = {}

    def pre_proc(_logger, _method, ed):
        ed["pre_chain"] = True
        captured.update(ed)
        return ed

    def renderer(_logger, _method, ed):
        return json.dumps({"pre_chain": ed.get("pre_chain", False)})

    fmt = ProcessorFormatter(
        processors=[renderer],
        foreign_pre_chain=[pre_proc],
    )
    record = logging.LogRecord("test", logging.INFO, "f", 1, "msg", (), None)
    result = fmt.format(record)
    parsed = json.loads(result)
    assert parsed["pre_chain"] is True


def test_processor_formatter_string_result_returns_early():
    """If a processor returns str, remaining processors are skipped."""
    call_count = {"n": 0}

    def early_return(_logger, _method, ed):
        return "early"

    def never_called(_logger, _method, ed):
        call_count["n"] += 1
        return ed

    fmt = ProcessorFormatter(processors=[early_return, never_called])
    record = logging.LogRecord("test", logging.INFO, "f", 1, "msg", (), None)
    result = fmt.format(record)
    assert result == "early"
    assert call_count["n"] == 0


def test_processor_formatter_dict_fallback():
    """If final processor returns dict, str(dict) is used."""

    def passthrough(_logger, _method, ed):
        return ed

    fmt = ProcessorFormatter(processors=[passthrough])
    record = logging.LogRecord("test", logging.INFO, "f", 1, "msg", (), None)
    result = fmt.format(record)
    assert "msg" in result


def test_processor_formatter_record_populated():
    """_record is set in event_dict."""
    captured = {}

    def inspector(_logger, _method, ed):
        captured["record"] = ed.get("_record")
        return str(ed)

    fmt = ProcessorFormatter(processors=[inspector])
    record = logging.LogRecord("myname", logging.WARNING, "f", 1, "msg", (), None)
    fmt.format(record)
    assert captured["record"] is record
    assert captured["record"].name == "myname"
