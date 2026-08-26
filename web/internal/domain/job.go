// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package domain

import "time"

// JobStatus represents the lifecycle state of a migration job.
type JobStatus string

const (
	JobPending   JobStatus = "pending"
	JobRunning   JobStatus = "running"
	JobCompleted JobStatus = "completed"
	JobFailed    JobStatus = "failed"
	JobCancelled JobStatus = "cancelled"
)

// Job represents a migration job and its current state.
type Job struct {
	ID          string          `json:"id"`
	Config      MigrationConfig `json:"config"`
	Status      JobStatus       `json:"status"`
	Progress    *JobProgress    `json:"progress,omitempty"`
	LogLines    []string        `json:"log_lines,omitempty"`
	Error       string          `json:"error,omitempty"`
	PID         int             `json:"pid,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
	StartedAt   *time.Time      `json:"started_at,omitempty"`
	CompletedAt *time.Time      `json:"completed_at,omitempty"`
}

// JobProgress tracks real-time progress of a running migration.
type JobProgress struct {
	Phase           string  `json:"phase"`
	PercentComplete float64 `json:"percent_complete"`
	CurrentStep     string  `json:"current_step"`
	BytesProcessed  int64   `json:"bytes_processed,omitempty"`
	TotalBytes      int64   `json:"total_bytes,omitempty"`
	Rate            string  `json:"rate,omitempty"`
	ETA             string  `json:"eta,omitempty"`
}

// JobFilter constrains job listing results.
type JobFilter struct {
	Status []JobStatus `json:"status,omitempty"`
	Limit  int         `json:"limit,omitempty"`
}

// JobStats holds aggregate job statistics.
type JobStats struct {
	Total     int `json:"total"`
	Pending   int `json:"pending"`
	Running   int `json:"running"`
	Completed int `json:"completed"`
	Failed    int `json:"failed"`
	Cancelled int `json:"cancelled"`
}

// JobEvent is sent over WebSocket to notify clients of job state changes.
type JobEvent struct {
	Type   string      `json:"type"`
	JobID  string      `json:"job_id"`
	Data   interface{} `json:"data,omitempty"`
	Time   time.Time   `json:"time"`
}
