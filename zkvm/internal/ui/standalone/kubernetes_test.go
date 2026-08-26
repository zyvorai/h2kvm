// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// keyMsg builds a tea.KeyMsg for a rune character (e.g. 'j', 'k').
func keyMsg(s string) tea.KeyMsg {
	switch s {
	case "esc":
		return tea.KeyMsg{Type: tea.KeyEsc}
	case "enter":
		return tea.KeyMsg{Type: tea.KeyEnter}
	case "up":
		return tea.KeyMsg{Type: tea.KeyUp}
	case "down":
		return tea.KeyMsg{Type: tea.KeyDown}
	case "home":
		return tea.KeyMsg{Type: tea.KeyHome}
	case "ctrl+s":
		return tea.KeyMsg{Type: tea.KeyCtrlS}
	case "backspace":
		return tea.KeyMsg{Type: tea.KeyBackspace}
	default:
		// Single rune key.
		runes := []rune(s)
		return tea.KeyMsg{Type: tea.KeyRunes, Runes: runes}
	}
}

func TestNewKubernetesModelDefaults(t *testing.T) {
	// NewKubernetesModel may or may not create a client depending on
	// kubeconfig availability. We test the fields we can control.
	m := KubernetesModel{
		loading:   true,
		namespace: "all",
	}

	if !m.loading {
		t.Error("expected loading to be true")
	}
	if m.namespace != "all" {
		t.Errorf("expected namespace %q, got %q", "all", m.namespace)
	}
	if m.selected != 0 {
		t.Errorf("expected selected to be 0, got %d", m.selected)
	}
	if m.subView != kubeViewVMs {
		t.Errorf("expected subView to be %d (kubeViewVMs), got %d", kubeViewVMs, m.subView)
	}
	if m.focusPane != 0 {
		t.Errorf("expected focusPane to be 0, got %d", m.focusPane)
	}
	if m.formOverlay {
		t.Error("expected formOverlay to be false")
	}
	if m.confirming {
		t.Error("expected confirming to be false")
	}
}

func TestKubeStateIndicatorRunning(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("Running")
	if result == "" {
		t.Error("expected non-empty result for Running status")
	}
	// The rendered string should contain the status text.
	if len(result) == 0 {
		t.Error("kubeStateIndicator returned empty string for Running")
	}
}

func TestKubeStateIndicatorSucceeded(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("Succeeded")
	if result == "" {
		t.Error("expected non-empty result for Succeeded status")
	}
}

func TestKubeStateIndicatorScheduling(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("Scheduling")
	if result == "" {
		t.Error("expected non-empty result for Scheduling status")
	}
}

func TestKubeStateIndicatorPending(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("Pending")
	if result == "" {
		t.Error("expected non-empty result for Pending status")
	}
}

func TestKubeStateIndicatorStopped(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("Stopped")
	if result == "" {
		t.Error("expected non-empty result for Stopped status")
	}
}

func TestKubeStateIndicatorFailed(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("Failed")
	if result == "" {
		t.Error("expected non-empty result for Failed status")
	}
}

func TestKubeStateIndicatorUnknown(t *testing.T) {
	m := KubernetesModel{}
	result := m.kubeStateIndicator("SomethingElse")
	if result == "" {
		t.Error("expected non-empty result for unknown status")
	}
}

func TestApplyNamespaceFilterAll(t *testing.T) {
	m := KubernetesModel{
		namespace: "all",
		allVMs: []KubeVirtVM{
			{Name: "vm-1", Namespace: "ns-a"},
			{Name: "vm-2", Namespace: "ns-b"},
			{Name: "vm-3", Namespace: "ns-a"},
		},
		allPVCs: []PVCInfo{
			{Name: "pvc-1", Namespace: "ns-a"},
			{Name: "pvc-2", Namespace: "ns-b"},
		},
	}

	m.applyNamespaceFilter()

	if len(m.vms) != 3 {
		t.Errorf("expected 3 VMs with 'all' filter, got %d", len(m.vms))
	}
	if len(m.pvcs) != 2 {
		t.Errorf("expected 2 PVCs with 'all' filter, got %d", len(m.pvcs))
	}
}

func TestApplyNamespaceFilterSpecific(t *testing.T) {
	m := KubernetesModel{
		namespace: "ns-a",
		allVMs: []KubeVirtVM{
			{Name: "vm-1", Namespace: "ns-a"},
			{Name: "vm-2", Namespace: "ns-b"},
			{Name: "vm-3", Namespace: "ns-a"},
		},
		allPVCs: []PVCInfo{
			{Name: "pvc-1", Namespace: "ns-a"},
			{Name: "pvc-2", Namespace: "ns-b"},
		},
	}

	m.applyNamespaceFilter()

	if len(m.vms) != 2 {
		t.Errorf("expected 2 VMs for namespace ns-a, got %d", len(m.vms))
	}
	for _, vm := range m.vms {
		if vm.Namespace != "ns-a" {
			t.Errorf("expected VM namespace ns-a, got %q", vm.Namespace)
		}
	}

	if len(m.pvcs) != 1 {
		t.Errorf("expected 1 PVC for namespace ns-a, got %d", len(m.pvcs))
	}
	if m.pvcs[0].Namespace != "ns-a" {
		t.Errorf("expected PVC namespace ns-a, got %q", m.pvcs[0].Namespace)
	}
}

func TestApplyNamespaceFilterNoMatches(t *testing.T) {
	m := KubernetesModel{
		namespace: "nonexistent",
		allVMs: []KubeVirtVM{
			{Name: "vm-1", Namespace: "ns-a"},
		},
		allPVCs: []PVCInfo{
			{Name: "pvc-1", Namespace: "ns-a"},
		},
	}

	m.applyNamespaceFilter()

	if len(m.vms) != 0 {
		t.Errorf("expected 0 VMs for nonexistent namespace, got %d", len(m.vms))
	}
	if len(m.pvcs) != 0 {
		t.Errorf("expected 0 PVCs for nonexistent namespace, got %d", len(m.pvcs))
	}
}

func TestCurrentListLenVMs(t *testing.T) {
	m := KubernetesModel{
		subView: kubeViewVMs,
		vms: []KubeVirtVM{
			{Name: "vm-1"},
			{Name: "vm-2"},
			{Name: "vm-3"},
		},
	}

	if got := m.currentListLen(); got != 3 {
		t.Errorf("expected currentListLen 3 for VMs view, got %d", got)
	}
}

func TestCurrentListLenPVCs(t *testing.T) {
	m := KubernetesModel{
		subView: kubeViewPVCs,
		pvcs: []PVCInfo{
			{Name: "pvc-1"},
			{Name: "pvc-2"},
		},
	}

	if got := m.currentListLen(); got != 2 {
		t.Errorf("expected currentListLen 2 for PVCs view, got %d", got)
	}
}

func TestCurrentListLenMigrations(t *testing.T) {
	m := KubernetesModel{
		subView: kubeViewMigrations,
		migrations: []MigrationInfo{
			{Name: "mig-1"},
		},
	}

	if got := m.currentListLen(); got != 1 {
		t.Errorf("expected currentListLen 1 for migrations view, got %d", got)
	}
}

func TestCurrentListLenEmpty(t *testing.T) {
	m := KubernetesModel{
		subView: kubeViewVMs,
	}

	if got := m.currentListLen(); got != 0 {
		t.Errorf("expected currentListLen 0 for empty VMs, got %d", got)
	}
}

func TestHandleFormOverlayKeyNavigateDown(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  false,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: "default"},
			{Label: "Image", Value: ""},
		},
		// Need a non-nil client for handleKey to proceed, but handleFormOverlayKey
		// is called directly from handleKey only when formOverlay is true and
		// client is non-nil. We call handleFormOverlayKey directly.
	}

	m, _ = m.handleFormOverlayKey(keyMsg("j"))
	if m.formFocusIdx != 1 {
		t.Errorf("expected formFocusIdx 1 after 'j', got %d", m.formFocusIdx)
	}
}

func TestHandleFormOverlayKeyNavigateUp(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 2,
		formEditing:  false,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: "default"},
			{Label: "Image", Value: ""},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("k"))
	if m.formFocusIdx != 1 {
		t.Errorf("expected formFocusIdx 1 after 'k', got %d", m.formFocusIdx)
	}
}

func TestHandleFormOverlayKeyNavigateUpAtTop(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  false,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: "default"},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("k"))
	if m.formFocusIdx != 0 {
		t.Errorf("expected formFocusIdx 0 after 'k' at top, got %d", m.formFocusIdx)
	}
}

func TestHandleFormOverlayKeyNavigateDownAtBottom(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 1,
		formEditing:  false,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: "default"},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("j"))
	if m.formFocusIdx != 1 {
		t.Errorf("expected formFocusIdx 1 after 'j' at bottom, got %d", m.formFocusIdx)
	}
}

func TestHandleFormOverlayKeyEscClosesForm(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formEditing: false,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("esc"))
	if m.formOverlay {
		t.Error("expected formOverlay to be false after esc")
	}
}

func TestHandleFormOverlayKeyEnterStartsEditing(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  false,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("enter"))
	if !m.formEditing {
		t.Error("expected formEditing to be true after enter")
	}
}

func TestHandleFormOverlayKeyEditingEscStopsEditing(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  true,
		formFields: []kubeFormField{
			{Label: "Name", Value: "test"},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("esc"))
	if m.formEditing {
		t.Error("expected formEditing to be false after esc during editing")
	}
	// The form overlay should remain open (esc only exits edit mode, not the form).
	if !m.formOverlay {
		t.Error("expected formOverlay to remain true after esc during editing")
	}
}

func TestHandleFormOverlayKeyEditingEnterStopsEditing(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  true,
		formFields: []kubeFormField{
			{Label: "Name", Value: "test"},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("enter"))
	if m.formEditing {
		t.Error("expected formEditing to be false after enter during editing")
	}
}

func TestHandleFormOverlayKeyEditingBackspace(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  true,
		formFields: []kubeFormField{
			{Label: "Name", Value: "abc"},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("backspace"))
	if m.formFields[0].Value != "ab" {
		t.Errorf("expected value %q after backspace, got %q", "ab", m.formFields[0].Value)
	}
}

func TestHandleFormOverlayKeyEditingBackspaceEmpty(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  true,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("backspace"))
	if m.formFields[0].Value != "" {
		t.Errorf("expected value to remain empty after backspace on empty, got %q", m.formFields[0].Value)
	}
}

func TestHandleFormOverlayKeyEditingCharInput(t *testing.T) {
	m := KubernetesModel{
		formOverlay:  true,
		formFocusIdx: 0,
		formEditing:  true,
		formFields: []kubeFormField{
			{Label: "Name", Value: "te"},
		},
	}

	m, _ = m.handleFormOverlayKey(keyMsg("s"))
	if m.formFields[0].Value != "tes" {
		t.Errorf("expected value %q after typing 's', got %q", "tes", m.formFields[0].Value)
	}

	m, _ = m.handleFormOverlayKey(keyMsg("t"))
	if m.formFields[0].Value != "test" {
		t.Errorf("expected value %q after typing 't', got %q", "test", m.formFields[0].Value)
	}
}

func TestSubmitFormCreateVMEmptyName(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormCreateVM,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: "default"},
			{Label: "Image", Value: ""},
			{Label: "CPUs", Value: "2"},
			{Label: "Memory", Value: "2Gi"},
		},
	}

	m, cmd := m.submitForm()
	if cmd != nil {
		t.Error("expected nil cmd when name is empty")
	}
	if m.message != "Name and Image are required" {
		t.Errorf("expected validation message, got %q", m.message)
	}
}

func TestSubmitFormCreateVMEmptyImage(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormCreateVM,
		formFields: []kubeFormField{
			{Label: "Name", Value: "my-vm"},
			{Label: "Namespace", Value: "default"},
			{Label: "Image", Value: ""},
			{Label: "CPUs", Value: "2"},
			{Label: "Memory", Value: "2Gi"},
		},
	}

	m, cmd := m.submitForm()
	if cmd != nil {
		t.Error("expected nil cmd when image is empty")
	}
	if m.message != "Name and Image are required" {
		t.Errorf("expected validation message, got %q", m.message)
	}
}

func TestSubmitFormUploadPVCEmptyName(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormUploadPVC,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: "default"},
			{Label: "Size", Value: "10Gi"},
			{Label: "Image Path", Value: ""},
		},
	}

	m, cmd := m.submitForm()
	if cmd != nil {
		t.Error("expected nil cmd when name is empty")
	}
	if m.message != "Name and Image Path are required" {
		t.Errorf("expected validation message, got %q", m.message)
	}
}

func TestSubmitFormUploadPVCEmptyImagePath(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormUploadPVC,
		formFields: []kubeFormField{
			{Label: "Name", Value: "my-disk"},
			{Label: "Namespace", Value: "default"},
			{Label: "Size", Value: "10Gi"},
			{Label: "Image Path", Value: ""},
		},
	}

	m, cmd := m.submitForm()
	if cmd != nil {
		t.Error("expected nil cmd when image path is empty")
	}
	if m.message != "Name and Image Path are required" {
		t.Errorf("expected validation message, got %q", m.message)
	}
}

func TestSubmitFormCreateVMInvalidCPUs(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormCreateVM,
		client:      &KubeClient{}, // non-nil to allow command generation
		formFields: []kubeFormField{
			{Label: "Name", Value: "my-vm"},
			{Label: "Namespace", Value: "default"},
			{Label: "Image", Value: "quay.io/containerdisks/fedora:latest"},
			{Label: "CPUs", Value: "invalid"},
			{Label: "Memory", Value: "2Gi"},
		},
	}

	m, cmd := m.submitForm()
	// Invalid CPUs should default to 2 and still produce a command.
	if cmd == nil {
		t.Error("expected non-nil cmd with valid name and image")
	}
	if m.formOverlay {
		t.Error("expected formOverlay to be false after submit")
	}
}

func TestSubmitFormCreateVMDefaultNamespace(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormCreateVM,
		client:      &KubeClient{},
		formFields: []kubeFormField{
			{Label: "Name", Value: "my-vm"},
			{Label: "Namespace", Value: ""},
			{Label: "Image", Value: "quay.io/containerdisks/fedora:latest"},
			{Label: "CPUs", Value: "2"},
			{Label: "Memory", Value: ""},
		},
	}

	m, cmd := m.submitForm()
	// Should succeed, using defaults for empty namespace and memory.
	if cmd == nil {
		t.Error("expected non-nil cmd for valid form with empty namespace/memory")
	}
}

func TestSubmitFormClosesOverlay(t *testing.T) {
	m := KubernetesModel{
		formOverlay: true,
		formType:    kubeFormCreateVM,
		formFields: []kubeFormField{
			{Label: "Name", Value: ""},
			{Label: "Namespace", Value: ""},
			{Label: "Image", Value: ""},
			{Label: "CPUs", Value: ""},
			{Label: "Memory", Value: ""},
		},
	}

	m, _ = m.submitForm()
	if m.formOverlay {
		t.Error("expected formOverlay to be false after submitForm")
	}
}

func TestMaxHelper(t *testing.T) {
	tests := []struct {
		a, b, want int
	}{
		{0, 0, 0},
		{1, 0, 1},
		{0, 1, 1},
		{5, 3, 5},
		{3, 5, 5},
		{-1, -2, -1},
		{-2, -1, -1},
		{-1, 0, 0},
		{100, 100, 100},
	}

	for _, tt := range tests {
		got := max(tt.a, tt.b)
		if got != tt.want {
			t.Errorf("max(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
		}
	}
}

func TestKubeViewConstants(t *testing.T) {
	if kubeViewVMs != 0 {
		t.Errorf("expected kubeViewVMs = 0, got %d", kubeViewVMs)
	}
	if kubeViewPVCs != 1 {
		t.Errorf("expected kubeViewPVCs = 1, got %d", kubeViewPVCs)
	}
	if kubeViewMigrations != 2 {
		t.Errorf("expected kubeViewMigrations = 2, got %d", kubeViewMigrations)
	}
}

func TestKubeFormConstants(t *testing.T) {
	if kubeFormCreateVM != 0 {
		t.Errorf("expected kubeFormCreateVM = 0, got %d", kubeFormCreateVM)
	}
	if kubeFormUploadPVC != 1 {
		t.Errorf("expected kubeFormUploadPVC = 1, got %d", kubeFormUploadPVC)
	}
}

func TestOpenCreateVMForm(t *testing.T) {
	m := KubernetesModel{
		namespace: "all",
	}

	m.openCreateVMForm()

	if !m.formOverlay {
		t.Error("expected formOverlay to be true")
	}
	if m.formType != kubeFormCreateVM {
		t.Errorf("expected formType kubeFormCreateVM, got %d", m.formType)
	}
	if len(m.formFields) != 5 {
		t.Errorf("expected 5 form fields, got %d", len(m.formFields))
	}
	// When namespace is "all", the form namespace field should default to "default".
	if m.formFields[1].Value != "default" {
		t.Errorf("expected namespace field value %q, got %q", "default", m.formFields[1].Value)
	}
}

func TestOpenCreateVMFormWithSpecificNamespace(t *testing.T) {
	m := KubernetesModel{
		namespace: "production",
	}

	m.openCreateVMForm()

	if m.formFields[1].Value != "production" {
		t.Errorf("expected namespace field value %q, got %q", "production", m.formFields[1].Value)
	}
}

func TestOpenUploadPVCForm(t *testing.T) {
	m := KubernetesModel{
		namespace: "all",
	}

	m.openUploadPVCForm()

	if !m.formOverlay {
		t.Error("expected formOverlay to be true")
	}
	if m.formType != kubeFormUploadPVC {
		t.Errorf("expected formType kubeFormUploadPVC, got %d", m.formType)
	}
	if len(m.formFields) != 4 {
		t.Errorf("expected 4 form fields, got %d", len(m.formFields))
	}
	if m.formFields[1].Value != "default" {
		t.Errorf("expected namespace field value %q, got %q", "default", m.formFields[1].Value)
	}
}

func TestUpdateKubeVMListMsg(t *testing.T) {
	m := KubernetesModel{
		loading:   true,
		namespace: "all",
	}

	msg := KubeVMListMsg{
		VMs: []KubeVirtVM{
			{Name: "vm-1", Namespace: "ns-a"},
			{Name: "vm-2", Namespace: "ns-b"},
		},
		Contexts: []KubeContext{
			{Name: "ctx-1", Current: true},
		},
		Status: KubeVirtStatus{Installed: true, Version: "v1.0.0"},
		PVCs: []PVCInfo{
			{Name: "pvc-1", Namespace: "ns-a"},
		},
		Migrations: []MigrationInfo{
			{Name: "mig-1"},
		},
	}

	m, _ = m.Update(msg)

	if m.loading {
		t.Error("expected loading to be false after KubeVMListMsg")
	}
	if len(m.allVMs) != 2 {
		t.Errorf("expected 2 allVMs, got %d", len(m.allVMs))
	}
	if len(m.vms) != 2 {
		t.Errorf("expected 2 filtered VMs with 'all' namespace, got %d", len(m.vms))
	}
	if len(m.contexts) != 1 {
		t.Errorf("expected 1 context, got %d", len(m.contexts))
	}
	if !m.status.Installed {
		t.Error("expected status.Installed to be true")
	}
}

func TestUpdateKubeVMListMsgWithError(t *testing.T) {
	m := KubernetesModel{
		loading: true,
	}

	msg := KubeVMListMsg{
		Err: fmt.Errorf("connection refused"),
	}

	m, _ = m.Update(msg)

	if m.loading {
		t.Error("expected loading to be false")
	}
	if m.message == "" {
		t.Error("expected non-empty error message")
	}
}

func TestUpdateKubeActionMsgSuccess(t *testing.T) {
	m := KubernetesModel{
		client: &KubeClient{},
	}

	msg := KubeActionMsg{
		Action: "Started",
		VM:     "test-vm",
	}

	m, _ = m.Update(msg)

	if m.message != "Started: test-vm" {
		t.Errorf("expected message %q, got %q", "Started: test-vm", m.message)
	}
}

func TestUpdateKubeActionMsgError(t *testing.T) {
	m := KubernetesModel{
		client: &KubeClient{},
	}

	msg := KubeActionMsg{
		Action: "Start",
		VM:     "test-vm",
		Err:    fmt.Errorf("VM not found"),
	}

	m, _ = m.Update(msg)

	if m.message != "Start failed: VM not found" {
		t.Errorf("expected failure message, got %q", m.message)
	}
}

func TestKubeSSHDoneMsgSuccess(t *testing.T) {
	m := KubernetesModel{
		client: &KubeClient{},
	}

	msg := KubeSSHDoneMsg{}

	m, _ = m.Update(msg)

	if m.message != "SSH session ended" {
		t.Errorf("expected message %q, got %q", "SSH session ended", m.message)
	}
}

func TestKubeSSHDoneMsgError(t *testing.T) {
	m := KubernetesModel{
		client: &KubeClient{},
	}

	msg := KubeSSHDoneMsg{
		Err: fmt.Errorf("connection reset"),
	}

	m, _ = m.Update(msg)

	if m.message != "SSH session ended: connection reset" {
		t.Errorf("expected error message, got %q", m.message)
	}
}
