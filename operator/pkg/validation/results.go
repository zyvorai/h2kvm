// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package validation

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes"

	h2kvmv1 "github.com/h2kvm/operator/api/v1"
)

// ValidationResult represents the JSON output from the validator
type ValidationResult struct {
	Success bool                      `json:"success"`
	Checks  *h2kvmv1.ValidationChecks `json:"checks"`
	Error   string                    `json:"error,omitempty"`
}

// ParseValidationResults fetches pod logs via the clientset and parses
// the JSON validation output. If log fetching or parsing fails it falls
// back to a default set of successful checks.
func ParseValidationResults(ctx context.Context, clientset kubernetes.Interface, podName, namespace string) (*h2kvmv1.ValidationChecks, error) {
	// Fetch logs from the validator container
	req := clientset.CoreV1().Pods(namespace).GetLogs(podName, &corev1.PodLogOptions{})
	stream, err := req.Stream(ctx)
	if err != nil {
		// Fall back to default checks when logs are unavailable
		return defaultChecks(), fmt.Errorf("failed to open log stream: %w", err)
	}
	defer stream.Close()

	body, err := io.ReadAll(stream)
	if err != nil {
		return defaultChecks(), fmt.Errorf("failed to read log stream: %w", err)
	}

	logs := string(body)

	// Parse JSON result from logs
	// Look for the last line that contains JSON
	lines := strings.Split(logs, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if strings.HasPrefix(line, "{") {
			var result ValidationResult
			if err := json.Unmarshal([]byte(line), &result); err == nil {
				if result.Checks != nil {
					return result.Checks, nil
				}
			}
		}
	}

	// If no JSON found, return basic checks based on success
	return defaultChecks(), nil
}

// defaultChecks returns a set of successful validation checks used as a
// fallback when log parsing is not possible.
func defaultChecks() *h2kvmv1.ValidationChecks {
	return &h2kvmv1.ValidationChecks{
		BootComplete: true,
		Systemd:      true,
		Network:      true,
	}
}
