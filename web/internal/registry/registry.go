// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package registry

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"github.com/h2kvm/web/internal/domain"
	"github.com/h2kvm/web/internal/ports"
)

// ProviderFactory creates a new ComputeProvider instance.
type ProviderFactory func() ports.ComputeProvider

// Registry manages provider connections.
type Registry struct {
	mu          sync.RWMutex
	factories   map[domain.ProviderType]ProviderFactory
	connections map[string]ports.ComputeProvider // keyed by provider config ID
	configs     map[string]domain.ProviderConfig
	persistPath string // path to JSON file for credential persistence
}

// New creates an empty provider registry.
func New() *Registry {
	return &Registry{
		factories:   make(map[domain.ProviderType]ProviderFactory),
		connections: make(map[string]ports.ComputeProvider),
		configs:     make(map[string]domain.ProviderConfig),
	}
}

// SetPersistPath sets the file path for saving/loading provider configs.
func (r *Registry) SetPersistPath(path string) {
	r.persistPath = path
}

// persist saves the current configs map to disk as JSON.
// Must be called while r.mu is held (at least RLock).
func (r *Registry) persist() {
	if r.persistPath == "" {
		return
	}
	data, err := json.MarshalIndent(r.configs, "", "  ")
	if err != nil {
		return
	}
	_ = os.MkdirAll(filepath.Dir(r.persistPath), 0750)
	_ = os.WriteFile(r.persistPath, data, 0600)
}

// LoadSaved reads previously persisted provider configs from disk.
// Returns the configs so the caller can re-connect them.
func (r *Registry) LoadSaved() []domain.ProviderConfig {
	if r.persistPath == "" {
		return nil
	}
	data, err := os.ReadFile(r.persistPath)
	if err != nil {
		return nil
	}
	var configs map[string]domain.ProviderConfig
	if err := json.Unmarshal(data, &configs); err != nil {
		return nil
	}
	var result []domain.ProviderConfig
	for _, c := range configs {
		result = append(result, c)
	}
	return result
}

// RegisterFactory registers a provider factory for the given type.
func (r *Registry) RegisterFactory(pType domain.ProviderType, factory ProviderFactory) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.factories[pType] = factory
}

// Connect creates and connects a provider from the given config.
func (r *Registry) Connect(ctx context.Context, config domain.ProviderConfig) error {
	r.mu.Lock()
	factory, ok := r.factories[config.Type]
	if !ok {
		r.mu.Unlock()
		return fmt.Errorf("unsupported provider type: %s", config.Type)
	}
	r.mu.Unlock()

	provider := factory()
	if err := provider.Connect(ctx, config); err != nil {
		return fmt.Errorf("connect %s (%s): %w", config.Name, config.Type, err)
	}

	r.mu.Lock()
	r.connections[config.ID] = provider
	r.configs[config.ID] = config
	r.persist()
	r.mu.Unlock()

	return nil
}

// Disconnect closes a provider connection.
func (r *Registry) Disconnect(ctx context.Context, id string) error {
	r.mu.Lock()
	provider, ok := r.connections[id]
	if !ok {
		r.mu.Unlock()
		return fmt.Errorf("provider not found: %s", id)
	}
	delete(r.connections, id)
	delete(r.configs, id)
	r.persist()
	r.mu.Unlock()

	return provider.Disconnect(ctx)
}

// Get returns a connected provider by ID.
func (r *Registry) Get(id string) (ports.ComputeProvider, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	provider, ok := r.connections[id]
	if !ok {
		return nil, fmt.Errorf("provider not found: %s", id)
	}
	return provider, nil
}

// List returns all configured providers with their connection status.
func (r *Registry) List() []domain.ProviderStatus {
	r.mu.RLock()
	defer r.mu.RUnlock()

	var result []domain.ProviderStatus
	for id, config := range r.configs {
		_, connected := r.connections[id]
		result = append(result, domain.ProviderStatus{
			ID:        id,
			Type:      config.Type,
			Name:      config.Name,
			Connected: connected,
		})
	}
	return result
}

// GetConfig returns a provider config by ID.
func (r *Registry) GetConfig(id string) (domain.ProviderConfig, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	config, ok := r.configs[id]
	return config, ok
}

// DisconnectAll closes all provider connections.
func (r *Registry) DisconnectAll(ctx context.Context) {
	r.mu.Lock()
	providers := make(map[string]ports.ComputeProvider)
	for id, p := range r.connections {
		providers[id] = p
	}
	r.connections = make(map[string]ports.ComputeProvider)
	r.configs = make(map[string]domain.ProviderConfig)
	r.mu.Unlock()

	for _, p := range providers {
		_ = p.Disconnect(ctx)
	}
}
