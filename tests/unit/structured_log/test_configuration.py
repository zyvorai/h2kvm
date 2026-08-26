# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for configure_structured_logging, set_log_level, add_processor, _ensure_configured, _get_logger."""

from __future__ import annotations

import h2kvm.core.structured_log as sl
from h2kvm.core.structured_log import (
    AsyncLogWriter,
    BoundLogger,
    PrintLoggerFactory,
    _ConsoleRenderer,
    _JSONRenderer,
    add_processor,
    configure_structured_logging,
    set_log_level,
)


# --- configure_structured_logging ---


def test_json_output_renderer():
    configure_structured_logging(json_output=True, async_writes=False)
    # Last processor in chain should be _JSONRenderer
    last = sl._global_processors[-1]
    assert isinstance(last, _JSONRenderer)


def test_console_output_renderer():
    configure_structured_logging(json_output=False, async_writes=False)
    last = sl._global_processors[-1]
    assert isinstance(last, _ConsoleRenderer)


def test_async_creates_writers():
    configure_structured_logging(json_output=True, async_writes=True)
    assert sl._main_writer is not None
    assert sl._audit_writer is not None
    assert isinstance(sl._main_writer, AsyncLogWriter)
    assert isinstance(sl._audit_writer, AsyncLogWriter)


def test_sync_no_writers():
    configure_structured_logging(json_output=True, async_writes=False)
    assert sl._main_writer is None
    assert sl._audit_writer is None


def test_sets_configured_flag():
    sl._configured = False
    configure_structured_logging(json_output=True, async_writes=False)
    assert sl._configured is True


def test_pipeline_has_all_builtins():
    configure_structured_logging(json_output=True, async_writes=False)
    # Check key processors are present by checking the chain length and some known items
    assert len(sl._global_processors) >= 8  # At least 8 built-in processors
    # Verify specific processors by function identity
    assert sl._add_log_level in sl._global_processors
    assert sl._level_filter in sl._global_processors
    assert sl.add_envelope in sl._global_processors
    assert sl._enforce_field_limits in sl._global_processors
    assert sl._rate_limit_processor in sl._global_processors
    assert sl._sampling_processor in sl._global_processors
    assert sl._format_exc_info in sl._global_processors


def test_custom_processors_included():
    def my_proc(_logger, _method, ed):
        return ed

    sl._custom_processors.clear()
    add_processor(my_proc)
    configure_structured_logging(json_output=True, async_writes=False)
    assert my_proc in sl._global_processors


# --- set_log_level ---


def test_set_log_level_changes_level():
    set_log_level("error")
    assert sl._current_level == "error"


def test_set_log_level_resets_configured():
    sl._configured = True
    set_log_level("warning")
    assert sl._configured is False


def test_set_log_level_case_insensitive():
    set_log_level("WARNING")
    assert sl._current_level == "warning"


# --- add_processor ---


def test_add_processor_appends():
    sl._custom_processors.clear()

    def fn(_l, _m, ed):
        return ed

    add_processor(fn)
    assert fn in sl._custom_processors


def test_add_processor_resets_configured():
    sl._configured = True

    def fn(_l, _m, ed):
        return ed

    add_processor(fn)
    assert sl._configured is False


# --- _ensure_configured ---


def test_ensure_configured_auto():
    sl._configured = False
    sl._ensure_configured()
    assert sl._configured is True


def test_ensure_configured_noop():
    configure_structured_logging(json_output=True, async_writes=False)
    procs_before = sl._global_processors[:]
    sl._ensure_configured()
    # Should not have reconfigured
    assert sl._global_processors == procs_before


# --- _get_logger ---


def test_get_logger_returns_bound():
    configure_structured_logging(json_output=True, async_writes=False)
    logger = sl._get_logger()
    assert isinstance(logger, BoundLogger)


# --- max_queue_size ---


def test_max_queue_size_forwarded():
    configure_structured_logging(json_output=True, async_writes=True, max_queue_size=42)
    assert sl._main_writer is not None
    assert sl._main_writer._queue.maxsize == 42
