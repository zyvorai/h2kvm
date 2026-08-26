# H2KVM Quick Reference Card

One-page reference for common commands, workflows, and configurations.

---

## Installation (Pick One)

```bash
# Python package
pip install h2kvm

# From source
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm && pip install -e .

# Container
docker pull ghcr.io/ssahani/h2kvm:latest

# System dependencies + libguestfs (recommended for LVM/LUKS)
sudo ./scripts/install-deps.sh --all
# Or: sudo dnf install libguestfs-tools python3-libguestfs
```

---

## Basic Migration Workflows

### 1. Simple Local Migration (Most Common)

```bash
h2kvm --config << EOF
command: local
vmdk: /vmware/myvm.vmdk
output_dir: /kvm/vms
to_output: myvm.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
EOF
```

**Time**: 10-30 min | **Success Rate**: 96%+

### 2. LUKS-Encrypted Disk Migration

```bash
sudo h2kvmctl --cmd local \
  --vmdk /path/to/encrypted.vmdk \
  --luks-enable --luks-passphrase "passphrase" \
  --flatten --regen-initramfs \
  --emit-domain-xml --virsh-define -o /output
# VM prompts for LUKS passphrase at boot
```

**See**: [LUKS Migration Guide](../guides/migration/luks-encrypted-disks.md)

### 3. Quick Migration (Default Settings)

```bash
h2kvmctl migrate local /vmware/myvm.vmdk --output /kvm/vms/myvm.qcow2
```

### 3. Interactive TUI Mode

```bash
h2kvmctl tui
# Follow on-screen prompts
```

### 4. Remote vSphere Export

```bash
h2kvm --config << EOF
command: vsphere
vcenter_host: vcenter.example.com
vcenter_user: admin@vsphere.local
vcenter_password: secret
vm_name: production-web-01
vs_action: export_vm
output_dir: /kvm/vms
to_output: prod-web.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
EOF
```

---

## Essential YAML Options

### Migration Modes

```yaml
# Local file migration
command: local
vmdk: /path/to/vm.vmdk

# Remote vSphere (govc-based)
command: vsphere
vcenter_host: vcenter.example.com
vcenter_user: admin@vsphere.local
vm_name: myvm
vs_action: export_vm    # or export_ova for OVA format

# OVA import
command: ova
ova: /path/to/vm.ova
firmware: uefi          # Optional: force UEFI mode
```

### Output Options

```yaml
output_dir: /kvm/vms          # Output directory
to_output: myvm.qcow2         # Output filename
compress: true                # Enable compression (smaller but slower)
format: qcow2                 # Format: qcow2 (default), raw
```

### Boot Fix Options (Recommended)

```yaml
fstab_mode: stabilize-all     # Fix fstab entries (always use)
xfs_regenerate_uuid: true     # Fix cloned VMware VMs
regen_initramfs: true         # Rebuild initramfs for new drivers
# grub is auto-handled
```

### Advanced Options

```yaml
enable_vmcraft: true          # Use VMCraft engine (default)
network_retry: 3              # Network operation retries
timeout: 3600                 # Operation timeout (seconds)
keep_original: true           # Keep original VMDK (default)
validate: true                # Run post-migration validation

# Container CPU awareness
effective_cpu_count: auto     # Auto-detect cgroup limits (default)

# LUKS encryption support
luks_enable: true
luks_passphrase: "password"   # VM prompts at boot after migration
```

---

## Common Command Patterns

### Inspect Before Migration

```bash
# Analyze VMDK
./scripts/vmdk_inspect.py /vmware/myvm.vmdk

# With auto-fix recommendations
./scripts/vmdk_inspect.py /vmware/myvm.vmdk --auto-fix
```

### Batch Migration

```bash
# Submit multiple migrations to daemon
h2kvm daemon start

for vmdk in /vmware/*.vmdk; do
    h2kvm daemon submit migration-$(basename $vmdk .vmdk).yaml
done

# Monitor progress
h2kvm daemon status
```

### Live Fix (Minimal Downtime)

```bash
# Fix running VM via SSH (<5 sec downtime)
h2kvmctl fix ssh 192.168.1.100 --user root --key ~/.ssh/id_rsa
```

---

## Troubleshooting Commands

### Check Migration Status

```bash
# View logs
journalctl -u h2kvm -f

# Check daemon jobs
h2kvmctl daemon list

# Validate QCOW2
qemu-img check /kvm/vms/myvm.qcow2
```

### Fix Common Issues

```bash
# Regenerate initramfs manually
h2kvmctl fix initramfs /dev/vda1

# Fix fstab
h2kvmctl fix fstab /dev/vda1 --mode stabilize-all

# Fix XFS UUID
h2kvmctl fix xfs-uuid /dev/vda1
```

### Boot VM for Testing

```bash
# Quick boot test
qemu-system-x86_64 -m 2048 -hda /kvm/vms/myvm.qcow2 -vnc :0
```

---

## fstab Stabilization Modes

| Mode | Behavior | Use When |
|------|----------|----------|
| `stabilize-all` | Convert all entries to UUID | **Recommended** - Always use |
| `uuid-only` | Only update UUID entries | Preserve LABEL entries |
| `label-fallback` | Prefer UUID, fallback to LABEL | Mixed environments |
| `preserve` | Keep original entries | Testing only |

---

## OS-Specific Quick Fixes

### RHEL/CentOS/Rocky

```yaml
command: local
vmdk: /vmware/rhel9.vmdk
output_dir: /kvm/vms
to_output: rhel9.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

### Ubuntu/Debian

```yaml
command: local
vmdk: /vmware/ubuntu.vmdk
output_dir: /kvm/vms
to_output: ubuntu.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

### Windows

```yaml
command: local
vmdk: /vmware/windows.vmdk
output_dir: /kvm/vms
to_output: windows.qcow2
inject_virtio_drivers: true
windows_version: 2019        # 2012, 2016, 2019, 2022, 10, 11
# virtio-win ISO auto-detected from:
#   /usr/share/virtio-win/virtio-win.iso
#   /var/lib/h2kvm/virtio-win.iso
#   /var/lib/libvirt/images/virtio-win.iso
```

**Auto-detection**: Both zkvm TUI and h2kweb wizard auto-detect Windows from the filename
(e.g., `win10.vmdk`). When detected, `regen_initramfs` and `fstab_mode` are automatically
disabled — no manual configuration needed.

**Best practice — Pre-install drivers before migration**:
Install VirtIO drivers inside the VM while still on VMware/Hyper-V. Attach
`virtio-win.iso` as CD-ROM → run `virtio-win-guest-tools.exe` → reboot → then migrate.
Network and guest agent will work on first KVM boot with no post-migration steps.

**Production Windows workflow** (migrated VMs):

1. Select a Windows VMDK — Linux fixes auto-disabled if filename contains "win"
2. Migrate with **SATA disk bus** (default for Windows) — Windows always boots
3. `virtio-win.iso` auto-attached as CD-ROM (D: drive)
4. First boot: Windows boots on SATA, no network yet — use VNC console
5. Open D: drive, run `virtio-win-guest-tools.exe` (or `/S` for silent install)
6. Network, balloon, guest agent all work immediately — no reboot needed
7. Disk stays on SATA (VirtIO disk requires offline registry fix not worth the complexity)

**What works after installer runs**: VirtIO network (immediate), memory balloon, QEMU Guest Agent, vioserial. **What stays SATA**: disk bus (fine for production).

**Automated firstboot mechanisms** (staged offline, best-effort):

| Mechanism | When it runs | Limitation for migrated VMs |
|-----------|-------------|----------------------------|
| SetupComplete.cmd | After OOBE | Only fires on fresh installs |
| rhsrvany.exe service | At boot | Blocked by unsigned binary restrictions (Win10/11) |
| HKLM RunOnce key | After user login | Only triggers on new login sessions |
| Startup folder .bat | After user login | Requires actual user login |
| **Manual CD-ROM install** | **User action** | **Always works — recommended** |

### VMware Cloned VMs

```yaml
command: local
vmdk: /vmware/cloned-vm.vmdk
output_dir: /kvm/vms
to_output: fixed-vm.qcow2
xfs_regenerate_uuid: true    # Critical for clones
fstab_mode: stabilize-all
regen_initramfs: true
```

---

## Performance Tuning

### Fast Migration (Less Compression)

```yaml
compress: false               # Faster but larger
parallel_streams: 4           # Use multiple streams
```

### Small Output (More Compression)

```yaml
compress: true                # Slower but smaller
compression_level: 9          # Max compression
```

### Large VM (Resource Management)

```yaml
chunk_size: 1G                # Process in chunks
memory_limit: 4096            # Limit memory usage (MB)
```

---

## Kubernetes Deployment

### Quick Deploy with Helm

```bash
helm repo add h2kvm https://ssahani.github.io/h2kvm-charts
helm install h2kvm h2kvm/h2kvm -n h2kvm-system --create-namespace
```

### Submit Migration Job

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: migrate-web-server
  namespace: default
spec:
  source:
    type: vmdk
    path: /mnt/vmware/web-server.vmdk

  conversion:
    outputFormat: qcow2
    compress: true
    offlineFixes: true       # Enable offline fixes in operator

  fixes:
    fstabMode: stabilize-all
    regenInitramfs: true
    xfsRegenerateUuid: true  # For cloned VMs

  deployment:
    libvirt:
      enabled: true
      autoDefine: true
```

```bash
kubectl apply -f hyperconversion.yaml
kubectl get hyperconversion migrate-web-server -w
kubectl logs -f deployment/hyperconversion-operator-controller-manager -n hyperconversion-system
```

---

## Environment Variables

```bash
# Logging
export H2KVM_LOG_LEVEL=DEBUG    # DEBUG, INFO, WARNING, ERROR
export H2KVM_LOG_FILE=/var/log/h2kvm.log

# Performance
export H2KVM_WORKERS=4          # Parallel workers
export H2KVM_CACHE_DIR=/tmp/h2kvm

# Network
export H2KVM_TIMEOUT=3600       # Operation timeout
export H2KVM_RETRY=3            # Retry attempts
```

---

## File Locations

```
# Configuration
/etc/h2kvm/config.yaml          # System config
/etc/h2kvm/daemon.yaml          # Daemon config
~/.h2kvm/config.yaml            # User config

# Logs
/var/log/h2kvm/                 # System logs
~/.h2kvm/logs/                  # User logs

# Cache
/var/cache/h2kvm/               # System cache
~/.cache/h2kvm/                 # User cache

# Runtime
/run/h2kvm/                     # Runtime directory (created by quickstart/deploy)
/var/run/h2kvm.pid              # Daemon PID
/var/run/h2kvm.sock             # Daemon socket

# VirtIO drivers
/usr/share/virtio-win/virtio-win.iso       # System virtio-win ISO
/var/lib/h2kvm/virtio-win/             # Pre-extracted virtio-win drivers
```

---

## Common Error Fixes

### Error: "VMDK not found"
```bash
# Check path and permissions
ls -l /path/to/vm.vmdk
chmod 644 /path/to/vm.vmdk
```

### Error: "Boot failure - kernel panic"
```yaml
# Add these options
regen_initramfs: true
# grub is auto-handled
fstab_mode: stabilize-all
```

### Error: "Duplicate UUID"
```yaml
# For cloned VMware VMs
xfs_regenerate_uuid: true
```

### Error: "Network timeout"
```yaml
# Increase retries and timeout
network_retry: 5
timeout: 7200
```

---

## Success Rates by OS

| OS Family | Success Rate | Avg Time |
|-----------|--------------|----------|
| **RHEL/CentOS** | 98% | 15 min |
| **Ubuntu** | 97% | 12 min |
| **SUSE** | 96% | 18 min |
| **Windows** | 94% | 25 min |
| **Other Linux** | 95% | 20 min |

---

## Quick Links

- **Documentation**: `/docs/index.md`
- **Tutorials**: `/docs/tutorials/`
- **Recipes**: `/docs/recipes/`
- **FAQ**: `/docs/quick-reference/FAQ.md`
- **Troubleshooting**: `/docs/guides/troubleshooting.md`
- **API Reference**: `/docs/reference/api/`

---

## Web Dashboard (h2kweb)

```bash
cd web && make build && sudo make install
# → https://localhost:5070 (PAM login, HTTPS by default)
# TLS: auto-generated self-signed cert at /var/lib/h2kvm/tls/
# Disable: h2kweb --tls-cert none
```

### Docker Deployment

```bash
docker build -t h2kweb web/
docker run -d --name h2kweb \
  --privileged \
  -p 5070:5070 \
  -v /var/run/libvirt:/var/run/libvirt \
  -v /var/lib/libvirt:/var/lib/libvirt \
  h2kweb
# → https://localhost:5070
```

**Dashboard features**: VM screenshots, OS type badges, disk bus info, guest agent status,
migration readiness panel (19 checks: libguestfs, supermin, hivex, virtio-win, etc.),
disk images inventory, network topology, live migration logs with auto-scroll,
dark/light theme toggle, VM resource stats (CPU/memory bars), migration report export,
file upload from browser (drag-drop, progress bar, cancel),
chunked resumable upload (opt-in, 10MB chunks, retry on failure, session resume),
VM disk image download (range request support for resume),
batch migration (queue multiple VMs), migration presets (3 built-in + custom),
bulk VM actions (select → start/stop/delete all), search & filter (VMs by name/state/OS,
jobs by status), webhook notifications (Slack/Teams on job events),
migration summary (before/after comparison), API docs page,
migration timeline (4-phase visual bar), email notifications (SMTP),
VM health checks (running/IP/SSH/agent), config backup/restore,
i18n (English + German with language selector), login rate limiting (5 attempts/IP/5min),
stale upload cleanup (hourly, 24h expiry), webhook persistence (webhooks.json).

### Prometheus Metrics

```bash
# Scrape metrics endpoint (8 metric families)
curl -k https://localhost:5070/metrics

# Example metrics: migration counts, VM stats, system load, disk usage
# Add to prometheus.yml:
#   - job_name: h2kweb
#     static_configs:
#       - targets: ['localhost:5070']
```

### Email Notifications

Configure SMTP in Settings page to receive email alerts on job completion or failure.
Settings include SMTP host, port, username, password, sender address, and recipient list.

### VM Health Check API

```bash
# Check VM health: running status, IP, SSH, guest agent
curl -k https://localhost:5070/api/v1/vms/{name}/health

# Response: {"running": true, "ip": "192.168.1.50", "ssh": true, "agent": true}
```

### i18n (Internationalization)

5 languages: English, Deutsch, Français, Español, 日本語. Click language buttons in header.

### Session Timeout

Auto-logout after 30 minutes of inactivity. 2-minute warning toast before expiry.

### Audit Log

System → Audit Log: chronological record of all user actions (VM ops, migrations, webhooks).

### E2E Migration Test

```bash
sudo ./scripts/test/e2e-migration-test.sh /data/demo/ubuntu2404.vmdk
# Automated: detect OS → migrate → verify boot → check IP/SSH → cleanup
```

### Debug Logging

```bash
# Python (migration pipeline)
h2kvmctl --config migration.yaml -vv

# Go (web server)
journalctl -u h2kweb -f
# Prefixes: [api] [vm] [auth] [upload] [download] [webhook] [email] [ws] [cleanup] [tls]
```

**API endpoints for automation**:
```bash
# Batch migrate
curl -X POST /api/v1/migrations/batch -d '{"configs":[...]}'

# Bulk VM action
curl -X POST /api/v1/vms/bulk-action -d '{"names":["vm1","vm2"],"action":"start"}'

# Webhook
curl -X POST /api/v1/webhooks -d '{"url":"https://hooks.slack.com/...","events":["job_completed"]}'

# Search VMs
curl /api/v1/vms?state=running&os=windows&search=win10

# Config backup/restore
curl -k https://localhost:5070/api/v1/settings/export > config-backup.json
curl -k -X POST https://localhost:5070/api/v1/settings/import -d @config-backup.json
```

---

## Auto-Detect Device Models

Domain XML video and graphics models are auto-detected at runtime:

- **has_spice()** — checks if libspice-server.so is present
- **default_video()** — returns `qxl` if SPICE available, else `virtio`
- **default_graphics()** — returns `spice` if available, else `vnc`
- **Smoke test auto-fix** — if virsh define fails (e.g., qxl not available), retries with virtio/vnc
- **virtio-win ISO** — auto-detected from well-known paths (no manual `--virtio-drivers-dir` needed)

---

## Daemon Service

```bash
# Systemd unit for h2kvm daemon
sudo systemctl enable --now h2kvm
# Config: /etc/h2kvm/daemon.yaml
# Requires: watchdog (core dependency)
```

---

## Version Information

**H2KVM**: v0.3.0
**API Version**: v1alpha1
**Kubernetes Operator**: v0.1.0
**Last Updated**: April 2026

---

## Support

- **Issues**: https://github.com/ssahani/h2kvm/issues
- **Discussions**: https://github.com/ssahani/h2kvm/discussions
- **Documentation**: https://github.com/ssahani/h2kvm/tree/main/docs

---

**Print this page** for quick reference at your desk!
