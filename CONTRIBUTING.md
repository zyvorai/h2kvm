# Contributing to h2kvm

Thank you for your interest in contributing to h2kvm! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/h2kvm.git
   cd h2kvm
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/ssahani/h2kvm.git
   ```

## Development Setup

### Python Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install in development mode with all dependencies
pip install -e ".[dev,test]"

# Install pre-commit hooks
pre-commit install
```

### Go Development (for operator)

```bash
cd operator

# Download dependencies
go mod download

# Install controller-gen
make controller-gen
```

### System Dependencies

**Debian/Ubuntu:**
```bash
sudo apt install qemu-system-x86 qemu-utils libguestfs-tools python3-guestfs
```

**RHEL/Fedora:**
```bash
sudo dnf install qemu-system-x86 qemu-img libguestfs-tools python3-libguestfs
```

## Making Changes

### 1. Create a Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/issue-123
```

Branch naming conventions:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `perf/description` - Performance improvements
- `test/description` - Test improvements

### 2. Make Your Changes

- Write clear, concise code
- Follow existing code style
- Add tests for new functionality
- Update documentation as needed

### 3. Write Tests

All new code should include tests:

**Python tests:**
```bash
# Run all tests
pytest

# Run specific test file
pytest h2kvm/vmspawn/tests/test_machine.py

# Run with coverage
pytest --cov=h2kvm
```

**Go tests:**
```bash
cd operator
go test ./...
```

### 4. Update Documentation

If your changes affect user-facing functionality:

- Update relevant docs in `docs/`
- Update API reference if needed
- Add examples if appropriate
- Update CHANGELOG.md

## Testing

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests
make test-integration

# Operator tests
make test-operator

# With coverage
make test-coverage
```

### Writing Tests

**Unit tests:**
```python
import pytest
from h2kvm.vmspawn import Machine, MachineConfig

def test_machine_creation():
    """Test basic machine creation."""
    config = MachineConfig(name="test", image="/path/to/image.qcow2")
    machine = Machine(config)
    assert machine.config.name == "test"
```

**Integration tests:**
```python
@pytest.mark.integration
@pytest.mark.requires_kvm
def test_vm_boot():
    """Test actual VM boot (requires KVM)."""
    config = MachineConfig(name="test", image="/images/test.qcow2")
    machine = Machine(config)
    machine.start()
    assert machine.is_running()
    machine.stop()
```

### Performance Tests

Run benchmarks before and after changes:

```bash
# Baseline
pytest h2kvm/vmspawn/tests/test_performance.py \
    --benchmark-only \
    --benchmark-save=before

# After changes
pytest h2kvm/vmspawn/tests/test_performance.py \
    --benchmark-only \
    --benchmark-compare=before
```

## Code Style

### Python

We use **ruff** for linting and formatting:

```bash
# Check code style
ruff check h2kvm/

# Fix automatically
ruff check --fix h2kvm/

# Format code
ruff format h2kvm/

# Type checking
mypy h2kvm/
```

**Style guidelines:**
- Line length: 100 characters
- Use type hints
- Document all public APIs
- Follow PEP 8

**Example:**
```python
def validate_vm(
    config: MachineConfig,
    timeout: int = 300,
) -> ValidationResult:
    """Validate a VM configuration.
    
    Args:
        config: VM configuration to validate
        timeout: Validation timeout in seconds
        
    Returns:
        ValidationResult with success status and checks
        
    Raises:
        VMStartError: If VM fails to start
        ValidationError: If validation fails
    """
    # Implementation
```

### Go

We follow standard Go conventions:

```bash
# Format code
gofmt -s -w .

# Lint
golangci-lint run

# Vet
go vet ./...
```

**Style guidelines:**
- Use gofmt
- Follow [Effective Go](https://golang.org/doc/effective_go.html)
- Document exported functions
- Use meaningful variable names

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Tests
- `perf`: Performance improvement
- `refactor`: Code refactoring
- `chore`: Maintenance

**Examples:**

```
feat: add TPM support to vmspawn SDK

Implement TPM emulation using swtpm for VMs that require
secure boot validation.

Closes #123
```

```
fix: handle timeout in async validation

Previously, async validation could hang indefinitely. Now
properly raises TimeoutError after configured timeout.

Fixes #456
```

```
docs: add tutorials for batch validation

Add step-by-step tutorial showing how to validate 100 VMs
in parallel using AsyncVMManager.
```

## Pull Request Process

### 1. Update Your Branch

```bash
# Fetch latest changes
git fetch upstream

# Rebase onto main
git rebase upstream/main
```

### 2. Push Changes

```bash
git push origin feature/my-feature
```

### 3. Create Pull Request

- Go to GitHub and create a PR
- Fill in the PR template
- Link related issues
- Request review from maintainers

### 4. PR Checklist

- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Code style checks pass
- [ ] No merge conflicts
- [ ] Commits are signed (optional but recommended)

### 5. Code Review

- Address reviewer feedback
- Make requested changes
- Push updates to the same branch
- Re-request review when ready

### 6. Merging

Once approved, maintainers will merge your PR. We use:
- **Squash and merge** for most PRs
- **Rebase and merge** for large feature branches
- **Merge commit** for release branches

## Development Workflow

### Typical Workflow

```bash
# 1. Update main
git checkout main
git pull upstream main

# 2. Create feature branch
git checkout -b feature/my-feature

# 3. Make changes
# ... edit files ...

# 4. Test changes
make test

# 5. Commit
git add .
git commit -m "feat: add my feature"

# 6. Push
git push origin feature/my-feature

# 7. Create PR on GitHub
```

### Running CI Locally

Before pushing, run the same checks as CI:

```bash
# Python checks
make ci-python

# Operator checks
make ci-operator

# All checks
make ci-all
```

## Reporting Issues

### Bug Reports

Include:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment (OS, Python version, etc.)
- Stack traces or error messages

### Feature Requests

Include:
- Description of the feature
- Use case and motivation
- Proposed implementation (optional)
- Examples of usage

## Getting Help

- **Email**: info@lilotechnologies.com
- **Phone**: +91 9999379738

Bug reports and feature requests: https://github.com/ssahani/h2kvm/issues

## License

By contributing, you agree that your contributions will be licensed under the Proprietary (Zyvor AI Labs) License.

## Thank You!

Your contributions make h2kvm better for everyone. Thank you for taking the time to contribute!
