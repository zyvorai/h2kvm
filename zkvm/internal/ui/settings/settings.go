// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package settings

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/models"
	"github.com/hyper2kvm/zkvm/internal/state"
	"github.com/hyper2kvm/zkvm/internal/ui"
)

// category represents one settings section.
type category int

const (
	catGeneral     category = iota
	catMigration
	catVSphere
	catOfflineFixes
	catPerformance
	catAdvanced
	catCount // sentinel
)

var categoryNames = []string{
	"General",
	"Migration",
	"vSphere",
	"Offline Fixes",
	"Performance",
	"Advanced",
}

// focusPane tracks which panel has focus.
type focusPane int

const (
	focusCategories focusPane = iota
	focusFields
)

// field holds the metadata for one editable setting.
type field struct {
	label    string
	kind     string // "text", "toggle", "select"
	options  []string
	getValue func(models.TUIConfig) string
	getBool  func(models.TUIConfig) bool
	getIdx   func(models.TUIConfig) int
}

// Model is the settings editor tab.
type Model struct {
	store  *state.Store
	width  int
	height int

	focus    focusPane
	catIdx   int
	fieldIdx int

	// Editing state -- a mutable copy of the config.
	config models.TUIConfig

	// Cached field definitions per category.
	fields [int(catCount)][]field

	// Text editing buffer for the currently focused text field.
	editBuf string
	editing bool
}

// New creates a new settings model.
// Auto-populates vSphere fields from GOVC_* and VC_* environment variables.
func New(store *state.Store) Model {
	m := Model{
		store:  store,
		config: store.GetConfig(),
	}
	m.loadFromEnv()
	m.buildFields()
	return m
}

// loadFromEnv populates vSphere config from GOVC_* and VC_* environment variables.
func (m *Model) loadFromEnv() {
	// GOVC_URL → vCenter host (strip https:// and /sdk)
	if url := os.Getenv("GOVC_URL"); url != "" && m.config.VSphere.VCenterHost == "" {
		host := url
		host = strings.TrimPrefix(host, "https://")
		host = strings.TrimPrefix(host, "http://")
		host = strings.TrimSuffix(host, "/sdk")
		host = strings.TrimSuffix(host, "/")
		m.config.VSphere.VCenterHost = host
	}

	if user := os.Getenv("GOVC_USERNAME"); user != "" && m.config.VSphere.Username == "" {
		m.config.VSphere.Username = user
	}

	if pass := os.Getenv("GOVC_PASSWORD"); pass != "" && m.config.VSphere.Password == "" {
		m.config.VSphere.Password = pass
	} else if pass := os.Getenv("VC_PASSWORD"); pass != "" && m.config.VSphere.Password == "" {
		m.config.VSphere.Password = pass
	}

	if dc := os.Getenv("GOVC_DATACENTER"); dc != "" && m.config.VSphere.Datacenter == "" {
		m.config.VSphere.Datacenter = dc
	}

	if os.Getenv("GOVC_INSECURE") == "1" {
		m.config.VSphere.Insecure = true
	}
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Settings"
}

func (m *Model) buildFields() {
	// General
	m.fields[catGeneral] = []field{
		{label: "Output Directory", kind: "text",
			getValue: func(c models.TUIConfig) string { return c.General.OutputDir }},
		{label: "Log Level", kind: "select", options: []string{"debug", "info", "warning", "error"},
			getValue: func(c models.TUIConfig) string { return c.General.LogLevel }},
		{label: "Log to File", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.General.LogToFile }},
		{label: "Log File Path", kind: "text",
			getValue: func(c models.TUIConfig) string { return c.General.LogFilePath }},
	}

	// Migration
	m.fields[catMigration] = []field{
		{label: "Default Format", kind: "select", options: []string{"qcow2", "raw", "vmdk"},
			getValue: func(c models.TUIConfig) string { return c.Migration.DefaultFormat }},
		{label: "Compression", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.Migration.EnableCompression }},
		{label: "Parallel Migrations", kind: "text",
			getValue: func(c models.TUIConfig) string {
				return strconv.Itoa(c.Migration.ParallelMigrations)
			}},
		{label: "Skip Existing", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.Migration.SkipExisting }},
	}

	// vSphere
	m.fields[catVSphere] = []field{
		{label: "vCenter Host", kind: "text",
			getValue: func(c models.TUIConfig) string { return c.VSphere.VCenterHost }},
		{label: "Username", kind: "text",
			getValue: func(c models.TUIConfig) string { return c.VSphere.Username }},
		{label: "Password", kind: "password",
			getValue: func(c models.TUIConfig) string { return c.VSphere.Password }},
		{label: "Password Env Var", kind: "text",
			getValue: func(c models.TUIConfig) string { return c.VSphere.PasswordEnv }},
		{label: "Datacenter", kind: "text",
			getValue: func(c models.TUIConfig) string { return c.VSphere.Datacenter }},
		{label: "Insecure (skip TLS)", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.VSphere.Insecure }},
		{label: "Save Credentials", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.VSphere.SaveCredentials }},
		{label: "Verify SSL", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.VSphere.VerifySSL }},
	}

	// Offline Fixes
	m.fields[catOfflineFixes] = []field{
		{label: "Fstab Mode", kind: "select", options: []string{"stabilize-all", "stabilize-boot", "none"},
			getValue: func(c models.TUIConfig) string { return c.OfflineFixes.FstabMode }},
		{label: "Regen Initramfs", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.OfflineFixes.RegenInitramfs }},
		{label: "Update GRUB", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.OfflineFixes.UpdateGrub }},
		{label: "Fix Network", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.OfflineFixes.FixNetwork }},
		{label: "Enhanced Chroot", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.OfflineFixes.EnhancedChroot }},
	}

	// Performance
	m.fields[catPerformance] = []field{
		{label: "Max Concurrent Ops", kind: "text",
			getValue: func(c models.TUIConfig) string {
				return strconv.Itoa(c.Performance.MaxConcurrentOps)
			}},
		{label: "Operation Timeout (s)", kind: "text",
			getValue: func(c models.TUIConfig) string {
				return strconv.Itoa(c.Performance.OperationTimeout)
			}},
		{label: "Network Timeout (s)", kind: "text",
			getValue: func(c models.TUIConfig) string {
				return strconv.Itoa(c.Performance.NetworkTimeout)
			}},
	}

	// Advanced
	m.fields[catAdvanced] = []field{
		{label: "GuestFS Backend", kind: "select", options: []string{"vmcraft", "libguestfs", "direct"},
			getValue: func(c models.TUIConfig) string { return c.Advanced.GuestfsBackend }},
		{label: "Debug Mode", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.Advanced.DebugMode }},
		{label: "Verbose Output", kind: "toggle",
			getBool: func(c models.TUIConfig) bool { return c.Advanced.VerboseOutput }},
	}
}

// Init initializes the settings tab.
func (m Model) Init() tea.Cmd {
	return nil
}

// Update handles messages for the settings tab.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		switch msg.String() {
		case "tab":
			if m.focus == focusCategories {
				m.focus = focusFields
				m.fieldIdx = 0
			} else {
				m.focus = focusCategories
			}
			m.editing = false
			return m, nil

		case "esc":
			if m.editing {
				m.applyTextEdit()
				m.editing = false
				m.saveConfig()
				return m, nil
			}
			if m.focus == focusFields {
				m.focus = focusCategories
				return m, nil
			}
		}

		if m.focus == focusCategories {
			m.updateCategoryNav(msg)
		} else {
			m.updateFieldEdit(msg)
		}
	}
	return m, nil
}

func (m *Model) updateCategoryNav(msg tea.KeyMsg) {
	switch msg.String() {
	case "up", "k":
		if m.catIdx > 0 {
			m.catIdx--
			m.fieldIdx = 0
		}
	case "down", "j":
		if m.catIdx < int(catCount)-1 {
			m.catIdx++
			m.fieldIdx = 0
		}
	case "enter":
		m.focus = focusFields
		m.fieldIdx = 0
	}
}

func (m *Model) updateFieldEdit(msg tea.KeyMsg) {
	fields := m.fields[m.catIdx]
	if len(fields) == 0 {
		return
	}

	f := fields[m.fieldIdx]

	if m.editing && (f.kind == "text" || f.kind == "password") {
		key := msg.String()
		switch {
		case key == "enter":
			m.applyTextEdit()
			m.editing = false
			m.saveConfig()
		case key == "backspace":
			if len(m.editBuf) > 0 {
				m.editBuf = m.editBuf[:len(m.editBuf)-1]
			}
		case len(key) == 1:
			m.editBuf += key
		}
		return
	}

	switch msg.String() {
	case "up", "k":
		if m.fieldIdx > 0 {
			m.fieldIdx--
		}
	case "down", "j":
		if m.fieldIdx < len(fields)-1 {
			m.fieldIdx++
		}

	case "enter":
		switch f.kind {
		case "text":
			m.editBuf = f.getValue(m.config)
			m.editing = true
		case "toggle":
			m.toggleField()
			m.saveConfig()
		}

	case " ":
		if f.kind == "toggle" {
			m.toggleField()
			m.saveConfig()
		}

	case "left", "h":
		if f.kind == "select" {
			m.cycleSelect(-1)
			m.saveConfig()
		}
	case "right", "l":
		if f.kind == "select" {
			m.cycleSelect(1)
			m.saveConfig()
		}
	}
}

func (m *Model) toggleField() {
	cat := category(m.catIdx)
	switch cat {
	case catGeneral:
		switch m.fieldIdx {
		case 2:
			m.config.General.LogToFile = !m.config.General.LogToFile
		}
	case catMigration:
		switch m.fieldIdx {
		case 1:
			m.config.Migration.EnableCompression = !m.config.Migration.EnableCompression
		case 3:
			m.config.Migration.SkipExisting = !m.config.Migration.SkipExisting
		}
	case catVSphere:
		switch m.fieldIdx {
		case 5: // Insecure (skip TLS)
			m.config.VSphere.Insecure = !m.config.VSphere.Insecure
		case 6: // Save Credentials
			m.config.VSphere.SaveCredentials = !m.config.VSphere.SaveCredentials
		case 7: // Verify SSL
			m.config.VSphere.VerifySSL = !m.config.VSphere.VerifySSL
		}
	case catOfflineFixes:
		switch m.fieldIdx {
		case 1:
			m.config.OfflineFixes.RegenInitramfs = !m.config.OfflineFixes.RegenInitramfs
		case 2:
			m.config.OfflineFixes.UpdateGrub = !m.config.OfflineFixes.UpdateGrub
		case 3:
			m.config.OfflineFixes.FixNetwork = !m.config.OfflineFixes.FixNetwork
		case 4:
			m.config.OfflineFixes.EnhancedChroot = !m.config.OfflineFixes.EnhancedChroot
		}
	case catAdvanced:
		switch m.fieldIdx {
		case 1:
			m.config.Advanced.DebugMode = !m.config.Advanced.DebugMode
		case 2:
			m.config.Advanced.VerboseOutput = !m.config.Advanced.VerboseOutput
		}
	}
}

func (m *Model) cycleSelect(dir int) {
	f := m.fields[m.catIdx][m.fieldIdx]
	if len(f.options) == 0 {
		return
	}

	current := f.getValue(m.config)
	idx := 0
	for i, opt := range f.options {
		if opt == current {
			idx = i
			break
		}
	}

	idx += dir
	if idx < 0 {
		idx = len(f.options) - 1
	} else if idx >= len(f.options) {
		idx = 0
	}

	newVal := f.options[idx]
	m.applySelectValue(newVal)
}

func (m *Model) applySelectValue(val string) {
	cat := category(m.catIdx)
	switch cat {
	case catGeneral:
		if m.fieldIdx == 1 {
			m.config.General.LogLevel = val
		}
	case catMigration:
		if m.fieldIdx == 0 {
			m.config.Migration.DefaultFormat = val
		}
	case catOfflineFixes:
		if m.fieldIdx == 0 {
			m.config.OfflineFixes.FstabMode = val
		}
	case catAdvanced:
		if m.fieldIdx == 0 {
			m.config.Advanced.GuestfsBackend = val
		}
	}
}

func (m *Model) applyTextEdit() {
	cat := category(m.catIdx)
	val := m.editBuf

	switch cat {
	case catGeneral:
		switch m.fieldIdx {
		case 0:
			m.config.General.OutputDir = val
		case 3:
			m.config.General.LogFilePath = val
		}
	case catMigration:
		if m.fieldIdx == 2 {
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				m.config.Migration.ParallelMigrations = n
			}
		}
	case catVSphere:
		switch m.fieldIdx {
		case 0:
			m.config.VSphere.VCenterHost = val
		case 1:
			m.config.VSphere.Username = val
		case 2:
			m.config.VSphere.Password = val
		case 3:
			m.config.VSphere.PasswordEnv = val
		case 4:
			m.config.VSphere.Datacenter = val
		}
	case catPerformance:
		switch m.fieldIdx {
		case 0:
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				m.config.Performance.MaxConcurrentOps = n
			}
		case 1:
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				m.config.Performance.OperationTimeout = n
			}
		case 2:
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				m.config.Performance.NetworkTimeout = n
			}
		}
	}
}

// GetConfig returns the currently edited configuration.
func (m Model) GetConfig() models.TUIConfig {
	return m.config
}

// saveConfig persists the current config to the store and disk.
func (m *Model) saveConfig() {
	m.store.UpdateConfig(m.config)
	_ = m.store.SaveConfigToFile()
}

// View renders the settings tab.
func (m Model) View() string {
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render("Settings"))
	b.WriteString("\n")

	// Two-pane layout: categories on the left, fields on the right.
	leftPanel := m.renderCategories()
	rightPanel := m.renderFields()

	// Join horizontally.
	layout := lipgloss.JoinHorizontal(lipgloss.Top, leftPanel, "  ", rightPanel)
	b.WriteString(layout)

	b.WriteString("\n\n")
	helpLine := ui.DimStyle.Render("tab: switch pane  j/k: navigate  enter: edit  space: toggle  h/l: cycle select  esc: back")
	b.WriteString(helpLine)

	return b.String()
}

func (m Model) renderCategories() string {
	var items []string
	for i, name := range categoryNames {
		cursor := "  "
		style := ui.ValueStyle
		if i == m.catIdx {
			cursor = "> "
			if m.focus == focusCategories {
				style = ui.SelectedStyle
			} else {
				style = lipgloss.NewStyle().Bold(true).Foreground(ui.Green)
			}
		}
		items = append(items, style.Render(cursor+name))
	}

	content := strings.Join(items, "\n")

	panelStyle := ui.PanelStyle
	if m.focus == focusCategories {
		panelStyle = ui.ActivePanelStyle
	}

	return panelStyle.Width(20).Render(content)
}

func (m Model) renderFields() string {
	fields := m.fields[m.catIdx]
	header := ui.SubtitleStyle.Render(categoryNames[m.catIdx])

	if len(fields) == 0 {
		content := header + "\n" + ui.DimStyle.Render("  No settings in this category")
		return ui.PanelStyle.Width(50).Render(content)
	}

	var rows []string
	for i, f := range fields {
		cursor := "  "
		labelStyle := ui.LabelStyle
		if i == m.fieldIdx && m.focus == focusFields {
			cursor = "> "
			labelStyle = ui.SelectedStyle
		}

		label := labelStyle.Render(f.label + ":")
		var value string

		switch f.kind {
		case "text":
			if m.editing && i == m.fieldIdx && m.focus == focusFields {
				inputStyle := lipgloss.NewStyle().
					Border(lipgloss.NormalBorder()).
					BorderForeground(ui.Cyan).
					Padding(0, 1)
				value = inputStyle.Render(m.editBuf + "█")
			} else {
				value = ui.ValueStyle.Render(f.getValue(m.config))
			}

		case "password":
			if m.editing && i == m.fieldIdx && m.focus == focusFields {
				inputStyle := lipgloss.NewStyle().
					Border(lipgloss.NormalBorder()).
					BorderForeground(ui.Cyan).
					Padding(0, 1)
				value = inputStyle.Render(strings.Repeat("•", len(m.editBuf)) + "█")
			} else {
				pw := f.getValue(m.config)
				if pw != "" {
					value = ui.DimStyle.Render(strings.Repeat("•", len(pw)))
				} else {
					value = ui.DimStyle.Render("(not set)")
				}
			}

		case "toggle":
			value = ui.RenderToggle(f.getBool(m.config))

		case "select":
			current := f.getValue(m.config)
			var parts []string
			for _, opt := range f.options {
				if opt == current {
					parts = append(parts, ui.SelectedStyle.Render("["+opt+"]"))
				} else {
					parts = append(parts, ui.DimStyle.Render(" "+opt+" "))
				}
			}
			value = strings.Join(parts, " ")
		}

		row := fmt.Sprintf("%s%s %s", cursor, label, value)
		rows = append(rows, row)
	}

	content := header + "\n\n" + strings.Join(rows, "\n")

	panelStyle := ui.PanelStyle
	if m.focus == focusFields {
		panelStyle = ui.ActivePanelStyle
	}

	panelWidth := 55
	if m.width > 0 && m.width-30 > panelWidth {
		panelWidth = m.width - 30
	}

	return panelStyle.Width(panelWidth).Render(content)
}
