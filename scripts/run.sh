#!/bin/bash
# Simple wrapper to run h2kvm from project directory
set -euo pipefail

# Check if no arguments provided or help requested
if [ $# -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    cat <<'EOF'
h2kvm: Ultimate VMware → KVM/QEMU Converter + Fixer

USAGE:
    sudo ./run.sh --config <yaml-file>
    sudo ./run.sh [OPTIONS]

REQUIRED:
    --config FILE           Path to YAML configuration file(s)
                           (can be specified multiple times)

YAML FILE MUST INCLUDE:
    command: <cmd>          One of: local, fetch-and-fix, ova, ovf, vhd, ami,
                           live-fix, vsphere, daemon, generate-systemd

COMMON OPTIONS:
    -h, --help             Show detailed help with examples
    -v, -vv                Increase verbosity
    --dry-run              Preview changes without modifying anything
    --dump-config          Show merged configuration and exit
    --dump-args            Show parsed arguments and exit

QUICK START EXAMPLES:

  1. Local VMDK conversion:
     sudo ./run.sh --config examples/local.yaml

  2. Fetch from ESXi:
     sudo ./run.sh --config examples/esxi-fetch.yaml

  3. vSphere export:
     sudo ./run.sh --config examples/vsphere-export.yaml

  4. Live fix via SSH:
     sudo ./run.sh --config examples/live-fix.yaml

  5. Dry-run preview:
     sudo ./run.sh --config myvm.yaml --dry-run -vv

EXAMPLE YAML CONFIG (local.yaml):
    command: local
    vmdk: /path/to/vm.vmdk
    output_dir: ./out
    flatten: true
    to_output: vm-fixed.qcow2
    out_format: qcow2
    compress: true
    fstab_mode: stabilize-all
    regen_initramfs: true

For detailed help, examples, and all options:
    sudo ./run.sh --help (once with --config specified)

Or view inline documentation:
    less h2kvm/cli/help_texts.py

Documentation:
    docs/README.md
    docs/98-Enhanced-Features.md
    docs/TUI_DASHBOARD.md

EOF
    exit 0
fi

cd "$(dirname "$0")"
exec sudo python3 -m h2kvm "$@"
