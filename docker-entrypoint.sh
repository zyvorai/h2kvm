#!/bin/bash
# Docker entrypoint wrapper for h2kvm
# Supports multiple execution modes via H2KVM_MODE environment variable

set -eo pipefail

# Function to log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

# Handle different execution modes
case "${H2KVM_MODE:-cli}" in
  cli)
    log "Starting h2kvm in CLI mode"
    exec h2kvmctl "$@"
    ;;

  daemon)
    log "Starting h2kvm in Daemon mode"
    # Ensure daemon config exists
    DAEMON_CONFIG="${H2KVM_DAEMON_CONFIG:-/etc/h2kvm/daemon.yaml}"
    if [ ! -f "$DAEMON_CONFIG" ]; then
        log "ERROR: Daemon config not found at $DAEMON_CONFIG"
        exit 1
    fi
    exec h2kvmctl daemon --config "$DAEMON_CONFIG"
    ;;

  batch)
    log "Starting h2kvm in Batch mode"
    # Ensure batch config exists
    if [ ! -f /etc/h2kvm/batch.yaml ]; then
        log "ERROR: Batch config not found at /etc/h2kvm/batch.yaml"
        exit 1
    fi
    exec h2kvmctl --config /etc/h2kvm/batch.yaml
    ;;

  tui)
    log "Starting h2kvm in TUI mode"
    exec zkvm
    ;;

  worker)
    log "Starting h2kvm in Worker mode"
    # Create health check PID file
    mkdir -p /var/lib/h2kvm
    echo $$ > /var/lib/h2kvm/worker.pid

    # Set worker ID from environment or hostname
    WORKER_ID="${WORKER_ID:-$(hostname)}"
    log "Worker ID: ${WORKER_ID}"

    # If no args provided, start worker daemon listening for jobs
    if [ $# -eq 0 ]; then
      log "Starting worker daemon (waiting for jobs)"
      log "Worker capabilities:"
      python3 -m h2kvm.worker.cli capabilities || log "Capability detection failed (expected in k3d)"

      log "Worker ready and waiting for job submissions"
      log "Submit jobs using: kubectl exec ... -- python3 -m h2kvm.worker.cli run /path/to/job.json"

      # Trap SIGTERM/SIGINT for graceful container shutdown
      trap 'exit 0' SIGTERM SIGINT

      # Keep container alive - in production this would poll a queue
      # For now, just sleep indefinitely and keep the worker.pid file updated
      while true; do
        echo $$ > /var/lib/h2kvm/worker.pid
        sleep 60
      done
    else
      # Direct job execution mode
      log "Executing job: $*"
      exec python3 -m h2kvm.worker.cli "$@" --worker-id "${WORKER_ID}"
    fi
    ;;

  *)
    log "Unknown H2KVM_MODE: ${H2KVM_MODE}, defaulting to CLI"
    exec h2kvmctl "$@"
    ;;
esac
