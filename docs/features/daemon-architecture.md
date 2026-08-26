# Integrated Daemon Architecture - h2kvm

## Overview

This document describes the integrated daemon architecture where the Go daemon (hypervisord) and Python daemon (h2kvm) work together to provide automated VM migration from vSphere to KVM.

**Vision:** Single command to migrate a VM from vSphere to KVM, fully automated.

```bash
# User runs one command
hyperctl convert --vm "production-db" --vcenter vcenter.example.com

# Behind the scenes:
# 1. hypervisord (Go) fetches VMDK from vSphere
# 2. h2kvm (Python) automatically converts it to KVM
# 3. VM is ready in libvirt
```

---

## Architecture Diagram

```mermaid
graph TB
    User[User]
    CLI[hyperctl - Control CLI<br/>• Parses user commands<br/>• Orchestrates workflow<br/>• Monitors progress]
    GoDaemon[hypervisord<br/>Go Daemon<br/>• vSphere export<br/>• Disk download<br/>• Queue management<br/>• Status API]
    PyDaemon[h2kvm daemon<br/>Python Daemon<br/>• Watches queue<br/>• Converts VMDKs<br/>• Applies VirtIO drivers<br/>• Control API]
    vSphere[vSphere Server<br/>• Source VMs<br/>• VMDK export]
    KVM[libvirt KVM<br/>• Converted VMs<br/>• Ready to run]

    User -->|hyperctl convert --vm "db-server"| CLI
    CLI -->|HTTP REST API| GoDaemon
    CLI -->|Unix Socket| PyDaemon
    GoDaemon -->|VMDK files| PyDaemon
    GoDaemon -->|govmomi SDK| vSphere
    PyDaemon -->|Converted VMs| KVM

    style User fill:#9C27B0,stroke:#6A1B9A,color:#fff
    style CLI fill:#FF9800,stroke:#E65100,color:#fff
    style GoDaemon fill:#2196F3,stroke:#1565C0,color:#fff
    style PyDaemon fill:#4CAF50,stroke:#2E7D32,color:#fff
    style vSphere fill:#607D8B,stroke:#37474F,color:#fff
    style KVM fill:#00BCD4,stroke:#006064,color:#fff
```

---

## Component Breakdown

### 1. hyperctl - Unified Control CLI

**Purpose:** Single entry point for all VM migration operations

**Features:**
- Convert VMs from vSphere with one command
- Monitor conversion progress
- Manage both daemons
- Query status and statistics
- Handle errors gracefully

**Commands:**
```bash
# Convert a VM from vSphere
hyperctl convert --vm "vm-name" --vcenter vcenter.example.com

# Convert with options
hyperctl convert --vm "vm-name" \
  --vcenter vcenter.example.com \
  --output-dir /var/lib/libvirt/images \
  --skip-network-fix \
  --to-libvirt

# Monitor conversion
hyperctl status --vm "vm-name"
hyperctl logs --vm "vm-name" --follow

# List all conversions
hyperctl list

# Daemon management
hyperctl daemon start --all
hyperctl daemon stop --all
hyperctl daemon status

# Statistics
hyperctl stats
hyperctl stats --daemon python
hyperctl stats --daemon go
```

**Implementation:** Python CLI tool using Click/Typer framework

---

### 2. hypervisord (hypervisord) - Export Orchestrator

**Current Features:**
- vSphere API integration
- VMDK export and download
- Queue management
- HTTP API for control

**New Features Needed:**
- **Webhook notifications** to Python daemon
- **Conversion queue integration**
- **Status tracking** for end-to-end flow
- **Automatic cleanup** of downloaded VMDKs after conversion

**API Endpoints:**

```go
// Existing
GET  /health              - Health check
GET  /status              - Daemon status
POST /export              - Export VM from vSphere

// New
POST /convert             - Export + trigger conversion
GET  /jobs                - List all jobs
GET  /jobs/{id}           - Job details
DELETE /jobs/{id}         - Cancel job
POST /jobs/{id}/retry     - Retry failed job
```

**Configuration:**
```yaml
# /etc/hypervisord/config.yaml
daemon:
  listen: "0.0.0.0:8080"
  work_dir: "/var/lib/hypervisord/work"

vsphere:
  server: "vcenter.example.com"
  vc_user: "automation@vsphere.local"
  password: "${VSPHERE_PASSWORD}"

conversion:
  # Automatically trigger Python daemon after export
  auto_convert: true

  # Python daemon connection
  python_daemon:
    queue_dir: "/var/lib/h2kvm/queue"
    control_socket: "/var/lib/h2kvm/output/.daemon/control.sock"

  # Cleanup after successful conversion
  cleanup_source: true
```

---

### 3. Python Daemon (h2kvm) - Conversion Engine

**Current Features:**
- Watch directory for VMDKs
- Automatic conversion
- VirtIO driver injection
- Retry mechanism
- Control API (Unix socket)
- Statistics tracking

**New Features Needed:**
- **Job queue API** (accept conversion requests)
- **Webhook callback** (notify Go daemon of completion)
- **Priority queue** (handle urgent conversions first)
- **Systemd integration** (auto-start, auto-restart)

**Configuration:**
```yaml
# /var/lib/h2kvm/daemon.yaml
command: daemon
daemon: true

# Directories
watch_dir: /var/lib/h2kvm/queue
output_dir: /var/lib/h2kvm/output
work_dir: /var/lib/h2kvm/work

# Conversion options
max_concurrent_jobs: 3
file_stable_timeout: 30

# Go daemon integration
go_daemon:
  # Notify Go daemon when conversion completes
  webhook_url: "http://localhost:8080/webhook/conversion-complete"

  # Cleanup options
  archive_processed: true
  notify_on_complete: true
  notify_on_failure: true

# Systemd integration
systemd:
  auto_restart: true
  restart_delay: 10
```

**New API Endpoints (Unix Socket):**
```python
# Existing
status          - Daemon status
stats           - Statistics
pause/resume    - Control processing
drain/stop      - Graceful shutdown

# New
queue-job       - Add conversion job to queue
list-jobs       - List all jobs
job-status      - Get job status
cancel-job      - Cancel job
set-priority    - Change job priority
```

---

### 4. Systemd Services

#### Python Daemon Service

**File:** `/etc/systemd/system/h2kvm-daemon.service`

```ini
[Unit]
Description=H2KVM Conversion Daemon
Documentation=https://github.com/ssahani/h2kvm
After=network.target libvirtd.service
Wants=libvirtd.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/var/lib/h2kvm

# Main service
ExecStart=/usr/local/bin/h2kvmctl --config /etc/h2kvm/daemon.yaml

# Graceful shutdown
ExecStop=/usr/bin/h2kvmctl.cli.daemon_ctl \
  --output-dir /var/lib/h2kvm/output drain
TimeoutStopSec=300

# Restart policy
Restart=always
RestartSec=10

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096
MemoryLimit=8G
CPUQuota=400%

# Security
NoNewPrivileges=false
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=h2kvm

[Install]
WantedBy=multi-user.target
```

#### hypervisord Service (Enhanced)

**File:** `/etc/systemd/system/hypervisord.service`

```ini
[Unit]
Description=H2KVM Export Daemon (Go)
Documentation=https://github.com/ssahani/h2kvm
After=network-online.target
Wants=network-online.target h2kvm-daemon.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/var/lib/hypervisord

# Main service
ExecStart=/usr/local/bin/hypervisord --config /etc/hypervisord/config.yaml

# Graceful shutdown
ExecStop=/bin/kill -SIGTERM $MAINPID
TimeoutStopSec=120

# Restart policy
Restart=always
RestartSec=10

# Resource limits
LimitNOFILE=65536
MemoryLimit=4G

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hypervisord

[Install]
WantedBy=multi-user.target
```

---

## Workflow: End-to-End VM Conversion

### User Command
```bash
hyperctl convert --vm "production-db" --vcenter vcenter.example.com
```

### Step-by-Step Flow

#### Phase 1: Command Parsing (hyperctl)
```
1. hyperctl receives command
2. Validates parameters (VM name, vCenter, credentials)
3. Checks if both daemons are running
4. If Python daemon not running, starts it via systemd
5. Generates unique job ID: job-abc123
6. Sends request to Go daemon
```

#### Phase 2: Export (hypervisord)
```
7. Go daemon receives export request
8. Connects to vSphere API
9. Locates VM "production-db"
10. Exports VMDK to /var/lib/hypervisord/work/job-abc123/
11. Downloads VMDK (progress tracked)
12. Verifies VMDK integrity (MD5/SHA256)
13. Copies VMDK to Python daemon queue: /var/lib/h2kvm/queue/
14. Sends webhook to Python daemon (optional)
15. Updates job status: "exported, queued for conversion"
```

#### Phase 3: Conversion (Python Daemon)
```
16. Python daemon detects new VMDK in queue/
17. Waits for file stability (file_stable_timeout)
18. Queues file for processing
19. Worker picks up job
20. Runs conversion pipeline:
    - Detect guest OS
    - Inject VirtIO drivers
    - Update bootloader
    - Fix network configuration
    - Update fstab
21. Archives original VMDK to .processed/
22. Updates statistics
23. Sends webhook to Go daemon: "conversion complete"
24. Updates job status: "completed"
```

#### Phase 4: Notification (hyperctl)
```
25. hyperctl polls job status
26. Shows real-time progress
27. Displays completion message
28. Shows libvirt import command
```

### Progress Output Example

```bash
$ hyperctl convert --vm "production-db" --vcenter vcenter.example.com

🚀 Starting VM conversion
Job ID: job-abc123

Phase 1: Connecting to vSphere
  ✅ Connected to vcenter.example.com
  ✅ Found VM: production-db (3 disks, 250 GB total)

Phase 2: Exporting from vSphere
  📥 Downloading disk 1/3: production-db.vmdk
  [████████████████████████████████] 100% (85.2 GB) - ETA: 0s
  ✅ Disk 1 downloaded (2m 15s)

  📥 Downloading disk 2/3: production-db_1.vmdk
  [████████████████████████████████] 100% (120.5 GB) - ETA: 0s
  ✅ Disk 2 downloaded (3m 42s)

  📥 Downloading disk 3/3: production-db_2.vmdk
  [████████████████████████████████] 100% (44.3 GB) - ETA: 0s
  ✅ Disk 3 downloaded (1m 28s)

Phase 3: Queued for conversion
  ⏳ Waiting in conversion queue (position: 2)
  ⏳ Queue position: 1
  ▶️  Conversion started

Phase 4: Converting to KVM
  🔍 Detected: Red Hat Enterprise Linux 8.9
  🧬 Filesystem: xfs (LVM)
  💉 Injecting VirtIO drivers...
  [████████████████████████████████] 100% - dracut complete
  ✅ VirtIO drivers injected

  🥾 Updating bootloader...
  ✅ GRUB2 updated

  🌐 Fixing network configuration...
  ✅ Network configured for KVM

  📦 Finalizing...
  ✅ Conversion complete (4m 32s)

Phase 5: Cleanup
  🧹 Archiving source VMDK
  ✅ Cleanup complete

╔══════════════════════════════════════════════════════════╗
║              ✅ Conversion Successful                    ║
╚══════════════════════════════════════════════════════════╝

Job ID:        job-abc123
Source VM:     production-db (vSphere)
Total Size:    250 GB
Total Time:    12m 57s
Output:        /var/lib/h2kvm/output/2026-01-17/production-db/

Next steps:

1. Import to libvirt:
   hyperctl import --job job-abc123

2. Or manually:
   virt-install --name production-db \
     --disk /var/lib/h2kvm/output/2026-01-17/production-db/disk1.vmdk \
     --disk /var/lib/h2kvm/output/2026-01-17/production-db/disk2.vmdk \
     --disk /var/lib/h2kvm/output/2026-01-17/production-db/disk3.vmdk \
     --memory 16384 --vcpus 8 --import

3. View logs:
   hyperctl logs --job job-abc123
```

---

## Communication Protocols

### hyperctl → hypervisord (HTTP REST API)

**Convert Request:**
```http
POST /api/v1/convert
Content-Type: application/json

{
  "vm_name": "production-db",
  "vcenter": {
    "server": "vcenter.example.com",
    "username": "automation@vsphere.local",
    "password": "password",
    "datacenter": "DC1"
  },
  "options": {
    "auto_convert": true,
    "priority": "normal",
    "notify_email": "ops@company.com"
  }
}
```

**Response:**
```json
{
  "job_id": "job-abc123",
  "status": "started",
  "vm_name": "production-db",
  "disks": [
    {
      "name": "production-db.vmdk",
      "size_gb": 85.2,
      "status": "queued"
    },
    {
      "name": "production-db_1.vmdk",
      "size_gb": 120.5,
      "status": "queued"
    }
  ],
  "created_at": "2026-01-17T10:00:00Z",
  "estimated_duration": "8m 30s"
}
```

**Status Query:**
```http
GET /api/v1/jobs/job-abc123
```

**Response:**
```json
{
  "job_id": "job-abc123",
  "status": "converting",
  "phase": "conversion",
  "progress": {
    "phase": "conversion",
    "current_disk": 2,
    "total_disks": 3,
    "percent_complete": 67,
    "eta_seconds": 180
  },
  "export": {
    "status": "completed",
    "duration": "7m 25s",
    "bytes_downloaded": 268435456000
  },
  "conversion": {
    "status": "in_progress",
    "current_step": "injecting_virtio_drivers",
    "steps_completed": 3,
    "steps_total": 5
  }
}
```

### hypervisord → Python Daemon (File System + Webhook)

**Method 1: File System (Primary)**
```bash
# Go daemon copies VMDK to Python daemon queue
cp /var/lib/hypervisord/work/job-abc123/disk.vmdk \
   /var/lib/h2kvm/queue/

# Python daemon auto-detects via watchdog
```

**Method 2: Webhook (Optional Notification)**
```http
POST http://localhost:9000/webhook/new-job
Content-Type: application/json

{
  "job_id": "job-abc123",
  "vm_name": "production-db",
  "files": [
    "/var/lib/h2kvm/queue/production-db.vmdk",
    "/var/lib/h2kvm/queue/production-db_1.vmdk"
  ],
  "priority": "normal",
  "callback_url": "http://localhost:8080/webhook/conversion-complete"
}
```

### Python Daemon → hypervisord (Webhook Callback)

**Conversion Complete:**
```http
POST http://localhost:8080/webhook/conversion-complete
Content-Type: application/json

{
  "job_id": "job-abc123",
  "status": "success",
  "vm_name": "production-db",
  "output_dir": "/var/lib/h2kvm/output/2026-01-17/production-db",
  "files": [
    "/var/lib/h2kvm/output/2026-01-17/production-db/disk1.vmdk",
    "/var/lib/h2kvm/output/2026-01-17/production-db/disk2.vmdk"
  ],
  "duration_seconds": 272,
  "modifications": {
    "virtio_drivers": true,
    "bootloader_updated": true,
    "network_fixed": true
  }
}
```

**Conversion Failed:**
```http
POST http://localhost:8080/webhook/conversion-complete
Content-Type: application/json

{
  "job_id": "job-abc123",
  "status": "failed",
  "vm_name": "production-db",
  "error": "Failed to inject VirtIO drivers: missing kernel modules",
  "error_file": "/var/lib/h2kvm/queue/.errors/production-db.vmdk.error.json",
  "retry_count": 1,
  "retry_available": true
}
```

### hyperctl → Python Daemon (Unix Socket)

**Queue Job:**
```python
# hyperctl sends to Python daemon control socket
{
  "command": "queue-job",
  "job_id": "job-abc123",
  "file": "/var/lib/h2kvm/queue/production-db.vmdk",
  "priority": "high",
  "options": {
    "fix_fstab": true,
    "fix_grub": true,
    "fix_network": true
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Job queued",
  "queue_position": 2,
  "estimated_start": "2026-01-17T10:05:00Z"
}
```

---

## Database Schema (Job Tracking)

### hypervisord (SQLite)

**Table: jobs**
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,                    -- job-abc123
    vm_name TEXT NOT NULL,                  -- production-db
    vcenter_server TEXT NOT NULL,           -- vcenter.example.com

    -- Status
    status TEXT NOT NULL,                   -- pending, exporting, exported, converting, completed, failed
    phase TEXT NOT NULL,                    -- export, conversion, cleanup

    -- Export details
    export_started_at TIMESTAMP,
    export_completed_at TIMESTAMP,
    export_duration_seconds INTEGER,
    bytes_downloaded INTEGER,

    -- Conversion details
    conversion_started_at TIMESTAMP,
    conversion_completed_at TIMESTAMP,
    conversion_duration_seconds INTEGER,
    conversion_status TEXT,                 -- queued, converting, completed, failed

    -- Files
    source_files JSON,                      -- List of VMDKs
    output_dir TEXT,                        -- /var/lib/h2kvm/output/2026-01-17/production-db

    -- Metadata
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,

    -- Error handling
    error TEXT,
    retry_count INTEGER DEFAULT 0,

    -- User info
    requested_by TEXT,
    priority TEXT DEFAULT 'normal'         -- low, normal, high
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
```

### Python Daemon (Existing deduplication.db)

**Enhanced Table: processed_files**
```sql
ALTER TABLE processed_files ADD COLUMN job_id TEXT;
ALTER TABLE processed_files ADD COLUMN priority TEXT DEFAULT 'normal';
ALTER TABLE processed_files ADD COLUMN conversion_duration INTEGER;

CREATE INDEX idx_job_id ON processed_files(job_id);
```

---

## Error Handling & Retry Logic

### Export Failures (hypervisord)

**Retry Policy:**
```yaml
retry_policy:
  max_retries: 3
  retry_delay: 300          # 5 minutes
  backoff_multiplier: 2.0

  # Retry on these errors
  retryable_errors:
    - "connection timeout"
    - "network unreachable"
    - "temporary failure"

  # Don't retry on these
  permanent_errors:
    - "VM not found"
    - "authentication failed"
    - "insufficient permissions"
```

**Error Handling:**
```go
func (d *Daemon) handleExportError(jobID string, err error) {
    if isRetryable(err) && job.RetryCount < MaxRetries {
        // Schedule retry
        delay := calculateBackoff(job.RetryCount)
        d.scheduleRetry(jobID, delay)
    } else {
        // Mark as permanently failed
        d.markJobFailed(jobID, err)

        // Notify user
        d.sendNotification(jobID, "failed", err.Error())
    }
}
```

### Conversion Failures (Python Daemon)

**Already Implemented:**
- Automatic retry with exponential backoff
- Error context generation
- File moved to `.errors/` directory

**Enhanced with Job ID tracking:**
```python
def handle_conversion_error(self, job_id: str, filename: str, error: Exception):
    # Create error context
    error_context = {
        'job_id': job_id,
        'filename': filename,
        'error': str(error),
        'traceback': traceback.format_exc(),
        'phase': self.current_phase,
        'timestamp': datetime.now().isoformat()
    }

    # Save error file
    error_file = self.queue_dir / '.errors' / f'{filename}.error.json'
    with open(error_file, 'w') as f:
        json.dump(error_context, f, indent=2)

    # Notify Go daemon
    if self.go_daemon_webhook:
        self.notify_conversion_failed(job_id, error_context)

    # Check retry
    if self.retry_manager.should_retry(filename):
        self.retry_manager.schedule_retry(filename, job_id)
```

---

## Monitoring & Observability

### Metrics (Prometheus Format)

**hypervisord:**
```
# Export metrics
hypervisord_exports_total{status="success"} 145
hypervisord_exports_total{status="failed"} 3
hypervisord_export_duration_seconds{quantile="0.5"} 420
hypervisord_export_duration_seconds{quantile="0.99"} 1200
hypervisord_bytes_downloaded_total 1.5e12

# Job queue
hypervisord_queue_depth{priority="high"} 2
hypervisord_queue_depth{priority="normal"} 5
hypervisord_queue_depth{priority="low"} 1
```

**Python Daemon:**
```
# Conversion metrics
h2kvm_conversions_total{status="success"} 142
h2kvm_conversions_total{status="failed"} 3
h2kvm_conversion_duration_seconds{quantile="0.5"} 45
h2kvm_conversion_duration_seconds{quantile="0.99"} 180

# Queue metrics
h2kvm_queue_depth 3
h2kvm_active_conversions 2
```

### Health Checks

**hypervisord:**
```http
GET /health

{
  "status": "healthy",
  "uptime_seconds": 86400,
  "vsphere_connection": "ok",
  "python_daemon_reachable": true,
  "disk_space_available_gb": 500,
  "active_jobs": 3
}
```

**Python Daemon:**
```bash
$ sudo h2kvmctl.cli.daemon_ctl status --json

{
  "status": "running",
  "paused": false,
  "uptime_hours": 24.5,
  "queue_depth": 3,
  "active_conversions": 2,
  "disk_space_gb": 450
}
```

---

## Security Considerations

### Authentication & Authorization

**vSphere Credentials:**
```yaml
# Use environment variables
vsphere:
  server: "vcenter.example.com"
  vc_user: "${VSPHERE_USERNAME}"
  password: "${VSPHERE_PASSWORD}"

# Or use credential file with restricted permissions
vsphere:
  credentials_file: "/etc/hypervisord/vsphere-credentials.yaml"
  # File must be 0600 (read-write owner only)
```

**Unix Socket Permissions:**
```bash
# Python daemon control socket
/var/lib/h2kvm/output/.daemon/control.sock
srwxr-x--- 1 root h2kvm 0 Jan 17 10:00 control.sock

# Only root and h2kvm group can access
```

**API Authentication (hypervisord):**
```yaml
api:
  listen: "127.0.0.1:8080"  # Localhost only by default

  # Optional: Token-based auth
  auth:
    enabled: true
    token: "${API_TOKEN}"
```

### File System Security

**Work Directories:**
```bash
# Restrict permissions
chmod 700 /var/lib/hypervisord/work
chmod 700 /var/lib/h2kvm/queue
chmod 700 /var/lib/h2kvm/output

# SELinux contexts (RHEL/CentOS)
semanage fcontext -a -t virt_image_t "/var/lib/h2kvm/output(/.*)?"
restorecon -Rv /var/lib/h2kvm/
```

---

## Deployment Guide

### Installation

**1. Install Prerequisites:**
```bash
# Python daemon
sudo pip3 install h2kvm

# Go daemon
sudo wget https://github.com/ssahani/hypersdk/releases/latest/download/hypervisord
sudo chmod +x hypervisord
sudo mv hypervisord /usr/local/bin/

# Control CLI
sudo pip3 install hyperctl  # To be created
```

**2. Create Directories:**
```bash
# Go daemon
sudo mkdir -p /var/lib/hypervisord/work
sudo mkdir -p /etc/hypervisord

# Python daemon
sudo mkdir -p /var/lib/h2kvm/{queue,output,work}
sudo mkdir -p /etc/h2kvm

# Logs
sudo mkdir -p /var/log/h2kvm
```

**3. Install Systemd Services:**
```bash
# Copy service files
sudo cp hypervisord.service /etc/systemd/system/
sudo cp h2kvm-daemon.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable hypervisord
sudo systemctl enable h2kvm-daemon

# Start services
sudo systemctl start hypervisord
sudo systemctl start h2kvm-daemon
```

**4. Verify:**
```bash
# Check status
sudo systemctl status hypervisord
sudo systemctl status h2kvm-daemon

# Check logs
sudo journalctl -u hypervisord -f
sudo journalctl -u h2kvm-daemon -f

# Test CLI
hyperctl daemon status
```

---

## Usage Examples

### Example 1: Convert Single VM

```bash
hyperctl convert \
  --vm "web-server-01" \
  --vcenter vcenter.example.com \
  --username admin@vsphere.local \
  --datacenter DC1

# Output:
# Job ID: job-xyz789
# Status: Export started...
# Follow progress: hyperctl status --job job-xyz789
```

### Example 2: Batch Convert Multiple VMs

```bash
# Create batch file
cat > vms.txt <<EOF
web-server-01
web-server-02
db-server-primary
db-server-standby
EOF

# Convert all
hyperctl convert --batch vms.txt --vcenter vcenter.example.com

# Or use parallel mode
hyperctl convert --batch vms.txt --parallel 3
```

### Example 3: Convert with Custom Options

```bash
hyperctl convert \
  --vm "production-db" \
  --vcenter vcenter.example.com \
  --priority high \
  --output-dir /mnt/fast-storage/vms \
  --fix-network \
  --fix-fstab \
  --fix-grub \
  --notify ops@company.com \
  --tags "production,database,critical"
```

### Example 4: Monitor Progress

```bash
# Real-time progress
hyperctl status --job job-abc123 --follow

# View logs
hyperctl logs --job job-abc123 --tail 50

# List all jobs
hyperctl list

# Filter by status
hyperctl list --status converting
hyperctl list --status failed
```

### Example 5: Retry Failed Job

```bash
# List failed jobs
hyperctl list --status failed

# Retry specific job
hyperctl retry --job job-abc123

# Retry all failed jobs
hyperctl retry --all-failed
```

---

## Configuration Reference

### hyperctl Configuration

**File:** `~/.config/h2kvm/config.yaml`

```yaml
# Daemon endpoints
daemons:
  go:
    url: "http://localhost:8080"
    timeout: 30
  python:
    socket: "/var/lib/h2kvm/output/.daemon/control.sock"
    timeout: 10

# Default vCenter
vsphere:
  server: "vcenter.example.com"
  vc_user: "automation@vsphere.local"
  dc_name: "DC1"
  # Password: use env var VSPHERE_PASSWORD

# Conversion defaults
conversion:
  # network is auto-handled
  fstab_mode: stabilize-all
  # grub is auto-handled
  output_dir: "/var/lib/h2kvm/output"

# Notifications
notifications:
  email: "ops@company.com"
  slack_webhook: "https://hooks.slack.com/..."

# UI preferences
ui:
  show_progress: true
  color: true
  log_level: "info"
```

---

## Next Steps

1. **Implement hyperctl CLI** (Priority 1)
2. **Enhance Go daemon** with conversion API (Priority 1)
3. **Enhance Python daemon** with job queue API (Priority 2)
4. **Create systemd services** (Priority 1)
5. **Add webhook communication** (Priority 2)
6. **Write integration tests** (Priority 3)
7. **Create user documentation** (Priority 3)

---

**Document Version:** 1.0
**Date:** 2026-01-17
**Status:** Design Complete - Ready for Implementation
