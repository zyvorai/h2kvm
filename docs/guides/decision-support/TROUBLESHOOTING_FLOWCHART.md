# Troubleshooting Flowchart

Visual decision trees for diagnosing and fixing common H2KVM issues.

---

## Quick Links

- [Migration Failures](#migration-failures-flowchart)
- [Boot Failures](#boot-failures-flowchart)
- [Network Issues](#network-issues-flowchart)
- [Performance Problems](#performance-problems-flowchart)
- [Windows-Specific](#windows-specific-flowchart)
- [Deployment Issues](#deployment-issues-flowchart)

---

## Migration Failures Flowchart

```
Migration Failed?
│
├─ Error: "VMDK not found"
│  │
│  ├─ File exists? → NO
│  │  └─→ Check path, verify file location
│  │      └─→ Use absolute paths
│  │
│  └─ File exists? → YES
│     └─→ Permission issue?
│        ├─ YES → chmod 644 vmdk file
│        └─ NO → Check if file is locked
│
├─ Error: "Conversion failed"
│  │
│  ├─ Disk space available? → NO
│     │  └─→ Free up space or change output_dir
│     │      └─→ Check: df -h
│     │
│     └─ Disk space available? → YES
│        │
│        ├─ VMDK corrupted?
│        │  └─→ Run: ./scripts/vmdk_inspect.py <vmdk>
│        │     ├─ Shows errors → Get clean VMDK
│        │     └─ No errors → Continue below
│        │
│        └─ qemu-img working?
│           └─→ Test: qemu-img --version
│              ├─ Not found → Install qemu-utils
│              └─ Found → Check qemu-img compatibility
│
├─ Error: "Timeout"
│  │
│  └─→ Increase timeout in YAML
│     ```yaml
│     timeout: 7200  # 2 hours
│     network_retry: 5
│     ```
│
├─ Error: "Network failure"
│  │
│  └─→ See [Network Issues Flowchart](#network-issues-flowchart)
│
└─ Error: "Python/Module not found"
   │
   └─→ Reinstall h2kvm
      ```bash
      pip install --upgrade --force-reinstall "h2kvm[full]"
      ```
```

**Quick Fixes**:
```bash
# Check logs
journalctl -u h2kvm -f

# Verify installation
h2kvmctl --version
pip list | grep h2kvm

# Test basic functionality
h2kvmctl --help
```

---

## Boot Failures Flowchart

```
VM Won't Boot After Migration?
│
├─ Kernel Panic?
│  │
│  ├─ Message: "VFS: Unable to mount root"
│  │  │
│  │  └─→ fstab issue
│  │     └─→ Re-run with fstab_mode: stabilize-all
│  │        ```yaml
│  │        command: local
│  │        vmdk: /path/to/vm.vmdk
│  │        output_dir: /output
│  │        fstab_mode: stabilize-all
│  │        regen_initramfs: true
│  │        ```
│  │
│  ├─ Message: "Kernel panic - not syncing"
│  │  │
│  │  └─→ Missing drivers in initramfs
│  │     └─→ Re-run with regen_initramfs: true
│  │        ```yaml
│  │        regen_initramfs: true
│  │        # grub is auto-handled
│  │        ```
│  │
│  └─ Message: "No bootable device"
│     │
│     └─→ GRUB not installed
│        └─→ Re-run with # grub is auto-handled
│
├─ Hangs at GRUB?
│  │
│  └─→ GRUB misconfiguration
│     └─→ Manual fix:
│        ```bash
│        # Mount QCOW2
│        sudo modprobe nbd
│        sudo qemu-nbd -c /dev/nbd0 /path/to/vm.qcow2
│        sudo mount /dev/nbd0p1 /mnt
│
│        # Fix GRUB
│        sudo chroot /mnt
│        grub2-mkconfig -o /boot/grub2/grub.cfg
│        exit
│
│        # Cleanup
│        sudo umount /mnt
│        sudo qemu-nbd -d /dev/nbd0
│        ```
│
├─ Boots but drops to emergency shell?
│  │
│  ├─ Check fstab
│  │  └─→ UUID mismatch
│  │     └─→ Use h2kvmctl fix fstab
│  │
│  └─ Check for duplicate UUIDs (VMware clones)
│     └─→ Use xfs_regenerate_uuid: true
│        ```yaml
│        xfs_regenerate_uuid: true
│        fstab_mode: stabilize-all
│        ```
│
└─ Windows won't boot?
   │
   └─→ See [Windows-Specific Flowchart](#windows-specific-flowchart)
```

**Quick Diagnostic Commands**:
```bash
# Check VM console
virsh console <vm-name>

# View boot logs
virsh dumpxml <vm-name> | grep serial

# Test boot in QEMU
qemu-system-x86_64 -m 2048 -hda /path/to/vm.qcow2 -vnc :0
```

---

## Network Issues Flowchart

```
Network Not Working?
│
├─ Remote Fetch Failing?
│  │
│  ├─ Error: "Connection refused"
│  │  │
│  │  └─→ SSH not accessible?
│  │     ├─ Test: ssh user@host
│  │     ├─ Check firewall
│  │     └─→ Verify SSH keys
│  │
│  ├─ Error: "Permission denied"
│  │  │
│  │  └─→ SSH key issue
│  │     └─→ Add key to authorized_keys
│  │        ```bash
│  │        ssh-copy-id user@host
│  │        ```
│  │
│  └─ Error: "Network timeout"
│     │
│     └─→ Increase timeout & retries
│        ```yaml
│        timeout: 7200
│        network_retry: 5
│        ```
│
├─ VM Network Not Working After Migration?
│  │
│  ├─ Linux VM?
│  │  │
│  │  ├─ Check interface name changed?
│  │  │  └─→ eth0 → ens3 or similar
│  │  │     └─→ Update network config
│  │  │        ```bash
│  │  │        # Check interfaces
│  │  │        ip link show
│  │  │
│  │  │        # Update config
│  │  │        vi /etc/sysconfig/network-scripts/ifcfg-ens3
│  │  │        ```
│  │  │
│  │  └─ Check NetworkManager
│  │     └─→ Restart service
│  │        ```bash
│  │        systemctl restart NetworkManager
│  │        ```
│  │
│  └─ Windows VM?
│     │
│     └─→ VirtIO network driver missing?
│        └─→ Re-run with inject_virtio_drivers: true
│           ```yaml
│           inject_virtio_drivers: true
│           windows_version: 2019
│           ```
│
└─ vSphere Connection Issues?
   │
   └─→ Check credentials and network
      ```yaml
      command: vsphere_export
      vcenter_host: vcenter.example.com
      vcenter_user: admin@vsphere.local
      vcenter_password: <password>
      # Add these for debugging
      network_retry: 5
      timeout: 3600
      ```
```

**Quick Network Diagnostics**:
```bash
# Test connectivity
ping -c 4 <host>

# Test SSH
ssh -v user@host

# Check DNS
nslookup vcenter.example.com

# Test port
nc -zv <host> 22
```

---

## Performance Problems Flowchart

```
Migration Too Slow?
│
├─ Check bottleneck
│  │
│  ├─ CPU usage high?
│  │  └─→ Reduce parallel workers
│  │     ```yaml
│  │     batch_parallel: 2  # Reduce from 4
│  │     ```
│  │
│  ├─ Disk I/O bottleneck?
│  │  │
│  │  └─→ Check: iostat -x 1
│  │     ├─ High await → Disk is slow
│  │     │  └─→ Use faster storage
│  │     │     └─→ Or disable compression temporarily
│  │     │        ```yaml
│  │     │        compress: false
│  │     │        ```
│  │     │
│  │     └─→ Move conversion_dir to faster disk
│  │        ```yaml
│  │        conversion_dir: /fast/ssd/temp
│  │        ```
│  │
│  ├─ Network bottleneck?
│  │  │
│  │  └─→ Check: iftop or nethogs
│  │     └─→ Use compression for remote transfers
│  │        ```yaml
│  │        compress: true
│  │        compression_level: 6
│  │        ```
│  │
│  └─ Memory pressure?
│     │
│     └─→ Check: free -h
│        └─→ Reduce chunk size
│           ```yaml
│           chunk_size: 512M  # Reduce from 1G
│           ```
│
├─ Converted VM runs slowly?
│  │
│  ├─ Using virtio drivers?
│  │  │
│  │  ├─ Linux → Should be automatic
│  │  │  └─→ Verify: lsmod | grep virtio
│  │  │
│  │  └─ Windows → Need injection
│  │     └─→ Re-run with inject_virtio_drivers: true
│  │
│  ├─ Proper CPU/memory allocation?
│  │  └─→ Check virsh dumpxml <vm>
│  │     └─→ Adjust in libvirt XML
│  │
│  └─ Storage performance?
│     └─→ Check qcow2 vs raw
│        └─→ Convert to raw for better performance
│           ```bash
│           qemu-img convert -O raw vm.qcow2 vm.raw
│           ```
│
└─ GuestKit operations slow?
   │
   └─→ Enable caching
      ```python
      # In custom code
      guestkit.enable_cache()
      ```
```

**Performance Monitoring**:
```bash
# During migration
watch -n 1 'ps aux | grep h2kvm'
iostat -x 1
iotop -o

# VM performance
virsh domstats <vm-name>
```

---

## Windows-Specific Flowchart

```
Windows VM Issues?
│
├─ Blue Screen on Boot (BSOD)?
│  │
│  ├─ Error: "INACCESSIBLE_BOOT_DEVICE"
│  │  │
│  │  └─→ Missing storage drivers
│  │     └─→ Re-run with VirtIO driver injection
│  │        ```yaml
│  │        command: local
│  │        vmdk: /windows/server.vmdk
│  │        output_dir: /output
│  │        inject_virtio_drivers: true
│  │        windows_version: 2019  # or 2016, 2022, etc.
│  │        ```
│  │
│  └─ Other STOP codes
│     └─→ Check Windows boot logs
│        └─→ See [Windows Troubleshooting](os-support/windows/troubleshooting.md)
│
├─ Network Not Working?
│  │
│  └─→ VirtIO network driver missing
│     └─→ Manual driver installation
│        1. Download VirtIO ISO
│        2. Attach to VM
│        3. Install netkvm driver
│        └─→ See [Windows Networking](os-support/windows/networking.md)
│
├─ Can't Login?
│  │
│  └─→ Password reset needed
│     └─→ Use offline password reset
│        ```bash
│        # Mount QCOW2
│        sudo guestmount -a windows.qcow2 -m /dev/sda2 /mnt
│
│        # Reset password with chntpw
│        cd /mnt/Windows/System32/config
│        sudo chntpw -u Administrator SAM
│
│        # Cleanup
│        sudo guestunmount /mnt
│        ```
│
├─ Activation Issues?
│  │
│  └─→ Hardware change detected
│     └─→ Re-activate Windows
│        └─→ Use original license key
│
└─ Poor Performance?
   │
   ├─ VirtIO drivers installed?
   │  └─→ Check Device Manager
   │     └─→ Install all VirtIO drivers
   │
   └─ Memory ballooning?
      └─→ Check virtio-balloon driver
```

**Windows Diagnostics**:
```powershell
# Inside Windows VM
# Check drivers
Get-PnpDevice | Where-Object {$_.Status -eq "Error"}

# Check disk
Get-PhysicalDisk
Get-Disk

# Check network
Get-NetAdapter
ipconfig /all
```

---

## Deployment Issues Flowchart

```
Deployment Problems?
│
├─ Kubernetes/OpenShift?
│  │
│  ├─ Pod won't start?
│  │  │
│  │  ├─ Check pod status
│  │  │  ```bash
│  │  │  kubectl get pods -n h2kvm-system
│  │  │  kubectl describe pod <pod-name> -n h2kvm-system
│  │  │  ```
│  │  │
│  │  ├─ Image pull error?
│  │  │  └─→ Check image exists
│  │  │     ```bash
│  │  │     kubectl get events -n h2kvm-system
│  │  │     ```
│  │  │
│  │  ├─ Permission issues?
│  │  │  └─→ Check RBAC
│  │  │     ```bash
│  │  │     kubectl get rolebinding -n h2kvm-system
│  │  │     kubectl get clusterrolebinding | grep h2kvm
│  │  │     ```
│  │  │
│  │  └─ Resource limits?
│  │     └─→ Check resources
│  │        ```bash
│  │        kubectl top nodes
│  │        kubectl describe node <node-name>
│  │        ```
│  │
│  ├─ MigrationJob fails?
│  │  │
│  │  └─→ Check job logs
│  │     ```bash
│  │     kubectl logs -n h2kvm-system <job-pod>
│  │     kubectl describe migrationjob <job-name>
│  │     ```
│  │
│  └─ Operator issues?
│     │
│     └─→ Check operator logs
│        ```bash
│        kubectl logs -n h2kvm-system \
│          deployment/h2kvm-operator
│        ```
│
├─ Helm Installation Failed?
│  │
│  ├─ Chart not found?
│  │  └─→ Add repo
│  │     ```bash
│  │     helm repo add h2kvm https://ssahani.github.io/h2kvm-charts
│  │     helm repo update
│  │     ```
│  │
│  └─ Values error?
│     └─→ Validate values
│        ```bash
│        helm template h2kvm h2kvm/h2kvm \
│          -f values.yaml --debug
│        ```
│
└─ Daemon Mode Issues?
   │
   ├─ Daemon won't start?
   │  └─→ Check systemd
   │     ```bash
   │     systemctl status h2kvm
   │     journalctl -u h2kvm -f
   │     ```
   │
   └─ Job submission fails?
      └─→ Check daemon status
         ```bash
         h2kvmctl daemon status
         curl http://localhost:8080/api/v1/health
         ```
```

**Deployment Diagnostics**:
```bash
# Kubernetes
kubectl get all -n h2kvm-system
kubectl get events -n h2kvm-system --sort-by='.lastTimestamp'

# Helm
helm list -n h2kvm-system
helm get values h2kvm -n h2kvm-system

# Daemon
systemctl status h2kvm
ss -tlnp | grep 8080
```

---

## General Diagnostic Steps

### Step 1: Gather Information

```bash
# H2KVM version
h2kvmctl --version

# System information
uname -a
cat /etc/os-release

# Check dependencies
qemu-img --version
python3 --version
pip list | grep h2kvm

# Disk space
df -h

# Memory
free -h

# Logs
journalctl -u h2kvm -n 100 --no-pager
```

### Step 2: Enable Debug Logging

```yaml
# In migration config
command: local
vmdk: /path/to/vm.vmdk
output_dir: /output

# Enable debug
log_level: DEBUG
log_file: /tmp/migration-debug.log
```

Or via environment:
```bash
export H2KVM_LOG_LEVEL=DEBUG
export H2KVM_LOG_FILE=/tmp/debug.log
h2kvmctl --config migration.yaml
```

### Step 3: Test Components

```bash
# Test VMDK accessibility
ls -lh /path/to/vm.vmdk

# Test VMDK integrity
./scripts/vmdk_inspect.py /path/to/vm.vmdk

# Test qemu-img
qemu-img info /path/to/vm.vmdk

# Test network (for remote operations)
ping -c 4 <remote-host>
ssh user@host "echo test"

# Test GuestKit
python3 -c "from h2kvm.core import guestkit_client; print('OK')"
```

### Step 4: Minimal Test Case

```yaml
# minimal-test.yaml
command: local
vmdk: /path/to/small-test.vmdk
output_dir: /tmp/test
to_output: test.qcow2

# Disable all features for testing
fstab_mode: preserve
regen_initramfs: false
compress: false
```

```bash
h2kvmctl --config minimal-test.yaml
```

---

## Quick Reference Matrix

| Symptom | Most Likely Cause | Quick Fix |
|---------|-------------------|-----------|
| **VMDK not found** | Wrong path | Use absolute path |
| **Permission denied** | File permissions | `chmod 644 <vmdk>` |
| **Kernel panic** | Missing drivers | `regen_initramfs: true` |
| **Boot to emergency** | fstab UUID mismatch | `fstab_mode: stabilize-all` |
| **Windows BSOD** | Missing VirtIO drivers | `inject_virtio_drivers: true` |
| **Network timeout** | Connectivity issue | Increase `timeout` and `network_retry` |
| **Slow migration** | Disk I/O bottleneck | Disable compression or use faster storage |
| **VM won't boot** | GRUB issue | `# grub is auto-handled` |
| **Duplicate UUID** | Cloned VM | `xfs_regenerate_uuid: true` |
| **Pod won't start** | Image/RBAC issue | Check `kubectl describe pod` |

---

## Getting Additional Help

### 1. Check Documentation
- [FAQ](FAQ.md) - Common questions
- [Troubleshooting Guide](guides/troubleshooting.md) - Detailed guide
- [Failure Modes](reference/failure-modes.md) - Known issues

### 2. Search GitHub Issues
- [Existing Issues](https://github.com/ssahani/h2kvm/issues)
- Search for your error message

### 3. Create Detailed Issue

Include:
```
**H2KVM Version**: (h2kvmctl --version)
**OS**: (cat /etc/os-release)
**Python**: (python3 --version)

**Configuration**:
```yaml
(paste your YAML)
```

**Error**:
```
(paste error output)
```

**Logs**:
```
(paste relevant logs)
```

**Steps to Reproduce**:
1. Step 1
2. Step 2
3. ...
```

### 4. Community Support
- [GitHub Discussions](https://github.com/ssahani/h2kvm/discussions)
- Stack Overflow (tag: h2kvm)

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
