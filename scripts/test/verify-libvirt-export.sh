#!/bin/bash
set -euo pipefail
# Verification script for libvirt export

echo "=== Libvirt Export Verification ==="
echo ""

echo "1. Checking libvirt VMs:"
virsh list --all | grep -E "opensuse-leap-15.4|fedora43-cloud" || echo "VMs not found!"
echo ""

echo "2. Checking VM details:"
echo "--- openSUSE Leap 15.4 ---"
virsh dominfo opensuse-leap-15.4 | grep -E "Name|State|CPU|memory"
echo ""
echo "--- Fedora Cloud 43 ---"
virsh dominfo fedora43-cloud | grep -E "Name|State|CPU|memory"
echo ""

echo "3. Checking disk images:"
virsh domblklist opensuse-leap-15.4
virsh domblklist fedora43-cloud
echo ""

echo "4. Checking network configuration:"
virsh domiflist opensuse-leap-15.4 | head -3
virsh domiflist fedora43-cloud | head -3
echo ""

echo "5. Verifying XML files exist:"
ls -lh /home/ssahani/tt/h2kvm/out/opensuse-leap-test/opensuse-leap-15.4.xml
ls -lh /home/ssahani/tt/h2kvm/out/fedora43-cloud-test/fedora43-cloud.xml
echo ""

echo "✅ Verification complete!"
echo ""
echo "To start VMs:"
echo "  virsh start opensuse-leap-15.4"
echo "  virsh start fedora43-cloud"
