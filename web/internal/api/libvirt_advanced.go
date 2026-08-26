// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/xml"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

// ─── GPU / PCI Passthrough ──────────────────────────────────────────────────

// handleListPCIDevices lists PCI devices suitable for passthrough (GPUs and related).
//
// GET /api/v1/host/pci-devices
func (s *Server) handleListPCIDevices(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "nodedev-list", "--cap", "pci").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to list PCI devices")
		return
	}

	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	var devices []map[string]interface{}

	// GPU-related vendor IDs and PCI class prefixes.
	gpuVendors := map[string]bool{"0x10de": true, "0x1002": true, "0x8086": true}
	gpuClasses := map[string]bool{"0x0300": true, "0x0302": true, "0x0380": true}

	for _, line := range lines {
		devName := strings.TrimSpace(line)
		if devName == "" {
			continue
		}

		xmlOut, err := exec.CommandContext(ctx, "virsh", "nodedev-dumpxml", devName).Output()
		if err != nil {
			continue
		}

		type xmlAddress struct {
			Domain   string `xml:"domain,attr"`
			Bus      string `xml:"bus,attr"`
			Slot     string `xml:"slot,attr"`
			Function string `xml:"function,attr"`
		}
		type xmlCapability struct {
			Type     string     `xml:"type,attr"`
			Class    string     `xml:"class"`
			Vendor   struct{ ID string `xml:"id,attr"` } `xml:"vendor"`
			Product  struct{ ID string `xml:"id,attr"` } `xml:"product"`
			Domain   int        `xml:"domain"`
			Bus      int        `xml:"bus"`
			Slot     int        `xml:"slot"`
			Function int        `xml:"function"`
			Driver   struct{ Name string `xml:",chardata"` } `xml:"driver>name"`
			IOMMUGroup struct {
				Number int `xml:"number,attr"`
			} `xml:"iommuGroup"`
		}
		type xmlDevice struct {
			Name       string       `xml:"name"`
			Capability xmlCapability `xml:"capability"`
		}

		var dev xmlDevice
		if err := xml.Unmarshal(xmlOut, &dev); err != nil {
			continue
		}

		cap := dev.Capability
		vendorID := cap.Vendor.ID
		classID := cap.Class

		// Filter to GPU-related devices only.
		if !gpuVendors[vendorID] || !gpuClasses[classID] {
			continue
		}

		address := fmt.Sprintf("%04x:%02x:%02x.%x", cap.Domain, cap.Bus, cap.Slot, cap.Function)

		devices = append(devices, map[string]interface{}{
			"name":        devName,
			"vendor":      vendorID,
			"product":     cap.Product.ID,
			"driver":      cap.Driver.Name,
			"iommu_group": cap.IOMMUGroup.Number,
			"address":     address,
			"class":       classID,
		})
	}

	log.Printf("[host] listPCIDevices found %d GPU devices from %s", len(devices), r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"devices": devices,
		"total":   len(devices),
	})
}

// pciAddressRe validates PCI addresses like "0000:01:00.0".
var pciAddressRe = regexp.MustCompile(`^([0-9a-fA-F]{4}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-9a-fA-F])$`)

// handleAttachGPU attaches a GPU/PCI device to a VM via hostdev passthrough.
//
// POST /api/v1/vms/{vmName}/gpu
// Body: {"address": "0000:01:00.0", "managed": true}
func (s *Server) handleAttachGPU(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Address string `json:"address"`
		Managed bool   `json:"managed"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	m := pciAddressRe.FindStringSubmatch(req.Address)
	if m == nil {
		jsonError(w, http.StatusBadRequest, "invalid PCI address format (expected 0000:01:00.0)")
		return
	}

	domain := m[1]
	bus := m[2]
	slot := m[3]
	function := m[4]

	managedStr := "no"
	if req.Managed {
		managedStr = "yes"
	}

	log.Printf("[vm] attachGPU requested: vm=%s address=%s managed=%v from %s",
		safeName, req.Address, req.Managed, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Check VM state.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	// Build hostdev XML.
	hostdevXML := fmt.Sprintf(`<hostdev mode='subsystem' type='pci' managed='%s'>
  <source>
    <address domain='0x%s' bus='0x%s' slot='0x%s' function='0x%s'/>
  </source>
</hostdev>`, managedStr, domain, bus, slot, function)

	tmpFile, err := os.CreateTemp("", "h2kweb-gpu-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(hostdevXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write device XML")
		return
	}
	tmpFile.Close()

	var attachArgs []string
	if isRunning {
		attachArgs = []string{"attach-device", safeName, tmpFile.Name(), "--live", "--config"}
	} else {
		attachArgs = []string{"attach-device", safeName, tmpFile.Name(), "--config"}
	}

	attachOut, err := exec.CommandContext(ctx, "virsh", attachArgs...).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh attach-device failed: %s", strings.TrimSpace(string(attachOut))))
		return
	}

	log.Printf("[vm] attachGPU vm=%s address=%s succeeded", safeName, req.Address)
	s.auditLog(r, "gpu_attach", safeName, req.Address)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("GPU %s attached to %s", req.Address, safeName),
		"address": req.Address,
		"managed": req.Managed,
	})
}

// handleDetachGPU detaches a GPU/PCI device from a VM.
//
// DELETE /api/v1/vms/{vmName}/gpu/{address}
func (s *Server) handleDetachGPU(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	address := chi.URLParam(r, "address")
	m := pciAddressRe.FindStringSubmatch(address)
	if m == nil {
		jsonError(w, http.StatusBadRequest, "invalid PCI address format (expected 0000:01:00.0)")
		return
	}

	domain := m[1]
	bus := m[2]
	slot := m[3]
	function := m[4]

	log.Printf("[vm] detachGPU requested: vm=%s address=%s from %s", safeName, address, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	hostdevXML := fmt.Sprintf(`<hostdev mode='subsystem' type='pci' managed='yes'>
  <source>
    <address domain='0x%s' bus='0x%s' slot='0x%s' function='0x%s'/>
  </source>
</hostdev>`, domain, bus, slot, function)

	tmpFile, err := os.CreateTemp("", "h2kweb-gpu-detach-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(hostdevXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write device XML")
		return
	}
	tmpFile.Close()

	var detachArgs []string
	if isRunning {
		detachArgs = []string{"detach-device", safeName, tmpFile.Name(), "--live", "--config"}
	} else {
		detachArgs = []string{"detach-device", safeName, tmpFile.Name(), "--config"}
	}

	detachOut, err := exec.CommandContext(ctx, "virsh", detachArgs...).CombinedOutput()
	if err != nil {
		// Fallback: try without --live.
		if isRunning {
			detachArgs2 := []string{"detach-device", safeName, tmpFile.Name(), "--config"}
			out2, err2 := exec.CommandContext(ctx, "virsh", detachArgs2...).CombinedOutput()
			if err2 != nil {
				jsonError(w, http.StatusInternalServerError,
					fmt.Sprintf("virsh detach-device failed: %s", strings.TrimSpace(string(out2))))
				return
			}
		} else {
			jsonError(w, http.StatusInternalServerError,
				fmt.Sprintf("virsh detach-device failed: %s", strings.TrimSpace(string(detachOut))))
			return
		}
	}

	log.Printf("[vm] detachGPU vm=%s address=%s succeeded", safeName, address)
	s.auditLog(r, "gpu_detach", safeName, address)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("GPU %s detached from %s", address, safeName),
		"address": address,
	})
}

// ─── NUMA / CPU Pinning ─────────────────────────────────────────────────────

// handleGetNUMATopology returns the host NUMA topology.
//
// GET /api/v1/host/numa
func (s *Server) handleGetNUMATopology(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Get nodeinfo for totals.
	nodeOut, err := exec.CommandContext(ctx, "virsh", "nodeinfo").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to get node info")
		return
	}

	var totalCPUs, totalMemMB int
	for _, line := range strings.Split(string(nodeOut), "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		switch key {
		case "CPU(s)":
			totalCPUs, _ = strconv.Atoi(val)
		case "Memory size":
			// "Memory size:      65536000 KiB" -> extract number and convert to MB.
			fields := strings.Fields(val)
			if len(fields) >= 1 {
				kib, _ := strconv.Atoi(fields[0])
				totalMemMB = kib / 1024
			}
		}
	}

	// Parse NUMA topology from virsh capabilities.
	capsOut, err := exec.CommandContext(ctx, "virsh", "capabilities").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to get capabilities")
		return
	}

	type xmlCPU struct {
		ID string `xml:"id,attr"`
	}
	type xmlMemory struct {
		Size string `xml:"size,attr"`
		Unit string `xml:"unit,attr"`
	}
	type xmlCell struct {
		ID     string    `xml:"id,attr"`
		CPUs   struct{ CPUs []xmlCPU } `xml:"cpus"`
		Memory xmlMemory `xml:"memory"`
	}
	type xmlTopology struct {
		Cells struct{ Cells []xmlCell `xml:"cell"` } `xml:"cells"`
	}
	type xmlCaps struct {
		Host struct {
			Topology xmlTopology `xml:"topology"`
		} `xml:"host"`
	}

	var caps xmlCaps
	if err := xml.Unmarshal(capsOut, &caps); err != nil {
		// Fallback: return just nodeinfo data.
		log.Printf("[host] NUMA topology parse failed, returning nodeinfo only: %v", err)
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"cells":          []interface{}{},
			"total_cpus":     totalCPUs,
			"total_memory_mb": totalMemMB,
		})
		return
	}

	var cells []map[string]interface{}
	for _, cell := range caps.Host.Topology.Cells.Cells {
		var cpuIDs []string
		for _, cpu := range cell.CPUs.CPUs {
			cpuIDs = append(cpuIDs, cpu.ID)
		}
		cpuList := strings.Join(cpuIDs, ",")

		memSize, _ := strconv.Atoi(cell.Memory.Size)
		memMB := memSize
		switch cell.Memory.Unit {
		case "KiB":
			memMB = memSize / 1024
		case "GiB":
			memMB = memSize * 1024
		}

		cells = append(cells, map[string]interface{}{
			"id":        cell.ID,
			"cpus":      cpuList,
			"memory_mb": memMB,
		})
	}

	log.Printf("[host] getNUMATopology %d cells from %s", len(cells), r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"cells":           cells,
		"total_cpus":      totalCPUs,
		"total_memory_mb": totalMemMB,
	})
}

// handleGetCPUPinning returns the current vCPU pinning for a VM.
//
// GET /api/v1/vms/{vmName}/cpu-pinning
func (s *Server) handleGetCPUPinning(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "vcpupin", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("failed to get CPU pinning: %s", strings.TrimSpace(string(out))))
		return
	}

	// Parse output like:
	//  VCPU   CPU Affinity
	// ---------------------
	//  0      0-3
	//  1      0-3
	var pinnings []map[string]interface{}
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "VCPU") || strings.HasPrefix(line, "---") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) >= 2 {
			vcpu, err := strconv.Atoi(fields[0])
			if err != nil {
				continue
			}
			pinnings = append(pinnings, map[string]interface{}{
				"vcpu": vcpu,
				"cpus": fields[1],
			})
		}
	}

	log.Printf("[vm] getCPUPinning vm=%s from %s", safeName, r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"vm":       safeName,
		"pinnings": pinnings,
	})
}

// handleSetCPUPinning sets vCPU-to-pCPU pinning for a VM.
//
// PUT /api/v1/vms/{vmName}/cpu-pinning
// Body: {"pinning": [{"vcpu": 0, "cpus": "0,1"}, {"vcpu": 1, "cpus": "2,3"}], "emulator_cpus": "0-3"}
func (s *Server) handleSetCPUPinning(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Pinning []struct {
			VCPU int    `json:"vcpu"`
			CPUs string `json:"cpus"`
		} `json:"pinning"`
		EmulatorCPUs string `json:"emulator_cpus"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if len(req.Pinning) == 0 && req.EmulatorCPUs == "" {
		jsonError(w, http.StatusBadRequest, "at least one pinning entry or emulator_cpus is required")
		return
	}

	// Validate CPU list format (digits, commas, dashes).
	cpuListRe := regexp.MustCompile(`^[0-9,\-]+$`)
	for _, p := range req.Pinning {
		if !cpuListRe.MatchString(p.CPUs) {
			jsonError(w, http.StatusBadRequest, fmt.Sprintf("invalid cpu list for vcpu %d: %s", p.VCPU, p.CPUs))
			return
		}
	}
	if req.EmulatorCPUs != "" && !cpuListRe.MatchString(req.EmulatorCPUs) {
		jsonError(w, http.StatusBadRequest, fmt.Sprintf("invalid emulator_cpus: %s", req.EmulatorCPUs))
		return
	}

	log.Printf("[vm] setCPUPinning requested: vm=%s pinnings=%d emulator=%s from %s",
		safeName, len(req.Pinning), req.EmulatorCPUs, r.RemoteAddr)

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

	// Set vCPU pinning.
	for _, p := range req.Pinning {
		vcpuStr := strconv.Itoa(p.VCPU)
		var args []string
		if isRunning {
			args = []string{"vcpupin", safeName, vcpuStr, p.CPUs, "--live", "--config"}
		} else {
			args = []string{"vcpupin", safeName, vcpuStr, p.CPUs, "--config"}
		}
		out, err := exec.CommandContext(ctx, "virsh", args...).CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("vcpu %d: %s", p.VCPU, strings.TrimSpace(string(out))))
		}
	}

	// Set emulator pinning.
	if req.EmulatorCPUs != "" {
		var args []string
		if isRunning {
			args = []string{"emulatorpin", safeName, req.EmulatorCPUs, "--live", "--config"}
		} else {
			args = []string{"emulatorpin", safeName, req.EmulatorCPUs, "--config"}
		}
		out, err := exec.CommandContext(ctx, "virsh", args...).CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("emulatorpin: %s", strings.TrimSpace(string(out))))
		}
	}

	if len(errors) > 0 {
		log.Printf("[vm] setCPUPinning vm=%s partial failure: %v", safeName, errors)
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("CPU pinning errors: %s", strings.Join(errors, "; ")))
		return
	}

	log.Printf("[vm] setCPUPinning vm=%s succeeded (running=%v)", safeName, isRunning)
	s.auditLog(r, "vm_set_cpu_pinning", safeName, fmt.Sprintf("%d pinnings", len(req.Pinning)))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":  "CPU pinning updated",
		"pinnings": len(req.Pinning),
	})
}

// handleSetNUMAPlacement sets NUMA memory placement policy for a VM (offline only).
//
// PUT /api/v1/vms/{vmName}/numa
// Body: {"mode": "strict"|"preferred"|"interleave", "nodeset": "0,1"}
func (s *Server) handleSetNUMAPlacement(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Mode    string `json:"mode"`
		Nodeset string `json:"nodeset"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Validate mode.
	validModes := map[string]bool{"strict": true, "preferred": true, "interleave": true}
	if !validModes[req.Mode] {
		jsonError(w, http.StatusBadRequest, "mode must be 'strict', 'preferred', or 'interleave'")
		return
	}

	// Validate nodeset format.
	nodesetRe := regexp.MustCompile(`^[0-9,\-]+$`)
	if !nodesetRe.MatchString(req.Nodeset) {
		jsonError(w, http.StatusBadRequest, "invalid nodeset format (expected e.g. '0' or '0,1' or '0-3')")
		return
	}

	log.Printf("[vm] setNUMAPlacement requested: vm=%s mode=%s nodeset=%s from %s",
		safeName, req.Mode, req.Nodeset, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// NUMA placement requires offline VM.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	if state == "running" {
		jsonError(w, http.StatusConflict, "VM must be shut off to change NUMA placement")
		return
	}

	// Get current domain XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to get domain XML")
		return
	}

	xmlStr := string(xmlOut)

	// Build new numatune element.
	newNumatune := fmt.Sprintf(`<numatune>
    <memory mode='%s' nodeset='%s'/>
  </numatune>`, req.Mode, req.Nodeset)

	// Replace existing <numatune> or insert before <os>.
	numatuneRe := regexp.MustCompile(`(?s)<numatune>.*?</numatune>`)
	if numatuneRe.MatchString(xmlStr) {
		xmlStr = numatuneRe.ReplaceAllString(xmlStr, newNumatune)
	} else {
		// Insert before <os>.
		xmlStr = strings.Replace(xmlStr, "<os>", newNumatune+"\n  <os>", 1)
	}

	// Write modified XML and redefine.
	tmpFile, err := os.CreateTemp("", "h2kweb-numa-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(xmlStr); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write modified XML")
		return
	}
	tmpFile.Close()

	defineOut, err := exec.CommandContext(ctx, "virsh", "define", tmpFile.Name()).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh define failed: %s", strings.TrimSpace(string(defineOut))))
		return
	}

	log.Printf("[vm] setNUMAPlacement vm=%s mode=%s nodeset=%s succeeded", safeName, req.Mode, req.Nodeset)
	s.auditLog(r, "vm_set_numa", safeName, fmt.Sprintf("mode=%s nodeset=%s", req.Mode, req.Nodeset))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": "NUMA placement configured",
		"mode":    req.Mode,
		"nodeset": req.Nodeset,
	})
}

// ─── Memory Ballooning ──────────────────────────────────────────────────────

// handleGetBalloonInfo returns memory balloon statistics for a running VM.
//
// GET /api/v1/vms/{vmName}/balloon
func (s *Server) handleGetBalloonInfo(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "dommemstat", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("failed to get balloon info: %s", strings.TrimSpace(string(out))))
		return
	}

	// Parse output like:
	// actual 1048576
	// swap_in 0
	// rss 524288
	stats := map[string]interface{}{}
	for _, line := range strings.Split(string(out), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 {
			val, err := strconv.ParseInt(fields[1], 10, 64)
			if err == nil {
				stats[fields[0]] = val
			}
		}
	}

	// Convert 'actual' from KiB to MB for convenience.
	if actual, ok := stats["actual"]; ok {
		if v, ok := actual.(int64); ok {
			stats["actual_mb"] = v / 1024
		}
	}

	log.Printf("[vm] getBalloonInfo vm=%s from %s", safeName, r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"vm":    safeName,
		"stats": stats,
	})
}

// handleSetBalloon adjusts VM memory via ballooning and optionally sets stats collection period.
//
// PUT /api/v1/vms/{vmName}/balloon
// Body: {"current_mb": 2048, "period": 10}
func (s *Server) handleSetBalloon(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		CurrentMB int `json:"current_mb"`
		Period    int `json:"period"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.CurrentMB <= 0 && req.Period <= 0 {
		jsonError(w, http.StatusBadRequest, "at least one of current_mb or period is required")
		return
	}

	if req.CurrentMB > 0 && (req.CurrentMB < 64 || req.CurrentMB > 1048576) {
		jsonError(w, http.StatusBadRequest, "current_mb must be between 64 and 1048576 (1TB)")
		return
	}

	if req.Period > 0 && req.Period > 3600 {
		jsonError(w, http.StatusBadRequest, "period must be between 1 and 3600 seconds")
		return
	}

	log.Printf("[vm] setBalloon requested: vm=%s current_mb=%d period=%d from %s",
		safeName, req.CurrentMB, req.Period, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// VM must be running for balloon operations.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	if state != "running" {
		jsonError(w, http.StatusConflict, "VM must be running for balloon adjustment")
		return
	}

	var errors []string

	// Set memory via balloon.
	if req.CurrentMB > 0 {
		memKiB := fmt.Sprintf("%d", req.CurrentMB*1024)
		out, err := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--live").CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("setmem: %s", strings.TrimSpace(string(out))))
		}
	}

	// Set balloon stats collection period.
	if req.Period > 0 {
		periodStr := strconv.Itoa(req.Period)
		out, err := exec.CommandContext(ctx, "virsh", "dommemstat", safeName, "--period", periodStr, "--live").CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("dommemstat period: %s", strings.TrimSpace(string(out))))
		}
	}

	if len(errors) > 0 {
		log.Printf("[vm] setBalloon vm=%s partial failure: %v", safeName, errors)
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("balloon errors: %s", strings.Join(errors, "; ")))
		return
	}

	log.Printf("[vm] setBalloon vm=%s succeeded", safeName)
	s.auditLog(r, "vm_set_balloon", safeName, fmt.Sprintf("mb=%d period=%d", req.CurrentMB, req.Period))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":    "Balloon configuration updated",
		"current_mb": req.CurrentMB,
		"period":     req.Period,
	})
}

// ─── Live Migration ─────────────────────────────────────────────────────────

// migrateDestRe validates libvirt connection URIs.
var migrateDestRe = regexp.MustCompile(`^qemu(\+ssh|\+tls|\+tcp)?://[a-zA-Z0-9._\-]+(:[0-9]+)?/system$`)

// handleLiveMigrate initiates live migration of a VM to another host.
//
// POST /api/v1/vms/{vmName}/live-migrate
// Body: {"destination": "qemu+ssh://host2/system", "bandwidth_mbps": 0, "compressed": false, "auto_converge": false}
func (s *Server) handleLiveMigrate(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Destination  string `json:"destination"`
		BandwidthMBPS int   `json:"bandwidth_mbps"`
		Compressed   bool   `json:"compressed"`
		AutoConverge bool   `json:"auto_converge"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Destination == "" {
		jsonError(w, http.StatusBadRequest, "destination is required")
		return
	}

	if !migrateDestRe.MatchString(req.Destination) {
		jsonError(w, http.StatusBadRequest, "invalid destination URI (expected qemu[+ssh|+tls|+tcp]://host/system)")
		return
	}

	log.Printf("[vm] liveMigrate requested: vm=%s dest=%s bw=%d compressed=%v autoconverge=%v from %s",
		safeName, req.Destination, req.BandwidthMBPS, req.Compressed, req.AutoConverge, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Verify VM is running.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	if state != "running" {
		jsonError(w, http.StatusConflict, "VM must be running for live migration")
		return
	}

	// Build virsh migrate command.
	args := []string{"migrate", "--live", "--persistent", "--verbose", safeName, req.Destination}

	if req.Compressed {
		args = append(args, "--compressed")
	}
	if req.AutoConverge {
		args = append(args, "--auto-converge")
	}
	if req.BandwidthMBPS > 0 {
		args = append(args, "--bandwidth", strconv.Itoa(req.BandwidthMBPS))
	}

	// Start migration asynchronously.
	cmd := exec.Command("virsh", args...)
	if err := cmd.Start(); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to start migration: %v", err))
		return
	}

	jobID := fmt.Sprintf("migrate-%s-%d", safeName, time.Now().UnixMilli())

	// Monitor in background.
	go func() {
		if err := cmd.Wait(); err != nil {
			log.Printf("[vm] liveMigrate vm=%s FAILED: %v", safeName, err)
		} else {
			log.Printf("[vm] liveMigrate vm=%s COMPLETED to %s", safeName, req.Destination)
		}
	}()

	log.Printf("[vm] liveMigrate vm=%s started, job=%s", safeName, jobID)
	s.auditLog(r, "vm_live_migrate", safeName, req.Destination)

	jsonResponse(w, http.StatusAccepted, map[string]interface{}{
		"message":     "Live migration started",
		"job_id":      jobID,
		"destination": req.Destination,
		"vm":          safeName,
	})
}

// handleGetMigrationStatus returns the current migration job status for a VM.
//
// GET /api/v1/vms/{vmName}/migration-status
func (s *Server) handleGetMigrationStatus(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "domjobinfo", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("failed to get migration status: %s", strings.TrimSpace(string(out))))
		return
	}

	// Parse output like:
	// Job type:         Unbounded
	// Time elapsed:     1234 ms
	// Data processed:   123.456 MiB
	// Data remaining:   789.012 MiB
	// Data total:       912.468 MiB
	// Memory processed: ...
	info := map[string]interface{}{}
	for _, line := range strings.Split(string(out), "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		// Normalize key to snake_case.
		key = strings.ToLower(strings.ReplaceAll(key, " ", "_"))
		info[key] = val
	}

	log.Printf("[vm] getMigrationStatus vm=%s from %s", safeName, r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"vm":   safeName,
		"info": info,
	})
}

// ─── SR-IOV Network ─────────────────────────────────────────────────────────

// handleListSRIOVDevices lists SR-IOV capable NICs on the host.
//
// GET /api/v1/host/sriov-devices
func (s *Server) handleListSRIOVDevices(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Find SR-IOV capable interfaces by checking sriov_totalvfs.
	out, err := exec.CommandContext(ctx, "bash", "-c",
		`for iface in /sys/class/net/*/device/sriov_totalvfs; do
			[ -f "$iface" ] || continue
			name=$(basename $(dirname $(dirname "$iface")))
			total=$(cat "$iface")
			numvfs=$(cat "$(dirname "$iface")/sriov_numvfs" 2>/dev/null || echo 0)
			pci=$(basename $(readlink -f "$(dirname "$iface")"))
			driver=$(basename $(readlink -f "$(dirname "$iface")/driver") 2>/dev/null || echo unknown)
			echo "$name|$pci|$total|$numvfs|$driver"
		done`).Output()
	if err != nil {
		// No SR-IOV devices is not an error.
		jsonResponse(w, http.StatusOK, map[string]interface{}{
			"devices": []interface{}{},
			"total":   0,
		})
		return
	}

	var devices []map[string]interface{}
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "|", 5)
		if len(parts) < 5 {
			continue
		}
		totalVFs, _ := strconv.Atoi(parts[2])
		activeVFs, _ := strconv.Atoi(parts[3])
		devices = append(devices, map[string]interface{}{
			"interface":   parts[0],
			"pci_address": parts[1],
			"total_vfs":   totalVFs,
			"active_vfs":  activeVFs,
			"driver":      parts[4],
		})
	}

	log.Printf("[host] listSRIOVDevices found %d devices from %s", len(devices), r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"devices": devices,
		"total":   len(devices),
	})
}

// handleAttachSRIOV attaches an SR-IOV VF to a VM as a PCI passthrough device.
//
// POST /api/v1/vms/{vmName}/sriov-interface
// Body: {"pf_interface": "ens4f0", "vf_index": 0, "vlan": 100, "mac": ""}
func (s *Server) handleAttachSRIOV(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		PFInterface string `json:"pf_interface"`
		VFIndex     int    `json:"vf_index"`
		VLAN        int    `json:"vlan"`
		MAC         string `json:"mac"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Validate PF interface name.
	ifaceRe := regexp.MustCompile(`^[a-zA-Z0-9._\-]+$`)
	if !ifaceRe.MatchString(req.PFInterface) {
		jsonError(w, http.StatusBadRequest, "invalid PF interface name")
		return
	}

	if req.VFIndex < 0 || req.VFIndex > 255 {
		jsonError(w, http.StatusBadRequest, "vf_index must be between 0 and 255")
		return
	}

	if req.VLAN < 0 || req.VLAN > 4095 {
		jsonError(w, http.StatusBadRequest, "vlan must be between 0 and 4095")
		return
	}

	// Validate MAC if provided.
	if req.MAC != "" {
		macRe := regexp.MustCompile(`^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$`)
		if !macRe.MatchString(req.MAC) {
			jsonError(w, http.StatusBadRequest, "invalid MAC address format (expected XX:XX:XX:XX:XX:XX)")
			return
		}
	}

	log.Printf("[vm] attachSRIOV requested: vm=%s pf=%s vf=%d vlan=%d from %s",
		safeName, req.PFInterface, req.VFIndex, req.VLAN, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Get VF PCI address from sysfs.
	virtfnLink := fmt.Sprintf("/sys/class/net/%s/device/virtfn%d", req.PFInterface, req.VFIndex)
	pciOut, err := exec.CommandContext(ctx, "readlink", "-f", virtfnLink).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound,
			fmt.Sprintf("VF %d not found on interface %s", req.VFIndex, req.PFInterface))
		return
	}

	// Extract PCI address from path like /sys/devices/pci.../0000:03:10.0
	pciPath := strings.TrimSpace(string(pciOut))
	pciAddr := pciPath[strings.LastIndex(pciPath, "/")+1:]

	m := pciAddressRe.FindStringSubmatch(pciAddr)
	if m == nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to parse VF PCI address: %s", pciAddr))
		return
	}

	domain := m[1]
	bus := m[2]
	slot := m[3]
	function := m[4]

	// Check VM state.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	// Build hostdev XML for network SR-IOV.
	hostdevXML := fmt.Sprintf(`<hostdev mode='subsystem' type='pci' managed='yes'>
  <source>
    <address domain='0x%s' bus='0x%s' slot='0x%s' function='0x%s'/>
  </source>
</hostdev>`, domain, bus, slot, function)

	tmpFile, err := os.CreateTemp("", "h2kweb-sriov-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(hostdevXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write device XML")
		return
	}
	tmpFile.Close()

	// Set VLAN and MAC on the VF before attaching (via ip link).
	if req.VLAN > 0 || req.MAC != "" {
		var ipArgs []string
		if req.MAC != "" && req.VLAN > 0 {
			ipArgs = []string{"link", "set", req.PFInterface, "vf", strconv.Itoa(req.VFIndex),
				"mac", req.MAC, "vlan", strconv.Itoa(req.VLAN)}
		} else if req.MAC != "" {
			ipArgs = []string{"link", "set", req.PFInterface, "vf", strconv.Itoa(req.VFIndex),
				"mac", req.MAC}
		} else {
			ipArgs = []string{"link", "set", req.PFInterface, "vf", strconv.Itoa(req.VFIndex),
				"vlan", strconv.Itoa(req.VLAN)}
		}
		ipOut, err := exec.CommandContext(ctx, "ip", ipArgs...).CombinedOutput()
		if err != nil {
			log.Printf("[vm] attachSRIOV warning: ip link set failed: %s", strings.TrimSpace(string(ipOut)))
			// Continue anyway, the device may still work.
		}
	}

	var attachArgs []string
	if isRunning {
		attachArgs = []string{"attach-device", safeName, tmpFile.Name(), "--live", "--config"}
	} else {
		attachArgs = []string{"attach-device", safeName, tmpFile.Name(), "--config"}
	}

	attachOut, err := exec.CommandContext(ctx, "virsh", attachArgs...).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh attach-device failed: %s", strings.TrimSpace(string(attachOut))))
		return
	}

	log.Printf("[vm] attachSRIOV vm=%s pf=%s vf=%d pci=%s succeeded", safeName, req.PFInterface, req.VFIndex, pciAddr)
	s.auditLog(r, "sriov_attach", safeName, fmt.Sprintf("pf=%s vf=%d pci=%s", req.PFInterface, req.VFIndex, pciAddr))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":     fmt.Sprintf("SR-IOV VF %d from %s attached to %s", req.VFIndex, req.PFInterface, safeName),
		"pci_address": pciAddr,
		"pf":          req.PFInterface,
		"vf_index":    req.VFIndex,
		"vlan":        req.VLAN,
	})
}
