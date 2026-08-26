// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package models

import (
	"testing"
	"time"
)

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.General.OutputDir != "/tmp/h2kvm-output" {
		t.Errorf("expected output dir /tmp/h2kvm-output, got %s", cfg.General.OutputDir)
	}
	if cfg.Migration.DefaultFormat != "qcow2" {
		t.Errorf("expected default format qcow2, got %s", cfg.Migration.DefaultFormat)
	}
	if !cfg.Migration.EnableCompression {
		t.Error("expected compression enabled by default")
	}
	if cfg.Migration.ParallelMigrations != 2 {
		t.Errorf("expected 2 parallel migrations, got %d", cfg.Migration.ParallelMigrations)
	}
	if cfg.OfflineFixes.FstabMode != "stabilize-all" {
		t.Errorf("expected fstab mode stabilize-all, got %s", cfg.OfflineFixes.FstabMode)
	}
	if !cfg.OfflineFixes.RegenInitramfs {
		t.Error("expected initramfs regen enabled")
	}
	if cfg.Advanced.GuestfsBackend != "vmcraft" {
		t.Errorf("expected vmcraft backend, got %s", cfg.Advanced.GuestfsBackend)
	}
	if cfg.Performance.MaxConcurrentOps != 4 {
		t.Errorf("expected 4 max concurrent ops, got %d", cfg.Performance.MaxConcurrentOps)
	}
}

func TestMigrationStatusIsActive(t *testing.T) {
	tests := []struct {
		status MigrationStatus
		active bool
	}{
		{StatusPending, true},
		{StatusRunning, true},
		{StatusPaused, true},
		{StatusCompleted, false},
		{StatusFailed, false},
		{StatusCancelled, false},
	}
	for _, tc := range tests {
		if tc.status.IsActive() != tc.active {
			t.Errorf("IsActive(%s) = %v, want %v", tc.status, tc.status.IsActive(), tc.active)
		}
	}
}

func TestMigrationRecordDuration(t *testing.T) {
	now := time.Now()

	// Completed migration
	end := now.Add(5 * time.Minute)
	m := &MigrationRecord{
		Status:    StatusCompleted,
		StartTime: now,
		EndTime:   &end,
	}
	d := m.Duration()
	if d != 5*time.Minute {
		t.Errorf("expected 5m duration, got %v", d)
	}

	// Active migration (no end time)
	active := &MigrationRecord{
		Status:    StatusRunning,
		StartTime: now.Add(-10 * time.Second),
	}
	ad := active.Duration()
	if ad < 9*time.Second || ad > 20*time.Second {
		t.Errorf("expected ~10s duration for active, got %v", ad)
	}

	// Failed migration with no end time and not active
	failed := &MigrationRecord{
		Status:    StatusFailed,
		StartTime: now,
	}
	if failed.Duration() != 0 {
		t.Errorf("expected 0 duration for failed without end time, got %v", failed.Duration())
	}
}

func TestMigrationRecordStatusColor(t *testing.T) {
	tests := []struct {
		status MigrationStatus
		color  string
	}{
		{StatusRunning, "green"},
		{StatusPaused, "yellow"},
		{StatusCompleted, "green"},
		{StatusFailed, "red"},
		{StatusCancelled, "dim"},
		{StatusPending, "cyan"},
	}
	for _, tc := range tests {
		m := &MigrationRecord{Status: tc.status}
		if m.StatusColor() != tc.color {
			t.Errorf("StatusColor(%s) = %s, want %s", tc.status, m.StatusColor(), tc.color)
		}
	}
}
