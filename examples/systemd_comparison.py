#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
systemd Configuration Comparison Tool

Compare systemd configurations across multiple VMs to identify:
- Distribution-specific systemd behaviors
- Security posture differences
- Boot configuration variations
- Network setup patterns

Usage:
    python3 systemd_comparison.py <vm1.vmdk> <vm2.vmdk> [vm3.vmdk ...]

Example:
    python3 systemd_comparison.py \
        /path/to/ubuntu.vmdk \
        /path/to/opensuse.vmdk \
        /path/to/fedora.vmdk
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from hyper2kvm.vmcraft.main import VMCraft


class SystemdComparison:
    """Compare systemd configurations across multiple VMs."""

    def __init__(self, disk_paths: list[str]):
        self.disk_paths = disk_paths
        self.results = {}

    def analyze_vm(self, disk_path: str) -> dict[str, Any]:
        """Analyze a single VM and collect systemd data."""
        print(f"\n{'=' * 70}")
        print(f" Analyzing: {Path(disk_path).name}")
        print(f"{'=' * 70}\n")

        g = VMCraft()
        vm_data = {
            "disk_path": disk_path,
            "disk_name": Path(disk_path).name,
            "analysis_time": datetime.now().isoformat(),
        }

        try:
            g.add_drive_opts(disk_path, readonly=True)
            g.launch()

            # Collect all systemd data points
            print("[*] Collecting virtualization info...")
            vm_data["virtualization"] = g.systemd_detect_virt()
            vm_data["machine_id"] = g.systemd_machine_id()

            print("[*] Analyzing boot configuration...")
            vm_data["boot_time"] = g.systemd_analyze_time_offline()
            vm_data["boot_entries"] = g.systemd_boot_entries()
            vm_data["loader_config"] = g.systemd_boot_loader_config()

            print("[*] Checking security...")
            vm_data["security"] = g.systemd_analyze_security_offline()
            vm_data["compliance"] = g.systemd_security_compliance_check()
            vm_data["anomalies"] = g.systemd_detect_anomalies()

            print("[*] Analyzing network...")
            vm_data["networkd"] = g.systemd_networkd_config()
            vm_data["resolved"] = g.systemd_resolved_config()

            print("[*] Checking system configuration...")
            vm_data["logind"] = g.systemd_logind_config()
            vm_data["oomd"] = g.systemd_oomd_config()
            vm_data["timesyncd"] = g.systemd_timesyncd_config()
            vm_data["sysusers"] = g.systemd_sysusers_config()

            print("[*] Checking failures and forensics...")
            vm_data["failures"] = g.systemd_analyze_failures()
            vm_data["coredumps"] = g.systemd_coredump_list()
            vm_data["coredump_config"] = g.systemd_coredump_config()
            vm_data["pstore"] = g.systemd_pstore_list()

            print("[*] Checking extensions...")
            vm_data["sysext"] = g.systemd_sysext_list()
            vm_data["portable"] = g.systemd_portable_list()

            print("[*] Checking migration readiness...")
            vm_data["migration_ready"] = g.systemd_migration_readiness_check()

            print("[*] Checking journal...")
            vm_data["boots"] = g.journalctl_list_boots_detailed()

            print("✓ Analysis complete\n")

        except Exception as e:
            print(f"✗ Error analyzing {Path(disk_path).name}: {e}\n")
            vm_data["error"] = str(e)

        finally:
            g.shutdown()

        return vm_data

    def run(self) -> dict[str, Any]:
        """Analyze all VMs and generate comparison."""
        print(f"{'=' * 70}")
        print(f" systemd Configuration Comparison")
        print(f" VMs to analyze: {len(self.disk_paths)}")
        print(f"{'=' * 70}")

        # Analyze each VM
        for disk_path in self.disk_paths:
            if not Path(disk_path).exists():
                print(f"⚠ Skipping (not found): {disk_path}")
                continue

            vm_data = self.analyze_vm(disk_path)
            self.results[Path(disk_path).stem] = vm_data

        # Generate comparison report
        self._print_comparison()

        # Save detailed report
        report_path = "/tmp/systemd_comparison_report.json"
        with open(report_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\n📄 Detailed report saved: {report_path}\n")

        return self.results

    def _print_comparison(self):
        """Print comparison table of key metrics."""
        print(f"\n{'=' * 70}")
        print(f" COMPARISON REPORT")
        print(f"{'=' * 70}\n")

        if not self.results:
            print("No results to compare")
            return

        # Table header
        vm_names = list(self.results.keys())
        print(f"{'Metric':<35} | " + " | ".join(f"{name[:15]:>15}" for name in vm_names))
        print("-" * 70)

        # Virtualization
        print(f"{'Virtualization Type':<35} | ", end="")
        for name in vm_names:
            virt_type = self.results[name].get("virtualization", {}).get("vm", "unknown")
            print(f"{virt_type:>15} | ", end="")
        print()

        # Boot time
        print(f"{'Boot Time (seconds)':<35} | ", end="")
        for name in vm_names:
            boot_time = self.results[name].get("boot_time", {}).get("total_time", 0)
            print(f"{boot_time:>15.2f} | ", end="")
        print()

        # Security score
        print(f"{'Security Compliance Score':<35} | ", end="")
        for name in vm_names:
            score = self.results[name].get("compliance", {}).get("score", 0)
            print(f"{score:>15} | ", end="")
        print()

        # Anomalies
        print(f"{'Total Anomalies':<35} | ", end="")
        for name in vm_names:
            anomalies = self.results[name].get("anomalies", {})
            total = (
                len(anomalies.get("hidden_units", []))
                + len(anomalies.get("writable_units", []))
                + len(anomalies.get("suspicious_timers", []))
                + len(anomalies.get("suspicious_sockets", []))
            )
            print(f"{total:>15} | ", end="")
        print()

        # Failed services
        print(f"{'Failed Services':<35} | ", end="")
        for name in vm_names:
            failures = self.results[name].get("failures", {})
            count = len(failures.get("failed_units", []))
            print(f"{count:>15} | ", end="")
        print()

        # Core dumps
        print(f"{'Core Dumps':<35} | ", end="")
        for name in vm_names:
            coredumps = self.results[name].get("coredumps", [])
            print(f"{len(coredumps):>15} | ", end="")
        print()

        # Migration readiness
        print(f"{'Migration Ready':<35} | ", end="")
        for name in vm_names:
            ready = self.results[name].get("migration_ready", {}).get("ready", False)
            status = "YES" if ready else "NO"
            print(f"{status:>15} | ", end="")
        print()

        # Network configuration
        print(f"{'systemd-networkd Files':<35} | ", end="")
        for name in vm_names:
            networkd = self.results[name].get("networkd", {})
            count = len(networkd.get("networks", []))
            print(f"{count:>15} | ", end="")
        print()

        # Boot entries
        print(f"{'systemd-boot Entries':<35} | ", end="")
        for name in vm_names:
            boot_entries = self.results[name].get("boot_entries", [])
            print(f"{len(boot_entries):>15} | ", end="")
        print()

        # System extensions
        print(f"{'System Extensions':<35} | ", end="")
        for name in vm_names:
            sysext = self.results[name].get("sysext", [])
            print(f"{len(sysext):>15} | ", end="")
        print()

        # Portable services
        print(f"{'Portable Services':<35} | ", end="")
        for name in vm_names:
            portable = self.results[name].get("portable", [])
            print(f"{len(portable):>15} | ", end="")
        print()

        print()

        # Differences analysis
        self._print_differences()

    def _print_differences(self):
        """Print notable differences between VMs."""
        print(f"\n{'=' * 70}")
        print(f" KEY DIFFERENCES")
        print(f"{'=' * 70}\n")

        if len(self.results) < 2:
            print("Need at least 2 VMs for comparison")
            return

        vm_names = list(self.results.keys())

        # Security compliance differences
        scores = {name: self.results[name].get("compliance", {}).get("score", 0) for name in vm_names}
        if scores:
            best = max(scores, key=scores.get)
            worst = min(scores, key=scores.get)
            if scores[best] != scores[worst]:
                print(f"🔒 Security Compliance:")
                print(f"   Best:  {best} ({scores[best]}/100)")
                print(f"   Worst: {worst} ({scores[worst]}/100)")
                print(f"   Gap:   {scores[best] - scores[worst]} points\n")

        # Boot time differences
        boot_times = {}
        for name in vm_names:
            bt = self.results[name].get("boot_time", {}).get("total_time", 0)
            if bt > 0:
                boot_times[name] = bt

        if boot_times:
            fastest = min(boot_times, key=boot_times.get)
            slowest = max(boot_times, key=boot_times.get)
            if boot_times[fastest] != boot_times[slowest]:
                print(f"⚡ Boot Performance:")
                print(f"   Fastest: {fastest} ({boot_times[fastest]:.2f}s)")
                print(f"   Slowest: {slowest} ({boot_times[slowest]:.2f}s)")
                diff = boot_times[slowest] - boot_times[fastest]
                print(f"   Diff:    {diff:.2f}s ({diff / boot_times[fastest] * 100:.1f}% slower)\n")

        # Network configuration differences
        networkd_counts = {
            name: len(self.results[name].get("networkd", {}).get("networks", [])) for name in vm_names
        }
        using_networkd = [name for name, count in networkd_counts.items() if count > 0]
        not_using_networkd = [name for name, count in networkd_counts.items() if count == 0]

        if using_networkd and not_using_networkd:
            print(f"🌐 Network Configuration:")
            print(f"   Using systemd-networkd: {', '.join(using_networkd)}")
            print(f"   Not using networkd:     {', '.join(not_using_networkd)}")
            print(f"   (Likely using NetworkManager or traditional networking)\n")

        # Migration readiness differences
        migration_status = {
            name: self.results[name].get("migration_ready", {}).get("ready", False) for name in vm_names
        }
        ready = [name for name, status in migration_status.items() if status]
        not_ready = [name for name, status in migration_status.items() if not status]

        if ready and not_ready:
            print(f"🚀 Migration Readiness:")
            print(f"   Ready:     {', '.join(ready)}")
            print(f"   Not Ready: {', '.join(not_ready)}\n")

        # Anomaly differences
        anomaly_counts = {}
        for name in vm_names:
            anomalies = self.results[name].get("anomalies", {})
            total = (
                len(anomalies.get("hidden_units", []))
                + len(anomalies.get("writable_units", []))
                + len(anomalies.get("suspicious_timers", []))
                + len(anomalies.get("suspicious_sockets", []))
            )
            anomaly_counts[name] = total

        if any(count > 0 for count in anomaly_counts.values()):
            print(f"⚠️  Security Anomalies:")
            for name, count in sorted(anomaly_counts.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    print(f"   {name}: {count} anomalies detected")
            print()

        # Configuration recommendations
        print(f"\n{'=' * 70}")
        print(f" RECOMMENDATIONS")
        print(f"{'=' * 70}\n")

        for name in vm_names:
            recommendations = self.results[name].get("migration_ready", {}).get("recommendations", [])
            if recommendations:
                print(f"{name}:")
                for rec in recommendations[:3]:  # Top 3
                    print(f"  • {rec}")
                print()


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <vm1.vmdk> <vm2.vmdk> [vm3.vmdk ...]")
        print(f"\nExample:")
        print(f"  {sys.argv[0]} \\")
        print(f"    /path/to/ubuntu.vmdk \\")
        print(f"    /path/to/opensuse.vmdk \\")
        print(f"    /path/to/fedora.vmdk")
        sys.exit(1)

    disk_paths = sys.argv[1:]

    comparison = SystemdComparison(disk_paths)
    comparison.run()


if __name__ == "__main__":
    main()
