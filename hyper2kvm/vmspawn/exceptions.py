# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Exceptions for vmspawn SDK."""


class VMSpawnError(Exception):
    """Base exception for vmspawn operations."""


class VMStartError(VMSpawnError):
    """Raised when VM fails to start."""


class VMStopError(VMSpawnError):
    """Raised when VM fails to stop."""


class VMValidationError(VMSpawnError):
    """Raised when VM validation fails."""


class VMTimeoutError(VMSpawnError):
    """Raised when VM operation times out."""


class VMNotRunningError(VMSpawnError):
    """Raised when VM is not running but expected to be."""
