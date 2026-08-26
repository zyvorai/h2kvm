# Cloud-Init Template Library

Pre-built cloud-init templates for common VM configurations with HyperConversion operator.

## Available Templates

| Template | OS | Purpose | Includes |
|----------|----|---------| ---------|
| **ubuntu-server.yaml** | Ubuntu | Basic server | SSH, common tools, qemu-guest-agent |
| **centos-server.yaml** | CentOS/RHEL | Basic server | SSH, common tools, SELinux, firewalld |
| **debian-server.yaml** | Debian | Basic server | SSH, common tools, qemu-guest-agent |
| **kubernetes-node.yaml** | Ubuntu | K8s node | containerd, kubeadm, kubelet, kubectl |
| **docker-host.yaml** | Ubuntu | Docker host | Docker Engine, Docker Compose |
| **windows-server.yaml** | Windows | Reference | Cloudbase-init example (see notes) |

## Usage

### Method 1: ConfigMap (Recommended)

Create a ConfigMap with your customized cloud-init data:

```bash
# Customize template
cp templates/cloud-init/ubuntu-server.yaml my-cloud-init.yaml
# Edit my-cloud-init.yaml to add your SSH keys, etc.

# Create ConfigMap
kubectl create configmap ubuntu-cloud-init \
  --from-file=userdata=my-cloud-init.yaml \
  -n default
```

Reference in HyperConversion:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: ubuntu-vm
spec:
  source:
    url: "http://example.com/ubuntu-20.04.qcow2"
    format: qcow2

  storage:
    size: 20Gi

  vm:
    cpu: 2
    memory: 4Gi

    # Reference cloud-init ConfigMap
    cloudInit:
      configMapRef:
        name: ubuntu-cloud-init
```

### Method 2: Inline (For Simple Cases)

For small cloud-init configs, use inline:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: simple-ubuntu
spec:
  source:
    url: "http://example.com/ubuntu.qcow2"
    format: qcow2

  storage:
    size: 20Gi

  vm:
    cpu: 2
    memory: 4Gi

    cloudInit:
      userData: |
        #cloud-config
        hostname: my-server
        users:
          - name: ubuntu
            ssh_authorized_keys:
              - ssh-rsa AAAAB3NzaC1yc2E...
        packages:
          - curl
          - htop
```

### Method 3: Secret (For Sensitive Data)

For cloud-init with sensitive data (passwords, tokens):

```bash
# Create secret
kubectl create secret generic ubuntu-cloud-init-secret \
  --from-file=userdata=my-cloud-init.yaml \
  -n default
```

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: ubuntu-vm-secure
spec:
  source:
    url: "http://example.com/ubuntu.qcow2"
    format: qcow2

  storage:
    size: 20Gi

  vm:
    cpu: 2
    memory: 4Gi

    cloudInit:
      secretRef:
        name: ubuntu-cloud-init-secret
```

## Template Customization

### Ubuntu Server Template

```bash
# Copy template
cp templates/cloud-init/ubuntu-server.yaml ubuntu-custom.yaml

# Edit to customize:
# 1. Replace SSH public key
# 2. Change hostname/FQDN
# 3. Add/remove packages
# 4. Add custom scripts in runcmd
# 5. Add files in write_files
```

Key customization points:

```yaml
hostname: your-hostname              # Change hostname
fqdn: your-hostname.your-domain.com # Change FQDN

users:
  - name: ubuntu
    ssh_authorized_keys:
      - ssh-rsa YOUR_SSH_PUBLIC_KEY  # Replace with your key

packages:
  - your-package-1                   # Add packages
  - your-package-2

runcmd:
  - your-custom-command              # Add commands

write_files:
  - path: /path/to/file              # Add files
    content: |
      file content
```

### Kubernetes Node Template

Prepares node to join a cluster:

```bash
# After VM boots, SSH in and run:
sudo kubeadm join <control-plane-ip>:6443 \
  --token <token> \
  --discovery-token-ca-cert-hash sha256:<hash>
```

### Docker Host Template

Installs Docker Engine and Docker Compose:

```bash
# After VM boots, verify:
docker --version
docker compose --version

# Run a test container:
docker run hello-world
```

## Common Customizations

### Add SSH Keys

Replace the placeholder SSH key in any template:

```yaml
users:
  - name: ubuntu
    ssh_authorized_keys:
      - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... user@host
      - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD... another-user@host
```

### Set Static IP

Add network configuration:

```yaml
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
```

### Install Custom Software

Add to runcmd:

```yaml
runcmd:
  - curl -fsSL https://get.k3s.io | sh -
  - kubectl version
```

### Configure Firewall

For Ubuntu/Debian with ufw:

```yaml
runcmd:
  - ufw allow ssh
  - ufw enable
```

For CentOS/RHEL with firewalld:

```yaml
runcmd:
  - firewall-cmd --permanent --add-service=ssh
  - firewall-cmd --permanent --add-service=http
  - firewall-cmd --reload
```

### Add Cron Jobs

```yaml
write_files:
  - path: /etc/cron.d/custom-job
    content: |
      0 2 * * * root /usr/local/bin/backup.sh
    permissions: '0644'
```

### Mount Additional Disks

For multi-disk VMs:

```yaml
mounts:
  - [ /dev/vdb, /data, ext4, "defaults,nofail", "0", "2" ]

runcmd:
  - mkfs.ext4 /dev/vdb
  - mkdir -p /data
  - mount /dev/vdb /data
```

## Windows Notes

Windows VMs use **cloudbase-init** instead of cloud-init. The workflow is different:

1. Install cloudbase-init in the Windows image
2. Create a cloudbase-init configuration file
3. Inject via ConfigMap or CD-ROM

Example cloudbase-init PowerShell script:

```powershell
# Set hostname
Rename-Computer -NewName "windows-server" -Force

# Configure network
Get-NetAdapter | Set-NetIPInterface -DHCP Enabled

# Enable RDP
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -name "fDenyTSConnections" -value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Restart
Restart-Computer -Force
```

See: https://cloudbase-init.readthedocs.io/

## Testing Templates

Test cloud-init syntax:

```bash
# Install cloud-init locally
sudo apt-get install cloud-init

# Validate syntax
cloud-init schema --config-file ubuntu-server.yaml

# Dry run
cloud-init devel schema -c ubuntu-server.yaml --annotate
```

## Debugging

Check cloud-init logs in the VM:

```bash
# View cloud-init output
sudo cat /var/log/cloud-init-output.log

# View cloud-init logs
sudo cat /var/log/cloud-init.log

# Check status
sudo cloud-init status

# Re-run cloud-init (for testing)
sudo cloud-init clean
sudo cloud-init init
```

## Best Practices

1. **Always Test**: Test templates in a dev environment first
2. **Use ConfigMaps**: Prefer ConfigMaps over inline for reusability
3. **Secure Secrets**: Use Secrets for sensitive data (passwords, tokens)
4. **Version Control**: Keep templates in Git
5. **Document Changes**: Add comments explaining customizations
6. **Minimal Packages**: Only install what's needed
7. **Update Regularly**: Keep templates updated with latest package versions
8. **Enable qemu-guest-agent**: Always include for better KubeVirt integration

## Advanced: Template Variables

For templating with environment-specific values:

```bash
# Create template with placeholders
cat > template.yaml <<EOF
#cloud-config
hostname: {{HOSTNAME}}
users:
  - name: {{USERNAME}}
    ssh_authorized_keys:
      - {{SSH_KEY}}
EOF

# Substitute variables
export HOSTNAME=my-server
export USERNAME=admin
export SSH_KEY="ssh-rsa AAAA..."

envsubst < template.yaml > cloud-init.yaml

# Create ConfigMap
kubectl create configmap my-cloud-init --from-file=userdata=cloud-init.yaml
```

## Example: Complete Deployment

```bash
# 1. Customize template
cp templates/cloud-init/ubuntu-server.yaml my-server.yaml
# Edit my-server.yaml: add SSH key, customize packages

# 2. Create ConfigMap
kubectl create configmap ubuntu-server-init \
  --from-file=userdata=my-server.yaml

# 3. Create HyperConversion
kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: my-ubuntu-server
spec:
  source:
    url: "http://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img"
    format: qcow2

  storage:
    size: 20Gi
    storageClass: local-path

  vm:
    cpu: 2
    memory: 4Gi
    firmware: bios

    cloudInit:
      configMapRef:
        name: ubuntu-server-init
EOF

# 4. Wait for VM to boot
kubectl get hyperconversion my-ubuntu-server -w

# 5. Get VM IP
kubectl get vmi my-ubuntu-server -o jsonpath='{.status.interfaces[0].ipAddress}'

# 6. SSH into VM
ssh ubuntu@<vm-ip>
```

## References

- [Cloud-Init Documentation](https://cloudinit.readthedocs.io/)
- [Cloud-Init Examples](https://cloudinit.readthedocs.io/en/latest/topics/examples.html)
- [KubeVirt Cloud-Init](https://kubevirt.io/user-guide/virtual_machines/startup_scripts/)
- [Cloudbase-Init (Windows)](https://cloudbase-init.readthedocs.io/)
