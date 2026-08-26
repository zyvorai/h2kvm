# Validation Framework Guide

## Overview

The validation framework provides a comprehensive system for verifying converted VMs meet quality and correctness standards. It supports multiple validators, severity levels, and detailed reporting.

## Features

- **Extensible Architecture**: Easy to create custom validators
- **Severity Levels**: INFO, WARNING, ERROR, CRITICAL
- **Detailed Reporting**: Per-check results with suggestions
- **Multiple Validators**: Run multiple validators in sequence
- **Aggregate Reporting**: Combined results across all validators
- **Built-in Validators**: Disk and XML validation out of the box

## Quick Start

### Basic Usage

```python
from h2kvm.validation import DiskValidator, XMLValidator, ValidationRunner

# Create runner
runner = ValidationRunner()

# Add validators
runner.add_validator(DiskValidator())
runner.add_validator(XMLValidator())

# Run validation
context = {
    "output_path": "/output/vm-disk.qcow2",
    "format": "qcow2",
    "xml_path": "/output/domain.xml",
}

reports = runner.run_all(context)

# Check results
for report in reports:
    summary = report.get_summary()
    print(f"{summary['validator']}: {summary['passed']}/{summary['total_checks']} passed")

    if summary['has_errors']:
        print(f"  Errors: {summary['errors']}, Critical: {summary['critical']}")
```

## Built-in Validators

### 1. DiskValidator

Validates disk files and properties.

**Checks**:
- Disk file exists
- Disk size (minimum size check)
- Non-zero size
- Disk is readable

**Context Parameters**:
```python
context = {
    "output_path": "/path/to/disk.qcow2",  # Required
    "format": "qcow2",                      # Required
    "minimum_size": 1073741824,             # Optional (bytes)
}
```

**Example**:
```python
from h2kvm.validation import DiskValidator

validator = DiskValidator()
report = validator.validate({
    "output_path": "/output/vm-disk.qcow2",
    "format": "qcow2",
    "minimum_size": 1 * 1024 * 1024 * 1024,  # 1GB minimum
})

if report.has_errors():
    for error in report.get_issues_by_severity(ValidationSeverity.ERROR):
        print(f"Error: {error.message}")
        for suggestion in error.suggestions:
            print(f"  Suggestion: {suggestion}")
```

### 2. XMLValidator

Validates libvirt domain XML files.

**Checks**:
- XML file exists
- XML is well-formed
- Root element is 'domain'
- Domain has name
- Domain has disk devices

**Context Parameters**:
```python
context = {
    "xml_path": "/path/to/domain.xml",  # Required
}
```

**Example**:
```python
from h2kvm.validation import XMLValidator

validator = XMLValidator()
report = validator.validate({
    "xml_path": "/output/domain.xml",
})

print(f"XML validation: {report.passed_checks}/{report.total_checks} passed")
```

## Severity Levels

### ValidationSeverity Enum

```python
from h2kvm.validation import ValidationSeverity

ValidationSeverity.INFO      # Informational message
ValidationSeverity.WARNING   # Non-critical issue
ValidationSeverity.ERROR     # Critical issue that may prevent VM boot
ValidationSeverity.CRITICAL  # Severe issue that will prevent VM boot
```

**Interpretation**:

- **INFO**: Everything is OK, informational only
- **WARNING**: Issue detected but VM may still work
- **ERROR**: Significant issue that may prevent VM from booting
- **CRITICAL**: Severe issue that will definitely prevent VM from booting

## Creating Custom Validators

### Simple Custom Validator

```python
from h2kvm.validation import BaseValidator, ValidationSeverity

class NetworkValidator(BaseValidator):
    """Validates network configuration."""

    def validate(self, context):
        import time
        start_time = time.time()

        # Get context
        network_count = context.get("network_count", 0)

        # Check 1: Has networks
        if network_count > 0:
            self._add_result(
                check_name="has_networks",
                passed=True,
                severity=ValidationSeverity.INFO,
                message=f"Domain has {network_count} network(s)",
            )
        else:
            self._add_result(
                check_name="has_networks",
                passed=False,
                severity=ValidationSeverity.WARNING,
                message="Domain has no networks",
                suggestions=["Add at least one network interface"],
            )

        # Set duration and return
        self.report.duration = time.time() - start_time
        return self.report

# Use custom validator
validator = NetworkValidator()
report = validator.validate({"network_count": 2})
```

### Advanced Custom Validator

```python
from h2kvm.validation import BaseValidator, ValidationSeverity
from pathlib import Path

class BootValidator(BaseValidator):
    """Validates boot configuration."""

    def validate(self, context):
        import time
        start_time = time.time()

        firmware = context.get("firmware", "bios")
        boot_disk = context.get("boot_disk")

        # Check 1: Boot disk specified
        if boot_disk:
            self._add_result(
                "boot_disk_specified",
                True,
                ValidationSeverity.INFO,
                f"Boot disk: {boot_disk}",
            )

            # Check 2: Boot disk exists
            if Path(boot_disk).exists():
                self._add_result(
                    "boot_disk_exists",
                    True,
                    ValidationSeverity.INFO,
                    "Boot disk file exists",
                )
            else:
                self._add_result(
                    "boot_disk_exists",
                    False,
                    ValidationSeverity.CRITICAL,
                    f"Boot disk not found: {boot_disk}",
                    suggestions=[
                        "Check disk conversion completed",
                        "Verify disk path is correct",
                    ],
                )
        else:
            self._add_result(
                "boot_disk_specified",
                False,
                ValidationSeverity.ERROR,
                "No boot disk specified",
                suggestions=["Specify boot_disk in context"],
            )

        # Check 3: Firmware type
        if firmware in ("bios", "uefi"):
            self._add_result(
                "firmware_valid",
                True,
                ValidationSeverity.INFO,
                f"Firmware type: {firmware}",
            )
        else:
            self._add_result(
                "firmware_valid",
                False,
                ValidationSeverity.WARNING,
                f"Unknown firmware type: {firmware}",
            )

        self.report.duration = time.time() - start_time
        return self.report
```

## Validation Reports

### ValidationResult

Individual check result:

```python
from h2kvm.validation import ValidationResult, ValidationSeverity

result = ValidationResult(
    check_name="disk_size",
    severity=ValidationSeverity.ERROR,
    passed=False,
    message="Disk too small: 500MB < 1GB",
    details={"actual_mb": 500, "required_mb": 1024},
    suggestions=[
        "Increase source disk size",
        "Reduce minimum size requirement",
    ],
)

print(f"Check: {result.check_name}")
print(f"Passed: {result.passed}")
print(f"Severity: {result.severity.value}")
print(f"Message: {result.message}")
print(f"Details: {result.details}")
for suggestion in result.suggestions:
    print(f"  - {suggestion}")
```

### ValidationReport

Aggregate report from a validator:

```python
from h2kvm.validation import DiskValidator

validator = DiskValidator()
report = validator.validate(context)

# Report properties
print(f"Validator: {report.validator_name}")
print(f"Total checks: {report.total_checks}")
print(f"Passed: {report.passed_checks}")
print(f"Failed: {report.failed_checks}")
print(f"Duration: {report.duration:.2f}s")

# Check for issues
if report.has_errors():
    print("Validation failed with errors")

if report.has_warnings():
    print("Validation has warnings")

# Get summary
summary = report.get_summary()
print(f"Errors: {summary['errors']}")
print(f"Warnings: {summary['warnings']}")
print(f"Critical: {summary['critical']}")

# Get issues by severity
from h2kvm.validation import ValidationSeverity

errors = report.get_issues_by_severity(ValidationSeverity.ERROR)
for error in errors:
    print(f"ERROR: {error.message}")
```

## Validation Runner

### Running Multiple Validators

```python
from h2kvm.validation import (
    ValidationRunner,
    DiskValidator,
    XMLValidator,
)

# Create runner
runner = ValidationRunner()

# Add validators
runner.add_validator(DiskValidator())
runner.add_validator(XMLValidator())

# Custom validator
class CustomValidator(BaseValidator):
    def validate(self, context):
        # ... custom validation logic
        return self.report

runner.add_validator(CustomValidator())

# Run all validators
context = {
    "output_path": "/output/disk.qcow2",
    "format": "qcow2",
    "xml_path": "/output/domain.xml",
}

reports = runner.run_all(context)

# Process results
for report in reports:
    print(f"\n{report.validator_name}:")
    print(f"  {report.passed_checks}/{report.total_checks} passed")

    if report.has_errors():
        print("  ERRORS:")
        for error in report.get_issues_by_severity(ValidationSeverity.ERROR):
            print(f"    - {error.message}")
```

### Aggregate Summary

```python
# Get aggregate summary across all validators
summary = runner.get_aggregate_summary(reports)

print(f"Total validators: {summary['total_validators']}")
print(f"Total checks: {summary['total_checks']}")
print(f"Passed: {summary['passed']}")
print(f"Failed: {summary['failed']}")
print(f"Has errors: {summary['has_errors']}")
print(f"Has warnings: {summary['has_warnings']}")

# Per-validator summaries
for validator_summary in summary['validator_summaries']:
    print(f"\n{validator_summary['validator']}:")
    print(f"  Checks: {validator_summary['passed']}/{validator_summary['total_checks']}")
    print(f"  Errors: {validator_summary['errors']}")
    print(f"  Warnings: {validator_summary['warnings']}")
```

## Integration Examples

### Post-Conversion Validation

```python
from h2kvm.validation import ValidationRunner, DiskValidator, XMLValidator
from pathlib import Path

def validate_conversion(output_dir: Path, vm_name: str) -> bool:
    """
    Validate conversion results.

    Returns:
        True if validation passed, False otherwise
    """
    runner = ValidationRunner()
    runner.add_validator(DiskValidator())
    runner.add_validator(XMLValidator())

    context = {
        "output_path": str(output_dir / f"{vm_name}.qcow2"),
        "format": "qcow2",
        "xml_path": str(output_dir / f"{vm_name}.xml"),
        "minimum_size": 1 * 1024 * 1024 * 1024,  # 1GB
    }

    reports = runner.run_all(context)

    # Check if any validator reported errors
    has_errors = any(r.has_errors() for r in reports)

    if has_errors:
        print(f"Validation failed for {vm_name}")
        for report in reports:
            if report.has_errors():
                for error in report.get_issues_by_severity(ValidationSeverity.ERROR):
                    print(f"  ERROR: {error.message}")
                for error in report.get_issues_by_severity(ValidationSeverity.CRITICAL):
                    print(f"  CRITICAL: {error.message}")
        return False

    print(f"Validation passed for {vm_name}")
    return True
```

### Batch Validation

```python
from h2kvm.validation import ValidationRunner, DiskValidator, XMLValidator

def validate_batch(vm_list: list[dict]) -> dict:
    """
    Validate multiple VMs.

    Args:
        vm_list: List of VM dictionaries with paths

    Returns:
        Summary of validation results
    """
    runner = ValidationRunner()
    runner.add_validator(DiskValidator())
    runner.add_validator(XMLValidator())

    results = {
        "total_vms": len(vm_list),
        "passed": 0,
        "failed": 0,
        "failures": [],
    }

    for vm in vm_list:
        context = {
            "output_path": vm["disk_path"],
            "format": vm["format"],
            "xml_path": vm["xml_path"],
        }

        reports = runner.run_all(context)
        has_errors = any(r.has_errors() for r in reports)

        if has_errors:
            results["failed"] += 1
            results["failures"].append({
                "vm_name": vm["name"],
                "errors": [
                    error.message
                    for report in reports
                    for error in report.get_issues_by_severity(ValidationSeverity.ERROR)
                ],
            })
        else:
            results["passed"] += 1

    return results
```

## Best Practices

### 1. Validate After Each Stage

Validate at key points in the conversion pipeline:
- After extraction
- After fixes
- After conversion
- Before libvirt import

### 2. Use Appropriate Severity Levels

- **CRITICAL**: Issues that will definitely prevent boot (missing disk, corrupt XML)
- **ERROR**: Issues that may prevent boot (disk too small, missing firmware)
- **WARNING**: Non-critical issues (performance concerns, missing metadata)
- **INFO**: Informational messages (disk size, format detected)

### 3. Provide Actionable Suggestions

Always include suggestions for fixing issues:

```python
self._add_result(
    "disk_format",
    False,
    ValidationSeverity.ERROR,
    "Unsupported disk format: vmdk",
    suggestions=[
        "Convert disk to qcow2 format",
        "Use 'qemu-img convert' to convert format",
    ],
)
```

### 4. Add Context to Results

Include relevant details in results:

```python
self._add_result(
    "disk_size",
    True,
    ValidationSeverity.INFO,
    f"Disk size: {size_mb}MB",
    details={
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "size_gb": size_gb,
    },
)
```

### 5. Track Validation Duration

Always set duration in custom validators:

```python
def validate(self, context):
    import time
    start_time = time.time()

    # ... validation checks ...

    self.report.duration = time.time() - start_time
    return self.report
```

## Troubleshooting

### Issue: Validation Takes Too Long

**Solution**: Check which validators are slow:

```python
reports = runner.run_all(context)

for report in reports:
    if report.duration > 5.0:  # More than 5 seconds
        print(f"Slow validator: {report.validator_name} ({report.duration:.2f}s)")
```

### Issue: Too Many False Positives

**Solution**: Adjust severity levels or add more specific checks:

```python
# Instead of ERROR, use WARNING for non-critical issues
self._add_result(
    "optional_feature",
    False,
    ValidationSeverity.WARNING,  # Not ERROR
    "Optional feature not found",
)
```

### Issue: Missing Context Information

**Solution**: Validate context before running checks:

```python
def validate(self, context):
    required_keys = ["output_path", "format"]

    for key in required_keys:
        if key not in context:
            self._add_result(
                f"context_{key}",
                False,
                ValidationSeverity.CRITICAL,
                f"Missing required context key: {key}",
            )
            return self.report

    # Continue with validation...
```

## Related Documentation

- [Batch Migration Guide](../../docs/Batch-Migration-Features-Guide.md)
- [Manifest Orchestrator](../../h2kvm/manifest/orchestrator.py)
- [BaseValidator API](../../h2kvm/validation/validation_framework.py)

## Conclusion

The validation framework provides a flexible, extensible system for ensuring converted VMs meet quality standards. By using severity levels, detailed reporting, and custom validators, you can build comprehensive validation pipelines tailored to your specific requirements.
