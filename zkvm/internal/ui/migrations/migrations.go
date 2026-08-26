// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package migrations

import (
	"fmt"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/models"
	"github.com/h2kvm/zkvm/internal/state"
	"github.com/h2kvm/zkvm/internal/ui"
)

// Model is the active migrations panel tab.
type Model struct {
	store    *state.Store
	width    int
	height   int
	selected int
}

// New creates a new migrations model.
func New(store *state.Store) Model {
	return Model{
		store: store,
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Migrations"
}

// Init initializes the migrations panel.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the migrations tab.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		all := m.allMigrations()

		switch msg.String() {
		case "up", "k":
			if m.selected > 0 {
				m.selected--
			}
		case "down", "j":
			if m.selected < len(all)-1 {
				m.selected++
			}

		case "p":
			if id := m.selectedIDFrom(all); id != "" {
				return m, func() tea.Msg { return models.PauseMigrationMsg{ID: id} }
			}
		case "r":
			if id := m.selectedIDFrom(all); id != "" {
				return m, func() tea.Msg { return models.ResumeMigrationMsg{ID: id} }
			}
		case "c":
			if id := m.selectedIDFrom(all); id != "" {
				return m, func() tea.Msg { return models.CancelMigrationMsg{ID: id} }
			}
		}
	}
	return m, nil
}

// allMigrations returns a snapshot of all migrations sorted by start time
// (most recent first). It collects both active and non-active records.
func (m Model) allMigrations() []*models.MigrationRecord {
	var all []*models.MigrationRecord
	for _, rec := range m.store.Migrations {
		all = append(all, rec)
	}

	sort.Slice(all, func(i, j int) bool {
		return all[i].StartTime.After(all[j].StartTime)
	})

	return all
}

// SelectedID returns the migration ID of the currently selected row, if any.
func (m Model) SelectedID() string {
	return m.selectedIDFrom(m.allMigrations())
}

// selectedIDFrom returns the selected ID from a pre-computed migrations slice.
func (m Model) selectedIDFrom(all []*models.MigrationRecord) string {
	if m.selected >= 0 && m.selected < len(all) {
		return all[m.selected].ID
	}
	return ""
}

// View renders the migrations panel.
func (m Model) View() string {
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render("Active Migrations"))
	b.WriteString("\n")

	migrations := m.allMigrations()

	if len(migrations) == 0 {
		b.WriteString(ui.DimStyle.Render("  No migrations to display"))
		b.WriteString("\n\n")
		b.WriteString(ui.DimStyle.Render("  Start a migration from the Wizard (F2) or Browser (F3)"))
		b.WriteString("\n")
		return b.String()
	}

	// Table header.
	colWidths := []int{8, 20, 12, 10, 16, 10, 12}
	headers := []string{"ID", "VM Name", "Status", "Progress", "Stage", "Duration", "Throughput"}
	headerLine := renderRow(headers, colWidths, ui.TableHeaderStyle)
	b.WriteString(headerLine + "\n")

	for i, mig := range migrations {
		style := lipgloss.NewStyle()
		if i == m.selected {
			style = ui.SelectedStyle
		}

		progress := fmt.Sprintf("%.1f%%", mig.Progress)
		progressBar := ui.RenderProgressBar(mig.Progress, 6)
		progressCol := progress + " " + progressBar

		duration := formatDuration(mig.Duration())
		throughput := fmt.Sprintf("%.1f MB/s", mig.Throughput)
		status := renderStatus(mig.Status)

		shortID := mig.ID
		if len(shortID) > 8 {
			shortID = shortID[:8]
		}

		cols := []string{
			shortID,
			truncate(mig.VMName, colWidths[1]),
			status,
			progressCol,
			truncate(mig.CurrentStage, colWidths[4]),
			duration,
			throughput,
		}

		b.WriteString(renderRow(cols, colWidths, style) + "\n")
	}

	b.WriteString("\n")
	helpLine := ui.DimStyle.Render("p: pause  r: resume  c: cancel  enter: details  j/k: navigate")
	b.WriteString(helpLine)

	return b.String()
}

func renderRow(cols []string, widths []int, style lipgloss.Style) string {
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

func formatDuration(d time.Duration) string {
	secs := int(d.Seconds())
	if secs < 60 {
		return fmt.Sprintf("%ds", secs)
	}
	m := secs / 60
	s := secs % 60
	if m < 60 {
		return fmt.Sprintf("%dm%02ds", m, s)
	}
	h := m / 60
	m = m % 60
	return fmt.Sprintf("%dh%02dm", h, m)
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
