#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# test-all-distros.sh
#
# Comprehensive test of universal filesystem support across all major Linux distributions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Results tracking
declare -A RESULTS
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

log_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

log_info() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

test_distribution() {
    local name="$1"
    local config="$2"

    log_header "Testing: $name"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    # Check if config exists
    if [[ ! -f "$config" ]]; then
        log_error "Config not found: $config"
        RESULTS["$name"]="SKIP"
        return 1
    fi

    # Check if source image exists
    local source
    source=$(grep "^vmdk:" "$config" | cut -d: -f2- | xargs)
    if [[ ! -f "$source" ]]; then
        log_warn "Source image not found: $source"
        RESULTS["$name"]="SKIP"
        return 1
    fi

    log_info "Source: $source"
    log_info "Config: $config"

    # Run conversion
    local log_file
    log_file="/tmp/hyper2kvm-test-${name}.log"

    echo "Running conversion (this may take a few minutes)..."

    if sudo timeout 300 python3 -m hyper2kvm --config "$config" > "$log_file" 2>&1; then
        log_info "Conversion completed successfully"

        # Extract stats from log
        local converted
        converted=$(grep -oP 'fstab.*converted.*\K\d+' "$log_file" | head -1 || echo "0")
        local already_stable
        already_stable=$(grep -oP 'already stable.*\K\d+' "$log_file" | head -1 || echo "0")

        log_info "fstab entries converted: $converted"
        log_info "fstab entries already stable: $already_stable"

        # Check output file was created
        local output
        output=$(grep "^to_output:" "$config" | cut -d: -f2- | xargs)
        if [[ -f "$output" ]]; then
            local size
            size=$(du -h "$output" | cut -f1)
            log_info "Output created: $output ($size)"
            RESULTS["$name"]="PASS"
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            log_error "Output file not created: $output"
            RESULTS["$name"]="FAIL"
            FAILED_TESTS=$((FAILED_TESTS + 1))
        fi
    else
        log_error "Conversion failed (see $log_file)"
        RESULTS["$name"]="FAIL"
        FAILED_TESTS=$((FAILED_TESTS + 1))

        # Show last 20 lines of error log
        echo -e "\n${RED}Last 20 lines of log:${NC}"
        tail -20 "$log_file"
    fi

    echo ""
}

# Main test sequence
log_header "Universal Filesystem Support - Multi-Distribution Test Suite"

echo "Testing hyper2kvm with multiple Linux distributions"
echo "This validates:"
echo "  - Different filesystems (ext4, XFS, Btrfs, etc.)"
echo "  - Different storage layouts (partitions, LVM, etc.)"
echo "  - fstab/crypttab stabilization"
echo "  - Cross-distribution reliability"
echo ""

# Test each distribution (using absolute paths from repo root)
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
test_distribution "Fedora 42 Server" "$REPO_ROOT/test-confs/fedora42-simple-test.yaml"
test_distribution "CentOS 10 Server" "$REPO_ROOT/test-confs/centos10-test.yaml"
test_distribution "Arch Linux" "$REPO_ROOT/test-confs/arch-test.yaml"
test_distribution "Ubuntu Server 25.04" "$REPO_ROOT/test-confs/ubuntu25-test.yaml"

# Summary
log_header "Test Summary"

echo -e "${BLUE}Distribution Test Results:${NC}"
for distro in "Fedora 42 Server" "CentOS 10 Server" "Arch Linux" "Ubuntu Server 25.04"; do
    result="${RESULTS[$distro]:-UNKNOWN}"
    case "$result" in
        PASS)
            echo -e "  ${GREEN}✓${NC} $distro: ${GREEN}PASSED${NC}"
            ;;
        FAIL)
            echo -e "  ${RED}✗${NC} $distro: ${RED}FAILED${NC}"
            ;;
        SKIP)
            echo -e "  ${YELLOW}⊘${NC} $distro: ${YELLOW}SKIPPED${NC}"
            ;;
        *)
            echo -e "  ${YELLOW}?${NC} $distro: ${YELLOW}UNKNOWN${NC}"
            ;;
    esac
done

echo ""
echo -e "${BLUE}Statistics:${NC}"
echo -e "  Total tests:  $TOTAL_TESTS"
echo -e "  ${GREEN}Passed:${NC}       $PASSED_TESTS"
echo -e "  ${RED}Failed:${NC}       $FAILED_TESTS"
echo -e "  ${YELLOW}Skipped:${NC}      $((TOTAL_TESTS - PASSED_TESTS - FAILED_TESTS))"

echo ""
if [[ $FAILED_TESTS -eq 0 ]]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}All tests passed! Universal filesystem support is working correctly.${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}Some tests failed. Check logs in /tmp/hyper2kvm-test-*.log${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi
