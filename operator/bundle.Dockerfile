FROM scratch

# Core bundle labels
LABEL operators.operatorframework.io.bundle.mediatype.v1=registry+v1
LABEL operators.operatorframework.io.bundle.manifests.v1=manifests/
LABEL operators.operatorframework.io.bundle.metadata.v1=metadata/
LABEL operators.operatorframework.io.bundle.package.v1=hyperconversion-operator
LABEL operators.operatorframework.io.bundle.channels.v1=stable,alpha
LABEL operators.operatorframework.io.bundle.channel.default.v1=stable
LABEL operators.operatorframework.io.metrics.builder=operator-sdk-v1.34.1
LABEL operators.operatorframework.io.metrics.mediatype.v1=metrics+v1
LABEL operators.operatorframework.io.metrics.project_layout=go.kubebuilder.io/v4

# Labels for testing
LABEL operators.operatorframework.io.test.mediatype.v1=scorecard+v1
LABEL operators.operatorframework.io.test.config.v1=tests/scorecard/

# Multi-architecture support
LABEL operators.operatorframework.io/arch.amd64=supported
LABEL operators.operatorframework.io/arch.arm64=supported
LABEL operators.operatorframework.io/arch.ppc64le=supported
LABEL operators.operatorframework.io/arch.s390x=supported
LABEL operators.operatorframework.io/os.linux=supported

# Copy files to locations specified by labels
COPY bundle/manifests /manifests/
COPY bundle/metadata /metadata/
COPY bundle/tests/scorecard /tests/scorecard/
