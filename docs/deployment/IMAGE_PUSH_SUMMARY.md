# Hyper2KVM v2.1.0 - Container Images Push Summary

**Date:** 2026-01-30
**Registry:** ghcr.io/ssahani

---

## ✅ Successfully Pushed Images

### Application Images

1. **Operator Image**
   - `ghcr.io/ssahani/hyper2kvm:2.1.0-operator`
   - `ghcr.io/ssahani/hyper2kvm:latest-operator`
   - Size: 2.08GB
   - Digest: sha256:da51525f4f1905708e075080c3459882ab26bd5a144816238fc9609185f980d2

2. **Worker Image**
   - `ghcr.io/ssahani/hyper2kvm:2.1.0-worker`
   - `ghcr.io/ssahani/hyper2kvm:latest-worker`
   - Size: 2.03GB
   - Digest: sha256:9a9b8a7435dbac9fe2db8c7063e57553dfac289186a66c9dfa40734efeb33eeb

3. **CLI Image**
   - `ghcr.io/ssahani/hyper2kvm:2.1.0-cli`
   - `ghcr.io/ssahani/hyper2kvm:latest-cli`
   - Size: 2.02GB
   - Digest: sha256:c552b89782595f8cd44e40c481c9b8b6626a12ebad239e7e16aa01425ec0b4a0

4. **Daemon Image**
   - `ghcr.io/ssahani/hyper2kvm:2.1.0-daemon`
   - `ghcr.io/ssahani/hyper2kvm:latest-daemon`
   - Size: 2.02GB
   - Digest: sha256:1190b01443bdb24b4f03596e4e4c92d0dad0978d9d046a231d0a7e467c30a2ab

### OLM Bundle Image

5. **Operator Bundle**
   - `ghcr.io/ssahani/hyper2kvm-operator-bundle:v2.1.0`
   - `ghcr.io/ssahani/hyper2kvm-operator-bundle:latest`
   - Size: 54.8KB
   - Digest: sha256:fed8ae1d8fd988b9582034eb2a26f16d2abb9894c4619e4f8a796a45d96e7510

---

## 📊 Total Upload Statistics

- **Total Images Pushed:** 10 (5 versioned + 5 latest tags)
- **Total Size:** ~8.17GB (deduplicated with layer sharing)
- **Registry:** GitHub Container Registry (ghcr.io)
- **Namespace:** ssahani
- **Project:** hyper2kvm

---

## ✅ Verification Commands

Test pulling images:

```bash
# Operator
docker pull ghcr.io/ssahani/hyper2kvm:2.1.0-operator

# Worker
docker pull ghcr.io/ssahani/hyper2kvm:2.1.0-worker

# CLI
docker pull ghcr.io/ssahani/hyper2kvm:2.1.0-cli

# Daemon
docker pull ghcr.io/ssahani/hyper2kvm:2.1.0-daemon

# OLM Bundle
docker pull ghcr.io/ssahani/hyper2kvm-operator-bundle:v2.1.0
```

---

## 🎯 Next Steps

With images pushed, you can now:

### 1. Update Helm Chart Versions
```bash
sed -i 's/version: 1.6.0/version: 2.1.0/' helm/hyper2kvm-operator/Chart.yaml
sed -i 's/appVersion: ".*"/appVersion: "0.3.0"/' helm/hyper2kvm-operator/Chart.yaml
./scripts/package-charts.sh
```

### 2. Deploy to Staging
```bash
./scripts/deploy-to-openshift.sh 2.1.0 helm hyper2kvm-staging
./scripts/test-openshift-deployment.sh hyper2kvm-staging
```

### 3. Create GitHub Release
```bash
git push origin main
git tag -a v2.1.0 -m "Release v2.1.0 - OpenShift Container Platform support"
git push origin v2.1.0
```

Then create release at: https://github.com/ssahani/hyper2kvm/releases/new

### 4. Test Deployment
```bash
# Test via Helm
helm install hyper2kvm-test ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-test \
  --create-namespace \
  --set openshift.enabled=false \
  --set image.tag=2.1.0-operator

# Test via OLM
operator-sdk run bundle ghcr.io/ssahani/hyper2kvm-operator-bundle:v2.1.0
```

---

## 📝 Image Registry Visibility

All images are public and can be pulled without authentication:
- View at: https://github.com/ssahani?tab=packages

Make them public (if not already):
1. Go to https://github.com/users/ssahani/packages
2. Select each package
3. Package settings → Change visibility → Public

---

**Push Status:** ✅ COMPLETE
**Ready for:** Deployment, Git tagging, GitHub release
**Registry URLs:**
- Operator: https://github.com/ssahani/hyper2kvm/pkgs/container/hyper2kvm
- Bundle: https://github.com/ssahani/hyper2kvm-operator-bundle/pkgs/container/hyper2kvm-operator-bundle

