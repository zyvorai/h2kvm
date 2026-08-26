# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Hostname and hosts file configuration injector."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hyper2kvm.core.guestfs_typing import guestfs


def inject_hostname_config(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # covers hostname + /etc/hosts config in one pass
    self, g: guestfs.GuestFS
) -> dict[str, Any]:
    """Configure hostname, domain, and /etc/hosts."""
    logger = getattr(self, "logger", None)

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    # pylint: disable=duplicate-code
    # reason: config-presence/type-check boilerplate mirrors
    # hyper2kvm/fixers/injectors/service_config_injector.py's inject_service_config(),
    # but the results dict shape differs per injector (hostname_set/hosts_entries_added
    # vs enabled/disabled/masked) -- coincidental shape, not shared logic.
    config = getattr(self, "hostname_config_inject", None)
    if config is None:
        return {"injected": False, "reason": "no_config"}
    if not isinstance(config, dict):
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "hostname_set": False,
        "hosts_entries_added": 0,
    }

    hostname = config.get("hostname")
    domain = config.get("domain")
    hosts = config.get("hosts", {})

    if not hostname and not hosts:
        return {"injected": False, "reason": "no_config"}

    # Set hostname
    if hostname:
        if dry:
            _log("info", f"DRY-RUN: would set hostname to {hostname}")
            results["hostname_set"] = True
        else:
            try:
                # Write /etc/hostname
                g.write("/etc/hostname", f"{hostname}\n".encode())

                # Update /etc/hosts
                hosts_content = g.read_file("/etc/hosts").decode("utf-8") if g.is_file("/etc/hosts") else ""

                lines = hosts_content.splitlines()
                new_lines = []
                updated_127 = False

                for line in lines:
                    if line.strip().startswith("127.0.1.1"):
                        fqdn = f"{hostname}.{domain}" if domain else hostname
                        new_lines.append(f"127.0.1.1\t{fqdn} {hostname}")
                        updated_127 = True
                    else:
                        new_lines.append(line)

                if not updated_127:
                    fqdn = f"{hostname}.{domain}" if domain else hostname
                    new_lines.insert(1, f"127.0.1.1\t{fqdn} {hostname}")

                g.write("/etc/hosts", "\n".join(new_lines).encode("utf-8"))
                results["hostname_set"] = True
                _log("info", f"Set hostname to {hostname}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest hostname injection must not abort the migration
                _log("error", f"Failed to set hostname: {e}")

    # Add custom hosts entries
    if hosts:
        if dry:
            results["hosts_entries_added"] = len(hosts)
        else:
            try:
                if g.is_file("/etc/hosts"):
                    hosts_content = g.read_file("/etc/hosts").decode("utf-8")
                else:
                    hosts_content = "127.0.0.1\tlocalhost\n"

                for ip, names in hosts.items():
                    hosts_content += f"{ip}\t{names}\n"
                    results["hosts_entries_added"] += 1

                g.write("/etc/hosts", hosts_content.encode("utf-8"))
                _log("info", f"Added {len(hosts)} hosts entries")
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort guest hosts-file injection must not abort the migration
                _log("error", f"Failed to update hosts: {e}")

    return results
