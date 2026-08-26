#!/bin/bash
# Extended Multi-Distribution Test Suite for hyper2kvm
# Tests additional distributions beyond the core 4

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
    sudo umount /tmp/hyper2kvm-guestfs-* 2>/dev/null || true

    # Wait for devices to settle
    sleep 2
}

test_distribution() {
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
    local log_file="/tmp/hyper2kvm-test-$name.log"
    if sudo timeout 600 python3 -m hyper2kvm --config "$config" > "$log_file" 2>&1; then
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
        echo "Last 20 lines of output:"
        tail -20 "$log_file"
    fi

    # Clean up after test
    cleanup_env
}

print_summary() {
    echo ""
    print_header "Extended Test Suite Summary"

    if [ $FAILED -eq 0 ] && [ $PASSED -gt 0 ]; then
        echo -e "${GREEN}All tests passed! Extended filesystem support validated.${NC}"
    elif [ $FAILED -gt 0 ]; then
        echo -e "${RED}Some tests failed. Review the logs above.${NC}"
    fi

    echo ""
    echo "Distribution Test Results:"
    for dist in "${!TEST_RESULTS[@]}"; do
        result="${TEST_RESULTS[$dist]}"
        case "$result" in
            PASSED)
                echo -e "  ${GREEN}✓${NC} $dist: $result"
                ;;
            FAILED)
                echo -e "  ${RED}✗${NC} $dist: $result"
                ;;
            SKIPPED)
                echo -e "  ${YELLOW}⊘${NC} $dist: $result"
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
    print_header "hyper2kvm Extended Distribution Test Suite"
    echo "Testing additional distributions beyond core validation"
    echo ""

    # Initial cleanup
    cleanup_env

    # Test new distributions
    test_distribution "Fedora Cloud Base 43" "test-confs/fedora43-cloud-test.yaml"
    test_distribution "VMware Photon OS 5.0" "test-confs/photon-test.yaml"
    test_distribution "Arch Linux 2024" "test-confs/arch2-test.yaml"

    # Print final summary
    print_summary
}

# Run main function
main
