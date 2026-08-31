// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"strings"
)

// DiagnosisResult contains failure analysis and suggested fixes.
type DiagnosisResult struct {
	ErrorType   string
	Description string
	Causes      []string
	Fixes       []string
}

// DiagnoseFailure analyzes log output and returns a diagnosis.
func DiagnoseFailure(exitCode int, logs string) *DiagnosisResult {
	lower := strings.ToLower(logs)

	// Boot failure
	if strings.Contains(lower, "inaccessible_boot_device") ||
		strings.Contains(lower, "no boot device") ||
		strings.Contains(lower, "boot failed") {
		return &DiagnosisResult{
			ErrorType:   "Boot Failure",
			Description: "VM cannot find a bootable disk",
			Causes: []string{
				"VirtIO storage driver not injected (Windows)",
				"initramfs missing virtio_blk/virtio_scsi modules (Linux)",
				"Wrong disk bus type (SATA vs VirtIO)",
			},
			Fixes: []string{
				"Enable --regen-initramfs",
				"For Windows: SATA is the default (--win-stage bootstrap)",
				"For Windows: virtio-win ISO auto-detected from /var/lib/h2kvm/",
				"After boot: install drivers from CD-ROM (D:\\virtio-win-guest-tools.exe)",
				"Try --disk-bus sata as fallback",
			},
		}
	}

	// fstab / mount failure
	if strings.Contains(lower, "failed to mount") ||
		strings.Contains(lower, "mount_root") ||
		strings.Contains(lower, "can't find root") {
		return &DiagnosisResult{
			ErrorType:   "Root Filesystem Mount Failure",
			Description: "Cannot mount the root filesystem",
			Causes: []string{
				"fstab uses device names that changed (/dev/sda → /dev/vda)",
				"LVM volumes not activated",
				"Filesystem type not supported in initramfs",
			},
			Fixes: []string{
				"Enable --fstab-mode stabilize-all (converts to UUID)",
				"Enable --regen-initramfs (adds virtio + LVM modules)",
				"Check if disk has LVM: use --backend guestkit",
			},
		}
	}

	// GRUB failure
	if strings.Contains(lower, "grub") && (strings.Contains(lower, "error") || strings.Contains(lower, "fail")) {
		return &DiagnosisResult{
			ErrorType:   "GRUB Bootloader Error",
			Description: "GRUB configuration is broken or missing",
			Causes: []string{
				"GRUB root= parameter points to wrong device",
				"Missing GRUB modules for new disk type",
				"UEFI/BIOS mismatch",
			},
			Fixes: []string{
				"h2kvm auto-fixes GRUB (ensure it ran)",
				"Try --uefi if source VM was UEFI",
				"Omit --no-grub to allow GRUB repair",
			},
		}
	}

	// Network failure
	if strings.Contains(lower, "no network") ||
		strings.Contains(lower, "network unreachable") ||
		strings.Contains(lower, "dhcp") {
		return &DiagnosisResult{
			ErrorType:   "Network Configuration Error",
			Description: "VM booted but has no network connectivity",
			Causes: []string{
				"Network interface name changed (eth0 → ens3)",
				"VMware network driver replaced but config not updated",
				"libvirt default network not started",
			},
			Fixes: []string{
				"Check: virsh net-start default",
				"VM should auto-detect via DHCP with VirtIO net driver",
				"For static IP: configure inside guest after boot",
			},
		}
	}

	// Conversion failure
	if strings.Contains(lower, "qemu-img") && strings.Contains(lower, "error") {
		return &DiagnosisResult{
			ErrorType:   "Disk Conversion Error",
			Description: "qemu-img failed during conversion",
			Causes: []string{
				"Source VMDK is corrupted or truncated",
				"Disk is locked by another process",
				"Unsupported VMDK format (split extents)",
			},
			Fixes: []string{
				"Re-export VMDK from vSphere",
				"Use --flatten to merge snapshot chain",
				"Check disk: qemu-img check <file>",
			},
		}
	}

	// Permission / SELinux
	if strings.Contains(lower, "permission denied") ||
		strings.Contains(lower, "selinux") {
		return &DiagnosisResult{
			ErrorType:   "Permission Error",
			Description: "Access denied during migration",
			Causes: []string{
				"SELinux blocking qemu-nbd or libvirt",
				"Disk file not accessible by qemu user",
				"Missing sudo / root privileges",
			},
			Fixes: []string{
				"Run with sudo",
				"Try: sudo setenforce 0 (temporary)",
				"Check: chcon -t virt_image_t <qcow2>",
			},
		}
	}

	// NBD failure
	if strings.Contains(lower, "nbd") && (strings.Contains(lower, "error") || strings.Contains(lower, "fail")) {
		return &DiagnosisResult{
			ErrorType:   "NBD Module Error",
			Description: "Cannot connect disk via NBD (Network Block Device)",
			Causes: []string{
				"nbd kernel module not loaded",
				"All NBD devices in use",
				"Previous NBD not disconnected",
			},
			Fixes: []string{
				"Load module: sudo modprobe nbd max_part=16",
				"Disconnect stale: sudo qemu-nbd -d /dev/nbd0",
				"Increase max: echo 'options nbd nbds_max=128' > /etc/modprobe.d/nbd.conf",
			},
		}
	}

	// vSphere / govc failure
	if strings.Contains(lower, "govc") || strings.Contains(lower, "vsphere") || strings.Contains(lower, "vcenter") {
		if strings.Contains(lower, "connection refused") || strings.Contains(lower, "timeout") {
			return &DiagnosisResult{
				ErrorType:   "vSphere Connection Error",
				Description: "Cannot connect to vCenter / ESXi",
				Causes: []string{
					"Wrong vCenter hostname or IP",
					"vCenter is down or unreachable",
					"Firewall blocking HTTPS (443)",
				},
				Fixes: []string{
					"Verify: ping <vcenter-ip>",
					"Check credentials and --vc-insecure flag",
					"Test: govc about",
				},
			}
		}
	}

	// Timeout
	if strings.Contains(lower, "timeout") {
		return &DiagnosisResult{
			ErrorType:   "Timeout",
			Description: "Operation timed out",
			Causes: []string{
				"VM takes too long to boot",
				"Network transfer too slow",
				"Disk too large for timeout value",
			},
			Fixes: []string{
				"Increase --timeout value",
				"For large disks (>100GB): expect 30+ minutes",
				"Check network speed to vCenter",
			},
		}
	}

	// Generic
	return &DiagnosisResult{
		ErrorType:   "Unknown Error",
		Description: fmt.Sprintf("Migration failed with exit code %d", exitCode),
		Causes: []string{
			"Check log output for details",
		},
		Fixes: []string{
			"Run with -v for verbose output",
			"Check: h2kvmctl --config <yaml> --dry-run",
			"Report issue: github.com/ssahani/h2kvm/issues",
		},
	}
}

// Render returns a formatted string for TUI display.
func (d *DiagnosisResult) Render() string {
	var b strings.Builder

	b.WriteString(fmt.Sprintf("❌ %s\n", d.ErrorType))
	b.WriteString(fmt.Sprintf("   %s\n\n", d.Description))

	if len(d.Causes) > 0 {
		b.WriteString("  Possible causes:\n")
		for _, c := range d.Causes {
			b.WriteString(fmt.Sprintf("    • %s\n", c))
		}
		b.WriteString("\n")
	}

	if len(d.Fixes) > 0 {
		b.WriteString("  Suggested fixes:\n")
		for _, f := range d.Fixes {
			b.WriteString(fmt.Sprintf("    → %s\n", f))
		}
	}

	return b.String()
}
