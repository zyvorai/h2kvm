# Windows VirtIO Driver Troubleshooting

Troubleshooting guide for Windows VirtIO driver injection during VMware/Hyper-V/cloud to KVM migration.

## How Driver Discovery Works

h2kvm uses a multi-step pipeline to find and inject VirtIO drivers:

```
virtio-win.iso → Extract (cached) → Bucket match → Glob patterns → INF/SYS copy → Registry edit
```

### 1. ISO Source Resolution

The VirtIO driver source is resolved in this order:

1. `--virtio-drivers-dir /path/to/dir` (explicit directory)
2. `--virtio-drivers-dir /path/to/virtio-win.iso` (ISO file)
3. Auto-discover at `/var/lib/h2kvm/virtio-win.iso` (installed by quickstart.sh)

### 2. ISO Extraction (Cached)

When an ISO is used, h2kvm extracts it **once** and caches at `/var/lib/h2kvm/virtio-win-extracted/`:

- **Primary**: `bsdtar` (handles Rock Ridge long names correctly)
- **Fallback**: `pycdlib` with Rock Ridge name support
- **Cache invalidation**: ISO mtime changes

The cache is reused on all subsequent migrations — no re-extraction needed.

### 3. Bucket Matching

Windows versions map to VirtIO driver "buckets" (directory names in the ISO):

| Windows Version | Bucket Hint | Candidates (fallback order) |
|----------------|------------|---------------------------|
| Windows 12 | w12 | w12, w11, w10, w8, w7 |
| Windows 11 | w11 | w11, w10, w8, w7 |
| Windows 10 | w10 | w10, w11, w8, w7 |
| Windows 8.1 | w8 | w8, w10, w7 |
| Windows 8 | w8 | w8, w10, w7 |
| Windows 7 | w7 | w7, w8, w10 |
| Server 2022 | w11 | w11, w10, w8, w7 |
| Server 2019 | w10 | w10, w11, w8, w7 |
| Server 2016 | w10 | w10, w11, w8, w7 |

### 4. Driver Files

Four driver types are injected by default:

| Driver | Service | Type | Start | Purpose |
|--------|---------|------|-------|---------|
| viostor | viostor | storage | BOOT (0) | VirtIO block storage |
| vioscsi | vioscsi | storage | BOOT (0) | VirtIO SCSI |
| NetKVM | netkvm | network | AUTO (2) | VirtIO network |
| Balloon | balloon | balloon | AUTO (2) | Memory ballooning |

## Common Issues

### "A Joliet path can only be specified for a Joliet ISO"

**Cause**: Old code used pycdlib ISO 9660 mode which truncated Rock Ridge directory names (`w11` → `w`, `w8.1` → `w8.`).

**Fixed in**: Commit `0119554`. Now uses bsdtar for extraction with Rock Ridge support.

**Verify fix**: Check that the cached extraction has correct directory names:

```bash
ls /var/lib/h2kvm/virtio-win-extracted/viostor/
# Should show: 2k12 2k12R2 2k16 2k19 2k22 2k25 w10 w11 w7 w8 w8.1 xp
# NOT: w (truncated w11) or w8. (truncated w8.1)
```

**If still broken**: Delete the cache and re-run:

```bash
sudo rm -rf /var/lib/h2kvm/virtio-win-extracted/
sudo h2kvmctl --config your-config.yaml
```

### "Driver not found: type=storage name=viostor"

**Causes**:
1. Wrong ISO — ensure you have the full `virtio-win.iso` (not a partial download)
2. Architecture mismatch — 32-bit Windows needs x86 drivers, 64-bit needs amd64
3. Very old Windows — XP/Vista may need legacy SHA-1 signed drivers

**Debug**: Run with verbose and check bucket matching:

```bash
sudo h2kvmctl --config config.yaml -v 2>&1 | grep -E "bucket|Found driver|Driver not"
```

### "VMCraft has no attribute 'hivex_open'"

**Cause**: Old code called guestfs hivex API on VMCraft backend.

**Fixed in**: Commit `0119554`. VMCraft now provides a hivex API shim that downloads the hive and uses python-hivex directly.

**Verify**: Check python-hivex is installed:

```bash
python3 -c "import hivex; print('OK')"
# If missing: sudo dnf install python3-hivex
```

### Registry edits not applied (silent failure)

**Cause**: `h.value_value()` returns a tuple `(type, data)` — if code slices the tuple instead of destructuring, the operation silently fails.

**Fixed in**: Commit `3ebd6f4`. All `value_value()` calls now properly destructure as `t, data = h.value_value(val)`.

### RDP check fails / "Remote Desktop may be disabled"

The RDP check reads `fDenyTSConnections` from the SYSTEM registry hive. If it can't read the value, it warns conservatively.

**Common reasons**:
- SYSTEM hive not found (Windows not detected correctly)
- hivex not installed (`dnf install python3-hivex`)
- Encrypted disk (BitLocker blocks registry access)

**To skip the warning** (RDP will remain in its current state):
The warning is informational — migration proceeds regardless.

## VirtIO Config Override

Override driver definitions via YAML:

```yaml
# In your migration config
windows_virtio:
  bucket_candidates:
    windows_10: ["w10", "w11"]
  drivers:
    storage:
      - name: viostor
        pattern: "viostor/{bucket}/{arch}/viostor.sys"
        service: viostor
        start: 0
        class_guid: "{4D36E967-E325-11CE-BFC1-08002BE10318}"
```

Or via JSON file:

```bash
sudo h2kvmctl --config config.yaml --virtio-config /path/to/virtio-config.json
```

## Cache Management

```bash
# Check cache status
ls -la /var/lib/h2kvm/virtio-win-extracted/.iso_mtime

# Force re-extraction
sudo rm -rf /var/lib/h2kvm/virtio-win-extracted/

# Check ISO info
file /var/lib/h2kvm/virtio-win.iso
isoinfo -d -i /var/lib/h2kvm/virtio-win.iso | grep -i "rock ridge\|joliet"
```

## SATA/e1000 Fallback Mode

If VirtIO drivers can't be injected (no ISO, unsupported OS), use SATA + e1000:

```yaml
disk_bus: sata
net_model: e1000
```

The VM will boot with emulated hardware (slower but universally compatible). VirtIO drivers can be installed manually from within Windows after boot.

## See Also

- [Windows Migration Tutorial](../../tutorials/06-windows-migration.md)
- [VirtIO Config Reference](../../reference/api/vmcraft.md)
- [Test Config: Windows 10](../../../test-confs/win10-migration.yaml)
