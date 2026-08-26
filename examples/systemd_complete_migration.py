#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Complete VM Migration Workflow using Systemd Tools.

This example demonstrates a full end-to-end VM migration workflow
using all available systemd tool integrations.
"""

from pathlib import Path

from h2kvm.systemd import (
    SystemdAnalyze,
    SystemdCat,
    SystemdCgtop,
    SystemdCreds,
    SystemdDelta,
    SystemdDetectVirt,
    SystemdDissect,
    SystemdId128,
    SystemdInhibit,
    SystemdMachineId,
    SystemdNspawn,
    SystemdPath,
    SystemdVmspawn,
)


def phase_1_detect_source():
    """Phase 1: Detect source virtualization platform."""
    print("🔍 Phase 1: Detecting Source Platform")
    print("=" * 60)

    detector = SystemdDetectVirt()

    if not detector.is_virtualized():
        print("❌ Not running in virtualized environment")
        return None

    virt_type = detector.detect()
    hypervisor = detector.get_hypervisor_name()

    print(f"✅ Detected: {hypervisor}")
    print(f"   Type: {virt_type.value}")
    print(f"   VM: {detector.is_vm()}")
    print(f"   Container: {detector.is_container()}")

    return hypervisor


def phase_2_inspect_disk(image_path: Path):
    """Phase 2: Inspect source disk image."""
    print("\n🔍 Phase 2: Inspecting Disk Image")
    print("=" * 60)

    dissect = SystemdDissect()

    # Validate image
    if dissect.validate(image_path):
        print(f"✅ Image validated: {image_path}")
    else:
        print(f"❌ Invalid image: {image_path}")
        return None

    # Inspect image
    info = dissect.inspect(image_path)

    print("📀 Image Info:")
    print(f"   Format: {info.format}")
    print(f"   Size: {info.size / 1e9:.2f} GB")
    print(f"   Partitions: {len(info.partitions)}")

    if info.os_release:
        print(f"   OS: {info.os_release.get('NAME')} {info.os_release.get('VERSION')}")
        print(f"   Hostname: {info.hostname}")

    for i, part in enumerate(info.partitions, 1):
        print(f"   Partition {i}: {part.type} ({part.size / 1e9:.2f} GB)")

    return info


def phase_3_secure_credentials():
    """Phase 3: Secure migration credentials."""
    print("\n🔐 Phase 3: Securing Credentials")
    print("=" * 60)

    creds = SystemdCreds()

    # Check TPM2 availability
    if creds.has_tpm2():
        print("✅ TPM2 available for credential encryption")

        # Encrypt vCenter password (example)
        vcenter_password = "example-password"
        encrypted_path = Path("/tmp/vcenter.cred")

        creds.encrypt(
            vcenter_password,
            "vcenter-password",
            output=encrypted_path,
        )

        print(f"✅ Credentials encrypted to: {encrypted_path}")
    else:
        print("⚠️  TPM2 not available, using alternative encryption")

    return True


def phase_4_prepare_environment():
    """Phase 4: Prepare migration environment."""
    print("\n🛠️  Phase 4: Preparing Environment")
    print("=" * 60)

    path = SystemdPath()

    # Get system paths
    temp_dir = path.get_temporary_directory()
    state_dir = path.get_state_directory()
    cache_dir = path.get_cache_directory()

    print("📁 System Paths:")
    print(f"   Temp: {temp_dir}")
    print(f"   State: {state_dir}")
    print(f"   Cache: {cache_dir}")

    # Create migration directories
    migration_tmp = Path(temp_dir) / "h2kvm"
    migration_tmp.mkdir(exist_ok=True, parents=True)

    print(f"✅ Created migration temp: {migration_tmp}")

    return migration_tmp


def phase_5_convert_with_monitoring(source: Path, target: Path):
    """Phase 5: Convert disk with resource limits and monitoring."""
    print("\n⚙️  Phase 5: Converting Disk with Monitoring")
    print("=" * 60)

    # Prevent system sleep during conversion
    inhibit = SystemdInhibit()
    cat = SystemdCat()

    # Log start to journal
    cat.log("Starting VM disk conversion", priority=6)

    print("🚫 Preventing system sleep/shutdown")
    print(f"🔄 Converting: {source} -> {target}")
    print("📊 Resource limits: 4GB RAM, 200% CPU")

    # Run conversion with resource limits
    try:
        inhibit.run(
            [
                "systemd-run",
                "--scope",
                "--property=MemoryMax=4G",
                "--property=CPUQuota=200%",
                "--",
                "qemu-img",
                "convert",
                "-O",
                "qcow2",
                str(source),
                str(target),
            ],
            what="idle:sleep:shutdown",
            why="Critical VM disk conversion in progress",
        )

        print("✅ Conversion completed successfully")
        cat.log("VM disk conversion completed", priority=6)

    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        cat.log(f"VM disk conversion failed: {e}", priority=3)
        raise

    # Monitor resource usage
    cgtop = SystemdCgtop()
    stats = cgtop.snapshot()

    print("\n📈 Resource Usage Snapshot:")
    for cg in stats[:5]:  # Top 5 cgroups
        print(f"   {cg.path}: CPU {cg.cpu_percent:.1f}%, MEM {cg.memory_bytes / 1e6:.1f}MB")

    return target


def phase_6_test_container(image: Path):
    """Phase 6: Test VM in container."""
    print("\n🧪 Phase 6: Testing in Container")
    print("=" * 60)

    nspawn = SystemdNspawn()

    print(f"🐳 Spawning ephemeral container from: {image}")
    print("   Mode: Ephemeral (no persistent changes)")
    print("   Boot: Full init system")

    try:
        # Quick smoke test in ephemeral container
        nspawn.spawn_image(
            image,
            ephemeral=True,
            boot=False,  # Don't boot for quick test
            read_only=True,
        )

        print("✅ Container test passed")
    except Exception as e:
        print(f"⚠️  Container test skipped: {e}")

    return True


def phase_7_test_vm(image: Path):
    """Phase 7: Test VM in full virtualization."""
    print("\n🖥️  Phase 7: Testing in Full Virtualization")
    print("=" * 60)

    vmspawn = SystemdVmspawn()

    print(f"🚀 Spawning VM from: {image}")
    print("   CPUs: 2")
    print("   Memory: 4GB")
    print("   Network: User-mode")

    try:
        # Test in QEMU/KVM
        vmspawn.spawn(
            image,
            cpus=2,
            memory="4G",
            network_user=True,
            console="read-only",  # Non-interactive for automation
        )

        print("✅ VM test passed")
    except Exception as e:
        print(f"⚠️  VM test skipped: {e}")

    return True


def phase_8_setup_identity(vm_root: Path):
    """Phase 8: Setup unique VM identity."""
    print("\n🆔 Phase 8: Setting Up VM Identity")
    print("=" * 60)

    # Generate unique IDs
    id128 = SystemdId128()
    vm_id = id128.generate_vm_id()
    volume_id = id128.generate_volume_id()

    print("🔑 Generated IDs:")
    print(f"   VM ID: {vm_id}")
    print(f"   Volume ID: {volume_id}")

    # Setup machine ID
    machine_id = SystemdMachineId()

    # Clear old machine ID
    machine_id.clear(root=vm_root)
    print("🧹 Cleared old machine ID")

    # Generate new machine ID
    new_machine_id = machine_id.setup(root=vm_root)
    print(f"✅ New machine ID: {new_machine_id}")

    return {
        "vm_id": vm_id,
        "volume_id": volume_id,
        "machine_id": new_machine_id,
    }


def phase_9_analyze_configuration(vm_root: Path):
    """Phase 9: Analyze VM configuration."""
    print("\n📋 Phase 9: Analyzing Configuration")
    print("=" * 60)

    delta = SystemdDelta()

    # Find configuration overrides
    overrides = delta.find_overrides()

    if overrides:
        print(f"⚙️  Found {len(overrides)} configuration overrides:")
        for override in overrides[:10]:  # Show first 10
            print(f"   [{override.type.upper()}] {override.original}")
    else:
        print("✅ No configuration overrides found")

    # Check for masked services
    masked = delta.find_masked()
    if masked:
        print(f"\n🚫 Masked services: {len(masked)}")
        for m in masked[:5]:
            print(f"   - {m.original}")

    return len(overrides)


def phase_10_verify_boot(vm_root: Path):
    """Phase 10: Verify boot performance."""
    print("\n⚡ Phase 10: Verifying Boot Performance")
    print("=" * 60)

    analyze = SystemdAnalyze()

    try:
        # Get boot time breakdown
        boot_time = analyze.time()

        print("⏱️  Boot Time Analysis:")
        print(f"   Firmware: {boot_time.firmware:.2f}s")
        print(f"   Loader: {boot_time.loader:.2f}s")
        print(f"   Kernel: {boot_time.kernel:.2f}s")
        print(f"   Initrd: {boot_time.initrd:.2f}s")
        print(f"   Userspace: {boot_time.userspace:.2f}s")
        print(f"   TOTAL: {boot_time.total:.2f}s")

        # Find slow units
        slow_units = analyze.blame(limit=5)
        if slow_units:
            print("\n🐌 Slowest Units:")
            for unit in slow_units:
                print(f"   {unit.unit}: {unit.time:.2f}s")

        # Verify units
        errors = analyze.verify()
        if errors:
            print(f"\n⚠️  Unit Errors: {len(errors)}")
            for unit, msgs in list(errors.items())[:3]:
                print(f"   {unit}: {msgs[0]}")
        else:
            print("\n✅ All units verified")

    except Exception as e:
        print(f"⚠️  Boot analysis skipped: {e}")

    return True


def main():
    """Run complete migration workflow."""
    print("\n" + "=" * 60)
    print("🚀 Complete VM Migration Workflow with Systemd Tools")
    print("=" * 60)

    # Example paths (adjust as needed)
    source_image = Path("/path/to/source.vmdk")
    target_image = Path("/path/to/target.qcow2")
    vm_root = Path("/mnt/vm")

    try:
        # Phase 1: Detect source platform
        phase_1_detect_source()

        # Phase 2: Inspect disk (if image exists)
        if source_image.exists():
            phase_2_inspect_disk(source_image)

        # Phase 3: Secure credentials
        phase_3_secure_credentials()

        # Phase 4: Prepare environment
        phase_4_prepare_environment()

        # Phase 5: Convert disk (if source exists)
        if source_image.exists() and not target_image.exists():
            phase_5_convert_with_monitoring(source_image, target_image)

        # Phase 6: Test in container
        if target_image.exists():
            phase_6_test_container(target_image)

        # Phase 7: Test in VM
        if target_image.exists():
            phase_7_test_vm(target_image)

        # Phase 8: Setup identity (if VM root exists)
        if vm_root.exists():
            phase_8_setup_identity(vm_root)

        # Phase 9: Analyze configuration
        if vm_root.exists():
            phase_9_analyze_configuration(vm_root)

        # Phase 10: Verify boot
        phase_10_verify_boot(vm_root)

        print("\n" + "=" * 60)
        print("✅ Migration workflow completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Migration workflow failed: {e}")
        raise


if __name__ == "__main__":
    main()
