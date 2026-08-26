# Building and Testing hyper2kvm

This document explains how to build, test, and develop hyper2kvm using the modern Python toolchain.

## Quick Start

```bash
# For enterprise users familiar with Make
make help          # Show all available commands
make test          # Run tests
make install       # Install the package

# For Python developers
pip install hatch
hatch run test     # Run tests
hatch run lint     # Run linting
hatch build        # Build package
```

## Build System

hyper2kvm uses a **hybrid build system**:

- **Hatch** - Modern Python project manager (primary)
- **Makefile** - Enterprise-friendly wrapper around Hatch

This approach provides:
- ✅ Modern Python tooling for developers
- ✅ Familiar `make` commands for sysadmins
- ✅ Single source of truth (`pyproject.toml`)
- ✅ Cross-platform support

## Build Prerequisites

```bash
# System dependencies (all distros)
sudo ./scripts/install-deps.sh --all

# Or manually:
sudo dnf install libguestfs-tools python3-libguestfs qemu-img   # Fedora/RHEL
sudo apt install libguestfs-tools python3-guestfs qemu-utils    # Ubuntu/Debian
```

## Installation Methods

### 1. Virtual Environment (Recommended for All Distros)

```bash
# Works on Fedora, RHEL, Ubuntu, Debian, SUSE
sudo ./scripts/install-venv.sh              # /opt/hyper2kvm
sudo ./scripts/install-venv.sh /custom/path # custom location
./scripts/install-venv.sh --user            # ~/.local/hyper2kvm (no root)
```

See [venv-install.md](venv-install.md) for full details.

### 2. RPM (Fedora / RHEL / CentOS / Rocky / Alma)

```bash
sudo rm -rf dist/ build/ *.egg-info
python3 -m build --wheel --no-isolation
rpmbuild -bb hyper2kvm.spec
sudo rpm -Uvh ~/rpmbuild/RPMS/noarch/hyper2kvm-*.rpm
```

See [rpm-build.md](rpm-build.md) for full details.

### 3. DEB (Ubuntu / Debian)

```bash
# Build inside container (works from any host)
./scripts/build-deb.sh ubuntu:24.04
sudo apt install -y ./dist/hyper2kvm_*.deb
```

See [deb-build.md](deb-build.md) for full details.

### 4. Editable Install (Development)

```bash
pip install hatch
pip install -e .[dev,full]

# Or using Make
make quickstart
```

## Testing

### Using Make

```bash
make test              # Run unit tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-all          # All tests
make test-cov          # Tests with coverage report
make test-matrix       # Test across Python 3.10, 3.11, 3.12
```

### Using Hatch

```bash
hatch run test              # Run unit tests
hatch run test-unit         # Unit tests only
hatch run test-integration  # Integration tests
hatch run test-all          # All tests
hatch run test-cov          # With coverage
hatch run test-cov-all      # Coverage for all tests
```

### Using pytest directly

```bash
pytest tests/unit/ -v
pytest tests/unit/ --cov=hyper2kvm --cov-report=html
pytest tests/integration/ -v
```

## Code Quality

### Using Make

```bash
make lint        # Run ruff + mypy
make fmt         # Auto-format code
make fmt-check   # Check formatting without changes
make security    # Run security scans (bandit + safety)
```

### Using Hatch

```bash
hatch run lint              # Linting
hatch run fmt               # Format code
hatch run fmt-check         # Check formatting
hatch run security          # Security scans
hatch run security-audit    # Generate security report
```

## Building

### Source and Wheel Distribution

```bash
# Using Make
make build

# Using Hatch
hatch build

# Using Python directly
python -m build
```

Output: `dist/hyper2kvm-{version}.tar.gz` and `dist/hyper2kvm-{version}-py3-none-any.whl`

### RPM Package (Fedora/RHEL)

```bash
# Using Make
make rpm

# Manually
python3 -m build --sdist
rpmbuild -ba hyper2kvm.spec
```

## Publishing

### To PyPI

```bash
# Using Hatch (recommended)
export HATCH_INDEX_USER=__token__
export HATCH_INDEX_AUTH=pypi-...
hatch publish

# Using Make
make publish

# To TestPyPI first
make publish-test
```

## CI/CD Pipeline

### Full CI Check

```bash
# Using Make
make ci          # test-cov + lint + security

# Using Hatch
hatch run ci     # Same as above

# Individual checks
make check       # test + lint + security (without coverage)
```

### CI Usage (GitHub Actions)

```yaml
- name: Run tests
  run: hatch run test

- name: Run linting
  run: hatch run lint

- name: Full CI pipeline
  run: hatch run ci
```

## Development Workflow

### 1. Setup Development Environment

```bash
# Clone repository
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

# Install in development mode
make dev-install
# OR
pip install -e .[dev,full]
```

### 2. Make Changes

Edit code in `hyper2kvm/` directory.

### 3. Test Changes

```bash
# Quick test
make test

# Full check before commit
make check
```

### 4. Format Code

```bash
make fmt
```

### 5. Commit

```bash
git add .
git commit -m "Your changes"
```

## Environment Management

### Hatch Environments

Hatch manages isolated environments defined in `pyproject.toml`:

- **default** - Standard development environment
- **dev** - Development with docs tools
- **test** - Matrix testing environment (Python 3.10, 3.11, 3.12)

```bash
# Show all environments
hatch env show

# Run command in specific environment
hatch -e dev run docs-build

# Remove all environments (clean slate)
hatch env prune

# Create environment
hatch env create
```

### Available Scripts

All scripts are defined in `pyproject.toml` under `[tool.hatch.envs.default.scripts]`:

| Command | Description |
|---------|-------------|
| `test` | Run unit tests |
| `test-unit` | Unit tests only |
| `test-integration` | Integration tests |
| `test-all` | All tests |
| `test-cov` | Tests with coverage |
| `test-cov-all` | Coverage for all tests |
| `lint` | Ruff + mypy linting |
| `fmt` | Format code with ruff |
| `fmt-check` | Check formatting |
| `security` | Bandit + safety scans |
| `security-audit` | Generate security JSON report |
| `check` | test + lint + security |
| `ci` | test-cov + lint + security |

## Cleaning

```bash
# Clean build artifacts
make clean

# Clean everything (including test data)
make clean-all

# Using Hatch
hatch clean
```

## Documentation

### Build Documentation

```bash
# Using Make
make docs
make docs-serve  # Serve on http://localhost:8000

# Using Hatch
hatch run docs-build
hatch run docs-serve

# Manually
cd man && make html
```

## Troubleshooting

### Hatch Not Found

```bash
# Install hatch
pip install hatch

# Or the Makefile will auto-install it
make test
```

### Coverage Report Not Generated

```bash
# Make sure you're using test-cov target
make test-cov

# Report will be in htmlcov/index.html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Import Errors in Tests

```bash
# Reinstall in development mode
pip install -e .

# Or
make dev-install
```

### Matrix Testing Fails

```bash
# Install all Python versions (using pyenv)
pyenv install 3.10 3.11 3.12
pyenv local 3.10 3.11 3.12

# Run matrix tests
hatch run test:run
```

## Migration from Old Setup

If you're migrating from the old setup:

```bash
# Old way
pytest tests/unit/ -v
ruff check hyper2kvm/
mypy hyper2kvm/

# New way (Make)
make test
make lint

# New way (Hatch)
hatch run test
hatch run lint
```

## References

- **Hatch Documentation**: https://hatch.pypa.io/
- **PyPA Python Packaging Guide**: https://packaging.python.org/
- **GNU Make Manual**: https://www.gnu.org/software/make/manual/

## Summary

| Task | Make | Hatch |
|------|------|-------|
| Run tests | `make test` | `hatch run test` |
| Test with coverage | `make test-cov` | `hatch run test-cov` |
| Lint code | `make lint` | `hatch run lint` |
| Format code | `make fmt` | `hatch run fmt` |
| Security scan | `make security` | `hatch run security` |
| Build package | `make build` | `hatch build` |
| Install dev mode | `make dev-install` | `pip install -e .[dev,full]` |
| Clean artifacts | `make clean` | `hatch clean` |
| Full CI check | `make ci` | `hatch run ci` |

**Recommendation**: Use `make` for quick commands, use `hatch` for advanced features and environment management.
