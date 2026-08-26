# Quick Start Guide

Get started with hyper2kvm in minutes.

## Installation

### From PyPI

```bash
pip install hyper2kvm
```

### From Source

```bash
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
pip install -e .
```

### System Dependencies

hyper2kvm requires systemd tools for VM validation:

**Debian/Ubuntu:**
```bash
sudo apt install systemd-container qemu-system-x86 qemu-utils
```

**RHEL/Fedora:**
```bash
sudo dnf install systemd-container qemu-system-x86 qemu-img
```

## Basic Usage

### 1. Validate a VM Image

Quickly validate a VM image boots correctly:

```bash
hyper2kvm validate /path/to/image.qcow2
```

This will:
- Boot the VM with systemd-vmspawn
- Check systemd is running
- Verify network configuration
- Confirm boot completed successfully

### 2. Kubernetes Node Validation

Validate a Kubernetes node image:

```bash
hyper2kvm validate /path/to/k8s-node.qcow2 --kubernetes
```

This checks:
- Basic VM validation (systemd, network, boot)
- Kubelet is running
- Container runtime (containerd/docker) is active
- CNI plugins are configured

### 3. Parallel Validation

Validate multiple VMs in parallel:

```python
import asyncio
from hyper2kvm.vmspawn import AsyncVMManager, MachineConfig

async def validate_batch():
    manager = AsyncVMManager(max_parallel=10)
    
    configs = [
        MachineConfig(name=f"vm-{i}", image=f"/images/vm-{i}.qcow2")
        for i in range(100)
    ]
    
    results = await manager.validate_batch(configs)
    
    for result in results:
        print(f"{result.config.name}: {'✓' if result.success else '✗'}")

asyncio.run(validate_batch())
```

## Kubernetes Operator

### Install Operator

```bash
# Install CRDs
kubectl apply -f https://github.com/ssahani/hyper2kvm/releases/latest/download/crd.yaml

# Install operator
kubectl apply -f https://github.com/ssahani/hyper2kvm/releases/latest/download/operator.yaml
```

### Create Validation

```yaml
apiVersion: hyper2kvm.io/v1
kind: Validation
metadata:
  name: my-vm-validation
spec:
  image: /images/test.qcow2
  memory: 2048
  cpus: 2
  timeout: 300
```

Apply it:

```bash
kubectl apply -f validation.yaml
```

Check status:

```bash
kubectl get validations
kubectl describe validation my-vm-validation
```

### Create KubeVirt VM After Validation

```yaml
apiVersion: hyper2kvm.io/v1
kind: Validation
metadata:
  name: k8s-node-validation
spec:
  image: /images/k8s-node.qcow2
  memory: 4096
  cpus: 4
  kubernetesValidation: true
  createKubeVirtVM: true
  kubevirtTemplate:
    spec:
      running: true
      template:
        spec:
          domain:
            resources:
              requests:
                memory: 4Gi
```

## Common Workflows

### Workflow 1: Quick VM Test

Test a VM boots and network works:

```bash
hyper2kvm validate vm.qcow2 --timeout 60
```

### Workflow 2: Kubernetes Node Testing

Validate a K8s node image before deploying:

```bash
hyper2kvm validate k8s-node.qcow2 \
    --kubernetes \
    --timeout 300 \
    --memory 4096 \
    --cpus 4
```

### Workflow 3: Batch Validation with Reporting

```python
from hyper2kvm.vmspawn import VMValidator, KubernetesNodeValidator
from hyper2kvm.vmspawn import MachineConfig

# Basic VM validation
config = MachineConfig(name="test", image="test.qcow2")
validator = VMValidator(config)
result = validator.validate(timeout=300)

if result.success:
    print("✓ Validation passed")
    print(f"  Systemd: {result.checks.systemd}")
    print(f"  Network: {result.checks.network}")
    print(f"  Boot: {result.checks.boot_complete}")
else:
    print(f"✗ Validation failed: {result.error}")
```

### Workflow 4: Operator-Based CI/CD

Integrate VM validation into CI/CD:

```bash
# In your CI pipeline
kubectl apply -f validation-${CI_COMMIT_SHA}.yaml
kubectl wait --for=condition=validated validation/${CI_COMMIT_SHA} --timeout=600s

# Check result
if kubectl get validation ${CI_COMMIT_SHA} -o jsonpath='{.status.validated}' | grep -q true; then
    echo "Validation passed"
    exit 0
else
    echo "Validation failed"
    kubectl describe validation ${CI_COMMIT_SHA}
    exit 1
fi
```

## Troubleshooting

### VM Won't Start

Check systemd-vmspawn is available:

```bash
which systemd-vmspawn
```

Install if missing:

```bash
# Debian/Ubuntu
sudo apt install systemd-container

# RHEL/Fedora
sudo dnf install systemd-container
```

### Permission Denied on /dev/kvm

Add your user to the kvm group:

```bash
sudo usermod -a -G kvm $USER
# Log out and back in
```

### Validation Timeout

Increase timeout for slow images:

```bash
hyper2kvm validate vm.qcow2 --timeout 600
```

Or in Python:

```python
result = validator.validate(timeout=600)
```

### Operator Pod Not Starting

Check node has KVM:

```bash
kubectl get nodes -o json | jq '.items[].status.allocatable["devices.kubevirt.io/kvm"]'
```

If empty, nodes need KVM device plugin.

## Next Steps

- Read the [User Guide](USER_GUIDE.md) for detailed usage
- See [API Reference](API_REFERENCE.md) for Python API docs
- Check [Examples](../examples/) for more code samples
- Review [Performance Guide](performance/BENCHMARKS.md) for optimization
- Learn about [Architecture](ARCHITECTURE.md) for internals

## Getting Help

- Issues: https://github.com/ssahani/hyper2kvm/issues
- Discussions: https://github.com/ssahani/hyper2kvm/discussions
- Email: contact@hyper2kvm.io
