// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os/exec"
	"strings"
)

// QuickMigrateConfig holds auto-detected settings for one-click migration.
type QuickMigrateConfig struct {
	SourcePath  string
	SourceType  string // vmdk, ova, ovf, qcow2
	OSType      string // linux, windows, unknown
	DiskSizeGB  float64
	SuggestRAM  int    // MiB
	SuggestCPU  int
	SuggestUEFI bool
	NeedsVirtIO bool
	Warnings    []string
}

// DetectSource analyzes a disk image and returns smart defaults.
func DetectSource(path string) (*QuickMigrateConfig, error) {
	cfg := &QuickMigrateConfig{
		SourcePath:  path,
		SuggestRAM:  2048,
		SuggestCPU:  2,
		SuggestUEFI: true,
	}

	// Detect format via qemu-img
	out, err := exec.Command("qemu-img", "info", "--output=json", path).Output()
	if err != nil {
		return nil, fmt.Errorf("cannot read disk image at %q: %w — verify the file exists, is readable, and qemu-img is installed (sudo dnf install qemu-img)", path, err)
	}

	outStr := string(out)

	// Parse format
	if strings.Contains(outStr, `"format": "vmdk"`) {
		cfg.SourceType = "vmdk"
	} else if strings.Contains(outStr, `"format": "qcow2"`) {
		cfg.SourceType = "qcow2"
	} else if strings.Contains(outStr, `"format": "raw"`) {
		cfg.SourceType = "raw"
	} else if strings.Contains(outStr, `"format": "vpc"`) {
		cfg.SourceType = "vhd"
	} else {
		cfg.SourceType = "unknown"
	}

	// Parse virtual size (rough)
	// "virtual-size": 8589934592
	if idx := strings.Index(outStr, `"virtual-size":`); idx >= 0 {
		var size int64
		_, _ = fmt.Sscanf(outStr[idx:], `"virtual-size": %d`, &size)
		cfg.DiskSizeGB = float64(size) / (1024 * 1024 * 1024)
	}

	// Detect OS type via virt-inspector or guestfish (if available)
	inspOut, err := exec.Command("virt-inspector", "--format="+cfg.SourceType, path).Output()
	if err == nil {
		inspStr := string(inspOut)
		if strings.Contains(inspStr, "windows") || strings.Contains(inspStr, "Windows") {
			cfg.OSType = "windows"
			cfg.NeedsVirtIO = true
			cfg.SuggestRAM = 4096
			cfg.SuggestCPU = 4
		} else {
			cfg.OSType = "linux"
		}

		// Check for UEFI hints
		if strings.Contains(inspStr, "efi") || strings.Contains(inspStr, "EFI") {
			cfg.SuggestUEFI = true
		}
	} else {
		cfg.OSType = "unknown"
		cfg.Warnings = append(cfg.Warnings, "Could not detect OS type (virt-inspector not available)")
	}

	// Size-based RAM suggestion
	if cfg.DiskSizeGB > 100 {
		cfg.SuggestRAM = 8192
		cfg.SuggestCPU = 4
	} else if cfg.DiskSizeGB > 50 {
		cfg.SuggestRAM = 4096
		cfg.SuggestCPU = 2
	}

	return cfg, nil
}

// BuildQuickArgs generates h2kvmctl CLI arguments from detected config.
func (c *QuickMigrateConfig) BuildQuickArgs(outputDir string) []string {
	args := []string{
		"--cmd", "local",
		"--vmdk", c.SourcePath,
		"--output-dir", outputDir,
		"--to-output", "migrated.qcow2",
		"--out-format", "qcow2",
		"--flatten",
		"--compress",
		"--fstab-mode", "stabilize-all",
		"--regen-initramfs",
		"--remove-vmware-tools",
		"--emit-domain-xml",
		"--virsh-define",
		"--machine", "q35",
		"--disk-bus", "virtio",
		"--net-model", "virtio",
		"--libvirt-network", "default",
		"--memory", fmt.Sprintf("%d", c.SuggestRAM),
		"--vcpus", fmt.Sprintf("%d", c.SuggestCPU),
		"--libvirt-test",
		"--keep-domain",
		"-v",
	}

	if c.SuggestUEFI {
		args = append(args, "--uefi")
	}

	if c.OSType == "windows" {
		args = append(args,
			"--windows",
			"--guest-os", "windows",
			"--win-stage", "bootstrap",
			"--graphics", "spice",
			"--video", "qxl",
			"--usb-tablet",
			"--clock", "localtime",
		)
		// Add virtio ISO if found
		for _, p := range []string{
			"/usr/share/virtio-win/virtio-win.iso",
			"/usr/share/virtio-win.iso",
		} {
			if fileExists(p) {
				args = append(args, "--virtio-win-iso", p)
				break
			}
		}
	} else {
		args = append(args, "--guest-os", "linux")
		args = append(args, "--serial-console")
		args = append(args, "--graphics", "vnc")
	}

	return args
}

// PreviewCommand returns the full command as a string for display.
func (c *QuickMigrateConfig) PreviewCommand(binaryPath, outputDir string) string {
	args := c.BuildQuickArgs(outputDir)
	parts := []string{binaryPath}
	parts = append(parts, args...)

	// Format with line continuations
	var lines []string
	lines = append(lines, parts[0]+" \\")
	for i := 1; i < len(parts)-1; i += 2 {
		if i+1 < len(parts) {
			lines = append(lines, fmt.Sprintf("    %s %s \\", parts[i], parts[i+1]))
		} else {
			lines = append(lines, fmt.Sprintf("    %s", parts[i]))
		}
	}
	if len(lines) > 0 {
		// Remove trailing backslash from last line
		last := lines[len(lines)-1]
		lines[len(lines)-1] = strings.TrimSuffix(last, " \\")
	}

	return strings.Join(lines, "\n")
}

// Summary returns a human-readable summary of detected config.
func (c *QuickMigrateConfig) Summary() string {
	var lines []string
	lines = append(lines, fmt.Sprintf("  Source:    %s (%s)", c.SourcePath, c.SourceType))
	lines = append(lines, fmt.Sprintf("  OS:       %s", c.OSType))
	lines = append(lines, fmt.Sprintf("  Disk:     %.1f GB", c.DiskSizeGB))
	lines = append(lines, fmt.Sprintf("  RAM:      %d MiB", c.SuggestRAM))
	lines = append(lines, fmt.Sprintf("  CPU:      %d vCPUs", c.SuggestCPU))
	lines = append(lines, fmt.Sprintf("  UEFI:     %v", c.SuggestUEFI))
	if c.NeedsVirtIO {
		lines = append(lines, "  VirtIO:   required (Windows)")
	}
	for _, w := range c.Warnings {
		lines = append(lines, fmt.Sprintf("  ⚠️ %s", w))
	}
	return strings.Join(lines, "\n")
}

func fileExists(path string) bool {
	_, err := exec.Command("test", "-f", path).Output()
	return err == nil
}
