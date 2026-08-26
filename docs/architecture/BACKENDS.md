# Hyper2KVM Backend Options

Hyper2KVM supports multiple backends for offline guest fixes, each with different trade-offs between speed, security, and reliability.

## Overview

| Backend | Speed | Security | Maturity | Use Case |
|---------|-------|----------|----------|----------|
| **vmcraft** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | Default backend |
| **namespace** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | Maximum isolation (experimental) |

## Backend Descriptions

### 1. VMCraft (Fast Pure-Python)

**Architecture:**
- Pure Python implementation
- Native LVM module
- Direct NBD + device mapper operations
- No appliance overhead

**Pros:**
- ✅ Fast startup with low overhead
- ✅ Lower memory footprint
- ✅ No appliance dependencies
- ✅ Native Python integration

**Cons:**
- ❌ Newer codebase (less battle-tested)
- ❌ Limited to Linux guests
- ❌ Requires root for NBD/LVM operations

**When to use:**
- Bulk migrations (speed critical)
- Development/testing
- Modern Linux guests (RHEL 8+, Ubuntu 20+)
- When you have root access

**Configuration:**
```yaml
backend: vmcraft
```

**Example:**
```python
config = OfflineFixConfig(
    image=Path("guest.qcow2"),
    backend="vmcraft",
    fstab_mode="stabilize-all",
    conversion_dir="/var/tmp/hyper2kvm",  # VMCraft working directory
)

fixer = OfflineFSFix(logger, config)
result = fixer.fix()
```

---

### 2. Namespace (Maximum Isolation) - **EXPERIMENTAL**

**Architecture:**
- Unshare-based namespace isolation
- Isolated mount namespace for /dev
- Separate PID namespace for LVM
- No host LVM cache pollution

**Pros:**
- ✅ Maximum security guarantees
- ✅ Complete isolation from host LVM
- ✅ Safe concurrent operations
- ✅ No host state modification

**Cons:**
- ❌ Experimental (new code)
- ❌ Requires CAP_SYS_ADMIN
- ❌ Requires unshare command
- ❌ Linux-only

**When to use:**
- Multi-tenant environments
- Security-critical scenarios
- Concurrent guest processing
- Development/testing new isolation approaches

**Requirements:**
```bash
# Check if unshare is available
which unshare

# Check capabilities (when not root)
getcap $(which unshare)
```

**Direct Usage (Standalone):**
```python
from hyper2kvm.vmcraft.namespace_lvm import Hyper2KVM

# Use context manager for automatic cleanup
with Hyper2KVM(image="guest.qcow2") as engine:
    volumes = engine.start()

    for vol in volumes:
        engine.mount(vol, f"/mnt/{vol.replace('/', '_')}")
        # ... process mounted filesystem ...
        engine.unmount(f"/mnt/{vol.replace('/', '_')}")
```

**Via Storage Activator:**
```python
from hyper2kvm.vmcraft.storage import LVMActivator

audit = LVMActivator.activate_namespace(
    logger,
    image_path="/path/to/guest.qcow2"
)

if audit["ok"]:
    for volume in audit["volumes"]:
        print(f"Activated: {volume}")
```

---

## Backend Selection Guide

### Decision Tree

```
┌─────────────────────────────────────┐
│   Need maximum speed?                │
│   (Bulk migration, modern guests)    │
└──────────────┬──────────────────────┘
               │ YES
               ├──> Use: vmcraft
               │
               │ NO
┌──────────────┴──────────────────────┐
│   Need maximum isolation?            │
│   (Multi-tenant, security-critical)  │
└──────────────┬──────────────────────┘
               │ YES
               └──> Use: namespace (experimental)
```

### Performance Comparison

Typical migration times (RHEL 8.8, 16GB disk, LVM root):

| Backend | Launch | Mount | Total |
|---------|--------|-------|-------|
| vmcraft | 2s | 3s | 5s |
| namespace | 3s | 4s | 7s |

*Note: Actual performance depends on disk size, storage complexity, and system resources.*

---

## Configuration Examples

### Production Migration (Reliability)
```yaml
backend: vmcraft
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
filesystem_repair_enable: true
```

### Bulk Migration (Speed)
```yaml
backend: vmcraft
fstab_mode: by-uuid
regen_initramfs: true
conversion_dir: /mnt/fast-ssd/hyper2kvm
```

### Security-Hardened (Isolation)
```yaml
backend: namespace
fstab_mode: stabilize-all
dry_run: true  # Read-only inspection
```

---

## Fallback Strategy

Hyper2KVM automatically falls back to more reliable backends on failure:

```
namespace → vmcraft
   ↓          ↓
 (isolated)  (fast)
```

**Example with automatic fallback:**
```python
backends_to_try = ["namespace", "vmcraft"]

for backend in backends_to_try:
    try:
        config = OfflineFixConfig(image=image_path, backend=backend)
        fixer = OfflineFSFix(logger, config)
        result = fixer.fix()

        if result.get("status") == "success":
            logger.info(f"✅ Success with {backend} backend")
            break
    except Exception as e:
        logger.warning(f"⚠️  {backend} backend failed: {e}")
        continue
else:
    logger.error("❌ All backends failed")
```

---

## Troubleshooting

### VMCraft Backend Issues

**Problem:** LVM activation fails
```
Solution: Ensure proper udev settling
```

**Problem:** Permission denied on NBD
```
Solution: Run with sudo or adjust permissions
sudo h2kvmctl --config config.yaml
```

### Namespace Backend Issues

**Problem:** unshare: Operation not permitted
```
Solution: Run with CAP_SYS_ADMIN or as root
sudo h2kvmctl --config config.yaml --backend namespace
```

**Problem:** No volumes found
```
Solution: Verify NBD connection and LVM setup
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT
```

---

## Best Practices

1. **Start with vmcraft** for production workloads (default)
2. **Experiment with namespace** in isolated environments
4. **Always test** with dry_run=True first
5. **Monitor logs** for backend-specific warnings
6. **Have fallback** configured for reliability

---

## Future Enhancements

- [ ] Automatic backend selection based on image complexity
- [ ] Hybrid mode: namespace isolation with vmcraft speed
- [ ] Benchmark tool for backend comparison
- [ ] Cloud-optimized backends (S3, Azure Blob, etc.)

---

## See Also

- [LVM Implementation](../hyper2kvm/vmcraft/lvm.py) - Native Python LVM
- [Namespace LVM](../hyper2kvm/vmcraft/namespace_lvm.py) - Unshare-based isolation
- [Backend Comparison Example](../examples/backend_comparison.py) - Demo script
