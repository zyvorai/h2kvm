# Automation Scripts Collection

Practical automation scripts for streamlining VM migration workflows with Hyper2KVM.

---

## Quick Links

- [Pre-Migration Scripts](#pre-migration-scripts)
- [Migration Execution Scripts](#migration-execution-scripts)
- [Post-Migration Scripts](#post-migration-scripts)
- [Validation Scripts](#validation-scripts)
- [Monitoring Scripts](#monitoring-scripts)
- [Utility Scripts](#utility-scripts)

---

## Overview

This collection provides production-ready automation scripts for:
- **Pre-migration validation and preparation**
- **Batch migration orchestration**
- **Post-migration validation and testing**
- **Ongoing monitoring and health checks**
- **Common administrative tasks**

All scripts are tested, documented, and ready to use.

---

## Pre-Migration Scripts

### 1. Bulk VMDK Inspector

Inspect multiple VMDKs and generate a consolidated report.

**File**: `scripts/bulk-vmdk-inspect.sh`

```bash
#!/bin/bash
# Bulk VMDK Inspection Script
# Usage: ./bulk-vmdk-inspect.sh /path/to/vmware/vms

set -euo pipefail

VMDK_DIR="${1:?Usage: $0 <vmdk-directory>}"
OUTPUT_DIR="${2:-./inspection-reports}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SUMMARY_FILE="${OUTPUT_DIR}/summary-${TIMESTAMP}.txt"

mkdir -p "$OUTPUT_DIR"

echo "=== Bulk VMDK Inspection Report ===" > "$SUMMARY_FILE"
echo "Date: $(date)" >> "$SUMMARY_FILE"
echo "Source: $VMDK_DIR" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"

total=0
healthy=0
warnings=0
errors=0

for vmdk in "$VMDK_DIR"/*.vmdk; do
    [ -f "$vmdk" ] || continue

    vm_name=$(basename "$vmdk" .vmdk)
    report_file="${OUTPUT_DIR}/${vm_name}-${TIMESTAMP}.txt"

    echo "Inspecting: $vm_name"
    total=$((total + 1))

    # Run inspection
    if python3 ./scripts/vmdk_inspect.py "$vmdk" > "$report_file" 2>&1; then
        # Check for warnings
        if grep -qi "warning" "$report_file"; then
            warnings=$((warnings + 1))
            echo "  ⚠️  Warnings found"
            echo "⚠️  $vm_name - Has warnings" >> "$SUMMARY_FILE"
        else
            healthy=$((healthy + 1))
            echo "  ✅ Healthy"
            echo "✅ $vm_name - Healthy" >> "$SUMMARY_FILE"
        fi
    else
        errors=$((errors + 1))
        echo "  ❌ Errors found"
        echo "❌ $vm_name - Has errors" >> "$SUMMARY_FILE"
    fi
done

echo "" >> "$SUMMARY_FILE"
echo "=== Summary ===" >> "$SUMMARY_FILE"
echo "Total VMDKs: $total" >> "$SUMMARY_FILE"
echo "Healthy: $healthy" >> "$SUMMARY_FILE"
echo "Warnings: $warnings" >> "$SUMMARY_FILE"
echo "Errors: $errors" >> "$SUMMARY_FILE"

echo ""
echo "Inspection complete!"
echo "Summary: $SUMMARY_FILE"
echo "Details: $OUTPUT_DIR"
```

**Usage**:
```bash
chmod +x scripts/bulk-vmdk-inspect.sh
./scripts/bulk-vmdk-inspect.sh /vmware/vms ./inspection-reports
```

---

### 2. Migration Config Generator

Generate migration YAML configs from a CSV inventory.

**File**: `scripts/generate-migration-configs.py`

```python
#!/usr/bin/env python3
"""
Generate migration configs from CSV inventory
Usage: ./generate-migration-configs.py inventory.csv output-dir/
"""

import csv
import sys
import os
from pathlib import Path

def generate_config(vm_data, output_dir):
    """Generate YAML config for a VM"""

    config = f"""# Migration config for {vm_data['name']}
# Generated: {vm_data.get('generated', 'auto')}

command: local
vmdk: {vm_data['vmdk_path']}
output_dir: {vm_data['output_dir']}
to_output: {vm_data['name']}.qcow2

"""

    # OS-specific options
    if vm_data['os_type'].lower() == 'linux':
        config += """# Linux VM options
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled

"""
    elif vm_data['os_type'].lower() == 'windows':
        config += f"""# Windows VM options
inject_virtio_drivers: true
windows_version: {vm_data.get('windows_version', '2019')}

"""

    # Performance options
    if vm_data.get('workload_type') == 'database':
        config += """# Database optimizations
out_format: raw
compress: false

"""
    else:
        config += """# Standard options
out_format: qcow2
compress: true

"""

    # Special handling
    if vm_data.get('is_cloned', 'false').lower() == 'true':
        config += """# Cloned VM fix
xfs_regenerate_uuid: true

"""

    # Validation
    config += f"""# Validation
libvirt_test: {vm_data.get('libvirt_test', 'true')}

# Logging
log_level: INFO
log_file: /var/log/hyper2kvm/{vm_data['name']}.log
"""

    # Write config file
    output_path = Path(output_dir) / f"{vm_data['name']}.yaml"
    output_path.write_text(config)
    print(f"✅ Generated: {output_path}")

def main():
    if len(sys.argv) != 3:
        print("Usage: ./generate-migration-configs.py inventory.csv output-dir/")
        sys.exit(1)

    csv_file = sys.argv[1]
    output_dir = sys.argv[2]

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Read CSV and generate configs
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            generate_config(row, output_dir)
            count += 1

    print(f"\n✅ Generated {count} migration configs in {output_dir}")

if __name__ == '__main__':
    main()
```

**Example CSV** (`inventory.csv`):
```csv
name,vmdk_path,output_dir,os_type,workload_type,windows_version,is_cloned,libvirt_test
web-01,/vmware/web-01.vmdk,/kvm/vms,linux,web,,false,true
web-02,/vmware/web-02.vmdk,/kvm/vms,linux,web,,false,true
db-01,/vmware/db-01.vmdk,/kvm/databases,linux,database,,false,false
win-srv,/vmware/win-srv.vmdk,/kvm/windows,windows,app,2019,false,true
```

**Usage**:
```bash
chmod +x scripts/generate-migration-configs.py
./generate-migration-configs.py inventory.csv ./migration-configs/
```

---

### 3. Storage Space Calculator

Calculate required storage space for migrations.

**File**: `scripts/calculate-storage.sh`

```bash
#!/bin/bash
# Calculate storage requirements for VM migrations
# Usage: ./calculate-storage.sh /path/to/vmdks

set -euo pipefail

VMDK_DIR="${1:?Usage: $0 <vmdk-directory>}"

echo "=== Storage Space Calculator ==="
echo ""

total_source_size=0
total_raw_size=0
total_qcow2_size=0
total_compressed_size=0

for vmdk in "$VMDK_DIR"/*.vmdk; do
    [ -f "$vmdk" ] || continue

    vm_name=$(basename "$vmdk" .vmdk)
    source_size=$(du -b "$vmdk" | cut -f1)

    # Get actual disk size from qemu-img
    if info=$(qemu-img info "$vmdk" 2>/dev/null); then
        virtual_size=$(echo "$info" | grep "virtual size" | awk '{print $3}')

        # Estimates:
        # - Raw: ~100% of virtual size
        # - QCOW2 uncompressed: ~70% of virtual size (average)
        # - QCOW2 compressed: ~40% of virtual size (average)

        virtual_bytes=$(echo "$virtual_size" | numfmt --from=iec)

        raw_estimate=$virtual_bytes
        qcow2_estimate=$((virtual_bytes * 70 / 100))
        compressed_estimate=$((virtual_bytes * 40 / 100))

        total_source_size=$((total_source_size + source_size))
        total_raw_size=$((total_raw_size + raw_estimate))
        total_qcow2_size=$((total_qcow2_size + qcow2_estimate))
        total_compressed_size=$((total_compressed_size + compressed_estimate))

        echo "VM: $vm_name"
        echo "  Source (VMDK): $(numfmt --to=iec $source_size)"
        echo "  Raw estimate: $(numfmt --to=iec $raw_estimate)"
        echo "  QCOW2 estimate: $(numfmt --to=iec $qcow2_estimate)"
        echo "  Compressed estimate: $(numfmt --to=iec $compressed_estimate)"
        echo ""
    fi
done

echo "=== Total Requirements ==="
echo "Source VMDKs: $(numfmt --to=iec $total_source_size)"
echo "Raw format: $(numfmt --to=iec $total_raw_size)"
echo "QCOW2 format: $(numfmt --to=iec $total_qcow2_size)"
echo "QCOW2 compressed: $(numfmt --to=iec $total_compressed_size)"
echo ""
echo "Recommended free space: $(numfmt --to=iec $((total_qcow2_size * 150 / 100)))"
echo "(1.5x estimated size for safety margin)"
```

**Usage**:
```bash
chmod +x scripts/calculate-storage.sh
./scripts/calculate-storage.sh /vmware/vms
```

---

## Migration Execution Scripts

### 4. Parallel Batch Migration

Execute migrations in parallel with progress tracking.

**File**: `scripts/parallel-migrate.sh`

```bash
#!/bin/bash
# Parallel migration executor with progress tracking
# Usage: ./parallel-migrate.sh config-dir/ 4

set -euo pipefail

CONFIG_DIR="${1:?Usage: $0 <config-directory> <parallel-count>}"
PARALLEL="${2:-4}"
LOG_DIR="./migration-logs"
STATUS_FILE="./migration-status.txt"

mkdir -p "$LOG_DIR"

# Initialize status file
echo "=== Migration Status ===" > "$STATUS_FILE"
echo "Started: $(date)" >> "$STATUS_FILE"
echo "" >> "$STATUS_FILE"

# Count total configs
total=$(find "$CONFIG_DIR" -name "*.yaml" | wc -l)
echo "Total VMs to migrate: $total"
echo "Parallel migrations: $PARALLEL"
echo ""

# Function to run single migration
migrate_vm() {
    local config=$1
    local vm_name=$(basename "$config" .yaml)
    local log_file="$LOG_DIR/${vm_name}.log"

    echo "⏳ Starting: $vm_name" | tee -a "$STATUS_FILE"

    if h2kvmctl --config "$config" > "$log_file" 2>&1; then
        echo "✅ Success: $vm_name" | tee -a "$STATUS_FILE"
        return 0
    else
        echo "❌ Failed: $vm_name" | tee -a "$STATUS_FILE"
        return 1
    fi
}

export -f migrate_vm
export LOG_DIR STATUS_FILE

# Run migrations in parallel
find "$CONFIG_DIR" -name "*.yaml" | \
    parallel -j "$PARALLEL" --bar migrate_vm {}

# Generate summary
echo "" >> "$STATUS_FILE"
echo "=== Summary ===" >> "$STATUS_FILE"
echo "Completed: $(date)" >> "$STATUS_FILE"

success=$(grep -c "✅ Success" "$STATUS_FILE" || true)
failed=$(grep -c "❌ Failed" "$STATUS_FILE" || true)

echo "Success: $success" >> "$STATUS_FILE"
echo "Failed: $failed" >> "$STATUS_FILE"

cat "$STATUS_FILE"

if [ $failed -gt 0 ]; then
    echo ""
    echo "⚠️  Some migrations failed. Check logs in $LOG_DIR"
    exit 1
fi
```

**Usage**:
```bash
# Requires GNU parallel
sudo apt-get install parallel  # or: sudo yum install parallel

chmod +x scripts/parallel-migrate.sh
./scripts/parallel-migrate.sh ./migration-configs/ 4
```

---

### 5. Migration Progress Monitor

Monitor migration progress in real-time.

**File**: `scripts/monitor-migration.sh`

```bash
#!/bin/bash
# Real-time migration progress monitor
# Usage: ./monitor-migration.sh

watch -n 2 '
echo "=== Hyper2KVM Migration Monitor ==="
echo ""
echo "Running Migrations:"
ps aux | grep -E "h2kvmctl|hyper2kvm" | grep -v grep || echo "  None"
echo ""
echo "System Resources:"
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk "{print \$2}" | cut -d"%" -f1)%"
echo "Memory: $(free -h | grep Mem | awk "{print \$3\"/\"\$2}")"
echo "Disk I/O:"
iostat -x 1 2 | tail -n +4 | head -n 5
echo ""
echo "Recent Log Activity:"
tail -n 10 /var/log/hyper2kvm/*.log 2>/dev/null | tail -n 5 || echo "  No logs found"
'
```

---

## Post-Migration Scripts

### 6. Batch VM Validator

Validate multiple migrated VMs.

**File**: `scripts/batch-validate.sh`

```bash
#!/bin/bash
# Batch VM validation script
# Usage: ./batch-validate.sh /kvm/vms

set -euo pipefail

VM_DIR="${1:?Usage: $0 <vm-directory>}"
VALIDATION_REPORT="./validation-report-$(date +%Y%m%d-%H%M%S).txt"

echo "=== VM Validation Report ===" > "$VALIDATION_REPORT"
echo "Date: $(date)" >> "$VALIDATION_REPORT"
echo "" >> "$VALIDATION_REPORT"

total=0
passed=0
failed=0

for qcow2 in "$VM_DIR"/*.qcow2; do
    [ -f "$qcow2" ] || continue

    vm_name=$(basename "$qcow2" .qcow2)
    total=$((total + 1))

    echo "Validating: $vm_name"
    echo "--- $vm_name ---" >> "$VALIDATION_REPORT"

    # Test 1: File integrity
    if qemu-img check "$qcow2" >> "$VALIDATION_REPORT" 2>&1; then
        echo "  ✅ File integrity OK"
        echo "  ✅ Integrity: PASS" >> "$VALIDATION_REPORT"
    else
        echo "  ❌ File integrity FAILED"
        echo "  ❌ Integrity: FAIL" >> "$VALIDATION_REPORT"
        failed=$((failed + 1))
        continue
    fi

    # Test 2: Check if VM can be defined
    xml_file="${VM_DIR}/${vm_name}.xml"
    if [ -f "$xml_file" ]; then
        if virsh define "$xml_file" >> "$VALIDATION_REPORT" 2>&1; then
            echo "  ✅ Libvirt define OK"
            echo "  ✅ Libvirt define: PASS" >> "$VALIDATION_REPORT"

            # Test 3: Try to start VM
            if virsh start "$vm_name" >> "$VALIDATION_REPORT" 2>&1; then
                echo "  ✅ VM start OK"
                echo "  ✅ VM start: PASS" >> "$VALIDATION_REPORT"

                # Wait for boot
                sleep 30

                # Test 4: Check if running
                if [ "$(virsh domstate $vm_name)" = "running" ]; then
                    echo "  ✅ VM running"
                    echo "  ✅ VM status: PASS" >> "$VALIDATION_REPORT"
                    passed=$((passed + 1))
                else
                    echo "  ❌ VM not running"
                    echo "  ❌ VM status: FAIL" >> "$VALIDATION_REPORT"
                    failed=$((failed + 1))
                fi

                # Shutdown for next test
                virsh shutdown "$vm_name" >> "$VALIDATION_REPORT" 2>&1
            else
                echo "  ❌ VM start FAILED"
                echo "  ❌ VM start: FAIL" >> "$VALIDATION_REPORT"
                failed=$((failed + 1))
            fi

            # Cleanup
            virsh undefine "$vm_name" >> "$VALIDATION_REPORT" 2>&1
        fi
    else
        echo "  ⚠️  No XML file found"
        echo "  ⚠️  Libvirt XML: MISSING" >> "$VALIDATION_REPORT"
    fi

    echo "" >> "$VALIDATION_REPORT"
done

echo "" >> "$VALIDATION_REPORT"
echo "=== Summary ===" >> "$VALIDATION_REPORT"
echo "Total VMs: $total" >> "$VALIDATION_REPORT"
echo "Passed: $passed" >> "$VALIDATION_REPORT"
echo "Failed: $failed" >> "$VALIDATION_REPORT"
echo "Success Rate: $((passed * 100 / total))%" >> "$VALIDATION_REPORT"

echo ""
echo "Validation complete!"
echo "Report: $VALIDATION_REPORT"

cat "$VALIDATION_REPORT"
```

---

### 7. Network Configuration Validator

Verify network connectivity for migrated VMs.

**File**: `scripts/validate-network.sh`

```bash
#!/bin/bash
# Network validation for migrated VMs
# Usage: ./validate-network.sh vm-name

set -euo pipefail

VM_NAME="${1:?Usage: $0 <vm-name>}"

echo "=== Network Validation for $VM_NAME ==="
echo ""

# Check if VM is running
if [ "$(virsh domstate $VM_NAME)" != "running" ]; then
    echo "❌ VM is not running"
    exit 1
fi

echo "✅ VM is running"

# Get IP address
IP=$(virsh domifaddr "$VM_NAME" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)

if [ -z "$IP" ]; then
    echo "❌ Could not determine IP address"
    exit 1
fi

echo "✅ IP address: $IP"

# Test connectivity
echo ""
echo "Testing connectivity..."
if ping -c 4 "$IP" > /dev/null 2>&1; then
    echo "✅ Ping successful"
else
    echo "❌ Ping failed"
    exit 1
fi

# Test SSH (if port 22 is open)
echo ""
echo "Testing SSH..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$IP/22" 2>/dev/null; then
    echo "✅ SSH port is open"
else
    echo "⚠️  SSH port is not accessible"
fi

# Test HTTP (if port 80 is open)
echo ""
echo "Testing HTTP..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$IP/80" 2>/dev/null; then
    echo "✅ HTTP port is open"
else
    echo "⚠️  HTTP port is not accessible"
fi

echo ""
echo "=== Network validation complete ==="
```

---

## Monitoring Scripts

### 8. VM Health Monitor

Continuous health monitoring for migrated VMs.

**File**: `scripts/health-monitor.sh`

```bash
#!/bin/bash
# VM health monitoring script
# Usage: ./health-monitor.sh vm-name [interval-seconds]

set -euo pipefail

VM_NAME="${1:?Usage: $0 <vm-name> [interval]}"
INTERVAL="${2:-60}"
LOG_FILE="./health-${VM_NAME}-$(date +%Y%m%d).log"

echo "Starting health monitor for $VM_NAME (interval: ${INTERVAL}s)"
echo "Logging to: $LOG_FILE"

while true; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Check VM state
    state=$(virsh domstate "$VM_NAME" 2>/dev/null || echo "unknown")

    # Get resource usage
    if [ "$state" = "running" ]; then
        cpu=$(virsh domstats "$VM_NAME" | grep "cpu.time" | awk '{print $2}')
        mem=$(virsh domstats "$VM_NAME" | grep "balloon.current" | awk '{print $2}')

        # Check network connectivity
        ip=$(virsh domifaddr "$VM_NAME" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)
        if [ -n "$ip" ]; then
            if ping -c 1 -W 2 "$ip" > /dev/null 2>&1; then
                network="OK"
            else
                network="FAIL"
            fi
        else
            network="NO_IP"
        fi

        echo "$timestamp | State: $state | CPU: $cpu | Mem: $mem | Network: $network" | tee -a "$LOG_FILE"
    else
        echo "$timestamp | State: $state | VM not running" | tee -a "$LOG_FILE"
    fi

    sleep "$INTERVAL"
done
```

---

## Utility Scripts

### 9. Cleanup Old Migrations

Clean up old migration files and logs.

**File**: `scripts/cleanup-old.sh`

```bash
#!/bin/bash
# Cleanup old migration artifacts
# Usage: ./cleanup-old.sh [days-to-keep]

set -euo pipefail

DAYS="${1:-30}"

echo "=== Cleanup Old Migration Artifacts ==="
echo "Removing files older than $DAYS days"
echo ""

# Clean old logs
if [ -d "/var/log/hyper2kvm" ]; then
    echo "Cleaning logs..."
    find /var/log/hyper2kvm -name "*.log" -type f -mtime +$DAYS -delete
    echo "✅ Logs cleaned"
fi

# Clean old inspection reports
if [ -d "./inspection-reports" ]; then
    echo "Cleaning inspection reports..."
    find ./inspection-reports -name "*.txt" -type f -mtime +$DAYS -delete
    echo "✅ Reports cleaned"
fi

# Clean old status files
echo "Cleaning status files..."
find . -maxdepth 1 -name "migration-status-*.txt" -type f -mtime +$DAYS -delete
find . -maxdepth 1 -name "validation-report-*.txt" -type f -mtime +$DAYS -delete
echo "✅ Status files cleaned"

echo ""
echo "Cleanup complete!"
```

---

### 10. Migration Statistics Generator

Generate statistics from completed migrations.

**File**: `scripts/generate-stats.py`

```python
#!/usr/bin/env python3
"""
Generate migration statistics from logs
Usage: ./generate-stats.py /var/log/hyper2kvm
"""

import sys
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def parse_log(log_file):
    """Extract migration info from log file"""
    data = {
        'vm_name': log_file.stem,
        'success': False,
        'duration': None,
        'size': None,
        'errors': []
    }

    content = log_file.read_text()

    # Check success
    if 'Migration completed successfully' in content:
        data['success'] = True

    # Extract duration (if logged)
    duration_match = re.search(r'Duration: ([\d.]+)', content)
    if duration_match:
        data['duration'] = float(duration_match.group(1))

    # Extract size
    size_match = re.search(r'Size: ([\d.]+)([A-Z]+)', content)
    if size_match:
        data['size'] = f"{size_match.group(1)} {size_match.group(2)}"

    # Extract errors
    for line in content.split('\n'):
        if 'ERROR' in line:
            data['errors'].append(line.strip())

    return data

def main():
    if len(sys.argv) != 2:
        print("Usage: ./generate-stats.py /var/log/hyper2kvm")
        sys.exit(1)

    log_dir = Path(sys.argv[1])

    if not log_dir.exists():
        print(f"Error: {log_dir} does not exist")
        sys.exit(1)

    # Parse all logs
    migrations = []
    for log_file in log_dir.glob('*.log'):
        migrations.append(parse_log(log_file))

    # Generate statistics
    total = len(migrations)
    successful = sum(1 for m in migrations if m['success'])
    failed = total - successful

    print("=== Migration Statistics ===")
    print(f"Total migrations: {total}")
    print(f"Successful: {successful} ({successful*100//total if total > 0 else 0}%)")
    print(f"Failed: {failed} ({failed*100//total if total > 0 else 0}%)")
    print()

    # Duration statistics
    durations = [m['duration'] for m in migrations if m['duration']]
    if durations:
        print("Duration Statistics:")
        print(f"  Average: {sum(durations)/len(durations):.1f} seconds")
        print(f"  Min: {min(durations):.1f} seconds")
        print(f"  Max: {max(durations):.1f} seconds")
        print()

    # Common errors
    all_errors = defaultdict(int)
    for m in migrations:
        for error in m['errors']:
            # Extract error type
            error_type = error.split(':')[0] if ':' in error else error[:50]
            all_errors[error_type] += 1

    if all_errors:
        print("Most Common Errors:")
        for error, count in sorted(all_errors.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {count}x: {error}")

if __name__ == '__main__':
    main()
```

**Usage**:
```bash
chmod +x scripts/generate-stats.py
./scripts/generate-stats.py /var/log/hyper2kvm
```

---

## Installation

1. **Create scripts directory**:
```bash
mkdir -p scripts
cd scripts
```

2. **Download all scripts**:
```bash
# Clone repository
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm/scripts

# Or download individually
curl -O https://raw.githubusercontent.com/ssahani/hyper2kvm/main/scripts/bulk-vmdk-inspect.sh
# ... etc
```

3. **Make executable**:
```bash
chmod +x scripts/*.sh scripts/*.py
```

4. **Install dependencies**:
```bash
# For parallel migrations
sudo apt-get install parallel

# For Python scripts
pip3 install pyyaml
```

---

## Quick Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| bulk-vmdk-inspect.sh | Inspect multiple VMDKs | `./bulk-vmdk-inspect.sh /vmware/vms` |
| generate-migration-configs.py | Generate configs from CSV | `./generate-migration-configs.py inventory.csv ./configs/` |
| calculate-storage.sh | Calculate storage needs | `./calculate-storage.sh /vmware/vms` |
| parallel-migrate.sh | Parallel migrations | `./parallel-migrate.sh ./configs/ 4` |
| monitor-migration.sh | Real-time monitoring | `./monitor-migration.sh` |
| batch-validate.sh | Validate multiple VMs | `./batch-validate.sh /kvm/vms` |
| validate-network.sh | Test VM network | `./validate-network.sh vm-name` |
| health-monitor.sh | Continuous health check | `./health-monitor.sh vm-name 60` |
| cleanup-old.sh | Clean old artifacts | `./cleanup-old.sh 30` |
| generate-stats.py | Migration statistics | `./generate-stats.py /var/log/hyper2kvm` |

---

## Complete Workflow Example

```bash
# 1. Inspect source VMs
./scripts/bulk-vmdk-inspect.sh /vmware/vms ./reports

# 2. Calculate storage requirements
./scripts/calculate-storage.sh /vmware/vms

# 3. Generate migration configs from inventory
./scripts/generate-migration-configs.py inventory.csv ./configs

# 4. Run migrations in parallel with monitoring
./scripts/parallel-migrate.sh ./configs 4 &
./scripts/monitor-migration.sh

# 5. Validate migrated VMs
./scripts/batch-validate.sh /kvm/vms

# 6. Test network connectivity
for vm in web-01 web-02 db-01; do
    ./scripts/validate-network.sh $vm
done

# 7. Start health monitoring
./scripts/health-monitor.sh production-db 60 &

# 8. Generate statistics
./scripts/generate-stats.py /var/log/hyper2kvm

# 9. Cleanup old files
./scripts/cleanup-old.sh 30
```

---

## Best Practices

**✅ DO**:
- Test scripts on non-production VMs first
- Review generated configs before using
- Monitor resource usage during batch operations
- Keep logs for troubleshooting
- Run validations after every migration

**❌ DON'T**:
- Run untested scripts on production
- Set parallel count too high
- Delete logs immediately
- Skip validation steps
- Ignore script warnings

---

## Troubleshooting

### Script Permission Denied
```bash
chmod +x scripts/*.sh scripts/*.py
```

### Python Module Not Found
```bash
pip3 install --user pyyaml
```

### Parallel Command Not Found
```bash
# Ubuntu/Debian
sudo apt-get install parallel

# RHEL/CentOS
sudo yum install parallel
```

### Out of Memory During Batch
- Reduce parallel count
- Add swap space
- Process in smaller batches

---

## Additional Resources

- [Best Practices](BEST_PRACTICES.md) - Migration best practices
- [Examples Library](EXAMPLES_LIBRARY.md) - Configuration examples
- [Migration Checklist](MIGRATION_CHECKLIST.md) - Step-by-step checklist
- [Troubleshooting](TROUBLESHOOTING_FLOWCHART.md) - Problem solving

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
**Scripts Version**: 1.0.0
