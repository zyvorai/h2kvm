"""Shared TYPE_CHECKING-only typing stand-in for the optional ``guestfs`` module.

Many fixer/inspector modules reference ``guestfs.GuestFS`` in type hints
without requiring the real (C-extension-backed) ``python3-guestfs`` package
to be installed. Each of those modules used to define its own identical
fallback stub inside an ``if TYPE_CHECKING:`` guard, which pylint's
duplicate-code (R0801) checker flagged as cross-file duplication. This
module provides ONE canonical stand-in so callers can import it instead.

Usage, inside a caller's own ``TYPE_CHECKING`` guard::

    if TYPE_CHECKING:
        from h2kvm.core.guestfs_typing import guestfs

This module is only ever imported for static type checking (never at
runtime), so the try/except below is evaluated by type checkers, not by
the Python interpreter.
"""

from __future__ import annotations

from typing import Protocol

try:
    import guestfs
except ImportError:

    class guestfs:  # type: ignore  # pylint: disable=invalid-name,too-few-public-methods
        """Typing-only stand-in for the ``guestfs`` module when it isn't installed."""

        class GuestFS(Protocol):  # pylint: disable=too-few-public-methods
            """Typing-only stand-in for ``guestfs.GuestFS`` when it isn't installed."""


__all__ = ["guestfs"]
