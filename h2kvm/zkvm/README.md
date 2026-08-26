# h2kvm zkvm - Backend Components

This package contains the Python backend components for the h2kvm TUI.

The TUI itself is a standalone Go binary (`zkvm`) built with
[Bubble Tea](https://github.com/charmbracelet/bubbletea). It communicates
with the Python backend via a Unix domain socket using a newline-delimited
JSON protocol.

## Architecture

```
+----------------------+       Unix Socket        +----------------------+
|   zkvm (Go)          |<========================>|  h2kvmctl (Python)   |
|   Bubble Tea UI      |   JSON messages          |  Migration backend   |
|   Lipgloss styling   |                          |  Socket server       |
+----------------------+                          +----------------------+
```

## Components

### Backend (this package)

- **`socket_server.py`** - Asyncio Unix socket server for TUI communication
- **`migration_tracker.py`** - Migration state and history tracking
- **`migration_controller.py`** - Process control (pause/resume/cancel)
- **`zkvm_config.py`** - zkvm configuration management
- **`types.py`** - Shared type definitions

### Go TUI (`zkvm/` at project root)

The Go TUI source is in `zkvm/` at the project root. Build with:

```bash
cd zkvm && make build
```

## Usage

```bash
# Launch TUI (starts backend + Go TUI)
h2kvmctl --zkvm

# Start socket server only (for external TUI clients)
h2kvmctl --zkvm-server

# Run Go TUI standalone (connects to existing socket server)
zkvm

# Run Go TUI in demo mode (no backend connection)
zkvm --no-connect
```

## Socket Path

- Root: `/run/h2kvm/zkvm.sock`
- User: `$XDG_RUNTIME_DIR/h2kvm/zkvm.sock`
- Custom: `h2kvmctl --zkvm-socket /path/to/sock`

## Keyboard Shortcuts

| Key       | Action          |
|-----------|-----------------|
| Ctrl+Q    | Quit            |
| F1        | Help overlay    |
| F2        | Quick wizard    |
| F3        | Browse VMs      |
| F5        | Refresh         |
| Ctrl+S    | Settings        |
| Tab       | Next tab        |
| Shift+Tab | Previous tab    |
| j/k       | Scroll down/up  |
| Enter     | Select/confirm  |
| Esc       | Back/close      |
