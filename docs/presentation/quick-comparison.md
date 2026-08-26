# hyper2kvm: Quick Mode Comparison

## One-Page Overview

```mermaid
graph TD
    C1[CLI: User runs command] --> C2[Process VM]
    C2 --> C3[Exit]

    D1[Daemon: Watch /queue] --> D2[Auto-detect]
    D2 --> D3[Process]
    D3 --> D4[Archive]
    D4 --> D1

    classDef cliStyle fill:#2196F3,stroke:#1565C0,color:#fff
    classDef daemonStyle fill:#4CAF50,stroke:#2E7D32,color:#fff

    class C1,C2,C3 cliStyle
    class D1,D2,D3,D4 daemonStyle
```

---

## Side-by-Side Comparison

| Aspect | CLI Mode | Daemon Mode |
|--------|----------|-------------|
| **Trigger** | Manual command | File drop |
| **Process** | One VM | Continuous |
| **Feedback** | Interactive | Logs |
| **Use Case** | Dev/Testing | Production |
| **Deployment** | Ad-hoc | systemd service |

---

## Quick Commands

### CLI Mode
```bash
# Single VM conversion
hyper2kvm local --source vm.vmdk --output vm.qcow2
```

### Daemon Mode
```bash
# Start daemon
sudo systemctl start hyper2kvm.service

# Drop files → auto-processed
cp *.vmdk /var/lib/hyper2kvm/queue/
```

---

## When to Use

### Use CLI Mode 👨‍💻
- Testing a single VM
- Development work
- Need immediate feedback
- Manual control required

### Use Daemon Mode ⚙️
- Production environment
- Batch processing
- Automated workflows
- Overnight operations
- CI/CD integration
