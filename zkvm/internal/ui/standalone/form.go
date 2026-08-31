// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/charmbracelet/lipgloss"

	"github.com/h2kvm/zkvm/internal/theme"
)

// Maximum completions shown in the dropdown.
const maxCompletions = 8

// detectSourceFormat returns the YAML key and human label for a source file path.
func detectSourceFormat(path string) (yamlKey, label string) {
	ext := strings.ToLower(filepath.Ext(path))
	base := strings.ToLower(filepath.Base(path))
	switch ext {
	case ".vmdk":
		return "vmdk", "VMDK (VMware)"
	case ".ova":
		return "ova", "OVA (Appliance)"
	case ".ovf":
		return "ovf", "OVF (Descriptor)"
	case ".vhd", ".vhdx":
		return "vhd", "VHD (Hyper-V)"
	case ".raw":
		return "raw", "RAW Disk"
	case ".img":
		return "raw", "RAW Disk Image"
	case ".gz", ".tar":
		if strings.Contains(base, "ami") {
			return "ami", "AMI Archive"
		}
		return "raw", "Archive"
	}
	return "raw", "Unknown"
}

// autoDetectWindows checks if the source filename contains "win" and
// auto-sets Windows-specific form fields (guest_os, fstab_mode, etc.).
func autoDetectWindows(fd *FormData, sourcePath string) {
	base := strings.ToLower(filepath.Base(sourcePath))
	if strings.Contains(base, "win") {
		fd.SetSelectValue("guest_os", "windows")
		fd.SetSelectValue("fstab_mode", "noop")
		fd.SetFieldBoolValue("regen_initramfs", false)
		fd.SetFieldBoolValue("no_grub", true)
		fd.SetFieldBoolValue("windows", true)
		// Memory/vCPUs for Windows
		fd.SetFieldValue("memory", "8192")
		fd.SetFieldValue("vcpus", "4")
	}
}

// FieldType determines how a form field is rendered and edited.
type FieldType int

const (
	FieldText     FieldType = iota // Free-form text input
	FieldPassword                  // Masked text input
	FieldSelect                    // Pick from a list of options
	FieldToggle                    // On/off boolean
	FieldNumber                    // Integer input
)

// Field represents a single configurable parameter.
type Field struct {
	Label       string    // Display label (e.g. "VMDK Path")
	Flag        string    // CLI flag name (e.g. "--vmdk")
	Type        FieldType // Input type
	Value       string    // Current text/number value
	BoolValue   bool      // Current toggle value
	Options     []string  // Choices for FieldSelect
	SelectedIdx int       // Current selection index for FieldSelect
	Placeholder string    // Placeholder hint
	Editing     bool      // Whether this field is being edited
	CursorPos   int       // Cursor position within Value

	// Path autocompletion.
	PathComplete bool     // Enable filesystem path completion
	Extensions   []string // Filter by these extensions (e.g. ".vmdk"); empty = all
	DirOnly      bool     // Only show directories
}

// DisplayValue returns the human-readable value for rendering.
func (f *Field) DisplayValue() string {
	switch f.Type {
	case FieldToggle:
		if f.BoolValue {
			return "[ON]"
		}
		return "[OFF]"
	case FieldSelect:
		if len(f.Options) > 0 && f.SelectedIdx >= 0 && f.SelectedIdx < len(f.Options) {
			return "[" + f.Options[f.SelectedIdx] + "]"
		}
		return "[]"
	case FieldPassword:
		if f.Value == "" {
			return ""
		}
		return strings.Repeat("*", len(f.Value))
	default:
		return f.Value
	}
}

// CLIValue returns the value as a CLI argument string, or empty if unset.
func (f *Field) CLIValue() string {
	switch f.Type {
	case FieldToggle:
		if f.BoolValue {
			return "true"
		}
		return ""
	case FieldSelect:
		if len(f.Options) > 0 && f.SelectedIdx >= 0 && f.SelectedIdx < len(f.Options) {
			return f.Options[f.SelectedIdx]
		}
		return ""
	default:
		return f.Value
	}
}

// Category groups related fields under a collapsible heading.
type Category struct {
	Name     string
	Expanded bool
	Fields   []Field
	ShowWhen func(form *FormData) bool // nil means always shown
}

// FormData holds all categories and tracks navigation state.
type FormData struct {
	Categories  []Category
	FocusCat    int  // Currently focused category index
	FocusField  int  // Currently focused field index within category
	InCategory  bool // Whether focus is inside a category's fields
	// Path completion state.
	completions []string // current completion matches
	compIdx     int      // selected completion index
	compVisible bool     // whether dropdown is shown
}

// envPassword returns vCenter password from GOVC_PASSWORD or VC_PASSWORD env var.
func envPassword() string {
	if p := os.Getenv("GOVC_PASSWORD"); p != "" {
		return p
	}
	return os.Getenv("VC_PASSWORD")
}

// Prefill holds pre-filled values from CLI flags.
type Prefill struct {
	Cmd       string
	VMDK      string
	OutputDir string
	VCenter   string
	VCUser    string
	DCName    string
	VMName    string
}

// NewFormData creates the form with all 8 categories and their fields.
func NewFormData(pf Prefill) *FormData {
	fd := &FormData{}

	// Determine initial cmd index.
	cmdIdx := 0
	cmdOpts := []string{"local", "vsphere", "ova", "ovf", "vhd", "ami", "raw", "azure", "fetch-and-fix", "live-fix"}
	if pf.Cmd != "" {
		for i, opt := range cmdOpts {
			if opt == pf.Cmd {
				cmdIdx = i
				break
			}
		}
	}

	// Auto-populate from GOVC_* / VC_* env vars if not set via CLI flags.
	if pf.VCenter == "" {
		if url := os.Getenv("GOVC_URL"); url != "" {
			host := url
			host = strings.TrimPrefix(host, "https://")
			host = strings.TrimPrefix(host, "http://")
			host = strings.TrimSuffix(host, "/sdk")
			host = strings.TrimSuffix(host, "/")
			pf.VCenter = host
		}
	}
	if pf.VCUser == "" {
		if user := os.Getenv("GOVC_USERNAME"); user != "" {
			pf.VCUser = user
		}
	}
	if pf.DCName == "" {
		if dc := os.Getenv("GOVC_DATACENTER"); dc != "" {
			pf.DCName = dc
		}
	}

	outputDir := pf.OutputDir
	if outputDir == "" {
		outputDir = "./out"
	}

	fd.Categories = []Category{
		// 1. Source — auto-detects format, cmd hidden but set automatically.
		{
			Name:     "Step 1: Source",
			Expanded: true,
			Fields: []Field{
				{Label: "source", Type: FieldText, Value: pf.VMDK, Placeholder: "Select disk/image file (.vmdk .ova .ovf .vhd .raw)",
					PathComplete: true, Extensions: []string{".vmdk", ".ova", ".ovf", ".vhd", ".vhdx", ".raw", ".img", ".gz", ".tar"}},
				{Label: "cmd", Flag: "--cmd", Type: FieldSelect, Options: cmdOpts, SelectedIdx: cmdIdx, Placeholder: "Mode (auto-detected)"},
			},
		},

		// 2. Remote Access — collapsed by default, only for fetch/live-fix.
		{
			Name:     "Remote Access (optional)",
			Expanded: false,
			Fields: []Field{
				{Label: "host", Flag: "--host", Type: FieldText, Placeholder: "hostname or IP"},
				{Label: "user", Flag: "--user", Type: FieldText, Placeholder: "root"},
				{Label: "port", Flag: "--port", Type: FieldNumber, Placeholder: "22"},
				{Label: "identity", Flag: "--identity", Type: FieldText, Placeholder: "SSH key path", PathComplete: true},
				{Label: "remote", Flag: "--remote", Type: FieldText, Placeholder: "Remote disk path"},
			},
		},

		// 3. Output
		{
			Name:     "Step 2: Output",
			Expanded: true,
			Fields: []Field{
				{Label: "output_dir", Flag: "--output-dir", Type: FieldText, Value: outputDir, Placeholder: "./out", PathComplete: true, DirOnly: true},
				{Label: "out_format", Flag: "--out-format", Type: FieldSelect, Options: []string{"qcow2", "raw", "vdi"}, SelectedIdx: 0},
			},
		},

		// 4. Offline Fixes
		{
			Name:     "Step 3: Fixes",
			Expanded: false,
			Fields: []Field{
				{Label: "backend", Flag: "--backend", Type: FieldSelect, Options: []string{"guestkit", "guestfs", "auto"}, SelectedIdx: 0},
				{Label: "fstab_mode", Flag: "--fstab-mode", Type: FieldSelect, Options: []string{"stabilize-all", "bypath-only", "noop"}, SelectedIdx: 0},
				{Label: "regen_initramfs", Flag: "--regen-initramfs", Type: FieldToggle, BoolValue: true},
				{Label: "no_grub", Flag: "--no-grub", Type: FieldToggle, BoolValue: false},
				{Label: "remove_vmware_tools", Flag: "--remove-vmware-tools", Type: FieldToggle, BoolValue: false},
				{Label: "serial_console", Flag: "--serial-console", Type: FieldToggle, BoolValue: false},
				{Label: "root_password", Flag: "--root-password", Type: FieldPassword, Placeholder: "New root password"},
				{Label: "container_isolation", Flag: "--container-isolation", Type: FieldToggle, BoolValue: false},
				{Label: "resize", Flag: "--resize", Type: FieldText, Placeholder: "+10G or 50G"},
			},
		},

		// 5. Deploy to Libvirt
		{
			Name:     "Step 4: Deploy to Libvirt",
			Expanded: true,
			Fields: []Field{
				{Label: "emit_domain_xml", Flag: "--emit-domain-xml", Type: FieldToggle, BoolValue: false},
				{Label: "virsh_define", Flag: "--virsh-define", Type: FieldToggle, BoolValue: false},
				{Label: "vm_name", Flag: "--vm-name", Type: FieldText, Placeholder: "converted-vm"},
				{Label: "memory", Flag: "--memory", Type: FieldNumber, Value: "2048", Placeholder: "MiB"},
				{Label: "vcpus", Flag: "--vcpus", Type: FieldNumber, Value: "2", Placeholder: "CPU count"},
				{Label: "machine", Flag: "--machine", Type: FieldSelect, Options: []string{"q35", "pc", "virt"}, SelectedIdx: 0},
				{Label: "uefi", Flag: "--uefi", Type: FieldToggle, BoolValue: false},
				{Label: "libvirt_test", Flag: "--libvirt-test", Type: FieldToggle, BoolValue: false},
				{Label: "high_perf", Flag: "--high-perf", Type: FieldToggle, BoolValue: false},
			},
		},

		// 6. Advanced
		{
			Name:     "Advanced",
			Expanded: false,
			Fields: []Field{
				{Label: "compress", Flag: "--compress", Type: FieldToggle, BoolValue: false},
				{Label: "compress_level", Flag: "--compress-level", Type: FieldNumber, Placeholder: "1-9"},
				{Label: "flatten", Flag: "--flatten", Type: FieldToggle, BoolValue: false},
				{Label: "checksum", Flag: "--checksum", Type: FieldToggle, BoolValue: false},
				{Label: "dry_run", Flag: "--dry-run", Type: FieldToggle, BoolValue: false},
				{Label: "verbose", Flag: "--verbose", Type: FieldToggle, BoolValue: false},
				{Label: "log_file", Flag: "--log-file", Type: FieldText, Placeholder: "/path/to/log", PathComplete: true},
				{Label: "config", Flag: "--config", Type: FieldText, Placeholder: "YAML config path", PathComplete: true, Extensions: []string{".yaml", ".yml"}},
				{Label: "parallel_processing", Flag: "--parallel-processing", Type: FieldToggle, BoolValue: false},
				{Label: "workers", Flag: "--workers", Type: FieldNumber, Placeholder: "Worker count"},
				{Label: "workdir", Flag: "--workdir", Type: FieldText, Placeholder: "Working directory", PathComplete: true, DirOnly: true},
			},
		},

		// 7. Azure (vSphere moved to dedicated tab)
		{
			Name:     "Azure",
			Expanded: false,
			ShowWhen: func(form *FormData) bool {
				return form.getCmd() == "azure"
			},
			Fields: []Field{
				{Label: "azure_resource_group", Flag: "--azure-resource-group", Type: FieldText, Placeholder: "Resource group name"},
				{Label: "azure_vm_names", Flag: "--azure-vm-names", Type: FieldText, Placeholder: "VM name patterns (glob)"},
				{Label: "azure_shutdown_mode", Flag: "--azure-shutdown-mode", Type: FieldSelect, Options: []string{"none", "stop", "deallocate"}, SelectedIdx: 0},
				{Label: "azure_use_snapshots", Flag: "--azure-use-snapshots", Type: FieldToggle, BoolValue: false},
				{Label: "azure_parallel", Flag: "--azure-parallel", Type: FieldNumber, Value: "4", Placeholder: "Parallel downloads"},
				{Label: "azure_subscription", Flag: "--azure-subscription", Type: FieldText, Placeholder: "Subscription ID"},
				{Label: "azure_tenant", Flag: "--azure-tenant", Type: FieldText, Placeholder: "Tenant ID"},
				{Label: "azure_disks", Flag: "--azure-disks", Type: FieldSelect, Options: []string{"all", "os", "data"}, SelectedIdx: 0},
			},
		},

		// 9. Windows
		{
			Name:     "Windows",
			Expanded: false,
			Fields: []Field{
				{Label: "windows", Flag: "--windows", Type: FieldToggle, BoolValue: false},
				{Label: "guest_os", Flag: "--guest-os", Type: FieldSelect, Options: []string{"linux", "windows"}, SelectedIdx: 0},
				{Label: "virtio_win_iso", Flag: "--virtio-win-iso", Type: FieldText, Placeholder: "Auto-detected from /var/lib/h2kvm/", PathComplete: true, Extensions: []string{".iso"}},
				{Label: "win_stage", Flag: "--win-stage", Type: FieldSelect, Options: []string{"bootstrap", "final"}, SelectedIdx: 0, Placeholder: "SATA (bootstrap) or VirtIO (final)"},
				{Label: "clock", Flag: "--clock", Type: FieldSelect, Options: []string{"utc", "localtime"}, SelectedIdx: 0},
			},
		},

		// 10. vSphere (hidden — populated by syncVSphereToForm)
		{
			Name:     "vSphere",
			Expanded: false,
			ShowWhen: func(form *FormData) bool {
				return form.getCmd() == "vsphere"
			},
			Fields: []Field{
				{Label: "vcenter", Flag: "--vcenter", Type: FieldText},
				{Label: "vc_user", Flag: "--vc-user", Type: FieldText},
				{Label: "vc_password", Flag: "--vc-password", Type: FieldPassword},
				{Label: "vc_password_env", Flag: "--vc-password-env", Type: FieldText},
				{Label: "dc_name", Flag: "--dc-name", Type: FieldText},
				{Label: "vc_insecure", Flag: "--vc-insecure", Type: FieldToggle},
				{Label: "vs_vm", Flag: "--vs-vm", Type: FieldText},
				{Label: "vs_action", Flag: "--vs-action", Type: FieldText},
			},
		},

		// 11. Kubernetes / KubeVirt
		{
			Name:     "Kubernetes / KubeVirt",
			Expanded: false,
			Fields: []Field{
				{Label: "deploy_k8s", Flag: "--deploy-k8s", Type: FieldToggle, BoolValue: false},
				{Label: "k8s_vm_name", Flag: "--k8s-vm-name", Type: FieldText, Placeholder: "KubeVirt VM name"},
				{Label: "k8s_namespace", Flag: "--k8s-namespace", Type: FieldText, Value: "default", Placeholder: "Kubernetes namespace"},
				{Label: "k8s_pvc_size", Flag: "--k8s-pvc-size", Type: FieldText, Value: "10Gi", Placeholder: "PVC size (e.g. 10Gi)"},
				{Label: "k8s_memory", Flag: "--k8s-memory", Type: FieldText, Value: "2Gi", Placeholder: "VM memory (e.g. 2Gi)"},
				{Label: "k8s_cpu", Flag: "--k8s-cpu", Type: FieldNumber, Value: "2", Placeholder: "CPU cores"},
			},
		},
	}

	return fd
}

// GetFieldValue returns the current value of a field by label, searching all categories.
func (fd *FormData) GetFieldValue(label string) string {
	for i := range fd.Categories {
		for j := range fd.Categories[i].Fields {
			if fd.Categories[i].Fields[j].Label == label {
				return fd.Categories[i].Fields[j].CLIValue()
			}
		}
	}
	return ""
}

// SetFieldValue sets the value of a field by label.
func (fd *FormData) SetFieldValue(label, val string) {
	for i := range fd.Categories {
		for j := range fd.Categories[i].Fields {
			f := &fd.Categories[i].Fields[j]
			if f.Label == label {
				if f.Type == FieldSelect {
					for k, opt := range f.Options {
						if opt == val {
							f.SelectedIdx = k
							return
						}
					}
				}
				f.Value = val
				return
			}
		}
	}
}

// SetSelectValue sets a FieldSelect option by value string.
func (fd *FormData) SetSelectValue(label, val string) {
	fd.SetFieldValue(label, val)
}

// SetFieldBoolValue sets a toggle field's bool value.
func (fd *FormData) SetFieldBoolValue(label string, val bool) {
	for i := range fd.Categories {
		for j := range fd.Categories[i].Fields {
			f := &fd.Categories[i].Fields[j]
			if f.Label == label {
				f.BoolValue = val
				return
			}
		}
	}
}

// ToggleFieldBool flips a toggle field's bool value.
func (fd *FormData) ToggleFieldBool(label string) {
	for i := range fd.Categories {
		for j := range fd.Categories[i].Fields {
			f := &fd.Categories[i].Fields[j]
			if f.Label == label {
				f.BoolValue = !f.BoolValue
				return
			}
		}
	}
}

// GetFieldBool returns the bool value of a toggle field by label.
func (fd *FormData) GetFieldBool(label string) bool {
	for i := range fd.Categories {
		for j := range fd.Categories[i].Fields {
			if fd.Categories[i].Fields[j].Label == label {
				return fd.Categories[i].Fields[j].BoolValue
			}
		}
	}
	return false
}

// getCmd returns the currently selected command type.
func (fd *FormData) getCmd() string {
	if len(fd.Categories) > 0 && len(fd.Categories[0].Fields) > 0 {
		f := &fd.Categories[0].Fields[0]
		if len(f.Options) > 0 && f.SelectedIdx >= 0 && f.SelectedIdx < len(f.Options) {
			return f.Options[f.SelectedIdx]
		}
	}
	return "local"
}

// VisibleCategories returns indices of categories that should be shown.
// Also clamps FocusCat/FocusField if they're out of bounds.
func (fd *FormData) VisibleCategories() []int {
	var indices []int
	for i := range fd.Categories {
		cat := &fd.Categories[i]
		if cat.ShowWhen == nil || cat.ShowWhen(fd) {
			indices = append(indices, i)
		}
	}
	// Clamp focus to valid range.
	if fd.FocusCat >= len(indices) {
		fd.FocusCat = len(indices) - 1
		if fd.FocusCat < 0 {
			fd.FocusCat = 0
		}
		fd.InCategory = false
	}
	if fd.InCategory && fd.FocusCat < len(indices) {
		catIdx := indices[fd.FocusCat]
		cat := &fd.Categories[catIdx]
		if fd.FocusField >= len(cat.Fields) {
			fd.FocusField = len(cat.Fields) - 1
			if fd.FocusField < 0 {
				fd.FocusField = 0
			}
		}
	}
	return indices
}

// FocusedField returns the currently focused field, or nil if focus is on a category header.
func (fd *FormData) FocusedField() *Field {
	vis := fd.VisibleCategories()
	if fd.FocusCat < 0 || fd.FocusCat >= len(vis) {
		return nil
	}
	catIdx := vis[fd.FocusCat]
	cat := &fd.Categories[catIdx]
	if !fd.InCategory || !cat.Expanded {
		return nil
	}
	if fd.FocusField < 0 || fd.FocusField >= len(cat.Fields) {
		return nil
	}
	return &cat.Fields[fd.FocusField]
}

// StopEditing clears the editing state of the currently focused field.
func (fd *FormData) StopEditing() {
	if f := fd.FocusedField(); f != nil {
		f.Editing = false
	}
}

// ToggleCategory expands or collapses the focused category.
func (fd *FormData) ToggleCategory() {
	vis := fd.VisibleCategories()
	if fd.FocusCat < 0 || fd.FocusCat >= len(vis) {
		return
	}
	catIdx := vis[fd.FocusCat]
	fd.Categories[catIdx].Expanded = !fd.Categories[catIdx].Expanded
	if fd.Categories[catIdx].Expanded {
		fd.InCategory = true
		fd.FocusField = 0
	} else {
		fd.InCategory = false
		fd.FocusField = 0 // Reset so reopening starts at first field.
	}
}

// MoveUp navigates up in the form.
func (fd *FormData) MoveUp() {
	vis := fd.VisibleCategories()
	if len(vis) == 0 {
		return
	}

	if fd.InCategory {
		if fd.FocusField > 0 {
			fd.FocusField--
		} else {
			// Move back to category header.
			fd.InCategory = false
		}
	} else {
		if fd.FocusCat > 0 {
			fd.FocusCat--
			catIdx := vis[fd.FocusCat]
			cat := &fd.Categories[catIdx]
			if cat.Expanded && len(cat.Fields) > 0 {
				fd.InCategory = true
				fd.FocusField = len(cat.Fields) - 1
			}
		}
	}
}

// MoveDown navigates down in the form.
func (fd *FormData) MoveDown() {
	vis := fd.VisibleCategories()
	if len(vis) == 0 {
		return
	}

	if fd.InCategory {
		catIdx := vis[fd.FocusCat]
		cat := &fd.Categories[catIdx]
		if fd.FocusField < len(cat.Fields)-1 {
			fd.FocusField++
		} else {
			// Move to next category.
			fd.InCategory = false
			if fd.FocusCat < len(vis)-1 {
				fd.FocusCat++
				catIdx = vis[fd.FocusCat]
				cat = &fd.Categories[catIdx]
				if cat.Expanded && len(cat.Fields) > 0 {
					fd.InCategory = true
					fd.FocusField = 0
				}
			}
		}
	} else {
		catIdx := vis[fd.FocusCat]
		cat := &fd.Categories[catIdx]
		if cat.Expanded && len(cat.Fields) > 0 {
			fd.InCategory = true
			fd.FocusField = 0
		} else if fd.FocusCat < len(vis)-1 {
			fd.FocusCat++
		}
	}
}

// CycleSelectLeft moves the select option backward.
func (fd *FormData) CycleSelectLeft() {
	f := fd.FocusedField()
	if f == nil || f.Type != FieldSelect {
		return
	}
	if len(f.Options) == 0 {
		return
	}
	f.SelectedIdx = (f.SelectedIdx - 1 + len(f.Options)) % len(f.Options)
}

// CycleSelectRight moves the select option forward.
func (fd *FormData) CycleSelectRight() {
	f := fd.FocusedField()
	if f == nil || f.Type != FieldSelect {
		return
	}
	if len(f.Options) == 0 {
		return
	}
	f.SelectedIdx = (f.SelectedIdx + 1) % len(f.Options)
}

// ToggleField toggles a boolean field.
func (fd *FormData) ToggleField() {
	f := fd.FocusedField()
	if f == nil || f.Type != FieldToggle {
		return
	}
	f.BoolValue = !f.BoolValue
}

// InsertChar inserts a character at the cursor position in the editing field.
func (fd *FormData) InsertChar(ch rune) {
	f := fd.FocusedField()
	if f == nil || !f.Editing {
		return
	}
	if f.Type == FieldNumber {
		if ch < '0' || ch > '9' {
			return
		}
	}
	if f.CursorPos > len(f.Value) {
		f.CursorPos = len(f.Value)
	}
	f.Value = f.Value[:f.CursorPos] + string(ch) + f.Value[f.CursorPos:]
	f.CursorPos++
}

// DeleteChar deletes the character before the cursor.
func (fd *FormData) DeleteChar() {
	f := fd.FocusedField()
	if f == nil || !f.Editing || f.CursorPos <= 0 {
		return
	}
	f.Value = f.Value[:f.CursorPos-1] + f.Value[f.CursorPos:]
	f.CursorPos--
}

// MoveCursorLeft moves the editing cursor left.
func (fd *FormData) MoveCursorLeft() {
	f := fd.FocusedField()
	if f == nil || !f.Editing || f.CursorPos <= 0 {
		return
	}
	f.CursorPos--
}

// MoveCursorRight moves the editing cursor right.
func (fd *FormData) MoveCursorRight() {
	f := fd.FocusedField()
	if f == nil || !f.Editing || f.CursorPos >= len(f.Value) {
		return
	}
	f.CursorPos++
}

// StartEditing enters editing mode for the focused field.
func (fd *FormData) StartEditing() {
	f := fd.FocusedField()
	if f == nil {
		return
	}
	switch f.Type {
	case FieldToggle:
		f.BoolValue = !f.BoolValue
	case FieldSelect:
		fd.CycleSelectRight()
	case FieldText, FieldPassword, FieldNumber:
		f.Editing = true
		f.CursorPos = len(f.Value)
	}
}

// --- Path autocompletion ---

// ComputeCompletions generates filesystem path matches for the focused field.
func (fd *FormData) ComputeCompletions() {
	f := fd.FocusedField()
	if f == nil || !f.PathComplete || !f.Editing {
		fd.completions = nil
		fd.compVisible = false
		return
	}
	fd.completions = pathCompletions(f.Value, f.Extensions, f.DirOnly)
	fd.compIdx = 0
	fd.compVisible = len(fd.completions) > 0
}

// CycleCompletion applies the current completion and advances to the next.
func (fd *FormData) CycleCompletion() bool {
	if !fd.compVisible || len(fd.completions) == 0 {
		return false
	}
	f := fd.FocusedField()
	if f == nil {
		return false
	}
	if len(fd.completions) == 0 {
		return false
	}
	f.Value = fd.completions[fd.compIdx]
	f.CursorPos = len(f.Value)
	fd.compIdx = (fd.compIdx + 1) % len(fd.completions)
	// Recompute: if the completion is a directory, show its contents.
	if strings.HasSuffix(f.Value, "/") {
		fd.completions = pathCompletions(f.Value, f.Extensions, f.DirOnly)
		fd.compIdx = 0
		fd.compVisible = len(fd.completions) > 0
	}
	return true
}

// CompletionVisible returns whether the completion dropdown is active.
func (fd *FormData) CompletionVisible() bool {
	return fd.compVisible
}

// HideCompletions dismisses the completion dropdown.
func (fd *FormData) HideCompletions() {
	fd.compVisible = false
	fd.completions = nil
}

// pathCompletions returns filesystem entries matching the partial path.
func pathCompletions(partial string, extensions []string, dirOnly bool) []string {
	if partial == "" {
		partial = "./"
	}

	dir := partial
	prefix := ""

	// If partial doesn't end with /, treat last component as the prefix to match.
	if !strings.HasSuffix(partial, "/") {
		dir = filepath.Dir(partial)
		prefix = filepath.Base(partial)
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}

	var matches []string
	for _, e := range entries {
		name := e.Name()

		// Skip hidden files unless the prefix starts with a dot.
		if strings.HasPrefix(name, ".") && !strings.HasPrefix(prefix, ".") {
			continue
		}

		if prefix != "" && !strings.HasPrefix(strings.ToLower(name), strings.ToLower(prefix)) {
			continue
		}

		full := filepath.Join(dir, name)
		if e.IsDir() {
			matches = append(matches, full+"/")
			continue
		}

		if dirOnly {
			continue
		}

		// Filter by extensions if specified.
		if len(extensions) > 0 {
			ext := strings.ToLower(filepath.Ext(name))
			matched := false
			for _, allowed := range extensions {
				if ext == allowed {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
		}

		matches = append(matches, full)
	}

	sort.Strings(matches)
	if len(matches) > maxCompletions {
		matches = matches[:maxCompletions]
	}
	return matches
}

// BuildArgs converts the form state into h2kvmctl CLI arguments.
func (fd *FormData) BuildArgs() []string {
	var args []string

	for i := range fd.Categories {
		cat := &fd.Categories[i]
		// Skip hidden categories.
		if cat.ShowWhen != nil && !cat.ShowWhen(fd) {
			continue
		}

		for j := range cat.Fields {
			f := &cat.Fields[j]
			switch f.Type {
			case FieldToggle:
				if f.BoolValue {
					args = append(args, f.Flag)
				}
			case FieldSelect:
				val := f.CLIValue()
				if val != "" {
					args = append(args, f.Flag, val)
				}
			case FieldText, FieldPassword:
				if f.Value != "" {
					args = append(args, f.Flag, f.Value)
				}
			case FieldNumber:
				if f.Value != "" {
					if _, err := strconv.Atoi(f.Value); err == nil {
						args = append(args, f.Flag, f.Value)
					}
				}
			}
		}
	}

	return args
}

// BuildYAML converts the form state into a YAML config string suitable for
// h2kvmctl --config. Field labels are used as YAML keys (they match the
// Python argparse dest names).
func (fd *FormData) BuildYAML() string {
	var b strings.Builder
	b.WriteString("# Generated by zkvm standalone mode\n")

	for i := range fd.Categories {
		cat := &fd.Categories[i]
		if cat.ShowWhen != nil && !cat.ShowWhen(fd) {
			continue
		}

		wroteHeader := false
		for j := range cat.Fields {
			f := &cat.Fields[j]
			line := ""

			switch f.Type {
			case FieldToggle:
				if f.BoolValue {
					line = fmt.Sprintf("%s: true", f.Label)
				}
				// Omit false toggles (use defaults).
			case FieldSelect:
				val := f.CLIValue()
				if val != "" {
					line = fmt.Sprintf("%s: %s", f.Label, val)
				}
			case FieldText, FieldPassword:
				if f.Value != "" {
					label := f.Label
					// Unified source field → emit the right YAML key based on file extension.
					if label == "source" {
						yamlKey, _ := detectSourceFormat(f.Value)
						label = yamlKey
					}
					line = fmt.Sprintf("%s: %s", label, yamlQuote(f.Value))
				}
			case FieldNumber:
				if f.Value != "" {
					if _, err := strconv.Atoi(f.Value); err == nil {
						line = fmt.Sprintf("%s: %s", f.Label, f.Value)
					}
				}
			}

			if line != "" {
				if !wroteHeader {
					b.WriteString(fmt.Sprintf("\n# %s\n", cat.Name))
					wroteHeader = true
				}
				b.WriteString(line)
				b.WriteString("\n")
			}
		}
	}

	return b.String()
}

// yamlQuote wraps a string value in quotes if it contains special characters.
func yamlQuote(s string) string {
	for _, ch := range s {
		switch ch {
		case ':', '#', '[', ']', '{', '}', ',', '&', '*', '!', '|', '>', '\'', '"', '%', '@', '`':
			return fmt.Sprintf("%q", s)
		}
	}
	// Quote strings that look like booleans or numbers.
	lower := strings.ToLower(s)
	if lower == "true" || lower == "false" || lower == "yes" || lower == "no" || lower == "null" {
		return fmt.Sprintf("%q", s)
	}
	return s
}

// Styles for form rendering.
var (
	catExpandedStyle  = lipgloss.NewStyle().Bold(true).Foreground(theme.Orange)
	catCollapsedStyle = lipgloss.NewStyle().Bold(true).Foreground(theme.CoralLight)
	catFocusedStyle   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#FFFFFF")).Background(theme.Orange)
	fieldLabelStyle   = lipgloss.NewStyle().Foreground(theme.CoralLight)
	fieldValueStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("#FFFFFF"))
	fieldFocusedStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("#FFFFFF")).Background(theme.Coral)
	fieldEditStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#333333"))
	placeholderStyle  = lipgloss.NewStyle().Foreground(theme.Dim).Italic(true)
	toggleOnStyle     = lipgloss.NewStyle().Bold(true).Foreground(theme.Green)
	toggleOffStyle    = lipgloss.NewStyle().Foreground(theme.Dim)
	selectStyle       = lipgloss.NewStyle().Foreground(theme.Cyan)
	compStyle         = lipgloss.NewStyle().Foreground(theme.Dim)
	compSelectedStyle = lipgloss.NewStyle().Foreground(theme.Cyan).Bold(true)

	// Input box styles — MarginLeft for consistent indent with borders.
	inputBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#444444")).
			Padding(0, 1).MarginLeft(3)
	inputBoxFocusedStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Orange).
				Padding(0, 1).MarginLeft(3)
	inputBoxEditStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Cyan).
				Padding(0, 1).MarginLeft(3)
	selectBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#444444")).
			Padding(0, 1).MarginLeft(3)
	selectBoxFocusedStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(theme.Orange).
				Padding(0, 1).MarginLeft(3)
)

// Render draws the full form as a string. formWidth constrains the width.
func (fd *FormData) Render(formWidth int) string {
	var b strings.Builder
	vis := fd.VisibleCategories()

	for vi, catIdx := range vis {
		cat := &fd.Categories[catIdx]

		// Category header.
		arrow := "\u25b8" // collapsed arrow
		if cat.Expanded {
			arrow = "\u25be" // expanded arrow
		}

		headerText := fmt.Sprintf(" %s %s", arrow, cat.Name)
		if vi == fd.FocusCat && !fd.InCategory {
			b.WriteString(catFocusedStyle.Render(headerText))
		} else if cat.Expanded {
			b.WriteString(catExpandedStyle.Render(headerText))
		} else {
			b.WriteString(catCollapsedStyle.Render(headerText))
		}
		b.WriteString("\n")

		if !cat.Expanded {
			continue
		}

		// Fields.
		boxW := formWidth - 8 // width for input boxes
		if boxW < 20 {
			boxW = 20
		}

		for fi := range cat.Fields {
			f := &cat.Fields[fi]
			isFocused := vi == fd.FocusCat && fd.InCategory && fi == fd.FocusField

			label := fmt.Sprintf("   %s", f.Label)
			if isFocused && !f.Editing {
				b.WriteString(fieldFocusedStyle.Render(label))
			} else {
				b.WriteString(fieldLabelStyle.Render(label))
			}
			b.WriteString("\n")

			var boxContent string
			var boxStyle lipgloss.Style

			switch f.Type {
			case FieldToggle:
				if f.BoolValue {
					boxContent = "◉ ON"
					boxStyle = inputBoxStyle.Copy().Width(boxW).Foreground(theme.Green)
				} else {
					boxContent = "○ OFF"
					boxStyle = inputBoxStyle.Copy().Width(boxW).Foreground(theme.Dim)
				}
				if isFocused {
					boxStyle = boxStyle.BorderForeground(theme.Orange)
				}

			case FieldSelect:
				boxContent = "◂ " + f.DisplayValue() + " ▸"
				if isFocused {
					boxStyle = selectBoxFocusedStyle.Copy().Width(boxW).Foreground(theme.Cyan)
				} else {
					boxStyle = selectBoxStyle.Copy().Width(boxW).Foreground(theme.Cyan)
				}

			case FieldPassword:
				if f.Editing {
					boxContent = renderEditingField(f)
					boxStyle = inputBoxEditStyle.Copy().Width(boxW)
				} else if f.Value == "" {
					boxContent = f.Placeholder
					boxStyle = inputBoxStyle.Copy().Width(boxW).Foreground(theme.Dim)
					if isFocused {
						boxStyle = boxStyle.BorderForeground(theme.Orange)
					}
				} else {
					boxContent = strings.Repeat("•", len(f.Value))
					boxStyle = inputBoxStyle.Copy().Width(boxW)
					if isFocused {
						boxStyle = boxStyle.BorderForeground(theme.Orange)
					}
				}

			default: // FieldText, FieldNumber
				hint := ""
				if f.PathComplete {
					hint = "  📂"
				}
				if f.Editing {
					boxContent = renderEditingField(f)
					boxStyle = inputBoxEditStyle.Copy().Width(boxW)
				} else if f.Value == "" {
					boxContent = f.Placeholder + hint
					boxStyle = inputBoxStyle.Copy().Width(boxW).Foreground(theme.Dim)
					if isFocused {
						boxStyle = boxStyle.BorderForeground(theme.Orange)
					}
				} else {
					boxContent = f.Value + hint
					boxStyle = inputBoxStyle.Copy().Width(boxW)
					if isFocused {
						boxStyle = boxStyle.BorderForeground(theme.Orange)
					}
				}
			}

			b.WriteString(boxStyle.Render(boxContent))
			b.WriteString("\n")

			// Show detected format below the unified source field.
			if f.Label == "source" && f.Value != "" {
				_, prettyLabel := detectSourceFormat(f.Value)
				detectedStyle := lipgloss.NewStyle().Foreground(theme.Green).Italic(true)
				b.WriteString("   " + detectedStyle.Render("Detected: "+prettyLabel) + "\n")
			}

			// Show path completion dropdown below the editing field.
			if f.Editing && f.PathComplete && fd.compVisible && isFocused {
				for ci, comp := range fd.completions {
					if ci == fd.compIdx {
						b.WriteString(compSelectedStyle.Render(fmt.Sprintf("   ► %s", comp)))
					} else {
						b.WriteString(compStyle.Render(fmt.Sprintf("     %s", comp)))
					}
					b.WriteString("\n")
				}
			}
		}
	}

	return b.String()
}

// renderEditingField renders a text field in editing mode with cursor.
func renderEditingField(f *Field) string {
	val := f.Value
	if f.Type == FieldPassword {
		val = strings.Repeat("*", len([]rune(val)))
	}

	runes := []rune(val)
	if f.CursorPos > len(runes) {
		f.CursorPos = len(runes)
	}

	// Show cursor as a block character.
	before := string(runes[:f.CursorPos])
	var cursor, after string
	if f.CursorPos < len(runes) {
		cursor = string(runes[f.CursorPos])
		after = string(runes[f.CursorPos+1:])
	} else {
		cursor = " "
		after = ""
	}

	cursorStyle := lipgloss.NewStyle().Reverse(true)
	return before + cursorStyle.Render(cursor) + after
}

// TotalVisibleRows returns the total number of rendered rows for scroll calculations.
func (fd *FormData) TotalVisibleRows() int {
	count := 0
	vis := fd.VisibleCategories()
	for _, catIdx := range vis {
		cat := &fd.Categories[catIdx]
		count++ // category header
		if cat.Expanded {
			count += len(cat.Fields)
		}
	}
	return count
}

// FocusRow returns the row number of the currently focused item.
func (fd *FormData) FocusRow() int {
	row := 0
	vis := fd.VisibleCategories()
	for vi, catIdx := range vis {
		if vi == fd.FocusCat && !fd.InCategory {
			return row
		}
		row++ // category header line
		cat := &fd.Categories[catIdx]
		if cat.Expanded {
			for fi := range cat.Fields {
				if vi == fd.FocusCat && fd.InCategory && fi == fd.FocusField {
					return row
				}
				// Each field renders as: label (1) + box border top (1) + box content (1) + box border bottom (1) = 4 lines
				// Plus optional "Detected:" hint line for source field
				row += 4
				f := &cat.Fields[fi]
				if f.Label == "source" && f.Value != "" {
					row++ // "Detected: ..." hint line
				}
			}
		}
	}
	return row
}
