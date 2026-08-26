// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os/exec"
	"strings"
)

// KubeContext represents a kubectl context.
type KubeContext struct {
	Name      string
	Cluster   string
	Namespace string
	Current   bool
}

// KubeVirtVM represents a KubeVirt virtual machine instance.
type KubeVirtVM struct {
	Name         string
	Namespace    string
	Status       string // Running, Stopped, Scheduling, etc.
	Ready        bool
	CPUs         int
	Memory       string
	Node         string
	IP           string
	Age          string
	GuestOS      string // status.guestOSInfo.name
	Conditions   string // summary of true conditions
	CreationTime string // human-readable age
	Migrating    bool   // active migration targets this VM
}

// MigrationInfo represents a KubeVirt VirtualMachineInstanceMigration.
type MigrationInfo struct {
	Name      string
	VMName    string
	Namespace string
	Phase     string
	Created   string
}

// KubeVirtStatus holds the installation status of KubeVirt and CDI.
type KubeVirtStatus struct {
	Installed    bool
	Version      string
	CDIInstalled bool
	CDIVersion   string
	Error        string // non-empty when API check failed (shown in UI)
}

// PVCInfo represents a Kubernetes PersistentVolumeClaim.
type PVCInfo struct {
	Name         string
	Namespace    string
	Status       string
	Volume       string
	Capacity     string
	AccessModes  string
	StorageClass string
	Age          string
}

// runVirtctl executes virtctl or falls back to kubectl virt plugin.
func runVirtctl(args ...string) (string, error) {
	if _, err := exec.LookPath("virtctl"); err == nil {
		cmd := exec.Command("virtctl", args...)
		out, err := cmd.CombinedOutput()
		return strings.TrimSpace(string(out)), err
	}
	// Fallback: kubectl virt subcommand.
	args = append([]string{"virt"}, args...)
	cmd := exec.Command("kubectl", args...)
	out, err := cmd.CombinedOutput()
	return strings.TrimSpace(string(out)), err
}

// StartKubeVirtVM starts a stopped KubeVirt VM.
func StartKubeVirtVM(name, namespace string) error {
	out, err := runVirtctl("start", name, "-n", namespace)
	if err != nil {
		return fmt.Errorf("failed to start VM '%s': %s. Ensure virtctl is installed and the VM exists", name, out)
	}
	return nil
}

// StopKubeVirtVM stops a running KubeVirt VM.
func StopKubeVirtVM(name, namespace string) error {
	out, err := runVirtctl("stop", name, "-n", namespace)
	if err != nil {
		return fmt.Errorf("failed to stop VM '%s': %s. The VM may already be stopped", name, out)
	}
	return nil
}

// RestartKubeVirtVM restarts a KubeVirt VM.
func RestartKubeVirtVM(name, namespace string) error {
	out, err := runVirtctl("restart", name, "-n", namespace)
	if err != nil {
		return fmt.Errorf("failed to restart VM '%s': %s. The VM may not be running", name, out)
	}
	return nil
}

// OpenKubeVirtConsole launches virtctl vnc for the given VM.
func OpenKubeVirtConsole(name, namespace string) *exec.Cmd {
	cmd := exec.Command("virtctl", "vnc", name, "-n", namespace)
	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.Stdin = nil
	if err := cmd.Start(); err != nil {
		return nil
	}
	return cmd
}

// UploadImage uploads a disk image to a PVC via CDI using virtctl.
func UploadImage(name, namespace, size, imagePath string) error {
	out, err := runVirtctl("image-upload", "dv", name,
		"--namespace", namespace,
		"--size", size,
		"--image-path", imagePath,
		"--insecure")
	if err != nil {
		return fmt.Errorf("failed to upload disk image to PVC '%s': %s. Check that CDI is installed and virtctl is available", name, out)
	}
	return nil
}
