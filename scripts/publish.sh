#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Quick publish script for h2kvm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

print_step() {
    echo "==> $1"
}

print_error() {
    echo "ERROR: $1"
}

print_warning() {
    echo "WARNING: $1"
}

# Parse arguments
MODE="${1:-test}"  # test or prod

if [[ "$MODE" != "test" && "$MODE" != "prod" ]]; then
    echo "Usage: $0 [test|prod]"
    echo ""
    echo "  test - Upload to TestPyPI (default)"
    echo "  prod - Upload to production PyPI"
    exit 1
fi

# Get current version
CURRENT_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
print_step "Current version: $CURRENT_VERSION"

# Clean build artifacts
print_step "Cleaning build artifacts..."
rm -rf build/ dist/ *.egg-info

# Install/upgrade build tools
print_step "Ensuring build tools are installed..."
python3 -m pip install --break-system-packages --upgrade pip build twine 2>/dev/null || python3 -m pip install --upgrade pip build twine

# Build package
print_step "Building package..."
python3 -m build

# Check package
print_step "Checking package..."
twine check dist/*

# List built files
print_step "Built files:"
ls -lh dist/

# Upload
if [[ "$MODE" == "test" ]]; then
    print_step "Uploading to TestPyPI..."
    twine upload --repository testpypi dist/*

    print_step "Package uploaded to TestPyPI!"
    echo ""
    echo "Test installation:"
    echo "  python3 -m venv /tmp/test-env"
    echo "  source /tmp/test-env/bin/activate"
    echo "  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ h2kvm"
    echo "  h2kvmctl --version"
    echo "  deactivate"
    echo ""
    echo "View on TestPyPI: https://test.pypi.org/project/h2kvm/"

else
    print_step "Uploading to production PyPI..."

    echo ""
    read -p "Are you sure you want to publish to PRODUCTION PyPI? (yes/no): " confirm

    if [[ "$confirm" != "yes" ]]; then
        print_error "Aborted by user"
        exit 1
    fi

    # Check git status
    if [[ -n $(git status --porcelain) ]]; then
        print_warning "Working directory is not clean!"
        git status --short
        echo ""
        read -p "Continue anyway? (yes/no): " continue_dirty
        if [[ "$continue_dirty" != "yes" ]]; then
            exit 1
        fi
    fi

    # Upload to PyPI first (tag after successful upload)
    twine upload dist/*

    # Create git tag after successful upload
    TAG_NAME="v${CURRENT_VERSION}"
    if ! git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
        print_step "Creating git tag: $TAG_NAME"
        git tag -a "$TAG_NAME" -m "Release $TAG_NAME"
        git push origin "$TAG_NAME"
    else
        print_warning "Tag $TAG_NAME already exists"
    fi

    print_step "Package published to PyPI!"
    echo ""
    echo "Installation:"
    echo "  pip install h2kvm"
    echo ""
    echo "View on PyPI: https://pypi.org/project/h2kvm/"
    echo ""
    echo "Next steps:"
    echo "  1. Create GitHub release: https://github.com/ssahani/h2kvm/releases/new"
    echo "  2. Announce the release"
    echo "  3. Update documentation"
fi
