#!/bin/bash
#
# Release automation script
#
# Usage:
#   ./scripts/release.sh 1.2.3       # Create release v1.2.3
#   ./scripts/release.sh --check     # Check if ready for release

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Functions
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ Error: $1 not found"
        exit 1
    fi
}

check_clean_git() {
    if [ -n "$(git status --porcelain)" ]; then
        echo "❌ Error: Working directory not clean"
        git status --short
        exit 1
    fi
}

check_branch() {
    local branch=$(git branch --show-current)
    if [ "$branch" != "main" ]; then
        echo "⚠️  Warning: Not on main branch (currently on: $branch)"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Check if this is a check run
if [ "${1:-}" == "--check" ]; then
    echo "🔍 === Release Readiness Check ==="
    echo

    # Check tools
    echo "🛠️  Checking required tools..."
    check_command git
    check_command python3
    check_command pip
    echo "✅ All required tools present"
    echo

    # Check git status
    echo "📝 Checking git status..."
    check_clean_git
    check_branch
    echo "✅ Git status clean"
    echo

    # Check tests pass
    echo "🧪 Running tests..."
    if pytest tests/unit/ -q; then
        echo "✅ All tests pass"
    else
        echo "❌ Some tests failed"
        exit 1
    fi
    echo

    # Check code quality
    echo "🔍 Checking code quality..."
    if ruff check . && ruff format --check . && mypy h2kvm/; then
        echo "✅ Code quality checks pass"
    else
        echo "❌ Code quality checks failed"
        exit 1
    fi
    echo

    echo "🎉 Ready for release!"
    exit 0
fi

# Check version argument
if [ -z "${1:-}" ]; then
    echo "Usage: $0 <version> or $0 --check"
    echo "Example: $0 1.2.3"
    exit 1
fi

VERSION="${1:-}"

# Validate version format
if ! [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ Error: Invalid version format"
    echo "Expected format: MAJOR.MINOR.PATCH (e.g., 1.2.3)"
    exit 1
fi

echo "🚀 === Creating Release v$VERSION ==="
echo

# Pre-flight checks
echo "🔍 Running pre-flight checks..."
check_command git
check_command python3
check_clean_git
check_branch

# Run tests
echo "🧪 Running tests..."
if ! pytest tests/unit/ -q; then
    echo "❌ Tests failed"
    exit 1
fi
echo "✅ Tests passed"
echo

# Run code quality checks
echo "🔍 Running code quality checks..."
if ! ruff check . || ! ruff format --check . || ! mypy h2kvm/; then
    echo "❌ Code quality checks failed"
    exit 1
fi
echo "✅ Code quality passed"
echo

# Update version in all files
echo "📝 Updating version..."
"$SCRIPT_DIR/bump-version.sh" "$VERSION"
echo "✅ Version updated"
echo

# Confirm release
echo "⚡ Ready to create release v$VERSION"
echo
echo "This will:"
echo "  1. 📝 Commit version bump"
echo "  2. 🏷️  Create git tag v$VERSION"
echo "  3. 🚀 Push to remote"
echo
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Release cancelled"
    exit 1
fi

# Commit version bump (bump-version.sh updates pyproject.toml, __init__.py, setup.py, h2kvm.spec)
if [ -n "$(git status --porcelain)" ]; then
    git add pyproject.toml h2kvm/__init__.py
    [ -f setup.py ] && git add setup.py
    [ -f h2kvm.spec ] && git add h2kvm.spec
    git commit -m "chore: bump version to $VERSION"
fi

# Create tag
echo "🏷️  Creating git tag v$VERSION..."
git tag -a "v$VERSION" -m "Release v$VERSION"
echo "✅ Tag created"
echo

# Push
echo "🚀 Pushing to remote..."
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$CURRENT_BRANCH"
git push origin "v$VERSION"
echo "✅ Pushed to remote"
echo

echo "🎉 === Release v$VERSION Complete ==="
echo
echo "📋 Next steps:"
echo "  1. ⚙️  GitHub Actions will build and publish to PyPI"
echo "  2. 📝 Update CHANGELOG.md with release notes"
echo "  3. 📢 Create GitHub release with notes"
