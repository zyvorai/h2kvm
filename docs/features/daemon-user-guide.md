# Enhanced Daemon Mode - Complete User Guide

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Enhancement 1: Concurrent Processing](#enhancement-1-concurrent-processing)
4. [Enhancement 2: File Completion Detection](#enhancement-2-file-completion-detection)
5. [Enhancement 3: Statistics Tracking](#enhancement-3-statistics-tracking)
6. [Enhancement 4: Retry Mechanism](#enhancement-4-retry-mechanism)
7. [Enhancement 5: Control API](#enhancement-5-control-api)
8. [Enhancement 6: Notifications](#enhancement-6-notifications)
9. [Enhancement 7: File Deduplication](#enhancement-7-file-deduplication)
10. [Enhancement 8: Enhanced Error Context](#enhancement-8-enhanced-error-context)
11. [Production Deployment](#production-deployment)
12. [Monitoring and Operations](#monitoring-and-operations)
13. [Troubleshooting](#troubleshooting)

---

## Overview

The enhanced daemon mode transforms h2kvm into a production-ready, always-on VM conversion service. It monitors a directory for incoming VM files and automatically converts them with enterprise-grade features:

- **🚀 Concurrent Processing** - Convert multiple VMs simultaneously
- **⏱️ File Completion Detection** - Wait for uploads to finish before processing
- **📊 Statistics Tracking** - Monitor performance and success rates
- **🔄 Retry Mechanism** - Automatically retry failed conversions
- **🎮 Control API** - Manage daemon without restarts
- **🔔 Notifications** - Get alerts via Slack, Discord, or email
- **🔍 File Deduplication** - Prevent reprocessing duplicate files
- **📝 Enhanced Error Context** - Detailed troubleshooting information

---

## Getting Started

### Prerequisites

```bash
# Install h2kvm
pip install h2kvm

# Verify installation
h2kvm --version
```

### Quick Start

**1. Create a configuration file:**

```bash
mkdir -p /etc/h2kvm
cat > /etc/h2kvm/daemon.yaml <<'EOF'
command: daemon
daemon: true
watch_dir: /var/lib/h2kvm/queue
output_dir: /var/lib/h2kvm/output
work_dir: /var/lib/h2kvm/work

# Enable all enhancements
max_concurrent_jobs: 3
file_stable_timeout: 30
enable_deduplication: true
archive_processed: true

retry_policy:
  enabled: true
  max_retries: 3
  retry_delay: 300
  backoff_multiplier: 2.0

verbose: 2
EOF
```

**2. Create directories:**

```bash
sudo mkdir -p /var/lib/h2kvm/{queue,output,work}
sudo chown -R $(whoami):$(whoami) /var/lib/h2kvm
```

**3. Start the daemon:**

```bash
sudo h2kvmctl --config /etc/h2kvm/daemon.yaml
```

**4. Drop VM files into the queue:**

```bash
# Daemon will automatically detect and convert them
cp my-vm.vmdk /var/lib/h2kvm/queue/
```

---

## Enhancement 1: Concurrent Processing

### What It Does

Processes multiple VM files simultaneously using a pool of worker threads. Instead of converting VMs one at a time, the daemon can handle 3, 5, or more conversions in parallel.

### Configuration

```yaml
# Number of VMs to convert simultaneously
max_concurrent_jobs: 3
```

**Choosing the Right Value:**

- **Small server (2-4 cores, 8GB RAM):** `max_concurrent_jobs: 2`
- **Medium server (8 cores, 16GB RAM):** `max_concurrent_jobs: 3-4`
- **Large server (16+ cores, 32GB+ RAM):** `max_concurrent_jobs: 5-8`

**Resource Considerations:**

Each concurrent job requires:
- **CPU:** 1-2 cores for conversion
- **RAM:** 2-4GB for guestfs backend operations
- **Disk I/O:** Significant read/write bandwidth

### Usage Example

```yaml
# Configuration for a server with 8 cores and 16GB RAM
max_concurrent_jobs: 4

# With this configuration, if you drop 10 VM files:
# - 4 will start processing immediately
# - 6 will wait in queue
# - As each completes, the next one starts
```

### Monitoring Concurrent Jobs

```bash
# Check how many jobs are currently processing
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats

# Output shows:
#   Queue Depth: 3       ← Jobs waiting to process
#   Currently Processing: 4  ← Jobs actively running
```

### Performance Tips

**1. Balance CPU and I/O:**
```yaml
# If conversions are CPU-bound (high CPU, low I/O):
max_concurrent_jobs: 6

# If conversions are I/O-bound (low CPU, high disk I/O):
max_concurrent_jobs: 3  # Don't overwhelm storage
```

**2. Monitor system resources:**
```bash
# Watch CPU and memory while daemon runs
htop

# Watch disk I/O
iostat -x 2
```

**3. Adjust based on file sizes:**
```yaml
# For small VMs (< 20GB):
max_concurrent_jobs: 5

# For large VMs (100GB+):
max_concurrent_jobs: 2  # Prevent I/O saturation
```

---

## Enhancement 2: File Completion Detection

### What It Does

Waits for file uploads to complete before starting conversion. Prevents processing incomplete or still-uploading files that would result in corrupted conversions.

### Configuration

```yaml
# Seconds to wait for file size to stabilize
file_stable_timeout: 30
```

**How It Works:**

1. File appears in watch directory
2. Daemon checks file size every 1 second
3. File must have same size for **3 consecutive checks**
4. If size keeps changing, daemon waits up to `file_stable_timeout` seconds
5. Once stable (or timeout reached), file is queued for processing

### Configuration Guidelines

**For fast local copies:**
```yaml
file_stable_timeout: 10  # Files stabilize quickly
```

**For network uploads (SMB, NFS, rsync):**
```yaml
file_stable_timeout: 60  # Allow time for large transfers
```

**For slow WAN transfers:**
```yaml
file_stable_timeout: 300  # 5 minutes for very slow connections
```

### Usage Example

**Scenario:** Uploading a 100GB VMDK over network

```yaml
file_stable_timeout: 120  # 2 minutes

# Timeline:
# 00:00 - File appears in queue/ (10GB written)
# 00:30 - Still growing (50GB written)
# 01:00 - Still growing (80GB written)
# 01:15 - Upload completes (100GB)
# 01:15 - Size check #1: 100GB
# 01:16 - Size check #2: 100GB
# 01:17 - Size check #3: 100GB ✓ STABLE
# 01:17 - File queued for processing
```

### Verification

Check daemon logs to see stability detection:

```bash
tail -f /var/log/h2kvm/daemon.log

# You'll see:
# INFO: Waiting for file stability: large-vm.vmdk
# INFO: File size stable after 45 seconds
# INFO: 📥 New file queued: large-vm.vmdk
```

### Advanced: Custom Stability Checks

The stability check requires **3 consecutive identical size checks** (hardcoded). This typically takes 3 seconds minimum.

**Tradeoffs:**

- **Short timeout (10s):** Fast response, but may process incomplete files if transfer is slow
- **Long timeout (300s):** Very safe, but delays processing of complete files
- **Recommended:** 30-60 seconds for most use cases

---

## Enhancement 3: Statistics Tracking

### What It Does

Tracks comprehensive metrics about daemon performance, success rates, and processing times. Data is available via API and saved to JSON file for external monitoring.

### Configuration

```yaml
# Statistics are always enabled in enhanced mode
# Data saved to: {output_dir}/.daemon/stats.json
```

### Accessing Statistics

**Method 1: Control API**

```bash
# Get current statistics
h2kvmctl.cli.daemon_ctl \
  --output-dir /var/lib/h2kvm/output \
  stats

# Example output:
# 📊 Daemon Statistics:
#   Uptime: 12.5 hours
#   Processed: 145
#   Failed: 3
#   Success Rate: 97.9%
#   Avg Processing Time: 284.3s
#   Queue Depth: 2
```

**Method 2: JSON File**

```bash
# Read stats.json directly
cat /var/lib/h2kvm/output/.daemon/stats.json | python3 -m json.tool

# Output structure:
{
  "daemon_start_time": "2026-01-17T08:00:00",
  "uptime_hours": 12.5,
  "total_processed": 145,
  "total_failed": 3,
  "total_retried": 5,
  "success_rate": 97.9,
  "average_processing_time_seconds": 284.3,
  "current_queue_depth": 2,
  "by_file_type": {
    "vmdk": {"processed": 120, "failed": 2, "avg_time": 245.1},
    "vhdx": {"processed": 25, "failed": 1, "avg_time": 412.8}
  },
  "current_jobs": {
    "vm-001.vmdk": {
      "status": "processing",
      "start_time": "2026-01-17T20:30:15",
      "file_size_mb": 51200.0
    }
  }
}
```

### Monitoring Strategies

**1. Real-Time Monitoring:**

```bash
# Watch statistics update every 5 seconds
watch -n 5 'h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats'
```

**2. Automated Monitoring (Prometheus/Grafana):**

```bash
# Script to export metrics for Prometheus
#!/bin/bash
STATS_FILE="/var/lib/h2kvm/output/.daemon/stats.json"

# Export to Prometheus text format
python3 << 'PYEOF'
import json
with open("/var/lib/h2kvm/output/.daemon/stats.json") as f:
    stats = json.load(f)
    print(f"h2kvm_processed_total {stats['total_processed']}")
    print(f"h2kvm_failed_total {stats['total_failed']}")
    print(f"h2kvm_success_rate {stats['success_rate']}")
    print(f"h2kvm_queue_depth {stats['current_queue_depth']}")
    print(f"h2kvm_avg_processing_time_seconds {stats['average_processing_time_seconds']}")
PYEOF
```

**3. Alerting:**

```bash
# Check if success rate drops below threshold
#!/bin/bash
SUCCESS_RATE=$(h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats --json | \
  jq -r '.stats.success_rate')

if (( $(echo "$SUCCESS_RATE < 90" | bc -l) )); then
  echo "ALERT: Success rate dropped to ${SUCCESS_RATE}%"
  # Send alert via email/webhook
fi
```

### Statistics File Behavior

- **Auto-save interval:** Every 60 seconds
- **Save on events:** Job completion, daemon shutdown
- **File location:** `{output_dir}/.daemon/stats.json`
- **Format:** Human-readable JSON
- **Persistence:** Survives daemon restarts

### Per-File-Type Metrics

Track performance by file type to identify patterns:

```json
{
  "by_file_type": {
    "vmdk": {
      "processed": 120,
      "failed": 2,
      "avg_time": 245.1,
      "success_rate": 98.3
    },
    "vhdx": {
      "processed": 25,
      "failed": 5,
      "avg_time": 412.8,
      "success_rate": 80.0  // ← Indicates VHDX conversions have issues
    }
  }
}
```

---

## Enhancement 4: Retry Mechanism

### What It Does

Automatically retries failed conversions with exponential backoff. Handles transient errors without manual intervention.

### Configuration

```yaml
retry_policy:
  enabled: true
  max_retries: 3           # Try up to 3 times (initial + 2 retries)
  retry_delay: 300         # Initial delay: 5 minutes
  backoff_multiplier: 2.0  # Double delay each retry
```

### How It Works

**Example: File fails with network timeout**

```
Attempt 1 (immediate): FAILED - Network timeout
  ↓ Wait 5 minutes
Attempt 2 (5 min later): FAILED - Network timeout
  ↓ Wait 10 minutes (5 * 2.0)
Attempt 3 (15 min later): SUCCESS ✓
```

**Retry Schedule Calculator:**

```python
# Formula: delay = retry_delay * (backoff_multiplier ** attempt)

# With default config (retry_delay=300, backoff_multiplier=2.0):
Attempt 1: Immediate
Retry 1:   5 minutes later  (300 * 2^0 = 300s)
Retry 2:   10 minutes later (300 * 2^1 = 600s)
Retry 3:   20 minutes later (300 * 2^2 = 1200s)
```

### Configuration Examples

**Aggressive Retry (for transient errors):**
```yaml
retry_policy:
  enabled: true
  max_retries: 5
  retry_delay: 60          # 1 minute initial delay
  backoff_multiplier: 1.5  # Slower exponential growth

# Schedule: 0s → 1m → 1.5m → 2.25m → 3.4m → 5m
```

**Conservative Retry (for rare errors):**
```yaml
retry_policy:
  enabled: true
  max_retries: 2
  retry_delay: 600         # 10 minute initial delay
  backoff_multiplier: 3.0  # Aggressive backoff

# Schedule: 0s → 10m → 30m
```

**No Retries (fail fast):**
```yaml
retry_policy:
  enabled: false
```

### Monitoring Retries

**Check retry queue:**

```bash
# Files in retry queue have retry count in stats
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats --json | \
  jq '.stats.current_jobs[] | select(.retry_count > 0)'

# Example output:
{
  "filename": "vm-042.vmdk",
  "status": "retrying",
  "retry_count": 2,
  "next_retry": "2026-01-17T21:15:00",
  "error": "Connection timeout to vSphere"
}
```

**Watch daemon logs:**

```bash
tail -f /var/log/h2kvm/daemon.log | grep -i retry

# Output:
# INFO: Retry 1/3 for vm-042.vmdk (next retry in 5.0 minutes)
# INFO: 🔄 Scheduling retry for vm-042.vmdk
# INFO: Processing retry attempt 2/3: vm-042.vmdk
```

### Retry Behavior

**Files remain in queue during retries:**
- File stays in `watch_dir` until all retries exhausted
- After final failure, moved to `watch_dir/.errors/`
- Successful retry moves file to archive (if enabled)

**What triggers retries:**
- ✅ Network timeouts
- ✅ Temporary permission errors
- ✅ vSphere connection failures
- ✅ Transient I/O errors
- ❌ Invalid file format (no retry)
- ❌ Missing required tools (no retry)

**Retry state persists:**
- Retry queue survives daemon restart
- Next retry time preserved
- Retry count maintained

### Manual Retry Override

**Force immediate retry:**

```bash
# Move file from .errors back to queue
mv /var/lib/h2kvm/queue/.errors/vm-042.vmdk \
   /var/lib/h2kvm/queue/

# Daemon will process as new file
```

**Clear retry count:**

```bash
# Restart daemon to clear in-memory retry queue
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stop
sudo h2kvmctl --config /etc/h2kvm/daemon.yaml
```

---

## Enhancement 5: Control API

### What It Does

Provides runtime control of the daemon via Unix socket. Manage daemon without restarts using simple CLI commands.

### Available Commands

```bash
# Check daemon status
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status

# Get statistics
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats

# Pause processing (finish current jobs, don't start new ones)
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output pause

# Resume processing
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output resume

# Drain and stop (finish current jobs, then exit)
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output drain

# Stop immediately (graceful shutdown)
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stop
```

### Configuration

```yaml
# Control socket automatically created at:
# {output_dir}/.daemon/control.sock

# No configuration needed - always enabled
```

### Command Details

#### `status` - Check Daemon State

```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status

# Output:
  Status: ▶️  RUNNING

# Possible states:
#   ▶️  RUNNING  - Processing files normally
#   ⏸️  PAUSED   - Not accepting new jobs
#   🚰 DRAINING - Finishing current jobs before shutdown
#   ⏹️  STOPPED  - Daemon not running
```

#### `stats` - Get Statistics

```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats

# Output:
📊 Daemon Statistics:
  Uptime: 5.2 hours
  Processed: 42
  Failed: 1
  Success Rate: 97.6%
  Avg Processing Time: 245.8s
  Queue Depth: 3

# Add --json for machine-readable output:
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats --json
```

#### `pause` - Pause Processing

```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output pause

# Use cases:
# - Maintenance window (backup storage)
# - Resource constraints (free up CPU/RAM)
# - Manual intervention needed
# - Testing changes
```

**What happens:**
- Currently processing jobs: Continue to completion
- Queued jobs: Remain in queue, not started
- New files: Detected but not processed
- Watchdog: Continues monitoring directory

**Resume when ready:**
```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output resume
```

#### `drain` - Graceful Shutdown

```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output drain

# Use cases:
# - Planned daemon restart
# - Server maintenance
# - Configuration changes
# - Upgrading h2kvm
```

**What happens:**
1. Stop accepting new jobs
2. Wait for current jobs to complete
3. Save all state (stats, retry queue)
4. Shut down cleanly

**Timeline example:**
```
00:00 - drain command sent
00:00 - 3 jobs currently processing
00:05 - Job 1 completes (2 remaining)
00:08 - Job 2 completes (1 remaining)
00:12 - Job 3 completes (0 remaining)
00:12 - Daemon exits cleanly
```

#### `stop` - Immediate Shutdown

```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stop

# Use case: Emergency shutdown
```

**What happens:**
- Send SIGTERM to daemon
- Daemon attempts graceful shutdown
- Current jobs: Interrupted (safe rollback)
- State: Saved before exit

### Usage Examples

**Example 1: Maintenance Window**

```bash
# Pause daemon before storage maintenance
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output pause

# Perform storage backup
rsync -av /var/lib/h2kvm/output/ backup-server:/backups/

# Resume processing
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output resume
```

**Example 2: Safe Restart for Config Changes**

```bash
# Drain current work
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output drain

# Wait for completion (or check status)
while h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status | grep -q RUNNING; do
  sleep 5
done

# Update configuration
vim /etc/h2kvm/daemon.yaml

# Restart daemon
sudo h2kvmctl --config /etc/h2kvm/daemon.yaml
```

**Example 3: Monitoring Script**

```bash
#!/bin/bash
# monitor-daemon.sh

while true; do
  clear
  echo "=== H2KVM Daemon Monitor ==="
  echo

  h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status
  echo
  h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats

  sleep 10
done
```

### API Socket Location

```bash
# Default location:
/var/lib/h2kvm/output/.daemon/control.sock

# Permissions:
srwxr-xr-x 1 root root 0 Jan 17 08:36 control.sock

# Check if socket exists:
ls -l /var/lib/h2kvm/output/.daemon/control.sock

# Test connectivity:
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status
```

### Troubleshooting Control API

**Error: "Connection refused"**
```bash
# Daemon not running - start it
sudo h2kvmctl --config /etc/h2kvm/daemon.yaml
```

**Error: "Socket not found"**
```bash
# Wrong output directory
h2kvmctl.cli.daemon_ctl --output-dir /correct/path/to/output status
```

**Error: "Timeout"**
```bash
# Daemon busy or hung - check logs
tail -f /var/log/h2kvm/daemon.log

# Force stop if needed
sudo pkill -TERM -f "h2kvm.*daemon"
```

---

## Enhancement 6: Notifications

### What It Does

Sends real-time alerts about conversion events via webhooks (Slack, Discord, generic) or email. Get notified about failures, completions, and daemon health.

### Configuration

**Slack Integration:**

```yaml
notifications:
  enabled: true
  webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  webhook_type: "slack"

  # Optional: Filter events
  notify_on_success: false  # Don't spam on every success
  notify_on_failure: true   # Alert on failures
  notify_on_stall: true     # Alert if daemon stalls
```

**Discord Integration:**

```yaml
notifications:
  enabled: true
  webhook_url: "https://discord.com/api/webhooks/YOUR/WEBHOOK/URL"
  webhook_type: "discord"
  notify_on_success: true
  notify_on_failure: true
```

**Generic Webhook:**

```yaml
notifications:
  enabled: true
  webhook_url: "https://your-monitoring.com/webhook"
  webhook_type: "generic"  # Sends JSON payload
  webhook_headers:
    Authorization: "Bearer YOUR_TOKEN"
    X-Custom-Header: "value"
```

**Email Notifications:**

```yaml
notifications:
  enabled: true
  email_enabled: true
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  smtp_use_tls: true
  smtp_username: "your-email@gmail.com"
  smtp_password: "your-app-password"  # Use app-specific password
  email_from: "h2kvm@yourcompany.com"
  email_to: "ops-team@yourcompany.com"
  email_subject_prefix: "[H2KVM]"
```

**Combined (Webhook + Email):**

```yaml
notifications:
  enabled: true

  # Webhook for real-time alerts
  webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  webhook_type: "slack"

  # Email for failures only
  email_enabled: true
  smtp_server: "smtp.company.com"
  smtp_port: 587
  smtp_use_tls: true
  smtp_username: "notifications@company.com"
  smtp_password: "password"
  email_from: "h2kvm@company.com"
  email_to: "oncall@company.com"

  # Event filters
  notify_on_success: false  # Slack only, not email
  notify_on_failure: true   # Both Slack and email
  notify_on_stall: true     # Both
```

### Setting Up Slack Webhooks

**1. Create Incoming Webhook:**
- Go to: https://api.slack.com/apps
- Create new app → "From scratch"
- Enable "Incoming Webhooks"
- Click "Add New Webhook to Workspace"
- Select channel (e.g., #vm-conversions)
- Copy webhook URL

**2. Configure h2kvm:**

```yaml
notifications:
  enabled: true
  webhook_url: "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
  webhook_type: "slack"
```

**3. Test:**

```bash
# Trigger a test failure to see notification
echo "test" > /var/lib/h2kvm/queue/test.vmdk
# (Will fail, triggering notification)
```

### Setting Up Discord Webhooks

**1. Create Webhook:**
- Open Discord server
- Server Settings → Integrations → Webhooks
- Click "New Webhook"
- Choose channel (e.g., #vm-alerts)
- Copy webhook URL

**2. Configure h2kvm:**

```yaml
notifications:
  enabled: true
  webhook_url: "https://discord.com/api/webhooks/123456789/abcdefghijklmnop"
  webhook_type: "discord"
```

### Notification Events

**Conversion Success:**
```
✅ Conversion Successful
vm-042.vmdk → /var/lib/h2kvm/output/2026-01-17/vm-042
Size: 51.2GB
Duration: 4m 32s
```

**Conversion Failure:**
```
❌ Conversion Failed
vm-123.vmdk
Error: Connection timeout to vSphere
Retry: 1/3 (next retry in 5.0 minutes)
```

**Daemon Stall:**
```
⚠️ Daemon Stalled
No files processed in 60 minutes
Queue depth: 5
Currently processing: 0
Action: Check daemon health
```

**Retry Success:**
```
✅ Retry Successful
vm-123.vmdk succeeded on attempt 2/3
Previous error: Connection timeout to vSphere
Duration: 5m 12s
```

### Notification Payload Examples

**Slack Format:**

```json
{
  "attachments": [{
    "color": "danger",
    "title": "❌ Conversion Failed",
    "text": "Failed to convert vm-123.vmdk",
    "fields": [
      {"title": "Filename", "value": "vm-123.vmdk", "short": true},
      {"title": "Size", "value": "51.2GB", "short": true},
      {"title": "Error", "value": "Connection timeout", "short": false},
      {"title": "Retry", "value": "1/3 (next in 5.0 min)", "short": true}
    ],
    "footer": "H2KVM Daemon",
    "ts": 1705488000
  }]
}
```

**Generic Webhook Format:**

```json
{
  "event": "conversion_failure",
  "timestamp": "2026-01-17T14:30:00Z",
  "details": {
    "filename": "vm-123.vmdk",
    "file_size_mb": 51200.0,
    "error": "Connection timeout to vSphere",
    "retry_count": 1,
    "max_retries": 3,
    "next_retry_minutes": 5.0
  }
}
```

### Testing Notifications

**Test webhook connectivity:**

```bash
# Manual webhook test (Slack)
curl -X POST -H 'Content-Type: application/json' \
  -d '{"text":"Test from h2kvm"}' \
  https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Test email configuration:**

```python
# test-email.py
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Test email from h2kvm")
msg['Subject'] = '[H2KVM] Test Notification'
msg['From'] = 'h2kvm@company.com'
msg['To'] = 'you@company.com'

with smtplib.SMTP('smtp.company.com', 587) as server:
    server.starttls()
    server.login('username', 'password')
    server.send_message(msg)
    print("Email sent successfully")
```

### Advanced: Custom Notification Logic

**Conditional notifications based on error type:**

```yaml
notifications:
  enabled: true
  webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  webhook_type: "slack"

  # Only notify on non-transient errors
  # (Transient errors will retry automatically)
  notify_on_failure: true

  # Don't spam on every success
  notify_on_success: false

  # Alert if daemon hasn't processed anything in 1 hour
  stall_check_interval: 3600
  notify_on_stall: true
```

### Troubleshooting Notifications

**Notifications not sending:**

```bash
# Check daemon logs
tail -f /var/log/h2kvm/daemon.log | grep -i notif

# Common issues:
# - Invalid webhook URL
# - Network connectivity
# - SMTP authentication failure
```

**Test webhook manually:**

```bash
# Add debug logging
verbose: 3  # In config file

# Trigger test failure
echo "test" > /var/lib/h2kvm/queue/test-notify.vmdk

# Watch logs for webhook attempt
tail -f /var/log/h2kvm/daemon.log | grep -i "webhook\|notification"
```

---

## Enhancement 7: File Deduplication

### What It Does

Prevents reprocessing files that were already converted. Uses SQLite database to track processed files by filename+size or MD5 hash.

### Configuration

```yaml
# Enable deduplication
enable_deduplication: true

# Deduplication method:
deduplication_use_md5: false  # Fast: filename + size
# deduplication_use_md5: true   # Secure: MD5 hash (slower)
```

### How It Works

**Filename + Size Method (default):**

```
1. File appears: vm-001.vmdk (100GB)
2. Check database: Has "vm-001.vmdk, 100GB" been processed?
3. If YES: Skip (duplicate)
4. If NO: Process and record
```

**MD5 Hash Method:**

```
1. File appears: vm-001.vmdk (100GB)
2. Calculate MD5: a1b2c3d4e5f6...
3. Check database: Has this MD5 been processed?
4. If YES: Skip (duplicate, even if renamed)
5. If NO: Process and record
```

### Configuration Guide

**Fast Method (filename + size):**
```yaml
enable_deduplication: true
deduplication_use_md5: false

# Pros:
# - Instant check (no file read needed)
# - Minimal CPU overhead
# - Good for most use cases

# Cons:
# - Renamed duplicates not detected
# - Files with same size but different content treated as duplicates
```

**Secure Method (MD5 hash):**
```yaml
enable_deduplication: true
deduplication_use_md5: true

# Pros:
# - Detects renamed duplicates
# - Content-based deduplication
# - 100% accurate

# Cons:
# - Must read entire file to calculate hash
# - Slower for large files (100GB = ~2 minutes)
# - Higher CPU usage
```

**Disabled:**
```yaml
enable_deduplication: false

# All files processed, even duplicates
```

### Database Location

```bash
# Database stored at:
/var/lib/h2kvm/output/.daemon/deduplication.db

# SQLite database file
ls -lh /var/lib/h2kvm/output/.daemon/deduplication.db
# -rw-r--r-- 1 root root 245K Jan 17 14:30 deduplication.db
```

### Database Schema

```sql
CREATE TABLE processed_files (
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    md5_hash TEXT,
    processed_at TEXT NOT NULL,
    output_path TEXT,
    status TEXT NOT NULL,  -- 'success' or 'failed'
    UNIQUE(filename, file_size)
);

CREATE INDEX idx_filename_size ON processed_files(filename, file_size);
CREATE INDEX idx_md5 ON processed_files(md5_hash);
```

### Querying Deduplication Database

**Check if file was processed:**

```bash
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "SELECT * FROM processed_files WHERE filename = 'vm-001.vmdk';"

# Output:
# vm-001.vmdk|/var/lib/h2kvm/queue/vm-001.vmdk|107374182400|a1b2c3...|2026-01-17T14:30:00|/var/lib/h2kvm/output/2026-01-17/vm-001|success
```

**List all processed files:**

```bash
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "SELECT filename, file_size/1024/1024/1024 AS size_gb, processed_at, status FROM processed_files ORDER BY processed_at DESC LIMIT 10;"

# Output:
# vm-042.vmdk|100.0|2026-01-17T15:45:00|success
# vm-041.vmdk|51.2|2026-01-17T15:30:00|success
# vm-040.vmdk|200.0|2026-01-17T15:15:00|failed
```

**Count processed files:**

```bash
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "SELECT status, COUNT(*) FROM processed_files GROUP BY status;"

# Output:
# success|142
# failed|3
```

**Find duplicate files (same MD5):**

```bash
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "SELECT md5_hash, COUNT(*), GROUP_CONCAT(filename) FROM processed_files WHERE md5_hash IS NOT NULL GROUP BY md5_hash HAVING COUNT(*) > 1;"

# Output shows files with identical content but different names
```

### Usage Examples

**Example 1: Detect duplicate upload**

```bash
# User uploads vm-001.vmdk
cp /mnt/import/vm-001.vmdk /var/lib/h2kvm/queue/
# ✅ Processed successfully

# User accidentally uploads again
cp /mnt/import/vm-001.vmdk /var/lib/h2kvm/queue/
# ℹ️ Skipped (duplicate detected)

# Daemon log:
# INFO: Duplicate file detected: vm-001.vmdk (100.0GB)
# INFO: Previously processed: 2026-01-17T14:30:00
# INFO: Skipping duplicate
```

**Example 2: Renamed file detection (MD5 mode)**

```yaml
deduplication_use_md5: true
```

```bash
# Process original
cp /mnt/import/production-db.vmdk /var/lib/h2kvm/queue/
# ✅ Processed (MD5: a1b2c3d4...)

# Someone renames and uploads again
cp /mnt/import/production-db.vmdk /mnt/import/db-backup-2026-01.vmdk
cp /mnt/import/db-backup-2026-01.vmdk /var/lib/h2kvm/queue/
# ℹ️ Skipped (same MD5 hash detected)

# Daemon log:
# INFO: Duplicate file detected (MD5 match): db-backup-2026-01.vmdk
# INFO: Original file: production-db.vmdk
# INFO: Skipping duplicate
```

**Example 3: Force reprocessing**

```bash
# Remove file from deduplication database
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "DELETE FROM processed_files WHERE filename = 'vm-001.vmdk';"

# Now file can be reprocessed
cp /mnt/import/vm-001.vmdk /var/lib/h2kvm/queue/
# ✅ Processing (not a duplicate anymore)
```

### Maintenance

**Database size management:**

```bash
# Check database size
du -h /var/lib/h2kvm/output/.daemon/deduplication.db

# Compact database (reclaim space)
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db "VACUUM;"
```

**Purge old records:**

```sql
-- Delete records older than 90 days
DELETE FROM processed_files
WHERE processed_at < datetime('now', '-90 days');

-- Compact database
VACUUM;
```

**Automated cleanup script:**

```bash
#!/bin/bash
# cleanup-dedup-db.sh

DB_PATH="/var/lib/h2kvm/output/.daemon/deduplication.db"
RETENTION_DAYS=90

sqlite3 "$DB_PATH" <<SQL
DELETE FROM processed_files
WHERE processed_at < datetime('now', '-${RETENTION_DAYS} days');
VACUUM;
SQL

echo "Cleaned up records older than $RETENTION_DAYS days"
```

### Performance Impact

**Filename + Size Mode:**
- Overhead: ~1ms per file check
- No file read required
- Negligible impact on performance

**MD5 Hash Mode:**
- Overhead: ~20MB/s hash calculation
- Must read entire file
- 100GB file = ~85 seconds additional time
- Consider for smaller files or when duplicates are common

### Troubleshooting

**Database locked error:**

```bash
# Another process accessing database
# Wait and retry, or restart daemon
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stop
sudo h2kvmctl --config /etc/h2kvm/daemon.yaml
```

**False duplicate detection:**

```bash
# Check database entry
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "SELECT * FROM processed_files WHERE filename = 'suspected-false-positive.vmdk';"

# If incorrect, delete entry
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "DELETE FROM processed_files WHERE filename = 'suspected-false-positive.vmdk';"
```

---

## Enhancement 8: Enhanced Error Context

### What It Does

Creates detailed JSON error files with comprehensive debugging information when conversions fail. Includes error messages, stack traces, suggestions, and system state.

### Configuration

```yaml
# Enhanced error context is always enabled
# Error files saved to: {watch_dir}/.errors/
```

### Error File Structure

**Location:**
```
/var/lib/h2kvm/queue/.errors/vm-failed.vmdk.error.json
```

**Content:**

```json
{
  "filename": "vm-failed.vmdk",
  "filepath": "/var/lib/h2kvm/queue/vm-failed.vmdk",
  "file_size_mb": 51200.0,
  "timestamp": "2026-01-17T14:30:15.123456",
  "error": "Connection timeout to vSphere server",
  "phase": "export",
  "exception_traceback": "Traceback (most recent call last):\n  File \"h2kvm/orchestrator.py\", line 245, in run\n    ...",
  "suggestion": "Check network connectivity to vSphere server. Verify credentials and server URL.",
  "system_info": {
    "python_version": "3.14.2 (main, Dec  5 2025, 00:00:00) [GCC 15.2.1]",
    "disk_space_free_gb": 150.5,
    "memory_available_gb": 8.2
  },
  "retry_info": {
    "retry_count": 1,
    "max_retries": 3,
    "next_retry_at": "2026-01-17T14:35:15"
  }
}
```

### Error Fields Explained

**Basic Information:**
- `filename`: Name of failed VM file
- `filepath`: Full path to source file
- `file_size_mb`: File size in megabytes
- `timestamp`: When error occurred (ISO 8601)

**Error Details:**
- `error`: Human-readable error message
- `phase`: Which phase failed (export, conversion, upload, validation)
- `exception_traceback`: Full Python stack trace

**Actionable Information:**
- `suggestion`: Specific advice for fixing the error
- `system_info`: Relevant system state at time of error
- `retry_info`: Retry status if applicable

### Error Suggestions by Type

The system provides intelligent suggestions based on error patterns:

**Network Errors:**
```json
{
  "error": "Connection timeout to vSphere server",
  "suggestion": "Check network connectivity to vSphere server. Verify credentials and server URL. Check firewall rules."
}
```

**Permission Errors:**
```json
{
  "error": "This operation requires root. Re-run with sudo.",
  "suggestion": "Run daemon with sudo or configure appropriate permissions for guestfs backend operations."
}
```

**Disk Space Errors:**
```json
{
  "error": "No space left on device",
  "suggestion": "Free up disk space in work directory or output directory. Current free space: 2.1GB"
}
```

**Invalid Format:**
```json
{
  "error": "Invalid VMDK descriptor format",
  "suggestion": "Verify VMDK file is not corrupted. Check if file is a valid VMware disk image. Try exporting VM again from source."
}
```

**vSphere Errors:**
```json
{
  "error": "VM not found: vm-123",
  "suggestion": "Verify VM name or UUID is correct. Check if VM exists in vSphere inventory. Ensure proper datacenter/folder path."
}
```

### Using Error Context for Troubleshooting

**1. Quick diagnosis:**

```bash
# Check latest error
ls -lt /var/lib/h2kvm/queue/.errors/ | head -n 2

# Read error details
cat /var/lib/h2kvm/queue/.errors/vm-failed.vmdk.error.json | \
  jq '{error: .error, suggestion: .suggestion}'

# Output:
# {
#   "error": "Connection timeout to vSphere server",
#   "suggestion": "Check network connectivity to vSphere server..."
# }
```

**2. Batch analysis:**

```bash
# Find all errors by type
cd /var/lib/h2kvm/queue/.errors/
for f in *.error.json; do
  echo "=== $f ==="
  jq -r '.error' "$f"
done

# Find common error patterns
jq -r '.error' *.error.json | sort | uniq -c | sort -rn

# Output:
#   15 Connection timeout to vSphere server
#    3 No space left on device
#    1 Invalid VMDK descriptor format
```

**3. Track retry success:**

```bash
# Check if file succeeded on retry
FILE="vm-123.vmdk"

if [ -f "/var/lib/h2kvm/queue/.errors/${FILE}.error.json" ]; then
  echo "Failed initially:"
  jq -r '.error' "/var/lib/h2kvm/queue/.errors/${FILE}.error.json"

  if [ -d "/var/lib/h2kvm/output/2026-01-17/vm-123" ]; then
    echo "✅ But succeeded on retry!"
  fi
fi
```

**4. Generate error report:**

```bash
#!/bin/bash
# generate-error-report.sh

ERROR_DIR="/var/lib/h2kvm/queue/.errors"
REPORT_FILE="error-report-$(date +%Y%m%d).txt"

echo "H2KVM Error Report - $(date)" > "$REPORT_FILE"
echo "======================================" >> "$REPORT_FILE"
echo >> "$REPORT_FILE"

# Count errors by phase
echo "Errors by Phase:" >> "$REPORT_FILE"
jq -r '.phase' "$ERROR_DIR"/*.error.json 2>/dev/null | sort | uniq -c >> "$REPORT_FILE"
echo >> "$REPORT_FILE"

# List unique errors
echo "Unique Errors:" >> "$REPORT_FILE"
jq -r '.error' "$ERROR_DIR"/*.error.json 2>/dev/null | sort -u >> "$REPORT_FILE"
echo >> "$REPORT_FILE"

# Recent failures
echo "Recent Failures (last 5):" >> "$REPORT_FILE"
ls -t "$ERROR_DIR"/*.error.json 2>/dev/null | head -5 | while read f; do
  echo "---" >> "$REPORT_FILE"
  jq '{filename: .filename, error: .error, time: .timestamp}' "$f" >> "$REPORT_FILE"
done

echo "Report saved to: $REPORT_FILE"
```

### Integration with Monitoring

**Export errors to monitoring system:**

```bash
#!/bin/bash
# export-errors-to-monitoring.sh

ERROR_DIR="/var/lib/h2kvm/queue/.errors"
MONITORING_ENDPOINT="https://monitoring.company.com/api/errors"

for error_file in "$ERROR_DIR"/*.error.json; do
  # Send to monitoring API
  curl -X POST "$MONITORING_ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_TOKEN" \
    -d @"$error_file"

  # Archive after sending
  mv "$error_file" "$ERROR_DIR/archived/"
done
```

**Parse errors for alerting:**

```python
#!/usr/bin/env python3
# check-critical-errors.py

import json
import glob
from datetime import datetime, timedelta

ERROR_DIR = "/var/lib/h2kvm/queue/.errors"
CRITICAL_PATTERNS = [
    "disk space",
    "permission denied",
    "cannot connect"
]

recent_errors = []
cutoff_time = datetime.now() - timedelta(hours=1)

for error_file in glob.glob(f"{ERROR_DIR}/*.error.json"):
    with open(error_file) as f:
        error_data = json.load(f)
        error_time = datetime.fromisoformat(error_data['timestamp'])

        if error_time > cutoff_time:
            error_msg = error_data['error'].lower()

            for pattern in CRITICAL_PATTERNS:
                if pattern in error_msg:
                    recent_errors.append({
                        'file': error_data['filename'],
                        'error': error_data['error'],
                        'suggestion': error_data['suggestion']
                    })
                    break

if recent_errors:
    print(f"CRITICAL: {len(recent_errors)} critical errors in last hour")
    for err in recent_errors:
        print(f"  - {err['file']}: {err['error']}")
    exit(1)
else:
    print("OK: No critical errors")
    exit(0)
```

### Error File Cleanup

**Manual cleanup:**

```bash
# Remove error files older than 30 days
find /var/lib/h2kvm/queue/.errors/ \
  -name "*.error.json" \
  -mtime +30 \
  -delete
```

**Automated cleanup (cron):**

```bash
# Add to crontab
0 2 * * * find /var/lib/h2kvm/queue/.errors/ -name "*.error.json" -mtime +30 -delete
```

**Archive before cleanup:**

```bash
#!/bin/bash
# archive-errors.sh

ERROR_DIR="/var/lib/h2kvm/queue/.errors"
ARCHIVE_DIR="/var/lib/h2kvm/error-archives"
RETENTION_DAYS=30

# Create monthly archive
MONTH=$(date +%Y-%m)
ARCHIVE_FILE="$ARCHIVE_DIR/errors-$MONTH.tar.gz"

mkdir -p "$ARCHIVE_DIR"

# Archive old errors
find "$ERROR_DIR" -name "*.error.json" -mtime +$RETENTION_DAYS \
  -exec tar -czf "$ARCHIVE_FILE" --append {} \; \
  -delete

echo "Archived errors to: $ARCHIVE_FILE"
```

---

## Production Deployment

### System Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 8GB
- Disk: 100GB free (for work directory)
- OS: Linux (Ubuntu 20.04+, RHEL 8+, Fedora 35+)

**Recommended:**
- CPU: 8+ cores
- RAM: 16GB+
- Disk: 500GB+ SSD (fast I/O)
- Network: 1Gbps+ (for vSphere access)

### Installation Steps

**1. Install h2kvm:**

```bash
# Production installation
sudo pip3 install h2kvm

# Verify
h2kvm --version
```

**2. Create system user:**

```bash
# Create dedicated user for daemon
sudo useradd -r -s /bin/bash -d /var/lib/h2kvm -m h2kvm

# Add to required groups
sudo usermod -aG kvm h2kvm
```

**3. Create directory structure:**

```bash
sudo mkdir -p /var/lib/h2kvm/{queue,output,work}
sudo mkdir -p /etc/h2kvm
sudo mkdir -p /var/log/h2kvm

# Set ownership
sudo chown -R h2kvm:h2kvm /var/lib/h2kvm
sudo chown -R h2kvm:h2kvm /var/log/h2kvm
```

**4. Create production configuration:**

```bash
sudo tee /etc/h2kvm/daemon.yaml > /dev/null <<'EOF'
command: daemon
daemon: true

# Directories
watch_dir: /var/lib/h2kvm/queue
output_dir: /var/lib/h2kvm/output
work_dir: /var/lib/h2kvm/work

# Logging
log_file: /var/log/h2kvm/daemon.log
verbose: 2

# Performance
max_concurrent_jobs: 3
file_stable_timeout: 60

# Reliability
retry_policy:
  enabled: true
  max_retries: 3
  retry_delay: 600
  backoff_multiplier: 2.0

# Deduplication
enable_deduplication: true
deduplication_use_md5: false

# File Management
archive_processed: true

# Notifications
notifications:
  enabled: true
  webhook_url: "YOUR_WEBHOOK_URL"
  webhook_type: "slack"
  notify_on_success: false
  notify_on_failure: true
  notify_on_stall: true

# vSphere connection (if using vSphere export)
vsphere:
  server: "vcenter.company.com"
  vc_user: "automation@vsphere.local"
  password: "CHANGE_ME"
  dc_name: "DC1"
  insecure: false
EOF

# Secure the config file
sudo chmod 600 /etc/h2kvm/daemon.yaml
sudo chown h2kvm:h2kvm /etc/h2kvm/daemon.yaml
```

**5. Create systemd service:**

```bash
sudo tee /etc/systemd/system/h2kvm-daemon.service > /dev/null <<'EOF'
[Unit]
Description=H2KVM Daemon - Automated VM Conversion Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/var/lib/h2kvm
ExecStart=/usr/local/bin/h2kvmctl --config /etc/h2kvm/daemon.yaml
ExecStop=/usr/bin/h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output drain

# Restart policy
Restart=always
RestartSec=10s

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

# Security
NoNewPrivileges=false
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=h2kvm

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload
```

**6. Enable and start service:**

```bash
# Enable on boot
sudo systemctl enable h2kvm-daemon

# Start service
sudo systemctl start h2kvm-daemon

# Check status
sudo systemctl status h2kvm-daemon
```

### Log Rotation

```bash
sudo tee /etc/logrotate.d/h2kvm > /dev/null <<'EOF'
/var/log/h2kvm/daemon.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 h2kvm h2kvm
    sharedscripts
    postrotate
        systemctl reload h2kvm-daemon > /dev/null 2>&1 || true
    endscript
}
EOF
```

### Monitoring Setup

**1. Create monitoring script:**

```bash
sudo tee /usr/local/bin/h2kvm-healthcheck > /dev/null <<'EOF'
#!/bin/bash
# Health check script for monitoring systems

OUTPUT_DIR="/var/lib/h2kvm/output"
STATS_FILE="$OUTPUT_DIR/.daemon/stats.json"

# Check if daemon is running
if ! systemctl is-active --quiet h2kvm-daemon; then
    echo "CRITICAL: Daemon not running"
    exit 2
fi

# Check if control socket responds
if ! h2kvmctl.cli.daemon_ctl --output-dir "$OUTPUT_DIR" status > /dev/null 2>&1; then
    echo "WARNING: Control API not responding"
    exit 1
fi

# Check success rate
if [ -f "$STATS_FILE" ]; then
    SUCCESS_RATE=$(jq -r '.success_rate // 100' "$STATS_FILE")

    if (( $(echo "$SUCCESS_RATE < 50" | bc -l) )); then
        echo "CRITICAL: Success rate below 50%: $SUCCESS_RATE%"
        exit 2
    elif (( $(echo "$SUCCESS_RATE < 80" | bc -l) )); then
        echo "WARNING: Success rate below 80%: $SUCCESS_RATE%"
        exit 1
    fi
fi

echo "OK: Daemon healthy"
exit 0
EOF

sudo chmod +x /usr/local/bin/h2kvm-healthcheck
```

**2. Add to monitoring system:**

```bash
# Nagios/Icinga example
define service {
    use                     generic-service
    host_name               vm-conversion-server
    service_description     H2KVM Daemon
    check_command           check_by_ssh!/usr/local/bin/h2kvm-healthcheck
    check_interval          5
    retry_interval          1
}
```

### Backup Strategy

```bash
#!/bin/bash
# /usr/local/bin/h2kvm-backup

BACKUP_DIR="/backup/h2kvm"
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup configuration
tar -czf "$BACKUP_DIR/config-$DATE.tar.gz" /etc/h2kvm/

# Backup deduplication database
cp /var/lib/h2kvm/output/.daemon/deduplication.db \
   "$BACKUP_DIR/deduplication-$DATE.db"

# Backup statistics
cp /var/lib/h2kvm/output/.daemon/stats.json \
   "$BACKUP_DIR/stats-$DATE.json"

# Keep last 30 days
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.json" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### Security Hardening

**1. File permissions:**

```bash
# Restrict config file access
sudo chmod 600 /etc/h2kvm/daemon.yaml

# Protect queue directory
sudo chmod 750 /var/lib/h2kvm/queue
```

**2. SELinux (RHEL/CentOS):**

```bash
# Create SELinux policy if needed
sudo setsebool -P virt_use_nfs 1
sudo setsebool -P virt_use_samba 1
```

**3. Firewall:**

```bash
# No inbound ports needed (daemon is local-only)
# Only outbound access to vSphere required
```

---

## Monitoring and Operations

### Daily Operations

**Check daemon status:**

```bash
sudo systemctl status h2kvm-daemon
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status
```

**View recent activity:**

```bash
sudo journalctl -u h2kvm-daemon -f
```

**Check statistics:**

```bash
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats
```

**View queue:**

```bash
ls -lh /var/lib/h2kvm/queue/
```

### Performance Monitoring

**Resource usage:**

```bash
# CPU and memory
ps aux | grep h2kvm

# Disk I/O
iostat -x 2 10

# Disk space
df -h /var/lib/h2kvm/
```

**Conversion metrics:**

```bash
# Average processing time
jq -r '.average_processing_time_seconds' /var/lib/h2kvm/output/.daemon/stats.json

# Success rate
jq -r '.success_rate' /var/lib/h2kvm/output/.daemon/stats.json

# Queue depth
jq -r '.current_queue_depth' /var/lib/h2kvm/output/.daemon/stats.json
```

### Maintenance Tasks

**Planned restart:**

```bash
# Drain and stop
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output drain

# Wait for completion
while systemctl is-active --quiet h2kvm-daemon; do sleep 5; done

# Perform maintenance
# ...

# Restart
sudo systemctl start h2kvm-daemon
```

**Clear stuck jobs:**

```bash
# Pause daemon
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output pause

# Move stuck files
mv /var/lib/h2kvm/queue/stuck-file.vmdk /var/lib/h2kvm/queue/.errors/

# Resume
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output resume
```

**Database maintenance:**

```bash
# Vacuum deduplication database
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db "VACUUM;"

# Clean old records
sqlite3 /var/lib/h2kvm/output/.daemon/deduplication.db \
  "DELETE FROM processed_files WHERE processed_at < datetime('now', '-90 days');"
```

---

## Troubleshooting

### Common Issues

**Issue: Daemon won't start**

```bash
# Check systemd status
sudo systemctl status h2kvm-daemon

# View logs
sudo journalctl -u h2kvm-daemon -n 50

# Common causes:
# - Invalid configuration
# - Missing directories
# - Permission issues
# - Port conflicts
```

**Issue: Files not being processed**

```bash
# Check if daemon is paused
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status

# Check file stability timeout
# Files must be stable for file_stable_timeout seconds

# Check logs
sudo journalctl -u h2kvm-daemon -f | grep -i "queued\|processing"
```

**Issue: High failure rate**

```bash
# Check error files
ls -lh /var/lib/h2kvm/queue/.errors/

# Analyze common errors
jq -r '.error' /var/lib/h2kvm/queue/.errors/*.error.json | sort | uniq -c | sort -rn

# Common fixes:
# - Network connectivity issues
# - vSphere authentication
# - Disk space
# - Permission problems
```

**Issue: Slow processing**

```bash
# Check concurrent jobs
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats

# Increase workers if CPU/RAM available
# Edit /etc/h2kvm/daemon.yaml:
# max_concurrent_jobs: 5  # Increase from 3

# Restart daemon
sudo systemctl restart h2kvm-daemon
```

### Debug Mode

Enable verbose logging:

```yaml
# In /etc/h2kvm/daemon.yaml
verbose: 3  # Maximum verbosity
```

```bash
# Restart daemon
sudo systemctl restart h2kvm-daemon

# Watch detailed logs
sudo journalctl -u h2kvm-daemon -f
```

### Support Information

When reporting issues, collect:

```bash
# System info
uname -a
python3 --version
h2kvm --version

# Daemon status
sudo systemctl status h2kvm-daemon
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output status
h2kvmctl.cli.daemon_ctl --output-dir /var/lib/h2kvm/output stats

# Recent logs
sudo journalctl -u h2kvm-daemon -n 100 --no-pager

# Recent errors
ls -lh /var/lib/h2kvm/queue/.errors/
cat /var/lib/h2kvm/queue/.errors/recent-error.vmdk.error.json

# Configuration (redact passwords!)
cat /etc/h2kvm/daemon.yaml | grep -v password
```

---

**Document Version:** 1.0
**Last Updated:** 2026-03-29
**For:** h2kvm Enhanced Daemon Mode
