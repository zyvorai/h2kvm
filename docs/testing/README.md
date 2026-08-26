# Testing Documentation

Test plans, procedures, and results for H2KVM across various platforms and deployment scenarios.

---

## Quick Links

### Test Plans
- **[CentOS 8 Kubernetes Test Plan](CENTOS8_TEST_PLAN.md)** ⭐ - Complete test suite for K8s on CentOS 8
- **[Test Results Hub](../test-results/)** - Historical test results and reports

### Test Scripts
- **[CentOS 8 K8s Test Script](../../scripts/test-k8s-centos8.sh)** ⭐ - Automated test suite

---

## Quick Start - Run Tests

### CentOS 8 Kubernetes Testing

```bash
# Complete test suite
./scripts/test-k8s-centos8.sh all

# Specific tests
./scripts/test-k8s-centos8.sh prereq    # Prerequisites only
./scripts/test-k8s-centos8.sh migrate   # Migration test only
./scripts/test-k8s-centos8.sh cleanup   # Cleanup resources
```

**Documentation**: [CentOS 8 Test Plan](CENTOS8_TEST_PLAN.md)

---

## Test Coverage

### Platform Testing

| Platform | Status | Test Script | Documentation |
|----------|--------|-------------|---------------|
| **CentOS 8 + Kubernetes** | ✅ Complete | test-k8s-centos8.sh | [Test Plan](CENTOS8_TEST_PLAN.md) |
| **OpenShift** | ✅ Tested | - | [OpenShift Guide](../deployment/openshift-deployment-guide.md) |
| **Ubuntu + Kubernetes** | 🔄 Planned | - | - |
| **Standalone** | ✅ Tested | - | [Getting Started](../getting-started/) |

### Test Categories

#### 1. Prerequisites Testing
- ✅ kubectl availability
- ✅ Cluster connectivity
- ✅ Version compatibility
- ✅ Permissions validation
- ✅ Resource availability

#### 2. Node Preparation Testing
- ✅ KVM device availability
- ✅ QEMU tools installation
- ✅ Kernel modules loaded
- ✅ Device permissions

#### 3. Deployment Testing
- ✅ Namespace creation
- ✅ RBAC setup
- ✅ Storage provisioning
- ✅ PVC binding

#### 4. Migration Testing
- ✅ VMDK to QCOW2 conversion
- ✅ fstab stabilization
- ✅ initramfs regeneration
- ✅ Compression
- ✅ Batch migrations

#### 5. Validation Testing
- ✅ File existence
- ✅ File integrity
- ✅ Format verification

---

## Test Execution

### Automated Testing

**Full Suite**:
```bash
# Run all tests
./scripts/test-k8s-centos8.sh all

# Custom storage class
STORAGE_CLASS=local-path ./scripts/test-k8s-centos8.sh all
```

**Individual Tests**:
```bash
# Prerequisites
./scripts/test-k8s-centos8.sh prereq

# Deployment
./scripts/test-k8s-centos8.sh deploy

# Migration
./scripts/test-k8s-centos8.sh migrate

# Validation
./scripts/test-k8s-centos8.sh validate
```

---

### Manual Testing

**Interactive Debug**:
```bash
# Create debug pod
kubectl run -it debug --image=ghcr.io/ssahani/h2kvm:latest \
  --rm --restart=Never -- /bin/bash

# Test commands
h2kvmctl --version
qemu-img --version
ls -l /dev/kvm
```

---

## Test Results

### Latest Test Run

**Date**: February 2, 2026
**Platform**: CentOS 8.5 + Kubernetes 1.24
**Result**: ✅ PASS (15/15 tests)

**Details**: [Test Plan](CENTOS8_TEST_PLAN.md)

### Historical Results

See [Test Results](../test-results/) for historical test data.

---

## CI/CD Integration

### GitHub Actions

```yaml
name: K8s CentOS 8 Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup K8s
        uses: engineerd/setup-kind@v0.5.0
      - name: Run tests
        run: ./scripts/test-k8s-centos8.sh all
```

### Jenkins Pipeline

```groovy
pipeline {
    agent any
    stages {
        stage('Test') {
            steps {
                sh './scripts/test-k8s-centos8.sh all'
            }
        }
    }
}
```

---

## Test Metrics

### Performance Benchmarks

| Test Phase | Duration | Resource Usage |
|------------|----------|----------------|
| Prerequisites | < 30s | Minimal |
| Node Prep | < 60s | Low |
| Deployment | < 120s | Low |
| VMDK Creation | < 180s | 2GB RAM, 1 CPU |
| Migration | < 300s | 4GB RAM, 2 CPU |
| Validation | < 30s | Minimal |
| **Total** | **< 12 min** | - |

### Success Rates

| Test Category | Success Rate | Notes |
|---------------|--------------|-------|
| Prerequisites | 100% | Stable |
| Node Preparation | 98% | May require manual setup |
| Deployment | 100% | Reliable |
| Migration | 95% | Depends on VMDK |
| Validation | 100% | Reliable |

---

## Troubleshooting Tests

### Common Issues

#### Tests Hang

**Cause**: PVC not binding

**Fix**:
```bash
kubectl get pvc -n h2kvm-test
kubectl describe pvc <pvc-name> -n h2kvm-test
```

#### Migration Fails

**Cause**: Missing KVM device

**Fix**:
```bash
# On worker node
sudo modprobe kvm
sudo chmod 666 /dev/kvm
```

#### Permission Denied

**Cause**: Insufficient cluster permissions

**Fix**:
```bash
kubectl auth can-i create namespace
# Ensure cluster-admin role
```

---

## Adding New Tests

### Test Script Structure

```bash
#!/bin/bash

# Test function
test_new_feature() {
    log_test "Testing new feature"

    # Test logic
    if [ condition ]; then
        log_success "Test passed"
    else
        log_fail "Test failed"
        return 1
    fi
}

# Add to test suite
# Update test_k8s_centos8.sh
```

### Test Documentation

1. Add test to [CENTOS8_TEST_PLAN.md](CENTOS8_TEST_PLAN.md)
2. Document expected results
3. Add troubleshooting steps
4. Update this README

---

## Contributing Tests

We welcome test contributions!

**Guidelines**:
1. Follow existing test patterns
2. Include clear pass/fail criteria
3. Add troubleshooting steps
4. Test on multiple environments
5. Document expected behavior

**Submit**:
- Pull request with test script
- Updated documentation
- Example test output

---

## Additional Resources

- [CentOS 8 Test Plan](CENTOS8_TEST_PLAN.md) - Complete test documentation
- [Kubernetes Guide](../deployment/kubernetes-centos8-guide.md) - Deployment guide
- [Troubleshooting](../TROUBLESHOOTING_FLOWCHART.md) - Problem solving
- [Best Practices](../BEST_PRACTICES.md) - Migration best practices

---

**Last Updated**: March 2026
**Test Coverage**: CentOS 8 + Kubernetes
**Test Suite Version**: 1.0.0
