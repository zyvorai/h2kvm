// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package widgets

import (
	"fmt"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/theme"
)

// Local styles for the status bar — uses theme colors.
var (
	sbConnectedStyle    = lipgloss.NewStyle().Foreground(theme.Active.Success).Bold(true)
	sbDisconnectedStyle = lipgloss.NewStyle().Foreground(theme.Active.Error).Bold(true)
	sbLabelStyle        = lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Fg)
	sbHintKeyStyle      = lipgloss.NewStyle().Foreground(theme.Active.Primary).Bold(true)
	sbHintStyle         = lipgloss.NewStyle().Foreground(theme.Active.Muted)
	sbBarStyle          = lipgloss.NewStyle().Foreground(theme.Active.Fg).Background(theme.Active.Border).Padding(0, 1)
)

// StatusBar is a Bubble Tea model for the bottom status bar.
type StatusBar struct {
	connected        bool
	activeMigrations int
	width            int
}

// NewStatusBar creates a new status bar.
func NewStatusBar(width int) StatusBar {
	return StatusBar{
		width: width,
	}
}

// SetConnected updates the connection status.
func (sb StatusBar) SetConnected(connected bool) StatusBar {
	sb.connected = connected
	return sb
}

// SetActiveMigrations updates the active migration count.
func (sb StatusBar) SetActiveMigrations(n int) StatusBar {
	sb.activeMigrations = n
	return sb
}

// SetWidth updates the status bar width.
func (sb StatusBar) SetWidth(w int) StatusBar {
	sb.width = w
	return sb
}

// Init implements tea.Model.
func (sb StatusBar) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model.
func (sb StatusBar) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	return sb, nil
}

// View implements tea.Model.
func (sb StatusBar) View() string {
	// Connection indicator
	var connStatus string
	if sb.connected {
		connStatus = sbConnectedStyle.Render("\u25cf Connected")
	} else {
		connStatus = sbDisconnectedStyle.Render("\u25cb Disconnected")
	}

	// Active migrations indicator
	migrationsText := sbLabelStyle.Render(
		fmt.Sprintf("Migrations: %d active", sb.activeMigrations),
	)

	// Key hints
	hints := sbHintKeyStyle.Render("F1") + sbHintStyle.Render(" Help  ") +
		sbHintKeyStyle.Render("F2") + sbHintStyle.Render(" Wizard  ") +
		sbHintKeyStyle.Render("Tab") + sbHintStyle.Render(" Switch  ") +
		sbHintKeyStyle.Render("Ctrl+Q") + sbHintStyle.Render(" Quit")

	// Build status bar: left-aligned status, right-aligned hints
	left := connStatus + "  " + migrationsText
	right := hints

	// Calculate spacing
	leftWidth := lipgloss.Width(left)
	rightWidth := lipgloss.Width(right)
	spacing := sb.width - leftWidth - rightWidth
	if spacing < 1 {
		spacing = 1
	}

	padStyle := lipgloss.NewStyle().Width(spacing)
	bar := left + padStyle.Render("") + right

	return sbBarStyle.Width(sb.width).Render(bar)
}
