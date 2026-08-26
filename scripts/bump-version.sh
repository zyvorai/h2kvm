#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Version bump script for hyper2kvm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"


print_step() {
    echo "✅ ==> $1"
}

# Get current version
CURRENT_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')

echo "Current version: $CURRENT_VERSION"
echo ""

# Parse new version from argument or ask
if [[ -n "${1:-}" ]]; then
    NEW_VERSION="$1"
else
    read -p "Enter new version (e.g., 0.0.2): " NEW_VERSION
fi

# Validate version format
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(a[0-9]+|b[0-9]+|rc[0-9]+|\.post[0-9]+)?$ ]]; then
    echo "Invalid version format: $NEW_VERSION"
    echo "Expected format: X.Y.Z or X.Y.Za1 or X.Y.Zb1 or X.Y.Zrc1 or X.Y.Z.post1"
    exit 1
fi

echo "Bumping version from $CURRENT_VERSION to $NEW_VERSION"
echo ""

# Files to update
FILES=(
    "pyproject.toml"
    "hyper2kvm/__init__.py"
    "setup.py"
    "hyper2kvm.spec"
)

# Update each file
for file in "${FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "⚠ Skipping $file (not found)"
        continue
    fi

    print_step "Updating $file"

    case "$file" in
        pyproject.toml)
            sed -i.bak "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$file" && rm -f "$file.bak"
            ;;
        hyper2kvm/__init__.py)
            sed -i.bak "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$file" && rm -f "$file.bak"
            ;;
        setup.py)
            sed -i.bak "s/version=\".*\"/version=\"$NEW_VERSION\"/" "$file" && rm -f "$file.bak"
            ;;
        hyper2kvm.spec)
            sed -i.bak "s/^Version:.*$/Version:        $NEW_VERSION/" "$file" && rm -f "$file.bak"
            ;;
    esac

    # Show diff
    if git diff --quiet "$file"; then
        echo "  No changes"
    else
        echo "  Changed:"
        git diff "$file" | grep -E "^[-+].*version" || true
    fi
done

echo ""
print_step "Version bump complete!"
echo ""
echo "Review changes:"
echo "  git diff"
echo ""
echo "Commit changes:"
echo "  git add ${FILES[*]}"
echo "  git commit -m \"chore: Bump version to $NEW_VERSION\""
echo ""
echo "Next steps:"
echo "  1. Review and test"
echo "  2. Commit version bump"
echo "  3. Build and publish: ./scripts/publish.sh test"
echo "  4. If tests pass: ./scripts/publish.sh prod"
