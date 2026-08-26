# Contributing to HyperConversion Operator

We welcome contributions! This guide will help you get started.

## Development Setup

### Prerequisites

- Go 1.21+
- Docker or Podman
- kubectl with cluster access
- CDI and KubeVirt installed on test cluster

### Clone and Build

```bash
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm/operator

# Download dependencies
go mod download

# Generate manifests and code
make manifests generate

# Run tests
make test

# Build binary
make build
```

## Development Workflow

### 1. Make Changes

Edit files in:
- `api/v1alpha1/` - CRD types
- `controllers/` - Reconciliation logic
- `pkg/` - Helper packages

### 2. Update Generated Code

```bash
# Regenerate manifests after changing types
make manifests

# Regenerate DeepCopy after changing API
make generate

# Format code
make fmt

# Run linter
make vet
```

### 3. Test Changes

```bash
# Unit tests
make test

# Build to check compilation
make build

# Run locally (against configured cluster)
make run
```

### 4. Test in Cluster

```bash
# Build image
make docker-build IMG=h2kvm-operator:dev

# Load to k3d (if using k3d)
k3d image import h2kvm-operator:dev

# Deploy
make deploy IMG=h2kvm-operator:dev

# Test with sample
kubectl apply -f config/samples/simple-vmdk-to-vm.yaml
kubectl get hc -w
```

## Code Guidelines

### Go Code Style

- Follow standard Go formatting (enforced by `make fmt`)
- Add meaningful comments for exported types and functions
- Use descriptive variable names
- Handle errors explicitly

### CRD Design

- Use kubebuilder markers for validation
- Provide sensible defaults
- Add clear descriptions
- Use enums for choice fields
- Validate ranges where appropriate

### Controller Best Practices

- Keep reconciliation idempotent
- Use phases for complex workflows
- Emit events for important transitions
- Update conditions for observability
- Set owner references for cleanup
- Use finalizers when needed

## Testing

### Unit Tests

Add tests for:
- Controller reconciliation logic
- Helper functions
- Type validation

Example:
```go
func TestReconcilePending(t *testing.T) {
    // Test pending phase reconciliation
}
```

### Integration Tests

Update `tests/integration/e2e_test.sh` for new features.

## Pull Request Process

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

3. **Make changes and commit**
   ```bash
   git add .
   git commit -m "feat: add support for X"
   ```

4. **Push to your fork**
   ```bash
   git push origin feature/my-feature
   ```

5. **Create Pull Request**
   - Provide clear description
   - Reference related issues
   - Include test results

### Commit Message Format

Use conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test additions/changes
- `chore:` - Maintenance tasks

Example:
```
feat: add support for S3 authentication

- Add SecretRef field to SourceSpec
- Update CDI helper to use credentials
- Add sample CR with S3 source
- Update documentation
```

## Areas for Contribution

### High Priority

- [ ] Python worker integration for offline fixes
- [ ] Webhooks for validation and defaulting
- [ ] Prometheus metrics
- [ ] Multi-disk VM support

### Medium Priority

- [ ] Support for additional source types (NFS, PVC)
- [ ] Backup/restore integration
- [ ] VM templates
- [ ] Resource quotas and limits

### Documentation

- [ ] More examples
- [ ] Video tutorials
- [ ] Architecture diagrams
- [ ] Troubleshooting guides

### Testing

- [ ] Increase test coverage
- [ ] Add more integration tests
- [ ] Performance testing
- [ ] Chaos testing

## Getting Help

- **Questions**: Open a GitHub issue
- **Discussions**: GitHub Discussions
- **Bugs**: GitHub Issues with bug template

## Code Review

All contributions require:
- [ ] Code builds successfully
- [ ] Tests pass
- [ ] Documentation updated
- [ ] Commits follow format
- [ ] No linter warnings

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
