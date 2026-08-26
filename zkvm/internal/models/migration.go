// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package models

import "time"

// MigrationStatus represents the status of a migration.
type MigrationStatus string

const (
	StatusPending   MigrationStatus = "pending"
	StatusRunning   MigrationStatus = "running"
	StatusPaused    MigrationStatus = "paused"
	StatusCompleted MigrationStatus = "completed"
	StatusFailed    MigrationStatus = "failed"
	StatusCancelled MigrationStatus = "cancelled"
)

// IsActive returns true if the migration is still running.
func (s MigrationStatus) IsActive() bool {
	return s == StatusPending || s == StatusRunning || s == StatusPaused
}

// MigrationRecord tracks a single migration operation.
type MigrationRecord struct {
	ID           string          `json:"id"`
	VMName       string          `json:"vm_name"`
	SourceType   string          `json:"source_type"`
	Status       MigrationStatus `json:"status"`
	StartTime    time.Time       `json:"start_time"`
	EndTime      *time.Time      `json:"end_time,omitempty"`
	Progress     float64         `json:"progress"`
	CurrentStage string          `json:"current_stage,omitempty"`
	Throughput   float64         `json:"throughput_mbps,omitempty"`
	Elapsed      float64         `json:"elapsed_seconds,omitempty"`
	ETA          float64         `json:"eta_seconds,omitempty"`
	ErrorMessage string          `json:"error_message,omitempty"`
	OutputPath   string          `json:"output_path,omitempty"`
	SourcePath   string          `json:"source_path,omitempty"`
	SizeMB       float64         `json:"size_mb,omitempty"`
}

// Duration returns the migration duration.
func (m *MigrationRecord) Duration() time.Duration {
	if m.EndTime != nil {
		return m.EndTime.Sub(m.StartTime)
	}
	if m.Status.IsActive() {
		return time.Since(m.StartTime)
	}
	return 0
}

// StatusColor returns a color identifier for the status.
func (m *MigrationRecord) StatusColor() string {
	switch m.Status {
	case StatusRunning:
		return "green"
	case StatusPaused:
		return "yellow"
	case StatusCompleted:
		return "green"
	case StatusFailed:
		return "red"
	case StatusCancelled:
		return "dim"
	default:
		return "cyan"
	}
}
