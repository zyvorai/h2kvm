# Security Best Practices for hyper2kvm

Comprehensive security guide for deploying and using hyper2kvm in production environments.

## Table of Contents

1. [Security Overview](#security-overview)
2. [Installation Security](#installation-security)
3. [Access Control](#access-control)
4. [Network Security](#network-security)
5. [Image Security](#image-security)
6. [Secrets Management](#secrets-management)
7. [Audit Logging](#audit-logging)
8. [Compliance](#compliance)
9. [Incident Response](#incident-response)

---

## Security Overview

### Threat Model

hyper2kvm processes privileged operations on VM disk images. Key security concerns:

1. **Image Tampering**: Malicious modification of VM images
2. **Credential Exposure**: vSphere/cloud credentials in configurations
3. **Privilege Escalation**: Guestfs backends may run with elevated privileges
4. **Data Exfiltration**: Sensitive data in VM disk images
5. **Supply Chain**: Compromised dependencies or binaries

### Security Principles

- **Least Privilege**: Run with minimum required permissions
- **Defense in Depth**: Multiple layers of security controls
- **Fail Secure**: Fail safely when errors occur
- **Audit Everything**: Log all security-relevant operations
- **Encrypt in Transit**: Protect credentials and data transfers

---

## Installation Security

### Verify Package Integrity

Always verify package signatures before installation:

```bash
# For RPM installations
rpm --checksig hyper2kvm-*.rpm

# Verify GPG signature
rpm --import https://download.hyper2kvm.io/GPG-KEY
rpm -K hyper2kvm-*.rpm

# For pip installations
pip install hyper2kvm --require-hashes
```

### Use Official Sources Only

```bash
# ✅ GOOD: Official PyPI
pip install hyper2kvm

# ✅ GOOD: Official GitHub releases
wget https://github.com/yourorg/hyper2kvm/releases/download/v1.0.0/hyper2kvm.rpm

# ❌ BAD: Unknown third-party mirrors
pip install -i http://unknown-mirror.com/simple hyper2kvm
```

### Verify Binary Checksums

```bash
# Download checksum file
wget https://download.hyper2kvm.io/hyper2kvm-1.0.0.tar.gz.sha256

# Verify checksum
sha256sum -c hyper2kvm-1.0.0.tar.gz.sha256
```

### Container Security

When using Docker:

```dockerfile
# Use specific version tags (not 'latest')
FROM hyper2kvm/hyper2kvm:1.0.0

# Run as non-root user
USER hyper2kvm

# Read-only root filesystem
RUN chmod -R a-w /app

# Drop capabilities
RUN setcap cap_sys_admin+ep /usr/bin/h2kvmctl
```

---

## Access Control

### File Permissions

Set restrictive permissions on configuration files:

```bash
# Configuration files - owner read/write only
chmod 600 /etc/hyper2kvm/config.yaml
chown hyper2kvm:hyper2kvm /etc/hyper2kvm/config.yaml

# Credentials file - owner read only
chmod 400 /etc/hyper2kvm/credentials
chown hyper2kvm:hyper2kvm /etc/hyper2kvm/credentials

# Log directory - owner read/write/execute
chmod 700 /var/log/hyper2kvm
chown hyper2kvm:hyper2kvm /var/log/hyper2kvm

# Output directory - owner read/write/execute
chmod 700 /var/lib/libvirt/images
chown hyper2kvm:qemu /var/lib/libvirt/images
```

### Run as Dedicated User

Create a dedicated service account:

```bash
# Create hyper2kvm user
useradd -r -s /sbin/nologin -d /var/lib/hyper2kvm hyper2kvm

# Add to necessary groups
usermod -aG qemu hyper2kvm
usermod -aG libvirt hyper2kvm

# Configure sudo for specific commands only
cat > /etc/sudoers.d/hyper2kvm << 'EOF'
hyper2kvm ALL=(root) NOPASSWD: /usr/bin/guestfish
hyper2kvm ALL=(root) NOPASSWD: /usr/bin/virt-inspector
hyper2kvm ALL=(root) NOPASSWD: /usr/bin/qemu-img
EOF
chmod 440 /etc/sudoers.d/hyper2kvm
```

### SELinux / AppArmor

Enable mandatory access control:

#### SELinux

```bash
# Check SELinux status
getenforce

# Create custom policy
cat > hyper2kvm.te << 'EOF'
module hyper2kvm 1.0;

require {
    type unconfined_t;
    type virt_image_t;
    class file { read write open };
}

#============= unconfined_t ==============
allow unconfined_t virt_image_t:file { read write open };
EOF

# Compile and load policy
checkmodule -M -m -o hyper2kvm.mod hyper2kvm.te
semodule_package -o hyper2kvm.pp -m hyper2kvm.mod
semodule -i hyper2kvm.pp

# Set correct contexts
semanage fcontext -a -t virt_image_t "/var/lib/libvirt/images(/.*)?"
restorecon -Rv /var/lib/libvirt/images
```

#### AppArmor

```bash
# Create AppArmor profile
cat > /etc/apparmor.d/usr.bin.hyper2kvm << 'EOF'
#include <tunables/global>

/usr/bin/h2kvmctl {
  #include <abstractions/base>
  #include <abstractions/python>

  # Allow reading VM images
  /var/lib/libvirt/images/** r,

  # Allow writing converted images
  /var/lib/libvirt/images/** w,

  # Allow temporary files
  /tmp/** rw,

  # Deny network access
  deny network,

  # Deny capability changes
  deny capability setuid,
  deny capability setgid,
}
EOF

# Load profile
apparmor_parser -r /etc/apparmor.d/usr.bin.hyper2kvm
```

---

## Network Security

### Firewall Configuration

Restrict network access:

```bash
# Allow only necessary connections
firewall-cmd --permanent --add-rich-rule='
  rule family="ipv4"
  source address="vcenter.example.com"
  port protocol="tcp" port="443"
  accept'

# Block all other outbound HTTPS
firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 \
  -p tcp --dport 443 -j REJECT

firewall-cmd --reload
```

### TLS/SSL Verification

Always verify SSL certificates:

```yaml
# config.yaml - GOOD
vsphere:
  host: vcenter.example.com
  verify_ssl: true
  ca_bundle: /etc/pki/tls/certs/ca-bundle.crt
```

```yaml
# config.yaml - BAD (only for testing!)
vsphere:
  host: vcenter.example.com
  verify_ssl: false  # ❌ INSECURE
```

### Network Isolation

Use dedicated network segment for VM migrations:

```bash
# Create dedicated VLAN for migrations
ip link add link eth0 name eth0.100 type vlan id 100
ip addr add 192.168.100.10/24 dev eth0.100
ip link set eth0.100 up

# Route vSphere traffic through migration VLAN
ip route add vcenter.example.com via 192.168.100.1 dev eth0.100
```

---

## Image Security

### Image Validation

Always validate images before processing:

```python
import hashlib

def validate_image_checksum(image_path, expected_checksum):
    """Validate image hasn't been tampered with."""
    sha256 = hashlib.sha256()

    with open(image_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)

    actual = sha256.hexdigest()
    if actual != expected_checksum:
        raise SecurityError(f"Image checksum mismatch: {actual} != {expected_checksum}")

# Use in pipeline
validate_image_checksum(
    "/exports/vm-001/disk-001.vmdk",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
```

### Malware Scanning

Scan images for malware before conversion:

```bash
# Install ClamAV
dnf install clamav clamd

# Update virus definitions
freshclam

# Scan image
clamscan --infected --recursive /exports/vm-001/

# Automated scanning
cat > /usr/local/bin/scan-vm-image.sh << 'EOF'
#!/bin/bash
IMAGE=$1
clamscan --infected --max-filesize=4000M "$IMAGE"
if [ $? -ne 0 ]; then
    echo "⚠️ Malware detected in $IMAGE"
    exit 1
fi
EOF
chmod +x /usr/local/bin/scan-vm-image.sh
```

### Image Encryption

Encrypt images at rest:

```bash
# Create encrypted volume
cryptsetup luksFormat /dev/sdb
cryptsetup luksOpen /dev/sdb encrypted_images

# Create filesystem
mkfs.xfs /dev/mapper/encrypted_images

# Mount
mount /dev/mapper/encrypted_images /var/lib/libvirt/images

# Add to /etc/crypttab
echo "encrypted_images /dev/sdb none" >> /etc/crypttab

# Add to /etc/fstab
echo "/dev/mapper/encrypted_images /var/lib/libvirt/images xfs defaults 0 2" >> /etc/fstab
```

### Secure Deletion

Securely delete temporary files:

```bash
# Overwrite before deletion
shred -vfz -n 3 /tmp/temp-vm-image.qcow2

# Use secure temp directory
export TMPDIR=/dev/shm  # RAM-based, not persisted to disk
```

---

## Secrets Management

### Never Hardcode Credentials

```yaml
# ❌ BAD - Hardcoded credentials
vsphere:
  vc_user: administrator@vsphere.local
  password: MySecretPassword123
```

```yaml
# ✅ GOOD - Environment variables
vsphere:
  vc_user: ${VSPHERE_USERNAME}
  password: ${VSPHERE_PASSWORD}
```

### Use HashiCorp Vault

```bash
# Store credentials in Vault
vault kv put secret/hyper2kvm/vsphere \
  username=administrator@vsphere.local \
  password=MySecretPassword123

# Retrieve in script
export VSPHERE_USERNAME=$(vault kv get -field=username secret/hyper2kvm/vsphere)
export VSPHERE_PASSWORD=$(vault kv get -field=password secret/hyper2kvm/vsphere)

h2kvmctl vsphere --vc-user "$VSPHERE_USERNAME" --vc-password "$VSPHERE_PASSWORD" ...
```

### Use Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: vsphere-credentials
type: Opaque
stringData:
  vc_user: administrator@vsphere.local
  password: MySecretPassword123
---
apiVersion: v1
kind: Pod
metadata:
  name: hyper2kvm
spec:
  containers:
  - name: hyper2kvm
    image: hyper2kvm/hyper2kvm:1.0.0
    env:
    - name: VSPHERE_USERNAME
      valueFrom:
        secretKeyRef:
          name: vsphere-credentials
          key: username
    - name: VSPHERE_PASSWORD
      valueFrom:
        secretKeyRef:
          name: vsphere-credentials
          key: password
```

### Credential Rotation

Implement regular credential rotation:

```bash
#!/bin/bash
# rotate-credentials.sh

# Generate new password
NEW_PASSWORD=$(openssl rand -base64 32)

# Update in vCenter
govc user.update -password "$NEW_PASSWORD" administrator@vsphere.local

# Update in Vault
vault kv put secret/hyper2kvm/vsphere \
  username=administrator@vsphere.local \
  password="$NEW_PASSWORD"

echo "✓ Credentials rotated successfully"
```

---

## Audit Logging

### Enable Comprehensive Logging

```yaml
# config.yaml
logging:
  level: INFO
  audit_log: /var/log/hyper2kvm/audit.log
  security_events: true
  include_checksums: true
  log_all_api_calls: true
```

### Log Format

Use structured JSON logging:

```python
import logging
import json

class SecurityAuditLogger:
    def log_conversion_start(self, user, vm_name, source):
        event = {
            "timestamp": time.time(),
            "event": "conversion_start",
            "user": user,
            "vm_name": vm_name,
            "source": source,
            "checksum": self.calculate_checksum(source),
        }
        logging.info(json.dumps(event))
```

### Centralized Logging

Forward logs to SIEM:

```bash
# Configure rsyslog
cat > /etc/rsyslog.d/hyper2kvm.conf << 'EOF'
# Forward hyper2kvm logs to SIEM
if $programname == 'hyper2kvm' then @@siem.example.com:514
& stop
EOF

systemctl restart rsyslog
```

### Log Retention

```bash
# Configure logrotate
cat > /etc/logrotate.d/hyper2kvm << 'EOF'
/var/log/hyper2kvm/*.log {
    daily
    rotate 365
    compress
    delaycompress
    notifempty
    create 0600 hyper2kvm hyper2kvm
    postrotate
        systemctl reload hyper2kvm-daemon
    endscript
}
EOF
```

---

## Compliance

### GDPR Compliance

Data protection considerations:

1. **Data Minimization**: Only process necessary VM data
2. **Purpose Limitation**: Use data only for migration
3. **Storage Limitation**: Delete temporary files after conversion
4. **Right to Erasure**: Implement secure deletion procedures

```bash
# Secure deletion script
#!/bin/bash
# gdpr-delete.sh

VM_IMAGE=$1

# Verify it's a temporary file
if [[ "$VM_IMAGE" != /tmp/hyper2kvm/* ]]; then
    echo "Can only delete temporary files"
    exit 1
fi

# Secure deletion
shred -vfz -n 7 "$VM_IMAGE"

# Log deletion
logger -t hyper2kvm "GDPR deletion: $VM_IMAGE by $USER"
```

### PCI-DSS Compliance

For environments processing payment data:

1. **Encryption**: All VM images containing cardholder data must be encrypted
2. **Access Control**: Implement multi-factor authentication
3. **Logging**: Log and monitor all access to cardholder data
4. **Network Segmentation**: Isolate migration systems from cardholder data environment

```yaml
# config.yaml - PCI-DSS compliant configuration
security:
  require_encryption: true
  mfa_required: true
  audit_logging: true
  network_segmentation: true
  approved_sources:
    - vcenter-pci.example.com
  prohibited_destinations:
    - "*"  # Whitelist only
```

### HIPAA Compliance

For healthcare environments:

1. **Access Controls**: Role-based access control (RBAC)
2. **Audit Controls**: Complete audit trails
3. **Integrity Controls**: Validate image integrity
4. **Transmission Security**: Encrypt all data in transit

---

## Incident Response

### Security Incident Playbook

#### 1. Detection

Monitor for suspicious activities:

```bash
# Detect unusual file access
auditctl -w /var/lib/libvirt/images -p wa -k vm_image_access

# Monitor for privilege escalation
auditctl -w /etc/sudoers -p wa -k sudoers_changes

# Detect credential access
auditctl -w /etc/hyper2kvm/credentials -p r -k credential_access
```

#### 2. Containment

```bash
# Immediately stop hyper2kvm service
systemctl stop hyper2kvm-daemon

# Block network access
iptables -A OUTPUT -j REJECT

# Preserve evidence
cp -a /var/log/hyper2kvm /evidence/hyper2kvm-logs-$(date +%Y%m%d-%H%M%S)
cp -a /var/lib/hyper2kvm /evidence/hyper2kvm-data-$(date +%Y%m%d-%H%M%S)
```

#### 3. Investigation

```bash
# Review audit logs
ausearch -k vm_image_access -ts recent

# Check for unauthorized changes
rpm -Va hyper2kvm

# Review access logs
grep -E "(FAILED|ERROR|DENIED)" /var/log/hyper2kvm/audit.log
```

#### 4. Recovery

```bash
# Reinstall from trusted source
dnf reinstall hyper2kvm

# Restore configuration from backup
cp /backup/config.yaml /etc/hyper2kvm/config.yaml

# Rotate credentials
./rotate-credentials.sh

# Restart service
systemctl start hyper2kvm-daemon
```

### Forensic Collection

```bash
#!/bin/bash
# collect-forensics.sh

EVIDENCE_DIR="/evidence/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$EVIDENCE_DIR"

# Collect logs
cp -a /var/log/hyper2kvm "$EVIDENCE_DIR/logs"

# Collect configuration
cp -a /etc/hyper2kvm "$EVIDENCE_DIR/config"

# Collect system state
ps aux > "$EVIDENCE_DIR/processes.txt"
netstat -tulpn > "$EVIDENCE_DIR/network.txt"
lsof > "$EVIDENCE_DIR/open-files.txt"

# Collect audit logs
ausearch -ts boot > "$EVIDENCE_DIR/audit.txt"

# Create tarball with hash
tar czf "$EVIDENCE_DIR.tar.gz" "$EVIDENCE_DIR"
sha256sum "$EVIDENCE_DIR.tar.gz" > "$EVIDENCE_DIR.tar.gz.sha256"

echo "✓ Forensic data collected: $EVIDENCE_DIR.tar.gz"
```

---

## Security Checklist

Use this checklist before production deployment:

### Installation
- [ ] Verify package signatures
- [ ] Use official sources only
- [ ] Check binary checksums
- [ ] Review dependencies for vulnerabilities

### Access Control
- [ ] Set restrictive file permissions (600/400)
- [ ] Run as dedicated user
- [ ] Enable SELinux/AppArmor
- [ ] Implement RBAC

### Network
- [ ] Configure firewall rules
- [ ] Enable SSL verification
- [ ] Use network segmentation
- [ ] Restrict outbound connections

### Secrets
- [ ] No hardcoded credentials
- [ ] Use secrets management (Vault/Kubernetes)
- [ ] Implement credential rotation
- [ ] Encrypt secrets at rest

### Logging
- [ ] Enable audit logging
- [ ] Use structured JSON logs
- [ ] Forward to SIEM
- [ ] Configure log retention

### Images
- [ ] Validate image checksums
- [ ] Scan for malware
- [ ] Encrypt at rest
- [ ] Secure deletion procedures

### Compliance
- [ ] Document data handling procedures
- [ ] Implement required controls (GDPR/PCI-DSS/HIPAA)
- [ ] Regular compliance audits
- [ ] Incident response plan

---

## Security Contacts

Report security vulnerabilities to:
- Email: security@hyper2kvm.io
- PGP Key: https://hyper2kvm.io/security.pgp
- Bug Bounty: https://hackerone.com/hyper2kvm

---

## Additional Resources

- [OWASP Security Guidelines](https://owasp.org/)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [Cloud Security Alliance](https://cloudsecurityalliance.org/)
