#!/usr/bin/env bash
# Launch zkvm TUI with vSphere credentials pre-loaded.
set -euo pipefail

export GOVC_URL="${GOVC_URL:?Set GOVC_URL to your vCenter address (e.g. https://vcenter.example.com/sdk)}"
export GOVC_USERNAME="${GOVC_USERNAME:-administrator@vsphere.local}"
export GOVC_PASSWORD="${GOVC_PASSWORD:?Set GOVC_PASSWORD environment variable}"
export GOVC_DATACENTER="${GOVC_DATACENTER:-data}"
export GOVC_INSECURE="${GOVC_INSECURE:-1}"

exec sudo \
    GOVC_URL="$GOVC_URL" \
    GOVC_USERNAME="$GOVC_USERNAME" \
    GOVC_PASSWORD="$GOVC_PASSWORD" \
    GOVC_DATACENTER="$GOVC_DATACENTER" \
    GOVC_INSECURE="$GOVC_INSECURE" \
    ./zkvm/zkvm "$@"
