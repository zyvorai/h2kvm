# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Azure-specific exceptions for VM migration operations."""
# h2kvm/azure/exceptions.py

from __future__ import annotations

from typing import Any

from ...core.exceptions import H2KvmError


class AzureError(H2KvmError):
    """
    Base exception for Azure operations.

    Inherits rich exception handling from H2KvmError:
    - Exit codes, context tracking, cause chaining
    - Secret redaction, user messages, JSON serialization
    """


class AzureCLIError(AzureError):
    """
    Azure CLI command failed.

    Used when 'az' commands fail (non-zero exit, parsing errors, etc.).
    """


class AzureAuthError(AzureError):
    """
    Azure authentication error.

    Used when Azure login/credential issues occur.
    """


class AzureDownloadError(AzureError):
    """
    Azure download operation failed.

    Used when VHD/blob downloads fail (network, resume, verification, etc.).
    """


# Convenience wrapper functions (following core/exceptions.py pattern)


def wrap_azure_cli_error(
    msg: str, exc: BaseException | None = None, code: int = 60, **context: Any
) -> AzureCLIError:
    """Wrap Azure CLI errors with context."""
    return AzureCLIError(code=code, msg=msg, cause=exc, context=context or None)


def wrap_azure_auth_error(
    msg: str, exc: BaseException | None = None, code: int = 61, **context: Any
) -> AzureAuthError:
    """Wrap Azure authentication errors with context."""
    return AzureAuthError(code=code, msg=msg, cause=exc, context=context or None)


def wrap_azure_download_error(
    msg: str, exc: BaseException | None = None, code: int = 62, **context: Any
) -> AzureDownloadError:
    """Wrap Azure download errors with context."""
    return AzureDownloadError(code=code, msg=msg, cause=exc, context=context or None)
