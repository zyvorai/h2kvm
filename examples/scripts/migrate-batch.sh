#!/bin/bash
# ============================================
# Batch VM Migration Script
# ============================================
# Description: Migrate multiple VMs from a list file
# Usage: ./migrate-batch.sh <vm-list.txt>
# ============================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Usage: $0 <vm-list.txt> [--parallel N]${NC}"
    echo ""
    echo "VM list format (one per line):"
    echo "  input.vmdk|output.qcow2"
    echo "  input.vmdk|output.qcow2|windows"
    echo ""
    echo "Example vm-list.txt:"
    echo "  /data/vms/web-01/web-01.vmdk|/data/kvm/web-01.qcow2"
    echo "  /data/vms/web-02/web-02.vmdk|/data/kvm/web-02.qcow2"
    echo "  /data/vms/win10/win10.vmdk|/data/kvm/win10.qcow2|windows"
    echo ""
    echo "Options:"
    echo "  --parallel N   Process N VMs in parallel (default: 1)"
    exit 1
fi

VM_LIST="$1"
PARALLEL=1
AUTO_YES=false

shift
while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel)
            PARALLEL="$2"
            shift 2
            ;;
        --yes|-y)
            AUTO_YES=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate VM list
if [ ! -f "$VM_LIST" ]; then
    echo -e "${RED}Error: VM list file not found: $VM_LIST${NC}"
    exit 1
fi

# Create output directories
REPORT_DIR="./batch-migration-reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BATCH_DIR="$REPORT_DIR/batch-$TIMESTAMP"
mkdir -p "$BATCH_DIR"

# Count VMs
TOTAL_VMS=$(grep -v '^#' "$VM_LIST" | grep -v '^[[:space:]]*$' | wc -l)

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Batch Migration Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "VM List:     ${YELLOW}$VM_LIST${NC}"
echo -e "Total VMs:   ${YELLOW}$TOTAL_VMS${NC}"
echo -e "Parallel:    ${YELLOW}$PARALLEL${NC}"
echo -e "Reports Dir: ${YELLOW}$BATCH_DIR${NC}"
echo ""

# Confirm
if [ "$AUTO_YES" != true ]; then
    read -p "Proceed with batch migration? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}Migration cancelled${NC}"
        exit 1
    fi
fi

# Statistics
SUCCESS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

# Function to migrate single VM
migrate_vm() {
    local LINE="$1"
    local INDEX="$2"

    # Parse line: input|output|type
    IFS='|' read -r INPUT OUTPUT TYPE <<< "$LINE"

    INPUT=$(echo "$INPUT" | xargs)  # Trim whitespace
    OUTPUT=$(echo "$OUTPUT" | xargs)
    TYPE=$(echo "$TYPE" | xargs)

    if [ -z "$INPUT" ] || [ -z "$OUTPUT" ]; then
        echo -e "${RED}[VM $INDEX] Invalid line format${NC}"
        return 1
    fi

    if [ ! -f "$INPUT" ]; then
        echo -e "${RED}[VM $INDEX] Input not found: $INPUT${NC}"
        return 1
    fi

    VM_NAME=$(basename "$OUTPUT" .qcow2)
    REPORT_FILE="$BATCH_DIR/${VM_NAME}.md"

    echo -e "${BLUE}[VM $INDEX/$TOTAL_VMS]${NC} Migrating: ${YELLOW}$VM_NAME${NC}"
    echo -e "  Input:  $INPUT"
    echo -e "  Output: $OUTPUT"

    # Build command array
    CMD=(sudo h2kvmctl)
    CMD+=(--vmdk "$INPUT")
    CMD+=(--to-output "$OUTPUT")
    CMD+=(--flatten)
    CMD+=(--compress)
    CMD+=(--fix-fstab)
    CMD+=(--fix-grub)
    CMD+=(--fix-network)
    CMD+=(--report "$REPORT_FILE")
    CMD+=(--log-level INFO)

    if [ "$TYPE" = "windows" ]; then
        if [ -z "${VIRTIO_ISO:-}" ]; then
            echo -e "${YELLOW}[VM $INDEX] Warning: Windows VM but no VIRTIO_ISO set, skipping${NC}"
            return 2
        fi
        CMD+=(--windows --inject-virtio --virtio-win-iso "$VIRTIO_ISO")
    fi

    # Execute
    if "${CMD[@]}" 2>&1 | tee "$BATCH_DIR/${VM_NAME}.log"; then
        echo -e "${GREEN}[VM $INDEX] SUCCESS: $VM_NAME${NC}"
        return 0
    else
        echo -e "${RED}[VM $INDEX] FAILED: $VM_NAME${NC}"
        return 1
    fi
}

export -f migrate_vm
export BATCH_DIR
export TOTAL_VMS
export VIRTIO_ISO="${VIRTIO_ISO:-}"

# Process VMs
INDEX=0
while IFS= read -r LINE; do
    # Skip comments and empty lines
    [[ "$LINE" =~ ^#.*$ ]] && continue
    [[ -z "$LINE" ]] && continue

    INDEX=$((INDEX + 1))

    migrate_vm "$LINE" "$INDEX"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    elif [ $EXIT_CODE -eq 2 ]; then
        SKIP_COUNT=$((SKIP_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi

    echo ""
done < "$VM_LIST"

# Summary
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Batch Migration Complete${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "Total VMs:    ${BLUE}$TOTAL_VMS${NC}"
echo -e "Successful:   ${GREEN}$SUCCESS_COUNT${NC}"
echo -e "Failed:       ${RED}$FAIL_COUNT${NC}"
echo -e "Skipped:      ${YELLOW}$SKIP_COUNT${NC}"
echo ""
echo -e "Reports saved to: ${YELLOW}$BATCH_DIR${NC}"

# Generate summary report
SUMMARY_FILE="$BATCH_DIR/SUMMARY.md"
cat > "$SUMMARY_FILE" <<EOF
# Batch Migration Summary

**Date:** $(date)
**VM List:** $VM_LIST

## Statistics

- Total VMs: $TOTAL_VMS
- Successful: $SUCCESS_COUNT
- Failed: $FAIL_COUNT
- Skipped: $SKIP_COUNT

## Successful Migrations

EOF

for REPORT in "$BATCH_DIR"/*.md; do
    [ "$REPORT" = "$SUMMARY_FILE" ] && continue
    if grep -q "Status: SUCCESS" "$REPORT" 2>/dev/null; then
        VM_NAME=$(basename "$REPORT" .md)
        echo "- $VM_NAME" >> "$SUMMARY_FILE"
    fi
done

cat >> "$SUMMARY_FILE" <<EOF

## Failed Migrations

EOF

for REPORT in "$BATCH_DIR"/*.md; do
    [ "$REPORT" = "$SUMMARY_FILE" ] && continue
    if grep -q "Status: FAILED" "$REPORT" 2>/dev/null; then
        VM_NAME=$(basename "$REPORT" .md)
        echo "- $VM_NAME" >> "$SUMMARY_FILE"
    fi
done

echo ""
echo -e "Summary report: ${GREEN}$SUMMARY_FILE${NC}"

# Exit with appropriate code
if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
else
    exit 0
fi
