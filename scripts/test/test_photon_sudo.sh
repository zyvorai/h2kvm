#!/bin/bash
set -euo pipefail
# Quick test with sudo for photon.vmdk

echo "🚀 Running Photon OS workflow with root permissions..."
echo ""

# Setup
WORKFLOW_DIR="/var/lib/hyper2kvm/photon-sudo-test"
OUTPUT_DIR="/var/lib/hyper2kvm/photon-sudo-output"
DAEMON_LOG="/tmp/photon-sudo-daemon.log"

# Create directories
sudo mkdir -p "$WORKFLOW_DIR"/{to_be_processed,processing,processed,failed}
sudo mkdir -p "$OUTPUT_DIR"
sudo chown -R $(whoami):$(whoami) "$WORKFLOW_DIR" "$OUTPUT_DIR"

# Create daemon config
cat > /tmp/photon-sudo-daemon.yaml <<EOF
command: daemon
daemon: true
manifest_workflow_mode: true
manifest_workflow_dir: $WORKFLOW_DIR
output_dir: $OUTPUT_DIR
max_concurrent_jobs: 1
log_file: $DAEMON_LOG
verbose: 2
EOF

# Create manifest
cat > /tmp/photon-sudo-manifest.json <<EOF
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
      "fstab": {"enabled": true, "mode": "stabilize-all"},
      "grub": {"enabled": true},
      "initramfs": {"enabled": true, "regenerate": true}
    },
    "convert": {
      "output_format": "qcow2",
      "compress": true,
      "output_path": "photon-converted-sudo.qcow2"
    }
  }
}
EOF

echo "✅ Setup complete"
echo ""
echo "Starting workflow daemon with sudo..."
echo "This will process photon.vmdk → qcow2"
echo ""

# Start daemon with sudo
sudo h2kvmctl --config /tmp/photon-sudo-daemon.yaml > "$DAEMON_LOG" 2>&1 &
DAEMON_PID=$!

sleep 5

# Submit manifest
echo "📥 Submitting manifest..."
cp /tmp/photon-sudo-manifest.json "$WORKFLOW_DIR/to_be_processed/photon-$(date +%s).json"

echo "🔄 Processing... (this may take 2-5 minutes)"
echo "Monitor with: sudo tail -f $DAEMON_LOG"
echo ""

# Monitor for completion (max 10 minutes)
START=$(date +%s)
while true; do
    ELAPSED=$(($(date +%s) - START))

    PROCESSING=$(ls -1 "$WORKFLOW_DIR/processing" 2>/dev/null | wc -l)
    PROCESSED=$(ls -1 "$WORKFLOW_DIR/processed" 2>/dev/null | wc -l)
    FAILED=$(ls -1 "$WORKFLOW_DIR/failed" 2>/dev/null | wc -l)

    echo -ne "\r[${ELAPSED}s] Processing: $PROCESSING | Completed: $PROCESSED | Failed: $FAILED    "

    if [ $PROCESSED -gt 0 ] || [ $FAILED -gt 0 ]; then
        echo ""
        break
    fi

    if [ $ELAPSED -gt 600 ]; then
        echo ""
        echo "⚠️  Timeout"
        break
    fi

    sleep 3
done

# Show results
echo ""
if [ $PROCESSED -gt 0 ]; then
    echo "✅ PROCESSING COMPLETED!"
    echo ""
    echo "Output files:"
    ls -lh "$OUTPUT_DIR" 2>/dev/null || echo "  (checking...)"
    echo ""

    echo "Processed manifests:"
    find "$WORKFLOW_DIR/processed" -name "*.json" -o -name "*.report.json" | head -5

elif [ $FAILED -gt 0 ]; then
    echo "❌ PROCESSING FAILED"
    echo ""
    echo "Error details:"
    find "$WORKFLOW_DIR/failed" -name "*.error.json" -exec cat {} \; | head -50
fi

echo ""
echo "📋 Last 20 lines of daemon log:"
sudo tail -20 "$DAEMON_LOG"

echo ""
echo "🛑 Stopping daemon..."
sudo kill $DAEMON_PID 2>/dev/null || true

echo ""
echo "✅ Test complete!"
echo "   Workflow: $WORKFLOW_DIR"
echo "   Output:   $OUTPUT_DIR"
