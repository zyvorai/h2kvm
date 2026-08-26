#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Example pre-fix hook: Create backup of source disk before modification

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <source_disk> <backup_directory>" >&2
    exit 1
fi

SOURCE_DISK="$1"
BACKUP_DIR="$2"

echo "═══════════════════════════════════════════════════════════"
echo "💾 Creating Disk Backup"
echo "═══════════════════════════════════════════════════════════"
echo "Source:       $SOURCE_DISK"
echo "Backup Dir:   $BACKUP_DIR"
echo "═══════════════════════════════════════════════════════════"

# Verify source disk exists
if [ ! -f "$SOURCE_DISK" ]; then
    echo "❌ Error: Source disk not found: $SOURCE_DISK" >&2
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DISK_BASENAME=$(basename "$SOURCE_DISK")
BACKUP_FILE="$BACKUP_DIR/${DISK_BASENAME}.backup.$TIMESTAMP"

# Create backup using cp with progress (if pv is available)
if command -v pv &> /dev/null; then
    echo "📦 Creating backup with progress..."
    pv "$SOURCE_DISK" > "$BACKUP_FILE"
else
    echo "📦 Creating backup (install 'pv' for progress display)..."
    cp "$SOURCE_DISK" "$BACKUP_FILE"
fi

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE")
    SOURCE_SIZE=$(stat -c%s "$SOURCE_DISK")

    if [ "$BACKUP_SIZE" -eq "$SOURCE_SIZE" ]; then
        echo "✅ Backup created successfully: $BACKUP_FILE"
        echo "   Size: $(numfmt --to=iec-i --suffix=B $BACKUP_SIZE)"
        exit 0
    else
        echo "❌ Error: Backup size mismatch" >&2
        echo "   Source: $SOURCE_SIZE bytes" >&2
        echo "   Backup: $BACKUP_SIZE bytes" >&2
        exit 1
    fi
else
    echo "❌ Error: Backup file not created" >&2
    exit 1
fi
