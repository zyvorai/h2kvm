// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os/exec"
	"strings"
	"sync"
	"time"
)

// --- Batch VM Operations ---

// handleBatchOperation executes a virsh operation on multiple VMs concurrently.
//
// POST /api/v1/vms/batch
// Body: {"names": ["vm1", "vm2"], "operation": "start"|"stop"|"reboot"|"pause"|"resume"|"snapshot"|"destroy"}
func (s *Server) handleBatchOperation(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Names     []string `json:"names"`
		Operation string   `json:"operation"`
	}
	if err := readJSON(r, &req); err != nil {
		jsonError(w, http.StatusBadRequest, err.Error())
		return
	}

	if len(req.Names) == 0 {
		jsonError(w, http.StatusBadRequest, "names array is required and must not be empty")
		return
	}
	if len(req.Names) > 50 {
		jsonError(w, http.StatusBadRequest, "maximum 50 VMs per batch operation")
		return
	}

	// Map operation to virsh command.
	opMap := map[string]string{
		"start":   "start",
		"stop":    "shutdown",
		"reboot":  "reboot",
		"pause":   "suspend",
		"resume":  "resume",
		"destroy": "destroy",
	}

	virshCmd, ok := opMap[req.Operation]
	if !ok && req.Operation != "snapshot" {
		jsonError(w, http.StatusBadRequest,
			"operation must be one of: start, stop, reboot, pause, resume, snapshot, destroy")
		return
	}

	log.Printf("[batch] batchOperation op=%s vms=%v from %s", req.Operation, req.Names, r.RemoteAddr)

	type batchResult struct {
		Name    string `json:"name"`
		Success bool   `json:"success"`
		Message string `json:"message,omitempty"`
		Error   string `json:"error,omitempty"`
	}

	results := make([]batchResult, len(req.Names))
	var wg sync.WaitGroup
	var mu sync.Mutex

	// Semaphore to limit concurrency.
	sem := make(chan struct{}, 10)

	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Minute)
	defer cancel()

	for i, name := range req.Names {
		safeName := safeNameRe.ReplaceAllString(name, "")
		if safeName == "" || safeName != name {
			results[i] = batchResult{Name: name, Success: false, Error: "invalid VM name"}
			continue
		}

		wg.Add(1)
		go func(idx int, vmName string) {
			defer wg.Done()

			sem <- struct{}{}        // Acquire semaphore.
			defer func() { <-sem }() // Release semaphore.

			if req.Operation == "snapshot" {
				snapName := fmt.Sprintf("batch-%s", time.Now().Format("20060102-150405"))
				out, err := exec.CommandContext(ctx, "virsh", "snapshot-create-as", vmName, snapName).CombinedOutput()
				mu.Lock()
				if err != nil {
					results[idx] = batchResult{
						Name:    vmName,
						Success: false,
						Error:   fmt.Sprintf("snapshot failed: %s", strings.TrimSpace(string(out))),
					}
				} else {
					results[idx] = batchResult{
						Name:    vmName,
						Success: true,
						Message: fmt.Sprintf("Snapshot %s created", snapName),
					}
				}
				mu.Unlock()
				return
			}

			out, err := exec.CommandContext(ctx, "virsh", virshCmd, vmName).CombinedOutput()
			mu.Lock()
			if err != nil {
				results[idx] = batchResult{
					Name:    vmName,
					Success: false,
					Error:   strings.TrimSpace(string(out)),
				}
			} else {
				results[idx] = batchResult{
					Name:    vmName,
					Success: true,
					Message: strings.TrimSpace(string(out)),
				}
			}
			mu.Unlock()
		}(i, safeName)
	}

	wg.Wait()

	// Count successes and failures.
	successes := 0
	failures := 0
	for _, res := range results {
		if res.Success {
			successes++
		} else {
			failures++
		}
	}

	log.Printf("[batch] batchOperation op=%s completed: %d success, %d failed", req.Operation, successes, failures)
	s.auditLog(r, "batch_"+req.Operation, fmt.Sprintf("%d VMs", len(req.Names)),
		fmt.Sprintf("success=%d failed=%d", successes, failures))

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"operation": req.Operation,
		"total":     len(req.Names),
		"successes": successes,
		"failures":  failures,
		"results":   results,
	})
}
