// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package ports

import (
	"github.com/h2kvm/web/internal/domain"
)

// JobManager orchestrates migration job lifecycle.
type JobManager interface {
	// Submit queues a new migration job and returns its ID.
	Submit(config domain.MigrationConfig) (string, error)
	// Get returns a job by ID.
	Get(id string) (*domain.Job, error)
	// List returns all jobs, optionally filtered.
	List(filter domain.JobFilter) []*domain.Job
	// Cancel requests cancellation of a running job.
	Cancel(id string) error
	// Stats returns aggregate job statistics.
	Stats() domain.JobStats
}

// EventBroadcaster pushes real-time job events to connected clients.
type EventBroadcaster interface {
	// Broadcast sends a typed message to all connected WebSocket clients.
	Broadcast(msgType string, data map[string]interface{})
}
