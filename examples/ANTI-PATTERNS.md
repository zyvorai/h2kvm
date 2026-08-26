# hyper2kvm Anti-Patterns and Common Mistakes

> **"Learn from the mistakes of others. You can't live long enough to make them all yourself."** - Eleanor Roosevelt

This document catalogs common mistakes, anti-patterns, and pitfalls when migrating VMs to KVM. Learn from these failures to ensure your migrations succeed.

---

## Table of Contents

- [Pre-Migration Anti-Patterns](#pre-migration-anti-patterns)
- [Configuration Anti-Patterns](#configuration-anti-patterns)
- [Network Anti-Patterns](#network-anti-patterns)
- [Storage Anti-Patterns](#storage-anti-patterns)
- [Security Anti-Patterns](#security-anti-patterns)
- [Performance Anti-Patterns](#performance-anti-patterns)
- [Operational Anti-Patterns](#operational-anti-patterns)
- [Recovery Anti-Patterns](#recovery-anti-patterns)

---

## Pre-Migration Anti-Patterns

### ❌ Anti-Pattern: "Let's Migrate Everything at Once"

**What people do:**
```bash
# Migrate entire datacenter in one weekend
for vm in $(govc ls /DC1/vm/); do
    hyper2kvm vsphere --vs-vm-name "$vm" &  # Fork bomb!
done
```

**Why it fails:**
- No prioritization (critical systems migrate last by accident)
- Resource exhaustion (network, storage, CPU bottlenecks)
- No rollback plan (can't undo 500 VMs)
- Impossible to troubleshoot (which of 500 VMs failed?)

**✅ Do this instead:**
```bash
# Phased migration approach
# Week 1: Non-critical dev/test (10 VMs)
# Week 2: Secondary systems (20 VMs)
# Week 3: Production tier-3 (30 VMs)
# Week 4: Production tier-2 (40 VMs)
# Week 5: Production tier-1 (critical 10 VMs)

# One VM at a time with validation
hyper2kvm --config tier1-database.yaml
# Test, validate, monitor for 24 hours
# Only then proceed to next VM
```

**Lesson:** Slow is smooth, smooth is fast.

---

### ❌ Anti-Pattern: "We Don't Need Backups, This Will Work"

**What people do:**
```yaml
# No backup, no snapshot, YOLO migration
cmd: vsphere
vs_vm_name: production-database
# Just delete the VMware VM after, right?
```

**Why it fails:**
- Murphy's Law: Anything that can go wrong, will
- Network failures during migration = corrupt disk
- Wrong VM selected = delete production instead of test
- Unforeseen application compatibility issues

**✅ Do this instead:**
```bash
# BEFORE migration
# 1. VMware snapshot
govc snapshot.create -vm production-database \
    -m "Pre-migration snapshot $(date +%Y%m%d)"

# 2. Verify snapshot exists
govc snapshot.tree -vm production-database

# 3. Backup current state
govc datastore.download \
    -ds datastore1 \
    production-database/production-database.vmdk \
    /backups/pre-migration/

# 4. THEN migrate
hyper2kvm --config production-database.yaml

# 5. Keep VMware snapshot for 30 days
# 6. Only delete after successful validation
```

**Lesson:** Always have a rollback plan. Always.

---

### ❌ Anti-Pattern: "Testing is for the Weak"

**What people do:**
```bash
# Migrate straight to production without testing
hyper2kvm vsphere --vs-vm-name critical-erp-prod --output-dir /var/lib/libvirt/images/
virsh start critical-erp-prod  # HOPE IT WORKS!
```

**Why it fails:**
- Driver issues discovered in production
- Network config errors = outage
- Application incompatibilities = angry users
- No performance baseline = degraded service

**✅ Do this instead:**
```bash
# 1. Clone VM for testing
govc vm.clone -vm critical-erp-prod -on=false critical-erp-test

# 2. Migrate test clone
hyper2kvm vsphere --vs-vm-name critical-erp-test \
    --output-dir /test/migrations/

# 3. Boot and validate
virsh start critical-erp-test
# Run test suite
./tests/erp-smoke-tests.sh critical-erp-test

# 4. Performance test
ab -n 1000 -c 10 http://critical-erp-test/

# 5. Only if all tests pass → migrate production
```

**Lesson:** Test twice, migrate once.

---

## Configuration Anti-Patterns

### ❌ Anti-Pattern: "Default Settings are Fine"

**What people do:**
```yaml
# Bare minimum configuration
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: /output
# That's it!
```

**Why it fails:**
- fstab still has /dev/sdX entries → boot fails
- initramfs missing virtio drivers → kernel panic
- GRUB still references old root device → "Kernel not found"
- Network configured for VMware vmxnet3 → no network

**✅ Do this instead:**
```yaml
# Comprehensive configuration for production
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: /output
out_format: qcow2
compress: true

# Critical fixes (don't skip these!)
regen_initramfs: true       # ← REQUIRED for boot success
fstab_mode: stabilize-all   # ← Converts /dev/sdX to UUID
# grub is auto-handled
network_mode: preserve      # ← Keeps existing network config

# Logging for troubleshooting
verbose: 2
log_file: /var/log/hyper2kvm/{vm-name}.log
report: /reports/{vm-name}.md

# Test before production
test_boot: true
test_timeout: 300
```

**Lesson:** Defaults are defaults for a reason - they're not optimal for your use case.

---

### ❌ Anti-Pattern: "fstab? What's that?"

**What people do:**
```yaml
# Ignore fstab completely
fstab_mode: noop  # "We'll fix it later"
```

**Why it fails:**
```
# After migration (boot failure):
[FAILED] Failed to mount /data
[DEPEND] Dependency failed for Local File Systems
You are in emergency mode.
```

**Real-world failure:**
```bash
# /etc/fstab (before migration):
/dev/sdb1  /data  ext4  defaults  0  2  # ← Device name will change!

# After migration to KVM:
# /dev/sdb → /dev/vdb (virtio)
# Mount fails, boot fails
```

**✅ Do this instead:**
```yaml
# Always stabilize fstab
fstab_mode: stabilize-all  # Converts all entries to UUID

# Result:
# UUID=abc-123  /data  ext4  defaults  0  2  ← Works anywhere!
```

**Lesson:** Device names are ephemeral, UUIDs are forever.

---

### ❌ Anti-Pattern: "We'll Fix initramfs After Migration"

**What people do:**
```yaml
regen_initramfs: false  # "Too slow, skip it"
```

**Why it fails:**
```
Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)
```

**What happened:**
```bash
# VMware VM initramfs contains:
# - vmxnet3 (VMware network driver)
# - pvscsi (VMware storage driver)

# But KVM needs:
# - virtio_net (KVM network)
# - virtio_blk (KVM storage)

# Without regenerating initramfs → kernel can't access storage → panic
```

**✅ Do this instead:**
```yaml
# ALWAYS regenerate initramfs
regen_initramfs: true

# hyper2kvm automatically:
# 1. Detects OS type (RHEL/Ubuntu/SUSE)
# 2. Runs appropriate command:
#    - RHEL: dracut -f
#    - Ubuntu: update-initramfs -u
#    - SUSE: mkinitrd
# 3. Includes virtio drivers
# 4. Verifies initramfs contains required modules
```

**Lesson:** initramfs is not optional, it's the boot process.

---

## Network Anti-Patterns

### ❌ Anti-Pattern: "Let's Change All Network Config During Migration"

**What people do:**
```yaml
# Reconfigure networking during migration
network_mode: reconfigure
# Change to different IP range, new gateway, new DNS
# What could go wrong?
```

**Why it fails:**
- Application hardcoded to old IP → can't connect to database
- Firewall rules reference old IPs → blocked
- Monitoring still expects old IP → pages NOC at 3 AM
- Load balancer has old backend IP → traffic goes nowhere

**✅ Do this instead:**
```yaml
# Phase 1: Preserve existing network config
network_mode: preserve  # Keep everything the same

# Phase 2: After successful migration and validation
# THEN change network config (separate change window)
```

**Lesson:** Change one thing at a time. Hypervisor OR network, not both.

---

### ❌ Anti-Pattern: "We Don't Need Network Isolation for Testing"

**What people do:**
```bash
# Test VM on production network with production IP
virsh attach-interface test-vm bridge br-production --mac 00:50:56:ab:cd:ef
```

**Why it fails:**
- IP conflict (test VM has same IP as production)
- ARP storm (duplicate MACs)
- Accidental database writes to production
- Test email sends to real customers

**Horror story:**
```
Test migration of e-commerce system accidentally:
- Connected to production database
- Sent 10,000 "Order Confirmed" emails to random customers
- Charged credit cards for fake test orders
- Cost: $2.5M in refunds + reputation damage
```

**✅ Do this instead:**
```bash
# Use isolated network for testing
virsh attach-interface test-vm bridge br-isolated --mac 00:00:00:00:00:01

# Or use completely separate VLAN
# VLAN 100: Production
# VLAN 999: Testing/Migration (no route to production)
```

**Lesson:** Isolation isn't paranoia, it's prudence.

---

## Storage Anti-Patterns

### ❌ Anti-Pattern: "Let's Skip Thin Provisioning, We Have Plenty of Space"

**What people do:**
```bash
# Convert to thick/preallocated format
qemu-img convert -O qcow2 -o preallocation=full source.vmdk output.qcow2
# 100 VMs × 500 GB each = 50 TB used (but only 5 TB actual data)
```

**Why it fails:**
- Storage 95% full after 20 migrations (planned for 100)
- Can't complete migration project
- Emergency storage procurement ($$$$)
- 6-week delay waiting for new SAN

**✅ Do this instead:**
```yaml
# Use thin provisioning (default in hyper2kvm)
out_format: qcow2  # Thin by default
compress: true     # Further reduces size

# Result:
# 500 GB VMDK → 50 GB qcow2 (actual data)
# 100 VMs use 5 TB instead of 50 TB
```

**Lesson:** Thin provisioning is your friend (but monitor usage!).

---

### ❌ Anti-Pattern: "Who Needs Disk Cache Settings?"

**What people do:**
```yaml
# Accept defaults, don't think about cache
# (default: writethrough on many systems)
```

**Why it fails:**
```
# Performance comparison:
# cache=writethrough: 50 IOPS
# cache=writeback:    5000 IOPS (100x faster!)
#
# Application expects fast storage → times out
# Database health checks fail → pager alert
# Users complain about "slow" migrated system
```

**✅ Do this instead:**
```yaml
# Choose cache mode based on use case:

# Database servers (integrity > speed):
disk_cache: none

# Web servers (speed > integrity):
disk_cache: writeback

# General purpose:
disk_cache: writethrough  # Balance of both
```

**Lesson:** Cache settings can make or break performance.

---

## Security Anti-Patterns

### ❌ Anti-Pattern: "SELinux? Just Disable It"

**What people do:**
```bash
# After migration fails to start application
setenforce 0  # "Quick fix!"
sed -i 's/SELINUX=enforcing/SELINUX=disabled/' /etc/selinux/config
```

**Why it fails:**
- Compliance violation (PCI-DSS, HIPAA require MAC)
- Opens security holes
- Audit findings = failed certification
- Potential breach exposure

**Real incident:**
```
Company disabled SELinux "temporarily" during migration.
Forgot to re-enable it.
Attacker exploited Apache vulnerability.
SELinux would have contained the breach.
Entire database exfiltrated.
Cost: $15M fine + $200M in damages.
```

**✅ Do this instead:**
```bash
# Fix SELinux contexts instead of disabling
restorecon -Rv /var/www/html
# Or create custom policy
audit2allow -a -M myapp
semodule -i myapp.pp
```

**Lesson:** SELinux errors mean "fix your app", not "disable security".

---

### ❌ Anti-Pattern: "Passwords in Config Files are Fine"

**What people do:**
```yaml
# Plaintext password in version control
vcenter: vcenter.example.com
vc_user: administrator@vsphere.local
password: "SuperSecret123!"  # ← OOPS, committed to GitHub
```

**Why it fails:**
- Credential leak to version control history
- Scanners find credentials (GitGuardian, TruffleHog)
- Automated exploitation (cryptominers, ransomware)
- Incident response cost > $100K

**✅ Do this instead:**
```yaml
# Use password files (not in VCS)
vcenter: vcenter.example.com
vc_user: administrator@vsphere.local
vc_password_env: VC_PASSWORD

# Or environment variables
password: ${VCENTER_PASSWORD}

# Or secret management
# HashiCorp Vault, AWS Secrets Manager, etc.
```

**Lesson:** Secrets in version control = guaranteed breach.

---

## Performance Anti-Patterns

### ❌ Anti-Pattern: "1 vCPU Should Be Enough for Everyone"

**What people do:**
```yaml
# Under-provision resources to "save money"
domain_vcpus: 1  # Production database with 1 CPU
domain_memory: 2048  # 2GB for Java app that needs 8GB
```

**Why it fails:**
```
# Performance comparison:
Before migration (VMware 8 vCPU): 1000 req/sec
After migration (KVM 1 vCPU):     10 req/sec (100x slower!)

# User complaints flood in
# "Why is everything so slow?"
# Rollback required
# Project credibility destroyed
```

**✅ Do this instead:**
```yaml
# Match or exceed original VM specs
domain_vcpus: 8  # Same as VMware
domain_memory: 16384  # Same as VMware

# After migration validated, THEN rightsize
# Use monitoring data to determine actual needs
```

**Lesson:** Migrate first, optimize later.

---

### ❌ Anti-Pattern: "We Don't Need Performance Testing"

**What people do:**
```bash
# Migrate, put in production, hope for the best
hyper2kvm --config prod-vm.yaml
virsh start prod-vm
# Users are the performance testers!
```

**Why it fails:**
```
# 3 PM Friday:
"The website is down!"

# Investigation:
KVM host: 99% CPU utilization (host oversubscribed)
Disk I/O wait: 85% (slow SAN)
Memory: Swapping (host OOM)

# Root cause:
Never tested with production load
Discovered issues in production
Emergency rollback required
Weekend ruined
```

**✅ Do this instead:**
```bash
# Before production cutover:

# 1. Baseline current performance
ab -n 10000 -c 100 http://prod-vm-vmware/

# 2. Performance test KVM
ab -n 10000 -c 100 http://prod-vm-kvm/

# 3. Compare metrics
# - Response time: ±10% acceptable
# - Throughput: Same or better
# - Error rate: Same or better
# - Resource usage: < 70% CPU, < 80% RAM

# 4. Load soak test (24-hour run)
# 5. THEN cut over to production
```

**Lesson:** Performance surprises in production are career-limiting events.

---

## Operational Anti-Patterns

### ❌ Anti-Pattern: "Documentation is for Losers"

**What people do:**
```bash
# No documentation, all tribal knowledge
# Run some commands (don't remember which)
# Six months later: "How did we do this again?"
```

**Why it fails:**
```
New engineer: "How do I migrate a VM?"
Team: "Ask Bob, he did all the migrations"
Bob: "I left the company 3 months ago"
Team: "Uh..."

# Result: Repeat all the mistakes again
```

**✅ Do this instead:**
```yaml
# Every migration: Generate report
report: /docs/migrations/{vm-name}-report.md

# Result: Automatic documentation of:
# - Configuration used
# - Fixes applied
# - Issues encountered
# - Validation results
#
# Future migrations: Reference past reports
```

**Lesson:** Your future self (or replacement) will thank you.

---

### ❌ Anti-Pattern: "Who Needs Monitoring After Migration?"

**What people do:**
```bash
# Migrate VM, forget about it
# No monitoring, no alerts
# Hope == strategy
```

**Why it fails:**
```
# 2 weeks after migration:
VM crashed 10 days ago
No one noticed
No alerts sent
Customers tried to report it, gave up
Lost 10 days of business

# Post-mortem:
"Why didn't monitoring catch this?"
"We disabled the VMware monitoring during migration"
"We forgot to set up KVM monitoring"
```

**✅ Do this instead:**
```bash
# BEFORE migration:
1. Set up monitoring for new KVM VM
2. Configure alerts (same thresholds as VMware)
3. Test alerts (trigger test page)
4. THEN migrate
5. Verify alerts working post-migration

# Monitoring checklist:
✓ CPU usage
✓ Memory usage
✓ Disk I/O
✓ Network connectivity
✓ Application health check
✓ Disk space
✓ Service status
```

**Lesson:** If it's not monitored, it's not in production.

---

## Recovery Anti-Patterns

### ❌ Anti-Pattern: "Rollback Plan? What Rollback Plan?"

**What people do:**
```bash
# Migrate on Friday evening
# Delete VMware VM immediately after migration
# No rollback possible
# "It'll be fine!"
```

**Why it fails:**
```
# Friday 11 PM:
Migration complete!

# Saturday 2 AM:
Application won't start

# Saturday 3 AM:
Can't figure out why

# Saturday 4 AM:
Try to rollback... VMware VM deleted!

# Saturday 5 AM:
Restore from backup (24 hours old)
Lost day of transactions
Weekend ruined
Resume on Monday
```

**✅ Do this instead:**
```bash
# Rollback plan:

# Week 0: Migration
# - Create VMware snapshot
# - Keep VMware VM powered off (don't delete)
# - Run in parallel if possible

# Week 1-2: Validation
# - Monitor KVM VM
# - Compare metrics to baseline
# - User acceptance testing

# Week 3: Confidence building
# - Still can rollback to VMware

# Week 4: Commitment
# - Delete VMware snapshot
# - Delete VMware VM
# - Full commitment to KVM

# If issues at any point:
virsh destroy kvm-vm
govc vm.power -on vmware-vm
# 5-minute rollback
```

**Lesson:** Hope is not a strategy. Planning is.

---

### ❌ Anti-Pattern: "We'll Just Wing the Disaster Recovery Test"

**What people do:**
```bash
# DR Test Day:
# "Uh, where are the runbooks?"
# "How do we start the DR VMs?"
# "What's the admin password again?"
# "Is this the right backup?"
```

**Why it fails:**
```
# DR Test Results:
✗ Runbooks out of date (references deleted VMs)
✗ Passwords in runbooks incorrect (changed 6 months ago)
✗ Backups not tested (last restore test: 2 years ago)
✗ Network configuration wrong (DR IP ranges changed)
✗ DNS not updated (still points to primary)
✗ Certificate expired (no one renewed DR certs)
✗ Total recovery time: 18 hours (RTO: 4 hours)

# Audit finding: FAILED
```

**✅ Do this instead:**
```
# Quarterly DR Testing Schedule:

Q1: Documentation review
- Update all runbooks
- Test restore from backup
- Verify passwords
- Update network diagrams

Q2: Tabletop exercise
- Walk through DR scenario
- Identify gaps
- Update procedures

Q3: Partial failover
- Failover non-production systems
- Validate DR infrastructure
- Measure RTO/RPO

Q4: Full DR test
- Complete failover
- Run production workload in DR
- Measure performance
- Document lessons learned

# Each test: Detailed report + action items
```

**Lesson:** Untested DR is wishful thinking.

---

## Summary: The Golden Rules

1. **Test first, migrate later** - No production migrations without successful test migrations
2. **One change at a time** - Hypervisor OR network OR app config, not all three
3. **Always have a rollback plan** - Keep original VM for 30 days minimum
4. **Document everything** - Use --report flag, future you will thank you
5. **Monitor aggressively** - If you can't see it, you can't fix it
6. **Security is not optional** - SELinux, firewalls, encryption - all required
7. **Performance test before production** - Surprises belong in birthday parties, not production
8. **Backups are mandatory** - If it's not backed up, it doesn't exist
9. **DR is not a nice-to-have** - Test quarterly or fail when it matters
10. **Learn from mistakes** - Post-mortems prevent repeat incidents

---

## Real-World War Stories

### Story #1: The Friday Evening Disaster

**Company:** E-commerce startup (Series B)
**VM:** Payment processing system
**Mistake:** Migrated on Friday 5 PM, deleted VMware VM immediately, went home

**Timeline:**
- Friday 5:30 PM: Migration "complete"
- Friday 11 PM: Payment processing stops working
- Saturday 2 AM: On-call engineer can't fix it
- Saturday 3 AM: Try to rollback... VMware VM deleted!
- Saturday 6 AM: Restore from backup (12 hours old)
- Saturday 8 AM: Recovery complete

**Damage:**
- 14 hours of downtime (Friday evening Black Friday sale)
- $500K in lost sales
- 50,000 abandoned carts
- CTO fired
- Engineering VP resigned

**Lesson:** Never migrate on Friday. Never delete immediately. Always have rollback.

---

### Story #2: The SELinux "Temporary" Disable

**Company:** Healthcare provider
**VM:** Electronic Health Records system
**Mistake:** Disabled SELinux during migration, forgot to re-enable

**Timeline:**
- Month 1: Migration complete, SELinux disabled "temporarily"
- Month 3: Security audit found it disabled, asked to fix
- Month 3: "We'll fix it next quarter" (didn't)
- Month 6: Attacker exploited Apache vulnerability
- Month 6: SELinux would have contained breach, but was disabled
- Month 6: Entire patient database exfiltrated (500K records)

**Damage:**
- $15M HIPAA fine
- $200M class-action lawsuit
- CEO fired
- Company acquired at fire-sale price

**Lesson:** Security shortcuts have expensive consequences.

---

### Story #3: The "We Don't Need Testing" Migration

**Company:** Financial services firm
**VM:** Trading platform
**Mistake:** Migrated straight to production without performance testing

**Timeline:**
- Monday 9 AM: Migration complete, production launch
- Monday 9:30 AM: Market opens, trading starts
- Monday 9:32 AM: System slows to a crawl
- Monday 9:35 AM: Traders can't execute orders
- Monday 9:40 AM: Emergency rollback initiated
- Monday 10:15 AM: Rollback complete

**Damage:**
- 45 minutes of trading outage
- $2M in missed trading opportunities
- SEC investigation (failure to maintain orderly market)
- $500K SEC fine
- Loss of major client ($10M/year revenue)

**Lesson:** Performance testing is not optional for latency-sensitive systems.

---

## Conclusion

**The best way to avoid anti-patterns: Read this document before every migration.**

Print it. Laminate it. Put it on your wall. Make it required reading for your team.

Because the only thing more expensive than doing it right the first time... is doing it wrong, then doing it right.

---

**Questions? Found a new anti-pattern?**
Submit a PR or open an issue: https://github.com/ssahani/hyper2kvm/issues

**Remember:** Every expert was once a beginner who refused to give up. Learn from these mistakes so you don't have to make them yourself.
