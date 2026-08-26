#!/bin/bash
#
# Coverage reporter - Generate and display coverage reports
#
# Usage:
#   ./scripts/coverage.sh              # Generate coverage report
#   ./scripts/coverage.sh --html       # Generate HTML report and open
#   ./scripts/coverage.sh --fail-under 90  # Fail if coverage < 90%

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Options
GENERATE_HTML=false
OPEN_BROWSER=false
FAIL_UNDER=0
COVERAGE_ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --html)
            GENERATE_HTML=true
            OPEN_BROWSER=true
            shift
            ;;
        --fail-under)
            FAIL_UNDER="$2"
            shift 2
            ;;
        *)
            COVERAGE_ARGS+=("$1")
            shift
            ;;
    esac
done

echo "📊 === h2kvm Coverage Reporter ==="
echo

# Check if coverage is installed
if ! command -v coverage &> /dev/null; then
    echo "❌ Error: coverage not found"
    echo "📦 Install with: pip install coverage"
    exit 1
fi

# Run tests with coverage
echo "🧪 Running tests with coverage..."
pytest tests/unit/ \
    -n auto \
    --cov=h2kvm \
    --cov-report=term-missing:skip-covered \
    --cov-report=xml \
    --cov-report=html \
    "${COVERAGE_ARGS[@]}"

echo
echo "✅ Coverage data collected"
echo

# Generate coverage report
echo "📈 Coverage Summary:"
coverage report --skip-covered

# Check coverage threshold
if [ "$FAIL_UNDER" -gt 0 ]; then
    echo
    if coverage report --fail-under="$FAIL_UNDER" &>/dev/null; then
        echo "✅ Coverage meets threshold of ${FAIL_UNDER}%"
    else
        echo "❌ Coverage below threshold of ${FAIL_UNDER}%"
        exit 1
    fi
fi

# Display report locations
echo
echo "📁 Coverage reports generated:"
echo "  📄 HTML: file://$PROJECT_ROOT/htmlcov/index.html"
echo "  📄 XML:  $PROJECT_ROOT/coverage.xml"

# Open HTML report
if [ "$OPEN_BROWSER" = true ]; then
    echo
    echo "🌐 Opening HTML report in browser..."

    if command -v xdg-open &> /dev/null; then
        xdg-open htmlcov/index.html
    elif command -v open &> /dev/null; then
        open htmlcov/index.html
    else
        echo "⚠️  Could not open browser automatically"
        echo "📂 Open manually: file://$PROJECT_ROOT/htmlcov/index.html"
    fi
fi
