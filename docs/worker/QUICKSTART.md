# Worker Job Protocol - Quick Start Guide

Get up and running with the hyper2kvm Worker Job Protocol in 5 minutes.

---

## Step 1: Check Your Environment

```bash
cd /home/ssahani/tt/hyper2kvm
h2kvmctl.worker.cli capabilities
```

This shows:
- Execution mode (host, safe_container, or privileged_container)
- Available capabilities (NBD, LVM, mount, SELinux, qemu-img)
- System resources

---

## Step 2: Create a Job Specification

Create `my-job.json`:

```json
{
  "version": "1.0",
  "job_id": "my-first-job",
  "operation": "inspect",
  "image": {
    "path": "/path/to/your/vm.qcow2",
    "format": "qcow2"
  },
  "artifacts": {
    "output_path": "/tmp/worker-output"
  },
  "audit": {
    "requested_by": "quickstart-guide"
  }
}
```

---

## Step 3: Run the Job

```bash
h2kvmctl.worker.cli run my-job.json --follow
```

You'll see:
- Real-time progress bar
- Phase-by-phase execution
- Final result

---

## Step 4: Check the Results

```bash
# View job status
h2kvmctl.worker.cli status my-first-job

# View events
h2kvmctl.worker.cli events my-first-job

# Check output
ls -lh /tmp/worker-output/
```

---

## Next Steps

### Try Format Conversion

```json
{
  "version": "1.0",
  "job_id": "convert-job",
  "operation": "convert",
  "image": {
    "path": "/path/to/vm.vmdk",
    "format": "vmdk"
  },
  "parameters": {
    "output_format": "qcow2",
    "compress": true
  },
  "artifacts": {
    "output_path": "/tmp/converted"
  },
  "audit": {
    "requested_by": "quickstart"
  }
}
```

Run it:
```bash
h2kvmctl.worker.cli run convert-job.json --follow
```

### Run the Example Script

```bash
python3 examples/worker_example.py
```

This demonstrates:
- Environment detection
- Job creation
- Execution with progress
- Result handling

---

## Common Operations

### List All Jobs

```bash
h2kvmctl.worker.cli list
```

### Filter by State

```bash
h2kvmctl.worker.cli list --state completed
h2kvmctl.worker.cli list --state failed
```

### Follow Events in Real-Time

```bash
h2kvmctl.worker.cli events my-job --follow
```

### Get JSON Output

```bash
h2kvmctl.worker.cli capabilities --json-output
```

---

## Troubleshooting

### "Permission denied" on NBD operations

You're running in safe container mode. Options:
1. Run on host: `sudo h2kvmctl.worker.cli run job.json`
2. Use privileged container
3. Stick to conversion/inspection operations

### "Job not found"

The job ID doesn't exist. List all jobs:
```bash
h2kvmctl.worker.cli list
```

### "Missing required capability"

Your worker can't execute this job type. Check:
```bash
h2kvmctl.worker.cli capabilities
```

---

## What's Next?

1. Read the [complete protocol spec](PROTOCOL_SPEC.md)
2. Try the Python API (see `examples/worker_example.py`)
3. Deploy workers in Kubernetes (see `k8s/worker/`)

---

**Happy job orchestration!** 🚀
