#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMCraft Systemd API Reference

This demonstrates all 46 systemd APIs and their signatures.
The APIs work with offline disk images but return meaningful data
only when systemd is running in the guest.
"""

from hyper2kvm.vmcraft.main import VMCraft
import inspect


def print_api_reference():
    """Print reference for all systemd APIs."""
    g = VMCraft()

    # Group APIs by category
    categories = {
        "systemctl": {
            "description": "Service Management (15 methods)",
            "methods": [],
        },
        "journalctl": {
            "description": "Log Analysis (8 methods)",
            "methods": [],
        },
        "systemd_analyze": {
            "description": "Performance & Security Analysis (10 methods)",
            "methods": [],
        },
        "timedatectl": {
            "description": "Time/Date Configuration (3 methods)",
            "methods": [],
        },
        "hostnamectl": {
            "description": "Hostname & System Identity (2 methods)",
            "methods": [],
        },
        "localectl": {
            "description": "Locale & Keyboard Configuration (5 methods)",
            "methods": [],
        },
        "loginctl": {
            "description": "Session Management (3 methods)",
            "methods": [],
        },
    }

    # Collect all systemd methods
    for attr in dir(g):
        for cat in categories:
            if attr.startswith(cat + "_"):
                method = getattr(g, attr)
                if callable(method):
                    sig = inspect.signature(method)
                    doc = (method.__doc__ or "").strip().split("\n")[0]
                    categories[cat]["methods"].append(
                        {
                            "name": attr,
                            "signature": str(sig),
                            "doc": doc,
                        }
                    )

    # Print reference
    print("=" * 100)
    print(" VMCraft Systemd Integration - Complete API Reference")
    print("=" * 100)
    print()
    print("Total APIs: 46 methods across 7 systemd tools")
    print()

    total_apis = 0
    for cat, info in categories.items():
        if not info["methods"]:
            continue

        print()
        print(f"{'─' * 100}")
        print(f" {cat.upper()}: {info['description']}")
        print(f"{'─' * 100}")
        print()

        for method in sorted(info["methods"], key=lambda m: m["name"]):
            total_apis += 1
            print(f"{total_apis:2d}. {method['name']}{method['signature']}")
            print(f"    {method['doc'][:90]}")
            print()

    print("=" * 100)
    print(f" {total_apis} systemd APIs successfully integrated into VMCraft")
    print("=" * 100)
    print()
    print("USAGE NOTES:")
    print()
    print("• All APIs work with offline disk images (mounted via VMCraft)")
    print("• APIs return empty results when systemd is not running (graceful degradation)")
    print("• For full output, use with:")
    print("  - Running VMs (via libvirt/qemu)")
    print("  - Container images with systemd")
    print("  - Host system analysis")
    print()
    print("EXAMPLE USAGE:")
    print()
    print("  from hyper2kvm.vmcraft.main import VMCraft")
    print()
    print("  g = VMCraft()")
    print("  g.add_drive_opts('/path/to/vm.vmdk', readonly=True)")
    print("  g.launch()")
    print()
    print("  # Service Management")
    print("  services = g.systemctl_list_units('service', state='active')")
    print("  failed = g.systemctl_list_failed()")
    print()
    print("  # Log Analysis")
    print("  errors = g.journalctl_get_errors(since='1 hour ago')")
    print("  boots = g.journalctl_list_boots()")
    print()
    print("  # Performance Analysis")
    print("  timing = g.systemd_analyze_time()")
    print("  blame = g.systemd_analyze_blame(lines=10)")
    print()
    print("  # System Configuration")
    print("  hostname = g.hostnamectl_status()")
    print("  time_config = g.timedatectl_status()")
    print()
    print("  g.shutdown()")
    print()
    print("=" * 100)


if __name__ == "__main__":
    print_api_reference()
