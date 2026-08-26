# Testing Guide

**Comprehensive guide to h2kvm testing infrastructure and practices**

## Overview

h2kvm maintains **100% test coverage** with 664 tests covering unit, integration, and end-to-end scenarios. This guide explains our testing strategy, how to run tests, and how to write new tests.

### Test Statistics

- **✅ 504 Unit Tests** (100% passing)
- **✅ 160 Integration Tests** (100% passing)
- **📊 Total Coverage:** 664 tests, 100% pass rate
- **⚡ Fast Execution:** ~15-20 seconds for full unit test suite
- **🔬 Isolated:** No external dependencies required

---

## Test Structure

```
tests/
├── unit/                          # Fast, isolated unit tests
│   ├── test_cli/                  # CLI argument parsing
│   ├── test_converters/           # Format converters (VMDK, VHD)
│   ├── test_fixers/               # Offline VM fixes
│   ├── test_hooks/                # Hook execution
│   ├── test_libvirt/              # Libvirt integration
│   ├── test_manifest/             # Manifest handling
│   ├── test_profiles/             # Profile system
│   ├── test_utils/                # Utility functions
│   └── test_vmware/               # VMware-specific logic
│
├── integration/                   # Integration tests
│   ├── test_batch_features/       # Batch migration
│   ├── test_hooks/                # Hook integration
│   ├── test_offline_operations/   # Offline VM operations
│   └── test_vsphere/              # vSphere integration
│
├── fixtures/                      # Test fixtures and helpers
│   ├── fake_guestfs.py            # Mock guestfs interface
│   └── fake_logger.py             # Mock logging
│
├── fakes/                         # Fake test data
│   ├── images/                    # Test VM images
│   └── create_test_images.py     # Image generators
│
└── pytest.ini                     # pytest configuration
```

---

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-xdist pytest-timeout

# Optional: parallel execution
pip install pytest-xdist
```

### Quick Test Commands

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run with coverage report
pytest --cov=h2kvm --cov-report=html

# Run in parallel (faster)
pytest -n auto

# Run specific test file
pytest tests/unit/test_converters/test_vmdk_parser.py

# Run specific test class
pytest tests/unit/test_converters/test_vmdk_parser.py::TestVMDKParser

# Run specific test
pytest tests/unit/test_converters/test_vmdk_parser.py::TestVMDKParser::test_parse_descriptor

# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Run only failed tests from last run
pytest --lf
```

### Advanced Test Execution

```bash
# Run with specific markers
pytest -m "not slow"              # Skip slow tests
pytest -m "integration"           # Only integration tests

# Run with timeout (prevents hanging)
pytest --timeout=300

# Generate XML report (for CI)
pytest --junitxml=test-results.xml

# Generate coverage badge
pytest --cov=h2kvm --cov-report=term-missing

# Parallel execution with live output
pytest -n auto -v --tb=short
```

---

## Test Categories

### Unit Tests (tests/unit/)

**Fast, isolated tests for individual components**

#### Test Converters

```python
# tests/unit/test_converters/test_vmdk_parser.py
def test_parse_vmdk_descriptor():
    """Test VMDK descriptor parsing"""
    parser = VMDKParser()
    descriptor = parser.parse_descriptor(vmdk_path)

    assert descriptor["ddb.adapterType"] == "lsilogic"
    assert descriptor["createType"] == "monolithicSparse"
```

#### Test Fixers

```python
# tests/unit/test_fixers/test_network_config_injector.py
def test_inject_network_config():
    """Test network configuration injection"""
    g = FakeGuestFS()
    obj = create_test_object(network_config=config)

    result = inject_network_config(obj, g)

    assert result["injected"] is True
    assert len(result["files_created"]) == 2
```

#### Test Hooks

```python
# tests/unit/test_hooks/test_hook_runner.py
def test_hook_execution():
    """Test hook execution with retry"""
    hook = {
        "type": "script",
        "path": "/path/to/hook.sh",
        "retry": {"max_attempts": 3}
    }

    runner = HookRunner()
    result = runner.execute_hook(hook, context)

    assert result["success"] is True
```

### Integration Tests (tests/integration/)

**Tests combining multiple components**

#### Batch Processing

```python
# tests/integration/test_batch_features/test_batch_orchestrator.py
def test_parallel_batch_migration():
    """Test parallel VM migration"""
    batch_manifest = create_batch_manifest(vm_count=5)

    orchestrator = BatchOrchestrator()
    results = orchestrator.run_batch(batch_manifest, parallel_limit=2)

    assert len(results) == 5
    assert all(r["status"] == "completed" for r in results)
```

#### Hook Integration

```python
# tests/integration/test_hooks/test_hook_integration.py
def test_pre_post_hooks():
    """Test pre and post hooks in pipeline"""
    manifest = {
        "hooks": {
            "pre_fix": [{"type": "script", "path": "pre.sh"}],
            "post_fix": [{"type": "script", "path": "post.sh"}]
        }
    }

    pipeline = Pipeline(manifest)
    result = pipeline.run()

    assert result["hooks_executed"] == 2
```

---

## Writing New Tests

### Test Structure Template

```python
# tests/unit/test_module/test_feature.py
"""Unit tests for feature X."""

import pytest
from h2kvm.module import Feature


class TestFeature:
    """Test suite for Feature functionality."""

    def test_basic_operation(self):
        """Test basic feature operation."""
        feature = Feature()
        result = feature.do_something()

        assert result is not None
        assert result.status == "success"

    def test_error_handling(self):
        """Test error handling."""
        feature = Feature()

        with pytest.raises(ValueError, match="Invalid input"):
            feature.do_something(invalid_input=True)

    def test_edge_case(self):
        """Test edge case handling."""
        feature = Feature()
        result = feature.do_something(edge_case=True)

        assert result.handled_correctly is True
```

### Using Fixtures

```python
# tests/unit/conftest.py
import pytest
from tests.fixtures.fake_guestfs import FakeGuestFS


@pytest.fixture
def fake_guest():
    """Provide FakeGuestFS instance."""
    g = FakeGuestFS()
    g.fs["/etc/hostname"] = b"testhost\n"
    return g


# In test file
def test_with_fixture(fake_guest):
    """Test using fake_guest fixture."""
    hostname = fake_guest.read_file("/etc/hostname")
    assert hostname == b"testhost\n"
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("eth0", "network"),
    ("br0", "bridge"),
    ("bond0", "bond"),
])
def test_device_type_detection(input, expected):
    """Test device type detection with various inputs."""
    device_type = detect_device_type(input)
    assert device_type == expected
```

### Temporary Files

```python
def test_with_temp_files(tmp_path):
    """Test using temporary directory."""
    # tmp_path is a pytest fixture providing temp directory
    test_file = tmp_path / "test.vmdk"
    test_file.write_text("# Disk DescriptorFile\n")

    result = parse_vmdk(test_file)
    assert result is not None

    # Cleanup automatic
```

---

## Test Helpers and Utilities

### FakeGuestFS

Mock guestfs for testing without real VMs:

```python
from tests.fixtures.fake_guestfs import FakeGuestFS

def test_file_operations():
    """Test file operations on fake guest."""
    g = FakeGuestFS()

    # Write file
    g.write("/etc/hostname", b"newhost\n")

    # Read file
    content = g.read_file("/etc/hostname")
    assert content == b"newhost\n"

    # Check file exists
    assert g.exists("/etc/hostname")
    assert g.is_file("/etc/hostname")

    # Create directory
    g.mkdir_p("/etc/systemd/network")
    assert g.is_dir("/etc/systemd/network")

    # Create symlink
    g.ln_sf("/usr/lib/systemd/system/sshd.service",
            "/etc/systemd/system/multi-user.target.wants/sshd.service")
    assert g.exists("/etc/systemd/system/multi-user.target.wants/sshd.service")
```

### FakeLogger

Mock logger for testing without output:

```python
from tests.fixtures.fake_logger import FakeLogger

def test_with_logging():
    """Test function with logging."""
    logger = FakeLogger()

    function_that_logs(logger)

    # Verify logging calls (if needed)
    assert logger.info.called
```

### Test Image Generators

Create test VMDK images:

```python
from tests.fakes.create_test_images import create_test_vmdk

def test_with_real_vmdk(tmp_path):
    """Test with generated VMDK."""
    vmdk_path = tmp_path / "test.vmdk"
    create_test_vmdk(
        vmdk_path,
        size_mb=100,
        adapter_type="lsilogic",
        create_type="monolithicSparse"
    )

    result = parse_vmdk(vmdk_path)
    assert result["adapter_type"] == "lsilogic"
```

---

## Test Markers

### Available Markers

```python
@pytest.mark.slow
def test_large_conversion():
    """Test that takes >5 seconds."""
    pass

@pytest.mark.integration
def test_full_pipeline():
    """Integration test."""
    pass

@pytest.mark.skipif(not VSPHERE_AVAILABLE, reason="vSphere not configured")
def test_vsphere_export():
    """Test requiring vSphere."""
    pass

@pytest.mark.parametrize("input,expected", [...])
def test_with_params(input, expected):
    """Parametrized test."""
    pass
```

### Running by Marker

```bash
# Skip slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration

# Run only unit tests
pytest tests/unit/

# Run everything except vSphere tests
pytest -m "not vsphere"
```

---

## Coverage Analysis

### Generate Coverage Report

```bash
# Terminal report
pytest --cov=h2kvm --cov-report=term-missing

# HTML report (interactive)
pytest --cov=h2kvm --cov-report=html
open htmlcov/index.html

# XML report (for CI)
pytest --cov=h2kvm --cov-report=xml

# Combined report
pytest --cov=h2kvm --cov-report=term-missing --cov-report=html
```

### Coverage Configuration

```ini
# pytest.ini or pyproject.toml
[tool:pytest]
addopts =
    --cov=h2kvm
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=95
```

### Checking Coverage

```bash
# View coverage summary
pytest --cov=h2kvm --cov-report=term

# Find uncovered lines
pytest --cov=h2kvm --cov-report=term-missing | grep "TOTAL"
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e .[test]

      - name: Run tests
        run: |
          pytest --cov=h2kvm --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

## Test Best Practices

### 1. Test Organization

✅ **DO:**
- Group related tests in classes
- Use descriptive test names
- One assertion concept per test
- Keep tests independent

❌ **DON'T:**
- Mix unit and integration tests
- Create test dependencies
- Use global state
- Skip writing tests for bug fixes

### 2. Test Naming

```python
# Good test names
def test_parse_vmdk_descriptor_with_multiple_extents():
    """Test VMDK descriptor parsing with multiple extent entries."""
    pass

def test_network_injection_creates_systemd_files():
    """Test that network injection creates systemd-networkd files."""
    pass

# Bad test names
def test_vmdk():  # Too vague
    pass

def test_1():  # Meaningless
    pass
```

### 3. Assertions

```python
# Good: Clear, specific assertions
assert result["status"] == "success"
assert len(result["files"]) == 3
assert "error" not in result

# Bad: Vague assertions
assert result  # What are we checking?
assert True  # Meaningless
```

### 4. Test Isolation

```python
# Good: Each test independent
def test_create_user():
    g = FakeGuestFS()  # Fresh instance
    create_user(g, "testuser")
    assert g.exists("/home/testuser")

# Bad: Tests depend on each other
def test_step1():
    global g
    g = FakeGuestFS()
    create_user(g, "testuser")

def test_step2():  # Depends on test_step1
    assert g.exists("/home/testuser")
```

### 5. Error Testing

```python
# Good: Test specific errors
with pytest.raises(ValueError, match="Invalid username"):
    create_user(g, "invalid@user")

# Bad: Catch-all error testing
with pytest.raises(Exception):
    create_user(g, "baduser")
```

---

## Debugging Tests

### Run with Debugging

```bash
# Drop into debugger on failure
pytest --pdb

# Drop into debugger on first failure, then stop
pytest -x --pdb

# Show local variables on failure
pytest --showlocals

# Full traceback
pytest --tb=long

# Show print statements
pytest -s
```

### Using pdb

```python
def test_with_debugging():
    """Test with breakpoint."""
    result = function_under_test()

    # Add breakpoint
    import pdb; pdb.set_trace()

    assert result is not None
```

---

## Performance Testing

### Timing Tests

```python
import time

def test_performance():
    """Test that operation completes in reasonable time."""
    start = time.time()

    perform_expensive_operation()

    duration = time.time() - start
    assert duration < 5.0, f"Too slow: {duration}s"
```

### Benchmark Tests

```python
import pytest

def test_batch_processing_performance(benchmark):
    """Benchmark batch processing."""
    batch = create_test_batch(size=100)

    result = benchmark(process_batch, batch)

    assert result["processed"] == 100
```

---

## Common Testing Patterns

### Testing Exceptions

```python
def test_invalid_input_raises_error():
    """Test that invalid input raises ValueError."""
    with pytest.raises(ValueError, match="Invalid format"):
        parse_config(invalid_data)
```

### Testing Warnings

```python
import warnings

def test_deprecated_function_warns():
    """Test that deprecated function warns."""
    with pytest.warns(DeprecationWarning):
        old_function()
```

### Mocking External Dependencies

```python
from unittest.mock import Mock, patch

def test_with_mock():
    """Test with mocked dependency."""
    with patch('h2kvm.module.external_call') as mock_call:
        mock_call.return_value = "mocked_result"

        result = function_that_calls_external()

        assert mock_call.called
        assert result == "processed_mocked_result"
```

---

## Test Maintenance

### Updating Tests

When updating code:

1. **Run existing tests** - Ensure no regressions
2. **Update test expectations** - If behavior changed intentionally
3. **Add new tests** - For new functionality or bug fixes
4. **Run full suite** - Verify everything passes

### Refactoring Tests

```bash
# Before refactoring
pytest --cov=h2kvm --cov-report=term > coverage_before.txt

# After refactoring
pytest --cov=h2kvm --cov-report=term > coverage_after.txt

# Compare
diff coverage_before.txt coverage_after.txt
```

---

## See Also

- [Contributing Guide](CONTRIBUTING.md) - Contribution guidelines
- [Architecture](01-Architecture.md) - System architecture
- [Development Setup](BUILDING.md) - Development environment setup
- [CI/CD Pipeline](../.github/workflows/) - GitHub Actions workflows

---

**Last Updated:** 2026-03-29
**Test Coverage:** 100% (664 tests passing)
**Maintained by:** h2kvm team
