#!/bin/bash
# Test script for workflow daemon
# Creates a test environment and demonstrates the workflow

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}hyper2kvm Workflow Daemon Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Setup test directories
TEST_BASE="/tmp/hyper2kvm-workflow-test"
echo -e "${GREEN}Setting up test environment...${NC}"
rm -rf "$TEST_BASE"
mkdir -p "$TEST_BASE"/{workflow,output}

echo -e "${GREEN}Creating directory structure...${NC}"
mkdir -p "$TEST_BASE/workflow"/{to_be_processed,processing,processed,failed}

# Create test config
cat > "$TEST_BASE/workflow-daemon.yaml" <<'EOF'
command: daemon
daemon: true
workflow_mode: true
workflow_dir: /tmp/hyper2kvm-workflow-test/workflow
output_dir: /tmp/hyper2kvm-workflow-test/output
max_concurrent_jobs: 2
out_format: qcow2
compress: true
flatten: true
fstab_mode: stabilize-all
verbose: 2
EOF

echo -e "${GREEN}Created config:${NC} $TEST_BASE/workflow-daemon.yaml"

# Create example job configs
cat > "$TEST_BASE/workflow/to_be_processed/simple-job.yaml" <<'EOF'
input: test-vm.vmdk
output_format: qcow2
compress: true
fstab_mode: stabilize-all
regen_initramfs: true
EOF

cat > "$TEST_BASE/workflow/to_be_processed/batch-job.yaml" <<'EOF'
jobs:
  - input: vm1.vmdk
    output_format: qcow2
    compress: true
  - input: vm2.vhd
    output_format: raw
EOF

echo -e "${GREEN}Created example job configs${NC}"

# Create a dummy VMDK file for testing
echo -e "${GREEN}Creating test VMDK file...${NC}"
cat > "$TEST_BASE/workflow/to_be_processed/test-vm.vmdk" <<'EOF'
# Disk DescriptorFile
version=1
CID=fffffffe
parentCID=ffffffff
createType="monolithicSparse"

# This is a minimal test VMDK - not a real VM disk
EOF

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Test Environment Ready!${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo -e "${GREEN}Directory Structure:${NC}"
tree -L 3 "$TEST_BASE" 2>/dev/null || find "$TEST_BASE" -type d | sort

echo ""
echo -e "${GREEN}To start the workflow daemon:${NC}"
echo -e "  sudo python -m hyper2kvm --config $TEST_BASE/workflow-daemon.yaml"
echo ""
echo -e "${GREEN}To monitor:${NC}"
echo -e "  watch ls -lR $TEST_BASE/workflow/"
echo ""
echo -e "${GREEN}Directories:${NC}"
echo -e "  📥 Drop zone:  $TEST_BASE/workflow/to_be_processed/"
echo -e "  🔄 Processing: $TEST_BASE/workflow/processing/"
echo -e "  ✅ Completed:  $TEST_BASE/workflow/processed/"
echo -e "  ❌ Failed:     $TEST_BASE/workflow/failed/"
echo -e "  📤 Output:     $TEST_BASE/output/"
echo ""
echo -e "${YELLOW}Cleanup when done:${NC}"
echo -e "  rm -rf $TEST_BASE"
echo ""
