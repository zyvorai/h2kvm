#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Integration CLI Tool
=============================

Command-line interface for systemd boot integration features.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .boot import (
    BootEnvironment,
    BootEnvironmentRecovery,
    BootPerformanceAnalyzer,
    BootType,
    FilesystemType,
    SystemdBootIntegration,
    SystemdFirstBootManager,
    SystemdRepartManager,
    integrate_with_vm_repair,
)


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def cmd_prepare_boot(args):
    """Prepare VM boot environment"""
    boot_env = BootEnvironment(
        boot_type=BootType[args.boot_type.upper()],
        root_device=args.root_device,
        root_fstype=FilesystemType[args.fstype.upper()],
        hostname=args.hostname,
    )

    integration = SystemdBootIntegration(
        root_path=args.root_path, vm_name=args.vm_name or Path(args.root_path).name
    )

    results = integration.prepare_vm_boot_environment(
        boot_env=boot_env, setup_machine_id=not args.no_machine_id, configure_recovery=not args.no_recovery
    )

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"Machine ID: {results.get('machine_id', 'N/A')}")
        print(f"Tmpfiles created: {results.get('tmpfiles_created', False)}")
        print(f"Recovery configured: {results.get('recovery_configured', False)}")
        print(f"Boot ready: {results['verification']['ready']}")

        if not results["verification"]["ready"]:
            print("\nIssues found:")
            for issue in results["verification"]["issues"]:
                print(f"  - {issue}")

    return 0 if results["verification"]["ready"] else 1


def cmd_configure_autogrow(args):
    """Configure filesystems for auto-grow"""
    integration = SystemdBootIntegration(root_path=args.root_path, vm_name=args.vm_name or "unknown")

    mount_points = args.mount_points or ["/"]
    success = integration.configure_auto_grow_filesystems(mount_points)

    if args.json:
        print(json.dumps({"success": success, "mount_points": mount_points}))
    elif success:
        print(f"✓ Configured auto-grow for: {', '.join(mount_points)}")
    else:
        print("✗ Failed to configure auto-grow")

    return 0 if success else 1


def cmd_create_partitions(args):
    """Create partition configuration"""
    repart = SystemdRepartManager()

    boot_type = BootType[args.boot_type.upper()]
    configs = repart.create_standard_layout(boot_type=boot_type, disk_size_gb=args.disk_size)

    if args.json:
        print(json.dumps([str(c) for c in configs], indent=2))
    else:
        print(f"Created {len(configs)} partition configurations:")
        for config in configs:
            print(f"  - {config.name}")

        if not args.no_apply:
            print(f"\nSimulating repart on {args.device}...")
            success = repart.apply_repart(args.device, dry_run=True)
            print(f"Simulation: {'Success' if success else 'Failed'}")

    return 0


def cmd_firstboot(args):
    """Configure first boot settings"""
    firstboot = SystemdFirstBootManager()

    success = firstboot.configure_firstboot(
        root_path=args.root_path,
        hostname=args.hostname,
        timezone=args.timezone,
        locale=args.locale,
        keymap=args.keymap,
    )

    if args.setup_machine_id:
        machine_id = firstboot.setup_machine_id(args.root_path)
        if args.json:
            print(json.dumps({"success": success, "machine_id": machine_id}))
        else:
            print(f"First boot configuration: {'Success' if success else 'Failed'}")
            print(f"Machine ID: {machine_id}")
    elif args.json:
        print(json.dumps({"success": success}))
    else:
        print(f"First boot configuration: {'Success' if success else 'Failed'}")

    return 0 if success else 1


def cmd_analyze_boot(args):
    """Analyze boot performance"""
    analyzer = BootPerformanceAnalyzer()

    results = {}

    # Get boot time
    boot_time = analyzer.get_boot_time()
    if boot_time:
        results["boot_time"] = boot_time
        results["total_time_ms"] = sum(boot_time.values())

    # Get critical chain
    if args.show_chain:
        critical_chain = analyzer.get_critical_chain()
        results["critical_chain"] = critical_chain

    # Get blame
    blame = analyzer.get_blame()
    if blame:
        results["slow_services"] = [{"time_ms": time, "service": svc} for time, svc in blame[: args.top]]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if "boot_time" in results:
            print("Boot time breakdown:")
            for component, time_ms in results["boot_time"].items():
                print(f"  {component}: {time_ms:.2f}ms")
            print(f"\nTotal: {results['total_time_ms']:.2f}ms")

        if "slow_services" in results:
            print(f"\nTop {args.top} slowest services:")
            for entry in results["slow_services"]:
                print(f"  {entry['time_ms']:.2f}ms - {entry['service']}")

        if "critical_chain" in results:
            print("\nCritical chain:")
            print(results["critical_chain"])

    return 0


def cmd_verify_boot(args):
    """Verify boot environment"""
    recovery = BootEnvironmentRecovery()

    verification = recovery.verify_boot_environment(args.root_path)

    if args.json:
        print(json.dumps(verification, indent=2))
    else:
        print("Boot environment verification:")
        print(f"  fstab exists: {verification['fstab_exists']}")
        print(f"  initramfs exists: {verification['initramfs_exists']}")
        print(f"  GRUB config exists: {verification['grub_config_exists']}")
        print(f"  machine-id exists: {verification['machine_id_exists']}")
        print(f"  systemd exists: {verification['systemd_exists']}")
        print(f"\nBoot ready: {verification['ready']}")

        if verification["issues"]:
            print("\nIssues found:")
            for issue in verification["issues"]:
                print(f"  - {issue}")

    return 0 if verification["ready"] else 1


def cmd_integrate_repair(args):
    """Integrate systemd boot features with VM repair"""
    success = integrate_with_vm_repair(
        vm_name=args.vm_name, root_path=args.root_path, root_device=args.root_device, hostname=args.hostname
    )

    if args.json:
        print(json.dumps({"success": success}))
    elif success:
        print("✓ Systemd boot integration successful")
    else:
        print("✗ Systemd boot integration failed or completed with warnings")

    return 0 if success else 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Systemd Boot Integration CLI", formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # prepare-boot command
    prepare_parser = subparsers.add_parser("prepare-boot", help="Prepare VM boot environment")
    prepare_parser.add_argument("root_path", help="Root filesystem path")
    prepare_parser.add_argument("root_device", help="Root device path")
    prepare_parser.add_argument("--vm-name", help="VM name (default: root_path basename)")
    prepare_parser.add_argument(
        "--boot-type", choices=["bios", "uefi", "unknown"], default="uefi", help="Boot firmware type"
    )
    prepare_parser.add_argument(
        "--fstype", choices=["ext4", "xfs", "btrfs"], default="ext4", help="Root filesystem type"
    )
    prepare_parser.add_argument("--hostname", help="VM hostname")
    prepare_parser.add_argument("--no-machine-id", action="store_true", help="Skip machine ID setup")
    prepare_parser.add_argument(
        "--no-recovery", action="store_true", help="Skip recovery mode configuration"
    )
    prepare_parser.set_defaults(func=cmd_prepare_boot)

    # auto-grow command
    autogrow_parser = subparsers.add_parser("auto-grow", help="Configure filesystems for auto-grow")
    autogrow_parser.add_argument("root_path", help="Root filesystem path")
    autogrow_parser.add_argument(
        "--mount-points", nargs="+", help="Mount points to enable auto-grow (default: /)"
    )
    autogrow_parser.add_argument("--vm-name", help="VM name")
    autogrow_parser.set_defaults(func=cmd_configure_autogrow)

    # create-partitions command
    partition_parser = subparsers.add_parser("create-partitions", help="Create partition configuration")
    partition_parser.add_argument("device", help="Block device path (for simulation)")
    partition_parser.add_argument(
        "--boot-type", choices=["bios", "uefi"], default="uefi", help="Boot firmware type"
    )
    partition_parser.add_argument("--disk-size", type=int, default=50, help="Disk size in GB (default: 50)")
    partition_parser.add_argument("--no-apply", action="store_true", help="Skip apply simulation")
    partition_parser.set_defaults(func=cmd_create_partitions)

    # firstboot command
    firstboot_parser = subparsers.add_parser("firstboot", help="Configure first boot settings")
    firstboot_parser.add_argument("root_path", help="Root filesystem path")
    firstboot_parser.add_argument("--hostname", help="System hostname")
    firstboot_parser.add_argument("--timezone", help="System timezone")
    firstboot_parser.add_argument("--locale", help="System locale")
    firstboot_parser.add_argument("--keymap", help="Console keymap")
    firstboot_parser.add_argument("--setup-machine-id", action="store_true", help="Setup machine ID")
    firstboot_parser.set_defaults(func=cmd_firstboot)

    # analyze-boot command
    analyze_parser = subparsers.add_parser("analyze-boot", help="Analyze boot performance")
    analyze_parser.add_argument(
        "--top", type=int, default=10, help="Number of slow services to show (default: 10)"
    )
    analyze_parser.add_argument("--show-chain", action="store_true", help="Show critical boot chain")
    analyze_parser.set_defaults(func=cmd_analyze_boot)

    # verify-boot command
    verify_parser = subparsers.add_parser("verify-boot", help="Verify boot environment")
    verify_parser.add_argument("root_path", help="Root filesystem path")
    verify_parser.set_defaults(func=cmd_verify_boot)

    # integrate-repair command
    integrate_parser = subparsers.add_parser(
        "integrate-repair", help="Integrate systemd boot features with VM repair"
    )
    integrate_parser.add_argument("vm_name", help="VM name")
    integrate_parser.add_argument("root_path", help="Root filesystem path")
    integrate_parser.add_argument("root_device", help="Root device path")
    integrate_parser.add_argument("--hostname", help="VM hostname")
    integrate_parser.set_defaults(func=cmd_integrate_repair)

    # Parse arguments
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if not args.command:
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except Exception as e:
        logging.exception(f"Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
