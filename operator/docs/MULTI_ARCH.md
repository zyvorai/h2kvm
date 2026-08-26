# Multi-Architecture Support

The HyperConversion operator supports multiple CPU architectures for broader deployment options.

## Supported Architectures

### Primary (Tested & Supported)

- **linux/amd64** - Intel/AMD 64-bit (x86_64)
- **linux/arm64** - ARM 64-bit (aarch64)

### Extended (Best Effort)

- **linux/s390x** - IBM Z mainframes
- **linux/ppc64le** - IBM POWER (Little Endian)

## Why Multi-Architecture?

- **ARM64**: Cost-effective cloud instances (AWS Graviton, Azure ARM, etc.)
- **Edge Computing**: Raspberry Pi, ARM servers
- **Cloud Native**: Run on any Kubernetes cluster regardless of architecture
- **Cost Savings**: ARM instances often 20-40% cheaper than x86_64

## Building Multi-Arch Images

### Prerequisites

```bash
# Enable Docker buildx
docker buildx create --use

# Verify QEMU support
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

### Build for AMD64 + ARM64 (Primary)

```bash
# Build and push to registry
make docker-buildx IMG=myregistry/hyperconversion-operator:v1.0.0

# Or use environment variable
export IMG=myregistry/hyperconversion-operator:v1.0.0
make docker-buildx
```

### Build for All Platforms (Extended)

```bash
# Build for amd64, arm64, s390x, ppc64le
make docker-buildx-extended IMG=myregistry/hyperconversion-operator:v1.0.0
```

### Build for Specific Architecture

```bash
# Build only ARM64
make docker-build-arm64 IMG=myregistry/hyperconversion-operator:v1.0.0

# Build only AMD64
make docker-build-amd64 IMG=myregistry/hyperconversion-operator:v1.0.0
```

## CI/CD Integration

### GitHub Actions

The operator includes a GitHub Actions workflow for automated multi-arch builds.

**Workflow**: `.github/workflows/multi-arch-build.yaml`

**Triggers**:
- Push to tag matching `v*` pattern
- Manual workflow dispatch

**Features**:
- Builds for linux/amd64 and linux/arm64
- Pushes to GitHub Container Registry (ghcr.io)
- Generates SBOM (Software Bill of Materials)
- Uses buildx cache for faster builds

**Example**:

```bash
# Create and push tag
git tag v1.0.0
git push origin v1.0.0

# Or manually trigger
gh workflow run multi-arch-build.yaml -f tag=v1.0.0
```

### GitLab CI

```yaml
build-multiarch:
  image: docker:latest
  services:
    - docker:dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker buildx create --use
  script:
    - docker buildx build
        --platform linux/amd64,linux/arm64
        --push
        --tag $CI_REGISTRY_IMAGE:$CI_COMMIT_TAG
        -f Dockerfile.operator .
  only:
    - tags
```

## Deployment

### Kubernetes Auto-Selection

Kubernetes automatically selects the correct architecture:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hyperconversion-operator
spec:
  template:
    spec:
      containers:
      - name: manager
        image: myregistry/hyperconversion-operator:v1.0.0
        # Kubernetes pulls the correct architecture automatically
```

### Verify Running Architecture

```bash
# Get pod architecture
kubectl get pod hyperconversion-operator-xxx -o jsonpath='{.status.hostIP}' | \
  xargs -I {} kubectl get node -o jsonpath='{.status.nodeInfo.architecture}'

# Or inspect container
kubectl exec hyperconversion-operator-xxx -- uname -m
# Output: x86_64 (amd64) or aarch64 (arm64)
```

### Node Affinity (Optional)

Force deployment to specific architecture:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hyperconversion-operator
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: kubernetes.io/arch
                operator: In
                values:
                - arm64
      containers:
      - name: manager
        image: myregistry/hyperconversion-operator:v1.0.0
```

## Helm Chart Support

The Helm chart automatically handles multi-arch deployments:

```bash
# Install on ARM64 cluster
helm install hyperconversion ./charts/hyperconversion-operator \
  --set image.repository=myregistry/hyperconversion-operator \
  --set image.tag=v1.0.0

# Kubernetes will pull the ARM64 image automatically
```

### Force Specific Architecture in Helm

```yaml
# values.yaml
nodeSelector:
  kubernetes.io/arch: arm64
```

## Testing Multi-Arch Images

### Test on Local Machine

```bash
# Test ARM64 image on AMD64 machine (requires QEMU)
docker run --rm --platform linux/arm64 \
  myregistry/hyperconversion-operator:v1.0.0 \
  --help

# Test AMD64 image
docker run --rm --platform linux/amd64 \
  myregistry/hyperconversion-operator:v1.0.0 \
  --help
```

### Inspect Manifest

```bash
# View all architectures in manifest
docker manifest inspect myregistry/hyperconversion-operator:v1.0.0

# Output shows available platforms
{
  "manifests": [
    {
      "platform": {
        "architecture": "amd64",
        "os": "linux"
      }
    },
    {
      "platform": {
        "architecture": "arm64",
        "os": "linux"
      }
    }
  ]
}
```

## ARM64 Performance

### Cost Comparison

| Provider | Instance Type | vCPU | RAM | Price/Hour | Monthly |
|----------|--------------|------|-----|------------|---------|
| **AWS** | t4g.medium (ARM) | 2 | 4GB | $0.0336 | ~$24 |
| **AWS** | t3.medium (x86) | 2 | 4GB | $0.0416 | ~$30 |
| **Savings** | | | | **19%** | **$6/mo** |

### Performance Notes

- ARM64 generally performs **similar** to AMD64 for Go applications
- Container startup time: **comparable**
- Memory usage: **identical**
- API latency: **negligible difference**
- Image size: **same** (Go produces similar binaries)

## Cloud Provider Support

### AWS (Graviton)

```bash
# EKS with Graviton nodes
eksctl create nodegroup \
  --cluster=my-cluster \
  --name=arm64-nodes \
  --instance-types=t4g.medium,t4g.large \
  --nodes=3
```

### Azure (Ampere Altra)

```bash
# AKS with ARM64 nodes
az aks nodepool add \
  --cluster-name my-cluster \
  --name arm64pool \
  --node-vm-size Standard_D2ps_v5 \
  --node-count 3
```

### GCP (Tau T2A)

```bash
# GKE with ARM64 nodes
gcloud container node-pools create arm64-pool \
  --cluster=my-cluster \
  --machine-type=t2a-standard-2 \
  --num-nodes=3
```

## Troubleshooting

### Build Fails on ARM64

```bash
# Error: exec format error
# Solution: Enable QEMU
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Verify
docker buildx inspect --bootstrap
```

### Image Not Found for Architecture

```bash
# Error: no matching manifest for linux/arm64
# Solution: Rebuild with correct platforms
docker buildx build --platform linux/amd64,linux/arm64 ...
```

### Pod Stuck in ImagePullBackOff

```bash
# Check node architecture
kubectl get nodes -o wide

# Check image manifest
docker manifest inspect myregistry/hyperconversion-operator:v1.0.0 | \
  grep -E "architecture|os"

# Ensure architecture matches
```

## Best Practices

1. **Always Build Multi-Arch**: Include both amd64 and arm64 in releases
2. **Test Both Platforms**: Run E2E tests on both architectures
3. **Use Manifest Lists**: Never push single-arch images with generic tags
4. **CI/CD Automation**: Automate multi-arch builds in pipeline
5. **Document Support**: Clearly state supported architectures
6. **Performance Test**: Benchmark on ARM64 before production
7. **Cost Optimize**: Use ARM64 for cost-sensitive workloads

## References

- [Docker Buildx](https://docs.docker.com/buildx/working-with-buildx/)
- [Kubernetes Multi-Arch](https://kubernetes.io/docs/concepts/cluster-administration/multi-platform/)
- [AWS Graviton](https://aws.amazon.com/ec2/graviton/)
- [Azure ARM](https://azure.microsoft.com/en-us/blog/azure-virtual-machines-with-ampere-altra-arm-based-processors-generally-available/)
- [GCP Tau T2A](https://cloud.google.com/compute/docs/general-purpose-machines#t2a_machines)

## Example: Complete Multi-Arch Deployment

```bash
# 1. Build multi-arch image
make docker-buildx IMG=ghcr.io/myorg/hyperconversion-operator:v1.0.0

# 2. Verify manifest
docker manifest inspect ghcr.io/myorg/hyperconversion-operator:v1.0.0

# 3. Deploy with Helm (works on any architecture)
helm install hyperconversion ./charts/hyperconversion-operator \
  --set image.repository=ghcr.io/myorg/hyperconversion-operator \
  --set image.tag=v1.0.0

# 4. Verify deployment
kubectl get pods -l app=hyperconversion-operator -o wide

# 5. Check architecture
kubectl exec -it hyperconversion-operator-xxx -- uname -m
```

## License Considerations

- **Go**: Multi-arch support is free, no licensing restrictions
- **Container Images**: No additional licensing for multi-arch
- **Cloud Providers**: ARM instances usually cheaper than x86_64

## Future Support

Potential future architectures:
- **RISC-V**: Emerging open-source architecture
- **loong64**: LoongArch (China)
- **mips64**: MIPS 64-bit

These will be added as Go compiler and ecosystem support matures.
