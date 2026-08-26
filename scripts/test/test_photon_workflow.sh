#!/bin/bash
# =============================================================================
# HyperSDK Integration - Real Photon VM Workflow Test
# =============================================================================
# Tests the complete workflow with a real Photon OS VMDK
#
# This test demonstrates:
# 1. Workflow directory setup
# 2. Manifest creation for Photon OS
# 3. Daemon startup
# 4. Manifest submission via multiple methods
# 5. Real-time progress monitoring
# 6. Results verification
#
# Usage: ./test_photon_workflow.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Configuration
TEST_NAME="Photon-Workflow-Test"
PHOTON_VMDK="/home/ssahani/tt/hyper2kvm/photon.vmdk"
WORKFLOW_DIR="/var/lib/hyper2kvm/photon-test-workflow"
OUTPUT_DIR="/var/lib/hyper2kvm/photon-test-output"
DAEMON_CONFIG="/tmp/photon-daemon.yaml"
DAEMON_LOG="/tmp/photon-daemon.log"
DAEMON_PID=""
HYPERCTL="/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl"

# Print functions
print_header() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║$(printf '%62s' | tr ' ' ' ')║${NC}"
    echo -e "${BLUE}║$(printf "  %-58s  " "$1")║${NC}"
    echo -e "${BLUE}║$(printf '%62s' | tr ' ' ' ')║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
}

print_section() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}▶ $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ  $1${NC}"; }
print_step() { echo -e "${MAGENTA}➤ $1${NC}"; }

# Cleanup function
cleanup() {
    echo ""
    print_section "Cleanup"

    if [ -n "$DAEMON_PID" ] && kill -0 $DAEMON_PID 2>/dev/null; then
        print_step "Stopping workflow daemon (PID: $DAEMON_PID)..."
        kill $DAEMON_PID 2>/dev/null || true
        wait $DAEMON_PID 2>/dev/null || true
        print_success "Daemon stopped"
    fi

    # Don't remove directories - keep results for inspection
    print_info "Test artifacts preserved at:"
    echo "  - Workflow dir: $WORKFLOW_DIR"
    echo "  - Output dir:   $OUTPUT_DIR"
    echo "  - Daemon log:   $DAEMON_LOG"
}

trap cleanup EXIT

# =============================================================================
# Main Test
# =============================================================================

print_header "HyperSDK Photon OS Workflow Test"

print_info "Test Configuration:"
echo "  Source VM:    $PHOTON_VMDK ($(du -h $PHOTON_VMDK | cut -f1))"
echo "  Workflow Dir: $WORKFLOW_DIR"
echo "  Output Dir:   $OUTPUT_DIR"
echo ""

# =============================================================================
# Step 1: Verify Prerequisites
# =============================================================================
print_section "Step 1: Verify Prerequisites"

print_step "Checking Photon VMDK exists..."
if [ -f "$PHOTON_VMDK" ]; then
    SIZE=$(du -h "$PHOTON_VMDK" | cut -f1)
    TYPE=$(file -b "$PHOTON_VMDK")
    print_success "Found: $SIZE - $TYPE"
else
    print_error "Photon VMDK not found at $PHOTON_VMDK"
    exit 1
fi

print_step "Checking hyperctl binary..."
if [ -f "$HYPERCTL" ]; then
    print_success "HyperCTL found"
else
    print_info "Building hyperctl..."
    cd /home/ssahani/go/github/hypersdk/cmd/hyperctl
    go build -o hyperctl . 2>&1 | tail -2
    if [ -f "$HYPERCTL" ]; then
        print_success "HyperCTL built successfully"
    else
        print_error "Failed to build hyperctl"
        exit 1
    fi
fi

print_step "Checking hyper2kvm..."
if command -v h2kvmctl &>/dev/null; then
    VERSION=$(h2kvmctl --version 2>&1)
    print_success "h2kvmctl: v$VERSION"
else
    print_error "h2kvmctl not found in PATH"
    exit 1
fi

# =============================================================================
# Step 2: Setup Workflow Directories
# =============================================================================
print_section "Step 2: Setup Workflow Directories"

print_step "Creating workflow directory structure..."
sudo mkdir -p "$WORKFLOW_DIR"/{to_be_processed,processing,processed,failed}
sudo mkdir -p "$OUTPUT_DIR"
sudo chown -R $(whoami):$(whoami) "$WORKFLOW_DIR" "$OUTPUT_DIR"

print_success "Directory structure created:"
tree -L 2 "$WORKFLOW_DIR" 2>/dev/null || ls -la "$WORKFLOW_DIR"

# =============================================================================
# Step 3: Create Daemon Configuration
# =============================================================================
print_section "Step 3: Create Daemon Configuration"

print_step "Generating daemon config..."
cat > "$DAEMON_CONFIG" <<EOF
# Photon OS Workflow Test Configuration
command: daemon
daemon: true
manifest_workflow_mode: true

# Workflow directories
manifest_workflow_dir: $WORKFLOW_DIR
output_dir: $OUTPUT_DIR

# Processing settings
max_concurrent_jobs: 1

# Logging
log_file: $DAEMON_LOG
verbose: 2
EOF

print_success "Configuration created at $DAEMON_CONFIG"
echo ""
cat "$DAEMON_CONFIG"

# =============================================================================
# Step 4: Create Photon Manifest
# =============================================================================
print_section "Step 4: Create Photon OS Manifest"

MANIFEST_FILE="/tmp/photon-test-manifest.json"

print_step "Creating manifest with full pipeline..."
cat > "$MANIFEST_FILE" <<EOF
{
  "version": "1.0",
  "metadata": {
    "name": "photon-os-migration",
    "description": "HyperSDK integration test with Photon OS",
    "created_at": "$(date -Iseconds)",
    "created_by": "test_photon_workflow.sh"
  },
  "pipeline": {
    "load": {
      "source_type": "vmdk",
      "source_path": "$PHOTON_VMDK",
      "description": "Photon OS 5.0 VMDK"
    },
    "inspect": {
      "enabled": true,
      "detect_os": true,
      "detect_drivers": true,
      "scan_partitions": true
    },
    "fix": {
      "fstab": {
        "enabled": true,
        "mode": "stabilize-all",
        "comment": "Convert UUIDs to device names for KVM"
      },
      "grub": {
        "enabled": true,
        "update_cmdline": true,
        "add_console": true
      },
      "initramfs": {
        "enabled": true,
        "regenerate": true,
        "add_modules": ["virtio", "virtio_pci", "virtio_blk", "virtio_net", "virtio_scsi"]
      },
      "network": {
        "enabled": true,
        "fix_level": "full",
        "ensure_dhcp": true
      }
    },
    "convert": {
      "output_format": "qcow2",
      "compress": true,
      "output_path": "photon-hypersdk-test.qcow2"
    },
    "validate": {
      "enabled": true,
      "check_bootable": true,
      "check_filesystem": true,
      "boot_test": false
    }
  }
}
EOF

print_success "Manifest created at $MANIFEST_FILE"
echo ""
echo -e "${YELLOW}Pipeline stages configured:${NC}"
echo "  📥 LOAD     - Source VMDK"
echo "  🔍 INSPECT  - OS/driver detection"
echo "  🔧 FIX      - fstab, grub, initramfs, network"
echo "  🔄 CONVERT  - To qcow2 with compression"
echo "  ✅ VALIDATE - Bootability check"
echo ""

# Validate manifest JSON
print_step "Validating manifest JSON syntax..."
if python3 -c "import json; json.load(open('$MANIFEST_FILE'))" 2>/dev/null; then
    print_success "Manifest JSON is valid"
else
    print_error "Invalid JSON in manifest"
    exit 1
fi

# =============================================================================
# Step 5: Start Workflow Daemon
# =============================================================================
print_section "Step 5: Start Workflow Daemon"

print_step "Starting manifest workflow daemon..."
h2kvmctl --config "$DAEMON_CONFIG" > "$DAEMON_LOG" 2>&1 &
DAEMON_PID=$!

sleep 3

if kill -0 $DAEMON_PID 2>/dev/null; then
    print_success "Daemon started (PID: $DAEMON_PID)"
    print_info "Log file: $DAEMON_LOG"
else
    print_error "Daemon failed to start"
    echo ""
    echo "Last 20 lines of log:"
    tail -20 "$DAEMON_LOG"
    exit 1
fi

# Show initial daemon log
echo ""
print_info "Daemon startup log:"
tail -15 "$DAEMON_LOG" | sed 's/^/  /'
echo ""

# =============================================================================
# Step 6: Submit Manifest
# =============================================================================
print_section "Step 6: Submit Manifest to Workflow"

print_step "Copying manifest to to_be_processed directory..."
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
QUEUE_MANIFEST="$WORKFLOW_DIR/to_be_processed/photon-$TIMESTAMP.json"
cp "$MANIFEST_FILE" "$QUEUE_MANIFEST"

print_success "Manifest submitted: $(basename $QUEUE_MANIFEST)"
echo ""
print_info "Workflow queue status:"
echo "  📥 to_be_processed: $(ls -1 $WORKFLOW_DIR/to_be_processed 2>/dev/null | wc -l) manifest(s)"
echo "  🔄 processing:      $(ls -1 $WORKFLOW_DIR/processing 2>/dev/null | wc -l) manifest(s)"
echo "  ✅ processed:       $(ls -1 $WORKFLOW_DIR/processed 2>/dev/null | wc -l) manifest(s)"
echo "  ❌ failed:          $(ls -1 $WORKFLOW_DIR/failed 2>/dev/null | wc -l) manifest(s)"
echo ""

# =============================================================================
# Step 7: Monitor Processing
# =============================================================================
print_section "Step 7: Monitor Processing"

print_info "Monitoring workflow progress..."
print_info "Press Ctrl+C to stop monitoring (processing will continue)"
echo ""

MONITOR_START=$(date +%s)
MAX_WAIT=600  # 10 minutes max

while true; do
    ELAPSED=$(($(date +%s) - MONITOR_START))

    # Check queue status
    TO_PROCESS=$(ls -1 $WORKFLOW_DIR/to_be_processed 2>/dev/null | wc -l)
    PROCESSING=$(ls -1 $WORKFLOW_DIR/processing 2>/dev/null | wc -l)
    PROCESSED=$(ls -1 $WORKFLOW_DIR/processed 2>/dev/null | wc -l)
    FAILED=$(ls -1 $WORKFLOW_DIR/failed 2>/dev/null | wc -l)

    # Clear line and print status
    echo -ne "\r\033[K"
    echo -ne "${CYAN}[${ELAPSED}s]${NC} "
    echo -ne "Queue: ${YELLOW}$TO_PROCESS${NC} | "
    echo -ne "Processing: ${MAGENTA}$PROCESSING${NC} | "
    echo -ne "Completed: ${GREEN}$PROCESSED${NC} | "
    echo -ne "Failed: ${RED}$FAILED${NC}"

    # Check if processing is complete
    if [ $PROCESSED -gt 0 ]; then
        echo ""
        print_success "Processing completed!"
        break
    fi

    if [ $FAILED -gt 0 ]; then
        echo ""
        print_error "Processing failed!"
        break
    fi

    # Timeout check
    if [ $ELAPSED -gt $MAX_WAIT ]; then
        echo ""
        print_error "Processing timeout (${MAX_WAIT}s)"
        break
    fi

    # Show live log snippet every 5 seconds
    if [ $((ELAPSED % 5)) -eq 0 ] && [ $PROCESSING -gt 0 ]; then
        echo ""
        print_info "Recent activity:"
        tail -3 "$DAEMON_LOG" | sed 's/^/  /' | grep -v "^$" || true
    fi

    sleep 2
done

echo ""

# =============================================================================
# Step 8: Show Results
# =============================================================================
print_section "Step 8: Results"

# Check for completed processing
if [ $PROCESSED -gt 0 ]; then
    print_success "Workflow completed successfully!"
    echo ""

    # Find the latest processed manifest
    PROCESSED_DIR=$(find "$WORKFLOW_DIR/processed" -type d -name "20*" | sort | tail -1)

    if [ -n "$PROCESSED_DIR" ]; then
        print_info "Processed files:"
        ls -lh "$PROCESSED_DIR" | tail -n +2 | sed 's/^/  /'
        echo ""

        # Show processing report if it exists
        REPORT_FILE=$(find "$PROCESSED_DIR" -name "*.report.json" | head -1)
        if [ -f "$REPORT_FILE" ]; then
            print_info "Processing Report:"
            echo ""
            python3 -c "
import json, sys
with open('$REPORT_FILE') as f:
    report = json.load(f)
    print('  Status:', report.get('status', 'N/A'))
    print('  Started:', report.get('start_time', 'N/A'))
    print('  Completed:', report.get('end_time', 'N/A'))
    print('  Duration:', report.get('duration_seconds', 'N/A'), 'seconds')
    if 'stages' in report:
        print('\n  Pipeline Stages:')
        for stage, result in report['stages'].items():
            status = '✅' if result.get('success') else '❌'
            print(f'    {status} {stage.upper()}')
" 2>/dev/null || cat "$REPORT_FILE" | head -20
            echo ""
        fi
    fi

    # Check output directory
    print_info "Output files:"
    if [ -d "$OUTPUT_DIR" ]; then
        ls -lh "$OUTPUT_DIR" | tail -n +2 | sed 's/^/  /'
        echo ""

        # Show converted file details
        CONVERTED=$(find "$OUTPUT_DIR" -name "*.qcow2" | head -1)
        if [ -f "$CONVERTED" ]; then
            print_success "Converted image created:"
            echo "  File: $CONVERTED"
            echo "  Size: $(du -h $CONVERTED | cut -f1)"
            echo "  Type: $(file -b $CONVERTED)"

            # Check with qemu-img if available
            if command -v qemu-img &>/dev/null; then
                echo ""
                print_info "QEMU image info:"
                qemu-img info "$CONVERTED" | sed 's/^/  /'
            fi
        fi
    fi

elif [ $FAILED -gt 0 ]; then
    print_error "Processing failed!"
    echo ""

    # Find the latest failed manifest
    FAILED_DIR=$(find "$WORKFLOW_DIR/failed" -type d -name "20*" | sort | tail -1)

    if [ -n "$FAILED_DIR" ]; then
        print_info "Failed files:"
        ls -lh "$FAILED_DIR" | tail -n +2 | sed 's/^/  /'
        echo ""

        # Show error details
        ERROR_FILE=$(find "$FAILED_DIR" -name "*.error.json" | head -1)
        if [ -f "$ERROR_FILE" ]; then
            print_info "Error details:"
            cat "$ERROR_FILE" | python3 -m json.tool 2>/dev/null | head -30 | sed 's/^/  /' || cat "$ERROR_FILE" | sed 's/^/  /'
            echo ""
        fi
    fi
fi

# =============================================================================
# Step 9: Daemon Log Summary
# =============================================================================
print_section "Step 9: Daemon Log Summary"

print_info "Last 30 lines of daemon log:"
echo ""
tail -30 "$DAEMON_LOG" | sed 's/^/  /'

# =============================================================================
# Step 10: Test HyperCTL Commands
# =============================================================================
print_section "Step 10: Test HyperCTL Commands"

print_step "Testing hyperctl workflow commands..."
echo ""

if [ -f "$HYPERCTL" ]; then
    print_info "hyperctl workflow -op status:"
    $HYPERCTL workflow -op status 2>&1 | head -20 | sed 's/^/  /'
    echo ""

    print_info "hyperctl workflow -op queue:"
    $HYPERCTL workflow -op queue 2>&1 | head -20 | sed 's/^/  /'
    echo ""
else
    print_error "HyperCTL not available"
fi

# =============================================================================
# Summary
# =============================================================================
print_header "Test Summary"

echo ""
echo -e "${GREEN}✅ Prerequisites verified${NC}"
echo -e "${GREEN}✅ Workflow directories created${NC}"
echo -e "${GREEN}✅ Daemon configuration created${NC}"
echo -e "${GREEN}✅ Photon manifest created${NC}"
echo -e "${GREEN}✅ Workflow daemon started${NC}"
echo -e "${GREEN}✅ Manifest submitted${NC}"
echo -e "${GREEN}✅ Processing monitored${NC}"

if [ $PROCESSED -gt 0 ]; then
    echo -e "${GREEN}✅ Processing completed successfully!${NC}"
elif [ $FAILED -gt 0 ]; then
    echo -e "${RED}❌ Processing failed${NC}"
else
    echo -e "${YELLOW}⚠  Processing incomplete or timed out${NC}"
fi

echo ""
print_info "Test artifacts:"
echo "  Workflow dir: $WORKFLOW_DIR"
echo "  Output dir:   $OUTPUT_DIR"
echo "  Daemon log:   $DAEMON_LOG"
echo "  Manifest:     $MANIFEST_FILE"
echo ""

print_header "Test Complete"
