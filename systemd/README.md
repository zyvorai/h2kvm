# H2KVM Systemd Integration

Production-grade systemd integration for automated VM boot repair operations.

## Directory Structure

```
systemd/
├── units/                              # Systemd unit files
│   ├── h2kvm.service              # Main daemon service
│   ├── h2kvm.socket               # Socket activation
│   ├── h2kvm.timer                # Scheduled repairs timer
│   ├── h2kvm-scheduled.service    # Scheduled repair service
│   ├── h2kvm.path                 # Path monitoring unit
│   ├── h2kvm-path-trigger.service # Path trigger handler
│   ├── h2kvm.target               # Combined target
│   └── h2kvm@.service             # Per-VM template service
└── README.md                           # This file
```

## Quick Start

```bash
# Install all features
sudo ../scripts/systemd/install-systemd-integration.sh --enable-all

# Check status
systemctl status h2kvm.socket h2kvm.timer
```

## Documentation

See `docs/features/systemd-integration.md` for complete documentation.

## License

Proprietary (Zyvor AI Labs)
