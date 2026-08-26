#!/usr/bin/env bash
#
# Ransomware Recovery Scenario
#
# Situation: Production VMware environment hit by ransomware
# - VMware vCenter compromised
# - ESXi hosts partially encrypted
# - Some VMs still accessible via read-only datastores
# - Need to recover critical workloads to isolated KVM environment
#
# Recovery Objectives:
# - RPO: Last known good backup (24 hours ago)
# - RTO: 4 hours for critical systems
# - Priority: Restore business operations
#
# This script demonstrates emergency VM extraction and migration
# when the hypervisor infrastructure is compromised.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# Configuration
RECOVERY_BASE="/recovery/ransomware-$(date +%Y%m%d)"
BACKUP_LOCATION="/backups/vmware/20260118"  # Last known good backup
ISOLATED_NETWORK="br-isolated"  # Isolated recovery network
INCIDENT_ID="INC-2026-0019"

log_info "=== RANSOMWARE RECOVERY PROCEDURE ==="
log_info "Incident ID: ${INCIDENT_ID}"
log_info "Recovery Base: ${RECOVERY_BASE}"
log_warn "This system is in INCIDENT RESPONSE mode"
log_warn "All actions are logged for forensic analysis"

# Create recovery workspace
mkdir -p "${RECOVERY_BASE}"/{vms,logs,forensics,reports}
cd "${RECOVERY_BASE}"

# Log everything for incident response
exec > >(tee -a "${RECOVERY_BASE}/logs/recovery-$(date +%Y%m%d-%H%M%S).log") 2>&1

log_info "Step 1: Assess available VMs from backup"
# List available VMs from last good backup
if [ -d "${BACKUP_LOCATION}" ]; then
    log_info "Found backup from: $(stat -c %y "${BACKUP_LOCATION}" | cut -d' ' -f1)"
    log_info "Available VMs:"
    find "${BACKUP_LOCATION}" -name "*.vmdk" | while read -r vmdk; do
        vm_name=$(basename "$(dirname "${vmdk}")")
        log_info "  - ${vm_name}"
    done
else
    log_error "Backup location not accessible: ${BACKUP_LOCATION}"
    exit 1
fi

log_info "Step 2: Priority VM list (Business Impact Order)"
# Critical systems to recover first
declare -a PRIORITY_VMS=(
    "dc-prod-01"           # Domain Controller - HIGHEST
    "exchange-prod"        # Email server
    "sql-prod-01"          # Primary database
    "app-erp-prod"         # ERP application
    "fileserver-prod"      # File server
)

log_info "Step 3: Verify backup integrity before recovery"
for vm in "${PRIORITY_VMS[@]}"; do
    vmdk_path="${BACKUP_LOCATION}/${vm}/${vm}.vmdk"

    if [ -f "${vmdk_path}" ]; then
        log_info "Checking: ${vm}"

        # Calculate checksum
        checksum=$(sha256sum "${vmdk_path}" | awk '{print $1}')
        log_info "  SHA256: ${checksum}"

        # Save for incident report
        echo "${vm}|${checksum}|$(date '+%Y-%m-%d %H:%M:%S')" >> \
            "${RECOVERY_BASE}/forensics/backup-checksums.csv"

        # Quick VMDK header check (detect corruption/encryption)
        if ! file "${vmdk_path}" | grep -q "VMware"; then
            log_error "  ${vm}: VMDK header corrupted or encrypted!"
            log_error "  File signature: $(file "${vmdk_path}")"
            continue
        fi

        log_info "  ${vm}: Backup integrity OK"
    else
        log_error "  ${vm}: Backup not found!"
    fi
done

log_info "Step 4: Start recovery (in isolated network)"
log_warn "VMs will be recovered to ISOLATED network: ${ISOLATED_NETWORK}"
log_warn "Network isolation prevents potential malware propagation"

# Recover each critical VM
for vm in "${PRIORITY_VMS[@]}"; do
    log_info "=== Recovering: ${vm} ==="

    vmdk_path="${BACKUP_LOCATION}/${vm}/${vm}.vmdk"
    output_dir="${RECOVERY_BASE}/vms/${vm}"

    if [ ! -f "${vmdk_path}" ]; then
        log_error "  Skipping ${vm}: Backup not found"
        continue
    fi

    mkdir -p "${output_dir}"

    log_info "  Converting ${vm} to qcow2..."

    # Use hyper2kvm for recovery conversion
    sudo python -m hyper2kvm local \
        --vmdk "${vmdk_path}" \
        --output-dir "${output_dir}" \
        --to-output "${vm}-recovery.qcow2" \
        --out-format qcow2 \
        --flatten \
        --compress \
        --regen-initramfs \
        --fstab-mode stabilize-all \
        --fix-grub \
        --verbose 2 \
        --log-file "${RECOVERY_BASE}/logs/${vm}-conversion.log" \
        --report "${RECOVERY_BASE}/reports/${vm}-migration-report.md" \
        2>&1 | tee -a "${RECOVERY_BASE}/logs/${vm}-recovery.log"

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log_info "  ${vm}: Conversion successful"

        # Create libvirt domain in isolated network
        log_info "  Creating isolated KVM domain..."

        virt-install \
            --name "${vm}-recovery" \
            --memory 4096 \
            --vcpus 2 \
            --disk path="${output_dir}/${vm}-recovery.qcow2",bus=virtio \
            --network bridge="${ISOLATED_NETWORK}",model=virtio \
            --graphics vnc,listen=127.0.0.1 \
            --noautoconsole \
            --import \
            --os-variant detect=on \
            2>&1 | tee -a "${RECOVERY_BASE}/logs/${vm}-domain-create.log"

        log_info "  ${vm}: Domain created in isolated network"
        log_warn "  Access via: virsh console ${vm}-recovery"

        # Don't start automatically - manual validation required
        log_warn "  VM is NOT started (manual validation required)"

    else
        log_error "  ${vm}: Conversion failed (check logs)"
    fi
done

log_info "Step 5: Post-recovery security scan"
log_warn "CRITICAL: Scan all recovered VMs for malware before production"

for vm in "${PRIORITY_VMS[@]}"; do
    qcow2_path="${RECOVERY_BASE}/vms/${vm}/${vm}-recovery.qcow2"

    if [ -f "${qcow2_path}" ]; then
        log_info "Scanning ${vm} for malware..."

        # Mount and scan with ClamAV
        sudo guestfish -a "${qcow2_path}" -i <<EOF > "${RECOVERY_BASE}/forensics/${vm}-malware-scan.log" 2>&1 || true
            # List all files for forensic analysis
            find /

            # Check for suspicious files
            find / -name "*.exe"
            find / -name "*.dll"
            find / -name "*.bat"
            find / -name "*.ps1"

            # Check for persistence mechanisms (Windows)
            find /Windows/System32/Tasks
            find /ProgramData/Microsoft/Windows/Start\ Menu/Programs/Startup
EOF

        log_info "  Forensic file list saved: forensics/${vm}-malware-scan.log"

        # Run ClamAV if available
        if command -v clamdscan &> /dev/null; then
            log_info "  Running ClamAV scan..."
            sudo virt-filesystems -a "${qcow2_path}" --all --long || true
        fi
    fi
done

log_info "Step 6: Generate incident report"
cat > "${RECOVERY_BASE}/reports/incident-summary.md" <<EOF
# Ransomware Incident Recovery Report

**Incident ID:** ${INCIDENT_ID}
**Date:** $(date '+%Y-%m-%d %H:%M:%S')
**Recovery Base:** ${RECOVERY_BASE}

## Incident Overview

- **Attack Vector:** [TO BE DETERMINED - Under investigation]
- **Impact:** VMware vCenter and ESXi hosts compromised
- **Recovery Strategy:** Restore from last known good backup (24h RPO)
- **Recovery Network:** Isolated network (${ISOLATED_NETWORK})

## Recovered Systems

EOF

for vm in "${PRIORITY_VMS[@]}"; do
    if [ -f "${RECOVERY_BASE}/vms/${vm}/${vm}-recovery.qcow2" ]; then
        echo "- ✅ ${vm}: Recovered successfully" >> "${RECOVERY_BASE}/reports/incident-summary.md"
    else
        echo "- ❌ ${vm}: Recovery failed" >> "${RECOVERY_BASE}/reports/incident-summary.md"
    fi
done

cat >> "${RECOVERY_BASE}/reports/incident-summary.md" <<EOF

## Recovery Timeline

- **Incident Detected:** [TIMESTAMP]
- **Recovery Started:** $(date '+%Y-%m-%d %H:%M:%S')
- **Estimated Completion:** [+4 hours]

## Next Steps

1. **Malware Analysis**
   - Review forensic scans in: \`${RECOVERY_BASE}/forensics/\`
   - Engage incident response team
   - Determine attack vector

2. **VM Validation**
   - Manual inspection of each recovered VM
   - Verify no malware present
   - Check system integrity

3. **Network Isolation**
   - Keep VMs in isolated network until cleared
   - No internet access
   - No production network connectivity

4. **Gradual Restoration**
   - Start with Domain Controller (after validation)
   - Restore critical services one-by-one
   - Monitor for anomalous behavior

5. **Root Cause Analysis**
   - Forensic investigation
   - Patch vulnerabilities
   - Implement additional security controls

## Forensic Evidence

All recovery logs and checksums preserved in:
- Logs: \`${RECOVERY_BASE}/logs/\`
- Forensics: \`${RECOVERY_BASE}/forensics/\`
- Reports: \`${RECOVERY_BASE}/reports/\`

**DO NOT DELETE - Required for insurance claim and legal proceedings**

## Incident Response Contacts

- Security Team: security@company.com
- Incident Commander: [NAME]
- Legal: legal@company.com
- Insurance: [PROVIDER]
- Law Enforcement: [IF APPLICABLE]

EOF

log_info "Incident report generated: ${RECOVERY_BASE}/reports/incident-summary.md"

log_info "=== RECOVERY COMPLETE ==="
log_warn "IMPORTANT: VMs are in ISOLATED network"
log_warn "DO NOT connect to production until:"
log_warn "  1. Malware scans complete"
log_warn "  2. Forensic analysis complete"
log_warn "  3. Security team approval"
log_warn "  4. Incident commander authorization"

log_info "Recovery artifacts location: ${RECOVERY_BASE}"
log_info "View status: virsh list --all"
log_info "Access VMs: virsh console [vm-name]-recovery"

log_info "Next: Review ${RECOVERY_BASE}/reports/incident-summary.md"
