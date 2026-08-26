#!/bin/bash
#
# Post-create script for hyper2kvm development container
# Runs after the container is created to set up the development environment

set -e

echo "=== hyper2kvm Development Container Setup ==="
echo

# Install project in development mode
echo "📦 Installing hyper2kvm in development mode..."
pip install -e ".[dev,test]" --no-cache-dir

echo

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "✅ Pre-commit hooks installed"
else
    echo "⚠️  pre-commit not found, skipping hook installation"
fi

echo

# Verify installation
echo "🔍 Verifying installation..."
python -c "import hyper2kvm; print(f'hyper2kvm version: {hyper2kvm.__version__}')" || echo "⚠️  hyper2kvm import failed"

echo

# Check tools
echo "🛠️  Checking development tools..."
ruff --version
mypy --version
pytest --version

echo

# Run initial tests to verify environment
echo "🧪 Running quick test verification..."
pytest tests/unit/ -x --maxfail=3 -q || echo "⚠️  Some tests failed (this may be expected in dev container)"

echo

# Display environment info
echo "ℹ️  Environment Information:"
echo "   Python: $(python --version)"
echo "   Pip: $(pip --version | cut -d' ' -f2)"
echo "   Working directory: $(pwd)"
echo "   User: $(whoami)"

echo

# Display helpful commands
echo "✨ Development container ready!"
echo
echo "📚 Helpful commands:"
echo "   ruff format .              # Format code"
echo "   ruff check .               # Lint code"
echo "   mypy hyper2kvm/            # Type check"
echo "   pytest tests/unit/         # Run unit tests"
echo "   pytest --cov=hyper2kvm     # Run tests with coverage"
echo "   pre-commit run --all-files # Run all pre-commit hooks"
echo
echo "🎉 Happy coding!"
