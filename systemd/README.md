# Hyper2KVM Systemd Integration

Production-grade systemd integration for automated VM boot repair operations.

## Directory Structure

```
systemd/
├── units/                              # Systemd unit files
│   ├── hyper2kvm.service              # Main daemon service
│   ├── hyper2kvm.socket               # Socket activation
│   ├── hyper2kvm.timer                # Scheduled repairs timer
│   ├── hyper2kvm-scheduled.service    # Scheduled repair service
│   ├── hyper2kvm.path                 # Path monitoring unit
│   ├── hyper2kvm-path-trigger.service # Path trigger handler
│   ├── hyper2kvm.target               # Combined target
│   └── hyper2kvm@.service             # Per-VM template service
└── README.md                           # This file
```

## Quick Start

```bash
# Install all features
sudo ../scripts/systemd/install-systemd-integration.sh --enable-all

# Check status
systemctl status hyper2kvm.socket hyper2kvm.timer
```

## Documentation

See `docs/features/systemd-integration.md` for complete documentation.

## License

Proprietary (Zyvor AI Labs)
