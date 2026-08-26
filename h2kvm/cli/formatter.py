# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/formatter.py
"""
Output formatting for CLI.

Provides rich terminal output with colors, tables, and formatting.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OutputStyle(Enum):
    """Output styles."""

    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HEADER = "header"
    NORMAL = "normal"


# ANSI color codes
COLORS = {
    OutputStyle.SUCCESS: "\033[92m",  # Green
    OutputStyle.ERROR: "\033[91m",  # Red
    OutputStyle.WARNING: "\033[93m",  # Yellow
    OutputStyle.INFO: "\033[94m",  # Blue
    OutputStyle.HEADER: "\033[1m\033[96m",  # Bold Cyan
    OutputStyle.NORMAL: "\033[0m",  # Reset
}

RESET = "\033[0m"


@dataclass
class Table:
    """
    Simple ASCII table.

    Attributes:
        headers: Column headers
        rows: Table rows
        title: Optional table title
    """

    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)
    title: str | None = None

    def add_row(self, row: list[str]) -> None:
        """Add row to table."""
        self.rows.append(row)

    def render(self) -> str:
        """
        Render table as string.

        Returns:
            Formatted table string
        """
        if not self.headers:
            return ""

        # Calculate column widths
        col_widths = [len(h) for h in self.headers]

        for row in self.rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # Build separator
        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

        lines = []

        # Title
        if self.title:
            total_width = sum(col_widths) + len(col_widths) * 3 + 1
            lines.append("=" * total_width)
            lines.append(self.title.center(total_width))
            lines.append("=" * total_width)

        # Header
        lines.append(separator)
        header_row = (
            "|" + "|".join(f" {self.headers[i]:<{col_widths[i]}} " for i in range(len(self.headers))) + "|"
        )
        lines.append(header_row)
        lines.append(separator)

        # Rows
        for row in self.rows:
            row_str = (
                "|"
                + "|".join(
                    f" {row[i] if i < len(row) else ''!s:<{col_widths[i]}} "
                    for i in range(len(self.headers))
                )
                + "|"
            )
            lines.append(row_str)

        lines.append(separator)

        return "\n".join(lines)


class OutputFormatter:
    """
    Output formatter.

    Formats terminal output with colors and styles.
    """

    def __init__(self, enable_colors: bool = True):
        """
        Initialize output formatter.

        Args:
            enable_colors: Enable colored output (default: True)
        """
        self.enable_colors = enable_colors and sys.stdout.isatty()

    def format(self, message: str, style: OutputStyle = OutputStyle.NORMAL) -> str:
        """
        Format message with style.

        Args:
            message: Message to format
            style: Output style

        Returns:
            Formatted message
        """
        if not self.enable_colors:
            return message

        color = COLORS.get(style, RESET)
        return f"{color}{message}{RESET}"

    def print(self, message: str, style: OutputStyle = OutputStyle.NORMAL) -> None:
        """
        Print formatted message.

        Args:
            message: Message to print
            style: Output style
        """
        print(self.format(message, style))

    def print_success(self, message: str) -> None:
        """Print success message."""
        self.print(f"✓ {message}", OutputStyle.SUCCESS)

    def print_error(self, message: str) -> None:
        """Print error message."""
        self.print(f"✗ {message}", OutputStyle.ERROR)

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        self.print(f"⚠ {message}", OutputStyle.WARNING)

    def print_info(self, message: str) -> None:
        """Print info message."""
        self.print(f"ℹ {message}", OutputStyle.INFO)

    def print_header(self, message: str, char: str = "=") -> None:
        """
        Print header with separator.

        Args:
            message: Header message
            char: Separator character
        """
        separator = char * len(message)
        self.print(separator, OutputStyle.HEADER)
        self.print(message, OutputStyle.HEADER)
        self.print(separator, OutputStyle.HEADER)

    def print_section(self, message: str) -> None:
        """Print section header."""
        self.print(f"\n{message}", OutputStyle.HEADER)
        self.print("-" * len(message), OutputStyle.HEADER)

    def print_table(self, table: Table) -> None:
        """
        Print table.

        Args:
            table: Table to print
        """
        print(table.render())

    def print_key_value(self, key: str, value: Any, indent: int = 0) -> None:
        """
        Print key-value pair.

        Args:
            key: Key name
            value: Value
            indent: Indentation level
        """
        indent_str = "  " * indent
        print(f"{indent_str}{key}: {value}")

    def print_list(self, items: list[str], bullet: str = "•", indent: int = 0) -> None:
        """
        Print bulleted list.

        Args:
            items: List items
            bullet: Bullet character
            indent: Indentation level
        """
        indent_str = "  " * indent
        for item in items:
            print(f"{indent_str}{bullet} {item}")
