#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Complete systemd Forensic Analysis Example

Demonstrates all 28 new systemd inspection methods for:
- Security compliance auditing
- Migration readiness assessment
- Crash/forensic analysis
- Boot performance analysis
- Anomaly detection

Usage:
    python3 systemd_forensic_analysis.py <disk-image>

Example:
    python3 systemd_forensic_analysis.py /path/to/vm.qcow2
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.main import VMCraft


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f" {title}")
    print(f"{'=' * 80}\n")


def forensic_analysis(disk_path: str):
    """Run comprehensive forensic analysis on VM disk."""
    g = VMCraft()

    try:
        print(f"[*] Launching {disk_path}...")
        g.add_drive_opts(disk_path, readonly=True)
        g.launch()

        # ====================================================================
        # Category 1: Core Offline Analysis
        # ====================================================================

        print_section("1. VIRTUALIZATION & IDENTITY")

        # Detect virtualization
        virt = g.systemd_detect_virt()
        print(f"Virtualization Type: {virt['type']}")
        print(f"  VM:        {virt['vm']}")
        print(f"  Container: {virt['container']}")

        # Machine ID
        machine_id = g.systemd_machine_id()
        print(f"\nMachine ID: {machine_id}")

        # ====================================================================
        # Category 2: Boot Performance Analysis
        # ====================================================================

        print_section("2. BOOT PERFORMANCE ANALYSIS")

        # Boot timing
        boot_time = g.systemd_analyze_time_offline()
        if boot_time["total_time"] > 0:
            print(f"Boot Time Analysis:")
            print(f"  Kernel:     {boot_time['kernel_time']:.2f}s")
            print(f"  Userspace:  {boot_time['userspace_time']:.2f}s")
            print(f"  Total:      {boot_time['total_time']:.2f}s")

            # Generate boot plot
            output_file = "/tmp/boot-plot.svg"
            print(f"\n[*] Generating boot timeline SVG...")
            svg_content = g.systemd_analyze_plot_offline(output_file)
            if svg_content:
                print(f"    Saved to: {output_file}")
                print(f"    Size:     {len(svg_content)} bytes")
        else:
            print("No boot data available")

        # ====================================================================
        # Category 3: Security Analysis
        # ====================================================================

        print_section("3. SECURITY ANALYSIS")

        # Offline security analysis
        print("[*] Running systemd-analyze security (offline)...")
        security = g.systemd_analyze_security_offline()
        if security:
            print(f"Analyzed {len(security)} services:\n")

            # Show top 5 most exposed
            sorted_sec = sorted(
                security,
                key=lambda x: float(
                    x.get("exposure", "0") if x.get("exposure", "0").replace(".", "").isdigit() else "0"
                ),
                reverse=True,
            )

            print("Top 5 Most Exposed Services:")
            print(f"{'Service':<40} {'Exposure':<10} {'Status'}")
            print("-" * 65)
            for svc in sorted_sec[:5]:
                print(f"{svc['unit']:<40} {svc['exposure']:<10} {svc['predicate']}")

        # Compliance check
        print("\n[*] Running security compliance check...")
        compliance = g.systemd_security_compliance_check()
        print(f"\nCompliance Score: {compliance['score']}/100")
        print(f"  Checks Performed: {compliance['total_checks']}")
        print(f"  Passed:           {compliance['passed']}")
        print(f"  Failed:           {compliance['failed']}")

        if compliance["findings"]:
            print("\nFindings:")
            for finding in compliance["findings"][:3]:
                print(f"  [{finding['severity'].upper()}] {finding['check']}: {finding['status']}")

        if compliance["recommendations"]:
            print("\nTop Recommendations:")
            for rec in compliance["recommendations"][:3]:
                print(f"  - {rec}")

        # ====================================================================
        # Category 4: Anomaly Detection
        # ====================================================================

        print_section("4. ANOMALY DETECTION")

        anomalies = g.systemd_detect_anomalies()

        print(f"Hidden Units:       {len(anomalies['hidden_units'])}")
        print(f"Writable Units:     {len(anomalies['writable_units'])}")
        print(f"Suspicious Timers:  {len(anomalies['suspicious_timers'])}")
        print(f"Suspicious Sockets: {len(anomalies['suspicious_sockets'])}")

        if anomalies["hidden_units"]:
            print("\nHidden Units Found:")
            for unit in anomalies["hidden_units"]:
                print(f"  - {unit['file']} ({unit['size']} bytes)")

        if anomalies["suspicious_sockets"]:
            print("\nSuspicious Socket Activations:")
            for socket in anomalies["suspicious_sockets"]:
                print(f"  - {socket['file']}: {socket['address']} ({socket['reason']})")

        # ====================================================================
        # Category 5: Forensic Data
        # ====================================================================

        print_section("5. CRASH & FORENSIC DATA")

        # Core dumps
        coredumps = g.systemd_coredump_list()
        print(f"Core Dumps Found: {len(coredumps)}")
        if coredumps:
            print("\nRecent Crashes:")
            for dump in coredumps[:5]:
                print(f"  - {dump['command']} (PID {dump['pid']}) - {dump['size_mb']:.2f} MB")

        coredump_config = g.systemd_coredump_config()
        print(f"\nCore Dump Config:")
        print(f"  Storage:          {coredump_config['Storage']}")
        print(f"  Compress:         {coredump_config['Compress']}")
        print(f"  ProcessSizeMax:   {coredump_config['ProcessSizeMax']}")

        # Persistent storage (pstore)
        pstore = g.systemd_pstore_list()
        print(f"\nPersistent Storage Entries: {len(pstore)}")
        if pstore:
            print("Crash Data:")
            for entry in pstore:
                print(f"  - {entry['file']} ({entry['type']}) - {entry['size_kb']:.2f} KB")

        # ====================================================================
        # Category 6: Failed Services Analysis
        # ====================================================================

        print_section("6. FAILED SERVICES ANALYSIS")

        failures = g.systemd_analyze_failures()
        print(f"Failed Services: {len(failures['failed_units'])}")

        if failures["failure_patterns"]:
            print("\nFailure Patterns:")
            for pattern, count in failures["failure_patterns"].items():
                print(f"  {pattern}: {count}")

        if failures["recommendations"]:
            print("\nRecommendations:")
            for rec in failures["recommendations"]:
                print(f"  - {rec}")

        # ====================================================================
        # Category 7: Network Configuration
        # ====================================================================

        print_section("7. NETWORK CONFIGURATION")

        # systemd-networkd
        netconfig = g.systemd_networkd_config()
        print(f"systemd-networkd Files:")
        print(f"  Networks: {len(netconfig['networks'])}")
        print(f"  Netdevs:  {len(netconfig['netdevs'])}")
        print(f"  Links:    {len(netconfig['links'])}")

        if netconfig["networks"]:
            print("\nNetwork Files:")
            for net in netconfig["networks"]:
                print(f"  - {net['file']}")

        # systemd-resolved
        dns_config = g.systemd_resolved_config()
        if dns_config["dns_servers"]:
            print(f"\nDNS Configuration:")
            print(f"  Servers:     {', '.join(dns_config['dns_servers'])}")
        if dns_config["fallback_dns"]:
            print(f"  Fallback:    {', '.join(dns_config['fallback_dns'])}")
        if dns_config["dnssec"]:
            print(f"  DNSSEC:      {dns_config['dnssec']}")

        # ====================================================================
        # Category 8: Boot Configuration
        # ====================================================================

        print_section("8. BOOT CONFIGURATION")

        # Boot entries (UEFI)
        boot_entries = g.systemd_boot_entries()
        print(f"systemd-boot Entries: {len(boot_entries)}")
        if boot_entries:
            print("\nBoot Entries:")
            for entry in boot_entries:
                print(f"  - {entry.get('title', entry['file'])}")
                if "linux" in entry:
                    print(f"    Kernel: {entry['linux']}")

        # Boot loader config
        loader_config = g.systemd_boot_loader_config()
        if loader_config:
            print("\nBoot Loader Configuration:")
            for key, value in loader_config.items():
                print(f"  {key}: {value}")

        # ====================================================================
        # Category 9: System Users & Sessions
        # ====================================================================

        print_section("9. SYSTEM USERS & SESSIONS")

        # sysusers
        sysusers = g.systemd_sysusers_config()
        print(f"Provisioned System Users: {len(sysusers)}")
        if sysusers:
            print("\nSystem Users (first 5):")
            for user in sysusers[:5]:
                print(f"  - {user['name']} ({user['type']}) from {user['source_file']}")

        # logind config
        logind = g.systemd_logind_config()
        print(f"\nlogind Configuration:")
        print(f"  KillUserProcesses: {logind['KillUserProcesses']}")
        print(f"  HandlePowerKey:    {logind['HandlePowerKey']}")
        print(f"  IdleAction:        {logind['IdleAction']}")

        # ====================================================================
        # Category 10: Migration Readiness
        # ====================================================================

        print_section("10. MIGRATION READINESS ASSESSMENT")

        readiness = g.systemd_migration_readiness_check()
        print(f"Migration Ready: {'YES ✓' if readiness['ready'] else 'NO ✗'}")
        print(f"  Checks Performed: {readiness['checks_performed']}")
        print(f"  Checks Passed:    {readiness['checks_passed']}")

        if readiness["blockers"]:
            print("\nBLOCKERS:")
            for blocker in readiness["blockers"]:
                print(f"  [{blocker['severity'].upper()}] {blocker['check']}")
                print(f"    Issue:  {blocker['issue']}")
                print(f"    Impact: {blocker['impact']}")

        if readiness["warnings"]:
            print("\nWARNINGS:")
            for warning in readiness["warnings"]:
                print(f"  - {warning['check']}: {warning['issue']}")

        if readiness["recommendations"]:
            print("\nRECOMMENDATIONS:")
            for rec in readiness["recommendations"][:5]:
                print(f"  - {rec}")

        # ====================================================================
        # Category 11: Advanced System Configuration
        # ====================================================================

        print_section("11. ADVANCED SYSTEM CONFIGURATION")

        # OOM daemon
        oomd = g.systemd_oomd_config()
        print(f"OOM Daemon Configuration:")
        print(f"  SwapUsedLimit:                 {oomd['SwapUsedLimit']}")
        print(f"  DefaultMemoryPressureLimit:    {oomd['DefaultMemoryPressureLimit']}")
        print(f"  DefaultMemoryPressureDuration: {oomd['DefaultMemoryPressureDurationSec']}")

        # Time sync
        timesyncd = g.systemd_timesyncd_config()
        print(f"\nTime Synchronization:")
        if timesyncd["NTP"]:
            print(f"  NTP Servers:      {', '.join(timesyncd['NTP'])}")
        print(f"  Fallback Servers: {', '.join(timesyncd['FallbackNTP'])}")
        print(f"  Poll Min/Max:     {timesyncd['PollIntervalMinSec']}s / {timesyncd['PollIntervalMaxSec']}s")

        # System extensions
        sysext = g.systemd_sysext_list()
        print(f"\nSystem Extensions: {len(sysext)}")
        if sysext:
            for ext in sysext:
                print(f"  - {ext['name']} ({ext['size_mb']:.2f} MB) from {ext['location']}")

        # Portable services
        portables = g.systemd_portable_list()
        print(f"\nPortable Services: {len(portables)}")
        if portables:
            for portable in portables:
                print(f"  - {portable['name']} ({portable['type']}) - {portable['size_mb']:.2f} MB")

        # ====================================================================
        # Category 12: Journal Analysis
        # ====================================================================

        print_section("12. JOURNAL ANALYSIS")

        # Detailed boot history
        boots = g.journalctl_list_boots_detailed()
        print(f"Boot History: {len(boots)} boot(s) recorded")
        if boots:
            print("\nRecent Boots:")
            for boot in boots[:3]:
                print(f"  - Boot ID: {boot['boot_id'][:8]}...")
                if boot["first_entry"]:
                    print(f"    First: {boot['first_entry']}")
                if boot["last_entry"]:
                    print(f"    Last:  {boot['last_entry']}")

        # Export journal
        journal_export_path = "/tmp/journal_export.bin"
        print(f"\n[*] Exporting journal logs...")
        if g.journalctl_export_to_file(journal_export_path):
            import os

            size_mb = os.path.getsize(journal_export_path) / (1024 * 1024)
            print(f"    Exported to: {journal_export_path} ({size_mb:.2f} MB)")

        # ====================================================================
        # Summary
        # ====================================================================

        print_section("FORENSIC ANALYSIS SUMMARY")

        summary = {
            "virtualization": virt,
            "machine_id": machine_id,
            "boot_time_total": boot_time.get("total_time", 0),
            "security_score": compliance["score"],
            "anomalies_found": (
                len(anomalies["hidden_units"])
                + len(anomalies["writable_units"])
                + len(anomalies["suspicious_timers"])
                + len(anomalies["suspicious_sockets"])
            ),
            "core_dumps": len(coredumps),
            "pstore_entries": len(pstore),
            "failed_services": len(failures["failed_units"]),
            "migration_ready": readiness["ready"],
            "boot_entries": len(boot_entries),
            "system_users": len(sysusers),
            "system_extensions": len(sysext),
            "portable_services": len(portables),
        }

        print(json.dumps(summary, indent=2))

        # Save detailed report
        report_path = "/tmp/forensic_analysis_report.json"
        with open(report_path, "w") as f:
            report = {
                "summary": summary,
                "compliance": compliance,
                "anomalies": anomalies,
                "readiness": readiness,
                "boot_time": boot_time,
                "security": security[:10] if security else [],  # Top 10 services
                "coredumps": coredumps,
                "pstore": pstore,
                "failures": failures,
            }
            json.dump(report, f, indent=2)

        print(f"\n✓ Detailed report saved to: {report_path}")

    finally:
        print("\n[*] Shutting down...")
        g.shutdown()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <disk-image>")
        print(f"\nExample: {sys.argv[0]} /path/to/vm.qcow2")
        sys.exit(1)

    disk_image = sys.argv[1]

    if not Path(disk_image).exists():
        print(f"Error: Disk image not found: {disk_image}")
        sys.exit(1)

    forensic_analysis(disk_image)
