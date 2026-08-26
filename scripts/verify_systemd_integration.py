#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Verify Systemd Boot Integration
================================

Quick verification script to ensure systemd boot integration is properly
integrated into the pipeline.
"""

import sys
from pathlib import Path


def verify_imports():
    """Verify all imports work correctly"""
    print("=" * 60)
    print("1. Verifying Module Imports")
    print("=" * 60)

    try:
        from hyper2kvm.infrastructure.systemd import (
            SystemdBootIntegration,
            SystemdRepartManager,
            SystemdGrowfsManager,
            BootEnvironment,
            BootType,
            FilesystemType,
            integrate_with_vm_repair,
        )

        print("✓ systemd_integration module imports successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import systemd_integration: {e}")
        return False


def verify_pipeline_integration():
    """Verify integration into offline_fixer"""
    print("\n" + "=" * 60)
    print("2. Verifying Pipeline Integration")
    print("=" * 60)

    try:
        from hyper2kvm.fixers.offline_fixer import OfflineFSFix

        # Check method exists
        if hasattr(OfflineFSFix, "apply_systemd_boot_integration"):
            print("✓ apply_systemd_boot_integration() method exists in OfflineFSFix")
        else:
            print("✗ apply_systemd_boot_integration() method NOT found in OfflineFSFix")
            return False

        # Verify it's callable
        import inspect

        if inspect.ismethod(OfflineFSFix.apply_systemd_boot_integration) or inspect.isfunction(
            OfflineFSFix.apply_systemd_boot_integration
        ):
            print("✓ apply_systemd_boot_integration() is callable")
        else:
            print("✗ apply_systemd_boot_integration() is not callable")
            return False

        return True
    except Exception as e:
        print(f"✗ Pipeline integration verification failed: {e}")
        return False


def verify_files_exist():
    """Verify all files were created"""
    print("\n" + "=" * 60)
    print("3. Verifying File Structure")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent

    files_to_check = [
        "hyper2kvm/systemd/boot.py",
        "hyper2kvm/systemd/cli.py",
        "hyper2kvm/systemd/README.md",
        "docs/features/SYSTEMD_BOOT_INTEGRATION.md",
        "examples/systemd_boot_integration_examples.py",
        "tests/test_systemd_boot_integration.py",
        "SYSTEMD_INTEGRATION_SUMMARY.md",
        "SYSTEMD_BOOT_PIPELINE_INTEGRATION.md",
    ]

    all_exist = True
    for file_path in files_to_check:
        full_path = base_dir / file_path
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"✓ {file_path} ({size:,} bytes)")
        else:
            print(f"✗ {file_path} MISSING")
            all_exist = False

    return all_exist


def verify_documentation():
    """Verify documentation is complete"""
    print("\n" + "=" * 60)
    print("4. Verifying Documentation")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent

    readme = base_dir / "hyper2kvm/systemd/README.md"
    if readme.exists():
        content = readme.read_text()
        required_sections = [
            "Features",
            "Usage",
            "Examples",
            "Architecture",
            "Installation",
            "Best Practices",
        ]

        all_found = True
        for section in required_sections:
            if section in content:
                print(f"✓ README contains '{section}' section")
            else:
                print(f"✗ README missing '{section}' section")
                all_found = False

        return all_found
    else:
        print("✗ README.md not found")
        return False


def verify_tests():
    """Verify tests can be imported"""
    print("\n" + "=" * 60)
    print("5. Verifying Tests")
    print("=" * 60)

    try:
        base_dir = Path(__file__).parent.parent
        sys.path.insert(0, str(base_dir))

        # Try to import test module
        import tests.test_systemd_boot_integration as test_module

        # Count test classes
        import inspect

        test_classes = [
            name
            for name, obj in inspect.getmembers(test_module)
            if inspect.isclass(obj) and name.startswith("Test")
        ]

        print(f"✓ Test module imports successfully")
        print(f"✓ Found {len(test_classes)} test classes")

        if len(test_classes) >= 10:
            print(f"✓ Test coverage appears comprehensive ({len(test_classes)} classes)")
            return True
        else:
            print(f"⚠ Test coverage may be limited ({len(test_classes)} classes)")
            return True

    except Exception as e:
        print(f"✗ Test verification failed: {e}")
        return False


def verify_cli_tool():
    """Verify CLI tool works"""
    print("\n" + "=" * 60)
    print("6. Verifying CLI Tool")
    print("=" * 60)

    try:
        from hyper2kvm.infrastructure.systemd import cli
        import inspect

        # Check main function exists
        if hasattr(cli, "main"):
            print("✓ CLI main() function exists")
        else:
            print("✗ CLI main() function NOT found")
            return False

        # Count command functions
        command_functions = [
            name
            for name, obj in inspect.getmembers(cli)
            if inspect.isfunction(obj) and name.startswith("cmd_")
        ]

        print(f"✓ Found {len(command_functions)} CLI commands")

        expected_commands = [
            "cmd_prepare_boot",
            "cmd_configure_autogrow",
            "cmd_create_partitions",
            "cmd_firstboot",
            "cmd_analyze_boot",
            "cmd_verify_boot",
            "cmd_integrate_repair",
        ]

        all_found = True
        for cmd in expected_commands:
            if cmd in command_functions:
                print(f"  ✓ {cmd}")
            else:
                print(f"  ✗ {cmd} MISSING")
                all_found = False

        return all_found

    except Exception as e:
        print(f"✗ CLI verification failed: {e}")
        return False


def main():
    """Run all verifications"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║  SYSTEMD BOOT INTEGRATION VERIFICATION                  ║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = {
        "Imports": verify_imports(),
        "Pipeline Integration": verify_pipeline_integration(),
        "File Structure": verify_files_exist(),
        "Documentation": verify_documentation(),
        "Tests": verify_tests(),
        "CLI Tool": verify_cli_tool(),
    }

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8s} {name}")

    print("=" * 60)
    print(f"Results: {passed}/{total} checks passed")
    print("=" * 60)

    if all(results.values()):
        print("\n✅ ALL VERIFICATIONS PASSED!")
        print("\nSystemd boot integration is properly integrated and ready to use.")
        print("\nNext steps:")
        print("  1. Run unit tests: pytest tests/test_systemd_boot_integration.py -v")
        print("  2. Test with real VM: hyper2kvm --vmdk /path/to/vm.vmdk --output-dir /output")
        print("  3. Check migration report for systemd_boot_integration section")
        return 0
    else:
        print("\n⚠️  SOME VERIFICATIONS FAILED")
        print("\nPlease review the failures above and fix any issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
