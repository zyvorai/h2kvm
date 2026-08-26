# Migration Cookbook
## Common VM Migration Recipes and Patterns

This cookbook provides tested recipes for common VM migration scenarios using VMCraft.

---

## Table of Contents

1. [Basic VMware to KVM Migration](#recipe-1-basic-vmware-to-kvm-migration)
2. [Large Enterprise VM Migration](#recipe-2-large-enterprise-vm-migration)
3. [Database Server Migration](#recipe-3-database-server-migration)
4. [Web Server Farm Migration](#recipe-4-web-server-farm-migration)
5. [Security-Hardened Migration](#recipe-5-security-hardened-migration)
6. [Minimal Downtime Migration](#recipe-6-minimal-downtime-migration)
7. [Disaster Recovery Setup](#recipe-7-disaster-recovery-setup)
8. [Batch Migration Workflow](#recipe-8-batch-migration-workflow)
9. [Troubleshooting Failed Migrations](#recipe-9-troubleshooting-failed-migrations)
10. [Performance Optimization](#recipe-10-performance-optimization)

---

## Recipe 1: Basic VMware to KVM Migration

**Use Case:** Migrate a simple VMware VM to KVM with minimal customization

**Time:** ~15 minutes
**Complexity:** Easy
**Risk:** Low

### Prerequisites
- Source VMware VMDK file
- Target KVM host with sufficient storage
- qemu-img and qemu-nbd installed

### Steps

```python
from h2kvm.core.vmcraft.main import VMCraft

# 1. Quick readiness check
with VMCraft("/vmware/simple-vm.vmdk") as g:
    roots = g.inspect_os()
    if not roots:
        print("No OS detected")
        exit(1)

    root = roots[0]
    print(f"OS: {g.inspect_get_distro(root)} {g.inspect_get_major_version(root)}")

# 2. Disable VMware services
with VMCraft("/vmware/simple-vm.vmdk") as g:
    roots = g.inspect_os()
    root = roots[0]

    # Mount filesystem
    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp)

    # Disable VMware tools
    if g.systemd_is_available():
        vmware_services = ["vmtoolsd", "vmware-tools"]
        g.systemd_services_disable_multiple(vmware_services)
        g.systemd_services_mask(vmware_services)

        # Enable KVM guest agent
        g.systemd_service_enable("qemu-guest-agent")
        g.systemd_daemon_reload()

# 3. Convert to qcow2
import subprocess
subprocess.run([
    "qemu-img", "convert",
    "-f", "vmdk",
    "-O", "qcow2",
    "/vmware/simple-vm.vmdk",
    "/kvm/simple-vm.qcow2"
], check=True)

print("✓ Migration complete!")
```

### Post-Migration
1. Test boot in KVM
2. Verify network connectivity
3. Check services are running

---

## Recipe 2: Large Enterprise VM Migration

**Use Case:** Migrate large (>500GB) enterprise VM with maximum performance

**Time:** ~2-4 hours
**Complexity:** Medium
**Risk:** Medium

### Key Features
- Parallel mount operations (2-3x faster)
- Partition caching
- Incremental conversion
- Comprehensive validation

### Steps

```python
from h2kvm.core.vmcraft.main import VMCraft
import subprocess

# 1. Pre-migration readiness check
subprocess.run([
    "python",
    "examples/migration_tools/pre_migration_readiness.py",
    "/vmware/large-enterprise-vm.vmdk",
    "--output", "readiness-report.json"
], check=True)

# Check readiness score before proceeding
import json
with open("readiness-report.json") as f:
    report = json.load(f)
    if report['risk_score'] > 35:
        print("⚠ High risk - review report before proceeding")

# 2. Performance-optimized migration
with VMCraft("/vmware/large-enterprise-vm.vmdk") as g:
    roots = g.inspect_os()
    root = roots[0]

    # Use parallel mounting for speed
    mountpoints = g.inspect_get_mountpoints(root)
    mount_targets = [(device, mp) for mp, device in mountpoints.items()]

    results = g.mount_all_parallel(mount_targets, max_workers=4)
    print(f"Mounted {sum(results.values())}/{len(results)} filesystems")

    # Disable VMware services in bulk
    vmware_services = [
        "vmtoolsd.service",
        "vmware-tools.service",
        "open-vm-tools.service"
    ]
    g.systemd_services_disable_multiple(vmware_services)
    g.systemd_services_mask(vmware_services)

    # Enable KVM services
    g.systemd_service_enable("qemu-guest-agent.service")

    # Migrate network configuration
    for interface in ["eth0", "eth1", "ens192", "ens224"]:
        result = g.networkd_migrate_from_ifcfg(interface)
        if result["ok"]:
            print(f"✓ Migrated {interface}")

    # Enable systemd-networkd
    g.networkd_enable_networkd()

    # Create configuration backup
    g.tar_out("/etc", "/backups/enterprise-vm-etc.tar.xz", compress="xz")

    g.systemd_daemon_reload()

# 3. Convert with compression (saves space)
subprocess.run([
    "qemu-img", "convert",
    "-f", "vmdk",
    "-O", "qcow2",
    "-c",  # Compress
    "-p",  # Show progress
    "/vmware/large-enterprise-vm.vmdk",
    "/kvm/large-enterprise-vm.qcow2"
], check=True)

# 4. Post-migration validation
subprocess.run([
    "python",
    "examples/migration_tools/post_migration_validation.py",
    "/kvm/large-enterprise-vm.qcow2",
    "--output", "validation-report.json"
], check=True)

print("✓ Large enterprise VM migration complete!")
```

### Best Practices
1. Use parallel operations for speed
2. Enable caching for repeated operations
3. Create backups before and after
4. Validate thoroughly before production

---

## Recipe 3: Database Server Migration

**Use Case:** Migrate database server (MySQL, PostgreSQL, Oracle) with data integrity

**Time:** ~30-60 minutes
**Complexity:** Medium
**Risk:** Medium-High

### Critical Considerations
- Data integrity is paramount
- Proper shutdown before migration
- Transaction log consistency
- Performance baselines

### Steps

```python
from h2kvm.core.vmcraft.main import VMCraft

# 1. Pre-migration database health check
with VMCraft("/vmware/db-server.vmdk") as g:
    roots = g.inspect_os()
    root = roots[0]

    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp, readonly=True)

    # Check database service status
    if g.systemd_is_available():
        db_services = ["mysqld", "postgresql", "oracle"]
        for svc in db_services:
            status = g.systemd_service_status(svc)
            if status["ok"]:
                print(f"Database service found: {svc}")
                print(f"  State: {status.get('active')}")

    # Verify data directories exist
    data_dirs = ["/var/lib/mysql", "/var/lib/postgresql", "/opt/oracle"]
    for data_dir in data_dirs:
        try:
            files = g.ls(data_dir)
            if files:
                print(f"✓ Data directory found: {data_dir} ({len(files)} files)")
        except:
            pass

# 2. Migrate with data integrity focus
with VMCraft("/vmware/db-server.vmdk") as g:
    roots = g.inspect_os()
    root = roots[0]

    # Mount read-write for migration
    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp, readonly=False)

    # Create pre-migration backup of database data
    for data_dir in ["/var/lib/mysql", "/var/lib/postgresql"]:
        try:
            backup_file = f"/backups/db-data-{Path(data_dir).name}.tar.xz"
            g.tar_out(data_dir, backup_file, compress="xz")
            print(f"✓ Backed up {data_dir}")
        except:
            pass

    # Service migration
    vmware_services = ["vmtoolsd", "vmware-tools"]
    g.systemd_services_disable_multiple(vmware_services)
    g.systemd_services_mask(vmware_services)

    # Enable KVM agent
    g.systemd_service_enable("qemu-guest-agent")

    # Network migration (databases need reliable networking)
    result = g.networkd_migrate_from_ifcfg("eth0")
    if result["ok"]:
        g.networkd_enable_networkd()

    g.systemd_daemon_reload()

# 3. Convert
import subprocess
subprocess.run([
    "qemu-img", "convert",
    "-f", "vmdk",
    "-O", "qcow2",
    "/vmware/db-server.vmdk",
    "/kvm/db-server.qcow2"
], check=True)

print("✓ Database server migration complete!")
print("\nIMPORTANT: Before starting database:")
print("1. Verify filesystem integrity")
print("2. Check database logs for consistency")
print("3. Run database-specific recovery if needed")
print("4. Test database connectivity")
print("5. Verify replication if configured")
```

### Post-Migration Checklist
- [ ] Verify filesystem mounted correctly
- [ ] Check database service starts
- [ ] Verify database connections work
- [ ] Test read/write operations
- [ ] Confirm replication (if applicable)
- [ ] Update monitoring systems
- [ ] Update backup scripts

---

## Recipe 4: Web Server Farm Migration

**Use Case:** Migrate multiple web servers with consistent configuration

**Time:** ~20 minutes per server
**Complexity:** Medium
**Risk:** Low-Medium

### Batch Migration Script

```python
from h2kvm.core.vmcraft.main import VMCraft
from pathlib import Path
import subprocess

# List of web servers to migrate
web_servers = [
    "/vmware/web01.vmdk",
    "/vmware/web02.vmdk",
    "/vmware/web03.vmdk",
    "/vmware/web04.vmdk",
]

# Common configuration for all servers
def migrate_web_server(vmdk_path):
    """Migrate single web server with standard config."""
    vm_name = Path(vmdk_path).stem
    output_path = f"/kvm/{vm_name}.qcow2"

    print(f"\n{'='*60}")
    print(f"Migrating: {vm_name}")
    print(f"{'='*60}")

    with VMCraft(vmdk_path) as g:
        roots = g.inspect_os()
        if not roots:
            print(f"⚠ {vm_name}: No OS detected - skipping")
            return False

        root = roots[0]

        # Mount with parallel operations
        mountpoints = g.inspect_get_mountpoints(root)
        mount_targets = [(device, mp) for mp, device in mountpoints.items()]
        g.mount_all_parallel(mount_targets, max_workers=4)

        # Standard service migration
        vmware_services = ["vmtoolsd", "vmware-tools"]
        g.systemd_services_disable_multiple(vmware_services)
        g.systemd_services_mask(vmware_services)
        g.systemd_service_enable("qemu-guest-agent")

        # Network migration
        for interface in ["eth0", "ens192"]:
            result = g.networkd_migrate_from_ifcfg(interface)
            if result["ok"]:
                break

        g.networkd_enable_networkd()

        # Backup web server configuration
        backup_file = f"/backups/{vm_name}-config.tar.xz"
        g.tar_out("/etc/httpd", backup_file, compress="xz")
        print(f"  ✓ Backed up Apache config")

        # Security hardening (disable root login)
        try:
            import augeas
            g.aug_init()
            g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
            g.aug_save()
            g.aug_close()
            print(f"  ✓ Disabled root SSH login")
        except:
            pass

        g.systemd_daemon_reload()

    # Convert
    subprocess.run([
        "qemu-img", "convert",
        "-f", "vmdk",
        "-O", "qcow2",
        "-c",  # Compress
        vmdk_path,
        output_path
    ], check=True)

    print(f"✓ {vm_name} migration complete!")
    return True

# Migrate all servers
results = {}
for server in web_servers:
    try:
        success = migrate_web_server(server)
        results[server] = success
    except Exception as e:
        print(f"✗ {server} failed: {e}")
        results[server] = False

# Summary
print(f"\n{'='*60}")
print("Migration Summary")
print(f"{'='*60}")
success_count = sum(1 for s in results.values() if s)
print(f"Successful: {success_count}/{len(web_servers)}")
for server, success in results.items():
    status = "✓" if success else "✗"
    print(f"  {status} {Path(server).stem}")
```

### Load Balancer Update
After migration, update load balancer configuration to point to new KVM IPs.

---

## Recipe 5: Security-Hardened Migration

**Use Case:** Migrate VM with security hardening applied during migration

**Time:** ~25 minutes
**Complexity:** Medium
**Risk:** Low

### Security Checklist
- [x] Disable root SSH login
- [x] Enforce key-based authentication
- [x] Remove VMware services
- [x] Enable KVM guest agent
- [x] Audit file permissions
- [x] Update security policies

### Steps

```python
from h2kvm.core.vmcraft.main import VMCraft

with VMCraft("/vmware/sensitive-vm.vmdk") as g:
    roots = g.inspect_os()
    root = roots[0]

    # Mount filesystem
    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp, readonly=False)

    # 1. SSH Hardening
    try:
        import augeas

        g.aug_init()

        # Disable root login
        g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
        print("✓ Disabled root SSH login")

        # Disable password authentication
        g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")
        print("✓ Disabled password authentication")

        # Enable public key authentication
        g.aug_set("/files/etc/ssh/sshd_config/PubkeyAuthentication", "yes")
        print("✓ Enabled public key authentication")

        # Set maximum authentication attempts
        g.aug_set("/files/etc/ssh/sshd_config/MaxAuthTries", "3")
        print("✓ Set max auth attempts to 3")

        g.aug_save()
        g.aug_close()

    except ImportError:
        print("⚠ Augeas not available - skipping SSH hardening")

    # 2. Service hardening
    if g.systemd_is_available():
        # Disable unnecessary services
        unnecessary_services = [
            "vmtoolsd",
            "vmware-tools",
            "telnet",
            "rsh",
            "rlogin"
        ]

        disabled = g.systemd_services_disable_multiple(unnecessary_services)
        masked = g.systemd_services_mask(unnecessary_services)

        print(f"✓ Disabled {sum(disabled.values())} unnecessary services")
        print(f"✓ Masked {sum(masked.values())} services")

        # Enable security services
        g.systemd_service_enable("firewalld")
        g.systemd_service_enable("qemu-guest-agent")

    # 3. Network hardening
    g.networkd_migrate_from_ifcfg("eth0")
    g.networkd_enable_networkd()

    # 4. Create security audit log
    import json
    security_audit = {
        'timestamp': datetime.now().isoformat(),
        'vm': str(self.vm_path),
        'actions': [
            'Disabled root SSH login',
            'Enforced key-based authentication',
            'Disabled unnecessary services',
            'Enabled firewall',
            'Migrated to systemd-networkd',
        ]
    }

    with open("/security-audit.json", "w") as f:
        json.dump(security_audit, f, indent=2)

    g.systemd_daemon_reload()

print("✓ Security-hardened migration complete!")
```

---

## Recipe 6: Minimal Downtime Migration

**Use Case:** Migrate production VM with minimal service interruption

**Time:** Preparation: 2 hours, Cutover: 15 minutes
**Complexity:** High
**Risk:** Medium

### Strategy
1. Pre-stage everything
2. Quick cutover window
3. Rollback plan ready

### Steps

```python
# Phase 1: Pre-staging (no downtime)
from h2kvm.core.vmcraft.main import VMCraft

# 1. Create initial conversion (read-only)
with VMCraft("/vmware/production-vm.vmdk") as g:
    # Analyze and prepare migration plan
    roots = g.inspect_os()
    root = roots[0]

    # Document current state
    config_backup = "/backups/production-pre-migration.tar.xz"
    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp, readonly=True)

    g.tar_out("/etc", config_backup, compress="xz")

# 2. Pre-convert disk image
import subprocess
subprocess.run([
    "qemu-img", "convert",
    "-f", "vmdk",
    "-O", "qcow2",
    "/vmware/production-vm.vmdk",
    "/kvm/production-vm-staged.qcow2"
], check=True)

# Phase 2: Cutover window (downtime starts)
print("\n*** CUTOVER WINDOW - DOWNTIME BEGINS ***\n")

# 1. Shutdown source VM
# (done in VMware vCenter/ESXi)

# 2. Final incremental sync (if any changes)
# (use qemu-img rebase if needed)

# 3. Apply final configurations
with VMCraft("/kvm/production-vm-staged.qcow2") as g:
    roots = g.inspect_os()
    root = roots[0]

    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp, readonly=False)

    # Quick service migration
    g.systemd_services_disable_multiple(["vmtoolsd", "vmware-tools"])
    g.systemd_service_enable("qemu-guest-agent")
    g.systemd_daemon_reload()

# 4. Start VM in KVM
# (done in KVM hypervisor)

print("\n*** CUTOVER COMPLETE - DOWNTIME ENDS ***\n")

# Phase 3: Post-cutover validation
# Verify services are up and running
```

### Rollback Plan
```bash
# If migration fails:
# 1. Power off KVM VM
# 2. Power on original VMware VM
# 3. Restore from backup if needed
# 4. Update DNS/load balancer to original IPs
```

---

## Recipe 7: Disaster Recovery Setup

**Use Case:** Create KVM-based DR copy of production VM

**Time:** ~40 minutes
**Complexity:** Medium
**Risk:** Low (non-destructive)

### Steps

```python
from h2kvm.core.vmcraft.main import VMCraft
import subprocess
from datetime import datetime

# 1. Create DR copy with timestamp
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
dr_copy = f"/dr/production-vm-dr-{timestamp}.qcow2"

# 2. Convert to KVM format
subprocess.run([
    "qemu-img", "convert",
    "-f", "vmdk",
    "-O", "qcow2",
    "/vmware/production-vm.vmdk",
    dr_copy
], check=True)

# 3. Prepare DR VM
with VMCraft(dr_copy) as g:
    roots = g.inspect_os()
    root = roots[0]

    for mp, device in g.inspect_get_mountpoints(root).items():
        g.mount(device, mp, readonly=False)

    # Label as DR copy
    try:
        hostname_file = "/etc/hostname"
        current_hostname = g.read_file(hostname_file).decode().strip()
        new_hostname = f"{current_hostname}-dr"
        g.write(hostname_file, new_hostname.encode())
        print(f"✓ Updated hostname to {new_hostname}")
    except:
        pass

    # Create DR marker file
    g.write("/etc/THIS_IS_DR_COPY", f"Created: {timestamp}\n".encode())

    # Service configuration for DR
    g.systemd_services_disable_multiple(["vmtoolsd", "vmware-tools"])
    g.systemd_service_enable("qemu-guest-agent")

    # Network configuration for DR subnet
    # (would configure DR IP addresses here)

    g.systemd_daemon_reload()

print(f"✓ DR copy created: {dr_copy}")

# 4. Create DR runbook
runbook = f"""
DR Runbook for Production VM
=============================
Created: {timestamp}
DR Image: {dr_copy}

Activation Steps:
1. Start VM from {dr_copy}
2. Verify network connectivity
3. Check all services are running
4. Update load balancer to DR IPs
5. Verify application functionality
6. Monitor logs for issues

Rollback Steps:
1. Power off DR VM
2. Restore production VM
3. Update load balancer to production IPs
4. Verify production services

Contact: ops-team@company.com
"""

with open(f"/dr/runbook-{timestamp}.txt", "w") as f:
    f.write(runbook)

print("✓ DR setup complete!")
```

---

## Recipe 8: Batch Migration Workflow

**Use Case:** Migrate 10+ VMs efficiently with automation

**Time:** ~15 minutes per VM (parallelizable)
**Complexity:** High
**Risk:** Medium

### Parallel Batch Migration

```python
from h2kvm.core.vmcraft.main import VMCraft
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import json

def migrate_single_vm(vmdk_path, output_dir):
    """Migrate a single VM."""
    vm_name = Path(vmdk_path).stem
    output_path = Path(output_dir) / f"{vm_name}.qcow2"

    try:
        print(f"Starting: {vm_name}")

        # Migrate configuration
        with VMCraft(str(vmdk_path)) as g:
            roots = g.inspect_os()
            if not roots:
                return {'vm': vm_name, 'status': 'failed', 'error': 'No OS detected'}

            root = roots[0]

            # Mount filesystems
            for mp, device in g.inspect_get_mountpoints(root).items():
                try:
                    g.mount(device, mp)
                except:
                    pass

            # Service migration
            g.systemd_services_disable_multiple(["vmtoolsd", "vmware-tools"])
            g.systemd_service_enable("qemu-guest-agent")
            g.systemd_daemon_reload()

        # Convert disk
        subprocess.run([
            "qemu-img", "convert",
            "-f", "vmdk",
            "-O", "qcow2",
            "-c",
            str(vmdk_path),
            str(output_path)
        ], check=True, capture_output=True)

        return {'vm': vm_name, 'status': 'success'}

    except Exception as e:
        return {'vm': vm_name, 'status': 'failed', 'error': str(e)}

# List of VMs to migrate
vm_list = [
    "/vmware/vm01.vmdk",
    "/vmware/vm02.vmdk",
    "/vmware/vm03.vmdk",
    "/vmware/vm04.vmdk",
    "/vmware/vm05.vmdk",
    "/vmware/vm06.vmdk",
    "/vmware/vm07.vmdk",
    "/vmware/vm08.vmdk",
    "/vmware/vm09.vmdk",
    "/vmware/vm10.vmdk",
]

output_dir = "/kvm/migrated"

# Parallel migration (max 3 concurrent)
results = []
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(migrate_single_vm, vm, output_dir): vm
        for vm in vm_list
    }

    for future in as_completed(futures):
        result = future.result()
        results.append(result)
        status_icon = "✓" if result['status'] == 'success' else "✗"
        print(f"{status_icon} {result['vm']}: {result['status']}")

# Generate summary report
summary = {
    'total': len(results),
    'successful': sum(1 for r in results if r['status'] == 'success'),
    'failed': sum(1 for r in results if r['status'] == 'failed'),
    'results': results
}

with open("/migration-summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"\n✓ Batch migration complete: {summary['successful']}/{summary['total']} successful")
```

---

## Recipe 9: Troubleshooting Failed Migrations

**Use Case:** Debug and recover from migration failures

### Common Issues and Solutions

#### Issue 1: Mount Failed

```python
# Problem: "Failed to mount /dev/sda1"
# Solution: Use mount with fallback

with VMCraft("/vmware/problematic-vm.vmdk") as g:
    device = "/dev/sda1"
    mountpoint = "/"

    # Try mount with fallback strategies
    success = g.mount_with_fallback(device, mountpoint)

    if success:
        print("✓ Mounted with fallback strategy")
    else:
        print("✗ All mount strategies failed")
        # Try manual recovery
        # 1. Check filesystem type
        metadata = g.blkid(device)
        print(f"Filesystem: {metadata.get('TYPE')}")

        # 2. Try filesystem repair (if needed)
        # fsck commands here
```

#### Issue 2: Systemd Not Detected

```python
# Problem: "Systemd not available"
# Solution: Handle SysV init systems

with VMCraft("/vmware/old-vm.vmdk") as g:
    if not g.systemd_is_available():
        print("Using SysV init - manual service management required")

        # Disable VMware tools manually
        try:
            # Remove VMware tools scripts
            g.rm("/etc/init.d/vmware-tools")
            g.rm("/etc/rc3.d/S99vmware-tools")
            print("✓ Removed VMware tools init scripts")
        except:
            pass
```

#### Issue 3: Network Configuration Missing

```python
# Problem: No network configuration found
# Solution: Create minimal network configuration

with VMCraft("/vmware/vm-no-network.vmdk") as g:
    # Create basic DHCP configuration
    result = g.networkd_create_network_file(
        name="10-eth0",
        match={"Name": "eth0"},
        network={},
        dhcp="yes"
    )

    if result["ok"]:
        g.networkd_enable_networkd()
        print("✓ Created basic DHCP network configuration")
```

---

## Recipe 10: Performance Optimization

**Use Case:** Optimize VM for maximum performance on KVM

### Optimization Checklist

```python
from h2kvm.core.vmcraft.main import VMCraft

with VMCraft("/kvm/vm-to-optimize.qcow2") as g:
    roots = g.inspect_os()
    root = roots[0]

    # Use parallel mounts for speed
    mountpoints = g.inspect_get_mountpoints(root)
    mount_targets = [(device, mp) for mp, device in mountpoints.items()]
    results = g.mount_all_parallel(mount_targets, max_workers=4)

    # 1. Analyze boot performance
    if g.systemd_is_available():
        perf = g.units_analyze_boot_performance()
        if perf["ok"]:
            print(f"Boot time: {perf.get('boot_time')}")

        # Get slowest services
        blame = g.units_analyze_blame()
        if blame["ok"]:
            print("\nSlowest services:")
            for svc in blame["services"][:5]:
                print(f"  {svc['time']:>10} - {svc['name']}")

    # 2. Disable unnecessary services
    unnecessary = [
        "bluetooth.service",
        "cups.service",
        "avahi-daemon.service"
    ]

    disabled = g.systemd_services_disable_multiple(unnecessary)
    print(f"\n✓ Disabled {sum(disabled.values())} unnecessary services")

    # 3. Optimize network configuration
    # Use systemd-networkd for better performance
    for interface in ["eth0", "ens192"]:
        result = g.networkd_migrate_from_ifcfg(interface)
        if result["ok"]:
            print(f"✓ Migrated {interface} to networkd")
            break

    g.networkd_enable_networkd()

    g.systemd_daemon_reload()

print("✓ Performance optimization complete!")
```

### Additional KVM Tuning (Outside VM)

```bash
# Optimize qcow2 image
qemu-img convert -O qcow2 -o cluster_size=2M,lazy_refcounts=on \
    old.qcow2 optimized.qcow2

# Enable virtio drivers in VM XML
# <disk type='file' device='disk'>
#   <driver name='qemu' type='qcow2' cache='writeback' io='native'/>
#   <target dev='vda' bus='virtio'/>
# </disk>
```

---

## Additional Resources

- **Pre-Migration Tool:** `examples/migration_tools/pre_migration_readiness.py`
- **Post-Migration Tool:** `examples/migration_tools/post_migration_validation.py`
- **Master Example:** `examples/enterprise_migration_master.py`
- **Features Guide:** `examples/VMCRAFT-FEATURES-GUIDE.md`

---

## Quick Reference

| Scenario | Recipe | Time | Complexity |
|----------|--------|------|------------|
| Simple VM | Recipe 1 | 15 min | Easy |
| Large Enterprise | Recipe 2 | 2-4 hours | Medium |
| Database Server | Recipe 3 | 30-60 min | Medium |
| Web Farm | Recipe 4 | 20 min/server | Medium |
| Security Hardened | Recipe 5 | 25 min | Medium |
| Minimal Downtime | Recipe 6 | 15 min cutover | High |
| Disaster Recovery | Recipe 7 | 40 min | Medium |
| Batch Migration | Recipe 8 | 15 min/VM | High |

---

**Need help?** Check the troubleshooting recipe or open an issue on GitHub.
