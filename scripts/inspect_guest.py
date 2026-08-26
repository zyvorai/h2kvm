#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Comprehensive guest image inspector.

Mounts disk images and extracts detailed information including:
- OS details and version
- Network interfaces with MAC addresses
- IP configuration
- Installed packages
- Systemd services
- User accounts
- SSH keys
- Disk usage
- And more!

Usage:
    python inspect_guest.py <image_path>
    python inspect_guest.py <image_path> --no-packages
    python inspect_guest.py <image_path> --network-only
"""

import sys
import argparse
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.core.guest_inspector import (
    ComprehensiveGuestInspector,
    GUESTFS_AVAILABLE,
)

# Orange theme colors (matching TUI dashboard)
ORANGE = "\033[38;5;208m"  # Orange
BRIGHT_ORANGE = "\033[38;5;214m"  # Bright orange
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def supports_color() -> bool:
    """Check if terminal supports ANSI colors."""
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            h_stdout = kernel32.GetStdHandle(-11)
            console_mode = ctypes.c_ulong()
            if not kernel32.GetConsoleMode(h_stdout, ctypes.byref(console_mode)):
                return False
            return True
        except Exception:
            return False
    return True


USE_COLOR = supports_color()


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def print_result(result, args):
    """Print inspection result in a nice format."""

    # Color helpers
    def orange(text):
        return f"{ORANGE}{text}{RESET}" if USE_COLOR else text

    def bright_orange(text):
        return f"{BRIGHT_ORANGE}{text}{RESET}" if USE_COLOR else text

    def bold_orange(text):
        return f"{BOLD}{ORANGE}{text}{RESET}" if USE_COLOR else text

    print(orange("=" * 80))
    print(bold_orange(f"📀 Disk Image: {args.image}"))
    print(orange("=" * 80))
    print()

    if not result.identity:
        print("❌ Could not detect operating system")
        return

    # OS Information
    print(bright_orange("✓ Operating System Detected"))
    print()

    identity = result.identity

    # OS Type and Distribution
    print(bold_orange(f"OS Information"))
    print(orange("─" * 80))
    print(f"  Type: {_get_os_emoji(identity.type.value)} {identity.type.value}")

    if identity.os_pretty_name:
        print(f"  Distribution: {identity.os_pretty_name}")
    elif identity.os_name:
        print(f"  Distribution: {identity.os_name}")
    else:
        print(f"  Distribution: unknown")

    if identity.os_version:
        print(f"  Version: {identity.os_version}")

    if result.hostname:
        print(f"  Hostname: {result.hostname}")
    elif identity.hostname:
        print(f"  Hostname: {identity.hostname}")

    if identity.architecture:
        print(f"  Architecture: {identity.architecture}")

    if identity.kernel_version:
        print(f"  Kernel: {identity.kernel_version}")

    if identity.machine_id:
        print(f"  Machine ID: {identity.machine_id}")

    if result.timezone:
        print(f"  Timezone: {result.timezone}")

    if result.locale:
        print(f"  Locale: {result.locale}")

    print()

    # Network Information
    if result.network_interfaces:
        print(bold_orange(f"Network Interfaces ({len(result.network_interfaces)} found)"))
        print(orange("─" * 80))

        for iface in result.network_interfaces:
            print(f"  Interface: {iface.name}")
            if iface.mac_address:
                print(f"    MAC Address: {iface.mac_address}")
            if iface.type:
                print(f"    Type: {iface.type}")
            if iface.driver:
                print(f"    Driver: {iface.driver}")
            if iface.mtu:
                print(f"    MTU: {iface.mtu}")
            if iface.ip_addresses:
                print(f"    IP Addresses: {', '.join(iface.ip_addresses)}")
            print()

    if result.dns_servers:
        print(bold_orange(f"DNS Servers"))
        print(orange("─" * 80))
        for dns in result.dns_servers:
            print(f"  {dns}")
        print()

    # Package Information
    if args.package_info and result.package_format:
        print(bold_orange(f"Package Information"))
        print(orange("─" * 80))
        print(f"  Package Format: {result.package_format}")
        print(f"  Package Count: {result.package_count}")

        if result.installed_packages:
            print(f"  Sample Packages (showing first {min(20, len(result.installed_packages))}):")
            for pkg in result.installed_packages[:20]:
                pkg_str = f"    - {pkg.name}"
                if pkg.version:
                    pkg_str += f" ({pkg.version})"
                if pkg.architecture:
                    pkg_str += f" [{pkg.architecture}]"
                print(pkg_str)

            if len(result.installed_packages) > 20:
                print(f"    ... and {len(result.installed_packages) - 20} more")

        print()

    # Service Information
    if args.service_info and result.systemd_services:
        print(bold_orange(f"Systemd Services ({len(result.systemd_services)} enabled)"))
        print(orange("─" * 80))

        for svc in result.systemd_services[:30]:
            status = "✓ enabled" if svc.enabled else "✗ disabled"
            print(f"  {svc.name:40} {status}")

        if len(result.systemd_services) > 30:
            print(f"  ... and {len(result.systemd_services) - 30} more")

        print()

    # User Information
    if args.user_info and result.user_accounts:
        print(bold_orange(f"User Accounts ({len(result.user_accounts)} found)"))
        print(orange("─" * 80))

        for user in result.user_accounts:
            user_str = f"  {user.username:20}"
            if user.uid is not None:
                user_str += f" UID:{user.uid:5}"
            if user.home:
                user_str += f" Home:{user.home:30}"
            if user.shell:
                user_str += f" Shell:{user.shell}"
            print(user_str)

        print()

    # SSH Information
    if args.ssh_info:
        if result.ssh_authorized_keys:
            print(bold_orange(f"SSH Authorized Keys"))
            print(orange("─" * 80))
            for username, keys in result.ssh_authorized_keys.items():
                print(f"  User: {username}")
                for key in keys:
                    key_type = key.split()[0] if key.split() else "unknown"
                    key_preview = key[:60] + "..." if len(key) > 60 else key
                    print(f"    {key_type}: {key_preview}")
            print()

        if result.ssh_host_keys:
            print(bold_orange(f"SSH Host Keys"))
            print(orange("─" * 80))
            for host_key in result.ssh_host_keys:
                print(f"  {host_key}")
            print()

    # Disk Usage
    if args.disk_info and result.disk_usage:
        print(bold_orange(f"Disk Usage"))
        print(orange("─" * 80))

        for disk in result.disk_usage:
            print(f"  Filesystem: {disk.filesystem}")
            print(f"    Size: {format_bytes(disk.size_bytes)}")
            print(f"    Used: {format_bytes(disk.used_bytes)} ({disk.use_percent:.1f}%)")
            print(f"    Available: {format_bytes(disk.available_bytes)}")
            print()

    # Additional Information
    if result.kernel_modules and args.verbose:
        print(bold_orange(f"Loaded Kernel Modules (sample)"))
        print(orange("─" * 80))
        for mod in result.kernel_modules[:20]:
            print(f"  {mod}")
        if len(result.kernel_modules) > 20:
            print(f"  ... and {len(result.kernel_modules) - 20} more")
        print()

    if result.boot_parameters and args.verbose:
        print(bold_orange(f"Kernel Boot Parameters"))
        print(orange("─" * 80))
        print(f"  {result.boot_parameters}")
        print()

    # Partitions and Filesystems
    if result.partitions and args.verbose:
        print(bold_orange(f"Partitions ({len(result.partitions)} found)"))
        print(orange("─" * 80))
        for part in result.partitions:
            print(f"  Device: {part.device}")
            if part.number is not None:
                print(f"    Partition #: {part.number}")
            if part.size_bytes:
                print(f"    Size: {format_bytes(part.size_bytes)}")
            if part.filesystem_type:
                print(f"    Filesystem: {part.filesystem_type}")
            if part.label:
                print(f"    Label: {part.label}")
            if part.uuid:
                print(f"    UUID: {part.uuid}")
            if part.bootable:
                print(f"    Bootable: Yes")
            print()

    if result.filesystems and args.verbose:
        print(bold_orange(f"Filesystems"))
        print(orange("─" * 80))
        print(f"  Types: {', '.join(result.filesystems)}")
        print()

    # Applications (Windows) or extended packages
    if result.applications and args.verbose:
        print(bold_orange(f"Applications ({len(result.applications)} found)"))
        print(orange("─" * 80))
        for app in result.applications[:20]:
            print(f"  {app.name}")
            if app.version:
                print(f"    Version: {app.version}")
            if app.vendor:
                print(f"    Vendor: {app.vendor}")
            if app.install_location:
                print(f"    Location: {app.install_location}")
            print()
        if len(result.applications) > 20:
            print(f"  ... and {len(result.applications) - 20} more")
            print()

    # Firewall Rules
    if result.firewall_rules and args.verbose:
        print(bold_orange(f"Firewall Rules ({len(result.firewall_rules)} found)"))
        print(orange("─" * 80))
        for rule in result.firewall_rules[:15]:
            status = "✓ enabled" if rule.enabled else "✗ disabled"
            print(f"  {rule.name:50} {status}")
            if rule.direction:
                print(f"    Direction: {rule.direction}")
            if rule.action:
                print(f"    Action: {rule.action}")
            if rule.protocol:
                print(f"    Protocol: {rule.protocol}")
            if rule.port:
                print(f"    Port: {rule.port}")
        if len(result.firewall_rules) > 15:
            print(f"  ... and {len(result.firewall_rules) - 15} more")
        print()

    # Scheduled Tasks / Cron Jobs
    if result.scheduled_tasks and args.verbose:
        print(bold_orange(f"Scheduled Tasks ({len(result.scheduled_tasks)} found)"))
        print(orange("─" * 80))
        for task in result.scheduled_tasks[:10]:
            print(f"  {task.name}")
            if task.schedule:
                print(f"    Schedule: {task.schedule}")
            if task.user:
                print(f"    User: {task.user}")
            if task.command:
                cmd_display = task.command[:60] + "..." if len(task.command) > 60 else task.command
                print(f"    Command: {cmd_display}")
            print()
        if len(result.scheduled_tasks) > 10:
            print(f"  ... and {len(result.scheduled_tasks) - 10} more")
            print()

    # SELinux (Linux only)
    if result.selinux_status and args.verbose:
        print(bold_orange(f"SELinux Status"))
        print(orange("─" * 80))
        print(f"  Status: {result.selinux_status}")
        print()

    # Environment Variables
    if result.environment_variables and args.verbose:
        print(bold_orange(f"Environment Variables ({len(result.environment_variables)} found)"))
        print(orange("─" * 80))
        for key, value in list(result.environment_variables.items())[:10]:
            print(f"  {key}={value}")
        if len(result.environment_variables) > 10:
            print(f"  ... and {len(result.environment_variables) - 10} more")
        print()

    # Windows-specific info
    if result.windows_product_name:
        print(bold_orange(f"Windows Information"))
        print(orange("─" * 80))
        print(f"  Product: {result.windows_product_name}")
        if result.windows_build_number:
            print(f"  Build: {result.windows_build_number}")
        if result.windows_install_date:
            print(f"  Install Date: {result.windows_install_date}")
        print()

    # Summary
    print(orange("=" * 80))
    print(bright_orange("Inspection Complete"))
    print(orange("=" * 80))


def _get_os_emoji(os_type: str) -> str:
    """Get emoji for OS type."""
    emoji_map = {
        "linux": "🐧",
        "windows": "🪟",
        "bsd": "😈",
        "macos": "🍎",
        "unknown": "❓",
    }
    return emoji_map.get(os_type.lower(), "❓")


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive guest disk image inspector with mounting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/disk.qcow2
  %(prog)s /path/to/disk.qcow2 --no-packages
  %(prog)s /path/to/disk.qcow2 --network-only
  %(prog)s /path/to/disk.qcow2 --verbose

This tool mounts the disk image (read-only) and extracts:
  - OS details and version
  - Network interfaces with MAC addresses
  - IP configuration and DNS servers
  - Installed packages
  - Systemd services
  - User accounts
  - SSH authorized keys and host keys
  - Disk usage
  - Kernel modules and boot parameters
  - Timezone and locale

Requires:
  - python3-guestfs
  - sudo apt install python3-guestfs  (Ubuntu/Debian)
  - sudo dnf install python3-guestfs  (Fedora/RHEL)
        """,
    )

    parser.add_argument("image", type=Path, help="Path to disk image (qcow2, raw, vmdk, etc.)")

    parser.add_argument(
        "--no-network", dest="network_info", action="store_false", help="Skip network interface inspection"
    )

    parser.add_argument(
        "--no-packages", dest="package_info", action="store_false", help="Skip package inspection (faster)"
    )

    parser.add_argument(
        "--no-services", dest="service_info", action="store_false", help="Skip service inspection"
    )

    parser.add_argument(
        "--no-users", dest="user_info", action="store_false", help="Skip user account inspection"
    )

    parser.add_argument("--no-ssh", dest="ssh_info", action="store_false", help="Skip SSH key inspection")

    parser.add_argument(
        "--no-disk", dest="disk_info", action="store_false", help="Skip disk usage inspection"
    )

    parser.add_argument("--network-only", action="store_true", help="Only inspect network information")

    parser.add_argument("--verbose", "-v", action="store_true", help="Show additional verbose information")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Check dependencies
    if not GUESTFS_AVAILABLE:
        print("Error: guestfs Python bindings not available")
        print()
        print("Install with:")
        print("  Ubuntu/Debian: sudo apt install python3-guestfs")
        print("  Fedora/RHEL:   sudo dnf install python3-guestfs")
        print("  Arch:          sudo pacman -S python-guestfs")
        return 1

    # Check image exists
    if not args.image.exists():
        print(f"❌ Error: Image not found: {args.image}")
        return 1

    # Network-only mode
    if args.network_only:
        args.package_info = False
        args.service_info = False
        args.user_info = False
        args.ssh_info = False
        args.disk_info = False

    # Run inspection
    try:
        inspector = ComprehensiveGuestInspector()

        result = inspector.inspect(
            args.image,
            readonly=True,
            network_info=args.network_info,
            package_info=args.package_info,
            service_info=args.service_info,
            user_info=args.user_info,
            ssh_info=args.ssh_info,
            disk_info=args.disk_info,
        )

        print_result(result, args)

        return 0

    except Exception as e:
        print(f"\n❌ Inspection failed: {e}")
        if args.debug:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
