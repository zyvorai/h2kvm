#!/bin/bash
# Test script for manifest workflow daemon

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Manifest Workflow Daemon Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Setup test directories
TEST_BASE="/tmp/hyper2kvm-manifest-test"
echo -e "${GREEN}Setting up test environment...${NC}"
rm -rf "$TEST_BASE"
mkdir -p "$TEST_BASE"/{manifest-workflow,output}

echo -e "${GREEN}Creating directory structure...${NC}"
mkdir -p "$TEST_BASE/manifest-workflow"/{to_be_processed,processing,processed,failed}

# Create test config
cat > "$TEST_BASE/manifest-daemon.yaml" <<'EOF'
command: daemon
daemon: true
manifest_workflow_mode: true
manifest_workflow_dir: /tmp/hyper2kvm-manifest-test/manifest-workflow
output_dir: /tmp/hyper2kvm-manifest-test/output
max_concurrent_jobs: 1
verbose: 2
EOF

echo -e "${GREEN}Created config:${NC} $TEST_BASE/manifest-daemon.yaml"

# Create a test manifest for Photon OS
cat > "$TEST_BASE/manifest-workflow/to_be_processed/photon-test.json" <<'EOF'
{
  "version": "1.0",
  "pipeline": {
    "load": {
      "source_type": "vmdk",
      "source_path": "/home/ssahani/tt/hyper2kvm/photon.vmdk"
    },
    "inspect": {
      "enabled": true,
      "detect_os": true
    },
    "fix": {
      "fstab": {
        "enabled": true,
        "mode": "stabilize-all"
      },
      "grub": {
        "enabled": true
      },
      "initramfs": {
        "enabled": true,
        "regenerate": true
      }
    },
    "convert": {
      "output_format": "qcow2",
      "compress": true,
      "output_path": "photon-manifest.qcow2"
    },
    "validate": {
      "enabled": true,
      "boot_test": false
    }
  }
}
EOF

echo -e "${GREEN}Created test manifest${NC}"

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Test Environment Ready!${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo -e "${GREEN}Directory Structure:${NC}"
tree -L 3 "$TEST_BASE" 2>/dev/null || find "$TEST_BASE" -type d | sort

echo ""
echo -e "${GREEN}Manifest File:${NC}"
cat "$TEST_BASE/manifest-workflow/to_be_processed/photon-test.json" | head -20

echo ""
echo -e "${GREEN}To start the manifest workflow daemon:${NC}"
echo -e "  sudo python -m hyper2kvm --config $TEST_BASE/manifest-daemon.yaml"
echo ""
echo -e "${GREEN}To monitor:${NC}"
echo -e "  watch -n 1 'ls -lR $TEST_BASE/manifest-workflow/'"
echo ""
echo -e "${GREEN}Directories:${NC}"
echo -e "  📥 Drop zone:  $TEST_BASE/manifest-workflow/to_be_processed/"
echo -e "  🔄 Processing: $TEST_BASE/manifest-workflow/processing/"
echo -e "  ✅ Completed:  $TEST_BASE/manifest-workflow/processed/"
echo -e "  ❌ Failed:     $TEST_BASE/manifest-workflow/failed/"
echo -e "  📤 Output:     $TEST_BASE/output/"
echo ""
echo -e "${YELLOW}Cleanup when done:${NC}"
echo -e "  rm -rf $TEST_BASE"
echo ""
