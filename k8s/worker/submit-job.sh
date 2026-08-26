#!/bin/bash
# Helper script to submit jobs to hyper2kvm workers

set -e

NAMESPACE="${NAMESPACE:-hyper2kvm-workers}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

usage() {
    cat << USAGE
Submit a job to hyper2kvm Worker Job Protocol

Usage: $0 [OPTIONS] <job-spec.json>

Options:
  -n, --namespace NAMESPACE    Kubernetes namespace (default: hyper2kvm-workers)
  -k, --kubeconfig PATH        Path to kubeconfig (default: ~/.kube/config)
  -f, --follow                 Follow job execution logs
  -w, --worker POD_NAME        Submit to specific worker pod
  -h, --help                   Show this help message

Examples:
  # Submit job and follow progress
  $0 --follow convert-job.json

  # Submit to specific worker
  $0 --worker hyper2kvm-worker-abc123 inspect-job.json

  # Use custom namespace
  $0 --namespace my-namespace job.json
USAGE
    exit 1
}

# Parse arguments
FOLLOW=false
WORKER_POD=""
JOB_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -k|--kubeconfig)
            KUBECONFIG="$2"
            shift 2
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -w|--worker)
            WORKER_POD="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Unknown option: $1"
            usage
            ;;
        *)
            JOB_FILE="$1"
            shift
            ;;
    esac
done

# Validate job file
if [ -z "$JOB_FILE" ]; then
    echo "ERROR: Job file not specified"
    usage
fi

if [ ! -f "$JOB_FILE" ]; then
    echo "ERROR: Job file not found: $JOB_FILE"
    exit 1
fi

# Extract job ID from job spec
JOB_ID=$(jq -r .job_id "$JOB_FILE" 2>/dev/null || grep -o '"job_id"[[:space:]]*:[[:space:]]*"[^"]*"' "$JOB_FILE" | cut -d'"' -f4)
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Could not extract job_id from job spec"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Submitting Job: $JOB_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create ConfigMap with job spec
echo "Creating job specification ConfigMap..."
kubectl --kubeconfig="$KUBECONFIG" create configmap "hyper2kvm-job-$JOB_ID" \
    --from-file=job-spec.json="$JOB_FILE" \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml | kubectl --kubeconfig="$KUBECONFIG" apply -f -

echo "✓ Job specification uploaded"
echo ""

# Find worker pod if not specified
if [ -z "$WORKER_POD" ]; then
    echo "Finding available worker pod..."
    WORKER_POD=$(kubectl --kubeconfig="$KUBECONFIG" get pods \
        --namespace="$NAMESPACE" \
        -l app=hyper2kvm-worker \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$WORKER_POD" ]; then
        echo "ERROR: No worker pods found"
        exit 1
    fi
    
    echo "✓ Using worker: $WORKER_POD"
else
    echo "Using specified worker: $WORKER_POD"
fi
echo ""

# Copy job spec into pod
echo "Copying job specification to worker..."
kubectl --kubeconfig="$KUBECONFIG" cp \
    "$JOB_FILE" \
    "$NAMESPACE/$WORKER_POD:/var/lib/hyper2kvm/job-$JOB_ID.json"

echo "✓ Job specification ready"
echo ""

# Execute job
echo "Executing job..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$FOLLOW" = true ]; then
    # Run job and follow logs
    kubectl --kubeconfig="$KUBECONFIG" exec \
        --namespace="$NAMESPACE" \
        "$WORKER_POD" -- \
        python3 -m hyper2kvm.worker.cli run \
        "/var/lib/hyper2kvm/job-$JOB_ID.json" \
        --worker-id "$WORKER_POD" \
        --follow
else
    # Run job in background
    kubectl --kubeconfig="$KUBECONFIG" exec \
        --namespace="$NAMESPACE" \
        "$WORKER_POD" -- \
        python3 -m hyper2kvm.worker.cli run \
        "/var/lib/hyper2kvm/job-$JOB_ID.json" \
        --worker-id "$WORKER_POD" &
    
    JOB_PID=$!
    echo ""
    echo "Job submitted in background (PID: $JOB_PID)"
    echo ""
    echo "To check status:"
    echo "  kubectl exec -n $NAMESPACE $WORKER_POD -- \\"
    echo "    python3 -m hyper2kvm.worker.cli status $JOB_ID"
    echo ""
    echo "To view events:"
    echo "  kubectl exec -n $NAMESPACE $WORKER_POD -- \\"
    echo "    python3 -m hyper2kvm.worker.cli events $JOB_ID --follow"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Job ID: $JOB_ID"
echo "Worker: $WORKER_POD"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
