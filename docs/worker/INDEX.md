# Worker Job Protocol - Documentation Index

Complete guide to the h2kvm Worker Job Protocol v1 for production Kubernetes deployments.

---

## 📚 Documentation Structure

### Getting Started

1. **[QUICKSTART.md](QUICKSTART.md)** ⭐ **START HERE**
   - 5-minute introduction
   - First job submission
   - Basic concepts
   - CLI usage examples

2. **[PROTOCOL_SPEC.md](PROTOCOL_SPEC.md)** - Complete Specification
   - JSON schema definitions
   - State machine details
   - Capability system
   - Event streaming
   - API reference

### Deployment Guides

3. **[../deployment/WORKER_PROTOCOL_SUMMARY.md](../deployment/WORKER_PROTOCOL_SUMMARY.md)** - Complete Implementation Summary
   - v1.0.0 - v1.3.0 overview
   - Architecture diagrams
   - Statistics and metrics
   - Deployment options
   - Production checklist

4. **[../../k8s/README.md](../../k8s/README.md)** - Kubernetes Deployment
   - kubectl deployment
   - Makefile targets
   - PVC configuration
   - Job submission
   - Troubleshooting

5. **[../../helm/h2kvm-worker/README.md](../../helm/h2kvm-worker/README.md)** - Helm Chart
   - Installation guide
   - Configuration parameters
   - Storage setup
   - Monitoring integration
   - Examples (minimal, production)

### Version-Specific Guides

6. **[../deployment/production-enhancements.md](../deployment/production-enhancements.md)** - v1.1.0 Features
   - Persistent storage (5 PVCs)
   - Prometheus metrics
   - ServiceMonitor
   - Alert rules
   - Production DaemonSet

7. **[../deployment/v1.2.0-enhancements.md](../deployment/v1.2.0-enhancements.md)** - v1.2.0 Features
   - Metrics integration
   - Grafana dashboard (9 panels)
   - Helm charts
   - Template helpers
   - Conditional resources

8. **[../deployment/v1.3.0-cicd-ops.md](../deployment/v1.3.0-cicd-ops.md)** - v1.3.0 Features
   - GitHub Actions CI/CD
   - GitLab CI pipeline
   - Backup/restore scripts
   - Helm migration tool
   - Operator CRD foundation

### Operator Development (Future)

9. **[../../k8s/operator/README.md](../../k8s/operator/README.md)** - Operator Roadmap
   - MigrationJob CRD
   - Controller architecture
   - Development roadmap
   - Implementation technologies
   - Contributing guide

### Release Information

10. **[../../RELEASE_NOTES_v1.3.0.md](../../RELEASE_NOTES_v1.3.0.md)** - Latest Release
    - What's new in v1.3.0
    - Upgrade instructions
    - Breaking changes
    - Future roadmap

---

## 🎯 Quick Navigation

### By Role

**Developers (First Time)**
1. [QUICKSTART.md](QUICKSTART.md) - Learn basics
2. [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md) - Understand details
3. [k8s/worker/examples/](../../k8s/worker/examples/) - See examples

**DevOps Engineers**
1. [k8s/README.md](../../k8s/README.md) - kubectl deployment
2. [helm/README.md](../../helm/h2kvm-worker/README.md) - Helm installation
3. [v1.3.0-cicd-ops.md](../deployment/v1.3.0-cicd-ops.md) - CI/CD setup

**SRE / Operations**
1. [production-enhancements.md](../deployment/production-enhancements.md) - Monitoring
2. [v1.3.0-cicd-ops.md](../deployment/v1.3.0-cicd-ops.md) - Backup/restore
3. [WORKER_PROTOCOL_SUMMARY.md](../deployment/WORKER_PROTOCOL_SUMMARY.md) - Architecture

**Architects**
1. [WORKER_PROTOCOL_SUMMARY.md](../deployment/WORKER_PROTOCOL_SUMMARY.md) - Full overview
2. [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md) - Technical details
3. [operator/README.md](../../k8s/operator/README.md) - Future direction

### By Task

**Deploy Workers**
- [Helm Chart README](../../helm/h2kvm-worker/README.md) - Helm installation
- [k8s README](../../k8s/README.md) - kubectl deployment
- [k3d Test Report](../deployment/k3d-test-report.md) - Local testing

**Submit Jobs**
- [QUICKSTART.md](QUICKSTART.md) - Basic job submission
- [k8s/worker/examples/](../../k8s/worker/examples/) - Job examples
- [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md) - JSON schema

**Monitor Jobs**
- [v1.2.0-enhancements.md](../deployment/v1.2.0-enhancements.md) - Grafana dashboard
- [production-enhancements.md](../deployment/production-enhancements.md) - Prometheus metrics
- [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md) - Event streaming

**Operate Workers**
- [v1.3.0-cicd-ops.md](../deployment/v1.3.0-cicd-ops.md) - Backup/restore
- [helm/README.md](../../helm/h2kvm-worker/README.md) - Helm operations
- [k8s/README.md](../../k8s/README.md) - Troubleshooting

**Set Up CI/CD**
- [v1.3.0-cicd-ops.md](../deployment/v1.3.0-cicd-ops.md) - GitHub Actions + GitLab CI
- [.github/workflows/](../../.github/workflows/) - Workflow files
- [.gitlab-ci.yml](../../.gitlab-ci.yml) - GitLab config

---

## 📖 Learning Paths

### Path 1: Quick Start (1 hour)

1. Read [QUICKSTART.md](QUICKSTART.md) (15 min)
2. Deploy to k3d using [k8s README](../../k8s/README.md) (30 min)
3. Submit example job from [examples/](../../k8s/worker/examples/) (15 min)

### Path 2: Production Deployment (4 hours)

1. Read [WORKER_PROTOCOL_SUMMARY.md](../deployment/WORKER_PROTOCOL_SUMMARY.md) (30 min)
2. Review [Helm Chart README](../../helm/h2kvm-worker/README.md) (30 min)
3. Set up storage classes (1 hour)
4. Deploy with Helm + monitoring (1 hour)
5. Configure backups and CI/CD (1 hour)

### Path 3: Development (8 hours)

1. Read [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md) (1 hour)
2. Study code in `h2kvm/worker/*.py` (2 hours)
3. Run tests: `pytest tests/test_worker_protocol.py` (1 hour)
4. Build Docker images (1 hour)
5. Test in k3d (2 hours)
6. Review CI/CD workflows (1 hour)

### Path 4: Operator Development (Future)

1. Read [operator/README.md](../../k8s/operator/README.md) (30 min)
2. Install CRDs: `kubectl apply -f k8s/operator/crds/` (10 min)
3. Study MigrationJob spec (30 min)
4. Review operator frameworks (Kopf, Operator SDK) (1 hour)
5. Propose architecture in GitHub Discussions

---

## 🔍 Find What You Need

### Schemas and Specifications

| Topic | Document | Location |
|-------|----------|----------|
| Job Schema | PROTOCOL_SPEC.md | Section 2 |
| State Machine | PROTOCOL_SPEC.md | Section 3 |
| Capability System | PROTOCOL_SPEC.md | Section 4 |
| Event Format | PROTOCOL_SPEC.md | Section 5 |
| MigrationJob CRD | operator/README.md | Full spec |

### Configuration

| Topic | Document | Section |
|-------|----------|---------|
| Helm Values | helm/README.md | Configuration |
| Storage Classes | helm/README.md | Storage Configuration |
| Prometheus Metrics | production-enhancements.md | Metrics |
| Grafana Dashboard | v1.2.0-enhancements.md | Dashboard |
| DaemonSet Config | k8s/README.md | Manifests |

### Operations

| Topic | Document | Section |
|-------|----------|---------|
| Backup | v1.3.0-cicd-ops.md | Operational Scripts |
| Restore | v1.3.0-cicd-ops.md | Operational Scripts |
| Helm Migration | v1.3.0-cicd-ops.md | Operational Scripts |
| Troubleshooting | k8s/README.md | Troubleshooting |
| Monitoring | production-enhancements.md | Full Document |

### Examples

| Example | Location | Description |
|---------|----------|-------------|
| Inspect Job | k8s/worker/examples/inspect-job.json | Basic inspection |
| Convert Job | k8s/worker/examples/convert-job.json | VMDK to qcow2 |
| Offline Fix | k8s/worker/examples/offline-fix-job.json | Boot repair |
| Job Status | k8s/worker/examples/job-state.json | State tracking |
| Helm Values (Minimal) | helm/README.md | k3d deployment |
| Helm Values (Production) | helm/README.md | Production config |

---

## 📝 Documentation Standards

### File Organization

```
docs/
├── worker/                      Core protocol docs
│   ├── INDEX.md                This file
│   ├── QUICKSTART.md           Getting started
│   └── PROTOCOL_SPEC.md        Complete spec
│
├── deployment/                  Deployment guides
│   ├── WORKER_PROTOCOL_SUMMARY.md  Complete overview
│   ├── production-enhancements.md  v1.1.0 features
│   ├── v1.2.0-enhancements.md      v1.2.0 features
│   ├── v1.3.0-cicd-ops.md          v1.3.0 features
│   └── k3d-test-report.md          Test results
│
k8s/
├── README.md                    kubectl deployment
├── operator/
│   └── README.md                Operator roadmap
└── worker/examples/             Job examples

helm/h2kvm-worker/
└── README.md                    Helm chart guide

RELEASE_NOTES_v1.3.0.md         Latest release notes
```

### Document Types

**Guides (QUICKSTART, k8s/README)**
- Step-by-step instructions
- Code examples
- Expected outputs
- Common issues

**Specifications (PROTOCOL_SPEC)**
- Formal definitions
- JSON schemas
- API contracts
- State machines

**Reference (helm/README, SUMMARY)**
- Complete parameter lists
- Architecture diagrams
- Statistics
- Decision matrices

**Release Notes**
- What's new
- Upgrade instructions
- Breaking changes
- Known issues

---

## 🆕 Recent Updates

**v1.3.0 (2026-01-30)**
- Added CI/CD documentation
- Operational scripts guide
- Operator CRD foundation
- Complete implementation summary

**v1.2.0 (2026-01-30)**
- Grafana dashboard documentation
- Helm chart complete guide
- Metrics integration details

**v1.1.0 (2026-01-30)**
- Production enhancements guide
- Prometheus metrics reference
- k3d test report

**v1.0.0 (2026-01-30)**
- Initial protocol specification
- Quick start guide
- Kubernetes deployment basics

---

## 💡 Tips

### For New Users

1. **Start with QUICKSTART.md** - Don't skip this!
2. **Use k3d for learning** - Safe, local, fast
3. **Study examples** - Copy and modify example jobs
4. **Test locally first** - Before production deployment

### For Production

1. **Read WORKER_PROTOCOL_SUMMARY.md** - Understand architecture
2. **Review production checklist** - In WORKER_PROTOCOL_SUMMARY.md
3. **Set up monitoring first** - Before deploying workers
4. **Test backup/restore** - Before you need it

### For Developers

1. **Read PROTOCOL_SPEC.md thoroughly** - Complete understanding
2. **Run tests locally** - `pytest tests/test_worker_protocol.py`
3. **Use type hints** - Pydantic models are your friends
4. **Check CI before pushing** - Local tests first

### For Operators

1. **Automate backups** - Use scripts in `scripts/ops/`
2. **Monitor alerts** - Set up AlertManager integration
3. **Document customizations** - Keep Helm values in Git
4. **Plan upgrades** - Test in staging first

---

## 🤝 Contributing

Found a documentation issue?

1. Check if it's already reported: [GitHub Issues](https://github.com/ssahani/h2kvm/issues)
2. Submit improvement: [GitHub Pull Request](https://github.com/ssahani/h2kvm/pulls)
3. Discuss ideas: [GitHub Discussions](https://github.com/ssahani/h2kvm/discussions)

**Documentation Standards:**
- Use markdown (.md files)
- Include code examples
- Add expected outputs
- Link to related docs
- Keep navigation updated

---

## 📞 Support

### Self-Service

1. Search this index for your topic
2. Read the relevant guide
3. Check examples in `k8s/worker/examples/`
4. Review troubleshooting sections

### Community Support

- **GitHub Issues:** [Report bugs](https://github.com/ssahani/h2kvm/issues)
- **Discussions:** [Ask questions](https://github.com/ssahani/h2kvm/discussions)
- **Examples:** [k8s/worker/examples/](../../k8s/worker/examples/)

### Enterprise Support

For enterprise support, consulting, or custom development, contact the maintainers.

---

## 🎯 Next Steps

Based on your role:

**I'm a Developer** → [QUICKSTART.md](QUICKSTART.md)
**I'm deploying to k3d** → [k8s/README.md](../../k8s/README.md)
**I'm deploying to production** → [WORKER_PROTOCOL_SUMMARY.md](../deployment/WORKER_PROTOCOL_SUMMARY.md)
**I want to use Helm** → [helm/README.md](../../helm/h2kvm-worker/README.md)
**I need to set up CI/CD** → [v1.3.0-cicd-ops.md](../deployment/v1.3.0-cicd-ops.md)
**I want to contribute** → [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md)

---

**Last Updated:** 2026-03-29 (v1.3.0)
**Status:** Production-Ready ✅
