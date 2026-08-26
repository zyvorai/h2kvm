# Monitoring & Observability Guide

Comprehensive guide for monitoring migrated VMs and ensuring operational excellence.

---

## Quick Links

- [Monitoring Strategy](#monitoring-strategy)
- [Pre-Production Monitoring](#pre-production-monitoring)
- [Production Monitoring](#production-monitoring)
- [Performance Metrics](#performance-metrics)
- [Alerting](#alerting-best-practices)
- [Troubleshooting with Monitoring](#troubleshooting-with-monitoring)
- [Tools & Integration](#monitoring-tools--integration)

---

## Overview

Effective monitoring ensures:
- **Early problem detection** before users are impacted
- **Performance validation** after migration
- **Capacity planning** data
- **Compliance** with SLAs
- **Operational insights** for optimization

---

## Monitoring Strategy

### Three-Phase Approach

```
Phase 1: Migration (Real-time)
├── Track migration progress
├── Monitor resource usage
└── Detect failures immediately

Phase 2: Post-Migration (Intensive - 7 days)
├── Validate performance vs baseline
├── Monitor for regressions
├── Track stability metrics
└── Identify optimization opportunities

Phase 3: Steady State (Ongoing)
├── Standard monitoring
├── Trend analysis
└── Capacity planning
```

---

## Pre-Production Monitoring

### Migration Progress Tracking

Monitor active migrations in real-time.

**Script**: `monitor-active-migrations.sh`

```bash
#!/bin/bash
# Monitor active migrations

echo "=== Active Migration Monitor ==="
date

# Check running processes
echo ""
echo "Running Migrations:"
ps aux | grep -E "h2kvmctl|hyper2kvm" | grep -v grep | awk '{print $11, $12, $13}'

# System resources
echo ""
echo "System Resources:"
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')% used"
echo "Memory: $(free -h | grep Mem | awk '{print $3 " / " $2}')"
echo "Load: $(uptime | awk -F'load average:' '{print $2}')"

# Disk I/O
echo ""
echo "Disk I/O (top 3):"
iostat -x 1 2 | tail -n +4 | head -n 3

# Recent logs
echo ""
echo "Recent Activity:"
tail -n 5 /var/log/hyper2kvm/*.log 2>/dev/null | grep -E "INFO|ERROR|WARNING" | tail -3
```

**Dashboard**: Set up continuous monitoring

```bash
watch -n 5 './monitor-active-migrations.sh'
```

---

### Disk Space Monitoring

Critical during migrations to prevent failures.

**Script**: `check-disk-space.sh`

```bash
#!/bin/bash
# Disk space monitoring

THRESHOLD=80  # Percentage

echo "=== Disk Space Monitor ==="

df -h | grep -vE '^Filesystem|tmpfs|cdrom' | awk '{print $5 " " $6}' | while read output; do
    usage=$(echo $output | awk '{print $1}' | sed 's/%//')
    partition=$(echo $output | awk '{print $2}')

    if [ $usage -ge $THRESHOLD ]; then
        echo "❌ CRITICAL: $partition is ${usage}% full"
    elif [ $usage -ge 70 ]; then
        echo "⚠️  WARNING: $partition is ${usage}% full"
    else
        echo "✅ OK: $partition is ${usage}% full"
    fi
done
```

---

## Production Monitoring

### VM Health Checks

Continuous validation of migrated VMs.

**Script**: `vm-health-check.sh`

```bash
#!/bin/bash
# VM health check script

VM_NAME=$1

check_vm_health() {
    local vm=$1
    local status="OK"
    local issues=()

    # Check 1: VM State
    state=$(virsh domstate "$vm" 2>/dev/null)
    if [ "$state" != "running" ]; then
        status="CRITICAL"
        issues+=("VM not running (state: $state)")
    fi

    # Check 2: CPU Usage
    cpu_time=$(virsh cpu-stats "$vm" --total 2>/dev/null | grep "cpu_time" | awk '{print $2}')

    # Check 3: Memory
    mem_stats=$(virsh dommemstat "$vm" 2>/dev/null)
    if [ $? -ne 0 ]; then
        status="WARNING"
        issues+=("Cannot retrieve memory stats")
    fi

    # Check 4: Network
    ip=$(virsh domifaddr "$vm" 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)
    if [ -n "$ip" ]; then
        if ! ping -c 1 -W 2 "$ip" > /dev/null 2>&1; then
            status="WARNING"
            issues+=("Network unreachable")
        fi
    else
        status="WARNING"
        issues+=("No IP address")
    fi

    # Check 5: Disk I/O
    disk_stats=$(virsh domblkstat "$vm" vda 2>/dev/null)
    if [ $? -ne 0 ]; then
        status="WARNING"
        issues+=("Cannot retrieve disk stats")
    fi

    # Report
    echo "VM: $vm - Status: $status"
    if [ ${#issues[@]} -gt 0 ]; then
        for issue in "${issues[@]}"; do
            echo "  - $issue"
        done
    fi

    # Return status code
    if [ "$status" = "CRITICAL" ]; then
        return 2
    elif [ "$status" = "WARNING" ]; then
        return 1
    else
        return 0
    fi
}

if [ -z "$VM_NAME" ]; then
    # Check all VMs
    for vm in $(virsh list --name); do
        [ -z "$vm" ] && continue
        check_vm_health "$vm"
    done
else
    # Check specific VM
    check_vm_health "$VM_NAME"
fi
```

**Usage**:
```bash
# Check all VMs
./vm-health-check.sh

# Check specific VM
./vm-health-check.sh web-server-01

# Continuous monitoring
watch -n 30 './vm-health-check.sh'
```

---

### Performance Baseline Comparison

Compare post-migration performance to baseline.

**Collect Baseline** (before migration):
```bash
#!/bin/bash
# collect-baseline.sh - Run on source VM

VM_NAME=$1
BASELINE_FILE="baseline-${VM_NAME}.txt"

echo "=== Performance Baseline for $VM_NAME ===" > "$BASELINE_FILE"
echo "Collected: $(date)" >> "$BASELINE_FILE"
echo "" >> "$BASELINE_FILE"

# CPU
echo "CPU:" >> "$BASELINE_FILE"
mpstat 1 10 | tail -1 >> "$BASELINE_FILE"

# Memory
echo "" >> "$BASELINE_FILE"
echo "Memory:" >> "$BASELINE_FILE"
free -h >> "$BASELINE_FILE"

# Disk I/O
echo "" >> "$BASELINE_FILE"
echo "Disk I/O:" >> "$BASELINE_FILE"
iostat -x 1 10 | tail -n +4 >> "$BASELINE_FILE"

# Network
echo "" >> "$BASELINE_FILE"
echo "Network:" >> "$BASELINE_FILE"
sar -n DEV 1 10 | grep -v "^$" | tail -5 >> "$BASELINE_FILE"

echo "Baseline collected: $BASELINE_FILE"
```

**Compare Performance** (after migration):
```bash
#!/bin/bash
# compare-performance.sh

VM_NAME=$1
BASELINE_FILE="baseline-${VM_NAME}.txt"
CURRENT_FILE="current-${VM_NAME}.txt"

# Collect current metrics (same as baseline)
# ... (same collection commands)

# Compare
echo "=== Performance Comparison ==="
echo "Baseline vs Current for $VM_NAME"
echo ""

# Show side-by-side comparison
echo "CPU Idle %:"
echo "  Baseline: $(grep "all" "$BASELINE_FILE" | awk '{print $NF}')"
echo "  Current:  $(grep "all" "$CURRENT_FILE" | awk '{print $NF}')"

# Memory comparison
# Disk I/O comparison
# Network comparison
# ...
```

---

## Performance Metrics

### Key Metrics to Track

#### 1. CPU Metrics

```bash
# CPU utilization per VM
virsh cpu-stats VM_NAME --total

# Host CPU usage
mpstat 1 5

# Per-vCPU stats
virsh vcpuinfo VM_NAME
```

**Thresholds**:
- Normal: < 70%
- Warning: 70-85%
- Critical: > 85%

---

#### 2. Memory Metrics

```bash
# VM memory stats
virsh dommemstat VM_NAME

# Memory balloon
virsh dommeminfo VM_NAME

# Host memory
free -h
```

**Key Metrics**:
- `actual`: Current memory usage
- `available`: Available memory
- `unused`: Memory not in use
- `swap_in/swap_out`: Swapping activity (should be 0)

**Thresholds**:
- Normal: < 80%
- Warning: 80-90%
- Critical: > 90%

---

#### 3. Disk I/O Metrics

```bash
# VM disk stats
virsh domblkstat VM_NAME vda

# Detailed disk I/O
virsh domblklist VM_NAME
for disk in $(virsh domblklist VM_NAME | grep -v "^Target" | awk '{print $1}'); do
    echo "Disk: $disk"
    virsh domblkstat VM_NAME $disk
done

# Host disk I/O
iostat -x 1 5
```

**Key Metrics**:
- `rd_req`: Read requests
- `rd_bytes`: Bytes read
- `wr_req`: Write requests
- `wr_bytes`: Bytes written

**Thresholds** (IOPS):
- SSD: > 10,000 good, < 5,000 investigate
- HDD: > 200 good, < 100 investigate

---

#### 4. Network Metrics

```bash
# VM network stats
virsh domifstat VM_NAME vnet0

# All interfaces
for iface in $(virsh domiflist VM_NAME | grep -v "^Interface" | awk '{print $1}'); do
    echo "Interface: $iface"
    virsh domifstat VM_NAME $iface
done

# Detailed network info
virsh domifaddr VM_NAME

# Host network
sar -n DEV 1 5
```

**Key Metrics**:
- `rx_bytes`: Received bytes
- `rx_packets`: Received packets
- `rx_drop`: Dropped packets (should be 0)
- `tx_bytes`: Transmitted bytes
- `tx_packets`: Transmitted packets
- `tx_drop`: Dropped packets (should be 0)

---

### Performance Monitoring Script

Complete performance monitoring solution:

```bash
#!/bin/bash
# performance-monitor.sh - Comprehensive performance tracking

VM_NAME=$1
INTERVAL=${2:-60}
LOG_DIR="./perf-logs"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${VM_NAME}-$(date +%Y%m%d).csv"

# Create CSV header
echo "timestamp,cpu_time,mem_actual,mem_available,disk_rd,disk_wr,net_rx,net_tx" > "$LOG_FILE"

echo "Monitoring $VM_NAME (interval: ${INTERVAL}s)"
echo "Logging to: $LOG_FILE"
echo "Press Ctrl+C to stop"

while true; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Collect metrics
    cpu_time=$(virsh cpu-stats "$VM_NAME" --total 2>/dev/null | grep "cpu_time" | awk '{print $2}')
    mem_actual=$(virsh dommemstat "$VM_NAME" 2>/dev/null | grep "actual" | awk '{print $2}')
    mem_available=$(virsh dommemstat "$VM_NAME" 2>/dev/null | grep "available" | awk '{print $2}')

    disk_stats=$(virsh domblkstat "$VM_NAME" vda 2>/dev/null)
    disk_rd=$(echo "$disk_stats" | grep "rd_bytes" | awk '{print $2}')
    disk_wr=$(echo "$disk_stats" | grep "wr_bytes" | awk '{print $2}')

    net_stats=$(virsh domifstat "$VM_NAME" vnet0 2>/dev/null)
    net_rx=$(echo "$net_stats" | grep "rx_bytes" | awk '{print $2}')
    net_tx=$(echo "$net_stats" | grep "tx_bytes" | awk '{print $2}')

    # Log to CSV
    echo "$timestamp,$cpu_time,$mem_actual,$mem_available,$disk_rd,$disk_wr,$net_rx,$net_tx" >> "$LOG_FILE"

    # Display current values
    echo "$timestamp | CPU: $cpu_time | Mem: $mem_actual/$mem_available | Disk: R:$disk_rd W:$disk_wr | Net: RX:$net_rx TX:$net_tx"

    sleep "$INTERVAL"
done
```

**Usage**:
```bash
# Monitor single VM
./performance-monitor.sh web-server-01 60

# Monitor multiple VMs in background
for vm in web-01 web-02 db-01; do
    ./performance-monitor.sh $vm 60 &
done
```

---

## Alerting Best Practices

### Alert Levels

**CRITICAL** (immediate action):
- VM down
- Out of memory
- Disk full
- Network complete failure

**WARNING** (investigate soon):
- High CPU (> 85%)
- High memory (> 90%)
- High disk I/O wait
- Packet drops

**INFO** (track trends):
- Moderate CPU (> 70%)
- Moderate memory (> 80%)
- Performance degradation

---

### Alerting Script

```bash
#!/bin/bash
# alert-handler.sh - Send alerts based on thresholds

VM_NAME=$1
ALERT_EMAIL="ops@example.com"

check_and_alert() {
    local vm=$1
    local metric=$2
    local value=$3
    local threshold=$4
    local level=$5

    if [ "$value" -gt "$threshold" ]; then
        message="[$level] $vm: $metric is $value (threshold: $threshold)"

        echo "$message"

        # Send email
        echo "$message" | mail -s "VM Alert: $vm" "$ALERT_EMAIL"

        # Send to syslog
        logger -t hyper2kvm-alert "$message"

        # Send to monitoring system (example: Prometheus Pushgateway)
        # curl -X POST http://pushgateway:9091/metrics/job/hyper2kvm ...
    fi
}

# Check CPU
cpu_usage=$(virsh cpu-stats "$VM_NAME" --total | grep "cpu_time" | awk '{print $2}')
# Convert to percentage and check
# ...

# Check memory
mem_used=$(virsh dommemstat "$VM_NAME" | grep "actual" | awk '{print $2}')
mem_total=$(virsh dommeminfo "$VM_NAME" | grep "Max memory" | awk '{print $3}')
mem_pct=$((mem_used * 100 / mem_total))

check_and_alert "$VM_NAME" "Memory" "$mem_pct" 90 "WARNING"

# Check disk space (from inside VM)
# Check network connectivity
# ...
```

---

### Integration with Monitoring Systems

#### Prometheus Integration

**Libvirt Exporter**:
```bash
# Install libvirt_exporter
wget https://github.com/prometheus-community/libvirt_exporter/releases/download/v0.1.0/libvirt_exporter
chmod +x libvirt_exporter

# Run exporter
./libvirt_exporter &

# Metrics available at http://localhost:9177/metrics
```

**Prometheus Config** (`prometheus.yml`):
```yaml
scrape_configs:
  - job_name: 'libvirt'
    static_configs:
      - targets: ['localhost:9177']
```

**Example Queries**:
```promql
# CPU usage per VM
libvirt_domain_info_cpu_time_seconds_total

# Memory usage
libvirt_domain_info_memory_usage_bytes

# Disk read/write
rate(libvirt_domain_block_stats_read_bytes_total[5m])
rate(libvirt_domain_block_stats_write_bytes_total[5m])
```

---

#### Grafana Dashboards

**Create Dashboard** for migrated VMs:

```json
{
  "dashboard": {
    "title": "Hyper2KVM Migrated VMs",
    "panels": [
      {
        "title": "CPU Usage",
        "targets": [
          {
            "expr": "rate(libvirt_domain_info_cpu_time_seconds_total[5m])"
          }
        ]
      },
      {
        "title": "Memory Usage",
        "targets": [
          {
            "expr": "libvirt_domain_info_memory_usage_bytes / libvirt_domain_info_maximum_memory_bytes * 100"
          }
        ]
      },
      {
        "title": "Disk I/O",
        "targets": [
          {
            "expr": "rate(libvirt_domain_block_stats_read_bytes_total[5m])"
          },
          {
            "expr": "rate(libvirt_domain_block_stats_write_bytes_total[5m])"
          }
        ]
      },
      {
        "title": "Network Traffic",
        "targets": [
          {
            "expr": "rate(libvirt_domain_interface_stats_receive_bytes_total[5m])"
          },
          {
            "expr": "rate(libvirt_domain_interface_stats_transmit_bytes_total[5m])"
          }
        ]
      }
    ]
  }
}
```

---

## Troubleshooting with Monitoring

### Common Scenarios

#### High CPU After Migration

**Symptoms**: CPU usage consistently > 80%

**Investigation**:
```bash
# Check per-vCPU stats
virsh vcpuinfo VM_NAME

# Check CPU pinning
virsh vcpupin VM_NAME

# Check host CPU allocation
lscpu

# Inside VM: Check processes
virsh console VM_NAME
top
```

**Possible Causes**:
- Insufficient vCPU allocation
- CPU pinning issues
- Runaway processes
- Missing optimizations (virtio drivers)

---

#### Memory Pressure

**Symptoms**: High swap usage, OOM errors

**Investigation**:
```bash
# Check memory stats
virsh dommemstat VM_NAME

# Check balloon status
virsh dommeminfo VM_NAME

# Check host memory
free -h

# Inside VM
virsh console VM_NAME
free -h
vmstat 1 10
```

**Possible Causes**:
- Insufficient memory allocation
- Memory leak in application
- Memory balloon too aggressive

---

#### Poor Disk Performance

**Symptoms**: High I/O wait, slow disk operations

**Investigation**:
```bash
# Check disk stats
virsh domblkinfo VM_NAME vda
virsh domblkstat VM_NAME vda

# Check disk cache mode
virsh dumpxml VM_NAME | grep -A 5 "disk type"

# Check host disk performance
iostat -x 1 10

# Inside VM
virsh console VM_NAME
iostat -x 1 10
```

**Possible Causes**:
- Wrong cache mode (use writeback for performance)
- Slow underlying storage
- Missing virtio drivers
- I/O scheduler issues

---

## Monitoring Tools & Integration

### Recommended Tools

#### 1. **virt-top** (Real-time VM Monitoring)

```bash
# Install
sudo apt-get install virt-top

# Run
virt-top
```

Features:
- Real-time CPU, memory, disk, network stats
- Similar to `top` but for VMs
- Sortable columns

---

#### 2. **virt-manager** (GUI Monitoring)

```bash
# Install
sudo apt-get install virt-manager

# Run
virt-manager
```

Features:
- Graphical interface
- Resource graphs
- Console access
- VM management

---

#### 3. **Prometheus + Grafana** (Production Monitoring)

**Why**: Industry-standard, scalable, flexible

**Setup**:
```bash
# Install Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
cd prometheus-*

# Configure (prometheus.yml)
# Run
./prometheus --config.file=prometheus.yml

# Install Grafana
sudo apt-get install -y grafana

# Start
sudo systemctl start grafana-server

# Access at http://localhost:3000
```

---

#### 4. **Nagios/Icinga** (Traditional Monitoring)

**Libvirt Plugin**:
```bash
# Install check_libvirt plugin
wget https://github.com/vpenso/libvirt-shell-functions/raw/master/check_libvirt
chmod +x check_libvirt

# Check VM state
./check_libvirt -H localhost -v VM_NAME -w state

# Check CPU
./check_libvirt -H localhost -v VM_NAME -w cpu:80 -c cpu:90
```

---

### Log Aggregation

**Centralize logs** for easier troubleshooting:

```bash
# Configure rsyslog to forward logs
echo "*.* @@logserver.example.com:514" >> /etc/rsyslog.conf
sudo systemctl restart rsyslog

# Or use Elastic Stack (ELK)
# Filebeat -> Logstash -> Elasticsearch -> Kibana
```

---

## Monitoring Checklist

### Post-Migration (First 24 Hours)

- [ ] Verify VM is running
- [ ] Check boot time vs baseline
- [ ] Validate CPU metrics
- [ ] Validate memory metrics
- [ ] Validate disk I/O performance
- [ ] Validate network connectivity
- [ ] Check application logs for errors
- [ ] Run performance baseline comparison
- [ ] Test all critical functionality
- [ ] Set up continuous monitoring

### Week 1 (Intensive Monitoring)

- [ ] Monitor performance trends daily
- [ ] Compare against baseline
- [ ] Track any anomalies
- [ ] Adjust resources if needed
- [ ] Collect feedback from users
- [ ] Document any issues
- [ ] Fine-tune monitoring thresholds

### Ongoing (Steady State)

- [ ] Review metrics weekly
- [ ] Check for resource trends
- [ ] Plan capacity based on growth
- [ ] Update baselines quarterly
- [ ] Test alerting mechanisms
- [ ] Review and update runbooks

---

## Additional Resources

- [Best Practices](BEST_PRACTICES.md) - Migration best practices
- [Troubleshooting Flowchart](TROUBLESHOOTING_FLOWCHART.md) - Problem solving
- [Automation Scripts](AUTOMATION_SCRIPTS.md) - Monitoring scripts
- [FAQ](FAQ.md) - Common questions

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
