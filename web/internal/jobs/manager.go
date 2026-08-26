// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package jobs

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/hyper2kvm/web/internal/domain"
	"github.com/hyper2kvm/web/internal/ports"
)

// Manager is an in-memory job queue that executes migrations via H2KVMRunner.
// Implements ports.JobManager.
type Manager struct {
	mu          sync.RWMutex
	jobs        map[string]*domain.Job
	order       []string // insertion order
	runner      ports.H2KVMRunner
	broadcaster ports.EventBroadcaster
	ctx         context.Context
}

// NewManager creates a job manager wired to the given runner and broadcaster.
func NewManager(ctx context.Context, runner ports.H2KVMRunner, broadcaster ports.EventBroadcaster) *Manager {
	return &Manager{
		jobs:        make(map[string]*domain.Job),
		runner:      runner,
		broadcaster: broadcaster,
		ctx:         ctx,
	}
}

// Submit queues a new migration job and starts it immediately.
func (m *Manager) Submit(config domain.MigrationConfig) (string, error) {
	id := uuid.New().String()[:8]
	now := time.Now()

	job := &domain.Job{
		ID:        id,
		Config:    config,
		Status:    domain.JobPending,
		CreatedAt: now,
	}

	m.mu.Lock()
	m.jobs[id] = job
	m.order = append(m.order, id)
	m.mu.Unlock()

	m.broadcast("job_created", map[string]interface{}{
		"job_id": id,
		"config": config,
		"status": string(domain.JobPending),
	})

	// Start execution in background.
	go m.execute(id)

	return id, nil
}

// Get returns a job by ID.
func (m *Manager) Get(id string) (*domain.Job, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	job, ok := m.jobs[id]
	if !ok {
		return nil, fmt.Errorf("job not found: %s", id)
	}
	return job, nil
}

// List returns jobs matching the filter.
func (m *Manager) List(filter domain.JobFilter) []*domain.Job {
	m.mu.RLock()
	defer m.mu.RUnlock()

	statusSet := make(map[domain.JobStatus]bool)
	for _, s := range filter.Status {
		statusSet[s] = true
	}

	var result []*domain.Job
	for _, id := range m.order {
		job := m.jobs[id]
		if len(statusSet) > 0 && !statusSet[job.Status] {
			continue
		}
		result = append(result, job)
		if filter.Limit > 0 && len(result) >= filter.Limit {
			break
		}
	}
	return result
}

// Cancel requests cancellation of a running job.
func (m *Manager) Cancel(id string) error {
	m.mu.Lock()
	job, ok := m.jobs[id]
	if !ok {
		m.mu.Unlock()
		return fmt.Errorf("job not found: %s", id)
	}
	if job.Status != domain.JobRunning && job.Status != domain.JobPending {
		m.mu.Unlock()
		return fmt.Errorf("job %s is not cancellable (status: %s)", id, job.Status)
	}
	job.Status = domain.JobCancelled
	now := time.Now()
	job.CompletedAt = &now
	m.mu.Unlock()

	_ = m.runner.Stop(id)

	m.broadcast("job_cancelled", map[string]interface{}{
		"job_id": id,
	})

	return nil
}

// Stats returns aggregate job statistics.
func (m *Manager) Stats() domain.JobStats {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var stats domain.JobStats
	stats.Total = len(m.jobs)
	for _, job := range m.jobs {
		switch job.Status {
		case domain.JobPending:
			stats.Pending++
		case domain.JobRunning:
			stats.Running++
		case domain.JobCompleted:
			stats.Completed++
		case domain.JobFailed:
			stats.Failed++
		case domain.JobCancelled:
			stats.Cancelled++
		}
	}
	return stats
}

// execute runs a single job via the h2kvmctl runner.
func (m *Manager) execute(jobID string) {
	m.mu.Lock()
	job, ok := m.jobs[jobID]
	if !ok {
		m.mu.Unlock()
		return
	}
	job.Status = domain.JobRunning
	now := time.Now()
	job.StartedAt = &now
	config := job.Config
	m.mu.Unlock()

	m.broadcast("job_started", map[string]interface{}{
		"job_id": jobID,
	})

	events, err := m.runner.Run(m.ctx, jobID, config)
	if err != nil {
		m.mu.Lock()
		job.Status = domain.JobFailed
		job.Error = err.Error()
		done := time.Now()
		job.CompletedAt = &done
		m.mu.Unlock()

		m.broadcast("job_failed", map[string]interface{}{
			"job_id": jobID,
			"error":  err.Error(),
		})
		return
	}

	m.processEvents(jobID, events)
}

// processEvents reads runner events and updates job state + broadcasts.
func (m *Manager) processEvents(jobID string, events <-chan ports.RunnerEvent) {
	for event := range events {
		m.mu.Lock()
		job, ok := m.jobs[jobID]
		if !ok {
			m.mu.Unlock()
			continue
		}

		switch event.Type {
		case ports.EventStarted:
			job.PID = event.PID

		case ports.EventLog:
			// Keep last 500 log lines.
			if len(job.LogLines) >= 500 {
				job.LogLines = job.LogLines[1:]
			}
			job.LogLines = append(job.LogLines, event.Line)
			m.mu.Unlock()

			m.broadcast("job_log", map[string]interface{}{
				"job_id": jobID,
				"line":   event.Line,
			})
			continue

		case ports.EventProgress:
			job.Progress = event.Progress
			m.mu.Unlock()

			m.broadcast("job_progress", map[string]interface{}{
				"job_id":   jobID,
				"progress": event.Progress,
			})
			continue

		case ports.EventDone:
			done := time.Now()
			job.CompletedAt = &done
			if event.ExitCode == 0 && event.Err == nil {
				job.Status = domain.JobCompleted
				// Keep cancelled status if already set.
				if job.Status == domain.JobCancelled {
					m.mu.Unlock()
					continue
				}
				job.Status = domain.JobCompleted
			} else if job.Status != domain.JobCancelled {
				job.Status = domain.JobFailed
				if event.Err != nil {
					job.Error = event.Err.Error()
				} else {
					job.Error = fmt.Sprintf("exit code %d", event.ExitCode)
				}
			}
			m.mu.Unlock()

			eventType := "job_completed"
			data := map[string]interface{}{"job_id": jobID}
			if job.Status == domain.JobFailed {
				eventType = "job_failed"
				data["error"] = job.Error
			}
			m.broadcast(eventType, data)
			continue
		}
		m.mu.Unlock()
	}
}

func (m *Manager) broadcast(msgType string, data map[string]interface{}) {
	if m.broadcaster != nil {
		m.broadcaster.Broadcast(msgType, data)
	} else {
		log.Printf("[%s] %v", msgType, data)
	}
}
