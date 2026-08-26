# Daemon Mode Examples

This directory contains examples for running hyper2kvm in daemon mode with advanced features.

## Available Examples

- **`daemon_with_metrics_example.py`** - Daemon with Prometheus metrics
  - Metrics server on port 9090
  - Migration counters and durations
  - Health monitoring
  - Grafana dashboard integration

- **`enhanced_features_example.py`** - Enhanced features demonstration
  - Configuration validation (pydantic or stdlib fallback)
  - Enhanced retry logic (tenacity or stdlib fallback)
  - Advanced logging
  - RHEL 10 compatible

## Features

### Daemon Mode
- Watch directory for manifest files
- Automatic processing of new VMs
- Background operation
- Systemd integration

### Metrics & Monitoring
- Prometheus-compatible metrics endpoint
- Migration success/failure tracking
- Duration and performance metrics
- Resource utilization monitoring

### Enhanced Features
- Robust retry with exponential backoff
- Configuration validation
- Structured logging
- Graceful degradation on RHEL 10

## Requirements

```bash
# Basic daemon
pip install -e .

# With metrics
pip install 'hyper2kvm[metrics]'

# Full features
pip install 'hyper2kvm[daemon,metrics]'
```

## Usage

```bash
# Daemon with metrics
python daemon_with_metrics_example.py

# Enhanced features demo
python enhanced_features_example.py
```

## Monitoring

The metrics example includes:
- Prometheus configuration: `../monitoring/prometheus.yml`
- Grafana dashboard: `../monitoring/grafana-dashboard.json`

## Documentation

- [docs/10-Daemon-Mode.md](../../docs/10-Daemon-Mode.md) - Basic daemon mode
- [docs/12-Enhanced-Daemon-User-Guide.md](../../docs/12-Enhanced-Daemon-User-Guide.md) - Enhanced features
- [docs/13-Integrated-Daemon-Architecture.md](../../docs/13-Integrated-Daemon-Architecture.md) - Architecture
- [docs/guides/98-Enhanced-Features.md](../../docs/guides/98-Enhanced-Features.md) - Feature documentation
