#!/bin/bash
#
# VMCraft Batch Migration Script
#
# Migrate multiple VMs from a config file.
#
# Usage:
#   ./batch_migrate.sh <config.json>
#
# Example:
#   ./batch_migrate.sh batch_migration_example.json
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
if [ $# -lt 1 ]; then
    echo "Usage: $0 <config.json>"
    echo ""
    echo "Config file format:"
    echo '{'
    echo '  "migrations": ['
    echo '    {'
    echo '      "source": "/vmware/vm1.vmdk",'
    echo '      "target": "/kvm/vm1.qcow2",'
    echo '      "strategy": "enterprise"'
    echo '    }'
    echo '  ]'
    echo '}'
    echo ""
    echo "Example:"
    echo "  $0 batch_migration_example.json"
    exit 1
fi

CONFIG_FILE="$1"

# Check config exists
if [ ! -f "$CONFIG_FILE" ]; then
    print_error "Config file not found: $CONFIG_FILE"
    exit 1
fi

# Check jq is available
if ! command -v jq &> /dev/null; then
    print_error "jq is required but not installed"
    print_info "Install: sudo apt-get install jq"
    exit 1
fi

# Check Python 3 is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create output directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="batch_migration_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

# Log file
LOG_FILE="$OUTPUT_DIR/batch_migration.log"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

print_header "VMCraft Batch Migration"
log "Starting batch migration"
log "Config: $CONFIG_FILE"
log "Output directory: $OUTPUT_DIR"
log "Log file: $LOG_FILE"
echo ""

# Parse config and count migrations
MIGRATION_COUNT=$(jq '.migrations | length' "$CONFIG_FILE")

if [ "$MIGRATION_COUNT" = "0" ] || [ "$MIGRATION_COUNT" = "null" ]; then
    print_error "No migrations found in config file"
    exit 1
fi

print_info "Found $MIGRATION_COUNT migration(s) to process"
echo ""

# Ask for confirmation
echo "This will migrate $MIGRATION_COUNT VM(s). Continue? (yes/no)"
read -r CONTINUE
if [ "$CONTINUE" != "yes" ]; then
    print_info "Batch migration cancelled by user"
    exit 0
fi

echo ""

# Track success/failure
SUCCESSFUL=0
FAILED=0

# Process each migration
for i in $(seq 0 $((MIGRATION_COUNT - 1))); do
    # Extract migration details
    SOURCE=$(jq -r ".migrations[$i].source" "$CONFIG_FILE")
    TARGET=$(jq -r ".migrations[$i].target" "$CONFIG_FILE")
    STRATEGY=$(jq -r ".migrations[$i].strategy // \"enterprise\"" "$CONFIG_FILE")
    DESCRIPTION=$(jq -r ".migrations[$i].description // \"\"" "$CONFIG_FILE")

    MIGRATION_NUM=$((i + 1))

    print_header "Migration $MIGRATION_NUM/$MIGRATION_COUNT"
    log "Processing migration $MIGRATION_NUM/$MIGRATION_COUNT"
    log "Source: $SOURCE"
    log "Target: $TARGET"
    log "Strategy: $STRATEGY"

    if [ -n "$DESCRIPTION" ]; then
        print_info "Description: $DESCRIPTION"
        log "Description: $DESCRIPTION"
    fi

    echo ""

    # Check source exists
    if [ ! -f "$SOURCE" ]; then
        print_error "Source VM not found: $SOURCE"
        log "ERROR: Source VM not found: $SOURCE"
        FAILED=$((FAILED + 1))
        echo ""
        continue
    fi

    # Create migration-specific output directory
    MIGRATION_OUTPUT="$OUTPUT_DIR/migration_${MIGRATION_NUM}"
    mkdir -p "$MIGRATION_OUTPUT"

    # Run quick migration script
    MIGRATION_LOG="$MIGRATION_OUTPUT/migration.log"

    if "$SCRIPT_DIR/quick_migrate.sh" "$SOURCE" "$TARGET" "$STRATEGY" > "$MIGRATION_LOG" 2>&1; then
        print_success "Migration $MIGRATION_NUM completed successfully"
        log "Migration $MIGRATION_NUM completed successfully"
        SUCCESSFUL=$((SUCCESSFUL + 1))
    else
        print_error "Migration $MIGRATION_NUM failed"
        log "ERROR: Migration $MIGRATION_NUM failed"
        print_info "Check log: $MIGRATION_LOG"
        FAILED=$((FAILED + 1))
    fi

    echo ""

    # Brief pause between migrations
    if [ $i -lt $((MIGRATION_COUNT - 1)) ]; then
        sleep 2
    fi
done

# ============================================================================
# Summary
# ============================================================================
print_header "Batch Migration Summary"

log "Batch migration complete"
log "Successful: $SUCCESSFUL"
log "Failed: $FAILED"

echo ""
print_info "Total Migrations: $MIGRATION_COUNT"

if [ $SUCCESSFUL -gt 0 ]; then
    print_success "Successful: $SUCCESSFUL"
fi

if [ $FAILED -gt 0 ]; then
    print_error "Failed: $FAILED"
else
    print_success "All migrations completed successfully!"
fi

echo ""
print_info "Output directory: $OUTPUT_DIR"
print_info "Log file: $LOG_FILE"
echo ""

# Add all reports to analytics if available
if [ -f "$SCRIPT_DIR/migration_analytics.py" ]; then
    print_info "Adding reports to analytics database..."

    # Find all migration reports
    REPORT_COUNT=$(find "$OUTPUT_DIR" -name "migration_*.json" -type f | wc -l)

    if [ "$REPORT_COUNT" -gt 0 ]; then
        if python3 "$SCRIPT_DIR/migration_analytics.py" add-batch "$OUTPUT_DIR" >> "$LOG_FILE" 2>&1; then
            print_success "Added $REPORT_COUNT report(s) to analytics"
            print_info "Generate dashboard: python3 migration_analytics.py dashboard"
        fi
    fi
fi

echo ""

# Calculate success rate
if [ "$MIGRATION_COUNT" -gt 0 ]; then
    SUCCESS_RATE=$(echo "scale=2; $SUCCESSFUL / $MIGRATION_COUNT * 100" | bc)
    print_info "Success Rate: ${SUCCESS_RATE}%"
fi

echo ""

if [ $FAILED -eq 0 ]; then
    print_success "Batch migration complete - all migrations successful!"
    exit 0
else
    print_warning "Batch migration complete - some migrations failed"
    exit 1
fi
