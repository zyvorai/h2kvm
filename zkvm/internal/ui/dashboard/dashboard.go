// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package dashboard

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/models"
	"github.com/h2kvm/zkvm/internal/state"
	"github.com/h2kvm/zkvm/internal/ui"
)

// Model is the migration dashboard tab view.
type Model struct {
	store    *state.Store
	width    int
	height   int
	selected int
}

// New creates a new dashboard model.
func New(store *state.Store) Model {
	return Model{
		store: store,
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Dashboard"
}

// Init initializes the dashboard.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the dashboard.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.selected > 0 {
				m.selected--
			}
		case "down", "j":
			active := m.store.GetActiveMigrations()
			if m.selected < len(active)-1 {
				m.selected++
			}
		case "r":
			// Refresh is a no-op; data comes from store updates.
		}
	}
	return m, nil
}

// View renders the dashboard.
func (m Model) View() string {
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render("Migration Dashboard"))
	b.WriteString("\n")

	// Quick metrics panel
	metricsPanel := m.renderMetrics()
	b.WriteString(metricsPanel)
	b.WriteString("\n\n")

	// Active migrations table
	tablePanel := m.renderActiveMigrationsTable()
	b.WriteString(tablePanel)
	b.WriteString("\n\n")

	// Recent logs
	logsPanel := m.renderLogs()
	b.WriteString(logsPanel)
	b.WriteString("\n")

	// Help line
	helpLine := ui.DimStyle.Render("r: refresh  j/k: navigate  q: back")
	b.WriteString(helpLine)

	return b.String()
}

func (m Model) renderMetrics() string {
	stats := m.store.GetStats()

	activeStyle := lipgloss.NewStyle().Bold(true).Foreground(ui.Green)
	completedStyle := lipgloss.NewStyle().Bold(true).Foreground(ui.Cyan)
	failedStyle := lipgloss.NewStyle().Bold(true).Foreground(ui.Red)

	metrics := fmt.Sprintf("%s %s    %s %s    %s %s",
		ui.LabelStyle.Render("Active:"),
		activeStyle.Render(fmt.Sprintf("%d", stats.ActiveMigrations)),
		ui.LabelStyle.Render("Completed:"),
		completedStyle.Render(fmt.Sprintf("%d", stats.TotalCompleted)),
		ui.LabelStyle.Render("Failed:"),
		failedStyle.Render(fmt.Sprintf("%d", stats.TotalFailed)),
	)

	return ui.PanelStyle.Render(metrics)
}

func (m Model) renderActiveMigrationsTable() string {
	active := m.store.GetActiveMigrations()

	header := ui.SubtitleStyle.Render("Active Migrations")

	if len(active) == 0 {
		return header + "\n" + ui.DimStyle.Render("  No active migrations")
	}

	// Table header
	colWidths := []int{20, 12, 10, 16, 12, 8}
	headers := []string{"VM Name", "Status", "Progress", "Stage", "Throughput", "ETA"}
	headerLine := renderTableRow(headers, colWidths, ui.TableHeaderStyle)

	var rows []string
	for i, migPtr := range active {
		mig := *migPtr
		rowStyle := lipgloss.NewStyle()
		if i == m.selected {
			rowStyle = ui.SelectedStyle
		}

		progress := fmt.Sprintf("%.1f%%", mig.Progress)
		progressBar := ui.RenderProgressBar(mig.Progress, 8)
		progressCol := progress + " " + progressBar

		throughput := fmt.Sprintf("%.1f MB/s", mig.Throughput)
		eta := formatETA(mig.ETA)
		status := renderStatus(mig.Status)

		cols := []string{
			truncate(mig.VMName, colWidths[0]),
			status,
			progressCol,
			truncate(mig.CurrentStage, colWidths[3]),
			throughput,
			eta,
		}

		row := renderTableRow(cols, colWidths, rowStyle)
		rows = append(rows, row)
	}

	table := header + "\n" + headerLine + "\n" + strings.Join(rows, "\n")
	return table
}

func (m Model) renderLogs() string {
	logs := m.store.GetLogs(20)

	header := ui.SubtitleStyle.Render("Recent Logs")

	if len(logs) == 0 {
		return header + "\n" + ui.DimStyle.Render("  No log entries")
	}

	var lines []string
	for _, log := range logs {
		levelStyle := ui.DimStyle
		switch log.Level {
		case "error":
			levelStyle = ui.ErrorStyle
		case "warning", "warn":
			levelStyle = ui.WarningStyle
		case "info":
			levelStyle = ui.SuccessStyle
		}

		line := fmt.Sprintf("  %s %s %s",
			ui.DimStyle.Render(log.Timestamp),
			levelStyle.Render(fmt.Sprintf("[%-5s]", log.Level)),
			log.Message,
		)
		lines = append(lines, line)
	}

	maxVisible := 10
	if m.height > 30 {
		maxVisible = 20
	}
	if len(lines) > maxVisible {
		lines = lines[len(lines)-maxVisible:]
	}

	content := header + "\n" + strings.Join(lines, "\n")
	return content
}

func renderTableRow(cols []string, widths []int, style lipgloss.Style) string {
	var parts []string
	for i, col := range cols {
		w := 12
		if i < len(widths) {
			w = widths[i]
		}
		cell := fmt.Sprintf("%-*s", w, col)
		parts = append(parts, cell)
	}
	return style.Render(strings.Join(parts, "  "))
}

func renderStatus(status models.MigrationStatus) string {
	switch status {
	case models.StatusRunning:
		return ui.SuccessStyle.Render("Running")
	case models.StatusPaused:
		return ui.WarningStyle.Render("Paused")
	case models.StatusPending:
		return ui.DimStyle.Render("Pending")
	case models.StatusCompleted:
		return ui.SuccessStyle.Render("Done")
	case models.StatusFailed:
		return ui.ErrorStyle.Render("Failed")
	case models.StatusCancelled:
		return ui.DimStyle.Render("Cancelled")
	default:
		return string(status)
	}
}

func formatETA(seconds float64) string {
	if seconds <= 0 {
		return "--"
	}
	m := int(seconds) / 60
	s := int(seconds) % 60
	if m > 0 {
		return fmt.Sprintf("%dm%02ds", m, s)
	}
	return fmt.Sprintf("%ds", s)
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	if maxLen < 4 {
		return s[:maxLen]
	}
	return s[:maxLen-3] + "..."
}
