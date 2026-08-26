// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"log"
	"math"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/h2kvm/web/internal/domain"
)

// --- Libvirt VM Management ---

func (s *Server) handleListLibvirtVMs(w http.ResponseWriter, r *http.Request) {
	listStart := time.Now()
	type vmInfo struct {
		Name       string `json:"name"`
		State      string `json:"state"`
		ID         string `json:"id"`
		Autostart  string `json:"autostart"`
		Memory     string `json:"memory"`
		VCPUs      string `json:"vcpus"`
		IP         string `json:"ip,omitempty"`
		DiskBus    string `json:"disk_bus,omitempty"`
		GuestAgent bool   `json:"guest_agent"`
		OSType     string `json:"os_type"`
		DiskPath   string `json:"disk_path,omitempty"`
		DiskFormat string `json:"disk_format,omitempty"`
	}

	// Parse optional filter query params.
	filterState := strings.ToLower(r.URL.Query().Get("state"))
	filterOS := strings.ToLower(r.URL.Query().Get("os"))
	filterSearch := strings.ToLower(r.URL.Query().Get("search"))

	listCtx, listCancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer listCancel()

	out, err := exec.CommandContext(listCtx, "virsh", "list", "--all").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "virsh list failed")
		return
	}

	var vms []vmInfo
	lines := strings.Split(string(out), "\n")
	for _, line := range lines[2:] { // skip header
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}

		var vm vmInfo
		if fields[0] == "-" {
			vm.Name = fields[1]
			vm.State = strings.Join(fields[2:], " ")
			vm.ID = "-"
		} else {
			vm.ID = fields[0]
			vm.Name = fields[1]
			vm.State = strings.Join(fields[2:], " ")
		}

		// Get memory/vcpus
		infoCtx, infoCancel := context.WithTimeout(r.Context(), 5*time.Second)
		if infoOut, err := exec.CommandContext(infoCtx, "virsh", "dominfo", vm.Name).Output(); err == nil {
			for _, l := range strings.Split(string(infoOut), "\n") {
				if strings.HasPrefix(l, "Max memory:") {
					vm.Memory = strings.TrimSpace(strings.TrimPrefix(l, "Max memory:"))
				}
				if strings.HasPrefix(l, "CPU(s):") {
					vm.VCPUs = strings.TrimSpace(strings.TrimPrefix(l, "CPU(s):"))
				}
				if strings.HasPrefix(l, "Autostart:") {
					vm.Autostart = strings.TrimSpace(strings.TrimPrefix(l, "Autostart:"))
				}
			}
		}
		infoCancel()

		// Get disk info from dumpxml + OS detection from XML
		var xmlData string
		xmlCtx, xmlCancel := context.WithTimeout(r.Context(), 5*time.Second)
		if xmlOut, err := exec.CommandContext(xmlCtx, "virsh", "dumpxml", vm.Name).Output(); err == nil {
			xmlData = string(xmlOut)
			vm.DiskBus, vm.DiskPath, vm.DiskFormat = parseDiskInfoFromXML(xmlData)
		}
		xmlCancel()

		// Detect OS type: try name first, fall back to XML hints
		vm.OSType = detectOSType(vm.Name)
		if vm.OSType == "linux" && xmlData != "" {
			vm.OSType = detectOSFromXML(xmlData)
		}

		// Get IP for running VMs
		if vm.State == "running" {
			ipCtx, ipCancel := context.WithTimeout(r.Context(), 3*time.Second)
			if ipOut, err := exec.CommandContext(ipCtx, "virsh", "domifaddr", vm.Name).Output(); err == nil {
				re := regexp.MustCompile(`(\d+\.\d+\.\d+\.\d+)`)
				if m := re.FindString(string(ipOut)); m != "" {
					vm.IP = m
				}
			}
			ipCancel()

			// Check guest agent with 2-second timeout (non-blocking)
			agentCtx, agentCancel := context.WithTimeout(r.Context(), 2*time.Second)
			if err := exec.CommandContext(agentCtx, "virsh", "qemu-agent-command", vm.Name, `{"execute":"guest-ping"}`).Run(); err == nil {
				vm.GuestAgent = true
			}
			agentCancel()
		}

		// Apply filters. If no params, all VMs pass (backward compatible).
		if filterState != "" && strings.ToLower(vm.State) != filterState {
			continue
		}
		if filterOS != "" && strings.ToLower(vm.OSType) != filterOS {
			continue
		}
		if filterSearch != "" {
			nameLower := strings.ToLower(vm.Name)
			if !strings.Contains(nameLower, filterSearch) && !strings.Contains(strings.ToLower(vm.OSType), filterSearch) {
				continue
			}
		}

		vms = append(vms, vm)
	}

	filters := []string{}
	if filterState != "" {
		filters = append(filters, "state="+filterState)
	}
	if filterOS != "" {
		filters = append(filters, "os="+filterOS)
	}
	if filterSearch != "" {
		filters = append(filters, "search="+filterSearch)
	}
	filterDesc := "(none)"
	if len(filters) > 0 {
		filterDesc = strings.Join(filters, ", ")
	}
	log.Printf("[vm] listLibvirtVMs: %d VMs returned, filters=[%s], elapsed=%s", len(vms), filterDesc, time.Since(listStart).Round(time.Millisecond))

	jsonResponse(w, http.StatusOK, vms)
}

// --- Bulk VM Action ---

func (s *Server) handleBulkVMAction(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Names  []string `json:"names"`
		Action string   `json:"action"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if len(req.Names) == 0 {
		jsonError(w, http.StatusBadRequest, "names array is required")
		return
	}

	// Validate action.
	validActions := map[string]bool{
		"start": true, "shutdown": true, "destroy": true, "delete": true,
	}
	if !validActions[req.Action] {
		jsonError(w, http.StatusBadRequest, "action must be one of: start, shutdown, destroy, delete")
		return
	}

	log.Printf("[vm] bulk action=%s count=%d vms=%v from %s", req.Action, len(req.Names), req.Names, r.RemoteAddr)

	type bulkResult struct {
		Name    string `json:"name"`
		Success bool   `json:"success"`
		Error   string `json:"error,omitempty"`
	}

	var results []bulkResult
	for _, name := range req.Names {
		// Sanitize VM name: only allow alphanumeric, dash, underscore, dot.
		safeName := safeNameRe.ReplaceAllString(name, "")
		if safeName == "" || safeName != name {
			results = append(results, bulkResult{Name: name, Success: false, Error: "invalid VM name"})
			continue
		}

		var err error
		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)

		if req.Action == "delete" {
			// Delete: destroy if running, then undefine with storage removal.
			exec.CommandContext(ctx, "virsh", "destroy", safeName).Run()
			out, e := exec.CommandContext(ctx, "virsh", "undefine", safeName,
				"--remove-all-storage", "--snapshots-metadata", "--nvram").CombinedOutput()
			if e != nil {
				// Retry without --nvram.
				out, e = exec.CommandContext(ctx, "virsh", "undefine", safeName,
					"--remove-all-storage", "--snapshots-metadata").CombinedOutput()
				if e != nil {
					// Last resort: undefine only.
					out, e = exec.CommandContext(ctx, "virsh", "undefine", safeName).CombinedOutput()
					if e != nil {
						err = fmt.Errorf("%s", strings.TrimSpace(string(out)))
					}
				}
			}
		} else {
			out, e := exec.CommandContext(ctx, "virsh", req.Action, safeName).CombinedOutput()
			if e != nil {
				err = fmt.Errorf("%s", strings.TrimSpace(string(out)))
			}
		}
		cancel()

		res := bulkResult{Name: safeName, Success: err == nil}
		if err != nil {
			res.Error = err.Error()
		}
		results = append(results, res)

		resultStr := "ok"
		if err != nil {
			resultStr = err.Error()
		}
		s.auditLog(r, "bulk_vm_"+req.Action, safeName, resultStr)
	}

	successCount := 0
	for _, r := range results {
		if r.Success {
			successCount++
		}
	}
	log.Printf("[vm] bulk action=%s completed: %d/%d succeeded", req.Action, successCount, len(results))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"results": results,
	})
}

// handlePromoteVirtIO changes a VM's disk bus from SATA to VirtIO (or vice versa).
// This is used after Windows firstboot installs VirtIO drivers.
func (s *Server) handlePromoteVirtIO(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Bus string `json:"bus"` // "virtio" or "sata"
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Bus != "virtio" && req.Bus != "sata" {
		jsonError(w, http.StatusBadRequest, "bus must be 'virtio' or 'sata'")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Get current XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	xmlStr := string(xmlOut)

	// Check if VM is running — must be shut off to change disk bus.
	stateOut, _ := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	state := strings.TrimSpace(string(stateOut))
	if state == "running" || state == "paused" {
		jsonError(w, http.StatusConflict, "VM must be shut off before changing disk bus. Stop the VM first.")
		return
	}

	// Replace disk bus and device name in XML.
	currentBus, _, _ := parseDiskInfoFromXML(xmlStr)
	log.Printf("[vm] promote vm=%s current_bus=%s target_bus=%s from %s", safeName, currentBus, req.Bus, r.RemoteAddr)

	var oldBus, newBus, oldDev, newDev string
	if req.Bus == "virtio" {
		oldBus = `bus='sata'`
		newBus = `bus='virtio'`
		oldDev = `dev='sda'`
		newDev = `dev='vda'`
	} else {
		oldBus = `bus='virtio'`
		newBus = `bus='sata'`
		oldDev = `dev='vda'`
		newDev = `dev='sda'`
	}

	// Only replace the first disk (device='disk', not CDROM).
	// Also remove the <address> element from the disk — SATA uses
	// type='drive' addresses which are incompatible with VirtIO (PCI).
	// Libvirt will auto-assign the correct address type.
	replaced := false
	lines := strings.Split(xmlStr, "\n")
	inDiskDevice := false // true when inside <disk device='disk'> (not cdrom)
	skipAddress := false
	var result []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		if strings.Contains(trimmed, "<disk") && strings.Contains(trimmed, "device='disk'") {
			inDiskDevice = true
		}
		if strings.Contains(trimmed, "<disk") && strings.Contains(trimmed, "device='cdrom'") {
			inDiskDevice = false
		}

		if inDiskDevice && strings.Contains(trimmed, "<target") && strings.Contains(trimmed, oldBus) {
			line = strings.Replace(line, oldBus, newBus, 1)
			line = strings.Replace(line, oldDev, newDev, 1)
			replaced = true
			skipAddress = true // Remove the next <address> element
		}

		// Skip the <address> element inside the disk we're modifying.
		// SATA uses type='drive', VirtIO needs type='pci' — let libvirt auto-assign.
		if skipAddress && strings.Contains(trimmed, "<address") {
			skipAddress = false
			continue // Drop this line
		}

		if strings.Contains(trimmed, "</disk>") {
			inDiskDevice = false
			skipAddress = false
		}

		result = append(result, line)
	}

	if !replaced {
		jsonError(w, http.StatusConflict, fmt.Sprintf("disk bus is already '%s' or not found", req.Bus))
		return
	}

	newXML := strings.Join(result, "\n")

	// Write new XML to temp file.
	tmpFile := filepath.Join(os.TempDir(), fmt.Sprintf("h2kweb-promote-%s.xml", safeName))
	defer os.Remove(tmpFile)
	if err := os.WriteFile(tmpFile, []byte(newXML), 0644); err != nil {
		jsonError(w, http.StatusInternalServerError, "write XML failed: "+err.Error())
		return
	}

	// Save original XML for rollback.
	origFile := tmpFile + ".orig"
	os.WriteFile(origFile, xmlOut, 0644)
	defer os.Remove(origFile)

	// Undefine (without --remove-all-storage so disk is preserved).
	undefOut, undefErr := exec.CommandContext(ctx, "virsh", "undefine", safeName).CombinedOutput()
	if undefErr != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virsh undefine failed: %s", strings.TrimSpace(string(undefOut))))
		return
	}

	out, err := exec.CommandContext(ctx, "virsh", "define", tmpFile).CombinedOutput()
	if err != nil {
		// Restore original definition on failure.
		log.Printf("[promote] define failed (%s), restoring original", strings.TrimSpace(string(out)))
		exec.CommandContext(ctx, "virsh", "define", origFile).Run()
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virsh define failed: %s", strings.TrimSpace(string(out))))
		return
	}

	s.auditLog(r, "promote_disk_bus", safeName, req.Bus)
	log.Printf("[promote] %s disk bus changed to %s", safeName, req.Bus)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"name":    safeName,
		"bus":     req.Bus,
		"message": fmt.Sprintf("Disk bus changed to %s. Start the VM to boot with the new configuration.", req.Bus),
	})
}

// parseDiskInfoFromXML extracts disk bus, path, and format from virsh dumpxml output.
func parseDiskInfoFromXML(xmlData string) (bus, path, format string) {
	type xmlDisk struct {
		Type   string `xml:"type,attr"`
		Device string `xml:"device,attr"`
		Driver struct {
			Type string `xml:"type,attr"`
		} `xml:"driver"`
		Source struct {
			File string `xml:"file,attr"`
		} `xml:"source"`
		Target struct {
			Bus string `xml:"bus,attr"`
		} `xml:"target"`
	}
	type xmlDomain struct {
		Devices struct {
			Disks []xmlDisk `xml:"disk"`
		} `xml:"devices"`
	}

	var dom xmlDomain
	if err := xml.Unmarshal([]byte(xmlData), &dom); err != nil {
		return
	}

	for _, d := range dom.Devices.Disks {
		if d.Device == "disk" {
			bus = d.Target.Bus
			path = d.Source.File
			format = d.Driver.Type
			return
		}
	}
	return
}

// handleEnableRDP enables Remote Desktop on a running Windows VM via guest agent
// or falls back to a PowerShell command via virsh qemu-agent-command.
func (s *Server) handleEnableRDP(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] enable-rdp requested for vm=%s from %s", safeName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Check VM is running.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	if state != "running" {
		jsonError(w, http.StatusConflict, "VM must be running to enable RDP")
		return
	}

	// Try enabling RDP via guest agent using reg.exe (simpler escaping than PowerShell).
	// Step 1: Set fDenyTSConnections=0 via reg.exe
	agentCmd := `{"execute":"guest-exec","arguments":{"path":"reg.exe","arg":["add","HKLM\\System\\CurrentControlSet\\Control\\Terminal Server","\/v","fDenyTSConnections","\/t","REG_DWORD","\/d","0","\/f"],"capture-output":true}}`

	// Execute reg.exe to enable RDP.
	out, err := exec.CommandContext(ctx, "virsh", "qemu-agent-command", safeName, agentCmd).CombinedOutput()
	if err != nil {
		log.Printf("[vm] enable-rdp vm=%s reg.exe failed: %s (output: %s)", safeName, err, strings.TrimSpace(string(out)))
	} else {
		log.Printf("[vm] enable-rdp vm=%s reg.exe succeeded", safeName)
		// Step 2: Enable firewall rule via netsh (more reliable than PowerShell for escaping).
		fwCmd := `{"execute":"guest-exec","arguments":{"path":"netsh.exe","arg":["advfirewall","firewall","set","rule","group=Remote Desktop","new","enable=yes"],"capture-output":true}}`
		fwOut, fwErr := exec.CommandContext(ctx, "virsh", "qemu-agent-command", safeName, fwCmd).CombinedOutput()
		if fwErr != nil {
			log.Printf("[vm] enable-rdp vm=%s firewall rule failed: %s", safeName, strings.TrimSpace(string(fwOut)))
		} else {
			log.Printf("[vm] enable-rdp vm=%s firewall rule enabled", safeName)
		}
	}

	if err != nil {

		// Get VM IP for manual instructions.
		var vmIP string
		ipOut, _ := exec.CommandContext(ctx, "virsh", "domifaddr", safeName, "--source", "lease").Output()
		for _, line := range strings.Split(string(ipOut), "\n") {
			if strings.Contains(line, "ipv4") {
				fields := strings.Fields(line)
				if len(fields) >= 4 {
					vmIP = strings.Split(fields[3], "/")[0]
				}
			}
		}

		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"enabled":       false,
			"method":        "manual",
			"ip":            vmIP,
			"rdp_port":      3389,
			"message":       "Guest agent not available. Enable RDP manually via VNC console.",
			"instructions": []string{
				"Connect via VNC console",
				"Open PowerShell as Administrator",
				`Run: Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0`,
				`Run: Enable-NetFirewallRule -DisplayGroup "Remote Desktop"`,
				fmt.Sprintf("Then connect: mstsc /v:%s", vmIP),
			},
		})
		return
	}

	log.Printf("[vm] enable-rdp vm=%s guest-agent command sent successfully", safeName)

	// Get VM IP for connection info.
	var vmIP string
	ipOut, _ := exec.CommandContext(ctx, "virsh", "domifaddr", safeName, "--source", "lease").Output()
	for _, line := range strings.Split(string(ipOut), "\n") {
		if strings.Contains(line, "ipv4") {
			fields := strings.Fields(line)
			if len(fields) >= 4 {
				vmIP = strings.Split(fields[3], "/")[0]
			}
		}
	}

	s.auditLog(r, "enable_rdp", safeName)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"enabled":    true,
		"method":     "guest-agent",
		"ip":         vmIP,
		"rdp_port":   3389,
		"message":    fmt.Sprintf("RDP enabled. Connect: mstsc /v:%s", vmIP),
		"connection": fmt.Sprintf("%s:3389", vmIP),
	})
}

// detectOSType guesses the OS type from the VM name.
func detectOSType(name string) string {
	lower := strings.ToLower(name)
	switch {
	case strings.Contains(lower, "win"):
		return "windows"
	case strings.Contains(lower, "legacy"):
		return "windows"
	case strings.Contains(lower, "kali"):
		return "kali"
	case strings.Contains(lower, "ubuntu"):
		return "ubuntu"
	case strings.Contains(lower, "centos"), strings.Contains(lower, "rhel"),
		strings.Contains(lower, "rocky"), strings.Contains(lower, "alma"):
		return "rhel"
	case strings.Contains(lower, "debian"):
		return "debian"
	case strings.Contains(lower, "fedora"):
		return "fedora"
	default:
		return "linux"
	}
}

// detectOSFromXML detects OS type from libvirt domain XML when the VM name
// doesn't contain an obvious OS hint. Checks description, hyperv features,
// and clock offset which are strong Windows indicators.
func detectOSFromXML(xmlData string) string {
	lower := strings.ToLower(xmlData)

	if i := strings.Index(lower, "<description>"); i >= 0 {
		desc := lower[i:]
		if j := strings.Index(desc, "</description>"); j >= 0 {
			if strings.Contains(desc[:j], "windows") {
				return "windows"
			}
		}
	}

	if strings.Contains(lower, "<hyperv") {
		return "windows"
	}

	if strings.Contains(lower, `offset='localtime'`) || strings.Contains(lower, `offset="localtime"`) {
		return "windows"
	}

	if strings.Contains(lower, "rdp") && strings.Contains(lower, "3389") {
		return "windows"
	}

	if strings.Contains(lower, `type='windows'`) || strings.Contains(lower, `type="windows"`) {
		return "windows"
	}

	return "linux"
}

func (s *Server) handleVMAction(action string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		name := chi.URLParam(r, "vmName")
		log.Printf("[vm] action=%s vm=%s from %s", action, name, r.RemoteAddr)
		out, err := exec.CommandContext(r.Context(), "virsh", action, name).CombinedOutput()
		if err != nil {
			log.Printf("[vm] action=%s vm=%s FAILED: %s", action, name, strings.TrimSpace(string(out)))
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virsh %s %s failed: %s", action, name, strings.TrimSpace(string(out))))
			return
		}
		log.Printf("[vm] action=%s vm=%s succeeded", action, name)
		s.auditLog(r, "vm_"+action, name)
		jsonResponse(w, http.StatusOK, map[string]string{
			"message": fmt.Sprintf("VM %s: %s", name, action),
			"output":  strings.TrimSpace(string(out)),
		})
	}
}

func (s *Server) handleVMDelete(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] delete requested for vm=%s from %s", safeName, r.RemoteAddr)

	// Force stop if running (best-effort).
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	exec.CommandContext(ctx, "virsh", "destroy", safeName).Run()

	// Undefine with all storage, snapshots, and NVRAM removed.
	undefCtx, undefCancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer undefCancel()
	out, err := exec.CommandContext(undefCtx, "virsh", "undefine", safeName,
		"--remove-all-storage", "--snapshots-metadata", "--nvram").CombinedOutput()
	if err != nil {
		log.Printf("[vm] delete vm=%s full undefine failed: %s, retrying without --nvram", safeName, strings.TrimSpace(string(out)))
		// Retry without --nvram (not all VMs have NVRAM).
		out, err = exec.CommandContext(undefCtx, "virsh", "undefine", safeName,
			"--remove-all-storage", "--snapshots-metadata").CombinedOutput()
		if err != nil {
			log.Printf("[vm] delete vm=%s still failed: %s, retrying minimal", safeName, strings.TrimSpace(string(out)))
			// Last resort: undefine without storage removal.
			out, err = exec.CommandContext(undefCtx, "virsh", "undefine", safeName).CombinedOutput()
			if err != nil {
				log.Printf("[vm] delete vm=%s FAILED: %s", safeName, strings.TrimSpace(string(out)))
				jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virsh undefine failed: %s", strings.TrimSpace(string(out))))
				return
			}
			log.Printf("[vm] delete vm=%s succeeded (storage NOT removed — manual cleanup needed)", safeName)
			s.auditLog(r, "vm_delete", safeName, "ok (no storage)")
			jsonResponse(w, http.StatusOK, map[string]string{
				"message": fmt.Sprintf("VM %s deleted (storage may need manual cleanup)", safeName),
			})
			return
		}
	}

	log.Printf("[vm] delete vm=%s succeeded (storage removed)", safeName)
	s.auditLog(r, "vm_delete", safeName, "ok")
	jsonResponse(w, http.StatusOK, map[string]string{"message": fmt.Sprintf("VM %s deleted with storage", safeName)})
}

func (s *Server) handleVMStats(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	out, err := exec.CommandContext(r.Context(), "virsh", "domstats", name).Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "domstats failed")
		return
	}

	stats := map[string]string{}
	for _, line := range strings.Split(string(out), "\n") {
		parts := strings.SplitN(strings.TrimSpace(line), "=", 2)
		if len(parts) == 2 {
			stats[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
		}
	}
	jsonResponse(w, http.StatusOK, stats)
}

func (s *Server) handleVMLiveStats(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")

	// Sanitize VM name: only allow alphanumeric, dash, underscore, dot.
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	type liveStats struct {
		CPUTime      uint64  `json:"cpu_time"`
		CPUPercent   float64 `json:"cpu_percent"`
		MemCurrentMB uint64  `json:"mem_current_mb"`
		MemMaxMB     uint64  `json:"mem_max_mb"`
		MemPercent   float64 `json:"mem_percent"`
	}

	result := liveStats{}

	// Run virsh domstats with 3-second timeout.
	domCtx, domCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer domCancel()

	domOut, err := exec.CommandContext(domCtx, "virsh", "domstats", safeName, "--cpu-total", "--balloon").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virsh domstats failed for %s", safeName))
		return
	}

	// Parse domstats output: lines like "  cpu.time=123456" and "  balloon.current=1048576".
	for _, line := range strings.Split(string(domOut), "\n") {
		line = strings.TrimSpace(line)
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])

		switch key {
		case "cpu.time":
			if v, err := strconv.ParseUint(val, 10, 64); err == nil {
				result.CPUTime = v
			}
		case "balloon.current":
			// balloon values are in KiB.
			if v, err := strconv.ParseUint(val, 10, 64); err == nil {
				result.MemCurrentMB = v / 1024
			}
		case "balloon.maximum":
			if v, err := strconv.ParseUint(val, 10, 64); err == nil {
				result.MemMaxMB = v / 1024
			}
		}
	}

	// Run virsh cpu-stats for percentage-style stats (3-second timeout).
	cpuCtx, cpuCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cpuCancel()

	cpuOut, err := exec.CommandContext(cpuCtx, "virsh", "cpu-stats", safeName, "--total").Output()
	if err == nil {
		// Parse lines like "    cpu_time    123.456789 seconds"
		for _, line := range strings.Split(string(cpuOut), "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "cpu_time") {
				fields := strings.Fields(line)
				if len(fields) >= 2 {
					if v, err := strconv.ParseFloat(fields[1], 64); err == nil {
						// Convert cpu_time seconds to a rough percentage.
						// cpu_time is cumulative; we report it as-is for the caller
						// to compute delta-based percentage over time.
						result.CPUPercent = v
					}
				}
			}
		}
	}

	// Compute memory percentage.
	if result.MemMaxMB > 0 {
		result.MemPercent = float64(result.MemCurrentMB) / float64(result.MemMaxMB) * 100.0
	}

	log.Printf("[vm] liveStats vm=%s cpu_time=%d mem=%dMB/%dMB (%.0f%%)", safeName, result.CPUTime, result.MemCurrentMB, result.MemMaxMB, result.MemPercent)

	jsonResponse(w, http.StatusOK, result)
}

func (s *Server) handleVMVnc(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	out, err := exec.CommandContext(r.Context(), "virsh", "vncdisplay", name).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "no VNC display")
		return
	}
	display := strings.TrimSpace(string(out))
	// Convert :N to port 5900+N
	port := "5900"
	if strings.HasPrefix(display, ":") {
		n := strings.TrimPrefix(display, ":")
		port = fmt.Sprintf("590%s", n)
	}
	jsonResponse(w, http.StatusOK, map[string]string{
		"display": display,
		"port":    port,
		"url":     fmt.Sprintf("vnc://127.0.0.1:%s", port),
	})
}

// --- Console Proxy ---

// handleConsoleProxy starts a websockify proxy for noVNC access to a libvirt VM.
// Returns the proxy URL that noVNC can connect to.
func (s *Server) handleConsoleProxy(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")

	// Get VNC display port
	out, err := exec.CommandContext(r.Context(), "virsh", "vncdisplay", name).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("no VNC display for %s", name))
		return
	}
	display := strings.TrimSpace(string(out))

	// Parse display :N → port 5900+N
	vncPort := "5900"
	if strings.Contains(display, ":") {
		parts := strings.Split(display, ":")
		n := parts[len(parts)-1]
		if num, err := strconv.Atoi(n); err == nil {
			vncPort = fmt.Sprintf("%d", 5900+num)
		}
	}

	// Start websockify on a random port (6080+N)
	wsPort := fmt.Sprintf("%d", 6080+time.Now().UnixNano()%100)

	// Check if websockify is already running for this port
	exec.CommandContext(r.Context(), "pkill", "-f", fmt.Sprintf("websockify.*%s.*127.0.0.1:%s", wsPort, vncPort)).Run()

	// Start websockify in background
	cmd := exec.Command("websockify", "--web", "/usr/share/novnc/", wsPort, fmt.Sprintf("127.0.0.1:%s", vncPort))
	cmd.Start()

	// Give it a moment to start
	time.Sleep(500 * time.Millisecond)

	host := r.Host
	if idx := strings.Index(host, ":"); idx > 0 {
		host = host[:idx]
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"vm_name":    name,
		"vnc_port":   vncPort,
		"ws_port":    wsPort,
		"display":    display,
		"novnc_url":  fmt.Sprintf("http://%s:%s/vnc.html?autoconnect=true&resize=scale&path=websockify", host, wsPort),
		"websocket":  fmt.Sprintf("ws://%s:%s/websockify", host, wsPort),
	})
}

// --- Snapshots ---

func (s *Server) handleListSnapshots(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	out, err := exec.CommandContext(r.Context(), "virsh", "snapshot-list", name, "--tree").Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}

	var snaps []map[string]string
	// Also get detailed list
	detailOut, _ := exec.CommandContext(r.Context(), "virsh", "snapshot-list", name).Output()
	for _, line := range strings.Split(string(detailOut), "\n")[2:] {
		fields := strings.Fields(line)
		if len(fields) >= 3 {
			snaps = append(snaps, map[string]string{
				"name":    fields[0],
				"created": strings.Join(fields[1:len(fields)-1], " "),
				"state":   fields[len(fields)-1],
			})
		}
	}
	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"snapshots": snaps,
		"tree":      strings.TrimSpace(string(out)),
	})
}

func (s *Server) handleCreateSnapshot(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")
	var req struct {
		Name        string `json:"name"`
		Description string `json:"description"`
	}
	readJSON(r, &req)
	if req.Name == "" {
		req.Name = fmt.Sprintf("snap-%d", time.Now().Unix())
	}

	args := []string{"snapshot-create-as", vmName, req.Name}
	if req.Description != "" {
		args = append(args, "--description", req.Description)
	}

	out, err := exec.CommandContext(r.Context(), "virsh", args...).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("snapshot failed: %s", string(out)))
		return
	}
	s.auditLog(r, "snapshot_create", fmt.Sprintf("%s/%s", vmName, req.Name))
	jsonResponse(w, http.StatusCreated, map[string]string{
		"message": strings.TrimSpace(string(out)),
		"name":    req.Name,
	})
}

func (s *Server) handleRevertSnapshot(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")
	snapName := chi.URLParam(r, "snapName")
	out, err := exec.CommandContext(r.Context(), "virsh", "snapshot-revert", vmName, snapName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("revert failed: %s", string(out)))
		return
	}
	s.auditLog(r, "snapshot_revert", fmt.Sprintf("%s/%s", vmName, snapName))
	jsonResponse(w, http.StatusOK, map[string]string{"message": strings.TrimSpace(string(out))})
}

func (s *Server) handleDeleteSnapshot(w http.ResponseWriter, r *http.Request) {
	vmName := chi.URLParam(r, "vmName")
	snapName := chi.URLParam(r, "snapName")
	out, err := exec.CommandContext(r.Context(), "virsh", "snapshot-delete", vmName, snapName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("delete failed: %s", string(out)))
		return
	}
	s.auditLog(r, "snapshot_delete", fmt.Sprintf("%s/%s", vmName, snapName))
	jsonResponse(w, http.StatusOK, map[string]string{"message": strings.TrimSpace(string(out))})
}

func (s *Server) handleVMAutostart(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	var req struct {
		Enable bool `json:"enable"`
	}
	readJSON(r, &req)
	flag := "--autostart"
	if !req.Enable {
		flag = "--autostart" // virsh autostart --disable
	}
	args := []string{"autostart", name}
	if !req.Enable {
		args = append(args, "--disable")
	}
	out, err := exec.CommandContext(r.Context(), "virsh", args...).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, string(out))
		return
	}
	_ = flag
	jsonResponse(w, http.StatusOK, map[string]string{"message": strings.TrimSpace(string(out))})
}

// --- KubeVirt Management ---

// kubectlCmd creates an exec.Cmd for kubectl that uses the active kubeconfig
// from the multi-kubeconfig manager (if one is set).
func (s *Server) kubectlCmd(ctx context.Context, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, "kubectl", args...)
	if s.kubeconfigMgr != nil {
		if kc := s.kubeconfigMgr.ActiveKubeconfigPath(); kc != "" {
			cmd.Env = append(os.Environ(), "KUBECONFIG="+kc)
		}
	}
	return cmd
}

// virtctlCmd creates an exec.Cmd for virtctl that uses the active kubeconfig.
func (s *Server) virtctlCmd(ctx context.Context, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, "virtctl", args...)
	if s.kubeconfigMgr != nil {
		if kc := s.kubeconfigMgr.ActiveKubeconfigPath(); kc != "" {
			cmd.Env = append(os.Environ(), "KUBECONFIG="+kc)
		}
	}
	return cmd
}

func (s *Server) handleKubeVirtVMs(w http.ResponseWriter, r *http.Request) {
	out, err := s.kubectlCmd(r.Context(), "get", "vm", "-A", "-o", "json").Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}
	var result map[string]interface{}
	json.Unmarshal(out, &result)
	items, _ := result["items"].([]interface{})
	jsonResponse(w, http.StatusOK, items)
}

func (s *Server) handleKubeVirtVMIs(w http.ResponseWriter, r *http.Request) {
	out, err := s.kubectlCmd(r.Context(), "get", "vmi", "-A", "-o", "json").Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}
	var result map[string]interface{}
	json.Unmarshal(out, &result)
	items, _ := result["items"].([]interface{})
	jsonResponse(w, http.StatusOK, items)
}

func (s *Server) handleKubeVirtAction(action string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ns := chi.URLParam(r, "ns")
		name := chi.URLParam(r, "name")
		out, err := s.virtctlCmd(r.Context(), action, name, "-n", ns).CombinedOutput()
		if err != nil {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virtctl %s failed: %s", action, string(out)))
			return
		}
		s.auditLog(r, "kubevirt_"+action, fmt.Sprintf("%s/%s", ns, name))
		jsonResponse(w, http.StatusOK, map[string]string{"message": strings.TrimSpace(string(out))})
	}
}

func (s *Server) handleKubeVirtVMDetail(w http.ResponseWriter, r *http.Request) {
	ns := chi.URLParam(r, "ns")
	name := chi.URLParam(r, "name")

	result := map[string]interface{}{}

	// Get VM
	if out, err := s.kubectlCmd(r.Context(), "get", "vm", name, "-n", ns, "-o", "json").Output(); err == nil {
		var vm interface{}
		json.Unmarshal(out, &vm)
		result["vm"] = vm
	}

	// Get VMI
	if out, err := s.kubectlCmd(r.Context(), "get", "vmi", name, "-n", ns, "-o", "json").Output(); err == nil {
		var vmi interface{}
		json.Unmarshal(out, &vmi)
		result["vmi"] = vmi
	}

	// Get guest OS info
	if out, err := s.virtctlCmd(r.Context(), "guestosinfo", name, "-n", ns).Output(); err == nil {
		result["guestOSInfo"] = strings.TrimSpace(string(out))
	}

	jsonResponse(w, http.StatusOK, result)
}

func (s *Server) handleKubeVirtDelete(w http.ResponseWriter, r *http.Request) {
	ns := chi.URLParam(r, "ns")
	name := chi.URLParam(r, "name")
	out, err := s.kubectlCmd(r.Context(), "delete", "vm", name, "-n", ns).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("delete failed: %s", string(out)))
		return
	}
	s.auditLog(r, "kubevirt_delete", fmt.Sprintf("%s/%s", ns, name))
	jsonResponse(w, http.StatusOK, map[string]string{"message": strings.TrimSpace(string(out))})
}

func (s *Server) handleKubeVirtVNC(w http.ResponseWriter, r *http.Request) {
	ns := chi.URLParam(r, "ns")
	name := chi.URLParam(r, "name")

	sshUser := r.URL.Query().Get("ssh_user")
	if sshUser == "" {
		sshUser = "root"
	}

	// virtctl vnc creates a proxy — we return connection info
	// For browser-based VNC, we'd need a websockify proxy
	// For now, return the command the user needs
	result := map[string]interface{}{
		"command":     fmt.Sprintf("virtctl vnc %s -n %s", name, ns),
		"ssh_command": fmt.Sprintf("virtctl ssh --local-ssh-opts='-o StrictHostKeyChecking=no' %s@%s -n %s", sshUser, name, ns),
		"console":     fmt.Sprintf("virtctl console %s -n %s", name, ns),
		"port_forward": fmt.Sprintf("virtctl port-forward vm/%s 5900 -n %s", name, ns),
	}

	// Check if VNC is available by trying port-forward
	jsonResponse(w, http.StatusOK, result)
}

func (s *Server) handleKubeVirtGuestOS(w http.ResponseWriter, r *http.Request) {
	ns := chi.URLParam(r, "ns")
	name := chi.URLParam(r, "name")

	// Get from VMI status
	out, err := s.kubectlCmd(r.Context(), "get", "vmi", name, "-n", ns,
		"-o", "jsonpath={.status.guestOSInfo}").Output()
	if err != nil || len(out) == 0 {
		jsonResponse(w, http.StatusOK, map[string]string{"status": "not available"})
		return
	}
	var info interface{}
	json.Unmarshal(out, &info)
	jsonResponse(w, http.StatusOK, info)
}

// --- Network Management ---

func (s *Server) handleListNetworks(w http.ResponseWriter, r *http.Request) {
	type netInfo struct {
		Name      string `json:"name"`
		State     string `json:"state"`
		Autostart string `json:"autostart"`
		Bridge    string `json:"bridge"`
	}

	out, err := exec.CommandContext(r.Context(), "virsh", "net-list", "--all").Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, []netInfo{})
		return
	}

	var nets []netInfo
	for _, line := range strings.Split(string(out), "\n")[2:] {
		fields := strings.Fields(line)
		if len(fields) >= 3 {
			n := netInfo{Name: fields[0], State: fields[1], Autostart: fields[2]}
			if len(fields) >= 4 {
				n.Bridge = fields[3]
			}
			nets = append(nets, n)
		}
	}
	jsonResponse(w, http.StatusOK, nets)
}

func (s *Server) handleNetworkAction(action string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		name := chi.URLParam(r, "name")
		out, err := exec.CommandContext(r.Context(), "virsh", action, name).CombinedOutput()
		if err != nil {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virsh %s failed: %s", action, string(out)))
			return
		}
		s.auditLog(r, "network_"+action, name)
		jsonResponse(w, http.StatusOK, map[string]string{"message": strings.TrimSpace(string(out))})
	}
}

// --- Batch Migration ---

func (s *Server) handleBatchMigration(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Configs []domain.MigrationConfig `json:"configs"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if len(req.Configs) == 0 {
		jsonError(w, http.StatusBadRequest, "configs array is required and must not be empty")
		return
	}

	log.Printf("[api] batch migration: %d configs submitted from %s", len(req.Configs), r.RemoteAddr)

	type batchJob struct {
		ID     string `json:"id"`
		Source string `json:"source"`
	}

	var jobs []batchJob
	for _, config := range req.Configs {
		if err := config.ValidateDeployExclusive(); err != nil {
			jsonError(w, http.StatusBadRequest, err.Error())
			return
		}
		id, err := s.manager.Submit(config)
		if err != nil {
			continue
		}
		// Determine source label from config.
		source := config.VMDK
		if source == "" {
			source = config.OVA
		}
		if source == "" {
			source = config.OVF
		}
		if source == "" {
			source = config.VHD
		}
		if source == "" {
			source = config.Raw
		}
		if source == "" {
			source = config.VMPath
		}
		if source == "" {
			source = "(unknown)"
		}
		jobs = append(jobs, batchJob{ID: id, Source: source})
	}

	s.auditLog(r, "batch_migration", fmt.Sprintf("%d jobs submitted", len(jobs)), "ok")
	jsonResponse(w, http.StatusAccepted, map[string]interface{}{
		"jobs":  jobs,
		"total": len(jobs),
	})
}

// --- Screenshot ---

var safeNameRe = regexp.MustCompile(`[^a-zA-Z0-9._-]`)

func (s *Server) handleVMScreenshot(w http.ResponseWriter, r *http.Request) {
	screenshotStart := time.Now()
	name := chi.URLParam(r, "vmName")

	// Sanitize VM name to prevent path traversal.
	safeName := safeNameRe.ReplaceAllString(name, "_")
	tmpFile := filepath.Join(os.TempDir(), fmt.Sprintf("h2kweb-ss-%s.ppm", safeName))
	defer os.Remove(tmpFile) // Always clean up, even on error paths.

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "screenshot", name, tmpFile).CombinedOutput()
	if err != nil {
		log.Printf("[vm] screenshot vm=%s FAILED: %s", name, strings.TrimSpace(string(out)))
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("screenshot failed: %s", strings.TrimSpace(string(out))))
		return
	}

	data, err := os.ReadFile(tmpFile)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("read screenshot failed: %v", err))
		return
	}

	log.Printf("[vm] screenshot vm=%s size=%d bytes elapsed=%s", name, len(data), time.Since(screenshotStart).Round(time.Millisecond))

	// virsh screenshot writes PNG despite .ppm extension.
	w.Header().Set("Content-Type", "image/png")
	w.Header().Set("Cache-Control", "no-cache, no-store")
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusOK)
	w.Write(data)
}

// --- Readiness ---

func (s *Server) handleReadiness(w http.ResponseWriter, r *http.Request) {
	type readinessCheck struct {
		Name   string `json:"name"`
		Status string `json:"status"`
		Detail string `json:"detail"`
	}

	var checks []readinessCheck
	var mu sync.Mutex
	var wg sync.WaitGroup

	addCheck := func(name, status, detail string) {
		mu.Lock()
		checks = append(checks, readinessCheck{Name: name, Status: status, Detail: detail})
		mu.Unlock()
	}

	// virtio_win_iso
	wg.Add(1)
	go func() {
		defer wg.Done()
		path := "/var/lib/h2kvm/virtio-win.iso"
		if fileExists(path) {
			addCheck("virtio_win_iso", "ok", path)
		} else {
			addCheck("virtio_win_iso", "warning", "not found: "+path)
		}
	}()

	// virtio_win_extracted
	wg.Add(1)
	go func() {
		defer wg.Done()
		path := "/var/lib/h2kvm/virtio-win-extracted/viostor"
		if fileExists(path) {
			addCheck("virtio_win_extracted", "ok", path)
		} else {
			addCheck("virtio_win_extracted", "warning", "not found: "+path)
		}
	}()

	// hivex
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		// Try python versions in order
		for _, py := range []string{"python3.12", "python3.11", "python3.10", "python3"} {
			if err := exec.CommandContext(ctx, py, "-c", "import hivex").Run(); err == nil {
				addCheck("hivex", "ok", fmt.Sprintf("available via %s", py))
				return
			}
		}
		addCheck("hivex", "error", "python hivex module not found")
	}()

	// nbd_module
	wg.Add(1)
	go func() {
		defer wg.Done()
		if fileExists("/sys/module/nbd") {
			addCheck("nbd_module", "ok", "loaded")
		} else {
			addCheck("nbd_module", "error", "/sys/module/nbd not found")
		}
	}()

	// libvirtd
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		out, err := exec.CommandContext(ctx, "systemctl", "is-active", "libvirtd").Output()
		state := strings.TrimSpace(string(out))
		if err == nil && state == "active" {
			addCheck("libvirtd", "ok", "active")
		} else {
			addCheck("libvirtd", "error", "not active: "+state)
		}
	}()

	// qemu_img
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "qemu-img").Output(); err == nil {
			addCheck("qemu_img", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("qemu_img", "error", "not found in PATH")
		}
	}()

	// h2kvmctl
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "h2kvmctl").Output(); err == nil {
			addCheck("h2kvmctl", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("h2kvmctl", "error", "not found in PATH")
		}
	}()

	// kvm
	wg.Add(1)
	go func() {
		defer wg.Done()
		if fileExists("/dev/kvm") {
			addCheck("kvm", "ok", "/dev/kvm")
		} else {
			addCheck("kvm", "error", "/dev/kvm not found")
		}
	}()

	// libguestfs (python3 -c "import guestfs")
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		for _, py := range []string{"python3.12", "python3.11", "python3.10", "python3"} {
			if err := exec.CommandContext(ctx, py, "-c", "import guestfs").Run(); err == nil {
				addCheck("libguestfs", "ok", fmt.Sprintf("available via %s", py))
				return
			}
		}
		addCheck("libguestfs", "warning", "python guestfs module not found")
	}()

	// supermin
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "supermin").Output(); err == nil {
			addCheck("supermin", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("supermin", "warning", "not found (needed by libguestfs)")
		}
	}()

	// guestfish
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "guestfish").Output(); err == nil {
			addCheck("guestfish", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("guestfish", "warning", "not found")
		}
	}()

	// qemu-nbd
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "qemu-nbd").Output(); err == nil {
			addCheck("qemu_nbd", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("qemu_nbd", "error", "not found in PATH")
		}
	}()

	// python-augeas
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		for _, py := range []string{"python3.12", "python3.11", "python3.10", "python3"} {
			if err := exec.CommandContext(ctx, py, "-c", "import augeas").Run(); err == nil {
				addCheck("python_augeas", "ok", fmt.Sprintf("available via %s", py))
				return
			}
		}
		addCheck("python_augeas", "warning", "python-augeas not found")
	}()

	// govc
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "govc").Output(); err == nil {
			addCheck("govc", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("govc", "warning", "not found (needed for vSphere)")
		}
	}()

	// virt-install
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "virt-install").Output(); err == nil {
			addCheck("virt_install", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("virt_install", "warning", "not found (Create VM via virt-install only — migration uses virsh define)")
		}
	}()

	// OVMF firmware
	wg.Add(1)
	go func() {
		defer wg.Done()
		for _, p := range []string{
			"/usr/share/edk2/ovmf/OVMF_CODE.fd",
			"/usr/share/OVMF/OVMF_CODE.fd",
			"/usr/share/edk2/x64/OVMF_CODE.fd",
		} {
			if fileExists(p) {
				addCheck("ovmf", "ok", p)
				return
			}
		}
		addCheck("ovmf", "warning", "OVMF firmware not found (needed for UEFI VMs)")
	}()

	// bsdtar
	wg.Add(1)
	go func() {
		defer wg.Done()
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		if out, err := exec.CommandContext(ctx, "which", "bsdtar").Output(); err == nil {
			addCheck("bsdtar", "ok", strings.TrimSpace(string(out)))
		} else {
			addCheck("bsdtar", "warning", "not found (needed for VirtIO ISO extraction)")
		}
	}()

	// /run/h2kvm (runtime dir for NBD locks)
	wg.Add(1)
	go func() {
		defer wg.Done()
		if fileExists("/run/h2kvm") {
			addCheck("runtime_dir", "ok", "/run/h2kvm")
		} else {
			addCheck("runtime_dir", "error", "/run/h2kvm missing (NBD locking will fail)")
		}
	}()

	wg.Wait()

	okCount, warnCount, errCount := 0, 0, 0
	for _, c := range checks {
		switch c.Status {
		case "ok":
			okCount++
		case "warning":
			warnCount++
		case "error":
			errCount++
		}
	}
	log.Printf("[api] readiness check: %d ok, %d warnings, %d errors (total %d checks)", okCount, warnCount, errCount, len(checks))

	jsonResponse(w, http.StatusOK, checks)
}

// --- Disk Images ---

func (s *Server) handleDiskImages(w http.ResponseWriter, r *http.Request) {
	type fileInfo struct {
		Name      string `json:"name"`
		Path      string `json:"path"`
		SizeBytes int64  `json:"size_bytes"`
		SizeHuman string `json:"size_human"`
		Format    string `json:"format"`
	}
	type dirInfo struct {
		Path  string     `json:"path"`
		Files []fileInfo `json:"files"`
	}

	diskExts := map[string]bool{
		".qcow2": true, ".vmdk": true, ".raw": true,
		".ova": true, ".vhd": true,
	}

	scanDirs := []string{
		"/var/lib/libvirt/images/",
		"/data/demo/",
		"/var/lib/h2kvm/demo/",
	}

	var directories []dirInfo
	for _, dir := range scanDirs {
		entries, err := os.ReadDir(dir)
		if err != nil {
			continue
		}
		d := dirInfo{Path: dir}
		for _, e := range entries {
			if e.IsDir() {
				continue
			}
			ext := strings.ToLower(filepath.Ext(e.Name()))
			if !diskExts[ext] {
				continue
			}
			info, err := e.Info()
			if err != nil {
				continue
			}
			d.Files = append(d.Files, fileInfo{
				Name:      e.Name(),
				Path:      filepath.Join(dir, e.Name()),
				SizeBytes: info.Size(),
				SizeHuman: humanSize(info.Size()),
				Format:    strings.TrimPrefix(ext, "."),
			})
		}
		if len(d.Files) > 0 {
			directories = append(directories, d)
		}
	}

	totalFiles := 0
	for _, d := range directories {
		totalFiles += len(d.Files)
	}
	log.Printf("[vm] diskImages: %d directories, %d files found", len(directories), totalFiles)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"directories": directories,
	})
}

// humanSize converts bytes to a human-readable string.
func humanSize(bytes int64) string {
	const (
		KB = 1024
		MB = KB * 1024
		GB = MB * 1024
		TB = GB * 1024
	)
	switch {
	case bytes >= TB:
		return fmt.Sprintf("%.1f TB", float64(bytes)/float64(TB))
	case bytes >= GB:
		return fmt.Sprintf("%.1f GB", float64(bytes)/float64(GB))
	case bytes >= MB:
		return fmt.Sprintf("%.1f MB", float64(bytes)/float64(MB))
	case bytes >= KB:
		return fmt.Sprintf("%.1f KB", float64(bytes)/float64(KB))
	default:
		return fmt.Sprintf("%d B", bytes)
	}
}

// --- Network Topology ---

func (s *Server) handleNetworkTopology(w http.ResponseWriter, r *http.Request) {
	type vmEntry struct {
		Name  string `json:"name"`
		MAC   string `json:"mac"`
		IP    string `json:"ip"`
		State string `json:"state"`
	}
	type networkEntry struct {
		Name   string    `json:"name"`
		State  string    `json:"state"`
		Bridge string    `json:"bridge"`
		VMs    []vmEntry `json:"vms"`
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	// Get all networks
	out, err := exec.CommandContext(ctx, "virsh", "net-list", "--all").Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, map[string]interface{}{"networks": []interface{}{}})
		return
	}

	// Parse networks
	var networks []networkEntry
	netMap := map[string]*networkEntry{}
	for _, line := range strings.Split(string(out), "\n")[2:] {
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		n := networkEntry{Name: fields[0], State: fields[1]}
		if len(fields) >= 4 {
			n.Bridge = fields[3]
		}
		networks = append(networks, n)
		netMap[n.Name] = &networks[len(networks)-1]
	}

	// Get DHCP leases for each active network (MAC -> IP)
	macToIP := map[string]string{}
	for i := range networks {
		if networks[i].State != "active" {
			continue
		}
		func() {
			leaseCtx, leaseCancel := context.WithTimeout(r.Context(), 5*time.Second)
			defer leaseCancel()
			if leaseOut, err := exec.CommandContext(leaseCtx, "virsh", "net-dhcp-leases", networks[i].Name).Output(); err == nil {
				for _, line := range strings.Split(string(leaseOut), "\n")[2:] {
					fields := strings.Fields(line)
					if len(fields) >= 5 {
						mac := fields[1]
						ip := strings.Split(fields[4], "/")[0]
						macToIP[mac] = ip
					}
				}
			}
		}()
	}

	// Get running VMs and map them to networks via domiflist
	runCtx, runCancel := context.WithTimeout(r.Context(), 5*time.Second)
	vmListOut, err := exec.CommandContext(runCtx, "virsh", "list", "--name", "--state-running").Output()
	runCancel()
	if err == nil {
		for _, vmName := range strings.Split(strings.TrimSpace(string(vmListOut)), "\n") {
			vmName = strings.TrimSpace(vmName)
			if vmName == "" {
				continue
			}

			ifCtx, ifCancel := context.WithTimeout(r.Context(), 5*time.Second)
			ifOut, err := exec.CommandContext(ifCtx, "virsh", "domiflist", vmName).Output()
			ifCancel()
			if err != nil {
				continue
			}

			// Parse domiflist: Interface  Type  Source  Model  MAC
			for _, line := range strings.Split(string(ifOut), "\n")[2:] {
				fields := strings.Fields(line)
				if len(fields) < 5 {
					continue
				}
				netName := fields[2]
				mac := fields[4]

				if net, ok := netMap[netName]; ok {
					ip := macToIP[mac]
					net.VMs = append(net.VMs, vmEntry{
						Name:  vmName,
						MAC:   mac,
						IP:    ip,
						State: "running",
					})
				}
			}
		}
	}

	totalVMs := 0
	for _, n := range networks {
		totalVMs += len(n.VMs)
	}
	log.Printf("[vm] networkTopology: %d networks, %d VMs mapped", len(networks), totalVMs)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"networks": networks,
	})
}

// --- Guest Agent Insights ---

// handleVMGuestInfo queries the QEMU guest agent for rich VM internals:
// hostname, OS info, filesystems, and network interfaces.
func (s *Server) handleVMGuestInfo(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] guest-info requested for vm=%s from %s", safeName, r.RemoteAddr)

	// Helper to run a guest agent command with 5s timeout.
	agentQuery := func(cmd string) (map[string]interface{}, bool) {
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		out, err := exec.CommandContext(ctx, "virsh", "qemu-agent-command", safeName, cmd).Output()
		if err != nil {
			return nil, false
		}
		var result map[string]interface{}
		if err := json.Unmarshal(out, &result); err != nil {
			return nil, false
		}
		return result, true
	}

	// Check if guest agent is available at all.
	if _, ok := agentQuery(`{"execute":"guest-info"}`); !ok {
		log.Printf("[vm] guest-info vm=%s guest agent not available", safeName)
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"available": false,
		})
		return
	}

	resp := map[string]interface{}{
		"available": true,
	}

	// Get OS info.
	if osInfo, ok := agentQuery(`{"execute":"guest-get-osinfo"}`); ok {
		if ret, ok := osInfo["return"].(map[string]interface{}); ok {
			osMap := map[string]interface{}{}
			if v, ok := ret["name"]; ok {
				osMap["name"] = v
			}
			if v, ok := ret["version"]; ok {
				osMap["version"] = v
			}
			if v, ok := ret["kernel-release"]; ok {
				osMap["kernel"] = v
			} else if v, ok := ret["kernel-version"]; ok {
				osMap["kernel"] = v
			}
			resp["os"] = osMap

			// Try to extract hostname from os-info id or pretty-name.
			if v, ok := ret["pretty-name"].(string); ok && v != "" {
				resp["hostname"] = v
			}
		}
	}

	// Get hostname from guest-get-host-name if available.
	if hn, ok := agentQuery(`{"execute":"guest-get-host-name"}`); ok {
		if ret, ok := hn["return"].(map[string]interface{}); ok {
			if v, ok := ret["host-name"].(string); ok && v != "" {
				resp["hostname"] = v
			}
		}
	}

	// Get filesystem info.
	if fsInfo, ok := agentQuery(`{"execute":"guest-get-fsinfo"}`); ok {
		if ret, ok := fsInfo["return"].([]interface{}); ok {
			var filesystems []map[string]interface{}
			for _, item := range ret {
				fs, ok := item.(map[string]interface{})
				if !ok {
					continue
				}
				entry := map[string]interface{}{}
				if v, ok := fs["mountpoint"]; ok {
					entry["mountpoint"] = v
				}
				if v, ok := fs["type"]; ok {
					entry["type"] = v
				}
				if v, ok := fs["total-bytes"]; ok {
					entry["total_bytes"] = v
				}
				if v, ok := fs["used-bytes"]; ok {
					entry["used_bytes"] = v
				}
				// Extract disk device name from the disk list.
				if disks, ok := fs["disk"].([]interface{}); ok && len(disks) > 0 {
					if d, ok := disks[0].(map[string]interface{}); ok {
						if pci, ok := d["pci-controller"].(map[string]interface{}); ok {
							_ = pci // present but we want serial/dev
						}
						if serial, ok := d["serial"].(string); ok && serial != "" {
							entry["disk"] = serial
						} else if dev, ok := d["dev"].(string); ok && dev != "" {
							entry["disk"] = dev
						}
					}
				}
				filesystems = append(filesystems, entry)
			}
			resp["filesystems"] = filesystems
		}
	}

	// Get network interfaces.
	if netInfo, ok := agentQuery(`{"execute":"guest-network-get-interfaces"}`); ok {
		if ret, ok := netInfo["return"].([]interface{}); ok {
			var interfaces []map[string]interface{}
			for _, item := range ret {
				iface, ok := item.(map[string]interface{})
				if !ok {
					continue
				}
				entry := map[string]interface{}{}
				if v, ok := iface["name"]; ok {
					entry["name"] = v
				}
				if v, ok := iface["hardware-address"]; ok {
					entry["mac"] = v
				}
				// Extract the first IPv4 address.
				if addrs, ok := iface["ip-addresses"].([]interface{}); ok {
					for _, a := range addrs {
						addr, ok := a.(map[string]interface{})
						if !ok {
							continue
						}
						if t, ok := addr["ip-address-type"].(string); ok && t == "ipv4" {
							entry["ip"] = addr["ip-address"]
							break
						}
					}
				}
				interfaces = append(interfaces, entry)
			}
			resp["interfaces"] = interfaces
		}
	}

	log.Printf("[vm] guest-info vm=%s available=true", safeName)
	jsonResponse(w, http.StatusOK, resp)
}

// --- Smart Status with Root Cause ---

// handleVMStatusDetail returns enriched VM status with "why" context,
// disk errors, and resource pressure metrics.
func (s *Server) handleVMStatusDetail(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] status-detail requested for vm=%s from %s", safeName, r.RemoteAddr)

	// Get state with reason.
	stateCtx, stateCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer stateCancel()

	stateOut, err := exec.CommandContext(stateCtx, "virsh", "domstate", safeName, "--reason").Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	// Parse "running (booted)" or "shut off (user)" etc.
	stateStr := strings.TrimSpace(string(stateOut))
	state := stateStr
	reason := ""
	if idx := strings.Index(stateStr, "("); idx > 0 {
		state = strings.TrimSpace(stateStr[:idx])
		end := strings.Index(stateStr, ")")
		if end > idx {
			reason = stateStr[idx+1 : end]
		}
	}

	resp := map[string]interface{}{
		"state":  state,
		"reason": reason,
	}

	// Build human-readable state detail.
	var warnings []string

	// Check disk errors.
	blkCtx, blkCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer blkCancel()
	if blkOut, err := exec.CommandContext(blkCtx, "virsh", "domblkerror", safeName).Output(); err == nil {
		blkStr := strings.TrimSpace(string(blkOut))
		if blkStr != "" && !strings.Contains(strings.ToLower(blkStr), "no errors") {
			for _, line := range strings.Split(blkStr, "\n") {
				line = strings.TrimSpace(line)
				if line != "" {
					warnings = append(warnings, "Disk error: "+line)
				}
			}
		}
	}

	// Get resource stats.
	var cpuPercent, memPercent float64
	statsCtx, statsCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer statsCancel()
	if statsOut, err := exec.CommandContext(statsCtx, "virsh", "domstats", safeName, "--cpu-total", "--balloon").Output(); err == nil {
		var cpuTime uint64
		var memCurrent, memMax uint64
		for _, line := range strings.Split(string(statsOut), "\n") {
			line = strings.TrimSpace(line)
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			key := strings.TrimSpace(parts[0])
			val := strings.TrimSpace(parts[1])
			switch key {
			case "cpu.time":
				cpuTime, _ = strconv.ParseUint(val, 10, 64)
			case "balloon.current":
				memCurrent, _ = strconv.ParseUint(val, 10, 64)
			case "balloon.maximum":
				memMax, _ = strconv.ParseUint(val, 10, 64)
			}
		}
		_ = cpuTime
		if memMax > 0 {
			memPercent = float64(memCurrent) / float64(memMax) * 100.0
		}

		// For CPU percentage, use virsh cpu-stats.
		cpuStatsCtx, cpuStatsCancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cpuStatsCancel()
		if cpuOut, err := exec.CommandContext(cpuStatsCtx, "virsh", "cpu-stats", safeName, "--total").Output(); err == nil {
			for _, line := range strings.Split(string(cpuOut), "\n") {
				line = strings.TrimSpace(line)
				if strings.HasPrefix(line, "cpu_time") {
					fields := strings.Fields(line)
					if len(fields) >= 2 {
						if v, err := strconv.ParseFloat(fields[1], 64); err == nil {
							cpuPercent = v
						}
					}
				}
			}
		}
	}

	resp["resource_pressure"] = map[string]interface{}{
		"cpu_percent":    cpuPercent,
		"memory_percent": memPercent,
	}

	// Build state detail string.
	stateDetail := strings.ToUpper(state[:1]) + state[1:]
	if reason != "" {
		stateDetail += fmt.Sprintf(" (%s)", reason)
	}
	if len(warnings) > 0 {
		stateDetail += fmt.Sprintf(" — %d issue(s) detected", len(warnings))
	} else if state == "running" {
		stateDetail += " — no issues detected"
	}
	resp["state_detail"] = stateDetail
	resp["warnings"] = warnings

	log.Printf("[vm] status-detail vm=%s state=%s reason=%s warnings=%d", safeName, state, reason, len(warnings))
	jsonResponse(w, http.StatusOK, resp)
}

// --- Domain XML Viewer ---

// handleVMXML returns the raw virsh dumpxml output for a VM.
func (s *Server) handleVMXML(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] xml requested for vm=%s from %s", safeName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	jsonResponse(w, http.StatusOK, map[string]string{
		"xml": string(out),
	})
}

// --- Audit Log ---

// auditLog records an action to the in-memory audit log.
// The result parameter is optional (variadic); defaults to "ok".
func (s *Server) auditLog(r *http.Request, action, target string, results ...string) {
	user := "unknown"
	if token := extractSessionToken(r); token != "" {
		if u, ok := s.sessions.ValidateSession(token); ok {
			user = u
		}
	}
	result := "ok"
	if len(results) > 0 {
		result = results[0]
	}

	entry := AuditEntry{
		Timestamp: time.Now().Format(time.RFC3339),
		User:      user,
		Action:    action,
		Target:    target,
		Result:    result,
		RemoteIP:  r.RemoteAddr,
	}

	s.auditMu.Lock()
	s.auditEntries = append(s.auditEntries, entry)
	// Keep only the last 500 entries.
	if len(s.auditEntries) > 500 {
		s.auditEntries = s.auditEntries[len(s.auditEntries)-500:]
	}
	s.auditMu.Unlock()

	log.Printf("[audit] user=%s action=%s target=%s result=%s remote=%s", user, action, target, result, r.RemoteAddr)
}

func (s *Server) handleAuditLog(w http.ResponseWriter, r *http.Request) {
	s.auditMu.RLock()
	entries := make([]AuditEntry, len(s.auditEntries))
	copy(entries, s.auditEntries)
	s.auditMu.RUnlock()

	// Return in reverse chronological order (most recent first).
	for i, j := 0, len(entries)-1; i < j; i, j = i+1, j-1 {
		entries[i], entries[j] = entries[j], entries[i]
	}

	// Support optional limit query param.
	if limitStr := r.URL.Query().Get("limit"); limitStr != "" {
		if limit, err := strconv.Atoi(limitStr); err == nil && limit > 0 && limit < len(entries) {
			entries = entries[:limit]
		}
	}

	jsonResponse(w, http.StatusOK, entries)
}

// handleActivity returns the last 20 audit entries sorted newest-first.
func (s *Server) handleActivity(w http.ResponseWriter, r *http.Request) {
	s.auditMu.RLock()
	defer s.auditMu.RUnlock()

	limit := 20
	entries := s.auditEntries
	if len(entries) > limit {
		entries = entries[len(entries)-limit:]
	}
	// Reverse for newest-first.
	reversed := make([]AuditEntry, len(entries))
	for i, e := range entries {
		reversed[len(entries)-1-i] = e
	}
	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"activities": reversed,
		"total":      len(reversed),
	})
}

// --- Network Connectivity Test ---

// handleVMConnectivityTest checks if a VM is reachable via ping and probes
// common service ports (SSH, HTTP, RDP) in parallel.
func (s *Server) handleVMConnectivityTest(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] connectivity-test requested for vm=%s from %s", safeName, r.RemoteAddr)

	// Get the VM's IP via virsh domifaddr.
	ipCtx, ipCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer ipCancel()

	ipOut, err := exec.CommandContext(ipCtx, "virsh", "domifaddr", safeName).Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"reachable": false,
			"error":     "no IP address",
		})
		return
	}

	// Extract first IPv4 address.
	re := regexp.MustCompile(`(\d+\.\d+\.\d+\.\d+)`)
	ip := re.FindString(string(ipOut))
	if ip == "" {
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"reachable": false,
			"error":     "no IP address",
		})
		return
	}

	type portResult struct {
		Port int    `json:"port"`
		Name string `json:"name"`
		Open bool   `json:"open"`
	}

	// Run checks in parallel with 3s overall timeout.
	var (
		pingOK bool
		ports  []portResult
		mu     sync.Mutex
		wg     sync.WaitGroup
	)

	// Ping check.
	wg.Add(1)
	go func() {
		defer wg.Done()
		pingCtx, pingCancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer pingCancel()
		if err := exec.CommandContext(pingCtx, "ping", "-c", "1", "-W", "2", ip).Run(); err == nil {
			mu.Lock()
			pingOK = true
			mu.Unlock()
		}
	}()

	// Port checks.
	portChecks := []struct {
		port int
		name string
	}{
		{22, "SSH"},
		{80, "HTTP"},
		{3389, "RDP"},
	}

	for _, pc := range portChecks {
		wg.Add(1)
		go func(port int, name string) {
			defer wg.Done()
			conn, err := net.DialTimeout("tcp", fmt.Sprintf("%s:%d", ip, port), 2*time.Second)
			open := err == nil
			if conn != nil {
				conn.Close()
			}
			mu.Lock()
			ports = append(ports, portResult{Port: port, Name: name, Open: open})
			mu.Unlock()
		}(pc.port, pc.name)
	}

	wg.Wait()

	// Sort ports by port number for consistent output.
	for i := 0; i < len(ports); i++ {
		for j := i + 1; j < len(ports); j++ {
			if ports[j].Port < ports[i].Port {
				ports[i], ports[j] = ports[j], ports[i]
			}
		}
	}

	log.Printf("[vm] connectivity-test vm=%s ip=%s reachable=%v ports=%d", safeName, ip, pingOK, len(ports))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"ip":        ip,
		"reachable": pingOK,
		"ports":     ports,
	})
}

// --- Smart Recommendations ---

// handleVMRecommendations analyzes a VM and generates actionable recommendations
// for performance, monitoring, and storage improvements.
func (s *Server) handleVMRecommendations(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] recommendations requested for vm=%s from %s", safeName, r.RemoteAddr)

	type recommendation struct {
		Type     string `json:"type"`
		Severity string `json:"severity"`
		Title    string `json:"title"`
		Detail   string `json:"detail"`
		Action   string `json:"action,omitempty"`
	}

	var recs []recommendation
	score := 100

	// 1. Get VM info: vCPUs, memory.
	var memoryKiB uint64
	infoCtx, infoCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer infoCancel()
	if infoOut, err := exec.CommandContext(infoCtx, "virsh", "dominfo", safeName).Output(); err == nil {
		for _, line := range strings.Split(string(infoOut), "\n") {
			if strings.HasPrefix(line, "Max memory:") {
				memStr := strings.TrimSpace(strings.TrimPrefix(line, "Max memory:"))
				memStr = strings.TrimSuffix(memStr, " KiB")
				memStr = strings.TrimSpace(memStr)
				memoryKiB, _ = strconv.ParseUint(memStr, 10, 64)
			}
		}
	} else {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	// 2. Get disk info and XML.
	var diskBus, diskFormat, xmlData string
	xmlCtx, xmlCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer xmlCancel()
	if xmlOut, err := exec.CommandContext(xmlCtx, "virsh", "dumpxml", safeName).Output(); err == nil {
		xmlData = string(xmlOut)
		diskBus, _, diskFormat = parseDiskInfoFromXML(xmlData)
	}

	// 3. Detect OS type.
	osType := detectOSType(safeName)
	if osType == "linux" && xmlData != "" {
		osType = detectOSFromXML(xmlData)
	}

	// 4. Check guest agent (only for running VMs).
	hasAgent := false
	agentCtx, agentCancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer agentCancel()
	if err := exec.CommandContext(agentCtx, "virsh", "qemu-agent-command", safeName, `{"execute":"guest-ping"}`).Run(); err == nil {
		hasAgent = true
	}

	// Generate recommendations based on analysis.

	// Disk bus check.
	if diskBus == "sata" || diskBus == "ide" {
		recs = append(recs, recommendation{
			Type:     "performance",
			Severity: "medium",
			Title:    "Upgrade to VirtIO disk bus",
			Detail:   fmt.Sprintf("Current bus: %s. VirtIO provides better I/O performance.", diskBus),
			Action:   "promote",
		})
		score -= 20
	}

	// Guest agent check.
	if !hasAgent {
		recs = append(recs, recommendation{
			Type:     "monitoring",
			Severity: "low",
			Title:    "Install QEMU Guest Agent",
			Detail:   "Enables filesystem, OS, and network visibility from the host.",
			Action:   "install-agent",
		})
		score -= 10
	}

	// Disk format check.
	if diskFormat == "raw" {
		recs = append(recs, recommendation{
			Type:     "storage",
			Severity: "low",
			Title:    "Convert to qcow2 format",
			Detail:   "qcow2 supports snapshots and thin provisioning.",
		})
		score -= 5
	}

	// Hugepages suggestion for large-memory Linux VMs.
	memoryMB := memoryKiB / 1024
	if memoryMB > 8192 && osType != "windows" {
		recs = append(recs, recommendation{
			Type:     "performance",
			Severity: "info",
			Title:    "Consider hugepages",
			Detail:   "VMs with >8GB memory benefit from hugepage backing.",
		})
	}

	// Windows + VirtIO confirmation.
	if osType == "windows" && diskBus == "virtio" {
		recs = append(recs, recommendation{
			Type:     "info",
			Severity: "info",
			Title:    "VirtIO drivers installed",
			Detail:   "Windows VM is using VirtIO — optimal configuration.",
		})
	}

	if score < 0 {
		score = 0
	}

	log.Printf("[vm] recommendations vm=%s count=%d score=%d os=%s bus=%s agent=%v", safeName, len(recs), score, osType, diskBus, hasAgent)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"recommendations": recs,
		"score":           score,
	})
}

// --- Security Exposure Analysis ---

// handleVMSecurity parses a VM's domain XML to identify security concerns
// such as host device passthrough, exposed VNC, and raw block devices.
func (s *Server) handleVMSecurity(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] security analysis requested for vm=%s from %s", safeName, r.RemoteAddr)

	// Get domain XML.
	xmlCtx, xmlCancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer xmlCancel()

	xmlOut, err := exec.CommandContext(xmlCtx, "virsh", "dumpxml", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	xmlData := string(xmlOut)

	type finding struct {
		Severity string `json:"severity"`
		Category string `json:"category"`
		Title    string `json:"title"`
		Detail   string `json:"detail"`
	}

	var findings []finding
	score := 100
	highCount, medCount, lowCount := 0, 0, 0

	// Parse XML for security concerns using a structural approach.
	// We use a minimal XML domain struct for targeted checks.
	type xmlGraphics struct {
		Type   string `xml:"type,attr"`
		Listen string `xml:"listen,attr"`
	}
	type xmlInterface struct {
		Type string `xml:"type,attr"`
	}
	type xmlDisk struct {
		Type string `xml:"type,attr"`
	}
	type xmlHostdev struct {
		XMLName xml.Name `xml:"hostdev"`
	}
	type xmlHugepages struct {
		XMLName xml.Name `xml:"hugepages"`
	}
	type xmlMemoryBacking struct {
		Hugepages *xmlHugepages `xml:"hugepages"`
	}
	type xmlCPU struct {
		Mode string `xml:"mode,attr"`
	}
	type xmlSecDomain struct {
		Devices struct {
			Hostdevs   []xmlHostdev   `xml:"hostdev"`
			Interfaces []xmlInterface `xml:"interface"`
			Graphics   []xmlGraphics  `xml:"graphics"`
			Disks      []xmlDisk      `xml:"disk"`
		} `xml:"devices"`
		MemoryBacking *xmlMemoryBacking `xml:"memoryBacking"`
		CPU           *xmlCPU           `xml:"cpu"`
	}

	var dom xmlSecDomain
	if err := xml.Unmarshal([]byte(xmlData), &dom); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to parse VM XML")
		return
	}

	// Check host device passthrough (HIGH).
	if len(dom.Devices.Hostdevs) > 0 {
		findings = append(findings, finding{
			Severity: "high",
			Category: "device",
			Title:    "Host device passthrough",
			Detail:   fmt.Sprintf("%d PCI device(s) attached directly to the VM", len(dom.Devices.Hostdevs)),
		})
		highCount++
		score -= 25
	}

	// Check network interfaces.
	for _, iface := range dom.Devices.Interfaces {
		switch iface.Type {
		case "direct":
			findings = append(findings, finding{
				Severity: "medium",
				Category: "network",
				Title:    "Direct host network access",
				Detail:   "Interface uses macvtap (direct) mode — VM has direct access to the host network.",
			})
			medCount++
			score -= 10
		case "bridge":
			// Check if it's a physical bridge (not virbr0).
			// A rough heuristic: look for bridge source in the raw XML.
			if strings.Contains(xmlData, `bridge='br0'`) || strings.Contains(xmlData, `bridge='br1'`) ||
				strings.Contains(xmlData, `bridge='bond0'`) {
				findings = append(findings, finding{
					Severity: "low",
					Category: "network",
					Title:    "Bridged to physical network",
					Detail:   "VM is bridged to a physical network interface — exposed to the physical network.",
				})
				lowCount++
				score -= 5
			}
		}
	}

	// Check VNC exposed on all interfaces.
	for _, g := range dom.Devices.Graphics {
		if g.Type == "vnc" && g.Listen == "0.0.0.0" {
			findings = append(findings, finding{
				Severity: "medium",
				Category: "console",
				Title:    "VNC on 0.0.0.0",
				Detail:   "VNC console accessible from all network interfaces.",
			})
			medCount++
			score -= 10
		}
	}

	// Check raw block device access.
	for _, d := range dom.Devices.Disks {
		if d.Type == "block" {
			findings = append(findings, finding{
				Severity: "medium",
				Category: "storage",
				Title:    "Raw block device access",
				Detail:   "VM has direct access to a host block device.",
			})
			medCount++
			score -= 10
			break // Only report once even if multiple block devices.
		}
	}

	// Check hugepages (info, not a risk).
	if dom.MemoryBacking != nil && dom.MemoryBacking.Hugepages != nil {
		findings = append(findings, finding{
			Severity: "info",
			Category: "memory",
			Title:    "Hugepages enabled",
			Detail:   "VM is using hugepage-backed memory.",
		})
	}

	// Check CPU host-passthrough.
	if dom.CPU != nil && dom.CPU.Mode == "host-passthrough" {
		findings = append(findings, finding{
			Severity: "low",
			Category: "cpu",
			Title:    "CPU host-passthrough mode",
			Detail:   "Full host CPU features exposed to the VM.",
		})
		lowCount++
		score -= 5
	}

	if score < 0 {
		score = 0
	}

	// Build summary.
	var summaryParts []string
	if highCount > 0 {
		summaryParts = append(summaryParts, fmt.Sprintf("%d high", highCount))
	}
	if medCount > 0 {
		summaryParts = append(summaryParts, fmt.Sprintf("%d medium", medCount))
	}
	if lowCount > 0 {
		summaryParts = append(summaryParts, fmt.Sprintf("%d low", lowCount))
	}
	summary := fmt.Sprintf("%d findings", len(findings))
	if len(summaryParts) > 0 {
		summary += " (" + strings.Join(summaryParts, ", ") + ")"
	}

	log.Printf("[vm] security vm=%s score=%d findings=%d summary=%s", safeName, score, len(findings), summary)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"findings": findings,
		"score":    score,
		"summary":  summary,
	})
}

// --- Storage Detail ---

func (s *Server) handleVMStorageDetail(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] storage-detail requested for vm=%s from %s", safeName, r.RemoteAddr)

	type diskInfo struct {
		Target          string `json:"target"`
		Source          string `json:"source"`
		ReadBytes       int64  `json:"read_bytes"`
		WriteBytes      int64  `json:"write_bytes"`
		ReadOps         int64  `json:"read_ops"`
		WriteOps        int64  `json:"write_ops"`
		Errors          int64  `json:"errors"`
		CapacityBytes   int64  `json:"capacity_bytes,omitempty"`
		AllocationBytes int64  `json:"allocation_bytes,omitempty"`
	}

	// 1. Get block device list.
	blkCtx, blkCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer blkCancel()
	blkOut, err := exec.CommandContext(blkCtx, "virsh", "domblklist", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "virsh domblklist failed")
		return
	}

	// Parse domblklist output (skip header lines).
	var disks []diskInfo
	for _, line := range strings.Split(string(blkOut), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "---") || strings.HasPrefix(line, "Target") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		src := fields[1]
		if src == "-" {
			src = ""
		}
		disks = append(disks, diskInfo{
			Target: fields[0],
			Source: src,
		})
	}

	// 2. Get block stats (human readable).
	statCtx, statCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer statCancel()
	statOut, err := exec.CommandContext(statCtx, "virsh", "domblkstat", safeName, "--human").Output()
	if err == nil {
		// Parse per-device stats. Lines look like:
		//   Device: vda
		//    rd_bytes         1234567
		//    wr_bytes         7654321
		var curIdx int = -1
		for _, line := range strings.Split(string(statOut), "\n") {
			trimmed := strings.TrimSpace(line)
			if strings.HasPrefix(trimmed, "Device:") {
				devName := strings.TrimSpace(strings.TrimPrefix(trimmed, "Device:"))
				curIdx = -1
				for i, d := range disks {
					if d.Target == devName {
						curIdx = i
						break
					}
				}
				continue
			}
			if curIdx < 0 {
				continue
			}
			parts := strings.Fields(trimmed)
			if len(parts) < 2 {
				continue
			}
			val, err := strconv.ParseInt(parts[1], 10, 64)
			if err != nil {
				log.Printf("[warn] failed to parse disk stat %s: %v", parts[1], err)
			}
			switch parts[0] {
			case "rd_bytes":
				disks[curIdx].ReadBytes = val
			case "wr_bytes":
				disks[curIdx].WriteBytes = val
			case "rd_operations":
				disks[curIdx].ReadOps = val
			case "wr_operations":
				disks[curIdx].WriteOps = val
			case "errors":
				disks[curIdx].Errors = val
			}
		}
	}

	// 3. Get disk size info for each disk via domblkinfo.
	for i, d := range disks {
		if d.Source == "" {
			continue
		}
		infoCtx, infoCancel := context.WithTimeout(r.Context(), 5*time.Second)
		infoOut, err := exec.CommandContext(infoCtx, "virsh", "domblkinfo", safeName, d.Target).Output()
		infoCancel()
		if err != nil {
			continue
		}
		for _, line := range strings.Split(string(infoOut), "\n") {
			parts := strings.Fields(line)
			if len(parts) < 2 {
				continue
			}
			val, err := strconv.ParseInt(parts[1], 10, 64)
			if err != nil {
				log.Printf("[warn] failed to parse blkinfo %s: %v", parts[1], err)
			}
			switch parts[0] {
			case "Capacity:":
				disks[i].CapacityBytes = val
			case "Allocation:":
				disks[i].AllocationBytes = val
			}
		}
	}

	// 4. Get snapshot tree.
	snapCtx, snapCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer snapCancel()
	snapOut, _ := exec.CommandContext(snapCtx, "virsh", "snapshot-list", safeName, "--tree").Output()
	snapshotTree := strings.TrimSpace(string(snapOut))

	// 5. Get pool info (best-effort).
	poolResp := map[string]interface{}{}
	poolCtx, poolCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer poolCancel()
	poolOut, err := exec.CommandContext(poolCtx, "virsh", "pool-info", "default").Output()
	if err == nil {
		for _, line := range strings.Split(string(poolOut), "\n") {
			if strings.HasPrefix(line, "Capacity:") {
				poolResp["capacity_gb"] = parsePoolSize(strings.TrimPrefix(line, "Capacity:"))
			} else if strings.HasPrefix(line, "Allocation:") {
				poolResp["used_gb"] = parsePoolSize(strings.TrimPrefix(line, "Allocation:"))
			} else if strings.HasPrefix(line, "Available:") {
				poolResp["available_gb"] = parsePoolSize(strings.TrimPrefix(line, "Available:"))
			} else if strings.HasPrefix(line, "Name:") {
				poolResp["name"] = strings.TrimSpace(strings.TrimPrefix(line, "Name:"))
			}
		}
	}

	log.Printf("[vm] storage-detail vm=%s disks=%d", safeName, len(disks))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"disks":         disks,
		"snapshot_tree": snapshotTree,
		"pool":          poolResp,
	})
}

// parsePoolSize converts virsh pool-info size strings like "100.00 GiB" to float64 GB.
func parsePoolSize(s string) float64 {
	s = strings.TrimSpace(s)
	parts := strings.Fields(s)
	if len(parts) < 2 {
		return 0
	}
	val, err := strconv.ParseFloat(parts[0], 64)
	if err != nil {
		return 0
	}
	unit := strings.ToLower(parts[1])
	switch {
	case strings.HasPrefix(unit, "tib"), strings.HasPrefix(unit, "tb"):
		return math.Round(val*1024*100) / 100
	case strings.HasPrefix(unit, "gib"), strings.HasPrefix(unit, "gb"):
		return math.Round(val*100) / 100
	case strings.HasPrefix(unit, "mib"), strings.HasPrefix(unit, "mb"):
		return math.Round(val/1024*100) / 100
	case strings.HasPrefix(unit, "kib"), strings.HasPrefix(unit, "kb"):
		return math.Round(val/1024/1024*100) / 100
	default:
		return val
	}
}

// --- Process Viewer via Guest Agent ---

func (s *Server) handleVMProcesses(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] processes requested for vm=%s from %s", safeName, r.RemoteAddr)

	type processInfo struct {
		User    string  `json:"user"`
		PID     int     `json:"pid"`
		CPU     float64 `json:"cpu"`
		Mem     float64 `json:"mem"`
		Command string  `json:"command"`
	}

	// Helper to run guest-exec and retrieve output.
	guestExec := func(path string, args []string) (string, bool) {
		// Build the exec request.
		type execArgs struct {
			Path          string   `json:"path"`
			Arg           []string `json:"arg"`
			CaptureOutput bool     `json:"capture-output"`
		}
		type execReq struct {
			Execute   string   `json:"execute"`
			Arguments execArgs `json:"arguments"`
		}
		req := execReq{
			Execute: "guest-exec",
			Arguments: execArgs{
				Path:          path,
				Arg:           args,
				CaptureOutput: true,
			},
		}
		reqJSON, err := json.Marshal(req)
		if err != nil {
			log.Printf("[warn] json marshal failed: %v", err)
		}

		// Start guest-exec.
		execCtx, execCancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer execCancel()
		out, err := exec.CommandContext(execCtx, "virsh", "qemu-agent-command", safeName, string(reqJSON)).Output()
		if err != nil {
			return "", false
		}

		// Parse PID from response.
		var execResp struct {
			Return struct {
				PID int `json:"pid"`
			} `json:"return"`
		}
		if err := json.Unmarshal(out, &execResp); err != nil {
			return "", false
		}

		// Wait briefly for process to complete, then poll status.
		time.Sleep(500 * time.Millisecond)

		type statusArgs struct {
			PID int `json:"pid"`
		}
		type statusReq struct {
			Execute   string     `json:"execute"`
			Arguments statusArgs `json:"arguments"`
		}
		sReq := statusReq{
			Execute:   "guest-exec-status",
			Arguments: statusArgs{PID: execResp.Return.PID},
		}
		sJSON, err := json.Marshal(sReq)
		if err != nil {
			log.Printf("[warn] json marshal failed: %v", err)
		}

		statusCtx, statusCancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer statusCancel()
		sOut, err := exec.CommandContext(statusCtx, "virsh", "qemu-agent-command", safeName, string(sJSON)).Output()
		if err != nil {
			return "", false
		}

		var statusResp struct {
			Return struct {
				Exited  bool   `json:"exited"`
				OutData string `json:"out-data"`
			} `json:"return"`
		}
		if err := json.Unmarshal(sOut, &statusResp); err != nil {
			return "", false
		}
		if !statusResp.Return.Exited {
			return "", false
		}

		decoded, err := base64.StdEncoding.DecodeString(statusResp.Return.OutData)
		if err != nil {
			return "", false
		}
		return string(decoded), true
	}

	// Try ps aux --sort=-%cpu first.
	output, ok := guestExec("/bin/ps", []string{"aux", "--sort=-%cpu"})
	if !ok {
		// Fallback: try top.
		output, ok = guestExec("/usr/bin/top", []string{"-bn1"})
		if !ok {
			log.Printf("[vm] processes vm=%s guest-exec not available", safeName)
			jsonResponse(w, http.StatusOK, map[string]interface{}{
				"available": false,
			})
			return
		}
	}

	// Parse ps aux output.
	var processes []processInfo
	lines := strings.Split(output, "\n")
	for i, line := range lines {
		if i == 0 { // skip header
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 11 {
			continue
		}
		pid, err := strconv.Atoi(fields[1])
		if err != nil {
			log.Printf("[warn] failed to parse pid %s: %v", fields[1], err)
		}
		cpu, err := strconv.ParseFloat(fields[2], 64)
		if err != nil {
			log.Printf("[warn] failed to parse cpu %s: %v", fields[2], err)
		}
		mem, err := strconv.ParseFloat(fields[3], 64)
		if err != nil {
			log.Printf("[warn] failed to parse mem %s: %v", fields[3], err)
		}
		cmd := strings.Join(fields[10:], " ")
		processes = append(processes, processInfo{
			User:    fields[0],
			PID:     pid,
			CPU:     cpu,
			Mem:     mem,
			Command: cmd,
		})
		if len(processes) >= 15 {
			break
		}
	}

	log.Printf("[vm] processes vm=%s count=%d", safeName, len(processes))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"available": true,
		"processes": processes,
	})
}

// --- Network Detail ---

func (s *Server) handleVMNetworkDetail(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	log.Printf("[vm] network-detail requested for vm=%s from %s", safeName, r.RemoteAddr)

	type ifaceInfo struct {
		Name      string `json:"name"`
		MAC       string `json:"mac"`
		Source    string `json:"source"`
		Model     string `json:"model"`
		RxBytes   int64  `json:"rx_bytes"`
		TxBytes   int64  `json:"tx_bytes"`
		RxPackets int64  `json:"rx_packets"`
		TxPackets int64  `json:"tx_packets"`
		RxErrors  int64  `json:"rx_errors"`
		TxErrors  int64  `json:"tx_errors"`
		RxDrops   int64  `json:"rx_drops"`
		TxDrops   int64  `json:"tx_drops"`
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Get interface list from domiflist.
	listOut, err := exec.CommandContext(ctx, "virsh", "domiflist", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("VM %s not found or domiflist failed", safeName))
		return
	}

	var ifaces []ifaceInfo
	lines := strings.Split(string(listOut), "\n")
	for _, line := range lines {
		fields := strings.Fields(line)
		// Skip header lines and separators.
		if len(fields) < 4 || fields[0] == "Interface" || strings.HasPrefix(fields[0], "-") {
			continue
		}
		iface := ifaceInfo{
			Name: fields[0],
		}
		if len(fields) >= 2 {
			// Type field (e.g. "network", "bridge").
			_ = fields[1]
		}
		if len(fields) >= 3 {
			iface.Source = fields[2]
		}
		if len(fields) >= 4 {
			iface.Model = fields[3]
		}
		if len(fields) >= 5 {
			iface.MAC = fields[4]
		}

		// Get stats for this interface via domifstat.
		statOut, err := exec.CommandContext(ctx, "virsh", "domifstat", safeName, iface.Name).Output()
		if err == nil {
			for _, sl := range strings.Split(string(statOut), "\n") {
				parts := strings.Fields(sl)
				if len(parts) < 3 {
					continue
				}
				val, err := strconv.ParseInt(parts[2], 10, 64)
				if err != nil {
					log.Printf("[warn] failed to parse ifstat %s: %v", parts[2], err)
				}
				switch parts[1] {
				case "rx_bytes":
					iface.RxBytes = val
				case "tx_bytes":
					iface.TxBytes = val
				case "rx_packets":
					iface.RxPackets = val
				case "tx_packets":
					iface.TxPackets = val
				case "rx_errs":
					iface.RxErrors = val
				case "tx_errs":
					iface.TxErrors = val
				case "rx_drop":
					iface.RxDrops = val
				case "tx_drop":
					iface.TxDrops = val
				}
			}
		}

		ifaces = append(ifaces, iface)
	}

	log.Printf("[vm] network-detail vm=%s interfaces=%d", safeName, len(ifaces))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"interfaces": ifaces,
	})
}

// --- VM Create ---

func (s *Server) handleVMCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name      string `json:"name"`
		VCPUs     int    `json:"vcpus"`
		MemoryMB  int    `json:"memory_mb"`
		DiskGB    int    `json:"disk_gb"`
		OSVariant string `json:"os_variant"`
		Network   string `json:"network"`
		CDROM     string `json:"cdrom"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Validate required fields.
	if req.Name == "" {
		jsonError(w, http.StatusBadRequest, "name is required")
		return
	}
	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid VM name: only alphanumeric, dash, underscore, dot allowed")
		return
	}
	if req.VCPUs <= 0 {
		req.VCPUs = 1
	}
	if req.MemoryMB <= 0 {
		req.MemoryMB = 1024
	}
	if req.DiskGB <= 0 {
		req.DiskGB = 10
	}
	if req.OSVariant == "" {
		req.OSVariant = "generic"
	}
	if req.Network == "" {
		req.Network = "default"
	}

	// Validate os_variant and network (alphanumeric + dash/dot/underscore only).
	safeField := regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)
	if !safeField.MatchString(req.OSVariant) {
		jsonError(w, http.StatusBadRequest, "invalid os_variant")
		return
	}
	if !safeField.MatchString(req.Network) {
		jsonError(w, http.StatusBadRequest, "invalid network name")
		return
	}
	// Validate CDROM path: must be absolute, no ".." sequences.
	if req.CDROM != "" {
		if !filepath.IsAbs(req.CDROM) {
			jsonError(w, http.StatusBadRequest, "cdrom path must be absolute")
			return
		}
		if strings.Contains(req.CDROM, "..") {
			jsonError(w, http.StatusBadRequest, "cdrom path must not contain '..'")
			return
		}
	}

	log.Printf("[vm] create requested: name=%s vcpus=%d mem=%dMB disk=%dGB os=%s net=%s cdrom=%s from %s",
		safeName, req.VCPUs, req.MemoryMB, req.DiskGB, req.OSVariant, req.Network, req.CDROM, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	defer cancel()

	// Build virt-install command.
	args := []string{
		"--name", safeName,
		"--vcpus", strconv.Itoa(req.VCPUs),
		"--memory", strconv.Itoa(req.MemoryMB),
		"--os-variant", req.OSVariant,
		"--network", "network=" + req.Network,
		"--noautoconsole",
	}

	if req.CDROM != "" {
		// Boot from ISO.
		args = append(args, "--disk", fmt.Sprintf("size=%d,format=qcow2", req.DiskGB))
		args = append(args, "--cdrom", req.CDROM)
	} else {
		// No ISO: create disk and boot from it.
		args = append(args, "--disk", fmt.Sprintf("size=%d,format=qcow2", req.DiskGB))
		args = append(args, "--boot", "hd")
		args = append(args, "--import")
	}

	out, err := exec.CommandContext(ctx, "virt-install", args...).CombinedOutput()
	if err != nil {
		log.Printf("[vm] create vm=%s FAILED: %s (output: %s)", safeName, err, strings.TrimSpace(string(out)))
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virt-install failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[vm] create vm=%s succeeded", safeName)
	s.auditLog(r, "vm_create", safeName, "ok")

	jsonResponse(w, http.StatusOK, map[string]string{
		"message": fmt.Sprintf("VM %s created successfully", safeName),
		"name":    safeName,
	})
}

// handleVMClone clones an existing VM using virt-clone.
func (s *Server) handleVMClone(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Source string `json:"source"`
		Name   string `json:"name"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Source == "" || req.Name == "" {
		jsonError(w, http.StatusBadRequest, "source and name are required")
		return
	}

	safeSource := safeNameRe.ReplaceAllString(req.Source, "")
	if safeSource == "" || safeSource != req.Source {
		jsonError(w, http.StatusBadRequest, "invalid source VM name")
		return
	}
	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid clone VM name: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	log.Printf("[vm] clone requested: source=%s name=%s from %s", safeSource, safeName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virt-clone",
		"--original", safeSource,
		"--name", safeName,
		"--auto-clone",
	).CombinedOutput()
	if err != nil {
		log.Printf("[vm] clone source=%s name=%s FAILED: %s (output: %s)", safeSource, safeName, err, strings.TrimSpace(string(out)))
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virt-clone failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[vm] clone source=%s name=%s succeeded", safeSource, safeName)
	s.auditLog(r, "vm_clone", safeName, "ok")

	jsonResponse(w, http.StatusOK, map[string]string{
		"message": "VM cloned",
		"name":    safeName,
	})
}

// handleVMResize resizes vCPUs and/or memory for a VM.
func (s *Server) handleVMResize(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		VCPUs    *int `json:"vcpus"`
		MemoryMB *int `json:"memory_mb"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.VCPUs == nil && req.MemoryMB == nil {
		jsonError(w, http.StatusBadRequest, "at least one of vcpus or memory_mb is required")
		return
	}
	if req.VCPUs != nil && (*req.VCPUs <= 0 || *req.VCPUs > 512) {
		jsonError(w, http.StatusBadRequest, "vcpus must be between 1 and 512")
		return
	}
	if req.MemoryMB != nil && (*req.MemoryMB <= 0 || *req.MemoryMB > 1048576) {
		jsonError(w, http.StatusBadRequest, "memory_mb must be between 1 and 1048576 (1TB)")
		return
	}

	log.Printf("[vm] resize requested: vm=%s vcpus=%v memory_mb=%v from %s", safeName, req.VCPUs, req.MemoryMB, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Determine if VM is running.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	var errors []string

	if req.VCPUs != nil {
		vcpuStr := strconv.Itoa(*req.VCPUs)
		if isRunning {
			out, err := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--live").CombinedOutput()
			if err != nil {
				errors = append(errors, fmt.Sprintf("setvcpus --live: %s", strings.TrimSpace(string(out))))
			}
		} else {
			out, err := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--config", "--maximum", vcpuStr).CombinedOutput()
			if err != nil {
				errors = append(errors, fmt.Sprintf("setvcpus --config: %s", strings.TrimSpace(string(out))))
			} else {
				// Also set current count.
				out2, err2 := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--config").CombinedOutput()
				if err2 != nil {
					errors = append(errors, fmt.Sprintf("setvcpus --config current: %s", strings.TrimSpace(string(out2))))
				}
			}
		}
	}

	if req.MemoryMB != nil {
		memKiB := fmt.Sprintf("%dkib", *req.MemoryMB*1024)
		if isRunning {
			out, err := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--live").CombinedOutput()
			if err != nil {
				errors = append(errors, fmt.Sprintf("setmem --live: %s", strings.TrimSpace(string(out))))
			}
		} else {
			out, err := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--config", "--maximum").CombinedOutput()
			if err != nil {
				errors = append(errors, fmt.Sprintf("setmem --config: %s", strings.TrimSpace(string(out))))
			} else {
				out2, err2 := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--config").CombinedOutput()
				if err2 != nil {
					errors = append(errors, fmt.Sprintf("setmem --config current: %s", strings.TrimSpace(string(out2))))
				}
			}
		}
	}

	if len(errors) > 0 {
		log.Printf("[vm] resize vm=%s partial failure: %v", safeName, errors)
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("resize errors: %s", strings.Join(errors, "; ")))
		return
	}

	log.Printf("[vm] resize vm=%s succeeded (running=%v)", safeName, isRunning)
	s.auditLog(r, "vm_resize", safeName, "ok")

	resp := map[string]interface{}{
		"message": "VM resized",
	}
	if req.VCPUs != nil {
		resp["vcpus"] = *req.VCPUs
	}
	if req.MemoryMB != nil {
		resp["memory_mb"] = *req.MemoryMB
	}
	jsonResponse(w, http.StatusOK, resp)
}

// handleVMImport imports an existing disk image as a new VM via virt-install --import.
func (s *Server) handleVMImport(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name     string `json:"name"`
		DiskPath string `json:"disk_path"`
		VCPUs    int    `json:"vcpus"`
		MemoryMB int    `json:"memory_mb"`
		OSVariant string `json:"os_variant"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Name == "" {
		jsonError(w, http.StatusBadRequest, "name is required")
		return
	}
	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid VM name: only alphanumeric, dash, underscore, dot allowed")
		return
	}
	if req.DiskPath == "" {
		jsonError(w, http.StatusBadRequest, "disk_path is required")
		return
	}
	if !filepath.IsAbs(req.DiskPath) {
		jsonError(w, http.StatusBadRequest, "disk_path must be absolute")
		return
	}
	if strings.Contains(req.DiskPath, "..") {
		jsonError(w, http.StatusBadRequest, "disk_path must not contain '..'")
		return
	}

	if req.VCPUs <= 0 {
		req.VCPUs = 1
	}
	if req.MemoryMB <= 0 {
		req.MemoryMB = 1024
	}
	if req.OSVariant == "" {
		req.OSVariant = "generic"
	}

	// Validate os_variant.
	safeField := regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)
	if !safeField.MatchString(req.OSVariant) {
		jsonError(w, http.StatusBadRequest, "invalid os_variant")
		return
	}

	log.Printf("[vm] import requested: name=%s disk=%s vcpus=%d mem=%dMB os=%s from %s",
		safeName, req.DiskPath, req.VCPUs, req.MemoryMB, req.OSVariant, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	defer cancel()

	args := []string{
		"--name", safeName,
		"--vcpus", strconv.Itoa(req.VCPUs),
		"--memory", strconv.Itoa(req.MemoryMB),
		"--disk", req.DiskPath,
		"--os-variant", req.OSVariant,
		"--network", "network=default",
		"--import",
		"--noautoconsole",
	}

	out, err := exec.CommandContext(ctx, "virt-install", args...).CombinedOutput()
	if err != nil {
		log.Printf("[vm] import vm=%s FAILED: %s (output: %s)", safeName, err, strings.TrimSpace(string(out)))
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("virt-install import failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[vm] import vm=%s succeeded", safeName)
	s.auditLog(r, "vm_import", safeName, "ok")

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":   fmt.Sprintf("VM %s imported successfully", safeName),
		"name":      safeName,
		"disk_path": req.DiskPath,
	})
}

// --- Disk & CDROM Management ---

// handleVMDiskAttach creates a new disk image and attaches it to a VM.
func (s *Server) handleVMDiskAttach(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		SizeGB int    `json:"size_gb"`
		Format string `json:"format"`
		Bus    string `json:"bus"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	// Defaults.
	if req.SizeGB <= 0 || req.SizeGB > 10240 {
		jsonError(w, http.StatusBadRequest, "size_gb must be > 0")
		return
	}
	if req.Format == "" {
		req.Format = "qcow2"
	}
	if req.Bus == "" {
		req.Bus = "virtio"
	}

	// Validate format and bus.
	validFormats := map[string]bool{"qcow2": true, "raw": true}
	if !validFormats[req.Format] {
		jsonError(w, http.StatusBadRequest, "format must be 'qcow2' or 'raw'")
		return
	}
	validBuses := map[string]bool{"virtio": true, "sata": true, "scsi": true, "ide": true}
	if !validBuses[req.Bus] {
		jsonError(w, http.StatusBadRequest, "bus must be one of: virtio, sata, scsi, ide")
		return
	}

	log.Printf("[vm] disk-attach requested for vm=%s size=%dGB format=%s bus=%s from %s",
		safeName, req.SizeGB, req.Format, req.Bus, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Auto-detect next available target device.
	// Get current block devices to find next free target.
	blkOut, err := exec.CommandContext(ctx, "virsh", "domblklist", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found or domblklist failed")
		return
	}

	usedTargets := map[string]bool{}
	for _, line := range strings.Split(string(blkOut), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 1 && (strings.HasPrefix(fields[0], "vd") || strings.HasPrefix(fields[0], "sd") ||
			strings.HasPrefix(fields[0], "hd")) {
			usedTargets[fields[0]] = true
		}
	}

	// Pick next target based on bus type.
	prefix := "vd"
	if req.Bus == "sata" || req.Bus == "scsi" {
		prefix = "sd"
	} else if req.Bus == "ide" {
		prefix = "hd"
	}

	target := ""
	for _, suffix := range "bcdefghijklmnopqrstuvwxyz" {
		candidate := prefix + string(suffix)
		if !usedTargets[candidate] {
			target = candidate
			break
		}
	}
	if target == "" {
		jsonError(w, http.StatusConflict, "no available disk target slots")
		return
	}

	// Create the disk image.
	timestamp := time.Now().Unix()
	diskPath := fmt.Sprintf("/var/lib/libvirt/images/%s-extra-%d.%s", safeName, timestamp, req.Format)

	createOut, err := exec.CommandContext(ctx, "qemu-img", "create", "-f", req.Format,
		diskPath, fmt.Sprintf("%dG", req.SizeGB)).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("qemu-img create failed: %s", strings.TrimSpace(string(createOut))))
		return
	}

	// Attach the disk.
	attachArgs := []string{"attach-disk", safeName, diskPath, target, "--persistent"}
	if req.Format == "qcow2" {
		attachArgs = append(attachArgs, "--subdriver", "qcow2")
	}
	attachArgs = append(attachArgs, "--targetbus", req.Bus)

	attachOut, err := exec.CommandContext(ctx, "virsh", attachArgs...).CombinedOutput()
	if err != nil {
		// Clean up the created disk on attach failure.
		os.Remove(diskPath)
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh attach-disk failed: %s", strings.TrimSpace(string(attachOut))))
		return
	}

	log.Printf("[vm] disk-attach vm=%s path=%s target=%s succeeded", safeName, diskPath, target)
	s.auditLog(r, "disk_attach", safeName, fmt.Sprintf("%s %s %dGB", target, req.Format, req.SizeGB))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":   fmt.Sprintf("Disk attached as %s", target),
		"target":    target,
		"path":      diskPath,
		"size_gb":   req.SizeGB,
		"format":    req.Format,
		"bus":       req.Bus,
	})
}

// handleVMDiskDetach detaches a disk from a VM.
func (s *Server) handleVMDiskDetach(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Target string `json:"target"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Target == "" {
		jsonError(w, http.StatusBadRequest, "target is required (e.g., vdb, sdc)")
		return
	}

	// Validate target format.
	targetRe := regexp.MustCompile(`^[a-z]{2,3}[a-z]$`)
	if !targetRe.MatchString(req.Target) {
		jsonError(w, http.StatusBadRequest, "invalid target device name")
		return
	}

	log.Printf("[vm] disk-detach requested for vm=%s target=%s from %s", safeName, req.Target, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "detach-disk", safeName, req.Target, "--persistent").CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh detach-disk failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[vm] disk-detach vm=%s target=%s succeeded", safeName, req.Target)
	s.auditLog(r, "disk_detach", safeName, req.Target)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Disk %s detached", req.Target),
		"target":  req.Target,
	})
}

// handleVMCDROMChange inserts or ejects an ISO in the VM's CDROM drive.
func (s *Server) handleVMCDROMChange(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Path string `json:"path"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	// Validate path if provided (insert mode).
	if req.Path != "" {
		if !filepath.IsAbs(req.Path) {
			jsonError(w, http.StatusBadRequest, "path must be an absolute path")
			return
		}
		if strings.Contains(req.Path, "..") {
			jsonError(w, http.StatusBadRequest, "path must not contain '..'")
			return
		}
	}

	log.Printf("[vm] cdrom-change requested for vm=%s path=%q from %s", safeName, req.Path, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Find the CDROM target from dumpxml.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	type xmlDisk struct {
		Device string `xml:"device,attr"`
		Target struct {
			Dev string `xml:"dev,attr"`
		} `xml:"target"`
	}
	type xmlDomain struct {
		Devices struct {
			Disks []xmlDisk `xml:"disk"`
		} `xml:"devices"`
	}

	var dom xmlDomain
	if err := xml.Unmarshal(xmlOut, &dom); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to parse domain XML")
		return
	}

	cdromTarget := ""
	for _, d := range dom.Devices.Disks {
		if d.Device == "cdrom" {
			cdromTarget = d.Target.Dev
			break
		}
	}

	if cdromTarget == "" {
		jsonError(w, http.StatusNotFound, "no CDROM device found in VM configuration")
		return
	}

	// Insert or eject.
	var out []byte
	if req.Path == "" {
		// Eject.
		out, err = exec.CommandContext(ctx, "virsh", "change-media", safeName, cdromTarget, "--eject").CombinedOutput()
	} else {
		// Insert.
		out, err = exec.CommandContext(ctx, "virsh", "change-media", safeName, cdromTarget, req.Path, "--insert").CombinedOutput()
	}

	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh change-media failed: %s", strings.TrimSpace(string(out))))
		return
	}

	action := "ejected"
	if req.Path != "" {
		action = "inserted"
	}

	log.Printf("[vm] cdrom-change vm=%s target=%s action=%s path=%q succeeded", safeName, cdromTarget, action, req.Path)
	s.auditLog(r, "cdrom_"+action, safeName, req.Path)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("CDROM %s: %s", cdromTarget, action),
		"target":  cdromTarget,
		"action":  action,
		"path":    req.Path,
	})
}

// --- VM Events ---

// handleVMEvents returns lifecycle events for a VM inferred from current state and audit log.
func (s *Server) handleVMEvents(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	type vmEvent struct {
		Timestamp string `json:"timestamp"`
		Type      string `json:"type"`
		Action    string `json:"action"`
		Detail    string `json:"detail"`
	}

	var events []vmEvent

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	// 1. Current state with reason.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName, "--reason").Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	stateLines := strings.Split(strings.TrimSpace(string(stateOut)), "\n")
	if len(stateLines) > 0 {
		stateStr := strings.TrimSpace(stateLines[0])
		events = append(events, vmEvent{
			Timestamp: time.Now().Format(time.RFC3339),
			Type:      "lifecycle",
			Action:    "current_state",
			Detail:    stateStr,
		})
	}

	// 2. Disk errors.
	blkErrOut, err := exec.CommandContext(ctx, "virsh", "domblkerror", safeName).Output()
	if err == nil {
		errStr := strings.TrimSpace(string(blkErrOut))
		if errStr != "" && !strings.Contains(errStr, "No errors found") {
			for _, line := range strings.Split(errStr, "\n") {
				line = strings.TrimSpace(line)
				if line != "" {
					events = append(events, vmEvent{
						Timestamp: time.Now().Format(time.RFC3339),
						Type:      "disk_error",
						Action:    "error",
						Detail:    line,
					})
				}
			}
		}
	}

	// 3. Relevant entries from the audit log.
	s.auditMu.RLock()
	for _, entry := range s.auditEntries {
		if entry.Target == safeName {
			events = append(events, vmEvent{
				Timestamp: entry.Timestamp,
				Type:      "audit",
				Action:    entry.Action,
				Detail:    entry.Result,
			})
		}
	}
	s.auditMu.RUnlock()

	// Sort events by timestamp descending (most recent first).
	sort.Slice(events, func(i, j int) bool {
		return events[i].Timestamp > events[j].Timestamp
	})

	// Limit to 50 events.
	if len(events) > 50 {
		events = events[:50]
	}

	log.Printf("[vm] events vm=%s count=%d from %s", safeName, len(events), r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"events": events,
	})
}

// --- Libvirt-to-KubeVirt Migration ---

// MigrationDomainInfo holds parsed domain XML details for migration.
type MigrationDomainInfo struct {
	Name     string
	MemoryMB int
	VCPUs    int
	IsUEFI   bool
	IsWindows bool
	Disks    []MigrationDisk
	Networks []MigrationNetwork
}

// MigrationDisk represents a disk parsed from domain XML.
type MigrationDisk struct {
	Source string
	Target string
	Bus    string
	Format string
}

// MigrationNetwork represents a network interface parsed from domain XML.
type MigrationNetwork struct {
	Type   string
	Source string
	MAC    string
	Model  string
}

// parseFullDomainXMLForMigration parses a virsh dumpxml output into a
// MigrationDomainInfo struct suitable for building a KubeVirt VM CR.
func parseFullDomainXMLForMigration(xmlData string) (*MigrationDomainInfo, error) {
	type xmlLoader struct {
		Type string `xml:"type,attr"`
	}
	type xmlOS struct {
		Loader *xmlLoader `xml:"loader"`
	}
	type xmlFeatures struct {
		HyperV *struct{} `xml:"hyperv"`
	}
	type xmlClock struct {
		Offset string `xml:"offset,attr"`
	}
	type xmlDisk struct {
		Type   string `xml:"type,attr"`
		Device string `xml:"device,attr"`
		Driver struct {
			Type string `xml:"type,attr"`
		} `xml:"driver"`
		Source struct {
			File string `xml:"file,attr"`
		} `xml:"source"`
		Target struct {
			Dev string `xml:"dev,attr"`
			Bus string `xml:"bus,attr"`
		} `xml:"target"`
	}
	type xmlInterface struct {
		Type   string `xml:"type,attr"`
		Source struct {
			Network string `xml:"network,attr"`
			Bridge  string `xml:"bridge,attr"`
		} `xml:"source"`
		MAC struct {
			Address string `xml:"address,attr"`
		} `xml:"mac"`
		Model struct {
			Type string `xml:"type,attr"`
		} `xml:"model"`
	}
	type xmlDomain struct {
		Name   string `xml:"name"`
		Memory struct {
			Unit  string `xml:"unit,attr"`
			Value int    `xml:",chardata"`
		} `xml:"memory"`
		VCPUs    int         `xml:"vcpu"`
		OS       xmlOS       `xml:"os"`
		Features xmlFeatures `xml:"features"`
		Clock    xmlClock    `xml:"clock"`
		Devices  struct {
			Disks      []xmlDisk      `xml:"disk"`
			Interfaces []xmlInterface `xml:"interface"`
		} `xml:"devices"`
	}

	var dom xmlDomain
	if err := xml.Unmarshal([]byte(xmlData), &dom); err != nil {
		return nil, fmt.Errorf("parse domain XML: %w", err)
	}

	info := &MigrationDomainInfo{
		Name:  dom.Name,
		VCPUs: dom.VCPUs,
	}
	if info.VCPUs == 0 {
		info.VCPUs = 1
	}

	// Convert memory to MB.
	switch strings.ToLower(dom.Memory.Unit) {
	case "kib":
		info.MemoryMB = dom.Memory.Value / 1024
	case "mib":
		info.MemoryMB = dom.Memory.Value
	case "gib":
		info.MemoryMB = dom.Memory.Value * 1024
	case "bytes", "b":
		info.MemoryMB = dom.Memory.Value / (1024 * 1024)
	default:
		// Default assume KiB (libvirt default).
		info.MemoryMB = dom.Memory.Value / 1024
	}
	if info.MemoryMB == 0 {
		info.MemoryMB = 1024
	}

	// Detect UEFI.
	if dom.OS.Loader != nil && dom.OS.Loader.Type == "pflash" {
		info.IsUEFI = true
	}

	// Detect Windows.
	if dom.Features.HyperV != nil || dom.Clock.Offset == "localtime" {
		info.IsWindows = true
	}

	// Parse disks (skip cdrom).
	for _, d := range dom.Devices.Disks {
		if d.Device != "disk" {
			continue
		}
		info.Disks = append(info.Disks, MigrationDisk{
			Source: d.Source.File,
			Target: d.Target.Dev,
			Bus:    d.Target.Bus,
			Format: d.Driver.Type,
		})
	}

	// Parse network interfaces.
	for _, iface := range dom.Devices.Interfaces {
		src := iface.Source.Network
		if src == "" {
			src = iface.Source.Bridge
		}
		info.Networks = append(info.Networks, MigrationNetwork{
			Type:   iface.Type,
			Source: src,
			MAC:    iface.MAC.Address,
			Model:  iface.Model.Type,
		})
	}

	return info, nil
}

func guestOSAnnotation(isWindows bool) string {
	if isWindows {
		return "windows"
	}
	return "linux"
}

// inferKubevirtOSVariant guesses a KubeVirt os-variant label from the VM / source name.
func inferKubevirtOSVariant(name string) string {
	n := strings.ToLower(name)
	if m := regexp.MustCompile(`rhel[\-_]?(\d)(\d+)`).FindStringSubmatch(n); len(m) == 3 {
		return fmt.Sprintf("rhel%s.%s", m[1], m[2])
	}
	if m := regexp.MustCompile(`rocky[\-_]?(\d+)`).FindStringSubmatch(n); len(m) == 2 {
		return fmt.Sprintf("rocky%s.0", m[1])
	}
	if m := regexp.MustCompile(`ubuntu[\-_]?(\d{2})\.?(\d{2})?`).FindStringSubmatch(n); len(m) >= 2 {
		minor := "04"
		if len(m) > 2 && m[2] != "" {
			minor = m[2]
		}
		return fmt.Sprintf("ubuntu%s.%s", m[1], minor)
	}
	if m := regexp.MustCompile(`\bu(\d{2})(\d{2})\b`).FindStringSubmatch(n); len(m) == 3 {
		return fmt.Sprintf("ubuntu%s.%s", m[1], m[2])
	}
	if m := regexp.MustCompile(`centos[\-_]?(\d+)`).FindStringSubmatch(n); len(m) == 2 {
		return fmt.Sprintf("centos%s.0", m[1])
	}
	if strings.Contains(n, "fedora") {
		if m := regexp.MustCompile(`fedora[\-_]?(\d+)`).FindStringSubmatch(n); len(m) == 2 {
			return fmt.Sprintf("fedora%s", m[1])
		}
	}
	return ""
}

// buildKubeVirtVMYAML generates a KubeVirt VirtualMachine CR YAML from
// the parsed domain info and the list of PVC names created during upload.
func buildKubeVirtVMYAML(name, ns string, info *MigrationDomainInfo, pvcNames []string) string {
	bus := "virtio"
	if info.IsWindows {
		bus = "sata"
	}

	osLabels := ""
	if info.IsWindows {
		osLabels = `
    h2kvm.io/guest-os: windows
    v9s.io/guest-os: windows
    v9s.io/rdp: enabled`
	} else {
		osLabels = `
    h2kvm.io/guest-os: linux
    v9s.io/guest-os: linux`
		if variant := inferKubevirtOSVariant(name); variant != "" {
			osLabels += fmt.Sprintf("\n    os.template.kubevirt.io/variant: %s", variant)
			osLabels += fmt.Sprintf("\n    h2kvm.io/os-variant: %s", variant)
		}
	}

	y := fmt.Sprintf(`apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: %s
  namespace: %s
  labels:
    h2kvm.io/migrated: "true"
    h2kvm.io/source: libvirt
    h2kvm.io/source-vm: %s%s
  annotations:
    h2kvm.io/guest-os: %s
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/domain: %s
    spec:
      domain:
        cpu:
          cores: %d
        resources:
          requests:
            memory: %dMi
        devices:
          disks:`, name, ns, info.Name, osLabels, guestOSAnnotation(info.IsWindows), name, info.VCPUs, info.MemoryMB)

	for i := range pvcNames {
		y += fmt.Sprintf(`
          - name: disk%d
            disk:
              bus: %s`, i, bus)
	}

	y += `
          interfaces:
          - name: default
            masquerade: {}`
	if info.IsWindows {
		y += `
            ports:
            - name: rdp
              port: 3389
              protocol: TCP`
	} else {
		y += `
            ports:
            - name: ssh
              port: 22
              protocol: TCP`
	}

	if info.IsWindows {
		y += `
          video:
          - name: default
            qxl: {}`
	} else {
		y += `
          rng: {}`
	}

	if info.IsUEFI {
		y += `
        firmware:
          bootloader:
            efi: {}`
	}

	if info.IsWindows {
		y += `
        os:
          type: windows
        features:
          acpi: {}
          apic: {}
          hyperv:
            relaxed: {}
            vapic: {}
            spinlocks:
              spinlocks: 8191
        clock:
          utc: {}
          timer:
            hpet:
              present: false
            pit:
              tickPolicy: delay
            rtc:
              tickPolicy: catchup
            hyperv: {}`
	} else {
		y += `
        os:
          type: hvm
        features:
          acpi: {}
          apic: {}
        clock:
          utc: {}
          timer:
            hpet:
              present: false
            pit:
              tickPolicy: delay
            rtc:
              tickPolicy: catchup`
	}

	y += `
      networks:
      - name: default
        pod: {}
      volumes:`

	for i, pvc := range pvcNames {
		y += fmt.Sprintf(`
      - name: disk%d
        persistentVolumeClaim:
          claimName: %s`, i, pvc)
	}

	return y
}

// handleVMMigrateToKubeVirt migrates a libvirt VM to KubeVirt.
//
// POST /api/v1/vms/{vmName}/migrate-to-kubevirt
//
// This is a synchronous endpoint that converts disks, uploads them as PVCs,
// and creates a KubeVirt VirtualMachine CR.
func (s *Server) handleVMMigrateToKubeVirt(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Namespace     string `json:"namespace"`
		KubeVirtName  string `json:"kubevirt_vm_name"`
		StorageClass  string `json:"storage_class"`
		AutoStop      bool   `json:"auto_stop"`
		AutoStart     bool   `json:"auto_start"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid request body: "+err.Error())
		return
	}

	if req.Namespace == "" {
		req.Namespace = "default"
	}
	if req.KubeVirtName == "" {
		req.KubeVirtName = safeName
	}
	// Sanitize target KubeVirt VM name.
	kvName := safeNameRe.ReplaceAllString(req.KubeVirtName, "")
	if kvName == "" {
		jsonError(w, http.StatusBadRequest, "invalid kubevirt_vm_name")
		return
	}

	log.Printf("[vm] migrate-to-kubevirt requested: vm=%s target=%s/%s storage_class=%s auto_stop=%v auto_start=%v from %s",
		safeName, req.Namespace, kvName, req.StorageClass, req.AutoStop, req.AutoStart, r.RemoteAddr)

	// Use a 10-minute timeout for the whole operation (disk convert + upload).
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()

	// Step 1: Validate VM exists via virsh dominfo.
	if _, err := exec.CommandContext(ctx, "virsh", "dominfo", safeName).Output(); err != nil {
		jsonError(w, http.StatusNotFound, "VM not found: "+safeName)
		return
	}

	// Step 2: Parse full domain XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to get VM XML: "+err.Error())
		return
	}

	info, err := parseFullDomainXMLForMigration(string(xmlOut))
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to parse VM XML: "+err.Error())
		return
	}

	if len(info.Disks) == 0 {
		jsonError(w, http.StatusBadRequest, "VM has no disks to migrate")
		return
	}

	// Step 3: Stop VM if running and auto_stop is true.
	stateOut, _ := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	state := strings.TrimSpace(string(stateOut))
	if state == "running" || state == "paused" {
		if !req.AutoStop {
			jsonError(w, http.StatusConflict, "VM is running. Set auto_stop=true or stop the VM manually.")
			return
		}
		log.Printf("[vm] migrate-to-kubevirt: shutting down vm=%s", safeName)
		exec.CommandContext(ctx, "virsh", "shutdown", safeName).Run()

		// Poll for shutdown (up to 60 seconds).
		shutdownDeadline := time.Now().Add(60 * time.Second)
		for time.Now().Before(shutdownDeadline) {
			out, _ := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
			if strings.TrimSpace(string(out)) == "shut off" {
				break
			}
			time.Sleep(2 * time.Second)
		}
		// Check final state.
		out, _ := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
		if strings.TrimSpace(string(out)) != "shut off" {
			log.Printf("[vm] migrate-to-kubevirt: graceful shutdown failed for vm=%s, forcing destroy", safeName)
			exec.CommandContext(ctx, "virsh", "destroy", safeName).Run()
			time.Sleep(2 * time.Second)
		}
	}

	// Step 4: Convert disks to raw format.
	workDir := filepath.Join(os.TempDir(), "l2k", safeName)
	if err := os.MkdirAll(workDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create work directory: "+err.Error())
		return
	}
	defer os.RemoveAll(workDir) // Clean up converted disks after upload.

	type convertedDisk struct {
		rawPath string
		sizeGB  int
	}
	var converted []convertedDisk

	for i, disk := range info.Disks {
		if disk.Source == "" {
			log.Printf("[vm] migrate-to-kubevirt: skipping disk %d with empty source", i)
			continue
		}

		srcFormat := disk.Format
		if srcFormat == "" {
			srcFormat = "qcow2"
		}

		rawName := fmt.Sprintf("%s-disk%d.raw", safeName, i)
		rawPath := filepath.Join(workDir, rawName)

		log.Printf("[vm] migrate-to-kubevirt: converting disk %d: %s (%s) -> %s", i, disk.Source, srcFormat, rawPath)

		out, err := exec.CommandContext(ctx, "qemu-img", "convert", "-f", srcFormat, "-O", "raw", disk.Source, rawPath).CombinedOutput()
		if err != nil {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("disk %d conversion failed: %s: %s", i, err, strings.TrimSpace(string(out))))
			return
		}

		// Get disk size for PVC allocation.
		fi, err := os.Stat(rawPath)
		if err != nil {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("failed to stat converted disk %d: %s", i, err))
			return
		}
		sizeGB := int(math.Ceil(float64(fi.Size()) / (1024 * 1024 * 1024)))
		if sizeGB < 1 {
			sizeGB = 1
		}

		converted = append(converted, convertedDisk{rawPath: rawPath, sizeGB: sizeGB})
	}

	if len(converted) == 0 {
		jsonError(w, http.StatusBadRequest, "no disks could be converted")
		return
	}

	// Step 5: Upload disks to KubeVirt as PVCs via virtctl image-upload.
	var pvcNames []string
	for i, cd := range converted {
		pvcName := fmt.Sprintf("%s-disk%d", kvName, i)

		log.Printf("[vm] migrate-to-kubevirt: uploading disk %d (%d GiB) as pvc/%s in namespace %s", i, cd.sizeGB, pvcName, req.Namespace)

		args := []string{
			"image-upload", "pvc", pvcName,
			"--image-path=" + cd.rawPath,
			fmt.Sprintf("--size=%dGi", cd.sizeGB),
			"--namespace=" + req.Namespace,
			"--insecure",
		}
		if req.StorageClass != "" {
			args = append(args, "--storage-class="+req.StorageClass)
		}

		out, err := s.virtctlCmd(ctx, args...).CombinedOutput()
		if err != nil {
			jsonError(w, http.StatusInternalServerError, fmt.Sprintf("disk %d upload failed: %s: %s", i, err, strings.TrimSpace(string(out))))
			return
		}

		pvcNames = append(pvcNames, pvcName)
	}

	// Step 6: Create KubeVirt VM CR via kubectl apply.
	vmYAML := buildKubeVirtVMYAML(kvName, req.Namespace, info, pvcNames)

	yamlPath := filepath.Join(workDir, kvName+"-vm.yaml")
	if err := os.WriteFile(yamlPath, []byte(vmYAML), 0644); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to write VM YAML: "+err.Error())
		return
	}

	out, err := s.kubectlCmd(ctx, "apply", "-f", yamlPath).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("kubectl apply failed: %s: %s", err, strings.TrimSpace(string(out))))
		return
	}
	log.Printf("[vm] migrate-to-kubevirt: VM CR created: %s/%s", req.Namespace, kvName)

	// Step 7: Start VM if auto_start is true.
	if req.AutoStart {
		log.Printf("[vm] migrate-to-kubevirt: starting VM %s/%s", req.Namespace, kvName)
		startOut, err := s.virtctlCmd(ctx, "start", kvName, "-n", req.Namespace).CombinedOutput()
		if err != nil {
			log.Printf("[vm] migrate-to-kubevirt: start failed (non-fatal): %s: %s", err, strings.TrimSpace(string(startOut)))
		}
	}

	s.auditLog(r, "vm_migrate_to_kubevirt", safeName, fmt.Sprintf("migrated to %s/%s (%d disks)", req.Namespace, kvName, len(pvcNames)))

	log.Printf("[vm] migrate-to-kubevirt: completed vm=%s -> %s/%s disks=%d", safeName, req.Namespace, kvName, len(pvcNames))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":   fmt.Sprintf("VM %s migrated to KubeVirt as %s/%s", safeName, req.Namespace, kvName),
		"vm_name":   kvName,
		"namespace": req.Namespace,
		"disks":     len(pvcNames),
		"pvc_names": pvcNames,
		"uefi":      info.IsUEFI,
		"windows":   info.IsWindows,
		"vcpus":     info.VCPUs,
		"memory_mb": info.MemoryMB,
	})
}
