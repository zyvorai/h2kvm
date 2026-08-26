FROM scratch

# Core bundle labels
LABEL operators.operatorframework.io.bundle.mediatype.v1=registry+v1
LABEL operators.operatorframework.io.bundle.manifests.v1=manifests/
LABEL operators.operatorframework.io.bundle.metadata.v1=metadata/
LABEL operators.operatorframework.io.bundle.package.v1=hyper2kvm-operator
LABEL operators.operatorframework.io.bundle.channels.v1=stable,preview
LABEL operators.operatorframework.io.bundle.channel.default.v1=stable
LABEL operators.operatorframework.io.metrics.builder=operator-sdk-v1.34.0
LABEL operators.operatorframework.io.metrics.mediatype.v1=metrics+v1
LABEL operators.operatorframework.io.metrics.project_layout=go.kubebuilder.io/v3

# OpenShift version compatibility
LABEL com.redhat.openshift.versions="v4.10-v4.16"

# Disconnected/air-gapped support
LABEL operators.operatorframework.io.bundle.disconnected=true

# Container image
LABEL operators.operatorframework.io.bundle.container-image=ghcr.io/ssahani/hyper2kvm-operator-bundle:v2.0.0

# Copy bundle files
COPY bundle/manifests /manifests/
COPY bundle/metadata /metadata/
COPY bundle/tests/scorecard /tests/scorecard/
