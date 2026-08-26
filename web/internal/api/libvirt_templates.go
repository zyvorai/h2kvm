// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

const templateBaseDir = "/var/lib/libvirt/templates"

// templateMeta stores metadata about a saved template.
type templateMeta struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	SourceVM    string   `json:"source_vm"`
	CreatedAt   string   `json:"created_at"`
	VCPUs       int      `json:"vcpus"`
	MemoryMB    int      `json:"memory_mb"`
	Disks       []string `json:"disks"`
}

// handleListTemplates lists all saved VM templates.
//
// GET /api/v1/templates
func (s *Server) handleListTemplates(w http.ResponseWriter, r *http.Request) {
	entries, err := os.ReadDir(templateBaseDir)
	if err != nil {
		// Directory doesn't exist yet -- return empty list.
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}

	var templates []templateMeta
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		metaPath := filepath.Join(templateBaseDir, entry.Name(), "template.json")
		data, err := os.ReadFile(metaPath)
		if err != nil {
			continue
		}
		var meta templateMeta
		if err := json.Unmarshal(data, &meta); err != nil {
			continue
		}
		templates = append(templates, meta)
	}

	log.Printf("[templates] listTemplates count=%d from %s", len(templates), r.RemoteAddr)
	jsonResponse(w, http.StatusOK, templates)
}

// handleCreateTemplate creates a template from an existing VM.
//
// POST /api/v1/templates
// Body: {"source_vm": "myvm", "name": "template-name", "description": "A base template"}
func (s *Server) handleCreateTemplate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		SourceVM    string `json:"source_vm"`
		Name        string `json:"name"`
		Description string `json:"description"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	safeSource := safeNameRe.ReplaceAllString(req.SourceVM, "")
	if safeSource == "" || safeSource != req.SourceVM {
		jsonError(w, http.StatusBadRequest, "invalid source_vm name")
		return
	}

	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid template name: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	log.Printf("[templates] createTemplate source=%s name=%s from %s", safeSource, safeName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	// Dump the source VM XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeSource, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "source VM not found")
		return
	}

	// Parse XML to get disk paths, vCPUs, and memory.
	type xmlVCPU struct {
		Value string `xml:",chardata"`
	}
	type xmlMemory struct {
		Value string `xml:",chardata"`
		Unit  string `xml:"unit,attr"`
	}
	type xmlDiskSource struct {
		File string `xml:"file,attr"`
	}
	type xmlDisk struct {
		Device string        `xml:"device,attr"`
		Source xmlDiskSource `xml:"source"`
	}
	type xmlDomain struct {
		VCPU   xmlVCPU   `xml:"vcpu"`
		Memory xmlMemory `xml:"memory"`
		Devices struct {
			Disks []xmlDisk `xml:"disk"`
		} `xml:"devices"`
	}

	var dom xmlDomain
	if err := xml.Unmarshal(xmlOut, &dom); err != nil {
		jsonError(w, http.StatusInternalServerError, "failed to parse domain XML")
		return
	}

	// Create template directory.
	templateDir := filepath.Join(templateBaseDir, safeName)
	if _, err := os.Stat(templateDir); err == nil {
		jsonError(w, http.StatusConflict, fmt.Sprintf("template %s already exists", safeName))
		return
	}
	if err := os.MkdirAll(templateDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to create template directory: %v", err))
		return
	}

	// Save domain XML.
	xmlPath := filepath.Join(templateDir, "domain.xml")
	if err := os.WriteFile(xmlPath, xmlOut, 0644); err != nil {
		os.RemoveAll(templateDir)
		jsonError(w, http.StatusInternalServerError, "failed to save domain XML")
		return
	}

	// Copy disk images.
	var diskPaths []string
	var copyErrors []string
	for _, d := range dom.Devices.Disks {
		if d.Device != "disk" || d.Source.File == "" {
			continue
		}
		srcPath := d.Source.File
		dstName := filepath.Base(srcPath)
		dstPath := filepath.Join(templateDir, dstName)

		copyOut, err := exec.CommandContext(ctx, "qemu-img", "convert", "-O", "qcow2",
			"-c", srcPath, dstPath).CombinedOutput()
		if err != nil {
			copyErrors = append(copyErrors, fmt.Sprintf("%s: %s", srcPath, strings.TrimSpace(string(copyOut))))
			continue
		}
		diskPaths = append(diskPaths, dstName)
	}

	if len(copyErrors) > 0 && len(diskPaths) == 0 {
		os.RemoveAll(templateDir)
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to copy disks: %s", strings.Join(copyErrors, "; ")))
		return
	}

	// Parse vCPUs and memory.
	vcpus := 0
	fmt.Sscanf(dom.VCPU.Value, "%d", &vcpus)

	memVal := 0
	fmt.Sscanf(dom.Memory.Value, "%d", &memVal)
	memMB := memVal
	switch dom.Memory.Unit {
	case "KiB", "kib":
		memMB = memVal / 1024
	case "GiB", "gib":
		memMB = memVal * 1024
	case "bytes", "b":
		memMB = memVal / (1024 * 1024)
	}

	// Save metadata.
	meta := templateMeta{
		Name:        safeName,
		Description: req.Description,
		SourceVM:    safeSource,
		CreatedAt:   time.Now().Format(time.RFC3339),
		VCPUs:       vcpus,
		MemoryMB:    memMB,
		Disks:       diskPaths,
	}

	metaData, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		os.RemoveAll(templateDir)
		jsonError(w, http.StatusInternalServerError, "failed to marshal template metadata")
		return
	}

	metaPath := filepath.Join(templateDir, "template.json")
	if err := os.WriteFile(metaPath, metaData, 0644); err != nil {
		os.RemoveAll(templateDir)
		jsonError(w, http.StatusInternalServerError, "failed to save template metadata")
		return
	}

	log.Printf("[templates] createTemplate name=%s source=%s disks=%d succeeded", safeName, safeSource, len(diskPaths))
	s.auditLog(r, "template_create", safeName, fmt.Sprintf("source=%s disks=%d", safeSource, len(diskPaths)))

	resp := map[string]interface{}{
		"message":  fmt.Sprintf("Template %s created from %s", safeName, safeSource),
		"name":     safeName,
		"source":   safeSource,
		"disks":    len(diskPaths),
		"vcpus":    vcpus,
		"memory_mb": memMB,
	}
	if len(copyErrors) > 0 {
		resp["warnings"] = copyErrors
	}
	jsonResponse(w, http.StatusOK, resp)
}

// handleDeployTemplate deploys a new VM from a template.
//
// POST /api/v1/templates/{name}/deploy
// Body: {"vm_name": "new-vm", "vcpus": 4, "memory_mb": 4096}
func (s *Server) handleDeployTemplate(w http.ResponseWriter, r *http.Request) {
	tplName := chi.URLParam(r, "name")
	safeTpl := safeNameRe.ReplaceAllString(tplName, "")
	if safeTpl == "" || safeTpl != tplName {
		jsonError(w, http.StatusBadRequest, "invalid template name")
		return
	}

	var req struct {
		VMName   string `json:"vm_name"`
		VCPUs    int    `json:"vcpus"`
		MemoryMB int    `json:"memory_mb"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	safeVM := safeNameRe.ReplaceAllString(req.VMName, "")
	if safeVM == "" || safeVM != req.VMName {
		jsonError(w, http.StatusBadRequest, "invalid vm_name: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	log.Printf("[templates] deployTemplate template=%s vm=%s from %s", safeTpl, safeVM, r.RemoteAddr)

	templateDir := filepath.Join(templateBaseDir, safeTpl)

	// Load template metadata.
	metaPath := filepath.Join(templateDir, "template.json")
	metaData, err := os.ReadFile(metaPath)
	if err != nil {
		jsonError(w, http.StatusNotFound, "template not found")
		return
	}

	var meta templateMeta
	if err := json.Unmarshal(metaData, &meta); err != nil {
		jsonError(w, http.StatusInternalServerError, "corrupt template metadata")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	// Load domain XML.
	xmlPath := filepath.Join(templateDir, "domain.xml")
	xmlData, err := os.ReadFile(xmlPath)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "template domain.xml missing")
		return
	}

	xmlStr := string(xmlData)

	// Replace VM name in XML.
	nameRe := strings.NewReplacer(
		"<name>"+meta.SourceVM+"</name>", "<name>"+safeVM+"</name>",
	)
	xmlStr = nameRe.Replace(xmlStr)

	// Remove UUID so libvirt generates a new one.
	uuidStart := strings.Index(xmlStr, "<uuid>")
	uuidEnd := strings.Index(xmlStr, "</uuid>")
	if uuidStart >= 0 && uuidEnd >= 0 {
		xmlStr = xmlStr[:uuidStart] + xmlStr[uuidEnd+len("</uuid>"):]
	}

	// Copy template disks to /var/lib/libvirt/images/.
	imgDir := "/var/lib/libvirt/images"
	var newDiskPaths []string
	for _, diskName := range meta.Disks {
		srcPath := filepath.Join(templateDir, diskName)
		// Prefix disk with new VM name to avoid conflicts.
		dstName := safeVM + "-" + diskName
		dstPath := filepath.Join(imgDir, dstName)

		copyOut, err := exec.CommandContext(ctx, "qemu-img", "convert", "-O", "qcow2",
			srcPath, dstPath).CombinedOutput()
		if err != nil {
			// Clean up any already copied disks.
			for _, p := range newDiskPaths {
				os.Remove(p)
			}
			jsonError(w, http.StatusInternalServerError,
				fmt.Sprintf("failed to copy disk %s: %s", diskName, strings.TrimSpace(string(copyOut))))
			return
		}
		newDiskPaths = append(newDiskPaths, dstPath)

		// Update disk path in XML.
		oldPath := filepath.Join(templateDir, diskName)
		xmlStr = strings.ReplaceAll(xmlStr, oldPath, dstPath)
		// Also try replacing original source paths.
		xmlStr = strings.ReplaceAll(xmlStr, "file='"+filepath.Join(templateDir, diskName)+"'",
			"file='"+dstPath+"'")
	}

	// Apply vCPU override.
	if req.VCPUs > 0 {
		vcpuStr := fmt.Sprintf("%d", req.VCPUs)
		vcpuOpenRe := strings.Index(xmlStr, "<vcpu")
		vcpuClose := strings.Index(xmlStr, "</vcpu>")
		if vcpuOpenRe >= 0 && vcpuClose >= 0 {
			// Find the > that ends the vcpu opening tag.
			vcpuTagEnd := strings.Index(xmlStr[vcpuOpenRe:], ">")
			if vcpuTagEnd >= 0 {
				xmlStr = xmlStr[:vcpuOpenRe+vcpuTagEnd+1] + vcpuStr + xmlStr[vcpuClose:]
			}
		}
	}

	// Apply memory override.
	if req.MemoryMB > 0 {
		memKiB := fmt.Sprintf("%d", req.MemoryMB*1024)
		// Replace <memory unit='KiB'>VALUE</memory>.
		memOpen := strings.Index(xmlStr, "<memory")
		memClose := strings.Index(xmlStr, "</memory>")
		if memOpen >= 0 && memClose >= 0 {
			xmlStr = xmlStr[:memOpen] + fmt.Sprintf("<memory unit='KiB'>%s", memKiB) + xmlStr[memClose:]
		}
		// Also replace currentMemory.
		curMemOpen := strings.Index(xmlStr, "<currentMemory")
		curMemClose := strings.Index(xmlStr, "</currentMemory>")
		if curMemOpen >= 0 && curMemClose >= 0 {
			xmlStr = xmlStr[:curMemOpen] + fmt.Sprintf("<currentMemory unit='KiB'>%s", memKiB) + xmlStr[curMemClose:]
		}
	}

	// Validate the modified XML is well-formed before defining.
	if err := xml.Unmarshal([]byte(xmlStr), &struct{ XMLName xml.Name }{}); err != nil {
		for _, p := range newDiskPaths {
			os.Remove(p)
		}
		jsonError(w, http.StatusInternalServerError, "XML corruption during template deployment")
		return
	}

	// Verify that new disk paths actually exist on disk.
	for _, p := range newDiskPaths {
		if _, err := os.Stat(p); os.IsNotExist(err) {
			for _, cleanup := range newDiskPaths {
				os.Remove(cleanup)
			}
			jsonError(w, http.StatusInternalServerError, "disk copy verification failed")
			return
		}
	}

	// Write modified XML and define the VM.
	tmpFile, err := os.CreateTemp("", "h2kweb-tpl-deploy-*.xml")
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
		// Clean up copied disks on failure.
		for _, p := range newDiskPaths {
			os.Remove(p)
		}
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh define failed: %s", strings.TrimSpace(string(defineOut))))
		return
	}

	log.Printf("[templates] deployTemplate template=%s vm=%s succeeded", safeTpl, safeVM)
	s.auditLog(r, "template_deploy", safeTpl, fmt.Sprintf("vm=%s", safeVM))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":  fmt.Sprintf("VM %s deployed from template %s", safeVM, safeTpl),
		"vm_name":  safeVM,
		"template": safeTpl,
		"disks":    len(newDiskPaths),
	})
}

// handleDeleteTemplate removes a template and its disk copies.
//
// DELETE /api/v1/templates/{name}
func (s *Server) handleDeleteTemplate(w http.ResponseWriter, r *http.Request) {
	tplName := chi.URLParam(r, "name")
	safeTpl := safeNameRe.ReplaceAllString(tplName, "")
	if safeTpl == "" || safeTpl != tplName {
		jsonError(w, http.StatusBadRequest, "invalid template name")
		return
	}

	templateDir := filepath.Join(templateBaseDir, safeTpl)
	if _, err := os.Stat(templateDir); os.IsNotExist(err) {
		jsonError(w, http.StatusNotFound, "template not found")
		return
	}

	log.Printf("[templates] deleteTemplate name=%s from %s", safeTpl, r.RemoteAddr)

	if err := os.RemoveAll(templateDir); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to remove template: %v", err))
		return
	}

	log.Printf("[templates] deleteTemplate name=%s succeeded", safeTpl)
	s.auditLog(r, "template_delete", safeTpl)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Template %s deleted", safeTpl),
	})
}
