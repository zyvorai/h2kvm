# Operational Runbooks

Procedures for handling common operational scenarios in h2kvm migrations.

## Quick Reference

| Runbook | Scenario | Severity | Est. Time |
|---------|----------|----------|-----------|
| [crash-recovery.md](crash-recovery.md) | Worker crash during migration | High | 10-30 min |
| [network-failure.md](network-failure.md) | Network partition during migration | Medium | 5-15 min |
| [storage-failure.md](storage-failure.md) | Storage backend failure | Critical | 15-45 min |
| [partial-migration.md](partial-migration.md) | Incomplete migration recovery | Medium | 20-60 min |
| [upgrade.md](upgrade.md) | Operator/worker upgrade procedure | Low | 15-30 min |

## General Troubleshooting Tools

### System Readiness Check
```bash
./scripts/doctor.sh
```
Validates KVM, QEMU, libvirt, disk space, and all dependencies.

### Debug Bundle Collection
```bash
./scripts/collect-debug-bundle.sh
```
Gathers logs, events, resource states, and metrics into `/tmp/h2kvm-debug-<timestamp>.tar.gz`.

### Health Check
```bash
./scripts/health-check.sh
```
Validates operator, workers, KubeVirt, CDI, and all cluster components.

### Log Locations

**CLI migrations:**
- Migration logs: `/tmp/h2kvm-<random>/migration.log`
- Output directory: Specified via `--output-dir` (default varies)
- Checkpoints: `<output-dir>/checkpoints/`

**Kubernetes migrations:**
- Operator logs: `kubectl logs -n h2kvm-system -l control-plane=controller-manager`
- Worker logs: `kubectl logs -n h2kvm-workers <pod-name>`
- Migration job logs: `kubectl logs -n h2kvm-migration <job-pod>`
- Events: `kubectl get events -n h2kvm-migration --sort-by=.lastTimestamp`

**System paths:**
- State directory: `/var/lib/h2kvm/`
- Temporary workspace: `/tmp/h2kvm-*/`
- NBD devices: `/dev/nbd*`
- Device mapper: `/dev/mapper/`

## Emergency Contacts

| Role | Contact Method | Response Time |
|------|---------------|---------------|
| On-call Engineer | PagerDuty/Slack | 15 minutes |
| Platform Team | Slack #h2kvm-ops | 1 hour |
| Vendor Support | support@example.com | 4 hours |

## Escalation Criteria

**Immediate escalation:**
- Data loss risk (corrupted disks, failed writes)
- Production VM unavailable >1 hour
- Security incident (exposed credentials, unauthorized access)

**Standard escalation:**
- Migration failed after 3 retry attempts
- Unknown error patterns not in runbooks
- Performance degradation affecting multiple migrations
