# Validation API Reference

**Module**: `h2kvm.validation`
**Version**: 1.0.0
**Status**: Production-Ready

Complete API reference for the Migration Validation Suite, providing automated post-migration health checks, service validation, network validation, database validation, and performance benchmarking.

---

## Overview

The Validation API provides comprehensive post-migration validation to ensure migrated VMs are functioning correctly. It includes:

- **Health Checks**: System boot, fstab, kernel modules
- **Service Validation**: Critical service status
- **Network Validation**: Interface configuration, DNS, connectivity
- **Database Validation**: PostgreSQL, MySQL/MariaDB status
- **Performance Benchmarking**: Disk I/O, CPU, memory metrics

---

## Quick Start

```python
from h2kvm.validation import ValidationOrchestrator
from h2kvm.vmcraft import VMCraft
import logging

# Setup
logger = logging.getLogger(__name__)
vmcraft = VMCraft(logger)

# Launch VMCraft with migrated disk
vmcraft.add_disk("/vms/migrated/server.qcow2")
vmcraft.launch()

# Create orchestrator and run validation
orchestrator = ValidationOrchestrator(logger)
report = orchestrator.validate_migration(
    vmcraft,
    check_services=True,
    check_network=True,
    check_databases=True,
    check_performance=True
)

# Check results
if report.overall_status == "PASS":
    print("✓ Validation passed!")
else:
    print(f"✗ Validation failed: {len(report.failed_checks)} failures")

# Save reports
from pathlib import Path
reports = orchestrator.save_report(report, Path("/reports"))
print(f"JSON report: {reports['json']}")
print(f"Markdown report: {reports['markdown']}")

# Cleanup
vmcraft.shutdown()
```

---

## Core Classes

### ValidationOrchestrator

**Purpose**: Orchestrate all validation checks and generate reports

**Import**:
```python
from h2kvm.validation import ValidationOrchestrator
```

**Constructor**:
```python
ValidationOrchestrator(logger: logging.Logger | None = None)
```

**Parameters**:
- `logger`: Optional logger instance (creates default if None)

---

#### validate_migration()

Run comprehensive migration validation.

**Signature**:
```python
def validate_migration(
    self,
    vmcraft_instance,
    *,
    check_services: bool = True,
    check_network: bool = True,
    check_databases: bool = True,
    check_performance: bool = True,
) -> ValidationReport
```

**Parameters**:
- `vmcraft_instance`: Launched VMCraft instance with mounted filesystems
- `check_services`: Enable service validation (default: True)
- `check_network`: Enable network validation (default: True)
- `check_databases`: Enable database validation (default: True)
- `check_performance`: Enable performance benchmarking (default: True)

**Returns**: `ValidationReport` object containing all check results

**Example**:
```python
report = orchestrator.validate_migration(
    vmcraft,
    check_services=True,
    check_network=True,
    check_databases=False,  # Skip database checks
    check_performance=True
)

print(f"Overall status: {report.overall_status}")
print(f"Total checks: {report.total_checks}")
print(f"Passed: {report.passed_checks}")
print(f"Failed: {report.failed_checks}")
print(f"Warnings: {report.warnings}")
```

---

#### generate_markdown_report()

Generate human-readable Markdown report.

**Signature**:
```python
def generate_markdown_report(self, report: ValidationReport) -> str
```

**Parameters**:
- `report`: ValidationReport object from validate_migration()

**Returns**: Formatted Markdown string

**Example**:
```python
markdown = orchestrator.generate_markdown_report(report)
print(markdown)
```

**Output**:
```markdown
# Migration Validation Report

**Generated**: 2026-01-27 10:30:45
**Overall Status**: ✅ PASS

## Summary

- **Total Checks**: 15
- **Passed**: 13
- **Failed**: 0
- **Warnings**: 2
- **Skipped**: 0

## System Health Checks

### ✓ PASS: Boot configuration valid
- **Type**: SYSTEM
- **Description**: Bootloader configured correctly for KVM

### ✓ PASS: Kernel modules available
- **Type**: SYSTEM
- **Description**: Required kernel modules present (virtio_net, virtio_blk)

...
```

---

#### save_report()

Save validation reports to files.

**Signature**:
```python
def save_report(
    self,
    report: ValidationReport,
    output_dir: Path,
    *,
    json_report: bool = True,
    markdown_report: bool = True
) -> dict[str, str]
```

**Parameters**:
- `report`: ValidationReport object
- `output_dir`: Directory to save reports
- `json_report`: Generate JSON report (default: True)
- `markdown_report`: Generate Markdown report (default: True)

**Returns**: Dict mapping report type to file path

**Example**:
```python
from pathlib import Path

reports = orchestrator.save_report(
    report,
    Path("/reports/migration-001"),
    json_report=True,
    markdown_report=True
)

print(f"JSON: {reports['json']}")
# Output: JSON: /reports/migration-001/validation-report.json

print(f"Markdown: {reports['markdown']}")
# Output: Markdown: /reports/migration-001/validation-report.md
```

---

### HealthChecker

**Purpose**: System health checks (boot, fstab, kernel modules)

**Import**:
```python
from h2kvm.validation import HealthChecker
```

**Constructor**:
```python
HealthChecker(logger: logging.Logger | None = None)
```

---

#### check_system_boot()

Verify boot configuration is valid for KVM.

**Signature**:
```python
def check_system_boot(self, vmcraft_instance) -> HealthCheckResult
```

**Returns**: `HealthCheckResult` with status and details

**Example**:
```python
checker = HealthChecker(logger)
result = checker.check_system_boot(vmcraft)

if result.status == HealthCheckStatus.PASS:
    print("✓ Boot configuration valid")
else:
    print(f"✗ Boot check failed: {result.message}")
```

---

#### check_fstab_valid()

Validate fstab entries are accessible.

**Signature**:
```python
def check_fstab_valid(self, vmcraft_instance) -> HealthCheckResult
```

**Returns**: `HealthCheckResult` with fstab validation status

**Example**:
```python
result = checker.check_fstab_valid(vmcraft)

if result.status == HealthCheckStatus.PASS:
    print("✓ All fstab UUIDs found")
    print(f"Entries: {result.details['entries']}")
else:
    print(f"✗ Missing UUIDs: {result.details['missing_uuids']}")
```

---

#### check_kernel_modules()

Check required kernel modules are available.

**Signature**:
```python
def check_kernel_modules(
    self,
    vmcraft_instance,
    required_modules: list[str] | None = None
) -> HealthCheckResult
```

**Parameters**:
- `vmcraft_instance`: VMCraft instance
- `required_modules`: List of required modules (default: virtio modules)

**Returns**: `HealthCheckResult` with module availability

**Example**:
```python
result = checker.check_kernel_modules(
    vmcraft,
    required_modules=["virtio_net", "virtio_blk", "virtio_scsi"]
)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ Modules available: {result.details['available_modules']}")
```

---

### ServiceValidator

**Purpose**: Validate critical services are enabled and configured

**Import**:
```python
from h2kvm.validation import ServiceValidator
```

**Constructor**:
```python
ServiceValidator(logger: logging.Logger | None = None)
```

---

#### validate_critical_services()

Validate critical services are enabled.

**Signature**:
```python
def validate_critical_services(
    self,
    vmcraft_instance,
    services: list[str] | None = None
) -> HealthCheckResult
```

**Parameters**:
- `vmcraft_instance`: VMCraft instance
- `services`: List of service names (default: sshd, NetworkManager)

**Returns**: `HealthCheckResult` with service status

**Example**:
```python
validator = ServiceValidator(logger)
result = validator.validate_critical_services(
    vmcraft,
    services=["sshd", "NetworkManager", "firewalld"]
)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ Services enabled: {result.details['enabled_services']}")
elif result.status == HealthCheckStatus.WARN:
    print(f"⚠ Some services not found: {result.details['not_found']}")
```

---

#### check_service_enabled()

Check if specific service is enabled.

**Signature**:
```python
def check_service_enabled(
    self,
    vmcraft_instance,
    service_name: str
) -> ServiceCheckResult
```

**Parameters**:
- `vmcraft_instance`: VMCraft instance
- `service_name`: Service name to check

**Returns**: `ServiceCheckResult` with detailed service status

**Example**:
```python
result = validator.check_service_enabled(vmcraft, "postgresql")

print(f"Enabled: {result.enabled}")
print(f"Active: {result.active}")
print(f"State: {result.state}")
```

---

### NetworkValidator

**Purpose**: Validate network configuration

**Import**:
```python
from h2kvm.validation import NetworkValidator
```

**Constructor**:
```python
NetworkValidator(logger: logging.Logger | None = None)
```

---

#### check_network_interfaces()

Validate network interfaces are configured.

**Signature**:
```python
def check_network_interfaces(self, vmcraft_instance) -> HealthCheckResult
```

**Returns**: `HealthCheckResult` with interface configuration

**Example**:
```python
validator = NetworkValidator(logger)
result = validator.check_network_interfaces(vmcraft)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ Interfaces: {result.details['interfaces']}")
    print(f"Primary: {result.details['primary_interface']}")
```

---

#### check_dns_configuration()

Validate DNS nameservers are configured.

**Signature**:
```python
def check_dns_configuration(self, vmcraft_instance) -> HealthCheckResult
```

**Returns**: `HealthCheckResult` with DNS configuration

**Example**:
```python
result = validator.check_dns_configuration(vmcraft)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ DNS: {result.details['nameservers']}")
```

---

### DatabaseValidator

**Purpose**: Validate database installations and configurations

**Import**:
```python
from h2kvm.validation import DatabaseValidator
```

**Constructor**:
```python
DatabaseValidator(logger: logging.Logger | None = None)
```

---

#### validate_postgresql()

Validate PostgreSQL installation.

**Signature**:
```python
def validate_postgresql(self, vmcraft_instance) -> HealthCheckResult
```

**Returns**: `HealthCheckResult` with PostgreSQL status

**Example**:
```python
validator = DatabaseValidator(logger)
result = validator.validate_postgresql(vmcraft)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ PostgreSQL version: {result.details['version']}")
    print(f"✓ Data directory: {result.details['data_dir']}")
    print(f"✓ Config: {result.details['config_file']}")
```

---

#### validate_mysql()

Validate MySQL/MariaDB installation.

**Signature**:
```python
def validate_mysql(self, vmcraft_instance) -> HealthCheckResult
```

**Returns**: `HealthCheckResult` with MySQL status

**Example**:
```python
result = validator.validate_mysql(vmcraft)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ MySQL version: {result.details['version']}")
    print(f"✓ Data directory: {result.details['data_dir']}")
```

---

### PerformanceValidator

**Purpose**: Benchmark disk I/O performance

**Import**:
```python
from h2kvm.validation import PerformanceValidator
```

**Constructor**:
```python
PerformanceValidator(logger: logging.Logger | None = None)
```

---

#### benchmark_disk_io()

Benchmark disk I/O performance.

**Signature**:
```python
def benchmark_disk_io(
    self,
    vmcraft_instance,
    test_size_mb: int = 100
) -> HealthCheckResult
```

**Parameters**:
- `vmcraft_instance`: VMCraft instance
- `test_size_mb`: Size of test file in MB (default: 100)

**Returns**: `HealthCheckResult` with performance metrics

**Example**:
```python
validator = PerformanceValidator(logger)
result = validator.benchmark_disk_io(vmcraft, test_size_mb=500)

if result.status == HealthCheckStatus.PASS:
    print(f"✓ Write speed: {result.details['write_speed_mbps']} MB/s")
    print(f"✓ Read speed: {result.details['read_speed_mbps']} MB/s")
```

---

## Data Structures

### HealthCheckStatus

**Enum**: Status of a health check

```python
class HealthCheckStatus(Enum):
    PASS = "pass"    # Check passed successfully
    FAIL = "fail"    # Check failed, critical issue
    WARN = "warn"    # Check passed with warnings
    SKIP = "skip"    # Check skipped (not applicable)
    ERROR = "error"  # Check could not complete
```

### HealthCheckType

**Enum**: Type of health check

```python
class HealthCheckType(Enum):
    SYSTEM = "system"             # System health
    SERVICE = "service"           # Service status
    NETWORK = "network"           # Network configuration
    DATABASE = "database"         # Database status
    APPLICATION = "application"   # Application status
    STORAGE = "storage"           # Storage configuration
    SECURITY = "security"         # Security checks
    PERFORMANCE = "performance"   # Performance benchmarks
```

### HealthCheckResult

**Dataclass**: Result of a single health check

```python
@dataclass
class HealthCheckResult:
    check_type: HealthCheckType
    status: HealthCheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
```

**Example**:
```python
result = HealthCheckResult(
    check_type=HealthCheckType.SYSTEM,
    status=HealthCheckStatus.PASS,
    message="Boot configuration valid",
    details={"bootloader": "grub2", "config_file": "/boot/grub/grub.cfg"}
)
```

### ValidationReport

**Dataclass**: Complete validation report

```python
@dataclass
class ValidationReport:
    overall_status: str  # "PASS", "FAIL", "WARN"
    health_checks: list[HealthCheckResult]
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: int
    skipped_checks: int
    timestamp: str
    duration_seconds: float
```

---

## Complete Example

```python
import logging
from pathlib import Path
from h2kvm.vmcraft import VMCraft
from h2kvm.validation import ValidationOrchestrator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate migrated VM
def validate_vm(disk_path: str, output_dir: str) -> bool:
    """Validate migrated VM and generate reports."""

    # Launch VMCraft
    vmcraft = VMCraft(logger)
    vmcraft.add_disk(disk_path)
    vmcraft.launch()

    try:
        # Create orchestrator
        orchestrator = ValidationOrchestrator(logger)

        # Run validation
        logger.info("Running validation checks...")
        report = orchestrator.validate_migration(
            vmcraft,
            check_services=True,
            check_network=True,
            check_databases=True,
            check_performance=True
        )

        # Log summary
        logger.info(f"Validation complete:")
        logger.info(f"  Total checks: {report.total_checks}")
        logger.info(f"  Passed: {report.passed_checks}")
        logger.info(f"  Failed: {report.failed_checks}")
        logger.info(f"  Warnings: {report.warnings}")
        logger.info(f"  Overall: {report.overall_status}")

        # Save reports
        reports = orchestrator.save_report(
            report,
            Path(output_dir),
            json_report=True,
            markdown_report=True
        )

        logger.info(f"Reports saved:")
        logger.info(f"  JSON: {reports['json']}")
        logger.info(f"  Markdown: {reports['markdown']}")

        # Return success if passed
        return report.overall_status == "PASS"

    finally:
        # Always shutdown VMCraft
        vmcraft.shutdown()

# Example usage
if __name__ == "__main__":
    success = validate_vm(
        "/vms/migrated/web-server.qcow2",
        "/reports/web-server-validation"
    )

    if success:
        print("✓ Validation passed - VM is ready for production")
    else:
        print("✗ Validation failed - review reports before deployment")
```

---

## See Also

- **[Migration Validation Guide](../features/migration-validation.md)**: Feature documentation
- **[Rollback API](rollback-api.md)**: Rollback failed migrations
- **[VMCraft API](vmcraft-api.md)**: Guest filesystem manipulation
- **[Troubleshooting Guide](../guides/troubleshooting.md)**: Resolve validation failures

---

**Last Updated**: March 2026
**API Version**: 1.0.0
