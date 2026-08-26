#!/bin/bash
# H2KVM System Limits Setup Script
#
# Configures system for reliable parallel VM conversions with NBD devices.
# Fixes "Too many open files" and NBD I/O errors.
#
# Usage:
#   sudo ./setup-system-limits.sh
#
# What it does:
#   1. Increases inotify limits
#   2. Increases file descriptor limits
#   3. Configures NBD module for 128 devices
#   4. Configures systemd resource limits
#   5. Applies changes immediately

set -e

# Colors for output

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: This script must be run as root"
  echo "Usage: sudo $0"
  exit 1
fi

echo "✅ =================================================="
echo "✅ H2KVM System Limits Setup"
echo "✅ =================================================="
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ETC_DIR="$(dirname "$SCRIPT_DIR")/etc"

# ========================================
# 1. Sysctl Configuration
# ========================================

echo "⚠️ [1/5] Configuring sysctl limits..."

SYSCTL_CONF="$ETC_DIR/sysctl.d/99-h2kvm-nbd.conf"

if [ -f "$SYSCTL_CONF" ]; then
  cp "$SYSCTL_CONF" /etc/sysctl.d/
  echo "  ✓ Installed /etc/sysctl.d/99-h2kvm-nbd.conf"

  # Apply immediately
  sysctl --system > /dev/null 2>&1
  echo "  ✓ Applied sysctl configuration"
else
  echo "❌   ✗ Configuration file not found: $SYSCTL_CONF"
  exit 1
fi

# ========================================
# 2. NBD Module Configuration
# ========================================

echo "⚠️ [2/5] Configuring NBD module..."

NBD_CONF="$ETC_DIR/modprobe.d/nbd.conf"

if [ -f "$NBD_CONF" ]; then
  cp "$NBD_CONF" /etc/modprobe.d/
  echo "  ✓ Installed /etc/modprobe.d/nbd.conf"

  # Reload NBD module
  if lsmod | grep -q nbd; then
    echo "  ⚠ NBD module is loaded, reloading..."
    modprobe -r nbd 2>/dev/null || echo "  ⚠ Cannot unload NBD (devices in use)"
  fi

  modprobe nbd
  echo "  ✓ Loaded NBD module with new configuration"

  # Verify
  NBDS_MAX=$(cat /sys/module/nbd/parameters/nbds_max 2>/dev/null || echo "unknown")
  MAX_PART=$(cat /sys/module/nbd/parameters/max_part 2>/dev/null || echo "unknown")
  echo "  ✓ NBD configuration: nbds_max=$NBDS_MAX, max_part=$MAX_PART"
else
  echo "❌   ✗ Configuration file not found: $NBD_CONF"
  exit 1
fi

# ========================================
# 3. Systemd Resource Limits
# ========================================

echo "⚠️ [3/5] Configuring systemd limits..."

SYSTEMD_CONF="$ETC_DIR/systemd/system.conf.d/h2kvm-limits.conf"

mkdir -p /etc/systemd/system.conf.d/

if [ -f "$SYSTEMD_CONF" ]; then
  cp "$SYSTEMD_CONF" /etc/systemd/system.conf.d/
  echo "  ✓ Installed /etc/systemd/system.conf.d/h2kvm-limits.conf"

  # Reload systemd
  systemctl daemon-reload
  echo "  ✓ Reloaded systemd configuration"
else
  echo "❌   ✗ Configuration file not found: $SYSTEMD_CONF"
  exit 1
fi

# ========================================
# 4. Cleanup Orphaned NBD Devices
# ========================================

echo "⚠️ [4/5] Cleaning up orphaned NBD devices..."

CLEANED=0
FORCE="${1:-}"
for i in /dev/nbd[0-9]*; do
  [ -b "$i" ] || continue
  # Skip partition devices (e.g. nbd0p1)
  [[ "$i" =~ p[0-9]+$ ]] && continue
  DEVNAME=$(basename "$i")
  PID_FILE="/sys/block/$DEVNAME/pid"
  if [ "$FORCE" = "--force" ]; then
    # Force mode: disconnect all NBD devices
    qemu-nbd --disconnect "$i" 2>/dev/null && ((CLEANED++)) || true
  elif [ -f "$PID_FILE" ]; then
    NBD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$NBD_PID" ] && ! kill -0 "$NBD_PID" 2>/dev/null; then
      # PID exists but process is gone — orphaned
      qemu-nbd --disconnect "$i" 2>/dev/null && ((CLEANED++)) || true
    fi
  fi
done

echo "  ✓ Cleaned up $CLEANED orphaned NBD devices"
if [ "$FORCE" != "--force" ]; then
  echo "  (use --force to disconnect all NBD devices including active ones)"
fi

# ========================================
# 5. Verify Configuration
# ========================================

echo "⚠️ [5/5] Verifying configuration..."

# Check inotify limits
INOTIFY_WATCHES=$(sysctl -n fs.inotify.max_user_watches)
INOTIFY_INSTANCES=$(sysctl -n fs.inotify.max_user_instances)
FILE_MAX=$(sysctl -n fs.file-max)

echo "  ✓ fs.inotify.max_user_watches = $INOTIFY_WATCHES"
echo "  ✓ fs.inotify.max_user_instances = $INOTIFY_INSTANCES"
echo "  ✓ fs.file-max = $FILE_MAX"

# Check NBD configuration
if [ -d /sys/module/nbd ]; then
  NBDS_MAX=$(cat /sys/module/nbd/parameters/nbds_max)
  MAX_PART=$(cat /sys/module/nbd/parameters/max_part)
  echo "  ✓ NBD: nbds_max=$NBDS_MAX, max_part=$MAX_PART"
fi

# Check systemd limits
NOFILE=$(systemctl show --property DefaultLimitNOFILE --value)
NPROC=$(systemctl show --property DefaultLimitNPROC --value)
echo "  ✓ Systemd: DefaultLimitNOFILE=$NOFILE, DefaultLimitNPROC=$NPROC"

echo
echo "✅ =================================================="
echo "✅ ✓ System configuration completed successfully!"
echo "✅ =================================================="
echo
echo "Summary:"
echo "  • Inotify watches: $INOTIFY_WATCHES"
echo "  • File descriptors: $FILE_MAX"
echo "  • NBD devices: $NBDS_MAX"
echo "  • Max partitions: $MAX_PART"
echo
echo "Changes are effective immediately."
echo
echo "⚠️ Recommended next steps:"
echo "  1. Verify with: ulimit -n"
echo "  2. Test NBD: qemu-nbd --connect=/dev/nbd0 test.vmdk"
echo "  3. Check limits: cat /proc/sys/fs/inotify/max_user_watches"
echo

exit 0
