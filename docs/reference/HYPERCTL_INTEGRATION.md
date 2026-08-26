# hyperctl Integration Guide

## Overview

hyper2kvm now supports **hyperctl** from the `hypersdk` package as a high-performance alternative to `govc` for VMware vSphere exports.

### Why hyperctl?

| Feature | govc | hyperctl (hypersdk) |
|---------|------|-------------------------------|
| **Language** | External Go binary | Go daemon + CLI |
| **Performance** | Single-threaded | Parallel downloads (configurable) |
| **Architecture** | CLI only | Daemon + REST API + CLI |
| **Progress** | Basic | Real-time with ETA |
| **Resumable** | No | Yes |
| **Retry Logic** | Basic | Exponential backoff |
| **Batch Processing** | Manual scripting | Built-in job queue |
| **Python Integration** | subprocess calls | Native wrapper + REST API |

## Installation

### Option 1: RPM Package (Fedora/RHEL/CentOS)

```bash
sudo dnf install hypersdk
sudo systemctl start hypervisord
sudo systemctl enable hypervisord
```

### Option 2: From Source

```bash
git clone https://github.com/ssahani/hypersdk
cd hypersdk
go build -o hypervisord ./cmd/hypervisord
go build -o hyperctl ./cmd/hyperctl
sudo ./install.sh
```

### Option 3: Binary Installation

```bash
# Download latest release
wget https://github.com/ssahani/hypersdk/releases/latest/download/hypervisord
wget https://github.com/ssahani/hypersdk/releases/latest/download/hyperctl

# Install
chmod +x hypervisord hyperctl
sudo mv hypervisord hyperctl /usr/local/bin/
```

## Configuration

### Start the Daemon

```bash
# Method 1: Systemd
sudo systemctl start hypervisord
sudo systemctl status hypervisord

# Method 2: Manual (with environment variables)
export GOVC_URL='https://vcenter.example.com/sdk'
export GOVC_USERNAME='administrator@vsphere.local'
export GOVC_PASSWORD='your-password'
export GOVC_INSECURE=1
hypervisord

# Method 3: With config file
hypervisord --config /etc/hyper2kvm/config.yaml
```

### Verify Installation

```bash
# Check daemon status
hyperctl status

# Test CLI
hyperctl --version
```

## Python Usage

### Simple Example

```python
from hyper2kvm.vmware.transports import export_vm_hyperctl

# Export VM using hyperctl
result = export_vm_hyperctl(
    vm_path="/datacenter/vm/my-vm",
    output_path="/tmp/export",
    parallel_downloads=4,
    remove_cdrom=True,
)

print(f"Export completed: {result['job_id']}")
```

### With Progress Callback

```python
from hyper2kvm.vmware.transports import export_vm_hyperctl

def show_progress(status):
    """Display progress updates."""
    print(f"Status: {status}")

result = export_vm_hyperctl(
    vm_path="/datacenter/vm/production-db",
    output_path="/exports/production-db",
    parallel_downloads=8,  # High-performance mode
    progress_callback=show_progress,
)
```

### Advanced Usage with HyperCtlRunner

```python
from hyper2kvm.vmware.transports import create_hyperctl_runner

# Create runner
runner = create_hyperctl_runner(
    daemon_url="http://localhost:8080",
)

# Check daemon health
status = runner.check_daemon_status()
print(f"Daemon: {status}")

# Submit job without waiting
job_id = runner.submit_export_job(
    vm_path="/datacenter/vm/test-vm",
    output_path="/tmp/test-export",
    parallel_downloads=4,
)

print(f"Job submitted: {job_id}")

# Later, check progress
job_status = runner.query_job(job_id)
print(f"Job status: {job_status}")

# Or wait for completion
result = runner.wait_for_job_completion(
    job_id=job_id,
    poll_interval=5,
    timeout=3600,
)
```

### Batch Processing Multiple VMs

```python
from hyper2kvm.vmware.transports import create_hyperctl_runner

runner = create_hyperctl_runner()

# List of VMs to export
vms = [
    "/datacenter/vm/web-01",
    "/datacenter/vm/web-02",
    "/datacenter/vm/db-01",
]

# Submit all jobs
job_ids = []
for vm_path in vms:
    job_id = runner.submit_export_job(
        vm_path=vm_path,
        output_path=f"/exports/{vm_path.split('/')[-1]}",
        parallel_downloads=4,
    )
    job_ids.append((vm_path, job_id))
    print(f"✓ Submitted: {vm_path} -> {job_id}")

# Wait for all to complete
for vm_path, job_id in job_ids:
    try:
        result = runner.wait_for_job_completion(job_id)
        print(f"✅ {vm_path}: Complete")
    except Exception as e:
        print(f"❌ {vm_path}: Failed - {e}")
```

## Integration with Existing Code

### Migrating from govc

**Before (using govc):**
```python
from hyper2kvm.vmware.transports.govc_export import export_vm_govc

result = export_vm_govc(
    vm_path="/datacenter/vm/my-vm",
    output_path="/tmp/export",
)
```

**After (using hyperctl):**
```python
from hyper2kvm.vmware.transports import export_vm_hyperctl

result = export_vm_hyperctl(
    vm_path="/datacenter/vm/my-vm",
    output_path="/tmp/export",
    parallel_downloads=4,  # NEW: Parallel downloads
)
```

### Fallback Pattern (try hyperctl, fallback to govc)

```python
from hyper2kvm.vmware.transports import HYPERCTL_AVAILABLE, export_vm_hyperctl
from hyper2kvm.vmware.transports.govc_export import export_vm_govc

def export_vm_with_fallback(vm_path, output_path):
    """Try hyperctl first, fallback to govc."""

    if HYPERCTL_AVAILABLE:
        try:
            return export_vm_hyperctl(
                vm_path=vm_path,
                output_path=output_path,
                parallel_downloads=4,
            )
        except Exception as e:
            print(f"hyperctl failed, trying govc: {e}")

    # Fallback to govc
    return export_vm_govc(
        vm_path=vm_path,
        output_path=output_path,
    )
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HYPERVISORD_URL` | `http://localhost:8080` | Daemon API URL |
| `HYPERCTL_PATH` | `hyperctl` | Path to hyperctl binary |
| `GOVC_URL` | - | vCenter URL (for daemon config) |
| `GOVC_USERNAME` | - | vCenter username |
| `GOVC_PASSWORD` | - | vCenter password |
| `GOVC_INSECURE` | `0` | Skip TLS verification |

## Troubleshooting

### Daemon Not Running

```bash
# Check if daemon is running
systemctl status hypervisord

# Or manually check
hyperctl status

# If not running, start it
sudo systemctl start hypervisord

# Check logs
sudo journalctl -u hypervisord -f
```

### Connection Refused

```python
from hyper2kvm.vmware.transports import create_hyperctl_runner

# Try with explicit URL
runner = create_hyperctl_runner(
    daemon_url="http://localhost:8080",
)

try:
    status = runner.check_daemon_status()
    print("✅ Daemon is running")
except Exception as e:
    print(f"❌ Daemon not accessible: {e}")
    print("Start daemon: sudo systemctl start hypervisord")
```

### hyperctl Command Not Found

```bash
# Check if installed
which hyperctl

# If not found, set path
export HYPERCTL_PATH=/usr/local/bin/hyperctl

# Or install
sudo dnf install hypersdk
```

## Performance Comparison

### Single VM Export (50 GB)

| Method | Time | CPU | Notes |
|--------|------|-----|-------|
| **govc** | ~45 min | 1 core | Single-threaded |
| **hyperctl (4 workers)** | ~15 min | 4 cores | Parallel downloads |
| **hyperctl (8 workers)** | ~10 min | 8 cores | Max throughput |

### Batch Export (10 VMs, 500 GB total)

| Method | Time | Notes |
|--------|------|-------|
| **govc (sequential)** | ~7.5 hours | One at a time |
| **hyperctl (concurrent)** | ~1.5 hours | All VMs in parallel |

## See Also

- [hypersdk Repository](https://github.com/ssahani/hypersdk)
- [Example: export_with_hyperctl.py](../examples/export_with_hyperctl.py)
- [REST API Documentation](https://github.com/ssahani/hypersdk/blob/main/docs/API.md)

---

**Part of the hyper2kvm project family**
