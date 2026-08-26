# Systemd Integration Guide

Complete guide to H2KVM's deep systemd integration for production deployments.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Systemd Units](#systemd-units)
- [Resource Control](#resource-control)
- [Socket Activation](#socket-activation)
- [Path Monitoring](#path-monitoring)
- [Journal Integration](#journal-integration)
- [Troubleshooting](#troubleshooting)
- [Advanced Topics](#advanced-topics)

## Overview

H2KVM provides deep integration with systemd, enabling production-grade VM boot repair operations with service management, resource control, automated scheduling, and comprehensive logging.

### Key Benefits

- Service Management: Full systemd lifecycle control with watchdog support
- Resource Control: CPU, memory, and I/O limits using cgroups v2
- Socket Activation: On-demand service activation via Unix domain sockets
- Scheduled Repairs: Timer-based automated VM maintenance
- Path Monitoring: Automatic repair triggers on VM image changes
- Journal Logging: Structured logging with searchable metadata
- Security Hardening: Comprehensive systemd security features

## Features

### 1. Service Management

- Systemd service units for main daemon and per-VM repairs
- Watchdog support for automatic recovery
- Graceful shutdown handling
- Service dependencies and ordering

### 2. Resource Control

- CPU quota and weight management
- Memory limits (hard and soft)
- I/O weight and bandwidth limits
- Task/thread count limits
- Real-time monitoring and statistics

### 3. Socket Activation

- Unix domain socket for IPC
- On-demand service activation
- Request/response protocol
- Multiple request types (repair, status, list, health check)

### 4. Scheduled Operations

- Timer-based periodic repairs
- Configurable schedules with systemd calendar expressions
- Randomized delays to prevent load spikes
- Persistent timers (run missed executions)

### 5. Path Monitoring

- inotify-based file system monitoring
- Automatic repair triggers on VM image changes
- Configurable debouncing and cooldown
- Multiple directory support

### 6. Journal Integration

- Structured logging with custom fields
- Operation tracking and reporting
- Performance metrics collection
- Searchable logs with journalctl

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Systemd Integration                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Service    │  │    Socket    │  │    Timer     │      │
│  │  Management  │  │  Activation  │  │  Scheduling  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │               │
│         └──────────────────┼──────────────────┘              │
│                            │                                  │
│  ┌──────────────┐  ┌──────┴───────┐  ┌──────────────┐      │
│  │   Resource   │  │     Path     │  │   Journal    │      │
│  │   Control    │  │  Monitoring  │  │   Logging    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

```bash
# System packages (Fedora/RHEL)
sudo dnf install systemd python3 python3-pip

# System packages (Debian/Ubuntu)
sudo apt-get install systemd python3 python3-pip

# Python packages
pip install systemd-python dbus-python psutil inotify
```

### Quick Install

```bash
# Install all features
sudo ./scripts/systemd/install-systemd-integration.sh --enable-all

# Install specific features
sudo ./scripts/systemd/install-systemd-integration.sh --enable-socket --enable-timer

# Dry run (see what would be installed)
sudo ./scripts/systemd/install-systemd-integration.sh --enable-all --dry-run
```

### Manual Installation

```bash
# Create directories
sudo mkdir -p /var/lib/h2kvm /var/log/h2kvm /run/h2kvm /etc/h2kvm

# Copy unit files
sudo cp systemd/units/*.service /etc/systemd/system/
sudo cp systemd/units/*.socket /etc/systemd/system/
sudo cp systemd/units/*.timer /etc/systemd/system/
sudo cp systemd/units/*.path /etc/systemd/system/
sudo cp systemd/units/*.target /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable h2kvm.socket
sudo systemctl enable h2kvm.timer
sudo systemctl start h2kvm.socket
```

## Configuration

### Main Configuration File

`/etc/h2kvm/h2kvm.conf`:

```bash
# VM image directories to monitor (comma-separated)
WATCH_PATHS=/var/lib/libvirt/images,/mnt/vmimages

# Resource limits
CPU_QUOTA=75%
MEMORY_MAX=4G

# Path monitoring
ENABLE_PATH_MONITOR=true
PATH_MONITOR_DEBOUNCE=5

# Auto-repair settings
AUTO_REPAIR_ENABLED=false
AUTO_REPAIR_COOLDOWN=30

# Logging
LOG_LEVEL=INFO
JOURNAL_LOGGING=true

# Socket settings
SOCKET_PATH=/run/h2kvm/repair.sock
SOCKET_TIMEOUT=30

# Timer settings
TIMER_SCHEDULE=daily
TIMER_RANDOM_DELAY=30min
```

## Usage Examples

### Service Management

```bash
# Start the main service
sudo systemctl start h2kvm.service

# Check service status
sudo systemctl status h2kvm.service

# View service logs
journalctl -u h2kvm.service -f

# Restart service
sudo systemctl restart h2kvm.service
```

### Socket Activation

```python
from h2kvm.systemd import RepairSocketClient

client = RepairSocketClient()

# Health check
response = client.health_check()
print(response)

# Repair a VM
response = client.repair_vm('/var/lib/libvirt/images/vm1.vmdk')
print(response)
```

### Resource Control

```python
from h2kvm.systemd import SystemdResourceControl, ResourceLimits

rc = SystemdResourceControl()

# Define limits
limits = ResourceLimits(
    cpu_quota='50%',
    memory_max='2G',
    io_weight=100,
    tasks_max=512
)

# Apply to process
rc.apply_limits(pid=12345, limits=limits)
```

### Resource Monitoring

```python
from h2kvm.systemd import ResourceMonitor

monitor = ResourceMonitor(pid=12345, interval=1.0)
monitor.start_monitoring()

# Get current usage
usage = monitor.get_current_usage()
print(f"CPU: {usage.cpu_percent}%")
print(f"Memory: {usage.memory_bytes / 1024**3:.2f} GB")

# Get statistics
stats = monitor.get_statistics()
print(f"Average CPU: {stats['cpu']['avg']:.1f}%")

monitor.stop_monitoring()
```

### Path Monitoring

```python
from h2kvm.systemd import VMPathMonitor

def on_file_change(event):
    print(f"File changed: {event.path / event.filename}")

monitor = VMPathMonitor(
    watch_paths=['/var/lib/libvirt/images'],
    callback=on_file_change
)

monitor.start()
```

### Journal Logging

```python
from h2kvm.systemd import JournalLogger

logger = JournalLogger(vm_name='web-server-01', operation='migration')

logger.log_start()
logger.log_step('disk_copy', 'in_progress', 'Copying VM disk')
logger.log_progress(50, 100, '50% complete')
logger.log_metric('disk_size_gb', 100.5, 'GB')
logger.log_success(duration=120.5)
```

## Systemd Units

### h2kvm.service

Main daemon service with:
- Type: notify (supports systemd notifications)
- Resource limits: 75% CPU, 4GB memory
- Security hardening enabled
- Watchdog support (60s timeout)

### h2kvm.socket

Socket activation unit:
- Unix domain socket at `/run/h2kvm/repair.sock`
- Mode 0666 (all users can connect)
- Auto-starts service on connection

### h2kvm.timer

Scheduled repair timer:
- Default: Daily at 2 AM
- Runs 15 minutes after boot
- Random delay: 30 minutes
- Persistent (runs missed timers)

### h2kvm@.service

Template service for per-VM repairs:
- Instance-based (one per VM)
- Isolated resource limits
- Automatic conflict prevention

## Troubleshooting

### Service Won't Start

```bash
# Check for errors
systemctl status h2kvm.service
journalctl -u h2kvm.service -n 50

# Verify Python packages
python3 -c "import systemd.daemon; import dbus; import psutil"
```

### Socket Connection Failed

```bash
# Check socket exists
ls -l /run/h2kvm/repair.sock

# Check permissions
stat /run/h2kvm/repair.sock
```

### Path Monitoring Not Working

```bash
# Check inotify limits
sysctl fs.inotify.max_user_watches

# Increase if needed
sudo sysctl fs.inotify.max_user_watches=524288
```

## License

Apache-2.0
