#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Boot Integration Examples
==================================

Examples demonstrating how to use systemd boot-time integration features
for VM preparation and optimization.
"""

from pathlib import Path
from hyper2kvm.infrastructure.systemd import (
    SystemdBootIntegration,
    SystemdRepartManager,
    SystemdGrowfsManager,
    SystemdMountManager,
    SystemdFirstBootManager,
    SystemdTmpfilesManager,
    BootPerformanceAnalyzer,
    BootEnvironmentRecovery,
    PartitionType,
    FilesystemType,
    BootType,
    PartitionDefinition,
    MountConfiguration,
    BootEnvironment,
    integrate_with_vm_repair,
)


def example_basic_vm_preparation():
    """Example: Basic VM boot environment preparation"""
    print("=" * 60)
    print("Example 1: Basic VM Boot Environment Preparation")
    print("=" * 60)

    # Define boot environment
    boot_env = BootEnvironment(
        boot_type=BootType.UEFI,
        root_device="/dev/vda2",
        root_fstype=FilesystemType.EXT4,
        hostname="migrated-vm-01",
        kernel_cmdline=["quiet", "splash", "console=tty0", "console=ttyS0,115200"],
    )

    # Initialize integration (for offline VM preparation)
    integration = SystemdBootIntegration(root_path="/mnt/vmroot", vm_name="web-server-01")

    # Prepare complete boot environment
    results = integration.prepare_vm_boot_environment(
        boot_env=boot_env, setup_machine_id=True, configure_recovery=True
    )

    print(f"Machine ID: {results.get('machine_id')}")
    print(f"Tmpfiles created: {results.get('tmpfiles_created')}")
    print(f"Recovery configured: {results.get('recovery_configured')}")
    print(f"Boot ready: {results['verification']['ready']}")

    if not results["verification"]["ready"]:
        print(f"Issues found: {results['verification']['issues']}")

    print()


def example_partition_management():
    """Example: Automatic partition management with systemd-repart"""
    print("=" * 60)
    print("Example 2: Automatic Partition Management")
    print("=" * 60)

    repart = SystemdRepartManager()

    # Create standard partition layout for 50GB disk
    configs = repart.create_standard_layout(boot_type=BootType.UEFI, disk_size_gb=50)

    print(f"Created {len(configs)} partition configurations:")
    for config in configs:
        print(f"  - {config.name}")

    # Custom partition definition
    data_partition = PartitionDefinition(
        type=PartitionType.DATA,
        size_min="10G",
        size_max="",  # Grow to fill
        filesystem=FilesystemType.XFS,
        label="data",
        priority=1500,
        grow=True,
    )

    data_config = repart.create_partition_config(data_partition, filename="30-data.conf")
    print(f"\nCustom data partition config: {data_config}")

    # Simulate repart (dry-run)
    print("\nSimulating repart on /dev/vda...")
    success = repart.apply_repart("/dev/vda", dry_run=True)
    print(f"Repart simulation: {'Success' if success else 'Failed'}")

    print()


def example_filesystem_auto_grow():
    """Example: Configure filesystems for automatic growth"""
    print("=" * 60)
    print("Example 3: Automatic Filesystem Growth")
    print("=" * 60)

    growfs = SystemdGrowfsManager()

    # Define mount points to auto-grow
    mount_configs = [
        MountConfiguration(what="/dev/vda2", where="/", type=FilesystemType.EXT4),
        MountConfiguration(what="/dev/vda3", where="/var", type=FilesystemType.XFS),
        MountConfiguration(what="/dev/vda4", where="/home", type=FilesystemType.BTRFS),
    ]

    # Configure auto-grow
    created_files = growfs.configure_growfs(mount_configs)

    print(f"Configured auto-grow for {len(created_files)} filesystems:")
    for file in created_files:
        print(f"  - {file}")

    print("\nFilesystems will automatically grow to partition size on boot!")
    print()


def example_mount_unit_creation():
    """Example: Create systemd mount units"""
    print("=" * 60)
    print("Example 4: Systemd Mount Unit Creation")
    print("=" * 60)

    mount_mgr = SystemdMountManager()

    # Create mount unit for /data
    data_mount = MountConfiguration(
        what="UUID=12345678-1234-1234-1234-123456789012",
        where="/data",
        type=FilesystemType.XFS,
        options=["defaults", "noatime", "x-systemd.growfs"],
        wanted_by="multi-user.target",
        after=["local-fs-pre.target"],
        timeout_sec=120,
    )

    mount_unit = mount_mgr.create_mount_unit(data_mount)
    print(f"Created mount unit: {mount_unit}")

    # Enable the mount
    success = mount_mgr.enable_mount("/data")
    print(f"Mount unit enabled: {success}")

    print()


def example_firstboot_configuration():
    """Example: First boot system configuration"""
    print("=" * 60)
    print("Example 5: First Boot Configuration")
    print("=" * 60)

    firstboot = SystemdFirstBootManager()

    # Configure system for first boot
    success = firstboot.configure_firstboot(
        root_path="/mnt/vmroot",
        hostname="prod-web-01.example.com",
        timezone="America/New_York",
        locale="en_US.UTF-8",
        keymap="us",
        root_shell="/bin/bash",
    )

    print(f"First boot configuration: {'Success' if success else 'Failed'}")

    # Setup machine ID
    machine_id = firstboot.setup_machine_id("/mnt/vmroot")
    print(f"Machine ID: {machine_id}")

    print()


def example_tmpfiles_management():
    """Example: Temporary files management"""
    print("=" * 60)
    print("Example 6: Tmpfiles Management")
    print("=" * 60)

    tmpfiles = SystemdTmpfilesManager()

    # Create VM-specific tmpfiles configuration
    vm_config = tmpfiles.create_vm_tmpfiles()
    print(f"Created VM tmpfiles config: {vm_config}")

    # Custom tmpfiles configuration
    custom_entries = [
        # Type, Path, Mode, User, Group, Age, Argument
        ("d", "/var/lib/myapp", "0755", "myapp", "myapp", "-", "-"),
        ("d", "/var/log/myapp", "0750", "myapp", "myapp", "-", "-"),
        ("d", "/run/myapp", "0755", "myapp", "myapp", "-", "-"),
        ("f", "/var/log/myapp/app.log", "0640", "myapp", "myapp", "-", "-"),
        ("L+", "/var/lib/myapp/current", "-", "-", "-", "-", "/opt/myapp/latest"),
    ]

    custom_config = tmpfiles.create_tmpfiles_config("myapp", custom_entries)
    print(f"Created custom tmpfiles config: {custom_config}")

    # Apply tmpfiles
    success = tmpfiles.apply_tmpfiles("/mnt/vmroot")
    print(f"Tmpfiles applied: {success}")

    print()


def example_boot_performance_analysis():
    """Example: Boot performance analysis"""
    print("=" * 60)
    print("Example 7: Boot Performance Analysis")
    print("=" * 60)

    analyzer = BootPerformanceAnalyzer()

    # Get boot time breakdown
    boot_time = analyzer.get_boot_time()
    if boot_time:
        print("Boot time breakdown:")
        for component, time_ms in boot_time.items():
            print(f"  {component}: {time_ms:.2f}ms")

    # Get critical chain
    critical_chain = analyzer.get_critical_chain()
    if critical_chain:
        print("\nCritical boot chain:")
        print(critical_chain[:500])  # First 500 chars

    # Get blame (slowest services)
    blame = analyzer.get_blame()
    if blame:
        print("\nTop 5 slowest services:")
        for time_ms, service in blame[:5]:
            print(f"  {time_ms:.2f}ms - {service}")

    print()


def example_recovery_configuration():
    """Example: Boot recovery configuration"""
    print("=" * 60)
    print("Example 8: Boot Recovery Configuration")
    print("=" * 60)

    recovery = BootEnvironmentRecovery()

    # Generate rescue target configuration
    rescue_config = recovery.generate_rescue_target("/mnt/vmroot")
    print(f"Created rescue target config: {rescue_config}")

    # Create emergency shell override
    emergency_config = recovery.create_emergency_shell_override("/mnt/vmroot")
    print(f"Created emergency shell config: {emergency_config}")

    # Verify boot environment
    verification = recovery.verify_boot_environment("/mnt/vmroot")

    print("\nBoot environment verification:")
    print(f"  fstab exists: {verification['fstab_exists']}")
    print(f"  initramfs exists: {verification['initramfs_exists']}")
    print(f"  GRUB config exists: {verification['grub_config_exists']}")
    print(f"  machine-id exists: {verification['machine_id_exists']}")
    print(f"  systemd exists: {verification['systemd_exists']}")
    print(f"  Boot ready: {verification['ready']}")

    if verification["issues"]:
        print(f"\nIssues found:")
        for issue in verification["issues"]:
            print(f"  - {issue}")

    print()


def example_complete_vm_migration():
    """Example: Complete VM migration with all features"""
    print("=" * 60)
    print("Example 9: Complete VM Migration Workflow")
    print("=" * 60)

    # Step 1: Define boot environment
    boot_env = BootEnvironment(
        boot_type=BootType.UEFI,
        root_device="/dev/vda2",
        root_fstype=FilesystemType.EXT4,
        hostname="migrated-db-server",
        kernel_cmdline=["quiet", "console=ttyS0,115200n8"],
        initrd_modules=["virtio_blk", "virtio_net", "virtio_scsi"],
    )

    # Step 2: Initialize integration
    integration = SystemdBootIntegration(root_path="/mnt/vmroot", vm_name="database-server-01")

    # Step 3: Apply all features
    results = integration.apply_all_features(
        boot_env=boot_env,
        auto_grow_mounts=["/", "/var", "/home"],
        analyze_performance=False,  # Skip during offline prep
    )

    print("Migration results:")
    print(f"  Boot environment: {results['boot_env']['success']}")
    print(f"  Machine ID: {results['boot_env']['machine_id']}")
    print(f"  Auto-grow configured: {results.get('auto_grow', False)}")

    verification = results["boot_env"]["verification"]
    if verification["ready"]:
        print("\n✅ VM is ready to boot!")
    else:
        print(f"\n⚠️  Issues found: {verification['issues']}")

    print()


def example_integration_with_repair():
    """Example: Integration with VM repair workflow"""
    print("=" * 60)
    print("Example 10: Integration with VM Repair Workflow")
    print("=" * 60)

    # This function integrates systemd boot features into the repair workflow
    success = integrate_with_vm_repair(
        vm_name="production-app-01",
        root_path="/mnt/vmroot",
        root_device="/dev/vda2",
        hostname="prod-app-01.internal.example.com",
    )

    if success:
        print("✅ Systemd boot integration successful!")
        print("\nVM is ready with:")
        print("  - Configured machine ID")
        print("  - Auto-growing root filesystem")
        print("  - Emergency recovery mode")
        print("  - Tmpfiles configuration")
        print("  - Boot environment verification")
    else:
        print("⚠️  Systemd boot integration completed with warnings")

    print()


def main():
    """Run all examples"""
    print("\n")
    print("=" * 60)
    print("SYSTEMD BOOT INTEGRATION EXAMPLES")
    print("=" * 60)
    print("\nThese examples demonstrate systemd boot-time integration")
    print("features for VM migration and optimization.\n")

    try:
        # Core examples
        example_basic_vm_preparation()
        example_partition_management()
        example_filesystem_auto_grow()
        example_mount_unit_creation()
        example_firstboot_configuration()
        example_tmpfiles_management()

        # Analysis and recovery
        example_boot_performance_analysis()
        example_recovery_configuration()

        # Complete workflows
        example_complete_vm_migration()
        example_integration_with_repair()

        print("=" * 60)
        print("All examples completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
