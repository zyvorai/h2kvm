// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package widgets

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/theme"
)

// maxLogLines is the maximum number of lines retained in the log viewer.
const maxLogLines = 1000

// LogView is a viewport-based scrollable log viewer.
type LogView struct {
	viewport   viewport.Model
	lines      []string
	autoScroll bool
	width      int
	height     int
}

// NewLogView creates a new log viewer with the given dimensions.
func NewLogView(width, height int) LogView {
	vp := viewport.New(width, height)
	vp.Style = lipgloss.NewStyle()

	return LogView{
		viewport:   vp,
		lines:      make([]string, 0, maxLogLines),
		autoScroll: true,
		width:      width,
		height:     height,
	}
}

// SetSize updates the log viewer dimensions.
func (lv LogView) SetSize(width, height int) LogView {
	lv.width = width
	lv.height = height
	lv.viewport.Width = width
	lv.viewport.Height = height
	lv.viewport.SetContent(strings.Join(lv.lines, "\n"))
	if lv.autoScroll {
		lv.viewport.GotoBottom()
	}
	return lv
}

// AppendLog adds a log line with color based on level.
func (lv LogView) AppendLog(level, message string) LogView {
	styled := lv.colorize(level, message)
	lv.lines = append(lv.lines, styled)

	// Enforce maximum line count.
	if len(lv.lines) > maxLogLines {
		excess := len(lv.lines) - maxLogLines
		lv.lines = lv.lines[excess:]
	}

	lv.viewport.SetContent(strings.Join(lv.lines, "\n"))
	if lv.autoScroll {
		lv.viewport.GotoBottom()
	}
	return lv
}

// colorize returns a styled log line based on the log level.
func (lv LogView) colorize(level, message string) string {
	var style lipgloss.Style

	switch strings.ToUpper(level) {
	case "ERROR":
		style = lipgloss.NewStyle().Foreground(theme.Red)
	case "WARNING", "WARN":
		style = lipgloss.NewStyle().Foreground(theme.Yellow)
	case "INFO":
		style = lipgloss.NewStyle().Foreground(theme.Cyan)
	case "DEBUG":
		style = lipgloss.NewStyle().Foreground(theme.Dim)
	default:
		style = lipgloss.NewStyle()
	}

	prefix := style.Render(fmt.Sprintf("[%-7s]", strings.ToUpper(level)))
	return prefix + " " + message
}

// SetAutoScroll enables or disables auto-scrolling to the bottom.
func (lv LogView) SetAutoScroll(enabled bool) LogView {
	lv.autoScroll = enabled
	return lv
}

// Clear removes all log lines.
func (lv LogView) Clear() LogView {
	lv.lines = lv.lines[:0]
	lv.viewport.SetContent("")
	return lv
}

// LineCount returns the number of stored log lines.
func (lv LogView) LineCount() int {
	return len(lv.lines)
}

// Lines returns all stored log lines.
func (lv LogView) Lines() []string {
	return lv.lines
}

// Init implements tea.Model.
func (lv LogView) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model.
func (lv LogView) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	lv.viewport, cmd = lv.viewport.Update(msg)

	// Disable auto-scroll if the user scrolled away from the bottom.
	if lv.viewport.AtBottom() {
		lv.autoScroll = true
	} else {
		lv.autoScroll = false
	}

	return lv, cmd
}

// UpdateLogView provides typed access to Update that returns LogView
// instead of tea.Model, for convenience when embedding.
func (lv LogView) UpdateLogView(msg tea.Msg) (LogView, tea.Cmd) {
	var cmd tea.Cmd
	lv.viewport, cmd = lv.viewport.Update(msg)

	if lv.viewport.AtBottom() {
		lv.autoScroll = true
	} else {
		lv.autoScroll = false
	}

	return lv, cmd
}

// View implements tea.Model.
func (lv LogView) View() string {
	return lv.viewport.View()
}
