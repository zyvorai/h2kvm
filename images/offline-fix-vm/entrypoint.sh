#!/bin/bash
# images/offline-fix-vm/entrypoint.sh
#
# Entrypoint for offline-fix VM
# Runs inside KubeVirt VM and executes repair operations

set -e

SPEC_FILE="${SPEC_FILE:-/config/spec.json}"
RESULT_FILE="${RESULT_FILE:-/output/result.json}"
VMROOT="${VMROOT:-/vmroot}"

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║          Offline-Fix VM Worker Starting                          ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Validate inputs
if [ ! -f "$SPEC_FILE" ]; then
    echo "ERROR: Spec file not found: $SPEC_FILE"
    exit 1
fi

if [ ! -d "$VMROOT/etc" ]; then
    echo "ERROR: VM root not mounted or invalid: $VMROOT"
    ls -la "$VMROOT" || true
    exit 1
fi

echo "Configuration:"
echo "  Spec file:   $SPEC_FILE"
echo "  VM root:     $VMROOT"
echo "  Result file: $RESULT_FILE"
echo ""

# Show OS info from guest
echo "Guest OS Information:"
if [ -f "$VMROOT/etc/os-release" ]; then
    grep -E "^(NAME|VERSION)=" "$VMROOT/etc/os-release" || true
else
    echo "  (no /etc/os-release found)"
fi
echo ""

# Show requested operations
echo "Requested Operations:"
jq -r '.fixes[]' "$SPEC_FILE" 2>/dev/null || echo "  (could not parse spec)"
echo ""

# Run Python worker
echo "═══════════════════════════════════════════════════════════════════"
echo "Executing Fixers"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

set +e
python3 /opt/offline-fix/worker.py \
    --spec "$SPEC_FILE" \
    --root "$VMROOT" \
    --output "$RESULT_FILE"
EXIT_CODE=$?
set -e

echo ""
echo "═══════════════════════════════════════════════════════════════════"

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Offline-fix VM completed successfully"

    # Show summary
    if [ -f "$RESULT_FILE" ]; then
        echo ""
        echo "Results Summary:"
        jq -r '.operations[] | "  \(.operation): \(.success)"' "$RESULT_FILE" 2>/dev/null || true
    fi
else
    echo "❌ Offline-fix VM failed with exit code $EXIT_CODE"
fi

echo "═══════════════════════════════════════════════════════════════════"

exit $EXIT_CODE
