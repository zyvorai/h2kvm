#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# record-demo.sh — Record a 3-minute asciinema demo of hyper2kvm
#
# Usage:
#   ./scripts/record-demo.sh              # interactive (you drive)
#   ./scripts/record-demo.sh --scripted   # automated typing (hands-free)
#
# Prerequisites:
#   - asciinema installed
#   - photon.vmdk in repo root (or any small VMDK)
#   - GOVC_* env vars set (for vSphere demo)
#   - sudo access (for h2kvmctl)
#
# Output: demo.cast (upload to asciinema.org or embed in README)

set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: $0 [options] [output-file]

Record a 3-minute asciinema demo of hyper2kvm.

Options:
  --scripted     Automated typing (hands-free demo)
  --help, -h     Show this help message

Prerequisites:
  - asciinema installed (pip install asciinema)
  - photon.vmdk in repo root (or any small VMDK)
  - GOVC_* env vars set (for vSphere demo section)
  - sudo access (for h2kvmctl)

Examples:
  $0                          # Interactive recording
  $0 --scripted               # Automated demo
  $0 --scripted my-demo.cast  # Custom output file
EOF
    exit 0
}

SCRIPTED=false
CAST_FILE=""

for arg in "$@"; do
    case "$arg" in
        --help|-h)     usage ;;
        --scripted)    SCRIPTED=true ;;
        *)             CAST_FILE="$arg" ;;
    esac
done

[ -z "$CAST_FILE" ] && CAST_FILE="demo.cast"

command -v asciinema &>/dev/null || die "asciinema not found. Install: pip install asciinema"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Colors for section headers
G='\033[1;32m'  # green
C='\033[1;36m'  # cyan
Y='\033[1;33m'  # yellow
W='\033[1;37m'  # white
R='\033[0m'     # reset

# Simulated typing — types text with realistic delays
type_cmd() {
    local cmd="$1"
    local delay="${2:-0.04}"
    for (( i=0; i<${#cmd}; i++ )); do
        printf '%s' "${cmd:$i:1}"
        sleep "$delay"
    done
    echo
    sleep 0.3
}

# Section banner
banner() {
    echo
    echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}"
    echo -e "${G}  $1${R}"
    echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}"
    echo
    sleep 1.5
}

# Pause with message
pause() {
    echo -e "${Y}  ▸ $1${R}"
    sleep "${2:-2}"
}

# The actual demo content
run_demo() {
    clear
    echo -e "${W}"
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║                                                      ║"
    echo "  ║   hyper2kvm — VM Migration Demo                      ║"
    echo "  ║                                                      ║"
    echo "  ║   VMware / Cloud → KVM / KubeVirt                    ║"
    echo "  ║   Open Source (Apache 2.0)                            ║"
    echo "  ║                                                      ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo -e "${R}"
    sleep 3

    # --- SECTION 1: Version & Help ---
    banner "1/6  Quick Overview"

    pause "Check version and available commands"
    type_cmd "h2kvmctl --version"
    h2kvmctl --version 2>&1
    sleep 1

    type_cmd "h2kvmctl --help 2>&1 | head -25"
    h2kvmctl --help 2>&1 | head -25
    sleep 2

    # --- SECTION 2: VMDK Inspection ---
    banner "2/6  Inspect Source Disk"

    if [ -f photon.vmdk ]; then
        pause "Inspect a VMDK file — detect format, boot mode, risks"
        type_cmd "qemu-img info photon.vmdk | head -10"
        qemu-img info photon.vmdk 2>&1 | head -10
        sleep 2

        type_cmd "ls -lh photon.vmdk"
        ls -lh photon.vmdk
        sleep 1
    else
        pause "No photon.vmdk found — skipping inspection"
    fi

    # --- SECTION 3: YAML Config ---
    banner "3/6  YAML-Driven Migration"

    pause "Create a migration config — one file defines everything"
    cat <<'YAML'

  # migration.yaml — full pipeline config
  cmd: local
  vmdk: photon.vmdk
  output_dir: ./out
  out_format: qcow2
  flatten: true
  fstab_mode: stabilize-all
  regen_initramfs: true
  emit_domain_xml: true
  vm_name: photon-demo
  memory: 1024
  vcpus: 2

YAML
    sleep 3

    pause "Run the migration (dry-run to show pipeline)"
    type_cmd "sudo h2kvmctl --cmd local --vmdk photon.vmdk --output-dir /tmp/demo-out --dry-run 2>&1 | tail -20"
    if [ -f photon.vmdk ]; then
        sudo h2kvmctl --cmd local --vmdk photon.vmdk --output-dir /tmp/demo-out --out-format qcow2 --flatten --fstab-mode stabilize-all --dry-run 2>&1 | tail -20 || true
    else
        echo "  [demo] would run: h2kvmctl --config migration.yaml"
    fi
    sleep 2

    # --- SECTION 4: vSphere Discovery ---
    banner "4/6  vSphere VM Discovery"

    if [ -n "${GOVC_URL:-}" ]; then
        pause "Connect to vCenter and discover VMs"
        type_cmd "govc ls /\$(echo \$GOVC_DATACENTER)/vm/ | head -10"
        govc ls "/${GOVC_DATACENTER}/vm/" 2>&1 | head -10 || echo "  [demo] vCenter not reachable"
        sleep 2

        pause "Get VM details with CPU, RAM, power state"
        local first_vm
        first_vm=$(govc ls "/${GOVC_DATACENTER}/vm/" 2>/dev/null | head -1)
        if [ -n "$first_vm" ]; then
            vm_name=$(basename "$first_vm")
            type_cmd "govc vm.info -json $vm_name 2>&1 | python3 -c \"import json,sys; d=json.load(sys.stdin); vm=d['virtualMachines'][0]; print(f'  Name: {vm[\\\"config\\\"][\\\"name\\\"]}'); print(f'  CPU: {vm[\\\"config\\\"][\\\"hardware\\\"][\\\"numCPU\\\"]}'); print(f'  RAM: {vm[\\\"config\\\"][\\\"hardware\\\"][\\\"memoryMB\\\"]} MB'); print(f'  Power: {vm[\\\"runtime\\\"][\\\"powerState\\\"]}')\""
            govc vm.info -json "$vm_name" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
vm=d['virtualMachines'][0]
print(f'  Name:  {vm[\"config\"][\"name\"]}')
print(f'  CPU:   {vm[\"config\"][\"hardware\"][\"numCPU\"]}')
print(f'  RAM:   {vm[\"config\"][\"hardware\"][\"memoryMB\"]} MB')
print(f'  Power: {vm[\"runtime\"][\"powerState\"]}')
" 2>/dev/null || echo "  [demo] vm.info failed"
        fi
        sleep 2
    else
        pause "GOVC_URL not set — showing example output"
        echo "  Name:  production-web-01"
        echo "  CPU:   4"
        echo "  RAM:   8192 MB"
        echo "  Power: poweredOn"
        sleep 2
    fi

    # --- SECTION 5: KubeVirt Check ---
    banner "5/6  Kubernetes / KubeVirt"

    if command -v kubectl &>/dev/null; then
        pause "Check KubeVirt VMs running on Kubernetes"
        type_cmd "kubectl get vm -A 2>&1 | head -10"
        kubectl get vm -A 2>&1 | head -10 || echo "  No KubeVirt VMs found"
        sleep 2

        type_cmd "kubectl get vmi -A 2>&1 | head -10"
        kubectl get vmi -A 2>&1 | head -10 || echo "  No running VMIs"
        sleep 2
    else
        pause "kubectl not found — skipping K8s demo"
    fi

    # --- SECTION 6: TUI Preview ---
    banner "6/6  Interactive TUI (zkvm)"

    pause "The zkvm TUI provides guided migration with live progress"
    echo
    echo -e "${C}  Features:${R}"
    echo "    • Step-by-step form with input boxes"
    echo "    • vSphere VM discovery + batch selection"
    echo "    • Built-in file browser with fuzzy search"
    echo "    • Deploy targets: Libvirt + Kubernetes toggles"
    echo "    • Live execution plan updates"
    echo "    • Real-time progress streaming"
    echo
    echo -e "${C}  Launch:${R}"
    echo "    ./zkvm/zkvm"
    echo
    sleep 3

    # --- CLOSING ---
    echo
    echo -e "${W}"
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║                                                      ║"
    echo "  ║   hyper2kvm — Production-Grade VM Migration          ║"
    echo "  ║                                                      ║"
    echo "  ║   ✓ 10 cloud providers (via hypersdk)                ║"
    echo "  ║   ✓ VMware, Hyper-V, AWS, Azure, GCP                ║"
    echo "  ║   ✓ KVM/libvirt + KubeVirt targets                   ║"
    echo "  ║   ✓ Windows + Linux guest support                    ║"
    echo "  ║   ✓ 1,273 tests passing                              ║"
    echo "  ║   ✓ Apache 2.0 — free forever                        ║"
    echo "  ║                                                      ║"
    echo "  ║   github.com/ssahani/hyper2kvm                       ║"
    echo "  ║                                                      ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo -e "${R}"
    sleep 4
}

# --- MAIN ---
if [ "$SCRIPTED" = true ]; then
    echo "Recording scripted demo to $CAST_FILE..."
    asciinema rec "$CAST_FILE" \
        --title "hyper2kvm — VM Migration Demo" \
        --idle-time-limit 3 \
        --cols 100 \
        --rows 35 \
        --command "bash -c 'SCRIPTED=true source $0 && run_demo'" \
        --overwrite
    echo
    echo "Done! Upload with: asciinema upload $CAST_FILE"
    echo "Or embed in README with: [![demo](https://asciinema.org/a/XXXXX.svg)](https://asciinema.org/a/XXXXX)"
else
    echo "Recording interactive demo to $CAST_FILE..."
    echo "Run commands manually. Press Ctrl+D when done."
    echo
    echo "Suggested flow:"
    echo "  1. h2kvmctl --version"
    echo "  2. h2kvmctl --help | head -20"
    echo "  3. qemu-img info photon.vmdk"
    echo "  4. cat migration.yaml"
    echo "  5. sudo h2kvmctl --config migration.yaml --dry-run"
    echo "  6. govc ls /datacenter/vm/ | head -10"
    echo "  7. kubectl get vm -A"
    echo "  8. ./zkvm/zkvm  (show TUI, press Tab for vSphere, quit)"
    echo
    asciinema rec "$CAST_FILE" \
        --title "hyper2kvm — VM Migration Demo" \
        --idle-time-limit 3 \
        --cols 120 \
        --rows 40 \
        --overwrite
fi
