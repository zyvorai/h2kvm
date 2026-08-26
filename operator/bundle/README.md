# HyperConversion Operator Bundle

This directory contains the OLM (Operator Lifecycle Manager) bundle for the HyperConversion Operator.

## Quick Start

### Install via OperatorHub

```bash
# From OperatorHub.io
kubectl create -f https://operatorhub.io/install/hyperconversion-operator.yaml
```

### Install via operator-sdk

```bash
# Run the bundle
operator-sdk run bundle ghcr.io/ssahani/h2kvm-operator-bundle:v1.2.0

# Cleanup
operator-sdk cleanup hyperconversion-operator
```

## Bundle Structure

```
bundle/
├── manifests/                                   # Operator manifests
│   ├── hyperconversion-operator.clusterserviceversion.yaml
│   └── h2kvm.io_hyperconversions.yaml
├── metadata/                                    # Bundle metadata
│   └── annotations.yaml
└── tests/                                       # Scorecard tests
    └── scorecard/
        └── config.yaml
```

## Building

```bash
# Generate bundle
make bundle

# Build bundle image
make bundle-build BUNDLE_IMG=<your-registry>/hyperconversion-operator-bundle:v1.2.0

# Push to registry
make bundle-push BUNDLE_IMG=<your-registry>/hyperconversion-operator-bundle:v1.2.0
```

## Validation

```bash
# Validate bundle
operator-sdk bundle validate ./bundle

# Run scorecard tests
operator-sdk scorecard bundle
```

## Multi-Architecture

The bundle supports:
- linux/amd64
- linux/arm64
- linux/s390x
- linux/ppc64le

## Version

Current version: **v1.2.0**

## Documentation

See [OLM Integration Guide](../docs/OLM_INTEGRATION.md) for detailed documentation.

## Channels

- **stable**: Production releases
- **alpha**: Early access features

## Prerequisites

- Kubernetes 1.24+
- KubeVirt v1.0.0+
- CDI v1.58.0+

## Support

- GitHub: https://github.com/ssahani/h2kvm
- Issues: https://github.com/ssahani/h2kvm/issues
