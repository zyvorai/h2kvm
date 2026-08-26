// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"
)

const cleanupConfigPath = "/var/lib/h2kvm/cleanup-config.json"

// activeJobMinAge protects in-progress artifacts from phase-2 (oldest-first) cleanup.
const activeJobMinAge = 2 * time.Hour

// isProtectedFromCleanup skips files that must not be deleted during active migrations.
func isProtectedFromCleanup(path string, info os.FileInfo) bool {
	base := filepath.Base(path)
	lower := strings.ToLower(base)
	if strings.HasSuffix(lower, ".part") || strings.HasSuffix(lower, ".tmp") {
		return true
	}
	// Phase 2 ignores max_age — never delete recently modified job outputs.
	if time.Since(info.ModTime()) < activeJobMinAge {
		return true
	}
	return false
}

// CleanupConfig holds the auto-cleanup configuration.
type CleanupConfig struct {
	Enabled          bool     `json:"enabled"`
	ThresholdPercent int      `json:"threshold_percent"`
	MaxAgeHours      int      `json:"max_age_hours"`
	Dirs             []string `json:"dirs"`
	LastCleanup      string   `json:"last_cleanup,omitempty"`
	LastResult       string   `json:"last_result,omitempty"`
}

// cleanupState holds the runtime cleanup state on the server.
type cleanupState struct {
	mu     sync.RWMutex
	config CleanupConfig
	ticker *time.Ticker
}

// initAutoCleanup loads persisted settings and starts the background goroutine.
func (s *Server) initAutoCleanup() {
	s.cleanup = &cleanupState{}
	s.cleanup.config = CleanupConfig{
		Enabled:          true,
		ThresholdPercent: 85,
		MaxAgeHours:      24,
		Dirs:             []string{"output", "input"},
	}

	// Load from disk if present.
	data, err := os.ReadFile(cleanupConfigPath)
	if err == nil {
		var cfg CleanupConfig
		if err := json.Unmarshal(data, &cfg); err == nil {
			s.cleanup.config = cfg
			log.Printf("[auto-cleanup] loaded config from %s (enabled=%v threshold=%d%% max_age=%dh)",
				cleanupConfigPath, cfg.Enabled, cfg.ThresholdPercent, cfg.MaxAgeHours)
		} else {
			log.Printf("[auto-cleanup] corrupt %s, using defaults: %v", cleanupConfigPath, err)
		}
	}

	// Start background ticker.
	s.cleanup.ticker = time.NewTicker(10 * time.Minute)
	go func() {
		for {
			select {
			case <-s.cleanup.ticker.C:
				s.runAutoCleanup()
			case <-s.ctx.Done():
				s.cleanup.ticker.Stop()
				return
			}
		}
	}()
	log.Printf("[auto-cleanup] background goroutine started (interval=10m)")
}

// saveCleanupConfig persists the cleanup config to disk.
func (s *Server) saveCleanupConfig() {
	dir := filepath.Dir(cleanupConfigPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		log.Printf("[auto-cleanup] cannot create %s: %v", dir, err)
		return
	}

	data, err := json.MarshalIndent(s.cleanup.config, "", "  ")
	if err != nil {
		log.Printf("[auto-cleanup] marshal error: %v", err)
		return
	}

	if err := os.WriteFile(cleanupConfigPath, data, 0644); err != nil {
		log.Printf("[auto-cleanup] write %s failed: %v", cleanupConfigPath, err)
	}
}

// runAutoCleanup checks disk usage and cleans up old artifacts if threshold is exceeded.
func (s *Server) runAutoCleanup() {
	s.cleanup.mu.RLock()
	if !s.cleanup.config.Enabled {
		s.cleanup.mu.RUnlock()
		return
	}
	threshold := s.cleanup.config.ThresholdPercent
	maxAge := s.cleanup.config.MaxAgeHours
	dirs := make([]string, len(s.cleanup.config.Dirs))
	copy(dirs, s.cleanup.config.Dirs)
	s.cleanup.mu.RUnlock()

	// Check disk usage using syscall.Statfs.
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/var/lib/h2kvm", &stat); err != nil {
		log.Printf("[auto-cleanup] statfs failed: %v", err)
		return
	}
	usedPercent := 100.0 - (float64(stat.Bavail) / float64(stat.Blocks) * 100.0)

	if usedPercent <= float64(threshold) {
		return
	}

	log.Printf("[auto-cleanup] disk usage %.1f%% exceeds threshold %d%%, starting cleanup", usedPercent, threshold)

	// Resolve allowed directories.
	allowedDirs := map[string]string{
		"output": "/var/lib/h2kvm/output",
		"input":  "/var/lib/h2kvm/input",
	}

	var targetDirs []string
	for _, d := range dirs {
		if fullPath, ok := allowedDirs[d]; ok {
			targetDirs = append(targetDirs, fullPath)
		}
	}
	if len(targetDirs) == 0 {
		targetDirs = []string{"/var/lib/h2kvm/output", "/var/lib/h2kvm/input"}
	}

	// Phase 1: age-based cleanup.
	cutoff := time.Now().Add(-time.Duration(maxAge) * time.Hour)
	var deleted int
	var freedBytes int64

	for _, dir := range targetDirs {
		filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			if !strings.HasPrefix(path, "/var/lib/h2kvm/") {
				return nil
			}
			if isProtectedFromCleanup(path, info) {
				return nil
			}
			if info.ModTime().Before(cutoff) {
				size := info.Size()
				if err := os.Remove(path); err != nil {
					log.Printf("[auto-cleanup] failed to delete %s: %v", path, err)
				} else {
					log.Printf("[auto-cleanup] deleted %s (%s)", path, formatBytesHuman(size))
					deleted++
					freedBytes += size
				}
			}
			return nil
		})
	}

	// Phase 2: if still over threshold, delete oldest files first.
	if err := syscall.Statfs("/var/lib/h2kvm", &stat); err == nil {
		usedPercent = 100.0 - (float64(stat.Bavail) / float64(stat.Blocks) * 100.0)
	}

	if usedPercent > float64(threshold) {
		type fileEntry struct {
			path    string
			size    int64
			modTime time.Time
		}
		var files []fileEntry

		for _, dir := range targetDirs {
			filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
				if err != nil || info.IsDir() {
					return nil
				}
				if !strings.HasPrefix(path, "/var/lib/h2kvm/") {
					return nil
				}
				if isProtectedFromCleanup(path, info) {
					return nil
				}
				files = append(files, fileEntry{path: path, size: info.Size(), modTime: info.ModTime()})
				return nil
			})
		}

		// Sort oldest first.
		sort.Slice(files, func(i, j int) bool {
			return files[i].modTime.Before(files[j].modTime)
		})

		for _, f := range files {
			if err := os.Remove(f.path); err != nil {
				log.Printf("[auto-cleanup] failed to delete %s: %v", f.path, err)
				continue
			}
			log.Printf("[auto-cleanup] deleted (oldest) %s (%s)", f.path, formatBytesHuman(f.size))
			deleted++
			freedBytes += f.size

			// Re-check disk usage.
			if err := syscall.Statfs("/var/lib/h2kvm", &stat); err == nil {
				usedPercent = 100.0 - (float64(stat.Bavail) / float64(stat.Blocks) * 100.0)
				if usedPercent <= float64(threshold) {
					break
				}
			}
		}
	}

	resultMsg := fmt.Sprintf("deleted %d files, freed %s", deleted, formatBytesHuman(freedBytes))
	log.Printf("[auto-cleanup] complete: %s", resultMsg)

	s.cleanup.mu.Lock()
	s.cleanup.config.LastCleanup = time.Now().Format(time.RFC3339)
	s.cleanup.config.LastResult = resultMsg
	s.cleanup.mu.Unlock()

	s.saveCleanupConfig()
}

// handleGetCleanupSettings returns current auto-cleanup configuration.
func (s *Server) handleGetCleanupSettings(w http.ResponseWriter, r *http.Request) {
	s.cleanup.mu.RLock()
	cfg := s.cleanup.config
	s.cleanup.mu.RUnlock()

	// Also include current disk usage.
	var diskPercent float64
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/var/lib/h2kvm", &stat); err == nil {
		diskPercent = 100.0 - (float64(stat.Bavail) / float64(stat.Blocks) * 100.0)
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"enabled":           cfg.Enabled,
		"threshold_percent": cfg.ThresholdPercent,
		"max_age_hours":     cfg.MaxAgeHours,
		"dirs":              cfg.Dirs,
		"last_cleanup":      cfg.LastCleanup,
		"last_result":       cfg.LastResult,
		"disk_usage_percent": diskPercent,
	})
}

// handleSetCleanupSettings updates auto-cleanup configuration.
func (s *Server) handleSetCleanupSettings(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Enabled          *bool    `json:"enabled"`
		ThresholdPercent *int     `json:"threshold_percent"`
		MaxAgeHours      *int     `json:"max_age_hours"`
		Dirs             []string `json:"dirs"`
		RunNow           bool     `json:"run_now"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	s.cleanup.mu.Lock()
	if req.Enabled != nil {
		s.cleanup.config.Enabled = *req.Enabled
	}
	if req.ThresholdPercent != nil {
		v := *req.ThresholdPercent
		if v < 50 || v > 95 {
			s.cleanup.mu.Unlock()
			jsonError(w, http.StatusBadRequest, "threshold_percent must be between 50 and 95")
			return
		}
		s.cleanup.config.ThresholdPercent = v
	}
	if req.MaxAgeHours != nil {
		v := *req.MaxAgeHours
		if v < 0 {
			s.cleanup.mu.Unlock()
			jsonError(w, http.StatusBadRequest, "max_age_hours must be non-negative")
			return
		}
		s.cleanup.config.MaxAgeHours = v
	}
	if len(req.Dirs) > 0 {
		// Validate dirs.
		allowed := map[string]bool{"output": true, "input": true}
		for _, d := range req.Dirs {
			if !allowed[d] {
				s.cleanup.mu.Unlock()
				jsonError(w, http.StatusBadRequest, fmt.Sprintf("invalid dir %q: allowed values are \"output\" and \"input\"", d))
				return
			}
		}
		s.cleanup.config.Dirs = req.Dirs
	}
	s.cleanup.mu.Unlock()

	s.saveCleanupConfig()

	log.Printf("[auto-cleanup] settings updated: enabled=%v threshold=%d%% max_age=%dh dirs=%v",
		s.cleanup.config.Enabled, s.cleanup.config.ThresholdPercent,
		s.cleanup.config.MaxAgeHours, s.cleanup.config.Dirs)

	if req.RunNow {
		go s.runAutoCleanup()
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"message": "cleanup settings updated",
	})
}
