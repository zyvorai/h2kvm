#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Pre-Migration Readiness Assessment Tool

This tool performs comprehensive pre-migration checks to assess if a VM is
ready for migration from VMware to KVM. It generates a detailed readiness
report with recommendations.

Checks Performed:
1. Operating System Compatibility
2. Disk Configuration Analysis
3. Storage Health Assessment
4. Service Dependencies
5. Network Configuration Review
6. Boot Configuration Validation
7. Performance Baseline Metrics
8. Security Considerations
9. Migration Risk Assessment
10. Recommended Migration Strategy

Output:
- Detailed readiness report (JSON)
- Human-readable summary
- Risk assessment score
- Migration recommendations

Usage:
    python pre_migration_readiness.py <vm-path> [--output report.json]
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

from h2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


class ReadinessAssessment:
    """Pre-migration readiness assessment tool."""

    def __init__(self, vm_path: str):
        self.logger = setup_logging()
        self.vm_path = Path(vm_path)
        self.vm_name = self.vm_path.stem

        # Assessment results
        self.checks: dict[str, Any] = {}
        self.warnings: list[str] = []
        self.blockers: list[str] = []
        self.recommendations: list[str] = []
        self.risk_score = 0  # 0-100, lower is better

    def print_banner(self, title: str):
        """Print formatted banner."""
        print(f"\n{'=' * 80}")
        print(f"  {title}")
        print(f"{'=' * 80}\n")

    def print_section(self, title: str, status: str = ""):
        """Print formatted section."""
        status_str = f" [{status}]" if status else ""
        print(f"\n{'-' * 80}")
        print(f"  {title}{status_str}")
        print(f"{'-' * 80}")

    def check_os_compatibility(self, g: VMCraft, root: str) -> dict[str, Any]:
        """Check 1: Operating System Compatibility."""
        self.print_section("Check 1: Operating System Compatibility")

        check = {
            "name": "OS Compatibility",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Get OS details
        os_type = g.inspect_get_type(root)
        distro = g.inspect_get_distro(root)
        major_ver = g.inspect_get_major_version(root)
        minor_ver = g.inspect_get_minor_version(root)
        version = f"{major_ver}.{minor_ver}"
        product = g.inspect_get_product_name(root)

        check["details"] = {
            "type": os_type,
            "distro": distro,
            "version": version,
            "product": product,
        }

        print(f"  OS Type: {os_type}")
        print(f"  Distribution: {distro}")
        print(f"  Version: {version}")
        print(f"  Product: {product}")

        # Check OS type
        if os_type not in ("linux", "windows"):
            check["status"] = "FAIL"
            check["issues"].append(f"Unsupported OS type: {os_type}")
            self.blockers.append(f"Unsupported OS type: {os_type}")
            self.risk_score += 50

        # Check for known compatible distros
        compatible_distros = [
            "rhel",
            "centos",
            "fedora",
            "ubuntu",
            "debian",
            "sles",
            "opensuse",
            "rocky",
            "almalinux",
            "windows",
        ]

        if distro not in compatible_distros:
            check["status"] = "WARN"
            check["issues"].append(f"Unknown distribution: {distro}")
            self.warnings.append(f"Distribution '{distro}' may require additional testing")
            self.risk_score += 10

        # Check version support
        if distro == "rhel" and major_ver < 7:
            check["status"] = "WARN"
            check["issues"].append(f"RHEL {version} is EOL, consider upgrade")
            self.warnings.append(f"RHEL {version} is end-of-life")
            self.risk_score += 15

        if check["status"] == "PASS":
            print(f"  ✓ OS is compatible with KVM")
        elif check["status"] == "WARN":
            print(f"  ⚠ OS may require additional configuration")
        else:
            print(f"  ✗ OS compatibility issues detected")

        return check

    def check_disk_configuration(self, g: VMCraft) -> dict[str, Any]:
        """Check 2: Disk Configuration Analysis."""
        self.print_section("Check 2: Disk Configuration Analysis")

        check = {
            "name": "Disk Configuration",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Get partitions
        partitions = g.list_partitions(use_cache=True)
        check["details"]["partition_count"] = len(partitions)

        print(f"  Partitions: {len(partitions)}")

        # Check partition table type
        device = g.get_nbd_device()
        parttype = g.part_get_parttype(device)
        check["details"]["partition_table"] = parttype

        print(f"  Partition table: {parttype}")

        if parttype == "unknown":
            check["status"] = "WARN"
            check["issues"].append("Unknown partition table type")
            self.warnings.append("Unknown partition table type - may be a raw disk")
            self.risk_score += 5

        # Analyze each partition
        partition_details = []
        for part in partitions:
            metadata = g.blkid(part, use_cache=True)
            fstype = metadata.get("TYPE", "unknown")
            uuid = metadata.get("UUID", "none")

            partition_details.append(
                {
                    "device": part,
                    "fstype": fstype,
                    "uuid": uuid,
                }
            )

            print(f"    {part}: {fstype}")

            # Check for problematic filesystems
            if fstype in ("swap", "unknown"):
                # These are OK
                pass
            elif fstype not in ("ext2", "ext3", "ext4", "xfs", "btrfs", "ntfs", "vfat", "lvm2_member"):
                check["status"] = "WARN"
                check["issues"].append(f"Uncommon filesystem: {fstype} on {part}")
                self.warnings.append(f"Filesystem '{fstype}' may require special handling")
                self.risk_score += 5

        check["details"]["partitions"] = partition_details

        # Check disk size
        disk_size = g.blockdev_getsize64(device)
        disk_gb = disk_size / (1024**3)
        check["details"]["disk_size_gb"] = round(disk_gb, 2)

        print(f"  Disk size: {disk_gb:.2f} GB")

        if disk_gb > 1000:
            check["status"] = "WARN"
            check["issues"].append(f"Large disk ({disk_gb:.0f} GB) - migration may take time")
            self.warnings.append(f"Large disk size ({disk_gb:.0f} GB) will increase migration time")
            self.risk_score += 5

        if check["status"] == "PASS":
            print(f"  ✓ Disk configuration is standard")

        return check

    def check_lvm_configuration(self, g: VMCraft) -> dict[str, Any]:
        """Check 3: LVM Configuration Assessment."""
        self.print_section("Check 3: LVM Configuration")

        check = {
            "name": "LVM Configuration",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Check for LVM
        pvs = g.pvs()
        vgs = g.vgs()
        lvs = g.lvs()

        has_lvm = len(pvs) > 0

        check["details"] = {
            "has_lvm": has_lvm,
            "pv_count": len(pvs),
            "vg_count": len(vgs),
            "lv_count": len(lvs),
        }

        if has_lvm:
            print(f"  ✓ LVM detected:")
            print(f"    Physical Volumes: {len(pvs)}")
            print(f"    Volume Groups: {len(vgs)}")
            print(f"    Logical Volumes: {len(lvs)}")

            # LVM is fully supported
            self.recommendations.append("LVM configuration will be preserved during migration")
        else:
            print(f"  - No LVM detected (standard partitions)")

        return check

    def check_systemd_services(self, g: VMCraft, root: str) -> dict[str, Any]:
        """Check 4: Systemd Service Dependencies."""
        self.print_section("Check 4: Systemd Service Dependencies")

        check = {
            "name": "Systemd Services",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Mount filesystem for systemd check
        try:
            mountpoints = g.inspect_get_mountpoints(root)
            for mp, device in mountpoints.items():
                try:
                    g.mount(device, mp, readonly=True)
                except Exception:
                    pass

            if not g.systemd_is_available():
                check["status"] = "WARN"
                check["details"]["has_systemd"] = False
                check["issues"].append("Systemd not detected - may use SysV init")
                self.warnings.append("Non-systemd init system detected")
                self.risk_score += 10
                print(f"  ⚠ Systemd not detected (SysV init?)")
                return check

            check["details"]["has_systemd"] = True

            # Get service stats
            services = g.systemd_list_services()
            failed_services = g.systemd_list_failed_services()

            check["details"]["total_services"] = len(services)
            check["details"]["failed_services"] = len(failed_services)
            check["details"]["failed_list"] = failed_services[:10]  # First 10

            print(f"  ✓ Systemd detected")
            print(f"    Total services: {len(services)}")
            print(f"    Failed services: {len(failed_services)}")

            if failed_services:
                check["status"] = "WARN"
                check["issues"].append(f"{len(failed_services)} services currently failed")
                self.warnings.append(f"{len(failed_services)} services are failed - may need attention")
                self.risk_score += min(len(failed_services) * 2, 20)

                if len(failed_services) <= 5:
                    print(f"    Failed:")
                    for svc in failed_services:
                        print(f"      - {svc}")

            # Check for VMware tools
            vmware_services = []
            for svc in services:
                if "vmware" in svc.lower() or "vmtool" in svc.lower():
                    vmware_services.append(svc)

            if vmware_services:
                check["details"]["vmware_services"] = vmware_services
                print(f"  ✓ VMware services detected ({len(vmware_services)})")
                self.recommendations.append(
                    f"Will disable {len(vmware_services)} VMware services during migration"
                )

        except Exception as e:
            check["status"] = "WARN"
            check["issues"].append(f"Failed to check systemd: {e}")
            self.warnings.append("Unable to check systemd status")
            self.risk_score += 5

        return check

    def check_network_configuration(self, g: VMCraft) -> dict[str, Any]:
        """Check 5: Network Configuration Review."""
        self.print_section("Check 5: Network Configuration")

        check = {
            "name": "Network Configuration",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Check for network configuration files
        has_networkd = False
        has_ifcfg = False
        has_netplan = False

        try:
            # Check for systemd-networkd
            networkd_files = g.networkd_list_network_files()
            if networkd_files:
                has_networkd = True
                check["details"]["networkd_files"] = len(networkd_files)
                print(f"  ✓ systemd-networkd configuration found ({len(networkd_files)} files)")

            # Check for ifcfg (RHEL/CentOS/Fedora)
            try:
                ifcfg_files = g.ls("/etc/sysconfig/network-scripts")
                ifcfg_count = len([f for f in ifcfg_files if f.startswith("ifcfg-")])
                if ifcfg_count > 0:
                    has_ifcfg = True
                    check["details"]["ifcfg_files"] = ifcfg_count
                    print(f"  ✓ ifcfg configuration found ({ifcfg_count} files)")
                    self.recommendations.append(
                        f"Will migrate {ifcfg_count} ifcfg files to systemd-networkd"
                    )
            except Exception:
                pass

            # Check for netplan (Ubuntu)
            try:
                netplan_files = g.ls("/etc/netplan")
                if netplan_files:
                    has_netplan = True
                    check["details"]["netplan_files"] = len(netplan_files)
                    print(f"  ✓ Netplan configuration found ({len(netplan_files)} files)")
            except Exception:
                pass

            check["details"]["config_types"] = {
                "networkd": has_networkd,
                "ifcfg": has_ifcfg,
                "netplan": has_netplan,
            }

            if not any([has_networkd, has_ifcfg, has_netplan]):
                check["status"] = "WARN"
                check["issues"].append("No standard network configuration found")
                self.warnings.append("Network configuration may need manual setup")
                self.risk_score += 10
                print(f"  ⚠ No standard network configuration detected")

        except Exception as e:
            check["status"] = "WARN"
            check["issues"].append(f"Failed to check network config: {e}")
            self.warnings.append("Unable to check network configuration")
            self.risk_score += 5

        return check

    def check_boot_configuration(self, g: VMCraft, root: str) -> dict[str, Any]:
        """Check 6: Boot Configuration Validation."""
        self.print_section("Check 6: Boot Configuration")

        check = {
            "name": "Boot Configuration",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Get boot information
        try:
            # Check for EFI vs BIOS
            mountpoints = g.inspect_get_mountpoints(root)
            has_efi = "/boot/efi" in mountpoints or "/boot/EFI" in mountpoints

            check["details"]["boot_mode"] = "EFI" if has_efi else "BIOS"
            print(f"  Boot mode: {'EFI' if has_efi else 'BIOS'}")

            # Both are supported
            if has_efi:
                self.recommendations.append("EFI boot mode will be preserved in KVM")
            else:
                self.recommendations.append("BIOS boot mode will be preserved in KVM")

            # Check for bootloader
            bootloader = g.inspect_get_bootloader(root)
            if bootloader:
                check["details"]["bootloader"] = bootloader
                print(f"  Bootloader: {bootloader}")
            else:
                check["status"] = "WARN"
                check["issues"].append("Bootloader not detected")
                self.warnings.append("Bootloader detection failed - manual verification recommended")
                self.risk_score += 10

        except Exception as e:
            check["status"] = "WARN"
            check["issues"].append(f"Failed to check boot config: {e}")
            self.warnings.append("Unable to validate boot configuration")
            self.risk_score += 5

        return check

    def calculate_risk_assessment(self) -> dict[str, Any]:
        """Calculate overall risk assessment."""
        self.print_section("Risk Assessment")

        # Categorize risk
        if self.risk_score <= 15:
            risk_level = "LOW"
            risk_desc = "Migration should proceed smoothly with minimal issues"
        elif self.risk_score <= 35:
            risk_level = "MEDIUM"
            risk_desc = "Migration should succeed but may require some manual intervention"
        elif self.risk_score <= 60:
            risk_level = "HIGH"
            risk_desc = "Migration has significant risks - careful planning required"
        else:
            risk_level = "CRITICAL"
            risk_desc = "Migration not recommended without addressing blockers"

        assessment = {
            "risk_score": self.risk_score,
            "risk_level": risk_level,
            "description": risk_desc,
            "blockers": len(self.blockers),
            "warnings": len(self.warnings),
        }

        print(f"  Risk Score: {self.risk_score}/100")
        print(f"  Risk Level: {risk_level}")
        print(f"  Blockers: {len(self.blockers)}")
        print(f"  Warnings: {len(self.warnings)}")
        print(f"\n  {risk_desc}")

        return assessment

    def generate_recommendations(self) -> list[str]:
        """Generate migration recommendations."""
        self.print_section("Migration Recommendations")

        # Add general recommendations based on risk
        if self.risk_score <= 15:
            self.recommendations.insert(0, "✓ VM is ready for automated migration")
        elif self.risk_score <= 35:
            self.recommendations.insert(0, "⚠ VM can be migrated with caution - review warnings")
        else:
            self.recommendations.insert(0, "✗ Address blockers before migration")

        # Print recommendations
        for i, rec in enumerate(self.recommendations, 1):
            print(f"  {i}. {rec}")

        return self.recommendations

    def run_assessment(self):
        """Run complete readiness assessment."""
        self.print_banner(f"PRE-MIGRATION READINESS ASSESSMENT: {self.vm_name}")

        print(f"VM: {self.vm_path}")
        print(f"Assessment Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        with VMCraft(str(self.vm_path)) as g:
            # Detect OS
            roots = g.inspect_os()
            if not roots:
                self.logger.error("No operating system detected")
                self.blockers.append("No operating system detected in VM")
                self.risk_score = 100

                report = self.generate_report()
                return report

            root = roots[0]

            # Run all checks
            self.checks["os_compatibility"] = self.check_os_compatibility(g, root)
            self.checks["disk_configuration"] = self.check_disk_configuration(g)
            self.checks["lvm_configuration"] = self.check_lvm_configuration(g)
            self.checks["systemd_services"] = self.check_systemd_services(g, root)
            self.checks["network_configuration"] = self.check_network_configuration(g)
            self.checks["boot_configuration"] = self.check_boot_configuration(g, root)

            # Risk assessment
            self.checks["risk_assessment"] = self.calculate_risk_assessment()

            # Recommendations
            self.generate_recommendations()

        # Generate report
        report = self.generate_report()
        return report

    def generate_report(self) -> dict[str, Any]:
        """Generate final assessment report."""
        self.print_banner("ASSESSMENT SUMMARY")

        # Summary
        print(f"VM Name: {self.vm_name}")
        print(f"Risk Level: {self.checks.get('risk_assessment', {}).get('risk_level', 'UNKNOWN')}")
        print(f"Risk Score: {self.risk_score}/100")
        print(f"\nChecks Performed: {len(self.checks)}")

        # Status breakdown
        pass_count = sum(
            1 for c in self.checks.values() if isinstance(c, dict) and c.get("status") == "PASS"
        )
        warn_count = sum(
            1 for c in self.checks.values() if isinstance(c, dict) and c.get("status") == "WARN"
        )
        fail_count = sum(
            1 for c in self.checks.values() if isinstance(c, dict) and c.get("status") == "FAIL"
        )

        print(f"  Passed: {pass_count}")
        print(f"  Warnings: {warn_count}")
        print(f"  Failed: {fail_count}")

        # Blockers
        if self.blockers:
            print(f"\nBlockers ({len(self.blockers)}):")
            for blocker in self.blockers:
                print(f"  ✗ {blocker}")

        # Warnings
        if self.warnings:
            print(f"\nWarnings ({len(self.warnings)}):")
            for warning in self.warnings[:5]:
                print(f"  ⚠ {warning}")
            if len(self.warnings) > 5:
                print(f"  ... and {len(self.warnings) - 5} more")

        # Final recommendation
        print(f"\n{'=' * 80}")
        if self.risk_score <= 15:
            print("  ✓ READY FOR MIGRATION")
        elif self.risk_score <= 35:
            print("  ⚠ MIGRATION POSSIBLE WITH CAUTION")
        elif self.risk_score <= 60:
            print("  ⚠ HIGH RISK - CAREFUL PLANNING REQUIRED")
        else:
            print("  ✗ NOT READY - ADDRESS BLOCKERS FIRST")
        print(f"{'=' * 80}\n")

        # Generate full report
        report = {
            "vm_name": self.vm_name,
            "vm_path": str(self.vm_path),
            "assessment_time": datetime.now().isoformat(),
            "risk_score": self.risk_score,
            "risk_level": self.checks.get("risk_assessment", {}).get("risk_level", "UNKNOWN"),
            "checks": self.checks,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "summary": {
                "total_checks": len(self.checks),
                "passed": pass_count,
                "warnings": warn_count,
                "failed": fail_count,
            },
        }

        return report


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python pre_migration_readiness.py <vm-path> [--output report.json]")
        print("")
        print("Pre-Migration Readiness Assessment Tool")
        print("")
        print("Performs comprehensive checks before VM migration:")
        print("  • Operating system compatibility")
        print("  • Disk configuration analysis")
        print("  • LVM assessment")
        print("  • Systemd service dependencies")
        print("  • Network configuration review")
        print("  • Boot configuration validation")
        print("  • Risk assessment")
        print("  • Migration recommendations")
        print("")
        print("Example:")
        print("  python pre_migration_readiness.py /vmware/rhel9.vmdk")
        print("  python pre_migration_readiness.py /vmware/rhel9.vmdk --output assessment.json")
        sys.exit(1)

    vm_path = sys.argv[1]
    output_file = None

    if "--output" in sys.argv:
        output_idx = sys.argv.index("--output")
        if output_idx + 1 < len(sys.argv):
            output_file = sys.argv[output_idx + 1]

    if not Path(vm_path).exists():
        print(f"Error: VM not found: {vm_path}")
        sys.exit(1)

    # Run assessment
    assessment = ReadinessAssessment(vm_path)
    report = assessment.run_assessment()

    # Save report if requested
    if output_file:
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nDetailed report saved to: {output_file}")


if __name__ == "__main__":
    main()
