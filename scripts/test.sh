#!/bin/bash
#
# Test runner script - Run tests with various configurations
#
# Usage:
#   ./scripts/test.sh              # Run unit tests
#   ./scripts/test.sh --all        # Run all tests
#   ./scripts/test.sh --integration # Run integration tests only
#   ./scripts/test.sh --coverage   # Run with coverage report
#   ./scripts/test.sh --fast       # Run fastest tests only
#   ./scripts/test.sh --watch      # Run in watch mode (requires pytest-watch)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Default options
RUN_UNIT=true
RUN_INTEGRATION=false
RUN_COVERAGE=false
RUN_FAST=false
RUN_WATCH=false
PARALLEL=true
VERBOSITY="-v"
EXTRA_ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            RUN_UNIT=true
            RUN_INTEGRATION=true
            shift
            ;;
        --integration)
            RUN_UNIT=false
            RUN_INTEGRATION=true
            shift
            ;;
        --coverage)
            RUN_COVERAGE=true
            shift
            ;;
        --fast)
            RUN_FAST=true
            PARALLEL=true
            shift
            ;;
        --watch)
            RUN_WATCH=true
            shift
            ;;
        --no-parallel)
            PARALLEL=false
            shift
            ;;
        --verbose)
            VERBOSITY="-vv"
            shift
            ;;
        --quiet)
            VERBOSITY="-q"
            shift
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ Error: pytest not found"
    echo "📦 Install with: pip install -e .[dev,test]"
    exit 1
fi

echo "🧪 === h2kvm Test Runner ==="
echo

# Build pytest command
PYTEST_CMD="pytest"
PYTEST_ARGS=()

# Add verbosity
PYTEST_ARGS+=("$VERBOSITY")

# Add parallel execution
if [ "$PARALLEL" = true ]; then
    PYTEST_ARGS+=("-n" "auto")
fi

# Add coverage
if [ "$RUN_COVERAGE" = true ]; then
    PYTEST_ARGS+=(
        "--cov=h2kvm"
        "--cov-report=term-missing:skip-covered"
        "--cov-report=html"
        "--cov-report=xml"
    )
fi

# Add markers for fast tests
if [ "$RUN_FAST" = true ]; then
    PYTEST_ARGS+=("-m" "not slow")
fi

# Add extra arguments
PYTEST_ARGS+=("${EXTRA_ARGS[@]}")

# Run tests based on options
if [ "$RUN_WATCH" = true ]; then
    echo "👀 Running in watch mode..."
    if ! command -v ptw &> /dev/null; then
        echo "❌ Error: pytest-watch not installed"
        echo "📦 Install with: pip install pytest-watch"
        exit 1
    fi
    ptw -- "${PYTEST_ARGS[@]}"
elif [ "$RUN_UNIT" = true ] && [ "$RUN_INTEGRATION" = true ]; then
    echo "🔬 Running all tests..."
    $PYTEST_CMD tests/ "${PYTEST_ARGS[@]}"
elif [ "$RUN_INTEGRATION" = true ]; then
    echo "🔗 Running integration tests..."
    $PYTEST_CMD tests/integration/ "${PYTEST_ARGS[@]}"
else
    echo "⚡ Running unit tests..."
    $PYTEST_CMD tests/unit/ "${PYTEST_ARGS[@]}"
fi

# Show coverage report location if generated
if [ "$RUN_COVERAGE" = true ]; then
    echo
    echo "📊 Coverage report generated:"
    echo "  HTML: file://$PROJECT_ROOT/htmlcov/index.html"
    echo "  XML:  $PROJECT_ROOT/coverage.xml"
fi

echo
echo "✅ Tests completed"
