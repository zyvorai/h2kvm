# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for SafeJSONEncoder and _safe_json_serializer."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import uuid
from pathlib import Path

from h2kvm.core.structured_log import SafeJSONEncoder, _safe_json_serializer


class _Unserializable:
    """Object whose __str__ raises."""

    def __str__(self):
        raise RuntimeError("boom")

    def __repr__(self):
        raise RuntimeError("boom")


# --- SafeJSONEncoder.default ---


def test_encode_datetime():
    now = dt.datetime(2024, 1, 15, 12, 30, 45)
    result = json.loads(json.dumps({"v": now}, cls=SafeJSONEncoder))
    assert result["v"] == now.isoformat()


def test_encode_date():
    d = dt.date(2024, 6, 1)
    result = json.loads(json.dumps({"v": d}, cls=SafeJSONEncoder))
    assert result["v"] == d.isoformat()


def test_encode_time():
    t = dt.time(14, 30, 0)
    result = json.loads(json.dumps({"v": t}, cls=SafeJSONEncoder))
    assert result["v"] == t.isoformat()


def test_encode_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    result = json.loads(json.dumps({"v": u}, cls=SafeJSONEncoder))
    assert result["v"] == str(u)


def test_encode_path():
    p = Path("/tmp/foo/bar")
    result = json.loads(json.dumps({"v": p}, cls=SafeJSONEncoder))
    assert result["v"] == str(p)


def test_encode_bytes_utf8():
    b = b"hello world"
    result = json.loads(json.dumps({"v": b}, cls=SafeJSONEncoder))
    assert result["v"] == "hello world"


def test_encode_bytes_non_utf8():
    b = b"\xff\xfe"
    result = json.loads(json.dumps({"v": b}, cls=SafeJSONEncoder))
    # Should contain replacement characters, not raise
    assert isinstance(result["v"], str)


def test_encode_set():
    s = {1, 2, 3}
    result = json.loads(json.dumps({"v": s}, cls=SafeJSONEncoder))
    assert sorted(result["v"]) == [1, 2, 3]


def test_encode_frozenset():
    fs = frozenset([4, 5])
    result = json.loads(json.dumps({"v": fs}, cls=SafeJSONEncoder))
    assert sorted(result["v"]) == [4, 5]


def test_encode_dataclass():
    @dataclasses.dataclass
    class Point:
        x: int
        y: int

    p = Point(1, 2)
    result = json.loads(json.dumps({"v": p}, cls=SafeJSONEncoder))
    assert result["v"] == {"x": 1, "y": 2}


def test_encode_exception():
    e = ValueError("oops")
    result = json.loads(json.dumps({"v": e}, cls=SafeJSONEncoder))
    assert result["v"] == "ValueError: oops"


def test_encode_custom_object_str_fallback():
    class MyObj:
        def __str__(self):
            return "custom-repr"

    obj = MyObj()
    result = json.loads(json.dumps({"v": obj}, cls=SafeJSONEncoder))
    assert result["v"] == "custom-repr"


def test_encode_unserializable_object():
    obj = _Unserializable()
    result = json.loads(json.dumps({"v": obj}, cls=SafeJSONEncoder))
    assert result["v"] == "<unserializable _Unserializable>"


# --- _safe_json_serializer ---


def test_serializer_returns_string():
    result = _safe_json_serializer({"a": 1})
    assert isinstance(result, str)
    assert json.loads(result) == {"a": 1}


def test_serializer_exotic_values_end_to_end():
    data = {
        "dt": dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
        "uid": uuid.UUID("abcdef12-3456-7890-abcd-ef1234567890"),
        "path": Path("/opt/data"),
        "tags": {10, 20},
    }
    result = _safe_json_serializer(data)
    parsed = json.loads(result)
    assert parsed["dt"] == "2024-01-01T00:00:00+00:00"
    assert parsed["uid"] == "abcdef12-3456-7890-abcd-ef1234567890"
    assert parsed["path"] == "/opt/data"
    assert sorted(parsed["tags"]) == [10, 20]


def test_serializer_forwards_kwargs():
    result = _safe_json_serializer({"b": 1, "a": 2}, indent=2, sort_keys=True)
    lines = result.strip().split("\n")
    # With indent=2, output should be multi-line
    assert len(lines) > 1
    parsed = json.loads(result)
    assert parsed == {"a": 2, "b": 1}


def test_serializer_nested_types():
    data = {"exc": TypeError("bad"), "bs": b"raw"}
    result = _safe_json_serializer(data)
    parsed = json.loads(result)
    assert parsed["exc"] == "TypeError: bad"
    assert parsed["bs"] == "raw"
