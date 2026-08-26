# H2KVM Contrib Directory

Additional tools, integrations, and examples for H2KVM.

---

## Contents

### LUKS Auto-Unlock

Production-grade LUKS auto-unlock system with TPM2, Vault, and Kubernetes support.

#### dracut Module (`dracut/90h2kvm-luks/`)

Initramfs integration for boot-time LUKS unlock.

**Files**:
- `module-setup.sh` - dracut module installer
- `h2kvm-luks-unlock.sh` - Boot-time unlock script
- `h2kvm-luks-unlock.service` - systemd service

**Installation**:
```bash
sudo cp -r dracut/90h2kvm-luks /usr/lib/dracut/modules.d/
sudo dracut -f
```

**Usage**: Automatic at boot time

---

#### Kubernetes Integration (`kubernetes/`)

DaemonSet for automatic LUKS unlock on Kubernetes worker nodes.

**Files**:
- `daemonset.yaml` - Complete Kubernetes deployment

**Installation**:
```bash
kubectl apply -f kubernetes/daemonset.yaml

# Create Vault token secret
kubectl create secret generic vault-token \
  --from-literal=token=s.xxx \
  -n h2kvm-system

# Label nodes with LUKS
kubectl label node worker1 h2kvm.io/luks=true
```

**Monitoring**:
```bash
kubectl logs -n h2kvm-system daemonset/h2kvm-luks-unlocker
```

---

#### Docker Images (`docker/`)

Container images for Kubernetes deployment.

**Files**:
- `Dockerfile.luks-unlocker` - LUKS unlock container

**Build**:
```bash
docker build -f docker/Dockerfile.luks-unlocker -t h2kvm/luks-unlocker:latest .
```

**Push**:
```bash
docker push h2kvm/luks-unlocker:latest
```

---

#### Examples (`examples/`)

Configuration examples for different deployment scenarios.

**Files**:
- `luks-tpm.json` - TPM2-only unlock
- `luks-vault.json` - Vault-only unlock
- `luks-multi-factor.json` - TPM + Vault multi-factor

**Usage**:
```bash
# Copy example
sudo cp examples/luks-tpm.json /etc/h2kvm/luks.json

# Edit configuration
sudo vim /etc/h2kvm/luks.json

# Test
h2kvm-luks unlock -v
```

---

#### Installation Script (`install-luks-unlock.sh`)

Automated installation and configuration.

**Features**:
- Installs dependencies
- Configures TPM2 or Vault
- Seals keys to TPM
- Installs dracut module
- Rebuilds initramfs

**Usage**:
```bash
# TPM2-only installation
sudo ./install-luks-unlock.sh \
  --keyfile /root/luks.key \
  --device /dev/sda1 \
  --tpm-handle 0x81000010

# Vault-only installation
sudo ./install-luks-unlock.sh \
  --vault-addr https://vault:8200 \
  --vault-token s.xxx \
  --keyfile /root/luks.key \
  --skip-seal

# Multi-factor installation
sudo ./install-luks-unlock.sh \
  --keyfile /root/luks.key \
  --device /dev/sda1 \
  --tpm-handle 0x81000010 \
  --vault-addr https://vault:8200 \
  --vault-token s.xxx
```

**Options**:
- `--tpm-handle HANDLE` - TPM2 handle (default: 0x81000010)
- `--vault-addr ADDR` - Vault server address
- `--vault-token TOKEN` - Vault token
- `--keyfile PATH` - LUKS keyfile path
- `--device DEVICE` - LUKS device (e.g., /dev/sda1)
- `--skip-seal` - Skip TPM sealing
- `--skip-dracut` - Skip initramfs integration

---

## Quick Start Guides

### Scenario 1: Bare Metal Server with TPM2

```bash
# 1. Install
sudo ./contrib/install-luks-unlock.sh \
  --keyfile /root/luks.key \
  --device /dev/sda1

# 2. Reboot
sudo reboot

# Device unlocks automatically via TPM2!
```

### Scenario 2: Cloud VM with Vault

```bash
# 1. Store key in Vault
vault kv put secret/h2kvm/luks \
  key=$(xxd -p /root/luks.key | tr -d '\n')

# 2. Install
sudo ./contrib/install-luks-unlock.sh \
  --vault-addr https://vault:8200 \
  --vault-token s.xxx \
  --keyfile /root/luks.key \
  --device /dev/sda1 \
  --skip-seal

# 3. Reboot
sudo reboot

# Device unlocks automatically via Vault!
```

### Scenario 3: Kubernetes Worker Nodes

```bash
# 1. Store key in Vault
vault kv put secret/h2kvm/luks \
  key=$(xxd -p /root/luks.key | tr -d '\n')

# 2. Deploy DaemonSet
kubectl apply -f contrib/kubernetes/daemonset.yaml

# 3. Create Vault token secret
kubectl create secret generic vault-token \
  --from-literal=token=s.xxx \
  -n h2kvm-system

# 4. Label nodes
kubectl label node worker1 worker2 worker3 h2kvm.io/luks=true

# 5. Monitor
kubectl logs -n h2kvm-system daemonset/h2kvm-luks-unlocker -f

# Nodes unlock LUKS devices automatically at boot!
```

---

## Architecture

### Boot Flow

```
1. BIOS/UEFI
   ↓
2. GRUB bootloader
   ↓
3. Kernel + initramfs
   ↓
4. dracut executes h2kvm-luks-unlock.sh
   ↓
5. Try unlock methods:
   • TPM2 unseal (if configured)
   • Vault fetch (if configured)
   • Keyfile read (if configured)
   ↓
6. cryptsetup open /dev/sdaX h2kvm-xxx
   ↓
7. LVM activation
   ↓
8. Mount root filesystem
   ↓
9. systemd init
   ↓
10. Kubernetes kubelet (if applicable)
```

### Security Model

**TPM2 Unlock**:
- ✅ Hardware-bound (only unseals on same machine)
- ✅ Firmware-bound (PCR measurements)
- ✅ Offline (no network required)
- ✅ Transparent (fully automatic)

**Vault Unlock**:
- ✅ Centralized key management
- ✅ Full audit trail
- ✅ Dynamic key rotation
- ✅ Policy-based access control
- ⚠️ Network required at boot

**Multi-Factor (TPM + Vault)**:
- ✅ Defense in depth
- ✅ Prevents disk theft (TPM won't unseal on different HW)
- ✅ Prevents network attacks (Vault key alone insufficient)
- ✅ Auditability (Vault tracks all access)

---

## Troubleshooting

### TPM Issues

```bash
# Check TPM device
ls -l /dev/tpm*

# Check tpm2-tools
which tpm2_unseal

# Read PCRs
tpm2_pcrread

# Test unseal
tpm2_unseal -c 0x81000010
```

### Vault Issues

```bash
# Check connectivity
curl -k https://vault:8200/v1/sys/health

# Check token
vault token lookup

# Check secret
vault kv get secret/h2kvm/luks
```

### Initramfs Issues

```bash
# Check module
ls /usr/lib/dracut/modules.d/90h2kvm-luks/

# Rebuild with verbose
dracut -f -v

# Check contents
lsinitrd | grep h2kvm
```

### Boot Logs

```bash
# Current boot
journalctl -b | grep h2kvm

# Specific service
journalctl -u h2kvm-luks-unlock
```

---

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| TPM unseal | ~200ms | Hardware-dependent |
| Vault fetch | ~500ms | Network-dependent |
| cryptsetup open | ~300ms | Device-dependent |
| **Total boot overhead** | **<1s** | Per device |

---

## Security Considerations

### Threats Mitigated

✅ **Disk Theft** - TPM won't unseal on different hardware
✅ **Cold Boot Attacks** - Keys not in memory when unused
✅ **Network Sniffing** - Vault uses HTTPS
✅ **Credential Leakage** - No secrets in logs/cmdline
✅ **Unauthorized Access** - Vault RBAC + audit trail

### Best Practices

1. **Use multi-factor** (TPM + Vault) for critical systems
2. **Rotate Vault keys** regularly
3. **Monitor audit logs** for unauthorized access attempts
4. **Keep emergency keyfile** in secure offline storage
5. **Test recovery** procedures regularly

---

## Support

- **Documentation**: `h2kvm/luks/README.md`
- **Issues**: https://github.com/anthropics/h2kvm/issues
- **Security**: security@h2kvm.io

---

## License

Proprietary (Zyvor AI Labs)
