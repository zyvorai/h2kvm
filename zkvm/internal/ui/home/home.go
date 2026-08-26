// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package home

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/state"
	"github.com/h2kvm/zkvm/internal/ui"
)

const asciiTitle = `
 _                           ____  _
| |__  _   _ _ __   ___ _ __|___ \| | ____   ___ __ ___
| '_ \| | | | '_ \ / _ \ '__| __) | |/ /\ \ / / '_ ' _ \
| | | | |_| | |_) |  __/ |  / __/|   <  \ V /| | | | | |
|_| |_|\__, | .__/ \___|_| |_____|_|\_\  \_/ |_| |_| |_|
       |___/|_|
`

// Model is the home tab view.
type Model struct {
	store  *state.Store
	width  int
	height int
}

// New creates a new home tab model.
func New(store *state.Store) Model {
	return Model{
		store: store,
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Home"
}

// Init initializes the home tab.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the home tab.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	}
	return m, nil
}

// View renders the home tab.
func (m Model) View() string {
	var b strings.Builder

	// ASCII title in coral
	titleStyle := lipgloss.NewStyle().
		Foreground(ui.Green).
		Bold(true)
	b.WriteString(titleStyle.Render(asciiTitle))
	b.WriteString("\n")

	// Version info
	versionLine := ui.SubtitleStyle.Render("Version: ") +
		ui.ValueStyle.Render(m.store.Version)
	b.WriteString(versionLine)
	b.WriteString("\n\n")

	// Connection status
	connStatus := m.renderConnectionStatus()
	b.WriteString(connStatus)
	b.WriteString("\n\n")

	// Quick stats panel
	statsPanel := m.renderStatsPanel()
	b.WriteString(statsPanel)
	b.WriteString("\n\n")

	// Quick actions
	actionsPanel := m.renderQuickActions()
	b.WriteString(actionsPanel)

	return b.String()
}

func (m Model) renderConnectionStatus() string {
	var indicator string
	if m.store.IsConnected() {
		indicator = ui.SuccessStyle.Render("● Connected")
	} else {
		indicator = ui.ErrorStyle.Render("● Disconnected")
	}
	return ui.LabelStyle.Render("Backend: ") + indicator
}

func (m Model) renderStatsPanel() string {
	stats := m.store.GetStats()

	header := ui.SubtitleStyle.Render("Quick Stats")

	rows := []string{
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Total Migrations:"),
			ui.ValueStyle.Render(fmt.Sprintf("%d", stats.TotalMigrations))),
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Active:"),
			ui.ValueStyle.Render(fmt.Sprintf("%d", stats.ActiveMigrations))),
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Completed Today:"),
			ui.ValueStyle.Render(fmt.Sprintf("%d", stats.CompletedToday))),
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Success Rate:"),
			m.renderSuccessRate(stats.SuccessRate)),
	}

	content := header + "\n" + strings.Join(rows, "\n")

	panelWidth := 40
	if m.width > 0 && m.width < panelWidth+6 {
		panelWidth = m.width - 6
	}

	return ui.PanelStyle.Width(panelWidth).Render(content)
}

func (m Model) renderSuccessRate(rate float64) string {
	text := fmt.Sprintf("%.1f%%", rate)
	if rate >= 90 {
		return ui.SuccessStyle.Render(text)
	} else if rate >= 70 {
		return ui.WarningStyle.Render(text)
	}
	return ui.ErrorStyle.Render(text)
}

func (m Model) renderQuickActions() string {
	header := ui.SubtitleStyle.Render("Quick Actions")

	actions := []string{
		fmt.Sprintf("  %s  %s",
			ui.HelpKeyStyle.Render("F2"),
			ui.HelpDescStyle.Render("Migration Wizard")),
		fmt.Sprintf("  %s  %s",
			ui.HelpKeyStyle.Render("F3"),
			ui.HelpDescStyle.Render("Browse VMs")),
		fmt.Sprintf("  %s  %s",
			ui.HelpKeyStyle.Render("F1"),
			ui.HelpDescStyle.Render("Help")),
	}

	content := header + "\n" + strings.Join(actions, "\n")

	panelWidth := 40
	if m.width > 0 && m.width < panelWidth+6 {
		panelWidth = m.width - 6
	}

	return ui.PanelStyle.Width(panelWidth).Render(content)
}
