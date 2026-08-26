# ARCHITECTURE.md — hyper2kvm Internal Architecture


## Table of Contents

- [Purpose](#purpose)
- [The Canonical Pipeline](#the-canonical-pipeline)
  - [Pipeline Stages Explained](#pipeline-stages-explained)
    - [FETCH](#fetch)
    - [FLATTEN](#flatten)
    - [INSPECT](#inspect)
    - [PLAN](#plan)
    - [FIX](#fix)
    - [CONVERT](#convert)
    - [VALIDATE / TEST](#validate-test)
- [Repository Structure (Authoritative)](#repository-structure-authoritative)
- [Orchestrator Architecture (Refactored)](#orchestrator-architecture-refactored)
  - [Component Breakdown](#component-breakdown)
    - [1. **Orchestrator** (`orchestrator/orchestrator.py`)](#1-orchestrator-orchestratororchestratorpy)
    - [2. **DiskDiscovery** (`orchestrator/disk_discovery.py`)](#2-diskdiscovery-orchestratordisk_discoverypy)
    - [3. **DiskProcessor** (`orchestrator/disk_processor.py`)](#3-diskprocessor-orchestratordisk_processorpy)
    - [4. **VsphereExporter** (`orchestrator/vsphere_exporter.py`)](#4-vsphereexporter-orchestratorvsphere_exporterpy)
  - [Refactoring Benefits](#refactoring-benefits)
- [Control-Plane vs Data-Plane (VMware)](#control-plane-vs-data-plane-vmware)
  - [Control-Plane: Inventory, Planning, Orchestration](#control-plane-inventory-planning-orchestration)
    - [Implementation 1: govc (Primary)](#implementation-1-govc-primary)
    - [Implementation 2: pyvmomi / pyVim (Fallback)](#implementation-2-pyvmomi-pyvim-fallback)
    - [CLI Glue Layer](#cli-glue-layer)
  - [Data-Plane: Byte Movement](#data-plane-byte-movement)
    - [Transport 1: VDDK (Highest Performance)](#transport-1-vddk-highest-performance)
    - [Transport 2: ovftool (Official VMware Export)](#transport-2-ovftool-official-vmware-export)
    - [Transport 3: HTTP `/folder` (Datastore Downloads)](#transport-3-http-folder-datastore-downloads)
    - [Transport 4: SSH/SCP (Universal Fallback)](#transport-4-sshscp-universal-fallback)
    - [Transport 5: govc export (CLI-Based)](#transport-5-govc-export-cli-based)
- [Fixer Subsystems (Deep Dive)](#fixer-subsystems-deep-dive)
  - [Offline Fixing (Default Strategy)](#offline-fixing-default-strategy)
    - [1. Filesystem Fixing (`fixers/filesystem/`)](#1-filesystem-fixing-fixersfilesystem)
    - [2. Bootloader Fixing (`fixers/bootloader/`)](#2-bootloader-fixing-fixersbootloader)
    - [3. Config Rewriting (`fixers/offline/config_rewriter.py`)](#3-config-rewriting-fixersofflineconfig_rewriterpy)
    - [4. VMware Tools Removal (`fixers/offline/vmware_tools_remover.py`)](#4-vmware-tools-removal-fixersofflinevmware_tools_removerpy)
  - [Live Fixing (Opt-In Strategy)](#live-fixing-opt-in-strategy)
  - [Windows Fixing (Hermetically Sealed)](#windows-fixing-hermetically-sealed)
    - [Registry Subsystem (`fixers/windows/registry/`)](#registry-subsystem-fixerswindowsregistry)
    - [VirtIO Subsystem (`fixers/windows/virtio/`)](#virtio-subsystem-fixerswindowsvirtio)
  - [Network Fixing (Cross-Platform)](#network-fixing-cross-platform)
    - [Discovery (`discovery.py`)](#discovery-discoverypy)
    - [Topology (`topology.py`)](#topology-topologypy)
    - [Core (`core.py`)](#core-corepy)
    - [Validation (`validation.py`)](#validation-validationpy)
    - [Backend (`backend.py`)](#backend-backendpy)
- [LibVirt Integration](#libvirt-integration)
  - [Domain Emitter (`domain_emitter.py`)](#domain-emitter-domain_emitterpy)
  - [Linux Domain (`linux_domain.py`)](#linux-domain-linux_domainpy)
  - [Windows Domain (`windows_domain.py`)](#windows-domain-windows_domainpy)
- [Core Utilities](#core-utilities)
- [VMCraft - VM Manipulation Engine](#vmcraft---vm-manipulation-engine)
  - [Architecture](#architecture)
  - [Key Capabilities](#key-capabilities)
  - [Integration with Pipeline](#integration-with-pipeline)
  - [Performance](#performance)
  - [Usage in hyper2kvm](#usage-in-hyper2kvm)
  - [Essential Utilities](#essential-utilities)
    - [Guest Identity (`guest_identity.py`)](#guest-identity-guest_identitypy)
    - [Recovery Manager (`recovery_manager.py`)](#recovery-manager-recovery_managerpy)
    - [Retry Logic (`retry.py`)](#retry-logic-retrypy)
    - [Validation Suite (`validation_suite.py`)](#validation-suite-validation_suitepy)
    - [File Operations (`file_ops.py`)](#file-operations-file_opspy)
    - [Logging (`logger.py`, `logging_utils.py`)](#logging-loggerpy-logging_utilspy)
- [Key Architectural Invariants](#key-architectural-invariants)
  - [1. Offline is the Default Truth](#1-offline-is-the-default-truth)
  - [2. Inspection Over Assumption](#2-inspection-over-assumption)
  - [3. `/dev/disk/by-path` is Radioactive](#3-devdiskby-path-is-radioactive)
  - [4. Windows Logic is Hermetically Sealed](#4-windows-logic-is-hermetically-sealed)
  - [5. Control-Plane and Data-Plane Never Mix](#5-control-plane-and-data-plane-never-mix)
  - [6. Idempotent, Best-Effort Behavior](#6-idempotent-best-effort-behavior)
- [Module Ownership and Responsibilities](#module-ownership-and-responsibilities)
  - [`cli/`](#cli)
  - [`config/`](#config)
  - [`core/`](#core)
  - [`converters/`](#converters)
  - [`fixers/`](#fixers)
  - [`libvirt/`](#libvirt)
  - [`modes/`](#modes)
  - [`orchestrator/`](#orchestrator)
  - [`ssh/`](#ssh)
  - [`testers/`](#testers)
  - [`vmware/`](#vmware)
- [Why This Architecture Works](#why-this-architecture-works)
  - [Predictability](#predictability)
  - [Reliability](#reliability)
  - [Maintainability](#maintainability)
  - [Extensibility](#extensibility)
  - [Debuggability](#debuggability)
- [Adding New Features](#adding-new-features)
  - [Where Does My Feature Go?](#where-does-my-feature-go)
    - [1. New Disk Source (e.g., Azure Blob, S3)](#1-new-disk-source-eg-azure-blob-s3)
    - [2. New Fix (e.g., SELinux relabeling)](#2-new-fix-eg-selinux-relabeling)
    - [3. New Network Manager (e.g., wicked for SUSE)](#3-new-network-manager-eg-wicked-for-suse)
    - [4. New Validation Test (e.g., storage performance)](#4-new-validation-test-eg-storage-performance)
    - [5. New VMware Transport (e.g., NBD direct)](#5-new-vmware-transport-eg-nbd-direct)
  - [Feature Addition Checklist](#feature-addition-checklist)
- [Performance Considerations](#performance-considerations)
  - [Parallel Processing](#parallel-processing)
    - [Disk Processing](#disk-processing)
  - [I/O Optimization](#io-optimization)
    - [VDDK (VMware)](#vddk-vmware)
    - [Compression](#compression)
- [Testing Strategy](#testing-strategy)
  - [Unit Tests](#unit-tests)
  - [Integration Tests](#integration-tests)
  - [Security Tests](#security-tests)
- [Future Architecture Directions](#future-architecture-directions)
  - [Plugin System](#plugin-system)
  - [Cloud-Native Integration](#cloud-native-integration)
  - [Advanced Recovery](#advanced-recovery)
  - [Metrics and Telemetry](#metrics-and-telemetry)
- [Glossary](#glossary)
- [Code Examples](#code-examples)
- [Contributing](#contributing)
- [Summary](#summary)

---
## Purpose

This document provides an in-depth exploration of **hyper2kvm's module-level architecture**, execution flow, and core architectural principles.

It's designed for:
* **Contributors** wanting to understand the codebase structure
* **Reviewers** evaluating design decisions and implementation quality
* **Power users** seeking to extend or customize the migration pipeline

hyper2kvm is laser-focused on fixing "successful" conversions that fail at boot, lose network connectivity, or exhibit instability post-migration. This architecture document explains how the modular design achieves reliability through:

* **Deterministic inspection** over assumption-based heuristics
* **Offline-first fixing** to avoid runtime dependencies
* **Strict separation** between control-plane and data-plane operations
* **Composable pipeline stages** that enforce predictable ordering

---

## The Canonical Pipeline

At the heart of every migration is this invariant flow:

**FETCH → FLATTEN → INSPECT → PLAN → FIX → CONVERT → VALIDATE / TEST**

Not every command executes every stage, but **the order is sacred**. Stages can be skipped, but never reordered or interleaved.

### Pipeline Stages Explained

#### FETCH
Acquire source disks and metadata from any source:
- vSphere APIs (via pyvmomi or govc)
- ESXi hosts via SSH/SCP
- Local filesystem paths
- HTTP datastore downloads
- VDDK high-speed transfers
- OVA/OVF archives

**Key principle:** Source-agnostic acquisition with unified interface.

#### FLATTEN
Transform complex disk chains into single-image files:
- Collapse VMware snapshot chains (delta extents)
- Resolve VMDK descriptor file references
- Merge linked clones into standalone images
- Normalize quirky vendor formats

**Output:** Clean, single-file disk images ready for inspection.

#### INSPECT
Offline deep-dive using the guestfs backend (VMCraft by default) to extract ground truth:
- OS family detection (Linux vs Windows)
- Firmware type (BIOS vs UEFI)
- Partition layouts and mount points
- Bootloader configuration (GRUB, GRUB2, systemd-boot)
- Network interface configurations
- Installed drivers and kernel modules
- Critical system files (/etc/fstab, initramfs, etc.)

**Philosophy:** Derive facts, never guess. Inspection over assumption.

#### PLAN
Strategic planning before execution:
- Inventory scans (read-only VM discovery)
- Dry-run simulations (what-if analysis)
- Dependency resolution
- Resource requirement calculation

**Value:** Plan smart, execute once. No trial-and-error.

#### FIX
Apply deterministic patches to ensure bootability:
- **Offline fixes** (default): guestfs-based disk mutations (VMCraft by default), no boot required
- **Live fixes** (opt-in): SSH-based corrections on running guests
- fstab rewriting (UUID/PARTUUID over by-path)
- Bootloader regeneration (GRUB config, initramfs)
- Network cleanup (remove MAC pinning, VMware artifacts)
- Windows VirtIO driver injection
- VMware Tools removal

**Guarantee:** Idempotent operations that tolerate re-runs.

#### CONVERT
Image format transformation via qemu-img:
- VMDK → qcow2 (default)
- Support for raw, VDI, VHDX
- Compression and sparse allocation
- Disk resizing (expansion/shrinkage)

**Integration:** Optional direct export pre/post-processing hooks.

#### VALIDATE / TEST
Ruthless verification:
- Boot smoke tests (QEMU direct or libvirt domains)
- Network connectivity checks
- Filesystem integrity validation
- Performance benchmarking

**Motto:** Does it boot? Does it network? Does it survive? Prove it.

---


### Pipeline Flow Diagram

```mermaid
flowchart LR
    FETCH[FETCH<br/>Acquire Disks] --> FLATTEN[FLATTEN<br/>Collapse Chains]
    FLATTEN --> INSPECT[INSPECT<br/>Extract Facts]
    INSPECT --> PLAN[PLAN<br/>Strategy]
    PLAN --> FIX[FIX<br/>Apply Patches]
    FIX --> CONVERT[CONVERT<br/>Format Transform]
    CONVERT --> VALIDATE[VALIDATE/TEST<br/>Boot Tests]

    style FETCH fill:#4CAF50,stroke:#2E7D32,color:#fff
    style FLATTEN fill:#2196F3,stroke:#1565C0,color:#fff
    style INSPECT fill:#FF9800,stroke:#E65100,color:#fff
    style PLAN fill:#9C27B0,stroke:#6A1B9A,color:#fff
    style FIX fill:#F44336,stroke:#C62828,color:#fff
    style CONVERT fill:#00BCD4,stroke:#006064,color:#fff
    style VALIDATE fill:#8BC34A,stroke:#558B2F,color:#fff
```

**Key Invariants:**
- Order is sacred: stages can be skipped but never reordered
- Each stage has clear inputs/outputs
- Failures are isolated to specific stages


## Repository Structure (Authoritative)

This reflects the **actual codebase structure** as of the latest refactor:

```bash
hyper2kvm/
├── __init__.py                       # Package root
├── __main__.py                       # Entry point (h2kvmctl)
│
├── cli/                              # Command-line interface layer
│   ├── __init__.py
│   ├── argument_parser.py            # Main argument parser (legacy entry)
│   ├── help_texts.py                 # User-facing help documentation
│   └── args/                         # Refactored argument parsing (modular)
│       ├── __init__.py
│       ├── builder.py                # Argument builder pattern
│       ├── groups.py                 # Argument group definitions
│       ├── helpers.py                # Parsing utilities
│       ├── parser.py                 # Core parser logic
│       └── validators.py             # Argument validation rules
│
├── config/                           # Configuration management
│   ├── __init__.py
│   ├── config_loader.py              # YAML config loading and merging
│   └── systemd_template.py          # Systemd unit templates for guest injection
│
├── core/                             # Foundational utilities and infrastructure
│   ├── __init__.py
│   ├── cred.py                       # Credential handling (secure storage)
│   ├── exceptions.py                 # Custom exception hierarchy
│   ├── file_ops.py                   # File operation utilities
│   ├── guest_identity.py             # Guest OS identity detection
│   ├── guest_utils.py                # Guest-specific utilities
│   ├── list_utils.py                 # List manipulation helpers
│   ├── logger.py                     # Structured logging (rich console)
│   ├── logging_utils.py              # Logging configuration helpers
│   ├── optional_imports.py           # Graceful optional dependency handling
│   ├── recovery_manager.py           # Crash recovery and checkpointing
│   ├── retry.py                      # Retry logic with exponential backoff
│   ├── sanity_checker.py             # Pre-flight sanity checks
│   ├── utils.py                      # General-purpose utilities
│   ├── validation_suite.py           # Validation test suites
│   └── xml_utils.py                  # XML parsing and generation utilities
│
├── converters/                       # Disk transformation engines
│   ├── __init__.py
│   ├── disk_resizer.py               # Disk resizing operations
│   ├── fetch.py                      # Unified disk fetching interface
│   ├── flatten.py                    # Snapshot chain flattening
│   ├── extractors/                   # Archive/container extractors
│   │   ├── __init__.py
│   │   ├── ami.py                    # AWS AMI tarball extractor
│   │   ├── ovf.py                    # OVF/OVA unpacker
│   │   ├── raw.py                    # RAW/tarball extractor with security checks
│   │   └── vhd.py                    # VHD/VHDX handler (Azure/Hyper-V)
│   └── qemu/                         # QEMU image operations
│       ├── __init__.py
│       └── converter.py              # qemu-img wrapper (convert, resize, info)
│
├── fixers/                           # Guest OS repair and modification layer
│   ├── __init__.py
│   ├── base_fixer.py                 # Base class defining fixer interface
│   ├── cloud_init_injector.py        # Cloud-init metadata injection
│   ├── network_fixer.py              # Top-level network fixer coordinator
│   ├── offline_fixer.py              # Top-level offline fixer coordinator
│   ├── report_writer.py              # Migration report generation
│   │
│   ├── bootloader/                   # Bootloader fixing subsystem
│   │   ├── __init__.py
│   │   ├── fixer.py                  # Bootloader fixer orchestration
│   │   └── grub.py                   # GRUB/GRUB2 specific fixes
│   │
│   ├── filesystem/                   # Filesystem fixing subsystem
│   │   ├── __init__.py
│   │   ├── fixer.py                  # Filesystem fixer orchestration
│   │   └── fstab.py                  # /etc/fstab rewriting (UUID conversion)
│   │
│   ├── live/                         # Live (SSH-based) fixing subsystem
│   │   ├── __init__.py
│   │   ├── fixer.py                  # Live SSH fixer
│   │   └── grub_fixer.py             # Live GRUB regeneration via SSH
│   │
│   ├── network/                      # Network fixing subsystem
│   │   ├── __init__.py
│   │   ├── backend.py                # Network backend abstraction
│   │   ├── core.py                   # Core network fixing logic
│   │   ├── discovery.py              # Network interface discovery
│   │   ├── model.py                  # Network configuration models
│   │   ├── topology.py               # Network topology analysis
│   │   └── validation.py             # Network config validation
│   │
│   ├── offline/                      # Offline (guestfs backend) fixing subsystem
│   │   ├── __init__.py
│   │   ├── config_rewriter.py        # System config file rewriting
│   │   ├── mount.py                  # Guest filesystem mounting
│   │   ├── spec_converter.py         # Spec file format conversions
│   │   ├── validation.py             # Offline fix validation
│   │   └── vmware_tools_remover.py   # Offline VMware Tools purge
│   │
│   └── windows/                      # Windows-specific fixing subsystem
│       ├── __init__.py
│       ├── fixer.py                  # Main Windows fixer orchestrator
│       ├── network_fixer.py          # Windows network fixing
│       ├── registry_core.py          # Registry manipulation core
│       ├── registry/                 # Windows Registry subsystem
│       │   ├── __init__.py
│       │   ├── encoding.py           # Registry value encoding/decoding
│       │   ├── firstboot.py          # First-boot registry tweaks
│       │   ├── io.py                 # Registry file I/O (hivex wrapper)
│       │   ├── mount.py              # Registry hive mounting
│       │   ├── software.py           # HKLM\Software modifications
│       │   └── system.py             # HKLM\System modifications
│       └── virtio/                   # Windows VirtIO driver injection
│           ├── __init__.py
│           ├── config.py             # VirtIO configuration
│           ├── core.py               # Core VirtIO injection logic
│           ├── detection.py          # VirtIO ISO detection
│           ├── discovery.py          # Driver discovery in VirtIO ISO
│           ├── install.py            # Driver installation to registry
│           ├── paths.py              # VirtIO ISO path resolution
│           └── utils.py              # VirtIO utilities
│
├── libvirt/                          # LibVirt integration layer
│   ├── domain_emitter.py             # Generic domain XML emitter
│   ├── libvirt_utils.py              # LibVirt utility functions
│   ├── linux_domain.py               # Linux-specific domain XML generation
│   └── windows_domain.py             # Windows-specific domain XML generation
│
├── modes/                            # Specialized operational modes
│   ├── __init__.py
│   ├── inventory_mode.py             # Read-only VM/disk inventory scanning
│   └── plan_mode.py                  # Dry-run planning mode (what-if)
│
├── orchestrator/                     # Pipeline orchestration layer
│   ├── __init__.py
│   ├── README.md                     # Refactoring documentation
│   ├── orchestrator.py               # Main pipeline coordinator (refactored)
│   ├── disk_discovery.py             # Input disk discovery logic
│   ├── disk_processor.py             # Disk processing pipeline executor
│   └── vsphere_exporter.py           # vSphere VM export orchestration
│
├── ssh/                              # SSH/SCP transport layer
│   ├── __init__.py
│   ├── ssh_client.py                 # Paramiko-based SSH client
│   └── ssh_config.py                 # SSH connection configuration
│
├── testers/                          # Post-migration validation layer
│   ├── __init__.py
│   ├── libvirt_tester.py             # LibVirt domain boot testing
│   └── qemu_tester.py                # Direct QEMU boot testing
│
└── vmware/                           # VMware ecosystem integration
    ├── __init__.py
    ├── clients/                      # VMware API clients
    │   ├── __init__.py
    │   ├── client.py                 # pyvmomi SmartConnect wrapper
    │   ├── extensions.py             # vSphere API extensions
    │   └── nfc_lease.py              # NFC lease management for exports
    │
    ├── transports/                   # Data-plane transport implementations
    │   ├── __init__.py
    │   ├── govc_common.py            # govc CLI wrapper utilities
    │   ├── govc_export.py            # govc export operations
    │   ├── http_client.py            # HTTP datastore download client
    │   ├── http_progress.py          # HTTP download progress tracking
    │   ├── ovftool_client.py         # VMware ovftool wrapper
    │   ├── ovftool_loader.py         # ovftool dynamic loader
    │   ├── vddk_client.py            # VDDK high-speed transfer client
    │   └── vddk_loader.py            # VDDK dynamic library loader
    │
    ├── utils/                        # VMware utilities
    │   ├── __init__.py
    │   ├── datastore.py              # Datastore path parsing
    │   ├── utils.py                  # General VMware utilities
    │   └── vmdk_parser.py            # VMDK descriptor file parser
    │
    └── vsphere/                      # vSphere control-plane operations
        ├── __init__.py
        ├── command.py                # vSphere command abstraction
        ├── errors.py                 # vSphere error handling
        ├── govc.py                   # govc-specific operations
        └── mode.py                   # vSphere operational modes
```bash

**Total:** 27 directories, 117+ Python modules
```
---

## Orchestrator Architecture (Refactored)

The orchestrator was refactored from a single 1,197-line monolithic class into **4 focused components**, each under 300 lines and following the Single Responsibility Principle.

### Component Breakdown

#### 1. **Orchestrator** (`orchestrator/orchestrator.py`)
**Responsibility:** Main pipeline coordinator

**Key Methods:**
- `run()` - Execute full migration pipeline
- `_setup_recovery()` - Initialize crash recovery
- `_discover_disks()` - Delegate to DiskDiscovery
- `_process_disks()` - Delegate to DiskProcessor
- `_run_tests()` - Execute validation tests
- `_emit_domain_xml()` - Generate libvirt domain XML

**Philosophy:** Coordinate, don't implement. Delegate to specialists.

#### 2. **DiskDiscovery** (`orchestrator/disk_discovery.py`)
**Responsibility:** Input disk detection and preparation

**Supported Sources:**
- Local VMDK files
- Remote SSH fetch-and-fix
- OVA/OVF archives
- VHD/VHDX files
- RAW/IMG files
- AMI tarballs
- Live-fix mode (SSH to running guest)

**Output:** List of discovered disk paths + optional temp directory

#### 3. **DiskProcessor** (`orchestrator/disk_processor.py`)
**Responsibility:** Per-disk processing pipeline

**Pipeline Stages:**
1. Flatten (optional snapshot collapse)
2. Offline fixes (guestfs backend modifications)
3. Convert to output format (qemu-img)
4. Validation (sanity checks)

**Features:**
- Serial or parallel processing
- Progress tracking
- Error isolation per-disk

#### 4. **VsphereExporter** (`orchestrator/vsphere_exporter.py`)
**Responsibility:** vSphere VM export orchestration

**Export Modes:**
- Direct export
- Download-only (no conversion)
- VDDK high-speed transfer

**Features:**
- Snapshot management (create/delete)
- Credential resolution (env vars, YAML configs)
- Batch export with failure tracking
- VM name pattern matching

### Refactoring Benefits

| Aspect | Before (Monolithic) | After (Refactored) |
|--------|---------------------|-------------------|
| **Lines of Code** | 1,197 lines, 50+ methods | 4 files, each < 310 lines |
| **Testability** | Difficult to test in isolation | Each component independently testable |
| **Maintainability** | All concerns mixed | Single Responsibility Principle |
| **Reusability** | Tightly coupled | Components usable independently |
| **Debugging** | Hard to isolate failures | Clear component boundaries |

---

## Control-Plane vs Data-Plane (VMware)

VMware integration enforces strict separation between **what to do** (control) and **how to move bytes** (data).

### Control-Plane: Inventory, Planning, Orchestration

**Purpose:** Answer "what exists, where, and what's the plan?"

**Never touches bulk data** - keeps operations lean, fast, and auditable.

#### Implementation 1: govc (Primary)
**Tool:** VMware's official CLI (`govc`)

**Capabilities:**
- VM discovery (by name, UUID, MoRef)
- Snapshot tree traversal
- Disk path resolution (backings, controllers)
- Firmware detection (BIOS/UEFI)
- CBT (Changed Block Tracking) management
- Datastore browsing

**Why govc:**
- Stable, scriptable CLI
- Structured output (JSON)
- Real-world vSphere coverage
- Minimal memory footprint

**Integration:** `vmware/vsphere/govc.py` + `vmware/vsphere/command.py`

#### Implementation 2: pyvmomi / pyVim (Fallback)
**Library:** VMware's official Python SDK

**Use Cases:**
- Deep object graph traversals
- Advanced property queries
- Custom vCenter extensions
- Gaps in govc functionality

**Integration:** `vmware/clients/client.py` - SmartConnect wrapper with retry logic

**Details:**
- SOAP API connections via `SmartConnect`
- MoRef (Managed Object Reference) traversal
- Property retrieval via `RetrievePropertiesEx`
- SSL verification and authentication

#### CLI Glue Layer
**Modules:** `vmware/vsphere/mode.py` + `vmware/vsphere/command.py`

**Function:** Translate user commands (`vsphere inventory`, `vsphere plan`) into pure metadata operations. No data hauling.

---

### Data-Plane: Byte Movement

**Purpose:** Answer "how do we safely move disk data?"

**No inventory logic** - pure transport layer.

#### Transport 1: VDDK (Highest Performance)
**Library:** VMware Virtual Disk Development Kit

**Module:** `vmware/transports/vddk_client.py`

**Features:**
- Direct disk access over NBD or SAN
- Multi-threaded I/O
- CBT support for incremental transfers
- Throughput-optimized

**When to Use:** Large VMs, bandwidth-constrained environments

#### Transport 2: ovftool (Official VMware Export)
**Tool:** VMware OVF Tool

**Module:** `vmware/transports/ovftool_client.py`

**Features:**
- OVF/OVA export/import
- Compression and progress tracking
- OVF manifest validation
- Resumable exports

**When to Use:** Need OVF compatibility, vendor-specific flags

#### Transport 3: HTTP `/folder` (Datastore Downloads)
**Protocol:** HTTPS datastore browsing

**Module:** `vmware/transports/http_client.py`

**Features:**
- Range request support (resume partial downloads)
- CBT incremental downloads
- Stateless (no session management)

**When to Use:** Simple downloads, no VDDK available

#### Transport 4: SSH/SCP (Universal Fallback)
**Protocol:** SSH with SCP/SFTP

**Module:** `ssh/ssh_client.py`

**Features:**
- Key-based authentication
- File transfers with progress
- Command execution on ESXi hosts

**When to Use:** API access unavailable, ESXi direct access

#### Transport 5: govc export (CLI-Based)
**Tool:** govc export.ovf / export.ova

**Module:** `vmware/transports/govc_export.py`

**Features:**
- Simple CLI-based export
- Progress tracking
- Structured error handling

**When to Use:** Lightweight exports, scripting

---

## Fixer Subsystems (Deep Dive)

### Offline Fixing (Default Strategy)

**Module:** `fixers/offline/`

**Philosophy:** Modify disk images without booting. No runtime dependencies.

**Technology:** Guestfs backend (VMCraft by default)

**Advantages:**
- No systemd/init requirements
- No kernel module loading
- Works on corrupted/unbootable guests
- Deterministic outcomes

**Subsystems:**

#### 1. Filesystem Fixing (`fixers/filesystem/`)
- `/etc/fstab` rewriting (by-path → UUID/PARTUUID)
- Mount point validation
- Filesystem consistency checks

#### 2. Bootloader Fixing (`fixers/bootloader/`)
- GRUB configuration regeneration
- Initramfs rebuilding
- Kernel command-line updates
- UEFI boot entry management

#### 3. Config Rewriting (`fixers/offline/config_rewriter.py`)
- Systemd unit modifications
- Network configuration updates
- Service enablement/disablement

#### 4. VMware Tools Removal (`fixers/offline/vmware_tools_remover.py`)
- Package removal (offline dpkg/rpm manipulation)
- Service cleanup
- Artifact deletion

---

### Live Fixing (Opt-In Strategy)

**Module:** `fixers/live/`

**Philosophy:** Execute fixes on running Linux guests via SSH.

**Use Cases:**
- Fixes requiring running kernel (GRUB regeneration)
- Runtime-dependent operations
- Interactive troubleshooting

**Safety:**
- Explicit opt-in required
- Dry-run mode available
- Rollback mechanisms

---

### Windows Fixing (Hermetically Sealed)

**Module:** `fixers/windows/`

**Principle:** Windows logic **never leaks** into Linux fixers. Complete isolation.

#### Registry Subsystem (`fixers/windows/registry/`)

**Purpose:** Modify Windows Registry offline (no Windows boot required)

**Technology:** hivex (offline registry manipulation)

**Operations:**
- Driver installation (VirtIO, storage, network)
- Service configuration
- First-boot scripts
- Hardware profile updates

**Modules:**
- `io.py` - Registry hive I/O (read/write)
- `encoding.py` - Registry value encoding
- `mount.py` - Hive mounting (SYSTEM, SOFTWARE, SAM)
- `firstboot.py` - First-boot tweaks
- `software.py` - HKLM\Software modifications
- `system.py` - HKLM\System modifications (drivers, services)

#### VirtIO Subsystem (`fixers/windows/virtio/`)

**Purpose:** Inject VirtIO drivers for KVM compatibility

**Challenge:** Windows won't boot on KVM without VirtIO drivers, but drivers can't be installed without booting.

**Solution:** Offline registry modification to pre-install drivers.

**Workflow:**
1. **Detection** (`detection.py`) - Locate VirtIO ISO (local/remote)
2. **Discovery** (`discovery.py`) - Extract drivers matching guest OS version
3. **Installation** (`install.py`) - Add driver registry entries
4. **Configuration** (`config.py`) - Configure driver load order

**Drivers Injected:**
- `viostor` - Storage controller
- `netkvm` - Network adapter
- `vioscsi` - SCSI controller
- `viorng` - RNG device
- `balloon` - Memory ballooning

---

### Network Fixing (Cross-Platform)

**Module:** `fixers/network/`

**Architecture:** Modular backend system supporting multiple network managers.

**Backends Supported:**
- NetworkManager (RHEL/Fedora/CentOS)
- netplan (Ubuntu/Debian)
- systemd-networkd
- ifupdown (legacy Debian)
- Windows network stack (separate module)

**Components:**

#### Discovery (`discovery.py`)
- Detect network interfaces (physical/virtual)
- Identify MAC addresses and interface names
- Detect existing configuration files

#### Topology (`topology.py`)
- Build network topology map
- Detect bridging/bonding
- VLAN detection

#### Core (`core.py`)
- Apply network fixes
- Generate new configurations
- Remove VMware-specific settings

#### Validation (`validation.py`)
- Validate network configurations
- Check for conflicts
- Ensure bootability

#### Backend (`backend.py`)
- Abstract network manager differences
- Unified configuration API
- Backend auto-detection

**Fixes Applied:**
- Remove MAC address pinning
- Delete VMware-specific routes
- Clean up stale interface configs
- Regenerate predictable interface names
- Configure for DHCP (default)

---

## LibVirt Integration

**Module:** `libvirt/`

**Purpose:** Generate libvirt domain XML for migrated VMs

**Components:**

### Domain Emitter (`domain_emitter.py`)
Generic XML generation framework

### Linux Domain (`linux_domain.py`)
Linux-specific domain XML:
- Virtio devices (disk, network, RNG)
- CPU topology
- Memory configuration
- BIOS/UEFI firmware selection
- Multi-NIC support (`nic_count` from OVF detection generates multiple `<interface>` elements)
- Multi-disk support (`additional_disks` generates extra `<disk>` elements with sequential device letters)
- Secure Boot support (`secure_boot` flag resolves `.secboot.fd` OVMF code/vars, adds `secure='yes'` to `<loader>`)

### Windows Domain (`windows_domain.py`)
Windows-specific domain XML:
- Hyper-V enlightenments
- QEMU guest agent
- VirtIO device configuration
- UEFI with Secure Boot support

**Output:** Ready-to-import libvirt XML (`virsh define domain.xml`)

---

## Core Utilities

**Module:** `core/`

The foundational layer providing infrastructure for all other modules.

### Essential Utilities

#### Guest Identity (`guest_identity.py`)
- OS detection (Linux distro, Windows version)
- Architecture detection (x86_64, aarch64)
- Kernel version parsing

#### Recovery Manager (`recovery_manager.py`)
- Crash recovery checkpoints
- Resume from partial migrations
- Cleanup on abort

#### Retry Logic (`retry.py`)
- Exponential backoff
- Configurable retry limits
- Exception filtering

#### Validation Suite (`validation_suite.py`)
- Pre-flight sanity checks
- Post-migration validation
- Regression test framework

#### File Operations (`file_ops.py`)
- Safe file I/O with atomic writes
- Temporary file management
- Checksum verification

#### Logging (`logger.py`, `logging_utils.py`)
- Rich console output (colors, progress bars)
- Structured logging (JSON)
- Log level management

---

## VMCraft - VM Manipulation Engine

**Module:** `core/vmcraft/`

**Version:** v9.0

VMCraft is hyper2kvm's pure Python disk image manipulation platform, serving as the primary VM inspection and modification engine.

### Architecture

VMCraft consists of **57 specialized modules** organized into focused categories:

```
core/vmcraft/
├── main.py                    # Orchestrator
├── Core Infrastructure (4 modules)
│   ├── nbd.py                 # NBD device management
│   ├── storage.py             # LVM/LUKS/RAID/ZFS
│   ├── mount.py               # Filesystem mounting
│   └── file_ops.py            # File operations (70+ methods)
├── OS Detection (3 modules)
│   ├── inspection.py          # Orchestration
│   ├── linux_detection.py     # 15+ Linux distros
│   └── windows_detection.py   # 20+ Windows versions
├── Windows Support (6 modules)
│   ├── windows_registry.py    # Registry operations
│   ├── windows_drivers.py     # Driver injection
│   ├── windows_users.py       # User management
│   ├── windows_services.py    # Service control
│   ├── windows_applications.py # App detection
│   └── scheduled_tasks.py     # Task Scheduler
├── Linux Support (1 module)
│   └── linux_services.py      # Systemd/init services
├── Enterprise Intelligence (5 modules)
│   ├── ml_analyzer.py         # AI/ML analytics
│   ├── cloud_optimizer.py     # Cloud migration
│   ├── disaster_recovery.py   # DR planning
│   ├── audit_trail.py         # Compliance logging
│   └── resource_orchestrator.py # Auto-scaling
└── Operational Tools (5 modules)
    ├── backup.py              # Backup/restore
    ├── security.py            # Security auditing
    ├── optimization.py        # Disk optimization
    ├── advanced_analysis.py   # Forensics
    └── export.py              # VM export
```

### Key Capabilities

**Core Operations:**
- **Fast launch:** ~1.9s (NBD connection + storage activation)
- **OS detection:** 15+ Linux distros, 20+ Windows versions
- **File operations:** 70+ methods for comprehensive file manipulation
- **Storage stack:** LVM, LUKS, RAID, ZFS support

**Cross-Platform:**
- **Linux:** Package management, service control, driver analysis
- **Windows:** Registry operations, driver injection, user/service management

**Enterprise Intelligence (v9.0):**
- **AI/ML Analytics:** Anomaly detection, behavior prediction, workload classification
- **Cloud Optimization:** Multi-cloud migration planning (AWS, Azure, GCP)
- **Disaster Recovery:** RTO/RPO planning, backup strategies
- **Audit Trail:** Multi-standard compliance (SOC2, PCI-DSS, HIPAA, GDPR)
- **Resource Orchestration:** Auto-scaling, workload balancing

### Integration with Pipeline

VMCraft integrates into the migration pipeline at these stages:

1. **INSPECT:** OS detection and filesystem analysis
2. **FIX:** Offline file modifications, registry edits, driver injection
3. **VALIDATE:** Pre-migration verification

### Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Launch | ~1.9s | NBD + storage |
| OS Inspection | ~0.3s | Linux/Windows detection |
| File Read | <50ms | Direct filesystem access |
| Registry Read | ~150ms | Windows offline registry |

### Usage in hyper2kvm

```python
from hyper2kvm.vmcraft import VMCraft

with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=False)
    g.launch()

    # OS detection
    roots = g.inspect_os()

    # File operations
    g.write("/etc/motd", "Migrated to KVM\n")

    # Windows registry (if Windows)
    g.win_registry_write("SOFTWARE", r"Microsoft\...", "Key", "Value")

    # AI/ML analytics (v9.0)
    anomalies = g.ml_detect_anomalies(metrics, "cpu")

    # Cloud optimization (v9.0)
    readiness = g.cloud_analyze_readiness(system_info)
```

**Documentation:** See [VMCraft Platform Guide](09-VMCraft.md) for complete reference (307+ methods).

---

## Key Architectural Invariants

These principles are **non-negotiable**. Violating them leads to unreliable migrations.

### 1. Offline is the Default Truth

Unless explicitly marked `live`, all fixers assume:
- **No systemd** or init systems running
- **No kernel modules** can be loaded
- **Only guestfs backend** disk access (VMCraft by default)

**Runtime dependencies belong in `fixers/live/`.**

### 2. Inspection Over Assumption

Never guess. Always derive facts from:
- Guestfs backend inspection
- Partition table analysis
- Filesystem examination
- Bootloader configuration parsing

**Code must handle "unexpected but valid" configurations gracefully.**

### 3. `/dev/disk/by-path` is Radioactive

VMware uses by-path references extensively. KVM **does not**.

**All fixer code must:**
- Detect by-path references in fstab, GRUB configs, crypttab
- Replace with UUID or PARTUUID
- Verify replacement correctness

**This is the #1 cause of boot failures if missed.**

### 4. Windows Logic is Hermetically Sealed

**Windows-specific code lives exclusively in `fixers/windows/`.**

Linux fixers:
- Detect Windows guests
- Immediately return / skip
- **Never attempt** Windows-specific operations

**Cross-contamination is forbidden.**

### 5. Control-Plane and Data-Plane Never Mix

**Control-plane** (`vmware/vsphere/`, `vmware/clients/`):
- Inventory queries
- Metadata operations
- Planning and orchestration

**Data-plane** (`vmware/transports/`):
- Disk downloads
- Byte transfer
- Bandwidth optimization

**No module should perform both.** Separation ensures:
- Auditability (what metadata was collected?)
- Performance (control-plane doesn't bottleneck on I/O)
- Security (minimize attack surface for credential use)

### 6. Idempotent, Best-Effort Behavior

Fixers should:
- **Tolerate re-runs** (detect already-applied fixes)
- **Contain failures** (one fixer failure doesn't abort entire pipeline)
- **Report loudly** (log all actions, successes, and failures)

**Only critical failures (unbootable guest) should halt the pipeline.**

---

## Module Ownership and Responsibilities

### `cli/`
**Owns:** User-facing command-line interface, argument parsing, help text.
**Does NOT own:** Business logic, execution.

### `config/`
**Owns:** Configuration file loading (YAML), merging, defaults.
**Does NOT own:** Configuration validation (done in `core/sanity_checker.py`).

### `core/`
**Owns:** Cross-cutting concerns (logging, errors, retries, recovery, validation).
**Does NOT own:** Domain-specific logic.

### `converters/`
**Owns:** Format conversions (VMDK→qcow2), extractions (OVA, AMI, VHD), disk operations.
**Does NOT own:** Guest OS modifications (that's `fixers/`).

### `fixers/`
**Owns:** Guest OS modifications (offline and live), bootloader fixes, network cleanup, Windows drivers.
**Does NOT own:** Disk format conversions (that's `converters/`).

### `libvirt/`
**Owns:** LibVirt domain XML generation.
**Does NOT own:** QEMU execution (that's `testers/qemu_tester.py`).

### `modes/`
**Owns:** Read-only operational modes (inventory, planning).
**Does NOT own:** Write operations (migrations).

### `orchestrator/`
**Owns:** Pipeline coordination, stage ordering, component delegation.
**Does NOT own:** Stage implementation (delegates to specialists).

### `ssh/`
**Owns:** SSH/SCP transport, remote command execution.
**Does NOT own:** What commands to execute (that's `fixers/live/`).

### `testers/`
**Owns:** Post-migration validation (boot tests, network tests).
**Does NOT own:** Migration itself.

### `vmware/`
**Owns:** VMware-specific integrations (vSphere API, VDDK, govc).
**Does NOT own:** Generic disk operations (that's `converters/`).

---

## Why This Architecture Works

### Predictability
- **Fixed pipeline order** eliminates non-deterministic behavior
- **Inspection-based fixes** remove guesswork
- **Idempotent operations** allow safe retries

### Reliability
- **Offline-first** means no runtime dependencies
- **Hermetic isolation** (Windows, VMware, etc.) prevents cross-contamination
- **Component separation** isolates failures

### Maintainability
- **Single Responsibility Principle** (refactored orchestrator)
- **Clear module boundaries** (ownership table above)
- **Focused components** (all under 300 lines)

### Extensibility
- **Pluggable fixers** (add new fixer, register in orchestrator)
- **Pluggable transports** (add new VMware transport)
- **Pluggable network backends** (add new network manager)

### Debuggability
- **Structured logging** with timestamps and context
- **Component isolation** (easy to trace failures)
- **Validation at every stage** (fail fast with clear errors)

---

## Adding New Features

### Where Does My Feature Go?

#### 1. New Disk Source (e.g., Azure Blob, S3)
**Location:** `converters/extractors/azure.py` or `converters/fetch.py`
**Hook:** Register in `orchestrator/disk_discovery.py`

#### 2. New Fix (e.g., SELinux relabeling)
**Location:** `fixers/offline/selinux_fixer.py` or extend `fixers/offline/config_rewriter.py`
**Hook:** Call from `orchestrator/disk_processor.py`

#### 3. New Network Manager (e.g., wicked for SUSE)
**Location:** `fixers/network/backend.py` (add backend class)
**Hook:** Auto-detected via backend discovery

#### 4. New Validation Test (e.g., storage performance)
**Location:** `testers/storage_tester.py`
**Hook:** Call from `orchestrator/orchestrator.py:_run_tests()`

#### 5. New VMware Transport (e.g., NBD direct)
**Location:** `vmware/transports/nbd_client.py`
**Hook:** Register in `vmware/transports/__init__.py`

### Feature Addition Checklist

1. **Identify module boundary** (don't violate separation of concerns)
2. **Check for existing extension point** (don't duplicate)
3. **Write unit tests** (isolated component tests)
4. **Update this ARCHITECTURE.md** (document new component)
5. **Add integration test** (end-to-end validation)
6. **Update user documentation** (if user-visible feature)

---

## Performance Considerations

### Parallel Processing

#### Disk Processing
**Module:** `orchestrator/disk_processor.py`

**Option:** `args.parallel_processing = True`

**Implementation:** ThreadPoolExecutor (multiple disks processed concurrently)

**When to Use:** Multi-disk VMs (e.g., VM with OS disk + data disks)

### I/O Optimization

#### VDDK (VMware)
**Benefit:** 3-5x faster than HTTP downloads
**Trade-off:** Requires VDDK installation, complex setup

#### Compression
**Benefit:** Smaller output files, faster network transfers
**Trade-off:** CPU overhead during conversion

**Recommendation:** Use compression for network transfers, skip for local migrations.

---

## Testing Strategy

### Unit Tests
**Location:** `tests/unit/`

**Coverage:**
- Core utilities (`core/`)
- Converters (`converters/`)
- Fixers (`fixers/`)
- Network backends (`fixers/network/`)

**Technology:** pytest, pytest-mock

### Integration Tests
**Location:** `tests/integration/`

**Coverage:**
- End-to-end pipelines
- Multi-stage workflows
- VMware integration (mocked vSphere API)

### Security Tests
**Runs:** GitHub Actions (Bandit, pip-audit)

**Focus:**
- Path traversal prevention (`converters/extractors/raw.py`)
- Symlink attacks
- Command injection
- Credential leakage

---

## Future Architecture Directions

### Plugin System
Allow third-party fixers, transports, and validators without modifying core code.

**Design:**
- Entry point discovery (setuptools entry points)
- Plugin registration API
- Isolated plugin execution (sandboxing)

### Cloud-Native Integration
Direct export to cloud providers without intermediate storage.

**Candidates:**
- AWS (EC2 import, S3 streaming)
- Azure (Managed Disk import, Blob streaming)
- GCP (Compute Engine import, GCS streaming)

**Module:** `converters/cloud/` (new)

### Advanced Recovery
Transactional migrations with automatic rollback on failure.

**Design:**
- Snapshot source VM before migration
- Checkpoint every pipeline stage
- Rollback to last good state on failure

**Module:** Enhanced `core/recovery_manager.py`

### Metrics and Telemetry
Real-time progress tracking and performance metrics.

**Design:**
- Prometheus exporter
- JSON logs for structured analysis
- Performance profiling hooks

**Module:** `core/metrics.py` (new)

---

## Glossary

**guestfs backend:** Abstraction for accessing and modifying virtual machine disk images offline. VMCraft is the default backend.

**VDDK:** VMware Virtual Disk Development Kit - high-performance API for disk access.

**govc:** VMware's official CLI for vSphere operations.

**pyvmomi:** VMware's official Python SDK for vSphere SOAP API.

**VirtIO:** Paravirtualized I/O drivers for KVM (storage, network, RNG, balloon).

**hivex:** Library for reading and writing Windows Registry hive files.

**NBD:** Network Block Device - protocol for accessing block devices over network.

**CBT:** Changed Block Tracking - VMware feature for incremental backups.

**MoRef:** Managed Object Reference - vSphere API identifier for objects.

**NFC:** Network File Copy - VMware protocol for efficient VM export.

---


## Code Examples

### Example 1: Basic Pipeline Usage

```python
from hyper2kvm.orchestrator.disk_processor import DiskProcessor
from hyper2kvm.core.guest_identity import GuestIdentity

# Initialize processor
processor = DiskProcessor()

# Process a VMDK
result = processor.process_disk(
    source_path='/data/vm.vmdk',
    output_path='/data/vm.qcow2',
    flatten=True,
    compress=True
)

# Inspect guest OS
identity = GuestIdentity.from_disk('/data/vm.qcow2')
print(f"OS: {identity.os_family}")
print(f"Firmware: {identity.firmware_type}")
```

### Example 2: Custom Fixer

```python
from hyper2kvm.fixers.offline_fixer import OfflineFixer

# Create fixer instance
fixer = OfflineFixer('/data/vm.qcow2')

# Apply specific fixes
fixer.fix_fstab(use_uuid=True)
fixer.fix_grub(regenerate=True)
fixer.fix_network(clean_mac=True)

# Verify fixes
fixer.validate()
```

### Example 3: vSphere Integration

```python
from hyper2kvm.vmware.clients.client import VMwareClient

# Connect to vCenter
client = VMwareClient(
    host='vcenter.example.com',
    username='administrator@vsphere.local',
    password='password'
)

# Export VM
await client.async_export_vm(
    vm_name='production-web',
    output_dir='/data/exports',
    export_mode='export'
)
```


## Contributing

When proposing architectural changes:

1. **Open an issue first** (discuss design before implementation)
2. **Follow existing patterns** (don't introduce new paradigms without justification)
3. **Respect module boundaries** (don't mix concerns)
4. **Add tests** (unit + integration)
5. **Update documentation** (this file + module docstrings)
6. **Keep classes focused** (under 300 lines when possible)

---

## Summary

hyper2kvm's architecture achieves **reliable, repeatable VM migrations** through:

1. **Deterministic pipeline** (FETCH → FLATTEN → INSPECT → PLAN → FIX → CONVERT → TEST)
2. **Offline-first fixing** (guestfs backend via VMCraft, no runtime dependencies)
3. **Strict separation** (control-plane vs data-plane, offline vs live, Windows vs Linux)
4. **Modular components** (Single Responsibility Principle)
5. **Inspection over assumption** (derive facts, never guess)
6. **Idempotent operations** (safe to retry)

**The result:** Migrations that "just work" - boring, predictable, and successful.

**Boring migrations are successful migrations.**
