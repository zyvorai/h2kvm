# Tutorials

Step-by-step tutorials for common hyper2kvm use cases.

## Tutorial 1: First VM Validation

Learn to validate a VM image in 5 minutes.

### Prerequisites

- hyper2kvm installed: `pip install hyper2kvm`
- systemd-container package
- A VM image (qcow2, raw, vmdk, etc.)

### Step 1: Basic Validation

```bash
# Validate a simple VM image
hyper2kvm validate /path/to/ubuntu-22.04.qcow2
```

Expected output:
```
Starting VM validation...
✓ VM started successfully
✓ Systemd is running
✓ Network configured
✓ Boot completed
Validation passed in 45.2 seconds
```

### Step 2: Custom Configuration

```bash
# Customize memory and CPUs
hyper2kvm validate ubuntu.qcow2 \
    --memory 4096 \
    --cpus 4 \
    --timeout 300
```

### Step 3: Enable TPM

```bash
# Validate with TPM emulation (for secure boot testing)
hyper2kvm validate ubuntu.qcow2 --tpm
```

### Troubleshooting

If validation fails:

1. Check image is bootable:
   ```bash
   qemu-img info ubuntu.qcow2
   ```

2. Increase timeout:
   ```bash
   hyper2kvm validate ubuntu.qcow2 --timeout 600
   ```

3. Check systemd-vmspawn:
   ```bash
   systemd-vmspawn --version
   ```

## Tutorial 2: Kubernetes Node Validation

Validate a Kubernetes node image before deployment.

### Prerequisites

- K8s node image with:
  - kubelet installed
  - Container runtime (containerd/docker)
  - CNI plugins

### Step 1: Basic K8s Validation

```bash
hyper2kvm validate k8s-node.qcow2 \
    --kubernetes \
    --memory 4096 \
    --cpus 4 \
    --timeout 600
```

### Step 2: Python API

```python
from hyper2kvm.vmspawn import KubernetesNodeValidator, MachineConfig

# Configure VM
config = MachineConfig(
    name="k8s-node-test",
    image="/images/k8s-node.qcow2",
    memory=4096,
    cpus=4,
)

# Run validation
validator = KubernetesNodeValidator(config)
result = validator.validate(timeout=600)

# Check results
if result.success:
    print("✓ Validation passed")
    print(f"  Kubelet: {result.checks.kubelet}")
    print(f"  Container Runtime: {result.checks.container_runtime}")
    print(f"  CNI: {result.checks.cni}")
else:
    print(f"✗ Validation failed: {result.error}")
```

### Step 3: Automated Testing in CI

```yaml
# .github/workflows/test-images.yml
name: Test K8s Node Images

on:
  push:
    paths:
      - 'images/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install hyper2kvm
        run: |
          sudo apt install systemd-container
          pip install hyper2kvm
      
      - name: Validate image
        run: |
          hyper2kvm validate images/k8s-node.qcow2 \
            --kubernetes \
            --timeout 600
```

## Tutorial 3: Batch Validation

Validate 100 VMs in parallel.

### Step 1: Create Configuration

```python
# batch_validate.py
import asyncio
from hyper2kvm.vmspawn import AsyncVMManager, MachineConfig

async def main():
    # Create manager with parallelism limit
    manager = AsyncVMManager(max_parallel=50)
    
    # Create 100 VM configurations
    configs = []
    for i in range(100):
        config = MachineConfig(
            name=f"vm-{i}",
            image=f"/images/vm-{i}.qcow2",
            memory=2048,
            cpus=2,
        )
        configs.append(config)
    
    # Validate all in parallel
    print(f"Validating {len(configs)} VMs...")
    results = await manager.validate_batch(configs, timeout=300)
    
    # Report results
    success_count = sum(1 for r in results if r['success'])
    print(f"\nResults: {success_count}/{len(results)} passed")
    
    # Show failures
    for result in results:
        if not result['success']:
            print(f"  ✗ {result['config'].name}: {result.get('error', 'Unknown')}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 2: Run Batch Validation

```bash
python batch_validate.py
```

Expected output:
```
Validating 100 VMs...
Progress: [====================] 100/100
Results: 98/100 passed

Failures:
  ✗ vm-42: Timeout waiting for boot
  ✗ vm-87: Network not configured
```

### Step 3: Generate Report

```python
# Add to main():
    # Generate JSON report
    import json
    
    report = {
        "total": len(results),
        "success": success_count,
        "failures": []
    }
    
    for result in results:
        if not result['success']:
            report['failures'].append({
                "name": result['config'].name,
                "error": result.get('error', 'Unknown')
            })
    
    with open('validation-report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print("\nReport saved to validation-report.json")
```

## Tutorial 4: Kubernetes Operator Deployment

Deploy validation as Kubernetes CRDs.

### Step 1: Install Operator

```bash
# Install CRDs
kubectl apply -f https://github.com/ssahani/hyper2kvm/releases/latest/download/crd.yaml

# Install operator
kubectl apply -f https://github.com/ssahani/hyper2kvm/releases/latest/download/operator.yaml

# Verify installation
kubectl get pods -n hyper2kvm-system
```

### Step 2: Create Validation

```yaml
# validation-example.yaml
apiVersion: hyper2kvm.io/v1
kind: Validation
metadata:
  name: ubuntu-test
  namespace: default
spec:
  image: /images/ubuntu-22.04.qcow2
  memory: 2048
  cpus: 2
  timeout: 300
  vsock: true
```

Apply:

```bash
kubectl apply -f validation-example.yaml
```

### Step 3: Monitor Progress

```bash
# Watch status
kubectl get validations -w

# Get details
kubectl describe validation ubuntu-test

# View pod logs
kubectl logs -f $(kubectl get pods -l hyper2kvm.io/validation=ubuntu-test -o name)
```

### Step 4: Create KubeVirt VM

```yaml
# validation-with-vm.yaml
apiVersion: hyper2kvm.io/v1
kind: Validation
metadata:
  name: k8s-node-vm
spec:
  image: /images/k8s-node.qcow2
  memory: 4096
  cpus: 4
  kubernetesValidation: true
  createKubeVirtVM: true
  kubevirtTemplate:
    metadata:
      labels:
        app: k8s-node
    spec:
      running: true
      template:
        spec:
          domain:
            cpu:
              cores: 4
            devices:
              disks:
                - name: disk0
                  disk:
                    bus: virtio
            resources:
              requests:
                memory: 4Gi
          volumes:
            - name: disk0
              persistentVolumeClaim:
                claimName: k8s-node-disk
```

Apply and verify:

```bash
kubectl apply -f validation-with-vm.yaml

# Wait for validation
kubectl wait --for=condition=validated validation/k8s-node-vm --timeout=600s

# Check KubeVirt VM created
kubectl get vms
```

## Tutorial 5: Performance Tuning

Optimize validation performance for your workload.

### Step 1: Benchmark Current Performance

```bash
# Install test dependencies
pip install pytest-benchmark

# Run benchmarks
pytest hyper2kvm/vmspawn/tests/test_performance.py --benchmark-only
```

### Step 2: Find Optimal Parallelism

```python
# find_optimal.py
import asyncio
import time
from hyper2kvm.vmspawn import AsyncVMManager, MachineConfig

async def test_concurrency(concurrency):
    manager = AsyncVMManager(max_parallel=concurrency)
    
    configs = [
        MachineConfig(name=f"vm-{i}", image="/images/test.qcow2")
        for i in range(100)
    ]
    
    start = time.time()
    results = await manager.validate_batch(configs, timeout=300)
    elapsed = time.time() - start
    
    throughput = len(configs) / elapsed
    return throughput

async def main():
    print("Testing different concurrency levels...\n")
    
    for concurrency in [10, 25, 50, 100, 200]:
        throughput = await test_concurrency(concurrency)
        print(f"Concurrency {concurrency:3d}: {throughput:.2f} VMs/sec")

if __name__ == "__main__":
    asyncio.run(main())
```

Run:

```bash
python find_optimal.py
```

Output:
```
Testing different concurrency levels...

Concurrency  10: 5.2 VMs/sec
Concurrency  25: 12.8 VMs/sec
Concurrency  50: 18.5 VMs/sec  <-- Optimal
Concurrency 100: 17.2 VMs/sec
Concurrency 200: 14.1 VMs/sec
```

### Step 3: Apply Optimizations

```python
# Use optimal concurrency
OPTIMAL_PARALLEL = 50

manager = AsyncVMManager(max_parallel=OPTIMAL_PARALLEL)
```

### Step 4: Profile Bottlenecks

```bash
# Use profiler
h2kvmctl.vmspawn.benchmarks.profiler async

# Load test
h2kvmctl.vmspawn.benchmarks.load_test \
    --vms 100 \
    --parallel 50 \
    --output results.json
```

## Tutorial 6: Integration with CI/CD

Integrate VM validation into your CI/CD pipeline.

### GitLab CI Example

```yaml
# .gitlab-ci.yml
stages:
  - build
  - validate
  - deploy

validate-images:
  stage: validate
  image: ubuntu:22.04
  before_script:
    - apt-get update
    - apt-get install -y systemd-container qemu-utils python3-pip
    - pip3 install hyper2kvm
  script:
    - hyper2kvm validate images/*.qcow2
  artifacts:
    reports:
      junit: validation-report.xml
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    
    stages {
        stage('Validate Images') {
            steps {
                sh '''
                    pip install hyper2kvm
                    hyper2kvm validate images/*.qcow2 --report-format junit
                '''
            }
        }
    }
    
    post {
        always {
            junit 'validation-report.xml'
        }
    }
}
```

### GitHub Actions Example

```yaml
# .github/workflows/validate.yml
name: Validate VM Images

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup hyper2kvm
        run: |
          sudo apt install systemd-container
          pip install hyper2kvm
      
      - name: Validate images
        run: |
          hyper2kvm validate images/*.qcow2 \
            --report-format github
```

## Next Steps

- Explore [API Reference](API_REFERENCE.md) for detailed API docs
- Check [Performance Guide](performance/BENCHMARKS.md) for optimization
- Review [Examples](../examples/) for more code samples
- Join [Discussions](https://github.com/ssahani/hyper2kvm/discussions) for help
