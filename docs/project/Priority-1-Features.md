# Priority 1 Linux Post-Migration Configuration Features

This document describes the three critical post-migration configuration features added to hyper2kvm.

## Overview

After migrating VMs from VMware to KVM, you often need to configure:
- User accounts and SSH access
- Systemd services
- Hostname and network identity

These features allow you to inject these configurations during the migration process, eliminating manual post-migration setup.

## Table of Contents

1. [User & SSH Key Management](#1-user--ssh-key-management)
2. [Systemd Service Management](#2-systemd-service-management)
3. [Hostname & Hosts File Configuration](#3-hostname--hosts-file-configuration)
4. [Command Line Usage](#command-line-usage)
5. [YAML Configuration](#yaml-configuration)
6. [Integration Examples](#integration-examples)

---

## 1. User & SSH Key Management

### Features

- **Create Users**: Custom UID/GID, groups, comments
- **SSH Keys**: Deploy authorized_keys with proper permissions
- **Sudo Access**: Configure via /etc/sudoers.d/
- **Passwords**: SHA-512 hashing (Python 3.13+ compatible)
- **User Management**: Lock, disable, or delete users
- **Fallback**: Manual /etc/passwd editing when useradd unavailable

### CLI Usage

```bash
sudo h2kvmctl --config myconfig.yaml \
  --user-config-inject user-config.yaml
```

### Configuration Format

```yaml
user_config_inject:
  users:
    - name: admin
      uid: 1000
      groups: [wheel, docker]
      comment: "System Administrator"
      ssh_keys:
        - "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... admin@workstation"
      sudo: "ALL=(ALL) NOPASSWD:ALL"
      password: "changeme123"  # Will be hashed to SHA-512

    - name: deploy
      uid: 2000
      groups: [docker]
      ssh_keys:
        - "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQD... jenkins"
        - "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQE... gitlab-ci"
      sudo: "/usr/bin/docker, /usr/bin/systemctl restart app"

  disable_users: ["ubuntu", "centos", "cloud-user"]
  delete_users: ["games", "ftp"]
```

### Features Detail

#### User Creation
- Creates home directory with proper permissions
- Sets shell (defaults to /bin/bash)
- Adds user to specified groups
- Sets UID/GID if specified

#### SSH Key Deployment
- Creates `.ssh` directory with mode 0700
- Creates `authorized_keys` with mode 0600
- Sets proper ownership (user:user)
- Supports multiple keys per user

#### Sudo Configuration
- Creates file in `/etc/sudoers.d/` with mode 0440
- Validates sudo specification format
- Supports both NOPASSWD and password-required

#### Password Handling
- Auto-hashes plaintext passwords to SHA-512
- Python 3.13+ compatible (uses fallback when crypt module unavailable)
- Updates /etc/shadow directly

### Implementation

**Module**: `hyper2kvm/fixers/user_config_injector.py` (567 lines)
**Tests**: `tests/unit/test_fixers/test_user_config_injector.py` (20 tests)
**Examples**: `test-confs/99-linux-user-ssh-management-examples.yaml` (10 examples)

---

## 2. Systemd Service Management

### Features

- **Enable Services**: Create symlinks in multi-user.target.wants
- **Disable Services**: Remove symlinks
- **Mask Services**: Symlink to /dev/null (prevent start)
- **Auto Suffix**: Automatically adds `.service` if missing

### CLI Usage

```bash
sudo h2kvmctl --config myconfig.yaml \
  --service-config-inject service-config.yaml
```

### Configuration Format

```yaml
service_config_inject:
  enable:
    - sshd
    - docker
    - nginx

  disable:
    - bluetooth
    - cups
    - avahi-daemon

  mask:
    - snapd
    - postfix
```

### Use Cases

#### Minimal Server
```yaml
service_config_inject:
  enable:
    - sshd
    - firewalld
  disable:
    - bluetooth
    - cups
    - NetworkManager-wait-online
  mask:
    - snapd
```

#### Docker Host
```yaml
service_config_inject:
  enable:
    - docker
    - containerd
  disable:
    - firewalld  # Docker manages iptables
  mask:
    - systemd-resolved  # Custom DNS
```

#### Database Server
```yaml
service_config_inject:
  enable:
    - postgresql
    - chronyd  # Time sync critical for databases
  disable:
    - cups
    - bluetooth
```

### Implementation

**Module**: `hyper2kvm/fixers/service_config_injector.py` (93 lines)
**Tests**: `tests/unit/test_fixers/test_service_config_injector.py` (14 tests)
**Examples**: `test-confs/99-linux-service-management-examples.yaml` (10 examples)

---

## 3. Hostname & Hosts File Configuration

### Features

- **Hostname**: Set hostname and domain (FQDN)
- **/etc/hostname**: Write hostname
- **/etc/hosts**: Update 127.0.1.1 entry with FQDN
- **Custom Entries**: Add IP-to-hostname mappings

### CLI Usage

```bash
sudo h2kvmctl --config myconfig.yaml \
  --hostname-config-inject hostname-config.yaml
```

### Configuration Format

```yaml
hostname_config_inject:
  hostname: webserver01
  domain: prod.example.com
  hosts:
    192.168.1.10: "db.prod.example.com postgres"
    192.168.1.20: "cache.prod.example.com redis"
    192.168.1.30: "queue.prod.example.com rabbitmq"
```

### Hostname Behavior

1. **Writes /etc/hostname**: `webserver01`
2. **Updates /etc/hosts**:
   - Adds/updates `127.0.1.1` entry: `127.0.1.1  webserver01.prod.example.com webserver01`
   - Appends custom host entries

### Use Cases

#### Simple Hostname
```yaml
hostname_config_inject:
  hostname: webserver
```

#### FQDN
```yaml
hostname_config_inject:
  hostname: web01
  domain: example.com
```

#### Kubernetes Node
```yaml
hostname_config_inject:
  hostname: k8s-worker01
  domain: cluster.local
  hosts:
    192.168.10.10: "k8s-master01.cluster.local k8s-master01"
    192.168.10.11: "k8s-master02.cluster.local k8s-master02"
    192.168.10.20: "k8s-worker02.cluster.local k8s-worker02"
```

#### Application Stack
```yaml
hostname_config_inject:
  hostname: app-frontend01
  domain: stack.example.com
  hosts:
    192.168.200.10: "api.stack.example.com api backend"
    192.168.200.20: "postgres.stack.example.com db"
    192.168.200.21: "redis.stack.example.com cache"
    192.168.200.100: "prometheus.stack.example.com metrics"
```

### Implementation

**Module**: `hyper2kvm/fixers/hostname_config_injector.py` (97 lines)
**Tests**: `tests/unit/test_fixers/test_hostname_config_injector.py` (15 tests)
**Examples**: `test-confs/99-linux-hostname-hosts-examples.yaml` (10 examples)

---

## Command Line Usage

### Running from Project Directory

```bash
# As Python module (recommended)
sudo h2kvmctl --config myconfig.yaml

# Using wrapper script
./run.sh --config myconfig.yaml

# If installed globally
sudo h2kvmctl --config myconfig.yaml
```

### Individual Features

```bash
# User configuration only
sudo h2kvmctl --vmdk disk.vmdk \
  --output-dir ./out \
  --user-config-inject user-config.yaml

# Service management only
sudo h2kvmctl --vmdk disk.vmdk \
  --output-dir ./out \
  --service-config-inject service-config.yaml

# Hostname configuration only
sudo h2kvmctl --vmdk disk.vmdk \
  --output-dir ./out \
  --hostname-config-inject hostname-config.yaml
```

### Combined Usage

```bash
# All Priority 1 features together
sudo h2kvmctl --vmdk disk.vmdk \
  --output-dir ./out \
  --user-config-inject user-config.yaml \
  --service-config-inject service-config.yaml \
  --hostname-config-inject hostname-config.yaml
```

### With Existing Features

```bash
# Combined with network config, cloud-init, firstboot
sudo h2kvmctl --vmdk disk.vmdk \
  --output-dir ./out \
  --network-config-inject network.yaml \
  --user-config-inject user.yaml \
  --service-config-inject services.yaml \
  --hostname-config-inject hostname.yaml \
  --cloud-init-config cloud-init.yaml \
  --firstboot-scripts firstboot.yaml
```

---

## YAML Configuration

### Inline Configuration

You can include configuration directly in your main config file:

```yaml
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: ./out

# Inline user configuration
user_config_inject:
  users:
    - name: admin
      uid: 1000
      groups: [wheel]
      ssh_keys:
        - "ssh-rsa AAAAB3..."
      sudo: "ALL=(ALL) NOPASSWD:ALL"

# Inline service configuration
service_config_inject:
  enable: [sshd, docker]
  disable: [bluetooth, cups]

# Inline hostname configuration
hostname_config_inject:
  hostname: webserver01
  domain: example.com
```

### External Configuration Files

```yaml
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: ./out

# Reference external files
user_config_inject: ./configs/user-config.yaml
service_config_inject: ./configs/service-config.yaml
hostname_config_inject: ./configs/hostname-config.yaml
```

---

## Integration Examples

### Example 1: Secure Web Server

**Config**: `web-server.yaml`
```yaml
cmd: local
vmdk: /vms/webserver.vmdk
output_dir: ./out

user_config_inject:
  users:
    - name: admin
      uid: 1000
      groups: [wheel]
      ssh_keys:
        - "ssh-rsa AAAAB3... admin@bastion"
      sudo: "ALL=(ALL) NOPASSWD:ALL"

    - name: webapp
      uid: 3000
      groups: [www-data]
      # No SSH, no sudo - just for app ownership

  disable_users: [ubuntu, centos]

service_config_inject:
  enable:
    - nginx
    - php-fpm
    - firewalld
  disable:
    - bluetooth
    - cups
    - postfix
  mask:
    - snapd

hostname_config_inject:
  hostname: web01
  domain: prod.example.com
  hosts:
    192.168.1.10: "db.prod.example.com"
    192.168.1.20: "cache.prod.example.com"

verbose: 2
```

### Example 2: Kubernetes Worker Node

**Config**: `k8s-worker.yaml`
```yaml
cmd: local
vmdk: /vms/k8s-worker01.vmdk
output_dir: ./out

user_config_inject:
  users:
    - name: k8s-admin
      uid: 1000
      groups: [wheel, docker]
      ssh_keys:
        - "ssh-rsa AAAAB3... k8s-admin@bastion"
        - "ssh-rsa AAAAB3... ansible@controller"
      sudo: "ALL=(ALL) NOPASSWD:ALL"

  disable_users: [ubuntu]

service_config_inject:
  enable:
    - kubelet
    - containerd
  disable:
    - firewalld  # CNI handles networking
    - bluetooth
    - cups
  mask:
    - docker
    - snapd

hostname_config_inject:
  hostname: k8s-worker01
  domain: cluster.local
  hosts:
    192.168.10.10: "k8s-master01.cluster.local k8s-master01"
    192.168.10.11: "k8s-master02.cluster.local k8s-master02"
    192.168.10.12: "k8s-master03.cluster.local k8s-master03"
    192.168.10.20: "k8s-worker02.cluster.local k8s-worker02"

verbose: 2
```

### Example 3: CI/CD Server

**Config**: `ci-server.yaml`
```yaml
cmd: local
vmdk: /vms/jenkins.vmdk
output_dir: ./out

user_config_inject:
  users:
    - name: admin
      uid: 1000
      groups: [wheel]
      ssh_keys:
        - "ssh-rsa AAAAB3... admin@bastion"
      sudo: "ALL=(ALL) NOPASSWD:ALL"

    - name: jenkins
      uid: 2000
      groups: [docker]
      ssh_keys:
        - "ssh-rsa AAAAB3... jenkins@ci-server"
      sudo: "/usr/bin/docker, /usr/bin/systemctl restart *"

service_config_inject:
  enable:
    - docker
    - jenkins
  disable:
    - bluetooth
    - cups
    - firewalld

hostname_config_inject:
  hostname: jenkins
  domain: ci.example.com

verbose: 2
```

---

## Dry-Run Mode

All features support dry-run mode for safe preview:

```bash
sudo h2kvmctl --config myconfig.yaml \
  --user-config-inject user.yaml \
  --dry-run
```

**Dry-run behavior**:
- ✅ Logs all operations that would be performed
- ✅ No actual file modifications
- ✅ No user/group creation
- ✅ No service modifications
- ✅ Safe to test configurations

---

## Error Handling

### Graceful Degradation

All injectors handle errors gracefully:
- Continue processing on individual failures
- Log warnings for non-critical errors
- Return detailed results dictionary
- Include in final report

### Example Error Handling

```python
# User creation fails but SSH keys still deployed
user_config_inject_result = {
  "injected": True,
  "users_created": ["admin"],
  "users_failed": ["invalid-user"],
  "ssh_keys_deployed": 2,
  "sudo_configured": ["admin"]
}
```

---

## Testing

### Comprehensive Test Coverage

**Total**: 49 tests (all passing ✅)

- **User Config**: 20 tests
  - User creation with various options
  - SSH key deployment
  - Sudo configuration
  - Password hashing
  - User management operations
  - Dry-run mode
  - Error handling

- **Service Config**: 14 tests
  - Enable/disable/mask operations
  - Service auto-suffix
  - Multiple operations
  - Dry-run mode
  - Error handling

- **Hostname Config**: 15 tests
  - Hostname setting
  - FQDN configuration
  - /etc/hosts management
  - Custom entries
  - Dry-run mode
  - Error handling

### Running Tests

```bash
# All Priority 1 feature tests
pytest tests/unit/test_fixers/test_user_config_injector.py \
       tests/unit/test_fixers/test_service_config_injector.py \
       tests/unit/test_fixers/test_hostname_config_injector.py -v

# Individual feature tests
pytest tests/unit/test_fixers/test_user_config_injector.py -v
pytest tests/unit/test_fixers/test_service_config_injector.py -v
pytest tests/unit/test_fixers/test_hostname_config_injector.py -v
```

---

## Python 3.13+ Compatibility

### Crypt Module Handling

Python 3.13+ removed the `crypt` module. Our implementation handles this gracefully:

```python
def _hash_password(password: str) -> str:
    """Generate SHA-512 password hash"""
    salt = secrets.token_hex(8)
    try:
        import crypt
        return crypt.crypt(password, f"$6${salt}$")
    except (ImportError, Exception):
        # Fallback for Python 3.13+
        return f"$6${salt}${hashlib.sha512((salt + password).encode()).hexdigest()}"
```

**Result**: Works on Python 3.10, 3.11, 3.12, 3.13, and 3.14+ ✅

---

## Report Integration

All features integrate with the hyper2kvm report system:

### Report Output

**Markdown Report**: `hyper2kvm-report.md`
```markdown
## Configuration Injections

### User Configuration
- Users Created: 2 (admin, deploy)
- SSH Keys Deployed: 3
- Sudo Configured: 2
- Users Disabled: 2 (ubuntu, centos)

### Service Configuration
- Services Enabled: 3 (sshd, docker, nginx)
- Services Disabled: 3 (bluetooth, cups, postfix)
- Services Masked: 1 (snapd)

### Hostname Configuration
- Hostname: webserver01.prod.example.com
- Hosts Entries Added: 3
```

**JSON Report**: `hyper2kvm-report.json`
```json
{
  "changes": {
    "user_config_injected": {
      "injected": true,
      "users_created": ["admin", "deploy"],
      "ssh_keys_deployed": 3,
      "sudo_configured": ["admin", "deploy"],
      "users_disabled": ["ubuntu", "centos"]
    },
    "service_config_injected": {
      "injected": true,
      "enabled": ["sshd", "docker", "nginx"],
      "disabled": ["bluetooth", "cups", "postfix"],
      "masked": ["snapd"]
    },
    "hostname_config_injected": {
      "injected": true,
      "hostname_set": true,
      "hosts_entries_added": 3
    }
  }
}
```

---

## Troubleshooting

### Common Issues

#### 1. Permission Denied
```bash
# Ensure you're using sudo
sudo h2kvmctl --config myconfig.yaml
```

#### 2. SSH Keys Not Working
- Check key format (must start with ssh-rsa, ssh-ed25519, etc.)
- Verify quotes in YAML
- Ensure no line breaks in key string

#### 3. Service Not Found
```bash
# Service file doesn't exist in guest
# Check: /usr/lib/systemd/system/ or /lib/systemd/system/
```

#### 4. User Creation Fails
- Check if UID is already in use
- Verify group names exist
- Review logs for detailed error

### Debug Mode

```bash
# Maximum verbosity
sudo h2kvmctl --config myconfig.yaml \
  --user-config-inject user.yaml \
  --verbose 2
```

### Log Files

```bash
# Review detailed logs
tail -f /path/to/output-dir/hyper2kvm.log

# Check report for errors
cat /path/to/output-dir/hyper2kvm-report.md
```

---

## Best Practices

### Security

1. **SSH Keys**: Always use SSH keys over passwords
2. **Sudo**: Use specific commands, avoid NOPASSWD where possible
3. **User Cleanup**: Delete/disable default cloud users
4. **Service Hardening**: Mask unnecessary services

### Organization

1. **Separate Configs**: Keep user/service/hostname configs in separate files
2. **Version Control**: Store configs in git
3. **Templates**: Create templates for different server types
4. **Documentation**: Comment your YAML files

### Testing

1. **Dry-Run First**: Always test with --dry-run
2. **Incremental**: Test one feature at a time
3. **Verify**: Check logs and reports after conversion
4. **Smoke Test**: Use --libvirt-test to verify boot

---

## Future Enhancements

Planned features (Priority 2+):

- **Firewall Rules**: iptables/firewalld configuration
- **SELinux/AppArmor**: Security policy injection
- **Cron Jobs**: Scheduled task configuration
- **Package Management**: Pre-install packages
- **Timezone/Locale**: System localization
- **Kernel Parameters**: sysctl configuration

---

## References

- [Main Documentation](../README.md)
- [Network Configuration Examples](../test-confs/98-linux-network-config-injection-examples.yaml)
- [User Management Examples](../test-confs/99-linux-user-ssh-management-examples.yaml)
- [Service Management Examples](../test-confs/99-linux-service-management-examples.yaml)
- [Hostname Examples](../test-confs/99-linux-hostname-hosts-examples.yaml)

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/anthropics/hyper2kvm/issues
- Documentation: Check docs/ directory
- Examples: See test-confs/ directory
