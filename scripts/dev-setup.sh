#!/bin/bash
#
# Development environment setup script
#
# Usage:
#   ./scripts/dev-setup.sh              # Full setup
#   ./scripts/dev-setup.sh --minimal    # Minimal setup (no optional tools)
#   ./scripts/dev-setup.sh --check      # Check current setup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Options
MINIMAL_SETUP=false
CHECK_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --minimal)
            MINIMAL_SETUP=true
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "🚀 === h2kvm Development Setup ==="
echo

# Check Python version
echo "🐍 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    echo "❌ Python 3.9+ required, found $PYTHON_VERSION"
    exit 1
else
    echo "✅ Python $PYTHON_VERSION"
fi
echo

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  No virtual environment detected"
    echo "📦 Recommended: create and activate a virtual environment first"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ Virtual environment: $VIRTUAL_ENV"
fi
echo

if [ "$CHECK_ONLY" = true ]; then
    echo "🔍 Checking installed tools..."

    # Check each tool
    TOOLS=(
        "ruff:Ruff linter/formatter"
        "mypy:Mypy type checker"
        "pytest:Pytest testing framework"
        "pre-commit:Pre-commit hooks"
        "bandit:Bandit security scanner"
    )

    for tool_info in "${TOOLS[@]}"; do
        IFS=':' read -r tool desc <<< "$tool_info"
        if command -v "$tool" &> /dev/null; then
            version=$($tool --version 2>&1 | head -n1)
            echo "✅ $desc: $version"
        else
            echo "❌ $desc: not installed"
        fi
    done

    exit 0
fi

# Install development dependencies
echo "📦 Installing development dependencies..."
pip3 install --upgrade pip setuptools wheel
pip3 install -e ".[dev,test]"
echo "✅ Development dependencies installed"
echo

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "✅ Pre-commit hooks installed"
else
    echo "❌ pre-commit not found"
    exit 1
fi
echo

# Optional: Install additional tools
if [ "$MINIMAL_SETUP" = false ]; then
    echo "🛠️  Installing optional development tools..."

    # Install debugging tools
    pip3 install ipdb ipython || echo "Failed to install debugging tools"

    # Install profiling tools
    pip3 install memory-profiler line-profiler || echo "Failed to install profiling tools"

    # Install documentation tools
    pip3 install sphinx sphinx-rtd-theme || echo "Failed to install documentation tools"

    echo "✅ Optional tools installed"
    echo
fi

# Run initial verification
echo "🧪 Running initial verification..."

# Import check
if python3 -c "import h2kvm; print(f'h2kvm {h2kvm.__version__}')" 2>/dev/null; then
    echo "✅ h2kvm import successful"
else
    echo "❌ h2kvm import failed"
    exit 1
fi

# Run quick test
if pytest tests/unit/ -x --maxfail=1 -q 2>/dev/null; then
    echo "✅ Quick test passed"
else
    echo "⚠️  Some tests failed (this may be expected)"
fi
echo

# Display summary
echo "🎉 === Setup Complete ==="
echo
echo "📋 Next steps:"
echo "  1. 🧪 Run tests:         ./scripts/test.sh"
echo "  2. 🔍 Check code quality: ./scripts/quality.sh"
echo "  3. 🪝 Run pre-commit:    pre-commit run --all-files"
echo "  4. 💻 Start developing!"
echo
echo "📚 See docs/HACKING.md for more information"
