// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"bufio"
	"fmt"
	"strings"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// LogLineMsg delivers a single line of subprocess output.
type LogLineMsg struct{ Line string }

// ProcessStartedMsg signals that the subprocess has started.
type ProcessStartedMsg struct{ PID int }

// ProcessDoneMsg signals that the subprocess has exited.
type ProcessDoneMsg struct {
	ExitCode int
	Err      error
}

// Runner manages the h2kvmctl subprocess lifecycle.
type Runner struct {
	mu         sync.Mutex
	cmd        *exec.Cmd
	cancel     chan struct{}
	running    bool
	program    *tea.Program
	configPath string // temp YAML config file
	binaryPath string // explicit binary path (empty = auto-detect)
}

// NewRunner creates a new Runner. If binaryPath is non-empty it is used
// instead of auto-detection.
func NewRunner(binaryPath string) *Runner {
	return &Runner{
		cancel:     make(chan struct{}),
		binaryPath: binaryPath,
	}
}

// BinaryPath returns the configured or auto-detected binary path.
// Search order: --binary flag → ./h2kvmctl → ../h2kvmctl → PATH → fallback.
func (r *Runner) BinaryPath() string {
	if r.binaryPath != "" {
		return r.binaryPath
	}
	// Check local directory (when running from repo root)
	if _, err := os.Stat("./h2kvmctl"); err == nil {
		return "./h2kvmctl"
	}
	// Check parent directory (when running from zkvm/)
	if _, err := os.Stat("../h2kvmctl"); err == nil {
		return "../h2kvmctl"
	}
	// Check PATH
	if p, err := exec.LookPath("h2kvmctl"); err == nil {
		return p
	}
	return "h2kvmctl"
}

// SetProgram stores the tea.Program reference for sending messages.
func (r *Runner) SetProgram(p *tea.Program) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.program = p
}

// findBinary locates the h2kvmctl Python CLI binary.
// If override is non-empty it is returned directly.
func findBinary(override string) string {
	if override != "" {
		return override
	}

	// Check PATH first — prefer the Python entry point.
	for _, name := range []string{"h2kvmctl", "hyper2kvm"} {
		if p, err := exec.LookPath(name); err == nil {
			return p
		}
	}

	// Check common locations (development repo + installed).
	candidates := []string{
		"./h2kvmctl",
		"../h2kvmctl",
		"/usr/local/bin/h2kvmctl",
		"/usr/bin/h2kvmctl",
	}
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}

	return "h2kvmctl"
}

// ConfigPath returns the path of the last generated temp config file.
func (r *Runner) ConfigPath() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.configPath
}

// StartWithConfig writes yamlContent to a temp file and launches
// h2kvmctl --config <tempfile>, streaming output to the Bubble Tea program.
// RunWithArgs starts h2kvmctl with direct CLI arguments (for quick migrate).
func (r *Runner) RunWithArgs(args []string) tea.Cmd {
	return func() tea.Msg {
		r.mu.Lock()
		if r.running {
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: nil}
		}

		binary := findBinary(r.binaryPath)
		if !filepath.IsAbs(binary) {
			if abs, err := filepath.Abs(binary); err == nil {
				binary = abs
			}
		}

		r.cmd = exec.Command(binary, args...)
		r.cancel = make(chan struct{})
		r.running = true

		stdoutPipe, err := r.cmd.StdoutPipe()
		if err != nil {
			r.running = false
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: fmt.Errorf("failed to create stdout pipe for h2kvmctl: %w", err)}
		}
		r.cmd.Stderr = r.cmd.Stdout

		if err := r.cmd.Start(); err != nil {
			r.running = false
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: fmt.Errorf("failed to start h2kvmctl (%s): %w — verify the binary exists and is executable", binary, err)}
		}

		pid := r.cmd.Process.Pid
		prog := r.program
		r.mu.Unlock()

		if prog != nil {
			prog.Send(ProcessStartedMsg{PID: pid})
		}

		reader := bufio.NewReader(stdoutPipe)
		for {
			line, err := reader.ReadString('\n')
			if len(line) > 0 {
				line = strings.TrimRight(line, "\r\n")
				if len(line) > 0 && prog != nil {
					prog.Send(LogLineMsg{Line: line})
				}
			}
			if err != nil {
				break
			}
		}

		exitCode := 0
		waitErr := r.cmd.Wait()
		if waitErr != nil {
			if exitErr, ok := waitErr.(*exec.ExitError); ok {
				exitCode = exitErr.ExitCode()
			} else {
				exitCode = -1
			}
		}

		r.mu.Lock()
		r.running = false
		r.mu.Unlock()

		return ProcessDoneMsg{ExitCode: exitCode, Err: waitErr}
	}
}

func (r *Runner) StartWithConfig(yamlContent string) tea.Cmd {
	return func() tea.Msg {
		r.mu.Lock()
		if r.running {
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: nil}
		}

		// Write YAML to a temp file.
		tmpDir := os.TempDir()
		tmpFile, err := os.CreateTemp(tmpDir, "zkvm-*.yaml")
		if err != nil {
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: fmt.Errorf("create temp config: %w", err)}
		}

		configPath := tmpFile.Name()

		if _, err := tmpFile.WriteString(yamlContent); err != nil {
			tmpFile.Close()
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: fmt.Errorf("write temp config: %w", err)}
		}
		tmpFile.Close()

		r.configPath = configPath

		binary := findBinary(r.binaryPath)
		// Resolve to absolute path to avoid PATH issues.
		if !filepath.IsAbs(binary) {
			if abs, err := filepath.Abs(binary); err == nil {
				binary = abs
			}
		}

		// Use sudo if not already root.
		if os.Getuid() != 0 {
			r.cmd = exec.Command("sudo", binary, "--config", configPath)
		} else {
			r.cmd = exec.Command(binary, "--config", configPath)
		}
		r.cancel = make(chan struct{})
		r.running = true

		// Merge stdout and stderr into a single pipe.
		stdoutPipe, err := r.cmd.StdoutPipe()
		if err != nil {
			r.running = false
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: err}
		}
		r.cmd.Stderr = r.cmd.Stdout

		if err := r.cmd.Start(); err != nil {
			r.running = false
			r.mu.Unlock()
			return ProcessDoneMsg{ExitCode: -1, Err: err}
		}

		pid := r.cmd.Process.Pid
		prog := r.program
		r.mu.Unlock()

		if prog != nil {
			prog.Send(ProcessStartedMsg{PID: pid})
		}

		// Read output splitting on \n or \r so govc progress (which uses \r) is streamed live.
		scanner := bufio.NewScanner(stdoutPipe)
		scanner.Split(scanLinesOrCR)
		var lastProgress string
		var lastProgressTime time.Time
		for scanner.Scan() {
			line := scanner.Text()
			if line == "" || prog == nil {
				continue
			}
			// Throttle govc progress lines (contain "Downloading" + "%") to once per 3s.
			if strings.Contains(line, "Downloading") && strings.Contains(line, "%") {
				now := time.Now()
				if line == lastProgress || now.Sub(lastProgressTime) < 3*time.Second {
					continue
				}
				lastProgress = line
				lastProgressTime = now
			}
			prog.Send(LogLineMsg{Line: line})
		}
		if err := scanner.Err(); err != nil {
			if prog != nil {
				prog.Send(LogLineMsg{Line: "[read error: " + err.Error() + "]"})

			}
		}

		waitErr := r.cmd.Wait()

		// Clean up temp config file after subprocess has finished reading it.
		os.Remove(configPath)

		exitCode := 0
		if waitErr != nil {
			if exitErr, ok := waitErr.(*exec.ExitError); ok {
				exitCode = exitErr.ExitCode()
			} else {
				exitCode = -1
			}
		}

		r.mu.Lock()
		r.running = false
		r.mu.Unlock()

		return ProcessDoneMsg{ExitCode: exitCode, Err: waitErr}
	}
}

// Stop sends SIGTERM to the subprocess. If it doesn't exit within 5 seconds,
// SIGKILL is sent. The main reader goroutine's cmd.Wait() handles reaping.
func (r *Runner) Stop() {
	r.mu.Lock()
	if !r.running || r.cmd == nil || r.cmd.Process == nil {
		r.mu.Unlock()
		return
	}
	proc := r.cmd.Process
	_ = proc.Signal(syscall.SIGTERM)
	r.mu.Unlock()

	// Wait briefly, then escalate to SIGKILL if still running.
	time.AfterFunc(5*time.Second, func() {
		r.mu.Lock()
		defer r.mu.Unlock()
		if r.running && r.cmd != nil && r.cmd.Process != nil {
			_ = r.cmd.Process.Signal(syscall.SIGKILL)
		}
	})
}

// IsRunning returns whether a subprocess is currently active.
func (r *Runner) IsRunning() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.running
}

// scanLinesOrCR is a bufio.SplitFunc that splits on \n, \r\n, or bare \r.
// This captures govc progress output which uses \r for in-place updates.
func scanLinesOrCR(data []byte, atEOF bool) (advance int, token []byte, err error) {
	if atEOF && len(data) == 0 {
		return 0, nil, nil
	}
	for i := 0; i < len(data); i++ {
		if data[i] == '\n' {
			return i + 1, data[:i], nil
		}
		if data[i] == '\r' {
			// \r\n counts as one line break
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
