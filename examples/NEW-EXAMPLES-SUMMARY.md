# New Examples Summary - 2026-01-19

This document summarizes the new comprehensive examples added to hyper2kvm to demonstrate real-world migration scenarios, best practices, and CI/CD integration.

---

## 📚 New Example Categories

### 1. Industry-Specific Migration Examples (`industry-specific/`)

Real-world migration configurations for different industries with compliance requirements, security controls, and operational considerations.

#### Healthcare - HIPAA Compliant (`healthcare-hipaa-migration.yaml`)
**Scenario:** Electronic Health Records (EHR) system migration
**Compliance:** HIPAA, HITECH
**Features:**
- LUKS encryption for PHI (Protected Health Information)
- Audit logging for compliance
- Network isolation (medical VLAN)
- SELinux enforcing mode
- FIPS 140-2 compliant cryptography
- Post-migration validation checklist
- TPM 2.0 for measured boot

**Use Case:** Hospital migrating Epic EMR / Cerner / Athenahealth from VMware to KVM

---

#### Finance - PCI-DSS Compliant (`finance-pci-dss-migration.yaml`)
**Scenario:** Payment processing system migration
**Compliance:** PCI-DSS 4.0, SOC 2 Type II
**Features:**
- Network segmentation (CDE - Cardholder Data Environment)
- Encryption at rest and in transit
- Comprehensive audit trail
- Anti-malware scanning
- Change control documentation
- Quarterly vulnerability scanning
- HSM key management (Thales Luna)

**Use Case:** Bank migrating payment gateway from VMware to OpenStack KVM

---

#### E-Commerce - High Availability (`ecommerce-high-availability.yaml`)
**Scenario:** Zero-downtime migration for online store
**Scale:** 10,000 orders/day, Black Friday peak: 100,000 orders/day
**Features:**
- Blue-green deployment strategy
- Load balancer integration (HAProxy/NGINX)
- Database replication (MySQL primary-replica)
- Redis cluster for sessions
- CDN integration (Cloudflare/Fastly)
- Gradual traffic shift (10% → 100%)
- Performance monitoring (Prometheus/Grafana)

**Use Case:** E-commerce company migrating Magento/WooCommerce with zero downtime

---

#### Government - FedRAMP High (`government-fedramp-migration.yaml`)
**Scenario:** Federal government system migration
**Compliance:** FedRAMP High, FISMA High, NIST 800-53 Rev 5
**Features:**
- FIPS 140-2 validated cryptography
- Multi-factor authentication (PIV/CAC)
- Continuous monitoring (SIEM integration)
- DISA STIG hardening
- Supply chain security validation
- 7-year audit retention
- Annual security assessments (3PAO)

**Use Case:** Federal agency migrating case management system to FedRAMP cloud

---

### 2. Disaster Recovery Scenarios (`disaster-recovery/`)

Emergency migration procedures for catastrophic failures and business continuity scenarios.

#### Ransomware Recovery (`ransomware-recovery.sh`)
**Scenario:** VMware environment compromised by ransomware
**Challenge:** vCenter and ESXi hosts partially encrypted
**Solution:**
- Emergency VM extraction from read-only datastores
- Forensic analysis and malware scanning
- Isolated network recovery environment
- Priority-based restoration (Domain Controller → Email → Database)
- Integrity verification with checksums
- Incident response documentation

**Recovery Time:** 4 hours for critical systems
**Recovery Point:** Last known good backup (24 hours ago)

**Shell Script Features:**
- Automated backup integrity checking
- Priority VM queue (business impact order)
- Malware scanning with ClamAV + guestfish
- Forensic evidence preservation
- Incident report generation
- Network isolation enforcement

---

#### Datacenter Failover (`datacenter-failover.yaml`)
**Scenario:** Primary datacenter catastrophic failure
**Challenge:** Power outage, generators failed, 48+ hour restore time
**Solution:**
- Emergency activation of DR site KVM infrastructure
- CBT-replicated VMs (15-minute RPO)
- Automated DNS/load balancer cutover
- Multi-tier activation (Database → App → Web)
- Performance validation tests
- Communication plan for stakeholders

**Recovery Time Objective (RTO):** 2 hours
**Recovery Point Objective (RPO):** 15 minutes

**Includes:**
- Pre-activation checklist (incident commander approval)
- Network cutover procedures (DNS, HAProxy, firewall)
- Post-activation validation tests
- Rollback plan (if DR fails)
- Lessons learned template
- Annual DR testing schedule

---

### 3. Anti-Patterns Documentation (`ANTI-PATTERNS.md`)

Comprehensive guide to common mistakes and how to avoid them.

**Categories:**
1. **Pre-Migration Anti-Patterns**
   - "Let's Migrate Everything at Once" → Phased approach
   - "We Don't Need Backups" → Always snapshot first
   - "Testing is for the Weak" → Test clone before production

2. **Configuration Anti-Patterns**
   - "Default Settings are Fine" → Comprehensive config required
   - "fstab? What's that?" → UUID stability critical
   - "We'll Fix initramfs After" → Regenerate during migration

3. **Network Anti-Patterns**
   - "Change All Network Config During Migration" → One change at a time
   - "We Don't Need Network Isolation" → Test in isolated VLAN

4. **Storage Anti-Patterns**
   - "Skip Thin Provisioning" → Use qcow2 thin provisioning
   - "Who Needs Disk Cache Settings?" → cache=none for databases

5. **Security Anti-Patterns**
   - "SELinux? Just Disable It" → Fix contexts, don't disable
   - "Passwords in Config Files" → Use password files or vaults

6. **Performance Anti-Patterns**
   - "1 vCPU Should Be Enough" → Match original specs
   - "We Don't Need Performance Testing" → Baseline before cutover

7. **Operational Anti-Patterns**
   - "Documentation is for Losers" → Use --report flag
   - "Who Needs Monitoring?" → Set up before migration

8. **Recovery Anti-Patterns**
   - "Rollback Plan? What Rollback Plan?" → Keep VMware VM for 30 days
   - "We'll Just Wing the DR Test" → Quarterly testing required

**Real-World War Stories:**
- The Friday Evening Disaster ($500K lost sales)
- The SELinux "Temporary" Disable ($215M in damages)
- The "We Don't Need Testing" Migration ($2M + SEC fine)

---

### 4. CI/CD Integration Examples (`cicd-integration/`)

Automated migration pipelines for major CI/CD platforms.

#### Jenkins (`Jenkinsfile`)
**Features:**
- Multi-branch pipeline support
- Parallel VM processing (max 3 concurrent)
- Automated backup creation (VMware snapshots)
- Post-migration validation tests
- Automatic rollback on failure
- Slack/email notifications
- HTML reports publishing

**Pipeline Stages:**
1. Preparation - Create workspace, check resources
2. Pre-Migration Checks - Validate environment
3. Backup VMware VMs - Create snapshots
4. Migrate VMs - Parallel processing with hyper2kvm
5. Post-Migration Tests - Boot validation + smoke tests
6. Generate Reports - Aggregate results

**Parameters:**
- `MIGRATION_BATCH`: dev, test, staging, production
- `DRY_RUN`: Validation only (boolean)
- `AUTO_ROLLBACK`: Revert snapshot on failure (boolean)

---

#### GitLab CI/CD (`.gitlab-ci.yml`)
**Features:**
- Multi-stage pipeline (validate → backup → migrate → test → deploy → cleanup)
- Parallel processing with job dependencies
- Manual approval gates for production
- GitLab Environments integration (staging/production)
- Artifact management (30-day retention)
- Slack webhook notifications

**Stages:**
1. **Validate** - Preflight checks + config validation
2. **Backup** - VMware snapshots (manual approval required)
3. **Migrate** - Web servers (parallel 3x) + databases (sequential)
4. **Test** - Boot validation + smoke tests
5. **Deploy** - Staging (manual) → Production (manual + change ticket)
6. **Cleanup** - Remove old artifacts

**Matrix Strategy:**
- Web servers: Parallel processing (3 workers)
- Databases: Sequential (data integrity)

---

#### GitHub Actions (`github-actions.yml`)
**Features:**
- Workflow dispatch with input parameters
- Matrix strategy for parallel VMs
- GitHub Deployments (staging/production)
- Self-hosted runner support
- Test reporting with junit integration
- Slack notifications with action buttons
- Artifact retention (30-90 days)

**Jobs:**
1. **Preflight** - Environment validation
2. **Backup** - VMware snapshots
3. **Migrate** - Matrix strategy (fail-fast: false, max-parallel: 3)
4. **Test** - Boot validation + pytest smoke tests
5. **Deploy-Staging** - Automatic on develop branch
6. **Deploy-Production** - Manual approval on main branch
7. **Report** - Generate summary + GitHub release
8. **Notify** - Slack webhooks (success/failure)

**GitHub Features:**
- Environment protection rules
- Required reviewers for production
- Deployment status tracking
- Release notes generation

---

## 📊 Example Statistics

| Category | Files Created | Lines of Code | Use Cases Covered |
|----------|--------------|---------------|-------------------|
| Industry-Specific | 4 | 850+ | Healthcare, Finance, E-commerce, Government |
| Disaster Recovery | 2 | 600+ | Ransomware, Datacenter Failover |
| Anti-Patterns | 1 | 600+ | 24 anti-patterns, 3 war stories |
| CI/CD Integration | 3 | 900+ | Jenkins, GitLab CI, GitHub Actions |
| **Total** | **10** | **2,950+** | **8 real-world scenarios** |

---

## 🎯 How to Use These Examples

### Industry-Specific Examples

1. **Choose your industry template:**
   ```bash
   cp examples/industry-specific/healthcare-hipaa-migration.yaml \
      configs/my-ehr-migration.yaml
   ```

2. **Customize for your environment:**
   - Update vCenter connection details
   - Set VM names and resource allocations
   - Configure compliance-specific settings
   - Add your network/storage configuration

3. **Review security checklist:**
   - Each template includes post-migration security tasks
   - Compliance verification steps
   - Monitoring and alerting configuration

4. **Execute migration:**
   ```bash
   sudo python -m hyper2kvm --config configs/my-ehr-migration.yaml
   ```

---

### Disaster Recovery Scenarios

#### Ransomware Recovery

1. **Assess the situation:**
   - Verify backup integrity
   - Identify accessible datastores
   - Prioritize critical systems

2. **Run recovery script:**
   ```bash
   sudo ./examples/disaster-recovery/ransomware-recovery.sh
   ```

3. **Script automatically:**
   - Checks backup checksums
   - Recovers VMs in priority order
   - Performs malware scanning
   - Isolates recovered VMs in separate network
   - Generates incident report

4. **Post-recovery:**
   - Review forensic logs
   - Validate no malware present
   - Gradual production restoration

#### Datacenter Failover

1. **Customize config:**
   ```bash
   cp examples/disaster-recovery/datacenter-failover.yaml \
      configs/my-dr-failover.yaml
   ```

2. **Update DR site details:**
   - DR network configuration
   - Storage paths
   - Load balancer IPs

3. **Follow activation checklist:**
   - Verify last replication timestamp
   - Check DR infrastructure health
   - Get incident commander approval

4. **Execute DR activation:**
   ```bash
   sudo python -m hyper2kvm --config configs/my-dr-failover.yaml
   ```

---

### Anti-Patterns Guide

**Before EVERY migration:**

1. **Read the anti-patterns document:**
   ```bash
   less examples/ANTI-PATTERNS.md
   ```

2. **Review relevant sections:**
   - Pre-Migration Anti-Patterns → Before planning
   - Configuration Anti-Patterns → When writing configs
   - Security Anti-Patterns → Security review
   - Operational Anti-Patterns → Production deployment

3. **Use as migration checklist:**
   - Print the "Golden Rules" section
   - Check off each rule as you address it
   - Review war stories to understand consequences

4. **Team onboarding:**
   - Make required reading for new engineers
   - Reference during migration planning meetings
   - Include in runbooks

---

### CI/CD Integration

#### Jenkins Setup

1. **Install pipeline:**
   ```bash
   cp examples/cicd-integration/Jenkinsfile \
      jenkins/pipelines/vm-migration/Jenkinsfile
   ```

2. **Configure Jenkins:**
   - Add credentials (vCenter username/password)
   - Configure Slack webhook (optional)
   - Set up Jenkins agent with KVM

3. **Create VM batch files:**
   ```yaml
   # jenkins/vm-batches/dev.yaml
   vms:
     - name: dev-web-01
       memory: 4096
       vcpus: 2
     - name: dev-db-01
       memory: 8192
       vcpus: 4
   ```

4. **Run pipeline:**
   - Trigger from Jenkins UI
   - Select migration batch
   - Monitor progress in Jenkins console

#### GitLab CI Setup

1. **Add pipeline to repo:**
   ```bash
   cp examples/cicd-integration/.gitlab-ci.yml .
   ```

2. **Configure CI/CD variables:**
   - Go to: Settings → CI/CD → Variables
   - Add: `VCENTER_USER` (protected, masked)
   - Add: `VCENTER_PASSWORD` (protected, masked)
   - Add: `SLACK_WEBHOOK_URL` (optional)

3. **Configure GitLab Runner:**
   ```bash
   # Install hyper2kvm on runner
   pip install hyper2kvm

   # Tag runner
   gitlab-runner register --tag-list kvm-migration
   ```

4. **Trigger pipeline:**
   - Push to repository
   - Or: CI/CD → Pipelines → Run Pipeline

#### GitHub Actions Setup

1. **Add workflow:**
   ```bash
   mkdir -p .github/workflows
   cp examples/cicd-integration/github-actions.yml \
      .github/workflows/vm-migration.yml
   ```

2. **Configure secrets:**
   - Settings → Secrets and variables → Actions
   - Add: `VCENTER_USER`
   - Add: `VCENTER_PASSWORD`
   - Add: `SLACK_WEBHOOK` (optional)

3. **Set up self-hosted runner:**
   ```bash
   # On KVM host
   ./config.sh --url https://github.com/org/repo \
     --token YOUR_TOKEN \
     --labels kvm-migration
   ```

4. **Trigger workflow:**
   - Actions → VM Migration to KVM → Run workflow
   - Select migration batch
   - Configure options (dry-run, auto-rollback)

---

## 🚀 Quick Start for Common Scenarios

### Scenario 1: Healthcare EHR Migration

```bash
# 1. Copy template
cp examples/industry-specific/healthcare-hipaa-migration.yaml \
   configs/ehr-migration.yaml

# 2. Edit configuration
vim configs/ehr-migration.yaml
# Update: vcenter, vs_vm_name, output_dir

# 3. Dry-run validation
sudo python -m hyper2kvm --config configs/ehr-migration.yaml --dry-run

# 4. Execute migration (after approval)
sudo python -m hyper2kvm --config configs/ehr-migration.yaml

# 5. Post-migration: Enable LUKS encryption
sudo cryptsetup luksFormat --type luks2 --cipher aes-xts-plain64 \
    /dev/vg0/ehr-prod-01
```

---

### Scenario 2: E-Commerce Blue-Green Migration

```bash
# 1. Copy template
cp examples/industry-specific/ecommerce-high-availability.yaml \
   configs/webshop-migration.yaml

# 2. Phase 1: Migrate first web server
sudo python -m hyper2kvm --config configs/webshop-migration.yaml

# 3. Phase 2: Run in parallel with production (24 hours)
# Monitor metrics, compare performance

# 4. Phase 3: Gradual traffic shift
# HAProxy: 10% → 25% → 50% → 75% → 100%

# 5. Phase 4: Full cutover after validation
```

---

### Scenario 3: Ransomware Emergency Recovery

```bash
# 1. Assess damage
ls -la /backups/vmware/latest/

# 2. Run emergency recovery
sudo ./examples/disaster-recovery/ransomware-recovery.sh

# 3. Script automatically:
# - Verifies backup integrity
# - Recovers critical VMs in priority order
# - Scans for malware
# - Generates incident report

# 4. Review incident report
cat /recovery/ransomware-*/reports/incident-summary.md

# 5. Gradual restoration (after malware clearance)
```

---

## 📖 Additional Resources

- **Main Documentation:** `docs/`
- **Configuration Examples:** `examples/yaml/`
- **Test Configs:** `test-confs/`
- **Library API Examples:** `examples/library_*.py`

---

## 🤝 Contributing

Found these examples helpful? Have a new industry-specific scenario? Encountered an anti-pattern not documented?

**Submit a PR or open an issue:**
- GitHub: https://github.com/ssahani/hyper2kvm/issues
- GitLab: https://gitlab.com/ssahani/hyper2kvm/issues

---

## 📝 License

These examples are part of hyper2kvm and are licensed under the Apache-2.0 License.

---

**Last Updated:** 2026-01-19
**Author:** hyper2kvm contributors
**Maintained by:** ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
