# Development container for h2kvm
# Based on official Python image with development tools

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Build essentials
    build-essential \
    gcc \
    g++ \
    make \
    pkg-config \
    # Version control
    git \
    git-lfs \
    # libvirt and virtualization
    libvirt-dev \
    libvirt-clients \
    qemu-kvm \
    qemu-utils \
    # NBD
    nbd-client \
    nbd-server \
    # LVM
    lvm2 \
    # Filesystem tools
    e2fsprogs \
    xfsprogs \
    btrfs-progs \
    dosfstools \
    # Cryptography
    libssl-dev \
    libffi-dev \
    cryptsetup \
    # XML/YAML libraries
    libxml2-dev \
    libxslt1-dev \
    libyaml-dev \
    # guestfs dependencies
    guestfs-tools \
    python3-guestfs \
    # Debugging and profiling
    gdb \
    strace \
    ltrace \
    valgrind \
    # Network tools
    curl \
    wget \
    netcat-traditional \
    # Utilities
    sudo \
    vim \
    nano \
    less \
    tree \
    htop \
    jq \
    ripgrep \
    fd-find \
    # Shell
    zsh \
    bash-completion \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Install Python development tools globally
RUN pip install --no-cache-dir --upgrade \
    pip \
    setuptools \
    wheel \
    # Code quality
    ruff \
    mypy \
    pre-commit \
    # Testing
    pytest \
    pytest-cov \
    pytest-xdist \
    pytest-timeout \
    pytest-asyncio \
    pytest-mock \
    # Debugging
    ipdb \
    ipython \
    # Profiling
    memory-profiler \
    line-profiler \
    # Documentation
    sphinx \
    sphinx-rtd-theme \
    # Build tools
    build \
    twine

# Configure git-lfs
RUN git lfs install --system

# Set up libvirt for non-root user
RUN usermod -a -G libvirt,kvm $USERNAME 2>/dev/null || true

# Configure environment
ENV SHELL=/bin/bash
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Set working directory
WORKDIR /workspace

# Switch to non-root user
USER $USERNAME

# Configure git defaults
RUN git config --global init.defaultBranch main \
    && git config --global pull.rebase false \
    && git config --global fetch.prune true

# Set up shell customization
RUN echo 'export PS1="\[\033[01;32m\]\u@devcontainer\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ "' >> ~/.bashrc

# Health check (optional)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python --version || exit 1

# Default command
CMD ["/bin/bash"]
