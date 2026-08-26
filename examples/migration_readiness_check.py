#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Migration Readiness Checker

Pre-flight check for VM migration from VMware to KVM.
Identifies blockers, warnings, and provides remediation recommendations.

Usage:
    python3 migration_readiness_check.py <vmdk-path>

Example:
    python3 migration_readiness_check.py /vmware/production-vm.vmdk
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.main import VMCraft


class MigrationReadinessChecker:
    """Check VM migration readiness with detailed reporting."""

    def __init__(self, disk_path: str):
        self.disk_path = Path(disk_path)
        self.g = VMCraft()
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "vm_disk": str(self.disk_path),
            "ready": False,
            "risk_level": "unknown",
            "checks": {},
        }

    def run(self) -> dict:
        """Run comprehensive migration readiness check."""
        try:
            print(f"[*] Analyzing: {self.disk_path.name}")
            print(f"[*] Size: {self.disk_path.stat().st_size / (1024**3):.2f} GiB\n")

            self.g.add_drive_opts(str(self.disk_path), readonly=True)
            self.g.launch()

            # Run all checks
            self._check_virtualization()
            self._check_systemd_migration_readiness()
            self._check_boot_configuration()
            self._check_network_configuration()
            self._check_security_posture()
            self._check_failed_services()

            # Calculate overall readiness
            self._calculate_readiness()

            # Print report
            self._print_report()

            return self.report

        finally:
            self.g.shutdown()

    def _check_virtualization(self):
        """Check current virtualization environment."""
        print("=" * 70)
        print(" CHECK 1: Virtualization Detection")
        print("=" * 70)

        virt = self.g.systemd_detect_virt()
        machine_id = self.g.systemd_machine_id()

        self.report["checks"]["virtualization"] = {
            "type": virt["type"],
            "vm": virt["vm"],
            "container": virt["container"],
            "machine_id": machine_id,
            "status": "info",
        }

        print(f"Current Environment:")
        print(f"  Type:       {virt['type']}")
        print(f"  VM:         {virt['vm']}")
        print(f"  Container:  {virt['container']}")
        print(f"  Machine ID: {machine_id[:16] + '...' if machine_id else 'Not found'}")

        if virt["vm"] == "vmware":
            print(f"\n✓ VMware guest tools detected - will need replacement in KVM")
        elif virt["vm"] != "none":
            print(f"\n⚠ Currently running on {virt['vm']} - migration may have compatibility issues")

        print()

    def _check_systemd_migration_readiness(self):
        """Run systemd migration readiness checks."""
        print("=" * 70)
        print(" CHECK 2: systemd Migration Readiness")
        print("=" * 70)

        readiness = self.g.systemd_migration_readiness_check()

        self.report["checks"]["systemd_readiness"] = readiness

        print(f"Overall Status: {'READY ✓' if readiness['ready'] else 'NOT READY ✗'}")
        print(f"  Checks Performed: {readiness['checks_performed']}")
        print(f"  Checks Passed:    {readiness['checks_passed']}")

        # Show blockers
        if readiness["blockers"]:
            print(f"\n🚫 BLOCKERS ({len(readiness['blockers'])}):")
            for i, blocker in enumerate(readiness["blockers"], 1):
                print(f"\n  {i}. {blocker['check']}")
                print(f"     Severity: {blocker['severity'].upper()}")
                print(f"     Issue:    {blocker['issue']}")
                print(f"     Impact:   {blocker['impact']}")

        # Show warnings
        if readiness["warnings"]:
            print(f"\n⚠️  WARNINGS ({len(readiness['warnings'])}):")
            for i, warning in enumerate(readiness["warnings"], 1):
                print(f"\n  {i}. {warning['check']}")
                print(f"     Issue:  {warning['issue']}")
                print(f"     Impact: {warning.get('impact', 'May cause issues')}")

        # Show recommendations
        if readiness["recommendations"]:
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in readiness["recommendations"]:
                print(f"  • {rec}")

        print()

    def _check_boot_configuration(self):
        """Check boot loader and boot entries."""
        print("=" * 70)
        print(" CHECK 3: Boot Configuration")
        print("=" * 70)

        boot_entries = self.g.systemd_boot_entries()
        loader_config = self.g.systemd_boot_loader_config()

        self.report["checks"]["boot"] = {
            "systemd_boot_entries": len(boot_entries),
            "loader_config": loader_config,
            "status": "pass" if boot_entries or loader_config else "info",
        }

        if boot_entries:
            print(f"✓ systemd-boot entries found: {len(boot_entries)}")
            for entry in boot_entries:
                print(f"  • {entry.get('title', entry['file'])}")
        else:
            print("ℹ No systemd-boot entries (may use GRUB or other bootloader)")

        if loader_config:
            print(f"\nBoot Loader Configuration:")
            for key, value in loader_config.items():
                print(f"  {key}: {value}")

        print()

    def _check_network_configuration(self):
        """Check network configuration for migration compatibility."""
        print("=" * 70)
        print(" CHECK 4: Network Configuration")
        print("=" * 70)

        netconfig = self.g.systemd_networkd_config()
        dns_config = self.g.systemd_resolved_config()

        issues = []

        # Check for systemd-networkd
        if netconfig["networks"]:
            print(f"✓ systemd-networkd in use ({len(netconfig['networks'])} network files)")

            # Check each network file for hardcoded MACs
            for net_file_info in netconfig["networks"]:
                net_file = Path(net_file_info["path"])
                if net_file.exists():
                    content = net_file.read_text()
                    if "MACAddress=" in content or "PermanentMACAddress=" in content:
                        issues.append(f"Hardcoded MAC in {net_file.name}")

            if issues:
                print(f"\n⚠️  Network Issues:")
                for issue in issues:
                    print(f"  • {issue}")
        else:
            print("ℹ No systemd-networkd configuration found")
            print("  (May use NetworkManager or traditional networking)")

        # DNS configuration
        if dns_config["dns_servers"]:
            print(f"\n✓ DNS configured: {', '.join(dns_config['dns_servers'])}")

        self.report["checks"]["network"] = {
            "networkd_files": len(netconfig["networks"]),
            "dns_servers": dns_config["dns_servers"],
            "issues": issues,
            "status": "fail" if issues else "pass",
        }

        print()

    def _check_security_posture(self):
        """Check security configuration."""
        print("=" * 70)
        print(" CHECK 5: Security Posture")
        print("=" * 70)

        compliance = self.g.systemd_security_compliance_check()
        anomalies = self.g.systemd_detect_anomalies()

        self.report["checks"]["security"] = {
            "compliance_score": compliance["score"],
            "anomalies_found": sum(len(v) for v in anomalies.values()),
            "status": "pass" if compliance["score"] >= 70 else "warn",
        }

        print(f"Security Compliance Score: {compliance['score']}/100")

        if compliance["score"] >= 80:
            print("  ✓ Good security posture")
        elif compliance["score"] >= 60:
            print("  ⚠ Moderate security posture")
        else:
            print("  ✗ Poor security posture")

        # Anomalies
        anomaly_count = sum(len(v) for v in anomalies.values())
        if anomaly_count > 0:
            print(f"\n⚠️  Anomalies Detected: {anomaly_count}")
            if anomalies["hidden_units"]:
                print(f"  • Hidden units: {len(anomalies['hidden_units'])}")
            if anomalies["writable_units"]:
                print(f"  • World-writable units: {len(anomalies['writable_units'])}")
            if anomalies["suspicious_timers"]:
                print(f"  • Suspicious timers: {len(anomalies['suspicious_timers'])}")
            if anomalies["suspicious_sockets"]:
                print(f"  • Suspicious sockets: {len(anomalies['suspicious_sockets'])}")

        print()

    def _check_failed_services(self):
        """Check for failed services that may cause issues."""
        print("=" * 70)
        print(" CHECK 6: Service Health")
        print("=" * 70)

        failures = self.g.systemd_analyze_failures()

        self.report["checks"]["services"] = {
            "failed_count": len(failures["failed_units"]),
            "failure_patterns": failures["failure_patterns"],
            "status": "warn" if len(failures["failed_units"]) > 0 else "pass",
        }

        if failures["failed_units"]:
            print(f"⚠️  Failed Services: {len(failures['failed_units'])}")

            if failures["failure_patterns"]:
                print(f"\nFailure Patterns:")
                for pattern, count in failures["failure_patterns"].items():
                    print(f"  • {pattern}: {count}")

            if failures["recommendations"]:
                print(f"\nRecommendations:")
                for rec in failures["recommendations"]:
                    print(f"  • {rec}")
        else:
            print("✓ No failed services detected")

        print()

    def _calculate_readiness(self):
        """Calculate overall migration readiness."""
        # Check for blockers
        systemd_check = self.report["checks"].get("systemd_readiness", {})
        has_blockers = len(systemd_check.get("blockers", [])) > 0

        # Count issues
        total_warnings = len(systemd_check.get("warnings", []))
        network_issues = len(self.report["checks"]["network"].get("issues", []))
        failed_services = self.report["checks"]["services"].get("failed_count", 0)
        security_score = self.report["checks"]["security"].get("compliance_score", 0)

        # Determine readiness
        if has_blockers:
            self.report["ready"] = False
            self.report["risk_level"] = "high"
        elif total_warnings > 5 or network_issues > 0 or failed_services > 10:
            self.report["ready"] = True
            self.report["risk_level"] = "medium"
        elif total_warnings > 0 or security_score < 70:
            self.report["ready"] = True
            self.report["risk_level"] = "low"
        else:
            self.report["ready"] = True
            self.report["risk_level"] = "minimal"

    def _print_report(self):
        """Print final readiness report."""
        print("=" * 70)
        print(" MIGRATION READINESS REPORT")
        print("=" * 70)

        # Overall status
        if self.report["ready"]:
            print(f"\n✅ READY FOR MIGRATION")
        else:
            print(f"\n❌ NOT READY FOR MIGRATION")

        print(f"\nRisk Level: {self.report['risk_level'].upper()}")

        # Risk explanation
        if self.report["risk_level"] == "minimal":
            print("  All checks passed with no significant issues.")
        elif self.report["risk_level"] == "low":
            print("  Minor issues detected, migration should proceed smoothly.")
        elif self.report["risk_level"] == "medium":
            print("  Some issues detected, recommend fixing before migration.")
        elif self.report["risk_level"] == "high":
            print("  Critical blockers found, MUST be fixed before migration.")

        # Summary
        print(f"\nChecks Summary:")
        for check_name, check_data in self.report["checks"].items():
            status = check_data.get("status", "unknown")
            icon = {"pass": "✓", "warn": "⚠", "fail": "✗", "info": "ℹ"}.get(status, "?")
            print(f"  {icon} {check_name:30} {status.upper()}")

        # Next steps
        print(f"\n{'=' * 70}")
        print(" NEXT STEPS")
        print("=" * 70)

        if not self.report["ready"]:
            print("\n1. Fix all BLOCKERS identified above")
            print("2. Re-run this check to verify")
            print("3. Proceed with migration only when ready")
        else:
            if self.report["risk_level"] in ["medium", "high"]:
                print("\n1. Review and address warnings (recommended)")
                print("2. Test migration in non-production environment")
                print("3. Plan rollback procedure")
                print("4. Proceed with migration")
            else:
                print("\n1. Perform backup of source VM")
                print("2. Test migration in non-production environment (recommended)")
                print("3. Execute migration")
                print("4. Run post-migration validation")

        # Save report
        report_file = f"/tmp/migration_readiness_{self.disk_path.stem}.json"
        with open(report_file, "w") as f:
            json.dump(self.report, f, indent=2)

        print(f"\n📄 Detailed report saved: {report_file}")
        print()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <vmdk-path>")
        print(f"\nExample: {sys.argv[0]} /vmware/production-vm.vmdk")
        sys.exit(1)

    disk_path = sys.argv[1]

    if not Path(disk_path).exists():
        print(f"Error: Disk image not found: {disk_path}")
        sys.exit(1)

    checker = MigrationReadinessChecker(disk_path)
    report = checker.run()

    # Exit code based on readiness
    if not report["ready"]:
        sys.exit(2)  # Not ready (blockers)
    elif report["risk_level"] in ["medium", "high"]:
        sys.exit(1)  # Ready but risky
    else:
        sys.exit(0)  # Ready with minimal risk


if __name__ == "__main__":
    main()
