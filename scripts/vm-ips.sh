#!/usr/bin/env bash
set -euo pipefail
# vm-ips.sh — Show all running VMs and their IPs
printf "%-40s %-18s %-20s\n" "VM Name" "State" "IP Address"
printf '%.0s─' {1..78}; echo
for vm in $(virsh list --name 2>/dev/null); do
    [[ -z "$vm" ]] && continue
    state=$(virsh domstate "$vm" 2>/dev/null)
    ip=$(virsh domifaddr "$vm" --source lease 2>/dev/null | awk '/ipv4/{print $4}' | cut -d/ -f1)
    [[ -z "$ip" ]] && ip=$(virsh domifaddr "$vm" --source arp 2>/dev/null | awk '/ipv4/{print $4}' | cut -d/ -f1)
    [[ -z "$ip" ]] && ip="(no IP yet)"
    printf "%-40s %-18s %-20s\n" "$vm" "$state" "$ip"
done
