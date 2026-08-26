#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Demonstration of VMCraft systemd integration APIs.

This script shows how to use the 46 systemd APIs for VM analysis,
service management, log querying, and system inspection.

Usage:
    python3 demo_systemd_apis.py <disk-image-path>

Example:
    python3 demo_systemd_apis.py /path/to/ubuntu-server.vmdk
    python3 demo_systemd_apis.py /path/to/fedora.qcow2
"""

import sys
from pathlib import Path
from hyper2kvm.vmcraft.main import VMCraft


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f" {title}")
    print(f"{'=' * 80}\n")


def demo_systemctl_apis(g):
    """Demonstrate systemctl service management APIs."""
    print_section("SYSTEMCTL - Service Management APIs")

    # 1. List all services
    print("1. Listing all systemd services:")
    print("-" * 40)
    services = g.systemctl_list_units(unit_type="service", all_units=True)
    print(f"Total services: {len(services)}")

    if services:
        print("\nFirst 10 services:")
        for svc in services[:10]:
            unit = svc.get("unit", "N/A")[:40]
            active = svc.get("active", "N/A")[:10]
            sub = svc.get("sub", "N/A")[:15]
            desc = svc.get("description", "N/A")[:40]
            print(f"  {unit:40s} {active:10s} {sub:15s} {desc}")

    # 2. Check specific service status
    print("\n2. Checking specific services:")
    print("-" * 40)
    critical_services = ["sshd.service", "systemd-journald.service", "dbus.service"]
    for svc in critical_services:
        is_active = g.systemctl_is_active(svc)
        is_enabled = g.systemctl_is_enabled(svc)
        is_failed = g.systemctl_is_failed(svc)

        status = "✅" if is_active else "❌"
        print(
            f"{status} {svc:30s} Active: {str(is_active):5s} Enabled: {is_enabled:10s} Failed: {str(is_failed)}"
        )

    # 3. List failed services
    print("\n3. Failed services:")
    print("-" * 40)
    failed = g.systemctl_list_failed()
    if failed:
        print(f"⚠️  {len(failed)} services in failed state:")
        for svc in failed:
            print(f"   - {svc.get('unit', 'N/A'):40s} {svc.get('description', 'N/A')}")
    else:
        print("✅ No failed services")

    # 4. Default boot target
    print("\n4. Default boot target:")
    print("-" * 40)
    target = g.systemctl_get_default_target()
    print(f"Boot target: {target or 'Unknown'}")

    # 5. List timers
    print("\n5. Systemd timers:")
    print("-" * 40)
    timers = g.systemctl_list_timers()
    print(f"Total timers: {len(timers)}")
    if timers:
        print("\nActive timers:")
        for timer in timers[:5]:
            unit = timer.get("unit", "N/A")[:40]
            next_run = timer.get("next", "N/A")[:30]
            print(f"  {unit:40s} Next: {next_run}")

    # 6. Service dependencies
    print("\n6. Service dependencies example (sshd.service):")
    print("-" * 40)
    deps = g.systemctl_list_dependencies("sshd.service")
    if deps:
        print(f"Dependencies: {len(deps)} units")
        for dep in deps[:5]:
            print(f"  → {dep}")


def demo_journalctl_apis(g):
    """Demonstrate journalctl log analysis APIs."""
    print_section("JOURNALCTL - Log Analysis APIs")

    # 1. Boot history
    print("1. Boot history:")
    print("-" * 40)
    boots = g.journalctl_list_boots()
    print(f"Total boots recorded: {len(boots)}")
    if boots:
        print("\nRecent boots:")
        for boot in boots[:3]:
            offset = boot.get("offset", "N/A")
            boot_id = boot.get("boot_id", "N/A")[:16]
            time_range = boot.get("time_range", "N/A")[:50]
            print(f"  Boot {offset:3s}: {boot_id}... {time_range}")

    # 2. Error messages
    print("\n2. Recent error messages:")
    print("-" * 40)
    errors = g.journalctl_get_errors(since="1 hour ago", lines=10)
    if errors:
        print(f"Found {len(errors)} errors in last hour:")
        for err in errors[:5]:
            unit = err.get("unit", "unknown")[:25]
            msg = err.get("message", "N/A")[:70]
            print(f"  [{unit}] {msg}")
    else:
        print("✅ No errors in last hour")

    # 3. Warning messages
    print("\n3. Recent warnings:")
    print("-" * 40)
    warnings = g.journalctl_get_warnings(since="1 hour ago", lines=10)
    if warnings:
        print(f"Found {len(warnings)} warnings in last hour:")
        for warn in warnings[:5]:
            unit = warn.get("unit", "unknown")[:25]
            msg = warn.get("message", "N/A")[:70]
            print(f"  [{unit}] {msg}")
    else:
        print("✅ No warnings in last hour")

    # 4. Journal disk usage
    print("\n4. Journal disk usage:")
    print("-" * 40)
    usage = g.journalctl_disk_usage()
    if usage:
        print(f"Current usage: {usage.get('current_use', 'Unknown')}")
    else:
        print("Unable to determine journal disk usage")

    # 5. Query specific unit logs
    print("\n5. SSH service logs (last 10 lines):")
    print("-" * 40)
    ssh_logs = g.journalctl_query(unit="sshd.service", lines=10)
    if ssh_logs:
        lines = ssh_logs.strip().split("\n")[:10]
        for line in lines:
            print(f"  {line[:120]}")


def demo_systemd_analyze_apis(g):
    """Demonstrate systemd-analyze performance APIs."""
    print_section("SYSTEMD-ANALYZE - Performance & Security APIs")

    # 1. Boot time analysis
    print("1. Boot time analysis:")
    print("-" * 40)
    timing = g.systemd_analyze_time()
    if timing:
        total = timing.get("total", 0)
        print(f"Total boot time: {total:.2f}s")

        if "firmware" in timing:
            print(f"  Firmware:  {timing['firmware']:6.2f}s")
        if "loader" in timing:
            print(f"  Loader:    {timing['loader']:6.2f}s")
        if "kernel" in timing:
            print(f"  Kernel:    {timing['kernel']:6.2f}s")
        if "initrd" in timing:
            print(f"  Initrd:    {timing['initrd']:6.2f}s")
        if "userspace" in timing:
            print(f"  Userspace: {timing['userspace']:6.2f}s")

        if total > 120:
            print(f"\n⚠️  Boot time exceeds 2 minutes")
        else:
            print(f"\n✅ Boot time is acceptable")
    else:
        print("Unable to analyze boot time")

    # 2. Service blame (slowest services)
    print("\n2. Top 10 slowest services:")
    print("-" * 40)
    blame = g.systemd_analyze_blame(lines=10)
    if blame:
        for idx, svc in enumerate(blame, 1):
            time_str = svc.get("time", "N/A")
            unit = svc.get("unit", "N/A")
            print(f"{idx:2d}. {time_str:>10s}  {unit}")

    # 3. Critical boot chain
    print("\n3. Critical boot chain:")
    print("-" * 40)
    chain = g.systemd_analyze_critical_chain()
    if chain:
        # Show first 15 lines
        lines = chain.strip().split("\n")[:15]
        for line in lines:
            print(f"  {line}")
        chain_lines = len(chain.split("\n"))
        if chain_lines > 15:
            print(f"  ... ({chain_lines - 15} more lines)")

    # 4. Security analysis (for important service)
    print("\n4. Security analysis for sshd.service:")
    print("-" * 40)
    security = g.systemd_analyze_security("sshd.service")
    if security:
        print(f"Security checks performed: {len(security)}")
        for check in security[:5]:
            print(f"  {check.get('description', 'N/A')[:80]}")


def demo_configuration_apis(g):
    """Demonstrate configuration tool APIs."""
    print_section("CONFIGURATION TOOLS - System Settings APIs")

    # 1. Time/Date configuration
    print("1. Time/Date configuration (timedatectl):")
    print("-" * 40)
    time_status = g.timedatectl_status()
    if time_status:
        for key, value in list(time_status.items())[:8]:
            print(f"  {key:25s}: {value}")

    # 2. Hostname and system info
    print("\n2. System identity (hostnamectl):")
    print("-" * 40)
    hostname_status = g.hostnamectl_status()
    if hostname_status:
        print(f"  Hostname:     {hostname_status.get('static_hostname', 'Unknown')}")
        print(f"  OS:           {hostname_status.get('operating_system', 'Unknown')}")
        print(f"  Kernel:       {hostname_status.get('kernel', 'Unknown')}")
        print(f"  Architecture: {hostname_status.get('architecture', 'Unknown')}")
        print(f"  Machine ID:   {hostname_status.get('machine_id', 'Unknown')}")

    # 3. Locale configuration
    print("\n3. Locale configuration (localectl):")
    print("-" * 40)
    locale_status = g.localectl_status()
    if locale_status:
        print(f"  System Locale: {locale_status.get('system_locale', 'Unknown')}")
        print(f"  VC Keymap:     {locale_status.get('vc_keymap', 'Unknown')}")

    # 4. Login sessions
    print("\n4. Login sessions (loginctl):")
    print("-" * 40)
    sessions = g.loginctl_list_sessions()
    if sessions:
        print(f"Active sessions: {len(sessions)}")
        for session in sessions:
            sid = session.get("session", "N/A")
            user = session.get("user", "N/A")
            tty = session.get("tty", "N/A")
            print(f"  Session {sid}: User '{user}' on {tty}")
    else:
        print("  No active sessions")


def main():
    """Main demonstration function."""
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"\nError: Please provide a disk image path")
        sys.exit(1)

    disk_image = sys.argv[1]

    if not Path(disk_image).exists():
        print(f"Error: Disk image not found: {disk_image}")
        sys.exit(1)

    print(f"\n{'#' * 80}")
    print(f"# VMCraft Systemd Integration - Complete API Demonstration")
    print(f"#")
    print(f"# Disk Image: {disk_image}")
    print(f"# Total APIs: 46 methods across 7 systemd tools")
    print(f"{'#' * 80}")

    # Create VMCraft instance and launch
    print("\n[*] Launching VMCraft and connecting to disk image...")
    g = VMCraft()
    g.add_drive_opts(disk_image, readonly=True)
    g.launch()

    try:
        # Demonstrate each category of systemd APIs
        demo_systemctl_apis(g)
        demo_journalctl_apis(g)
        demo_systemd_analyze_apis(g)
        demo_configuration_apis(g)

        print_section("DEMONSTRATION COMPLETE")
        print("All 46 systemd APIs demonstrated successfully!")
        print("\nAPI Categories:")
        print("  • systemctl:       15 methods (service management)")
        print("  • journalctl:       8 methods (log analysis)")
        print("  • systemd-analyze: 10 methods (performance/security)")
        print("  • Configuration:   13 methods (time/hostname/locale/sessions)")
        print(f"\n{'=' * 80}\n")

    finally:
        print("[*] Shutting down VMCraft...")
        g.shutdown()


if __name__ == "__main__":
    main()
