#!/bin/bash
# VMware Production VM Test Suite for h2kvm
# Tests actual VMware VMs from /home/ssahani/vmware

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TOTAL=0
PASSED=0
FAILED=0
SKIPPED=0

# Results tracking
declare -A TEST_RESULTS

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

cleanup_env() {
    echo "Cleaning up test environment..."

    # Deactivate any LVM volumes
    sudo vgchange -an 2>/dev/null || true

    # Disconnect all NBD devices
    for nbd in /dev/nbd{0..15}; do
        if [ -b "$nbd" ]; then
            sudo qemu-nbd -d "$nbd" 2>/dev/null || true
        fi
    done

    # Clean up any stale mount points
    sudo umount /tmp/h2kvm-guestfs-* 2>/dev/null || true

    # Wait for devices to settle
    sleep 2
}

test_vm() {
    local name="$1"
    local config="$2"

    TOTAL=$((TOTAL + 1))

    echo ""
    print_header "Testing: $name"

    # Check if config file exists
    if [ ! -f "$config" ]; then
        echo -e "${YELLOW}⊘ SKIPPED: Config file not found: $config${NC}"
        SKIPPED=$((SKIPPED + 1))
        TEST_RESULTS["$name"]="SKIPPED"
        return
    fi

    # Clean up before test
    cleanup_env

    # Run the conversion
    local log_file="/tmp/h2kvm-vmware-test-$name.log"
    echo "Running conversion (this may take several minutes for large VMs)..."

    if sudo timeout 900 python3 -m h2kvm --config "$config" > "$log_file" 2>&1; then
        echo -e "${GREEN}✓ PASSED: $name${NC}"
        PASSED=$((PASSED + 1))
        TEST_RESULTS["$name"]="PASSED"

        # Show output file info
        local output_dir
        output_dir=$(grep -oP 'output_dir: \K.*' "$config" || echo "out/$(basename "$config" .yaml)")
        if [ -d "$output_dir" ]; then
            echo "Output files:"
            find "$output_dir" -name "*.qcow2" -exec ls -lh {} \; 2>/dev/null || true
        fi
    else
        echo -e "${RED}✗ FAILED: $name${NC}"
        FAILED=$((FAILED + 1))
        TEST_RESULTS["$name"]="FAILED"
        echo "Error log saved to: $log_file"
        echo "Last 30 lines of output:"
        tail -30 "$log_file"
    fi

    # Clean up after test
    cleanup_env
}

print_summary() {
    echo ""
    print_header "VMware Production VM Test Summary"

    if [ $FAILED -eq 0 ] && [ $PASSED -gt 0 ]; then
        echo -e "${GREEN}All tests passed! VMware VM migration is working correctly.${NC}"
    elif [ $FAILED -gt 0 ]; then
        echo -e "${RED}Some tests failed. Review the logs above.${NC}"
    fi

    echo ""
    echo "VM Test Results:"
    for vm in "${!TEST_RESULTS[@]}"; do
        result="${TEST_RESULTS[$vm]}"
        case "$result" in
            PASSED)
                echo -e "  ${GREEN}✓${NC} $vm: $result"
                ;;
            FAILED)
                echo -e "  ${RED}✗${NC} $vm: $result"
                ;;
            SKIPPED)
                echo -e "  ${YELLOW}⊘${NC} $vm: $result"
                ;;
        esac
    done

    echo ""
    echo "Statistics:"
    echo "  Total tests:  $TOTAL"
    echo "  Passed:       $PASSED"
    echo "  Failed:       $FAILED"
    echo "  Skipped:      $SKIPPED"

    # Exit with failure if any tests failed
    if [ $FAILED -gt 0 ]; then
        exit 1
    fi
}

# Main test execution
main() {
    print_header "h2kvm VMware Production VM Test Suite"
    echo "Testing actual VMware VMs from /home/ssahani/vmware"
    echo ""

    # Initial cleanup
    cleanup_env

    # Test Linux VMs
    test_vm "openSUSE Leap 15.4" "test-confs/opensuse-leap-test.yaml"
    test_vm "Ubuntu VMware" "test-confs/ubuntu-vmware-test.yaml"
    test_vm "Photon OS VMware" "test-confs/photon-vmware-test.yaml"

    # Print final summary
    print_summary
}

# Run main function
main
