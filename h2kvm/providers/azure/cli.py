# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Azure CLI wrapper with retry logic and error handling."""
# h2kvm/azure/cli.py

from __future__ import annotations

import json
import logging
import random
import subprocess
import time
from typing import Any

from h2kvm.core.retry_decorator import api_retry

from .exceptions import AzureAuthError, AzureCLIError

LOG = logging.getLogger(__name__)


def _is_transient(stderr: str) -> bool:
    s = (stderr or "").lower()
    return any(
        x in s
        for x in (
            "throttle",
            "too many requests",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "internal server error",
            "gateway timeout",
            "connection reset",
            "connection aborted",
            "rate limit",
            "server busy",
            "retry later",
        )
    )


def _backoff_sleep(attempt: int, base: float, cap: float) -> None:
    # exp backoff with jitter
    t = min(cap, base * (2**attempt))
    t = t * (0.7 + random.random() * 0.6)
    time.sleep(t)


def run_az_json(args: list[str], *, timeout_s: int = 300, retries: int = 3) -> Any:
    """
    Run 'az <args> --output json --only-show-errors' and parse JSON.
    Retries transient failures.
    """
    cmd = ["az", *args, "--output", "json", "--only-show-errors"]

    last_err = ""
    for attempt in range(max(1, retries)):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        except FileNotFoundError:
            raise AzureCLIError("Azure CLI 'az' not found. Install Azure CLI.") from None
        except subprocess.TimeoutExpired:
            last_err = f"az timed out after {timeout_s}s"
            if attempt + 1 < retries:
                _backoff_sleep(attempt, 1.0, 15.0)
                continue
            raise AzureCLIError(last_err) from None

        if p.returncode == 0:
            out = (p.stdout or "").strip()
            if out == "":
                return None
            try:
                return json.loads(out)
            except Exception as e:
                raise AzureCLIError(f"Failed to parse az JSON output: {e}") from e

        last_err = (p.stderr or p.stdout or "").strip()
        if attempt + 1 < retries and _is_transient(last_err):
            _backoff_sleep(attempt, 1.0, 15.0)
            continue

        raise AzureCLIError(f"az failed: {' '.join(args)} :: {last_err}")

    raise AzureCLIError(f"az failed: {' '.join(args)} :: {last_err}")


def validate_account(subscription: str | None, tenant: str | None) -> dict[str, Any]:
    """Verify the Azure CLI is logged in, optionally selecting a subscription/tenant."""
    # Verify logged in
    try:
        acct = run_az_json(["account", "show"], timeout_s=30, retries=2)
    except AzureCLIError as e:
        raise AzureAuthError(f"Azure CLI not logged in or not usable: {e}") from e

    if subscription:
        run_az_json(["account", "set", "--subscription", subscription], timeout_s=60, retries=2)
        acct = run_az_json(["account", "show"], timeout_s=30, retries=2)

    if tenant and str(acct.get("tenantId")) != str(tenant):
        raise AzureAuthError(f"Tenant mismatch: expected {tenant}, got {acct.get('tenantId')}")

    return acct


@api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
def list_vms(resource_group: str | None, *, show_details: bool = False) -> list[dict[str, Any]]:
    """
    List VMs, optionally with instance details (including power state).

    Args:
        resource_group: Optional resource group filter
        show_details: If True, includes instance view with power state (slower but more complete)

    Returns:
        List of VM dictionaries
    """
    args = ["vm", "list"]
    if resource_group:
        args += ["--resource-group", resource_group]
    if show_details:
        args += ["--show-details"]
    data = run_az_json(args, timeout_s=180, retries=3)  # Increased timeout for --show-details
    return list(data or [])


@api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
def get_vm_show(rg: str, name: str) -> dict[str, Any]:
    """Return `az vm show` details for the given resource group and VM name."""
    return run_az_json(["vm", "show", "--resource-group", rg, "--name", name], timeout_s=120, retries=3)


def extract_power_state_from_vm_dict(vm: dict[str, Any]) -> str | None:
    """
    Extract power state from VM dictionary (requires --show-details in list_vms).

    Args:
        vm: VM dictionary from az vm list --show-details

    Returns:
        Power state string (e.g., "running", "stopped", "deallocated") or None if not available
    """
    # Check for powerState field (added by --show-details)
    ps = vm.get("powerState")
    if ps:
        # Format is "VM running" or "VM stopped", extract the status part
        parts = str(ps).lower().split()
        if len(parts) >= 2:
            return parts[1]  # "running", "stopped", "deallocated"
        return ps.lower()

    # Fallback: check instance view if embedded
    iv = vm.get("instanceView")
    if iv:
        statuses = iv.get("statuses") or []
        for st in statuses:
            code = st.get("code") or ""
            if code.lower().startswith("powerstate/"):
                return code.split("/", 1)[1].lower()

    return None


@api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
def get_vm_power_state(rg: str, name: str) -> str:
    """Get VM power state via dedicated API call (slower, use extract_power_state_from_vm_dict when possible)."""
    # instance view is slower, but accurate
    iv = run_az_json(
        ["vm", "get-instance-view", "--resource-group", rg, "--name", name], timeout_s=120, retries=3
    )
    statuses = (iv or {}).get("statuses") or []
    for st in statuses:
        code = st.get("code") or ""
        if code.lower().startswith("powerstate/"):
            return code.split("/", 1)[1].lower()
    return "unknown"


def disk_show_by_id(disk_id: str) -> dict[str, Any]:
    """Return `az disk show` details for the given disk resource ID."""
    return run_az_json(["disk", "show", "--ids", disk_id], timeout_s=120, retries=3)


def snapshot_create(
    *, rg: str, name: str, source_disk_id: str, location: str, tags: dict[str, str]
) -> dict[str, Any]:
    """Create an Azure disk snapshot from `source_disk_id`."""
    args = [
        "snapshot",
        "create",
        "--resource-group",
        rg,
        "--name",
        name,
        "--source",
        source_disk_id,
        "--location",
        location,
    ]
    if tags:
        args += ["--tags"] + [f"{k}={v}" for k, v in tags.items()]
    return run_az_json(args, timeout_s=600, retries=5)


def disk_create_from_snapshot(
    *, rg: str, name: str, snapshot_id: str, location: str, tags: dict[str, str]
) -> dict[str, Any]:
    """Create a new Azure managed disk from `snapshot_id`."""
    args = [
        "disk",
        "create",
        "--resource-group",
        rg,
        "--name",
        name,
        "--source",
        snapshot_id,
        "--location",
        location,
    ]
    if tags:
        args += ["--tags"] + [f"{k}={v}" for k, v in tags.items()]
    return run_az_json(args, timeout_s=600, retries=5)


def disk_grant_access_by_id(*, disk_id: str, duration_s: int) -> str:
    """Grant read (SAS) access to a disk for `duration_s` seconds and return the SAS URL."""
    out = run_az_json(
        [
            "disk",
            "grant-access",
            "--ids",
            disk_id,
            "--duration-in-seconds",
            str(duration_s),
            "--access-level",
            "Read",
        ],
        timeout_s=180,
        retries=5,
    )
    sas = (out or {}).get("accessSas")
    if not sas:
        raise AzureCLIError("disk grant-access returned no accessSas")
    return sas


def disk_revoke_access_by_id(*, disk_id: str) -> None:
    """Revoke previously granted SAS access to a disk."""
    run_az_json(["disk", "revoke-access", "--ids", disk_id], timeout_s=180, retries=5)


def snapshot_grant_access_by_id(*, snapshot_id: str, duration_s: int) -> str:
    """Grant read (SAS) access to a snapshot for `duration_s` seconds and return the SAS URL."""
    out = run_az_json(
        [
            "snapshot",
            "grant-access",
            "--ids",
            snapshot_id,
            "--duration-in-seconds",
            str(duration_s),
            "--access-level",
            "Read",
        ],
        timeout_s=180,
        retries=5,
    )
    sas = (out or {}).get("accessSas")
    if not sas:
        raise AzureCLIError("snapshot grant-access returned no accessSas")
    return sas


def snapshot_revoke_access_by_id(*, snapshot_id: str) -> None:
    """Revoke previously granted SAS access to a snapshot."""
    run_az_json(["snapshot", "revoke-access", "--ids", snapshot_id], timeout_s=180, retries=5)


def resource_delete_by_id(*, resource_id: str) -> None:
    """Delete any Azure resource by its resource ID."""
    # generic delete
    run_az_json(["resource", "delete", "--ids", resource_id], timeout_s=600, retries=5)


def vm_stop_or_deallocate(*, rg: str, name: str, mode: str, wait: bool) -> None:
    """Stop or deallocate a VM per `mode` ("none"/"stop"/"deallocate"), optionally waiting."""
    mode = (mode or "none").lower()
    if mode == "none":
        return
    if mode == "stop":
        args = ["vm", "stop", "--resource-group", rg, "--name", name]
    elif mode == "deallocate":
        args = ["vm", "deallocate", "--resource-group", rg, "--name", name]
    else:
        raise AzureCLIError(f"Unknown shutdown.mode={mode}")

    if not wait:
        args.append("--no-wait")
    run_az_json(args, timeout_s=600, retries=5)

    if wait:
        # poll until stopped/deallocated
        for _ in range(120):
            ps = get_vm_power_state(rg, name)
            if mode == "stop" and ps in ("stopped", "stoppedallocated"):
                return
            if mode == "deallocate" and ps == "deallocated":
                return
            time.sleep(5)
        raise AzureCLIError(f"VM did not reach expected power state after {mode}: {rg}/{name}")


def best_effort_quiesce_vm(rg: str, name: str, guest_hint: str | None) -> None:
    """Best-effort guest quiesce hook before snapshotting (currently a non-fatal no-op stub)."""
    # Stub: leave this as best-effort hook.
    # In practice you may implement:
    # - Linux: fsfreeze via run-command
    # - Windows: VSS via run-command / agents
    # Keep it non-fatal.
    _ = (rg, name, guest_hint)
