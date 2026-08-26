# h2kvm Daemon Mode - Advanced Features

This document details the 8 major enhancements to daemon mode for production deployments.

## Enhancement Summary

| # | Feature | Benefit | Config |
|---|---------|---------|--------|
| 1 | **Concurrent Processing** | 3-5x throughput | `max_concurrent_jobs: 3` |
| 2 | **File Completion Detection** | Prevents corruption | `file_stable_timeout: 30` |
| 3 | **Statistics Tracking** | Performance monitoring | Auto-enabled |
| 4 | **Retry Mechanism** | Handles transient failures | `retry_policy: {...}` |
| 5 | **Control API** | Runtime management | Auto-enabled |
| 6 | **Notifications** | Alerting | `notifications: {...}` |
| 7 | **Deduplication** | Prevents reprocessing | `enable_deduplication: true` |
| 8 | **Error Context** | Better troubleshooting | Auto-enabled |

---

## 1. Concurrent Processing

### Overview
Process multiple VMs simultaneously using a thread pool, dramatically increasing throughput.

### Configuration

```yaml
max_concurrent_jobs: 3  # Adjust based on system resources
```

### Benefits
- **3-5x faster** for multiple small/medium VMs
- Better resource utilization (CPU, disk I/O)
- Configurable based on system capacity

### Resource Planning

| System | Recommended Workers | Notes |
|--------|-------------------|-------|
| 4 CPU, 8GB RAM | 2 | Conservative |
| 8 CPU, 16GB RAM | 3-4 | Balanced |
| 16+ CPU, 32GB+ RAM | 4-6 | Aggressive |

### Monitoring

```bash
# Check current queue depth
h2kvmctl.cli.daemon_ctl stats | grep "Queue Depth"

# Monitor CPU usage
top -p $(pgrep -f "h2kvm.*daemon")
```

---

## 2. File Completion Detection

### Overview
Waits for files to be completely written before processing, preventing corruption from incomplete transfers.

### How It Works

1. File appears in watch directory
2. Daemon checks file size every second
3. Waits for size to stabilize (3 consecutive identical size checks)
4. Proceeds with processing only when stable
5. Times out after `file_stable_timeout` seconds

### Configuration

```yaml
file_stable_timeout: 30  # Wait up to 30 seconds for stability
```

### Use Cases

**When to increase timeout:**
- Large files (100GB+) over slow networks
- Network file systems (NFS, CIFS)
- Files being written incrementally

**When to decrease timeout:**
- Fast local disk copies
- Known-fast transfers
- Testing with small files

### Example

```
08:15:01 File still growing: large-vm.vmdk (10GB)
08:15:02 File still growing: large-vm.vmdk (25GB)
08:15:03 File still growing: large-vm.vmdk (50GB)
08:15:04 File stable: large-vm.vmdk (50GB)
08:15:04 📥 New file queued: large-vm.vmdk
```

---

## 3. Statistics Tracking

### Overview
Comprehensive metrics tracking for monitoring, troubleshooting, and capacity planning.

### Metrics Tracked

**Overall:**
- Total processed/failed
- Success rate
- Average processing time
- Uptime

**Per File Type:**
- Count by extension (.vmdk, .ova, etc.)
- Success rate by type
- Average time by type

**Current State:**
- Queue depth
- Active jobs
- Recent completions

### Accessing Statistics

**Method 1: Control CLI**
```bash
h2kvmctl.cli.daemon_ctl stats

# Output:
📊 Daemon Statistics:
  Uptime: 12.5 hours
  Processed: 45
  Failed: 2
  Success Rate: 95.7%
  Avg Processing Time: 125.3s
  Queue Depth: 3

  By File Type:
    vmdk: 30 ok, 1 failed, 96.8% success
    ova: 15 ok, 1 failed, 93.8% success
```

**Method 2: JSON File**
```bash
cat /var/lib/h2kvm/output/.daemon/stats.json
```

**Method 3: Signal (live daemon)**
```bash
# Send SIGUSR1 to print stats to log
kill -USR1 $(pgrep -f "h2kvm.*daemon")

# View in journal
journalctl -u h2kvm -n 50
```

### Automatic Reporting

Stats are automatically:
- Saved every 60 seconds to `stats.json`
- Printed to logs every hour
- Included in final shutdown summary

### Monitoring Integration

```python
# Example: Prometheus exporter
import json
from pathlib import Path

stats = json.load(open('/var/lib/h2kvm/output/.daemon/stats.json'))

print(f"h2kvm_processed_total {stats['total_processed']}")
print(f"h2kvm_failed_total {stats['total_failed']}")
print(f"h2kvm_success_rate {stats['success_rate_percent']}")
print(f"h2kvm_queue_depth {stats['current_queue_depth']}")
```

---

## 4. Retry Mechanism

### Overview
Automatically retries failed conversions with exponential backoff, handling transient failures.

### Configuration

```yaml
retry_policy:
  enabled: true
  max_retries: 3
  retry_delay: 300  # 5 minutes initial delay
  backoff_multiplier: 2.0  # Doubles each retry
```

### Retry Schedule Example

| Attempt | Delay | Time |
|---------|-------|------|
| 1 (initial) | 0s | 10:00:00 |
| 2 | 5 minutes | 10:05:00 |
| 3 | 10 minutes | 10:15:00 |
| 4 | 20 minutes | 10:35:00 |
| Final failure | - | 10:35:00 |

### When Retries Help

**Good candidates for retry:**
- Temporary network issues
- Disk I/O timeouts
- Rate limiting
- Transient guestfs backend errors
- Resource exhaustion (temporary)

**Not suitable for retry:**
- Corrupted disk images
- Unsupported formats
- Permission errors
- Disk full errors

### Monitoring Retries

```bash
# View retry statistics
h2kvmctl.cli.daemon_ctl stats | grep retried

# Check logs for retry attempts
journalctl -u h2kvm | grep -i retry
```

### Retry Behavior

1. First failure → Schedule retry in 5 minutes
2. File stays in `.errors/` directory
3. After delay, file moved back to watch directory
4. Processing attempted again
5. If successful → Moves to `.processed/`
6. If fails again → Next retry scheduled with longer delay
7. After max retries → Permanently moved to `.errors/`

---

## 5. Health Check & Control API

### Overview
Unix socket-based control interface for runtime management without restarting.

### Control Socket Location

```
{output_dir}/.daemon/control.sock
```

Default: `/var/lib/h2kvm/output/.daemon/control.sock`

### Available Commands

| Command | Description | Use Case |
|---------|-------------|----------|
| `status` | Get running/paused state | Health checks |
| `stats` | Get full statistics | Monitoring |
| `pause` | Pause processing | Maintenance window |
| `resume` | Resume processing | After maintenance |
| `drain` | Finish queue and exit | Graceful shutdown |
| `stop` | Stop immediately | Emergency shutdown |

### Using the Control CLI

```bash
# Basic usage
h2kvmctl.cli.daemon_ctl status

# Specify custom output directory
h2kvmctl.cli.daemon_ctl --output-dir /custom/path status

# Get JSON output
h2kvmctl.cli.daemon_ctl stats --json

# Full path to socket (if non-standard)
h2kvmctl.cli.daemon_ctl --socket /path/to/control.sock status
```

### Examples

**Pause for Maintenance:**
```bash
# Pause processing
h2kvmctl.cli.daemon_ctl pause
# ✅ Daemon paused

# Perform maintenance...
# ...

# Resume
h2kvmctl.cli.daemon_ctl resume
# ✅ Daemon resumed
```

**Graceful Drain:**
```bash
# Drain queue and exit when empty
h2kvmctl.cli.daemon_ctl drain
# ✅ Draining queue

# Daemon will:
# 1. Stop accepting new files
# 2. Finish processing queued files
# 3. Exit cleanly
```

**Emergency Stop:**
```bash
h2kvmctl.cli.daemon_ctl stop
# ✅ Stopping daemon
```

### Integration with Monitoring

```bash
#!/bin/bash
# Health check script for monitoring systems

SOCKET="/var/lib/h2kvm/output/.daemon/control.sock"

if [ ! -S "$SOCKET" ]; then
    echo "CRITICAL: Daemon not running"
    exit 2
fi

STATS=$(h2kvmctl.cli.daemon_ctl stats --json)
QUEUE=$(echo "$STATS" | jq -r '.stats.current_queue_depth')

if [ "$QUEUE" -gt 10 ]; then
    echo "WARNING: Queue depth is $QUEUE"
    exit 1
fi

echo "OK: Daemon healthy, queue depth $QUEUE"
exit 0
```

---

## 6. Notifications

### Overview
Send alerts via webhooks or email for failures, stalls, and optionally successes.

### Configuration

```yaml
notifications:
  enabled: true

  # When to notify
  on_success: false  # Usually too noisy
  on_failure: true   # Alert on failures
  on_stalled: true   # Alert if idle >60min with items in queue

  # Webhook (Slack/Discord/Generic)
  webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  webhook_type: "slack"  # slack, discord, or generic

  # Email (optional)
  email_enabled: false
  email_smtp_host: "smtp.gmail.com"
  email_smtp_port: 587
  email_from: "h2kvm@example.com"
  email_to: "admin@example.com"
  email_username: "h2kvm@example.com"
  email_password: "app-specific-password"
```

### Webhook Types

**Slack:**
```yaml
webhook_type: "slack"
webhook_url: "https://hooks.slack.com/services/T00/B00/XXX"
```

**Discord:**
```yaml
webhook_type: "discord"
webhook_url: "https://discord.com/api/webhooks/123/abc"
```

**Generic (any HTTP endpoint):**
```yaml
webhook_type: "generic"
webhook_url: "https://your-monitoring.com/webhooks/h2kvm"
```

### Notification Events

**Success (if enabled):**
```json
{
  "event": "conversion_success",
  "filename": "vm1.vmdk",
  "duration_seconds": 125.3,
  "output_path": "/var/lib/h2kvm/output/2026-01-17/vm1",
  "timestamp": "2026-01-17T10:30:00Z"
}
```

**Failure:**
```json
{
  "event": "conversion_failure",
  "filename": "vm2.ova",
  "error": "Disk image corrupted",
  "retry_count": 2,
  "timestamp": "2026-01-17T11:00:00Z"
}
```

**Stalled:**
```json
{
  "event": "daemon_stalled",
  "queue_depth": 5,
  "idle_minutes": 75,
  "last_activity": "2026-01-17T09:45:00Z",
  "timestamp": "2026-01-17T11:00:00Z"
}
```

### Email Notifications

**Gmail Setup:**
1. Enable 2FA on Google account
2. Generate app-specific password
3. Use in configuration:

```yaml
email_smtp_host: "smtp.gmail.com"
email_smtp_port: 587
email_username: "your-email@gmail.com"
email_password: "your-app-specific-password"
```

### Testing Notifications

```bash
# Trigger a test failure by copying an invalid file
echo "corrupt" > /var/lib/h2kvm/queue/test.vmdk

# Check logs for notification attempt
journalctl -u h2kvm | grep -i "webhook\|email"
```

---

## 7. File Deduplication

### Overview
Tracks processed files in SQLite database to prevent reprocessing duplicates.

### Configuration

```yaml
enable_deduplication: true

# Hash-based deduplication (slower but catches renamed files)
deduplication_use_md5: false
```

### Deduplication Methods

**Method 1: Filename + Size (default)**
- Fast
- Catches exact copies
- Won't detect renamed files

**Method 2: MD5 Hash**
- Slower (reads entire file)
- Catches renamed files with same content
- More reliable but impacts performance

### Database Location

```
{output_dir}/.daemon/deduplication.db
```

### How It Works

1. New file appears
2. Check database for:
   - Same filename + file size OR
   - Same MD5 hash (if enabled)
3. If match found → Skip processing, log as duplicate
4. If no match → Process normally
5. After processing → Record in database

### Example Output

```
⏭️ Skipping duplicate: vm1.vmdk (originally processed: 2026-01-17T09:00:00Z)
```

### Database Maintenance

```bash
# Database is automatically cleaned up every 90 days on daemon shutdown
# Manual cleanup can be done with SQLite:

sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db

# View all processed files
sqlite> SELECT filename, processed_at, status FROM processed_files ORDER BY processed_at DESC LIMIT 10;

# Delete old records
sqlite> DELETE FROM processed_files WHERE processed_at < datetime('now', '-90 days');

# Check database size
sqlite> .dbinfo
```

### Statistics

```python
# Check deduplication stats programmatically
from pathlib import Path
import sqlite3

db_path = Path('/var/lib/h2kvm/output/.daemon/deduplication.db')
conn = sqlite3.connect(str(db_path))

cursor = conn.execute("""
    SELECT status, COUNT(*) as count
    FROM processed_files
    GROUP BY status
""")

for row in cursor:
    print(f"{row[0]}: {row[1]} files")
```

---

## 8. Enhanced Error Context

### Overview
Detailed error information with actionable suggestions for faster troubleshooting.

### Error Files Location

```
{watch_dir}/.errors/
  ├── failed-vm.vmdk           # Failed disk file
  └── failed-vm.vmdk.error.json  # Detailed error context
```

### Error JSON Structure

```json
{
  "filename": "failed-vm.vmdk",
  "filepath": "/var/lib/h2kvm/queue/failed-vm.vmdk",
  "file_size_mb": 50.5,
  "timestamp": "2026-01-17T11:30:00Z",
  "error": "Disk image corrupted: invalid VMDK descriptor",
  "phase": "disk_extraction",
  "exception_traceback": "Traceback (most recent call last):\n...",
  "suggestion": "Re-export the VM from source, the disk image may be corrupted",
  "system_info": {
    "python_version": "3.11.2",
    "disk_space_free_gb": 250.5
  }
}
```

### Error Phases

Tracks where in the pipeline the error occurred:

- `initialization` - Setup phase
- `file_type_detection` - File extension validation
- `argument_preparation` - Config preparation
- `output_directory_creation` - Directory setup
- `conversion` - Main conversion pipeline
- `completion` - Final steps

### Actionable Suggestions

The system provides context-aware suggestions based on the error:

| Error Pattern | Suggestion |
|--------------|------------|
| Disk full/space | Free up disk space or configure different output directory |
| Permission denied | Check file permissions and ensure daemon has required access |
| Corrupt/invalid | Re-export the VM from source, the disk image may be corrupted |
| Network/timeout | Check network connectivity to source system |
| Memory error | Reduce max_concurrent_jobs or increase system memory |

### Troubleshooting Workflow

```bash
# 1. List failed files
ls -lh /var/lib/h2kvm/queue/.errors/

# 2. Read error context
cat /var/lib/h2kvm/queue/.errors/failed-vm.vmdk.error.json | jq '.'

# 3. Follow suggestion
cat /var/lib/h2kvm/queue/.errors/failed-vm.vmdk.error.json | jq -r '.suggestion'

# 4. Check system state if needed
cat /var/lib/h2kvm/queue/.errors/failed-vm.vmdk.error.json | jq '.system_info'

# 5. Review full traceback if needed
cat /var/lib/h2kvm/queue/.errors/failed-vm.vmdk.error.json | jq -r '.exception_traceback'
```

---

## Complete Configuration Example

See `examples/yaml/50-daemon/daemon-enhanced.yaml` for a fully-commented configuration demonstrating all features.

## Performance Impact

| Feature | CPU Overhead | Memory Overhead | Disk I/O Overhead |
|---------|--------------|-----------------|-------------------|
| Concurrent Processing | None (better utilization) | +50MB per worker | Parallel I/O (faster) |
| File Completion | Minimal | Negligible | None |
| Statistics | Minimal | ~1-2MB | ~100KB/hour |
| Retry | Minimal | Negligible | None |
| Control API | Minimal | ~1MB | None |
| Notifications | Minimal | Negligible | Network only |
| Deduplication (filename) | Minimal | ~1MB | ~10KB/file |
| Deduplication (MD5) | Moderate (hash calc) | ~1MB | Full file read |
| Error Context | Minimal | ~100KB/error | ~10KB/error |

**Total overhead:** ~5-10MB RAM, negligible CPU except MD5 deduplication

## Production Checklist

- [ ] Configure appropriate `max_concurrent_jobs` for your system
- [ ] Enable notifications with webhook or email
- [ ] Set up monitoring of stats.json
- [ ] Configure retry policy for your use case
- [ ] Test control API commands
- [ ] Verify deduplication is working
- [ ] Check error context files are being created
- [ ] Set up log rotation for daemon logs
- [ ] Configure systemd service limits appropriately
- [ ] Test pause/resume functionality
- [ ] Verify stall detection threshold is appropriate

## See Also

- [Main Daemon Documentation](10-Daemon-Mode.md)
- [YAML Configuration Examples](05-YAML-Examples.md)
- [Systemd Service Setup](../systemd/README.md)
