#!/bin/bash
#
# Code quality checker - Run all code quality tools
#
# Usage:
#   ./scripts/quality.sh           # Run all checks
#   ./scripts/quality.sh --fix     # Auto-fix issues where possible
#   ./scripts/quality.sh --strict  # Fail on any warnings

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Options
FIX_ISSUES=false
STRICT_MODE=false
FAILED_CHECKS=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_ISSUES=true
            shift
            ;;
        --strict)
            STRICT_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "🔍 === h2kvm Code Quality Checker ==="
echo

# Function to run a check
run_check() {
    local name=$1
    local cmd=$2

    echo "⚙️  Running $name..."
    if bash -c "$cmd"; then
        echo "✅ $name passed"
    else
        echo "❌ $name failed"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
    echo
}

# 1. Ruff format check/fix
if [ "$FIX_ISSUES" = true ]; then
    run_check "Ruff Format (auto-fix)" "ruff format ."
else
    run_check "Ruff Format Check" "ruff format --check ."
fi

# 2. Ruff lint check/fix
if [ "$FIX_ISSUES" = true ]; then
    run_check "Ruff Lint (auto-fix)" "ruff check --fix ."
else
    run_check "Ruff Lint" "ruff check ."
fi

# 3. Mypy type checking
if [ "$STRICT_MODE" = true ]; then
    run_check "Mypy Type Check (strict)" "mypy h2kvm/ --strict"
else
    run_check "Mypy Type Check" "mypy h2kvm/"
fi

# 4. Security check with bandit
run_check "Bandit Security Scan" "bandit -r h2kvm/ -ll -q"

# 5. Check for common issues
echo "🔎 Checking for common issues..."

# Check for TODO without issue numbers
if grep -rn "TODO:" h2kvm/ --include="*.py" | grep -v "TODO("; then
    echo "⚠️  Found TODO comments without issue reference"
    if [ "$STRICT_MODE" = true ]; then
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
else
    echo "✅ No orphaned TODO comments"
fi
echo

# Check for print statements (should use logging)
if grep -rn "print(" h2kvm/ --include="*.py" | grep -v "# noqa"; then
    echo "⚠️  Found print() statements (use logging instead)"
    if [ "$STRICT_MODE" = true ]; then
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
else
    echo "✅ No print() statements found"
fi
echo

# Check for debugger statements
if grep -rn "breakpoint()\|pdb.set_trace()\|ipdb.set_trace()" h2kvm/ \
   --include="*.py"; then
    echo "❌ Found debugger statements"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
else
    echo "✅ No debugger statements"
fi
echo

# Summary
echo "📋 === Summary ==="
if [ $FAILED_CHECKS -eq 0 ]; then
    echo "🎉 All quality checks passed!"
    exit 0
else
    echo "💥 $FAILED_CHECKS check(s) failed"
    exit 1
fi
