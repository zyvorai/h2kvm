// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

const isoBaseDir = "/var/lib/libvirt/images"

// --- ISO Management ---

// handleListISOs lists all ISO files in the ISO directory.
//
// GET /api/v1/isos
func (s *Server) handleListISOs(w http.ResponseWriter, r *http.Request) {
	entries, err := os.ReadDir(isoBaseDir)
	if err != nil {
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}

	type isoInfo struct {
		Name     string `json:"name"`
		SizeMB   int64  `json:"size_mb"`
		Modified string `json:"modified"`
	}

	var isos []isoInfo
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		if !strings.HasSuffix(strings.ToLower(entry.Name()), ".iso") {
			continue
		}

		info, err := entry.Info()
		if err != nil {
			continue
		}

		isos = append(isos, isoInfo{
			Name:     entry.Name(),
			SizeMB:   info.Size() / (1024 * 1024),
			Modified: info.ModTime().Format(time.RFC3339),
		})
	}

	log.Printf("[iso] listISOs count=%d from %s", len(isos), r.RemoteAddr)
	jsonResponse(w, http.StatusOK, isos)
}

// handleUploadISO handles multipart form upload of an ISO file.
//
// POST /api/v1/isos/upload
// Content-Type: multipart/form-data
// Form field: "file" (the ISO file)
func (s *Server) handleUploadISO(w http.ResponseWriter, r *http.Request) {
	// Limit to 10GB.
	r.Body = http.MaxBytesReader(w, r.Body, 10*1024*1024*1024)

	if err := r.ParseMultipartForm(32 << 20); err != nil {
		jsonError(w, http.StatusBadRequest, fmt.Sprintf("failed to parse multipart form: %v", err))
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		jsonError(w, http.StatusBadRequest, "file field is required")
		return
	}
	defer file.Close()

	fileName := filepath.Base(header.Filename)

	// Validate filename.
	if !strings.HasSuffix(strings.ToLower(fileName), ".iso") {
		jsonError(w, http.StatusBadRequest, "file must have .iso extension")
		return
	}

	safeName := safeNameRe.ReplaceAllString(fileName, "")
	if safeName == "" || safeName != fileName {
		jsonError(w, http.StatusBadRequest, "invalid filename: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	dstPath := filepath.Join(isoBaseDir, safeName)

	// Validate resolved path stays within the base directory (path traversal protection).
	absPath, _ := filepath.Abs(dstPath)
	absBase, _ := filepath.Abs(isoBaseDir)
	if !strings.HasPrefix(absPath, absBase+string(filepath.Separator)) && absPath != absBase {
		jsonError(w, http.StatusBadRequest, "invalid file path")
		return
	}

	// Check if file already exists.
	if _, err := os.Stat(dstPath); err == nil {
		jsonError(w, http.StatusConflict, fmt.Sprintf("ISO %s already exists", safeName))
		return
	}

	log.Printf("[iso] uploadISO name=%s size=%d from %s", safeName, header.Size, r.RemoteAddr)

	// Ensure directory exists.
	if err := os.MkdirAll(isoBaseDir, 0755); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to create ISO directory: %v", err))
		return
	}

	// Create destination file.
	dst, err := os.Create(dstPath)
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to create file: %v", err))
		return
	}
	defer dst.Close()

	written, err := io.Copy(dst, file)
	if err != nil {
		os.Remove(dstPath)
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to save ISO: %v", err))
		return
	}

	log.Printf("[iso] uploadISO name=%s bytes=%d succeeded", safeName, written)
	s.auditLog(r, "iso_upload", safeName, fmt.Sprintf("size=%dMB", written/(1024*1024)))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("ISO %s uploaded", safeName),
		"name":    safeName,
		"size_mb": written / (1024 * 1024),
		"path":    dstPath,
	})
}

// handleDeleteISO removes an ISO file.
//
// DELETE /api/v1/isos/{name}
func (s *Server) handleDeleteISO(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "name")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid ISO name")
		return
	}

	if !strings.HasSuffix(strings.ToLower(safeName), ".iso") {
		jsonError(w, http.StatusBadRequest, "name must have .iso extension")
		return
	}

	isoPath := filepath.Join(isoBaseDir, safeName)

	// Validate resolved path stays within the base directory (path traversal protection).
	absISOPath, _ := filepath.Abs(isoPath)
	absISOBase, _ := filepath.Abs(isoBaseDir)
	if !strings.HasPrefix(absISOPath, absISOBase+string(filepath.Separator)) && absISOPath != absISOBase {
		jsonError(w, http.StatusBadRequest, "invalid file path")
		return
	}

	if _, err := os.Stat(isoPath); os.IsNotExist(err) {
		jsonError(w, http.StatusNotFound, "ISO not found")
		return
	}

	log.Printf("[iso] deleteISO name=%s from %s", safeName, r.RemoteAddr)

	if err := os.Remove(isoPath); err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to delete ISO: %v", err))
		return
	}

	log.Printf("[iso] deleteISO name=%s succeeded", safeName)
	s.auditLog(r, "iso_delete", safeName)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("ISO %s deleted", safeName),
	})
}
