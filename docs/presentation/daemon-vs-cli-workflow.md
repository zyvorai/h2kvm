# hyper2kvm: Daemon vs CLI Mode

## Architecture Overview

```mermaid
graph TD
    CLI1[CLI: User Runs Command] --> CLI2[Process Single VM]
    CLI2 --> CLI3[Convert & Fix]
    CLI3 --> CLI4[Output Result]
    CLI4 --> CLI5[Exit]

    D1[Daemon: Watch Directory] --> D2{New File?}
    D2 -->|Yes| D3[Queue VM]
    D2 -->|No| D1
    D3 --> D4[Process Pipeline]
    D4 --> D5[Archive Source]
    D5 --> D1

    classDef cliStyle fill:#2196F3,stroke:#1565C0,color:#fff
    classDef daemonStyle fill:#4CAF50,stroke:#2E7D32,color:#fff

    class CLI1,CLI2,CLI3,CLI4,CLI5 cliStyle
    class D1,D2,D3,D4,D5 daemonStyle
```

---

## Command Line Mode

### Use Case
**Interactive, one-time conversions**

### Workflow
```
User → Command → Process → Result → Exit
```

### Example
```bash
hyper2kvm local \
  --source vm.vmdk \
  --output /vms/converted.qcow2 \
  --compress
```

### Characteristics
- ✓ Interactive control
- ✓ Immediate feedback
- ✓ Single VM focus
- ✓ Manual execution

---

## Daemon Mode

### Use Case
**Automated, continuous processing**

### Workflow
```
Drop File → Auto-Detect → Process → Archive → Repeat
```

### Example
```bash
# Start daemon
hyper2kvm --config daemon.yaml

# Drop files and they're auto-processed
cp *.vmdk /queue/
```

### Characteristics
- ✓ Unattended operation
- ✓ Batch processing
- ✓ Watch directory
- ✓ Production deployments

---

## Pipeline Comparison

### CLI Mode Pipeline
```mermaid
graph LR
    C1[Source] --> C2[Flatten]
    C2 --> C3[Fix]
    C3 --> C4[Convert]
    C4 --> C5[Test]
    C5 --> C6[Done]

    classDef cliClass fill:#E3F2FD,stroke:#1976D2
    class C1,C2,C3,C4,C5,C6 cliClass
```

### Daemon Mode Pipeline
```mermaid
graph LR
    D1[Watch] --> D2[Detect]
    D2 --> D3[Flatten]
    D3 --> D4[Fix]
    D4 --> D5[Convert]
    D5 --> D6[Archive]
    D6 --> D1

    classDef daemonClass fill:#E8F5E9,stroke:#388E3C
    class D1,D2,D3,D4,D5,D6 daemonClass
```

---

## Decision Matrix

| Feature | CLI Mode | Daemon Mode |
|---------|----------|-------------|
| **Execution** | Manual | Automatic |
| **Volume** | Single VM | Multiple VMs |
| **Use Case** | Testing, Dev | Production |
| **Monitoring** | Terminal | Logs/Journal |
| **Integration** | Scripts | CI/CD, Cron |
| **Restart** | Manual | Systemd |

---

## Daemon Architecture Detail

```mermaid
graph TD
    I1[Input: queue/vm1.vmdk] --> W1[Watchdog: inotify]
    I2[Input: queue/vm2.ova] --> W1
    I3[Input: queue/vm3.vhd] --> W1

    W1 --> W2[File Detection]
    W2 --> W3[Type Classification]

    W3 --> P1[Flatten Chain]
    P1 --> P2[Offline Fixes]
    P2 --> P3[Format Convert]
    P3 --> P4[Validation]

    P4 --> O1[Output: output/vm1/]
    P4 --> O2[Output: output/vm2/]
    P4 --> O3[Archive: .processed/]

    classDef inputClass fill:#FFF3E0,stroke:#F57C00
    classDef watchClass fill:#E1F5FE,stroke:#0277BD
    classDef processClass fill:#F3E5F5,stroke:#7B1FA2
    classDef outputClass fill:#E8F5E9,stroke:#2E7D32

    class I1,I2,I3 inputClass
    class W1,W2,W3 watchClass
    class P1,P2,P3,P4 processClass
    class O1,O2,O3 outputClass
```

---

## Production Deployment

```mermaid
graph LR
    S1[vSphere Export] --> D1[systemd Service]
    S2[Manual Drop] --> D1
    S3[Cron Job] --> D1

    D1 --> D2[Watch Queue]
    D2 --> D3[Process VMs]

    D3 --> T1[libvirt Pool]
    D3 --> T2[Storage Array]
    D3 --> T3[Archive]

    classDef sourceClass fill:#FFEBEE,stroke:#C62828
    classDef daemonClass fill:#E8F5E9,stroke:#2E7D32
    classDef destClass fill:#E3F2FD,stroke:#1565C0

    class S1,S2,S3 sourceClass
    class D1,D2,D3 daemonClass
    class T1,T2,T3 destClass
```

### Deployment Commands
```bash
# Install daemon
sudo cp daemon.yaml /etc/hyper2kvm/
sudo systemctl enable --now hyper2kvm.service

# Monitor
sudo journalctl -u hyper2kvm.service -f

# Drop VMs
cp exports/*.vmdk /var/lib/hyper2kvm/queue/
```

---

## Key Takeaways

### CLI Mode
- **Interactive** - Full control, immediate feedback
- **Development** - Testing and troubleshooting
- **Single VM** - One-off conversions

### Daemon Mode
- **Automated** - Drop and forget
- **Production** - 24/7 processing
- **Scale** - Batch operations

### Choose CLI for:
- Development and testing
- Manual control needed
- Single VM migrations
- Interactive troubleshooting

### Choose Daemon for:
- Production environments
- Automated workflows
- Batch processing
- CI/CD integration
