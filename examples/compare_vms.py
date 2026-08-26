#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Multi-VM Comparison Tool

Compare multiple VM disk images side-by-side:
- OS versions and configurations
- Filesystem types and layouts
- Disk space usage
- Service configurations (systemd)
- Package inventories
- Network configurations

Generates comparison tables and migration priority recommendations.

Usage:
    python3 compare_vms.py <disk1> <disk2> [disk3] [...] [options]

Example:
    python3 compare_vms.py /vms/web*.vmdk --output comparison_report.html
    python3 compare_vms.py vm1.vmdk vm2.vmdk vm3.vmdk --format table
"""

import sys
import argparse
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from datetime import datetime

from h2kvm.vmcraft.main import VMCraft


@dataclass
class VMProfile:
    """Profile of a single VM."""

    name: str
    path: Path
    size_gb: float

    # OS Information
    os_type: str
    os_distro: str
    os_product: str
    os_version: str
    os_arch: str

    # Filesystem Information
    filesystem_count: int
    filesystem_types: list[str]
    root_filesystem: str
    total_disk_gb: float
    used_disk_gb: float
    usage_percent: float

    # Services (systemd)
    total_services: int
    active_services: int
    failed_services: int
    boot_time_seconds: float

    # Configuration
    mountpoints: dict[str, str]
    network_interfaces: int

    # Migration complexity score (0-100)
    complexity_score: int


class VMComparator:
    """Compare multiple VMs and generate comparison reports."""

    def __init__(self, disk_images: list[Path]):
        """
        Initialize comparator.

        Args:
            disk_images: List of disk image paths to compare
        """
        self.disk_images = disk_images
        self.profiles: list[VMProfile] = []

    def analyze_vm(self, disk_image: Path) -> VMProfile:
        """
        Analyze a single VM and create profile.

        Args:
            disk_image: Path to disk image

        Returns:
            VMProfile with analysis results
        """
        print(f"Analyzing: {disk_image.name}...", end=" ", flush=True)

        # Initialize profile with defaults
        profile = VMProfile(
            name=disk_image.stem,
            path=disk_image,
            size_gb=disk_image.stat().st_size / (1024**3),
            os_type="unknown",
            os_distro="unknown",
            os_product="Unknown",
            os_version="0.0",
            os_arch="unknown",
            filesystem_count=0,
            filesystem_types=[],
            root_filesystem="unknown",
            total_disk_gb=0.0,
            used_disk_gb=0.0,
            usage_percent=0.0,
            total_services=0,
            active_services=0,
            failed_services=0,
            boot_time_seconds=0.0,
            mountpoints={},
            network_interfaces=0,
            complexity_score=0,
        )

        g = VMCraft()
        g.add_drive_opts(str(disk_image), readonly=True)
        g.launch()

        try:
            # OS Detection
            roots = g.inspect_os()
            if roots:
                root = roots[0]
                profile.os_type = g.inspect_get_type(root) or "unknown"
                profile.os_distro = g.inspect_get_distro(root) or "unknown"
                profile.os_product = g.inspect_get_product_name(root) or "Unknown"

                major = g.inspect_get_major_version(root) or 0
                minor = g.inspect_get_minor_version(root) or 0
                profile.os_version = f"{major}.{minor}"

                profile.os_arch = g.inspect_get_arch(root) or "unknown"

                # Mount structure
                profile.mountpoints = g.inspect_get_mountpoints(root)

            # Filesystem Analysis
            filesystems = g.list_filesystems()
            profile.filesystem_count = len(filesystems)
            profile.filesystem_types = list(set(filesystems.values()))

            # Get root filesystem type
            if roots:
                root_fs_type = g.vfs_type(roots[0])
                profile.root_filesystem = root_fs_type or "unknown"

            # Disk Usage
            try:
                stats = g.statvfs("/")
                profile.total_disk_gb = stats["blocks"] * stats["bsize"] / (1024**3)
                free_gb = stats["bfree"] * stats["bsize"] / (1024**3)
                profile.used_disk_gb = profile.total_disk_gb - free_gb
                profile.usage_percent = (profile.used_disk_gb / profile.total_disk_gb) * 100
            except Exception:
                pass

            # Systemd Analysis (Linux only)
            if profile.os_type == "linux":
                try:
                    all_services = g.systemctl_list_units("service", all_units=True)
                    profile.total_services = len(all_services)
                    profile.active_services = len([s for s in all_services if s.get("active") == "active"])

                    failed = g.systemctl_list_failed()
                    profile.failed_services = len(failed)

                    timing = g.systemd_analyze_time()
                    if timing:
                        profile.boot_time_seconds = timing.get("total", 0.0)
                except Exception:
                    pass

            # Calculate complexity score
            profile.complexity_score = self._calculate_complexity(profile)

        finally:
            g.shutdown()

        print("✓")
        return profile

    def _calculate_complexity(self, profile: VMProfile) -> int:
        """
        Calculate migration complexity score (0-100).

        Higher score = more complex migration

        Args:
            profile: VM profile

        Returns:
            Complexity score (0-100)
        """
        score = 0

        # Base complexity from OS type
        if profile.os_type == "windows":
            score += 30  # Windows migrations are more complex
        elif profile.os_type == "linux":
            score += 10

        # Filesystem complexity
        if "btrfs" in profile.filesystem_types:
            score += 15  # Btrfs subvolumes add complexity
        if "zfs" in profile.filesystem_types:
            score += 20  # ZFS is complex
        if "lvm" in profile.filesystem_types:
            score += 10  # LVM adds complexity

        score += min(profile.filesystem_count * 2, 20)  # More filesystems = more complex

        # Disk usage
        if profile.usage_percent > 80:
            score += 15  # High usage = potential issues

        # Services
        if profile.total_services > 100:
            score += 10
        if profile.failed_services > 0:
            score += 5 * min(profile.failed_services, 4)

        # Boot time
        if profile.boot_time_seconds > 60:
            score += 10  # Slow boot may indicate issues

        # Mount complexity
        if len(profile.mountpoints) > 5:
            score += 5

        return min(score, 100)

    def analyze_all(self):
        """Analyze all VMs and build profiles."""
        print(f"\nAnalyzing {len(self.disk_images)} VM(s)...\n")

        for disk_image in self.disk_images:
            try:
                profile = self.analyze_vm(disk_image)
                self.profiles.append(profile)
            except Exception as e:
                print(f"✗ Error: {e}")

        print(f"\n✓ Analysis complete: {len(self.profiles)}/{len(self.disk_images)} successful\n")

    def print_comparison_table(self):
        """Print comparison table to console."""
        if not self.profiles:
            print("No VMs analyzed")
            return

        print(f"{'=' * 120}")
        print(f" VM COMPARISON SUMMARY")
        print(f"{'=' * 120}\n")

        # Header
        print(
            f"{'VM Name':<20s} {'OS':<25s} {'Version':<10s} {'Root FS':<10s} "
            f"{'Disk GB':<10s} {'Usage':<8s} {'Services':<10s} {'Complexity':<10s}"
        )
        print(f"{'-' * 120}")

        # Rows
        for p in self.profiles:
            os_display = f"{p.os_distro}"[:24]
            services_display = f"{p.active_services}/{p.total_services}" if p.total_services > 0 else "N/A"

            complexity_label = self._complexity_label(p.complexity_score)

            print(
                f"{p.name:<20s} "
                f"{os_display:<25s} "
                f"{p.os_version:<10s} "
                f"{p.root_filesystem:<10s} "
                f"{p.total_disk_gb:>8.1f} GB "
                f"{p.usage_percent:>6.1f}% "
                f"{services_display:<10s} "
                f"{complexity_label}"
            )

        print(f"{'-' * 120}\n")

        # Detailed breakdown
        self._print_detailed_breakdown()

    def _complexity_label(self, score: int) -> str:
        """Get complexity label with color indicator."""
        if score < 30:
            return f"Low ({score})"
        elif score < 60:
            return f"Medium ({score})"
        else:
            return f"High ({score})"

    def _print_detailed_breakdown(self):
        """Print detailed comparison breakdown."""
        print(f"{'=' * 120}")
        print(f" DETAILED BREAKDOWN")
        print(f"{'=' * 120}\n")

        # OS Distribution
        print("OS Distribution:")
        os_counts = {}
        for p in self.profiles:
            key = f"{p.os_type}/{p.os_distro}"
            os_counts[key] = os_counts.get(key, 0) + 1

        for os_type, count in sorted(os_counts.items(), key=lambda x: -x[1]):
            print(f"  {os_type:30s}: {count} VM(s)")

        # Filesystem Types
        print("\nFilesystem Types:")
        fs_counts = {}
        for p in self.profiles:
            for fs in p.filesystem_types:
                fs_counts[fs] = fs_counts.get(fs, 0) + 1

        for fs_type, count in sorted(fs_counts.items(), key=lambda x: -x[1]):
            print(f"  {fs_type:30s}: {count} VM(s)")

        # Disk Usage Statistics
        print("\nDisk Usage Statistics:")
        if self.profiles:
            total_disk = sum(p.total_disk_gb for p in self.profiles)
            total_used = sum(p.used_disk_gb for p in self.profiles)
            avg_usage = sum(p.usage_percent for p in self.profiles) / len(self.profiles)

            print(f"  Total disk space:   {total_disk:.1f} GB")
            print(f"  Total used space:   {total_used:.1f} GB")
            print(f"  Average usage:      {avg_usage:.1f}%")

        # Service Statistics (Linux VMs)
        linux_vms = [p for p in self.profiles if p.os_type == "linux"]
        if linux_vms:
            print("\nSystemd Service Statistics (Linux VMs):")
            total_services = sum(p.total_services for p in linux_vms)
            total_active = sum(p.active_services for p in linux_vms)
            total_failed = sum(p.failed_services for p in linux_vms)

            print(f"  Total services:     {total_services}")
            print(f"  Active services:    {total_active}")
            print(f"  Failed services:    {total_failed}")

            if total_failed > 0:
                print(f"\n  ⚠️  {total_failed} failed service(s) detected across VMs")

    def print_migration_recommendations(self):
        """Print migration priority recommendations."""
        print(f"\n{'=' * 120}")
        print(f" MIGRATION RECOMMENDATIONS")
        print(f"{'=' * 120}\n")

        # Sort by complexity (easiest first)
        sorted_profiles = sorted(self.profiles, key=lambda p: p.complexity_score)

        print("Recommended Migration Order (easiest to hardest):\n")

        for i, p in enumerate(sorted_profiles, 1):
            complexity = self._complexity_label(p.complexity_score)
            issues = []

            if p.failed_services > 0:
                issues.append(f"{p.failed_services} failed service(s)")
            if p.usage_percent > 80:
                issues.append(f"high disk usage ({p.usage_percent:.0f}%)")
            if "btrfs" in p.filesystem_types or "zfs" in p.filesystem_types:
                issues.append("complex filesystem")

            issues_str = ", ".join(issues) if issues else "no issues"

            print(f"{i}. {p.name:<20s} - {complexity:<15s} - {issues_str}")

        # High-risk VMs
        high_risk = [p for p in self.profiles if p.complexity_score >= 60]
        if high_risk:
            print(f"\n⚠️  High Complexity VMs ({len(high_risk)}):")
            for p in high_risk:
                print(f"  - {p.name}: Review carefully before migration")

        # Quick wins
        quick_wins = [p for p in self.profiles if p.complexity_score < 30]
        if quick_wins:
            print(f"\n✓ Quick Win VMs ({len(quick_wins)}):")
            for p in quick_wins:
                print(f"  - {p.name}: Low complexity, good migration candidate")

    def save_report(self, output_file: Path, format: str = "json"):
        """
        Save comparison report to file.

        Args:
            output_file: Output file path
            format: Output format ('json' or 'html')
        """
        if format == "json":
            self._save_json_report(output_file)
        elif format == "html":
            self._save_html_report(output_file)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _save_json_report(self, output_file: Path):
        """Save JSON report."""
        import json

        report = {
            "comparison_timestamp": datetime.now().isoformat(),
            "vm_count": len(self.profiles),
            "profiles": [
                {
                    "name": p.name,
                    "path": str(p.path),
                    "size_gb": p.size_gb,
                    "os": {
                        "type": p.os_type,
                        "distro": p.os_distro,
                        "product": p.os_product,
                        "version": p.os_version,
                        "arch": p.os_arch,
                    },
                    "filesystem": {
                        "count": p.filesystem_count,
                        "types": p.filesystem_types,
                        "root": p.root_filesystem,
                    },
                    "disk_usage": {
                        "total_gb": p.total_disk_gb,
                        "used_gb": p.used_disk_gb,
                        "percent": p.usage_percent,
                    },
                    "services": {
                        "total": p.total_services,
                        "active": p.active_services,
                        "failed": p.failed_services,
                        "boot_time_seconds": p.boot_time_seconds,
                    },
                    "complexity_score": p.complexity_score,
                }
                for p in self.profiles
            ],
        }

        output_file.write_text(json.dumps(report, indent=2))
        print(f"\n✓ JSON report saved: {output_file}")

    def _save_html_report(self, output_file: Path):
        """Save HTML report."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>VM Comparison Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #ff6600; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th {{ background-color: #ff6600; color: white; padding: 10px; text-align: left; }}
        td {{ border: 1px solid #ddd; padding: 8px; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .complexity-low {{ color: green; font-weight: bold; }}
        .complexity-medium {{ color: orange; font-weight: bold; }}
        .complexity-high {{ color: red; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>VM Comparison Report</h1>
    <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>Total VMs: {len(self.profiles)}</p>

    <h2>Comparison Table</h2>
    <table>
        <tr>
            <th>VM Name</th>
            <th>OS</th>
            <th>Version</th>
            <th>Root FS</th>
            <th>Disk (GB)</th>
            <th>Usage</th>
            <th>Services</th>
            <th>Complexity</th>
        </tr>
"""

        for p in self.profiles:
            services = f"{p.active_services}/{p.total_services}" if p.total_services > 0 else "N/A"
            complexity_class = (
                "low" if p.complexity_score < 30 else ("medium" if p.complexity_score < 60 else "high")
            )
            complexity_label = self._complexity_label(p.complexity_score)

            html += f"""        <tr>
            <td>{p.name}</td>
            <td>{p.os_distro}</td>
            <td>{p.os_version}</td>
            <td>{p.root_filesystem}</td>
            <td>{p.total_disk_gb:.1f}</td>
            <td>{p.usage_percent:.1f}%</td>
            <td>{services}</td>
            <td class="complexity-{complexity_class}">{complexity_label}</td>
        </tr>
"""

        html += """    </table>
</body>
</html>
"""

        output_file.write_text(html)
        print(f"\n✓ HTML report saved: {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare multiple VM disk images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("disk_images", nargs="+", type=Path, help="Paths to disk images to compare")
    parser.add_argument("-o", "--output", type=Path, help="Output file for comparison report")
    parser.add_argument(
        "-f", "--format", choices=["json", "html"], default="json", help="Output format (default: json)"
    )

    args = parser.parse_args()

    # Validate inputs
    invalid = [img for img in args.disk_images if not img.exists()]
    if invalid:
        print(f"Error: Disk images not found:")
        for img in invalid:
            print(f"  - {img}")
        sys.exit(1)

    # Run comparison
    comparator = VMComparator(args.disk_images)
    comparator.analyze_all()
    comparator.print_comparison_table()
    comparator.print_migration_recommendations()

    # Save report if requested
    if args.output:
        comparator.save_report(args.output, args.format)


if __name__ == "__main__":
    main()
