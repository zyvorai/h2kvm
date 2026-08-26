# hyper2kvm- User Stories

**Product:** Enterprise VM migration — any hypervisor to KVM

Cross-reference: [Documentation index](README.md) · [Main README](../README.md)

## Personas

| Persona | Name | Focus |
|---------|------|-------|
| Migration Engineer | Alex | VMware/Hyper-V to KVM pipelines |
| Windows Admin | Morgan | Win10/11 migration with driver fixes |
| K8s Platform | Jordan | Libvirt-to-KubeVirt migration |

---

### Story 1 — Migrate VMware VM to KVM

**As Alex** (Migration Engineer), I want export, convert, and deploy vm with offline guest fixes, **so that** I deliver reliable outcomes.

| Criterion | Notes |
|-----------|-------|
| Core capability | h2kvmctl, offline fixes, 8 input formats |

---

### Story 2 — Web dashboard migration

**As Alex** (Migration Engineer), I want run migration pipeline from h2kweb with progress tracking, **so that** I deliver reliable outcomes.

| Criterion | Notes |
|-----------|-------|
| Core capability | h2kweb, 480+ APIs, webhooks |

---

### Story 3 — Libvirt to KubeVirt

**As Jordan** (K8s Platform), I want one-click migrate running libvirt vm to kubevirt cr, **so that** I deliver reliable outcomes.

| Criterion | Notes |
|-----------|-------|
| Core capability | POST migrate-to-kubevirt, PVC upload |

---

### Story 4 — Auto disk cleanup

**As Morgan** (Windows Admin), I want reclaim space when conversion artifacts fill disk, **so that** I deliver reliable outcomes.

| Criterion | Notes |
|-----------|-------|
| Core capability | cleanup API, threshold settings |

---

### Story 5 — K8s operator deploy

**As Jordan** (K8s Platform), I want run hyper2kvm as in-cluster operator, **so that** I deliver reliable outcomes.

| Criterion | Notes |
|-----------|-------|
| Core capability | operator/, Helm, OLM |

---

## Validation

Map each story to smoke tests, CI jobs, or manual lab steps before marking production-ready.
