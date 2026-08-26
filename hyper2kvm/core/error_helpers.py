# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/error_helpers.py
"""
Enhanced error message helpers with actionable suggestions and documentation links.
"""

from __future__ import annotations

from typing import Any

# Documentation base URL
DOCS_BASE = "https://github.com/ssahani/hyper2kvm/blob/main/docs"


class ErrorHelper:
    """
    Helper to build actionable error messages with:
    - Clear problem statement
    - Actionable solutions
    - Documentation links
    - Common causes
    - Example commands
    """

    def __init__(self, message: str):
        self.message = message
        self.solutions: list[str] = []
        self.causes: list[str] = []
        self.doc_links: list[str] = []
        self.examples: list[str] = []

    def add_solution(self, solution: str) -> ErrorHelper:
        """Add an actionable solution."""
        self.solutions.append(solution)
        return self

    def add_cause(self, cause: str) -> ErrorHelper:
        """Add a common cause."""
        self.causes.append(cause)
        return self

    def add_doc(self, doc_path: str, title: str | None = None) -> ErrorHelper:
        """Add a documentation link."""
        url = f"{DOCS_BASE}/{doc_path}"
        if title:
            self.doc_links.append(f"{title}: {url}")
        else:
            self.doc_links.append(url)
        return self

    def add_example(self, example: str) -> ErrorHelper:
        """Add an example command or configuration."""
        self.examples.append(example)
        return self

    def build(self) -> str:
        """Build the complete error message."""
        parts = [f"ERROR: {self.message}"]

        if self.causes:
            parts.append("")
            parts.append("Common causes:")
            for i, cause in enumerate(self.causes, 1):
                parts.append(f"  {i}. {cause}")

        if self.solutions:
            parts.append("")
            parts.append("Solutions:")
            for i, solution in enumerate(self.solutions, 1):
                parts.append(f"  {i}. {solution}")

        if self.examples:
            parts.append("")
            parts.append("Examples:")
            for example in self.examples:
                parts.append(f"  {example}")

        if self.doc_links:
            parts.append("")
            parts.append("Documentation:")
            for link in self.doc_links:
                parts.append(f"  {link}")

        return "\n".join(parts)


# Pre-defined error helpers for common scenarios


def missing_dependency_error(package: str, install_cmd: str | None = None) -> str:
    """Error for missing Python dependencies."""
    helper = ErrorHelper(f"Required package '{package}' is not installed")

    # Default install command
    if install_cmd is None:
        install_cmd = f"pip install {package}"

    helper.add_solution(f"Install the package: {install_cmd}")

    # Add package-specific guidance
    if package == "pyvmomi":
        helper.add_solution("Or install with vSphere support: pip install hyper2kvm[vsphere]")
        helper.add_doc("02-Installation.md#vsphere-integration", "vSphere Setup Guide")
    elif package == "guestfs":
        helper.add_cause("python3-guestfs not installed (only needed for guestfs backend)")
        helper.add_solution("Install system package first:")
        helper.add_example("Fedora/RHEL: sudo dnf install python3-guestfs")
        helper.add_example("Ubuntu/Debian: sudo apt install python3-guestfs")
        helper.add_doc("02-Installation.md#system-dependencies", "Installation Guide")
    elif package == "requests":
        helper.add_solution("Install with: pip install requests")
    elif package in ["azure-mgmt-compute", "azure-identity"]:
        helper.add_solution("Or install with Azure support: pip install hyper2kvm[azure]")
        helper.add_doc("02-Installation.md#azure-integration", "Azure Setup Guide")

    return helper.build()


def vm_not_found_error(vm_name: str, vcenter: str | None = None) -> str:
    """Error for VM not found in vCenter."""
    helper = ErrorHelper(f"VM not found: {vm_name}")

    helper.add_cause("VM name is misspelled or case-sensitive")
    helper.add_cause("VM is in a different datacenter")
    helper.add_cause("Insufficient permissions to view VM")
    helper.add_cause("VM has been renamed or deleted")

    helper.add_solution("Verify VM name (case-sensitive): govc ls /DC/vm/")
    helper.add_solution("List all accessible VMs: hyper2kvm vsphere --vs-action list-vms")
    helper.add_solution("Check datacenter: govc ls /")
    helper.add_solution("Verify permissions with your vCenter administrator")

    if vcenter:
        helper.add_example(f"govc ls -u 'user@{vcenter}' /")

    helper.add_doc("30-vSphere-Export.md#troubleshooting", "vSphere Troubleshooting")

    return helper.build()


def boot_failure_error(reason: str | None = None) -> str:
    """Error for VM boot failures."""
    msg = "VM failed to boot"
    if reason:
        msg += f": {reason}"

    helper = ErrorHelper(msg)

    helper.add_cause("initramfs missing virtio drivers")
    helper.add_cause("fstab references wrong device names (/dev/sdX instead of UUID)")
    helper.add_cause("GRUB root= parameter incorrect")
    helper.add_cause("SELinux context issues (if SELinux enabled)")

    helper.add_solution("Ensure initramfs was regenerated: --regen-initramfs")
    helper.add_solution("Ensure fstab was fixed: --fstab-mode stabilize-all")
    helper.add_solution("Ensure GRUB was fixed: --fix-grub")
    helper.add_solution("Check VM console for specific error message")

    helper.add_example(
        "hyper2kvm --config your-config.yaml --regen-initramfs --fstab-mode stabilize-all --fix-grub"
    )

    helper.add_doc("90-Failure-Modes.md#boot-failures", "Boot Failure Troubleshooting")

    return helper.build()


def permission_error(path: str, operation: str = "access") -> str:
    """Error for permission denied."""
    helper = ErrorHelper(f"Permission denied: cannot {operation} {path}")

    helper.add_cause("Running without root/sudo privileges")
    helper.add_cause("File/directory ownership incorrect")
    helper.add_cause("SELinux blocking access")
    helper.add_cause("Disk mounted read-only")

    helper.add_solution("Run with sudo: sudo python -m hyper2kvm ...")
    helper.add_solution("Check file ownership: ls -la " + path)
    helper.add_solution("Check SELinux: getenforce && audit2why < /var/log/audit/audit.log")
    helper.add_solution("Verify mount is read-write: mount | grep $(dirname " + path + ")")

    helper.add_doc("90-Failure-Modes.md#permissions", "Permission Troubleshooting")

    return helper.build()


def disk_full_error(path: str, needed: str | None = None) -> str:
    """Error for disk full conditions."""
    msg = f"Insufficient disk space: {path}"
    if needed:
        msg += f" (need: {needed})"

    helper = ErrorHelper(msg)

    helper.add_cause("Destination filesystem full")
    helper.add_cause("Disk quota exceeded")
    helper.add_cause("Temporary directory (/tmp) full")

    helper.add_solution("Check disk space: df -h " + path)
    helper.add_solution("Free up space or use different --output-dir")
    helper.add_solution("Use --compress to reduce output size")
    helper.add_solution("Clean up old migrations")

    helper.add_example(f"df -h {path}")
    helper.add_example("find /data/migrations -mtime +30 -delete  # Clean old files")

    helper.add_doc("90-Failure-Modes.md#disk-space", "Disk Space Troubleshooting")

    return helper.build()


def network_error(host: str, operation: str = "connect") -> str:
    """Error for network connectivity issues."""
    helper = ErrorHelper(f"Network error: cannot {operation} to {host}")

    helper.add_cause("Hostname/IP unreachable")
    helper.add_cause("Firewall blocking connection")
    helper.add_cause("DNS resolution failure")
    helper.add_cause("VPN/network route missing")
    helper.add_cause("TLS certificate verification failure")

    helper.add_solution(f"Check connectivity: ping {host}")
    helper.add_solution(f"Check DNS: nslookup {host}")
    helper.add_solution("Check firewall: sudo firewall-cmd --list-all")
    helper.add_solution("Try with --no-verify (only for testing!)")

    helper.add_example(f"ping -c 3 {host}")
    helper.add_example(f"telnet {host} 443")

    helper.add_doc("90-Failure-Modes.md#network-issues", "Network Troubleshooting")

    return helper.build()


def config_validation_error(field: str, value: Any, expected: str) -> str:
    """Error for configuration validation failures."""
    helper = ErrorHelper(f"Invalid configuration: {field}={value}")

    helper.add_cause(f"Expected {expected}, got {type(value).__name__}")
    helper.add_cause("Configuration file syntax error")
    helper.add_cause("Missing required field")

    helper.add_solution("Check configuration file syntax (YAML/JSON)")
    helper.add_solution(f"Ensure {field} is {expected}")
    helper.add_solution("Validate against example configs in examples/")

    helper.add_example("yamllint your-config.yaml")
    helper.add_example("python -m json.tool your-config.json")

    helper.add_doc("05-YAML-Examples.md", "Configuration Examples")
    helper.add_doc("04-CLI-Reference.md", "CLI Reference")

    return helper.build()


def vmdk_parsing_error(vmdk_path: str, reason: str | None = None) -> str:
    """Error for VMDK parsing failures."""
    msg = f"Failed to parse VMDK: {vmdk_path}"
    if reason:
        msg += f" - {reason}"

    helper = ErrorHelper(msg)

    helper.add_cause("VMDK file corrupted")
    helper.add_cause("Unsupported VMDK format/version")
    helper.add_cause("Sparse VMDK with missing extents")
    helper.add_cause("VMDK encrypted or compressed")

    helper.add_solution("Verify VMDK integrity: file " + vmdk_path)
    helper.add_solution("Check VMDK descriptor: head -20 " + vmdk_path)
    helper.add_solution("Try with --flatten to consolidate snapshots")
    helper.add_solution("If encrypted, decrypt in VMware first")

    helper.add_example(f"qemu-img info {vmdk_path}")
    helper.add_example(f"qemu-img check {vmdk_path}")

    helper.add_doc("90-Failure-Modes.md#vmdk-issues", "VMDK Troubleshooting")

    return helper.build()


def validation_failure_error(test_name: str, details: str | None = None) -> str:
    """Error for VM test/validation failures."""
    msg = f"Test failed: {test_name}"
    if details:
        msg += f" - {details}"

    helper = ErrorHelper(msg)

    helper.add_cause("VM did not boot within timeout")
    helper.add_cause("Required service not running")
    helper.add_cause("Network connectivity issue")
    helper.add_cause("Application health check failed")

    helper.add_solution("Check VM console for errors: virsh console <vm-name>")
    helper.add_solution("Increase test timeout: --test-timeout 600")
    helper.add_solution("Disable testing temporarily: --no-test-boot")
    helper.add_solution("Review migration logs for warnings")

    helper.add_doc("90-Failure-Modes.md#test-failures", "Test Troubleshooting")

    return helper.build()


# Anti-pattern errors (from ANTI-PATTERNS.md)


def no_backup_warning() -> str:
    """Warning about migrating without backups."""
    helper = ErrorHelper("WARNING: No backup/snapshot detected")

    helper.add_cause("Running migration without safety net")

    helper.add_solution("Create VMware snapshot BEFORE migration:")
    helper.add_example("govc snapshot.create -vm <vm-name> -m 'Pre-migration backup'")

    helper.add_solution("Or use --dry-run to validate first")

    helper.add_doc("ANTI-PATTERNS.md#pre-migration-anti-patterns", "Anti-Patterns Guide")

    return helper.build()


def selinux_disabled_warning() -> str:
    """Warning about SELinux being disabled."""
    helper = ErrorHelper("WARNING: SELinux is disabled")

    helper.add_cause("SELinux disabled on migrated VM")

    helper.add_solution("DO NOT disable SELinux - fix contexts instead:")
    helper.add_example("restorecon -Rv /path")
    helper.add_example("audit2allow -a -M myapp && semodule -i myapp.pp")

    helper.add_doc("ANTI-PATTERNS.md#security-anti-patterns", "Security Anti-Patterns")

    return helper.build()


def production_without_testing_warning(vm_name: str) -> str:
    """Warning about migrating to production without testing."""
    helper = ErrorHelper(f"WARNING: Migrating {vm_name} directly to production")

    helper.add_cause("No test migration performed")

    helper.add_solution("ALWAYS test with clone first:")
    helper.add_example(f"govc vm.clone -vm {vm_name} -on=false {vm_name}-test")
    helper.add_example("# Migrate test clone, validate, THEN migrate production")

    helper.add_doc("ANTI-PATTERNS.md#pre-migration-anti-patterns", "Testing Best Practices")

    return helper.build()
