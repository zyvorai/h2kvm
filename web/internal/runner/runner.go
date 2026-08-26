// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package runner

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/h2kvm/web/internal/domain"
	"github.com/h2kvm/web/internal/ports"

	"gopkg.in/yaml.v3"
)

// Runner manages h2kvmctl subprocesses. Implements ports.H2KVMRunner.
type Runner struct {
	mu         sync.Mutex
	binaryPath string
	processes  map[string]*runningProcess
}

type runningProcess struct {
	cmd    *exec.Cmd
	cancel context.CancelFunc
}

// New creates a new Runner. If binaryPath is empty, auto-detection is used.
func New(binaryPath string) *Runner {
	return &Runner{
		binaryPath: binaryPath,
		processes:  make(map[string]*runningProcess),
	}
}

// BinaryPath returns the configured or auto-detected h2kvmctl path.
func (r *Runner) BinaryPath() string {
	return findBinary(r.binaryPath)
}

// Run starts h2kvmctl with the given migration config, returning a channel
// of runner events. Adapted from zkvm/internal/ui/standalone/runner.go.
func (r *Runner) Run(ctx context.Context, jobID string, config domain.MigrationConfig) (<-chan ports.RunnerEvent, error) {
	// Marshal config to YAML.
	yamlBytes, err := yaml.Marshal(&config)
	if err != nil {
		return nil, fmt.Errorf("marshal config: %w", err)
	}

	// Write to temp file.
	tmpFile, err := os.CreateTemp("", "h2kweb-*.yaml")
	if err != nil {
		return nil, fmt.Errorf("create temp config: %w", err)
	}
	if _, err := tmpFile.Write(yamlBytes); err != nil {
		tmpFile.Close()
		os.Remove(tmpFile.Name())
		return nil, fmt.Errorf("write temp config: %w", err)
	}
	tmpFile.Close()
	configPath := tmpFile.Name()

	// Resolve binary.
	binary := findBinary(r.binaryPath)
	if !filepath.IsAbs(binary) {
		if abs, err := filepath.Abs(binary); err == nil {
			binary = abs
		}
	}

	// Build command — use sudo if not root (same as zkvm runner).
	procCtx, procCancel := context.WithCancel(ctx)
	var cmd *exec.Cmd
	if os.Getuid() != 0 {
		cmd = exec.CommandContext(procCtx, "sudo", binary, "--config", configPath)
	} else {
		cmd = exec.CommandContext(procCtx, binary, "--config", configPath)
	}

	// Merge stdout and stderr.
	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		procCancel()
		os.Remove(configPath)
		return nil, fmt.Errorf("stdout pipe: %w", err)
	}
	cmd.Stderr = cmd.Stdout

	if err := cmd.Start(); err != nil {
		procCancel()
		os.Remove(configPath)
		return nil, fmt.Errorf("start h2kvmctl (%s): %w", binary, err)
	}

	// Track the running process.
	r.mu.Lock()
	r.processes[jobID] = &runningProcess{cmd: cmd, cancel: procCancel}
	r.mu.Unlock()

	events := make(chan ports.RunnerEvent, 256)

	// Send started event.
	events <- ports.RunnerEvent{
		Type:  ports.EventStarted,
		JobID: jobID,
		PID:   cmd.Process.Pid,
	}

	// Stream output in a goroutine.
	go func() {
		defer close(events)
		defer os.Remove(configPath)
		defer func() {
			r.mu.Lock()
			delete(r.processes, jobID)
			r.mu.Unlock()
		}()

		scanner := bufio.NewScanner(stdoutPipe)
		scanner.Split(scanLinesOrCR)

		var lastProgress string
		var lastProgressTime time.Time

		for scanner.Scan() {
			line := scanner.Text()
			if line == "" {
				continue
			}

			// Try to parse as structured progress.
			if prog, ok := parseProgressLine(line); ok {
				events <- ports.RunnerEvent{
					Type:     ports.EventProgress,
					JobID:    jobID,
					Progress: prog,
				}
				continue
			}

			// Throttle govc download progress lines to once per 3s.
			if isGovcProgress(line) {
				now := time.Now()
				if line == lastProgress || now.Sub(lastProgressTime) < 3*time.Second {
					continue
				}
				lastProgress = line
				lastProgressTime = now
			}

			// Regular log line.
			events <- ports.RunnerEvent{
				Type:  ports.EventLog,
				JobID: jobID,
				Line:  line,
			}
		}

		// Wait for process exit.
		waitErr := cmd.Wait()
		exitCode := 0
		if waitErr != nil {
			if exitErr, ok := waitErr.(*exec.ExitError); ok {
				exitCode = exitErr.ExitCode()
			} else {
				exitCode = -1
			}
		}

		events <- ports.RunnerEvent{
			Type:     ports.EventDone,
			JobID:    jobID,
			ExitCode: exitCode,
			Err:      waitErr,
		}
	}()

	return events, nil
}

// Stop sends SIGTERM to the h2kvmctl process for the given job.
// If the process doesn't exit within 5 seconds, SIGKILL is sent.
func (r *Runner) Stop(jobID string) error {
	r.mu.Lock()
	proc, ok := r.processes[jobID]
	r.mu.Unlock()

	if !ok {
		return fmt.Errorf("no running process for job %s", jobID)
	}

	if proc.cmd.Process == nil {
		return nil
	}

	_ = proc.cmd.Process.Signal(syscall.SIGTERM)

	// Escalate to SIGKILL after 5 seconds.
	time.AfterFunc(5*time.Second, func() {
		r.mu.Lock()
		p, exists := r.processes[jobID]
		r.mu.Unlock()
		if exists && p.cmd.Process != nil {
			_ = p.cmd.Process.Signal(syscall.SIGKILL)
		}
	})

	return nil
}

// findBinary locates the h2kvmctl binary.
// Search order: override → PATH → common locations → fallback.
func findBinary(override string) string {
	if override != "" {
		return override
	}

	for _, name := range []string{"h2kvmctl", "h2kvm"} {
		if p, err := exec.LookPath(name); err == nil {
			return p
		}
	}

	candidates := []string{
		"/usr/local/bin/h2kvmctl",
		"/usr/local/sbin/h2kvmctl",
		"/usr/bin/h2kvmctl",
		"./h2kvmctl",
		"../h2kvmctl",
	}
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}

	return "h2kvmctl"
}

// scanLinesOrCR is a bufio.SplitFunc that splits on \n, \r\n, or bare \r.
// This captures govc progress output which uses \r for in-place updates.
// Copied from zkvm/internal/ui/standalone/runner.go.
func scanLinesOrCR(data []byte, atEOF bool) (advance int, token []byte, err error) {
	if atEOF && len(data) == 0 {
		return 0, nil, nil
	}
	for i := 0; i < len(data); i++ {
		if data[i] == '\n' {
			return i + 1, data[:i], nil
		}
		if data[i] == '\r' {
			if i+1 < len(data) && data[i+1] == '\n' {
				return i + 2, data[:i], nil
			}
			return i + 1, data[:i], nil
		}
	}
	if atEOF {
		return len(data), data, nil
	}
	return 0, nil, nil
}
