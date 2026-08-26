#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example demonstrating enhanced features with RHEL 10 compatibility.

This example shows how to use:
1. Configuration validation (with pydantic or stdlib fallback)
2. Enhanced retry logic (with tenacity or stdlib fallback)
3. The excellent built-in logging system

All features work on RHEL 10 even without optional dependencies!
"""

from pathlib import Path
import logging

# Check what's available
from h2kvm.core.optional_imports import PYDANTIC_AVAILABLE, TENACITY_AVAILABLE

print("=" * 60)
print("Enhanced Features Example")
print("=" * 60)
print(f"Pydantic available: {PYDANTIC_AVAILABLE}")
print(f"Tenacity available: {TENACITY_AVAILABLE}")
print(f"Note: All features work even if these are False!")
print("=" * 60)
print()

# Example 1: Configuration Validation
# Works with or without pydantic!
from h2kvm.config.validation import NetworkConfig, VMwareSourceConfig, ConfigValidationError

print("1. Configuration Validation Example")
print("-" * 60)

# Valid network configuration
try:
    network = NetworkConfig(
        interface_name="eth0",
        mac_address="52:54:00:12:34:56",
        ip_address="192.168.1.10",
        dns_servers=["8.8.8.8"],
    )
    print(f"✓ Network config created: {network.interface_name}")
    print(f"  Implementation: {'Pydantic' if PYDANTIC_AVAILABLE else 'Stdlib'}")
except ConfigValidationError as e:
    print(f"✗ Validation failed: {e}")

# Invalid configuration - catches errors
try:
    invalid_network = NetworkConfig(interface_name="0invalid")  # Starts with digit
    print("✗ Should have failed validation!")
except ConfigValidationError as e:
    print(f"✓ Caught validation error as expected")
    for error in e.errors:
        print(f"  - {error['field']}: {error['message']}")

print()

# VMware configuration
try:
    vmware = VMwareSourceConfig(
        host="vcenter.example.com", username="admin", password="secret", vm_name="test-vm"
    )
    print(f"✓ VMware config created: {vmware.host}")
except ConfigValidationError as e:
    print(f"✗ Validation failed: {e}")

print()

# Example 2: Enhanced Retry Logic
# Works with or without tenacity!
from h2kvm.core.retry_enhanced import retry_network_operation, RetryContext

print("2. Enhanced Retry Logic Example")
print("-" * 60)

# Decorator-based retry
attempt_count = [0]


@retry_network_operation(max_attempts=3, min_wait=0.1)
def flaky_download():
    """Simulated flaky network operation."""
    attempt_count[0] += 1
    print(f"  Attempt {attempt_count[0]}")

    if attempt_count[0] < 2:
        raise ConnectionError("Network error")

    return f"Downloaded successfully on attempt {attempt_count[0]}"


try:
    result = flaky_download()
    print(f"✓ {result}")
    print(f"  Implementation: {'Tenacity' if TENACITY_AVAILABLE else 'Stdlib'}")
except Exception as e:
    print(f"✗ Failed: {e}")

print()

# Context manager retry
print("Using RetryContext:")
with RetryContext(max_attempts=3, wait_time=0.1) as retry:
    for attempt in retry:
        print(f"  Attempt {attempt.number}")
        try:
            if attempt.number < 2:
                raise OSError("File busy")
            print(f"✓ Operation succeeded on attempt {attempt.number}")
            break
        except OSError as e:
            if attempt.is_last:
                print(f"✗ Failed after all retries")
                raise
            print(f"  Retrying...")

print()

# Example 3: Using the Built-in Logger
# Already excellent - no structlog needed!
from h2kvm.core.logger import Log

print("3. Built-in Logging Example")
print("-" * 60)

# Setup logger
logger = Log.setup(
    verbose=2,  # 0=INFO, 1=INFO, 2=DEBUG, 3=TRACE
    json_logs=False,  # Set to True for JSON output (great for production!)
    show_proc=True,
    show_pid=True,
)

# Basic logging
logger.info("This is an info message")
logger.debug("This is a debug message")

# Context-aware logging (like structlog!)
log_with_ctx = Log.bind(logger, vm="web-server-01", stage="export")
log_with_ctx.info("Starting VM export", extra={"ctx": {"disk_count": 3}})

# Helper methods
Log.step(logger, "Processing VM", vm="web-server-01")
Log.ok(logger, "Export completed", duration_s=45.2)
Log.warn(logger, "Disk is large", size_gb=500)

# JSON logging example
print()
print("JSON Logging (for production):")
json_logger = Log.setup(
    verbose=1,
    json_logs=True,  # NDJSON output
    show_proc=True,
    show_pid=True,
    logger_name="h2kvm.json",
)

json_logger.info("Migration started", extra={"ctx": {"vm": "web-01", "hypervisor": "vmware"}})

print()

# Example 4: Complete Integration Example
print("4. Complete Integration Example")
print("-" * 60)


class EnhancedVMwareMigration:
    """Example showing all features working together."""

    def __init__(self, config_dict: dict):
        # Validate configuration
        try:
            self.vmware_config = VMwareSourceConfig(**config_dict)
            print(f"✓ Configuration validated")
        except ConfigValidationError as e:
            print(f"✗ Configuration invalid:")
            for error in e.errors:
                print(f"  - {error['field']}: {error['message']}")
            raise

        # Setup logger with context
        self.logger = Log.setup(verbose=1, show_proc=True)
        self.log = Log.bind(self.logger, vm=self.vmware_config.vm_name, host=self.vmware_config.host)

    @retry_network_operation(max_attempts=3)
    def connect_to_vmware(self):
        """Connect to vSphere with automatic retry."""
        self.log.info("Connecting to vSphere")
        # Simulated connection
        return True

    @retry_network_operation(max_attempts=5)
    def download_vm_disk(self):
        """Download VM disk with automatic retry."""
        self.log.info("Downloading VM disk")
        # Simulated download
        return "/tmp/disk.vmdk"

    def run_migration(self):
        """Run complete migration."""
        Log.step(self.logger, "Starting migration")

        try:
            self.connect_to_vmware()
            Log.ok(self.logger, "Connected to vSphere")

            disk_path = self.download_vm_disk()
            Log.ok(self.logger, "Downloaded VM disk", path=disk_path)

            Log.ok(self.logger, "Migration completed successfully")
            return True

        except Exception as e:
            Log.fail(self.logger, "Migration failed", error=str(e))
            raise


# Run example migration
try:
    migration = EnhancedVMwareMigration(
        {
            "host": "vcenter.example.com",
            "username": "admin",
            "password": "secret",
            "vm_name": "web-server-01",
        }
    )

    migration.run_migration()
    print()
    print("✓ Example completed successfully!")

except Exception as e:
    print(f"✗ Example failed: {e}")

print()
print("=" * 60)
print("Summary:")
print("-" * 60)
print("✓ Configuration validation works (with or without pydantic)")
print("✓ Retry logic works (with or without tenacity)")
print("✓ Logging is excellent (no structlog needed!)")
print("✓ All features compatible with RHEL 10")
print("=" * 60)
