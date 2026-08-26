# GitHub Actions Workflows

This directory contains CI/CD workflows for h2kvm.

## Workflows

### 1. Tests (`tests.yml`)
**Triggers**: Push to main/develop, Pull requests
**Purpose**: Run tests, linting, and code coverage

```yaml
Jobs:
  - test: Run unit tests on Python 3.10, 3.11, 3.12
  - lint: Run ruff + mypy
  - integration: Run integration tests (main branch only)
```

**Commands used**:
- `hatch run test` - Unit tests
- `hatch run test-cov` - Coverage report
- `hatch run lint` - Code quality

**Artifacts**: Coverage reports uploaded to Codecov

### 2. Security (`security.yml`)
**Triggers**: Push to main, PRs, weekly schedule, manual
**Purpose**: Security scanning and vulnerability detection

```yaml
Jobs:
  - security: Bandit + pip-audit scanning
  - dependency-review: Check for vulnerable dependencies (PRs only)
```

**Commands used**:
- `hatch run security-audit` - Generate JSON report
- `hatch run security` - Terminal output
- `pip-audit --desc` - Dependency vulnerabilities

**Artifacts**: Security reports

### 3. Semantic Release (`semantic-release.yml`)
**Triggers**: Push to main, manual
**Purpose**: Automated versioning and releases

```yaml
Process:
  1. Analyze commits (conventional commits)
  2. Determine version bump
  3. Update version in code
  4. Update CHANGELOG.md
  5. Create Git tag
  6. Build package
  7. Publish to PyPI
  8. Create GitHub release
```

**Environment variables**:
- `GITHUB_TOKEN` - Automatic
- `PYPI_TOKEN` - Secret (required for publishing)

**Commit format**:
```
feat: add new feature        → Minor bump (0.1.0 → 0.2.0)
fix: fix bug                 → Patch bump (0.1.0 → 0.1.1)
perf: improve performance    → Patch bump
BREAKING CHANGE: ...         → Major bump (0.1.0 → 1.0.0)
```

### 4. RPM Packaging (`rpm-packaging.yml`)
**Triggers**: Push to main/develop, PRs, manual
**Purpose**: Build and test RPM packages for Fedora

```yaml
Jobs:
  - build-rpm: Build on Fedora 41, 42, 43
  - test-installation-methods: Test install/upgrade/removal
```

**Artifacts**: RPM packages (.rpm, .src.rpm)

### 5. Documentation (`docs.yml`)
**Triggers**: Push to main, manual
**Purpose**: Build and deploy documentation

### 6. Pylint (`pylint.yml`)
**Triggers**: Push, PRs
**Purpose**: Additional code quality checks

## Badges

Add these to README.md:

```markdown
[![Tests](https://github.com/ssahani/h2kvm/workflows/tests/badge.svg)](https://github.com/ssahani/h2kvm/actions)
[![Security](https://github.com/ssahani/h2kvm/workflows/security/badge.svg)](https://github.com/ssahani/h2kvm/actions)
[![codecov](https://codecov.io/gh/ssahani/h2kvm/branch/main/graph/badge.svg)](https://codecov.io/gh/ssahani/h2kvm)
```

## Secrets Required

For full automation, configure these secrets in GitHub Settings:

1. **PYPI_TOKEN** - PyPI API token
   - Go to https://pypi.org/manage/account/token/
   - Create token with scope: "Entire account"
   - Add to GitHub: Settings → Secrets → Actions → New repository secret

2. **CODECOV_TOKEN** (optional)
   - Go to https://codecov.io/gh/ssahani/h2kvm
   - Copy token
   - Add to GitHub secrets

## Local Testing

Run workflows locally with [act](https://github.com/nektos/act):

```bash
# Install act
brew install act  # macOS
# or
sudo dnf install act  # Fedora

# Run tests workflow
act -j test

# Run security workflow
act -j security

# List all workflows
act -l
```

## Debugging Workflows

### View logs
```bash
# Via GitHub CLI
gh run list
gh run view <run-id> --log

# Or in browser
https://github.com/ssahani/h2kvm/actions
```

### Common issues

**1. Test failures**
```bash
# Run locally first
make test
hatch run test
```

**2. Security scan failures**
```bash
# Run locally
make security
```

**3. Release failures**
- Check commit message format
- Verify PYPI_TOKEN is set
- Ensure version in pyproject.toml is correct

## Workflow Permissions

Each workflow has specific permissions (GITHUB_TOKEN):

- **tests.yml**: read (default)
- **security.yml**: read, security-events write
- **semantic-release.yml**: contents write, issues write, pull-requests write
- **rpm-packaging.yml**: read (default)

## Best Practices

1. **Always test locally first**
   ```bash
   make ci  # Runs full CI pipeline locally
   ```

2. **Use conventional commits**
   ```bash
   git commit -m "feat: add feature"
   git commit -m "fix: fix bug"
   ```

3. **Check workflow status before merging**
   - All checks must pass
   - Review coverage reports

4. **Monitor automated releases**
   - Verify version bump is correct
   - Check CHANGELOG.md generation
   - Confirm PyPI publication

## Resources

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [Codecov](https://docs.codecov.com/)

---

**Last Updated**: 2026-01-18
