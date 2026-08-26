// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package state

import (
	"testing"
	"time"

	"github.com/h2kvm/zkvm/internal/models"
	"github.com/h2kvm/zkvm/internal/protocol"
)

func TestNewStore(t *testing.T) {
	s := NewStore()
	if s.Migrations == nil {
		t.Fatal("Migrations map should be initialized")
	}
	if s.Logs == nil {
		t.Fatal("Logs slice should be initialized")
	}
	if s.Connected {
		t.Error("should not be connected initially")
	}
	if s.Config.Migration.DefaultFormat != "qcow2" {
		t.Errorf("expected default format qcow2, got %s", s.Config.Migration.DefaultFormat)
	}
}

func TestUpdateMigration(t *testing.T) {
	s := NewStore()
	m := &models.MigrationRecord{ID: "test-1", VMName: "vm1", Status: models.StatusRunning}
	s.UpdateMigration(m)

	got := s.GetMigration("test-1")
	if got == nil {
		t.Fatal("migration not found")
	}
	if got.VMName != "vm1" {
		t.Errorf("expected vm1, got %s", got.VMName)
	}
	if s.MigrationCount() != 1 {
		t.Errorf("expected 1 migration, got %d", s.MigrationCount())
	}
}

func TestGetActiveMigrations(t *testing.T) {
	s := NewStore()
	s.UpdateMigration(&models.MigrationRecord{ID: "1", Status: models.StatusRunning})
	s.UpdateMigration(&models.MigrationRecord{ID: "2", Status: models.StatusCompleted})
	s.UpdateMigration(&models.MigrationRecord{ID: "3", Status: models.StatusPending})

	active := s.GetActiveMigrations()
	if len(active) != 2 {
		t.Errorf("expected 2 active migrations, got %d", len(active))
	}
}

func TestAddLog(t *testing.T) {
	s := NewStore()
	for i := 0; i < 5; i++ {
		s.AddLog(LogEntry{Timestamp: time.Now(), Level: LogLevelInfo, Message: "test"})
	}

	logs := s.GetRecentLogs(3)
	if len(logs) != 3 {
		t.Errorf("expected 3 logs, got %d", len(logs))
	}
}

func TestAddLogEviction(t *testing.T) {
	s := NewStore()
	for i := 0; i < maxLogEntries+100; i++ {
		s.AddLog(LogEntry{Timestamp: time.Now(), Level: LogLevelInfo, Message: "test"})
	}

	if len(s.Logs) != maxLogEntries {
		t.Errorf("expected %d logs after eviction, got %d", maxLogEntries, len(s.Logs))
	}
}

func TestAppendLog(t *testing.T) {
	s := NewStore()
	s.AppendLog(protocol.LogData{
		Message:   "hello",
		Level:     "INFO",
		Timestamp: time.Now().Format(time.RFC3339),
	})

	logs := s.GetRecentLogs(1)
	if len(logs) != 1 {
		t.Fatal("expected 1 log entry")
	}
	if logs[0].Message != "hello" {
		t.Errorf("expected message 'hello', got '%s'", logs[0].Message)
	}
}

func TestAppendLogInvalidTimestamp(t *testing.T) {
	s := NewStore()
	s.AppendLog(protocol.LogData{
		Message:   "bad time",
		Level:     "ERROR",
		Timestamp: "not-a-timestamp",
	})

	logs := s.GetRecentLogs(1)
	if len(logs) != 1 {
		t.Fatal("expected 1 log entry even with bad timestamp")
	}
}

func TestGetRecentLogsEdgeCases(t *testing.T) {
	s := NewStore()
	s.AddLog(LogEntry{Message: "one"})
	s.AddLog(LogEntry{Message: "two"})

	// Request more than available
	logs := s.GetRecentLogs(100)
	if len(logs) != 2 {
		t.Errorf("expected 2, got %d", len(logs))
	}

	// Request 0
	logs = s.GetRecentLogs(0)
	if logs != nil {
		t.Errorf("expected nil for n=0, got %v", logs)
	}

	// Request negative
	logs = s.GetRecentLogs(-1)
	if logs != nil {
		t.Errorf("expected nil for n=-1, got %v", logs)
	}
}

func TestSetConnected(t *testing.T) {
	s := NewStore()
	s.SetConnected(true)
	if !s.IsConnected() {
		t.Error("expected connected")
	}
	s.SetConnected(false)
	if s.IsConnected() {
		t.Error("expected disconnected")
	}
}

func TestUpdateStats(t *testing.T) {
	s := NewStore()
	stats := models.Statistics{TotalMigrations: 42}
	s.UpdateStats(stats)
	got := s.GetStats()
	if got.TotalMigrations != 42 {
		t.Errorf("expected 42 total migrations, got %d", got.TotalMigrations)
	}
}

func TestSetConfig(t *testing.T) {
	s := NewStore()
	cfg := models.TUIConfig{
		General: models.GeneralConfig{LogLevel: "debug"},
	}
	s.SetConfig(cfg)
	got := s.GetConfig()
	if got.General.LogLevel != "debug" {
		t.Errorf("expected debug log level, got %s", got.General.LogLevel)
	}
}

func TestGetMigrationNotFound(t *testing.T) {
	s := NewStore()
	if s.GetMigration("nonexistent") != nil {
		t.Error("expected nil for nonexistent migration")
	}
}

func TestGetLogsProtocol(t *testing.T) {
	s := NewStore()
	s.AddLog(LogEntry{Timestamp: time.Now(), Level: LogLevelError, Message: "err"})
	s.AddLog(LogEntry{Timestamp: time.Now(), Level: LogLevelInfo, Message: "info"})

	logs := s.GetLogs(1)
	if len(logs) != 1 {
		t.Errorf("expected 1, got %d", len(logs))
	}
	if logs[0].Level != "INFO" {
		t.Errorf("expected INFO, got %s", logs[0].Level)
	}

	// All logs
	all := s.GetLogs(0)
	if len(all) != 2 {
		t.Errorf("expected 2 for n=0, got %d", len(all))
	}
}

func TestConcurrentAccess(t *testing.T) {
	s := NewStore()
	done := make(chan bool, 4)

	go func() {
		for i := 0; i < 100; i++ {
			s.AddLog(LogEntry{Message: "log"})
		}
		done <- true
	}()
	go func() {
		for i := 0; i < 100; i++ {
			s.GetRecentLogs(10)
		}
		done <- true
	}()
	go func() {
		for i := 0; i < 100; i++ {
			s.UpdateMigration(&models.MigrationRecord{ID: "m1", Status: models.StatusRunning})
		}
		done <- true
	}()
	go func() {
		for i := 0; i < 100; i++ {
			s.GetActiveMigrations()
		}
		done <- true
	}()

	for i := 0; i < 4; i++ {
		<-done
	}
}
