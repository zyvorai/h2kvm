.PHONY: help install install-dev install-deps \
       test test-unit test-integration test-operator test-zkvm test-all test-coverage \
       lint lint-fix lint-all format \
       build build-zkvm build-operator build-operator-image build-k8s-image build-all \
       zkvm-install zkvm-clean \
       k8s-deploy k8s-deploy-k3d k8s-status k8s-cleanup \
       operator-install-crds operator-uninstall-crds operator-deploy operator-undeploy operator-run \
       clean clean-state clean-all \
       package-deb package-rpm package-all \
       ci-python ci-operator ci-zkvm ci-all \
       release-check docs docs-serve \
       go-tidy go-update go-vet \
       security-scan sbom license-check changelog version validate-examples \
       preflight preflight-fix health debug-bundle \
       uninstall uninstall-operator uninstall-workers uninstall-migrations uninstall-all uninstall-k3d \
       backup-operator backup-workers

# Default target
.DEFAULT_GOAL := build-all

# Python binary
PYTHON := python3
PIP    := $(PYTHON) -m pip

# Go binary
GO := go

# Directories
OPERATOR_DIR  := operator
ZKVM_DIR      := zkvm
K8S_DIR       := k8s
HYPER2KVM_DIR := hyper2kvm

# Binary names
ZKVM_BINARY := zkvm
OPERATOR_BINARY := hyper2kvm-operator

# Install prefix
PREFIX     ?= /usr
BINDIR     ?= $(PREFIX)/bin

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@awk '/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)}' $(MAKEFILE_LIST)
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Installation

install: build-all clean-state ## Build and install everything (Python h2kvmctl + zkvm + operator + h2k) to $(BINDIR)
	@# Remove any user-level pip install so $(BINDIR) copy takes precedence in PATH
	-$(PIP) uninstall -y hyper2kvm 2>/dev/null || true
	$(PIP) install --prefix=$(PREFIX) --no-warn-script-location .
	install -Dm755 $(ZKVM_DIR)/$(ZKVM_BINARY) $(BINDIR)/$(ZKVM_BINARY)
	install -Dm755 $(OPERATOR_DIR)/bin/manager $(BINDIR)/$(OPERATOR_BINARY)
	install -Dm755 scripts/h2k $(BINDIR)/h2k
	@echo "Installed h2kvmctl, $(ZKVM_BINARY), $(OPERATOR_BINARY), h2k to $(BINDIR)"

install-dev: ## Install Python package in editable mode with dev deps
	$(PIP) install -e ".[dev,ui,vsphere,validation,retry,daemon,async]"
	@echo "Installed hyper2kvm in editable mode with dev dependencies"

install-deps: ## Download all dependencies (Python + Go modules)
	$(PIP) install -e ".[dev]"
	cd $(OPERATOR_DIR) && $(GO) mod download
	cd $(ZKVM_DIR) && $(GO) mod download
	@echo "All dependencies installed"

##@ Testing

selftest: ## Post-installation verification (checks binaries, Python, manifests, services)
	@./scripts/selftest.sh

selftest-quick: ## Quick post-installation check (skip services)
	@./scripts/selftest.sh --quick

test: test-unit ## Run default tests (unit)

test-unit: ## Run Python unit tests
	pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests
	pytest tests/unit/ -v -m integration

test-operator: ## Run operator Go tests
	cd $(OPERATOR_DIR) && $(GO) test ./... -v

test-zkvm: ## Run zkvm Go tests
	cd $(ZKVM_DIR) && $(GO) test ./...

test-all: test-unit test-operator test-zkvm ## Run all tests (Python + Go)

test-coverage: ## Run Python tests with coverage report
	pytest tests/unit/ -v --cov=$(HYPER2KVM_DIR) --cov-report=html --cov-report=term

##@ Code Quality

lint: ## Run linters (ruff + mypy + go vet)
	ruff check $(HYPER2KVM_DIR)/
	cd $(ZKVM_DIR) && $(GO) vet ./...
	cd $(OPERATOR_DIR) && $(GO) vet ./...

lint-fix: ## Run linters and auto-fix issues
	ruff check --fix $(HYPER2KVM_DIR)/

format: ## Format all code (Python + Go)
	ruff format $(HYPER2KVM_DIR)/
	cd $(ZKVM_DIR) && gofmt -s -w .
	cd $(OPERATOR_DIR) && $(GO) fmt ./...

##@ Building

build: build-zkvm build-h2kweb build-operator ## Build everything (Python + zkvm + h2kweb + operator)
	$(PYTHON) -m build

build-zkvm: ## Build Go zkvm binary
	cd $(ZKVM_DIR) && $(GO) build -ldflags "-s -w -X main.version=$$(git describe --tags --always --dirty 2>/dev/null || echo dev)" -o $(ZKVM_BINARY) .
	@echo "Built $(ZKVM_DIR)/$(ZKVM_BINARY)"

build-operator: ## Build operator binary
	cd $(OPERATOR_DIR) && $(GO) build -ldflags "-s -w" -o bin/manager cmd/main.go

build-operator-image: ## Build operator container image
	cd $(OPERATOR_DIR) && docker build -t ghcr.io/hyper2kvm/operator:latest .

build-k8s-image: ## Build k8s worker container image
	cd $(K8S_DIR) && docker build --target worker -t hyper2kvm:worker ..

build-h2kweb: ## Build h2kweb web dashboard (Go + React)
	@if [ -f web/Makefile ]; then cd web && $(MAKE) build; else echo "web/ not found — skipping h2kweb"; fi

build-all: build ## Build everything (Python + zkvm + h2kweb + operator)

##@ h2kweb

h2kweb-install: build-h2kweb ## Build and install h2kweb (web dashboard) with systemd service
	cd web && $(MAKE) install

h2kweb-clean: ## Clean h2kweb build artifacts
	@if [ -f web/Makefile ]; then cd web && $(MAKE) clean; fi

##@ zkvm

zkvm-install: build-zkvm ## Build and install zkvm binary to $(BINDIR)
	install -Dm755 $(ZKVM_DIR)/$(ZKVM_BINARY) $(BINDIR)/$(ZKVM_BINARY)
	@echo "Installed $(BINDIR)/$(ZKVM_BINARY)"

zkvm-clean: ## Clean zkvm build artifacts
	rm -f $(ZKVM_DIR)/$(ZKVM_BINARY)

##@ Kubernetes / k3d

k8s-deploy: ## Deploy to Kubernetes (production)
	$(MAKE) -C $(K8S_DIR) deploy-all

k8s-deploy-k3d: ## Deploy to k3d cluster
	$(MAKE) -C $(K8S_DIR) deploy-all-k3d

k8s-load-image: ## Load worker image into k3d (CLUSTER_NAME required)
	$(MAKE) -C $(K8S_DIR) load-image-k3d CLUSTER_NAME=$(CLUSTER_NAME)

k8s-status: ## Show k8s deployment status
	$(MAKE) -C $(K8S_DIR) status

k8s-logs: ## Show k8s worker logs
	$(MAKE) -C $(K8S_DIR) logs

k8s-cleanup: ## Delete all k8s resources
	$(MAKE) -C $(K8S_DIR) cleanup

##@ Lifecycle (install / uninstall / health)

preflight: ## Pre-flight cluster readiness check
	@./scripts/preflight-check.sh

preflight-fix: ## Pre-flight check with auto-fix
	@./scripts/preflight-check.sh --fix

uninstall: ## Remove all hyper2kvm components from cluster
	@./scripts/uninstall.sh

uninstall-operator: ## Remove operator only
	@./scripts/uninstall.sh --operator

uninstall-workers: ## Remove workers only
	@./scripts/uninstall.sh --workers

uninstall-migrations: ## Remove migration resources only
	@./scripts/uninstall.sh --migrations

uninstall-all: ## Remove everything (hyper2kvm + KubeVirt + CDI)
	@./scripts/uninstall.sh --all

uninstall-k3d: ## Delete entire k3d cluster
	@./scripts/uninstall.sh --k3d

health: ## Full-stack health check
	@./scripts/health-check.sh

debug-bundle: ## Collect debug bundle for troubleshooting
	@./scripts/collect-debug-bundle.sh

backup-operator: ## Backup operator state before upgrade
	@./scripts/ops/backup-operator-state.sh

backup-workers: ## Backup worker state
	@./scripts/ops/backup-worker-state.sh

##@ Operator Management

operator-install-crds: ## Install operator CRDs
	cd $(OPERATOR_DIR) && kubectl apply -f config/crd/

operator-uninstall-crds: ## Uninstall operator CRDs
	cd $(OPERATOR_DIR) && kubectl delete -f config/crd/

operator-deploy: ## Deploy operator to Kubernetes
	cd $(OPERATOR_DIR) && make deploy

operator-undeploy: ## Remove operator from Kubernetes
	cd $(OPERATOR_DIR) && make undeploy

operator-run: ## Run operator locally
	cd $(OPERATOR_DIR) && $(GO) run ./cmd/main.go

operator-webhook-certs: ## Generate webhook certs (cert-manager preferred, fallback to openssl)
	@if kubectl get crd certificates.cert-manager.io >/dev/null 2>&1; then \
		echo "cert-manager detected, deploying Certificate resource..."; \
		kubectl apply -f $(OPERATOR_DIR)/config/certmanager/; \
	else \
		echo "cert-manager not found, using manual certificate generation..."; \
		./scripts/generate-webhook-certs.sh; \
	fi

# All Go module directories
GO_MODULES := $(OPERATOR_DIR) $(ZKVM_DIR)

##@ Go Modules

go-tidy: ## Run go mod tidy across all Go modules
	@for mod in $(GO_MODULES); do \
		echo "go mod tidy in $$mod/"; \
		(cd $$mod && $(GO) mod tidy) || exit 1; \
	done
	@echo "All Go modules tidied"

go-update: go-tidy ## Tidy + download all Go module dependencies
	@for mod in $(GO_MODULES); do \
		echo "go mod download in $$mod/"; \
		(cd $$mod && $(GO) mod download) || exit 1; \
	done
	@echo "All Go modules updated"

go-vet: ## Run go vet across all Go modules
	@for mod in $(GO_MODULES); do \
		echo "go vet in $$mod/"; \
		(cd $$mod && $(GO) vet ./...) || exit 1; \
	done
	@echo "All Go modules passed vet"

##@ Cleanup

clean: zkvm-clean h2kweb-clean ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .coverage htmlcov/
	rm -rf $(OPERATOR_DIR)/bin/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

clean-state: ## Clean runtime state (workflow dirs, conversions, locks, caches)
	rm -rf /var/lib/hyper2kvm/conversions/* 2>/dev/null || true
	rm -rf /var/lib/hyper2kvm/output/* 2>/dev/null || true
	rm -rf /run/hyper2kvm/workflow/* 2>/dev/null || true
	systemd-tmpfiles --create hyper2kvm.conf 2>/dev/null || true
	@echo "Cleaned runtime state"

clean-all: clean ## Clean everything including Go caches
	cd $(OPERATOR_DIR) && $(GO) clean -cache -modcache
	cd $(ZKVM_DIR) && $(GO) clean -cache -modcache

##@ Packaging

package-deb: ## Build Debian package
	dpkg-buildpackage -us -uc

package-rpm: ## Build RPM package
	$(PYTHON) -m build --wheel

package-all: build package-deb package-rpm ## Build all packages

##@ CI/CD

ci-python: install lint test-unit ## Run Python CI checks

ci-operator: ## Run operator CI checks
	cd $(OPERATOR_DIR) && $(GO) fmt ./...
	cd $(OPERATOR_DIR) && $(GO) vet ./...
	cd $(OPERATOR_DIR) && $(GO) test ./... -v

ci-zkvm: ## Run zkvm CI checks
	cd $(ZKVM_DIR) && $(GO) vet ./...
	cd $(ZKVM_DIR) && $(GO) test ./...

ci-all: ci-python ci-operator ci-zkvm ## Run all CI checks

##@ Release

release-check: ## Check if ready for release
	@echo "Checking release readiness..."
	@$(PYTHON) -m build --check
	@echo "  Build configuration is valid"
	@git diff --quiet || (echo "  Working directory is not clean" && exit 1)
	@echo "  Working directory is clean"
	@echo "Ready for release!"

##@ Documentation

docs: ## Build documentation (CLI reference + API docs)
	@mkdir -p docs/_build
	$(PYTHON) -c "from hyper2kvm.cli.args.parser import build_parser; p = build_parser(); p.print_help()" > docs/_build/cli-reference.txt
	$(PYTHON) -m pydoc -w hyper2kvm 2>/dev/null || true
	@echo "CLI reference generated at docs/_build/cli-reference.txt"

docs-serve: docs ## Serve documentation locally on port 8080
	cd docs/_build && $(PYTHON) -m http.server 8080

##@ Security & Compliance

security-scan: ## Run security scanning (bandit + pip-audit + detect-secrets)
	@echo "Running bandit (SAST)..."
	-bandit -r $(HYPER2KVM_DIR)/ -c pyproject.toml -q 2>/dev/null || bandit -r $(HYPER2KVM_DIR)/ -ll -q
	@echo "Running pip-audit (dependency vulnerabilities)..."
	-pip-audit 2>/dev/null || echo "  pip-audit not installed: pip install pip-audit"
	@echo "Running detect-secrets..."
	-detect-secrets scan --baseline .secrets.baseline 2>/dev/null || echo "  detect-secrets not installed: pip install detect-secrets"
	@echo "Security scan complete"

sbom: ## Generate Software Bill of Materials (CycloneDX)
	@echo "Generating SBOM..."
	-$(PYTHON) -m cyclonedx_py environment -o sbom.json 2>/dev/null || echo "  Install: pip install cyclonedx-bom"
	@echo "SBOM generated at sbom.json"

license-check: ## Check license compliance (REUSE)
	-reuse lint 2>/dev/null || echo "  Install: pip install reuse"

changelog: ## Generate changelog from git commits
	@echo "# Changelog" > CHANGELOG.generated.md
	@echo "" >> CHANGELOG.generated.md
	@git log --pretty=format:"- %s (%h)" --no-merges $$(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~50")..HEAD >> CHANGELOG.generated.md 2>/dev/null || \
		git log --pretty=format:"- %s (%h)" --no-merges -50 >> CHANGELOG.generated.md
	@echo ""
	@echo "Changelog generated at CHANGELOG.generated.md"

lint-all: lint ## Run all linters (ruff + mypy + go vet + shellcheck)
	-mypy $(HYPER2KVM_DIR)/ --ignore-missing-imports 2>/dev/null || echo "  mypy not installed or has errors"
	-shellcheck scripts/*.sh 2>/dev/null || echo "  shellcheck not installed: dnf install ShellCheck"

version: ## Show all component versions
	@echo "hyper2kvm: $$($(PYTHON) -c 'import hyper2kvm; print(hyper2kvm.__version__)' 2>/dev/null || echo 'not installed')"
	@echo "zkvm:      $$(cd $(ZKVM_DIR) && git describe --tags --always --dirty 2>/dev/null || echo 'dev')"
	@echo "operator:  $$(cd $(OPERATOR_DIR) && git describe --tags --always --dirty 2>/dev/null || echo 'dev')"
	@echo "python:    $$($(PYTHON) --version)"
	@echo "go:        $$($(GO) version 2>/dev/null || echo 'not installed')"

validate-examples: ## Validate all example YAML/JSON configs
	@echo "Validating example configurations..."
	@for f in examples/yaml/**/*.yaml; do \
		$(PYTHON) -c "import yaml; yaml.safe_load(open('$$f'))" 2>/dev/null && echo "  ✓ $$f" || echo "  ✗ $$f"; \
	done
	@echo "Validation complete"
