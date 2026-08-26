#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Show static examples of progress bars with orange theme."""

print("=" * 80)
print("Orange Theme Progress Bars - Visual Examples".center(80))
print("=" * 80)
print()

print("📊 Progress Bar States (Orange Theme)")
print("-" * 80)
print()

# Show different progress states
examples = [
    (0, "Initializing migration"),
    (25, "Exporting VM from source"),
    (50, "Transferring disk image"),
    (75, "Converting to QCOW2"),
    (100, "Migration complete"),
]

for progress, description in examples:
    # Create visual bar
    filled = int(progress / 100 * 40)
    empty = 40 - filled

    if progress < 100:
        bar = f"[{'█' * filled}{'░' * empty}]"
    else:
        bar = f"[{'█' * filled}]"

    # Status symbol
    if progress == 0:
        symbol = "⏳"
    elif progress == 100:
        symbol = "✅"
    else:
        symbol = "🔄"

    print(f"  {symbol} {description:30} {progress:3d}% {bar}")

print()
print()

print("🎨 With Color Codes (Orange Theme)")
print("-" * 80)
print()

print("  Bright Orange Progress Bar:")
print("  \033[38;5;208m[████████████████████░░░░░░░░░░░░░░░░░░░░]\033[0m  50%")
print()

print("  With Brackets and Percentage:")
print(
    "  Exporting VM \033[38;5;214m[\033[0m\033[38;5;208m███████████\033[0m\033[2m░░░░░░░░░░░\033[0m\033[38;5;214m]\033[0m \033[1m\033[38;5;208m 50%\033[0m"
)
print()

print("  With Spinner:")
print(
    "  Converting disk \033[38;5;214m[\033[0m\033[38;5;208m████████████████\033[0m\033[2m░░░░░░\033[0m\033[38;5;214m]\033[0m \033[1m\033[38;5;208m 75%\033[0m \033[38;5;214m⠋\033[0m"
)
print()

print("  Completed:")
print(
    "  Migration \033[38;5;214m[\033[0m\033[38;5;208m██████████████████████\033[0m\033[38;5;214m]\033[0m \033[1m\033[38;5;208m100%\033[0m \033[38;5;46m✓ Done!\033[0m"
)
print()

print()
print("🔢 Custom Characters")
print("-" * 80)
print()

# Different bar styles
styles = [
    ("Block", "█", "░"),
    ("Equals", "=", " "),
    ("Hash", "#", "-"),
    ("Dot", "●", "○"),
]

for name, filled_char, empty_char in styles:
    filled = filled_char * 20
    empty = empty_char * 20
    print(f"  {name:10} [{filled}{empty}]  50%")

print()
print()

print("🌈 Status-Based Colors")
print("-" * 80)
print()

statuses = [
    ("Pending", 0, "⏳", "\033[38;5;208m"),  # Orange
    ("In Progress", 45, "🔄", "\033[38;5;214m"),  # Gold-Orange
    ("Almost Done", 90, "🔄", "\033[38;5;216m"),  # Light Orange
    ("Completed", 100, "✅", "\033[38;5;46m"),  # Green
    ("Failed", 30, "❌", "\033[38;5;196m"),  # Red
]

for status, progress, symbol, color in statuses:
    filled = int(progress / 100 * 30)
    empty = 30 - filled
    bar = f"{color}[{'█' * filled}{'░' * empty}]\033[0m"
    print(f"  {symbol} {status:15} {progress:3d}% {bar}")

print()
print()

print("💡 Usage Examples")
print("-" * 80)
print()

print("  Python code:")
print("  " + "-" * 70)
print("""
  from h2kvm.core.progress import create_progress_bar

  # Automatic detection (uses Rich if available, otherwise fallback)
  with create_progress_bar("Migrating VM", total=100) as progress:
      for i in range(100):
          progress.update(i + 1)

  # Or use simple progress bar directly
  from h2kvm.core.progress import SimpleProgressBar, ProgressBarConfig

  config = ProgressBarConfig(
      width=40,
      show_percentage=True,
      show_spinner=True,
      show_eta=True,
  )

  progress = SimpleProgressBar(
      total=100,
      description="Exporting VM",
      config=config,
  )

  for i in range(101):
      progress.update(i)

  progress.finish("Export completed!")
""")

print()
print("=" * 80)
print("Features".center(80))
print("=" * 80)
print()

features = [
    "✅ Works with or without Rich library",
    "✅ Orange theme consistent across implementations",
    "✅ ANSI color support (auto-detects terminal capability)",
    "✅ Customizable characters and width",
    "✅ Optional spinner animation",
    "✅ Optional ETA display",
    "✅ Multiple status colors (success, error, in-progress)",
    "✅ Percentage display",
    "✅ Description text",
]

for feature in features:
    print(f"  {feature}")

print()
print("=" * 80)
