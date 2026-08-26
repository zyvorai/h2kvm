// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package wizard

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/state"
	"github.com/hyper2kvm/zkvm/internal/ui"
)

const totalSteps = 5

// sourceType enumerates the supported source types.
var sourceTypes = []string{"local", "vsphere", "ova", "hyperv"}

// outputFormats enumerates the supported output disk formats.
var outputFormats = []string{"qcow2", "raw", "vmdk"}

// stepTitles maps step index to a human-readable title.
var stepTitles = []string{
	"Source Type",
	"Source Selection",
	"Target Configuration",
	"Offline Fixes",
	"Confirmation",
}

// Model is the 5-step migration wizard tab.
type Model struct {
	store  *state.Store
	width  int
	height int

	// Current step (0-4).
	step int

	// Step 0: Source type selection.
	sourceTypeIdx int

	// Step 1: Source path or VM picker.
	sourcePath string
	sourceVMs  []string
	sourceVMID int

	// Step 2: Target configuration.
	outputDir      string
	formatIdx      int
	compress       bool
	targetFocusIdx int // 0=outputDir, 1=format, 2=compress

	// Step 3: Offline fixes toggles.
	fixFstab       bool
	fixInitramfs   bool
	fixGrub        bool
	fixNetwork     bool
	fixesFocusIdx  int // 0-3

	// Step 4: Confirmation (read-only summary).
}

// New creates a new wizard model.
func New(store *state.Store) Model {
	cfg := store.GetConfig()
	return Model{
		store:        store,
		outputDir:    cfg.General.OutputDir,
		compress:     cfg.Migration.EnableCompression,
		fixFstab:     true,
		fixInitramfs: cfg.OfflineFixes.RegenInitramfs,
		fixGrub:      cfg.OfflineFixes.UpdateGrub,
		fixNetwork:   cfg.OfflineFixes.FixNetwork,
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Wizard"
}

// Init initializes the wizard.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the wizard.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		switch msg.String() {
		case "esc":
			if m.step > 0 {
				m.step--
			}
			return m, nil

		case "enter":
			if m.step < totalSteps-1 {
				m.step++
			}
			return m, nil

		case "tab":
			m.cycleFieldForward()
			return m, nil

		case "shift+tab":
			m.cycleFieldBackward()
			return m, nil
		}

		// Delegate to step-specific handlers.
		switch m.step {
		case 0:
			m.updateStepSourceType(msg)
		case 1:
			m.updateStepSourceSelection(msg)
		case 2:
			m.updateStepTarget(msg)
		case 3:
			m.updateStepFixes(msg)
		}
	}
	return m, nil
}

func (m *Model) cycleFieldForward() {
	switch m.step {
	case 2:
		m.targetFocusIdx = (m.targetFocusIdx + 1) % 3
	case 3:
		m.fixesFocusIdx = (m.fixesFocusIdx + 1) % 4
	}
}

func (m *Model) cycleFieldBackward() {
	switch m.step {
	case 2:
		m.targetFocusIdx = (m.targetFocusIdx + 2) % 3
	case 3:
		m.fixesFocusIdx = (m.fixesFocusIdx + 3) % 4
	}
}

func (m *Model) updateStepSourceType(msg tea.KeyMsg) {
	switch msg.String() {
	case "up", "k":
		if m.sourceTypeIdx > 0 {
			m.sourceTypeIdx--
		}
	case "down", "j":
		if m.sourceTypeIdx < len(sourceTypes)-1 {
			m.sourceTypeIdx++
		}
	}
}

func (m *Model) updateStepSourceSelection(msg tea.KeyMsg) {
	selectedSource := sourceTypes[m.sourceTypeIdx]
	switch selectedSource {
	case "local", "ova":
		// Text input for path.
		key := msg.String()
		switch {
		case key == "backspace":
			if len(m.sourcePath) > 0 {
				m.sourcePath = m.sourcePath[:len(m.sourcePath)-1]
			}
		case len(key) == 1:
			m.sourcePath += key
		}
	case "vsphere", "hyperv":
		// VM picker navigation.
		switch msg.String() {
		case "up", "k":
			if m.sourceVMID > 0 {
				m.sourceVMID--
			}
		case "down", "j":
			if m.sourceVMID < len(m.sourceVMs)-1 {
				m.sourceVMID++
			}
		}
	}
}

func (m *Model) updateStepTarget(msg tea.KeyMsg) {
	switch m.targetFocusIdx {
	case 0:
		// Output directory text input.
		key := msg.String()
		switch {
		case key == "backspace":
			if len(m.outputDir) > 0 {
				m.outputDir = m.outputDir[:len(m.outputDir)-1]
			}
		case len(key) == 1:
			m.outputDir += key
		}
	case 1:
		// Format selector.
		switch msg.String() {
		case "up", "k", "left":
			if m.formatIdx > 0 {
				m.formatIdx--
			}
		case "down", "j", "right":
			if m.formatIdx < len(outputFormats)-1 {
				m.formatIdx++
			}
		}
	case 2:
		// Compression toggle.
		if msg.String() == " " {
			m.compress = !m.compress
		}
	}
}

func (m *Model) updateStepFixes(msg tea.KeyMsg) {
	if msg.String() == " " {
		switch m.fixesFocusIdx {
		case 0:
			m.fixFstab = !m.fixFstab
		case 1:
			m.fixInitramfs = !m.fixInitramfs
		case 2:
			m.fixGrub = !m.fixGrub
		case 3:
			m.fixNetwork = !m.fixNetwork
		}
	}
}

// View renders the wizard.
func (m Model) View() string {
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render("Migration Wizard"))
	b.WriteString("\n")

	// Step progress indicator.
	b.WriteString(m.renderStepIndicator())
	b.WriteString("\n\n")

	// Current step content.
	switch m.step {
	case 0:
		b.WriteString(m.viewStepSourceType())
	case 1:
		b.WriteString(m.viewStepSourceSelection())
	case 2:
		b.WriteString(m.viewStepTarget())
	case 3:
		b.WriteString(m.viewStepFixes())
	case 4:
		b.WriteString(m.viewStepConfirmation())
	}

	b.WriteString("\n\n")

	// Navigation help.
	nav := ui.DimStyle.Render("enter: next  esc: back  tab: cycle fields  space: toggle")
	b.WriteString(nav)

	return b.String()
}

func (m Model) renderStepIndicator() string {
	var parts []string
	for i, title := range stepTitles {
		label := fmt.Sprintf("%d. %s", i+1, title)
		if i == m.step {
			parts = append(parts, ui.SelectedStyle.Render(label))
		} else if i < m.step {
			parts = append(parts, ui.SuccessStyle.Render(label))
		} else {
			parts = append(parts, ui.DimStyle.Render(label))
		}
	}
	return strings.Join(parts, ui.DimStyle.Render(" > "))
}

func (m Model) viewStepSourceType() string {
	header := ui.SubtitleStyle.Render("Select Source Type")

	var items []string
	for i, st := range sourceTypes {
		cursor := "  "
		style := ui.ValueStyle
		if i == m.sourceTypeIdx {
			cursor = "> "
			style = ui.SelectedStyle
		}
		items = append(items, style.Render(cursor+st))
	}

	content := header + "\n\n" + strings.Join(items, "\n")

	panelWidth := 40
	if m.width > 0 && m.width < panelWidth+6 {
		panelWidth = m.width - 6
	}
	return ui.PanelStyle.Width(panelWidth).Render(content)
}

func (m Model) viewStepSourceSelection() string {
	selectedSource := sourceTypes[m.sourceTypeIdx]

	switch selectedSource {
	case "local", "ova":
		header := ui.SubtitleStyle.Render("Enter Source Path")

		inputStyle := lipgloss.NewStyle().
			Border(lipgloss.NormalBorder()).
			BorderForeground(ui.Green).
			Padding(0, 1).
			Width(50)

		display := m.sourcePath + "█"
		input := inputStyle.Render(display)

		hint := ui.DimStyle.Render("Type the path to the disk image or OVA file")

		content := header + "\n\n" + input + "\n" + hint

		panelWidth := 60
		if m.width > 0 && m.width < panelWidth+6 {
			panelWidth = m.width - 6
		}
		return ui.PanelStyle.Width(panelWidth).Render(content)

	case "vsphere", "hyperv":
		header := ui.SubtitleStyle.Render("Select VM")

		if len(m.sourceVMs) == 0 {
			hint := ui.DimStyle.Render("No VMs available. Connect to vSphere/Hyper-V first.")
			content := header + "\n\n" + hint

			panelWidth := 50
			if m.width > 0 && m.width < panelWidth+6 {
				panelWidth = m.width - 6
			}
			return ui.PanelStyle.Width(panelWidth).Render(content)
		}

		var items []string
		for i, vm := range m.sourceVMs {
			cursor := "  "
			style := ui.ValueStyle
			if i == m.sourceVMID {
				cursor = "> "
				style = ui.SelectedStyle
			}
			items = append(items, style.Render(cursor+vm))
		}

		content := header + "\n\n" + strings.Join(items, "\n")

		panelWidth := 50
		if m.width > 0 && m.width < panelWidth+6 {
			panelWidth = m.width - 6
		}
		return ui.PanelStyle.Width(panelWidth).Render(content)

	default:
		return ui.DimStyle.Render("Unknown source type")
	}
}

func (m Model) viewStepTarget() string {
	header := ui.SubtitleStyle.Render("Target Configuration")

	// Output directory field.
	dirLabel := ui.LabelStyle.Render("Output Directory:")
	dirFocus := ""
	if m.targetFocusIdx == 0 {
		dirFocus = ui.SelectedStyle.Render("> ")
	} else {
		dirFocus = "  "
	}

	inputStyle := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(ui.Dim).
		Padding(0, 1)
	if m.targetFocusIdx == 0 {
		inputStyle = inputStyle.BorderForeground(ui.Green)
	}
	dirInput := inputStyle.Render(m.outputDir + "█")

	// Format selector.
	fmtLabel := ui.LabelStyle.Render("Output Format:")
	fmtFocus := ""
	if m.targetFocusIdx == 1 {
		fmtFocus = ui.SelectedStyle.Render("> ")
	} else {
		fmtFocus = "  "
	}
	var fmtParts []string
	for i, f := range outputFormats {
		if i == m.formatIdx {
			fmtParts = append(fmtParts, ui.SelectedStyle.Render("["+f+"]"))
		} else {
			fmtParts = append(fmtParts, ui.DimStyle.Render(" "+f+" "))
		}
	}
	fmtSelector := strings.Join(fmtParts, " ")

	// Compression toggle.
	compLabel := ui.LabelStyle.Render("Compression:")
	compFocus := ""
	if m.targetFocusIdx == 2 {
		compFocus = ui.SelectedStyle.Render("> ")
	} else {
		compFocus = "  "
	}
	compToggle := ui.RenderToggle(m.compress)

	content := header + "\n\n" +
		dirFocus + dirLabel + "\n" +
		"  " + dirInput + "\n\n" +
		fmtFocus + fmtLabel + " " + fmtSelector + "\n\n" +
		compFocus + compLabel + " " + compToggle

	panelWidth := 60
	if m.width > 0 && m.width < panelWidth+6 {
		panelWidth = m.width - 6
	}
	return ui.PanelStyle.Width(panelWidth).Render(content)
}

func (m Model) viewStepFixes() string {
	header := ui.SubtitleStyle.Render("Offline Fixes")

	type toggle struct {
		label string
		on    bool
	}
	toggles := []toggle{
		{"Fix fstab", m.fixFstab},
		{"Regenerate initramfs", m.fixInitramfs},
		{"Update GRUB", m.fixGrub},
		{"Fix network config", m.fixNetwork},
	}

	var items []string
	for i, t := range toggles {
		cursor := "  "
		style := ui.ValueStyle
		if i == m.fixesFocusIdx {
			cursor = "> "
			style = ui.SelectedStyle
		}
		indicator := ui.RenderToggle(t.on)
		items = append(items, style.Render(cursor+t.label+": ")+indicator)
	}

	hint := ui.DimStyle.Render("Press space to toggle")

	content := header + "\n\n" + strings.Join(items, "\n") + "\n\n" + hint

	panelWidth := 50
	if m.width > 0 && m.width < panelWidth+6 {
		panelWidth = m.width - 6
	}
	return ui.PanelStyle.Width(panelWidth).Render(content)
}

func (m Model) viewStepConfirmation() string {
	header := ui.SubtitleStyle.Render("Confirm Migration")

	selectedSource := sourceTypes[m.sourceTypeIdx]
	selectedFormat := outputFormats[m.formatIdx]

	var sourceName string
	switch selectedSource {
	case "local", "ova":
		sourceName = m.sourcePath
	case "vsphere", "hyperv":
		if m.sourceVMID < len(m.sourceVMs) {
			sourceName = m.sourceVMs[m.sourceVMID]
		} else {
			sourceName = "(none selected)"
		}
	}

	rows := []string{
		fmt.Sprintf("  %s %s", ui.LabelStyle.Render("Source Type:"), ui.ValueStyle.Render(selectedSource)),
		fmt.Sprintf("  %s %s", ui.LabelStyle.Render("Source:"), ui.ValueStyle.Render(sourceName)),
		fmt.Sprintf("  %s %s", ui.LabelStyle.Render("Output Dir:"), ui.ValueStyle.Render(m.outputDir)),
		fmt.Sprintf("  %s %s", ui.LabelStyle.Render("Format:"), ui.ValueStyle.Render(selectedFormat)),
		fmt.Sprintf("  %s %s", ui.LabelStyle.Render("Compression:"), ui.RenderToggle(m.compress)),
		"",
		ui.LabelStyle.Render("  Offline Fixes:"),
		fmt.Sprintf("    Fix fstab:          %s", ui.RenderToggle(m.fixFstab)),
		fmt.Sprintf("    Regen initramfs:    %s", ui.RenderToggle(m.fixInitramfs)),
		fmt.Sprintf("    Update GRUB:        %s", ui.RenderToggle(m.fixGrub)),
		fmt.Sprintf("    Fix network:        %s", ui.RenderToggle(m.fixNetwork)),
	}

	startHint := "\n" + ui.SuccessStyle.Render("  Press Enter to start migration")

	content := header + "\n\n" + strings.Join(rows, "\n") + startHint

	panelWidth := 60
	if m.width > 0 && m.width < panelWidth+6 {
		panelWidth = m.width - 6
	}
	return ui.PanelStyle.Width(panelWidth).Render(content)
}
