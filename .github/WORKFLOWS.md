# .github Directory

This directory contains GitHub-specific configuration and automation for the hyper2kvm project.

## 📁 Directory Structure

```
.github/
├── workflows/              # GitHub Actions CI/CD workflows
│   ├── tests.yml          # Automated testing (unit, integration)
│   ├── security.yml       # Security scanning (Bandit, dependency audit)
│   ├── release.yml        # Release automation and PyPI publishing
│   ├── docs.yml           # Documentation building and deployment
│   └── README.md          # Workflow documentation
├── ISSUE_TEMPLATE/        # Issue templates
│   ├── bug_report.md      # Bug report template
│   └── feature_request.md # Feature request template
├── PULL_REQUEST_TEMPLATE.md  # PR template with checklist
├── dependabot.yml         # Dependabot configuration
└── markdown-link-check-config.json  # Link validation config
```

## 🚀 Quick Start

### For Contributors

When you create a PR, the following will run automatically:
- ✅ Unit tests on Python 3.10, 3.11, 3.12
- 🔍 Code linting (ruff) and type checking (mypy)
- 🔒 Security scanning (Bandit, pip-audit)
- 📝 Documentation validation

### For Maintainers

**Creating a Release:**
```bash
# Tag a new version
git tag v1.2.3
git push origin v1.2.3

# This automatically:
# - Creates a GitHub release
# - Builds Python packages
# - Publishes to PyPI (if configured)
```

## 🛠️ Configuration

### Required Secrets

Add these in **Settings → Secrets and variables → Actions**:

| Secret | Purpose | Required |
|--------|---------|----------|
| `PYPI_API_TOKEN` | Publish releases to PyPI | For releases |
| `CODECOV_TOKEN` | Upload coverage reports | Optional (public repos) |

### Branch Protection

Recommended settings for `main` branch:
- ✅ Require pull request before merging
- ✅ Require status checks to pass (Tests, Lint)
- ✅ Require branches to be up to date
- ✅ Require linear history
- ✅ Include administrators

## 📊 Status Badges

Add to README.md:

```markdown
![Tests](https://github.com/ssahani/hyper2kvm/workflows/Tests/badge.svg)
![Security](https://github.com/ssahani/hyper2kvm/workflows/Security%20Checks/badge.svg)
[![codecov](https://codecov.io/gh/ssahani/hyper2kvm/branch/main/graph/badge.svg)](https://codecov.io/gh/ssahani/hyper2kvm)
```

## 🔄 Workflow Details

### Tests Workflow (tests.yml)
- **Trigger**: Push, PR to main/develop
- **Matrix**: Python 3.10, 3.11, 3.12
- **Coverage**: Uploaded from Python 3.12
- **Runtime**: ~5-10 minutes

### Security Workflow (security.yml)
- **Trigger**: Push to main, PRs, Weekly (Monday 00:00 UTC)
- **Tools**: Bandit, pip-audit, dependency-review
- **Runtime**: ~2-3 minutes

### Release Workflow (release.yml)
- **Trigger**: Tags matching `v*.*.*`
- **Actions**: Build, Release, PyPI publish
- **Runtime**: ~3-5 minutes

### Documentation Workflow (docs.yml)
- **Trigger**: Push/PR to docs, markdown files
- **Actions**: Link checking, Sphinx build, GitHub Pages deploy
- **Runtime**: ~2-4 minutes

## 🔧 Local Development

Run checks locally before pushing:

```bash
# Install dev dependencies
pip install pytest pytest-cov ruff mypy bandit

# Run full test suite
python -m pytest tests/unit/ -v --cov=hyper2kvm

# Check code quality
ruff check hyper2kvm/
mypy hyper2kvm/ --ignore-missing-imports

# Security scan
bandit -r hyper2kvm/

# Check documentation links
markdown-link-check README.md
```

## 📝 Issue & PR Guidelines

### Creating Issues
- Use the appropriate template (Bug Report or Feature Request)
- Provide detailed reproduction steps
- Include environment information
- Attach logs and configuration (sanitized)

### Creating Pull Requests
- Fill out the PR template completely
- Link related issues
- Ensure all CI checks pass
- Request review from maintainers
- Keep PRs focused and atomic

## 🤖 Dependabot

Dependabot automatically:
- Updates GitHub Actions weekly
- Updates Python dependencies weekly
- Creates PRs with changelogs
- Groups related updates

**Managing Dependabot PRs:**
```bash
# Review and merge
gh pr review <PR-number> --approve
gh pr merge <PR-number> --auto --squash

# Or use GitHub web interface
```

## 📚 Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [PyPI Publishing Guide](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
