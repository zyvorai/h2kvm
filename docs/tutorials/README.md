# H2KVM Tutorials

Step-by-step tutorials for learning H2KVM, from beginner to enterprise deployment.

## Learning Path

Follow these tutorials in order for the best learning experience:

### 🟢 Level 1: Beginner (0-2 hours)
**[01 - Beginner Migration](01-beginner-migration.md)**

Your first VM migration with detailed explanations.

**Prerequisites**: None - start here!

**What you'll learn:**
- Installing H2KVM
- Understanding YAML configuration
- Running your first migration
- Importing to libvirt
- Verifying the migrated VM

**Time**: 1-2 hours  
**Difficulty**: ⭐ Easy

---

### 🟡 Level 2: Intermediate (2-8 hours)
**[02 - Intermediate Workflows](02-intermediate-workflows.md)**

Batch migrations, automation, and advanced workflows.

**Prerequisites**: Complete beginner tutorial

**What you'll learn:**
- Batch migration with manifests
- Automating migrations with scripts
- Using different input formats (OVA, OVF, VHD)
- Remote fetch from ESXi
- Migration validation
- Rollback procedures

**Time**: 4-8 hours  
**Difficulty**: ⭐⭐ Moderate

---

### 🟠 Level 3: Advanced (8+ hours)
**[03 - Advanced Features](03-advanced-features.md)**

Live migration, DR testing, and database-aware migrations.

**Prerequisites**: Complete intermediate tutorial

**What you'll learn:**
- Live migration techniques
- Database server migration
- DR testing workflows
- Custom fixers and hooks
- Performance optimization
- Advanced troubleshooting

**Time**: 8+ hours  
**Difficulty**: ⭐⭐⭐ Advanced

---

### 🔴 Level 4: Enterprise (Full deployment)
**[04 - Enterprise Deployment](04-enterprise-deployment.md)**

Production deployment strategies and best practices.

**Prerequisites**: Complete advanced tutorial

**What you'll learn:**
- Production architecture design
- High-availability setup
- Monitoring and alerting
- Security hardening
- Compliance and audit
- Large-scale migration planning
- Kubernetes/OpenShift deployment

**Time**: Full implementation project  
**Difficulty**: ⭐⭐⭐⭐ Expert

---

## Quick Reference

### By Skill Level

| Level | Tutorial | Time | Prerequisites |
|-------|----------|------|---------------|
| **Beginner** | [01 - Beginner](01-beginner-migration.md) | 1-2h | None |
| **Intermediate** | [02 - Intermediate](02-intermediate-workflows.md) | 4-8h | Tutorial 01 |
| **Advanced** | [03 - Advanced](03-advanced-features.md) | 8+h | Tutorial 02 |
| **Enterprise** | [04 - Enterprise](04-enterprise-deployment.md) | Project | Tutorial 03 |
| **vSphere** | [05 - vSphere Export](05-vsphere-export-tools.md) | 1-2h | govc or ovftool |
| **Windows** | [06 - Windows Migration](06-windows-migration.md) | 2-4h | virtio-win ISO |

### By Topic

| Topic | Tutorial | Level |
|-------|----------|-------|
| **First Migration** | Tutorial 01 | Beginner |
| **Batch Migration** | Tutorial 02 | Intermediate |
| **Live Migration** | Tutorial 03 | Advanced |
| **Windows VMs** | Tutorial 01, 02 | Beginner/Intermediate |
| **Linux VMs** | Tutorial 01, 02 | Beginner/Intermediate |
| **Remote Fetch** | Tutorial 02 | Intermediate |
| **DR Testing** | Tutorial 03 | Advanced |
| **Database Migration** | Tutorial 03 | Advanced |
| **Production Deployment** | Tutorial 04 | Enterprise |
| **Kubernetes/OpenShift** | Tutorial 04 | Enterprise |

### By Use Case

| Use Case | Recommended Tutorial |
|----------|---------------------|
| **Migrate a single VM** | Tutorial 01 |
| **Migrate 10-50 VMs** | Tutorial 02 |
| **Migrate 100+ VMs** | Tutorial 04 |
| **Test DR environment** | Tutorial 03 |
| **Move database server** | Tutorial 03 |
| **Production migration** | Tutorial 04 |
| **Learn the tool** | Tutorial 01 → 02 → 03 |
| **Quick proof of concept** | Tutorial 01 |

## Tutorial Structure

Each tutorial follows this structure:

### 1. Overview
- What you'll learn
- Prerequisites
- Time required
- Difficulty level

### 2. Concepts
- Key concepts introduced
- Why they matter
- When to use them

### 3. Hands-On Practice
- Step-by-step instructions
- Example configurations
- Expected outputs
- Troubleshooting tips

### 4. Validation
- How to verify success
- What to check
- Common issues

### 5. Summary
- Key takeaways
- Next steps
- Additional resources

## Tutorial Prerequisites

### For All Tutorials

**Required:**
- Linux system (RHEL 9, Ubuntu 22.04+, or similar)
- Python 3.10+
- 8 GB RAM minimum
- 100 GB free disk space
- Basic Linux command-line knowledge

**Optional:**
- Test VMs for practice
- KVM/libvirt installed
- ESXi host for remote fetch practice

### Tutorial-Specific Prerequisites

**Tutorial 01 (Beginner):**
- No additional requirements

**Tutorial 02 (Intermediate):**
- Completed Tutorial 01
- Multiple test VMs (or sample VMDKs)
- Understanding of YAML

**Tutorial 03 (Advanced):**
- Completed Tutorials 01-02
- Understanding of Linux boot process
- Database server knowledge (for DB migration)

**Tutorial 04 (Enterprise):**
- Completed Tutorials 01-03
- Kubernetes/OpenShift cluster (or access to one)
- Understanding of enterprise architecture
- Security and compliance knowledge

## Practice Environment Setup

### Option 1: Local Practice

```bash
# Install H2KVM
pip install "h2kvm[full]"

# Install libvirt for testing
sudo dnf install -y libvirt qemu-kvm virt-manager  # Fedora/RHEL
sudo apt-get install -y libvirt-daemon qemu-kvm  # Ubuntu

# Download sample VMs (if needed)
# See examples/test-vms/ for sample VMDK files
```

### Option 2: Lab Environment

Consider setting up a dedicated lab with:
- ESXi host or VMware Workstation
- KVM host for target
- Network connectivity between source and target
- Sufficient storage for VM images

### Option 3: Cloud-Based Practice

Use cloud providers for practice:
- AWS EC2 instances
- Azure VMs
- Google Cloud Compute
- Oracle Cloud

**Note**: Some tutorials include cloud-specific examples.

## Getting Help

### During Tutorials

If you get stuck:

1. **Check the Troubleshooting section** in the tutorial
2. **Review error messages** carefully
3. **Consult the troubleshooting guide**: [Troubleshooting Guide](../guides/troubleshooting.md)
4. **Check migration recipes**: [Migration Recipes](../recipes/01-common-scenarios.md)
5. **Ask for help**: [GitHub Discussions](https://github.com/ssahani/h2kvm/discussions)

### Additional Resources

- **[Migration Recipes](../recipes/)** - Quick solutions for common scenarios
- **[User Guides](../guides/)** - Task-oriented guides
- **[API Reference](../reference/api/)** - Detailed API documentation
- **[Troubleshooting Guide](../guides/troubleshooting.md)** - Common issues and solutions

## Time Estimates

### Total Learning Time

| Path | Time | Description |
|------|------|-------------|
| **Quick Start** | 2 hours | Tutorial 01 only |
| **Intermediate** | 12 hours | Tutorials 01-02 |
| **Advanced** | 24+ hours | Tutorials 01-03 |
| **Complete** | 40+ hours | All tutorials + practice |
| **Enterprise Ready** | 80+ hours | All tutorials + production deployment |

### Practice Recommendations

- **Beginner**: 1 week (1-2 hours/day)
- **Intermediate**: 2-3 weeks (2-3 hours/day)
- **Advanced**: 4-6 weeks (2-3 hours/day)
- **Enterprise**: 2-3 months (includes planning and deployment)

## Tutorial Goals

### After Tutorial 01 (Beginner)
✅ Understand basic migration concepts  
✅ Perform a simple VM migration  
✅ Import VM to libvirt  
✅ Verify migrated VM boots

### After Tutorial 02 (Intermediate)
✅ Perform batch migrations  
✅ Use different input formats  
✅ Fetch VMs remotely  
✅ Automate migration workflows  
✅ Validate and rollback migrations

### After Tutorial 03 (Advanced)
✅ Perform live migrations  
✅ Migrate database servers safely  
✅ Test DR scenarios  
✅ Create custom fixers  
✅ Optimize performance  
✅ Troubleshoot complex issues

### After Tutorial 04 (Enterprise)
✅ Design production architecture  
✅ Implement HA and monitoring  
✅ Deploy on Kubernetes/OpenShift  
✅ Meet security requirements  
✅ Plan large-scale migrations  
✅ Ensure compliance

## Related Documentation

### Before Tutorials
- **[Getting Started](../getting-started/)** - Installation and setup
- **[Installation Guide](../getting-started/01-Installation.md)** - Install H2KVM

### During Tutorials
- **[Migration Recipes](../recipes/)** - Quick reference patterns
- **[Troubleshooting Guide](../guides/troubleshooting.md)** - Fix issues
- **[User Guides](../guides/)** - Feature-specific guides

### After Tutorials
- **[API Reference](../reference/api/)** - Complete API docs
- **[Features](../features/)** - Detailed feature documentation
- **[Deployment](../deployment/)** - Production deployment guides

## Feedback and Improvements

Help us improve these tutorials:

- **Found an error?** [Open an issue](https://github.com/ssahani/h2kvm/issues)
- **Have a suggestion?** [Start a discussion](https://github.com/ssahani/h2kvm/discussions)
- **Want to contribute?** [See contributing guide](../development/contributing.md)

## What's Next?

Choose your starting point:

### 🎯 I'm brand new to H2KVM
→ Start with [Tutorial 01 - Beginner](01-beginner-migration.md)

### 🚀 I've done a basic migration before
→ Jump to [Tutorial 02 - Intermediate](02-intermediate-workflows.md)

### 🔧 I need advanced features
→ Go to [Tutorial 03 - Advanced](03-advanced-features.md)

### 🏢 I'm planning production deployment
→ See [Tutorial 04 - Enterprise](04-enterprise-deployment.md)

### 📚 I want to explore features
→ Check [Features Index](../features/README.md)

---

## Quick Links

### Before You Start
- **[Installation Guide](../getting-started/01-Installation.md)** - Set up h2kvm
- **[System Requirements](../getting-started/02-System-Requirements.md)** - Prerequisites check
- **[LVM Performance Guide](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - Understand 7x faster LVM improvements

### Learning Resources
- **[Migration Recipes](../recipes/README.md)** - Quick reference patterns
- **[OS-Specific Guides](../os-support/README.md)** - Platform-specific migration guides
- **[Troubleshooting](../guides/troubleshooting.md)** - Common issues and solutions

### Performance Features
- **[LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - 7x faster LVM activation, 100% host protection
- **[Test Results](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Production validation with RHEL 8.8 and openSUSE

---

**Ready to learn?** Start with [Tutorial 01](01-beginner-migration.md) →

---

**Last Updated**: March 29, 2026
**Version**: 0.3.0
**Total Tutorials**: 4
**Estimated Total Time**: 40+ hours for complete mastery
