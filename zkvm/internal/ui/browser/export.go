// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

//
// Export engine — runs govc export + h2kvmctl pipeline from the Browser tab.
package browser

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// ── Export Templates (matching hypersdk) ──

type ExportTemplate struct {
	Name        string
	Description string
	Format      string // ovf, ova
	Compress    bool
	Flatten     bool
	Fix         bool   // run guest fixes
	LibvirtTest bool
}

var ExportTemplates = []ExportTemplate{
	{
		Name:        "Quick Export",
		Description: "Fast OVF export without compression",
		Format:      "ovf",
		Compress:    false,
		Flatten:     true,
		Fix:         false,
		LibvirtTest: false,
	},
	{
		Name:        "Full Migration",
		Description: "Export + convert + fix + boot test (recommended)",
		Format:      "ovf",
		Compress:    true,
		Flatten:     true,
		Fix:         true,
		LibvirtTest: true,
	},
	{
		Name:        "Production Backup",
		Description: "Compressed OVA with verification",
		Format:      "ova",
		Compress:    true,
		Flatten:     true,
		Fix:         false,
		LibvirtTest: false,
	},
	{
		Name:        "KubeVirt Deploy",
		Description: "Export + convert + deploy to Kubernetes",
		Format:      "ovf",
		Compress:    true,
		Flatten:     true,
		Fix:         true,
		LibvirtTest: false,
	},
}

// ── Export Progress ──

type ExportProgress struct {
	Phase        string  // "export", "convert", "fix", "test"
	Percent      float64 // 0-100
	CurrentVM    string
	CurrentFile  string
	Speed        string  // e.g. "45.2 MB/s"
	Elapsed      time.Duration
	VMsDone      int
	VMsTotal     int
	StartTime    time.Time
}

// ── Messages ──

type ExportStartMsg struct{}

type ExportProgressMsg struct {
	Progress ExportProgress
}

type ExportLineMsg struct {
	Line string
}

type ExportDoneMsg struct {
	VMName   string
	Index    int
	Err      error
	Duration time.Duration
}

type ExportAllDoneMsg struct {
	Total    int
	Failed   int
	Duration time.Duration
}

// ── Progress parsing ──

var (
	reProgress  = regexp.MustCompile(`(?i)progress:\s*([\d.]+)%`)
	reConvert   = regexp.MustCompile(`(?i)convert|conversion|qemu-img`)
	reFix       = regexp.MustCompile(`(?i)offline fix|initramfs|fstab|vmcraft`)
	reExport    = regexp.MustCompile(`(?i)export|nfc|govc|ovftool`)
	reTest      = regexp.MustCompile(`(?i)libvirt|boot test|smoke test|domain.*running`)
	reSpeed     = regexp.MustCompile(`(\d+\.?\d*)\s*MB/s`)
)

func parsePhase(line string) string {
	lower := strings.ToLower(line)
	if reTest.MatchString(lower) {
		return "test"
	}
	if reFix.MatchString(lower) {
		return "fix"
	}
	if reConvert.MatchString(lower) {
		return "convert"
	}
	if reExport.MatchString(lower) {
		return "export"
	}
	return ""
}

func parseProgress(line string) float64 {
	if m := reProgress.FindStringSubmatch(line); len(m) > 1 {
		var pct float64
		fmt.Sscanf(m[1], "%f", &pct)
		return pct
	}
	return -1
}

func parseSpeed(line string) string {
	if m := reSpeed.FindStringSubmatch(line); len(m) > 1 {
		return m[0]
	}
	return ""
}

// ── Build h2kvmctl command ──

func BuildExportCommand(vm VMItem, tmpl ExportTemplate, outputDir string) []string {
	args := []string{
		"--cmd", "vsphere",
		"--vs-action", "export_vm",
		"--export-mode", tmpl.Format + "_export",
		"--vs-control-plane", "govc",
		"--vm-name", vm.Name,
		"--output-dir", outputDir,
	}

	// Use env vars for connection (GOVC_*)
	if os.Getenv("GOVC_URL") != "" {
		vcenter := os.Getenv("GOVC_URL")
		vcenter = strings.TrimPrefix(vcenter, "https://")
		vcenter = strings.TrimPrefix(vcenter, "http://")
		vcenter = strings.TrimSuffix(vcenter, "/sdk")
		args = append(args, "--vcenter", vcenter)
	}
	if u := os.Getenv("GOVC_USERNAME"); u != "" {
		args = append(args, "--vc-user", u)
	}
	args = append(args, "--vc-password-env", "GOVC_PASSWORD")
	if os.Getenv("GOVC_INSECURE") == "1" {
		args = append(args, "--vc-insecure")
	}
	if dc := os.Getenv("GOVC_DATACENTER"); dc != "" {
		args = append(args, "--govc-datacenter", dc)
		args = append(args, "--dc-name", dc)
	}
	args = append(args, "--govc-insecure")
	args = append(args, "--govc-export-remove-cdroms")

	// Conversion options
	if tmpl.Flatten {
		args = append(args, "--flatten")
	}
	if tmpl.Compress {
		args = append(args, "--compress")
	}
	args = append(args, "--to-output", vm.Name+".qcow2")
	args = append(args, "--out-format", "qcow2")

	// Guest fixes
	if tmpl.Fix {
		args = append(args, "--fstab-mode", "stabilize-all")
		args = append(args, "--regen-initramfs")
		args = append(args, "--remove-vmware-tools")
	}

	// Libvirt
	if tmpl.LibvirtTest || tmpl.Fix {
		args = append(args, "--emit-domain-xml")
		args = append(args, "--uefi")
		args = append(args, "--machine", "q35")
		args = append(args, "--disk-bus", "virtio")
		args = append(args, "--net-model", "virtio")
		args = append(args, "--libvirt-network", "default")
		args = append(args, "--guest-os", "linux")
	}
	if tmpl.LibvirtTest {
		args = append(args, "--libvirt-test")
		args = append(args, "--keep-domain")
		args = append(args, "--timeout", "120")
	}

	args = append(args, "-v")

	return args
}

// PreviewCommand returns a formatted command string for display.
func PreviewCommand(binary string, args []string) string {
	var lines []string
	lines = append(lines, binary+" \\")
	for i := 0; i < len(args)-1; i += 2 {
		if i+1 < len(args) {
			lines = append(lines, fmt.Sprintf("    %s %s \\", args[i], args[i+1]))
		}
	}
	if len(args)%2 == 1 {
		lines = append(lines, fmt.Sprintf("    %s", args[len(args)-1]))
	}
	if len(lines) > 0 {
		last := lines[len(lines)-1]
		lines[len(lines)-1] = strings.TrimSuffix(last, " \\")
	}
	return strings.Join(lines, "\n")
}

// ── Run export (async via Bubble Tea) ──

func RunExportCmd(binary string, args []string, vmName string, index int, p *tea.Program) tea.Cmd {
	return func() tea.Msg {
		start := time.Now()

		cmd := exec.Command(binary, args...)
		cmd.Env = os.Environ()

		stdout, err := cmd.StdoutPipe()
		if err != nil {
			return ExportDoneMsg{VMName: vmName, Index: index, Err: err, Duration: time.Since(start)}
		}
		cmd.Stderr = cmd.Stdout

		if err := cmd.Start(); err != nil {
			return ExportDoneMsg{VMName: vmName, Index: index, Err: err, Duration: time.Since(start)}
		}

		// Stream output lines
		scanner := bufio.NewScanner(stdout)
		progress := ExportProgress{
			Phase:     "export",
			CurrentVM: vmName,
			StartTime: start,
		}

		for scanner.Scan() {
			line := scanner.Text()

			// Send line to TUI
			if p != nil {
				p.Send(ExportLineMsg{Line: line})
			}

			// Parse progress
			if phase := parsePhase(line); phase != "" {
				progress.Phase = phase
			}
			if pct := parseProgress(line); pct >= 0 {
				progress.Percent = pct
			}
			if spd := parseSpeed(line); spd != "" {
				progress.Speed = spd
			}
			progress.Elapsed = time.Since(start)

			if p != nil {
				p.Send(ExportProgressMsg{Progress: progress})
			}
		}

		waitErr := cmd.Wait()
		duration := time.Since(start)

		return ExportDoneMsg{
			VMName:   vmName,
			Index:    index,
			Err:      waitErr,
			Duration: duration,
		}
	}
}
