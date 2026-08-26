# HyperConversion Operator - Quick Start

5-minute guide to get the HyperConversion operator running.

## Prerequisites Check

```bash
# Check cluster connection
kubectl cluster-info

# Check CDI installed
kubectl get crd datavolumes.cdi.kubevirt.io

# Check KubeVirt installed
kubectl get crd virtualmachines.kubevirt.io
```

If CDI or KubeVirt are not installed:

```bash
# Install CDI
kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/v1.58.0/cdi-operator.yaml
kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/v1.58.0/cdi-cr.yaml

# Install KubeVirt
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-operator.yaml
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-cr.yaml
```

## Install Operator (3 commands)

```bash
cd operator

# 1. Install CRD
make install

# 2. Build image (for local testing)
make docker-build IMG=h2kvm-operator:dev

# 3. Deploy operator
make deploy IMG=h2kvm-operator:dev
```

## Verify Deployment

```bash
# Check operator pod
kubectl get pods -n h2kvm-system

# Expected output:
# NAME                                        READY   STATUS    RESTARTS   AGE
# hyperconversion-operator-xxxxxxxxxx-xxxxx   1/1     Running   0          30s

# Check logs
kubectl logs -n h2kvm-system -l control-plane=controller-manager
```

## Create Your First HyperConversion

```bash
# Create a simple conversion
cat <<EOF | kubectl apply -f -
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: my-first-vm
spec:
  source:
    url: "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    format: qcow2
  storage:
    size: 20Gi
  vm:
    cpu:
      cores: 2
    memory: 4Gi
EOF

# Watch progress
kubectl get hc my-first-vm -w

# Expected output:
# NAME          PHASE       PROGRESS   DATAVOLUME        VM            AGE
# my-first-vm   Pending     0                                          1s
# my-first-vm   Uploading   5          my-first-vm-dv                  10s
# my-first-vm   Uploading   25         my-first-vm-dv                  30s
# my-first-vm   Uploading   75         my-first-vm-dv                  1m
# my-first-vm   CreatingVM  75         my-first-vm-dv                  2m
# my-first-vm   Ready       100        my-first-vm-dv    my-first-vm   2m30s

# Note: If offline fixes are enabled, you'll see an additional Fixing phase:
# my-first-vm   Fixing      80         my-first-vm-dv                  1m30s
```

## Verify Resources

```bash
# Check DataVolume created
kubectl get datavolume
# NAME              PHASE       PROGRESS   RESTARTS   AGE
# my-first-vm-dv    Succeeded   100.0%                2m

# Check VirtualMachine created
kubectl get vm
# NAME          AGE   STATUS    READY
# my-first-vm   2m    Running   True

# Get detailed info
kubectl describe hc my-first-vm
```

## Access the VM

```bash
# Start VM (if not auto-started)
virtctl start my-first-vm

# Access console
virtctl console my-first-vm

# SSH (if cloud-init configured with SSH keys)
virtctl ssh my-first-vm
```

## Cleanup

```bash
# Delete HyperConversion (auto-deletes DataVolume and VM)
kubectl delete hc my-first-vm

# Verify cleanup
kubectl get datavolume
kubectl get vm
```

## Common Use Cases

### VMDK to KubeVirt VM with Offline Fixes

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: vmdk-migration
spec:
  source:
    url: "https://example.com/rhel.vmdk"
    format: vmdk
  storage:
    size: 100Gi
  conversion:
    offlineFixes: true  # Enable offline fixes for Linux VMs
    compression: zstd   # Compress qcow2 output
    timeout: 120        # Timeout in minutes
  vm:
    cpu:
      cores: 4
    memory: 8Gi
```

**What are offline fixes?**

When migrating Linux VMs from VMware/Hyper-V to KVM, the operator can automatically fix:

- **LVM**: Detect and activate logical volumes
- **initramfs**: Rebuild with virtio drivers for KVM
- **fstab**: Update disk device paths (VMware /dev/sda → KVM /dev/vda)
- **Network**: Update netplan/NetworkManager for virtio NICs
- **GRUB**: Ensure bootloader works on KVM

To enable, add to your HyperConversion spec:

```yaml
spec:
  conversion:
    offlineFixes: true
```

The operator will run a fixer Job after the DataVolume upload completes. Check the Job logs:

```bash
kubectl logs job/<name>-fixer
```

### Disk-Only Conversion

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: disk-only
spec:
  source:
    url: "https://example.com/disk.vhd"
    format: vhd
  storage:
    size: 50Gi
  # No vm: section - creates DataVolume only
```

### Multi-Network VM

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: multi-net
spec:
  source:
    url: "https://example.com/ubuntu.qcow2"
  storage:
    size: 30Gi
  vm:
    cpu:
      cores: 4
    memory: 8Gi
    networks:
    - name: default
      type: pod
    - name: management
      type: multus
      networkName: mgmt-network
```

## Troubleshooting

### Operator not starting

```bash
# Check operator logs
kubectl logs -n h2kvm-system -l control-plane=controller-manager

# Check RBAC
kubectl get clusterrole manager-role
kubectl get clusterrolebinding manager-rolebinding
```

### HyperConversion stuck in Pending

```bash
# Check events
kubectl get events --sort-by='.lastTimestamp' | grep my-first-vm

# Describe the resource
kubectl describe hc my-first-vm

# Check DataVolume
kubectl get datavolume
```

### Upload failing

```bash
# Check CDI logs
kubectl logs -n cdi -l app=cdi-uploadproxy

# Check DataVolume details
kubectl describe datavolume my-first-vm-dv
```

## Next Steps

- Read [README.md](README.md) for complete documentation
- See [config/samples/](config/samples/) for more examples
- Check [docs/operator/](../docs/operator/) for guides
- View [API Reference](../docs/operator/hyperconversion-crd.md)

## Uninstall

```bash
# Remove all HyperConversions
kubectl delete hc --all

# Undeploy operator
make undeploy

# Uninstall CRD (WARNING: deletes all HyperConversion resources)
make uninstall
```

## Cheat Sheet

| Command | Description |
|---------|-------------|
| `kubectl get hc` | List all HyperConversions (short: hc, hconv) |
| `kubectl get hc -w` | Watch HyperConversion progress |
| `kubectl describe hc <name>` | View detailed status |
| `kubectl get datavolume` | List created DataVolumes |
| `kubectl get vm` | List created VirtualMachines |
| `kubectl logs -n h2kvm-system -l control-plane=controller-manager -f` | Follow operator logs |
| `kubectl get events --sort-by='.lastTimestamp'` | View recent events |

## Support

- Issues: https://github.com/ssahani/h2kvm/issues
- Documentation: [operator/README.md](README.md)
- Examples: [config/samples/](config/samples/)
