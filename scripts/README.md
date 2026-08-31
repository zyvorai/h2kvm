# Development Scripts

Automation scripts for common development tasks.

## Available Scripts

### `test.sh` - Test Runner

Run tests with various configurations.

```bash
# Run unit tests (default)
./scripts/test.sh

# Run all tests (unit + integration)
./scripts/test.sh --all

# Run integration tests only
./scripts/test.sh --integration

# Run with coverage report
./scripts/test.sh --coverage

# Run fastest tests only (skip slow tests)
./scripts/test.sh --fast

# Run in watch mode (requires pytest-watch)
./scripts/test.sh --watch

# Run without parallel execution
./scripts/test.sh --no-parallel

# Verbose output
./scripts/test.sh --verbose

# Quiet output
./scripts/test.sh --quiet
```

### `quality.sh` - Code Quality Checker

Run all code quality tools.

```bash
# Run all quality checks
./scripts/quality.sh

# Auto-fix issues where possible
./scripts/quality.sh --fix

# Strict mode (fail on any warnings)
./scripts/quality.sh --strict
```

Checks performed:

- Ruff format check/fix
- Ruff lint check/fix
- Mypy type checking
- Bandit security scan
- TODO comment validation
- Print statement detection
- Debugger statement detection

### `coverage.sh` - Coverage Reporter

Generate and display coverage reports.

```bash
# Generate coverage report
./scripts/coverage.sh

# Generate HTML report and open in browser
./scripts/coverage.sh --html

# Fail if coverage below threshold
./scripts/coverage.sh --fail-under 90
```

Generates:

- Terminal report with missing lines
- HTML report (`htmlcov/index.html`)
- XML report (`coverage.xml`) for CI

### `dev-setup.sh` - Development Setup

Set up development environment.

```bash
# Full setup (recommended)
./scripts/dev-setup.sh

# Minimal setup (no optional tools)
./scripts/dev-setup.sh --minimal

# Check current setup
./scripts/dev-setup.sh --check
```

Performs:

- Python version check
- Virtual environment check
- Install development dependencies
- Install pre-commit hooks
- Install optional tools (debugging, profiling, documentation)
- Run initial verification tests

### `release.sh` - Release Automation

Automate release process.

```bash
# Check if ready for release
./scripts/release.sh --check

# Create release v1.2.3
./scripts/release.sh 1.2.3
```

Release checklist:

- ✅ Git working directory clean
- ✅ On main branch
- ✅ All tests pass
- ✅ Code quality checks pass
- ✅ Version updated in `pyproject.toml`
- ✅ Git tag created
- ✅ Pushed to remote

### `install-deps.sh` - Dependency Installer

Install runtime dependencies and optional components.

```bash
# Install VirtIO Windows drivers ISO to standard path
# Downloads virtio-win.iso to /var/lib/h2kvm/virtio-win.iso
# This is auto-discovered by h2kvm for Windows migrations
# (no --virtio-drivers-dir flag needed)
./scripts/install-deps.sh --virtio-win
```

### `deploy-local.sh` - Local Deployment

Build and deploy h2kvm on this machine.

```bash
./scripts/deploy-local.sh              # full install (system deps + pip + h2kweb)
./scripts/deploy-local.sh --quick      # pip install + services only
./scripts/deploy-local.sh --uninstall  # remove h2kvm
```

What it does:
1. pip install h2kvm from source (with `--break-system-packages` for PEP 668)
2. Copy h2kvmctl to `/usr/local/bin/`
3. Build h2kweb dashboard (Go + React)
4. Install systemd services (h2kvm daemon + h2kweb)
5. Auto-link libguestfs for the active Python version
6. Verify installation (tools, modules, services)

### `deploy-remote.sh` - Remote Server Deployment

Full deployment to a remote server via SSH/rsync. **Full guide:** [docs/deployment/deploy-remote.md](../docs/deployment/deploy-remote.md)

```bash
./scripts/deploy-remote.sh <host> [user] [password] [options]
./scripts/deploy-remote.sh 175.110.122.71 sus --keep-sources --quick --skip-dashboard
```

What it does:
1. Rsync repo to `~/.deployments/h2kvm` on remote
2. Auto-detect container/orchestration runtime (k3s, k8s, docker, podman, libvirt)
3. Run quickstart.sh (system packages) — full mode only
4. Run install-deps.sh (hivex, boto3, virtio-win) — full mode only
5. `pip install .[full]` — requires **`hypersdk-guestkit>=1.1.0`** (build maturin wheel from GuestKit source if PyPI lags)
6. Copy h2kvmctl to `/usr/local/bin/`, install h2kweb + systemd daemon
7. Verify installation

**Deploy GuestKit CLI separately** from the GuestKit repo (`./scripts/deploy-remote.sh`).

Features:
- `--keep-sources` — retain checkout for maturin rebuilds
- `--skip-dashboard` — skip h2kweb when only CLI needed
- `--quick` — skip system deps
- `--uninstall` — remove pip package and checkout
- Sets `/var/lib/h2kvm` mode **755** for QEMU read access

Environment variables: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PASS`, `DEPLOY_DIR`

---

## See Also

- [HACKING.md](../docs/HACKING.md) - Developer guide
- [CODING_STYLE.md](../docs/CODING_STYLE.md) - Coding standards
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
