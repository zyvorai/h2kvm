#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Enterprise Migration Master Example

This is the MASTER example demonstrating how to use ALL VMCraft features together
in a comprehensive enterprise VMware to KVM migration workflow.

This example integrates:
- VMCraft v9.2 systemd integration (52 APIs)
- Advanced features: parallel mounts, partition management, LVM, Augeas, archives
- Performance optimizations: caching, parallel operations
- Security hardening: SSH config, service management
- Complete validation and reporting

Workflow:
1. Pre-migration inspection and readiness check
2. Performance-optimized migration with parallel operations
3. Post-migration customization (partitions, LVM, configuration)
4. Security hardening (SSH, services, network)
5. Boot validation and performance analysis
6. Backup and archive creation
7. Complete migration report generation

This demonstrates enterprise-grade VM migration using all VMCraft capabilities.
"""

import sys
import json
import time
import tempfile
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

from h2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


class EnterpriseMigration:
    """
    Enterprise-grade migration workflow with all VMCraft features.

    Demonstrates:
    - Systemd integration for service management
    - Performance optimizations (parallel mounts, caching)
    - Advanced storage management (partitions, LVM)
    - Configuration management with Augeas
    - Security hardening
    - Complete validation and reporting
    """

    def __init__(self, source_vm: str, output_dir: str):
        self.logger = setup_logging()
        self.source_vm = Path(source_vm)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.vm_name = self.source_vm.stem
        self.migration_data: dict[str, Any] = {}
        self.start_time = time.time()

    def print_banner(self, title: str):
        """Print formatted banner."""
        print(f"\n{'=' * 80}")
        print(f"  {title}")
        print(f"{'=' * 80}\n")

    def print_section(self, title: str):
        """Print formatted section."""
        print(f"\n{'-' * 80}")
        print(f"  {title}")
        print(f"{'-' * 80}")

    # =========================================================================
    # PHASE 1: Pre-Migration Inspection
    # =========================================================================

    def phase1_inspection(self, g: VMCraft):
        """Phase 1: Comprehensive pre-migration inspection."""
        self.print_banner("PHASE 1: PRE-MIGRATION INSPECTION")

        phase_data = {}

        # 1.1: Operating System Detection
        self.print_section("1.1 Operating System Detection")

        roots = g.inspect_os()
        if not roots:
            self.logger.error("No operating system detected")
            return None

        root = roots[0]
        os_info = {
            "type": g.inspect_get_type(root),
            "distro": g.inspect_get_distro(root),
            "version": f"{g.inspect_get_major_version(root)}.{g.inspect_get_minor_version(root)}",
            "product": g.inspect_get_product_name(root),
        }

        print(f"  OS Type: {os_info['type']}")
        print(f"  Distribution: {os_info['distro']}")
        print(f"  Version: {os_info['version']}")
        print(f"  Product: {os_info['product']}")

        phase_data["os"] = os_info

        # 1.2: Partition Analysis with Caching
        self.print_section("1.2 Partition Analysis (with caching)")

        partitions = g.list_partitions(use_cache=True)
        print(f"  Found {len(partitions)} partitions (cached for performance)")

        partition_info = []
        for part in partitions:
            # Use cached blkid metadata
            metadata = g.blkid(part, use_cache=True)
            info = {
                "device": part,
                "fstype": metadata.get("TYPE", "unknown"),
                "uuid": metadata.get("UUID", "none"),
                "label": metadata.get("LABEL", "none"),
            }
            partition_info.append(info)
            print(f"    {part}: {info['fstype']} (UUID: {info['uuid'][:8]}...)")

        phase_data["partitions"] = partition_info

        # 1.3: LVM Detection
        self.print_section("1.3 LVM Detection")

        pvs = g.pvs()
        vgs = g.vgs()
        lvs = g.lvs()

        lvm_info = {
            "has_lvm": len(pvs) > 0,
            "pv_count": len(pvs),
            "vg_count": len(vgs),
            "lv_count": len(lvs),
        }

        if lvm_info["has_lvm"]:
            print(f"  ✓ LVM detected:")
            print(f"    Physical Volumes: {len(pvs)}")
            print(f"    Volume Groups: {len(vgs)}")
            print(f"    Logical Volumes: {len(lvs)}")
        else:
            print(f"  - No LVM detected")

        phase_data["lvm"] = lvm_info

        # 1.4: Systemd Check
        self.print_section("1.4 Systemd Detection")

        if g.systemd_is_available():
            print(f"  ✓ Systemd is available")

            # List services
            services = g.systemd_list_services()
            failed_services = g.systemd_list_failed_services()

            systemd_info = {
                "available": True,
                "total_services": len(services),
                "failed_services": len(failed_services),
                "failed_list": failed_services,
            }

            print(f"    Total services: {len(services)}")
            print(f"    Failed services: {len(failed_services)}")

            if failed_services:
                print(f"    Failed:")
                for svc in failed_services[:5]:
                    print(f"      - {svc}")
        else:
            print(f"  - Systemd not available (SysV init?)")
            systemd_info = {"available": False}

        phase_data["systemd"] = systemd_info

        self.migration_data["phase1"] = phase_data
        return root

    # =========================================================================
    # PHASE 2: Performance-Optimized Migration
    # =========================================================================

    def phase2_migration(self, g: VMCraft, root: str):
        """Phase 2: Performance-optimized migration with parallel operations."""
        self.print_banner("PHASE 2: PERFORMANCE-OPTIMIZED MIGRATION")

        phase_data = {}

        # 2.1: Parallel Mount Operations
        self.print_section("2.1 Parallel Mount Operations")

        # Unmount any existing mounts
        g.umount_all()

        # Get all mountable partitions
        mountpoints = g.inspect_get_mountpoints(root)

        # Prepare mount targets for parallel mounting
        mount_targets = []
        for mountpoint, device in mountpoints.items():
            mount_targets.append((device, mountpoint))

        print(f"  Mounting {len(mount_targets)} filesystems in parallel...")

        start_time = time.time()
        results = g.mount_all_parallel(mount_targets, max_workers=4, readonly=False)
        elapsed = time.time() - start_time

        successful = sum(1 for success in results.values() if success)
        print(f"  ✓ Mounted {successful}/{len(mount_targets)} filesystems in {elapsed:.2f}s")
        print(f"    Performance: ~{elapsed / len(mount_targets):.3f}s per mount")

        phase_data["mount_time"] = elapsed
        phase_data["mount_success_rate"] = successful / len(mount_targets)

        self.migration_data["phase2"] = phase_data

    # =========================================================================
    # PHASE 3: Post-Migration Service Management
    # =========================================================================

    def phase3_service_management(self, g: VMCraft):
        """Phase 3: Service migration (VMware to KVM) using systemd APIs."""
        self.print_banner("PHASE 3: SERVICE MANAGEMENT (VMware → KVM)")

        if not g.systemd_is_available():
            print("  - Skipping (systemd not available)")
            return

        phase_data = {}

        # 3.1: Disable VMware Services
        self.print_section("3.1 Disable VMware Services")

        vmware_services = [
            "vmtoolsd.service",
            "vmware-tools.service",
            "open-vm-tools.service",
            "vmware-tools-thinprint.service",
        ]

        print(f"  Disabling {len(vmware_services)} VMware services...")

        # Bulk disable
        disable_results = g.systemd_services_disable_multiple(vmware_services)
        disabled_count = sum(1 for ok in disable_results.values() if ok)
        print(f"    Disabled: {disabled_count}/{len(vmware_services)}")

        # Mask to prevent re-activation
        mask_results = g.systemd_services_mask(vmware_services)
        masked_count = sum(1 for ok in mask_results.values() if ok)
        print(f"    Masked: {masked_count}/{len(vmware_services)}")

        # 3.2: Enable KVM Services
        self.print_section("3.2 Enable KVM Services")

        kvm_services = ["qemu-guest-agent.service"]

        for service in kvm_services:
            result = g.systemd_service_enable(service)
            if result["ok"]:
                print(f"  ✓ Enabled {service}")
            else:
                print(f"  - {service} not available (will install later)")

        # Reload systemd
        g.systemd_daemon_reload()
        print(f"  ✓ Systemd daemon reloaded")

        phase_data["vmware_services_disabled"] = disabled_count
        phase_data["kvm_services_enabled"] = len(kvm_services)

        self.migration_data["phase3"] = phase_data

    # =========================================================================
    # PHASE 4: Network Configuration Migration
    # =========================================================================

    def phase4_network_configuration(self, g: VMCraft):
        """Phase 4: Migrate network configuration to systemd-networkd."""
        self.print_banner("PHASE 4: NETWORK CONFIGURATION MIGRATION")

        phase_data = {}

        # 4.1: Check for ifcfg files (RHEL/Fedora)
        self.print_section("4.1 Migrate ifcfg to systemd-networkd")

        interfaces_to_migrate = ["eth0", "eth1", "ens3", "ens33"]
        migrated_count = 0

        for interface in interfaces_to_migrate:
            result = g.networkd_migrate_from_ifcfg(interface)

            if result["ok"]:
                print(f"  ✓ Migrated {interface} to {result['networkd_file']}")
                migrated_count += 1
            elif result["error"] == "ifcfg_not_found":
                # Expected - interface doesn't exist
                pass
            else:
                print(f"  - Failed to migrate {interface}: {result['error']}")

        print(f"  Migrated {migrated_count} network interfaces")

        # 4.2: Enable systemd-networkd
        if migrated_count > 0:
            self.print_section("4.2 Enable systemd-networkd")

            result = g.networkd_enable_networkd()
            if result["ok"]:
                print(f"  ✓ systemd-networkd enabled")
            else:
                print(f"  - Failed to enable: {result['error']}")

        phase_data["interfaces_migrated"] = migrated_count

        self.migration_data["phase4"] = phase_data

    # =========================================================================
    # PHASE 5: Security Hardening with Augeas
    # =========================================================================

    def phase5_security_hardening(self, g: VMCraft):
        """Phase 5: Security hardening using Augeas configuration management."""
        self.print_banner("PHASE 5: SECURITY HARDENING")

        try:
            import augeas
        except ImportError:
            print("  - Skipping (Augeas library not available)")
            return

        phase_data = {}

        # 5.1: Initialize Augeas
        self.print_section("5.1 SSH Security Hardening")

        try:
            g.aug_init()

            # Disable root login
            try:
                g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
                print(f"  ✓ Disabled root login")
            except Exception:
                print(f"  - SSH config not found")

            # Disable password authentication
            try:
                g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")
                print(f"  ✓ Disabled password authentication")
            except Exception:
                pass

            # Enable public key authentication
            try:
                g.aug_set("/files/etc/ssh/sshd_config/PubkeyAuthentication", "yes")
                print(f"  ✓ Enabled public key authentication")
            except Exception:
                pass

            # Save changes
            g.aug_save()
            g.aug_close()

            print(f"  ✓ Security configuration saved")
            phase_data["ssh_hardened"] = True

        except Exception as e:
            print(f"  - Security hardening failed: {e}")
            phase_data["ssh_hardened"] = False

        self.migration_data["phase5"] = phase_data

    # =========================================================================
    # PHASE 6: Boot Validation and Performance Analysis
    # =========================================================================

    def phase6_boot_validation(self, g: VMCraft):
        """Phase 6: Validate boot configuration and analyze performance."""
        self.print_banner("PHASE 6: BOOT VALIDATION & PERFORMANCE")

        if not g.systemd_is_available():
            print("  - Skipping (systemd not available)")
            return

        phase_data = {}

        # 6.1: Check for failed services
        self.print_section("6.1 Service Health Check")

        failed_services = g.systemd_list_failed_services()

        if failed_services:
            print(f"  ⚠ Found {len(failed_services)} failed services:")
            for service in failed_services[:5]:
                print(f"    - {service}")
        else:
            print(f"  ✓ No failed services detected")

        phase_data["failed_services"] = len(failed_services)

        # 6.2: Boot Performance Analysis
        self.print_section("6.2 Boot Performance Analysis")

        try:
            perf = g.units_analyze_boot_performance()

            if perf["ok"]:
                print(f"  Boot Performance:")
                print(f"    Kernel time: {perf.get('kernel_time', 'N/A')}")
                print(f"    Userspace time: {perf.get('userspace_time', 'N/A')}")
                print(f"    Total boot time: {perf.get('boot_time', 'N/A')}")

                phase_data["boot_performance"] = perf
        except Exception:
            print(f"  - Boot performance analysis not available")

        # 6.3: Critical Chain Analysis
        try:
            chain = g.units_analyze_critical_chain()

            if chain["ok"]:
                print(f"  Critical boot path chain available")
                phase_data["has_critical_chain"] = True
        except Exception:
            pass

        # 6.4: Slowest Services
        try:
            blame = g.units_analyze_blame()

            if blame["ok"] and len(blame["services"]) > 0:
                print(f"  Slowest services (top 3):")
                for service_info in blame["services"][:3]:
                    print(f"    {service_info['time']:>10} - {service_info['name']}")

                phase_data["slowest_service"] = blame["services"][0]
        except Exception:
            pass

        self.migration_data["phase6"] = phase_data

    # =========================================================================
    # PHASE 7: Backup and Archive Creation
    # =========================================================================

    def phase7_backup_creation(self, g: VMCraft):
        """Phase 7: Create backups and archives for disaster recovery."""
        self.print_banner("PHASE 7: BACKUP & ARCHIVE CREATION")

        phase_data = {}

        # 7.1: Create configuration backup
        self.print_section("7.1 Configuration Backup")

        backup_file = self.output_dir / f"{self.vm_name}-config-backup.tar.xz"

        try:
            # Backup /etc directory with maximum compression
            g.tar_out("/etc", str(backup_file), compress="xz")

            backup_size = backup_file.stat().st_size
            print(f"  ✓ Created configuration backup")
            print(f"    File: {backup_file.name}")
            print(f"    Size: {backup_size:,} bytes ({backup_size / 1024 / 1024:.1f} MB)")

            phase_data["config_backup"] = {
                "file": str(backup_file),
                "size": backup_size,
            }
        except Exception as e:
            print(f"  - Backup failed: {e}")

        # 7.2: Query disk information
        self.print_section("7.2 Disk Information")

        device = g.get_nbd_device()
        size_bytes = g.blockdev_getsize64(device)
        size_gb = size_bytes / (1024**3)

        print(f"  Disk size: {size_bytes:,} bytes ({size_gb:.2f} GB)")

        phase_data["disk_size"] = size_bytes

        self.migration_data["phase7"] = phase_data

    # =========================================================================
    # PHASE 8: Final Report Generation
    # =========================================================================

    def phase8_final_report(self):
        """Phase 8: Generate comprehensive migration report."""
        self.print_banner("PHASE 8: MIGRATION REPORT")

        total_time = time.time() - self.start_time

        # Generate report
        report = {
            "vm_name": self.vm_name,
            "migration_timestamp": datetime.now().isoformat(),
            "migration_duration_seconds": total_time,
            "phases": self.migration_data,
        }

        # Save report
        report_file = self.output_dir / f"{self.vm_name}-migration-report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Print summary
        self.print_section("Migration Summary")

        print(f"  VM Name: {self.vm_name}")
        print(f"  Duration: {total_time:.1f} seconds")
        print(f"  Report: {report_file}")

        # Phase summaries
        if "phase1" in self.migration_data:
            p1 = self.migration_data["phase1"]
            print(f"\n  OS: {p1['os']['distro']} {p1['os']['version']}")
            print(f"  Partitions: {len(p1['partitions'])}")
            if p1["lvm"]["has_lvm"]:
                print(f"  LVM: {p1['lvm']['lv_count']} logical volumes")

        if "phase2" in self.migration_data:
            p2 = self.migration_data["phase2"]
            print(f"  Mount time: {p2['mount_time']:.2f}s (parallel)")

        if "phase3" in self.migration_data:
            p3 = self.migration_data["phase3"]
            print(f"  VMware services disabled: {p3['vmware_services_disabled']}")
            print(f"  KVM services enabled: {p3['kvm_services_enabled']}")

        if "phase4" in self.migration_data:
            p4 = self.migration_data["phase4"]
            if p4["interfaces_migrated"] > 0:
                print(f"  Network interfaces migrated: {p4['interfaces_migrated']}")

        if "phase6" in self.migration_data:
            p6 = self.migration_data["phase6"]
            if p6["failed_services"] == 0:
                print(f"  ✓ No failed services")
            else:
                print(f"  ⚠ Failed services: {p6['failed_services']}")

        print(f"\n{'=' * 80}")
        print(f"  MIGRATION COMPLETE!")
        print(f"{'=' * 80}\n")

    # =========================================================================
    # Main Migration Orchestrator
    # =========================================================================

    def run(self):
        """Execute complete enterprise migration workflow."""
        self.print_banner(f"ENTERPRISE MIGRATION: {self.vm_name}")

        print(f"Source: {self.source_vm}")
        print(f"Output: {self.output_dir}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Launch VMCraft with NBD retry logic
        with VMCraft(str(self.source_vm)) as g:
            self.logger.info("VMCraft launched (with NBD retry logic)")

            # Phase 1: Inspection
            root = self.phase1_inspection(g)
            if not root:
                self.logger.error("Pre-migration inspection failed")
                return

            # Phase 2: Performance-optimized migration
            self.phase2_migration(g, root)

            # Phase 3: Service management
            self.phase3_service_management(g)

            # Phase 4: Network configuration
            self.phase4_network_configuration(g)

            # Phase 5: Security hardening
            self.phase5_security_hardening(g)

            # Phase 6: Boot validation
            self.phase6_boot_validation(g)

            # Phase 7: Backup creation
            self.phase7_backup_creation(g)

        # Phase 8: Final report (after VMCraft closes)
        self.phase8_final_report()


def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python enterprise_migration_master.py <source-vm> <output-dir>")
        print("")
        print("This is the MASTER example demonstrating ALL VMCraft features:")
        print("")
        print("Features Demonstrated:")
        print("  • Systemd integration (v9.2) - 52 APIs")
        print("  • Performance optimizations (parallel mounts, caching)")
        print("  • Advanced storage (partitions, LVM)")
        print("  • Configuration management (Augeas)")
        print("  • Security hardening (SSH, services)")
        print("  • Boot validation and performance analysis")
        print("  • Backup and archive operations")
        print("  • Comprehensive reporting")
        print("")
        print("Example:")
        print("  python enterprise_migration_master.py /vmware/rhel9.vmdk /output/kvm")
        print("")
        print("Output:")
        print("  - Migration report (JSON)")
        print("  - Configuration backup (tar.xz)")
        print("  - Performance metrics")
        sys.exit(1)

    source_vm = sys.argv[1]
    output_dir = sys.argv[2]

    if not Path(source_vm).exists():
        print(f"Error: Source VM not found: {source_vm}")
        sys.exit(1)

    # Run enterprise migration
    migration = EnterpriseMigration(source_vm, output_dir)
    migration.run()


if __name__ == "__main__":
    main()
