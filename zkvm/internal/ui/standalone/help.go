// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/theme"
)

// HelpModel provides a context-aware help overlay.
type HelpModel struct {
	visible bool
	scroll  int
	width   int
	height  int
}

// NewHelpModel creates a new help overlay (initially hidden).
func NewHelpModel() HelpModel {
	return HelpModel{}
}

// Toggle flips the help overlay visibility.
func (m *HelpModel) Toggle() {
	m.visible = !m.visible
	m.scroll = 0
}

// Visible returns whether the overlay is displayed.
func (m HelpModel) Visible() bool {
	return m.visible
}

// SetSize updates the overlay dimensions.
func (m *HelpModel) SetSize(w, h int) {
	m.width = w
	m.height = h
}

// Update handles scroll keys when the overlay is visible.
func (m HelpModel) Update(msg tea.KeyMsg) HelpModel {
	key := msg.String()
	switch key {
	case "?", "esc", "q":
		m.visible = false
	case "up", "k":
		if m.scroll > 0 {
			m.scroll--
		}
	case "down", "j":
		m.scroll++
	case "home", "g":
		m.scroll = 0
	}
	return m
}

// View renders the help overlay centered on screen.
func (m HelpModel) View(activeTab int) string {
	content := m.buildContent(activeTab)

	lines := strings.Split(content, "\n")
	maxVisible := m.height - 6
	if maxVisible < 5 {
		maxVisible = 5
	}
	if m.scroll > len(lines)-maxVisible {
		m.scroll = len(lines) - maxVisible
	}
	if m.scroll < 0 {
		m.scroll = 0
	}

	end := m.scroll + maxVisible
	if end > len(lines) {
		end = len(lines)
	}
	visible := strings.Join(lines[m.scroll:end], "\n")

	overlayW := m.width - 8
	if overlayW > 70 {
		overlayW = 70
	}
	if overlayW < 30 {
		overlayW = 30
	}

	box := helpOverlayStyle.
		Width(overlayW).
		Render(
			helpTitleStyle.Render("  Keyboard Shortcuts") + "\n\n" +
				visible + "\n\n" +
				helpFooterStyle.Render("  Press ? or Esc to close  ·  j/k to scroll"))

	return box
}

func (m HelpModel) buildContent(activeTab int) string {
	var b strings.Builder

	// Global keys.
	b.WriteString(helpSectionStyle.Render("  Global") + "\n")
	writeKey(&b, "Alt+1-5", "Jump to tab")
	writeKey(&b, "Tab", "Next tab (wraps around)")
	writeKey(&b, "Shift+Tab", "Previous tab")
	writeKey(&b, "?", "Toggle this help")
	writeKey(&b, "Ctrl+C", "Stop process / Quit")
	writeKey(&b, "Ctrl+Q", "Quit immediately")
	b.WriteString("\n")

	switch activeTab {
	case TabMigration:
		b.WriteString(helpSectionStyle.Render("  Migration Tab") + "\n")
		writeKey(&b, "j/k", "Navigate form fields")
		writeKey(&b, "Enter", "Edit field / Expand category")
		writeKey(&b, "Space", "Toggle boolean / Cycle select")
		writeKey(&b, "h/l", "Cycle select options")
		writeKey(&b, "Esc", "Stop editing / Collapse category")
		writeKey(&b, "Ctrl+R", "Run migration")
		writeKey(&b, "E", "Export to Libvirt (after completion)")
		writeKey(&b, "Ctrl+P", "Save profile")
		writeKey(&b, "Ctrl+L", "Load profile")

	case TabLogs:
		b.WriteString(helpSectionStyle.Render("  Logs Tab") + "\n")
		writeKey(&b, "j/k", "Scroll logs")
		writeKey(&b, "Ctrl+R", "Run migration")

	case TabLibvirt:
		b.WriteString(helpSectionStyle.Render("  Libvirt VMs Tab") + "\n")
		writeKey(&b, "j/k", "Navigate VM list")
		writeKey(&b, "p", "Switch panes (list/details)")
		writeKey(&b, "s", "Start VM")
		writeKey(&b, "h", "Shutdown VM")
		writeKey(&b, "d", "Delete VM (with confirmation)")
		writeKey(&b, "c", "Open console (virt-viewer)")
		writeKey(&b, "w", "Web console (noVNC)")
		writeKey(&b, "n", "Create snapshot")
		writeKey(&b, "r", "Refresh VM list")

	case TabKubernetes:
		b.WriteString(helpSectionStyle.Render("  Kubernetes Tab") + "\n")
		writeKey(&b, "j/k", "Navigate list")
		writeKey(&b, "p", "Switch panes")
		writeKey(&b, "1", "Show VMs view")
		writeKey(&b, "2", "Show PVCs view")
		writeKey(&b, "3", "Show Migrations view")
		writeKey(&b, "s", "Start VM")
		writeKey(&b, "x", "Stop VM")
		writeKey(&b, "t", "Restart VM")
		writeKey(&b, "d", "Delete VM")
		writeKey(&b, "c", "Console (virtctl vnc)")
		writeKey(&b, "e", "SSH into VM (port-forward)")
		writeKey(&b, "w", "VM creation wizard")
		writeKey(&b, "u", "Upload disk image (PVC view)")
		writeKey(&b, "n", "Next kubeconfig context")
		writeKey(&b, "a", "Cycle namespace filter")
		writeKey(&b, "r", "Refresh")

	}

	b.WriteString("\n")
	b.WriteString(helpSectionStyle.Render("  Profiles") + "\n")
	writeKey(&b, "Ctrl+P", "Save current form as profile")
	writeKey(&b, "Ctrl+L", "Load profile into form")

	return b.String()
}

func writeKey(b *strings.Builder, key, desc string) {
	b.WriteString(fmt.Sprintf("    %s  %s\n",
		helpKeyStyle.Render(fmt.Sprintf("%-10s", key)),
		helpDescStyle.Render(desc)))
}

// Styles for the help overlay.
var (
	helpOverlayStyle = lipgloss.NewStyle().
				Border(lipgloss.DoubleBorder()).
				BorderForeground(theme.Orange).
				Background(lipgloss.Color("#111111")).
				Padding(1, 2)

	helpTitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(theme.Orange)

	helpFooterStyle = lipgloss.NewStyle().
			Foreground(theme.Dim).
			Italic(true)

	helpSectionStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Cyan)

	helpKeyStyle = lipgloss.NewStyle().
			Foreground(theme.OrangeLight).
			Bold(true)

	helpDescStyle = lipgloss.NewStyle().
			Foreground(theme.CoralLight)
)
