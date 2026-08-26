# Quick Reference - Orange Theme TUI & Progress Bars

## 🚀 Quick Start

### Run TUI Dashboard
```python
from hyper2kvm.tui import run_dashboard
run_dashboard()  # Auto-detects best implementation
```

### Use Progress Bar
```python
from hyper2kvm.core.progress import create_progress_bar

with create_progress_bar("Task name", total=100) as progress:
    for i in range(100):
        progress.update(i + 1)
```

## 🎨 Orange Theme Colors

| Name | Hex | Usage |
|------|-----|-------|
| Bright Orange | `#ff6600` | Headers, highlights |
| Gold-Orange | `#ffaa44` | Accents, borders |
| Light Orange | `#ffbb66` | Text |
| Success Green | `#66ff66` | Completed |
| Error Red | `#ff4444` | Failed |

## 📊 TUI Dashboard

### Import
```python
from hyper2kvm.tui import run_dashboard, get_dashboard_type, MigrationStatus
```

### Check Type
```python
dashboard_type = get_dashboard_type()
# Returns: 'textual' | 'curses' | 'cli'
```

### Create Migration Status
```python
migration = MigrationStatus(
    vm_name="web-server-01",
    hypervisor="vmware",
    status="in_progress",  # pending, in_progress, completed, failed
    progress=0.45,         # 0.0 to 1.0
    current_stage="export",
    throughput_mbps=150.5,
    elapsed_seconds=120.0,
)
```

### Control Dashboard
```python
# Textual
from hyper2kvm.tui.dashboard import MigrationDashboard
dashboard = MigrationDashboard(refresh_interval=1.0)

# Curses
from hyper2kvm.tui.fallback_dashboard import CursesDashboard
dashboard = CursesDashboard(refresh_interval=1.0)

# CLI
from hyper2kvm.tui.cli_dashboard import CLIDashboard
dashboard = CLIDashboard(refresh_interval=2.0)

# Operations (same for all)
dashboard.add_migration(migration)
dashboard.update_migration_progress(vm_name, 0.75, "convert", 180.0)
dashboard.log_message("Message", "INFO")  # INFO, WARNING, ERROR, SUCCESS
dashboard.remove_migration(vm_name)
```

### Keyboard Shortcuts

**Textual:**
- `q` - Quit | `r` - Refresh | `l` - Focus logs
- `m` - Focus migrations | `d` - Toggle dark mode

**Curses:**
- `q` - Quit | `r` - Refresh | `UP/DOWN` - Scroll

**CLI:**
- `Ctrl+C` - Quit

## 📈 Progress Bars

### Simple Usage
```python
from hyper2kvm.core.progress import create_progress_bar

with create_progress_bar("Description", total=100) as progress:
    progress.update(50)           # Set to 50%
    progress.advance(10)          # Add 10%
    progress.update(75, "Stage")  # Update with new description
```

### Custom Configuration
```python
from hyper2kvm.core.progress import SimpleProgressBar, ProgressBarConfig

config = ProgressBarConfig(
    width=40,           # Bar width in characters
    filled_char="█",    # Character for filled portion
    empty_char="░",     # Character for empty portion
    left_bracket="[",   # Left bracket
    right_bracket="]",  # Right bracket
    show_percentage=True,  # Show percentage
    show_spinner=True,     # Show spinner animation
    show_eta=True,         # Show ETA
    color_enabled=True,    # Use orange ANSI colors
)

progress = SimpleProgressBar(
    total=100,
    description="Exporting VM",
    config=config,
)

for i in range(101):
    progress.update(i)

progress.finish("Done!")
```

### Progress Manager (Auto-fallback)
```python
from hyper2kvm.core.progress import ProgressManager

# Uses Rich if available, otherwise SimpleProgressBar
with ProgressManager("Task", total=100) as progress:
    progress.update(50)
    progress.advance(25)
```

## 🎯 Installation

```bash
# Minimal (CLI only)
pip install hyper2kvm

# Recommended (with Textual)
pip install 'hyper2kvm[tui]'

# Full (all features)
pip install 'hyper2kvm[full]'
```

## 🔧 Optional Dependencies

| Feature | Package | Install |
|---------|---------|---------|
| Textual TUI | textual>=0.47.0 | `pip install textual` |
| Rich Progress | rich>=10.0.0 | `pip install rich` |
| Curses (Windows) | windows-curses | `pip install windows-curses` |

## 📝 Migration Status Fields

```python
@dataclass
class MigrationStatus:
    vm_name: str              # VM name
    hypervisor: str           # vmware, azure, hyperv
    status: str               # pending, in_progress, completed, failed
    progress: float           # 0.0 to 1.0
    current_stage: str        # export, transfer, convert, validate
    throughput_mbps: float    # MB/s
    elapsed_seconds: float    # Seconds elapsed
    eta_seconds: Optional[float]  # Estimated remaining (optional)
    error: Optional[str]      # Error message (optional)
```

## 🎨 ANSI Color Codes

```python
from hyper2kvm.core.progress import Colors

# Orange theme
Colors.BRIGHT_ORANGE  # \033[38;5;208m
Colors.GOLD_ORANGE    # \033[38;5;214m
Colors.LIGHT_ORANGE   # \033[38;5;216m

# Status colors
Colors.SUCCESS_GREEN  # \033[38;5;46m
Colors.ERROR_RED      # \033[38;5;196m
Colors.WARNING_YELLOW # \033[38;5;226m

# Styles
Colors.BOLD           # \033[1m
Colors.DIM            # \033[2m
Colors.RESET          # \033[0m

# Usage
print(f"{Colors.BRIGHT_ORANGE}Orange text{Colors.RESET}")
```

## 🧪 Examples

```bash
# TUI Demo
python examples/tui_demo.py

# Progress Bar Demo
python examples/progress_bar_demo.py

# Static Previews
python show_tui_preview.py
python show_implementations.py
python show_progress_bars.py
```

## 🏗️ Architecture

```
TUI:      Textual → Curses → CLI (automatic fallback)
Progress: Rich → SimpleProgressBar (automatic fallback)
Theme:    Orange (#ff6600) everywhere
```

## ✅ Tests

```bash
# Run TUI tests
pytest tests/unit/test_tui/test_tui_fallback.py -v

# Run progress tests
pytest tests/unit/test_core/test_progress.py -v

# Run all tests
pytest tests/unit/ -v
```

## 📚 Documentation

- `docs/TUI_IMPLEMENTATION.md` - Full TUI guide
- `docs/ORANGE_THEME.md` - Theme documentation
- `COMPLETE_SUMMARY.md` - Complete summary
- `ARCHITECTURE.md` - Architecture details
- `TUI_SUMMARY.md` - TUI overview

## 🔍 Troubleshooting

### Textual not found
```bash
pip install 'hyper2kvm[tui]'
```

### Curses not found (Windows)
```bash
pip install windows-curses
```

### No colors in terminal
```python
# Disable colors
config = ProgressBarConfig(color_enabled=False)
```

### Dashboard not starting
```python
# Check available type
from hyper2kvm.tui import get_dashboard_type
print(get_dashboard_type())  # Should show: textual, curses, or cli
```

## 💡 Common Patterns

### VM Migration with Progress
```python
from hyper2kvm.core.progress import create_progress_bar
from hyper2kvm.tui import MigrationDashboard

# Create dashboard
dashboard = MigrationDashboard()

# Add migration
migration = MigrationStatus(
    vm_name="server-01",
    hypervisor="vmware",
    status="in_progress",
    progress=0.0,
    current_stage="export",
)
dashboard.add_migration(migration)

# Show progress
with create_progress_bar("Exporting VM", total=100) as progress:
    for i in range(100):
        progress.update(i + 1)
        dashboard.update_migration_progress("server-01", i/100, "export")
```

### Batch Migration
```python
vms = ["vm1", "vm2", "vm3"]

with create_progress_bar("Batch Migration", total=len(vms)*100) as progress:
    for idx, vm in enumerate(vms):
        for step in range(100):
            current = idx * 100 + step + 1
            progress.update(current, f"Migrating {vm}")
```

### Error Handling
```python
try:
    with create_progress_bar("Task", total=100) as progress:
        # ... do work ...
        progress.update(100)
except Exception as e:
    dashboard.log_message(f"Error: {e}", "ERROR")
    migration.status = "failed"
    migration.error = str(e)
    dashboard.add_migration(migration)
```

## 🎊 Summary

✅ **TUI**: 3-tier fallback (Textual → Curses → CLI)
✅ **Progress**: 2-tier fallback (Rich → SimpleProgressBar)
✅ **Theme**: Orange (#ff6600) everywhere
✅ **Tests**: 38 passing tests
✅ **Docs**: Complete documentation
✅ **Platform**: Works on all platforms

---

For more details, see the complete documentation in `/docs/`.
