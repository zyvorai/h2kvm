# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.core.xml_utils module.

Pure logic tests for xml_escape, xml_escape_attr, and xml_escape_text.
"""

from __future__ import annotations

from h2kvm.core.xml_utils import xml_escape, xml_escape_attr, xml_escape_text


# --- xml_escape ---


def test_xml_escape_ampersand():
    assert xml_escape("a & b") == "a &amp; b"


def test_xml_escape_less_than():
    assert xml_escape("a < b") == "a &lt; b"


def test_xml_escape_greater_than():
    assert xml_escape("a > b") == "a &gt; b"


def test_xml_escape_single_quote():
    assert xml_escape("it's") == "it&apos;s"


def test_xml_escape_double_quote():
    assert xml_escape('say "hi"') == "say &quot;hi&quot;"


def test_xml_escape_combined():
    assert xml_escape("<a & 'b' \"c\">") == "&lt;a &amp; &apos;b&apos; &quot;c&quot;&gt;"


def test_xml_escape_no_special_chars():
    assert xml_escape("hello world") == "hello world"


def test_xml_escape_non_string_input():
    assert xml_escape(42) == "42"


# --- xml_escape_attr ---


def test_xml_escape_attr_ampersand():
    assert xml_escape_attr("a & b") == "a &amp; b"


def test_xml_escape_attr_quotes_escaped():
    assert xml_escape_attr("it's") == "it&apos;s"
    assert xml_escape_attr('say "hi"') == "say &quot;hi&quot;"


def test_xml_escape_attr_combined():
    result = xml_escape_attr('<a & "b">')
    assert result == "&lt;a &amp; &quot;b&quot;&gt;"


def test_xml_escape_attr_no_special_chars():
    assert xml_escape_attr("plain text") == "plain text"


def test_xml_escape_attr_no_double_escape():
    assert xml_escape_attr("&amp;") == "&amp;amp;"


def test_xml_escape_attr_empty_string():
    assert xml_escape_attr("") == ""


# --- xml_escape_text ---


def test_xml_escape_text_ampersand():
    assert xml_escape_text("a & b") == "a &amp; b"


def test_xml_escape_text_less_than():
    assert xml_escape_text("a < b") == "a &lt; b"


def test_xml_escape_text_greater_than():
    assert xml_escape_text("a > b") == "a &gt; b"


def test_xml_escape_text_no_quote_escaping():
    assert xml_escape_text('say "hello"') == 'say "hello"'
    assert xml_escape_text("it's fine") == "it's fine"


def test_xml_escape_text_combined():
    assert xml_escape_text("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_xml_escape_text_empty_string():
    assert xml_escape_text("") == ""
