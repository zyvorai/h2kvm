# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for DropEvent, PrintLogger, PrintLoggerFactory, BoundLogger, _configure, _get_bound_logger."""

from __future__ import annotations

import io
import sys
from unittest.mock import Mock, patch

from hyper2kvm.core.structured_log import (
    BoundLogger,
    DropEvent,
    PrintLogger,
    PrintLoggerFactory,
    _configure,
    _get_bound_logger,
)


# --- DropEvent ---


def test_drop_event_is_exception():
    assert issubclass(DropEvent, Exception)


def test_drop_event_can_be_raised():
    try:
        raise DropEvent
    except DropEvent:
        pass  # expected


# --- PrintLogger ---


def test_print_logger_writes_to_file(capture_output):
    logger = PrintLogger(file=capture_output)
    logger.msg("hello")
    assert capture_output.getvalue() == "hello\n"


def test_print_logger_flushes():
    buf = Mock()
    logger = PrintLogger(file=buf)
    logger.msg("test")
    buf.flush.assert_called_once()


def test_print_logger_defaults_stdout():
    logger = PrintLogger()
    assert logger._file is sys.stdout


def test_print_logger_all_methods_delegate(capture_output):
    logger = PrintLogger(file=capture_output)
    for method_name in ("info", "debug", "warning", "error", "critical", "fatal"):
        getattr(logger, method_name)(method_name)
    output = capture_output.getvalue()
    for method_name in ("info", "debug", "warning", "error", "critical", "fatal"):
        assert method_name in output


# --- PrintLoggerFactory ---


def test_print_logger_factory_creates_logger():
    factory = PrintLoggerFactory()
    logger = factory()
    assert isinstance(logger, PrintLogger)


def test_print_logger_factory_passes_file():
    buf = io.StringIO()
    factory = PrintLoggerFactory(file=buf)
    logger = factory()
    logger.msg("test")
    assert buf.getvalue() == "test\n"


# --- BoundLogger ---


def test_bound_logger_runs_chain():
    """Two processors called in order."""
    order = []

    def proc1(_logger, _method, ed):
        order.append(1)
        ed["proc1"] = True
        return ed

    def proc2(_logger, _method, ed):
        order.append(2)
        return str(ed)

    mock_log = Mock()
    bl = BoundLogger(mock_log, [proc1, proc2])
    bl.info("test")
    assert order == [1, 2]
    mock_log.msg.assert_called_once()


def test_bound_logger_string_writes_directly():
    """Renderer returns str -> written via msg()."""

    def renderer(_logger, _method, ed):
        return "rendered"

    mock_log = Mock()
    bl = BoundLogger(mock_log, [renderer])
    bl.info("test")
    mock_log.msg.assert_called_once_with("rendered")


def test_bound_logger_drop_event_silences():
    """DropEvent -> nothing written."""

    def dropper(_logger, _method, ed):
        raise DropEvent

    mock_log = Mock()
    bl = BoundLogger(mock_log, [dropper])
    bl.info("test")
    mock_log.msg.assert_not_called()


def test_bound_logger_dict_fallback():
    """No renderer (processor returns dict) -> str(dict) written."""

    def passthrough(_logger, _method, ed):
        return ed

    mock_log = Mock()
    bl = BoundLogger(mock_log, [passthrough])
    bl.info("test")
    mock_log.msg.assert_called_once()
    call_arg = mock_log.msg.call_args[0][0]
    assert "test" in call_arg


def test_bound_logger_info():
    mock_log = Mock()

    def capture(_logger, _method, ed):
        ed["_captured_method"] = _method
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.info("e")
    assert "info" in mock_log.msg.call_args[0][0]


def test_bound_logger_debug():
    mock_log = Mock()
    captured = {}

    def capture(_logger, method, ed):
        captured["method"] = method
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.debug("e")
    assert captured["method"] == "debug"


def test_bound_logger_warning():
    mock_log = Mock()
    captured = {}

    def capture(_logger, method, ed):
        captured["method"] = method
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.warning("e")
    assert captured["method"] == "warning"


def test_bound_logger_error():
    mock_log = Mock()
    captured = {}

    def capture(_logger, method, ed):
        captured["method"] = method
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.error("e")
    assert captured["method"] == "error"


def test_bound_logger_critical():
    mock_log = Mock()
    captured = {}

    def capture(_logger, method, ed):
        captured["method"] = method
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.critical("e")
    assert captured["method"] == "critical"


def test_bound_logger_msg_uses_info():
    """msg() dispatches as 'info'."""
    mock_log = Mock()
    captured = {}

    def capture(_logger, method, ed):
        captured["method"] = method
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.msg("e")
    assert captured["method"] == "info"


def test_bound_logger_kwargs_in_event_dict():
    """info("e", foo=1) -> {"event":"e","foo":1}."""
    mock_log = Mock()
    captured = {}

    def capture(_logger, _method, ed):
        captured.update(ed)
        return str(ed)

    bl = BoundLogger(mock_log, [capture])
    bl.info("e", foo=1)
    assert captured["event"] == "e"
    assert captured["foo"] == 1


# --- _configure ---


def test_configure_sets_globals():
    procs = [lambda l, m, ed: ed]
    factory = PrintLoggerFactory()
    _configure(procs, factory)

    import hyper2kvm.core.structured_log as sl

    assert sl._global_processors == procs
    assert sl._global_logger_factory is factory


# --- _get_bound_logger ---


def test_get_bound_logger_uses_config():
    procs = [lambda l, m, ed: ed]
    factory = PrintLoggerFactory()
    _configure(procs, factory)

    bl = _get_bound_logger()
    assert isinstance(bl, BoundLogger)
    assert bl._processors == procs


def test_get_bound_logger_default_factory():
    """None factory -> PrintLoggerFactory."""
    _configure([], None)
    bl = _get_bound_logger()
    assert isinstance(bl, BoundLogger)
    assert isinstance(bl._logger, PrintLogger)
