#!/bin/bash
# =============================================================================
# HyperSDK Integration Demo Script
# =============================================================================
# Demonstrates the HyperSDK + hyper2kvm workflow integration
#
# This script shows:
# 1. Setting up workflow directories
# 2. Creating manifests
# 3. Using hyperctl commands
# 4. Monitoring workflow progress
#
# Usage: ./demo_hypersdk_integration.sh
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
DEMO_DIR="/tmp/hyper2kvm-demo"
WORKFLOW_DIR="$DEMO_DIR/manifest-workflow"
OUTPUT_DIR="$DEMO_DIR/output"
HYPERCTL="/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   HyperSDK + hyper2kvm Workflow Integration Demo         ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# Demo 1: Directory Setup
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 1: Setting up Workflow Directories${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}Creating workflow directory structure...${NC}"
mkdir -p "$WORKFLOW_DIR"/{to_be_processed,processing,processed,failed}
mkdir -p "$OUTPUT_DIR"

echo -e "${GREEN}✓ Created directories:${NC}"
tree -L 2 "$WORKFLOW_DIR" 2>/dev/null || ls -la "$WORKFLOW_DIR"
echo ""

# =============================================================================
# Demo 2: Create Sample Manifests
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 2: Creating Sample Manifests${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}Creating a simple VM conversion manifest...${NC}"
cat > "$DEMO_DIR/ubuntu-server-manifest.json" <<'EOF'
{
  "version": "1.0",
  "pipeline": {
    "load": {
      "source_type": "vmdk",
      "source_path": "/path/to/ubuntu-server.vmdk",
      "comment": "Update this path to point to your actual VM disk"
    },
    "inspect": {
      "enabled": true,
      "detect_os": true,
      "detect_drivers": true
    },
    "fix": {
      "fstab": {
        "enabled": true,
        "mode": "stabilize-all",
        "comment": "Fix /etc/fstab for KVM boot"
      },
      "grub": {
        "enabled": true,
        "update_cmdline": true
      },
      "initramfs": {
        "enabled": true,
        "regenerate": true,
        "add_modules": ["virtio", "virtio_pci", "virtio_blk", "virtio_net"]
      },
      "network": {
        "enabled": true,
        "fix_level": "full"
      }
    },
    "convert": {
      "output_format": "qcow2",
      "compress": true,
      "output_path": "ubuntu-server-kvm.qcow2"
    },
    "validate": {
      "enabled": true,
      "check_bootable": true,
      "boot_test": false
    }
  }
}
EOF

echo -e "${GREEN}✓ Created: ubuntu-server-manifest.json${NC}"
echo ""

echo -e "${YELLOW}Creating a batch manifest for multiple VMs...${NC}"
cat > "$DEMO_DIR/batch-migration-manifest.json" <<'EOF'
{
  "version": "1.0",
  "batch": true,
  "description": "Batch migration of web tier VMs",
  "vms": [
    {
      "name": "web-frontend",
      "pipeline": {
        "load": {
          "source_type": "vmdk",
          "source_path": "/vms/web-frontend.vmdk"
        },
        "inspect": {"enabled": true},
        "fix": {
          "fstab": {"enabled": true, "mode": "stabilize-all"},
          "grub": {"enabled": true},
          "initramfs": {"enabled": true, "regenerate": true},
          "network": {"enabled": true, "fix_level": "full"}
        },
        "convert": {
          "output_format": "qcow2",
          "compress": true,
          "output_path": "web-frontend.qcow2"
        }
      }
    },
    {
      "name": "web-backend",
      "pipeline": {
        "load": {
          "source_type": "vhd",
          "source_path": "/vms/web-backend.vhd"
        },
        "inspect": {"enabled": true},
        "fix": {
          "fstab": {"enabled": true, "mode": "stabilize-all"},
          "grub": {"enabled": true}
        },
        "convert": {
          "output_format": "raw",
          "compress": false,
          "output_path": "web-backend.img"
        }
      }
    },
    {
      "name": "web-cache",
      "pipeline": {
        "load": {
          "source_type": "ova",
          "source_path": "/vms/web-cache.ova"
        },
        "inspect": {"enabled": true},
        "fix": {
          "fstab": {"enabled": true, "mode": "conservative"}
        },
        "convert": {
          "output_format": "qcow2",
          "compress": true
        }
      }
    }
  ]
}
EOF

echo -e "${GREEN}✓ Created: batch-migration-manifest.json${NC}"
echo ""

# =============================================================================
# Demo 3: Daemon Configuration
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 3: Workflow Daemon Configuration${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}Creating daemon configuration...${NC}"
cat > "$DEMO_DIR/manifest-daemon.yaml" <<EOF
# hyper2kvm Manifest Workflow Daemon
command: daemon
daemon: true
manifest_workflow_mode: true

# Workflow directories
manifest_workflow_dir: $WORKFLOW_DIR
output_dir: $OUTPUT_DIR

# Worker pool
max_concurrent_jobs: 3

# Logging
log_file: $DEMO_DIR/daemon.log
verbose: 2
EOF

echo -e "${GREEN}✓ Created: manifest-daemon.yaml${NC}"
echo ""
cat "$DEMO_DIR/manifest-daemon.yaml"
echo ""

# =============================================================================
# Demo 4: HyperCTL Commands
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 4: HyperCTL Commands${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ ! -f "$HYPERCTL" ]; then
    echo -e "${YELLOW}Building hyperctl...${NC}"
    cd /home/ssahani/go/github/hypersdk/cmd/hyperctl
    go build -o hyperctl .
    echo -e "${GREEN}✓ Built hyperctl${NC}"
    echo ""
fi

echo -e "${YELLOW}Available workflow commands:${NC}"
echo ""
echo "  $ hyperctl workflow -op status       # Check daemon status"
echo "  $ hyperctl workflow -op list         # List all jobs"
echo "  $ hyperctl workflow -op queue        # Show queue statistics"
echo "  $ hyperctl workflow -op watch        # Watch in real-time"
echo ""
echo "  $ hyperctl manifest create           # Interactive manifest builder"
echo "  $ hyperctl manifest validate -file <manifest.json>"
echo "  $ hyperctl manifest submit -file <manifest.json>"
echo "  $ hyperctl manifest generate <vm-path> <output-dir>"
echo ""

# =============================================================================
# Demo 5: Workflow Simulation
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 5: Workflow Submission Simulation${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}Simulating manifest submission...${NC}"
echo ""

# Copy manifest to to_be_processed
cp "$DEMO_DIR/ubuntu-server-manifest.json" "$WORKFLOW_DIR/to_be_processed/ubuntu-$(date +%s).json"
echo -e "${GREEN}✓ Placed ubuntu-server manifest in queue${NC}"

cp "$DEMO_DIR/batch-migration-manifest.json" "$WORKFLOW_DIR/to_be_processed/batch-$(date +%s).json"
echo -e "${GREEN}✓ Placed batch manifest in queue${NC}"
echo ""

# Show queue status
echo -e "${YELLOW}Current queue status:${NC}"
echo ""
echo "  to_be_processed: $(ls -1 $WORKFLOW_DIR/to_be_processed 2>/dev/null | wc -l) manifests"
echo "  processing:      $(ls -1 $WORKFLOW_DIR/processing 2>/dev/null | wc -l) manifests"
echo "  processed:       $(ls -1 $WORKFLOW_DIR/processed 2>/dev/null | wc -l) manifests"
echo "  failed:          $(ls -1 $WORKFLOW_DIR/failed 2>/dev/null | wc -l) manifests"
echo ""

# =============================================================================
# Demo 6: Starting the Workflow Daemon
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 6: Starting Workflow Daemon (Manual)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}To start the workflow daemon manually:${NC}"
echo ""
echo "  $ python3 -m hyper2kvm --config $DEMO_DIR/manifest-daemon.yaml"
echo ""
echo -e "${YELLOW}Or use systemd (production):${NC}"
echo ""
echo "  $ sudo systemctl start hyper2kvm-workflow@manifest.service"
echo "  $ sudo systemctl status hyper2kvm-workflow@manifest.service"
echo ""

# =============================================================================
# Demo 7: API Usage
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 7: REST API Usage${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}Example API calls (requires HyperSDK daemon running):${NC}"
echo ""

cat <<'EOAPI'
# Get workflow status
curl http://localhost:8080/api/workflow/status | jq

# List all jobs
curl http://localhost:8080/api/workflow/jobs | jq

# List active jobs
curl http://localhost:8080/api/workflow/jobs/active | jq

# Submit manifest
curl -X POST http://localhost:8080/api/workflow/manifest/submit \
  -H "Content-Type: application/json" \
  -d @ubuntu-server-manifest.json | jq

# Validate manifest
curl -X POST http://localhost:8080/api/workflow/manifest/validate \
  -H "Content-Type: application/json" \
  -d @ubuntu-server-manifest.json | jq
EOAPI

echo ""

# =============================================================================
# Demo 8: Web Dashboard
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo 8: Web Dashboard Access${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}To use the web dashboard:${NC}"
echo ""
echo "1. Start HyperSDK daemon:"
echo "   $ cd /home/ssahani/go/github/hypersdk"
echo "   $ go run ./cmd/daemon --config config.yaml"
echo ""
echo "2. Open in browser:"
echo "   http://localhost:8080/web/dashboard/"
echo ""
echo "3. Features:"
echo "   - Workflow Dashboard: Monitor queue and active jobs"
echo "   - Manifest Builder: Create manifests with GUI"
echo "   - Real-time Updates: Auto-refresh every 3 seconds"
echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Demo Summary${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${GREEN}✓ Created workflow directories${NC}"
echo -e "${GREEN}✓ Generated sample manifests${NC}"
echo -e "${GREEN}✓ Created daemon configuration${NC}"
echo -e "${GREEN}✓ Simulated manifest submission${NC}"
echo ""

echo -e "${YELLOW}Demo artifacts available at:${NC}"
echo "  $DEMO_DIR"
echo ""
echo "  Manifests:"
echo "    - ubuntu-server-manifest.json"
echo "    - batch-migration-manifest.json"
echo ""
echo "  Configuration:"
echo "    - manifest-daemon.yaml"
echo ""
echo "  Directories:"
echo "    - $WORKFLOW_DIR"
echo "    - $OUTPUT_DIR"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Next Steps:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "1. Update source_path in manifests to point to real VM disks"
echo ""
echo "2. Start the workflow daemon:"
echo "   python3 -m hyper2kvm --config $DEMO_DIR/manifest-daemon.yaml"
echo ""
echo "3. Monitor with hyperctl:"
echo "   $HYPERCTL workflow -op watch"
echo ""
echo "4. Or use the web dashboard at:"
echo "   http://localhost:8080/web/dashboard/"
echo ""

echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Demo Completed Successfully! ✅               ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
