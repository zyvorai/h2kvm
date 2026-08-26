// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/state"
	"github.com/hyper2kvm/zkvm/internal/theme"
	"github.com/hyper2kvm/zkvm/internal/widgets"
)

// ExportResultMsg carries the result of an Export to Libvirt action.
type ExportResultMsg struct {
	Err error
}

// Progress-parsing regexes.
var (
	reProgress  = regexp.MustCompile(`progress:\s*([\d.]+)%`)
	reDiskStage = regexp.MustCompile(`Processing disk \d+/\d+:\s*(.+)`)
)

// RunState represents the subprocess lifecycle.
type RunState int

const (
	StateIdle      RunState = iota // Filling form
	StateRunning                   // h2kvmctl running
	StateCompleted                 // Exited 0
	StateFailed                    // Exited non-0
)

// Tab constants.
const (
	TabMigration  = 0
	TabVSphere    = 1
	TabLogs       = 2
	TabLibvirt    = 3
	TabKubernetes = 4
	tabCount      = 5
)

// Tab display names.
var tabNames = [tabCount]string{"Migration", "vSphere", "Logs", "Libvirt VMs", "Kubernetes"}

// Powerline / Zellij-style separator characters.
const (
	tabSepRight = "\ue0b0" //
)

// Border + padding overhead for each pane.
const (
	paneHPad = 4 // horizontal: 2 border + 2 padding
	paneVPad = 2 // vertical:   2 border + 0 padding
	headerH  = 2 // pane header + margin
)

// Fixed vertical layout lines:
//   title bar (1) + tab bar (1) + content (flexible) + status bar (1)
//   plus 3 newlines between them = 6 lines overhead.
const layoutOverhead = 6

// Model is the top-level Bubble Tea model for standalone mode.
type Model struct {
	store        *state.Store
	form         *FormData
	logView      widgets.LogView
	formVP       viewport.Model
	runner       *Runner
	state        RunState
	activeTab    int
	libvirtModel LibvirtModel
	kubeModel    KubernetesModel
	helpModel    HelpModel
	notifyCfg    NotificationConfig
	pid          int
	exitCode     int
	exitErr      string
	width        int
	height       int
	ready        bool

	// Progress tracking.
	progress      float64 // 0.0–100.0, parsed from log output
	stage         string  // current pipeline stage
	exportMsg     string  // result message from export action
	exporting     bool    // export in progress
	profileMsg    string  // profile save/load result message
	exportProgress ExportProgress // structured export progress

	// vSphere tab.
	vsphereTab     *VsphereTab     // vSphere connection + discovery (pointer survives value copies)
	discoveredVMs  []VsphereVMInfo // VMs found via govc
	discoverMsg    string          // discovery status message
	discovering    bool            // discovery in progress
	vmListCursor   int             // cursor position in VM list

	// File browser modal.
	fileBrowser    *FileBrowser // nil when not active

	// Quick migrate.
	quickConfig    *QuickMigrateConfig // auto-detected config
	quickMsg       string              // quick migrate status
	showPreview    bool                // show command preview overlay

	// Pre-flight.
	preflightResults []PreflightCheck // pre-flight check results
	showPreflight    bool             // show preflight overlay

	// Diagnosis.
	diagnosisResult *DiagnosisResult // failure diagnosis
	showDiagnosis   bool             // show diagnosis overlay

	// Queue — sequential VM processing.
	vmQueue       []VsphereVMInfo // VMs to process one by one
	queueIdx      int             // current VM in queue
	queueResults  []QueueResult   // per-VM results
	queueRunning  bool            // queue is running

	webConsoles    []*WebConsole     // active noVNC web consoles
}

// QueueResult tracks per-VM migration outcome.
type QueueResult struct {
	VMName  string
	Success bool
	Error   string
}

// QueueDoneMsg signals one VM in the queue finished.
type QueueDoneMsg struct {
	VMName   string
	ExitCode int
	Err      error
}

// triggerVSphereAutoDiscover triggers VM discovery when switching to vSphere tab.
func (m *Model) triggerVSphereAutoDiscover() tea.Cmd {
	if m.discovering || len(m.discoveredVMs) > 0 {
		return nil
	}
	if !m.vsphereTab.HasCredentials() {
		return nil
	}
	m.discovering = true
	m.discoverMsg = "Discovering VMs..."
	return discoverVMsCmd(m.vsphereTab.BuildFormData())
}

// handleVSphereKey handles keys for the vSphere tab.
func (m Model) handleVSphereKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	// Handle text editing in connection fields.
	if m.vsphereTab.focusPanel == 0 {
		f := &m.vsphereTab.fields[m.vsphereTab.fieldIdx]
		if f.Editing {
			switch key {
			case "esc", "enter":
				f.Editing = false
				if key == "enter" && m.vsphereTab.fieldIdx < len(m.vsphereTab.fields)-1 {
					m.vsphereTab.fieldIdx++
				}
			case "backspace":
				if len(f.Value) > 0 {
					f.Value = f.Value[:len(f.Value)-1]
				}
			default:
				if len(msg.Runes) > 0 {
					for _, r := range msg.Runes {
						f.Value += string(r)
					}
				}
			}
			return m, nil
		}
	}

	switch key {
	case "j", "down":
		if m.vsphereTab.focusPanel == 0 {
			if m.vsphereTab.fieldIdx < len(m.vsphereTab.fields)-1 {
				m.vsphereTab.fieldIdx++
			} else {
				// Move to VM list panel.
				if len(m.discoveredVMs) > 0 {
					m.vsphereTab.focusPanel = 1
				}
			}
		} else {
			if m.vmListCursor < len(m.discoveredVMs)-1 {
				m.vmListCursor++
			}
		}
		return m, nil

	case "k", "up":
		if m.vsphereTab.focusPanel == 1 {
			if m.vmListCursor > 0 {
				m.vmListCursor--
			} else {
				// Move back to connection fields.
				m.vsphereTab.focusPanel = 0
				m.vsphereTab.fieldIdx = len(m.vsphereTab.fields) - 1
			}
		} else {
			if m.vsphereTab.fieldIdx > 0 {
				m.vsphereTab.fieldIdx--
			}
		}
		return m, nil

	case "enter":
		if m.vsphereTab.focusPanel == 0 {
			f := &m.vsphereTab.fields[m.vsphereTab.fieldIdx]
			if f.IsToggle {
				f.BoolValue = !f.BoolValue
			} else {
				f.Editing = true
				f.CursorPos = len(f.Value)
			}
		}
		return m, nil

	case " ":
		if m.vsphereTab.focusPanel == 1 && len(m.discoveredVMs) > 0 {
			if m.vmListCursor >= 0 && m.vmListCursor < len(m.discoveredVMs) {
				m.discoveredVMs[m.vmListCursor].Selected = !m.discoveredVMs[m.vmListCursor].Selected
			}
			count := 0
			for _, vm := range m.discoveredVMs {
				if vm.Selected {
					count++
				}
			}
			m.discoverMsg = fmt.Sprintf("%d VM(s) selected — Ctrl+R to migrate", count)
		} else if m.vsphereTab.focusPanel == 0 {
			f := &m.vsphereTab.fields[m.vsphereTab.fieldIdx]
			if f.IsToggle {
				f.BoolValue = !f.BoolValue
			}
		}
		return m, nil

	case "a":
		// Select all VMs.
		if m.vsphereTab.focusPanel == 1 && len(m.discoveredVMs) > 0 {
			allSelected := true
			for _, vm := range m.discoveredVMs {
				if !vm.Selected {
					allSelected = false
					break
				}
			}
			for i := range m.discoveredVMs {
				m.discoveredVMs[i].Selected = !allSelected
			}
			count := 0
			for _, vm := range m.discoveredVMs {
				if vm.Selected {
					count++
				}
			}
			m.discoverMsg = fmt.Sprintf("%d VM(s) selected — Ctrl+R to migrate", count)
		}
		return m, nil

	case "ctrl+d":
		if !m.discovering {
			if !m.vsphereTab.HasCredentials() {
				m.discoverMsg = "Fill in vCenter hostname first"
				return m, nil
			}
			m.discovering = true
			m.discoveredVMs = nil
			m.vmListCursor = 0
			m.discoverMsg = "Discovering VMs..."
			return m, discoverVMsCmd(m.vsphereTab.BuildFormData())
		}
		return m, nil

	case "ctrl+r":
		// Run migration for selected VMs.
		if m.state != StateRunning && len(m.discoveredVMs) > 0 {
			var selected []VsphereVMInfo
			for _, vm := range m.discoveredVMs {
				if vm.Selected {
					selected = append(selected, vm)
				}
			}
			if len(selected) > 0 {
				// Copy vSphere credentials to the main form.
				m.syncVSphereToForm()
				return m.startQueue(selected)
			}
			m.discoverMsg = "Select VMs first (Space to toggle, a for all)"
		}
		return m, nil
	}

	return m, nil
}

// syncVSphereToForm copies vSphere tab fields to the migration form
// and enables the full pipeline: export → convert → fix → libvirt deploy.
func (m *Model) syncVSphereToForm() {
	// Set cmd to vsphere with export_vm action.
	m.form.SetSelectValue("cmd", "vsphere")
	m.form.SetFieldValue("vs_action", "export_vm")

	// Enable full pipeline: export → offline fixes → libvirt domain.
	m.form.SetFieldBoolValue("emit_domain_xml", true)
	m.form.SetFieldBoolValue("regen_initramfs", true)

	// Copy connection fields (vcenter, vc_user, vc_password, dc_name, etc).
	for _, vf := range m.vsphereTab.fields {
		if vf.IsToggle {
			m.form.SetFieldBoolValue(vf.Label, vf.BoolValue)
		} else if vf.Value != "" {
			m.form.SetFieldValue(vf.Label, vf.Value)
		}
	}
}

// renderVSphereContent draws the vSphere tab — connection fields (left) + VM list (right).
func (m Model) renderVSphereContent() string {
	leftW, rightW, paneH, leftInnerW, rightInnerW, _ := m.splitPaneDims()

	// Left pane: connection fields.
	leftContent := m.vsphereTab.RenderConnectionFields(leftInnerW, true)

	leftPane := focusedPaneStyle.
		Width(leftW).
		Height(paneH).
		Render(leftContent)

	// Right pane: VM list.
	rightContent := m.vsphereTab.RenderVMList(
		m.discoveredVMs,
		m.vmListCursor,
		true,
		m.discoverMsg,
		m.discovering,
		rightInnerW,
	)

	rightPane := blurredPaneStyle.
		Width(rightW).
		Height(paneH).
		Render(rightContent)

	return lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)
}

// renderVSphereStatusBar draws the status bar for the vSphere tab.
func (m Model) renderVSphereStatusBar() string {
	left := statusIdleStyle.Render("[vSphere]")

	if m.discovering {
		left = statusRunningStyle.Render("[DISCOVERING]")
	} else if len(m.discoveredVMs) > 0 {
		selected := 0
		for _, vm := range m.discoveredVMs {
			if vm.Selected {
				selected++
			}
		}
		left = statusCompletedStyle.Render(fmt.Sprintf("[%d VMs — %d selected]", len(m.discoveredVMs), selected))
	}

	hints := hintKeyStyle.Render("^D") + hintStyle.Render(" Discover ") +
		hintKeyStyle.Render("^R") + hintStyle.Render(" Migrate ") +
		hintKeyStyle.Render("Space") + hintStyle.Render(" Toggle ") +
		hintKeyStyle.Render("a") + hintStyle.Render(" All ") +
		hintKeyStyle.Render("j/k") + hintStyle.Render(" Navigate ") +
		hintKeyStyle.Render("Enter") + hintStyle.Render(" Edit")

	leftWidth := lipgloss.Width(left)
	rightWidth := lipgloss.Width(hints)
	spacing := m.width - leftWidth - rightWidth - 2
	if spacing < 1 {
		spacing = 1
	}

	return statusBarStyle.Width(m.width).Render(
		left + strings.Repeat(" ", spacing) + hints,
	)
}

// New creates a standalone model with pre-filled values.
// binaryPath overrides automatic h2kvmctl detection (empty = auto-detect).
func New(store *state.Store, pf Prefill, binaryPath string) Model {
	return Model{
		store:        store,
		form:         NewFormData(pf),
		logView:      widgets.NewLogView(20, 10),
		formVP:       viewport.New(20, 10),
		runner:       NewRunner(binaryPath),
		state:        StateIdle,
		vsphereTab:   NewVsphereTab(pf),
		libvirtModel: NewLibvirtModel(),
		kubeModel:    NewKubernetesModel(),
		helpModel:    NewHelpModel(),
		notifyCfg:     NotificationConfig{DesktopEnabled: true, OnCompletion: true, OnFailure: true},
	}
}

// SetProgram stores the tea.Program reference on the runner.
// Must be called after tea.NewProgram() so the runner can send messages.
func (m *Model) SetProgram(p *tea.Program) {
	m.runner.SetProgram(p)
	m.libvirtModel.SetProgram(p)
}

// Init implements tea.Model.
func (m Model) Init() tea.Cmd {
	cmds := []tea.Cmd{tea.EnterAltScreen, m.libvirtModel.Init(), m.kubeModel.Init()}

	// Auto-discover VMs if vCenter credentials are available from env.
	if m.vsphereTab.HasCredentials() {
		m.discovering = true
		m.discoverMsg = "Discovering VMs..."
		cmds = append(cmds, discoverVMsCmd(m.vsphereTab.BuildFormData()))
	}

	return tea.Batch(cmds...)
}

// Update implements tea.Model.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.recalcLayout()
		m.updateFormViewport()
		m.ready = true
		return m, nil

	// Process messages — always handle regardless of active tab.
	case LogLineMsg:
		m.parseProgress(msg.Line)
		// Suppress progress/monitor lines from log view — shown as progress bar instead.
		if !strings.Contains(msg.Line, "[PROGRESS]") && !strings.HasPrefix(msg.Line, "📥") {
			m.logView = m.logView.AppendLog(classifyLogLevel(msg.Line), msg.Line)
		}
		return m, nil

	case ExportResultMsg:
		m.exporting = false
		if msg.Err != nil {
			m.exportMsg = "Export failed: " + msg.Err.Error()
		} else {
			m.exportMsg = "Exported! VM defined in libvirt"
			// Trigger a libvirt tab refresh.
			return m, fetchVMList
		}
		return m, nil

	case DiscoverVMsMsg:
		m.discovering = false
		if msg.Err != nil {
			m.discoverMsg = "Discovery failed: " + msg.Err.Error()
		} else {
			m.discoveredVMs = msg.VMs
			m.vmListCursor = 0
			m.vsphereTab.focusPanel = 1 // Auto-focus VM list.
			m.discoverMsg = fmt.Sprintf("Found %d VM(s) — j/k to navigate, Space to select", len(msg.VMs))
		}
		return m, nil

	case ProcessStartedMsg:
		m.pid = msg.PID
		m.state = StateRunning
		m.progress = 0
		m.stage = ""
		m.exportMsg = ""
		m.logView = m.logView.AppendLog("INFO",
			fmt.Sprintf("Process started (PID %d)", msg.PID))
		// Auto-switch to Logs tab when process starts.
		m.activeTab = TabLogs
		return m, nil

	case ProcessDoneMsg:
		m.exitCode = msg.ExitCode
		if msg.Err != nil {
			m.exitErr = msg.Err.Error()
		}
		if msg.ExitCode == 0 && msg.Err == nil {
			m.state = StateCompleted
			m.logView = m.logView.AppendLog("INFO", "Process completed successfully")

			// Show Windows driver install hint if this was a Windows migration.
			if guestOS := m.form.GetFieldValue("guest_os"); guestOS == "windows" {
				m.logView = m.logView.AppendLog("INFO", "")
				m.logView = m.logView.AppendLog("INFO", "━━━ Windows Post-Migration Steps ━━━")
				m.logView = m.logView.AppendLog("INFO", "1. Connect via VNC console")
				m.logView = m.logView.AppendLog("INFO", "2. Open CD Drive (D:) in File Explorer")
				m.logView = m.logView.AppendLog("INFO", "3. Run: virtio-win-guest-tools.exe")
				m.logView = m.logView.AppendLog("INFO", "   This installs VirtIO network, balloon, and guest agent")
				m.logView = m.logView.AppendLog("INFO", "4. Network will be available immediately (no reboot needed)")
				m.logView = m.logView.AppendLog("INFO", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
			}

			// Queue: record success and start next VM.
			if m.queueRunning {
				m.queueResults = append(m.queueResults, QueueResult{
					VMName:  m.vmQueue[m.queueIdx].Name,
					Success: true,
				})
				m.queueIdx++
				if m.queueIdx < len(m.vmQueue) {
					return m.runQueuedVM(m.queueIdx)
				}
				// All done.
				m.queueRunning = false
				m.logView = m.logView.AppendLog("INFO", m.queueSummary())
				m.discoverMsg = m.queueSummary()
			}

			if m.notifyCfg.OnCompletion {
				SendNotification(m.notifyCfg, "Migration Complete", "hyper2kvm migration finished successfully")
			}
		} else {
			m.state = StateFailed

			// Queue: record failure and continue to next VM.
			if m.queueRunning {
				errStr := ""
				if msg.Err != nil {
					errStr = msg.Err.Error()
				}
				m.queueResults = append(m.queueResults, QueueResult{
					VMName:  m.vmQueue[m.queueIdx].Name,
					Success: false,
					Error:   errStr,
				})
				m.logView = m.logView.AppendLog("ERROR",
					fmt.Sprintf("VM %s failed (exit %d), continuing...", m.vmQueue[m.queueIdx].Name, msg.ExitCode))
				m.queueIdx++
				if m.queueIdx < len(m.vmQueue) {
					m.state = StateIdle
					return m.runQueuedVM(m.queueIdx)
				}
				// All done.
				m.queueRunning = false
				m.logView = m.logView.AppendLog("INFO", m.queueSummary())
				m.discoverMsg = m.queueSummary()
			} else {
				// Single VM failure — diagnose.
				var allLogs string
				for _, l := range m.logView.Lines() {
					allLogs += l + "\n"
				}
				m.diagnosisResult = DiagnoseFailure(msg.ExitCode, allLogs)
				m.showDiagnosis = true
			}

			errMsg := fmt.Sprintf("Process exited with code %d", msg.ExitCode)
			if msg.Err != nil {
				errMsg += ": " + msg.Err.Error()
			}
			m.logView = m.logView.AppendLog("ERROR", errMsg)
			if m.notifyCfg.OnFailure {
				SendNotification(m.notifyCfg, "Migration Failed", errMsg)
			}
		}
		return m, nil

	// Open console request from Libvirt/Kubernetes tab.
	case OpenConsoleMsg:
		go func(name string) {
			// Timeout prevents goroutine leak if virsh hangs.
			done := make(chan struct{})
			go func() {
				SetVNCListenAll(name)
				close(done)
			}()
			select {
			case <-done:
			case <-time.After(30 * time.Second):
			}
		}(msg.VMName)
		err := LaunchViewer(msg.VMName, msg.Host, msg.Port, msg.GfxType)
		if err != nil {
			m.logView = m.logView.AppendLog("ERROR", "Console: "+err.Error())
		} else {
			m.logView = m.logView.AppendLog("INFO", "Opened viewer for "+msg.VMName)
		}
		return m, nil

	// Open web console (noVNC) request.
	case OpenWebConsoleMsg:
		go func(name string) {
			// Timeout prevents goroutine leak if virsh hangs.
			done := make(chan struct{})
			go func() {
				SetVNCListenAll(name)
				close(done)
			}()
			select {
			case <-done:
			case <-time.After(30 * time.Second):
			}
		}(msg.VMName)
		wc, err := StartWebConsole(msg.VMName, msg.Host, msg.Port)
		if err != nil {
			m.logView = m.logView.AppendLog("ERROR", "Web console: "+err.Error())
		} else {
			m.webConsoles = append(m.webConsoles, wc)
			m.logView = m.logView.AppendLog("INFO", "noVNC for "+msg.VMName+": "+wc.URL())
		}
		return m, nil

	// Libvirt tab messages — always handle so background refreshes work.
	case VMListMsg, VMActionMsg, vmTickMsg, SnapshotActionMsg:
		var cmd tea.Cmd
		m.libvirtModel, cmd = m.libvirtModel.Update(msg)
		return m, cmd

	// Kubernetes tab messages.
	case KubeVMListMsg, KubeActionMsg, kubeTickMsg:
		var cmd tea.Cmd
		m.kubeModel, cmd = m.kubeModel.Update(msg)
		return m, cmd

	case KubeSSHDoneMsg:
		var cmd tea.Cmd
		m.kubeModel, cmd = m.kubeModel.Update(msg)
		return m, cmd

	case tea.KeyMsg:
		return m.handleKey(msg)
	}

	// Forward non-key messages to the Logs tab viewport.
	if m.activeTab == TabLogs {
		m.logView, _ = m.logView.UpdateLogView(msg)
	}

	return m, nil
}

// handleKey processes keyboard input based on current state.
func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	// Help overlay intercepts all keys when visible.
	if m.helpModel.Visible() {
		m.helpModel = m.helpModel.Update(msg)
		return m, nil
	}

	// Quick migrate preview overlay.
	if m.showPreview {
		switch key {
		case "enter":
			// Run quick migrate with detected config.
			if m.quickConfig != nil && m.state != StateRunning {
				outputDir := m.form.GetFieldValue("output_dir")
				if outputDir == "" {
					outputDir = "./out"
				}
				args := m.quickConfig.BuildQuickArgs(outputDir)
				m.showPreview = false
				m.quickMsg = ""
				return m, m.runner.RunWithArgs(args)
			}
		case "esc":
			m.showPreview = false
			m.quickMsg = ""
		}
		return m, nil
	}

	// Pre-flight overlay.
	if m.showPreflight {
		m.showPreflight = false
		return m, nil
	}

	// Diagnosis overlay.
	if m.showDiagnosis {
		m.showDiagnosis = false
		return m, nil
	}

	// Global keys (always active, regardless of tab).
	switch key {
	case "ctrl+q":
		if m.runner.IsRunning() {
			m.runner.Stop()
		}
		for _, wc := range m.webConsoles {
			wc.Stop()
		}
		return m, tea.Quit

	case "ctrl+c":
		if m.state == StateRunning {
			m.runner.Stop()
			m.logView = m.logView.AppendLog("WARN", "Process interrupted by user")
			return m, nil
		}
		for _, wc := range m.webConsoles {
			wc.Stop()
		}
		return m, tea.Quit

	case "?":
		m.helpModel.Toggle()
		return m, nil

	case "alt+1":
		m.activeTab = TabMigration
		return m, nil

	case "alt+2":
		m.activeTab = TabVSphere
		return m, m.triggerVSphereAutoDiscover()

	case "alt+3":
		m.activeTab = TabLogs
		return m, nil

	case "alt+4":
		m.activeTab = TabLibvirt
		return m, nil

	case "alt+5":
		m.activeTab = TabKubernetes
		return m, nil

	case "tab":
		// When editing a path field, Tab cycles completions instead.
		if m.activeTab == TabMigration {
			if f := m.form.FocusedField(); f != nil && f.Editing && f.PathComplete {
				m.form.CycleCompletion()
				m.updateFormViewport()
				return m, nil
			}
		}
		m.activeTab = (m.activeTab + 1) % tabCount
		if m.activeTab == TabVSphere {
			return m, m.triggerVSphereAutoDiscover()
		}
		return m, nil

	case "shift+tab":
		m.activeTab = (m.activeTab - 1 + tabCount) % tabCount
		if m.activeTab == TabVSphere {
			return m, m.triggerVSphereAutoDiscover()
		}
		return m, nil
	}

	// Route to the active tab.
	switch m.activeTab {
	case TabVSphere:
		return m.handleVSphereKey(msg)
	case TabLogs:
		return m.handleLogsKey(msg)
	case TabLibvirt:
		return m.handleLibvirtKey(msg)
	case TabKubernetes:
		return m.handleKubernetesKey(msg)
	default:
		return m.handleMigrationKey(msg)
	}
}

// handleMigrationKey handles keys for the Migration tab (config form only).
func (m Model) handleMigrationKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	// File browser modal is active — route all keys to it.
	if m.fileBrowser != nil && m.fileBrowser.IsActive() {
		closed := m.fileBrowser.HandleKey(key)
		if closed {
			if sel := m.fileBrowser.Selected(); sel != "" {
				if f := m.form.FocusedField(); f != nil {
					f.Value = sel
					f.CursorPos = len(sel)

					// Auto-detect Windows from source filename.
					if f.Label == "source" {
						autoDetectWindows(m.form, sel)
					}
				}
			}
			m.fileBrowser = nil
		}
		return m, nil
	}

	// A field is being edited — handle text input.
	if f := m.form.FocusedField(); f != nil && f.Editing {
		switch key {
		case "esc", "enter":
			m.form.StopEditing()
			m.form.HideCompletions()
		case "up", "down", "k", "j":
			// Exit edit mode and navigate — don't insert j/k as text.
			m.form.StopEditing()
			m.form.HideCompletions()
			return m.handleFormKey(key, msg)
		case "backspace":
			m.form.DeleteChar()
			m.form.ComputeCompletions()
		case "left":
			m.form.MoveCursorLeft()
		case "right":
			m.form.MoveCursorRight()
		case "tab":
			// Tab moves to next field instead of inserting.
			m.form.StopEditing()
			m.form.HideCompletions()
			m.form.MoveDown()
		default:
			if len(msg.Runes) > 0 {
				for _, r := range msg.Runes {
					m.form.InsertChar(r)
				}
				m.form.ComputeCompletions()
			}
		}
		m.updateFormViewport()
		return m, nil
	}

	switch key {
	case "ctrl+r":
		if m.state != StateRunning {
			// Single VM migration (form-based).
			return m.runMigration()
		}
		return m, nil

	case "ctrl+d":
		// Switch to vSphere tab for discovery.
		m.activeTab = TabVSphere
		return m, m.triggerVSphereAutoDiscover()

	case "ctrl+a":
		// No-op in Migration tab (vSphere moved to own tab).
		return m, nil

	case "ctrl+q":
		// Quick migrate — auto-detect and run.
		sourcePath := m.form.GetFieldValue("vmdk")
		if sourcePath == "" {
			sourcePath = m.form.GetFieldValue("ova")
		}
		if sourcePath == "" {
			m.quickMsg = "Set source disk path first (vmdk/ova)"
			return m, nil
		}
		cfg, err := DetectSource(sourcePath)
		if err != nil {
			m.quickMsg = "Detection failed: " + err.Error()
			return m, nil
		}
		m.quickConfig = cfg
		m.showPreview = true
		m.quickMsg = "Quick migrate: press Enter to run, Esc to cancel"
		m.updateFormViewport()
		return m, nil

	case "ctrl+f":
		// Pre-flight checks.
		m.preflightResults = RunPreflight(m.form)
		m.showPreflight = true
		m.updateFormViewport()
		return m, nil

	case "e":
		if m.state == StateCompleted && !m.exporting {
			return m.exportToLibvirt()
		}
	case "ctrl+p":
		// Save current form as profile.
		vmName := m.form.GetFieldValue("vm_name")
		if vmName == "" {
			vmName = "default"
		}
		if err := SaveProfile(vmName, m.form); err != nil {
			m.profileMsg = "Save failed: " + err.Error()
		} else {
			m.profileMsg = "Profile saved: " + vmName
		}
		return m, nil
	case "ctrl+l":
		// Load most recent profile.
		profiles, err := ListProfiles()
		if err != nil || len(profiles) == 0 {
			m.profileMsg = "No profiles found"
		} else {
			ApplyProfile(&profiles[0], m.form)
			m.profileMsg = "Loaded profile: " + profiles[0].Name
			m.updateFormViewport()
		}
		return m, nil
	}

	return m.handleFormKey(key, msg)
}

// handleLogsKey handles keys for the Logs tab.
func (m Model) handleLogsKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	switch key {
	case "ctrl+r":
		if m.state != StateRunning {
			return m.runMigration()
		}
		return m, nil
	}

	// Forward to log viewport for scrolling.
	m.logView, _ = m.logView.UpdateLogView(msg)
	return m, nil
}

// handleLibvirtKey forwards keys to the Libvirt tab model.
func (m Model) handleLibvirtKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	m.libvirtModel, cmd = m.libvirtModel.Update(msg)
	return m, cmd
}

// handleKubernetesKey forwards keys to the Kubernetes tab model.
func (m Model) handleKubernetesKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	m.kubeModel, cmd = m.kubeModel.Update(msg)
	return m, cmd
}


// handleFormKey handles keys when the config form is focused.
func (m Model) handleFormKey(key string, msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	// Number keys 1-4 toggle deploy targets from anywhere in the form.
	switch key {
	case "1":
		m.form.ToggleFieldBool("emit_domain_xml")
		return m, nil
	case "2":
		m.form.ToggleFieldBool("virsh_define")
		return m, nil
	case "3":
		m.form.ToggleFieldBool("libvirt_test")
		return m, nil
	case "4":
		m.form.ToggleFieldBool("deploy_k8s")
		return m, nil
	}

	switch key {
	case "up", "k":
		m.form.MoveUp()
		m.updateFormViewport()

	case "down", "j":
		m.form.MoveDown()
		m.updateFormViewport()

	case "enter":
		if m.form.InCategory {
			// Open file browser for path fields instead of inline editing.
			if f := m.form.FocusedField(); f != nil && f.PathComplete {
				startDir := f.Value
				if startDir == "" {
					startDir, _ = os.Getwd()
				}
				m.fileBrowser = NewFileBrowser(startDir, f.Extensions, f.DirOnly)
			} else {
				m.form.StartEditing()
			}
		} else {
			m.form.ToggleCategory()
		}
		m.updateFormViewport()

	case " ":
		if m.form.InCategory {
			m.form.ToggleField()
			m.updateFormViewport()
		}

	case "left", "h":
		m.form.CycleSelectLeft()
		m.updateFormViewport()

	case "right", "l":
		m.form.CycleSelectRight()
		m.updateFormViewport()

	case "esc":
		if m.form.InCategory {
			vis := m.form.VisibleCategories()
			if m.form.FocusCat >= 0 && m.form.FocusCat < len(vis) {
				catIdx := vis[m.form.FocusCat]
				m.form.Categories[catIdx].Expanded = false
				m.form.InCategory = false
			}
		}
		m.updateFormViewport()
	}

	return m, nil
}

// runMigration generates a YAML config and starts h2kvmctl.
func (m Model) runMigration() (tea.Model, tea.Cmd) {
	// Auto-set cmd to match source type before generating YAML.
	if src := m.form.GetFieldValue("source"); src != "" {
		cmdMap := map[string]string{"ova": "ova", "ovf": "ovf", "vhd": "vhd", "ami": "ami", "raw": "raw"}
		yamlKey, _ := detectSourceFormat(src)
		if cmd, ok := cmdMap[yamlKey]; ok {
			m.form.SetSelectValue("cmd", cmd)
		}
	}
	yamlContent := m.form.BuildYAML()
	m.state = StateRunning
	m.logView = m.logView.Clear()
	m.logView = m.logView.AppendLog("INFO", "Generated config and running: h2kvmctl --config <tempfile>")
	for _, line := range strings.Split(strings.TrimSpace(yamlContent), "\n") {
		if line != "" && !strings.HasPrefix(line, "#") {
			m.logView = m.logView.AppendLog("DEBUG", "  "+line)
		}
	}

	cmd := m.runner.StartWithConfig(yamlContent)
	return m, cmd
}

// exportToLibvirt initiates the export to libvirt process.
func (m Model) exportToLibvirt() (tea.Model, tea.Cmd) {
	outputDir := m.form.GetFieldValue("output_dir")
	vmName := m.form.GetFieldValue("vm_name")
	if outputDir == "" {
		outputDir = "./out"
	}
	if vmName == "" {
		vmName = "converted-vm"
	}

	m.exporting = true
	m.exportMsg = ""
	binaryPath := m.runner.binaryPath

	cmd := func() tea.Msg {
		err := ExportToLibvirt(binaryPath, outputDir, vmName)
		return ExportResultMsg{Err: err}
	}
	return m, cmd
}

// contentHeight returns the usable height for the content area.
func (m Model) contentHeight() int {
	h := m.height - layoutOverhead
	if h < 4 {
		h = 4
	}
	return h
}

// paneDims computes dimensions for a full-width single-pane tab.
func (m Model) paneDims() (outerW, paneH, innerW, vpH int) {
	paneH = m.contentHeight()
	outerW = m.width
	innerW = outerW - paneHPad
	if innerW < 10 {
		innerW = 10
	}
	vpH = paneH - paneVPad - headerH
	if vpH < 3 {
		vpH = 3
	}
	return
}

// splitPaneDims computes dimensions for a two-pane split tab (Libvirt VMs).
func (m Model) splitPaneDims() (leftOuterW, rightOuterW, paneH, leftInnerW, rightInnerW, vpH int) {
	paneH = m.contentHeight()
	leftOuterW = m.width / 2
	rightOuterW = m.width - leftOuterW
	leftInnerW = leftOuterW - paneHPad
	rightInnerW = rightOuterW - paneHPad
	if leftInnerW < 10 {
		leftInnerW = 10
	}
	if rightInnerW < 10 {
		rightInnerW = 10
	}
	vpH = paneH - paneVPad - headerH
	if vpH < 3 {
		vpH = 3
	}
	return
}

// recalcLayout adjusts sub-component sizes after a window resize.
func (m *Model) recalcLayout() {
	_, _, formInnerW, formVpH := m.paneDims()
	m.formVP.Width = formInnerW
	m.formVP.Height = formVpH

	_, _, logInnerW, logVpH := m.paneDims()
	m.logView = m.logView.SetSize(logInnerW, logVpH)

	leftW, rightW, libH, _, _, _ := m.splitPaneDims()
	m.libvirtModel.SetSize(leftW+rightW, libH)
	m.kubeModel.SetSize(leftW+rightW, libH)
	m.helpModel.SetSize(m.width, m.height)
}

// updateFormViewport refreshes the form viewport content and scroll position.
func (m *Model) updateFormViewport() {
	content := m.form.Render(m.formVP.Width)
	m.formVP.SetContent(content)

	focusRow := m.form.FocusRow()
	vpHeight := m.formVP.Height
	if vpHeight <= 0 {
		return
	}
	targetOffset := focusRow - vpHeight/2
	if targetOffset < 0 {
		targetOffset = 0
	}
	m.formVP.SetYOffset(targetOffset)
}

// View implements tea.Model.
func (m Model) View() string {
	if !m.ready {
		return "Initializing..."
	}

	var b strings.Builder

	// 1. Content area (no title bar — Zellij style).
	switch m.activeTab {
	case TabVSphere:
		b.WriteString(m.renderVSphereContent())
	case TabLogs:
		b.WriteString(m.renderLogsContent())
	case TabLibvirt:
		leftW, rightW, paneH, _, _, _ := m.splitPaneDims()
		b.WriteString(m.libvirtModel.View(leftW, rightW, paneH))
	case TabKubernetes:
		leftW, rightW, paneH, _, _, _ := m.splitPaneDims()
		b.WriteString(m.kubeModel.View(leftW, rightW, paneH))
	default:
		// Split panel: form (left) + logs (right) — Zellij style.
		b.WriteString(m.renderSplitMigration())
	}
	b.WriteString("\n")

	// 2. Tab bar (bottom — Zellij layout).
	b.WriteString(m.renderTabBar())
	b.WriteString("\n")

	// 3. Status bar (very bottom — mode + hints).
	switch m.activeTab {
	case TabVSphere:
		b.WriteString(m.renderVSphereStatusBar())
	case TabLogs:
		b.WriteString(m.renderLogsStatusBar())
	case TabLibvirt:
		b.WriteString(m.libvirtModel.StatusBar(m.width))
	case TabKubernetes:
		b.WriteString(m.kubeModel.StatusBar(m.width))
	default:
		b.WriteString(m.renderMigrationStatusBar())
	}

	output := b.String()

	// 5. Help overlay (rendered on top when visible).
	if m.helpModel.Visible() {
		output += "\n" + m.helpModel.View(m.activeTab)
	}

	// 6. Quick migrate preview overlay.
	if m.showPreview && m.quickConfig != nil {
		binaryPath := m.runner.BinaryPath()
		outputDir := m.form.GetFieldValue("output_dir")
		if outputDir == "" {
			outputDir = "./out"
		}
		preview := "\n╔══ Quick Migrate Preview ═══════════════════════╗\n"
		preview += "\n" + m.quickConfig.Summary() + "\n"
		preview += "\n  Command:\n" + m.quickConfig.PreviewCommand(binaryPath, outputDir) + "\n"
		preview += "\n  Enter: run  |  Esc: cancel\n"
		preview += "╚═══════════════════════════════════════════════════╝\n"
		output += preview
	}

	// 7. Pre-flight overlay.
	if m.showPreflight && len(m.preflightResults) > 0 {
		output += "\n" + RenderPreflight(m.preflightResults)
		output += "\n  Press any key to dismiss\n"
	}

	// 8. Diagnosis overlay.
	if m.showDiagnosis && m.diagnosisResult != nil {
		output += "\n" + m.diagnosisResult.Render()
		output += "\n  Press any key to dismiss\n"
	}

	// 9. File browser overlay.
	if m.fileBrowser != nil && m.fileBrowser.IsActive() {
		output += "\n" + m.fileBrowser.Render(m.width, m.height)
	}

	return output
}

// renderTabBar draws a Zellij-style bottom tab bar.
func (m Model) renderTabBar() string {
	var b strings.Builder

	for i, name := range tabNames {
		label := fmt.Sprintf(" %d %s ", i+1, name)

		if i == m.activeTab {
			b.WriteString(tabActiveStyle.Render(label))
		} else {
			b.WriteString(tabInactiveStyle.Render(label))
		}

		// Separator between tabs
		if i < len(tabNames)-1 {
			b.WriteString(tabBarBgStyle.Render("│"))
		}
	}

	rendered := b.String()
	barW := lipgloss.Width(rendered)
	if barW < m.width {
		rendered += tabBarBgStyle.Width(m.width - barW).Render("")
	}

	return rendered
}

// renderMigrationContent draws the Migration tab — full-width config form + progress.
func (m Model) renderMigrationContent() string {
	outerW, paneH, innerW, _ := m.paneDims()

	formContent := m.form.Render(innerW)

	if m.quickMsg != "" {
		formContent += "\n  " + m.quickMsg
	}
	if m.profileMsg != "" {
		formContent += "\n" + libvirtSuccessMsg.Render("  "+m.profileMsg)
	}
	progressSection := m.renderProgressSection(innerW)
	if progressSection != "" {
		formContent += "\n" + progressSection
	}

	formVP := m.formVP
	formVP.SetContent(formContent)

	content := formHeaderStyle.Render("Configuration") + "\n" + formVP.View()

	pane := focusedPaneStyle.
		Width(outerW).
		Height(paneH).
		Render(content)

	return pane
}

// startQueue begins sequential migration of selected VMs.
func (m Model) startQueue(vms []VsphereVMInfo) (tea.Model, tea.Cmd) {
	m.vmQueue = vms
	m.queueIdx = 0
	m.queueResults = nil
	m.queueRunning = true
	m.logView = m.logView.AppendLog("INFO",
		fmt.Sprintf("Starting queue: %d VM(s) to migrate one by one", len(vms)))

	for i, vm := range vms {
		status := "⏸ Pending"
		if i == 0 {
			status = "⏳ Starting..."
		}
		m.logView = m.logView.AppendLog("INFO", fmt.Sprintf("  [%d] %s — %s", i+1, vm.Name, status))
	}

	return m.runQueuedVM(0)
}

// runQueuedVM sets up the form for the next VM and runs migration.
func (m Model) runQueuedVM(idx int) (tea.Model, tea.Cmd) {
	vm := m.vmQueue[idx]
	m.logView = m.logView.AppendLog("INFO",
		fmt.Sprintf("━━━ VM %d/%d: %s ━━━", idx+1, len(m.vmQueue), vm.Name))

	// Set vs_vm and vm_name for vSphere migration.
	m.form.SetFieldValue("vs_vm", vm.Name)
	m.form.SetFieldValue("vm_name", vm.Name)

	m.discoverMsg = fmt.Sprintf("Migrating VM %d/%d: %s", idx+1, len(m.vmQueue), vm.Name)
	return m.runMigration()
}

// queueSummary returns a formatted summary of queue results.
func (m Model) queueSummary() string {
	success := 0
	failed := 0
	for _, r := range m.queueResults {
		if r.Success {
			success++
		} else {
			failed++
		}
	}
	return fmt.Sprintf("✅ Queue complete: %d/%d succeeded, %d failed", success, len(m.queueResults), failed)
}

// renderSplitMigration draws form (left) + logs (right) side by side.
func (m Model) renderSplitMigration() string {
	leftW, rightW, paneH, leftInnerW, rightInnerW, _ := m.splitPaneDims()

	// Left pane: config form (vSphere moved to dedicated tab).
	formContent := m.form.Render(leftInnerW)

	if m.quickMsg != "" {
		formContent += "\n  " + m.quickMsg
	}
	if m.profileMsg != "" {
		formContent += "\n" + libvirtSuccessMsg.Render("  "+m.profileMsg)
	}
	progressSection := m.renderProgressSection(leftInnerW)
	if progressSection != "" {
		formContent += "\n" + progressSection
	}

	formVP := m.formVP
	formVP.SetContent(formContent)

	leftContent := formHeaderStyle.Render("⚙ Configuration") + "\n" + formVP.View()

	leftPane := focusedPaneStyle.
		Width(leftW).
		Height(paneH).
		Render(leftContent)

	// Right pane: status + progress + queue (logs moved to dedicated Logs tab).
	var rightContent string

	rightContent += formHeaderStyle.Render("📊 Status") + "\n\n"

	// State badge.
	switch m.state {
	case StateIdle:
		rightContent += "  ● READY — Press Ctrl+R to run\n"
	case StateRunning:
		rightContent += fmt.Sprintf("  ⏳ RUNNING (PID %d)\n", m.pid)
		if m.stage != "" {
			rightContent += "  " + m.stage + "\n"
		}
	case StateCompleted:
		rightContent += "  ✅ COMPLETED\n"
	case StateFailed:
		rightContent += fmt.Sprintf("  ❌ FAILED (exit %d)\n", m.exitCode)
		if m.exitErr != "" {
			rightContent += "  " + m.exitErr + "\n"
		}
	}

	// Progress bar (export, conversion, or flattening).
	if m.exportProgress.Active {
		label := "📥 Export Progress"
		if strings.Contains(m.stage, "Flatten") || strings.Contains(m.stage, "flatten") {
			label = "⚙ Flattening Progress"
		} else if strings.Contains(m.stage, "Convert") || strings.Contains(m.stage, "convert") {
			label = "⚙ Conversion Progress"
		}
		rightContent += "\n" + formHeaderStyle.Render(label) + "\n"
		rightContent += m.exportProgress.RenderBar(rightInnerW) + "\n"
	}

	// Execution plan — shows what will happen based on current settings.
	rightContent += "\n"
	rightContent += formHeaderStyle.Render("📋 Execution Plan") + "\n\n"

	stepDone := lipgloss.NewStyle().Foreground(theme.Active.Success).Render("✔")
	stepPend := lipgloss.NewStyle().Foreground(theme.Active.Muted).Render("→")

	sourcePath := m.form.GetFieldValue("source")
	outFmt := m.form.GetFieldValue("out_format")
	if outFmt == "" {
		outFmt = "qcow2"
	}
	if sourcePath != "" {
		_, sourceLabel := detectSourceFormat(sourcePath)
		rightContent += fmt.Sprintf("  %s Input:    %s\n", stepDone, sourceLabel)
	} else {
		rightContent += fmt.Sprintf("  %s Input:    (select source)\n", stepPend)
	}
	rightContent += fmt.Sprintf("  %s Convert:  %s\n", stepPend, outFmt)

	emitXML := m.form.GetFieldBool("emit_domain_xml")
	virshDef := m.form.GetFieldBool("virsh_define")
	libTest := m.form.GetFieldBool("libvirt_test")
	deployK8s := m.form.GetFieldBool("deploy_k8s")

	if emitXML {
		rightContent += fmt.Sprintf("  %s Define:   libvirt XML\n", stepPend)
	}
	if virshDef {
		rightContent += fmt.Sprintf("  %s Register: virsh define\n", stepPend)
	}
	if libTest {
		rightContent += fmt.Sprintf("  %s Test:     boot verify\n", stepPend)
	}
	if deployK8s {
		rightContent += fmt.Sprintf("  %s Deploy:   Kubernetes\n", stepPend)
	}

	// Deploy toggles.
	rightContent += "\n"
	rightContent += formHeaderStyle.Render("🚀 Deploy Targets") + "\n\n"

	chk := func(on bool) string {
		if on {
			return lipgloss.NewStyle().Foreground(theme.Active.Success).Bold(true).Render("[✓]")
		}
		return lipgloss.NewStyle().Foreground(theme.Active.Muted).Render("[ ]")
	}

	rightContent += fmt.Sprintf("  %s  Libvirt XML     (1)\n", chk(emitXML))
	rightContent += fmt.Sprintf("  %s  virsh define    (2)\n", chk(virshDef))
	rightContent += fmt.Sprintf("  %s  Boot test       (3)\n", chk(libTest))
	rightContent += fmt.Sprintf("  %s  Kubernetes      (4)\n", chk(deployK8s))
	rightContent += "\n"

	rightContent += formHeaderStyle.Render("⌨ Shortcuts") + "\n\n"
	rightContent += "  1-4    Toggle deploy\n"
	rightContent += "  Ctrl+R Run migration\n"
	rightContent += "  Ctrl+D Discover VMs\n"
	rightContent += "  Tab    Switch tabs\n"

	// Queue status (if running).
	if m.queueRunning && len(m.vmQueue) > 0 {
		rightContent += "\n" + formHeaderStyle.Render("📦 Queue Progress") + "\n"
		for i, vm := range m.vmQueue {
			icon := "⏸"
			status := "Pending"
			if i < len(m.queueResults) {
				if m.queueResults[i].Success {
					icon = "✅"
					status = "Done"
				} else {
					icon = "❌"
					status = "Failed"
				}
			} else if i == m.queueIdx {
				icon = "⏳"
				status = "Running..."
			}
			rightContent += fmt.Sprintf("  %s %s — %s\n", icon, vm.Name, status)
		}
	}

	rightPane := blurredPaneStyle.
		Width(rightW).
		Height(paneH).
		Render(rightContent)

	return lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)
}

// renderLogsContent draws the Logs tab — full-width log viewer.
func (m Model) renderLogsContent() string {
	outerW, paneH, _, _ := m.paneDims()

	pane := focusedPaneStyle.
		Width(outerW).
		Height(paneH).
		Render(logHeaderStyle.Render("Live Logs") + "\n" + m.logView.View())

	return pane
}

// renderMigrationStatusBar draws the status bar for the Migration tab.
func (m Model) renderMigrationStatusBar() string {
	var left string

	switch m.state {
	case StateIdle:
		left = statusIdleStyle.Render("[READY]")
	case StateRunning:
		left = statusRunningStyle.Render(fmt.Sprintf("[RUNNING] PID %d", m.pid))
	case StateCompleted:
		left = statusCompletedStyle.Render("[COMPLETED]")
	case StateFailed:
		msg := fmt.Sprintf("[FAILED] exit %d", m.exitCode)
		if m.exitErr != "" {
			msg += " - " + m.exitErr
		}
		left = statusFailedStyle.Render(msg)
	}

	var hints string
	if m.state == StateCompleted {
		hints = hintKeyStyle.Render("e") + hintStyle.Render(" Export ") +
			hintKeyStyle.Render("^R") + hintStyle.Render(" Re-run ") +
			hintKeyStyle.Render("^Q") + hintStyle.Render(" Quick ") +
			hintKeyStyle.Render("?") + hintStyle.Render(" Help")
	} else if m.state == StateRunning {
		hints = hintKeyStyle.Render("Tab") + hintStyle.Render(" Switch ") +
			hintKeyStyle.Render("?") + hintStyle.Render(" Help")
	} else {
		hints = hintKeyStyle.Render("^R") + hintStyle.Render(" Run ") +
			hintKeyStyle.Render("^Q") + hintStyle.Render(" Quick ") +
			hintKeyStyle.Render("^F") + hintStyle.Render(" Preflight ") +
			hintKeyStyle.Render("^D") + hintStyle.Render(" Discover ") +
			hintKeyStyle.Render("^P") + hintStyle.Render(" Save ") +
			hintKeyStyle.Render("?") + hintStyle.Render(" Help")
	}

	return m.buildStatusBar(left, hints)
}

// renderLogsStatusBar draws the status bar for the Logs tab.
func (m Model) renderLogsStatusBar() string {
	lineCount := fmt.Sprintf("%d lines", m.logView.LineCount())
	left := logLineCountStyle.Render(lineCount)

	var stateHint string
	switch m.state {
	case StateRunning:
		stateHint = statusRunningStyle.Render(" [RUNNING]") + "  "
	case StateCompleted:
		stateHint = statusCompletedStyle.Render(" [DONE]") + "  "
	case StateFailed:
		stateHint = statusFailedStyle.Render(" [FAILED]") + "  "
	}

	hints := stateHint +
		hintKeyStyle.Render("Ctrl+R") + hintStyle.Render(": Run  ") +
		hintKeyStyle.Render("j/k") + hintStyle.Render(": Scroll  ") +
		hintKeyStyle.Render("Alt+1-5") + hintStyle.Render(": Tab  ") +
		hintKeyStyle.Render("Ctrl+Q") + hintStyle.Render(": Quit")

	return m.buildStatusBar(left, hints)
}

// buildStatusBar renders a left + right justified status bar.
func (m Model) buildStatusBar(left, right string) string {
	leftW := lipgloss.Width(left)
	rightW := lipgloss.Width(right)
	spacing := m.width - leftW - rightW - 2
	if spacing < 1 {
		spacing = 1
	}
	bar := left + lipgloss.NewStyle().Width(spacing).Render("") + right
	return statusBarStyle.Width(m.width).Render(bar)
}

// classifyLogLevel guesses a log level from a raw output line.
func classifyLogLevel(line string) string {
	upper := strings.ToUpper(line)
	switch {
	case strings.Contains(upper, "[ERROR]") || strings.Contains(upper, "ERROR:") || strings.Contains(upper, "FATAL"):
		return "ERROR"
	case strings.Contains(upper, "[WARN") || strings.Contains(upper, "WARNING:"):
		return "WARN"
	case strings.Contains(upper, "[DEBUG]") || strings.Contains(upper, "DEBUG:"):
		return "DEBUG"
	case strings.Contains(upper, "[INFO]") || strings.Contains(upper, "INFO:"):
		return "INFO"
	default:
		return "INFO"
	}
}

// parseProgress extracts progress percentage and stage from a log line.
// ExportProgress holds structured export download progress.
type ExportProgress struct {
	Percent  float64
	Current  int64
	Total    int64
	RateBps  float64
	ETASecs  int
	Active   bool
}

// RenderBar draws a progress bar like: ████████░░░░ 64%
func (ep ExportProgress) RenderBar(width int) string {
	if !ep.Active {
		return ""
	}
	barW := width - 8 // room for " 100% "
	if barW < 10 {
		barW = 10
	}
	filled := int(ep.Percent / 100 * float64(barW))
	if filled > barW {
		filled = barW
	}
	bar := strings.Repeat("█", filled) + strings.Repeat("░", barW-filled)

	// If we have byte-level details, show them.
	if ep.Total > 0 {
		curGB := float64(ep.Current) / (1024 * 1024 * 1024)
		totGB := float64(ep.Total) / (1024 * 1024 * 1024)
		rateMB := ep.RateBps / (1024 * 1024)
		etaM, etaS := ep.ETASecs/60, ep.ETASecs%60
		return fmt.Sprintf("  %s %.0f%%\n  %.1f / %.1f GB — %.1f MB/s — ETA %dm%02ds",
			bar, ep.Percent, curGB, totGB, rateMB, etaM, etaS)
	}
	// Percentage-only mode (no total known).
	return fmt.Sprintf("  %s %.0f%%", bar, ep.Percent)
}

func (m *Model) parseProgress(line string) {
	// Parse structured [PROGRESS] pct|current|total|rate|eta from Python monitor.
	// The line may be prefixed by the logger timestamp, e.g. "15:18:49 ... [PROGRESS] 5.8|..."
	if idx := strings.Index(line, "[PROGRESS] "); idx >= 0 {
		parts := strings.Split(line[idx+len("[PROGRESS] "):], "|")
		if len(parts) >= 5 {
			pct, _ := strconv.ParseFloat(parts[0], 64)
			cur, _ := strconv.ParseInt(parts[1], 10, 64)
			tot, _ := strconv.ParseInt(parts[2], 10, 64)
			rate, _ := strconv.ParseFloat(parts[3], 64)
			eta, _ := strconv.Atoi(parts[4])
			m.exportProgress = ExportProgress{
				Percent: pct, Current: cur, Total: tot,
				RateBps: rate, ETASecs: eta, Active: true,
			}
			m.progress = pct
		}
		return
	}

	// Parse human-readable progress: 📥 X/Y MB (Z%) — R MB/s — ETA ...
	if strings.HasPrefix(line, "📥 ") {
		return // already handled by [PROGRESS] line
	}

	// Parse "Total disk size: X.X GB" to set total for progress tracking.
	if strings.Contains(line, "Total disk size:") {
		if idx := strings.Index(line, "Total disk size:"); idx >= 0 {
			rest := strings.TrimSpace(line[idx+16:])
			rest = strings.TrimSuffix(rest, " GB")
			if gb, err := strconv.ParseFloat(rest, 64); err == nil {
				m.exportProgress.Total = int64(gb * 1024 * 1024 * 1024)
				m.exportProgress.Active = true
			}
		}
	}

	if match := reProgress.FindStringSubmatch(line); len(match) > 1 {
		if v, err := strconv.ParseFloat(match[1], 64); err == nil {
			m.progress = v
			m.exportProgress.Percent = v
			m.exportProgress.Active = true
			// Set stage from context.
			if strings.Contains(line, "Flattening") {
				m.stage = "Flattening"
			} else if strings.Contains(line, "Conversion") {
				m.stage = "Converting"
			}
		}
	}
	// Detect conversion/flatten start from log lines.
	if strings.Contains(line, "Converting:") && strings.Contains(line, "->") {
		m.stage = "Converting"
	}
	if match := reDiskStage.FindStringSubmatch(line); len(match) > 1 {
		m.stage = "Converting: " + strings.TrimSpace(match[1])
	}
	if strings.Contains(line, "Conversion complete") || strings.Contains(line, "conversion complete") ||
		strings.Contains(line, "qemu_convert_complete") {
		m.stage = "Complete"
		m.progress = 100
		m.exportProgress.Active = false
	}
}

// renderProgressSection draws the progress bar area for the migration tab.
func (m Model) renderProgressSection(width int) string {
	if m.state == StateIdle {
		return ""
	}

	var b strings.Builder
	divider := strings.Repeat("─", width)
	b.WriteString(progressDividerStyle.Render(divider))
	b.WriteString("\n")

	if m.state == StateCompleted {
		b.WriteString(statusCompletedStyle.Render("  ✓ Migration completed successfully"))
		b.WriteString("\n")
		if m.exporting {
			b.WriteString(statusRunningStyle.Render("  Exporting to Libvirt..."))
		} else if m.exportMsg != "" {
			if strings.Contains(m.exportMsg, "failed") {
				b.WriteString("  " + statusFailedStyle.Render(m.exportMsg))
			} else {
				b.WriteString("  " + statusCompletedStyle.Render(m.exportMsg))
			}
		} else {
			b.WriteString("  " + hintKeyStyle.Render("[E]") + hintStyle.Render("xport to Libvirt") + "    " +
				hintKeyStyle.Render("[F2]") + hintStyle.Render(" View Logs"))
		}
		return b.String()
	}

	if m.state == StateFailed {
		msg := fmt.Sprintf("  ✗ Migration failed (exit %d)", m.exitCode)
		if m.exitErr != "" {
			msg += ": " + m.exitErr
		}
		b.WriteString(statusFailedStyle.Render(msg))
		return b.String()
	}

	// StateRunning — show stage + progress bar.
	if m.stage != "" {
		b.WriteString(progressStageStyle.Render(fmt.Sprintf("  Stage: %s", m.stage)))
		b.WriteString("\n")
	}

	barWidth := width - 10 // space for "  [" + "] XXX%"
	if barWidth < 10 {
		barWidth = 10
	}
	filled := int(m.progress / 100.0 * float64(barWidth))
	if filled > barWidth {
		filled = barWidth
	}
	empty := barWidth - filled

	bar := fmt.Sprintf("  [%s%s] %3.0f%%",
		strings.Repeat("█", filled),
		strings.Repeat("░", empty),
		m.progress)
	b.WriteString(progressBarStyle.Render(bar))

	return b.String()
}

// ─── Styles ──────────────────────────────────────────────────────────────────

var (
	// Title bar.
	titleBarStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#FFFFFF")).
			Background(theme.Coral).
			Padding(0, 1)

	// Tab bar — Zellij-inspired with powerline separators.
	tabActiveStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#FFFFFF")).
			Background(theme.Orange).
			Padding(0, 1)

	tabInactiveStyle = lipgloss.NewStyle().
				Foreground(theme.CoralLight).
				Background(theme.BgDark)

	tabSepToActiveStyle = lipgloss.NewStyle().
				Foreground(theme.BgDark).
				Background(theme.Orange)

	tabSepFromActiveStyle = lipgloss.NewStyle().
				Foreground(theme.Orange).
				Background(theme.BgDark)

	tabSepInactiveStyle = lipgloss.NewStyle().
				Foreground(theme.Dim).
				Background(theme.BgDark)

	tabBarBgStyle = lipgloss.NewStyle().
			Background(theme.BgDark)

	// Pane borders.
	focusedPaneStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Orange).
				Padding(0, 1)

	blurredPaneStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Dim).
				Padding(0, 1)

	// Pane headers.
	formHeaderStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(theme.Orange).
			MarginBottom(1)

	logHeaderStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(theme.Cyan).
			MarginBottom(1)

	// Status bar.
	statusBarStyle = lipgloss.NewStyle().
			Foreground(theme.CoralLight).
			Background(theme.BgDark).
			Padding(0, 1)

	statusIdleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(theme.Cyan)

	statusRunningStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Green)

	statusCompletedStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Green)

	statusFailedStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Red)

	logLineCountStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Cyan)

	hintKeyStyle = lipgloss.NewStyle().
			Foreground(theme.OrangeLight).
			Bold(true)

	hintStyle = lipgloss.NewStyle().
			Foreground(theme.Dim)

	progressDividerStyle = lipgloss.NewStyle().
				Foreground(theme.Dim)

	progressStageStyle = lipgloss.NewStyle().
				Foreground(theme.CoralLight)

	progressBarStyle = lipgloss.NewStyle().
				Foreground(theme.Green)
)
