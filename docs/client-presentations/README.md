# hyper2kvm Client Presentations

57 slide decks + 4 templates covering business value, architecture, migration guides, competitive analysis, and live demos.

All presentations available as HTML (viewable in browser) and PDF (printable).

## Presentation Index

### Business & Executive

| # | Title | Pages | Audience |
|---|-------|-------|----------|
| 01 | Business Value | 8 | C-suite, VP Infrastructure |
| 08 | ROI Calculator | 6 | Finance, Procurement |
| 10 | Executive Summary | 4 | Board, CTO |
| 24 | ROI Calculator (Updated) | 6 | Finance, Procurement |
| 26 | Executive Summary (Updated) | 4 | Board, CTO |
| 48 | Project Management | 6 | PMO, Program Managers |
| 50 | Licensing & TCO | 6 | Finance, Legal |

### Architecture & Technical Deep Dives

| # | Title | Pages | Focus |
|---|-------|-------|-------|
| 02 | Technical Architecture | 8 | Full platform architecture |
| 19 | hypersdk Architecture | 6 | Cloud export daemon (10 providers) |
| 20 | zkvm TUI Architecture | 6 | Interactive terminal UI |
| 31 | VMCraft Engine | 6 | Pure Python + qemu-nbd backend |
| 32 | Performance Optimization | 6 | I/O tuning, CPU pinning, NUMA |
| 33 | Storage Architecture | 6 | LVM, LUKS, Btrfs, ZFS, mdadm |
| 35 | Network Architecture | 6 | VirtIO-net, bridges, VLANs, SR-IOV |
| 45 | Monitoring & Observability | 6 | Structured logging, metrics |

### Migration Guides (Source Platform)

| # | Title | Pages | Source |
|---|-------|-------|-------|
| 03 | VMware Exit Guide | 8 | VMware vSphere |
| 21 | VMware Exit Strategy | 6 | VMware (updated) |
| 22 | Hyper-V Migration | 6 | Microsoft Hyper-V |
| 18 | Cloud Repatriation | 6 | AWS, Azure, GCP |
| 42 | Cloud-to-KVM Repatriation | 6 | Multi-cloud consolidation |

### Migration Guides (OS-Specific)

| # | Title | Pages | OS |
|---|-------|-------|---|
| 06 | Windows Migration | 8 | Windows Server/Desktop |
| 16 | Windows VM Migration (Complete) | 8 | All Windows versions, SQL Server |
| 17 | Linux VM Migration (Complete) | 8 | 15+ distros, all fixes |
| 53 | **Complete Win+Linux Migration** | **16** | **All features, both OS** |

### Feature Deep Dives

| # | Title | Pages | Feature |
|---|-------|-------|---------|
| 29 | KubeVirt Deployment | 6 | Kubernetes/KubeVirt target |
| 30 | Database Migration | 6 | SQL Server, PostgreSQL, MySQL |
| 34 | Air-Gap / Disconnected | 6 | Offline environments |
| 36 | Automation & CI/CD | 6 | Pipeline integration |
| 37 | Disaster Recovery | 6 | DR planning with KVM |
| 38 | Multi-Tenant Migration | 6 | Tenant isolation |
| 39 | GPU Passthrough | 6 | VFIO, VDI, ML workloads |
| 47 | Container-VM Convergence | 6 | KubeVirt + containers |
| 51 | VDI Migration | 6 | Virtual desktop infrastructure |
| 52 | Database Migration (Best Practices) | 6 | Advanced DB patterns |
| 54 | **Windows PNP Drivers & VirtIO** | **5** | **Offline driver injection, registry** |
| 55 | **Linux Guest Customization** | **4** | **Network inject, SSH, firstboot** |
| 56 | **Advanced Features** | **4** | **LUKS, LVM, AI, batch, daemon** |

### Security & Compliance

| # | Title | Pages | Focus |
|---|-------|-------|-------|
| 05 | Security & Compliance | 8 | Enterprise security |
| 23 | Security & Compliance (Updated) | 6 | FIPS, STIG, FedRAMP |
| 41 | Compliance & Audit Trail | 6 | Audit logging |

### Competitive Analysis

| # | Title | Pages | Compared To |
|---|-------|-------|-------------|
| 07 | Competitive Analysis | 8 | Overview |
| 13 | hyper2kvm vs virt-v2v | 6 | Red Hat virt-v2v |
| 14 | hyper2kvm vs MTV | 6 | Red Hat Migration Toolkit |

### Operations & Day 2

| # | Title | Pages | Focus |
|---|-------|-------|-------|
| 40 | Troubleshooting & Diagnostics | 6 | AI diagnostics, error patterns |
| 43 | Migration Testing & Validation | 6 | Boot test, health checks |
| 44 | Capacity Planning & Sizing | 6 | Resource estimation |
| 46 | Day 2 Operations | 6 | Post-migration ops |
| 49 | Training & Skills | 6 | Team enablement |

### Partner & Sales

| # | Title | Pages | Audience |
|---|-------|-------|----------|
| 09 | Case Studies | 6 | Customer success stories |
| 11 | Quickstart PoC | 4 | Pre-sales, solutions architects |
| 12 | Partner/MSP Deck | 6 | Channel partners |
| 25 | Case Studies (Updated) | 6 | Customer success stories |
| 27 | Partner MSP Revenue | 6 | MSP business model |
| 28 | Quickstart PoC (Updated) | 4 | Pre-sales |

### Edge & Specialized

| # | Title | Pages | Focus |
|---|-------|-------|-------|
| 04 | Edge & Cloud Migration | 6 | Edge computing |
| 15 | Edge Computing | 6 | K3s + KubeVirt at edge |

### Live Demos

| # | Title | Pages | Content |
|---|-------|-------|---------|
| 57 | **Migration Demo (Photon to KVM)** | **4** | **Live output, VM screenshot, network verify** |

### Templates

| Name | Purpose |
|------|---------|
| migration-readiness-assessment | Pre-migration checklist |
| rfp-response-template | RFP/RFI response |
| statement-of-work-template | SOW for migration projects |
| tco-calculator | TCO comparison spreadsheet |

## Generating PDFs

```bash
cd docs/client-presentations/
# Single presentation
google-chrome --headless --print-to-pdf=01-business-value.pdf \
  --print-to-pdf-no-header --no-margins 01-business-value.html

# All presentations
for f in *.html; do
  google-chrome --headless --print-to-pdf="${f%.html}.pdf" \
    --print-to-pdf-no-header --no-margins "$f"
done
```

## Color Themes

| Color | Topics |
|-------|--------|
| Blue (#0c4a6e) | Windows migration, architecture |
| Orange (#7c2d12) | Linux migration |
| Purple (#1e1b4b) | Advanced features, competitive |
| Teal (#065f46) | Demos, ROI, edge |
| Crimson (#7f1d1d) | VMware exit, security |
| Amber (#78350f) | Partner, business value |
| Green (#14532d) | Operations, day 2 |
| Cyan (#164e63) | Hyper-V, cloud |
| Indigo (#1e1b4b) | Compliance, audit |
