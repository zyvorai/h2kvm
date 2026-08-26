// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

// --- Storage Pool Management ---

// handleListPools returns all storage pools with details.
//
// GET /api/v1/pools
func (s *Server) handleListPools(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "pool-list", "--all", "--details").Output()
	if err != nil {
		jsonResponse(w, http.StatusOK, []interface{}{})
		return
	}

	type poolInfo struct {
		Name       string `json:"name"`
		State      string `json:"state"`
		Autostart  string `json:"autostart"`
		Persistent string `json:"persistent"`
		Capacity   string `json:"capacity"`
		Allocation string `json:"allocation"`
		Available  string `json:"available"`
	}

	var pools []poolInfo
	lines := strings.Split(string(out), "\n")
	// Skip header lines (first 2 lines are header + separator).
	for _, line := range lines {
		if line == "" || strings.HasPrefix(line, " Name") || strings.HasPrefix(line, "---") || strings.HasPrefix(line, " ") && strings.Contains(line, "Name") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}

		p := poolInfo{
			Name:  fields[0],
			State: fields[1],
		}
		if len(fields) >= 3 {
			p.Autostart = fields[2]
		}
		if len(fields) >= 4 {
			p.Persistent = fields[3]
		}
		if len(fields) >= 5 {
			p.Capacity = fields[4]
		}
		if len(fields) >= 6 {
			p.Allocation = fields[5]
		}
		if len(fields) >= 7 {
			p.Available = fields[6]
		}
		pools = append(pools, p)
	}

	log.Printf("[storage] listPools count=%d from %s", len(pools), r.RemoteAddr)
	jsonResponse(w, http.StatusOK, pools)
}

// handleGetPool returns details about a specific storage pool.
//
// GET /api/v1/pools/{poolName}
func (s *Server) handleGetPool(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "poolName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	infoOut, err := exec.CommandContext(ctx, "virsh", "pool-info", safeName).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "pool not found")
		return
	}

	// Parse pool-info output (key: value lines).
	info := map[string]string{}
	for _, line := range strings.Split(string(infoOut), "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) == 2 {
			info[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
		}
	}

	// Get pool XML.
	xmlOut, err := exec.CommandContext(ctx, "virsh", "pool-dumpxml", safeName).Output()
	if err != nil {
		xmlOut = []byte{}
	}

	log.Printf("[storage] getPool pool=%s from %s", safeName, r.RemoteAddr)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"name":       safeName,
		"info":       info,
		"xml":        string(xmlOut),
	})
}

// handleCreatePool creates a new storage pool.
//
// POST /api/v1/pools
// Body: {"name": "mypool", "path": "/var/lib/libvirt/images/mypool", "type": "dir"}
func (s *Server) handleCreatePool(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name string `json:"name"`
		Path string `json:"path"`
		Type string `json:"type"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid pool name: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	if req.Path == "" {
		jsonError(w, http.StatusBadRequest, "path is required")
		return
	}
	if strings.Contains(req.Path, "..") {
		jsonError(w, http.StatusBadRequest, "path must not contain '..'")
		return
	}

	poolType := req.Type
	if poolType == "" {
		poolType = "dir"
	}
	validTypes := map[string]bool{"dir": true, "logical": true, "netfs": true}
	if !validTypes[poolType] {
		jsonError(w, http.StatusBadRequest, "type must be one of: dir, logical, netfs")
		return
	}

	log.Printf("[storage] createPool name=%s type=%s path=%s from %s", safeName, poolType, req.Path, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Define the pool.
	defineOut, err := exec.CommandContext(ctx, "virsh", "pool-define-as", safeName, poolType, "--target", req.Path).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh pool-define-as failed: %s", strings.TrimSpace(string(defineOut))))
		return
	}

	// Build the pool.
	buildOut, err := exec.CommandContext(ctx, "virsh", "pool-build", safeName).CombinedOutput()
	if err != nil {
		log.Printf("[storage] pool-build warning: %s", strings.TrimSpace(string(buildOut)))
		// Not fatal -- pool-build may fail for logical pools.
	}

	// Start the pool.
	startOut, err := exec.CommandContext(ctx, "virsh", "pool-start", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh pool-start failed: %s", strings.TrimSpace(string(startOut))))
		return
	}

	// Enable autostart.
	autostartOut, err := exec.CommandContext(ctx, "virsh", "pool-autostart", safeName).CombinedOutput()
	if err != nil {
		log.Printf("[storage] pool-autostart warning: %s", strings.TrimSpace(string(autostartOut)))
	}

	log.Printf("[storage] createPool name=%s succeeded", safeName)
	s.auditLog(r, "pool_create", safeName, fmt.Sprintf("type=%s path=%s", poolType, req.Path))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Pool %s created and started", safeName),
		"name":    safeName,
		"type":    poolType,
		"path":    req.Path,
	})
}

// handleDeletePool destroys and undefines a storage pool.
//
// DELETE /api/v1/pools/{poolName}
func (s *Server) handleDeletePool(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "poolName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	log.Printf("[storage] deletePool pool=%s from %s", safeName, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	// Destroy (stop) the pool first.
	destroyOut, err := exec.CommandContext(ctx, "virsh", "pool-destroy", safeName).CombinedOutput()
	if err != nil {
		log.Printf("[storage] pool-destroy warning: %s", strings.TrimSpace(string(destroyOut)))
		// Not fatal -- pool might already be stopped.
	}

	// Undefine the pool.
	undefOut, err := exec.CommandContext(ctx, "virsh", "pool-undefine", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh pool-undefine failed: %s", strings.TrimSpace(string(undefOut))))
		return
	}

	log.Printf("[storage] deletePool pool=%s succeeded", safeName)
	s.auditLog(r, "pool_delete", safeName)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Pool %s deleted", safeName),
	})
}

// handleStartPool starts a stopped storage pool.
//
// POST /api/v1/pools/{poolName}/start
func (s *Server) handleStartPool(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "poolName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "pool-start", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh pool-start failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[storage] startPool pool=%s succeeded", safeName)
	s.auditLog(r, "pool_start", safeName)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Pool %s started", safeName),
	})
}

// handleStopPool stops a running storage pool.
//
// POST /api/v1/pools/{poolName}/stop
func (s *Server) handleStopPool(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "poolName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "pool-destroy", safeName).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh pool-destroy failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[storage] stopPool pool=%s succeeded", safeName)
	s.auditLog(r, "pool_stop", safeName)

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Pool %s stopped", safeName),
	})
}

// handleListPoolVolumes lists all volumes in a storage pool.
//
// GET /api/v1/pools/{poolName}/volumes
func (s *Server) handleListPoolVolumes(w http.ResponseWriter, r *http.Request) {
	name := chi.URLParam(r, "poolName")
	safeName := safeNameRe.ReplaceAllString(name, "")
	if safeName == "" || safeName != name {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "vol-list", "--pool", safeName, "--details").Output()
	if err != nil {
		jsonError(w, http.StatusNotFound,
			fmt.Sprintf("pool not found or not active: %s", strings.TrimSpace(string(out))))
		return
	}

	type volInfo struct {
		Name     string `json:"name"`
		Path     string `json:"path"`
		Type     string `json:"type"`
		Capacity string `json:"capacity"`
		Allocation string `json:"allocation"`
	}

	var volumes []volInfo
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		if line == "" || strings.HasPrefix(line, " Name") || strings.HasPrefix(line, "---") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}

		v := volInfo{
			Name: fields[0],
			Path: fields[1],
		}
		if len(fields) >= 3 {
			v.Type = fields[2]
		}
		if len(fields) >= 4 {
			v.Capacity = fields[3]
		}
		if len(fields) >= 5 {
			v.Allocation = fields[4]
		}
		volumes = append(volumes, v)
	}

	log.Printf("[storage] listPoolVolumes pool=%s count=%d from %s", safeName, len(volumes), r.RemoteAddr)
	jsonResponse(w, http.StatusOK, volumes)
}

// handleCreateVolume creates a new volume in a storage pool.
//
// POST /api/v1/pools/{poolName}/volumes
// Body: {"name": "disk.qcow2", "capacity_gb": 20, "format": "qcow2"}
func (s *Server) handleCreateVolume(w http.ResponseWriter, r *http.Request) {
	poolName := chi.URLParam(r, "poolName")
	safePool := safeNameRe.ReplaceAllString(poolName, "")
	if safePool == "" || safePool != poolName {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	var req struct {
		Name       string `json:"name"`
		CapacityGB int    `json:"capacity_gb"`
		Format     string `json:"format"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	safeName := safeNameRe.ReplaceAllString(req.Name, "")
	if safeName == "" || safeName != req.Name {
		jsonError(w, http.StatusBadRequest, "invalid volume name: only alphanumeric, dash, underscore, dot allowed")
		return
	}

	if req.CapacityGB <= 0 || req.CapacityGB > 10240 {
		jsonError(w, http.StatusBadRequest, "capacity_gb must be between 1 and 10240")
		return
	}

	format := req.Format
	if format == "" {
		format = "qcow2"
	}
	validFormats := map[string]bool{"qcow2": true, "raw": true}
	if !validFormats[format] {
		jsonError(w, http.StatusBadRequest, "format must be 'qcow2' or 'raw'")
		return
	}

	log.Printf("[storage] createVolume pool=%s name=%s capacity=%dGB format=%s from %s",
		safePool, safeName, req.CapacityGB, format, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	capacityStr := fmt.Sprintf("%dG", req.CapacityGB)
	out, err := exec.CommandContext(ctx, "virsh", "vol-create-as", safePool, safeName,
		capacityStr, "--format", format).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh vol-create-as failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[storage] createVolume pool=%s name=%s succeeded", safePool, safeName)
	s.auditLog(r, "vol_create", safeName, fmt.Sprintf("pool=%s capacity=%dGB format=%s", safePool, req.CapacityGB, format))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":     fmt.Sprintf("Volume %s created in pool %s", safeName, safePool),
		"name":        safeName,
		"pool":        safePool,
		"capacity_gb": req.CapacityGB,
		"format":      format,
	})
}

// handleDeleteVolume deletes a volume from a storage pool.
//
// DELETE /api/v1/pools/{poolName}/volumes/{volName}
func (s *Server) handleDeleteVolume(w http.ResponseWriter, r *http.Request) {
	poolName := chi.URLParam(r, "poolName")
	safePool := safeNameRe.ReplaceAllString(poolName, "")
	if safePool == "" || safePool != poolName {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	volName := chi.URLParam(r, "volName")
	safeVol := safeNameRe.ReplaceAllString(volName, "")
	if safeVol == "" || safeVol != volName {
		jsonError(w, http.StatusBadRequest, "invalid volume name")
		return
	}

	log.Printf("[storage] deleteVolume pool=%s vol=%s from %s", safePool, safeVol, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "virsh", "vol-delete", safeVol, "--pool", safePool).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh vol-delete failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[storage] deleteVolume pool=%s vol=%s succeeded", safePool, safeVol)
	s.auditLog(r, "vol_delete", safeVol, fmt.Sprintf("pool=%s", safePool))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": fmt.Sprintf("Volume %s deleted from pool %s", safeVol, safePool),
	})
}

// handleResizeVolume resizes a volume in a storage pool.
//
// POST /api/v1/pools/{poolName}/volumes/{volName}/resize
// Body: {"capacity_gb": 40}
func (s *Server) handleResizeVolume(w http.ResponseWriter, r *http.Request) {
	poolName := chi.URLParam(r, "poolName")
	safePool := safeNameRe.ReplaceAllString(poolName, "")
	if safePool == "" || safePool != poolName {
		jsonError(w, http.StatusBadRequest, "invalid pool name")
		return
	}

	volName := chi.URLParam(r, "volName")
	safeVol := safeNameRe.ReplaceAllString(volName, "")
	if safeVol == "" || safeVol != volName {
		jsonError(w, http.StatusBadRequest, "invalid volume name")
		return
	}

	var req struct {
		CapacityGB int `json:"capacity_gb"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.CapacityGB <= 0 || req.CapacityGB > 10240 {
		jsonError(w, http.StatusBadRequest, "capacity_gb must be between 1 and 10240")
		return
	}

	log.Printf("[storage] resizeVolume pool=%s vol=%s capacity=%dGB from %s",
		safePool, safeVol, req.CapacityGB, r.RemoteAddr)

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	// Get the volume path first.
	pathOut, err := exec.CommandContext(ctx, "virsh", "vol-path", safeVol, "--pool", safePool).Output()
	if err != nil {
		jsonError(w, http.StatusNotFound, "volume not found")
		return
	}
	volPath := strings.TrimSpace(string(pathOut))

	capacityBytes := strconv.FormatInt(int64(req.CapacityGB)*1024*1024*1024, 10)
	out, err := exec.CommandContext(ctx, "virsh", "vol-resize", volPath, capacityBytes).CombinedOutput()
	if err != nil {
		jsonError(w, http.StatusInternalServerError,
			fmt.Sprintf("virsh vol-resize failed: %s", strings.TrimSpace(string(out))))
		return
	}

	log.Printf("[storage] resizeVolume pool=%s vol=%s capacity=%dGB succeeded", safePool, safeVol, req.CapacityGB)
	s.auditLog(r, "vol_resize", safeVol, fmt.Sprintf("pool=%s capacity=%dGB", safePool, req.CapacityGB))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message":     fmt.Sprintf("Volume %s resized to %dGB", safeVol, req.CapacityGB),
		"capacity_gb": req.CapacityGB,
	})
}
