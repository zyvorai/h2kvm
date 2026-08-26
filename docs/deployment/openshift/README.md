# OpenShift Deployment

OpenShift-specific deployment documentation for H2KVM.

---

## OpenShift Documentation

- **[OpenShift Quickstart](OPENSHIFT_QUICKSTART.md)** - Deploy on OpenShift in 5 minutes

---

## Quick Start

### Deploy Operator
```bash
# Install via OperatorHub
oc apply -f operator-subscription.yaml

# Or deploy manually
oc apply -f operator.yaml
```

### Create Migration Job
```bash
oc apply -f migrationjob.yaml
```

---

## OpenShift Features

- **OperatorHub Integration** - Install via OpenShift OperatorHub
- **SCCs (Security Context Constraints)** - Proper privilege handling
- **Routes** - Automatic ingress creation
- **Image Streams** - Automated image updates
- **Templates** - Reusable deployment templates

---

## Related Documentation

- **[OpenShift Deployment Guide](../openshift-deployment-guide.md)** - Complete guide
- **[OpenShift Features](../OPENSHIFT_FEATURES_SUMMARY.md)** - Feature summary
- **[OpenShift Test Results](../../test-results/OPENSHIFT_TEST_SUMMARY.md)** - Testing results
- **[Kubernetes Integration](../KUBERNETES_INTEGRATION.md)** - General K8s docs

---

**Last Updated**: March 2026
