// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func helpKeyMsg(s string) tea.KeyMsg {
	switch s {
	case "esc":
		return tea.KeyMsg{Type: tea.KeyEsc}
	case "up":
		return tea.KeyMsg{Type: tea.KeyUp}
	case "down":
		return tea.KeyMsg{Type: tea.KeyDown}
	case "home":
		return tea.KeyMsg{Type: tea.KeyHome}
	default:
		return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
	}
}

func TestNewHelpModelInitialState(t *testing.T) {
	h := NewHelpModel()

	if h.Visible() {
		t.Error("expected help to be initially hidden")
	}
	if h.scroll != 0 {
		t.Errorf("expected scroll to be 0, got %d", h.scroll)
	}
	if h.width != 0 {
		t.Errorf("expected width to be 0, got %d", h.width)
	}
	if h.height != 0 {
		t.Errorf("expected height to be 0, got %d", h.height)
	}
}

func TestHelpToggle(t *testing.T) {
	h := NewHelpModel()

	h.Toggle()
	if !h.Visible() {
		t.Error("expected help to be visible after first toggle")
	}

	h.Toggle()
	if h.Visible() {
		t.Error("expected help to be hidden after second toggle")
	}
}

func TestHelpToggleResetsScroll(t *testing.T) {
	h := NewHelpModel()
	h.scroll = 5

	h.Toggle()
	if h.scroll != 0 {
		t.Errorf("expected scroll to reset to 0 after toggle, got %d", h.scroll)
	}
}

func TestHelpSetSize(t *testing.T) {
	h := NewHelpModel()
	h.SetSize(80, 40)

	if h.width != 80 {
		t.Errorf("expected width 80, got %d", h.width)
	}
	if h.height != 40 {
		t.Errorf("expected height 40, got %d", h.height)
	}
}

func TestHelpUpdateScrollDown(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 0

	h = h.Update(helpKeyMsg("j"))
	if h.scroll != 1 {
		t.Errorf("expected scroll 1 after 'j', got %d", h.scroll)
	}

	h = h.Update(helpKeyMsg("j"))
	if h.scroll != 2 {
		t.Errorf("expected scroll 2 after second 'j', got %d", h.scroll)
	}
}

func TestHelpUpdateScrollUp(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 3

	h = h.Update(helpKeyMsg("k"))
	if h.scroll != 2 {
		t.Errorf("expected scroll 2 after 'k', got %d", h.scroll)
	}
}

func TestHelpUpdateScrollUpAtZero(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 0

	h = h.Update(helpKeyMsg("k"))
	if h.scroll != 0 {
		t.Errorf("expected scroll to remain 0 after 'k' at top, got %d", h.scroll)
	}
}

func TestHelpUpdateHomeKey(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 10

	h = h.Update(helpKeyMsg("home"))
	if h.scroll != 0 {
		t.Errorf("expected scroll 0 after 'home', got %d", h.scroll)
	}
}

func TestHelpUpdateGKey(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 10

	h = h.Update(helpKeyMsg("g"))
	if h.scroll != 0 {
		t.Errorf("expected scroll 0 after 'g', got %d", h.scroll)
	}
}

func TestHelpUpdateEscClosesHelp(t *testing.T) {
	h := NewHelpModel()
	h.visible = true

	h = h.Update(helpKeyMsg("esc"))
	if h.Visible() {
		t.Error("expected help to be hidden after esc")
	}
}

func TestHelpUpdateQuestionMarkClosesHelp(t *testing.T) {
	h := NewHelpModel()
	h.visible = true

	h = h.Update(helpKeyMsg("?"))
	if h.Visible() {
		t.Error("expected help to be hidden after '?'")
	}
}

func TestHelpUpdateQClosesHelp(t *testing.T) {
	h := NewHelpModel()
	h.visible = true

	h = h.Update(helpKeyMsg("q"))
	if h.Visible() {
		t.Error("expected help to be hidden after 'q'")
	}
}

func TestBuildContentMigrationTab(t *testing.T) {
	h := NewHelpModel()
	content := h.buildContent(TabMigration)

	if !strings.Contains(content, "Global") {
		t.Error("expected content to contain 'Global' section")
	}
	if !strings.Contains(content, "Migration Tab") {
		t.Error("expected content to contain 'Migration Tab' section")
	}
	if !strings.Contains(content, "Ctrl+R") {
		t.Error("expected content to contain 'Ctrl+R' key")
	}
}

func TestBuildContentLogsTab(t *testing.T) {
	h := NewHelpModel()
	content := h.buildContent(TabLogs)

	if !strings.Contains(content, "Global") {
		t.Error("expected content to contain 'Global' section")
	}
	if !strings.Contains(content, "Logs Tab") {
		t.Error("expected content to contain 'Logs Tab' section")
	}
}

func TestBuildContentLibvirtTab(t *testing.T) {
	h := NewHelpModel()
	content := h.buildContent(TabLibvirt)

	if !strings.Contains(content, "Libvirt VMs Tab") {
		t.Error("expected content to contain 'Libvirt VMs Tab' section")
	}
	if !strings.Contains(content, "Start VM") {
		t.Error("expected content to contain 'Start VM' action")
	}
}

func TestBuildContentKubernetesTab(t *testing.T) {
	h := NewHelpModel()
	content := h.buildContent(TabKubernetes)

	if !strings.Contains(content, "Kubernetes Tab") {
		t.Error("expected content to contain 'Kubernetes Tab' section")
	}
	if !strings.Contains(content, "SSH") {
		t.Error("expected content to contain 'SSH' action")
	}
	if !strings.Contains(content, "Navigate") || !strings.Contains(content, "list") {
		t.Error("expected content to contain navigation info")
	}
}

func TestBuildContentAlwaysIncludesGlobal(t *testing.T) {
	h := NewHelpModel()

	for _, tab := range []int{TabMigration, TabLogs, TabLibvirt, TabKubernetes} {
		content := h.buildContent(tab)
		if !strings.Contains(content, "Global") {
			t.Errorf("expected content for tab %d to contain 'Global' section", tab)
		}
		if !strings.Contains(content, "Ctrl+C") {
			t.Errorf("expected content for tab %d to contain 'Ctrl+C'", tab)
		}
	}
}

func TestBuildContentAlwaysIncludesProfiles(t *testing.T) {
	h := NewHelpModel()

	for _, tab := range []int{TabMigration, TabLogs, TabLibvirt, TabKubernetes} {
		content := h.buildContent(tab)
		if !strings.Contains(content, "Profiles") {
			t.Errorf("expected content for tab %d to contain 'Profiles' section", tab)
		}
	}
}

func TestHelpUpdateDownArrow(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 0

	h = h.Update(helpKeyMsg("down"))
	if h.scroll != 1 {
		t.Errorf("expected scroll 1 after 'down', got %d", h.scroll)
	}
}

func TestHelpUpdateUpArrow(t *testing.T) {
	h := NewHelpModel()
	h.visible = true
	h.scroll = 5

	h = h.Update(helpKeyMsg("up"))
	if h.scroll != 4 {
		t.Errorf("expected scroll 4 after 'up', got %d", h.scroll)
	}
}
