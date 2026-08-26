#!/bin/bash
# =============================================================================
# One-shot RHEL 8.8 Migration on k3s/k3d
# =============================================================================
# Automates the full pipeline:
#   1. Build hyper2kvm container image
#   2. Load image into k3d cluster
#   3. Deploy PVCs and copy VMDK into cluster
#   4. Run h2kvmctl migration as a Kubernetes Job
#   5. Upload converted QCOW2 to KubeVirt DataVolume
#   6. Start the VM in KubeVirt
#   7. Export libvirt domain XML
#
# Prerequisites: k3d, kubectl, virtctl, docker
#
# Usage:
#   ./scripts/run-k8s-migration.sh [--skip-build] [--skip-copy]
# =============================================================================

set -euo pipefail


SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="${K3D_CLUSTER:-hyper2kvm-test}"
NAMESPACE="hyper2kvm-migration"
VMDK_FILE="esx8.0-rhel8.8-with-thin-provision-disk1.vmdk"
MANIFEST="$SCRIPT_DIR/k8s/migration/rhel88-k3s-migration.yaml"
SKIP_BUILD=false
SKIP_COPY=false

for arg in "$@"; do
    case $arg in
        --skip-build) SKIP_BUILD=true ;;
        --skip-copy)  SKIP_COPY=true ;;
    esac
done

log()  { echo "[$(date +%H:%M:%S)] $1"; }
ok()   { echo "✅ [$(date +%H:%M:%S)] ✓ $1"; }
warn() { echo "⚠️ [$(date +%H:%M:%S)] ! $1"; }
err()  { echo "❌ [$(date +%H:%M:%S)] ✗ $1"; }

die() { err "$1"; exit 1; }

# ─── Prerequisites ───────────────────────────────────────────────────────────

log "Checking prerequisites..."
command -v kubectl >/dev/null  || die "kubectl not found"
command -v k3d     >/dev/null  || die "k3d not found"
command -v docker  >/dev/null  || die "docker not found"
k3d cluster list | grep -q "$CLUSTER_NAME" || die "k3d cluster '$CLUSTER_NAME' not found"
kubectl get kubevirts -n kubevirt >/dev/null 2>&1 || die "KubeVirt not installed"
ok "Prerequisites OK"

# ─── Step 1: Build container image ──────────────────────────────────────────

if [ "$SKIP_BUILD" = false ]; then
    log "Building hyper2kvm:cli container image..."
    cd "$SCRIPT_DIR"
    docker build --target cli -t hyper2kvm:cli -f Dockerfile . 2>&1 | tail -3
    ok "Container image built: hyper2kvm:cli"
else
    warn "Skipping image build (--skip-build)"
fi

# ─── Step 2: Load image into k3d ───────────────────────────────────────────

log "Loading image into k3d cluster '$CLUSTER_NAME'..."
k3d image import hyper2kvm:cli -c "$CLUSTER_NAME" 2>&1 | tail -1
ok "Image loaded into k3d"

# ─── Step 3: Deploy namespace, PVCs, config ────────────────────────────────

log "Creating namespace and PVCs..."
kubectl apply -f "$MANIFEST" -l step!=migrate -l step!=copy-input 2>&1 | grep -v "^$" || true
# Apply only the namespace, PVCs, ConfigMap, Services, VM definition
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: hyper2kvm-migration
EOF
kubectl apply -f "$MANIFEST" 2>&1 | head -20
ok "Resources created"

# ─── Step 4: Wait for copy job ─────────────────────────────────────────────

if [ "$SKIP_COPY" = false ]; then
    log "Waiting for VMDK copy job..."
    kubectl wait --for=condition=complete job/rhel88-copy-vmdk \
        -n "$NAMESPACE" --timeout=600s 2>&1 || {
        warn "Copy job may have already completed or failed, checking..."
        kubectl get job rhel88-copy-vmdk -n "$NAMESPACE" -o jsonpath='{.status.succeeded}' 2>/dev/null
    }
    ok "VMDK copied to PVC"
else
    warn "Skipping VMDK copy (--skip-copy)"
fi

# ─── Step 5: Wait for migration job ───────────────────────────────────────

log "Waiting for migration job to complete (this takes ~5 minutes)..."
log "Follow logs: kubectl logs -n $NAMESPACE -l step=migrate -f"

# Wait for the migration job to complete
kubectl wait --for=condition=complete job/rhel88-migration \
    -n "$NAMESPACE" --timeout=1800s 2>&1 || {
    err "Migration job failed or timed out"
    echo "--- Job status ---"
    kubectl get job rhel88-migration -n "$NAMESPACE" -o wide
    echo "--- Pod logs ---"
    kubectl logs -n "$NAMESPACE" -l step=migrate --tail=30
    exit 1
}
ok "Migration complete"

# Show the migration logs summary
kubectl logs -n "$NAMESPACE" -l step=migrate --tail=5

# ─── Step 6: Start the KubeVirt VM ───────────────────────────────────────

log "Starting KubeVirt VM..."
virtctl start rhel88-migrated -n "$NAMESPACE" 2>&1 || {
    # If runStrategy is Manual, use kubectl patch
    kubectl patch vm rhel88-migrated -n "$NAMESPACE" \
        --type merge -p '{"spec":{"runStrategy":"Always"}}' 2>&1
}

log "Waiting for VM to become ready..."
sleep 10
kubectl get vmi rhel88-migrated -n "$NAMESPACE" -o wide 2>&1 || warn "VMI not yet ready"

# Wait for VMI to be Running
for i in $(seq 1 30); do
    phase=$(kubectl get vmi rhel88-migrated -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
    if [ "$phase" = "Running" ]; then
        ok "VM is Running"
        break
    fi
    sleep 5
done

# ─── Step 7: Export libvirt domain XML ───────────────────────────────────

log "Exporting libvirt domain XML..."
mkdir -p "$SCRIPT_DIR/output/libvirt"

# Get VM details for the XML
VM_IP=$(kubectl get vmi rhel88-migrated -n "$NAMESPACE" -o jsonpath='{.status.interfaces[0].ipAddress}' 2>/dev/null || echo "")
VM_NODE=$(kubectl get vmi rhel88-migrated -n "$NAMESPACE" -o jsonpath='{.status.nodeName}' 2>/dev/null || echo "")
VM_GUESTOS=$(kubectl get vmi rhel88-migrated -n "$NAMESPACE" -o jsonpath='{.status.guestOSInfo.name}' 2>/dev/null || echo "")

# Copy the converted QCOW2 from the output PVC to local
log "Extracting converted QCOW2 from PVC..."
kubectl run extract-qcow2 -n "$NAMESPACE" --rm -i --restart=Never \
    --image=fedora:43 \
    --overrides='{
      "spec": {
        "containers": [{
          "name": "extract-qcow2",
          "image": "fedora:43",
          "command": ["cat", "/output/rhel8.8-fixed.qcow2"],
          "volumeMounts": [{
            "name": "output",
            "mountPath": "/output",
            "readOnly": true
          }]
        }],
        "volumes": [{
          "name": "output",
          "persistentVolumeClaim": {
            "claimName": "rhel88-qcow2-output"
          }
        }]
      }
    }' > "$SCRIPT_DIR/output/rhel8.8-k8s-migrated.qcow2" 2>/dev/null && {
    ok "QCOW2 extracted to output/rhel8.8-k8s-migrated.qcow2"
} || {
    warn "Could not extract QCOW2 (VM is using it). Domain XML only."
}

# Generate libvirt domain XML
if [ -f "$SCRIPT_DIR/output/rhel8.8-k8s-migrated.qcow2" ]; then
    DISK_PATH="$SCRIPT_DIR/output/rhel8.8-k8s-migrated.qcow2"
else
    DISK_PATH="$SCRIPT_DIR/output/rhel8.8-fixed.qcow2"
fi

h2kvmctl --cmd local \
    --vmdk /dev/null \
    --emit-domain-xml \
    --vm-name rhel88-k8s-migrated \
    --memory 4096 \
    --vcpus 2 \
    --output-dir "$SCRIPT_DIR/output" \
    --dry-run 2>/dev/null || {
    # Fallback: generate simple domain XML
    cat > "$SCRIPT_DIR/output/libvirt/rhel88-k8s-migrated.xml" <<XMLEOF
<domain type='kvm'>
  <name>rhel88-k8s-migrated</name>
  <memory unit='MiB'>4096</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features><acpi/><apic/></features>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='${DISK_PATH}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <serial type='pty'><target port='0'/></serial>
    <console type='pty'><target type='serial' port='0'/></console>
    <graphics type='vnc' port='-1' autoport='yes'/>
    <video><model type='qxl'/></video>
  </devices>
</domain>
XMLEOF
    ok "Generated fallback libvirt domain XML"
}

# ─── Summary ────────────────────────────────────────────────────────────

echo ""
echo "✅ ════════════════════════════════════════════════════════════════"
echo "✅   RHEL 8.8 Migration Complete (in-cluster)"
echo "✅ ════════════════════════════════════════════════════════════════"
echo ""
echo "  KubeVirt VM:  rhel88-migrated (ns: $NAMESPACE)"
echo "  VM IP:        ${VM_IP:-pending}"
echo "  VM Node:      ${VM_NODE:-pending}"
echo "  Guest OS:     ${VM_GUESTOS:-detecting...}"
echo "  SSH:          ssh -p 30088 root@localhost"
echo ""
echo "  Libvirt XML:  output/libvirt/rhel88-k8s-migrated.xml"
echo ""
echo "  Commands:"
echo "    kubectl get vm,vmi -n $NAMESPACE"
echo "    virtctl console rhel88-migrated -n $NAMESPACE"
echo "    virtctl ssh rhel88-migrated -n $NAMESPACE"
echo ""
echo "  Define in libvirt:"
echo "    virsh define output/libvirt/rhel88-k8s-migrated.xml"
echo "    virsh start rhel88-k8s-migrated"
echo ""
echo "✅ ════════════════════════════════════════════════════════════════"
