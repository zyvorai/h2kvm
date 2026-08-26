// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/theme"
)

// Auto-refresh interval for the VM list.
const vmRefreshInterval = 5 * time.Second

// VMListMsg carries the result of a VM list refresh.
type VMListMsg struct {
	VMs []VMInfo
	Err error
}

// VMActionMsg carries the result of a VM action (start, shutdown, etc.).
type VMActionMsg struct {
	Action string
	VM     string
	Err    error
}

// vmTickMsg triggers periodic VM list refresh.
type vmTickMsg struct{}

// OpenConsoleMsg requests opening an embedded screen console for a VM.
type OpenConsoleMsg struct {
	VMName  string
	Host    string
	Port    int
	GfxType string
}

// OpenWebConsoleMsg requests opening a noVNC web console for a VM.
type OpenWebConsoleMsg struct {
	VMName string
	Host   string
	Port   int
}

// SnapshotActionMsg carries the result of a snapshot action.
type SnapshotActionMsg struct {
	Action string
	VM     string
	Err    error
}

// LibvirtModel is the Bubble Tea model for the Libvirt VM Manager tab.
type LibvirtModel struct {
	vms        []VMInfo
	snapshots  []SnapshotInfo // snapshots for selected VM
	selected   int
	loading    bool
	message    string
	confirming bool // delete confirmation prompt active
	width      int
	height     int
	focusPane  int // 0 = list, 1 = details

	program *tea.Program
}

// NewLibvirtModel creates a new Libvirt VM Manager tab model.
func NewLibvirtModel() LibvirtModel {
	return LibvirtModel{
		loading: true,
	}
}

// Init returns the initial commands: fetch VM list and start ticker.
func (m LibvirtModel) Init() tea.Cmd {
	return tea.Batch(fetchVMList, tickVM())
}

// fetchVMList runs ListVMs in a goroutine and returns the result.
func fetchVMList() tea.Msg {
	vms, err := ListVMs()
	return VMListMsg{VMs: vms, Err: err}
}

// tickVM returns a command that fires a vmTickMsg after the refresh interval.
func tickVM() tea.Cmd {
	return tea.Tick(vmRefreshInterval, func(_ time.Time) tea.Msg {
		return vmTickMsg{}
	})
}

// Update handles messages for the Libvirt tab.
func (m LibvirtModel) Update(msg tea.Msg) (LibvirtModel, tea.Cmd) {
	switch msg := msg.(type) {
	case VMListMsg:
		m.loading = false
		if msg.Err != nil {
			m.message = "Error: " + msg.Err.Error()
		} else {
			m.vms = msg.VMs
			if m.selected >= len(m.vms) {
				m.selected = len(m.vms) - 1
			}
			if m.selected < 0 {
				m.selected = 0
			}
		}
		return m, nil

	case VMActionMsg:
		if msg.Err != nil {
			m.message = fmt.Sprintf("%s failed: %s", msg.Action, msg.Err.Error())
		} else {
			m.message = fmt.Sprintf("%s: %s", msg.Action, msg.VM)
		}
		// Refresh after action.
		return m, fetchVMList

	case SnapshotActionMsg:
		if msg.Err != nil {
			m.message = fmt.Sprintf("Snapshot %s failed: %s", msg.Action, msg.Err.Error())
		} else {
			m.message = fmt.Sprintf("Snapshot %s: %s", msg.Action, msg.VM)
		}
		// Refresh snapshots.
		m.refreshSnapshots()
		return m, nil

	case vmTickMsg:
		return m, tea.Batch(fetchVMList, tickVM())

	case tea.KeyMsg:
		return m.handleKey(msg)
	}

	return m, nil
}

// handleKey processes keyboard input for the Libvirt tab.
func (m LibvirtModel) handleKey(msg tea.KeyMsg) (LibvirtModel, tea.Cmd) {
	key := msg.String()

	// Handle delete confirmation.
	if m.confirming {
		switch key {
		case "y", "Y":
			m.confirming = false
			if m.selected >= 0 && m.selected < len(m.vms) {
				vm := m.vms[m.selected]
				m.message = "Deleting " + vm.Name + "..."
				return m, deleteVMCmd(vm.Name)
			}
		default:
			m.confirming = false
			m.message = "Delete cancelled"
		}
		return m, nil
	}

	switch key {
	case "up", "k":
		if m.selected > 0 {
			m.selected--
			m.refreshSnapshots()
		}
	case "down", "j":
		if m.selected < len(m.vms)-1 {
			m.selected++
			m.refreshSnapshots()
		}
	case "p":
		m.focusPane = (m.focusPane + 1) % 2
	case "s":
		if m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			m.message = "Starting " + vm.Name + "..."
			return m, startVMCmd(vm.Name)
		}
	case "h":
		if m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			m.message = "Shutting down " + vm.Name + "..."
			return m, shutdownVMCmd(vm.Name)
		}
	case "d":
		if m.selected >= 0 && m.selected < len(m.vms) {
			m.confirming = true
			m.message = ""
		}
	case "c":
		if m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			if vm.State != "running" {
				m.message = "VM must be running to open console"
			} else {
				listen := vm.Graphics.Listen
				if listen == "" || listen == "0.0.0.0" {
					listen = "127.0.0.1"
				}
				// Send message to open console in dedicated tab.
				return m, func() tea.Msg {
					return OpenConsoleMsg{
						VMName:  vm.Name,
						Host:    listen,
						Port:    vm.Graphics.Port,
						GfxType: vm.Graphics.Type,
					}
				}
			}
		}
	case "w":
		if m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			if vm.State != "running" {
				m.message = "VM must be running for web console"
			} else if vm.Graphics.Type != "vnc" {
				m.message = "Web console requires VNC display (current: " + vm.Graphics.Type + ")"
			} else if vm.Graphics.Port <= 0 {
				m.message = "VNC port not available (autoport, VM may need restart)"
			} else {
				listen := vm.Graphics.Listen
				if listen == "" || listen == "0.0.0.0" {
					listen = "127.0.0.1"
				}
				return m, func() tea.Msg {
					return OpenWebConsoleMsg{VMName: vm.Name, Host: listen, Port: vm.Graphics.Port}
				}
			}
		}
	case "n":
		if m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			snapName := fmt.Sprintf("snap-%d", time.Now().Unix())
			m.message = "Creating snapshot " + snapName + "..."
			return m, createSnapshotCmd(vm.Name, snapName)
		}
	case "r":
		m.loading = true
		m.message = "Refreshing..."
		return m, fetchVMList
	}

	return m, nil
}

// refreshSnapshots fetches snapshots for the currently selected VM.
func (m *LibvirtModel) refreshSnapshots() {
	if m.selected >= 0 && m.selected < len(m.vms) {
		m.snapshots, _ = ListSnapshots(m.vms[m.selected].Name)
	} else {
		m.snapshots = nil
	}
}

func createSnapshotCmd(vmName, snapName string) tea.Cmd {
	return func() tea.Msg {
		err := CreateSnapshot(vmName, snapName, "Created by zkvm")
		return SnapshotActionMsg{Action: "created", VM: vmName + "/" + snapName, Err: err}
	}
}

// VM action commands.
func startVMCmd(name string) tea.Cmd {
	return func() tea.Msg {
		fixes, _ := PreflightVM(name)
		out, err := runVirsh("start", name)
		if err != nil {
			return VMActionMsg{Action: "Started", VM: name,
				Err: fmt.Errorf("%s", out)}
		}
		action := "Started"
		if len(fixes) > 0 {
			action = "Started (auto-fixed: " + strings.Join(fixes, ", ") + ")"
		}
		return VMActionMsg{Action: action, VM: name, Err: nil}
	}
}

func shutdownVMCmd(name string) tea.Cmd {
	return func() tea.Msg {
		err := ShutdownVM(name)
		return VMActionMsg{Action: "Shutdown", VM: name, Err: err}
	}
}

func deleteVMCmd(name string) tea.Cmd {
	return func() tea.Msg {
		err := DeleteVM(name)
		return VMActionMsg{Action: "Deleted", VM: name, Err: err}
	}
}

// SetProgram stores the tea.Program reference for VNC console.
func (m *LibvirtModel) SetProgram(p *tea.Program) {
	m.program = p
}

// SetSize updates the layout dimensions for the Libvirt tab.
func (m *LibvirtModel) SetSize(width, height int) {
	m.width = width
	m.height = height
}

// View renders the Libvirt VM Manager tab.
func (m LibvirtModel) View(leftOuterW, rightOuterW, paneH int) string {
	// Build left pane: VM list.
	leftStyle := libvirtBlurredPane
	rightStyle := libvirtBlurredPane
	if m.focusPane == 0 {
		leftStyle = libvirtFocusedPane
	} else {
		rightStyle = libvirtFocusedPane
	}

	listContent := m.renderVMList(leftOuterW - paneHPad)
	leftPane := leftStyle.
		Width(leftOuterW).
		Height(paneH).
		Render(libvirtHeaderStyle.Render("VM List") + "\n" + listContent)

	detailContent := m.renderVMDetails(rightOuterW - paneHPad)
	rightPane := rightStyle.
		Width(rightOuterW).
		Height(paneH).
		Render(libvirtDetailHeaderStyle.Render("VM Details") + "\n" + detailContent)

	return lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)
}

// renderVMList draws the VM list for the left pane.
func (m LibvirtModel) renderVMList(width int) string {
	if m.loading && len(m.vms) == 0 {
		return libvirtDimStyle.Render("  Loading VMs...")
	}

	if len(m.vms) == 0 {
		return libvirtDimStyle.Render("  No VMs found")
	}

	var b strings.Builder
	for i, vm := range m.vms {
		indicator := "  "
		if i == m.selected {
			indicator = libvirtSelectedIndicator.Render("● ")
		}

		stateStr := m.stateIndicator(vm.State)
		name := vm.Name

		// Truncate long names.
		maxName := width - 12
		if maxName < 10 {
			maxName = 10
		}
		if len(name) > maxName {
			name = name[:maxName-1] + "…"
		}

		line := fmt.Sprintf("%s%-*s %s", indicator, maxName, name, stateStr)
		if i == m.selected {
			b.WriteString(libvirtSelectedLine.Render(line))
		} else {
			b.WriteString(line)
		}
		b.WriteString("\n")
	}
	return b.String()
}

// stateIndicator returns a colored state string.
func (m LibvirtModel) stateIndicator(state string) string {
	switch state {
	case "running":
		return libvirtStateRunning.Render("running")
	case "paused":
		return libvirtStatePaused.Render("paused")
	case "shut off":
		return libvirtStateShutoff.Render("shut off")
	default:
		return libvirtDimStyle.Render(state)
	}
}

// renderVMDetails draws the detail pane for the selected VM.
func (m LibvirtModel) renderVMDetails(width int) string {
	if len(m.vms) == 0 || m.selected < 0 || m.selected >= len(m.vms) {
		return libvirtDimStyle.Render("  No VM selected")
	}

	vm := m.vms[m.selected]
	var b strings.Builder

	// Detail fields.
	detailLabel := libvirtDetailLabel
	detailValue := libvirtDetailValue

	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Name:"), detailValue.Render(vm.Name)))
	b.WriteString(fmt.Sprintf("  %s %s\n", detailLabel.Render("State:"), m.stateIndicator(vm.State)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("UUID:"), detailValue.Render(vm.UUID)))
	b.WriteString(fmt.Sprintf("  %s %s\n", detailLabel.Render("vCPUs:"), detailValue.Render(fmt.Sprintf("%d", vm.CPUs))))
	b.WriteString(fmt.Sprintf("  %s %s\n", detailLabel.Render("Memory:"), detailValue.Render(fmt.Sprintf("%d MiB", vm.MemoryMiB))))

	// Disk paths.
	if len(vm.DiskPaths) > 0 {
		for i, dp := range vm.DiskPaths {
			if i == 0 {
				b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Disk:"), detailValue.Render(dp)))
			} else {
				b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("     "), detailValue.Render(dp)))
			}
		}
	} else {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Disk:"), libvirtDimStyle.Render("none")))
	}

	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Auto:"), detailValue.Render(vm.Autostart)))

	// Display graphics info.
	switch vm.Graphics.Type {
	case "vnc":
		portInfo := "autoport"
		if vm.Graphics.Port > 0 {
			portInfo = fmt.Sprintf(":%d", vm.Graphics.Port)
		}
		listen := vm.Graphics.Listen
		if listen == "" {
			listen = "127.0.0.1"
		}
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Display:"),
			detailValue.Render(fmt.Sprintf("VNC %s (%s)", portInfo, listen))))
	case "spice":
		portInfo := "autoport"
		if vm.Graphics.Port > 0 {
			portInfo = fmt.Sprintf(":%d", vm.Graphics.Port)
		}
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Display:"),
			detailValue.Render(fmt.Sprintf("SPICE %s", portInfo))))
	default:
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Display:"),
			libvirtDimStyle.Render("none")))
	}

	// Snapshots.
	if len(m.snapshots) > 0 {
		b.WriteString(fmt.Sprintf("  %s  ", detailLabel.Render("Snaps:")))
		for i, snap := range m.snapshots {
			if i > 2 {
				b.WriteString(libvirtDimStyle.Render(fmt.Sprintf(" +%d more", len(m.snapshots)-3)))
				break
			}
			if i > 0 {
				b.WriteString(", ")
			}
			name := snap.Name
			if snap.Current {
				name = "*" + name
			}
			b.WriteString(detailValue.Render(name))
		}
		b.WriteString("\n")
	}

	// Actions box.
	b.WriteString("\n")
	actionsBox := libvirtActionsBoxStyle.Width(width - 4).Render(
		libvirtActionsTitle.Render("Actions") + "\n" +
			"  " + libvirtActionKey.Render("[S]") + libvirtDimStyle.Render("tart") + "  " +
			libvirtActionKey.Render("s[H]") + libvirtDimStyle.Render("utdown") + "  " +
			libvirtActionKey.Render("[D]") + libvirtDimStyle.Render("elete") + "\n" +
			"  " + libvirtActionKey.Render("[C]") + libvirtDimStyle.Render("onsole") + "  " +
			libvirtActionKey.Render("[W]") + libvirtDimStyle.Render("eb console") + "  " +
			libvirtActionKey.Render("[N]") + libvirtDimStyle.Render("ew snap") + "\n" +
			"  " + libvirtActionKey.Render("[R]") + libvirtDimStyle.Render("efresh"))

	b.WriteString(actionsBox)

	// Confirmation prompt.
	if m.confirming {
		b.WriteString("\n\n")
		b.WriteString(libvirtConfirmStyle.Render(
			fmt.Sprintf("  Delete \"%s\" and all its storage? [y/N] ", vm.Name)))
	}

	// Action result message.
	if m.message != "" && !m.confirming {
		b.WriteString("\n\n")
		if strings.Contains(m.message, "failed") || strings.Contains(m.message, "Error") {
			b.WriteString("  " + libvirtErrorMsg.Render(m.message))
		} else {
			b.WriteString("  " + libvirtSuccessMsg.Render(m.message))
		}
	}

	return b.String()
}

// StatusBar returns the status bar content for the Libvirt tab.
func (m LibvirtModel) StatusBar(width int) string {
	vmCount := fmt.Sprintf("%d VMs", len(m.vms))
	left := libvirtStatusCount.Render(vmCount)

	hints := hintKeyStyle.Render("s") + hintStyle.Render(": Start  ") +
		hintKeyStyle.Render("h") + hintStyle.Render(": Shutdown  ") +
		hintKeyStyle.Render("d") + hintStyle.Render(": Delete  ") +
		hintKeyStyle.Render("c") + hintStyle.Render(": Console  ") +
		hintKeyStyle.Render("w") + hintStyle.Render(": Web  ") +
		hintKeyStyle.Render("n") + hintStyle.Render(": Snap  ") +
		hintKeyStyle.Render("r") + hintStyle.Render(": Refresh  ") +
		hintKeyStyle.Render("Alt+1-6") + hintStyle.Render(": Tab")

	leftW := lipgloss.Width(left)
	rightW := lipgloss.Width(hints)
	spacing := width - leftW - rightW - 2
	if spacing < 1 {
		spacing = 1
	}

	bar := left + lipgloss.NewStyle().Width(spacing).Render("") + hints
	return statusBarStyle.Width(width).Render(bar)
}

// Styles for the Libvirt VM Manager tab.
var (
	libvirtFocusedPane = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Orange).
				Padding(0, 1)

	libvirtBlurredPane = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Dim).
				Padding(0, 1)

	libvirtHeaderStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Orange).
				MarginBottom(1)

	libvirtDetailHeaderStyle = lipgloss.NewStyle().
					Bold(true).
					Foreground(theme.Cyan).
					MarginBottom(1)

	libvirtSelectedIndicator = lipgloss.NewStyle().
					Foreground(theme.Orange).
					Bold(true)

	libvirtSelectedLine = lipgloss.NewStyle().
				Foreground(theme.White).
				Bold(true)

	libvirtStateRunning = lipgloss.NewStyle().
				Foreground(theme.Green).
				Bold(true)

	libvirtStatePaused = lipgloss.NewStyle().
				Foreground(theme.Yellow).
				Bold(true)

	libvirtStateShutoff = lipgloss.NewStyle().
				Foreground(theme.Red)

	libvirtDimStyle = lipgloss.NewStyle().
			Foreground(theme.Dim)

	libvirtDetailLabel = lipgloss.NewStyle().
				Foreground(theme.CoralLight).
				Width(8)

	libvirtDetailValue = lipgloss.NewStyle().
				Foreground(theme.White)

	libvirtActionsBoxStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Dim).
				Padding(0, 1)

	libvirtActionsTitle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Orange)

	libvirtActionKey = lipgloss.NewStyle().
			Foreground(theme.OrangeLight).
			Bold(true)

	libvirtConfirmStyle = lipgloss.NewStyle().
				Foreground(theme.Yellow).
				Bold(true)

	libvirtErrorMsg = lipgloss.NewStyle().
			Foreground(theme.Red)

	libvirtSuccessMsg = lipgloss.NewStyle().
				Foreground(theme.Green)

	libvirtStatusCount = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Cyan)

)
