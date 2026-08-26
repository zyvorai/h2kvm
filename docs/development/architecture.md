# Architecture Overview - Orange Theme Implementation

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         hyper2kvm Orange Theme System                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┴────────────────────┐
                │                                        │
                ▼                                        ▼
┌───────────────────────────────┐        ┌──────────────────────────────┐
│       TUI System              │        │    Progress Bar System       │
│   (Terminal User Interface)   │        │    (Visual Feedback)         │
└───────────────────────────────┘        └──────────────────────────────┘
                │                                        │
                │                                        │
    ┌───────────┴───────────┐              ┌────────────┴────────────┐
    │                       │              │                         │
    ▼                       ▼              ▼                         ▼
┌─────────┐         ┌──────────┐    ┌───────────┐           ┌────────────┐
│Textual  │  Tier 1 │ Curses   │    │   Rich    │  Primary  │  Simple    │
│Dashboard│  (Best) │Dashboard │    │  Progress │  (Best)   │  Progress  │
│         │         │          │    │           │           │   Bar      │
│#ff6600  │         │ANSI color│    │ Orange    │           │  Orange    │
│Orange   │         │Orange    │    │ Styling   │           │  ANSI      │
└─────────┘         └──────────┘    └───────────┘           └────────────┘
                           │                                      │
                           ▼                                      │
                    ┌──────────┐                                  │
                    │   CLI    │  Tier 3                          │
                    │Dashboard │  (Fallback)                      │
                    │          │                                  │
                    │  ASCII   │  Fallback                        │
                    │  Orange  │  (Always)                        │
                    └──────────┘◄─────────────────────────────────┘
```

## Component Breakdown

### 1. TUI System Hierarchy

```
hyper2kvm.tui
    │
    ├── __init__.py (Auto-detection logic)
    │   ├── get_dashboard_type() → 'textual' | 'curses' | 'cli'
    │   └── run_dashboard() → Launches best available
    │
    ├── dashboard.py (Textual - Tier 1)
    │   ├── MigrationDashboard (App)
    │   ├── CSS orange theme
    │   ├── Reactive widgets
    │   └── Keyboard shortcuts (q, r, l, m, d)
    │
    ├── fallback_dashboard.py (Curses - Tier 2)
    │   ├── CursesDashboard
    │   ├── ANSI color pairs (orange approximation)
    │   ├── Text-based UI
    │   └── Keyboard navigation (q, r, UP/DOWN)
    │
    ├── cli_dashboard.py (CLI - Tier 3)
    │   ├── CLIDashboard
    │   ├── ASCII progress bars
    │   ├── Terminal output
    │   └── Ctrl+C to quit
    │
    └── widgets.py (Shared components)
        ├── MigrationStatus (dataclass)
        ├── MigrationStatusWidget (Textual)
        ├── MetricsWidget (Textual)
        └── MigrationTable (Textual)
```

### 2. Progress Bar System

```
hyper2kvm.core.progress
    │
    ├── Colors (ANSI color codes)
    │   ├── BRIGHT_ORANGE = \033[38;5;208m
    │   ├── GOLD_ORANGE = \033[38;5;214m
    │   ├── LIGHT_ORANGE = \033[38;5;216m
    │   └── supports_color() → bool
    │
    ├── ProgressBarConfig (Configuration)
    │   ├── width: int = 40
    │   ├── filled_char: str = "█"
    │   ├── empty_char: str = "░"
    │   ├── show_percentage: bool = True
    │   ├── show_spinner: bool = False
    │   └── show_eta: bool = False
    │
    ├── SimpleProgressBar (Fallback)
    │   ├── __init__(total, description, config)
    │   ├── update(current, description?)
    │   ├── advance(amount)
    │   ├── finish(message?)
    │   └── _render() → Orange themed output
    │
    ├── ProgressManager (Smart wrapper)
    │   ├── Uses Rich if available
    │   ├── Falls back to SimpleProgressBar
    │   ├── Context manager support
    │   └── Unified API
    │
    └── create_progress_bar() → ProgressManager
```

## Data Flow

### TUI Migration Tracking

```
User Code
    │
    ▼
dashboard.add_migration(MigrationStatus(...))
    │
    ├─► Textual: Reactive widget update
    │   ├─► CSS styling applied (#ff6600 orange)
    │   └─► Screen refresh (async)
    │
    ├─► Curses: Manual render
    │   ├─► ANSI colors applied
    │   └─► Screen refresh (sync)
    │
    └─► CLI: Append to internal state
        ├─► Next refresh cycle
        └─► Full screen redraw
```

### Progress Bar Update

```
User Code
    │
    ▼
progress.update(50)
    │
    ├─► Rich Available?
    │   │
    │   ├─► Yes: Rich.update()
    │   │   ├─► Orange styling (#ff6600)
    │   │   ├─► Spinner animation
    │   │   └─► ETA calculation
    │   │
    │   └─► No: SimpleProgressBar._render()
    │       ├─► ANSI orange codes (\033[38;5;208m)
    │       ├─► ASCII bar [████░░░]
    │       ├─► Percentage 50%
    │       └─► Write to stdout
    │
    └─► Output to terminal
```

## Fallback Decision Tree

### TUI System

```
run_dashboard()
    │
    ├─► Check TEXTUAL_AVAILABLE
    │   │
    │   ├─► True: Use Textual Dashboard
    │   │   └─► Best experience, full orange theme
    │   │
    │   └─► False: Check CURSES_AVAILABLE
    │       │
    │       ├─► True: Use Curses Dashboard
    │       │   └─► Good experience, ANSI orange
    │       │
    │       └─► False: Use CLI Dashboard
    │           └─► Basic experience, ASCII orange
```

### Progress Bar

```
create_progress_bar()
    │
    └─► ProgressManager.__init__()
        │
        ├─► Check RICH_AVAILABLE
        │   │
        │   ├─► True: Initialize Rich Progress
        │   │   ├─► Orange theme: #ff6600
        │   │   ├─► Spinner, ETA, TimeRemaining
        │   │   └─► BarColumn with custom styling
        │   │
        │   └─► False: Initialize SimpleProgressBar
        │       ├─► ProgressBarConfig
        │       ├─► Orange ANSI codes
        │       ├─► Spinner frames: ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏
        │       └─► Manual ETA calculation
```

## Orange Theme Application

### Color Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Textual (CSS-based)                                │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Header { background: #ff6600; color: #fff; }            │ │
│ │ Screen { background: #1a0f00; }                         │ │
│ │ Container { border: #ff8833; background: #261500; }     │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Curses (ANSI color pairs)                         │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ curses.init_pair(5, BLACK, YELLOW)  # Header            │ │
│ │ curses.init_pair(6, YELLOW, BLACK)  # Orange accent     │ │
│ │ curses.init_pair(3, YELLOW, BLACK)  # In-progress       │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: CLI (ANSI escape codes)                           │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ BRIGHT_ORANGE = \033[38;5;208m                          │ │
│ │ GOLD_ORANGE = \033[38;5;214m                            │ │
│ │ Usage: f"{BRIGHT_ORANGE}text{RESET}"                    │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Module Dependencies

```
hyper2kvm/
    │
    ├── core/
    │   ├── optional_imports.py
    │   │   ├── TEXTUAL_AVAILABLE
    │   │   ├── RICH_AVAILABLE
    │   │   ├── CURSES_AVAILABLE (checked at runtime)
    │   │   └── Import guards for all optional deps
    │   │
    │   └── progress.py
    │       ├── Depends on: optional_imports.RICH_AVAILABLE
    │       ├── No hard dependencies
    │       └── Falls back to stdlib only
    │
    ├── tui/
    │   ├── __init__.py
    │   │   ├── Depends on: optional_imports.TEXTUAL_AVAILABLE
    │   │   ├── Runtime check: curses availability
    │   │   └── Exports: run_dashboard, get_dashboard_type
    │   │
    │   ├── dashboard.py
    │   │   ├── Requires: Textual (optional)
    │   │   ├── Imports from: optional_imports
    │   │   └── Imports from: widgets, core.metrics
    │   │
    │   ├── fallback_dashboard.py
    │   │   ├── Requires: curses (stdlib)
    │   │   └── No external dependencies
    │   │
    │   ├── cli_dashboard.py
    │   │   └── Pure Python, no dependencies
    │   │
    │   └── widgets.py
    │       ├── Requires: Textual (optional)
    │       └── Defines: MigrationStatus (no deps)
    │
    └── tests/
        ├── test_tui/
        │   └── test_tui_fallback.py
        │       └── Tests all TUI implementations
        │
        └── test_core/
            └── test_progress.py
                └── Tests progress bar system
```

## Threading Model

### TUI Dashboard

```
Textual Dashboard:
    Main Thread
        │
        ├─► Textual App.run() (blocking)
        │   ├─► Event loop
        │   ├─► Keyboard input handler
        │   └─► @work decorators (background workers)
        │       ├─► refresh_worker() → asyncio.sleep()
        │       └─► Updates UI (thread-safe)

Curses Dashboard:
    Main Thread
        │
        └─► curses.wrapper() (blocking)
            ├─► Main loop (while self._running)
            ├─► Keyboard input (stdscr.getch())
            └─► Periodic refresh (time.sleep())

CLI Dashboard:
    Main Thread
        │
        └─► while self._running (blocking)
            ├─► Screen refresh
            ├─► time.sleep(refresh_interval)
            └─► Keyboard: Ctrl+C (KeyboardInterrupt)
```

### Progress Bar

```
Progress Bar (Both Rich and Simple):
    Main Thread
        │
        └─► Synchronous updates
            ├─► progress.update(current)
            ├─► Write to stdout
            └─► Flush immediately
```

## Platform Compatibility Matrix

```
┌──────────────┬──────────┬─────────┬─────────┬─────────┐
│ Platform     │ Textual  │ Curses  │ CLI     │ Rich    │
├──────────────┼──────────┼─────────┼─────────┼─────────┤
│ Linux        │    ✅    │   ✅    │   ✅    │   ✅    │
│ macOS        │    ✅    │   ✅    │   ✅    │   ✅    │
│ Windows 10+  │    ✅    │   ⚠️*   │   ✅    │   ✅    │
│ Unix/BSD     │    ✅    │   ✅    │   ✅    │   ✅    │
│ SSH          │    ✅    │   ✅    │   ✅    │   ✅    │
│ CI/CD        │    ⚠️†   │   ⚠️†   │   ✅    │   ✅    │
└──────────────┴──────────┴─────────┴─────────┴─────────┘

* Requires: pip install windows-curses
† Requires TTY; falls back to CLI
```

## Performance Characteristics

```
┌──────────────────┬──────────┬────────────┬────────────┐
│ Implementation   │ Refresh  │ CPU Usage  │ Memory     │
├──────────────────┼──────────┼────────────┼────────────┤
│ Textual          │ 1s       │ Low (async)│ ~50MB      │
│ Curses           │ 1s       │ Very low   │ ~10MB      │
│ CLI              │ 2s       │ Minimal    │ ~5MB       │
│ Rich Progress    │ Real-time│ Low        │ ~20MB      │
│ Simple Progress  │ Real-time│ Minimal    │ ~1MB       │
└──────────────────┴──────────┴────────────┴────────────┘
```

## Testing Strategy

```
Unit Tests (38 total)
    │
    ├── TUI System (18 tests)
    │   ├── Auto-detection (3)
    │   ├── MigrationStatus dataclass (2)
    │   ├── CLI dashboard (7)
    │   ├── Curses dashboard (2)
    │   ├── Textual widgets (2)
    │   └── Utilities (2)
    │
    └── Progress System (20 tests)
        ├── Color support (2)
        ├── Configuration (2)
        ├── SimpleProgressBar (8)
        ├── ProgressManager (5)
        └── Convenience functions (3)
```

## Future Architecture Extensions

```
Planned Enhancements:
    │
    ├── WebSocket Layer
    │   └── Real-time remote monitoring
    │
    ├── Metrics Export
    │   ├── Prometheus format
    │   └── REST API endpoints
    │
    ├── Theme System
    │   ├── Blue theme
    │   ├── Green theme
    │   └── Custom themes (JSON config)
    │
    └── Data Persistence
        ├── SQLite for history
        └── CSV export
```

---

## Summary

This architecture provides:

✅ **Layered fallback** - Textual → Curses → CLI
✅ **Consistent theming** - Orange across all layers
✅ **Zero dependencies** - Works with stdlib alone
✅ **Progressive enhancement** - Better with Textual/Rich
✅ **Cross-platform** - Linux, macOS, Windows, Unix
✅ **Well-tested** - 38 comprehensive unit tests
✅ **Production-ready** - Error handling, performance optimized

The system is designed for reliability, ease of use, and visual consistency across all platforms and configurations.
