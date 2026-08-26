# hyper2kvm Examples

Comprehensive examples demonstrating all features of hyper2kvm.

## Performance Highlights

The examples leverage hyper2kvm's enterprise improvements:
- **7x Faster LVM Activation** - Enterprise-grade LVM with device filtering
- **100% Host Protection** - Safe VG activation prevents corruption
- **Production Validated** - Tested with RHEL 8.8 and openSUSE Leap 15.4

See [LVM Enterprise Improvements](../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md) for technical details.

## Quick Start

```bash
# Complete forensic analysis of VM (28 systemd methods)
python3 systemd_forensic_analysis.py /path/to/disk.vmdk

# Pre-migration readiness check
python3 migration_readiness_check.py /path/to/disk.vmdk

# Security audit with HTML report
python3 security_audit.py /path/to/disk.vmdk --format html

# Compare systemd configurations across VMs
python3 systemd_comparison.py vm1.vmdk vm2.vmdk vm3.vmdk

# Performance benchmarking
python3 benchmark_systemd_tools.py vm1.vmdk vm2.vmdk

# Advanced analytics dashboard
python3 analytics_report_generator.py --format html

# View all filesystem APIs (37+ methods)
python3 vmcraft_filesystem_apis.py /path/to/disk.qcow2

# Complete migration workflow
python3 complete_migration_workflow.py /vmware/vm.vmdk /output/kvm
```

## Production Tools

### 1. systemd Forensic Analysis (`systemd_forensic_analysis.py`)

Complete offline forensic analysis using all 28 systemd inspection methods.

**Categories analyzed:**
- Virtualization detection & identity
- Boot performance analysis
- Security compliance & hardening
- Anomaly detection (hidden units, suspicious sockets)
- Crash data (core dumps, pstore)
- Failed services analysis
- Network configuration
- Boot configuration (systemd-boot, UEFI)
- System users & sessions
- Migration readiness assessment
- Advanced configuration (OOM daemon, time sync, extensions)
- Journal analysis

**Usage:**
```bash
python3 systemd_forensic_analysis.py /path/to/disk.vmdk

# Generates:
# - Console output with formatted sections
# - /tmp/forensic_analysis_report.json (detailed JSON report)
# - /tmp/boot-plot.svg (boot timeline visualization)
# - /tmp/journal_export.bin (exported journal logs)
```

**Example output:**
```
Security Compliance Score: 60/100
Migration Ready: YES ✓
Anomalies Found: 0
Core Dumps: 0
Boot Time: 12.34s (kernel: 3.21s, userspace: 9.13s)
```

### 2. Migration Readiness Check (`migration_readiness_check.py`)

Pre-flight validation for VMware to KVM migrations.

**6 comprehensive checks:**
1. Virtualization detection
2. systemd migration readiness
3. Boot configuration compatibility
4. Network configuration portability
5. Security posture assessment
6. Service health validation

**Risk levels:**
- **Minimal**: Ready to migrate immediately
- **Low**: Minor issues, migration should proceed smoothly
- **Medium**: Some issues, recommend fixing before migration
- **High**: Critical blockers, MUST fix before migration

**Usage:**
```bash
python3 migration_readiness_check.py /path/to/vm.vmdk

# Exit codes:
# 0 = Ready with minimal risk
# 1 = Ready but risky (medium/high risk)
# 2 = Not ready (blockers present)

# Generates:
# - Formatted console report with recommendations
# - /tmp/migration_readiness_<vm-name>.json
```

**Example output:**
```
✅ READY FOR MIGRATION
Risk Level: LOW
  Minor issues detected, migration should proceed smoothly.

NEXT STEPS:
1. Perform backup of source VM
2. Test migration in non-production environment
3. Execute migration
4. Run post-migration validation
```

### 3. Security Audit (`security_audit.py`)

Comprehensive security compliance audit with multiple output formats.

**6 audit categories (weighted scoring):**
1. systemd service security (25%)
2. Security compliance checks (25%)
3. Anomaly detection (20%)
4. User & session security (15%)
5. Network security (10%)
6. Boot security (5%)

**Output formats:**
- **JSON**: Machine-readable detailed report
- **HTML**: Visual report with grades and CSS styling
- **Text**: Human-readable console output (default)

**Usage:**
```bash
# Console output (default)
python3 security_audit.py /path/to/vm.vmdk

# HTML report with visual grades
python3 security_audit.py /path/to/vm.vmdk --format html

# JSON for automation/CI
python3 security_audit.py /path/to/vm.vmdk --format json

# Generates:
# - /tmp/security_audit_<vm>_<timestamp>.{html,json,txt}
```

**Example output:**
```
Overall Security Score: 84/100 (Grade: B) 🟡
Risk Level: LOW

Category Scores:
  compliance               60/100
  anomalies               100/100
  user_security            90/100
  network_security        100/100
  boot_security           100/100
```

### 4. systemd Configuration Comparison (`systemd_comparison.py`)

Compare systemd configurations across multiple VMs to identify distribution-specific behaviors.

**Comparison metrics:**
- Virtualization types
- Boot performance
- Security scores
- Anomaly counts
- Failed services
- Network configurations
- Migration readiness
- System extensions

**Usage:**
```bash
python3 systemd_comparison.py vm1.vmdk vm2.vmdk vm3.vmdk

# Generates:
# - Side-by-side comparison table
# - Key differences analysis
# - Per-VM recommendations
# - /tmp/systemd_comparison_report.json
```

**Example output:**
```
Metric                              | Ubuntu          | openSUSE        | Fedora
------------------------------------------------------------------------------
Security Compliance Score           |              75 |              60 |              85
Boot Time (seconds)                 |           12.34 |           15.67 |           10.21
Migration Ready                     |             YES |             YES |             YES
systemd-networkd Files              |               3 |               0 |               5

KEY DIFFERENCES:
🔒 Security Compliance:
   Best:  Fedora (85/100)
   Worst: openSUSE (60/100)
   Gap:   25 points

⚡ Boot Performance:
   Fastest: Fedora (10.21s)
   Slowest: openSUSE (15.67s)
   Diff:    5.46s (53.5% slower)
```

### 5. Performance Benchmark (`benchmark_systemd_tools.py`)

Benchmark all production tools for performance testing and optimization.

**Features**:
- Benchmarks all 4 production tools
- Measures execution time, memory usage, throughput
- Multi-VM testing support
- Performance statistics and insights
- Identifies fastest/slowest tools

**Usage**:
```bash
python3 benchmark_systemd_tools.py vm1.vmdk vm2.vmdk vm3.vmdk

# Generates:
# - /tmp/systemd_tools_benchmark.json
```

**Example output**:
```
Tool Performance Statistics:
Tool                                Avg Time     Min/Max         Avg Mem
--------------------------------------------------------------------------------
systemd_forensic_analysis             5.22s       5.22/5.22 s       0.0 MB
migration_readiness_check             4.53s       4.53/4.53 s       0.0 MB
security_audit                        4.31s       4.31/4.31 s      15.2 MB
filesystem_api_demo                   7.89s       7.89/7.89 s       0.0 MB

Performance Insights:
  ⚡ Fastest tool:  security_audit (4.31s avg)
  🐌 Slowest tool:  filesystem_api_demo (7.89s avg)
  💾 Most memory:   security_audit (15.2 MB avg)
  🚀 Best throughput: security_audit (0.210 GB/s)
```

### 6. Advanced Analytics (`analytics_report_generator.py`)

Generate comprehensive analytics dashboards from aggregated tool outputs.

**Features**:
- Aggregates results from multiple tool runs
- Security compliance tracking over time
- Migration readiness dashboard
- Forensic issue aggregation
- Performance trend analysis
- Multiple output formats (HTML, JSON, Markdown)
- Executive summary with actionable recommendations

**Usage**:
```bash
# Run tools first
python3 systemd_forensic_analysis.py vm*.vmdk
python3 migration_readiness_check.py vm*.vmdk
python3 security_audit.py vm*.vmdk --format json

# Generate analytics
python3 analytics_report_generator.py --format html

# Generates:
# - /tmp/analytics_report.html (visual dashboard)
# - or /tmp/analytics_report.json (machine-readable)
# - or /tmp/analytics_report.md (markdown)
```

**Example output**:
```
## Executive Summary

| Metric | Value |
|--------|-------|
| VMs Audited (Security) | 15 |
| VMs Assessed (Migration) | 15 |
| VMs Analyzed (Forensics) | 12 |

## Security Compliance Dashboard

**Overall Statistics:**
- Average Security Score: **75.2/100**
- Score Range: 45-95
- Grade Distribution: {'A': 3, 'B': 7, 'C': 4, 'F': 1}

## Migration Readiness Dashboard

**Status Overview:**
- ✅ Ready for Migration: **12**
- ❌ Not Ready: **3**
- Risk Distribution: {'minimal': 5, 'low': 7, 'medium': 2, 'high': 1}

## Recommendations

### Security Improvements
**3 VMs** have security scores below 70
**Action**: Run security audit with `--format html` for detailed findings.

### Migration Readiness
**3 VMs** are not ready for migration
**Action**: Review blockers and fix before attempting migration.
```

## API Reference Examples

### 7. systemd API Reference (`systemd_api_reference.py`)

Complete reference for all 46 systemd APIs with code examples.

### 8. Interactive systemd Demo (`demo_systemd_apis.py`)

Interactive demonstration of systemd APIs with real VM analysis.

### 9. Filesystem API Reference (`vmcraft_filesystem_apis.py`)

Comprehensive demonstration of all 37+ filesystem detection and manipulation APIs.

**API Categories covered:**
- OS Inspection (8 methods): `inspect_os()`, `inspect_get_type()`, etc.
- Filesystem Detection (4 methods): `list_filesystems()`, `vfs_type()`, etc.
- Partition Operations (2 methods): `part_to_partnum()`, `part_to_dev()`
- Block Device Operations (9 methods): `blockdev_getsize64()`, `blockdev_getss()`, etc.
- Inspection Wrappers (2 methods): `inspect_filesystems()`, etc.
- Extended Attributes (2 methods): `get_e2attrs()`, `set_e2attrs()`
- Filesystem-Specific (13+ methods): Btrfs, ZFS, XFS, NTFS operations
- Filesystem Statistics: `statvfs()`

**Usage:**
```bash
python3 vmcraft_filesystem_apis.py /path/to/disk.vmdk

# Demonstrates:
# - OS detection and version information
# - Filesystem type detection for all partitions
# - Partition number extraction
# - Block device geometry (size, sector size, etc.)
# - Btrfs subvolume listing
# - ZFS pool and dataset listing
# - Extended attribute operations
# - Filesystem usage statistics
```

**Example output:**
```
PARTITION OPERATIONS:
  part_to_partnum('/dev/nbd0p2') → 2
  part_to_dev('/dev/nbd0p2') → /dev/nbd0

BLOCK DEVICE OPERATIONS:
  Size: 512.00 GiB
  Sector size: 512 bytes
  Block size: 4096 bytes

FILESYSTEM-SPECIFIC:
  Btrfs: 2 filesystems detected
  UUID: 3235f585-e2d1-441f-8ba4-569d4f0ad34d
  Subvolumes: 3 found
```

---

## Migration Workflow Examples

### 10. Complete Migration Workflow (`complete_migration_workflow.py`)

End-to-end VMware to KVM migration with comprehensive pre/post validation.

**Workflow phases:**
1. **Pre-migration inspection**: OS detection, filesystem analysis, service inventory
2. **Migration execution**: VMDK to QCOW2 conversion with all fixers
3. **Post-migration validation**: Boot config, network config, service health
4. **Report generation**: JSON and Markdown migration reports
5. **Libvirt XML creation**: Ready-to-use KVM domain configuration

**Usage:**
```bash
python3 complete_migration_workflow.py /vmware/vm.vmdk /output/kvm-vms

# Generates:
# - /output/kvm-vms/vm-name/vm-name.qcow2 (converted disk)
# - /output/kvm-vms/vm-name/migration-report.json (detailed report)
# - /output/kvm-vms/vm-name/migration-report.md (human-readable)
# - /output/kvm-vms/vm-name/vm-name.xml (libvirt domain XML)
```

**Features:**
- Comprehensive pre-migration OS and service inspection
- Automatic fixer application (bootloader, fstab, network)
- Post-migration validation and comparison
- Detailed migration metrics (time, size, compression ratio)
- libvirt XML with proper hardware mapping
- Success/failure reporting with actionable recommendations

---

### 11. Multi-VM Comparison (`compare_vms.py`)

Compare multiple VM disk images side-by-side for migration planning.

**Comparison categories:**
- Operating system versions and distributions
- Filesystem types and disk layouts
- Disk space usage and capacity
- systemd service configurations
- Package inventories
- Network interface configurations
- Migration complexity scoring (0-100)

**Usage:**
```bash
# Compare 3 VMs
python3 compare_vms.py /vms/web-*.vmdk

# Compare specific VMs with table output
python3 compare_vms.py vm1.vmdk vm2.vmdk vm3.vmdk --format table

# Generate HTML comparison report
python3 compare_vms.py vm*.vmdk --output comparison.html
```

**Features:**
- Side-by-side comparison tables
- Migration complexity scoring based on:
  - OS compatibility with KVM
  - Filesystem complexity (LVM, Btrfs, ZFS)
  - Service count and configuration
  - Disk size and fragmentation
- Priority recommendations (migrate simplest first)
- Configuration drift detection
- Package version comparison

**Example output:**
```
VM COMPARISON SUMMARY
====================

VM Name       OS                    Disk   Services  Complexity  Priority
-------       --                    ----   --------  ----------  --------
web-01        Ubuntu 22.04 LTS      50GB   85        Low (25)    High
web-02        openSUSE Leap 15.4    80GB   102       Medium (55) Medium
web-03        CentOS 7 (EOL)        120GB  156       High (78)   Review

Recommendations:
  1. Migrate web-01 first (lowest complexity, newest OS)
  2. Review web-03 for EOL migration strategy
  3. Consider updating web-02 to Leap 15.5 before migration
```

---

### 12. Migration Benchmark (`benchmark_migration.py`)

Performance benchmarking tool for VM migration operations.

**Metrics measured:**
- Throughput (MB/s) for each migration phase
- Memory usage during migration
- CPU utilization
- Disk I/O (read/write MB)
- Compression ratios
- Time breakdown by phase

**Benchmark categories:**
- Disk format comparison (VMDK vs VHD vs RAW)
- Compression level impact (none, fast, best)
- Filesystem type performance (ext4 vs xfs vs btrfs)
- VM size impact (small/medium/large)

**Usage:**
```bash
# Benchmark single VM (3 iterations)
python3 benchmark_migration.py /vmware/vm.vmdk --iterations 3

# Benchmark with output file
python3 benchmark_migration.py vm.vmdk --output benchmark_results.json

# Compare disk formats
python3 benchmark_migration.py vm.vmdk --format-comparison
```

**Features:**
- Multi-iteration averaging for accurate results
- Per-phase timing (inspection, conversion, validation)
- Memory profiling to detect leaks
- I/O throughput analysis
- Compression ratio vs time trade-offs
- Baseline comparison for regression testing
- JSON and HTML report generation

**Example output:**
```
MIGRATION BENCHMARK RESULTS
===========================

Disk Image: /vmware/production-db.vmdk
Size: 120 GB
Iterations: 3

Phase                    Avg Time    Throughput    Memory    CPU
-----                    --------    ----------    ------    ---
Pre-inspection           4.2s        28.6 GB/s     145 MB    25%
VMDK → QCOW2 conversion  180.5s      0.66 GB/s     512 MB    85%
Fixer application        12.8s       9.4 GB/s      230 MB    40%
Post-validation          5.1s        23.5 GB/s     180 MB    30%
-------------------------------------------------------------------------
Total                    202.6s      0.59 GB/s     Peak: 512 MB

Compression ratio: 2.1:1 (120 GB → 57 GB)
Recommendations:
  ✓ Throughput is good for this VM size
  ⚠ Consider compressing source VMDK for faster transfer
  ✓ Memory usage within acceptable limits
```

## Usage Tips

**For production migrations:**
```bash
# 1. Pre-flight check
python3 migration_readiness_check.py vm.vmdk
# Exit code 0 = proceed, 1 = review warnings, 2 = fix blockers

# 2. Security audit
python3 security_audit.py vm.vmdk --format html
# Review HTML report before migration

# 3. Execute migration
python3 complete_migration_workflow.py vm.vmdk /output/kvm

# 4. Post-migration validation
python3 systemd_forensic_analysis.py /output/kvm/vm.qcow2
```

**For forensic investigation:**
```bash
# Full analysis
python3 systemd_forensic_analysis.py crashed-vm.vmdk

# Check for anomalies
python3 security_audit.py crashed-vm.vmdk

# Review journal logs
# Check /tmp/journal_export.bin
```

**For fleet management:**
```bash
# Compare all VMs
python3 systemd_comparison.py vm*.vmdk

# Audit all VMs
for vm in vm*.vmdk; do
    python3 security_audit.py "$vm" --format json
done

# Aggregate results
jq -s 'map({name: .vm_name, score: .overall_score})' /tmp/security_audit_*.json
```

## What's Next?

### 🎯 I want to try production tools
→ Start with `systemd_forensic_analysis.py` for VM inspection

### 📊 I want migration validation
→ Use `migration_readiness_check.py` for pre-flight checks

### 🔒 I want security audits
→ Run `security_audit.py --format html` for visual reports

### 🚀 I want complete workflows
→ Try `complete_migration_workflow.py` for end-to-end migration

### 📚 I want to learn the APIs
→ Explore `systemd_api_reference.py` and `vmcraft_filesystem_apis.py`

## YAML Configuration Examples

Ready-to-use YAML configs in `yaml/` for declarative migrations:

| Directory | Description |
|-----------|-------------|
| `yaml/10-local/` | Local disk conversion (Linux & Windows) |
| `yaml/20-live-fix/` | Live VM patching |
| `yaml/30-fetch-and-fix/` | Fetch from ESXi and convert |
| `yaml/40-ova-ovf/` | OVA/OVF/RAW import |
| `yaml/50-daemon/` | Daemon mode and systemd integration |
| `yaml/60-vsphere/` | vSphere operations (list, export, snapshot, CBT) |
| `yaml/70-complete-workflows/` | End-to-end migration workflows |

### Complete Workflow Examples

| Config | Description |
|--------|-------------|
| `vsphere-to-libvirt-demo-export.yaml` | vSphere → govc export → libvirt (env var credentials) |
| `vsphere-to-libvirt-{distro}.yaml` | Distro-specific configs (RHEL, Ubuntu, Fedora, etc.) |
| `fetch-and-fix-esxi.yaml` | ESXi SSH download → convert → libvirt |
| `live-fix-ssh.yaml` | Zero-downtime VM prep via SSH |
| `azure-to-libvirt.yaml` | Azure VM export → convert → libvirt |
| `ova-import-to-libvirt.yaml` | OVA/OVF file → convert → libvirt |
| `batch-migration.yaml` | Multiple VMs in one manifest |
| `daemon-watch-mode.yaml` | Auto-process VMDKs dropped into watch dir |

### Demo: vSphere Export to libvirt

The `yaml/70-complete-workflows/vsphere-to-libvirt-demo-export.yaml` example shows a
complete vSphere-to-libvirt export with credentials stored in environment variables.

**Prerequisites:**

```bash
# 1. Install govc (VMware govmomi CLI)
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | tar xzf - -C /usr/local/bin govc
chmod +x /usr/local/bin/govc

# 2. (Optional) Install OVF Tool for ovftool_export mode
#    Download from https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest
#    export PATH=/opt/ovftool:$PATH

# 3. Install pyvmomi
pip install pyvmomi

# 4. Install qemu-img and libguestfs
# Fedora/RHEL:
dnf install qemu-img libguestfs-tools
# Debian/Ubuntu:
apt install qemu-utils libguestfs-tools
```

**Run:**

```bash
# Set connection and VM details
export VCENTER_HOST=vcenter.example.com
export VCENTER_USERNAME=administrator@vsphere.local
export VCENTER_PASSWORD=your-password
export VCENTER_DATACENTER=Production-DC
export VCENTER_VM_NAME=production-web

# Run the migration
h2kvmctl --config examples/yaml/70-complete-workflows/vsphere-to-libvirt-demo-export.yaml
```

The config exports a VM via govc, converts to qcow2, applies guest fixes (fstab, initramfs),
and generates a libvirt domain XML. See the `70-complete-workflows/` directory
for distro-specific examples (Ubuntu, RHEL, Fedora, Windows, etc.).

## See Also

- **[LVM Performance Guide](../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - Technical details on 7x faster LVM
- **[Test Results](../docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Production validation
- **[Tutorials](../docs/tutorials/README.md)** - Step-by-step learning paths
- **[Migration Recipes](../docs/recipes/README.md)** - Quick reference patterns

Individual script help:
```bash
python3 <script>.py --help
```

---

**Last Updated**: February 14, 2026
**Version**: 0.2.2
**Total Examples**: 12+ production-ready tools
**LVM Performance**: 7x faster with 100% host protection
