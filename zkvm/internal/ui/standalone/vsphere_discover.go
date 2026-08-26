// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// govc discovery timeout.
const govcTimeout = 30 * time.Second

// Cached govc path (resolved once).
var (
	govcOnce sync.Once
	govcPath string
	govcErr  error
)

func resolveGovc() (string, error) {
	govcOnce.Do(func() {
		govcPath, govcErr = exec.LookPath("govc")
		if govcErr != nil {
			govcErr = fmt.Errorf("govc not found in PATH — install: curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz | sudo tar xzf - -C /usr/local/bin govc")
		}
	})
	return govcPath, govcErr
}

// VsphereVMInfo holds basic VM metadata from govc.
type VsphereVMInfo struct {
	Name       string `json:"name"`
	GuestName  string `json:"guest_name"`
	MemoryMB   int    `json:"memory_mb"`
	NumCPU     int    `json:"num_cpu"`
	PowerState string `json:"power_state"`
	Path       string `json:"path"`
	Selected   bool   `json:"-"`
}

// DatastoreInfo holds datastore metadata from govc.
type DatastoreInfo struct {
	Name     string `json:"name"`
	Type     string `json:"type"`
	Capacity string `json:"capacity"`
	Free     string `json:"free"`
}

// VSphereClient wraps govc commands with pre-built environment.
type VSphereClient struct {
	env []string
	dc  string
}

// NewVSphereClient creates a client from form data.
func NewVSphereClient(form *FormData) *VSphereClient {
	return &VSphereClient{
		env: govcEnv(form),
		dc:  form.GetFieldValue("dc_name"),
	}
}

// govcEnv builds environment variables for govc from form fields.
func govcEnv(form *FormData) []string {
	env := os.Environ()

	vcenter := form.GetFieldValue("vcenter")
	user := form.GetFieldValue("vc_user")
	password := form.GetFieldValue("vc_password")
	dc := form.GetFieldValue("dc_name")
	insecure := form.GetFieldBool("vc_insecure")

	// Try password from env var if not set directly.
	if password == "" {
		if envVar := form.GetFieldValue("vc_password_env"); envVar != "" {
			password = os.Getenv(envVar)
		}
	}

	if vcenter != "" {
		env = append(env, fmt.Sprintf("GOVC_URL=https://%s/sdk", vcenter))
	}
	if user != "" {
		env = append(env, fmt.Sprintf("GOVC_USERNAME=%s", user))
	}
	if password != "" {
		env = append(env, fmt.Sprintf("GOVC_PASSWORD=%s", password))
	}
	if dc != "" {
		env = append(env, fmt.Sprintf("GOVC_DATACENTER=%s", dc))
	}
	if insecure {
		env = append(env, "GOVC_INSECURE=1")
	}

	return env
}

// datacenter returns the configured datacenter or default.
func (c *VSphereClient) datacenter() string {
	if c.dc != "" {
		return c.dc
	}
	return "ha-datacenter"
}

// govcCmd creates an exec.Cmd with timeout and env set.
func (c *VSphereClient) govcCmd(ctx context.Context, args ...string) (*exec.Cmd, error) {
	path, err := resolveGovc()
	if err != nil {
		return nil, err
	}
	cmd := exec.CommandContext(ctx, path, args...)
	cmd.Env = c.env
	return cmd, nil
}

// DiscoverVMs lists VMs from vCenter. Blocking — run in a goroutine.
func (c *VSphereClient) DiscoverVMs() ([]VsphereVMInfo, error) {
	ctx, cancel := context.WithTimeout(context.Background(), govcTimeout)
	defer cancel()

	dc := c.datacenter()

	// Step 1: list VM paths.
	cmd, err := c.govcCmd(ctx, "ls", fmt.Sprintf("/%s/vm/", dc))
	if err != nil {
		return nil, err
	}
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("govc ls /%s/vm/ failed: %w — verify vCenter credentials (GOVC_URL, GOVC_USERNAME, GOVC_PASSWORD) and datacenter name are correct", dc, err)
	}

	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	var vms []VsphereVMInfo
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.Split(line, "/")
		name := parts[len(parts)-1]
		vms = append(vms, VsphereVMInfo{
			Name: name,
			Path: line,
		})
	}

	// Step 2: enrich with details (batch vm.info).
	if len(vms) > 0 {
		c.enrichVMs(ctx, vms)
	}

	return vms, nil
}

// enrichVMs fetches CPU/memory/power for discovered VMs.
func (c *VSphereClient) enrichVMs(ctx context.Context, vms []VsphereVMInfo) {
	// Collect paths for batch query.
	paths := make([]string, len(vms))
	for i, vm := range vms {
		paths[i] = vm.Path
	}

	args := append([]string{"vm.info", "-json"}, paths...)
	cmd, err := c.govcCmd(ctx, args...)
	if err != nil {
		return
	}
	out, err := cmd.Output()
	if err != nil {
		return // best effort — VMs still have name/path
	}

	var result struct {
		VirtualMachines []struct {
			Config struct {
				Name          string `json:"name"`
				GuestFullName string `json:"guestFullName"`
				Hardware      struct {
					MemoryMB int `json:"memoryMB"`
					NumCPU   int `json:"numCPU"`
				} `json:"hardware"`
			} `json:"config"`
			Runtime struct {
				PowerState string `json:"powerState"`
			} `json:"runtime"`
		} `json:"virtualMachines"`
	}
	if err := json.Unmarshal(out, &result); err != nil {
		return
	}

	// Match by name.
	byName := make(map[string]int, len(vms))
	for i, vm := range vms {
		byName[vm.Name] = i
	}
	for _, rvm := range result.VirtualMachines {
		if idx, ok := byName[rvm.Config.Name]; ok {
			vms[idx].GuestName = rvm.Config.GuestFullName
			vms[idx].MemoryMB = rvm.Config.Hardware.MemoryMB
			vms[idx].NumCPU = rvm.Config.Hardware.NumCPU
			vms[idx].PowerState = rvm.Runtime.PowerState
		}
	}
}

// DiscoverDatastores lists datastores from vCenter.
func (c *VSphereClient) DiscoverDatastores() ([]DatastoreInfo, error) {
	ctx, cancel := context.WithTimeout(context.Background(), govcTimeout)
	defer cancel()

	cmd, err := c.govcCmd(ctx, "datastore.info", "-json")
	if err != nil {
		return nil, err
	}

	out, err := cmd.Output()
	if err != nil {
		// Fallback to ls.
		return c.discoverDatastoresFallback(ctx)
	}

	var result struct {
		Datastores []struct {
			Name    string `json:"name"`
			Summary struct {
				Type      string `json:"type"`
				Capacity  int64  `json:"capacity"`
				FreeSpace int64  `json:"freeSpace"`
			} `json:"summary"`
		} `json:"datastores"`
	}
	if err := json.Unmarshal(out, &result); err != nil {
		return nil, fmt.Errorf("failed to parse govc datastore.info JSON response: %w — the vCenter may have returned unexpected output; try running 'govc datastore.info -json' manually", err)
	}

	var dss []DatastoreInfo
	for _, ds := range result.Datastores {
		dss = append(dss, DatastoreInfo{
			Name:     ds.Name,
			Type:     ds.Summary.Type,
			Capacity: formatBytes(ds.Summary.Capacity),
			Free:     formatBytes(ds.Summary.FreeSpace),
		})
	}
	return dss, nil
}

func (c *VSphereClient) discoverDatastoresFallback(ctx context.Context) ([]DatastoreInfo, error) {
	dc := c.datacenter()
	cmd, err := c.govcCmd(ctx, "ls", fmt.Sprintf("/%s/datastore/", dc))
	if err != nil {
		return nil, err
	}
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("govc ls /%s/datastore/ failed: %w — verify vCenter credentials and that the datacenter %q exists", dc, err, dc)
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	var dss []DatastoreInfo
	for _, line := range lines {
		parts := strings.Split(strings.TrimSpace(line), "/")
		if len(parts) > 0 {
			dss = append(dss, DatastoreInfo{Name: parts[len(parts)-1]})
		}
	}
	return dss, nil
}

// --- Streaming support for TUI log panel ---

// StreamEvent carries one line of govc output or a completion/error signal.
type StreamEvent struct {
	Line string
	Err  error
	Done bool
}

// RunStream executes a govc command and streams stdout+stderr line by line.
func (c *VSphereClient) RunStream(ctx context.Context, args ...string) (<-chan StreamEvent, error) {
	cmd, err := c.govcCmd(ctx, args...)
	if err != nil {
		return nil, err
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stdout pipe for govc %s: %w", strings.Join(args, " "), err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stderr pipe for govc %s: %w", strings.Join(args, " "), err)
	}

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start govc command: %w — verify govc is installed and vCenter environment variables are set correctly", err)
	}

	ch := make(chan StreamEvent, 64)
	go func() {
		defer close(ch)
		scanner := bufio.NewScanner(io.MultiReader(stdout, stderr))
		for scanner.Scan() {
			ch <- StreamEvent{Line: scanner.Text()}
		}
		err := cmd.Wait()
		ch <- StreamEvent{Done: true, Err: err}
	}()

	return ch, nil
}

// --- Bubble Tea integration ---

// DiscoverVMsMsg carries the result of VM discovery.
type DiscoverVMsMsg struct {
	VMs []VsphereVMInfo
	Err error
}

// DiscoverLogMsg carries a streaming log line during discovery.
type DiscoverLogMsg struct {
	Line string
}

// discoverVMsCmd runs VM discovery async via tea.Cmd.
func discoverVMsCmd(form *FormData) tea.Cmd {
	return func() tea.Msg {
		client := NewVSphereClient(form)
		vms, err := client.DiscoverVMs()
		return DiscoverVMsMsg{VMs: vms, Err: err}
	}
}

// formatBytes converts bytes to human-readable string.
func formatBytes(b int64) string {
	const gb = 1024 * 1024 * 1024
	if b >= gb {
		return fmt.Sprintf("%.1f GB", float64(b)/float64(gb))
	}
	const mb = 1024 * 1024
	return fmt.Sprintf("%.0f MB", float64(b)/float64(mb))
}
