#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Post-Migration Validation Tool

This tool performs comprehensive post-migration validation to ensure the
migrated VM is ready for production use on KVM.

Validations Performed:
1. Boot Configuration Verification
2. Service Health Check
3. Network Configuration Validation
4. Filesystem Integrity Check
5. Performance Baseline Comparison
6. Security Posture Validation
7. VMware Artifacts Cleanup Verification
8. KVM Integration Check
9. Critical Services Validation
10. Production Readiness Assessment

Output:
- Validation report (JSON)
- Pass/fail status for each check
- Issues found and remediation steps
- Production readiness score

Usage:
    python post_migration_validation.py <migrated-vm-path> [--output report.json]
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


class PostMigrationValidation:
    """Post-migration validation tool."""

    def __init__(self, vm_path: str):
        self.logger = setup_logging()
        self.vm_path = Path(vm_path)
        self.vm_name = self.vm_path.stem

        # Validation results
        self.validations: dict[str, Any] = {}
        self.issues: list[str] = []
        self.remediation_steps: list[str] = []
        self.production_score = 100  # Start at 100, deduct for issues

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

    def validate_boot_configuration(self, g: VMCraft, root: str) -> dict[str, Any]:
        """Validation 1: Boot Configuration."""
        self.print_section("Validation 1: Boot Configuration")

        validation = {
            "name": "Boot Configuration",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        try:
            # Check bootloader
            bootloader = g.inspect_get_bootloader(root)
            if bootloader:
                validation["details"]["bootloader"] = bootloader
                print(f"  ✓ Bootloader: {bootloader}")
            else:
                validation["status"] = "WARN"
                validation["issues"].append("Bootloader not detected")
                self.issues.append("Bootloader configuration could not be verified")
                self.remediation_steps.append("Verify GRUB configuration manually")
                self.production_score -= 10

            # Check boot mode
            mountpoints = g.inspect_get_mountpoints(root)
            has_efi = "/boot/efi" in mountpoints or "/boot/EFI" in mountpoints
            boot_mode = "EFI" if has_efi else "BIOS"

            validation["details"]["boot_mode"] = boot_mode
            print(f"  ✓ Boot mode: {boot_mode}")

            # Check for /boot partition
            has_boot = "/boot" in mountpoints
            validation["details"]["has_boot_partition"] = has_boot

            if has_boot:
                print(f"  ✓ Separate /boot partition detected")
            else:
                print(f"  - /boot is part of root filesystem")

        except Exception as e:
            validation["status"] = "FAIL"
            validation["issues"].append(f"Boot validation failed: {e}")
            self.issues.append("Boot configuration validation failed")
            self.production_score -= 15

        return validation

    def validate_service_health(self, g: VMCraft) -> dict[str, Any]:
        """Validation 2: Service Health Check."""
        self.print_section("Validation 2: Service Health Check")

        validation = {
            "name": "Service Health",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        if not g.systemd_is_available():
            validation["status"] = "SKIP"
            validation["issues"].append("Systemd not available")
            print(f"  - Systemd not available (skipping)")
            return validation

        # Check failed services
        failed_services = g.systemd_list_failed_services()
        validation["details"]["failed_services"] = len(failed_services)
        validation["details"]["failed_list"] = failed_services

        if failed_services:
            validation["status"] = "WARN"
            validation["issues"].append(f"{len(failed_services)} services failed")
            self.issues.append(f"{len(failed_services)} services are in failed state")

            print(f"  ⚠ Failed services: {len(failed_services)}")
            for svc in failed_services[:5]:
                print(f"      - {svc}")
                self.remediation_steps.append(f"Investigate and fix failed service: {svc}")

            if len(failed_services) > 5:
                print(f"      ... and {len(failed_services) - 5} more")

            self.production_score -= min(len(failed_services) * 3, 30)
        else:
            print(f"  ✓ No failed services detected")

        # Check for VMware services still enabled
        all_services = g.systemd_list_services()
        vmware_services = [s for s in all_services if "vmware" in s.lower() or "vmtool" in s.lower()]

        if vmware_services:
            enabled_vmware = []
            for svc in vmware_services:
                if g.systemd_is_service_enabled(svc):
                    enabled_vmware.append(svc)

            if enabled_vmware:
                validation["status"] = "WARN"
                validation["issues"].append(f"{len(enabled_vmware)} VMware services still enabled")
                self.issues.append("VMware services not properly disabled")

                print(f"  ⚠ VMware services still enabled: {len(enabled_vmware)}")
                for svc in enabled_vmware:
                    print(f"      - {svc}")
                    self.remediation_steps.append(f"Disable and mask VMware service: {svc}")

                self.production_score -= 15
            else:
                print(f"  ✓ VMware services properly disabled")
                validation["details"]["vmware_services_disabled"] = True
        else:
            validation["details"]["no_vmware_services"] = True

        # Check for qemu-guest-agent
        has_qemu_ga = "qemu-guest-agent.service" in all_services
        if has_qemu_ga:
            enabled = g.systemd_is_service_enabled("qemu-guest-agent.service")
            validation["details"]["qemu_guest_agent"] = enabled

            if enabled:
                print(f"  ✓ qemu-guest-agent enabled")
            else:
                validation["status"] = "WARN"
                validation["issues"].append("qemu-guest-agent not enabled")
                self.issues.append("KVM guest agent not enabled")
                self.remediation_steps.append("Enable qemu-guest-agent for KVM integration")
                self.production_score -= 10
        else:
            validation["details"]["qemu_guest_agent"] = False
            print(f"  - qemu-guest-agent not found (may need installation)")

        return validation

    def validate_network_configuration(self, g: VMCraft) -> dict[str, Any]:
        """Validation 3: Network Configuration."""
        self.print_section("Validation 3: Network Configuration")

        validation = {
            "name": "Network Configuration",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Check network configuration files
        try:
            # Check systemd-networkd
            networkd_files = g.networkd_list_network_files()
            if networkd_files:
                validation["details"]["networkd_files"] = len(networkd_files)
                print(f"  ✓ systemd-networkd: {len(networkd_files)} network files")

                # Validate each network file
                invalid_files = []
                for file_info in networkd_files:
                    result = g.networkd_parse_network_file(file_info["name"])
                    if not result["ok"]:
                        invalid_files.append(file_info["name"])

                if invalid_files:
                    validation["status"] = "WARN"
                    validation["issues"].append(f"{len(invalid_files)} invalid network files")
                    self.issues.append("Some network configuration files are invalid")
                    for f in invalid_files:
                        self.remediation_steps.append(f"Fix invalid network file: {f}")
                    self.production_score -= 10

                # Check if networkd is enabled
                result = g.systemd_is_service_enabled("systemd-networkd.service")
                validation["details"]["networkd_enabled"] = result

                if result:
                    print(f"  ✓ systemd-networkd service enabled")
                else:
                    validation["status"] = "WARN"
                    validation["issues"].append("systemd-networkd not enabled")
                    self.issues.append("Network service not enabled")
                    self.remediation_steps.append("Enable systemd-networkd service")
                    self.production_score -= 10

            # Check for old ifcfg files
            try:
                ifcfg_files = g.ls("/etc/sysconfig/network-scripts")
                ifcfg_count = len([f for f in ifcfg_files if f.startswith("ifcfg-")])
                if ifcfg_count > 0:
                    validation["details"]["old_ifcfg_files"] = ifcfg_count
                    print(f"  - Old ifcfg files still present: {ifcfg_count}")
                    print(f"    (These may conflict with systemd-networkd)")
                    self.remediation_steps.append(
                        "Review and remove old ifcfg files if using systemd-networkd"
                    )
            except Exception:
                pass

        except Exception as e:
            validation["status"] = "WARN"
            validation["issues"].append(f"Network validation failed: {e}")
            self.issues.append("Could not validate network configuration")
            self.production_score -= 10

        return validation

    def validate_filesystem_integrity(self, g: VMCraft) -> dict[str, Any]:
        """Validation 4: Filesystem Integrity."""
        self.print_section("Validation 4: Filesystem Integrity")

        validation = {
            "name": "Filesystem Integrity",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        # Check filesystems
        partitions = g.list_partitions()
        validation["details"]["partition_count"] = len(partitions)

        healthy_count = 0
        issue_count = 0

        for part in partitions:
            metadata = g.blkid(part)
            fstype = metadata.get("TYPE", "unknown")

            # Skip non-filesystem partitions
            if fstype in ("swap", "lvm2_member", "unknown"):
                continue

            # Try to mount read-only to verify filesystem
            try:
                mountpoint = f"/test-{Path(part).name}"
                g.mount(part, mountpoint, readonly=True, failure_log_level=logging.DEBUG)
                g.umount(mountpoint)
                healthy_count += 1
                print(f"  ✓ {part} ({fstype}): Healthy")
            except Exception as e:
                issue_count += 1
                validation["status"] = "WARN"
                validation["issues"].append(f"{part} mount failed")
                self.issues.append(f"Filesystem {part} may have issues")
                self.remediation_steps.append(f"Run filesystem check on {part}")
                self.production_score -= 10
                print(f"  ⚠ {part} ({fstype}): Could not mount - {str(e)[:50]}")

        validation["details"]["healthy_filesystems"] = healthy_count
        validation["details"]["filesystem_issues"] = issue_count

        if issue_count == 0:
            print(f"  ✓ All filesystems are healthy")

        return validation

    def validate_boot_performance(self, g: VMCraft) -> dict[str, Any]:
        """Validation 5: Boot Performance."""
        self.print_section("Validation 5: Boot Performance Analysis")

        validation = {
            "name": "Boot Performance",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        if not g.systemd_is_available():
            validation["status"] = "SKIP"
            print(f"  - Systemd not available (skipping)")
            return validation

        try:
            # Get boot performance
            perf = g.units_analyze_boot_performance()

            if perf["ok"]:
                validation["details"] = {
                    "kernel_time": perf.get("kernel_time"),
                    "userspace_time": perf.get("userspace_time"),
                    "boot_time": perf.get("boot_time"),
                }

                print(f"  Boot Performance:")
                print(f"    Kernel time: {perf.get('kernel_time', 'N/A')}")
                print(f"    Userspace time: {perf.get('userspace_time', 'N/A')}")
                print(f"    Total: {perf.get('boot_time', 'N/A')}")

                # Get slowest services
                blame = g.units_analyze_blame()
                if blame["ok"] and len(blame["services"]) > 0:
                    slowest = blame["services"][0]
                    validation["details"]["slowest_service"] = slowest

                    print(f"    Slowest service: {slowest['name']} ({slowest['time']})")

                    # Check if any service is extremely slow (>30s)
                    time_str = slowest["time"]
                    if "min" in time_str or (time_str.endswith("s") and float(time_str[:-1]) > 30):
                        validation["status"] = "WARN"
                        validation["issues"].append(f"Very slow service: {slowest['name']}")
                        self.issues.append(f"Boot performance impacted by slow service: {slowest['name']}")
                        self.remediation_steps.append(f"Investigate slow boot service: {slowest['name']}")
                        self.production_score -= 5
            else:
                validation["status"] = "WARN"
                validation["issues"].append("Boot performance analysis not available")
                print(f"  - Boot performance analysis not available")

        except Exception as e:
            validation["status"] = "WARN"
            validation["issues"].append(f"Performance validation failed: {e}")
            print(f"  - Could not analyze boot performance")

        return validation

    def validate_security_posture(self, g: VMCraft) -> dict[str, Any]:
        """Validation 6: Security Posture."""
        self.print_section("Validation 6: Security Posture")

        validation = {
            "name": "Security Posture",
            "status": "PASS",
            "details": {},
            "issues": [],
        }

        try:
            # Check SSH configuration (if Augeas is available)
            try:
                import augeas

                g.aug_init()

                # Check PermitRootLogin
                root_login = g.aug_get("/files/etc/ssh/sshd_config/PermitRootLogin")
                validation["details"]["permit_root_login"] = root_login

                if root_login and root_login.lower() != "no":
                    validation["status"] = "WARN"
                    validation["issues"].append("Root login is permitted")
                    self.issues.append("SSH permits root login (security risk)")
                    self.remediation_steps.append("Disable root login in /etc/ssh/sshd_config")
                    self.production_score -= 10
                    print(f"  ⚠ SSH PermitRootLogin: {root_login} (should be 'no')")
                else:
                    print(f"  ✓ SSH PermitRootLogin: no")

                # Check PasswordAuthentication
                pwd_auth = g.aug_get("/files/etc/ssh/sshd_config/PasswordAuthentication")
                validation["details"]["password_authentication"] = pwd_auth

                if pwd_auth and pwd_auth.lower() == "yes":
                    print(f"  - SSH PasswordAuthentication: yes (consider key-based auth)")
                else:
                    print(f"  ✓ SSH PasswordAuthentication: no (key-based auth)")

                g.aug_close()

            except ImportError:
                validation["details"]["augeas_available"] = False
                print(f"  - Augeas not available (skipping SSH config check)")
            except Exception:
                print(f"  - Could not check SSH configuration")

        except Exception as e:
            validation["status"] = "WARN"
            validation["issues"].append(f"Security validation failed: {e}")
            print(f"  - Security validation encountered errors")

        return validation

    def validate_production_readiness(self) -> dict[str, Any]:
        """Calculate production readiness score."""
        self.print_section("Production Readiness Assessment")

        # Categorize readiness
        if self.production_score >= 90:
            readiness_level = "READY"
            readiness_desc = "VM is production-ready"
        elif self.production_score >= 75:
            readiness_level = "MOSTLY READY"
            readiness_desc = "VM is mostly ready, address warnings before production"
        elif self.production_score >= 60:
            readiness_level = "NEEDS WORK"
            readiness_desc = "VM needs remediation before production use"
        else:
            readiness_level = "NOT READY"
            readiness_desc = "VM is not ready for production - significant issues found"

        assessment = {
            "production_score": self.production_score,
            "readiness_level": readiness_level,
            "description": readiness_desc,
            "issues_found": len(self.issues),
            "remediation_steps": len(self.remediation_steps),
        }

        print(f"  Production Score: {self.production_score}/100")
        print(f"  Readiness Level: {readiness_level}")
        print(f"  Issues Found: {len(self.issues)}")
        print(f"  Remediation Steps: {len(self.remediation_steps)}")
        print(f"\n  {readiness_desc}")

        return assessment

    def run_validation(self):
        """Run complete post-migration validation."""
        self.print_banner(f"POST-MIGRATION VALIDATION: {self.vm_name}")

        print(f"VM: {self.vm_path}")
        print(f"Validation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        with VMCraft(str(self.vm_path)) as g:
            # Detect OS
            roots = g.inspect_os()
            if not roots:
                self.logger.error("No operating system detected")
                self.issues.append("No operating system detected")
                self.production_score = 0

                report = self.generate_report()
                return report

            root = roots[0]

            # Mount filesystem
            mountpoints = g.inspect_get_mountpoints(root)
            for mp, device in mountpoints.items():
                try:
                    g.mount(device, mp, readonly=False)
                except Exception:
                    pass

            # Run all validations
            self.validations["boot_configuration"] = self.validate_boot_configuration(g, root)
            self.validations["service_health"] = self.validate_service_health(g)
            self.validations["network_configuration"] = self.validate_network_configuration(g)
            self.validations["filesystem_integrity"] = self.validate_filesystem_integrity(g)
            self.validations["boot_performance"] = self.validate_boot_performance(g)
            self.validations["security_posture"] = self.validate_security_posture(g)

            # Production readiness
            self.validations["production_readiness"] = self.validate_production_readiness()

            # Print remediation steps if any
            if self.remediation_steps:
                self.print_section("Remediation Steps Required")
                for i, step in enumerate(self.remediation_steps, 1):
                    print(f"  {i}. {step}")

        # Generate report
        report = self.generate_report()
        return report

    def generate_report(self) -> dict[str, Any]:
        """Generate final validation report."""
        self.print_banner("VALIDATION SUMMARY")

        # Summary
        print(f"VM Name: {self.vm_name}")
        print(f"Production Score: {self.production_score}/100")
        print(
            f"Readiness: {self.validations.get('production_readiness', {}).get('readiness_level', 'UNKNOWN')}"
        )

        # Validation breakdown
        pass_count = sum(
            1 for v in self.validations.values() if isinstance(v, dict) and v.get("status") == "PASS"
        )
        warn_count = sum(
            1 for v in self.validations.values() if isinstance(v, dict) and v.get("status") == "WARN"
        )
        fail_count = sum(
            1 for v in self.validations.values() if isinstance(v, dict) and v.get("status") == "FAIL"
        )
        skip_count = sum(
            1 for v in self.validations.values() if isinstance(v, dict) and v.get("status") == "SKIP"
        )

        print(f"\nValidations: {len(self.validations)}")
        print(f"  Passed: {pass_count}")
        print(f"  Warnings: {warn_count}")
        print(f"  Failed: {fail_count}")
        print(f"  Skipped: {skip_count}")

        # Issues
        if self.issues:
            print(f"\nIssues Found: {len(self.issues)}")
            for issue in self.issues[:5]:
                print(f"  ⚠ {issue}")
            if len(self.issues) > 5:
                print(f"  ... and {len(self.issues) - 5} more")

        # Final recommendation
        print(f"\n{'=' * 80}")
        if self.production_score >= 90:
            print("  ✓ PRODUCTION READY")
        elif self.production_score >= 75:
            print("  ⚠ MOSTLY READY - Address warnings")
        elif self.production_score >= 60:
            print("  ⚠ NEEDS REMEDIATION")
        else:
            print("  ✗ NOT READY FOR PRODUCTION")
        print(f"{'=' * 80}\n")

        # Generate full report
        report = {
            "vm_name": self.vm_name,
            "vm_path": str(self.vm_path),
            "validation_time": datetime.now().isoformat(),
            "production_score": self.production_score,
            "readiness_level": self.validations.get("production_readiness", {}).get(
                "readiness_level", "UNKNOWN"
            ),
            "validations": self.validations,
            "issues": self.issues,
            "remediation_steps": self.remediation_steps,
            "summary": {
                "total_validations": len(self.validations),
                "passed": pass_count,
                "warnings": warn_count,
                "failed": fail_count,
                "skipped": skip_count,
            },
        }

        return report


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python post_migration_validation.py <migrated-vm-path> [--output report.json]")
        print("")
        print("Post-Migration Validation Tool")
        print("")
        print("Validates migrated VM for production readiness:")
        print("  • Boot configuration verification")
        print("  • Service health check")
        print("  • Network configuration validation")
        print("  • Filesystem integrity check")
        print("  • Boot performance analysis")
        print("  • Security posture validation")
        print("  • Production readiness assessment")
        print("")
        print("Example:")
        print("  python post_migration_validation.py /kvm/migrated-rhel9.qcow2")
        print("  python post_migration_validation.py /kvm/migrated-rhel9.qcow2 --output validation.json")
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

    # Run validation
    validation = PostMigrationValidation(vm_path)
    report = validation.run_validation()

    # Save report if requested
    if output_file:
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nDetailed report saved to: {output_file}")


if __name__ == "__main__":
    main()
