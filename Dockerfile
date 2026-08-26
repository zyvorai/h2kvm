# Multi-stage Dockerfile for hyper2kvm
# Supports both development and production builds

# Stage 1: Base image with system dependencies
FROM fedora:43 AS base

LABEL maintainer="ZyvorAI Labs Private Limited <ssahani@zyvor.dev>"
LABEL description="hyper2kvm - Hypervisor to KVM/QEMU Migration Toolkit"
LABEL org.opencontainers.image.source="https://github.com/ssahani/hyper2kvm"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Install system dependencies
RUN dnf update -y && \
    dnf install -y \
        python3 \
        python3-pip \
        python3-devel \
        qemu-img \
        qemu-system-x86 \
        libvirt-daemon \
        libvirt-client \
        openssh-clients \
        git \
        make \
        sudo \
    && dnf clean all

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Stage 2: Development image
FROM base AS development

# Install development tools
RUN pip install --no-cache-dir \
    hatch \
    pre-commit \
    ipython

# Copy project files
COPY . /app/

# Install hyper2kvm in development mode
RUN pip install -e .[dev,full]

# Install pre-commit hooks
RUN git init . && pre-commit install-hooks || true

# Default command for development
CMD ["/bin/bash"]

# Stage 3: Builder for production
FROM base AS builder

# Copy only necessary files for building
COPY pyproject.toml README.md LICENSE ./
COPY hyper2kvm/ ./hyper2kvm/

# Install build dependencies and build wheel
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Stage 4: Base runtime (shared by all specialized images)
FROM base AS base-runtime

# Copy only the built wheel from builder
COPY --from=builder /app/dist/*.whl /tmp/

# Install minimal runtime dependencies
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Create non-root user and directories
RUN useradd -m -u 1000 -s /bin/bash hyper2kvm && \
    mkdir -p /data /output /var/lib/hyper2kvm /var/log/hyper2kvm /etc/hyper2kvm && \
    chown -R hyper2kvm:hyper2kvm /data /output /var/lib/hyper2kvm /var/log/hyper2kvm

# Copy entrypoint wrapper
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /data

# Stage 5: CLI Container (optimized for one-shot migrations)
FROM base-runtime AS cli

# Install CLI-specific minimal dependencies (no Azure/vSphere SDKs)
RUN pip install --no-cache-dir \
    click \
    PyYAML \
    argcomplete \
    rich \
    pydantic

USER hyper2kvm

# Health check for CLI
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import hyper2kvm; print(hyper2kvm.__version__)" || exit 1

ENV HYPER2KVM_MODE=cli
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["--help"]

# Stage 6: Daemon Container (optimized for long-running file watching)
FROM base-runtime AS daemon

# Install daemon-specific dependencies
RUN dnf install -y inotify-tools && dnf clean all && \
    pip install --no-cache-dir \
    watchdog \
    tenacity

USER hyper2kvm

# Create daemon PID file directory
RUN mkdir -p /var/lib/hyper2kvm/queue

# Health check for daemon (checks if daemon process is running)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pgrep -f "hyper2kvm.*daemon" > /dev/null || exit 1

ENV HYPER2KVM_MODE=daemon
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Stage 7: Batch Container (optimized for parallel processing)
FROM base-runtime AS batch

# Install batch-specific dependencies
RUN pip install --no-cache-dir \
    httpx \
    tenacity

USER hyper2kvm

# Health check for batch
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 -c "import hyper2kvm; print('Ready')" || exit 1

ENV HYPER2KVM_MODE=batch
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Stage 8: TUI Container (interactive terminal UI)
FROM base-runtime AS tui

# Install TUI-specific dependencies
RUN pip install --no-cache-dir \
    textual[dev]

USER hyper2kvm

# No health check for TUI (interactive mode)
ENV HYPER2KVM_MODE=tui
ENV TERM=xterm-256color
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Stage 9: Worker Container (Worker Job Protocol daemon)
FROM base-runtime AS worker

# Install worker-specific system tools for offline fixes
# Required for NBD partition detection and LVM operations
RUN dnf install -y \
    parted \
    kpartx \
    lvm2 \
    && dnf clean all

# Install worker-specific dependencies
# Note: Adding minimal dependencies to avoid importing full hyper2kvm with Azure/vSphere
RUN pip install --no-cache-dir \
    click \
    rich \
    pydantic \
    watchdog \
    tenacity \
    requests \
    httpx \
    psutil \
    prometheus-client

# Worker requires some privileged operations via sudo (restricted to specific commands)
RUN echo "hyper2kvm ALL=(ALL) NOPASSWD: /usr/bin/qemu-nbd, /usr/sbin/modprobe, /usr/bin/qemu-system-x86_64, /usr/libexec/qemu-kvm, /usr/local/sbin/h2kvmctl, /usr/bin/virsh, /usr/sbin/kpartx, /usr/bin/mount, /usr/bin/umount, /usr/sbin/blkid, /usr/sbin/losetup" > /etc/sudoers.d/hyper2kvm && \
    chmod 0440 /etc/sudoers.d/hyper2kvm

USER hyper2kvm

# Create worker directories
RUN mkdir -p \
    /var/lib/hyper2kvm/jobs \
    /var/lib/hyper2kvm/events \
    /var/lib/hyper2kvm/queue

# Health check for worker (checks if worker daemon is running)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -m hyper2kvm.worker.cli capabilities --json-output > /dev/null || exit 1

ENV HYPER2KVM_MODE=worker
ENV HYPER2KVM_STATE_DIR=/var/lib/hyper2kvm/jobs
ENV HYPER2KVM_EVENT_DIR=/var/lib/hyper2kvm/events
ENV HYPER2KVM_QUEUE_DIR=/var/lib/hyper2kvm/queue

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD []

# Stage 10: Operator Container (Kubernetes Operator)
FROM base-runtime AS operator

# Install operator-specific dependencies
RUN pip install --no-cache-dir \
    kopf \
    kubernetes \
    click \
    rich \
    pydantic \
    requests

USER hyper2kvm

# Create operator directories
RUN mkdir -p /var/lib/hyper2kvm/operator

# Health check for operator
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

ENV HYPER2KVM_MODE=operator
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "-m", "hyper2kvm.operator.cli"]

# Stage 11: Production image (full-featured, backwards compatible)
FROM base AS production

# Copy only the built wheel from builder
COPY --from=builder /app/dist/*.whl /tmp/

# Install the wheel with full dependencies
RUN WHEEL=$(ls /tmp/*.whl) && \
    pip install --no-cache-dir "$WHEEL[full]" && \
    rm -rf /tmp/*.whl

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash hyper2kvm && \
    mkdir -p /data /output && \
    chown -R hyper2kvm:hyper2kvm /data /output && \
    echo "hyper2kvm ALL=(ALL) NOPASSWD: /usr/bin/qemu-nbd, /usr/sbin/modprobe, /usr/bin/qemu-system-x86_64, /usr/libexec/qemu-kvm, /usr/local/sbin/h2kvmctl, /usr/bin/virsh, /usr/sbin/kpartx, /usr/bin/mount, /usr/bin/umount, /usr/sbin/blkid, /usr/sbin/losetup" > /etc/sudoers.d/hyper2kvm && \
    chmod 0440 /etc/sudoers.d/hyper2kvm

USER hyper2kvm
WORKDIR /data

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import hyper2kvm; print(hyper2kvm.__version__)" || exit 1

# Default command shows help
ENTRYPOINT ["h2kvmctl"]
CMD ["--help"]

# Stage 5: Testing image
FROM development AS testing

# Run tests during build (optional, comment out for faster builds)
# RUN hatch run test

# Default command runs tests
CMD ["hatch", "run", "ci"]
