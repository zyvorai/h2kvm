# Getting Started with h2kvm Production Tools

This guide walks you through using the h2kvm production tools for VM migration, security auditing, and forensic analysis.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Common Workflows](#common-workflows)
5. [Tool Reference](#tool-reference)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+, RHEL 8+, openSUSE Leap 15+)
- **Python**: 3.10 or newer
- **Memory**: 2 GB RAM minimum, 4 GB recommended
- **Disk Space**: 5 GB for tools and reports

### Required Packages

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip \
    qemu-utils \
    systemd

# RHEL/CentOS/Fedora
sudo dnf install -y \
    python3 python3-pip \
    qemu-img \
    systemd

# openSUSE
sudo zypper install -y \
    python3 python3-pip \
    qemu-tools \
    systemd
```

### Optional: Additional Backend Tools

> **Note**: GuestKit is the default backend and uses qemu-nbd and qemu-img. No additional packages are required for the default backend.

### Optional Packages (for advanced features)

```bash
# For NTFS support
sudo apt-get install ntfs-3g

# For Btrfs support
sudo apt-get install btrfs-progs

# For ZFS support (Ubuntu)
sudo apt-get install zfsutils-linux

# For performance monitoring
pip install psutil

# For YAML configuration
pip install pyyaml
```

---

## Installation

### From Source

```bash
# Clone repository
git clone https://github.com/your-org/h2kvm.git
cd h2kvm

# Install Python dependencies
pip install -r requirements.txt

# Add to PATH (optional)
export PATH="$PATH:$(pwd)/examples"
```

### Verify Installation

```bash
# Check Python version
python3 --version  # Should be 3.10+

# Test import
python3 -c "from h2kvm.core import guestkit_client; print('✓ Installation successful')"

# Run quick validation
cd examples
./quick_validation.sh
```

---

## Quick Start

### 1. Your First VM Analysis (5 minutes)

Let's analyze a VM with the forensic analysis tool:

```bash
# Analyze a VM disk image
python3 systemd_forensic_analysis.py /path/to/your-vm.vmdk

# View the report
cat /tmp/forensic_analysis_report.json | jq '.summary'
```

**Expected output**:
```json
{
  "virtualization": {
    "type": "vm",
    "vm": "vmware"
  },
  "machine_id": "abc123...",
  "security_score": 75,
  "anomalies_found": 0,
  "migration_ready": true
}
```

### 2. Check Migration Readiness (3 minutes)

Before migrating a VM, check if it's ready:

```bash
# Run readiness check
python3 migration_readiness_check.py /path/to/your-vm.vmdk

# Check exit code
echo $?
# 0 = ready (minimal/low risk)
# 1 = ready but risky (medium/high risk)
# 2 = not ready (has blockers)
```

**What to look for**:
- ✅ **Ready with minimal risk**: Proceed with migration
- ⚠️ **Ready with medium risk**: Review warnings
- ❌ **Not ready**: Fix blockers before migration

### 3. Security Audit with Visual Report (3 minutes)

Generate a visual security report:

```bash
# Run security audit
python3 security_audit.py /path/to/your-vm.vmdk --format html

# Open in browser
xdg-open /tmp/security_audit_*.html
```

**What you'll see**:
- Overall security score (0-100)
- Letter grade (A-F)
- Findings by category
- Actionable recommendations

---

## Common Workflows

### Workflow 1: Pre-Migration Validation

**Goal**: Ensure VM is ready before migrating from VMware to KVM

```bash
#!/bin/bash
# pre-migration-check.sh

VM_PATH="$1"

echo "=== Pre-Migration Validation ==="
echo ""

# Step 1: Readiness check
echo "[1/3] Running readiness check..."
python3 migration_readiness_check.py "$VM_PATH"
READINESS_EXIT=$?

if [ $READINESS_EXIT -eq 2 ]; then
    echo "❌ VM is not ready for migration"
    echo "   Fix blockers and try again"
    exit 1
elif [ $READINESS_EXIT -eq 1 ]; then
    echo "⚠️  VM is ready but has elevated risk"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 2: Security baseline
echo "[2/3] Generating security baseline..."
python3 security_audit.py "$VM_PATH" --format json
SECURITY_SCORE=$(jq -r '.overall_score' /tmp/security_audit_*.json | tail -1)
echo "   Security score: $SECURITY_SCORE/100"

# Step 3: Forensic analysis
echo "[3/3] Running forensic analysis..."
python3 systemd_forensic_analysis.py "$VM_PATH"

echo ""
echo "✓ Pre-migration validation complete"
echo "  Review reports in /tmp/ before proceeding"
```

**Usage**:
```bash
chmod +x pre-migration-check.sh
./pre-migration-check.sh /vmware/production-db.vmdk
```

### Workflow 2: Fleet Security Audit

**Goal**: Audit security across all VMs in your fleet

```bash
#!/bin/bash
# fleet-security-audit.sh

OUTPUT_DIR="./security-reports"
mkdir -p "$OUTPUT_DIR"

echo "=== Fleet Security Audit ==="
echo ""

# Audit all VMs
for vm in /vmware/*.vmdk; do
    vm_name=$(basename "$vm" .vmdk)
    echo "Auditing: $vm_name"

    python3 security_audit.py "$vm" --format json 2>/dev/null

    # Move report to output directory
    mv /tmp/security_audit_*.json "$OUTPUT_DIR/${vm_name}_audit.json" 2>/dev/null
done

# Generate aggregate report
echo ""
echo "=== Aggregate Results ==="
echo ""

jq -s 'map({
    vm: .vm_name,
    score: .overall_score,
    grade: .grade,
    risk: .risk_level
}) | sort_by(.score)' "$OUTPUT_DIR"/*.json

# Generate analytics dashboard
python3 analytics_report_generator.py --format html
mv /tmp/analytics_report.html "$OUTPUT_DIR/dashboard.html"

echo ""
echo "✓ Fleet audit complete"
echo "  Dashboard: $OUTPUT_DIR/dashboard.html"
```

### Workflow 3: Forensic Investigation

**Goal**: Investigate a VM that has crashed or is behaving abnormally

```bash
#!/bin/bash
# forensic-investigation.sh

VM_PATH="$1"
REPORT_DIR="./forensic-reports/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$REPORT_DIR"

echo "=== Forensic Investigation ==="
echo "VM: $VM_PATH"
echo "Report directory: $REPORT_DIR"
echo ""

# Full forensic analysis
echo "[1/4] Running comprehensive forensic analysis..."
python3 systemd_forensic_analysis.py "$VM_PATH"
cp /tmp/forensic_analysis_report.json "$REPORT_DIR/"
cp /tmp/boot-plot.svg "$REPORT_DIR/" 2>/dev/null
cp /tmp/journal_export.bin "$REPORT_DIR/" 2>/dev/null

# Security anomaly detection
echo "[2/4] Detecting security anomalies..."
python3 security_audit.py "$VM_PATH" --format html
cp /tmp/security_audit_*.html "$REPORT_DIR/security_audit.html"

# Filesystem inspection
echo "[3/4] Inspecting filesystem..."
python3 filesystem_api_demo.py "$VM_PATH"
cp /tmp/filesystem_api_demo_*.json "$REPORT_DIR/"

# Extract key findings
echo "[4/4] Extracting key findings..."
cat > "$REPORT_DIR/summary.txt" << EOF
Forensic Investigation Summary
==============================
Date: $(date)
VM: $VM_PATH

Core Dumps: $(jq -r '.coredumps | length' "$REPORT_DIR/forensic_analysis_report.json")
Anomalies: $(jq -r '.anomalies | map(length) | add' "$REPORT_DIR/forensic_analysis_report.json")
Failed Services: $(jq -r '.failures.failed_units | length' "$REPORT_DIR/forensic_analysis_report.json")
Security Score: $(jq -r '.compliance.score' "$REPORT_DIR/forensic_analysis_report.json")/100

Review detailed reports in: $REPORT_DIR/
EOF

cat "$REPORT_DIR/summary.txt"
echo ""
echo "✓ Forensic investigation complete"
```

### Workflow 4: Performance Benchmarking

**Goal**: Benchmark tool performance and track trends

```bash
#!/bin/bash
# benchmark-tools.sh

VMS_TO_TEST=(
    "/vmware/small-vm.vmdk"
    "/vmware/medium-vm.vmdk"
    "/vmware/large-vm.vmdk"
)

echo "=== Tool Performance Benchmark ==="
echo ""

# Run benchmark
python3 benchmark_systemd_tools.py "${VMS_TO_TEST[@]}"

# Extract key metrics
echo ""
echo "=== Key Metrics ==="
jq -r '.tool_statistics | to_entries[] |
    "\(.key): \(.value.avg_time)s avg, \(.value.avg_memory) MB"' \
    /tmp/systemd_tools_benchmark.json

# Compare against baselines
echo ""
echo "=== Performance vs Baseline ==="
# TODO: Add baseline comparison logic

echo ""
echo "✓ Benchmark complete"
echo "  Full report: /tmp/systemd_tools_benchmark.json"
```

---

## Tool Reference

### 1. systemd_forensic_analysis.py

**Purpose**: Complete offline VM forensic analysis

**Usage**:
```bash
python3 systemd_forensic_analysis.py <vm-disk-path>
```

**Output**:
- `/tmp/forensic_analysis_report.json` - Complete analysis
- `/tmp/boot-plot.svg` - Boot timeline visualization
- `/tmp/journal_export.bin` - Exported system logs

**Key Insights**:
- Virtualization type and machine ID
- Boot performance analysis
- Security compliance score
- Anomaly detection
- Crash data (coredumps, kernel panics)
- Failed services
- Network and boot configuration

**When to use**:
- Post-crash investigation
- Pre-migration analysis
- Security audits
- Performance troubleshooting

### 2. migration_readiness_check.py

**Purpose**: Pre-flight migration validation

**Usage**:
```bash
python3 migration_readiness_check.py <vm-disk-path>

# Check exit code
echo $?  # 0=ready, 1=risky, 2=blocked
```

**Output**:
- `/tmp/migration_readiness_<vm>.json` - Detailed assessment
- Console: Formatted report with recommendations

**Risk Levels**:
- **Minimal**: No issues, proceed
- **Low**: Minor issues, should proceed smoothly
- **Medium**: Some issues, recommend fixing first
- **High**: Critical blockers, must fix before migration

**Checks Performed**:
1. Virtualization detection
2. systemd migration readiness
3. Boot configuration compatibility
4. Network configuration portability
5. Security posture
6. Service health

**When to use**:
- Before any VMware to KVM migration
- As part of CI/CD pipeline
- Migration planning

### 3. security_audit.py

**Purpose**: Security compliance audit

**Usage**:
```bash
# Text output (console)
python3 security_audit.py <vm-disk-path>

# HTML report (visual)
python3 security_audit.py <vm-disk-path> --format html

# JSON (machine-readable)
python3 security_audit.py <vm-disk-path> --format json
```

**Output**:
- `/tmp/security_audit_<vm>_<timestamp>.html` - Visual report
- `/tmp/security_audit_<vm>_<timestamp>.json` - Machine-readable
- Console: Text summary

**Scoring**:
- 90-100: Grade A (Excellent)
- 80-89: Grade B (Good)
- 70-79: Grade C (Fair)
- 60-69: Grade D (Poor)
- 0-59: Grade F (Failing)

**Categories Audited** (weighted):
1. systemd service security (25%)
2. Security compliance checks (25%)
3. Anomaly detection (20%)
4. User & session security (15%)
5. Network security (10%)
6. Boot security (5%)

**When to use**:
- Regular security audits
- Compliance reporting
- Before production deployment
- Security baseline establishment

### 4. systemd_comparison.py

**Purpose**: Compare configurations across multiple VMs

**Usage**:
```bash
python3 systemd_comparison.py <vm1> <vm2> <vm3> ...
```

**Output**:
- `/tmp/systemd_comparison_report.json` - Comparison data
- Console: Side-by-side comparison table

**Comparisons**:
- Virtualization types
- Boot performance
- Security scores
- Anomaly counts
- Failed services
- Network configurations
- Migration readiness

**When to use**:
- Fleet configuration management
- Distribution comparison
- Migration impact analysis
- Configuration drift detection

### 5. filesystem_api_demo.py

**Purpose**: Demonstrate filesystem detection APIs

**Usage**:
```bash
python3 filesystem_api_demo.py <vm-disk-path>
```

**Output**:
- `/tmp/filesystem_api_demo_<vm>.json` - API results
- Console: Detailed API demonstration

**APIs Demonstrated** (33 total):
- OS inspection (8 methods)
- Filesystem detection (3 methods)
- Block device operations (10 methods)
- Partition operations (2 methods)
- High-level inspection (2 methods)
- Extended attributes (2 methods)
- Filesystem-specific operations (6 methods)

**When to use**:
- Learning the API
- Filesystem troubleshooting
- Custom script development

### 6. benchmark_systemd_tools.py

**Purpose**: Performance benchmarking

**Usage**:
```bash
python3 benchmark_systemd_tools.py <vm1> <vm2> ...
```

**Output**:
- `/tmp/systemd_tools_benchmark.json` - Benchmark results
- Console: Performance statistics

**Metrics**:
- Execution time (seconds)
- Memory usage (MB)
- Throughput (GB/s)
- Performance insights

**When to use**:
- Performance regression testing
- Capacity planning
- Optimization validation

### 7. analytics_report_generator.py

**Purpose**: Advanced analytics dashboard

**Usage**:
```bash
# Run some tools first
python3 systemd_forensic_analysis.py vm*.vmdk
python3 migration_readiness_check.py vm*.vmdk
python3 security_audit.py vm*.vmdk --format json

# Generate analytics
python3 analytics_report_generator.py --format html
```

**Output**:
- `/tmp/analytics_report.html` - Visual dashboard
- `/tmp/analytics_report.json` - Machine-readable
- `/tmp/analytics_report.md` - Markdown summary

**Dashboards**:
- Security compliance overview
- Migration readiness status
- Forensic issue aggregation
- Performance metrics

**When to use**:
- Fleet management
- Trend analysis
- Executive reporting
- Long-term tracking

---

## Configuration

### Configuration File

Copy the example configuration:

```bash
mkdir -p ~/.config/h2kvm
cp examples/h2kvm-tools.yaml.example ~/.config/h2kvm/tools.yaml
```

Edit the configuration:

```bash
vi ~/.config/h2kvm/tools.yaml
```

### Environment Variables

```bash
# Override output directory
export H2KVM_OUTPUT_DIR=/var/lib/h2kvm/reports

# Enable verbose logging
export H2KVM_VERBOSE=1

# Set default format
export H2KVM_FORMAT=html
```

### Command-Line Options

Most tools support these common options:

```bash
# Specify output format
--format {json,html,markdown,text}

# Increase verbosity
--verbose or -v

# Specify output directory
--output-dir /path/to/reports
```

---

## Troubleshooting

### Common Issues

#### 1. "RuntimeError: Not launched"

**Cause**: GuestKit couldn't access the disk image

**Solution**:
```bash
# Check file exists and is readable
ls -lh /path/to/vm.vmdk

# Check permissions
chmod 644 /path/to/vm.vmdk

# Try with sudo if needed
sudo python3 systemd_forensic_analysis.py /path/to/vm.vmdk
```

#### 2. "No operating systems detected"

**Cause**: Disk image is empty, corrupted, or not a bootable system

**Solution**:
```bash
# Verify disk image
qemu-img info /path/to/vm.vmdk

# Check if it's a valid VM disk
file /path/to/vm.vmdk

# Try with different disk format
python3 systemd_forensic_analysis.py /path/to/vm.qcow2
```

#### 3. Tools running slowly

**Cause**: Large disk images or limited resources

**Solution**:
```bash
# Check VM size
ls -lh /path/to/vm.vmdk

# Run on smaller test VM first
python3 systemd_forensic_analysis.py /path/to/small-vm.vmdk

# Increase timeout (if using scripts)
timeout 600 python3 systemd_forensic_analysis.py /path/to/large-vm.vmdk
```

#### 4. "No module named 'guestfs'"

**Cause**: Missing guestfs Python bindings. This is only needed if you are using an alternative guestfs backend instead of the default GuestKit backend.

**Solution**:
```bash
# Ubuntu/Debian
sudo apt-get install python3-guestfs

# RHEL/CentOS/Fedora
sudo dnf install python3-guestfs

# openSUSE
sudo zypper install python3-guestfs
```

### Getting Help

1. **Check documentation**:
   ```bash
   # Tool help
   python3 migration_readiness_check.py --help

   # API reference
   cat docs/API_QUICK_REFERENCE.md
   ```

2. **Enable verbose logging**:
   ```bash
   python3 systemd_forensic_analysis.py /path/to/vm.vmdk --verbose
   ```

3. **Check logs**:
   ```bash
   # System logs
   journalctl -xe | grep h2kvm

   # Tool logs (if configured)
   tail -f /var/log/h2kvm/tools.log
   ```

4. **Report issues**:
   - GitHub Issues: https://github.com/your-org/h2kvm/issues
   - Include: Tool version, OS version, error message, VM disk format

---

## Next Steps

Now that you're familiar with the basics:

1. **Explore Advanced Features**:
   - Configure notifications
   - Set up CI/CD integration
   - Create custom workflows

2. **Integrate with Your Environment**:
   - Add to migration pipeline
   - Schedule regular security audits
   - Automate forensic analysis

3. **Learn the APIs**:
   - Review `docs/API_QUICK_REFERENCE.md`
   - Study example scripts
   - Build custom tools

4. **Join the Community**:
   - Contribute improvements
   - Share workflows
   - Report bugs

---

**Happy VM analyzing!** 🚀
