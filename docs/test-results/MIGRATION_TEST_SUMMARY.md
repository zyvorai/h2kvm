# Migration Pipeline Test Summary

## Test Configuration

**Input:** ESX 8.0 RHEL 8.8 with thin-provisioned disk (3.9GB VMDK)
**Output:** QCOW2 with compression
**Options:** 
- Flatten: Yes
- Fstab Mode: stabilize-all  
- Regen Initramfs: Yes
- Compress: Yes

## Pipeline Stages

### 1. Disk Conversion
- Convert VMDK → QCOW2 format
- Flatten thin-provisioned disk chains
- Apply compression

### 2. Offline Fixes
- Stabilize /etc/fstab (UUID → /dev/sdX for reliability)
- Regenerate initramfs with KVM drivers
- Update bootloader configuration

### 3. VM Validation (vmspawn)
- Boot VM using systemd-vmspawn  
- Verify systemd is running
- Check network configuration
- Confirm boot completed successfully

### 4. Reporting
- Console output with timeline
- JSON report generation

## Commands

### Using Python Script
```bash
sudo python3 test_simple_migration.py
```

### Using Config File
```bash
sudo h2kvmctl --config test-config.yaml
```

### Config File (test-config.yaml)
```yaml
cmd: local
vmdk: ./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk
output_dir: ./output
to_output: rhel8.8-fixed.qcow2
out_format: qcow2
compress: true
flatten: true
fstab_mode: stabilize-all
regen_initramfs: true
```

## Expected Timeline

- VMDK Conversion: 2-5 minutes
- Offline Fixes: 30-60 seconds  
- VM Validation: 30-180 seconds
- **Total:** ~3-7 minutes

## Success Criteria

✅ Conversion completes without errors
✅ Output file created: `output/rhel8.8-fixed.qcow2`
✅ VM boots successfully with vmspawn
✅ Systemd status: active
✅ Network: configured
✅ Boot: complete

## Output Files

After successful migration:
```
output/
├── rhel8.8-fixed.qcow2      # Converted VM image
└── migration-report.json     # Detailed results
```

## Validation with vmspawn

The test uses systemd-vmspawn to validate the converted image:

```bash
systemd-vmspawn \
  --machine=migration-test \
  --image=output/rhel8.8-fixed.qcow2 \
  --ram=2048M \
  --cpus=2
```

This ensures the migrated VM actually boots and runs correctly on KVM.

## Next Steps After Success

1. Test boot performance
2. Verify all services start correctly
3. Check application functionality  
4. Deploy to production KVM/KubeVirt

## Integration with KubeVirt

After validation, deploy to Kubernetes:

```yaml
apiVersion: h2kvm.io/v1
kind: Validation
metadata:
  name: rhel88-migration
spec:
  image: /path/to/rhel8.8-fixed.qcow2
  memory: 2048
  cpus: 2
  createKubeVirtVM: true
```

## Troubleshooting

### Permission Issues
Requires sudo for filesystem operations:
```bash
sudo python3 test_simple_migration.py
```

### systemd-vmspawn Not Found
Install systemd-container package:
```bash
sudo dnf install systemd-container  # RHEL/Fedora
sudo apt install systemd-container  # Debian/Ubuntu
```

### Validation Timeout
Increase timeout in config if needed:
```python
"validation_timeout": 600  # 10 minutes
```
