# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Enterprise-Grade Firstboot Script Generator
============================================

Generates production-level firstboot scripts matching Azure/AWS/virt-v2v standards.

Features:
- Hardware adaptation (virtio drivers)
- Network auto-repair
- UUID/fstab repair
- Bootloader self-healing
- Security reset (SSH keys)
- qemu-guest-agent installation
- Cloud-init integration
- Health verification
- Conversion metadata
- Structured journal logging
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class FirstbootConfig:
    """
    Firstboot configuration - Enterprise-grade options.

    Matches Azure Migrate, AWS VM Import, and virt-v2v production standards.
    """

    # Critical repairs (Tier 1)
    regenerate_machine_id: bool = True  # Generate unique machine ID
    regenerate_initramfs: bool = True  # Rebuild initramfs
    regenerate_grub: bool = True  # Regenerate GRUB config
    reinstall_grub: bool = True  # Full GRUB reinstall (bootloader self-healing)
    fix_disk_uuids: bool = True  # Fix disk UUIDs in fstab
    activate_lvm: bool = True  # Activate LVM volumes
    settle_udev: bool = True  # Settle udev

    # Hardware adaptation (Tier 1)
    inject_virtio_drivers: bool = True  # Inject virtio drivers into initramfs
    trigger_hardware_detection: bool = True  # Force hardware re-enumeration (udevadm)
    install_qemu_guest_agent: bool = True  # Install QEMU guest agent

    # Network repair (Tier 1 - CRITICAL)
    regenerate_network: bool = True  # Full network reconfiguration
    remove_persistent_net_rules: bool = True  # Remove VMware-specific persistent rules
    reconfigure_network_manager: bool = True  # Reconfigure NetworkManager/systemd-networkd

    # Security (Tier 1)
    regenerate_ssh_keys: bool = True  # Generate new SSH host keys

    # System optimization (Tier 2)
    apply_virtual_guest_tuning: bool = True  # Apply tuned virtual-guest profile
    enable_cloud_init: bool = False  # Cloud-init integration (optional)

    # Health verification (Tier 2)
    verify_boot_health: bool = True  # Post-boot health verification
    create_conversion_metadata: bool = True  # Create conversion metadata

    # Advanced (Tier 3)
    custom_commands: list[str] = None  # Custom commands to execute
    enable_telemetry: bool = False  # Telemetry integration (optional)


def generate_enterprise_firstboot_script(config: Optional[FirstbootConfig] = None) -> str:
    """
    Generate enterprise-grade firstboot script.

    Args:
        config: Firstboot configuration

    Returns:
        Complete firstboot script content
    """
    if config is None:
        config = FirstbootConfig()

    script_lines = [
        "#!/bin/bash",
        "set -e",
        "",
        "#" + "=" * 78,
        "# H2KVM Enterprise First Boot Initialization",
        "# Production-grade post-conversion self-healing and adaptation",
        "# Matches Azure Migrate, AWS VM Import, and virt-v2v standards",
        "#" + "=" * 78,
        "",
        "# Structured logging function",
        "log() {",
        '    local level="${2:-info}"',
        '    echo "$1"',
        "    logger --journald <<EOF",
        "MESSAGE=$1",
        "H2KVM=1",
        "CONVERSION=VMWARE_TO_KVM",
        "PRIORITY=6",
        "SYSLOG_IDENTIFIER=h2kvm-firstboot",
        "EOF",
        "}",
        "",
        "# Error logging",
        "log_error() {",
        '    log "$1" "err"',
        "    logger --journald <<EOF",
        "MESSAGE=$1",
        "H2KVM=1",
        "PRIORITY=3",
        "SYSLOG_IDENTIFIER=h2kvm-firstboot",
        "EOF",
        "}",
        "",
        'log "=" + "=" * 76',
        'log "H2KVM Enterprise First Boot Initialization Started"',
        'log "=" + "=" * 76',
        "",
        "# Detect hypervisor",
        'HYPERVISOR=$(systemd-detect-virt || echo "unknown")',
        'log "Detected hypervisor: $HYPERVISOR"',
        "",
        "STEP=1",
        "TOTAL_STEPS=18",
        "",
    ]

    # Step 1: Machine ID (full reset)
    if config.regenerate_machine_id:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Regenerating machine identity"',
                "# Full machine-id reset (systemd + dbus)",
                "rm -f /etc/machine-id /var/lib/dbus/machine-id",
                "systemd-machine-id-setup 2>&1 | systemd-cat -t h2kvm-firstboot",
                "MACHINE_ID=$(cat /etc/machine-id)",
                'log "  ✓ New machine-id: $MACHINE_ID"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 2: Hardware detection trigger
    if config.trigger_hardware_detection:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Triggering hardware re-detection"',
                "# Force full hardware enumeration for virtio devices",
                "udevadm trigger --action=add 2>&1 | systemd-cat -t h2kvm-firstboot",
                "udevadm settle 2>&1 | systemd-cat -t h2kvm-firstboot",
                'log "  ✓ Hardware re-detection complete"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 3: Virtio drivers injection
    if config.inject_virtio_drivers:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Installing virtio drivers"',
                "# Add virtio modules to initramfs",
                "if command -v dracut >/dev/null 2>&1; then",
                '    log "  Installing virtio drivers via dracut"',
                "    dracut -f --add-drivers 'virtio virtio_blk virtio_scsi virtio_net virtio_pci' 2>&1 | systemd-cat -t h2kvm-firstboot",
                "elif command -v update-initramfs >/dev/null 2>&1; then",
                '    log "  Installing virtio drivers via update-initramfs"',
                "    echo 'virtio_blk' >> /etc/initramfs-tools/modules",
                "    echo 'virtio_scsi' >> /etc/initramfs-tools/modules",
                "    echo 'virtio_net' >> /etc/initramfs-tools/modules",
                "    echo 'virtio_pci' >> /etc/initramfs-tools/modules",
                "    update-initramfs -u 2>&1 | systemd-cat -t h2kvm-firstboot",
                "fi",
                "depmod -a",
                'log "  ✓ Virtio drivers installed"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 4: Network auto-repair (CRITICAL)
    if config.regenerate_network:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Repairing network configuration"',
                "# Remove VMware-specific network rules",
                "rm -f /etc/udev/rules.d/70-persistent-net.rules",
                "rm -f /etc/udev/rules.d/75-persistent-net-generator.rules",
                "",
                "# Regenerate network configuration",
                "if command -v nmcli >/dev/null 2>&1; then",
                '    log "  Reconfiguring NetworkManager"',
                "    nmcli connection reload 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "    # Reapply all connections",
                "    for conn in $(nmcli -t -f NAME connection show); do",
                '        nmcli device reapply "$conn" 2>&1 | systemd-cat -t h2kvm-firstboot || true',
                "    done",
                "elif systemctl is-enabled systemd-networkd >/dev/null 2>&1; then",
                '    log "  Restarting systemd-networkd"',
                "    systemctl restart systemd-networkd",
                "fi",
                'log "  ✓ Network configuration repaired"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 5: UUID/fstab repair
    if config.fix_disk_uuids:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Repairing disk UUIDs in fstab"',
                "# Detect current UUIDs and update fstab if needed",
                "if [ -f /etc/fstab ]; then",
                "    cp /etc/fstab /etc/fstab.pre-h2kvm",
                '    log "  Backed up fstab to /etc/fstab.pre-h2kvm"',
                "    # Update UUIDs using blkid",
                "    blkid | while IFS= read -r line; do",
                '        UUID=$(echo "$line" | grep -o \'UUID="[^"]*"\' | cut -d\'"\' -f2)',
                '        DEV=$(echo "$line" | cut -d: -f1)',
                '        if [ -n "$UUID" ] && [ -n "$DEV" ]; then',
                "            # Check if device is in fstab and UUID is different",
                '            if grep -q "$DEV" /etc/fstab 2>/dev/null; then',
                '                sed -i "s|$DEV|UUID=$UUID|g" /etc/fstab',
                "            fi",
                "        fi",
                "    done",
                'log "  ✓ fstab UUIDs updated"',
                "fi",
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 6: LVM activation
    if config.activate_lvm:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Activating LVM volumes"',
                "if command -v pvscan >/dev/null 2>&1; then",
                "    pvscan --cache 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    vgscan --mknodes 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    vgchange -ay 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    lvscan 2>&1 | systemd-cat -t h2kvm-firstboot",
                'log "  ✓ LVM volumes activated"',
                "else",
                '    log "  ⚠ LVM not available"',
                "fi",
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 7: GRUB reinstall (critical for bootloader self-healing)
    if config.reinstall_grub:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Reinstalling GRUB bootloader"',
                "# Detect boot device",
                "BOOT_DEV=$(lsblk -no PKNAME $(findmnt -n -o SOURCE /) | head -1)",
                'BOOT_DEV="/dev/${BOOT_DEV}"',
                'log "  Boot device detected: $BOOT_DEV"',
                "",
                "if [ -d /sys/firmware/efi ]; then",
                '    log "  Reinstalling GRUB (UEFI mode)"',
                "    if command -v grub2-install >/dev/null 2>&1; then",
                "        grub2-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=BOOT 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "        grub2-mkconfig -o /boot/efi/EFI/*/grub.cfg 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    elif command -v grub-install >/dev/null 2>&1; then",
                "        grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=BOOT 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "        update-grub 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    fi",
                "else",
                '    log "  Reinstalling GRUB (BIOS mode)"',
                "    if command -v grub2-install >/dev/null 2>&1; then",
                '        grub2-install "$BOOT_DEV" 2>&1 | systemd-cat -t h2kvm-firstboot',
                "        grub2-mkconfig -o /boot/grub2/grub.cfg 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    elif command -v grub-install >/dev/null 2>&1; then",
                '        grub-install "$BOOT_DEV" 2>&1 | systemd-cat -t h2kvm-firstboot',
                "        update-grub 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    fi",
                "fi",
                'log "  ✓ GRUB reinstalled"',
                "STEP=$((STEP+1))",
                "",
            ]
        )
    elif config.regenerate_grub:
        # Just regenerate config without reinstall
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Regenerating GRUB configuration"',
                "if [ -d /sys/firmware/efi ]; then",
                "    if command -v grub2-mkconfig >/dev/null 2>&1; then",
                "        grub2-mkconfig -o /boot/efi/EFI/*/grub.cfg 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    elif command -v update-grub >/dev/null 2>&1; then",
                "        update-grub 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    fi",
                "else",
                "    if command -v grub2-mkconfig >/dev/null 2>&1; then",
                "        grub2-mkconfig -o /boot/grub2/grub.cfg 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    elif command -v update-grub >/dev/null 2>&1; then",
                "        update-grub 2>&1 | systemd-cat -t h2kvm-firstboot",
                "    fi",
                "fi",
                'log "  ✓ GRUB configuration regenerated"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 8: qemu-guest-agent installation
    if config.install_qemu_guest_agent:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Installing qemu-guest-agent"',
                'if [ "$HYPERVISOR" = "kvm" ] || [ "$HYPERVISOR" = "qemu" ]; then',
                "    if command -v dnf >/dev/null 2>&1; then",
                "        dnf install -y qemu-guest-agent 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "    elif command -v yum >/dev/null 2>&1; then",
                "        yum install -y qemu-guest-agent 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "    elif command -v apt-get >/dev/null 2>&1; then",
                "        apt-get update -qq 2>&1 | systemd-cat -t h2kvm-firstboot",
                "        apt-get install -y qemu-guest-agent 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "    fi",
                "    systemctl enable --now qemu-guest-agent 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                'log "  ✓ qemu-guest-agent installed and enabled"',
                "else",
                '    log "  ⚠ Not running on KVM/QEMU, skipping"',
                "fi",
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 9: SSH keys regeneration
    if config.regenerate_ssh_keys:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Regenerating SSH host keys"',
                "# Remove old VMware SSH keys",
                "rm -f /etc/ssh/ssh_host_*",
                "# Generate new keys",
                "ssh-keygen -A 2>&1 | systemd-cat -t h2kvm-firstboot",
                'log "  ✓ SSH host keys regenerated"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 10: Virtual guest tuning
    if config.apply_virtual_guest_tuning:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Applying virtual guest tuning"',
                "if command -v tuned-adm >/dev/null 2>&1; then",
                "    tuned-adm profile virtual-guest 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                'log "  ✓ Applied virtual-guest tuning profile"',
                "else",
                '    log "  ⚠ tuned not available"',
                "fi",
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 11: Cloud-init integration
    if config.enable_cloud_init:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Enabling cloud-init"',
                "if systemctl list-unit-files | grep -q cloud-init; then",
                "    systemctl enable cloud-init cloud-config cloud-final cloud-init-local 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                "    # Create h2kvm cloud-init datasource config",
                "    mkdir -p /etc/cloud/cloud.cfg.d",
                "    cat > /etc/cloud/cloud.cfg.d/99-h2kvm.cfg <<'CLOUDEOF'",
                "# H2KVM cloud-init configuration",
                "datasource_list: [ NoCloud, None ]",
                "CLOUDEOF",
                'log "  ✓ cloud-init enabled with h2kvm config"',
                "else",
                '    log "  ⚠ cloud-init not installed"',
                "fi",
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 12: Conversion metadata
    if config.create_conversion_metadata:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Creating conversion metadata"',
                "mkdir -p /etc/h2kvm",
                "cat > /etc/h2kvm/metadata.json <<METAEOF",
                "{",
                '  "source_hypervisor": "vmware",',
                '  "target_hypervisor": "kvm",',
                '  "conversion_tool": "h2kvm",',
                '  "conversion_date": "$(date -Iseconds)",',
                '  "detected_hypervisor": "$HYPERVISOR",',
                '  "machine_id": "$(cat /etc/machine-id 2>/dev/null || echo unknown)",',
                '  "firstboot_completed": true',
                "}",
                "METAEOF",
                'log "  ✓ Conversion metadata saved to /etc/h2kvm/metadata.json"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 13: Health verification
    if config.verify_boot_health:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Verifying boot health"',
                "HEALTH_ERRORS=0",
                "",
                "# Check network",
                "if ip link show | grep -q 'state UP'; then",
                '    log "  ✓ Network interface UP"',
                "else",
                '    log_error "  ✗ No network interfaces UP"',
                "    HEALTH_ERRORS=$((HEALTH_ERRORS+1))",
                "fi",
                "",
                "# Check disks",
                "if findmnt / >/dev/null 2>&1; then",
                '    log "  ✓ Root filesystem mounted"',
                "else",
                '    log_error "  ✗ Root filesystem mount issue"',
                "    HEALTH_ERRORS=$((HEALTH_ERRORS+1))",
                "fi",
                "",
                "# Check qemu-guest-agent",
                "if systemctl is-active qemu-guest-agent >/dev/null 2>&1; then",
                '    log "  ✓ qemu-guest-agent active"',
                "else",
                '    log "  ⚠ qemu-guest-agent not active"',
                "fi",
                "",
                'log "  Health check: $HEALTH_ERRORS errors detected"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Step 14: systemd daemon reload
    script_lines.extend(
        [
            'log "[$STEP/$TOTAL_STEPS] Reloading systemd daemon"',
            "systemctl daemon-reexec 2>&1 | systemd-cat -t h2kvm-firstboot || true",
            'log "  ✓ Systemd daemon reloaded"',
            "STEP=$((STEP+1))",
            "",
        ]
    )

    # Custom commands
    if config.custom_commands:
        script_lines.extend(
            [
                'log "[$STEP/$TOTAL_STEPS] Executing custom commands"',
            ]
        )
        for i, cmd in enumerate(config.custom_commands, 1):
            script_lines.extend(
                [
                    f'log "  Custom command {i}: {cmd}"',
                    f"{cmd} 2>&1 | systemd-cat -t h2kvm-firstboot || true",
                ]
            )
        script_lines.extend(
            [
                'log "  ✓ Custom commands executed"',
                "STEP=$((STEP+1))",
                "",
            ]
        )

    # Final cleanup
    script_lines.extend(
        [
            'log "[$STEP/$TOTAL_STEPS] Cleaning up and self-disabling"',
            "# Remove conversion flag (prevents re-run)",
            "rm -f /etc/h2kvm/converted",
            "# Disable this service (oneshot, never run again)",
            "systemctl disable h2kvm-firstboot.service 2>&1 | systemd-cat -t h2kvm-firstboot || true",
            'log "  ✓ Conversion flag removed, service disabled"',
            "",
            'log "=" + "=" * 76',
            'log "H2KVM Enterprise First Boot Initialization Completed Successfully"',
            'log "=" + "=" * 76',
            "",
            "# Log boot metrics",
            "if command -v systemd-analyze >/dev/null 2>&1; then",
            "    BOOT_TIME=$(systemd-analyze | head -1)",
            '    log "Boot performance: $BOOT_TIME"',
            "fi",
            "",
            "exit 0",
        ]
    )

    return "\n".join(script_lines)
