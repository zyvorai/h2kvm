# Hyper2KVM LUKS Auto-Unlock System

Production-grade LUKS auto-unlock for:
- Bare metal servers
- Virtual machines
- Kubernetes worker nodes
- Cloud instances

## Features

✅ **TPM2 Auto-Unlock** - Hardware-backed, automatic unlock
✅ **HashiCorp Vault Integration** - Network-based key management
✅ **Keyfile Support** - Filesystem-based semi-automatic unlock
✅ **Initramfs Integration** - Unlock at boot before root mount
✅ **Kubernetes Native** - DaemonSet for worker node unlock
✅ **Secure** - Memory wiping, HKDF key derivation, audit logging
✅ **Multi-Factor** - Combine TPM + Vault for enhanced security

---

## Architecture

```
Boot Flow:
  BIOS/UEFI
    ↓
  Bootloader (GRUB)
    ↓
  Kernel + Initramfs
    ↓
  dracut: hyper2kvm-luks-unlock
    ↓
  Try unlock sources (TPM → Vault → Keyfile)
    ↓
  cryptsetup open /dev/sda1 hyper2kvm-xxx
    ↓
  LVM activation
    ↓
  Mount root filesystem
    ↓
  systemd init
    ↓
  Kubernetes kubelet (if applicable)
```

---

## Quick Start

### 1. Install

```bash
pip install hyper2kvm[luks]
```

### 2. Seal LUKS Key to TPM2

```bash
# Create LUKS key (or use existing)
dd if=/dev/urandom of=/root/luks.key bs=1 count=32

# Add to LUKS device
cryptsetup luksAddKey /dev/sda1 /root/luks.key

# Seal to TPM2
hyper2kvm-luks seal /root/luks.key \
  --handle 0x81000010 \
  --pcr 0 1 2 3 7

# Verify
hyper2kvm-luks status
```

### 3. Configure Auto-Unlock

Create `/etc/hyper2kvm/luks.json`:

```json
{
  "tpm_handle": "0x81000010"
}
```

### 4. Install dracut Module

```bash
# Copy dracut module
cp -r contrib/dracut/90hyper2kvm-luks /usr/lib/dracut/modules.d/

# Rebuild initramfs
dracut -f

# Reboot
reboot
```

---

## Configuration

### TPM2 Only

`/etc/hyper2kvm/luks.json`:
```json
{
  "tpm_handle": "0x81000010"
}
```

### Vault Only

```json
{
  "vault": {
    "addr": "https://vault.example.com:8200",
    "token": "s.xxxxxx",
    "path": "secret/hyper2kvm/luks"
  }
}
```

### TPM + Vault (Multi-Factor)

```json
{
  "tpm_handle": "0x81000010",
  "vault": {
    "addr": "https://vault.example.com:8200",
    "token": "s.xxxxxx",
    "path": "secret/hyper2kvm/luks"
  }
}
```

Keys from both sources are combined using HKDF.

### Keyfile Fallback

```json
{
  "tpm_handle": "0x81000010",
  "keyfile": "/etc/hyper2kvm/luks.key"
}
```

### Environment Variables

Alternatively, use environment variables:

```bash
export HYPER2KVM_TPM_HANDLE=0x81000010
export HYPER2KVM_VAULT_ADDR=https://vault:8200
export HYPER2KVM_VAULT_TOKEN=s.xxxxxx
export HYPER2KVM_VAULT_PATH=secret/hyper2kvm/luks
export HYPER2KVM_LUKS_KEYFILE=/etc/hyper2kvm/luks.key
```

---

## Kubernetes Deployment

### 1. Deploy DaemonSet

```bash
kubectl apply -f contrib/kubernetes/daemonset.yaml
```

### 2. Create Vault Secret

```bash
# In Vault
vault kv put secret/hyper2kvm/luks \
  key=$(xxd -p /root/luks.key | tr -d '\n')

# Create Kubernetes secret with Vault token
kubectl create secret generic vault-token \
  --from-literal=token=s.xxxxxx \
  -n hyper2kvm-system
```

### 3. Label Nodes

```bash
kubectl label node worker1 hyper2kvm.io/luks=true
```

### 4. Verify

```bash
kubectl logs -n hyper2kvm-system \
  daemonset/hyper2kvm-luks-unlocker
```

---

## Security Properties

### TPM2 Unlock

✅ **Physical Binding** - Key only unseals on same hardware
✅ **Firmware Binding** - Key only unseals with same firmware
✅ **Kernel Binding** - Key only unseals with same kernel
✅ **Secure Boot** - Respects Secure Boot state (PCR 7)
✅ **No Network** - Works offline

### Vault Unlock

✅ **Centralized Key Management** - One place for all keys
✅ **Access Audit** - Full audit trail of key access
✅ **Dynamic Secrets** - Rotate keys without touching nodes
✅ **Policy-Based Access** - Fine-grained access control
⚠️ **Network Required** - Needs Vault connectivity at boot

### Multi-Factor (TPM + Vault)

✅ **Defense in Depth** - Both keys required
✅ **Prevents Disk Theft** - TPM key won't unseal on different hardware
✅ **Prevents Network Attacks** - Vault key alone insufficient
✅ **Auditability** - Vault tracks all access attempts

---

## CLI Usage

### List LUKS Devices

```bash
hyper2kvm-luks list
```

Output:
```
Found 2 LUKS devices:
  /dev/sda1
    UUID: 12345678-1234-1234-1234-123456789012
  /dev/sdb1
    UUID: 87654321-4321-4321-4321-210987654321
```

### Show Unlock Status

```bash
hyper2kvm-luks status
```

Output:
```
LUKS Device Status:
  /dev/sda1: ✓ UNLOCKED
    Mapper: /dev/mapper/hyper2kvm-abc123def456
  /dev/sdb1: ✗ LOCKED
```

### Manual Unlock

```bash
hyper2kvm-luks unlock -v
```

### Seal Key to TPM2

```bash
hyper2kvm-luks seal /root/luks.key \
  --handle 0x81000010 \
  --pcr 0 1 2 3 7
```

---

## Troubleshooting

### TPM Unlock Fails

```bash
# Check TPM is available
ls -l /dev/tpm*

# Check tpm2-tools installed
which tpm2_unseal

# Read PCRs
tpm2_pcrread

# Try manual unseal
tpm2_unseal -c 0x81000010
```

### Vault Unlock Fails

```bash
# Check connectivity
curl -k $VAULT_ADDR/v1/sys/health

# Check token
vault token lookup

# Check secret exists
vault kv get secret/hyper2kvm/luks
```

### Initramfs Issues

```bash
# Check dracut module installed
ls /usr/lib/dracut/modules.d/90hyper2kvm-luks/

# Rebuild with verbose
dracut -f -v

# Check initramfs contents
lsinitrd | grep hyper2kvm
```

### Logs

```bash
# Boot logs
journalctl -b | grep hyper2kvm-luks

# Initramfs logs
journalctl -b 0 -u hyper2kvm-luks-unlock
```

---

## Advanced Usage

### PCR Policy Customization

```bash
# Seal only to firmware (PCR 0)
hyper2kvm-luks seal /root/luks.key --pcr 0

# Seal to firmware + bootloader (PCRs 0,1,2,3)
hyper2kvm-luks seal /root/luks.key --pcr 0 1 2 3

# Seal to firmware + Secure Boot (PCRs 0,7)
hyper2kvm-luks seal /root/luks.key --pcr 0 7
```

### Vault with Kubernetes Auth

```python
from hyper2kvm.luks.unlocker import VaultKeySource

source = VaultKeySource.from_kubernetes_sa(
    addr="https://vault:8200",
    role="hyper2kvm-luks",
    path="secret/hyper2kvm/luks"
)

key = source.get_key()
```

### Programmatic Usage

```python
from hyper2kvm.luks import LUKSUnlocker

unlocker = LUKSUnlocker(
    tpm_handle="0x81000010",
    vault_config={
        "addr": "https://vault:8200",
        "token": "s.xxxxxx",
        "path": "secret/hyper2kvm/luks",
    }
)

results = unlocker.unlock_all()
for device, success in results.items():
    print(f"{device}: {'✓' if success else '✗'}")
```

---

## Comparison with Alternatives

| Feature | Hyper2KVM | Clevis | systemd-cryptenroll |
|---------|-----------|---------|---------------------|
| TPM2 Support | ✅ | ✅ | ✅ |
| Vault Support | ✅ | ❌ | ❌ |
| Kubernetes Integration | ✅ | ❌ | ❌ |
| Multi-Factor | ✅ (HKDF) | ⚠️ (limited) | ❌ |
| Initramfs Safe | ✅ | ✅ | ✅ |
| Python API | ✅ | ❌ | ❌ |

---

## Performance

- **TPM Unlock**: ~200ms per device
- **Vault Unlock**: ~500ms per device (network dependent)
- **Keyfile Unlock**: ~50ms per device
- **Overhead**: Minimal (<1s added to boot time)

---

## Security Audit

✅ **No secrets in logs** - Keys never logged
✅ **Secure memory wiping** - Keys zeroed after use
✅ **No secrets in cmdline** - Keys passed via files
✅ **HKDF key derivation** - Cryptographically sound combining
✅ **Audit trail** - Vault provides full audit log
✅ **Principle of least privilege** - Minimal permissions

---

## License

Apache-2.0

---

## Support

- GitHub Issues: https://github.com/anthropics/hyper2kvm/issues
- Documentation: https://hyper2kvm.readthedocs.io/
- Security: security@hyper2kvm.io
