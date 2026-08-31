# H2KVM Documentation Hub

**Enterprise-Grade VM Migration from Any Hypervisor to KVM/Libvirt**

Welcome to the comprehensive documentation for H2KVM, a production-ready VM migration toolkit designed for seamless hypervisor transitions.

---

## 🔥 Latest Updates

### April 2026 - OVF Hardware Parsing & Multi-NIC/Disk Support
- ✅ **OVF Hardware Resource Parsing** - CPU, memory, NIC count, Secure Boot, OS type, CPU topology from DMTF CIM ResourceType
- ✅ **Multi-NIC Libvirt Domain XML** - OVF NIC count generates multiple `<interface>` elements
- ✅ **Multi-Disk Libvirt Domain XML** - Additional disks rendered as separate `<disk>` elements (vdb, vdc, ...)
- ✅ **Secure Boot for Linux Domains** - Auto-detected from OVF and guest EFI shim binaries; `.secboot.fd` OVMF resolution
- ✅ **VM Hardware Propagation** - govc export extracts memory/vCPUs/NICs from vSphere for domain emitter
- ✅ **Swap Size Detection** - Offline fixer reads swap partition sizes for memory estimation fallback
- ✅ **Secure Boot Shim Detection** - Scans guest EFI binaries (Fedora, RHEL, CentOS, Ubuntu, Debian, SUSE)

### March 2026 - Security & Robustness
- ✅ **70+ Bug Fixes** - Security, crashes, correctness across entire codebase
- ✅ **Windows VirtIO Driver Injection** - Cached ISO extraction with Rock Ridge support, all 4 drivers found
- ✅ **GuestKit disk backend** — offline inspect and repair via `hypersdk-guestkit` (replaces VMCraft)
- ✅ **Remote Deployment** - `deploy-remote.sh` — one command to fully set up any server
- ✅ **AWS EC2 Provider** - Production-grade EC2 → KVM with boto3, retry, resume, multi-disk, 51 tests
- ✅ **AMI to KVM Migration** - Download cloud images, convert, fix, deploy in one command
- ✅ **Split VMDK Fix** - No more false FATAL on twoGbMaxExtentSparse VMDKs
- ✅ **Command Injection Fixes** - Password handling, dracut args, SSH password exposure
- ✅ **noVNC Auto-Launch** - Browser console after VM deployment
- ✅ **User Injection** - Password, groups, home dir, fstab partition mounting
- ✅ **K8s Deployer** - CDI auto-detect, qcow2→raw conversion, kubeconfig auto-detect
- ✅ **Cross-Distro Fixes** - QEMU binary auto-detect, SPICE/VNC auto-detect, netplan fixer
- ✅ **LUKS Improvements** - Skip initramfs rebuild for LUKS, fix false detection
- ✅ **61 Client Presentations** - Including new AMI to KVM migration deck

### February 2026 - Enterprise Features
- ✅ **Multi-Stage VirtIO Boot Deployment** - Automated VMware → KVM Windows migration
- ✅ **KubeVirt Deployment** - Complete pipeline for deploying VMs to Kubernetes
- ✅ **OpenStack Glance Deploy** - Upload converted QCOW2 to Glance (`--deploy-openstack`) with optional Nova boot
- ✅ **Enterprise LVM Safety** - 0.71s activation, 100% host protection
- ✅ **Systemd Integration** - 20+ systemd tools for enhanced workflows

📖 **[Complete Architecture Summary](architecture/ARCHITECTURE_SUMMARY.md)**

---

## 📚 Documentation Structure

### 🚀 Getting Started
**New to h2kvm? Start here!**

| Document | Description |
|----------|-------------|
| [Installation Guide](getting-started/01-Installation.md) | Install in 5 minutes |
| [Quick Start](getting-started/02-Quick-Start.md) | First migration in 10 minutes |
| [Getting Started Guide](getting-started/03-Getting-Started.md) | Comprehensive introduction |
| [Quickstart Tutorial](getting-started/QUICKSTART.md) | Fast-track tutorial |

### 📖 Tutorials
**Step-by-step learning paths**

| Level | Document | What You'll Learn |
|-------|----------|-------------------|
| **Beginner** | [First Migration](tutorials/01-beginner-migration.md) | Basic VMDK to QCOW2 conversion |
| **Intermediate** | [Workflows & Batch](tutorials/02-intermediate-workflows.md) | Batch migrations and automation |
| **Advanced** | [Advanced Features](tutorials/03-advanced-features.md) | Live migration, DR testing |
| **Enterprise** | [Production Deployment](tutorials/04-enterprise-deployment.md) | Large-scale deployments |
| **Cookbook** | [Tutorial Collection](tutorials/TUTORIALS.md) | All tutorials index |

### 🍳 Recipes & Examples
**Real-world migration patterns**

| Document | Use Cases |
|----------|-----------|
| [Common Scenarios](recipes/01-common-scenarios.md) | Frequently encountered patterns |
| [Migration Cookbook](guides/cookbook.md) | Quick recipes for common tasks |
| [Examples Library](guides/operations/EXAMPLES_LIBRARY.md) | 23+ configuration examples |

### 📋 User Guides
**Comprehensive operation guides**

#### CLI & Configuration
- [CLI Reference](guides/cli/reference.md) - Complete command-line reference
- [h2kvmctl Guide](guides/cli/h2kvmctl-guide.md) - Worker job control CLI
- [YAML Examples](guides/cli/yaml-examples.md) - Configuration file examples
- [YAML vs Manifests](guides/yaml-vs-manifests.md) - Format comparison

#### Migration Guides
- [AMI & Cloud Image Migration](guides/migration/ami-cloud-repatriation.md) - AWS, Azure, GCP cloud repatriation
- [Batch Migration Guide](guides/migration/batch-features.md) - Multiple VMs at once
- [Migration Playbooks](guides/migration/playbooks.md) - Step-by-step workflows
- [Quick Reference](guides/migration/quick-reference.md) - Essential commands
- [Batch Quick Reference](guides/migration/batch-quick-reference.md) - Batch shortcuts

#### Platform-Specific Guides
- [Windows Migration](guides/windows-migration-guide.md) - Windows VM migration
- [Windows VirtIO Troubleshooting](guides/troubleshooting-windows-virtio.md) - Driver discovery, ISO extraction, registry
- [Windows VirtIO Driver Injection](os-support/windows/driver-injection.md) - Offline driver injection + staged boot
- [Windows Boot Guide](os-support/windows/guide.md) - SATA → VirtIO boot validation
- [Windows Best Practices](guides/windows-best-practices.md) - Windows optimization
- [Windows Troubleshooting](guides/windows-troubleshooting-runbook.md) - Windows issues
- [Cloud-Native Distros](guides/cloud-native-distros.md) - Modern Linux distros
- [HyperSDK Quickstart](guides/hypersdk-quickstart.md) - SDK integration

#### Operational Guides
- [Operations Hub](guides/operations/) - All operational guides
- [Migration Checklist](guides/operations/MIGRATION_CHECKLIST.md) - Complete checklists
- [Pre-Flight Validation](guides/operations/PRE_FLIGHT_VALIDATION.md) - Readiness verification
- [Migration Runbook](guides/operations/MIGRATION_RUNBOOK_TEMPLATE.md) - Customizable template
- [Best Practices](guides/operations/BEST_PRACTICES.md) - Proven practices
- [Automation Scripts](guides/operations/AUTOMATION_SCRIPTS.md) - Ready-to-use scripts
- [Monitoring Guide](guides/operations/MONITORING_GUIDE.md) - Observability

#### Security & Configuration
- [Security Best Practices](guides/security-best-practices.md) - Secure workflows
- [Conversion Directory](guides/configuration/conversion-directory.md) - Temp directory config
- [Enhanced Features](guides/enhanced-features.md) - Advanced capabilities
- [Troubleshooting](guides/troubleshooting.md) - Diagnose and fix issues

#### TUI (Terminal UI)
- See [zkvm/README.md](../zkvm/README.md) - Interactive terminal UI guide

#### Decision Support
- [Decision Support Hub](guides/decision-support/) - All decision tools
- [Migration Decision Tree](guides/decision-support/MIGRATION_DECISION_TREE.md) - Choose approach
- [Comparison Matrix](guides/decision-support/COMPARISON_MATRIX.md) - Compare options
- [Troubleshooting Flowchart](guides/decision-support/TROUBLESHOOTING_FLOWCHART.md) - Diagnose issues

### 🏗️ Architecture & Internals
**Understanding how h2kvm works**

| Component | Documentation |
|-----------|---------------|
| **Overview** | [Architecture Summary](architecture/ARCHITECTURE_SUMMARY.md) |
| **Backends** | [Backend Comparison](architecture/BACKENDS.md) |
| **GuestKit** | [GuestKit Integration](architecture/GUESTKIT.md) |
| **LVM** | [LVM Backends](architecture/LVM_BACKENDS.md) |
| **Reference** | [Full Architecture](reference/architecture.md) |

### 🎯 Features & Capabilities
**Deep dives into specific features**

| Feature | Documentation |
|---------|---------------|
| **GuestKit** | [GuestKit Integration](architecture/GUESTKIT.md) |
| **Live Migration** | [Live Migration](features/LIVE_MIGRATION.md) |
| **LVM Safety** | [Enterprise LVM](features/LVM_AND_ENTERPRISE_IMPROVEMENTS.md) |
| **Systemd Integration** | [Systemd Tools](features/SYSTEMD_INTEGRATION_SUMMARY.md) |
| **Systemd Boot** | [Boot Integration](features/SYSTEMD_BOOT_INTEGRATION.md) |
| **Systemd Firstboot** | [Firstboot Integration](features/SYSTEMD_FIRSTBOOT_INTEGRATION.md) |
| **VMDK Inspector** | [VMDK Validation](features/vmdk-inspector.md) |
| **BusLogic Fix** | [Auto-Fix Guide](features/buslogic-auto-fix.md) |
| **fstab Stabilization** | [fstab Guide](features/fstab-stabilization.md) |
| **XFS UUID** | [UUID Regeneration](features/xfs-uuid-regeneration.md) |
| **Daemon Mode** | [Daemon Architecture](features/daemon-architecture.md) |
| **Cloud Integration** | [Configuration Injection](features/configuration-injection.md) |
| **vSphere** | [vSphere Export](features/vsphere-export.md) |
| **Windows Firstboot** | [Windows Integration](features/WINDOWS_FIRSTBOOT_INTEGRATION.md) |
| **Enhanced Chroot** | [Chroot Safety](features/enhanced-chroot.md) |
| **systemd-vmspawn** | [VMSPAWN Guide](features/SYSTEMD_VMSPAWN_GUIDE.md) |
| **VMSPAWN Internals** | [VMSPAWN Internals](features/SYSTEMD_VMSPAWN_INTERNALS.md) |
| **VMSPAWN SDK** | [SDK README](features/VMSPAWN_SDK_README.md) |
| **Systemd Comparison** | [Tool Comparison](features/SYSTEMD_COMPARISON.md) |
| **Systemd Quick Ref** | [Quick Reference](features/SYSTEMD_QUICK_REFERENCE.md) |

### 🚢 Deployment
**Production deployment strategies**

| Platform | Documentation |
|----------|---------------|
| **Kubernetes** | [K8s Integration](deployment/KUBERNETES_INTEGRATION.md) |
| **KubeVirt** | [KubeVirt Deployment](deployment/KUBEVIRT-DEPLOYMENT.md) |
| **OpenStack** | [Glance upload after migration](guides/openstack-deployment.md) |
| **OpenShift** | [OCP Deployment](deployment/openshift-deployment-guide.md) |
| **Containers** | [Container Guide](deployment/container-deployment-guide.md) |
| **Production** | [Production Guide](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md) |
| **Helm** | [Helm Repository](deployment/helm-repository.md) |
| **Quick Ref** | [Deployment Quick Ref](deployment/DEPLOYMENT_QUICKREF.md) |
| **k3d Testing** | [k3d Test Report](deployment/k3d-test-report.md) |
| **Container Testing** | [Container Test Report](deployment/container-test-report.md) |
| **Worker Protocol** | [Protocol Summary](deployment/WORKER_PROTOCOL_SUMMARY.md) |
| **REST API** | [REST API Complete](deployment/PHASE6_REST_API_COMPLETE.md) |

### 📚 API Reference
**Complete API documentation**

| API | Documentation |
|-----|---------------|
| **GuestKit** | [GuestKit Integration](../architecture/GUESTKIT.md) |
| **API Reference** | [API Reference](reference/API_REFERENCE.md) |
| **Library API** | [Library Usage](reference/api/library-api.md) |
| **Quick Reference** | [API Quick Ref](reference/api/quick-reference.md) |
| **Rollback API** | [Rollback Operations](api/rollback-api.md) |
| **Validation API** | [Validation Suite](api/validation-api.md) |

### 📋 Reference Documentation
**Technical references and schemas**

| Document | Description |
|----------|-------------|
| [Installation](reference/INSTALLATION.md) | Installation reference |
| [Dependencies](reference/dependencies.md) | Required dependencies |
| [Optional Dependencies](reference/optional-dependencies.md) | Optional components |
| [Failure Modes](reference/failure-modes.md) | Error handling |
| [Network Resilience](reference/network-resilience.md) | Network reliability |
| [Manifest Workflow](reference/manifest-workflow.md) | Manifest processing |
| [Integration Contract](reference/Integration-Contract.md) | API contracts |
| [Hyperctl Integration](reference/HYPERCTL_INTEGRATION.md) | Hyperctl integration |
| [Windows Schema](reference/windows-configuration-schema.md) | Windows config |
| [Windows AppCompat](reference/windows-appcompat-schema.md) | App compatibility |
| [Windows Performance](reference/windows-performance-schema.md) | Performance tuning |
| [Upgrade Guide](reference/UPGRADE_GUIDE.md) | Version upgrades |

### ⚡ Quick Reference
**Fast access to essential information**

| Resource | Description |
|----------|-------------|
| [Quick Reference Card](quick-reference/QUICK_REFERENCE.md) | One-page printable reference |
| [Navigation Map](quick-reference/NAVIGATION_MAP.md) | Documentation navigation |
| [Glossary](quick-reference/GLOSSARY.md) | 150+ terms defined |
| [FAQ](quick-reference/FAQ.md) | 25+ common questions |

### 🧪 Testing
**Quality assurance and testing**

| Document | Description |
|----------|-------------|
| [E2E Testing](testing/E2E_TESTING.md) | End-to-end tests |
| [Testing Guide](development/testing-guide.md) | Testing strategies |
| [Test Migration](testing/TEST_MIGRATION.md) | Migration testing |
| [CentOS 8 Plan](testing/CENTOS8_TEST_PLAN.md) | CentOS test plan |

### 📊 Test Results
**Validation and test reports**

| Test | Results |
|------|---------|
| [LVM Enterprise Tests](test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md) | LVM validation |
| [Final Test Results](test-results/FINAL_TEST_RESULTS.md) | Complete suite |
| [Migration Summary](test-results/MIGRATION_TEST_SUMMARY.md) | Migration tests |
| [CentOS 8](test-results/centos8-migration-success.md) | CentOS 8.x |
| [CentOS 9](test-results/centos9-migration-success.md) | CentOS 9.x |
| [OpenShift Tests](test-results/OPENSHIFT_TEST_SUMMARY.md) | OCP testing |
| [Local Tests](test-results/LOCAL_TEST_REPORT.md) | Local validation |

### 💻 Development
**Contributing and development guides**

| Document | Purpose |
|----------|---------|
| [Developer Guide](development/DEVELOPER_GUIDE.md) | Development setup |
| [Contributing](development/contributing.md) | Contribution guidelines |
| [Coding Style](development/CODING_STYLE.md) | Code conventions |
| [Hacking](development/HACKING.md) | Development tips |
| [Building](development/building.md) | Build instructions |
| [Publishing](development/publishing.md) | Release process |
| [Testing Guide](development/testing-guide.md) | Test development |
| [Architecture](development/architecture.md) | Design patterns |
| [Guardrails](development/architecture-guardrails.md) | Design principles |
| [Exception Handling](development/EXCEPTION_HANDLING_IMPROVEMENTS.md) | Error handling |
| [Code Metrics](development/CODE_METRICS.md) | Quality metrics |
| [Refactoring Summary](development/REFACTORING_SESSION_SUMMARY.md) | Refactoring notes |
| [Exception Review](development/EXCEPTION_HANDLING_REVIEW.md) | Error review |
| [TUI (zkvm)](../zkvm/README.md) | TUI development and architecture |
| [Feature Suggestions](development/feature-suggestions.md) | New features |

### 🔧 Operator & CRDs
**Kubernetes Operator resources**

| Document | Description |
|----------|-------------|
| [Getting Started](operator/getting-started.md) | Operator setup |
| [HyperConversion CRD](operator/hyperconversion-crd.md) | Custom resource |
| [Migration Complete](operator/OPERATOR_MIGRATION_COMPLETE.md) | Migration status |

### 🌍 OS Support
**Operating system compatibility**

| OS | Documentation |
|----|---------------|
| [RHEL 10](os-support/rhel-10.md) | Red Hat Enterprise Linux 10 |
| [Ubuntu 24.04](os-support/ubuntu-2404.md) | Ubuntu LTS |
| [SUSE](os-support/suse.md) | SUSE Linux Enterprise |
| [Photon OS](os-support/photon-os.md) | VMware Photon OS |
| [Windows](os-support/windows/) | Windows compatibility |

### 📊 Performance
**Performance benchmarks and optimization**

| Document | Description |
|----------|-------------|
| [Benchmarks](performance/BENCHMARKS.md) | Performance data |

### 📈 Project Information
**Project status and roadmap**

| Document | Description |
|----------|-------------|
| [Project Status](project/PROJECT_STATUS.md) | Current state |
| [Implementation Status](project/IMPLEMENTATION_STATUS.md) | Feature status |
| [Ecosystem](project/ECOSYSTEM.md) | Integration ecosystem |
| [Priority 1 Features](project/Priority-1-Features.md) | High-priority items |
| [Roadmap](roadmap/) | Future plans |

### 🚀 Presentations
**Pitch decks and comparisons**

| Document | Description |
|----------|-------------|
| [Pipeline Architecture](presentation/pipeline-architecture.md) | Architecture overview |
| [Daemon vs CLI](presentation/daemon-vs-cli-workflow.md) | Workflow comparison |
| [Quick Comparison](presentation/quick-comparison.md) | Feature comparison |

### 📢 Marketing
**Public-facing content**

| Document | Description |
|----------|-------------|
| [LinkedIn Article](marketing/h2kvm-linkedin-article.md) | Long-form article |
| [LinkedIn Short Post](marketing/h2kvm-linkedin-short-post.md) | Social post |
| [LinkedIn Carousel](marketing/h2kvm-linkedin-carousel-slides.md) | Visual slides |
| [Content Guide](marketing/linkedin-content-guide.md) | Content strategy |

### 📝 Documentation Meta
**Documentation maintenance**

| Document | Description |
|----------|-------------|
| [Contributing Docs](meta/CONTRIBUTING_DOCS.md) | Doc contribution guide |
| [Documentation Changelog](meta/DOCUMENTATION_CHANGELOG.md) | Doc changes |
| [Dependency Map](meta/dependency-map.md) | Documentation dependencies |

---

## 🔍 Finding Documentation

### By Task
- **First-time user?** → [Quick Start](getting-started/02-Quick-Start.md)
- **Planning migration?** → [Decision Tree](guides/decision-support/MIGRATION_DECISION_TREE.md)
- **Need API docs?** → [GuestKit Integration](architecture/GUESTKIT.md)
- **Troubleshooting?** → [Troubleshooting Guide](guides/troubleshooting.md)
- **Production deployment?** → [Production Guide](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)

### By Platform
- **Kubernetes/OpenShift** → [Deployment](deployment/)
- **Windows VMs** → [Windows Guide](guides/windows-migration-guide.md)
- **VMware ESXi** → [vSphere Export](features/vsphere-export.md)
- **Cloud (AWS/Azure)** → [Cloud-Native Guide](guides/cloud-native-distros.md)

### By Component
- **GuestKit** → [Architecture](architecture/GUESTKIT.md)
- **CLI Tools** → [Guides/CLI](guides/cli/)
- **TUI Dashboard** → [Guides/TUI](guides/tui/)
- **Worker System** → [Worker Protocol](worker/)

---

## 📖 Documentation Conventions

### File Organization
- **getting-started/** - New user onboarding
- **tutorials/** - Learning paths
- **guides/** - Task-oriented how-tos
- **reference/** - Technical specifications
- **features/** - Feature deep-dives
- **architecture/** - System design
- **deployment/** - Production deployments
- **development/** - Contributor guides

### Reading Order
1. Start with [Quick Start](getting-started/02-Quick-Start.md)
2. Follow [Beginner Tutorial](tutorials/01-beginner-migration.md)
3. Explore [User Guides](guides/)
4. Deep dive into [Features](features/)
5. Study [Architecture](architecture/) for advanced understanding

---

## 🤝 Contributing

- **Found an issue?** → [Contributing Guide](development/contributing.md)
- **Want to add docs?** → [Documentation Guide](meta/CONTRIBUTING_DOCS.md)
- **Code contributions?** → [Developer Guide](development/DEVELOPER_GUIDE.md)

---

## 📚 External Resources

- **GitHub Repository**: https://github.com/ssahani/h2kvm
- **PyPI Package**: https://pypi.org/project/h2kvm/
- **Issue Tracker**: https://github.com/ssahani/h2kvm/issues

---

<div align="center">

**Need help? Check the [FAQ](quick-reference/FAQ.md) or [Troubleshooting Guide](guides/troubleshooting.md)**

*Last updated: March 2026*

</div>
