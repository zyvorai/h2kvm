# HyperSDK Integration - Quick Start Guide

**5-Minute Setup Guide** - Get started with HyperSDK workflow integration

---

## Prerequisites

- h2kvm installed (`make install` puts binaries in `/usr/bin`)
- HyperSDK repository cloned
- Go 1.19+ installed
- Python 3.8+ installed

> **Note:** The daemon workflow only accepts Artifact Manifest v1.0 (`"manifest_version": "1.0"`). Legacy manifest formats are no longer supported. Windows WinRM connectivity uses a native Go library; no external WinRM binary is required.

---

## 1. Build HyperCTL

```bash
cd /home/ssahani/go/github/hypersdk/cmd/hyperctl
go build -o hyperctl .
```

**Verify:**
```bash
./hyperctl workflow --help
./hyperctl manifest --help
```

---

## 2. Set Up Workflow Directories

```bash
sudo mkdir -p /var/lib/h2kvm/manifest-workflow/{to_be_processed,processing,processed,failed}
sudo mkdir -p /var/lib/h2kvm/output
sudo chown -R $(whoami):$(whoami) /var/lib/h2kvm
```

---

## 3. Create Daemon Config

```bash
cat > /tmp/manifest-daemon.yaml <<EOF
command: daemon
daemon: true
manifest_workflow_mode: true
manifest_workflow_dir: /var/lib/h2kvm/manifest-workflow
output_dir: /var/lib/h2kvm/output
max_concurrent_jobs: 3
verbose: 2
log_file: /tmp/workflow-daemon.log
EOF
```

---

## 4. Create a Test Manifest

```bash
cat > /tmp/test-vm.json <<'EOF'
{
  "manifest_version": "1.0",
  "pipeline": {
    "load": {
      "source_type": "vmdk",
      "source_path": "/path/to/your/vm.vmdk"
    },
    "inspect": {
      "enabled": true,
      "detect_os": true
    },
    "fix": {
      "fstab": {"enabled": true, "mode": "stabilize-all"},
      "grub": {"enabled": true},
      "initramfs": {"enabled": true, "regenerate": true}
    },
    "convert": {
      "output_format": "qcow2",
      "compress": true
    }
  }
}
EOF
```

**Update the `source_path` to point to a real VM disk!**

---

## 5. Test the Integration

### Option A: File-Based Workflow

```bash
# Start daemon (in terminal 1)
h2kvmctl --config /tmp/manifest-daemon.yaml

# Submit manifest (in terminal 2)
cp /tmp/test-vm.json /var/lib/h2kvm/manifest-workflow/to_be_processed/

# Watch progress
watch -n 1 'ls -lR /var/lib/h2kvm/manifest-workflow/'
```

### Option B: Using HyperCTL

```bash
# Check workflow status
/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl workflow -op status

# Validate manifest
/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl manifest validate -file /tmp/test-vm.json

# Submit manifest (requires HyperSDK daemon running)
/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl manifest submit -file /tmp/test-vm.json
```

### Option C: Using Web Dashboard

```bash
# Start HyperSDK daemon
cd /home/ssahani/go/github/hypersdk
go run ./cmd/daemon --config config.yaml

# Open browser
firefox http://localhost:8080/web/dashboard/
```

---

## 6. Monitor Results

### Check Processing Status

```bash
# Via CLI
ls -la /var/lib/h2kvm/manifest-workflow/processing/

# Via HyperCTL
/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl workflow -op list
```

### View Completed Jobs

```bash
# List completed
ls -la /var/lib/h2kvm/manifest-workflow/processed/

# View processing report
cat /var/lib/h2kvm/manifest-workflow/processed/*/your-manifest.json.report.json
```

### Check Failed Jobs

```bash
# List failed
ls -la /var/lib/h2kvm/manifest-workflow/failed/

# View error details
cat /var/lib/h2kvm/manifest-workflow/failed/*/your-manifest.json.error.json
```

---

## 7. Common Commands

### HyperCTL Workflow Commands

```bash
HYPERCTL="/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl"

# Workflow operations
$HYPERCTL workflow -op status      # Daemon status
$HYPERCTL workflow -op list        # List all jobs
$HYPERCTL workflow -op queue       # Queue statistics
$HYPERCTL workflow -op watch       # Real-time monitoring

# Manifest operations
$HYPERCTL manifest create          # Interactive builder
$HYPERCTL manifest validate -file <manifest.json>
$HYPERCTL manifest submit -file <manifest.json>
$HYPERCTL manifest generate <vm-path> <output-dir>
```

### API Commands

```bash
# Status
curl http://localhost:8080/api/workflow/status | jq

# List jobs
curl http://localhost:8080/api/workflow/jobs | jq

# Active jobs
curl http://localhost:8080/api/workflow/jobs/active | jq

# Submit manifest
curl -X POST http://localhost:8080/api/workflow/manifest/submit \
  -H "Content-Type: application/json" \
  -d @test-vm.json | jq

# Validate manifest
curl -X POST http://localhost:8080/api/workflow/manifest/validate \
  -H "Content-Type: application/json" \
  -d @test-vm.json | jq
```

---

## 8. Example Batch Manifest

For processing multiple VMs:

```json
{
  "manifest_version": "1.0",
  "batch": true,
  "vms": [
    {
      "name": "web-server-1",
      "pipeline": {
        "load": {
          "source_type": "vmdk",
          "source_path": "/vms/web1.vmdk"
        },
        "fix": {
          "fstab": {"enabled": true, "mode": "stabilize-all"}
        },
        "convert": {
          "output_format": "qcow2",
          "compress": true
        }
      }
    },
    {
      "name": "web-server-2",
      "pipeline": {
        "load": {
          "source_type": "vmdk",
          "source_path": "/vms/web2.vmdk"
        },
        "fix": {
          "fstab": {"enabled": true, "mode": "stabilize-all"}
        },
        "convert": {
          "output_format": "qcow2",
          "compress": true
        }
      }
    }
  ]
}
```

---

## 9. Troubleshooting

### Daemon Won't Start

```bash
# Check Python module
h2kvmctl --version

# Check directories exist
ls -la /var/lib/h2kvm/manifest-workflow/

# Check logs
tail -f /tmp/workflow-daemon.log
```

### Manifests Not Processing

```bash
# Check daemon is running
ps aux | grep h2kvm

# Check file permissions
ls -la /var/lib/h2kvm/manifest-workflow/to_be_processed/

# Check daemon logs
tail -f /tmp/workflow-daemon.log
```

### API Connection Refused

```bash
# Ensure HyperSDK daemon is running
curl http://localhost:8080/health

# Start HyperSDK daemon if needed
cd /home/ssahani/go/github/hypersdk
go run ./cmd/daemon --config config.yaml
```

---

## 10. Next Steps

### Try the Demo

```bash
cd /home/ssahani/tt/h2kvm
./demo_hypersdk_integration.sh
```

### Run Integration Tests

```bash
cd /home/ssahani/tt/h2kvm
./test_hypersdk_integration.sh
```

### Read Full Documentation

- **Integration Guide:** `HYPERSDK_INTEGRATION.md`
- **Test Report:** `INTEGRATION_TEST_REPORT.md`
- **Success Summary:** `HYPERSDK_INTEGRATION_SUCCESS.md`

---

## 📁 File Locations

| File | Location |
|------|----------|
| **HyperCTL** | `/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl` |
| **Workflow Dirs** | `/var/lib/h2kvm/manifest-workflow/` |
| **Output Dirs** | `/var/lib/h2kvm/output/` |
| **Example Manifests** | `/home/ssahani/tt/h2kvm/examples/manifest-workflow/` |
| **Test Scripts** | `/home/ssahani/tt/h2kvm/test_*.sh` |
| **Demo Script** | `/home/ssahani/tt/h2kvm/demo_*.sh` |

---

## ✅ Success Checklist

After following this guide, you should have:

- [ ] HyperCTL built and working
- [ ] Workflow directories created
- [ ] Daemon configuration created
- [ ] Test manifest created
- [ ] Daemon running and processing manifests
- [ ] Able to monitor via CLI/API/Web

---

**Need Help?**

Check the comprehensive documentation:
- `HYPERSDK_INTEGRATION.md` - Full integration guide
- `INTEGRATION_TEST_REPORT.md` - Detailed test results
- `HYPERSDK_INTEGRATION_SUCCESS.md` - Complete feature list

**Quick Commands Reference:**
```bash
# Build
cd /home/ssahani/go/github/hypersdk/cmd/hyperctl && go build .

# Start daemon
h2kvmctl --config /tmp/manifest-daemon.yaml

# Submit manifest
cp manifest.json /var/lib/h2kvm/manifest-workflow/to_be_processed/

# Monitor
./hyperctl workflow -op watch
```

---

**Quick Start Complete!** 🚀

You now have a working HyperSDK + h2kvm workflow integration.
