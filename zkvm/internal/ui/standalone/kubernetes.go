// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"context"
	"fmt"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/theme"
)

// Refresh interval for KubeVirt VMs.
const kubeRefreshInterval = 10 * time.Second

// --- Messages ---

// KubeVMListMsg carries the result of a KubeVirt VM list refresh.
type KubeVMListMsg struct {
	VMs        []KubeVirtVM
	Contexts   []KubeContext
	Status     KubeVirtStatus
	PVCs       []PVCInfo
	Migrations []MigrationInfo
	Err        error
}

// KubeActionMsg carries the result of a KubeVirt action.
type KubeActionMsg struct {
	Action string
	VM     string
	Err    error
}

// KubeSSHDoneMsg is sent when an SSH session finishes.
type KubeSSHDoneMsg struct {
	Err error
}

type kubeTickMsg struct{}

// KubeVirt tab sub-views.
const (
	kubeViewVMs        = 0
	kubeViewPVCs       = 1
	kubeViewMigrations = 2
)

// Form overlay types.
const (
	kubeFormCreateVM  = 0
	kubeFormUploadPVC = 1
)

// kubeFormField represents a single field in a form overlay.
type kubeFormField struct {
	Label       string
	Value       string
	Placeholder string
}

// KubernetesModel is the Bubble Tea model for the Kubernetes/KubeVirt tab.
type KubernetesModel struct {
	contexts   []KubeContext
	vms        []KubeVirtVM
	allVMs     []KubeVirtVM // unfiltered VMs from API
	pvcs       []PVCInfo
	allPVCs    []PVCInfo // unfiltered PVCs from API
	migrations []MigrationInfo
	status     KubeVirtStatus
	selected   int
	loading    bool
	message    string
	confirming bool
	client     *KubeClient // nil when kubeconfig unavailable
	subView    int         // kubeViewVMs, kubeViewPVCs, or kubeViewMigrations
	focusPane  int         // 0 = list, 1 = details
	width      int
	height     int

	// Namespace filter.
	namespace    string   // "all" or specific namespace
	namespaceIdx int      // index into namespaces slice
	namespaces   []string // ["all", "ns1", "ns2", ...]

	// Form overlay.
	formOverlay  bool
	formType     int
	formFields   []kubeFormField
	formFocusIdx int
	formEditing  bool

	// SSH port-forward stop channel.
	sshStopChan chan struct{}
}

// NewKubernetesModel creates a new Kubernetes tab model.
func NewKubernetesModel() KubernetesModel {
	var kc *KubeClient
	var initMsg string
	if KubeConfigAvailable() {
		var err error
		kc, err = NewKubeClient("")
		if err != nil {
			initMsg = "Kubeconfig found but connection failed: " + err.Error()
		}
	}
	return KubernetesModel{
		loading:   true,
		client:    kc,
		message:   initMsg,
		namespace: "all",
	}
}

// Init returns initial commands for the Kubernetes tab.
func (m KubernetesModel) Init() tea.Cmd {
	if m.client == nil {
		return nil
	}
	return tea.Batch(m.fetchKubeDataCmd(), tickKube())
}

func (m KubernetesModel) fetchKubeDataCmd() tea.Cmd {
	kc := m.client
	return func() tea.Msg {
		ctx := context.Background()
		contexts := kc.ListContexts()
		status := kc.GetKubeVirtStatus(ctx)

		var vms []KubeVirtVM
		var pvcs []PVCInfo
		var migrations []MigrationInfo
		var err error

		if status.Installed {
			vms, err = kc.ListKubeVirtVMs(ctx, "all")
			migrations, _ = kc.ListMigrations(ctx, "all")

			// Cross-reference: mark VMs that have active migrations.
			activeMigVMs := make(map[string]bool)
			for _, mig := range migrations {
				if mig.Phase == "Running" || mig.Phase == "Scheduling" || mig.Phase == "Pending" || mig.Phase == "PreparingTarget" {
					activeMigVMs[mig.Namespace+"/"+mig.VMName] = true
				}
			}
			for i := range vms {
				if activeMigVMs[vms[i].Namespace+"/"+vms[i].Name] {
					vms[i].Migrating = true
				}
			}
		}
		pvcs, _ = kc.ListPVCs(ctx, "all")

		return KubeVMListMsg{
			VMs:        vms,
			Contexts:   contexts,
			Status:     status,
			PVCs:       pvcs,
			Migrations: migrations,
			Err:        err,
		}
	}
}

func tickKube() tea.Cmd {
	return tea.Tick(kubeRefreshInterval, func(_ time.Time) tea.Msg {
		return kubeTickMsg{}
	})
}

// Update handles messages for the Kubernetes tab.
func (m KubernetesModel) Update(msg tea.Msg) (KubernetesModel, tea.Cmd) {
	switch msg := msg.(type) {
	case KubeVMListMsg:
		m.loading = false
		if msg.Err != nil {
			m.message = "Error: " + msg.Err.Error()
		} else {
			m.contexts = msg.Contexts
			m.allVMs = msg.VMs
			m.allPVCs = msg.PVCs
			m.migrations = msg.Migrations
			m.status = msg.Status

			// Extract unique namespaces from VMs and PVCs.
			nsSet := make(map[string]bool)
			for _, vm := range msg.VMs {
				if vm.Namespace != "" {
					nsSet[vm.Namespace] = true
				}
			}
			for _, pvc := range msg.PVCs {
				if pvc.Namespace != "" {
					nsSet[pvc.Namespace] = true
				}
			}
			nsList := []string{"all"}
			for ns := range nsSet {
				nsList = append(nsList, ns)
			}
			sort.Strings(nsList[1:])
			m.namespaces = nsList

			// Apply namespace filter.
			m.applyNamespaceFilter()

			if m.subView == kubeViewVMs && m.selected >= len(m.vms) {
				m.selected = max(0, len(m.vms)-1)
			}
			if m.subView == kubeViewPVCs && m.selected >= len(m.pvcs) {
				m.selected = max(0, len(m.pvcs)-1)
			}
			if m.subView == kubeViewMigrations && m.selected >= len(m.migrations) {
				m.selected = max(0, len(m.migrations)-1)
			}
		}
		return m, nil

	case KubeActionMsg:
		if msg.Err != nil {
			m.message = fmt.Sprintf("%s failed: %s", msg.Action, msg.Err.Error())
		} else {
			m.message = fmt.Sprintf("%s: %s", msg.Action, msg.VM)
		}
		return m, m.fetchKubeDataCmd()

	case KubeSSHDoneMsg:
		if msg.Err != nil {
			m.message = "SSH session ended: " + msg.Err.Error()
		} else {
			m.message = "SSH session ended"
		}
		return m, m.fetchKubeDataCmd()

	case kubeTickMsg:
		if m.client != nil {
			return m, tea.Batch(m.fetchKubeDataCmd(), tickKube())
		}
		return m, tickKube()

	case tea.KeyMsg:
		return m.handleKey(msg)
	}

	return m, nil
}

func (m *KubernetesModel) applyNamespaceFilter() {
	if m.namespace == "all" {
		m.vms = m.allVMs
		m.pvcs = m.allPVCs
	} else {
		m.vms = nil
		for _, vm := range m.allVMs {
			if vm.Namespace == m.namespace {
				m.vms = append(m.vms, vm)
			}
		}
		m.pvcs = nil
		for _, pvc := range m.allPVCs {
			if pvc.Namespace == m.namespace {
				m.pvcs = append(m.pvcs, pvc)
			}
		}
	}
}

func (m KubernetesModel) handleKey(msg tea.KeyMsg) (KubernetesModel, tea.Cmd) {
	key := msg.String()

	if m.client == nil {
		return m, nil
	}

	// Form overlay intercepts all keys when visible.
	if m.formOverlay {
		return m.handleFormOverlayKey(msg)
	}

	// Delete confirmation.
	if m.confirming {
		switch key {
		case "y", "Y":
			m.confirming = false
			if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
				vm := m.vms[m.selected]
				m.message = "Deleting " + vm.Name + "..."
				return m, kubeDeleteVMCmd(m.client, vm.Name, vm.Namespace)
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
		}
	case "down", "j":
		listLen := m.currentListLen()
		if m.selected < listLen-1 {
			m.selected++
		}
	case "p":
		m.focusPane = (m.focusPane + 1) % 2
	case "1":
		m.subView = kubeViewVMs
		m.selected = 0
	case "2":
		m.subView = kubeViewPVCs
		m.selected = 0
	case "3":
		m.subView = kubeViewMigrations
		m.selected = 0

	// Context switcher.
	case "n":
		if len(m.contexts) > 1 {
			curIdx := 0
			for i, ctx := range m.contexts {
				if ctx.Current {
					curIdx = i
					break
				}
			}
			nextIdx := (curIdx + 1) % len(m.contexts)
			nextName := m.contexts[nextIdx].Name
			m.message = "Switching to context: " + nextName + "..."
			m.loading = true
			return m, kubeSwitchContextCmd(m.client, nextName)
		} else {
			m.message = "Only one context available"
		}

	// Namespace filter.
	case "a":
		if len(m.namespaces) > 0 {
			m.namespaceIdx = (m.namespaceIdx + 1) % len(m.namespaces)
			m.namespace = m.namespaces[m.namespaceIdx]
			m.applyNamespaceFilter()
			m.selected = 0
			if m.namespace == "all" {
				m.message = "Showing all namespaces"
			} else {
				m.message = "Filtering: " + m.namespace
			}
		}

	// VM creation wizard.
	case "w":
		if m.subView == kubeViewVMs {
			m.openCreateVMForm()
		}

	// SSH into VM.
	case "e":
		if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			if vm.Status != "Running" {
				m.message = "VM must be running for SSH"
			} else {
				m.message = "Connecting SSH to " + vm.Name + "..."
				return m, m.kubeSSHCmd(vm.Name, vm.Namespace)
			}
		}

	// PVC upload.
	case "u":
		if m.subView == kubeViewPVCs {
			m.openUploadPVCForm()
		}

	case "s":
		if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			m.message = "Starting " + vm.Name + "..."
			return m, kubeStartVMCmd(vm.Name, vm.Namespace)
		}
	case "x":
		if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			m.message = "Stopping " + vm.Name + "..."
			return m, kubeStopVMCmd(vm.Name, vm.Namespace)
		}
	case "t":
		if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			m.message = "Restarting " + vm.Name + "..."
			return m, kubeRestartVMCmd(vm.Name, vm.Namespace)
		}
	case "d":
		if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
			m.confirming = true
			m.message = ""
		}
	case "c":
		if m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
			vm := m.vms[m.selected]
			if vm.Status != "Running" {
				m.message = "VM must be running for console"
			} else {
				OpenKubeVirtConsole(vm.Name, vm.Namespace)
				m.message = "Opened console for " + vm.Name
			}
		}
	case "r":
		m.loading = true
		m.message = "Refreshing..."
		return m, m.fetchKubeDataCmd()
	}

	return m, nil
}

func (m KubernetesModel) currentListLen() int {
	switch m.subView {
	case kubeViewPVCs:
		return len(m.pvcs)
	case kubeViewMigrations:
		return len(m.migrations)
	default:
		return len(m.vms)
	}
}

// --- Form overlay ---

func (m *KubernetesModel) openCreateVMForm() {
	ns := "default"
	if m.namespace != "all" {
		ns = m.namespace
	}
	m.formOverlay = true
	m.formType = kubeFormCreateVM
	m.formFocusIdx = 0
	m.formEditing = false
	m.formFields = []kubeFormField{
		{Label: "Name", Value: "", Placeholder: "my-vm"},
		{Label: "Namespace", Value: ns, Placeholder: "default"},
		{Label: "Image", Value: "", Placeholder: "quay.io/containerdisks/fedora:latest"},
		{Label: "CPUs", Value: "2", Placeholder: "2"},
		{Label: "Memory", Value: "2Gi", Placeholder: "2Gi"},
	}
}

func (m *KubernetesModel) openUploadPVCForm() {
	ns := "default"
	if m.namespace != "all" {
		ns = m.namespace
	}
	m.formOverlay = true
	m.formType = kubeFormUploadPVC
	m.formFocusIdx = 0
	m.formEditing = false
	m.formFields = []kubeFormField{
		{Label: "Name", Value: "", Placeholder: "my-disk"},
		{Label: "Namespace", Value: ns, Placeholder: "default"},
		{Label: "Size", Value: "10Gi", Placeholder: "10Gi"},
		{Label: "Image Path", Value: "", Placeholder: "/path/to/disk.qcow2"},
	}
}

func (m KubernetesModel) handleFormOverlayKey(msg tea.KeyMsg) (KubernetesModel, tea.Cmd) {
	key := msg.String()

	if m.formEditing {
		switch key {
		case "esc", "enter":
			m.formEditing = false
		case "backspace":
			f := &m.formFields[m.formFocusIdx]
			if len(f.Value) > 0 {
				f.Value = f.Value[:len(f.Value)-1]
			}
		default:
			if len(msg.Runes) > 0 {
				f := &m.formFields[m.formFocusIdx]
				for _, r := range msg.Runes {
					f.Value += string(r)
				}
			}
		}
		return m, nil
	}

	switch key {
	case "esc":
		m.formOverlay = false
	case "j", "down":
		if m.formFocusIdx < len(m.formFields)-1 {
			m.formFocusIdx++
		}
	case "k", "up":
		if m.formFocusIdx > 0 {
			m.formFocusIdx--
		}
	case "enter":
		m.formEditing = true
	case "ctrl+s":
		return m.submitForm()
	}

	return m, nil
}

func (m KubernetesModel) submitForm() (KubernetesModel, tea.Cmd) {
	m.formOverlay = false

	switch m.formType {
	case kubeFormCreateVM:
		name := m.formFields[0].Value
		ns := m.formFields[1].Value
		image := m.formFields[2].Value
		cpusStr := m.formFields[3].Value
		memory := m.formFields[4].Value

		if name == "" || image == "" {
			m.message = "Name and Image are required"
			return m, nil
		}
		if ns == "" {
			ns = "default"
		}
		cpus, err := strconv.Atoi(cpusStr)
		if err != nil || cpus < 1 {
			cpus = 2
		}
		if memory == "" {
			memory = "2Gi"
		}

		m.message = "Creating VM " + name + "..."
		return m, kubeCreateVMCmd(m.client, name, ns, image, cpus, memory)

	case kubeFormUploadPVC:
		name := m.formFields[0].Value
		ns := m.formFields[1].Value
		size := m.formFields[2].Value
		imagePath := m.formFields[3].Value

		if name == "" || imagePath == "" {
			m.message = "Name and Image Path are required"
			return m, nil
		}
		if ns == "" {
			ns = "default"
		}
		if size == "" {
			size = "10Gi"
		}

		m.message = "Uploading image to PVC " + name + "..."
		return m, kubeUploadPVCCmd(name, ns, size, imagePath)
	}

	return m, nil
}

// --- SSH ---

func (m KubernetesModel) kubeSSHCmd(name, namespace string) tea.Cmd {
	kc := m.client
	return func() tea.Msg {
		ctx := context.Background()
		localPort, stopChan, err := kc.PortForwardSSH(ctx, name, namespace)
		if err != nil {
			// Fallback to virtctl ssh if port-forward fails.
			if _, lookErr := exec.LookPath("virtctl"); lookErr == nil {
				cmd := exec.Command("virtctl", "ssh", name, "-n", namespace)
				return tea.ExecProcess(cmd, func(err error) tea.Msg {
					return KubeSSHDoneMsg{Err: err}
				})
			}
			return KubeSSHDoneMsg{Err: fmt.Errorf("port-forward: %w", err)}
		}

		cmd := exec.Command("ssh",
			"-o", "StrictHostKeyChecking=no",
			"-o", "UserKnownHostsFile=/dev/null",
			"-p", fmt.Sprintf("%d", localPort),
			"localhost")
		return tea.ExecProcess(cmd, func(err error) tea.Msg {
			close(stopChan)
			return KubeSSHDoneMsg{Err: err}
		})
	}
}

// --- Action commands ---

func kubeStartVMCmd(name, ns string) tea.Cmd {
	return func() tea.Msg {
		err := StartKubeVirtVM(name, ns)
		return KubeActionMsg{Action: "Started", VM: name, Err: err}
	}
}

func kubeStopVMCmd(name, ns string) tea.Cmd {
	return func() tea.Msg {
		err := StopKubeVirtVM(name, ns)
		return KubeActionMsg{Action: "Stopped", VM: name, Err: err}
	}
}

func kubeRestartVMCmd(name, ns string) tea.Cmd {
	return func() tea.Msg {
		err := RestartKubeVirtVM(name, ns)
		return KubeActionMsg{Action: "Restarted", VM: name, Err: err}
	}
}

func kubeDeleteVMCmd(client *KubeClient, name, ns string) tea.Cmd {
	return func() tea.Msg {
		err := client.DeleteVM(context.Background(), name, ns)
		return KubeActionMsg{Action: "Deleted", VM: name, Err: err}
	}
}

func kubeSwitchContextCmd(client *KubeClient, name string) tea.Cmd {
	return func() tea.Msg {
		err := client.SwitchContext(name)
		if err != nil {
			return KubeActionMsg{Action: "Switch context", VM: name, Err: err}
		}
		return KubeActionMsg{Action: "Switched context", VM: name}
	}
}

func kubeCreateVMCmd(client *KubeClient, name, ns, image string, cpus int, memory string) tea.Cmd {
	return func() tea.Msg {
		err := client.CreateVM(context.Background(), name, ns, image, cpus, memory)
		return KubeActionMsg{Action: "Created", VM: name, Err: err}
	}
}

func kubeUploadPVCCmd(name, ns, size, imagePath string) tea.Cmd {
	return func() tea.Msg {
		err := UploadImage(name, ns, size, imagePath)
		return KubeActionMsg{Action: "Uploaded", VM: name, Err: err}
	}
}

// SetSize updates layout dimensions.
func (m *KubernetesModel) SetSize(width, height int) {
	m.width = width
	m.height = height
}

// View renders the Kubernetes tab.
func (m KubernetesModel) View(leftOuterW, rightOuterW, paneH int) string {
	if m.client == nil {
		return kubeUnavailableView(leftOuterW+rightOuterW, paneH)
	}

	leftStyle := libvirtBlurredPane
	rightStyle := libvirtBlurredPane
	if m.focusPane == 0 {
		leftStyle = libvirtFocusedPane
	} else {
		rightStyle = libvirtFocusedPane
	}

	var listHeader, listContent string
	switch m.subView {
	case kubeViewPVCs:
		listHeader = "PVCs"
		listContent = m.renderPVCList(leftOuterW - paneHPad)
	case kubeViewMigrations:
		listHeader = "Migrations"
		listContent = m.renderMigrationList(leftOuterW - paneHPad)
	default:
		listHeader = "KubeVirt VMs"
		listContent = m.renderVMList(leftOuterW - paneHPad)
	}

	leftPane := leftStyle.
		Width(leftOuterW).
		Height(paneH).
		Render(kubeHeaderStyle.Render(listHeader) + "\n" + listContent)

	detailContent := m.renderDetails(rightOuterW - paneHPad)
	rightPane := rightStyle.
		Width(rightOuterW).
		Height(paneH).
		Render(kubeDetailHeaderStyle.Render("Details") + "\n" + detailContent)

	view := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)

	// Render form overlay on top if active.
	if m.formOverlay {
		view += "\n" + m.renderFormOverlay(leftOuterW+rightOuterW)
	}

	return view
}

func kubeUnavailableView(w, h int) string {
	content := libvirtDimStyle.Render("  Kubeconfig not found\n\n") +
		libvirtDimStyle.Render("  Configure a kubeconfig file\n") +
		libvirtDimStyle.Render("  to manage KubeVirt virtual machines.")
	return libvirtBlurredPane.
		Width(w).
		Height(h).
		Render(kubeHeaderStyle.Render("Kubernetes") + "\n" + content)
}

func (m KubernetesModel) renderVMList(width int) string {
	if m.loading && len(m.vms) == 0 {
		return libvirtDimStyle.Render("  Loading VMs...")
	}
	if !m.status.Installed {
		msg := "  KubeVirt not installed on cluster\n" +
			"  Install KubeVirt to manage VMs"
		if m.status.Error != "" {
			msg = "  " + m.status.Error
		}
		return libvirtDimStyle.Render(msg)
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

		stateStr := m.kubeStateIndicator(vm.Status)
		name := vm.Name
		if vm.Namespace != "" && vm.Namespace != "default" {
			name = vm.Namespace + "/" + vm.Name
		}

		// Migration indicator.
		migIndicator := ""
		if vm.Migrating {
			migIndicator = kubeMigrationIndicator.Render(" ↔")
		}

		maxName := width - 18
		if maxName < 10 {
			maxName = 10
		}
		if len(name) > maxName {
			name = name[:maxName-1] + "…"
		}

		line := fmt.Sprintf("%s%-*s %s%s", indicator, maxName, name, stateStr, migIndicator)
		if i == m.selected {
			b.WriteString(libvirtSelectedLine.Render(line))
		} else {
			b.WriteString(line)
		}
		b.WriteString("\n")
	}
	return b.String()
}

func (m KubernetesModel) renderPVCList(width int) string {
	if len(m.pvcs) == 0 {
		return libvirtDimStyle.Render("  No PVCs found")
	}

	var b strings.Builder
	for i, pvc := range m.pvcs {
		indicator := "  "
		if i == m.selected {
			indicator = libvirtSelectedIndicator.Render("● ")
		}

		name := pvc.Name
		if pvc.Namespace != "" && pvc.Namespace != "default" {
			name = pvc.Namespace + "/" + pvc.Name
		}

		maxName := width - 16
		if maxName < 10 {
			maxName = 10
		}
		if len(name) > maxName {
			name = name[:maxName-1] + "…"
		}

		statusStyle := libvirtDimStyle
		if pvc.Status == "Bound" {
			statusStyle = libvirtStateRunning
		}

		line := fmt.Sprintf("%s%-*s %s", indicator, maxName, name, statusStyle.Render(pvc.Status))
		if i == m.selected {
			b.WriteString(libvirtSelectedLine.Render(line))
		} else {
			b.WriteString(line)
		}
		b.WriteString("\n")
	}
	return b.String()
}

func (m KubernetesModel) renderMigrationList(width int) string {
	if len(m.migrations) == 0 {
		return libvirtDimStyle.Render("  No migrations found")
	}

	var b strings.Builder
	for i, mig := range m.migrations {
		indicator := "  "
		if i == m.selected {
			indicator = libvirtSelectedIndicator.Render("● ")
		}

		name := mig.Name
		maxName := width - 20
		if maxName < 10 {
			maxName = 10
		}
		if len(name) > maxName {
			name = name[:maxName-1] + "…"
		}

		phaseStyle := libvirtDimStyle
		switch mig.Phase {
		case "Succeeded":
			phaseStyle = libvirtStateRunning
		case "Running", "Scheduling", "PreparingTarget":
			phaseStyle = libvirtStatePaused
		case "Failed":
			phaseStyle = libvirtStateShutoff
		}

		line := fmt.Sprintf("%s%-*s %s", indicator, maxName, name, phaseStyle.Render(mig.Phase))
		if i == m.selected {
			b.WriteString(libvirtSelectedLine.Render(line))
		} else {
			b.WriteString(line)
		}
		b.WriteString("\n")
	}
	return b.String()
}

func (m KubernetesModel) renderDetails(width int) string {
	var b strings.Builder
	detailLabel := kubeDetailLabel
	detailValue := libvirtDetailValue

	// Cluster status header.
	b.WriteString(kubeSubHeaderStyle.Render("  Cluster Status") + "\n")
	for _, ctx := range m.contexts {
		if ctx.Current {
			b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Context:"), detailValue.Render(ctx.Name)))
			b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Cluster:"), detailValue.Render(ctx.Cluster)))
			break
		}
	}

	if m.status.Installed {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("KubeVirt:"), libvirtStateRunning.Render(m.status.Version)))
	} else {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("KubeVirt:"), libvirtStateShutoff.Render("not installed")))
	}
	if m.status.CDIInstalled {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("CDI:"), libvirtStateRunning.Render(m.status.CDIVersion)))
	} else {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("CDI:"), libvirtDimStyle.Render("not installed")))
	}

	// Show active namespace filter.
	if m.namespace != "all" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Filter:"), kubeFilterStyle.Render(m.namespace)))
	}

	b.WriteString("\n")

	// Selected item details.
	switch m.subView {
	case kubeViewPVCs:
		b.WriteString(m.renderPVCDetails(detailLabel, detailValue))
	case kubeViewMigrations:
		b.WriteString(m.renderMigrationDetails(detailLabel, detailValue))
	default:
		b.WriteString(m.renderVMDetails(width, detailLabel, detailValue))
	}

	// Actions box.
	b.WriteString("\n")
	switch m.subView {
	case kubeViewVMs:
		actionsBox := libvirtActionsBoxStyle.Width(width - 4).Render(
			libvirtActionsTitle.Render("Actions") + "\n" +
				"  " + libvirtActionKey.Render("[S]") + libvirtDimStyle.Render("tart") + "  " +
				libvirtActionKey.Render("s[X]") + libvirtDimStyle.Render("top") + "  " +
				libvirtActionKey.Render("res[T]") + libvirtDimStyle.Render("art") + "  " +
				libvirtActionKey.Render("[E]") + libvirtDimStyle.Render(" SSH") + "\n" +
				"  " + libvirtActionKey.Render("[D]") + libvirtDimStyle.Render("elete") + "  " +
				libvirtActionKey.Render("[C]") + libvirtDimStyle.Render("onsole") + "  " +
				libvirtActionKey.Render("[W]") + libvirtDimStyle.Render("izard") + "  " +
				libvirtActionKey.Render("[R]") + libvirtDimStyle.Render("efresh") + "\n" +
				"  " + libvirtActionKey.Render("[1]") + libvirtDimStyle.Render(" VMs") + "  " +
				libvirtActionKey.Render("[2]") + libvirtDimStyle.Render(" PVCs") + "  " +
				libvirtActionKey.Render("[3]") + libvirtDimStyle.Render(" Migrations") + "\n" +
				"  " + libvirtActionKey.Render("[N]") + libvirtDimStyle.Render("ext ctx") + "  " +
				libvirtActionKey.Render("[A]") + libvirtDimStyle.Render(" Namespace"))
		b.WriteString(actionsBox)
	case kubeViewPVCs:
		actionsBox := libvirtActionsBoxStyle.Width(width - 4).Render(
			libvirtActionsTitle.Render("Views") + "\n" +
				"  " + libvirtActionKey.Render("[1]") + libvirtDimStyle.Render(" VMs") + "  " +
				libvirtActionKey.Render("[2]") + libvirtDimStyle.Render(" PVCs") + "  " +
				libvirtActionKey.Render("[3]") + libvirtDimStyle.Render(" Migrations") + "\n" +
				"  " + libvirtActionKey.Render("[U]") + libvirtDimStyle.Render("pload") + "  " +
				libvirtActionKey.Render("[R]") + libvirtDimStyle.Render("efresh") + "\n" +
				"  " + libvirtActionKey.Render("[N]") + libvirtDimStyle.Render("ext ctx") + "  " +
				libvirtActionKey.Render("[A]") + libvirtDimStyle.Render(" Namespace"))
		b.WriteString(actionsBox)
	case kubeViewMigrations:
		actionsBox := libvirtActionsBoxStyle.Width(width - 4).Render(
			libvirtActionsTitle.Render("Views") + "\n" +
				"  " + libvirtActionKey.Render("[1]") + libvirtDimStyle.Render(" VMs") + "  " +
				libvirtActionKey.Render("[2]") + libvirtDimStyle.Render(" PVCs") + "  " +
				libvirtActionKey.Render("[3]") + libvirtDimStyle.Render(" Migrations") + "\n" +
				"  " + libvirtActionKey.Render("[R]") + libvirtDimStyle.Render("efresh") + "\n" +
				"  " + libvirtActionKey.Render("[N]") + libvirtDimStyle.Render("ext ctx") + "  " +
				libvirtActionKey.Render("[A]") + libvirtDimStyle.Render(" Namespace"))
		b.WriteString(actionsBox)
	}

	// Confirmation / message.
	if m.confirming && m.subView == kubeViewVMs && m.selected >= 0 && m.selected < len(m.vms) {
		b.WriteString("\n\n")
		b.WriteString(libvirtConfirmStyle.Render(
			fmt.Sprintf("  Delete VM \"%s\"? [y/N] ", m.vms[m.selected].Name)))
	}
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

func (m KubernetesModel) renderVMDetails(width int, detailLabel, detailValue lipgloss.Style) string {
	if len(m.vms) == 0 || m.selected < 0 || m.selected >= len(m.vms) {
		return libvirtDimStyle.Render("  No VM selected") + "\n"
	}

	vm := m.vms[m.selected]
	var b strings.Builder
	b.WriteString(kubeSubHeaderStyle.Render("  VM Details") + "\n")
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Name:"), detailValue.Render(vm.Name)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Namespace:"), detailValue.Render(vm.Namespace)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Status:"), m.kubeStateIndicator(vm.Status)))
	if vm.CPUs > 0 {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("CPUs:"), detailValue.Render(fmt.Sprintf("%d", vm.CPUs))))
	}
	if vm.Memory != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Memory:"), detailValue.Render(vm.Memory)))
	}
	if vm.Node != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Node:"), detailValue.Render(vm.Node)))
	}
	if vm.IP != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("IP:"), detailValue.Render(vm.IP)))
	}
	if vm.CreationTime != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Age:"), detailValue.Render(vm.CreationTime)))
	}
	if vm.GuestOS != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Guest OS:"), detailValue.Render(vm.GuestOS)))
	}
	if vm.Conditions != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Conds:"), detailValue.Render(vm.Conditions)))
	}
	if vm.Migrating {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Migration:"), kubeMigrationIndicator.Render("in progress")))
	}
	return b.String()
}

func (m KubernetesModel) renderPVCDetails(detailLabel, detailValue lipgloss.Style) string {
	if len(m.pvcs) == 0 || m.selected < 0 || m.selected >= len(m.pvcs) {
		return libvirtDimStyle.Render("  No PVC selected") + "\n"
	}

	pvc := m.pvcs[m.selected]
	var b strings.Builder
	b.WriteString(kubeSubHeaderStyle.Render("  PVC Details") + "\n")
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Name:"), detailValue.Render(pvc.Name)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Namespace:"), detailValue.Render(pvc.Namespace)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Status:"), detailValue.Render(pvc.Status)))
	if pvc.Capacity != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Capacity:"), detailValue.Render(pvc.Capacity)))
	}
	if pvc.AccessModes != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Access:"), detailValue.Render(pvc.AccessModes)))
	}
	if pvc.StorageClass != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("SC:"), detailValue.Render(pvc.StorageClass)))
	}
	if pvc.Volume != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Volume:"), detailValue.Render(pvc.Volume)))
	}
	return b.String()
}

func (m KubernetesModel) renderMigrationDetails(detailLabel, detailValue lipgloss.Style) string {
	if len(m.migrations) == 0 || m.selected < 0 || m.selected >= len(m.migrations) {
		return libvirtDimStyle.Render("  No migration selected") + "\n"
	}

	mig := m.migrations[m.selected]
	var b strings.Builder
	b.WriteString(kubeSubHeaderStyle.Render("  Migration Details") + "\n")
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Name:"), detailValue.Render(mig.Name)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("VM:"), detailValue.Render(mig.VMName)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Namespace:"), detailValue.Render(mig.Namespace)))
	b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Phase:"), detailValue.Render(mig.Phase)))
	if mig.Created != "" {
		b.WriteString(fmt.Sprintf("  %s  %s\n", detailLabel.Render("Age:"), detailValue.Render(mig.Created)))
	}
	return b.String()
}

func (m KubernetesModel) renderFormOverlay(totalW int) string {
	overlayW := totalW - 10
	if overlayW > 60 {
		overlayW = 60
	}
	if overlayW < 30 {
		overlayW = 30
	}

	var title string
	switch m.formType {
	case kubeFormCreateVM:
		title = "Create VM"
	case kubeFormUploadPVC:
		title = "Upload Disk Image"
	}

	var b strings.Builder
	b.WriteString(kubeFormTitleStyle.Render("  " + title) + "\n\n")

	for i, f := range m.formFields {
		cursor := "  "
		if i == m.formFocusIdx {
			cursor = kubeFormCursorStyle.Render("> ")
		}

		label := kubeFormLabelStyle.Render(fmt.Sprintf("%-12s", f.Label+":"))
		val := f.Value
		if val == "" {
			val = libvirtDimStyle.Render(f.Placeholder)
		}

		if i == m.formFocusIdx && m.formEditing {
			val = kubeFormEditStyle.Render(f.Value + "█")
		}

		b.WriteString(cursor + label + " " + val + "\n")
	}

	b.WriteString("\n")
	b.WriteString(kubeFormFooterStyle.Render("  Enter: edit  j/k: navigate  Ctrl+S: submit  Esc: cancel"))

	return kubeFormOverlayStyle.Width(overlayW).Render(b.String())
}

func (m KubernetesModel) kubeStateIndicator(status string) string {
	switch status {
	case "Running", "Succeeded":
		return libvirtStateRunning.Render(status)
	case "Scheduling", "Pending":
		return libvirtStatePaused.Render(status)
	case "Stopped", "Failed":
		return libvirtStateShutoff.Render(status)
	default:
		return libvirtDimStyle.Render(status)
	}
}

// StatusBar returns the status bar for the Kubernetes tab.
func (m KubernetesModel) StatusBar(width int) string {
	var left string
	if m.client == nil {
		left = statusFailedStyle.Render("kubeconfig not found")
	} else {
		// Show current context.
		ctxName := ""
		for _, ctx := range m.contexts {
			if ctx.Current {
				ctxName = ctx.Name
				break
			}
		}
		vmCount := fmt.Sprintf("%d VMs  %d PVCs", len(m.vms), len(m.pvcs))
		if ctxName != "" {
			left = libvirtStatusCount.Render(ctxName+": ") + libvirtStatusCount.Render(vmCount)
		} else {
			left = libvirtStatusCount.Render(vmCount)
		}
		if m.namespace != "all" {
			left += libvirtDimStyle.Render("  ns:") + kubeFilterStyle.Render(m.namespace)
		}
	}

	hints := hintKeyStyle.Render("s") + hintStyle.Render(": Start  ") +
		hintKeyStyle.Render("x") + hintStyle.Render(": Stop  ") +
		hintKeyStyle.Render("d") + hintStyle.Render(": Del  ") +
		hintKeyStyle.Render("e") + hintStyle.Render(": SSH  ") +
		hintKeyStyle.Render("n") + hintStyle.Render(": Ctx  ") +
		hintKeyStyle.Render("a") + hintStyle.Render(": NS  ") +
		hintKeyStyle.Render("1/2/3") + hintStyle.Render(": View")

	leftW := lipgloss.Width(left)
	rightW := lipgloss.Width(hints)
	spacing := width - leftW - rightW - 2
	if spacing < 1 {
		spacing = 1
	}
	bar := left + lipgloss.NewStyle().Width(spacing).Render("") + hints
	return statusBarStyle.Width(width).Render(bar)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// Styles for the Kubernetes tab.
var (
	kubeHeaderStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(theme.Cyan).
			MarginBottom(1)

	kubeDetailHeaderStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Orange).
				MarginBottom(1)

	kubeSubHeaderStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.OrangeLight)

	kubeDetailLabel = lipgloss.NewStyle().
			Foreground(theme.CoralLight).
			Width(10)

	kubeMigrationIndicator = lipgloss.NewStyle().
				Foreground(theme.Orange).
				Bold(true)

	kubeFilterStyle = lipgloss.NewStyle().
			Foreground(theme.Cyan).
			Bold(true)

	kubeFormOverlayStyle = lipgloss.NewStyle().
				Border(lipgloss.DoubleBorder()).
				BorderForeground(theme.Orange).
				Background(lipgloss.Color("#111111")).
				Padding(1, 2)

	kubeFormTitleStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(theme.Orange)

	kubeFormLabelStyle = lipgloss.NewStyle().
				Foreground(theme.CoralLight)

	kubeFormCursorStyle = lipgloss.NewStyle().
				Foreground(theme.Orange).
				Bold(true)

	kubeFormEditStyle = lipgloss.NewStyle().
				Foreground(theme.Green)

	kubeFormFooterStyle = lipgloss.NewStyle().
				Foreground(theme.Dim).
				Italic(true)
)
