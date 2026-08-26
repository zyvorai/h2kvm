#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Show comparison of the three TUI implementations.
"""

print("=" * 80)
print("TUI Implementation Comparison - Orange Theme".center(80))
print("=" * 80)
print()

# Tier 1: Textual
print("🥇 TIER 1: TEXTUAL DASHBOARD (Best Experience)")
print("-" * 80)
print("""
Features:
  ✅ Full CSS-based orange theme with gradients
  ✅ Reactive widgets (auto-update on data change)
  ✅ Smooth animations and transitions
  ✅ Interactive elements (scrollable, focusable)
  ✅ Async/await support for background tasks
  ✅ Rich widget library (DataTable, ProgressBar, Log)

Installation: pip install 'hyper2kvm[tui]'

Visual:
╔══════════════════════════════════════════════════════════════════════════════╗
║ [BRIGHT ORANGE HEADER #ff6600]  hyper2kvm Dashboard | 14:23:45              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  📦 Active Migrations [GOLD-ORANGE #ffaa44]                                  ║
║  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ [LIGHT ORANGE BORDER #ff8833]  ║
║  ┃ 🔄 web-server-01 (vmware)              ┃ [LIGHT ORANGE TEXT #ffbb66]    ║
║  ┃ Stage: export | 45% [████░░░░░░░░░]    ┃ [DARK BROWN BG #331a00]        ║
║  ┃ Throughput: 150.5 MB/s | 2m 0s          ┃                                ║
║  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛                                ║
║                                                                              ║
║  ┏━━━━━━━━━━━━━━━━┓ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓                    ║
║  ┃ 📊 Metrics     ┃ ┃ 📝 Logs                         ┃                    ║
║  ┃ ────────────── ┃ ┃ [14:23] ✅ Dashboard initialized┃                    ║
║  ┃ Active:     1  ┃ ┃ [14:24] 🔄 Migration started    ┃                    ║
║  ┃ Total:      4  ┃ ┃ [14:25] 📊 Progress: 45%        ┃                    ║
║  ┗━━━━━━━━━━━━━━━━┛ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛                    ║
║                                                                              ║
║ [DARK BROWN STATUS BAR #331a00] Active: 1 | Press 'q' to quit              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ [BRIGHT ORANGE FOOTER] q Quit│r Refresh│l Logs│m Migrations│d Dark Mode     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Keyboard Shortcuts:
  q - Quit   r - Refresh   l - Focus logs   m - Focus migrations   d - Dark mode
""")
print()

# Tier 2: Curses
print("🥈 TIER 2: CURSES DASHBOARD (Good Experience)")
print("-" * 80)
print("""
Features:
  ✅ Orange theme using ANSI colors (yellow/orange approximation)
  ✅ No external dependencies (built-in Python)
  ✅ Live updates with color support
  ✅ Keyboard navigation
  ✅ Lightweight and fast

Installation: Built-in on Linux/macOS/Unix
             Windows: pip install windows-curses

Visual (using terminal colors):
╔══════════════════════════════════════════════════════════════════════════════╗
║ [YELLOW BG] hyper2kvm Migration Dashboard | 14:23:45 [/YELLOW]              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║ === METRICS ===                                                              ║
║   Active Migrations:     1                                                   ║
║   Total Migrations:      4 (Success: 1 | Failed: 1)                          ║
║   Success Rate:          25.0%                                               ║
║   Avg Throughput:        165.3 MB/s                                          ║
║   Data Processed:        5.00 GB                                             ║
║                                                                              ║
║ === ACTIVE MIGRATIONS ===                                                    ║
║   [YELLOW]web-server-01          [IN-PROG]  45% [=======        ][/YELLOW]  ║
║     Stage: export                    | 150.5 MB/s                            ║
║   [GREEN]database-server         [DONE   ] 100% [===============][/GREEN]   ║
║     Stage: complete                  | 180.2 MB/s                            ║
║   [RED]app-server-03            [FAILED ]  30% [====           ][/RED]      ║
║     Stage: convert                   | N/A                                   ║
║                                                                              ║
║ === LOGS ===                                                                 ║
║   [14:23:30] [INFO] Dashboard initialized                                    ║
║   [14:23:35] [INFO] Waiting for migrations...                                ║
║   [14:23:40] [INFO] web-server-01: in_progress - export                      ║
║                                                                              ║
║ [YELLOW BG] Press 'q' to quit | 'r' to refresh | UP/DOWN to scroll          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Keyboard Shortcuts:
  q - Quit   r - Refresh   UP/DOWN - Scroll logs
""")
print()

# Tier 3: CLI
print("🥉 TIER 3: CLI DASHBOARD (Universal Fallback)")
print("-" * 80)
print("""
Features:
  ✅ Works everywhere (Windows, Linux, macOS, CI/CD)
  ✅ Simple terminal output
  ✅ ASCII progress bars
  ✅ No dependencies required
  ✅ Periodic refresh (reduces flicker)

Installation: Always available!

Visual:
================================================================================
                   hyper2kvm Migration Dashboard - 14:23:45
================================================================================

[METRICS]
--------------------------------------------------------------------------------
  Active Migrations:     1
  Total Migrations:      4 (Success: 1 | Failed: 1)
  Success Rate:          25.0%
  Avg Throughput:        165.3 MB/s
  Data Processed:        5.00 GB

[ACTIVE MIGRATIONS]
--------------------------------------------------------------------------------

  web-server-01 (vmware)
  Status: 🔄 IN-PROGRESS
  Progress:  45% [=============                 ]
  Stage: export
  Throughput: 150.5 MB/s
  Elapsed: 2m 0s

  database-server (vmware)
  Status: ✅ COMPLETED
  Progress: 100% [==============================]
  Stage: complete
  Throughput: 180.2 MB/s
  Elapsed: 5m 0s

  app-server-03 (azure)
  Status: ❌ FAILED
  Progress:  30% [=========                     ]
  Stage: convert
  Error: Disk conversion failed: Invalid format

[RECENT LOGS]
--------------------------------------------------------------------------------
  [14:23:30] [INFO] Dashboard initialized
  [14:23:35] [INFO] Waiting for migrations...
  [14:23:40] [INFO] web-server-01: in_progress - export
  [14:23:42] [INFO] Metrics updated
  [14:23:45] [INFO] Progress: 45%

================================================================================
                          Press Ctrl+C to quit
================================================================================

Keyboard Shortcuts:
  Ctrl+C - Quit
""")
print()

# Summary
print("=" * 80)
print("SUMMARY".center(80))
print("=" * 80)
print("""
All three implementations share:
  ✅ Orange theme (adapted to platform capabilities)
  ✅ Same data model (MigrationStatus)
  ✅ Same API (add_migration, update_progress, log_message)
  ✅ Real-time updates
  ✅ Progress tracking
  ✅ Metrics dashboard
  ✅ Log viewer

The TUI is now a standalone Go binary (zkvm) using Bubble Tea.
It communicates with the Python backend via Unix socket + JSON protocol.

Usage:
  h2kvmctl --zkvm             # Launch TUI (starts backend + Go TUI)
  h2kvmctl --zkvm-server      # Start socket server only
  zkvm                        # Run Go TUI standalone
""")
print("=" * 80)
