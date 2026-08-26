// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// ClusterEntry represents a single kubeconfig cluster registration.
type ClusterEntry struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	Source       string `json:"source"`        // "upload", "path", "migrated"
	OriginalPath string `json:"original_path"` // original file path if applicable
	Filename     string `json:"filename"`      // file on disk inside configDir
	AddedAt      string `json:"added_at"`
}

// ClustersConfig holds the full multi-kubeconfig state persisted to clusters.json.
type ClustersConfig struct {
	Active   string         `json:"active"`
	Clusters []ClusterEntry `json:"clusters"`
}

// KubeconfigManager manages multiple kubeconfig files on disk.
type KubeconfigManager struct {
	mu        sync.RWMutex
	config    ClustersConfig
	configDir string
}

const defaultKubeconfigDir = "/var/lib/hyper2kvm/kubeconfigs"
const legacySingleKubeconfig = "/var/lib/hyper2kvm/kubeconfig"

// NewKubeconfigManager creates a new manager, ensuring the storage directory
// exists and loading any previously persisted state from clusters.json.
// If a legacy single kubeconfig file exists and no clusters are configured,
// it is auto-migrated as the "default" cluster.
func NewKubeconfigManager(configDir string) (*KubeconfigManager, error) {
	if configDir == "" {
		configDir = defaultKubeconfigDir
	}

	if err := os.MkdirAll(configDir, 0750); err != nil {
		return nil, fmt.Errorf("create kubeconfig dir: %w", err)
	}

	mgr := &KubeconfigManager{
		configDir: configDir,
	}

	// Load existing clusters.json if present.
	metaPath := filepath.Join(configDir, "clusters.json")
	data, err := os.ReadFile(metaPath)
	if err == nil {
		if jsonErr := json.Unmarshal(data, &mgr.config); jsonErr != nil {
			return nil, fmt.Errorf("parse clusters.json: %w", jsonErr)
		}
	}

	// Auto-migrate legacy single kubeconfig.
	if len(mgr.config.Clusters) == 0 {
		if legacyData, err := os.ReadFile(legacySingleKubeconfig); err == nil && len(legacyData) > 0 {
			entry := ClusterEntry{
				ID:           "default",
				Name:         "default",
				Source:       "migrated",
				OriginalPath: legacySingleKubeconfig,
				Filename:     "default.kubeconfig",
				AddedAt:      time.Now().UTC().Format(time.RFC3339),
			}
			dst := filepath.Join(configDir, entry.Filename)
			if writeErr := os.WriteFile(dst, legacyData, 0600); writeErr != nil {
				return nil, fmt.Errorf("migrate legacy kubeconfig: %w", writeErr)
			}
			mgr.config.Clusters = []ClusterEntry{entry}
			mgr.config.Active = entry.ID
			if persistErr := mgr.persist(); persistErr != nil {
				return nil, fmt.Errorf("persist after migration: %w", persistErr)
			}
		}
	}

	return mgr, nil
}

// List returns a copy of the current clusters configuration.
func (m *KubeconfigManager) List() ClustersConfig {
	m.mu.RLock()
	defer m.mu.RUnlock()

	cp := ClustersConfig{
		Active:   m.config.Active,
		Clusters: make([]ClusterEntry, len(m.config.Clusters)),
	}
	copy(cp.Clusters, m.config.Clusters)
	return cp
}

// Add registers a new kubeconfig. The name is slugified to produce an ID.
// If this is the first cluster, it is automatically activated.
func (m *KubeconfigManager) Add(name, source string, data []byte, originalPath string) (ClusterEntry, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	id := slugify(name)
	if id == "" {
		return ClusterEntry{}, fmt.Errorf("invalid cluster name: produces empty ID")
	}

	for _, c := range m.config.Clusters {
		if c.ID == id {
			return ClusterEntry{}, fmt.Errorf("cluster %q already exists", id)
		}
	}

	filename := id + ".kubeconfig"
	dst := filepath.Join(m.configDir, filename)
	if err := os.WriteFile(dst, data, 0600); err != nil {
		return ClusterEntry{}, fmt.Errorf("write kubeconfig file: %w", err)
	}

	entry := ClusterEntry{
		ID:           id,
		Name:         name,
		Source:       source,
		OriginalPath: originalPath,
		Filename:     filename,
		AddedAt:      time.Now().UTC().Format(time.RFC3339),
	}
	m.config.Clusters = append(m.config.Clusters, entry)

	// Auto-activate if this is the first cluster.
	if len(m.config.Clusters) == 1 {
		m.config.Active = id
	}

	if err := m.persist(); err != nil {
		return ClusterEntry{}, fmt.Errorf("persist metadata: %w", err)
	}

	return entry, nil
}

// Activate sets the given cluster ID as the active kubeconfig.
func (m *KubeconfigManager) Activate(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	found := false
	for _, c := range m.config.Clusters {
		if c.ID == id {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("cluster %q not found", id)
	}

	m.config.Active = id
	return m.persist()
}

// Delete removes a cluster by ID, deleting both the kubeconfig file and
// metadata entry. If the deleted cluster was active, the active field is cleared.
func (m *KubeconfigManager) Delete(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	idx := -1
	for i, c := range m.config.Clusters {
		if c.ID == id {
			idx = i
			break
		}
	}
	if idx < 0 {
		return fmt.Errorf("cluster %q not found", id)
	}

	// Remove the kubeconfig file.
	fp := filepath.Join(m.configDir, m.config.Clusters[idx].Filename)
	os.Remove(fp) // best-effort

	// Remove from slice.
	m.config.Clusters = append(m.config.Clusters[:idx], m.config.Clusters[idx+1:]...)

	if m.config.Active == id {
		m.config.Active = ""
	}

	return m.persist()
}

// ActiveKubeconfigPath returns the full filesystem path to the currently
// active kubeconfig file, or an empty string if none is active.
func (m *KubeconfigManager) ActiveKubeconfigPath() string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	if m.config.Active == "" {
		return ""
	}
	for _, c := range m.config.Clusters {
		if c.ID == m.config.Active {
			return filepath.Join(m.configDir, c.Filename)
		}
	}
	return ""
}

// CheckConnection tests connectivity to the cluster identified by id.
// It returns whether the connection succeeded, the Kubernetes server
// version, and the API server URL.
func (m *KubeconfigManager) CheckConnection(id string) (connected bool, version, server string) {
	m.mu.RLock()
	var kubeconfigPath string
	for _, c := range m.config.Clusters {
		if c.ID == id {
			kubeconfigPath = filepath.Join(m.configDir, c.Filename)
			break
		}
	}
	m.mu.RUnlock()

	if kubeconfigPath == "" {
		return false, "", ""
	}

	env := append(os.Environ(), "KUBECONFIG="+kubeconfigPath)

	// Get server version.
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	verCmd := exec.CommandContext(ctx, "kubectl", "version", "--short")
	verCmd.Env = env
	verOut, err := verCmd.CombinedOutput()
	if err != nil {
		return false, "", ""
	}
	version = strings.TrimSpace(string(verOut))

	// Get server URL.
	srvCmd := exec.CommandContext(ctx, "kubectl", "config", "view", "--minify",
		"-o", "jsonpath={.clusters[0].cluster.server}")
	srvCmd.Env = env
	srvOut, err := srvCmd.Output()
	if err == nil {
		server = strings.TrimSpace(string(srvOut))
	}

	connected = true
	return
}

// persist atomically writes clusters.json using a temp file + rename.
func (m *KubeconfigManager) persist() error {
	data, err := json.MarshalIndent(m.config, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal clusters config: %w", err)
	}

	metaPath := filepath.Join(m.configDir, "clusters.json")
	tmp, err := os.CreateTemp(m.configDir, "clusters-*.tmp")
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	tmpName := tmp.Name()

	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		os.Remove(tmpName)
		return fmt.Errorf("write temp file: %w", err)
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpName)
		return fmt.Errorf("close temp file: %w", err)
	}

	if err := os.Rename(tmpName, metaPath); err != nil {
		os.Remove(tmpName)
		return fmt.Errorf("rename to clusters.json: %w", err)
	}

	return nil
}

var slugifyRe = regexp.MustCompile(`[^a-z0-9]+`)

// slugify converts a human-readable name to a DNS-safe identifier:
// lowercase, non-alphanumeric characters replaced with hyphens,
// consecutive hyphens collapsed, leading/trailing hyphens trimmed,
// and truncated to 63 characters.
func slugify(name string) string {
	s := strings.ToLower(name)
	s = slugifyRe.ReplaceAllString(s, "-")
	s = strings.Trim(s, "-")
	if len(s) > 63 {
		s = s[:63]
		s = strings.TrimRight(s, "-")
	}
	return s
}

