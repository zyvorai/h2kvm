# Documentation Navigation Map

Visual guide to navigating H2KVM documentation.

---

## Quick Navigation by User Type

### 🆕 New Users (Never used H2KVM)

**Start Here** → **Learn Basics** → **Practice**

```
1. Installation (5 min)
   ├─→ [Installation Guide](getting-started/01-Installation.md)
   └─→ [Quick Reference](QUICK_REFERENCE.md) - Keep open!

2. First Migration (10 min)
   ├─→ [Quick Start](getting-started/02-Quick-Start.md)
   └─→ [Beginner Tutorial](tutorials/01-beginner-migration.md)

3. Understanding (30 min)
   ├─→ [Getting Started Guide](getting-started/03-Getting-Started.md)
   ├─→ [FAQ](FAQ.md) - Common questions
   └─→ [Glossary](GLOSSARY.md) - Learn terms

4. Practice (1-2 hours)
   └─→ [Common Recipes](recipes/01-common-scenarios.md)
```

---

### 💼 Intermediate Users (Basic experience)

**Expand Skills** → **Batch Operations** → **Automation**

```
1. Advanced Workflows (2-4 hours)
   ├─→ [Intermediate Tutorial](tutorials/02-intermediate-workflows.md)
   ├─→ [Batch Migration Guide](guides/migration/batch-features.md)
   └─→ [Migration Playbooks](guides/migration/playbooks.md)

2. OS-Specific Skills
   ├─→ [Windows Migration](os-support/windows/guide.md)
   ├─→ [RHEL/CentOS](os-support/rhel-10.md)
   └─→ [Ubuntu](os-support/ubuntu-2404.md)

3. Troubleshooting
   ├─→ [Troubleshooting Guide](guides/troubleshooting.md)
   ├─→ [FAQ](FAQ.md)
   └─→ [Known Issues](reference/failure-modes.md)

4. Features Deep Dive
   ├─→ [Features Hub](features/)
   ├─→ [GuestKit Guide](features/architecture/GUESTKIT.md)
   └─→ [VMDK Inspector](features/vmdk-inspector.md)
```

---

### 🚀 Advanced Users (Production deployments)

**Enterprise Features** → **Architecture** → **Optimization**

```
1. Enterprise Deployment (8+ hours)
   ├─→ [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
   ├─→ [Production Deployment](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)
   └─→ [Security Best Practices](guides/security-best-practices.md)

2. Platform Integration
   ├─→ [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)
   ├─→ [OpenShift Guide](deployment/openshift-deployment-guide.md)
   └─→ [Container Deployment](deployment/container-deployment-guide.md)

3. Advanced Features
   ├─→ [Advanced Tutorial](tutorials/03-advanced-features.md)
   ├─→ [GuestKit Advanced](features/architecture/GUESTKIT.md)
   └─→ [Worker Protocol](worker/PROTOCOL_SPEC.md)

4. Architecture Understanding
   ├─→ [Architecture](reference/architecture.md)
   ├─→ [Integration Contract](reference/Integration-Contract.md)
   └─→ [Network Resilience](reference/network-resilience.md)
```

---

### 👨‍💻 Developers (Integrating/Contributing)

**API Reference** → **Development** → **Testing**

```
1. API Documentation
   ├─→ [API Reference](reference/api/API-Reference.md)
   ├─→ [GuestKit API](architecture/GUESTKIT.md) - 480+ methods
   ├─→ [Library API](reference/api/library-api.md)
   └─→ [REST API](worker/REST_API.md)

2. Development Setup
   ├─→ [Building from Source](development/building.md)
   ├─→ [Contributing Guide](development/contributing.md)
   ├─→ [Contributing to Docs](CONTRIBUTING_DOCS.md)
   └─→ [Testing Guide](development/testing-guide.md)

3. Architecture Deep Dive
   ├─→ [Architecture](reference/architecture.md)
   ├─→ [Daemon Architecture](features/daemon-architecture.md)
   └─→ [TUI Implementation](development/tui-implementation.md)

4. Integration
   ├─→ [Integration Contract](reference/Integration-Contract.md)
   ├─→ [HyperCtl Integration](reference/HYPERCTL_INTEGRATION.md)
   └─→ [Manifest Workflow](reference/manifest-workflow.md)
```

---

### 🔧 Operators (Running in production)

**Deployment** → **Monitoring** → **Maintenance**

```
1. Deployment Options
   ├─→ [Deployment Hub](deployment/)
   ├─→ [Production Deployment](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)
   ├─→ [OpenShift Quickstart](deployment/openshift/OPENSHIFT_QUICKSTART.md)
   └─→ [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)

2. Operations
   ├─→ [Daemon User Guide](features/daemon-user-guide.md)
   ├─→ [Worker Protocol](worker/)
   └─→ [h2kvmctl Guide](guides/cli/h2kvmctl-guide.md)

3. Monitoring & Troubleshooting
   ├─→ [Test Results](test-results/)
   ├─→ [Troubleshooting Guide](guides/troubleshooting.md)
   └─→ [Failure Modes](reference/failure-modes.md)

4. Security
   ├─→ [Security Best Practices](guides/security-best-practices.md)
   └─→ [SECURITY.md](../SECURITY.md)
```

---

## Navigation by Task

### "I want to migrate my first VM"

```
Quick Path (30 minutes):
└─→ [Quick Start](getting-started/02-Quick-Start.md)
    └─→ [Common Recipes](recipes/01-common-scenarios.md)
        └─→ Pick OS-specific recipe

Detailed Path (2 hours):
└─→ [Installation](getting-started/01-Installation.md)
    └─→ [Getting Started Guide](getting-started/03-Getting-Started.md)
        └─→ [Beginner Tutorial](tutorials/01-beginner-migration.md)
            └─→ [First migration complete!]
```

---

### "I need to migrate 100+ VMs"

```
Batch Migration Path:
└─→ [Intermediate Tutorial](tutorials/02-intermediate-workflows.md)
    └─→ [Batch Migration Guide](guides/migration/batch-features.md)
        └─→ [Migration Playbooks](guides/migration/playbooks.md)
            └─→ [Daemon User Guide](features/daemon-user-guide.md)

Enterprise Path:
└─→ [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
    └─→ [Deployment Hub](deployment/)
        └─→ [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md) or
            [OpenShift Guide](deployment/openshift-deployment-guide.md)
```

---

### "I'm getting an error"

```
Troubleshooting Path:
└─→ [Quick Reference](QUICK_REFERENCE.md) - Check common errors
    └─→ [FAQ](FAQ.md) - Search for your error
        └─→ [Troubleshooting Guide](guides/troubleshooting.md)
            └─→ [Failure Modes](reference/failure-modes.md)
                └─→ Still stuck? [GitHub Issues](https://github.com/ssahani/h2kvm/issues)
```

---

### "I want to understand how it works"

```
Architecture Path:
└─→ [Glossary](GLOSSARY.md) - Learn terminology first
    └─→ [Architecture](reference/architecture.md)
        └─→ [GuestKit integration guide](features/architecture/GUESTKIT.md)
            └─→ [Features Hub](features/)
                └─→ [API Reference](reference/api/API-Reference.md)
```

---

### "I want to deploy to Kubernetes/OpenShift"

```
Kubernetes Path:
└─→ [Deployment Hub](deployment/)
    └─→ [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)
        └─→ [Worker Protocol](worker/)
            └─→ [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)

OpenShift Path:
└─→ [OpenShift Quickstart](deployment/openshift/OPENSHIFT_QUICKSTART.md)
    └─→ [OpenShift Guide](deployment/openshift-deployment-guide.md)
        └─→ [Test Results](test-results/OPENSHIFT_TEST_SUMMARY.md)
```

---

### "I want to migrate Windows VMs"

```
Windows Migration Path:
└─→ [Windows Guide](os-support/windows/guide.md)
    └─→ [Windows Driver Injection](os-support/windows/driver-injection.md)
        └─→ [Windows Networking](os-support/windows/networking.md)
            └─→ [Windows Troubleshooting](os-support/windows/troubleshooting.md)
```

---

### "I need API documentation"

```
API Documentation Path:
└─→ [Quick Reference](reference/api/quick-reference.md) - Start here
    └─→ [Library API](reference/api/library-api.md) - Python usage
        └─→ [API Reference](reference/api/API-Reference.md) - Complete reference
            └─→ [GuestKit API](architecture/GUESTKIT.md) - 480+ methods
```

---

## Navigation by Topic

### Migration Workflows

```
migration/
├── Basics
│   ├─→ [Quick Start](getting-started/02-Quick-Start.md)
│   ├─→ [Beginner Tutorial](tutorials/01-beginner-migration.md)
│   └─→ [Common Recipes](recipes/01-common-scenarios.md)
│
├── Batch Operations
│   ├─→ [Batch Migration Guide](guides/migration/batch-features.md)
│   ├─→ [Intermediate Tutorial](tutorials/02-intermediate-workflows.md)
│   └─→ [Migration Playbooks](guides/migration/playbooks.md)
│
├── Advanced
│   ├─→ [Advanced Tutorial](tutorials/03-advanced-features.md)
│   └─→ [Live Migration](guides/migration/playbooks.md#live-fix)
│
└── Enterprise
    ├─→ [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
    └─→ [Production Deployment](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)
```

---

### Features & Capabilities

```
features/
├── Core Features
│   ├─→ [GuestKit engine](features/architecture/GUESTKIT.md)
│   ├─→ [fstab Stabilization](features/fstab-stabilization.md)
│   ├─→ [Enhanced Chroot](features/enhanced-chroot.md)
│   └─→ [XFS UUID Regeneration](features/xfs-uuid-regeneration.md)
│
├── Inspection & Validation
│   ├─→ [VMDK Inspector](features/vmdk-inspector.md)
│   ├─→ [VMDK Validation](features/vmdk-validation.md)
│   └─→ [BusLogic Auto-Fix](features/buslogic-auto-fix.md)
│
├── Automation
│   ├─→ [Daemon Mode](features/daemon-mode.md)
│   ├─→ [Daemon Architecture](features/daemon-architecture.md)
│   └─→ [Systemd Integration](features/systemd-integration.md)
│
└── GuestKit Advanced
    ├─→ [Advanced Features](features/architecture/GUESTKIT.md)
    ├─→ [OS Detection](features/architecture/GUESTKIT.md)
    ├─→ [Windows Support](features/os-support/windows/README.md)
    ├─→ [Augeas Guide](features/architecture/GUESTKIT.md)
    ├─→ [LVM Guide](features/architecture/LVM_BACKENDS.md)
    └─→ [Performance Guide](features/architecture/GUESTKIT.md)
```

---

### Operating Systems

```
os-support/
├── Linux
│   ├─→ [RHEL/CentOS/Rocky](os-support/rhel-10.md)
│   ├─→ [Ubuntu/Debian](os-support/ubuntu-2404.md)
│   ├─→ [SUSE/openSUSE](os-support/suse.md)
│   └─→ [Photon OS](os-support/photon-os.md)
│
└── Windows
    ├─→ [Windows Guide](os-support/windows/guide.md)
    ├─→ [Boot Cycle](os-support/windows/boot-cycle.md)
    ├─→ [Networking](os-support/windows/networking.md)
    ├─→ [Driver Injection](os-support/windows/driver-injection.md)
    └─→ [Troubleshooting](os-support/windows/troubleshooting.md)
```

---

### Deployment Options

```
deployment/
├── Container Platforms
│   ├─→ [Container Deployment](deployment/container-deployment-guide.md)
│   └─→ [Docker/Podman Usage](deployment/)
│
├── Kubernetes
│   ├─→ [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)
│   ├─→ [KubeVirt Integration](deployment/KUBEVIRT_INTEGRATION.md)
│   └─→ [Operator Guide](deployment/v1.4.0-operator.md)
│
├── OpenShift
│   ├─→ [OpenShift Quickstart](deployment/openshift/OPENSHIFT_QUICKSTART.md)
│   ├─→ [OpenShift Guide](deployment/openshift-deployment-guide.md)
│   └─→ [OpenShift Features](deployment/OPENSHIFT_FEATURES_SUMMARY.md)
│
└── Production
    ├─→ [Production Deployment](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)
    └─→ [Deployment Quickref](deployment/DEPLOYMENT_QUICKREF.md)
```

---

## Documentation Structure

### Directory Hierarchy

```
docs/
│
├── 📄 Core Documents (Always Start Here)
│   ├── index.md ............................ Main hub
│   ├── QUICK_REFERENCE.md .................. 1-page reference
│   ├── GLOSSARY.md ......................... All terms
│   ├── FAQ.md .............................. 25+ Q&A
│   ├── CONTRIBUTING_DOCS.md ................ Doc contribution
│   ├── DOCUMENTATION_CHANGELOG.md .......... Track changes
│   └── NAVIGATION_MAP.md ................... This file
│
├── 🚀 getting-started/ ..................... New users
│   ├── README.md ........................... Hub
│   ├── 01-Installation.md .................. Install (5 min)
│   ├── 02-Quick-Start.md ................... First migration (10 min)
│   └── 03-Getting-Started.md ............... Complete intro
│
├── 🎓 tutorials/ ........................... Step-by-step learning
│   ├── README.md ........................... Hub
│   ├── 01-beginner-migration.md ............ 0-2 hours
│   ├── 02-intermediate-workflows.md ........ 2-8 hours
│   ├── 03-advanced-features.md ............. 8+ hours
│   └── 04-enterprise-deployment.md ......... Enterprise
│
├── 🍳 recipes/ ............................. Quick solutions
│   ├── README.md ........................... Hub
│   └── 01-common-scenarios.md .............. 10 recipes
│
├── 🛠️ guides/ ............................. Task guides
│   ├── README.md ........................... Hub
│   ├── cli/ ................................ CLI reference
│   ├── migration/ .......................... Migration workflows
│   ├── tui/ ................................ Terminal UI
│   ├── configuration/ ...................... Config guides
│   ├── cookbook.md ......................... Quick recipes
│   ├── security-best-practices.md .......... Security
│   ├── troubleshooting.md .................. Fix issues
│   └── [more guides]
│
├── 🔧 features/ ............................ Features
│   ├── README.md ........................... Hub
│   ├── guestkit/ ............................ GuestKit engine
│   ├── vmdk-inspector.md ................... VMDK analysis
│   ├── xfs-uuid-regeneration.md ............ UUID fixes
│   ├── fstab-stabilization.md .............. fstab repair
│   └── [20+ feature docs]
│
├── 🖥️ os-support/ .......................... OS-specific
│   ├── README.md ........................... Hub
│   ├── windows/ ............................ Windows guides
│   ├── rhel-10.md .......................... RHEL/CentOS
│   ├── ubuntu-2404.md ...................... Ubuntu
│   └── [more OS guides]
│
├── 🚢 deployment/ .......................... Deployment
│   ├── README.md ........................... Hub
│   ├── openshift/ .......................... OpenShift
│   ├── releases/ ........................... Release notes
│   └── [25+ deployment docs]
│
├── 🔄 worker/ .............................. Worker protocol
│   ├── README.md ........................... Hub
│   ├── QUICKSTART.md ....................... Quick start
│   ├── PROTOCOL_SPEC.md .................... Specification
│   └── REST_API.md ......................... REST API
│
├── 🔬 test-results/ ........................ Test results
│   ├── README.md ........................... Hub
│   └── [9 test reports]
│
├── 📚 reference/ ........................... Technical ref
│   ├── README.md ........................... Hub
│   ├── api/ ................................ API docs
│   ├── architecture.md ..................... Architecture
│   ├── dependencies.md ..................... Dependencies
│   └── [15+ reference docs]
│
└── 👥 development/ ......................... Development
    ├── README.md ........................... Hub
    ├── contributing.md ..................... Contribute
    ├── building.md ......................... Build from source
    └── [10+ dev docs]
```

---

## Cross-Reference Map

### Key Documents and Their Related Links

#### Quick Reference Card
**Links to**:
- Installation Guide
- Tutorials
- Recipes
- Troubleshooting
- FAQ

#### FAQ
**Links to**:
- All major features
- Troubleshooting guide
- OS-specific guides
- Quick Reference
- Glossary

#### Glossary
**Links to**:
- Tutorials (for learning)
- Features (for definitions)
- Reference (for technical details)

#### Getting Started
**Links to**:
- Tutorials (next steps)
- Recipes (quick examples)
- FAQ (common questions)
- Troubleshooting

#### Tutorials
**Link to each other** (progression):
Beginner → Intermediate → Advanced → Enterprise

**Also link to**:
- Recipes (quick reference)
- Guides (detailed how-to)
- Features (in-depth)

#### Features
**Link to**:
- API Reference (technical details)
- Guides (how to use)
- Tutorials (learning path)

---

## Search Strategy

### Finding Information Fast

**1. Know what you want?**
- Use [Quick Reference](QUICK_REFERENCE.md)

**2. Have a specific question?**
- Check [FAQ](FAQ.md)

**3. Don't know a term?**
- Look it up in [Glossary](GLOSSARY.md)

**4. Want to learn?**
- Start with [Tutorials](tutorials/)

**5. Need to do something specific?**
- Try [Recipes](recipes/) or [Guides](guides/)

**6. Getting an error?**
- See [Troubleshooting](guides/troubleshooting.md)

**7. Want technical details?**
- Check [Reference](reference/) or [API Docs](reference/api/)

---

## Documentation Workflow

### Recommended Reading Order

#### For Learning (New Users):
```
1. QUICK_REFERENCE.md (skim, keep open)
2. getting-started/01-Installation.md (5 min)
3. getting-started/02-Quick-Start.md (10 min)
4. tutorials/01-beginner-migration.md (2 hours)
5. recipes/ (as needed)
6. FAQ.md (reference)
7. GLOSSARY.md (reference)
```

#### For Production Deployment:
```
1. tutorials/04-enterprise-deployment.md
2. deployment/PRODUCTION_DEPLOYMENT_GUIDE.md
3. deployment/KUBERNETES_INTEGRATION.md or openshift-deployment-guide.md
4. guides/security-best-practices.md
5. features/ (relevant features)
6. test-results/ (validation)
```

#### For Development:
```
1. GLOSSARY.md (learn terminology)
2. reference/architecture.md
3. reference/api/API-Reference.md
4. development/contributing.md
5. development/building.md
6. development/testing-guide.md
```

---

## Tips for Navigation

### Best Practices

✅ **DO**:
- Start with Quick Reference for commands
- Use FAQ for quick answers
- Check Glossary for unfamiliar terms
- Follow tutorial progression (beginner → advanced)
- Bookmark frequently used docs

❌ **DON'T**:
- Skip the Getting Started guide
- Jump to advanced topics without basics
- Ignore prerequisites in tutorials
- Forget to check FAQ first

### Keyboard Shortcuts (GitHub)

- `t` - File finder
- `/` - Search files
- `b` - Browse files
- `y` - Get permalink
- `?` - Show shortcuts

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
