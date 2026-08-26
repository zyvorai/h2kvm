#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# nuke-libvirt.sh — Remove ALL libvirt domains, networks, pools, and hyper2kvm artifacts
#
# Usage:
#   sudo ./scripts/nuke-libvirt.sh                    # interactive (asks for confirmation)
#   sudo ./scripts/nuke-libvirt.sh --force             # no prompts
#   sudo ./scripts/nuke-libvirt.sh --keep-networks     # skip network removal
#   sudo ./scripts/nuke-libvirt.sh --force --keep-networks
#
# WARNING: This is destructive and irreversible. It will:
#   1. Destroy and undefine every libvirt domain (VM) + their snapshots and NVRAM
#   2. Destroy and undefine every virtual network (unless --keep-networks)
#   3. Destroy and undefine every storage pool + delete its contents
#   4. Remove hyper2kvm conversion cache and AI knowledge base
#
set -euo pipefail

# Detect the real user's home directory (works under sudo)
if [[ -n "${SUDO_USER:-}" ]]; then
    USER_HOME="$(eval echo ~"$SUDO_USER")"
else
    USER_HOME="${HOME:-$(eval echo ~"$(whoami)")}"
fi

FORCE=false
KEEP_NETWORKS=false
for arg in "$@"; do
    case "$arg" in
        --force|-f)       FORCE=true ;;
        --keep-networks)  KEEP_NETWORKS=true ;;
    esac
done

log()  { printf "[+] %s\n" "$*"; }
warn() { printf "[!] %s\n" "$*"; }
err()  { printf "[✗] %s\n" "$*"; }

# ── preflight ──────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo)."
    exit 1
fi

if ! command -v virsh &>/dev/null; then
    err "virsh not found. Is libvirt installed?"
    exit 1
fi

# ── gather inventory ───────────────────────────────────────────────────
ALL_DOMAINS=$(virsh list --all --name 2>/dev/null | grep -v '^$' || true)
RUNNING_DOMAINS=$(virsh list --name 2>/dev/null | grep -v '^$' || true)
ALL_NETS=$(virsh net-list --all --name 2>/dev/null | grep -v '^$' || true)
ALL_POOLS=$(virsh pool-list --all --name 2>/dev/null | grep -v '^$' || true)

count_lines() { if [[ -z "$1" ]]; then echo 0; else echo "$1" | wc -l; fi; }
DOMAIN_COUNT=$(count_lines "$ALL_DOMAINS")
NET_COUNT=$(count_lines "$ALL_NETS")
POOL_COUNT=$(count_lines "$ALL_POOLS")

echo ""
printf "╔══════════════════════════════════════════════════════════╗\n"
printf "║          LIBVIRT FULL CLEANUP — DESTRUCTIVE              ║\n"
printf "╚══════════════════════════════════════════════════════════╝\n"
echo ""
echo "This will remove:"
echo "  Domains (VMs):      $DOMAIN_COUNT"
if [[ "$KEEP_NETWORKS" == true ]]; then
    echo "  Virtual networks:   (skipped — --keep-networks)"
else
    echo "  Virtual networks:   $NET_COUNT"
fi
echo "  Storage pools:      $POOL_COUNT"
echo "  hyper2kvm cache:    ~/.cache/hyper2kvm/"
echo ""

if [[ "$DOMAIN_COUNT" -eq 0 && "$NET_COUNT" -eq 0 && "$POOL_COUNT" -eq 0 ]]; then
    log "Nothing to clean up — no domains, networks, or pools found."
    # Still clean up hyper2kvm cache artifacts
    log "Cleaning hyper2kvm artifacts..."
    for cache_dir in \
        "$USER_HOME/.cache/hyper2kvm" \
        "/var/lib/hyper2kvm/conversions"; do
        if [[ -d "$cache_dir" ]]; then
            rm -rf "$cache_dir"
            log "  Removed: $cache_dir"
        fi
    done
    exit 0
fi

if [[ "$FORCE" != true ]]; then
    printf "Type 'YES' to confirm total destruction: "
    read -r confirm
    if [[ "$confirm" != "YES" ]]; then
        warn "Aborted."
        exit 1
    fi
fi

echo ""

# ── 1. Destroy and undefine all domains ────────────────────────────────
if [[ -n "$ALL_DOMAINS" ]]; then
    log "Removing $DOMAIN_COUNT domain(s)..."
    while IFS= read -r dom; do
        [[ -z "$dom" ]] && continue

        # Delete all snapshots first
        SNAPS=$(virsh snapshot-list "$dom" --name 2>/dev/null | grep -v '^$' | grep -v '^[[:space:]]*$' || true)
        if [[ -n "$SNAPS" ]]; then
            while IFS= read -r snap; do
                [[ -z "$snap" ]] && continue
                virsh snapshot-delete "$dom" "$snap" &>/dev/null || true
                log "  Deleted snapshot: $dom/$snap"
            done <<< "$SNAPS"
        fi

        # Destroy if running
        if echo "$RUNNING_DOMAINS" | grep -qx "$dom" 2>/dev/null; then
            virsh destroy "$dom" &>/dev/null || true
            log "  Destroyed (stopped): $dom"
        fi

        # Remove managed save state if any
        virsh managedsave-remove "$dom" &>/dev/null || true

        # Undefine with all storage and NVRAM
        if virsh undefine "$dom" --remove-all-storage --nvram &>/dev/null; then
            log "  Undefined (with storage + NVRAM): $dom"
        elif virsh undefine "$dom" --remove-all-storage &>/dev/null; then
            log "  Undefined (with storage): $dom"
        elif virsh undefine "$dom" --nvram &>/dev/null; then
            log "  Undefined (with NVRAM): $dom"
        elif virsh undefine "$dom" &>/dev/null; then
            log "  Undefined: $dom"
        else
            err "  Failed to undefine: $dom"
        fi
    done <<< "$ALL_DOMAINS"
else
    log "No domains to remove."
fi

# ── 2. Destroy and undefine all networks ───────────────────────────────
if [[ "$KEEP_NETWORKS" == true ]]; then
    log "Skipping network removal (--keep-networks)."
elif [[ -n "$ALL_NETS" ]]; then
    log "Removing $NET_COUNT network(s)..."
    while IFS= read -r net; do
        [[ -z "$net" ]] && continue

        # Destroy if active
        virsh net-destroy "$net" &>/dev/null || true

        # Disable autostart
        virsh net-autostart "$net" --disable &>/dev/null || true

        # Undefine
        if virsh net-undefine "$net" &>/dev/null; then
            log "  Removed network: $net"
        else
            err "  Failed to remove network: $net"
        fi
    done <<< "$ALL_NETS"
else
    log "No networks to remove."
fi

# ── 3. Destroy and undefine all storage pools ──────────────────────────
if [[ -n "$ALL_POOLS" ]]; then
    log "Removing $POOL_COUNT storage pool(s)..."
    while IFS= read -r pool; do
        [[ -z "$pool" ]] && continue

        # Delete all volumes in the pool
        VOLS=$(virsh vol-list "$pool" 2>/dev/null | awk 'NR>2 && NF{print $1}' || true)
        if [[ -n "$VOLS" ]]; then
            while IFS= read -r vol; do
                [[ -z "$vol" ]] && continue
                virsh vol-delete "$vol" --pool "$pool" &>/dev/null || true
                log "  Deleted volume: $pool/$vol"
            done <<< "$VOLS"
        fi

        # Destroy if active
        virsh pool-destroy "$pool" &>/dev/null || true

        # Undefine
        if virsh pool-undefine "$pool" &>/dev/null; then
            log "  Removed pool: $pool"
        else
            err "  Failed to remove pool: $pool"
        fi
    done <<< "$ALL_POOLS"
else
    log "No storage pools to remove."
fi

# ── 4. Clean up hyper2kvm artifacts ────────────────────────────────────
log "Cleaning hyper2kvm artifacts..."
for cache_dir in \
    "$USER_HOME/.cache/hyper2kvm" \
    "/var/lib/hyper2kvm/conversions"; do
    if [[ -d "$cache_dir" ]]; then
        rm -rf "$cache_dir"
        log "  Removed: $cache_dir"
    fi
done

# ── done ───────────────────────────────────────────────────────────────
echo ""
log "Cleanup complete."

# Show remaining state
REMAINING=$(virsh list --all --name 2>/dev/null | grep -c '[^ ]' || true)
if [[ "$REMAINING" -gt 0 ]]; then
    warn "Warning: $REMAINING domain(s) still remain (may need manual removal)."
else
    log "All libvirt resources removed."
fi
