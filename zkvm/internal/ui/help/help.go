// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package help

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/state"
	"github.com/h2kvm/zkvm/internal/ui"
)

// shortcut represents a single key binding entry.
type shortcut struct {
	key  string
	desc string
}

// section groups related shortcuts under a heading.
type section struct {
	title    string
	bindings []shortcut
}

var sections = []section{
	{
		title: "Global",
		bindings: []shortcut{
			{"Ctrl+Q", "Quit application"},
			{"F1", "Toggle help overlay"},
			{"F2", "Open migration wizard"},
			{"F3", "Open VM/disk browser"},
			{"F5", "Refresh data"},
			{"Ctrl+S", "Open settings"},
			{"Tab", "Next tab"},
			{"Shift+Tab", "Previous tab"},
		},
	},
	{
		title: "Navigation",
		bindings: []shortcut{
			{"j / Down", "Move cursor down"},
			{"k / Up", "Move cursor up"},
			{"Enter", "Select / confirm"},
			{"Esc", "Back / close"},
			{"h / Left", "Cycle option left"},
			{"l / Right", "Cycle option right"},
		},
	},
	{
		title: "Dashboard",
		bindings: []shortcut{
			{"r", "Refresh dashboard"},
			{"j / k", "Navigate active migrations"},
		},
	},
	{
		title: "Wizard",
		bindings: []shortcut{
			{"Enter", "Advance to next step"},
			{"Esc", "Go back one step"},
			{"Tab", "Cycle fields within step"},
			{"Space", "Toggle option"},
		},
	},
	{
		title: "Migrations",
		bindings: []shortcut{
			{"p", "Pause selected migration"},
			{"r", "Resume selected migration"},
			{"c", "Cancel selected migration"},
			{"Enter", "View migration details"},
			{"d", "Remove from batch queue"},
		},
	},
}

// Model is the help overlay tab.
type Model struct {
	store  *state.Store
	width  int
	height int
	scroll int
}

// New creates a new help model.
func New(store *state.Store) Model {
	return Model{
		store: store,
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Help"
}

// Init initializes the help overlay.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the help overlay.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.scroll > 0 {
				m.scroll--
			}
		case "down", "j":
			m.scroll++
		case "home":
			m.scroll = 0
		}
	}
	return m, nil
}

// View renders the help overlay.
func (m Model) View() string {
	var b strings.Builder

	title := lipgloss.NewStyle().
		Bold(true).
		Foreground(ui.Coral).
		Render("Keyboard Shortcuts")

	b.WriteString(title)
	b.WriteString("\n\n")

	for i, sec := range sections {
		sectionHeader := ui.SubtitleStyle.Render(sec.title)
		b.WriteString(sectionHeader)
		b.WriteString("\n")

		for _, bind := range sec.bindings {
			keyCol := ui.HelpKeyStyle.Render(fmt.Sprintf("  %-14s", bind.key))
			descCol := ui.HelpDescStyle.Render(bind.desc)
			b.WriteString(keyCol + "  " + descCol + "\n")
		}

		if i < len(sections)-1 {
			b.WriteString("\n")
		}
	}

	b.WriteString("\n")
	dismiss := ui.DimStyle.Render("Press Esc or F1 to dismiss")
	b.WriteString(dismiss)

	content := b.String()

	// Apply scrolling.
	lines := strings.Split(content, "\n")
	if m.scroll > 0 {
		if m.scroll >= len(lines) {
			m.scroll = len(lines) - 1
		}
		lines = lines[m.scroll:]
	}

	// Limit visible lines to terminal height minus some margin.
	maxVisible := m.height - 4
	if maxVisible <= 0 {
		maxVisible = 40
	}
	if len(lines) > maxVisible {
		lines = lines[:maxVisible]
	}

	scrolled := strings.Join(lines, "\n")

	// Wrap in overlay style.
	overlayWidth := 50
	if m.width > 60 {
		overlayWidth = 55
	}

	return ui.OverlayStyle.Width(overlayWidth).Render(scrolled)
}
