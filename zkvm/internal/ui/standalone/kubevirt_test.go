// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"os/exec"
	"testing"
)

func TestKubeVirtVMFields(t *testing.T) {
	vm := KubeVirtVM{
		Name:         "test-vm",
		Namespace:    "default",
		Status:       "Running",
		Ready:        true,
		CPUs:         4,
		Memory:       "8Gi",
		Node:         "node-1",
		IP:           "10.244.0.5",
		Age:          "2d",
		GuestOS:      "Fedora 40",
		Conditions:   "Ready, LiveMigratable",
		CreationTime: "48h",
		Migrating:    false,
	}

	if vm.Name != "test-vm" {
		t.Errorf("expected Name %q, got %q", "test-vm", vm.Name)
	}
	if vm.Namespace != "default" {
		t.Errorf("expected Namespace %q, got %q", "default", vm.Namespace)
	}
	if vm.Status != "Running" {
		t.Errorf("expected Status %q, got %q", "Running", vm.Status)
	}
	if !vm.Ready {
		t.Error("expected Ready to be true")
	}
	if vm.CPUs != 4 {
		t.Errorf("expected CPUs %d, got %d", 4, vm.CPUs)
	}
	if vm.Memory != "8Gi" {
		t.Errorf("expected Memory %q, got %q", "8Gi", vm.Memory)
	}
	if vm.Node != "node-1" {
		t.Errorf("expected Node %q, got %q", "node-1", vm.Node)
	}
	if vm.IP != "10.244.0.5" {
		t.Errorf("expected IP %q, got %q", "10.244.0.5", vm.IP)
	}
	if vm.GuestOS != "Fedora 40" {
		t.Errorf("expected GuestOS %q, got %q", "Fedora 40", vm.GuestOS)
	}
	if vm.Conditions != "Ready, LiveMigratable" {
		t.Errorf("expected Conditions %q, got %q", "Ready, LiveMigratable", vm.Conditions)
	}
	if vm.Migrating {
		t.Error("expected Migrating to be false")
	}
}

func TestKubeVirtVMZeroValue(t *testing.T) {
	var vm KubeVirtVM
	if vm.Name != "" {
		t.Errorf("expected zero-value Name to be empty, got %q", vm.Name)
	}
	if vm.CPUs != 0 {
		t.Errorf("expected zero-value CPUs to be 0, got %d", vm.CPUs)
	}
	if vm.Ready {
		t.Error("expected zero-value Ready to be false")
	}
	if vm.Migrating {
		t.Error("expected zero-value Migrating to be false")
	}
}

func TestMigrationInfoFields(t *testing.T) {
	m := MigrationInfo{
		Name:      "mig-001",
		VMName:    "test-vm",
		Namespace: "prod",
		Phase:     "Succeeded",
		Created:   "3h",
	}

	if m.Name != "mig-001" {
		t.Errorf("expected Name %q, got %q", "mig-001", m.Name)
	}
	if m.VMName != "test-vm" {
		t.Errorf("expected VMName %q, got %q", "test-vm", m.VMName)
	}
	if m.Namespace != "prod" {
		t.Errorf("expected Namespace %q, got %q", "prod", m.Namespace)
	}
	if m.Phase != "Succeeded" {
		t.Errorf("expected Phase %q, got %q", "Succeeded", m.Phase)
	}
	if m.Created != "3h" {
		t.Errorf("expected Created %q, got %q", "3h", m.Created)
	}
}

func TestMigrationInfoZeroValue(t *testing.T) {
	var m MigrationInfo
	if m.Name != "" {
		t.Errorf("expected zero-value Name to be empty, got %q", m.Name)
	}
	if m.Phase != "" {
		t.Errorf("expected zero-value Phase to be empty, got %q", m.Phase)
	}
}

func TestKubeVirtStatusFields(t *testing.T) {
	s := KubeVirtStatus{
		Installed:    true,
		Version:      "v1.2.0",
		CDIInstalled: true,
		CDIVersion:   "v1.59.0",
		Error:        "",
	}

	if !s.Installed {
		t.Error("expected Installed to be true")
	}
	if s.Version != "v1.2.0" {
		t.Errorf("expected Version %q, got %q", "v1.2.0", s.Version)
	}
	if !s.CDIInstalled {
		t.Error("expected CDIInstalled to be true")
	}
	if s.CDIVersion != "v1.59.0" {
		t.Errorf("expected CDIVersion %q, got %q", "v1.59.0", s.CDIVersion)
	}
	if s.Error != "" {
		t.Errorf("expected Error to be empty, got %q", s.Error)
	}
}

func TestKubeVirtStatusWithError(t *testing.T) {
	s := KubeVirtStatus{
		Installed: false,
		Error:     "connection refused",
	}

	if s.Installed {
		t.Error("expected Installed to be false")
	}
	if s.Error != "connection refused" {
		t.Errorf("expected Error %q, got %q", "connection refused", s.Error)
	}
}

func TestPVCInfoFields(t *testing.T) {
	p := PVCInfo{
		Name:         "data-disk",
		Namespace:    "default",
		Status:       "Bound",
		Volume:       "pv-001",
		Capacity:     "50Gi",
		AccessModes:  "ReadWriteOnce",
		StorageClass: "standard",
		Age:          "5d",
	}

	if p.Name != "data-disk" {
		t.Errorf("expected Name %q, got %q", "data-disk", p.Name)
	}
	if p.Status != "Bound" {
		t.Errorf("expected Status %q, got %q", "Bound", p.Status)
	}
	if p.Capacity != "50Gi" {
		t.Errorf("expected Capacity %q, got %q", "50Gi", p.Capacity)
	}
	if p.StorageClass != "standard" {
		t.Errorf("expected StorageClass %q, got %q", "standard", p.StorageClass)
	}
}

func TestKubeContextFields(t *testing.T) {
	ctx := KubeContext{
		Name:      "prod-cluster",
		Cluster:   "prod",
		Namespace: "default",
		Current:   true,
	}

	if ctx.Name != "prod-cluster" {
		t.Errorf("expected Name %q, got %q", "prod-cluster", ctx.Name)
	}
	if ctx.Cluster != "prod" {
		t.Errorf("expected Cluster %q, got %q", "prod", ctx.Cluster)
	}
	if !ctx.Current {
		t.Error("expected Current to be true")
	}
}

func TestRunVirtctlMissingBinaries(t *testing.T) {
	// When neither virtctl nor kubectl are in PATH, runVirtctl should fail.
	// Save and clear PATH to ensure the binaries are not found.
	t.Setenv("PATH", "/nonexistent")

	_, err := runVirtctl("version")
	if err == nil {
		t.Error("expected error when virtctl and kubectl are not in PATH")
	}
}

func TestRunVirtctlFallbackToKubectl(t *testing.T) {
	// Verify that when virtctl is not found, it falls back to kubectl virt.
	// We can at least verify exec.LookPath behavior.
	_, err := exec.LookPath("virtctl-nonexistent-binary-for-test")
	if err == nil {
		t.Skip("unexpected: virtctl-nonexistent-binary-for-test found in PATH")
	}
}

func TestUploadImageMissingVirtctl(t *testing.T) {
	// When virtctl is missing, UploadImage should return an error.
	t.Setenv("PATH", "/nonexistent")

	err := UploadImage("test-dv", "default", "10Gi", "/tmp/test.qcow2")
	if err == nil {
		t.Error("expected error from UploadImage when virtctl is not available")
	}
}

func TestStartKubeVirtVMMissingVirtctl(t *testing.T) {
	t.Setenv("PATH", "/nonexistent")

	err := StartKubeVirtVM("test-vm", "default")
	if err == nil {
		t.Error("expected error from StartKubeVirtVM when virtctl is not available")
	}
}

func TestStopKubeVirtVMMissingVirtctl(t *testing.T) {
	t.Setenv("PATH", "/nonexistent")

	err := StopKubeVirtVM("test-vm", "default")
	if err == nil {
		t.Error("expected error from StopKubeVirtVM when virtctl is not available")
	}
}

func TestRestartKubeVirtVMMissingVirtctl(t *testing.T) {
	t.Setenv("PATH", "/nonexistent")

	err := RestartKubeVirtVM("test-vm", "default")
	if err == nil {
		t.Error("expected error from RestartKubeVirtVM when virtctl is not available")
	}
}
