# VMCraft Hivex API Reference

VMCraft provides a hivex compatibility shim that emulates the guestfs hivex API using python-hivex. This enables Windows registry access on the VMCraft backend without requiring libguestfs.

## Overview

The shim downloads registry hive files from the guest filesystem, opens them with python-hivex, and exposes the same method signatures as guestfs. This means existing code written for `g.hivex_open()` / `g.hivex_close()` works transparently on VMCraft.

## Requirements

```bash
# Install python-hivex
sudo dnf install python3-hivex      # Fedora/RHEL
sudo apt install python3-hivex      # Ubuntu/Debian
```

## Methods

### hivex_open

```python
handle_id = g.hivex_open(hive_path: str) -> int
```

Opens a Windows registry hive for reading. Downloads the hive from the guest filesystem to a temp file and opens it with python-hivex.

**Parameters:**
- `hive_path` — Guest filesystem path (e.g., `/Windows/System32/config/SYSTEM`)

**Returns:** Handle ID (integer) used for subsequent operations.

**Notes:**
- The hive is opened read-only
- Temp file is cleaned up on `hivex_close()`
- Sets the "last opened" handle for handle-less API calls

### hivex_close

```python
g.hivex_close(handle_id: int) -> None
```

Closes the hivex handle, releases the python-hivex object, and deletes the temp file.

### hivex_root

```python
root_node = g.hivex_root(handle_id: int) -> int
```

Returns the root node of the hive.

### hivex_node_get_child

```python
child = g.hivex_node_get_child(handle_id: int, node: int, name: str) -> int
```

Find a child node by name. Returns 0 if not found.

### hivex_node_children

```python
children = g.hivex_node_children(node: int) -> list
```

List all children of a node. **Handle-less** — uses the last-opened hive.

### hivex_node_name

```python
name = g.hivex_node_name(node: int) -> str
```

Get the name of a node. **Handle-less** — uses the last-opened hive.

### hivex_node_values

```python
values = g.hivex_node_values(node: int) -> list
```

List all values of a node. **Handle-less** — uses the last-opened hive.

### hivex_node_get_value

```python
value = g.hivex_node_get_value(handle_id: int, node: int, name: str)
```

Get a specific value by name from a node.

### hivex_value_key

```python
key_name = g.hivex_value_key(val: int) -> str
```

Get the key name of a value. **Handle-less**.

### hivex_value_type

```python
reg_type = g.hivex_value_type(val: int) -> int
```

Get the registry type of a value (1=REG_SZ, 2=REG_EXPAND_SZ, 4=REG_DWORD, 7=REG_MULTI_SZ). **Handle-less**.

### hivex_value_value

```python
data = g.hivex_value_value(val: int) -> bytes
```

Get the raw data bytes of a value. **Handle-less**.

### hivex_value_string

```python
text = g.hivex_value_string(handle_id: int, val: int) -> str
```

Get a string value. Handles REG_SZ, REG_EXPAND_SZ (UTF-16LE decode), REG_MULTI_SZ, and fallback UTF-8.

### hivex_commit

```python
g.hivex_commit(handle_id: int) -> None
```

No-op for read-only handles. The shim opens all hives as read-only.

## Handle-less vs Handle-based Methods

Some guestfs hivex methods require a handle parameter, others use an implicit "current hive." The VMCraft shim tracks the last-opened hive via `_hivex_last_handle`:

| Method | Handle | Notes |
|--------|--------|-------|
| `hivex_root` | Required | Explicit handle |
| `hivex_node_get_child` | Required | Explicit handle |
| `hivex_node_get_value` | Required | Explicit handle |
| `hivex_value_string` | Required | Explicit handle |
| `hivex_node_children` | Last-opened | Handle-less |
| `hivex_node_name` | Last-opened | Handle-less |
| `hivex_node_values` | Last-opened | Handle-less |
| `hivex_value_key` | Last-opened | Handle-less |
| `hivex_value_type` | Last-opened | Handle-less |
| `hivex_value_value` | Last-opened | Handle-less |

**Important:** When opening multiple hives (e.g., SYSTEM then SOFTWARE), handle-less methods operate on the *last-opened* hive. Close hives in reverse order to avoid confusion.

## Usage Example

```python
from h2kvm.vmcraft import VMCraft

with VMCraft() as g:
    g.add_disk("/vms/windows10.qcow2")
    g.launch()

    # Open SYSTEM hive
    h = g.hivex_open("/Windows/System32/config/SYSTEM")
    root = g.hivex_root(h)

    # Navigate to ControlSet001\Services
    cs = g.hivex_node_get_child(h, root, "ControlSet001")
    services = g.hivex_node_get_child(h, cs, "Services")

    # List all services
    for child in g.hivex_node_children(services):
        name = g.hivex_node_name(child)
        print(f"Service: {name}")

    g.hivex_close(h)
```

## Used By

These modules use the hivex API (works on both guestfs and VMCraft):

- `h2kvm/fixers/windows/rdp.py` — RDP verification (fDenyTSConnections)
- `h2kvm/fixers/windows/firewall.py` — Firewall service status check
- `h2kvm/fixers/windows/network_fixer.py` — TCP/IP config snapshot
- `h2kvm/fixers/windows/virtio/detection.py` — Windows build number from SOFTWARE hive
- `h2kvm/fixers/windows/virtio/install.py` — SYSTEM hive registry edits

## See Also

- [VMCraft Complete Guide](vmcraft.md)
- [Windows VirtIO Troubleshooting](../../guides/troubleshooting-windows-virtio.md)
- [Windows Migration Tutorial](../../tutorials/06-windows-migration.md)
