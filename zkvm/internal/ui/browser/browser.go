// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

//
// VM Browser — hypersdk-style interactive VM selection + export.
// Connects to vCenter via govc, lists VMs with details, supports
// search, filter, sort, bulk selection, and export.
package browser

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/hyper2kvm/zkvm/internal/protocol"
	"github.com/hyper2kvm/zkvm/internal/state"
	"github.com/hyper2kvm/zkvm/internal/ui"
)

// ── Phases ──

type phase string

const (
	phaseLoading  phase = "loading"
	phaseSelect   phase = "select"
	phaseDetail   phase = "detail"
	phaseFilter   phase = "filter"
	phaseSearch   phase = "search"
	phaseConfirm  phase = "confirm"
	phaseTemplate phase = "template"
	phasePreview  phase = "preview"
	phaseExport   phase = "export"
	phaseError    phase = "error"
)

// ── VM Item ──

type VMItem struct {
	Name       string
	Path       string
	GuestOS    string
	PowerState string
	NumCPU     int32
	MemoryMB   int32
	StorageMB  int64
	Selected   bool
}

// ── Messages ──

type vmsLoadedMsg struct {
	VMs []VMItem
	Err error
}

// ── Model ──

type Model struct {
	store  *state.Store
	width  int
	height int

	phase       phase
	vms         []VMItem
	cursor      int
	err         error
	message     string

	// Search + filter.
	searchQuery string
	searching   bool
	sortMode    string // name, cpu, memory, storage, power
	filterPower string // "", "on", "off"

	// Stats.
	totalCPU    int32
	totalMemMB  int32
	totalStorMB int64
	poweredOn   int
	poweredOff  int

	// Export.
	templateCursor int
	selectedTmpl   *ExportTemplate
	exportProgress ExportProgress
	exportLogs     []string
	exportResults  []ExportResult
	currentExport  int
	program        *tea.Program
}

// ExportResult tracks per-VM export outcome.
type ExportResult struct {
	VMName   string
	Success  bool
	Duration time.Duration
	Error    string
}

// New creates a new browser model.
func New(store *state.Store) Model {
	return Model{
		store:    store,
		phase:    phaseSelect,
		sortMode: "name",
	}
}

// SetProgram stores the tea.Program reference for async export.
func (m *Model) SetProgram(p *tea.Program) {
	m.program = p
}

// TabTitle returns the display name for this tab.
func (m Model) TabTitle() string {
	return "Browser"
}

// Init initializes the browser.
func (m Model) Init() tea.Cmd {
	return nil
}

// EnsureLoaded loads VMs if not already loaded (called when tab becomes active).
func (m *Model) EnsureLoaded() tea.Cmd {
	if len(m.vms) > 0 || m.phase == phaseLoading {
		return nil // Already loaded or loading
	}
	if os.Getenv("GOVC_URL") != "" {
		m.phase = phaseLoading
		return loadVMsCmd()
	}
	return nil
}

// ── Load VMs via govc ──

func loadVMsCmd() tea.Cmd {
	return func() tea.Msg {
		govcPath, err := exec.LookPath("govc")
		if err != nil {
			return vmsLoadedMsg{Err: fmt.Errorf("govc not found in PATH")}
		}

		// Get VM list with JSON details
		cmd := exec.Command(govcPath, "vm.info", "-json", "*")
		cmd.Env = os.Environ()
		out, err := cmd.Output()
		if err != nil {
			// Fallback: simple list
			return loadVMsSimple()
		}

		return parseVMInfoJSON(out)
	}
}

func loadVMsSimple() tea.Msg {
	govcPath, err := exec.LookPath("govc")
	if err != nil {
		return vmsLoadedMsg{Err: fmt.Errorf("govc not found in PATH")}
	}
	dc := os.Getenv("GOVC_DATACENTER")
	if dc == "" {
		dc = "ha-datacenter"
	}

	cmd := exec.Command(govcPath, "ls", fmt.Sprintf("/%s/vm/", dc))
	cmd.Env = os.Environ()
	out, err := cmd.Output()
	if err != nil {
		return vmsLoadedMsg{Err: fmt.Errorf("govc ls failed: %w", err)}
	}

	var vms []VMItem
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.Split(line, "/")
		name := parts[len(parts)-1]
		if name == "vCLS" || name == "Discovered virtual machine" {
			continue
		}
		vms = append(vms, VMItem{
			Name: name,
			Path: line,
		})
	}

	return vmsLoadedMsg{VMs: vms}
}

func parseVMInfoJSON(data []byte) tea.Msg {
	// Parse govc vm.info -json output
	// Structure: {"virtualMachines": [{...}]}
	type vmJSON struct {
		VirtualMachines []struct {
			Config struct {
				Name          string `json:"name"`
				GuestFullName string `json:"guestFullName"`
				Hardware      struct {
					MemoryMB int32 `json:"memoryMB"`
					NumCPU   int32 `json:"numCPU"`
				} `json:"hardware"`
			} `json:"config"`
			Runtime struct {
				PowerState string `json:"powerState"`
			} `json:"runtime"`
			Summary struct {
				Config struct {
					VmPathName string `json:"vmPathName"`
				} `json:"config"`
				Storage struct {
					Committed int64 `json:"committed"`
				} `json:"storage"`
			} `json:"summary"`
		} `json:"virtualMachines"`
	}

	// Try parsing — if fails, fallback to simple
	var result vmJSON
	if err := json.Unmarshal(data, &result); err != nil {
		return loadVMsSimple()
	}

	var vms []VMItem
	for _, vm := range result.VirtualMachines {
		name := vm.Config.Name
		if name == "" || name == "vCLS" {
			continue
		}
		vms = append(vms, VMItem{
			Name:       name,
			Path:       vm.Summary.Config.VmPathName,
			GuestOS:    vm.Config.GuestFullName,
			PowerState: vm.Runtime.PowerState,
			NumCPU:     vm.Config.Hardware.NumCPU,
			MemoryMB:   vm.Config.Hardware.MemoryMB,
			StorageMB:  vm.Summary.Storage.Committed / (1024 * 1024),
		})
	}

	return vmsLoadedMsg{VMs: vms}
}

// ── Update ──

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case ExportProgressMsg:
		m.exportProgress = msg.Progress
		return m, nil

	case ExportLineMsg:
		m.exportLogs = append(m.exportLogs, msg.Line)
		if len(m.exportLogs) > 200 {
			m.exportLogs = m.exportLogs[len(m.exportLogs)-200:]
		}
		return m, nil

	case ExportDoneMsg:
		result := ExportResult{VMName: msg.VMName, Duration: msg.Duration}
		if msg.Err != nil {
			result.Error = msg.Err.Error()
		} else {
			result.Success = true
		}
		m.exportResults = append(m.exportResults, result)
		m.currentExport++

		// Start next VM export if any
		selected := m.getSelectedVMs()
		if m.currentExport < len(selected) {
			return m, m.exportNextVM(selected[m.currentExport], m.currentExport)
		}
		// All done
		m.phase = phaseSelect
		m.message = fmt.Sprintf("✅ Export complete: %d/%d succeeded", m.countSuccessful(), len(selected))
		return m, nil

	case vmsLoadedMsg:
		if msg.Err != nil {
			m.err = msg.Err
			m.phase = phaseError
		} else {
			m.vms = msg.VMs
			m.phase = phaseSelect
			m.updateStats()
			m.sortVMs()
		}

	case tea.KeyMsg:
		// Auto-load VMs on first key press if env vars are set.
		if len(m.vms) == 0 && m.phase != phaseLoading && m.phase != phaseError {
			if os.Getenv("GOVC_URL") != "" {
				m.phase = phaseLoading
				return m, loadVMsCmd()
			}
		}
		return m.handleKey(msg)
	}
	return m, nil
}

func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	// Search mode — capture text.
	if m.searching {
		switch key {
		case "esc":
			m.searching = false
			m.searchQuery = ""
		case "enter":
			m.searching = false
		case "backspace":
			if len(m.searchQuery) > 0 {
				m.searchQuery = m.searchQuery[:len(m.searchQuery)-1]
			}
		default:
			if len(key) == 1 {
				m.searchQuery += key
			}
		}
		m.cursor = 0
		return m, nil
	}

	// Detail view.
	if m.phase == phaseDetail {
		m.phase = phaseSelect
		return m, nil
	}

	// Template selection.
	if m.phase == phaseTemplate {
		switch key {
		case "esc":
			m.phase = phaseSelect
		case "up", "k":
			if m.templateCursor > 0 {
				m.templateCursor--
			}
		case "down", "j":
			if m.templateCursor < len(ExportTemplates)-1 {
				m.templateCursor++
			}
		case "enter":
			tmpl := ExportTemplates[m.templateCursor]
			m.selectedTmpl = &tmpl
			m.phase = phasePreview
		}
		return m, nil
	}

	// Preview — Enter to run, Esc to cancel.
	if m.phase == phasePreview {
		switch key {
		case "esc":
			m.phase = phaseSelect
		case "enter":
			return m.startExport()
		}
		return m, nil
	}

	// Export in progress — only Esc to cancel.
	if m.phase == phaseExport {
		return m, nil
	}

	// Error view.
	if m.phase == phaseError {
		if key == "r" {
			m.phase = phaseLoading
			m.err = nil
			return m, loadVMsCmd()
		}
		return m, nil
	}

	visible := m.getVisibleVMs()

	switch key {
	// Navigation.
	case "up", "k":
		if m.cursor > 0 {
			m.cursor--
		}
	case "down", "j":
		if m.cursor < len(visible)-1 {
			m.cursor++
		}

	// Selection.
	case " ":
		if m.cursor < len(visible) {
			name := visible[m.cursor].Name
			for i := range m.vms {
				if m.vms[i].Name == name {
					m.vms[i].Selected = !m.vms[i].Selected
					break
				}
			}
		}
	case "a":
		// Select all visible.
		for _, v := range visible {
			for i := range m.vms {
				if m.vms[i].Name == v.Name {
					m.vms[i].Selected = true
				}
			}
		}
	case "n":
		// Deselect all.
		for i := range m.vms {
			m.vms[i].Selected = false
		}

	// Search.
	case "/":
		m.searching = true
		m.searchQuery = ""

	// Sort.
	case "s":
		modes := []string{"name", "cpu", "memory", "storage", "power"}
		for i, mode := range modes {
			if mode == m.sortMode {
				m.sortMode = modes[(i+1)%len(modes)]
				break
			}
		}
		m.sortVMs()

	// Power filter.
	case "f":
		switch m.filterPower {
		case "":
			m.filterPower = "on"
		case "on":
			m.filterPower = "off"
		case "off":
			m.filterPower = ""
		}
		m.cursor = 0

	// Clear filters.
	case "c":
		m.searchQuery = ""
		m.filterPower = ""
		m.cursor = 0

	// Detail view.
	case "d", "i":
		if m.cursor < len(visible) {
			m.phase = phaseDetail
		}

	// Export selected VMs.
	case "enter", "e":
		if m.countSelected() > 0 {
			m.templateCursor = 0
			m.phase = phaseTemplate
		} else if m.cursor < len(visible) {
			m.phase = phaseDetail
		}

	// Load VMs if not loaded yet.
	case "l":
		if len(m.vms) == 0 {
			m.phase = phaseLoading
			return m, loadVMsCmd()
		}

	// Refresh.
	case "r":
		m.phase = phaseLoading
		return m, loadVMsCmd()
	}

	// Clamp cursor.
	if m.cursor >= len(visible) && len(visible) > 0 {
		m.cursor = len(visible) - 1
	}

	return m, nil
}

// ── Helpers ──

func (m *Model) updateStats() {
	m.totalCPU = 0
	m.totalMemMB = 0
	m.totalStorMB = 0
	m.poweredOn = 0
	m.poweredOff = 0

	for _, vm := range m.vms {
		m.totalCPU += vm.NumCPU
		m.totalMemMB += vm.MemoryMB
		m.totalStorMB += vm.StorageMB
		if vm.PowerState == "poweredOn" {
			m.poweredOn++
		} else {
			m.poweredOff++
		}
	}
}

func (m *Model) sortVMs() {
	sort.SliceStable(m.vms, func(i, j int) bool {
		switch m.sortMode {
		case "cpu":
			return m.vms[i].NumCPU > m.vms[j].NumCPU
		case "memory":
			return m.vms[i].MemoryMB > m.vms[j].MemoryMB
		case "storage":
			return m.vms[i].StorageMB > m.vms[j].StorageMB
		case "power":
			return m.vms[i].PowerState < m.vms[j].PowerState
		default:
			return strings.ToLower(m.vms[i].Name) < strings.ToLower(m.vms[j].Name)
		}
	})
}

func (m Model) getVisibleVMs() []VMItem {
	var visible []VMItem
	for _, vm := range m.vms {
		// Power filter.
		if m.filterPower == "on" && vm.PowerState != "poweredOn" {
			continue
		}
		if m.filterPower == "off" && vm.PowerState == "poweredOn" {
			continue
		}
		// Search filter.
		if m.searchQuery != "" {
			if !strings.Contains(strings.ToLower(vm.Name), strings.ToLower(m.searchQuery)) &&
				!strings.Contains(strings.ToLower(vm.GuestOS), strings.ToLower(m.searchQuery)) {
				continue
			}
		}
		visible = append(visible, vm)
	}
	return visible
}

func (m Model) countSelected() int {
	count := 0
	for _, vm := range m.vms {
		if vm.Selected {
			count++
		}
	}
	return count
}

func (m Model) getSelectedVMs() []VMItem {
	var selected []VMItem
	for _, vm := range m.vms {
		if vm.Selected {
			selected = append(selected, vm)
		}
	}
	return selected
}

func (m Model) countSuccessful() int {
	count := 0
	for _, r := range m.exportResults {
		if r.Success {
			count++
		}
	}
	return count
}

func (m Model) startExport() (tea.Model, tea.Cmd) {
	selected := m.getSelectedVMs()
	if len(selected) == 0 || m.selectedTmpl == nil {
		return m, nil
	}
	m.phase = phaseExport
	m.currentExport = 0
	m.exportResults = nil
	m.exportLogs = nil
	m.exportProgress = ExportProgress{
		Phase:     "export",
		CurrentVM: selected[0].Name,
		VMsTotal:  len(selected),
		StartTime: time.Now(),
	}
	return m, m.exportNextVM(selected[0], 0)
}

func (m Model) exportNextVM(vm VMItem, index int) tea.Cmd {
	binary := findH2kvmctl()
	outputDir := "./output-" + vm.Name
	args := BuildExportCommand(vm, *m.selectedTmpl, outputDir)
	return RunExportCmd(binary, args, vm.Name, index, m.program)
}

func findH2kvmctl() string {
	if _, err := os.Stat("./h2kvmctl"); err == nil {
		return "./h2kvmctl"
	}
	if _, err := os.Stat("../h2kvmctl"); err == nil {
		return "../h2kvmctl"
	}
	if p, err := exec.LookPath("h2kvmctl"); err == nil {
		return p
	}
	return "h2kvmctl"
}

// SetVMs updates the VM list (for compatibility with parent).
func (m *Model) SetVMs(vms []protocol.VMInfo) {
	for _, v := range vms {
		m.vms = append(m.vms, VMItem{
			Name:       v.Name,
			GuestOS:    v.GuestOS,
			PowerState: v.PowerState,
			NumCPU:     int32(v.NumCPUs),
			MemoryMB:   int32(v.MemoryMB),
			StorageMB:  int64(v.DiskSizeMB),
		})
	}
	m.updateStats()
}

// SetDisks is a no-op for compatibility.
func (m *Model) SetDisks(disks []protocol.DiskInfo) {}

// ── View ──

func (m Model) View() string {
	var b strings.Builder

	switch m.phase {
	case phaseLoading:
		b.WriteString(ui.TitleStyle.Render("🔍 Loading VMs from vCenter..."))

	case phaseError:
		b.WriteString(ui.ErrorStyle.Render(fmt.Sprintf("❌ %s", m.err)))
		b.WriteString("\n\n")
		b.WriteString(ui.DimStyle.Render("  r: Retry  |  Set GOVC_URL, GOVC_USERNAME, GOVC_PASSWORD env vars"))

	case phaseDetail:
		b.WriteString(m.renderDetail())

	case phaseTemplate:
		b.WriteString(m.renderTemplates())

	case phasePreview:
		b.WriteString(m.renderPreview())

	case phaseExport:
		b.WriteString(m.renderExportProgress())

	case phaseSelect:
		b.WriteString(m.renderVMList())

	default:
		if os.Getenv("GOVC_URL") != "" {
			b.WriteString(ui.TitleStyle.Render("📦 vSphere VM Browser"))
			b.WriteString("\n\n")
			b.WriteString(ui.ValueStyle.Render("  Press ") + ui.KeyHintKeyStyle.Render("l") + ui.ValueStyle.Render(" to load VMs from vCenter"))
			b.WriteString("\n")
			b.WriteString(ui.DimStyle.Render(fmt.Sprintf("  vCenter: %s", os.Getenv("GOVC_URL"))))
		} else {
			b.WriteString(ui.WarningStyle.Render("Set GOVC_* env vars to browse vSphere VMs"))
			b.WriteString("\n\n")
			b.WriteString(ui.DimStyle.Render("  export GOVC_URL='https://vcenter/sdk'"))
			b.WriteString("\n")
			b.WriteString(ui.DimStyle.Render("  export GOVC_USERNAME='admin@vsphere.local'"))
			b.WriteString("\n")
			b.WriteString(ui.DimStyle.Render("  export GOVC_PASSWORD='password'"))
			b.WriteString("\n")
			b.WriteString(ui.DimStyle.Render("  export GOVC_INSECURE=1"))
			b.WriteString("\n")
			b.WriteString(ui.DimStyle.Render("  export GOVC_DATACENTER='dc'"))
		}
	}

	return b.String()
}

func (m Model) renderVMList() string {
	var b strings.Builder

	// Title + stats bar.
	visible := m.getVisibleVMs()
	selected := m.countSelected()

	b.WriteString(ui.TitleStyle.Render("📦 vSphere VM Browser"))
	b.WriteString("\n\n")

	// Stats line (hypersdk style).
	stats := fmt.Sprintf("💻 %d VMs  🟢 %d ON  🔴 %d OFF  ⚡ %d CPUs  💾 %.1f GB RAM",
		len(m.vms), m.poweredOn, m.poweredOff, m.totalCPU, float64(m.totalMemMB)/1024)
	b.WriteString(ui.StatsStyle.Render(stats))
	b.WriteString("\n")

	// Filter/search bar.
	var filters []string
	if m.searchQuery != "" {
		filters = append(filters, fmt.Sprintf("🔍 %s", m.searchQuery))
	}
	if m.filterPower != "" {
		filters = append(filters, fmt.Sprintf("⚡ %s", m.filterPower))
	}
	filters = append(filters, fmt.Sprintf("📑 %s", m.sortMode))
	if selected > 0 {
		filters = append(filters, fmt.Sprintf("✅ %d selected", selected))
	}
	b.WriteString(ui.DimStyle.Render(strings.Join(filters, "  │  ")))
	b.WriteString("\n")

	// Search input.
	if m.searching {
		b.WriteString(ui.LabelStyle.Render("Search: ") + m.searchQuery + "█")
		b.WriteString("\n")
	}

	b.WriteString("\n")

	// Table header.
	header := fmt.Sprintf("  %-3s %-35s %s %4s %6s %8s  %-20s",
		"", "VM Name", "⚡", "CPU", "RAM", "Disk", "Guest OS")
	b.WriteString(ui.TableHeaderStyle.Render(header))
	b.WriteString("\n")

	// VM list (windowed — show max 30 rows around cursor).
	if len(visible) == 0 {
		b.WriteString(ui.DimStyle.Render("  No VMs match current filters"))
		b.WriteString("\n")
	}

	maxVisible := 30
	if m.height > 10 {
		maxVisible = m.height - 12 // Leave room for header/footer
	}
	if maxVisible < 5 {
		maxVisible = 5
	}

	start := 0
	if m.cursor > maxVisible/2 {
		start = m.cursor - maxVisible/2
	}
	end := start + maxVisible
	if end > len(visible) {
		end = len(visible)
		start = end - maxVisible
		if start < 0 {
			start = 0
		}
	}

	if start > 0 {
		b.WriteString(ui.DimStyle.Render(fmt.Sprintf("  ↑ %d more above", start)))
		b.WriteString("\n")
	}

	for i := start; i < end; i++ {
		vm := visible[i]
		isCursor := i == m.cursor

		// Checkbox.
		checkbox := "[ ]"
		if vm.Selected {
			checkbox = "[✓]"
		}

		// Cursor.
		cursor := "  "
		if isCursor {
			cursor = "▶ "
		}

		// Power icon.
		powerIcon := "🔴"
		if vm.PowerState == "poweredOn" {
			powerIcon = "🟢"
		}

		// Format line.
		line := fmt.Sprintf("%s%s %-35s %s %4d %4.0fG %6dM  %-20s",
			cursor, checkbox,
			truncate(vm.Name, 35),
			powerIcon,
			vm.NumCPU,
			float64(vm.MemoryMB)/1024,
			vm.StorageMB,
			truncate(vm.GuestOS, 20))

		if isCursor {
			b.WriteString(ui.SelectedStyle.Render(line))
		} else if vm.Selected {
			b.WriteString(ui.SuccessStyle.Render(line))
		} else {
			b.WriteString(ui.ValueStyle.Render(line))
		}
		b.WriteString("\n")
	}

	if end < len(visible) {
		b.WriteString(ui.DimStyle.Render(fmt.Sprintf("  ↓ %d more below", len(visible)-end)))
		b.WriteString("\n")
	}

	b.WriteString("\n")

	// Help bar.
	help := ui.KeyHintKeyStyle.Render("Space") + ui.KeyHintStyle.Render(" Select  ") +
		ui.KeyHintKeyStyle.Render("a") + ui.KeyHintStyle.Render(" All  ") +
		ui.KeyHintKeyStyle.Render("n") + ui.KeyHintStyle.Render(" None  ") +
		ui.KeyHintKeyStyle.Render("/") + ui.KeyHintStyle.Render(" Search  ") +
		ui.KeyHintKeyStyle.Render("s") + ui.KeyHintStyle.Render(" Sort  ") +
		ui.KeyHintKeyStyle.Render("f") + ui.KeyHintStyle.Render(" Filter  ") +
		ui.KeyHintKeyStyle.Render("d") + ui.KeyHintStyle.Render(" Detail  ") +
		ui.KeyHintKeyStyle.Render("r") + ui.KeyHintStyle.Render(" Refresh")
	b.WriteString(help)

	return b.String()
}

func (m Model) renderDetail() string {
	visible := m.getVisibleVMs()
	if m.cursor >= len(visible) {
		return ui.DimStyle.Render("No VM selected")
	}

	vm := visible[m.cursor]
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render(fmt.Sprintf("📦 %s", vm.Name)))
	b.WriteString("\n\n")

	// Power state.
	power := "🔴 Powered OFF"
	if vm.PowerState == "poweredOn" {
		power = "🟢 Powered ON"
	}

	info := [][]string{
		{"Power:", power},
		{"Path:", vm.Path},
		{"OS:", vm.GuestOS},
		{"", ""},
		{"CPUs:", fmt.Sprintf("%d cores", vm.NumCPU)},
		{"Memory:", fmt.Sprintf("%.1f GB (%d MB)", float64(vm.MemoryMB)/1024, vm.MemoryMB)},
		{"Storage:", fmt.Sprintf("%d MB", vm.StorageMB)},
	}

	for _, row := range info {
		if row[0] == "" {
			b.WriteString("\n")
			continue
		}
		b.WriteString(fmt.Sprintf("  %-10s %s\n",
			ui.StatsStyle.Render(row[0]),
			ui.ValueStyle.Render(row[1])))
	}

	b.WriteString("\n")
	if vm.Selected {
		b.WriteString(ui.BadgeSuccessStyle.Render(" ✓ SELECTED FOR MIGRATION "))
	} else {
		b.WriteString(ui.DimStyle.Render("  Not selected"))
	}

	b.WriteString("\n\n")
	b.WriteString(ui.DimStyle.Render("  Press any key to go back"))

	return ui.PanelStyle.Render(b.String())
}

func (m Model) renderTemplates() string {
	var b strings.Builder

	b.WriteString(ui.TitleStyle.Render("📋 Export Templates"))
	b.WriteString("\n\n")

	selected := m.getSelectedVMs()
	b.WriteString(ui.StatsStyle.Render(fmt.Sprintf("Exporting %d VM(s)", len(selected))))
	b.WriteString("\n\n")

	for i, tmpl := range ExportTemplates {
		cursor := "  "
		if i == m.templateCursor {
			cursor = "▶ "
		}

		style := ui.ValueStyle
		if i == m.templateCursor {
			style = ui.SelectedStyle
		}

		header := fmt.Sprintf("%s[%d] %s", cursor, i+1, tmpl.Name)
		b.WriteString(style.Render(header))
		b.WriteString("\n")
		b.WriteString(ui.DimStyle.Render(fmt.Sprintf("    %s", tmpl.Description)))
		b.WriteString("\n")

		settings := fmt.Sprintf("    Format: %s │ Compress: %s │ Fix: %s │ Test: %s",
			tmpl.Format, boolYN(tmpl.Compress), boolYN(tmpl.Fix), boolYN(tmpl.LibvirtTest))
		b.WriteString(ui.DimStyle.Render(settings))
		b.WriteString("\n\n")
	}

	b.WriteString(ui.KeyHintKeyStyle.Render("↑/↓") + ui.KeyHintStyle.Render(" Navigate  ") +
		ui.KeyHintKeyStyle.Render("Enter") + ui.KeyHintStyle.Render(" Select  ") +
		ui.KeyHintKeyStyle.Render("Esc") + ui.KeyHintStyle.Render(" Back"))

	return ui.PanelStyle.Render(b.String())
}

func (m Model) renderPreview() string {
	var b strings.Builder

	selected := m.getSelectedVMs()
	tmpl := m.selectedTmpl

	b.WriteString(ui.TitleStyle.Render("📋 Export Preview"))
	b.WriteString("\n\n")

	// Summary stats
	var totalCPU int32
	var totalMem int32
	var totalStor int64
	for _, vm := range selected {
		totalCPU += vm.NumCPU
		totalMem += vm.MemoryMB
		totalStor += vm.StorageMB
	}

	stats := []string{
		fmt.Sprintf("VMs: %d", len(selected)),
		fmt.Sprintf("Template: %s", tmpl.Name),
		fmt.Sprintf("Total CPUs: %d", totalCPU),
		fmt.Sprintf("Total RAM: %.1f GB", float64(totalMem)/1024),
		fmt.Sprintf("Total Disk: %.1f GB", float64(totalStor)/1024),
	}
	for _, s := range stats {
		b.WriteString(ui.ValueStyle.Render("  • " + s))
		b.WriteString("\n")
	}

	// VM list
	b.WriteString("\n")
	b.WriteString(ui.SubtitleStyle.Render("VMs to export:"))
	b.WriteString("\n")
	for _, vm := range selected {
		power := "🔴"
		if vm.PowerState == "poweredOn" {
			power = "🟢"
		}
		b.WriteString(fmt.Sprintf("  %s %s (%d CPU, %.0fG RAM)\n", power, vm.Name, vm.NumCPU, float64(vm.MemoryMB)/1024))
	}

	// Command preview
	if len(selected) > 0 {
		binary := findH2kvmctl()
		args := BuildExportCommand(selected[0], *tmpl, "./output-"+selected[0].Name)
		b.WriteString("\n")
		b.WriteString(ui.SubtitleStyle.Render("Command (first VM):"))
		b.WriteString("\n")
		b.WriteString(ui.DimStyle.Render(PreviewCommand(binary, args)))
	}

	b.WriteString("\n\n")
	b.WriteString(ui.KeyHintKeyStyle.Render("Enter") + ui.KeyHintStyle.Render(" Start export  ") +
		ui.KeyHintKeyStyle.Render("Esc") + ui.KeyHintStyle.Render(" Cancel"))

	return ui.PanelStyle.Render(b.String())
}

func (m Model) renderExportProgress() string {
	var b strings.Builder

	selected := m.getSelectedVMs()
	p := m.exportProgress

	b.WriteString(ui.TitleStyle.Render("📦 Exporting VMs"))
	b.WriteString("\n\n")

	// Overall progress
	b.WriteString(fmt.Sprintf("VM %d / %d", m.currentExport+1, len(selected)))
	if p.CurrentVM != "" {
		b.WriteString(fmt.Sprintf("  —  %s", p.CurrentVM))
	}
	b.WriteString("\n")

	// Progress bar
	barWidth := 40
	filled := int(p.Percent / 100.0 * float64(barWidth))
	if filled > barWidth {
		filled = barWidth
	}
	bar := strings.Repeat("█", filled) + strings.Repeat("░", barWidth-filled)
	b.WriteString(ui.ProgressFullStyle.Render(bar))
	b.WriteString(fmt.Sprintf(" %.0f%%", p.Percent))
	b.WriteString("\n")

	// Phase + speed
	b.WriteString(fmt.Sprintf("Phase: %s", strings.ToUpper(p.Phase)))
	if p.Speed != "" {
		b.WriteString(fmt.Sprintf("  │  Speed: %s", p.Speed))
	}
	elapsed := time.Since(p.StartTime)
	b.WriteString(fmt.Sprintf("  │  Elapsed: %s", formatDuration(elapsed)))
	b.WriteString("\n\n")

	// Per-VM status
	for i, vm := range selected {
		icon := "⏸ "
		status := "Pending"
		style := ui.DimStyle

		if i < len(m.exportResults) {
			if m.exportResults[i].Success {
				icon = "✅"
				status = fmt.Sprintf("Done (%s)", formatDuration(m.exportResults[i].Duration))
				style = ui.SuccessStyle
			} else {
				icon = "❌"
				status = "Failed"
				style = ui.ErrorStyle
			}
		} else if i == m.currentExport {
			icon = "⏳"
			status = "Exporting..."
			style = ui.SelectedStyle
		}

		line := fmt.Sprintf("%s %-35s %s", icon, truncate(vm.Name, 35), status)
		b.WriteString(style.Render(line))
		b.WriteString("\n")
	}

	// Last log lines
	if len(m.exportLogs) > 0 {
		b.WriteString("\n")
		b.WriteString(ui.SubtitleStyle.Render("Log:"))
		b.WriteString("\n")
		start := len(m.exportLogs) - 5
		if start < 0 {
			start = 0
		}
		for _, line := range m.exportLogs[start:] {
			b.WriteString(ui.DimStyle.Render("  " + truncate(line, 70)))
			b.WriteString("\n")
		}
	}

	return b.String()
}

func boolYN(v bool) string {
	if v {
		return "Yes"
	}
	return "No"
}

func formatDuration(d time.Duration) string {
	if d < time.Minute {
		return fmt.Sprintf("%.0fs", d.Seconds())
	}
	return fmt.Sprintf("%.0fm%.0fs", d.Minutes(), d.Seconds()-d.Truncate(time.Minute).Seconds())
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
