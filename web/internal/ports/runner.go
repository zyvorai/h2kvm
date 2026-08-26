// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package ports

import (
	"context"

	"github.com/hyper2kvm/web/internal/domain"
)

// RunnerEventType classifies events emitted by the h2kvmctl subprocess.
type RunnerEventType int

const (
	EventLog      RunnerEventType = iota // A log line from stdout/stderr
	EventProgress                        // A parsed progress update
	EventStarted                         // Process has started (PID available)
	EventDone                            // Process has exited
)

// RunnerEvent carries a single event from the h2kvmctl subprocess.
type RunnerEvent struct {
	Type     RunnerEventType
	JobID    string
	Line     string               // Log line (EventLog)
	Progress *domain.JobProgress  // Parsed progress (EventProgress)
	PID      int                  // Process ID (EventStarted)
	ExitCode int                  // Exit code (EventDone)
	Err      error                // Error if any (EventDone)
}

// H2KVMRunner manages h2kvmctl subprocess lifecycle.
type H2KVMRunner interface {
	// Run starts h2kvmctl with the given migration config, returning a channel
	// of events. The channel is closed when the process exits.
	Run(ctx context.Context, jobID string, config domain.MigrationConfig) (<-chan RunnerEvent, error)
	// Stop sends SIGTERM to the process for the given job, escalating to
	// SIGKILL after a timeout.
	Stop(jobID string) error
	// BinaryPath returns the resolved h2kvmctl binary path.
	BinaryPath() string
}
