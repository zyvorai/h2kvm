// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
)

// handleListKubeconfigs returns all registered kubeconfigs with live
// connection status for each cluster. Connection checks run in parallel
// with a 3-second timeout.
func (s *Server) handleListKubeconfigs(w http.ResponseWriter, r *http.Request) {
	cfg := s.kubeconfigMgr.List()

	type clusterStatus struct {
		ClusterEntry
		Connected bool   `json:"connected"`
		Version   string `json:"version,omitempty"`
		ServerURL string `json:"server_url,omitempty"`
		IsActive  bool   `json:"is_active"`
	}

	results := make([]clusterStatus, len(cfg.Clusters))

	var wg sync.WaitGroup
	for i, c := range cfg.Clusters {
		wg.Add(1)
		go func(idx int, entry ClusterEntry) {
			defer wg.Done()

			done := make(chan struct{})
			var connected bool
			var version, server string

			go func() {
				connected, version, server = s.kubeconfigMgr.CheckConnection(entry.ID)
				close(done)
			}()

			select {
			case <-done:
			case <-time.After(3 * time.Second):
			}

			results[idx] = clusterStatus{
				ClusterEntry: entry,
				Connected:    connected,
				Version:      version,
				ServerURL:    server,
				IsActive:     entry.ID == cfg.Active,
			}
		}(i, c)
	}
	wg.Wait()

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"active":   cfg.Active,
		"clusters": results,
	})
}

// handleAddKubeconfig adds a new kubeconfig via file upload (multipart)
// or by referencing a server-side path (JSON body).
func (s *Server) handleAddKubeconfig(w http.ResponseWriter, r *http.Request) {
	ct := r.Header.Get("Content-Type")

	var name, source, originalPath string
	var data []byte

	switch {
	case strings.HasPrefix(ct, "multipart/form-data"):
		if err := r.ParseMultipartForm(10 << 20); err != nil { // 10 MB max
			jsonError(w, http.StatusBadRequest, "failed to parse multipart form: "+err.Error())
			return
		}

		name = strings.TrimSpace(r.FormValue("name"))
		if name == "" {
			jsonError(w, http.StatusBadRequest, "name is required")
			return
		}

		file, header, err := r.FormFile("kubeconfig")
		if err != nil {
			jsonError(w, http.StatusBadRequest, "kubeconfig file is required")
			return
		}
		defer file.Close()

		data, err = io.ReadAll(file)
		if err != nil {
			jsonError(w, http.StatusInternalServerError, "failed to read uploaded file")
			return
		}

		source = "upload"
		originalPath = header.Filename

	case strings.HasPrefix(ct, "application/json"):
		var req struct {
			Name string `json:"name"`
			Path string `json:"path"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			jsonError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
			return
		}

		name = strings.TrimSpace(req.Name)
		if name == "" {
			jsonError(w, http.StatusBadRequest, "name is required")
			return
		}

		reqPath := strings.TrimSpace(req.Path)
		if reqPath == "" {
			jsonError(w, http.StatusBadRequest, "path is required")
			return
		}

		// Reject path traversal.
		if strings.Contains(reqPath, "..") {
			jsonError(w, http.StatusBadRequest, "path must not contain '..'")
			return
		}

		absPath, err := filepath.Abs(reqPath)
		if err != nil {
			jsonError(w, http.StatusBadRequest, "invalid path")
			return
		}

		var readErr error
		data, readErr = os.ReadFile(absPath)
		if readErr != nil {
			jsonError(w, http.StatusBadRequest, fmt.Sprintf("cannot read file %s: %v", absPath, readErr))
			return
		}

		source = "path"
		originalPath = absPath

	default:
		jsonError(w, http.StatusUnsupportedMediaType,
			"Content-Type must be multipart/form-data or application/json")
		return
	}

	entry, err := s.kubeconfigMgr.Add(name, source, data, originalPath)
	if err != nil {
		jsonError(w, http.StatusConflict, err.Error())
		return
	}

	s.auditLog(r, "kubeconfig_add", entry.ID)
	log.Printf("[kubeconfig] added cluster %q (source=%s)", entry.ID, source)

	jsonResponse(w, http.StatusCreated, entry)
}

// handleActivateKubeconfig sets a cluster as the active kubeconfig.
func (s *Server) handleActivateKubeconfig(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		jsonError(w, http.StatusBadRequest, "cluster id is required")
		return
	}

	if err := s.kubeconfigMgr.Activate(id); err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	s.auditLog(r, "kubeconfig_activate", id)
	log.Printf("[kubeconfig] activated cluster %q", id)

	jsonResponse(w, http.StatusOK, map[string]string{
		"status": "activated",
		"active": id,
	})
}

// handleDeleteKubeconfig removes a cluster and its kubeconfig file.
func (s *Server) handleDeleteKubeconfig(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		jsonError(w, http.StatusBadRequest, "cluster id is required")
		return
	}

	if err := s.kubeconfigMgr.Delete(id); err != nil {
		jsonError(w, http.StatusNotFound, err.Error())
		return
	}

	s.auditLog(r, "kubeconfig_delete", id)
	log.Printf("[kubeconfig] deleted cluster %q", id)

	jsonResponse(w, http.StatusOK, map[string]string{
		"status":  "deleted",
		"cluster": id,
	})
}
