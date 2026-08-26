// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// PreflightCheck represents a single validation check.
type PreflightCheck struct {
	Name   string
	Status string // "ok", "warn", "fail"
	Detail string
}

// RunPreflight runs all pre-migration checks and returns results.
func RunPreflight(form *FormData) []PreflightCheck {
	var checks []PreflightCheck

	// 1. h2kvmctl available
	if _, err := exec.LookPath("h2kvmctl"); err == nil {
		checks = append(checks, PreflightCheck{"h2kvmctl", "ok", "found"})
	} else {
		checks = append(checks, PreflightCheck{"h2kvmctl", "fail", "not in PATH"})
	}

	// 2. qemu-img available
	if _, err := exec.LookPath("qemu-img"); err == nil {
		checks = append(checks, PreflightCheck{"qemu-img", "ok", "found"})
	} else {
		checks = append(checks, PreflightCheck{"qemu-img", "fail", "not installed (dnf install qemu-img)"})
	}

	// 3. qemu-nbd available
	if _, err := exec.LookPath("qemu-nbd"); err == nil {
		checks = append(checks, PreflightCheck{"qemu-nbd", "ok", "found"})
	} else {
		checks = append(checks, PreflightCheck{"qemu-nbd", "fail", "not installed (sudo dnf install qemu-img or sudo apt install qemu-utils)"})
	}

	// 4. KVM support
	if _, err := os.Stat("/dev/kvm"); err == nil {
		checks = append(checks, PreflightCheck{"/dev/kvm", "ok", "available"})
	} else {
		checks = append(checks, PreflightCheck{"/dev/kvm", "warn", "not available (emulation only)"})
	}

	// 5. nbd module
	out, _ := exec.Command("lsmod").Output()
	if strings.Contains(string(out), "nbd") {
		checks = append(checks, PreflightCheck{"nbd module", "ok", "loaded"})
	} else {
		checks = append(checks, PreflightCheck{"nbd module", "warn", "not loaded (sudo modprobe nbd)"})
	}

	// 6. virsh available
	if _, err := exec.LookPath("virsh"); err == nil {
		checks = append(checks, PreflightCheck{"virsh", "ok", "found"})
	} else {
		checks = append(checks, PreflightCheck{"virsh", "warn", "not installed — needed for VM deployment (sudo dnf install libvirt-client or sudo apt install libvirt-clients)"})
	}

	// 7. libvirtd running
	out, err := exec.Command("systemctl", "is-active", "libvirtd").Output()
	if err == nil && strings.TrimSpace(string(out)) == "active" {
		checks = append(checks, PreflightCheck{"libvirtd", "ok", "running"})
	} else {
		checks = append(checks, PreflightCheck{"libvirtd", "warn", "not running — start with: sudo systemctl enable --now libvirtd"})
	}

	// 8. Source disk readable (if set)
	cmd := form.getCmd()
	var sourcePath string
	switch cmd {
	case "local":
		sourcePath = form.GetFieldValue("vmdk")
	case "ova":
		sourcePath = form.GetFieldValue("ova")
	case "ovf":
		sourcePath = form.GetFieldValue("ovf")
	}
	if sourcePath != "" {
		if _, err := os.Stat(sourcePath); err == nil {
			checks = append(checks, PreflightCheck{"Source disk", "ok", sourcePath})
		} else {
			checks = append(checks, PreflightCheck{"Source disk", "fail", fmt.Sprintf("not found: %s", sourcePath)})
		}
	}

	// 9. Disk space
	out, _ = exec.Command("df", "-BG", ".").Output()
	lines := strings.Split(string(out), "\n")
	if len(lines) >= 2 {
		fields := strings.Fields(lines[1])
		if len(fields) >= 4 {
			checks = append(checks, PreflightCheck{"Disk space", "ok", fields[3] + " free"})
		}
	}

	// 10. govc (for vsphere)
	if cmd == "vsphere" {
		if _, err := exec.LookPath("govc"); err == nil {
			checks = append(checks, PreflightCheck{"govc", "ok", "found"})
		} else {
			checks = append(checks, PreflightCheck{"govc", "fail", "not installed (required for vSphere)"})
		}

		// vCenter connectivity
		vcenter := form.GetFieldValue("vcenter")
		if vcenter != "" {
			out, err := exec.Command("ping", "-c", "1", "-W", "2", vcenter).Output()
			if err == nil && strings.Contains(string(out), "1 received") {
				checks = append(checks, PreflightCheck{"vCenter", "ok", vcenter + " reachable"})
			} else {
				checks = append(checks, PreflightCheck{"vCenter", "warn", vcenter + " unreachable"})
			}
		}
	}

	// 11. VirtIO ISO (for Windows)
	if form.GetFieldBool("windows") {
		iso := form.GetFieldValue("virtio_win_iso")
		if iso == "" {
			iso = "/usr/share/virtio-win/virtio-win.iso"
		}
		if _, err := os.Stat(iso); err == nil {
			checks = append(checks, PreflightCheck{"VirtIO ISO", "ok", iso})
		} else {
			checks = append(checks, PreflightCheck{"VirtIO ISO", "fail", "not found (dnf install virtio-win)"})
		}
	}

	return checks
}

// RenderPreflight returns a formatted string for TUI display.
func RenderPreflight(checks []PreflightCheck) string {
	var b strings.Builder
	b.WriteString("Pre-flight Checks:\n\n")

	for _, c := range checks {
		var icon string
		switch c.Status {
		case "ok":
			icon = "✅"
		case "warn":
			icon = "⚠️"
		case "fail":
			icon = "❌"
		}
		b.WriteString(fmt.Sprintf("  %s %-15s %s\n", icon, c.Name, c.Detail))
	}

	// Count
	ok, warn, fail := 0, 0, 0
	for _, c := range checks {
		switch c.Status {
		case "ok":
			ok++
		case "warn":
			warn++
		case "fail":
			fail++
		}
	}
	b.WriteString(fmt.Sprintf("\n  %d passed, %d warnings, %d failed\n", ok, warn, fail))

	if fail > 0 {
		b.WriteString("\n  ❌ Fix failed checks before running migration\n")
	}

	return b.String()
}
