// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package widgets

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/theme"
)

// ProgressBar is a Bubble Tea model that renders a progress bar with percentage.
type ProgressBar struct {
	width    int
	progress float64
}

// NewProgressBar creates a new progress bar with the given width.
func NewProgressBar(width int) ProgressBar {
	if width < 10 {
		width = 20
	}
	return ProgressBar{
		width: width,
	}
}

// SetWidth updates the bar width.
func (p ProgressBar) SetWidth(w int) ProgressBar {
	if w < 10 {
		w = 20
	}
	p.width = w
	return p
}

// SetProgress updates the progress value (clamped to 0.0-1.0).
func (p ProgressBar) SetProgress(v float64) ProgressBar {
	if v < 0 {
		v = 0
	}
	if v > 1 {
		v = 1
	}
	p.progress = v
	return p
}

// progressColor returns the bar color based on progress value.
func (p ProgressBar) progressColor() lipgloss.Color {
	switch {
	case p.progress > 0.7:
		return theme.Green
	case p.progress > 0.3:
		return theme.Yellow
	default:
		return theme.Red
	}
}

// Init implements tea.Model.
func (p ProgressBar) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model.
func (p ProgressBar) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	return p, nil
}

// View implements tea.Model.
func (p ProgressBar) View() string {
	// Reserve space for brackets and percentage label: "[] 100%"
	barWidth := p.width - 7
	if barWidth < 1 {
		barWidth = 1
	}

	filled := int(p.progress * float64(barWidth))
	if filled > barWidth {
		filled = barWidth
	}
	empty := barWidth - filled

	color := p.progressColor()
	filledStyle := lipgloss.NewStyle().Foreground(color)
	emptyStyle := lipgloss.NewStyle().Foreground(theme.Dim)

	bar := "[" +
		filledStyle.Render(strings.Repeat("\u2588", filled)) +
		emptyStyle.Render(strings.Repeat("\u2591", empty)) +
		"]"

	pct := fmt.Sprintf("%3d%%", int(p.progress*100))

	return bar + " " + pct
}
