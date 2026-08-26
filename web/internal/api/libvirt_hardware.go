// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/xml"
	"fmt"
	"html"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

// --- VM Hardware Management Endpoints ---

// handleGetHardware returns the full hardware configuration of a VM parsed from domain XML.
//
// GET /api/v1/vms/{vmName}/hardware
func (s *Server) handleGetHardware(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	// Parse domain XML into a structured response.
	type xmlVCPU struct {
		Value string `xml:",chardata"`
	}
	type xmlMemory struct {
		Value string `xml:",chardata"`
		Unit  string `xml:"unit,attr"`
	}
	type xmlCPUTopology struct {
		Sockets string `xml:"sockets,attr"`
		Cores   string `xml:"cores,attr"`
		Threads string `xml:"threads,attr"`
	}
	type xmlCPU struct {
		Topology *xmlCPUTopology `xml:"topology"`
	}
	type xmlDiskSource struct {
		File string `xml:"file,attr"`
		Dev  string `xml:"dev,attr"`
	}
	type xmlDiskTarget struct {
		Dev string `xml:"dev,attr"`
		Bus string `xml:"bus,attr"`
	}
	type xmlDiskDriver struct {
		Name  string `xml:"name,attr"`
		Type  string `xml:"type,attr"`
		Cache string `xml:"cache,attr"`
	}
	type xmlDisk struct {
		Type   string        `xml:"type,attr"`
		Device string        `xml:"device,attr"`
		Driver xmlDiskDriver `xml:"driver"`
		Source xmlDiskSource `xml:"source"`
		Target xmlDiskTarget `xml:"target"`
	}
	type xmlInterfaceSource struct {
		Network string `xml:"network,attr"`
		Bridge  string `xml:"bridge,attr"`
	}
	type xmlInterfaceMAC struct {
		Address string `xml:"address,attr"`
	}
	type xmlInterfaceModel struct {
		Type string `xml:"type,attr"`
	}
	type xmlInterface struct {
		Type   string             `xml:"type,attr"`
		MAC    xmlInterfaceMAC    `xml:"mac"`
		Source xmlInterfaceSource `xml:"source"`
		Model  xmlInterfaceModel  `xml:"model"`
	}
	type xmlTPMBackend struct {
		Type    string `xml:"type,attr"`
		Version string `xml:"version,attr"`
	}
	type xmlTPMModel struct {
		Model string `xml:"model,attr"`
	}
	type xmlTPM struct {
		Model   string        `xml:"model,attr"`
		Backend xmlTPMBackend `xml:"backend"`
	}
	type xmlBootDev struct {
		Dev string `xml:"dev,attr"`
	}
	type xmlOS struct {
		Type    string       `xml:"type"`
		Boot    []xmlBootDev `xml:"boot"`
		Loader  string       `xml:"loader"`
		NVRam   string       `xml:"nvram"`
	}
	type xmlDomain struct {
		VCPU          xmlVCPU   `xml:"vcpu"`
		Memory        xmlMemory `xml:"memory"`
		CurrentMemory xmlMemory `xml:"currentMemory"`
		CPU           xmlCPU    `xml:"cpu"`
		OS            xmlOS     `xml:"os"`
		Devices       struct {
			Disks      []xmlDisk      `xml:"disk"`
			Interfaces []xmlInterface `xml:"interface"`
			TPMs       []xmlTPM       `xml:"tpm"`
		} `xml:"devices"`
	}

	var dom xmlDomain
	if err := xml.Unmarshal(xmlOut, &dom); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to parse domain XML")
		return
	}

	// Build CPU info.
	vcpus, _ := strconv.Atoi(strings.TrimSpace(dom.VCPU.Value))
	cpuInfo := map[string]interface{}{
		"vcpus": vcpus,
	}
	if dom.CPU.Topology != nil {
		sockets, _ := strconv.Atoi(strings.TrimSpace(dom.CPU.Topology.Sockets))
		cores, _ := strconv.Atoi(strings.TrimSpace(dom.CPU.Topology.Cores))
		threads, _ := strconv.Atoi(strings.TrimSpace(dom.CPU.Topology.Threads))
		cpuInfo["sockets"] = sockets
		cpuInfo["cores"] = cores
		cpuInfo["threads"] = threads
	}

	// Build memory info (convert to MB).
	toMB := func(m xmlMemory) int {
		v, _ := strconv.Atoi(strings.TrimSpace(m.Value))
		switch m.Unit {
		case "KiB", "kib", "":
			return v / 1024
		case "GiB", "gib":
			return v * 1024
		case "MiB", "mib":
			return v
		case "bytes", "b":
			return v / (1024 * 1024)
		}
		return v / 1024
	}
	maxMB := toMB(dom.Memory)
	curMB := maxMB
	if dom.CurrentMemory.Value != "" {
		curMB = toMB(dom.CurrentMemory)
	}
	memInfo := map[string]interface{}{
		"memory_mb":     curMB,
		"max_memory_mb": maxMB,
	}

	// Build disks.
	var disks []map[string]interface{}
	for _, d := range dom.Devices.Disks {
		disk := map[string]interface{}{
			"device": d.Device,
			"target": d.Target.Dev,
			"bus":    d.Target.Bus,
		}
		if d.Source.File != "" {
			disk["path"] = d.Source.File
		} else if d.Source.Dev != "" {
			disk["path"] = d.Source.Dev
		}
		if d.Driver.Type != "" {
			disk["format"] = d.Driver.Type
		}
		if d.Driver.Cache != "" {
			disk["cache"] = d.Driver.Cache
		}
		disks = append(disks, disk)
	}

	// Build interfaces.
	var interfaces []map[string]interface{}
	for _, iface := range dom.Devices.Interfaces {
		ni := map[string]interface{}{
			"type":  iface.Type,
			"mac":   iface.MAC.Address,
			"model": iface.Model.Type,
		}
		if iface.Source.Network != "" {
			ni["network"] = iface.Source.Network
		}
		if iface.Source.Bridge != "" {
			ni["bridge"] = iface.Source.Bridge
		}
		interfaces = append(interfaces, ni)
	}

	// Build TPM info.
	var tpms []map[string]interface{}
	for _, t := range dom.Devices.TPMs {
		tpms = append(tpms, map[string]interface{}{
			"model":           t.Model,
			"backend_type":    t.Backend.Type,
			"backend_version": t.Backend.Version,
		})
	}

	// Build boot info.
	var bootOrder []string
	for _, b := range dom.OS.Boot {
		bootOrder = append(bootOrder, b.Dev)
	}
	firmware := "bios"
	if dom.OS.Loader != "" || dom.OS.NVRam != "" {
		firmware = "uefi"
	}
	bootInfo := map[string]interface{}{
		"order":    bootOrder,
		"firmware": firmware,
	}

	log.Printf("[vm] getHardware vm=%s from %s", safeName, r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"name":       safeName,
		"cpu":        cpuInfo,
		"memory":     memInfo,
		"disks":      disks,
		"interfaces": interfaces,
		"tpm":        tpms,
		"boot":       bootInfo,
	})
}

// handleSetCPU updates CPU configuration for a VM.
//
// PUT /api/v1/vms/{vmName}/cpu
// Body: {"vcpus": 4, "sockets": 1, "cores": 2, "threads": 2}
func (s *Server) handleSetCPU(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		VCPUs   int `json:"vcpus"`
		Sockets int `json:"sockets"`
		Cores   int `json:"cores"`
		Threads int `json:"threads"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.VCPUs <= 0 || req.VCPUs > 512 {
		jsonError(w, http.StatusBadRequest, "vcpus must be between 1 and 512")
		return
	}

	log.Printf("[vm] setCPU requested: vm=%s vcpus=%d sockets=%d cores=%d threads=%d from %s",
		safeName, req.VCPUs, req.Sockets, req.Cores, req.Threads, r.RemoteAddr)

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

	// Set vCPU count.
	vcpuStr := strconv.Itoa(req.VCPUs)
	if isRunning {
		out, err := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--live").CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("setvcpus --live: %s", strings.TrimSpace(string(out))))
		}
		// Also persist to config.
		out2, err2 := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--config", "--maximum", vcpuStr).CombinedOutput()
		if err2 != nil {
			errors = append(errors, fmt.Sprintf("setvcpus --config --maximum: %s", strings.TrimSpace(string(out2))))
		} else {
			out3, err3 := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--config").CombinedOutput()
			if err3 != nil {
				errors = append(errors, fmt.Sprintf("setvcpus --config: %s", strings.TrimSpace(string(out3))))
			}
		}
	} else {
		out, err := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--config", "--maximum", vcpuStr).CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("setvcpus --config: %s", strings.TrimSpace(string(out))))
		} else {
			out2, err2 := exec.CommandContext(ctx, "virsh", "setvcpus", safeName, vcpuStr, "--config").CombinedOutput()
			if err2 != nil {
				errors = append(errors, fmt.Sprintf("setvcpus --config current: %s", strings.TrimSpace(string(out2))))
			}
		}
	}

	// Set CPU topology if provided (requires XML edit for offline VMs).
	if req.Sockets > 0 && req.Cores > 0 && req.Threads > 0 {
		if err := s.setCPUTopology(ctx, safeName, req.Sockets, req.Cores, req.Threads); err != nil {
			errors = append(errors, fmt.Sprintf("topology: %v", err))
		}
	}

	if len(errors) > 0 {
		log.Printf("[vm] setCPU vm=%s partial failure: %v", safeName, errors)
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("CPU config errors: %s", strings.Join(errors, "; ")))
		return
	}

	log.Printf("[vm] setCPU vm=%s succeeded (running=%v)", safeName, isRunning)
	s.auditLog(r, "vm_set_cpu", safeName, fmt.Sprintf("vcpus=%d", req.VCPUs))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": "CPU configuration updated",
		"vcpus":   req.VCPUs,
		"sockets": req.Sockets,
		"cores":   req.Cores,
		"threads": req.Threads,
	})
}

// setCPUTopology updates the CPU topology in domain XML via virsh edit emulation.
func (s *Server) setCPUTopology(ctx context.Context, vmName string, sockets, cores, threads int) error {
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", vmName, "--inactive").Output()
	if err != nil {
		return fmt.Errorf("dumpxml: %w", err)
	}

	xmlStr := string(xmlOut)

	// Build the new topology element.
	newTopology := fmt.Sprintf(`<topology sockets="%d" cores="%d" threads="%d"/>`, sockets, cores, threads)

	// Replace existing topology or insert into <cpu> element.
	topologyRe := regexp.MustCompile(`<topology\s+[^/]*/>`)
	if topologyRe.MatchString(xmlStr) {
		xmlStr = topologyRe.ReplaceAllString(xmlStr, newTopology)
	} else {
		// Check if <cpu> element exists.
		cpuEndRe := regexp.MustCompile(`</cpu>`)
		cpuSelfCloseRe := regexp.MustCompile(`<cpu\s*/>`)
		if cpuEndRe.MatchString(xmlStr) {
			xmlStr = cpuEndRe.ReplaceAllString(xmlStr, "    "+newTopology+"\n  </cpu>")
		} else if cpuSelfCloseRe.MatchString(xmlStr) {
			xmlStr = cpuSelfCloseRe.ReplaceAllString(xmlStr, "<cpu>\n    "+newTopology+"\n  </cpu>")
		} else {
			// Insert <cpu> block before </domain>.
			xmlStr = strings.Replace(xmlStr, "</domain>",
				"  <cpu>\n    "+newTopology+"\n  </cpu>\n</domain>", 1)
		}
	}

	// Write to temp file and virsh define.
	tmpFile, err := os.CreateTemp("", "h2kweb-cpu-*.xml")
	if err != nil {
		return fmt.Errorf("create temp: %w", err)
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(xmlStr); err != nil {
		tmpFile.Close()
		return fmt.Errorf("write temp: %w", err)
	}
	tmpFile.Close()

	out, err := exec.CommandContext(ctx, "virsh", "define", tmpFile.Name()).CombinedOutput()
	if err != nil {
		return fmt.Errorf("virsh define: %s", strings.TrimSpace(string(out)))
	}

	return nil
}

// handleSetMemory updates memory configuration for a VM.
//
// PUT /api/v1/vms/{vmName}/memory
// Body: {"memory_mb": 4096, "max_memory_mb": 8192}
func (s *Server) handleSetMemory(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		MemoryMB    int `json:"memory_mb"`
		MaxMemoryMB int `json:"max_memory_mb"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.MemoryMB <= 0 || req.MemoryMB > 1048576 {
		jsonError(w, http.StatusBadRequest, "memory_mb must be between 1 and 1048576 (1TB)")
		return
	}

	maxMem := req.MaxMemoryMB
	if maxMem <= 0 {
		maxMem = req.MemoryMB
	}
	if maxMem < req.MemoryMB {
		jsonError(w, http.StatusBadRequest, "max_memory_mb must be >= memory_mb")
		return
	}

	log.Printf("[vm] setMemory requested: vm=%s memory_mb=%d max_memory_mb=%d from %s",
		safeName, req.MemoryMB, maxMem, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	var errors []string
	memKiB := fmt.Sprintf("%d", req.MemoryMB*1024)
	maxMemKiB := fmt.Sprintf("%d", maxMem*1024)

	if isRunning {
		// Live memory change.
		out, err := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--live").CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("setmem --live: %s", strings.TrimSpace(string(out))))
		}
		// Persist to config.
		out2, err2 := exec.CommandContext(ctx, "virsh", "setmaxmem", safeName, maxMemKiB, "--config").CombinedOutput()
		if err2 != nil {
			errors = append(errors, fmt.Sprintf("setmaxmem --config: %s", strings.TrimSpace(string(out2))))
		}
		out3, err3 := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--config").CombinedOutput()
		if err3 != nil {
			errors = append(errors, fmt.Sprintf("setmem --config: %s", strings.TrimSpace(string(out3))))
		}
	} else {
		// Set max memory first, then current.
		out, err := exec.CommandContext(ctx, "virsh", "setmaxmem", safeName, maxMemKiB, "--config").CombinedOutput()
		if err != nil {
			errors = append(errors, fmt.Sprintf("setmaxmem --config: %s", strings.TrimSpace(string(out))))
		} else {
			out2, err2 := exec.CommandContext(ctx, "virsh", "setmem", safeName, memKiB, "--config").CombinedOutput()
			if err2 != nil {
				errors = append(errors, fmt.Sprintf("setmem --config: %s", strings.TrimSpace(string(out2))))
			}
		}
	}

	if len(errors) > 0 {
		log.Printf("[vm] setMemory vm=%s partial failure: %v", safeName, errors)
		jsonError(w, http.StatusInternalServerError, fmt.Sprintf("memory config errors: %s", strings.Join(errors, "; ")))
		return
	}

	log.Printf("[vm] setMemory vm=%s succeeded (running=%v)", safeName, isRunning)
	s.auditLog(r, "vm_set_memory", safeName, fmt.Sprintf("mem=%dMB max=%dMB", req.MemoryMB, maxMem))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":       "Memory configuration updated",
		"memory_mb":     req.MemoryMB,
		"max_memory_mb": maxMem,
	})
}

// handleHWAddDisk creates a new disk image and attaches it to a VM.
//
// POST /api/v1/vms/{vmName}/disks
// Body: {"path": "/var/lib/libvirt/images/data.qcow2", "size_gb": 20, "bus": "virtio", "format": "qcow2", "cache": "writeback"}
func (s *Server) handleHWAddDisk(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Path   string `json:"path"`
		SizeGB int    `json:"size_gb"`
		Bus    string `json:"bus"`
		Format string `json:"format"`
		Cache  string `json:"cache"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Defaults.
	if req.Format == "" {
		req.Format = "qcow2"
	}
	if req.Bus == "" {
		req.Bus = "virtio"
	}
	if req.Cache == "" {
		req.Cache = "none"
	}
	if req.SizeGB <= 0 || req.SizeGB > 10240 {
		jsonError(w, http.StatusBadRequest, "size_gb must be between 1 and 10240")
		return
	}

	// Validate format.
	validFormats := map[string]bool{"qcow2": true, "raw": true}
	if !validFormats[req.Format] {
		jsonError(w, http.StatusBadRequest, "format must be 'qcow2' or 'raw'")
		return
	}

	// Validate bus.
	validBuses := map[string]bool{"virtio": true, "sata": true, "scsi": true, "ide": true}
	if !validBuses[req.Bus] {
		jsonError(w, http.StatusBadRequest, "bus must be one of: virtio, sata, scsi, ide")
		return
	}

	// Validate cache.
	validCaches := map[string]bool{"none": true, "writethrough": true, "writeback": true, "directsync": true, "unsafe": true}
	if !validCaches[req.Cache] {
		jsonError(w, http.StatusBadRequest, "cache must be one of: none, writethrough, writeback, directsync, unsafe")
		return
	}

	// Determine disk path.
	diskPath := req.Path
	if diskPath == "" {
		timestamp := time.Now().Unix()
		diskPath = fmt.Sprintf("/var/lib/libvirt/images/%s-data-%d.%s", safeName, timestamp, req.Format)
	} else {
		if !filepath.IsAbs(diskPath) {
			jsonError(w, http.StatusBadRequest, "path must be absolute")
			return
		}
		if strings.Contains(diskPath, "..") {
			jsonError(w, http.StatusBadRequest, "path must not contain '..'")
			return
		}
	}

	log.Printf("[vm] hwAddDisk requested: vm=%s path=%s size=%dGB bus=%s format=%s cache=%s from %s",
		safeName, diskPath, req.SizeGB, req.Bus, req.Format, req.Cache, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Determine VM state.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	// Find next available target.
	blkOut, err := exec.CommandContext(ctx, "virsh", "domblklist", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to list block devices")
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

	// Create the disk image with cleanup tracking.
	diskCreated := false
	diskAttached := false
	defer func() {
		if diskCreated && !diskAttached {
			os.Remove(diskPath)
		}
	}()

	createOut, err := exec.CommandContext(ctx, "qemu-img", "create", "-f", req.Format,
		diskPath, fmt.Sprintf("%dG", req.SizeGB)).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("qemu-img create failed: %s", strings.TrimSpace(string(createOut))))
		return
	}
	diskCreated = true

	// Build attach-device XML for more control (cache, bus).
	diskXML := fmt.Sprintf(`<disk type='file' device='disk'>
  <driver name='qemu' type='%s' cache='%s'/>
  <source file='%s'/>
  <target dev='%s' bus='%s'/>
</disk>`, req.Format, req.Cache, diskPath, target, req.Bus)

	tmpFile, err := os.CreateTemp("", "h2kweb-disk-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(diskXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write disk XML")
		return
	}
	tmpFile.Close()

	// Attach: try --live --config for running, --config for stopped.
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
	diskAttached = true

	log.Printf("[vm] hwAddDisk vm=%s path=%s target=%s succeeded", safeName, diskPath, target)
	s.auditLog(r, "hw_disk_add", safeName, fmt.Sprintf("%s %s %dGB", target, req.Format, req.SizeGB))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Disk attached as %s", target),
		"target":  target,
		"path":    diskPath,
		"size_gb": req.SizeGB,
		"format":  req.Format,
		"bus":     req.Bus,
		"cache":   req.Cache,
	})
}

// handleHWRemoveDisk detaches a disk from a VM by target device name.
//
// DELETE /api/v1/vms/{vmName}/disks/{target}
func (s *Server) handleHWRemoveDisk(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	target := chi.URLParam(r, "target")
	targetRe := regexp.MustCompile(`^[a-z]{2,3}[a-z]$`)
	if !targetRe.MatchString(target) {
		jsonError(w, http.StatusBadRequest, "invalid target device name (e.g., vdb, sdc)")
		return
	}

	log.Printf("[vm] hwRemoveDisk requested: vm=%s target=%s from %s", safeName, target, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Determine VM state.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	var detachArgs []string
	if isRunning {
		detachArgs = []string{"detach-disk", safeName, target, "--live", "--config"}
	} else {
		detachArgs = []string{"detach-disk", safeName, target, "--config"}
	}

	out, err := exec.CommandContext(ctx, "virsh", detachArgs...).CombinedOutput()
	if err != nil {
		// Fallback: try without --live if it failed.
		if isRunning {
			out2, err2 := exec.CommandContext(ctx, "virsh", "detach-disk", safeName, target, "--config").CombinedOutput()
			if err2 != nil {
				jsonError(w, http.StatusInternalServerError,
					fmt.Sprintf("virsh detach-disk failed: %s", strings.TrimSpace(string(out2))))
				return
			}
		} else {
			jsonError(w, http.StatusInternalServerError,
				fmt.Sprintf("virsh detach-disk failed: %s", strings.TrimSpace(string(out))))
			return
		}
	}

	log.Printf("[vm] hwRemoveDisk vm=%s target=%s succeeded", safeName, target)
	s.auditLog(r, "hw_disk_remove", safeName, target)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Disk %s detached", target),
		"target":  target,
	})
}

// handleHWAddInterface attaches a network interface to a VM.
//
// POST /api/v1/vms/{vmName}/interfaces
// Body: {"network": "default", "model": "virtio", "mac": ""}
func (s *Server) handleHWAddInterface(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Network string `json:"network"`
		Model   string `json:"model"`
		MAC     string `json:"mac"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Network == "" {
		req.Network = "default"
	}
	if req.Model == "" {
		req.Model = "virtio"
	}

	// Validate network name.
	netRe := regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)
	if !netRe.MatchString(req.Network) {
		jsonError(w, http.StatusBadRequest, "invalid network name")
		return
	}

	// Validate model.
	validModels := map[string]bool{"virtio": true, "e1000": true, "e1000e": true, "rtl8139": true}
	if !validModels[req.Model] {
		jsonError(w, http.StatusBadRequest, "model must be one of: virtio, e1000, e1000e, rtl8139")
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

	log.Printf("[vm] hwAddInterface requested: vm=%s network=%s model=%s mac=%s from %s",
		safeName, req.Network, req.Model, req.MAC, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	isRunning := state == "running"

	// Build interface XML.
	macLine := ""
	if req.MAC != "" {
		macLine = fmt.Sprintf("\n  <mac address='%s'/>", req.MAC)
	}
	ifaceXML := fmt.Sprintf(`<interface type='network'>%s
  <source network='%s'/>
  <model type='%s'/>
</interface>`, macLine, req.Network, req.Model)

	tmpFile, err := os.CreateTemp("", "h2kweb-nic-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(ifaceXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write interface XML")
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

	log.Printf("[vm] hwAddInterface vm=%s network=%s model=%s succeeded", safeName, req.Network, req.Model)
	s.auditLog(r, "hw_nic_add", safeName, fmt.Sprintf("network=%s model=%s", req.Network, req.Model))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Interface attached to network %s", req.Network),
		"network": req.Network,
		"model":   req.Model,
		"mac":     req.MAC,
	})
}

// handleHWRemoveInterface detaches a network interface from a VM by MAC address.
//
// DELETE /api/v1/vms/{vmName}/interfaces/{mac}
func (s *Server) handleHWRemoveInterface(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	mac := chi.URLParam(r, "mac")
	macRe := regexp.MustCompile(`^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$`)
	if !macRe.MatchString(mac) {
		jsonError(w, http.StatusBadRequest, "invalid MAC address format (expected XX:XX:XX:XX:XX:XX)")
		return
	}

	log.Printf("[vm] hwRemoveInterface requested: vm=%s mac=%s from %s", safeName, mac, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Get domain XML to find the interface with the given MAC.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	// Parse to find the matching interface XML.
	type xmlIfaceMAC struct {
		Address string `xml:"address,attr"`
	}
	type xmlIfaceSource struct {
		Network string `xml:"network,attr"`
		Bridge  string `xml:"bridge,attr"`
	}
	type xmlIfaceModel struct {
		Type string `xml:"type,attr"`
	}
	type xmlIface struct {
		Type   string         `xml:"type,attr"`
		MAC    xmlIfaceMAC    `xml:"mac"`
		Source xmlIfaceSource `xml:"source"`
		Model  xmlIfaceModel  `xml:"model"`
	}
	type xmlDom struct {
		Devices struct {
			Interfaces []xmlIface `xml:"interface"`
		} `xml:"devices"`
	}

	var dom xmlDom
	if err := xml.Unmarshal(xmlOut, &dom); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to parse domain XML")
		return
	}

	// Find the interface matching the MAC.
	var found *xmlIface
	for i, iface := range dom.Devices.Interfaces {
		if strings.EqualFold(iface.MAC.Address, mac) {
			found = &dom.Devices.Interfaces[i]
			break
		}
	}
	if found == nil {
		jsonError(w, http.StatusNotFound, fmt.Sprintf("no interface with MAC %s found", mac))
		return
	}

	// Build the detach XML.
	sourceAttr := ""
	if found.Source.Network != "" {
		sourceAttr = fmt.Sprintf("network='%s'", found.Source.Network)
	} else if found.Source.Bridge != "" {
		sourceAttr = fmt.Sprintf("bridge='%s'", found.Source.Bridge)
	}

	detachXML := fmt.Sprintf(`<interface type='%s'>
  <mac address='%s'/>
  <source %s/>
  <model type='%s'/>
</interface>`, found.Type, found.MAC.Address, sourceAttr, found.Model.Type)

	tmpFile, err := os.CreateTemp("", "h2kweb-nic-detach-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(detachXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write detach XML")
		return
	}
	tmpFile.Close()

	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	isRunning := strings.TrimSpace(string(stateOut)) == "running"

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

	log.Printf("[vm] hwRemoveInterface vm=%s mac=%s succeeded", safeName, mac)
	s.auditLog(r, "hw_nic_remove", safeName, mac)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Interface with MAC %s detached", mac),
		"mac":     mac,
	})
}

// handleHWCDROM inserts or ejects a CDROM ISO.
//
// PUT /api/v1/vms/{vmName}/cdrom
// Body: {"path": "/path/to/iso", "eject": false}
func (s *Server) handleHWCDROM(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Path  string `json:"path"`
		Eject bool   `json:"eject"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if !req.Eject && req.Path == "" {
		jsonError(w, http.StatusBadRequest, "path is required when not ejecting")
		return
	}
	if req.Path != "" {
		if !filepath.IsAbs(req.Path) {
			jsonError(w, http.StatusBadRequest, "path must be absolute")
			return
		}
		if strings.Contains(req.Path, "..") {
			jsonError(w, http.StatusBadRequest, "path must not contain '..'")
			return
		}
	}

	log.Printf("[vm] hwCDROM requested: vm=%s path=%q eject=%v from %s", safeName, req.Path, req.Eject, r.RemoteAddr)

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

	var out []byte
	if req.Eject || req.Path == "" {
		out, err = exec.CommandContext(ctx, "virsh", "change-media", safeName, cdromTarget, "--eject").CombinedOutput()
	} else {
		out, err = exec.CommandContext(ctx, "virsh", "change-media", safeName, cdromTarget, req.Path, "--insert").CombinedOutput()
	}

	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh change-media failed: %s", strings.TrimSpace(string(out))))
		return
	}

	action := "ejected"
	if !req.Eject && req.Path != "" {
		action = "inserted"
	}

	log.Printf("[vm] hwCDROM vm=%s target=%s action=%s path=%q succeeded", safeName, cdromTarget, action, req.Path)
	s.auditLog(r, "hw_cdrom_"+action, safeName, req.Path)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("CDROM %s: %s", cdromTarget, action),
		"target":  cdromTarget,
		"action":  action,
		"path":    req.Path,
	})
}

// handleHWAddTPM adds a TPM device to a VM (offline only).
//
// POST /api/v1/vms/{vmName}/tpm
// Body: {"model": "tpm-tis", "version": "2.0"}
func (s *Server) handleHWAddTPM(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Model   string `json:"model"`
		Version string `json:"version"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Model == "" {
		req.Model = "tpm-tis"
	}
	if req.Version == "" {
		req.Version = "2.0"
	}

	// Validate model.
	validModels := map[string]bool{"tpm-tis": true, "tpm-crb": true}
	if !validModels[req.Model] {
		jsonError(w, http.StatusBadRequest, "model must be 'tpm-tis' or 'tpm-crb'")
		return
	}

	// Validate version.
	validVersions := map[string]bool{"1.2": true, "2.0": true}
	if !validVersions[req.Version] {
		jsonError(w, http.StatusBadRequest, "version must be '1.2' or '2.0'")
		return
	}

	log.Printf("[vm] hwAddTPM requested: vm=%s model=%s version=%s from %s", safeName, req.Model, req.Version, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Check if VM is running -- TPM can only be added offline.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	if state == "running" {
		jsonError(w, http.StatusConflict, "VM must be shut off to add a TPM device")
		return
	}

	// Check if TPM already exists.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to get domain XML")
		return
	}

	if strings.Contains(string(xmlOut), "<tpm ") {
		jsonError(w, http.StatusConflict, "VM already has a TPM device")
		return
	}

	// Build TPM XML and attach via virsh attach-device.
	tpmXML := fmt.Sprintf(`<tpm model='%s'>
  <backend type='emulator' version='%s'/>
</tpm>`, req.Model, req.Version)

	tmpFile, err := os.CreateTemp("", "h2kweb-tpm-*.xml")
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to create temp file")
		return
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.WriteString(tpmXML); err != nil {
		tmpFile.Close()
		jsonError(w, http.StatusInternalServerError, "failed to write TPM XML")
		return
	}
	tmpFile.Close()

	attachOut, err := exec.CommandContext(ctx, "virsh", "attach-device", safeName, tmpFile.Name(), "--config").CombinedOutput()
	if err != nil {
		// Fallback: modify XML directly if attach-device doesn't support TPM.
		xmlStr := string(xmlOut)
		tpmBlock := fmt.Sprintf("    <tpm model='%s'>\n      <backend type='emulator' version='%s'/>\n    </tpm>", req.Model, req.Version)
		xmlStr = strings.Replace(xmlStr, "</devices>", tpmBlock+"\n  </devices>", 1)

		tmpDefine, err2 := os.CreateTemp("", "h2kweb-tpm-define-*.xml")
		if err2 != nil {
			jsonError(w, http.StatusInternalServerError,
				fmt.Sprintf("virsh attach-device failed: %s", strings.TrimSpace(string(attachOut))))
			return
		}
		defer os.Remove(tmpDefine.Name())

		if _, err2 := tmpDefine.WriteString(xmlStr); err2 != nil {
			tmpDefine.Close()
			jsonError(w, http.StatusInternalServerError, "failed to write modified XML")
			return
		}
		tmpDefine.Close()

		defineOut, err2 := exec.CommandContext(ctx, "virsh", "define", tmpDefine.Name()).CombinedOutput()
		if err2 != nil {
			jsonError(w, http.StatusInternalServerError,
				fmt.Sprintf("failed to add TPM: %s", strings.TrimSpace(string(defineOut))))
			return
		}
	}

	log.Printf("[vm] hwAddTPM vm=%s model=%s version=%s succeeded", safeName, req.Model, req.Version)
	s.auditLog(r, "hw_tpm_add", safeName, fmt.Sprintf("model=%s version=%s", req.Model, req.Version))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": "TPM device added",
		"model":   req.Model,
		"version": req.Version,
	})
}

// handleSetBoot updates the boot order and firmware type for a VM (offline only).
//
// PUT /api/v1/vms/{vmName}/boot
// Body: {"order": ["hd", "cdrom", "network"], "firmware": "bios"|"uefi"}
func (s *Server) handleSetBoot(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "vmName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid VM name")
		return
	}

	var req struct {
		Order    []string `json:"order"`
		Firmware string   `json:"firmware"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if len(req.Order) == 0 && req.Firmware == "" {
		jsonError(w, http.StatusBadRequest, "at least one of 'order' or 'firmware' is required")
		return
	}

	// Validate boot devices.
	validDevices := map[string]bool{"hd": true, "cdrom": true, "network": true, "fd": true}
	for _, dev := range req.Order {
		if !validDevices[dev] {
			jsonError(w, http.StatusBadRequest, fmt.Sprintf("invalid boot device: %s (must be hd, cdrom, network, or fd)", dev))
			return
		}
	}

	// Validate firmware.
	if req.Firmware != "" && req.Firmware != "bios" && req.Firmware != "uefi" {
		jsonError(w, http.StatusBadRequest, "firmware must be 'bios' or 'uefi'")
		return
	}

	log.Printf("[vm] setBoot requested: vm=%s order=%v firmware=%s from %s", safeName, req.Order, req.Firmware, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Require VM to be off for boot config changes.
	stateOut, err := exec.CommandContext(ctx, "virsh", "domstate", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}
	state := strings.TrimSpace(string(stateOut))
	if state == "running" {
		jsonError(w, http.StatusConflict, "VM must be shut off to change boot configuration")
		return
	}

	// Get current XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to get domain XML")
		return
	}

	xmlStr := string(xmlOut)

	// Update boot order.
	if len(req.Order) > 0 {
		// Remove existing <boot> elements.
		bootRe := regexp.MustCompile(`\s*<boot dev='[^']*'/>\s*`)
		xmlStr = bootRe.ReplaceAllString(xmlStr, "\n")

		// Build new boot elements.
		var bootLines []string
		for _, dev := range req.Order {
			bootLines = append(bootLines, fmt.Sprintf("    <boot dev='%s'/>", dev))
		}
		newBoots := strings.Join(bootLines, "\n")

		// Insert after <type ...>...</type> in <os>.
		typeEndRe := regexp.MustCompile(`(</type>)`)
		xmlStr = typeEndRe.ReplaceAllString(xmlStr, "${1}\n"+newBoots)
	}

	// Update firmware (BIOS vs UEFI).
	if req.Firmware == "uefi" {
		// Add UEFI loader if not present.
		if !strings.Contains(xmlStr, "<loader") {
			// Detect architecture for correct firmware path.
			loaderPath := "/usr/share/OVMF/OVMF_CODE.fd"
			if _, err := os.Stat("/usr/share/edk2/ovmf/OVMF_CODE.fd"); err == nil {
				loaderPath = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
			} else if _, err := os.Stat("/usr/share/OVMF/OVMF_CODE.secboot.fd"); err == nil {
				loaderPath = "/usr/share/OVMF/OVMF_CODE.secboot.fd"
			}

			loaderXML := fmt.Sprintf("    <loader readonly='yes' type='pflash'>%s</loader>", html.EscapeString(loaderPath))
			typeEndRe := regexp.MustCompile(`(</type>)`)
			xmlStr = typeEndRe.ReplaceAllString(xmlStr, "${1}\n"+loaderXML)
		}
	} else if req.Firmware == "bios" {
		// Remove UEFI loader and nvram if present.
		loaderRe := regexp.MustCompile(`\s*<loader[^>]*>.*?</loader>`)
		xmlStr = loaderRe.ReplaceAllString(xmlStr, "")
		nvramRe := regexp.MustCompile(`\s*<nvram[^>]*>.*?</nvram>`)
		xmlStr = nvramRe.ReplaceAllString(xmlStr, "")
		nvramSelfRe := regexp.MustCompile(`\s*<nvram[^/]*/>\s*`)
		xmlStr = nvramSelfRe.ReplaceAllString(xmlStr, "")
	}

	// Write modified XML and redefine.
	tmpFile, err := os.CreateTemp("", "h2kweb-boot-*.xml")
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

	log.Printf("[vm] setBoot vm=%s order=%v firmware=%s succeeded", safeName, req.Order, req.Firmware)
	s.auditLog(r, "vm_set_boot", safeName, fmt.Sprintf("order=%v firmware=%s", req.Order, req.Firmware))

	resp := map[string]interface{}{
		"message": "Boot configuration updated",
	}
	if len(req.Order) > 0 {
		resp["order"] = req.Order
	}
	if req.Firmware != "" {
		resp["firmware"] = req.Firmware
	}
	jsonResponse(w, http.StatusOK, resp)
}
