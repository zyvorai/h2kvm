# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/xml_utils.py
"""Shared XML escaping and manipulation utilities

Provides common helpers for XML escaping to avoid duplication across modules.
Uses xml.sax.saxutils for standard escaping with additional entity support.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _sax_escape


def xml_escape(s: object) -> str:
    """Escape string for XML text and attribute contexts.

    Args:
        s: Object to escape (will be converted to string)

    Returns:
        Escaped XML string with &, <, >, ', " encoded as entities

    Note:
        Safe for both XML text content and attribute values.
        Uses standard library xml.sax.saxutils.escape internally.

    Example:
        >>> xml_escape("a < b & c > d")
        'a &lt; b &amp; c &gt; d'
        >>> xml_escape('say "hello"')
        'say &quot;hello&quot;'
    """
    return _sax_escape(str(s), entities={"'": "&apos;", '"': "&quot;"})


def xml_escape_attr(s: str) -> str:
    """Escape string specifically for XML attribute values.

    Args:
        s: String to escape

    Returns:
        Escaped XML attribute string

    Note:
        Escapes &, <, >, ', " characters.
        Order matters: & must be escaped first to avoid double-escaping.

    Example:
        >>> xml_escape_attr('path="/tmp/file with spaces"')
        'path=&quot;/tmp/file with spaces&quot;'
    """
    return (
        s.replace("&", "&amp;")
        .replace("'", "&apos;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def xml_escape_text(s: str) -> str:
    """Escape string specifically for XML text content.

    Args:
        s: String to escape

    Returns:
        Escaped XML text string

    Note:
        Escapes &, <, > characters.
        Order matters: & must be escaped first to avoid double-escaping.
        Does not escape quotes since they don't need escaping in text content.

    Example:
        >>> xml_escape_text("a < b & c > d")
        'a &lt; b &amp; c &gt; d'
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = [
    "xml_escape",
    "xml_escape_attr",
    "xml_escape_text",
]
