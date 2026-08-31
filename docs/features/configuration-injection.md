# Configuration Injection Guide

**Guide to Pre-Boot Configuration Injection for Migrated VMs**

## Overview

h2kvm provides powerful configuration injection capabilities that allow you to customize VM settings **before first boot**. Unlike traditional cloud-init approaches that run on boot, these injectors work offline using the guestfs backend (GuestKit by default) to modify the VM disk image directly.

**Why Pre-Boot Injection?**
- ✅ **Deterministic:** Changes applied offline, guaranteed before boot
- ✅ **Safe:** No dependency on VM booting successfully
- ✅ **Fast:** Modify configuration without starting the VM
- ✅ **Flexible:** Works with any Linux distribution
- ✅ **Cloud-Free:** No cloud-init or guest agent dependencies

## Available Injectors

h2kvm supports five configuration injectors:

1. **[Network Configuration](#network-configuration-injection)** - Static IPs, bonds, bridges, VLANs
2. **[Hostname Configuration](#hostname-configuration-injection)** - Set system hostname
3. **[User Configuration](#user-configuration-injection)** - Create users, set passwords, SSH keys
4. **[Service Configuration](#service-configuration-injection)** - Enable/disable systemd services
5. **[First-Boot Scripts](#first-boot-script-injection)** - Run custom scripts on first boot

---

## Network Configuration Injection

Inject network configuration files for **systemd-networkd** or **NetworkManager** without cloud-init.

### Supported Network Managers

- ✅ **systemd-networkd** (`.network`, `.netdev` files)
- ✅ **NetworkManager** (`.nmconnection` files)

### Use Cases

- Static IP configuration for migrated VMs
- Bond/bridge/VLAN setup
- Virtual network devices (VXLANs, tunnels, macvlan)
- DNS and gateway configuration
- Interface naming and renaming

### Configuration Format

```yaml
network_config_inject:
  # systemd-networkd files
  network_files:
    - name: eth0                    # Creates /etc/systemd/network/10-eth0.network
      type: network                  # "network" or "netdev"
      priority: 10                   # File priority (default: 50)
      content: |
        [Match]
        Name=eth0

        [Network]
        Address=192.168.1.100/24
        Gateway=192.168.1.1
        DNS=8.8.8.8
        DNS=8.8.4.4

    - name: br0
      type: netdev                   # Virtual network device
      priority: 10
      content: |
        [NetDev]
        Name=br0
        Kind=bridge

        [Bridge]
        STP=yes

  # NetworkManager connection files
  nm_connections:
    - name: Production              # Creates /etc/NetworkManager/system-connections/Production.nmconnection
      content: |
        [connection]
        id=Production
        type=ethernet
        interface-name=eth0
        autoconnect=true

        [ipv4]
        method=manual
        address1=192.168.1.100/24,192.168.1.1
        dns=8.8.8.8;8.8.4.4;

        [ipv6]
        method=disabled

  # Optional: Enable services
  enable_networkd: true              # Enable systemd-networkd.service
  enable_network_manager: true       # Enable NetworkManager.service
```

### Examples

#### Static IP with systemd-networkd

```yaml
network_config_inject:
  network_files:
    - name: eth0
      type: network
      priority: 10
      content: |
        [Match]
        Name=eth0

        [Network]
        Address=10.0.1.50/24
        Gateway=10.0.1.1
        DNS=10.0.1.1
        Domains=example.com

  enable_networkd: true
```

#### Bonded Network (LACP)

```yaml
network_config_inject:
  network_files:
    # Create bond interface
    - name: bond0
      type: netdev
      priority: 10
      content: |
        [NetDev]
        Name=bond0
        Kind=bond

        [Bond]
        Mode=802.3ad
        LACPTransmitRate=fast

    # Bond configuration
    - name: bond0
      type: network
      priority: 11
      content: |
        [Match]
        Name=bond0

        [Network]
        Address=192.168.1.100/24
        Gateway=192.168.1.1

    # Slave interfaces
    - name: eth0
      type: network
      priority: 12
      content: |
        [Match]
        Name=eth0

        [Network]
        Bond=bond0

    - name: eth1
      type: network
      priority: 12
      content: |
        [Match]
        Name=eth1

        [Network]
        Bond=bond0

  enable_networkd: true
```

#### Bridge with VLAN

```yaml
network_config_inject:
  network_files:
    # Bridge device
    - name: br-vlan100
      type: netdev
      priority: 10
      content: |
        [NetDev]
        Name=br-vlan100
        Kind=bridge

    # VLAN device
    - name: vlan100
      type: netdev
      priority: 11
      content: |
        [NetDev]
        Name=vlan100
        Kind=vlan

        [VLAN]
        Id=100

    # Physical interface
    - name: eth0
      type: network
      priority: 20
      content: |
        [Match]
        Name=eth0

        [Network]
        VLAN=vlan100

    # VLAN to bridge
    - name: vlan100
      type: network
      priority: 21
      content: |
        [Match]
        Name=vlan100

        [Network]
        Bridge=br-vlan100

    # Bridge IP
    - name: br-vlan100
      type: network
      priority: 22
      content: |
        [Match]
        Name=br-vlan100

        [Network]
        Address=192.168.100.10/24

  enable_networkd: true
```

#### NetworkManager Connection

```yaml
network_config_inject:
  nm_connections:
    - name: Management
      content: |
        [connection]
        id=Management
        type=ethernet
        interface-name=eno1
        autoconnect=true
        autoconnect-priority=10

        [ethernet]
        mac-address=52:54:00:aa:bb:cc

        [ipv4]
        method=manual
        address1=10.10.10.50/24,10.10.10.1
        dns=10.10.10.1;
        dns-search=mgmt.example.com;

        [ipv6]
        method=link-local

  enable_network_manager: true
```

### File Locations

- **systemd-networkd**: `/etc/systemd/network/`
  - Priority determines order: `10-eth0.network`, `50-default.network`
- **NetworkManager**: `/etc/NetworkManager/system-connections/`
  - Permissions automatically set to `0600`

---

## Hostname Configuration Injection

Set the system hostname before first boot.

### Configuration Format

```yaml
hostname_config:
  hostname: production-web-01        # Simple hostname
  # OR
  fqdn: web01.production.example.com # Fully qualified domain name
```

### Examples

#### Simple Hostname

```yaml
hostname_config:
  hostname: database-server
```

#### FQDN with Domain

```yaml
hostname_config:
  fqdn: app01.datacenter.example.com
```

### Implementation Details

- Updates `/etc/hostname`
- Updates `/etc/hosts` with FQDN mapping
- Preserves localhost entries
- Safe for both RHEL and Debian-based systems

---

## User Configuration Injection

Create users, set passwords, and configure SSH keys before first boot.

### Configuration Format

```yaml
user_config:
  users:
    - username: deploy
      uid: 1001                      # Optional: specific UID
      gid: 1001                      # Optional: specific GID
      groups:                        # Additional groups
        - wheel
        - docker
      shell: /bin/bash
      home: /home/deploy             # Default: /home/{username}
      comment: "Deployment User"     # GECOS field
      password_hash: "$6$rounds=4096$..."  # Hashed password (see below)
      ssh_authorized_keys:
        - "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... user@host"
        - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... backup@host"
      sudo: true                     # Add to sudoers
      sudo_nopasswd: true            # Passwordless sudo

    - username: appuser
      groups: [users, appgroup]
      shell: /bin/bash
      ssh_authorized_keys:
        - "ssh-rsa AAAAB3... deploy-key"
```

### Password Hashing

Generate password hashes with `mkpasswd`:

```bash
# Install mkpasswd (Fedora/RHEL)
sudo dnf install whois

# Generate SHA-512 password hash
mkpasswd -m sha-512 MySecurePassword

# Output:
# $6$rounds=656000$xyz...$abc...
```

Or with Python:

```python
import crypt
import secrets

# Generate salt
salt = crypt.mksalt(crypt.METHOD_SHA512)

# Hash password
password_hash = crypt.crypt("MySecurePassword", salt)
print(password_hash)
```

### Examples

#### Create Deployment User with SSH Key

```yaml
user_config:
  users:
    - username: deploy
      groups: [wheel, docker]
      shell: /bin/bash
      ssh_authorized_keys:
        - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFoo... deploy@cicd"
      sudo: true
      sudo_nopasswd: true
```

#### Multiple Users with Different Permissions

```yaml
user_config:
  users:
    # Admin user
    - username: admin
      uid: 2000
      groups: [wheel]
      password_hash: "$6$rounds=656000$salt$hash"
      sudo: true
      sudo_nopasswd: false

    # Application user
    - username: webapp
      uid: 3000
      shell: /bin/bash
      groups: [www-data]
      comment: "Web Application User"

    # Service account
    - username: monitoring
      uid: 4000
      shell: /sbin/nologin
      groups: [monitoring]
      ssh_authorized_keys:
        - "ssh-rsa AAAAB3... monitoring@nagios"
```

### Implementation Details

- Uses `/etc/passwd`, `/etc/shadow`, `/etc/group`
- Creates home directories with correct permissions
- Sets up `.ssh/authorized_keys` with mode `0600`
- Configures sudoers via `/etc/sudoers.d/{username}`
- Validates UID/GID conflicts

---

## Service Configuration Injection

Enable or disable systemd services before first boot.

### Configuration Format

```yaml
service_config:
  enable:
    - sshd                          # Enable SSH daemon
    - firewalld                     # Enable firewall
    - chronyd                       # Enable NTP
    - NetworkManager                # Enable NetworkManager

  disable:
    - bluetooth                     # Disable Bluetooth
    - cups                          # Disable printing
    - avahi-daemon                  # Disable mDNS
```

### Examples

#### Standard Server Configuration

```yaml
service_config:
  enable:
    - sshd
    - firewalld
    - chronyd
    - rsyslog

  disable:
    - bluetooth
    - cups
    - ModemManager
```

#### Minimal Container Host

```yaml
service_config:
  enable:
    - sshd
    - docker
    - containerd

  disable:
    - firewalld          # Using iptables directly
    - NetworkManager     # Using systemd-networkd
    - bluetooth
    - cups
    - avahi-daemon
```

### Implementation Details

- Creates/removes symlinks in `/etc/systemd/system/multi-user.target.wants/`
- Verifies service units exist before enabling
- Supports `.service`, `.socket`, `.timer` units
- Safe for systems not yet booted

---

## First-Boot Script Injection

Execute custom scripts automatically on first boot via systemd.

### Use Cases

- Post-migration cleanup
- Application initialization
- Configuration finalization
- Environment-specific setup
- Integration with orchestration tools

### Configuration Format

```yaml
firstboot_config:
  # Single script (simple form)
  script: |
    #!/bin/bash
    echo "First boot setup"
    systemctl restart NetworkManager

  # OR: Multiple scripts with ordering
  scripts:
    - name: network-setup
      order: 10                    # Lower runs first
      content: |
        #!/bin/bash
        echo "Configuring network..."
        nmcli connection reload

    - name: app-init
      order: 20
      content: |
        #!/bin/bash
        echo "Initializing application..."
        /opt/app/initialize.sh

    - name: cleanup
      order: 90
      content: |
        #!/bin/bash
        echo "Final cleanup..."
        systemctl disable h2kvm-firstboot.service

  # Service configuration
  service_name: h2kvm-firstboot   # Default
  keep_enabled: false                  # Disable service after first run

  # Systemd service customization (optional)
  service:
    Description: "Custom first boot setup"
    After: network-online.target
    RequiresMountsFor: [/data, /opt/app]
    Environment:
      - "APP_ENV=production"
      - "DEBUG=0"
```

### Examples

#### Simple Network Restart

```yaml
firstboot_config:
  script: |
    #!/bin/bash
    systemctl restart NetworkManager
    nmcli connection reload
```

#### Multi-Stage Initialization

```yaml
firstboot_config:
  scripts:
    - name: mount-storage
      order: 10
      content: |
        #!/bin/bash
        set -e
        echo "Mounting storage..."
        mount /dev/vdb1 /data

    - name: start-services
      order: 20
      content: |
        #!/bin/bash
        set -e
        echo "Starting services..."
        systemctl start docker
        systemctl start nginx

    - name: notify-complete
      order: 90
      content: |
        #!/bin/bash
        curl -X POST https://api.example.com/vm-ready \
          -d "hostname=$(hostname)" \
          -d "status=ready"

  service:
    After: "network-online.target docker.service"
    Environment:
      - "DEPLOYMENT_ID={{ deployment_id }}"
```

#### Production Environment Setup

```yaml
firstboot_config:
  scripts:
    - name: security-hardening
      order: 5
      content: |
        #!/bin/bash
        # Apply security baseline
        chmod 0700 /root
        systemctl mask debug-shell.service

    - name: monitoring-setup
      order: 15
      content: |
        #!/bin/bash
        # Configure monitoring agent
        /opt/monitoring/register.sh --datacenter=dc1
        systemctl enable monitoring-agent
        systemctl start monitoring-agent

    - name: app-deployment
      order: 20
      content: |
        #!/bin/bash
        # Pull latest application
        docker pull registry.internal/app:latest
        docker-compose up -d

    - name: cleanup-and-disable
      order: 99
      content: |
        #!/bin/bash
        # Clean up firstboot artifacts
        rm -rf /var/lib/h2kvm-firstboot
        systemctl disable h2kvm-firstboot.service

  service:
    Description: "Production First Boot Setup"
    After: "network-online.target docker.service"
    RequiresMountsFor: /data
    Environment:
      - "ENV=production"
      - "REGION=us-east-1"
```

### Script Execution

Scripts execute in order (by `order` field, lower first):

1. Scripts run as **root** via systemd oneshot service
2. Output logged to `/var/log/h2kvm-firstboot.log`
3. Service auto-disables after completion (unless `keep_enabled: true`)
4. Failures don't prevent boot (service continues)

### Runner Script Structure

The injector creates:
- Individual script files in `/usr/local/lib/h2kvm-firstboot/`
- Master runner script that executes all in order
- Systemd service unit at `/etc/systemd/system/{service_name}.service`
- Symlink in `/etc/systemd/system/multi-user.target.wants/`

---

## Complete Integration Example

Combining all injectors for a production web server:

```yaml
# Production web server configuration
hostname_config:
  fqdn: web01.production.example.com

user_config:
  users:
    - username: deploy
      groups: [wheel, docker]
      shell: /bin/bash
      ssh_authorized_keys:
        - "ssh-ed25519 AAAAC3... deploy@cicd"
      sudo: true
      sudo_nopasswd: true

    - username: webapp
      uid: 5000
      groups: [webapp]
      shell: /bin/bash
      home: /opt/webapp

network_config_inject:
  network_files:
    - name: eth0
      type: network
      priority: 10
      content: |
        [Match]
        Name=eth0

        [Network]
        Address=10.0.1.50/24
        Gateway=10.0.1.1
        DNS=10.0.1.1
        DNS=8.8.8.8
        Domains=production.example.com

  enable_networkd: true

service_config:
  enable:
    - sshd
    - firewalld
    - docker
    - nginx

  disable:
    - bluetooth
    - cups

firstboot_config:
  scripts:
    - name: firewall-rules
      order: 10
      content: |
        #!/bin/bash
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --reload

    - name: deploy-app
      order: 20
      content: |
        #!/bin/bash
        cd /opt/webapp
        docker-compose pull
        docker-compose up -d

    - name: register-monitoring
      order: 30
      content: |
        #!/bin/bash
        curl -X POST https://monitoring.example.com/register \
          -d "host=$(hostname -f)" \
          -d "ip=$(ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')"

  service:
    After: "network-online.target docker.service nginx.service"
    Environment:
      - "ENVIRONMENT=production"
```

---

## Best Practices

### Security

1. **SSH Keys Over Passwords:** Always prefer SSH key authentication
2. **Hash Passwords:** Never store plaintext passwords in YAML
3. **Minimal Permissions:** Create service accounts with `nologin` shells
4. **Sudoers Configuration:** Use `sudo_nopasswd: false` for human users

### Network Configuration

1. **Test Configurations:** Validate network configs on test VM first
2. **Priority Ordering:** Use lower numbers for physical interfaces
3. **Service Enablement:** Enable corresponding network manager service
4. **Fallback Configuration:** Consider DHCP fallback for recovery

### First-Boot Scripts

1. **Idempotency:** Scripts should be safe to run multiple times
2. **Error Handling:** Use `set -e` or proper error checks
3. **Logging:** Add logging for troubleshooting
4. **Cleanup:** Disable service after completion

### Dry-Run Testing

Always test configuration injection with `--dry-run` first:

```bash
sudo h2kvmctl local \
  --vmdk /path/to/vm.vmdk \
  --manifest /path/to/config.yaml \
  --dry-run
```

Check logs for:
- Files that would be created
- Services that would be enabled
- Users that would be created

---

## Troubleshooting

### Network Not Working After Boot

1. Check if correct network manager is enabled:
   ```bash
   systemctl status systemd-networkd
   systemctl status NetworkManager
   ```

2. Verify configuration files exist:
   ```bash
   ls -la /etc/systemd/network/
   ls -la /etc/NetworkManager/system-connections/
   ```

3. Check network manager logs:
   ```bash
   journalctl -u systemd-networkd
   journalctl -u NetworkManager
   ```

### SSH Login Fails

1. Verify user was created:
   ```bash
   grep username /etc/passwd
   ```

2. Check SSH key permissions:
   ```bash
   ls -la /home/username/.ssh/
   # Should be: drwx------ .ssh/
   # Should be: -rw------- authorized_keys
   ```

3. Check SSH daemon logs:
   ```bash
   journalctl -u sshd
   ```

### First-Boot Script Didn't Run

1. Check if service exists:
   ```bash
   systemctl list-unit-files | grep firstboot
   ```

2. Check service status:
   ```bash
   systemctl status h2kvm-firstboot.service
   ```

3. View script logs:
   ```bash
   cat /var/log/h2kvm-firstboot.log
   journalctl -u h2kvm-firstboot.service
   ```

4. Manually trigger (for testing):
   ```bash
   systemctl start h2kvm-firstboot.service
   ```

---

## See Also

- [YAML Examples](05-YAML-Examples.md) - Complete manifest examples
- [Batch Migration Guide](Batch-Migration-Features-Guide.md) - Using injectors in batch workflows
- [Library API](08-Library-API.md) - Programmatic injection usage
- [Quick Start](03-Quick-Start.md) - Basic usage examples
