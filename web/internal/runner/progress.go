// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package runner

import (
	"regexp"
	"strconv"
	"strings"

	"github.com/h2kvm/web/internal/domain"
)

// Patterns for progress parsing.
var (
	// [PROGRESS] pct|current|total|rate|eta
	structuredProgressRe = regexp.MustCompile(`^\[PROGRESS\]\s*(.+)$`)
	// "progress: 45%" or "progress: 45.2%"
	simpleProgressRe = regexp.MustCompile(`(?i)progress:\s*(\d+\.?\d*)%`)
	// "Processing disk 1/3: boot.vmdk"
	diskProcessingRe = regexp.MustCompile(`Processing disk (\d+)/(\d+):\s*(.+)`)
	// govc: "Downloading ... 45%"
	govcProgressRe = regexp.MustCompile(`Downloading.*?(\d+)%`)
)

// parseProgressLine attempts to extract structured progress from an h2kvmctl output line.
func parseProgressLine(line string) (*domain.JobProgress, bool) {
	// Try structured [PROGRESS] format: pct|current|total|rate|eta
	if m := structuredProgressRe.FindStringSubmatch(line); m != nil {
		parts := strings.SplitN(m[1], "|", 5)
		if len(parts) >= 1 {
			prog := &domain.JobProgress{}
			if pct, err := strconv.ParseFloat(strings.TrimSpace(parts[0]), 64); err == nil {
				prog.PercentComplete = pct
			}
			if len(parts) >= 2 {
				if cur, err := strconv.ParseInt(strings.TrimSpace(parts[1]), 10, 64); err == nil {
					prog.BytesProcessed = cur
				}
			}
			if len(parts) >= 3 {
				if total, err := strconv.ParseInt(strings.TrimSpace(parts[2]), 10, 64); err == nil {
					prog.TotalBytes = total
				}
			}
			if len(parts) >= 4 {
				prog.Rate = strings.TrimSpace(parts[3])
			}
			if len(parts) >= 5 {
				prog.ETA = strings.TrimSpace(parts[4])
			}
			return prog, true
		}
	}

	// Try "progress: N%" pattern.
	if m := simpleProgressRe.FindStringSubmatch(line); m != nil {
		pct, _ := strconv.ParseFloat(m[1], 64)
		return &domain.JobProgress{
			PercentComplete: pct,
			Phase:           "converting",
		}, true
	}

	// Try "Processing disk X/Y: name" pattern.
	if m := diskProcessingRe.FindStringSubmatch(line); m != nil {
		current, _ := strconv.Atoi(m[1])
		total, _ := strconv.Atoi(m[2])
		pct := float64(current-1) / float64(total) * 100
		return &domain.JobProgress{
			Phase:           "processing",
			PercentComplete: pct,
			CurrentStep:     strings.TrimSpace(m[3]),
		}, true
	}

	// Try govc download progress.
	if m := govcProgressRe.FindStringSubmatch(line); m != nil {
		pct, _ := strconv.ParseFloat(m[1], 64)
		return &domain.JobProgress{
			Phase:           "exporting",
			PercentComplete: pct,
			CurrentStep:     "Downloading from vSphere",
		}, true
	}

	return nil, false
}

// isGovcProgress returns true if the line looks like a govc download progress line.
func isGovcProgress(line string) bool {
	return strings.Contains(line, "Downloading") && strings.Contains(line, "%")
}
