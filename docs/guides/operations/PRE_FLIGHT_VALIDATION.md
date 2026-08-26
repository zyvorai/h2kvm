# Pre-Flight Validation Guide

Complete validation checks to ensure your environment is ready for VM migrations.

---

## Quick Links

- [Installation Validation](#installation-validation)
- [System Requirements](#system-requirements-validation)
- [Network Validation](#network-validation)
- [Storage Validation](#storage-validation)
- [Source VM Validation](#source-vm-validation)
- [Quick Validation Script](#quick-validation-script)

---

## Overview

Run these validation checks before starting any migrations to:
- ✅ Verify H2KVM is properly installed
- ✅ Confirm system meets requirements
- ✅ Validate network connectivity
- ✅ Check storage capacity
- ✅ Test source VM accessibility
- ✅ Identify potential issues early

**Estimated Time**: 15-30 minutes

---

## Installation Validation

### 1. Verify H2KVM Installation

```bash
# Check H2KVM is installed
h2kvmctl --version
h2kvm --version

# Expected output: h2kvm version 2.1.0 (or later)
```

**✅ Pass**: Version displays correctly
**❌ Fail**: Command not found → [Install H2KVM](getting-started/01-Installation.md)

---

### 2. Verify Python Environment

```bash
# Check Python version
python3 --version

# Expected: Python 3.10.0 or later
```

**✅ Pass**: Python 3.10+
**❌ Fail**: Python < 3.10 → Upgrade Python

```bash
# Check pip
pip --version
pip list | grep h2kvm

# Expected: h2kvm package listed
```

---

### 3. Verify Dependencies

```bash
# Check qemu-img (required)
qemu-img --version

# Expected: QEMU 6.0+ or later
```

**✅ Pass**: qemu-img 6.0+
**❌ Fail**: Not installed or old version

```bash
# Fedora/RHEL/CentOS
sudo dnf install -y qemu-img qemu-system-x86

# Ubuntu/Debian
sudo apt-get install -y qemu-utils qemu-system-x86
```

---

### 4. Verify Optional Dependencies

**For Windows VM Support**:
```bash
# Check ntfs-3g
which ntfs-3g

# Check libhivex
which hivexsh
```

**✅ Pass**: Both commands found
**⚠️ Warning**: Missing → Windows migrations may not work

```bash
# Install if missing
# Fedora/RHEL/CentOS
sudo dnf install -y ntfs-3g libhivex-bin

# Ubuntu/Debian
sudo apt-get install -y ntfs-3g libhivex-bin
```

---

### 5. Test Basic Functionality

```bash
# Test help command
h2kvmctl --help

# Test config validation
cat > /tmp/test-config.yaml << EOF
command: local
vmdk: /tmp/test.vmdk
output_dir: /tmp
to_output: test.qcow2
EOF

# Validate config (will fail on missing VMDK, which is expected)
h2kvmctl --config /tmp/test-config.yaml --dry-run 2>&1 | head -5
```

**✅ Pass**: Config loads, shows error about missing VMDK
**❌ Fail**: Python errors or cannot parse YAML

---

## System Requirements Validation

### 1. CPU Check

```bash
# Check CPU count
nproc

# Check CPU features
lscpu | grep -E "Model name|CPU\(s\)|Thread|Core"

# Check virtualization support
grep -E '(vmx|svm)' /proc/cpuinfo
```

**Minimum Requirements**:
- ✅ 2+ CPUs
- ✅ Virtualization enabled (vmx/svm)

**Recommended**:
- ✅ 4+ CPUs for better performance
- ✅ 8+ CPUs for batch migrations

---

### 2. Memory Check

```bash
# Check total memory
free -h

# Check available memory
free -h | grep Mem | awk '{print $7}'
```

**Minimum Requirements**:
- ✅ 4 GB total RAM
- ✅ 2 GB available RAM

**Recommended**:
- ✅ 8+ GB total RAM
- ✅ 4+ GB available RAM
- ✅ 16+ GB for batch migrations

**⚠️ Warning**: If available < 2 GB:
```bash
# Free up memory
sync
echo 3 > /proc/sys/vm/drop_caches
```

---

### 3. Disk Space Check

```bash
# Check available disk space
df -h

# Check space in output directory
df -h /kvm/vms  # Replace with your output_dir

# Check space in temp directory
df -h /tmp
df -h /var/tmp
```

**Minimum Requirements**:
- ✅ 2x source VMDK size for output
- ✅ 1x source VMDK size for temp space

**Example**: For 100 GB VMDK:
- Output directory: 200 GB free (for qcow2 + working space)
- Temp directory: 100 GB free

**✅ Pass**: Sufficient space
**❌ Fail**: Insufficient space → Free up disk or use different location

```bash
# Check largest files
du -sh /var/* | sort -h | tail -10

# Clean up if needed
# Remove old logs, temp files, unused packages
```

---

### 4. I/O Performance Check

```bash
# Test write performance
dd if=/dev/zero of=/tmp/testfile bs=1G count=1 oflag=direct

# Expected: > 100 MB/s for good performance

# Test read performance
dd if=/tmp/testfile of=/dev/null bs=1G count=1 iflag=direct

# Cleanup
rm /tmp/testfile
```

**✅ Pass**: > 100 MB/s
**⚠️ Warning**: 50-100 MB/s (acceptable but slower)
**❌ Fail**: < 50 MB/s (very slow, consider faster storage)

---

### 5. System Load Check

```bash
# Check current load
uptime

# Check processes
top -b -n 1 | head -20

# Check I/O wait
iostat -x 1 3
```

**✅ Pass**: Load average < number of CPUs
**⚠️ Warning**: Load average = number of CPUs (system busy)
**❌ Fail**: Load average > 2x CPUs (system overloaded)

**If system is overloaded**:
- Wait for load to decrease
- Identify and stop non-essential processes
- Consider migrating during off-hours

---

## Network Validation

### 1. Network Connectivity

```bash
# Test internet connectivity
ping -c 4 8.8.8.8

# Test DNS
nslookup google.com
```

**✅ Pass**: Ping and DNS working
**❌ Fail**: Network issues → Check network configuration

---

### 2. Source Host Connectivity

**For Remote Migrations**:

```bash
# Test ESXi/vCenter connectivity
ping -c 4 esxi-host.example.com

# Test SSH access
ssh root@esxi-host.example.com "echo test"

# Test with key authentication
ssh -i ~/.ssh/id_rsa root@esxi-host.example.com "echo test"
```

**✅ Pass**: SSH works with key auth
**❌ Fail**: Cannot connect → Check SSH keys and firewall

**Setup SSH keys if needed**:
```bash
# Generate key if you don't have one
ssh-keygen -t rsa -b 4096

# Copy key to ESXi
ssh-copy-id -i ~/.ssh/id_rsa.pub root@esxi-host.example.com

# Test
ssh root@esxi-host.example.com "echo success"
```

---

### 3. Network Bandwidth Test

**For Remote Migrations**:

```bash
# Test network speed with iperf3 (if available)
# On ESXi host: iperf3 -s
# On migration host:
iperf3 -c esxi-host.example.com -t 10

# Or use simple transfer test
time scp root@esxi-host.example.com:/tmp/testfile /tmp/
```

**Recommended Bandwidth**:
- ✅ 1 Gbps: Good (typical migration times)
- ⚠️ 100 Mbps: Acceptable (slower migrations)
- ❌ < 100 Mbps: Very slow (consider local export first)

---

### 4. vCenter API Test

**For vSphere Integration**:

```bash
# Test vCenter connectivity
curl -k https://vcenter.example.com/

# Expected: HTML response or redirect
```

**✅ Pass**: vCenter responds
**❌ Fail**: No response → Check vCenter hostname/IP

---

## Storage Validation

### 1. Output Directory Check

```bash
# Verify output directory exists
ls -ld /kvm/vms

# Check permissions
test -w /kvm/vms && echo "Writable" || echo "Not writable"

# Create if doesn't exist
mkdir -p /kvm/vms
chmod 755 /kvm/vms
```

**✅ Pass**: Directory exists and writable
**❌ Fail**: Cannot write → Check permissions

---

### 2. Filesystem Type Check

```bash
# Check filesystem type
df -T /kvm/vms

# Check filesystem features
tune2fs -l /dev/sda1 | grep -i features  # for ext4
xfs_info /dev/sda1  # for XFS
```

**Recommended Filesystems**:
- ✅ XFS (best for large files)
- ✅ ext4 (good performance)
- ⚠️ NFS (acceptable, may be slower)
- ❌ FAT32 (not suitable, file size limits)

---

### 3. Storage Performance Benchmark

```bash
# Install fio if not available
# Fedora: sudo dnf install fio
# Ubuntu: sudo apt-get install fio

# Test sequential write
fio --name=seqwrite --ioengine=libaio --iodepth=4 \
    --rw=write --bs=1M --direct=1 --size=1G \
    --numjobs=1 --runtime=60 --directory=/kvm/vms

# Test random write
fio --name=randwrite --ioengine=libaio --iodepth=16 \
    --rw=randwrite --bs=4k --direct=1 --size=1G \
    --numjobs=4 --runtime=60 --directory=/kvm/vms
```

**Good Performance**:
- ✅ Sequential write: > 200 MB/s
- ✅ Random write: > 50 MB/s (IOPS > 10,000)

**Acceptable Performance**:
- ⚠️ Sequential write: 100-200 MB/s
- ⚠️ Random write: 20-50 MB/s

---

## Source VM Validation

### 1. VMDK File Validation

```bash
# Check VMDK exists
ls -lh /vmware/vm.vmdk

# Check VMDK is readable
test -r /vmware/vm.vmdk && echo "Readable" || echo "Not readable"

# Get VMDK info
qemu-img info /vmware/vm.vmdk
```

**✅ Pass**: File exists, readable, qemu-img shows info
**❌ Fail**: File missing or unreadable → Check path and permissions

---

### 2. VMDK Inspection

```bash
# Run VMDK inspector
./scripts/vmdk_inspect.py /vmware/vm.vmdk

# Save report
./scripts/vmdk_inspect.py /vmware/vm.vmdk > vm-inspection.txt
```

**Review for**:
- ✅ OS detected correctly
- ✅ No corruption detected
- ✅ Filesystem types identified
- ⚠️ Any warnings or issues noted

**Common Issues**:
- Cloned VM → Use `xfs_regenerate_uuid: true`
- BusLogic SCSI → Automatic fix available
- Multiple disks → Migrate separately

---

### 3. VMDK Size Validation

```bash
# Check VMDK size
du -sh /vmware/vm.vmdk

# Check virtual size
qemu-img info /vmware/vm.vmdk | grep "virtual size"

# Calculate required space
# Output needs: virtual size * 1.1 (for qcow2)
# Temp needs: virtual size (during conversion)
```

**Example**: 100 GB virtual size
- Output: 110 GB free space required
- Temp: 100 GB free space required
- Total: 210 GB recommended

---

### 4. Source VM State Check

**For Live/Running VMs**:

```bash
# On ESXi, check VM is powered off
ssh root@esxi-host "vim-cmd vmsvc/getallvms | grep vm-name"
ssh root@esxi-host "vim-cmd vmsvc/power.getstate VM_ID"
```

**✅ Recommended**: VM powered off (for cold migration)
**⚠️ Warning**: VM running (create snapshot first)

---

## Test Migration

### 1. Small Test VM

```bash
# Create small test VMDK (if you have one)
# Or use smallest production VM

# Test migration
cat > /tmp/test-migration.yaml << EOF
command: local
vmdk: /vmware/test-vm.vmdk
output_dir: /tmp/test-output
to_output: test-vm.qcow2

fstab_mode: stabilize-all
regen_initramfs: true
compress: false
libvirt_test: true
EOF

# Run test
mkdir -p /tmp/test-output
h2kvmctl --config /tmp/test-migration.yaml
```

**✅ Pass**: Migration completes, VM boots
**❌ Fail**: Review errors, fix issues before production migration

---

### 2. Validate Test Output

```bash
# Check output file
qemu-img info /tmp/test-output/test-vm.qcow2
qemu-img check /tmp/test-output/test-vm.qcow2

# Test boot
virsh define /tmp/test-output/test-vm.xml
virsh start test-vm
virsh console test-vm
```

**✅ Pass**: File created, no errors, VM boots
**❌ Fail**: Investigate and fix before production

---

## Quick Validation Script

```bash
#!/bin/bash
# pre-flight-check.sh - Automated validation

echo "=== H2KVM Pre-Flight Validation ==="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
WARN=0
FAIL=0

check_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

check_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARN++))
}

check_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

# 1. Check H2KVM installation
echo "1. Checking H2KVM installation..."
if command -v h2kvmctl &> /dev/null; then
    VERSION=$(h2kvmctl --version 2>&1 | head -1)
    check_pass "H2KVM installed: $VERSION"
else
    check_fail "H2KVM not found. Install with: pip install 'h2kvm[full]'"
fi

# 2. Check Python version
echo "2. Checking Python version..."
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version | cut -d' ' -f2)
    PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
    PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        check_pass "Python $PY_VERSION (>= 3.10 required)"
    else
        check_fail "Python $PY_VERSION (3.10+ required)"
    fi
else
    check_fail "Python 3 not found"
fi

# 3. Check qemu-img
echo "3. Checking qemu-img..."
if command -v qemu-img &> /dev/null; then
    QEMU_VERSION=$(qemu-img --version | head -1)
    check_pass "qemu-img found: $QEMU_VERSION"
else
    check_fail "qemu-img not found. Install with: dnf install qemu-img"
fi

# 4. Check CPU count
echo "4. Checking CPU resources..."
CPU_COUNT=$(nproc)
if [ "$CPU_COUNT" -ge 4 ]; then
    check_pass "$CPU_COUNT CPUs (4+ recommended)"
elif [ "$CPU_COUNT" -ge 2 ]; then
    check_warn "$CPU_COUNT CPUs (4+ recommended for best performance)"
else
    check_fail "$CPU_COUNT CPUs (minimum 2 required)"
fi

# 5. Check memory
echo "5. Checking memory..."
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_TOTAL_GB=$((MEM_TOTAL_KB / 1024 / 1024))
MEM_AVAIL_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
MEM_AVAIL_GB=$((MEM_AVAIL_KB / 1024 / 1024))

if [ "$MEM_TOTAL_GB" -ge 8 ]; then
    check_pass "${MEM_TOTAL_GB}GB total RAM (8+ recommended)"
elif [ "$MEM_TOTAL_GB" -ge 4 ]; then
    check_warn "${MEM_TOTAL_GB}GB total RAM (8+ recommended)"
else
    check_fail "${MEM_TOTAL_GB}GB total RAM (minimum 4GB required)"
fi

if [ "$MEM_AVAIL_GB" -ge 2 ]; then
    check_pass "${MEM_AVAIL_GB}GB available RAM"
else
    check_warn "${MEM_AVAIL_GB}GB available RAM (2+ recommended)"
fi

# 6. Check disk space
echo "6. Checking disk space..."
if [ -d "/kvm/vms" ]; then
    DISK_AVAIL=$(df -BG /kvm/vms | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "$DISK_AVAIL" -ge 100 ]; then
        check_pass "${DISK_AVAIL}GB available in /kvm/vms"
    elif [ "$DISK_AVAIL" -ge 50 ]; then
        check_warn "${DISK_AVAIL}GB available in /kvm/vms (100+ recommended)"
    else
        check_fail "${DISK_AVAIL}GB available in /kvm/vms (50+ minimum)"
    fi
else
    check_warn "/kvm/vms does not exist (will be created)"
fi

# 7. Check virtualization support
echo "7. Checking virtualization support..."
if grep -qE '(vmx|svm)' /proc/cpuinfo; then
    check_pass "CPU virtualization enabled (vmx/svm)"
else
    check_warn "CPU virtualization may not be enabled"
fi

# 8. Check system load
echo "8. Checking system load..."
LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
LOAD_INT=$(echo $LOAD_AVG | cut -d. -f1)
if [ "$LOAD_INT" -lt "$CPU_COUNT" ]; then
    check_pass "System load: $LOAD_AVG (CPUs: $CPU_COUNT)"
else
    check_warn "System load high: $LOAD_AVG (CPUs: $CPU_COUNT)"
fi

# Summary
echo ""
echo "=== Summary ==="
echo -e "${GREEN}Passed${NC}: $PASS"
if [ "$WARN" -gt 0 ]; then
    echo -e "${YELLOW}Warnings${NC}: $WARN"
fi
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Failed${NC}: $FAIL"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✓ System ready for migration${NC}"
    exit 0
else
    echo -e "${RED}✗ Fix failed checks before migrating${NC}"
    exit 1
fi
```

**Usage**:
```bash
chmod +x pre-flight-check.sh
./pre-flight-check.sh
```

---

## Validation Results

### All Checks Pass ✅

Your system is ready for migrations! Next steps:

1. **Plan your migration**
   - [ ] Review [Migration Decision Tree](MIGRATION_DECISION_TREE.md)
   - [ ] Choose migration approach
   - [ ] Prepare YAML configurations

2. **Test with small VM**
   - [ ] Migrate test VM
   - [ ] Validate results
   - [ ] Document any issues

3. **Proceed with production**
   - [ ] Follow [Migration Checklist](MIGRATION_CHECKLIST.md)
   - [ ] Monitor progress
   - [ ] Validate results

---

### Some Warnings ⚠️

Review warnings and decide if acceptable:
- **Performance warnings**: May result in slower migrations
- **Resource warnings**: May need to limit parallel migrations
- **Network warnings**: May need longer timeouts

**Recommendation**: Test with a small VM first

---

### Critical Failures ❌

Fix critical failures before proceeding:

**Installation issues**:
- Install H2KVM: `pip install "h2kvm[full]"`
- Install dependencies: `dnf install qemu-img qemu-system-x86`

**Resource issues**:
- Free up disk space
- Free up memory
- Wait for system load to decrease

**Network issues**:
- Fix connectivity problems
- Setup SSH keys
- Check firewall rules

---

## Troubleshooting Common Issues

### "h2kvmctl: command not found"

```bash
# Check if installed
pip list | grep h2kvm

# If not installed
pip install "h2kvm[full]"

# If installed but not in PATH
export PATH=$PATH:~/.local/bin
# Add to ~/.bashrc for persistence
```

### "qemu-img: command not found"

```bash
# Fedora/RHEL/CentOS
sudo dnf install qemu-img qemu-system-x86

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install qemu-utils qemu-system-x86
```

### "Insufficient disk space"

```bash
# Find large files
du -sh /var/* | sort -h | tail -10

# Clean up
sudo journalctl --vacuum-time=7d
sudo dnf clean all  # or apt-get clean
docker system prune -a  # if using Docker

# Or use different output directory with more space
```

### "Cannot connect to ESXi"

```bash
# Test SSH manually
ssh -v root@esxi-host.example.com

# Check SSH keys
ls -l ~/.ssh/id_rsa*

# Generate if missing
ssh-keygen -t rsa -b 4096

# Copy to ESXi
ssh-copy-id root@esxi-host.example.com
```

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
