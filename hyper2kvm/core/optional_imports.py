# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/optional_imports.py
"""
Centralized optional imports to eliminate duplicate import guards.

This module provides a single location for optional dependencies, eliminating
the need for try/except import blocks scattered across 20+ files.
"""

from __future__ import annotations

# requests library (HTTP client)
try:
    import requests
    import requests.adapters  # pylint: disable=unused-import  # ensures requests.adapters submodule is loaded for re-export

    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

# httpx library (Async HTTP client)
try:
    import httpx
    from httpx import AsyncClient, Limits, Timeout

    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore
    AsyncClient = None  # type: ignore
    Limits = None  # type: ignore
    Timeout = None  # type: ignore
    HTTPX_AVAILABLE = False

# urllib3 library (HTTP utilities, TLS warnings)
try:
    import urllib3

    URLLIB3_AVAILABLE = True
except ImportError:
    urllib3 = None  # type: ignore
    URLLIB3_AVAILABLE = False

# pyVmomi library (VMware vSphere API)
try:
    from pyVmomi import vim, vmodl

    PYVMOMI_AVAILABLE = True
except ImportError:
    vim = None  # type: ignore
    vmodl = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# paramiko library (SSH client)
try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:
    paramiko = None  # type: ignore
    PARAMIKO_AVAILABLE = False

# Pydantic (configuration validation)
try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    PYDANTIC_AVAILABLE = True
except ImportError:
    BaseModel = None  # type: ignore
    Field = None  # type: ignore
    field_validator = None  # type: ignore
    ConfigDict = None  # type: ignore
    ValidationError = None  # type: ignore
    BaseSettings = None  # type: ignore
    SettingsConfigDict = None  # type: ignore
    PYDANTIC_AVAILABLE = False

# Tenacity (advanced retry logic)
try:
    from tenacity import (
        RetryError,
        after_log,
        before_sleep_log,
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
        wait_fixed,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    retry = None  # type: ignore
    stop_after_attempt = None  # type: ignore
    wait_exponential = None  # type: ignore
    wait_fixed = None  # type: ignore
    retry_if_exception_type = None  # type: ignore
    before_sleep_log = None  # type: ignore
    after_log = None  # type: ignore
    RetryError = None  # type: ignore
    TENACITY_AVAILABLE = False

# Watchdog (file system monitoring for daemon mode)
try:
    from watchdog.events import FileCreatedEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    Observer = None  # type: ignore
    FileSystemEventHandler = None  # type: ignore
    FileCreatedEvent = None  # type: ignore
    WATCHDOG_AVAILABLE = False

# Textual (Terminal User Interface framework)
# NOTE: Textual is no longer used by hyper2kvm. The TUI is now a standalone
# Go binary (zkvm) using Bubble Tea. This flag is kept for backward
# compatibility with any code that checks TEXTUAL_AVAILABLE.
TEXTUAL_AVAILABLE = False

# Helper functions


def require_requests() -> None:
    """Raise ImportError if requests is not available."""
    if not REQUESTS_AVAILABLE:
        raise ImportError(
            "requests library is required but not installed. Install with: pip install requests"
        )


def require_httpx() -> None:
    """Raise ImportError if httpx is not available."""
    if not HTTPX_AVAILABLE:
        raise ImportError(
            "httpx library is required but not installed. Install with: pip install httpx>=0.24.0"
        )


def require_pyvmomi() -> None:
    """Raise ImportError if pyVmomi is not available."""
    if not PYVMOMI_AVAILABLE:
        raise ImportError("pyVmomi library is required but not installed. Install with: pip install pyvmomi")


def require_paramiko() -> None:
    """Raise ImportError if paramiko is not available."""
    if not PARAMIKO_AVAILABLE:
        raise ImportError(
            "paramiko library is required but not installed. Install with: pip install paramiko"
        )


def require_pydantic() -> None:
    """Raise ImportError if pydantic is not available."""
    if not PYDANTIC_AVAILABLE:
        raise ImportError(
            "pydantic library is required but not installed. "
            "Install with: pip install pydantic>=2.5.0 pydantic-settings>=2.1.0"
        )


def require_tenacity() -> None:
    """Raise ImportError if tenacity is not available."""
    if not TENACITY_AVAILABLE:
        raise ImportError(
            "tenacity library is required but not installed. Install with: pip install tenacity>=8.2.0"
        )


def require_watchdog() -> None:
    """Raise ImportError if watchdog is not available."""
    if not WATCHDOG_AVAILABLE:
        raise ImportError(
            "watchdog library is required but not installed. Install with: pip install watchdog>=3.0.0"
        )


def require_textual() -> None:
    """Raise ImportError — Textual is no longer used.

    The TUI is now a standalone Go binary (zkvm). This function is kept
    for backward compatibility.
    """
    raise ImportError(
        "Textual is no longer used. The TUI is now a Go binary (zkvm). Launch with: h2kvmctl --zkvm"
    )


# This module is a centralized barrel for optional third-party dependencies;
# callers import the re-exported names directly (e.g. `from
# hyper2kvm.core.optional_imports import BaseModel`), so pylint's
# unused-import check needs these listed explicitly.
__all__ = [
    "HTTPX_AVAILABLE",
    "PARAMIKO_AVAILABLE",
    "PYDANTIC_AVAILABLE",
    "PYVMOMI_AVAILABLE",
    "REQUESTS_AVAILABLE",
    "TENACITY_AVAILABLE",
    "TEXTUAL_AVAILABLE",
    "URLLIB3_AVAILABLE",
    "WATCHDOG_AVAILABLE",
    "AsyncClient",
    "BaseModel",
    "BaseSettings",
    "ConfigDict",
    "Field",
    "FileCreatedEvent",
    "FileSystemEventHandler",
    "Limits",
    "Observer",
    "RetryError",
    "SettingsConfigDict",
    "Timeout",
    "ValidationError",
    "after_log",
    "before_sleep_log",
    "field_validator",
    "httpx",
    "paramiko",
    "requests",
    "require_httpx",
    "require_paramiko",
    "require_pydantic",
    "require_pyvmomi",
    "require_requests",
    "require_tenacity",
    "require_textual",
    "require_watchdog",
    "retry",
    "retry_if_exception_type",
    "stop_after_attempt",
    "urllib3",
    "vim",
    "vmodl",
    "wait_exponential",
    "wait_fixed",
]
