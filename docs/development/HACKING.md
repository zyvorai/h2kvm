# Developer Guide

**Welcome to h2kvm development!**

This guide will help you get started with contributing to h2kvm.

---

## Quick Start

### Prerequisites

- Python 3.9+ (3.12+ recommended)
- libvirt development headers
- QEMU/KVM
- Git

### Development Setup

```bash
# Clone repository
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e .[dev,test]

# Install pre-commit hooks
pre-commit install

# Verify installation
python -c "import h2kvm; print(h2kvm.__version__)"
pytest tests/unit/ -v
```

---

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/issue-123
```

### 2. Make Changes

Follow [CODING_STYLE.md](CODING_STYLE.md) for code standards.

**Key points**:

- Add type hints to all functions
- Write docstrings (NumPy/Google style)
- Keep functions <50 lines
- Maximum line length: 109 characters

### 3. Run Quality Checks

```bash
# Format code (automatic)
ruff format .

# Fix linting issues (automatic)
ruff check --fix .

# Type check
mypy h2kvm/

# Run unit tests
pytest tests/unit/

# Run with coverage
pytest --cov=h2kvm --cov-report=html
```

### 4. Write Tests

All new code must have tests:

```python
# tests/unit/test_mymodule.py
import pytest
from h2kvm.mymodule import my_function

class TestMyFunction:
    """Tests for my_function()."""

    def test_success_case(self):
        """Should return expected result for valid input."""
        result = my_function("input")
        assert result == "expected"

    def test_error_case(self):
        """Should raise ValueError for invalid input."""
        with pytest.raises(ValueError, match="invalid"):
            my_function("bad_input")
```

### 5. Commit Changes

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
git add .
git commit -m "feat: add new NBD device manager"
# or
git commit -m "fix: resolve race condition in LVM activation"
# or
git commit -m "docs: update API documentation"
```

**Pre-commit hooks run automatically**:

- Ruff formatting
- Ruff linting
- YAML/JSON validation
- Security scanning (Bandit)
- Type checking (Mypy)
- Secret detection
- Spell checking

### 6. Push and Create PR

```bash
git push origin feature/my-feature
```

Then create PR on GitHub.

---

## Project Structure

```text
h2kvm/
├── core/              # Foundation (utilities, logging, validation)
├── vmcraft/           # VM analysis/modification API
│   ├── block_device.py   # Loop device + NBD manager
│   ├── storage.py        # LVM activation with isolation
│   └── ...
├── providers/         # Source providers (VMware, Azure, backup)
├── converters/        # Disk conversion engines
├── fixers/            # Post-migration fixes
├── libvirt/           # Target platform (KVM/libvirt)
├── luks/              # LUKS auto-unlock (TPM2, Vault)
├── pipeline/          # End-to-end conversion pipelines
├── orchestration/     # Workflow coordination
├── runtime/           # Job management (daemon, worker, operator)
├── platforms/         # Platform-specific features
├── quality/           # Validation & compliance
├── cli/               # Command-line interface
├── tui/               # Terminal UI
└── infrastructure/    # Supporting services

tests/
├── unit/              # Fast unit tests (mocked)
├── integration/       # Integration tests (real resources)
├── fuzz/              # Fuzzing test data
└── benchmarks/        # Performance tests
```

---

## Testing

### Test Categories

Run specific test categories:

```bash
# Unit tests only (fast, run in CI)
pytest tests/unit/

# Integration tests (slower, requires resources)
pytest tests/integration/

# Specific module
pytest tests/unit/test_vmcraft/

# Specific test
pytest tests/unit/test_vmcraft/test_block_device.py::TestLoopDevice::test_attach_success

# With coverage
pytest --cov=h2kvm --cov-report=html

# Parallel execution (faster)
pytest -n auto
```

### Test Markers

Use markers to categorize tests:

```python
import pytest

@pytest.mark.unit
def test_fast_unit_test():
    """Fast test with mocking."""
    pass

@pytest.mark.integration
@pytest.mark.requires_libvirt
def test_integration_with_libvirt():
    """Integration test requiring libvirt."""
    pass

@pytest.mark.slow
def test_long_running():
    """Test that takes >5 seconds."""
    pass
```

Run by marker:

```bash
# Only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Only integration tests
pytest -m integration
```

### Writing Good Tests

**Structure**: Arrange-Act-Assert

```python
def test_activate_lvm_success(mock_run_sudo):
    """Should activate VG successfully."""
    # Arrange - Set up test data and mocks
    mock_run_sudo.return_value = Mock(returncode=0, stdout="")
    device = "/dev/nbd0"
    vg_name = "vg-root"

    # Act - Execute the function
    result = activate_lvm(device, vg_name)

    # Assert - Verify the results
    assert result.success
    assert len(result.logical_volumes) > 0
    mock_run_sudo.assert_called_once()
```

**Coverage Goals**:

- New code: 100% coverage
- Modified code: Maintain or improve coverage
- Overall target: 90%+

---

## Code Quality

### Ruff (Linter + Formatter)

Ruff enforces code quality automatically:

```bash
# Format code
ruff format .

# Check linting
ruff check .

# Auto-fix issues
ruff check --fix .

# Check specific file
ruff check h2kvm/vmcraft/storage.py
```

Configuration: `ruff.toml`

### Mypy (Type Checker)

Type hints are required:

```bash
# Check all code
mypy h2kvm/

# Check specific file
mypy h2kvm/vmcraft/storage.py

# Show error codes
mypy --show-error-codes h2kvm/
```

Configuration: `mypy.ini`

### Pre-commit Hooks

Hooks run automatically on `git commit`:

```bash
# Run manually on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files

# Update hook versions
pre-commit autoupdate

# Skip hooks (emergency only)
git commit --no-verify
```

Configuration: `.pre-commit-config.yaml`

---

## Debugging

### Enable Debug Logging

```bash
export H2KVM_LOG_LEVEL=DEBUG
h2kvm-migrate ...
```

### Interactive Debugging

```python
# Use built-in debugger
import pdb; pdb.set_trace()

# Or use ipdb (better interface)
import ipdb; ipdb.set_trace()

# Or use breakpoint() (Python 3.7+)
breakpoint()
```

### Run in Container

For isolated testing:

```bash
docker run -v $PWD:/workspace -it python:3.12 bash
cd /workspace
pip install -e .[dev]
pytest tests/unit/
```

---

## Common Tasks

### Add New Module

1. Create module file: `h2kvm/mymodule.py`
2. Add type hints and docstrings
3. Create test file: `tests/unit/test_mymodule.py`
4. Write comprehensive tests
5. Update `__init__.py` if needed
6. Run quality checks

### Fix Bug

1. Create failing test that reproduces bug
2. Fix the bug
3. Verify test passes
4. Check for similar issues
5. Update documentation if needed

### Add New Feature

1. Discuss design in issue/PR
2. Write tests first (TDD)
3. Implement feature
4. Verify all tests pass
5. Update documentation
6. Add example usage

### Update Dependencies

```bash
# Update development dependencies
pip install --upgrade pip setuptools wheel
pip install --upgrade ruff mypy pytest pre-commit

# Update pre-commit hooks
pre-commit autoupdate

# Test with new versions
pytest tests/unit/
```

---

## Release Process

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Creating a Release

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create git tag: `git tag -a v1.2.0 -m "Release v1.2.0"`
4. Push tag: `git push origin v1.2.0`
5. GitHub Actions will build and publish to PyPI

---

## Getting Help

### Documentation

- [CODING_STYLE.md](CODING_STYLE.md) - Coding standards
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
- [CODE_METRICS.md](../CODE_METRICS.md) - Code quality metrics
- [API Documentation](https://h2kvm.readthedocs.io) - Online docs

### Community

- **GitHub Issues**: <https://github.com/ssahani/h2kvm/issues>
- **GitHub Discussions**: <https://github.com/ssahani/h2kvm/discussions>
- **Pull Requests**: <https://github.com/ssahani/h2kvm/pulls>

### Asking Questions

When asking for help, include:

1. What you're trying to do
2. What you've tried
3. Error messages (full traceback)
4. Environment (OS, Python version, h2kvm version)
5. Minimal reproducible example

---

## Tips and Tricks

### Fast Test Iteration

```bash
# Run only failed tests from last run
pytest --lf

# Run failed tests first, then others
pytest --ff

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l
```

### EditorConfig

Your editor will automatically use correct formatting if it supports
EditorConfig (`.editorconfig`).

Supported editors: VS Code, PyCharm, Vim, Emacs, Sublime, Atom

### VS Code Setup

Install extensions:

- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)
- Mypy Type Checker (ms-python.mypy-type-checker)

Settings (`.vscode/settings.json`):

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  },
  "python.testing.pytestEnabled": true
}
```

### PyCharm Setup

1. Settings → Tools → Ruff
   - Enable Ruff formatter
2. Settings → Tools → Python Integrated Tools
   - Default test runner: pytest
3. Settings → Editor → Code Style → Python
   - Set line length to 109

---

## Advanced Topics

### Performance Profiling

```bash
# Profile with cProfile
python -m cProfile -o profile.stats h2kvm/cli/main.py

# Visualize with snakeviz
pip install snakeviz
snakeviz profile.stats
```

### Memory Profiling

```bash
# Install memory_profiler
pip install memory_profiler

# Profile function
python -m memory_profiler script.py
```

### Coverage Analysis

```bash
# Generate coverage report
pytest --cov=h2kvm --cov-report=html

# Open in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## Continuous Integration

### GitHub Actions

Our CI runs:

- Ruff formatting check
- Ruff linting
- Mypy type checking
- Pytest (unit tests)
- Coverage reporting
- Security scanning

See `.github/workflows/` for configuration.

### Local CI Simulation

```bash
# Run what CI will run
ruff format --check .
ruff check .
mypy h2kvm/
pytest tests/unit/ --cov=h2kvm
```

---

## Troubleshooting

### Pre-commit Hook Failures

```bash
# See what failed
git commit  # Shows which hooks failed

# Fix issues
ruff format .
ruff check --fix .

# Try again
git commit
```

### Import Errors

```bash
# Reinstall in development mode
pip install -e .[dev,test]

# Check installation
python -c "import h2kvm; print(h2kvm.__file__)"
```

### Test Failures

```bash
# Run with verbose output
pytest -vv tests/unit/test_mymodule.py

# Show local variables
pytest -l tests/unit/test_mymodule.py

# Drop into debugger on failure
pytest --pdb tests/unit/test_mymodule.py
```

---

## Best Practices

### ✅ Do

- Write tests for all new code
- Add type hints to functions
- Keep functions small (<50 lines)
- Use meaningful variable names
- Document public APIs
- Run quality checks before committing
- Ask questions when unsure

### ❌ Don't

- Commit without running tests
- Skip type hints
- Write functions >100 lines
- Use single-letter variables (except i, j, k in loops)
- Leave TODO comments without issues
- Bypass pre-commit hooks
- Assume others know context

---

## Summary

**Quick Reference**:

```bash
# Setup
pip install -e .[dev,test]
pre-commit install

# Development
ruff format .                    # Format
ruff check --fix .               # Lint
mypy h2kvm/                  # Type check
pytest tests/unit/               # Test

# Commit
git add .
git commit -m "feat: add feature"  # Pre-commit runs

# Quality
pytest --cov=h2kvm --cov-report=html
open htmlcov/index.html
```

**Ready to contribute? Check out [CONTRIBUTING.md](../CONTRIBUTING.md)!**
