// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package theme

import "github.com/charmbracelet/lipgloss"

// Theme holds a complete color palette.
type Theme struct {
	Bg        lipgloss.Color
	BgPanel   lipgloss.Color
	Fg        lipgloss.Color
	Primary   lipgloss.Color
	Secondary lipgloss.Color
	Accent    lipgloss.Color
	Success   lipgloss.Color
	Warning   lipgloss.Color
	Error     lipgloss.Color
	Highlight lipgloss.Color
	Border    lipgloss.Color
	Muted     lipgloss.Color
	Subtle    lipgloss.Color
}

// Forge — signature zkvm premium theme.
// Industrial + modern. Warm orange accent + cold graphite depth.
var Forge = Theme{
	Bg:        lipgloss.Color("#0b0b0c"), // Near black
	BgPanel:   lipgloss.Color("#141416"), // Deep carbon
	Fg:        lipgloss.Color("#e8e6df"), // Warm white
	Primary:   lipgloss.Color("#ff8f3f"), // Refined orange
	Secondary: lipgloss.Color("#cc6f2c"), // Darker orange
	Accent:    lipgloss.Color("#ff8f3f"), // Orange
	Success:   lipgloss.Color("#7fb069"), // Olive green
	Warning:   lipgloss.Color("#e6a84a"), // Warm amber
	Error:     lipgloss.Color("#d95757"), // Soft red
	Highlight: lipgloss.Color("#e6a84a"), // Amber key hints
	Border:    lipgloss.Color("#26262b"), // Subtle edge
	Muted:     lipgloss.Color("#7a7a82"), // Soft gray
	Subtle:    lipgloss.Color("#4a4a50"), // Faint UI
}

// TokyoNight — clean harmonious blue theme.
var TokyoNight = Theme{
	Bg:        lipgloss.Color("#0f111a"),
	BgPanel:   lipgloss.Color("#1a1d2b"),
	Fg:        lipgloss.Color("#c0caf5"),
	Primary:   lipgloss.Color("#7aa2f7"),
	Secondary: lipgloss.Color("#9ece6a"),
	Accent:    lipgloss.Color("#bb9af7"),
	Success:   lipgloss.Color("#9ece6a"),
	Warning:   lipgloss.Color("#e0af68"),
	Error:     lipgloss.Color("#f7768e"),
	Highlight: lipgloss.Color("#e0af68"),
	Border:    lipgloss.Color("#2a2f45"),
	Muted:     lipgloss.Color("#565f89"),
	Subtle:    lipgloss.Color("#3b4261"),
}

// Hypersdk — neon cyberpunk.
var Hypersdk = Theme{
	Bg:        lipgloss.Color("#0d0d0d"),
	BgPanel:   lipgloss.Color("#1a1a1a"),
	Fg:        lipgloss.Color("#e0e0e0"),
	Primary:   lipgloss.Color("#00ffff"),
	Secondary: lipgloss.Color("#ff00ff"),
	Accent:    lipgloss.Color("#00ffff"),
	Success:   lipgloss.Color("#00ff00"),
	Warning:   lipgloss.Color("#ffaa00"),
	Error:     lipgloss.Color("#ff0000"),
	Highlight: lipgloss.Color("#ffff00"),
	Border:    lipgloss.Color("#333333"),
	Muted:     lipgloss.Color("#666666"),
	Subtle:    lipgloss.Color("#444444"),
}

// Light theme.
var Light = Theme{
	Bg:        lipgloss.Color("#f0f0f5"),
	BgPanel:   lipgloss.Color("#ffffff"),
	Fg:        lipgloss.Color("#1a1b26"),
	Primary:   lipgloss.Color("#d45d1e"),
	Secondary: lipgloss.Color("#587539"),
	Accent:    lipgloss.Color("#d45d1e"),
	Success:   lipgloss.Color("#587539"),
	Warning:   lipgloss.Color("#8f5e15"),
	Error:     lipgloss.Color("#c64343"),
	Highlight: lipgloss.Color("#8f5e15"),
	Border:    lipgloss.Color("#d0d0e0"),
	Muted:     lipgloss.Color("#8990b3"),
	Subtle:    lipgloss.Color("#b0b0c0"),
}

// Active theme. Default: Forge.
var Active = Forge

func SetTheme(name string) {
	switch name {
	case "tokyo", "blue":
		Active = TokyoNight
	case "neon", "hypersdk", "cyber":
		Active = Hypersdk
	case "light":
		Active = Light
	default:
		Active = Forge
	}
	updateAliases()
}

func init() { updateAliases() }

// Legacy aliases.
var (
	Primary      = Active.Primary
	PrimaryDim   = Active.Muted
	Accent       = Active.Accent
	AccentBright = Active.Accent
	Coral        = Active.Accent
	CoralLight   = Active.Accent
	Orange       = Active.Warning
	OrangeLight  = Active.Warning
	Green        = Active.Success
	GreenBright  = Active.Success
	Red          = Active.Error
	Yellow       = Active.Highlight
	Cyan         = Active.Primary
	Blue         = Active.Primary
	Dim          = Active.Muted
	DimLight     = Active.Muted
	White        = Active.Fg
	BgDark       = Active.Bg
	BgPanel      = Active.BgPanel
	BgHighlight  = Active.Border
)

func updateAliases() {
	Primary = Active.Primary
	PrimaryDim = Active.Muted
	Accent = Active.Accent
	AccentBright = Active.Accent
	Coral = Active.Accent
	CoralLight = Active.Accent
	Orange = Active.Warning
	OrangeLight = Active.Warning
	Green = Active.Success
	GreenBright = Active.Success
	Red = Active.Error
	Yellow = Active.Highlight
	Cyan = Active.Primary
	Blue = Active.Primary
	Dim = Active.Muted
	DimLight = Active.Muted
	White = Active.Fg
	BgDark = Active.Bg
	BgPanel = Active.BgPanel
	BgHighlight = Active.Border
}
