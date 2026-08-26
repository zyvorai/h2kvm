# Automation Enhancements

Summary of all automation improvements implemented across the h2kvm project.

## KubeVirt TUI Enhancements (7 features)

New keybindings added to the Kubernetes tab in the standalone TUI (`zkvm`):

| Key | Feature | Description |
|-----|---------|-------------|
| `n` | Context switcher | Cycle through kubeconfig contexts |
| `a` | Namespace filter | Cycle namespace filter (all → ns1 → ns2 → all) |
| `w` | VM creation wizard | Form overlay: name, namespace, image, CPUs, memory |
| `e` | SSH into VM | Native SPDY port-forward + ssh, fallback to virtctl |
| `u` | Upload disk image | CDI upload via virtctl (PVC view) |
| `3` | Migrations view | List/detail VirtualMachineInstanceMigrations |
| — | Live metrics | Guest OS, age, conditions, migration status in details |

Files: `kubernetes.go`, `kubevirt.go`, `kube_client.go`, `standalone.go`, `help.go`

## Project-Wide Automation (37 items)

### Critical

| # | Item | Implementation |
|---|------|----------------|
| 1 | HyperConversion controller | Full lifecycle: Pending→Uploading→Converting→CreatingVM→Ready. CDI DataVolume creation, KubeVirt VM creation, finalizer cleanup, owner references. |
| 2 | Operator log fetching | Real pod log parsing via `clientset.CoreV1().Pods().GetLogs()`. JSON extraction with fallback to defaults. |
| 3 | zkvm Go tests | 87 tests across 4 files: `kubevirt_test.go`, `kubernetes_test.go`, `help_test.go`, `kube_client_test.go` |
| 4 | Webhook handlers | Defaulting: CPU=2, Memory=2Gi, RunStrategy=Always, Compression=zstd, Timeout=60. Validation: URL required, CPU 1-128. |

### High Priority

| # | Item | Implementation |
|---|------|----------------|
| 5 | KubeVirt version | Removed hardcoded `v1.1.0` from `kubernetes.py` |
| 6 | Version management | `make version` target showing all component versions |
| 7 | Webhook cert automation | `make operator-webhook-certs` — auto-detects cert-manager, falls back to openssl script |
| 8 | Deploy automation | Kustomize overlays (dev/production) replace manual steps |
| 9 | VMCraft multi-drive | Documented limitation (existing NotImplementedError) |
| 10 | Veeam extraction | Documented limitation (requires external utility) |
| 11 | Database migrations | MongoDB `fsyncLock/Unlock`, PostgreSQL `CHECKPOINT`, Redis `BGSAVE` with polling |
| 12 | Security scanning | `make security-scan` — bandit + pip-audit + detect-secrets |
| 13 | OVF Tool retries | Default changed 0 → 3 with exponential backoff |

### Medium Priority

| # | Item | Implementation |
|---|------|----------------|
| 14-15 | Documentation build | `make docs` generates CLI reference, `make docs-serve` on port 8080 |
| 16 | Kustomize overlays | `k8s/overlays/dev/` and `k8s/overlays/production/` with resource tuning |
| 17 | PodDisruptionBudget | `k8s/worker/pdb.yaml` — minAvailable=1 |
| 18 | Health probes | `/healthz` + `/readyz` HTTP endpoints in worker engine (port 8081) |
| 19 | HPA | Already existed in `worker-hpa.yaml` |
| 20 | Circuit breaker | `h2kvm/core/circuit_breaker.py` — thread-safe, decorator pattern, global registry |
| 21 | Batch resume | Checkpoint-aware `_process_disks()` + `load_checkpoint()` in orchestrator |
| 22 | TPM flag | `--no-tpm` wired through encryption pipeline |
| 23 | OVMF auto-detect | Searches 5 common paths across Fedora/RHEL/Debian/Ubuntu/Arch |
| 24 | User config | `~/.config/h2kvm/config.yaml` via XDG_CONFIG_HOME |
| 25 | Operator tests | 3 HyperConversion tests: pending, ready, deletion |
| 26 | Changelog | `make changelog` from git commits |
| 27 | RBAC expansion | Added hyperconversions, datavolumes, configmaps, secrets |

### Low Priority

| # | Item | Implementation |
|---|------|----------------|
| 28 | SBOM | `make sbom` — CycloneDX generation |
| 29-30 | Image signing | Documented for CI integration |
| 31 | Ingress example | `k8s/examples/ingress.yaml` — nginx ingress for worker API |
| 32-33 | Config backup | `h2kvm/core/config_backup.py` — backup/restore/list |
| 34 | Daemon health | HTTP `/healthz` + `/readyz` on configurable port |
| 35 | CLI docs | `make docs` generates from argparse |
| 36 | License compliance | `make license-check` — REUSE lint |
| 37 | Example validation | `make validate-examples` — YAML syntax check |

## New Makefile Targets

```bash
# Documentation
make docs              # Build CLI reference documentation
make docs-serve        # Serve docs on localhost:8080

# Security & Compliance
make security-scan     # Run bandit + pip-audit + detect-secrets
make sbom              # Generate CycloneDX SBOM
make license-check     # REUSE license compliance

# Release
make changelog         # Generate changelog from git commits
make version           # Show all component versions
make validate-examples # Validate example YAML/JSON configs

# Lifecycle
make preflight         # Pre-flight cluster readiness check
make preflight-fix     # Pre-flight check with auto-fix
make health            # Full-stack health check (all components)
make debug-bundle      # Collect debug bundle for troubleshooting

# Uninstall
make uninstall            # Remove all h2kvm components
make uninstall-operator   # Remove operator only
make uninstall-workers    # Remove workers only
make uninstall-migrations # Remove migration resources only
make uninstall-all        # Remove h2kvm + KubeVirt + CDI
make uninstall-k3d        # Delete entire k3d cluster

# Backup
make backup-operator   # Backup operator state before upgrade
make backup-workers    # Backup worker state

# Operator
make operator-webhook-certs  # cert-manager or manual cert generation
make lint-all                # ruff + mypy + go vet + shellcheck
```

## New Files Created

### Go (operator + TUI)

| File | Purpose |
|------|---------|
| `operator/controllers/hyperconversion_controller.go` | HyperConversion reconciler (880 lines) |
| `operator/controllers/hyperconversion_controller_test.go` | Controller tests (Ginkgo v2) |
| `operator/api/v1alpha1/hyperconversion_webhook.go` | Defaulting + validation webhooks |
| `zkvm/internal/ui/standalone/kubevirt_test.go` | KubeVirt types tests |
| `zkvm/internal/ui/standalone/kubernetes_test.go` | Kubernetes model tests |
| `zkvm/internal/ui/standalone/help_test.go` | Help overlay tests |
| `zkvm/internal/ui/standalone/kube_client_test.go` | Client utility tests |

### Python

| File | Purpose |
|------|---------|
| `h2kvm/core/circuit_breaker.py` | Thread-safe circuit breaker with decorator |
| `h2kvm/core/config_backup.py` | Config backup/restore utility |

### Kubernetes manifests

| File | Purpose |
|------|---------|
| `k8s/migration/rhel88-k3s-migration.yaml` | In-cluster Job migration (all-in-one) |
| `k8s/operator-deploy/deploy-operator-migrate.yaml` | Operator + HC CR deployment |
| `k8s/base/kustomization.yaml` | Base Kustomize config |
| `k8s/worker/kustomization.yaml` | Worker Kustomize config |
| `k8s/worker/pdb.yaml` | PodDisruptionBudget |
| `k8s/overlays/dev/kustomization.yaml` | Dev overlay (reduced resources) |
| `k8s/overlays/production/kustomization.yaml` | Production overlay (high resources) |
| `k8s/examples/ingress.yaml` | Ingress for worker API |

### Scripts

| File | Purpose |
|------|---------|
| `scripts/run-k8s-migration.sh` | One-shot in-cluster migration automation |
| `scripts/preflight-check.sh` | Cluster readiness validation (tools, K8s, KubeVirt, CDI, storage, RBAC) |
| `scripts/uninstall.sh` | Component removal (operator, workers, migrations, KubeVirt, CDI, k3d) |
| `scripts/health-check.sh` | Full-stack health check (cluster, operator, workers, VMs, storage) |
| `scripts/collect-debug-bundle.sh` | Debug bundle collection (logs, events, resources, metrics) |
| `scripts/ops/backup-operator-state.sh` | Operator state backup (CRDs, CRs, RBAC, webhooks, config) |

## Modified Files

### Python fixes

| File | Change |
|------|--------|
| `h2kvm/cli/args/groups.py` | OVF retry 0→3, OVMF auto-detect |
| `h2kvm/cli/system_config.py` | User-level config path support |
| `h2kvm/infrastructure/deployers/kubernetes.py` | Remove hardcoded KubeVirt version |
| `h2kvm/libvirt/domain_emitter.py` | OVMF auto-detection across distros |
| `h2kvm/orchestration/orchestrator.py` | Batch checkpoint/resume |
| `h2kvm/pipeline/cli.py` | Wire --no-tpm flag |
| `h2kvm/pipeline/vmware_to_luks_tpm.py` | Skip TPM enrollment when --no-tpm |
| `h2kvm/runtime/worker/engine.py` | HTTP health server |
| `h2kvm/database_migration/mongodb.py` | Real fsyncLock/Unlock implementation |
| `h2kvm/database_migration/postgresql.py` | Real CHECKPOINT implementation |
| `h2kvm/database_migration/redis.py` | Real BGSAVE with polling |

### Go fixes

| File | Change |
|------|--------|
| `operator/cmd/main.go` | Register HyperConversion controller + v1alpha1 scheme |
| `operator/controllers/validation_controller.go` | Pass clientset for log fetching |
| `operator/controllers/suite_test.go` | Register HC controller in test suite |
| `operator/pkg/validation/results.go` | Real pod log fetching via client-go |
| `operator/config/rbac/role.yaml` | Expanded RBAC rules |
| `operator/Dockerfile` | Go 1.23→1.25 |

## Commit History

```
ac3ed6d feat: operator-driven migration — deploy operator, HyperConversion CR auto-creates KubeVirt VM
6f59732 feat: add one-shot in-cluster RHEL 8.8 migration YAML + automation script
cf983df feat: automate 37 gaps — operator controller, tests, resilience, K8s hardening, tooling
baf963e feat: add 7 KubeVirt TUI enhancements — context switcher, namespace filter, VM wizard, live metrics, PVC upload, migrations view, SSH
```
