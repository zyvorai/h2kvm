# images/offline-fix-vm/Dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    qemu-utils \
    lvm2 \
    xfsprogs \
    e2fsprogs \
    btrfs-progs \
    grub-common \
    grub2-common \
    dracut-core \
    systemd \
    jq \
    curl \
    kmod \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    pydantic==2.5.0 \
    pyyaml==6.0.1

# Create app directory
RUN mkdir -p /opt/offline-fix

# Copy fixer code from Phase 3
COPY hyper2kvm/fixers/offline_vm/*.py /opt/offline-fix/fixers/
COPY hyper2kvm/worker/offline_fix_contract.py /opt/offline-fix/contract.py

# Copy VM worker and entrypoint
COPY images/offline-fix-vm/worker.py /opt/offline-fix/worker.py
COPY images/offline-fix-vm/entrypoint.sh /opt/offline-fix/entrypoint.sh

RUN chmod +x /opt/offline-fix/entrypoint.sh

# Create directories for config and output
RUN mkdir -p /config /output /vmroot

WORKDIR /opt/offline-fix

ENTRYPOINT ["/opt/offline-fix/entrypoint.sh"]
