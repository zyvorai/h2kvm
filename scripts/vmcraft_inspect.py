#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMCraft Comprehensive Guest Inspector

Showcases all VMCraft enhanced features:
- Enhanced OS detection (Windows NT-12, all major Linux distros)
- Container detection (Docker, Podman, LXC, systemd-nspawn)
- Bootloader detection (GRUB2, systemd-boot, UEFI, LILO)
- SELinux/AppArmor detection
- Package management (RPM, APT, Pacman)
- Windows user management (SAM registry parsing)
- Linux systemd service management
- Performance metrics and cache statistics

Usage:
    sudo python vmcraft_inspect.py <image_path>
    sudo python vmcraft_inspect.py <image_path> --format vmdk
    sudo python vmcraft_inspect.py <image_path> --show-all
"""

import sys
import argparse
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft import VMCraft

# Orange theme colors
ORANGE = "\033[38;5;208m"
BRIGHT_ORANGE = "\033[38;5;214m"
GREEN = "\033[38;5;46m"
BLUE = "\033[38;5;39m"
YELLOW = "\033[38;5;226m"
RED = "\033[38;5;196m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def supports_color() -> bool:
    """Check if terminal supports ANSI colors."""
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    return True


USE_COLOR = supports_color()


def orange(text):
    return f"{ORANGE}{text}{RESET}" if USE_COLOR else text


def bright_orange(text):
    return f"{BRIGHT_ORANGE}{text}{RESET}" if USE_COLOR else text


def bold_orange(text):
    return f"{BOLD}{ORANGE}{text}{RESET}" if USE_COLOR else text


def green(text):
    return f"{GREEN}{text}{RESET}" if USE_COLOR else text


def blue(text):
    return f"{BLUE}{text}{RESET}" if USE_COLOR else text


def yellow(text):
    return f"{YELLOW}{text}{RESET}" if USE_COLOR else text


def red(text):
    return f"{RED}{text}{RESET}" if USE_COLOR else text


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def print_section(title: str):
    """Print section header."""
    print(f"\n{orange('=' * 80)}")
    print(f"  {bold_orange(title)}")
    print(f"{orange('=' * 80)}\n")


def inspect_vm(image_path: Path, args):
    """Inspect VM disk image with VMCraft."""

    print_section(f"🚀 VMCraft Comprehensive Inspector")
    print(f"Image: {blue(str(image_path))}")
    print(f"Format: {args.format}")
    print()

    # Initialize VMCraft
    g = VMCraft(python_return_dict=True)

    try:
        # Phase 1: Launch
        print(bold_orange("Phase 1: Launching VMCraft"))
        print(f"  Adding drive: {image_path}")
        g.add_drive_opts(str(image_path), readonly=True, format=args.format)

        print("  Connecting NBD and activating storage...")
        g.launch()
        print(green("  ✓ Launched successfully\n"))

        # Phase 2: OS Detection
        print(bold_orange("Phase 2: OS Detection & Inspection"))
        roots = g.inspect_os()

        if not roots:
            print(red("  ❌ No operating systems detected"))
            return 1

        print(green(f"  ✓ Found {len(roots)} operating system(s)\n"))

        for idx, root in enumerate(roots, 1):
            print(orange(f"--- Operating System #{idx} ---"))
            print(f"  Root device: {root}")

            # Basic OS info
            os_type = g.inspect_get_type(root)
            product = g.inspect_get_product_name(root)
            distro = g.inspect_get_distro(root)
            arch = g.inspect_get_arch(root)
            major = g.inspect_get_major_version(root)
            minor = g.inspect_get_minor_version(root)

            emoji = "🪟" if os_type == "windows" else "🐧" if os_type == "linux" else "❓"
            print(f"  Type: {emoji} {os_type}")
            print(f"  Product: {product}")
            print(f"  Distribution: {distro}")
            print(f"  Version: {major}.{minor}")
            print(f"  Architecture: {arch}")
            print()

            # Mount filesystem
            mountpoints = g.inspect_get_mountpoints(root)
            if mountpoints:
                print(bold_orange(f"Mounting {len(mountpoints)} filesystem(s)"))
                for mp, dev in sorted(mountpoints.items()):
                    try:
                        g.mount_ro(dev, mp)
                        print(green(f"  ✓ Mounted {dev} at {mp}"))
                    except Exception as e:
                        print(yellow(f"  ⚠ Could not mount {dev} at {mp}: {e}"))
                print()

            # Phase 3: Enhanced Detection Features
            if args.show_containers or args.show_all:
                print_section("🐳 Container Detection")
                try:
                    containers = g.detect_containers()
                    print(f"  Is Container: {containers['is_container']}")
                    print(f"  Container Type: {containers.get('container_type', 'None')}")
                    print(f"\n  Indicators:")
                    for tech, detected in containers["indicators"].items():
                        status = green("✓") if detected else red("✗")
                        print(f"    {status} {tech}: {detected}")
                except Exception as e:
                    print(yellow(f"  ⚠ Container detection failed: {e}"))

            if args.show_bootloader or args.show_all:
                print_section("🥾 Bootloader Detection")
                try:
                    bootloader = g.detect_bootloader()
                    print(f"  Bootloader: {bootloader.get('bootloader', 'unknown')}")
                    print(f"  Is UEFI: {bootloader.get('is_uefi', False)}")
                    print(f"  Config Path: {bootloader.get('config_path', 'N/A')}")

                    entries = bootloader.get("entries", [])
                    if entries:
                        print(f"\n  Boot Entries ({len(entries)}):")
                        for entry in entries[:10]:
                            print(f"    - {entry.get('title', 'Unknown')}")
                            if entry.get("kernel"):
                                print(f"      Kernel: {entry['kernel']}")
                except Exception as e:
                    print(yellow(f"  ⚠ Bootloader detection failed: {e}"))

            # Phase 4: Security Analysis
            if args.show_security or args.show_all:
                print_section("🔒 Security Analysis")

                # SELinux
                try:
                    selinux = g.detect_selinux()
                    print(bold_orange("SELinux:"))
                    print(f"  Enabled: {selinux.get('enabled', False)}")
                    if selinux.get("enabled"):
                        print(f"  Mode: {selinux.get('mode', 'unknown')}")
                        print(f"  Policy: {selinux.get('policy', 'unknown')}")
                except Exception as e:
                    print(yellow(f"  ⚠ SELinux detection failed: {e}"))

                print()

                # AppArmor
                try:
                    apparmor = g.detect_apparmor()
                    print(bold_orange("AppArmor:"))
                    print(f"  Enabled: {apparmor.get('enabled', False)}")
                    if apparmor.get("enabled"):
                        print(f"  Profiles Loaded: {apparmor.get('profiles_loaded', 0)}")
                except Exception as e:
                    print(yellow(f"  ⚠ AppArmor detection failed: {e}"))

            # Phase 5: Package Management
            if args.show_packages or args.show_all:
                print_section("📦 Package Management")
                try:
                    packages = g.list_installed_packages(limit=20)
                    if isinstance(packages, dict):
                        print(f"  Package Manager: {packages.get('package_manager', 'unknown')}")
                        print(f"  Total Packages: {packages.get('total_count', 0)}")

                        pkg_list = packages.get("packages", [])
                        if pkg_list:
                            print(f"\n  Sample Packages (showing {min(20, len(pkg_list))}):")
                            for pkg in pkg_list[:20]:
                                pkg_str = f"    - {pkg['name']}"
                                if pkg.get("version"):
                                    pkg_str += f" ({pkg['version']})"
                                if pkg.get("arch"):
                                    pkg_str += f" [{pkg['arch']}]"
                                print(pkg_str)

                            if packages.get("total_count", 0) > 20:
                                print(f"    ... and {packages['total_count'] - 20} more")
                    else:
                        print(yellow("  ⚠ Package manager not detected"))
                except Exception as e:
                    print(yellow(f"  ⚠ Package listing failed: {e}"))

            # Phase 6: Windows-Specific Features
            if os_type == "windows" and (args.show_windows or args.show_all):
                print_section("🪟 Windows Analysis")

                # Windows Registry
                print(bold_orange("Registry Information:"))
                try:
                    product = g.win_registry_read(
                        "SOFTWARE", r"Microsoft\Windows NT\CurrentVersion", "ProductName"
                    )
                    build = g.win_registry_read(
                        "SOFTWARE", r"Microsoft\Windows NT\CurrentVersion", "CurrentBuild"
                    )
                    edition = g.win_registry_read(
                        "SOFTWARE", r"Microsoft\Windows NT\CurrentVersion", "EditionID"
                    )

                    print(f"  ProductName: {product or 'N/A'}")
                    print(f"  CurrentBuild: {build or 'N/A'}")
                    print(f"  EditionID: {edition or 'N/A'}")
                except Exception as e:
                    print(yellow(f"  ⚠ Registry read failed: {e}"))

                print()

                # Windows Users
                print(bold_orange("User Accounts:"))
                try:
                    users = g.win_list_users()
                    print(f"  Found {len(users)} user(s):")
                    for user in users[:20]:
                        status = red("(DISABLED)") if user.get("disabled") else green("(ENABLED)")
                        print(f"    - {user['username']} {status}")
                        print(f"      RID: {user.get('rid', 'N/A')}")

                    if len(users) > 20:
                        print(f"    ... and {len(users) - 20} more")

                    # Admin check
                    print()
                    admins = g.win_list_administrators()
                    print(f"  Administrators ({len(admins)}):")
                    for admin in admins[:10]:
                        print(f"    - {admin}")

                    # User statistics
                    print()
                    stats = g.win_get_user_count()
                    print(bold_orange("User Statistics:"))
                    print(f"  Total: {stats.get('total', 0)}")
                    print(f"  Enabled: {stats.get('enabled', 0)}")
                    print(f"  Disabled: {stats.get('disabled', 0)}")
                    print(f"  Administrators: {stats.get('administrators', 0)}")
                except Exception as e:
                    print(yellow(f"  ⚠ User enumeration failed: {e}"))

            # Phase 7: Linux-Specific Features
            if os_type == "linux" and (args.show_services or args.show_all):
                print_section("⚙️ Linux Services (systemd)")
                try:
                    # Boot services
                    boot_services = g.linux_get_boot_services()
                    print(bold_orange(f"Boot Services ({len(boot_services)} found):"))
                    for svc in boot_services[:15]:
                        print(f"  - {svc['name']} (target: {svc.get('target', 'N/A')})")
                    if len(boot_services) > 15:
                        print(f"  ... and {len(boot_services) - 15} more")

                    print()

                    # Enabled services
                    enabled = g.linux_list_enabled_services()
                    print(bold_orange(f"Enabled Services ({len(enabled)} found):"))
                    for svc in enabled[:20]:
                        print(f"  - {svc}")
                    if len(enabled) > 20:
                        print(f"  ... and {len(enabled) - 20} more")
                except Exception as e:
                    print(yellow(f"  ⚠ Service enumeration failed: {e}"))

            # Phase 8: Filesystem Information
            if args.show_filesystems or args.show_all:
                print_section("💾 Filesystems & Partitions")
                try:
                    filesystems = g.list_filesystems()
                    partitions = g.list_partitions()

                    print(bold_orange(f"Partitions ({len(partitions)} found):"))
                    for part in partitions:
                        print(f"  {part}")

                    print()
                    print(bold_orange(f"Filesystems ({len(filesystems)} devices):"))
                    for dev, fstype in list(filesystems.items())[:20]:
                        if "nbd" in dev or "loop" not in dev:
                            print(f"  {dev}: {fstype}")
                except Exception as e:
                    print(yellow(f"  ⚠ Filesystem listing failed: {e}"))

        # Phase 9: Performance Metrics
        if args.show_performance or args.show_all:
            print_section("⚡ Performance Metrics")
            try:
                metrics = g.get_performance_metrics()
                print(bold_orange("Timing:"))
                print(f"  Launch Time: {metrics.get('launch_time_s', 0):.2f}s")
                print(f"  NBD Connect Time: {metrics.get('nbd_connect_time_s', 0):.2f}s")
                print(f"  Storage Activation Time: {metrics.get('storage_activation_time_s', 0):.2f}s")

                ops = metrics.get("operations", {})
                print(f"\n{bold_orange('Operations:')}")
                print(f"  Mounts: {ops.get('mounts', 0)}")
                print(f"  File Reads: {ops.get('file_reads', 0)}")
                print(f"  File Writes: {ops.get('file_writes', 0)}")
                print(f"  Registry Reads: {ops.get('registry_reads', 0)}")

                print(f"\n{bold_orange('Memory:')}")
                print(f"  Estimate: {metrics.get('memory_estimate_mb', 0):.1f} MB")
            except Exception as e:
                print(yellow(f"  ⚠ Performance metrics failed: {e}"))

            print_section("📊 Cache Statistics")
            try:
                cache_stats = g.get_cache_stats()
                print(f"  Total Hit Rate: {cache_stats.get('total_hit_rate', 0) * 100:.1f}%")

                meta = cache_stats.get("metadata_cache", {})
                print(f"\n{bold_orange('Metadata Cache:')}")
                print(f"  Hits: {meta.get('hits', 0)}")
                print(f"  Misses: {meta.get('misses', 0)}")
                print(f"  Size: {meta.get('size', 0)} entries")
                print(f"  Hit Rate: {meta.get('hit_rate', 0) * 100:.1f}%")

                dirr = cache_stats.get("directory_cache", {})
                print(f"\n{bold_orange('Directory Cache:')}")
                print(f"  Hits: {dirr.get('hits', 0)}")
                print(f"  Misses: {dirr.get('misses', 0)}")
                print(f"  Size: {dirr.get('size', 0)} entries")
                print(f"  Hit Rate: {dirr.get('hit_rate', 0) * 100:.1f}%")
            except Exception as e:
                print(yellow(f"  ⚠ Cache statistics failed: {e}"))

        # Cleanup
        print_section("🧹 Cleanup")
        print("  Unmounting filesystems...")
        g.umount_all()
        print(green("  ✓ Unmounted"))

        print("  Shutting down...")
        g.shutdown()
        print(green("  ✓ Shutdown complete"))

        print_section("✅ Inspection Complete")
        return 0

    except Exception as e:
        print(f"\n{red('❌ Error during inspection:')} {e}")
        if args.debug:
            import traceback

            traceback.print_exc()
        return 1

    finally:
        try:
            g.umount_all()
        except Exception:
            pass
        try:
            g.shutdown()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="VMCraft Comprehensive Guest Inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo %(prog)s /path/to/disk.qcow2
  sudo %(prog)s /path/to/disk.vmdk --format vmdk
  sudo %(prog)s /path/to/disk.qcow2 --show-all
  sudo %(prog)s /path/to/disk.qcow2 --show-containers --show-bootloader

VMCraft Features Showcased:
  - Enhanced OS detection (Windows NT-12, all major Linux distros)
  - Container detection (Docker, Podman, LXC, systemd-nspawn)
  - Bootloader detection (GRUB2, systemd-boot, UEFI, LILO)
  - SELinux/AppArmor detection
  - Package management (RPM, APT, Pacman)
  - Windows user management (SAM registry parsing)
  - Linux systemd service management
  - Performance metrics and cache statistics

Performance:
  - 5-10x faster than appliance-based inspection
  - NBD-based architecture
  - LRU caching for repeated operations

Requires:
  - sudo privileges (for NBD device access)
  - qemu-utils (provides qemu-nbd)
  - ntfs-3g (for Windows NTFS support)
  - hivex (for Windows registry parsing)
        """,
    )

    parser.add_argument("image", type=Path, help="Path to disk image (qcow2, raw, vmdk, vdi, etc.)")

    parser.add_argument("--format", default="qcow2", help="Disk image format (default: qcow2)")

    parser.add_argument("--show-all", action="store_true", help="Show all available information")

    parser.add_argument(
        "--show-containers",
        action="store_true",
        help="Show container detection (Docker, Podman, LXC, systemd-nspawn)",
    )

    parser.add_argument(
        "--show-bootloader",
        action="store_true",
        help="Show bootloader detection (GRUB2, systemd-boot, UEFI, LILO)",
    )

    parser.add_argument(
        "--show-security", action="store_true", help="Show security module detection (SELinux, AppArmor)"
    )

    parser.add_argument(
        "--show-packages", action="store_true", help="Show installed packages (RPM, APT, Pacman)"
    )

    parser.add_argument(
        "--show-windows", action="store_true", help="Show Windows-specific info (registry, users)"
    )

    parser.add_argument("--show-services", action="store_true", help="Show Linux systemd services")

    parser.add_argument("--show-filesystems", action="store_true", help="Show filesystems and partitions")

    parser.add_argument(
        "--show-performance", action="store_true", help="Show performance metrics and cache statistics"
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Check image exists
    if not args.image.exists():
        print(f"{red('❌ Error:')} Image not found: {args.image}")
        return 1

    # Run inspection
    return inspect_vm(args.image, args)


if __name__ == "__main__":
    sys.exit(main())
