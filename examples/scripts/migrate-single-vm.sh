#!/bin/bash
# ============================================
# Single VM Migration Script
# ============================================
# Description: Migrate a single VM from VMDK to qcow2
# Usage: ./migrate-single-vm.sh <input.vmdk> <output.qcow2>
# ============================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check arguments
if [ $# -lt 2 ]; then
    echo -e "${RED}Usage: $0 <input.vmdk> <output.qcow2> [options]${NC}"
    echo ""
    echo "Options:"
    echo "  --windows           Migrate Windows VM (inject VirtIO drivers)"
    echo "  --virtio-iso PATH   Path to virtio-win.iso (required for Windows)"
    echo "  --test              Run boot test after conversion"
    echo "  --dry-run           Preview changes without executing"
    echo ""
    echo "Examples:"
    echo "  $0 linux.vmdk linux.qcow2"
    echo "  $0 windows.vmdk windows.qcow2 --windows --virtio-iso /data/virtio-win.iso"
    echo "  $0 vm.vmdk vm.qcow2 --test --dry-run"
    exit 1
fi

INPUT_VMDK="$1"
OUTPUT_QCOW2="$2"
shift 2

# Default options
WINDOWS=false
VIRTIO_ISO=""
TEST=false
DRY_RUN=false
AUTO_YES=false

# Parse optional arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --windows)
            WINDOWS=true
            shift
            ;;
        --virtio-iso)
            VIRTIO_ISO="$2"
            shift 2
            ;;
        --test)
            TEST=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
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

# Validate inputs
if [ ! -f "$INPUT_VMDK" ]; then
    echo -e "${RED}Error: Input VMDK not found: $INPUT_VMDK${NC}"
    exit 1
fi

if $WINDOWS && [ -z "$VIRTIO_ISO" ]; then
    echo -e "${RED}Error: --virtio-iso required for Windows migrations${NC}"
    exit 1
fi

if $WINDOWS && [ ! -f "$VIRTIO_ISO" ]; then
    echo -e "${RED}Error: VirtIO ISO not found: $VIRTIO_ISO${NC}"
    exit 1
fi

# Generate report filename
REPORT_DIR="./migration-reports"
mkdir -p "$REPORT_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="$REPORT_DIR/migration-${TIMESTAMP}.md"

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}h2kvm Migration Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "Input:       ${YELLOW}$INPUT_VMDK${NC}"
echo -e "Output:      ${YELLOW}$OUTPUT_QCOW2${NC}"
echo -e "Windows:     ${YELLOW}$WINDOWS${NC}"
echo -e "Test:        ${YELLOW}$TEST${NC}"
echo -e "Dry-run:     ${YELLOW}$DRY_RUN${NC}"
echo -e "Report:      ${YELLOW}$REPORT_FILE${NC}"
echo ""

# Build h2kvm command array
CMD_ARRAY=(
    sudo h2kvmctl
    --vmdk "$INPUT_VMDK"
    --to-output "$OUTPUT_QCOW2"
    --flatten
    --compress
    --fix-fstab
    --fix-grub
    --fix-network
    --report "$REPORT_FILE"
)

if $WINDOWS; then
    CMD_ARRAY+=(--windows --inject-virtio --virtio-win-iso "$VIRTIO_ISO")
fi

if $TEST; then
    CMD_ARRAY+=(--libvirt-test)
fi

if $DRY_RUN; then
    CMD_ARRAY+=(--dry-run)
fi

# Display command
echo -e "${YELLOW}Command to execute:${NC}"
printf '%q ' "${CMD_ARRAY[@]}"
echo ""
echo ""

# Confirm execution
if ! $DRY_RUN && [ "$AUTO_YES" != true ]; then
    read -p "Proceed with migration? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}Migration cancelled${NC}"
        exit 1
    fi
fi

# Execute migration
echo -e "${GREEN}Starting migration...${NC}"
if "${CMD_ARRAY[@]}"; then
    RESULT=0
else
    RESULT=$?
fi

if [ $RESULT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}======================================${NC}"
    echo -e "${GREEN}Migration completed successfully!${NC}"
    echo -e "${GREEN}======================================${NC}"
    echo ""
    echo -e "Output file: ${GREEN}$OUTPUT_QCOW2${NC}"
    echo -e "Report:      ${GREEN}$REPORT_FILE${NC}"

    if [ -f "$OUTPUT_QCOW2" ]; then
        SIZE=$(du -h "$OUTPUT_QCOW2" | cut -f1)
        echo -e "Size:        ${GREEN}$SIZE${NC}"
    fi

    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Review migration report: cat $REPORT_FILE"
    echo "2. Import to libvirt: sudo virsh define <domain.xml>"
    echo "3. Start VM: sudo virsh start <vm-name>"
    exit 0
else
    echo ""
    echo -e "${RED}======================================${NC}"
    echo -e "${RED}Migration failed with exit code $RESULT${NC}"
    echo -e "${RED}======================================${NC}"
    echo ""
    echo -e "${YELLOW}Check the report for details:${NC}"
    echo "cat $REPORT_FILE"
    exit $RESULT
fi
