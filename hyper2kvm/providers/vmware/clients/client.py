# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/clients/client.py
# pylint: disable=too-many-lines  # cohesive vSphere/vCenter client covering connect/inventory/export/download/vddk/ovftool
"""
vSphere / vCenter client for hyper2kvm.
"""

from __future__ import annotations

import atexit
import os
import random
import re
import shlex
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

# Optional: non-blocking pump
# (shared availability probe, centralized in utils/compat.py to avoid
# duplicating this try/except stub across vmware provider modules)
from hyper2kvm.providers.vmware.utils.compat import SELECT_AVAILABLE, select

# govc helpers (single source of truth)
try:
    from hyper2kvm.providers.vmware.transports.govc_common import GovcRunner
except ImportError:  # pragma: no cover
    GovcRunner = None  # type: ignore

# OVF Tool client
try:
    from hyper2kvm.providers.vmware.transports.ovftool_client import (
        OvfToolPaths,
        find_ovftool,
        ovftool_version,
    )
except ImportError:  # pragma: no cover
    find_ovftool = None  # type: ignore
    ovftool_version = None  # type: ignore
    OvfToolPaths = None  # type: ignore

# HTTP/HTTPS download client
try:
    from hyper2kvm.providers.vmware.transports.http_client import HTTPDownloadClient, VMwareError
except ImportError:  # pragma: no cover
    HTTPDownloadClient = None  # type: ignore
    try:
        from ....core.exceptions import VMwareError  # type: ignore
    except ImportError:  # pragma: no cover

        class VMwareError(RuntimeError):
            """Fallback VMware error type when neither http_client nor core.exceptions is importable."""


# ✅ shared credential resolver (supports vs_password_env + vc_password_env)
try:
    from ....core.cred import resolve_vsphere_creds  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from ....core.creds import resolve_vsphere_creds  # type: ignore
    except ImportError:  # pragma: no cover
        resolve_vsphere_creds = None  # type: ignore

# Optional: vSphere / vCenter integration (pyvmomi)
try:
    from pyVim.connect import Disconnect, SmartConnect  # type: ignore

    PYVMOMI_AVAILABLE = True
except ImportError:  # pragma: no cover
    SmartConnect = None  # type: ignore
    Disconnect = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# Optional: requests library for HTTP operations (availability probe only; not referenced directly here)
try:  # pragma: no cover
    import requests  # type: ignore  # noqa: F401  # pylint: disable=unused-import

    REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover
    REQUESTS_AVAILABLE = False

# Optional: silence urllib3 TLS warnings when verify=False (availability probe only)
try:  # pragma: no cover
    import urllib3  # type: ignore  # noqa: F401  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    pass

# VDDK client (availability probe only; heavy logic lives in vddk_loader.py / vddk_client.py)
try:
    # pylint: disable=unused-import,ungrouped-imports  # this optional-dependency probe is intentionally interleaved
    # with the other try/except ImportError blocks above/below, in the order they're actually needed
    from hyper2kvm.providers.vmware.transports.vddk_client import (  # type: ignore  # noqa: F401
        VDDKConnectionSpec,
        VDDKESXClient,
    )

    VDDK_CLIENT_AVAILABLE = True
except ImportError:  # pragma: no cover
    VDDK_CLIENT_AVAILABLE = False


from hyper2kvm.core.retry_decorator import api_retry
from hyper2kvm.core.structured_log import log_event
from hyper2kvm.providers.vmware.utils.utils import safe_vm_name as _safe_vm_name

_BACKING_RE = re.compile(r"\[(.+?)\]\s+(.*)")


class GovmomiCLI(GovcRunner):
    """
    Thin alias wrapper for older naming; actual logic lives in GovcRunner (govc_common.py).
    """

    def __init__(self, logger: Any, **kwargs: Any):
        super().__init__(logger=logger, args=type("Args", (), kwargs))


@dataclass
class ExportOptions:  # pylint: disable=too-many-instance-attributes  # models every independent export/download/transport tuning knob
    """
    Export and download options for vSphere VMs.
    """

    vm_name: str
    export_mode: str = "ovf_export"  # stable default

    # vCenter placement resolution (for export)
    datacenter: str = "auto"
    compute: str = "auto"

    # export options
    transport: str = "vddk"  # export transport: vddk|ssh
    no_verify: bool = False
    vddk_libdir: Path | None = None  # passed to export -io vddk-libdir
    vddk_thumbprint: str | None = None  # passed to export vddk-thumbprint (if provided)
    vddk_snapshot_moref: str | None = None
    vddk_transports: str | None = None
    output_dir: Path = Path("./out")
    output_format: str = "qcow2"  # qcow2|raw
    extra_args: tuple[str, ...] = ()

    # OVF Tool options
    ovftool_path: str | None = None
    ovftool_no_ssl_verify: bool = True
    ovftool_thumbprint: str | None = None
    ovftool_accept_all_eulas: bool = True
    ovftool_quiet: bool = False
    ovftool_verbose: bool = False
    ovftool_overwrite: bool = False
    ovftool_disk_mode: str | None = None
    ovftool_retries: int = 0
    ovftool_retry_backoff_s: float = 2.0
    ovftool_extra_args: tuple[str, ...] = ()

    # Inventory printing (opt-in)
    print_vm_names: tuple[str, ...] = ()
    vm_list_limit: int = 120
    vm_list_columns: int = 3

    # download-only options
    download_only_include_globs: tuple[str, ...] = ("*",)
    download_only_exclude_globs: tuple[str, ...] = (
        "*.lck",
        "*.log",
        "*.scoreboard",
        "*.vswp",
        "*.vmem",
        "*.vmsn",
        "*.nvram~",
        "*.tmp",
    )
    download_only_max_files: int = 5000
    download_only_fail_on_missing: bool = False

    # govc export options
    govc_export_snapshot: str | None = None
    govc_export_power_off: bool = False
    govc_export_disk_mode: str | None = None  # "thin"|"thick" etc.

    # vddk_download options (experimental)
    vddk_download_disk: str | None = None
    vddk_download_output: Path | None = None
    vddk_download_sectors_per_read: int = 2048  # 1 MiB (2048 * 512)
    vddk_download_log_every_bytes: int = 256 * 1024 * 1024


# Import all functions from split modules
#
# These must come *after* the ExportOptions/GovmomiCLI definitions above: vddk_loader.py
# does `from hyper2kvm.providers.vmware.clients.client import ExportOptions, _safe_vm_name`,
# so this module has a circular import with vddk_loader.py and must define ExportOptions
# before importing it back.

# Import datastore operations
# Import ovftool operations
from hyper2kvm.providers.vmware.transports.ovftool_loader import (  # pylint: disable=wrong-import-position
    _build_ovftool_source_url as _ovftool_build_ovftool_source_url,
    _ovftool_deploy_options as _ovftool_ovftool_deploy_options,
    _ovftool_export_options as _ovftool_ovftool_export_options,
    _vm_inventory_path_under_vmfolder as _ovftool_vm_inventory_path_under_vmfolder,
    govc_export_ova as _ovftool_govc_export_ova,
    govc_export_ovf as _ovftool_govc_export_ovf,
    ovftool_deploy_ova as _ovftool_ovftool_deploy_ova,
    ovftool_export_vm as _ovftool_ovftool_export_vm,
)

# Import vddk operations (circular import: vddk_loader imports ExportOptions back from this module)
from hyper2kvm.providers.vmware.transports.vddk_loader import (  # pylint: disable=wrong-import-position,cyclic-import
    select_disk as _vddk_select_disk,
    vddk_download_disk as _vddk_download_disk,
    vm_disks as _vddk_vm_disks,
)
from hyper2kvm.providers.vmware.utils.datastore import (  # pylint: disable=wrong-import-position
    _download_only_vm_force_https as _datastore_download_only_vm_force_https,
    _download_selected_files as _datastore_download_selected_files,
    _filter_download_only_files as _datastore_filter_download_only_files,
    _get_vm_datastore_browser as _datastore_get_vm_datastore_browser,
    _glob_any as _datastore_glob_any,
    _host_parent_compute_name as _datastore_host_parent_compute_name,
    _list_vm_directory_files as _datastore_list_vm_directory_files,
    _refresh_datacenter_cache as _datastore_refresh_datacenter_cache,
    _refresh_host_cache as _datastore_refresh_host_cache,
    _resolve_datacenter_for_download as _datastore_resolve_datacenter_for_download,
    _split_ds_path as _datastore_split_ds_path,
    _vm_runtime_host as _datastore_vm_runtime_host,
    _vmx_pathname as _datastore_vmx_pathname,
    datacenter_exists as _datastore_datacenter_exists,
    download_datastore_file as _datastore_download_datastore_file,
    download_only_vm as _datastore_download_only_vm,
    get_datacenter_by_name as _datastore_get_datacenter_by_name,
    get_vm_by_name as _datastore_get_vm_by_name,
    list_datacenters as _datastore_list_datacenters,
    list_host_names as _datastore_list_host_names,
    parse_backing_filename as _datastore_parse_backing_filename,
    resolve_compute_for_vm as _datastore_resolve_compute_for_vm,
    resolve_datacenter_for_vm as _datastore_resolve_datacenter_for_vm,
    resolve_host_system_for_vm as _datastore_resolve_host_system_for_vm,
    vm_datacenter_name as _datastore_vm_datacenter_name,
    vm_to_datacenter as _datastore_vm_to_datacenter,
    wait_for_task as _datastore_wait_for_task,
)

if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence

# Import export operations
# NOTE: export functionality removed - hyper2kvm uses pure architecture now
# from ..utils.export import (
#     export_export_vm as _export_export_vm,
# )


@dataclass(frozen=True)
class VMwareConnectionOptions:  # pylint: disable=too-many-instance-attributes  # models every independent connection/retry tuning knob
    """
    Options for VMware vSphere/vCenter connection establishment with retry logic.

    Attributes:
        max_retries: Maximum number of connection attempts (default: 3)
        base_backoff_s: Base backoff time in seconds for exponential backoff (default: 2.0)
        max_backoff_s: Maximum backoff time in seconds (default: 30.0)
        timeout_s: Connection timeout in seconds (default: 30.0)
        enable_jitter: Add random jitter to backoff to prevent thundering herd (default: True)
    """

    max_retries: int = 3
    base_backoff_s: float = 2.0
    max_backoff_s: float = 30.0
    timeout_s: float = 30.0
    enable_jitter: bool = True


# Client


class VMwareClient:  # pylint: disable=too-many-instance-attributes,too-many-public-methods  # single client covering connect/inventory/export/download/vddk/ovftool surfaces
    """
    vSphere/vCenter client for VM operations and export.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        logger: logging.Logger,
        host: str,
        user: str,
        password: str,
        *,
        port: int = 443,
        insecure: bool = False,
        timeout: float | None = None,
        connection_options: VMwareConnectionOptions | None = None,
    ) -> None:
        self.logger = logger
        self.host = (host or "").strip()
        self.user = (user or "").strip()
        self.password = (password or "").strip()
        self.port = int(port)
        self.insecure = bool(insecure)
        self.timeout = timeout
        self.connection_options = connection_options or VMwareConnectionOptions()

        self.si: Any = None

        # HTTP download client
        self._http_client: HTTPDownloadClient | None = None

        # caches
        self._dc_cache: list[Any] | None = None
        self._dc_name_cache: list[str] | None = None
        self._host_name_cache: list[str] | None = None
        self._vm_obj_by_name_cache: dict[str, Any] = {}
        self._vm_name_cache: list[str] | None = None

        # govc knobs
        self.govc_bin = os.environ.get("GOVC_BIN", "govc")
        self.no_govmomi = False
        self._govc_client: GovmomiCLI | None = None

        # OVF Tool knobs
        self.ovftool_path: str | None = None
        self._ovftool_paths: OvfToolPaths | None = None

    # build from config using shared resolver (vs_* + vc_* + *_env)

    @classmethod
    def from_config(
        cls,
        logger: logging.Logger,
        cfg: dict[str, Any],
        *,
        port: int | None = None,
        insecure: bool | None = None,
        timeout: float | None = None,
    ) -> VMwareClient:
        """Build a client from a pipeline config dict via the shared vSphere credential resolver."""
        if resolve_vsphere_creds is None:
            raise VMwareError(
                "resolve_vsphere_creds not importable. Fix import: from ..core.cred(s) import resolve_vsphere_creds"
            )
        creds = resolve_vsphere_creds(cfg)
        p = int(port if port is not None else (cfg.get("vc_port") or cfg.get("vs_port") or 443))
        ins = bool(
            insecure
            if insecure is not None
            else (
                cfg.get("vc_insecure")
                if cfg.get("vc_insecure") is not None
                else cfg.get("vs_insecure", False)
            )
        )

        # Parse connection retry options from config
        connection_options = VMwareConnectionOptions(
            max_retries=int(cfg.get("vc_connection_max_retries", 3)),
            base_backoff_s=float(cfg.get("vc_connection_base_backoff_s", 2.0)),
            max_backoff_s=float(cfg.get("vc_connection_max_backoff_s", 30.0)),
            timeout_s=float(cfg.get("vc_connection_timeout_s", 30.0)),
            enable_jitter=bool(cfg.get("vc_connection_enable_jitter", True)),
        )

        c = cls(
            logger,
            creds.host,
            creds.user,
            creds.password,
            port=p,
            insecure=ins,
            timeout=timeout,
            connection_options=connection_options,
        )
        c.govc_bin = str(cfg.get("govc_bin") or os.environ.get("GOVC_BIN") or "govc")
        c.no_govmomi = bool(cfg.get("no_govmomi", False))
        c.ovftool_path = str(cfg.get("ovftool_path", "")) or None
        return c

    def has_creds(self) -> bool:
        """Return True if host, user, and password are all set."""
        return bool(self.host and self.user and self.password)

    # Internal helpers: tool handles

    def _govc(self) -> GovmomiCLI | None:
        """
        Return govc wrapper if available and not disabled.
        """
        if self.no_govmomi or GovcRunner is None:
            return None
        if self._govc_client is None:
            self._govc_client = GovmomiCLI(
                self.logger,
                vcenter=self.host,
                vc_user=self.user,
                vc_password=self.password,
                vc_insecure=self.insecure,
                govc_bin=self.govc_bin,
                dc_name=None,
                no_govmomi=self.no_govmomi,
            )
        return self._govc_client if self._govc_client.available() else None

    def _http_download_client(self) -> HTTPDownloadClient:
        """
        Return HTTP download client.
        """
        if self._http_client is None:
            if HTTPDownloadClient is None:
                raise VMwareError(
                    "HTTP download client not available. Ensure http_download_client.py is importable."
                )
            self._http_client = HTTPDownloadClient(
                logger=self.logger,
                host=self.host,
                port=self.port,
                insecure=self.insecure,
                timeout=self.timeout,
            )
        return self._http_client

    def _ovftool(self) -> OvfToolPaths:
        """
        Return OVF Tool paths if available.
        """
        if self._ovftool_paths is None:
            if find_ovftool is None:
                raise VMwareError("OVF Tool client not available. Ensure ovftool_client.py is importable.")
            try:
                self._ovftool_paths = find_ovftool(self.ovftool_path)
                version = ovftool_version(self._ovftool_paths) if ovftool_version is not None else None
                self.logger.info(
                    "OVF Tool found: %s (version: %s)",
                    getattr(self._ovftool_paths, "ovftool_bin", "ovftool"),
                    version or "unknown",
                )
            except Exception as e:
                raise VMwareError(f"OVF Tool not found: {e}") from e
        return self._ovftool_paths

    # Context managers

    def __enter__(self) -> VMwareClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            self.disconnect()
        finally:
            if exc_type is not None:
                self.logger.error(
                    "Exception in context: %s: %s", getattr(exc_type, "__name__", exc_type), exc_val
                )
        return False

    # Connection

    def _require_pyvmomi(self) -> None:
        if not PYVMOMI_AVAILABLE:
            raise VMwareError("pyvmomi not installed. Install: pip install pyvmomi")

    def _ssl_context(self) -> ssl.SSLContext:
        """
        Create SSL context for vSphere connections.

        SECURITY WARNING: When insecure=True, TLS certificate verification is completely
        disabled, making connections vulnerable to Man-in-the-Middle attacks. Only use
        insecure mode in trusted network environments with self-signed certificates.
        """
        if self.insecure:
            self.logger.warning(
                "TLS certificate verification is DISABLED (insecure=True). "
                "Connections are vulnerable to Man-in-the-Middle attacks. "
                "Only use this in trusted environments with self-signed certificates."
            )
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False  # SECURITY: Disabled for self-signed cert support
            ctx.verify_mode = ssl.CERT_NONE  # SECURITY: Disabled for self-signed cert support
            return ctx
        return ssl.create_default_context()

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient and worth retrying.

        Args:
            error: Exception to classify

        Returns:
            True if the error is transient and should be retried, False otherwise
        """
        error_str = str(error).lower()

        # Transient error patterns in error messages
        transient_patterns = [
            "connection timed out",
            "connection refused",
            "network is unreachable",
            "no route to host",
            "temporary failure in name resolution",
            "connection reset by peer",
            "broken pipe",
            "ssl handshake failed",
            "could not resolve hostname",
            "timeout waiting for",
            "timed out",
            "name resolution failed",
            "connection closed",
            "connection aborted",
            "network error",
            "socket error",
            "certificate verify failed",
            "ssl error",
            "connection error",
        ]

        # Check exception types that are typically transient
        if isinstance(
            error,
            (
                socket.timeout,
                ConnectionRefusedError,
                ConnectionResetError,
                ConnectionAbortedError,
                TimeoutError,
                OSError,
            ),
        ):
            return True

        # Check error message patterns
        return any(pattern in error_str for pattern in transient_patterns)

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff time with exponential backoff and optional jitter.

        Implements exponential backoff: base_backoff * (2 ** (attempt - 1))
        with optional jitter to prevent thundering herd problem.

        Args:
            attempt: Current retry attempt number (1-indexed)

        Returns:
            Backoff time in seconds
        """
        # Calculate exponential backoff: 2s, 4s, 8s, 16s, 30s (capped at max_backoff_s)
        backoff = min(
            self.connection_options.base_backoff_s * (2 ** (attempt - 1)),
            self.connection_options.max_backoff_s,
        )

        # Add jitter: ±25% randomness to prevent thundering herd
        if self.connection_options.enable_jitter:
            jitter = backoff * 0.25 * (2 * random.random() - 1)
            backoff += jitter

        return max(0.0, backoff)

    @api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
    def connect(self) -> None:  # pylint: disable=too-many-branches  # handles several distinct TLS/connection-option and retry combinations
        """
        Connect to vSphere/vCenter with retry logic.

        Implements exponential backoff retry for transient errors.
        Configuration via connection_options parameter in __init__.

        Raises:
            VMwareError: On connection failure after all retries exhausted
        """
        self._require_pyvmomi()
        ctx = self._ssl_context()

        last_error: Exception | None = None
        max_attempts = self.connection_options.max_retries + 1  # +1 for initial attempt

        for attempt in range(1, max_attempts + 1):
            try:
                # Set timeout if specified
                old_timeout = None
                if self.timeout is not None:
                    old_timeout = socket.getdefaulttimeout()
                    socket.setdefaulttimeout(self.timeout)

                try:
                    # Attempt connection
                    self.si = SmartConnect(  # type: ignore[misc]
                        host=self.host,
                        user=self.user,
                        pwd=self.password,
                        port=self.port,
                        sslContext=ctx,
                    )
                finally:
                    # Restore original timeout
                    if old_timeout is not None:
                        socket.setdefaulttimeout(old_timeout)

                # Connection successful! Set session cookie for HTTP download client
                try:
                    stub = getattr(self.si, "_stub", None)
                    cookie = getattr(stub, "cookie", None)
                    if cookie:
                        self._http_download_client().set_session_cookie(str(cookie))
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cookie propagation must not abort a successful connect
                    self.logger.debug("Failed to set HTTP session cookie: %s", e)

                # Warm caches (best-effort)
                try:
                    _datastore_refresh_datacenter_cache(self)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cache warmup must not abort a successful connect
                    self.logger.debug("Datacenter cache warmup failed (non-fatal): %s", e)
                try:
                    _datastore_refresh_host_cache(self)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cache warmup must not abort a successful connect
                    self.logger.debug("Host cache warmup failed (non-fatal): %s", e)

                # Log success
                if attempt > 1:
                    self.logger.info(
                        "Connected to vSphere: %s:%s (succeeded on attempt %d/%d)",
                        self.host,
                        self.port,
                        attempt,
                        max_attempts,
                    )
                else:
                    self.logger.info("Connected to vSphere: %s:%s", self.host, self.port)
                log_event("vsphere_connected", host=self.host, port=self.port, attempt=attempt)
                return

            # pylint: disable-next=broad-exception-caught  # pyvmomi/ssl/socket raise dynamic error types; the retry loop must classify and continue
            except Exception as e:
                last_error = e
                self.si = None

                # Check if error is transient and worth retrying
                is_transient = self._is_transient_error(e)

                # Don't retry if it's the last attempt or error is not transient
                if attempt >= max_attempts:
                    if is_transient:
                        self.logger.exception(
                            "Failed to connect to vSphere after %d attempts: %s", max_attempts, e
                        )
                    break

                if not is_transient:
                    self.logger.exception(
                        "Non-transient error connecting to vSphere (attempt %d/%d): %s. Not retrying.",
                        attempt,
                        max_attempts,
                        e,
                    )
                    break

                # Calculate backoff and log retry attempt
                backoff = self._calculate_backoff(attempt)
                self.logger.warning(
                    "Connection attempt %d/%d failed with transient error: %s. Retrying in %.1f seconds...",
                    attempt,
                    max_attempts,
                    e,
                    backoff,
                )
                time.sleep(backoff)

        # All retries exhausted - raise final error
        raise VMwareError(
            f"Failed to connect to vSphere ({self.host}:{self.port}) "
            f"after {max_attempts} attempts: {last_error}"
        ) from last_error

    def disconnect(self) -> None:
        """Disconnect from vSphere/vCenter and clear cached session state."""
        try:
            if self.si is not None:
                Disconnect(self.si)  # type: ignore[misc]
        except Exception as e:  # pylint: disable=broad-exception-caught  # pyvmomi raises dynamic/untyped errors; cleanup must still clear local state below
            self.logger.exception("Error during disconnect: %s", e)
        finally:
            self.si = None
            self._dc_cache = None
            self._dc_name_cache = None
            self._host_name_cache = None
            self._vm_name_cache = None
            self._vm_obj_by_name_cache = {}

    def _content(self) -> Any:
        if not self.si:
            raise VMwareError("Not connected")
        try:
            return self.si.RetrieveContent()
        except Exception as e:
            raise VMwareError(f"Failed to retrieve content: {e}") from e

    # Datacenters / Hosts - Delegate to vmware_datastore

    def _refresh_datacenter_cache(self) -> None:
        """Refresh the cached list of datacenters."""
        return _datastore_refresh_datacenter_cache(self)

    def list_datacenters(self, *, refresh: bool = False) -> list[str]:
        """List datacenter names, using the cache unless refresh=True."""
        return _datastore_list_datacenters(self, refresh=refresh)

    def get_datacenter_by_name(self, name: str, *, refresh: bool = False) -> Any:
        """Look up a datacenter object by name."""
        return _datastore_get_datacenter_by_name(self, name, refresh=refresh)

    def datacenter_exists(self, name: str, *, refresh: bool = False) -> bool:
        """Return True if a datacenter with this name exists."""
        return _datastore_datacenter_exists(self, name, refresh=refresh)

    def _refresh_host_cache(self) -> None:
        """Refresh the cached list of ESXi hosts."""
        return _datastore_refresh_host_cache(self)

    def list_host_names(self, *, refresh: bool = False) -> list[str]:
        """List ESXi host names, using the cache unless refresh=True."""
        return _datastore_list_host_names(self, refresh=refresh)

    # VM lookup - Delegate to vmware_datastore

    @api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
    def get_vm_by_name(self, name: str) -> Any:
        """Look up a VM object by name."""
        return _datastore_get_vm_by_name(self, name)

    def vm_to_datacenter(self, vm_obj: Any) -> Any:
        """Resolve the datacenter object that owns a VM."""
        return _datastore_vm_to_datacenter(self, vm_obj)

    def vm_datacenter_name(self, vm_obj: Any) -> str | None:
        """Resolve the datacenter name that owns a VM."""
        return _datastore_vm_datacenter_name(self, vm_obj)

    def resolve_datacenter_for_vm(self, vm_name: str, preferred: str | None) -> str:
        """Resolve the datacenter name for a VM, honoring an optional preferred override."""
        return _datastore_resolve_datacenter_for_vm(self, vm_name, preferred)

    def _vm_runtime_host(self, vm_obj: Any) -> Any:
        """Return the ESXi host object currently running a VM."""
        return _datastore_vm_runtime_host(self, vm_obj)

    def _host_parent_compute_name(self, host_obj: Any) -> str | None:
        """Return the name of the cluster/compute resource that parents an ESXi host."""
        return _datastore_host_parent_compute_name(self, host_obj)

    def resolve_host_system_for_vm(self, vm_name: str) -> str:
        """Resolve the ESXi host system name running a VM."""
        return _datastore_resolve_host_system_for_vm(self, vm_name)

    def resolve_compute_for_vm(self, vm_name: str, preferred: str | None) -> str:
        """Resolve the compute resource (cluster/host) name for a VM."""
        return _datastore_resolve_compute_for_vm(self, vm_name, preferred)

    # govc export (stable) - Delegate to vmware_ovftool

    def _ensure_output_dir(self, base: Path) -> Path:
        """Resolve and create the export output directory, returning its absolute path."""
        out = Path(base).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        return out

    def govc_export_ovf(self, opt: ExportOptions) -> Path:
        """Export a VM to OVF using govc."""
        return _ovftool_govc_export_ovf(self, opt)

    def govc_export_ova(self, opt: ExportOptions) -> Path:
        """Export a VM to OVA using govc."""
        return _ovftool_govc_export_ova(self, opt)

    # OVF Tool export/deploy - Delegate to vmware_ovftool

    def _vm_inventory_path_under_vmfolder(self, vm_obj: Any, dc_obj: Any) -> str:
        """
        Compute inventory path relative to Datacenter/vm folder, e.g.
          "<folder1>/<folder2>/<vmname>"

        This is what ovftool expects after ".../<dc_name>/vm/".
        """
        return _ovftool_vm_inventory_path_under_vmfolder(self, vm_obj, dc_obj)

    def _build_ovftool_source_url(self, vm_name: str) -> str:
        """
        Build a vi:// source URL for OVF Tool from VM object + inventory path.

        Format:
          vi://user:pass@host/<Datacenter>/vm/<folder...>/<vm>
        """
        return _ovftool_build_ovftool_source_url(self, vm_name)

    def _ovftool_export_options(self, opt: ExportOptions) -> Any:
        """Build OvfExportOptions from an ExportOptions instance."""
        return _ovftool_ovftool_export_options(self, opt)

    def _ovftool_deploy_options(self, opt: ExportOptions, *, name: str) -> Any:
        """Build OvfDeployOptions from an ExportOptions instance."""
        return _ovftool_ovftool_deploy_options(self, opt, name=name)

    def ovftool_export_vm(self, opt: ExportOptions) -> Path:
        """Export a VM using VMware OVF Tool."""
        return _ovftool_ovftool_export_vm(self, opt)

    def ovftool_deploy_ova(self, source_ova: Path, opt: ExportOptions) -> None:
        """Deploy an OVA to this vSphere/vCenter using VMware OVF Tool."""
        return _ovftool_ovftool_deploy_ova(self, source_ova, opt)

    # Datastore parsing + HTTPS /folder download - Delegate to vmware_datastore

    @staticmethod
    def parse_backing_filename(file_name: str) -> tuple[str, str]:
        """
        Parse VMware style backing fileName:
          "[datastore] path/to/file.ext" -> ("datastore", "path/to/file.ext")
        """
        return _datastore_parse_backing_filename(file_name)

    @staticmethod
    def _split_ds_path(path: str) -> tuple[str, str, str]:
        """
        "[ds] folder/file" -> (ds, "folder", "file")
        """
        return _datastore_split_ds_path(path)

    def _resolve_datacenter_for_download(self, dc_name: str | None) -> str:
        """
        Resolve a usable datacenter name for /folder URL construction.
        """
        return _datastore_resolve_datacenter_for_download(self, dc_name)

    @api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
    def download_datastore_file(  # pylint: disable=too-many-arguments
        self,
        *,
        datastore: str,
        ds_path: str,
        local_path: Path,
        dc_name: str | None = None,
        on_bytes: Any | None = None,
        chunk_size: int = 1024 * 1024,
        force_https: bool = False,
    ) -> None:
        """Download a file from a datastore, delegating to the datastore-utils implementation."""
        return _datastore_download_datastore_file(
            self,
            datastore=datastore,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            on_bytes=on_bytes,
            chunk_size=chunk_size,
            force_https=force_https,
        )

    # Download-only (list via DatastoreBrowser, download via govc/https) - Delegate to vmware_datastore

    def wait_for_task(self, task: Any) -> None:
        """Block until a pyvmomi Task completes, raising on failure."""
        return _datastore_wait_for_task(self, task)

    def _get_vm_datastore_browser(self, vm_obj: Any) -> Any:
        """Return the DatastoreBrowser for a VM's primary datastore."""
        return _datastore_get_vm_datastore_browser(self, vm_obj)

    def _vmx_pathname(self, vm_obj: Any) -> str:
        """Resolve vm_obj's .vmx path."""
        return _datastore_vmx_pathname(self, vm_obj)

    def _list_vm_directory_files(self, vm_obj: Any) -> tuple[str, str, list[str]]:
        """
        Returns: (datastore_name, folder_rel, [files...]) where files are relative to folder_rel.
        Uses DatastoreBrowser.SearchDatastoreSubFolders_Task against the VM folder.
        """
        return _datastore_list_vm_directory_files(self, vm_obj)

    @staticmethod
    def _glob_any(name: str, globs: Sequence[str]) -> bool:
        return _datastore_glob_any(name, globs)

    def _filter_download_only_files(
        self,
        files: Sequence[str],
        *,
        include_globs: Sequence[str],
        exclude_globs: Sequence[str],
        max_files: int,
    ) -> list[str]:
        return _datastore_filter_download_only_files(
            self,
            files,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            max_files=max_files,
        )

    def _download_selected_files(  # pylint: disable=too-many-arguments
        self,
        *,
        selected: Sequence[str],
        out_dir: Path,
        ds_name: str,
        folder_rel: str,
        dc_name: str,
        force_https: bool,
        fail_on_missing: bool,
        log_prefix: str,
    ) -> None:
        return _datastore_download_selected_files(
            self,
            selected=selected,
            out_dir=out_dir,
            ds_name=ds_name,
            folder_rel=folder_rel,
            dc_name=dc_name,
            force_https=force_https,
            fail_on_missing=fail_on_missing,
            log_prefix=log_prefix,
        )

    def download_only_vm(self, opt: ExportOptions) -> Path:
        """Download a VM's files directly from its datastore without converting/exporting."""
        return _datastore_download_only_vm(self, opt)

    def _download_only_vm_force_https(self, opt: ExportOptions) -> Path:
        """
        Forced HTTPS /folder fallback. This bypasses govc even if installed.
        """
        return _datastore_download_only_vm_force_https(self, opt)

    # export (power user path) - Delegate to vmware_export

    def _vpx_uri(self, *, datacenter: str, compute: str, no_verify: bool) -> str:
        q = "?no_verify=1" if no_verify else ""
        user_enc = quote(self.user or "", safe="")
        host = (self.host or "").strip()
        dc_enc = quote((datacenter or "").strip(), safe="")
        compute_norm = (compute or "").strip().lstrip("/")
        compute_enc = quote(compute_norm, safe="/-_.")
        return f"vpx://{user_enc}@{host}/{dc_enc}/{compute_enc}{q}"

    def _write_password_file(self, base_dir: Path) -> Path:
        pw = (self.password or "").strip()
        if not pw:
            raise VMwareError(
                "Missing vSphere password for export (-ip). "
                "Set vs_password or vs_password_env (or vc_password/vc_password_env as fallback)."
            )
        base_dir = self._ensure_output_dir(base_dir)
        pwfile = base_dir / f".export-pass-{os.getpid()}.txt"
        # Create file atomically with secure permissions to avoid race condition (CWE-377)
        try:
            fd = os.open(str(pwfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Stale file from crashed run (extremely rare - requires PID reuse after reboot)
            # Remove it and retry once
            pwfile.unlink(missing_ok=True)
            fd = os.open(str(pwfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, (pw + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        atexit.register(lambda p=pwfile: p.unlink(missing_ok=True))
        return pwfile

    def _build_virt_export_cmd(self, opt: ExportOptions, *, password_file: Path) -> list[str]:
        if not opt.vm_name:
            raise VMwareError("ExportOptions.vm_name is required")
        if not self.si:
            raise VMwareError("Not connected to vSphere; cannot export. Call connect() first.")

        resolved_dc = self.resolve_datacenter_for_vm(opt.vm_name, opt.datacenter)
        resolved_compute = self.resolve_compute_for_vm(opt.vm_name, opt.compute)

        transport = (opt.transport or "").strip().lower()
        if transport not in ("vddk", "ssh"):
            raise VMwareError(f"Unsupported export transport: {transport!r} (expected 'vddk' or 'ssh')")

        argv: list[str] = [
            "export",
            "-i",
            "libvirt",
            "-ic",
            self._vpx_uri(datacenter=resolved_dc, compute=resolved_compute, no_verify=opt.no_verify),
            "-it",
            transport,
            "-ip",
            str(password_file),
        ]

        if transport == "vddk":
            if opt.vddk_libdir:
                argv += ["-io", f"vddk-libdir={Path(opt.vddk_libdir)!s}"]
            if opt.vddk_thumbprint:
                argv += ["-io", f"vddk-thumbprint={opt.vddk_thumbprint!s}"]
            if opt.vddk_snapshot_moref:
                argv += ["-io", f"vddk-snapshot={opt.vddk_snapshot_moref}"]
            if opt.vddk_transports:
                argv += ["-io", f"vddk-transports={opt.vddk_transports}"]

        argv.append(opt.vm_name)
        self._ensure_output_dir(opt.output_dir)
        argv += ["-o", "local", "-os", str(opt.output_dir), "-of", opt.output_format]
        argv += list(opt.extra_args)
        return argv

    def _popen_text(self, argv: Sequence[str], *, env: dict[str, str] | None = None) -> Any:
        """Start a govc subprocess with pipes, returning the Popen for the pump helpers below."""
        self.logger.info("Running: %s", " ".join(shlex.quote(a) for a in argv))
        # pylint: disable-next=consider-using-with  # process outlives this method; consumed by the _pump_lines_* helpers and reaped by the caller
        proc = subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,
        )
        if proc.stdout is None or proc.stderr is None:
            raise RuntimeError(
                "Failed to capture govc command output. "
                "Check system resources (open file limits, available memory)."
            )
        if SELECT_AVAILABLE:
            try:
                os.set_blocking(proc.stdout.fileno(), False)  # type: ignore[attr-defined]
                os.set_blocking(proc.stderr.fileno(), False)  # type: ignore[attr-defined]
            except OSError:
                pass
        return proc

    def _pump_lines_blocking(self, proc: Any) -> list[str]:
        if proc.stdout is None or proc.stderr is None:
            raise RuntimeError(
                "Failed to capture govc command output. "
                "Check system resources (open file limits, available memory)."
            )
        lines: list[str] = []
        out_line = proc.stdout.readline()
        err_line = proc.stderr.readline()
        if out_line:
            lines.append(out_line.rstrip("\n"))
        if err_line:
            lines.append(err_line.rstrip("\n"))
        return lines

    def _pump_lines_select(self, proc: Any, *, timeout_s: float = 0.20) -> list[str]:
        if proc.stdout is None or proc.stderr is None:
            raise RuntimeError(
                "Failed to capture govc command output. "
                "Check system resources (open file limits, available memory)."
            )
        rlist = [proc.stdout, proc.stderr]
        try:
            ready, _, _ = select.select(rlist, [], [], timeout_s)  # type: ignore[union-attr]
        except OSError:
            ready = rlist

        lines: list[str] = []
        for s in ready:
            try:
                chunk = s.read()
            except OSError:
                chunk = ""
            if not chunk:
                continue
            for ln in chunk.splitlines():
                lines.append(ln.rstrip("\n"))
        return lines

    def _drain_remaining_output(self, proc: Any, *, max_rounds: int = 10) -> None:
        for _ in range(max_rounds):
            lines = (
                self._pump_lines_select(proc, timeout_s=0.05)
                if SELECT_AVAILABLE
                else self._pump_lines_blocking(proc)
            )
            if not lines:
                break
            for ln in lines:
                s = ln.strip()
                if s:
                    self.logger.info("%s", s)

    def _run_logged_subprocess(self, argv: Sequence[str], *, env: dict[str, str] | None = None) -> int:
        proc = self._popen_text(argv, env=env)

        def pump() -> list[str]:
            if SELECT_AVAILABLE:
                return self._pump_lines_select(proc)
            return self._pump_lines_blocking(proc)

        # Plain logger loop
        while True:
            lines = pump()
            for ln in lines:
                s = ln.strip()
                if s:
                    self.logger.info("%s", s)
            if (not lines) and (proc.poll() is not None):
                break

        self._drain_remaining_output(proc, max_rounds=10)
        return int(proc.wait())

    # NOTE: export functionality uses pure hyper2kvm architecture
    # Legacy method removed

    # VDDK raw disk download (experimental orchestration only) - Delegate to vmware_vddk

    def _require_vddk_client(self) -> None:
        if not VDDK_CLIENT_AVAILABLE:
            raise VMwareError(
                "VDDK raw download requested but vddk_client is not importable. "
                "Ensure hyper2kvm/vsphere/vddk_client.py exists and imports cleanly."
            )

    def vm_disks(self, vm_obj: Any) -> list[Any]:
        """Return the list of VirtualDisk devices attached to a VM."""
        return _vddk_vm_disks(self, vm_obj)

    def select_disk(self, vm_obj: Any, label_or_index: str | None) -> Any:
        """Select a VM disk by index or by (case-insensitive substring) label."""
        return _vddk_select_disk(self, vm_obj, label_or_index)

    def _vm_disk_backing_filename(self, disk_obj: Any) -> str:
        backing = getattr(disk_obj, "backing", None)
        fn = getattr(backing, "fileName", None) if backing else None
        if not fn:
            raise VMwareError("Selected disk has no backing.fileName (unexpected)")
        return str(fn)

    def _resolve_esx_host_for_vm(self, vm_obj: Any) -> str:
        host_obj = self._vm_runtime_host(vm_obj)
        if host_obj is None:
            raise VMwareError("VM has no runtime.host; cannot determine ESXi host for VDDK download")
        name = str(getattr(host_obj, "name", "") or "").strip()
        if not name:
            raise VMwareError("Could not resolve ESXi host name for VM runtime.host")
        return name

    def _default_vddk_download_path(self, opt: ExportOptions, *, disk_index: int) -> Path:
        out_dir = self._ensure_output_dir(opt.output_dir)
        return out_dir / f"{_safe_vm_name(opt.vm_name)}-disk{disk_index}.vmdk"

    def vddk_download_disk(self, opt: ExportOptions) -> Path:
        """Download a VM disk directly via VDDK (experimental raw download path)."""
        return _vddk_download_disk(self, opt)

    # Unified entrypoint (policy) - refactored into smaller handlers

    @staticmethod
    def _normalize_export_mode(mode: str | None) -> str:
        return (mode or "ovf_export").strip().lower()

    def _handle_mode_vddk(self, mode: str, opt: ExportOptions) -> Path | None:
        if mode in ("vddk_download", "vddk-download", "vddkdownload"):
            return self.vddk_download_disk(opt)
        return None

    def _handle_mode_export(self, mode: str, _opt: ExportOptions) -> Path | None:
        """Handle 'export'/'virt_export' modes (no dedicated implementation; falls through)."""
        # NOTE: these modes have no dedicated implementation (this used to call a nonexistent
        # self.export_export_vm()); fall through to the stable OVF->OVA->HTTPS chain via the
        # "Unknown export_mode" handling at the end of export_vm().
        if mode in ("export", "virt_export"):
            self.logger.debug("Export mode=%r has no dedicated handler; falling through to stable chain", mode)

    def _handle_mode_ovftool(self, mode: str, opt: ExportOptions) -> Path | None:
        if mode in ("ovftool_export", "ovftool", "ovftool-export"):
            self.logger.info("Export mode=OVF Tool: attempting OVF Tool export for VM=%s", opt.vm_name)
            return self.ovftool_export_vm(opt)
        return None

    def _handle_mode_download_only(self, mode: str, opt: ExportOptions) -> Path | None:
        if mode in ("download_only", "download-only", "download"):
            return self.download_only_vm(opt)
        return None

    def _stable_chain_ovf_ova_https(self, opt: ExportOptions, *, log_context: str) -> Path:
        try:
            self.logger.info("%s: attempting govc export.ovf for VM=%s", log_context, opt.vm_name)
            return self.govc_export_ovf(opt)
        # pylint: disable-next=broad-exception-caught  # govc/pyvmomi raise dynamic errors; fall through to the next chain link
        except Exception as e_ovf:
            self.logger.warning("%s: govc export.ovf failed; trying export.ova next: %s", log_context, e_ovf)
            try:
                return self.govc_export_ova(opt)
            # pylint: disable-next=broad-exception-caught  # govc/pyvmomi raise dynamic errors; fall through to the HTTPS fallback
            except Exception as e_ova:
                self.logger.warning(
                    "%s: govc export.ova also failed; forcing HTTPS /folder fallback: %s", log_context, e_ova
                )
                return self._download_only_vm_force_https(opt)

    def _stable_chain_ova_https(self, opt: ExportOptions, *, log_context: str) -> Path:
        try:
            self.logger.info("%s: attempting govc export.ova for VM=%s", log_context, opt.vm_name)
            return self.govc_export_ova(opt)
        # pylint: disable-next=broad-exception-caught  # govc/pyvmomi raise dynamic errors; fall through to the HTTPS fallback
        except Exception as e_ova:
            self.logger.warning(
                "%s: govc export.ova failed; forcing HTTPS /folder fallback: %s", log_context, e_ova
            )
            return self._download_only_vm_force_https(opt)

    def export_vm(self, opt: ExportOptions) -> Path:
        """
        Export VM using specified export mode.
        """
        log_event(
            "vm_export_start", vm_name=opt.vm_name, export_mode=opt.export_mode, transport=opt.transport
        )
        mode = self._normalize_export_mode(opt.export_mode)

        # Explicit/special modes first (no fallback unless explicitly coded)
        for handler in (self._handle_mode_vddk, self._handle_mode_export):
            out = handler(mode, opt)
            if out is not None:
                return out

        # OVF Tool requested: if it fails, fall through to stable chain
        try:
            out = self._handle_mode_ovftool(mode, opt)
            if out is not None:
                return out
        # pylint: disable-next=broad-exception-caught  # OVF Tool subprocess raises dynamic errors; fall through to the stable chain
        except Exception as e:
            self.logger.warning("OVF Tool export failed; falling back to stable chain: %s", e)

        out = self._handle_mode_download_only(mode, opt)
        if out is not None:
            return out

        # Stable families
        if mode in ("ovf_export", "ovf", "export_ovf", "govc_ovf", "govc_export"):
            return self._stable_chain_ovf_ova_https(opt, log_context="Export mode=OVF (stable)")

        if mode in ("ova_export", "ova", "export_ova", "govc_ova"):
            return self._stable_chain_ova_https(opt, log_context="Export mode=OVA")

        # Unknown -> stable default chain
        self.logger.warning("Unknown export_mode=%r; using stable OVF->OVA->HTTPS chain", mode)
        return self._stable_chain_ovf_ova_https(opt, log_context="Export mode=UNKNOWN (stable fallback)")
