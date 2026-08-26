#!/usr/bin/env bash
set -euo pipefail
# SPDX-License-Identifier: Apache-2.0
#
# h2kvm selftest — post-installation verification
#
# Verifies that all binaries, Python packages, configs, services,
# and the Artifact Manifest v1.0 pipeline are correctly installed
# before running any migration workloads.
#
# Usage:
#   ./scripts/selftest.sh              # Run all checks
#   ./scripts/selftest.sh --quick      # Skip daemon/service checks
#   make selftest                      # Via Makefile
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed


PASS=0
FAIL=0
WARN=0
QUICK=false

[[ "${1:-}" == "--quick" ]] && QUICK=true

pass() { PASS=$((PASS + 1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  ❌ $1"; }
warn() { WARN=$((WARN + 1)); echo "  ⚠️  $1"; }
section() { echo ""; echo "━━━ $1 ━━━"; }

# ── Binaries ──────────────────────────────────────────────────────────────────
section "Binaries"

for bin in h2kvmctl h2kvm; do
    if command -v "$bin" &>/dev/null; then
        pass "$bin found: $(command -v "$bin")"
    else
        fail "$bin not found in PATH"
    fi
done

for bin in zkvm h2k h2kvm-operator; do
    if command -v "$bin" &>/dev/null; then
        pass "$bin found: $(command -v "$bin")"
    else
        warn "$bin not found (optional)"
    fi
done

# ── Python package ────────────────────────────────────────────────────────────
section "Python Package"

if python3 -c "import h2kvm" &>/dev/null; then
    ver=$(python3 -c "import h2kvm; print(h2kvm.__version__)" 2>/dev/null || echo "?")
    pass "h2kvm package installed: $ver"
else
    fail "h2kvm package not importable"
fi

# Check key submodules
for mod in h2kvm.orchestration.orchestrator \
           h2kvm.orchestration.manifest.orchestrator \
           h2kvm.orchestration.manifest.loader \
           h2kvm.runtime.daemon.manifest_workflow_daemon \
           h2kvm.vmcraft.nbd \
           h2kvm.fixers.offline_fixer \
           h2kvm.providers.aws_ec2 \
           h2kvm.providers.azure; do
    if python3 -c "import $mod" &>/dev/null; then
        pass "import $mod"
    else
        fail "import $mod failed"
    fi
done

# ── Version check ────────────────────────────────────────────────────────────
section "Version"

ver=$(h2kvmctl --version 2>/dev/null || echo "FAILED")
if [[ "$ver" != "FAILED" ]]; then
    pass "h2kvmctl --version: $ver"
else
    fail "h2kvmctl --version failed"
fi

# ── External tools ────────────────────────────────────────────────────────────
section "External Tools"

for tool in qemu-img qemu-nbd virsh virt-install; do
    if command -v "$tool" &>/dev/null; then
        pass "$tool found"
    else
        warn "$tool not found (needed for VM conversion)"
    fi
done

for tool in podman; do
    if command -v "$tool" &>/dev/null; then
        pass "$tool found (used for LVM scanning)"
    else
        warn "$tool not found (optional, needed for LVM support)"
    fi
done

# ── VirtIO Windows drivers ────────────────────────────────────────────────────
section "VirtIO Windows Drivers"

if [ -f /var/lib/h2kvm/virtio-win.iso ]; then
    pass "virtio-win.iso: /var/lib/h2kvm/virtio-win.iso"
else
    warn "virtio-win.iso not found (needed for Windows VirtIO migration)"
fi

# ── hypersdk integration ─────────────────────────────────────────────────────
section "hypersdk Integration"

for bin in hypervisord hyperctl hyperexport; do
    if command -v "$bin" &>/dev/null; then
        pass "$bin found: $(command -v "$bin")"
    else
        warn "$bin not found (install hypersdk for full pipeline)"
    fi
done

# ── Manifest v1.0 validation ─────────────────────────────────────────────────
section "Artifact Manifest v1.0 Pipeline"

TEST_TMPDIR=$(mktemp -d)
trap 'rm -rf "$TEST_TMPDIR"' EXIT

# Create a minimal test VMDK
qemu-img create -f vmdk "$TEST_TMPDIR/test.vmdk" 1M &>/dev/null 2>&1
if [[ -f "$TEST_TMPDIR/test.vmdk" ]]; then
    pass "qemu-img can create test VMDK"
else
    fail "qemu-img create failed"
fi

# Create a test manifest v1.0
cat > "$TEST_TMPDIR/test-manifest.json" <<TESTEOF
{
  "manifest_version": "1.0",
  "source": {"provider": "selftest", "vm_name": "selftest-vm", "export_timestamp": "$(date -Iseconds)"},
  "vm": {"cpu": 1, "mem_gb": 1, "firmware": "bios", "os_hint": "linux"},
  "disks": [{"id": "disk-0", "source_format": "vmdk", "bytes": 1048576, "local_path": "$TEST_TMPDIR/test.vmdk", "disk_type": "boot"}],
  "output": {"directory": "$TEST_TMPDIR/out", "format": "qcow2"}
}
TESTEOF

# Validate manifest loads without error
if python3 -c "
from h2kvm.orchestration.manifest.loader import ManifestLoader
loader = ManifestLoader()
m = loader.load('$TEST_TMPDIR/test-manifest.json')
assert m['manifest_version'] == '1.0'
assert len(m['disks']) == 1
assert m['disks'][0]['source_format'] == 'vmdk'
print('OK')
" 2>/dev/null | grep -q OK; then
    pass "ManifestLoader accepts Artifact Manifest v1.0"
else
    fail "ManifestLoader rejected valid Artifact Manifest v1.0"
fi

# Validate h2kvmctl can parse the manifest (dry run, will fail on blank disk but should parse OK)
if h2kvmctl --manifest "$TEST_TMPDIR/test-manifest.json" --dry-run 2>&1 | grep -q "Artifact Manifest v1.0 loaded"; then
    pass "h2kvmctl --manifest parses v1.0 manifest"
else
    # Try without root (some operations need root)
    if sudo h2kvmctl --manifest "$TEST_TMPDIR/test-manifest.json" --dry-run 2>&1 | grep -q "Artifact Manifest v1.0 loaded"; then
        pass "h2kvmctl --manifest parses v1.0 manifest (with sudo)"
    else
        warn "h2kvmctl --manifest could not parse test manifest (may need root)"
    fi
fi

# ── Directories ───────────────────────────────────────────────────────────────
section "Directories"

for dir in /var/lib/h2kvm; do
    if [[ -d "$dir" ]]; then
        pass "$dir exists"
    else
        warn "$dir does not exist (create with: sudo mkdir -p $dir)"
    fi
done

# ── Systemd Services (skip with --quick) ──────────────────────────────────────
if ! $QUICK; then
    section "Systemd Services"

    if systemctl list-unit-files 'h2kvm@.service' &>/dev/null; then
        pass "h2kvm@.service template installed"
    else
        warn "h2kvm@.service not installed"
    fi

    if systemctl list-unit-files 'h2kvm.service' &>/dev/null; then
        pass "h2kvm.service installed"
    else
        warn "h2kvm.service not installed"
    fi

    # Check if any instance is running
    running=$(systemctl list-units 'h2kvm@*.service' --no-pager --no-legend 2>/dev/null | grep -c active 2>/dev/null || echo 0)
    if [[ "$running" -gt 0 ]]; then
        pass "$running h2kvm daemon instance(s) active"
    else
        warn "No h2kvm daemon instances running"
    fi
fi

# ── Configuration ─────────────────────────────────────────────────────────────
section "Configuration"

if [[ -d /etc/h2kvm ]]; then
    cfgs=$(find /etc/h2kvm -maxdepth 1 -name '*.yaml' 2>/dev/null | wc -l)
    if [[ "$cfgs" -gt 0 ]]; then
        pass "/etc/h2kvm/ has $cfgs config file(s)"
    else
        warn "/etc/h2kvm/ exists but has no .yaml files"
    fi
else
    warn "/etc/h2kvm/ does not exist"
fi

# ── Go components ─────────────────────────────────────────────────────────────
section "Go Components"

if command -v go &>/dev/null; then
    pass "Go installed: $(go version | awk '{print $3}')"
else
    warn "Go not installed (needed for zkvm/operator development)"
fi

if command -v zkvm &>/dev/null; then
    pass "zkvm binary available"
fi

if command -v h2kvm-operator &>/dev/null; then
    pass "h2kvm-operator binary available"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━ Summary ━━━"
echo "  ✅ Passed: $PASS  ❌ Failed: $FAIL  ⚠️  Warnings: $WARN"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "💥 SELFTEST FAILED — fix the above errors before proceeding"
    exit 1
else
    echo ""
    echo "🎉 SELFTEST PASSED"
    exit 0
fi
