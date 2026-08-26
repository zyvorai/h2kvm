#!/bin/bash
#
# VMCraft Quick Migration Script
#
# Complete VM migration workflow with assessment and validation.
#
# Usage:
#   ./quick_migrate.sh <source.vmdk> <target.qcow2> [strategy]
#
# Example:
#   ./quick_migrate.sh /vmware/rhel9.vmdk /kvm/rhel9.qcow2 enterprise
#
# Author: VMCraft Team
# Version: 1.0.0

set -eo pipefail  # Exit on error, catch pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <source.vmdk> <target.qcow2> [strategy]"
    echo ""
    echo "Strategies:"
    echo "  basic             - Simple migration (default)"
    echo "  enterprise        - Full migration with all phases"
    echo "  database          - Optimized for database servers"
    echo "  web_server        - Optimized for web servers"
    echo "  security_hardened - Security-focused migration"
    echo "  minimal_downtime  - Fast migration"
    echo ""
    echo "Example:"
    echo "  $0 /vmware/rhel9.vmdk /kvm/rhel9.qcow2 enterprise"
    exit 1
fi

SOURCE_VM="$1"
TARGET_VM="$2"
STRATEGY="${3:-enterprise}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Output directory for reports
OUTPUT_DIR="$(dirname "$TARGET_VM")/migration_reports"
mkdir -p "$OUTPUT_DIR"

# Timestamp for filenames
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Report filenames
READINESS_REPORT="$OUTPUT_DIR/readiness_${TIMESTAMP}.json"
MIGRATION_REPORT="$OUTPUT_DIR/migration_${TIMESTAMP}.json"
VALIDATION_REPORT="$OUTPUT_DIR/validation_${TIMESTAMP}.json"

# Log file
LOG_FILE="$OUTPUT_DIR/migration_${TIMESTAMP}.log"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

print_header "VMCraft Quick Migration"
log "Starting migration workflow"
log "Source: $SOURCE_VM"
log "Target: $TARGET_VM"
log "Strategy: $STRATEGY"
log "Log file: $LOG_FILE"

# Check source exists
if [ ! -f "$SOURCE_VM" ]; then
    print_error "Source VM not found: $SOURCE_VM"
    exit 1
fi

# Check Python 3 is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

# ============================================================================
# Phase 1: Pre-Migration Readiness Assessment
# ============================================================================
print_header "Phase 1: Pre-Migration Readiness Assessment"

log "Running readiness assessment..."
if python3 "$SCRIPT_DIR/pre_migration_readiness.py" "$SOURCE_VM" --output "$READINESS_REPORT" >> "$LOG_FILE" 2>&1; then
    print_success "Readiness assessment complete"

    # Check risk score
    if command -v jq &> /dev/null; then
        RISK_SCORE=$(jq -r '.risk_assessment.overall_score' "$READINESS_REPORT" 2>/dev/null || echo "unknown")
        RISK_LEVEL=$(jq -r '.risk_assessment.risk_level' "$READINESS_REPORT" 2>/dev/null || echo "UNKNOWN")
        BLOCKER_COUNT=$(jq -r '.blockers | length' "$READINESS_REPORT" 2>/dev/null || echo "0")

        print_info "Risk Score: $RISK_SCORE/100 ($RISK_LEVEL)"
        print_info "Blockers: $BLOCKER_COUNT"

        # Check if migration should proceed
        if [ "$BLOCKER_COUNT" != "0" ] && [ "$BLOCKER_COUNT" != "unknown" ]; then
            print_error "Migration has $BLOCKER_COUNT blocker(s)!"
            print_warning "Review blockers in: $READINESS_REPORT"
            echo ""
            echo "Do you want to continue anyway? (yes/no)"
            read -r CONTINUE
            if [ "$CONTINUE" != "yes" ]; then
                print_info "Migration aborted by user"
                exit 0
            fi
        fi

        if [ "$RISK_LEVEL" = "CRITICAL" ]; then
            print_warning "Risk level is CRITICAL - migration not recommended"
            echo ""
            echo "Do you want to continue anyway? (yes/no)"
            read -r CONTINUE
            if [ "$CONTINUE" != "yes" ]; then
                print_info "Migration aborted by user"
                exit 0
            fi
        fi
    else
        print_warning "jq not installed - cannot parse risk score"
    fi
else
    print_warning "Readiness assessment failed (continuing anyway)"
fi

echo ""

# ============================================================================
# Phase 2: Migration Execution
# ============================================================================
print_header "Phase 2: Migration Execution"

log "Starting migration with strategy: $STRATEGY"
if python3 "$SCRIPT_DIR/migration_orchestrator.py" migrate \
    "$SOURCE_VM" \
    "$TARGET_VM" \
    --strategy "$STRATEGY" \
    --verbose >> "$LOG_FILE" 2>&1; then

    print_success "Migration completed successfully"

    # Find the generated migration report
    LATEST_MIGRATION_REPORT=$(ls -t "$OUTPUT_DIR"/../migration_report_*.json 2>/dev/null | head -1 || echo "")
    if [ -n "$LATEST_MIGRATION_REPORT" ]; then
        # Move to our output directory
        mv "$LATEST_MIGRATION_REPORT" "$MIGRATION_REPORT"
        print_info "Migration report: $MIGRATION_REPORT"

        # Show duration if jq is available
        if command -v jq &> /dev/null; then
            DURATION=$(jq -r '.duration_seconds' "$MIGRATION_REPORT" 2>/dev/null || echo "unknown")
            if [ "$DURATION" != "unknown" ]; then
                DURATION_MIN=$(echo "scale=2; $DURATION / 60" | bc 2>/dev/null || echo "$DURATION")
                print_info "Duration: ${DURATION_MIN} minutes"
            fi
        fi
    fi
else
    print_error "Migration failed!"
    print_info "Check log file: $LOG_FILE"
    exit 1
fi

echo ""

# ============================================================================
# Phase 3: Post-Migration Validation
# ============================================================================
print_header "Phase 3: Post-Migration Validation"

log "Running post-migration validation..."
if python3 "$SCRIPT_DIR/post_migration_validation.py" "$TARGET_VM" --output "$VALIDATION_REPORT" >> "$LOG_FILE" 2>&1; then
    print_success "Validation complete"

    # Check production readiness
    if command -v jq &> /dev/null; then
        PROD_SCORE=$(jq -r '.production_readiness.score' "$VALIDATION_REPORT" 2>/dev/null || echo "unknown")
        READINESS=$(jq -r '.production_readiness.readiness' "$VALIDATION_REPORT" 2>/dev/null || echo "UNKNOWN")
        ISSUE_COUNT=$(jq -r '.issues | length' "$VALIDATION_REPORT" 2>/dev/null || echo "0")

        print_info "Production Score: $PROD_SCORE/100 ($READINESS)"
        print_info "Issues: $ISSUE_COUNT"

        # Interpret readiness
        case "$READINESS" in
            "READY")
                print_success "VM is production-ready!"
                ;;
            "CONDITIONALLY_READY")
                print_warning "VM is conditionally ready - review issues"
                ;;
            "NEEDS_WORK")
                print_warning "VM needs work before production deployment"
                ;;
            "NOT_READY")
                print_error "VM is NOT production-ready!"
                ;;
        esac
    else
        print_warning "jq not installed - cannot parse validation results"
    fi
else
    print_warning "Validation failed (check manually)"
fi

echo ""

# ============================================================================
# Summary
# ============================================================================
print_header "Migration Summary"

echo ""
print_info "Source VM: $SOURCE_VM"
print_info "Target VM: $TARGET_VM"
print_info "Strategy: $STRATEGY"
echo ""
print_info "Reports:"
echo "  - Readiness:  $READINESS_REPORT"
[ -f "$MIGRATION_REPORT" ] && echo "  - Migration:  $MIGRATION_REPORT"
echo "  - Validation: $VALIDATION_REPORT"
echo "  - Log file:   $LOG_FILE"
echo ""

# Add to analytics if available
if [ -f "$SCRIPT_DIR/migration_analytics.py" ] && [ -f "$MIGRATION_REPORT" ]; then
    print_info "Adding to analytics database..."
    if python3 "$SCRIPT_DIR/migration_analytics.py" add "$MIGRATION_REPORT" >> "$LOG_FILE" 2>&1; then
        print_success "Added to analytics"
        print_info "Generate dashboard: python3 migration_analytics.py dashboard"
    fi
fi

echo ""
print_success "Migration workflow complete!"
log "Migration workflow complete"
