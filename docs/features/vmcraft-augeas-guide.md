# VMCraft Augeas Configuration Management Guide

Complete guide to Augeas-based configuration file editing with VMCraft for consistent, programmatic configuration management.

## Overview

VMCraft v9.1+ integrates Augeas for structured configuration file manipulation:
- Parse configuration files (fstab, hosts, sshd_config, networkd, systemd units)
- Query and modify values with XPath-like syntax
- Save changes atomically with validation
- Support for 100+ file formats via Augeas lenses

Augeas enables migration workflows like:
- Standardizing fstab entries (UUID → LABEL conversion)
- Updating network configurations for KVM
- Modifying SSH daemon settings
- Editing systemd unit files programmatically
- Batch configuration updates across VMs

## Augeas Concepts

### What is Augeas?

Augeas is a configuration editing library that:
1. Parses config files into tree structure (like XML DOM)
2. Provides XPath-style navigation
3. Validates changes before saving
4. Preserves comments and formatting

### Tree Navigation

Configuration files are represented as paths:

```
/files/etc/fstab/1/spec      = "UUID=abc123..."
/files/etc/fstab/1/file      = "/"
/files/etc/fstab/1/vfstype   = "ext4"
/files/etc/fstab/1/opt[1]    = "defaults"
/files/etc/fstab/1/dump      = "0"
/files/etc/fstab/1/passno    = "1"
```

---

## Installation

Augeas is an **optional dependency** for VMCraft.

### Install Augeas Library

```bash
# Fedora/RHEL
sudo dnf install augeas python3-augeas

# Ubuntu/Debian
sudo apt install augeas-tools python3-augeas

# Verify installation
python3 -c "import augeas; print('Augeas available')"
```

### Without Augeas

VMCraft gracefully degrades if Augeas is not available:
```python
g = VMCraft("ubuntu.vmdk")
g.launch()

try:
    g.aug_init()
except RuntimeError as e:
    print(f"Augeas not available: {e}")
    # Fall back to manual file editing with g.read(), g.write()
```

---

## Augeas Management APIs

### Core APIs (10 methods)

| Method | Purpose |
|--------|---------|
| `aug_init()` | Initialize Augeas with guest filesystem root |
| `aug_close()` | Close Augeas and release resources |
| `aug_get()` | Get configuration value at path |
| `aug_set()` | Set configuration value |
| `aug_save()` | Save all changes to disk |
| `aug_match()` | Find paths matching pattern |
| `aug_insert()` | Insert new node |
| `aug_rm()` | Remove nodes matching path |
| `aug_defvar()` | Define variable for path expressions |
| `aug_defnode()` | Define node variable (creates if missing) |

---

## Quick Start Examples

### 1. Basic Augeas Workflow

```python
from hyper2kvm.vmcraft import VMCraft

g = VMCraft("ubuntu-server.vmdk")
g.launch()
g.mount("/dev/nbd0p1", "/")

# Initialize Augeas
g.aug_init()

try:
    # Read value
    hostname = g.aug_get("/files/etc/hostname")
    print(f"Current hostname: {hostname}")

    # Modify value
    g.aug_set("/files/etc/hostname", "kvm-server")

    # Save changes
    g.aug_save()
    print("✓ Hostname updated")

finally:
    # Cleanup
    g.aug_close()
```

### 2. Modify /etc/fstab Entry

```python
# Update fstab to use LABEL instead of UUID

g.aug_init()

try:
    # Find all fstab entries
    entries = g.aug_match("/files/etc/fstab/*")
    print(f"Found {len(entries)} fstab entries")

    # Update first entry to use LABEL
    g.aug_set("/files/etc/fstab/1/spec", "LABEL=root")

    # Verify change
    new_spec = g.aug_get("/files/etc/fstab/1/spec")
    print(f"Updated fstab entry: {new_spec}")

    # Save
    g.aug_save()

finally:
    g.aug_close()
```

### 3. Configure SSH Daemon

```python
# Disable root login and password auth

g.aug_init()

try:
    # Disable root login
    g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")

    # Disable password authentication
    g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")

    # Enable public key auth
    g.aug_set("/files/etc/ssh/sshd_config/PubkeyAuthentication", "yes")

    # Save changes
    g.aug_save()
    print("✓ SSH configuration hardened")

finally:
    g.aug_close()
```

### 4. Add /etc/hosts Entry

```python
# Add custom host entry

g.aug_init()

try:
    # Find last hosts entry
    entries = g.aug_match("/files/etc/hosts/*[canonical]")
    last_entry = len(entries)

    # Add new entry
    new_entry_num = last_entry + 1
    base_path = f"/files/etc/hosts/{new_entry_num}"

    g.aug_set(f"{base_path}/ipaddr", "192.168.1.100")
    g.aug_set(f"{base_path}/canonical", "kvm-host.local")
    g.aug_set(f"{base_path}/alias", "kvm-host")

    # Save
    g.aug_save()
    print("✓ Added hosts entry: 192.168.1.100  kvm-host.local")

finally:
    g.aug_close()
```

---

## API Reference

### aug_init()

Initialize Augeas with guest filesystem root.

**Signature:**
```python
def aug_init(flags: int = 0) -> None
```

**Parameters:**
- `flags` (int): Augeas flags (default: 0)
  - `augeas.Augeas.SAVE_BACKUP` (1) - Create .augsave backup
  - `augeas.Augeas.SAVE_NEWFILE` (2) - Save to .augnew file
  - `augeas.Augeas.NO_MODL_AUTOLOAD` (4) - Don't auto-load lenses

**Example:**
```python
# Basic initialization
g.aug_init()

# Initialize with backup
import augeas
g.aug_init(flags=augeas.Augeas.SAVE_BACKUP)

# Custom flags
g.aug_init(flags=augeas.Augeas.SAVE_BACKUP | augeas.Augeas.NO_MODL_AUTOLOAD)
```

**Notes:**
- Must call after mounting guest filesystem
- Only one Augeas instance per VMCraft instance
- Call `aug_close()` when done

---

### aug_close()

Close Augeas instance and release resources.

**Signature:**
```python
def aug_close() -> None
```

**Example:**
```python
g.aug_init()
# ... perform operations
g.aug_close()  # Cleanup
```

**Notes:**
- Always call in `finally` block for proper cleanup
- Changes not saved with `aug_save()` are lost

---

### aug_get()

Get configuration value at path.

**Signature:**
```python
def aug_get(path: str) -> str | None
```

**Parameters:**
- `path` (str): Augeas path (e.g., `/files/etc/hostname`)

**Returns:**
- `str | None`: Value at path, or `None` if path doesn't exist

**Example:**
```python
# Get hostname
hostname = g.aug_get("/files/etc/hostname")
print(f"Hostname: {hostname}")

# Get fstab entry
root_device = g.aug_get("/files/etc/fstab/1/spec")
print(f"Root device: {root_device}")

# Get SSH setting
permit_root = g.aug_get("/files/etc/ssh/sshd_config/PermitRootLogin")
print(f"PermitRootLogin: {permit_root}")
```

---

### aug_set()

Set configuration value.

**Signature:**
```python
def aug_set(path: str, value: str) -> None
```

**Parameters:**
- `path` (str): Augeas path
- `value` (str): New value

**Example:**
```python
# Set hostname
g.aug_set("/files/etc/hostname", "new-hostname")

# Set fstab entry
g.aug_set("/files/etc/fstab/1/spec", "LABEL=root")

# Set multiple values
g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")

# Must call aug_save() to persist changes
g.aug_save()
```

---

### aug_save()

Save all changes to disk.

**Signature:**
```python
def aug_save() -> None
```

**Example:**
```python
# Make changes
g.aug_set("/files/etc/hostname", "kvm-host")
g.aug_set("/files/etc/hosts/1/canonical", "kvm-host.local")

# Save atomically
g.aug_save()
print("✓ Changes saved")
```

**Notes:**
- Validates changes before saving
- Atomic operation (all or nothing)
- Creates backups if SAVE_BACKUP flag set

---

### aug_match()

Find paths matching pattern.

**Signature:**
```python
def aug_match(pattern: str) -> list[str]
```

**Parameters:**
- `pattern` (str): Path pattern (supports wildcards)

**Returns:**
- `list[str]`: Matching paths

**Example:**
```python
# Find all fstab entries
entries = g.aug_match("/files/etc/fstab/*")
print(f"Fstab entries: {len(entries)}")

# Find all SSH config keys
keys = g.aug_match("/files/etc/ssh/sshd_config/*")
for key in keys:
    value = g.aug_get(key)
    print(f"{key} = {value}")

# Find all hosts with specific IP
hosts = g.aug_match("/files/etc/hosts/*[ipaddr = '192.168.1.100']")
```

---

### aug_insert()

Insert new node at path.

**Signature:**
```python
def aug_insert(path: str, label: str, before: bool = True) -> None
```

**Parameters:**
- `path` (str): Reference path
- `label` (str): New node label
- `before` (bool): Insert before (True) or after (False) reference

**Example:**
```python
# Insert new fstab entry before entry 1
g.aug_insert("/files/etc/fstab/1", "01", before=True)
g.aug_set("/files/etc/fstab/01/spec", "LABEL=boot")
g.aug_set("/files/etc/fstab/01/file", "/boot")
g.aug_set("/files/etc/fstab/01/vfstype", "ext4")
g.aug_save()
```

---

### aug_rm()

Remove nodes matching path.

**Signature:**
```python
def aug_rm(path: str) -> int
```

**Parameters:**
- `path` (str): Path pattern to remove

**Returns:**
- `int`: Number of nodes removed

**Example:**
```python
# Remove specific fstab entry
count = g.aug_rm("/files/etc/fstab/3")
print(f"Removed {count} fstab entry")

# Remove all entries matching pattern
count = g.aug_rm("/files/etc/hosts/*[ipaddr = '127.0.0.1']")
print(f"Removed {count} localhost entries")

# Save changes
g.aug_save()
```

---

### aug_defvar()

Define variable for reuse in path expressions.

**Signature:**
```python
def aug_defvar(name: str, expr: str) -> None
```

**Parameters:**
- `name` (str): Variable name
- `expr` (str): Path expression

**Example:**
```python
# Define variable for SSH config path
g.aug_defvar("sshd", "/files/etc/ssh/sshd_config")

# Use variable in paths
permit_root = g.aug_get("$sshd/PermitRootLogin")
g.aug_set("$sshd/PasswordAuthentication", "no")
```

---

### aug_defnode()

Define node variable, creating node if it doesn't exist.

**Signature:**
```python
def aug_defnode(name: str, expr: str, value: str | None = None) -> tuple[int, bool]
```

**Parameters:**
- `name` (str): Variable name
- `expr` (str): Path expression
- `value` (str | None): Value for new node

**Returns:**
- `tuple[int, bool]`: (number of nodes, created flag)

**Example:**
```python
# Define node, create if missing
num_nodes, created = g.aug_defnode(
    "sshd_port",
    "/files/etc/ssh/sshd_config/Port",
    "22"
)

if created:
    print("Created SSH Port entry")
else:
    print(f"SSH Port entry already exists ({num_nodes} nodes)")

# Use variable
g.aug_set("$sshd_port", "2222")  # Change SSH port
g.aug_save()
```

---

## Advanced Use Cases

### 1. Batch fstab Conversion (UUID → LABEL)

```python
# Convert all UUID-based fstab entries to LABEL

g.aug_init()

try:
    # Find all fstab entries
    entries = g.aug_match("/files/etc/fstab/*")

    for entry in entries:
        # Get current spec
        spec = g.aug_get(f"{entry}/spec")

        if spec and spec.startswith("UUID="):
            # Extract UUID
            uuid = spec.split("=", 1)[1]

            # Get device label from blkid
            # (This requires mapping UUID to device first)
            device = f"/dev/disk/by-uuid/{uuid}"
            metadata = g.blkid(device)

            if "LABEL" in metadata:
                label = metadata["LABEL"]
                # Update to LABEL
                g.aug_set(f"{entry}/spec", f"LABEL={label}")
                print(f"✓ Converted {uuid} → LABEL={label}")
            else:
                print(f"⚠ No LABEL for {uuid}")

    # Save all changes
    g.aug_save()

finally:
    g.aug_close()
```

### 2. Standardize systemd-networkd Configuration

```python
# Ensure all .network files use consistent DNS servers

g.aug_init()

try:
    # Find all .network files
    network_files = g.aug_match("/files/etc/systemd/network/*.network")

    dns_servers = ["8.8.8.8", "8.8.4.4"]

    for net_file in network_files:
        # Remove existing DNS entries
        g.aug_rm(f"{net_file}/Network/DNS")

        # Add standard DNS servers
        for idx, dns in enumerate(dns_servers, 1):
            g.aug_set(f"{net_file}/Network/DNS[{idx}]", dns)

        print(f"✓ Updated DNS for {net_file}")

    g.aug_save()

finally:
    g.aug_close()
```

### 3. Audit and Fix SSH Security Settings

```python
# Audit SSH configuration and fix insecure settings

def audit_sshd_config(g: VMCraft) -> dict:
    """Audit SSH daemon configuration."""
    g.aug_init()

    try:
        audit = {
            "permit_root": g.aug_get("/files/etc/ssh/sshd_config/PermitRootLogin"),
            "password_auth": g.aug_get("/files/etc/ssh/sshd_config/PasswordAuthentication"),
            "pubkey_auth": g.aug_get("/files/etc/ssh/sshd_config/PubkeyAuthentication"),
            "permit_empty_passwords": g.aug_get("/files/etc/ssh/sshd_config/PermitEmptyPasswords"),
        }

        # Check for insecure settings
        issues = []
        if audit["permit_root"] != "no":
            issues.append("Root login enabled")
        if audit["password_auth"] != "no":
            issues.append("Password auth enabled")
        if audit["permit_empty_passwords"] == "yes":
            issues.append("Empty passwords permitted")

        audit["issues"] = issues
        return audit

    finally:
        g.aug_close()


def fix_sshd_config(g: VMCraft):
    """Fix insecure SSH settings."""
    g.aug_init()

    try:
        # Harden configuration
        g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
        g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")
        g.aug_set("/files/etc/ssh/sshd_config/PubkeyAuthentication", "yes")
        g.aug_set("/files/etc/ssh/sshd_config/PermitEmptyPasswords", "no")

        # Additional hardening
        g.aug_set("/files/etc/ssh/sshd_config/X11Forwarding", "no")
        g.aug_set("/files/etc/ssh/sshd_config/MaxAuthTries", "3")

        g.aug_save()
        print("✓ SSH configuration hardened")

    finally:
        g.aug_close()


# Usage
g = VMCraft("ubuntu.vmdk")
g.launch()
g.mount("/dev/nbd0p1", "/")

audit = audit_sshd_config(g)
print(f"SSH audit issues: {audit['issues']}")

if audit["issues"]:
    fix_sshd_config(g)
```

### 4. Bulk Configuration Update Across Multiple VMs

```python
# Apply consistent configuration to fleet of VMs

def update_vm_config(vmdk_path: str, updates: dict):
    """Apply configuration updates to VM."""
    g = VMCraft(vmdk_path)
    g.launch()
    g.mount("/dev/nbd0p1", "/")
    g.aug_init()

    try:
        for path, value in updates.items():
            g.aug_set(path, value)
            print(f"✓ Set {path} = {value}")

        g.aug_save()

    finally:
        g.aug_close()
        g.shutdown()


# Define standard configuration
standard_config = {
    "/files/etc/hostname": "kvm-server",
    "/files/etc/ssh/sshd_config/PermitRootLogin": "no",
    "/files/etc/ssh/sshd_config/PasswordAuthentication": "no",
    "/files/etc/systemd/network/eth0.network/Network/DNS[1]": "8.8.8.8",
    "/files/etc/systemd/network/eth0.network/Network/DNS[2]": "8.8.4.4",
}

# Apply to multiple VMs
vms = ["vm1.vmdk", "vm2.vmdk", "vm3.vmdk"]

for vm in vms:
    print(f"\nUpdating {vm}...")
    update_vm_config(vm, standard_config)
```

---

## Supported File Formats

Augeas supports 100+ file formats via lenses:

| Category | Files |
|----------|-------|
| **System Config** | `/etc/hostname`, `/etc/hosts`, `/etc/resolv.conf`, `/etc/sysctl.conf` |
| **SSH** | `/etc/ssh/sshd_config`, `/etc/ssh/ssh_config` |
| **Filesystem** | `/etc/fstab`, `/etc/crypttab` |
| **Network** | `/etc/network/interfaces`, `/etc/systemd/network/*.network` |
| **Systemd** | `*.service`, `*.timer`, `*.socket`, `*.mount` |
| **Package Managers** | `/etc/yum.conf`, `/etc/apt/sources.list` |
| **Web Servers** | Apache, Nginx config files |
| **Databases** | MySQL, PostgreSQL config files |

Full list: https://github.com/hercules-team/augeas/tree/master/lenses

---

## Best Practices

### 1. Always Use try/finally for aug_close()

```python
# ✓ GOOD: Guaranteed cleanup
g.aug_init()
try:
    g.aug_set("/files/etc/hostname", "new-host")
    g.aug_save()
finally:
    g.aug_close()

# ✗ BAD: Resource leak if exception occurs
g.aug_init()
g.aug_set("/files/etc/hostname", "new-host")
g.aug_save()
g.aug_close()  # May not be called if aug_set() fails
```

### 2. Verify Path Exists Before aug_get()

```python
# ✓ GOOD: Check path exists
value = g.aug_get("/files/etc/hostname")
if value:
    print(f"Hostname: {value}")
else:
    print("Hostname not set")

# ✗ BAD: Assume path exists
value = g.aug_get("/files/etc/hostname")
print(f"Hostname: {value}")  # May print "Hostname: None"
```

### 3. Use aug_match() for Bulk Operations

```python
# ✓ GOOD: Find all entries, then iterate
entries = g.aug_match("/files/etc/fstab/*")
for entry in entries:
    spec = g.aug_get(f"{entry}/spec")
    # Process each entry

# ✗ BAD: Hardcode entry numbers (fragile)
for i in range(1, 10):
    spec = g.aug_get(f"/files/etc/fstab/{i}/spec")
    # May miss entries or hit non-existent ones
```

### 4. Save Changes Atomically

```python
# ✓ GOOD: Batch changes, then save once
g.aug_set("/files/etc/hostname", "kvm-host")
g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
g.aug_set("/files/etc/hosts/1/canonical", "kvm-host.local")
g.aug_save()  # Single atomic save

# ✗ BAD: Save after each change (slow, not atomic)
g.aug_set("/files/etc/hostname", "kvm-host")
g.aug_save()
g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
g.aug_save()
```

---

## Troubleshooting

### Issue: "Augeas library not available"

**Cause:** `python-augeas` not installed

**Solution:**
```bash
# Install Augeas Python bindings
pip install python-augeas

# Or use system package
sudo dnf install python3-augeas  # Fedora/RHEL
sudo apt install python3-augeas  # Ubuntu/Debian
```

### Issue: aug_get() returns None for known path

**Cause:** File not in Augeas tree (file doesn't exist or not mounted)

**Solution:**
```python
# Verify file exists in guest
exists = g.exists("/etc/hostname")
if not exists:
    print("File /etc/hostname doesn't exist")

# Verify filesystem mounted
# g.mount("/dev/nbd0p1", "/")
```

### Issue: aug_save() fails silently

**Cause:** Validation errors or permission issues

**Solution:**
```python
# Check for Augeas errors after save
g.aug_save()

# Get error messages (custom implementation)
errors = g.aug_match("/augeas//error")
if errors:
    for error_path in errors:
        msg = g.aug_get(f"{error_path}/message")
        print(f"Augeas error: {msg}")
```

### Issue: Changes not persisted after aug_save()

**Cause:** Augeas not initialized with correct root

**Solution:**
```python
# Ensure guest filesystem mounted first
g.mount("/dev/nbd0p1", "/")

# Then initialize Augeas
g.aug_init()  # Uses mount root automatically

# Verify root
# g.aug_get("/augeas/root") should match mount root
```

---

## See Also

- [VMCraft Complete Guide](vmcraft/complete-guide.md) - Full VMCraft API reference
- [VMCraft Advanced Features](vmcraft/advanced-features.md) - Advanced usage patterns
- [Augeas Documentation](https://augeas.net/docs/index.html) - Official Augeas docs
- [Augeas Path Guide](https://augeas.net/docs/paths.html) - Path expression syntax

---

**Last Updated**: March 2026
**VMCraft Version**: v9.1+
