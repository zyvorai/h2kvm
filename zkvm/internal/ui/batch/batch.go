// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package batch

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/models"
	"github.com/h2kvm/zkvm/internal/state"
	"github.com/h2kvm/zkvm/internal/ui"
)

// BatchItem represents a VM queued for batch migration.
type BatchItem struct {
	VMName      string
	SourceType  string
	SourcePath  string
	Status      string // "queued", "running", "done", "failed"
	Progress    float64
	MigrationID string // Set when migration is started via backend
}

// focusArea tracks which UI section has focus.
type focusArea int

const (
	focusList focusArea = iota
	focusControls
	focusBrowser
)

// Model is the batch migration manager tab.
type Model struct {
	store  *state.Store
	width  int
	height int

	items    []BatchItem
	selected int
	focus    focusArea

	// Common configuration for all items.
	outputDir    string
	outputFormat string
	compress     bool

	// Control button focus.
	controlIdx int

	// File browser state.
	browserActive  bool
	browserCwd     string
	browserEntries []fileEntry
	browserCursor  int
	browserOffset  int
}

type fileEntry struct {
	name  string
	isDir bool
	size  int64
}

// controlLabels are the available batch control actions.
var controlLabels = []string{"Add VM", "Start All", "Pause All", "Cancel All", "Remove Selected"}

// Supported disk image extensions for batch Add VM.
var diskExtensions = map[string]string{
	".vmdk": "vmdk",
	".ova":  "ova",
	".ovf":  "ovf",
	".vhd":  "vhd",
	".vhdx": "vhd",
	".raw":  "raw",
	".img":  "raw",
	".qcow2": "qcow2",
}

// New creates a new batch model.
func New(store *state.Store) Model {
	cfg := store.GetConfig()
	return Model{
		store:        store,
		outputDir:    cfg.General.OutputDir,
		outputFormat: cfg.Migration.DefaultFormat,
		compress:     cfg.Migration.EnableCompression,
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Batch"
}

// Init initializes the batch manager.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the batch tab.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		// File browser handles keys when active.
		if m.browserActive {
			return m.handleBrowserKey(msg)
		}

		switch msg.String() {
		case "tab":
			if m.focus == focusList {
				m.focus = focusControls
			} else {
				m.focus = focusList
			}

		case "up", "k":
			if m.focus == focusList {
				if m.selected > 0 {
					m.selected--
				}
			}
		case "down", "j":
			if m.focus == focusList {
				if m.selected < len(m.items)-1 {
					m.selected++
				}
			}

		case "left", "h":
			if m.focus == focusControls {
				if m.controlIdx > 0 {
					m.controlIdx--
				}
			}
		case "right", "l":
			if m.focus == focusControls {
				if m.controlIdx < len(controlLabels)-1 {
					m.controlIdx++
				}
			}

		case "enter":
			if m.focus == focusControls {
				return m.executeControl()
			}

		case "d", "delete":
			m.removeSelected()
		}
	}
	return m, nil
}

func (m Model) executeControl() (tea.Model, tea.Cmd) {
	switch m.controlIdx {
	case 0:
		// Add VM — open file browser.
		m.openBrowser()
		return m, nil

	case 1:
		// Start All — send to backend via parent message.
		var startItems []models.BatchStartItem
		for i := range m.items {
			if m.items[i].Status == "queued" {
				m.items[i].Status = "running"
				startItems = append(startItems, models.BatchStartItem{
					VMName:     m.items[i].VMName,
					SourceType: m.items[i].SourceType,
					SourcePath: m.items[i].SourcePath,
				})
			}
		}
		if len(startItems) > 0 {
			items := startItems
			return m, func() tea.Msg { return models.BatchStartAllMsg{Items: items} }
		}

	case 2:
		// Pause All.
		for i := range m.items {
			if m.items[i].Status == "running" {
				m.items[i].Status = "queued"
			}
		}

	case 3:
		// Cancel All.
		var ids []string
		for i := range m.items {
			if m.items[i].MigrationID != "" && m.items[i].Status == "running" {
				ids = append(ids, m.items[i].MigrationID)
			}
			m.items[i].Status = "queued"
			m.items[i].Progress = 0
		}
		if len(ids) > 0 {
			cancelIDs := ids
			return m, func() tea.Msg { return models.BatchCancelAllMsg{IDs: cancelIDs} }
		}

	case 4:
		// Remove Selected.
		m.removeSelected()
	}
	return m, nil
}

func (m *Model) removeSelected() {
	if m.selected >= 0 && m.selected < len(m.items) {
		m.items = append(m.items[:m.selected], m.items[m.selected+1:]...)
		if m.selected >= len(m.items) && m.selected > 0 {
			m.selected--
		}
	}
}

// AddItem appends an item to the batch queue if not already present.
func (m *Model) AddItem(item BatchItem) {
	for _, existing := range m.items {
		if existing.SourcePath == item.SourcePath {
			return // Already queued
		}
	}
	item.Status = "queued"
	m.items = append(m.items, item)
}

// ---------------------------------------------------------------------------
// File browser for Add VM
// ---------------------------------------------------------------------------

func (m *Model) openBrowser() {
	cwd, err := os.Getwd()
	if err != nil {
		cwd = "/"
	}
	m.browserCwd = cwd
	m.browserCursor = 0
	m.browserOffset = 0
	m.browserActive = true
	m.focus = focusBrowser
	m.readBrowserDir()
}

func (m *Model) readBrowserDir() {
	entries, err := os.ReadDir(m.browserCwd)
	if err != nil {
		m.browserEntries = nil
		return
	}

	var result []fileEntry
	// Parent directory entry.
	if m.browserCwd != "/" {
		result = append(result, fileEntry{name: "..", isDir: true})
	}

	var dirs, files []fileEntry
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, ".") {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		fe := fileEntry{name: name, isDir: e.IsDir(), size: info.Size()}
		if e.IsDir() {
			dirs = append(dirs, fe)
		} else {
			ext := strings.ToLower(filepath.Ext(name))
			if _, ok := diskExtensions[ext]; ok {
				files = append(files, fe)
			}
		}
	}

	sort.Slice(dirs, func(i, j int) bool { return dirs[i].name < dirs[j].name })
	sort.Slice(files, func(i, j int) bool { return files[i].name < files[j].name })
	result = append(result, dirs...)
	result = append(result, files...)
	m.browserEntries = result
	m.browserCursor = 0
	m.browserOffset = 0
}

func (m Model) handleBrowserKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	maxVisible := 15
	key := msg.String()

	switch key {
	case "esc", "q":
		m.browserActive = false
		m.focus = focusControls
		return m, nil

	case "up", "k":
		if m.browserCursor > 0 {
			m.browserCursor--
			if m.browserCursor < m.browserOffset {
				m.browserOffset = m.browserCursor
			}
		}

	case "down", "j":
		if m.browserCursor < len(m.browserEntries)-1 {
			m.browserCursor++
			if m.browserCursor >= m.browserOffset+maxVisible {
				m.browserOffset = m.browserCursor - maxVisible + 1
			}
		}

	case "enter":
		if m.browserCursor >= 0 && m.browserCursor < len(m.browserEntries) {
			entry := m.browserEntries[m.browserCursor]
			if entry.isDir {
				if entry.name == ".." {
					m.browserCwd = filepath.Dir(m.browserCwd)
				} else {
					m.browserCwd = filepath.Join(m.browserCwd, entry.name)
				}
				m.readBrowserDir()
			} else {
				// File selected — add to batch queue.
				fullPath := filepath.Join(m.browserCwd, entry.name)
				ext := strings.ToLower(filepath.Ext(entry.name))
				srcType := diskExtensions[ext]
				if srcType == "" {
					srcType = "raw"
				}
				vmName := strings.TrimSuffix(entry.name, filepath.Ext(entry.name))
				m.AddItem(BatchItem{
					VMName:     vmName,
					SourceType: srcType,
					SourcePath: fullPath,
				})
				m.browserActive = false
				m.focus = focusList
			}
		}

	case "backspace":
		m.browserCwd = filepath.Dir(m.browserCwd)
		m.readBrowserDir()
	}

	return m, nil
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

// View renders the batch tab.
func (m Model) View() string {
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render("Batch Migration Manager"))
	b.WriteString("\n")

	// Common config summary.
	b.WriteString(m.renderConfig())
	b.WriteString("\n\n")

	// Batch progress overview.
	b.WriteString(m.renderProgress())
	b.WriteString("\n\n")

	// File browser overlay or item list.
	if m.browserActive {
		b.WriteString(m.renderBrowser())
	} else {
		b.WriteString(m.renderItemList())
	}
	b.WriteString("\n\n")

	// Control buttons.
	b.WriteString(m.renderControls())
	b.WriteString("\n\n")

	helpLine := ui.DimStyle.Render("tab: switch focus  j/k: navigate list  h/l: navigate controls  enter: activate  d: remove")
	b.WriteString(helpLine)

	return b.String()
}

func (m Model) renderConfig() string {
	header := ui.SubtitleStyle.Render("Common Configuration")

	rows := []string{
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Output Dir:"),
			ui.ValueStyle.Render(m.outputDir)),
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Format:"),
			ui.ValueStyle.Render(m.outputFormat)),
		fmt.Sprintf("  %s %s",
			ui.LabelStyle.Render("Compression:"),
			ui.RenderToggle(m.compress)),
	}

	content := header + "\n" + strings.Join(rows, "\n")
	return ui.PanelStyle.Render(content)
}

func (m Model) renderProgress() string {
	total := len(m.items)
	var queued, running, done, failed int
	for _, item := range m.items {
		switch item.Status {
		case "queued":
			queued++
		case "running":
			running++
		case "done":
			done++
		case "failed":
			failed++
		}
	}

	var pct float64
	if total > 0 {
		pct = float64(done) / float64(total) * 100
	}

	bar := ui.RenderProgressBar(pct, 30)

	summary := fmt.Sprintf("Total: %d  |  Queued: %d  |  %s: %d  |  %s: %d  |  %s: %d",
		total,
		queued,
		ui.SuccessStyle.Render("Running"), running,
		ui.SuccessStyle.Render("Done"), done,
		ui.ErrorStyle.Render("Failed"), failed,
	)

	return summary + "\n" + bar
}

func (m Model) renderBrowser() string {
	panelStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ui.Cyan).
		Padding(0, 1)

	header := ui.SubtitleStyle.Render("Select Disk Image")
	pathLine := ui.DimStyle.Render(m.browserCwd)

	maxVisible := 15
	if len(m.browserEntries) == 0 {
		content := header + "\n" + pathLine + "\n" + ui.DimStyle.Render("  No disk images found")
		return panelStyle.Render(content)
	}

	var rows []string
	end := m.browserOffset + maxVisible
	if end > len(m.browserEntries) {
		end = len(m.browserEntries)
	}
	for i := m.browserOffset; i < end; i++ {
		entry := m.browserEntries[i]
		cursor := "  "
		if i == m.browserCursor {
			cursor = "> "
		}
		if entry.isDir {
			name := entry.name + "/"
			style := lipgloss.NewStyle().Foreground(ui.Cyan)
			if i == m.browserCursor {
				style = ui.SelectedStyle
			}
			rows = append(rows, style.Render(cursor+name))
		} else {
			name := entry.name
			sizeStr := fmtSize(entry.size)
			style := lipgloss.NewStyle()
			if i == m.browserCursor {
				style = ui.SelectedStyle
			}
			rows = append(rows, style.Render(fmt.Sprintf("%s%-30s %8s", cursor, name, sizeStr)))
		}
	}

	help := ui.DimStyle.Render("enter: select/open  backspace: parent  esc: cancel")
	content := header + "\n" + pathLine + "\n\n" + strings.Join(rows, "\n") + "\n\n" + help
	return panelStyle.Render(content)
}

func (m Model) renderItemList() string {
	listStyle := lipgloss.NewStyle()
	if m.focus == focusList {
		listStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ui.Green).
			Padding(0, 1)
	} else {
		listStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ui.Dim).
			Padding(0, 1)
	}

	header := ui.SubtitleStyle.Render("Queued VMs")

	if len(m.items) == 0 {
		content := header + "\n" + ui.DimStyle.Render("  No VMs in batch queue. Press Add VM to begin.")
		return listStyle.Render(content)
	}

	colWidths := []int{20, 10, 10, 10}
	headers := []string{"VM Name", "Source", "Status", "Progress"}
	headerLine := renderRow(headers, colWidths, ui.TableHeaderStyle)

	var rows []string
	for i, item := range m.items {
		rowStyle := lipgloss.NewStyle()
		if i == m.selected && m.focus == focusList {
			rowStyle = ui.SelectedStyle
		}

		statusText := item.Status
		switch item.Status {
		case "running":
			statusText = ui.SuccessStyle.Render("Running")
		case "done":
			statusText = ui.SuccessStyle.Render("Done")
		case "failed":
			statusText = ui.ErrorStyle.Render("Failed")
		case "queued":
			statusText = ui.DimStyle.Render("Queued")
		}

		progress := fmt.Sprintf("%.0f%%", item.Progress)
		if item.Status == "running" {
			progress += " " + ui.RenderProgressBar(item.Progress, 6)
		}

		cols := []string{
			truncate(item.VMName, colWidths[0]),
			truncate(item.SourceType, colWidths[1]),
			statusText,
			progress,
		}

		rows = append(rows, renderRow(cols, colWidths, rowStyle))
	}

	content := header + "\n" + headerLine + "\n" + strings.Join(rows, "\n")
	return listStyle.Render(content)
}

func (m Model) renderControls() string {
	var buttons []string
	for i, label := range controlLabels {
		btnStyle := lipgloss.NewStyle().
			Padding(0, 2).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ui.Dim)

		if m.focus == focusControls && i == m.controlIdx {
			btnStyle = btnStyle.
				Bold(true).
				Foreground(ui.Green).
				BorderForeground(ui.Green)
		}

		buttons = append(buttons, btnStyle.Render(label))
	}

	return lipgloss.JoinHorizontal(lipgloss.Top, buttons...)
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

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	if maxLen < 4 {
		return s[:maxLen]
	}
	return s[:maxLen-3] + "..."
}

func fmtSize(b int64) string {
	switch {
	case b >= 1<<30:
		return fmt.Sprintf("%.1fG", float64(b)/float64(1<<30))
	case b >= 1<<20:
		return fmt.Sprintf("%.1fM", float64(b)/float64(1<<20))
	case b >= 1<<10:
		return fmt.Sprintf("%.1fK", float64(b)/float64(1<<10))
	default:
		return fmt.Sprintf("%dB", b)
	}
}
