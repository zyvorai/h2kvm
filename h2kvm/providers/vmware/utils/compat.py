# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/utils/compat.py

"""
Shared optional-dependency compatibility shims for the VMware provider package.

Several modules under h2kvm/providers/vmware/ independently probed the
same optional imports (the stdlib ``select`` module, ``pyVmomi.vim``) and
resolved the same ``VMwareError`` fallback chain with identical try/except
boilerplate. Centralizing those probes here avoids each module repeating an
identical stub (previously flagged by pylint's whole-project duplicate-code
check across module boundaries).

Modules that need one of these should import it directly from here, e.g.::

    from h2kvm.providers.vmware.utils.compat import VMwareError
"""

from __future__ import annotations

# Optional: select, for single-flow multiplexing of stdout/stderr without threads.
try:  # pragma: no cover
    import select  # type: ignore

    SELECT_AVAILABLE = True
except ImportError:  # pragma: no cover
    select = None  # type: ignore  # pylint: disable=invalid-name  # intentional module-name fallback, matches select.select(...) usage at call sites
    SELECT_AVAILABLE = False

# Optional: pyVmomi's vim module.
try:
    from pyVmomi import vim  # type: ignore

    PYVMOMI_AVAILABLE = True
except ImportError:  # pragma: no cover
    vim = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# VMwareError: prefer the transport module's definition, fall back to
# core.exceptions, and finally fall back to a local RuntimeError subclass.
try:
    from h2kvm.providers.vmware.transports.http_client import VMwareError
except ImportError:  # pragma: no cover
    try:
        from h2kvm.core.exceptions import VMwareError  # type: ignore
    except ImportError:  # pragma: no cover

        class VMwareError(RuntimeError):  # type: ignore
            """Fallback VMwareError used when neither http_client nor core.exceptions is importable."""


__all__ = ["PYVMOMI_AVAILABLE", "SELECT_AVAILABLE", "VMwareError", "select", "vim"]
