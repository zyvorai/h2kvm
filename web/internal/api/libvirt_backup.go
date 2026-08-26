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

const backupBaseDir = "/var/lib/libvirt/backups"

// backupMeta stores metadata about a VM backup.
type backupMeta struct {
	ID        string   `json:"id"`
	VMName    string   `json:"vm_name"`
	CreatedAt string   `json:"created_at"`
	Disks     []string `json:"disks"`
	XMLFile   string   `json:"xml_file"`
	Compressed bool   `json:"compressed"`
	SizeMB    int64    `json:"size_mb"`
}

// handleListBackups lists all available VM backups.
//
// GET /api/v1/backups
func (s *Server) handleListBackups(w http.ResponseWriter, r *http.Request) {
	entries, err := os.ReadDir(backupBaseDir)
	if err != nil {
		// Directory doesn't exist yet -- return empty list.
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}

	var backups []backupMeta
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		metaPath := filepath.Join(backupBaseDir, entry.Name(), "backup.json")
		data, err := os.ReadFile(metaPath)
		if err != nil {
			continue
		}
		var meta backupMeta
		if err := json.Unmarshal(data, &meta); err != nil {
			continue
		}
		backups = append(backups, meta)
	}

	log.Printf("[backup] listBackups count=%d from %s", len(backups), r.RemoteAddr)
	jsonResponse(w, http.StatusOK, backups)
}

// handleCreateBackup creates a full backup of a VM (XML + disk images).
//
// POST /api/v1/backups
// Body: {"vm_name": "myvm", "compress": true}
func (s *Server) handleCreateBackup(w http.ResponseWriter, r *http.Request) {
	var req struct {
		VMName   string `json:"vm_name"`
		Compress bool   `json:"compress"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	safeName := safeNameRe.ReplaceAllString(req.VMName, "")
	if safeName == "" || safeName != req.VMName {
		jsonError(w, http.StatusBadRequest, "invalid vm_name")
		return
	}

	log.Printf("[backup] createBackup vm=%s compress=%v from %s", safeName, req.Compress, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()

	// Dump domain XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "dumpxml", safeName, "--inactive").Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "VM not found")
		return
	}

	// Parse XML to find disk paths.
	type xmlDiskSource struct {
		File string `xml:"file,attr"`
	}
	type xmlDisk struct {
		Device string        `xml:"device,attr"`
		Source xmlDiskSource `xml:"source"`
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

	// Create backup directory.
	timestamp := time.Now().Format("20060102-150405")
	backupID := fmt.Sprintf("%s-%s", safeName, timestamp)
	backupDir := filepath.Join(backupBaseDir, backupID)

	if err := os.MkdirAll(backupDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to create backup directory: %v", err))
		return
	}

	// Save domain XML.
	xmlPath := filepath.Join(backupDir, "domain.xml")
	if err := os.WriteFile(xmlPath, xmlOut, 0644); err != nil {
		os.RemoveAll(backupDir)
		jsonError(w, http.StatusInternalServerError, "failed to save domain XML")
		return
	}

	// Copy disk images.
	var diskNames []string
	var totalSize int64
	var copyErrors []string

	for _, d := range dom.Devices.Disks {
		if d.Device != "disk" || d.Source.File == "" {
			continue
		}
		srcPath := d.Source.File
		dstName := filepath.Base(srcPath)
		dstPath := filepath.Join(backupDir, dstName)

		var copyArgs []string
		if req.Compress {
			copyArgs = []string{"convert", "-O", "qcow2", "-c", srcPath, dstPath}
		} else {
			copyArgs = []string{"convert", "-O", "qcow2", srcPath, dstPath}
		}

		copyOut, err := exec.CommandContext(ctx, "qemu-img", copyArgs...).CombinedOutput()
		if err != nil {
			copyErrors = append(copyErrors, fmt.Sprintf("%s: %s", srcPath, strings.TrimSpace(string(copyOut))))
			continue
		}

		// Get backup file size.
		if info, err := os.Stat(dstPath); err == nil {
			totalSize += info.Size() / (1024 * 1024)
		}
		diskNames = append(diskNames, dstName)
	}

	if len(copyErrors) > 0 && len(diskNames) == 0 {
		os.RemoveAll(backupDir)
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to backup disks: %s", strings.Join(copyErrors, "; ")))
		return
	}

	// Save backup metadata.
	meta := backupMeta{
		ID:         backupID,
		VMName:     safeName,
		CreatedAt:  time.Now().Format(time.RFC3339),
		Disks:      diskNames,
		XMLFile:    "domain.xml",
		Compressed: req.Compress,
		SizeMB:     totalSize,
	}

	metaData, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		os.RemoveAll(backupDir)
		jsonError(w, http.StatusInternalServerError, "failed to marshal backup metadata")
		return
	}

	metaPath := filepath.Join(backupDir, "backup.json")
	if err := os.WriteFile(metaPath, metaData, 0644); err != nil {
		os.RemoveAll(backupDir)
		jsonError(w, http.StatusInternalServerError, "failed to save backup metadata")
		return
	}

	log.Printf("[backup] createBackup id=%s vm=%s disks=%d size=%dMB succeeded",
		backupID, safeName, len(diskNames), totalSize)
	s.auditLog(r, "backup_create", safeName, fmt.Sprintf("id=%s disks=%d size=%dMB", backupID, len(diskNames), totalSize))

	resp := map[string]interface{}{
		"message":    fmt.Sprintf("Backup %s created", backupID),
		"id":         backupID,
		"vm_name":    safeName,
		"disks":      len(diskNames),
		"size_mb":    totalSize,
		"compressed": req.Compress,
	}
	if len(copyErrors) > 0 {
		resp["warnings"] = copyErrors
	}
	jsonResponse(w, http.StatusOK, resp)
}

// handleRestoreBackup restores a VM from a backup.
//
// POST /api/v1/backups/{id}/restore
// Body: {"new_name": "restored-vm"} (optional)
func (s *Server) handleRestoreBackup(w http.ResponseWriter, r *http.Request) {
	backupID := chi.URLParam(r, "id")
	safeID := safeNameRe.ReplaceAllString(backupID, "")
	if safeID == "" || safeID != backupID {
		jsonError(w, http.StatusBadRequest, "invalid backup ID")
		return
	}

	var req struct {
		NewName string `json:"new_name"`
	}
	// Body is optional -- ignore read errors.
	readJSON(r, &req)

	backupDir := filepath.Join(backupBaseDir, safeID)

	// Load backup metadata.
	metaPath := filepath.Join(backupDir, "backup.json")
	metaData, err := os.ReadFile(metaPath)
	if err != nil {
		jsonError(w, http.StatusNotFound, "backup not found")
		return
	}

	var meta backupMeta
	if err := json.Unmarshal(metaData, &meta); err != nil {
		jsonError(w, http.StatusInternalServerError, "corrupt backup metadata")
		return
	}

	vmName := meta.VMName
	if req.NewName != "" {
		safeNew := safeNameRe.ReplaceAllString(req.NewName, "")
		if safeNew == "" || safeNew != req.NewName {
			jsonError(w, http.StatusBadRequest, "invalid new_name")
			return
		}
		vmName = safeNew
	}

	log.Printf("[backup] restoreBackup id=%s vm=%s from %s", safeID, vmName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()

	// Load domain XML.
	xmlPath := filepath.Join(backupDir, meta.XMLFile)
	xmlData, err := os.ReadFile(xmlPath)
	if err != nil {
		jsonError(w, http.StatusInternalServerError, "backup domain.xml missing")
		return
	}

	xmlStr := string(xmlData)

	// Update VM name if restoring with a different name.
	if vmName != meta.VMName {
		xmlStr = strings.Replace(xmlStr, "<name>"+meta.VMName+"</name>", "<name>"+vmName+"</name>", 1)
		// Remove UUID so libvirt generates a new one.
		uuidStart := strings.Index(xmlStr, "<uuid>")
		uuidEnd := strings.Index(xmlStr, "</uuid>")
		if uuidStart >= 0 && uuidEnd >= 0 {
			xmlStr = xmlStr[:uuidStart] + xmlStr[uuidEnd+len("</uuid>"):]
		}
	}

	// Copy disks back to /var/lib/libvirt/images/.
	imgDir := "/var/lib/libvirt/images"
	var restoredDisks []string
	for _, diskName := range meta.Disks {
		srcPath := filepath.Join(backupDir, diskName)
		dstName := diskName
		if vmName != meta.VMName {
			dstName = vmName + "-" + diskName
		}
		dstPath := filepath.Join(imgDir, dstName)

		copyOut, err := exec.CommandContext(ctx, "qemu-img", "convert", "-O", "qcow2",
			srcPath, dstPath).CombinedOutput()
		if err != nil {
			// Clean up already restored disks.
			for _, p := range restoredDisks {
				os.Remove(p)
			}
			log.Printf("[backup] restore disk %s failed: %s", diskName, strings.TrimSpace(string(copyOut)))
			jsonError(w, http.StatusInternalServerError, "failed to restore disk")
			return
		}
		restoredDisks = append(restoredDisks, dstPath)

		// Update disk path in XML.
		oldPath := filepath.Join(backupDir, diskName)
		xmlStr = strings.ReplaceAll(xmlStr, oldPath, dstPath)
		// Also try updating original paths that were in the backup.
		if vmName != meta.VMName {
			origPath := filepath.Join(imgDir, diskName)
			xmlStr = strings.ReplaceAll(xmlStr, origPath, dstPath)
		}
	}

	// Write modified XML and define the VM.
	tmpFile, err := os.CreateTemp("", "h2kweb-restore-*.xml")
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
		// Clean up restored disks on failure.
		for _, p := range restoredDisks {
			os.Remove(p)
		}
		log.Printf("[backup] virsh define failed for restore %s: %s", safeID, strings.TrimSpace(string(defineOut)))
		jsonError(w, http.StatusInternalServerError, "failed to define restored VM")
		return
	}

	log.Printf("[backup] restoreBackup id=%s vm=%s disks=%d succeeded", safeID, vmName, len(restoredDisks))
	s.auditLog(r, "backup_restore", safeID, fmt.Sprintf("vm=%s disks=%d", vmName, len(restoredDisks)))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("VM %s restored from backup %s", vmName, safeID),
		"vm_name": vmName,
		"backup":  safeID,
		"disks":   len(restoredDisks),
	})
}

// handleDeleteBackup removes a backup and all its disk copies.
//
// DELETE /api/v1/backups/{id}
func (s *Server) handleDeleteBackup(w http.ResponseWriter, r *http.Request) {
	backupID := chi.URLParam(r, "id")
	safeID := safeNameRe.ReplaceAllString(backupID, "")
	if safeID == "" || safeID != backupID {
		jsonError(w, http.StatusBadRequest, "invalid backup ID")
		return
	}

	backupDir := filepath.Join(backupBaseDir, safeID)
	if _, err := os.Stat(backupDir); os.IsNotExist(err) {
		jsonError(w, http.StatusNotFound, "backup not found")
		return
	}

	log.Printf("[backup] deleteBackup id=%s from %s", safeID, r.RemoteAddr)

	if err := os.RemoveAll(backupDir); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to remove backup: %v", err))
		return
	}

	log.Printf("[backup] deleteBackup id=%s succeeded", safeID)
	s.auditLog(r, "backup_delete", safeID)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Backup %s deleted", safeID),
	})
}

// handleVerifyBackup verifies the integrity of disk images in a backup.
//
// POST /api/v1/backups/{id}/verify
func (s *Server) handleVerifyBackup(w http.ResponseWriter, r *http.Request) {
	backupID := chi.URLParam(r, "id")
	safeID := safeNameRe.ReplaceAllString(backupID, "")
	if safeID == "" || safeID != backupID {
		jsonError(w, http.StatusBadRequest, "invalid backup ID")
		return
	}

	backupDir := filepath.Join(backupBaseDir, safeID)

	// Load backup metadata.
	metaPath := filepath.Join(backupDir, "backup.json")
	metaData, err := os.ReadFile(metaPath)
	if err != nil {
		jsonError(w, http.StatusNotFound, "backup not found")
		return
	}

	var meta backupMeta
	if err := json.Unmarshal(metaData, &meta); err != nil {
		jsonError(w, http.StatusInternalServerError, "corrupt backup metadata")
		return
	}

	log.Printf("[backup] verifyBackup id=%s from %s", safeID, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	type diskCheck struct {
		Name    string `json:"name"`
		Status  string `json:"status"`
		Details string `json:"details,omitempty"`
	}

	var checks []diskCheck
	allOK := true

	for _, diskName := range meta.Disks {
		diskPath := filepath.Join(backupDir, diskName)

		out, err := exec.CommandContext(ctx, "qemu-img", "check", diskPath).CombinedOutput()
		outStr := strings.TrimSpace(string(out))

		if err != nil {
			checks = append(checks, diskCheck{
				Name:    diskName,
				Status:  "error",
				Details: outStr,
			})
			allOK = false
		} else {
			checks = append(checks, diskCheck{
				Name:    diskName,
				Status:  "ok",
				Details: outStr,
			})
		}
	}

	// Also verify domain.xml exists.
	xmlPath := filepath.Join(backupDir, meta.XMLFile)
	xmlStatus := "ok"
	if _, err := os.Stat(xmlPath); os.IsNotExist(err) {
		xmlStatus = "missing"
		allOK = false
	}

	log.Printf("[backup] verifyBackup id=%s result=%v", safeID, allOK)

	status := "healthy"
	if !allOK {
		status = "degraded"
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"id":         safeID,
		"status":     status,
		"xml_status": xmlStatus,
		"disks":      checks,
	})
}
