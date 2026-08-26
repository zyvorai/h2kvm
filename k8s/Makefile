# Makefile for h2kvm Worker Job Protocol Kubernetes deployment
# Usage: make deploy-all

NAMESPACE := h2kvm-workers
KUBECONFIG ?= ~/.kube/config
KUBECTL := kubectl --kubeconfig=$(KUBECONFIG)

.PHONY: help
help: ## Show this help message
	@echo "h2kvm Worker Job Protocol - Kubernetes Deployment"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

.PHONY: check-prereqs
check-prereqs: ## Check prerequisites
	@echo "Checking prerequisites..."
	@command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found"; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo "docker not found"; exit 1; }
	@$(KUBECTL) version --client >/dev/null 2>&1 || { echo "kubectl not configured"; exit 1; }
	@echo "✓ All prerequisites met"

.PHONY: build-image
build-image: ## Build worker container image
	@echo "Building h2kvm:worker image..."
	docker build --target worker -t h2kvm:worker ..
	@echo "✓ Image built successfully"

.PHONY: load-image-k3d
load-image-k3d: ## Load image into k3d cluster (requires CLUSTER_NAME)
	@if [ -z "$(CLUSTER_NAME)" ]; then \
		echo "ERROR: CLUSTER_NAME not set. Usage: make load-image-k3d CLUSTER_NAME=mycluster"; \
		exit 1; \
	fi
	@echo "Loading image into k3d cluster: $(CLUSTER_NAME)"
	k3d image import h2kvm:worker -c $(CLUSTER_NAME)
	@echo "✓ Image loaded into k3d cluster"

.PHONY: create-namespace
create-namespace: check-prereqs ## Create namespace
	@echo "Creating namespace: $(NAMESPACE)"
	@$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	@echo "✓ Namespace created"

.PHONY: label-nodes
label-nodes: ## Label nodes as worker-enabled (requires NODE_NAMES)
	@if [ -z "$(NODE_NAMES)" ]; then \
		echo "ERROR: NODE_NAMES not set. Usage: make label-nodes NODE_NAMES='node1 node2'"; \
		exit 1; \
	fi
	@echo "Labeling nodes: $(NODE_NAMES)"
	@for node in $(NODE_NAMES); do \
		$(KUBECTL) label nodes $$node h2kvm.io/worker-enabled=true --overwrite; \
	done
	@echo "✓ Nodes labeled"

.PHONY: deploy-rbac
deploy-rbac: create-namespace ## Deploy RBAC resources
	@echo "Deploying RBAC..."
	@$(KUBECTL) apply -f worker/rbac.yaml
	@echo "✓ RBAC deployed"

.PHONY: deploy-configmap
deploy-configmap: create-namespace ## Deploy ConfigMap
	@echo "Deploying ConfigMap..."
	@$(KUBECTL) apply -f worker/configmap.yaml
	@echo "✓ ConfigMap deployed"

.PHONY: deploy-storage
deploy-storage: create-namespace ## Deploy storage classes and PVCs
	@echo "Deploying storage resources..."
	@$(KUBECTL) apply -f base/storageclasses.yaml || echo "WARNING: Storage classes may need customization"
	@$(KUBECTL) apply -f worker/pvc-templates.yaml || echo "WARNING: PVCs may need storage class adjustment"
	@echo "✓ Storage resources deployed"

.PHONY: deploy-workers
deploy-workers: create-namespace ## Deploy worker DaemonSet
	@echo "Deploying worker DaemonSet..."
	@$(KUBECTL) apply -f worker/daemonset-production.yaml
	@echo "✓ Workers deployed"

.PHONY: deploy-workers-k3d
deploy-workers-k3d: create-namespace ## Deploy worker DaemonSet (k3d version without init container)
	@echo "Deploying worker DaemonSet (k3d version)..."
	@$(KUBECTL) apply -f worker/daemonset.yaml
	@echo "✓ Workers deployed (k3d version)"

.PHONY: deploy-monitoring
deploy-monitoring: create-namespace ## Deploy monitoring resources (Prometheus)
	@echo "Deploying monitoring resources..."
	@$(KUBECTL) apply -f monitoring/servicemonitor.yaml || echo "WARNING: Prometheus Operator may not be installed"
	@echo "✓ Monitoring resources deployed"

.PHONY: deploy-all
deploy-all: check-prereqs create-namespace deploy-rbac deploy-configmap deploy-storage deploy-workers deploy-monitoring ## Deploy all resources
	@echo ""
	@echo "════════════════════════════════════════════════════════════"
	@echo "✓ All resources deployed successfully!"
	@echo "════════════════════════════════════════════════════════════"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Label nodes: make label-nodes NODE_NAMES='node1 node2'"
	@echo "  2. Check status: make status"
	@echo "  3. Submit a job: make submit-job JOB_FILE=examples/convert-job.json"
	@echo ""

.PHONY: deploy-all-k3d
deploy-all-k3d: check-prereqs create-namespace deploy-rbac deploy-configmap deploy-workers-k3d ## Deploy all resources (k3d version)
	@echo ""
	@echo "════════════════════════════════════════════════════════════"
	@echo "✓ All resources deployed successfully (k3d)!"
	@echo "════════════════════════════════════════════════════════════"

.PHONY: status
status: ## Show deployment status
	@echo "Deployment Status:"
	@echo ""
	@echo "Namespace:"
	@$(KUBECTL) get namespace $(NAMESPACE)
	@echo ""
	@echo "Worker Pods:"
	@$(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o wide
	@echo ""
	@echo "Services:"
	@$(KUBECTL) get svc -n $(NAMESPACE)
	@echo ""
	@echo "PVCs:"
	@$(KUBECTL) get pvc -n $(NAMESPACE)

.PHONY: logs
logs: ## Show worker logs (use POD_NAME= to specify pod)
	@if [ -z "$(POD_NAME)" ]; then \
		echo "Following logs from all worker pods..."; \
		$(KUBECTL) logs -n $(NAMESPACE) -l app=h2kvm-worker --tail=50 -f; \
	else \
		echo "Following logs from pod: $(POD_NAME)"; \
		$(KUBECTL) logs -n $(NAMESPACE) $(POD_NAME) -f; \
	fi

.PHONY: exec
exec: ## Exec into worker pod (requires POD_NAME)
	@if [ -z "$(POD_NAME)" ]; then \
		echo "ERROR: POD_NAME not set. Usage: make exec POD_NAME=h2kvm-worker-xxxxx"; \
		exit 1; \
	fi
	@$(KUBECTL) exec -n $(NAMESPACE) -it $(POD_NAME) -- /bin/bash

.PHONY: submit-job
submit-job: ## Submit a job (requires JOB_FILE)
	@if [ -z "$(JOB_FILE)" ]; then \
		echo "ERROR: JOB_FILE not set. Usage: make submit-job JOB_FILE=examples/convert-job.json"; \
		exit 1; \
	fi
	@if [ ! -f "$(JOB_FILE)" ]; then \
		echo "ERROR: Job file not found: $(JOB_FILE)"; \
		exit 1; \
	fi
	@JOB_ID=$$(cat $(JOB_FILE) | grep job_id | cut -d'"' -f4); \
	echo "Submitting job: $$JOB_ID"; \
	$(KUBECTL) create configmap h2kvm-job-$$JOB_ID \
		--from-file=job-spec.json=$(JOB_FILE) \
		-n $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -; \
	POD=$$($(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}'); \
	echo "Executing job in pod: $$POD"; \
	$(KUBECTL) exec -n $(NAMESPACE) $$POD -- \
		python3 -m h2kvm.worker.cli run /data/job-spec.json --worker-id $$POD

.PHONY: cleanup
cleanup: ## Delete all resources
	@echo "WARNING: This will delete all h2kvm resources in namespace $(NAMESPACE)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "Deleting resources..."; \
		$(KUBECTL) delete namespace $(NAMESPACE); \
		echo "✓ Resources deleted"; \
	else \
		echo "Cancelled"; \
	fi

.PHONY: restart-workers
restart-workers: ## Restart all worker pods
	@echo "Restarting worker pods..."
	@$(KUBECTL) delete pods -n $(NAMESPACE) -l app=h2kvm-worker
	@echo "✓ Pods restarted"

.PHONY: describe-worker
describe-worker: ## Describe worker pod (requires POD_NAME)
	@if [ -z "$(POD_NAME)" ]; then \
		POD_NAME=$$($(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}'); \
	fi; \
	echo "Describing pod: $$POD_NAME"; \
	$(KUBECTL) describe pod -n $(NAMESPACE) $$POD_NAME

.PHONY: capabilities
capabilities: ## Show worker capabilities
	@POD_NAME=$$($(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}'); \
	echo "Checking capabilities on pod: $$POD_NAME"; \
	$(KUBECTL) exec -n $(NAMESPACE) $$POD_NAME -- \
		python3 -m h2kvm.worker.cli capabilities

.PHONY: list-jobs
list-jobs: ## List all jobs
	@POD_NAME=$$($(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}'); \
	$(KUBECTL) exec -n $(NAMESPACE) $$POD_NAME -- \
		python3 -m h2kvm.worker.cli list

.PHONY: job-status
job-status: ## Show job status (requires JOB_ID)
	@if [ -z "$(JOB_ID)" ]; then \
		echo "ERROR: JOB_ID not set. Usage: make job-status JOB_ID=my-job-001"; \
		exit 1; \
	fi
	@POD_NAME=$$($(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}'); \
	$(KUBECTL) exec -n $(NAMESPACE) $$POD_NAME -- \
		python3 -m h2kvm.worker.cli status $(JOB_ID)

.PHONY: job-events
job-events: ## Show job events (requires JOB_ID)
	@if [ -z "$(JOB_ID)" ]; then \
		echo "ERROR: JOB_ID not set. Usage: make job-events JOB_ID=my-job-001"; \
		exit 1; \
	fi
	@POD_NAME=$$($(KUBECTL) get pods -n $(NAMESPACE) -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}'); \
	$(KUBECTL) exec -n $(NAMESPACE) $$POD_NAME -- \
		python3 -m h2kvm.worker.cli events $(JOB_ID)
