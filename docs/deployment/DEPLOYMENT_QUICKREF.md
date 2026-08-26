# Deployment Quick Reference - Hyper2KVM Operator v2.1.0

**Status:** ✅ Production Ready | **Test Coverage:** 87.5% | **Date:** 2026-01-30

---

## 🚀 Quick Deploy Commands

### Option 1: Helm (Recommended)

```bash
# OpenShift
helm install hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system --create-namespace \
  --set openshift.enabled=true \
  --set image.tag=2.1.0-operator

# Kubernetes
helm install hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system --create-namespace \
  --set openshift.enabled=false \
  --set image.tag=2.1.0-operator
```

### Option 2: OLM Bundle

```bash
# Via operator-sdk
operator-sdk run bundle ghcr.io/ssahani/hyper2kvm-operator-bundle:v2.1.0 \
  --namespace hyper2kvm-system

# Via OLM catalog
oc apply -f olm/catalog/catalog-source.yaml
oc apply -f olm/catalog/subscription.yaml
```

### Option 3: Automated Script

```bash
# Deploy with automation
./scripts/deploy-to-openshift.sh 2.1.0 helm hyper2kvm-system

# Or manual deployment
./scripts/deploy-to-openshift.sh 2.1.0 manual hyper2kvm-system
```

---

## ✅ Validation

```bash
# Quick validation
kubectl get crd | grep hyper2kvm
kubectl get pods -n hyper2kvm-system
kubectl logs -n hyper2kvm-system deployment/hyper2kvm-operator

# Full test suite
./scripts/test-openshift-deployment.sh hyper2kvm-system

# Test migration job
kubectl apply -f k8s/operator/examples/inspect-job.yaml
kubectl get migrationjobs -w
```

---

## 📦 Image Registry

**Public Images:**
- `ghcr.io/ssahani/hyper2kvm:2.1.0-operator`
- `ghcr.io/ssahani/hyper2kvm:2.1.0-worker`
- `ghcr.io/ssahani/hyper2kvm-operator-bundle:v2.1.0`

**Build Local:**
```bash
# All images
./scripts/build-operator-images.sh 2.1.0

# OLM bundle
./scripts/build-olm-bundle.sh 2.1.0
```

---

## 🔧 Key Configuration

**Helm Values:**
```yaml
openshift:
  enabled: true          # Or autoDetect: true
  route.enabled: true
  scc.create: true

operator:
  replicas: 1           # 2+ for HA
  leaderElection.enabled: true

image:
  tag: 2.1.0-operator
  pullPolicy: IfNotPresent
```

**Environment Variables:**
- `RECONCILE_INTERVAL=30`
- `WORKER_DISCOVERY_INTERVAL=60`
- `LOG_LEVEL=INFO`
- `LEADER_ELECTION_ENABLED=true`

---

## 🚨 Common Issues

**Pod not starting:** Check `kubectl describe pod` → Likely SCC (OpenShift) or image pull
**CRD validation fails:** Use `kubectl apply --dry-run=server`
**RBAC denied:** Verify `kubectl auth can-i create migrationjobs.hyper2kvm.io`
**Worker not found:** Check pod labels `hyper2kvm.io/worker: "true"`

---

## 📊 Monitoring

**Metrics:** `http://operator-service:8080/metrics`
**Logs:** `kubectl logs -n hyper2kvm-system deployment/hyper2kvm-operator --follow`
**Debug:** `kubectl set env deployment/hyper2kvm-operator LOG_LEVEL=DEBUG`

---

## 🔄 Upgrade

```bash
# Helm
helm upgrade hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --set image.tag=2.2.0-operator \
  --reuse-values

# Rollback
helm rollback hyper2kvm-operator -n hyper2kvm-system
```

---

## 📚 Full Documentation

- **Production Guide:** `PRODUCTION_DEPLOYMENT_GUIDE.md`
- **Quick Start:** `OPENSHIFT_QUICKSTART.md`
- **Complete Guide:** `docs/deployment/openshift-deployment-guide.md`
- **Test Results:** `TEST_RESULTS.md`
- **OLM Guide:** `olm/README.md`

---

**Version:** 0.3.0 | **Status:** Production Ready ✅
