# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Active Directory membership information extraction.

Extracts domain membership metadata from offline Windows registry for
preservation and automated domain rejoin after VM migration.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DomainInfo:
    """Active Directory domain membership information."""

    is_domain_joined: bool = False
    domain_name: Optional[str] = None
    computer_name: Optional[str] = None
    dns_domain: Optional[str] = None
    last_dc: Optional[str] = None
    workgroup: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "is_domain_joined": self.is_domain_joined,
            "domain_name": self.domain_name,
            "computer_name": self.computer_name,
            "dns_domain": self.dns_domain,
            "last_dc": self.last_dc,
            "workgroup": self.workgroup,
        }


# pylint: disable=duplicate-code
# reason: mirrors _navigate_key/_read_registry_value in
# h2kvm/fixers/windows/license/extractor.py -- both are small hivex
# key-path readers local to unrelated fixer domains (AD vs. licensing);
# a shared home belongs in registry/encoding.py, out of scope for this pass.
def _read_registry_sz_value(h, key_path: str, value_name: str):
    """Navigate a hivex key_path (backslash-separated) and read value_name as a string.

    Mirrors the local helper in h2kvm.fixers.windows.license.extractor since
    no shared ``read_registry_value`` helper exists in registry.encoding.
    """
    # Lazy: avoid importing hivex-backed internals until a hive is actually open.
    from h2kvm.fixers.windows.registry.encoding import (  # pylint: disable=import-outside-toplevel
        _hivex_read_sz,
        _hivex_read_value_dict,
        _node_id,
    )

    node = h.root()
    for component in key_path.split("\\"):
        if not component:
            continue
        child = h.node_get_child(node, component)
        if not _node_id(child):
            return None
        node = child

    result = _hivex_read_sz(h, node, value_name)
    if result is not None:
        return result
    vd = _hivex_read_value_dict(h, node, value_name)
    if vd is not None:
        raw = vd.get("value")
        if raw is not None:
            return raw
    return None


# Walks SYSTEM+SOFTWARE hives across several registry paths with independent best-effort fallbacks.
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def extract_domain_info(guestfs, root: str) -> DomainInfo:
    """Extract Active Directory membership information from offline registry.

    Args:
        guestfs: GuestFS instance with mounted filesystem
        root: Root path of Windows installation

    Returns:
        DomainInfo object with extracted domain data

    Raises:
        RuntimeError: If registry hives cannot be accessed
    """
    # Lazy: only needed when a hive is actually downloaded/opened, and avoids
    # importing hivex-backed registry internals when no Windows hive is present.
    import tempfile  # pylint: disable=import-outside-toplevel
    from pathlib import Path  # pylint: disable=import-outside-toplevel

    from h2kvm.fixers.windows.registry.encoding import (  # pylint: disable=import-outside-toplevel
        _close_best_effort,
        _detect_current_controlset,
    )
    from h2kvm.fixers.windows.registry.io import (  # pylint: disable=import-outside-toplevel
        detect_windows_hive,
        download_and_open_hive,
    )

    logger.info("Extracting Active Directory domain information")

    domain_info = DomainInfo()

    try:
        # Locate SYSTEM hive for computer name and domain info
        system_path = detect_windows_hive(guestfs, root, "SYSTEM")
        if not system_path:
            logger.warning("SYSTEM hive not found")
            return domain_info

        with tempfile.TemporaryDirectory() as tmpdir:
            local_system_hive = Path(tmpdir) / "SYSTEM"
            system_hive = download_and_open_hive(
                logger, guestfs, system_path, local_system_hive, write=False
            )

            try:
                # Determine current control set
                try:
                    controlset = _detect_current_controlset(system_hive, system_hive.root())
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort control-set detection; fall back to the common default
                    controlset = "ControlSet001"  # Default

                logger.debug("Using %s for domain info extraction", controlset)

                # Extract computer name
                computer_name_path = f"{controlset}\\Control\\ComputerName\\ComputerName"
                try:
                    domain_info.computer_name = _read_registry_sz_value(
                        system_hive, computer_name_path, "ComputerName"
                    )
                    logger.debug("Computer name: %s", domain_info.computer_name)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry read; a missing value must not abort extraction
                    logger.debug("Could not read computer name: %s", e)

                # Extract domain/workgroup information
                tcpip_params_path = f"{controlset}\\Services\\Tcpip\\Parameters"
                try:
                    # Check for domain membership
                    domain = _read_registry_sz_value(system_hive, tcpip_params_path, "Domain")
                    if domain:
                        domain_info.domain_name = domain
                        domain_info.is_domain_joined = True
                        logger.info("Domain-joined: %s", domain)
                    else:
                        # Not domain-joined, check workgroup
                        workgroup = _read_registry_sz_value(system_hive, tcpip_params_path, "NV Domain")
                        if workgroup:
                            domain_info.workgroup = workgroup
                            logger.info("Workgroup: %s", workgroup)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry read; a missing value must not abort extraction
                    logger.debug("Could not read domain/workgroup: %s", e)

                # Try to get DNS domain (more reliable for domain-joined systems)
                try:
                    dns_domain = _read_registry_sz_value(system_hive, tcpip_params_path, "DhcpDomain")
                    if not dns_domain:
                        dns_domain = _read_registry_sz_value(system_hive, tcpip_params_path, "Domain")

                    if dns_domain and dns_domain != domain_info.workgroup:
                        domain_info.dns_domain = dns_domain
                        logger.debug("DNS domain: %s", dns_domain)
                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry read; a missing value must not abort extraction
                    logger.debug("Could not read DNS domain: %s", e)

            finally:
                _close_best_effort(system_hive)

        # Try SOFTWARE hive for Group Policy information (contains DC info)
        try:
            software_path = detect_windows_hive(guestfs, root, "SOFTWARE")
            if software_path:
                with tempfile.TemporaryDirectory() as tmpdir2:
                    local_software_hive = Path(tmpdir2) / "SOFTWARE"
                    software_hive = download_and_open_hive(
                        logger, guestfs, software_path, local_software_hive, write=False
                    )

                    try:
                        # Extract last known domain controller from Group Policy history
                        gp_history_path = r"Microsoft\Windows\CurrentVersion\Group Policy\History"
                        try:
                            dc_name = _read_registry_sz_value(software_hive, gp_history_path, "DCName")
                            if dc_name:
                                domain_info.last_dc = dc_name
                                logger.debug("Last DC: %s", dc_name)
                        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry read; a missing value must not abort extraction
                            logger.debug("Could not read DC name: %s", e)

                        # Verify DNS domain from GP history if not found earlier
                        if not domain_info.dns_domain:
                            try:
                                network_name = _read_registry_sz_value(
                                    software_hive, gp_history_path, "NetworkName"
                                )
                                if network_name:
                                    domain_info.dns_domain = network_name
                                    logger.debug("DNS domain from GP: %s", network_name)
                            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry read; a missing value must not abort extraction
                                logger.debug("Could not read GP network name: %s", e)

                    finally:
                        _close_best_effort(software_hive)

        except Exception as e:  # pylint: disable=broad-exception-caught  # SOFTWARE hive is optional context; its absence must not abort extraction
            logger.debug("Could not access SOFTWARE hive for GP info: %s", e)

        # Final determination of domain join status
        if domain_info.domain_name and domain_info.dns_domain:
            domain_info.is_domain_joined = True
        elif domain_info.workgroup:
            domain_info.is_domain_joined = False

        logger.info(
            "Domain info extracted: domain_joined=%s, domain=%s",
            domain_info.is_domain_joined,
            domain_info.domain_name or domain_info.workgroup,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught  # top-level fixer step must not crash the whole migration over one guest's registry quirks
        logger.exception("Failed to extract domain information: %s", e)
        logger.debug("Domain extraction error", exc_info=True)

    return domain_info
