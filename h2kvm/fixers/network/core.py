# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/network/core.py
"""
Network configuration fixer for VMware to KVM migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .backend import NetworkFixersBackend
from .discovery import NetworkDiscovery
from .model import FixLevel, FixResult, NetworkConfig, NetworkConfigType
from .topology import NetworkTopology
from .udev_rules import inject_persistent_net_rules
from .validation import NetworkValidation

# pylint: disable=duplicate-code  # typing-only guestfs fallback stub is deliberately repeated per-module
if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # Typing-only fallback so annotations referencing ``guestfs.GuestFS``
        # still resolve when the real ``guestfs`` library isn't installed.
        # Named to match the real module so type checkers accept the alias.
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,too-few-public-methods
            """Typing-only stand-in for the ``guestfs`` module."""

            class GuestFS(Protocol):  # pylint: disable=too-few-public-methods
                """Typing-only stand-in for ``guestfs.GuestFS``."""
# pylint: enable=duplicate-code


class NetworkFixer:  # pylint: disable=too-many-instance-attributes  # orchestrator composing all network-fixer helpers
    """
    Network configuration fixer for VMware to KVM migration.
    """

    # VMware-specific driver patterns to remove
    VMWARE_DRIVERS = {
        "vmxnet3": r"\bvmxnet3\b",
        "e1000": r"\be1000\b",
        "e1000e": r"\be1000e\b",
        "vmxnet": r"\bvmxnet\b",
        "vlance": r"\bvlance\b",
        "pvscsi": r"\bpvscsi\b",
        "vmw_pvscsi": r"\bvmw_pvscsi\b",
    }

    # MAC address pinning patterns to remove
    MAC_PINNING_PATTERNS = [
        (r"(?im)^\s*HWADDR\s*=.*$", "ifcfg-hwaddr"),
        (r"(?im)^\s*MACADDR\s*=.*$", "ifcfg-macaddr"),
        (r"(?im)^\s*MACADDRESS\s*=.*$", "ifcfg-macaddress"),
        (r"(?im)^\s*CLONED_MAC\s*=.*$", "ifcfg-cloned-mac"),
        (r"(?im)^\s*macaddress\s*:.*$", "netplan-macaddress"),
        (r"(?im)^\s*cloned-mac-address\s*:.*$", "netplan-cloned-mac"),
        (r"(?im)^\s*hwaddress\s+ether\s+.*$", "interfaces-hwaddress"),
        (r"(?im)^\s*MACAddress\s*=.*$", "systemd-macaddress"),
        (r"(?im)^\s*Match\s+MACAddress\s*=.*$", "systemd-match-mac"),
        (r"(?im)^\s*mac-address\s*=.*$", "nm-mac-address"),
        (r"(?im)^\s*cloned-mac-address\s*=.*$", "nm-cloned-mac"),
        (r"(?im)^\s*mac-address-blacklist\s*=.*$", "nm-mac-blacklist"),
    ]

    def __init__(
        self,
        logger: logging.Logger,
        fix_level: FixLevel = FixLevel.MODERATE,
        *,
        dry_run: bool = False,
        backup_suffix: str | None = None,
    ):
        """
        Initialize network fixer orchestrator.

        Args:
            logger: Logger instance
            fix_level: Fix level (CONSERVATIVE, MODERATE, AGGRESSIVE)
            dry_run: If True, don't write changes to disk
            backup_suffix: Backup file suffix (auto-generated if not provided)
        """
        self.logger = logger
        self.fix_level = fix_level
        self.dry_run = dry_run
        self.backup_suffix = backup_suffix or f".h2kvm_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create helper module instances (composition over inheritance)
        self.discovery = NetworkDiscovery(logger=logger, backup_suffix=self.backup_suffix)
        self.topology = NetworkTopology(logger=logger, fix_level=fix_level)
        self.validation = NetworkValidation(logger=logger)
        self.backend = NetworkFixersBackend(
            logger=logger,
            fix_level=fix_level,
            vmware_drivers=self.VMWARE_DRIVERS,
            mac_pinning_patterns=self.MAC_PINNING_PATTERNS,
        )

    # Main orchestration pipeline

    def fix_network_config(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # 7-phase fixer pipeline
        self,
        g: guestfs.GuestFS,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Main orchestration method - coordinates all network fixing operations.

        Pipeline:
        1. Discovery: Find all network config files
        2. Topology: Build device relationship graph
        3. Planning: Compute interface renames (AGGRESSIVE mode only)
        4. Fixing: Apply backend-specific fixes
        5. Validation: Verify fixes didn't corrupt configs
        6. Apply: Write changes to disk (unless dry_run)
        7. Summary: Generate statistics and recommendations

        Args:
            g: GuestFS handle with root filesystem mounted
            progress_callback: Optional progress callback (current, total, message)

        Returns:
            Dict with detailed statistics, warnings, and recommendations
        """
        self.logger.info(
            "🌐 Starting network fixes (level=%s dry_run=%s)", self.fix_level.value, self.dry_run
        )

        # Phase 1: Discovery
        configs = self.discovery.find_network_configs(g)
        if not configs:
            self.logger.info("No network configuration files found")
            return {
                "stats": {
                    "total_files": 0,
                    "files_modified": 0,
                    "files_failed": 0,
                    "backups_created": 0,
                    "total_fixes_applied": 0,
                    "dry_run": self.dry_run,
                    "by_type": {},
                    "details": [],
                },
                "warnings": [],
                "recommendations": [
                    "No network configuration files found. Manual network setup may be required."
                ],
            }

        self.logger.info("Found %d network configuration files", len(configs))

        # Phase 1.5: Remove stale udev rules that pin MAC→interface name,
        # then generate new correct ones based on current network config.
        # The old VMware-era rules reference vmxnet3 MACs with wrong names;
        # we replace them with rules that map the preserved MACs to the
        # expected interface names so static IP configs survive migration.
        if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE) and not self.dry_run:
            stale_udev_rules = [
                "/etc/udev/rules.d/70-persistent-net.rules",
                "/etc/udev/rules.d/75-persistent-net-generator.rules",
            ]
            for rule_path in stale_udev_rules:
                try:
                    if g.is_file(rule_path):
                        g.rm(rule_path)
                        self.logger.info("Removed stale udev rule: %s", rule_path)
                except Exception:  # pylint: disable=broad-exception-caught  # stale rule may not exist; must not abort the fixer
                    pass

            # Generate new MAC-based udev rules from existing network config
            udev_result = inject_persistent_net_rules(g, self.logger, dry_run=self.dry_run)
            if udev_result.get("injected"):
                self.logger.info(
                    "Injected %d MAC-based udev rules for persistent interface naming",
                    len(udev_result.get("mappings", [])),
                )

        # Phase 2: Topology building
        topo = self.topology.build_topology(configs)
        self.logger.debug(
            "Topology: %d nodes, %d edges, %d warnings", len(topo.nodes), len(topo.edges), len(topo.warnings)
        )

        # Phase 3: Interface rename planning (AGGRESSIVE mode only)
        rename_map = self.topology.compute_rename_map(topo)
        if rename_map:
            self.logger.info("Interface rename map (AGGRESSIVE): %s", rename_map)

        # Statistics tracking
        stats = {
            "total_files": len(configs),
            "files_modified": 0,
            "files_failed": 0,
            "backups_created": 0,
            "total_fixes_applied": 0,
            "dry_run": self.dry_run,
            "by_type": {},
            "details": [],
            "rename_map": rename_map,
            "topology": {
                "nodes": len(topo.nodes),
                "edges": len(topo.edges),
                "warnings": topo.warnings,
            },
        }

        # Phase 4-6: Apply fixes to each configuration file
        total = len(configs)
        for idx, config in enumerate(configs, start=1):
            if progress_callback:
                progress_callback(idx, total, f"Processing {config.path}")

            try:
                # Determine backend-specific fixer
                result = self._fix_config_by_type(config, topo, rename_map)

                # Track statistics
                type_key = config.type.value
                stats["by_type"].setdefault(type_key, 0)

                if result.applied_fixes:
                    # Validate and apply fix
                    success = self.apply_fix(g, config, result)

                    if success:
                        stats["files_modified"] += 1
                        stats["total_fixes_applied"] += len(result.applied_fixes)
                        stats["by_type"][type_key] += 1
                        if result.backup_created:
                            stats["backups_created"] += 1

                        # Record details
                        stats["details"].append(
                            {
                                "path": config.path,
                                "type": type_key,
                                "modified": True,
                                "fixes": result.applied_fixes,
                                "new_hash": self.discovery.calculate_hash(result.new_content),
                            }
                        )

                        self.logger.info(
                            "✓ Fixed %s (%s) - %d fixes applied",
                            config.path,
                            type_key,
                            len(result.applied_fixes),
                        )
                    else:
                        stats["files_failed"] += 1
                        stats["details"].append(
                            {
                                "path": config.path,
                                "type": type_key,
                                "modified": False,
                                "error": "apply_fix failed",
                            }
                        )
                        self.logger.warning(
                            "✗ Failed to apply network fixes to %s — validation rejected the changes "
                            "(the original config was preserved). Check the fix details in the report "
                            "and manually review the network config after boot.",
                            config.path,
                        )
                else:
                    # No fixes needed
                    stats["details"].append(
                        {"path": config.path, "type": type_key, "modified": False, "fixes": []}
                    )
                    self.logger.debug("No fixes needed for %s", config.path)

            except Exception as e:  # pylint: disable=broad-exception-caught  # one config's failure must not abort the fixer run
                stats["files_failed"] += 1
                stats["details"].append(
                    {"path": config.path, "type": config.type.value, "modified": False, "error": str(e)}
                )
                self.logger.exception("Error processing %s: %s", config.path, e)

        # Phase 7: Generate summary
        warnings = topo.warnings.copy()
        recommendations = self.generate_recommendations(stats)

        self.logger.info(
            "Network fixes complete: %d/%d files modified, %d failed",
            stats["files_modified"],
            stats["total_files"],
            stats["files_failed"],
        )

        return {"stats": stats, "warnings": warnings, "recommendations": recommendations}

    def _fix_config_by_type(  # pylint: disable=too-many-return-statements  # one branch per network config backend type
        self,
        config: NetworkConfig,
        topo,
        rename_map: dict[str, str],
    ) -> FixResult:
        """
        Route config to appropriate backend-specific fixer.

        Args:
            config: Network configuration to fix
            topo: Topology graph
            rename_map: Interface rename map

        Returns:
            FixResult with applied fixes
        """
        if config.type in (NetworkConfigType.IFCFG_RH, NetworkConfigType.WICKED_IFCFG):
            return self.backend.fix_ifcfg_rh(config, topo=topo, rename_map=rename_map)
        if config.type == NetworkConfigType.NETPLAN:
            return self.backend.fix_netplan(config, topo=topo, rename_map=rename_map)
        if config.type == NetworkConfigType.INTERFACES:
            return self.backend.fix_interfaces(config)
        if config.type == NetworkConfigType.SYSTEMD_NETWORK:
            return self.backend.fix_systemd_network(config, rename_map=rename_map)
        if config.type == NetworkConfigType.SYSTEMD_NETDEV:
            # netdev files (.netdev) define virtual devices — no fixes needed
            return FixResult(config=config, new_content=config.content, applied_fixes=[])
        if config.type == NetworkConfigType.NETWORK_MANAGER:
            return self.backend.fix_network_manager(config, rename_map=rename_map)
        if config.type == NetworkConfigType.WICKED:
            return self.backend.fix_wicked_xml(config)
        return FixResult(config=config, new_content=config.content, applied_fixes=[])

    # Fix application and validation

    def apply_fix(
        self,
        g: guestfs.GuestFS,
        config: NetworkConfig,
        result: FixResult,
    ) -> bool:
        """
        Apply fix to disk with validation and backup.

        Args:
            g: GuestFS handle
            config: Original network configuration
            result: Fix result from backend fixer

        Returns:
            True if successfully applied, False otherwise
        """
        # Validate fix didn't corrupt configuration
        validation_errors = self.validation.validate_fix(
            original=config.content,
            fixed=result.new_content,
            config_type=config.type,
        )

        if validation_errors:
            self.logger.error(
                "Network config validation failed for %s: %s. "
                "The proposed fix would corrupt the config file. "
                "The original file is preserved unchanged.",
                config.path,
                validation_errors,
            )
            return False

        # Dry run mode - don't write
        if self.dry_run:
            self.logger.debug("Dry-run: would write %s", config.path)
            return True

        # Never modify vendor-shipped files (package-managed, would be
        # clobbered by updates).  They're discovered for topology building
        # but fixes should go to /etc/ overrides instead.
        vendor_prefixes = ("/usr/lib/", "/lib/", "/run/")
        if any(config.path.startswith(p) for p in vendor_prefixes):
            self.logger.debug("Skipping vendor file (read-only): %s", config.path)
            return True

        try:
            # Create backup before modifying
            backup_path = self.discovery.create_backup(
                g,
                config.path,
                config.content,
                suffix=self.backup_suffix,
            )

            if backup_path:
                result.backup_created = True
                self.logger.debug("Created backup: %s", backup_path)

            # Write fixed content with proper mode preservation
            prefer_mode = 0o600 if config.type == NetworkConfigType.NETWORK_MANAGER else None
            self.discovery.write_with_mode(
                g,
                config.path,
                result.new_content,
                prefer_mode=prefer_mode,
            )

            return True

        except Exception as e:  # pylint: disable=broad-exception-caught  # write failure must trigger backup restore below, not crash
            self.logger.exception(
                "Failed to write network config fix to %s: %s. "
                "The original file was preserved (backup at %s*). "
                "After boot, manually review network configuration.",
                config.path,
                e,
                config.path,
            )

            # Attempt to restore from backup
            if result.backup_created and backup_path:
                try:
                    backup_content = g.read_file(backup_path).decode("utf-8", errors="replace")
                    g.write(config.path, backup_content.encode("utf-8"))
                    self.logger.info("Restored %s from backup after failure", config.path)
                except Exception as restore_err:  # pylint: disable=broad-exception-caught  # best-effort restore, must not mask the original failure
                    self.logger.exception("Failed to restore backup for %s: %s", config.path, restore_err)

            return False

    # Summary and recommendations

    def generate_recommendations(self, stats: dict[str, Any]) -> list[str]:
        """
        Generate user-facing recommendations based on fix results.

        Args:
            stats: Statistics from fix operation

        Returns:
            List of recommendation strings
        """
        recommendations: list[str] = []

        if stats.get("dry_run"):
            recommendations.append(
                "Dry-run enabled: no files were written. Review details and rerun with dry_run=False."
            )

        if stats.get("rename_map"):
            recommendations.append(
                "Aggressive interface renaming was computed. Ensure your libvirt domain XML uses virtio-net and "
                "verify the guest sees the expected interface name(s) after boot."
            )

        if stats["files_modified"] > 0:
            recommendations.append(
                f"Modified {stats['files_modified']} network configuration files. Review changes and test after boot."
            )
            if stats["total_fixes_applied"] > 0:
                recommendations.append(
                    f"Applied {stats['total_fixes_applied']} fixes (MAC pinning removal, VMware token "
                    "cleanup, topology-aware DHCP, rename propagation)."
                )
            if stats["backups_created"] > 0:
                recommendations.append(
                    f"Created {stats['backups_created']} backup file(s) with suffix '{self.backup_suffix}' "
                    "(NetworkManager backups get an extra '.bak')."
                )

        if stats["files_failed"] > 0:
            recommendations.append(
                f"Failed to process {stats['files_failed']} files. Manual network config may be required."
            )

        topo = stats.get("topology") or {}
        if topo.get("warnings"):
            recommendations.append(
                "Topology warnings detected. Review 'stats.warnings' and confirm bond/bridge/vlan intent."
            )

        # Backend-specific recommendations
        if "ifcfg-rh" in stats["by_type"] or "wicked-ifcfg" in stats["by_type"]:
            recommendations.append(
                "ifcfg-based system detected. After boot, restart network service (or reboot)."
            )

        if "netplan" in stats["by_type"]:
            recommendations.append("Netplan detected. After boot, run 'netplan apply' (or reboot).")

        if "systemd-network" in stats["by_type"]:
            recommendations.append(
                "systemd-networkd detected. After boot, restart systemd-networkd (or reboot)."
            )

        if "network-manager" in stats["by_type"]:
            recommendations.append(
                "NetworkManager profiles detected. After boot, toggle networking or reboot."
            )

        if stats["total_fixes_applied"] == 0 and stats["files_modified"] == 0:
            recommendations.append(
                "No network configuration changes were needed. The existing config looks KVM-safe."
            )

        return recommendations


__all__ = ["NetworkFixer"]
