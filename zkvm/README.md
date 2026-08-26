# zkvm — Terminal UI for hyper2kvm

Interactive TUI built with [Bubble Tea](https://github.com/charmbracelet/bubbletea) for managing VM migrations from the terminal.

## Features

- **Standalone mode** — form-based migration wizard with real-time log output
- **vSphere integration** — auto-discover VMs and datastores from vCenter via govc
- **Windows support** — VirtIO driver injection, two-phase boot configuration
- **KubeVirt deployment** — deploy converted VMs to Kubernetes
- **Libvirt management** — view and manage VMs via virsh
- **Multi-tab UI** — Home, Dashboard, Wizard, Browser, Migrations, Batch, Settings
- **Profiles** — save and load reusable migration configurations
- **Cross-platform** — builds for Linux (amd64/arm64) and macOS (amd64/arm64)

## Quick Start

### Build

```bash
cd zkvm
make build
```

### Run (Standalone Mode)

```bash
# Interactive form
./zkvm -s

# Pre-fill with VMDK path
./zkvm -s --vmdk /path/to/disk.vmdk

# Pre-fill for vSphere export
./zkvm -s --cmd vsphere --vcenter 10.73.213.134 --vc-user admin@vsphere.local --dc-name data --vm-name my-vm

# Specify h2kvmctl binary path
./zkvm -s --binary /usr/local/bin/h2kvmctl
```

### Run (Tabbed Mode — requires backend socket)

```bash
# Auto-detect socket
./zkvm

# Demo mode (no backend)
./zkvm --no-connect
```

## CLI Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--standalone` | `-s` | Run standalone mode (form + log pane) |
| `--no-connect` | `-n` | Start without backend connection (demo mode) |
| `--socket PATH` | `-S` | Unix socket path for backend |
| `--binary PATH` | `-b` | Path to h2kvmctl binary |
| `--cmd CMD` | `-c` | Pre-fill command type (local, vsphere, etc.) |
| `--vmdk PATH` | `-m` | Pre-fill VMDK path |
| `--output-dir DIR` | `-o` | Pre-fill output directory |
| `--vcenter HOST` | | Pre-fill vCenter hostname |
| `--vc-user USER` | | Pre-fill vCenter username |
| `--dc-name NAME` | | Pre-fill datacenter name |
| `--vm-name NAME` | | Pre-fill VM name |
| `--version` | `-v` | Print version |

## Environment Variables

zkvm auto-reads vSphere credentials from environment variables — no manual typing needed:

| Env Var | Maps to | Example |
|---------|---------|---------|
| `GOVC_URL` | vCenter Host (strips `https://` and `/sdk`) | `https://10.73.213.134/sdk` |
| `GOVC_USERNAME` | Username | `administrator@vsphere.local` |
| `GOVC_PASSWORD` | Password | `VCENTER@redhat2025` |
| `VC_PASSWORD` | Password (fallback) | `VCENTER@redhat2025` |
| `GOVC_DATACENTER` | Datacenter | `data` |
| `GOVC_INSECURE` | Insecure toggle (if `1`) | `1` |

```bash
# Set env vars once
export GOVC_URL='https://10.73.213.134/sdk'
export GOVC_USERNAME='administrator@vsphere.local'
export GOVC_PASSWORD='VCENTER@redhat2025'
export GOVC_INSECURE=1
export GOVC_DATACENTER='data'

# zkvm auto-fills all vSphere fields
./zkvm -s

# Or with CLI flag overrides (take priority over env vars)
./zkvm -s --vcenter 10.0.0.1 --dc-name Production-DC
```

Works in both standalone form and Settings → vSphere tab.

## Keyboard Shortcuts (vSphere)

| Key | Action |
|-----|--------|
| `Ctrl+D` | Discover VMs from vCenter (fills vm_name dropdown) |
| `Ctrl+R` | Run migration |
| `Ctrl+P` | Save profile |
| `Ctrl+L` | Load profile |

## Form Categories

The standalone migration form has 10 categories:

1. **Command Type** — local, ova, ovf, vsphere, azure, fetch-and-fix, live-fix
2. **Source** — VMDK/OVA/OVF path, SSH host (fetch/live-fix)
3. **Output** — format (qcow2/raw), compress, flatten, checksum
4. **Offline Fixes** — backend, fstab_mode, initramfs, grub, vmware-tools
5. **Libvirt / Testing** — emit XML, virsh define, memory, vcpus, UEFI, boot test
6. **Advanced** — dry-run, verbose, log file, parallel, workers
7. **vSphere** — vcenter, credentials, vs_action, govc settings, export mode
8. **Azure** — resource group, VM names, snapshots, subscription
9. **Windows** — VirtIO ISO, win_stage (bootstrap/final), clock
10. **Kubernetes / KubeVirt** — deploy_k8s, namespace, PVC size, memory, CPU

Categories 7-8 only appear when the matching command type is selected.

## vSphere Auto-Discovery

When the vSphere category is configured, zkvm can auto-discover VMs and datastores:

```go
// List all VMs in datacenter
vms, err := DiscoverVMs(form)

// Get detailed VM info
info, err := DiscoverVMsDetailed(form, "my-vm")
// info.Name, info.GuestName, info.MemoryMB, info.NumCPU, info.PowerState

// List datastores
dss, err := DiscoverDatastores(form)
// ds.Name, ds.Type, ds.Capacity, ds.Free
```

Requires `govc` in PATH. Uses form field values (vcenter, vc_user, vc_password, dc_name) to build GOVC_* environment variables automatically.

## Build for macOS

```bash
# Build for macOS ARM (Apple Silicon)
make build-macos

# Or cross-compile all platforms
make cross-compile
# Produces: zkvm-linux-amd64, zkvm-linux-arm64, zkvm-darwin-amd64, zkvm-darwin-arm64
```

## Architecture

```
zkvm/
├── main.go                         # Entry point, flag parsing
├── internal/
│   ├── models/                     # Data models (migration, config, stats)
│   ├── protocol/                   # Unix socket JSON protocol
│   ├── state/                      # Global state store
│   ├── theme/                      # Color themes
│   ├── widgets/                    # Reusable UI widgets
│   └── ui/
│       ├── app.go                  # Main tabbed app
│       ├── styles.go               # Lipgloss styles
│       ├── home/                   # Home tab
│       ├── dashboard/              # Dashboard tab
│       ├── wizard/                 # Migration wizard tab
│       ├── browser/                # VM browser tab
│       ├── migrations/             # Active migrations tab
│       ├── batch/                  # Batch operations tab
│       ├── settings/               # Settings tab
│       ├── help/                   # Help overlay
│       └── standalone/             # Standalone mode
│           ├── standalone.go       # Main standalone model
│           ├── form.go             # Form fields + categories
│           ├── runner.go           # h2kvmctl subprocess runner
│           ├── pipeline.go         # Pipeline progress tracking
│           ├── profiles.go         # Save/load profiles
│           ├── virsh.go            # virsh integration
│           ├── libvirt.go          # Libvirt VM management
│           ├── kubernetes.go       # KubeVirt integration
│           └── vsphere_discover.go # vSphere VM/DS discovery
└── Makefile
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Switch between tabs |
| `↑` / `↓` / `j` / `k` | Navigate fields |
| `Enter` | Edit field / expand category |
| `Space` | Toggle boolean fields |
| `Ctrl+R` | Run migration |
| `Ctrl+S` | Save profile |
| `Ctrl+L` | Load profile |
| `Ctrl+C` / `q` | Quit |
| `?` | Show help |
