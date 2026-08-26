# Publishing hyper2kvm to PyPI

This guide explains how to publish hyper2kvm to PyPI so users can install it with `pip install hyper2kvm`.

## Table of Contents

- [Prerequisites](#prerequisites)
- [One-Time Setup](#one-time-setup)
- [Building the Package](#building-the-package)
- [Testing with TestPyPI](#testing-with-testpypi)
- [Publishing to PyPI](#publishing-to-pypi)
- [Post-Publication](#post-publication)
- [Automated Publishing with GitHub Actions](#automated-publishing-with-github-actions)
- [Version Management](#version-management)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Install Build Tools

```bash
# Install/upgrade build tools
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade build twine
```

### Check Package Structure

Verify all required files exist:

```bash
ls -1 pyproject.toml MANIFEST.in README.md LICENSE requirements.txt setup.py
```

All files should be present.

---

## One-Time Setup

### 1. Create PyPI Accounts

Create accounts on both Test PyPI and production PyPI:

- **TestPyPI** (for testing): https://test.pypi.org/account/register/
- **PyPI** (production): https://pypi.org/account/register/

### 2. Enable Two-Factor Authentication

**Highly recommended** for security:

1. Go to Account Settings
2. Enable 2FA
3. Save recovery codes

### 3. Create API Tokens

API tokens are more secure than passwords.

#### For TestPyPI

1. Go to https://test.pypi.org/manage/account/token/
2. Click "Add API token"
3. Set scope to "Entire account" (or specific to hyper2kvm)
4. Save the token (starts with `pypi-`)

#### For Production PyPI

1. Go to https://pypi.org/manage/account/token/
2. Click "Add API token"
3. Set scope to "Entire account" (or specific to hyper2kvm)
4. Save the token

### 4. Configure Credentials

Create `~/.pypirc`:

```bash
cat >~/.pypirc <<'EOF'
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
  username = __token__
  password = pypi-YOUR-PRODUCTION-TOKEN-HERE

[testpypi]
  repository = https://test.pypi.org/legacy/
  username = __token__
  password = pypi-YOUR-TEST-TOKEN-HERE
EOF

chmod 600 ~/.pypirc
```

**Important:** Replace `pypi-YOUR-*-TOKEN-HERE` with your actual API tokens.

---

## Building the Package

### 1. Clean Previous Builds

```bash
# Remove old build artifacts
rm -rf build/ dist/ *.egg-info
```

### 2. Update Version

Edit version in **3 places**:

```bash
# 1. pyproject.toml
vim pyproject.toml  # Update version = "0.0.1" to "0.0.2" etc.

# 2. hyper2kvm/__init__.py
vim hyper2kvm/__init__.py  # Update __version__ = "0.0.1"

# 3. setup.py (if still used)
vim setup.py  # Update version="0.0.1"
```

**Pro tip:** Use a script to update all versions:

```bash
NEW_VERSION="0.0.2"

sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml
sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" hyper2kvm/__init__.py
sed -i "s/version=\".*\"/version=\"$NEW_VERSION\"/" setup.py

git diff  # Review changes
```

### 3. Build Source and Wheel Distributions

```bash
python3 -m build
```

This creates:
- `dist/hyper2kvm-0.0.1.tar.gz` (source distribution)
- `dist/hyper2kvm-0.0.1-py3-none-any.whl` (wheel)

### 4. Verify Build

```bash
# Check built files
ls -lh dist/

# Inspect wheel contents
unzip -l dist/hyper2kvm-*.whl

# Inspect tarball contents
tar tzf dist/hyper2kvm-*.tar.gz | head -20
```

### 5. Check Package Validity

```bash
# Check with twine
twine check dist/*
```

Should output: `Checking dist/... PASSED`

---

## Testing with TestPyPI

**Always test with TestPyPI first** before publishing to production.

### 1. Upload to TestPyPI

```bash
twine upload --repository testpypi dist/*
```

### 2. Test Installation

```bash
# Create test virtual environment
python3 -m venv /tmp/test-hyper2kvm
source /tmp/test-hyper2kvm/bin/activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    hyper2kvm

# Test the package
hyper2kvm --version
hyper2kvm --help

# Test library import
python3 -c "import hyper2kvm; print(hyper2kvm.__version__)"

# Test library API
python3 <<'EOF'
from hyper2kvm import GuestDetector, DiskProcessor
print("✓ Library imports work!")
EOF

# Cleanup
deactivate
rm -rf /tmp/test-hyper2kvm
```

### 3. View on TestPyPI

Visit: https://test.pypi.org/project/hyper2kvm/

Verify:
- Package metadata looks correct
- README renders properly
- Links work
- Classifiers are appropriate

---

## Publishing to PyPI

Once testing passes, publish to production PyPI.

### 1. Final Checks

```bash
# Ensure you're on main branch
git branch

# Ensure working tree is clean
git status

# Verify version is correct
grep version pyproject.toml
grep __version__ hyper2kvm/__init__.py

# Re-check package
twine check dist/*
```

### 2. Create Git Tag

```bash
VERSION="0.0.1"

git tag -a "v${VERSION}" -m "Release v${VERSION}"
git push origin "v${VERSION}"
```

### 3. Upload to PyPI

```bash
twine upload dist/*
```

### 4. Verify Publication

Visit: https://pypi.org/project/hyper2kvm/

### 5. Test Installation from PyPI

```bash
# Fresh environment
python3 -m venv /tmp/test-pypi-hyper2kvm
source /tmp/test-pypi-hyper2kvm/bin/activate

# Install from production PyPI
pip install hyper2kvm

# Test
hyper2kvm --version
python3 -c "import hyper2kvm; print(hyper2kvm.__version__)"

# Cleanup
deactivate
rm -rf /tmp/test-pypi-hyper2kvm
```

---

## Post-Publication

### 1. Create GitHub Release

Go to: https://github.com/ssahani/hyper2kvm/releases/new

- **Tag:** `v0.0.1`
- **Title:** `v0.0.1 - Initial Release`
- **Description:**
  ```markdown
  ## What's New

  - Initial public release
  - Full library API support
  - VMware, Azure, Hyper-V support
  - Comprehensive documentation

  ## Installation

  ```bash
  pip install hyper2kvm
  ```

  ## Documentation

  - [Library API](https://github.com/ssahani/hyper2kvm/blob/main/docs/08-Library-API.md)
  - [Quick Start](https://github.com/ssahani/hyper2kvm/blob/main/docs/03-Quick-Start.md)
  ```

- **Attach Files:** Upload `dist/` files

### 2. Announce the Release

- Update README.md with PyPI installation instructions
- Post on relevant forums/communities
- Tweet/blog about it

### 3. Monitor

- Watch for issues on GitHub
- Monitor PyPI download stats: https://pypistats.org/packages/hyper2kvm

---

## Automated Publishing with GitHub Actions

Automate releases with GitHub Actions.

### Create `.github/workflows/publish-pypi.yml`

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  build-and-publish:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'

    - name: Install build tools
      run: |
        python -m pip install --upgrade pip
        pip install build twine

    - name: Build package
      run: python -m build

    - name: Check package
      run: twine check dist/*

    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

### Configure Secrets

1. Go to: https://github.com/ssahani/hyper2kvm/settings/secrets/actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token
5. Click "Add secret"

### Usage

```bash
# Create and push a tag
git tag -a v0.0.2 -m "Release v0.0.2"
git push origin v0.0.2

# Create GitHub release (via UI or gh CLI)
gh release create v0.0.2 \
  --title "v0.0.2" \
  --notes "Bug fixes and improvements"

# GitHub Actions will automatically:
# - Build the package
# - Run checks
# - Publish to PyPI
```

---

## Version Management

### Semantic Versioning

Follow [SemVer](https://semver.org/):

- **MAJOR** (1.0.0): Breaking API changes
- **MINOR** (0.1.0): New features, backward compatible
- **PATCH** (0.0.1): Bug fixes, backward compatible

### Pre-release Versions

For testing:

```bash
# Alpha release
version = "0.1.0a1"

# Beta release
version = "0.1.0b1"

# Release candidate
version = "0.1.0rc1"
```

### Version Update Checklist

Before each release:

- [ ] Update version in `pyproject.toml`
- [ ] Update version in `hyper2kvm/__init__.py`
- [ ] Update version in `setup.py`
- [ ] Update version in `hyper2kvm.spec` (for RPM)
- [ ] Update `CHANGELOG.md` (if exists)
- [ ] Update README.md if needed
- [ ] Run tests
- [ ] Build and check package
- [ ] Test with TestPyPI
- [ ] Create git tag
- [ ] Publish to PyPI
- [ ] Create GitHub release

---

## Troubleshooting

### "File already exists" Error

PyPI doesn't allow re-uploading the same version. Solutions:

1. **Increment version** (recommended):
   ```bash
   # Change 0.0.1 to 0.0.2
   ```

2. **Use a post-release** (for urgent fixes):
   ```bash
   version = "0.0.1.post1"
   ```

### Authentication Errors

```bash
# Check ~/.pypirc exists and has correct format
cat ~/.pypirc

# Verify token is correct (starts with pypi-)
# Regenerate token if needed
```

### Package Not Found After Upload

Wait a few minutes - PyPI indexing takes time. Check:

```bash
# Check PyPI project page
curl -s https://pypi.org/pypi/hyper2kvm/json | jq -r '.info.version'
```

### Import Errors After Installation

Verify package structure:

```bash
# Check wheel contents
unzip -l dist/hyper2kvm-*.whl | grep -E "\.py$"

# Should include all hyper2kvm/* files
```

### "Invalid distribution" Error

```bash
# Ensure pyproject.toml is valid
python3 <<EOF
import tomllib
with open('pyproject.toml', 'rb') as f:
    print(tomllib.load(f))
EOF
```

### README Not Rendering

Ensure README.md uses standard markdown (not GitHub-specific features).

Test locally:

```bash
pip install readme-renderer
python3 -m readme_renderer README.md
```

---

## Quick Reference

### Full Release Workflow

```bash
# 1. Update version
VERSION="0.0.2"
sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
sed -i "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" hyper2kvm/__init__.py

# 2. Clean and build
rm -rf build/ dist/ *.egg-info
python3 -m build

# 3. Check
twine check dist/*

# 4. Test with TestPyPI
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ hyper2kvm

# 5. Tag and publish
git tag -a "v${VERSION}" -m "Release v${VERSION}"
git push origin "v${VERSION}"
twine upload dist/*

# 6. Verify
pip install --upgrade hyper2kvm
hyper2kvm --version
```

---

## Resources

- **PyPI:** https://pypi.org/
- **TestPyPI:** https://test.pypi.org/
- **Packaging Guide:** https://packaging.python.org/
- **Twine Docs:** https://twine.readthedocs.io/
- **SemVer:** https://semver.org/

---

**Status:** Ready for PyPI publication
