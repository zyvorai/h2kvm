# hyper2kvm Worker Job Protocol - REST API Server
# Multi-stage build for minimal production image

# ============================================================================
# Stage 1: Build stage
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-api.txt ./

# Install Python dependencies to a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

# ============================================================================
# Stage 2: Runtime stage
# ============================================================================
FROM python:3.11-slim

# Metadata
LABEL org.opencontainers.image.title="hyper2kvm Worker API" \
      org.opencontainers.image.description="REST API for hyper2kvm Worker Job Protocol" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="hyper2kvm" \
      org.opencontainers.image.source="https://github.com/ssahani/hyper2kvm"

# Create non-root user
RUN groupadd -r hyper2kvm && useradd -r -g hyper2kvm -u 1000 hyper2kvm

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY hyper2kvm/ ./hyper2kvm/
COPY examples/ ./examples/

# Create directories for state persistence
RUN mkdir -p /var/lib/hyper2kvm/jobs /var/lib/hyper2kvm/events /var/lib/hyper2kvm/queue && \
    chown -R hyper2kvm:hyper2kvm /var/lib/hyper2kvm

# Switch to non-root user
USER hyper2kvm

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run API server
CMD ["uvicorn", "hyper2kvm.worker.api:app", "--host", "0.0.0.0", "--port", "8000"]
