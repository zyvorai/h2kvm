# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.core.list_utils module.

Pure logic tests for dedup_preserve_order and dedup_preserve_order_str.
"""

from __future__ import annotations

from h2kvm.core.list_utils import dedup_preserve_order, dedup_preserve_order_str


# --- dedup_preserve_order ---


def test_dedup_preserve_order_basic():
    assert dedup_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_dedup_preserve_order_empty():
    assert dedup_preserve_order([]) == []


def test_dedup_preserve_order_no_duplicates():
    assert dedup_preserve_order(["x", "y", "z"]) == ["x", "y", "z"]


def test_dedup_preserve_order_all_same():
    assert dedup_preserve_order(["a", "a", "a"]) == ["a"]


def test_dedup_preserve_order_integers():
    assert dedup_preserve_order([1, 2, 3, 2, 1]) == [1, 2, 3]


def test_dedup_preserve_order_preserves_first_occurrence():
    result = dedup_preserve_order(["c", "b", "a", "b", "c"])
    assert result == ["c", "b", "a"]


def test_dedup_preserve_order_tuples():
    items = [(1, 2), (3, 4), (1, 2), (5, 6)]
    assert dedup_preserve_order(items) == [(1, 2), (3, 4), (5, 6)]


# --- dedup_preserve_order_str ---


def test_dedup_preserve_order_str_basic():
    assert dedup_preserve_order_str(["foo", "bar", "foo", "baz"]) == [
        "foo",
        "bar",
        "baz",
    ]


def test_dedup_preserve_order_str_empty():
    assert dedup_preserve_order_str([]) == []


def test_dedup_preserve_order_str_no_duplicates():
    assert dedup_preserve_order_str(["alpha", "beta", "gamma"]) == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_dedup_preserve_order_str_all_same():
    assert dedup_preserve_order_str(["dup", "dup", "dup"]) == ["dup"]


def test_dedup_preserve_order_str_case_sensitive():
    result = dedup_preserve_order_str(["A", "a", "A", "a"])
    assert result == ["A", "a"]
