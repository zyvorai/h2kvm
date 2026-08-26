# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Shared helpers for the systemd/*.py CLI wrapper modules.

Every wrapper in this package follows the same "verify the binary is on
PATH before use" and "parse a K/M/G/T size string" patterns. Factoring
them out here avoids pylint duplicate-code (R0801) findings across the
wrapper modules while keeping each module's own command-building logic
independent.
"""

from __future__ import annotations

import subprocess

from h2kvm.core.exceptions import SystemdError


def check_systemd_binary_available(
    binary: str,
    tool_name: str,
    *,
    solutions: list[str],
) -> None:
    """
    Verify a systemd CLI tool is available on PATH.

    Parameters
    ----------
    binary : str
        Path or name of the binary to probe with ``--version``.
    tool_name : str
        Human-readable tool name used in the raised error message.
    solutions : list[str]
        Suggested remediation steps surfaced via ``SystemdError`` context.

    Raises
    ------
    SystemdError
        If the binary is missing or fails to report its version.
    """
    try:
        subprocess.run(
            [binary, "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        msg = f"{tool_name} not available: {e}"
        raise SystemdError(code=127, msg=msg).with_context(solutions=solutions) from e


def parse_binary_size(size_str: str) -> int:
    """
    Parse a size string like ``"1.5G"`` into a byte count.

    Supports ``K``/``M``/``G``/``T`` suffixes (powers of 1024); a string
    with no suffix is treated as a raw byte count. Raises ``ValueError``
    on malformed input -- callers that want lenient parsing should catch
    it themselves.
    """
    size_str = size_str.upper()
    multipliers = {
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
    }

    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            value = float(size_str[:-1])
            return int(value * multiplier)

    # No suffix, assume bytes
    return int(size_str)
