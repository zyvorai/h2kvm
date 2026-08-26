// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package state

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/h2kvm/zkvm/internal/models"
	"github.com/h2kvm/zkvm/internal/protocol"
)

// settingsDir is the base directory for persistent configuration.
const settingsDir = ".config/h2kvm"

// settingsFile is the filename for persisted settings.
const settingsFile = "settings.json"

// maxLogEntries is the maximum number of log entries retained in the store.
const maxLogEntries = 1000

// LogLevel represents a log severity level.
type LogLevel string

const (
	LogLevelDebug   LogLevel = "DEBUG"
	LogLevelInfo    LogLevel = "INFO"
	LogLevelWarning LogLevel = "WARNING"
	LogLevelError   LogLevel = "ERROR"
)

// LogEntry represents a single log message.
type LogEntry struct {
	Timestamp time.Time
	Level     LogLevel
	Message   string
}

// Store holds all application state fed by socket events.
type Store struct {
	mu         sync.RWMutex
	Migrations map[string]*models.MigrationRecord
	Logs       []LogEntry
	Stats      models.Statistics
	Config     models.TUIConfig
	Connected  bool

	// Client is the protocol client for sending requests.
	Client *protocol.Client

	// Version holds the application version string.
	Version string
}

// NewStore creates a new state store with default values.
func NewStore() *Store {
	return &Store{
		Migrations: make(map[string]*models.MigrationRecord),
		Logs:       make([]LogEntry, 0, maxLogEntries),
		Config:     models.DefaultConfig(),
		Version:    "0.1.0",
	}
}

// UpdateMigration adds or updates a migration record in the store.
func (s *Store) UpdateMigration(m *models.MigrationRecord) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Migrations[m.ID] = m
}

// AddLog appends a log entry, evicting the oldest entries when the
// buffer exceeds maxLogEntries.
func (s *Store) AddLog(entry LogEntry) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.Logs = append(s.Logs, entry)
	if len(s.Logs) > maxLogEntries {
		excess := len(s.Logs) - maxLogEntries
		s.Logs = s.Logs[excess:]
	}
}

// AppendLog adds a log entry from protocol data, keeping at most
// maxLogEntries entries. This provides backward compatibility with
// code that uses protocol.LogData directly.
func (s *Store) AppendLog(log protocol.LogData) {
	ts, err := time.Parse(time.RFC3339, log.Timestamp)
	if err != nil {
		ts = time.Now()
	}

	s.AddLog(LogEntry{
		Timestamp: ts,
		Level:     LogLevel(log.Level),
		Message:   log.Message,
	})
}

// UpdateStats replaces the current statistics snapshot.
func (s *Store) UpdateStats(stats models.Statistics) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Stats = stats
}

// SetStats is a backward-compatible alias for UpdateStats.
func (s *Store) SetStats(stats models.Statistics) {
	s.UpdateStats(stats)
}

// UpdateConfig replaces the current TUI configuration.
func (s *Store) UpdateConfig(cfg models.TUIConfig) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Config = cfg
}

// SetConfig is a backward-compatible alias for UpdateConfig.
func (s *Store) SetConfig(cfg models.TUIConfig) {
	s.UpdateConfig(cfg)
}

// SetConnected updates the connection status.
func (s *Store) SetConnected(connected bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Connected = connected
}

// GetActiveMigrations returns all migrations that are still active.
func (s *Store) GetActiveMigrations() []*models.MigrationRecord {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var active []*models.MigrationRecord
	for _, m := range s.Migrations {
		if m.Status.IsActive() {
			active = append(active, m)
		}
	}
	return active
}

// GetRecentLogs returns the most recent n log entries. If n is larger
// than the number of stored entries, all entries are returned.
func (s *Store) GetRecentLogs(n int) []LogEntry {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if n <= 0 {
		return nil
	}
	if n > len(s.Logs) {
		n = len(s.Logs)
	}
	start := len(s.Logs) - n
	result := make([]LogEntry, n)
	copy(result, s.Logs[start:])
	return result
}

// GetLogs returns the most recent n log entries as protocol.LogData
// for backward compatibility. If n is <= 0 or > total, all entries
// are returned.
func (s *Store) GetLogs(n int) []protocol.LogData {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if n <= 0 || n > len(s.Logs) {
		n = len(s.Logs)
	}
	start := len(s.Logs) - n
	out := make([]protocol.LogData, n)
	for i, entry := range s.Logs[start : start+n] {
		out[i] = protocol.LogData{
			Message:   entry.Message,
			Level:     string(entry.Level),
			Timestamp: entry.Timestamp.Format(time.RFC3339),
		}
	}
	return out
}

// GetStats returns a copy of the current statistics.
func (s *Store) GetStats() models.Statistics {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.Stats
}

// GetConfig returns a copy of the current configuration.
func (s *Store) GetConfig() models.TUIConfig {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.Config
}

// IsConnected returns the current connection status.
func (s *Store) IsConnected() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.Connected
}

// GetMigration returns a single migration record by ID, or nil if not found.
func (s *Store) GetMigration(id string) *models.MigrationRecord {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.Migrations[id]
}

// MigrationCount returns the total number of tracked migrations.
func (s *Store) MigrationCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.Migrations)
}

// settingsPath returns the full path to the settings file.
func settingsPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, settingsDir, settingsFile), nil
}

// SaveConfigToFile persists the current configuration to disk as JSON.
func (s *Store) SaveConfigToFile() error {
	s.mu.RLock()
	cfg := s.Config
	s.mu.RUnlock()

	path, err := settingsPath()
	if err != nil {
		return err
	}

	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}

	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}

	// Atomic write: write to temp file then rename to avoid corruption.
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// LoadConfigFromFile loads configuration from disk, merging with defaults.
// Fields not present in the file retain their default values.
func (s *Store) LoadConfigFromFile() error {
	path, err := settingsPath()
	if err != nil {
		return err
	}

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // No saved settings, use defaults
		}
		return err
	}

	// Start from defaults so new fields get default values.
	cfg := models.DefaultConfig()
	if err := json.Unmarshal(data, &cfg); err != nil {
		return err
	}

	s.mu.Lock()
	s.Config = cfg
	s.mu.Unlock()

	return nil
}
