// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package ui

import (
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/theme"
)

// Legacy aliases.
var (
	Coral       = theme.Coral
	CoralLight  = theme.CoralLight
	Orange      = theme.Orange
	OrangeLight = theme.OrangeLight
	Green       = theme.Green
	Red         = theme.Red
	Yellow      = theme.Yellow
	Cyan        = theme.Cyan
	Dim         = theme.Dim
	BgDark      = theme.BgDark
)

// ── Tabs — blue active, dim inactive ──

var TabActiveStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Bg).
	Background(theme.Active.Primary).
	Padding(0, 2)

var TabInactiveStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Muted).
	Background(theme.Active.BgPanel).
	Padding(0, 2)

var TabBarStyle = lipgloss.NewStyle().
	Background(theme.Active.Bg)

var TitleBarStyle = TabActiveStyle

// ── Content ──

var ContentStyle = lipgloss.NewStyle().
	Padding(0, 1)

// ── Status Bar ──

var StatusBarStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Fg).
	Background(theme.Active.BgPanel).
	Padding(0, 1)

var StatusConnectedStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Success).
	Bold(true)

var StatusDisconnectedStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Error).
	Bold(true)

// ── Cards / Panels — straight borders for industrial look ──

var BorderStyle = lipgloss.NewStyle().
	Border(lipgloss.NormalBorder()).
	BorderForeground(theme.Active.Border)

var FocusedBorderStyle = lipgloss.NewStyle().
	Border(lipgloss.NormalBorder()).
	BorderForeground(theme.Active.Primary)

var BlurredBorderStyle = lipgloss.NewStyle().
	Border(lipgloss.NormalBorder()).
	BorderForeground(theme.Active.Subtle)

var PanelStyle = lipgloss.NewStyle().
	Border(lipgloss.NormalBorder()).
	BorderForeground(theme.Active.Border).
	Padding(1, 2)

var ActivePanelStyle = lipgloss.NewStyle().
	Border(lipgloss.NormalBorder()).
	BorderForeground(theme.Active.Primary).
	Padding(1, 2)

var OverlayStyle = lipgloss.NewStyle().
	Border(lipgloss.DoubleBorder()).
	BorderForeground(theme.Active.Accent).
	Padding(1, 2)

// ── Typography — clear hierarchy ──

var TitleStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Primary).
	MarginBottom(1)

var HeadingStyle = TitleStyle

var SubtitleStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Accent)

var SubtleStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Subtle)

var LabelStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Muted)

var ValueStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Fg)

// ── Status ──

var ErrorStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Error).
	Bold(true)

var WarningStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Warning).
	Bold(true)

var SuccessStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Success)

var DimStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Muted)

// ── Badges ──

var BadgeStyle = lipgloss.NewStyle().
	Background(theme.Active.Primary).
	Foreground(theme.Active.Bg).
	Padding(0, 1).
	Bold(true)

var BadgeSuccessStyle = lipgloss.NewStyle().
	Background(theme.Active.Success).
	Foreground(theme.Active.Bg).
	Padding(0, 1).
	Bold(true)

var BadgeWarningStyle = lipgloss.NewStyle().
	Background(theme.Active.Warning).
	Foreground(theme.Active.Bg).
	Padding(0, 1).
	Bold(true)

var BadgeErrorStyle = lipgloss.NewStyle().
	Background(theme.Active.Error).
	Foreground(theme.Active.Bg).
	Padding(0, 1).
	Bold(true)

// ── Key hints — yellow keys, muted descriptions ──

var KeyHintStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Muted)

var KeyHintKeyStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Highlight).
	Bold(true)

var HelpKeyStyle = KeyHintKeyStyle
var HelpDescStyle = DimStyle

// ── Tables + Selection ──

var SelectedStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Primary)

var SelectedRowStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Bg).
	Background(theme.Active.Primary).
	Bold(true)

var TableHeaderStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Muted).
	BorderBottom(true).
	BorderStyle(lipgloss.NormalBorder()).
	BorderForeground(theme.Active.Border)

var StatsStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Accent).
	Bold(true)

// ── Progress ──

var ProgressFullStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Success)

var ProgressEmptyStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Border)

var ToggleOnStyle = lipgloss.NewStyle().
	Bold(true).
	Foreground(theme.Active.Success)

var ToggleOffStyle = lipgloss.NewStyle().
	Foreground(theme.Active.Muted)

func RenderProgressBar(percent float64, width int) string {
	if width < 3 {
		width = 3
	}
	filled := int(percent / 100.0 * float64(width))
	if filled > width {
		filled = width
	}
	if filled < 0 {
		filled = 0
	}
	return ProgressFullStyle.Render(repeatChar('█', filled)) +
		ProgressEmptyStyle.Render(repeatChar('░', width-filled))
}

func repeatChar(ch rune, n int) string {
	if n <= 0 {
		return ""
	}
	b := make([]rune, n)
	for i := range b {
		b[i] = ch
	}
	return string(b)
}

func RenderToggle(on bool) string {
	if on {
		return ToggleOnStyle.Render("◉ ON")
	}
	return ToggleOffStyle.Render("○ OFF")
}

func RenderBadge(status string) string {
	switch status {
	case "running", "active", "ready":
		return BadgeSuccessStyle.Render(status)
	case "warning", "pending":
		return BadgeWarningStyle.Render(status)
	case "error", "failed":
		return BadgeErrorStyle.Render(status)
	default:
		return BadgeStyle.Render(status)
	}
}
