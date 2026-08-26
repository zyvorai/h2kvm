// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"encoding/xml"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

// VMGraphics holds display connection info extracted from domain XML.
type VMGraphics struct {
	Type   string // "vnc", "spice", "none"
	Port   int    // -1 if autoport/not running
	Listen string // "127.0.0.1", "0.0.0.0"
	WSPort int    // websocket port if available (-1 otherwise)
}

// VMInfo holds parsed information about a libvirt domain.
type VMInfo struct {
	Name      string
	State     string   // "running", "shut off", "paused", etc.
	UUID      string
	CPUs      int
	MemoryMiB int
	Autostart string   // "enable", "disable"
	DiskPaths []string // extracted from dumpxml
	Graphics  VMGraphics
}

// virshCmd returns the virsh command prefix, using sudo when not root.
func virshCmd() (string, []string) {
	if os.Getuid() == 0 {
		return "virsh", nil
	}
	return "sudo", []string{"virsh"}
}

// runVirsh executes a virsh subcommand and returns its combined output.
func runVirsh(args ...string) (string, error) {
	bin, prefix := virshCmd()
	fullArgs := append(prefix, args...)
	cmd := exec.Command(bin, fullArgs...)
	out, err := cmd.CombinedOutput()
	return strings.TrimSpace(string(out)), err
}

// ListVMs returns all defined VMs with detailed info.
func ListVMs() ([]VMInfo, error) {
	out, err := runVirsh("list", "--all", "--name")
	if err != nil {
		return nil, fmt.Errorf("virsh list failed: %w: %s — ensure libvirtd is running (sudo systemctl start libvirtd) and virsh is installed", err, out)
	}

	var vms []VMInfo
	for _, name := range strings.Split(out, "\n") {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		vm := VMInfo{Name: name}
		fillDomInfo(&vm)
		fillDomainXML(&vm)
		vms = append(vms, vm)
	}
	return vms, nil
}

// fillDomInfo parses `virsh dominfo` output into a VMInfo.
func fillDomInfo(vm *VMInfo) {
	out, err := runVirsh("dominfo", vm.Name)
	if err != nil {
		vm.State = "unknown"
		return
	}
	for _, line := range strings.Split(out, "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])

		switch key {
		case "State":
			vm.State = val
		case "UUID":
			vm.UUID = val
		case "CPU(s)":
			vm.CPUs, _ = strconv.Atoi(val)
		case "Max memory":
			// Value is like "2097152 KiB".
			fields := strings.Fields(val)
			if len(fields) >= 1 {
				if kib, err := strconv.Atoi(fields[0]); err == nil {
					vm.MemoryMiB = kib / 1024
				}
			}
		case "Autostart":
			vm.Autostart = val
		}
	}
}

// xmlDomain is a minimal representation of a libvirt domain XML.
type xmlDomain struct {
	XMLName xml.Name   `xml:"domain"`
	Devices xmlDevices `xml:"devices"`
}

type xmlDevices struct {
	Disks      []xmlDisk       `xml:"disk"`
	Graphics   []xmlGraphics   `xml:"graphics"`
	Interfaces []xmlInterface  `xml:"interface"`
}

type xmlInterface struct {
	Type   string          `xml:"type,attr"`
	Source xmlIfaceSource  `xml:"source"`
}

type xmlIfaceSource struct {
	Network string `xml:"network,attr"`
	Bridge  string `xml:"bridge,attr"`
}

type xmlDisk struct {
	Device string    `xml:"device,attr"`
	Source xmlSource `xml:"source"`
}

type xmlSource struct {
	File string `xml:"file,attr"`
	Dev  string `xml:"dev,attr"`
}

type xmlGraphics struct {
	Type     string `xml:"type,attr"`
	Port     string `xml:"port,attr"`
	Autoport string `xml:"autoport,attr"`
	Listen   string `xml:"listen,attr"`
	WSPort   string `xml:"websocket,attr"`
}

// fillDomainXML extracts disk paths and graphics info from `virsh dumpxml`.
func fillDomainXML(vm *VMInfo) {
	out, err := runVirsh("dumpxml", vm.Name)
	if err != nil {
		vm.Graphics = VMGraphics{Type: "none", Port: -1, WSPort: -1}
		return
	}

	var domain xmlDomain
	if err := xml.Unmarshal([]byte(out), &domain); err != nil {
		vm.Graphics = VMGraphics{Type: "none", Port: -1, WSPort: -1}
		return
	}

	// Extract disk paths.
	for _, d := range domain.Devices.Disks {
		if d.Device != "disk" {
			continue
		}
		path := d.Source.File
		if path == "" {
			path = d.Source.Dev
		}
		if path != "" {
			vm.DiskPaths = append(vm.DiskPaths, path)
		}
	}

	// Extract graphics info (prefer VNC, then SPICE).
	vm.Graphics = VMGraphics{Type: "none", Port: -1, WSPort: -1}
	for _, g := range domain.Devices.Graphics {
		gfx := VMGraphics{
			Type:   g.Type,
			Port:   -1,
			Listen: g.Listen,
			WSPort: -1,
		}
		if g.Port != "" && g.Port != "-1" {
			gfx.Port, _ = strconv.Atoi(g.Port)
		}
		if g.WSPort != "" && g.WSPort != "-1" {
			gfx.WSPort, _ = strconv.Atoi(g.WSPort)
		}
		vm.Graphics = gfx
		break // use first graphics device
	}
}

// GetVMGraphics extracts graphics info for a single VM by name.
func GetVMGraphics(name string) (VMGraphics, error) {
	out, err := runVirsh("dumpxml", name)
	if err != nil {
		return VMGraphics{Type: "none", Port: -1, WSPort: -1}, fmt.Errorf("failed to get VM graphics for %q: %w — verify the VM exists with 'virsh list --all'", name, err)
	}

	var domain xmlDomain
	if err := xml.Unmarshal([]byte(out), &domain); err != nil {
		return VMGraphics{Type: "none", Port: -1, WSPort: -1}, fmt.Errorf("failed to parse domain XML for %q: %w — the domain XML may be corrupted, try 'virsh dumpxml %s' manually", name, err, name)
	}

	for _, g := range domain.Devices.Graphics {
		gfx := VMGraphics{
			Type:   g.Type,
			Port:   -1,
			Listen: g.Listen,
			WSPort: -1,
		}
		if g.Port != "" && g.Port != "-1" {
			gfx.Port, _ = strconv.Atoi(g.Port)
		}
		if g.WSPort != "" && g.WSPort != "-1" {
			gfx.WSPort, _ = strconv.Atoi(g.WSPort)
		}
		return gfx, nil
	}

	return VMGraphics{Type: "none", Port: -1, WSPort: -1}, nil
}

// ExportToLibvirt defines a VM in libvirt. It first checks if the domain XML
// already exists at <outputDir>/libvirt/<vmName>.xml (generated during migration).
// If not, it falls back to running h2kvmctl with --emit-domain-xml --virsh-define.
func ExportToLibvirt(binaryPath, outputDir, vmName string) error {
	// Check if XML was already generated during migration.
	xmlPath := filepath.Join(outputDir, "libvirt", vmName+".xml")
	if _, err := os.Stat(xmlPath); err == nil {
		out, err := runVirsh("define", xmlPath)
		if err != nil {
			return fmt.Errorf("virsh define %s failed: %w: %s — check that the XML is valid and libvirtd is running (sudo systemctl start libvirtd)", xmlPath, err, out)
		}
		return nil
	}

	// Fallback: run h2kvmctl to generate XML and define.
	binary := findBinary(binaryPath)
	if !filepath.IsAbs(binary) {
		if abs, err := filepath.Abs(binary); err == nil {
			binary = abs
		}
	}

	// Find the qcow2 file in outputDir.
	qcow2Path := ""
	entries, err := os.ReadDir(outputDir)
	if err == nil {
		for _, e := range entries {
			if !e.IsDir() && strings.HasSuffix(e.Name(), ".qcow2") {
				qcow2Path = filepath.Join(outputDir, e.Name())
				break
			}
		}
	}

	args := []string{
		"--cmd", "local",
		"--output-dir", outputDir,
		"--emit-domain-xml",
		"--virsh-define",
	}
	if vmName != "" {
		args = append(args, "--vm-name", vmName)
	}
	if qcow2Path != "" {
		args = append(args, "--vmdk", qcow2Path)
	}
	args = append(args, "--dry-run=false")

	cmd := exec.Command(binary, args...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("h2kvmctl export to libvirt failed: %w: %s — ensure h2kvmctl is installed and the output directory contains a .qcow2 disk image", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// LaunchNoVNC starts websockify to proxy VNC and returns the web URL.
// If websockify or noVNC are not installed, it auto-installs them first.
func LaunchNoVNC(vncPort int) (url string, cmd *exec.Cmd, err error) {
	wsPath, _ := exec.LookPath("websockify")
	novncDir := findNoVNCDir()

	// Auto-install missing packages.
	if wsPath == "" || novncDir == "" {
		installed, installErr := installNoVNCPackages()
		if installErr != nil {
			return "", nil, fmt.Errorf("auto-install failed: %w (VNC port: %d)", installErr, vncPort)
		}
		if wsPath == "" {
			wsPath, _ = exec.LookPath("websockify")
		}
		if novncDir == "" {
			novncDir = findNoVNCDir()
		}
		if wsPath == "" {
			return "", nil, fmt.Errorf("websockify still not found after install (%s). VNC port: %d", installed, vncPort)
		}
	}

	webArg := ""
	if novncDir != "" {
		webArg = "--web=" + novncDir
	}

	target := fmt.Sprintf("localhost:%d", vncPort)
	args := []string{"6080", target}
	if webArg != "" {
		args = []string{webArg, "6080", target}
	}

	cmd = exec.Command(wsPath, args...)
	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.Stdin = nil
	if err := cmd.Start(); err != nil {
		return "", nil, fmt.Errorf("failed to start websockify (proxying VNC port %d to web port 6080): %w — verify websockify is installed and port 6080 is not in use", vncPort, err)
	}

	return "http://localhost:6080/vnc.html", cmd, nil
}

// findNoVNCDir locates the noVNC web directory.
func findNoVNCDir() string {
	candidates := []string{
		"/usr/share/novnc",
		"/usr/share/noVNC",
		"/usr/share/webapps/novnc",
	}
	for _, d := range candidates {
		if info, err := os.Stat(d); err == nil && info.IsDir() {
			return d
		}
	}
	return ""
}

// installNoVNCPackages detects the package manager and installs websockify + novnc.
func installNoVNCPackages() (string, error) {
	type pkgMgr struct {
		bin  string
		args []string
		desc string
	}

	managers := []pkgMgr{
		{"dnf", []string{"install", "-y", "python3-websockify", "novnc"}, "dnf"},
		{"yum", []string{"install", "-y", "python3-websockify", "novnc"}, "yum"},
		{"apt-get", []string{"install", "-y", "websockify", "novnc"}, "apt"},
		{"pacman", []string{"-S", "--noconfirm", "python-websockify", "novnc"}, "pacman"},
		{"zypper", []string{"install", "-y", "python3-websockify", "novnc"}, "zypper"},
	}

	for _, mgr := range managers {
		if _, err := exec.LookPath(mgr.bin); err != nil {
			continue
		}

		// Use sudo if not root.
		bin := mgr.bin
		args := mgr.args
		if os.Getuid() != 0 {
			args = append([]string{mgr.bin}, args...)
			bin = "sudo"
		}

		cmd := exec.Command(bin, args...)
		out, err := cmd.CombinedOutput()
		if err != nil {
			return mgr.desc, fmt.Errorf("%s install failed: %w: %s", mgr.desc, err, strings.TrimSpace(string(out)))
		}
		return mgr.desc, nil
	}

	// Fallback: install via pip.
	for _, pip := range []string{"pip3", "pip"} {
		if _, err := exec.LookPath(pip); err != nil {
			continue
		}
		cmd := exec.Command(pip, "install", "websockify")
		out, err := cmd.CombinedOutput()
		if err != nil {
			return "pip", fmt.Errorf("pip install failed: %w: %s", err, strings.TrimSpace(string(out)))
		}
		return "pip", nil
	}

	return "", fmt.Errorf("cannot auto-install websockify: no supported package manager (dnf, apt-get, pacman, zypper) or pip found — install websockify manually")
}

// SetVNCListenAll updates the VM's VNC graphics to listen on 0.0.0.0
// so it's accessible from remote hosts. Requires the VM to be shut off
// or uses live update if running.
func SetVNCListenAll(vmName string) error {
	// Try live update first (QEMU supports this).
	// If it fails, modify the persistent XML.
	xmlSnippet := `<graphics type='vnc' port='-1' autoport='yes' listen='0.0.0.0'/>`

	tmpFile, err := os.CreateTemp("", "h2kvm-vnc-*.xml")
	if err != nil {
		return fmt.Errorf("failed to create temp file for VNC XML snippet: %w", err)
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(xmlSnippet); err != nil {
		tmpFile.Close()
		return fmt.Errorf("failed to write VNC XML snippet to %s: %w", tmpFile.Name(), err)
	}
	tmpFile.Close()

	// Try updating the device.
	_, err = runVirsh("update-device", vmName, tmpFile.Name(), "--config")
	if err != nil {
		// Fallback: use sed-style approach via dumpxml + edit + define.
		return setVNCListenViaEdit(vmName)
	}
	return nil
}

// setVNCListenViaEdit dumps the domain XML, patches VNC listen, and redefines.
func setVNCListenViaEdit(vmName string) error {
	out, err := runVirsh("dumpxml", vmName, "--inactive")
	if err != nil {
		return fmt.Errorf("failed to dump domain XML for %q: %w — verify the VM exists and libvirtd is running", vmName, err)
	}

	// Replace listen='127.0.0.1' with listen='0.0.0.0' in graphics elements.
	patched := strings.ReplaceAll(out, `listen='127.0.0.1'`, `listen='0.0.0.0'`)
	patched = strings.ReplaceAll(patched, `listen="127.0.0.1"`, `listen="0.0.0.0"`)

	if patched == out {
		return nil // Already listening on 0.0.0.0 or no VNC configured.
	}

	tmpFile, err := os.CreateTemp("", "h2kvm-domain-*.xml")
	if err != nil {
		return fmt.Errorf("failed to create temp file for patched domain XML of VM %q: %w", vmName, err)
	}
	defer os.Remove(tmpFile.Name())

	if err := os.WriteFile(tmpFile.Name(), []byte(patched), 0644); err != nil {
		return fmt.Errorf("failed to write patched domain XML to %s: %w", tmpFile.Name(), err)
	}

	defOut, err := runVirsh("define", tmpFile.Name())
	if err != nil {
		return fmt.Errorf("failed to redefine VM %q with updated VNC listen address: %w: %s", vmName, err, defOut)
	}

	return nil
}

// --- Snapshot operations ---

// SnapshotInfo holds metadata about a VM snapshot.
type SnapshotInfo struct {
	Name      string
	CreatedAt string
	State     string // running, shutoff, disk-snapshot
	Current   bool
}

// ListSnapshots returns all snapshots for a VM.
func ListSnapshots(vmName string) ([]SnapshotInfo, error) {
	out, err := runVirsh("snapshot-list", vmName, "--name")
	if err != nil {
		return nil, fmt.Errorf("failed to list snapshots for VM %q: %w: %s — verify the VM exists with 'virsh list --all'", vmName, err, out)
	}

	var snaps []SnapshotInfo
	for _, name := range strings.Split(out, "\n") {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		snap := SnapshotInfo{Name: name}

		// Get snapshot info.
		info, err := runVirsh("snapshot-info", vmName, name)
		if err == nil {
			for _, line := range strings.Split(info, "\n") {
				parts := strings.SplitN(line, ":", 2)
				if len(parts) != 2 {
					continue
				}
				key := strings.TrimSpace(parts[0])
				val := strings.TrimSpace(parts[1])
				switch key {
				case "Created":
					snap.CreatedAt = val
				case "State":
					snap.State = val
				case "Current":
					snap.Current = val == "yes"
				}
			}
		}
		snaps = append(snaps, snap)
	}
	return snaps, nil
}

// CreateSnapshot creates a new snapshot for a VM.
func CreateSnapshot(vmName, snapName, description string) error {
	args := []string{"snapshot-create-as", vmName, snapName}
	if description != "" {
		args = append(args, "--description", description)
	}
	out, err := runVirsh(args...)
	if err != nil {
		return fmt.Errorf("failed to create snapshot %q for VM %q: %w: %s — the VM may need to be shut off for offline snapshots, or qemu-guest-agent installed for live snapshots", snapName, vmName, err, out)
	}
	return nil
}

// RevertSnapshot reverts a VM to a named snapshot.
func RevertSnapshot(vmName, snapName string) error {
	out, err := runVirsh("snapshot-revert", vmName, snapName)
	if err != nil {
		return fmt.Errorf("failed to revert VM %q to snapshot %q: %w: %s — ensure the snapshot exists ('virsh snapshot-list %s') and the VM is in a compatible state", vmName, snapName, err, out, vmName)
	}
	return nil
}

// DeleteSnapshot removes a snapshot from a VM.
func DeleteSnapshot(vmName, snapName string) error {
	out, err := runVirsh("snapshot-delete", vmName, snapName)
	if err != nil {
		return fmt.Errorf("failed to delete snapshot %q from VM %q: %w: %s — the snapshot may be in use or the VM may have dependent snapshots", snapName, vmName, err, out)
	}
	return nil
}

// --- Pre-flight & auto-fix ---

// PreflightVM inspects a VM's domain XML and ensures all required
// resources (networks, storage pools) are available and active.
// It returns a list of actions taken. If it cannot fix an issue,
// the error is returned.
func PreflightVM(name string) (fixes []string, err error) {
	out, err := runVirsh("dumpxml", name)
	if err != nil {
		return nil, fmt.Errorf("failed to dump domain XML for VM %q: %w — verify the VM exists with 'virsh list --all' and libvirtd is running", name, err)
	}

	var domain xmlDomain
	if err := xml.Unmarshal([]byte(out), &domain); err != nil {
		return nil, fmt.Errorf("failed to parse domain XML for VM %q: %w — the domain XML may be corrupted, try 'virsh dumpxml %s' manually to inspect", name, err, name)
	}

	// Ensure required networks exist and are active.
	seen := make(map[string]bool)
	for _, iface := range domain.Devices.Interfaces {
		netName := iface.Source.Network
		if netName == "" || seen[netName] {
			continue
		}
		seen[netName] = true

		fixed, err := ensureNetworkActive(netName)
		if err != nil {
			return fixes, fmt.Errorf("network %q: %w", netName, err)
		}
		fixes = append(fixes, fixed...)
	}

	// Ensure storage pool for each disk is active.
	for _, d := range domain.Devices.Disks {
		if d.Device != "disk" {
			continue
		}
		diskPath := d.Source.File
		if diskPath == "" {
			diskPath = d.Source.Dev
		}
		if diskPath == "" {
			continue
		}
		fixed, err := ensureStorageForDisk(diskPath)
		if err != nil {
			return fixes, fmt.Errorf("storage for %s: %w", diskPath, err)
		}
		fixes = append(fixes, fixed...)
	}

	return fixes, nil
}

// ensureNetworkActive makes sure a libvirt network is defined and running.
func ensureNetworkActive(name string) ([]string, error) {
	var fixes []string

	// Check if network exists.
	out, err := runVirsh("net-info", name)
	if err != nil {
		// Network not defined — try to create it.
		if name == "default" {
			if defErr := defineDefaultNetwork(); defErr != nil {
				return nil, fmt.Errorf("failed to define default libvirt network: %w — you can create it manually with 'virsh net-define /usr/share/libvirt/networks/default.xml && virsh net-start default'", defErr)
			}
			fixes = append(fixes, "Defined default network")
			out, err = runVirsh("net-info", name)
			if err != nil {
				return fixes, fmt.Errorf("failed to get info for network %q after defining it: %w", name, err)
			}
		} else {
			return nil, fmt.Errorf("libvirt network %q is not defined — create it with 'virsh net-define <network.xml>' and 'virsh net-start %s', or change the VM's network to 'default'", name, name)
		}
	}

	// Parse net-info to check if active.
	active := false
	autostart := false
	for _, line := range strings.Split(out, "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		switch key {
		case "Active":
			active = val == "yes"
		case "Autostart":
			autostart = val == "yes"
		}
	}

	if !active {
		if _, err := runVirsh("net-start", name); err != nil {
			return fixes, fmt.Errorf("failed to start libvirt network %q: %w — check 'virsh net-info %s' for details; the network may have conflicting IP ranges with another active network", name, err, name)
		}
		fixes = append(fixes, fmt.Sprintf("Started network %q", name))
	}

	if !autostart {
		if _, err := runVirsh("net-autostart", name); err != nil {
			// Non-fatal, just skip.
		} else {
			fixes = append(fixes, fmt.Sprintf("Enabled autostart for network %q", name))
		}
	}

	return fixes, nil
}

// defineDefaultNetwork creates the default NAT network from the system template.
func defineDefaultNetwork() error {
	// Try standard locations for the default network XML.
	candidates := []string{
		"/usr/share/libvirt/networks/default.xml",
		"/etc/libvirt/qemu/networks/default.xml",
	}

	for _, path := range candidates {
		if _, err := os.Stat(path); err == nil {
			out, err := runVirsh("net-define", path)
			if err != nil {
				return fmt.Errorf("net-define %s: %w: %s", path, err, out)
			}
			return nil
		}
	}

	// No template found — create a minimal default network XML.
	tmpFile, err := os.CreateTemp("", "h2kvm-default-net-*.xml")
	if err != nil {
		return fmt.Errorf("failed to create temp file for default network XML: %w", err)
	}
	defer os.Remove(tmpFile.Name())

	defaultXML := `<network>
  <name>default</name>
  <forward mode='nat'/>
  <bridge name='virbr0' stp='on' delay='0'/>
  <ip address='192.168.122.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.122.2' end='192.168.122.254'/>
    </dhcp>
  </ip>
</network>`

	if _, err := tmpFile.WriteString(defaultXML); err != nil {
		tmpFile.Close()
		return fmt.Errorf("failed to write default network XML to %s: %w", tmpFile.Name(), err)
	}
	tmpFile.Close()

	out, err := runVirsh("net-define", tmpFile.Name())
	if err != nil {
		return fmt.Errorf("virsh net-define failed for default network: %w: %s — check that libvirtd is running and the virbr0 bridge is not in conflict", err, out)
	}
	return nil
}

// ensureStorageForDisk checks that storage pools covering the disk path are active.
func ensureStorageForDisk(diskPath string) ([]string, error) {
	var fixes []string

	// List all pools to find which one covers this disk path.
	out, err := runVirsh("pool-list", "--all", "--name")
	if err != nil {
		return nil, nil // Can't list pools, skip check.
	}

	for _, poolName := range strings.Split(out, "\n") {
		poolName = strings.TrimSpace(poolName)
		if poolName == "" {
			continue
		}

		info, err := runVirsh("pool-info", poolName)
		if err != nil {
			continue
		}

		// Parse pool state.
		poolActive := false
		for _, line := range strings.Split(info, "\n") {
			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 && strings.TrimSpace(parts[0]) == "State" {
				poolActive = strings.TrimSpace(parts[1]) == "running"
			}
		}

		if poolActive {
			continue
		}

		// Check if pool's target path is a parent of diskPath.
		dumpOut, dErr := runVirsh("pool-dumpxml", poolName)
		if dErr != nil {
			continue
		}

		type poolXML struct {
			Target struct {
				Path string `xml:"path"`
			} `xml:"target"`
		}
		var pool poolXML
		if xml.Unmarshal([]byte(dumpOut), &pool) != nil {
			continue
		}

		if pool.Target.Path != "" && strings.HasPrefix(diskPath, pool.Target.Path) {
			if _, err := runVirsh("pool-start", poolName); err == nil {
				fixes = append(fixes, fmt.Sprintf("Started storage pool %q", poolName))
			}
			if _, err := runVirsh("pool-autostart", poolName); err == nil {
				fixes = append(fixes, fmt.Sprintf("Enabled autostart for pool %q", poolName))
			}
		}
	}

	return fixes, nil
}

// StartVM runs pre-flight checks to auto-fix common issues, then starts the VM.
func StartVM(name string) error {
	fixes, err := PreflightVM(name)
	if err != nil {
		return fmt.Errorf("pre-flight check failed for VM %q: %w — run 'virsh dumpxml %s' to inspect the VM configuration", name, err, name)
	}

	out, startErr := runVirsh("start", name)
	if startErr != nil {
		msg := fmt.Sprintf("virsh start %s: %s", name, out)
		if len(fixes) > 0 {
			msg += " (auto-fixed: " + strings.Join(fixes, ", ") + ")"
		}
		return fmt.Errorf("%s", msg)
	}
	return nil
}

// ShutdownVM sends a graceful shutdown signal to a running VM.
func ShutdownVM(name string) error {
	out, err := runVirsh("shutdown", name)
	if err != nil {
		return fmt.Errorf("virsh shutdown %s failed: %w: %s — the VM may already be shut off, or the guest OS may not support ACPI shutdown; use 'Force Stop' to forcefully power off", name, err, out)
	}
	return nil
}

// DestroyVM forces an immediate stop of a running VM.
func DestroyVM(name string) error {
	out, err := runVirsh("destroy", name)
	if err != nil {
		return fmt.Errorf("virsh destroy %s failed: %w: %s — the VM may already be stopped; check with 'virsh list --all'", name, err, out)
	}
	return nil
}

// DeleteVM undefines a VM and removes all its storage.
func DeleteVM(name string) error {
	out, err := runVirsh("undefine", name, "--remove-all-storage")
	if err != nil {
		return fmt.Errorf("virsh undefine %s failed: %w: %s — ensure the VM is stopped first ('virsh destroy %s'), or it may have snapshots that need to be deleted first ('virsh snapshot-list %s')", name, err, out, name, name)
	}
	return nil
}

// OpenConsole launches the appropriate viewer for the given VM.
// For SPICE VMs it tries remote-viewer first, for VNC it uses virt-viewer.
func OpenConsole(name string, gfx VMGraphics) *exec.Cmd {
	var cmd *exec.Cmd

	switch gfx.Type {
	case "spice":
		if _, err := exec.LookPath("remote-viewer"); err == nil {
			uri := fmt.Sprintf("spice://localhost:%d", gfx.Port)
			if gfx.Port <= 0 {
				// autoport — use virt-viewer with libvirt URI
				cmd = exec.Command("virt-viewer", "--connect", "qemu:///system", name)
			} else {
				cmd = exec.Command("remote-viewer", uri)
			}
		} else {
			cmd = exec.Command("virt-viewer", "--connect", "qemu:///system", name)
		}
	default:
		// VNC or unknown — use virt-viewer via libvirt
		cmd = exec.Command("virt-viewer", "--connect", "qemu:///system", name)
	}

	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.Stdin = nil
	if err := cmd.Start(); err != nil {
		return nil
	}
	// Intentional fire-and-forget: reap the child process to avoid
	// zombies. The goroutine exits when the subprocess does.
	go cmd.Wait()
	return cmd
}
