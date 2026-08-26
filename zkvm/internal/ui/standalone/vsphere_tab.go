// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os"
	"strings"

	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/theme"
)

// vsphereField holds a single editable vSphere connection field.
type vsphereField struct {
	Label       string
	Flag        string
	Value       string
	Placeholder string
	EnvVar      string // env var name for auto-population hint
	IsPassword  bool
	IsToggle    bool
	BoolValue   bool
	Editing     bool
	CursorPos   int
}

// VsphereTab holds vSphere tab state — connection fields + VM list.
// Stored as a pointer in Model so it survives Bubble Tea value copies.
type VsphereTab struct {
	fields     []vsphereField
	fieldIdx   int
	focusPanel int // 0 = connection fields, 1 = VM list
}

// envOrPrefill returns the prefill value if set, otherwise reads from env.
func envOrPrefill(envKey, prefill string) string {
	if prefill != "" {
		return prefill
	}
	return os.Getenv(envKey)
}

// NewVsphereTab creates a new vSphere tab with env-populated fields.
func NewVsphereTab(pf Prefill) *VsphereTab {
	vcenter := envOrPrefill("GOVC_URL", pf.VCenter)
	// Strip protocol/path from GOVC_URL (e.g. https://host/sdk → host).
	vcenter = strings.TrimPrefix(vcenter, "https://")
	vcenter = strings.TrimPrefix(vcenter, "http://")
	vcenter = strings.TrimSuffix(vcenter, "/sdk")
	vcenter = strings.TrimSuffix(vcenter, "/")

	user := envOrPrefill("GOVC_USERNAME", pf.VCUser)

	password := os.Getenv("GOVC_PASSWORD")
	if password == "" {
		password = os.Getenv("VC_PASSWORD")
	}

	dc := envOrPrefill("GOVC_DATACENTER", pf.DCName)

	insecure := os.Getenv("GOVC_INSECURE") == "1"

	return &VsphereTab{
		fields: []vsphereField{
			{Label: "vcenter", Flag: "--vcenter", Value: vcenter, Placeholder: "vCenter hostname/IP", EnvVar: "GOVC_URL"},
			{Label: "vc_user", Flag: "--vc-user", Value: user, Placeholder: "administrator@vsphere.local", EnvVar: "GOVC_USERNAME"},
			{Label: "vc_password", Flag: "--vc-password", Value: password, Placeholder: "vCenter password", IsPassword: true, EnvVar: "GOVC_PASSWORD"},
			{Label: "vc_password_env", Flag: "--vc-password-env", Placeholder: "Env var name holding password"},
			{Label: "dc_name", Flag: "--dc-name", Value: dc, Placeholder: "Datacenter name", EnvVar: "GOVC_DATACENTER"},
			{Label: "vc_insecure", Flag: "--vc-insecure", IsToggle: true, BoolValue: insecure || true},
		},
	}
}

// GetField returns the value of a field by label.
func (vt *VsphereTab) GetField(label string) string {
	for _, f := range vt.fields {
		if f.Label == label {
			if f.IsToggle {
				if f.BoolValue {
					return "true"
				}
				return ""
			}
			return f.Value
		}
	}
	return ""
}

// GetFieldBool returns the bool value of a toggle field.
func (vt *VsphereTab) GetFieldBool(label string) bool {
	for _, f := range vt.fields {
		if f.Label == label {
			return f.BoolValue
		}
	}
	return false
}

// HasCredentials returns true if enough info for discovery.
func (vt *VsphereTab) HasCredentials() bool {
	return vt.GetField("vcenter") != ""
}

// BuildFormData creates a FormData with vSphere fields populated for govcEnv().
func (vt *VsphereTab) BuildFormData() *FormData {
	fd := &FormData{}
	fd.Categories = []Category{
		{
			Name: "vSphere",
			Fields: []Field{
				{Label: "vcenter", Value: vt.GetField("vcenter")},
				{Label: "vc_user", Value: vt.GetField("vc_user")},
				{Label: "vc_password", Value: vt.GetField("vc_password")},
				{Label: "vc_password_env", Value: vt.GetField("vc_password_env")},
				{Label: "dc_name", Value: vt.GetField("dc_name")},
				{Label: "vc_insecure", Type: FieldToggle, BoolValue: vt.GetFieldBool("vc_insecure")},
			},
		},
	}
	return fd
}

// RenderConnectionFields draws the vSphere connection panel.
func (vt *VsphereTab) RenderConnectionFields(width int, focused bool) string {
	var b strings.Builder

	headerStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Primary)
	labelStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Muted).Width(16)
	valueStyle := lipgloss.NewStyle().Foreground(theme.Active.Fg)
	placeholderStyle := lipgloss.NewStyle().Foreground(theme.Active.Subtle)
	cursorStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Primary)
	envTagStyle := lipgloss.NewStyle().Foreground(theme.Active.Success).Bold(true)
	editStyle := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(theme.Active.Primary).
		Padding(0, 1)

	b.WriteString(headerStyle.Render("🔌 vCenter Connection"))
	b.WriteString("\n\n")

	for i, f := range vt.fields {
		cursor := "  "
		if i == vt.fieldIdx && focused && vt.focusPanel == 0 {
			cursor = cursorStyle.Render("▶ ")
		}

		label := labelStyle.Render(f.Label + ":")
		var value string

		if f.IsToggle {
			if f.BoolValue {
				value = lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Success).Render("◉ ON")
			} else {
				value = lipgloss.NewStyle().Foreground(theme.Active.Muted).Render("○ OFF")
			}
		} else if f.Editing {
			display := f.Value
			if f.IsPassword {
				display = strings.Repeat("•", len(f.Value))
			}
			value = editStyle.Render(display + "█")
		} else if f.Value == "" {
			value = placeholderStyle.Render(f.Placeholder)
			if f.EnvVar != "" {
				value += " " + lipgloss.NewStyle().Foreground(theme.Active.Muted).Render("(set "+f.EnvVar+" env)")
			}
		} else if f.IsPassword {
			value = valueStyle.Render(strings.Repeat("•", len(f.Value)))
			value += " " + envTagStyle.Render("[env]")
		} else {
			value = valueStyle.Render(f.Value)
			if f.EnvVar != "" && os.Getenv(f.EnvVar) != "" {
				value += " " + envTagStyle.Render("[env]")
			}
		}

		b.WriteString(fmt.Sprintf("%s%s %s\n", cursor, label, value))
	}

	return b.String()
}

// RenderVMList draws the discovered VM list with scroll support.
func (vt *VsphereTab) RenderVMList(vms []VsphereVMInfo, cursor int, focused bool, discoverMsg string, discovering bool, width int) string {
	var b strings.Builder

	headerStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Primary)

	if discovering {
		b.WriteString(headerStyle.Render("📦 Discovering VMs..."))
		b.WriteString("\n\n")
		b.WriteString("  ⏳ Connecting to vCenter...\n")
		return b.String()
	}

	if len(vms) == 0 {
		b.WriteString(headerStyle.Render("📦 VMs"))
		b.WriteString("\n\n")
		if discoverMsg != "" {
			b.WriteString("  " + discoverMsg + "\n")
		} else {
			b.WriteString("  No VMs discovered yet.\n")
			b.WriteString("  Fill in vCenter credentials above, then press Ctrl+D or Enter.\n")
		}
		return b.String()
	}

	// Count selected.
	selected := 0
	for _, vm := range vms {
		if vm.Selected {
			selected++
		}
	}

	hint := ""
	if focused && vt.focusPanel == 1 {
		hint = "  (j/k: navigate  Space: toggle  a: all  Ctrl+R: migrate)"
	}
	b.WriteString(headerStyle.Render(fmt.Sprintf("📦 Discovered VMs (%d) — %d selected%s", len(vms), selected, hint)))
	b.WriteString("\n\n")

	// Table header.
	thStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Muted)
	b.WriteString(thStyle.Render(fmt.Sprintf("  %-3s %-2s %-32s %4s %6s %-12s", "", "⚡", "VM Name", "CPU", "RAM", "Status")))
	b.WriteString("\n")
	b.WriteString(lipgloss.NewStyle().Foreground(theme.Active.Border).Render("  " + strings.Repeat("─", 70)))
	b.WriteString("\n")

	// Windowed display.
	maxVisible := 20
	total := len(vms)
	start := 0
	end := total
	if total > maxVisible {
		start = cursor - maxVisible/2
		if start < 0 {
			start = 0
		}
		end = start + maxVisible
		if end > total {
			end = total
			start = end - maxVisible
		}
	}

	if start > 0 {
		b.WriteString(lipgloss.NewStyle().Foreground(theme.Active.Muted).Render(
			fmt.Sprintf("  ↑ %d more above\n", start)))
	}

	for i := start; i < end; i++ {
		vm := vms[i]
		atCursor := i == cursor && focused && vt.focusPanel == 1

		checkbox := "[ ]"
		if vm.Selected {
			checkbox = "[✓]"
		}

		arrow := "  "
		if atCursor {
			arrow = "▶ "
		}

		powerIcon := "🔴"
		powerText := "off"
		if vm.PowerState == "poweredOn" {
			powerIcon = "🟢"
			powerText = "on"
		}

		vmName := vm.Name
		if len(vmName) > 30 {
			vmName = vmName[:27] + "..."
		}

		line := fmt.Sprintf("%s%s %s %-30s %4d %5.1fG %-12s",
			arrow, checkbox, powerIcon,
			vmName,
			vm.NumCPU,
			float64(vm.MemoryMB)/1024,
			powerText)

		if atCursor {
			b.WriteString(lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Primary).Render(line))
		} else if vm.Selected {
			b.WriteString(lipgloss.NewStyle().Foreground(theme.Active.Success).Render(line))
		} else {
			b.WriteString(line)
		}
		b.WriteString("\n")
	}

	if end < total {
		b.WriteString(lipgloss.NewStyle().Foreground(theme.Active.Muted).Render(
			fmt.Sprintf("  ↓ %d more below\n", total-end)))
	}

	if discoverMsg != "" {
		b.WriteString("\n  " + discoverMsg + "\n")
	}

	return b.String()
}
